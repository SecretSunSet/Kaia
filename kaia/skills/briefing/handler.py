"""Daily briefing skill — compiles morning summary from multiple data sources."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone as tz

from loguru import logger

from config.constants import (
    BUDGET_CATEGORY_EMOJIS,
    CURRENCY_SYMBOLS,
    SKILL_BRIEFING,
)
from config.settings import get_settings
from core.ai_engine import AIEngine
from database import queries as db
from database.models import User
from skills.base import BaseSkill, SkillResult
from skills.briefing.prompts import build_motivational_note_prompt, build_briefing_time_parse_prompt
from skills.web_browse.search import get_weather
from utils.time_utils import format_local, now_in_tz, today_in_tz


class BriefingSkill(BaseSkill):
    """Compiles and delivers the daily briefing."""

    name = SKILL_BRIEFING

    def __init__(self, ai_engine: AIEngine) -> None:
        super().__init__(ai_engine)

    async def handle(
        self,
        user: User,
        message: str,
        conversation_history: list[dict[str, str]],
        profile_context: str,
    ) -> SkillResult:
        msg = message.lower().strip()

        if _is_disable_request(msg):
            return await self._handle_disable(user)

        if _is_time_change_request(msg):
            return await self._handle_time_change(user, message)

        # Default: generate the briefing
        text = await self.generate_briefing(user, profile_context)
        return SkillResult(text=text, skill_name=self.name)

    async def generate_briefing(
        self,
        user: User,
        profile_context: str = "",
    ) -> str:
        """Compile all briefing components and format the morning message.

        Called both on-demand (via handle) and by the scheduler.
        """
        settings = get_settings()
        tz_name = user.timezone or settings.default_timezone
        currency = user.currency or settings.default_currency
        symbol = CURRENCY_SYMBOLS.get(currency, currency)

        # Load profile if not provided
        if not profile_context:
            profile_context = await _load_profile(user.id)

        # Gather all sections in parallel
        results = await asyncio.gather(
            self._get_reminders_section(user.id, tz_name),
            self._get_budget_section(user.id, symbol, tz_name),
            self._get_weather_section(profile_context),
            self._get_motivational_note(profile_context),
            return_exceptions=True,
        )

        reminders_section = results[0] if not isinstance(results[0], Exception) else ""
        budget_section = results[1] if not isinstance(results[1], Exception) else ""
        weather_section = results[2] if not isinstance(results[2], Exception) else ""
        note_section = results[3] if not isinstance(results[3], Exception) else ""

        # Assemble briefing — header carries the current date so the user sees
        # "today" anchored, and so the briefing is unambiguous if delivered
        # late or rescheduled.
        today = now_in_tz(tz_name)
        header = (
            f"🌅 Good morning! Here's your daily briefing — "
            f"{today.strftime('%A, %B %d, %Y')}:"
        )
        sections = [header]

        if weather_section:
            sections.append(f"\n🌤️ Weather\n{weather_section}")

        if reminders_section:
            sections.append(f"\n⏰ Today's Reminders\n{reminders_section}")

        if budget_section:
            sections.append(f"\n💰 Budget Snapshot\n{budget_section}")

        if note_section:
            sections.append(f"\n💡 Note\n{note_section}")

        # If ALL sections empty
        if len(sections) == 1:
            return "🌅 Good morning! Not much on the agenda today. Have a great day!"

        return "\n".join(sections)

    # ── Section builders ─────────────────────────────────────────────

    async def _get_reminders_section(self, user_id: str, tz_name: str) -> str:
        """Get today's reminders."""
        try:
            reminders = await db.get_active_reminders(user_id)
            if not reminders:
                return ""

            today = now_in_tz(tz_name).date()
            today_reminders = []
            for r in reminders:
                local_time = format_local(r.scheduled_time, tz_name)
                # Check if reminder is for today (format_local returns e.g. "Mon Apr 14 08:00 PM")
                r_date = r.scheduled_time
                if r_date.tzinfo is None:
                    r_date = r_date.replace(tzinfo=tz.utc)
                from utils.time_utils import to_local
                local_dt = to_local(r_date, tz_name)
                if local_dt.date() == today or r.recurrence != "none":
                    time_str = local_dt.strftime("%I:%M %p").lstrip("0")
                    today_reminders.append(f"- {time_str} — {r.title}")

            if not today_reminders:
                return ""
            return "\n".join(today_reminders)

        except Exception as exc:
            logger.error("Briefing reminders failed: {}", exc)
            return ""

    async def _get_budget_section(
        self, user_id: str, symbol: str, tz_name: str
    ) -> str:
        """Get current month budget snapshot."""
        try:
            today = today_in_tz(tz_name)
            start = today.replace(day=1).isoformat()
            end = today.isoformat()

            expenses = await db.get_expense_total(user_id, start, end)
            if expenses == 0:
                return ""

            income = await db.get_income_total(user_id, start, end)
            day_of_month = today.day
            daily_avg = expenses / day_of_month if day_of_month > 0 else 0

            lines = [
                f"Spent: {symbol}{expenses:,.2f} this month",
                f"Income: {symbol}{income:,.2f}",
                f"Daily average: {symbol}{daily_avg:,.2f}",
            ]

            # Check budget limits
            limits = await db.get_budget_limits(user_id)
            for bl in limits:
                spent = await db.get_category_total(user_id, bl.category, start, end)
                lim = float(bl.monthly_limit)
                if lim > 0 and spent >= lim * 0.8:
                    emoji = BUDGET_CATEGORY_EMOJIS.get(bl.category, "📦")
                    pct = spent / lim * 100
                    status = "🚨" if spent >= lim else "⚠️"
                    lines.append(
                        f"{status} {emoji} {bl.category.title()}: "
                        f"{symbol}{spent:,.0f} / {symbol}{lim:,.0f} ({pct:.0f}%)"
                    )

            return "\n".join(lines)

        except Exception as exc:
            logger.error("Briefing budget failed: {}", exc)
            return ""

    async def _get_weather_section(self, profile_context: str) -> str:
        """Get current weather."""
        try:
            settings = get_settings()
            if not settings.openweather_api_key:
                return ""

            # Try to find location from profile, fall back to default
            location = settings.default_location
            if "location" in profile_context.lower() or "city" in profile_context.lower():
                # Crude extraction — look for location in profile
                for line in profile_context.split("\n"):
                    low = line.lower()
                    if "location" in low or "city" in low or "lives in" in low:
                        # Extract value after colon
                        if ":" in line:
                            location = line.split(":", 1)[1].strip()
                            break

            weather = await get_weather(location)
            if weather is None:
                return ""

            return (
                f"{weather['location']} — {weather['temp']:.0f}°C, "
                f"{weather['description']}, Humidity {weather['humidity']}%"
            )

        except Exception as exc:
            logger.error("Briefing weather failed: {}", exc)
            return ""

    async def _get_motivational_note(self, profile_context: str) -> str:
        """Generate a personalized motivational note."""
        try:
            prompt = build_motivational_note_prompt(
                profile_context=profile_context,
                recent_patterns="(Based on user profile above)",
            )
            response = await self.ai.chat(
                system_prompt=prompt,
                messages=[{"role": "user", "content": "Generate my morning note"}],
                max_tokens=100,
            )
            return response.text.strip()

        except Exception as exc:
            logger.error("Briefing motivational note failed: {}", exc)
            return ""

    # ── Briefing management ──────────────────────────────────────────

    async def _handle_disable(self, user: User) -> SkillResult:
        """Disable the daily briefing."""
        from core.scheduler import cancel_daily_briefing
        await cancel_daily_briefing(user.id)
        return SkillResult(
            text="✅ Daily briefing turned off. Say 'turn on daily briefing' to re-enable.",
            skill_name=self.name,
        )

    async def _handle_time_change(self, user: User, message: str) -> SkillResult:
        """Change the daily briefing time."""
        tz_name = user.timezone or get_settings().default_timezone

        try:
            prompt = build_briefing_time_parse_prompt(tz_name)
            response = await self.ai.chat(
                system_prompt=prompt,
                messages=[{"role": "user", "content": message}],
                max_tokens=32,
            )
            data = json.loads(response.text.strip())
            time_str = data.get("time")
            if not time_str:
                return SkillResult(
                    text="I couldn't understand the time. Try: 'Change briefing to 6:30am'",
                    skill_name=self.name,
                )

            from core.scheduler import schedule_daily_briefing
            await schedule_daily_briefing(
                user_id=user.id,
                telegram_id=user.telegram_id,
                time_str=time_str,
                timezone=tz_name,
            )

            return SkillResult(
                text=f"✅ Daily briefing updated to {time_str} ({tz_name})",
                skill_name=self.name,
            )

        except Exception as exc:
            logger.error("Briefing time change failed: {}", exc)
            return SkillResult(
                text="Couldn't update the briefing time. Try: 'Change briefing to 7:00am'",
                skill_name=self.name,
            )


async def _load_profile(user_id: str) -> str:
    """Load profile context for briefing (when called by scheduler)."""
    try:
        from core.memory_manager import MemoryManager, format_profile
        entries = await db.get_user_profile(user_id)
        return format_profile(entries)
    except Exception:
        return ""


# ── Sub-intent helpers ───────────────────────────────────────────────

def _is_disable_request(msg: str) -> bool:
    patterns = ["turn off briefing", "disable briefing", "stop briefing", "no more briefing"]
    return any(p in msg for p in patterns)


def _is_time_change_request(msg: str) -> bool:
    patterns = ["change briefing", "briefing time", "move briefing", "set briefing"]
    return any(p in msg for p in patterns)
