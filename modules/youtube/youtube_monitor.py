# modules/youtube/youtube_monitor.py
import asyncio
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, List
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from settings.config import Config
from modules_utils.base_stream_monitor import BaseStreamMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase

class YouTubeMonitor(BaseStreamMonitor):
    """
    Объединенный монитор YouTube для отслеживания стримов и видео.
    Использует RSS ленту канала для мгновенного и надежного получения видео без лимитов и 403 Forbidden,
    а затем проверяет детальный статус live-вещания через Videos API (сверхнизкая квота, нет ошибок поиска).
    """
    def __init__(self, platform_name: str, config: Dict[str, Any], discord_bot, db_helper: Optional[GenericStreamDatabase] = None):
        super().__init__(platform_name, config, discord_bot, db_helper)
        self.api_key = Config.YOUTUBE_API_KEY
        
        # Настройки из конфига + Глобальные флаги
        self.monitor_live = config.get("monitor_live", True)
        self.monitor_video = config.get("monitor_video", True)

        # Кэш для минимизации запросов к YouTube API в рамках одной итерации
        self._cached_items: List[Dict[str, Any]] = []
        self._cache_time: float = 0.0
        self._api_error_reported: bool = False  # логируем ошибку API только один раз

    async def _fetch_latest_youtube_items(self) -> List[Dict[str, Any]]:
        """
        Внутренний метод для получения последних видео/стримов через RSS + Videos API.
        Возвращает список словарей со всеми нужными полями и флагом `is_live`.
        """
        import time
        now = time.time()
        # Кэш на 30 секунд, чтобы при последовательных вызовах fetch_current_streams 
        # и fetch_current_videos не делать повторные сетевые запросы
        if self._cached_items and (now - self._cache_time < 30.0):
            return self._cached_items

        self._cached_items = []
        self._cache_time = now

        from modules_utils.http_client import HttpClient

        rss_videos = []
        fetched_successfully = False

        # 1. Если задан API-ключ, в первую очередь используем надежный метод YouTube API v3 (playlistItems)
        if self.api_key:
            try:
                channel_id = self.platform_id
                uploads_playlist_id = "UU" + channel_id[2:] if (channel_id and channel_id.startswith("UC")) else channel_id
                
                playlist_url = "https://www.googleapis.com/youtube/v3/playlistItems"
                params = {
                    "part": "snippet",
                    "playlistId": uploads_playlist_id,
                    "maxResults": 15,
                    "key": self.api_key
                }
                
                # Запрос к официальному API
                api_data = await HttpClient.get(playlist_url, params=params, suppress_errors=self._api_error_reported, error_level="warning")
                if api_data and isinstance(api_data, dict) and "items" in api_data:
                    for item in api_data.get("items", []):
                        snippet = item.get("snippet", {})
                        resource_id = snippet.get("resourceId", {})
                        video_id = resource_id.get("videoId")
                        if not video_id:
                            continue
                        title = snippet.get("title", "")
                        author = snippet.get("channelTitle", self.config.get('name', self.platform_id))
                        description = snippet.get("description", "")
                        
                        thumbnails = snippet.get("thumbnails", {})
                        image_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
                        for quality in ["maxresdefault", "standard", "high", "medium", "default"]:
                            if quality in thumbnails and thumbnails[quality].get("url"):
                                image_url = thumbnails[quality]["url"]
                                break
                                
                        rss_videos.append({
                            "video_id": video_id,
                            "title": title,
                            "author": author,
                            "description": description,
                            "image": image_url,
                            "is_live": False
                        })
                    
                    fetched_successfully = True
                    # Отмечаем, что API отработало успешно
                    if not self._api_error_reported:
                        await send_to_any_log("info", f"[YouTube] Successfully fetched channel {self.platform_id} data via primary YouTube API (PlaylistItems).", emoji=LogEmojis.SUCCESS)
            except Exception as e_api:
                await send_to_any_log("warning", f"[YouTube] Failed to use primary YouTube API method for {self.platform_id} (switching to backup RSS): {e_api}", emoji=LogEmojis.WARNING)

        # 2. Резервный обходной путь: Загружаем и парсим RSS XML ленту канала, если API не сработало или ключ отсутствует
        if not fetched_successfully:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={self.platform_id}"
            try:
                xml_data = await HttpClient.get(rss_url, suppress_errors=True)
                if not xml_data or not isinstance(xml_data, str):
                    await send_to_any_log("warning", f"[YouTube] Fallback method: Failed to fetch RSS feed for channel {self.platform_id}", emoji=LogEmojis.WARNING)
                else:
                    # Очищаем от BOM, пробелов и недопустимых управляющих символов
                    xml_data = xml_data.lstrip('\ufeff').strip()
                    
                    import re
                    # Удаляем управляющие символы из диапазона ASCII, которые недопустимы в XML 1.0
                    xml_clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml_data)
                    
                    # Кодируем в bytes, чтобы избежать ошибки ValueError: multi-byte encodings are not supported
                    xml_bytes = xml_clean.encode('utf-8')
                    
                    # Парсим RSS ленту
                    root = ET.fromstring(xml_bytes)
                    namespaces = {
                        'atom': 'http://www.w3.org/2005/Atom',
                        'yt': 'http://www.youtube.com/xml/schemas/2015',
                        'media': 'http://search.yahoo.com/mrss/'
                    }
                    
                    for entry in root.findall('atom:entry', namespaces):
                        video_id_elem = entry.find('yt:videoId', namespaces)
                        if video_id_elem is not None and video_id_elem.text:
                            video_id = video_id_elem.text
                            title_elem = entry.find('atom:title', namespaces)
                            title = title_elem.text if title_elem is not None else ""
                            
                            author_elem = entry.find('atom:author/atom:name', namespaces)
                            author = author_elem.text if author_elem is not None else self.config.get('name', self.platform_id)
                            
                            description = ""
                            image_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
                            
                            media_group = entry.find('media:group', namespaces)
                            if media_group is not None:
                                desc_elem = media_group.find('media:description', namespaces)
                                if desc_elem is not None and desc_elem.text:
                                    description = desc_elem.text
                                
                                thumb_elem = media_group.find('media:thumbnail', namespaces)
                                if thumb_elem is not None:
                                    image_url = thumb_elem.attrib.get('url', image_url)
                                    
                            rss_videos.append({
                                "video_id": video_id,
                                "title": title,
                                "author": author,
                                "description": description,
                                "image": image_url,
                                "is_live": False
                            })
                    fetched_successfully = True
                    await send_to_any_log("info", f"[YouTube] Successfully fetched channel {self.platform_id} data via backup RSS feed.", emoji=LogEmojis.SUCCESS)
            except Exception as e:
                await send_to_any_log("error", f"[YouTube] Fallback method: Error fetching/parsing RSS feed for {self.platform_id}: {e}", emoji=LogEmojis.ERROR)

        # Получаем ID активных стримов из БД и памяти
        active_db_ids = []
        try:
            active_db_ids = await self.get_active_streams_from_db()
        except Exception as e:
            await send_to_any_log("warning", f"[YouTube] Error fetching active streams from DB for {self.platform_id}: {e}", emoji=LogEmojis.WARNING)

        active_memory_ids = list(self.active_streams_data.keys())
        all_active_ids = list(set(active_db_ids + active_memory_ids))

        # Собираем все ID для запроса к YouTube Videos API
        video_ids_to_query = [v["video_id"] for v in rss_videos]
        for aid in all_active_ids:
            if aid not in video_ids_to_query:
                video_ids_to_query.append(aid)

        # Ограничиваем список первыми 50 ID (лимит API YouTube Videos)
        video_ids_to_query = video_ids_to_query[:50]

        api_failed = False
        resolved_items = []

        # 3. Если есть API ключ, уточняем статус (live/none/upcoming) через videos API
        if self.api_key and video_ids_to_query:
            videos_url = "https://www.googleapis.com/youtube/v3/videos"
            params = {
                "part": "snippet,liveStreamingDetails",
                "id": ",".join(video_ids_to_query),
                "key": self.api_key
            }
            
            try:
                # При первой ошибке suppress_errors=False — чтобы HttpClient залогировал
                # реальный HTTP-статус от Google (403, 400 и т.д.) для диагностики.
                # После первого репорта переходим в suppress_errors=True, чтобы не спамить.
                data = await HttpClient.get(
                    videos_url,
                    params=params,
                    suppress_errors=self._api_error_reported,
                    error_level="warning",
                )
                if data and isinstance(data, dict) and "items" in data:
                    items = data.get("items", [])
                    
                    # Создаем мапу: id -> (status, metadata_dict)
                    status_map = {}
                    for item in items:
                        vid = item.get("id")
                        if not vid:
                            continue
                        snippet = item.get("snippet", {})
                        status = snippet.get("liveBroadcastContent")
                        
                        # Извлекаем метаданные на случай, если видео нет в RSS
                        title = snippet.get("title", "")
                        author = snippet.get("channelTitle", self.config.get('name', self.platform_id))
                        description = snippet.get("description", "")
                        
                        # Ищем лучшее превью
                        thumbnails = snippet.get("thumbnails", {})
                        image_url = f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"
                        for quality in ["maxresdefault", "standard", "high", "medium", "default"]:
                            if quality in thumbnails and thumbnails[quality].get("url"):
                                image_url = thumbnails[quality]["url"]
                                break
                                
                        status_map[vid] = {
                            "status": status,
                            "title": title,
                            "author": author,
                            "description": description,
                            "image": image_url
                        }

                    # Обрабатываем видео из RSS
                    for v in rss_videos:
                        vid = v["video_id"]
                        if vid in status_map:
                            info = status_map[vid]
                            status = info["status"]
                            if status == "live":
                                v["is_live"] = True
                                # Обновляем метаданные из API, так как они более свежие
                                v["title"] = info["title"]
                                v["author"] = info["author"]
                                v["description"] = info["description"]
                                v["image"] = info["image"]
                                resolved_items.append(v)
                            elif status == "upcoming":
                                # Пропускаем запланированные трансляции
                                continue
                            else:
                                v["is_live"] = False
                                resolved_items.append(v)
                        else:
                            # Если видео из RSS почему-то нет в ответе API (например, удалено или приватное),
                            # помечаем как не live
                            v["is_live"] = False
                            resolved_items.append(v)

                    # Важно! Обрабатываем активные стримы, которых нет в RSS, но которые по-прежнему live по данным API.
                    for aid in all_active_ids:
                        # Если стрим уже обработан в рамках RSS, пропускаем
                        if any(r["video_id"] == aid for r in resolved_items):
                            continue
                        
                        if aid in status_map:
                            info = status_map[aid]
                            if info["status"] == "live":
                                # Стрим все еще запущен! Добавляем его в resolved_items
                                resolved_items.append({
                                    "video_id": aid,
                                    "title": info["title"],
                                    "author": info["author"],
                                    "description": info["description"],
                                    "image": info["image"],
                                    "is_live": True
                                })
                            else:
                                # Стрим завершился (или перешел в статус upcoming/none)
                                # Добавляем его как неактивный (is_live=False), чтобы check_status зафиксировал завершение
                                resolved_items.append({
                                    "video_id": aid,
                                    "title": info["title"],
                                    "author": info["author"],
                                    "description": info["description"],
                                    "image": info["image"],
                                    "is_live": False
                                })
                        else:
                            # Если активного стрима нет в ответе API (например, удален/скрыт),
                            # то он завершился. Добавляем его с is_live=False, чтобы система корректно завершила его.
                            # Берем старые данные из памяти, если они есть.
                            old_data = self.active_streams_data.get(aid, {})
                            resolved_items.append({
                                "video_id": aid,
                                "title": old_data.get("title", "Стрим"),
                                "author": old_data.get("author", self.config.get('name', self.platform_id)),
                                "description": old_data.get("description", ""),
                                "image": old_data.get("image", f"https://i.ytimg.com/vi/{aid}/maxresdefault.jpg"),
                                "is_live": False
                            })

                    self._cached_items = resolved_items
                    if self._api_error_reported:
                        # Разовое уведомление о восстановлении Videos API
                        self._api_error_reported = False
                        await send_to_any_log(
                            "error",
                            f"[YouTube] Videos API is available again for channel {self.platform_id}, bot switched back from RSS to API.",
                            emoji=LogEmojis.SUCCESS,
                        )
                    return self._cached_items
                else:
                    api_failed = True
            except Exception as e:
                await send_to_any_log("error", f"[YouTube] Error accessing Videos API for {self.platform_id}: {e}", emoji=LogEmojis.ERROR)
                api_failed = True

        # 4. Если ключа нет, или API выдал ошибку/недоступен:
        # Используем RSS-видео как обычные видео (is_live=False).
        # КРИТИЧЕСКИ ВАЖНО: Если у нас есть активные стримы, мы ПРИНУДИТЕЛЬНО
        # сохраняем их статус как "live" (is_live=True), чтобы из-за сбоя API или лимитов
        # они не завершились ошибочно!
        resolved_items = []
        for v in rss_videos:
            v["is_live"] = False
            resolved_items.append(v)
        
        if all_active_ids:
            if api_failed and self.api_key:
                if not self._api_error_reported:
                    self._api_error_reported = True
                    # Первый переход на удержание активных стримов
                    await send_to_any_log(
                        "error",
                        f"[YouTube] Videos API is unavailable for channel {self.platform_id} (error or quota exceeded). "
                        f"Bot is temporarily retaining active stream status for {all_active_ids} to prevent false end-of-stream notifications.",
                        emoji=LogEmojis.WARNING,
                    )
            
            for aid in all_active_ids:
                # Если этот ID есть в RSS, мы должны обновить его статус на True
                found = False
                for r in resolved_items:
                    if r["video_id"] == aid:
                        r["is_live"] = True
                        found = True
                        break
                if not found:
                    # Если его нет в RSS, восстанавливаем из памяти
                    old_data = self.active_streams_data.get(aid, {})
                    resolved_items.append({
                        "video_id": aid,
                        "title": old_data.get("title", "Стрим"),
                        "author": old_data.get("author", self.config.get('name', self.platform_id)),
                        "description": old_data.get("description", ""),
                        "image": old_data.get("image", f"https://i.ytimg.com/vi/{aid}/maxresdefault.jpg"),
                        "is_live": True
                    })

        self._cached_items = resolved_items
        return self._cached_items

    async def fetch_current_streams(self) -> List[Dict[str, Any]]:
        """Получает список текущих активных стримов с YouTube."""
        if not self.monitor_live:
            return []

        items = await self._fetch_latest_youtube_items()
        streams = []
        for item in items:
            if item.get("is_live"):
                streams.append({
                    "stream_id": item["video_id"],
                    "title": item["title"],
                    "url": f"https://www.youtube.com/watch?v={item['video_id']}",
                    "author": item["author"],
                    "description": item["description"],
                    "image": item["image"]
                })
        return streams

    async def check_status(self, force_end: bool = False):
        """Переопределяем для добавления проверки видео."""
        if self.monitor_live:
            await super().check_status(force_end=force_end)
        
        if self.monitor_video:
            await self._check_videos()

    async def fetch_current_videos(self) -> List[Dict[str, Any]]:
        """Получает список текущих видео с YouTube."""
        if not self.monitor_video:
            return []

        items = await self._fetch_latest_youtube_items()
        videos = []
        for item in items:
            if not item.get("is_live"):
                videos.append({
                    "video_id": item["video_id"],
                    "title": item["title"],
                    "url": f"https://www.youtube.com/watch?v={item['video_id']}",
                    "author": item["author"],
                    "description": item["description"],
                    "image": item["image"]
                })
        return videos
