# constants/strings.py
import json
import os
from typing import Dict, Any, Optional

_STRINGS_CACHE: Optional[Dict[str, Any]] = None

_DEFAULT_STRINGS: Dict[str, Any] = {
    # App & Bot Info
    "APP_NAME": "Nexus Bot",
    "DEFAULT_FOOTER_TEXT": "Nexus Bot",
    "BOT_VERSION": "4.1",
    "BOT_VERSION_DATE": "11.08.2026 13:50 по Москве",
    "BOT_VERSION_FULL": "версия 4.1 от 11.08.2026 13:50 по Москве",

    # Startup Screen & Notifications
    "STARTUP_TITLE": "Запуск бота",
    "STARTUP_TIME_LABEL": "Время запуска",
    "STARTUP_PREVIOUS_STOP": "Предыдущая остановка",
    "STARTUP_MONITORING_STREAMS": "Мониторинг стримов",
    "STARTUP_MONITORING_CONTENT": "Мониторинг контента",
    "STARTUP_SYSTEMS_CONTROL": "Управление системами",
    "STARTUP_CONFIGURATION": "Конфигурация",
    "STARTUP_UPTIME": "Аптайм: {uptime}",
    "STARTUP_FOOTER": "Все слэш-команды синхронизированы в Discord. Бот полностью готов к работе.",

    # Stream Platforms Display
    "STARTUP_STREAM_VK_LIVE": "VK Live",
    "STARTUP_STREAM_YOUTUBE": "YouTube Live",
    "STARTUP_STREAM_RUTUBE": "RuTube Live",
    "STARTUP_STREAM_TWITCH": "Twitch",
    "STARTUP_STREAM_KICK": "Kick",
    "STARTUP_STREAM_TROVO": "Trovo",
    "STARTUP_STREAM_VK_COM": "VK.com Live",
    "STARTUP_STREAM_GOODGAME": "GoodGame",

    # Content Modules Display
    "STARTUP_CONTENT_VK_WALL": "VK Стены",
    "STARTUP_CONTENT_YOUTUBE": "YouTube Видео",
    "STARTUP_CONTENT_RUTUBE": "RuTube Видео",
    "STARTUP_CONTENT_TELEGRAM": "Telegram Ленты",
    "STARTUP_CONTENT_PDF": "PDF Мониторинг",
    "STARTUP_CONTENT_VK_ASSETS": "VK Ассеты и ресурсы",

    # Systems & Handlers Display
    "STARTUP_SYSTEM_TRELLO": "Trello интеграции",
    "STARTUP_SYSTEM_PROTECTION": "Защита каналов",
    "STARTUP_SYSTEM_ROLE_DEP": "Зависимости ролей",
    "STARTUP_SYSTEM_USER_ACT": "Учет активности",
    "STARTUP_SYSTEM_GAME_TRACKER": "Игровой трекер",
    "STARTUP_SYSTEM_VOICE_REGIONS": "Регионы голосовых",
    "STARTUP_SYSTEM_SECRET_VENDORS": "Секретные торговцы",
    "STARTUP_SYSTEM_GAME_SCHEDULE": "Игровое расписание",
    "STARTUP_SYSTEM_IMAGE_FORWARDER": "Пересылка изображений",
    "STARTUP_SYSTEM_STATS_SERVER": "Сервер статистики",

    # Startup Badges & Values
    "STARTUP_TRAP_INFO": "Ловушка бана",
    "STARTUP_DEP_IMMEDIATE": "моментальная",
    "STARTUP_DEP_TIMER": "только по таймеру",
    "STARTUP_TWITCH_CHECK_GQL_API": "GQL-скрапинг + API (Helix/EventSub)",
    "STARTUP_TWITCH_CHECK_API": "Официальный API (Helix + EventSub)",
    "STARTUP_TWITCH_CHECK_NO_KEYS": "Без ключей API (GQL-скрапинг)",
    "STARTUP_SETTING_ERRORS": "Ошибки & Алерты",
    "STARTUP_SETTING_NOTIF_ROLE": "Роль уведомлений",
    "STARTUP_SETTING_PING_ROLE": "Роль пинга стримов",
    "STARTUP_SETTING_VK_TOKEN": "Общий VK токен",
    "STARTUP_SETTING_LOGGER": "Продвинутый логгер",
    "STARTUP_SETTING_ADAPTIVE": "Адаптивный опрос",
    "STARTUP_SETTING_RESTART": "Автоперезапуск",
    "STARTUP_SETTING_RESTART_INTERVAL": "Интервал перезапуска",
    "LOGGER_STATUS_DISABLED": "Отключено",
    "LOGGER_STATUS_ENABLED": "Включено",
    "ADAPTIVE_POLLING_DISABLED": "Отключен",
    "ADAPTIVE_POLLING_ENABLED": "Включен",
    "STATUS_ENABLED": "Включен",
    "STATUS_DISABLED": "Отключен",
    "INTERVAL_DISABLED": "отключен",
    "INTERVAL_MINUTES": "{interval} мин",

    # Content Type Names
    "CONTENT_TYPE_NAMES": {
        "photo": "Фотография",
        "video": "Видео",
        "audio": "Аудиозапись",
        "doc": "Документ",
        "link": "Ссылка",
        "market": "Товар",
        "poll": "Опрос",
        "post": "Запись",
        "article": "Статья",
        "clip": "Клип",
        "map": "Карта",
        "repost": "Репост",
        "fallback": "Вложение"
    },

    # Embed Fields & Default Texts
    "DEFAULT_MAP_ADDRESS": "Карта",
    "DEFAULT_STREAM_TITLE": "Трансляция",
    "STREAM_WITHOUT_TITLE": "Стрим без названия",
    "VIDEO_WITHOUT_TITLE": "Видео без названия",
    "DEFAULT_AUTHOR_STREAMER": "Стример",
    "DEFAULT_AUTHOR_NAME": "Автор",
    "DEFAULT_EMBED_AUTHOR": "Группа / Канал",
    "DEFAULT_EMBED_TITLE": "Новая публикация",
    "FIELD_ARTIST_NAME": "Исполнитель",
    "FIELD_COORDS_NAME": "Координаты",
    "FIELD_DURATION_NAME": "Длительность",
    "FIELD_FORMAT_NAME": "Формат",
    "FIELD_INFO_NAME": "Информация",
    "FIELD_INFO_VALUE": "Детали",
    "FIELD_MAP_LINK_NAME": "Ссылка на карту",
    "FIELD_MAP_LINK_VALUE_TEMPLATE": "[Открыть карту]({url})",
    "FIELD_MIRRORS_LABEL_STREAM": "Трансляция на других платформах",
    "FIELD_MIRRORS_LABEL_VIDEO": "Видео также доступно на других платформах",
    "FIELD_MIRRORS_NAME": "Зеркала",
    "FIELD_POLL_ANSWERS": "Всего голосов",
    "FIELD_PRICE_NAME": "Цена",
    "FIELD_SIZE_NAME": "Размер",
    "FIELD_STATUS_VALUE_LIVE": "Прямой эфир",
    "FIELD_TITLE_NAME": "Название",
    "FOOTER_CHANNEL_TEMPLATE": "Канал: {channel}",
    "EMBED_PART_SUFFIX": " ({index} из {total})",
    "ARTICLE_READ_BUTTON": "Читать статью",
    "OPEN_ORIGINAL_POST": "Открыть оригинал",
    "REPOST_HEADER": "Репост из {author}:",

    # Stream Notification Templates & Fallbacks
    "STREAM_START_TEMPLATE": "🔴 **{author}** запустил стрим на **{platform}**!\n🎬 Название: {title}\n🔗 Ссылка: {url}",
    "STREAM_END_TEMPLATE": "⏹️ Стрим **{title}** на **{platform}** завершен.",
    "STREAM_RECORD_TEMPLATE": "🎥 Запись стрима **{title}** доступна по ссылке: {url}",
    "STREAM_MIRROR_STREAM_LABEL": "Стрим также доступен на",
    "STREAM_MIRROR_VIDEO_LABEL": "Видео также доступно на",
    "TG_START_TEMPLATE_FALLBACK": "🔴 {author} начал трансляцию на {platform}!\n🎬 Название: {title}\n🔗 Смотреть: {url}",
    "TG_END_TEMPLATE_FALLBACK": "Стрим {title} на {platform} завершен.",
    "TG_VIDEO_TEMPLATE_FALLBACK": "🎥 {author} опубликовал новое видео на {platform}!\n🎬 Название: {title}\n🔗 Смотреть: {url}",

    # General Systems
    "HEARTBEAT_STATUS_WORK": "Nexus Bot работает",
    "INFO_MESSAGES": {},
    "ROLE_DISPLAY_TEMPLATE": "<@&{role_id}>",
    "ROLE_NOT_SET": "Роль не задана",
    "UNIT_KB": "КБ",
    "UNIT_MB": "МБ",
    "UNIT_GB": "ГБ",
    "UNKNOWN_ARTIST": "Неизвестный исполнитель",
    "UNKNOWN_TRACK": "Без названия",

    # Poll & Options Formatting
    "POLL_MORE_OPTIONS_TEMPLATE": "И ещё {count} вариантов...",
    "POLL_OPTION_NAME_TEMPLATE": "Вариант {number}",
    "POLL_OPTION_VALUE_TEMPLATE": "{text} — {votes} голосов ({percentage}%)",
    "POLL_VOTES_TEMPLATE": "Опрос (голосов: {votes})",

    # Platform Emojis & Suffixes
    "PLATFORM_EMOJIS": {
        "youtube": "🔴",
        "twitch": "🟣",
        "vk": "🔵",
        "vk_com": "🔵",
        "vkvideo": "🔵",
        "goodgame": "🧡",
        "rutube": "🟢",
        "kick": "🟢",
        "trovo": "💚"
    },
    "PLATFORM_SUFFIXES": {
        "youtube": " на YouTube",
        "twitch": " на Twitch",
        "vk": " на VK Play Live",
        "vk_com": " в VK.com",
        "goodgame": " на GoodGame",
        "rutube": " на Rutube",
        "kick": " на Kick",
        "trovo": " на Trovo"
    },

    # Errors & Diagnostics
    "ERROR_ALERT_OCCURRED": "Произошла ошибка в работе бота",
    "ERROR_ALERT_TIME": "Время ошибки",
    "ERROR_ALERT_TITLE": "Детали ошибки",
    "ERROR_ALERT_TRACEBACK": "Трейсбэк",

    # Logging Messages
    "LOG_CLIENT_READY": "Discord client готов.",
    "LOG_CONNECTION_CLOSED": "Соединение с Discord закрыто.",
    "LOG_DISCORD_CONNECTED": "Успешно подключились к Discord как {user}.",
    "LOG_DISCORD_DISCONNECTED": "Отключились от Discord.",
    "LOG_GRACEFUL_RESTART": "Запуск планового перезапуска: {reason}",
    "LOG_GRACEFUL_SHUTDOWN": "Запуск завершения работы: {reason}",
    "LOG_GUILD_JOIN_CHUNKED": "Загружены участники гильдии {guild} ({count} членов).",
    "LOG_GUILD_JOIN_CHUNKING": "Запрос кэша участников гильдии {guild} (ID: {guild_id})...",
    "LOG_MEMBER_CACHE_ERROR": "Ошибка кэширования участников {guild}: {error}",
    "LOG_NAME_CHANGED": "Имя бота успешно изменено на: {username}",
    "LOG_NAME_CHANGE_ERROR": "Не удалось изменить имя бота на {username}: {error}",
    "LOG_NICKNAME_CHANGED": "Никнейм бота на сервере '{guild}' успешно изменен на: {nickname}",
    "LOG_NICKNAME_CHANGE_ERROR": "Не удалось изменить никнейм на сервере '{guild}': {error}",
    "LOG_NICKNAME_NEW_GUILD_CHANGED": "Установлен никнейм '{nickname}' на новом сервере '{guild}'",
    "LOG_NICKNAME_NEW_GUILD_ERROR": "Ошибка установки никнейма на новом сервере '{guild}': {error}",
    "LOG_RESTORE_ALERT_FAIL": "Не удалось отправить уведомление о восстановлении сервера.",
    "LOG_RESTORE_ALERT_SUCCESS": "Уведомление о восстановлении сервера успешно отправлено.",
    "LOG_SCHEDULED_RESTART": "Плановый перезапуск через {interval_min} мин ({interval_sec} сек).",
    "LOG_SCHEDULED_RESTART_REASON": "Плановый таймер перезапуска ({interval_min} мин)",
    "LOG_STARTUP_NOTIFICATION_FAIL": "Не удалось отправить стартовое сообщение в лог-канал Discord.",
    "LOG_STARTUP_NOTIFICATION_SUCCESS": "Стартовое сообщение успешно отправлено в канал Discord ({channel_info}).",
    "LOG_MESSAGE_PREPARED_SENDING": "Сообщение подготовлено, отправляем в Discord...",

    # Commands Descriptions & Help
    "HELP_CMD_DESC": "Показать список всех доступных команд бота с описанием и фильтром по категориям",
    "HELP_EMBED_TITLE": "Справка по командам бота",
    "HELP_EMBED_DESC": "Используйте выпадающее меню ниже для просмотра команд по категориям. Вы можете использовать как слэш-команды (`/`), так и префиксные команды (`!`).",
    "HELP_SELECT_PLACEHOLDER": "Выберите категорию команд...",
    "HELP_ALL_CAT_LABEL": "📋 Все категории",
    "HELP_ALL_CAT_DESC": "Показать обзор всех разделов и категорий команд",
    "HELP_INFO_CAT_LABEL": "📊 Информация и статус",
    "HELP_INFO_CAT_DESC": "Статус бота, источники трансляций, бустеры сервера и группы VK",
    "HELP_GAME_CAT_LABEL": "🎮 Игровое расписание и торговцы",
    "HELP_GAME_CAT_DESC": "Секретные торговцы Division 2, расписание и ротация миссий",
    "HELP_ROLES_CAT_LABEL": "🛡️ Роли и Активность",
    "HELP_ROLES_CAT_DESC": "Связанные роли сервера, уровни и автоотслеживание активности",
    "HELP_VOICE_CAT_LABEL": "🔊 Голосовые каналы",
    "HELP_VOICE_CAT_DESC": "Управление и массовая смена регионов голосовых каналов",
    "HELP_MEDIA_CAT_LABEL": "🖼️ Перенаправление картинок",
    "HELP_MEDIA_CAT_DESC": "Автоматическое перенаправление изображений между каналами",
    "HELP_ADMIN_CAT_LABEL": "⚙️ Администрирование и Система",
    "HELP_ADMIN_CAT_DESC": "Управление конфигурациями, синхронизация, статусы и выключение",
    "HELP_OVERVIEW_NAME": "📌 Обзор возможностей",
    "HELP_OVERVIEW_VALUE": "Бот содержит **{total_cmds} команд**, разделенных по **{total_cats} категориям**.\nВыберите нужную категорию в меню ниже, чтобы открыть подробное описание каждого раздела.",
    "HELP_PREFIX_LABEL": "\n*Префикс:* `{aliases}`",
    "HELP_PERM_LABEL": " • 🔒 **{perm}**",
    "HELP_FOOTER_TEXT": "Префикс для текстовых команд: ! | Вызов слэш-команд: /",

    # Commands Actions & Responses
    "SYNC_CMD_DESC": "Синхронизировать слэш-команды (только для владельца)",
    "SYNC_GUILD_SUCCESS": "Синхронизировано {count} слэш-команд для текущего СЕРВЕРА. Теперь они должны появиться в меню `/`.",
    "SYNC_GLOBAL_SUCCESS": "Синхронизировано {count} слэш-команд (ГЛОБАЛЬНО). Обновление во всем Discord может занять до 1 часа.",
    "SYNC_ERROR": "Ошибка синхронизации: {error}",
    "SYNC_ERR_OWNER_ONLY": "Эта команда только для владельца бота.",
    "CMD_SYNC_GUILD_SUCCESS": "Синхронизировано {count} слэш-команд для текущего СЕРВЕРА. Теперь они должны появиться в меню `/`.",
    "CMD_SYNC_GLOBAL_SUCCESS": "Синхронизировано {count} слэш-команд (ГЛОБАЛЬНО). Обновление во всем Discord может занять до 1 часа.",
    "CMD_SYNC_ERROR": "Ошибка синхронизации: {error}",
    "CMD_OWNER_ONLY": "Эта команда только для владельца бота.",
    "CMD_RELOAD_NO_APP": "Не удалось получить доступ к основному приложению.",
    "CMD_RELOAD_SUCCESS": "Все конфигурации и настройки статуса успешно перезагружены!",
    "CMD_RELOAD_NO_MANAGERS": "Активные менеджеры для перезагрузки не найдены. Настройки статуса обновлены.",
    "CMD_RELOAD_ERROR": "Ошибка при перезагрузке: {error}",
    "CMD_RESTART_REASON": "Перезапуск по команде пользователя: {user}",
    "CMD_RESTART_STARTING": "Выполняется штатный перезапуск бота...",
    "CMD_NO_APP_ERROR": "ОШИБКА: Не удалось получить экземпляр приложения.",
    "CMD_SHUTDOWN_REASON": "Выключение по команде пользователя: {user}",
    "CMD_SHUTDOWN_STARTING": "Выполняется штатное выключение бота...",

    # Status Command
    "CMD_STATUS_BOT_TITLE": "Статус бота",
    "CMD_STATUS_UPTIME": "Аптайм",
    "CMD_STATUS_QUEUE": "В очереди",
    "CMD_STATUS_ERRORS": "Ошибки",
    "CMD_STATUS_START_TIME": "Время запуска",
    "CMD_STATUS_PROCESSED_TITLE": "Обработано / Метрики",
    "CMD_STATUS_PROCESSED_SUMMARY": "{posts_icon} Постов всего: {posts}\n├ За последние 24ч: **{posts_24h}**\n└ За последние 7 дней: **{posts_7d}**\n{time_icon} Ср. время отправки: **{avg_time} сек.**\n{plug_icon} Срабатываний Circuit Breaker: **{cb_triggered}**\n{video_icon} Видео: **{videos}**\n{stream_icon} Стримов: **{streams}**\n{sticker_icon} Ассеты: **{assets}**",
    "CMD_STATUS_MONITOR_FOOTER": "Мониторинг {platform} • Nexus Bridge",
    "CMD_STATUS_DISABLED": "Отключен",
    "CMD_STATUS_PAUSED": "Пауза (Circuit Breaker)",
    "CMD_STATUS_ACTIVE": "Активен",
    "CMD_STATUS_ID_SOURCE": "ID источника",
    "CMD_STATUS_ID_GROUP": "ID группы/канала",
    "CMD_STATUS_CURRENT": "Текущий статус",
    "CMD_STATUS_PROCESSED": "Обработано",
    "CMD_STATUS_ERRORS_ALL": "Ошибки (всего)",
    "CMD_STATUS_CONSECUTIVE_ERRORS": "Ошибок подряд",
    "CMD_STATUS_LAST_CHECK": "Последняя проверка",
    "CMD_STATUS_LAST_SUCCESS": "Последний успех",
    "CMD_STATUS_NEVER": "Никогда",
    "CMD_STATUS_ADAPTIVE_INTERVAL": "Адаптивный интервал",
    "CMD_STATUS_STANDARD": "Стандартный",
    "CMD_STATUS_LAST_ERROR": "Последняя ошибка",

    # Role Dependencies Command & Module
    "CMD_RULES_INACTIVE": "Модуль зависимостей ролей не активен.",
    "CMD_RULES_EMPTY": "Правила не настроены.",
    "CMD_RULES_TITLE": "Правила связанных ролей",
    "CMD_RULES_DESC": "Ниже перечислены автоматические действия при изменении ролей участников.",
    "CMD_RULES_FIELD_NAME": "Правило #{number}",
    "CMD_RULES_NOTE": "Примечание: {comment}",
    "CMD_RULES_FOOTER": "Система автоматических ролей",
    "ROLE_DEP_GIVE_REASON": "Выдача связанных ролей ({comment})",
    "ROLE_DEP_REMOVE_REASON": "Снятие связанных ролей ({comment})",
    "ROLE_DEP_MUTUAL_EXCLUDE_REASON": "Снятие взаимоисключающих ролей ({comment})",
    "ROLE_DEP_ALERT_MISSING_ROLES": "У пользователя **{name}** отсутствуют необходимые роли.",
    "ROLE_DEP_NO_ROLES_ALERT": "{emoji} {mention}У пользователя с ником **{name}** ({user_mention}) теперь **нет ролей**!",

    # User Activity Command & Module
    "CMD_ACTIVITY_INACTIVE": "Модуль активности не активен.",
    "CMD_GUILD_ONLY": "Эта команда может быть использована только на сервере.",
    "CMD_NOT_CONFIGURED": "Не настроена",
    "CMD_ABSENT_ALL": "Отсутствует (отслеживаются все)",
    "CMD_NONE": "Нет",
    "CMD_DISABLED": "Выключено",
    "CMD_ENABLED_AUTO": "Включено автоматически",
    "CMD_ACT_RULES_TITLE": "Правила и настройки активности пользователей",
    "CMD_ACT_RULES_DESC": "Текущие конфигурации автоматического отслеживания статусов, активности и управления ролями на сервере.",
    "CMD_ACT_RULES_FIELD_MANAGE": "Автоматическое управление ролями",
    "CMD_ACT_RULES_FIELD_MANAGE_VAL": "Статус: **{status}**",
    "CMD_ACT_RULES_FIELD_ROLES": "Назначаемые роли активности",
    "CMD_ACT_RULES_FIELD_ROLES_VAL": "{active_emoji} **Роль активности**: {active_role}\n{afk_emoji} **Роль AFK (неактивен)**: {afk_role}",
    "CMD_ACT_RULES_FIELD_AFK": "Порог неактивности (AFK)",
    "CMD_ACT_RULES_FIELD_AFK_VAL": "Пользователь переводится в режим AFK, если находится в офлайне более **{days}** дней.",
    "CMD_ACT_RULES_FIELD_REQ_ROLE": "Обязательная роль",
    "CMD_ACT_RULES_FIELD_IGN_ROLES": "Игнорируемые роли",
    "CMD_ACT_RULES_FIELD_LOG_CHAN": "Канал для логов статусов",
    "CMD_ACT_RULES_FIELD_ALGO": "Алгоритм работы правил",
    "CMD_ACT_RULES_ALGO_DESC": "1. При **любом обнаружении активности в сети** (онлайн, смена кастомного статуса или установка статуса голосового канала) у пользователя автоматически снимается роль AFK и выдается роль активности.\n2. Фоновая проверка раз в 12 часов проверяет пользователей в офлайне и переводит их в AFK, если отсутствие превышает срок в **{days} дней**.\n3. Участники с игнорируемыми ролями полностью исключаются из системы.\n4. Если установлена обязательная роль, только владельцы этой роли будут отслеживаться, у всех остальных роли активности будут автоматически сняты.",
    "CMD_ACT_RULES_FOOTER": "Мониторинг активности участников",
    "CMD_ACT_TITLE": "Активность: {name}",
    "CMD_ACT_CURRENT_STATUS": "Текущий статус",
    "CMD_ACT_LAST_SEEN": "Последняя онлайн-активность",
    "CMD_ACT_NO_DATA": "Нет данных в базе",
    "CMD_ACT_ROLE_STATUS": "Статус ролей",
    "CMD_ACT_NO_SPECIAL_ROLES": "Нет специальных ролей",
    "CMD_SYNC_ACT_NO_PERMS": "Эта команда доступна только администраторам серверов и владельцу бота.",
    "CMD_SYNC_ACT_TITLE": "Результаты синхронизации ролей активности",
    "CMD_SYNC_ACT_DESC": "Синхронизация завершена успешно. Обновлены статусы и роли.",
    "CMD_SYNC_ACT_TOTAL": "Всего участников проверено",
    "CMD_SYNC_ACT_ACTIVE": "Выдано ролей «Активный»",
    "CMD_SYNC_ACT_AFK": "Выдано ролей «AFK»",
    "CMD_SYNC_ACT_REMOVED": "Снято ролей (нет обязательной)",
    "CMD_SYNC_ACT_IGNORED": "Пропущено (игнорируемые ролями)",
    "CMD_SYNC_ACT_NO_CHANGE": "Без изменений",
    "CMD_SYNC_ACT_ERRORS": "Ошибок при смене ролей",
    "CMD_SYNC_ACT_FOOTER": "Синхронизация по требованию",
    "CMD_SYNC_ACT_ERROR": "Ошибка в процессе синхронизации: `{error}`",
    "CMD_SYNC_ACT_STARTING": "Запущен процесс полной синхронизации ролей по активности пользователей...",
    "CMD_ROLE_DEP_RELOAD_SUCCESS": "`role_dependencies.json` успешно перезагружен.",
    "ACT_LOG_STATUS_CHANGED": "**{name}** изменил статус на: {status}",
    "ACT_LOG_CUSTOM_STATUS_SET": "**{name}** установил статус: `{status}`",
    "ACT_LOG_CUSTOM_STATUS_REMOVED": "**{name}** удалил статус",
    "ACT_LOG_VOICE_STATUS_CHANGED": "{emoji} Статус голосового канала **{channel}** изменён на: `{status}` (установил: **{name}**)",
    "ACT_LOG_VOICE_STATUS_REMOVED": "{emoji} Статус голосового канала **{channel}** удалён (пользователь: **{name}**)",
    "STATUS_NAME_ONLINE": "в сети",
    "STATUS_NAME_OFFLINE": "не в сети",
    "STATUS_NAME_IDLE": "неактивен",
    "STATUS_NAME_DND": "не беспокоить",
    "STATUS_NAME_UNKNOWN": "неизвестен",

    # VK Info & Groups
    "CMD_VK_GROUPS_INACTIVE": "Менеджер VK групп неактивен.",
    "CMD_VK_GROUPS_NO_MONITORS": "Нет активных мониторов групп VK.",
    "CMD_CHECK_GROUPS_STARTING": "Запущена принудительная проверка всех групп VK ({count} шт.)...",
    "CMD_CHECK_GROUPS_RESULTS": "Результаты проверки групп:\n{results}",
    "CMD_VK_INFO_HAS_LOCAL": "Да ({desc})",
    "CMD_VK_INFO_NO_LOCAL": "Нет, используется общий токен: {desc}",
    "CMD_VK_INFO_SUCCESS": "Информация по всем группам успешно отправлена.",

    # Bot Presence & Status Setter
    "CMD_SET_STATUS_SUCCESS": "Сетевой статус бота обновлен на: **{status}**",
    "CMD_SET_STATUS_ERROR": "Ошибка обновления статуса: `{error}`",
    "CMD_SET_ACT_REMOVED": "Активность / кастомный статус бота успешно удален!",
    "CMD_SET_ACT_SUCCESS": "Активность обновлена на: **{type}** - *{name}*",
    "CMD_SET_ACT_ERROR": "Ошибка обновления активности: `{error}`",
    "CMD_SET_STREAM_SUCCESS": "Статус стрима успешно установлен!\n• URL: <{url}>\n• Текст: *{text}*",
    "CMD_SET_STREAM_ERROR": "Ошибка обновления стрим-статуса: `{error}`",

    # Server Boosts Command
    "CMD_BOOSTS_NONE": "Бусты не обнаружены.",
    "CMD_BOOSTS_TITLE": "Бусты сервера — {guild}",
    "CMD_BOOSTS_CURRENT_LEVEL": "Текущий уровень",
    "CMD_BOOSTS_LEVEL_LABEL": "Уровень {level}",
    "CMD_BOOSTS_MAX_LEVEL": "{count} {emoji} (максимальный уровень)",
    "CMD_BOOSTS_NEXT_PROGRESS": "{count}/{threshold} {emoji} до {next_label}",
    "CMD_BOOSTS_ACTIVE_BOOSTERS": "Активные бустеры ({count})",
    "CMD_BOOSTS_MORE_BOOSTERS": "\n_...и ещё бустеры (превышен лимит отображения)_",
    "CMD_BOOSTS_NO_ACTIVE": "Нет активных бустеров или данные недоступны в текущем кэше.",
    "CMD_BOOSTS_FOOTER": "Все даты начала буста получены напрямую из Discord API",

    # Sources Command
    "CMD_SOURCES_TITLE": "Подключенные источники публикаций",
    "CMD_SOURCES_DESC": "Ниже представлен список всех активных внешних каналов, групп и системных модулей, подключенных к боту, и каналов Discord для их публикации.\n",
    "CMD_SOURCES_NO_CHAN": "⚠️ *Канал не настроен*",
    "CMD_SOURCES_NONE": "В данный момент нет подключенных источников.",
    "CMD_SOURCES_FOOTER": "Nexus Bot • Система мониторинга и публикаций",
    "CMD_COOLDOWN_MSG": "Команда на кулдауне. Повтори через **{time:.1f}с**.",
    "CMD_NO_PERMS_ADMIN": "У тебя нет прав для выполнения этой команды (требуется **Администратор**).",

    # Voice Region Module
    "VOICE_REGION_CMD_DESC": "Массово сменить регион во всех голосовых каналах текущего сервера",
    "VOICE_REGION_PARAM_DESC": "Выберите регион для установки (или Automatic)",
    "VOICE_LIST_CMD_DESC": "Показать список всех голосовых каналов и их текущие регионы",
    "VOICE_ERR_GUILD_ONLY": "Команда доступна только внутри сервера.",
    "VOICE_ERR_NO_PERMS": "У бота нет прав 'Управление каналами' на этом сервере.",
    "VOICE_ERR_NO_CHANNELS": "На сервере нет голосовых каналов.",
    "VOICE_REGION_AUTOMATIC": "Автоматический",
    "VOICE_REGION_SUCCESS": "Массовая смена завершена.\n• Регион установлен на: **{status}**\n• Каналов обновлено: **{updated}**",
    "VOICE_REGION_ERRORS": "\n• Ошибок при обновлении: **{errors}**",
    "VOICE_LIST_HEADER": "Регионы голосовых каналов сервера {guild}:",

    # Image Forwarder Module
    "FORWARDER_STATUS_CMD_DESC": "Показать статус модуля перенаправления картинок (Админ)",
    "FORWARDER_EMBED_TITLE": "Настройки модуля перенаправления картинок",
    "FORWARDER_STATUS_LABEL": "Статус модуля",
    "FORWARDER_COUNT_LABEL": "Перенаправлено с запуска",
    "FORWARDER_RULES_LABEL": "Активные правила",
    "FORWARDER_NO_RULES": "*Правила еще не созданы*",
    "FORWARDER_FOOTER": "Любой текст из исходных сообщений игнорируется. Отправляются только картинки.",
    "FORWARDER_MODAL_TITLE": "Настройка правила картинок",
    "FORWARDER_MODAL_SOURCE": "ID исходных каналов (через запятую)",
    "FORWARDER_MODAL_TARGET": "ID целевого канала",
    "FORWARDER_ERR_TARGET_INVALID": "Указан неверный ID целевого канала.",
    "FORWARDER_ERR_NO_PERMS": "У вас нет прав администратора.",
    "FORWARDER_BTN_TOGGLE": "Вкл / Выкл модуль",
    "FORWARDER_BTN_CONFIG": "Настроить каналы правила",
    "FORWARDER_SAVE_SUCCESS": "Правило успешно сохранено!",

    # PDF Module
    "PDF_EMBED_DEFAULT_NAME": "Обновление",
    "PDF_NEW_UPDATE_MSG": "Обнаружено новое обновление от **{date}**.\nНажмите на заголовок чтобы открыть страницу.",
    "PDF_INFO_FIELD": "Информация",

    # Secret Vendors Module
    "VENDOR_DAYS_RU": ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
    "VENDOR_DAYS_SHORT_RU": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
    "VENDOR_EMBED_TITLE": "Настройки вебхука и уведомлений торговцев",
    "VENDOR_NO_PERMS": "У вас нет прав администратора.",
    "VENDOR_MODAL_TITLE": "Настройка вебхука торговцев",
    "VENDOR_MODAL_NAME": "Имя вебхука",
    "VENDOR_MODAL_AVATAR": "URL или путь к аватарке вебхука",
    "VENDOR_BTN_EDIT_WEBHOOK": "Изменить вебхук, имя и аватар",
    "VENDOR_BTN_PREVIEW": "Предпросмотр карточек торговцев",
    "VENDOR_BTN_TOGGLE_SCHEDULE": "Переключить расписание",
    "VENDOR_STATUS_HEADER": "Статус секретных торговцев:",
    "VENDOR_STATUS_OPEN": "Открыт",
    "VENDOR_STATUS_CLOSED": "Закрыт",
    "VENDOR_LOCATION_LABEL": "Местоположение",
    "VENDOR_TIMER_OPEN_UNTIL": "Открыт до: {time}",
    "VENDOR_TIMER_CLOSED_UNTIL": "Откроется через: {time}",
    "VENDOR_ASSORTMENT_TITLE": "Ассортимент товаров",
    "VENDOR_ASSORTMENT_EMPTY": "Ассортимент обновляется...",
    "VENDOR_DEFAULT_NAME": "Секретные торговцы",
    "VENDOR_FOOTER_TEXT": "The Division 2 • Секретные торговцы",
    "VENDOR_OPEN_TITLE_DEFAULT": "{emoji} Секретные торговцы открыты!",
    "VENDOR_CLOSE_TITLE_DEFAULT": "{emoji} Секретные торговцы закрыты!",
    "VENDOR_OPEN_STATUS_DEFAULT": "{emoji} **Открыты** (до {next_day_ru} {next_time_str} МСК)",
    "VENDOR_CLOSE_STATUS_DEFAULT": "{emoji} **Закрыты** (до {next_day_ru} {next_time_str} МСК)",
    "VENDOR_DESC_TEMPLATE": "В этом канале публикуются уведомления о начале и конце работы двух секретных торговцев: **Дэнни (слева)** и **Кэйси (справа)**.\n\n{emoji_location} **Как найти торговцев**: [Товары недели, Дэнни и Мендоза]({guide_url})\n{emoji_link} **Еженедельный каталог торговцев**: [Перейти к каталогу]({catalog_url})",
    "VENDOR_FIELD_STATUS_NAME": "{emoji} Статус",
    "VENDOR_FIELD_STATUS_VALUE": "{status_text}\n{emoji} **Осталось времени**: {formatted_remaining}",
    "VENDOR_FIELD_ASSORTMENT_NAME": "{emoji} Ассортимент торговцев",
    "VENDOR_FIELD_ASSORTMENT_VALUE": "{emoji} **Дэнни (слева)** — торгует контейнерами, продает их за текстиль (желтая валюта гардероба).\n{emoji} **Кэйси (справа)** — снаряжение, продает их за обычные кредиты (деньги).",
    "VENDOR_FIELD_SCHEDULE_NAME": "{emoji} Расписание работы",
    "VENDOR_FIELD_SCHEDULE_VALUE": "Секретные торговцы работают **24 часа**, после чего **\"отдыхают\" 32 часа**. Меняют свое местоположение вместе с еженедельным сбросом.\n\n{emoji} **Открывается**: Понедельник 03:00 МСК\n{emoji} **Закрывается**: Вторник 03:00 МСК\n{emoji} **Открывается**: Среда 11:00 МСК\n{emoji} **Закрывается**: Четверг 11:00 МСК\n{emoji} **Открывается**: Пятница 19:00 МСК\n{emoji} **Закрывается**: Суббота 19:00 МСК",
    "VENDOR_CFG_NOT_SET": "*Не задан*",
    "VENDOR_CFG_NOT_SET_FEMALE": "*Не задана*",
    "VENDOR_CFG_DEFAULT": "*По умолчанию*",
    "VENDOR_CFG_FIELD_NAME": "Имя вебхука",
    "VENDOR_CFG_FIELD_AVATAR": "Аватар вебхука",
    "VENDOR_CFG_FIELD_CHANNEL": "Канал (фоллбэк)",
    "VENDOR_CFG_FIELD_ROLE": "Роль для пинга",
    "VENDOR_CFG_FIELD_OPEN_COLOR": "Цвет открыто (RGB)",
    "VENDOR_CFG_FIELD_CLOSE_COLOR": "Цвет закрыто (RGB)",
    "VENDOR_SEND_SUCCESS": "Сообщение о статусе торговцев успешно отправлено.",
    "VENDOR_SEND_FAIL": "Не удалось отправить сообщение. Проверьте webhook_url или channel_id в конфиге.",
    "VENDOR_CONFIG_UPDATED": "Настройки успешно обновлены!",
    "VENDOR_CONFIG_CURRENT": "Текущие настройки модуля секретных торговцев:",
    "VENDOR_CONFIG_SAVED_SUCCESS": "Настройки вебхука и цветов секретных торговцев успешно сохранены!",
    "CMD_VENDORS_DESC": "Показать текущий статус секретных торговцев (Дэнни и Кэйси)",
    "CMD_VENDORS_SEND_DESC": "Принудительно отправить сообщение о статусе торговцев в Webhook / канал (Админ)",
    "CMD_VENDORS_CONFIG_DESC": "Настроить вебхук, имя, аватар, цвета и каналы для секретных торговцев (Админ)",
    "CMD_VENDORS_PARAM_WEBHOOK_URL": "URL вебхука Discord",
    "CMD_VENDORS_PARAM_WEBHOOK_NAME": "Имя вебхука (по умолчанию: Секретные торговцы)",
    "CMD_VENDORS_PARAM_WEBHOOK_AVATAR": "URL или путь к аватарке вебхука",
    "CMD_VENDORS_PARAM_OPEN_COLOR": "Цвет при открытии в формате RGB (например: 46, 204, 113)",
    "CMD_VENDORS_PARAM_CLOSE_COLOR": "Цвет при закрытии в формате RGB (например: 231, 76, 60)",
    "CMD_VENDORS_PARAM_CHANNEL": "Канал Discord для отправки (если вебхук не используется)",
    "CMD_VENDORS_PARAM_ROLE": "Роль для пинга",

    # Protection Module
    "PROTECTION_WARNING_TEXT": "⚠️ Внимание, {user}! Этот канал предназначен только для чтения/медиа. Ваше текстовое сообщение было удалено.",
    "PROTECTION_LOG_DELETED": "Удалено сообщение от {user} в защищенном канале {channel}.",
    "PROTECTION_REASON_PROTECTED": "канал защищён",
    "PROTECTION_REASON_BOT_POSTING": "канал используется ботом для публикаций",
    "PROTECTION_REASON_VOICE_DISABLED": "чат в голосовом канале запрещён",
    "PROTECTION_MENTION_WARNING": "{user}, упоминание `@everyone` и `@here` запрещено.",
    "PROTECTION_TRAP_EMPTY_MSG": "<Пустое сообщение/вложение>",

    # Game Schedule Module
    "SCHEDULE_DAYS_RU": ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
    "SCHEDULE_EMBED_TITLE": "Настройки игрового расписания событий",
    "SCHEDULE_MODAL_TITLE": "Настройка игрового расписания",
    "SCHEDULE_NO_PERMS": "У вас нет прав администратора.",
    "SCHEDULE_EVENT_NOT_FOUND": "Событие `{event_id}` не найдено.",
    "SCHEDULE_EVENT_STATUS_ACTIVE": "Активно",
    "SCHEDULE_EVENT_STATUS_UPCOMING": "Скоро начнется",
    "SCHEDULE_EVENT_STATUS_ENDED": "Завершено",
    "SCHEDULE_TIME_REMAINING": "Осталось времени",
    "SCHEDULE_NEXT_ROTATION": "Следующая ротация",
    "SCHEDULE_DEFAULT_USERNAME": "Игровое расписание",
    "SCHEDULE_DEFAULT_AUTHOR": "Игровое расписание The Division 2",
    "SCHEDULE_DEFAULT_FOOTER": "Игровое расписание The Division 2",
    "SCHEDULE_AUTOPUB_FIELD": "Автопубликация",
    "SCHEDULE_AUTOPUB_ENABLED": "🟢 `Включена`",
    "SCHEDULE_AUTOPUB_DISABLED": "🔴 `Выключена`",
    "SCHEDULE_CFG_FIELD_AUTHOR": "Шапка (Author)",
    "SCHEDULE_CFG_FIELD_FOOTER": "Подвал (Footer)",
    "SCHEDULE_CFG_FIELD_COLOR": "Цвет сообщений (RGB)",
    "SCHEDULE_CFG_EVENTS_FIELD": "Настроенные события и их превью",
    "SCHEDULE_ROTATION_TITLE": "Установлена текущая легендарная миссия этой недели!",
    "SCHEDULE_ROTATION_CURRENT": "🎯 Текущая миссия: **{mission}**",
    "SCHEDULE_ROTATION_RESET_TUE": "📅 Опорный вторник сброса: **{reset_date} 11:00 МСК**",
    "SCHEDULE_ROTATION_PREVIEW_HEADER": "Расчет ротации на следующие недели:",
    "SCHEDULE_ROTATION_RESET_SUCCESS": "Ручная привязка сброшена! Включена автоматическая ротация. Текущая миссия недели: **{mission}**",
    "SCHEDULE_EVENT_SEND_SUCCESS": "Сообщение о событии `{event_id}` успешно отправлено!",
    "SCHEDULE_EVENT_SEND_FAIL": "Не удалось отправить сообщение. Проверьте webhook_url или channel_id в конфиге.",
    "SCHEDULE_ALL_SEND_SUCCESS": "Все события расписания успешно отправлены ({count}/{total})!",
    "SCHEDULE_ALL_SEND_PARTIAL": "Отправлено {count}/{total} событий. Не удалось отправить: {failed}. Проверьте webhook_url или channel_id в конфиге.",
    "SCHEDULE_CFG_UPDATED": "Настройки успешно обновлены!",
    "SCHEDULE_CFG_CURRENT": "Текущие настройки модуля игрового расписания:",
    "SCHEDULE_CFG_SAVED_SUCCESS": "Настройки вебхука и оформления игрового расписания успешно сохранены!",
    "SCHEDULE_EVENT_ROLE_SET": "Для события `{event_id}` установлена индивидуальная роль: <@&{role_id}>",
    "SCHEDULE_EVENT_ROLE_RESET": "Индивидуальная роль для события `{event_id}` сброшена (будет использоваться общая роль).",
    "SCHEDULE_MODAL_IMAGES_TITLE": "Настройка изображений события",
    "SCHEDULE_MODAL_IMG_UPDATED": "Изображения для события `{event_id}` успешно обновлены! Предпросмотр ниже:",

    # Game Tracker Module & Time Formatters
    "TIME_SEC": "{seconds} сек.",
    "TIME_MIN": "{minutes} мин.",
    "TIME_HOURS_MIN": "{hours} ч. {minutes} мин.",
    "TIME_DAYS_HOURS": "{days} дн. {hours} ч.",
    "TIME_JUST_NOW": "только что"
}


