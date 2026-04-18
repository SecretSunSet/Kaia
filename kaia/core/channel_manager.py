"""Channel state manager — handles switching between expert channels."""

from __future__ import annotations

from loguru import logger

from config.constants import CHANNEL_GENERAL
from database.models import Channel
from database.queries import (
    get_user_channel_state,
    set_user_channel_state,
    get_channel_by_id,
    get_all_active_channels,
    count_channel_conversations,
)


class ChannelManager:
    """Manages user channel state and switching."""

    async def get_active_channel(self, user_id: str) -> str:
        """Get user's current active channel. Returns 'general' if none set."""
        return await get_user_channel_state(user_id)

    async def switch_channel(self, user_id: str, channel_id: str) -> Channel:
        """Switch user to a different channel. Returns channel info.

        Raises:
            ValueError: If channel_id does not exist or is inactive.
        """
        channel = await get_channel_by_id(channel_id)
        if channel is None:
            raise ValueError(f"Channel '{channel_id}' not found")
        await set_user_channel_state(user_id, channel_id)
        logger.info("User {} switched to channel '{}'", user_id, channel_id)
        return channel

    async def exit_channel(self, user_id: str) -> None:
        """Return user to general KAIA channel."""
        await set_user_channel_state(user_id, CHANNEL_GENERAL)
        logger.info("User {} returned to general channel", user_id)

    async def get_channel_info(self, channel_id: str) -> Channel | None:
        """Get channel definition (name, personality, system_prompt) from DB."""
        return await get_channel_by_id(channel_id)

    async def get_all_channels(self) -> list[Channel]:
        """Get all active channels for /team command."""
        return await get_all_active_channels()

    async def is_first_visit(self, user_id: str, channel_id: str) -> bool:
        """Check if user has ever talked to this expert (for onboarding)."""
        count = await count_channel_conversations(user_id, channel_id)
        return count == 0
