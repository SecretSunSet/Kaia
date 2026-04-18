"""Channel-specific memory manager — per-channel profiles and knowledge gap tracking."""

from __future__ import annotations

from loguru import logger

from config.constants import CHANNEL_REQUIRED_KNOWLEDGE
from database.models import ChannelProfileEntry, ProfileEntry
from database.queries import (
    get_user_profile,
    get_channel_profile,
    upsert_channel_profile,
)


class ChannelMemoryManager:
    """Manages channel-specific memory (separate from general profile)."""

    async def load_channel_profile(self, user_id: str, channel_id: str) -> str:
        """Load and format channel-specific profile entries."""
        entries = await get_channel_profile(user_id, channel_id)
        return _format_channel_profile(entries)

    async def load_combined_context(self, user_id: str, channel_id: str) -> str:
        """Build the full context string for an expert's prompt.

        Combines:
        1. Shared user profile (from existing user_profile table)
        2. Channel-specific profile (from channel_profile table)
        3. Knowledge completeness score
        """
        # Load shared profile
        global_entries = await get_user_profile(user_id)
        global_text = _format_global_profile(global_entries)

        # Load channel-specific profile
        channel_entries = await get_channel_profile(user_id, channel_id)
        channel_text = _format_channel_profile(channel_entries)

        # Knowledge score
        score_info = self.get_knowledge_score(channel_id, channel_entries)

        parts: list[str] = []
        if global_text:
            parts.append(f"SHARED USER PROFILE:\n{global_text}")
        if channel_text:
            parts.append(f"CHANNEL-SPECIFIC KNOWLEDGE:\n{channel_text}")
        parts.append(
            f"KNOWLEDGE COMPLETENESS: {score_info['score']}% "
            f"({len(score_info['known'])} of "
            f"{len(score_info['known']) + len(score_info['missing'])} items)"
        )

        return "\n\n".join(parts) if parts else "No profile data yet."

    async def update_channel_profile(
        self,
        user_id: str,
        channel_id: str,
        category: str,
        key: str,
        value: str,
        confidence: float = 0.5,
        source: str = "inferred",
    ) -> None:
        """Upsert a channel-specific profile entry."""
        await upsert_channel_profile(
            user_id, channel_id, category, key, value, confidence, source
        )

    async def batch_update_channel_profile(
        self,
        user_id: str,
        channel_id: str,
        facts: list[dict],
    ) -> int:
        """Process multiple extracted facts at once. Returns count saved."""
        saved = 0
        for fact in facts:
            try:
                await upsert_channel_profile(
                    user_id=user_id,
                    channel_id=channel_id,
                    category=fact["category"],
                    key=fact["key"],
                    value=fact["value"],
                    confidence=fact.get("confidence", 0.5),
                    source=fact.get("source", "inferred"),
                )
                saved += 1
            except Exception as exc:
                logger.warning("Failed to save channel fact {}: {}", fact.get("key"), exc)
        return saved

    def get_knowledge_gaps(
        self,
        channel_id: str,
        existing_entries: list[ChannelProfileEntry],
    ) -> list[dict]:
        """Compare known facts vs required facts for this channel.

        Returns list of gaps sorted by priority.
        """
        required = CHANNEL_REQUIRED_KNOWLEDGE.get(channel_id, [])
        if not required:
            return []

        known_keys = {(e.category, e.key) for e in existing_entries}
        gaps = []
        for category, key, priority, question in required:
            if (category, key) not in known_keys:
                gaps.append({
                    "category": category,
                    "key": key,
                    "priority": priority,
                    "question": question,
                })
        gaps.sort(key=lambda g: g["priority"])
        return gaps

    def get_knowledge_score(
        self,
        channel_id: str,
        existing_entries: list[ChannelProfileEntry],
    ) -> dict:
        """Returns knowledge completeness.

        {"score": 45, "known": [...], "missing": [...]}
        """
        required = CHANNEL_REQUIRED_KNOWLEDGE.get(channel_id, [])
        if not required:
            return {"score": 100, "known": [], "missing": []}

        known_keys = {(e.category, e.key) for e in existing_entries}
        known = []
        missing = []
        for category, key, priority, question in required:
            if (category, key) in known_keys:
                known.append(key)
            else:
                missing.append(key)

        total = len(required)
        score = int((len(known) / total) * 100) if total > 0 else 100
        return {"score": score, "known": known, "missing": missing}

    def get_top_gap(
        self,
        channel_id: str,
        existing_entries: list[ChannelProfileEntry],
    ) -> dict | None:
        """Get the single highest-priority missing piece of knowledge."""
        gaps = self.get_knowledge_gaps(channel_id, existing_entries)
        return gaps[0] if gaps else None


def _format_global_profile(entries: list[ProfileEntry]) -> str:
    """Format the shared user profile entries."""
    if not entries:
        return ""
    lines: list[str] = []
    current_cat = ""
    for entry in sorted(entries, key=lambda e: e.category):
        if entry.category != current_cat:
            current_cat = entry.category
            lines.append(f"[{current_cat.upper()}]")
        conf = f" (confidence: {entry.confidence:.0%})" if entry.confidence < 1.0 else ""
        lines.append(f"  {entry.key}: {entry.value}{conf}")
    return "\n".join(lines)


def _format_channel_profile(entries: list[ChannelProfileEntry]) -> str:
    """Format channel-specific profile entries."""
    if not entries:
        return ""
    lines: list[str] = []
    current_cat = ""
    for entry in sorted(entries, key=lambda e: e.category):
        if entry.category != current_cat:
            current_cat = entry.category
            lines.append(f"[{current_cat.upper()}]")
        conf = f" (confidence: {entry.confidence:.0%})" if entry.confidence < 1.0 else ""
        lines.append(f"  {entry.key}: {entry.value}{conf}")
    return "\n".join(lines)
