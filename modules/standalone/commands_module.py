# modules/standalone/commands_module.py
import discord
from discord.ext import commands
from discord import app_commands
from modules_utils.stats_manager import stats_manager
from constants.emojis import LogEmojis, StartupEmojis, Emojis, EmojisFields, StatusEmojis, LiveEmojis
from constants.strings import BotStrings
from modules_utils.helpers import hex_to_color_int, resolve_asset_url, parse_color_to_int, safe_create_task
from log_system.logger_helper import send_to_any_log
from settings.config import Config
from settings.data_files import Files
import asyncio
import json
import os
import sys
import calendar
from datetime import datetime, timezone, timedelta
from typing import Optional
from modules_utils.files import get_project_path, get_config_path
from modules_utils.restart_helper import RestartHelper

def get_help_categories():
    return {
        "all": {
            "label": getattr(BotStrings, "HELP_ALL_CAT_LABEL", "📋 Все категории"),
            "description": getattr(BotStrings, "HELP_ALL_CAT_DESC", "Показать обзор всех разделов и категорий команд"),
            "emoji": "📋"
        },
        "info": {
            "label": getattr(BotStrings, "HELP_INFO_CAT_LABEL", "📊 Информация и статус"),
            "description": getattr(BotStrings, "HELP_INFO_CAT_DESC", "Статус бота, источники трансляций, бустеры сервера и группы VK"),
            "emoji": "📊",
            "commands": [
                {"name": "/status", "aliases": ["!status"], "desc": "Показать статус работы бота, нагрузку и статистику активных мониторов"},
                {"name": "/sources", "aliases": ["!sources"], "desc": "Показать список подключенных источников и каналов публикации"},
                {"name": "/boosts", "aliases": ["!boosts"], "desc": "Показать список активных бустеров сервера и дату начала их буста"},
                {"name": "/vk_groups_info", "aliases": ["!vk_groups_info"], "desc": "Показать информацию о подписках и токенах групп VK"},
                {"name": "/help", "aliases": ["!help", "?help"], "desc": "Показать справку по всем командам бота с фильтрацией по категориям"}
            ]
        },
        "game": {
            "label": getattr(BotStrings, "HELP_GAME_CAT_LABEL", "🎮 Игровое расписание и торговцы"),
            "description": getattr(BotStrings, "HELP_GAME_CAT_DESC", "Секретные торговцы Division 2, расписание и ротация миссий"),
            "emoji": "🎮",
            "commands": [
                {"name": "/vendors", "aliases": ["!vendors"], "desc": "Показать текущий статус и местоположение секретных торговцев (Дэнни и Кэйси)"},
                {"name": "/vendors_send", "aliases": ["!vendors_send"], "desc": "Принудительно отправить карточки торговцев в канал", "perm": "Администратор"},
                {"name": "/vendors_config", "aliases": ["!vendors_config"], "desc": "Настроить вебхук, цвет, аватар и каналы для торговцев", "perm": "Администратор"},
                {"name": "/schedule_preview", "aliases": ["!schedule_preview"], "desc": "Предпросмотр карточки любого события из игрового расписания", "perm": "Администратор"},
                {"name": "/schedule_send_week", "aliases": ["!schedule_send_week"], "desc": "Отправить все активные события расписания текущей недели одной командой", "perm": "Администратор"},
                {"name": "/schedule_send", "aliases": ["!schedule_send"], "desc": "Принудительно отправить тестовое событие расписания в канал", "perm": "Администратор"},
                {"name": "/schedule_set_legendary", "aliases": ["!schedule_set_legendary"], "desc": "Установить текущую легендарную миссию недели и запустить ротацию", "perm": "Администратор"},
                {"name": "/schedule_config", "aliases": ["!schedule_config"], "desc": "Настроить вебхук, имя, аватар и канал для игрового расписания", "perm": "Администратор"},
                {"name": "/schedule_set_event_role", "aliases": ["!schedule_set_event_role"], "desc": "Установить индивидуальную роль для пинга конкретного события", "perm": "Администратор"}
            ]
        },
        "roles": {
            "label": getattr(BotStrings, "HELP_ROLES_CAT_LABEL", "🛡️ Роли и Активность"),
            "description": getattr(BotStrings, "HELP_ROLES_CAT_DESC", "Связанные роли сервера, уровни и автоотслеживание активности"),
            "emoji": "🛡️",
            "commands": [
                {"name": "/rules", "aliases": ["!rules"], "desc": "Показать активные правила связанных ролей сервера"},
                {"name": "/activity", "aliases": ["!activity"], "desc": "Показать детализированную информацию об активности участника"},
                {"name": "/activity_rules", "aliases": ["!activity_rules"], "desc": "Показать правила и настройки автоматического отслеживания активности"},
                {"name": "/sync_activity", "aliases": ["!sync_activity"], "desc": "Принудительно синхронизировать роли активности участников", "perm": "Администратор"},
                {"name": "/reload_roles", "aliases": ["!reload_roles"], "desc": "Перезагрузить конфигурационный файл связанных ролей (role_dependencies.json)", "perm": "Владелец"}
            ]
        },
        "voice": {
            "label": getattr(BotStrings, "HELP_VOICE_CAT_LABEL", "🔊 Голосовые каналы"),
            "description": getattr(BotStrings, "HELP_VOICE_CAT_DESC", "Управление и массовая смена регионов голосовых каналов"),
            "emoji": "🔊",
            "commands": [
                {"name": "/voice-region", "aliases": ["!voice-region"], "desc": "Массово сменить регион во всех голосовых каналах текущего сервера", "perm": "Администратор"},
                {"name": "/voice-list", "aliases": ["!voice-list"], "desc": "Показать список всех голосовых каналов сервера и их текущие регионы", "perm": "Администратор"}
            ]
        },
        "media": {
            "label": getattr(BotStrings, "HELP_MEDIA_CAT_LABEL", "🖼️ Перенаправление картинок"),
            "description": getattr(BotStrings, "HELP_MEDIA_CAT_DESC", "Автоматическое перенаправление изображений между каналами"),
            "emoji": "🖼️",
            "commands": [
                {"name": "/forwarder_status", "aliases": ["!forwarder_status"], "desc": "Показать статус и правила работы модуля перенаправления картинок"},
                {"name": "/forwarder_add", "aliases": ["!forwarder_add"], "desc": "Добавить новое правило перенаправления картинок из одного канала в другой", "perm": "Администратор"}
            ]
        },
        "admin": {
            "label": getattr(BotStrings, "HELP_ADMIN_CAT_LABEL", "⚙️ Администрирование и Система"),
            "description": getattr(BotStrings, "HELP_ADMIN_CAT_DESC", "Управление конфигурациями, синхронизация, статусы и выключение"),
            "emoji": "⚙️",
            "commands": [
                {"name": "/reload", "aliases": ["!reload"], "desc": "Перечитать конфигурации из папок и настройки команд", "perm": "Администратор"},
                {"name": "/check_groups", "aliases": ["!check_groups"], "desc": "Принудительно проверить все подключенные группы VK на новые посты", "perm": "Администратор"},
                {"name": "/sync", "aliases": ["!sync"], "desc": "Синхронизировать слэш-команды бота с Discord API", "perm": "Владелец"},
                {"name": "/set_status", "aliases": ["!set_status"], "desc": "Установить сетевой статус бота (Online, Idle, DND, Invisible)", "perm": "Владелец"},
                {"name": "/set_activity", "aliases": ["!set_activity"], "desc": "Установить кастомный текст активности бота", "perm": "Владелец"},
                {"name": "/set_stream", "aliases": ["!set_stream"], "desc": "Установить статус стрима бота с кастомной ссылкой", "perm": "Владелец"},
                {"name": "/restart", "aliases": ["!restart"], "desc": "Безопасно перезапустить бота", "perm": "Владелец"},
                {"name": "/shutdown", "aliases": ["!shutdown"], "desc": "Полностью выключить бота", "perm": "Владелец"}
            ]
        }
    }


HELP_CATEGORIES = get_help_categories()


def build_help_embed(selected_category: str = "all", bot_user: discord.User = None) -> discord.Embed:
    """Формирует Embed со справкой по командам бота."""
    categories = get_help_categories()
    title_text = getattr(BotStrings, "HELP_EMBED_TITLE", "Справка по командам бота")
    desc_text = getattr(
        BotStrings,
        "HELP_EMBED_DESC",
        "Используйте выпадающее меню ниже для просмотра команд по категориям. "
        "Вы можете использовать как слэш-команды (`/`), так и префиксные команды (`!`)."
    )

    embed = discord.Embed(
        title=f"{Emojis.INFO if hasattr(Emojis, 'INFO') else 'ℹ️'} {title_text}",
        description=desc_text,
        color=0x2b2d31
    )

    if bot_user and hasattr(bot_user, "display_avatar"):
        embed.set_thumbnail(url=bot_user.display_avatar.url)

    if selected_category == "all" or selected_category not in categories:
        total_cmds = sum(len(cat.get("commands", [])) for cat in categories.values() if "commands" in cat)
        total_cats = sum(1 for k in categories.keys() if k != "all")
        overview_name = getattr(BotStrings, "HELP_OVERVIEW_NAME", "📌 Обзор возможностей")
        overview_val_tmpl = getattr(
            BotStrings,
            "HELP_OVERVIEW_VALUE",
            "Бот содержит **{total_cmds} команд**, разделенных по **{total_cats} категориям**.\n"
            "Выберите нужную категорию в меню ниже, чтобы открыть подробное описание каждого раздела."
        )
        embed.add_field(
            name=overview_name,
            value=overview_val_tmpl.format(total_cmds=total_cmds, total_cats=total_cats),
            inline=False
        )

        for cat_key, cat_data in categories.items():
            if cat_key == "all" or "commands" not in cat_data:
                continue
            cmds_count = len(cat_data["commands"])
            embed.add_field(
                name=f"{cat_data['label']} ({cmds_count})",
                value=cat_data["description"],
                inline=True
            )
    else:
        cat_data = categories[selected_category]
        embed.title = f"{cat_data['emoji']} {cat_data['label']}"
        embed.description = f"*{cat_data['description']}*\n\n"

        cmds = cat_data.get("commands", [])
        prefix_lbl = getattr(BotStrings, "HELP_PREFIX_LABEL", "\n*Префикс:* `{aliases}`")
        perm_lbl = getattr(BotStrings, "HELP_PERM_LABEL", " • 🔒 **{perm}**")
        for cmd in cmds:
            name = cmd["name"]
            aliases = prefix_lbl.format(aliases=", ".join(cmd['aliases'])) if cmd.get("aliases") else ""
            perm = perm_lbl.format(perm=cmd['perm']) if cmd.get("perm") else ""
            value = f"{cmd['desc']}{perm}{aliases}"
            embed.add_field(
                name=f"`{name}`",
                value=value,
                inline=False
            )

    footer_text = getattr(BotStrings, "HELP_FOOTER_TEXT", "Префикс для текстовых команд: ! | Вызов слэш-команд: /")
    embed.set_footer(text=footer_text)
    return embed


