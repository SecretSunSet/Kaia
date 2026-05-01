"""App-wide constants: categories, skill IDs, limits, defaults."""

# ── Skill identifiers ───────────────────────────────────────────────
SKILL_CHAT = "chat"
SKILL_MEMORY = "memory"
SKILL_REMINDERS = "reminders"
SKILL_BUDGET = "budget"
SKILL_BRIEFING = "briefing"
SKILL_WEB_BROWSE = "web_browse"

ALL_SKILLS = [
    SKILL_CHAT,
    SKILL_MEMORY,
    SKILL_REMINDERS,
    SKILL_BUDGET,
    SKILL_BRIEFING,
    SKILL_WEB_BROWSE,
]

# ── Budget categories ───────────────────────────────────────────────
EXPENSE_CATEGORIES = [
    "food",
    "transport",
    "utilities",
    "rent",
    "groceries",
    "entertainment",
    "health",
    "shopping",
    "subscriptions",
    "education",
    "personal_care",
    "gifts",
    "travel",
    "savings",
    "other",
]

INCOME_CATEGORIES = [
    "salary",
    "freelance",
    "gift",
    "refund",
    "investment",
    "other",
]

# ── User profile categories ─────────────────────────────────────────
PROFILE_CATEGORIES = [
    "identity",
    "health",
    "finances",
    "technical",
    "personality",
    "preferences",
    "goals",
    "patterns",
]

# ── Reminder recurrence options ──────────────────────────────────────
RECURRENCE_NONE = "none"
RECURRENCE_DAILY = "daily"
RECURRENCE_WEEKLY = "weekly"
RECURRENCE_MONTHLY = "monthly"

# ── Conversation roles ──────────────────────────────────────────────
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

# ── Memory fact types ────────────────────────────────────────────────
FACT_TYPES = [
    "correction",
    "preference",
    "habit",
    "mood",
    "goal",
    "general",
]

# ── Memory source types ─────────────────────────────────────────────
SOURCE_EXPLICIT = "explicit"
SOURCE_INFERRED = "inferred"

# ── Limits & defaults ────────────────────────────────────────────────
MAX_TELEGRAM_MESSAGE_LENGTH = 4096
MAX_SNOOZE_COUNT = 5
DEFAULT_SNOOZE_MINUTES = 10
DEFAULT_BRIEFING_HOUR = 7  # 7:00 AM local time
DEFAULT_CONFIDENCE = 0.5

# ── Budget ───────────────────────────────────────────────────────────
BUDGET_CATEGORIES = [
    "food", "transport", "bills", "entertainment", "health",
    "shopping", "education", "salary", "freelance", "family",
    "subscriptions", "savings", "gifts", "other",
]

BUDGET_CATEGORY_EMOJIS: dict[str, str] = {
    "food": "🍔",
    "transport": "🚗",
    "bills": "🏠",
    "entertainment": "🎮",
    "health": "💊",
    "shopping": "🛍️",
    "education": "📚",
    "salary": "💼",
    "freelance": "💻",
    "family": "👨‍👩‍👧",
    "subscriptions": "📱",
    "savings": "🏦",
    "gifts": "🎁",
    "other": "📦",
}

BUDGET_WARNING_THRESHOLD = 0.8  # Warn at 80% of limit

# ── Currency formatting ──────────────────────────────────────────────
CURRENCY_SYMBOLS: dict[str, str] = {
    "PHP": "₱",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
}

# ── Web browse & briefing ───────────────────────────────────────────
BRIEFING_DEFAULT_TIME = "07:00"
DEFAULT_WEATHER_LOCATION = "Manila, Philippines"
WEB_SEARCH_MAX_RESULTS = 5
WEB_SCRAPE_MAX_CHARS = 3000
WEB_REQUEST_TIMEOUT = 10  # seconds

# ── Channels / Expert system ────────────────────────────────────────
CHANNEL_GENERAL = "general"
CHANNEL_HEVN = "hevn"
CHANNEL_KAZUKI = "kazuki"
CHANNEL_AKABANE = "akabane"
CHANNEL_MAKUBEX = "makubex"

ALL_CHANNELS = [CHANNEL_GENERAL, CHANNEL_HEVN, CHANNEL_KAZUKI, CHANNEL_AKABANE, CHANNEL_MAKUBEX]

CHANNEL_EMOJIS: dict[str, str] = {
    CHANNEL_GENERAL: "\U0001f451",
    CHANNEL_HEVN: "\U0001f4b0",
    CHANNEL_KAZUKI: "\U0001f4c8",
    CHANNEL_AKABANE: "\u2694\ufe0f",
    CHANNEL_MAKUBEX: "\U0001f527",
}

# Required knowledge per expert channel.
# Each entry: (category, key, priority, question_text)
# Priority 1 = ask first, 2 = ask next, 3 = ask later.
CHANNEL_REQUIRED_KNOWLEDGE: dict[str, list[tuple[str, str, int, str]]] = {
    CHANNEL_HEVN: [
        ("income_info", "monthly_income", 1, "What's your monthly income?"),
        ("income_info", "income_frequency", 1, "When do you receive your salary?"),
        ("income_info", "income_sources", 2, "Do you have other income sources besides salary?"),
        ("debt_info", "active_debts", 1, "Do you have any active loans or credit card debt?"),
        ("savings", "emergency_fund", 2, "Do you have an emergency fund? How much is in it?"),
        ("insurance", "health_insurance", 2, "Do you have health insurance coverage?"),
        ("goals", "financial_goals", 2, "What are your main financial goals?"),
        ("risk_profile", "risk_tolerance", 2, "How comfortable are you with financial risk?"),
        ("retirement", "retirement_plans", 3, "Are you contributing to SSS, Pag-IBIG MP2, or any retirement fund?"),
        ("personal", "dependents", 3, "Are you financially supporting anyone (family, dependents)?"),
    ],
    CHANNEL_KAZUKI: [
        ("portfolio", "current_holdings", 1, "What investments do you currently hold?"),
        ("experience", "investment_level", 1, "How would you rate your investment experience?"),
        ("budget", "investment_budget", 1, "How much can you invest monthly?"),
        ("strategy", "time_horizon", 2, "When would you need this investment money?"),
        ("preferences", "asset_preferences", 2, "What types of assets interest you?"),
        ("platforms", "exchanges_used", 2, "What platforms do you use for investing?"),
        ("history", "past_investments", 3, "Any notable investment wins or losses?"),
    ],
    CHANNEL_AKABANE: [
        ("exchange", "binance_connected", 1, "Is your Binance account connected?"),
        ("capital", "trading_capital", 1, "How much is in your trading account?"),
        ("risk", "risk_per_trade", 1, "What's the max % you'd risk per trade?"),
        ("experience", "trading_experience", 2, "How long have you been trading?"),
        ("preferences", "preferred_pairs", 2, "Which trading pairs do you focus on?"),
        ("style", "trading_style", 2, "Are you a scalper, swing trader, or position trader?"),
        ("limits", "daily_loss_limit", 3, "What's your daily loss limit?"),
    ],
    CHANNEL_MAKUBEX: [
        ("projects", "current_projects", 1, "What are you currently building?"),
        ("stack", "tech_stack", 1, "What's your primary tech stack?"),
        ("skills", "skill_level", 2, "How would you rate your skills per technology?"),
        ("goals", "learning_goals", 2, "What do you want to learn next?"),
        ("context", "work_context", 2, "Are you a solo dev, in a team, or at a company?"),
        ("tools", "dev_environment", 3, "What's your dev setup (OS, IDE, tools)?"),
    ],
}
