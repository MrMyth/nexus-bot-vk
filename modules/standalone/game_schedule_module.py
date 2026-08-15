# modules/standalone/game_schedule_module.py
import asyncio
import json
import os
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, date, time as dtime
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional, List, Tuple

from settings.config import Config
from settings.data_files import Files
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, Emojis, ScheduleEmojis
from constants.strings import BotStrings
from modules_utils.helpers import safe_create_task, resolve_asset_url, parse_color_to_int, load_webhooks_metadata
from modules_utils.cache_utils import load_json_cache, save_json_cache_async

MSK_TZ = ZoneInfo("Europe/Moscow")
DAYS_RU = BotStrings.get("SCHEDULE_DAYS_RU", ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"])

DEFAULT_LEGENDARY_ROTATION = [
    "Стадион (District Union Arena)",
    "Капитолий (Capitol Building)",
    "Остров Рузвельта (Roosevelt Island)",
    "Тайдл-Басин (Tidal Basin)",
    "Зоопарк (Manning National Zoo)"
]

def get_current_reset_tuesday(now: Optional[datetime] = None) -> date:
    """
    Возвращает дату (date) того вторника (11:00 МСК), к которому относится текущий момент времени.
    """
    if now is None:
        now = datetime.now(MSK_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=MSK_TZ)

    days_since_tuesday = (now.weekday() - 1) % 7
    last_tuesday_date = now.date() - timedelta(days=days_since_tuesday)
    last_tuesday_reset_dt = datetime.combine(last_tuesday_date, dtime(11, 0), tzinfo=MSK_TZ)

    if now < last_tuesday_reset_dt:
        return last_tuesday_date - timedelta(days=7)
    return last_tuesday_date


def get_current_legendary_mission(
    rotation: List[str] = None,
    ref_date_str: str = "2026-07-28",
    start_index: int = 0,
    target_dt: Optional[datetime] = None,
    override: Optional[str] = None
) -> str:
    """
    Вычисляет ротацию легендарной миссии на основе опорного вторника или возвращает ручной оверрайд.
    Ротация меняется каждый вторник в 11:00 МСК.
    """
    if override and str(override).strip():
        return str(override).strip()

    if not rotation:
        rotation = DEFAULT_LEGENDARY_ROTATION

    if target_dt is None:
        target_dt = datetime.now(MSK_TZ)
    elif target_dt.tzinfo is None:
        target_dt = target_dt.replace(tzinfo=MSK_TZ)

    try:
        ref_date = date.fromisoformat(ref_date_str)
    except Exception:
        ref_date = date(2026, 7, 28)

    ref_dt = datetime.combine(ref_date, dtime(11, 0), tzinfo=MSK_TZ)

    if target_dt < ref_dt:
        diff_weeks = 0
    else:
        diff_seconds = (target_dt - ref_dt).total_seconds()
        diff_weeks = int(diff_seconds // (7 * 86400))

    index = (start_index + diff_weeks) % len(rotation)
    return rotation[index]


class SelectLegendaryView(discord.ui.View):
    def __init__(self, cog: "GameScheduleModule"):
        super().__init__(timeout=180)
        self.cog = cog

        rotation = cog.module_config.get("legendary_missions_rotation", DEFAULT_LEGENDARY_ROTATION)
        options = []
        for i, item in enumerate(rotation):
            options.append(
                discord.SelectOption(
                    label=f"{i+1}. {item[:90]}",
                    value=str(i+1),
                    description=f"Установить {item[:45]} как текущую миссию"
                )
            )

        select = discord.ui.Select(
            placeholder="Выберите текущую легендарную миссию недели...",
            min_values=1,
            max_values=1,
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        guild_perms = getattr(interaction.user, "guild_permissions", None)
        if not guild_perms or not guild_perms.administrator:
            await interaction.response.send_message(f"{ScheduleEmojis.ERROR} {BotStrings.get('SCHEDULE_NO_PERMS', 'У вас нет прав администратора.')}", ephemeral=True)
            return

        selected_val = interaction.data["values"][0]
        success, selected_m, reset_date, preview_text = self.cog._set_active_legendary_mission(selected_val)

        item = self.cog._get_schedule_item("legendary_mission")
        embed = self.cog.build_event_embed(item) if item else None

        title_str = BotStrings.get("SCHEDULE_ROTATION_TITLE", "Установлена текущая легендарная миссия этой недели!")
        curr_str = BotStrings.get("SCHEDULE_ROTATION_CURRENT", "🎯 Текущая миссия: **{mission}**").format(mission=selected_m)
        tue_str = BotStrings.get("SCHEDULE_ROTATION_RESET_TUE", "📅 Опорный вторник сброса: **{reset_date} 11:00 МСК**").format(reset_date=reset_date)
        prev_head = BotStrings.get("SCHEDULE_ROTATION_PREVIEW_HEADER", "Расчет ротации на следующие недели:")

        msg = (
            f"{ScheduleEmojis.SUCCESS} **{title_str}**\n\n"
            f"{curr_str}\n"
            f"{tue_str}\n\n"
            f"**{prev_head}**\n{preview_text}"
        )
        await interaction.response.edit_message(content=msg, embed=embed, view=None)


class GameScheduleModule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache_file = Files.GAME_SCHEDULE_CACHE_FILE
        self.config_file = Files.GAME_SCHEDULE_CONFIG_FILE

        self.cache: Dict[str, Any] = {}
        self.module_config: Dict[str, Any] = {}
        self.task: Optional[asyncio.Task] = None
        self.is_running = False

        self._load_cache()
        self._load_module_config()

    def _load_cache(self):
        """Загружает кэш отправленных событий."""
        data = load_json_cache(self.cache_file)
        self.cache = data if data else {"sent_events": {}}

    async def _save_cache(self):
        """Асинхронно сохраняет кэш."""
        await save_json_cache_async(self.cache_file, self.cache)

    def _load_module_config(self) -> Dict[str, Any]:
        """Загружает конфигурацию расписания игровых событий."""
        default_config = {
            "auto_publish": True,
            "webhook_url": getattr(Config, "GAME_SCHEDULE_WEBHOOK_URL", ""),
            "webhook_username": BotStrings.get("SCHEDULE_DEFAULT_USERNAME", "Игровое расписание"),
            "webhook_avatar_url": "assets/images/bot-image/thedivision2-icon.png",
            "author_name": BotStrings.get("SCHEDULE_DEFAULT_AUTHOR", "Игровое расписание The Division 2"),
            "author_icon_url": "assets/images/bot-image/agentwomanmaskot.jpg",
            "footer_text": BotStrings.get("SCHEDULE_DEFAULT_FOOTER", "Игровое расписание The Division 2"),
            "footer_icon_url": "assets/images/bot-image/thedivision2-icon.png",
            "channel_id": getattr(Config, "GAME_SCHEDULE_CHANNEL_ID", None),
            "ping_role_id": getattr(Config, "GAME_SCHEDULE_ROLE_ID", None),
            "content_template": "{role_ping}",
            "color": "244, 102, 27",
            "schedule": [
                {
                    "id": "paradise_reset",
                    "days": [0],
                    "time": "11:00",
                    "title": "{emoji_reset} Сброс еженедельных вылазок",
                    "description": "Произошел сброс еженедельных активностей **Вылазки**.",
                    "thumbnail_url": "assets/images/bot-image/thedivision2-icon.png",
                    "image_url": "assets/images/bot-image/paradise.jpg",
                    "ping_role_id": 1537021483203956766,
                    "enabled": True
                },
                {
                    "id": "legendary_mission",
                    "days": [1],
                    "time": "11:00",
                    "title": "{emoji_trophy} Новая игровая неделя",
                    "description": "Смена легендарной миссии недели: **{legendary_mission}**.\n\nТакже произошел сброс рейдов и каталога торговцев.",
                    "thumbnail_url": "assets/images/bot-image/thedivision2-icon.png",
                    "image_url": "assets/images/bot-image/legendary.jpg",
                    "ping_role_id": 1537021089245560842,
                    "enabled": True
                },
                {
                    "id": "college_reset",
                    "days": [1],
                    "time": "11:00",
                    "title": "{emoji_college} Обновление активности: Колледж Kenly",
                    "description": "Произошло обновление локации и задач в **Колледже Kenly**.",
                    "thumbnail_url": "assets/images/bot-image/thedivision2-icon.png",
                    "image_url": "assets/images/bot-image/kenly.jpg",
                    "ping_role_id": None,
                    "enabled": True
                },
                {
                    "id": "clan_container",
                    "days": [3],
                    "time": "12:00",
                    "title": "{emoji_container} Доступен контейнер за клан",
                    "description": "Еженедельный клановый контейнер с наградами стал **доступен для получения**!",
                    "thumbnail_url": "assets/images/bot-image/thedivision2-icon.png",
                    "image_url": "assets/images/bot-image/clan.jpg",
                    "ping_role_id": 1537021699671855115,
                    "enabled": True
                }
            ],
            "legendary_missions_rotation": DEFAULT_LEGENDARY_ROTATION,
            "legendary_start_index": 0,
            "legendary_reference_date": "2026-07-28"
        }

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in default_config.items():
                        if k not in data:
                            data[k] = v
                    if "schedule" in data and isinstance(data["schedule"], list):
                        for item in data["schedule"]:
                            if "ping_role_id" not in item:
                                item["ping_role_id"] = None
                    self.module_config = data
            except Exception as e:
                safe_create_task(send_to_any_log("error", f"GameSchedule: error reading {self.config_file}: {e}", emoji=LogEmojis.ERROR))
                self.module_config = default_config
        else:
            self.module_config = default_config
            try:
                os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump(self.module_config, f, ensure_ascii=False, indent=2)
            except Exception as e:
                safe_create_task(send_to_any_log("error", f"GameSchedule: error creating {self.config_file}: {e}", emoji=LogEmojis.ERROR))

        return self.module_config

    def _save_module_config(self):
        """Сохраняет конфигурацию модуля в JSON файл."""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.module_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"GameSchedule: error saving {self.config_file}: {e}", emoji=LogEmojis.ERROR))

    def get_webhook_url(self) -> Optional[str]:
        url = self.module_config.get("webhook_url") or getattr(Config, "GAME_SCHEDULE_WEBHOOK_URL", "")
        return url.strip() if url and url.strip() else None

    def get_config_embed(self) -> discord.Embed:
        """Генерирует Embed с текущими настройками модуля расписания."""
        auto_pub = self.module_config.get("auto_publish", True)
        webhook_url = self.module_config.get("webhook_url", "")
        username = self.module_config.get("webhook_username", BotStrings.get("SCHEDULE_DEFAULT_USERNAME", "Игровое расписание"))
        avatar_url = self.module_config.get("webhook_avatar_url", "")
        channel_id = self.module_config.get("channel_id")
        ping_role_id = self.module_config.get("ping_role_id")
        color_rgb = self.module_config.get("color", "244, 102, 27")
        author_name = self.module_config.get("author_name", "")
        footer_text = self.module_config.get("footer_text", "")

        embed = discord.Embed(
            title=f"{ScheduleEmojis.GEAR} {BotStrings.get('SCHEDULE_EMBED_TITLE', 'Настройки игрового расписания событий')}",
            color=parse_color_to_int(color_rgb, 0xF4661B)
        )
        not_set_str = BotStrings.get("VENDOR_CFG_NOT_SET", "*Не задан*")
        not_set_fem_str = BotStrings.get("VENDOR_CFG_NOT_SET_FEMALE", "*Не задана*")
        default_str = BotStrings.get("VENDOR_CFG_DEFAULT", "*По умолчанию*")

        pub_str = BotStrings.get("SCHEDULE_AUTOPUB_ENABLED", "🟢 `Включена`") if auto_pub else BotStrings.get("SCHEDULE_AUTOPUB_DISABLED", "🔴 `Выключена`")
        embed.add_field(
            name=BotStrings.get("SCHEDULE_AUTOPUB_FIELD", "Автопубликация"),
            value=pub_str,
            inline=True
        )
        embed.add_field(
            name=f"{ScheduleEmojis.LINK} Webhook URL",
            value=f"`{webhook_url}`" if webhook_url else not_set_str,
            inline=False
        )
        embed.add_field(
            name=f"{ScheduleEmojis.USER} {BotStrings.get('VENDOR_CFG_FIELD_NAME', 'Имя вебхука')}",
            value=f"`{username}`",
            inline=True
        )
        embed.add_field(
            name=f"{ScheduleEmojis.AVATAR} {BotStrings.get('VENDOR_CFG_FIELD_AVATAR', 'Аватар вебхука')}",
            value=f"`{avatar_url}`" if avatar_url else default_str,
            inline=True
        )
        embed.add_field(
            name=f"{ScheduleEmojis.COLOR} {BotStrings.get('SCHEDULE_CFG_FIELD_COLOR', 'Цвет сообщений (RGB)')}",
            value=f"`{color_rgb}`",
            inline=True
        )
        embed.add_field(
            name=BotStrings.get("SCHEDULE_CFG_FIELD_AUTHOR", "Шапка (Author)"),
            value=f"`{author_name}`" if author_name else not_set_fem_str,
            inline=True
        )
        embed.add_field(
            name=BotStrings.get("SCHEDULE_CFG_FIELD_FOOTER", "Подвал (Footer)"),
            value=f"`{footer_text}`" if footer_text else not_set_str,
            inline=True
        )
        embed.add_field(
            name=f"{ScheduleEmojis.CHANNEL} {BotStrings.get('VENDOR_CFG_FIELD_CHANNEL', 'Канал (фоллбэк)')}",
            value=f"<#{channel_id}>" if channel_id else not_set_str,
            inline=True
        )
        embed.add_field(
            name=f"{ScheduleEmojis.ROLE} {BotStrings.get('VENDOR_CFG_FIELD_ROLE', 'Роль для пинга')}",
            value=f"<@&{ping_role_id}>" if ping_role_id else not_set_fem_str,
            inline=True
        )

        schedule = self.module_config.get("schedule", [])
        schedule_info = []
        for item in schedule:
            item_id = item.get("id", "unknown")
            title_tmpl = item.get("title", item_id)
            try:
                title = title_tmpl.format(
                    emoji_reset=ScheduleEmojis.RESET,
                    emoji_trophy=ScheduleEmojis.TROPHY,
                    emoji_college=ScheduleEmojis.COLLEGE,
                    emoji_container=ScheduleEmojis.CONTAINER,
                )
            except Exception:
                title = title_tmpl

            item_role_id = item.get("ping_role_id")
            if item_role_id:
                role_str = f"<@&{item_role_id}>"
            elif ping_role_id:
                role_str = f"<@&{ping_role_id}> *(общая)*"
            else:
                role_str = "*Без пинга*"

            thumb = item.get("thumbnail_url", "")
            img = item.get("image_url", "")
            thumb_str = f"`{thumb[:30]}...`" if len(thumb) > 30 else f"`{thumb}`" if thumb else "*Аватар по умолч.*"
            img_str = f"`{img[:30]}...`" if len(img) > 30 else f"`{img}`" if img else "*Без баннера*"
            schedule_info.append(f"• **{title}** (`{item_id}`):\n  └ Роль: {role_str} | Миниатюра: {thumb_str} | Баннер: {img_str}")

        if schedule_info:
            embed.add_field(
                name=f"{ScheduleEmojis.CALENDAR} {BotStrings.get('SCHEDULE_CFG_EVENTS_FIELD', 'Настроенные события и их превью')}",
                value="\n".join(schedule_info),
                inline=False
            )

        resolved_avatar = resolve_asset_url(avatar_url) if avatar_url else None
        if resolved_avatar and (resolved_avatar.startswith('http://') or resolved_avatar.startswith('https://')):
            embed.set_thumbnail(url=resolved_avatar)

        return embed

    async def start(self):
        """Запускает фоновый цикл проверки событий."""
        if self.is_running:
            return
        self.is_running = True

        webhook_url = self.get_webhook_url()
        channel_id = self.module_config.get("channel_id") or getattr(Config, "GAME_SCHEDULE_CHANNEL_ID", None)

        log_msg = "GameSchedule: schedule loop started."
        if webhook_url:
            log_msg += f" Delivery method: Webhook ({webhook_url[:30]}...)"
        elif channel_id:
            log_msg += f" Delivery method: Discord Channel (#{channel_id})"
        else:
            log_msg += " (Warning: webhook_url and channel_id not configured)"

        await send_to_any_log("info", log_msg, emoji=LogEmojis.SYSTEM)
        self.task = safe_create_task(self._schedule_loop(), name="GameScheduleLoop")

    async def stop(self):
        """Останавливает модуль."""
        self.is_running = False
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None
        await send_to_any_log("info", "Game schedule module stopped.", emoji=LogEmojis.SYSTEM)

    def build_event_embed(self, item: Dict[str, Any], target_dt: Optional[datetime] = None) -> discord.Embed:
        """Создает Embed для конкретного события расписания."""
        cfg = self.module_config
        color_rgb = cfg.get("color", "244, 102, 27")
        embed_color = parse_color_to_int(color_rgb, 0xF4661B)

        title_template = item.get("title", "Игровое событие")
        desc_template = item.get("description", "")

        leg_rotation = cfg.get("legendary_missions_rotation", DEFAULT_LEGENDARY_ROTATION)
        ref_date_str = cfg.get("legendary_reference_date", "2026-07-28")
        start_idx = cfg.get("legendary_start_index", 0)
        leg_override = cfg.get("legendary_override")

        curr_leg_mission = get_current_legendary_mission(
            rotation=leg_rotation,
            ref_date_str=ref_date_str,
            start_index=start_idx,
            target_dt=target_dt,
            override=leg_override
        )

        fmt_kwargs = {
            "legendary_mission": curr_leg_mission,
            "emoji_reset": ScheduleEmojis.RESET,
            "emoji_trophy": ScheduleEmojis.TROPHY,
            "emoji_college": ScheduleEmojis.COLLEGE,
            "emoji_container": ScheduleEmojis.CONTAINER,
            "emoji_gear": ScheduleEmojis.GEAR,
            "emoji_link": ScheduleEmojis.LINK,
            "emoji_user": ScheduleEmojis.USER,
            "emoji_avatar": ScheduleEmojis.AVATAR,
            "emoji_color": ScheduleEmojis.COLOR,
            "emoji_channel": ScheduleEmojis.CHANNEL,
            "emoji_role": ScheduleEmojis.ROLE,
        }

        try:
            title = title_template.format(**fmt_kwargs)
        except Exception:
            title = title_template

        try:
            desc = desc_template.format(**fmt_kwargs)
        except Exception:
            desc = desc_template

        embed = discord.Embed(
            title=title,
            description=desc,
            color=embed_color,
            timestamp=datetime.now(MSK_TZ)
        )

        author_name = cfg.get("author_name") or cfg.get("name")
        author_icon = cfg.get("author_icon_url") or cfg.get("embed_author_icon_url")
        if author_name:
            resolved_author_icon = resolve_asset_url(author_icon) if author_icon else None
            if resolved_author_icon and not (resolved_author_icon.startswith('http://') or resolved_author_icon.startswith('https://')):
                resolved_author_icon = None
            embed.set_author(name=author_name, icon_url=resolved_author_icon)

        footer_text = cfg.get("footer_text") or cfg.get("name") or "Игровое расписание The Division 2"
        footer_icon = cfg.get("footer_icon_url") or cfg.get("embed_footer_icon_url")
        resolved_footer_icon = resolve_asset_url(footer_icon) if footer_icon else None
        if resolved_footer_icon and not (resolved_footer_icon.startswith('http://') or resolved_footer_icon.startswith('https://')):
            resolved_footer_icon = None
        embed.set_footer(text=footer_text, icon_url=resolved_footer_icon)

        # Thumbnail: item thumbnail_url OR fallback to webhook_avatar_url
        item_thumb = item.get("thumbnail_url") or cfg.get("webhook_avatar_url")
        resolved_thumb = resolve_asset_url(item_thumb) if item_thumb else None
        if resolved_thumb and (resolved_thumb.startswith('http://') or resolved_thumb.startswith('https://')):
            embed.set_thumbnail(url=resolved_thumb)

        # Main image banner: item image_url
        item_image = item.get("image_url")
        resolved_image = resolve_asset_url(item_image) if item_image else None
        if resolved_image and (resolved_image.startswith('http://') or resolved_image.startswith('https://')):
            embed.set_image(url=resolved_image)

        return embed

    async def send_event_notification(self, item: Dict[str, Any], target_dt: Optional[datetime] = None) -> bool:
        """
        Отправляет уведомление о событии через Webhook или Discord канал.
        """
        webhook_url = self.get_webhook_url()
        channel_id = self.module_config.get("channel_id") or getattr(Config, "GAME_SCHEDULE_CHANNEL_ID", None)
        role_id = item.get("ping_role_id") or self.module_config.get("ping_role_id") or getattr(Config, "GAME_SCHEDULE_ROLE_ID", None)

        role_ping = f"<@&{role_id}>" if role_id else ""
        content_template = item.get("content_template") or self.module_config.get("content_template", "{role_ping}")
        content = content_template.format(role_ping=role_ping).strip()

        embed = self.build_event_embed(item, target_dt)

        if webhook_url:
            meta = load_webhooks_metadata("game_schedule")
            username = self.module_config.get("webhook_username") or meta.get("webhook_username", "Игровое расписание")
            avatar_setting = self.module_config.get("webhook_avatar_url") or meta.get("webhook_avatar_url", "")
            avatar_url = resolve_asset_url(avatar_setting) if avatar_setting else None
            if avatar_url and not (avatar_url.startswith('http://') or avatar_url.startswith('https://')):
                avatar_url = None

            try:
                from modules_utils.http_client import HttpClient
                session = await HttpClient.get_session()
                webhook = discord.Webhook.from_url(webhook_url, session=session)
                sent_msg = await webhook.send(
                    content=content if content else None,
                    embed=embed,
                    username=username,
                    avatar_url=avatar_url,
                    wait=True
                )
                if sent_msg and hasattr(self.bot, "discord_bot") and self.bot.discord_bot:
                    await self.bot.discord_bot._handle_auto_publish(sent_msg, None, self.module_config)

                await send_to_any_log("info", f"GameSchedule: sent event '{item['title']}' via Webhook", emoji=LogEmojis.SUCCESS)
                return True
            except Exception as e:
                await send_to_any_log("error", f"GameSchedule: error sending via Webhook: {e}", emoji=LogEmojis.ERROR)

        if channel_id:
            try:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    channel = await self.bot.fetch_channel(int(channel_id))

                if channel:
                    sent_msg = await channel.send(
                        content=content if content else None,
                        embed=embed
                    )
                    if sent_msg and hasattr(self.bot, "discord_bot") and self.bot.discord_bot:
                        await self.bot.discord_bot._handle_auto_publish(sent_msg, channel, self.module_config)
                    await send_to_any_log("info", f"GameSchedule: sent event '{item['title']}' to channel #{channel.name}", emoji=LogEmojis.SUCCESS)
                    return True
            except Exception as e:
                await send_to_any_log("error", f"GameSchedule: error sending to channel {channel_id}: {e}", emoji=LogEmojis.ERROR)

        await send_to_any_log("warning", "GameSchedule: webhook_url and channel_id not configured, skipping send.", emoji=LogEmojis.WARNING)
        return False

    async def _schedule_loop(self):
        """Фоновый цикл проверки наставания времени для событий расписания."""
        await asyncio.sleep(5)

        while self.is_running:
            try:
                auto_pub = self.module_config.get("auto_publish", True)
                if not auto_pub:
                    for _ in range(30):
                        if not self.is_running:
                            break
                        await asyncio.sleep(1)
                    continue

                now = datetime.now(MSK_TZ)
                curr_weekday = now.weekday()  # 0=Пн .. 6=Вс
                curr_time_str = now.strftime("%H:%M")
                date_key_prefix = now.strftime("%Y-%m-%d")

                schedule = self.module_config.get("schedule", [])
                sent_events = self.cache.setdefault("sent_events", {})

                for item in schedule:
                    if not item.get("enabled", True):
                        continue

                    event_id = item.get("id")
                    target_days = item.get("days", [])
                    target_time = item.get("time", "11:00")

                    if curr_weekday in target_days and curr_time_str == target_time:
                        event_key = f"{date_key_prefix}_{event_id}_{target_time}"

                        if sent_events.get(event_id) != event_key:
                            success = await self.send_event_notification(item, now)
                            if success:
                                sent_events[event_id] = event_key
                                await self._save_cache()

            except Exception as e:
                await send_to_any_log("error", f"GameSchedule: Error in background schedule loop: {e}", emoji=LogEmojis.ERROR)

            for _ in range(30):
                if not self.is_running:
                    break
                await asyncio.sleep(1)

    def _set_active_legendary_mission(self, mission_input: str) -> Tuple[bool, str, str, str]:
        """
        Устанавливает текущую легендарную миссию недели и пересчитывает точку отсчета для всей будущей ротации.
        Возвращает (success, selected_mission, reset_date_str, preview_text).
        """
        rotation = self.module_config.get("legendary_missions_rotation", DEFAULT_LEGENDARY_ROTATION)
        clean_input = mission_input.strip()

        matched_idx = -1
        if clean_input.isdigit():
            idx = int(clean_input) - 1
            if 0 <= idx < len(rotation):
                matched_idx = idx

        if matched_idx == -1:
            for i, item in enumerate(rotation):
                if clean_input.lower() == item.lower():
                    matched_idx = i
                    break

        if matched_idx == -1:
            for i, item in enumerate(rotation):
                if clean_input.lower() in item.lower():
                    matched_idx = i
                    break

        selected_mission = rotation[matched_idx] if matched_idx != -1 else clean_input
        if matched_idx == -1:
            matched_idx = 0

        reset_tuesday = get_current_reset_tuesday()

        self.module_config["legendary_reference_date"] = reset_tuesday.isoformat()
        self.module_config["legendary_start_index"] = matched_idx
        self.module_config["legendary_override"] = None  # Сбрасываем жесткий оверрайд, чтобы работала автоматическая ротация!
        self._save_module_config()

        preview_lines = []
        for w in range(len(rotation)):
            idx = (matched_idx + w) % len(rotation)
            m_name = rotation[idx]
            w_date = reset_tuesday + timedelta(days=7 * w)
            w_str = w_date.strftime("%d.%m.%Y")
            if w == 0:
                preview_lines.append(f"• **ТЕКУЩАЯ НЕДЕЛЯ (с {w_str})**: **{m_name}**")
            else:
                preview_lines.append(f"• С {w_str}: {m_name}")

        preview_text = "\n".join(preview_lines)
        return True, selected_mission, reset_tuesday.strftime("%d.%m.%Y"), preview_text

    def _get_schedule_item(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Вспомогательный метод поиска события по ID или алиасу."""
        if not event_id:
            return None
        clean_id = str(event_id).lower().strip()
        alias_map = {
            "paradise": "paradise_reset",
            "рай": "paradise_reset",
            "потерянный_рай": "paradise_reset",
            "legendary": "legendary_mission",
            "легендарка": "legendary_mission",
            "легендарная": "legendary_mission",
            "college": "college_reset",
            "колледж": "college_reset",
            "kenly": "college_reset",
            "clan": "clan_container",
            "клан": "clan_container",
            "контейнер": "clan_container",
        }
        target_id = alias_map.get(clean_id, clean_id)
        for item in self.module_config.get("schedule", []):
            if item.get("id", "").lower() == target_id:
                return item
        return None

    # =========================
    # КОМАНДЫ И ОБРАБОТКА ОШИБОК
    # =========================

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Обработчик ошибок слэш-команд модуля."""
        if isinstance(error, app_commands.errors.MissingPermissions):
            msg = f"{ScheduleEmojis.ERROR} У вас нет прав администратора для использования этой команды."
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            msg = f"{ScheduleEmojis.WARNING} Команда на перезарядке. Попробуйте через `{error.retry_after:.1f}` сек."
        else:
            msg = f"{ScheduleEmojis.ERROR} Произошла ошибка при выполнении команды: `{error}`"
            await send_to_any_log("error", f"[GAME-SCHEDULE] Slash command error: {error}", emoji=LogEmojis.ERROR)

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Обработчик ошибок префиксных команд модуля."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"{ScheduleEmojis.ERROR} У вас нет прав администратора для выполнения этой команды.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"{ScheduleEmojis.ERROR} Отсутствует обязательный аргумент: `{error.param.name}`.")
        else:
            await ctx.send(f"{ScheduleEmojis.ERROR} Произошла ошибка: `{error}`")
            await send_to_any_log("error", f"[GAME-SCHEDULE] Prefix command error: {error}", emoji=LogEmojis.ERROR)

    @commands.Cog.listener()
    async def on_ready(self):
        """Вызывается при полной готовности бота."""
        await self.start()

    def cog_unload(self):
        """Вызывается при выгрузке модуля."""
        asyncio.create_task(self.stop())

    @commands.command(name="schedule_set_legendary", aliases=["установить_легендарку", "set_legendary", "legendary_set", "легендарка"])
    @commands.has_permissions(administrator=True)
    async def schedule_set_legendary_cmd(self, ctx: commands.Context, *, mission_name: Optional[str] = None):
        """Префиксная команда установки текущей легендарной миссии недели."""
        if not mission_name or not mission_name.strip():
            view = SelectLegendaryView(self)
            curr_mission = get_current_legendary_mission(
                rotation=self.module_config.get("legendary_missions_rotation", DEFAULT_LEGENDARY_ROTATION),
                ref_date_str=self.module_config.get("legendary_reference_date", "2026-07-28"),
                start_index=self.module_config.get("legendary_start_index", 0)
            )
            await ctx.send(
                content=(
                    f"{ScheduleEmojis.SEARCH} **Выберите текущую легендарную миссию недели из меню ниже.**\n"
                    f"Текущая установленная миссия: **{curr_mission}**\n\n"
                    f"Бот установит выбранную миссию активной на эту неделю и станет автоматически рассчитывать ротацию на будущие недели!"
                ),
                view=view
            )
            return

        clean_input = mission_name.strip()
        if clean_input.lower() in ["авто", "auto", "сброс", "reset", "clear"]:
            self.module_config["legendary_override"] = None
            self._save_module_config()
            curr_mission = get_current_legendary_mission(
                rotation=self.module_config.get("legendary_missions_rotation", DEFAULT_LEGENDARY_ROTATION),
                ref_date_str=self.module_config.get("legendary_reference_date", "2026-07-28"),
                start_index=self.module_config.get("legendary_start_index", 0)
            )
            await ctx.send(f"{ScheduleEmojis.SUCCESS} Ручная привязка сброшена! Включена автоматическая ротация. Текущая миссия недели: **{curr_mission}**")
            return

        success, selected_m, reset_date, preview_text = self._set_active_legendary_mission(clean_input)
        item = self._get_schedule_item("legendary_mission")
        embed = self.build_event_embed(item) if item else None

        await ctx.send(
            content=(
                f"{ScheduleEmojis.SUCCESS} **Установлена текущая легендарная миссия этой недели!**\n\n"
                f"🎯 Текущая миссия: **{selected_m}**\n"
                f"📅 Опорный вторник сброса: **{reset_date} 11:00 МСК**\n\n"
                f"**Автоматический расчет ротации на следующие недели:**\n{preview_text}"
            ),
            embed=embed
        )

    @app_commands.command(name="schedule_set_legendary", description="Установить текущую легендарную миссию недели и запустить ротацию (Админ)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(mission="Выберите легендарную миссию текущей недели для старта автоматической ротации")
    @app_commands.choices(mission=[
        app_commands.Choice(name="1. Стадион (District Union Arena)", value="1"),
        app_commands.Choice(name="2. Капитолий (Capitol Building)", value="2"),
        app_commands.Choice(name="3. Остров Рузвельта (Roosevelt Island)", value="3"),
        app_commands.Choice(name="4. Тайдл-Басин (Tidal Basin)", value="4"),
        app_commands.Choice(name="5. Зоопарк (Manning National Zoo)", value="5"),
        app_commands.Choice(name="🔄 Автоматическая ротация (Сброс)", value="авто")
    ])
    async def schedule_set_legendary_slash(self, interaction: discord.Interaction, mission: str):
        """Слэш-команда установки текущей легендарной миссии недели."""
        await interaction.response.defer(ephemeral=True)
        clean_input = mission.strip()
        if clean_input.lower() in ["авто", "auto", "сброс", "reset", "clear"]:
            self.module_config["legendary_override"] = None
            self._save_module_config()
            curr_mission = get_current_legendary_mission(
                rotation=self.module_config.get("legendary_missions_rotation", DEFAULT_LEGENDARY_ROTATION),
                ref_date_str=self.module_config.get("legendary_reference_date", "2026-07-28"),
                start_index=self.module_config.get("legendary_start_index", 0)
            )
            await interaction.followup.send(
                f"{ScheduleEmojis.SUCCESS} Ручная привязка сброшена! Включена автоматическая ротация. Текущая миссия недели: **{curr_mission}**"
            )
            return

        success, selected_m, reset_date, preview_text = self._set_active_legendary_mission(clean_input)
        item = self._get_schedule_item("legendary_mission")
        embed = self.build_event_embed(item) if item else None

        await interaction.followup.send(
            content=(
                f"{ScheduleEmojis.SUCCESS} **Установлена текущая легендарная миссия этой недели!**\n\n"
                f"🎯 Текущая миссия: **{selected_m}**\n"
                f"📅 Опорный вторник сброса: **{reset_date} 11:00 МСК**\n\n"
                f"**Автоматический расчет ротации на следующие недели:**\n{preview_text}"
            ),
            embed=embed
        )

    # --- Команды ручной отправки конкретных видов сообщений ---

    @commands.command(name="schedule_send_paradise", aliases=["отправить_рай", "paradise_send"])
    @commands.has_permissions(administrator=True)
    async def schedule_send_paradise_cmd(self, ctx: commands.Context):
        """Ручная отправка сообщения: Сброс 'Потерянного рая'."""
        item = self._get_schedule_item("paradise_reset")
        if not item:
            await ctx.send(f"{ScheduleEmojis.ERROR} Событие 'paradise_reset' не найдено в конфиге.")
            return
        success = await self.send_event_notification(item)
        if success:
            await ctx.send(f"{ScheduleEmojis.SUCCESS} Сообщение **Сброс Потерянного рая** успешно отправлено!")
        else:
            await ctx.send(f"{ScheduleEmojis.ERROR} Не удалось отправить сообщение. Проверьте webhook_url или channel_id.")

    @app_commands.command(name="schedule_send_paradise", description="Отправить сообщение о сбросе 'Потерянного рая' (Админ)")
    @app_commands.checks.has_permissions(administrator=True)
    async def schedule_send_paradise_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item = self._get_schedule_item("paradise_reset")
        if not item:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Событие 'paradise_reset' не найдено.")
            return
        success = await self.send_event_notification(item)
        if success:
            await interaction.followup.send(f"{ScheduleEmojis.SUCCESS} Сообщение **Сброс Потерянного рая** успешно отправлено!")
        else:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Не удалось отправить сообщение. Проверьте настройки.")

    @commands.command(name="schedule_send_legendary", aliases=["отправить_легендарку", "legendary_send"])
    @commands.has_permissions(administrator=True)
    async def schedule_send_legendary_cmd(self, ctx: commands.Context):
        """Ручная отправка сообщения: Еженедельная Легендарная миссия."""
        item = self._get_schedule_item("legendary_mission")
        if not item:
            await ctx.send(f"{ScheduleEmojis.ERROR} Событие 'legendary_mission' не найдено в конфиге.")
            return
        success = await self.send_event_notification(item)
        if success:
            await ctx.send(f"{ScheduleEmojis.SUCCESS} Сообщение **Еженедельная Легендарная миссия** успешно отправлено!")
        else:
            await ctx.send(f"{ScheduleEmojis.ERROR} Не удалось отправить сообщение. Проверьте webhook_url или channel_id.")

    @app_commands.command(name="schedule_send_legendary", description="Отправить сообщение о легендарной миссии недели (Админ)")
    @app_commands.checks.has_permissions(administrator=True)
    async def schedule_send_legendary_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item = self._get_schedule_item("legendary_mission")
        if not item:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Событие 'legendary_mission' не найдено.")
            return
        success = await self.send_event_notification(item)
        if success:
            await interaction.followup.send(f"{ScheduleEmojis.SUCCESS} Сообщение **Еженедельная Легендарная миссия** успешно отправлено!")
        else:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Не удалось отправить сообщение. Проверьте настройки.")

    @commands.command(name="schedule_send_college", aliases=["отправить_колледж", "college_send"])
    @commands.has_permissions(administrator=True)
    async def schedule_send_college_cmd(self, ctx: commands.Context):
        """Ручная отправка сообщения: Обновление Колледжа Kenly."""
        item = self._get_schedule_item("college_reset")
        if not item:
            await ctx.send(f"{ScheduleEmojis.ERROR} Событие 'college_reset' не найдено в конфиге.")
            return
        success = await self.send_event_notification(item)
        if success:
            await ctx.send(f"{ScheduleEmojis.SUCCESS} Сообщение **Обновление Колледжа Kenly** успешно отправлено!")
        else:
            await ctx.send(f"{ScheduleEmojis.ERROR} Не удалось отправить сообщение. Проверьте webhook_url или channel_id.")

    @app_commands.command(name="schedule_send_college", description="Отправить сообщение об обновлении Колледжа Kenly (Админ)")
    @app_commands.checks.has_permissions(administrator=True)
    async def schedule_send_college_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item = self._get_schedule_item("college_reset")
        if not item:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Событие 'college_reset' не найдено.")
            return
        success = await self.send_event_notification(item)
        if success:
            await interaction.followup.send(f"{ScheduleEmojis.SUCCESS} Сообщение **Обновление Колледжа Kenly** успешно отправлено!")
        else:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Не удалось отправить сообщение. Проверьте настройки.")

    @commands.command(name="schedule_send_clan", aliases=["отправить_клан", "clan_send"])
    @commands.has_permissions(administrator=True)
    async def schedule_send_clan_cmd(self, ctx: commands.Context):
        """Ручная отправка сообщения: Доступен контейнер за клан."""
        item = self._get_schedule_item("clan_container")
        if not item:
            await ctx.send(f"{ScheduleEmojis.ERROR} Событие 'clan_container' не найдено в конфиге.")
            return
        success = await self.send_event_notification(item)
        if success:
            await ctx.send(f"{ScheduleEmojis.SUCCESS} Сообщение **Клановый контейнер** успешно отправлено!")
        else:
            await ctx.send(f"{ScheduleEmojis.ERROR} Не удалось отправить сообщение. Проверьте webhook_url или channel_id.")

    @app_commands.command(name="schedule_send_clan", description="Отправить сообщение о клановом контейнере (Админ)")
    @app_commands.checks.has_permissions(administrator=True)
    async def schedule_send_clan_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item = self._get_schedule_item("clan_container")
        if not item:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Событие 'clan_container' не найдено.")
            return
        success = await self.send_event_notification(item)
        if success:
            await interaction.followup.send(f"{ScheduleEmojis.SUCCESS} Сообщение **Клановый контейнер** успешно отправлено!")
        else:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Не удалось отправить сообщение. Проверьте настройки.")

    @commands.command(name="schedule_preview", aliases=["превью_расписания", "schedule_view"])
    @commands.has_permissions(administrator=True)
    async def schedule_preview_cmd(self, ctx: commands.Context, event_id: Optional[str] = None):
        """Префиксная команда для предпросмотра карточки события из расписания."""
        schedule = self.module_config.get("schedule", [])
        if not schedule:
            await ctx.send(f"{ScheduleEmojis.ERROR} Список событий расписания пуст.")
            return

        if event_id:
            target_item = self._get_schedule_item(event_id)
            if not target_item:
                await ctx.send(f"{ScheduleEmojis.ERROR} Событие с ID/алиасом `{event_id}` не найдено.")
                return
            embed = self.build_event_embed(target_item)
            view = SchedulePreviewActionView(self, target_item.get("id", ""))
            await ctx.send(content=f"{ScheduleEmojis.SEARCH} **Предпросмотр карточки события** (`{target_item.get('id')}`):", embed=embed, view=view)
        else:
            for item in schedule:
                e_id = item.get("id", "")
                embed = self.build_event_embed(item)
                view = SchedulePreviewActionView(self, e_id)
                await ctx.send(content=f"{ScheduleEmojis.SEARCH} **Предпросмотр карточки события** (`{e_id}`):", embed=embed, view=view)

    @app_commands.command(name="schedule_preview", description="Предпросмотр оформления карточки любого события из расписания (Админ)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(event_id="Событие для предпросмотра")
    @app_commands.choices(event_id=[
        app_commands.Choice(name="1. Сброс Потерянного рая (paradise_reset)", value="paradise_reset"),
        app_commands.Choice(name="2. Еженедельная Легендарная миссия (legendary_mission)", value="legendary_mission"),
        app_commands.Choice(name="3. Обновление Колледжа Kenly (college_reset)", value="college_reset"),
        app_commands.Choice(name="4. Доступен клановый контейнер (clan_container)", value="clan_container")
    ])
    async def schedule_preview_slash(self, interaction: discord.Interaction, event_id: Optional[str] = None):
        """Слэш-команда для предпросмотра оформления события из расписания."""
        await interaction.response.defer(ephemeral=True)
        schedule = self.module_config.get("schedule", [])
        if not schedule:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Список событий расписания пуст.")
            return

        target_item = None
        if event_id:
            target_item = self._get_schedule_item(event_id)
            if not target_item:
                await interaction.followup.send(f"{ScheduleEmojis.ERROR} Событие `{event_id}` не найдено.")
                return
        else:
            target_item = schedule[0]

        e_id = target_item.get("id", "")
        embed = self.build_event_embed(target_item)
        view = SchedulePreviewActionView(self, e_id)
        await interaction.followup.send(
            content=f"{ScheduleEmojis.SEARCH} **Предпросмотр карточки события** (`{e_id}`):",
            embed=embed,
            view=view
        )

    @commands.command(name="schedule_send", aliases=["отправить_расписание", "schedule_test"])
    @commands.has_permissions(administrator=True)
    async def schedule_send_cmd(self, ctx: commands.Context, event_id: Optional[str] = None):
        """Префиксная команда для принудительной отправки события из расписания."""
        schedule = self.module_config.get("schedule", [])
        if not schedule:
            await ctx.send(f"{ScheduleEmojis.ERROR} Список событий расписания пуст.")
            return

        target_item = None
        if event_id:
            target_item = self._get_schedule_item(event_id)

        if not target_item:
            target_item = schedule[0]

        success = await self.send_event_notification(target_item)
        if success:
            await ctx.send(f"{ScheduleEmojis.SUCCESS} Сообщение о событии `{target_item.get('id')}` успешно отправлено!")
        else:
            await ctx.send(f"{ScheduleEmojis.ERROR} Не удалось отправить сообщение. Проверьте webhook_url или channel_id в конфиге.")

    @app_commands.command(name="schedule_send", description="Принудительно отправить тестовое событие расписания в Webhook / канал (Админ)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(event_id="Событие из расписания")
    @app_commands.choices(event_id=[
        app_commands.Choice(name="1. Сброс еженедельных вылазок (paradise_reset)", value="paradise_reset"),
        app_commands.Choice(name="2. Еженедельная Легендарная миссия (legendary_mission)", value="legendary_mission"),
        app_commands.Choice(name="3. Обновление Колледжа Kenly (college_reset)", value="college_reset"),
        app_commands.Choice(name="4. Доступен клановый контейнер (clan_container)", value="clan_container")
    ])
    async def schedule_send_slash(self, interaction: discord.Interaction, event_id: Optional[str] = None):
        """Слэш-команда принудительной отправки тестового сообщения расписания."""
        await interaction.response.defer(ephemeral=True)

        schedule = self.module_config.get("schedule", [])
        if not schedule:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Список событий расписания пуст.")
            return

        target_item = None
        if event_id:
            target_item = self._get_schedule_item(event_id)

        if not target_item:
            target_item = schedule[0]

        success = await self.send_event_notification(target_item)
        if success:
            await interaction.followup.send(f"{ScheduleEmojis.SUCCESS} Сообщение о событии `{target_item.get('id')}` успешно отправлено!")
        else:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Не удалось отправить сообщение. Проверьте webhook_url или channel_id в конфиге.")

    async def _send_week_schedule(self, delay_seconds: float = 3.0) -> Tuple[int, int, List[str]]:
        """
        Отправляет все активные (enabled=True) события расписания подряд,
        с задержкой между отправками во избежание рейтлимита вебхука.
        Возвращает (успешно_отправлено, всего_активных, список_названий_с_ошибкой).
        """
        schedule = self.module_config.get("schedule", [])
        enabled_items = [item for item in schedule if item.get("enabled", True)]

        sent_count = 0
        failed_titles: List[str] = []

        for idx, item in enumerate(enabled_items):
            success = await self.send_event_notification(item)
            if success:
                sent_count += 1
            else:
                failed_titles.append(item.get("title", item.get("id", "неизвестно")))

            if idx < len(enabled_items) - 1:
                await asyncio.sleep(delay_seconds)

        return sent_count, len(enabled_items), failed_titles

    @commands.command(name="schedule_send_week", aliases=["отправить_неделю", "schedule_send_all"])
    @commands.has_permissions(administrator=True)
    async def schedule_send_week_cmd(self, ctx: commands.Context):
        """Префиксная команда для отправки всех активных событий расписания текущей недели одной командой."""
        schedule = self.module_config.get("schedule", [])
        if not schedule:
            await ctx.send(f"{ScheduleEmojis.ERROR} Список событий расписания пуст.")
            return

        status_msg = await ctx.send(f"{ScheduleEmojis.INFO} Отправляю все активные события расписания...")
        sent_count, total, failed_titles = await self._send_week_schedule()

        if failed_titles:
            failed_list = ", ".join(f"`{t}`" for t in failed_titles)
            await status_msg.edit(content=(
                f"{ScheduleEmojis.WARNING} Отправлено {sent_count}/{total} событий. "
                f"Не удалось отправить: {failed_list}. Проверьте webhook_url или channel_id в конфиге."
            ))
        else:
            await status_msg.edit(content=f"{ScheduleEmojis.SUCCESS} Все события расписания успешно отправлены ({sent_count}/{total})!")

    @app_commands.command(name="schedule_send_week", description="Отправить все активные события расписания текущей недели одной командой (Админ)")
    @app_commands.checks.has_permissions(administrator=True)
    async def schedule_send_week_slash(self, interaction: discord.Interaction):
        """Слэш-команда для отправки всех активных событий расписания текущей недели."""
        await interaction.response.defer(ephemeral=True)

        schedule = self.module_config.get("schedule", [])
        if not schedule:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Список событий расписания пуст.")
            return

        sent_count, total, failed_titles = await self._send_week_schedule()

        if failed_titles:
            failed_list = ", ".join(f"`{t}`" for t in failed_titles)
            await interaction.followup.send(
                f"{ScheduleEmojis.WARNING} Отправлено {sent_count}/{total} событий. "
                f"Не удалось отправить: {failed_list}. Проверьте webhook_url или channel_id в конфиге."
            )
        else:
            await interaction.followup.send(f"{ScheduleEmojis.SUCCESS} Все события расписания успешно отправлены ({sent_count}/{total})!")

    @commands.command(name="schedule_config", aliases=["настройка_расписания", "schedule_setup"])
    @commands.has_permissions(administrator=True)
    async def schedule_config_cmd(self, ctx: commands.Context):
        """Префиксная команда просмотра и настройки параметров игрового расписания."""
        embed = self.get_config_embed()
        view = ScheduleConfigView(self)
        await ctx.send(embed=embed, view=view)

    @app_commands.command(name="schedule_config", description="Настроить вебхук, имя, аватар, цвет и канал для игрового расписания (Админ)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        auto_publish="Включить/выключить автоматическую отправку по расписанию",
        webhook_url="URL вебхука Discord",
        webhook_username="Имя вебхука",
        webhook_avatar_url="URL или путь к аватарке вебхука",
        author_name="Текст шапки (Author)",
        footer_text="Текст подвала (Footer)",
        color="Цвет в формате RGB (например: 244, 102, 27)",
        channel="Канал Discord для отправки (если вебхук не используется)",
        ping_role="Роль для пинга"
    )
    async def schedule_config_slash(
        self,
        interaction: discord.Interaction,
        auto_publish: Optional[bool] = None,
        webhook_url: Optional[str] = None,
        webhook_username: Optional[str] = None,
        webhook_avatar_url: Optional[str] = None,
        author_name: Optional[str] = None,
        footer_text: Optional[str] = None,
        color: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None,
        ping_role: Optional[discord.Role] = None
    ):
        """Слэш-команда настройки параметров вебхука и канала игрового расписания."""
        await interaction.response.defer(ephemeral=True)
        guild_perms = getattr(interaction.user, "guild_permissions", None)
        if not guild_perms or not guild_perms.administrator:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} У вас нет прав администратора.")
            return

        updated = False
        if auto_publish is not None:
            self.module_config["auto_publish"] = auto_publish
            updated = True
        if webhook_url is not None:
            self.module_config["webhook_url"] = webhook_url.strip()
            updated = True
        if webhook_username is not None:
            self.module_config["webhook_username"] = webhook_username.strip()
            updated = True
        if webhook_avatar_url is not None:
            self.module_config["webhook_avatar_url"] = webhook_avatar_url.strip()
            updated = True
        if author_name is not None:
            self.module_config["author_name"] = author_name.strip()
            updated = True
        if footer_text is not None:
            self.module_config["footer_text"] = footer_text.strip()
            updated = True
        if color is not None:
            self.module_config["color"] = color.strip()
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
        view = ScheduleConfigView(self)
        msg = f"{ScheduleEmojis.SUCCESS} Настройки успешно обновлены!" if updated else f"{ScheduleEmojis.GEAR} Текущие настройки модуля игрового расписания:"
        await interaction.followup.send(content=msg, embed=embed, view=view)

    @commands.command(name="schedule_set_event_role", aliases=["установить_роль_события", "schedule_role", "event_role"])
    @commands.has_permissions(administrator=True)
    async def schedule_set_event_role_cmd(self, ctx: commands.Context, event_id: str, role: Optional[discord.Role] = None):
        """Префиксная команда для установки индивидуальной роли для конкретного события."""
        item = self._get_schedule_item(event_id)
        if not item:
            await ctx.send(f"{ScheduleEmojis.ERROR} Событие `{event_id}` не найдено.")
            return

        if role:
            item["ping_role_id"] = role.id
            self._save_module_config()
            await ctx.send(f"{ScheduleEmojis.SUCCESS} Для события `{item.get('id')}` установлена индивидуальная роль: {role.mention}")
        else:
            item["ping_role_id"] = None
            self._save_module_config()
            await ctx.send(f"{ScheduleEmojis.SUCCESS} Индивидуальная роль для события `{item.get('id')}` сброшена (будет использоваться общая роль).")

    @app_commands.command(name="schedule_set_event_role", description="Установить индивидуальную роль для пинга конкретного события (Админ)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        event_id="Событие из расписания",
        role="Роль для пинга (оставьте пустым для сброса на общую роль)"
    )
    @app_commands.choices(event_id=[
        app_commands.Choice(name="1. Сброс еженедельных вылазок (paradise_reset)", value="paradise_reset"),
        app_commands.Choice(name="2. Еженедельная Легендарная миссия (legendary_mission)", value="legendary_mission"),
        app_commands.Choice(name="3. Обновление Колледжа Kenly (college_reset)", value="college_reset"),
        app_commands.Choice(name="4. Доступен клановый контейнер (clan_container)", value="clan_container")
    ])
    async def schedule_set_event_role_slash(
        self,
        interaction: discord.Interaction,
        event_id: str,
        role: Optional[discord.Role] = None
    ):
        """Слэш-команда установки индивидуальной роли события."""
        await interaction.response.defer(ephemeral=True)
        item = self._get_schedule_item(event_id)
        if not item:
            await interaction.followup.send(f"{ScheduleEmojis.ERROR} Событие `{event_id}` не найдено.")
            return

        if role:
            item["ping_role_id"] = role.id
            self._save_module_config()
            await interaction.followup.send(f"{ScheduleEmojis.SUCCESS} Для события `{item.get('id')}` установлена индивидуальная роль: {role.mention}")
        else:
            item["ping_role_id"] = None
            self._save_module_config()
            await interaction.followup.send(f"{ScheduleEmojis.SUCCESS} Индивидуальная роль для события `{item.get('id')}` сброшена (будет использоваться общая роль).")


class ScheduleConfigModal(discord.ui.Modal, title="Настройка игрового расписания"):
    webhook_url_input = discord.ui.TextInput(
        label="URL Webhook",
        placeholder="https://discord.com/api/webhooks/...",
        required=False,
        style=discord.TextStyle.short
    )
    webhook_username_input = discord.ui.TextInput(
        label="Имя вебхука",
        placeholder="Игровое расписание",
        required=False,
        style=discord.TextStyle.short
    )
    webhook_avatar_input = discord.ui.TextInput(
        label="URL или путь к аватарке вебхука",
        placeholder="https://... или assets/images/...",
        required=False,
        style=discord.TextStyle.short
    )
    author_name_input = discord.ui.TextInput(
        label="Текст шапки (Author)",
        placeholder="Игровое расписание The Division 2",
        required=False,
        style=discord.TextStyle.short
    )
    footer_text_input = discord.ui.TextInput(
        label="Текст подвала (Footer)",
        placeholder="Игровое расписание The Division 2",
        required=False,
        style=discord.TextStyle.short
    )

    def __init__(self, cog: 'GameScheduleModule'):
        super().__init__()
        self.cog = cog
        self.webhook_url_input.default = cog.module_config.get("webhook_url", "") or ""
        self.webhook_username_input.default = cog.module_config.get("webhook_username", "Игровое расписание") or "Игровое расписание"
        self.webhook_avatar_input.default = cog.module_config.get("webhook_avatar_url", "") or ""
        self.author_name_input.default = cog.module_config.get("author_name", "") or ""
        self.footer_text_input.default = cog.module_config.get("footer_text", "") or ""

    async def on_submit(self, interaction: discord.Interaction):
        self.cog.module_config["webhook_url"] = self.webhook_url_input.value.strip()
        self.cog.module_config["webhook_username"] = self.webhook_username_input.value.strip() or "Игровое расписание"
        self.cog.module_config["webhook_avatar_url"] = self.webhook_avatar_input.value.strip()
        self.cog.module_config["author_name"] = self.author_name_input.value.strip()
        self.cog.module_config["footer_text"] = self.footer_text_input.value.strip()
        self.cog._save_module_config()

        embed = self.cog.get_config_embed()
        view = ScheduleConfigView(self.cog)
        await interaction.response.send_message(
            content=f"{ScheduleEmojis.SUCCESS} Настройки вебхука и оформления игрового расписания успешно сохранены!",
            embed=embed,
            view=view,
            ephemeral=True
        )


class ScheduleEventImagesModal(discord.ui.Modal, title="Настройка изображений события"):
    event_id_input = discord.ui.TextInput(
        label="ID события",
        placeholder="paradise_reset / legendary_mission / college_reset / clan_container",
        required=True,
        style=discord.TextStyle.short
    )
    thumbnail_input = discord.ui.TextInput(
        label="URL миниатюры (thumbnail_url)",
        placeholder="https://... или assets/...",
        required=False,
        style=discord.TextStyle.short
    )
    image_input = discord.ui.TextInput(
        label="URL баннера (image_url)",
        placeholder="https://... или assets/...",
        required=False,
        style=discord.TextStyle.short
    )

    def __init__(self, cog: 'GameScheduleModule', default_event_id: str = ""):
        super().__init__()
        self.cog = cog
        if default_event_id:
            self.event_id_input.default = default_event_id
            for item in cog.module_config.get("schedule", []):
                if item.get("id") == default_event_id:
                    self.thumbnail_input.default = item.get("thumbnail_url", "") or ""
                    self.image_input.default = item.get("image_url", "") or ""
                    break

    async def on_submit(self, interaction: discord.Interaction):
        event_id = self.event_id_input.value.strip()
        schedule = self.cog.module_config.get("schedule", [])
        target_item = None
        for item in schedule:
            if item.get("id") == event_id:
                target_item = item
                break

        if not target_item:
            await interaction.response.send_message(
                f"{ScheduleEmojis.ERROR} Событие с ID `{event_id}` не найдено в расписании.",
                ephemeral=True
            )
            return

        target_item["thumbnail_url"] = self.thumbnail_input.value.strip()
        target_item["image_url"] = self.image_input.value.strip()
        self.cog._save_module_config()

        preview_embed = self.cog.build_event_embed(target_item)
        await interaction.response.send_message(
            content=f"{ScheduleEmojis.SUCCESS} Изображения для события `{event_id}` успешно обновлены! Предпросмотр ниже:",
            embed=preview_embed,
            ephemeral=True
        )


class ScheduleEventPreviewSelect(discord.ui.Select):
    def __init__(self, cog: 'GameScheduleModule'):
        self.cog = cog
        options = []
        schedule = cog.module_config.get("schedule", [])
        for item in schedule:
            event_id = item.get("id", "unknown")
            raw_title = item.get("title", event_id)
            clean_title = raw_title.replace("{emoji_reset}", ScheduleEmojis.RESET)\
                                   .replace("{emoji_trophy}", ScheduleEmojis.TROPHY)\
                                   .replace("{emoji_college}", ScheduleEmojis.COLLEGE)\
                                   .replace("{emoji_container}", ScheduleEmojis.CONTAINER)
            options.append(discord.SelectOption(
                label=clean_title[:100],
                value=event_id,
                description=f"Превью карточки события: {event_id}"[:100]
            ))

        if not options:
            options.append(discord.SelectOption(label="Нет доступных событий", value="none"))

        super().__init__(
            placeholder=f"{ScheduleEmojis.SEARCH} Выберите событие для предпросмотра...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        event_id = self.values[0]
        if event_id == "none":
            await interaction.response.send_message(f"{ScheduleEmojis.ERROR} Нет доступных событий.", ephemeral=True)
            return

        schedule = self.cog.module_config.get("schedule", [])
        target_item = None
        for item in schedule:
            if item.get("id") == event_id:
                target_item = item
                break

        if not target_item:
            await interaction.response.send_message(f"{ScheduleEmojis.ERROR} Событие не найдено.", ephemeral=True)
            return

        embed = self.cog.build_event_embed(target_item)
        view = SchedulePreviewActionView(self.cog, event_id)
        await interaction.response.send_message(
            content=f"{ScheduleEmojis.SEARCH} **Предпросмотр визуального оформления события** (`{event_id}`):",
            embed=embed,
            view=view,
            ephemeral=True
        )


class ScheduleEventRoleSelect(discord.ui.RoleSelect):
    def __init__(self, cog: 'GameScheduleModule', event_id: str):
        self.cog = cog
        self.event_id = event_id
        super().__init__(
            placeholder="Выберите специальную роль для этого события...",
            min_values=0,
            max_values=1,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        guild_perms = getattr(interaction.user, "guild_permissions", None)
        if not guild_perms or not guild_perms.administrator:
            await interaction.response.send_message(f"{ScheduleEmojis.ERROR} У вас нет прав администратора.", ephemeral=True)
            return

        item = self.cog._get_schedule_item(self.event_id)
        if not item:
            await interaction.response.send_message(f"{ScheduleEmojis.ERROR} Событие `{self.event_id}` не найдено.", ephemeral=True)
            return

        if self.values:
            role = self.values[0]
            item["ping_role_id"] = role.id
            msg_text = f"{ScheduleEmojis.SUCCESS} Индивидуальная роль для события `{self.event_id}` установлена: <@&{role.id}>"
        else:
            item["ping_role_id"] = None
            msg_text = f"{ScheduleEmojis.SUCCESS} Индивидуальная роль для события `{self.event_id}` сброшена (будет использоваться общая роль)."

        self.cog._save_module_config()
        embed = self.cog.build_event_embed(item)
        await interaction.response.send_message(content=msg_text, embed=embed, ephemeral=True)


class SchedulePreviewActionView(discord.ui.View):
    def __init__(self, cog: 'GameScheduleModule', event_id: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.event_id = event_id
        self.add_item(ScheduleEventRoleSelect(cog, event_id))

    @discord.ui.button(label="Настроить картинки этого события", style=discord.ButtonStyle.secondary, emoji=ScheduleEmojis.IMAGE, row=1)
    async def edit_images_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_perms = getattr(interaction.user, "guild_permissions", None)
        if not guild_perms or not guild_perms.administrator:
            await interaction.response.send_message(f"{ScheduleEmojis.ERROR} У вас нет прав администратора.", ephemeral=True)
            return
        modal = ScheduleEventImagesModal(self.cog, default_event_id=self.event_id)
        await interaction.response.send_modal(modal)


class ScheduleConfigView(discord.ui.View):
    def __init__(self, cog: 'GameScheduleModule'):
        super().__init__(timeout=180)
        self.cog = cog
        self.add_item(ScheduleEventPreviewSelect(cog))

        auto_pub = cog.module_config.get("auto_publish", True)
        pub_label = "Выключить автопубликацию" if auto_pub else "Включить автопубликацию"
        pub_style = discord.ButtonStyle.danger if auto_pub else discord.ButtonStyle.success
        
        btn = discord.ui.Button(label=pub_label, style=pub_style, emoji="⚙️", row=1)
        btn.callback = self.toggle_auto_publish
        self.add_item(btn)

    async def toggle_auto_publish(self, interaction: discord.Interaction):
        guild_perms = getattr(interaction.user, "guild_permissions", None)
        if not guild_perms or not guild_perms.administrator:
            await interaction.response.send_message(f"{ScheduleEmojis.ERROR} У вас нет прав администратора.", ephemeral=True)
            return

        current = self.cog.module_config.get("auto_publish", True)
        self.cog.module_config["auto_publish"] = not current
        self.cog._save_module_config()

        embed = self.cog.get_config_embed()
        new_view = ScheduleConfigView(self.cog)
        status_str = "включена" if not current else "выключена"
        await interaction.response.send_message(
            content=f"{ScheduleEmojis.SUCCESS} Автопубликация игрового расписания {status_str}!",
            embed=embed,
            view=new_view,
            ephemeral=True
        )

    @discord.ui.button(label="Настройки вебхука и оформления", style=discord.ButtonStyle.primary, emoji=ScheduleEmojis.GEAR, row=2)
    async def edit_webhook_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_perms = getattr(interaction.user, "guild_permissions", None)
        if not guild_perms or not guild_perms.administrator:
            await interaction.response.send_message(f"{ScheduleEmojis.ERROR} У вас нет прав администратора.", ephemeral=True)
            return
        modal = ScheduleConfigModal(self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Изменить картинки события", style=discord.ButtonStyle.secondary, emoji=ScheduleEmojis.IMAGE, row=2)
    async def edit_event_images_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_perms = getattr(interaction.user, "guild_permissions", None)
        if not guild_perms or not guild_perms.administrator:
            await interaction.response.send_message(f"{ScheduleEmojis.ERROR} У вас нет прав администратора.", ephemeral=True)
            return
        modal = ScheduleEventImagesModal(self.cog)
        await interaction.response.send_modal(modal)


async def setup(bot):
    cog = GameScheduleModule(bot)
    await bot.add_cog(cog)
    if hasattr(bot, 'app'):
        bot.app.game_schedule_module = cog
