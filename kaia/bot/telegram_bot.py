"""Main Telegram bot entry point — message, voice, callback handlers, scheduler."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from uuid import UUID

from loguru import logger
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config.settings import get_settings
from config.constants import (
    CHANNEL_GENERAL,
)
from core.ai_engine import AIEngine
from core.memory_manager import MemoryManager
from core.skill_router import SkillRouter
from core.channel_manager import ChannelManager
from core.channel_memory import ChannelMemoryManager
from core.expert_detector import clear_suggestion_history
from core.forum_manager import ForumManager, ForumSetupError
from core.scheduler import start_scheduler, shutdown_scheduler, handle_snooze, handle_dismiss
from agent_runtime.base_agent import BaseAgent
from bus import Bus, Envelope, PostgresBusTransport, Visibility
from database.queries import (
    get_or_create_user,
    get_channel_profile,
    get_user_by_id,
)
from bot.commands import cmd_status_extended, cmd_export, cmd_reset, handle_reset_confirmation
from bot.hevn_commands import (
    cmd_hevn_bills,
    cmd_hevn_digest,
    cmd_hevn_goals,
    cmd_hevn_health,
)
from bot.makubex_commands import (
    cmd_makubex_brief,
    cmd_makubex_learn,
    cmd_makubex_projects,
    cmd_makubex_review,
    cmd_makubex_security,
)
from bot.middleware import check_rate_limit, track_ai_usage
from experts import get_expert
from experts.placeholder import PlaceholderExpert
from concierge import Concierge, welcome_text
from skills.briefing.handler import BriefingSkill
from skills.reminders.handler import set_bot
from utils.formatters import truncate
from utils.voice_stt import transcribe_voice
from utils.voice_tts import text_to_speech, safe_delete, cleanup_old_files


# ── Globals (initialised in main) ────────────────────────────────────
settings = get_settings()
ai_engine = AIEngine()
memory_mgr = MemoryManager(ai_engine)
skill_router = SkillRouter(ai_engine)
channel_mgr = ChannelManager()
channel_mem = ChannelMemoryManager()
forum_mgr = ForumManager()
concierge = Concierge(ai_engine, skill_router=skill_router, memory_mgr=memory_mgr)

# R-3 bus globals
_bus: "Bus | None" = None
_user_visible_task: "asyncio.Task | None" = None
_AGENT_DISPLAY_CACHE: dict[str, tuple[str, str]] = {}


# ── Helpers ──────────────────────────────────────────────────────────

def _is_allowed(telegram_id: int) -> bool:
    """Check whether this user is authorised to use the bot."""
    if not settings.allowed_telegram_ids:
        return True
    return telegram_id in settings.allowed_telegram_ids


def _should_reply_with_voice(profile_context: str) -> bool:
    """Check if the user wants voice replies based on their profile."""
    low = profile_context.lower()
    return "voice_replies: true" in low or "voice replies: enabled" in low


def _forum_context(message) -> tuple[bool, int | None]:
    """Return (is_forum, topic_id) for a message. Safe against missing attrs."""
    if not settings.forum_mode_enabled:
        return False, None
    chat = message.chat
    is_forum = bool(getattr(chat, "is_forum", False))
    topic_id = getattr(message, "message_thread_id", None)
    return is_forum, topic_id


# ── Command handlers ─────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — greet user and ensure they exist in DB."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        await update.message.reply_text("Sorry, this bot is private.")
        return

    await get_or_create_user(tg_user.id, tg_user.username)
    await update.message.reply_text(welcome_text(), parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help — full feature guide."""
    if update.message is None:
        return
    await update.message.reply_text(
        "📖 *What I can do:*\n\n"
        "💬 *Chat* — Ask me anything. I use what I know about you for better answers.\n\n"
        "🧠 *Memory* — I remember things automatically. You can also:\n"
        '  • "Remember that I prefer short answers"\n'
        '  • "What do you know about me?"\n\n'
        "⏰ *Reminders:*\n"
        '  • "Remind me to take meds at 8pm daily"\n'
        '  • "What reminders do I have?"\n'
        '  • "Cancel my gym reminder"\n\n'
        "💰 *Budget:*\n"
        '  • "Spent ₱500 on groceries"\n'
        '  • "How much did I spend this month?"\n'
        '  • "Set food budget to ₱5,000"\n\n'
        "🌅 *Briefing:*\n"
        "  • /briefing — Get your daily summary now\n"
        '  • "Change briefing to 6:30am"\n\n'
        "🌐 *Search:*\n"
        '  • "Search for best restaurants in Laguna"\n'
        '  • "What\'s the weather?"\n\n'
        "🎙️ *Voice* — Send a voice message and I'll transcribe and respond!\n\n"
        "👥 *Expert Channels:*\n"
        "/team — View your full AI team\n"
        "/hevn — Financial advisor\n"
        "/kazuki — Investment manager\n"
        "/akabane — Trading strategist\n"
        "/makubex — Tech lead\n"
        "/exit — Return to general KAIA chat\n\n"
        "💰 *Hevn shortcuts:*\n"
        "/hevn_health — Financial health score\n"
        "/hevn_goals — Show all goals\n"
        "/hevn_bills — Upcoming bills\n"
        "/hevn_digest — Weekly digest on demand\n\n"
        "🔧 *MakubeX shortcuts:*\n"
        "/makubex_review — Review a code snippet\n"
        "/makubex_projects — List tracked tech projects\n"
        "/makubex_learn — Suggest what to learn next\n"
        "/makubex_security — Security audit a tracked project\n"
        "/makubex_brief — Weekly tech brief on demand\n\n"
        "⚙️ *Commands:*\n"
        "/start — Welcome message\n"
        "/help — This help text\n"
        "/status — Bot status and stats\n"
        "/briefing — Daily briefing\n"
        "/export — Export your data\n"
        "/reset — ⚠️ Delete all your data",
        parse_mode="Markdown",
    )


