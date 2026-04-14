"""Memory skill handler — profile queries and explicit fact storage."""

from __future__ import annotations

import json
import re

from loguru import logger

from core.ai_engine import AIEngine, build_message_history
from database.models import User
from database.queries import upsert_profile_entry, add_memory_log
from skills.base import BaseSkill, SkillResult
from skills.memory.prompts import build_memory_query_prompt, build_memory_store_prompt


class MemorySkill(BaseSkill):
    """Handles 'What do you know about me?' and 'Remember that...' requests."""

    name = "memory"

    def __init__(self, ai_engine: AIEngine) -> None:
        super().__init__(ai_engine)

    async def handle(
        self,
        user: User,
        message: str,
        conversation_history: list[dict[str, str]],
        profile_context: str,
    ) -> SkillResult:
        # Detect whether this is a store request or a query
        if _is_store_request(message):
            return await self._handle_store(user, message, conversation_history, profile_context)
        return await self._handle_query(user, message, conversation_history, profile_context)

    async def _handle_query(
        self,
        user: User,
        message: str,
        conversation_history: list[dict[str, str]],
        profile_context: str,
    ) -> SkillResult:
        """User asks what KAIA knows about them."""
        system_prompt = build_memory_query_prompt(profile_context)
        messages = build_message_history(conversation_history, message)

        ai_resp = await self.ai.chat(system_prompt=system_prompt, messages=messages)

        return SkillResult(text=ai_resp.text, skill_name=self.name, ai_response=ai_resp)

    async def _handle_store(
        self,
        user: User,
        message: str,
        conversation_history: list[dict[str, str]],
        profile_context: str,
    ) -> SkillResult:
        """User explicitly tells KAIA to remember something."""
        system_prompt = build_memory_store_prompt(profile_context)
        messages = build_message_history(conversation_history, message)

        ai_resp = await self.ai.chat(system_prompt=system_prompt, messages=messages)

        # Extract and save facts from <memory> tags
        response_text = ai_resp.text
        facts = _extract_memory_tags(response_text)

        if facts:
            for fact in facts:
                try:
                    await upsert_profile_entry(
                        user_id=user.id,
                        category=fact["category"],
                        key=fact["key"],
                        value=fact["value"],
                        confidence=fact.get("confidence", 1.0),
                        source="explicit",
                    )
                    await add_memory_log(
                        user_id=user.id,
                        session_id="explicit",
                        fact=f"[{fact['category']}] {fact['key']}: {fact['value']}",
                        fact_type=fact.get("fact_type", "general"),
                    )
                except Exception as exc:
                    logger.warning("Failed to save explicit memory: {}", exc)

            logger.info("Stored {} explicit memory entries for user {}", len(facts), user.id)

        # Remove <memory> tags from the visible response
        clean_text = re.sub(r"<memory>.*?</memory>", "", response_text, flags=re.DOTALL).strip()

        return SkillResult(text=clean_text, skill_name=self.name, ai_response=ai_resp)


def _is_store_request(message: str) -> bool:
    """Heuristic: does this message ask KAIA to remember/store something?"""
    lower = message.lower()
    store_patterns = [
        "remember that",
        "remember my",
        "remember i",
        "don't forget",
        "note that",
        "keep in mind",
        "save that",
        "store that",
        "my name is",
        "i go by",
        "call me",
    ]
    return any(pattern in lower for pattern in store_patterns)


def _extract_memory_tags(text: str) -> list[dict]:
    """Parse facts from <memory>...</memory> tags in the AI response."""
    match = re.search(r"<memory>(.*?)</memory>", text, flags=re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        logger.warning("Failed to parse <memory> tag content as JSON")
        return []
