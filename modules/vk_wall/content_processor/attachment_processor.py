# modules/vk_wall/content_processor/attachment_processor.py
import asyncio
import discord
from typing import Dict, Any, List, Tuple, Optional
from constants.emojis import LogEmojis
from constants.base import PhotoDelay, ContentTypes
from log_system.logger_helper import send_to_any_log
from modules.vk_wall.content_processor.config_resolver import ConfigResolver
from modules.vk_wall.content_processor.file_downloader import FileDownloader
from modules.vk_wall.content_processor.embed_builder import EmbedBuilder
from modules.vk_wall.content_processor.attachment_counter import count_attachments_by_type, get_attachment_index_info

class AttachmentProcessor:
    @staticmethod
    async def process_other_attachments(
        other_attachments: List[Dict[str, Any]],
        all_photos: List[Dict[str, Any]],
        group_config: Dict[str, Any],
        post_url: str
    ) -> Tuple[List[discord.Embed], List[dict]]:
        """Обрабатывает не-фото вложения (видео, статьи, ссылки, опросы, документы) и возвращает embeds и готовые сообщения."""
        messages_to_send = []
        embeds = []
        
        # Группируем все не-фото вложения по типу для корректного индексирования
        grouped_attachments = count_attachments_by_type(other_attachments)

        # Обработка не-фото вложений
        for att in other_attachments:
            att_type = att["type"]
            config = ConfigResolver.get_attachment_config(group_config, att_type)
            if not config["enabled"]:
                continue

            current_index, total_count = get_attachment_index_info(att_type, att, grouped_attachments)

            if config["as_file"]:
                file = await FileDownloader.download_file_by_type(att, att_type)
                if file:
                    msg = {
                        "content": None,
                        "embeds": [],
                        "files": [file]
                    }
                    messages_to_send.append(msg)
                    continue
                else:
                    await send_to_any_log("warning", f"{LogEmojis.WARNING} Failed to download {att_type} as file. Using embed as fallback.")

            embed = await EmbedBuilder._create_embed_for_type(
                att, group_config, config, post_url, index=current_index, total=total_count
            )
            if embed:
                if len(other_attachments) == 1 and not all_photos:
                    embeds.append(embed)
                else:
                    msg = {
                        "content": None,
                        "embeds": [embed],
                        "files": []
                    }
                    messages_to_send.append(msg)
                    if len(other_attachments) > 1:
                        await asyncio.sleep(PhotoDelay.SECONDS)
                        
        return embeds, messages_to_send
