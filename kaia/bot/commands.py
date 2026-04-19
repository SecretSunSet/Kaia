"""Extended slash command handlers: /export, /reset, enhanced /status."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import get_settings
from database.connection import get_supabase
from database.queries import get_or_create_user, get_user_profile, get_active_reminders
from bot.middleware import get_session_stats


def _is_allowed(telegram_id: int) -> bool:
    """Check whether this user is authorised to use the bot."""
    settings = get_settings()
    if not settings.allowed_telegram_ids:
        return True
    return telegram_id in settings.allowed_telegram_ids


async def cmd_status_extended(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enhanced /status with user stats."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    settings = get_settings()
    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        sb = get_supabase()

        # Count profile facts
        profile = sb.table("user_profile").select("id", count="exact").eq("user_id", user.id).execute()
        profile_count = profile.count or 0

        # Count active reminders
        reminders = sb.table("reminders").select("id", count="exact").eq("user_id", user.id).eq("is_active", True).execute()
        reminder_count = reminders.count or 0

        # Count transactions
        transactions = sb.table("transactions").select("id", count="exact").eq("user_id", user.id).execute()
        txn_count = transactions.count or 0

        # Count conversations
        conversations = sb.table("conversations").select("id", count="exact").eq("user_id", user.id).execute()
        convo_count = conversations.count or 0

        # Active channel + channel conversation count
        active_channel = "general"
        channel_state = sb.table("user_channel_state").select("active_channel").eq("user_id", user.id).execute()
        if channel_state.data:
            active_channel = channel_state.data[0]["active_channel"]

        channel_convos = sb.table("channel_conversations").select("id", count="exact").eq("user_id", user.id).execute()
        channel_convo_count = channel_convos.count or 0

        channel_facts = sb.table("channel_profile").select("id", count="exact").eq("user_id", user.id).execute()
        channel_facts_count = channel_facts.count or 0

        # Format member since
        member_since = ""
        if user.created_at:
            try:
                dt = datetime.fromisoformat(str(user.created_at).replace("Z", "+00:00"))
                member_since = dt.strftime("%B %d, %Y")
            except (ValueError, TypeError):
                member_since = str(user.created_at)[:10]

        stats = get_session_stats()

        text = (
            "⚙️ *KAIA Status*\n\n"
            f"🤖 Bot: Online\n"
            f"🧠 AI: Claude ({settings.claude_model})\n"
            f"🔄 Fallback: {'Groq ✅' if settings.groq_api_key else 'None'}\n"
            f"🌐 Web: {'SerpAPI ✅' if settings.serpapi_key else '❌'} | "
            f"{'News ✅' if settings.news_api_key else '❌'} | "
            f"{'Weather ✅' if settings.openweather_api_key else '❌'}\n\n"
            f"📊 *Your Stats:*\n"
            f"  • Profile facts: {profile_count}\n"
            f"  • Active reminders: {reminder_count}\n"
            f"  • Transactions: {txn_count}\n"
            f"  • Conversations: {convo_count}\n"
            f"  • Active channel: {active_channel}\n"
            f"  • Channel facts: {channel_facts_count}\n"
            f"  • Channel messages: {channel_convo_count}\n"
            f"  • Member since: {member_since or 'Unknown'}\n\n"
            f"💰 Session: {stats['total_calls']} AI calls, "
            f"~${stats['estimated_cost_usd']:.4f} est. cost"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("Error in /status: {}", exc)
        await update.message.reply_text("⚙️ KAIA is online, but couldn't load stats right now.")


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /export — export user data as JSON."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    await update.message.chat.send_action("typing")

    try:
        user = await get_or_create_user(tg_user.id, tg_user.username)
        sb = get_supabase()

        # Gather all user data
        profile = sb.table("user_profile").select("*").eq("user_id", user.id).execute()
        reminders = sb.table("reminders").select("*").eq("user_id", user.id).execute()
        transactions = sb.table("transactions").select("*").eq("user_id", user.id).execute()
        conversations = sb.table("conversations").select("*").eq("user_id", user.id).order("created_at", desc=True).limit(100).execute()
        channel_state = sb.table("user_channel_state").select("*").eq("user_id", user.id).execute()
        channel_profile = sb.table("channel_profile").select("*").eq("user_id", user.id).execute()
        channel_conversations = sb.table("channel_conversations").select("*").eq("user_id", user.id).order("created_at", desc=True).limit(200).execute()

        export_data = {
            "exported_at": datetime.utcnow().isoformat(),
            "user": {
                "telegram_id": user.telegram_id,
                "username": user.username,
                "timezone": user.timezone,
                "currency": user.currency,
            },
            "profile": profile.data,
            "reminders": reminders.data,
            "transactions": transactions.data,
            "recent_conversations": conversations.data,
            "channel_state": channel_state.data,
            "channel_profile": channel_profile.data,
            "recent_channel_conversations": channel_conversations.data,
        }

        # Write to temp file and send
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix="kaia_export_", delete=False
        ) as f:
            json.dump(export_data, f, indent=2, default=str)
            tmp_path = f.name

        with open(tmp_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"kaia_export_{tg_user.id}.json",
                caption="📦 Here's your data export. This includes your profile, reminders, transactions, and recent conversations.",
            )

        import os
        os.remove(tmp_path)

    except Exception as exc:
        logger.exception("Error in /export: {}", exc)
        await update.message.reply_text("Something went wrong generating your export.")


# Pending reset confirmations: {telegram_id: timestamp}
_pending_resets: dict[int, float] = {}
_RESET_TIMEOUT = 120  # seconds


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reset — request data deletion with confirmation."""
    if update.effective_user is None or update.message is None:
        return
    tg_user = update.effective_user
    if not _is_allowed(tg_user.id):
        return

    import time
    _pending_resets[tg_user.id] = time.time()

    await update.message.reply_text(
        "⚠️ *This will permanently delete ALL your data:*\n"
        "Profile, reminders, transactions, conversations, memory.\n\n"
        "*This cannot be undone.*\n\n"
        "Type `CONFIRM DELETE` within 2 minutes to proceed.",
        parse_mode="Markdown",
    )


async def handle_reset_confirmation(update: Update) -> bool:
    """Check if a text message is a reset confirmation. Returns True if handled."""
    if update.effective_user is None or update.message is None:
        return False

    tg_user = update.effective_user
    text = (update.message.text or "").strip()

    if text != "CONFIRM DELETE":
        return False

    import time
    pending_time = _pending_resets.get(tg_user.id)
    if pending_time is None:
        return False

    # Check timeout
    if time.time() - pending_time > _RESET_TIMEOUT:
        del _pending_resets[tg_user.id]
        await update.message.reply_text("Reset request expired. Use /reset again if needed.")
        return True

    del _pending_resets[tg_user.id]

    try:
        user = await get_or_create_user(tg_user.id)
        sb = get_supabase()

        # Delete all user data (cascading from users table would work too,
        # but let's be explicit)
        for table in (
            "conversations",
            "transactions",
            "reminders",
            "memory_log",
            "budget_limits",
            "financial_goals",
            "recurring_bills",
            "user_profile",
            "channel_conversations",
            "channel_profile",
            "user_channel_state",
        ):
            sb.table(table).delete().eq("user_id", user.id).execute()

        logger.info("Data reset for user {} (tg={})", user.id, tg_user.id)

        await update.message.reply_text(
            "🗑️ All data deleted. I've forgotten everything about you.\n"
            "Send any message to start fresh."
        )
        return True

    except Exception as exc:
        logger.exception("Error in reset confirmation: {}", exc)
        await update.message.reply_text("Something went wrong during reset. Please try again.")
        return True
