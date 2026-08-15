# config_validator.py
import asyncio
from log_system.logger_helper import send_to_any_log
from settings.config import Config
from constants.emojis import LogEmojis


async def _all_vk_groups_have_local_tokens():
    """
    Проверяет, у всех ли настроенных VK-групп (wall + live) задан локальный vk_token.

    :return: True — у всех групп есть локальный токен (общий VK_TOKEN не нужен);
             False — есть хотя бы одна группа без локального токена;
             None — конфиги групп не удалось загрузить/групп нет, проверить невозможно.
    """
    groups = []
    try:
        if Config.ENABLE_VK_WALL_MONITORING:
            from modules.vk_wall.group_search import load_groups
            groups.extend(await load_groups())
        if Config.ENABLE_VK_LIVE_MONITORING:
            from modules.vk_live.live_config import load_live_configs
            groups.extend(await load_live_configs())
    except Exception:
        return None

    if not groups:
        return None

    return all(bool(g.get("vk_token")) for g in groups)


async def validate_required_tokens():
    """Проверяет обязательные токены и условно-обязательные (зависят от включённых модулей)."""
    errors = []
    warnings = []

    # --- Безусловно обязательные ---
    if not Config.DISCORD_BOT_TOKEN:
        errors.append(
            "DISCORD_BOT_TOKEN не задан — бот не сможет подключиться к Discord. "
            "Добавьте токен бота из Discord Developer Portal в .env."
        )

    if not Config.VK_TOKEN and (Config.ENABLE_VK_WALL_MONITORING or Config.ENABLE_VK_LIVE_MONITORING):
        all_groups_have_local_tokens = await _all_vk_groups_have_local_tokens()
        if all_groups_have_local_tokens is False:
            # Есть хотя бы одна группа без локального токена, а общего тоже нет.
            errors.append(
                "VK_TOKEN не задан, но VK-мониторинг включён (ENABLE_VK_WALL_MONITORING или "
                "ENABLE_VK_LIVE_MONITORING=true), и не у всех групп задан локальный vk_token в их конфиге. "
                "Добавьте общий VK_TOKEN в .env, укажите локальный vk_token в конфиге каждой группы, "
                "или отключите VK-модули."
            )
        elif all_groups_have_local_tokens is None:
            # Не удалось однозначно проверить конфиги групп — предупреждаем, но не блокируем запуск.
            warnings.append(
                "VK_TOKEN не задан. Это нормально, если у ВСЕХ отслеживаемых VK-групп указан "
                "локальный vk_token в их конфиге — общий токен в этом случае не требуется. "
                "Не удалось автоматически проверить конфиги групп, поэтому убедитесь в этом вручную."
            )
        else:
            warnings.append(
                "VK_TOKEN не задан, но у всех отслеживаемых VK-групп указан локальный vk_token — "
                "общий токен не требуется для текущей конфигурации."
            )

    # --- Условно обязательные: нужны только если соответствующий модуль включён ---
    if Config.ENABLE_TELEGRAM_MODULE and not Config.TELEGRAM_BOT_TOKEN:
        errors.append(
            "ENABLE_TELEGRAM_MODULE=true, но TELEGRAM_BOT_TOKEN не задан. "
            "Добавьте токен Telegram-бота в .env, или установите ENABLE_TELEGRAM_MODULE=false."
        )

    if Config.ENABLE_YOUTUBE_MONITORING and not Config.YOUTUBE_API_KEY:
        errors.append(
            "ENABLE_YOUTUBE_MONITORING=true, но YOUTUBE_API_KEY не задан. "
            "Добавьте YouTube Data API v3 ключ в .env, или установите ENABLE_YOUTUBE_MONITORING=false."
        )

    if Config.ENABLE_TWITCH_LIVE_MONITORING:
        use_scraper_primary = getattr(Config, "TWITCH_USE_SCRAPER_PRIMARY", True)
        if not use_scraper_primary:
            if not Config.TWITCH_CLIENT_ID:
                errors.append(
                    "ENABLE_TWITCH_LIVE_MONITORING=true и TWITCH_USE_SCRAPER_PRIMARY=false, но TWITCH_CLIENT_ID не задан. "
                    "Добавьте Client ID Twitch-приложения в .env, включите TWITCH_USE_SCRAPER_PRIMARY=true или отключите модуль."
                )
            if not Config.TWITCH_CLIENT_SECRET:
                errors.append(
                    "ENABLE_TWITCH_LIVE_MONITORING=true и TWITCH_USE_SCRAPER_PRIMARY=false, но TWITCH_CLIENT_SECRET не задан. "
                    "Добавьте Client Secret Twitch-приложения в .env, включите TWITCH_USE_SCRAPER_PRIMARY=true или отключите модуль."
                )
        else:
            if not Config.TWITCH_CLIENT_ID or not Config.TWITCH_CLIENT_SECRET:
                warnings.append(
                    "TWITCH_CLIENT_ID или TWITCH_CLIENT_SECRET не заданы. Twitch модуль работает в режиме скрапера без ключей (GQL / ivr.fi)."
                )

    # --- Предупреждения: заданы, но скрыто пустые ---
    if Config.VK_TOKEN and len(Config.VK_TOKEN) < 20:
        warnings.append(
            f"VK_TOKEN подозрительно короткий ({len(Config.VK_TOKEN)} символов) — возможно, задан некорректно."
        )

    if Config.DISCORD_BOT_TOKEN and len(Config.DISCORD_BOT_TOKEN) < 50:
        warnings.append(
            f"DISCORD_BOT_TOKEN подозрительно короткий ({len(Config.DISCORD_BOT_TOKEN)} символов) — проверьте значение в .env."
        )

    # Выводим предупреждения
    for w in warnings:
        await send_to_any_log("warning", w, emoji=LogEmojis.WARNING)

    # Выводим ошибки и переводим бота в режим ожидания
    if errors:
        for error in errors:
            await send_to_any_log("critical", error, emoji=LogEmojis.CRITICAL)
        Config.DISABLE_BOT = True
        await send_to_any_log(
            "critical",
            f"Конфигурация содержит критические ошибки ({len(errors)} шт.). "
            "Бот переведен в спящий режим (DISABLE_BOT=True) для предотвращения падения. "
            "Пожалуйста, задайте необходимые переменные окружения или заполните файл .env и перезапустите приложение.",
            emoji=LogEmojis.CRITICAL
        )
        return

    # Успех — выводим информацию о токенах
    from modules_utils.helpers import get_vk_token_description
    if Config.VK_TOKEN:
        vk_desc = get_vk_token_description(Config.VK_TOKEN)
        await send_to_any_log("info", f"Общий VK_TOKEN: {vk_desc}", emoji=LogEmojis.CONFIG)
    await send_to_any_log("info", "Проверка токенов пройдена успешно", emoji=LogEmojis.INFO)


