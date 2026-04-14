"""NLP parsing of reminder requests using Claude/Groq."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from loguru import logger

from core.ai_engine import AIEngine
from skills.reminders.prompts import build_parse_prompt
from utils.time_utils import now_in_tz, to_utc


async def parse_reminder(
    ai_engine: AIEngine,
    message: str,
    user_timezone: str = "Asia/Manila",
) -> dict | None:
    """Parse a natural-language reminder into structured data.

    Returns dict with keys: title, datetime_utc (datetime), recurrence (str)
    or None if parsing fails.
    """
    current = now_in_tz(user_timezone)
    current_str = current.strftime("%Y-%m-%d %H:%M:%S %A")

    system_prompt = build_parse_prompt(user_timezone, current_str)

    try:
        response = await ai_engine.chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": message}],
            max_tokens=128,
        )
        return _parse_response(response.text, user_timezone, current)
    except Exception as exc:
        logger.warning("Reminder parsing failed: {}", exc)
        return None


def _parse_response(
    text: str,
    user_timezone: str,
    current: datetime,
) -> dict | None:
    """Extract structured reminder data from the AI response."""
    text = text.strip()

    # Try to parse JSON directly or find it in text
    data: dict | None = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

    if not data:
        logger.warning("Could not parse reminder response: {}", text[:100])
        return None

    title = data.get("title", "Reminder")
    recurrence = data.get("recurrence", "none")
    is_relative = data.get("is_relative", False)

    # Parse the datetime
    dt_str = data.get("datetime", "")
    if not dt_str:
        return None

    try:
        if is_relative:
            # For relative times, the AI returns a future datetime; parse it
            local_dt = datetime.fromisoformat(dt_str)
        else:
            local_dt = datetime.fromisoformat(dt_str)
    except ValueError:
        logger.warning("Could not parse datetime '{}' from reminder", dt_str)
        return None

    # Convert to UTC for storage
    datetime_utc = to_utc(local_dt, from_tz=user_timezone)

    return {
        "title": title,
        "datetime_utc": datetime_utc,
        "recurrence": recurrence,
    }
