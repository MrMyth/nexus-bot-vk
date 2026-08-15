# modules/vk_assets/asset_config.py
import os
import asyncio
import json
import aiofiles
from typing import List, Dict, Any
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from modules_utils.files import get_config_path

async def load_asset_configs() -> List[Dict[str, Any]]:
    """Загружает конфигурации для мониторинга ассетов ВК."""
    configs = []
    config_dir = get_config_path("vk_asset_configs")

    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
        return configs

    filenames = await asyncio.to_thread(os.listdir, config_dir)
    for filename in filenames:
        if filename.endswith('.json'):
            file_path = os.path.join(config_dir, filename)
            try:
                async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    config = json.loads(content)
                    if config.get('owner_id'):
                        configs.append(config)
            except Exception as e:
                await send_to_any_log("error", f"Error loading asset config {filename}: {e}", emoji=LogEmojis.ERROR)
    
    return configs
