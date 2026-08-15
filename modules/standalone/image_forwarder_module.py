import asyncio
import json
import os
import re
import aiohttp
import discord
from typing import Optional, List, Dict, Any
from discord import app_commands
from discord.ext import commands

from settings.config import Config
from settings.data_files import Files
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, ImageForwarderEmojis
from constants.strings import BotStrings
from modules_utils.cache_utils import load_json_cache, save_json_cache_async
from modules_utils.helpers import safe_create_task


IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff', '.svg')
URL_REGEX = re.compile(r'https?://\S+')


class ImageForwarderModule(commands.Cog):
    """
    Модуль авто-перенаправления картинок:
    Отслеживает сообщения с картинками в исходном канале,
    временно сохраняет картинки локально, отправляет их в целевой канал БЕЗ текста,
    и затем сразу удаляет временные файлы.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = Files.IMAGE_FORWARDER_CONFIG_FILE
        self.temp_dir = Files.IMAGE_FORWARDER_TEMP_FOLDER
        self.module_config: Dict[str, Any] = {}
        self.forwarded_count: int = 0
        self._load_config()

    def _load_config(self):
        """Загружает конфигурацию модуля."""
        data = load_json_cache(self.config_file)
        if not data:
            data = {
                "enabled": True,
                "rules": [
                    {
                        "id": "default_rule",
                        "name": "Основное перенаправление",
                        "source_channel_ids": [],
                        "target_channel_id": None,
                        "enabled": True
                    }
                ],
                "ignore_bot_messages": True
            }

        # Синхронизация с переменными окружения/Config если правила пустые
        rules = data.get("rules", [])
        if rules and not rules[0].get("source_channel_ids") and Config.IMAGE_FORWARDER_SOURCE_CHANNEL_ID:
            rules[0]["source_channel_ids"] = [Config.IMAGE_FORWARDER_SOURCE_CHANNEL_ID]
        if rules and not rules[0].get("target_channel_id") and Config.IMAGE_FORWARDER_TARGET_CHANNEL_ID:
            rules[0]["target_channel_id"] = Config.IMAGE_FORWARDER_TARGET_CHANNEL_ID

        self.module_config = data
        self._save_config_sync()

    def _save_config_sync(self):
        """Синхронное сохранение файла конфигурации."""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.module_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"IMAGE_FORWARDER: Error saving config: {e}", emoji=LogEmojis.ERROR))

    async def _save_config_async(self):
        """Асинхронное сохранение файла конфигурации."""
        try:
            await save_json_cache_async(self.config_file, self.module_config)
        except Exception as e:
            await send_to_any_log("error", f"Error saving image_forwarder config: {e}", emoji=LogEmojis.ERROR)

    # =========================
    # ВПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =========================

    def _is_image_attachment(self, attachment: discord.Attachment) -> bool:
        """Проверяет, является ли вложение картинкой."""
        if attachment.content_type and attachment.content_type.startswith("image/"):
            return True
        filename_lower = attachment.filename.lower()
        return any(filename_lower.endswith(ext) for ext in IMAGE_EXTENSIONS)

    async def _download_url_image(self, session: aiohttp.ClientSession, url: str, dest_path: str) -> bool:
        """Скачивает изображение по URL во временный файл."""
        try:
            async with session.get(url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    with open(dest_path, "wb") as f:
                        f.write(data)
                    return True
        except Exception as e:
            await send_to_any_log("error", f"IMAGE_FORWARDER: Error downloading {url}: {e}", emoji=LogEmojis.ERROR)
        return False

    # =========================
    # СЛУШАТЕЛЬ СООБЩЕНИЙ
    # =========================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Слушатель всех входящих сообщений."""
        if not message.guild:
            return

        if self.module_config.get("ignore_bot_messages", True) and message.author.bot:
            return

        if not self.module_config.get("enabled", True):
            return

        rules = self.module_config.get("rules", [])
        matching_rules = []
        for rule in rules:
            if not rule.get("enabled", True):
                continue
            source_ids = rule.get("source_channel_ids", [])
            if message.channel.id in source_ids:
                matching_rules.append(rule)

        if not matching_rules:
            return

        # Ищем картинки во вложениях
        image_attachments = [att for att in message.attachments if self._is_image_attachment(att)]

        # Ищем ссылки на картинки в тексте или эмбедах, если нет вложений
        image_urls = []
        if not image_attachments:
            # Из текста
            found_urls = URL_REGEX.findall(message.content or "")
            for url in found_urls:
                clean_url = url.split("?")[0].lower()
                if any(clean_url.endswith(ext) for ext in IMAGE_EXTENSIONS):
                    image_urls.append(url)

            # Из эмбедов
            for embed in message.embeds:
                if embed.image and embed.image.url:
                    image_urls.append(embed.image.url)
                elif embed.thumbnail and embed.thumbnail.url:
                    image_urls.append(embed.thumbnail.url)

        if not image_attachments and not image_urls:
            return

        os.makedirs(self.temp_dir, exist_ok=True)

        for rule in matching_rules:
            target_channel_id = rule.get("target_channel_id")
            if not target_channel_id or target_channel_id == message.channel.id:
                continue

            target_channel = self.bot.get_channel(target_channel_id)
            if not target_channel:
                try:
                    target_channel = await self.bot.fetch_channel(target_channel_id)
                except Exception as e:
                    await send_to_any_log(
                        "error",
                        f"[IMAGE_FORWARDER] Failed to get target channel <#{target_channel_id}>: {e}",
                        emoji=LogEmojis.ERROR
                    )
                    continue

            saved_file_paths: List[str] = []
            try:
                # 1. Сохраняем картинки из вложений во временную папку
                for idx, att in enumerate(image_attachments):
                    safe_filename = f"{message.id}_{idx}_{att.filename}"
                    temp_path = os.path.join(self.temp_dir, safe_filename)
                    await att.save(temp_path)
                    saved_file_paths.append(temp_path)

                # 2. Сохраняем картинки по URL во временную папку (если нет вложений)
                if not saved_file_paths and image_urls:
                    from modules_utils.http_client import HttpClient
                    session = await HttpClient.get_session()
                    for idx, url in enumerate(image_urls):
                        ext = ".png"
                        for e in IMAGE_EXTENSIONS:
                            if url.split("?")[0].lower().endswith(e):
                                ext = e
                                break
                        safe_filename = f"{message.id}_url_{idx}{ext}"
                        temp_path = os.path.join(self.temp_dir, safe_filename)
                        success = await self._download_url_image(session, url, temp_path)
                        if success:
                            saved_file_paths.append(temp_path)

                if not saved_file_paths:
                    continue

                # 3. Формируем список объектов discord.File
                discord_files = [discord.File(fp) for fp in saved_file_paths]

                # 4. Отправляем в целевой канал БЕЗ ТЕКСТА
                await target_channel.send(content=None, files=discord_files)
                self.forwarded_count += len(saved_file_paths)

                # 5. Логируем успешное перенаправление
                await send_to_any_log(
                    "info",
                    f"{ImageForwarderEmojis.IMAGE} Forwarded images: **{len(saved_file_paths)}** from <#{message.channel.id}> to <#{target_channel_id}>",
                    emoji=LogEmojis.SUCCESS
                )

            except Exception as forward_err:
                await send_to_any_log(
                    "error",
                    f"[IMAGE_FORWARDER] Error forwarding images: {forward_err}",
                    emoji=LogEmojis.ERROR
                )
            finally:
                # 6. Важно: Очистка временных файлов после отправки
                for fp in saved_file_paths:
                    if os.path.exists(fp):
                        try:
                            os.remove(fp)
                        except Exception as rm_err:
                            await send_to_any_log("warning", f"IMAGE_FORWARDER: Error deleting temp file {fp}: {rm_err}", emoji=LogEmojis.WARNING)

    # =========================
    # UI И НАСТРОЙКИ (VIEWS & MODALS)
    # =========================

    def build_status_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"{ImageForwarderEmojis.IMAGE} {BotStrings.FORWARDER_EMBED_TITLE}",
            color=0x3498DB if self.module_config.get("enabled", True) else 0x95A5A6
        )
        enabled_str = f"{ImageForwarderEmojis.OPEN} {BotStrings.STATUS_ENABLED}" if self.module_config.get("enabled", True) else f"{ImageForwarderEmojis.CLOSED} {BotStrings.STATUS_DISABLED}"
        embed.add_field(name=BotStrings.FORWARDER_STATUS_LABEL, value=enabled_str, inline=True)
        embed.add_field(name=BotStrings.FORWARDER_COUNT_LABEL, value=f"`{self.forwarded_count}`", inline=True)

        rules = self.module_config.get("rules", [])
        if rules:
            rules_lines = []
            for r in rules:
                r_id = r.get("id", "rule")
                r_name = r.get("name", "Правило")
                sources = r.get("source_channel_ids", [])
                target = r.get("target_channel_id")
                is_on = ImageForwarderEmojis.OPEN if r.get("enabled", True) else ImageForwarderEmojis.CLOSED

                src_str = ", ".join(f"<#{s_id}>" for s_id in sources) if sources else "*Не заданы*"
                tgt_str = f"<#{target}>" if target else "*Не задан*"
                rules_lines.append(
                    f"{is_on} **{r_name}** (`{r_id}`):\n"
                    f"  ├ Исходные каналы: {src_str}\n"
                    f"  └ Целевой канал: {tgt_str}"
                )
            embed.add_field(name=f"{ImageForwarderEmojis.RULES} {BotStrings.FORWARDER_RULES_LABEL}", value="\n\n".join(rules_lines), inline=False)
        else:
            embed.add_field(name=f"{ImageForwarderEmojis.RULES} {BotStrings.FORWARDER_RULES_LABEL}", value=BotStrings.FORWARDER_NO_RULES, inline=False)

        embed.set_footer(text=BotStrings.FORWARDER_FOOTER)
        return embed

    # =========================
    # КОМАНДЫ ПРЕФИКСА И СЛЭШ
    # =========================

    @commands.command(name="forwarder_status", aliases=["статус_перенаправления", "image_forwarder_status"])
    @commands.has_permissions(administrator=True)
    async def forwarder_status_cmd(self, ctx: commands.Context):
        """Показывает статус и правила модуля перенаправления картинок."""
        embed = self.build_status_embed()
        view = ImageForwarderConfigView(self)
        await ctx.send(embed=embed, view=view)

    @app_commands.command(name="forwarder_status", description=BotStrings.FORWARDER_STATUS_CMD_DESC)
    @app_commands.checks.has_permissions(administrator=True)
    async def forwarder_status_slash(self, interaction: discord.Interaction):
        """Слэш-команда статуса перенаправления картинок."""
        embed = self.build_status_embed()
        view = ImageForwarderConfigView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.command(name="forwarder_add", aliases=["добавить_перенаправление", "image_forwarder_add"])
    @commands.has_permissions(administrator=True)
    async def forwarder_add_cmd(self, ctx: commands.Context, source_channel: discord.TextChannel, target_channel: discord.TextChannel):
        """Быстрое добавление/обновление правила перенаправления картинок."""
        rules = self.module_config.get("rules", [])
        if not rules:
            rules = [{
                "id": "default_rule",
                "name": "Основное перенаправление",
                "source_channel_ids": [source_channel.id],
                "target_channel_id": target_channel.id,
                "enabled": True
            }]
        else:
            if source_channel.id not in rules[0].get("source_channel_ids", []):
                rules[0].setdefault("source_channel_ids", []).append(source_channel.id)
            rules[0]["target_channel_id"] = target_channel.id

        self.module_config["rules"] = rules
        await self._save_config_async()

        await ctx.send(
            f"{ImageForwarderEmojis.SUCCESS} Настроено перенаправление картинок:\n"
            f"  └ Исходный канал: {source_channel.mention}\n"
            f"  └ Целевой канал: {target_channel.mention}"
        )

    @app_commands.command(name="forwarder_add", description="Добавить правило перенаправления картинок из одного канала в другой (Админ)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(source_channel="Исходный канал с картинками", target_channel="Целевой канал для отправки")
    async def forwarder_add_slash(self, interaction: discord.Interaction, source_channel: discord.TextChannel, target_channel: discord.TextChannel):
        """Слэш-команда добавления/обновления правила перенаправления картинок."""
        rules = self.module_config.get("rules", [])
        if not rules:
            rules = [{
                "id": "default_rule",
                "name": "Основное перенаправление",
                "source_channel_ids": [source_channel.id],
                "target_channel_id": target_channel.id,
                "enabled": True
            }]
        else:
            if source_channel.id not in rules[0].get("source_channel_ids", []):
                rules[0].setdefault("source_channel_ids", []).append(source_channel.id)
            rules[0]["target_channel_id"] = target_channel.id

        self.module_config["rules"] = rules
        await self._save_config_async()

        await interaction.response.send_message(
            f"{ImageForwarderEmojis.SUCCESS} Настроено перенаправление картинок:\n"
            f"  └ Исходный канал: {source_channel.mention}\n"
            f"  └ Целевой канал: {target_channel.mention}",
            ephemeral=True
        )


class EditForwarderRuleModal(discord.ui.Modal):
    source_channels_input = discord.ui.TextInput(
        label=BotStrings.FORWARDER_MODAL_SOURCE,
        placeholder="123456789012345678, 987654321098765432",
        required=True,
        style=discord.TextStyle.paragraph
    )
    target_channel_input = discord.ui.TextInput(
        label=BotStrings.FORWARDER_MODAL_TARGET,
        placeholder="123456789012345678",
        required=True,
        style=discord.TextStyle.short
    )

    def __init__(self, cog: ImageForwarderModule, rule_index: int = 0):
        super().__init__(title=BotStrings.FORWARDER_MODAL_TITLE)
        self.cog = cog
        self.rule_index = rule_index

        rules = cog.module_config.get("rules", [])
        if 0 <= rule_index < len(rules):
            rule = rules[rule_index]
            sources = rule.get("source_channel_ids", [])
            self.source_channels_input.default = ", ".join(str(s) for s in sources)
            if rule.get("target_channel_id"):
                self.target_channel_input.default = str(rule.get("target_channel_id"))

    async def on_submit(self, interaction: discord.Interaction):
        raw_sources = self.source_channels_input.value.split(",")
        parsed_sources = []
        for s in raw_sources:
            clean_s = s.strip().replace("<#", "").replace(">", "")
            if clean_s.isdigit():
                parsed_sources.append(int(clean_s))

        clean_target = self.target_channel_input.value.strip().replace("<#", "").replace(">", "")
        parsed_target = int(clean_target) if clean_target.isdigit() else None

        if not parsed_target:
            await interaction.response.send_message(f"{ImageForwarderEmojis.ERROR} {BotStrings.FORWARDER_ERR_TARGET_INVALID}", ephemeral=True)
            return

        rules = self.cog.module_config.get("rules", [])
        if 0 <= self.rule_index < len(rules):
            rules[self.rule_index]["source_channel_ids"] = parsed_sources
            rules[self.rule_index]["target_channel_id"] = parsed_target
        else:
            rules.append({
                "id": f"rule_{len(rules) + 1}",
                "name": f"Правило #{len(rules) + 1}",
                "source_channel_ids": parsed_sources,
                "target_channel_id": parsed_target,
                "enabled": True
            })

        self.cog.module_config["rules"] = rules
        await self.cog._save_config_async()

        embed = self.cog.build_status_embed()
        await interaction.response.send_message(
            content=f"{ImageForwarderEmojis.SUCCESS} Правило перенаправления картинок успешно обновлено!",
            embed=embed,
            ephemeral=True
        )


class ImageForwarderConfigView(discord.ui.View):
    def __init__(self, cog: ImageForwarderModule):
        super().__init__(timeout=180)
        self.cog = cog

    @discord.ui.button(label=BotStrings.FORWARDER_BTN_TOGGLE, style=discord.ButtonStyle.primary, emoji=ImageForwarderEmojis.GEAR, row=0)
    async def toggle_module(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(f"{ImageForwarderEmojis.ERROR} {BotStrings.FORWARDER_ERR_NO_PERMS}", ephemeral=True)
            return

        curr = self.cog.module_config.get("enabled", True)
        self.cog.module_config["enabled"] = not curr
        await self.cog._save_config_async()

        embed = self.cog.build_status_embed()
        status_txt = "включен" if not curr else "выключен"
        await interaction.response.send_message(f"{ImageForwarderEmojis.GEAR} Модуль перенаправления картинок **{status_txt}**.", embed=embed, ephemeral=True)

    @discord.ui.button(label=BotStrings.FORWARDER_BTN_CONFIG, style=discord.ButtonStyle.secondary, emoji=ImageForwarderEmojis.EDIT, row=0)
    async def edit_rule(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(f"{ImageForwarderEmojis.ERROR} {BotStrings.FORWARDER_ERR_NO_PERMS}", ephemeral=True)
            return

        modal = EditForwarderRuleModal(self.cog, rule_index=0)
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot):
    cog = ImageForwarderModule(bot)
    await bot.add_cog(cog)
    if hasattr(bot, "image_forwarder_module"):
        bot.image_forwarder_module = cog
