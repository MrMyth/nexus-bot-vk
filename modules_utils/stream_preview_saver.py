# modules_utils/stream_preview_saver.py
import os
import re
import time
import hashlib
from urllib.parse import urlparse
from typing import Optional

from settings.data_files import Files
from settings.config import Config
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from modules_utils.helpers import safe_create_task

_last_cleanup_time: float = 0.0

def cleanup_old_stream_previews(max_age_days: Optional[int] = None) -> int:
    """Удаляет локально сохраненные превью стримов, старше указанного количества дней.
    
    Args:
        max_age_days: Количество дней хранения (по умолчанию из Config.SAVE_STREAM_PREVIEW_RETENTION_DAYS, 365)
        
    Returns:
        int: Количество удаленных файлов
    """
    global _last_cleanup_time
    now = time.time()
    
    # Не запускаем очистку чаще одного раза в час
    if now - _last_cleanup_time < 3600:
        return 0
        
    _last_cleanup_time = now
    
    if max_age_days is None:
        max_age_days = getattr(Config, "SAVE_STREAM_PREVIEW_RETENTION_DAYS", 365)
        
    folder = Files.SAVE_STREAM_PREVIEW_FOLDER
    if not os.path.exists(folder) or not os.path.isdir(folder):
        return 0
        
    max_age_sec = max_age_days * 86400
    removed_count = 0
    
    try:
        for fname in os.listdir(folder):
            fpath = os.path.join(folder, fname)
            if os.path.isfile(fpath):
                try:
                    file_age = now - os.path.getmtime(fpath)
                    if file_age > max_age_sec:
                        os.remove(fpath)
                        removed_count += 1
                except Exception:
                    pass
        if removed_count > 0:
            safe_create_task(send_to_any_log("info", f"StreamPreview: очищено {removed_count} устаревших превью (старше {max_age_days} дн.)", emoji=LogEmojis.INFO))
    except Exception as e:
        safe_create_task(send_to_any_log("error", f"StreamPreview: ошибка при очистке устаревших превью: {e}", emoji=LogEmojis.ERROR))
        
    return removed_count


async def save_stream_preview_image(
    url: Optional[str], 
    stream_id: Optional[str] = None, 
    platform: Optional[str] = None
) -> Optional[str]:
    """Скачивает внешнее превью стрима и сохраняет его локально в папку save_stream_preview.
    
    Если URL уже является локальным файлом или отсуствует, возвращается исходное значение.
    Если скачивание не удалось, возвращается исходный URL в качестве фолбэка.
    
    Args:
        url: Исходный URL или путь к превью
        stream_id: Идентификатор стрима или канала
        platform: Название платформы (Twitch, VK Live, YouTube, Rutube и т.д.)
        
    Returns:
        Optional[str]: Локальный путь к сохраненному превью (или исходный URL при сбое)
    """
    if not url or not isinstance(url, str):
        return url
        
    clean_url = url.strip()
    
    # Если это локальный файл, data URI или attachment:// - не скачиваем
    if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        return clean_url
        
    # Гарантируем существование директории
    save_folder = Files.SAVE_STREAM_PREVIEW_FOLDER
    os.makedirs(save_folder, exist_ok=True)
    
    # Извлекаем расширение из URL
    parsed = urlparse(clean_url)
    ext = os.path.splitext(parsed.path)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        ext = ".jpg"
        
    # Формируем имя файла
    clean_plat = re.sub(r'[^\w\-]', '_', str(platform or 'stream')).strip('_').lower()
    clean_sid = re.sub(r'[^\w\-]', '_', str(stream_id or 'live')).strip('_').lower()
    url_hash = hashlib.md5(clean_url.encode('utf-8')).hexdigest()[:10]
    
    filename = f"preview_{clean_plat}_{clean_sid}_{url_hash}{ext}"
    target_path = os.path.join(save_folder, filename)
    
    # Если файл уже скачан и имеет ненулевой размер, возвращаем локальный путь
    if os.path.isfile(target_path) and os.path.getsize(target_path) > 0:
        cleanup_old_stream_previews()
        return target_path
        
    # Скачиваем файл через HttpClient
    try:
        from modules_utils.http_client import HttpClient
        session = await HttpClient.get_session()
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        async with session.get(clean_url, headers=headers) as resp:
            if resp.status == 200:
                content = await resp.read()
                if content and len(content) > 0:
                    with open(target_path, "wb") as f:
                        f.write(content)
                    await send_to_any_log(
                        "debug", 
                        f"[Stream Preview] Сохранена локальная копия превью: {filename} ({len(content)} байт)", 
                        emoji=LogEmojis.SUCCESS
                    )
                    cleanup_old_stream_previews()
                    return target_path
            await send_to_any_log(
                "warning", 
                f"[Stream Preview] Не удалось скачать превью {clean_url}: HTTP {resp.status}", 
                emoji=LogEmojis.WARNING
            )
    except Exception as e:
        await send_to_any_log(
            "warning", 
            f"[Stream Preview] Ошибка при сохранении превью стрима {clean_url}: {e}", 
            emoji=LogEmojis.WARNING
        )
        
    # При ошибке возвращаем исходный URL
    return clean_url
