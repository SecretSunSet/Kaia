"""MakubeX-specific memory extractor.

Extends the generic channel extraction by mirroring high-signal technical
facts into the shared ``user_profile`` table under the ``technical`` category
so other experts and the general KAIA channel can see them.
"""

from __future__ import annotations

from loguru import logger

from core.ai_engine import AIEngine
from core.channel_extractor import channel_extract_and_save
from database.queries import get_channel_profile, upsert_profile_entry


# Channel categories whose facts also belong in the shared user profile.
_MIRROR_CATEGORIES: set[str] = {
    "tech_stack",
    "skills",
    "projects",
    "work_context",
    "infrastructure",
}


async def makubex_extract_and_save(
    ai_engine: AIEngine,
    user_id: str,
    conversation_messages: list[dict[str, str]],
) -> int:
    """Run MakubeX's domain extraction and mirror high-signal facts.

    Returns the count of channel-profile entries saved. Mirror writes are
    best-effort and not counted.
    """
    saved = await channel_extract_and_save(
        ai_engine=ai_engine,
        user_id=user_id,
        channel_id="makubex",
        conversation_messages=conversation_messages,
    )

    if saved <= 0:
        return saved

    try:
        entries = await get_channel_profile(user_id, "makubex")
    except Exception as exc:
        logger.warning("MakubeX mirror: failed to reload channel profile: {}", exc)
        return saved

    for entry in entries:
        if entry.category not in _MIRROR_CATEGORIES:
            continue
        try:
            await upsert_profile_entry(
                user_id=user_id,
                category="technical",
                key=entry.key,
                value=entry.value,
                confidence=entry.confidence,
                source=entry.source,
            )
        except Exception as exc:
            logger.debug("MakubeX mirror skipped {}: {}", entry.key, exc)

    return saved
