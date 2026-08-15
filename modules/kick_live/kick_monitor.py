# modules/kick_live/kick_monitor.py
import aiohttp
from typing import Dict, Any, Optional, List
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from settings.config import Config
from modules_utils.base_stream_monitor import BaseStreamMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase
from settings.data_files import Files

class KickMonitor(BaseStreamMonitor):
    """Монитор стримов для Kick."""

    def __init__(self, platform_name: str, config: Dict[str, Any], discord_bot, db_helper: Optional[GenericStreamDatabase] = None):
        super().__init__(platform_name, config, discord_bot, db_helper)

    async def fetch_current_streams(self) -> List[Dict[str, Any]]:
        """Получает статус стрима через Kick API (неофициальный) с авто-fallback на Selenium."""
        from modules_utils.http_client import HttpClient
        url = f"https://kick.com/api/v1/channels/{self.platform_id}"
        
        streams = []
        try:
            data = await HttpClient.get(url)
            if data and isinstance(data, dict):
                livestream = data.get("livestream")
                
                if livestream and livestream.get("is_live"):
                    stream_id = str(livestream.get("id"))
                    streams.append({
                        "stream_id": stream_id,
                        "title": livestream.get("session_title", "Kick Live"),
                        "url": f"https://kick.com/{self.platform_id}",
                        "author": data.get("user", {}).get("username", self.platform_id),
                        "game": (livestream.get("categories") or [{}])[0].get("name", ""),
                        "viewers": livestream.get("viewer_count", 0),
                        "image": livestream.get("thumbnail", {}).get("url")
                    })
        except Exception as e:
            # Не прерываем — ниже сработает Selenium fallback, но обязательно логируем,
            # иначе постоянные сбои основного (быстрого) пути остаются полностью невидимыми
            # и заметны только по возросшей частоте медленных Selenium-запросов.
            await send_to_any_log(
                "warning",
                f"[Kick {self.platform_id}] Primary request via HttpClient failed, attempting Selenium fallback: {e}",
                emoji=LogEmojis.WARNING
            )

        # Если обычный HttpClient был заблокирован Cloudflare или вернул ошибку,
        # запускаем надежный Selenium-обход в фоновом потоке
        if not streams:
            try:
                import asyncio
                import json
                from modules_utils.selenium_helper import SeleniumHelper
                
                # Запускаем headless-браузер с отдельной изолированной папкой для профиля
                html_source = await asyncio.to_thread(
                    SeleniumHelper.fetch_page_source, 
                    url, 
                    f"kick_{self.platform_id}_profile",
                    4.0  # даем время на выполнение JS и прохождение Cloudflare
                )
                
                if html_source:
                    data = None
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html_source, "html.parser")
                        pre = soup.find("pre")
                        if pre:
                            data = json.loads(pre.get_text().strip())
                        else:
                            body = soup.find("body")
                            if body:
                                body_text = body.get_text().strip()
                                if body_text.startswith("{") and body_text.endswith("}"):
                                    data = json.loads(body_text)
                    except Exception:
                        pass
                        
                    if not data:
                        try:
                            import re
                            match = re.search(r'\{.*\}', html_source, re.DOTALL)
                            if match:
                                data = json.loads(match.group(0))
                        except Exception:
                            pass
                            
                    if data and isinstance(data, dict):
                        livestream = data.get("livestream")
                        if livestream and livestream.get("is_live"):
                            stream_id = str(livestream.get("id"))
                            streams.append({
                                "stream_id": stream_id,
                                "title": livestream.get("session_title", "Kick Live"),
                                "url": f"https://kick.com/{self.platform_id}",
                                "author": data.get("user", {}).get("username", self.platform_id),
                                "game": (livestream.get("categories") or [{}])[0].get("name", ""),
                                "viewers": livestream.get("viewer_count", 0),
                                "image": livestream.get("thumbnail", {}).get("url")
                            })
                            await send_to_any_log(
                                "success", 
                                f"[Kick {self.platform_id}] Selenium successfully bypassed Cloudflare protection and detected active stream!", 
                                emoji=LogEmojis.SUCCESS
                            )
            except Exception as e:
                await send_to_any_log(
                    "error", 
                    f"Error in backup Kick monitoring via Selenium ({self.platform_id}): {e}", 
                    emoji=LogEmojis.ERROR
                )
            
        return streams
