"""Concierge — orchestrates one general (non-expert) KAIA turn.

Lifted verbatim from the duplicated block in bot/telegram_bot.py
(handle_message / handle_voice). Transport-agnostic: returns a
ConciergeResult; the caller renders it. See Docs/AGENTIC_OS/DESIGN.md
and Docs/AGENTIC_OS/PLAN_R2.md (behavior-preservation invariants).
"""

from __future__ import annotations

from config.constants import ROLE_ASSISTANT, ROLE_USER, SKILL_CHAT
from config.settings import get_settings
from core.ai_engine import AIEngine
from core.expert_detector import detect_expert_topic
from core.memory_manager import MemoryManager
from core.skill_router import SkillRouter
from database.models import User
from database.queries import get_recent_conversations, save_conversation
from utils.time_utils import format_relative_time

from concierge.result import ConciergeResult

settings = get_settings()


class Concierge:
    """KAIA's slim orchestrator for general (non-expert) conversation.

    Composes the existing SkillRouter + MemoryManager. The bot injects its
    already-constructed singletons so behavior and instances are identical
    to pre-R-2 (no double instantiation of skills/AI).
    """

    def __init__(
        self,
        ai_engine: AIEngine,
        *,
        skill_router: SkillRouter,
        memory_mgr: MemoryManager,
    ) -> None:
        self._ai = ai_engine
        self._router = skill_router
        self._memory = memory_mgr

    async def handle_general_turn(
        self,
        user: User,
        message: str,
        *,
        suggest_experts: bool,
    ) -> ConciergeResult:
        """Run one general KAIA turn.

        Args:
            user: The current user record.
            message: The incoming text (already transcribed for voice).
            suggest_experts: Whether to run the stateful expert-topic
                detector. ``True`` for the text path, ``False`` for voice
                — preserves the exact pre-R-2 divergence (invariant #2).

        Returns:
            ConciergeResult — transport renders it.
        """
        profile_context = await self._memory.load_profile_context(user.id)

        recent_convos = await get_recent_conversations(
            user.id, limit=settings.max_conversation_history
        )
        tz = user.timezone or settings.default_timezone
        history: list[dict[str, str]] = []
        for c in recent_convos:
            rel = format_relative_time(c.created_at, tz) if c.created_at else ""
            content = f"[{rel}] {c.content}" if rel else c.content
            history.append({"role": c.role, "content": content})

        result = await self._router.route(
            user=user,
            message=message,
            conversation_history=history,
            profile_context=profile_context,
        )

        await save_conversation(
            user.id, ROLE_USER, message, skill_used=result.skill_name
        )
        await save_conversation(
            user.id, ROLE_ASSISTANT, result.text, skill_used=result.skill_name
        )

        suggestion: str | None = None
        if suggest_experts and result.skill_name == SKILL_CHAT:
            hit = detect_expert_topic(message, result.text, user_id=user.id)
            if hit:
                suggestion = hit["suggestion"]

        updated_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": result.text},
        ]
        self._memory.run_background_extraction(user.id, updated_history)

        return ConciergeResult(
            text=result.text,
            skill_name=result.skill_name,
            ai_response=result.ai_response,
            suggestion=suggestion,
            profile_context=profile_context,
        )