class HelpSelectView(discord.ui.View):
    def __init__(self, bot_user: discord.User = None):
        super().__init__(timeout=180)
        self.bot_user = bot_user

        options = []
        for cat_key, cat_data in get_help_categories().items():
            options.append(
                discord.SelectOption(
                    label=cat_data["label"],
                    value=cat_key,
                    description=cat_data["description"][:100],
                    emoji=cat_data.get("emoji")
                )
            )

        select = discord.ui.Select(
            placeholder=getattr(BotStrings, "HELP_SELECT_PLACEHOLDER", "Выберите категорию команд..."),
            min_values=1,
            max_values=1,
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selected_key = interaction.data["values"][0]
        embed = build_help_embed(selected_key, self.bot_user or interaction.client.user)
        await interaction.response.edit_message(embed=embed, view=self)


class CommandsModule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_config = {}
        self._load_status_config()

    def _load_status_config(self):
        """Загружает настройки эмбеда статуса из JSON."""
        config_path = Files.STATUS_CONFIG_PATH
        if not os.path.exists(config_path):
            config_path = get_project_path("data", "json", "status_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.status_config = json.load(f)
            except Exception as e:
                safe_create_task(send_to_any_log("error", f"COMMANDS: Error loading status_config.json: {e}", emoji=LogEmojis.ERROR))
                self.status_config = {}
        else:
            self.status_config = {}

    @commands.command(name="help", aliases=["справка", "помощь", "commands", "команды"])
    async def help_prefix(self, ctx, category: str = None):
        """Показывает справку по командам бота (префиксная версия)."""
        cat_key = "all"
        if category:
            cat_lower = category.lower().strip()
            for k, v in HELP_CATEGORIES.items():
                if cat_lower in k or cat_lower in v["label"].lower():
                    cat_key = k
                    break

        embed = build_help_embed(cat_key, self.bot.user)
        view = HelpSelectView(self.bot.user)
        await ctx.send(embed=embed, view=view)

    @app_commands.command(name="help", description=getattr(BotStrings, "HELP_CMD_DESC", "Показать список всех команд бота с фильтром по категориям"))
    @app_commands.describe(category="Категория команд для фильтрации")
    @app_commands.choices(category=[
        app_commands.Choice(name="📋 Все категории", value="all"),
        app_commands.Choice(name="📊 Информация и статус", value="info"),
        app_commands.Choice(name="🎮 Игровое расписание и торговцы", value="game"),
        app_commands.Choice(name="🛡️ Роли и Активность", value="roles"),
        app_commands.Choice(name="🔊 Голосовые каналы", value="voice"),
        app_commands.Choice(name="🖼️ Перенаправление картинок", value="media"),
        app_commands.Choice(name="⚙️ Администрирование и Система", value="admin"),
    ])
    async def help_slash(self, interaction: discord.Interaction, category: str = "all"):
        """Показывает справку по командам бота (слэш-версия)."""
        embed = build_help_embed(category, self.bot.user)
        view = HelpSelectView(self.bot.user)
        await interaction.response.send_message(embed=embed, view=view)

    @commands.command(name="sync")
    @commands.is_owner()
    async def sync_prefix(self, ctx, scope: str = "global"):
        """Синхронизирует слэш-команды (префиксная версия). 
        Использование: !sync [global/guild]
        """
        try:
            if scope.lower() == "guild":
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)
                await ctx.send(f"{Emojis.SUCCESS} " + BotStrings.SYNC_GUILD_SUCCESS.format(count=len(synced)))
            else:
                synced = await self.bot.tree.sync()
                await ctx.send(f"{Emojis.SUCCESS} " + BotStrings.SYNC_GLOBAL_SUCCESS.format(count=len(synced)))
        except Exception as e:
            await ctx.send(f"{Emojis.FAILURE} " + BotStrings.SYNC_ERROR.format(error=e))

    @app_commands.command(name="sync", description=BotStrings.SYNC_CMD_DESC)
    async def sync_slash(self, interaction: discord.Interaction):
        """Синхронизирует слэш-команды (слэш-версия)."""
        is_owner = await self.bot.is_owner(interaction.user)
        if not is_owner:
            await interaction.response.send_message(f"{Emojis.FAILURE} {BotStrings.SYNC_ERR_OWNER_ONLY}", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(f"{Emojis.SUCCESS} " + BotStrings.SYNC_GLOBAL_SUCCESS.format(count=len(synced)))
        except Exception as e:
            await interaction.followup.send(f"{Emojis.FAILURE} " + BotStrings.SYNC_ERROR.format(error=e))

    @commands.command(name="status", aliases=["статус", "bot_status"])
    async def status_cmd(self, ctx: commands.Context):
        """Префиксная команда статуса."""
        await self._send_status(ctx)

    @app_commands.command(name="status", description="Показать статус и статистику мониторов")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
    async def status(self, interaction: discord.Interaction):
        """Слэш-команда статуса."""
        await self._send_status(interaction)

    @commands.command(name="reload", aliases=["перезагрузка", "релоад"])
    @commands.has_permissions(administrator=True)
    async def reload_cmd(self, ctx: commands.Context):
        """Префиксная команда перезагрузки конфигураций."""
        try:
            self._load_status_config()
            app = getattr(self.bot, "app", None)
            if not app:
                await ctx.send(f"{Emojis.FAILURE} Не удалось получить доступ к основному приложению.")
                return

            tasks = []
            managers = [
                app.vk_wall_manager,
                app.vk_live_manager,
                getattr(app, "youtube_manager", None),
                getattr(app, "rutube_manager", None),
                app.twitch_live_manager,
                app.kick_live_manager,
                app.vk_asset_manager
            ]

            for manager in managers:
                if manager and hasattr(manager, "reload_all"):
                    tasks.append(manager.reload_all())
            
            if tasks:
                await asyncio.gather(*tasks)
                await ctx.send(f"{Emojis.SUCCESS} {BotStrings.get('CMD_RELOAD_SUCCESS', 'Все конфигурации и настройки статуса успешно перезагружены!')}")
            else:
                await ctx.send(f"{Emojis.WARNING} {BotStrings.get('CMD_RELOAD_NO_MANAGERS', 'Активные менеджеры для перезагрузки не найдены. Настройки статуса обновлены.')}")
        except Exception as e:
            await ctx.send(f"{Emojis.FAILURE} {BotStrings.get('CMD_RELOAD_ERROR', 'Ошибка при перезагрузке: {error}').format(error=str(e))}")

    @app_commands.command(name="reload", description="Перечитать конфигурации из папок конфигураций и настройки команд")
    @app_commands.checks.has_permissions(administrator=True)
    async def reload(self, interaction: discord.Interaction):
        """Слэш-команда перезагрузки конфигураций."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Перезагружаем настройки команд
            self._load_status_config()
            
            app = getattr(self.bot, "app", None)
            if not app:
                await interaction.followup.send(f"{Emojis.FAILURE} {BotStrings.get('APP_INSTANCE_ERROR', 'Не удалось получить доступ к основному приложению.')}")
                return

            tasks = []
            # Перечисляем все менеджеры, которые поддерживают reload_all
            managers = [
                app.vk_wall_manager,
                app.vk_live_manager,
                getattr(app, "youtube_manager", None),
                getattr(app, "rutube_manager", None),
                app.twitch_live_manager,
                app.kick_live_manager,
                app.vk_asset_manager
            ]

            for manager in managers:
                if manager and hasattr(manager, "reload_all"):
                    tasks.append(manager.reload_all())
            
            if tasks:
                await asyncio.gather(*tasks)
                await interaction.followup.send(f"{Emojis.SUCCESS} {BotStrings.get('CMD_RELOAD_SUCCESS', 'Все конфигурации и настройки статуса успешно перезагружены!')}")
            else:
                await interaction.followup.send(f"{Emojis.WARNING} {BotStrings.get('CMD_RELOAD_NO_MANAGERS', 'Активные менеджеры для перезагрузки не найдены. Настройки статуса обновлены.')}")
                
        except Exception as e:
            await interaction.followup.send(f"{Emojis.FAILURE} {BotStrings.get('CMD_RELOAD_ERROR', 'Ошибка при перезагрузке: {error}').format(error=str(e))}")

    @commands.command(name="restart")
    @commands.is_owner()
    async def restart_prefix(self, ctx):
        """Перезапускает бота (только для владельца бота)."""
        username = ctx.author.global_name or ctx.author.name
        reason = f"Перезапуск по команде пользователя: {ctx.author} ({username})"
        await ctx.send(f"{Emojis.SUCCESS} {BotStrings.get('RESTART_EXECUTING', 'Выполняется штатный перезапуск бота...')}")
        app = getattr(self.bot, "app", None)
        if app:
            safe_create_task(app.request_graceful_restart(reason))
        else:
            await ctx.send(f"{Emojis.FAILURE} {BotStrings.get('APP_INSTANCE_ERROR', 'ОШИБКА: Не удалось получить экземпляр приложения.')}")

    @commands.command(name="shutdown", aliases=["stop_bot", "off"])
    @commands.is_owner()
    async def shutdown_prefix(self, ctx):
        """Полностью выключает бота (только для владельца)."""
        username = ctx.author.global_name or ctx.author.name
        reason = f"Выключение по команде пользователя: {ctx.author} ({username})"
        await ctx.send(f"{Emojis.SUCCESS} {BotStrings.get('SHUTDOWN_EXECUTING', 'Выполняется штатное выключение бота...')}")
        app = getattr(self.bot, "app", None)
        if app:
            safe_create_task(app.request_graceful_shutdown(reason))
        else:
            await ctx.send(f"{Emojis.FAILURE} {BotStrings.get('APP_INSTANCE_ERROR', 'ОШИБКА: Не удалось получить экземпляр приложения.')}")

    @app_commands.command(name="restart", description="Перезапустить бота (только для владельца)")
    async def restart_slash(self, interaction: discord.Interaction):
        """Перезапускает бота (слэш-версия)."""
        is_owner = await self.bot.is_owner(interaction.user)
        if not is_owner:
            await interaction.response.send_message(f"{Emojis.FAILURE} {BotStrings.get('OWNER_ONLY_ERROR', 'Эта команда доступна только владельцу бота.')}", ephemeral=True)
            return

        username = interaction.user.global_name or interaction.user.name
        reason = f"Перезапуск по команде пользователя: {interaction.user} ({username})"
        await interaction.response.send_message(
            f"{Emojis.SUCCESS} {BotStrings.get('RESTART_EXECUTING', 'Выполняется штатный перезапуск бота...')}", ephemeral=True
        )
        app = getattr(self.bot, "app", None)
        if app:
            safe_create_task(app.request_graceful_restart(reason))
        else:
            await interaction.followup.send(f"{Emojis.FAILURE} {BotStrings.get('APP_INSTANCE_ERROR', 'ОШИБКА: Не удалось получить экземпляр приложения.')}", ephemeral=True)

    @app_commands.command(name="shutdown", description="Полностью выключить бота (только для владельца)")
    async def shutdown_slash(self, interaction: discord.Interaction):
        """Полностью выключает бота (слэш-версия)."""
        is_owner = await self.bot.is_owner(interaction.user)
        if not is_owner:
            await interaction.response.send_message(f"{Emojis.FAILURE} {BotStrings.get('OWNER_ONLY_ERROR', 'Эта команда доступна только владельцу бота.')}", ephemeral=True)
            return

        username = interaction.user.global_name or interaction.user.name
        reason = f"Выключение по команде пользователя: {interaction.user} ({username})"
        await interaction.response.send_message(
            f"{Emojis.SUCCESS} {BotStrings.get('SHUTDOWN_EXECUTING', 'Выполняется штатное выключение бота...')}", ephemeral=True
        )
        app = getattr(self.bot, "app", None)
        if app:
            safe_create_task(app.request_graceful_shutdown(reason))
        else:
            await interaction.followup.send(f"{Emojis.FAILURE} {BotStrings.get('APP_INSTANCE_ERROR', 'ОШИБКА: Не удалось получить экземпляр приложения.')}", ephemeral=True)

    async def _send_status(self, target):
        stats = stats_manager.get_stats()
        
        # Получаем статистику постов за 24 часа и 7 дней
        posts_24h = 0
        posts_7d = 0
        try:
            from modules.vk_wall.database_wall import get_post_counts
            counts = await get_post_counts()
            posts_24h = counts.get("24h", 0)
            posts_7d = counts.get("7d", 0)
        except Exception:
            pass

        # Данные для подстановки
        replacements = {
            "uptime": stats["uptime"],
            "queue_size": str(stats.get("queue_size", 0)),
            "errors": str(stats["errors"]),
            "processed_posts": str(stats["processed_posts"]),
            "processed_streams": str(stats["processed_streams"]),
            "processed_videos": str(stats["processed_videos"]),
            "processed_assets": str(stats["processed_assets"]),
            "posts_24h": str(posts_24h),
            "posts_7d": str(posts_7d),
            "avg_processing_time": f"{stats.get('avg_processing_time', 0.0):.2f}s",
            "circuit_breakers_triggered": str(stats.get('circuit_breakers_triggered', 0)),
            "start_time": stats["start_time"],
            "emoji_info": Emojis.INFO,
            "emoji_success": Emojis.SUCCESS,
            "emoji_error": Emojis.ERROR,
            "emoji_processed": LogEmojis.PROCESSED,
            "emoji_uptime": LogEmojis.UPTIME,
            "emoji_queue": Emojis.PROCESSED,
            "emoji_start": LogEmojis.STARTUP,
            "emoji_posts": StartupEmojis.POSTS,
            "emoji_videos": Emojis.VIDEO,
            "emoji_streams": StartupEmojis.STREAMERS,
            "emoji_assets": StartupEmojis.COVER_PREVIEW,
            "emoji_status": LogEmojis.BOT_STATUS,
            "emoji_online": StatusEmojis.ONLINE,
            "emoji_offline": StatusEmojis.OFFLINE
        }

        # Кастомизация через JSON
        cfg = self.status_config.get("embed", {})
        
        def _fmt(text):
            if not isinstance(text, str): return text
            for k, v in replacements.items():
                text = text.replace(f"{{{k}}}", v)
            return text

        title = _fmt(cfg.get("title", f"{LogEmojis.INFO} Статус бота"))
        description = _fmt(cfg.get("description", ""))
        color_hex = cfg.get("color")
        if color_hex:
            color = hex_to_color_int(color_hex)
        else:
            color = parse_color_to_int(Config.EMBED_COLOR, 0x4568DC)
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=discord.utils.utcnow()
        )
        
        # Thumbnail & Author
        if cfg.get("thumbnail"):
            embed.set_thumbnail(url=resolve_asset_url(_fmt(cfg["thumbnail"])))
        
        if cfg.get("image"):
            embed.set_image(url=resolve_asset_url(_fmt(cfg["image"])))
        
        author_cfg = cfg.get("author", {})
        if author_cfg.get("name"):
            embed.set_author(
                name=_fmt(author_cfg["name"]),
                icon_url=resolve_asset_url(_fmt(author_cfg.get("icon_url", "")))
            )

        # Footer
        footer_cfg = cfg.get("footer", {})
        embed.set_footer(
            text=_fmt(footer_cfg.get("text", "VK → Discord Bot Statistics")),
            icon_url=resolve_asset_url(_fmt(footer_cfg.get("icon_url", "")))
        )

        # Fields from Config
        sections = cfg.get("sections", {})
        
        # Main Stats (Fields list)
        main_stats = sections.get("main_stats", {})
        if main_stats.get("fields"):
            for field in main_stats["fields"]:
                embed.add_field(
                    name=_fmt(field.get("name", "---")),
                    value=_fmt(field.get("value", "---")),
                    inline=field.get("inline", True)
                )
        else:
            # Fallback if no config
            embed.add_field(name=f"{EmojisFields.DURATION} Аптайм", value=stats["uptime"], inline=True)
            embed.add_field(name=f"{Emojis.PROCESSED} В очереди", value=str(stats.get("queue_size", 0)), inline=True)
            embed.add_field(name=f"{Emojis.WARNING} Ошибки", value=str(stats["errors"]), inline=True)
            embed.add_field(name=f"{Emojis.EVENT} Время запуска", value=stats["start_time"], inline=False)

        # Content Stats (Value text)
        content_stats = sections.get("content_stats", {})
        if content_stats.get("value"):
            embed.add_field(
                name=_fmt(content_stats.get("title", "Обработано")),
                value=_fmt(content_stats["value"]),
                inline=False
            )
        else:
            summary = (
                f"{StartupEmojis.POSTS} Постов всего: {stats['processed_posts']}\n"
                f"├ За последние 24ч: **{posts_24h}**\n"
                f"└ За последние 7 дней: **{posts_7d}**\n"
                f"{Emojis.TIME_REMAINING} Ср. время отправки: **{stats.get('avg_processing_time', 0.0):.2f} сек.**\n"
                f"{Emojis.PLUG} Срабатываний Circuit Breaker: **{stats.get('circuit_breakers_triggered', 0)}**\n"
                f"{Emojis.VIDEO} Видео: **{stats['processed_videos']}**\n"
                f"{LiveEmojis.STREAM_START} Стримов: **{stats['processed_streams']}**\n"
                f"{Emojis.STICKER} Ассеты: **{stats['processed_assets']}**"
            )
            embed.add_field(name="Обработано / Метрики", value=summary, inline=False)

        # Monitors Detail Embeds
        monitor_embeds = []
        app = getattr(self.bot, "app", None)
        if app:
            managers = [
                ("VK Wall", app.vk_wall_manager),
                ("VK Live", app.vk_live_manager),
                ("YouTube", getattr(app, "youtube_manager", None)),
                ("Rutube", getattr(app, "rutube_manager", None)),
                ("Twitch", app.twitch_live_manager),
                ("Kick", app.kick_live_manager),
                ("VK Assets", app.vk_asset_manager)
            ]
            for platform, manager in managers:
                if manager and hasattr(manager, "monitors"):
                    for pid, monitor in manager.monitors.items():
                        mon_embed = await self._create_monitor_embed(platform, pid, monitor)
                        monitor_embeds.append(mon_embed)

        if isinstance(target, discord.Interaction):
            if not target.response.is_done():
                await target.response.send_message(embed=embed)
            else:
                await target.followup.send(embed=embed)
            
            if monitor_embeds:
                for i in range(0, len(monitor_embeds), 5):
                    chunk = monitor_embeds[i:i+5]
                    await target.followup.send(embeds=chunk)
        else:
            await target.send(embed=embed)
            if monitor_embeds:
                for i in range(0, len(monitor_embeds), 5):
                    chunk = monitor_embeds[i:i+5]
                    await target.send(embeds=chunk)

    async def _create_monitor_embed(self, platform: str, pid: str, monitor) -> discord.Embed:
        """Создает красивый и подробный Embed для статуса конкретного монитора."""
        import time
        from modules_utils.vk_api_client import VKApiClient
        
        # Получаем данные о статусе
        status_data = {}
        if hasattr(monitor, "get_status"):
            try:
                status_data = monitor.get_status()
            except Exception:
                pass

        # Идентификация источника
        config = getattr(monitor, "config", getattr(monitor, "group_config", {}))
        name = status_data.get("group_name") or config.get("name") or pid
        
        # Определение статуса и circuit breaker
        is_running = status_data.get("running", getattr(monitor, "is_running", False))
        is_circuit_open = status_data.get("circuit_open", False)
        
        if not is_running:
            color = 0xFF4F4F  # Красный - остановлен
            status_text = f"{Emojis.CLOSED} Отключен"
        elif is_circuit_open:
            color = 0xFF9900  # Оранжевый - в режиме паузы
            status_text = f"{LogEmojis.CRITICAL} Пауза (Circuit Breaker)"
        else:
            color = 0x2ECC71  # Зеленый - в сети
            status_text = f"{Emojis.OPEN} Активен"

        embed = discord.Embed(
            title=f"{platform}: {name}",
            color=color,
            timestamp=discord.utils.utcnow()
        )
        
        # Поля основной информации
        embed.add_field(name="ID источника", value=f"`{pid}`", inline=True)
        if status_data.get("group_id"):
            embed.add_field(name="ID группы/канала", value=f"`{status_data['group_id']}`", inline=True)
        embed.add_field(name="Текущий статус", value=status_text, inline=True)

        # Статистика элементов
        proc_count = status_data.get("processed_count", getattr(monitor, "processed_count", 0))
        err_count = status_data.get("error_count", getattr(monitor, "error_count", 0))
        embed.add_field(name="Обработано", value=f"{Emojis.SUCCESS} {proc_count}", inline=True)
        embed.add_field(name="Ошибки (всего)", value=f"{Emojis.FAILURE} {err_count}", inline=True)
        
        # Ошибки подряд (consecutive errors)
        consecutive_errs = status_data.get("consecutive_errors", getattr(monitor, "_consecutive_errors", 0))
        embed.add_field(name="Ошибок подряд", value=f"{Emojis.WARNING} {consecutive_errs}" if consecutive_errs > 0 else f"0 {Emojis.SUCCESS}", inline=True)

        # Тайминги проверок
        last_check = status_data.get("last_check", getattr(monitor, "last_check_time", None))
        last_success = status_data.get("last_success", getattr(monitor, "last_success_time", None))
        
        def fmt_time(t):
            if not t: return "Никогда"
            if isinstance(t, datetime):
                return f"<t:{int(t.timestamp())}:R>"
            return str(t)

        embed.add_field(name="Последняя проверка", value=fmt_time(last_check), inline=True)
        embed.add_field(name="Последний успех", value=fmt_time(last_success), inline=True)

        # Адаптивный интервал (Interval Multiplier)
        mult = status_data.get("interval_multiplier", getattr(monitor, "_interval_multiplier", 1.0))
        if mult != 1.0:
            base_interval = config.get("check_interval", 300)
            effective_interval = int(base_interval * mult)
            embed.add_field(
                name="Адаптивный интервал", 
                value=f"{Emojis.SEARCH} `×{mult:.1f}` ({effective_interval}с вместо {base_interval}с)", 
                inline=False
            )
        else:
            embed.add_field(name="Адаптивный интервал", value=f"{Emojis.SEARCH} `×1.0` (Стандартный)", inline=True)

        # Сообщение о последней ошибке, если есть
        last_err = status_data.get("last_error_msg", getattr(monitor, "last_error_msg", None))
        if last_err:
            embed.add_field(name="Последняя ошибка", value=f"```\n{last_err[:900]}\n```", inline=False)
            
        # Аватар
        avatar_url = None
        group_id = status_data.get("group_id") or config.get("id")
        if group_id and platform == "VK Wall":
            try:
                avatar_url = await VKApiClient.get_group_avatar(group_id, token=config.get("vk_token"))
            except Exception:
                pass

        if not avatar_url:
            avatar_url = config.get("avatar_url") or config.get("embed_author_icon_url")

        if avatar_url:
            embed.set_thumbnail(url=str(avatar_url))

        embed.set_footer(text=f"Мониторинг {platform} • Nexus Bridge")
        return embed

    def _get_monitors_table(self, app, config: dict) -> str:
        all_monitors = []
        managers = [
            app.vk_wall_manager, app.vk_live_manager, 
            getattr(app, "youtube_manager", None),
            getattr(app, "rutube_manager", None),
            app.twitch_live_manager,
            app.kick_live_manager, app.vk_asset_manager
        ]
        
        for manager in managers:
            if manager and hasattr(manager, "monitors"):
                for pid, monitor in manager.monitors.items():
                    if hasattr(monitor, "get_status"):
                        all_monitors.append(monitor.get_status())
                    else:
                        all_monitors.append({
                            'group_name': getattr(monitor, 'config', {}).get('name', 'Unknown'),
                            'last_success': getattr(monitor, 'last_success_time', None),
                            'processed_count': getattr(monitor, 'processed_count', 0),
                            'running': getattr(monitor, 'is_running', False)
                        })

        if not all_monitors:
            return ""

        header = config.get("header", "Группа/Канал       | Успех    | Пост | Статус\n" + "-"*50)
        row_format = config.get("row_format", "{name:<18} | {last_success:<8} | {processed:<4} | {status_icon}")
        
        table = header + "\n"
        for m in all_monitors:
            row_data = {
                "name": m.get('group_name', 'Unknown')[:18],
                "last_success": m['last_success'].strftime("%H:%M:%S") if m.get('last_success') else "Никогда",
                "processed": str(m.get('processed_count', 0)),
                "status_icon": Emojis.ONLINE if m.get('running') else Emojis.OFFLINE
            }
            try:
                table += row_format.format(**row_data) + "\n"
            except KeyError:
                table += f"{row_data['name']:<18} | {row_data['last_success']:<8} | {row_data['processed']:<4} | {row_data['status_icon']}\n"
        
        return table.strip()

    @commands.command(name="rules", aliases=["правила", "role_rules"])
    async def rules_cmd(self, ctx: commands.Context):
        """Префиксная команда вывода правил связанных ролей."""
        app = getattr(self.bot, "app", None)
        if not app or not app.role_dependency_module:
            await ctx.send(f"{Emojis.FAILURE} Модуль зависимостей ролей не активен.")
            return

        module = app.role_dependency_module
        if not module.dependencies:
            await ctx.send(f"{Emojis.INFO} Правила не настроены.")
            return

        embed = discord.Embed(
            title=f"{Emojis.RULES if hasattr(Emojis, 'RULES') else Emojis.DOC} Правила связанных ролей",
            description="Ниже перечислены автоматические действия при изменении ролей участников.",
            color=parse_color_to_int(Config.EMBED_COLOR, 0x2ecc71),
            timestamp=discord.utils.utcnow()
        )
        
        rules_text = ""
        for i, dep in enumerate(module.dependencies, 1):
            rule_str = module.format_rule(dep, ctx.guild)
            comment = dep.get("comment", "")
            field_val = f"**{rule_str}**"
            if comment:
                 field_val += f"\n*Примечание: {comment}*"
            
            if len(module.dependencies) <= 25:
                embed.add_field(name=f"Правило #{i}", value=field_val, inline=False)
            else:
                rules_text += f"**{i}.** {field_val}\n\n"

        if rules_text:
            embed.description += f"\n\n{rules_text}"

        embed.set_footer(text="Система автоматических ролей", icon_url=self.bot.user.display_avatar.url)
        await ctx.send(embed=embed)

    @app_commands.command(name="rules", description="Показать активные правила связанных ролей")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
    async def rules(self, interaction: discord.Interaction):
        """Показывает правила RoleDependencyModule в виде эмбеда."""
        app = getattr(self.bot, "app", None)
        if not app or not app.role_dependency_module:
            await interaction.response.send_message(f"{Emojis.FAILURE} Модуль зависимостей ролей не активен.", ephemeral=True)
            return

        module = app.role_dependency_module
        if not module.dependencies:
            await interaction.response.send_message(f"{Emojis.INFO} Правила не настроены.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{Emojis.RULES if hasattr(Emojis, 'RULES') else Emojis.DOC} Правила связанных ролей",
            description="Ниже перечислены автоматические действия при изменении ролей участников.",
            color=parse_color_to_int(Config.EMBED_COLOR, 0x2ecc71),
            timestamp=discord.utils.utcnow()
        )
        
        rules_text = ""
        for i, dep in enumerate(module.dependencies, 1):
            rule_str = module.format_rule(dep, interaction.guild)
            comment = dep.get("comment", "")
            field_val = f"**{rule_str}**"
            if comment:
                 field_val += f"\n*Примечание: {comment}*"
            
            if len(module.dependencies) <= 25:
                embed.add_field(name=f"Правило #{i}", value=field_val, inline=False)
            else:
                rules_text += f"**{i}.** {field_val}\n\n"

        if rules_text:
            embed.description += f"\n\n{rules_text}"

        embed.set_footer(text="Система автоматических ролей", icon_url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="activity_rules", aliases=["правила_активности", "активность_правила"])
    async def activity_rules_cmd(self, ctx: commands.Context):
        """Префиксная команда отображения правил активности."""
        app = getattr(self.bot, "app", None)
        if not app or not app.user_activity_module:
            await ctx.send(f"{Emojis.FAILURE} Модуль активности не активен.")
            return

        module = app.user_activity_module
        guild = ctx.guild
        if not guild:
            await ctx.send(f"{Emojis.FAILURE} Эта команда может быть использована только на сервере.")
            return

        active_role_mention = f"<@&{module.active_role_id}>" if module.active_role_id else "*Не настроена*"
        afk_role_mention = f"<@&{module.afk_role_id}>" if module.afk_role_id else "*Не настроена*"
        required_role_mention = f"<@&{module.required_role_id}>" if module.required_role_id else "*Отсутствует (отслеживаются все)*"
        
        ignore_roles_mentions = []
        if module.ignore_role_ids:
            for rid in module.ignore_role_ids:
                ignore_roles_mentions.append(f"<@&{rid}>")
        ignore_roles_str = ", ".join(ignore_roles_mentions) if ignore_roles_mentions else "*Нет*"

        log_channel_mention = f"<#{module.channel_id}>" if module.channel_id else "*Выключено*"
        manage_roles_status = f"{Emojis.ACTIVE} Включено автоматически" if getattr(Config, "USER_ACTIVITY_MANAGE_ROLES", True) else f"{Emojis.CLOSED} Выключено"
        afk_days = getattr(Config, "AFK_DAYS_THRESHOLD", 180)

        embed = discord.Embed(
            title=f"{Emojis.STATUS} Правила и настройки активности пользователей",
            description="Текущие конфигурации автоматического отслеживания статусов, активности и управления ролями на сервере.",
            color=parse_color_to_int(Config.EMBED_COLOR, 0x4568DC),
            timestamp=discord.utils.utcnow()
        )
        
        thumbnail_url = guild.icon.url if guild.icon else self.bot.user.display_avatar.url
        embed.set_thumbnail(url=thumbnail_url)
        
        embed.add_field(
            name=f"{Emojis.GEAR} Автоматическое управление ролями",
            value=f"Статус: **{manage_roles_status}**",
            inline=False
        )
        embed.add_field(
            name=f"{Emojis.TAG} Назначаемые роли активности",
            value=(
                f"{Emojis.ACTIVE} **Роль активности**: {active_role_mention}\n"
                f"{Emojis.AFK} **Роль AFK (неактивен)**: {afk_role_mention}"
            ),
            inline=False
        )
        embed.add_field(
            name=f"{Emojis.COOLDOWN} Порог неактивности (AFK)",
            value=f"Пользователь переводится в режим AFK, если находится в офлайне более **{afk_days}** дней.",
            inline=False
        )
        embed.add_field(
            name=f"{Emojis.SHIELD} Обязательная роль",
            value=required_role_mention,
            inline=True
        )
        embed.add_field(
            name=f"{Emojis.MUTED} Игнорируемые роли",
            value=ignore_roles_str,
            inline=True
        )
        embed.add_field(
            name=f"{Emojis.MAIL} Канал для логов статусов",
            value=log_channel_mention,
            inline=False
        )

        logic_description = (
            "1. При **любом обнаружении активности в сети** (онлайн, смена кастомного "
            "статуса или установка статуса голосового канала) у пользователя автоматически снимается роль AFK и "
            "выдается роль активности.\n"
            "2. Фоновая проверка раз в 12 часов проверяет пользователей в офлайне и переводит их в "
            f"AFK, если отсутствие превышает срок в **{afk_days} дней**.\n"
            "3. Участники с игнорируемыми ролями полностью исключаются из системы.\n"
            "4. Если установлена обязательная роль, только владельцы этой роли будут отслеживаться, у всех остальных роли активности будут автоматически сняты."
        )
        embed.add_field(
            name=f"{Emojis.DOC} Алгоритм работы правил",
            value=logic_description,
            inline=False
        )

        embed.set_footer(
            text="Мониторинг активности участников",
            icon_url=self.bot.user.display_avatar.url
        )
        await ctx.send(embed=embed)

    @app_commands.command(name="activity_rules", description="Показать правила и настройки автоматического отслеживания активности")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
    async def activity_rules(self, interaction: discord.Interaction):
        """Показывает правила и настройки UserActivityModule в виде красивого эмбеда."""
        app = getattr(self.bot, "app", None)
        if not app or not app.user_activity_module:
            await interaction.response.send_message(f"{Emojis.FAILURE} Модуль активности не активен.", ephemeral=True)
            return

        module = app.user_activity_module
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message(f"{Emojis.FAILURE} Эта команда может быть использована только на сервере.", ephemeral=True)
            return

        active_role_mention = f"<@&{module.active_role_id}>" if module.active_role_id else "*Не настроена*"
        afk_role_mention = f"<@&{module.afk_role_id}>" if module.afk_role_id else "*Не настроена*"
        required_role_mention = f"<@&{module.required_role_id}>" if module.required_role_id else "*Отсутствует (отслеживаются все)*"
        
        ignore_roles_mentions = []
        if module.ignore_role_ids:
            for rid in module.ignore_role_ids:
                ignore_roles_mentions.append(f"<@&{rid}>")
        ignore_roles_str = ", ".join(ignore_roles_mentions) if ignore_roles_mentions else "*Нет*"

        log_channel_mention = f"<#{module.channel_id}>" if module.channel_id else "*Выключено*"
        manage_roles_status = f"{Emojis.ACTIVE} Включено автоматически" if getattr(Config, "USER_ACTIVITY_MANAGE_ROLES", True) else f"{Emojis.CLOSED} Выключено"
        afk_days = getattr(Config, "AFK_DAYS_THRESHOLD", 180)

        embed = discord.Embed(
            title=f"{Emojis.STATUS} Правила и настройки активности пользователей",
            description="Текущие конфигурации автоматического отслеживания статусов, активности и управления ролями на сервере.",
            color=parse_color_to_int(Config.EMBED_COLOR, 0x4568DC),
            timestamp=discord.utils.utcnow()
        )
        
        thumbnail_url = guild.icon.url if guild.icon else self.bot.user.display_avatar.url
        embed.set_thumbnail(url=thumbnail_url)
        
        embed.add_field(
            name=f"{Emojis.GEAR} Автоматическое управление ролями",
            value=f"Статус: **{manage_roles_status}**",
            inline=False
        )
        
        embed.add_field(
            name=f"{Emojis.TAG} Назначаемые роли активности",
            value=(
                f"{Emojis.ACTIVE} **Роль активности**: {active_role_mention}\n"
                f"{Emojis.AFK} **Роль AFK (неактивен)**: {afk_role_mention}"
            ),
            inline=False
        )
        
        embed.add_field(
            name=f"{Emojis.COOLDOWN} Порог неактивности (AFK)",
            value=f"Пользователь переводится в режим AFK, если находится в офлайне более **{afk_days}** дней.",
            inline=False
        )
        
        embed.add_field(
            name=f"{Emojis.SHIELD} Обязательная роль",
            value=required_role_mention,
            inline=True
        )
        
        embed.add_field(
            name=f"{Emojis.MUTED} Игнорируемые роли",
            value=ignore_roles_str,
            inline=True
        )
        
        embed.add_field(
            name=f"{Emojis.MAIL} Канал для логов статусов",
            value=log_channel_mention,
            inline=False
        )

        logic_description = (
            "1. При **любом обнаружении активности в сети** (онлайн, смена кастомного "
            "статуса или установка статуса голосового канала) у пользователя автоматически снимается роль AFK и "
            "выдается роль активности.\n"
            "2. Фоновая проверка раз в 12 часов проверяет пользователей в офлайне и переводит их в "
            f"AFK, если отсутствие превышает срок в **{afk_days} дней**.\n"
            "3. Участники с игнорируемыми ролями полностью исключаются из системы.\n"
            "4. Если установлена обязательная роль, только владельцы этой роли будут отслеживаться, у всех остальных роли активности будут автоматически сняты."
        )
        embed.add_field(
            name=f"{Emojis.DOC} Алгоритм работы правил",
            value=logic_description,
            inline=False
        )

        embed.set_footer(
            text="Мониторинг активности участников",
            icon_url=self.bot.user.display_avatar.url
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="activity", aliases=["активность", "my_activity"])
    async def activity_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Префиксная команда проверки активности участника."""
        target_member = member or ctx.author
        app = getattr(self.bot, "app", None)
        if not app or not app.user_activity_module:
            await ctx.send(f"{Emojis.FAILURE} Модуль активности не активен.")
            return

        last_seen_ts = await app.user_activity_module.get_user_activity_info(target_member.id)
        
        embed = discord.Embed(
            title=f"{Emojis.STATUS} Активность: {target_member.display_name}",
            color=target_member.color if target_member.color.value != 0 else parse_color_to_int(Config.EMBED_COLOR, 0x00FF00),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=target_member.display_avatar.url)
        
        status_emoji = StatusEmojis.ONLINE if target_member.status != discord.Status.offline else StatusEmojis.OFFLINE
        embed.add_field(name="Текущий статус", value=f"{status_emoji} {str(target_member.status).title()}", inline=True)
        
        if last_seen_ts:
            dt = datetime.fromtimestamp(last_seen_ts)
            rel_time = discord.utils.format_dt(dt, style="R")
            abs_time = discord.utils.format_dt(dt, style="f")
            embed.add_field(name="Последняя онлайн-активность", value=f"{abs_time} ({rel_time})", inline=False)
        else:
            embed.add_field(name="Последняя онлайн-активность", value="Нет данных в базе", inline=False)

        roles_val = "Нет специальных ролей"
        special_roles = []
        if app.user_activity_module.active_role_id:
            role = target_member.guild.get_role(app.user_activity_module.active_role_id)
            if role and role in target_member.roles: special_roles.append(f"{Emojis.SUCCESS} {role.mention}")
        if app.user_activity_module.afk_role_id:
            role = target_member.guild.get_role(app.user_activity_module.afk_role_id)
            if role and role in target_member.roles: special_roles.append(f"{Emojis.WARNING} {role.mention}")

        if special_roles:
            roles_val = "\n".join(special_roles)

        embed.add_field(name="Статус ролей", value=roles_val, inline=False)
        await ctx.send(embed=embed)

    @app_commands.command(name="activity", description="Показать информацию об активности участника")
    @app_commands.describe(member="Участник для проверки")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
    async def activity(self, interaction: discord.Interaction, member: discord.Member = None):
        """Слэш-команда проверки активности."""
        member = member or interaction.user
        
        app = getattr(self.bot, "app", None)
        if not app or not app.user_activity_module:
            await interaction.response.send_message(f"{Emojis.FAILURE} Модуль активности не активен.", ephemeral=True)
            return

        await interaction.response.defer()
        last_seen_ts = await app.user_activity_module.get_user_activity_info(member.id)
        
        embed = discord.Embed(
            title=f"{Emojis.STATUS} Активность: {member.display_name}",
            color=member.color if member.color.value != 0 else parse_color_to_int(Config.EMBED_COLOR, 0x00FF00),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        status_emoji = StatusEmojis.ONLINE if member.status != discord.Status.offline else StatusEmojis.OFFLINE
        embed.add_field(name="Текущий статус", value=f"{status_emoji} {str(member.status).title()}", inline=True)
        
        if last_seen_ts:
            dt = datetime.fromtimestamp(last_seen_ts)
            rel_time = discord.utils.format_dt(dt, style="R")
            abs_time = discord.utils.format_dt(dt, style="f")
            embed.add_field(name="Последняя онлайн-активность", value=f"{abs_time} ({rel_time})", inline=False)
        else:
            embed.add_field(name="Последняя онлайн-активность", value="Нет данных в базе", inline=False)

        roles_val = "Нет специальных ролей"
        special_roles = []
        if app.user_activity_module.active_role_id:
            role = member.guild.get_role(app.user_activity_module.active_role_id)
            if role and role in member.roles: special_roles.append(f"{Emojis.SUCCESS} {role.mention}")
        if app.user_activity_module.afk_role_id:
            role = member.guild.get_role(app.user_activity_module.afk_role_id)
            if role and role in member.roles: special_roles.append(f"{Emojis.WARNING} {role.mention}")

        if special_roles:
            roles_val = "\n".join(special_roles)
        
        embed.add_field(name="Статус ролей", value=roles_val, inline=False)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="check_groups", description="Принудительно проверить все группы VK на новые посты")
    async def check_groups_slash(self, interaction: discord.Interaction):
        """Слэш-команда для ручной проверки всех VK групп."""
        is_owner = await self.bot.is_owner(interaction.user)
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        if not is_owner and not is_admin:
            await interaction.response.send_message(f"{Emojis.FAILURE} У вас нет прав для выполнения этой команды.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        app = getattr(self.bot, "app", None)
        if not app or not getattr(app, "vk_wall_manager", None):
            await interaction.followup.send(f"{Emojis.FAILURE} Менеджер VK групп неактивен.")
            return

        monitors = app.vk_wall_manager.monitors
        if not monitors:
            await interaction.followup.send(f"{Emojis.WARNING} Нет активных мониторов групп VK.")
            return

        await interaction.followup.send(f"{Emojis.TIME_REMAINING} Запущена принудительная проверка всех групп VK ({len(monitors)} шт.)...")
        
        checked_names = []
        for pid, monitor in list(monitors.items()):
            name = monitor.group_config.get("name", pid)
            try:
                await monitor.check_group()
                checked_names.append(f"{Emojis.SUCCESS} {name}")
            except Exception as e:
                checked_names.append(f"{Emojis.FAILURE} {name}: {e}")
        
        results_str = "\n".join(checked_names)
        await interaction.followup.send(f"{Emojis.STATUS} Результаты проверки групп:\n{results_str}")

    @commands.command(name="check_groups", aliases=["checkgroups", "checkall"])
    @commands.is_owner()
    async def check_groups_prefix(self, ctx):
        """Принудительно проверить все группы VK на новые посты (префиксная версия)."""
        app = getattr(self.bot, "app", None)
        if not app or not getattr(app, "vk_wall_manager", None):
            await ctx.send(f"{Emojis.FAILURE} Менеджер VK групп неактивен.")
            return

        monitors = app.vk_wall_manager.monitors
        if not monitors:
            await ctx.send(f"{Emojis.WARNING} Нет активных мониторов групп VK.")
            return

        msg = await ctx.send(f"{Emojis.TIME_REMAINING} Запущена принудительная проверка всех групп VK ({len(monitors)} шт.)...")
        
        checked_names = []
        for pid, monitor in list(monitors.items()):
            name = monitor.group_config.get("name", pid)
            try:
                await monitor.check_group()
                checked_names.append(f"{Emojis.SUCCESS} {name}")
            except Exception as e:
                checked_names.append(f"{Emojis.FAILURE} {name}: {e}")
        
        results_str = "\n".join(checked_names)
        await msg.edit(content=f"{Emojis.STATUS} Результаты проверки групп:\n{results_str}")

    @app_commands.command(name="sync_activity", description="Принудительно синхронизировать роли активности (Активный/AFK) участников")
    async def sync_activity_slash(self, interaction: discord.Interaction):
        """Слэш-команда ручной синхронизации активности участников."""
        is_owner = await self.bot.is_owner(interaction.user)
        is_admin = interaction.user.guild_permissions.administrator if hasattr(interaction.user, "guild_permissions") else False
        if not (is_owner or is_admin):
            await interaction.response.send_message(f"{Emojis.FAILURE} Эта команда доступна только администраторам серверов и владельцу бота.", ephemeral=True)
            return

        app = getattr(self.bot, "app", None)
        module = getattr(app, "user_activity_module", None)
        if not module or not module.is_running:
            await interaction.response.send_message(f"{Emojis.FAILURE} Модуль активности не активен.", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message(f"{Emojis.FAILURE} Эта команда может быть использована только на сервере.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        try:
            stats = await module.sync_all_members_activity(guild)
            
            embed = discord.Embed(
                title=f"{Emojis.SYNC} Результаты синхронизации ролей активности",
                description="Синхронизация завершена успешно. Обновлены статусы и роли.",
                color=parse_color_to_int(Config.EMBED_COLOR, 0x00FF00),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Всего участников проверено", value=f"{Emojis.USERS} **{stats['total_checked']}**", inline=False)
            embed.add_field(name="Выдано ролей «Активный»", value=f"{Emojis.ACTIVE} **{stats['active_assigned']}**", inline=True)
            embed.add_field(name="Выдано ролей «AFK»", value=f"{Emojis.AFK} **{stats['afk_assigned']}**", inline=True)
            embed.add_field(name="Снято ролей (нет обязательной)", value=f"{Emojis.SHIELD} **{stats['roles_removed_no_req']}**", inline=True)
            embed.add_field(name="Пропущено (игнорируемые ролями)", value=f"{Emojis.MUTED} **{stats['ignored']}**", inline=True)
            embed.add_field(name="Без изменений", value=f"{Emojis.DOC} **{stats['no_change']}**", inline=True)
            embed.add_field(name="Ошибок при смене ролей", value=f"{Emojis.FAILURE} **{stats['errors']}**", inline=True)
            
            embed.set_footer(text="Синхронизация по требованию", icon_url=self.bot.user.display_avatar.url)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"{Emojis.FAILURE} Ошибка в процессе синхронизации: `{e}`")

    @commands.command(name="sync_activity", aliases=["syncactivity", "sync_active"])
    @commands.has_permissions(administrator=True)
    async def sync_activity_prefix(self, ctx):
        """Принудительно синхронизировать роли активности (Активный/AFK) участников (префиксная версия)."""
        app = getattr(self.bot, "app", None)
        module = getattr(app, "user_activity_module", None)
        if not module or not module.is_running:
            await ctx.send(f"{Emojis.FAILURE} Модуль активности не активен.")
            return

        guild = ctx.guild
        if not guild:
            await ctx.send(f"{Emojis.FAILURE} Эта команда может быть использована только на сервере.")
            return

        msg = await ctx.send(f"{Emojis.COOLDOWN} Запущен процесс полной синхронизации ролей по активности пользователей...")
        try:
            stats = await module.sync_all_members_activity(guild)
            
            embed = discord.Embed(
                title=f"{Emojis.SYNC} Результаты синхронизации ролей активности",
                description="Синхронизация завершена успешно. Обновлены статусы и роли.",
                color=parse_color_to_int(Config.EMBED_COLOR, 0x00FF00),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Всего участников проверено", value=f"{Emojis.USERS} **{stats['total_checked']}**", inline=False)
            embed.add_field(name="Выдано ролей «Активный»", value=f"{Emojis.ACTIVE} **{stats['active_assigned']}**", inline=True)
            embed.add_field(name="Выдано ролей «AFK»", value=f"{Emojis.AFK} **{stats['afk_assigned']}**", inline=True)
            embed.add_field(name="Снято ролей (нет обязательной)", value=f"{Emojis.SHIELD} **{stats['roles_removed_no_req']}**", inline=True)
            embed.add_field(name="Пропущено (игнорируемые ролями)", value=f"{Emojis.MUTED} **{stats['ignored']}**", inline=True)
            embed.add_field(name="Без изменений", value=f"{Emojis.DOC} **{stats['no_change']}**", inline=True)
            embed.add_field(name="Ошибок при смене ролей", value=f"{Emojis.FAILURE} **{stats['errors']}**", inline=True)
            
            embed.set_footer(text="Синхронизация по требованию", icon_url=self.bot.user.display_avatar.url)
            await msg.edit(content=None, embed=embed)
        except Exception as e:
            await msg.edit(content=f"{Emojis.FAILURE} Ошибка в процессе синхронизации: `{e}`")

    @commands.command(name="reload_roles", aliases=["обновить_роли", "перезагрузить_роли"])
    async def reload_roles_cmd(self, ctx: commands.Context):
        """Префиксная команда перезагрузки файла role_dependencies.json."""
        is_owner = await self.bot.is_owner(ctx.author)
        if not is_owner:
            await ctx.send(f"{Emojis.FAILURE} Эта команда только для владельца бота.")
            return

        app = getattr(self.bot, "app", None)
        rdm = getattr(app, "role_dependency_module", None) if app else None
        if not rdm or not getattr(rdm, "running", False):
            await ctx.send(f"{Emojis.FAILURE} Модуль зависимостей ролей не активен.")
            return

        await rdm.reload_config()
        await ctx.send(f"{Emojis.SUCCESS} `role_dependencies.json` успешно перезагружен.")

    @app_commands.command(name="reload_roles", description="Принудительно перезагрузить role_dependencies.json (только для владельца)")
    async def reload_roles_slash(self, interaction: discord.Interaction):
        """Слэш-команда для ручной перезагрузки конфига зависимостей ролей."""
        is_owner = await self.bot.is_owner(interaction.user)
        if not is_owner:
            await interaction.response.send_message(f"{Emojis.FAILURE} Эта команда только для владельца бота.", ephemeral=True)
            return

        app = getattr(self.bot, "app", None)
        rdm = getattr(app, "role_dependency_module", None) if app else None
        if not rdm or not getattr(rdm, "running", False):
            await interaction.response.send_message(f"{Emojis.FAILURE} Модуль зависимостей ролей не активен.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await rdm.reload_config()
        await interaction.followup.send(f"{Emojis.SUCCESS} `role_dependencies.json` успешно перезагружен.")

    @app_commands.command(name="vk_groups_info", description="Показать информацию о подключении и токенах для всех активных групп VK")
    async def vk_groups_info_slash(self, interaction: discord.Interaction):
        """Слэш-команда для вывода информации по всем группам VK."""
        await interaction.response.defer(ephemeral=False)
        
        app = getattr(self.bot, "app", None)
        if not app or not getattr(app, "vk_wall_manager", None):
            await interaction.followup.send(f"{Emojis.FAILURE} Менеджер VK групп неактивен.")
            return

        monitors = app.vk_wall_manager.monitors
        if not monitors:
            await interaction.followup.send(f"{Emojis.WARNING} Нет активных мониторов групп VK.")
            return

        from modules_utils.helpers import get_vk_token_description
        from settings.config import Config
        for pid, monitor in list(monitors.items()):
            local_tok = monitor.group_config.get("vk_token")
            if local_tok:
                has_local = f"Да ({get_vk_token_description(local_tok)})"
            else:
                has_local = f"Нет, используется общий токен: {get_vk_token_description(Config.VK_TOKEN)}"
                
            real_method = monitor.real_tracking_method or monitor.group_config.get("tracking_method", "polling")
            last_token = monitor.last_used_token_type or "неизвестно"
            
            # Добавим тип токена
            active_tok = local_tok if local_tok else Config.VK_TOKEN
            desc_str = get_vk_token_description(active_tok) if active_tok else "нет"
            
            auth_errors = getattr(monitor, 'token_auth_error_count', 0)
            auth_status = f"**{auth_errors}** {Emojis.WARNING}" if auth_errors > 0 else f"**{auth_errors}** {Emojis.SUCCESS}"
            last_error = getattr(monitor, 'last_error_msg', None)

            lines = [
                f"{Emojis.INFO} **Группа: {monitor.group_config.get('name', pid)}**",
                f"• Реальный режим мониторинга: **{real_method.upper()}**",
                f"• Локальный токен в настройках: **{has_local}**",
                f"• Детали активного токена: **{desc_str}**",
                f"• Ошибок авторизации токена (с запуска): {auth_status}",
            ]
            if last_error:
                lines.append(f"• Последняя ошибка: `{last_error}`")
            message = "\n".join(lines)
            await interaction.channel.send(message)
            
        await interaction.followup.send(f"{Emojis.SUCCESS} Информация по всем группам успешно отправлена.")

    @commands.command(name="vk_groups_info", aliases=["vkinfo", "vkgroups"])
    @commands.is_owner()
    async def vk_groups_info_prefix(self, ctx):
        """Показать информацию о подключении и токенах для всех активных групп VK (префиксная версия)."""
        app = getattr(self.bot, "app", None)
        if not app or not getattr(app, "vk_wall_manager", None):
            await ctx.send(f"{Emojis.FAILURE} Менеджер VK групп неактивен.")
            return

        monitors = app.vk_wall_manager.monitors
        if not monitors:
            await ctx.send(f"{Emojis.WARNING} Нет активных мониторов групп VK.")
            return

        from modules_utils.helpers import get_vk_token_description
        from settings.config import Config
        for pid, monitor in list(monitors.items()):
            local_tok = monitor.group_config.get("vk_token")
            if local_tok:
                has_local = f"Да ({get_vk_token_description(local_tok)})"
            else:
                has_local = f"Нет, используется общий токен: {get_vk_token_description(Config.VK_TOKEN)}"
                
            real_method = monitor.real_tracking_method or monitor.group_config.get("tracking_method", "polling")
            last_token = monitor.last_used_token_type or "неизвестно"
            
            active_tok = local_tok if local_tok else Config.VK_TOKEN
            desc_str = get_vk_token_description(active_tok) if active_tok else "нет"
            
            last_error = getattr(monitor, 'last_error_msg', None)

            lines = [
                f"ℹ️ **Группа: {monitor.group_config.get('name', pid)}**",
                f"• Реальный режим мониторинга: **{real_method.upper()}**",
                f"• Локальный токен в настройках: **{has_local}**",
                f"• Детали активного токена: **{desc_str}**",
            ]
            if last_error:
                lines.append(f"• Последняя ошибка: `{last_error}`")
            await ctx.send("\n".join(lines))

    @app_commands.command(name="set_status", description="Установить сетевой статус бота (только для владельца)")
    @app_commands.choices(status=[
        app_commands.Choice(name="В сети (Online)", value="online"),
        app_commands.Choice(name="Неактивен (Idle)", value="idle"),
        app_commands.Choice(name="Не беспокоить (Do Not Disturb)", value="dnd"),
        app_commands.Choice(name="Невидимка (Invisible/Offline)", value="invisible")
    ])
    async def set_status_slash(self, interaction: discord.Interaction, status: app_commands.Choice[str]):
        is_owner = await self.bot.is_owner(interaction.user)
        if not is_owner:
            await interaction.response.send_message(f"{Emojis.FAILURE} Эта команда доступна только владельцу бота.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            from modules_utils.presence_manager import PresenceManager
            new_status = await PresenceManager.update_status(self.bot, status.value)
            await interaction.followup.send(f"{Emojis.SUCCESS} Сетевой статус бота обновлен на: **{new_status.upper()}**")
        except Exception as e:
            await interaction.followup.send(f"{Emojis.FAILURE} Ошибка обновления статуса: `{e}`")

    @commands.command(name="set_status", aliases=["botstatus", "statusset"])
    @commands.is_owner()
    async def set_status_prefix(self, ctx, *, status: str):
        """Установить сетевой статус бота (online, idle, dnd, invisible)."""
        try:
            from modules_utils.presence_manager import PresenceManager
            new_status = await PresenceManager.update_status(self.bot, status)
            await ctx.send(f"{Emojis.SUCCESS} Сетевой статус бота обновлен на: **{new_status.upper()}**")
        except Exception as e:
            await ctx.send(f"{Emojis.FAILURE} Ошибка обновления статуса: `{e}`")

    @app_commands.command(name="set_activity", description="Установить активность / кастомный статус бота (только для владельца)")
    @app_commands.choices(type=[
        app_commands.Choice(name="Кастомный статус (Custom status)", value="custom"),
        app_commands.Choice(name="Играет в (Playing)", value="playing"),
        app_commands.Choice(name="Стримит (Streaming)", value="streaming"),
        app_commands.Choice(name="Слушает (Listening to)", value="listening"),
        app_commands.Choice(name="Смотрит (Watching)", value="watching"),
        app_commands.Choice(name="Соревнуется в (Competing in)", value="competing"),
        app_commands.Choice(name="Удалить статус (Remove activity)", value="none")
    ])
    async def set_activity_slash(
        self, 
        interaction: discord.Interaction, 
        type: app_commands.Choice[str], 
        text: str = "", 
        streaming_url: str = None
    ):
        is_owner = await self.bot.is_owner(interaction.user)
        if not is_owner:
            await interaction.response.send_message(f"{Emojis.FAILURE} Эта команда доступна только владельцу бота.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            from modules_utils.presence_manager import PresenceManager
            act_type, act_name = await PresenceManager.update_activity(self.bot, type.value, text, streaming_url)
            if act_type == "none":
                await interaction.followup.send(f"{Emojis.SUCCESS} Активность / кастомный статус бота успешно удален!")
            else:
                await interaction.followup.send(f"{Emojis.SUCCESS} Активность обновлена на: **{act_type.upper()}** - *{act_name}*")
        except Exception as e:
            await interaction.followup.send(f"{Emojis.FAILURE} Ошибка обновления активности: `{e}`")

    @commands.command(name="set_activity", aliases=["botactivity", "activityset"])
    @commands.is_owner()
    async def set_activity_prefix(self, ctx, type: str, *, text: str = ""):
        """Установить активность бота.
        Использование: !set_activity <playing/streaming/listening/watching/competing/custom/none> [текст]
        """
        try:
            from modules_utils.presence_manager import PresenceManager
            act_type, act_name = await PresenceManager.update_activity(self.bot, type, text)
            if act_type == "none":
                await ctx.send(f"{Emojis.SUCCESS} Активность / кастомный статус бота успешно удален!")
            else:
                await ctx.send(f"{Emojis.SUCCESS} Активность обновлена на: **{act_type.upper()}** - *{act_name}*")
        except Exception as e:
            await ctx.send(f"{Emojis.FAILURE} Ошибка обновления активности: `{e}`")

    @app_commands.command(name="set_stream", description="Установить статус стрима с кастомным URL (только для владельца)")
    @app_commands.describe(url="Ссылка на стрим (например, YouTube или Twitch)", text="Название стрима / заголовок")
    async def set_stream_slash(self, interaction: discord.Interaction, url: str, text: str):
        is_owner = await self.bot.is_owner(interaction.user)
        if not is_owner:
            await interaction.response.send_message(f"{Emojis.FAILURE} Эта команда доступна только владельцу бота.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            from modules_utils.presence_manager import PresenceManager
            act_type, act_name = await PresenceManager.update_activity(self.bot, "streaming", text, url)
            await interaction.followup.send(f"{Emojis.SUCCESS} Статус стрима успешно установлен!\n• URL: <{url}>\n• Текст: *{act_name}*")
        except Exception as e:
            await interaction.followup.send(f"{Emojis.FAILURE} Ошибка обновления стрим-статуса: `{e}`")

    @commands.command(name="set_stream", aliases=["streamset", "botstream"])
    @commands.is_owner()
    async def set_stream_prefix(self, ctx, url: str, *, text: str = "Стрим"):
        """Установить статус трансляции (стрима) с указанным URL.
        Использование: !set_stream <ссылка_на_twitch_или_youtube> <текст>
        """
        try:
            from modules_utils.presence_manager import PresenceManager
            act_type, act_name = await PresenceManager.update_activity(self.bot, "streaming", text, url)
            await ctx.send(f"{Emojis.SUCCESS} Статус стрима успешно установлен!\n• URL: <{url}>\n• Текст: *{act_name}*")
        except Exception as e:
            await ctx.send(f"{Emojis.FAILURE} Ошибка обновления стрим-статуса: `{e}`")

    @commands.command(name="boosts", aliases=["бусты", "бустеры"])
    async def boosts_cmd(self, ctx: commands.Context):
        """Префиксная команда отображения списка бустеров сервера."""
        guild = ctx.guild
        if not guild:
            await ctx.send(f"{Emojis.FAILURE} Команда доступна только на сервере.")
            return

        TIER_THRESHOLD = {1: 2, 2: 7, 3: 14}
        TIER_LABEL = {0: "Уровень 0", 1: "Уровень 1", 2: "Уровень 2", 3: "Уровень 3"}
        TIER_EMOJI = {0: Emojis.WHITE_SQUARE, 1: Emojis.BRONZE, 2: Emojis.SILVER, 3: Emojis.GOLD}
        BOOST_EMOJI = Emojis.DIAMOND

        tier = guild.premium_tier
        count = guild.premium_subscription_count or 0

        subscribers = guild.premium_subscribers
        if not subscribers and count > 0:
            try:
                await guild.chunk()
                subscribers = guild.premium_subscribers
            except Exception:
                pass

        if count == 0 and tier == 0:
            await ctx.send("Бусты не обнаружены.")
            return

        boosters: list[tuple[discord.Member, datetime]] = []
        for member in subscribers:
            if member.premium_since:
                ps = member.premium_since.astimezone(timezone.utc)
                boosters.append((member, ps))

        boosters.sort(key=lambda x: x[1])

        color = [0x4F545C, 0xF47B67, 0xF47BE8, 0x9B59B6][min(tier, 3)]
        embed = discord.Embed(
            title=f"{Emojis.ROCKET} Бусты сервера — {guild.name}",
            color=color,
            timestamp=discord.utils.utcnow()
        )

        next_tier = tier + 1
        next_threshold = TIER_THRESHOLD.get(next_tier)
        if next_threshold:
            progress = f"{count}/{next_threshold} {BOOST_EMOJI} до {TIER_LABEL[next_tier]}"
        else:
            progress = f"{count} {BOOST_EMOJI} (максимальный уровень)"

        embed.add_field(
            name=f"{TIER_EMOJI[tier]} Текущий уровень",
            value=f"**{TIER_LABEL[tier]}** — {progress}",
            inline=False
        )

        if boosters:
            lines = []
            for member, ps in boosters:
                ts = int(ps.timestamp())
                lines.append(f"• **{member.display_name}** — с <t:{ts}:D> (<t:{ts}:R>)")

            MAX_EXTRA_FIELDS = 23
            MAX_FIELD_LEN = 1000
            chunk, chunks = [], []
            for line in lines:
                if len(line) > MAX_FIELD_LEN:
                    line = line[:MAX_FIELD_LEN - 1] + "…"
                current_len = sum(len(l) + 1 for l in chunk)
                if chunk and current_len + len(line) > MAX_FIELD_LEN:
                    chunks.append("\n".join(chunk))
                    chunk = []
                chunk.append(line)
            if chunk:
                chunks.append("\n".join(chunk))

            chunks = [c for c in chunks if c.strip()]
            if len(chunks) > MAX_EXTRA_FIELDS:
                chunks = chunks[:MAX_EXTRA_FIELDS]
                chunks[-1] += "\n_...и ещё бустеры (превышен лимит отображения)_"

            for i, text in enumerate(chunks):
                if not text.strip():
                    continue
                name = f"{Emojis.DIAMOND} Активные бустеры ({len(boosters)})" if i == 0 else "\u200b"
                embed.add_field(name=name, value=text, inline=False)
        else:
            embed.add_field(
                name=f"{Emojis.DIAMOND} Бустеры",
                value="Нет активных бустеров или данные недоступны в текущем кэше.",
                inline=False
            )

        embed.set_footer(text="Все даты начала буста получены напрямую из Discord API")
        await ctx.send(embed=embed)

    @app_commands.command(name="boosts", description="Показать список активных бустеров сервера и дату начала их буста")
    @app_commands.checks.cooldown(1, 15.0, key=lambda i: (i.guild_id, i.user.id))
    async def boosts_slash(self, interaction: discord.Interaction):
        """Показывает текущий уровень буста, общее количество бустов и список бустеров с точной датой начала буста."""
        await interaction.response.defer()

        guild = interaction.guild
        if not guild:
            await interaction.followup.send(f"{Emojis.FAILURE} Команда доступна только на сервере.", ephemeral=True)
            return

        # --- Уровни и пороги бустов ---
        TIER_THRESHOLD = {1: 2, 2: 7, 3: 14}
        TIER_LABEL = {0: "Уровень 0", 1: "Уровень 1", 2: "Уровень 2", 3: "Уровень 3"}
        TIER_EMOJI = {0: Emojis.WHITE_SQUARE, 1: Emojis.BRONZE, 2: Emojis.SILVER, 3: Emojis.GOLD}
        BOOST_EMOJI = Emojis.DIAMOND

        tier = guild.premium_tier
        count = guild.premium_subscription_count or 0

        # --- Подгружаем участников если кэш пустой ---
        subscribers = guild.premium_subscribers
        if not subscribers and count > 0:
            try:
                await guild.chunk()
                subscribers = guild.premium_subscribers
            except Exception:
                pass

        # --- Ранний выход: нет бустов ---
        if count == 0 and tier == 0:
            await interaction.followup.send("Бусты не обнаружены.")
            return

        # --- Список бустеров ---
        boosters: list[tuple[discord.Member, datetime]] = []
        for member in subscribers:
            if member.premium_since:
                ps = member.premium_since.astimezone(timezone.utc)
                boosters.append((member, ps))

        # Сортируем от самых старых к самым новым
        boosters.sort(key=lambda x: x[1])

        # --- Строим embed ---
        color = [0x4F545C, 0xF47B67, 0xF47BE8, 0x9B59B6][min(tier, 3)]
        embed = discord.Embed(
            title=f"{Emojis.ROCKET} Бусты сервера — {guild.name}",
            color=color,
            timestamp=discord.utils.utcnow()
        )

        # Текущее состояние
        next_tier = tier + 1
        next_threshold = TIER_THRESHOLD.get(next_tier)
        if next_threshold:
            progress = f"{count}/{next_threshold} {BOOST_EMOJI} до {TIER_LABEL[next_tier]}"
        else:
            progress = f"{count} {BOOST_EMOJI} (максимальный уровень)"

        embed.add_field(
            name=f"{TIER_EMOJI[tier]} Текущий уровень",
            value=f"**{TIER_LABEL[tier]}** — {progress}",
            inline=False
        )

        # Список бустеров (с учётом лимита Discord: 25 полей, 6000 символов на embed)
        if boosters:
            lines = []
            for member, ps in boosters:
                ts = int(ps.timestamp())
                lines.append(f"• **{member.display_name}** — с <t:{ts}:D> (<t:{ts}:R>)")

            # Разбиваем на куски по 1000 символов, но не более 23 доп. полей
            MAX_EXTRA_FIELDS = 23
            MAX_FIELD_LEN = 1000
            chunk, chunks = [], []
            for line in lines:
                # Обрезаем строку если она сама по себе превышает лимит
                if len(line) > MAX_FIELD_LEN:
                    line = line[:MAX_FIELD_LEN - 1] + "…"
                current_len = sum(len(l) + 1 for l in chunk)
                if chunk and current_len + len(line) > MAX_FIELD_LEN:
                    chunks.append("\n".join(chunk))
                    chunk = []
                chunk.append(line)
            if chunk:
                chunks.append("\n".join(chunk))

            # Убираем пустые чанки
            chunks = [c for c in chunks if c.strip()]

            # Если чанков слишком много — обрезаем с пометкой
            if len(chunks) > MAX_EXTRA_FIELDS:
                chunks = chunks[:MAX_EXTRA_FIELDS]
                chunks[-1] += "\n_...и ещё бустеры (превышен лимит отображения)_"

            for i, text in enumerate(chunks):
                if not text.strip():
                    continue
                name = f"{Emojis.DIAMOND} Активные бустеры ({len(boosters)})" if i == 0 else "\u200b"
                embed.add_field(name=name, value=text, inline=False)
        else:
            embed.add_field(
                name=f"{Emojis.DIAMOND} Бустеры",
                value="Нет активных бустеров или данные недоступны в текущем кэше.",
                inline=False
            )

        embed.set_footer(text="Все даты начала буста получены напрямую из Discord API")

        await interaction.followup.send(embed=embed)

    def _build_sources_embed(self) -> discord.Embed:
        """Собирает и строит Embed со всеми подключенными источниками и каналами назначения."""
        embed = discord.Embed(
            title=f"{Emojis.LINK} Подключенные источники публикаций",
            description="Ниже представлен список всех активных внешних каналов, групп и системных модулей, подключенных к боту, и каналов Discord для их публикации.\n",
            color=0x2B2D31,
            timestamp=discord.utils.utcnow()
        )

        def get_channel_str(cid):
            if not cid:
                return "⚠️ *Канал не настроен*"
            cid_s = str(cid).strip()
            if not cid_s or cid_s.lower() == "none" or cid_s == "0":
                return "⚠️ *Канал не настроен*"
            return f"<#{cid_s}>"

        base_data_path = get_project_path("data", "json")

        # 1. VK Группы
        vk_lines = []
        vk_dir = os.path.join(base_data_path, "group_configs")
        if os.path.exists(vk_dir):
            for f in sorted(os.listdir(vk_dir)):
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(vk_dir, f), "r", encoding="utf-8") as fp:
                            cfg = json.load(fp)
                            name = cfg.get("name") or cfg.get("platform_id") or f
                            pid = cfg.get("platform_id") or ""
                            url = pid if pid.startswith("http") else (f"https://vk.com/{pid}" if pid else "https://vk.com")
                            cid = cfg.get("discord_channel_id")
                            vk_lines.append(f"• [{name}]({url}) ➔ {get_channel_str(cid)}")
                    except Exception:
                        pass
        if vk_lines:
            embed.add_field(
                name="🟦 VKontakte (Группы VK)",
                value="\n".join(vk_lines[:20]),
                inline=False
            )

        # 2. YouTube Каналы
        yt_lines = []
        yt_dir = os.path.join(base_data_path, "youtube_configs")
        if os.path.exists(yt_dir):
            for f in sorted(os.listdir(yt_dir)):
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(yt_dir, f), "r", encoding="utf-8") as fp:
                            cfg = json.load(fp)
                            name = cfg.get("name") or cfg.get("platform_id") or f
                            pid = cfg.get("platform_id") or ""
                            url = pid if pid.startswith("http") else (f"https://www.youtube.com/channel/{pid}" if pid else "https://youtube.com")
                            cid = cfg.get("discord_channel_id")
                            yt_lines.append(f"• [{name}]({url}) ➔ {get_channel_str(cid)}")
                    except Exception:
                        pass
        if yt_lines:
            embed.add_field(
                name="🔴 YouTube (Каналы)",
                value="\n".join(yt_lines[:20]),
                inline=False
            )

        # 3. Twitch Стримы
        tw_lines = []
        tw_dir = os.path.join(base_data_path, "twitch_configs")
        if os.path.exists(tw_dir):
            for f in sorted(os.listdir(tw_dir)):
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(tw_dir, f), "r", encoding="utf-8") as fp:
                            cfg = json.load(fp)
                            name = cfg.get("name") or cfg.get("platform_id") or f
                            pid = cfg.get("platform_id") or ""
                            url = pid if pid.startswith("http") else (f"https://www.twitch.tv/{pid}" if pid else "https://twitch.tv")
                            cid = cfg.get("discord_channel_id")
                            tw_lines.append(f"• [{name}]({url}) ➔ {get_channel_str(cid)}")
                    except Exception:
                        pass
        if tw_lines:
            embed.add_field(
                name="🟣 Twitch (Стримы)",
                value="\n".join(tw_lines[:20]),
                inline=False
            )

        # 4. Live Стримы (VK Live / Kick / Rutube)
        live_lines = []
        live_dir = os.path.join(base_data_path, "live_configs")
        if os.path.exists(live_dir):
            for f in sorted(os.listdir(live_dir)):
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(live_dir, f), "r", encoding="utf-8") as fp:
                            cfg = json.load(fp)
                            name = cfg.get("name") or cfg.get("platform_id") or f
                            pid = cfg.get("platform_id") or ""
                            mirrors = cfg.get("mirrors")
                            if mirrors and isinstance(mirrors, dict):
                                url = list(mirrors.values())[0]
                            else:
                                url = f"https://live.vkvideo.ru/{pid}" if pid else "https://live.vkvideo.ru"
                            cid = cfg.get("discord_channel_id")
                            live_lines.append(f"• [{name}]({url}) ➔ {get_channel_str(cid)}")
                    except Exception:
                        pass
        if live_lines:
            embed.add_field(
                name="🎥 Live-стримы (VK Live / Kick / Rutube)",
                value="\n".join(live_lines[:20]),
                inline=False
            )

        # 5. PDF Мониторинг & Веб-сайты
        pdf_lines = []
        pdf_dir = os.path.join(base_data_path, "pdf_configs")
        if os.path.exists(pdf_dir):
            for f in sorted(os.listdir(pdf_dir)):
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(pdf_dir, f), "r", encoding="utf-8") as fp:
                            cfg = json.load(fp)
                            name = cfg.get("name") or f
                            url = cfg.get("url") or "#"
                            cid = cfg.get("discord_channel_id")
                            pdf_lines.append(f"• [{name}]({url}) ➔ {get_channel_str(cid)}")
                    except Exception:
                        pass
        if pdf_lines:
            embed.add_field(
                name="📄 PDF Мониторинг & Веб-сайты",
                value="\n".join(pdf_lines[:20]),
                inline=False
            )

        # 6. Системные и игровые модули
        sys_lines = []
        gs_file = os.path.join(base_data_path, "system_configs", "game_schedule_config.json")
        if os.path.exists(gs_file):
            try:
                with open(gs_file, "r", encoding="utf-8") as fp:
                    cfg = json.load(fp)
                    cid = cfg.get("channel_id")
                    sys_lines.append(f"• **Игровое расписание The Division 2** ➔ {get_channel_str(cid)}")
            except Exception:
                pass

        sv_file = os.path.join(base_data_path, "system_configs", "secret_vendors_config.json")
        if os.path.exists(sv_file):
            try:
                with open(sv_file, "r", encoding="utf-8") as fp:
                    cfg = json.load(fp)
                    cid = cfg.get("channel_id")
                    cat_url = cfg.get("catalog_url", "https://rubenalamina.mx/the-division-weekly-vendor-reset/")
                    sys_lines.append(f"• [Секретные торговцы (Дэнни и Кэйси)]({cat_url}) ➔ {get_channel_str(cid)}")
            except Exception:
                pass

        fwd_file = os.path.join(base_data_path, "system_configs", "image_forwarder_config.json")
        if os.path.exists(fwd_file):
            try:
                with open(fwd_file, "r", encoding="utf-8") as fp:
                    cfg = json.load(fp)
                    if cfg.get("enabled"):
                        for rule in cfg.get("rules", []):
                            if rule.get("enabled"):
                                srcs = [f"<#{s}>" for s in rule.get("source_channel_ids", [])]
                                tgt = rule.get("target_channel_id")
                                src_str = ", ".join(srcs) if srcs else "не указан"
                                sys_lines.append(f"• **Перенаправление картинок**: Из {src_str} ➔ В {get_channel_str(tgt)}")
            except Exception:
                pass

        if sys_lines:
            embed.add_field(
                name="⚙️ Системные модули и расписания",
                value="\n".join(sys_lines[:20]),
                inline=False
            )

        if not embed.fields:
            embed.description = "В данный момент нет подключенных источников."

        if self.bot.user and getattr(self.bot.user, "display_avatar", None):
            embed.set_footer(text="Nexus Bot • Система мониторинга и публикаций", icon_url=self.bot.user.display_avatar.url)
        else:
            embed.set_footer(text="Nexus Bot • Система мониторинга и публикаций")

        return embed

    @commands.command(name="sources", aliases=["источники", "list_sources", "sources_list", "connections", "подключения"])
    async def sources_prefix(self, ctx: commands.Context):
        """Показать красивый список всех подключенных источников и каналов публикации (префиксная версия)."""
        embed = self._build_sources_embed()
        await ctx.send(embed=embed)

    @app_commands.command(name="sources", description="Показать красивый список всех подключенных источников и каналов публикации")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
    async def sources_slash(self, interaction: discord.Interaction):
        """Слэш-команда вывода всех подключенных источников."""
        embed = self._build_sources_embed()
        await interaction.response.send_message(embed=embed)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Централизованная обработка ошибок слэш-команд, в том числе cooldown."""
        async def _reply(msg: str) -> None:
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            except Exception:
                pass

        if isinstance(error, app_commands.CommandOnCooldown):
            await _reply(f"{Emojis.COOLDOWN} Команда на кулдауне. Повтори через **{error.retry_after:.1f}с**.")
        elif isinstance(error, app_commands.MissingPermissions):
            await _reply(f"{Emojis.PROHIBITED} У тебя нет прав для выполнения этой команды (требуется **Администратор**).")
        else:
            raise error


async def setup(bot):
    await bot.add_cog(CommandsModule(bot))
