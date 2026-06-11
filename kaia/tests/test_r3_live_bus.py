"""Env-gated live integration test: runs PostgresBusTransport against a
real Postgres if R3_INTEGRATION_DB_DSN is set. Otherwise SKIPPED.

To run locally:
  R3_INTEGRATION_DB_DSN="postgresql://user:pass@host:5432/db" \
    python3 -m pytest tests/test_r3_live_bus.py -q
"""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from bus import Bus, Envelope, PostgresBusTransport, Visibility

DSN = os.environ.get("R3_INTEGRATION_DB_DSN")
pytestmark = pytest.mark.skipif(DSN is None, reason="R3_INTEGRATION_DB_DSN not set")


@pytest.mark.asyncio
async def test_live_notify_round_trip():
    """Publish on a test channel, subscribe, and verify the payload arrives."""
    assert DSN is not None
    tx = PostgresBusTransport(DSN)
    await tx.start()
    received: list[str] = []
    async def watcher():
        async for payload in tx.subscribe("r3:integration-test"):
            received.append(payload)
            return
    task = asyncio.create_task(watcher())
    await asyncio.sleep(0.2)  # let LISTEN register
    await tx.publish("r3:integration-test", "hello")
    await asyncio.wait_for(task, timeout=5.0)
    assert received == ["hello"]
    await tx.shutdown()


@pytest.mark.asyncio
async def test_live_peer_call_round_trip():
    """Full peer_call round-trip with two handlers on the live bus."""
    assert DSN is not None
    tx = PostgresBusTransport(DSN)
    await tx.start()
    bus = Bus(transport=tx, default_timeout=5.0)

    async def echo(env: Envelope) -> dict:
        return {"echo": env.payload["q"]}

    bus.register_handler("makubex", "echo", echo)
    await bus.start()
    try:
        reply = await bus.peer_call(
            source="hevn", target="makubex", intent="echo",
            payload={"q": "live"}, user_id=uuid4(),
        )
        assert reply == {"echo": "live"}
    finally:
        await bus.shutdown()
        await tx.shutdown()
