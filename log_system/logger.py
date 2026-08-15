# log_system/logger.py

import logging
import pytz
from datetime import datetime
from settings.data_files import Files
from settings.config import Config
from constants.locale_mappings import MONTHS_RU, DAYS_RU
from constants.colors import LoggerColors


class PrintLogger:
    def __init__(self):
        self.level = logging.INFO

    def setLevel(self, level):
        self.level = level

    def log(self, level, msg, exc_info=None):
        if level >= self.level:
            tb_str = ""
            if exc_info:
                import traceback
                if isinstance(exc_info, bool) and exc_info:
                    tb_str = "\n" + traceback.format_exc()
                elif isinstance(exc_info, Exception):
                    tb_str = "\n" + "".join(traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__))
                elif isinstance(exc_info, tuple) and len(exc_info) == 3:
                    tb_str = "\n" + "".join(traceback.format_exception(*exc_info))
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {logging.getLevelName(level)} - {msg}{tb_str}")

    def debug(self, msg, exc_info=None):
        self.log(logging.DEBUG, msg, exc_info)

    def info(self, msg, exc_info=None):
        self.log(logging.INFO, msg, exc_info)

    def warning(self, msg, exc_info=None):
        self.log(logging.WARNING, msg, exc_info)

    def error(self, msg, exc_info=None):
        self.log(logging.ERROR, msg, exc_info)

    def critical(self, msg, exc_info=None):
        self.log(logging.CRITICAL, msg, exc_info)


class RussianFormatter(logging.Formatter):
    def __init__(self, fmt: str | None = None, timezone: str = "Europe/Moscow"):
        super().__init__(fmt or '[%(asctime)s] %(levelname)s - %(message)s')
        try:
            self.timezone = pytz.timezone(timezone)
        except (pytz.UnknownTimeZoneError, TypeError):
            self.timezone = pytz.timezone("Europe/Moscow")

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, self.timezone)
        return f"{DAYS_RU[dt.weekday()]}, {dt.day} {MONTHS_RU[dt.month - 1]} {dt.year}, {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"


class ConsoleColor:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


class ColoredConsoleFormatter(logging.Formatter):
    def __init__(self, fmt: str | None = None, timezone: str = "Europe/Moscow"):
        super().__init__(fmt or '[%(asctime)s] %(levelname)s - %(message)s')
        try:
            self.timezone = pytz.timezone(timezone)
        except (pytz.UnknownTimeZoneError, TypeError):
            self.timezone = pytz.timezone("Europe/Moscow")

        self.level_colors = {
            logging.DEBUG: self._hex_to_ansi(LoggerColors.DEBUG),
            logging.INFO: self._hex_to_ansi(LoggerColors.INFO),
            logging.WARNING: self._hex_to_ansi(LoggerColors.WARNING),
            logging.ERROR: self._hex_to_ansi(LoggerColors.ERROR),
            logging.CRITICAL: self._hex_to_ansi(LoggerColors.CRITICAL),
        }

    def format(self, record):
        formatted = super().format(record)
        color = self.level_colors.get(record.levelno, ConsoleColor.RESET)
        return f"{color}{formatted}{ConsoleColor.RESET}"

    def _hex_to_ansi(self, hex_color: str) -> str:
        if not hex_color or not hex_color.startswith("#") or len(hex_color) != 7:
            return ConsoleColor.WHITE
        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            return f"\033[38;2;{r};{g};{b}m"
        except ValueError:
            return ConsoleColor.WHITE


class NoEmojiFileFormatter(RussianFormatter):
    """Форматтер для файла — не добавляет эмодзи (это делает logger_helper)."""
    pass  # Наследуем всё от RussianFormatter, так как эмодзи уже обработаны выше




# Создаём папки до инициализации логгера
from settings.data_files import Files as _Files
_Files.ensure_directories()

# Инициализация логгеров — отдельные логгеры для консоли и файла
if Config.DISABLE_LOGGER:
    logger_console = PrintLogger()
    logger_file = PrintLogger()
else:
    # Отдельный логгер для консоли
    logger_console = logging.getLogger("bot.console")
    logger_console.setLevel(logging.INFO)
    logger_console.propagate = False  # Не передаем родительскому логгеру
    if logger_console.hasHandlers():
        logger_console.handlers.clear()
    
    console_handler = logging.StreamHandler()
    console_formatter = ColoredConsoleFormatter('[%(asctime)s] %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger_console.addHandler(console_handler)

    # Отдельный логгер для файла
    logger_file = logging.getLogger("bot.file")
    logger_file.setLevel(logging.INFO)
    logger_file.propagate = False  # Не передаем родительскому логгеру
    if logger_file.hasHandlers():
        logger_file.handlers.clear()
    
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        Files.LOG_FILE, 
        encoding=Config.LOG_FILE_ENCODING,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5
    )
    tz_region = getattr(Config, "TIMEZONE_REGION", None)
    safe_timezone = tz_region if isinstance(tz_region, str) and tz_region else "Europe/Moscow"
    file_formatter = NoEmojiFileFormatter(timezone=safe_timezone)
    file_handler.setFormatter(file_formatter)
    logger_file.addHandler(file_handler)

    # DiscordHandler больше не добавляем — критические ошибки шлются в Discord через logger_helper

    # Отдельный логгер для упоминаний (mentions.log)
    logger_mentions = logging.getLogger("bot.mentions")
    logger_mentions.setLevel(logging.INFO)
    logger_mentions.propagate = False
    if logger_mentions.hasHandlers():
        logger_mentions.handlers.clear()

    mentions_handler = RotatingFileHandler(
        Files.MENTIONS_LOG_FILE,
        encoding=Config.LOG_FILE_ENCODING,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5
    )
    mentions_handler.setFormatter(NoEmojiFileFormatter(timezone=safe_timezone))
    logger_mentions.addHandler(mentions_handler)


def update_logger_timezone(new_timezone: str) -> bool:
    if isinstance(logger_console, PrintLogger):
        return True
    try:
        if not isinstance(new_timezone, str) or not new_timezone:
            raise ValueError("Invalid timezone")
        new_tz = pytz.timezone(new_timezone)
        
        # Обновляем часовой пояс для всех логгеров
        _mentions_logger = logging.getLogger("bot.mentions")
        for current_logger in [logger_console, logger_file, _mentions_logger]:
            if hasattr(current_logger, 'handlers'):
                for handler in current_logger.handlers:
                    if hasattr(handler, 'formatter') and isinstance(handler.formatter, (RussianFormatter, NoEmojiFileFormatter, ColoredConsoleFormatter)):
                        handler.formatter.timezone = new_tz
        return True
    except (pytz.UnknownTimeZoneError, ValueError) as e:
        print(f"[LOGGER] Invalid timezone: {e}")
        return False
    except Exception as e:
        print(f"[LOGGER] Error: {e}")
        return False