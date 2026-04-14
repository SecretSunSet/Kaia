"""Input validation utilities."""

from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config.constants import CURRENCY_SYMBOLS


def sanitize_message(text: str) -> str:
    """Strip potentially harmful content and normalize whitespace."""
    if not text:
        return ""
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text.strip())
    # Remove null bytes
    text = text.replace("\x00", "")
    return text


def is_valid_amount(text: str) -> bool:
    """Check if a string represents a valid monetary amount."""
    cleaned = re.sub(r"[₱$€£¥,\s]", "", text.strip())
    try:
        val = float(cleaned)
        return val > 0
    except (ValueError, TypeError):
        return False


def validate_timezone(tz: str) -> bool:
    """Check if a timezone string is valid."""
    try:
        ZoneInfo(tz)
        return True
    except (ZoneInfoNotFoundError, KeyError):
        return False


def validate_currency(code: str) -> bool:
    """Check if a currency code is supported."""
    return code.upper() in CURRENCY_SYMBOLS
