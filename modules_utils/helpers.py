# helpers.py
import os
import pytz
from datetime import datetime, timedelta
from typing import Any, List, Optional, Tuple
from constants.locale_mappings import TIMEZONE_DISPLAY
from constants.emojis import LogEmojis


def get_human_timezone(timezone_region: str) -> str:
    """Возвращает локализованное, понятное человеку название часового пояса."""
    if timezone_region in TIMEZONE_DISPLAY:
        return TIMEZONE_DISPLAY[timezone_region]
    try:
        tz = pytz.timezone(timezone_region)
        now = datetime.now(tz)
        offset = now.utcoffset()
        if offset is None:
            return timezone_region
        total_minutes = int(offset.total_seconds() // 60)
        hours = total_minutes // 60
        minutes = abs(total_minutes % 60)
        sign = "+" if total_minutes >= 0 else ""
        if minutes:
            offset_str = f"{sign}{hours}:{minutes:02d}"
        else:
            offset_str = f"{sign}{hours}"
        city = timezone_region.split("/")[-1].replace("_", " ")
        return f"{city} (UTC{offset_str})"
    except Exception:
        return timezone_region


def get_full_local_time() -> str:
    """Возвращает время с учётом часового пояса в формате ДД.ММ.ГГГГ ЧЧ:ММ:СС."""
    try:
        from settings.config import Config
        tz_str = getattr(Config, "TIMEZONE_REGION", "Europe/Moscow")
        if not tz_str:
            tz_str = "Europe/Moscow"
        tz = pytz.timezone(tz_str)
        now = datetime.now(tz)
        return now.strftime("%d.%m.%Y %H:%M:%S")
    except Exception as e:
        from log_system.logger_helper import send_to_any_log
        safe_create_task(send_to_any_log("error", f"UTILS: ошибка получения времени: {e}", emoji=LogEmojis.ERROR))
        return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def bool_to_yes_no(value: bool) -> str:
    """Преобразует bool в 'Да'/'Нет'"""
    return "Да" if value else "Нет"


def universal_color_parser(color_val: Any, default: int) -> int:
    """
    Универсальный парсер цвета. Корректно определяет:
    - RGB hex-коды: '#FFB300', '0xFFB300', 'FFB300', '#FFF', 'FFF', 'f00', 'aabbccff', etc.
    - Названия цветов на русском и английском (содержит "зеленый"/"зелёный", "красный", "red" и т. д.)
    - Целочисленные (decimal) значения цветов: 16757504, '16757504'
    """
    if color_val is None:
        return default

    # Если уже целое число (и не bool)
    if isinstance(color_val, int) and not isinstance(color_val, bool):
        return color_val

    # Приводим к строке и очищаем
    val_str = str(color_val).strip()
    if not val_str:
        return default

    # Попытка распарсить как чистое десятичное число в строке (например, "16757504")
    if val_str.isdigit():
        try:
            return int(val_str)
        except (ValueError, TypeError):
            pass

    # Нормализуем для поиска по русским и английским словам:
    # убираем пробелы, дефисы, подчеркивания, приводим к нижнему регистру и заменяем ё -> е
    clean_word = val_str.lower().replace("_", "").replace("-", "").replace(" ", "").replace("ё", "е")

    color_map = {
        # Английские цвета
        "lime": 0x00ff00,
        "green": 0x2ecc71,
        "darkgreen": 0x1f8b4c,
        "lightgreen": 0x2ecc71,
        "blue": 0x3498db,
        "darkblue": 0x206694,
        "lightblue": 0x1abc9c,
        "cyan": 0x00ffff,
        "teal": 0x008080,
        "turquoise": 0x40e0d0,
        "red": 0xe74c3c,
        "darkred": 0x992d22,
        "pink": 0xe91e63,
        "hotpink": 0xff69b4,
        "fuchsia": 0xff00ff,
        "magenta": 0xe91e63,
        "purple": 0x9b59b6,
        "darkpurple": 0x71368a,
        "violet": 0x9b59b6,
        "lavender": 0xe6e6fa,
        "yellow": 0xf1c40f,
        "lemon": 0xfff700,
        "orange": 0xe67e22,
        "gold": 0xffd700,
        "silver": 0xb9bbbe,
        "bronze": 0xcd7f32,
        "copper": 0xb87333,
        "white": 0xffffff,
        "black": 0x010101,
        "gray": 0x95a5a6,
        "grey": 0x95a5a6,
        "darkgray": 0x607d8b,
        "darkgrey": 0x607d8b,
        "lightgray": 0x979c9f,
        "lightgrey": 0x979c9f,
        "charcoal": 0x36393f,
        "coral": 0xff7f50,
        "brown": 0x5c3a21,
        "chocolate": 0x7b3f00,
        "olive": 0x808000,
        "beige": 0xf5f5dc,
        "khaki": 0xf0e68c,
        "apricot": 0xfbceb1,
        "peach": 0xffe5b4,
        "emerald": 0x50c878,
        "ruby": 0xe0115f,
        "sapphire": 0x0f52ba,
        "amber": 0xffbf00,
        "mint": 0x3eb489,

        # Русские цвета
        "зеленый": 0x2ecc71,
        "темнозеленый": 0x1f8b4c,
        "светлозеленый": 0x2ecc71,
        "лайм": 0x00ff00,
        "салатовый": 0x00ff00,
        "синий": 0x3498db,
        "темносиний": 0x206694,
        "голубой": 0x1abc9c,
        "светлосиний": 0x1abc9c,
        "бирюзовый": 0x1abc9c,
        "синезеленый": 0x00ffff,
        "темнобирюзовый": 0x008080,
        "красный": 0xe74c3c,
        "темнокрасный": 0x992d22,
        "розовый": 0xe91e63,
        "яркорозовый": 0xff69b4,
        "фуксия": 0xff00ff,
        "пурпурный": 0xe91e63,
        "фиолетовый": 0x9b59b6,
        "темнофиолетовый": 0x71368a,
        "аметистовый": 0x9b59b6,
        "лавандовый": 0xe6e6fa,
        "желтый": 0xf1c40f,
        "лимонный": 0xfff700,
        "оранжевый": 0xe67e22,
        "рыжий": 0xe67e22,
        "золотой": 0xffd700,
        "золото": 0xffd700,
        "серебряный": 0xb9bbbe,
        "серебро": 0xb9bbbe,
        "бронзовый": 0xcd7f32,
        "бронза": 0xcd7f32,
        "медный": 0xb87333,
        "медь": 0xb87333,
        "белый": 0xffffff,
        "черный": 0x010101,
        "серый": 0x95a5a6,
        "темносерый": 0x607d8b,
        "светлосерый": 0x979c9f,
        "угольный": 0x36393f,
        "коралловый": 0xff7f50,
        "коричневый": 0x5c3a21,
        "бурый": 0x5c3a21,
        "шоколадный": 0x7b3f00,
        "оливковый": 0x808000,
        "бежевый": 0xf5f5dc,
        "хаки": 0xf0e68c,
        "абрикосовый": 0xfbceb1,
        "персиковый": 0xffe5b4,
        "изумрудный": 0x50c878,
        "рубиновый": 0xe0115f,
        "сапфировый": 0x0f52ba,
        "янтарный": 0xffbf00,
        "мятный": 0x3eb489,
    }

    if clean_word in color_map:
        return color_map[clean_word]

    # Разбираем как RGB: "rgb(255, 128, 0)", "255,128,0", "255 128 0"
    import re as _re
    _rgb_m = _re.match(r'^rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$', val_str.strip(), _re.IGNORECASE)
    if not _rgb_m:
        _rgb_m = _re.match(r'^(\d{1,3})\s*[,]\s*(\d{1,3})\s*[,]\s*(\d{1,3})$', val_str.strip())
    if _rgb_m:
        _r, _g, _b = int(_rgb_m.group(1)), int(_rgb_m.group(2)), int(_rgb_m.group(3))
        if all(0 <= v <= 255 for v in (_r, _g, _b)):
            return (_r << 16) | (_g << 8) | _b

    # Теперь разбираем как hex
    clean_hex = val_str.lower().strip()
    if clean_hex.startswith('#'):
        clean_hex = clean_hex[1:]
    elif clean_hex.startswith('0x'):
        clean_hex = clean_hex[2:]
    # Содержит ли только hex-символы?
    if clean_hex and all(c in '0123456789abcdef' for c in clean_hex):
        if len(clean_hex) == 6:
            try:
                return int(clean_hex, 16)
            except ValueError:
                pass
        elif len(clean_hex) == 3:
            # Превращаем f00 в ff0000
            expanded = "".join(c + c for c in clean_hex)
            try:
                return int(expanded, 16)
            except ValueError:
                pass
        elif len(clean_hex) == 8:
            # Превращаем, например, aabbccff в aabbcc
            try:
                return int(clean_hex[:6], 16)
            except ValueError:
                pass

    return default


def hex_to_color_int(hex_color: Any, default: int = 0x4568DC) -> int:
    """
    Преобразует hex-цвет (#RRGGBB) или название цвета в целое число для Discord embed.
    """
    return universal_color_parser(hex_color, default)


def parse_color_to_int(color_str: Any, default: int = 0x00FF00) -> int:
    """
    Преобразует строковое или числовое представление цвета (название цвета или hex) в int.
    """
    return universal_color_parser(color_str, default)


def format_uptime(td: timedelta) -> str:
    """Форматирует timedelta в читаемую строку."""
    total_seconds = int(td.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}д")
    if hours > 0:
        parts.append(f"{hours}ч")
    if minutes > 0:
        parts.append(f"{minutes}м")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}с")
    return " ".join(parts)


