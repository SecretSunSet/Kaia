"""MakubeX-specific slash commands — shortcuts for his most-used skills."""

from __future__ import annotations

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import get_settings
from core.ai_engine import AIEngine
from database import queries as db
from database.queries import get_or_create_user
from experts.makubex.parser import extract_code_block
from experts.makubex.skills.code_review import CodeReviewSkill
from experts.makubex.skills.learning_coach import LearningCoachSkill
from experts.makubex.skills.proactive import MakubexProactiveSkill
from experts.makubex.skills.project_manager import ProjectManagerSkill
from experts.makubex.skills.security import SecuritySkill
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


async def cmd_makubex_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/makubex_review — review a code snippet pasted after the command."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    raw = (update.message.text or "").strip()
    # Drop the command token (e.g. "/makubex_review" or "/makubex_review@bot")
    _, _, rest = raw.partition(" ")
    rest = rest.strip()
    if not rest:
        await update.message.reply_text(
            "Paste the code after the command. Example:\n"
            "`/makubex_review`\n```python\ndef foo(): ...\n```",
            **_topic_kwargs(update.message),
        )
        return

    await update.message.chat.send_action("typing")
    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        code, lang = extract_code_block(rest)
        if not code:
            code, lang = rest, None
        ai_engine = AIEngine()
        skill = CodeReviewSkill(ai_engine)
        review = await skill.review_code(user.id, code, language=lang)
        text = skill.format_review(review)
        await update.message.reply_text(truncate(text), **_topic_kwargs(update.message))
    except Exception as exc:
        logger.exception("Error in /makubex_review: {}", exc)
        await update.message.reply_text("Couldn't run the review right now.")


async def cmd_makubex_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/makubex_projects — list tracked tech projects."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    await update.message.chat.send_action("typing")
    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        ai_engine = AIEngine()
        skill = ProjectManagerSkill(ai_engine)
        projects = await skill.list_projects(user.id, status="active")
        text = skill.format_projects_list(projects)
        await update.message.reply_text(truncate(text), **_topic_kwargs(update.message))
    except Exception as exc:
        logger.exception("Error in /makubex_projects: {}", exc)
        await update.message.reply_text("Couldn't load your projects right now.")


async def cmd_makubex_learn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/makubex_learn — suggest the next topic to study."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    await update.message.chat.send_action("typing")
    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        ai_engine = AIEngine()
        skill = LearningCoachSkill(ai_engine)
        suggestion = await skill.suggest_next_topic(user.id)
        topic = suggestion.get("topic")
        if not topic:
            text = (
                "🎯 Nothing jumps out as a critical gap right now.\n\n"
                "Tell me what you want to level up on and I'll map a study plan."
            )
        else:
            reason = (
                "it would unblock an active project"
                if suggestion.get("project_driven")
                else "it's the next rung up from where you are"
            )
            options = suggestion.get("options", [])
            extra = ""
            if len(options) > 1:
                extra = "\n\nOther candidates: " + ", ".join(options[1:4])
            text = (
                f"🎯 *Next up:* {topic}\n"
                f"_Why:_ {reason}.{extra}"
            )
        await update.message.reply_text(truncate(text), **_topic_kwargs(update.message))
    except Exception as exc:
        logger.exception("Error in /makubex_learn: {}", exc)
        await update.message.reply_text("Couldn't pick a topic right now.")


async def cmd_makubex_security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/makubex_security [project_name] — audit a tracked project for security gaps."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    raw = (update.message.text or "").strip()
    _, _, project_name = raw.partition(" ")
    project_name = project_name.strip()

    await update.message.chat.send_action("typing")
    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        if not project_name:
            projects = await db.get_tech_projects(user.id, status="active")
            if not projects:
                await update.message.reply_text(
                    "No active projects tracked. Add one first with "
                    "'Add a new project: ...' in /makubex chat.",
                    **_topic_kwargs(update.message),
                )
                return
            project_name = projects[0].name

        ai_engine = AIEngine()
        skill = SecuritySkill(ai_engine)
        text = await skill.audit_project(user.id, project_name=project_name)
        header = f"🔒 *Security audit — {project_name}*\n\n"
        await update.message.reply_text(
            truncate(header + text), **_topic_kwargs(update.message)
        )
    except Exception as exc:
        logger.exception("Error in /makubex_security: {}", exc)
        await update.message.reply_text("Couldn't run the security audit right now.")


async def cmd_makubex_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/makubex_brief — generate the weekly tech brief on demand."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    await update.message.chat.send_action("typing")
    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        ai_engine = AIEngine()
        skill = MakubexProactiveSkill(ai_engine)
        text = await skill.generate_weekly_brief(user.id)
        await update.message.reply_text(truncate(text), **_topic_kwargs(update.message))
    except Exception as exc:
        logger.exception("Error in /makubex_brief: {}", exc)
        await update.message.reply_text("Couldn't generate the brief right now.")
