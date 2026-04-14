"""Reminders skill handler — create, list, cancel, edit reminders."""

from __future__ import annotations

from loguru import logger
from telegram import Bot

from core.ai_engine import AIEngine
from core.scheduler import schedule_reminder
from database.models import User
from database.queries import (
    create_reminder,
    get_active_reminders,
    deactivate_reminder,
)
from skills.base import BaseSkill, SkillResult
from skills.reminders.parser import parse_reminder
from skills.reminders.prompts import format_confirmation, format_reminder_list
from utils.time_utils import format_local

# Store bot reference so the handler can pass it to the scheduler
_bot: Bot | None = None


def set_bot(bot: Bot) -> None:
    """Store the bot reference (called during bot startup)."""
    global _bot
    _bot = bot


class RemindersSkill(BaseSkill):
    """Handles reminder creation, listing, cancellation, and editing."""

    name = "reminders"

    def __init__(self, ai_engine: AIEngine) -> None:
        super().__init__(ai_engine)

    async def handle(
        self,
        user: User,
        message: str,
        conversation_history: list[dict[str, str]],
        profile_context: str,
    ) -> SkillResult:
        lower = message.lower()

        # Detect sub-intent
        if _is_list_request(lower):
            return await self._handle_list(user)
        if _is_cancel_request(lower):
            return await self._handle_cancel(user, message)
        # Default: treat as create
        return await self._handle_create(user, message)

    # ── Create ───────────────────────────────────────────────────────

    async def _handle_create(self, user: User, message: str) -> SkillResult:
        parsed = await parse_reminder(self.ai, message, user.timezone)
        if not parsed:
            return SkillResult(
                text="Sorry, I couldn't understand that reminder. "
                     "Try something like: \"Remind me to take meds at 8pm daily\"",
                skill_name=self.name,
            )

        title = parsed["title"]
        dt_utc = parsed["datetime_utc"]
        recurrence = parsed["recurrence"]

        # Save to DB
        reminder = await create_reminder(
            user_id=user.id,
            title=title,
            scheduled_time=dt_utc.isoformat(),
            recurrence=recurrence,
        )

        # Schedule it
        if _bot:
            await schedule_reminder(
                reminder_id=reminder.id,
                telegram_id=user.telegram_id,
                title=title,
                fire_time_utc=dt_utc,
                bot=_bot,
            )

        display_time = format_local(dt_utc, user.timezone)
        text = format_confirmation(title, display_time, recurrence)

        logger.info(
            "Reminder created: id={} title='{}' at {} recurrence={}",
            reminder.id, title, dt_utc, recurrence,
        )

        return SkillResult(text=text, skill_name=self.name)

    # ── List ─────────────────────────────────────────────────────────

    async def _handle_list(self, user: User) -> SkillResult:
        reminders = await get_active_reminders(user.id)
        items = [
            {
                "title": r.title,
                "display_time": format_local(r.scheduled_time, user.timezone),
                "recurrence": r.recurrence,
            }
            for r in reminders
        ]
        text = format_reminder_list(items)
        return SkillResult(text=text, skill_name=self.name)

    # ── Cancel ───────────────────────────────────────────────────────

    async def _handle_cancel(self, user: User, message: str) -> SkillResult:
        reminders = await get_active_reminders(user.id)
        if not reminders:
            return SkillResult(
                text="You don't have any active reminders to cancel.",
                skill_name=self.name,
            )

        lower = message.lower()

        # Try to match by number (e.g. "cancel reminder 2")
        for word in lower.split():
            if word.isdigit():
                idx = int(word) - 1
                if 0 <= idx < len(reminders):
                    target = reminders[idx]
                    from core.scheduler import cancel_reminder as _cancel
                    await _cancel(target.id)
                    await deactivate_reminder(target.id)
                    return SkillResult(
                        text=f"🗑️ Reminder cancelled: {target.title}",
                        skill_name=self.name,
                    )

        # Try fuzzy title match
        for r in reminders:
            if r.title.lower() in lower or lower in r.title.lower():
                from core.scheduler import cancel_reminder as _cancel
                await _cancel(r.id)
                await deactivate_reminder(r.id)
                return SkillResult(
                    text=f"🗑️ Reminder cancelled: {r.title}",
                    skill_name=self.name,
                )

        # Ambiguous — show list and ask
        items = [
            {
                "title": r.title,
                "display_time": format_local(r.scheduled_time, user.timezone),
                "recurrence": r.recurrence,
            }
            for r in reminders
        ]
        text = (
            "Which reminder do you want to cancel? "
            "Reply with the number:\n\n"
            + format_reminder_list(items)
        )
        return SkillResult(text=text, skill_name=self.name)


def _is_list_request(text: str) -> bool:
    patterns = [
        "what reminders",
        "show my reminders",
        "list reminders",
        "my reminders",
        "show reminders",
        "active reminders",
        "upcoming reminders",
        "what alarms",
        "show alarms",
    ]
    return any(p in text for p in patterns)


def _is_cancel_request(text: str) -> bool:
    patterns = [
        "cancel reminder",
        "cancel my reminder",
        "delete reminder",
        "remove reminder",
        "cancel alarm",
        "delete alarm",
        "stop reminder",
        "cancel the",
        "remove the",
    ]
    return any(p in text for p in patterns)
