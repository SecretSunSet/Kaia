"""Transport-agnostic output of one general KAIA turn."""

from __future__ import annotations

from dataclasses import dataclass

from core.ai_engine import AIResponse


@dataclass(slots=True)
class ConciergeResult:
    """What a general (non-expert) KAIA turn produced.

    The concierge owns orchestration (routing, persistence, suggestion,
    extraction); the transport (Telegram bot) owns rendering. This object
    carries everything the transport needs and nothing Telegram-specific.

    Attributes:
        text: The assistant reply to send to the user.
        skill_name: Which skill produced ``text`` (e.g. ``"chat"``).
        ai_response: Token/provider usage for telemetry, or ``None``.
        suggestion: Expert-suggestion line to send as a follow-up message,
            or ``None``. Only ever populated on the text path (see R-2
            behavior-preservation invariant #2).
        profile_context: The formatted profile string the turn was routed
            with. Returned so the voice transport can make its TTS decision
            off the same string without a second profile load.
    """

    text: str
    skill_name: str
    ai_response: AIResponse | None = None
    suggestion: str | None = None
    profile_context: str = ""
