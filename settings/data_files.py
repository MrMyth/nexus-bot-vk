import os
from settings.config import Config


class Files:
    # --- Base paths ---
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # --- Subfolders ---
    DATA_PATH = os.path.abspath(os.path.join(PROJECT_ROOT, Config.DATA_FOLDER))
    DB_FOLDER = os.path.join(DATA_PATH, "db")
    JSON_FOLDER = os.path.join(DATA_PATH, "json")
    SYSTEM_CONFIGS_FOLDER = os.path.join(JSON_FOLDER, "system_configs")
    CACHE_FOLDER = os.path.join(JSON_FOLDER, "caches")
    LOGS_FOLDER = os.path.join(DATA_PATH, "logs")
    ASSETS_FOLDER = os.path.join(PROJECT_ROOT, "assets")
    SELENIUM_CACHE_FOLDER = os.path.join(DATA_PATH, "selenium_cache")
    SAVE_STREAM_PREVIEW_FOLDER = os.path.abspath(os.path.join(DATA_PATH, Config.SAVE_STREAM_PREVIEW_FOLDER))

    # --- Logs ---
    LOG_FILE = os.path.join(LOGS_FOLDER, Config.LOG_FILE_NAME)
    MENTIONS_LOG_FILE = os.path.join(LOGS_FOLDER, Config.MENTIONS_LOG_FILE_NAME)

    # --- Databases ---
    DATABASE_FILE = os.path.join(DB_FOLDER, Config.VK_POSTS_DB_FILE_NAME)
    LIVE_DATABASE_FILE = os.path.join(DB_FOLDER, Config.VK_LIVE_DB_FILE_NAME)
    CHANNEL_DATABASE_STREAM_FILE = os.path.join(DB_FOLDER, Config.VK_CHANNEL_STREAM_DB_FILE_NAME)
    CHANNEL_DATABASE_VIDEO_FILE = os.path.join(DB_FOLDER, Config.VK_CHANNEL_VIDEO_DB_FILE_NAME)
    YOUTUBE_DATABASE_FILE = os.path.join(DB_FOLDER, Config.YOUTUBE_DATABASE_FILE_NAME)
    RUTUBE_DATABASE_FILE = os.path.join(DB_FOLDER, Config.RUTUBE_DATABASE_FILE_NAME)
    TWITCH_DATABASE_FILE = os.path.join(DB_FOLDER, Config.TWITCH_DATABASE_FILE_NAME)
    KICK_DATABASE_FILE = os.path.join(DB_FOLDER, Config.KICK_DATABASE_FILE_NAME)
    TROVO_DATABASE_FILE = os.path.join(DB_FOLDER, Config.TROVO_DATABASE_FILE_NAME)
    VK_COM_LIVE_DATABASE_FILE = os.path.join(DB_FOLDER, Config.VK_COM_LIVE_DATABASE_FILE_NAME)
    GOODGAME_DATABASE_FILE = os.path.join(DB_FOLDER, Config.GOODGAME_DATABASE_FILE_NAME)
    VK_ASSETS_DATABASE_FILE = os.path.join(DB_FOLDER, Config.VK_ASSETS_DATABASE_FILE_NAME)
    USER_ACTIVITY_DATABASE_FILE = os.path.join(DB_FOLDER, Config.USER_ACTIVITY_DATABASE_FILE_NAME)

    # --- System JSON configs ---
    STOP_REASON_FILE = os.path.join(SYSTEM_CONFIGS_FOLDER, "stop_reason.json")
    CHANNEL_PROTECTION_LIST_PATH = os.path.join(SYSTEM_CONFIGS_FOLDER, Config.CHANNEL_PROTECTION_LIST_FILE_NAME)
    VOICE_CHANNEL_LIST_PATH = os.path.join(SYSTEM_CONFIGS_FOLDER, Config.VOICE_CHANNEL_FILE_NAME)
    STREAM_TOOLS_CONFIG_PATH = os.path.join(SYSTEM_CONFIGS_FOLDER, Config.STREAM_TOOLS_CONFIG_FILE_NAME)
    ROLE_DEPENDENCY_CONFIG_PATH = os.path.join(SYSTEM_CONFIGS_FOLDER, Config.ROLE_DEPENDENCY_CONFIG_FILE_NAME)
    SECRET_VENDORS_CONFIG_FILE = os.path.join(SYSTEM_CONFIGS_FOLDER, "secret_vendors_config.json")
    GAME_SCHEDULE_CONFIG_FILE = os.path.join(SYSTEM_CONFIGS_FOLDER, "game_schedule_config.json")
    IMAGE_FORWARDER_CONFIG_FILE = os.path.join(SYSTEM_CONFIGS_FOLDER, "image_forwarder_config.json")
    IMAGE_FORWARDER_TEMP_FOLDER = os.path.join(DATA_PATH, "temp", "image_forwarder")
    DEFAULT_EMBEDS_CONFIG_PATH = os.path.join(SYSTEM_CONFIGS_FOLDER, "default_embeds_config.json")
    BOT_PRESENCE_CONFIG_PATH = os.path.join(SYSTEM_CONFIGS_FOLDER, "bot_presence.json")
    STATUS_CONFIG_PATH = os.path.join(SYSTEM_CONFIGS_FOLDER, "status_config.json")
    WEBHOOKS_METADATA_CONFIG_PATH = os.path.join(SYSTEM_CONFIGS_FOLDER, "webhooks_metadata.json")
    STRINGS_CONFIG_PATH = os.path.join(SYSTEM_CONFIGS_FOLDER, "strings.json")
    STRINGS_RU_CONFIG_PATH = os.path.join(SYSTEM_CONFIGS_FOLDER, "strings_ru.json")
    STRINGS_EN_CONFIG_PATH = os.path.join(SYSTEM_CONFIGS_FOLDER, "strings_en.json")

    # --- Cache files ---
    CACHE_FILE = os.path.join(CACHE_FOLDER, Config.CACHE_FILE_NAME)
    LIVE_CACHE_FILE = os.path.join(CACHE_FOLDER, Config.LIVE_CACHE_FILE_NAME)
    VIDEO_CACHE_FILE = os.path.join(CACHE_FOLDER, Config.VIDEO_CACHE_FILE_NAME)
    PDF_CACHE_FILE = os.path.join(CACHE_FOLDER, Config.PDF_CACHE_FILE_NAME)
    TELEGRAM_CACHE_FILE = os.path.join(CACHE_FOLDER, Config.TELEGRAM_CACHE_FILE_NAME)
    TRELLO_CACHE_FILE = os.path.join(CACHE_FOLDER, Config.TRELLO_CACHE_FILE_NAME)
    SECRET_VENDORS_CACHE_FILE = os.path.join(CACHE_FOLDER, "secret_vendors_cache.json")
    GAME_SCHEDULE_CACHE_FILE = os.path.join(CACHE_FOLDER, "game_schedule_cache.json")

    @staticmethod
    def ensure_directories():
        folders = [
            Files.DATA_PATH,
            Files.DB_FOLDER,
            Files.JSON_FOLDER,
            Files.SYSTEM_CONFIGS_FOLDER,
            Files.CACHE_FOLDER,
            Files.LOGS_FOLDER,
            Files.ASSETS_FOLDER,
            Files.SELENIUM_CACHE_FOLDER,
            Files.IMAGE_FORWARDER_TEMP_FOLDER,
            Files.SAVE_STREAM_PREVIEW_FOLDER,
        ]
        for folder in folders:
            os.makedirs(folder, exist_ok=True)

        # Automatically migrate existing system config files from JSON_FOLDER to SYSTEM_CONFIGS_FOLDER
        system_files = [
            "stop_reason.json",
            Config.CHANNEL_PROTECTION_LIST_FILE_NAME,
            Config.VOICE_CHANNEL_FILE_NAME,
            Config.STREAM_TOOLS_CONFIG_FILE_NAME,
            Config.ROLE_DEPENDENCY_CONFIG_FILE_NAME,
            "secret_vendors_config.json",
            "game_schedule_config.json",
            "image_forwarder_config.json",
            "default_embeds_config.json",
            "bot_presence.json",
            "status_config.json",
            "strings.json",
        ]
        for fname in system_files:
            if not fname:
                continue
            old_path = os.path.join(Files.JSON_FOLDER, fname)
            new_path = os.path.join(Files.SYSTEM_CONFIGS_FOLDER, fname)
            if os.path.isfile(old_path):
                if not os.path.exists(new_path):
                    try:
                        os.rename(old_path, new_path)
                        print(f"[FILES] Migrated system config: {fname} -> system_configs/")
                    except Exception as e:
                        print(f"[FILES] Error migrating {old_path} to {new_path}: {e}")
                else:
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass

        # Automatically migrate cache files from JSON_FOLDER to CACHE_FOLDER
        if os.path.exists(Files.JSON_FOLDER):
            for item in os.listdir(Files.JSON_FOLDER):
                item_path = os.path.join(Files.JSON_FOLDER, item)
                if os.path.isfile(item_path) and item.endswith(".json"):
                    target_path = os.path.join(Files.CACHE_FOLDER, item)
                    if not os.path.exists(target_path):
                        try:
                            os.rename(item_path, target_path)
                            print(f"[FILES] Migrated cache file: {item} -> caches/")
                        except Exception as e:
                            print(f"[FILES] Error migrating {item_path} to {target_path}: {e}")
                    else:
                        try:
                            os.remove(item_path)
                        except Exception:
                            pass
