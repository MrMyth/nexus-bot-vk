# modules/standalone/telegram_module.py

import asyncio
import aiohttp
import json
import os
import html
import pytz
from typing import Dict, Optional, Set
from datetime import datetime
import discord
from settings.config import Config
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, StatusEmojis, Emojis, LiveEmojis
from settings.data_files import Files
from modules_utils.helpers import safe_create_task
from modules_utils.cache_utils import load_json_cache, save_json_cache_async


from discord.ext import commands



class TelegramModule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.running = False
        self.cache_file = Files.TELEGRAM_CACHE_FILE
        self._voice_lock = asyncio.Lock()

        self.telegram_token = getattr(Config, 'TELEGRAM_BOT_TOKEN', None) or None
        self.telegram_channel_id = self._parse_telegram_chat_id(getattr(Config, 'TELEGRAM_CHANNEL_ID', None))
        self.telegram_thread_id = self._get_safe_int_config('TELEGRAM_THREAD_ID')

        self.excluded_voice_channels: Set[int] = set(self._get_excluded_channels())
        self.monitor_all_voice = getattr(Config, 'TELEGRAM_MONITOR_ALL_VOICE_CHANNELS', True)

        self.voice_channel_users = self.load_cache()

    def _parse_telegram_chat_id(self, value) -> Optional[str]:
        """
        Преобразует TELEGRAM_CHANNEL_ID в строку.
        Поддерживает:
          - строку напрямую (например, "@mychannel" или "-1001234567890")
          - число (будет преобразовано в строку)
        """
        if value is None:
            return None
        try:
            if isinstance(value, str):
                v = value.strip()
                return v if v else None
            elif isinstance(value, int):
                return str(value)
            else:
                s = str(value).strip()
                return s if s else None
        except Exception:
            return None

    def _get_safe_int_config(self, config_name: str) -> Optional[int]:
        """Безопасное получение целочисленного параметра (например, thread_id)"""
        try:
            value = getattr(Config, config_name, None)
            if value is None:
                return None
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                v = value.strip()
                return int(v) if v else None
            return int(value)
        except (ValueError, TypeError):
            return None

    def _get_excluded_channels(self) -> list:
        """Получает список ИСКЛЮЧЁННЫХ голосовых каналов из конфига"""
        try:
            channels_str = getattr(Config, 'TELEGRAM_EXCLUDED_VOICE_CHANNELS', '')
            if not channels_str:
                return []
            channels = []
            for ch in channels_str.split(','):
                ch = ch.strip()
                if ch:
                    channels.append(int(ch))
            return channels
        except Exception:
            return []

    def load_cache(self) -> Dict[str, list]:
        """Загружает кэш пользователей в голосовых каналах"""
        return load_json_cache(self.cache_file)

    async def save_cache(self):
        """Сохраняет кэш на диск асинхронно"""
        try:
            await save_json_cache_async(self.cache_file, self.voice_channel_users)
        except Exception as e:
            await send_to_any_log("error", f"Error saving Telegram cache: {e}", emoji=LogEmojis.ERROR)

    async def send_telegram_message(self, text: str, pre_formatted: bool = False) -> bool:
        """
        Отправляет сообщение в Telegram.
        
        :param text: Текст сообщения.
        :param pre_formatted: Если True — текст уже содержит HTML-разметку и не будет экранирован.
                              Если False (по умолчанию) — текст экранируется и оборачивается в шаблон.
        """
        if not self.telegram_token or self.telegram_channel_id is None:
            await send_to_any_log("error", "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID", emoji=LogEmojis.ERROR)
            return False

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"

        if pre_formatted:
            formatted_text = text
        else:
            formatted_text = f"{LiveEmojis.STREAM_TITLE} <b>Голосовой канал:</b>\n{html.escape(text)}"

        params = {
            "chat_id": self.telegram_channel_id,
            "text": formatted_text,
            "parse_mode": "HTML"
        }
        if self.telegram_thread_id:
            params["message_thread_id"] = self.telegram_thread_id

        try:
            from modules_utils.http_client import HttpClient
            # Используем обёртку HttpClient.post — даёт единые ретраи (429/5xx)
            # и маскирование URL/токенов в логах, как у остальных модулей.
            result = await HttpClient.post(url, json=params, error_level="error")
            if result is None:
                return False
            return True
        except Exception as e:
            # Маскируем токен на случай, если он попал в текст исключения
            safe_e = str(e).replace(self.telegram_token, "***MASKED***") if self.telegram_token else str(e)
            await send_to_any_log("error", f"Error sending to Telegram: {safe_e}", emoji=LogEmojis.ERROR)
            return False

    def get_channel_name(self, channel_id: int) -> str:
        """Получает название канала по ID"""
        channel = self.bot.get_channel(channel_id)
        return channel.name if channel else f"Канал {channel_id}"

    def get_user_display_name(self, member) -> str:
        """Получает отображаемое имя пользователя"""
        return member.display_name or member.name

    def _should_track_channel(self, channel) -> bool:
        """Определяет, нужно ли отслеживать канал"""
        if not channel:
            return False
        
        # Поддержка разных типов голосовых каналов
        is_voice = isinstance(channel, (discord.VoiceChannel, discord.StageChannel))
        if not is_voice:
            # На всякий случай проверяем по атрибутам, если isinstance подведет
            if not hasattr(channel, 'bitrate'): 
                return False
                
        if not self.monitor_all_voice:
            return False
            
        if channel.id in self.excluded_voice_channels:
            # asyncio.create_task(send_to_any_log("debug", f"Telegram: канал {channel.name} ({channel.id}) исключен из мониторинга", emoji="🚫"))
            return False
            
        return True

    def get_moscow_time(self) -> str:
        """Возвращает текущее время по часовому поясу из Config в формате 'DD.MM.YYYY HH:MM:SS'."""
        from settings.config import Config
        tz = pytz.timezone(Config.TIMEZONE_REGION)
        return datetime.now(tz).strftime("%d.%m.%Y %H:%M:%S")

    async def process_voice_state_update(self, member, before, after):
        """Обрабатывает изменения голосового состояния"""
        if not self.running:
            return

        before_channel = before.channel
        after_channel = after.channel

        track_before = self._should_track_channel(before_channel)
        track_after = self._should_track_channel(after_channel)

        if not track_before and not track_after:
            return

        user_name = self.get_user_display_name(member)
        timestamp = self.get_moscow_time()

        if not before_channel and after_channel and track_after:
            msg = f"{StatusEmojis.ONLINE} {user_name} вошел в {after_channel.name} ({timestamp}, время по Москве)"
            await self.send_telegram_message(msg)
            await self.update_channel_users(after_channel.id, member.id, 'join')

        elif before_channel and not after_channel and track_before:
            msg = f"{StatusEmojis.DND} {user_name} вышел из {before_channel.name} ({timestamp}, время по Москве)"
            await self.send_telegram_message(msg)
            await self.update_channel_users(before_channel.id, member.id, 'leave')

        elif before_channel and after_channel and before_channel.id != after_channel.id:
            if track_before and track_after:
                msg = f"{Emojis.REPOST} {user_name} перешел из {before_channel.name} в {after_channel.name} ({timestamp}, время по Москве)"
                await self.send_telegram_message(msg)
                await self.update_channel_users(before_channel.id, member.id, 'leave')
                await self.update_channel_users(after_channel.id, member.id, 'join')
            elif track_before:
                msg = f"{StatusEmojis.DND} {user_name} вышел из {before_channel.name} ({timestamp}, время по Москве)"
                await self.send_telegram_message(msg)
                await self.update_channel_users(before_channel.id, member.id, 'leave')
            elif track_after:
                msg = f"{StatusEmojis.ONLINE} {user_name} вошел в {after_channel.name} ({timestamp}, время по Москве)"
                await self.send_telegram_message(msg)
                await self.update_channel_users(after_channel.id, member.id, 'join')

    async def update_channel_users(self, channel_id: int, user_id: int, action: str):
        """Обновляет информацию о пользователях в канале (потокобезопасно)."""
        async with self._voice_lock:
            channel_key = str(channel_id)
            if action == 'join':
                if channel_key not in self.voice_channel_users:
                    self.voice_channel_users[channel_key] = []
                if user_id not in self.voice_channel_users[channel_key]:
                    self.voice_channel_users[channel_key].append(user_id)
            elif action == 'leave':
                if channel_key in self.voice_channel_users and user_id in self.voice_channel_users[channel_key]:
                    self.voice_channel_users[channel_key].remove(user_id)
                    if not self.voice_channel_users[channel_key]:
                        del self.voice_channel_users[channel_key]
        await self.save_cache()

    async def send_channel_status(self):
        """Отправляет в Telegram только непустые отслеживаемые голосовые каналы."""
        if not self.monitor_all_voice:
            return

        message_lines = []

        for guild in self.bot.guilds:
            # Проверка всех типов голосовых каналов
            channels = list(guild.voice_channels) + list(guild.stage_channels)
            for channel in channels:
                if not self._should_track_channel(channel):
                    continue
                members = [html.escape(self.get_user_display_name(m)) for m in channel.members]
                if members:
                    status = ", ".join(members)
                    message_lines.append(f"<b>{html.escape(channel.name)}:</b> {status}")

        if message_lines:
            message = f"{Emojis.POLL} <b>Активные голосовые каналы:</b>\n\n" + "\n".join(message_lines)
            await self.send_telegram_message(message, pre_formatted=True)

    async def on_voice_state_update_telegram(self, member, before, after):
        """Обработчик события Discord (специфичный для Telegram)"""
        safe_create_task(send_to_any_log("debug", f"Telegram Voice Update: {member.name}, before={before.channel}, after={after.channel}", emoji=LogEmojis.DEBUG))
        
        if not self.running:
            return
        try:
            await self.process_voice_state_update(member, before, after)
        except Exception as e:
            await send_to_any_log("error", f"Error handling voice_state_update in TelegramModule: {e}", emoji=LogEmojis.ERROR)

    async def start(self):
        """Запускает модуль и регистрирует обработчик."""
        if self.running:
            return
        if not self.telegram_token:
            await send_to_any_log("error", "TELEGRAM_BOT_TOKEN is not set", emoji=LogEmojis.ERROR)
            return
        if self.telegram_channel_id is None:
            await send_to_any_log("error", "TELEGRAM_CHANNEL_ID is not set (specify string: e.g., '-1001234567890' or '@mychannel')", emoji=LogEmojis.ERROR)
            return

        await send_to_any_log("debug",
            f"Telegram config: token={'***' + self.telegram_token[-4:] if self.telegram_token else 'None'}, "
            f"channel_id={self.telegram_channel_id}, "
            f"thread_id={self.telegram_thread_id}, "
            f"excluded_channels={sorted(self.excluded_voice_channels)}, "
            f"monitor_all={self.monitor_all_voice}",
            emoji=LogEmojis.INFO)

        self.bot.remove_listener(self.on_voice_state_update_telegram, 'on_voice_state_update')
        self.bot.add_listener(self.on_voice_state_update_telegram, 'on_voice_state_update')

        self.running = True

        info = f"Telegram module started (channel {self.telegram_channel_id}"
        if self.telegram_thread_id:
            info += f", thread {self.telegram_thread_id}"
        info += f", excluded channels: {len(self.excluded_voice_channels)})"
        await send_to_any_log("info", info, emoji=LogEmojis.STARTUP)

        # Запускаем фоновый цикл обновления статуса
        safe_create_task(self._status_loop())

    async def _status_loop(self):
        """Фоновый цикл периодической отправки статуса в Telegram"""
        await asyncio.sleep(10) # Даем боту время загрузиться
        while self.running:
            try:
                await send_to_any_log("info", f"Telegram: Starting voice status check...", emoji=LogEmojis.INFO, targets=["console", "file"])
                await self.send_channel_status()
            except Exception as e:
                await send_to_any_log("error", f"Error in Telegram status loop: {e}", emoji=LogEmojis.ERROR)
            
            # Обновляем статус раз в час (или по конфигу)
            # Используем дробленый сон, чтобы быстрее реагировать на остановку модуля
            for _ in range(3600 // 10):
                if not self.running:
                    break
                await asyncio.sleep(10)

    async def stop(self):
        """Останавливает модуль."""
        self.running = False
        self.bot.remove_listener(self.on_voice_state_update_telegram, 'on_voice_state_update')

        await self.save_cache()
        await send_to_any_log("info", "Telegram module stopped", emoji=LogEmojis.INFO)


async def setup(bot):
    cog = TelegramModule(bot)
    await bot.add_cog(cog)
    if hasattr(bot, 'app'):
        bot.app.telegram_module = cog

