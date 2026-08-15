# vk_wall/monitor.py
import aiohttp
import asyncio
import traceback
import time
import random
from datetime import datetime
from typing import Dict, Any, Optional
from constants.emojis import LogEmojis
from log_system.logger_helper import send_to_any_log
from modules.vk_wall.database_wall import is_post_processed, mark_post_as_processed, get_processed_post, update_post_timestamp
from modules.vk_wall.content_processor.processor import ContentProcessor
from modules.vk_wall.hash_utils import get_attachments_hash
from clients.discord_client import DiscordBotManager
from modules_utils.vk_api_client import VKApiClient
from constants.base import VKAPI
from settings.config import Config
from modules_utils.base_monitor import BaseMonitor


class GroupMonitor(BaseMonitor):
    def __init__(self, platform_name: str, group_config: Dict[str, Any], discord_bot: DiscordBotManager):
        from modules_utils.helpers import clean_vk_token
        import os as _os
        # Создаем копию словаря, чтобы не мутировать исходный конфиг
        self.group_config = group_config.copy()
        if "vk_token" in self.group_config:
            raw_token = self.group_config["vk_token"]
            # Поддержка ссылок на переменные окружения: "env:VAR_NAME"
            if isinstance(raw_token, str) and raw_token.startswith("env:"):
                env_key = raw_token[4:].strip()
                raw_token = _os.environ.get(env_key, "")
                if not raw_token:
                    import logging
                    logging.warning(
                        f"[GroupMonitor] vk_token for group '{group_config.get('platform_id')}' "
                        f"references environment variable '{env_key}', but it is not set."
                    )
            self.group_config["vk_token"] = clean_vk_token(raw_token)

        super().__init__(
            platform_name=platform_name,
            platform_id=group_config.get("platform_id", ""),
            discord_bot=discord_bot,
        )

        self.is_first_run = True
        self.group_id = group_config.get("id") # Может быть уже в конфиге из кэша
        self.real_tracking_method = "polling"
        self.last_request_success = False
        self.last_used_token_type = "unknown"
        self.token_auth_error_count = 0
        self.last_error_msg: Optional[str] = None
        self._consecutive_errors: int = 0
        self._circuit_open_until: float = 0.0
        self._last_new_post_time: float = 0.0
        self._last_silence_alert_time: float = 0.0
        self._interval_multiplier: float = 1.0
        self._failed_posts: list[Any] = []
        self.processor = ContentProcessor(discord_bot.bot)

    async def start(self):
        """Запускает мониторинг группы. При неожиданном краше автоматически перезапускается."""
        import random

        # Разносим первый запуск во времени (jitter)
        await asyncio.sleep(random.uniform(0, 15))

        from modules_utils.http_client import HttpClient
        self.session = await HttpClient.get_session()
        await self.resolve_group_id()

        if not self.group_id:
            await send_to_any_log("error", f"Failed to get ID for group {self.group_config.get('platform_id')}", emoji=LogEmojis.ERROR)
            self.is_running = False
            return

        # Загружаем время последнего поста из БД во избежание ложных уведомлений о молчании
        try:
            from modules.vk_wall.database_wall import get_latest_post_timestamp
            latest_ts = await get_latest_post_timestamp(str(self.group_id))
            self._last_new_post_time = latest_ts if latest_ts else time.time()
        except Exception:
            self._last_new_post_time = time.time()

        tracking_method = self.group_config.get("tracking_method", "polling").strip().lower()

        # Если это профиль пользователя (group_id > 0), Bots Long Poll технически невозможен.
        if self.group_id and self.group_id > 0 and tracking_method == "bots_longpoll":
            await send_to_any_log("warning", f"[{self.group_config.get('name')}] Bots Long Poll mode is not available for user profile. Automatically switched to standard polling.", emoji=LogEmojis.WARNING)
            tracking_method = "polling"

        self.real_tracking_method = tracking_method
        name = self.group_config.get('name', self.group_config.get('platform_id'))

        restart_delay = 30  # начальная задержка перезапуска (сек)

        while True:  # внешний цикл самовосстановления
            self.is_running = True
            await send_to_any_log("info", f"[{name}] Starting monitoring in mode: {tracking_method}", emoji=LogEmojis.INFO)
            try:
                if tracking_method == "bots_longpoll":
                    await self._run_bots_longpoll()
                elif tracking_method == "user_longpoll":
                    await self._run_user_longpoll()
                else:
                    await self._run_standard_polling()
                # Нормальный выход (is_running=False снаружи) — прекращаем цикл
                break
            except asyncio.CancelledError:
                self.is_running = False
                return
            except Exception as e:
                self.error_count += 1
                tb = traceback.format_exc()
                await send_to_any_log("error",
                    f"[{name}] Monitor critical error: {str(e)[:200]}\n{tb[:600]}\n"
                    f"Restarting in {restart_delay}s...",
                    emoji=LogEmojis.ERROR)
            finally:
                self.is_running = False

            # Если is_running стал False снаружи (штатная остановка) — не перезапускаем
            if not self.is_running and self.error_count == 0:
                break

            await asyncio.sleep(restart_delay)
            restart_delay = min(restart_delay * 2, 600)  # экспоненциальный бэкофф, макс. 10 мин
            self.session = await HttpClient.get_session()  # обновляем сессию перед перезапуском

    async def _run_standard_polling(self):
        """Стандартный опрос через wall.get с адаптивным интервалом и circuit breaker."""
        from modules.vk_wall.polling_runners import run_standard_polling
        await run_standard_polling(self)

    async def _run_bots_longpoll(self):
        """Режим Bots Long Poll API (групповой токен)."""
        from modules.vk_wall.polling_runners import run_bots_longpoll
        await run_bots_longpoll(self)

    async def _run_user_longpoll(self):
        """Режим User Long Poll API с дублирующим фоновым периодическим опросом."""
        from modules.vk_wall.polling_runners import run_user_longpoll
        await run_user_longpoll(self)

    async def resolve_group_id(self):
        """Получает ID группы по platform_id"""
        if not self.platform_id:
            await send_to_any_log("error", f"Missing platform_id for group {self.group_config.get('name')}", emoji=LogEmojis.ERROR)
            return
        
        if self.group_id:
            return

        # Для разрешения ID группы предпочтительнее использовать глобальный пользовательский токен (избегаем ошибок прав групповых токенов)
        resolve_token = Config.VK_TOKEN or self.group_config.get("vk_token")
        group_id = await VKApiClient.get_group_id(self.platform_id, token=resolve_token)
        if group_id:
            self.group_id = group_id
            group_name = self.group_config.get('name', self.platform_id)
            await send_to_any_log("info", f"Group '{group_name}' ({self.platform_id}) → ID: {group_id}", emoji=LogEmojis.INFO)
        else:
            await send_to_any_log("error", f"Failed to get ID for group {self.platform_id}", emoji=LogEmojis.ERROR)

    async def check_group(self):
        """Проверяет новые посты в группе"""
        self.last_check_time = datetime.now()
        if not self.group_id:
            return

        # Проверка на молчание группы (silence check)
        if self._last_new_post_time > 0.0:
            silence_duration = time.time() - self._last_new_post_time
            max_silence_seconds = Config.VK_MAX_SILENCE_DAYS * 24 * 3600
            if silence_duration > max_silence_seconds:
                if time.time() - self._last_silence_alert_time > 24 * 3600:
                    self._last_silence_alert_time = time.time()
                    silence_days = silence_duration / (24 * 3600)
                    msg = (
                        f"{LogEmojis.WARNING} **Warning for group '{self.group_config['name']}' ({self.platform_id})**:\n"
                        f"No new posts for **{silence_days:.1f}** days (threshold: {Config.VK_MAX_SILENCE_DAYS} days).\n"
                        f"Please ensure the VK monitor token is working properly."
                    )
                    await send_to_any_log("warning", msg, emoji=LogEmojis.WARNING)
            
        await send_to_any_log("info", f"[{self.group_config['name']}] Checking for new posts...", emoji=LogEmojis.INFO, targets=["console", "file"])
        
        if self.is_first_run:
            count = self.group_config.get('initial_post_count', 5)
            await send_to_any_log("info", f"First run for {self.group_config['name']}, checking {count} posts", emoji=LogEmojis.INFO)
        else:
            count = self.group_config.get('posts_per_check', 1)
            
        # Сбрасываем флаг перед вызовом
        self.last_request_success = False
        self.last_used_token_type = "unknown"
        
        posts = await self.get_vk_posts_async(count)
        
        # Обновляем время успеха, если запрос прошел успешно (даже если вернулось 0 постов)
        if self.last_request_success:
            self.last_success_time = datetime.now()
            
            # Если это первая успешная проверка в текущей сессии, выводим расширенную информацию о подключении
            if self.is_first_run:
                from modules_utils.helpers import get_vk_token_description
                local_tok = self.group_config.get("vk_token")
                if local_tok:
                    has_local = f"Yes, {get_vk_token_description(local_tok)}"
                else:
                    has_local = f"No, using shared token: {get_vk_token_description(Config.VK_TOKEN)}"
                
                real_method = self.real_tracking_method or self.group_config.get("tracking_method", "polling")
                # Для bots_longpoll групп с локальным токеном основной механизм работает на локальном токене
                local_token = self.group_config.get("vk_token")
                if local_token and real_method == "bots_longpoll":
                    effective_token = f"LOCAL group token ({get_vk_token_description(local_token)})"
                else:
                    tok_to_desc = local_token if local_token else Config.VK_TOKEN
                    effective_token = f"{self.last_used_token_type.upper()} ({get_vk_token_description(tok_to_desc)})"

                log_message = (
                    f"[{self.group_config['name']}] First check completed successfully!\n"
                    f"• Real monitoring mode: {real_method.upper()}\n"
                    f"• Local token in group config: {has_local}\n"
                    f"• Token used during posts check: {effective_token}"
                )
                await send_to_any_log("info", log_message, emoji=LogEmojis.SUCCESS)

        if not posts:
            await send_to_any_log("info", f"No posts received for group {self.group_config['name']}", emoji=LogEmojis.INFO)
            await self.retry_failed_posts()
            return
        await send_to_any_log("info", f"Received posts for {self.group_config['name']}: {len(posts)}", emoji=LogEmojis.INFO)
        for post in reversed(posts):
            await self.process_post(post)
            await asyncio.sleep(1)
        await self.retry_failed_posts()

    async def get_vk_posts_async(self, count: int = 1) -> list[Dict[str, Any]]:
        """Асинхронное получение постов из VK с использованием HttpClient"""
        if not self.group_id:
            self.last_request_success = False
            return []
        
        # Определяем, какой токен используется
        local_token = self.group_config.get("vk_token")
        fallback_to_global = False
        
        if local_token:
            token = local_token
            self.last_used_token_type = "local (from group config)"
            fallback_to_global = bool(Config.VK_TOKEN)
        elif Config.VK_TOKEN:
            token = Config.VK_TOKEN
            self.last_used_token_type = "shared (global)"
        else:
            token = None
            self.last_used_token_type = "not set"

        from modules_utils.helpers import get_vk_token_description
        desc = get_vk_token_description(token)
        await send_to_any_log("info", f"[{self.group_config['name']}] Wall check: {self.last_used_token_type} ({desc})", emoji=LogEmojis.INFO, targets=["console", "file"])

        from modules_utils.http_client import HttpClient
        url = f"{VKAPI.BASE_URL}/{VKAPI.METHODS['WALL_GET']}"
        params = {
            "owner_id": self.group_id,
            "count": count,
            "filter": VKAPI.FILTER_OWNER,
            "access_token": token,
            "v": VKAPI.VERSION
        }
        
        try:
            data = await HttpClient.get(url, params=params, timeout=VKAPI.TIMEOUT)
            if data and isinstance(data, dict):
                if "error" in data:
                    error_code = data["error"].get("error_code", 0)
                    error_msg = data["error"].get("error_msg", "Unknown error")
                    
                    # Проверяем, вызвана ли ошибка использованием группового токена для wall.get
                    is_group_auth_error = (
                        error_code in [15, 28] or
                        "group auth" in error_msg.lower() or
                        "unavailable with group auth" in error_msg.lower()
                    )
                    
                    if is_group_auth_error and fallback_to_global:
                        await send_to_any_log(
                            "warning", 
                            f"[{self.group_config['name']}] Local token is a group token and wall.get is unavailable with it. "
                            f"Automatically falling back to shared user token...", 
                            emoji=LogEmojis.WARNING
                        )
                        params["access_token"] = Config.VK_TOKEN
                        self.last_used_token_type = "shared (global) [fallback]"
                        
                        data = await HttpClient.get(url, params=params, timeout=VKAPI.TIMEOUT)
                        if data and isinstance(data, dict):
                            if "error" not in data:
                                self.last_request_success = True
                                if "response" in data and data["response"]["count"] > 0:
                                    return data["response"]["items"]
                                return []
                            else:
                                error_code = data["error"].get("error_code", 0)
                                error_msg = data["error"].get("error_msg", "Unknown error")
                    
                    if error_code in [5, 15, 27, 28]:
                        self.token_auth_error_count += 1
                    self.last_error_msg = f"[{error_code}] {error_msg}"
                    await send_to_any_log("error", f"VK API Error in {self.group_config['name']}: {error_msg}", emoji=LogEmojis.ERROR)
                    self.last_request_success = False
                    return []
                self.last_request_success = True
                if "response" in data and data["response"]["count"] > 0:
                    return data["response"]["items"]
            else:
                self.last_request_success = False
            return []
        except Exception as e:
            self.last_error_msg = str(e)[:200]
            self.last_request_success = False
            await send_to_any_log("error", f"VK Request Error in {self.group_config['name']}: {str(e)[:200]}", emoji=LogEmojis.ERROR)
            return []
            
    async def process_post(self, post: Dict[str, Any]):
        """Обрабатывает отдельный пост"""
        if not self.group_id:
            return
        post_id = post["id"]
        group_id_str = str(self.group_id)
        group_name = self.group_config.get("name", "Unnamed")

        # Check if post has already been processed
        if await is_post_processed(post_id, group_id_str):
            # Update timestamp so post is not cleaned up as old if it is pinned or top
            await update_post_timestamp(post_id, group_id_str)

            if not Config.SILENT_DUPLICATES:
                await send_to_any_log("info", f"Post {post_id} (Group: {group_name}) already processed — skipping", emoji=LogEmojis.INFO)

            # Check for post edits
            trigger_words = self.group_config.get("edit_trigger_words", [])
            if Config.CHECK_POST_EDITS or trigger_words:
                saved_post = await get_processed_post(post_id, group_id_str)
                if saved_post:
                    from modules.vk_wall.hash_utils import get_attachments_hash, normalize_text, get_added_text
                    current_text = normalize_text(post.get("text", ""))
                    current_attachments_hash = get_attachments_hash(post.get("attachments", []))
                    
                    old_text = normalize_text(saved_post.get("text") or "")
                    old_hash = saved_post.get("attachments_hash") or ""
                    
                    text_changed = current_text != old_text
                    attachments_changed = current_attachments_hash != old_hash

                    if text_changed or attachments_changed:
                        added_text = get_added_text(old_text, current_text) if text_changed else ""

                        if trigger_words:
                            added_lower = added_text.lower()
                            matched = any(word.lower() in added_lower for word in trigger_words)
                            if not matched:
                                await send_to_any_log("info", f"Post {post_id} (Group: {group_name}) modified, but trigger words not found — skipping notification", emoji=LogEmojis.INFO)
                                await mark_post_as_processed(post_id, group_id_str, current_text, post.get("attachments", []), group_name=group_name)
                                return

                        edit_message = await self.processor.build_edit_notification(
                            post, self.group_config, text_changed, attachments_changed, added_text=added_text
                        )
                        
                        if edit_message:
                            await send_to_any_log("info", f"Post {post_id} (Group: {group_name}) was edited. Text: {text_changed}, Attachments: {attachments_changed}", emoji=LogEmojis.INFO)
                            success = await self.discord_bot.send_message_async(
                                screen_name=self.group_config.get('platform_id'),
                                message_data=[edit_message],
                                config=self.group_config
                            )
                            if success:
                                await mark_post_as_processed(post_id, group_id_str, current_text, post.get("attachments", []), group_name=group_name)
                        else:
                            await mark_post_as_processed(post_id, group_id_str, current_text, post.get("attachments", []), group_name=group_name)
            return

        # Check filters before sending
        if not self.processor.passes_all_filters(post, self.group_config):
            await mark_post_as_processed(post_id, group_id_str, 
                                       text=post.get("text", ""), 
                                       attachments=post.get("attachments", []),
                                       group_name=group_name)
            await send_to_any_log("info", f"Post {post_id} (Group: {group_name}) skipped by filters and marked as processed", emoji=LogEmojis.INFO)
            return

        # Send new post
        start_send_time = time.time()
        success = await self.send_post_to_discord(post)
        if success:
            self.processed_count += 1
            self._last_new_post_time = time.time()
            from modules_utils.stats_manager import stats_manager
            stats_manager.log_post("vk_wall")
            stats_manager.log_processing_time(time.time() - start_send_time)
            
            await mark_post_as_processed(post_id, group_id_str, 
                                       text=post.get("text", ""),
                                       attachments=post.get("attachments", []),
                                       group_name=group_name)
            
            group_info = f"'{group_name}' ({group_id_str})"
            await send_to_any_log("info", f"New post {post_id} (Group: {group_info}) sent to Discord", emoji=LogEmojis.SUCCESS)
        elif success is None:
            await send_to_any_log("info", f"Post {post_id} from group '{group_name}' deferred (live stream active) — will publish later", emoji=LogEmojis.INFO)
            if not any(fp[0]["id"] == post_id for fp in self._failed_posts):
                self._failed_posts.append((post, 1, time.time(), True))
        else:
            await send_to_any_log("warning", f"Failed to send post {post_id} from group '{group_name}' — added to retry queue", emoji=LogEmojis.WARNING)
            if not any(fp[0]["id"] == post_id for fp in self._failed_posts):
                self._failed_posts.append((post, 1, time.time(), False))

    async def send_post_to_discord(self, post: Dict[str, Any]) -> Optional[bool]:
        """Отправляет пост в Discord.

        Возвращает True при успехе, False при настоящей ошибке отправки,
        None — если пост намеренно отложен (например, skip_live_posts=true и на
        стене сейчас активен стрим); это не ошибка и не должно тратить попытки
        ретрая.
        """
        try:
            message = await self.processor.build_discord_message(post, self.group_config)
            if message is ContentProcessor.SKIP_LIVE_POST:
                return None
            if not message:
                return False
            screen_name = self.group_config.get('platform_id')
            
            # Применяем keyword-роутинг постов, если настроено в JSON группы
            target_config = self.group_config.copy()
            keyword_routing = target_config.get("keyword_routing")
            if keyword_routing and isinstance(keyword_routing, dict):
                text = post.get("text", "") or ""
                # Если это репост, проверим также текст из истории репостов
                if "copy_history" in post and isinstance(post["copy_history"], list) and post["copy_history"]:
                    for repost in post["copy_history"]:
                        if isinstance(repost, dict) and repost.get("text"):
                            text += " " + repost["text"]
                
                text_lower = text.lower()
                for keyword, target_channel_id in keyword_routing.items():
                    if keyword.lower() in text_lower:
                        await send_to_any_log("info", f"[Routing] Post {post['id']} («{self.group_config.get('name', 'VKSource')}») contains '{keyword}' -> routing to channel {target_channel_id}", emoji=LogEmojis.INFO)
                        target_config["discord_channel_id"] = str(target_channel_id)
                        # Reset thread_id so the post goes to the new channel instead of original thread
                        if "thread_id" in target_config:
                            target_config.pop("thread_id", None)
                        break

            config = {**target_config, "dedup_key": f"{self.group_id}:{post['id']}"}
            return await self.discord_bot.send_message_async(
                screen_name=screen_name,
                message_data=message,
                config=config
            )
        except Exception as e:
            await send_to_any_log("error", f"Error sending post to Discord: {e}", emoji=LogEmojis.ERROR)
            return False

    async def retry_failed_posts(self):
        """Attempts to resend posts that previously failed to send."""
        if not self._failed_posts:
            return

        still_failed = []
        for entry in self._failed_posts:
            if len(entry) == 4:
                post, attempts, last_time, is_deferred = entry
            else:
                post, attempts, last_time = entry
                is_deferred = False

            post_id = post["id"]
            group_name = self.group_config.get("name", "Unnamed")
            
            # Wait 30 seconds * 2^(attempts-1) (exponential backoff)
            wait_time = min(30 * (2 ** (attempts - 1)), 600)
            if time.time() - last_time < wait_time:
                still_failed.append((post, attempts, last_time, is_deferred))
                continue

            if is_deferred:
                await send_to_any_log("info", f"[{group_name}] Checking if stream finished to publish deferred post {post_id}...", emoji=LogEmojis.INFO)
            else:
                await send_to_any_log("info", f"[{group_name}] Retrying sending post {post_id} to Discord (attempt {attempts})...", emoji=LogEmojis.INFO)
            
            start_send_time = time.time()
            success = await self.send_post_to_discord(post)
            if success:
                self.processed_count += 1
                self._last_new_post_time = time.time()
                from modules_utils.stats_manager import stats_manager
                stats_manager.log_post("vk_wall")
                stats_manager.log_processing_time(time.time() - start_send_time)
                
                await mark_post_as_processed(
                    post_id, str(self.group_id), 
                    text=post.get("text", ""),
                    attachments=post.get("attachments", []),
                    group_name=group_name
                )
                await send_to_any_log("info", f"Post {post_id} (Group: {group_name}) successfully sent after retry!", emoji=LogEmojis.SUCCESS)
            elif success is None:
                still_failed.append((post, attempts, time.time(), True))
            else:
                if not is_deferred and attempts >= 5:
                    await send_to_any_log("error", f"[{group_name}] Post {post_id} failed after {attempts} attempts. Removed from retry queue to prevent infinite loop.", emoji=LogEmojis.ERROR)
                else:
                    await send_to_any_log("warning", f"[{group_name}] Failed to resend post {post_id}. Attempt {attempts}/5.", emoji=LogEmojis.WARNING)
                    still_failed.append((post, attempts + 1, time.time(), False))
                    
        self._failed_posts = still_failed

    async def stop(self):
        """Останавливает мониторинг группы"""
        self.is_running = False

    def get_status(self) -> Dict[str, Any]:
        """Возвращает статус монитора"""
        return {
            'running': self.is_running,
            'first_run': self.is_first_run,
            'processed_count': self.processed_count,
            'error_count': self.error_count,
            'last_check': self.last_check_time,
            'last_success': self.last_success_time,
            'group_id': self.group_id,
            'group_name': self.group_config.get('name'),
            'platform_id': self.platform_id,
            'last_error_msg': self.last_error_msg,
            'consecutive_errors': self._consecutive_errors,
            'circuit_open': (self._circuit_open_until > time.time()) if self._circuit_open_until else False,
            'interval_multiplier': self._interval_multiplier,
        }