async def validate_paths():
    """Проверяет доступность папки для данных."""
    import os
    try:
        os.makedirs(Config.DATA_FOLDER, exist_ok=True)
        test_file = os.path.join(Config.DATA_FOLDER, ".test_write")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        await send_to_any_log("info", f"Папка данных: '{Config.DATA_FOLDER}' готова к использованию",
                              emoji=LogEmojis.DATABASE)
    except Exception as e:
        error_msg = f"Невозможно использовать папку данных '{Config.DATA_FOLDER}': {e}"
        await send_to_any_log("critical", error_msg, emoji=LogEmojis.CRITICAL)
        raise RuntimeError(error_msg)


async def validate_intents():
    """Проверяет осмысленность настроек intents."""
    if not Config.INTENTS_MESSAGE_CONTENT:
        await send_to_any_log(
            "warning",
            "INTENTS_MESSAGE_CONTENT выключен — бот не сможет корректно отправлять сообщения или видеть их.",
            emoji=LogEmojis.WARNING,
        )


async def validate_config():
    """Полная проверка конфигурации перед запуском бота."""
    await send_to_any_log("info", "Начинаю проверку конфигурации...", emoji=LogEmojis.CONFIG)

    try:
        await validate_paths()
        await validate_required_tokens()
        await validate_intents()
        await send_to_any_log("info", "Конфигурация проверена успешно! Все системы в норме.",
                              emoji=LogEmojis.SUCCESS)
    except Exception as e:
        await send_to_any_log("critical", f"Критическая ошибка в конфигурации: {e}",
                              emoji=LogEmojis.CRITICAL)
        raise
