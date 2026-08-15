# constants/base.py

USE_VK_RU_DOMAIN = True


class _TextMeta(type):
    """Метакласс: обращение к несуществующему атрибуту класса возвращает "" вместо AttributeError."""
    def __getattr__(cls, name: str):
        return ""


class BotVersion(metaclass=_TextMeta):
    VERSION = "4.1"
    DATE = "11.08.2026 13:50 МСК"
    FULL_VERSION = "версия 4.1 от 11.08.2026 13:50 по Москве"


class Text(metaclass=_TextMeta):
    PASS = ""
    INFO_EMBED = "Кликни на автора, чтобы открыть группу. Кликни на заголовок для открытия медиа или поста."


class AsyncDelays(metaclass=_TextMeta):
    BETWEEN_GROUPS = 5
    BETWEEN_POSTS = 1
    PHOTO_DOWNLOAD_TIMEOUT = 30


class ContentTypes(metaclass=_TextMeta):
    ARTICLE = "article"
    AUDIO = "audio"
    CLIP = "clip"
    DOC = "doc"
    LINK = "link"
    MAP = "map"
    MARKET = "market"
    PHOTO = "photo"
    POLL = "poll"
    REPOST = "repost"
    TEXT = "text"
    VIDEO = "video"


class DefaultAttachmentSettings(metaclass=_TextMeta):
    AS_FILE = False
    ENABLED = True
    MUSTBE = False
    PREVIEW = None
    SKIP_IF_ONLY = False


class DiscordLimits(metaclass=_TextMeta):
    MAX_AUTHOR_NAME = 256
    MAX_EMBED_DESCRIPTION = 4096
    MAX_EMBED_TITLE = 256
    MAX_EMBEDS = 10
    MAX_FIELD_NAME = 256
    MAX_FIELD_VALUE = 1024
    MAX_FILE_SIZE = 25 * 1024 * 1024
    MAX_FILES = 10
    MAX_FOOTER_TEXT = 2048
    MAX_TEXT_LENGTH = 2000
    # Псевдонимы для совместимости со старым API
    EMBED_DESCRIPTION = 4096
    MESSAGE_CONTENT = 2000


class HashConstants(metaclass=_TextMeta):
    EMPTY_HASH = "empty"
    MAX_HASH_LENGTH = 64


class PhotoDelay(metaclass=_TextMeta):
    SECONDS = 10


class PhotoExtensions(metaclass=_TextMeta):
    ALLOWED = ('jpg', 'jpeg', 'png', 'gif', 'webp')
    DEFAULT = 'jpg'


class TimeIntervals(metaclass=_TextMeta):
    DB_CLEANUP_INTERVAL = 86400
    MAX_CHECK_INTERVAL = 3600
    MIN_CHECK_INTERVAL = 30


class VKAPI(metaclass=_TextMeta):
    DOMAIN = "vk.ru" if USE_VK_RU_DOMAIN else "vk.com"
    BASE_URL = f"https://api.{DOMAIN}/method"
    BASE_URL_VK_LIVE = "live.vkvideo.ru"
    BASE_URL_VK_VIDEO = "vk.com"
    VERSION = "5.241"
    TIMEOUT = 30
    MAX_RETRIES = 3
    GROUP_PHOTO_FIELD = "photo_200"
    FILTER_OWNER = "owner"
    METHODS = {
        'RESOLVE_SCREEN_NAME': 'utils.resolveScreenName',
        'VIDEO_GET': 'video.getLiveStatus',
        'GET_GROUP_BY_ID': 'groups.getById',
        'WALL_GET': 'wall.get',
    }


class VKConstants(metaclass=_TextMeta):
    GROUP_PREFIXES = ("club", "public", "group")
    MAX_POST_LENGTH = 10000
    OBJECT_TYPE_GROUP = "group"
    USER_PREFIXES = ("id",)


BASE_DIR = "."
