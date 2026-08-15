# modules/standalone/secret_vendors_module.py
import asyncio
import json
import os
import pytz
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from settings.config import Config
from settings.data_files import Files
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, Emojis, VendorEmojis
from constants.strings import BotStrings
from modules_utils.helpers import safe_create_task, resolve_asset_url, parse_color_to_int, load_webhooks_metadata
from modules_utils.cache_utils import load_json_cache, save_json_cache_async


MSK_TZ = pytz.timezone("Europe/Moscow")

RU_DAYS = {i: day for i, day in enumerate(BotStrings.get("VENDOR_DAYS_RU", ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]))}

RU_DAYS_SHORT = {i: day for i, day in enumerate(BotStrings.get("VENDOR_DAYS_SHORT_RU", ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]))}

# Расписание работы секретных торговцев в МСК (день недели 0..6, час, минута, статус):
# 0 = Понедельник, 1 = Вторник, 2 = Среда, 3 = Четверг, 4 = Пятница, 5 = Суббота, 6 = Воскресенье
# Работают 24ч, отдыхают 32ч
SCHEDULE_EVENTS = [
    (0, 3, 0, "OPEN"),     # Пн 03:00 МСК — Открываются
    (1, 3, 0, "CLOSED"),   # Вт 03:00 МСК — Закрываются
    (2, 11, 0, "OPEN"),    # Ср 11:00 МСК — Открываются
    (3, 11, 0, "CLOSED"),  # Чт 11:00 МСК — Закрываются
    (4, 19, 0, "OPEN"),    # Пт 19:00 МСК — Открываются
    (5, 19, 0, "CLOSED"),  # Сб 19:00 МСК — Закрываются
]


