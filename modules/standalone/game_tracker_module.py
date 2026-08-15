# modules/standalone/game_tracker_module.py
import discord
from discord.ext import commands
import time
import asyncio
from typing import Dict, List, Optional
from settings.config import Config
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, Emojis
from constants.strings import BotStrings

class GameTrackerModule(commands.Cog):
    """Модуль для отслеживания игровых активностей пользователей в Discord."""

    def __init__(self, bot):
        self.bot = bot
        self.is_running = False
        self.channel_id = getattr(Config, "GAME_TRACKER_CHANNEL_ID", None) or Config.USER_ACTIVITY_LOG_CHANNEL_ID
        self.ignore_role_ids = getattr(Config, "GAME_TRACKER_IGNORE_ROLE_IDS", []) or getattr(Config, "USER_ACTIVITY_IGNORE_ROLE_IDS", [])
        self.active_sessions: Dict[tuple, float] = {}  # (member_id, game_name) -> start_time_timestamp

    async def start(self):
        """Запускает модуль и регистрирует события."""
        if not self.channel_id:
            await send_to_any_log("warning", "GameTracker: GAME_TRACKER_CHANNEL_ID or USER_ACTIVITY_LOG_CHANNEL_ID not set", emoji=LogEmojis.WARNING)
            
        self.bot.remove_listener(self.on_presence_update_game, 'on_presence_update')
        self.bot.add_listener(self.on_presence_update_game, 'on_presence_update')
        
        self.is_running = True
        log_info = "GameTracker module started."
        if self.channel_id:
            log_channel = self.bot.get_channel(self.channel_id)
            channel_info = f"'{log_channel.name}'" if log_channel else str(self.channel_id)
            log_info += f" Tracking games → channel {channel_info}"
        
        await send_to_any_log("info", log_info, emoji=LogEmojis.STARTUP)

    async def stop(self):
        """Останавливает модуль."""
        self.is_running = False
        self.bot.remove_listener(self.on_presence_update_game, 'on_presence_update')
        await send_to_any_log("info", "GameTracker module stopped", emoji=LogEmojis.INFO)

    def _get_games(self, member: discord.Member) -> dict:
        """Извлекает активные игровые активности пользователя."""
        games = {}
        if not member or not hasattr(member, 'activities'):
            return games
            
        for activity in member.activities:
            # Игнорируем CustomActivity и Spotify
            if isinstance(activity, (discord.CustomActivity, discord.Spotify)):
                continue
            # Игнорируем обычный статус прослушивания медиа (например, "Слушает Spotify")
            if hasattr(activity, 'type') and activity.type == discord.ActivityType.listening:
                continue
                
            is_playing = False
            if isinstance(activity, discord.Game):
                is_playing = True
            elif hasattr(activity, 'type') and activity.type == discord.ActivityType.playing:
                is_playing = True
                
            if is_playing and activity.name:
                games[activity.name] = activity
        return games

    def _format_duration(self, seconds: int) -> str:
        """Форматирует продолжительность сессии в человекочитаемом виде."""
        if seconds < 60:
            return BotStrings.TIME_SEC.format(seconds=seconds)
        minutes = seconds // 60
        if minutes < 60:
            return BotStrings.TIME_MIN.format(minutes=minutes)
        hours = minutes // 60
        rem_minutes = minutes % 60
        if rem_minutes > 0:
            return BotStrings.TIME_HOURS_MIN.format(hours=hours, minutes=rem_minutes)
        return f"{hours} ч."

    async def on_presence_update_game(self, before: discord.Member, after: discord.Member):
        """Обработчик обновлений присутствия для отслеживания игр."""
        if not self.is_running or after.bot:
            return

        # Игнорируем по ролям
        if self.ignore_role_ids:
            if any(role.id in self.ignore_role_ids for role in after.roles):
                return

        before_games = self._get_games(before)
        after_games = self._get_games(after)

        started_games = [name for name in after_games if name not in before_games]
        stopped_games = [name for name in before_games if name not in after_games]

        current_time = time.time()

        for game_name in started_games:
            self.active_sessions[(after.id, game_name)] = current_time
            await self._log_game_event(after, game_name, "start")

        for game_name in stopped_games:
            start_time = self.active_sessions.pop((after.id, game_name), None)
            duration_str = ""
            if start_time:
                elapsed = int(current_time - start_time)
                # Игнорируем супер-короткие игровые сессии менее 5 секунд (защита от миганий API)
                if elapsed < 5:
                    continue
                duration_str = self._format_duration(elapsed)
            await self._log_game_event(after, game_name, "stop", duration_str)

    async def _log_game_event(self, member: discord.Member, game_name: str, event_type: str, duration_str: str = ""):
        """Отправляет отформатированное сообщение в канал логов."""
        if not self.channel_id:
            return

        log_channel = self.bot.get_channel(self.channel_id)
        if not log_channel:
            return

        # Ищем кастомные смайлики на основе названия игры (для The Division 2 можно использовать специальные)
        emoji = Emojis.GAME
        game_lower = game_name.lower()
        if "division" in game_lower:
            emoji = Emojis.TARGET  # Оранжевый прицел или щит для The Division
        elif "warcraft" in game_lower or "wow" in game_lower:
            emoji = Emojis.SWORD
        elif "dota" in game_lower:
            emoji = Emojis.SHIELD
        elif "counter-strike" in game_lower or "cs:" in game_lower or "csgo" in game_lower:
            emoji = Emojis.GUN
        elif "gta" in game_lower:
            emoji = Emojis.CAR

        if event_type == "start":
            msg = f"{emoji} **{member.display_name}** запустил(а) **{game_name}**"
        else:
            if duration_str:
                msg = f"{Emojis.STOP} **{member.display_name}** вышел(ла) из **{game_name}** (играл(а) {duration_str})"
            else:
                msg = f"{Emojis.STOP} **{member.display_name}** вышел(ла) из **{game_name}**"

        for attempt in range(1, 4):
            try:
                await log_channel.send(msg)
                break
            except Exception as e:
                if attempt < 3:
                     await asyncio.sleep(attempt * 2)
                else:
                    await send_to_any_log("error", f"GameTracker: failed to send message to Discord: {e}", emoji=LogEmojis.WARNING, targets=["console", "file"])


async def setup(bot):
    cog = GameTrackerModule(bot)
    await bot.add_cog(cog)
    if hasattr(bot, 'app'):
        bot.app.game_tracker_module = cog

