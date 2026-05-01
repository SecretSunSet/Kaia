"""Main Telegram bot entry point — message, voice, callback handlers, scheduler."""

from __future__ import annotations

import os
import sys
import tempfile

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
    ROLE_USER,
    ROLE_ASSISTANT,
    SKILL_CHAT,
    CHANNEL_GENERAL,
    CHANNEL_EMOJIS,
)
from core.ai_engine import AIEngine
from core.memory_manager import MemoryManager
from core.skill_router import SkillRouter
from core.channel_manager import ChannelManager
from core.channel_memory import ChannelMemoryManager
from core.expert_detector import detect_expert_topic, clear_suggestion_history
from core.forum_manager import ForumManager, ForumSetupError
from core.scheduler import start_scheduler, shutdown_scheduler, handle_snooze, handle_dismiss
from database.queries import (
    get_or_create_user,
    get_recent_conversations,
    save_conversation,
    get_channel_profile,
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
    await update.message.reply_text(
        "👋 Hi! I'm *KAIA* — your personal AI assistant.\n\n"
        "I can help you with:\n"
        "🗣️ Chat & advice — just talk to me naturally\n"
        "🧠 Memory — I learn about you over time\n"
        "⏰ Reminders — \"Remind me to take meds at 8pm daily\"\n"
        "💰 Budget — \"Spent ₱500 on groceries\"\n"
        "🌅 Briefing — Daily morning summary\n"
        "🌐 Web search — \"What's the latest news about...\"\n"
        "🎙️ Voice — Send me voice messages!\n\n"
        "👥 *Meet my team of experts:*\n"
        "💰 /hevn — Financial advisor\n"
        "📈 /kazuki — Investment manager\n"
        "⚔️ /akabane — Trading strategist\n"
        "🔧 /makubex — Tech lead\n"
        "Type /team to see everyone.\n\n"
        "Just talk to me like a friend. No commands needed!\n"
        "Type /help for more details.",
        parse_mode="Markdown",
    )


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

        profile_context = await memory_mgr.load_profile_context(user.id)
        recent_convos = await get_recent_conversations(
            user.id, limit=settings.max_conversation_history
        )
        history = [{"role": c.role, "content": c.content} for c in recent_convos]

        result = await skill_router.route(
            user=user,
            message=text,
            conversation_history=history,
            profile_context=profile_context,
        )

        await save_conversation(user.id, ROLE_USER, text, skill_used=result.skill_name)
        await save_conversation(
            user.id, ROLE_ASSISTANT, result.text, skill_used=result.skill_name
        )

        reply_kwargs: dict = {"parse_mode": "Markdown"}
        if is_forum and topic_id is not None:
            reply_kwargs["message_thread_id"] = topic_id

        await update.message.reply_text(truncate(result.text), **reply_kwargs)

        # Suggest expert if the message was handled by chat skill
        if result.skill_name == SKILL_CHAT:
            suggestion = detect_expert_topic(text, result.text, user_id=user.id)
            if suggestion:
                await update.message.reply_text(
                    f"💡 _{suggestion['suggestion']}_",
                    **reply_kwargs,
                )

        updated_history = history + [
            {"role": "user", "content": text},
            {"role": "assistant", "content": result.text},
        ]
        memory_mgr.run_background_extraction(user.id, updated_history)

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

        # General KAIA flow
        profile_context = await memory_mgr.load_profile_context(user.id)
        recent_convos = await get_recent_conversations(
            user.id, limit=settings.max_conversation_history
        )
        history = [{"role": c.role, "content": c.content} for c in recent_convos]

        result = await skill_router.route(
            user=user,
            message=transcribed,
            conversation_history=history,
            profile_context=profile_context,
        )

        # Save conversation
        await save_conversation(user.id, ROLE_USER, transcribed, skill_used=result.skill_name)
        await save_conversation(user.id, ROLE_ASSISTANT, result.text, skill_used=result.skill_name)

        # Send text response (in the same topic if applicable)
        await update.message.reply_text(truncate(result.text), **reply_kwargs)

        # Optionally reply with voice
        if _should_reply_with_voice(profile_context):
            tts_path = await text_to_speech(result.text, voice=settings.tts_voice)
            if tts_path:
                voice_kwargs: dict = {}
                if is_forum and topic_id is not None:
                    voice_kwargs["message_thread_id"] = topic_id
                with open(tts_path, "rb") as audio:
                    await update.message.reply_voice(voice=audio, **voice_kwargs)

        # Background extraction
        updated_history = history + [
            {"role": "user", "content": transcribed},
            {"role": "assistant", "content": result.text},
        ]
        memory_mgr.run_background_extraction(user.id, updated_history)

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
    """Called after the Application is initialised — start scheduler, cleanup."""
    bot = application.bot
    set_bot(bot)
    await start_scheduler(bot)
    cleanup_old_files()  # Clean up any stale TTS files from previous runs
    logger.info("Post-init complete: scheduler started, bot reference stored")


async def post_shutdown(application: Application) -> None:
    """Called when the Application shuts down."""
    shutdown_scheduler()


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
