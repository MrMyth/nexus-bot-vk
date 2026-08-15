# modules/youtube/youtube_manager.py
from modules_utils.generic_stream_manager import GenericStreamManager
from modules.youtube.youtube_monitor import YouTubeMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase
from settings.data_files import Files
from settings.config import Config

class YouTubeManager(GenericStreamManager):
    """
    Менеджер YouTube (Объединенный Video + Live).
    """
    def __init__(self, discord_bot):
        db_helper = GenericStreamDatabase(Files.YOUTUBE_DATABASE_FILE, "active_youtube_streams")
        super().__init__(
            platform_name="YouTube",
            monitor_class=YouTubeMonitor,
            discord_bot=discord_bot,
            db_helper=db_helper,
            config_dir_name="youtube_configs",
            enable_flag=Config.ENABLE_YOUTUBE_MONITORING,
            retention_days=Config.RETENTION_DAYS
        )
