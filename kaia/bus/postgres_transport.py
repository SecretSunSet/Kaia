"""PostgresBusTransport — asyncpg implementation of BusTransport.

Owns:
  - The asyncpg Pool for writes / fetches.
  - One dedicated listener connection per LISTEN channel; the LISTEN
    callback dispatches to per-channel asyncio.Queues that subscribe()
    iterates.

`store_envelope` is a no-op: the agent_messages row IS the storage.
`fetch_envelope` re-hydrates an Envelope by SELECTing the row.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator
from uuid import UUID

import asyncpg
from loguru import logger

from bus.envelope import Envelope, Visibility


_SELECT_ENVELOPE_SQL = """
SELECT envelope_id, conversation_id, from_agent, to_agent, user_id, intent,
       visibility, kind, reply_to, payload, created_at
FROM agent_messages
WHERE envelope_id = $1
"""


class PostgresBusTransport:
    """Production transport for Bus, backed by asyncpg."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._listener_conn: asyncpg.Connection | None = None
        self._channel_queues: dict[str, list[asyncio.Queue[str]]] = {}

    async def start(self) -> None:
        # Bus uses 2 DB connections at minimum: 1 pool conn (writes/fetches)
        # + 1 dedicated listener (LISTEN/NOTIFY). Pool sizing: max_size=4
        # is comfortable for the demo's traffic profile; bump if peer_call
        # concurrency exceeds 4.
        self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=4)
        self._listener_conn = await asyncpg.connect(self._dsn)
        logger.info("PostgresBusTransport started ({})", self._redact_dsn())

    async def shutdown(self) -> None:
        if self._listener_conn is not None:
            await self._listener_conn.close()
            self._listener_conn = None
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def publish(self, channel: str, payload: str) -> None:
        assert self._pool is not None, "PostgresBusTransport not started"
        sane = self._sanitize(channel)
        async with self._pool.acquire() as conn:
            await conn.execute(f'NOTIFY "{sane}", $1', payload)

    async def subscribe(self, channel: str) -> AsyncIterator[str]:
        """Register a listener on `channel` and yield each payload as it arrives."""
        assert self._listener_conn is not None, "PostgresBusTransport not started"
        q: asyncio.Queue[str] = asyncio.Queue()
        self._channel_queues.setdefault(channel, []).append(q)

        if len(self._channel_queues[channel]) == 1:
            await self._listener_conn.add_listener(
                self._sanitize(channel), self._on_notify
            )
        try:
            while True:
                yield await q.get()
        finally:
            self._channel_queues.get(channel, []).remove(q)
            if not self._channel_queues.get(channel):
                if self._listener_conn is not None:
                    await self._listener_conn.remove_listener(
                        self._sanitize(channel), self._on_notify
                    )

    def _on_notify(self, conn, pid, channel, payload):
        """asyncpg LISTEN callback — fan out to every queue subscribed to channel."""
        for q in list(self._channel_queues.get(channel, [])):
            q.put_nowait(payload)

    async def execute(self, sql: str, *args: Any) -> Any:
        assert self._pool is not None, "PostgresBusTransport not started"
        async with self._pool.acquire() as conn:
            return await conn.execute(sql, *args)

    async def store_envelope(self, env: Envelope) -> None:
        """No-op: the agent_messages row IS the storage (written by Bus via execute INSERT)."""
        return None

    async def fetch_envelope(self, envelope_id: UUID) -> Envelope | None:
        assert self._pool is not None, "PostgresBusTransport not started"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_SELECT_ENVELOPE_SQL, envelope_id)
            if row is None:
                return None
            return Envelope(
                envelope_id=row["envelope_id"],
                conversation_id=row["conversation_id"],
                from_agent=row["from_agent"],
                to_agent=row["to_agent"],
                user_id=row["user_id"],
                intent=row["intent"],
                visibility=Visibility(row["visibility"]),
                kind=row["kind"],
                payload=json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"],
                reply_to=row["reply_to"],
                created_at=row["created_at"],
            )

    # ── helpers ─────────────────────────────────────────────────────

    def _sanitize(self, channel: str) -> str:
        """Postgres LISTEN/NOTIFY channel names are identifiers; reject anything weird."""
        if not all(c.isalnum() or c in "_:-" for c in channel):
            raise ValueError(f"bad channel name {channel!r}")
        return channel

    def _redact_dsn(self) -> str:
        try:
            head, _, tail = self._dsn.partition("@")
            return f"{head.rsplit(':', 1)[0]}:***@{tail}"
        except Exception:
            return "<dsn>"
