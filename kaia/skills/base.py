"""Abstract base class for all KAIA skills."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.ai_engine import AIEngine, AIResponse
from database.models import User


@dataclass
class SkillResult:
    """Standard return type from every skill handler."""

    text: str
    skill_name: str
    ai_response: AIResponse | None = None


class BaseSkill(ABC):
    """Every skill inherits from this and implements ``handle``."""

    name: str = "base"

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine

    @abstractmethod
    async def handle(
        self,
        user: User,
        message: str,
        conversation_history: list[dict[str, str]],
        profile_context: str,
    ) -> SkillResult:
        """Process a user message and return a response.

        Args:
            user: The current user record.
            message: The incoming text message.
            conversation_history: Recent messages as [{role, content}, ...].
            profile_context: Pre-formatted user profile string for system prompt.
        """
        ...