def _ensure_loaded() -> Dict[str, Any]:
    global _STRINGS_CACHE
    if _STRINGS_CACHE is not None:
        return _STRINGS_CACHE

    _STRINGS_CACHE = dict(_DEFAULT_STRINGS)
    try:
        from settings.data_files import Files
        from settings.config import Config

        locale = getattr(Config, "LOCALE", "ru").lower()
        locale_path = getattr(Files, f"STRINGS_{locale.upper()}_CONFIG_PATH", None)
        generic_path = Files.STRINGS_CONFIG_PATH

        # 1. Загрузка файла для конкретной локали (strings_ru.json, strings_en.json и т.д.)
        target_path = None
        if locale_path and os.path.isfile(locale_path):
            target_path = locale_path
        elif os.path.isfile(generic_path):
            target_path = generic_path

        if target_path and os.path.isfile(target_path):
            with open(target_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    _STRINGS_CACHE.update(loaded)
        else:
            # Если файлов нет, создаем strings_ru.json и strings.json по умолчанию
            os.makedirs(os.path.dirname(generic_path), exist_ok=True)
            with open(generic_path, "w", encoding="utf-8") as f:
                json.dump(_DEFAULT_STRINGS, f, ensure_ascii=False, indent=2)
            if hasattr(Files, "STRINGS_RU_CONFIG_PATH") and not os.path.isfile(Files.STRINGS_RU_CONFIG_PATH):
                with open(Files.STRINGS_RU_CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(_DEFAULT_STRINGS, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[BotStrings] Ошибка при загрузке локализации: {e}")

    return _STRINGS_CACHE


class _StringMeta(type):
    def __getattr__(cls, name: str):
        data = _ensure_loaded()
        if name in data:
            return data[name]
        if name in _DEFAULT_STRINGS:
            return _DEFAULT_STRINGS[name]
        return ""


class BotStrings(metaclass=_StringMeta):
    @classmethod
    def load_strings(cls):
        """ Перезагружает локализацию из strings.json. """
        global _STRINGS_CACHE
        _STRINGS_CACHE = None
        return _ensure_loaded()

    @classmethod
    def get(cls, key: str, default: Any = "") -> Any:
        data = _ensure_loaded()
        return data.get(key, _DEFAULT_STRINGS.get(key, default))