def format_uptime_seconds(seconds: float) -> str:
    """Форматирует секунды в читаемый вид."""
    return format_uptime(timedelta(seconds=seconds))


def pluralize(n: int, forms: List[str]) -> str:
    """Склоняет слово по числам."""
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return forms[1]
    else:
        return forms[2]


def format_check_interval(seconds: int) -> str:
    if seconds < 60:
        return f"Каждые {seconds} секунд"
    minutes = seconds // 60
    remainder = seconds % 60
    if seconds == 60:
        return "Каждую минуту"
    if remainder == 0:
        if minutes == 1:
            return "Каждую минуту"
        elif 2 <= minutes <= 4:
            return f"Каждые {minutes} минуты"
        else:
            return f"Каждые {minutes} минут"
    else:
        if minutes == 1:
            min_str = "минуту"
        elif 2 <= minutes <= 4:
            min_str = f"{minutes} минуты"
        else:
            min_str = f"{minutes} минут"
        return f"Каждые {min_str} {remainder} сек"


def get_best_photo_url(photo: Optional[dict]) -> Optional[str]:
    """
    Извлекает лучший URL фотографии из объекта VK Photo.
    Учитывает ширину и типы размеров (w > z > y > x > m > s).
    """
    if not photo or not isinstance(photo, dict):
        return None
    
    sizes = photo.get("sizes", [])
    if not sizes:
        return None

    # Порядок типов размеров от лучшего к худшему
    type_priority = {"w": 6, "z": 5, "y": 4, "x": 3, "m": 2, "s": 1}

    def sort_key(size):
        width = size.get("width", 0)
        height = size.get("height", 0)
        # Если есть размеры, приоритет им
        if width > 0 or height > 0:
            return (1, width * height)
        # Если размеров нет, приоритет типу
        size_type = size.get("type", "s")
        return (0, type_priority.get(size_type, 0))

    try:
        sorted_sizes = sorted(sizes, key=sort_key, reverse=True)
        best_size = sorted_sizes[0]
        url = best_size.get("url")
        if url and isinstance(url, str) and url.startswith("http"):
            return url
    except Exception:
        pass

    # Последний шанс: просто первый URL
    for size in sizes:
        url = size.get("url")
        if url and isinstance(url, str) and url.startswith("http"):
            return url
            
    return None


