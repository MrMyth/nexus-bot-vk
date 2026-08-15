# modules/vk_wall/content_processor/processor.py
import asyncio
import aiohttp
import discord
from typing import Optional, Dict, Any, List
from log_system.logger_helper import send_to_any_log
from settings.config import Config
from constants.emojis import LogEmojis, EmojisFields, Emojis, LiveEmojis
from constants.base import Text
from modules_utils.event_manager import EventManager
from modules.vk_wall.content_processor.embed_builder import EmbedBuilder
from modules_utils.helpers import get_best_photo_url, safe_create_task
from modules_utils.stream_notification_helper import StreamNotificationHelper
from modules_utils.random_resolver import resolve_random_value

# Центральные константы
from constants.base import (
    DiscordLimits,
    ContentTypes,
    PhotoDelay,
    VKAPI
)

# Внутренние модули модуля vk_wall
from modules.vk_wall.content_processor.config_resolver import ConfigResolver
from modules.vk_wall.content_processor.post_filter import PostFilter
from modules.vk_wall.content_processor.link_fixer import LinkFixer
from modules.vk_wall.content_processor.repost_processor import RepostProcessor
from modules.vk_wall.content_processor.photo_group_processor import PhotoGroupProcessor
from modules.vk_wall.content_processor.attachment_processor import AttachmentProcessor

# Для проверки стримов
from modules_utils.vk_api_client import VKApiClient