async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /briefing — trigger an on-demand daily briefing."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    await update.message.chat.send_action("typing")

    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        profile_context = await memory_mgr.load_profile_context(user.id)

        briefing_skill = BriefingSkill(ai_engine)
        text = await briefing_skill.generate_briefing(user, profile_context)
        await update.message.reply_text(truncate(text), parse_mode="Markdown")

    except Exception as exc:
        logger.exception("Error generating briefing for {}: {}", tg_user.id, exc)
        await update.message.reply_text("Something went wrong generating your briefing.")


# ── Channel / Expert command handlers ───────────────────────────────

async def cmd_channel_switch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch to an expert channel (/hevn, /kazuki, /akabane, /makubex)."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    # Extract channel_id from the command (e.g., "/hevn" → "hevn")
    command_text = (update.message.text or "").strip().lstrip("/").split()[0].lower()
    # Strip @botname suffix (e.g. "/hevn@kaia_bot")
    channel_id = command_text.split("@", 1)[0]

    # Forum mode: redirect user to the expert's topic instead of switching.
    is_forum, _ = _forum_context(update.message)
    if is_forum:
        chat_id = update.message.chat_id
        topic_id = await forum_mgr.get_topic_for_channel(chat_id, channel_id)
        if topic_id is not None:
            channel = await channel_mgr.get_channel_info(channel_id)
            name = channel.character_name if channel else channel_id.title()
            emoji = channel.emoji if channel else ""
            await update.message.reply_text(
                f"{emoji} {name} has her/his own topic thread in this group — "
                f"tap it in the topics list to chat directly.",
            )
        else:
            await update.message.reply_text(
                "Expert topics aren't set up in this group yet. Run /setup_forum first."
            )
        return

    await update.message.chat.send_action("typing")

    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)

        # Switch channel
        channel = await channel_mgr.switch_channel(user.id, channel_id)

        # Clear expert suggestion history so we don't nag after switching
        clear_suggestion_history(user.id)

        # Check if first visit
        if await channel_mgr.is_first_visit(user.id, channel_id):
            # Generate onboarding
            combined_context = await channel_mem.load_combined_context(
                user.id, channel_id
            )
            expert = get_expert(channel_id, ai_engine) or PlaceholderExpert(ai_engine)
            onboarding = await expert.generate_onboarding(user, channel, combined_context)
            footer = expert.format_response_footer(channel)

            # Save onboarding to channel history
            await expert.save_messages(
                user.id, channel_id, f"/{channel_id}", onboarding
            )

            await update.message.reply_text(
                truncate(f"{onboarding}{footer}"), parse_mode="Markdown"
            )
        else:
            # Returning visit — direct greeting
            await update.message.reply_text(
                f"{channel.emoji} *{channel.character_name}* here. What do you need?\n\n"
                f"_{channel.role}_ | /exit to return to KAIA",
                parse_mode="Markdown",
            )

    except ValueError as exc:
        await update.message.reply_text(f"Channel not found: {exc}")
    except Exception as exc:
        logger.exception("Error switching to channel {}: {}", channel_id, exc)
        await update.message.reply_text("Something went wrong switching channels.")


