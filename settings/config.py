# config.py
from modules_utils.helpers import (
    _get_str,
    _get_bool,
    _get_int,
    _get_float,
    _get_int_or_none,
    _get_int_list,
    clean_vk_token
)

class Config:
    # --- Основные настройки ---
    COMMAND_PREFIX = _get_str("COMMAND_PREFIX", _get_str("BOT_PREFIX", "!"))
    VK_TOKEN = clean_vk_token(_get_str("VK_TOKEN", ""))
    DISCORD_BOT_TOKEN = _get_str("DISCORD_BOT_TOKEN", "")
    BOT_USERNAME = _get_str("BOT_USERNAME", "")
    BOT_NICKNAME = _get_str("BOT_NICKNAME", "")
    DISCORD_SEND_CONCURRENCY = _get_int("DISCORD_SEND_CONCURRENCY", 3)
    DISCORD_SEND_THROTTLE_SEC = _get_float("DISCORD_SEND_THROTTLE_SEC", 0.5)
    TELEGRAM_BOT_TOKEN = _get_str("TELEGRAM_BOT_TOKEN", "")
    SERVER_ID = _get_int_or_none("SERVER_ID")
    
    # --- Модули ---
    ENABLE_VK_WALL_MONITORING = _get_bool("ENABLE_VK_WALL_MONITORING", True)
    ENABLE_VK_LIVE_MONITORING = _get_bool("ENABLE_VK_LIVE_MONITORING", True)
    ENABLE_USER_ACTIVITY_MODULE = _get_bool("ENABLE_USER_ACTIVITY_MODULE", True)
    ENABLE_DISCORD_CHANNEL_PROTECTION = _get_bool("ENABLE_DISCORD_CHANNEL_PROTECTION", True)
    ENABLE_AUTO_PUBLISH = _get_bool("ENABLE_AUTO_PUBLISH", True)
    AUTO_PROTECT_POSTING_CHANNELS = _get_bool("AUTO_PROTECT_POSTING_CHANNELS", True)
    DISABLE_CHAT_IN_VOICE = _get_bool("DISABLE_CHAT_IN_VOICE", True)
    BLOCK_SENDING_INSTEAD_OF_DELETE = _get_bool("BLOCK_SENDING_INSTEAD_OF_DELETE", False)
    PROTECT_EVERYONE_HERE_MENTIONS = _get_bool("PROTECT_EVERYONE_HERE_MENTIONS", True)
    EVERYONE_HERE_BYPASS_ROLE_IDS = _get_int_list("EVERYONE_HERE_BYPASS_ROLE_IDS", [])
    ENABLE_TELEGRAM_MODULE = _get_bool("ENABLE_TELEGRAM_MODULE", False)
    ENABLE_TRELLO_MODULE = _get_bool("ENABLE_TRELLO_MODULE", False)
    ENABLE_PDF_MONITOR_MODULE = _get_bool("ENABLE_PDF_MONITOR_MODULE", False)
    ENABLE_ROLE_DEPENDENCY_MODULE = _get_bool("ENABLE_ROLE_DEPENDENCY_MODULE", False)
    ENABLE_YOUTUBE_MONITORING = _get_bool("ENABLE_YOUTUBE_MONITORING", False)
    ENABLE_RUTUBE_MONITORING = _get_bool("ENABLE_RUTUBE_MONITORING", False)
    ENABLE_TWITCH_LIVE_MONITORING = _get_bool("ENABLE_TWITCH_LIVE_MONITORING", False)
    ENABLE_KICK_LIVE_MONITORING = _get_bool("ENABLE_KICK_LIVE_MONITORING", False)
    ENABLE_TROVO_MONITORING = _get_bool("ENABLE_TROVO_MONITORING", False)
    ENABLE_VK_COM_LIVE_MONITORING = _get_bool("ENABLE_VK_COM_LIVE_MONITORING", False)
    ENABLE_GOODGAME_MONITORING = _get_bool("ENABLE_GOODGAME_MONITORING", False)
    ENABLE_VK_ASSETS_MONITORING = _get_bool("ENABLE_VK_ASSETS_MONITORING", False)
    ENABLE_VOICE_REGION_MODULE = _get_bool("ENABLE_VOICE_REGION_MODULE", True)
    ENABLE_NO_ROLE_NOTIFICATION = _get_bool("ENABLE_NO_ROLE_NOTIFICATION", True)
    NO_ROLE_NOTIFICATION_ROLE_ID = _get_int_or_none("NO_ROLE_NOTIFICATION_ROLE_ID")
    ENABLE_GAME_TRACKER_MODULE = _get_bool("ENABLE_GAME_TRACKER_MODULE", True)
    GAME_TRACKER_CHANNEL_ID = _get_int_or_none("GAME_TRACKER_CHANNEL_ID")
    GAME_TRACKER_IGNORE_ROLE_IDS = _get_int_list("GAME_TRACKER_IGNORE_ROLE_IDS", [])
    ENABLE_SECRET_VENDORS_MODULE = _get_bool("ENABLE_SECRET_VENDORS_MODULE", True)
    SECRET_VENDORS_CHANNEL_ID = _get_int_or_none("SECRET_VENDORS_CHANNEL_ID")
    SECRET_VENDORS_ROLE_ID = _get_int_or_none("SECRET_VENDORS_ROLE_ID")
    SECRET_VENDORS_WEBHOOK_URL = _get_str("SECRET_VENDORS_WEBHOOK_URL", "")

    ENABLE_GAME_SCHEDULE_MODULE = _get_bool("ENABLE_GAME_SCHEDULE_MODULE", True)
    GAME_SCHEDULE_CHANNEL_ID = _get_int_or_none("GAME_SCHEDULE_CHANNEL_ID")
    GAME_SCHEDULE_ROLE_ID = _get_int_or_none("GAME_SCHEDULE_ROLE_ID")
    GAME_SCHEDULE_WEBHOOK_URL = _get_str("GAME_SCHEDULE_WEBHOOK_URL", "")

    ENABLE_IMAGE_FORWARDER_MODULE = _get_bool("ENABLE_IMAGE_FORWARDER_MODULE", True)
    IMAGE_FORWARDER_SOURCE_CHANNEL_ID = _get_int_or_none("IMAGE_FORWARDER_SOURCE_CHANNEL_ID")
    IMAGE_FORWARDER_TARGET_CHANNEL_ID = _get_int_or_none("IMAGE_FORWARDER_TARGET_CHANNEL_ID")

    # --- Настройки Стриминга (Live) ---
    DEFAULT_LIVE_ROLE_ID = _get_int_or_none("DEFAULT_LIVE_ROLE_ID")
    DEFAULT_LIVE_PING_ROLE_ID = _get_int_or_none("DEFAULT_LIVE_PING_ROLE_ID")

    # --- Настройки Модуля Активности (User Activity) ---
    USER_ACTIVITY_LOG_CHANNEL_ID = _get_int_or_none("USER_ACTIVITY_LOG_CHANNEL_ID")
    USER_ACTIVITY_IGNORE_ROLE_IDS = _get_int_list("USER_ACTIVITY_IGNORE_ROLE_IDS", [])
    USER_ACTIVITY_MANAGE_ROLES = _get_bool("USER_ACTIVITY_MANAGE_ROLES", True)
    AFK_DAYS_THRESHOLD = _get_int("AFK_DAYS_THRESHOLD", 180)
    ACTIVE_ROLE_ID = _get_int_or_none("ACTIVE_ROLE_ID")
    AFK_ROLE_ID = _get_int_or_none("AFK_ROLE_ID")
    USER_ACTIVITY_REQUIRED_ROLE_ID = _get_int_or_none("USER_ACTIVITY_REQUIRED_ROLE_ID")
    FULL_LOG_USER_ACTIVITY = _get_bool("FULL_LOG_USER_ACTIVITY", False)

    # --- Настройки VK Assets модуля ---
    VK_ASSETS_CHECK_INTERVAL = _get_int("VK_ASSETS_CHECK_INTERVAL", 600)
    YOUTUBE_API_KEY = _get_str("YOUTUBE_API_KEY", "")

    # --- Настройки Twitch модуля ---
    TWITCH_CLIENT_ID = _get_str("TWITCH_CLIENT_ID", "")
    TWITCH_CLIENT_SECRET = _get_str("TWITCH_CLIENT_SECRET", "")
    TWITCH_USE_SCRAPER_PRIMARY = _get_bool("TWITCH_USE_SCRAPER_PRIMARY", True)

    # --- Настройки Trello модуля ---
    TRELLO_POLL_INTERVAL = _get_int_or_none("TRELLO_POLL_INTERVAL", 1800)  # 30 минут

    # --- Настройки PDF Monitor модуля ---
    PDF_CHECK_INTERVAL = _get_int_or_none("PDF_CHECK_INTERVAL", 1800)  # 30 минут
    PDF_MENTION_ROLE_ID = _get_int_or_none("PDF_MENTION_ROLE_ID")
    PDF_CHANNEL_ID = _get_int_or_none("PDF_CHANNEL_ID")

    # --- Пути ---
    DATA_FOLDER = _get_str("DATA_FOLDER", "data")
    SAVE_STREAM_PREVIEW_FOLDER = _get_str("SAVE_STREAM_PREVIEW_FOLDER", "save_stream_preview")
    SAVE_STREAM_PREVIEW_RETENTION_DAYS = _get_int("SAVE_STREAM_PREVIEW_RETENTION_DAYS", _get_int("STREAM_PREVIEW_RETENTION_DAYS", 365))
    FOLLOWS_CONFIGS_FOLDER = _get_str("FOLLOWS_CONFIGS_FOLDER", "data/json")
    LOG_FILE_NAME = _get_str("LOG_FILE_NAME", "bot.log")
    MENTIONS_LOG_FILE_NAME = _get_str("MENTIONS_LOG_FILE_NAME", "mentions.log")
    VK_POSTS_DB_FILE_NAME = _get_str("VK_POSTS_DB_FILE_NAME", "processed_posts.db")
    VK_LIVE_DB_FILE_NAME = _get_str("VK_LIVE_DB_FILE_NAME", "vk_live.db")
    VK_CHANNEL_STREAM_DB_FILE_NAME = _get_str("VK_CHANNEL_STREAM_DB_FILE_NAME", "channel_vk_stream.db")
    VK_CHANNEL_VIDEO_DB_FILE_NAME = _get_str("VK_CHANNEL_VIDEO_DB_FILE_NAME", "channel_vk_video.db")
    STREAM_TOOLS_CONFIG_FILE_NAME = _get_str("STREAM_TOOLS_CONFIG_FILE_NAME", "apps.json")
    VOICE_CHANNEL_FILE_NAME = _get_str("VOICE_CHANNEL_FILE_NAME", "protected_channels_voice.json")
    CHANNEL_PROTECTION_LIST_FILE_NAME = _get_str("CHANNEL_PROTECTION_LIST_FILE_NAME", "protected_channels.json")
    CACHE_FILE_NAME = _get_str("CACHE_FILE_NAME", "group_cache.json")
    LIVE_CACHE_FILE_NAME = _get_str("LIVE_CACHE_FILE_NAME", "VK_Live_cache.json")
    VIDEO_CACHE_FILE_NAME = _get_str("VIDEO_CACHE_FILE_NAME", "VK_Video_cache.json")
    TRELLO_CACHE_FILE_NAME = _get_str("TRELLO_CACHE_FILE_NAME", "trello_cache.json")
    TELEGRAM_CACHE_FILE_NAME = _get_str("TELEGRAM_CACHE_FILE_NAME", "telegram_cache.json")
    PDF_CACHE_FILE_NAME = _get_str("PDF_CACHE_FILE_NAME", "pdf_cache.json")
    YOUTUBE_DATABASE_FILE_NAME = _get_str("YOUTUBE_DATABASE_FILE_NAME", "youtube_live.db")
    RUTUBE_DATABASE_FILE_NAME = _get_str("RUTUBE_DATABASE_FILE_NAME", "rutube_live.db")
    TWITCH_DATABASE_FILE_NAME = _get_str("TWITCH_DATABASE_FILE_NAME", "twitch_live.db")
    KICK_DATABASE_FILE_NAME = _get_str("KICK_DATABASE_FILE_NAME", "kick_live.db")
    TROVO_DATABASE_FILE_NAME = _get_str("TROVO_DATABASE_FILE_NAME", "trovo_live.db")
    VK_COM_LIVE_DATABASE_FILE_NAME = _get_str("VK_COM_LIVE_DATABASE_FILE_NAME", "vk_com_live.db")
    GOODGAME_DATABASE_FILE_NAME = _get_str("GOODGAME_DATABASE_FILE_NAME", "goodgame_live.db")
    VK_ASSETS_DATABASE_FILE_NAME = _get_str("VK_ASSETS_DATABASE_FILE_NAME", "vk_assets.db")
    USER_ACTIVITY_DATABASE_FILE_NAME = _get_str("USER_ACTIVITY_DATABASE_FILE_NAME", "user_activity.db")
    ROLE_DEPENDENCY_CONFIG_FILE_NAME = _get_str("ROLE_DEPENDENCY_CONFIG_FILE_NAME", "role_dependencies.json")
    ROLE_DEPENDENCY_CHECK_INTERVAL = _get_int("ROLE_DEPENDENCY_CHECK_INTERVAL", 1800)
    ROLE_DEPENDENCY_IMMEDIATE_CHECK = _get_bool("ROLE_DEPENDENCY_IMMEDIATE_CHECK", True)
    
    # --- Настройки мониторов ---
    VK_WALL_CHECK_INTERVAL = _get_int("VK_WALL_CHECK_INTERVAL", 300)
    VK_LIVE_CHECK_INTERVAL = _get_int("VK_LIVE_CHECK_INTERVAL", 300)

    # --- Circuit breaker для VK-мониторов ---
    VK_CIRCUIT_BREAKER_ENABLED = _get_bool("VK_CIRCUIT_BREAKER_ENABLED", True)
    VK_CIRCUIT_BREAKER_THRESHOLD = _get_int("VK_CIRCUIT_BREAKER_THRESHOLD", 5)
    VK_CIRCUIT_BREAKER_PAUSE_MINUTES = _get_int("VK_CIRCUIT_BREAKER_PAUSE_MINUTES", 30)

    # --- Адаптивный интервал polling ---
    VK_ADAPTIVE_POLLING_ENABLED = _get_bool("VK_ADAPTIVE_POLLING_ENABLED", True)
    VK_ADAPTIVE_POLLING_MAX_MULTIPLIER = _get_int("VK_ADAPTIVE_POLLING_MAX_MULTIPLIER", 6)
    VK_ADAPTIVE_POLLING_IDLE_HOURS = _get_int("VK_ADAPTIVE_POLLING_IDLE_HOURS", 2)
    YOUTUBE_CHECK_INTERVAL = _get_int("YOUTUBE_CHECK_INTERVAL", 420)
    TWITCH_CHECK_INTERVAL = _get_int("TWITCH_CHECK_INTERVAL", 300)
    RUTUBE_CHECK_INTERVAL = _get_int("RUTUBE_CHECK_INTERVAL", 300)
    TROVO_CHECK_INTERVAL = _get_int("TROVO_CHECK_INTERVAL", 300)
    VK_COM_LIVE_CHECK_INTERVAL = _get_int("VK_COM_LIVE_CHECK_INTERVAL", 300)
    GOODGAME_CHECK_INTERVAL = _get_int("GOODGAME_CHECK_INTERVAL", 300)

    # --- Настройки логов ---
    DISABLE_LOGGER = _get_bool("DISABLE_LOGGER", False)
    LOG_FILE_ENCODING = _get_str("LOG_FILE_ENCODING", "utf-8")
    GLOBAL_LOG_CHANNEL_ID = _get_int_or_none("GLOBAL_LOG_CHANNEL_ID")
    ALERT_ROLE_ID = _get_int_or_none("ALERT_ROLE_ID")
    
    # --- Настройки ловушки бана (Auto-Ban Trap) ---
    AUTO_BAN_CHANNEL_ID = _get_int_or_none("AUTO_BAN_CHANNEL_ID")
    AUTO_BAN_ROLE_ID = _get_int_or_none("AUTO_BAN_ROLE_ID")
    
    TELEGRAM_EXCLUDED_VOICE_CHANNELS = _get_str("TELEGRAM_EXCLUDED_VOICE_CHANNELS", "")
    TELEGRAM_CHANNEL_ID = _get_str("TELEGRAM_CHANNEL_ID", "")
    TELEGRAM_THREAD_ID = _get_int_or_none("TELEGRAM_THREAD_ID")  # ID темы/комнаты

    # --- Telegram-уведомления о стримах/видео (per-config telegram_notifications) ---
    # Используются как значения по умолчанию, если конкретный конфиг канала (JSON)
    # не переопределяет chat_id/thread_id/bot_token. Приоритет токена: JSON bot_token ->
    # TELEGRAM_STREAM_BOT_TOKEN. TELEGRAM_BOT_TOKEN (бот голосовых уведомлений) как резерв
    # не используется — без TELEGRAM_STREAM_BOT_TOKEN стрим-уведомления не отправляются.
    TELEGRAM_STREAM_CHAT_ID = _get_str("TELEGRAM_STREAM_CHAT_ID", "")
    TELEGRAM_STREAM_THREAD_ID = _get_int_or_none("TELEGRAM_STREAM_THREAD_ID")
    # Отдельный бот для стрим-уведомлений (обязателен для отправки, без резерва)
    TELEGRAM_STREAM_BOT_TOKEN = _get_str("TELEGRAM_STREAM_BOT_TOKEN", "")
    
    # --- Остальные настройки ---
    EMBED_COLOR = _get_str("EMBED_COLOR", "lime")
    RETENTION_DAYS = _get_int("RETENTION_DAYS", 90)
    VK_MAX_SILENCE_DAYS = _get_int("VK_MAX_SILENCE_DAYS", 7)
    TIMEZONE_REGION = _get_str("TIMEZONE_REGION", "Europe/Moscow")
    LOCALE = _get_str("LOCALE", _get_str("BOT_LOCALE", "ru")).lower()
    
    # --- JSON ---
    JSON_ENSURE_ASCII = _get_bool("JSON_ENSURE_ASCII", False)
    JSON_INDENT = _get_int_or_none("JSON_INDENT", 2)
    
    # --- Флаги ---
    USE_GROUP_AVATAR_AS_DEFAULT = _get_bool("USE_GROUP_AVATAR_AS_DEFAULT", False)
    USE_GROUP_COVER_AS_PREVIEW = _get_bool("USE_GROUP_COVER_AS_PREVIEW", False)
    KEYBOARD_INTERRUPT_MODE = _get_str("KEYBOARD_INTERRUPT_MODE", "stop") # stop, restart, ignore
    # Поведение при неперехваченной критической ошибке в run_forever():
    # interactive — текущее поведение (ждать ~6 мин + спросить в консоли stop/restart, актуально для локального запуска);
    # restart — короткая пауза и автоматический перезапуск без ожидания/stdin (для серверного/headless режима);
    # stop — короткая пауза и остановка без ожидания/stdin.
    CRITICAL_ERROR_MODE = _get_str("CRITICAL_ERROR_MODE", "interactive")
    CRITICAL_ERROR_AUTO_DELAY = _get_int_or_none("CRITICAL_ERROR_AUTO_DELAY", 10) or 10
    DISABLE_EMOJI_CONSOLE = _get_bool("DISABLE_EMOJI_CONSOLE", False)
    DISABLE_EMOJI_FILE = _get_bool("DISABLE_EMOJI_FILE", False)
    DISABLE_EMOJI_DISCORD = _get_bool("DISABLE_EMOJI_DISCORD", False)
    CHECK_POST_EDITS = _get_bool("CHECK_POST_EDITS", True)
    SILENT_DUPLICATES = _get_bool("SILENT_DUPLICATES", True)
    DISABLE_BOT = _get_bool("DISABLE_BOT", False)
    
    # --- Discord intents ---
    INTENTS_MESSAGE_CONTENT = _get_bool("INTENTS_MESSAGE_CONTENT", True)
    INTENTS_PRESENCES = _get_bool("INTENTS_PRESENCES", True)
    INTENTS_MEMBERS = _get_bool("INTENTS_MEMBERS", True)
    INTENTS_VOICE_STATES = _get_bool("INTENTS_VOICE_STATES", True)
    ENABLE_GUILD_CHUNKING = _get_bool("ENABLE_GUILD_CHUNKING", True)
    ASSETS_BASE_URL = _get_str("ASSETS_BASE_URL", "")
    USE_LOCAL_ASSETS = _get_bool("USE_LOCAL_ASSETS", False)
    HEARTBEAT_INTERVAL = _get_int("HEARTBEAT_INTERVAL", 900)

    # --- Настройки HTTP-клиента ---
    HTTP_TIMEOUT_TOTAL = _get_int("HTTP_TIMEOUT_TOTAL", 45)
    HTTP_TIMEOUT_CONNECT = _get_int("HTTP_TIMEOUT_CONNECT", 10)
    HTTP_VERIFY_SSL = _get_bool("HTTP_VERIFY_SSL", True)

    # --- Настройки VK API ---
    VK_RATE_LIMIT_RETRY_DELAY = _get_int("VK_RATE_LIMIT_RETRY_DELAY", 1)

    # --- Настройки Discord-мероприятий (Events) ---
    STREAM_EVENT_DURATION_HOURS = _get_int("STREAM_EVENT_DURATION_HOURS", 1)
    STREAM_EVENT_EXTENSION_THRESHOLD_MINUTES = _get_int("STREAM_EVENT_EXTENSION_THRESHOLD_MINUTES", 30)

    # --- Настройки Twitch EventSub ---
    TWITCH_EVENTSUB_MAX_RETRIES = _get_int("TWITCH_EVENTSUB_MAX_RETRIES", 3)

    # --- Внутренние флаги состояния ---
    TELEGRAM_MONITOR_ALL_VOICE_CHANNELS = _get_bool("TELEGRAM_MONITOR_ALL_VOICE_CHANNELS", True)
    USE_AUTO_RESTART = _get_bool("USE_AUTO_RESTART", True)
    AUTO_RESTART_INTERVAL_MINUTES = _get_int_or_none("AUTO_RESTART_INTERVAL_MINUTES")
    IS_LOCAL_LAUNCH = _get_bool("IS_LOCAL_LAUNCH", False)
