"""Rate limiting and cost tracking middleware."""

from __future__ import annotations

import time
from collections import defaultdict

from loguru import logger

# ── Rate limiter ────────────────────────────────────────────────────

_RATE_LIMIT = 20  # messages per window
_RATE_WINDOW = 60  # seconds

_message_counts: dict[int, list[float]] = defaultdict(list)


def check_rate_limit(telegram_id: int) -> bool:
    """Return True if the user is within rate limits, False if exceeded."""
    now = time.time()
    window_start = now - _RATE_WINDOW

    # Prune old timestamps
    timestamps = _message_counts[telegram_id]
    _message_counts[telegram_id] = [t for t in timestamps if t > window_start]

    if len(_message_counts[telegram_id]) >= _RATE_LIMIT:
        logger.warning("Rate limit exceeded for user {}", telegram_id)
        return False

    _message_counts[telegram_id].append(now)
    return True


# ── AI cost tracking ────────────────────────────────────────────────

# Approximate per-token costs (USD) — Claude Sonnet
_COST_PER_INPUT_TOKEN = 3.0 / 1_000_000   # $3/M input tokens
_COST_PER_OUTPUT_TOKEN = 15.0 / 1_000_000  # $15/M output tokens

_session_stats = {
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_calls": 0,
    "estimated_cost_usd": 0.0,
}


def track_ai_usage(input_tokens: int, output_tokens: int, provider: str = "claude") -> None:
    """Track token usage and estimated cost."""
    _session_stats["total_input_tokens"] += input_tokens
    _session_stats["total_output_tokens"] += output_tokens
    _session_stats["total_calls"] += 1

    if provider == "claude":
        cost = (input_tokens * _COST_PER_INPUT_TOKEN) + (output_tokens * _COST_PER_OUTPUT_TOKEN)
        _session_stats["estimated_cost_usd"] += cost


def get_session_stats() -> dict:
    """Return current session stats."""
    return dict(_session_stats)
