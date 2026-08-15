# modules_utils/base_monitor_manager.py
import os
import json
import asyncio
import aiofiles
from typing import List, Dict, Any, Type, Optional
from modules_utils.config_watcher import ConfigWatcher
try:
    from log_system.logger_helper import send_to_any_log
except ModuleNotFoundError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from modules_utils.files import get_config_path
from modules_utils.task_scheduler import scheduler

class BaseMonitorManager:
    """Базовый менеджер для управления любыми типами мониторов (посты, стримы и т.д.)."""
    
    def __init__(
        self, 
        platform_name: str, 
        monitor_class: Type, 
        discord_bot, 
        config_dir_name: str, 
        enable_flag: bool,
        db_init_func=None,
        db_cleanup_func=None,
        extra_init_args: Optional[Dict[str, Any]] = None
    ):
        self.platform_name = platform_name
        self.monitor_class = monitor_class
        self.discord_bot = discord_bot
        self.config_dir_name = config_dir_name
        self.enable_flag = enable_flag
        self.db_init_func = db_init_func
        self.db_cleanup_func = db_cleanup_func
        self.extra_init_args = extra_init_args or {}
        
        self.monitors: Dict[str, Any] = {}
        self.config_watcher = ConfigWatcher()
        self.is_running = False
        self._cleanup_task: Optional[asyncio.Task] = None

    @staticmethod
    def _validate_config_schema(data: dict, filename: str) -> List[str]:
        """Minimal config schema validation during load.
        Returns a list of warnings (empty list = ok)."""
        errors: List[str] = []

        # platform_id must be a non-empty string or integer
        pid = data.get("platform_id")
        if pid is not None and not isinstance(pid, (str, int)):
            errors.append(f"platform_id must be a string or number, got: {type(pid).__name__}")

        # check_interval — numeric only
        if "check_interval" in data:
            ci = data["check_interval"]
            if not isinstance(ci, (int, float)):
                errors.append(f"check_interval must be a number, got: {type(ci).__name__} ({ci!r})")
            elif ci <= 0:
                errors.append(f"check_interval must be > 0, got: {ci}")

        # discord_channel_id — positive int or digit string
        if "discord_channel_id" in data:
            dcid = data["discord_channel_id"]
            if dcid is not None:
                if isinstance(dcid, str):
                    if dcid and not dcid.strip().isdigit():
                        errors.append(f"discord_channel_id must be a digit string, got: {dcid!r}")
                elif isinstance(dcid, int):
                    if dcid <= 0:
                        errors.append(f"discord_channel_id must be a positive number, got: {dcid}")
                else:
                    errors.append(f"discord_channel_id must be a number or numeric string, got: {type(dcid).__name__}")

        # vk_token — if present, must be string
        if "vk_token" in data:
            tok = data["vk_token"]
            if tok is not None and not isinstance(tok, str):
                errors.append(f"vk_token must be a string, got: {type(tok).__name__}")

        return errors

    async def start_all(self):
        """Database initialization and starting all monitors."""
        if not self.enable_flag:
            return

        self.is_running = True

        if self.db_init_func:
            await self.db_init_func()
        if self.db_cleanup_func:
            await self.db_cleanup_func()
            from modules_utils.helpers import safe_create_task
            self._cleanup_task = safe_create_task(self._periodic_db_cleanup_loop())
        
        await self._load_and_start_monitors()
        
        config_path = get_config_path(self.config_dir_name)
        if config_path:
            self.config_watcher.watch_directory(config_path, self.reload_all)
            self.config_watcher.start()

    async def _periodic_db_cleanup_loop(self):
        """Background loop for periodic database cleanup."""
        while self.is_running:
            try:
                await asyncio.sleep(24 * 3600)
                if self.is_running and self.db_cleanup_func:
                    await send_to_any_log("info", f"[AutoCleanup] Running periodic cleanup of old records for {self.platform_name}...", emoji=LogEmojis.CLEANUP)
                    await self.db_cleanup_func()
            except asyncio.CancelledError:
                break
            except Exception as e:
                await send_to_any_log("error", f"Error during periodic database cleanup for {self.platform_name}: {e}", emoji=LogEmojis.ERROR)
                await asyncio.sleep(3600)

    async def _load_and_start_monitors(self):
        """Loads configs and creates monitors."""
        configs = await self._load_configs()
        for config in configs:
            platform_id = str(config.get("platform_id", ""))
            if not platform_id:
                continue
            
            if platform_id not in self.monitors:
                await self.add_monitor(config)
                await asyncio.sleep(0.5)

        await send_to_any_log("info", f"{self.platform_name} monitors started. Total: {len(self.monitors)}", emoji=LogEmojis.STARTUP)

    async def add_monitor(self, config: Dict[str, Any]):
        """Creates and registers a single monitor."""
        platform_id = str(config.get("platform_id", ""))
        if not platform_id:
            return

        monitor = self.monitor_class(self.platform_name, config, self.discord_bot, **self.extra_init_args)
            
        self.monitors[platform_id] = monitor
        
        task_name = f"{self.platform_name}_{platform_id}"
        await scheduler.add_monitor(task_name, monitor.start())

    async def reload_all(self):
        """Reload on configuration file changes."""
        await send_to_any_log("info", f"{LogEmojis.CONFIG} Reloading configurations for {self.platform_name}...")
        
        configs = await self._load_configs()
        new_platform_ids = set()
        
        for config in configs:
            platform_id = str(config.get("platform_id", ""))
            if not platform_id:
                continue
            
            new_platform_ids.add(platform_id)
            
            if platform_id in self.monitors:
                monitor = self.monitors[platform_id]
                old_config = getattr(monitor, "config", getattr(monitor, "group_config", {}))
                
                if old_config != config:
                    if hasattr(monitor, "config"):
                        monitor.config = config
                    elif hasattr(monitor, "group_config"):
                        monitor.group_config = config
                        
                    from settings.config import Config
                    default_intervals = {
                        "VK Live": Config.VK_LIVE_CHECK_INTERVAL,
                        "YouTube": Config.YOUTUBE_CHECK_INTERVAL,
                        "Twitch": Config.TWITCH_CHECK_INTERVAL,
                        "Rutube": Config.RUTUBE_CHECK_INTERVAL
                    }
                    fallback_interval = default_intervals.get(getattr(monitor, "platform_name", ""), 300)
                    
                    if hasattr(monitor, "check_interval"):
                        monitor.check_interval = config.get("check_interval", fallback_interval)
                    if hasattr(monitor, "send_channel_notification"):
                        monitor.send_channel_notification = config.get("send_channel_notification", True)
                    if hasattr(monitor, "create_discord_event"):
                        monitor.create_discord_event = config.get("create_discord_event", True)
                    if hasattr(monitor, "discord_channel_id"):
                        monitor.discord_channel_id = config.get("discord_channel_id")
                        
                    if hasattr(monitor, "resolve_group_id"):
                        from modules_utils.helpers import safe_create_task
                        safe_create_task(monitor.resolve_group_id())
            else:
                await self.add_monitor(config)

        for platform_id in list(self.monitors.keys()):
            if platform_id not in new_platform_ids:
                await self.remove_monitor(platform_id)

    async def remove_monitor(self, platform_id: str):
        """Stops and removes monitor."""
        if platform_id in self.monitors:
            monitor = self.monitors[platform_id]
            
            if hasattr(monitor, "active_streams_data") and hasattr(monitor, "platform_name"):
                try:
                    from modules_utils.live_role_helper import LiveRoleHelper
                    for stream_id in list(monitor.active_streams_data.keys()):
                        await LiveRoleHelper.manage_role(
                            monitor.discord_bot, 
                            monitor.config, 
                            monitor.platform_name, 
                            stream_id, 
                            assign=False
                        )
                except Exception as e:
                    await send_to_any_log("error", f"Error clearing roles when removing monitor: {e}", emoji=LogEmojis.ERROR)

            await monitor.stop()
            
            config = getattr(monitor, "config", getattr(monitor, "group_config", {}))
            display_name = config.get("name", platform_id)
            
            task_name = f"{self.platform_name}_{platform_id}"
            await scheduler.remove_monitor(task_name)
            del self.monitors[platform_id]
            await send_to_any_log("info", f"Monitor {self.platform_name} removed: {display_name} ({platform_id})", emoji=LogEmojis.INFO)

    async def stop_all(self):
        """Full stop of all monitors."""
        self.is_running = False
        self.config_watcher.stop()

        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                await send_to_any_log("error", f"Error stopping auto-cleanup task for {self.platform_name}: {e}", emoji=LogEmojis.ERROR)
            self._cleanup_task = None

        for platform_id in list(self.monitors.keys()):
            await self.remove_monitor(platform_id)
        
        await send_to_any_log("info", f"Monitors {self.platform_name} stopped", emoji=LogEmojis.INFO)

    async def _load_configs(self) -> List[Dict[str, Any]]:
        """Loads JSON configs from directory."""
        configs = []
        config_dir = get_config_path(self.config_dir_name)
        if not config_dir or not os.path.exists(config_dir):
            return configs

        filenames = await asyncio.to_thread(os.listdir, config_dir)
        for filename in filenames:
            if filename.endswith('.json'):
                file_path = os.path.join(config_dir, filename)
                try:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        data = json.loads(content)
                        if data.get('platform_id'):
                            schema_errors = self._validate_config_schema(data, filename)
                            if schema_errors:
                                for err in schema_errors:
                                    await send_to_any_log("warning", f"Config {filename} ({self.platform_name}): {err}", emoji=LogEmojis.WARNING)
                            configs.append(data)
                except Exception as e:
                    await send_to_any_log("error", f"Error loading config {filename} ({self.platform_name}): {e}", emoji=LogEmojis.ERROR)
        return configs
