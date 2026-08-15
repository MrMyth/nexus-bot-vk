# modules_utils/cache_utils.py
import json
import os
import asyncio
from typing import Dict, Any
from settings.config import Config
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from modules_utils.helpers import safe_create_task

# Каждый лок хранится вместе с event loop-ом, к которому он был привязан при
# создании. asyncio.Lock привязывается к running loop-у при первом использовании,
# и если бот пересоздаёт loop (например, auto-restart без полного перезапуска
# процесса), старые локи из этого словаря останутся привязаны к уже закрытому
# loop-у и упадут с "bound to a different event loop" — тем же багом, что был
# исправлен в modules/vk_wall/database_wall.py.
_locks: Dict[str, "tuple[asyncio.Lock, asyncio.AbstractEventLoop]"] = {}


def get_file_lock(filepath: str) -> asyncio.Lock:
    abs_path = os.path.abspath(filepath)
    loop = asyncio.get_running_loop()
    entry = _locks.get(abs_path)
    if entry is None or entry[1] is not loop:
        lock = asyncio.Lock()
        _locks[abs_path] = (lock, loop)
        return lock
    return entry[0]


def load_json_cache(cache_file: str) -> Dict[str, Any]:
    """Загружает кэш из JSON-файла (синхронная версия)."""
    if not os.path.exists(cache_file):
        return {}
    try:
        with open(cache_file, "r", encoding=Config.LOG_FILE_ENCODING) as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        safe_create_task(send_to_any_log("error", f"CACHE: Ошибка чтения {cache_file}: {e}", emoji=LogEmojis.ERROR))
        return {}


def save_json_cache(cache_file: str, cache: Dict[str, Any]) -> None:
    """Сохраняет кэш в JSON-файл атомарно через временный файл (синхронная версия)."""
    try:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        temp_file = cache_file + ".tmp"
        with open(temp_file, "w", encoding=Config.LOG_FILE_ENCODING) as f:
            json.dump(
                cache,
                f,
                ensure_ascii=Config.JSON_ENSURE_ASCII,
                indent=Config.JSON_INDENT
            )
        os.replace(temp_file, cache_file)
    except Exception as e:
        safe_create_task(send_to_any_log("error", f"CACHE: Ошибка записи {cache_file}: {e}", emoji=LogEmojis.ERROR))


async def load_json_cache_async(cache_file: str) -> Dict[str, Any]:
    """Асинхронно и безопасно (с Lock) загружает кэш из JSON-файла."""
    lock = get_file_lock(cache_file)
    async with lock:
        if not os.path.exists(cache_file):
            return {}
        try:
            loop = asyncio.get_running_loop()
            def _read():
                with open(cache_file, "r", encoding=Config.LOG_FILE_ENCODING) as f:
                    return json.load(f)
            data = await loop.run_in_executor(None, _read)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            await send_to_any_log("error", f"CACHE: Ошибка чтения {cache_file}: {e}", emoji=LogEmojis.ERROR)
            return {}


async def save_json_cache_async(cache_file: str, cache: Any) -> None:
    """Асинхронно и безопасно (с Lock) сохраняет кэш в JSON-файл атомарно."""
    lock = get_file_lock(cache_file)
    async with lock:
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            loop = asyncio.get_running_loop()
            def _write():
                temp_file = cache_file + ".tmp"
                with open(temp_file, "w", encoding=Config.LOG_FILE_ENCODING) as f:
                    json.dump(
                        cache,
                        f,
                        ensure_ascii=Config.JSON_ENSURE_ASCII,
                        indent=Config.JSON_INDENT
                    )
                os.replace(temp_file, cache_file)
            await loop.run_in_executor(None, _write)
        except Exception as e:
            await send_to_any_log("error", f"CACHE: Ошибка записи {cache_file}: {e}", emoji=LogEmojis.ERROR)
