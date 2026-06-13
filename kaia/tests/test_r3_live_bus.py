"""Env-gated live integration test: runs PostgresBusTransport against a
real Postgres if R3_INTEGRATION_DB_DSN is set. Otherwise SKIPPED.

Prerequisite: migration kaia/database/migrations/006_agent_bus.sql must
be applied to the target database first (creates agent_conversations
and agent_messages tables). Without it, test_live_peer_call_round_trip
will fail with a relation-not-found error.

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
    try:
        received: list[str] = []
        async def watcher():
            async for payload in tx.subscribe("r3:integration-test"):
                received.append(payload)
                return
        task = asyncio.create_task(watcher())
        await asyncio.sleep(0.5)  # let LISTEN register (generous for remote Postgres)
        await tx.publish("r3:integration-test", "hello")
        await asyncio.wait_for(task, timeout=5.0)
        assert received == ["hello"]
    finally:
        await tx.shutdown()


@pytest.mark.asyncio
async def test_live_peer_call_round_trip():
    """Full peer_call round-trip with two handlers on the live bus.

    Uses a test-owned conversation_id so we can DELETE all rows
    created by this test before shutdown — keeps the operator's
    staging database clean across repeated runs."""
    assert DSN is not None
    tx = PostgresBusTransport(DSN)
    await tx.start()
    bus = Bus(transport=tx, default_timeout=5.0)

    async def echo(env: Envelope) -> dict:
        return {"echo": env.payload["q"]}

    bus.register_handler("makubex", "echo", echo)
    await bus.start()

    test_conv_id = uuid4()
    test_user_id = uuid4()
    try:
        reply = await bus.peer_call(
            source="hevn", target="makubex", intent="echo",
            payload={"q": "live"}, user_id=test_user_id,
            conversation_id=test_conv_id,
        )
        assert reply == {"echo": "live"}
    finally:
        await bus.shutdown()
        # Cleanup: delete this test's conversation (CASCADEs to agent_messages).
        # Best-effort — log via assert helpers, don't fail the test on cleanup error.
        try:
            await tx.execute(
                "DELETE FROM agent_conversations WHERE conversation_id = $1",
                test_conv_id,
            )
        except Exception:
            pass  # cleanup failure should not mask a passing/failing test result
        await tx.shutdown()
