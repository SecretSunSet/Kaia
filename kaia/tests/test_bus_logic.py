"""Bus logic tests — uses InMemoryBusTransport, no asyncpg."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from agent_runtime.base_agent import PeerCallError, PeerCallTimeoutError
from bus import Bus, Envelope, InMemoryBusTransport, Visibility


def _user_id() -> UUID:
    return uuid4()


async def _start_bus_with_handlers(handlers: dict[tuple[str, str], callable]) -> tuple[Bus, InMemoryBusTransport]:
    """Helper: build a Bus with the in-memory transport, register agent-intent handlers,
    start the dispatcher tasks for every agent that has at least one handler."""
    tx = InMemoryBusTransport()
    bus = Bus(transport=tx, default_timeout=1.0)
    for (agent_id, intent), handler in handlers.items():
        bus.register_handler(agent_id, intent, handler)
    await bus.start()
    return bus, tx


@pytest.mark.asyncio
async def test_peer_call_round_trip_success():
    async def makubex_handler(env: Envelope) -> dict:
        assert env.intent == "smart_contract_risk"
        return {"rating": "low-to-moderate", "protocol": env.payload["protocol"]}

    bus, tx = await _start_bus_with_handlers({("makubex", "smart_contract_risk"): makubex_handler})
    try:
        reply = await bus.peer_call(
            source="hevn",
            target="makubex",
            intent="smart_contract_risk",
            payload={"protocol": "Aave"},
            user_id=_user_id(),
        )
        assert reply == {"rating": "low-to-moderate", "protocol": "Aave"}
    finally:
        await bus.shutdown()


@pytest.mark.asyncio
async def test_peer_call_timeout_raises():
    async def slow_handler(env: Envelope) -> dict:
        await asyncio.sleep(10)
        return {}

    bus, _ = await _start_bus_with_handlers({("makubex", "any"): slow_handler})
    try:
        with pytest.raises(PeerCallTimeoutError):
            await bus.peer_call(
                source="hevn", target="makubex", intent="any",
                payload={}, user_id=_user_id(), timeout=0.05,
            )
    finally:
        await bus.shutdown()


@pytest.mark.asyncio
async def test_peer_call_peer_error_raises_peer_call_error():
    async def boom_handler(env: Envelope) -> dict:
        raise RuntimeError("makubex exploded")

    bus, _ = await _start_bus_with_handlers({("makubex", "any"): boom_handler})
    try:
        with pytest.raises(PeerCallError) as exc:
            await bus.peer_call(
                source="hevn", target="makubex", intent="any",
                payload={}, user_id=_user_id(),
            )
        assert "makubex exploded" in str(exc.value)
    finally:
        await bus.shutdown()


@pytest.mark.asyncio
async def test_two_in_flight_calls_dont_cross_correlate():
    async def echo_handler(env: Envelope) -> dict:
        await asyncio.sleep(0.01)
        return {"echo": env.payload["q"]}

    bus, _ = await _start_bus_with_handlers({("makubex", "echo"): echo_handler})
    try:
        results = await asyncio.gather(
            bus.peer_call("hevn", "makubex", "echo", {"q": "one"}, _user_id()),
            bus.peer_call("hevn", "makubex", "echo", {"q": "two"}, _user_id()),
        )
        echoes = sorted(r["echo"] for r in results)
        assert echoes == ["one", "two"]
    finally:
        await bus.shutdown()


@pytest.mark.asyncio
async def test_user_visible_envelopes_published_on_user_visible_channel():
    async def makubex_handler(env: Envelope) -> dict:
        return {"ok": True}

    bus, tx = await _start_bus_with_handlers({("makubex", "x"): makubex_handler})
    received_ids: list[str] = []

    async def watcher():
        async for payload in tx.subscribe("bus:user_visible"):
            received_ids.append(payload)
            if len(received_ids) >= 2:
                return

    watch_task = asyncio.create_task(watcher())
    await asyncio.sleep(0)
    try:
        await bus.peer_call("hevn", "makubex", "x", {}, _user_id(), visibility=Visibility.USER_VISIBLE)
        await asyncio.wait_for(watch_task, timeout=1.0)
        assert len(received_ids) == 2
    finally:
        await bus.shutdown()


@pytest.mark.asyncio
async def test_internal_visibility_does_not_publish_user_visible():
    async def makubex_handler(env: Envelope) -> dict:
        return {"ok": True}

    bus, tx = await _start_bus_with_handlers({("makubex", "x"): makubex_handler})
    received_ids: list[str] = []

    async def watcher():
        async for payload in tx.subscribe("bus:user_visible"):
            received_ids.append(payload)

    watch_task = asyncio.create_task(watcher())
    await asyncio.sleep(0)
    try:
        await bus.peer_call("hevn", "makubex", "x", {}, _user_id(), visibility=Visibility.INTERNAL)
        await asyncio.sleep(0.05)
        assert received_ids == []
    finally:
        watch_task.cancel()
        await asyncio.gather(watch_task, return_exceptions=True)
        await bus.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cancels_in_flight_futures():
    async def never_replies(env: Envelope) -> dict:
        await asyncio.sleep(60)
        return {}

    bus, _ = await _start_bus_with_handlers({("makubex", "any"): never_replies})

    async def caller():
        return await bus.peer_call(
            source="hevn", target="makubex", intent="any",
            payload={}, user_id=_user_id(), timeout=5.0,
        )

    call_task = asyncio.create_task(caller())
    await asyncio.sleep(0.01)
    await bus.shutdown()
    with pytest.raises(PeerCallError):
        await call_task


@pytest.mark.asyncio
async def test_bus_records_insert_for_request():
    """The Bus must INSERT a row into agent_messages for the request envelope.

    (Asserts on the recorded execute() sequence in InMemoryBusTransport.
    NOTIFY ordering relative to INSERT is guaranteed by the code structure
    of _persist_and_notify — see bus.py — and not separately asserted here.)
    """
    async def handler(env: Envelope) -> dict:
        return {}

    bus, tx = await _start_bus_with_handlers({("makubex", "x"): handler})
    try:
        await bus.peer_call("hevn", "makubex", "x", {}, _user_id())
        sql_sequence = [sql for sql, _ in tx.executed]
        assert any("INSERT INTO agent_messages" in s for s in sql_sequence), \
            "Bus did not INSERT the request row via transport.execute"
    finally:
        await bus.shutdown()


@pytest.mark.asyncio
async def test_peer_call_no_handler_raises_peer_call_error():
    """If the target agent has no handler for the intent, the Bus must send
    an error reply that surfaces to the caller as PeerCallError."""
    # Register a handler for a DIFFERENT intent so the target agent has a
    # dispatcher but no handler for 'missing_intent'.
    async def stub(env: Envelope) -> dict:
        return {}

    bus, _ = await _start_bus_with_handlers({("makubex", "other"): stub})
    try:
        with pytest.raises(PeerCallError) as exc:
            await bus.peer_call(
                source="hevn", target="makubex", intent="missing_intent",
                payload={}, user_id=_user_id(),
            )
        assert "no handler" in str(exc.value).lower() or "missing_intent" in str(exc.value)
    finally:
        await bus.shutdown()


@pytest.mark.asyncio
async def test_peer_call_after_shutdown_raises():
    """peer_call invoked after shutdown() must raise PeerCallError immediately."""
    async def handler(env: Envelope) -> dict:
        return {}

    bus, _ = await _start_bus_with_handlers({("makubex", "x"): handler})
    await bus.shutdown()
    with pytest.raises(PeerCallError) as exc:
        await bus.peer_call("hevn", "makubex", "x", {}, _user_id())
    assert "shutting down" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_shutdown_is_idempotent():
    """Calling shutdown() twice must not raise or hang."""
    async def handler(env: Envelope) -> dict:
        return {}

    bus, _ = await _start_bus_with_handlers({("makubex", "x"): handler})
    await bus.shutdown()
    await bus.shutdown()  # second call — guarded by _shutting_down


@pytest.mark.asyncio
async def test_dual_path_resolution_when_source_agent_has_dispatcher():
    """When the source agent ALSO has registered handlers (and thus a
    dispatcher subscribed to its own channel), the reply can arrive twice:
    once via the direct in-process path in _handle_request, once via the
    source-agent dispatcher receiving the NOTIFY. The second resolution
    must be a no-op (guarded by fut.done())."""
    async def makubex_handler(env: Envelope) -> dict:
        return {"ok": True}

    async def hevn_handler(env: Envelope) -> dict:
        return {"hevn-saw": env.payload.get("q")}

    # Both agents have handlers → both get dispatchers
    bus, _ = await _start_bus_with_handlers({
        ("makubex", "x"): makubex_handler,
        ("hevn", "y"): hevn_handler,  # unrelated to the call below; just to spawn hevn dispatcher
    })
    try:
        reply = await bus.peer_call("hevn", "makubex", "x", {}, _user_id())
        assert reply == {"ok": True}
        # Sanity: give the source dispatcher a chance to also process the reply
        # NOTIFY. The second resolution attempt must be a silent no-op.
        await asyncio.sleep(0.05)
    finally:
        await bus.shutdown()


@pytest.mark.asyncio
async def test_handler_registered_after_start_spawns_dispatcher():
    """Production ordering: bus.start() is called BEFORE any agent is
    instantiated. register_handler must dynamically spawn a dispatcher
    for the agent_id when called after start, so peer_call works.

    Without this fix, prod silently breaks: NOTIFY is published but no
    listener is registered → peer_call times out → demo fails."""
    tx = InMemoryBusTransport()
    bus = Bus(transport=tx, default_timeout=1.0)
    await bus.start()  # _handlers is empty; no dispatchers spawned by start()

    async def makubex_handler(env: Envelope) -> dict:
        return {"ok": True, "echo": env.payload.get("q")}

    # NOW register a handler — must trigger a dynamic dispatcher spawn.
    bus.register_handler("makubex", "echo", makubex_handler)

    try:
        reply = await bus.peer_call(
            source="hevn", target="makubex", intent="echo",
            payload={"q": "post-start"}, user_id=_user_id(),
        )
        assert reply == {"ok": True, "echo": "post-start"}
    finally:
        await bus.shutdown()