class ContentProcessor:
    # Маркер: пост намеренно отложен из-за активного стрима на стене (skip_live_posts=true).
    # Отличается от None (нет данных для отправки / фильтр отклонил пост), чтобы вызывающий
    # код (monitor.py) не считал это ошибкой отправки и не удалял пост из очереди повторов.
    SKIP_LIVE_POST = object()

    def __init__(self, bot):
        self.bot = bot

    def get_edit_config(self, group_config: Dict[str, Any]) -> dict:
        return ConfigResolver.get_edit_config(group_config)

    def mustbe_condition_passed(self, post: Dict[str, Any], group_config: Dict[str, Any]) -> bool:
        return PostFilter.mustbe_condition_passed(post, group_config)

    def skip_if_only_condition_passed(self, post: Dict[str, Any], group_config: Dict[str, Any]) -> bool:
        return PostFilter.skip_if_only_condition_passed(post, group_config)

    def should_skip_post(self, post: Dict[str, Any], group_config: Dict[str, Any]) -> bool:
        return PostFilter.should_skip_post(post, group_config)
    
    def passes_all_filters(self, post: Dict[str, Any], group_config: Dict[str, Any]) -> bool:
        """
        Проверяет, проходит ли пост все фильтры:
        - mustbe
        - skip_if_only
        - should_skip_post (закреп, реклама, репосты и т.д.)
        
        Возвращает True, если пост прошёл все фильтры.
        """
        # 1. Check mustbe
        if not self.mustbe_condition_passed(post, group_config):
            safe_create_task(send_to_any_log("info", f"{LogEmojis.INFO} Post {post['id']} skipped: does not satisfy 'mustbe' condition"))
            return False

        # 2. Check skip_if_only
        if self.skip_if_only_condition_passed(post, group_config):
            safe_create_task(send_to_any_log("info", f"{LogEmojis.INFO} Post {post['id']} skipped: contains only specified attachment types (skip_if_only)"))
            return False

        # 3. Check other filters
        if self.should_skip_post(post, group_config):
            safe_create_task(send_to_any_log("info", f"{LogEmojis.INFO} Post {post['id']} skipped: matched other filter criteria (pinned, ads, reposts, etc.)"))
            return False

        return True

    def _split_text_into_chunks(self, text: str, max_len: int = 1800) -> List[str]:
        """Разбивает текст на части, не ломая предложения и строки по возможности."""
        if not text:
            return []
        if len(text) <= max_len:
            return [text]

        chunks = []
        current_chunk = []
        current_len = 0
        
        # Разделяем по строкам
        lines = text.split("\n")
        for line in lines:
            line_len = len(line) + 1  # учитываем символ новой строки
            if current_len + line_len <= max_len:
                current_chunk.append(line)
                current_len += line_len
            else:
                # Если текущий чанк пуст, но строчка превышает лимит, делим её по словам
                if not current_chunk:
                    sub_chunks = []
                    words = line.split(" ")
                    sub_current = []
                    sub_len = 0
                    for word in words:
                        word_len = len(word) + 1
                        if sub_len + word_len <= max_len:
                            sub_current.append(word)
                            sub_len += word_len
                        else:
                            if sub_current:
                                sub_chunks.append(" ".join(sub_current))
                            sub_current = [word]
                            sub_len = word_len
                    if sub_current:
                        sub_chunks.append(" ".join(sub_current))
                    
                    if sub_chunks:
                        chunks.append(sub_chunks[0])
                        for sc in sub_chunks[1:]:
                            chunks.append(sc)
                    current_chunk = []
                    current_len = 0
                else:
                    # Записываем накопленное
                    chunks.append("\n".join(current_chunk))
                    current_chunk = [line]
                    current_len = line_len
                    
        if current_chunk:
            chunks.append("\n".join(current_chunk))
            
        return [c for c in chunks if c.strip()]

    async def build_edit_notification(
        self,
        post: Dict[str, Any],
        group: Dict[str, Any],
        text_changed: bool,
        attachments_changed: bool,
        added_text: str = ""
    ) -> Optional[dict]:
        """Создаёт сообщение для уведомления о редактировании поста."""
        config = self.get_edit_config(group)
        if not config["enabled"]:
            return None

        post_url = f"https://{VKAPI.DOMAIN}/wall{post['owner_id']}_{post['id']}"
        embed = await EmbedBuilder._create_base_embed(group, 'edit', config)
        embed.color = config["color"]
        embed.title = f"{config['emoji']} Пост был отредактирован!"
        embed.description = f"[Смотреть пост в VK]({post_url})"

        if text_changed:
            text_config = ConfigResolver.get_attachment_config(group, "text")
            emoji = text_config["emoji"]
            if added_text:
                # Показываем добавленный текст, соблюдая лимит Discord на значение поля
                display_added = added_text
                if len(display_added) > DiscordLimits.MAX_FIELD_VALUE - 3:
                    display_added = display_added[:DiscordLimits.MAX_FIELD_VALUE - 3] + "..."
                embed.add_field(
                    name=f"{emoji} Добавлен текст",
                    value=display_added,
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"{emoji} Изменён текст",
                    value="‎",
                    inline=False
                )

        if attachments_changed:
            embed.add_field(
                name=f"{Emojis.ATTACHMENTS} Изменены вложения",
                value="‎",
                inline=False
            )

        preview_url = config["preview"] or group.get("fallback_image")
        if preview_url:
            embed.set_image(url=preview_url)

        content = ""
        if group.get("role_id"):
            content = f"<@&{group['role_id']}>"

        return {
            "content": content,
            "embeds": [embed]
        }
    
    async def _build_stream_embed(
        self,
        post: Dict[str, Any],
        video: Dict[str, Any],
        group_config: Dict[str, Any]
    ) -> List[dict]:
        """
        Строит embed для активного стрима, опубликованного на стене группы.
        Использует универсальные компоненты.
        Возвращает список сообщений для совместимости с интерфейсом.
        """
        from constants.emojis import Emojis, EmojisFields

        # Подготавливаем данные стрима
        stream_info = video.copy()
        stream_info["url"] = f"https://{VKAPI.DOMAIN}/wall{post['owner_id']}_{post['id']}"
        stream_info["title"] = video.get("title") or "Прямой эфир"
        
        # Создаем уведомление через универсальный хелпер
        notification = await StreamNotificationHelper.build_stream_start_notification(
            stream_info, 
            group_config, 
            context="wall_post"
        )
        
        if not notification:
            return []

        # Создание мероприятия (если включено)
        if group_config.get("create_stream_event", False):
            try:
                channel_id = group_config.get("discord_channel_id")
                if not channel_id:
                    raise ValueError("discord_channel_id not set for group")

                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    raise ValueError(f"Channel {channel_id} not found")

                guild = channel.guild

                event_id = await EventManager.create_discord_event(
                    guild=guild,
                    event_data=stream_info,
                    config=group_config
                )
                
                if event_id:
                    event_data = {
                        "event_id": event_id,
                        "guild": guild,
                        "video_owner_id": video["owner_id"],
                        "video_id": video["id"]
                    }
                    EventManager.store_event(str(post['id']), event_data)

                    # Start background monitoring via EventManager
                    safe_create_task(EventManager.monitor_stream_end(
                        stream_id=str(post['id']),
                        video_owner_id=video["owner_id"],
                        video_id=video["id"]
                    ))

            except Exception as e:
                await send_to_any_log("error", f"{LogEmojis.ERROR} Error creating stream event: {e}")

        # Return list with one message for compatibility with processor.py interface
        return [notification]

    async def build_discord_message(
        self,
        post: Dict[str, Any],
        group_config: Dict[str, Any],
        extra_text: str = ""
    ) -> Optional[List[dict]]:
        if not isinstance(post, dict):
            await send_to_any_log("error", f"{LogEmojis.ERROR} Expected dict, got {type(post)}")
            return None

        if not self.passes_all_filters(post, group_config):
            return None

        # Save original text BEFORE filtering
        original_text = post.get("text", "").strip()
        # Process links and get filtered text
        text = LinkFixer.fix_vk_links(original_text)
        text = LinkFixer._restore_cut_links(text)

        post_url = f"https://{VKAPI.DOMAIN}/wall{post['owner_id']}_{post['id']}"

        attachment_types = [att["type"] for att in (post.get("attachments") or [])]
        main_type = attachment_types[0] if attachment_types else None

        type_names = {
            ContentTypes.PHOTO: "Photo",
            ContentTypes.VIDEO: "Video",
            ContentTypes.CLIP: "Clip",
            ContentTypes.DOC: "Document",
            ContentTypes.AUDIO: "Audio",
            ContentTypes.ARTICLE: "Article",
            ContentTypes.LINK: "Link",
            ContentTypes.POLL: "Poll",
            ContentTypes.MAP: "Map",
            ContentTypes.MARKET: "Product"
        }

        # Check: is this an active live stream?
        if main_type == ContentTypes.VIDEO:
            video = post["attachments"][0]["video"]
            video_owner_id = video.get("owner_id")
            video_id = video.get("id")

            if video_owner_id and video_id:
                is_live = video.get("is_live") or (video.get("live") == 1) or (video.get("live_status") == "started")
                if not is_live and (group_config.get("detect_stream", False) or group_config.get("skip_live_posts", False)):
                    is_live = await VKApiClient.is_live_video(video_owner_id, video_id)

                if is_live:
                    if group_config.get("skip_live_posts", False):
                        await send_to_any_log("info", f"{Emojis.PROHIBITED} Deferring post with active stream on group wall (skip_live_posts=true): {video.get('title', 'Untitled')}. Will publish once stream ends.", emoji=LogEmojis.INFO)
                        return ContentProcessor.SKIP_LIVE_POST
                    elif group_config.get("detect_stream", False):
                        group_id = group_config.get("id")
                        if group_id and video_owner_id == -abs(group_id):
                            await send_to_any_log("info", f"{LiveEmojis.STREAM_START} Detected active stream on group wall: {video.get('title', 'Untitled')}")
                            return await self._build_stream_embed(post, video, group_config)

        if not text and main_type:
            if original_text.strip():
                pass
            else:
                config = ConfigResolver.get_attachment_config(group_config, main_type)
                emoji = config["emoji"]
                type_name = type_names.get(main_type, main_type.capitalize())
                text = f"{emoji} {type_name} without text"

        text_chunks = []
        if text:
            limit = DiscordLimits.MAX_TEXT_LENGTH - 180
            text_chunks = self._split_text_into_chunks(text, max_len=limit)

        content_parts = []
        if group_config.get("custom_message"):
            content_parts.append(group_config["custom_message"])
        if group_config.get("role_id"):
            content_parts.append(f"<@&{group_config['role_id']}>")
        if text_chunks:
            content_parts.append(text_chunks[0])
        if extra_text:
            content_parts.append(extra_text)

        base_content = "\n".join(content_parts).strip() if content_parts else None
        attachments = post.get("attachments") or []
        other_attachments = []
        all_photos = []
        embeds = []
        files = []

        if "copy_history" in post:
            repost_config = ConfigResolver.get_attachment_config(group_config, "repost")
            if repost_config["enabled"]:
                repost_embed = await RepostProcessor.create_repost_embed(
                    post["copy_history"][0], group_config, repost_config, post_url
                )
                if repost_embed:
                    embeds.append(repost_embed)

        for att in attachments:
            try:
                if not isinstance(att, dict):
                    await send_to_any_log("warning", f"{LogEmojis.WARNING} Attachment is not a dict, skipped: {str(att)[:80]}")
                    continue
                att_type = att["type"]
                config = ConfigResolver.get_attachment_config(group_config, att_type)
                if not config["enabled"]:
                    continue
                if att_type == ContentTypes.PHOTO:
                    all_photos.append(att["photo"])
                else:
                    other_attachments.append(att)
            except Exception as e:
                att_type_safe = att.get('type', 'unknown') if isinstance(att, dict) else type(att).__name__
                await send_to_any_log("error", f"{LogEmojis.ERROR} Error processing attachment {att_type_safe}: {str(e)}")

        # Обработка не-фото вложений via AttachmentProcessor
        other_embeds, messages_to_send = await AttachmentProcessor.process_other_attachments(
            other_attachments, all_photos, group_config, post_url
        )
        embeds.extend(other_embeds)

        # Обработка фото via PhotoGroupProcessor
        if all_photos:
            photo_messages = await PhotoGroupProcessor.process_photos(
                all_photos, group_config, post_url, base_content, embeds
            )
            messages_to_send.extend(photo_messages)
        else:
            if base_content or embeds or files:
                final_content = base_content
                
                # Добавляем post_url, если его нет
                if not final_content:
                    final_content = post_url
                elif post_url not in final_content:
                    new_content = f"{final_content}\n{post_url}"
                    if len(new_content) > DiscordLimits.MAX_TEXT_LENGTH:
                        max_content_length = DiscordLimits.MAX_TEXT_LENGTH - len(post_url) - 4
                        final_content = f"{final_content[:max_content_length]}...\n{post_url}"
                    else:
                        final_content = new_content

                if final_content and len(final_content) > DiscordLimits.MAX_TEXT_LENGTH:
                    final_content = final_content[:DiscordLimits.MAX_TEXT_LENGTH - 3] + "..."

                message = {
                    "content": final_content,
                    "embeds": embeds[:DiscordLimits.MAX_EMBEDS] if embeds else [],
                    "files": files.copy() if files else []
                }
                messages_to_send.append(message)

        if messages_to_send and len(text_chunks) > 1:
            for idx, chunk in enumerate(text_chunks[1:], start=2):
                messages_to_send.append({
                    "content": f"**[Часть {idx}/{len(text_chunks)}]**\n{chunk}",
                    "embeds": [],
                    "files": []
                })

        return messages_to_send if messages_to_send else None
