# modules/twitch_live/twitch_manager.py
from modules_utils.generic_stream_manager import GenericStreamManager
from modules.twitch_live.twitch_monitor import TwitchMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase
from settings.data_files import Files
from settings.config import Config

class TwitchLiveManager(GenericStreamManager):
    def __init__(self, discord_bot):
        db_helper = GenericStreamDatabase(Files.TWITCH_DATABASE_FILE, "active_twitch_streams")
        super().__init__(
            platform_name="Twitch",
            monitor_class=TwitchMonitor,
            discord_bot=discord_bot,
            db_helper=db_helper,
            config_dir_name="twitch_configs",
            enable_flag=Config.ENABLE_TWITCH_LIVE_MONITORING,
            retention_days=Config.RETENTION_DAYS
        )
        self.eventsub_ws = None

    async def start_all(self):
        await super().start_all()
        if self.enable_flag:
            from modules.twitch_live.eventsub_websocket import TwitchEventSubWS
            self.eventsub_ws = TwitchEventSubWS(self.discord_bot)
            self.eventsub_ws.set_manager(self)
            import asyncio
            asyncio.create_task(self.eventsub_ws.start())

    async def add_monitor(self, config):
        await super().add_monitor(config)
        platform_id = str(config.get("platform_id", ""))
        if platform_id and self.eventsub_ws:
            import asyncio
            asyncio.create_task(self.eventsub_ws.subscribe_new_monitor(platform_id))

    async def stop_all(self):
        if self.eventsub_ws:
            await self.eventsub_ws.stop()
            self.eventsub_ws = None
        await super().stop_all()
