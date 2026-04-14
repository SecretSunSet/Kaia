"""Prompt builders for the daily briefing skill."""

from __future__ import annotations


def build_motivational_note_prompt(
    profile_context: str,
    recent_patterns: str,
) -> str:
    """Prompt for generating a personalized morning note."""
    return f"""\
Generate a short (1-2 sentence) personalized motivational or helpful note for the user's morning briefing.

What I know about the user:
{profile_context}

Recent patterns:
{recent_patterns}

Keep it warm, encouraging, and specific to them. Not generic motivation — reference something \
real about their life, goals, or recent progress. If you don't have enough info, give a simple \
friendly greeting.
"""


def build_briefing_time_parse_prompt(timezone: str) -> str:
    """Prompt for parsing briefing time change requests."""
    return f"""\
Parse the user's requested briefing time. The user's timezone is {timezone}.

Return ONLY a JSON object:
{{"time": "HH:MM"}}

Examples:
- "6:30am" → {{"time": "06:30"}}
- "7 in the morning" → {{"time": "07:00"}}
- "8pm" → {{"time": "20:00"}}

If you cannot determine a time, return: {{"time": null}}
"""
