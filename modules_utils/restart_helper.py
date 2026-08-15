# modules_utils/restart_helper.py

import asyncio
import os
import sys
import json
from datetime import datetime
from typing import Optional

from settings.config import Config
from settings.data_files import Files
from constants.emojis import LogEmojis
from log_system.logger_helper import send_to_any_log
from modules_utils.helpers import safe_create_task

class RestartHelper:
    """Хелпер для управления автоматическим перезапуском бота."""

    _restart_attempted = False
    _restart_count = 0
    _max_restart_attempts = 3
    _delay_before_start = 0.0

    # Флаги, читаемые run_forever() после завершения asyncio.run(main()).
    # _restart_requested=True  → немедленно перезапустить (continue в while-цикле).
    # _shutdown_requested=True → выйти из while-цикла (break).
    _restart_requested: bool = False
    _shutdown_requested: bool = False
    
    @classmethod
    async def start_auto_restart(cls, bot_instance):
        """Запускает процесс автоматического перезапуска."""
        if cls._restart_attempted:
            safe_create_task(send_to_any_log(
                "warning", "Перезапуск уже выполняется, пропускаем", 
                emoji=LogEmojis.WARNING, targets=["console", "file"]
            ))
            return
            
        cls._restart_attempted = True
        cls._restart_count += 1
        
        if cls._restart_count > cls._max_restart_attempts:
            safe_create_task(send_to_any_log(
                "error", f"Достигнут лимит попыток перезапуска ({cls._max_restart_attempts}). Остановка.", 
                emoji=LogEmojis.ERROR, targets=["console", "file"]
            ))
            return

        try:
            # Вычисляем задержку: 15с, 30с, 60с... (экспоненциально)
            delay = min(15 * (2 ** (cls._restart_count - 1)), 300) 
            cls._delay_before_start = float(delay)
            safe_create_task(send_to_any_log(
                "info", f"Попытка перезапуска {cls._restart_count}/{cls._max_restart_attempts} через {delay}с...", 
                emoji=LogEmojis.INFO, targets=["console", "file"]
            ))
            
            # Останавливаем текущий экземпляр.
            # Это приведет к завершению await bot.discord_client.start() в main()
            # и последующему перезапуску через внешний цикл while True в start.py
            await bot_instance.stop(reason=f"Авторестарт (попытка {cls._restart_count})")
            
            # Ждем перед тем как позволить циклу перезапуститься (опционально, 
            # так как внешний цикл может иметь свои задержки)
            await asyncio.sleep(delay)
            
            safe_create_task(send_to_any_log(
                "info", "Процесс текущего экземпляра завершен, ожидание перезапуска внешним циклом...", 
                emoji=LogEmojis.INFO, targets=["console", "file"]
            ))
            
        except Exception as e:
            safe_create_task(send_to_any_log(
                "error", f"Ошибка при перезапуске (helper): {e}", 
                emoji=LogEmojis.ERROR, targets=["console", "file"]
            ))
            cls._restart_attempted = False # Сбрасываем чтобы можно было попробовать снова при необходимости

    @classmethod
    def reset_attempts(cls):
        """Сбрасывает счетчик попыток и флаг выполнения."""
        cls._restart_attempted = False
        cls._restart_count = 0
        cls._delay_before_start = 0.0

    @classmethod
    def save_stop_reason(cls, reason: str):
        """Сохраняет причину остановки в файл."""
        if not reason:
            return
            
        try:
            os.makedirs(os.path.dirname(Files.STOP_REASON_FILE), exist_ok=True)
            with open(Files.STOP_REASON_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "reason": reason, 
                    "timestamp": datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=4)
        except Exception as e:
            safe_create_task(send_to_any_log("error", f"RestartHelper: не удалось сохранить причину остановки: {e}", emoji=LogEmojis.ERROR))

    @classmethod
    def load_stop_reason(cls) -> Optional[str]:
        """Загружает причину остановки из файла и удаляет его."""
        if not os.path.exists(Files.STOP_REASON_FILE):
            return None
            
        try:
            with open(Files.STOP_REASON_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                reason = data.get("reason")
            os.remove(Files.STOP_REASON_FILE)
            return reason
        except Exception:
            return None
