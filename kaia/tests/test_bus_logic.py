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
async def test_bus_records_insert_then_notify():
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
