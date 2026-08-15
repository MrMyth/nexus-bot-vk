# modules_utils/presence_manager.py
import asyncio
import discord
from settings.data_files import Files
from constants.emojis import Emojis, LogEmojis
from modules_utils.cache_utils import load_json_cache_async, save_json_cache_async
from log_system.logger_helper import send_to_any_log

CONFIG_PATH = Files.BOT_PRESENCE_CONFIG_PATH

class PresenceManager:
    @classmethod
    async def load_presence(cls):
        """ Загружает настройки присутствия из JSON асинхронно и безопасно. """
        data = await load_json_cache_async(CONFIG_PATH)
        if not data:
            # Создаем файл с дефолтными значениями, если его нет
            data = {
                "status": "online",
                "activity_type": "custom",
                "activity_name": f"на страже порядка {Emojis.SHIELD}",
                "streaming_url": "https://www.twitch.tv/twitch"
            }
            await save_json_cache_async(CONFIG_PATH, data)
        return data

    @classmethod
    async def save_presence(cls, data):
        """ Сохраняет настройки присутствия в JSON асинхронно и безопасно. """
        await save_json_cache_async(CONFIG_PATH, data)

    @staticmethod
    def parse_status(status_str: str) -> discord.Status:
        """ Преобразует строковый статус в discord.Status. """
        status_str = status_str.lower().strip()
        if status_str in ["online", "в сети", "зеленый", "зелёный", "on", "active"]:
            return discord.Status.online
        elif status_str in ["idle", "неактивен", "афк", "afk", "желтый", "жёлтый"]:
            return discord.Status.idle
        elif status_str in ["dnd", "не беспокоить", "do_not_disturb", "красный"]:
            return discord.Status.dnd
        elif status_str in ["invisible", "offline", "невидимка", "серый", "оффлайн", "выкл"]:
            return discord.Status.invisible
        return discord.Status.online

    @staticmethod
    def parse_activity(activity_type: str, name: str, streaming_url: str = None) -> discord.Activity:
        """ Создает объект discord.Activity (или Game/Streaming/CustomActivity) на основе параметров. """
        if not activity_type or not name:
            return None

        act_type = activity_type.lower().strip()
        name = name.strip()

        if act_type in ["none", "remove", "clear", "нет", "убрать", "стереть"]:
            return None
        elif act_type in ["playing", "play", "играет", "игра", "играть"]:
            return discord.Game(name=name)
        elif act_type in ["streaming", "stream", "стримит", "стрим", "трансляция"]:
            url = streaming_url or "https://www.twitch.tv/twitch"
            return discord.Streaming(name=name, url=url)
        elif act_type in ["listening", "listen", "слушает", "слушать", "музыка"]:
            return discord.Activity(type=discord.ActivityType.listening, name=name)
        elif act_type in ["watching", "watch", "смотрит", "смотреть", "видео"]:
            return discord.Activity(type=discord.ActivityType.watching, name=name)
        elif act_type in ["competing", "compete", "соревнуется", "соревнование"]:
            return discord.Activity(type=discord.ActivityType.competing, name=name)
        elif act_type in ["custom", "кастомный", "пользовательский", "статус"]:
            return discord.CustomActivity(name=name)
        
        # По умолчанию считаем это CustomActivity
        return discord.CustomActivity(name=name)

    @classmethod
    async def apply_presence(cls, client: discord.Client):
        """ Считывает текущие настройки из файла и применяет их к боту. """
        if not client or not client.is_ready():
            return

        data = await cls.load_presence()
        status_obj = cls.parse_status(data.get("status", "online"))
        
        act_type = data.get("activity_type")
        act_name = data.get("activity_name")
        stream_url = data.get("streaming_url")

        activity_obj = cls.parse_activity(act_type, act_name, stream_url)

        try:
            await client.change_presence(status=status_obj, activity=activity_obj)
            await send_to_any_log("info", f"PresenceManager: успешно применено: статус={status_obj}, активность={act_type} - '{act_name}'", emoji=LogEmojis.SUCCESS)
        except Exception as e:
            await send_to_any_log("error", f"PresenceManager: не удалось обновить статус: {e}", emoji=LogEmojis.ERROR)

    @classmethod
    async def update_status(cls, client: discord.Client, status_str: str) -> str:
        """ Обновляет статус сети бота, сохраняет его и сразу применяет. """
        data = await cls.load_presence()
        
        # Проверяем валидность статуса
        status_str_clean = status_str.lower().strip()
        valid_status = "online"
        
        if status_str_clean in ["online", "в сети", "зеленый", "зелёный", "on"]:
            valid_status = "online"
        elif status_str_clean in ["idle", "неактивен", "афк", "afk", "желтый", "жёлтый"]:
            valid_status = "idle"
        elif status_str_clean in ["dnd", "не беспокоить", "do_not_disturb", "красный"]:
            valid_status = "dnd"
        elif status_str_clean in ["invisible", "offline", "невидимка", "серый"]:
            valid_status = "invisible"
        else:
            raise ValueError(f"Неизвестный сетевой статус: `{status_str}`. Доступные варианты: `online` (в сети), `idle` (неактивен), `dnd` (не беспокоить), `invisible` (невидимка).")

        data["status"] = valid_status
        await cls.save_presence(data)
        await cls.apply_presence(client)
        return valid_status

    @classmethod
    async def update_activity(cls, client: discord.Client, activity_type: str, name: str, streaming_url: str = None) -> tuple:
        """ Обновляет активность / кастомный статус бота, сохраняет и применяет. """
        data = await cls.load_presence()
        
        # Очистим и нормализуем тип активности
        act_type_clean = activity_type.lower().strip()
        
        if act_type_clean in ["none", "remove", "clear", "нет", "убрать"]:
            data["activity_type"] = "none"
            data["activity_name"] = ""
        elif act_type_clean in ["playing", "play", "играет", "игра"]:
            data["activity_type"] = "playing"
            data["activity_name"] = name
        elif act_type_clean in ["streaming", "stream", "стримит", "стрим"]:
            data["activity_type"] = "streaming"
            data["activity_name"] = name
            if streaming_url:
                data["streaming_url"] = streaming_url
        elif act_type_clean in ["listening", "listen", "слушает", "слушать", "музыка"]:
            data["activity_type"] = "listening"
            data["activity_name"] = name
        elif act_type_clean in ["watching", "watch", "смотрит", "смотреть"]:
            data["activity_type"] = "watching"
            data["activity_name"] = name
        elif act_type_clean in ["competing", "compete", "соревнуется"]:
            data["activity_type"] = "competing"
            data["activity_name"] = name
        elif act_type_clean in ["custom", "кастомный", "пользовательский", "статус"]:
            data["activity_type"] = "custom"
            data["activity_name"] = name
        else:
            # По умолчанию кастомный
            data["activity_type"] = "custom"
            data["activity_name"] = name

        await cls.save_presence(data)
        await cls.apply_presence(client)
        return data["activity_type"], data["activity_name"]
