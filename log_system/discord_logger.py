import aiohttp
import asyncio
import json
import time
from typing import Dict, Any, Optional
from settings.config import Config
from constants.emojis import LogEmojis, StartupEmojis, Emojis
from constants.strings import BotStrings
from modules_utils.helpers import get_full_local_time, get_human_timezone, bool_to_yes_no, get_vk_token_description

class DiscordLogger:
    _lock: Optional[asyncio.Lock] = None
    _last_request_time = 0
    _rate_limit_delay = 1.0

    @staticmethod
    def _get_lock() -> asyncio.Lock:
        try:
            loop = asyncio.get_running_loop()
            if DiscordLogger._lock is None or getattr(DiscordLogger._lock, '_loop', loop) is not loop:
                DiscordLogger._lock = asyncio.Lock()
        except RuntimeError:
            DiscordLogger._lock = asyncio.Lock()
        return DiscordLogger._lock

    @staticmethod
    async def send_to_channel(
        content: str = "",
        channel_id: Optional[str] = None
    ) -> bool:
        final_channel_id = str(channel_id or Config.GLOBAL_LOG_CHANNEL_ID)
        if not final_channel_id or not Config.DISCORD_BOT_TOKEN:
            return False

        async with DiscordLogger._get_lock():
            current_time = time.time()
            elapsed = current_time - DiscordLogger._last_request_time
            if elapsed < DiscordLogger._rate_limit_delay:
                await asyncio.sleep(DiscordLogger._rate_limit_delay - elapsed)
            DiscordLogger._last_request_time = time.time()

        url = f"https://discord.com/api/v10/channels/{final_channel_id}/messages"
        headers = {
            "Authorization": f"Bot {Config.DISCORD_BOT_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://github.com/Rapptz/discord.py, 2.3.2) aiohttp"
        }
        payload = {"content": content}

        try:
            from modules_utils.http_client import HttpClient
            session = await HttpClient.get_session()
            async with session.post(url, data=json.dumps(payload), headers=headers, timeout=15) as response:
                if response.status not in (200, 201, 204):
                    from log_system.logger_helper import send_to_any_log
                    resp_text = await response.text()
                    await send_to_any_log("error", f"Discord API error: {response.status} - {resp_text}", targets=["console", "file"])
                    return False
                return True
        except Exception as e:
            from log_system.logger_helper import send_to_any_log
            await send_to_any_log("error", f"Exception in send_to_channel: {e}", targets=["console", "file"])
            return False

    @staticmethod
    async def send_heartbeat(uptime_str: str) -> bool:
        """Отправляет периодическое уведомление о работе бота."""
        content = f"{StartupEmojis.SYSTEM} **{BotStrings.HEARTBEAT_STATUS_WORK}**\n{BotStrings.STARTUP_UPTIME.format(uptime=uptime_str)}"
        return await DiscordLogger.send_to_channel(content=content)

    @staticmethod
    def get_role_display(role_id: Optional[int]) -> str:
        """Возвращает отображаемое имя роли без @"""
        if not role_id:
            return BotStrings.ROLE_NOT_SET
        
        try:
            from clients.bot_instance import bot
            guild = bot.get_guild(Config.SERVER_ID)
            if guild:
                role = guild.get_role(role_id)
                if role:
                    return f"**{role.name}**"
        except Exception:
            pass
        
        return f"**{BotStrings.ROLE_DISPLAY_TEMPLATE.format(role_id=role_id)}**"

    @staticmethod
    async def send_startup_notification(startup_data: Dict[str, Any]) -> bool:
        """
        Отправляет уведомление о старте бота.
        Отправляется ВСЕГДА, независимо от настроек логирования.
        """
        from log_system.logger_helper import send_to_any_log
        
        await send_to_any_log("debug", "Starting startup notification dispatch to Discord", emoji=LogEmojis.DEBUG)
        
        if not Config.GLOBAL_LOG_CHANNEL_ID:
            await send_to_any_log("info", "Startup notification: GLOBAL_LOG_CHANNEL_ID not set", emoji=LogEmojis.INFO)
            return False
        if not Config.DISCORD_BOT_TOKEN:
            await send_to_any_log("info", "Startup notification: DISCORD_BOT_TOKEN not set", emoji=LogEmojis.INFO)
            return False
            
        await send_to_any_log("debug", "Checks passed, preparing message...", emoji=LogEmojis.DEBUG)
        
        try:
            role_id = Config.ALERT_ROLE_ID
            role_display = DiscordLogger.get_role_display(role_id)
            
            def status_emoji(key: str) -> str:
                return Emojis.SUCCESS if startup_data['modules_status'].get(key, False) else Emojis.FAILURE
            
            content_lines = [
                f"{StartupEmojis.BOT} **{BotStrings.STARTUP_TITLE}** _({BotStrings.BOT_VERSION_FULL})_",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"{Emojis.CALENDAR} **{BotStrings.STARTUP_TIME_LABEL}:** {get_full_local_time()} ({get_human_timezone(startup_data.get('timezone_region', 'Europe/Moscow'))})",
                ""
            ]
            
            if startup_data.get('stop_reason'):
                content_lines.append(f"{StartupEmojis.WARNING} **{BotStrings.STARTUP_PREVIOUS_STOP}:** `{startup_data['stop_reason']}`")
                content_lines.append("")

            # Тип проверки Twitch
            twitch_enabled = startup_data.get('modules_status', {}).get('twitch_live', False)
            twitch_check_type = startup_data.get('twitch_check_type', '')
            twitch_tracking_info = f" _(тип: `{twitch_check_type}`)_" if (twitch_enabled and twitch_check_type) else ""

            # Мониторинг Стримов
            content_lines.extend([
                f"### {StartupEmojis.STREAMERS} {BotStrings.STARTUP_MONITORING_STREAMS}",
                f"*   {status_emoji('live')} **{BotStrings.STARTUP_STREAM_VK_LIVE}:** `{startup_data.get('vk_live_count', 0)}` ст.",
                f"*   {status_emoji('youtube')} **{BotStrings.STARTUP_STREAM_YOUTUBE}:** `{startup_data.get('youtube_live_count', 0)}` трансляций",
                f"*   {status_emoji('rutube')} **{BotStrings.STARTUP_STREAM_RUTUBE}:** `{startup_data.get('rutube_live_count', 0)}` трансляций",
                f"*   {status_emoji('twitch_live')} **{BotStrings.STARTUP_STREAM_TWITCH}:** `{startup_data.get('twitch_count', 0)}` каналов{twitch_tracking_info}",
                f"*   {status_emoji('kick_live')} **{BotStrings.STARTUP_STREAM_KICK}:** `{startup_data.get('kick_count', 0)}` каналов",
                f"*   {status_emoji('trovo_live')} **{BotStrings.STARTUP_STREAM_TROVO}:** `{startup_data.get('trovo_count', 0)}` каналов",
                f"*   {status_emoji('vk_com_live')} **{BotStrings.STARTUP_STREAM_VK_COM}:** `{startup_data.get('vk_com_count', 0)}` каналов",
                f"*   {status_emoji('goodgame_live')} **{BotStrings.STARTUP_STREAM_GOODGAME}:** `{startup_data.get('goodgame_count', 0)}` каналов",
                ""
            ])

            # Разбивка YouTube-каналов по способу отслеживания (Videos API по токену / чистый RSS)
            youtube_api_count = startup_data.get('youtube_api_count', 0)
            youtube_rss_count = startup_data.get('youtube_rss_count', 0)
            youtube_tracking_info = f" _(токен: `{youtube_api_count}`, RSS: `{youtube_rss_count}`)_" if (youtube_api_count or youtube_rss_count) else ""

            # Мониторинг Контента
            content_lines.extend([
                f"### {StartupEmojis.POSTS} {BotStrings.STARTUP_MONITORING_CONTENT}",
                f"*   {status_emoji('posts')} **{BotStrings.STARTUP_CONTENT_VK_WALL}:** `{startup_data.get('vk_wall_count', 0)}` задействовано",
                f"*   {status_emoji('youtube')} **{BotStrings.STARTUP_CONTENT_YOUTUBE}:** `{startup_data.get('youtube_video_count', 0)}` каналов{youtube_tracking_info}",
                f"*   {status_emoji('rutube')} **{BotStrings.STARTUP_CONTENT_RUTUBE}:** `{startup_data.get('rutube_video_count', 0)}` каналов",
                f"*   {status_emoji('telegram')} **{BotStrings.STARTUP_CONTENT_TELEGRAM}:** {status_emoji('telegram')}",
                f"*   {status_emoji('pdf_monitor')} **{BotStrings.STARTUP_CONTENT_PDF}:** `{startup_data.get('pdf_count', 0)}` расписаний",
                f"*   {status_emoji('vk_assets')} **{BotStrings.STARTUP_CONTENT_VK_ASSETS}:** `{startup_data.get('vk_assets_count', 0)}` ресурсов",
                ""
            ])

            # Системы и Управление
            from clients.bot_instance import bot
            trap_channel_id = getattr(Config, 'AUTO_BAN_CHANNEL_ID', None)
            trap_role_id = getattr(Config, 'AUTO_BAN_ROLE_ID', None)
            trap_info = ""
            if trap_channel_id and trap_role_id:
                trap_channel = bot.get_channel(trap_channel_id)
                trap_channel_name = f"#{trap_channel.name}" if trap_channel else f"ID {trap_channel_id}"
                
                trap_role_name = f"ID {trap_role_id}"
                server_id = getattr(Config, 'SERVER_ID', None)
                if server_id:
                    guild = bot.get_guild(server_id)
                    if guild:
                        role = guild.get_role(trap_role_id)
                        if role:
                            trap_role_name = role.name
                else:
                    for guild in bot.guilds:
                        role = guild.get_role(trap_role_id)
                        if role:
                            trap_role_name = role.name
                            break
                trap_info = f"\n    *   {StartupEmojis.TRAP} **{BotStrings.STARTUP_TRAP_INFO}:** `{trap_channel_name}` -> роль **{trap_role_name}**"

            dep_immediate = BotStrings.STARTUP_DEP_IMMEDIATE if getattr(Config, 'ROLE_DEPENDENCY_IMMEDIATE_CHECK', True) else BotStrings.STARTUP_DEP_TIMER
            content_lines.extend([
                f"### {StartupEmojis.TOOLS} {BotStrings.STARTUP_SYSTEMS_CONTROL}",
                f"*   {status_emoji('stats_server')} **{BotStrings.STARTUP_SYSTEM_STATS_SERVER}:** {status_emoji('stats_server')}",
                f"*   {status_emoji('trello')} **{BotStrings.STARTUP_SYSTEM_TRELLO}:** `{startup_data.get('trello_count', 0)}` досок",
                f"*   {status_emoji('channel_protection')} **{BotStrings.STARTUP_SYSTEM_PROTECTION}:** `{startup_data.get('protected_count', 0)}` каналов" + trap_info,
                f"*   {status_emoji('role_dependency')} **{BotStrings.STARTUP_SYSTEM_ROLE_DEP}:** `{startup_data.get('role_dependency_count', 0)}` связей ({dep_immediate})",
                f"*   {status_emoji('user_activity')} **{BotStrings.STARTUP_SYSTEM_USER_ACT}:** {status_emoji('user_activity')}",
                f"*   {status_emoji('game_tracker')} **{BotStrings.STARTUP_SYSTEM_GAME_TRACKER}:** {status_emoji('game_tracker')}",
                f"*   {status_emoji('voice_region')} **{BotStrings.STARTUP_SYSTEM_VOICE_REGIONS}:** {status_emoji('voice_region')}",
                f"*   {status_emoji('secret_vendors')} **{BotStrings.STARTUP_SYSTEM_SECRET_VENDORS}:** {status_emoji('secret_vendors')}",
                f"*   {status_emoji('game_schedule')} **{BotStrings.STARTUP_SYSTEM_GAME_SCHEDULE}:** {status_emoji('game_schedule')}",
                f"*   {status_emoji('image_forwarder')} **{BotStrings.STARTUP_SYSTEM_IMAGE_FORWARDER}:** {status_emoji('image_forwarder')}",
                ""
            ])

            # Настройки
            logger_status = BotStrings.LOGGER_STATUS_DISABLED if startup_data.get('disable_logger', False) else BotStrings.LOGGER_STATUS_ENABLED
            adaptive_polling_status = BotStrings.ADAPTIVE_POLLING_ENABLED if Config.VK_ADAPTIVE_POLLING_ENABLED else BotStrings.ADAPTIVE_POLLING_DISABLED
            
            auto_restart_enabled = startup_data.get('use_auto_restart', Config.USE_AUTO_RESTART)
            auto_restart_interval = startup_data.get('auto_restart_interval', Config.AUTO_RESTART_INTERVAL_MINUTES)
            if auto_restart_enabled:
                if auto_restart_interval and auto_restart_interval > 0:
                    restart_info = f"`{BotStrings.STATUS_ENABLED}` _(интервал: `{auto_restart_interval} мин`)_"
                else:
                    restart_info = f"`{BotStrings.STATUS_ENABLED}` _(интервал: `{BotStrings.INTERVAL_DISABLED}`)_"
            else:
                restart_info = f"`{BotStrings.STATUS_DISABLED}`"

            content_lines.extend([
                f"### {StartupEmojis.SETTINGS} {BotStrings.STARTUP_CONFIGURATION}",
                f"*   **{BotStrings.STARTUP_SETTING_ERRORS}:** {role_display}",
                f"*   **{BotStrings.STARTUP_SETTING_NOTIF_ROLE}:** {DiscordLogger.get_role_display(Config.DEFAULT_LIVE_ROLE_ID)}",
                f"*   **{BotStrings.STARTUP_SETTING_PING_ROLE}:** {DiscordLogger.get_role_display(Config.DEFAULT_LIVE_PING_ROLE_ID)}",
                f"*   **{BotStrings.STARTUP_SETTING_VK_TOKEN}:** `{get_vk_token_description(Config.VK_TOKEN)}`",
                f"*   **{BotStrings.STARTUP_SETTING_LOGGER}:** `{logger_status}`",
                f"*   **{BotStrings.STARTUP_SETTING_ADAPTIVE}:** `{adaptive_polling_status}`",
                f"*   **{BotStrings.STARTUP_SETTING_RESTART}:** {restart_info}",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"{StartupEmojis.SPARKLES} *{BotStrings.STARTUP_FOOTER}*"
            ])
            
            content = "\n".join(content_lines)
            
            await send_to_any_log("debug", BotStrings.LOG_MESSAGE_PREPARED_SENDING, emoji=LogEmojis.DEBUG)
            
            success = await DiscordLogger.send_to_channel(content=content)
            
            if success:
                from clients.bot_instance import bot
                channel = bot.get_channel(int(Config.GLOBAL_LOG_CHANNEL_ID)) if Config.GLOBAL_LOG_CHANNEL_ID else None
                channel_info = f"'{channel.name}'" if channel else str(Config.GLOBAL_LOG_CHANNEL_ID)
                await send_to_any_log("info", BotStrings.LOG_STARTUP_NOTIFICATION_SUCCESS.format(channel_info=channel_info), emoji=LogEmojis.STARTUP)
            else:
                await send_to_any_log("error", BotStrings.LOG_STARTUP_NOTIFICATION_FAIL, emoji=LogEmojis.ERROR, targets=["console", "file"])
            return success
            
        except Exception as e:
            await send_to_any_log("error", f"Error sending startup notification: {e}", emoji=LogEmojis.ERROR, targets=["console", "file"])
            return False

    @staticmethod
    async def send_restore_alert(error_msg: str, mention: bool = True, traceback_str: Optional[str] = None) -> bool:
        """
        Отправляет уведомление о критической ошибке.
        Отправляется ВСЕГДА, независимо от настроек логирования.
        """
        if not Config.ALERT_ROLE_ID:
            return False
        if not Config.GLOBAL_LOG_CHANNEL_ID:
            return False
        if not Config.DISCORD_BOT_TOKEN:
            return False
            
        mention_str = f"<@&{Config.ALERT_ROLE_ID}> " if mention else ""
        content_lines = [
            f"{mention_str}{LogEmojis.WARNING} **{BotStrings.ERROR_ALERT_OCCURRED}**",
            "",
            f"**{StartupEmojis.ERROR_ALERT} {BotStrings.ERROR_ALERT_TITLE}**",
            f"{error_msg}",
            ""
        ]
        if traceback_str:
            content_lines.extend([
                f"**{BotStrings.ERROR_ALERT_TRACEBACK}**",
                f"{traceback_str}",
                ""
            ])
        content_lines.extend([
            f"**{BotStrings.ERROR_ALERT_TIME}**",
            f"{get_full_local_time()}"
        ])
        content = "\n".join(content_lines)
        success = await DiscordLogger.send_to_channel(content=content)
        if success:
            from log_system.logger_helper import send_to_any_log, send_log_to_mentions_file
            log_msg = BotStrings.LOG_RESTORE_ALERT_SUCCESS
            if mention:
                log_msg += f" (роль <@&{Config.ALERT_ROLE_ID}> упомянута)"
                send_log_to_mentions_file(
                    f"[discord_logger] send_restore_alert | упоминание роли: <@&{Config.ALERT_ROLE_ID}> | {error_msg[:200]}"
                )
            await send_to_any_log("warning", log_msg, emoji=LogEmojis.RESTORE_ALERT, targets=["console", "file"])
        else:
            from log_system.logger_helper import send_to_any_log
            await send_to_any_log("error", BotStrings.LOG_RESTORE_ALERT_FAIL, emoji=LogEmojis.ERROR, targets=["console", "file"])
        return success
