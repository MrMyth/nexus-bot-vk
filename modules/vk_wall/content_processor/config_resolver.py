from typing import Dict, Any
from constants.base import DefaultAttachmentSettings
from constants.emojis  import Emojis
from constants.colors import DefaultColors
from modules_utils.helpers import hex_to_color_int

class ConfigResolver:
    """
    Статический класс для получения и нормализации конфигурации вложений.
    """

    @staticmethod
    def get_attachment_config(group_config: Dict[str, Any], att_type: str) -> dict:
        """Возвращает конфигурацию для указанного типа вложения."""
        attachments = group_config.get("attachments", {})
        config = attachments.get(att_type, {})

        defaults = {
            "enabled": DefaultAttachmentSettings.ENABLED,
            "as_file": DefaultAttachmentSettings.AS_FILE,
            "mustbe": DefaultAttachmentSettings.MUSTBE,
            "skip_if_only": DefaultAttachmentSettings.SKIP_IF_ONLY,
            "emoji": getattr(Emojis, att_type.upper(), Emojis.TEXT) if att_type != "text" else Emojis.TEXT,
            "preview": group_config.get("preview")
        }

        color_hex = config.get("color")
        if not color_hex:
            color_hex = group_config.get("color")
        if not color_hex:
            color_hex = DefaultColors.DEFAULT

        result = {}
        for key, default_value in defaults.items():
            result[key] = config.get(key, default_value)

        result["color"] = hex_to_color_int(color_hex, default=hex_to_color_int(DefaultColors.DEFAULT))

        return result

    @staticmethod
    def get_edit_config(group_config: Dict[str, Any]) -> dict:
        """Возвращает конфигурацию для уведомления о редактировании."""
        attachments = group_config.get("attachments", {})
        edit_config = attachments.get("edit", {})

        preview_val = group_config.get("preview")
        defaults = {
            "enabled": True,
            "as_file": False,
            "emoji": Emojis.EDIT,
            "preview": preview_val.get("edit") if isinstance(preview_val, dict) else None,
            "color": group_config.get("color", DefaultColors.DEFAULT)
        }

        result = {}
        for key, default_value in defaults.items():
            result[key] = edit_config.get(key, default_value)

        result["color"] = hex_to_color_int(result["color"], default=hex_to_color_int(DefaultColors.DEFAULT))

        return result