def get_vendor_schedule_info(now_dt_msk: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Вычисляет текущий статус секретных торговцев (Дэнни и Кэйси), 
    прошедшее событие и следующее изменение статуса.
    """
    if now_dt_msk is None:
        now_dt_msk = datetime.now(MSK_TZ)
    elif now_dt_msk.tzinfo is None:
        now_dt_msk = MSK_TZ.localize(now_dt_msk)

    current_monday = (now_dt_msk.date() - timedelta(days=now_dt_msk.weekday()))

    all_events = []
    for week_offset in [-1, 0, 1]:
        monday_date = current_monday + timedelta(weeks=week_offset)
        for day_offset, hour, minute, status in SCHEDULE_EVENTS:
            event_date = monday_date + timedelta(days=day_offset)
            event_naive = datetime(event_date.year, event_date.month, event_date.day, hour, minute, 0)
            event_dt = MSK_TZ.localize(event_naive)
            all_events.append((event_dt, status))

    all_events.sort(key=lambda x: x[0])

    last_event_dt = None
    last_status = "CLOSED"
    for ev_dt, status in all_events:
        if ev_dt <= now_dt_msk:
            last_event_dt = ev_dt
            last_status = status
        else:
            break

    next_event_dt = None
    next_status = "OPEN"
    for ev_dt, status in all_events:
        if ev_dt > now_dt_msk:
            next_event_dt = ev_dt
            next_status = status
            break

    time_until_next = next_event_dt - now_dt_msk if next_event_dt else timedelta(0)
    total_seconds = max(0, int(time_until_next.total_seconds()))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    if hours > 0:
        formatted_remaining = BotStrings.get("TIME_HOURS_MIN", "{hours} ч. {minutes} мин.").format(hours=hours, minutes=minutes)
    else:
        formatted_remaining = BotStrings.get("TIME_MIN", "{minutes} мин.").format(minutes=minutes)

    event_key = f"{last_event_dt.strftime('%Y-%m-%d_%H:%M')}_{last_status}" if last_event_dt else "INIT"

    return {
        "status": last_status,
        "is_open": (last_status == "OPEN"),
        "last_event_dt": last_event_dt,
        "last_event_key": event_key,
        "next_event_dt": next_event_dt,
        "next_status": next_status,
        "time_until_next": time_until_next,
        "formatted_remaining": formatted_remaining,
        "now_dt_msk": now_dt_msk,
    }


class SecretVendorsModule(commands.Cog):
    """
    Модуль отслеживания открытия и закрытия секретных торговцев (Дэнни и Кэйси) в The Division 2.
    Поддерживает отправку через Discord Webhook и полную настройку параметров Embed через JSON.
    """

    def __init__(self, bot):
        self.bot = bot
        self.is_running = False
        self.loop_task = None
        self.cache_file = Files.SECRET_VENDORS_CACHE_FILE
        self.config_file = Files.SECRET_VENDORS_CONFIG_FILE
        self.cache = self._load_cache()
        self.module_config = self._load_module_config()

    def _load_cache(self) -> dict:
        return load_json_cache(self.cache_file)

    async def _save_cache(self):
        try:
            await save_json_cache_async(self.cache_file, self.cache)
        except Exception as e:
            await send_to_any_log("error", f"SecretVendors: error saving cache: {e}", emoji=LogEmojis.ERROR)

    def _get_default_config(self) -> dict:
        game_icon = "assets/images/bot-image/thedivision2-icon.png"
        preview_img = "assets/images/bot-image/torg.jpg"
        return {
            "webhook_url": getattr(Config, "SECRET_VENDORS_WEBHOOK_URL", ""),
            "webhook_username": BotStrings.get("VENDOR_DEFAULT_NAME", "Секретные торговцы"),
            "webhook_avatar_url": game_icon,
            "channel_id": getattr(Config, "SECRET_VENDORS_CHANNEL_ID", None),
            "ping_role_id": getattr(Config, "SECRET_VENDORS_ROLE_ID", None),
            "catalog_url": "https://rubenalamina.mx/the-division-weekly-vendor-reset/",
            "guide_url": "https://discord.com/channels/835802952521351180/1082282584886738964",
            "author_name": "The Division 2",
            "author_icon_url": game_icon,
            "content_template": "{role_ping}",
            "open_title": BotStrings.get("VENDOR_OPEN_TITLE_DEFAULT", "{emoji} Секретные торговцы открыты!").format(emoji=VendorEmojis.OPEN),
            "close_title": BotStrings.get("VENDOR_CLOSE_TITLE_DEFAULT", "{emoji} Секретные торговцы закрыты!").format(emoji=VendorEmojis.CLOSED),
            "open_color": "46, 204, 113",
            "close_color": "231, 76, 60",
            "description_template": BotStrings.get("VENDOR_DESC_TEMPLATE", (
                "В этом канале публикуются уведомления о начале и конце работы двух секретных торговцев: **Дэнни (слева)** и **Кэйси (справа)**.\n\n"
                "{emoji_location} **Как найти торговцев**: [Товары недели, Дэнни и Мендоза]({guide_url})\n"
                "{emoji_link} **Еженедельный каталог торговцев**: [Перейти к каталогу]({catalog_url})"
            )),
            "open_status_template": BotStrings.get("VENDOR_OPEN_STATUS_DEFAULT", "{emoji} **Открыты** (до {{next_day_ru}} {{next_time_str}} МСК)").format(emoji=VendorEmojis.OPEN),
            "close_status_template": BotStrings.get("VENDOR_CLOSE_STATUS_DEFAULT", "{emoji} **Закрыты** (до {{next_day_ru}} {{next_time_str}} МСК)").format(emoji=VendorEmojis.CLOSED),
            "fields": [
                {
                    "name": BotStrings.get("VENDOR_FIELD_STATUS_NAME", "{emoji} Статус").format(emoji=VendorEmojis.STATUS),
                    "value": BotStrings.get("VENDOR_FIELD_STATUS_VALUE", "{status_text}\n{emoji} **Осталось времени**: {formatted_remaining}").format(emoji=VendorEmojis.TIME_REMAINING, status_text="{status_text}", formatted_remaining="{formatted_remaining}"),
                    "inline": False
                },
                {
                    "name": BotStrings.get("VENDOR_FIELD_ASSORTMENT_NAME", "{emoji} Ассортимент торговцев").format(emoji=VendorEmojis.ASSORTMENT),
                    "value": BotStrings.get("VENDOR_FIELD_ASSORTMENT_VALUE", (
                        "{emoji} **Дэнни (слева)** — торгует контейнерами, продает их за текстиль (желтая валюта гардероба).\n"
                        "{emoji} **Кэйси (справа)** — снаряжение, продает их за обычные кредиты (деньги)."
                    )).replace("{emoji}", VendorEmojis.BULLET),
                    "inline": False
                },
                {
                    "name": BotStrings.get("VENDOR_FIELD_SCHEDULE_NAME", "{emoji} Расписание работы").format(emoji=VendorEmojis.SCHEDULE),
                    "value": BotStrings.get("VENDOR_FIELD_SCHEDULE_VALUE", (
                        "Секретные торговцы работают **24 часа**, после чего **\"отдыхают\" 32 часа**. Меняют свое местоположение вместе с еженедельным сбросом.\n\n"
                        "{emoji} **Открывается**: Понедельник 03:00 МСК\n"
                        "{emoji} **Закрывается**: Вторник 03:00 МСК\n"
                        "{emoji} **Открывается**: Среда 11:00 МСК\n"
                        "{emoji} **Закрывается**: Четверг 11:00 МСК\n"
                        "{emoji} **Открывается**: Пятница 19:00 МСК\n"
                        "{emoji} **Закрывается**: Суббота 19:00 МСК"
                    )).replace("{emoji}", VendorEmojis.BULLET),
                    "inline": False
                }
            ],
            "image_url": preview_img,
            "thumbnail_url": game_icon,
            "footer_text": BotStrings.get("VENDOR_FOOTER_TEXT", "The Division 2 • Секретные торговцы"),
            "footer_icon_url": game_icon
        }

    def _load_module_config(self) -> dict:
        default_config = self._get_default_config()

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_config.update(data)
            except Exception as e:
                safe_create_task(send_to_any_log("error", f"SecretVendors: error reading {self.config_file}: {e}", emoji=LogEmojis.ERROR))
        else:
            try:
                os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, ensure_ascii=False, indent=2)
            except Exception as e:
                safe_create_task(send_to_any_log("error", f"SecretVendors: error creating {self.config_file}: {e}", emoji=LogEmojis.ERROR))

        return default_config

    def reload_config(self) -> dict:
        """Перезагружает конфигурацию из JSON файла."""
        self.module_config = self._load_module_config()
        return self.module_config

    def _save_module_config(self):
        """Сохраняет текущую конфигурацию модуля в JSON файл."""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.module_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"SecretVendors: error saving {self.config_file}: {e}", emoji=LogEmojis.ERROR))

    def get_config_embed(self) -> discord.Embed:
        """Генерирует Embed с текущей конфигурацией вебхука и настроек торговцев."""
        webhook_url = self.module_config.get("webhook_url", "")
        username = self.module_config.get("webhook_username", BotStrings.get("VENDOR_DEFAULT_NAME", "Секретные торговцы"))
        avatar_url = self.module_config.get("webhook_avatar_url", "")
        channel_id = self.module_config.get("channel_id")
        ping_role_id = self.module_config.get("ping_role_id")
        open_color = self.module_config.get("open_color", "46, 204, 113")
        close_color = self.module_config.get("close_color", "231, 76, 60")

        embed = discord.Embed(
            title=f"{VendorEmojis.GEAR} {BotStrings.get('VENDOR_EMBED_TITLE', 'Настройки вебхука и уведомлений торговцев')}",
            color=discord.Color.blue()
        )
        not_set_str = BotStrings.get("VENDOR_CFG_NOT_SET", "*Не задан*")
        not_set_female_str = BotStrings.get("VENDOR_CFG_NOT_SET_FEMALE", "*Не задана*")
        default_str = BotStrings.get("VENDOR_CFG_DEFAULT", "*По умолчанию*")

        embed.add_field(
            name=f"{VendorEmojis.LINK} Webhook URL",
            value=f"`{webhook_url}`" if webhook_url else not_set_str,
            inline=False
        )
        embed.add_field(
            name=f"{VendorEmojis.USER} {BotStrings.get('VENDOR_CFG_FIELD_NAME', 'Имя вебхука')}",
            value=f"`{username}`",
            inline=True
        )
        embed.add_field(
            name=f"{VendorEmojis.AVATAR} {BotStrings.get('VENDOR_CFG_FIELD_AVATAR', 'Аватар вебхука')}",
            value=f"`{avatar_url}`" if avatar_url else default_str,
            inline=True
        )
        embed.add_field(
            name=f"{VendorEmojis.CHANNEL} {BotStrings.get('VENDOR_CFG_FIELD_CHANNEL', 'Канал (фоллбэк)')}",
            value=f"<#{channel_id}>" if channel_id else not_set_str,
            inline=True
        )
        embed.add_field(
            name=f"{VendorEmojis.ROLE} {BotStrings.get('VENDOR_CFG_FIELD_ROLE', 'Роль для пинга')}",
            value=f"<@&{ping_role_id}>" if ping_role_id else not_set_female_str,
            inline=True
        )
        embed.add_field(
            name=f"{VendorEmojis.OPEN} {BotStrings.get('VENDOR_CFG_FIELD_OPEN_COLOR', 'Цвет открыто (RGB)')}",
            value=f"`{open_color}`",
            inline=True
        )
        embed.add_field(
            name=f"{VendorEmojis.CLOSED} {BotStrings.get('VENDOR_CFG_FIELD_CLOSE_COLOR', 'Цвет закрыто (RGB)')}",
            value=f"`{close_color}`",
            inline=True
        )

        resolved_avatar = resolve_asset_url(avatar_url) if avatar_url else None
        if resolved_avatar and (resolved_avatar.startswith('http://') or resolved_avatar.startswith('https://')):
            embed.set_thumbnail(url=resolved_avatar)

        return embed

    async def start(self):
        """Запускает фоновую проверку расписания торговцев."""
        if self.is_running:
            return

        self.is_running = True
        webhook_url = self.get_webhook_url()
        channel_id = self.get_target_channel_id()

        log_msg = f"SecretVendors module started."
        if webhook_url:
            log_msg += f" Delivery method: Webhook ({webhook_url[:30]}...)"
        elif channel_id:
            channel = self.bot.get_channel(channel_id)
            ch_name = f"'{channel.name}'" if channel else str(channel_id)
            log_msg += f" Delivery method: Discord channel ({ch_name})"
        else:
            log_msg += " (Warning: webhook_url and channel_id not configured)"

        await send_to_any_log("info", log_msg, emoji=LogEmojis.STARTUP)
        self.loop_task = safe_create_task(self._schedule_loop())

    async def stop(self):
        """Останавливает модуль."""
        self.is_running = False
        if self.loop_task:
            self.loop_task.cancel()
            self.loop_task = None
        await self._save_cache()
        await send_to_any_log("info", "SecretVendors module stopped.", emoji=LogEmojis.INFO)

    def get_webhook_url(self) -> Optional[str]:
        url = self.module_config.get("webhook_url") or getattr(Config, "SECRET_VENDORS_WEBHOOK_URL", "")
        if url and isinstance(url, str) and url.strip():
            return url.strip()
        return None

    def get_target_channel_id(self) -> Optional[int]:
        ch_id = self.module_config.get("channel_id") or getattr(Config, "SECRET_VENDORS_CHANNEL_ID", None)
        if ch_id:
            try:
                return int(ch_id)
            except ValueError:
                return None
        return None

    def get_ping_role_id(self) -> Optional[int]:
        role_id = self.module_config.get("ping_role_id") or getattr(Config, "SECRET_VENDORS_ROLE_ID", None)
        if role_id:
            try:
                return int(role_id)
            except ValueError:
                return None
        return None

    def _resolve_local_file(self, path_or_url: str) -> Optional[str]:
        """
        Проверяет, является ли значение пути локальным файлом на сервере.
        Возвращает абсолютный путь или None, если это HTTP URL или несуществующий файл.
        """
        if not path_or_url or not isinstance(path_or_url, str):
            return None
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return None

        candidates = [
            path_or_url,
            os.path.abspath(path_or_url),
            os.path.join(os.getcwd(), path_or_url),
            os.path.join(os.path.dirname(self.config_file), path_or_url)
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    def build_vendors_embed_and_files(self, info: Dict[str, Any]) -> Tuple[discord.Embed, List[discord.File]]:
        """
        Формирует discord.Embed и подготавливает локальные файлы discord.File 
        на основе загруженного JSON-конфига и текущего состояния торговцев.
        """
        cfg = self.reload_config()
        is_open = info["is_open"]
        next_dt = info["next_event_dt"]
        next_day_ru = RU_DAYS.get(next_dt.weekday(), "") if next_dt else ""
        next_time_str = next_dt.strftime("%H:%M") if next_dt else ""
        catalog_url = cfg.get("catalog_url", "https://rubenalamina.mx/the-division-weekly-vendor-reset/")
        guide_url = cfg.get("guide_url", "https://discord.com/channels/835802952521351180/1082282584886738964")

        default_open_status = f"{VendorEmojis.OPEN} **Открыты** (до {{next_day_ru}} {{next_time_str}} МСК)"
        default_close_status = f"{VendorEmojis.CLOSED} **Закрыты** (до {{next_day_ru}} {{next_time_str}} МСК)"
        default_open_title = f"{VendorEmojis.OPEN} Секретные торговцы открыты!"
        default_close_title = f"{VendorEmojis.CLOSED} Секретные торговцы закрыты!"

        if is_open:
            status_template = cfg.get("open_status_template", default_open_status)
            title_template = cfg.get("open_title", default_open_title)
            color_val = cfg.get("open_color", "46, 204, 113")
        else:
            status_template = cfg.get("close_status_template", default_close_status)
            title_template = cfg.get("close_title", default_close_title)
            color_val = cfg.get("close_color", "231, 76, 60")

        # Обработка цвета
        default_color = 0x2ECC71 if is_open else 0xE74C3C
        color = parse_color_to_int(color_val, default=default_color)

        fmt_kwargs = {
            "catalog_url": catalog_url,
            "guide_url": guide_url,
            "next_day_ru": next_day_ru,
            "next_time_str": next_time_str,
            "formatted_remaining": info.get("formatted_remaining", ""),
            "status": info.get("status", ""),
            "emoji_open": VendorEmojis.OPEN,
            "emoji_closed": VendorEmojis.CLOSED,
            "emoji_location": VendorEmojis.LOCATION,
            "emoji_link": VendorEmojis.LINK,
            "emoji_status": VendorEmojis.STATUS,
            "emoji_time": VendorEmojis.TIME_REMAINING,
            "emoji_assortment": VendorEmojis.ASSORTMENT,
            "emoji_schedule": VendorEmojis.SCHEDULE,
            "emoji_bullet": VendorEmojis.BULLET,
            "emoji_success": VendorEmojis.SUCCESS,
            "emoji_error": VendorEmojis.ERROR,
        }

        try:
            status_text = status_template.format(**fmt_kwargs)
        except Exception:
            status_text = f"**{'Открыты' if is_open else 'Закрыты'}**"

        fmt_kwargs["status_text"] = status_text

        try:
            title = title_template.format(**fmt_kwargs)
        except Exception:
            title = "Секретные торговцы"

        description_template = cfg.get("description_template", "")
        try:
            description = description_template.format(**fmt_kwargs)
        except Exception:
            description = description_template

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=info.get("now_dt_msk")
        )

        files: List[discord.File] = []

        # Шапка embed'а (author) — иконка + текст над заголовком
        author_name = cfg.get("author_name", "")
        author_icon_setting = cfg.get("author_icon_url", "")
        if author_name or author_icon_setting:
            author_icon_url = None
            if author_icon_setting:
                local_path = self._resolve_local_file(author_icon_setting)
                if local_path:
                    filename = f"author_{os.path.basename(local_path)}"
                    files.append(discord.File(local_path, filename=filename))
                    author_icon_url = f"attachment://{filename}"
                else:
                    author_icon_url = author_icon_setting
            embed.set_author(name=author_name or "\u200b", icon_url=author_icon_url)

        # Кастомные поля (fields) из JSON
        fields = cfg.get("fields", [])
        if isinstance(fields, list):
            for field in fields:
                if not isinstance(field, dict):
                    continue
                fname_tpl = field.get("name", "")
                fval_tpl = field.get("value", "")
                inline = bool(field.get("inline", False))

                try:
                    fname = fname_tpl.format(**fmt_kwargs)
                except Exception:
                    fname = fname_tpl

                try:
                    fval = fval_tpl.format(**fmt_kwargs)
                except Exception:
                    fval = fval_tpl

                if fname and fval:
                    embed.add_field(name=fname, value=fval, inline=inline)

        # Главная картинка (image_url) - поддерживает HTTP и локальные файлы
        image_setting = cfg.get("image_url", "")
        if image_setting:
            local_path = self._resolve_local_file(image_setting)
            if local_path:
                filename = os.path.basename(local_path)
                files.append(discord.File(local_path, filename=filename))
                embed.set_image(url=f"attachment://{filename}")
            else:
                embed.set_image(url=image_setting)

        # Миниатюра (thumbnail_url) - поддерживает HTTP и локальные файлы
        thumb_setting = cfg.get("thumbnail_url", "")
        if thumb_setting:
            local_path = self._resolve_local_file(thumb_setting)
            if local_path:
                filename = f"thumb_{os.path.basename(local_path)}"
                files.append(discord.File(local_path, filename=filename))
                embed.set_thumbnail(url=f"attachment://{filename}")
            else:
                embed.set_thumbnail(url=thumb_setting)

        # Подвал (footer)
        footer_text_tpl = cfg.get("footer_text", "The Division 2 • Секретные торговцы")
        try:
            footer_text = footer_text_tpl.format(**fmt_kwargs)
        except Exception:
            footer_text = footer_text_tpl

        footer_icon_setting = cfg.get("footer_icon_url", "")
        if footer_icon_setting:
            local_path = self._resolve_local_file(footer_icon_setting)
            if local_path:
                filename = f"footer_{os.path.basename(local_path)}"
                files.append(discord.File(local_path, filename=filename))
                embed.set_footer(text=footer_text, icon_url=f"attachment://{filename}")
            else:
                embed.set_footer(text=footer_text, icon_url=footer_icon_setting)
        else:
            embed.set_footer(text=footer_text)

        return embed, files

    async def post_status_notification(self, info: Dict[str, Any]) -> bool:
        """
        Отправляет уведомление о статусе торговцев в Discord через Webhook (если задан)
        или напрямую в текстовый канал.
        """
        embed, files = self.build_vendors_embed_and_files(info)

        ping_role_id = self.get_ping_role_id()
        role_ping_str = f"<@&{ping_role_id}>" if ping_role_id else ""
        content_template = self.module_config.get("content_template", "{role_ping}")

        if content_template:
            try:
                content = content_template.format(ping_role_id=ping_role_id or "", role_ping=role_ping_str)
            except Exception:
                content = role_ping_str if role_ping_str else None
        else:
            content = role_ping_str if role_ping_str else None

        if not content or not content.strip():
            content = None

        webhook_url = self.get_webhook_url()

        # 1. Отправка через Webhook
        if webhook_url:
            meta = load_webhooks_metadata("secret_vendors")
            username = self.module_config.get("webhook_username") or meta.get("webhook_username", "Секретные торговцы")
            avatar_setting = self.module_config.get("webhook_avatar_url") or meta.get("webhook_avatar_url", "")
            avatar_url = resolve_asset_url(avatar_setting) if avatar_setting else None
            if avatar_url and not (avatar_url.startswith('http://') or avatar_url.startswith('https://')):
                avatar_url = None

            try:
                from modules_utils.http_client import HttpClient
                session = await HttpClient.get_session()
                webhook = discord.Webhook.from_url(webhook_url, session=session)
                wh_msg = await webhook.send(
                    content=content,
                    embed=embed,
                    files=files,
                    username=username,
                    avatar_url=avatar_url,
                    wait=True
                )
                if wh_msg and hasattr(self.bot, "discord_bot") and self.bot.discord_bot:
                    await self.bot.discord_bot._handle_auto_publish(wh_msg, None, self.module_config)

                self.cache["last_triggered_event"] = info["last_event_key"]
                self.cache["last_status"] = info["status"]
                self.cache["updated_at"] = info["now_dt_msk"].isoformat()
                await self._save_cache()

                status_ru = "Opened" if info["is_open"] else "Closed"
                await send_to_any_log("info", f"SecretVendors: notification '{status_ru}' sent via Webhook.", emoji=LogEmojis.SUCCESS)
                return True
            except Exception as e:
                await send_to_any_log("error", f"SecretVendors: error sending via Webhook: {e}", emoji=LogEmojis.ERROR)

        # 2. Фоллбэк: Отправка напрямую в Discord канал
        channel_id = self.get_target_channel_id()
        if not channel_id:
            await send_to_any_log("warning", "SecretVendors: webhook_url and channel_id not configured, skipping notification.", emoji=LogEmojis.WARNING)
            return False

        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                await send_to_any_log("error", f"SecretVendors: failed to find channel {channel_id}: {e}", emoji=LogEmojis.ERROR)
                return False

        try:
            msg = await channel.send(content=content, embed=embed, files=files)
            if msg and hasattr(self.bot, "discord_bot") and self.bot.discord_bot:
                await self.bot.discord_bot._handle_auto_publish(msg, channel, self.module_config)
            self.cache["last_triggered_event"] = info["last_event_key"]
            self.cache["last_status"] = info["status"]
            self.cache["last_message_id"] = msg.id
            self.cache["updated_at"] = info["now_dt_msk"].isoformat()
            await self._save_cache()

            status_ru = "Opened" if info["is_open"] else "Closed"
            await send_to_any_log("info", f"SecretVendors: notification '{status_ru}' sent to channel #{channel.name}", emoji=LogEmojis.SUCCESS)
            return True
        except Exception as e:
            await send_to_any_log("error", f"SecretVendors: error sending to channel {channel_id}: {e}", emoji=LogEmojis.ERROR)
            return False

    async def _schedule_loop(self):
        """Фоновый цикл проверки наступления события открытия/закрытия торговцев."""
        await asyncio.sleep(5)

        while self.is_running:
            try:
                info = get_vendor_schedule_info()
                last_event_key = info["last_event_key"]
                cached_event = self.cache.get("last_triggered_event")

                if cached_event is None:
                    await send_to_any_log("info", f"SecretVendors: initializing initial state: {last_event_key}", emoji=LogEmojis.INFO)
                    await self.post_status_notification(info)
                elif cached_event != last_event_key:
                    await send_to_any_log("info", f"SecretVendors: event changed from {cached_event} to {last_event_key}", emoji=LogEmojis.INFO)
                    await self.post_status_notification(info)

            except asyncio.CancelledError:
                break
            except Exception as e:
                await send_to_any_log("error", f"SecretVendors: error in background loop: {e}", emoji=LogEmojis.ERROR)

            for _ in range(15):
                if not self.is_running:
                    break
                await asyncio.sleep(1)

    # =========================
    # КОМАНДЫ
    # =========================

    @commands.command(name="vendors", aliases=["торговцы", "дэнни", "кэйси"])
    async def vendors_cmd(self, ctx: commands.Context):
        """Префиксная команда получения статуса секретных торговцев."""
        info = get_vendor_schedule_info()
        embed, files = self.build_vendors_embed_and_files(info)
        await ctx.send(embed=embed, files=files)

    @app_commands.command(name="vendors", description=BotStrings.CMD_VENDORS_DESC)
    async def vendors_slash(self, interaction: discord.Interaction):
        """Слэш-команда получения статуса секретных торговцев."""
        info = get_vendor_schedule_info()
        embed, files = self.build_vendors_embed_and_files(info)
        await interaction.response.send_message(embed=embed, files=files)

    @commands.command(name="vendors_send", aliases=["отправить_торговцев", "send_vendors"])
    @commands.has_permissions(administrator=True)
    async def vendors_send_cmd(self, ctx: commands.Context):
        """Префиксная команда принудительной отправки статуса торговцев."""
        info = get_vendor_schedule_info()
        success = await self.post_status_notification(info)
        if success:
            await ctx.send(f"{VendorEmojis.SUCCESS} {BotStrings.get('VENDOR_SEND_SUCCESS', 'Сообщение о статусе торговцев успешно отправлено.')}")
        else:
            await ctx.send(f"{VendorEmojis.ERROR} {BotStrings.get('VENDOR_SEND_FAIL', 'Не удалось отправить сообщение. Проверьте webhook_url или channel_id в конфиге.')}")

    @app_commands.command(name="vendors_send", description=BotStrings.CMD_VENDORS_SEND_DESC)
    @app_commands.checks.has_permissions(administrator=True)
    async def vendors_send_slash(self, interaction: discord.Interaction):
        """Слэш-команда принудительной отправки статуса через Webhook или канал."""
        await interaction.response.defer(ephemeral=True)
        info = get_vendor_schedule_info()
        success = await self.post_status_notification(info)
        if success:
            await interaction.followup.send(f"{VendorEmojis.SUCCESS} {BotStrings.get('VENDOR_SEND_SUCCESS', 'Сообщение о статусе торговцев успешно отправлено.')}")
        else:
            await interaction.followup.send(f"{VendorEmojis.ERROR} {BotStrings.get('VENDOR_SEND_FAIL', 'Не удалось отправить сообщение. Проверьте webhook_url или channel_id в конфиге.')}")

    @commands.command(name="vendors_config", aliases=["настройка_торговцев", "vendors_setup"])
    @commands.has_permissions(administrator=True)
    async def vendors_config_cmd(self, ctx: commands.Context):
        """Префиксная команда просмотра и настройки параметров секретных торговцев."""
        embed = self.get_config_embed()
        view = VendorsConfigView(self)
        await ctx.send(embed=embed, view=view)

    @app_commands.command(name="vendors_config", description=BotStrings.CMD_VENDORS_CONFIG_DESC)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        webhook_url=BotStrings.CMD_VENDORS_PARAM_WEBHOOK_URL,
        webhook_username=BotStrings.CMD_VENDORS_PARAM_WEBHOOK_NAME,
        webhook_avatar_url=BotStrings.CMD_VENDORS_PARAM_WEBHOOK_AVATAR,
        open_color=BotStrings.CMD_VENDORS_PARAM_OPEN_COLOR,
        close_color=BotStrings.CMD_VENDORS_PARAM_CLOSE_COLOR,
        channel=BotStrings.CMD_VENDORS_PARAM_CHANNEL,
        ping_role=BotStrings.CMD_VENDORS_PARAM_ROLE
    )
    async def vendors_config_slash(
        self,
        interaction: discord.Interaction,
        webhook_url: Optional[str] = None,
        webhook_username: Optional[str] = None,
        webhook_avatar_url: Optional[str] = None,
        open_color: Optional[str] = None,
        close_color: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None,
        ping_role: Optional[discord.Role] = None
    ):
        """Слэш-команда настройки параметров вебхука и канала секретных торговцев."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(f"{VendorEmojis.ERROR} {BotStrings.get('VENDOR_NO_PERMS', 'У вас нет прав администратора.')}", ephemeral=True)
            return

        updated = False
        if webhook_url is not None:
            self.module_config["webhook_url"] = webhook_url.strip()
            updated = True
        if webhook_username is not None:
            self.module_config["webhook_username"] = webhook_username.strip()
            updated = True
        if webhook_avatar_url is not None:
            self.module_config["webhook_avatar_url"] = webhook_avatar_url.strip()
            updated = True
        if open_color is not None:
            self.module_config["open_color"] = open_color.strip()
            updated = True
        if close_color is not None:
            self.module_config["close_color"] = close_color.strip()
            updated = True
        if channel is not None:
            self.module_config["channel_id"] = channel.id
            updated = True
        if ping_role is not None:
            self.module_config["ping_role_id"] = ping_role.id
            updated = True

        if updated:
            self._save_module_config()

        embed = self.get_config_embed()
        view = VendorsConfigView(self)
        msg = f"{VendorEmojis.SUCCESS} {BotStrings.get('VENDOR_CONFIG_UPDATED', 'Настройки успешно обновлены!')}" if updated else f"{VendorEmojis.GEAR} {BotStrings.get('VENDOR_CONFIG_CURRENT', 'Текущие настройки модуля секретных торговцев:')}"
        await interaction.response.send_message(content=msg, embed=embed, view=view, ephemeral=True)


class VendorsConfigModal(discord.ui.Modal):
    webhook_url_input = discord.ui.TextInput(
        label="URL Webhook",
        placeholder="https://discord.com/api/webhooks/...",
        required=False,
        style=discord.TextStyle.short
    )
    webhook_username_input = discord.ui.TextInput(
        label=BotStrings.VENDOR_MODAL_NAME,
        placeholder=BotStrings.VENDOR_DEFAULT_NAME,
        required=False,
        style=discord.TextStyle.short
    )
    webhook_avatar_input = discord.ui.TextInput(
        label=BotStrings.VENDOR_MODAL_AVATAR,
        placeholder="https://... или assets/images/...",
        required=False,
        style=discord.TextStyle.short
    )
    open_color_input = discord.ui.TextInput(
        label=BotStrings.get("VENDOR_CFG_FIELD_OPEN_COLOR", "Цвет при открытии (RGB)"),
        placeholder="46, 204, 113",
        required=False,
        style=discord.TextStyle.short
    )
    close_color_input = discord.ui.TextInput(
        label=BotStrings.get("VENDOR_CFG_FIELD_CLOSE_COLOR", "Цвет при закрытии (RGB)"),
        placeholder="231, 76, 60",
        required=False,
        style=discord.TextStyle.short
    )

    def __init__(self, cog: 'SecretVendorsModule'):
        super().__init__(title=BotStrings.VENDOR_MODAL_TITLE)
        self.cog = cog
        self.webhook_url_input.default = cog.module_config.get("webhook_url", "") or ""
        self.webhook_username_input.default = cog.module_config.get("webhook_username", BotStrings.get("VENDOR_DEFAULT_NAME", "Секретные торговцы")) or BotStrings.get("VENDOR_DEFAULT_NAME", "Секретные торговцы")
        self.webhook_avatar_input.default = cog.module_config.get("webhook_avatar_url", "") or ""
        self.open_color_input.default = cog.module_config.get("open_color", "46, 204, 113") or "46, 204, 113"
        self.close_color_input.default = cog.module_config.get("close_color", "231, 76, 60") or "231, 76, 60"

    async def on_submit(self, interaction: discord.Interaction):
        self.cog.module_config["webhook_url"] = self.webhook_url_input.value.strip()
        self.cog.module_config["webhook_username"] = self.webhook_username_input.value.strip() or BotStrings.get("VENDOR_DEFAULT_NAME", "Секретные торговцы")
        self.cog.module_config["webhook_avatar_url"] = self.webhook_avatar_input.value.strip()
        if self.open_color_input.value.strip():
            self.cog.module_config["open_color"] = self.open_color_input.value.strip()
        if self.close_color_input.value.strip():
            self.cog.module_config["close_color"] = self.close_color_input.value.strip()
        self.cog._save_module_config()

        embed = self.cog.get_config_embed()
        view = VendorsConfigView(self.cog)
        await interaction.response.send_message(
            content=f"{VendorEmojis.SUCCESS} {BotStrings.get('VENDOR_CONFIG_SAVED_SUCCESS', 'Настройки вебхука и цветов секретных торговцев успешно сохранены!')}",
            embed=embed,
            view=view,
            ephemeral=True
        )


class VendorsConfigView(discord.ui.View):
    def __init__(self, cog: 'SecretVendorsModule'):
        super().__init__(timeout=180)
        self.cog = cog

    @discord.ui.button(label=BotStrings.VENDOR_BTN_EDIT_WEBHOOK, style=discord.ButtonStyle.primary, emoji=VendorEmojis.GEAR)
    async def edit_webhook_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(f"{VendorEmojis.ERROR} {BotStrings.VENDOR_NO_PERMS}", ephemeral=True)
            return
        modal = VendorsConfigModal(self.cog)
        await interaction.response.send_modal(modal)


async def setup(bot):
    cog = SecretVendorsModule(bot)
    await bot.add_cog(cog)
    if hasattr(bot, 'app'):
        bot.app.secret_vendors_module = cog
