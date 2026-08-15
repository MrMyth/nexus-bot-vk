import discord
from discord.ext import commands
import time
import asyncio
import aiosqlite
from typing import Dict, Optional, List, Any
from settings.config import Config
from settings.data_files import Files
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, StatusEmojis, EmojisFields
from constants.strings import BotStrings
from modules_utils.helpers import safe_create_task


class UserActivityModule(commands.Cog):
    """Модуль для отслеживания изменений статуса, активности и управления ролями Актив/AFK."""

    def __init__(self, bot):
        self.bot = bot
        self.is_running = False
        self.channel_id = Config.USER_ACTIVITY_LOG_CHANNEL_ID
        self.ignore_role_ids = getattr(Config, "USER_ACTIVITY_IGNORE_ROLE_IDS", [])
        self.active_role_id = getattr(Config, "ACTIVE_ROLE_ID", None)
        self.afk_role_id = getattr(Config, "AFK_ROLE_ID", None)
        self.required_role_id = getattr(Config, "USER_ACTIVITY_REQUIRED_ROLE_ID", None)
        self.last_updates: Dict[int, float] = {}
        self.activity_cache: Dict[int, float] = {}  # Кэш времени последнего обновления в БД
        self.voice_status_cache: Dict[int, str] = {}
        self.custom_status_cache: Dict[int, str] = {}
        self._bg_task: Optional[asyncio.Task] = None
        self._db: Optional[aiosqlite.Connection] = None

    async def start(self):
        """Запускает модуль и регистрирует обработчики."""
        await self._init_db()

        if not self.channel_id:
            await send_to_any_log("warning", "UserActivity: USER_ACTIVITY_LOG_CHANNEL_ID not set", emoji=LogEmojis.WARNING)
        
        # Регистрация лисенеров
        self.bot.remove_listener(self.on_presence_update_activity, 'on_presence_update')
        self.bot.remove_listener(self.on_voice_state_update_activity, 'on_voice_state_update')
        self.bot.remove_listener(self.on_member_remove_activity, 'on_member_remove')
        self.bot.remove_listener(self.on_member_update_activity, 'on_member_update')
        self.bot.add_listener(self.on_presence_update_activity, 'on_presence_update')
        self.bot.add_listener(self.on_voice_state_update_activity, 'on_voice_state_update')
        self.bot.add_listener(self.on_member_remove_activity, 'on_member_remove')
        self.bot.add_listener(self.on_member_update_activity, 'on_member_update')

        self.is_running = True
        
        # Запуск фоновой проверки AFK (раз в 12 часов)
        if self.afk_role_id:
            self._bg_task = safe_create_task(self._afk_check_loop())

        # Настройка ConfigWatcher для .env в корне
        try:
            import os
            from modules_utils.config_watcher import ConfigWatcher
            self.config_watcher = ConfigWatcher()
            root_dir = os.getcwd()
            self.config_watcher.watch_directory(root_dir, self.reload_config, allowed_extensions=('.env',))
            self.config_watcher.start()
        except Exception as e:
            await send_to_any_log("warning", f"UserActivity: failed to start watching .env: {e}", emoji=LogEmojis.WARNING)

        log_info = f"UserActivity module started."
        if self.channel_id:
            log_channel = self.bot.get_channel(self.channel_id)
            channel_info = f"'{log_channel.name}'" if log_channel else str(self.channel_id)
            log_info += f" Tracking presence/status → channel {channel_info}"
        
        await send_to_any_log("info", log_info, emoji=LogEmojis.STARTUP)

    async def reload_config(self):
        """Горячая перезагрузка конфигурации UserActivity из .env."""
        import os
        from dotenv import load_dotenv
        from settings.config import Config
        from modules_utils.helpers import _get_int_or_none, _get_int_list
        
        env_path = os.path.join(os.getcwd(), ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path, override=True)
            
        self.channel_id = _get_int_or_none("USER_ACTIVITY_LOG_CHANNEL_ID")
        self.ignore_role_ids = _get_int_list("USER_ACTIVITY_IGNORE_ROLE_IDS", [])
        self.active_role_id = _get_int_or_none("ACTIVE_ROLE_ID")
        self.afk_role_id = _get_int_or_none("AFK_ROLE_ID")
        self.required_role_id = _get_int_or_none("USER_ACTIVITY_REQUIRED_ROLE_ID")
        
        Config.USER_ACTIVITY_LOG_CHANNEL_ID = self.channel_id
        Config.USER_ACTIVITY_IGNORE_ROLE_IDS = self.ignore_role_ids
        Config.ACTIVE_ROLE_ID = self.active_role_id
        Config.AFK_ROLE_ID = self.afk_role_id
        Config.USER_ACTIVITY_REQUIRED_ROLE_ID = self.required_role_id
        
        await send_to_any_log("info", "UserActivityModule: configuration hot-reloaded from .env", emoji=LogEmojis.SUCCESS)

    async def cog_unload(self):
        """Вызывается discord.py при выгрузке Cog — гарантирует закрытие соединения с БД."""
        await self.stop()

    async def stop(self):
        """Останавливает модуль и отписывается от событий."""
        self.is_running = False
        if self._bg_task:
            self._bg_task.cancel()
            self._bg_task = None

        if hasattr(self, "config_watcher") and self.config_watcher:
            try:
                self.config_watcher.stop()
            except Exception:
                pass

        self.bot.remove_listener(self.on_presence_update_activity, 'on_presence_update')
        self.bot.remove_listener(self.on_voice_state_update_activity, 'on_voice_state_update')
        self.bot.remove_listener(self.on_member_remove_activity, 'on_member_remove')
        self.bot.remove_listener(self.on_member_update_activity, 'on_member_update')

        if self._db:
            await self._db.close()
            self._db = None

        await send_to_any_log("info", "UserActivity module stopped", emoji=LogEmojis.INFO)

    def _delete_db_files(self, db_path: str) -> None:
        """Удаляет файл БД и сопутствующие WAL/SHM файлы."""
        import os
        for suffix in ("", "-wal", "-shm"):
            path = db_path + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as exc:
                    # Логируем неудачное удаление — это важный диагностический сигнал
                    safe_create_task(send_to_any_log("warning", f"UserActivity: failed to delete DB file {path}: {exc}", emoji=LogEmojis.WARNING))

    async def _init_db_internal(self, db_path: str) -> None:
        """Создаёт соединение и инициализирует схему БД активности.

        Использует временное соединение: присваивает self._db только после успешного
        коммита, чтобы при ошибке (в т.ч. malformed) не оставалось частично
        открытого хендла.
        """
        tmp = await aiosqlite.connect(db_path)
        try:
            await tmp.execute("PRAGMA journal_mode=WAL")
            await tmp.execute("PRAGMA synchronous=NORMAL")
            await tmp.execute("""
                CREATE TABLE IF NOT EXISTS user_activity (
                    user_id INTEGER PRIMARY KEY,
                    last_seen_online INTEGER
                )
            """)
            await tmp.commit()
        except Exception:
            try:
                await tmp.close()
            except Exception:
                pass
            raise
        self._db = tmp

    async def _init_db(self):
        """Инициализирует БД активности пользователей, открывает постоянное соединение."""
        db_path = Files.USER_ACTIVITY_DATABASE_FILE
        try:
            await self._init_db_internal(db_path)
        except Exception as e:
            if "malformed" in str(e).lower() or "corrupt" in str(e).lower():
                await send_to_any_log(
                    "warning",
                    f"{LogEmojis.WARNING} Detected activity DB corruption ({db_path}). Recreating DB...",
                    emoji=LogEmojis.WARNING
                )
                self._delete_db_files(db_path)
                await self._init_db_internal(db_path)
            else:
                raise

    async def _get_db(self) -> Optional[aiosqlite.Connection]:
        """Возвращает активное соединение с БД, переподключаясь при необходимости."""
        if self._db is None:
            try:
                self._db = await aiosqlite.connect(Files.USER_ACTIVITY_DATABASE_FILE)
                await self._db.execute("PRAGMA journal_mode=WAL")
                await self._db.execute("PRAGMA synchronous=NORMAL")
                await self._db.commit()
            except Exception as e:
                await send_to_any_log("error", f"Error reconnecting to activity DB: {e}", emoji=LogEmojis.ERROR)
                return None
        return self._db

    async def _update_activity(self, user_id: int):
        """Обновляет время последней активности пользователя с учетом кулдауна (10 мин)."""
        current_time = time.time()
        # Кулдаун 10 минут (600 сек) чтобы не дергать БД слишком часто
        if user_id in self.activity_cache and (current_time - self.activity_cache[user_id]) < 600:
            return
            
        self.activity_cache[user_id] = current_time
        db = await self._get_db()
        if db:
            await db.execute(
                "INSERT OR REPLACE INTO user_activity (user_id, last_seen_online) VALUES (?, ?)",
                (user_id, int(current_time))
            )
            await db.commit()

    async def _update_activity_batch(self, user_ids: List[int]):
        """Массовое обновление времени последней активности пользователей с учетом кулдауна."""
        current_time = int(time.time())
        to_update = []
        
        for uid in user_ids:
            if uid not in self.activity_cache or (current_time - self.activity_cache[uid]) >= 600:
                to_update.append((uid, current_time))
                self.activity_cache[uid] = float(current_time)
        
        if not to_update:
            return
            
        db = await self._get_db()
        if db:
            await db.executemany(
                "INSERT OR REPLACE INTO user_activity (user_id, last_seen_online) VALUES (?, ?)",
                to_update
            )
            await db.commit()

    async def get_user_activity_info(self, user_id: int) -> Optional[int]:
        """Возвращает timestamp последней онлайн-активности пользователя, или None если данных нет."""
        db = await self._get_db()
        if not db:
            return None
        try:
            async with db.execute(
                "SELECT last_seen_online FROM user_activity WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    async def on_member_remove_activity(self, member: discord.Member):
        """Удаляет запись об активности из базы, если участник покинул сервер."""
        if not self.is_running:
            return
        
        db = await self._get_db()
        if db:
            await db.execute("DELETE FROM user_activity WHERE user_id = ?", (member.id,))
            await db.commit()
        
        # Очищаем все in-memory кэши, чтобы память не росла бесконечно
        self.activity_cache.pop(member.id, None)
        self.last_updates.pop(member.id, None)
        self.custom_status_cache.pop(member.id, None)
            
        if getattr(Config, "FULL_LOG_USER_ACTIVITY", False):
            await send_to_any_log("info", f"Removed activity record for departed member {member.display_name}", emoji=LogEmojis.INFO)

    async def _afk_check_loop(self):
        """Цикл проверки пользователей на AFK."""
        await self.bot.wait_until_ready()
        
        # Задержка перед первой проверкой при старте (на всякий случай)
        await asyncio.sleep(30)
        
        # Конвертируем дни в секунды
        afk_seconds = Config.AFK_DAYS_THRESHOLD * 24 * 3600
        
        while self.is_running:
            try:
                guild = self.bot.get_guild(Config.SERVER_ID)
                if not guild:
                    await asyncio.sleep(60)
                    continue

                afk_role = guild.get_role(self.afk_role_id)
                active_role = guild.get_role(self.active_role_id) if self.active_role_id else None
                
                if not afk_role:
                    await asyncio.sleep(3600)
                    continue

                current_time = int(time.time())
                
                db = await self._get_db()
                if db:
                    async with db.execute("SELECT user_id, last_seen_online FROM user_activity") as cursor:
                        rows = await cursor.fetchall()
                        activity_map = {row[0]: row[1] for row in rows}
                else:
                    activity_map = {}

                online_ids = []
                for member in guild.members:
                    if member.bot: continue

                    # Игнорируем пользователей с ролями-исключениями
                    if self.ignore_role_ids:
                        if any(role.id in self.ignore_role_ids for role in member.roles):
                            continue
                    
                    # Если задана обязательная роль, и у пользователя её нет - пропускаем и снимаем роли активности
                    if self.required_role_id:
                        if not any(role.id == self.required_role_id for role in member.roles):
                            if Config.USER_ACTIVITY_MANAGE_ROLES:
                                try:
                                    removed = False
                                    if afk_role and afk_role in member.roles:
                                        await member.remove_roles(afk_role, reason="Снятие AFK: отсутствует обязательная роль")
                                        removed = True
                                    if active_role and active_role in member.roles:
                                        await member.remove_roles(active_role, reason="Снятие Активный: отсутствует обязательная роль")
                                        removed = True
                                    if removed:
                                        await send_to_any_log("info", f"Removed activity roles for {member.display_name} (missing required role)", emoji=LogEmojis.INFO)
                                catch Exception as e:
                                    await send_to_any_log("error", f"Error removing activity roles for {member.display_name}: {e}", emoji=LogEmojis.ERROR)
                            continue

                    # Если пользователь не в сети сейчас
                    if member.status == discord.Status.offline:
                        last_seen = activity_map.get(member.id)
                        
                        # Если мы за ним следили и он офлайн больше заданного порога
                        if last_seen and (current_time - last_seen) > afk_seconds:
                            if Config.USER_ACTIVITY_MANAGE_ROLES and afk_role and afk_role not in member.roles:
                                try:
                                    await member.add_roles(afk_role, reason=f"Офлайн более {Config.AFK_DAYS_THRESHOLD} дней (AFK)")
                                    if active_role and active_role in member.roles:
                                        await member.remove_roles(active_role, reason="Автоматический переход в AFK")
                                    await send_to_any_log("info", f"Member {member.display_name} marked as AFK (offline > {Config.AFK_DAYS_THRESHOLD} days)", emoji=LogEmojis.INFO)
                                except Exception as e:
                                    await send_to_any_log("error", f"Error assigning AFK role to {member.display_name}: {e}", emoji=LogEmojis.ERROR)
                    else:
                        # Если он в сети, запоминаем для пачки
                        online_ids.append(member.id)
                        
                        # Если у него была роль AFK, но он в сети - исправляем (на случай сбоя лисенеров)
                        if Config.USER_ACTIVITY_MANAGE_ROLES and afk_role and afk_role in member.roles:
                            await self._handle_active_role(member)

                # Массово обновляем активность онлайн-пользователей
                await self._update_activity_batch(online_ids)

            except Exception as e:
                await send_to_any_log("error", f"Error in AFK check loop: {e}", emoji=LogEmojis.ERROR)
            
            await asyncio.sleep(12 * 3600) # Проверка раз в 12 часов

    async def sync_all_members_activity(self, guild: discord.Guild) -> Dict[str, Any]:
        """
        Принудительная ручная синхронизация ролей активности (Активный/AFK) для всех участников сервера.
        Возвращает словарь с результатами синхронизации.
        """
        stats = {
            "total_checked": 0,
            "active_assigned": 0,
            "afk_assigned": 0,
            "roles_removed_no_req": 0,
            "ignored": 0,
            "errors": 0,
            "no_change": 0
        }

        afk_role = guild.get_role(self.afk_role_id) if self.afk_role_id else None
        active_role = guild.get_role(self.active_role_id) if self.active_role_id else None
        
        if not afk_role and not active_role:
            raise ValueError("Не настроены роли активного и AFK участника.")

        afk_seconds = Config.AFK_DAYS_THRESHOLD * 24 * 3600
        current_time = int(time.time())
        
        db = await self._get_db()
        if db:
            async with db.execute("SELECT user_id, last_seen_online FROM user_activity") as cursor:
                rows = await cursor.fetchall()
                activity_map = {row[0]: row[1] for row in rows}
        else:
            activity_map = {}

        online_ids = []
        
        for member in guild.members:
            if member.bot:
                continue
                
            stats["total_checked"] += 1
            
            # 1. Проверяем игнорируемые роли
            if self.ignore_role_ids:
                if any(role.id in self.ignore_role_ids for role in member.roles):
                    stats["ignored"] += 1
                    continue
                    
            # 2. Проверяем обязательную роль
            if self.required_role_id:
                if not any(role.id == self.required_role_id for role in member.roles):
                    # Если обязательной роли нет, убираем обе роли активности
                    removed = False
                    try:
                        if afk_role and afk_role in member.roles:
                            await member.remove_roles(afk_role, reason="Снятие AFK: отсутствует обязательная роль (принудительный запуск)")
                            removed = True
                        if active_role and active_role in member.roles:
                            await member.remove_roles(active_role, reason="Снятие Активный: отсутствует обязательная роль (принудительный запуск)")
                            removed = True
                        if removed:
                            stats["roles_removed_no_req"] += 1
                        else:
                            stats["no_change"] += 1
                    except Exception as e:
                        stats["errors"] += 1
                        await send_to_any_log("error", f"Error removing roles for {member.display_name} during sync: {e}", emoji=LogEmojis.ERROR)
                    continue

            # 3. Обработка ролей в зависимости от статуса (офлайн/онлайн)
            if member.status == discord.Status.offline:
                last_seen = activity_map.get(member.id)
                # Если офлайн больше порога AFK
                if last_seen and (current_time - last_seen) > afk_seconds:
                    if afk_role:
                        try:
                            changed = False
                            if afk_role not in member.roles:
                                await member.add_roles(afk_role, reason=f"Офлайн более {Config.AFK_DAYS_THRESHOLD} дней (AFK, ручная синхронизация)")
                                changed = True
                            if active_role and active_role in member.roles:
                                await member.remove_roles(active_role, reason="Синхронизация: переход в AFK")
                                changed = True
                            if changed:
                                stats["afk_assigned"] += 1
                            else:
                                stats["no_change"] += 1
                        except Exception as e:
                            stats["errors"] += 1
                            await send_to_any_log("error", f"Error transferring {member.display_name} to AFK during sync: {e}", emoji=LogEmojis.ERROR)
                    else:
                        stats["no_change"] += 1
                else:
                    # Офлайн, но не превысил порог (или нет данных) — оставляем как есть
                    stats["no_change"] += 1
            else:
                # В сети
                online_ids.append(member.id)
                try:
                    changed = False
                    if afk_role and afk_role in member.roles:
                        await member.remove_roles(afk_role, reason="Появился в сети (ручная синхронизация)")
                        changed = True
                    if active_role and active_role not in member.roles:
                        await member.add_roles(active_role, reason="Активность в сети (ручная синхронизация)")
                        changed = True
                    if changed:
                        stats["active_assigned"] += 1
                    else:
                        stats["no_change"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    await send_to_any_log("error", f"Error assigning active role to {member.display_name} during sync: {e}", emoji=LogEmojis.ERROR)

        # Массово обновляем активность онлайн-пользователей
        if online_ids:
            await self._update_activity_batch(online_ids)
            
        return stats

    async def on_presence_update_activity(self, before: discord.Member, after: discord.Member):
        """Обработчик изменений статуса и управления ролями."""
        if not self.is_running or after.bot:
            return

        # Управление ролями (Актив / AFK)
        if after.status != discord.Status.offline:
            await self._update_activity(after.id)
            if Config.USER_ACTIVITY_MANAGE_ROLES:
                await self._handle_active_role(after)

        # Логирование в канал (если включено)
        if self.channel_id:
            await self._log_presence_change(before, after)

    async def _handle_active_role(self, member: discord.Member):
        """Выдает роль 'Активный' и убирает 'AFK'."""
        if member.bot:
            return

        # Игнорируем пользователей с ролями-исключениями
        if self.ignore_role_ids:
            if any(role.id in self.ignore_role_ids for role in member.roles):
                return

        # Проверяем обязательную роль
        if self.required_role_id:
            if not any(role.id == self.required_role_id for role in member.roles):
                # Если у пользователя нет обязательной роли, убираем роли активности
                guild = member.guild
                active_role = guild.get_role(self.active_role_id) if self.active_role_id else None
                afk_role = guild.get_role(self.afk_role_id) if self.afk_role_id else None
                
                changed = False
                try:
                    if afk_role and afk_role in member.roles:
                        await member.remove_roles(afk_role, reason="Снятие AFK: отсутствует обязательная роль")
                        changed = True
                    if active_role and active_role in member.roles:
                        await member.remove_roles(active_role, reason="Снятие Активный: отсутствует обязательная роль")
                        changed = True
                    if changed:
                        await send_to_any_log("info", f"Removed activity roles for {member.display_name} (missing required role)", emoji=LogEmojis.INFO)
                except Exception as e:
                    await send_to_any_log("error", f"Error removing activity roles for {member.display_name}: {e}", emoji=LogEmojis.ERROR)
                return

        guild = member.guild
        active_role = guild.get_role(self.active_role_id) if self.active_role_id else None
        afk_role = guild.get_role(self.afk_role_id) if self.afk_role_id else None

        changed = False
        try:
            if afk_role and afk_role in member.roles:
                await member.remove_roles(afk_role, reason="Появился в сети")
                changed = True
            
            if active_role and active_role not in member.roles:
                await member.add_roles(active_role, reason="Активность в сети")
                changed = True
                
            if changed:
                await send_to_any_log("info", f"Updated activity roles for {member.display_name} (Active)", emoji=LogEmojis.SUCCESS)
        except Exception as e:
            await send_to_any_log("error", f"Error updating roles for {member.display_name}: {e}", emoji=LogEmojis.ERROR)

    async def _log_presence_change(self, before: discord.Member, after: discord.Member):
        # Игнорируем ботов
        if after.bot:
            return

        # Игнорируем пользователей с указанными ролями
        if self.ignore_role_ids:
            if any(role.id in self.ignore_role_ids for role in after.roles):
                return

        current_time = time.time()
        if after.id in self.last_updates and (current_time - self.last_updates[after.id]) < 5:
            return
        self.last_updates[after.id] = current_time

        messages = []
        if before.status != after.status:
            status_text = self._format_status(after.status)
            tmpl = BotStrings.get("ACT_LOG_STATUS_CHANGED", "**{name}** изменил статус на: {status}")
            messages.append(tmpl.format(name=after.display_name, status=status_text))

        if not after.voice or not after.voice.channel:
            before_custom = self._get_custom_status(before)
            after_custom = self._get_custom_status(after)
            if before_custom != after_custom:
                if after_custom:
                    tmpl = BotStrings.get("ACT_LOG_CUSTOM_STATUS_SET", "**{name}** установил статус: `{status}`")
                    messages.append(tmpl.format(name=after.display_name, status=after_custom))
                else:
                    tmpl = BotStrings.get("ACT_LOG_CUSTOM_STATUS_REMOVED", "**{name}** удалил статус")
                    messages.append(tmpl.format(name=after.display_name))

        await self._send_messages(messages)

    async def on_member_update_activity(self, before: discord.Member, after: discord.Member):
        """Обработчик обновлений участников (включая изменение ролей)."""
        if not self.is_running or after.bot:
            return

        # Если изменились роли
        if before.roles != after.roles:
            # Если отслеживание и управление ролями активности включено
            if Config.USER_ACTIVITY_MANAGE_ROLES:
                # Если статус не оффлайн, запускаем обычную обработку (где идет в т.ч. проверка обязательной роли)
                if after.status != discord.Status.offline:
                    await self._handle_active_role(after)
                else:
                    # Если статус оффлайн, но роли изменились (например сняли обязательную роль),
                    # то нам нужно проверить обязательную роль и снять активный/AFK если её нет.
                    if self.required_role_id and not any(role.id == self.required_role_id for role in after.roles):
                        guild = after.guild
                        active_role = guild.get_role(self.active_role_id) if self.active_role_id else None
                        afk_role = guild.get_role(self.afk_role_id) if self.afk_role_id else None
                        
                        changed = False
                        try:
                            if afk_role and afk_role in after.roles:
                                await after.remove_roles(afk_role, reason="Снятие AFK: убрана обязательная роль")
                                changed = True
                            if active_role and active_role in after.roles:
                                await after.remove_roles(active_role, reason="Снятие Активный: убрана обязательная роль")
                                changed = True
                            if changed:
                                await send_to_any_log("info", f"Removed activity roles for {after.display_name} (required role removed)", emoji=LogEmojis.INFO)
                        except Exception as e:
                            await send_to_any_log("error", f"Error removing activity roles for {after.display_name}: {e}", emoji=LogEmojis.ERROR)

    async def on_voice_state_update_activity(self, member: discord.Member, before, after):
        """Обработчик изменений голосового состояния — для отслеживания статуса голосового канала."""
        if not self.is_running or member.bot:
            return

        # Игнорируем пользователей с указанными ролями
        if self.ignore_role_ids:
            if any(role.id in self.ignore_role_ids for role in member.roles):
                return

        if not after.channel:
            return

        current_time = time.time()
        if member.id in self.last_updates and (current_time - self.last_updates[member.id]) < 5:
            return
        self.last_updates[member.id] = current_time

        # Получаем статус голосового канала
        voice_status = self._get_voice_channel_status(member)
        channel_id = after.channel.id
        prev_status = self.voice_status_cache.get(channel_id)

        if voice_status != prev_status:
            self.voice_status_cache[channel_id] = voice_status
            channel_name = after.channel.name

            if voice_status:
                tmpl = BotStrings.get("ACT_LOG_VOICE_STATUS_CHANGED", "{emoji} Статус голосового канала **{channel}** изменён на: `{status}` (установил: **{name}**)")
                msg = tmpl.format(emoji=EmojisFields.VOICE, channel=channel_name, status=voice_status, name=member.display_name)
            else:
                tmpl = BotStrings.get("ACT_LOG_VOICE_STATUS_REMOVED", "{emoji} Статус голосового канала **{channel}** удалён (пользователь: **{name}**)")
                msg = tmpl.format(emoji=EmojisFields.VOICE, channel=channel_name, name=member.display_name)

            await self._send_messages([msg])

    # Исправлено: теперь корректно ловит “Задать статус голосового канала”
    def _get_voice_channel_status(self, member: discord.Member) -> Optional[str]:
        """
        Извлекает статус, заданный через 'Задать статус голосового канала'.
        Discord помечает это как CustomActivity с полем state и без name.
        """
        if not member.voice or not member.voice.channel:
            return None

        for activity in member.activities:
            if (
                isinstance(activity, discord.CustomActivity)
                and getattr(activity, "state", None)
                and not getattr(activity, "name", None)
            ):
                return activity.state
        return None

    def _get_custom_status(self, member: discord.Member) -> Optional[str]:
        """Извлекает обычный кастомный статус (не в голосовом канале)."""
        for activity in member.activities:
            if isinstance(activity, discord.CustomActivity) and getattr(activity, "name", None):
                return activity.name
        return None

    @staticmethod
    def _format_status(status: discord.Status) -> str:
        """Форматирует статус в читаемый вид."""
        online_str = BotStrings.get("STATUS_NAME_ONLINE", "в сети")
        offline_str = BotStrings.get("STATUS_NAME_OFFLINE", "не в сети")
        idle_str = BotStrings.get("STATUS_NAME_IDLE", "неактивен")
        dnd_str = BotStrings.get("STATUS_NAME_DND", "не беспокоить")
        unknown_str = BotStrings.get("STATUS_NAME_UNKNOWN", "неизвестен")

        status_map = {
            discord.Status.online: f"{online_str} {StatusEmojis.ONLINE}",
            discord.Status.offline: f"{offline_str} {StatusEmojis.OFFLINE}",
            discord.Status.idle: f"{idle_str} {StatusEmojis.IDLE}",
            discord.Status.dnd: f"{dnd_str} {StatusEmojis.DND}"
        }
        return status_map.get(status, f"{unknown_str} {StatusEmojis.UNKNOWN}")

    async def _send_messages(self, messages: list):
        """Отправляет список сообщений в лог-канал с автоматическим перезапуском и ретраями при сетевых сбоях."""
        if not messages:
            return
        
        log_channel = self.bot.get_channel(self.channel_id)
        channel_name = log_channel.name if log_channel else str(self.channel_id)

        if not log_channel:
            await send_to_any_log("error", f"UserActivity: channel {self.channel_id} not found", emoji=LogEmojis.ERROR)
            return

        for msg in messages:
            error = None
            for attempt in range(1, 4):
                try:
                    await log_channel.send(msg)
                    error = None
                    break
                except Exception as e:
                    error = e
                    if attempt < 3:
                        # Логируем предупреждение в локальный лог/консоль без спама в дискорд
                        await send_to_any_log("warning", f"UserActivity: temporary error sending to {channel_name} (attempt {attempt}/3): {e}. Retrying in {attempt * 2}s...", emoji=LogEmojis.WARNING, targets=["console", "file"])
                        await asyncio.sleep(attempt * 2)
                    else:
                        break

            if error:
                await send_to_any_log("error", f"UserActivity: critical error sending to {channel_name} after 3 attempts: {error}", emoji=LogEmojis.ERROR)

            # Логируем только если FULL_LOG_USER_ACTIVITY == True
            if getattr(Config, "FULL_LOG_USER_ACTIVITY", False):
                log_text = f"UserActivity ({channel_name}): {msg}"
                if error:
                    log_text += f" (send error: {error})"
                await send_to_any_log("info", log_text, emoji=LogEmojis.INFO)


async def setup(bot):
    cog = UserActivityModule(bot)
    await bot.add_cog(cog)
    if hasattr(bot, 'app'):
        bot.app.user_activity_module = cog

