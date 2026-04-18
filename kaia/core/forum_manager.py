"""Forum topics manager — maps Telegram forum threads to expert channels."""

from __future__ import annotations

from loguru import logger
from telegram import Bot
from telegram.error import BadRequest, TelegramError

from config.constants import (
    CHANNEL_GENERAL,
    CHANNEL_HEVN,
    CHANNEL_KAZUKI,
    CHANNEL_AKABANE,
    CHANNEL_MAKUBEX,
)
from database.queries import (
    save_forum_topic_mapping,
    get_forum_topic_mappings,
    get_forum_mapping_by_topic,
    get_forum_mapping_by_channel,
    delete_forum_topic_mappings,
)


# Topics created for each expert (General already exists by default in Telegram).
_EXPERT_TOPICS: list[tuple[str, str]] = [
    (CHANNEL_HEVN, "💰 Hevn — Financial Advisor"),
    (CHANNEL_KAZUKI, "📈 Kazuki — Investment Manager"),
    (CHANNEL_AKABANE, "⚔️ Akabane — Trading Strategist"),
    (CHANNEL_MAKUBEX, "🔧 MakubeX — Tech Lead"),
]


class ForumSetupError(Exception):
    """Raised when forum topic creation fails (permissions, API errors)."""

    def __init__(self, message: str, is_permission_error: bool = False) -> None:
        super().__init__(message)
        self.is_permission_error = is_permission_error


class ForumManager:
    """Manages Telegram Forum Topics for expert channels."""

    async def setup_forum_topics(self, bot: Bot, chat_id: int) -> dict[str, int]:
        """Create forum topics for each expert in a group chat.

        Raises:
            ForumSetupError: on permission or Telegram API error. If
                ``is_permission_error`` is True the bot lacks 'Manage Topics'.
        """
        mappings: dict[str, int] = {}
        for channel_id, topic_name in _EXPERT_TOPICS:
            try:
                topic = await bot.create_forum_topic(chat_id=chat_id, name=topic_name)
            except BadRequest as exc:
                msg = str(exc)
                if "not enough rights" in msg.lower() or "topic_name_invalid" in msg.lower():
                    raise ForumSetupError(msg, is_permission_error=True) from exc
                raise ForumSetupError(msg) from exc
            except TelegramError as exc:
                raise ForumSetupError(str(exc)) from exc

            topic_id = topic.message_thread_id
            await save_forum_topic_mapping(chat_id, channel_id, topic_id)
            mappings[channel_id] = topic_id
            logger.info(
                "Created forum topic: chat={} channel={} topic_id={}",
                chat_id, channel_id, topic_id,
            )

        return mappings

    async def get_channel_for_topic(
        self, chat_id: int, topic_id: int | None
    ) -> str | None:
        """Return channel_id for a topic. General topic (None/1) → 'general'.
        Returns None if topic_id is set but unmapped.
        """
        if topic_id is None or topic_id == 1:
            return CHANNEL_GENERAL
        mapping = await get_forum_mapping_by_topic(chat_id, topic_id)
        return mapping.channel_id if mapping else None

    async def get_topic_for_channel(
        self, chat_id: int, channel_id: str
    ) -> int | None:
        """Return the topic_id for a channel in this group, or None."""
        if channel_id == CHANNEL_GENERAL:
            return None
        mapping = await get_forum_mapping_by_channel(chat_id, channel_id)
        return mapping.topic_id if mapping else None

    async def is_forum_setup(self, chat_id: int) -> bool:
        """Check whether any expert topics have been created for this group."""
        mappings = await get_forum_topic_mappings(chat_id)
        return len(mappings) > 0

    async def load_topic_mappings(self, chat_id: int) -> dict[str, int]:
        """Load all (channel_id → topic_id) mappings for a group chat."""
        mappings = await get_forum_topic_mappings(chat_id)
        return {m.channel_id: m.topic_id for m in mappings}

    async def clear_mappings(self, chat_id: int) -> None:
        """Delete all mappings for a chat (e.g. after bot was removed)."""
        await delete_forum_topic_mappings(chat_id)
