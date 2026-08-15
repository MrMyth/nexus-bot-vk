from modules_utils.base_monitor_manager import BaseMonitorManager
from modules.vk_wall.monitor import GroupMonitor
from modules.vk_wall.database_wall import init_db, cleanup_old_posts
from settings.config import Config

class MonitorManager(BaseMonitorManager):
    def __init__(self, discord_bot):
        super().__init__(
            platform_name="VK Wall",
            monitor_class=GroupMonitor,
            discord_bot=discord_bot,
            config_dir_name="group_configs",
            enable_flag=Config.ENABLE_VK_WALL_MONITORING,
            db_init_func=init_db,
            db_cleanup_func=cleanup_old_posts
        )
