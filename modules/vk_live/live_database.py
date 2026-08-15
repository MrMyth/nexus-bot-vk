# vk_live/live_database.py
import aiosqlite
import os
from settings.config import Config
from settings.data_files import Files
from log_system.logger_helper import send_to_any_log
from typing import Optional
from constants.emojis import LogEmojis, LiveEmojis

def _delete_live_db_files():
    for suffix in ["", "-wal", "-shm"]:
        path = Files.LIVE_DATABASE_FILE + suffix
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

async def init_live_db():
    try:
        await _init_live_db_internal()
    except Exception as e:
        if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
            await send_to_any_log("warning", f"{LogEmojis.WARNING} VK Live database corruption detected. Recreating DB...", emoji=LogEmojis.WARNING)
            _delete_live_db_files()
            try:
                await _init_live_db_internal()
            except Exception as retry_err:
                await send_to_any_log("error", f"Critical error after recreating VK Live database: {retry_err}", emoji=LogEmojis.ERROR)
        else:
            await send_to_any_log("error", f"Error initializing VK Live database: {e}", emoji=LogEmojis.ERROR)

async def _init_live_db_internal():
    async with aiosqlite.connect(Files.LIVE_DATABASE_FILE) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS active_streams (
                stream_id TEXT PRIMARY KEY,
                platform_id TEXT,
                start_time DATETIME,
                discord_event_id TEXT,
                is_finished BOOLEAN DEFAULT 0
            )
        ''')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_platform_id ON active_streams (platform_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_is_finished ON active_streams (is_finished)')
        await conn.commit()
    await send_to_any_log("info", f"VK Live database initialized: {Files.LIVE_DATABASE_FILE}", emoji=LogEmojis.DATABASE)


async def is_stream_active(stream_id: str) -> bool:
    try:
        return await _is_stream_active_internal(stream_id)
    except Exception as e:
        if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
            await send_to_any_log("warning", f"{LogEmojis.WARNING} DB corruption detected when checking stream activity. Recreating DB...", emoji=LogEmojis.WARNING)
            _delete_live_db_files()
            await init_live_db()
            try:
                return await _is_stream_active_internal(stream_id)
            except Exception as retry_err:
                await send_to_any_log("error", f"Error after recreating DB in is_stream_active: {retry_err}", emoji=LogEmojis.ERROR)
                return False
        else:
            await send_to_any_log("error", f"Error checking stream activity for '{stream_id}': {e}", emoji=LogEmojis.ERROR)
            return False

async def _is_stream_active_internal(stream_id: str) -> bool:
    async with aiosqlite.connect(Files.LIVE_DATABASE_FILE) as conn:
        cursor = await conn.execute(
            "SELECT 1 FROM active_streams WHERE stream_id = ? AND is_finished = 0",
            (stream_id,)
        )
        return (await cursor.fetchone()) is not None


async def save_stream(stream_id: str, platform_id: str, discord_event_id: str):
    try:
        await _save_stream_internal(stream_id, platform_id, discord_event_id)
    except Exception as e:
        if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
            await send_to_any_log("warning", f"{LogEmojis.WARNING} DB corruption detected when saving stream. Recreating DB...", emoji=LogEmojis.WARNING)
            _delete_live_db_files()
            await init_live_db()
            try:
                await _save_stream_internal(stream_id, platform_id, discord_event_id)
            except Exception as retry_err:
                await send_to_any_log("error", f"Error after recreating DB in save_stream: {retry_err}", emoji=LogEmojis.ERROR)
        else:
            await send_to_any_log("error", f"Error saving stream '{stream_id}': {e}", emoji=LogEmojis.ERROR)

async def _save_stream_internal(stream_id: str, platform_id: str, discord_event_id: str):
    async with aiosqlite.connect(Files.LIVE_DATABASE_FILE) as conn:
        await conn.execute('''
            INSERT OR REPLACE INTO active_streams (stream_id, platform_id, start_time, discord_event_id, is_finished)
            VALUES (?, ?, datetime('now'), ?, 0)
        ''', (stream_id, platform_id, discord_event_id))
        await conn.commit()
    await send_to_any_log("debug", f"Stream '{stream_id}' saved to DB", emoji=LogEmojis.SUCCESS)


async def mark_stream_finished(stream_id: str):
    try:
        await _mark_stream_finished_internal(stream_id)
    except Exception as e:
        if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
            await send_to_any_log("warning", f"{LogEmojis.WARNING} DB corruption detected when finishing stream. Recreating DB...", emoji=LogEmojis.WARNING)
            _delete_live_db_files()
            await init_live_db()
            try:
                await _mark_stream_finished_internal(stream_id)
            except Exception as retry_err:
                await send_to_any_log("error", f"Error after recreating DB in mark_stream_finished: {retry_err}", emoji=LogEmojis.ERROR)
        else:
            await send_to_any_log("error", f"Error finishing stream '{stream_id}': {e}", emoji=LogEmojis.ERROR)

async def _mark_stream_finished_internal(stream_id: str):
    async with aiosqlite.connect(Files.LIVE_DATABASE_FILE) as conn:
        await conn.execute(
            "UPDATE active_streams SET is_finished = 1 WHERE stream_id = ?",
            (stream_id,)
        )
        await conn.commit()
    await send_to_any_log("debug", f"Stream '{stream_id}' marked as finished", emoji=LiveEmojis.STREAM_END)


async def get_event_id_for_stream(stream_id: str) -> Optional[str]:
    try:
        return await _get_event_id_for_stream_internal(stream_id)
    except Exception as e:
        if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
            await send_to_any_log("warning", f"{LogEmojis.WARNING} DB corruption detected when getting event_id. Recreating DB...", emoji=LogEmojis.WARNING)
            _delete_live_db_files()
            await init_live_db()
            try:
                return await _get_event_id_for_stream_internal(stream_id)
            except Exception as retry_err:
                await send_to_any_log("error", f"Error after recreating DB in get_event_id_for_stream: {retry_err}", emoji=LogEmojis.ERROR)
                return None
        else:
            await send_to_any_log("error", f"Error getting event_id for stream '{stream_id}': {e}", emoji=LogEmojis.ERROR)
            return None

async def _get_event_id_for_stream_internal(stream_id: str) -> Optional[str]:
    async with aiosqlite.connect(Files.LIVE_DATABASE_FILE) as conn:
        cursor = await conn.execute(
            "SELECT discord_event_id FROM active_streams WHERE stream_id = ? AND is_finished = 0",
            (stream_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def cleanup_old_streams():
    try:
        await _cleanup_old_streams_internal()
    except Exception as e:
        if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
            await send_to_any_log("warning", f"{LogEmojis.WARNING} DB corruption detected when cleaning up streams. Recreating DB...", emoji=LogEmojis.WARNING)
            _delete_live_db_files()
            await init_live_db()
            try:
                await _cleanup_old_streams_internal()
            except Exception as retry_err:
                await send_to_any_log("error", f"Error after recreating DB in cleanup_old_streams: {retry_err}", emoji=LogEmojis.ERROR)
        else:
            await send_to_any_log("error", f"Error cleaning up old streams: {e}", emoji=LogEmojis.ERROR)

async def _cleanup_old_streams_internal():
    async with aiosqlite.connect(Files.LIVE_DATABASE_FILE) as conn:
        await conn.execute('''
            DELETE FROM active_streams 
            WHERE start_time < datetime('now', ?)
        ''', (f"-{Config.RETENTION_DAYS} days",))
        deleted_count = conn.total_changes
        await conn.commit()
        if deleted_count > 0:
            await send_to_any_log("info", f"Cleaned up {deleted_count} old stream records (older than {Config.RETENTION_DAYS} days)", emoji=LogEmojis.CLEANUP)