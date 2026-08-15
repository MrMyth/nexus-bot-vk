# modules_utils/embed_builder_video.py
import discord
from typing import Dict, Any, Optional
from constants.emojis import Emojis, EmojisFields, LiveEmojis, LogEmojis
from constants.base import VKAPI, Text
from constants.strings import BotStrings
from settings.config import Config
from modules_utils.vk_api_client import VKApiClient
from modules_utils.random_resolver import resolve_random_value
from modules_utils.helpers import hex_to_color_int, get_best_photo_url, resolve_asset_url, parse_color_to_int, safe_create_task
from log_system.logger_helper import send_to_any_log

class EmbedBuilderVideo:
    """Универсальный билдер эмбедов для видео и стримов."""

    _INFO_MESSAGES = BotStrings.INFO_MESSAGES

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Проверяет валидность URL или локального пути."""
        if not url or not isinstance(url, str):
            return False
        if len(url) > 2048:
            return False
        # Разрешаем http/https и локальные пути из папки assets
        return url.startswith(('http://', 'https://', 'assets/'))

    @staticmethod
    def _get_text_val(config: Dict[str, Any], key: str, hardcoded_default: Any) -> Any:
        """
        Универсальный помощник для получения текстового значения.
        Проверяет индивидуальный JSON конфига группы/канала, затем общий default_embeds_config.json,
        и наконец возвращает hardcoded_default.
        """
        if config and key in config:
            return config[key]

        try:
            import json
            import os
            from modules_utils.files import get_config_path
            path = get_config_path("default_embeds_config.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    base_data = json.load(f)
                    if key in base_data:
                        return base_data[key]
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"EmbedBuilderVideo: ошибка загрузки ключа '{key}' из базового конфига: {e}", emoji=LogEmojis.ERROR))

        return hardcoded_default

    @staticmethod
    def _get_info_message(config: Dict[str, Any], context: str) -> Optional[str]:
        """
        Возвращает информационный текст для указанного контекста.
        Учитывает переопределения в индивидуальном конфиге, базовом конфиге и коде.
        """
        if config:
            info_text = config.get("info_field_text") or config.get("base_info_text") or config.get("custom_info_text")
            if info_text:
                return info_text

            info_messages = config.get("info_messages")
            if isinstance(info_messages, dict) and context in info_messages:
                return info_messages[context]

        try:
            import json
            import os
            from modules_utils.files import get_config_path
            path = get_config_path("default_embeds_config.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    base_data = json.load(f)
                    info_messages = base_data.get("info_messages")
                    if isinstance(info_messages, dict) and context in info_messages:
                        return info_messages[context]
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"EmbedBuilderVideo: ошибка загрузки сообщения для контекста '{context}' из базового конфига: {e}", emoji=LogEmojis.ERROR))

        return EmbedBuilderVideo._INFO_MESSAGES.get(context)

    @staticmethod
    def _get_platform_suffix(config: Dict[str, Any], context: str) -> str:
        """Определяет суффикс платформы для ссылок."""
        ctx = context.lower()
        
        # Сначала проверим в конфиге источника
        if config:
            suffixes = config.get("platform_suffixes")
            if isinstance(suffixes, dict):
                for key in sorted(suffixes.keys(), key=len, reverse=True):
                    if key in ctx:
                        return suffixes[key]
                if ctx == "live_stream" and "vk" in suffixes:
                    return suffixes["vk"]
        
        # Затем проверим в JSON (default_embeds_config.json)
        try:
            import json
            import os
            from modules_utils.files import get_config_path
            path = get_config_path("default_embeds_config.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    base_data = json.load(f)
                    suffixes = base_data.get("platform_suffixes")
                    if isinstance(suffixes, dict):
                        for key in sorted(suffixes.keys(), key=len, reverse=True):
                            if key in ctx:
                                return suffixes[key]
                        # Если context равен 'live_stream', то по умолчанию это vk
                        if ctx == "live_stream" and "vk" in suffixes:
                            return suffixes["vk"]
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"EmbedBuilderVideo: ошибка загрузки суффикса платформы из базового конфига: {e}", emoji=LogEmojis.ERROR))

        # Дефолтные хардкод значения
        for platform_key in sorted(BotStrings.PLATFORM_SUFFIXES.keys(), key=len, reverse=True):
            if platform_key != "default" and platform_key in ctx:
                return BotStrings.PLATFORM_SUFFIXES[platform_key]
        if "vk" in ctx or ctx == "live_stream":
            return BotStrings.PLATFORM_SUFFIXES.get("vk", " на VK Play Live")
        return ""

    @staticmethod
    def _get_best_image_url(image_data: Any) -> Optional[str]:
        """Извлекает лучший URL из различных форматов изображений VK/YouTube/Rutube."""
        if not image_data:
            return None
        
        # Если это строка, проверяем на валидность
        if isinstance(image_data, str):
            return image_data if EmbedBuilderVideo._is_valid_url(image_data) else None
            
        # Если это список (как в VK)
        if isinstance(image_data, list):
            # Используем наш универсальный хелпер, обернув список в объект photo
            return get_best_photo_url({"sizes": image_data})
        
        # Если это словарь (как в VK Photo)
        if isinstance(image_data, dict):
            return get_best_photo_url(image_data)
        
        return None

    @staticmethod
    def _get_preview_url(video_data: Dict[str, Any], config: Dict[str, Any], is_live: bool = False) -> Optional[str]:
        """
        Универсальный метод для выбора URL превью видео.
        Превью по умолчанию пробует платформу.
        """
        video_preview = None
        
        # Индивидуальный флаг для видео
        use_only_json = config.get("use_only_json_images", False)
        # По умолчанию True, если не включен глобальный запрет или не переопределено
        try_platform = config.get("try_platform_preview", not use_only_json)

        if try_platform:
            # 1. Пробуем достать из полей VK (photo_2560, photo_1920, photo_1280, photo_800 и т.д.)
            vk_photo_fields = ["photo_2560", "photo_1920", "photo_1280", "photo_800", "photo_640", "photo_320", "photo_130", "photo_max"]
            for field in vk_photo_fields:
                url = video_data.get(field)
                if url and EmbedBuilderVideo._is_valid_url(str(url)):
                    video_preview = str(url)
                    break
            
            # 2. Если не нашли, пробуем из списков image или images (VK Video / YouTube)
            if not video_preview:
                for field in ["image", "images"]:
                    url = EmbedBuilderVideo._get_best_image_url(video_data.get(field))
                    if url:
                        video_preview = url
                        break
            
            # 3. Если всё еще нет, пробуем поле thumbnail (Rutube/YouTube)
            if not video_preview:
                url = video_data.get("thumbnail")
                if url and EmbedBuilderVideo._is_valid_url(str(url)):
                    video_preview = url
        
        # 4. Если всё еще не нашли валидное превью из данных видео (или запрещено), пробуем из конфига
        if not video_preview:
            # Приоритет: preview -> event_image (если это стрим) -> embed_thumbnail_url
            raw_preview = config.get("preview")
            
            if not raw_preview and is_live:
                raw_preview = config.get("event_image")
            
            if not raw_preview:
                raw_preview = config.get("embed_thumbnail_url")
            
            if raw_preview:
                resolved = resolve_random_value(raw_preview)
                if resolved:
                    video_preview = resolve_asset_url(str(resolved).strip())
        
        return video_preview

    @staticmethod
    async def _get_avatar_url(raw_value: Any, config: Dict[str, Any]) -> Optional[str]:
        """
        Универсальный метод для получения аватара (для автора, футера или thumbnail).
        Аватары по умолчанию НЕ пробуют платформу (только JSON).
        """
        group_id = config.get("id") or config.get("group_id")
        
        # Для аватаров по умолчанию False
        try_platform = config.get("try_platform_preview", False)
        
        resolved_json = resolve_random_value(raw_value)
        json_url = resolve_asset_url(str(resolved_json).strip()) if resolved_json else None

        # Если включен try_platform и в JSON пусто — берем аватар группы из VK
        if try_platform and not json_url and group_id:
            try:
                avatar = await VKApiClient.get_group_avatar(group_id)
                if avatar:
                    return avatar
            except Exception:
                pass
            
        return json_url

    @staticmethod
    async def create_video_embed(
        video_data: Dict[str, Any],
        config: Dict[str, Any],
        is_live: bool = False,
        index: Optional[int] = None,
        total: Optional[int] = None,
        context: str = "wall_post"
    ) -> discord.Embed:
        embed = discord.Embed()
        suffix = f" ({index} из {total})" if total and total > 1 and index else ""

        owner_id = video_data.get("owner_id", "")
        video_id = video_data.get("id", "")
        raw_video_url = video_data.get("url")
        
        if raw_video_url and EmbedBuilderVideo._is_valid_url(str(raw_video_url)):
            video_url = str(raw_video_url)
        else:
            # Если это VK Video
            if owner_id and video_id:
                # Оптимизация для предпросмотра: если включено, используем альтернативные домены
                video_url = f"https://{VKAPI.DOMAIN}/video{owner_id}_{video_id}"
                
                # Фишка: иногда Discord лучше встраивает мобильные или специальные ссылки
                if config.get("use_vkvideo_long_links", False):
                    video_url = f"https://vkvideo.ru/video{owner_id}_{video_id}"
            else:
                # Если это внешняя ссылка (например YouTube/Rutube) — ищем в источнике
                video_url = None

        # Проверка кастомных превью-ссылок для Rutube
        if video_url and "rutube.ru" in video_url and config.get("use_rutube_embed_fix", False):
            # Заменяем rutube.ru/video/ID/ на rutube.ru/play/embed/ID (часто помогает с Embed)
            if "/video/" in video_url:
                video_url = video_url.replace("/video/", "/play/embed/")

        # Эмодзи: поддержка рандома
        emoji = resolve_random_value(config.get("emoji", Emojis.VIDEO))

        # Названия заголовков по умолчанию и из конфига
        default_stream_title_val = EmbedBuilderVideo._get_text_val(config, "default_stream_title", BotStrings.DEFAULT_STREAM_TITLE)
        default_video_title_val = EmbedBuilderVideo._get_text_val(config, "default_video_title", BotStrings.VIDEO_WITHOUT_TITLE)
        
        if is_live:
            title = video_data.get("title", default_stream_title_val)
            embed.title = f"{emoji} {title}{suffix}"
        else:
            title = video_data.get("title", default_video_title_val)
            embed.title = f"{emoji} {title}{suffix}"

        embed.url = video_url if EmbedBuilderVideo._is_valid_url(video_url) else None
        
        field_title_name = EmbedBuilderVideo._get_text_val(config, "field_title_name", f"{EmojisFields.TITLE} Название")
        embed.add_field(name=field_title_name, value=title, inline=False)

        duration = video_data.get("duration", 0)
        if duration and not is_live:
            minutes = duration // 60
            seconds = duration % 60
            field_duration_name = EmbedBuilderVideo._get_text_val(config, "field_duration_name", f"{EmojisFields.DURATION} Длительность")
            embed.add_field(
                name=field_duration_name,
                value=f"{minutes}:{seconds:02d}",
                inline=True
            )

        description = video_data.get("description", "").strip()
        if description:
            embed.description = description[:4096]

        # Выбираем URL превью через универсальный метод
        video_preview = EmbedBuilderVideo._get_preview_url(video_data, config, is_live)

        if video_preview:
            # Сохраняем превью стрима локально в save_stream_preview
            if is_live or "stream" in context.lower() or video_data.get("is_live") or video_data.get("stream_id"):
                from modules_utils.stream_preview_saver import save_stream_preview_image
                stream_id = video_data.get("stream_id") or video_data.get("id") or video_data.get("video_id")
                platform = config.get("platform") or config.get("platform_name") or video_data.get("platform")
                video_preview = await save_stream_preview_image(video_preview, stream_id=stream_id, platform=platform)
            try:
                embed.set_image(url=video_preview)
            except Exception as e:
                safe_create_task(send_to_any_log("error", f"EmbedBuilderVideo: ошибка установки изображения: {e}", emoji=LogEmojis.ERROR))

        if is_live:
            field_status_name = EmbedBuilderVideo._get_text_val(config, "field_status_name", f"{LiveEmojis.STREAM_START} Статус")
            field_status_value = EmbedBuilderVideo._get_text_val(config, "field_status_value", BotStrings.FIELD_STATUS_VALUE_LIVE)
            embed.add_field(
                name=field_status_name,
                value=field_status_value,
                inline=True
            )
            if video_url and EmbedBuilderVideo._is_valid_url(video_url):
                # Определяем платформу для Ссылки
                plat_suffix = EmbedBuilderVideo._get_platform_suffix(config, context)
                
                field_link_name = EmbedBuilderVideo._get_text_val(config, "field_link_name", f"{LiveEmojis.LINK} Ссылка")
                
                # Поддержка шаблона ссылки из конфига
                link_template = EmbedBuilderVideo._get_text_val(config, "field_link_value_template", None)
                if link_template:
                    link_value = link_template.replace("{platform}", plat_suffix).replace("{url}", video_url)
                else:
                    link_value = f"[Смотреть стрим{plat_suffix}]({video_url})"
                    
                embed.add_field(
                    name=field_link_name,
                    value=link_value,
                    inline=True
                )

        raw_color = config.get("color")
        color_val = resolve_random_value(raw_color)
        default_color = parse_color_to_int(Config.EMBED_COLOR, 0x0099FF)
        if color_val is not None:
            if isinstance(color_val, int):
                embed.color = color_val
            else:
                embed.color = parse_color_to_int(str(color_val), default_color)
        else:
            embed.color = default_color

        author_name = config.get("embed_author_name")
        if author_name:
            author_icon_url = await EmbedBuilderVideo._get_avatar_url(
                config.get("embed_author_icon_url"),
                config
            )
            embed.set_author(
                name=author_name,
                icon_url=str(author_icon_url) if author_icon_url else None,
                url=f"https://{VKAPI.BASE_URL_VK_LIVE}/{config.get('platform_id')}" if config.get('platform_id') else None,
            )

        thumb_url = await EmbedBuilderVideo._get_avatar_url(
            config.get("embed_thumbnail_url"),
            config
        )
        if thumb_url:
            thumb_url_str = str(thumb_url).strip()
            # Убираем проверку _is_valid_url, так как DiscordBotManager сам разберется
            # аттачмент это или ссылка. Главное, чтобы строка была не пустой.
            embed.set_thumbnail(url=thumb_url_str)

        if config.get("use_base_info_field", True):
            info_text = EmbedBuilderVideo._get_info_message(config, context)
            if info_text:
                field_info_name = EmbedBuilderVideo._get_text_val(config, "field_info_name", f"{EmojisFields.INFO} Информация")
                embed.add_field(
                    name=field_info_name,
                    value=info_text,
                    inline=False
                )

        footer_text = config.get("embed_footer_text")
        if footer_text:
            footer_icon_url = await EmbedBuilderVideo._get_avatar_url(
                config.get("embed_footer_icon_url"),
                config
            )
            embed.set_footer(
                text=footer_text,
                icon_url=str(footer_icon_url) if footer_icon_url else None
            )

        return embed

    @staticmethod
    async def add_stream_fields(embed: discord.Embed, stream_info: Dict[str, Any], config: Dict[str, Any]):
        game = stream_info.get("game", "")
        if game:
            field_game_name = EmbedBuilderVideo._get_text_val(config, "field_game_name", f"{LiveEmojis.STREAM_TITLE} Игра")
            embed.add_field(name=field_game_name, value=game, inline=True)

        viewers = stream_info.get("viewers")
        if viewers is not None:
            field_viewers_name = EmbedBuilderVideo._get_text_val(config, "field_viewers_name", f"{LiveEmojis.VIEWERS} Зрителей")
            embed.add_field(
                name=field_viewers_name, 
                value=str(viewers), 
                inline=True
            )

        if config.get("embed_show_streamer", True) and config.get("streamer_id"):
            field_streamer_name = EmbedBuilderVideo._get_text_val(config, "field_streamer_name", f"{LiveEmojis.STREAMER} Стример")
            embed.add_field(
                name=field_streamer_name,
                value=f"<@{config['streamer_id']}>",
                inline=True
            )

        if config.get("custom_fields"):
            for field in config["custom_fields"]:
                embed.add_field(
                    name=field.get("name", ""),
                    value=field.get("value", ""),
                    inline=field.get("inline", True)
                )

        # Добавляем зеркала стрима (мультитрансляции), если они настроены
        await EmbedBuilderVideo.add_mirrors_field(embed, config, is_video=False, game=game)

    @staticmethod
    async def add_mirrors_field(embed: discord.Embed, config: Dict[str, Any], is_video: bool = False, game: Optional[str] = None):
        """Добавляет в embed поле со списком зеркал (других платформ), если они настроены
        для данного типа контента (стрим/видео) и, при наличии переопределения, для игры."""
        from modules_utils.mirrors_resolver import resolve_mirrors
        mirrors_list = resolve_mirrors(config, is_video=is_video, game=game)
        if not mirrors_list:
            return

        # Сначала проверим в конфиге источника, затем загрузим из JSON
        platform_emojis = {}
        if config:
            emojis = config.get("platform_emojis")
            if isinstance(emojis, dict):
                platform_emojis = emojis

        if not platform_emojis:
            try:
                import json
                import os
                from modules_utils.files import get_config_path
                path = get_config_path("default_embeds_config.json")
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        base_data = json.load(f)
                        emojis = base_data.get("platform_emojis")
                        if isinstance(emojis, dict):
                            platform_emojis = emojis
            except Exception:
                pass

        if not platform_emojis:
            platform_emojis = BotStrings.PLATFORM_EMOJIS

        mirror_lines = []
        default_label = BotStrings.FIELD_MIRRORS_LABEL_VIDEO if is_video else BotStrings.FIELD_MIRRORS_LABEL_STREAM
        config_label_key = "field_mirrors_label_video" if is_video else "field_mirrors_label_stream"
        link_label = EmbedBuilderVideo._get_text_val(config, config_label_key, default_label)
        
        for plat, url in mirrors_list:
            plat_lower = plat.lower()
            emoji = Emojis.GLOBE
            for key, val in platform_emojis.items():
                if key in plat_lower:
                    emoji = val
                    break
            mirror_lines.append(f"{emoji} **{plat}**: [{link_label}]({url})")

        if mirror_lines:
            field_mirrors_name = EmbedBuilderVideo._get_text_val(config, "field_mirrors_name", BotStrings.FIELD_MIRRORS_NAME)
            embed.add_field(
                name=field_mirrors_name,
                value="\n".join(mirror_lines),
                inline=False
            )

    @staticmethod
    async def set_footer(embed: discord.Embed, config: Dict[str, Any]) -> None:
        footer_text = config.get("embed_footer_text")
        if footer_text:
            raw_footer_icon = config.get("embed_footer_icon_url")
            footer_icon_url_resolved = resolve_random_value(raw_footer_icon)
            icon_url = resolve_asset_url(str(footer_icon_url_resolved)) if footer_icon_url_resolved else None
            embed.set_footer(
                text=footer_text,
                icon_url=icon_url
            )
        elif "name" in config:
            footer_template = EmbedBuilderVideo._get_text_val(config, "footer_channel_template", BotStrings.FOOTER_CHANNEL_TEMPLATE)
            embed.set_footer(text=footer_template.format(name=config['name']))