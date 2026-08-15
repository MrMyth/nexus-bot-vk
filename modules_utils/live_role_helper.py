# modules_utils/live_role_helper.py
import asyncio
import discord
from typing import Dict, Any, Optional, Set
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from settings.config import Config

class LiveRoleHelper:
    """
    Хелпер для управления ролями стримеров.
    Отслеживает активность стримеров по всем платформам, чтобы не снимать роль,
    пока идет эфир хотя бы на одной из них.
    """
    
    # { member_id: set(active_stream_ids) }
    _active_streamers: Dict[int, Set[str]] = {}

    @staticmethod
    async def manage_role(discord_bot, config: Dict[str, Any], platform_name: str, stream_id: str, assign: bool):
        """
        Выдает или забирает роль стримера.
        """
        # Стример (Discord User ID)
        streamer_id_raw = config.get("streamer_id")
        
        # Роль (приоритет: live_role_id -> глобальная DEFAULT_LIVE_ROLE_ID)
        role_id_raw = config.get("live_role_id")
        role_id = None
        
        if role_id_raw:
            try:
                role_id = int(role_id_raw)
            except (ValueError, TypeError):
                pass
        
        if role_id is None:
            role_id = Config.DEFAULT_LIVE_ROLE_ID

        if not streamer_id_raw:
            return
            
        if not role_id:
            return

        try:
            member_id = int(streamer_id_raw)
        except (ValueError, TypeError):
            return

            
        if assign:
            if member_id not in LiveRoleHelper._active_streamers:
                LiveRoleHelper._active_streamers[member_id] = set()
            LiveRoleHelper._active_streamers[member_id].add(f"{platform_name}:{stream_id}")
            
            await LiveRoleHelper._apply_role(discord_bot, member_id, role_id, True, platform_name)
        else:
            if member_id in LiveRoleHelper._active_streamers:
                LiveRoleHelper._active_streamers[member_id].discard(f"{platform_name}:{stream_id}")
                
                # Забираем роль только если больше нет активных стримов
                if not LiveRoleHelper._active_streamers[member_id]:
                    await LiveRoleHelper._apply_role(discord_bot, member_id, role_id, False, platform_name)
                    del LiveRoleHelper._active_streamers[member_id]

    @staticmethod
    async def _apply_role(discord_bot, member_id: int, role_id: int, assign: bool, platform: str):
        try:
            guild_id = Config.SERVER_ID
            if not guild_id:
                return

            guild = discord_bot.bot.get_guild(guild_id)
            if not guild:
                return

            member = guild.get_member(member_id)
            if not member:
                try:
                    member = await guild.fetch_member(member_id)
                except Exception:
                    return

            role = guild.get_role(role_id)
            if not role:
                return

            if assign:
                if role not in member.roles:
                    await member.add_roles(role, reason=f"Начало трансляции на {platform}")
                    await send_to_any_log("info", f"[{platform}] Выдана роль '{role.name}' пользователю {member.display_name}", emoji=LogEmojis.SUCCESS)
            else:
                if role in member.roles:
                    await member.remove_roles(role, reason=f"Завершение всех трансляций")
                    await send_to_any_log("info", f"[{platform}] Забрана роль '{role.name}' у пользователя {member.display_name}", emoji=LogEmojis.INFO)

        except Exception as e:
            await send_to_any_log("error", f"Ошибка LiveRoleHelper: {e}", emoji=LogEmojis.ERROR)
