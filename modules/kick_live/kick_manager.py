# modules/kick_live/kick_manager.py
from modules_utils.generic_stream_manager import GenericStreamManager
from modules.kick_live.kick_monitor import KickMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase
from settings.data_files import Files
from settings.config import Config

class KickLiveManager(GenericStreamManager):
    def __init__(self, discord_bot):
        db_helper = GenericStreamDatabase(Files.KICK_DATABASE_FILE, "active_kick_streams")
        super().__init__(
            platform_name="Kick",
            monitor_class=KickMonitor,
            discord_bot=discord_bot,
            db_helper=db_helper,
            config_dir_name="kick_configs",
            enable_flag=Config.ENABLE_KICK_LIVE_MONITORING,
            retention_days=Config.RETENTION_DAYS
        )