def _clean_value(value: Optional[str]) -> Optional[str]:
    """Удаляет внешние кавычки и пробелы."""
    if isinstance(value, str):
        return value.strip().strip("'\"")
    return value


def _str_to_bool(value: Optional[str], default: bool) -> bool:
    """Преобразует строку в bool с поддержкой 'да/нет', 'yes/no'."""
    if not value:
        return default
    v = value.strip().lower()
    true_values = {"true", "1", "yes", "да", "on"}
    false_values = {"false", "0", "no", "нет", "off"}
    if v in true_values:
        return True
    elif v in false_values:
        return False
    from log_system.logger_helper import send_to_any_log
    safe_create_task(send_to_any_log("warning", f"CONFIG: Нераспознанное булево значение: '{value}' → используется значение по умолчанию: {default}", emoji=LogEmojis.WARNING))
    return default


def _get_str(env_name: str, default: str) -> str:
    """Получает строку из env с очисткой."""
    value = _clean_value(os.getenv(env_name))
    return value if value is not None else default


def _get_bool(env_name: str, default: bool) -> bool:
    """Получает bool из env."""
    value = _clean_value(os.getenv(env_name))
    return _str_to_bool(value, default)


def _get_int_or_none(env_name: str, default: Optional[int] = None) -> Optional[int]:
    """Получает int или None. Поддерживает отрицательные числа."""
    value = _clean_value(os.getenv(env_name))
    if value:
        try:
            return int(value)
        except (ValueError, TypeError):
            pass
    return default


