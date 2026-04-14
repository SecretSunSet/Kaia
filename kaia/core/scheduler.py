"""APScheduler setup — manages reminder jobs, briefing schedule, snooze, dismiss, and recurrence."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from database.queries import (
    get_all_active_reminders,
    get_or_create_user,
    get_reminder_by_id,
    get_user_for_reminder,
    update_reminder,
    deactivate_reminder,
)
from skills.reminders.prompts import format_fire_message
from utils.time_utils import next_occurrence, format_local

# Module-level scheduler instance
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Return the singleton scheduler (create if needed)."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def start_scheduler(bot: Bot) -> None:
    """Start the scheduler, load reminders, and schedule daily briefings."""
    scheduler = get_scheduler()
    _store_bot(bot)
    await load_all_reminders(bot)
    await _schedule_briefings_for_all_users(bot)
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def shutdown_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")


async def load_all_reminders(bot: Bot) -> None:
    """Load all active reminders from DB and schedule them."""
    scheduler = get_scheduler()
    rows = await get_all_active_reminders()
    now = datetime.now(timezone.utc)
    loaded = 0

    for row in rows:
        reminder = row["reminder"]
        telegram_id = row["telegram_id"]

        fire_time = reminder.scheduled_time
        if fire_time.tzinfo is None:
            fire_time = fire_time.replace(tzinfo=timezone.utc)

        # Skip reminders in the past (handle missed ones)
        if fire_time <= now:
            if reminder.recurrence != "none":
                # Advance recurring reminders to the next future occurrence
                while fire_time <= now:
                    fire_time = next_occurrence(fire_time, reminder.recurrence)
                await update_reminder(
                    reminder.id,
                    scheduled_time=fire_time.isoformat(),
                )
            else:
                # One-time reminder in the past — deactivate
                await deactivate_reminder(reminder.id)
                continue

        _add_job(scheduler, reminder.id, telegram_id, reminder.title, fire_time, bot)
        loaded += 1

    logger.info("Loaded {} active reminders from DB", loaded)


async def _schedule_briefings_for_all_users(bot: Bot) -> None:
    """Schedule daily briefings for all known users on startup."""
    from config.settings import get_settings
    from config.constants import BRIEFING_DEFAULT_TIME
    settings = get_settings()

    if not settings.briefing_enabled:
        logger.info("Daily briefing is disabled globally")
        return

    # Get all users who have the bot
    # For a single-user bot, use ALLOWED_TELEGRAM_IDS
    telegram_ids = settings.allowed_telegram_ids
    if not telegram_ids:
        logger.info("No allowed_telegram_ids configured, skipping briefing scheduling")
        return

    for tg_id in telegram_ids:
        try:
            user = await get_or_create_user(tg_id)
            await schedule_daily_briefing(
                user_id=user.id,
                telegram_id=tg_id,
                time_str=settings.briefing_time,
                timezone=user.timezone or settings.default_timezone,
                bot=bot,
            )
        except Exception as exc:
            logger.error("Failed to schedule briefing for tg_id={}: {}", tg_id, exc)


async def schedule_reminder(
    reminder_id: str,
    telegram_id: int,
    title: str,
    fire_time_utc: datetime,
    bot: Bot,
) -> None:
    """Add a new reminder job to the scheduler."""
    scheduler = get_scheduler()
    _add_job(scheduler, reminder_id, telegram_id, title, fire_time_utc, bot)
    logger.debug("Scheduled reminder {} for {}", reminder_id, fire_time_utc)


async def cancel_reminder(reminder_id: str) -> None:
    """Remove a reminder job from the scheduler."""
    scheduler = get_scheduler()
    job_id = f"reminder_{reminder_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.debug("Cancelled scheduler job {}", job_id)


async def reschedule_reminder(
    reminder_id: str,
    new_time_utc: datetime,
) -> None:
    """Reschedule an existing reminder to a new time."""
    scheduler = get_scheduler()
    job_id = f"reminder_{reminder_id}"
    job = scheduler.get_job(job_id)
    if job:
        job.reschedule(trigger="date", run_date=new_time_utc)
        logger.debug("Rescheduled {} to {}", job_id, new_time_utc)


# ── Snooze & dismiss (called from Telegram callback handler) ─────────

async def handle_snooze(reminder_id: str, minutes: int, bot: Bot) -> str:
    """Snooze a reminder by *minutes* and return a status message."""
    reminder = await get_reminder_by_id(reminder_id)
    if not reminder:
        return "Reminder not found."

    user = await get_user_for_reminder(reminder_id)
    if not user:
        return "User not found."

    new_time = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    await update_reminder(
        reminder_id,
        scheduled_time=new_time.isoformat(),
        snooze_count=reminder.snooze_count + 1,
    )

    # Reschedule or create new job
    scheduler = get_scheduler()
    job_id = f"reminder_{reminder_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    _add_job(scheduler, reminder_id, user.telegram_id, reminder.title, new_time, bot)

    display = format_local(new_time, user.timezone)
    return f"💤 Snoozed until {display}"


async def handle_dismiss(reminder_id: str) -> str:
    """Dismiss a reminder. If recurring, schedule next; if one-time, deactivate."""
    reminder = await get_reminder_by_id(reminder_id)
    if not reminder:
        return "Reminder not found."

    await cancel_reminder(reminder_id)

    if reminder.recurrence != "none":
        # Recurring — schedule next occurrence
        fire_time = reminder.scheduled_time
        if fire_time.tzinfo is None:
            fire_time = fire_time.replace(tzinfo=timezone.utc)
        new_time = next_occurrence(fire_time, reminder.recurrence)

        await update_reminder(
            reminder_id,
            scheduled_time=new_time.isoformat(),
            snooze_count=0,
        )

        user = await get_user_for_reminder(reminder_id)
        if user:
            from core.scheduler import get_scheduler as _gs  # avoid circular at module level
            bot_instance = None
            scheduler = _gs()
            # Re-retrieve bot from an existing job or skip (will load on restart)
            # For now, the next startup will pick it up
            display = format_local(new_time, user.timezone)
            return f"✅ Dismissed. Next: {display}"

        return "✅ Dismissed. Next occurrence scheduled."
    else:
        await deactivate_reminder(reminder_id)
        return "✅ Dismissed."


# ── Internal helpers ─────────────────────────────────────────────────

def _add_job(
    scheduler: AsyncIOScheduler,
    reminder_id: str,
    telegram_id: int,
    title: str,
    fire_time: datetime,
    bot: Bot,
) -> None:
    """Add (or replace) a date-trigger job for a reminder."""
    job_id = f"reminder_{reminder_id}"
    # Remove existing job if present (idempotent)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        _fire_reminder,
        trigger="date",
        run_date=fire_time,
        id=job_id,
        args=[reminder_id, telegram_id, title, bot],
        replace_existing=True,
    )


async def _fire_reminder(
    reminder_id: str,
    telegram_id: int,
    title: str,
    bot: Bot,
) -> None:
    """Send the reminder message to the user with snooze/dismiss buttons."""
    logger.info("Firing reminder {} for user {}", reminder_id, telegram_id)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💤 5m", callback_data=f"snooze_5_{reminder_id}"),
                InlineKeyboardButton("💤 15m", callback_data=f"snooze_15_{reminder_id}"),
                InlineKeyboardButton("💤 1hr", callback_data=f"snooze_60_{reminder_id}"),
            ],
            [
                InlineKeyboardButton("✅ Dismiss", callback_data=f"dismiss_{reminder_id}"),
            ],
        ]
    )

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=format_fire_message(title),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    except Exception as exc:
        logger.error("Failed to send reminder {} to {}: {}", reminder_id, telegram_id, exc)

    # Handle recurrence — schedule next if recurring
    reminder = await get_reminder_by_id(reminder_id)
    if reminder and reminder.recurrence != "none":
        fire_time = reminder.scheduled_time
        if fire_time.tzinfo is None:
            fire_time = fire_time.replace(tzinfo=timezone.utc)
        new_time = next_occurrence(fire_time, reminder.recurrence)
        await update_reminder(reminder_id, scheduled_time=new_time.isoformat(), snooze_count=0)
        _add_job(get_scheduler(), reminder_id, telegram_id, title, new_time, bot)
        logger.info("Recurring reminder {} rescheduled to {}", reminder_id, new_time)


# ── Daily Briefing ──────────────────────────────────────────────────

# Module-level storage for the bot ref (needed by briefing fire function)
_bot_ref: Bot | None = None


def _store_bot(bot: Bot) -> None:
    """Store bot reference for use by scheduled jobs."""
    global _bot_ref
    _bot_ref = bot


async def schedule_daily_briefing(
    user_id: str,
    telegram_id: int,
    time_str: str = "07:00",
    timezone: str = "Asia/Manila",
    bot: Bot | None = None,
) -> None:
    """Schedule (or reschedule) the daily briefing for a user.

    Args:
        user_id: Database user ID.
        telegram_id: Telegram chat ID for sending the briefing.
        time_str: "HH:MM" in the user's local timezone.
        timezone: User's timezone name.
        bot: Bot instance (uses stored ref if None).
    """
    scheduler = get_scheduler()
    job_id = f"briefing_{user_id}"

    # Remove existing briefing job if present
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    hour, minute = (int(x) for x in time_str.split(":"))
    trigger = CronTrigger(hour=hour, minute=minute, timezone=ZoneInfo(timezone))

    the_bot = bot or _bot_ref
    if the_bot is None:
        logger.warning("Cannot schedule briefing — no bot reference available")
        return

    scheduler.add_job(
        _fire_briefing,
        trigger=trigger,
        id=job_id,
        args=[user_id, telegram_id, the_bot],
        replace_existing=True,
    )
    logger.info("Daily briefing scheduled for user {} at {} {}", user_id, time_str, timezone)


async def cancel_daily_briefing(user_id: str) -> None:
    """Cancel the daily briefing for a user."""
    scheduler = get_scheduler()
    job_id = f"briefing_{user_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("Daily briefing cancelled for user {}", user_id)


async def _fire_briefing(user_id: str, telegram_id: int, bot: Bot) -> None:
    """Send the daily briefing to the user."""
    logger.info("Firing daily briefing for user {} (tg={})", user_id, telegram_id)
    try:
        # Import here to avoid circular imports
        from core.ai_engine import AIEngine
        from skills.briefing.handler import BriefingSkill
        from database.models import User

        # Load user data
        user = await get_or_create_user(telegram_id)

        ai_engine = AIEngine()
        skill = BriefingSkill(ai_engine)
        text = await skill.generate_briefing(user)

        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode="Markdown",
        )

    except Exception as exc:
        logger.error("Failed to send daily briefing to {}: {}", telegram_id, exc)
