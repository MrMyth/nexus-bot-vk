# vk_wall/live_config.py
import os
import asyncio
import json
import aiofiles
from typing import List, Dict, Any
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from modules_utils.files import get_config_path

async def load_live_configs() -> List[Dict[str, Any]]:
    configs = []
    config_dir = get_config_path("live_configs")

    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
        await send_to_any_log("info", f"Created folder for VK configs: {config_dir}", emoji=LogEmojis.INFO)
        return configs

    await send_to_any_log("info", f"Loading VK configs from: {config_dir}", emoji=LogEmojis.INFO)

    filenames = await asyncio.to_thread(os.listdir, config_dir)
    for filename in filenames:
        if filename.endswith('.json'):
            file_path = os.path.join(config_dir, filename)
            try:
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    live_config = json.loads(content)
                    platform_id = live_config.get('platform_id')
                    if not platform_id:
                        await send_to_any_log("error", f"Missing platform_id in JSON {filename}", emoji=LogEmojis.ERROR)
                        continue
                    if 'send_channel_notification' not in live_config:
                        live_config['send_channel_notification'] = True
                    configs.append(live_config)
                    
                    name = live_config.get('name')
                    info = f"'{name}' ({platform_id})" if name else str(platform_id)
                    await send_to_any_log("info", f"Loaded VK JSON config: {info}", emoji=LogEmojis.INFO)
            except Exception as e:
                await send_to_any_log("error", f"Error loading VK JSON config {filename}: {e}", emoji=LogEmojis.ERROR)

        elif filename.endswith('.py') and filename != '__init__.py':
            file_path = os.path.join(config_dir, filename)
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(filename[:-3], file_path)
                if spec is None or spec.loader is None:
                    continue

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if hasattr(module, 'LIVE_CONFIG'):
                    live_config = module.LIVE_CONFIG.copy()
                    platform_id = live_config.get('platform_id')
                    if not platform_id:
                        await send_to_any_log("error", f"Missing platform_id in file {filename}", emoji=LogEmojis.ERROR)
                        continue
                    if 'send_channel_notification' not in live_config:
                        live_config['send_channel_notification'] = True
                    configs.append(live_config)
                    
                    name = live_config.get('name')
                    info = f"'{name}' ({platform_id})" if name else str(platform_id)
                    await send_to_any_log("info", f"Loaded VK .py config: {info}", emoji=LogEmojis.INFO)
            except Exception as e:
                await send_to_any_log("error", f"Error loading VK .py config {filename}: {e}", emoji=LogEmojis.ERROR)

    return configs
