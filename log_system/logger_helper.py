# log_system/logger_helper.py

import asyncio
import sys
import traceback
from settings.config import Config
from typing import Literal, List, Any
from log_system.logger import logger_console, logger_file  # Отдельные логгеры для каждого назначения

try:
    import logging as _logging
    _logger_mentions = _logging.getLogger("bot.mentions")
except Exception:
    _logger_mentions = None

def send_log_to_console(level: str, message: str, emoji: str = "", exc_info: Any = None):
    """Отправляет лог в консоль с эмодзи (если не отключено)."""
    if not Config.DISABLE_EMOJI_CONSOLE and emoji:
        message = f"{emoji} {message}"
    getattr(logger_console, level)(message, exc_info=exc_info)  # ← пишется только в консоль
    
def send_log_to_file(level: str, message: str, emoji: str = "", exc_info: Any = None):
    """Отправляет лог в файл с эмодзи (если не отключено)."""
    if not Config.DISABLE_EMOJI_FILE and emoji:
        message = f"{emoji} {message}"
    getattr(logger_file, level)(message, exc_info=exc_info)  # ← пишется только в файл

def send_log_to_mentions_file(message: str):
    """Записывает событие с упоминанием в отдельный лог-файл mentions.log."""
    try:
        if _logger_mentions:
            _logger_mentions.info(message)
    except Exception:
        pass

async def send_log_to_discord(level: str, message: str, emoji: str = "", exc_info: Any = None):
    """Отправляет лог в Discord с эмодзи (если не отключено)."""
    # НЕ отправляем уведомления о перезапуске в Discord
    if "перезапуск" in message.lower() or "restart" in message.lower():
        return
        
    if not Config.DISABLE_EMOJI_DISCORD and emoji:
        message = f"{emoji} {message}"
    
    # Локальный импорт для разрыва цикла
    from log_system.discord_logger import DiscordLogger
    
    # Если это критическая ошибка, системный сбой или обычная ошибка — используем специальное уведомление
    if level in ("error", "critical"):
        # Проверяем, не является ли это рейт-лимитом (чтобы не спамить тегом роли)
        rate_limit_keywords = ["429", "rate limit", "слишком много запросов", "retry after", "error_code: 6"]
        is_rate_limit = any(kw in message.lower() for kw in rate_limit_keywords)
        
        # Если это критическая ошибка — всегда тегаем. 
        # Если обычная ошибка — тегаем только если это НЕ рейт-лимит.
        should_mention = (level == "critical") or (level == "error" and not is_rate_limit)
        
        traceback_str = None
        if exc_info:
            try:
                if isinstance(exc_info, bool) and exc_info:
                    tb_str = traceback.format_exc()
                elif isinstance(exc_info, Exception):
                    tb_str = "".join(traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__))
                elif isinstance(exc_info, tuple) and len(exc_info) == 3:
                    tb_str = "".join(traceback.format_exception(*exc_info))
                else:
                    tb_str = ""
                
                if tb_str:
                    # Ограничиваем traceback последними 1000 символами
                    if len(tb_str) > 1000:
                        tb_str = "...\n" + tb_str[-1000:]
                    traceback_str = f"```py\n{tb_str}```"
            except Exception:
                pass
        
        await DiscordLogger.send_restore_alert(message, mention=should_mention, traceback_str=traceback_str)
    else:
        # Информационные логи больше не шлем во избежание спама
        pass


async def send_to_any_log(
    level: Literal["debug", "info", "warning", "error", "critical"],
    message: str,
    emoji: str = "",
    targets: List[Literal["console", "file", "discord"]] = None,
    exc_info: Any = None
):
    """
    Универсальная точка входа для логирования.
    Распределяет сообщение по указанным каналам.
    """
    if exc_info is None:
        if level in ("error", "critical"):
            # Если мы находимся в блоке except, автоматически получаем текущее исключение
            active_exc = sys.exc_info()
            if active_exc[0] is not None:
                exc_info = active_exc

    if targets is None:
        targets = ["console", "file", "discord"]

    # Для сообщений о перезапуске отправляем ТОЛЬКО в консоль и файл
    if "перезапуск" in message.lower() or "restart" in message.lower():
        targets = ["console", "file"]

    if "console" in targets:
        send_log_to_console(level, message, emoji, exc_info=exc_info)

    if "file" in targets:
        send_log_to_file(level, message, emoji, exc_info=exc_info)

    if "discord" in targets:
        # Логи в Discord шлем только если это ошибки (DiscordLogger.send_restore_alert)
        await send_log_to_discord(level, message, emoji, exc_info=exc_info)
