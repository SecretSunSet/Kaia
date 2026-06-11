"""Bus class — logic only (RPC correlation, timeouts, dispatcher).

Depends only on bus.envelope and bus.transport. No asyncpg import.
"""

from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable
from uuid import UUID, uuid4

from loguru import logger

from agent_runtime.base_agent import PeerCallError, PeerCallTimeoutError
from bus.envelope import Envelope, Visibility
from bus.transport import BusTransport


PeerIntentHandler = Callable[[Envelope], Awaitable[dict]]


_INSERT_CONVERSATION_SQL = """
INSERT INTO agent_conversations (conversation_id, user_id, started_by_agent, intent_root)
VALUES ($1, $2, $3, $4)
ON CONFLICT (conversation_id) DO NOTHING
"""

_INSERT_MESSAGE_SQL = """
INSERT INTO agent_messages
    (envelope_id, conversation_id, from_agent, to_agent, user_id,
     intent, visibility, kind, reply_to, payload, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
"""


class Bus:
    """Agentic OS R-3 bus.

    Owns:
      - RPC future map (envelope_id -> asyncio.Future) for peer_call awaits
      - per-agent intent handler registry
      - per-agent LISTEN dispatcher tasks
      - default timeout enforcement

    Transport injected (PostgresBusTransport in prod, InMemoryBusTransport in tests).
    """

    def __init__(self, transport: BusTransport, *, default_timeout: float = 30.0) -> None:
        self._tx = transport
        self._default_timeout = default_timeout
        self._handlers: dict[tuple[str, str], PeerIntentHandler] = {}
        self._futures: dict[UUID, asyncio.Future[dict]] = {}
        self._dispatcher_tasks: list[asyncio.Task[None]] = []
        self._started = False
        self._shutting_down = False
        self._inflight: dict[UUID, Envelope] = {}

    # ── Public API ──────────────────────────────────────────────────

    def register_handler(self, agent_id: str, intent: str, handler: PeerIntentHandler) -> None:
        """Register an inbound peer-intent handler for an agent."""
        self._handlers[(agent_id, intent)] = handler

    async def start(self) -> None:
        """Launch one dispatcher task per agent that has handlers registered.

        Yields to the event loop after creating tasks so every dispatcher
        has had a chance to reach its first ``subscribe()`` call before
        ``start()`` returns. Without this yield, a ``peer_call()`` made
        immediately after ``start()`` would publish to an empty subscriber
        list and the message would be silently dropped.
        """
        if self._started:
            return
        agents = {agent_id for (agent_id, _intent) in self._handlers}
        for agent_id in agents:
            task = asyncio.create_task(
                self._dispatch_loop(agent_id), name=f"bus-dispatch-{agent_id}"
            )
            self._dispatcher_tasks.append(task)
        self._started = True
        # Let all dispatchers run to their first await (q.get inside subscribe).
        await asyncio.sleep(0)
        logger.info("Bus started; dispatcher tasks: {}", [a for a in agents])

    async def shutdown(self) -> None:
        """Cancel dispatcher tasks; resolve outstanding futures with PeerCallError."""
        if self._shutting_down:
            return
        self._shutting_down = True
        for t in self._dispatcher_tasks:
            t.cancel()
        for t in self._dispatcher_tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        for fut in list(self._futures.values()):
            if not fut.done():
                fut.set_exception(PeerCallError("bus shutting down"))
        self._futures.clear()
        self._dispatcher_tasks.clear()
        self._started = False
        logger.info("Bus shut down")

    async def peer_call(
        self,
        source: str,
        target: str,
        intent: str,
        payload: dict,
        user_id: UUID,
        *,
        conversation_id: UUID | None = None,
        visibility: Visibility = Visibility.USER_VISIBLE,
        timeout: float | None = None,
    ) -> dict:
        """RPC-style peer call. Returns the peer's reply payload (dict).

        Raises:
            PeerCallTimeoutError: budget exhausted.
            PeerCallError: peer raised, or bus is shutting down.
        """
        if self._shutting_down:
            raise PeerCallError("bus is shutting down")
        budget = timeout if timeout is not None else self._default_timeout
        conv_id = conversation_id or uuid4()
        envelope_id = uuid4()
        env = Envelope(
            envelope_id=envelope_id,
            conversation_id=conv_id,
            from_agent=source,
            to_agent=target,
            user_id=user_id,
            intent=intent,
            visibility=visibility,
            kind="request",
            payload=payload,
        )
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict] = loop.create_future()
        self._futures[envelope_id] = fut
        try:
            await self._persist_and_notify(env, ensure_conversation=True)
            return await asyncio.wait_for(fut, timeout=budget)
        except asyncio.TimeoutError as exc:
            raise PeerCallTimeoutError(
                f"peer_call({target!r}, {intent!r}) timed out after {budget}s"
            ) from exc
        finally:
            self._futures.pop(envelope_id, None)

    # ── Internals ───────────────────────────────────────────────────

    async def _persist_and_notify(self, env: Envelope, *, ensure_conversation: bool) -> None:
        """INSERT the row then NOTIFY (atomic ordering — the Bus's job)."""
        if ensure_conversation:
            await self._tx.execute(
                _INSERT_CONVERSATION_SQL,
                env.conversation_id,
                env.user_id,
                env.from_agent,
                env.intent,
            )
        await self._tx.execute(
            _INSERT_MESSAGE_SQL,
            env.envelope_id,
            env.conversation_id,
            env.from_agent,
            env.to_agent,
            env.user_id,
            env.intent,
            env.visibility.value,
            env.kind,
            env.reply_to,
            json.dumps(env.payload),
            env.created_at,
        )
        # Cache for in-process delivery (InMemoryBusTransport path).
        # Task 7 will replace this with transport.fetch_envelope() so the
        # dispatcher works correctly with PostgresBusTransport too.
        self._inflight[env.envelope_id] = env
        await self._tx.publish(f"agent:{env.to_agent}", str(env.envelope_id))
        if env.visibility is Visibility.USER_VISIBLE:
            await self._tx.publish("bus:user_visible", str(env.envelope_id))

    async def _dispatch_loop(self, agent_id: str) -> None:
        """Listen on agent:<agent_id>; dispatch incoming envelopes."""
        try:
            async for envelope_id_str in self._tx.subscribe(f"agent:{agent_id}"):
                try:
                    envelope_id = UUID(envelope_id_str)
                except ValueError:
                    logger.warning("Bus dispatch: malformed envelope_id {!r}", envelope_id_str)
                    continue
                env = self._inflight.get(envelope_id)
                if env is None:
                    logger.debug("Bus dispatch: no envelope for {}", envelope_id)
                    continue
                if env.kind == "request":
                    await self._handle_request(env)
                elif env.kind in ("reply", "error"):
                    self._resolve_future(env)
        except asyncio.CancelledError:
            return

    async def _handle_request(self, env: Envelope) -> None:
        handler = self._handlers.get((env.to_agent, env.intent))
        if handler is None:
            logger.warning("Bus: no handler registered for ({}, {})", env.to_agent, env.intent)
            await self._send_error_reply(env, f"no handler for intent {env.intent!r}")
            return
        try:
            reply_payload = await handler(env)
        except Exception as exc:
            logger.exception("Bus: handler raised for ({}, {})", env.to_agent, env.intent)
            await self._send_error_reply(env, f"{type(exc).__name__}: {exc}")
            return
        reply = Envelope(
            envelope_id=uuid4(),
            conversation_id=env.conversation_id,
            from_agent=env.to_agent,
            to_agent=env.from_agent,
            user_id=env.user_id,
            intent=env.intent,
            visibility=env.visibility,
            kind="reply",
            reply_to=env.envelope_id,
            payload=reply_payload,
        )
        await self._persist_and_notify(reply, ensure_conversation=False)
        # Direct in-process resolution: the caller's future lives in this
        # Bus instance, so we resolve it here without routing through a
        # second pub/sub cycle. (Postgres prod will do the same via the
        # caller's own LISTEN connection in Task 7.)
        self._resolve_future(reply)

    async def _send_error_reply(self, original: Envelope, error_text: str) -> None:
        err = Envelope(
            envelope_id=uuid4(),
            conversation_id=original.conversation_id,
            from_agent=original.to_agent,
            to_agent=original.from_agent,
            user_id=original.user_id,
            intent=original.intent,
            visibility=original.visibility,
            kind="error",
            reply_to=original.envelope_id,
            payload={"error": error_text},
        )
        await self._persist_and_notify(err, ensure_conversation=False)
        # Direct in-process resolution for error replies (same reasoning).
        self._resolve_future(err)

    def _resolve_future(self, env: Envelope) -> None:
        fut = self._futures.get(env.reply_to) if env.reply_to else None
        if fut is None or fut.done():
            logger.debug("Bus: dropping late or unmatched envelope {}", env.envelope_id)
            return
        if env.kind == "error":
            fut.set_exception(PeerCallError(env.payload.get("error", "peer raised")))
        else:
            fut.set_result(env.payload)
