"""Bus transport abstraction.

Bus logic depends on this Protocol; tests inject InMemoryBusTransport,
prod uses PostgresBusTransport (asyncpg). Keeps bus.py free of any DB
client dependency so its logic is unit-testable.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Protocol
from uuid import UUID

from bus.envelope import Envelope


class BusTransport(Protocol):
    """Minimal transport surface the Bus needs.

    Methods:
        publish(channel, payload): fire a NOTIFY (or equivalent) — payload
            is a small string (typically an envelope_id).
        subscribe(channel): async iterator of payloads received on channel.
            Subscribing twice on the same channel is allowed; each subscriber
            sees independent message streams (fan-out).
        execute(sql, *args): run a SQL statement (INSERT, etc.). Returns
            whatever the underlying driver returns (None in the in-memory
            impl; the asyncpg status string in prod).
        store_envelope(env): persist/cache an Envelope for later retrieval.
        fetch_envelope(envelope_id): retrieve a previously stored Envelope,
            or None if not found.
    """

    async def publish(self, channel: str, payload: str) -> None: ...

    def subscribe(self, channel: str) -> AsyncIterator[str]: ...

    async def execute(self, sql: str, *args: Any) -> Any: ...

    async def store_envelope(self, env: Envelope) -> None: ...

    async def fetch_envelope(self, envelope_id: UUID) -> Envelope | None: ...


class InMemoryBusTransport:
    """Test-only transport: asyncio.Queue per channel, fan-out subscribers.

    Records every execute() call in ``self.executed`` so tests can assert
    the SQL the Bus issued without a real database.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[str]]] = {}
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.envelopes: dict[UUID, Envelope] = {}

    async def publish(self, channel: str, payload: str) -> None:
        for q in list(self._subscribers.get(channel, [])):
            await q.put(payload)

    async def subscribe(self, channel: str) -> AsyncIterator[str]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self._subscribers.setdefault(channel, []).append(q)
        try:
            while True:
                yield await q.get()
        finally:
            # Unregister on iterator close.
            self._subscribers.get(channel, []).remove(q)

    async def execute(self, sql: str, *args: Any) -> Any:
        self.executed.append((sql, args))
        return None

    async def store_envelope(self, env: Envelope) -> None:
        self.envelopes[env.envelope_id] = env

    async def fetch_envelope(self, envelope_id: UUID) -> Envelope | None:
        return self.envelopes.get(envelope_id)
