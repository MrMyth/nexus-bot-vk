# modules_utils/stream_notification_helper.py
import discord
from typing import Dict, Any, Optional
from settings.config import Config
from constants.emojis import LiveEmojis
from constants.strings import BotStrings
from modules_utils.embed_builder_video import EmbedBuilderVideo
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis


class StreamNotificationHelper:
    """Универсальный хелпер для создания уведомлений о стримах."""
    
    @staticmethod
    def _get_platform_name(config: Dict[str, Any], context: str = "live_stream") -> str:
        """Определяет понятное название базовой платформы."""
        if config.get("platform_name"):
            return config["platform_name"]
            
        ctx = context.lower()

        # Сначала проверим в конфиге источника
        if config:
            names = config.get("platform_names")
            if isinstance(names, dict):
                for key in sorted(names.keys(), key=len, reverse=True):
                    if key in ctx:
                        return names[key]
                if ctx == "live_stream" and "vk" in names:
                    return names["vk"]
        
        # Затем проверим в JSON (default_embeds_config.json)
        try:
            import json
            import os
            from modules_utils.files import get_config_path
            path = get_config_path("default_embeds_config.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    base_data = json.load(f)
                    names = base_data.get("platform_names")
                    if isinstance(names, dict):
                        for key in sorted(names.keys(), key=len, reverse=True):
                            if key in ctx:
                                return names[key]
                        # Если context равен 'live_stream', то по умолчанию это vk
                        if ctx == "live_stream" and "vk" in names:
                            return names["vk"]
        except Exception:
            pass
            
        if "vk_com" in ctx:
            return "VK.com"
        if "goodgame" in ctx:
            return "GoodGame"
        if "twitch" in ctx:
            return "Twitch"
        if "kick" in ctx:
            return "Kick"
        if "rutube" in ctx:
            return "Rutube"
        if "youtube" in ctx:
            return "YouTube"
        if "trovo" in ctx:
            return "Trovo"
        if "vk" in ctx or ctx == "live_stream":
            return "VK Play Live"
            
        return "VK Play Live"

    @staticmethod
    def _get_formatted_mirrors(config: Dict[str, Any], is_video: bool = False, game: Optional[str] = None) -> str:
        """Возвращает форматированную строку зеркал с кликабельными ссылками."""
        from modules_utils.mirrors_resolver import resolve_mirrors
        mirrors_list = resolve_mirrors(config, is_video=is_video, game=game)

        if mirrors_list:
            return ", ".join(f"[{plat_name}]({plat_url})" for plat_name, plat_url in mirrors_list)
        return ""

    @staticmethod
    def _format_template(template: str, placeholders: Dict[str, Any]) -> str:
        """Форматирует шаблон сообщения, заменяя плейсхолдеры."""
        result = template
        for key, val in placeholders.items():
            placeholder = f"{{{key}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(val) if val is not None else "")
        return result

    @staticmethod
    def _get_notification_content(
        config: Dict[str, Any], 
        notification_type: str, 
        stream_info: Optional[Dict[str, Any]] = None,
        context: str = "live_stream"
    ) -> str:
        """Возвращает контент для уведомления (упоминание роли отдельной строкой + кастомный шаблон или дефолт)."""
        role_id = (
            config.get("notification_role_id") or 
            config.get("role_id") or 
            Config.DEFAULT_LIVE_PING_ROLE_ID
        )
        
        is_video = notification_type == "video" or "video" in context.lower()
        notif_type = "video" if is_video else notification_type

        # 1. Формируем упоминание роли в начале (пингуем роль отдельной строкой для старта/видео)
        ping_prefix = ""
        if notif_type in ("start", "video") and role_id and config.get("use_mention", True):
            ping_prefix = f"<@&{role_id}>\n"

        # Author/streamer name for template text
        author_name = config.get("role_name") or config.get("name") or BotStrings.get("DEFAULT_AUTHOR_STREAMER", "Streamer")

        if notif_type == "video":
            template_key = "video_template"
        elif notif_type == "start":
            template_key = "start_template"
        else:
            template_key = "end_template"

        custom_template = config.get(template_key)
        if not custom_template:
            custom_template = EmbedBuilderVideo._get_text_val(config, template_key, None)
        
        # Default template for video if custom is not set anywhere
        if not custom_template and notif_type == "video":
            custom_template = f"{LiveEmojis.VIDEO} **{{author}}** published a new video on **{{platform}}**!\n{LiveEmojis.CLAPPER} **{BotStrings.get('FIELD_TITLE_NAME', 'Title')}:** {{title}}\n{LiveEmojis.LINK} **Watch:** {{url}}"

        if custom_template:
            title = ""
            game = ""
            url = ""
            viewers = "0"
            
            if stream_info:
                title = stream_info.get("title", BotStrings.get("STREAM_WITHOUT_TITLE", "Stream without title") if not is_video else BotStrings.get("VIDEO_WITHOUT_TITLE", "Video without title"))
                game = stream_info.get("game", "")
                viewers = str(stream_info.get("viewers", 0))
                
                url = stream_info.get("url")
                if not url or url == "#":
                    platform_id = config.get("platform_id")
                    if platform_id:
                        from constants.base import VKAPI
                        url = f"https://{VKAPI.BASE_URL_VK_LIVE}/{platform_id}"
                    else:
                        url = ""

            platform_name = StreamNotificationHelper._get_platform_name(config, context)
            formatted_mirrors = StreamNotificationHelper._get_formatted_mirrors(config, is_video=is_video, game=game)
            
            default_ping_role_id = Config.DEFAULT_LIVE_PING_ROLE_ID
            ping_role_str = f"<@&{default_ping_role_id}>" if default_ping_role_id else (f"<@&{role_id}>" if role_id else "")

            live_role_id = config.get("live_role_id")
            live_role_str = f"<@&{live_role_id}>" if live_role_id else ""

            role_display = author_name if ("**{role}**" in custom_template or "**{author}**" in custom_template) else f"**{author_name}**"
            author_display = author_name if ("**{author}**" in custom_template or "**{role}**" in custom_template) else f"**{author_name}**"

            placeholders = {
                "role": role_display,
                "role_mention": f"<@&{role_id}>" if role_id else "",
                "role_name": author_name,
                "role_id": str(role_id) if role_id else "",
                "ping_role": ping_role_str,
                "live_role": live_role_str,
                "author": author_display,
                "name": author_name,
                "title": title,
                "game": game,
                "url": url,
                "viewers": viewers,
                "platform": platform_name,
                "mirrors": formatted_mirrors
            }
            
            formatted_text = StreamNotificationHelper._format_template(custom_template, placeholders)
            return f"{ping_prefix}{formatted_text}".strip()
            
        if ping_prefix:
            alert = LiveEmojis.VIDEO if notif_type == "video" else (LiveEmojis.ALERT if notif_type == "start" else "")
            return f"{ping_prefix.strip()} {alert}"
        return ""

    @staticmethod
    async def build_stream_start_notification(
        stream_info: Dict[str, Any], 
        config: Dict[str, Any], 
        context: str = "live_stream"
    ) -> Optional[dict]:
        """Creates an embed notification for stream start or video publication."""
        try:
            use_embed = config.get("use_embed", True)
            is_live_stream = "video" not in context.lower()
            notif_type = "start" if is_live_stream else "video"

            if not use_embed:
                await send_to_any_log("debug", f"Created text notification ({notif_type})", emoji=LogEmojis.INFO)
                return StreamNotificationHelper._build_text_notification(stream_info, config, notif_type, context)

            embed = await EmbedBuilderVideo.create_video_embed(
                video_data=stream_info,
                config=config,
                is_live=is_live_stream,
                context=context
            )
            game = stream_info.get("game") if stream_info else None
            if is_live_stream:
                await EmbedBuilderVideo.add_stream_fields(embed, stream_info, config)
            else:
                await EmbedBuilderVideo.add_mirrors_field(embed, config, is_video=True, game=game)
            await EmbedBuilderVideo.set_footer(embed, config)

            content = StreamNotificationHelper._get_notification_content(config, notif_type, stream_info, context)

            formatted_mirrors = StreamNotificationHelper._get_formatted_mirrors(config, is_video=not is_live_stream, game=game)
            if formatted_mirrors:
                template_key = "start_template" if is_live_stream else "video_template"
                custom_template = config.get(template_key)
                has_mirrors_placeholder = custom_template and "{mirrors}" in custom_template

                if not has_mirrors_placeholder:
                    label = BotStrings.get("STREAM_MIRROR_STREAM_LABEL", "Stream is also available on") if is_live_stream else BotStrings.get("STREAM_MIRROR_VIDEO_LABEL", "Video is also available on")
                    text_line = f"\n{LiveEmojis.TV} *{label}:* {formatted_mirrors}"
                    if text_line not in content:
                        if content:
                            content += text_line
                        else:
                            content = text_line

            await send_to_any_log("debug", f"Created embed notification ({notif_type})", emoji=LogEmojis.INFO)
            return {
                "content": content,
                "embeds": [embed]
            }
        except Exception as e:
            await send_to_any_log("error", f"Error creating notification ({notif_type}): {e}", emoji=LogEmojis.ERROR)
            return None

    @staticmethod
    async def build_stream_end_notification(
        stream_info: Dict[str, Any], 
        config: Dict[str, Any],
        context: str = "live_stream"
    ) -> Optional[dict]:
        """Creates a notification for stream end."""
        try:
            if not config.get("notify_stream_end", True):
                await send_to_any_log("debug", "Stream end notifications disabled in config", emoji=LogEmojis.INFO)
                return None

            use_embed = config.get("use_embed_end", config.get("use_embed", True))

            if not use_embed:
                await send_to_any_log("debug", "Created text notification for stream end", emoji=LogEmojis.INFO)
                return StreamNotificationHelper._build_text_notification(stream_info, config, "end", context)

            stream_url = stream_info.get("url")
            if not stream_url or stream_url == "#":
                platform_id = config.get("platform_id")
                if platform_id:
                    from constants.base import VKAPI
                    stream_url = f"https://{VKAPI.BASE_URL_VK_LIVE}/{platform_id}"
                else:
                    stream_url = None

            from modules_utils.random_resolver import resolve_random_value
            from modules_utils.helpers import parse_color_to_int
            
            raw_color = config.get("color_end") or config.get("end_color") or config.get("color")
            color_val = resolve_random_value(raw_color)
            default_color = parse_color_to_int(Config.EMBED_COLOR, 0xFF0000)
            if color_val is not None:
                if isinstance(color_val, int):
                    embed_color = color_val
                else:
                    embed_color = parse_color_to_int(str(color_val), default_color)
            else:
                embed_color = default_color

            embed = discord.Embed(
                title=f"{LiveEmojis.STREAM_END} Stream ended",
                description=f"**{stream_info.get('title', 'Untitled')}**",
                color=embed_color,
                url=stream_url
            )

            if stream_info.get("viewers"):
                embed.add_field(
                    name=f"{LiveEmojis.VIEWERS} Final viewer count",
                    value=f"{stream_info['viewers']}",
                    inline=True
                )

            end_image = (
                config.get("end_image_url")
                or config.get("offline_image_url")
                or config.get("end_image")
                or config.get("preview")
                or config.get("event_image")
            )
            if end_image:
                from modules_utils.random_resolver import resolve_random_value
                from modules_utils.helpers import resolve_asset_url
                resolved_end_img = resolve_asset_url(str(resolve_random_value(end_image)).strip())
                if resolved_end_img and EmbedBuilderVideo._is_valid_url(resolved_end_img):
                    from modules_utils.stream_preview_saver import save_stream_preview_image
                    stream_id = stream_info.get("stream_id") or stream_info.get("id")
                    platform = config.get("platform") or config.get("platform_name")
                    resolved_end_img = await save_stream_preview_image(resolved_end_img, stream_id=stream_id, platform=platform)
                    embed.set_image(url=resolved_end_img)

            end_thumb = (
                config.get("end_thumbnail_url")
                or config.get("embed_thumbnail_url")
            )
            if end_thumb:
                from modules_utils.random_resolver import resolve_random_value
                from modules_utils.helpers import resolve_asset_url
                resolved_thumb = resolve_asset_url(str(resolve_random_value(end_thumb)).strip())
                if resolved_thumb and EmbedBuilderVideo._is_valid_url(resolved_thumb):
                    embed.set_thumbnail(url=resolved_thumb)

            author_name = config.get("embed_author_name")
            if author_name:
                author_icon_url = await EmbedBuilderVideo._get_avatar_url(
                    config.get("embed_author_icon_url"),
                    config
                )
                embed.set_author(
                    name=author_name,
                    icon_url=str(author_icon_url) if author_icon_url else None
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

            await send_to_any_log("debug", "Created embed notification for stream end", emoji=LogEmojis.INFO)
            return {
                "content": StreamNotificationHelper._get_notification_content(config, "end", stream_info, context),
                "embeds": [embed]
            }
            
        except Exception as e:
            await send_to_any_log("error", f"Error creating notification for stream end: {e}", emoji=LogEmojis.ERROR)
            return None

    @staticmethod
    def _build_text_notification(
        stream_info: Dict[str, Any], 
        config: Dict[str, Any], 
        notification_type: str,
        context: str = "live_stream"
    ) -> dict:
        """Создаёт текстовое уведомление (без использования Embed)."""
        is_video = "video" in context.lower() or notification_type == "video"
        notif_type = "video" if is_video else notification_type

        # Если задан пользовательский шаблон, используем его
        if notif_type == "video":
            template_key = "video_template"
        elif notif_type == "start":
            template_key = "start_template"
        else:
            template_key = "end_template"

        if config.get(template_key) or (is_video and not config.get(template_key)):
            content = StreamNotificationHelper._get_notification_content(config, notif_type, stream_info, context)
            
            # Дописываем зеркала, если они заданы для стрима/видео и не упомянуты в шаблоне
            if notif_type in ("start", "video"):
                game = stream_info.get("game") if stream_info else None
                formatted_mirrors = StreamNotificationHelper._get_formatted_mirrors(config, is_video=is_video, game=game)
                if formatted_mirrors:
                    has_mirrors_placeholder = config.get(template_key) and "{mirrors}" in config.get(template_key)
                    
                    if not has_mirrors_placeholder:
                        mirrors_line = f"\n{LiveEmojis.TV} *{'Видео также доступно' if is_video else 'Трансляция также доступна'} на других платформах:* {formatted_mirrors}"
                        if mirrors_line not in content:
                            content += mirrors_line
            return {
                "content": content,
                "embeds": []
            }

        # Дефолтное текстовое оформление
        content_parts = []
        platform_name = StreamNotificationHelper._get_platform_name(config, context)
        
        role_id = (
            config.get("notification_role_id") or 
            config.get("role_id") or 
            Config.DEFAULT_LIVE_PING_ROLE_ID
        )
        if role_id:
            alert = LiveEmojis.VIDEO if is_video else (LiveEmojis.ALERT if notif_type == "start" else "")
            if config.get("use_mention", True):
                role_mention = f"<@&{role_id}>"
                content_parts.append(f"{role_mention} {alert}")
            else:
                role_text = config.get("role_name", "Стример")
                content_parts.append(f"**{role_text}** {alert}")

        game_part = f" | Играет в: {stream_info.get('game', '')}" if stream_info.get("game") else ""
        
        if is_video:
            stream_url = stream_info.get('url')
            message = f"{LiveEmojis.VIDEO} **{stream_info.get('title', 'Видео без названия')}**"
            if stream_url:
                message += f"\n{LiveEmojis.LINK} [Смотреть видео на {platform_name}]({stream_url})"

            formatted_mirrors = StreamNotificationHelper._get_formatted_mirrors(config, is_video=True, game=stream_info.get("game"))
            if formatted_mirrors:
                message += f"\n{LiveEmojis.TV} *Видео также доступно на других платформах:* {formatted_mirrors}"
        elif notif_type == "start":
            stream_url = stream_info.get('url')
            if not stream_url or stream_url == "#":
                platform_id = config.get("platform_id")
                if platform_id:
                    from constants.base import VKAPI
                    stream_url = f"https://{VKAPI.BASE_URL_VK_LIVE}/{platform_id}"
                else:
                    stream_url = ""

            message = f"{LiveEmojis.STREAM_START} **{stream_info.get('title', 'Стрим без названия')}**{game_part}"
            if stream_url:
                message += f"\n{LiveEmojis.LINK} [Смотреть стрим на {platform_name}]({stream_url})"

            formatted_mirrors = StreamNotificationHelper._get_formatted_mirrors(config, is_video=False, game=stream_info.get("game"))
            if formatted_mirrors:
                message += f"\n{LiveEmojis.TV} *Трансляция на других платформах:* {formatted_mirrors}"
        else:
            message = f"{LiveEmojis.STREAM_END} Стрим **{stream_info.get('title', 'Без названия')}** на {platform_name} завершен."

        content_parts.append(message)
        content = "\n".join(content_parts)

        return {
            "content": content,
            "embeds": []
        }

    @staticmethod
    def _get_telegram_formatted_mirrors(config: Dict[str, Any], is_video: bool = False, game: Optional[str] = None) -> str:
        """Возвращает форматированную строку зеркал с HTML-ссылками для Telegram."""
        from modules_utils.mirrors_resolver import resolve_mirrors
        mirrors_list = resolve_mirrors(config, is_video=is_video, game=game)

        if mirrors_list:
            import html
            return ", ".join(f'<a href="{html.escape(plat_url)}">{html.escape(plat_name)}</a>' for plat_name, plat_url in mirrors_list)
        return ""

    @staticmethod
    def _get_telegram_notification_content(
        config: Dict[str, Any], 
        notification_type: str, 
        stream_info: Optional[Dict[str, Any]] = None,
        context: str = "live_stream"
    ) -> str:
        """Возвращает форматированный HTML-контент для уведомления в Telegram."""
        import html
        import re
        
        # Единственная поддерживаемая форма конфигурации — вложенный блок telegram_notifications
        tg_config = config.get("telegram_notifications")
        template = None
        
        if isinstance(tg_config, dict):
            if notification_type == "start":
                template = tg_config.get("start_template")
            elif notification_type == "end":
                template = tg_config.get("end_template")
            elif notification_type == "video":
                template = tg_config.get("video_template")
        
        if not template:
            # Нет кастомного TG-шаблона в telegram_notifications — используем обычный шаблон канала
            fallback_key = "start_template" if notification_type in ("start", "video") else "end_template"
            template = config.get(fallback_key)
        
        # Если вообще нет шаблона, используем дефолтные HTML шаблоны
        if not template:
            if notification_type == "start":
                template = BotStrings.TG_START_TEMPLATE_FALLBACK
            elif notification_type == "video":
                template = BotStrings.TG_VIDEO_TEMPLATE_FALLBACK
            else:
                template = BotStrings.TG_END_TEMPLATE_FALLBACK

        title = ""
        game = ""
        url = ""
        viewers = "0"
        
        if stream_info:
            title = html.escape(stream_info.get("title", "Стрим без названия"))
            game = html.escape(stream_info.get("game", ""))
            viewers = str(stream_info.get("viewers", 0))
            
            raw_url = stream_info.get("url")
            if not raw_url or raw_url == "#":
                platform_id = config.get("platform_id")
                if platform_id:
                    from constants.base import VKAPI
                    raw_url = f"https://{VKAPI.BASE_URL_VK_LIVE}/{platform_id}"
                else:
                    raw_url = ""
            url = html.escape(raw_url) if raw_url else ""

        platform_name = html.escape(StreamNotificationHelper._get_platform_name(config, context))
        is_video_notification = notification_type == "video"
        formatted_mirrors = StreamNotificationHelper._get_telegram_formatted_mirrors(
            config, is_video=is_video_notification, game=stream_info.get("game") if stream_info else None
        )
        
        # Для роли в Telegram
        role_name = config.get("role_name") or config.get("name") or "Стример"
        role_str = f"<b>{html.escape(role_name)}</b>"
        
        placeholders = {
            "role": role_str,
            "name": html.escape(config.get("name") or role_name),
            "author": html.escape(config.get("name") or role_name),
            "title": title,
            "game": game,
            "url": url,
            "viewers": viewers,
            "platform": platform_name,
            "mirrors": formatted_mirrors
        }
        
        # Форматируем
        content = StreamNotificationHelper._format_template(template, placeholders)
        
        # Конвертируем Markdown-разметку (если осталась или была задана) в HTML
        # 1. Удаляем упоминания Discord
        content = re.sub(r'<@&\d+>', '', content)
        content = re.sub(r'<@\d+>', '', content)
        
        # 2. Конвертируем Discord/Markdown в HTML
        # Мы делаем это так, чтобы не сломать уже вставленные HTML-теги/ссылки ({mirrors} или {url}).
        # Сначала временно заменяем `<a href="...">...</a>` и другие теги на плейсхолдеры.
        links = []
        def save_link(match):
            links.append(match.group(0))
            return f"__LINK_PLACEHOLDER_{len(links)-1}__"
        
        content = re.sub(r'<a href=".*?">.*?</a>', save_link, content)
        content = re.sub(r'<b>.*?</b>', save_link, content) # также сохраняем уже готовые жирные теги
        content = re.sub(r'<i>.*?</i>', save_link, content) # сохраняем курсивы
        content = re.sub(r'<u>.*?</u>', save_link, content) # сохраняем подчеркивания
        content = re.sub(r'<code>.*?</code>', save_link, content) # сохраняем код
        
        # Теперь заменяем Markdown
        content = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', content)
        content = re.sub(r'\*(.*?)\*', r'<i>\1</i>', content)
        content = re.sub(r'__(.*?)__', r'<u>\1</u>', content)
        content = re.sub(r'`(.*?)`', r'<code>\1</code>', content)
        # Discord ссылки [текст](урл)
        content = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', content)
        
        # Возвращаем сохраненные HTML-теги обратно
        for i, link in enumerate(links):
            content = content.replace(f"__LINK_PLACEHOLDER_{i}__", link)
            
        # Добавляем текстовое примечание о зеркалах в конец контента сообщения, если они есть и не использовались в шаблоне
        if formatted_mirrors and notification_type in ("start", "video"):
            has_mirrors_placeholder = "{mirrors}" in template
            if not has_mirrors_placeholder:
                label = "Видео также доступно на" if is_video_notification else "Стрим также доступен на"
                text_line = f"\n{LiveEmojis.TV} <b>{label}:</b> {formatted_mirrors}"
                if text_line not in content:
                    content += text_line

        return content

    @staticmethod
    def _build_telegram_inline_keyboard(config: Dict[str, Any], stream_info: Optional[Dict[str, Any]] = None, notification_type: str = "start") -> Optional[Dict[str, Any]]:
        """
        Строит inline-клавиатуру для Telegram с кнопками на стрим и зеркала.
        """
        if notification_type not in ("start", "video"):
            return None
            
        buttons = []
        
        # 1. Ссылка на основной стрим/видео
        main_url = None
        if stream_info:
            main_url = stream_info.get("url")
            if not main_url or main_url == "#":
                platform_id = config.get("platform_id")
                if platform_id:
                    from constants.base import VKAPI
                    main_url = f"https://{VKAPI.BASE_URL_VK_LIVE}/{platform_id}"
                else:
                    main_url = None

        if main_url:
            platform_lower = config.get("platform", "").lower() or "stream"
            # Определим эмодзи для основной платформы
            if "youtube" in platform_lower:
                main_emoji = LiveEmojis.RED_CIRCLE
                plat_text = "YouTube"
            elif "twitch" in platform_lower:
                main_emoji = LiveEmojis.PURPLE_CIRCLE
                plat_text = "Twitch"
            elif "vk_com" in platform_lower:
                main_emoji = LiveEmojis.BLUE_CIRCLE
                plat_text = "VK.com"
            elif "goodgame" in platform_lower:
                main_emoji = LiveEmojis.ORANGE_CIRCLE
                plat_text = "GoodGame"
            elif "vk" in platform_lower or "vkvideo" in platform_lower:
                main_emoji = LiveEmojis.BLUE_CIRCLE
                plat_text = "VK Video"
            elif "rutube" in platform_lower:
                main_emoji = LiveEmojis.GREEN_CIRCLE
                plat_text = "Rutube"
            elif "kick" in platform_lower:
                main_emoji = LiveEmojis.GREEN_CIRCLE
                plat_text = "Kick"
            elif "trovo" in platform_lower:
                main_emoji = LiveEmojis.LIGHT_GREEN_CIRCLE
                plat_text = "Trovo"
            else:
                main_emoji = LiveEmojis.TV
                plat_text = config.get("platform") or "Смотреть"
                
            buttons.append({
                "text": f"{main_emoji} {plat_text}",
                "url": main_url
            })
            
        # 2. Зеркала
        from modules_utils.mirrors_resolver import resolve_mirrors
        mirrors_list = resolve_mirrors(
            config,
            is_video=(notification_type == "video"),
            game=stream_info.get("game") if stream_info else None
        )
        for plat_name, plat_url in mirrors_list:
            # Определим эмодзи для зеркала
            plat_name_lower = plat_name.lower()
            if "twitch" in plat_name_lower:
                mirror_emoji = LiveEmojis.PURPLE_CIRCLE
            elif "vk" in plat_name_lower or "vkvideo" in plat_name_lower:
                mirror_emoji = LiveEmojis.BLUE_CIRCLE
            elif "youtube" in plat_name_lower:
                mirror_emoji = LiveEmojis.RED_CIRCLE
            elif "rutube" in plat_name_lower:
                mirror_emoji = LiveEmojis.GREEN_CIRCLE
            elif "kick" in plat_name_lower:
                mirror_emoji = LiveEmojis.GREEN_CIRCLE
            elif "goodgame" in plat_name_lower:
                mirror_emoji = LiveEmojis.ORANGE_CIRCLE
            elif "trovo" in plat_name_lower:
                mirror_emoji = LiveEmojis.LIGHT_GREEN_CIRCLE
            else:
                mirror_emoji = LiveEmojis.LINK

            buttons.append({
                "text": f"{mirror_emoji} {plat_name}",
                "url": plat_url
            })
                
        if not buttons:
            return None
            
        # Сгруппируем кнопки по 2 в ряд для красивого вида
        keyboard = []
        row = []
        for btn in buttons:
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
            
        return {"inline_keyboard": keyboard}

    @staticmethod
    async def send_telegram_notification(
        stream_info: Dict[str, Any],
        config: Dict[str, Any],
        notification_type: str,  # "start", "end", "video"
        context: str = "live_stream"
    ) -> bool:
        """
        Отправляет уведомление в Telegram.

        Единственная поддерживаемая форма конфигурации канала — вложенный блок
        telegram_notifications: {"enabled": bool, "start_template": ..., "end_template": ..., "video_template": ...}.
        bot_token/chat_id/thread_id по умолчанию берутся из env
        (Config.TELEGRAM_STREAM_BOT_TOKEN / TELEGRAM_STREAM_CHAT_ID / TELEGRAM_STREAM_THREAD_ID).
        TELEGRAM_BOT_TOKEN (бот голосовых уведомлений) сюда не подставляется даже как резерв —
        без TELEGRAM_STREAM_BOT_TOKEN стрим-уведомления в Telegram не отправляются;
        при желании их всё ещё можно точечно переопределить полями chat_id/bot_token/thread_id
        внутри telegram_notifications для конкретного канала — тогда они имеют приоритет над env.
        Поддерживает отправку большого превью (картинки) сверху и кнопок (зеркал).
        """
        # Настройки Telegram канала (если модуль включен для этого стримера)
        tg_config = config.get("telegram_notifications")
        if not isinstance(tg_config, dict) or not tg_config.get("enabled", True):
            return False

        tg_channel_id = tg_config.get("chat_id")
        tg_token = tg_config.get("bot_token")
        tg_thread_id = tg_config.get("thread_id")

        # Токен, chat_id и thread_id по умолчанию берём из env; JSON может переопределить точечно.
        # TELEGRAM_BOT_TOKEN сюда НЕ подставляется — это токен другого бота (голосовые уведомления).
        if not tg_token:
            tg_token = getattr(Config, 'TELEGRAM_STREAM_BOT_TOKEN', None)
        if not tg_channel_id:
            tg_channel_id = getattr(Config, 'TELEGRAM_STREAM_CHAT_ID', None)
        if not tg_thread_id:
            tg_thread_id = getattr(Config, 'TELEGRAM_STREAM_THREAD_ID', None)

        if not tg_channel_id:
            return False

        if not tg_token:
            await send_to_any_log("error", f"Bot token is not set for sending TG notifications for {config.get('name')}", emoji=LogEmojis.ERROR)
            return False
        
        # Get formatted content
        content = StreamNotificationHelper._get_telegram_notification_content(
            config=config,
            notification_type=notification_type,
            stream_info=stream_info,
            context=context
        )
        
        # Build inline keyboard
        reply_markup = StreamNotificationHelper._build_telegram_inline_keyboard(
            config=config,
            stream_info=stream_info,
            notification_type=notification_type
        )
        
        # Try to get preview image
        photo_url = EmbedBuilderVideo._get_preview_url(
            video_data=stream_info,
            config=config,
            is_live=(notification_type == "start")
        )
        
        if photo_url and notification_type in ("start", "end", "video"):
            from modules_utils.stream_preview_saver import save_stream_preview_image
            stream_id = stream_info.get("stream_id") or stream_info.get("id")
            platform = config.get("platform") or config.get("platform_name")
            photo_url = await save_stream_preview_image(photo_url, stream_id=stream_id, platform=platform)

        import os
        is_photo_valid = photo_url and (photo_url.startswith("http://") or photo_url.startswith("https://") or os.path.isfile(photo_url))
        
        import json
        from modules_utils.http_client import HttpClient
        
        # Configure common parameters
        params = {
            "chat_id": str(tg_channel_id).strip(),
            "parse_mode": "HTML"
        }
        if tg_thread_id:
            try:
                params["message_thread_id"] = int(tg_thread_id)
            except (ValueError, TypeError):
                pass
                
        if reply_markup:
            params["reply_markup"] = json.dumps(reply_markup)
            
        use_photo = is_photo_valid and len(content) <= 1024 and notification_type in ("start", "video")
        
        try:
            await send_to_any_log("debug", f"Sending notification ({notification_type}) to Telegram chat {tg_channel_id} (use_photo={use_photo})...", emoji=LogEmojis.INFO)
            
            if use_photo:
                url = f"https://api.telegram.org/bot{tg_token}/sendPhoto"
                if photo_url and os.path.isfile(photo_url):
                    import aiohttp
                    form_data = aiohttp.FormData()
                    for k, v in params.items():
                        form_data.add_field(k, str(v))
                    form_data.add_field("caption", content)
                    with open(photo_url, "rb") as f:
                        form_data.add_field("photo", f.read(), filename=os.path.basename(photo_url))
                    result = await HttpClient.post(url, data=form_data, error_level="error")
                else:
                    params["photo"] = photo_url
                    params["caption"] = content
                    result = await HttpClient.post(url, json=params, error_level="error")
            else:
                url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
                params["text"] = content
                params["disable_web_page_preview"] = False
                result = await HttpClient.post(url, json=params, error_level="error")
            
            if result is None and use_photo:
                await send_to_any_log("warning", f"Failed to send photo notification for {config.get('name')}, falling back to text message...", emoji=LogEmojis.WARNING)
                url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
                if "photo" in params:
                    del params["photo"]
                if "caption" in params:
                    del params["caption"]
                params["text"] = content
                params["disable_web_page_preview"] = False
                result = await HttpClient.post(url, json=params, error_level="error")
                
            if result is None:
                await send_to_any_log("error", f"Failed to send Telegram notification for {config.get('name')}", emoji=LogEmojis.ERROR)
                return False
                
            await send_to_any_log("info", f"Successfully sent notification ({notification_type}) to Telegram for {config.get('name')}", emoji=LogEmojis.SUCCESS)
            return True
        except Exception as e:
            # Mask token in logs
            safe_e = str(e).replace(tg_token, "***MASKED***") if tg_token else str(e)
            await send_to_any_log("error", f"Error sending Telegram notification: {safe_e}", emoji=LogEmojis.ERROR)
            return False

