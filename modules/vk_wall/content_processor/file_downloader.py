# content_processing/file_downloader.py
import aiohttp
import io
import hashlib
import discord
from typing import Optional, Dict, Any
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from constants.base import DiscordLimits, PhotoExtensions, ContentTypes

class FileDownloader:
    """
    Статический класс для загрузки файлов (фото, аудио, документов) из интернета.
    НЕ должен импортировать ContentProcessor.
    """

    @staticmethod
    async def _download_single_photo_file(photo: Dict[str, Any], group_config: Dict[str, Any]) -> Optional[discord.File]:
        try:
            from modules_utils.helpers import get_best_photo_url
            best_url = get_best_photo_url(photo)
            if not best_url:
                return None

            from modules_utils.http_client import HttpClient
            session = await HttpClient.get_session()
            async with session.get(best_url) as response:
                if response.status == 200:
                    # Превентивная проверка по заголовку Content-Length
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        try:
                            size = int(content_length)
                            if size > DiscordLimits.MAX_FILE_SIZE:
                                await send_to_any_log("warning", f"Photo size from header ({size} bytes) exceeds 25 MB, download cancelled.", emoji=LogEmojis.WARNING)
                                return None
                        except ValueError:
                            pass

                    image_data = await response.read()
                    if len(image_data) > DiscordLimits.MAX_FILE_SIZE:
                        await send_to_any_log("warning", f"Photo too large: {len(image_data)} bytes")
                        return None
                    file_extension = best_url.split('.')[-1].split('?')[0].lower()
                    if file_extension not in PhotoExtensions.ALLOWED:
                        file_extension = PhotoExtensions.DEFAULT
                    filename = f"photo_{hashlib.md5(best_url.encode()).hexdigest()[:8]}.{file_extension}"
                    return discord.File(io.BytesIO(image_data), filename=filename)
        except Exception as e:
            await send_to_any_log("error", f"Error downloading photo: {str(e)}")
        return None

    @staticmethod
    async def _download_audio_file(audio: Dict[str, Any]) -> Optional[discord.File]:
        url = audio.get("url")
        if not url:
            return None
        try:
            from modules_utils.http_client import HttpClient
            session = await HttpClient.get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                
                # Превентивная проверка по заголовку Content-Length
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        size = int(content_length)
                        if size > DiscordLimits.MAX_FILE_SIZE:
                            await send_to_any_log("warning", f"Audio size from header ({size} bytes) exceeds 25 MB, download cancelled.", emoji=LogEmojis.WARNING)
                            return None
                    except ValueError:
                        pass

                data = await response.read()
                if len(data) > DiscordLimits.MAX_FILE_SIZE:
                    await send_to_any_log("warning", f"Audio exceeds 25 MB: {len(data)} bytes")
                    return None
                filename = f"{audio['artist']} - {audio['title']}.mp3"
                return discord.File(io.BytesIO(data), filename)
        except Exception as e:
            await send_to_any_log("error", f"Error downloading audio: {str(e)}")
            return None

    @staticmethod
    async def _download_doc_file(doc: Dict[str, Any]) -> Optional[discord.File]:
        url = doc.get("url")
        if not url:
            return None
        try:
            from modules_utils.http_client import HttpClient
            session = await HttpClient.get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    return None

                # Превентивная проверка по заголовку Content-Length
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        size = int(content_length)
                        if size > DiscordLimits.MAX_FILE_SIZE:
                            await send_to_any_log("warning", f"Document size from header ({size} bytes) exceeds 25 MB, download cancelled.", emoji=LogEmojis.WARNING)
                            return None
                    except ValueError:
                        pass

                data = await response.read()
                if len(data) > DiscordLimits.MAX_FILE_SIZE:
                    await send_to_any_log("warning", f"Document exceeds 25 MB: {len(data)} bytes")
                    return None
                filename = f"{doc['title']}.{doc['ext']}"
                return discord.File(io.BytesIO(data), filename)
        except Exception as e:
            await send_to_any_log("error", f"Error downloading document: {str(e)}")
            return None

    @staticmethod
    async def _download_video_file(video: Dict[str, Any]) -> Optional[discord.File]:
        """Пытается скачать видеофайл. Если нет прямой ссылки или файл > 25 МБ, возвращает None."""
        files = video.get("files")
        url = None
        if isinstance(files, dict):
            # Перебираем разрешения в порядке убывания качества, чтобы получить лучшую прямую ссылку
            for quality in ["mp4_1080", "mp4_720", "mp4_480", "mp4_360", "mp4_240"]:
                if quality in files:
                    url = files[quality]
                    break
        if not url:
            # Fallback к основному url, если он не содержит iframe-страниц
            url = video.get("url") or video.get("player")
            if url and "video_ext.php" in url:
                url = None

        if not url:
            return None

        try:
            from modules_utils.http_client import HttpClient
            session = await HttpClient.get_session()
            async with session.get(url) as response:
                if response.status != 200:
                    return None

                # Превентивная проверка по заголовку Content-Length до чтения данных в память
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        size = int(content_length)
                        if size > DiscordLimits.MAX_FILE_SIZE:
                            await send_to_any_log("warning", f"Video «{video.get('title', 'Untitled')}» exceeds 25 MB ({size} bytes), download cancelled. Falling back to embed.", emoji=LogEmojis.WARNING)
                            return None
                    except ValueError:
                        pass

                data = await response.read()
                if len(data) > DiscordLimits.MAX_FILE_SIZE:
                    await send_to_any_log("warning", f"Video «{video.get('title', 'Untitled')}» exceeds 25 MB ({len(data)} bytes). Falling back to embed.", emoji=LogEmojis.WARNING)
                    return None

                title = video.get("title", f"video_{video.get('id', 'unknown')}")
                import re
                filename = re.sub(r'[\\/*?:"<>|]', "", title)
                filename = filename.strip() or f"video_{video.get('id', 'unknown')}"
                if not filename.lower().endswith(".mp4"):
                    filename += ".mp4"

                return discord.File(io.BytesIO(data), filename)
        except Exception as e:
            await send_to_any_log("error", f"Error downloading video: {str(e)}")
            return None

    @staticmethod
    async def download_file_by_type(att: Dict[str, Any], att_type: str) -> Optional[discord.File]:
        """Унифицированный метод для загрузки файла по типу вложения."""
        if att_type == ContentTypes.AUDIO:
            return await FileDownloader._download_audio_file(att["audio"])
        elif att_type == ContentTypes.DOC:
            return await FileDownloader._download_doc_file(att["doc"])
        elif att_type == ContentTypes.PHOTO:
            return await FileDownloader._download_single_photo_file(att["photo"], {})
        elif att_type == ContentTypes.VIDEO:
            return await FileDownloader._download_video_file(att["video"])
        else:
            await send_to_any_log("warning", f"File download for type '{att_type}' is not supported.")
            return None