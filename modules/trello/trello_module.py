# trello_module.py
import discord
from datetime import datetime
import asyncio
import json
import aiohttp
import hashlib
import os
from typing import Dict, Optional, List
from settings.config import Config
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, Emojis
from settings.data_files import Files
from modules.trello.trello_boards import TRELLO_BOARDS
from modules_utils.helpers import safe_create_task
from modules_utils.cache_utils import load_json_cache, save_json_cache_async


class TrelloModule:
    def __init__(self, bot):
        self.bot = bot
        self.running = False
        self.task = None
        self.cache_file = Files.TRELLO_CACHE_FILE
        self.poll_interval = Config.TRELLO_POLL_INTERVAL or 1800
        self.seen_cards = self.load_cache()

    def load_cache(self) -> Dict[str, Dict[str, str]]:
        return load_json_cache(self.cache_file)

    async def save_cache(self):
        try:
            await save_json_cache_async(self.cache_file, self.seen_cards)
        except Exception as e:
            await send_to_any_log("error", f"Ошибка сохранения кэша Trello: {e}", emoji=LogEmojis.ERROR)

    async def fetch_board_json(self, board_shortlink: str) -> Optional[Dict]:
        url = f"https://trello.com/b/{board_shortlink}.json"
        try:
            from modules_utils.http_client import HttpClient
            data = await HttpClient.get(url)
            if isinstance(data, dict):
                return data
            elif isinstance(data, str):
                import json
                try:
                    return json.loads(data)
                except Exception:
                    pass
            return None
        except Exception as e:
            await send_to_any_log("error", f"Ошибка получения доски {board_shortlink}: {e}", emoji=LogEmojis.ERROR)
            return None

    def checksum_card(self, card: Dict) -> str:
        relevant_data = (card.get("name", ""), card.get("desc", ""), card.get("dateLastActivity", ""))
        return hashlib.md5(str(relevant_data).encode()).hexdigest()

    async def process_board(self, board_config: Dict) -> List[Dict]:
        """Обрабатывает одну доску Trello и возвращает список новых/изменённых карточек."""
        board_shortlink = board_config.get("shortlink")
        if not board_shortlink:
            await send_to_any_log("error", f"Пропущена доска без shortlink: {board_config.get('name')}", emoji=LogEmojis.ERROR)
            return []

        board_data = await self.fetch_board_json(board_shortlink)
        if not board_data:
            return []

        board_id = board_data.get("id", board_shortlink)
        cards = board_data.get("cards", [])
        updated_cards = []

        for card in cards:
            if card.get("closed", False):
                continue

            card_id = card.get("id")
            if not card_id:
                continue

            # Фильтрация карточек
            from modules_utils.text_filter import TextFilter
            name = card.get("name", "")
            desc = card.get("desc", "")
            # Проверяем и имя, и описание
            if TextFilter.should_skip(name, board_config, context=f"Trello:{board_config.get('name')}") or \
               TextFilter.should_skip(desc, board_config, context=f"Trello:{board_config.get('name')}"):
                continue

            checksum = self.checksum_card(card)
            cache_key = f"{board_id}_{card_id}"

            if cache_key not in self.seen_cards or self.seen_cards[cache_key] != checksum:
                updated_cards.append(card)
                self.seen_cards[cache_key] = checksum

        return updated_cards

    async def send_aggregated_notification(self, board_config: Dict, cards: List[Dict]):
        """Отправляет одно уведомление о новых карточках в доске."""
        channel_id = board_config.get("channel_id")
        if not channel_id:
            await send_to_any_log("error", f"Нет channel_id для доски {board_config.get('name')}", emoji=LogEmojis.ERROR)
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            await send_to_any_log("error", f"Канал {channel_id} не найден для доски {board_config.get('name')}", emoji=LogEmojis.ERROR)
            return

        mention_role_id = board_config.get("mention_role_id")
        content = f"<@&{mention_role_id}>" if mention_role_id else ""

        # Отправляем заголовок
        header_embed = discord.Embed(
            description=f"{Emojis.MAIL} **Новые или обновлённые карточки в доске «{board_config.get('name', 'Неизвестная доска')}»!**",
            color=0x0079BF
        )
        try:
            await channel.send(content=content, embed=header_embed)
        except Exception as e:
            await send_to_any_log("error", f"Ошибка отправки заголовка Trello: {e}", emoji=LogEmojis.ERROR)
            return

        # Отправляем каждую карточку отдельным сообщением
        for card in cards:
            embed = discord.Embed(
                title=card.get("name", "Без названия"),
                description=card.get("desc", "")[:2000] or "Описание отсутствует",
                url=card.get("url"),
                color=0x0079BF
            )
            last_activity = card.get("dateLastActivity")
            if last_activity:
                embed.timestamp = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))

            try:
                await channel.send(embed=embed)
            except Exception as e:
                await send_to_any_log("error", f"Ошибка отправки карточки Trello: {e}", emoji=LogEmojis.ERROR)

        await send_to_any_log("info", f"Отправлено уведомление о {len(cards)} карточках из доски '{board_config.get('name')}'", emoji=LogEmojis.INFO)

    async def poll_boards(self):
        """Основной цикл опроса досок"""
        while self.running:
            try:
                await send_to_any_log("info", "Trello: Пошла новая проверка досок...", emoji=LogEmojis.INFO, targets=["console", "file"])
                
                for board_config in TRELLO_BOARDS:
                    if not self.running:
                        break
                    try:
                        updated_cards = await self.process_board(board_config)
                        if updated_cards:
                            await self.send_aggregated_notification(board_config, updated_cards)
                        await asyncio.sleep(2)
                    except Exception as e:
                        await send_to_any_log("error", f"Ошибка обработки доски {board_config.get('name')}: {e}", emoji=LogEmojis.ERROR)
                
                await self.save_cache()
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                await send_to_any_log("error", f"Ошибка в цикле опроса Trello: {e}", emoji=LogEmojis.ERROR)
                await asyncio.sleep(60)

    async def start(self):
        """Запускает модуль Trello"""
        if self.running:
            return

        if not TRELLO_BOARDS:
            await send_to_any_log("warning", "Нет досок для отслеживания в Trello модуле", emoji=LogEmojis.WARNING)
            return

        self.running = True
        self.task = safe_create_task(self.poll_boards())
        
        board_names = [board.get("name", "Неизвестная доска") for board in TRELLO_BOARDS]
        await send_to_any_log("info", f"Trello модуль запущен. Отслеживаемые доски: {', '.join(board_names)}", emoji=LogEmojis.STARTUP)

    async def stop(self):
        """Останавливает модуль Trello"""
        self.running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        await self.save_cache()
        await send_to_any_log("info", "Trello модуль остановлен", emoji=LogEmojis.INFO)