import asyncio
import json
import os
import aiofiles
from typing import Optional, List

import aiohttp
import discord
from bs4 import BeautifulSoup

from settings.config import Config
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, Emojis
from constants.strings import BotStrings
from settings.data_files import Files
from modules_utils.helpers import safe_create_task
from modules_utils.cache_utils import load_json_cache, save_json_cache_async


from discord.ext import commands


class PDFMonitorModule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.running = False
        self.task = None
        self.cache_file = Files.PDF_CACHE_FILE
        self.update_history: List[str] = self.load_update_history()
        self.configs: List[dict] = []

    async def _load_configs(self):
        """Загружает конфигурации из pdf_configs"""
        from modules_utils.files import get_config_path
        config_dir = get_config_path("pdf_configs")
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
            return

        self.configs = []
        filenames = await asyncio.to_thread(os.listdir, config_dir)
        for filename in filenames:
            if filename.endswith('.json'):
                file_path = os.path.join(config_dir, filename)
                try:
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        config = json.loads(content)
                        if config.get('url'):
                            self.configs.append(config)
                except Exception as e:
                    await send_to_any_log("error", f"Error loading PDF config {filename}: {e}", emoji=LogEmojis.ERROR)

    # =========================
    # CACHE
    # =========================

    def load_update_history(self) -> List[str]:
        data = load_json_cache(self.cache_file)
        return data.get("dates", [])

    async def save_update_history(self):
        try:
            await save_json_cache_async(self.cache_file, {"dates": self.update_history})
        except Exception as e:
            await send_to_any_log("error", f"Error saving PDF date history: {e}", emoji=LogEmojis.ERROR)

    # =========================
    # HTTP FETCH
    # =========================

    async def get_last_updated_date(self, url: str) -> Optional[str]:
        """Получает дату 'Last updated:' с веб-страницы через HTTP-запрос с авто-fallback на Selenium."""
        html = None
        try:
            from modules_utils.http_client import HttpClient
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            }
            # Используем глобальную сессию HttpClient вместо создания новой на каждый запрос.
            # HttpClient обеспечивает retry-логику и единое управление соединениями.
            result = await HttpClient.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
                suppress_errors=True,
            )
            if isinstance(result, str):
                html = result
        except Exception:
            pass

        # Пробуем найти дату в полученном базовом html
        date_value = None
        if html:
            date_value = self._parse_date_from_html(html)

        # Если не удалось найти дату (например, из-за SPA клиентского рендеринга или Cloudflare),
        # задействуем headless-браузер Selenium
        if not date_value:
            try:
                from modules_utils.selenium_helper import SeleniumHelper
                import hashlib
                
                url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
                profile = f"pdf_{url_hash}"
                
                selenium_html = await asyncio.to_thread(
                    SeleniumHelper.fetch_page_source,
                    url,
                    profile,
                    4.0  # даем время на выполнение JS скриптов и отработку спа-приложением
                )
                
                if selenium_html:
                    date_value = self._parse_date_from_html(selenium_html)
            except Exception as e:
                await send_to_any_log("warning", f"PDF Monitor (Selenium fallback): failed to extract date for {url}: {e}", emoji=LogEmojis.WARNING)

        return date_value

    def _parse_date_from_html(self, html: str) -> Optional[str]:
        """Вспомогательный метод парсинга даты 'Last updated:' из HTML контента."""
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Ищем текст "Last updated:" в любом теге
            for tag in soup.find_all(string=lambda t: t and "Last updated:" in t):
                text = tag.strip()
                if "Last updated:" in text:
                    return text.split("Last updated:")[-1].strip()

            # Запасной вариант: ищем любой элемент, содержащий этот текст во вложенных ветках
            for el in soup.find_all(True):
                if el.string and "Last updated:" in el.string:
                    return el.string.split("Last updated:")[-1].strip()
        except Exception:
            pass
        return None

    # =========================
    # MAIN CHECK
    # =========================

    async def check_config(self, config: dict):
        url = config.get("url")
        if not url:
            return

        current_date = await self.get_last_updated_date(url)
        if not current_date:
            return

        # Фильтрация по содержимому даты или заголовку
        from modules_utils.text_filter import TextFilter
        name = config.get('name', url)
        if TextFilter.should_skip(current_date, config, context=f"PDF:{name}"):
            return

        cache_key = f"{url}_{current_date}"
        if cache_key in self.update_history:
            return

        await send_to_any_log("info", f"Update detected for {url}: {current_date}", emoji=LogEmojis.INFO)

        success = await self.send_notification_to_discord(current_date, config)
        if success:
            self.update_history.append(cache_key)
            await self.save_update_history()

    # =========================
    # DISCORD
    # =========================

    async def send_notification_to_discord(self, date_value: str, config: dict) -> bool:
        channel_id = config.get("discord_channel_id") or config.get("channel_id") or Config.PDF_CHANNEL_ID
        try:
            channel = self.bot.get_channel(int(channel_id)) if channel_id else None
        except (ValueError, TypeError):
            await send_to_any_log("error", f"PDF Monitor: invalid channel_id: {channel_id!r}", emoji=LogEmojis.ERROR)
            return False
        if not channel:
            await send_to_any_log("error", f"PDF Monitor: channel {channel_id} not found in Discord", emoji=LogEmojis.ERROR)
            return False

        role_id = config.get("role_id") or Config.PDF_MENTION_ROLE_ID
        content = f"<@&{role_id}>" if role_id else ""

        embed = discord.Embed()
        embed.title = f"{config.get('emoji', Emojis.POLL)} {config.get('name', BotStrings.PDF_EMBED_DEFAULT_NAME)}"
        embed.url = config.get("url")
        embed.description = BotStrings.PDF_NEW_UPDATE_MSG.format(date=date_value)

        from modules_utils.helpers import hex_to_color_int, parse_color_to_int
        color_hex = config.get("color")
        if color_hex:
            embed.color = hex_to_color_int(color_hex)
        else:
            embed.color = parse_color_to_int(Config.EMBED_COLOR, 0x0099FF)

        from modules_utils.helpers import resolve_asset_url
        author_name = config.get("embed_author_name")
        if author_name:
            embed.set_author(name=author_name, icon_url=resolve_asset_url(config.get("embed_author_icon_url")))

        thumb = resolve_asset_url(config.get("embed_thumbnail_url"))
        if thumb:
            embed.set_thumbnail(url=thumb)

        preview = resolve_asset_url(config.get("preview"))
        if isinstance(preview, str) and preview:
            embed.set_image(url=preview)

        footer = config.get("embed_footer_text", "PDF Monitor")
        embed.set_footer(text=footer, icon_url=resolve_asset_url(config.get("embed_footer_icon_url")))

        if config.get("use_base_info_field", True):
            from constants.base import Text
            from constants.emojis import EmojisFields
            embed.add_field(name=f"{EmojisFields.INFO} {BotStrings.PDF_INFO_FIELD}", value=Text.INFO_EMBED, inline=False)

        try:
            if hasattr(self.bot, "discord_bot") and self.bot.discord_bot:
                await self.bot.discord_bot.send_message_async(
                    channel_id=int(channel_id),
                    content=content,
                    embed=embed,
                    config=config
                )
            else:
                sent_msg = await channel.send(content=content, embed=embed)
                if sent_msg and hasattr(self.bot, "discord_bot") and self.bot.discord_bot:
                    await self.bot.discord_bot._handle_auto_publish(sent_msg, channel, config)
            channel_info = f"'{channel.name}' ({channel_id})"
            await send_to_any_log("info", f"PDF notification sent to channel {channel_info}", emoji=LogEmojis.INFO)
            return True
        except Exception as e:
            await send_to_any_log("error", f"Error sending PDF notification to Discord: {e}", emoji=LogEmojis.ERROR)
            return False

    # =========================
    # LOOP
    # =========================

    async def run_monitor(self):
        await send_to_any_log("info", "PDF Monitor started", emoji=LogEmojis.STARTUP)

        while self.running:
            try:
                await send_to_any_log("info", "PDF: Starting new file check...", emoji=LogEmojis.INFO, targets=["console", "file"])
                await self._load_configs()
                for config in self.configs:
                    await self.check_config(config)
                    await asyncio.sleep(10)

                interval = Config.PDF_CHECK_INTERVAL or 1800
                await asyncio.sleep(interval)

            except Exception as e:
                await send_to_any_log("error", f"Error in PDF monitor loop: {e}", emoji=LogEmojis.ERROR)
                await asyncio.sleep(60)

    async def reload_configs(self):
        """Горячая перезагрузка конфигураций PDF."""
        await self._load_configs()
        await send_to_any_log("info", f"PDF Monitor: configurations hot-reloaded (active: {len(self.configs)})", emoji=LogEmojis.SUCCESS)

    async def start(self):
        if self.running:
            return
        self.running = True
        await self._load_configs()
        
        # Горячая перезагрузка конфигов PDF
        try:
            from modules_utils.config_watcher import ConfigWatcher
            from modules_utils.files import get_config_path
            self.config_watcher = ConfigWatcher()
            config_dir = get_config_path("pdf_configs")
            self.config_watcher.watch_directory(config_dir, self.reload_configs)
            self.config_watcher.start()
        except Exception as e:
            await send_to_any_log("warning", f"PDF Monitor: failed to start config watcher: {e}", emoji=LogEmojis.WARNING)

        self.task = safe_create_task(self.run_monitor())

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
        if hasattr(self, "config_watcher") and self.config_watcher:
            try:
                self.config_watcher.stop()
            except Exception:
                pass
        await send_to_any_log("info", "PDF Monitor stopped", emoji=LogEmojis.INFO)


async def setup(bot):
    cog = PDFMonitorModule(bot)
    await bot.add_cog(cog)
    if hasattr(bot, 'app'):
        bot.app.pdf_monitor_module = cog

