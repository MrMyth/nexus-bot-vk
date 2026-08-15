# modules/rutube/rutube_monitor.py
import asyncio
import time
from typing import Dict, Any, Optional, List
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from settings.config import Config
from modules_utils.base_stream_monitor import BaseStreamMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase

# Стримы и видео на Rutube берутся из одного и того же ответа API
# (person/{id}/), поэтому кэшируем "сырые" результаты на короткое время, чтобы
# check_status() не делал два одинаковых HTTP-запроса подряд (fetch_current_streams
# + fetch_current_videos) в рамках одного цикла проверки.
_RAW_RESPONSE_TTL_SECONDS = 10

class RutubeMonitor(BaseStreamMonitor):
    """
    Объединенный монитор Rutube для отслеживания стримов и видео.
    """
    def __init__(self, platform_name: str, config: Dict[str, Any], discord_bot, db_helper: Optional[GenericStreamDatabase] = None):
        super().__init__(platform_name, config, discord_bot, db_helper)
        
        # Настройки из конфига + Глобальные флаги
        self.monitor_live = config.get("monitor_live", True)
        self.monitor_video = config.get("monitor_video", True)

        self._raw_response_cache: Optional[Dict[str, Any]] = None
        self._raw_response_cache_time: float = 0.0

    async def _fetch_person_data(self) -> Optional[Dict[str, Any]]:
        """Запрашивает (с коротким кэшем) общий ответ API Rutube для канала.

        Используется и стримами, и видео — без кэша каждый цикл check_status()
        делал бы этот запрос дважды подряд впустую.
        """
        now = time.monotonic()
        if self._raw_response_cache is not None and (now - self._raw_response_cache_time) < _RAW_RESPONSE_TTL_SECONDS:
            return self._raw_response_cache

        from modules_utils.http_client import HttpClient
        url = f"https://rutube.ru/api/video/person/{self.platform_id}/"
        data = await HttpClient.get(url)
        self._raw_response_cache = data if isinstance(data, dict) else None
        self._raw_response_cache_time = now
        return self._raw_response_cache

    async def fetch_current_streams(self) -> List[Dict[str, Any]]:
        """Получает список текущих активных стримов с Rutube."""
        if not self.monitor_live:
            return []

        streams = []
        try:
            data = await self._fetch_person_data()
            if data:
                results = data.get("results", [])
                for item in results:
                    if item.get("is_livestream") and not item.get("is_ended"):
                        stream_id = str(item.get("id"))
                        streams.append({
                            "stream_id": stream_id,
                            "title": item.get("title", "Rutube Live"),
                            "url": item.get("video_url") or f"https://rutube.ru/video/{stream_id}/",
                            "author": item.get("author", {}).get("name", self.platform_id),
                            "game": item.get("category", {}).get("title", ""),
                            "viewers": item.get("viewers_count", 0),
                            "image": item.get("thumbnail_url")
                        })
        except Exception as e:
            await send_to_any_log("error", f"[Rutube] Stream API error for {self.platform_id}: {e}", emoji=LogEmojis.ERROR)
            
        return streams

    async def check_status(self, force_end: bool = False):
        """Переопределяем для добавления проверки видео."""
        if self.monitor_live:
            await super().check_status(force_end=force_end)
        
        if self.monitor_video:
            await self._check_videos()

    async def fetch_current_videos(self) -> List[Dict[str, Any]]:
        """Получает список текущих видео с Rutube."""
        if not self.monitor_video:
            return []

        videos = []
        try:
            data = await self._fetch_person_data()
            if data:
                results = data.get("results", [])
                display_name = self.config.get('name', self.platform_id)
                for item in results:
                    if not item.get("is_livestream"):
                        video_id = str(item.get("id"))
                        videos.append({
                            "video_id": video_id,
                            "title": item.get("title", ""),
                            "url": item.get("video_url") or f"https://rutube.ru/video/{video_id}/",
                            "author": item.get("author", {}).get("name", display_name),
                            "image": item.get("thumbnail_url"),
                            "description": item.get("description", "")
                        })
        except Exception as e:
            await send_to_any_log("error", f"[Rutube Video Search] Video search API error for {self.platform_id}: {e}", emoji=LogEmojis.ERROR)
            
        return videos
