# modules_utils/heartbeat_manager.py
import asyncio
import os
import sys
import platform
import psutil
from datetime import datetime
from typing import Optional

from settings.config import Config
from constants.emojis import LogEmojis, StartupEmojis
from log_system.logger_helper import send_to_any_log
from log_system.discord_logger import DiscordLogger
from modules_utils.helpers import safe_create_task, format_uptime

class HeartbeatManager:
    _task: Optional[asyncio.Task] = None
    _bot = None

    @classmethod
    def start(cls, bot_instance):
        """Запуск единого сервиса сердцебиения и мониторинга."""
        if cls._task and not cls._task.done():
            cls._task.cancel()
            
        cls._bot = bot_instance
        cls._task = safe_create_task(cls._loop())
        pid = os.getpid()
        asyncio.create_task(send_to_any_log(
            "info", 
            f"Единый Сервис Сердцебиения запущен при старте бота. [Обозначение процесса: {pid}]", 
            emoji=LogEmojis.INFO, 
            targets=["console", "file"]
        ))

    @classmethod
    def stop(cls):
        """Остановка сервиса сердцебиения."""
        if cls._task and not cls._task.done():
            cls._task.cancel()
        cls._task = None
        cls._bot = None

    @classmethod
    async def _loop(cls):
        interval = Config.HEARTBEAT_INTERVAL or 900
        loop = asyncio.get_running_loop()
        pid = os.getpid()
        
        # Планируем первый Heartbeat через interval секунд
        next_heartbeat = loop.time() + interval
        
        while True:
            now = loop.time()
            sleep_time = max(0.0, next_heartbeat - now)
            await asyncio.sleep(sleep_time)
            next_heartbeat += interval
            
            try:
                # 1. Собираем системную статистику
                try:
                    process = psutil.Process(pid)
                    memory_info = process.memory_info().rss / 1024 / 1024  # MB
                except Exception:
                    memory_info = 0.0

                # 2. Получаем аптайм и статус задач планировщика
                from modules_utils.task_scheduler import scheduler
                active_tasks = []
                stopped_tasks = []
                for name, t in scheduler.tasks.items():
                    if t.done():
                        stopped_tasks.append(name)
                    else:
                        active_tasks.append(name)

                # 3. Аптайм бота
                uptime_str = "неизвестно"
                if cls._bot and getattr(cls._bot, "start_time", None):
                    uptime = datetime.now() - cls._bot.start_time
                    uptime_str = format_uptime(uptime)

                # 4. Проверяем очередь сообщений
                queue_size = 0
                if cls._bot and hasattr(cls._bot, "discord_client") and hasattr(cls._bot.discord_client, "_message_queue"):
                    queue_size = cls._bot.discord_client._message_queue.qsize()

                # Сводная диагностическая информация
                diag_info = f"Uptime: {uptime_str} | Задач в работе: {len(active_tasks)}/{len(scheduler.tasks)} | Очередь Discord: {queue_size} | Память: {memory_info:.1f} MB | [Обозначение процесса: {pid}]"
                
                # Добавляем инфо про остановленные задачи в консоль/файл
                if stopped_tasks:
                    diag_info += f" | {LogEmojis.WARNING} ОСТАНОВЛЕННЫЕ ЗАДАЧИ: {', '.join(stopped_tasks)}"

                # Отсылаем в Discord канал логов через DiscordLogger
                content_discord = (
                    f"{StartupEmojis.SYSTEM} **Сердцебиение бота [Обозначение процесса: {pid}]**\n"
                    f"{StartupEmojis.BLUE_DIAMOND} **Аптайм:** `{uptime_str}`\n"
                    f"{StartupEmojis.BLUE_DIAMOND} **Активных мониторов:** `{len(active_tasks)}/{len(scheduler.tasks)}`\n"
                    f"{StartupEmojis.BLUE_DIAMOND} **Очередь отправки:** `{queue_size}`\n"
                    f"{StartupEmojis.BLUE_DIAMOND} **Память:** `{memory_info:.1f} MB`"
                )
                if stopped_tasks:
                    content_discord += f"\n{StartupEmojis.WARNING} **ПРОБЛЕМА: Завершенные задачи:** `{', '.join(stopped_tasks)}`"

                # Отправляем сообщение на сервер
                await DiscordLogger.send_to_channel(content=content_discord)

                # Записываем в файл локального лога
                await send_to_any_log("info", f"Heartbeat отправлен: {diag_info}", emoji=LogEmojis.INFO, targets=["console", "file"])

                # Если есть упавшие задачи, дополнительно отправляем краш-предупреждение
                if stopped_tasks:
                    await send_to_any_log(
                        "warning", 
                        f"Обнаружены остановленные задачи мониторинга: {', '.join(stopped_tasks)} [Обозначение процесса: {pid}]", 
                        emoji=LogEmojis.WARNING
                    )

            except Exception as e:
                try:
                    await send_to_any_log(
                        "error", 
                        f"Ошибка в цикле Heartbeat [Обозначение процесса: {pid}]: {e}", 
                        emoji=LogEmojis.ERROR, 
                        targets=["console", "file"]
                    )
                except Exception:
                    print(f"Критическая ошибка Heartbeat: {e}")
