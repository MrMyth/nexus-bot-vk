# modules/trovo/trovo_manager.py
from modules_utils.generic_stream_manager import GenericStreamManager
from modules.trovo.trovo_monitor import TrovoMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase
from settings.data_files import Files
from settings.config import Config

class TrovoManager(GenericStreamManager):
    """Менеджер стримов для Trovo."""
    def __init__(self, discord_bot):
        db_helper = GenericStreamDatabase(Files.TROVO_DATABASE_FILE, "active_trovo_streams")
        super().__init__(
            platform_name="Trovo",
            monitor_class=TrovoMonitor,
            discord_bot=discord_bot,
            db_helper=db_helper,
            config_dir_name="trovo_configs",
            enable_flag=Config.ENABLE_TROVO_MONITORING,
            retention_days=Config.RETENTION_DAYS
        )
