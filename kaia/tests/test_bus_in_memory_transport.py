"""Tests for bus.InMemoryBusTransport — the test-only fake."""

from __future__ import annotations

import asyncio

import pytest

from bus import InMemoryBusTransport


@pytest.mark.asyncio
async def test_publish_subscribe_round_trip():
    """A message published on channel X is received by a subscriber on X."""
    tx = InMemoryBusTransport()
    received: list[str] = []

    async def subscriber():
        async for payload in tx.subscribe("agent:hevn"):
            received.append(payload)
            return

    sub_task = asyncio.create_task(subscriber())
    # Give the subscriber a tick to register.
    await asyncio.sleep(0)
    await tx.publish("agent:hevn", "envelope-id-1")
    await asyncio.wait_for(sub_task, timeout=1.0)

    assert received == ["envelope-id-1"]


@pytest.mark.asyncio
async def test_different_channels_dont_cross():
    """A subscriber on X does not see messages published on Y."""
    tx = InMemoryBusTransport()
    received: list[str] = []

    async def subscriber():
        async for payload in tx.subscribe("agent:hevn"):
            received.append(payload)
            return  # take 1

    sub_task = asyncio.create_task(subscriber())
    await asyncio.sleep(0)
    await tx.publish("agent:makubex", "other-channel-payload")
    # Subscriber should NOT have received anything — confirm by short timeout.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(sub_task), timeout=0.1)
    sub_task.cancel()
    await asyncio.gather(sub_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_execute_returns_what_caller_records():
    """InMemoryBusTransport.execute just records the call; returns None by default."""
    tx = InMemoryBusTransport()
    result = await tx.execute("INSERT INTO foo VALUES ($1)", "bar")
    assert result is None
    assert tx.executed == [("INSERT INTO foo VALUES ($1)", ("bar",))]
