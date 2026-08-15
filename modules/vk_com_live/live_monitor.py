# modules/vk_com_live/live_monitor.py
from typing import Dict, Any, Optional, List
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from modules_utils.base_stream_monitor import BaseStreamMonitor
from modules_utils.generic_stream_database import GenericStreamDatabase

class VKComLiveMonitor(BaseStreamMonitor):
    """Монитор стримов (трансляций) для VK.com (группы и профили)."""

    def __init__(self, platform_name: str, config: Dict[str, Any], discord_bot, db_helper: Optional[GenericStreamDatabase] = None):
        super().__init__(platform_name, config, discord_bot, db_helper)
        self._owner_id: Optional[int] = None

    async def resolve_owner_id(self) -> Optional[int]:
        """Разрешает screen_name в числовой owner_id (отрицательный для групп, положительный для профилей)."""
        if self._owner_id is not None:
            return self._owner_id
            
        from modules_utils.vk_api_client import VKApiClient
        try:
            # Сначала проверяем, является ли platform_id уже числом
            val = int(self.platform_id)
            self._owner_id = val
            return val
        except (ValueError, TypeError):
            pass
            
        # Если это буквенный screen_name, задействуем VK API
        from modules_utils.vk_api_client import VKApiClient
        owner_id = await VKApiClient.get_group_id(self.platform_id, session=self.session)
        if owner_id is not None:
            self._owner_id = owner_id
            return owner_id
            
        return None

    async def fetch_current_streams(self) -> List[Dict[str, Any]]:
        """Получает список активных трансляций через VK API video.get."""
        owner_id = await self.resolve_owner_id()
        if owner_id is None:
            await send_to_any_log(
                "error",
                f"[VK.com Live] Failed to resolve ID for platform {self.platform_id}",
                emoji=LogEmojis.ERROR
            )
            return []
            
        from modules_utils.vk_api_client import VKApiClient
        try:
            streams = await VKApiClient.get_vk_com_live_streams(
                owner_id=owner_id,
                session=self.session
            )
            return streams
        except Exception as e:
            await send_to_any_log(
                "error",
                f"Error fetching VK.com live streams for {self.platform_id} (ID: {owner_id}): {e}",
                emoji=LogEmojis.ERROR
            )
            return []
