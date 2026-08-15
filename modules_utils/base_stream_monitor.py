# modules_utils/base_stream_monitor.py
import asyncio
import aiohttp
import discord
from typing import Dict, Any, Optional, List
from abc import abstractmethod
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, LiveEmojis, Emojis
from modules_utils.event_manager import EventManager
from modules_utils.stream_notification_helper import StreamNotificationHelper
from modules_utils.base_monitor import BaseMonitor

from modules_utils.generic_stream_database import GenericStreamDatabase

from modules_utils.text_filter import TextFilter

class BaseStreamMonitor(BaseMonitor):
    """Базовый класс для мониторинга стримов на различных платформах.

    Наследует общие поля и жизненный цикл от BaseMonitor.
    Добавляет стрим-специфичную логику: circuit breaker, fetch-цикл,
    обработку новых/активных/завершённых стримов.
    """

    def __init__(self, platform_name: str, config: Dict[str, Any], discord_bot, db_helper: Optional[GenericStreamDatabase] = None):
        super().__init__(
            platform_name=platform_name,
            platform_id=config.get("platform_id", ""),
            discord_bot=discord_bot,
        )

        self.config = config
        self.db_helper = db_helper

        # Параметры из конфига
        from settings.config import Config
        default_intervals = {
            "VK Live": Config.VK_LIVE_CHECK_INTERVAL,
            "YouTube": Config.YOUTUBE_CHECK_INTERVAL,
            "Twitch": Config.TWITCH_CHECK_INTERVAL,
            "Rutube": Config.RUTUBE_CHECK_INTERVAL
        }
        fallback_interval = default_intervals.get(self.platform_name, 300)
        self.check_interval = config.get("check_interval", fallback_interval)
        self.send_channel_notification = config.get("send_channel_notification", True)
        self.create_discord_event = config.get("create_discord_event", True)
        self.discord_channel_id = config.get("discord_channel_id")
        self.active_streams_data: Dict[str, Any] = {}  # { stream_id: stream_data }

        # Подтверждение завершения стрима: одна неудачная проверка (сетевой сбой,
        # временная ошибка API, лаг RSS-ленты и т.п.) не должна сразу считаться
        # завершением стрима. Стрим считается завершённым только если он отсутствует
        # в нескольких проверках подряд.
        self.end_confirmation_checks = max(1, config.get("end_confirmation_checks", 2))
        self._missed_checks: Dict[str, int] = {}  # { stream_id: количество проверок подряд без стрима }

        # Circuit Breaker: пауза монитора при серии последовательных ошибок
        self.consecutive_errors = 0
        self.circuit_open = False
        self.circuit_breaker_threshold = config.get("circuit_breaker_threshold", 5)
        self.circuit_breaker_pause = config.get("circuit_breaker_pause", 300)  # секунды

    @abstractmethod
    async def fetch_current_streams(self) -> List[Dict[str, Any]]:
        """Получает список текущих активных стримов с платформы."""
        pass

    async def get_active_streams_from_db(self) -> List[str]:
        """Получает список ID активных стримов из локальной БД."""
        if self.db_helper:
            return await self.db_helper.get_active_stream_ids(self.platform_id)
        return []

    async def get_all_processed_ids_from_db(self) -> List[str]:
        """Получает список всех ID (активных и завершенных) из локальной БД."""
        if self.db_helper:
            if hasattr(self.db_helper, "get_all_processed_ids"):
                return await self.db_helper.get_all_processed_ids(self.platform_id)
            return await self.db_helper.get_active_stream_ids(self.platform_id)
        return []

    async def save_stream_to_db(self, stream_id: str, event_id: Optional[str]):
        """Сохраняет данные о новом стриме в БД."""
        if self.db_helper:
            await self.db_helper.save_stream(stream_id, self.platform_id, event_id)

    async def mark_stream_finished_in_db(self, stream_id: str):
        """Помечает стрим как завершенный в БД."""
        if self.db_helper:
            await self.db_helper.mark_finished(stream_id)

    async def get_event_id_from_db(self, stream_id: str) -> Optional[str]:
        """Получает ID мероприятия Discord из БД."""
        if self.db_helper:
            return await self.db_helper.get_event_id(stream_id)
        return None

    async def start(self):
        """Starts the monitoring loop with jitter."""
        if not self.platform_id:
            await send_to_any_log("critical", f"[{self.platform_name}] Platform ID (platform_id) is not set", emoji=LogEmojis.CRITICAL)
            return

        self.is_running = True
        
        # Spread monitor startup in time (jitter) to prevent load spikes
        import random
        await asyncio.sleep(random.uniform(0, 30))

        from modules_utils.http_client import HttpClient
        from modules_utils.task_scheduler import scheduler
        self.session = await HttpClient.get_session()

        try:
            _outer_errors = 0
            while self.is_running:
                try:
                    lock = scheduler.get_check_lock()

                    async with lock:
                        try:
                            await asyncio.wait_for(self.check_status(), timeout=300)
                        except asyncio.TimeoutError:
                            await send_to_any_log("error", f"[{self.platform_name}] Check {self.platform_id} timed out (300s)", emoji=LogEmojis.ERROR)
                        except Exception as e:
                            await send_to_any_log("error", f"[{self.platform_name}] Unexpected error in check loop {self.platform_id}: {e}", emoji=LogEmojis.ERROR)

                    if self.circuit_open:
                        await asyncio.sleep(self.circuit_breaker_pause)
                        self.circuit_open = False
                        self.consecutive_errors = 0

                    _outer_errors = 0

                    jittered_interval = self.check_interval * random.uniform(0.9, 1.1)
                    await asyncio.sleep(jittered_interval)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    _outer_errors += 1
                    self.error_count += 1
                    backoff = min(60 * (2 ** min(_outer_errors - 1, 4)), 900)
                    await send_to_any_log("error",
                        f"[{self.platform_name}] Unexpected error in outer loop {self.platform_id}: {e}. "
                        f"Retry in {backoff}s (attempt {_outer_errors})",
                        emoji=LogEmojis.ERROR)
                    await asyncio.sleep(backoff)
        except asyncio.CancelledError:
            self.is_running = False
            try:
                from modules_utils.live_role_helper import LiveRoleHelper
                for stream_id in list(self.active_streams_data.keys()):
                    await LiveRoleHelper.manage_role(self.discord_bot, self.config, self.platform_name, stream_id, assign=False)
            except Exception:
                pass

    def get_headers(self) -> Dict[str, str]:
        """Returns headers for HTTP requests."""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def check_status(self, force_end: bool = False):
        """Main status check logic for streams.

        Args:
            force_end: If True, streams missing from the current check are ended
                immediately without waiting for confirmation checks.
        """
        from datetime import datetime
        self.last_check_time = datetime.now()
        try:
            await send_to_any_log("info", f"[{self.platform_name}] New check started: {self.config.get('name', self.platform_id)}", emoji=LogEmojis.INFO, targets=["console", "file"])
            current_streams = await self.fetch_current_streams()
            
            self.last_success_time = datetime.now()
            self.consecutive_errors = 0
            self.circuit_open = False

            display_name = self.config.get('name', self.platform_id)
            filtered_streams = []
            for stream in current_streams:
                title = stream.get("title", "")
                description = stream.get("description", "")
                if TextFilter.should_skip(title, self.config, context=f"{self.platform_name}:{display_name}", second_text=description):
                    continue
                filtered_streams.append(stream)
            
            current_streams = filtered_streams
            active_in_db = await self.get_active_streams_from_db()
            
            current_ids = {str(s.get("stream_id")) for s in current_streams if s.get("stream_id")}
            
            for stream in current_streams:
                stream_id = str(stream.get("stream_id"))
                if stream_id not in active_in_db:
                    await self._handle_new_stream(stream)
                else:
                    await self._handle_existing_stream(stream_id)
                self._missed_checks.pop(stream_id, None)
            
            for db_id in active_in_db:
                if db_id not in current_ids:
                    misses = self._missed_checks.get(db_id, 0) + 1
                    self._missed_checks[db_id] = misses
                    if force_end or misses >= self.end_confirmation_checks:
                        await self._handle_ended_stream(db_id)
                        self._missed_checks.pop(db_id, None)
                    else:
                        display_name = self.config.get('name', self.platform_id)
                        await send_to_any_log(
                            "info",
                            f"[{self.platform_name}] Stream {db_id} ({display_name}) not found in check "
                            f"({misses}/{self.end_confirmation_checks}), awaiting confirmation before ending",
                            emoji=LogEmojis.INFO,
                            targets=["console", "file"],
                        )
                    
        except Exception as e:
            self.error_count += 1
            self.consecutive_errors += 1
            await send_to_any_log("error", f"[{self.platform_name}] Error checking {self.platform_id}: {e}", emoji=LogEmojis.ERROR)

            if self.consecutive_errors >= self.circuit_breaker_threshold:
                self.circuit_open = True
                await send_to_any_log(
                    "warning",
                    f"[{self.platform_name}] Circuit Breaker triggered for {self.platform_id} "
                    f"({self.consecutive_errors} consecutive errors). "
                    f"Pausing for {self.circuit_breaker_pause}s after releasing lock.",
                    emoji=LogEmojis.WARNING
                )

    async def _handle_new_stream(self, stream_data: Dict[str, Any]):
        """Logic when a new stream is detected."""
        stream_id = str(stream_data.get("stream_id"))
        title = stream_data.get("title", "Live Stream")
        display_name = self.config.get('name', self.platform_id)
        
        await send_to_any_log("info", f"[{self.platform_name}] New stream ({display_name}): {title} ({stream_id})", emoji=LogEmojis.SUCCESS)

        # 1. Create Discord Event
        event_id = None
        if self.create_discord_event:
            event_id = await EventManager.create_discord_event(None, stream_data, self.config)
            if event_id:
                await send_to_any_log("info", f"[{self.platform_name}] Created Discord event for {display_name} (Stream ID: {stream_id})", emoji=LogEmojis.SUCCESS)

        # 2. Save to DB and in-memory
        await self.save_stream_to_db(stream_id, event_id)
        self.active_streams_data[stream_id] = stream_data

        # 3. Channel notification
        if self.send_channel_notification and self.discord_channel_id:
            notification = await StreamNotificationHelper.build_stream_start_notification(
                stream_info=stream_data,
                config=self.config,
                context=f"{self.platform_name.lower()}_stream"
            )
            if notification:
                success = await self._send_notification(notification_data=notification)
                if success:
                    self.processed_count += 1
                    from modules_utils.stats_manager import stats_manager
                    stats_manager.log_stream(self.platform_name.lower())
                
                channel = self.discord_bot.bot.get_channel(self.discord_channel_id)
                channel_info = f"'{channel.name}'" if channel else str(self.discord_channel_id)
                await send_to_any_log("info", f"[{self.platform_name}] Sent stream start notification for {display_name} to channel {channel_info}", emoji=LogEmojis.SUCCESS)

        # 4. Telegram notification
        await StreamNotificationHelper.send_telegram_notification(
            stream_info=stream_data,
            config=self.config,
            notification_type="start",
            context=f"{self.platform_name.lower()}_stream"
        )

        # 5. Manage role via helper
        from modules_utils.live_role_helper import LiveRoleHelper
        await LiveRoleHelper.manage_role(self.discord_bot, self.config, self.platform_name, stream_id, assign=True)

    async def _handle_existing_stream(self, stream_id: str):
        """Logic for an already running stream (extend or recreate event)."""
        event_id = await self.get_event_id_from_db(stream_id)
        if event_id:
            new_event_id = await EventManager.extend_event_if_needed(stream_id, event_id)
            if new_event_id and new_event_id != event_id:
                await self.save_stream_to_db(stream_id, new_event_id)
        
        from modules_utils.live_role_helper import LiveRoleHelper
        await LiveRoleHelper.manage_role(self.discord_bot, self.config, self.platform_name, stream_id, assign=True)

    async def _handle_ended_stream(self, stream_id: str):
        """Logic when stream ends."""
        display_name = self.config.get('name', self.platform_id)
        await send_to_any_log("info", f"[{self.platform_name}] Stream ended: {display_name} ({stream_id})", emoji=LiveEmojis.STREAM_END)
        
        from modules_utils.live_role_helper import LiveRoleHelper
        await LiveRoleHelper.manage_role(self.discord_bot, self.config, self.platform_name, stream_id, assign=False)

        if self.send_channel_notification and self.discord_channel_id:
            stream_data = self.active_streams_data.get(stream_id, {"title": "Stream", "stream_id": stream_id})
            notification = await StreamNotificationHelper.build_stream_end_notification(
                stream_info=stream_data,
                config=self.config,
                context=f"{self.platform_name.lower()}_stream"
            )
            if notification:
                await self._send_notification(notification)
                channel = self.discord_bot.bot.get_channel(self.discord_channel_id)
                channel_info = f"'{channel.name}'" if channel else str(self.discord_channel_id)
                await send_to_any_log("info", f"[{self.platform_name}] Sent stream end notification for {display_name} to channel {channel_info}", emoji=LogEmojis.INFO)

        stream_data = self.active_streams_data.get(stream_id, {"title": "Stream", "stream_id": stream_id})
        await StreamNotificationHelper.send_telegram_notification(
            stream_info=stream_data,
            config=self.config,
            notification_type="end",
            context=f"{self.platform_name.lower()}_stream"
        )

        event_id = await self.get_event_id_from_db(stream_id)
        if event_id:
            await EventManager.cleanup_extension_data(stream_id=stream_id)
            await EventManager.delete_discord_event(None, event_id)
            await send_to_any_log("info", f"[{self.platform_name}] Deleted Discord event for {display_name} ({stream_id})", emoji=LogEmojis.INFO)

        await self.mark_stream_finished_in_db(stream_id)
        self.active_streams_data.pop(stream_id, None)

    async def _send_notification(self, notification_data: dict) -> bool:
        """Sends notification to Discord."""
        if not self.discord_channel_id:
            return False
        
        return await self.discord_bot.send_message_async(
            screen_name=f"{self.platform_name.lower()}_{self.platform_id}",
            message_data=[notification_data],
            override_channel_id=self.discord_channel_id,
            config=self.config
        )

    async def fetch_current_videos(self) -> List[Dict[str, Any]]:
        """Fetches current videos from platform. Overridden by subclasses."""
        return []

    async def _check_videos(self):
        """Logic for checking new videos."""
        try:
            current_videos = await self.fetch_current_videos()
            if not current_videos:
                return

            processed_ids = await self.get_all_processed_ids_from_db()
            display_name = self.config.get('name', self.platform_id)

            is_first_run = len(processed_ids) == 0
            if is_first_run:
                await send_to_any_log("info", f"[{self.platform_name} Video] First run for {display_name}. Populating DB with existing videos ({len(current_videos)} items) without sending notifications.", emoji=LogEmojis.INFO)

            for video in reversed(current_videos):
                video_id = video.get("video_id")
                if video_id and video_id not in processed_ids:
                    title = video.get("title", "")
                    description = video.get("description", "")
                    
                    if TextFilter.should_skip(title, self.config, context=f"{self.platform_name} Video:{display_name}", second_text=description):
                        continue

                    if is_first_run:
                        if self.db_helper:
                            await self.db_helper.save_video(video_id, self.platform_id)
                    else:
                        await self._handle_new_video(video)
        except Exception as e:
            await send_to_any_log("error", f"[{self.platform_name} Video] Error {self.platform_id}: {e}", emoji=LogEmojis.ERROR)

    async def _handle_new_video(self, video_data: Dict[str, Any]):
        """Handling a new video."""
        video_id = video_data["video_id"]
        await send_to_any_log("info", f"[{self.platform_name} Video] New video: {video_data['title']} ({video_id})", emoji=Emojis.VIDEO)
        
        if self.db_helper:
            await self.db_helper.save_video(video_id, self.platform_id)

        if self.send_channel_notification and self.discord_channel_id:
            notification = await StreamNotificationHelper.build_stream_start_notification(
                stream_info=video_data,
                config=self.config,
                context=f"{self.platform_name.lower()}_video"
            )
            if notification:
                success = await self._send_notification(notification)
                if success:
                    from modules_utils.stats_manager import stats_manager
                    stats_manager.log_video(self.platform_name.lower())

        await StreamNotificationHelper.send_telegram_notification(
            stream_info=video_data,
            config=self.config,
            notification_type="video",
            context=f"{self.platform_name.lower()}_video"
        )

    async def stop(self):
        """Останавливает мониторинг."""
        await super().stop()
