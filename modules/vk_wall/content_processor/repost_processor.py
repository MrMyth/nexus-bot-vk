# modules/vk_wall/content_processor/repost_processor.py
import discord
from typing import Dict, Any, Optional
from modules.vk_wall.content_processor.repost_handler import RepostHandler

class RepostProcessor:
    @staticmethod
    async def create_repost_embed(repost_data: Dict[str, Any], group_config: Dict[str, Any], config: Dict[str, Any], post_url: str) -> Optional[discord.Embed]:
        """Создает EMBED для репоста, делегируя вызов RepostHandler."""
        return await RepostHandler._create_repost_embed(repost_data, group_config, config, post_url)
