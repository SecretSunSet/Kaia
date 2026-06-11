"""Tests for BaseAgent.peer_call + register_peer_intent + set_bus (R-3)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent_runtime.base_agent import BaseAgent, PeerCallError, PeerCallTimeoutError
from bus import Envelope, InMemoryBusTransport, Visibility
from bus.bus import Bus
from skills.base import SkillResult


class _StubAgent(BaseAgent):
    channel_id = "stub"

    def __init__(self, ai_engine):
        super().__init__(ai_engine)
        self.received: list[Envelope] = []

    def _register_peer_intents(self) -> None:
        if self._bus is not None:
            self._bus.register_handler(self.agent_id, "echo", self._handle_echo)

    async def _handle_echo(self, env: Envelope) -> dict:
        self.received.append(env)
        return {"echoed": env.payload.get("q")}

    async def handle(self, user, message, channel) -> SkillResult:
        return SkillResult(text="ignored", skill_name="stub")


@pytest.fixture(autouse=True)
def _reset_base_agent_bus():
    """Each test gets a clean BaseAgent._bus class slot."""
    BaseAgent.set_bus(None)
    yield
    BaseAgent.set_bus(None)


@pytest.mark.asyncio
async def test_peer_call_raises_without_bus():
    """If set_bus(None), peer_call must raise — never silently succeed."""
    agent = _StubAgent(ai_engine=MagicMock())
    with pytest.raises(PeerCallError) as exc:
        await agent.peer_call("other", "echo", {"q": "x"}, user_id=uuid4())
    assert "bus" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_register_peer_intent_via_subclass_hook():
    tx = InMemoryBusTransport()
    bus = Bus(transport=tx, default_timeout=1.0)
    BaseAgent.set_bus(bus)
    agent = _StubAgent(ai_engine=MagicMock())
    await bus.start()
    try:
        reply = await bus.peer_call(
            source="other", target="stub", intent="echo",
            payload={"q": "hi"}, user_id=uuid4(),
        )
        assert reply == {"echoed": "hi"}
        assert len(agent.received) == 1
    finally:
        await bus.shutdown()


@pytest.mark.asyncio
async def test_peer_call_delegates_to_bus_and_returns_payload():
    bus = MagicMock()
    bus.peer_call = AsyncMock(return_value={"ok": True})
    BaseAgent.set_bus(bus)
    agent = _StubAgent(ai_engine=MagicMock())
    result = await agent.peer_call("other", "echo", {"q": "x"}, user_id=uuid4())
    bus.peer_call.assert_awaited_once()
    assert bus.peer_call.await_args.kwargs["source"] == "stub"
    assert bus.peer_call.await_args.kwargs["target"] == "other"
    assert bus.peer_call.await_args.kwargs["intent"] == "echo"
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_peer_call_propagates_timeout():
    bus = MagicMock()
    bus.peer_call = AsyncMock(side_effect=PeerCallTimeoutError("boom"))
    BaseAgent.set_bus(bus)
    agent = _StubAgent(ai_engine=MagicMock())
    with pytest.raises(PeerCallTimeoutError):
        await agent.peer_call("other", "echo", {"q": "x"}, user_id=uuid4())