def _get_int(env_name: str, default: int) -> int:
    """Получает целое число из env."""
    value = _clean_value(os.getenv(env_name))
    if value:
        try:
            return int(value)
        except ValueError:
            from log_system.logger_helper import send_to_any_log
            safe_create_task(send_to_any_log("warning", f"CONFIG: Некорректное числовое значение для {env_name}: '{value}'. Используется: {default}", emoji=LogEmojis.WARNING))
    return default


def _get_float(env_name: str, default: float) -> float:
    """Получает вещественное число из env."""
    value = _clean_value(os.getenv(env_name))
    if value:
        try:
            return float(value)
        except ValueError:
            from log_system.logger_helper import send_to_any_log
            safe_create_task(send_to_any_log("warning", f"CONFIG: Некорректное вещественное значение для {env_name}: '{value}'. Используется: {default}", emoji=LogEmojis.WARNING))
    return default


def _get_int_list(env_name: str, default: List[int]) -> List[int]:
    """Получает список целых чисел из env (разделенные запятой)."""
    value = _clean_value(os.getenv(env_name))
    if not value:
        return default
    try:
        return [int(x.strip()) for x in value.split(",") if x.strip()]
    except ValueError:
        from log_system.logger_helper import send_to_any_log
        safe_create_task(send_to_any_log("warning", f"CONFIG: Некорректный список чисел для {env_name}: '{value}'. Используется: {default}", emoji=LogEmojis.WARNING))
        return default


def cleanup_pycache(root_dir: str = "."):
    """Рекурсивно удаляет все папки __pycache__ в указанной директории."""
    import shutil
    import os
    for root, dirs, files in os.walk(root_dir):
        if "__pycache__" in dirs:
            pycache_path = os.path.join(root, "__pycache__")
            try:
                shutil.rmtree(pycache_path)
            except Exception:
                pass


# Глобальный реестр живых задач, созданных через safe_create_task.
# Задача добавляется при создании и автоматически удаляется через done-callback.
_live_tasks: set = set()


def safe_create_task(coro, *, name: str | None = None):
    """
    Безопасно создаёт asyncio задачу и регистрирует её в глобальном реестре.
    Если цикл не запущен или discord.py подставил _MissingSentinel, возвращает None.

    :param name: необязательное имя задачи (для отладки через asyncio.all_tasks()).
    """
    import asyncio
    from discord.utils import MISSING  # noqa: PLC0415 — отложенный импорт: нужен после инициализации discord.py
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()  # избегаем RuntimeWarning: coroutine was never awaited
            return None

        if loop is None or loop is MISSING:
            coro.close()
            return None

        create_task_method = getattr(loop, 'create_task', None)
        if create_task_method and callable(create_task_method):
            task = loop.create_task(coro, name=name)
            _live_tasks.add(task)
            task.add_done_callback(_live_tasks.discard)
            return task
        coro.close()
    except Exception as e:
        # Не поднимаем исключение выше (вызывающий код может быть sync-контекстом),
        # но оставляем минимальный след в логгере для диагностики.
        from log_system.logger_helper import send_log_to_console
        send_log_to_console("error", f"safe_create_task: не удалось создать задачу: {e}", emoji=LogEmojis.ERROR)
        try:
            coro.close()
        except Exception:
            pass
    return None


