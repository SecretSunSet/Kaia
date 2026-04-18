"""Expert topic detector — suggests relevant experts from general chat."""

from __future__ import annotations

from config.constants import (
    CHANNEL_HEVN,
    CHANNEL_KAZUKI,
    CHANNEL_AKABANE,
    CHANNEL_MAKUBEX,
)

# Keyword lists per expert channel
_EXPERT_KEYWORDS: dict[str, list[str]] = {
    CHANNEL_HEVN: [
        "budget", "savings", "debt", "loan", "interest rate", "insurance",
        "financial", "money management", "emergency fund", "retirement",
        "sss", "pag-ibig", "philhealth", "bir", "tax", "mp2",
        "gcash", "maya", "bank", "credit card", "financial goal",
        "income", "expense tracking", "financial plan", "net worth",
    ],
    CHANNEL_KAZUKI: [
        "invest", "portfolio", "stock", "crypto", "etf", "mutual fund",
        "bond", "dividend", "allocation", "diversif", "rebalance",
        "market", "bull", "bear", "roi", "compound", "uitf",
        "holding", "position", "long-term", "asset",
    ],
    CHANNEL_AKABANE: [
        "trade", "trading", "order", "buy order", "sell order",
        "stop loss", "take profit", "tp/sl", "binance", "leverage",
        "margin", "scalp", "swing trade", "position size", "risk reward",
        "candlestick", "technical analysis", "chart", "entry", "exit",
        "p&l", "pnl",
    ],
    CHANNEL_MAKUBEX: [
        "code", "programming", "debug", "deploy", "server", "api",
        "database", "architecture", "git", "docker", "kubernetes",
        "python", "javascript", "typescript", "react", "node",
        "infrastructure", "ci/cd", "security audit", "tech stack",
        "algorithm", "framework", "backend", "frontend",
    ],
}

# Expert suggestion messages
_SUGGESTION_TEMPLATES: dict[str, str] = {
    CHANNEL_HEVN: "This sounds like a financial topic. Want me to connect you with Hevn, your financial advisor? /hevn",
    CHANNEL_KAZUKI: "This looks like an investment topic. Want me to connect you with Kazuki, your investment manager? /kazuki",
    CHANNEL_AKABANE: "This seems trading-related. Want me to connect you with Akabane, your trading strategist? /akabane",
    CHANNEL_MAKUBEX: "This is a tech topic. Want me to connect you with MakubeX, your tech lead? /makubex",
}

# Track recently suggested channels per user to avoid nagging
# {user_id: set(channel_id)} — resets on bot restart, which is fine
_recent_suggestions: dict[str, set[str]] = {}


def detect_expert_topic(
    message: str,
    response: str,
    user_id: str | None = None,
) -> dict | None:
    """Analyse message and determine if an expert should be suggested.

    Args:
        message: The user's original message.
        response: KAIA's response (for additional context).
        user_id: Optional user ID to track suggestion history.

    Returns:
        {"channel_id": "hevn", "suggestion": "..."} or None.
    """
    combined = f"{message} {response}".lower()

    scores: dict[str, int] = {}
    for channel_id, keywords in _EXPERT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score >= 2:
            scores[channel_id] = score

    if not scores:
        return None

    best = max(scores, key=lambda k: scores[k])

    # Don't re-suggest the same expert to the same user
    if user_id:
        already_suggested = _recent_suggestions.get(user_id, set())
        if best in already_suggested:
            return None
        _recent_suggestions.setdefault(user_id, set()).add(best)

    return {
        "channel_id": best,
        "suggestion": _SUGGESTION_TEMPLATES[best],
    }


def clear_suggestion_history(user_id: str) -> None:
    """Clear suggestion tracking for a user (e.g., on channel switch)."""
    _recent_suggestions.pop(user_id, None)
