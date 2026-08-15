# modules/goodgame/goodgame_manager.py
from modules_utils.generic_stream_manager import GenericStreamManager
from modules.goodgame.goodgame_monitor import GoodGameMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase
from settings.data_files import Files
from settings.config import Config

class GoodGameLiveManager(GenericStreamManager):
    def __init__(self, discord_bot):
        db_helper = GenericStreamDatabase(Files.GOODGAME_DATABASE_FILE, "active_goodgame_streams")
        super().__init__(
            platform_name="goodgame",
            monitor_class=GoodGameMonitor,
            discord_bot=discord_bot,
            db_helper=db_helper,
            config_dir_name="goodgame_configs",
            enable_flag=Config.ENABLE_GOODGAME_MONITORING,
            retention_days=Config.RETENTION_DAYS
        )
