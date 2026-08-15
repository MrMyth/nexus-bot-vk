# modules_utils/generic_stream_database.py
import re
import os
import aiosqlite
from typing import List, Optional
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis

_SAFE_TABLE_NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')

class GenericStreamDatabase:
    """Универсальный класс для работы с БД стримов разных платформ."""

    def __init__(self, db_path: str, table_name: str):
        # Защита от SQL-инъекций через имя таблицы:
        # разрешены только латинские буквы, цифры и '_', начиная с буквы.
        if not _SAFE_TABLE_NAME_RE.match(table_name):
            raise ValueError(
                f"Недопустимое имя таблицы БД: {table_name!r}. "
                "Разрешены только латинские буквы, цифры и '_', начиная с буквы."
            )
        self.db_path = db_path
        self.table_name = table_name

    def _delete_db_files(self):
        """Удаляет файлы БД и связанные с WAL-режимом файлы при повреждении."""
        for suffix in ["", "-wal", "-shm"]:
            path = self.db_path + suffix
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    async def init_db(self):
        """Инициализирует таблицу в БД."""
        try:
            await self._init_db_internal()
        except Exception as e:
            if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
                await send_to_any_log("warning", f"{LogEmojis.WARNING} Обнаружено повреждение БД при инициализации ({self.table_name}) [Путь: {self.db_path}]. Пересоздаём БД...", emoji=LogEmojis.WARNING)
                self._delete_db_files()
                try:
                    await self._init_db_internal()
                except Exception as retry_err:
                    await send_to_any_log("error", f"Критическая ошибка после пересоздания БД при инициализации ({self.table_name}): {retry_err}", emoji=LogEmojis.ERROR)
            else:
                await send_to_any_log("error", f"Ошибка инициализации БД ({self.table_name}) [Путь: {self.db_path}]: {e}", emoji=LogEmojis.ERROR)

    async def _init_db_internal(self):
        async with aiosqlite.connect(self.db_path, timeout=20.0) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute(f'''
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    stream_id TEXT PRIMARY KEY,
                    platform_id TEXT,
                    event_id TEXT,
                    is_finished INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_platform_id ON {self.table_name} (platform_id)")
            await db.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_is_finished ON {self.table_name} (is_finished)")
            await db.commit()

    async def get_active_stream_ids(self, platform_id: str) -> List[str]:
        """Получает список ID активных стримов для платформы."""
        try:
            return await self._get_active_stream_ids_internal(platform_id)
        except Exception as e:
            if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
                await send_to_any_log("warning", f"{LogEmojis.WARNING} Обнаружено повреждение БД ({self.table_name}) [Путь: {self.db_path}]. Пересоздаём БД...", emoji=LogEmojis.WARNING)
                self._delete_db_files()
                await self.init_db()
                try:
                    return await self._get_active_stream_ids_internal(platform_id)
                except Exception as retry_err:
                    await send_to_any_log("error", f"Ошибка после пересоздания БД ({self.table_name}) в get_active_stream_ids: {retry_err}", emoji=LogEmojis.ERROR)
                    return []
            else:
                await send_to_any_log("error", f"Ошибка БД ({self.table_name}) [Путь: {self.db_path}]: {e}", emoji=LogEmojis.ERROR)
                return []

    async def _get_active_stream_ids_internal(self, platform_id: str) -> List[str]:
        async with aiosqlite.connect(self.db_path, timeout=20.0) as db:
            async with db.execute(
                f"SELECT stream_id FROM {self.table_name} WHERE platform_id = ? AND is_finished = 0",
                (str(platform_id),)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows] if rows else []

    async def save_stream(self, stream_id: str, platform_id: str, event_id: Optional[str] = None):
        """Сохраняет новый активный стрим."""
        try:
            await self._save_stream_internal(stream_id, platform_id, event_id)
        except Exception as e:
            if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
                await send_to_any_log("warning", f"{LogEmojis.WARNING} Обнаружено повреждение БД ({self.table_name}) [Путь: {self.db_path}]. Пересоздаём БД...", emoji=LogEmojis.WARNING)
                self._delete_db_files()
                await self.init_db()
                try:
                    await self._save_stream_internal(stream_id, platform_id, event_id)
                except Exception as retry_err:
                    await send_to_any_log("error", f"Ошибка после пересоздания БД ({self.table_name}) в save_stream: {retry_err}", emoji=LogEmojis.ERROR)
            else:
                await send_to_any_log("error", f"Ошибка сохранения в БД ({self.table_name}) [Путь: {self.db_path}]: {e}", emoji=LogEmojis.ERROR)

    async def _save_stream_internal(self, stream_id: str, platform_id: str, event_id: Optional[str] = None):
        async with aiosqlite.connect(self.db_path, timeout=20.0) as db:
            await db.execute(
                f"INSERT OR REPLACE INTO {self.table_name} (stream_id, platform_id, event_id, is_finished) VALUES (?, ?, ?, 0)",
                (str(stream_id), str(platform_id), event_id)
            )
            await db.commit()

    async def mark_finished(self, stream_id: str):
        """Помечает стрим как завершенный."""
        try:
            await self._mark_finished_internal(stream_id)
        except Exception as e:
            if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
                await send_to_any_log("warning", f"{LogEmojis.WARNING} Обнаружено повреждение БД ({self.table_name}) [Путь: {self.db_path}]. Пересоздаём БД...", emoji=LogEmojis.WARNING)
                self._delete_db_files()
                await self.init_db()
                try:
                    await self._mark_finished_internal(stream_id)
                except Exception as retry_err:
                    await send_to_any_log("error", f"Ошибка после пересоздания БД ({self.table_name}) в mark_finished: {retry_err}", emoji=LogEmojis.ERROR)
            else:
                await send_to_any_log("error", f"Ошибка обновления БД ({self.table_name}) [Путь: {self.db_path}]: {e}", emoji=LogEmojis.ERROR)

    async def _mark_finished_internal(self, stream_id: str):
        async with aiosqlite.connect(self.db_path, timeout=20.0) as db:
            await db.execute(
                f"UPDATE {self.table_name} SET is_finished = 1, last_updated = CURRENT_TIMESTAMP WHERE stream_id = ?",
                (str(stream_id),)
            )
            await db.commit()

    async def get_event_id(self, stream_id: str) -> Optional[str]:
        """Получает ID мероприятия Discord для стрима."""
        try:
            return await self._get_event_id_internal(stream_id)
        except Exception as e:
            if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
                await send_to_any_log("warning", f"{LogEmojis.WARNING} Обнаружено повреждение БД ({self.table_name}) [Путь: {self.db_path}]. Пересоздаём БД...", emoji=LogEmojis.WARNING)
                self._delete_db_files()
                await self.init_db()
                try:
                    return await self._get_event_id_internal(stream_id)
                except Exception as retry_err:
                    await send_to_any_log("error", f"Ошибка после пересоздания БД ({self.table_name}) в get_event_id: {retry_err}", emoji=LogEmojis.ERROR)
                    return None
            else:
                await send_to_any_log("error", f"Ошибка получения event_id из БД ({self.table_name}) [Путь: {self.db_path}]: {e}", emoji=LogEmojis.ERROR)
                return None

    async def _get_event_id_internal(self, stream_id: str) -> Optional[str]:
        async with aiosqlite.connect(self.db_path, timeout=20.0) as db:
            async with db.execute(
                f"SELECT event_id FROM {self.table_name} WHERE stream_id = ? AND is_finished = 0",
                (str(stream_id),)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def cleanup(self, days: int = 30):
        """Удаляет старые завершенные записи."""
        try:
            await self._cleanup_internal(days)
        except Exception as e:
            if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
                await send_to_any_log("warning", f"{LogEmojis.WARNING} Обнаружено повреждение БД ({self.table_name}) [Путь: {self.db_path}]. Пересоздаём БД...", emoji=LogEmojis.WARNING)
                self._delete_db_files()
                await self.init_db()
                try:
                    await self._cleanup_internal(days)
                except Exception as retry_err:
                    await send_to_any_log("error", f"Ошибка после пересоздания БД ({self.table_name}) в cleanup: {retry_err}", emoji=LogEmojis.ERROR)
            else:
                await send_to_any_log("error", f"Ошибка очистки БД ({self.table_name}) [Путь: {self.db_path}]: {e}", emoji=LogEmojis.ERROR)

    async def _cleanup_internal(self, days: int = 30):
        async with aiosqlite.connect(self.db_path, timeout=20.0) as db:
            await db.execute(
                f"DELETE FROM {self.table_name} WHERE is_finished = 1 AND last_updated < datetime('now', ?)",
                (f'-{days} days',)
            )
            await db.commit()

    async def save_video(self, video_id: str, platform_id: str):
        """Сохраняет новое видео (сразу помеченное как завершенное)."""
        try:
            await self._save_video_internal(video_id, platform_id)
        except Exception as e:
            if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
                await send_to_any_log("warning", f"{LogEmojis.WARNING} Обнаружено повреждение БД ({self.table_name}) [Путь: {self.db_path}]. Пересоздаём БД...", emoji=LogEmojis.WARNING)
                self._delete_db_files()
                await self.init_db()
                try:
                    await self._save_video_internal(video_id, platform_id)
                except Exception as retry_err:
                    await send_to_any_log("error", f"Ошибка после пересоздания БД ({self.table_name}) в save_video: {retry_err}", emoji=LogEmojis.ERROR)
            else:
                await send_to_any_log("error", f"Ошибка сохранения видео в БД ({self.table_name}) [Путь: {self.db_path}]: {e}", emoji=LogEmojis.ERROR)

    async def _save_video_internal(self, video_id: str, platform_id: str):
        async with aiosqlite.connect(self.db_path, timeout=20.0) as db:
            await db.execute(
                f"INSERT OR REPLACE INTO {self.table_name} (stream_id, platform_id, event_id, is_finished) VALUES (?, ?, ?, 1)",
                (str(video_id), str(platform_id), None)
            )
            await db.commit()

    async def get_all_processed_ids(self, platform_id: str) -> List[str]:
        """Получает список всех ID (активных и завершенных) для платформы."""
        try:
            return await self._get_all_processed_ids_internal(platform_id)
        except Exception as e:
            if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
                await send_to_any_log("warning", f"{LogEmojis.WARNING} Обнаружено повреждение БД ({self.table_name}) [Путь: {self.db_path}]. Пересоздаём БД...", emoji=LogEmojis.WARNING)
                self._delete_db_files()
                await self.init_db()
                try:
                    return await self._get_all_processed_ids_internal(platform_id)
                except Exception as retry_err:
                    await send_to_any_log("error", f"Ошибка после пересоздания БД ({self.table_name}) в get_all_processed_ids: {retry_err}", emoji=LogEmojis.ERROR)
                    return []
            else:
                await send_to_any_log("error", f"Ошибка БД ({self.table_name}) [Путь: {self.db_path}]: {e}", emoji=LogEmojis.ERROR)
                return []

    async def _get_all_processed_ids_internal(self, platform_id: str) -> List[str]:
        async with aiosqlite.connect(self.db_path, timeout=20.0) as db:
            async with db.execute(
                f"SELECT stream_id FROM {self.table_name} WHERE platform_id = ?",
                (str(platform_id),)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows] if rows else []

