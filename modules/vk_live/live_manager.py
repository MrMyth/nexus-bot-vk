# modules/vk_live/live_manager.py
from modules_utils.generic_stream_manager import GenericStreamManager
from modules.vk_live.live_monitor import LiveMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase
from settings.data_files import Files
from settings.config import Config

class LiveManager(GenericStreamManager):
    def __init__(self, discord_bot):
        db_helper = GenericStreamDatabase(Files.LIVE_DATABASE_FILE, "vk_active_streams")
        super().__init__(
            platform_name="VK Live",
            monitor_class=LiveMonitor,
            discord_bot=discord_bot,
            db_helper=db_helper,
            config_dir_name="live_configs",
            enable_flag=Config.ENABLE_VK_LIVE_MONITORING,
            retention_days=Config.RETENTION_DAYS
        )