async def cmd_exit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to general KAIA channel."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    # In forum mode there is no persistent channel state to exit — tap General.
    is_forum, _ = _forum_context(update.message)
    if is_forum:
        await update.message.reply_text(
            "💬 In this group each expert has their own topic. "
            "Tap the General topic to talk to KAIA."
        )
        return

    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        await channel_mgr.exit_channel(user.id)
        await update.message.reply_text(
            "👋 Back to KAIA. Your team is always here — just call their name!"
        )
    except Exception as exc:
        logger.exception("Error exiting channel: {}", exc)
        await update.message.reply_text("Something went wrong.")


async def cmd_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the team roster with status."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    is_forum, _ = _forum_context(update.message)
    if is_forum:
        await update.message.reply_text(
            "🏆 *KAIA Team Roster*\n\n"
            "👑 *KAIA* — Team Lead\n"
            "   💬 General topic (this one)\n\n"
            "💰 *Hevn* — Financial Advisor\n"
            "   📍 Tap her topic thread above\n\n"
            "📈 *Kazuki* — Investment Manager\n"
            "   📍 Tap his topic thread above\n\n"
            "⚔️ *Akabane* — Trading Strategist\n"
            "   📍 Tap his topic thread above\n\n"
            "🔧 *MakubeX* — Tech Lead\n"
            "   📍 Tap his topic thread above\n\n"
            "Each expert has their own thread — tap to chat directly!",
            parse_mode="Markdown",
        )
        return

    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        channels = await channel_mgr.get_all_channels()

        lines = ["🏆 *KAIA Team Roster*\n"]

        for ch in channels:
            if ch.channel_id == CHANNEL_GENERAL:
                lines.append(
                    f"{ch.emoji} *{ch.character_name}* — {ch.role} (always active)\n"
                    f"   General assistant, reminders, budget, briefing, web search\n"
                )
            else:
                # Get knowledge score if user has talked to this expert
                entries = await get_channel_profile(user.id, ch.channel_id)
                score_info = channel_mem.get_knowledge_score(ch.channel_id, entries)

                if entries:
                    known_summary = ", ".join(
                        k.replace("_", " ") for k in score_info["known"][:3]
                    )
                    knowledge_line = (
                        f"   📊 Knowledge: {score_info['score']}%"
                        + (f" — knows your {known_summary}" if known_summary else "")
                    )
                else:
                    knowledge_line = "   📊 Knowledge: not started yet"

                lines.append(
                    f"{ch.emoji} *{ch.character_name}* — {ch.role} (/{ch.channel_id})\n"
                    f"   {ch.personality[:80]}...\n"
                    f"{knowledge_line}\n"
                )

        lines.append("Type any command to connect with a team member!")

        await update.message.reply_text(
            "\n".join(lines), parse_mode="Markdown"
        )

    except Exception as exc:
        logger.exception("Error showing team roster: {}", exc)
        await update.message.reply_text("Something went wrong loading the team roster.")


# ── Forum setup ─────────────────────────────────────────────────────

