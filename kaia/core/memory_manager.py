"""Memory manager — profile loading, formatting, and background extraction orchestration."""

from __future__ import annotations

import asyncio

from loguru import logger

from core.ai_engine import AIEngine
from database.queries import get_user_profile, get_recent_conversations
from database.models import ProfileEntry
from skills.memory.extractor import extract_and_save


class MemoryManager:
    """Centralises profile operations and background memory extraction."""

    def __init__(self, ai_engine: AIEngine) -> None:
        self._ai = ai_engine

    async def load_profile_context(self, user_id: str) -> str:
        """Load and format the user's profile for system prompt injection."""
        entries = await get_user_profile(user_id)
        return format_profile(entries)

    async def load_profile_entries(self, user_id: str) -> list[ProfileEntry]:
        """Load raw profile entries."""
        return await get_user_profile(user_id)

    def run_background_extraction(
        self,
        user_id: str,
        conversation_messages: list[dict[str, str]],
    ) -> None:
        """Fire-and-forget background memory extraction after a conversation.

        Creates an asyncio task that runs the extractor without blocking
        the response to the user.
        """
        async def _extract() -> None:
            try:
                saved = await extract_and_save(
                    ai_engine=self._ai,
                    user_id=user_id,
                    conversation_messages=conversation_messages,
                )
                if saved:
                    logger.info("Background extraction: {} facts saved for user {}", saved, user_id)
            except Exception as exc:
                logger.warning("Background extraction error: {}", exc)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_extract())
        except RuntimeError:
            logger.warning("No running event loop for background extraction")


def format_profile(profile_entries: list[ProfileEntry]) -> str:
    """Turn profile DB rows into a readable string for the system prompt."""
    if not profile_entries:
        return ""
    lines: list[str] = []
    current_cat = ""
    for entry in sorted(profile_entries, key=lambda e: e.category):
        if entry.category != current_cat:
            current_cat = entry.category
            lines.append(f"\n[{current_cat.upper()}]")
        conf = f" (confidence: {entry.confidence:.0%})" if entry.confidence < 1.0 else ""
        lines.append(f"  {entry.key}: {entry.value}{conf}")
    return "\n".join(lines)
