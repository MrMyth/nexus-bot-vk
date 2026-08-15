# modules/vk_assets/asset_monitor.py
import asyncio
import discord
from typing import Dict, Any, List, Optional
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, Emojis, EmojisFields
from modules_utils.vk_api_client import VKApiClient
from modules.vk_assets.asset_database import is_asset_processed, mark_asset_processed
from modules_utils.helpers import hex_to_color_int
from modules_utils.random_resolver import resolve_random_value

class VKAssetMonitor:
    """Монитор ассетов ВК (новые фото, аудио, видео в группе)."""
    
    def __init__(self, config: Dict[str, Any], discord_bot):
        self.config = config
        self.discord_bot = discord_bot
        self.platform_id = str(config.get("platform_id") or config.get("owner_id", ""))
        self.check_interval = config.get("check_interval", 600)
        self.is_running = False
        
        # Настройки типов ассетов
        self.monitor_photos = config.get("monitor_photos", True)
        self.monitor_audio = config.get("monitor_audio", False) # Аудио часто требует спец. токен
        self.monitor_video = config.get("monitor_video", True)
        
        # Каналы уведомлений
        self.photo_channel_id = config.get("photo_channel_id") or config.get("channel_id")
        self.audio_channel_id = config.get("audio_channel_id") or config.get("channel_id")
        self.video_channel_id = config.get("video_channel_id") or config.get("channel_id")

    async def start(self):
        """Запускает цикл мониторинга."""
        self.is_running = True
        while self.is_running:
            try:
                # Устанавливаем таймаут на всю пачку проверок ассетов
                async def run_checks():
                    if self.monitor_photos:
                        await self._check_photos()
                    if self.monitor_video:
                        await self._check_videos()
                    if self.monitor_audio:
                        await self._check_audio()
                
                await asyncio.wait_for(run_checks(), timeout=300)
            except asyncio.TimeoutError:
                await send_to_any_log("error", f"Asset check ({self.platform_id}) timed out (300s)", emoji=LogEmojis.ERROR)
            except Exception as e:
                await send_to_any_log("error", f"Error in VKAssetMonitor ({self.platform_id}): {e}", emoji=LogEmojis.ERROR)
            
            await asyncio.sleep(self.check_interval)

    async def stop(self):
        """Останавливает мониторинг."""
        self.is_running = False

    async def _check_photos(self):
        """Проверяет новые фото в альбомах."""
        # Получаем список альбомов
        albums_resp = await VKApiClient.call_api("photos.getAlbums", {"owner_id": self.platform_id, "need_covers": 1})
        if not albums_resp:
            return

        for album in albums_resp.get("items", []):
            album_id = album.get("id")
            # Получаем последние фото из альбома
            photos_resp = await VKApiClient.call_api("photos.get", {
                "owner_id": self.platform_id,
                "album_id": album_id,
                "rev": 1,
                "count": 5,
                "extended": 1
            })
            
            if not photos_resp:
                continue
                
            for photo in photos_resp.get("items", []):
                photo_id = f"photo_{photo.get('owner_id')}_{photo.get('id')}"
                if not await is_asset_processed(photo_id):
                    await self._notify_photo(photo, album)
                    await mark_asset_processed(photo_id, "photo", self.platform_id)

    async def _check_videos(self):
        """Проверяет новые видео."""
        videos_resp = await VKApiClient.call_api("video.get", {
            "owner_id": self.platform_id,
            "count": 5
        })
        
        if not videos_resp:
            return
            
        for video in videos_resp.get("items", []):
            # Пропускаем стримы, они обрабатываются другим модулем
            if video.get("live"):
                continue
                
            video_id = f"video_{video.get('owner_id')}_{video.get('id')}"
            if not await is_asset_processed(video_id):
                await self._notify_video(video)
                await mark_asset_processed(video_id, "video", self.platform_id)

    async def _check_audio(self):
        """Проверяет новые аудиозаписи (требует прав доступа)."""
        # ВАЖНО: audio.get часто недоступен для обычных токенов приложений
        audio_resp = await VKApiClient.call_api("audio.get", {
            "owner_id": self.platform_id,
            "count": 5
        })
        
        if not audio_resp:
            return
            
        for audio in audio_resp.get("items", []):
            audio_id = f"audio_{audio.get('owner_id')}_{audio.get('id')}"
            if not await is_asset_processed(audio_id):
                await self._notify_audio(audio)
                await mark_asset_processed(audio_id, "audio", self.platform_id)

    async def _notify_photo(self, photo: Dict[str, Any], album: Dict[str, Any]):
        """Отправляет уведомление о новом фото."""
        embed = discord.Embed(
            title=f"{Emojis.PHOTO} Новое фото в альбоме «{album.get('title')}»",
            url=f"https://vk.com/photo{photo.get('owner_id')}_{photo.get('id')}",
            color=hex_to_color_int(resolve_random_value(self.config.get("color", "#0099FF")))
        )
        
        if photo.get("text"):
            embed.description = photo.get("text")[:4000]
            
        # Находим максимальный размер фото
        sizes = photo.get("sizes", [])
        if sizes:
            max_size = max(sizes, key=lambda s: s.get("width", 0) * s.get("height", 0))
            embed.set_image(url=max_size.get("url"))
            
        embed.set_footer(text=f"Группа: {self.config.get('name', self.platform_id)}")
        
        target_id = self.config.get("photo_thread_id") or self.photo_channel_id
        if target_id:
            success = await self.discord_bot.send_message_async(
                screen_name=f"vk_assets_{self.platform_id}_photo",
                message_data=[{"embeds": [embed]}],
                override_channel_id=int(target_id),
                config=self.config
            )
            if success:
                from modules_utils.stats_manager import stats_manager
                stats_manager.log_asset("photo")

    async def _notify_video(self, video: Dict[str, Any]):
        """Отправляет уведомление о новом видео."""
        embed = discord.Embed(
            title=f"{Emojis.VIDEO} Новое видео: {video.get('title')}",
            url=f"https://vk.com/video{video.get('owner_id')}_{video.get('id')}",
            color=hex_to_color_int(resolve_random_value(self.config.get("color", "#0099FF")))
        )
        
        if video.get("description"):
            embed.description = video.get("description")[:4000]
            
        # Превью видео
        image_url = None
        if video.get("image"):
            # В новых версиях API это список объектов
            if isinstance(video["image"], list) and video["image"]:
                image_url = max(video["image"], key=lambda i: i.get("width", 0)).get("url")
            else:
                image_url = video.get("photo_800") or video.get("photo_320")
        
        if image_url:
            embed.set_image(url=image_url)
            
        embed.set_footer(text=f"Группа: {self.config.get('name', self.platform_id)}")
        
        target_id = self.config.get("video_thread_id") or self.video_channel_id
        if target_id:
            success = await self.discord_bot.send_message_async(
                screen_name=f"vk_assets_{self.platform_id}_video",
                message_data=[{"embeds": [embed]}],
                override_channel_id=int(target_id),
                config=self.config
            )
            if success:
                from modules_utils.stats_manager import stats_manager
                stats_manager.log_asset("video")

    async def _notify_audio(self, audio: Dict[str, Any]):
        """Отправляет уведомление о новом аудио."""
        embed = discord.Embed(
            title=f"{Emojis.MUSIC} Добавлен новый трек",
            description=f"**{audio.get('artist')}** — {audio.get('title')}",
            color=hex_to_color_int(resolve_random_value(self.config.get("color", "#0099FF")))
        )
        
        embed.set_footer(text=f"Группа: {self.config.get('name', self.platform_id)}")
        
        target_id = self.config.get("audio_thread_id") or self.audio_channel_id
        if target_id:
            success = await self.discord_bot.send_message_async(
                screen_name=f"vk_assets_{self.platform_id}_audio",
                message_data=[{"embeds": [embed]}],
                override_channel_id=int(target_id),
                config=self.config
            )
            if success:
                from modules_utils.stats_manager import stats_manager
                stats_manager.log_asset("audio")
