# modules/goodgame/goodgame_monitor.py
from typing import Dict, Any, Optional, List
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from modules_utils.base_stream_monitor import BaseStreamMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase

class GoodGameMonitor(BaseStreamMonitor):
    """Монитор стримов для GoodGame.ru."""

    def __init__(self, platform_name: str, config: Dict[str, Any], discord_bot, db_helper: Optional[GenericStreamDatabase] = None):
        super().__init__(platform_name, config, discord_bot, db_helper)

    async def fetch_current_streams(self) -> List[Dict[str, Any]]:
        """Получает статус стрима через GoodGame API."""
        from modules_utils.http_client import HttpClient
        url = f"https://goodgame.ru/api/getggchannelstatus?id={self.platform_id}&fmt=json"
        
        streams = []
        try:
            data = await HttpClient.get(url)
            if data and isinstance(data, dict):
                for channel_key, channel_data in data.items():
                    if not isinstance(channel_data, dict):
                        continue
                    
                    status = str(channel_data.get("status", "")).strip().lower()
                    if status in ["live", "on"]:
                        stream_id = str(channel_data.get("stream_id", channel_data.get("id", channel_key)))
                        
                        title = channel_data.get("title") or "GoodGame Live"
                        author = channel_data.get("key") or self.platform_id
                        game = channel_data.get("game") or "GoodGame Stream"
                        
                        viewers_val = channel_data.get("viewers", 0)
                        try:
                            viewers = int(viewers_val)
                        except (ValueError, TypeError):
                            viewers = 0
                        
                        image = channel_data.get("img") or channel_data.get("thumb") or channel_data.get("avatar")
                        if image and isinstance(image, str) and image.startswith("/"):
                            image = f"https://goodgame.ru{image}"
                        
                        url_stream = channel_data.get("url") or f"https://goodgame.ru/channel/{self.platform_id}"
                        
                        streams.append({
                            "stream_id": stream_id,
                            "title": title,
                            "url": url_stream,
                            "author": author,
                            "game": game,
                            "viewers": viewers,
                            "image": image
                        })
        except Exception as e:
            await send_to_any_log(
                "error",
                f"Error monitoring GoodGame ({self.platform_id}): {e}",
                emoji=LogEmojis.ERROR
            )
            
        return streams
