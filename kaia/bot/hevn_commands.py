"""Hevn-specific slash commands — shortcuts for her most-used skills."""

from __future__ import annotations

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import get_settings
from database.queries import get_or_create_user
from experts.hevn.skills.bills_tracker import BillsTrackerSkill
from experts.hevn.skills.goals_manager import GoalsManagerSkill
from experts.hevn.skills.health_assessment import FinancialHealthSkill
from experts.hevn.skills.proactive import ProactiveAlertsSkill
from utils.formatters import truncate


def _is_allowed(telegram_id: int) -> bool:
    settings = get_settings()
    if not settings.allowed_telegram_ids:
        return True
    return telegram_id in settings.allowed_telegram_ids


def _topic_kwargs(message) -> dict:
    kwargs: dict = {"parse_mode": "Markdown"}
    topic_id = getattr(message, "message_thread_id", None)
    if topic_id is not None and getattr(message.chat, "is_forum", False):
        kwargs["message_thread_id"] = topic_id
    return kwargs


async def cmd_hevn_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/hevn_health — financial health score on demand."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    await update.message.chat.send_action("typing")
    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        currency = user.currency or "PHP"
        skill = FinancialHealthSkill()
        assessment = await skill.assess(user.id, currency)
        text = skill.format_health_report(assessment, currency)
        await update.message.reply_text(truncate(text), **_topic_kwargs(update.message))
    except Exception as exc:
        logger.exception("Error in /hevn_health: {}", exc)
        await update.message.reply_text("Couldn't generate your health report right now.")


async def cmd_hevn_goals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/hevn_goals — formatted list of all active goals."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    await update.message.chat.send_action("typing")
    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        currency = user.currency or "PHP"
        skill = GoalsManagerSkill()
        text = await skill.format_goals_overview(user.id, currency)
        await update.message.reply_text(truncate(text), **_topic_kwargs(update.message))
    except Exception as exc:
        logger.exception("Error in /hevn_goals: {}", exc)
        await update.message.reply_text("Couldn't load your goals right now.")


async def cmd_hevn_bills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/hevn_bills — upcoming bills in the next 7 days."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    await update.message.chat.send_action("typing")
    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        currency = user.currency or "PHP"
        skill = BillsTrackerSkill()
        upcoming = await skill.get_upcoming(user.id, days=7)
        if upcoming:
            text = skill.format_upcoming(upcoming, currency)
        else:
            bills = await skill.list_bills(user.id)
            text = skill.format_bills_list(bills, currency)
        await update.message.reply_text(truncate(text), **_topic_kwargs(update.message))
    except Exception as exc:
        logger.exception("Error in /hevn_bills: {}", exc)
        await update.message.reply_text("Couldn't load your bills right now.")


async def cmd_hevn_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/hevn_digest — generate the weekly financial digest on demand."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    await update.message.chat.send_action("typing")
    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        currency = user.currency or "PHP"
        skill = ProactiveAlertsSkill()
        text = await skill.generate_weekly_digest(user.id, currency)
        await update.message.reply_text(truncate(text), **_topic_kwargs(update.message))
    except Exception as exc:
        logger.exception("Error in /hevn_digest: {}", exc)
        await update.message.reply_text("Couldn't generate your digest right now.")
