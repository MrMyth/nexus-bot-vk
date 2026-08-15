# modules/rutube/rutube_manager.py
from modules_utils.generic_stream_manager import GenericStreamManager
from modules.rutube.rutube_monitor import RutubeMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase
from settings.data_files import Files
from settings.config import Config

class RutubeManager(GenericStreamManager):
    """
    Менеджер Rutube (Объединенный Video + Live).
    """
    def __init__(self, discord_bot):
        db_helper = GenericStreamDatabase(Files.RUTUBE_DATABASE_FILE, "active_rutube_streams")
        super().__init__(
            platform_name="Rutube",
            monitor_class=RutubeMonitor,
            discord_bot=discord_bot,
            db_helper=db_helper,
            config_dir_name="rutube_configs",
            enable_flag=Config.ENABLE_RUTUBE_MONITORING,
            retention_days=Config.RETENTION_DAYS
        )
