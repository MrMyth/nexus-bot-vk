# vk_wall/group_search.py
import os
import asyncio
import json
import importlib.util
import aiofiles
from typing import List, Dict, Any
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis

# Импорты для работы с кэшем и API
from modules_utils.group_cache import get_cached_id, cache_id
from modules_utils.vk_api_client import VKApiClient
from modules_utils.files import get_config_path  # Новый импорт


async def load_groups() -> List[Dict[str, Any]]:
    """
    Асинхронно загружает конфигурации групп из папки group_configs.
    Поддерживает форматы .json и .py.
    """
    import json
    groups = []
    config_dir = get_config_path("group_configs")

    if not os.path.exists(config_dir):
        await send_to_any_log("error", f"Directory {config_dir} not found!", emoji=LogEmojis.ERROR)
        return groups

    await send_to_any_log("info", f"Searching for group configs in: {config_dir}", emoji=LogEmojis.INFO)

    loaded_screen_names = set()

    filenames = await asyncio.to_thread(os.listdir, config_dir)
    for filename in filenames:
        group_config = None
        
        if filename.endswith('.json'):
            file_path = os.path.join(config_dir, filename)
            try:
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    group_config = json.loads(content)
            except Exception as e:
                await send_to_any_log("error", f"Error loading JSON config {filename}: {e}", emoji=LogEmojis.ERROR)
                continue

        elif filename.endswith('.py') and filename != '__init__.py':
            try:
                file_path = os.path.join(config_dir, filename)
                spec = importlib.util.spec_from_file_location(filename[:-3], file_path)
                if spec is None or spec.loader is None:
                    continue

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, 'GROUP_CONFIG'):
                    group_config = module.GROUP_CONFIG.copy()
                else:
                    await send_to_any_log("warning", f"GROUP_CONFIG variable not found in file {filename}", emoji=LogEmojis.WARNING)
                    continue
            except Exception as e:
                await send_to_any_log("error", f"Error loading .py config {filename}: {e}", emoji=LogEmojis.ERROR)
                continue

        if group_config:
            screen_name = group_config.get('platform_id') or group_config.get('screen_name')
            if not screen_name:
                await send_to_any_log("error", f"Missing platform_id or screen_name in config {filename}", emoji=LogEmojis.ERROR)
                continue
            
            # Гарантируем наличие platform_id для единообразия
            group_config['platform_id'] = screen_name

            # Валидация ID каналов
            for key in ['discord_channel_id', 'thread_id']:
                val = group_config.get(key)
                if val:
                    try:
                        int(val)
                    except (ValueError, TypeError):
                        await send_to_any_log("error", f"In config {filename}, field {key} must be a number (string or int), got: {val}", emoji=LogEmojis.ERROR)
                        group_config[key] = None

            if screen_name in loaded_screen_names:
                await send_to_any_log("error", f"screen_name conflict: '{screen_name}' is already loaded", emoji=LogEmojis.ERROR)
                continue
            loaded_screen_names.add(screen_name)

            # Кэш
            cached_id = get_cached_id(screen_name, namespace="group")
            if cached_id:
                group_config['id'] = cached_id
                groups.append(group_config)
                continue

            # API
            group_id = await VKApiClient.get_group_id(screen_name)
            if group_id is not None:
                group_config['id'] = group_id
                cache_id(screen_name, group_id, namespace="group")
                groups.append(group_config)
            else:
                await send_to_any_log("error", f"Failed to get ID for group '{screen_name}'", emoji=LogEmojis.ERROR)

    await send_to_any_log("info", f"Successfully loaded group configs: {len(groups)}", emoji=LogEmojis.SUCCESS)
    return groups
