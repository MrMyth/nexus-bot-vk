# modules/twitch_live/eventsub_websocket.py
import asyncio
import json
import aiohttp
from typing import Dict, Any, Optional, Set, List
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from settings.config import Config

class TwitchEventSubWS:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TwitchEventSubWS, cls).__new__(cls)
        return cls._instance

    def __init__(self, discord_bot=None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self.discord_bot = discord_bot
        self.client_id = Config.TWITCH_CLIENT_ID
        self.client_secret = Config.TWITCH_CLIENT_SECRET
        self.ws_url = "wss://eventsub.wss.twitch.tv/ws"
        self._session_id: Optional[str] = None
        self._user_id_map: Dict[str, str] = {}  # login -> user_id
        self._connect_task: Optional[asyncio.Task] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.manager = None
        self.is_running = False
        self._token: Optional[str] = None

    def set_manager(self, manager):
        """Регистрирует TwitchLiveManager для прямого вызова проверок."""
        self.manager = manager

    async def start(self):
        """Запускает WebSocket-клиент EventSub."""
        if not self.client_id or not self.client_secret:
            await send_to_any_log("warning", "[Twitch-EventSub] TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET not set. Real-time Twitch EventSub is disabled.", emoji=LogEmojis.WARNING)
            return

        self.is_running = True
        retry_delay = 5
        
        while self.is_running:
            try:
                await send_to_any_log("info", f"[Twitch-EventSub] Connecting to WebSocket ({self.ws_url})...", emoji=LogEmojis.INFO)
                
                from modules_utils.http_client import HttpClient
                session = await HttpClient.get_session()
                
                async with session.ws_connect(self.ws_url) as ws:
                    self._ws = ws
                    retry_delay = 5  # Сброс задержки при успешном коннекте
                    await self._handle_ws_loop(ws)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                await send_to_any_log("error", f"[Twitch-EventSub] WebSocket connection error: {e}", emoji=LogEmojis.ERROR)
            
            if self.is_running:
                await send_to_any_log("info", f"[Twitch-EventSub] Reconnecting in {retry_delay}s...", emoji=LogEmojis.INFO)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 120)

    async def stop(self):
        """Полная остановка WebSocket-клиента."""
        self.is_running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        await send_to_any_log("info", "[Twitch-EventSub] Twitch EventSub client stopped.", emoji=LogEmojis.INFO)

    async def _handle_ws_loop(self, ws):
        """Основной цикл приема сообщений из сокета."""
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await self._process_message(data)
                except Exception as e:
                    await send_to_any_log("error", f"[Twitch-EventSub] Error processing message: {e}", emoji=LogEmojis.ERROR)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                break

    async def _process_message(self, data: Dict[str, Any]):
        """Обработка различных типов EventSub сообщений."""
        metadata = data.get("metadata", {})
        msg_type = metadata.get("message_type")
        payload = data.get("payload", {})

        if msg_type == "session_welcome":
            session = payload.get("session", {})
            self._session_id = session.get("id")
            status = session.get("status")
            await send_to_any_log("info", f"[Twitch-EventSub] EventSub session welcomed. ID: {self._session_id} | Status: {status}", emoji=LogEmojis.SUCCESS)
            
            if status == "connected":
                # Новая сессия — подписываемся на все зарегистрированные каналы
                await self._subscribe_all()
            elif status == "reconnecting":
                # Сессия успешно переехала на новый сокет
                # Возвращаем стандартный адрес для будущих подключений
                self.ws_url = "wss://eventsub.wss.twitch.tv/ws"
                
        elif msg_type == "session_keepalive":
            # Просто проверка связи (ping-pong)
            pass
            
        elif msg_type == "session_reconnect":
            reconnect_url = payload.get("session", {}).get("reconnect_url")
            if reconnect_url:
                await send_to_any_log("info", f"[Twitch-EventSub] Reconnect request received. New URL: {reconnect_url}", emoji=LogEmojis.INFO)
                self.ws_url = reconnect_url
                if self._ws:
                    await self._ws.close()  # Закрываем старый сокет, запускаемся заново по новому URL

        elif msg_type == "notification":
            sub_type = payload.get("subscription", {}).get("type")
            event = payload.get("event", {})
            broadcaster_login = event.get("broadcaster_user_login")
            
            if not broadcaster_login:
                return
                
            await send_to_any_log("info", f"[Twitch-EventSub] Received '{sub_type}' event from {broadcaster_login}!", emoji=LogEmojis.SUCCESS)
            
            if self.manager:
                # Находим соответствующий монитор по platform_id (без учета регистра)
                monitor = None
                for pid, mon in self.manager.monitors.items():
                    if pid.lower() == broadcaster_login.lower():
                        monitor = mon
                        break
                        
                if monitor:
                    if sub_type == "stream.online":
                        # Когда стрим начинается, даем Twitch Helix 3 - 5 секунд на синхронизацию кэша перед проверкой
                        async def delayed_check():
                            await asyncio.sleep(4)
                            await monitor.check_status()
                        asyncio.create_task(delayed_check())
                    elif sub_type == "stream.offline":
                        # При завершении стрима запускаем проверку незамедлительно.
                        # force_end=True — Twitch уже авторитетно сообщил о завершении,
                        # поэтому не ждём подтверждения через несколько проверок подряд.
                        asyncio.create_task(monitor.check_status(force_end=True))

    async def _subscribe_all(self):
        """Подписывается на все активные мониторы Twitch."""
        if not self.manager:
            return
            
        logins = list(self.manager.monitors.keys())
        if not logins:
            await send_to_any_log("info", "[Twitch-EventSub] No active Twitch monitors to subscribe to.", emoji=LogEmojis.INFO)
            return

        await send_to_any_log("info", f"[Twitch-EventSub] Resolving user IDs for channels: {logins}...", emoji=LogEmojis.INFO)
        self._user_id_map = await self._resolve_user_ids(logins)
        
        sub_count = 0
        for login in logins:
            user_id = self._user_id_map.get(login.lower())
            if not user_id:
                await send_to_any_log("error", f"[Twitch-EventSub] Failed to get user ID for channel '{login}'", emoji=LogEmojis.ERROR)
                continue
                
            success_online = await self._subscribe_to_channel(user_id, "stream.online")
            success_offline = await self._subscribe_to_channel(user_id, "stream.offline")
            if success_online and success_offline:
                sub_count += 1
                
        await send_to_any_log("info", f"[Twitch-EventSub] Registered real-time subscription for {sub_count}/{len(logins)} Twitch channels.", emoji=LogEmojis.SUCCESS)

    async def subscribe_new_monitor(self, login: str):
        """Динамически регистрирует подписку для вновь добавленного или перезапущенного монитора."""
        if not self.is_running or not self._session_id:
            return
            
        login_lower = login.lower()
        if login_lower in self._user_id_map:
            user_id = self._user_id_map[login_lower]
        else:
            resolved = await self._resolve_user_ids([login])
            user_id = resolved.get(login_lower)
            if user_id:
                self._user_id_map[login_lower] = user_id
                
        if not user_id:
            await send_to_any_log("error", f"[Twitch-EventSub] Failed to get user ID for dynamic channel '{login}'", emoji=LogEmojis.ERROR)
            return
            
        await self._subscribe_to_channel(user_id, "stream.online")
        await self._subscribe_to_channel(user_id, "stream.offline")
        await send_to_any_log("info", f"[Twitch-EventSub] Dynamically added real-time subscription for {login} (ID: {user_id})", emoji=LogEmojis.SUCCESS)

    async def _resolve_user_ids(self, logins: List[str]) -> Dict[str, str]:
        """Пакетно запрашивает Twitch Helix API для получения внутренних user ID по логинам."""
        if not logins:
            return {}
        
        token = await self._get_token()
        if not token:
            return {}
            
        from modules_utils.http_client import HttpClient
        url = "https://api.twitch.tv/helix/users"
        resolved = {}
        
        # Twitch разрешает максимум 100 логинов за раз
        for i in range(0, len(logins), 100):
            chunk = logins[i:i+100]
            params = [("login", login) for login in chunk]
            headers = {
                "Client-ID": self.client_id,
                "Authorization": f"Bearer {token}"
            }
            try:
                data = await HttpClient.get(url, params=params, headers=headers)
                if data and isinstance(data, dict):
                    users = data.get("data", [])
                    for user in users:
                        login = user.get("login").lower()
                        uid = str(user.get("id"))
                        resolved[login] = uid
            except Exception as e:
                await send_to_any_log("error", f"[Twitch-EventSub] Helix users API error for {chunk}: {e}", emoji=LogEmojis.ERROR)
        return resolved

    async def _get_token(self) -> Optional[str]:
        """Получает и сохраняет App Access token."""
        if self._token:
            return self._token
            
        from modules_utils.http_client import HttpClient
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        max_retries = Config.TWITCH_EVENTSUB_MAX_RETRIES
        for attempt in range(1, max_retries + 1):
            try:
                data = await HttpClient.post(url, params=params)
                if data and isinstance(data, dict):
                    self._token = data.get("access_token")
                    if self._token:
                        return self._token
            except Exception as e:
                await send_to_any_log("error", f"[Twitch-EventSub] Error obtaining OAuth token (attempt {attempt}/{max_retries}): {e}", emoji=LogEmojis.ERROR)
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
        await send_to_any_log("error", f"[Twitch-EventSub] Failed to obtain OAuth token after {max_retries} attempts", emoji=LogEmojis.ERROR)
        return None

    async def _subscribe_to_channel(self, user_id: str, event_type: str) -> bool:
        """Регистрирует подписку на определенный тип событий на сессию WebSocket."""
        max_retries = Config.TWITCH_EVENTSUB_MAX_RETRIES
        for attempt in range(1, max_retries + 1):
            token = await self._get_token()
            if not token or not self._session_id:
                return False

            from modules_utils.http_client import HttpClient
            url = "https://api.twitch.tv/helix/eventsub/subscriptions"
            headers = {
                "Client-ID": self.client_id,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            payload = {
                "type": event_type,
                "version": "1",
                "condition": {
                    "broadcaster_user_id": user_id
                },
                "transport": {
                    "method": "websocket",
                    "session_id": self._session_id
                }
            }
            try:
                res = await HttpClient.post(url, json=payload, headers=headers)
                # HttpClient возвращает None при 4xx/5xx
                if res is not None:
                    return True
                await send_to_any_log("warning",
                    f"[Twitch-EventSub] Failed to create {event_type} subscription for {user_id} (attempt {attempt}/{max_retries})",
                    emoji=LogEmojis.WARNING)
            except Exception as e:
                await send_to_any_log("error",
                    f"[Twitch-EventSub] Exception creating {event_type} subscription for ID {user_id} (attempt {attempt}/{max_retries}): {e}",
                    emoji=LogEmojis.ERROR)
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
        return False
