# modules/vk_wall/content_processor/poll_processor.py
import discord
from typing import Dict, Any, Optional
from constants.emojis import EmojisFields, Emojis
from constants.base import ContentTypes
from constants.strings import BotStrings
from modules.vk_wall.content_processor.embed_builder import EmbedBuilder
from modules_utils.random_resolver import resolve_random_value

class PollProcessor:
    @staticmethod
    async def create_poll_embed(
        poll: Dict[str, Any],
        group_config: Dict[str, Any],
        config: Dict[str, Any],
        post_url: str,
        index: int = 1,
        total: int = 1
    ) -> Optional[discord.Embed]:
        """Форматирует данные опроса во вложении и возвращает Discord-совместимый Embed."""
        embed = await EmbedBuilder._create_base_embed(group_config, ContentTypes.POLL, config)
        question = poll.get("question", BotStrings.CONTENT_TYPE_NAMES["poll"])
        votes = poll.get("votes", 0)
        answers = poll.get("answers") or []
        total_answers = len(answers)
        embed.url = post_url
        embed.description = f"{Emojis.POLL} {BotStrings.POLL_VOTES_TEMPLATE.format(votes=votes)}"
        embed.add_field(name=f"{EmojisFields.ANSWERS} {BotStrings.FIELD_POLL_ANSWERS}", value=str(total_answers), inline=True)
        for i, ans in enumerate(answers[:5]):
            percentage = (ans['votes'] / votes * 100) if votes > 0 else 0
            embed.add_field(
                name=BotStrings.POLL_OPTION_NAME_TEMPLATE.format(number=i+1),
                value=BotStrings.POLL_OPTION_VALUE_TEMPLATE.format(text=ans['text'], votes=ans['votes'], percentage=percentage),
                inline=False
            )
        if len(answers) > 5:
            embed.add_field(name="...", value=BotStrings.POLL_MORE_OPTIONS_TEMPLATE.format(count=len(answers) - 5), inline=False)
        
        final_url = EmbedBuilder._get_preview_url(None, config, group_config)
        if final_url:
            embed.set_image(url=final_url)

        base_name = config.get("name", BotStrings.CONTENT_TYPE_NAMES["poll"])
        title_suffix = f" {index}/{total}" if total > 1 else ""
        emoji = resolve_random_value(config["emoji"])
        embed.title = f"{emoji} {base_name}{title_suffix}"
        return embed
