"""Timezone conversion and date parsing utilities."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta


def now_utc() -> datetime:
    """Return the current time in UTC (timezone-aware)."""
    return datetime.now(timezone.utc)


def now_in_tz(tz_name: str = "Asia/Manila") -> datetime:
    """Return the current time in the given timezone."""
    return datetime.now(ZoneInfo(tz_name))


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
