# modules/vk_com_live/live_manager.py
from modules_utils.generic_stream_manager import GenericStreamManager
from modules.vk_com_live.live_monitor import VKComLiveMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase
from settings.data_files import Files
from settings.config import Config

class VKComLiveManager(GenericStreamManager):
    def __init__(self, discord_bot):
        db_helper = GenericStreamDatabase(Files.VK_COM_LIVE_DATABASE_FILE, "active_vk_com_streams")
        super().__init__(
            platform_name="vk_com",
            monitor_class=VKComLiveMonitor,
            discord_bot=discord_bot,
            db_helper=db_helper,
            config_dir_name="vk_com_live_configs",
            enable_flag=Config.ENABLE_VK_COM_LIVE_MONITORING,
            retention_days=Config.RETENTION_DAYS
        )
