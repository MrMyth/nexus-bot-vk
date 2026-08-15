from modules_utils.base_monitor_manager import BaseMonitorManager
from modules_utils.generic_stream_database import GenericStreamDatabase
from modules_utils.base_stream_monitor import BaseStreamMonitor
from typing import Type

class GenericStreamManager(BaseMonitorManager):
    """Универсальный менеджер для управления мониторами стримов."""
    
    def __init__(
        self, 
        platform_name: str, 
        monitor_class: Type[BaseStreamMonitor], 
        discord_bot, 
        db_helper: GenericStreamDatabase, 
        config_dir_name: str, 
        enable_flag: bool, 
        retention_days: int = 30
    ):
        super().__init__(
            platform_name=platform_name,
            monitor_class=monitor_class,
            discord_bot=discord_bot,
            config_dir_name=config_dir_name,
            enable_flag=enable_flag,
            db_init_func=db_helper.init_db,
            db_cleanup_func=lambda: db_helper.cleanup(retention_days),
            extra_init_args={"db_helper": db_helper}
        )
        self.db_helper = db_helper
        self.retention_days = retention_days
