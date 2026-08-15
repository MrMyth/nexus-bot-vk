# vk_live/live_monitor.py
import asyncio
import aiohttp
import aiosqlite
from typing import Dict, Any, Optional, List
from log_system.logger_helper import send_to_any_log
from settings.config import Config
from constants.emojis import LogEmojis
from constants.base import VKAPI
from modules.vk_live.live_database import (
    save_stream, mark_stream_finished, get_event_id_for_stream
)
from modules_utils.vk_api_client import VKApiClient
from settings.data_files import Files
from modules_utils.base_stream_monitor import BaseStreamMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase

class LiveMonitor(BaseStreamMonitor):
    def __init__(self, platform_name: str, config: Dict[str, Any], discord_bot, db_helper: Optional[GenericStreamDatabase] = None):
        super().__init__(platform_name, config, discord_bot, db_helper)

    async def fetch_current_streams(self) -> List[Dict[str, Any]]:
        """Получает список текущих активных стримов с VK."""
        resp = await VKApiClient.get_live_status_with_session(self.session, self.platform_id)
        if not resp:
            return []

        api_streams = resp.get("data", {}).get("streams", [])
        streams = []
        
        for stream in api_streams:
            if stream.get("isOnline") and not stream.get("isEnded"):
                stream_id = str(stream.get("id"))
                streams.append({
                    "stream_id": stream_id,
                    "title": stream.get("title") or f"Стрим {self.platform_id}",
                    "url": f"https://{VKAPI.BASE_URL_VK_LIVE}/{self.platform_id}",
                    "game": stream.get("category", {}).get("title", ""),
                    "viewers": stream.get("count", {}).get("viewers", 0),
                    "author": self.platform_id,
                    "image": stream.get("previewUrl") or stream.get("preview_url")
                })
        return streams

    # Методы БД теперь наследуются от BaseStreamMonitor и используют db_helper
