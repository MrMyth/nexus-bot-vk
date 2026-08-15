# modules_utils/files.py
import os
from settings.config import Config

# Корень проекта (рассчитывается относительно этого файла)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_config_path(*path_parts: str) -> str:
    """Возвращает абсолютный путь к файлу/папке конфигураций (по умолчанию в data/json, data/json/system_configs или data/json/caches)"""
    full_path = os.path.join(PROJECT_ROOT, Config.FOLLOWS_CONFIGS_FOLDER, *path_parts)
    if not os.path.exists(full_path) and path_parts and len(path_parts) == 1:
        system_path = os.path.join(PROJECT_ROOT, Config.FOLLOWS_CONFIGS_FOLDER, "system_configs", path_parts[0])
        if os.path.exists(system_path):
            return system_path
        cache_path = os.path.join(PROJECT_ROOT, Config.FOLLOWS_CONFIGS_FOLDER, "caches", path_parts[0])
        if os.path.exists(cache_path):
            return cache_path
    try:
        if path_parts:
            last_part = path_parts[-1]
            if not os.path.splitext(last_part)[1]:
                os.makedirs(full_path, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
        else:
            os.makedirs(full_path, exist_ok=True)
    except Exception:
        pass
    return full_path

def get_project_path(*path_parts: str) -> str:
    """Возвращает абсолютный путь к файлу/папке в проекте"""
    return os.path.join(PROJECT_ROOT, *path_parts)
