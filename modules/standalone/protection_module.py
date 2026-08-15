import asyncio
import json
import os
from typing import Set, List
from discord.ext import commands
from discord import ChannelType
import discord
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from constants.strings import BotStrings
from settings.config import Config
from settings.data_files import Files
from modules_utils.helpers import safe_create_task
from modules_utils.cache_utils import save_json_cache_async, load_json_cache



class ChannelProtectionModule(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.enabled = Config.ENABLE_DISCORD_CHANNEL_PROTECTION
        self.disable_chat_in_voice = getattr(Config, 'DISABLE_CHAT_IN_VOICE', False)
        self.block_sending_instead_of_delete = getattr(Config, 'BLOCK_SENDING_INSTEAD_OF_DELETE', False)
        self.protect_everyone_here_mentions = getattr(Config, 'PROTECT_EVERYONE_HERE_MENTIONS', True)
        self.everyone_here_bypass_role_ids = getattr(Config, 'EVERYONE_HERE_BYPASS_ROLE_IDS', [])
        self.protected_channels: Set[int] = set()
        self.auto_protected_channels: Set[int] = set()
        self.voice_channels: Set[int] = set()  # Список для голосовых каналов
        self.list_path = Files.CHANNEL_PROTECTION_LIST_PATH
        self.voice_list_path = Files.VOICE_CHANNEL_LIST_PATH  # Путь для списка голосовых каналов
        self.blocked_channels_path = os.path.join(os.path.dirname(self.list_path), "permission_blocked_channels.json")
        self.currently_blocked_channels: Set[int] = set()
        
        # Создаем и загружаем списки
        self._ensure_protection_list()
        self._ensure_voice_list()
        self._load_protected_channels()
        self._load_voice_channels()
        self._load_currently_blocked_channels()
        
    def _ensure_protection_list(self):
        """Создает файл со списком защищенных каналов если его нет."""
        if not os.path.exists(self.list_path):
            try:
                os.makedirs(os.path.dirname(self.list_path), exist_ok=True)
                example_data = {
                    "description": "Список ID каналов, защищенных от сообщений пользователей",
                    "protected_channels": [
                        123456789012345678,  # Пример ID канала 1
                        987654321098765432   # Пример ID канала 2
                    ]
                }
                with open(self.list_path, 'w', encoding='utf-8') as f:
                    json.dump(example_data, f, ensure_ascii=False, indent=2)
                safe_create_task(send_to_any_log("info", f"Protection: created example protected channels file: {self.list_path}", emoji=LogEmojis.INFO))
            except Exception as e:
                safe_create_task(send_to_any_log("error", f"Protection: error creating protected channels file: {e}", emoji=LogEmojis.ERROR))

    def _ensure_voice_list(self):
        """Создает файл со списком голосовых каналов если его нет."""
        if not os.path.exists(self.voice_list_path):
            try:
                os.makedirs(os.path.dirname(self.voice_list_path), exist_ok=True)
                with open(self.voice_list_path, 'w', encoding='utf-8') as f:
                    json.dump({"voice_channels": []}, f, ensure_ascii=False, indent=2)
                safe_create_task(send_to_any_log("info", f"Protection: created example voice channels file: {self.voice_list_path}", emoji=LogEmojis.INFO))
            except Exception as e:
                safe_create_task(send_to_any_log("error", f"Protection: error creating voice channels file: {e}", emoji=LogEmojis.ERROR))

    def _load_protected_channels(self):
        """Загружает список защищенных каналов из JSON файла."""
        try:
            if os.path.exists(self.list_path):
                with open(self.list_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                channels = data.get('protected_channels', [])
                self.protected_channels = set(int(ch) for ch in channels if ch)
                safe_create_task(send_to_any_log("info", f"Protection: loaded protected channels: {len(self.protected_channels)}", emoji=LogEmojis.INFO))
            else:
                self.protected_channels = set()
                safe_create_task(send_to_any_log("warning", "Protection: protected channels file not found", emoji=LogEmojis.WARNING))
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"Protection: error loading protected channels: {e}", emoji=LogEmojis.ERROR))
            self.protected_channels = set()

    def _load_voice_channels(self):
        """Загружает список голосовых каналов из JSON файла."""
        try:
            if os.path.exists(self.voice_list_path):
                with open(self.voice_list_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                channels = data.get('voice_channels', [])
                self.voice_channels = set(channels)
                safe_create_task(send_to_any_log("info", f"Protection: loaded voice channels: {len(self.voice_channels)}", emoji=LogEmojis.INFO))
            else:
                self.voice_channels = set()
                safe_create_task(send_to_any_log("warning", "Protection: voice channels file not found", emoji=LogEmojis.WARNING))
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"Protection: error loading voice channels: {e}", emoji=LogEmojis.ERROR))
            self.voice_channels = set()

    def _load_currently_blocked_channels(self):
        """Загружает список каналов, у которых права были изменены ботом."""
        try:
            if os.path.exists(self.blocked_channels_path):
                with open(self.blocked_channels_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                channels = data.get('blocked_channels', [])
                self.currently_blocked_channels = set(int(ch) for ch in channels if ch)
                safe_create_task(send_to_any_log("info", f"Protection: loaded previously blocked channel permissions: {len(self.currently_blocked_channels)}", emoji=LogEmojis.INFO))
            else:
                self.currently_blocked_channels = set()
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"Protection: error loading blocked channel permissions: {e}", emoji=LogEmojis.ERROR))
            self.currently_blocked_channels = set()

    def _save_currently_blocked_channels(self):
        """Сохраняет список каналов с измененными правами."""
        try:
            os.makedirs(os.path.dirname(self.blocked_channels_path), exist_ok=True)
            with open(self.blocked_channels_path, 'w', encoding='utf-8') as f:
                json.dump({"blocked_channels": list(self.currently_blocked_channels)}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"Protection: error saving blocked channel permissions: {e}", emoji=LogEmojis.ERROR))

    async def reload_voice_list(self):
        """Перезагружает список голосовых каналов из файла."""
        old_count = len(self.voice_channels)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_voice_channels)
        new_count = len(self.voice_channels)
        
        safe_create_task(send_to_any_log("info", 
            f"Voice channels list reloaded. Previous: {old_count}, current: {new_count}", 
            emoji=LogEmojis.INFO))
        
        return new_count

    async def is_channel_protected(self, channel_id: int) -> bool:
        """Проверяет, защищен ли канал (явно или автоматически)."""
        return channel_id in self.protected_channels or channel_id in self.auto_protected_channels

    async def is_voice_channel(self, channel_id: int) -> bool:
        """Проверяет, является ли канал голосовым."""
        return channel_id in self.voice_channels
    
    async def get_protected_channels(self) -> List[int]:
        """Возвращает список защищенных каналов."""
        return list(self.protected_channels)

    async def get_voice_channels(self) -> List[int]:
        """Возвращает список голосовых каналов."""
        return list(self.voice_channels)

    async def _delete_and_warn(self, message, reason: str):
        """Вспомогательный метод для удаления сообщения и отправки временного предупреждения."""
        try:
            safe_create_task(send_to_any_log("warning", 
                f"Deleting message from {message.author} ({reason}) in #{message.channel.name} ({message.channel.id}): {message.content}",
                emoji=LogEmojis.WARNING))

            # Ждем 1.2 сек перед удалением, если есть упоминания, чтобы Discord сбросил красный индикатор (ghost ping) и обновил клиентский кэш
            if self._has_everyone_here(message):
                await asyncio.sleep(1.2)

            await message.delete()

            try:
                warn_template = BotStrings.get("PROTECTION_WARNING_TEXT", "⚠️ Внимание, {user}! Этот канал предназначен только для чтения/медиа. Ваше текстовое сообщение было удалено.")
                await message.channel.send(
                    warn_template.format(user=message.author.mention, reason=reason),
                    delete_after=5.0
                )
            except Exception as warn_e:
                safe_create_task(send_to_any_log("warning",
                    f"Failed to send warning to user {message.author}: {warn_e}",
                    emoji=LogEmojis.WARNING))
        except discord.NotFound:
            # Сообщение уже было удалено другим процессом или событием, игнорируем ошибку 404
            pass
        except Exception as e:
            safe_create_task(send_to_any_log("error", 
                f"Error deleting message in channel {message.channel.id}: {e}", 
                emoji=LogEmojis.ERROR))

    def _has_everyone_here(self, message) -> bool:
        """Проверяет наличие @everyone или @here в сообщении."""
        content = message.content or ""
        if "@everyone" in content or "@here" in content:
            return True
        if getattr(message, "mention_everyone", False):
            return True
        return False

    async def _delete_and_warn_mention(self, message):
        """Удаляет сообщение с упоминанием everyone/here и отправляет временное предупреждение."""
        try:
            safe_create_task(send_to_any_log("warning", 
                f"Detected forbidden mention (@everyone/@here) from {message.author} in #{message.channel.name} ({message.channel.id}): {message.content}",
                emoji=LogEmojis.WARNING))

            # Ждем 1.2 сек перед удалением, чтобы спровоцировать Discord сбросить красный индикатор (ghost ping) и обновить клиентский кэш
            await asyncio.sleep(1.2)

            await message.delete()

            try:
                mention_warn_template = BotStrings.get("PROTECTION_MENTION_WARNING", "{user}, упоминание `@everyone` и `@here` запрещено.")
                await message.channel.send(
                    mention_warn_template.format(user=message.author.mention),
                    delete_after=5.0
                )
            except Exception as warn_e:
                safe_create_task(send_to_any_log("warning",
                    f"Failed to send warning to user {message.author}: {warn_e}",
                    emoji=LogEmojis.WARNING))
        except discord.NotFound:
            pass
        except Exception as e:
            safe_create_task(send_to_any_log("error", 
                f"Error deleting message with mention in channel {message.channel.id}: {e}", 
                emoji=LogEmojis.ERROR))

    async def on_guild_channel_create(self, channel):
        """Обрабатывает создание нового канала"""
        if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            self.voice_channels.add(channel.id)
            # При создании нового голосового канала, возможно, нужно обновить список автозащиты?
            # Лучше дождаться периодического обновления или вызвать его
            safe_create_task(self.gather_auto_protected_channels())
        
        safe_create_task(self._apply_protection_permissions())

    async def on_guild_channel_delete(self, channel):
        """Обрабатывает удаление канала"""
        self.protected_channels.discard(channel.id)
        self.auto_protected_channels.discard(channel.id)
        self.voice_channels.discard(channel.id)
        if channel.id in self.currently_blocked_channels:
            self.currently_blocked_channels.discard(channel.id)
            self._save_currently_blocked_channels()

    async def _periodic_update_task(self):
        """Периодически обновляет список защищенных каналов (раз в час)"""
        await asyncio.sleep(600)  # Первое обновление через 10 минут
        while True:
            try:
                await self.gather_auto_protected_channels()
                # Также обновляем список голосовых каналов на всякий случай
                new_voice = set()
                for guild in self.bot.guilds:
                    for vc in guild.voice_channels:
                        new_voice.add(vc.id)
                    for sc in guild.stage_channels:
                        new_voice.add(sc.id)
                self.voice_channels = new_voice
                
                # Применяем обновленные разрешения
                await self._apply_protection_permissions()
                
            except Exception as e:
                await send_to_any_log("error", f"Protection: error in background update: {e}", emoji=LogEmojis.ERROR)
            
            await asyncio.sleep(3600)  # Раз в час

    async def on_message(self, message):
        """Обработчик сообщений — удаляет сообщения не от бота в защищённых каналах, в голосовых чатах (если включено) или с запрещенными упоминаниями."""
        if not self.enabled:
            return
            
        # Игнорируем сообщения от бота и других ботов
        if message.author == self.bot.user or message.author.bot:
            return

        channel = message.channel

        # Автоматическая выдача роли бана при сообщении в специальном канале
        trap_channel_id = getattr(Config, 'AUTO_BAN_CHANNEL_ID', None)
        if trap_channel_id and channel.id == trap_channel_id:
            member = message.author
            message_content = message.content[:1000] if message.content else BotStrings.get("PROTECTION_TRAP_EMPTY_MSG", "<Пустое сообщение/вложение>")
            
            # Сначала удаляем сообщение, чтобы Discord успел отправить событие MESSAGE_DELETE
            # клиенту пользователя, пока у него ещё есть полные роли и доступ к каналу.
            try:
                await message.delete()
            except Exception:
                pass
                
            # Короткая пауза, чтобы клиент обработал удаление сообщения и убрал его с экрана
            await asyncio.sleep(0.7)

            if isinstance(member, discord.Member):
                # Обход бана для администраторов и владельца сервера (Иммунитет)
                is_admin = member.guild_permissions.administrator or member.id == member.guild.owner_id
                if is_admin:
                    safe_create_task(send_to_any_log("warning",
                        f"Administrator {member} ({member.id}) posted in trap channel #{channel.name}: `{message_content}`. Punishment skipped due to immunity.",
                        emoji=LogEmojis.WARNING))
                    return

                ban_role_id = getattr(Config, 'AUTO_BAN_ROLE_ID', None)
                if ban_role_id:
                    role = member.guild.get_role(ban_role_id)
                    if role:
                        if role in member.roles:
                            # Уже забанен, повторно действия не применяем
                            return
                        try:
                            # Чтобы гарантированно и мгновенно снять все остальные роли у нарушителя
                            # мы задействуем модуль зависимостей ролей (RoleDependencyModule), если он активен.
                            r_dep_cog = self.bot.get_cog("RoleDependencyModule")
                            if r_dep_cog and r_dep_cog.running:
                                actions = {
                                    "add_roles_ids": [ban_role_id],
                                    "remove_roles_ids": [],
                                    "remove_all_other_roles": True
                                }
                                await r_dep_cog.apply_actions_compiled(
                                    member, 
                                    actions, 
                                    "автовыдача роли бана за сообщение в канале-ловушке",
                                    trigger_role_ids={ban_role_id}
                                )
                            else:
                                # Резервный вариант, если модуль зависимостей ролей отключен
                                await member.add_roles(role, reason="Автоматическая выдача роли бана по сообщению в канале")
                            
                            safe_create_task(send_to_any_log("warning", 
                                f"Assigned ban role {role.name} ({ban_role_id}) to {member} ({member.id}) for message in #{channel.name}. Content: `{message_content}`",
                                emoji=LogEmojis.WARNING))
                        except discord.Forbidden:
                            safe_create_task(send_to_any_log("error", 
                                f"Missing permissions to assign ban role {ban_role_id} to user {member}",
                                emoji=LogEmojis.ERROR))
                        except Exception as e:
                            safe_create_task(send_to_any_log("error", 
                                f"Error assigning ban role {ban_role_id} to user {member}: {e}",
                                emoji=LogEmojis.ERROR))
                    else:
                        safe_create_task(send_to_any_log("error", 
                            f"Ban role with ID {ban_role_id} not found on server {member.guild.name}",
                            emoji=LogEmojis.ERROR))
                else:
                    safe_create_task(send_to_any_log("warning",
                        f"User {member} posted in trap channel #{channel.name}, but AUTO_BAN_ROLE_ID is not configured. Content: `{message_content}`",
                        emoji=LogEmojis.WARNING))
            return

        # Определяем защищенность канала и голосового чата
        is_protected = await self.is_channel_protected(channel.id)
        is_voice = self.disable_chat_in_voice and await self.is_voice_channel(channel.id)

        # Вычисляем причину блокировки по правилам защиты каналов
        protection_reason = None
        if is_protected:
            protection_reason = BotStrings.get("PROTECTION_REASON_PROTECTED", "канал защищён")
            if channel.id in self.auto_protected_channels:
                protection_reason = BotStrings.get("PROTECTION_REASON_BOT_POSTING", "канал используется ботом для публикаций")
        elif is_voice:
            protection_reason = BotStrings.get("PROTECTION_REASON_VOICE_DISABLED", "чат в голосовом канале запрещён")

        # Проверка 1: защита от упоминаний @everyone и @here
        has_forbidden_mention = False
        if self.protect_everyone_here_mentions:
            if self._has_everyone_here(message):
                bypass = False
                if hasattr(message.author, "guild_permissions"):
                    if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages:
                        bypass = True
                    elif any(r.id in self.everyone_here_bypass_role_ids for r in getattr(message.author, "roles", [])):
                        bypass = True
                
                if not bypass:
                    has_forbidden_mention = True

        # Если есть несанкционированное упоминание, удаляем его в любом случае (даже при BLOCK_SENDING_INSTEAD_OF_DELETE)
        if has_forbidden_mention:
            if protection_reason:
                # Если это произошло в защищенном канале, выводим причину о защите канала
                await self._delete_and_warn(message, reason=protection_reason)
            else:
                await self._delete_and_warn_mention(message)
            return

        # Если включена блокировка отправки на уровне прав, то мы не удаляем обычные сообщения (они заблокированы на уровне Discord)
        if self.block_sending_instead_of_delete:
            return

        # Для обычных сообщений (без блокирующих тегов) в защищенных/голосовых каналах
        if protection_reason:
            await self._delete_and_warn(message, reason=protection_reason)
            return

    async def gather_auto_protected_channels(self):
        """Автоматически собирает ID всех каналов, в которые бот что-либо постит."""
        if not Config.AUTO_PROTECT_POSTING_CHANNELS:
            return

        # Небольшая пауза, чтобы убедиться, что все менеджеры успели загрузить свои конфиги
        await asyncio.sleep(2)

        self.auto_protected_channels.clear()
        
        # 1. Глобальные логи и системные каналы
        for attr in ["GLOBAL_LOG_CHANNEL_ID", "USER_ACTIVITY_LOG_CHANNEL_ID", "PDF_CHANNEL_ID"]:
            val = getattr(Config, attr, None)
            if val: 
                try:
                    self.auto_protected_channels.add(int(val))
                except Exception:
                    pass  # val не является числом — пропускаем

        app = getattr(self.bot, "app", None)
        if not app: return

        # 2. Каналы из мониторов (VK Wall, Live и т.д.)
        managers = [
            getattr(app, "vk_wall_manager", None),
            getattr(app, "vk_live_manager", None),
            getattr(app, "youtube_manager", None),
            getattr(app, "rutube_manager", None),
            getattr(app, "twitch_live_manager", None),
            getattr(app, "kick_live_manager", None),
            getattr(app, "vk_asset_manager", None)
        ]

        for manager in managers:
            if manager and hasattr(manager, "monitors"):
                for m_id, monitor in manager.monitors.items():
                    # Пытаемся достать channel_id из конфига монитора
                    # У волл-мониторов обычно group_config, у стрим-мониторов config
                    cfg = getattr(monitor, "config", getattr(monitor, "group_config", {}))
                    ch_id = cfg.get("discord_channel_id") or cfg.get("channel_id")
                    if ch_id:
                        try:
                            self.auto_protected_channels.add(int(ch_id))
                        except Exception:
                            pass  # ch_id не является числом — пропускаем

        # 3. Дополнительные модули
        if hasattr(app, "telegram_module") and app.telegram_module:
            # Если в будущем телеграм будет писать в дискорд, добавим сюда
            pass

        if self.auto_protected_channels:
            safe_create_task(send_to_any_log("info", 
                f"Auto-protected posting channels: {len(self.auto_protected_channels)}", 
                emoji=LogEmojis.PROTECTION))

    async def _apply_protection_permissions(self, force_reset: bool = False):
        """Применяет или сбрасывает права доступа к каналам в зависимости от настроек."""
        block_sending = self.block_sending_instead_of_delete and self.enabled and not force_reset
        
        # Собираем все каналы, которые ДОЛЖНЫ быть защищены блокировкой отправки прямо сейчас
        target_protected = set()
        if block_sending:
            target_protected.update(self.protected_channels)
            target_protected.update(self.auto_protected_channels)
            if self.disable_chat_in_voice:
                target_protected.update(self.voice_channels)

        # Каналы для обработки: те, которые должны быть заблокированы, и те, которые были заблокированы ранее
        channels_to_process = target_protected | self.currently_blocked_channels
        if not channels_to_process:
            return

        changed_any = False

        # Находим каналы, которые больше не существуют во всех гильдиях бота
        existing_ids = set()
        for guild in self.bot.guilds:
            for ch_id in channels_to_process:
                if guild.get_channel(ch_id) is not None:
                    existing_ids.add(ch_id)
        
        # Если какие-то ID из currently_blocked_channels больше не существуют, удалим их
        missing_ids = self.currently_blocked_channels - existing_ids
        if missing_ids:
            self.currently_blocked_channels -= missing_ids
            changed_any = True

        for guild in self.bot.guilds:
            for channel_id in list(channels_to_process):
                channel = guild.get_channel(channel_id)
                if not channel:
                    continue
                
                # Относится ли канал к этой гильдии
                if channel.guild.id != guild.id:
                    continue

                is_target = channel_id in target_protected
                
                # Получаем текущие права для @everyone (guild.default_role)
                overwrites = channel.overwrites_for(guild.default_role)
                current_send = overwrites.send_messages
                
                changed = False
                
                if is_target:
                    # Хотим заблокировать отправку
                    if current_send is not False:
                        overwrites.send_messages = False
                        changed = True
                        self.currently_blocked_channels.add(channel_id)
                else:
                    # Хотим вернуть по умолчанию (None)
                    if current_send is False:
                        overwrites.send_messages = None
                        changed = True
                    if channel_id in self.currently_blocked_channels:
                        self.currently_blocked_channels.discard(channel_id)
                        changed_any = True
                
                if changed:
                    try:
                        await channel.set_permissions(
                            guild.default_role, 
                            overwrite=overwrites, 
                            reason="Автоматическая настройка защиты каналов (блокировка отправки)"
                        )
                        changed_any = True
                    except discord.Forbidden:
                        pass # Если нет прав на управление каналом
                    except Exception as e:
                        safe_create_task(send_to_any_log("error", f"Protection: error setting permissions for channel {channel.id}: {e}", emoji=LogEmojis.ERROR))

        if changed_any:
            self._save_currently_blocked_channels()

    async def start(self):
        """Запускает модуль защиты каналов."""
        if not self.enabled:
            safe_create_task(send_to_any_log("info", 
                "Channel protection module is disabled in config", 
                emoji=LogEmojis.INFO))
            return
            
        # Собираем автоматически защищаемые каналы
        await self.gather_auto_protected_channels()

        # Собираем голосовые каналы с сервера
        for guild in self.bot.guilds:
            for voice_channel in guild.voice_channels:
                self.voice_channels.add(voice_channel.id)

        # Сохраняем обновленный список голосовых каналов
        self._save_voice_channels()

        # Применяем измененные права доступа (блокировка отправки)
        await self._apply_protection_permissions()

        # Сначала удаляем существующие слушатели, чтобы избежать дублирования
        self.bot.remove_listener(self.on_message, 'on_message')
        self.bot.remove_listener(self.on_guild_channel_create, 'on_guild_channel_create')
        self.bot.remove_listener(self.on_guild_channel_delete, 'on_guild_channel_delete')

        self.bot.add_listener(self.on_message, 'on_message')
        self.bot.add_listener(self.on_guild_channel_create, 'on_guild_channel_create')
        self.bot.add_listener(self.on_guild_channel_delete, 'on_guild_channel_delete')
        
        # Запускаем фоновую задачу для периодического обновления списка каналов
        safe_create_task(self._periodic_update_task())
        
        # Настройка ConfigWatcher для списков защищенных каналов
        try:
            from modules_utils.config_watcher import ConfigWatcher
            self.config_watcher = ConfigWatcher()
            config_dir = os.path.dirname(self.list_path)
            self.config_watcher.watch_directory(config_dir, self.reload_configs)
            self.config_watcher.start()
        except Exception as e:
            safe_create_task(send_to_any_log("warning", f"ChannelProtectionModule: failed to start config watcher: {e}", emoji=LogEmojis.WARNING))

        # Собираем названия защищенных каналов для лога
        protected_list = list(self.protected_channels | self.auto_protected_channels)
        protected_info = []
        for ch_id in protected_list:
            ch = self.bot.get_channel(ch_id)
            if ch:
                protected_info.append(f"#{ch.name}")
            else:
                protected_info.append(str(ch_id))
        
        info_str = f" ({', '.join(protected_info)})" if protected_info else ""
        
        # Собираем данные ловушки бана для стартового сообщения
        trap_info = ""
        trap_channel_id = getattr(Config, 'AUTO_BAN_CHANNEL_ID', None)
        trap_role_id = getattr(Config, 'AUTO_BAN_ROLE_ID', None)
        if trap_channel_id and trap_role_id:
            trap_channel = self.bot.get_channel(trap_channel_id)
            trap_channel_name = f"#{trap_channel.name}" if trap_channel else f"ID {trap_channel_id}"
            
            trap_role_name = f"ID {trap_role_id}"
            server_id = getattr(Config, 'SERVER_ID', None)
            if server_id:
                guild = self.bot.get_guild(server_id)
                if guild:
                    role = guild.get_role(trap_role_id)
                    if role:
                        trap_role_name = role.name
            else:
                for guild in self.bot.guilds:
                    role = guild.get_role(trap_role_id)
                    if role:
                        trap_role_name = role.name
                        break
            
            trap_info = f" Ban trap: channel {trap_channel_name}, role {trap_role_name}."

        safe_create_task(send_to_any_log("info", 
            f"Channel protection module started. Total protected: {len(protected_list)}{info_str}. "
            f"Disable chat in voice: {'enabled' if self.disable_chat_in_voice else 'disabled'}. "
            f"Block sending instead of delete: {'enabled' if self.block_sending_instead_of_delete else 'disabled'}.{trap_info}",
            emoji=LogEmojis.STARTUP))

    async def reload_configs(self):
        """Горячая перезагрузка конфигураций защищенных каналов."""
        self._load_protected_channels()
        self._load_voice_channels()
        self.block_sending_instead_of_delete = getattr(Config, 'BLOCK_SENDING_INSTEAD_OF_DELETE', False)
        self.protect_everyone_here_mentions = getattr(Config, 'PROTECT_EVERYONE_HERE_MENTIONS', True)
        self.everyone_here_bypass_role_ids = getattr(Config, 'EVERYONE_HERE_BYPASS_ROLE_IDS', [])
        safe_create_task(self._apply_protection_permissions())
        safe_create_task(send_to_any_log("info", 
            "ChannelProtectionModule: protected channel configurations hot-reloaded", 
            emoji=LogEmojis.SUCCESS))

    def _save_voice_channels(self):
        """Сохраняет список голосовых каналов атомарно (через temp-файл → rename) и с блокировкой."""
        async def _do_save():
            try:
                await save_json_cache_async(self.voice_list_path, {"voice_channels": list(self.voice_channels)})
                await send_to_any_log("info",
                    f"Voice channels list saved to {self.voice_list_path}",
                    emoji=LogEmojis.INFO)
            except Exception as e:
                await send_to_any_log("error",
                    f"Error saving voice channels list: {e}",
                    emoji=LogEmojis.ERROR)
        safe_create_task(_do_save())
    
    async def stop(self):
        """Останавливает модуль защиты каналов."""
        if hasattr(self, 'enabled') and self.enabled:
            self.bot.remove_listener(self.on_message, 'on_message')
            self.bot.remove_listener(self.on_guild_channel_create, 'on_guild_channel_create')
            self.bot.remove_listener(self.on_guild_channel_delete, 'on_guild_channel_delete')
            if hasattr(self, "config_watcher") and self.config_watcher:
                try:
                    self.config_watcher.stop()
                except Exception:
                    pass
            
            safe_create_task(send_to_any_log("info", 
                "Channel protection module stopped", 
                emoji=LogEmojis.INFO))


async def setup(bot):
    cog = ChannelProtectionModule(bot)
    await bot.add_cog(cog)
    if hasattr(bot, 'app'):
        bot.app.protection_module = cog

