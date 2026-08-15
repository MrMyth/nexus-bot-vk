# content_processing/post_filter.py
import regex
import asyncio
from typing import Dict, Any
from log_system.logger_helper import send_to_any_log
from constants.base import ContentTypes
from constants.emojis  import LogEmojis
from modules.vk_wall.content_processor.config_resolver import ConfigResolver
from modules_utils.helpers import safe_create_task

class PostFilter:
    """
    Статический класс, содержащий логику фильтрации постов.
    """

    @staticmethod
    def mustbe_condition_passed(post: Dict[str, Any], group_config: Dict[str, Any]) -> bool:
        """Проверяет условия mustbe с учетом глобального отключения."""
        if group_config.get("disable_mustbe", False):
            return True

        for att_type in [
            ContentTypes.PHOTO,
            ContentTypes.VIDEO,
            ContentTypes.CLIP,
            ContentTypes.DOC,
            ContentTypes.AUDIO,
            ContentTypes.LINK,
            ContentTypes.ARTICLE,
            ContentTypes.POLL,
            ContentTypes.MAP,
            ContentTypes.MARKET
        ]:
            config = ConfigResolver.get_attachment_config(group_config, att_type)
            if not config["mustbe"]:
                continue
            enabled = config["enabled"]
            has_att = any(att["type"] == att_type for att in post.get("attachments", []))
            if enabled and not has_att:
                return False

        text = post.get("text", "").strip()
        text_config = ConfigResolver.get_attachment_config(group_config, "text")
        if text_config.get("mustbe", False) and not text:
            return False

        return True

    @staticmethod
    def skip_if_only_condition_passed(post: Dict[str, Any], group_config: Dict[str, Any]) -> bool:
        """
        Checks whether post should be skipped based on skip_if_only flag.
        Returns True if post should be skipped.
        """
        if group_config.get("disable_skip_if_only", False):
            return False

        attachment_types = [att["type"] for att in post.get("attachments", [])]
        text = post.get("text", "").strip()
        group_name = group_config.get("name", "Unnamed")
        post_id = post.get("id", "unknown")

        if text:
            return False

        for att_type in attachment_types:
            config = ConfigResolver.get_attachment_config(group_config, att_type)
            if config.get("skip_if_only", False):
                other_attachments = [t for t in attachment_types if t != att_type]
                all_other_skip = all(
                    ConfigResolver.get_attachment_config(group_config, other_type).get("skip_if_only", False)
                    for other_type in other_attachments
                )
                if not other_attachments or all_other_skip:
                    safe_create_task(send_to_any_log("info", f"Post {post_id} (Group: {group_name}) skipped: contains only {att_type} (skip_if_only)", emoji=LogEmojis.INFO))
                    return True

        return False

    @staticmethod
    def _to_list(value: Any) -> list:
        """Helper to convert value to list."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [str(value)]

    @staticmethod
    def should_skip_post(post: Dict[str, Any], group_config: Dict[str, Any]) -> bool:
        """Checks if post should be skipped or filtered."""
        group_name = group_config.get("name", "Unnamed")
        post_id = post.get("id", "unknown")

        skip_pinned = group_config.get("skip_pinned", True)
        if skip_pinned and int(post.get("is_pinned", 0)) == 1:
            safe_create_task(send_to_any_log("info", f"Post {post_id} (Group: {group_name}) skipped: pinned post", emoji=LogEmojis.INFO))
            return True

        skip_ads = group_config.get("skip_ads", True)
        if skip_ads and int(post.get("marked_as_ads", 0)) == 1:
            safe_create_task(send_to_any_log("info", f"Post {post_id} (Group: {group_name}) skipped: ad post", emoji=LogEmojis.INFO))
            return True

        if "copy_history" in post:
            exclude_reposts = group_config.get("exclude_reposts", False)
            if exclude_reposts:
                safe_create_task(send_to_any_log("info", f"Post {post_id} (Group: {group_name}) skipped: reposts disabled (exclude_reposts)", emoji=LogEmojis.INFO))
                return True
                
            repost_config = ConfigResolver.get_attachment_config(group_config, "repost")
            if not repost_config["enabled"]:
                safe_create_task(send_to_any_log("info", f"Post {post_id} (Group: {group_name}) skipped: reposts disabled in config", emoji=LogEmojis.INFO))
                return True

        text = post.get("text", "") or ""
        if not text.strip():
            text = ""
        
        min_text_length = group_config.get("min_text_length", 0)
        if min_text_length > 0 and len(text) < min_text_length:
            safe_create_task(send_to_any_log("info", f"Post {post_id} (Group: {group_name}) skipped: text too short ({len(text)} < {min_text_length})", emoji=LogEmojis.INFO))
            return True

        text_lower = text.lower()

        blacklist_words = [w.strip().lower() for w in PostFilter._to_list(group_config.get("blacklist_words")) if w.strip()]
        blacklist_regex = PostFilter._to_list(group_config.get("blacklist_regex"))

        has_blacklist_match = False

        if blacklist_words:
            if any(word in text_lower for word in blacklist_words):
                has_blacklist_match = True
                safe_create_task(send_to_any_log("info", f"Post {post_id} (Group: {group_name}) contains prohibited word from blacklist_words", emoji=LogEmojis.INFO))

        if not has_blacklist_match and blacklist_regex:
            for pattern in blacklist_regex:
                try:
                    if pattern and regex.search(str(pattern), text, regex.IGNORECASE):
                        has_blacklist_match = True
                        safe_create_task(send_to_any_log("info", f"Post {post_id} (Group: {group_name}) contains prohibited regex: {pattern}", emoji=LogEmojis.INFO))
                        break
                except regex.error as e:
                    safe_create_task(send_to_any_log("warning", f"Invalid regular expression: {pattern} | {e}", emoji=LogEmojis.WARNING))

        if has_blacklist_match:
            if group_config.get("filter_text_only", False):
                post["text"] = " "
                post["__suppress_post_url__"] = True
                safe_create_task(send_to_any_log("info", f"Post {post_id} (Group: {group_name}) — text and link stripped, attachments kept", emoji=LogEmojis.INFO))
                return False
            else:
                safe_create_task(send_to_any_log("info", f"Post {post_id} (Group: {group_name}) skipped by blacklist", emoji=LogEmojis.INFO))
                return True

        whitelist_words = [w.strip().lower() for w in PostFilter._to_list(group_config.get("whitelist_words")) if w.strip()]
        whitelist_regex = PostFilter._to_list(group_config.get("whitelist_regex"))

        has_whitelist = bool(whitelist_words or whitelist_regex)

        if has_whitelist:
            matched = False
            if whitelist_words:
                if any(word in text_lower for word in whitelist_words):
                    matched = True
            if not matched and whitelist_regex:
                for pattern in whitelist_regex:
                    try:
                        if pattern and regex.search(str(pattern), text, regex.IGNORECASE):
                            matched = True
                            break
                    except regex.error as e:
                        safe_create_task(send_to_any_log("warning", f"Invalid regular expression in whitelist_regex: {pattern} | {e}", emoji=LogEmojis.WARNING))
            if not matched:
                safe_create_task(send_to_any_log("info", f"Post {post_id} (Group: {group_name}) skipped: did not match whitelist", emoji=LogEmojis.INFO))
                return True

        return False
