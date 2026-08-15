# modules/vk_assets/asset_database.py
import aiosqlite
import os
from settings.data_files import Files

async def init_assets_db():
    """Инициализирует базу данных для отслеживания ассетов ВК (фото, аудио, видео)."""
    db_path = Files.VK_ASSETS_DATABASE_FILE
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute('''
            CREATE TABLE IF NOT EXISTS processed_assets (
                asset_id TEXT PRIMARY KEY,
                asset_type TEXT,
                platform_id TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_platform_id ON processed_assets (platform_id)')
        await db.commit()

async def is_asset_processed(asset_id: str) -> bool:
    """Проверяет, был ли ассет уже обработан."""
    async with aiosqlite.connect(Files.VK_ASSETS_DATABASE_FILE) as db:
        async with db.execute(
            "SELECT 1 FROM processed_assets WHERE asset_id = ?",
            (asset_id,)
        ) as cursor:
            return await cursor.fetchone() is not None

async def mark_asset_processed(asset_id: str, asset_type: str, platform_id: str):
    """Помечает ассет как обработанный."""
    async with aiosqlite.connect(Files.VK_ASSETS_DATABASE_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO processed_assets (asset_id, asset_type, platform_id) VALUES (?, ?, ?)",
            (asset_id, asset_type, str(platform_id))
        )
        await db.commit()

async def cleanup_old_assets(days: int = 30):
    """Удаляет старые записи об ассетах."""
    async with aiosqlite.connect(Files.VK_ASSETS_DATABASE_FILE) as db:
        await db.execute(
            "DELETE FROM processed_assets WHERE processed_at < datetime('now', ?)",
            (f'-{days} days',)
        )
        await db.commit()