async def cmd_setup_forum(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create expert forum topics in this group (one-time setup)."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    chat = update.message.chat
    if chat.type == "private":
        await update.message.reply_text(
            "This command only works in group chats with Topics enabled."
        )
        return

    if not getattr(chat, "is_forum", False):
        await update.message.reply_text(
            "📋 Topics aren't enabled in this group yet.\n\n"
            "Turn them on: *Group Settings → Topics → Toggle ON*\n"
            "Then run /setup_forum again.",
            parse_mode="Markdown",
        )
        return

    if await forum_mgr.is_forum_setup(chat.id):
        await update.message.reply_text("✅ Expert topics are already set up here.")
        return

    await update.message.reply_text("🔧 Setting up expert topics…")

    try:
        mappings = await forum_mgr.setup_forum_topics(context.bot, chat.id)
    except ForumSetupError as exc:
        if exc.is_permission_error:
            await update.message.reply_text(
                "❌ I need admin rights with *Manage Topics* permission.\n"
                "Open *Group Settings → Admins → KAIA* and enable *Manage Topics*, "
                "then run /setup_forum again.",
                parse_mode="Markdown",
            )
        else:
            logger.exception("Forum setup failed: {}", exc)
            await update.message.reply_text(
                f"Couldn't create topics: {exc}"
            )
        return

    await update.message.reply_text(
        f"✅ Team is ready! Created {len(mappings)} expert topics.\n\n"
        "💰 Hevn — Financial Advisor\n"
        "📈 Kazuki — Investment Manager\n"
        "⚔️ Akabane — Trading Strategist\n"
        "🔧 MakubeX — Tech Lead\n\n"
        "Tap any topic to start chatting with that expert!"
    )


# ── Main message handler ────────────────────────────────────────────

async def _handle_expert_turn(
    update: Update,
    *,
    user,
    text: str,
    channel_id: str,
    topic_id: int | None,
) -> None:
    """Route a message to an expert and reply in the correct topic/DM."""
    channel = await channel_mgr.get_channel_info(channel_id)
    if channel is None:
        await update.message.reply_text(
            f"Expert '{channel_id}' isn't configured. Ask the bot owner to check setup."
        )
        return

    expert = get_expert(channel_id, ai_engine) or PlaceholderExpert(ai_engine)
    result = await expert.handle(user=user, message=text, channel=channel)

    reply_kwargs: dict = {"parse_mode": "Markdown"}
    if topic_id is not None:
        reply_kwargs["message_thread_id"] = topic_id

    await update.message.reply_text(truncate(result.text), **reply_kwargs)

    if result.ai_response:
        track_ai_usage(
            result.ai_response.input_tokens,
            result.ai_response.output_tokens,
            result.ai_response.provider,
        )
        logger.info(
            "msg handled | user={} channel={} topic={} provider={} tokens={}+{}",
            update.effective_user.id,
            channel_id,
            topic_id,
            result.ai_response.provider,
            result.ai_response.input_tokens,
            result.ai_response.output_tokens,
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process any text message through the skill pipeline."""
    if update.effective_user is None or update.message is None:
        return

    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    # Check for pending reset confirmation
    if await handle_reset_confirmation(update):
        return

    # Rate limiting
    if not check_rate_limit(tg_user.id):
        await update.message.reply_text("Slow down! I need a moment to catch up. 😅")
        return

    # Show typing indicator while processing
    await update.message.chat.send_action("typing")

    try:
        # 1. Get or create user
        user = await get_or_create_user(tg_user.id, tg_user.username)

        is_forum, topic_id = _forum_context(update.message)
        chat_type = update.message.chat.type

        # ── Forum mode: topic IS the channel ─────────────────────────
        if is_forum:
            chat_id = update.message.chat_id
            channel_id = await forum_mgr.get_channel_for_topic(chat_id, topic_id)

            if channel_id is None:
                # Unknown topic — ignore silently so bot isn't noisy in random threads
                return

            if channel_id != CHANNEL_GENERAL:
                await _handle_expert_turn(
                    update,
                    user=user,
                    text=text,
                    channel_id=channel_id,
                    topic_id=topic_id,
                )
                return
            # else: fall through to general KAIA flow, replying in this topic
        else:
            # ── DM mode: check persistent channel state ──────────────
            if chat_type != "private":
                # Regular (non-forum) group — ignore unless explicitly mentioned.
                return

            active_channel = await channel_mgr.get_active_channel(user.id)
            if active_channel != CHANNEL_GENERAL:
                channel = await channel_mgr.get_channel_info(active_channel)
                if channel is None:
                    await channel_mgr.exit_channel(user.id)
                else:
                    await _handle_expert_turn(
                        update,
                        user=user,
                        text=text,
                        channel_id=active_channel,
                        topic_id=None,
                    )
                    return

        # ── General KAIA flow (DM general OR forum General topic) ────
        # Orchestration lives in the concierge (R-2). The bot only renders.

        result = await concierge.handle_general_turn(
            user, text, suggest_experts=True
        )

        reply_kwargs: dict = {"parse_mode": "Markdown"}
        if is_forum and topic_id is not None:
            reply_kwargs["message_thread_id"] = topic_id

        await update.message.reply_text(truncate(result.text), **reply_kwargs)

        # Suggest expert (text path only — preserves pre-R-2 behavior).
        if result.suggestion:
            await update.message.reply_text(
                f"💡 _{result.suggestion}_",
                **reply_kwargs,
            )

        if result.ai_response:
            track_ai_usage(
                result.ai_response.input_tokens,
                result.ai_response.output_tokens,
                result.ai_response.provider,
            )
            logger.info(
                "msg handled | user={} skill={} provider={} tokens={}+{}",
                tg_user.id,
                result.skill_name,
                result.ai_response.provider,
                result.ai_response.input_tokens,
                result.ai_response.output_tokens,
            )

    except Exception as exc:
        logger.exception("Error handling message from {}: {}", tg_user.id, exc)
        await update.message.reply_text(
            "Something went wrong on my end. Please try again in a moment."
        )


# ── Voice message handler ──────────────────────────────────────────

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages — transcribe and process through skill pipeline."""
    if update.effective_user is None or update.message is None:
        return

    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    voice = update.message.voice or update.message.audio
    if voice is None:
        return

    # Rate limiting
    if not check_rate_limit(tg_user.id):
        await update.message.reply_text("Slow down! I need a moment to catch up. 😅")
        return

    await update.message.chat.send_action("typing")

    # Download the voice file
    voice_path = None
    tts_path = None
    try:
        file = await voice.get_file()
        voice_path = os.path.join(tempfile.gettempdir(), f"kaia_voice_{tg_user.id}_{voice.file_id}.ogg")
        await file.download_to_drive(voice_path)

        # Transcribe
        transcribed = await transcribe_voice(voice_path)
        if transcribed is None:
            await update.message.reply_text(
                "Sorry, I couldn't understand that voice message. "
                "Try again or type your message."
            )
            return

        is_forum, topic_id = _forum_context(update.message)
        chat_type = update.message.chat.type

        reply_kwargs: dict = {"parse_mode": "Markdown"}
        if is_forum and topic_id is not None:
            reply_kwargs["message_thread_id"] = topic_id

        # Show what was transcribed (in the same topic if applicable)
        await update.message.reply_text(f"🎙️ _I heard:_ {transcribed}", **reply_kwargs)

        # Process through the pipeline
        user = await get_or_create_user(tg_user.id, tg_user.username)

        # Decide channel: forum mode → topic, DM → persistent state, other → ignore
        channel_id: str
        if is_forum:
            chat_id = update.message.chat_id
            mapped = await forum_mgr.get_channel_for_topic(chat_id, topic_id)
            if mapped is None:
                return
            channel_id = mapped
        else:
            if chat_type != "private":
                return
            channel_id = await channel_mgr.get_active_channel(user.id)

        if channel_id != CHANNEL_GENERAL:
            await _handle_expert_turn(
                update,
                user=user,
                text=transcribed,
                channel_id=channel_id,
                topic_id=topic_id if is_forum else None,
            )
            return

        # General KAIA flow — orchestration via concierge (R-2).
        # suggest_experts=False: the voice path never ran the stateful
        # expert detector pre-R-2; that divergence is preserved.
        result = await concierge.handle_general_turn(
            user, transcribed, suggest_experts=False
        )

        # Send text response (in the same topic if applicable)
        await update.message.reply_text(truncate(result.text), **reply_kwargs)

        # Optionally reply with voice — keyed off the same profile_context
        # the turn was routed with (single profile load).
        if _should_reply_with_voice(result.profile_context):
            tts_path = await text_to_speech(result.text, voice=settings.tts_voice)
            if tts_path:
                voice_kwargs: dict = {}
                if is_forum and topic_id is not None:
                    voice_kwargs["message_thread_id"] = topic_id
                with open(tts_path, "rb") as audio:
                    await update.message.reply_voice(voice=audio, **voice_kwargs)

        # Voice path keeps no "msg handled" log — pre-R-2 behavior (see handle_message).
        if result.ai_response:
            track_ai_usage(
                result.ai_response.input_tokens,
                result.ai_response.output_tokens,
                result.ai_response.provider,
            )

    except Exception as exc:
        logger.exception("Error handling voice from {}: {}", tg_user.id, exc)
        await update.message.reply_text(
            "Something went wrong processing your voice message. Try typing instead."
        )
    finally:
        # Cleanup temp files
        if voice_path:
            safe_delete(voice_path)
        if tts_path:
            safe_delete(tts_path)


# ── Callback query handler (snooze/dismiss buttons) ─────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process inline button presses from reminder messages."""
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    data = query.data or ""

    try:
        if data.startswith("snooze_"):
            parts = data.split("_", 2)
            minutes = int(parts[1])
            reminder_id = parts[2]
            result_text = await handle_snooze(reminder_id, minutes, context.bot)
            await query.edit_message_text(result_text, parse_mode="Markdown")

        elif data.startswith("dismiss_"):
            reminder_id = data.split("_", 1)[1]
            result_text = await handle_dismiss(reminder_id)
            await query.edit_message_text(result_text, parse_mode="Markdown")

        else:
            logger.warning("Unknown callback data: {}", data)

    except Exception as exc:
        logger.exception("Error handling callback {}: {}", data, exc)
        await query.edit_message_text("Something went wrong processing that action.")


# ── Error handler ────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler for uncaught exceptions."""
    logger.error("Telegram error: {}", context.error, exc_info=context.error)
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply_text(
                "Something went wrong on my end. Try again in a moment! 🔧"
            )
        except Exception:
            pass  # Can't even send error message


# ── Post-init: start scheduler ───────────────────────────────────────

async def post_init(application: Application) -> None:
    """Called after the Application is initialised — start bus, scheduler, cleanup."""
    bot = application.bot
    set_bot(bot)

    # R-3: start the bus FIRST — fail fast if Postgres is unreachable.
    global _bus, _user_visible_task
    if not settings.database_url:
        raise RuntimeError(
            "R-3: DATABASE_URL is not set — bus cannot start. "
            "Set it in /opt/kaia/app/kaia/.env (Supabase → Project Settings → "
            "Database → Connection String) and restart."
        )
    transport = PostgresBusTransport(settings.database_url)
    await transport.start()
    _bus = Bus(transport=transport, default_timeout=settings.r3_peer_call_timeout_seconds)
    BaseAgent.set_bus(_bus)
    await _bus.start()

    _user_visible_task = asyncio.create_task(
        _relay_user_visible_envelopes(bot), name="bus-user-visible-relay"
    )

    # ── existing R-1/R-2 post_init body — preserve unchanged ──
    await start_scheduler(bot)
    cleanup_old_files()  # Clean up any stale TTS files from previous runs
    logger.info("Post-init complete: scheduler started, bus running, relay active")


async def post_shutdown(application: Application) -> None:
    """Called when the Application shuts down."""
    global _bus, _user_visible_task
    # R-3: cancel relay first, then stop the bus, then the existing scheduler.
    if _user_visible_task is not None:
        _user_visible_task.cancel()
        try:
            await _user_visible_task
        except asyncio.CancelledError:
            pass
        _user_visible_task = None
    if _bus is not None:
        await _bus.shutdown()
        tx = _bus._tx
        if hasattr(tx, "shutdown"):
            await tx.shutdown()
        _bus = None
    # ── existing R-1/R-2 post_shutdown body ──
    shutdown_scheduler()


# ── R-3: user-visible envelope relay ──────────────────────────────


async def _agent_display(agent_id: str) -> tuple[str, str]:
    """Return (emoji, character_name) for an agent_id. Cached.

    Reads from the `channels` table (populated by migration 002 — covers
    hevn, kazuki, akabane, makubex). Unknown agent IDs fall back to a
    generic 🤖 emoji and title-cased agent_id."""
    if agent_id in _AGENT_DISPLAY_CACHE:
        return _AGENT_DISPLAY_CACHE[agent_id]
    info = await channel_mgr.get_channel_info(agent_id)
    if info is None:
        display = ("🤖", agent_id.title())
    else:
        display = (info.emoji or "🤖", info.character_name or agent_id.title())
    _AGENT_DISPLAY_CACHE[agent_id] = display
    return display


def _format_reply_payload(payload: dict) -> str:
    """Pretty-print a peer reply payload as Markdown bullets.

    Handles structured fields like `caveats: list[str]` specially; falls
    back to a generic key/value bullet for other types."""
    lines = []
    for key, val in payload.items():
        if key == "caveats" and isinstance(val, list):
            lines.append(f"- *Caveats:* {'; '.join(val)}")
        elif isinstance(val, (dict, list)):
            lines.append(f"- *{key.replace('_', ' ').title()}:* {json.dumps(val)}")
        else:
            label = key.replace("_", " ").title()
            lines.append(f"- *{label}:* {val}")
    return "\n".join(lines)


async def _render_envelope_to_user(bot, env: Envelope) -> None:
    """Render one user-visible envelope as an attribution message in the
    originating user's private chat with the bot."""
    user = await get_user_by_id(env.user_id)
    if user is None:
        logger.warning("user_visible relay: no user for envelope {}", env.envelope_id)
        return
    from_emoji, from_name = await _agent_display(env.from_agent)
    to_emoji, to_name = await _agent_display(env.to_agent)
    if env.kind == "request":
        body = env.payload.get("context") or env.payload.get("question") or json.dumps(env.payload)
        text = f"{from_emoji} *{from_name}* → {to_emoji} *{to_name}* (consult): {body}"
    elif env.kind == "reply":
        body = _format_reply_payload(env.payload)
        text = f"{to_emoji} *{to_name}* → {from_emoji} *{from_name}* (reply):\n{body}"
    else:  # error
        text = f"⚠️ *{to_name}* → *{from_name}* (error): {env.payload.get('error', 'unknown')}"
    await bot.send_message(chat_id=user.telegram_id, text=truncate(text), parse_mode="Markdown")


async def _relay_user_visible_envelopes(bot) -> None:
    """Background task: subscribes to bus:user_visible and renders
    attribution messages into each envelope's originating user's Telegram
    thread. Loop is loud-on-failure (logs but does NOT silently drop —
    R-3 invariant #2)."""
    assert _bus is not None
    transport = _bus._tx  # intentional access via the Bus's transport
    try:
        async for envelope_id_str in transport.subscribe("bus:user_visible"):
            try:
                env = await transport.fetch_envelope(UUID(envelope_id_str))
                if env is None:
                    logger.debug("user_visible relay: no envelope {}", envelope_id_str)
                    continue
                await _render_envelope_to_user(bot, env)
            except Exception:
                logger.exception("user_visible relay: render failed for {}", envelope_id_str)
                # Keep the loop alive — R-3 invariant #2: never silently drop.
    except asyncio.CancelledError:
        return


# ── Application setup & run ──────────────────────────────────────────

def main() -> None:
    """Build and start the Telegram bot."""
    # Configure loguru
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    ))
    logger.info("Starting KAIA bot...")

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status_extended))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("reset", cmd_reset))

    # Expert channel commands
    app.add_handler(CommandHandler("hevn", cmd_channel_switch))
    app.add_handler(CommandHandler("kazuki", cmd_channel_switch))
    app.add_handler(CommandHandler("akabane", cmd_channel_switch))
    app.add_handler(CommandHandler("makubex", cmd_channel_switch))
    app.add_handler(CommandHandler("exit", cmd_exit))
    app.add_handler(CommandHandler("team", cmd_team))
    app.add_handler(CommandHandler("setup_forum", cmd_setup_forum))

    # Hevn shortcut commands
    app.add_handler(CommandHandler("hevn_health", cmd_hevn_health))
    app.add_handler(CommandHandler("hevn_goals", cmd_hevn_goals))
    app.add_handler(CommandHandler("hevn_bills", cmd_hevn_bills))
    app.add_handler(CommandHandler("hevn_digest", cmd_hevn_digest))

    # MakubeX shortcut commands
    app.add_handler(CommandHandler("makubex_review", cmd_makubex_review))
    app.add_handler(CommandHandler("makubex_projects", cmd_makubex_projects))
    app.add_handler(CommandHandler("makubex_learn", cmd_makubex_learn))
    app.add_handler(CommandHandler("makubex_security", cmd_makubex_security))
    app.add_handler(CommandHandler("makubex_brief", cmd_makubex_brief))

    # Text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Voice / audio messages
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    # Inline button callbacks (snooze/dismiss)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Error handler
    app.add_error_handler(error_handler)

    logger.info("Bot is polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
