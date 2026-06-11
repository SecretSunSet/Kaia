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


@pytest.mark.asyncio
async def test_register_peer_intent_explicit_raises_without_bus():
    """The explicit register_peer_intent method must fail-loud if bus is None,
    matching peer_call's contract."""
    agent = _StubAgent(ai_engine=MagicMock())

    async def dummy(env: Envelope) -> dict:
        return {}

    with pytest.raises(PeerCallError):
        agent.register_peer_intent("never", dummy)


@pytest.mark.asyncio
async def test_agent_constructed_before_set_bus_has_no_handlers_registered():
    """If an agent is instantiated BEFORE the bus is set, the
    _register_peer_intents hook does NOT run. The agent constructs
    successfully but handlers aren't bound; callers must use
    register_peer_intent explicitly after set_bus to recover."""
    # Bus is None at this point (autouse fixture).
    agent = _StubAgent(ai_engine=MagicMock())
    assert agent.received == []

    # Now set bus AFTER agent constructed.
    tx = InMemoryBusTransport()
    bus = Bus(transport=tx, default_timeout=1.0)
    BaseAgent.set_bus(bus)
    await bus.start()
    try:
        # Send a request to "stub" — no handler is bound, so the bus
        # returns a 'no handler' error which surfaces as PeerCallError.
        with pytest.raises(PeerCallError):
            await bus.peer_call(
                source="other", target="stub", intent="echo",
                payload={"q": "hi"}, user_id=uuid4(),
            )
        assert agent.received == []  # confirms no handler ran
    finally:
        await bus.shutdown()


@pytest.mark.asyncio
async def test_class_slot_is_shared_across_agent_instances():
    """All BaseAgent subclasses share the same _bus class slot — that's
    the whole point of using a classmethod for injection."""
    sentinel = MagicMock()
    BaseAgent.set_bus(sentinel)

    class _OtherStub(BaseAgent):
        channel_id = "other_stub"

        async def handle(self, user, message, channel):
            return None

    a1 = _StubAgent(ai_engine=MagicMock())
    a2 = _OtherStub(ai_engine=MagicMock())
    assert a1._bus is sentinel
    assert a2._bus is sentinel
    assert a1._bus is a2._bus


@pytest.mark.asyncio
async def test_peer_call_default_visibility_is_user_visible():
    """peer_call defaults visibility to USER_VISIBLE via the lazy import path.
    Confirms the default is correctly forwarded to bus.peer_call (not None)."""
    bus = MagicMock()
    bus.peer_call = AsyncMock(return_value={"ok": True})
    BaseAgent.set_bus(bus)
    agent = _StubAgent(ai_engine=MagicMock())
    await agent.peer_call("other", "echo", {}, user_id=uuid4())
    # Visibility kwarg must be USER_VISIBLE (not None / not missing).
    forwarded_visibility = bus.peer_call.await_args.kwargs["visibility"]
    assert forwarded_visibility is Visibility.USER_VISIBLE
