# modules_utils/group_cache.py
import asyncio
import time
from typing import Optional, Any
from settings.data_files import Files
from modules_utils.cache_utils import load_json_cache, save_json_cache

# Глобальный кэш в оперативной памяти для избежания повторного чтения диска
_cache_in_memory: Optional[dict] = None

# TTL (секунды) по namespace:
#   "avatar"  — аватары обновляются, кэшируем на 24 часа
#   "group"   — ID групп стабильны, кэшируем на 7 дней
#   default   — 24 часа
_TTL_BY_NAMESPACE: dict = {
    "avatar": 86400,       # 24 ч
    "group":  604800,      # 7 дней
}
_DEFAULT_TTL = 86400  # 24 ч


def _namespace_ttl(namespace: str) -> int:
    return _TTL_BY_NAMESPACE.get(namespace, _DEFAULT_TTL)


def _load_cache() -> dict:
    global _cache_in_memory
    if _cache_in_memory is None:
        _cache_in_memory = load_json_cache(Files.CACHE_FILE)
    return _cache_in_memory


def _save_cache(cache: dict) -> None:
    global _cache_in_memory
    _cache_in_memory = cache
    save_json_cache(Files.CACHE_FILE, cache)


def get_cached_id(screen_name: Any, namespace: str = "group") -> Optional[Any]:
    if screen_name is None:
        return None
    key = f"{namespace}:{str(screen_name).strip().lower()}"
    cache = _load_cache()
    entry = cache.get(key)
    if entry is None:
        return None

    # Поддержка как новых записей {value, ts}, так и старых (plain value)
    if isinstance(entry, dict) and "value" in entry and "ts" in entry:
        ttl = _namespace_ttl(namespace)
        if time.time() - entry["ts"] > ttl:
            # Запись устарела — удаляем и возвращаем None
            del cache[key]
            _save_cache(cache)
            return None
        return entry["value"]

    # Старый формат (plain value без TTL) — мигрируем при следующей записи
    return entry


def cache_id(screen_name: Any, value: Any, namespace: str = "group") -> None:
    if screen_name is None:
        return
    key = f"{namespace}:{str(screen_name).strip().lower()}"
    cache = _load_cache()
    cache[key] = {"value": value, "ts": time.time()}
    _save_cache(cache)


def purge_expired() -> int:
    """Удаляет все устаревшие записи из in-memory кэша и сохраняет на диск.
    Возвращает количество удалённых записей."""
    cache = _load_cache()
    now = time.time()
    stale = [
        k for k, v in cache.items()
        if isinstance(v, dict) and "ts" in v
        and now - v["ts"] > _namespace_ttl(k.split(":", 1)[0] if ":" in k else "")
    ]
    if stale:
        for k in stale:
            del cache[k]
        _save_cache(cache)
    return len(stale)


async def _cleanup_loop() -> None:
    """Фоновый цикл: раз в час запускает purge_expired()."""
    while True:
        await asyncio.sleep(3600)
        removed = purge_expired()
        if removed:
            try:
                from log_system.logger_helper import send_to_any_log
                from constants.emojis import LogEmojis
                await send_to_any_log(
                    "debug",
                    f"[GroupCache] Периодическая очистка: удалено {removed} устаревших записей",
                    emoji=LogEmojis.DEBUG,
                    targets=["console", "file"],
                )
            except Exception:
                pass


def start_periodic_cleanup() -> None:
    """Запускает фоновый цикл очистки кэша (раз в час).
    Вызывать один раз при старте бота после запуска event loop."""
    from modules_utils.helpers import safe_create_task
    safe_create_task(_cleanup_loop())
