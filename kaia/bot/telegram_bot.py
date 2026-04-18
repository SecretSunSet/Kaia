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
from core.scheduler import start_scheduler, shutdown_scheduler, handle_snooze, handle_dismiss
from database.queries import (
    get_or_create_user,
    get_recent_conversations,
    save_conversation,
    get_channel_profile,
)
from bot.commands import cmd_status_extended, cmd_export, cmd_reset, handle_reset_confirmation
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
    channel_id = command_text

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


# ── Main message handler ────────────────────────────────────────────

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

        # 2. Check which channel the user is in
        active_channel = await channel_mgr.get_active_channel(user.id)

        if active_channel != CHANNEL_GENERAL:
            # ── Expert channel flow ──────────────────────────────────
            channel = await channel_mgr.get_channel_info(active_channel)
            if channel is None:
                # Channel gone — reset to general and fall through
                await channel_mgr.exit_channel(user.id)
            else:
                expert = get_expert(active_channel, ai_engine) or PlaceholderExpert(ai_engine)
                result = await expert.handle(user=user, message=text, channel=channel)
                await update.message.reply_text(
                    truncate(result.text), parse_mode="Markdown"
                )
                if result.ai_response:
                    track_ai_usage(
                        result.ai_response.input_tokens,
                        result.ai_response.output_tokens,
                        result.ai_response.provider,
                    )
                    logger.info(
                        "msg handled | user={} channel={} provider={} tokens={}+{}",
                        tg_user.id,
                        active_channel,
                        result.ai_response.provider,
                        result.ai_response.input_tokens,
                        result.ai_response.output_tokens,
                    )
                return

        # ── General KAIA flow (existing) ─────────────────────────────

        # 3. Load profile + conversation history
        profile_context = await memory_mgr.load_profile_context(user.id)
        recent_convos = await get_recent_conversations(
            user.id, limit=settings.max_conversation_history
        )
        history = [{"role": c.role, "content": c.content} for c in recent_convos]

        # 4. Route to skill via intent detection
        result = await skill_router.route(
            user=user,
            message=text,
            conversation_history=history,
            profile_context=profile_context,
        )

        # 5. Save conversation (user message + bot response)
        await save_conversation(user.id, ROLE_USER, text, skill_used=result.skill_name)
        await save_conversation(
            user.id, ROLE_ASSISTANT, result.text, skill_used=result.skill_name
        )

        # 6. Send response (truncated for Telegram limit)
        await update.message.reply_text(truncate(result.text), parse_mode="Markdown")

        # 6b. Suggest expert if the message was handled by chat skill
        if result.skill_name == SKILL_CHAT:
            suggestion = detect_expert_topic(text, result.text, user_id=user.id)
            if suggestion:
                await update.message.reply_text(
                    f"💡 _{suggestion['suggestion']}_",
                    parse_mode="Markdown",
                )

        # 7. Run background memory extraction (fire-and-forget)
        updated_history = history + [
            {"role": "user", "content": text},
            {"role": "assistant", "content": result.text},
        ]
        memory_mgr.run_background_extraction(user.id, updated_history)

        # 8. Track AI usage
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

        # Show what was transcribed
        await update.message.reply_text(f"🎙️ _I heard:_ {transcribed}", parse_mode="Markdown")

        # Process through the pipeline
        user = await get_or_create_user(tg_user.id, tg_user.username)

        # Check active channel — route to expert if not in general
        active_channel = await channel_mgr.get_active_channel(user.id)

        if active_channel != CHANNEL_GENERAL:
            channel = await channel_mgr.get_channel_info(active_channel)
            if channel:
                expert = get_expert(active_channel, ai_engine) or PlaceholderExpert(ai_engine)
                result = await expert.handle(user=user, message=transcribed, channel=channel)
                await update.message.reply_text(
                    truncate(result.text), parse_mode="Markdown"
                )
                if result.ai_response:
                    track_ai_usage(
                        result.ai_response.input_tokens,
                        result.ai_response.output_tokens,
                        result.ai_response.provider,
                    )
                return
            else:
                await channel_mgr.exit_channel(user.id)

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

        # Send text response
        await update.message.reply_text(truncate(result.text), parse_mode="Markdown")

        # Optionally reply with voice
        if _should_reply_with_voice(profile_context):
            tts_path = await text_to_speech(result.text, voice=settings.tts_voice)
            if tts_path:
                with open(tts_path, "rb") as audio:
                    await update.message.reply_voice(voice=audio)

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
