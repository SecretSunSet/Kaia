"""Base class for all KAIA agents — supersedes experts.base.BaseExpert."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING
from uuid import UUID

from loguru import logger

if TYPE_CHECKING:
    from bus.bus import Bus, PeerIntentHandler

from agent_runtime.context import AgentContext
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


class PeerCallError(Exception):
    """Base error for failures in BaseAgent.peer_call (R-3)."""


class PeerCallTimeoutError(PeerCallError):
    """Raised when a peer_call exceeds its timeout budget (R-3)."""


class BaseAgent(ABC):
    """Base class for all KAIA agents.

    Backwards-compatible with the former `BaseExpert`: subclasses set
    `channel_id` and implement `handle(user, message, channel)`. The new
    `agent_id` property is a stable alias for `channel_id` going forward.
    """

    # Subclasses set this. `agent_id` reads it; both names are supported.
    channel_id: str = ""

    # Class-level bus slot — set once by the bot at post_init via BaseAgent.set_bus(bus).
    # Class-level (not instance-level) so all agent instances share the same bus
    # without needing the get_expert(...) factory to thread it.
    _bus: "Bus | None" = None  # noqa: F821  (Bus imported lazily in peer_call to avoid cycle)

    @classmethod
    def set_bus(cls, bus: "Bus | None") -> None:
        """Inject the process-wide bus. The bot calls this once at post_init."""
        cls._bus = bus

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine
        self._channel_mgr = ChannelManager()
        self._channel_mem = ChannelMemoryManager()
        # R-3: bind inbound peer-intent handlers if a bus is available.
        if self._bus is not None:
            self._register_peer_intents()

    # ── Identity ────────────────────────────────────────────────────

    @property
    def agent_id(self) -> str:
        """Stable name for this agent. Aliases `channel_id` during the
        BaseExpert → BaseAgent migration."""
        return self.channel_id

    # ── Handlers ────────────────────────────────────────────────────

    @abstractmethod
    async def handle(
        self,
        user: User,
        message: str,
        channel: Channel,
    ) -> SkillResult:
        """Handle a user message. Existing subclasses already implement this."""
        ...

    async def handle_turn(self, ctx: AgentContext) -> SkillResult:
        """Context-object handler. Default impl delegates to `handle()` so
        existing subclasses keep working without changes. R-3 callers
        (the bus) will use this entry point so conversation_id and
        visibility are preserved."""
        return await self.handle(ctx.user, ctx.message, ctx.channel)

    # ── Peer-to-peer (R-3) ─────────────────────────────────────────

    def _register_peer_intents(self) -> None:
        """Override in subclasses to register inbound peer-intent handlers
        via self._bus.register_handler(self.agent_id, intent, async_handler)."""
        pass

    def register_peer_intent(self, intent: str, handler: "PeerIntentHandler") -> None:
        """Register an inbound peer-intent handler on the bus."""
        if self._bus is None:
            raise PeerCallError("register_peer_intent requires the bus to be initialised")
        self._bus.register_handler(self.agent_id, intent, handler)

    async def peer_call(
        self,
        target_agent_id: str,
        intent: str,
        payload: dict[str, Any],
        *,
        user_id: UUID,
        visibility=None,  # bus.Visibility, optional
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a request to another agent; await its reply payload.

        Raises:
            PeerCallTimeoutError: budget exhausted.
            PeerCallError: peer raised, or bus not initialised.
        """
        if self._bus is None:
            raise PeerCallError(
                "peer_call requires the bus to be initialised — "
                "bot post_init did not call BaseAgent.set_bus(bus)"
            )
        # Lazy import to avoid bus → agent_runtime → bus cycle at module load.
        from bus import Visibility as _Visibility
        # NOTE(R-4): conversation_id is not forwarded — each BaseAgent.peer_call
        # starts a new conversation on the bus. Multi-hop consults (e.g.
        # MakubeX → Kazuki while answering Hevn) will need this threaded
        # through; not in scope for R-3.
        return await self._bus.peer_call(
            source=self.agent_id,
            target=target_agent_id,
            intent=intent,
            payload=payload,
            user_id=user_id,
            visibility=visibility if visibility is not None else _Visibility.USER_VISIBLE,
            timeout=timeout,
        )

    # ── History / persistence (verbatim from BaseExpert) ───────────

    async def get_conversation_history(
        self,
        user_id: str,
        channel_id: str,
        limit: int = 20,
        user_timezone: str | None = None,
    ) -> list[dict[str, str]]:
        """Load recent channel-specific conversation history.

        Each message's content is prefixed with a relative-time tag
        (e.g. "[3 days ago] ...") so the agent can reason about *when*
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
        """Generate the first-time onboarding message for this agent."""
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
