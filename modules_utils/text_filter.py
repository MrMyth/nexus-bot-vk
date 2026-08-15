# modules_utils/text_filter.py
import regex
import asyncio
from typing import Dict, Any, List, Optional
from log_system.logger_helper import send_to_any_log
from constants.emojis import LogEmojis
from modules_utils.helpers import safe_create_task

class TextFilter:
    """
    Universal class for filtering text content.
    Supports blacklists/whitelists of words and regular expressions.
    """

    @staticmethod
    def _to_list(value: Any) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [str(value)]

    @staticmethod
    def should_skip(text: str, config: Dict[str, Any], context: str = "Common", second_text: str = "") -> bool:
        """
        Checks whether the text should be skipped based on config.
        
        :param text: Input text to check (primary).
        :param config: Dictionary with settings (blacklist_words, blacklist_regex, etc).
        :param context: Context string for logs (module/group name).
        :param second_text: Additional text to check (e.g. description).
        :return: True if the text should be SKIPPED, False if it passed checks.
        """
        if not text:
            text = ""
        if not second_text:
            second_text = ""
        
        text_lower = text.lower()
        second_text_lower = second_text.lower()
        combined_text_lower = f"{text_lower} {second_text_lower}".strip()

        # 1. BLACKLIST WORDS (check across both fields)
        blacklist_words = [w.strip().lower() for w in TextFilter._to_list(config.get("blacklist_words")) if w.strip()]
        if blacklist_words:
            matched_word = next((word for word in blacklist_words if word in combined_text_lower), None)
            if matched_word:
                safe_create_task(send_to_any_log("info", f"[{context}] Text skipped: contains blacklisted word '{matched_word}'", emoji=LogEmojis.PROHIBITED))
                return True

        # 2. BLACKLIST REGEX
        blacklist_regex = TextFilter._to_list(config.get("blacklist_regex"))
        if blacklist_regex:
            for pattern in blacklist_regex:
                try:
                    if pattern and regex.search(str(pattern), f"{text} {second_text}".strip(), regex.IGNORECASE):
                        safe_create_task(send_to_any_log("info", f"[{context}] Text skipped: matched blacklist_regex: {pattern}", emoji=LogEmojis.PROHIBITED))
                        return True
                except regex.error as e:
                    safe_create_task(send_to_any_log("warning", f"[{context}] Error in blacklist_regex: {pattern} | {e}", emoji=LogEmojis.WARNING))

        # 3. WHITELIST (if specified, AT LEAST ONE match is required)
        whitelist_words = [w.strip().lower() for w in TextFilter._to_list(config.get("whitelist_words")) if w.strip()]
        whitelist_regex = TextFilter._to_list(config.get("whitelist_regex"))

        has_whitelist = bool(whitelist_words or whitelist_regex)
        if has_whitelist:
            matched = False
            if whitelist_words:
                if any(word in combined_text_lower for word in whitelist_words):
                    matched = True
            
            if not matched and whitelist_regex:
                for pattern in whitelist_regex:
                    try:
                        if pattern and regex.search(str(pattern), f"{text} {second_text}".strip(), regex.IGNORECASE):
                            matched = True
                            break
                    except regex.error as e:
                        safe_create_task(send_to_any_log("warning", f"[{context}] Error in whitelist_regex: {pattern} | {e}", emoji=LogEmojis.WARNING))
            
            if not matched:
                return True

        return False
