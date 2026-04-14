"""Telegram formatting helpers."""

from __future__ import annotations

import re
from datetime import datetime

from config.constants import CURRENCY_SYMBOLS, MAX_TELEGRAM_MESSAGE_LENGTH


def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2.

    Note: KAIA uses Markdown (not MarkdownV2) for most messages,
    so this is only needed when sending MarkdownV2 explicitly.
    """
    special = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special)}])", r"\\\1", text)


def format_currency(amount: float, currency: str = "PHP") -> str:
    """Format amount with currency symbol: e.g. ₱1,500.00"""
    symbol = CURRENCY_SYMBOLS.get(currency.upper(), currency)
    return f"{symbol}{amount:,.2f}"


def format_datetime(dt: datetime, timezone: str = "Asia/Manila") -> str:
    """Format datetime for display in user's timezone."""
    from utils.time_utils import to_local
    local = to_local(dt, timezone)
    return local.strftime("%b %d, %Y %I:%M %p").replace(" 0", " ")


def truncate(text: str, max_length: int = MAX_TELEGRAM_MESSAGE_LENGTH - 100) -> str:
    """Truncate text to fit Telegram message limit (with safety margin)."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "\n\n... (truncated)"
