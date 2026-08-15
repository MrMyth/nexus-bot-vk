# clients/discord_client.py
import asyncio
import discord
from discord.ext import commands
from typing import Dict, Any, Optional, List, Union
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from settings.config import Config


class DiscordBotManager:
    """Менеджер для взаимодействия с Discord API и отправки сообщений."""

    def __init__(self, bot: commands.Bot, group_mappings: Optional[Dict[str, int]] = None):
        self.bot = bot
        self.group_mappings = group_mappings if group_mappings is not None else {}
        self._message_queue: asyncio.Queue = asyncio.Queue()

    async def start(self):
        """Запуск менеджера сообщений при необходимости."""
        pass

    async def _handle_auto_publish(self, message: Any, channel: Optional[Any], config: Optional[Dict[str, Any]] = None):
        """Автоматическая публикация (crosspost) сообщения в новостных каналах (Announcement channels)."""
        if not message:
            return

        should_publish = False
        if config and isinstance(config, dict):
            should_publish = bool(config.get("auto_publish", config.get("auto_crosspost", False)))
        else:
            should_publish = getattr(Config, "AUTO_PUBLISH_NEWS", False)

        if not should_publish:
            return

        try:
            # Проверяем, является ли сообщение сообщением из новостного канала
            if hasattr(message, "publish"):
                # Если передан канал, проверим тип канала
                target_channel = channel or getattr(message, "channel", None)
                if target_channel:
                    channel_type = getattr(target_channel, "type", None)
                    if channel_type == discord.ChannelType.news or getattr(target_channel, "is_news", lambda: False)():
                        await message.publish()
                        await send_to_any_log("debug", f"Message {getattr(message, 'id', '')} automatically published (crosspost)", emoji=LogEmojis.DEBUG)
                else:
                    await message.publish()
        except discord.Forbidden:
            await send_to_any_log("warning", "Missing permissions to auto-publish (crosspost) message in news channel", emoji=LogEmojis.WARNING)
        except Exception as e:
            await send_to_any_log("debug", f"Auto-publish error: {e}", emoji=LogEmojis.DEBUG)

    async def send_message_async(
        self,
        screen_name: Optional[str] = None,
        message_data: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
        override_channel_id: Optional[Union[int, str]] = None,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> bool:
        """
        Асинхронно отправляет форматированное сообщение (или список сообщений) в Discord.
        Поддерживает отправку через обычные каналы, треды и Webhook.
        """
        if not message_data:
            return False

        config = config or {}
        channel_id = override_channel_id or config.get("discord_channel_id")
        if not channel_id and screen_name:
            channel_id = self.group_mappings.get(screen_name)

        # Проверяем webhook_url в конфигурации
        webhook_url = config.get("webhook_url") or config.get("webhook")

        messages_list = message_data if isinstance(message_data, list) else [message_data]
        all_success = True

        for item in messages_list:
            if not isinstance(item, dict):
                continue

            content = item.get("content")
            embeds = item.get("embeds")
            embed = item.get("embed")
            files = item.get("files")
            file = item.get("file")
            view = item.get("view")

            if embed and not embeds:
                embeds = [embed]
            if file and not files:
                files = [file]

            # 1. Отправка через Webhook
            if webhook_url:
                try:
                    import aiohttp
                    from modules_utils.http_client import HttpClient
                    session = HttpClient.get_session()
                    webhook = discord.Webhook.from_url(webhook_url, session=session)
                    thread_id = config.get("thread_id")
                    thread_obj = discord.Object(id=int(thread_id)) if thread_id else discord.utils.MISSING

                    sent_msg = await webhook.send(
                        content=content,
                        embeds=embeds or discord.utils.MISSING,
                        files=files or discord.utils.MISSING,
                        view=view or discord.utils.MISSING,
                        username=config.get("webhook_username") or discord.utils.MISSING,
                        avatar_url=config.get("webhook_avatar") or config.get("webhook_avatar_url") or discord.utils.MISSING,
                        thread=thread_obj,
                        wait=True
                    )
                    if sent_msg:
                        await self._handle_auto_publish(sent_msg, None, config)
                    continue
                except Exception as wh_err:
                    await send_to_any_log("warning", f"Failed to send via Webhook: {wh_err}. Trying to send directly to channel.", emoji=LogEmojis.WARNING)

            # 2. Отправка через канал бота
            if not channel_id:
                await send_to_any_log("error", f"send_message_async: channel_id not specified (screen_name={screen_name})", emoji=LogEmojis.ERROR)
                all_success = False
                continue

            try:
                target_id = int(channel_id)
                channel = self.bot.get_channel(target_id)
                if not channel:
                    channel = await self.bot.fetch_channel(target_id)

                if not channel:
                    await send_to_any_log("error", f"send_message_async: Channel with ID {target_id} not found", emoji=LogEmojis.ERROR)
                    all_success = False
                    continue

                thread_id = config.get("thread_id")
                target_dest = channel
                if thread_id:
                    try:
                        thread_obj = channel.get_thread(int(thread_id))
                        if not thread_obj:
                            thread_obj = await self.bot.fetch_channel(int(thread_id))
                        if thread_obj:
                            target_dest = thread_obj
                    except Exception as th_err:
                        await send_to_any_log("warning", f"Failed to get thread {thread_id}: {th_err}. Sending to main channel.", emoji=LogEmojis.WARNING)

                sent_msg = await target_dest.send(
                    content=content,
                    embeds=embeds,
                    files=files,
                    view=view
                )
                if sent_msg:
                    await self._handle_auto_publish(sent_msg, target_dest, config)

            except discord.Forbidden as f_err:
                await send_to_any_log("critical", f"Missing permissions to send message to channel {channel_id}: {f_err}", emoji=LogEmojis.CRITICAL)
                all_success = False
            except discord.HTTPException as h_err:
                await send_to_any_log("error", f"HTTP error sending message to channel {channel_id}: {h_err}", emoji=LogEmojis.ERROR)
                all_success = False
            except Exception as e:
                await send_to_any_log("error", f"Unexpected error sending message to channel {channel_id}: {e}", emoji=LogEmojis.ERROR)
                all_success = False

        return all_success
