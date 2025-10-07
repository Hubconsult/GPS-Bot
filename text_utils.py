from __future__ import annotations

import re

from telebot import util as telebot_util

__all__ = ["sanitize_model_output", "sanitize_for_telegram"]


_RESPONSE_REPR = re.compile(r"Response\w+Item\([^)]*\)")


def sanitize_model_output(text: object) -> str:
    """Normalize raw model output before presenting it to users."""

    if isinstance(text, str):
        cleaned = _RESPONSE_REPR.sub("", text)
        return cleaned.strip()

    if text is None:
        return ""

    return _RESPONSE_REPR.sub("", str(text)).strip()


def sanitize_for_telegram(text: object) -> str:
    """Remove service markup and escape HTML for Telegram delivery."""

    sanitized = sanitize_model_output(text)
    if not sanitized:
        return ""

    cleaned = sanitized.replace("<think>", "").replace("</think>", "")
    cleaned = cleaned.replace("<reasoning>", "").replace("</reasoning>", "")
    cleaned = cleaned.replace("\x00", "")
    return telebot_util.escape(cleaned)
