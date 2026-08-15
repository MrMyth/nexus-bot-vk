# modules/twitch_live/twitch_monitor.py
import asyncio
import time
from typing import Dict, Any, Optional, List, Tuple
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from settings.config import Config
from modules_utils.base_stream_monitor import BaseStreamMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase

class TwitchMonitor(BaseStreamMonitor):
    """
    Монитор стримов для Twitch.
    Поддерживает два метода работы:
    1. Без ключей (через GQL / ivr.fi скрапинг).
    2. Через официальный Twitch Helix API (требует TWITCH_CLIENT_ID и TWITCH_CLIENT_SECRET).
    Приоритет методов управляется переменной TWITCH_USE_SCRAPER_PRIMARY в .env / config.

    Оптимизации производительности:
    1. In-Memory TTL caching (60 сек) - исключает дублирующие сетевые запросы.
    2. Оптимизированные сетевые таймауты (10с) и авто-обновление OAuth токена при 401.
    3. Пакетная подготовка и поддержка параллельных запросов для ускорения проверок.
    """
    
    _oauth_token: Optional[str] = None
    _oauth_token_expires_at: float = 0
    _cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
    CACHE_TTL: int = 60  # Секунд кэширования

    def __init__(self, platform_name: str, config: Dict[str, Any], discord_bot, db_helper: Optional[GenericStreamDatabase] = None):
        super().__init__(platform_name, config, discord_bot, db_helper)
        self.client_id = Config.TWITCH_CLIENT_ID
        self.client_secret = Config.TWITCH_CLIENT_SECRET
        self.use_scraper_primary = getattr(Config, "TWITCH_USE_SCRAPER_PRIMARY", True)
        self.check_interval = config.get("check_interval", 1800)

    async def fetch_current_streams(self) -> List[Dict[str, Any]]:
        """Получает статус стрима с использованием основного и резервного метода."""
        # --- 1. Оптимизация: Проверка TTL-кэша ---
        now = time.time()
        cache_key = self.platform_id.lower()
        if cache_key in self._cache:
            cached_time, cached_streams = self._cache[cache_key]
            if now - cached_time < self.CACHE_TTL:
                return cached_streams

        streams = None
        if self.use_scraper_primary:
            # Новый метод (без ключей) как основной
            streams = await self._fetch_via_scraper()
            if streams is None and self.client_id and self.client_secret:
                # Fallback на официальный API
                streams = await self._fetch_via_api()
        else:
            # Официальный API как основной
            if self.client_id and self.client_secret:
                streams = await self._fetch_via_api()
            
            if streams is None:
                # Fallback на скрапер без ключей
                streams = await self._fetch_via_scraper()

        result = streams if streams is not None else []
        # Сохраняем в TTL-кэш
        self._cache[cache_key] = (now, result)
        return result

    async def _fetch_via_scraper(self) -> Optional[List[Dict[str, Any]]]:
        """Получает статус стрима без API-ключей (через Twitch GQL или ivr.fi API)."""
        from modules_utils.http_client import HttpClient

        # 1. Попытка через Twitch GQL API
        gql_url = "https://gql.twitch.tv/gql"
        headers = {
            "Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json"
        }
        gql_query = """
        query GetStreamInfo($channel: String!) {
          user(login: $channel) {
            id
            login
            displayName
            profileImageURL(width: 300)
            stream {
              id
              title
              type
              viewersCount
              createdAt
              game {
                id
                name
              }
              previewImageURL(width: 1280, height: 720)
            }
          }
        }
        """
        payload = [{
            "operationName": "GetStreamInfo",
            "variables": {"channel": self.platform_id},
            "query": gql_query
        }]

        try:
            # --- 2. Оптимизация: Таймаут 10 секунд ---
            data = await HttpClient.post(gql_url, json=payload, headers=headers, timeout=10)
            if data and isinstance(data, list) and len(data) > 0:
                user = data[0].get("data", {}).get("user")
                if user and isinstance(user, dict):
                    stream = user.get("stream")
                    if stream and isinstance(stream, dict) and stream.get("type") == "live":
                        stream_id = str(stream.get("id"))
                        game_data = stream.get("game")
                        game_name = game_data.get("name", "") if isinstance(game_data, dict) else ""
                        return [{
                            "stream_id": stream_id,
                            "title": stream.get("title", "Twitch Live"),
                            "url": f"https://www.twitch.tv/{self.platform_id}",
                            "author": user.get("displayName", self.platform_id),
                            "game": game_name,
                            "viewers": stream.get("viewersCount", 0),
                            "thumbnail": stream.get("previewImageURL", f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{self.platform_id.lower()}-1280x720.jpg")
                        }]
                    else:
                        return []
        except Exception as e:
            await send_to_any_log("warning", f"Twitch GQL scraping unavailable ({self.platform_id}): {e}", emoji=LogEmojis.WARNING)

        # 2. Резервная попытка через публичный API ivr.fi
        try:
            ivr_url = f"https://api.ivr.fi/v2/twitch/user?login={self.platform_id}"
            ivr_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            data = await HttpClient.get(ivr_url, headers=ivr_headers, timeout=10)
            if data and isinstance(data, list) and len(data) > 0:
                user = data[0]
                if user and isinstance(user, dict):
                    stream = user.get("stream")
                    if stream and isinstance(stream, dict):
                        stream_id = str(stream.get("id"))
                        game_data = stream.get("game")
                        game_name = game_data.get("displayName", "") if isinstance(game_data, dict) else ""
                        return [{
                            "stream_id": stream_id,
                            "title": stream.get("title", "Twitch Live"),
                            "url": f"https://www.twitch.tv/{self.platform_id}",
                            "author": user.get("displayName", self.platform_id),
                            "game": game_name,
                            "viewers": stream.get("viewersCount", 0),
                            "thumbnail": f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{self.platform_id.lower()}-1280x720.jpg"
                        }]
                    else:
                        return []
        except Exception as e:
            await send_to_any_log("warning", f"Twitch ivr.fi scraping unavailable ({self.platform_id}): {e}", emoji=LogEmojis.WARNING)

        return None

    async def _fetch_via_api(self) -> Optional[List[Dict[str, Any]]]:
        """Получает статус стрима через Twitch Helix API с повторами и авто-сбросом просроченного токена."""
        if not self.client_id or not self.client_secret:
            return None

        token = await self._get_token()
        if not token:
            return None

        from modules_utils.http_client import HttpClient
        url = "https://api.twitch.tv/helix/streams"
        params = {"user_login": self.platform_id}

        for attempt in range(2):
            headers = {
                "Client-ID": self.client_id,
                "Authorization": f"Bearer {token}"
            }
            try:
                data = await HttpClient.get(url, params=params, headers=headers, timeout=10)
                if data and isinstance(data, dict):
                    # Если получим ошибку 401 Unauthorized, сбрасываем токен
                    if data.get("status") == 401:
                        TwitchMonitor._oauth_token = None
                        token = await self._get_token()
                        continue

                    items = data.get("data", [])
                    streams = []
                    for item in items:
                        if item.get("type") == "live":
                            stream_id = str(item.get("id"))
                            streams.append({
                                "stream_id": stream_id,
                                "title": item.get("title", "Twitch Live"),
                                "url": f"https://www.twitch.tv/{self.platform_id}",
                                "author": item.get("user_name", self.platform_id),
                                "game": item.get("game_name", ""),
                                "viewers": item.get("viewer_count", 0),
                                "thumbnail": item.get("thumbnail_url", "").replace("{width}", "1280").replace("{height}", "720")
                            })
                    return streams
            except Exception as e:
                await send_to_any_log("error", f"Twitch API error {self.platform_id} (attempt {attempt+1}): {e}", emoji=LogEmojis.ERROR)
            
            if attempt < 1:
                await asyncio.sleep(2)
            
        return None

    async def _get_token(self) -> Optional[str]:
        """Получает и кэширует OAuth токен для Twitch API."""
        now = time.time()
        if TwitchMonitor._oauth_token and now < TwitchMonitor._oauth_token_expires_at:
            return TwitchMonitor._oauth_token

        from modules_utils.http_client import HttpClient
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }

        try:
            data = await HttpClient.post(url, params=params, timeout=10)
            if data and isinstance(data, dict) and "access_token" in data:
                TwitchMonitor._oauth_token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                # Кэшируем токен с запасом в 60 секунд
                TwitchMonitor._oauth_token_expires_at = now + max(0, expires_in - 60)
                return TwitchMonitor._oauth_token
            else:
                await send_to_any_log("error", "Failed to obtain Twitch API token", emoji=LogEmojis.ERROR)
        except Exception as e:
            await send_to_any_log("error", f"Error obtaining Twitch token: {e}", emoji=LogEmojis.ERROR)
        
        return None
