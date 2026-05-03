"""Timezone conversion and date parsing utilities."""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta


def now_utc() -> datetime:
    """Return the current time in UTC (timezone-aware)."""
    return datetime.now(timezone.utc)


def now_in_tz(tz_name: str = "Asia/Manila") -> datetime:
    """Return the current time in the given timezone."""
    return datetime.now(ZoneInfo(tz_name))


def today_in_tz(tz_name: str = "Asia/Manila") -> date:
    """Return today's calendar date in the given timezone."""
    return now_in_tz(tz_name).date()


def to_utc(dt: datetime, from_tz: str = "Asia/Manila") -> datetime:
    """Convert a naive or local datetime to UTC.

    If *dt* is naive, it is assumed to be in *from_tz*.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(from_tz))
    return dt.astimezone(timezone.utc)


def to_local(dt: datetime, to_tz: str = "Asia/Manila") -> datetime:
    """Convert a UTC (or any tz-aware) datetime to a local timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(to_tz))


def format_local(dt: datetime, to_tz: str = "Asia/Manila") -> str:
    """Format a datetime for display in the user's timezone.

    Returns something like: "Mon Apr 14 08:00 PM"
    """
    local = to_local(dt, to_tz)
    return local.strftime("%a %b %d %I:%M %p")


def format_current_context(tz_name: str = "Asia/Manila") -> str:
    """Format the current date/time as a block for system-prompt injection.

    Returns a string like:
        "Current date and time: Saturday, May 02, 2026 at 03:45 PM
         (Asia/Manila, UTC+08:00).
         Today is May 02, 2026. The current year is 2026. It is currently Saturday."
    """
    now = now_in_tz(tz_name)
    raw_offset = now.strftime("%z")  # e.g. "+0800"
    offset = f"{raw_offset[:3]}:{raw_offset[3:]}" if raw_offset else "+00:00"
    return (
        f"Current date and time: "
        f"{now.strftime('%A, %B %d, %Y at %I:%M %p')} "
        f"({tz_name}, UTC{offset}). "
        f"Today is {now.strftime('%B %d, %Y')}. "
        f"The current year is {now.year}. "
        f"It is currently {now.strftime('%A')}."
    )


def format_relative_time(
    dt: "datetime | str | None", tz_name: str = "Asia/Manila"
) -> str:
    """Format a timestamp as relative time from now in the user's timezone.

    Accepts either a ``datetime`` or an ISO-8601 string (Supabase's REST API
    returns timestamps as strings). Returns an empty string if ``dt`` is None
    or unparseable.

    Examples: "just now", "5 minutes ago", "2 hours ago",
    "yesterday at 3:45 PM", "3 days ago (Tuesday, Apr 28)",
    "last week (Apr 25)", "2 weeks ago (Apr 18)",
    "1 month ago (Apr 02, 2026)", "1 year ago (May 02, 2025)".
    """
    if dt is None:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(ZoneInfo(tz_name))
    now = now_in_tz(tz_name)

    secs = (now - local).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600 and now.date() == local.date():
        mins = int(secs // 60)
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    if secs < 86400 and now.date() == local.date():
        hrs = int(secs // 3600)
        return f"{hrs} hour{'s' if hrs != 1 else ''} ago"

    day_diff = (now.date() - local.date()).days
    if day_diff == 0:
        # Same calendar date but reported as "today"
        return f"earlier today at {local.strftime('%I:%M %p').lstrip('0')}"
    if day_diff == 1:
        return f"yesterday at {local.strftime('%I:%M %p').lstrip('0')}"
    if day_diff < 7:
        return f"{day_diff} days ago ({local.strftime('%A, %b %d')})"
    if day_diff < 14:
        return f"last week ({local.strftime('%b %d')})"
    if day_diff < 30:
        weeks = day_diff // 7
        return f"{weeks} week{'s' if weeks != 1 else ''} ago ({local.strftime('%b %d')})"
    if day_diff < 365:
        months = day_diff // 30
        return f"{months} month{'s' if months != 1 else ''} ago ({local.strftime('%b %d, %Y')})"
    years = day_diff // 365
    return f"{years} year{'s' if years != 1 else ''} ago ({local.strftime('%b %d, %Y')})"


def format_transaction_with_time(
    tx: Any, tz_name: str = "Asia/Manila", currency_symbol: str = "₱"
) -> str:
    """Format a Transaction (or any object exposing amount/description/category/created_at).

    Returns a one-line string like:
        "₱350.00 - Tiktok Shop (Shopping) — logged 5 days ago (Tuesday, Apr 27)"
    """
    created = getattr(tx, "created_at", None)
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            created = None
    when = f" — logged {format_relative_time(created, tz_name)}" if created else ""

    desc_val = getattr(tx, "description", None)
    desc = f" - {desc_val}" if desc_val else ""

    cat_val = getattr(tx, "category", "") or ""
    cat = f" ({cat_val.title()})" if cat_val else ""

    amount = float(getattr(tx, "amount", 0))
    return f"{currency_symbol}{amount:,.2f}{desc}{cat}{when}"


def next_occurrence(dt: datetime, recurrence: str) -> datetime:
    """Calculate the next occurrence of a recurring reminder.

    Args:
        dt: The current scheduled time (UTC).
        recurrence: "daily", "weekly", or "monthly".

    Returns:
        The next fire time (UTC).
    """
    if recurrence == "daily":
        return dt + timedelta(days=1)
    if recurrence == "weekly":
        return dt + timedelta(weeks=1)
    if recurrence == "monthly":
        return dt + relativedelta(months=1)
    return dt  # "none" — should not be called, but safe
