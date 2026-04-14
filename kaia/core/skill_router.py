"""Skill router — maps detected intent to the correct skill handler."""

from __future__ import annotations

from loguru import logger

from config.constants import (
    SKILL_BRIEFING,
    SKILL_BUDGET,
    SKILL_CHAT,
    SKILL_MEMORY,
    SKILL_REMINDERS,
    SKILL_WEB_BROWSE,
)
from core.ai_engine import AIEngine
from core.intent_detector import IntentDetector, IntentResult
from database.models import User
from skills.base import BaseSkill, SkillResult
from skills.briefing.handler import BriefingSkill
from skills.budget.handler import BudgetSkill
from skills.chat.handler import ChatSkill
from skills.memory.handler import MemorySkill
from skills.reminders.handler import RemindersSkill
from skills.web_browse.handler import WebBrowseSkill


class SkillRouter:
    """Manages skill instances and dispatches messages to the correct handler."""

    def __init__(self, ai_engine: AIEngine) -> None:
        self._ai = ai_engine
        self._detector = IntentDetector(ai_engine)

        # Register available skills
        self._skills: dict[str, BaseSkill] = {
            SKILL_CHAT: ChatSkill(ai_engine),
            SKILL_MEMORY: MemorySkill(ai_engine),
            SKILL_REMINDERS: RemindersSkill(ai_engine),
            SKILL_BUDGET: BudgetSkill(ai_engine),
            SKILL_BRIEFING: BriefingSkill(ai_engine),
            SKILL_WEB_BROWSE: WebBrowseSkill(ai_engine),
        }

    async def route(
        self,
        user: User,
        message: str,
        conversation_history: list[dict[str, str]],
        profile_context: str,
    ) -> SkillResult:
        """Detect intent and dispatch to the appropriate skill.

        Args:
            user: The current user.
            message: Incoming text message.
            conversation_history: Recent messages for context.
            profile_context: Formatted user profile string.

        Returns:
            SkillResult from the matched skill handler.
        """
        intent = await self._detector.detect(message)

        skill = self._skills.get(intent.skill)
        if skill is None:
            # Skill not yet implemented — fall back to chat
            logger.info(
                "Skill '{}' not implemented, falling back to chat",
                intent.skill,
            )
            skill = self._skills[SKILL_CHAT]

        logger.info(
            "Routing to '{}' (detected='{}', conf={:.2f})",
            skill.name,
            intent.skill,
            intent.confidence,
        )

        return await skill.handle(
            user=user,
            message=message,
            conversation_history=conversation_history,
            profile_context=profile_context,
        )

    @property
    def intent_detector(self) -> IntentDetector:
        """Expose the detector for direct use if needed."""
        return self._detector
