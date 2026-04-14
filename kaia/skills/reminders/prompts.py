"""Prompts for the reminders skill — parsing, confirmation, and listing."""


def build_parse_prompt(user_timezone: str, current_datetime: str) -> str:
    """System prompt for NLP reminder parsing."""
    return f"""\
Parse this reminder request into structured data.

The user's timezone is {user_timezone}.
The current date/time in their timezone is {current_datetime}.

Return ONLY a JSON object (no other text):
{{
  "title": "short description of what to remember",
  "datetime": "YYYY-MM-DDTHH:MM:SS (in the user's local timezone)",
  "recurrence": "none" | "daily" | "weekly" | "monthly",
  "is_relative": true | false
}}

RULES:
- "morning" = 07:00, "afternoon" = 14:00, "evening" = 18:00, "tonight" / "night" = 20:00
- "tomorrow" = next day. If no time given, default to 09:00.
- "in X minutes" / "in X hours" → add to current time, set is_relative true.
- "every day" / "daily" → recurrence "daily"
- "every week" / "weekly" / "every Monday" → recurrence "weekly"
- "every month" / "monthly" → recurrence "monthly"
- If no time is specified at all, default to 09:00 the next day.
- Always output a full datetime, never leave it vague.
- If the requested time has already passed today, schedule for the next day.
"""


def format_confirmation(title: str, display_time: str, recurrence: str) -> str:
    """Build a nice Telegram confirmation message."""
    rec = ""
    if recurrence != "none":
        rec = f" ({recurrence})"
    return f"✅ *Reminder set*\n\n📌 {title}\n🕐 {display_time}{rec}"


def format_reminder_list(reminders: list[dict]) -> str:
    """Build a formatted list of active reminders for display.

    Each item in *reminders* should have ``title``, ``display_time``, ``recurrence``.
    """
    if not reminders:
        return "You don't have any active reminders."
    lines = ["*Your reminders:*\n"]
    for i, r in enumerate(reminders, 1):
        rec = f" 🔁 {r['recurrence']}" if r["recurrence"] != "none" else ""
        lines.append(f"{i}. 📌 {r['title']}\n   🕐 {r['display_time']}{rec}")
    return "\n".join(lines)


def format_fire_message(title: str) -> str:
    """Message sent when a reminder fires."""
    return f"⏰ *Reminder*\n\n{title}"
