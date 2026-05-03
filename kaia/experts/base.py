"""Abstract base class for all KAIA expert channels."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from loguru import logger

from config.settings import get_settings
from core.ai_engine import AIEngine
from core.channel_manager import ChannelManager
from core.channel_memory import ChannelMemoryManager
from core.channel_extractor import channel_extract_and_save
from config.constants import ROLE_USER, ROLE_ASSISTANT
from database.models import Channel, User
from database.queries import (
    get_channel_conversations,
    save_channel_conversation,
    get_channel_profile,
)
from skills.base import SkillResult
from utils.time_utils import format_relative_time


class BaseExpert(ABC):
    """Base class for all KAIA expert channels."""

    channel_id: str = ""

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine
        self._channel_mgr = ChannelManager()
        self._channel_mem = ChannelMemoryManager()

    @abstractmethod
    async def handle(
        self,
        user: User,
        message: str,
        channel: Channel,
    ) -> SkillResult:
        """Handle a message in this expert's channel."""
        ...

    async def get_conversation_history(
        self,
        user_id: str,
        channel_id: str,
        limit: int = 20,
        user_timezone: str | None = None,
    ) -> list[dict[str, str]]:
        """Load recent channel-specific conversation history.

        Each message's content is prefixed with a relative-time tag
        (e.g. "[3 days ago] ...") so the expert can reason about *when*
        prior turns happened rather than treating them as undated.
        """
        tz = user_timezone or get_settings().default_timezone
        convos = await get_channel_conversations(user_id, channel_id, limit)
        out: list[dict[str, str]] = []
        for c in convos:
            rel = format_relative_time(c.created_at, tz) if c.created_at else ""
            content = f"[{rel}] {c.content}" if rel else c.content
            out.append({"role": c.role, "content": content})
        return out

    async def save_messages(
        self,
        user_id: str,
        channel_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Save both user and assistant messages to channel history."""
        await save_channel_conversation(user_id, channel_id, ROLE_USER, user_msg)
        await save_channel_conversation(user_id, channel_id, ROLE_ASSISTANT, assistant_msg)

    def run_background_extraction(
        self,
        user_id: str,
        channel_id: str,
        messages: list[dict[str, str]],
    ) -> None:
        """Fire-and-forget channel memory extraction after conversation."""
        async def _extract() -> None:
            try:
                saved = await channel_extract_and_save(
                    ai_engine=self.ai,
                    user_id=user_id,
                    channel_id=channel_id,
                    conversation_messages=messages,
                )
                if saved:
                    logger.info(
                        "Channel extraction ({}): {} facts saved for user {}",
                        channel_id, saved, user_id,
                    )
            except Exception as exc:
                logger.warning("Channel extraction error ({}): {}", channel_id, exc)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_extract())
        except RuntimeError:
            logger.warning("No running event loop for channel extraction")

    async def generate_onboarding(
        self,
        user: User,
        channel: Channel,
        combined_context: str,
    ) -> str:
        """Generate the first-time onboarding message for this expert.

        Introduces the expert and asks the top 2-3 critical questions.
        """
        channel_entries = await get_channel_profile(user.id, channel.channel_id)
        gaps = self._channel_mem.get_knowledge_gaps(channel.channel_id, channel_entries)
        top_questions = [g["question"] for g in gaps[:3]]

        questions_text = ""
        if top_questions:
            questions_text = (
                "\n\nTo get started, ask these critical questions naturally in your greeting:\n"
                + "\n".join(f"- {q}" for q in top_questions)
            )

        system_prompt = (
            f"{channel.system_prompt}\n\n"
            f"USER CONTEXT:\n{combined_context}\n\n"
            f"INSTRUCTION: This is the user's FIRST TIME meeting you. "
            f"Introduce yourself in character — who you are, what you can do for them, "
            f"and your personality. Keep it warm and concise (2-3 short paragraphs). "
            f"Weave in the critical questions naturally, don't list them.{questions_text}"
        )

        response = await self.ai.chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": "Hello!"}],
        )
        return response.text

    def format_response_footer(self, channel: Channel) -> str:
        """Return the channel indicator footer."""
        return (
            f"\n\n---\n"
            f"_{channel.emoji} {channel.character_name} — {channel.role}_ | "
            f"/exit to return to KAIA"
        )
