# modules/vk_assets/asset_manager.py
from typing import List
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from settings.config import Config
from modules.vk_assets.asset_config import load_asset_configs
from modules.vk_assets.asset_monitor import VKAssetMonitor
from modules.vk_assets.asset_database import init_assets_db, cleanup_old_assets
from modules_utils.config_watcher import ConfigWatcher
from modules_utils.files import get_config_path

from modules_utils.task_scheduler import scheduler

class VKAssetManager:
    """Менеджер для управления мониторами ассетов ВК."""
    
    def __init__(self, discord_bot):
        self.discord_bot = discord_bot
        self.monitors: Dict[str, VKAssetMonitor] = {}
        self.config_watcher = ConfigWatcher()

    async def start_all(self):
        """Запускает мониторинг ассетов для всех настроенных групп."""
        if not Config.ENABLE_VK_ASSETS_MONITORING:
            return

        await init_assets_db()
        await cleanup_old_assets(Config.RETENTION_DAYS)
        
        await self._load_and_start_monitors()
        
        # Запускаем отслеживание изменений в конфигах
        config_path = get_config_path("vk_asset_configs")
        self.config_watcher.watch_directory(config_path, self.reload_all)
        self.config_watcher.start()

    async def _load_and_start_monitors(self):
        configs = await load_asset_configs()
        if not configs:
            return

        for config in configs:
            platform_id = str(config.get("platform_id") or config.get("owner_id", ""))
            if not platform_id:
                continue
            
            if platform_id not in self.monitors:
                monitor = VKAssetMonitor(config, self.discord_bot)
                self.monitors[platform_id] = monitor
                await scheduler.add_monitor(f"VKAssets_{platform_id}", monitor.start())
                await send_to_any_log("info", f"Started VK asset monitor: {config.get('name', platform_id)}", emoji=LogEmojis.INFO)

    async def reload_all(self):
        """Перезагружает конфигурации и обновляет мониторы."""
        await send_to_any_log("info", "Reloading VK asset configs...", emoji=LogEmojis.CONFIG)
        
        configs = await load_asset_configs()
        new_platform_ids = set()
        
        for config in configs:
            platform_id = str(config.get("platform_id") or config.get("owner_id", ""))
            if not platform_id:
                continue
            
            new_platform_ids.add(platform_id)
            
            if platform_id in self.monitors:
                # Обновляем конфиг существующего монитора
                self.monitors[platform_id].config = config
            else:
                # Создаем новый монитор
                monitor = VKAssetMonitor(config, self.discord_bot)
                self.monitors[platform_id] = monitor
                await scheduler.add_monitor(f"VKAssets_{platform_id}", monitor.start())
                await send_to_any_log("info", f"Added new VK asset monitor: {config.get('name', platform_id)}", emoji=LogEmojis.INFO)

        # Удаляем мониторы, которых больше нет в конфигах
        for platform_id in list(self.monitors.keys()):
            if platform_id not in new_platform_ids:
                monitor = self.monitors[platform_id]
                display_name = getattr(monitor, "config", {}).get("name", platform_id)
                await monitor.stop()
                await scheduler.remove_monitor(f"VKAssets_{platform_id}")
                del self.monitors[platform_id]
                await send_to_any_log("info", f"Removed VK asset monitor: {display_name} ({platform_id})", emoji=LogEmojis.INFO)

    async def stop_all(self):
        """Останавливает все мониторы."""
        self.config_watcher.stop()
        for platform_id, monitor in self.monitors.items():
            await monitor.stop()
        self.monitors.clear()
        await send_to_any_log("info", "All VK asset monitors stopped.", emoji=LogEmojis.INFO)
