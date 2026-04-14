"""Post-conversation fact extraction — runs in background after each exchange."""

from __future__ import annotations

import json
import uuid

from loguru import logger

from core.ai_engine import AIEngine
from database.queries import (
    get_user_profile,
    upsert_profile_entry,
    add_memory_log,
)
from skills.memory.prompts import build_extraction_prompt


async def extract_and_save(
    ai_engine: AIEngine,
    user_id: str,
    conversation_messages: list[dict[str, str]],
) -> int:
    """Run the memory extraction pipeline on recent conversation.

    Args:
        ai_engine: The shared AI engine.
        user_id: DB user ID.
        conversation_messages: Recent messages [{role, content}, ...].

    Returns:
        Number of new/updated profile entries saved.
    """
    if len(conversation_messages) < 2:
        return 0  # Need at least one exchange

    # Load current profile so the AI knows what's already stored
    profile_entries = await get_user_profile(user_id)
    profile_summary = ""
    if profile_entries:
        profile_summary = "\n".join(
            f"- [{e.category}] {e.key}: {e.value}" for e in profile_entries
        )

    # Build the extraction prompt
    system_prompt = build_extraction_prompt()

    # Format the conversation for the AI
    convo_text = "\n".join(
        f"{'User' if m['role'] == 'user' else 'KAIA'}: {m['content']}"
        for m in conversation_messages[-10:]  # last 10 messages max
    )

    user_message = (
        f"EXISTING PROFILE:\n{profile_summary or '(empty — new user)'}\n\n"
        f"CONVERSATION:\n{convo_text}\n\n"
        "Extract any new facts as a JSON array:"
    )

    try:
        response = await ai_engine.chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=512,
        )

        facts = _parse_facts(response.text)
        if not facts:
            logger.debug("Memory extraction: no new facts found")
            return 0

        session_id = str(uuid.uuid4())[:8]
        saved = 0

        for fact in facts:
            try:
                await upsert_profile_entry(
                    user_id=user_id,
                    category=fact["category"],
                    key=fact["key"],
                    value=fact["value"],
                    confidence=fact.get("confidence", 0.5),
                    source=fact.get("source", "inferred"),
                )
                await add_memory_log(
                    user_id=user_id,
                    session_id=session_id,
                    fact=f"[{fact['category']}] {fact['key']}: {fact['value']}",
                    fact_type=fact.get("fact_type", "general"),
                )
                saved += 1
            except Exception as exc:
                logger.warning("Failed to save fact {}: {}", fact.get("key"), exc)

        logger.info(
            "Memory extraction: saved {}/{} facts (session={})",
            saved, len(facts), session_id,
        )
        return saved

    except Exception as exc:
        logger.warning("Memory extraction failed: {}", exc)
        return 0


def _parse_facts(text: str) -> list[dict]:
    """Parse the AI response into a list of fact dicts."""
    # Try to find a JSON array in the response
    text = text.strip()

    # If the response starts with [ and ends with ], parse directly
    if text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try to find JSON array within the text
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.debug("Could not parse facts from extraction response")
    return []
