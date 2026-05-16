"""Concierge — KAIA's slim orchestrator (Agentic OS R-2).

Owns the general (non-expert) conversation turn and KAIA's onboarding
greeting. Transport-agnostic: nothing here imports ``telegram``.
"""

from __future__ import annotations

from concierge.onboarding import welcome_text
from concierge.result import ConciergeResult

__all__ = ["ConciergeResult", "welcome_text"]
