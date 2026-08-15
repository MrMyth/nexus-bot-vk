# content_processing/repost_handler.py
import discord
from typing import Optional, Dict, Any
from constants.emojis  import EmojisFields, Emojis
from modules.vk_wall.content_processor.embed_builder import EmbedBuilder
from constants.base import VKAPI, ContentTypes
from modules_utils.helpers import get_best_photo_url


class RepostHandler:
    """
    Статический класс для создания embed-а для репоста.
    """

    @staticmethod
    async def _create_repost_embed(repost_data: Dict[str, Any], group_config: Dict[str, Any], config: Dict[str, Any], post_url: str) -> Optional[discord.Embed]:
        embed = await EmbedBuilder._create_base_embed(group_config, "repost", config)
        embed.color = config["color"]
        embed.title = f"{config['emoji']} Репост записи"
        embed.url = post_url

        repost_text = repost_data.get("text", "").strip()
        if repost_text:
            if len(repost_text) > 1000:
                repost_text = repost_text[:1000] + "..."
            embed.description = f"> {repost_text}"

        owner_id = repost_data.get("owner_id", "")
        if owner_id:
            if owner_id < 0:
                group_id = abs(owner_id)
                author_name = f"Группа {group_id}"
                author_url = f"https://{VKAPI.DOMAIN}/club{group_id}"
            else:
                author_name = f"Пользователь {owner_id}"
                author_url = f"https://{VKAPI.DOMAIN}/id{owner_id}"
            embed.add_field(
                name=f"{EmojisFields.SOURCE} Оригинальный автор",
                value=f"[{author_name}]({author_url})",
                inline=False
            )

        original_post_id = repost_data.get("id", "")
        if owner_id and original_post_id:
            original_url = f"https://{VKAPI.DOMAIN}/wall{owner_id}_{original_post_id}"
            embed.add_field(
                name=f"{Emojis.REPOST} Оригинальная запись",
                value=f"[Смотреть в VK]({original_url})",
                inline=False
            )

        # >>> НОВОЕ: Пытаемся взять изображение из оригинального поста <<<
        image_url = None
        attachments = repost_data.get("attachments") or []
        for att in attachments:
            att_type = att["type"]
            if att_type == ContentTypes.PHOTO:
                photo = att["photo"]
                image_url = get_best_photo_url(photo)
                if image_url:
                    break
            elif att_type == ContentTypes.VIDEO:
                video = att["video"]
                video_images = video.get("image", [])
                if video_images:
                    sorted_imgs = sorted(video_images, key=lambda x: x.get("width", 0), reverse=True)
                    image_url = sorted_imgs[0].get("url")
                    if image_url:
                        break
            elif att_type == ContentTypes.CLIP:
                clip = att["clip"]
                clip_images = clip.get("image", [])
                if clip_images:
                    sorted_imgs = sorted(clip_images, key=lambda x: x.get("width", 0), reverse=True)
                    image_url = sorted_imgs[0].get("url")
                    if image_url:
                        break
            elif att_type == ContentTypes.LINK:
                link = att["link"]
                if "photo" in link:
                    photo_url = get_best_photo_url(link["photo"])
                    if photo_url:
                        image_url = photo_url
                        break
            elif att_type == ContentTypes.ARTICLE:
                article = att["article"]
                if "photo" in article:
                    photo_url = get_best_photo_url(article["photo"])
                    if photo_url:
                        image_url = photo_url
                        break

        # Если не нашли изображение в репосте — используем превью из конфига
        if not image_url:
            image_url = config.get("preview") or group_config.get("fallback_image")

        if image_url:
            embed.set_image(url=image_url)

        return embed