def get_tracked_task_count() -> int:
    """Возвращает число активных задач, созданных через safe_create_task."""
    return len(_live_tasks)


async def cancel_all_tracked_tasks() -> int:
    """
    Отменяет все активные задачи реестра и ожидает их завершения.
    Предназначен для вызова при плановом останове бота (bot.stop()).
    Текущая задача (вызвавшая эту функцию) намеренно исключается:
    её отмена привела бы к self-cancellation deadlock внутри asyncio.gather.
    Возвращает количество отменённых задач.
    """
    import asyncio
    current = asyncio.current_task()
    tasks = [t for t in list(_live_tasks) if not t.done() and t is not current]
    if not tasks:
        return 0
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    return len(tasks)


def resolve_asset_url(path: Optional[str]) -> Optional[str]:
    """
    Разрешает путь к ассету.
    Если включен USE_LOCAL_ASSETS=True, принудительно возвращает относительный локальный путь (игнорируя ASSETS_BASE_URL).
    Иначе, если это локальный путь (не начинается с http) и задан ASSETS_BASE_URL в конфиге, возвращает полный URL.
    """
    if not path or not isinstance(path, (str, bytes)):
        return path
    
    # Если байты, возвращаем как есть (например, для иконок)
    if isinstance(path, bytes):
        return path

    path_str = str(path).strip()
    if not path_str:
        return path_str

    from settings.config import Config
    use_local = getattr(Config, "USE_LOCAL_ASSETS", False)

    if use_local:
        if path_str.startswith(('http://', 'https://')):
            if 'assets/' in path_str:
                rel_path = 'assets/' + path_str.split('assets/', 1)[1]
                if os.path.isfile(rel_path):
                    return rel_path
            return path_str
        return path_str

    if path_str.startswith(('http://', 'https://')):
        return path_str
        
    base_url = getattr(Config, "ASSETS_BASE_URL", "").strip()
    if not base_url:
        return path_str
        
    # Чистим base_url от слеша в конце и path от слеша в начале
    base_url = base_url.rstrip('/')
    clean_path = path_str.lstrip('./').lstrip('/')
    
    return f"{base_url}/{clean_path}"


def prepare_embed_local_files(embed: Any) -> List[Any]:
    """
    Сканирует discord.Embed на наличие локальных путей к файлам ассетов.
    Если путь является локальным существующим файлом, создаёт discord.File
    и заменяет URL на attachment://filename.
    Возвращает список созданных discord.File для передачи в send(embed=embed, files=files).
    """
    import discord
    files = []

    def process_url(url_val: Optional[str]) -> Tuple[Optional[str], Optional[discord.File]]:
        if not url_val or not isinstance(url_val, str):
            return url_val, None
        u_str = url_val.strip()
        if u_str.startswith(('http://', 'https://', 'attachment://', 'data:')):
            return u_str, None

        candidate = u_str.lstrip('./').lstrip('/')
        if os.path.isfile(candidate):
            fname = os.path.basename(candidate)
            try:
                f = discord.File(candidate, filename=fname)
                return f"attachment://{fname}", f
            except Exception:
                pass
        elif os.path.isfile(u_str):
            fname = os.path.basename(u_str)
            try:
                f = discord.File(u_str, filename=fname)
                return f"attachment://{fname}", f
            except Exception:
                pass

        return u_str, None

    if hasattr(embed, 'image') and embed.image and getattr(embed.image, 'url', None):
        new_url, f = process_url(embed.image.url)
        if f:
            embed.set_image(url=new_url)
            files.append(f)

    if hasattr(embed, 'thumbnail') and embed.thumbnail and getattr(embed.thumbnail, 'url', None):
        new_url, f = process_url(embed.thumbnail.url)
        if f:
            embed.set_thumbnail(url=new_url)
            files.append(f)

    if hasattr(embed, 'author') and embed.author and getattr(embed.author, 'icon_url', None):
        new_url, f = process_url(embed.author.icon_url)
        if f:
            embed.set_author(name=embed.author.name or "", url=embed.author.url, icon_url=new_url)
            files.append(f)

    if hasattr(embed, 'footer') and embed.footer and getattr(embed.footer, 'icon_url', None):
        new_url, f = process_url(embed.footer.icon_url)
        if f:
            embed.set_footer(text=embed.footer.text or "", icon_url=new_url)
            files.append(f)

    return files


