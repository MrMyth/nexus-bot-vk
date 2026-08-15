# vk_wall/database_wall.py
import asyncio
import aiosqlite
import os
from typing import Optional
from settings.config import Config
from settings.data_files import Files
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis

def get_db_path() -> str:
    """Возвращает актуальный путь к базе данных."""
    return Files.DATABASE_FILE

# ─── Общее соединение с БД ───────────────────────────────────────────────────
# Вместо открытия нового соединения на каждый запрос используем одно постоянное
# соединение с asyncio.Lock для сериализации записей.
# Правило: _reset_conn_unsafe() вызывать ТОЛЬКО под _get_lock()!

_conn: Optional[aiosqlite.Connection] = None
_conn_loop: Optional[asyncio.AbstractEventLoop] = None
_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _lock
    # asyncio.Lock привязывается к event loop-у при первом использовании. Если бот
    # пересоздаёт event loop (например, после auto-restart без полного перезапуска
    # процесса), старый лок остаётся привязан к уже закрытому loop-у, и любая
    # попытка взять его в новом loop-е падает с
    # "RuntimeError: ... is bound to a different event loop". Поэтому пересоздаём
    # лок, если текущий running loop отличается от того, к которому он привязан
    # (тот же паттерн, что и в HttpClient.get_session / DiscordLogger._get_lock).
    loop = asyncio.get_running_loop()
    if _lock is None or getattr(_lock, "_loop", None) is not loop:
        _lock = asyncio.Lock()
    return _lock


async def _get_conn() -> aiosqlite.Connection:
    """Возвращает общее соединение. Вызывать только под _get_lock()!"""
    global _conn, _conn_loop
    loop = asyncio.get_running_loop()
    if _conn is not None and _conn_loop is not None and _conn_loop is not loop:
        # Соединение было открыто в другом (уже закрытом) event loop-е — например,
        # после пересоздания loop-а в рамках auto-restart без полного перезапуска
        # процесса. Использовать его в новом loop-е нельзя, поэтому пересоздаём.
        await _reset_conn_unsafe()

    if _conn is None:
        _conn = await aiosqlite.connect(get_db_path(), timeout=30)
        _conn_loop = loop
        await _conn.execute("PRAGMA journal_mode=WAL")
        await _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


async def _reset_conn_unsafe():
    """Закрывает и обнуляет соединение. Вызывать только под _get_lock()!"""
    global _conn, _conn_loop
    if _conn is not None:
        try:
            await _conn.close()
        except Exception as e:
            await send_to_any_log(
                "warning", f"Error closing posts DB connection: {e}",
                emoji=LogEmojis.WARNING
            )
        _conn = None
    _conn_loop = None


# ─── Инициализация ────────────────────────────────────────────────────────────

def _delete_db_files(db_path: str) -> None:
    """Удаляет файл БД и сопутствующие WAL/SHM файлы."""
    for suffix in ("", "-wal", "-shm"):
        path = db_path + suffix
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


async def _init_db_internal(db_path: str) -> None:
    """Создаёт соединение и инициализирует схему БД постов.

    Использует временное соединение для выполнения всей схемы, и только после
    успешного коммита присваивает его к глобальному _conn. Это гарантирует, что
    при ошибке (в т.ч. malformed) _conn не остаётся в частично открытом состоянии.
    """
    global _conn, _conn_loop
    tmp = await aiosqlite.connect(db_path, timeout=30)
    try:
        await tmp.execute("PRAGMA journal_mode=WAL")
        await tmp.execute("PRAGMA synchronous=NORMAL")
        await tmp.execute('''
            CREATE TABLE IF NOT EXISTS processed_posts (
                post_id INTEGER,
                group_id TEXT,
                text TEXT,
                attachments_hash TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (post_id, group_id)
            )
        ''')
        await tmp.execute(
            'CREATE INDEX IF NOT EXISTS idx_group_id ON processed_posts (group_id)'
        )
        await tmp.execute(
            'CREATE INDEX IF NOT EXISTS idx_timestamp ON processed_posts (timestamp)'
        )
        await tmp.commit()
    except Exception:
        try:
            await tmp.close()
        except Exception:
            pass
        raise
    _conn = tmp
    _conn_loop = asyncio.get_running_loop()


