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
