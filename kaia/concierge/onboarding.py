"""KAIA's first-contact onboarding — the /start greeting.

Single source of truth for the welcome message. The Telegram transport
calls ``welcome_text()`` and renders it; no other copy of this string
should exist in the codebase.
"""

from __future__ import annotations

_WELCOME = (
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
    "Type /help for more details."
)


def welcome_text() -> str:
    """Return KAIA's /start greeting."""
    return _WELCOME