async def init_db():
    """Инициализирует базу данных для постов и открывает общее соединение."""
    global _conn, _conn_loop
    db_path = get_db_path()
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        async with _get_lock():
            # Безопасно закрываем предыдущее соединение если оно уже открыто
            if _conn is not None:
                try:
                    await _conn.close()
                except Exception:
                    pass
                _conn = None
                _conn_loop = None

            try:
                await _init_db_internal(db_path)
            except Exception as e:
                if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
                    await send_to_any_log(
                        "warning",
                        f"{LogEmojis.WARNING} Posts DB corruption detected ({db_path}). Recreating DB...",
                        emoji=LogEmojis.WARNING
                    )
                    _delete_db_files(db_path)
                    await _init_db_internal(db_path)
                else:
                    raise

        await send_to_any_log(
            "info", f"Posts database initialized: {db_path}",
            emoji=LogEmojis.DATABASE
        )
    except Exception as e:
        await send_to_any_log(
            "critical", f"Critical error initializing posts database: {e}",
            emoji=LogEmojis.CRITICAL
        )
        raise


# ─── Операции с постами ───────────────────────────────────────────────────────

async def update_post_timestamp(post_id: int, group_id: str):
    """Обновляет временную метку поста, чтобы он не был удалён при очистке."""
    try:
        async with _get_lock():
            try:
                conn = await _get_conn()
                await conn.execute(
                    "UPDATE processed_posts SET timestamp = datetime('now') "
                    "WHERE post_id = ? AND group_id = ?",
                    (post_id, group_id)
                )
                await conn.commit()
            except Exception as e:
                await _reset_conn_unsafe()
                # Не критично для основного потока обработки, но оставляем след в логах
                await send_to_any_log(
                    "warning",
                    f"Failed to update timestamp for post {post_id} (group {group_id}): {e}",
                    emoji=LogEmojis.WARNING
                )
    except Exception as e:
        await send_to_any_log(
            "warning",
            f"Lock error when updating timestamp for post {post_id} (group {group_id}): {e}",
            emoji=LogEmojis.WARNING
        )


async def is_post_processed(post_id: int, group_id: str) -> bool:
    """Проверяет, был ли пост уже обработан."""
    try:
        async with _get_lock():
            try:
                conn = await _get_conn()
                cursor = await conn.execute(
                    "SELECT 1 FROM processed_posts WHERE post_id = ? AND group_id = ?",
                    (post_id, group_id)
                )
                row = await cursor.fetchone()
                return row is not None
            except Exception:
                await _reset_conn_unsafe()
                raise
    except Exception as e:
        await send_to_any_log(
            "error", f"Error checking post {post_id} (group {group_id}): {e}",
            emoji=LogEmojis.ERROR
        )
        return False


async def mark_post_as_processed(
    post_id: int,
    group_id: str,
    text: str = "",
    attachments: list = None,
    group_name: str = None,
) -> bool:
    """
    Отмечает пост как обработанный.
    Возвращает True, если пост новый, False — если обновлён.

    Использует INSERT OR IGNORE + UPDATE вместо предварительного SELECT:
    устраняет лишний round-trip к SQLite для новых постов.
    """
    from modules.vk_wall.hash_utils import get_attachments_hash, normalize_text
    attachments_hash = get_attachments_hash(attachments)
    normalized_text = normalize_text(text)
    try:
        async with _get_lock():
            try:
                conn = await _get_conn()

                # Пытаемся вставить. Если запись уже есть — IGNORE (rowcount=0).
                cursor = await conn.execute(
                    '''INSERT OR IGNORE INTO processed_posts
                       (post_id, group_id, text, attachments_hash, timestamp)
                       VALUES (?, ?, ?, ?, datetime('now'))''',
                    (post_id, group_id, normalized_text, attachments_hash)
                )
                is_new = cursor.rowcount == 1

                if not is_new:
                    # Обновляем существующую запись
                    await conn.execute(
                        '''UPDATE processed_posts
                           SET text = ?, attachments_hash = ?, timestamp = datetime('now')
                           WHERE post_id = ? AND group_id = ?''',
                        (normalized_text, attachments_hash, post_id, group_id)
                    )

                await conn.commit()
            except Exception:
                await _reset_conn_unsafe()
                raise

        action = "New" if is_new else "Updated"
        name_info = f"'{group_name}' ({group_id})" if group_name else group_id
        await send_to_any_log(
            "info", f"{action} post {post_id} saved to DB (group {name_info})",
            emoji=LogEmojis.PROCESSED
        )
        return is_new
    except Exception as e:
        await send_to_any_log(
            "error", f"Error saving post {post_id}: {e}",
            emoji=LogEmojis.ERROR
        )
        return False


