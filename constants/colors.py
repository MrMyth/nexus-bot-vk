# constants/colors.py

class _ColorMeta(type):
    def __getattr__(cls, name: str):
        return 0x3498DB

class Colors(metaclass=_ColorMeta):
    DEFAULT = 0x3498DB
    SUCCESS = 0x2ECC71
    ERROR = 0xE74C3C
    WARNING = 0xF1C40F
    INFO = 0x3498DB

class LoggerColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GRAY = "\033[90m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    DEBUG = "#808080"
    INFO = "#00FF00"
    WARNING = "#FFFF00"
    ERROR = "#FF0000"
    CRITICAL = "#FF00FF"

class DefaultColors(metaclass=_ColorMeta):
    DEFAULT = 0x3498DB
