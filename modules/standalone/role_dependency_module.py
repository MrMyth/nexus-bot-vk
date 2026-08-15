# modules/standalone/role_dependency_module.py

import json
import os
import asyncio
import discord
from typing import List, Dict, Any, Optional
from settings.config import Config
from settings.data_files import Files
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis, StartupEmojis
from constants.strings import BotStrings
from modules_utils.helpers import safe_create_task


from discord.ext import commands


class RoleDependencyModule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.running = False
        self.config_path = Files.ROLE_DEPENDENCY_CONFIG_PATH
        self.dependencies: List[Dict[str, Any]] = []
        self.compiled_dependencies: List[Dict[str, Any]] = []
        self.compiled_exclusive_dependencies: List[Dict[str, Any]] = []
        self._check_task: Optional[asyncio.Task] = None
        # (member_id, trigger_role_id) -> [Task, ...] — для отмены таймеров при снятии роли
        self._pending_delay_tasks: Dict[tuple, List[asyncio.Task]] = {}
        # Задача горячей перезагрузки конфига
        self._config_watch_task: Optional[asyncio.Task] = None

        # Очередь обновлений ролей для защиты от лимитов Discord API (Rate-Limit Buffering)
        self._role_queue: Dict[int, Dict[str, Any]] = {}
        self._queue_worker_task: Optional[asyncio.Task] = None
        self._queue_lock = asyncio.Lock()

    def load_config(self) -> List[Dict[str, Any]]:
        """Загружает конфигурацию зависимостей ролей."""
        if not os.path.exists(self.config_path):
            # Создаем пустой конфиг с примером, если файла нет
            example_config = [
                {
                    "trigger_role_id": 0,
                    "comment": "Пример (одиночный триггер): когда выдают роль 0, выдать роли 1 и 2, забрать 3",
                    "on_add": {
                        "remove_all_other_roles": False,
                        "add_roles": [1, 2],
                        "remove_roles": [3]
                    },
                    "on_remove": {
                        "add_roles": [3],
                        "remove_roles": [1, 2]
                    }
                },
                {
                    "trigger_role_id": "10 or 20 or 30",
                    "comment": "Пример (OR-триггер строкой): когда выдают ЛЮБУЮ из ролей 10, 20 или 30 — снять роль 99",
                    "on_add": {
                        "remove_all_other_roles": False,
                        "add_roles": [],
                        "remove_roles": [99]
                    },
                    "on_remove": {
                        "add_roles": [],
                        "remove_roles": []
                    }
                }
            ]
            try:
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(example_config, f, ensure_ascii=False, indent=4)
                return []
            except Exception as e:
                safe_create_task(send_to_any_log("error", f"Error creating role config example: {e}", emoji=LogEmojis.ERROR))
                return []

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
                if isinstance(rules, list):
                    # Filter out service comments, leaving only real rules
                    return [
                        r for r in rules
                        if isinstance(r, dict) and (
                            "trigger_role_id" in r or
                            "exclusive_roles" in r or
                            "mutually_exclusive_roles" in r or
                            "mutually_exclusive" in r or
                            "exclusive_group" in r
                        )
                    ]
                return []
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"Error loading role dependencies config: {e}", emoji=LogEmojis.ERROR))
            return []

    def compile_dependencies(self):
        """Прекомпилирует правила для сверхбыстрой проверки без регулярных кастов типов и парсинга."""
        compiled = []
        compiled_exclusive = []

        for dep in self.dependencies:
            # 1. Проверяем, является ли правило чистым правилом взаимоисключения
            exclusive_raw = (
                dep.get("exclusive_roles") or 
                dep.get("mutually_exclusive_roles") or 
                dep.get("mutually_exclusive") or 
                dep.get("exclusive_group")
            )
            if exclusive_raw:
                group_ids = self._resolve_trigger_ids(exclusive_raw)
                ordered_ids = self._resolve_trigger_ids_ordered(exclusive_raw)
                if len(group_ids) >= 2:
                    compiled_exclusive.append({
                        "group_ids": group_ids,
                        "ordered_ids": ordered_ids,
                        "raw_dep": dep
                    })
                continue

            # 2. Проверяем стандартное правило триггеров
            trigger_ids = self._resolve_trigger_ids(dep.get("trigger_role_id"))
            if not trigger_ids:
                continue

            # Дополнительно: если заданы взаимоисключающие роли через exclusive_with / incompatible_roles
            exc_with_raw = dep.get("exclusive_with") or dep.get("incompatible_roles")
            if exc_with_raw:
                exc_with_ids = self._resolve_trigger_ids(exc_with_raw)
                combined_group = trigger_ids | exc_with_ids
                ordered_combined = (
                    self._resolve_trigger_ids_ordered(dep.get("trigger_role_id")) +
                    self._resolve_trigger_ids_ordered(exc_with_raw)
                )
                if len(combined_group) >= 2:
                    compiled_exclusive.append({
                        "group_ids": combined_group,
                        "ordered_ids": ordered_combined,
                        "raw_dep": dep
                    })

            def compile_actions(actions_dict: dict) -> dict:
                if not actions_dict:
                    return {}
                
                add_ids = []
                for rid in actions_dict.get("add_roles", []):
                    if rid:
                        try:
                            add_ids.append(int(rid))
                        except (ValueError, TypeError):
                            pass
                
                remove_ids = []
                for rid in actions_dict.get("remove_roles", []):
                    if rid:
                        try:
                            remove_ids.append(int(rid))
                        except (ValueError, TypeError):
                            pass
                
                compiled_group = {
                    "add_roles_ids": add_ids,
                    "remove_roles_ids": remove_ids,
                    "remove_all_other_roles": bool(actions_dict.get("remove_all_other_roles", False)),
                    "delay_check": None
                }
                
                delay_cfg = actions_dict.get("delay_check")
                if delay_cfg:
                    missing_id = None
                    missing_raw = delay_cfg.get("missing_role_id")
                    if missing_raw:
                        try:
                            missing_id = int(missing_raw)
                        except (ValueError, TypeError):
                            pass
                    
                    required_id = None
                    required_raw = delay_cfg.get("required_role_id")
                    if required_raw:
                        try:
                            required_id = int(required_raw)
                        except (ValueError, TypeError):
                            pass
                    
                    delay_actions = compile_actions(delay_cfg)
                    
                    compiled_group["delay_check"] = {
                        "wait_seconds": float(delay_cfg.get("wait_seconds", 0)),
                        "missing_role_id": missing_id,
                        "required_role_id": required_id,
                        "actions": delay_actions
                    }
                
                return compiled_group

            compiled.append({
                "trigger_ids": trigger_ids,
                "required_role_id": int(dep.get("required_role_id")) if str(dep.get("required_role_id", "")).isdigit() else None,
                "required_role_ids": self._resolve_trigger_ids(dep.get("required_role_id")),
                "voice_or_role": bool(dep.get("voice_or_role", False) or dep.get("voice_or_trigger", False)),
                "on_add": compile_actions(dep.get("on_add", {})),
                "on_remove": compile_actions(dep.get("on_remove", {})),
                "on_voice_join": compile_actions(dep.get("on_voice_join", {})),
                "on_voice_leave": compile_actions(dep.get("on_voice_leave", {})),
                "raw_dep": dep
            })
        self.compiled_dependencies = compiled
        self.compiled_exclusive_dependencies = compiled_exclusive

    @staticmethod
    def _resolve_trigger_ids_ordered(trigger_raw) -> List[int]:
        """Возвращает упорядоченный список уникальных ID ролей из конфигурации."""
        if not trigger_raw:
            return []
        
        raw_list = []
        if isinstance(trigger_raw, list):
            raw_list = trigger_raw
        elif isinstance(trigger_raw, str):
            if " or " in trigger_raw.lower():
                raw_list = [p.strip() for p in trigger_raw.lower().split(" or ")]
            else:
                raw_list = [trigger_raw.strip()]
        else:
            raw_list = [trigger_raw]

        res = []
        seen = set()
        for item in raw_list:
            try:
                val = int(str(item).strip())
                if val not in seen:
                    seen.add(val)
                    res.append(val)
            except (ValueError, TypeError):
                pass
        return res

    @staticmethod
    def _resolve_trigger_ids(trigger_raw) -> set:
        """Преобразует trigger_role_id (int, список int или строку с 'or') в множество ID."""
        if not trigger_raw:
            return set()
        
        if isinstance(trigger_raw, list):
            return {int(r) for r in trigger_raw if r}
        
        if isinstance(trigger_raw, str):
            # Поддержка формата "ID1 or ID2 or ID3"
            if " or " in trigger_raw.lower():
                parts = [p.strip() for p in trigger_raw.lower().split(" or ")]
                return {int(p) for p in parts if p.replace('-', '').isdigit()}
            # Поддержка одиночной строки
            if trigger_raw.strip().replace('-', '').isdigit():
                return {int(trigger_raw.strip())}
                
        # Поддержка int или других типов, приводимых к int
        try:
            return {int(trigger_raw)}
        except (ValueError, TypeError):
            return set()

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Обработчик изменения ролей участника."""
        if not self.running:
            return

        # Проверяем, включена ли моментальная проверка при выдаче/изменении ролей
        if not getattr(Config, 'ROLE_DEPENDENCY_IMMEDIATE_CHECK', True):
            return

        # Проверяем, изменились ли роли
        if before.roles == after.roles:
            return

        before_role_ids = {role.id for role in before.roles}
        after_role_ids = {role.id for role in after.roles}

        added_roles = after_role_ids - before_role_ids
        removed_roles = before_role_ids - after_role_ids

        # --- Обработка взаимоисключающих ролей при добавлении ---
        if added_roles:
            for c_exc in self.compiled_exclusive_dependencies:
                group_ids = c_exc["group_ids"]
                newly_added_in_group = added_roles & group_ids
                if newly_added_in_group:
                    current_in_group = after_role_ids & group_ids
                    conflicting_roles = current_in_group - newly_added_in_group
                    if len(newly_added_in_group) > 1:
                        ordered_ids = c_exc["ordered_ids"]
                        kept = next((r for r in ordered_ids if r in newly_added_in_group), next(iter(newly_added_in_group)))
                        conflicting_roles.update(newly_added_in_group - {kept})
                    
                    if conflicting_roles:
                        strip_actions = {
                            "add_roles_ids": [],
                            "remove_roles_ids": list(conflicting_roles),
                            "remove_all_other_roles": False
                        }
                        comment = c_exc["raw_dep"].get("comment", "exclusive roles")
                        reason_msg = BotStrings.get("ROLE_DEP_MUTUAL_EXCLUDE_REASON", "снятие взаимоисключающих ролей ({comment})").format(comment=comment)
                        await self.apply_actions_compiled(
                            after,
                            strip_actions,
                            reason_msg,
                            trigger_role_ids=group_ids
                        )

        # Уведомление о отсутствии ролей
        if Config.ENABLE_NO_ROLE_NOTIFICATION and len(after.roles) <= 1 and not after.bot:
            # Убеждаемся, что роли именно были сняты
            if len(before.roles) > 1:
                async def _send_no_role_notification_with_delay(member_id: int, guild_id: int):
                    # Задержка, чтобы исключить ложные срабатывания при кике, бане или выходе с сервера
                    await asyncio.sleep(3)
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        return
                    member = guild.get_member(member_id)
                    if not member:
                        # Пользователь был кикнут, забанен или сам покинул сервер
                        return
                    if len(member.roles) > 1:
                        # Роли уже были назначены заново или не были полностью сняты
                        return
                    
                    channel_id = Config.GLOBAL_LOG_CHANNEL_ID
                    if channel_id:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            # Получаем роль для уведомления (например, админов)
                            notify_role_mention = ""
                            if Config.NO_ROLE_NOTIFICATION_ROLE_ID:
                                notify_role = guild.get_role(Config.NO_ROLE_NOTIFICATION_ROLE_ID)
                                if notify_role:
                                    notify_role_mention = f"{notify_role.mention} "

                            tmpl = BotStrings.get("ROLE_DEP_NO_ROLES_ALERT", "{emoji} {mention}У пользователя с ником **{name}** ({user_mention}) теперь **нет ролей**!")
                            msg = tmpl.format(
                                emoji=LogEmojis.WARNING,
                                mention=notify_role_mention,
                                name=member.display_name,
                                user_mention=member.mention
                            )
                            try:
                                await channel.send(msg)
                            except Exception as err:
                                await send_to_any_log("error", f"Error sending no-role notification: {err}", emoji=LogEmojis.ERROR)

                safe_create_task(_send_no_role_notification_with_delay(after.id, after.guild.id))

        for c_dep in self.compiled_dependencies:
            trigger_ids = c_dep["trigger_ids"]
            voice_or_role = c_dep.get("voice_or_role", False)
            required_role_ids = c_dep.get("required_role_ids", set())

            if required_role_ids:
                has_any_required = bool(required_role_ids & after_role_ids)
                has_removed_required = bool(required_role_ids & removed_roles)

                # 1. Если обязательная роль была снята у пользователя так, что не осталось ни одной обязательной роли
                if has_removed_required and not has_any_required:
                    # Забираем все целевые роли правила
                    roles_to_strip = set()
                    roles_to_strip.update(c_dep["on_add"].get("add_roles_ids", []))
                    roles_to_strip.update(c_dep["on_voice_join"].get("add_roles_ids", []))
                    roles_to_remove = [rid for rid in roles_to_strip if rid in after_role_ids]
                    if roles_to_remove:
                        strip_actions = {
                            "add_roles_ids": [],
                            "remove_roles_ids": roles_to_remove,
                            "remove_all_other_roles": False
                        }
                        await self.apply_actions_compiled(after, strip_actions, "снятие зависимой роли (сняты обязательные роли правила)", trigger_role_ids=trigger_ids)
                    continue

                # 2. Если у пользователя сейчас нет обязательной роли, полностью игнорируем любые триггеры правила
                if not has_any_required:
                    continue

                # 3. Если обязательная роль была только что добавлена
                if required_role_ids & added_roles:
                    # Перепроверяем правила для этого участника (это автоматически выдаст целевую роль, если он в войсе или имеет триггер)
                    await self.check_member_roles(after)
                    continue

            # Если одна из триггерных ролей была ДОБАВЛЕНА
            if trigger_ids & added_roles:
                matched = next(iter(trigger_ids & added_roles))
                actions = c_dep["on_add"]
                
                # Поддержка задержки проверки (Grace Period)
                delay_check = actions.get("delay_check")
                if delay_check:
                    task_key = (after.id, matched)
                    if task_key not in self._pending_delay_tasks:
                        self._pending_delay_tasks[task_key] = []
                    task = safe_create_task(self._process_delayed_check(after, delay_check, f"задержка после добавления {matched}", task_key=task_key))
                    self._pending_delay_tasks[task_key].append(task)
                
                await self.apply_actions_compiled(after, actions, f"добавление роли {matched}", trigger_role_ids=trigger_ids)

                # Дополнительно: если пользователь уже сидит в войсе, запускаем для него on_voice_join
                if voice_or_role:
                    voice_actions = c_dep.get("on_voice_join")
                    if voice_actions:
                        await self.apply_actions_compiled(after, voice_actions, f"добавление роли {matched} (trigger-or-voice режим)", trigger_role_ids=trigger_ids)
                else:
                    if after.voice and after.voice.channel:
                        voice_actions = c_dep.get("on_voice_join")
                        if voice_actions:
                            await self.apply_actions_compiled(after, voice_actions, f"добавление роли {matched} (пользователь в голосовом канале)", trigger_role_ids=trigger_ids)

            # Если одна из триггерных ролей была УДАЛЕНА
            if trigger_ids & removed_roles:
                matched = next(iter(trigger_ids & removed_roles))
                actions = c_dep["on_remove"]

                # Отменяем все pending delay-задачи, связанные с этой триггерной ролью для данного участника
                task_key = (after.id, matched)
                if task_key in self._pending_delay_tasks:
                    pending = self._pending_delay_tasks.pop(task_key)
                    cancelled_count = sum(1 for t in pending if not t.done() and t.cancel())
                    if cancelled_count > 0:
                        await send_to_any_log("info", f"RoleDependencyModule: cancelled {cancelled_count} delayed tasks for {after.display_name} (role {matched} removed)", emoji=LogEmojis.INFO)

                # Поддержка задержки проверки (Grace Period) при снятии
                delay_check = actions.get("delay_check")
                if delay_check:
                    task_key = (after.id, matched)
                    if task_key not in self._pending_delay_tasks:
                        self._pending_delay_tasks[task_key] = []
                    task = safe_create_task(self._process_delayed_check(after, delay_check, f"задержка после снятия {matched}", task_key=task_key))
                    self._pending_delay_tasks[task_key].append(task)

                await self.apply_actions_compiled(after, actions, f"снятие роли {matched}", trigger_role_ids=trigger_ids)

                # Дополнительно: если пользователь в войсе, но у него сняли триггерную роль, забираем войсовую роль
                if voice_or_role:
                    is_in_voice = after.voice is not None and after.voice.channel is not None
                    if not is_in_voice:
                        voice_actions = c_dep.get("on_voice_leave")
                        if voice_actions:
                            await self.apply_actions_compiled(after, voice_actions, f"снятие роли {matched} (пользователь вне войса, trigger-or-voice режим)", trigger_role_ids=trigger_ids)
                else:
                    if after.voice and after.voice.channel:
                        voice_actions = c_dep.get("on_voice_leave")
                        if voice_actions:
                            await self.apply_actions_compiled(after, voice_actions, f"снятие роли {matched} (очистка голосовой зависимости)", trigger_role_ids=trigger_ids)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Обработчик изменения состояния голосового канала участника."""
        if not self.running:
            return
        if member.bot:
            return

        # Проверяем переход в/из голосового канала
        was_in_voice = before.channel is not None
        is_in_voice = after.channel is not None

        if was_in_voice == is_in_voice:
            # Не было изменения факта нахождения в войсе (например, просто мут или стрим)
            return

        current_role_ids = {role.id for role in member.roles}

        for c_dep in self.compiled_dependencies:
            trigger_ids = c_dep["trigger_ids"]
            voice_or_role = c_dep.get("voice_or_role", False)
            required_role_ids = c_dep.get("required_role_ids", set())
            
            # Проверяем обязательную роль на уровне правила
            if required_role_ids and not (required_role_ids & current_role_ids):
                continue

            # Проверяем, есть ли у пользователя триггерная роль
            has_trigger = bool(trigger_ids & current_role_ids)
            
            if is_in_voice:
                # Зашел в голосовой канал
                if has_trigger or voice_or_role:
                    actions = c_dep.get("on_voice_join")
                    if actions:
                        await self.apply_actions_compiled(member, actions, "вход в голосовой канал с триггерной ролью" if has_trigger else "вход в голосовой канал (voice_or_role)", trigger_role_ids=trigger_ids)
            else:
                # Вышел из голосового канала
                if voice_or_role:
                    if not has_trigger:
                        actions = c_dep.get("on_voice_leave")
                        if actions:
                            await self.apply_actions_compiled(member, actions, "выход из голосового канала без триггерной роли (voice_or_role)", trigger_role_ids=trigger_ids)
                else:
                    actions = c_dep.get("on_voice_leave")
                    if actions:
                        await self.apply_actions_compiled(member, actions, "выход из голосового канала", trigger_role_ids=trigger_ids)

    async def _process_delayed_check(self, member: discord.Member, delay_config: Dict[str, Any], context: str, task_key: tuple = None):
        """Выполняет проверку через заданный интервал времени с использованием скомпилированных данных."""
        try:
            wait_seconds = delay_config.get("wait_seconds", 0.0)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            
            # Переполучаем участника, чтобы данные были актуальными
            guild = member.guild
            member = guild.get_member(member.id)
            if not member:
                return

            missing_role_id = delay_config.get("missing_role_id")
            required_role_id = delay_config.get("required_role_id")
            
            should_apply = False
            role_ids = {r.id for r in member.roles}
            
            # Если указана missing_role_id — условие срабатывает, если этой роли НЕТ
            if missing_role_id is not None:
                if missing_role_id not in role_ids:
                    should_apply = True
            
            # Если указана required_role_id — условие срабатывает, если эта роль ЕСТЬ
            elif required_role_id is not None:
                if required_role_id in role_ids:
                    should_apply = True
            
            # Если не указано условий — просто применяем действия
            else:
                should_apply = True

            if should_apply:
                await self.apply_actions_compiled(member, delay_config["actions"], f"{context} (интервал {wait_seconds}с)")
        except asyncio.CancelledError:
            # Задача была отменена (триггерная роль снята до срабатывания) — это штатная ситуация
            raise
        finally:
            # Самоочистка из словаря после завершения (успешного или отменённого)
            if task_key and task_key in self._pending_delay_tasks:
                current = asyncio.current_task()
                tasks = self._pending_delay_tasks[task_key]
                if current in tasks:
                    tasks.remove(current)
                if not tasks:
                    self._pending_delay_tasks.pop(task_key, None)

    async def apply_actions(self, member: discord.Member, actions: Dict[str, Any], reason: str, trigger_role_ids: set = None):
        """Сохранено для обратной совместимости, оборачивает вызов в компиляцию на лету."""
        compiled_actions = {
            "add_roles_ids": [int(rid) for rid in actions.get("add_roles", []) if str(rid).isdigit()],
            "remove_roles_ids": [int(rid) for rid in actions.get("remove_roles", []) if str(rid).isdigit()],
            "remove_all_other_roles": bool(actions.get("remove_all_other_roles", False))
        }
        await self.apply_actions_compiled(member, compiled_actions, reason, trigger_role_ids)

    async def apply_actions_compiled(self, member: discord.Member, actions: Dict[str, Any], reason: str, trigger_role_ids: set = None, _chain_depth: int = 0):
        """Добавляет намеченные действия (изменение ролей) в буферизованную очередь для защиты от лимитов Discord API."""
        if member.bot:
            return

        roles_to_add_ids = actions.get("add_roles_ids", [])
        roles_to_remove_ids = actions.get("remove_roles_ids", [])
        remove_all_others = actions.get("remove_all_other_roles", False)

        if not roles_to_add_ids and not roles_to_remove_ids and not remove_all_others:
            return

        current_role_ids = {role.id for role in member.roles}

        # БЫСТРЫЙ ВЫХОД: Пытаемся оценить, нужны ли какие-то изменения вообще
        if not remove_all_others:
            needs_add = any(rid not in current_role_ids for rid in roles_to_add_ids)
            needs_remove = any(rid in current_role_ids for rid in roles_to_remove_ids)
            if not needs_add and not needs_remove:
                return

        # Добавляем в буферизованную очередь
        async with self._queue_lock:
            member_id = member.id
            if member_id not in self._role_queue:
                self._role_queue[member_id] = {
                    "member": member,
                    "roles_to_add_ids": set(),
                    "roles_to_remove_ids": set(),
                    "remove_all_other_roles": False,
                    "reasons": [],
                    "trigger_role_ids": set(),
                    "max_chain_depth": 0
                }
            
            entry = self._role_queue[member_id]
            # Всегда держим актуальный объект участника
            entry["member"] = member
            entry["roles_to_add_ids"].update(roles_to_add_ids)
            entry["roles_to_remove_ids"].update(roles_to_remove_ids)
            if remove_all_others:
                entry["remove_all_other_roles"] = True
            entry["reasons"].append(reason)
            if trigger_role_ids:
                entry["trigger_role_ids"].update(trigger_role_ids)
            entry["max_chain_depth"] = max(entry["max_chain_depth"], _chain_depth)

            # Санитарное разрешение коллизий (если одну и ту же роль просят выдать и забрать одновременно)
            # В этом случае приоритет отдается выдаче роли
            entry["roles_to_remove_ids"].difference_update(entry["roles_to_add_ids"])

    async def _queue_worker_loop(self):
        """Фоновый воркер для постепенного и безопасного применения изменений ролей."""
        await self.bot.wait_until_ready()
        while self.running:
            try:
                member_id = None
                entry = None
                
                # Извлекаем следующего участника из очереди
                async with self._queue_lock:
                    if self._role_queue:
                        member_id = next(iter(self._role_queue))
                        entry = self._role_queue.pop(member_id)
                
                if entry:
                    await self._execute_queued_update(entry)
                
                # Даем Discord API передышку в 150 мс перед следующим изменением для защиты от рейт-лимитов
                await asyncio.sleep(0.15)
            except asyncio.CancelledError:
                break
            except Exception as e:
                try:
                    await send_to_any_log("error", f"RoleDependencyModule role queue worker error: {e}", emoji=LogEmojis.ERROR)
                except Exception:
                    pass
                await asyncio.sleep(1.0)

    async def _execute_queued_update(self, entry: Dict[str, Any]):
        """Выполняет пакетное изменение ролей в ОДИН атомарный API-запрос к Discord через api edit."""
        member = entry["member"]
        guild = member.guild
        
        # Получаем свежие данные участника, чтобы избежать конфликтов и затирания сторонних ролей
        updated_member = guild.get_member(member.id)
        if not updated_member:
            try:
                updated_member = await guild.fetch_member(member.id)
            except Exception:
                return # Участник вышел с сервера
                
        member = updated_member
        roles_to_add_ids = entry["roles_to_add_ids"]
        roles_to_remove_ids = entry["roles_to_remove_ids"]
        remove_all_others = entry["remove_all_other_roles"]
        normalized_trigger_ids = entry["trigger_role_ids"]
        
        new_roles = []
        added_roles = []
        removed_roles = []
        
        # Предварительно находим объекты ролей для выдачи
        role_objects_to_add = {}
        for r_id in roles_to_add_ids:
            role = guild.get_role(r_id)
            if role:
                role_objects_to_add[r_id] = role

        bot_top_role = guild.me.top_role if (guild.me and hasattr(guild.me, 'top_role')) else None

        for role in member.roles:
            if role.is_default():
                new_roles.append(role)
                continue
                
            # Проверяем, можем ли мы физически управлять (снимать) этой ролью
            # Роли, которые мы не можем снимать, мы обязаны оставить, чтобы не получить Forbidden
            can_manage = True
            if bot_top_role:
                can_manage = (role < bot_top_role)
            if role.managed or role.is_premium_subscriber():
                can_manage = False

            if remove_all_others:
                # Оставляем роль только если ее нужно выдать по ходу,
                # либо если она является триггером правила (чтобы не снять триггерную роль, инициировавшую всё),
                # либо если мы физически не можем её снять (чтобы избежать Forbidden)
                if role.id in roles_to_add_ids or role.id in normalized_trigger_ids or not can_manage:
                    new_roles.append(role)
                else:
                    removed_roles.append(role)
            else:
                if role.id in roles_to_remove_ids and can_manage:
                    removed_roles.append(role)
                else:
                    new_roles.append(role)
                    
        # Добавляем новые роли, которых еще нет у участника
        for r_id, role in role_objects_to_add.items():
            if role not in new_roles:
                new_roles.append(role)
                added_roles.append(role)
                
        # Если ролевой состав не изменился, запрос делать не нужно
        old_ids = {r.id for r in member.roles}
        new_ids = {r.id for r in new_roles}
        if old_ids == new_ids:
            return
            
        try:
            # Устраняем дубликаты причин и собираем audit log
            unique_reasons = list(set(entry["reasons"]))
            combined_reason = ", ".join(unique_reasons)
            
            # Атомарный апдейт в один HTTP-запрос!
            await member.edit(roles=new_roles, reason=f"RoleDependencyModule: {combined_reason}")
            
            # Логируем результаты
            if added_roles:
                await send_to_any_log("info", f"Added roles {', '.join([r.name for r in added_roles])} to member {member.display_name} ({combined_reason})", emoji=LogEmojis.INFO)
            if removed_roles:
                await send_to_any_log("info", f"Removed roles {', '.join([r.name for r in removed_roles])} from member {member.display_name} ({combined_reason})", emoji=LogEmojis.INFO)
                
            # Запускаем цепочку последующих зависимостей (один раз на все изменения)
            safe_create_task(self._delayed_chain_check(member, _depth=entry["max_chain_depth"]))
            
        except discord.Forbidden:
            await send_to_any_log("error", f"Insufficient permissions to edit roles for {member.display_name}", emoji=LogEmojis.ERROR)
        except Exception as e:
            await send_to_any_log("error", f"Error editing roles for {member.display_name}: {e}", emoji=LogEmojis.ERROR)

    async def _delayed_chain_check(self, member: discord.Member, _depth: int = 0):
        """Перепроверяет правила для участника после паузы для обеспечения цепочек зависимостей."""
        if _depth >= 5:
            await send_to_any_log("warning",
                f"RoleDependencyModule: max chain depth reached ({_depth}) for {member.display_name}. Possible rule conflict.",
                emoji=LogEmojis.WARNING)
            return
        await asyncio.sleep(1.5)  # Даем Discord время обновить данные
        try:
            guild = member.guild
            # Пытаемся получить свежие данные участника
            latest_member = guild.get_member(member.id)
            if not latest_member:
                latest_member = await guild.fetch_member(member.id)
            
            if latest_member:
                await self.check_member_roles(latest_member, _chain_depth=_depth + 1)
        except Exception as e:
            await send_to_any_log("warning", f"RoleDependencyModule: role check chain error for {member.display_name}: {e}", emoji=LogEmojis.WARNING)

    async def check_member_roles(self, member: discord.Member, _chain_depth: int = 0):
        """Проверяет роли участника на соответствие всем зависимостям."""
        current_role_ids = {role.id for role in member.roles}
        is_in_voice = member.voice is not None and member.voice.channel is not None
        
        # --- Проверка взаимоисключающих ролей при полной/периодической проверке ---
        for c_exc in self.compiled_exclusive_dependencies:
            group_ids = c_exc["group_ids"]
            present_in_group = group_ids & current_role_ids
            if len(present_in_group) > 1:
                ordered_ids = c_exc["ordered_ids"]
                winner = next((r for r in ordered_ids if r in present_in_group), next(iter(present_in_group)))
                roles_to_strip = present_in_group - {winner}
                if roles_to_strip:
                    strip_actions = {
                        "add_roles_ids": [],
                        "remove_roles_ids": list(roles_to_strip),
                        "remove_all_other_roles": False
                    }
                    comment = c_exc["raw_dep"].get("comment", "взаимоисключающие роли")
                    await self.apply_actions_compiled(
                        member,
                        strip_actions,
                        f"разрешение конфликта взаимоисключающих ролей: сохранена роль ID:{winner} ({comment})",
                        trigger_role_ids=group_ids,
                        _chain_depth=_chain_depth
                    )
                    current_role_ids -= roles_to_strip

        for c_dep in self.compiled_dependencies:
            trigger_ids = c_dep["trigger_ids"]
            voice_or_role = c_dep.get("voice_or_role", False)
            required_role_ids = c_dep.get("required_role_ids", set())

            # Проверяем обязательную роль на уровне правила
            if required_role_ids and not (required_role_ids & current_role_ids):
                # Если у пользователя нет обязательной роли, у него не должно быть никаких целевых ролей этого правила
                roles_to_strip = set()
                roles_to_strip.update(c_dep["on_add"].get("add_roles_ids", []))
                roles_to_strip.update(c_dep["on_voice_join"].get("add_roles_ids", []))
                roles_to_remove = [rid for rid in roles_to_strip if rid in current_role_ids]
                if roles_to_remove:
                    strip_actions = {
                        "add_roles_ids": [],
                        "remove_roles_ids": roles_to_remove,
                        "remove_all_other_roles": False
                    }
                    await self.apply_actions_compiled(member, strip_actions, "снятие роли (отсутствует обязательная роль правила)", trigger_role_ids=trigger_ids, _chain_depth=_chain_depth)
                continue

            has_trigger = bool(trigger_ids & current_role_ids)

            if voice_or_role:
                # В режиме voice_or_role:
                # 1. on_add / on_remove основаны строго на наличии самой триггерной роли.
                if has_trigger:
                    actions = c_dep["on_add"]
                    await self.apply_actions_compiled(member, actions, "периодическая проверка (наличие триггера, voice_or_role)", trigger_role_ids=trigger_ids, _chain_depth=_chain_depth)
                else:
                    actions = c_dep["on_remove"]
                    await self.apply_actions_compiled(member, actions, "периодическая проверка (отсутствие триггера, voice_or_role)", trigger_role_ids=trigger_ids, _chain_depth=_chain_depth)

                # 2. on_voice_join / on_voice_leave срабатывают по условию OR: (has_trigger или is_in_voice)
                if has_trigger or is_in_voice:
                    voice_actions = c_dep.get("on_voice_join")
                    if voice_actions:
                        await self.apply_actions_compiled(member, voice_actions, "периодическая проверка (в голосовом канале или триггерная роль)", trigger_role_ids=trigger_ids, _chain_depth=_chain_depth)
                else:
                    voice_actions = c_dep.get("on_voice_leave")
                    if voice_actions:
                        await self.apply_actions_compiled(member, voice_actions, "периодическая проверка (выход: нет триггера и не в войсе)", trigger_role_ids=trigger_ids, _chain_depth=_chain_depth)
            else:
                # Стандартный режим
                if has_trigger:
                    actions = c_dep["on_add"]
                    await self.apply_actions_compiled(member, actions, "периодическая проверка (наличие триггера)", trigger_role_ids=trigger_ids, _chain_depth=_chain_depth)
                    
                    # Проверка войсовой роли
                    if is_in_voice:
                        voice_actions = c_dep.get("on_voice_join")
                        if voice_actions:
                            await self.apply_actions_compiled(member, voice_actions, "периодическая проверка (в голосовом канале)", trigger_role_ids=trigger_ids, _chain_depth=_chain_depth)
                    else:
                        voice_actions = c_dep.get("on_voice_leave")
                        if voice_actions:
                            await self.apply_actions_compiled(member, voice_actions, "периодическая проверка (не в голосовом канале)", trigger_role_ids=trigger_ids, _chain_depth=_chain_depth)
                else:
                    actions = c_dep["on_remove"]
                    await self.apply_actions_compiled(member, actions, "периодическая проверка (отсутствие триггера)", trigger_role_ids=trigger_ids, _chain_depth=_chain_depth)
                    
                    # Если триггера нет, но пользователь в войсе или нет — на всякий случай очищаем/применяем on_voice_leave
                    voice_actions = c_dep.get("on_voice_leave")
                    if voice_actions:
                        await self.apply_actions_compiled(member, voice_actions, "периодическая проверка (отсутствие триггера, очистка голосовой)", trigger_role_ids=trigger_ids, _chain_depth=_chain_depth)

    async def validate_rules_against_guild(self, guild: discord.Guild):
        """Проверяет настройки правил зависимостей ролей на предмет несуществующих ролей на сервере дс."""
        if not guild:
            return
            
        guild_role_ids = {role.id for role in guild.roles}
        warnings = []
        
        for idx, dep in enumerate(self.dependencies, 1):
            comment = dep.get("comment", "")
            rule_name = f"Правило #{idx} ({comment[:30]})" if comment else f"Правило #{idx}"
            
            # 0. Проверяем правило взаимоисключающих ролей
            exclusive_raw = (
                dep.get("exclusive_roles") or 
                dep.get("mutually_exclusive_roles") or 
                dep.get("mutually_exclusive") or 
                dep.get("exclusive_group")
            )
            if exclusive_raw:
                group_ids = self._resolve_trigger_ids(exclusive_raw)
                for tid in group_ids:
                    if tid not in guild_role_ids:
                        warnings.append(f"• {rule_name}: Роль из группы взаимоисключения с ID `{tid}` отсутствует на сервере!")
                continue

            # 1. Проверяем триггеры
            trigger_raw = dep.get("trigger_role_id")
            trigger_ids = self._resolve_trigger_ids(trigger_raw)
            for tid in trigger_ids:
                if tid not in guild_role_ids:
                    warnings.append(f"• {rule_name}: Триггерная роль с ID `{tid}` отсутствует на сервере!")
            
            # 2. Проверяем обязательную роль
            req_raw = dep.get("required_role_id")
            if req_raw:
                req_ids = self._resolve_trigger_ids(req_raw)
                for req_id in req_ids:
                    if req_id not in guild_role_ids:
                        warnings.append(f"• {rule_name}: Обязательная роль (required) с ID `{req_id}` отсутствует на сервере!")
                    
            # 3. Проверяем действия
            for act_name, group in [("on_add", dep.get("on_add", {})), 
                                    ("on_remove", dep.get("on_remove", {})), 
                                    ("on_voice_join", dep.get("on_voice_join", {})), 
                                    ("on_voice_leave", dep.get("on_voice_leave", {}))]:
                if not group:
                    continue
                # Нам интересны add_roles и remove_roles
                for pid in group.get("add_roles", []):
                    if pid and str(pid).isdigit():
                        if int(pid) not in guild_role_ids:
                            warnings.append(f"• {rule_name} (блок {act_name}): Ожидаемая к выдаче роль с ID `{pid}` отсутствует на сервере!")
                for pid in group.get("remove_roles", []):
                    if pid and str(pid).isdigit():
                        if int(pid) not in guild_role_ids:
                            warnings.append(f"• {rule_name} (блок {act_name}): Ожидаемая к снятию роль с ID `{pid}` отсутствует на сервере!")
                            
        if warnings:
            warn_msg = f"{LogEmojis.WARNING} **RoleDependencyModule: Detected rule configuration issues!**\n" + "\n".join(warnings[:15])
            if len(warnings) > 15:
                warn_msg += f"\n*And {len(warnings) - 15} more warnings...*"
            await send_to_any_log("warning", warn_msg, emoji=LogEmojis.WARNING)

    async def run_full_check(self):
        """Принудительно выполняет полную проверку участников во всех отслеживаемых гильдиях."""
        try:
            guild = None
            if Config.SERVER_ID:
                guild = self.bot.get_guild(Config.SERVER_ID)
                if guild:
                    try:
                        await guild.fetch_roles()
                        # Запускаем проверку утерянных ролей
                        await self.validate_rules_against_guild(guild)
                    except Exception as e:
                        await send_to_any_log("warning", f"RoleDependencyModule: failed to fetch guild roles: {e}", emoji=LogEmojis.WARNING)
            
            # Логируем пример одного из правил для контекста
            if self.dependencies:
                example_rule = self.format_rule(self.dependencies[0], guild)
                await send_to_any_log("info", f"{StartupEmojis.BLUE_DIAMOND} Example rule: {example_rule}", emoji=LogEmojis.INFO, targets=["console", "file"])

            for target_guild in self.bot.guilds:
                if Config.SERVER_ID and target_guild.id != Config.SERVER_ID:
                    continue
                
                # Оптимизация получения участников:
                if self.bot.intents.members and Config.ENABLE_GUILD_CHUNKING and not target_guild.chunked:
                    try:
                        await target_guild.chunk()
                    except Exception as e:
                        await send_to_any_log("info", f"RoleDependencyModule: Error during guild member chunking: {e}. Using fetch_members.", emoji=LogEmojis.INFO, targets=["console"])
                
                if target_guild.members and len(target_guild.members) > 1:
                    members_to_check = target_guild.members
                else:
                    members_to_check = []
                    async for m in target_guild.fetch_members(limit=None):
                        members_to_check.append(m)
                
                # Проверяем участников
                for idx, member in enumerate(members_to_check):
                    if not self.running:
                        break
                    await self.check_member_roles(member)
                    
                    # Даем передышку циклу событий asyncio каждые 100 проверок, а в остальных случаях моментально уступаем (0 секунд)
                    if idx % 100 == 0:
                        await asyncio.sleep(0.1)
                    else:
                        await asyncio.sleep(0)
                        
            await send_to_any_log("info", "RoleDependencyModule: Full member check completed.", emoji=LogEmojis.SUCCESS)
        except Exception as e:
            await send_to_any_log("error", f"Error during full member check in RoleDependencyModule: {e}", emoji=LogEmojis.ERROR)

    async def _background_check_task(self):
        """Фоновая задача для периодической проверки всех участников."""
        await self.bot.wait_until_ready()
        
        while self.running:
            interval = Config.ROLE_DEPENDENCY_CHECK_INTERVAL
            if not interval or interval <= 0:
                await asyncio.sleep(3600)
                continue

            await send_to_any_log("info", f"RoleDependencyModule: Starting periodic member check (active rules: {len(self.dependencies)})", emoji=LogEmojis.INFO)
            await self.run_full_check()
            
            # Ждем интервал ПОСЛЕ завершения проверки
            await asyncio.sleep(Config.ROLE_DEPENDENCY_CHECK_INTERVAL)

    def format_rule(self, dep: Dict[str, Any], guild: Optional[discord.Guild] = None) -> str:
        """Форматирует правило в человекочитаемый вид."""
        def get_role_name(r_id):
            if not guild:
                return f"ID:{r_id}"
            try:
                role = guild.get_role(int(r_id))
                return f"@{role.name}" if role else f"ID:{r_id}"
            except Exception:
                return f"ID:{r_id}"

        exclusive_raw = (
            dep.get("exclusive_roles") or 
            dep.get("mutually_exclusive_roles") or 
            dep.get("mutually_exclusive") or 
            dep.get("exclusive_group")
        )
        if exclusive_raw:
            group_ids = self._resolve_trigger_ids(exclusive_raw)
            roles_str = " ↔ ".join([get_role_name(rid) for rid in group_ids]) if group_ids else str(exclusive_raw)
            return f"Взаимоисключающие роли ({roles_str}): выдача любой из них автоматически снимает остальные"

        trigger_raw = dep.get("trigger_role_id")
        trigger_ids = self._resolve_trigger_ids(trigger_raw)

        triggers_str = " или ".join([get_role_name(tid) for tid in trigger_ids])
        
        def format_action_group(action_group: Dict[str, Any]) -> str:
            if not action_group:
                return ""
                
            res_actions = []
            add_roles = action_group.get("add_roles", [])
            remove_roles = action_group.get("remove_roles", [])
            remove_all_others = action_group.get("remove_all_other_roles", False)
            delay_check = action_group.get("delay_check")

            if remove_all_others:
                res_actions.append("забрать ВСЕ остальные роли")
            
            if add_roles:
                res_actions.append(f"выдать {', '.join([get_role_name(rid) for rid in add_roles])}")
            
            if remove_roles and not remove_all_others:
                res_actions.append(f"забрать {', '.join([get_role_name(rid) for rid in remove_roles])}")
            
            if delay_check:
                wait = delay_check.get("wait_seconds", 0)
                delay_actions = format_action_group(delay_check)
                cond = ""
                if delay_check.get("missing_role_id"):
                    cond = f" (если НЕТ {get_role_name(delay_check['missing_role_id'])})"
                elif delay_check.get("required_role_id"):
                    cond = f" (если ЕСТЬ {get_role_name(delay_check['required_role_id'])})"
                
                res_actions.append(f"через {wait}с{cond} → {delay_actions or 'ничего'}")
                
            return ", ".join(res_actions)

        on_add_str = format_action_group(dep.get("on_add", {}))
        on_remove_str = format_action_group(dep.get("on_remove", {}))
        on_voice_join_str = format_action_group(dep.get("on_voice_join", {}))
        on_voice_leave_str = format_action_group(dep.get("on_voice_leave", {}))
        
        voice_or_role = bool(dep.get("voice_or_role", False) or dep.get("voice_or_trigger", False))
        
        parts = []
        if on_add_str:
            parts.append(f"При получении → {on_add_str}")
        if on_remove_str:
            parts.append(f"При снятии → {on_remove_str}")
        if on_voice_join_str:
            prefix = "При входе в войс/роли" if voice_or_role else "При входе в войс"
            parts.append(f"{prefix} → {on_voice_join_str}")
        if on_voice_leave_str:
            prefix = "При выходе/снятии" if voice_or_role else "При выходе из войса"
            parts.append(f"{prefix} → {on_voice_leave_str}")
            
        required_raw = dep.get("required_role_id")
        required_ids = self._resolve_trigger_ids(required_raw)
        if required_ids:
            req_names = " или ".join([get_role_name(rid) for rid in required_ids])
            required_suffix = f" [требуется {req_names}]"
        else:
            required_suffix = ""

        if not parts:
            return f"{triggers_str}{required_suffix}: пустое правило"
            
        return f"{triggers_str}{required_suffix}: {' | '.join(parts)}"

    async def start(self):
        """Запускает модуль."""
        if self.running:
            return
        
        self.dependencies = self.load_config()
        self.compile_dependencies()
        if not self.dependencies:
            await send_to_any_log("info", "RoleDependencyModule: config is empty or not loaded", emoji=LogEmojis.INFO)
            return
        
        self.bot.add_listener(self.on_member_update, 'on_member_update')
        self.bot.add_listener(self.on_voice_state_update, 'on_voice_state_update')
        self.bot.add_listener(self._on_member_remove, 'on_member_remove')
        self.running = True

        # Запуск фонового воркера очереди ролей для защиты от лимитов Discord API
        self._queue_worker_task = safe_create_task(self._queue_worker_loop())

        # Логируем правила при запуске (пытаемся найти гильдию для имен ролей)
        guild = None
        if Config.SERVER_ID:
            guild = self.bot.get_guild(Config.SERVER_ID)
            if not guild:
                try:
                    guild = await self.bot.fetch_guild(Config.SERVER_ID)
                except Exception as e:
                    await send_to_any_log("warning", f"RoleDependencyModule: failed to fetch guild for rule logging: {e}", emoji=LogEmojis.WARNING)
            
            if guild:
                try:
                    # Предварительно загружаем все роли, чтобы имена были доступны в логах
                    await guild.fetch_roles()
                except Exception as e:
                    await send_to_any_log("warning", f"RoleDependencyModule: failed to load guild roles: {e}", emoji=LogEmojis.WARNING)
        
        rules_log = []
        for dep in self.dependencies:
            rules_log.append(self.format_rule(dep, guild))
        
        if rules_log:
            await send_to_any_log("info", "RoleDependencyModule: Loaded the following rules:\n" + "\n".join([f"{StartupEmojis.BLUE_DIAMOND} {r}" for r in rules_log]), emoji=LogEmojis.INFO)

        # Запуск фоновой задачи, если включена в Config
        if Config.ROLE_DEPENDENCY_CHECK_INTERVAL > 0:
            self._check_task = safe_create_task(self._background_check_task())
            msg_interval = f" (periodic check: every {Config.ROLE_DEPENDENCY_CHECK_INTERVAL} sec)"
        else:
            msg_interval = ""

        # Горячая перезагрузка конфига при изменении файла
        self._config_watch_task = safe_create_task(self._watch_config_loop())

        await send_to_any_log("info", f"Role dependency module started (loaded rules: {len(self.dependencies)}){msg_interval}", emoji=LogEmojis.STARTUP)

    async def _watch_config_loop(self):
        """Следит за изменением role_dependencies.json и перезагружает конфиг при обнаружении."""
        try:
            last_mtime = os.path.getmtime(self.config_path) if os.path.exists(self.config_path) else 0
        except OSError:
            last_mtime = 0

        while self.running:
            await asyncio.sleep(5)
            try:
                if os.path.exists(self.config_path):
                    current_mtime = os.path.getmtime(self.config_path)
                    if current_mtime != last_mtime:
                        last_mtime = current_mtime
                        await self.reload_config()
            except Exception as e:
                await send_to_any_log("warning", f"RoleDependencyModule: error checking config file changes: {e}", emoji=LogEmojis.WARNING)

    async def reload_config(self):
        """Перезагружает конфигурацию зависимостей ролей без перезапуска бота."""
        try:
            new_deps = await asyncio.to_thread(self.load_config)
            self.dependencies = new_deps
            self.compile_dependencies()
            await send_to_any_log("info", f"RoleDependencyModule: config hot-reloaded, active rules: {len(self.dependencies)}", emoji=LogEmojis.SUCCESS)
            # Принудительно запускаем перепроверку всех участников, чтобы новые правила применились сразу
            safe_create_task(self.run_full_check())
        except Exception as e:
            await send_to_any_log("error", f"RoleDependencyModule: config hot-reload error: {e}", emoji=LogEmojis.ERROR)

    async def _on_member_remove(self, member: discord.Member):
        """Отменяет все pending delay-задачи для участника, покинувшего сервер."""
        member_id = member.id
        cancelled = 0
        for key in list(self._pending_delay_tasks.keys()):
            if key[0] == member_id:
                tasks = self._pending_delay_tasks.pop(key, [])
                for task in tasks:
                    if not task.done():
                        task.cancel()
                        cancelled += 1
        if cancelled > 0:
            await send_to_any_log("info",
                f"Cancelled {cancelled} pending tasks for departed member {member.display_name}",
                emoji=LogEmojis.INFO)

    async def stop(self):
        """Останавливает модуль."""
        self.running = False
        
        if self._check_task:
            self._check_task.cancel()
            self._check_task = None

        if self._queue_worker_task:
            self._queue_worker_task.cancel()
            self._queue_worker_task = None

        if self._config_watch_task:
            self._config_watch_task.cancel()
            self._config_watch_task = None

        # Отменяем все оставшиеся отложенные задачи
        for key, tasks in list(self._pending_delay_tasks.items()):
            for t in tasks:
                if not t.done():
                    t.cancel()
        self._pending_delay_tasks.clear()

        self.bot.remove_listener(self.on_member_update, 'on_member_update')
        self.bot.remove_listener(self.on_voice_state_update, 'on_voice_state_update')
        self.bot.remove_listener(self._on_member_remove, 'on_member_remove')
        await send_to_any_log("info", "Role dependency module stopped", emoji=LogEmojis.INFO)


async def setup(bot):
    cog = RoleDependencyModule(bot)
    await bot.add_cog(cog)
    if hasattr(bot, 'app'):
        bot.app.role_dependency_module = cog

