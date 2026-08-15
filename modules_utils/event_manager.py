# modules_utils/event_manager.py
import asyncio
import aiohttp
import discord
import os
from typing import Dict, Any, Optional
from datetime import timedelta
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from modules_utils.random_resolver import resolve_random_value
from settings.config import Config


class EventManager:
    """Универсальный менеджер Discord событий для всех модулей."""
    
    _active_events = {}  # { stream_id: { "event_id", "guild_id", "config", "event_data", "extension_count", "check_interval" } }

    @staticmethod
    async def create_discord_event(
        guild: discord.Guild,
        event_data: Dict[str, Any],
        config: Dict[str, Any],
        recreating: bool = False
    ) -> Optional[str]:
        """
        Создаёт мероприятие в Discord с автоматическим продлением.
        
        :param guild: Discord сервер
        :param event_data: Данные события (название, описание и т.д.)
        :param config: Конфигурация модуля
        :param recreating: Флаг повторного создания (если старое удалено)
        """
        if not config.get("create_discord_event", True):
            return None

        if not guild:
            guild = await EventManager._get_guild_from_config(config)
            if not guild:
                await send_to_any_log("error", "Не удалось создать событие: guild не задан и не может быть получен автоматически", emoji=LogEmojis.ERROR)
                return None
    
        try:
            stream_id = str(event_data.get("stream_id"))
            if not stream_id:
                return None

            event_name = event_data.get("title") or "Стрим без названия"
            description = config.get("event_description") or "Прямой эфир начался!"
            
            # Добавляем примечание о примерном времени, если оно еще не добавлено
            approx_notice = "\n\n*Примечание: Время окончания примерное и может быть изменено в процессе.*"
            if approx_notice not in description:
                description = f"{description}{approx_notice}"
            
            # Локация: если нет URL, используем заглушку
            location = event_data.get("url")
            if not location or location == "#" or not isinstance(location, str):
                location = "Прямой эфир"
            
            # Гарантируем, что location — строка и не слишком длинная
            location = str(location)[:100]
            
            start_time = discord.utils.utcnow() + timedelta(seconds=10)

            # СТРАТЕГИЯ "СКОЛЬЗЯЩЕГО ОКНА":
            # Начальная длительность берётся из конфига (по умолчанию из Config).
            # Будем продлевать, поддерживая всегда запас.
            from settings.config import Config
            event_duration_hours = config.get("event_duration_hours", Config.STREAM_EVENT_DURATION_HOURS)
            check_interval = config.get("check_interval", 300)
            end_time = start_time + timedelta(hours=event_duration_hours)

            from modules_utils.embed_builder_video import EmbedBuilderVideo
            
            use_only_json = config.get("use_only_json_images", False)
            try_platform = config.get("try_platform_preview", not use_only_json)
            
            raw_event_image = None
            if try_platform:
                for field in ["photo_1280", "photo_800", "photo_640", "image", "images", "thumbnail"]:
                    val = event_data.get(field)
                    if val:
                        url = EmbedBuilderVideo._get_best_image_url(val)
                        if url:
                            raw_event_image = url
                            break
            
            if not raw_event_image:
                raw_event_image = config.get("event_image") or config.get("preview") or config.get("embed_thumbnail_url")
                
            selected_image_url = resolve_random_value(raw_event_image)
            image_bytes = None
            if selected_image_url:
                image_bytes = await EventManager._download_image(selected_image_url)

            event_kwargs = {
                "name": str(event_name)[:100],
                "description": str(description)[:1000],
                "location": location,
                "start_time": start_time,
                "end_time": end_time,
                "privacy_level": discord.PrivacyLevel.guild_only,
                "entity_type": discord.EntityType.external
            }
            if image_bytes is not None:
                event_kwargs["image"] = image_bytes

            event = await guild.create_scheduled_event(**event_kwargs)

            # Сохраняем полное состояние для возможности пересоздания
            EventManager._active_events[stream_id] = {
                "event_id": str(event.id),
                "guild_id": guild.id,
                "config": config,
                "event_data": event_data,
                "extension_count": 0,
                "check_interval": check_interval
            }

            log_prefix = "Мероприятие пересоздано" if recreating else "Мероприятие создано"
            await send_to_any_log("info", f"{log_prefix} (до {end_time.strftime('%H:%M:%S')}): {event.name} (ID: {event.id})", emoji=LogEmojis.SUCCESS)
            return str(event.id)

        except Exception as e:
            await send_to_any_log("error", f"Ошибка создания мероприятия: {e}", emoji=LogEmojis.ERROR)
            return None

    @staticmethod
    async def monitor_stream_end(stream_id: str, video_owner_id: int, video_id: int):
        """Фоновый мониторинг завершения стрима для удаления мероприятия."""
        retry_count = 0
        max_retries = 3 

        while True:
            await asyncio.sleep(60) 
            
            try:
                event_data = EventManager.get_event_data(stream_id)
                if not event_data:
                    break
                
                event_id = event_data.get("event_id")
                guild = event_data.get("guild")
                
                from modules_utils.vk_api_client import VKApiClient
                is_live = await VKApiClient.is_live_video(video_owner_id, video_id)
                
                if not is_live:
                    await send_to_any_log("info", f"Стрим {stream_id} завершен. Удаляю мероприятие {event_id}.", emoji=LogEmojis.INFO)
                    await EventManager.delete_discord_event(guild, event_id)
                    EventManager.remove_event(stream_id)
                    break
                else:
                    new_event_id = await EventManager.extend_event_if_needed(stream_id, str(event_id))
                    if new_event_id and new_event_id != str(event_id):
                        # Обновляем ID если ивент был пересоздан
                        event_data["event_id"] = new_event_id
                
                retry_count = 0 
            except Exception as e:
                retry_count += 1
                await send_to_any_log("error", f"Ошибка мониторинга завершения стрима {stream_id}: {e}", emoji=LogEmojis.ERROR)
                if retry_count >= max_retries:
                    break

    @staticmethod
    async def extend_event_if_needed(stream_id: str, event_id: str) -> Optional[str]:
        """
        Продлевает мероприятие или пересоздаёт его, если оно было удалено.
        
        :param stream_id: ID стрима
        :param event_id: Текущий ID мероприятия Discord
        :return: (Новый или старый) ID мероприятия, или None если всё плохо
        """
        try:
            state = EventManager._active_events.get(stream_id)
            if not state:
                return None

            from clients.bot_instance import bot
            if not bot:
                return None

            guild = bot.get_guild(state["guild_id"])
            if not guild:
                guild = await EventManager._get_guild_from_config(state["config"])
            
            if not guild:
                return event_id

            # Пытаемся получить событие
            event = None
            try:
                event = await guild.fetch_scheduled_event(int(event_id))
            except discord.NotFound:
                # СОБЫТИЕ УДАЛЕНО РУКАМИ ИЛИ БАГ
                await send_to_any_log("warning", f"Мероприятие {event_id} (стрим {stream_id}) удалено. Пересоздаю...", emoji=LogEmojis.WARNING)
                new_id = await EventManager.create_discord_event(guild, state["event_data"], state["config"], recreating=True)
                return new_id

            # Если мероприятие завершено или отменено
            if event.status in (discord.EventStatus.completed, discord.EventStatus.cancelled):
                await send_to_any_log("warning", f"Мероприятие {event_id} в статусе {event.status}. Пересоздаю...", emoji=LogEmojis.WARNING)
                new_id = await EventManager.create_discord_event(guild, state["event_data"], state["config"], recreating=True)
                return new_id

            # ПРОВЕРЯЕМ НУЖНО ЛИ ПРОДЛИТЬ (если до конца меньше порога из конфига)
            from settings.config import Config
            extension_threshold_secs = state.get("config", {}).get(
                "event_extension_threshold_minutes",
                Config.STREAM_EVENT_EXTENSION_THRESHOLD_MINUTES
            ) * 60
            event_duration_hours = state.get("config", {}).get(
                "event_duration_hours",
                Config.STREAM_EVENT_DURATION_HOURS
            )
            time_until_end = event.end_time - discord.utils.utcnow()
            if time_until_end.total_seconds() > extension_threshold_secs:
                return event_id

            # Продлеваем на event_duration_hours от текущего момента
            new_end_time = discord.utils.utcnow() + timedelta(hours=event_duration_hours)
            await event.edit(
                end_time=new_end_time,
                reason=f"Автопродление стрима {stream_id}"
            )

            state["extension_count"] += 1
            await send_to_any_log(
                "debug",
                f"Мероприятие {event_id} продлено до {new_end_time.strftime('%H:%M:%S')} (запас 1ч)",
                emoji=LogEmojis.INFO
            )
            return event_id

        except discord.HTTPException as e:
            if e.code == 50035:
                await send_to_any_log("warning", f"Ошибка Discord API (50035) для ивента {event_id}. Возможно, завершен.", emoji=LogEmojis.WARNING)
            else:
                await send_to_any_log("error", f"Ошибка продления мероприятия {event_id}: {e}", emoji=LogEmojis.ERROR)
            return event_id
        except Exception as e:
            await send_to_any_log("error", f"Ошибка в логике продления {stream_id}: {e}", emoji=LogEmojis.ERROR)
            return event_id

    @staticmethod
    async def cleanup_extension_data(stream_id: str = None, event_id: str = None):
        """Очищает данные после завершения мероприятия."""
        if stream_id:
            EventManager._active_events.pop(stream_id, None)
        elif event_id:
            # Ищем по event_id если stream_id не передан
            for sid, state in list(EventManager._active_events.items()):
                if state.get("event_id") == event_id:
                    EventManager._active_events.pop(sid, None)
                    break

    @staticmethod
    async def _get_guild_from_config(config: Dict[str, Any]) -> Optional[discord.Guild]:
        """
        Получает сервер по SERVER_ID из конфигурации (.env → config.py → Config.SERVER_ID).
        """
        from clients.bot_instance import bot

        if bot is None:
            await send_to_any_log("error", "Бот не инициализирован", emoji=LogEmojis.ERROR)
            return None

        guild_id = Config.SERVER_ID
        if guild_id is None:
            await send_to_any_log("warning", "SERVER_ID не задан в .env", emoji=LogEmojis.WARNING)
            return None

        guild = bot.get_guild(guild_id)
        if guild is None:
            await send_to_any_log(
                "error",
                f"Сервер с ID {guild_id} не найден. Убедитесь, что бот добавлен на сервер.",
                emoji=LogEmojis.ERROR
            )
            return None

        return guild

    @staticmethod
    async def delete_discord_event(guild: discord.Guild, event_id: str):
        """Удаляет Scheduled Event из Discord."""
        try:
            if not guild:
                guild = await EventManager._get_guild_from_config({})

            if not guild:
                await send_to_any_log("warning", f"Не удалось определить сервер для удаления ивента {event_id}", emoji=LogEmojis.WARNING)
                return

            # Очищаем состояние
            await EventManager.cleanup_extension_data(event_id=event_id)
            
            event = await guild.fetch_scheduled_event(int(event_id))
            await event.delete()
            await send_to_any_log("info", f"Мероприятие {event_id} удалено", emoji=LogEmojis.INFO)
        except discord.NotFound:
            await send_to_any_log("warning", f"Мероприятие {event_id} уже удалено", emoji=LogEmojis.WARNING)
            await EventManager.cleanup_extension_data(event_id=event_id)
        except Exception as e:
            await send_to_any_log("error", f"Ошибка удаления мероприятия {event_id}: {e}", emoji=LogEmojis.ERROR)

    @staticmethod
    async def _download_image(path_or_url: Optional[str]) -> Optional[bytes]:
        """Загружает изображение для мероприятия (поддерживает URL и локальные пути)."""
        if not path_or_url or not isinstance(path_or_url, str):
            return None

        path_or_url = str(path_or_url).strip()
        
        # 1. Если это локальный путь, читаем напрямую
        if not path_or_url.startswith(('http://', 'https://')):
            # Проверяем файлы в корне или в assets
            paths_to_try = [path_or_url, os.path.join(os.getcwd(), path_or_url)]
            for p in paths_to_try:
                if os.path.isfile(p):
                    try:
                        with open(p, "rb") as f:
                            return f.read()
                    except Exception as e:
                        await send_to_any_log("warning", f"Не удалось прочитать локальный ассет {p}: {e}")
            
            # Если не нашли файл локально, но есть ASSETS_BASE_URL — пробуем собрать URL
            from modules_utils.helpers import resolve_asset_url
            resolved_url = resolve_asset_url(path_or_url)
            if resolved_url and resolved_url.startswith('http'):
                path_or_url = resolved_url
            else:
                return None

        # 2. Если это URL, загружаем
        try:
            from modules_utils.http_client import HttpClient
            session = await HttpClient.get_session()
            async with session.get(path_or_url) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            await send_to_any_log("warning", f"Не удалось загрузить изображение мероприятия по URL {path_or_url}: {e}", emoji=LogEmojis.WARNING)
        return None

    @staticmethod
    def store_event(stream_id: str, data: Dict[str, Any]):
        """Сохраняет данные о запущенном событии."""
        EventManager._active_events[stream_id] = data

    @staticmethod
    def get_event_data(stream_id: str) -> Optional[Dict[str, Any]]:
        """Получает данные о событии по stream_id."""
        return EventManager._active_events.get(stream_id)

    @staticmethod
    def remove_event(stream_id: str):
        """Удаляет запись о событии."""
        EventManager._active_events.pop(stream_id, None)