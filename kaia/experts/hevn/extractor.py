"""Hevn-specific memory extractor.

Extends the generic channel extraction with a mirror step: when Hevn learns
income/debt/major financial facts, they are also written to the shared
`user_profile` table under the `finances` category so other experts
(Kazuki, etc.) can see them later.
"""

from __future__ import annotations

from loguru import logger

from core.ai_engine import AIEngine
from core.channel_extractor import channel_extract_and_save
from database.queries import get_channel_profile, upsert_profile_entry


# Channel categories whose facts also belong in the shared user profile.
_MIRROR_CATEGORIES: set[str] = {
    "income_info",
    "debt_info",
    "savings",
    "retirement",
    "insurance",
    "goals",
}


async def hevn_extract_and_save(
    ai_engine: AIEngine,
    user_id: str,
    conversation_messages: list[dict[str, str]],
) -> int:
    """Run Hevn's domain extraction and mirror high-signal facts.

    Returns the count of channel-profile entries saved (same semantics as
    ``channel_extract_and_save``). Mirror writes happen best-effort and are
    not counted.
    """
    saved = await channel_extract_and_save(
        ai_engine=ai_engine,
        user_id=user_id,
        channel_id="hevn",
        conversation_messages=conversation_messages,
    )

    if saved <= 0:
        return saved

    try:
        entries = await get_channel_profile(user_id, "hevn")
    except Exception as exc:
        logger.warning("Hevn mirror: failed to reload channel profile: {}", exc)
        return saved

    for entry in entries:
        if entry.category not in _MIRROR_CATEGORIES:
            continue
        try:
            await upsert_profile_entry(
                user_id=user_id,
                category="finances",
                key=entry.key,
                value=entry.value,
                confidence=entry.confidence,
                source=entry.source,
            )
        except Exception as exc:
            logger.debug("Hevn mirror skipped {}: {}", entry.key, exc)

    return saved
