"""Placeholder expert — responds using the channel's persona with no specialized skills."""

from __future__ import annotations

from loguru import logger

from core.ai_engine import AIResponse, build_message_history
from database.models import Channel, User
from database.queries import get_channel_profile
from experts.base import BaseExpert
from skills.base import SkillResult


class PlaceholderExpert(BaseExpert):
    """Generic expert that uses the channel's persona from DB.

    All commands work immediately — the expert responds in character.
    Skills get added when each expert's full phase is built.
    """

    async def handle(
        self,
        user: User,
        message: str,
        channel: Channel,
    ) -> SkillResult:
        """Handle a message in this expert's channel."""
        # 1. Load channel conversation history
        history = await self.get_conversation_history(user.id, channel.channel_id)

        # 2. Load combined context (global profile + channel profile)
        combined_context = await self._channel_mem.load_combined_context(
            user.id, channel.channel_id
        )

        # 3. Check if first visit → generate onboarding
        if await self._channel_mgr.is_first_visit(user.id, channel.channel_id):
            onboarding_text = await self.generate_onboarding(
                user, channel, combined_context
            )
            footer = self.format_response_footer(channel)

            # Save the onboarding exchange to channel history
            await self.save_messages(
                user.id, channel.channel_id, message, onboarding_text
            )

            return SkillResult(
                text=f"{onboarding_text}{footer}",
                skill_name=channel.channel_id,
            )

        # 4. Build system prompt
        system_prompt = self._build_system_prompt(channel, combined_context)

        # 5. Inject knowledge gap question if needed
        channel_entries = await get_channel_profile(user.id, channel.channel_id)
        top_gap = self._channel_mem.get_top_gap(channel.channel_id, channel_entries)
        if top_gap:
            system_prompt += (
                f"\n\nKNOWLEDGE GAP: You still need to learn the user's "
                f"{top_gap['key'].replace('_', ' ')}. Work ONE natural question "
                f"about it into your response if appropriate. Never ask more than "
                f"one question per response."
            )

        # 6. Call AI
        messages = build_message_history(history, message)
        ai_response = await self.ai.chat(
            system_prompt=system_prompt,
            messages=messages,
        )

        # 7. Add footer
        footer = self.format_response_footer(channel)
        full_text = f"{ai_response.text}{footer}"

        # 8. Save conversation to channel history
        await self.save_messages(
            user.id, channel.channel_id, message, ai_response.text
        )

        # 9. Fire background extraction
        updated_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": ai_response.text},
        ]
        self.run_background_extraction(user.id, channel.channel_id, updated_history)

        return SkillResult(
            text=full_text,
            skill_name=channel.channel_id,
            ai_response=ai_response,
        )

    def _build_system_prompt(
        self,
        channel: Channel,
        combined_context: str,
    ) -> str:
        """Build the full system prompt from channel persona + user context."""
        return (
            f"{channel.system_prompt}\n\n"
            f"USER CONTEXT:\n{combined_context}\n\n"
            f"IMPORTANT RULES:\n"
            f"- Be concise. Keep responses focused and useful.\n"
            f"- Stay in character as {channel.character_name} at all times.\n"
            f"- Use markdown formatting sparingly — Telegram supports basic markdown.\n"
            f"- Default currency is Philippine Peso (₱) unless told otherwise.\n"
            f"- Default timezone is Asia/Manila unless told otherwise.\n"
            f"- Ask at most ONE question per response to learn about the user.\n"
            f"- Never break character or mention that you are an AI/placeholder."
        )
