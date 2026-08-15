import discord
from typing import Optional, Dict, Any
from constants.base import ContentTypes, VKAPI, Text
from constants.emojis import Emojis, EmojisFields, StartupEmojis
from constants.strings import BotStrings
from settings.config import Config
from modules_utils.vk_api_client import VKApiClient
from modules_utils.embed_builder_video import EmbedBuilderVideo
from modules_utils.random_resolver import resolve_random_value
from modules_utils.helpers import hex_to_color_int, get_best_photo_url, resolve_asset_url, parse_color_to_int

class EmbedBuilder:
    """
    Статический класс для создания объектов discord.Embed для различных типов контента.
    НЕ должен импортировать ContentProcessor.
    """

    @staticmethod
    def _get_preview_url(platform_url: Optional[str], config: Dict[str, Any], group_config: Dict[str, Any]) -> Optional[str]:
        """
        Универсальный метод для выбора URL превью.
        Превью контента по умолчанию пробует платформу.
        """
        use_only_json = group_config.get("use_only_json_images", False)
        # Для превью приоритет: 1. Явный флаг в конфиге типа 2. Глобальный флаг (инвертированный) 3. По умолчанию True
        try_platform = config.get("try_platform_preview", not use_only_json)

        if try_platform and platform_url:
            return platform_url
            
        raw_preview = config.get("preview")
        if raw_preview:
            resolved = resolve_random_value(raw_preview)
            if resolved:
                return resolve_asset_url(str(resolved).strip())
        return None

    @staticmethod
    async def _get_avatar_url(raw_value: Any, group_config: Dict[str, Any]) -> Optional[str]:
        """
        Универсальный метод для получения аватара (для автора, футера или thumbnail).
        Аватары по умолчанию НЕ пробуют платформу (только JSON).
        """
        group_id = group_config.get("id")
        
        # Для аватаров по умолчанию False, берем из конфига если не указано иное
        try_platform = group_config.get("try_platform_preview", False)
        
        resolved_json = resolve_random_value(raw_value)
        json_url = resolve_asset_url(str(resolved_json).strip()) if resolved_json else None

        # Если включен try_platform и в JSON пусто (или мы хотим форсировать платформу)
        # В данном случае, если JSON пустой, а платформа разрешена — берем аватар.
        if try_platform and not json_url and group_id:
            return await VKApiClient.get_group_avatar(group_id, token=group_config.get("vk_token"))
            
        return json_url

    @staticmethod
    async def _create_base_embed(group_config: Dict[str, Any], content_type: str, config: Dict[str, Any]) -> discord.Embed:
        # === Цвет ===
        raw_color = config.get("color")
        color_val = resolve_random_value(raw_color)
        default_color = parse_color_to_int(Config.EMBED_COLOR, 0x0099FF)
        if color_val is not None:
            if isinstance(color_val, int):
                color = color_val
            else:
                color = parse_color_to_int(str(color_val), default_color)
        else:
            color = default_color

        embed = discord.Embed(color=color)

        # === Автор ===
        if "name" in group_config:
            author_name = group_config["name"]
            
            # Логика аватара автора
            author_icon_url = await EmbedBuilder._get_avatar_url(
                group_config.get("embed_author_icon_url"), 
                group_config
            )
            
            group_id = group_config.get("id")
            raw_author_url = group_config.get("embed_author_url")
            author_url = resolve_random_value(raw_author_url)
            
            if not author_url and group_id is not None:
                if group_id < 0:
                    author_url = f"https://{VKAPI.DOMAIN}/club{abs(group_id)}"
                else:
                    author_url = f"https://{VKAPI.DOMAIN}/id{group_id}"
            
            if author_url and author_icon_url:
                embed.set_author(name=author_name, icon_url=str(author_icon_url), url=str(author_url))
            elif author_url:
                embed.set_author(name=author_name, url=str(author_url))
            elif author_icon_url:
                embed.set_author(name=author_name, icon_url=str(author_icon_url))
            else:
                embed.set_author(name=author_name)

        # === Информационное поле ===
        use_base_field = group_config.get("use_base_info_field", True)
        if use_base_field:
            field_info_name = EmbedBuilderVideo._get_text_val(group_config, "field_info_name", BotStrings.FIELD_INFO_NAME)
            info_text = EmbedBuilderVideo._get_text_val(group_config, "field_info_value", BotStrings.FIELD_INFO_VALUE)
            embed.add_field(
                name=field_info_name,
                value=info_text,
                inline=False
            )

        # === THUMBNAIL ===
        # Приоритет: config (типа) -> group_config -> платформа
        thumbnail_url = await EmbedBuilder._get_avatar_url(
            config.get("thumbnail") or group_config.get("embed_thumbnail_url"),
            group_config
        )

        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        # === Футер ===
        footer_text = group_config.get("embed_footer_text", BotStrings.DEFAULT_FOOTER_TEXT)
        
        # Логика иконки футера
        footer_icon_url = await EmbedBuilder._get_avatar_url(
            group_config.get("embed_footer_icon_url"),
            group_config
        )
        
        if footer_icon_url:
            embed.set_footer(text=footer_text, icon_url=str(footer_icon_url))
        else:
            embed.set_footer(text=footer_text)

        return embed

    @staticmethod
    async def _create_photo_embed(
        photo: Dict[str, Any],
        group_config: Dict[str, Any],
        config: Dict[str, Any],
        post_url: str,
        index: int,
        total: int
    ) -> discord.Embed:
        embed = await EmbedBuilder._create_base_embed(group_config, "photo", config)
        emoji = resolve_random_value(config["emoji"])
        title_suffix = f" ({index + 1} из {total})" if total > 1 else ""
        embed.title = f"{emoji} {BotStrings.CONTENT_TYPE_NAMES['photo']}{title_suffix}"
        embed.url = post_url
        
        image_url = get_best_photo_url(photo)
        
        final_url = EmbedBuilder._get_preview_url(image_url, config, group_config)
        if final_url:
            embed.set_image(url=final_url)
        return embed

    @staticmethod
    async def _create_embed_for_type(
        att: Dict[str, Any],
        group_config: Dict[str, Any],
        config: Dict[str, Any],
        post_url: str,
        index: Optional[int] = None,
        total: Optional[int] = None
    ) -> Optional[discord.Embed]:
        att_type = att["type"]

        base_name = BotStrings.CONTENT_TYPE_NAMES.get(att_type, BotStrings.CONTENT_TYPE_NAMES["fallback"])
        title_suffix = f" ({index + 1} из {total})" if total and total > 1 and index is not None else ""

        if att_type == ContentTypes.VIDEO:
            video_data = att["video"]
            owner_id = video_data.get("owner_id", "")
            video_id = video_data.get("id", "")
            video_url = f"https://{VKAPI.DOMAIN}/video{owner_id}_{video_id}"
            video_data["url"] = video_url

            is_live = bool(video_data.get("is_live")) or (video_data.get("duration") == 0 and video_data.get("views") is not None)

            # Подготавливаем конфиг для EmbedBuilderVideo
            video_config = {
                "id": group_config.get("id"),
                "emoji": config.get("emoji", StartupEmojis.STREAMERS),
                "color": config["color"],
                "preview": config.get("preview"),
                "event_image": config.get("event_image"),
                "thumbnail": config.get("thumbnail") or group_config.get("embed_thumbnail_url"),
                "embed_author_name": group_config.get("name"),
                "embed_author_url": f"https://{VKAPI.DOMAIN}/club{abs(group_config['id'])}" if group_config.get("id") and group_config["id"] < 0 else f"https://{VKAPI.DOMAIN}/id{group_config['id']}" if group_config.get("id") else None,
                "embed_author_icon_url": group_config.get("embed_author_icon_url"),
                "embed_thumbnail_url": config.get("thumbnail") or group_config.get("embed_thumbnail_url"),
                "embed_footer_text": group_config.get("embed_footer_text", "VK → Discord Bot"),
                "embed_footer_icon_url": group_config.get("embed_footer_icon_url"),
                "use_base_info_field": group_config.get("use_base_info_field", True),
                "use_only_json_images": group_config.get("use_only_json_images", False),
                # Передаем настройку платформенных превью
                "try_platform_preview": config.get("try_platform_preview", not group_config.get("use_only_json_images", False))
            }

            embed = await EmbedBuilderVideo.create_video_embed(
                video_data=video_data,
                config=video_config,
                is_live=is_live,
                index=(index + 1) if index is not None else None,
                total=total,
                context="wall_post"
            )

            emoji = resolve_random_value(config["emoji"])
            embed.title = f"{emoji} {base_name}{title_suffix}"
            return embed

        elif att_type == ContentTypes.CLIP:
            clip_data = att["clip"]
            owner_id = clip_data.get("owner_id", "")
            clip_id = clip_data.get("id", "")
            clip_url = f"https://vk.com/clip{owner_id}_{clip_id}"
            clip_data["url"] = clip_url

            clip_config = {
                "id": group_config.get("id"),
                "emoji": config.get("emoji", StartupEmojis.STREAMERS),
                "color": config["color"],
                "preview": config.get("preview"),
                "event_image": config.get("event_image"),
                "thumbnail": config.get("thumbnail") or group_config.get("embed_thumbnail_url"),
                "embed_author_name": group_config.get("name"),
                "embed_author_url": f"https://{VKAPI.DOMAIN}/club{abs(group_config['id'])}" if group_config.get("id") and group_config["id"] < 0 else f"https://{VKAPI.DOMAIN}/id{group_config['id']}" if group_config.get("id") else None,
                "embed_author_icon_url": group_config.get("embed_author_icon_url"),
                "embed_thumbnail_url": config.get("thumbnail") or group_config.get("embed_thumbnail_url"),
                "embed_footer_text": group_config.get("embed_footer_text", "VK → Discord Bot"),
                "embed_footer_icon_url": group_config.get("embed_footer_icon_url"),
                "use_base_info_field": group_config.get("use_base_info_field", True),
                "use_only_json_images": group_config.get("use_only_json_images", False),
                "try_platform_preview": config.get("try_platform_preview", not group_config.get("use_only_json_images", False))
            }

            embed = await EmbedBuilderVideo.create_video_embed(
                video_data=clip_data,
                config=clip_config,
                is_live=False,
                index=(index + 1) if index is not None else None,
                total=total,
                context="wall_post"
            )

            emoji = resolve_random_value(config["emoji"])
            embed.title = f"{emoji} {base_name}{title_suffix}"
            return embed

        elif att_type == ContentTypes.ARTICLE:
            embed = await EmbedBuilder._create_article_embed(att["article"], group_config, config, post_url, index, total)
            emoji = resolve_random_value(config["emoji"])
            embed.title = f"{emoji} {base_name}{title_suffix}"
            return embed
        elif att_type == ContentTypes.POLL:
            embed = await EmbedBuilder._create_poll_embed(att["poll"], group_config, config, post_url, index, total)
            emoji = resolve_random_value(config["emoji"])
            embed.title = f"{emoji} {base_name}{title_suffix}"
            return embed
        elif att_type == ContentTypes.AUDIO:
            embed = await EmbedBuilder._create_audio_embed(att["audio"], group_config, config, post_url, index, total)
            emoji = resolve_random_value(config["emoji"])
            embed.title = f"{emoji} {base_name}{title_suffix}"
            return embed
        elif att_type == ContentTypes.DOC:
            embed = await EmbedBuilder._create_doc_embed(att["doc"], group_config, config, index, total)
            emoji = resolve_random_value(config["emoji"])
            embed.title = f"{emoji} {base_name}{title_suffix}"
            return embed
        elif att_type == ContentTypes.LINK:
            embed = await EmbedBuilder._create_link_embed(att["link"], group_config, config, index, total)
            emoji = resolve_random_value(config["emoji"])
            embed.title = f"{emoji} {base_name}{title_suffix}"
            return embed
        elif att_type == ContentTypes.MAP:
            embed = await EmbedBuilder._create_map_embed(att["map"], group_config, config, post_url, index, total)
            emoji = resolve_random_value(config["emoji"])
            embed.title = f"{emoji} {base_name}{title_suffix}"
            return embed
        elif att_type == ContentTypes.MARKET:
            embed = await EmbedBuilder._create_market_embed(att["market"], group_config, config, post_url, index, total)
            emoji = resolve_random_value(config["emoji"])
            embed.title = f"{emoji} {base_name}{title_suffix}"
            return embed
        else:
            return None

    @staticmethod
    async def _create_article_embed(article: Dict[str, Any], group_config: Dict[str, Any], config: Dict[str, Any], post_url: str, index: int = 1, total: int = 1) -> Optional[discord.Embed]:
        embed = await EmbedBuilder._create_base_embed(group_config, ContentTypes.ARTICLE, config)
        title = article.get("title", BotStrings.CONTENT_TYPE_NAMES["article"])
        raw_url = article.get("url")
        url = str(raw_url) if raw_url and str(raw_url).startswith("http") else None
        embed.url = url
        field_title_name = EmbedBuilderVideo._get_text_val(group_config, "field_title_name", BotStrings.FIELD_TITLE_NAME)
        embed.add_field(name=field_title_name, value=title, inline=False)
        description = article.get("description") or article.get("subtitle")
        if description:
            embed.description = description[:4096]
            
        platform_image = None
        photo_data = article.get("photo")
        if photo_data:
            platform_image = get_best_photo_url(photo_data)

        final_url = EmbedBuilder._get_preview_url(platform_image, config, group_config)
        if final_url:
            embed.set_image(url=final_url)
        return embed

    @staticmethod
    async def _create_poll_embed(poll: Dict[str, Any], group_config: Dict[str, Any], config: Dict[str, Any], post_url: str, index: int = 1, total: int = 1) -> Optional[discord.Embed]:
        from modules.vk_wall.content_processor.poll_processor import PollProcessor
        return await PollProcessor.create_poll_embed(poll, group_config, config, post_url, index, total)

    @staticmethod
    async def _create_audio_embed(audio: Dict[str, Any], group_config: Dict[str, Any], config: Dict[str, Any], post_url: str, index: int = 1, total: int = 1) -> Optional[discord.Embed]:
        embed = await EmbedBuilder._create_base_embed(group_config, ContentTypes.AUDIO, config)
        artist = audio.get("artist", BotStrings.UNKNOWN_ARTIST)
        title = audio.get("title", BotStrings.UNKNOWN_TRACK)
        embed.url = post_url
        field_artist_name = EmbedBuilderVideo._get_text_val(group_config, "field_artist_name", BotStrings.FIELD_ARTIST_NAME)
        field_title_name = EmbedBuilderVideo._get_text_val(group_config, "field_title_name", BotStrings.FIELD_TITLE_NAME)
        embed.add_field(name=field_artist_name, value=artist, inline=True)
        embed.add_field(name=field_title_name, value=title, inline=True)
        duration = audio.get("duration")
        if duration:
            minutes = duration // 60
            seconds = duration % 60
            field_duration_name = EmbedBuilderVideo._get_text_val(group_config, "field_duration_name", BotStrings.FIELD_DURATION_NAME)
            embed.add_field(name=field_duration_name, value=f"{minutes}:{seconds:02d}", inline=True)
            
        final_url = EmbedBuilder._get_preview_url(None, config, group_config)
        if final_url:
            embed.set_image(url=final_url)
        return embed

    @staticmethod
    async def _create_doc_embed(doc: Dict[str, Any], group_config: Dict[str, Any], config: Dict[str, Any], index: int = 1, total: int = 1) -> Optional[discord.Embed]:
        embed = await EmbedBuilder._create_base_embed(group_config, ContentTypes.DOC, config)
        title = doc.get("title", BotStrings.CONTENT_TYPE_NAMES["doc"])
        size = doc.get("size", 0)
        ext = doc.get("ext", "unknown")
        raw_url = doc.get("url")
        url = str(raw_url) if raw_url and str(raw_url).startswith("http") else None
        embed.url = url
        field_title_name = EmbedBuilderVideo._get_text_val(group_config, "field_title_name", BotStrings.FIELD_TITLE_NAME)
        embed.add_field(name=field_title_name, value=title, inline=False)
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} {BotStrings.UNIT_MB}"
        else:
            size_str = f"{size / 1024:.1f} {BotStrings.UNIT_KB}"
        field_size_name = EmbedBuilderVideo._get_text_val(group_config, "field_size_name", BotStrings.FIELD_SIZE_NAME)
        field_format_name = EmbedBuilderVideo._get_text_val(group_config, "field_format_name", BotStrings.FIELD_FORMAT_NAME)
        embed.add_field(name=field_size_name, value=size_str, inline=True)
        embed.add_field(name=field_format_name, value=ext.upper(), inline=True)
        
        final_url = EmbedBuilder._get_preview_url(None, config, group_config)
        if final_url:
            embed.set_image(url=final_url)
        return embed

    # Перевод английских меток типов, которые VK API возвращает в полях ссылок
    _VK_LINK_DESCRIPTION_TRANSLATIONS: Dict[str, str] = {
        "Article": "Статья",
        "article": "Статья",
        "Video": "Видео",
        "video": "Видео",
        "Photo": "Фото",
        "photo": "Фото",
        "Music": "Музыка",
        "music": "Музыка",
        "Audio": "Аудио",
        "audio": "Аудио",
        "Document": "Документ",
        "document": "Документ",
        "Poll": "Опрос",
        "poll": "Опрос",
        "Link": "Ссылка",
        "link": "Ссылка",
        "Product": "Товар",
        "product": "Товар",
        "Market": "Товар",
        "market": "Товар",
        "Story": "История",
        "story": "История",
        "Podcast": "Подкаст",
        "podcast": "Подкаст",
        "Clip": "Клип",
        "clip": "Клип",
        "Post": "Запись",
        "post": "Запись",
        "Note": "Заметка",
        "note": "Заметка",
    }

    @staticmethod
    async def _create_link_embed(link: Dict[str, Any], group_config: Dict[str, Any], config: Dict[str, Any], index: int = 1, total: int = 1) -> Optional[discord.Embed]:
        embed = await EmbedBuilder._create_base_embed(group_config, ContentTypes.LINK, config)
        title = link.get("title", BotStrings.CONTENT_TYPE_NAMES["link"])
        description = link.get("description", "")
        # Переводим английские метки типов, которые VK API может вернуть в description
        description = EmbedBuilder._VK_LINK_DESCRIPTION_TRANSLATIONS.get(description.strip(), description)
        raw_url = link.get("url")
        url = str(raw_url) if raw_url and str(raw_url).startswith("http") else None
        embed.url = url
        if description:
            embed.description = description[:4096]
            
        platform_photo = None
        if "photo" in link:
            platform_photo = get_best_photo_url(link["photo"])
            
        final_url = EmbedBuilder._get_preview_url(platform_photo, config, group_config)
        if final_url:
            embed.set_image(url=final_url)
        return embed

    @staticmethod
    async def _create_map_embed(
        map_: Dict[str, Any],
        group_config: Dict[str, Any],
        config: Dict[str, Any],
        post_url: str,
        index: int = 1,
        total: int = 1
    ) -> Optional[discord.Embed]:
        embed = await EmbedBuilder._create_base_embed(group_config, ContentTypes.MAP, config)
        latitude = map_.get("latitude")
        longitude = map_.get("longitude")
        if not latitude or not longitude:
            return None
        coords = f"{latitude:.5f}, {longitude:.5f}"
        address = map_.get("address", BotStrings.DEFAULT_MAP_ADDRESS)
        base_name = BotStrings.CONTENT_TYPE_NAMES["map"]
        title_suffix = f" ({index} из {total})" if total > 1 else ""
        emoji = resolve_random_value(config["emoji"])
        embed.title = f"{emoji} {base_name}{title_suffix}"
        embed.url = post_url
        field_coords_name = EmbedBuilderVideo._get_text_val(group_config, "field_coords_name", BotStrings.FIELD_COORDS_NAME)
        embed.add_field(name=field_coords_name, value=f"`{coords}`", inline=False)
        field_map_link_name = EmbedBuilderVideo._get_text_val(group_config, "field_map_link_name", BotStrings.FIELD_MAP_LINK_NAME)
        map_link_template = EmbedBuilderVideo._get_text_val(group_config, "field_map_link_value_template", BotStrings.FIELD_MAP_LINK_VALUE_TEMPLATE)
        map_url = f"https://www.google.com/maps?q={latitude},{longitude}"
        embed.add_field(name=field_map_link_name, value=map_link_template.replace("{url}", map_url), inline=False)
        
        final_url = EmbedBuilder._get_preview_url(None, config, group_config)
        if final_url:
            embed.set_image(url=final_url)
        return embed

    @staticmethod
    async def _create_market_embed(market: Dict[str, Any], group_config: Dict[str, Any], config: Dict[str, Any], post_url: str, index: int = 1, total: int = 1) -> Optional[discord.Embed]:
        embed = await EmbedBuilder._create_base_embed(group_config, ContentTypes.MARKET, config)
        title = market.get("title", BotStrings.CONTENT_TYPE_NAMES["market"])
        base_name = BotStrings.CONTENT_TYPE_NAMES["market"]
        title_suffix = f" ({index} из {total})" if total > 1 else ""
        emoji = resolve_random_value(config["emoji"])
        embed.title = f"{emoji} {base_name}{title_suffix}"
        embed.url = post_url
        field_title_name = EmbedBuilderVideo._get_text_val(group_config, "field_title_name", BotStrings.FIELD_TITLE_NAME)
        embed.add_field(name=field_title_name, value=title, inline=False)
        price_info = market.get("price", {})
        if price_info:
            amount = price_info.get("amount", 0) / 100
            currency = price_info.get("currency", {}).get("name", "RUB")
            field_price_name = EmbedBuilderVideo._get_text_val(group_config, "field_price_name", BotStrings.FIELD_PRICE_NAME)
            embed.add_field(name=field_price_name, value=f"{amount} {currency}", inline=True)
        description = market.get("description", "")
        if description:
            embed.description = description[:4096]
            
        platform_photo = market.get("thumb_photo")
        
        final_url = EmbedBuilder._get_preview_url(platform_photo, config, group_config)
        if final_url:
            embed.set_image(url=final_url)
        return embed