async def get_processed_post(post_id: int, group_id: str) -> dict | None:
    """Возвращает сохранённый текст и хеш вложений поста."""
    try:
        async with _get_lock():
            try:
                conn = await _get_conn()
                cursor = await conn.execute(
                    "SELECT text, attachments_hash FROM processed_posts "
                    "WHERE post_id = ? AND group_id = ?",
                    (post_id, group_id)
                )
                row = await cursor.fetchone()
                if row:
                    return {
                        "text": row[0] if row[0] is not None else "",
                        "attachments_hash": row[1] if row[1] is not None else "",
                    }
                return None
            except Exception:
                await _reset_conn_unsafe()
                raise
    except Exception as e:
        await send_to_any_log(
            "error", f"Error getting post data for {post_id}: {e}",
            emoji=LogEmojis.ERROR
        )
        return None


async def cleanup_old_posts():
    """Очищает старые записи из базы данных постов."""
    try:
        async with _get_lock():
            try:
                conn = await _get_conn()
                cursor = await conn.execute(
                    "DELETE FROM processed_posts WHERE timestamp < datetime('now', ?)",
                    (f"-{Config.RETENTION_DAYS} days",)
                )
                deleted_count = cursor.rowcount
                await conn.commit()
                # VACUUM нельзя выполнять внутри транзакции — выполняем отдельно
                await conn.execute("VACUUM")
            except Exception:
                await _reset_conn_unsafe()
                raise

        if deleted_count > 0:
            await send_to_any_log(
                "info",
                f"Cleaned up {deleted_count} old post records "
                f"(older than {Config.RETENTION_DAYS} days) and executed VACUUM",
                emoji=LogEmojis.CLEANUP
            )
    except Exception as e:
        await send_to_any_log(
            "error", f"Error cleaning up old posts: {e}", emoji=LogEmojis.ERROR
        )


async def get_post_counts() -> dict:
    """Возвращает число постов за последние 24 часа и 7 дней."""
    try:
        async with _get_lock():
            try:
                conn = await _get_conn()
                cursor_24h = await conn.execute(
                    "SELECT COUNT(*) FROM processed_posts "
                    "WHERE timestamp >= datetime('now', '-1 day')"
                )
                count_24h = (await cursor_24h.fetchone())[0]

                cursor_7d = await conn.execute(
                    "SELECT COUNT(*) FROM processed_posts "
                    "WHERE timestamp >= datetime('now', '-7 days')"
                )
                count_7d = (await cursor_7d.fetchone())[0]
            except Exception:
                await _reset_conn_unsafe()
                raise

        return {"24h": count_24h, "7d": count_7d}
    except Exception as e:
        await send_to_any_log("error", f"DB: Error getting post stats: {e}", emoji=LogEmojis.ERROR)
        return {"24h": 0, "7d": 0}


async def get_latest_post_timestamp(group_id: str) -> float | None:
    """Возвращает временную метку последнего опубликованного поста для группы."""
    import datetime
    try:
        async with _get_lock():
            try:
                conn = await _get_conn()
                cursor = await conn.execute(
                    "SELECT max(timestamp) FROM processed_posts WHERE group_id = ?",
                    (group_id,)
                )
                row = await cursor.fetchone()
            except Exception:
                await _reset_conn_unsafe()
                raise

        if row and row[0]:
            raw = row[0].split(".")[0]  # убираем миллисекунды если есть
            try:
                dt = datetime.datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
                return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
            except ValueError:
                await send_to_any_log("warning", f"DB: Unknown date format: {row[0]}", emoji=LogEmojis.WARNING)
    except Exception as e:
        await send_to_any_log("error", f"DB: Error getting latest post time for group {group_id}: {e}", emoji=LogEmojis.ERROR)
    return None