def clean_vk_token(token: Optional[str]) -> Optional[str]:
    """
    Извлекает чистый токен доступа VK из любой переданной строки (чистый токен, ссылка, фрагмент).
    """
    if not token or not isinstance(token, str):
        return token
    # Очищаем от внешних кавычек и концевых пробелов
    token_str = token.strip().strip("'\"")
    # Попробуем найти access_token= в URL или фрагменте
    import re
    match = re.search(r"access_token=([^&'\"]+)", token_str)
    if match:
        return match.group(1).strip()
    return token_str


def get_vk_token_description(token: Optional[str]) -> str:
    """
    Возвращает понятное текстовое описание типа и маски токена VK.
    """
    cleaned = clean_vk_token(token)
    if not cleaned:
        return "отсутствует"
    
    # Пытаемся понять тип токена
    if cleaned.startswith("vk1.a."):
        token_type = "Пользовательский / Специфический токен (User/Group Token, начинается с vk1.a.)"
    elif all(c in "0123456789abcdefABCDEF" for c in cleaned) and len(cleaned) >= 32:
        token_type = f"Сервисный ключ доступа / Ключ приложения (Service Access Token, hex-{len(cleaned)})"
    elif len(cleaned) == 85 and cleaned.startswith("vk1.s."):
        token_type = "Сервисный токен VK (начинается с vk1.s.)"
    else:
        # Универсальное определение
        if len(cleaned) > 40:
            token_type = f"Длинный токен VK ({len(cleaned)} симв.)"
        else:
            token_type = f"Короткий ключ/токен ({len(cleaned)} симв.)"
            
    # Маскируем токен
    if len(cleaned) <= 8:
        masked = "****"
    else:
        masked = f"{cleaned[:6]}...{cleaned[-6:]}"
        
    return f"{token_type} [маска: {masked}]"


def load_webhooks_metadata(platform_key: Optional[str] = None) -> dict:
    """
    Загружает конфигурацию вебхуков из data/json/system_configs/webhooks_metadata.json.
    Возвращает словарь с ключами webhook_username и webhook_avatar_url.
    """
    import json
    try:
        from settings.data_files import Files
        config_path = getattr(Files, "WEBHOOKS_METADATA_CONFIG_PATH", "data/json/system_configs/webhooks_metadata.json")
    except Exception:
        config_path = "data/json/system_configs/webhooks_metadata.json"

    if not os.path.exists(config_path):
        config_path = os.path.join(os.getcwd(), "data", "json", "system_configs", "webhooks_metadata.json")

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_meta = data.get("default", {})
                platforms = data.get("platforms", {})

                if platform_key and platform_key in platforms:
                    merged = dict(default_meta)
                    merged.update(platforms[platform_key])
                    return merged

                return default_meta
        except Exception as e:
            from log_system.logger_helper import send_to_any_log
            safe_create_task(send_to_any_log("error", f"HELPERS: ошибка чтения webhooks_metadata.json: {e}", emoji=LogEmojis.ERROR))

    return {
        "webhook_username": "AutoNotifier",
        "webhook_avatar_url": "assets/images/bot-image/thedivision2-icon.png"
    }



