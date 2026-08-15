# modules/vk_wall/content_processor/photo_group_processor.py
import asyncio
import discord
from typing import Dict, Any, List, Optional
from constants.emojis import LogEmojis
from constants.base import PhotoDelay, DiscordLimits
from log_system.logger_helper import send_to_any_log
from modules_utils.helpers import get_best_photo_url
from modules.vk_wall.content_processor.config_resolver import ConfigResolver
from modules.vk_wall.content_processor.file_downloader import FileDownloader
from modules.vk_wall.content_processor.embed_builder import EmbedBuilder

class PhotoGroupProcessor:
    @staticmethod
    async def create_single_photo_embed(
        photo: Dict[str, Any],
        group_config: Dict[str, Any],
        post_url: str,
        index: int,
        total: int
    ) -> discord.Embed:
        """Создает индивидуальный embed для одного фото."""
        config = ConfigResolver.get_attachment_config(group_config, "photo")
        return await EmbedBuilder._create_photo_embed(
            photo=photo,
            group_config=group_config,
            config=config,
            post_url=post_url,
            index=index,
            total=total
        )

    @staticmethod
    async def process_photos(
        all_photos: List[Dict[str, Any]],
        group_config: Dict[str, Any],
        post_url: str,
        base_content: Optional[str],
        embeds: List[discord.Embed]
    ) -> List[dict]:
        """Обрабатывает список фотографий, формируя сообщения для Discord в зависимости от параметров (скачивание или embed)."""
        messages_to_send = []
        files = []
        
        def add_url_safely(content: Optional[str], url: str) -> str:
            if not content:
                return url
            new_content = f"{content}\n{url}"
            if len(new_content) > DiscordLimits.MAX_TEXT_LENGTH:
                max_content_length = DiscordLimits.MAX_TEXT_LENGTH - len(url) - 4
                return f"{content[:max_content_length]}...\n{url}"
            return new_content

        photo_config = ConfigResolver.get_attachment_config(group_config, "photo")
        use_only_json_images = group_config.get("use_only_json_images", False)
        
        if use_only_json_images:
            single_photo_embed = await PhotoGroupProcessor.create_single_photo_embed(
                all_photos[0], group_config, post_url, 0, 1
            )
            
            final_content = base_content
            final_content = add_url_safely(final_content, post_url)
            
            res_embeds = (embeds or []) + [single_photo_embed]
            
            msg = {
                "content": final_content,
                "embeds": res_embeds[:DiscordLimits.MAX_EMBEDS],
                "files": files.copy() if files else None
            }
            messages_to_send.append(msg)
        else:
            send_photos_as_file = photo_config["as_file"]
            first_photo = all_photos[0]

            first_photo_embed = await PhotoGroupProcessor.create_single_photo_embed(
                first_photo, group_config, post_url, 0, len(all_photos)
            )

            if len(all_photos) == 1 and not base_content and not send_photos_as_file:
                final_content = add_url_safely(None, post_url)
                msg = {
                    "content": final_content,
                    "embeds": [first_photo_embed],
                    "files": []
                }
                messages_to_send.append(msg)
            elif len(all_photos) == 1 and send_photos_as_file:
                file = await FileDownloader._download_single_photo_file(first_photo, group_config)
                if file:
                    final_content = add_url_safely(None, post_url)
                    msg = {
                        "content": final_content,
                        "embeds": [],
                        "files": [file]
                    }
                    messages_to_send.append(msg)
                else:
                    await send_to_any_log("warning", f"{LogEmojis.WARNING} Failed to download photo as file. Using embed as fallback.")
                    msg = {
                        "content": final_content,
                        "embeds": [first_photo_embed],
                        "files": []
                    }
                    messages_to_send.append(msg)
            else:
                final_content = base_content
                final_content = add_url_safely(final_content, post_url)
                if final_content and len(final_content) > DiscordLimits.MAX_TEXT_LENGTH:
                    final_content = final_content[:DiscordLimits.MAX_TEXT_LENGTH - 3] + "..."

                if send_photos_as_file:
                    file = await FileDownloader._download_single_photo_file(first_photo, group_config)
                    if file:
                        first_msg = {
                            "content": final_content,
                            "embeds": embeds[:DiscordLimits.MAX_EMBEDS] if embeds else [],
                            "files": [file] + (files.copy() if files else [])
                        }
                        messages_to_send.append(first_msg)
                    else:
                        await send_to_any_log("warning", f"{LogEmojis.WARNING} Failed to download first photo as file. Using embed.")
                        first_msg = {
                            "content": final_content,
                            "embeds": embeds[:DiscordLimits.MAX_EMBEDS] if embeds else [first_photo_embed],
                            "files": files.copy() if files else []
                        }
                        messages_to_send.append(first_msg)
                else:
                    if embeds:
                        image_url = get_best_photo_url(first_photo)
                        if image_url:
                            embeds[0].set_image(url=image_url)
                        first_msg = {
                            "content": final_content,
                            "embeds": embeds[:DiscordLimits.MAX_EMBEDS],
                            "files": files.copy() if files else []
                        }
                    else:
                        first_msg = {
                            "content": final_content,
                            "embeds": [first_photo_embed],
                            "files": files.copy() if files else []
                        }
                    messages_to_send.append(first_msg)

                for i, photo in enumerate(all_photos[1:], 1):
                    await asyncio.sleep(PhotoDelay.SECONDS)
                    if send_photos_as_file:
                        file = await FileDownloader._download_single_photo_file(photo, group_config)
                        if file:
                            msg = {
                                "content": None,
                                "embeds": [],
                                "files": [file]
                            }
                            messages_to_send.append(msg)
                        else:
                            next_embed = await PhotoGroupProcessor.create_single_photo_embed(
                                photo, group_config, post_url, i, len(all_photos)
                            )
                            msg = {
                                "content": None,
                                "embeds": [next_embed],
                                "files": []
                            }
                            messages_to_send.append(msg)
                    else:
                        next_embed = await PhotoGroupProcessor.create_single_photo_embed(
                            photo, group_config, post_url, i, len(all_photos)
                        )
                        msg = {
                            "content": None,
                            "embeds": [next_embed],
                            "files": []
                        }
                        messages_to_send.append(msg)

        return messages_to_send
