import aiohttp
import asyncio
import json
import re
from typing import Optional, Union, Dict, Any
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis

# Паттерн для маскировки токенов в строках ошибок (access_token=<значение>)
_TOKEN_PATTERN = re.compile(r'(access_token=)[^\s&"\']+', re.IGNORECASE)


def _sanitize_err(msg: str) -> str:
    """Убирает значения токенов из строки ошибки перед логированием."""
    return _TOKEN_PATTERN.sub(r'\1***', msg)

class HttpClient:
    _session: Optional[aiohttp.ClientSession] = None
    _session_lock: Optional[asyncio.Lock] = None

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        """Возвращает глобальную сессию aiohttp (thread-safe инициализация)."""
        loop = asyncio.get_running_loop()
        if cls._session_lock is None or getattr(cls._session_lock, "_loop", None) is not loop:
            cls._session_lock = asyncio.Lock()
            
        async with cls._session_lock:
            if cls._session is not None:
                # Проверяем, совпадает ли loop у сессии с текущим запущенным loop-ом
                session_loop = getattr(cls._session, "_loop", None)
                if session_loop is None or session_loop.is_closed() or session_loop is not loop:
                    try:
                        await cls._session.close()
                    except Exception:
                        pass
                    cls._session = None

            if cls._session is None or cls._session.closed:
                from settings.config import Config
                import socket
                import ssl
                timeout = aiohttp.ClientTimeout(
                    total=Config.HTTP_TIMEOUT_TOTAL,
                    connect=Config.HTTP_TIMEOUT_CONNECT
                )
                
                # Настройка SSL в зависимости от конфигурации
                verify_ssl = getattr(Config, "HTTP_VERIFY_SSL", True)
                
                connector_kwargs = {
                    "family": socket.AF_INET,
                    "ttl_dns_cache": 300
                }
                
                if not verify_ssl:
                    connector_kwargs["ssl"] = False
                else:
                     try:
                         import certifi
                         connector_kwargs["ssl"] = ssl.create_default_context(cafile=certifi.where())
                     except Exception:
                         pass
                         
                connector = aiohttp.TCPConnector(**connector_kwargs)
                cls._session = aiohttp.ClientSession(timeout=timeout, connector=connector, trust_env=True)
        return cls._session

    @classmethod
    async def close_session(cls):
        """Закрывает глобальную сессию."""
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None

    @classmethod
    async def request(
        cls, 
        method: str, 
        url: str, 
        max_retries: int = 3, 
        backoff_factor: float = 1.5,
        **kwargs
    ) -> Optional[Union[Dict[str, Any], str]]:
        """Универсальный метод выполнения запроса с повторами."""
        session = await cls.get_session()
        
        error_level = kwargs.pop("error_level", "error")
        suppress_errors = kwargs.pop("suppress_errors", False)
        
        emoji_map = {
            "error": LogEmojis.ERROR,
            "warning": LogEmojis.WARNING,
            "info": LogEmojis.INFO,
            "success": LogEmojis.SUCCESS
        }
        err_emoji = emoji_map.get(error_level, LogEmojis.ERROR)
        
        # Маскируем чувствительные или длинные url для логирования
        display_url = url
        if "lp.vk.ru" in url or "lp.vk.com" in url:
            display_url = "https://lp.vk.ru/whp/..."
        elif "api.telegram.org/bot" in url:
            # Токен Telegram-бота передаётся прямо в пути URL (.../bot<token>/method)
            display_url = re.sub(r'(api\.telegram\.org/bot)[^/]+', r'\1***', url)
        elif "access_token" in url:
            # Токен в самом URL (query-string)
            display_url = url.split("?")[0] + "?access_token=***"
        else:
            # Токен передан через params= (aiohttp строит URL внутри).
            # Маскируем display_url превентивно, чтобы он не попал в str(e) при сетевой ошибке.
            _params = kwargs.get("params")
            if isinstance(_params, dict) and "access_token" in _params:
                display_url = url + "?[params_masked]"
            
        try:
            max_retries = int(max_retries)
        except (ValueError, TypeError):
            max_retries = 3

        for attempt in range(max_retries):
            try:
                # В kwargs могут быть params, headers, json, data, timeout и т.д.
                req_headers = kwargs.get("headers", {})
                if req_headers is None:
                    req_headers = {}
                else:
                    req_headers = dict(req_headers)
                
                # Добавляем браузерные заголовки для обычных запросов (не Discord/Telegram API), чтобы избежать 403/429
                if "discord.com" not in url and "telegram.org" not in url:
                    if "User-Agent" not in req_headers:
                        req_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    if "Accept-Language" not in req_headers:
                        req_headers["Accept-Language"] = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
                
                kwargs["headers"] = req_headers
                
                async with session.request(method, url, **kwargs) as response:
                    # Обработка лимитов
                    if response.status == 429:
                        delay = backoff_factor ** attempt
                        if not suppress_errors:
                            await send_to_any_log("warning", f"HTTP 429 ({display_url}). Попытка {attempt+1}/{max_retries}. Ждем {delay:.1f}с", emoji=LogEmojis.WARNING)
                        await asyncio.sleep(delay)
                        continue
                    
                    # Обработка серверных ошибок (5xx)
                    if response.status >= 500:
                        delay = backoff_factor ** (attempt + 1)
                        if not suppress_errors:
                            await send_to_any_log("warning", f"HTTP {response.status} ({display_url}). Попытка {attempt+1}/{max_retries}. Ждем {delay:.1f}с", emoji=LogEmojis.WARNING)
                        await asyncio.sleep(delay)
                        continue

                    # Успех
                    if 200 <= response.status < 300:
                        content_type = response.headers.get("Content-Type", "").lower()
                        text = await response.text()
                        
                        # Если заголовок говорит, что это JSON, или если текст выглядит как JSON объект/массив
                        if "application/json" in content_type:
                            try:
                                return json.loads(text)
                            except Exception:
                                pass
                        
                        # Попытка разобрать любой текст как JSON для максимальной отказоустойчивости (robustness principle)
                        stripped_text = text.strip()
                        if (stripped_text.startswith("{") and stripped_text.endswith("}")) or (stripped_text.startswith("[") and stripped_text.endswith("]")):
                            try:
                                return json.loads(stripped_text)
                            except Exception:
                                pass
                                
                        return text
                    
                    # Другие ошибки (4xx кроме 429) - обычно не ретраим
                    if not suppress_errors:
                        await send_to_any_log(error_level, f"HTTP {response.status} (неудача): {display_url}", emoji=err_emoji)
                    return None

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < max_retries - 1:
                    delay = backoff_factor ** attempt
                    await asyncio.sleep(delay)
                    continue
                raw = str(e) if str(e) else ("TimeoutError" if isinstance(e, asyncio.TimeoutError) else "Connection/ClientError")
                err_msg = _sanitize_err(raw)
                if not suppress_errors:
                    await send_to_any_log(error_level, f"HTTP Request Error ({display_url}): {err_msg}", emoji=err_emoji, exc_info=False)
            except Exception as e:
                raw = str(e) if str(e) else "Unknown critical exception"
                err_msg = _sanitize_err(raw)
                if not suppress_errors:
                    await send_to_any_log(error_level, f"HTTP Critical Error ({display_url}): {err_msg}", emoji=err_emoji)
                break
        
        return None

    @classmethod
    async def get(cls, url: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> Optional[Any]:
        """GET запрос."""
        return await cls.request("GET", url, params=params, **kwargs)

    @classmethod
    async def post(cls, url: str, data: Optional[Any] = None, json: Optional[Dict[str, Any]] = None, **kwargs) -> Optional[Any]:
        """POST запрос."""
        return await cls.request("POST", url, data=data, json=json, **kwargs)
