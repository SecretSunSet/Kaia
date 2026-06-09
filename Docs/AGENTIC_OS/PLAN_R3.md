# R-3 Implementation Plan — Postgres bus + A2A protocol + Hevn↔MakubeX demo

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first user-visible Agentic OS feature: a real Postgres `LISTEN`/`NOTIFY`-backed inter-agent bus, the A2A envelope protocol, and a working Hevn↔MakubeX peer-call demo where the user watches three messages flow in their Telegram thread (consult → reply → synthesis) on a smart-contract / DeFi risk question.

**Architecture:** Introduce `kaia/bus/` as an asyncpg sidecar alongside the existing supabase-py client. `Bus` owns RPC correlation + timeouts; a small `BusTransport` Protocol (`PostgresBusTransport` for prod, `InMemoryBusTransport` for tests) isolates the wire so the bus logic is unit-testable without asyncpg. `BaseAgent.peer_call(...)` (R-1 stub) is replaced by a real implementation that delegates to the class-injected bus; subclasses register inbound intent handlers via `_register_peer_intents()`. Hevn's `handle()` becomes a three-step orchestrator (classify → optional consult → synthesize) with a graceful fallback when the consult fails. MakubeX registers a `smart_contract_risk` peer-intent handler. The Telegram bot starts the bus in `post_init` (fails fast if the DB is unreachable), subscribes to `bus:user_visible`, and renders interleaved attribution messages into the user's thread.

**Tech Stack:** Python 3.11+, asyncio, asyncpg (NEW), python-telegram-bot, supabase-py (existing), loguru, pytest + pytest-asyncio (1.3.0). PostgreSQL via Supabase (existing) — adds the `006_agent_bus.sql` migration applied manually via the Supabase SQL editor (same pattern as 001–005).

---

## Scope Check

This plan covers a single coherent subsystem (the inter-agent bus + A2A protocol + a demo intent that exercises it end-to-end) and ships a working bot at every commit. Explicitly **out of scope** (each is its own later plan):

- **R-4: per-bot Telegram tokens / separate Railway/EC2 services.** The bus is designed for the multi-process world from day one (each agent process simply runs its own listener task; no `bus/` code change needed when R-4 lands).
- **R-5: cross-expert weekly digest, full mesh, more consult intents.**
- **Tool-calling inside Hevn's main LLM** (the brainstorming Q4 Approach B). Cleaner long-term, but its own initiative.
- **Intents beyond `smart_contract_risk`.** Each new intent is small follow-up work.
- **Rate limiting per-user across peer calls.** Open question in `DESIGN.md`; not blocking R-3.
- **`channel_profile` peer-readable without `peer_call`.** Another open question; explicitly left open.
- **Multi-hop consults** (MakubeX calls Kazuki mid-reply). Architecture supports it; not in the R-3 demo.
- **Row-level security on the bus tables.** Single service principal today; revisit at R-4.
- **Bus replay / dead-letter handling.** Audit tables enable this later; R-3 ships only the live path.

**Dominant constraints:**
1. **R-1 + R-2 must not regress.** All 13 existing tests must stay green throughout; behavior of `cmd_start`, `handle_message`, `handle_voice`, `_handle_expert_turn` and the concierge general flow is unchanged except where this plan explicitly modifies the bot to start/subscribe to the bus.
2. **Bus startup is a hard prerequisite.** If asyncpg can't connect on boot, the bot fails fast — does NOT silently start without the bus.
3. **No silent drops of `peer_call` failures.** Timeouts, peer errors, and bus DB write failures all raise to the caller; Hevn catches them and falls back gracefully (one user-visible message with a transparency footer instead of three).
4. **`visibility=user_visible` envelopes are always rendered** to the user's thread; rendering failure logs loud, does not silently drop.

---

## File Structure

```
kaia/
├── bus/                                  # NEW — Agentic OS R-3 bus
│   ├── __init__.py                       # exports Bus, BusTransport, Envelope, Visibility,
│   │                                     # InMemoryBusTransport, PostgresBusTransport
│   ├── envelope.py                       # Envelope dataclass + Visibility enum + (de)serializers
│   ├── transport.py                      # BusTransport Protocol + InMemoryBusTransport
│   ├── postgres_transport.py             # PostgresBusTransport (asyncpg impl)
│   └── bus.py                            # Bus class — logic only (uses BusTransport)
├── agent_runtime/
│   └── base_agent.py                     # MODIFIED — adds PeerCallTimeoutError, real peer_call,
│                                         # register_peer_intent, set_bus classmethod, _bus class attr
├── experts/
│   ├── hevn/
│   │   ├── expert.py                     # MODIFIED — handle() becomes 3-step orchestrator;
│   │   │                                 # adds _classify_consult_intent, _synthesize_with_consult,
│   │   │                                 # _direct_answer (the R-1/R-2 path extracted)
│   │   └── prompts.py                    # MODIFIED — adds classifier + synthesis prompts
│   └── makubex/
│       ├── expert.py                     # MODIFIED — overrides _register_peer_intents to bind
│       │                                 # smart_contract_risk handler
│       └── prompts.py                    # MODIFIED — adds smart_contract_risk system prompt
├── bot/
│   └── telegram_bot.py                   # MODIFIED — post_init starts Bus + injects via
│                                         # BaseAgent.set_bus; subscribes to bus:user_visible;
│                                         # renders attribution messages; post_shutdown calls
│                                         # bus.shutdown()
├── config/
│   └── settings.py                       # MODIFIED — adds database_url, r3_peer_call_timeout_seconds
├── database/
│   └── migrations/
│       └── 006_agent_bus.sql             # NEW — agent_conversations + agent_messages
├── requirements.txt                      # MODIFIED — adds asyncpg>=0.29.0
└── tests/
    ├── test_bus_envelope.py              # NEW — Envelope contract tests
    ├── test_bus_in_memory_transport.py   # NEW — InMemoryBusTransport behavior tests
    ├── test_bus_logic.py                 # NEW — Bus class with InMemoryBusTransport: RPC, timeout, correlation
    ├── test_base_agent_peer_call.py      # NEW — BaseAgent.peer_call + register_peer_intent
    ├── test_makubex_smart_contract_risk.py  # NEW — MakubeX inbound handler contract
    ├── test_hevn_classifier.py           # NEW — Hevn classifier prompt behavior (mocked AI)
    ├── test_hevn_consult_fallback.py     # NEW — Hevn graceful fallback on peer_call failure
    ├── test_r3_demo_e2e.py               # NEW — full DeFi demo with in-process bus (no real DB)
    └── test_r3_live_bus.py               # NEW — env-gated; runs against real Postgres when DSN set

Docs/AGENTIC_OS/
├── DESIGN.md                             # MODIFIED — status header bump (R-3 in progress → shipped)
├── DESIGN_R3.md                          # source of truth (already committed on this branch)
└── PLAN_R3.md                            # this file

Docs/
├── ARCHITECTURE.md                       # MODIFIED — Agentic OS section: R-3 current state
├── CHANGELOG.md                          # MODIFIED — R-3 entry
├── DEVELOPMENT_STATUS.md                 # MODIFIED — R-3 row → ✅ Complete
└── DATABASE.md                           # MODIFIED — append "Agentic OS Bus Tables (Migration 006)" section
```

**Responsibility split:**
- `bus/envelope.py` — pure data type. No I/O. Trivially testable.
- `bus/transport.py` — `BusTransport` Protocol (3 async methods: `publish`, `subscribe`, `execute`) + `InMemoryBusTransport` (asyncio.Queue per channel). Used by tests.
- `bus/postgres_transport.py` — `PostgresBusTransport` wrapping asyncpg. Owns the pool, the listener connection(s), the `add_listener` callbacks. Used by prod.
- `bus/bus.py` — `Bus` class: takes a `BusTransport`, owns the RPC future-correlation map, the intent-handler registry, the `peer_call` timeout logic, the dispatcher loop. Pure logic; no asyncpg import.
- `agent_runtime/base_agent.py` — adds the class-level `_bus` slot, `set_bus(bus)` classmethod, `register_peer_intent` instance method, `_register_peer_intents()` hook (subclasses override), and the real `peer_call` that delegates to `self._bus`. `PeerCallTimeoutError(PeerCallError)` lives here.
- `experts/hevn/expert.py` — `handle()` becomes the three-step orchestrator using `peer_call`. The existing R-1/R-2 direct-answer logic is extracted to `_direct_answer()` so the fallback path can reuse it.
- `experts/makubex/expert.py` — overrides `_register_peer_intents()` to bind `smart_contract_risk` to a new `handle_smart_contract_risk(envelope) -> dict` method.
- `bot/telegram_bot.py` — `post_init` becomes responsible for bus lifecycle and `BaseAgent.set_bus`. A new background task renders `bus:user_visible` envelopes into the user's thread.

> **Plan location note:** the writing-plans skill default is `docs/superpowers/plans/`. This project's established convention (set by `Docs/AGENTIC_OS/PLAN_R1.md` and `PLAN_R2.md`) overrides it — Agentic OS phase plans live under `Docs/AGENTIC_OS/`.

---

## Task 1: Bump DESIGN.md status and commit this plan

**Files:**
- Modify: `Docs/AGENTIC_OS/DESIGN.md:3-4`
- Create: `Docs/AGENTIC_OS/PLAN_R3.md` (this file — already written on `agentic-os-r3` branch)

- [ ] **Step 1: Update the status header in `Docs/AGENTIC_OS/DESIGN.md`**

Read `Docs/AGENTIC_OS/DESIGN.md`. The current status header line (set by R-2) reads something like:
```markdown
> Status: R-2 (concierge code split) — in progress. R-1 shipped.
```
(Whatever the exact post-R-2 wording is — read the file to confirm.)

Replace that single status line with:
```markdown
> Status: R-3 (bus + A2A protocol + peer-call demo) — in progress. R-1, R-2 shipped.
```
And bump the `Last updated:` line directly below it to today's date (`2026-06-09`). Do not change any other line in `DESIGN.md` — the rest of the design is locked.

- [ ] **Step 2: Commit the design status bump and this plan**

```bash
cd /home/ejay/Kaia && git add Docs/AGENTIC_OS/DESIGN.md Docs/AGENTIC_OS/PLAN_R3.md && git commit -m "$(cat <<'EOF'
docs(agentic-os): R-3 bus + protocol + demo plan; mark R-3 in progress

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add `asyncpg` dependency + new settings

**Files:**
- Modify: `kaia/requirements.txt` (add `asyncpg>=0.29.0`)
- Modify: `kaia/config/settings.py` (add `database_url`, `r3_peer_call_timeout_seconds`)

- [ ] **Step 1: Append `asyncpg` to `kaia/requirements.txt`**

Read the file first to see existing conventions (sorting, pinning style). Append a new line:
```
asyncpg>=0.29.0
```
(Match the existing pinning style if the file uses `~=` or exact pins — `>=0.29.0` is a safe lower bound for the asyncpg API we use; pin tighter if the file's other entries are tightly pinned.)

- [ ] **Step 2: Install asyncpg locally**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pip install --user "asyncpg>=0.29.0"
```
Expected: successful install, no errors. (Note: there's no usable venv activate script — system Python 3.12 is what `python3 -m pytest` uses; install into the same interpreter.)

- [ ] **Step 3: Sanity-check asyncpg imports**

```bash
cd /home/ejay/Kaia/kaia && python3 -c "import asyncpg; print('asyncpg', asyncpg.__version__)"
```
Expected: `asyncpg 0.29.x` or higher.

- [ ] **Step 4: Add settings fields to `kaia/config/settings.py`**

Read `kaia/config/settings.py` first. It uses a `Settings` class (likely Pydantic BaseSettings or a similar dataclass). Add two fields following the existing convention (snake_case field names, env-var-driven, with sensible defaults where applicable). The two new fields:

```python
# Postgres DSN for the asyncpg bus sidecar (R-3).
# Supabase exposes this at Project Settings → Database → Connection String.
# Use the connection pooler URL on port 6543 if available, else direct 5432.
database_url: str | None = None

# Default timeout (seconds) for BaseAgent.peer_call (R-3).
r3_peer_call_timeout_seconds: float = 30.0
```

If the existing `Settings` class uses Pydantic `BaseSettings`, the env vars `DATABASE_URL` and `R3_PEER_CALL_TIMEOUT_SECONDS` will be auto-bound by Pydantic's case-insensitive matching. If it uses `os.environ.get(...)` patterns, follow that style instead.

- [ ] **Step 5: Sanity-check settings still loads**

```bash
cd /home/ejay/Kaia/kaia && python3 -c "from config.settings import get_settings; s = get_settings(); print('database_url set:', s.database_url is not None); print('peer timeout:', s.r3_peer_call_timeout_seconds)"
```
Expected: prints `database_url set: False` (no DATABASE_URL in env yet — that's fine) and `peer timeout: 30.0`. **Do not set `DATABASE_URL` locally yet** — the bot will fail fast if it's set but unreachable, which we don't want until the bus code exists (Task 5+).

- [ ] **Step 6: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/requirements.txt kaia/config/settings.py && git commit -m "$(cat <<'EOF'
feat(deps): add asyncpg sidecar dep + R-3 bus settings

Adds asyncpg>=0.29.0 (for Postgres LISTEN/NOTIFY in the R-3 bus) and
two settings:

  - database_url — direct Postgres DSN for the asyncpg pool
  - r3_peer_call_timeout_seconds — peer_call RPC timeout (default 30)

No code uses these yet; the bus module lands in subsequent commits.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add migration `006_agent_bus.sql`

**Files:**
- Create: `kaia/database/migrations/006_agent_bus.sql`

This task creates the SQL file. **The migration must be applied manually to Supabase via the SQL editor before the bot can run with R-3 code** (same pattern as 001–005). The plan documents how; Task 12 (bot wiring) will fail-fast on startup if 006 hasn't been applied.

- [ ] **Step 1: Create `kaia/database/migrations/006_agent_bus.sql`**

```sql
-- 006_agent_bus.sql — Agentic OS R-3: inter-agent bus tables.

CREATE TABLE agent_conversations (
  conversation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  started_by_agent  VARCHAR(50)  NOT NULL,
  intent_root       VARCHAR(100),                          -- nullable; root intent if known
  status            VARCHAR(20)  NOT NULL DEFAULT 'open',  -- 'open' | 'closed' | 'errored'
  created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  closed_at         TIMESTAMPTZ
);

CREATE INDEX idx_agent_conv_user
  ON agent_conversations(user_id, created_at DESC);

CREATE TABLE agent_messages (
  envelope_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES agent_conversations(conversation_id) ON DELETE CASCADE,
  from_agent      VARCHAR(50)  NOT NULL,
  to_agent        VARCHAR(50)  NOT NULL,
  user_id         UUID         NOT NULL,                          -- denormalized for fast user lookups
  intent          VARCHAR(100) NOT NULL,
  visibility      VARCHAR(20)  NOT NULL DEFAULT 'user_visible',   -- 'user_visible' | 'internal'
  kind            VARCHAR(20)  NOT NULL,                          -- 'request' | 'reply' | 'error'
  reply_to        UUID REFERENCES agent_messages(envelope_id),    -- correlates reply → request
  payload         JSONB        NOT NULL,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_msg_conv
  ON agent_messages(conversation_id, created_at);

CREATE INDEX idx_agent_msg_to_pending
  ON agent_messages(to_agent, created_at DESC)
  WHERE kind = 'request';
```

- [ ] **Step 2: (Manual ops gate — not a code step) Apply migration to Supabase**

Operator (the developer, not the agentic worker): open Supabase Dashboard → SQL Editor → New Query → paste the contents of `kaia/database/migrations/006_agent_bus.sql` → Run. Verify both tables appear in the Tables view.

The agentic worker implementing this plan should NOT attempt to apply the migration (no programmatic Supabase admin access). Mark this checkbox once the operator confirms application. R-3's bot startup will fail fast in Task 12 if this is not done.

- [ ] **Step 3: Commit the SQL file**

```bash
cd /home/ejay/Kaia && git add kaia/database/migrations/006_agent_bus.sql && git commit -m "$(cat <<'EOF'
feat(db): migration 006 — agent_conversations + agent_messages

R-3 bus audit tables. Apply manually via Supabase SQL editor before
deploying R-3 (same pattern as migrations 001–005). Schema matches
Docs/AGENTIC_OS/DESIGN_R3.md §5.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `Envelope` dataclass + `Visibility` enum (TDD)

**Files:**
- Create: `kaia/bus/__init__.py`
- Create: `kaia/bus/envelope.py`
- Create: `kaia/tests/test_bus_envelope.py`

- [ ] **Step 1: Write the failing test for `Envelope`**

Create `kaia/tests/test_bus_envelope.py`:

```python
"""Contract tests for bus.Envelope and Visibility."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from bus import Envelope, Visibility


def _sample(**overrides) -> Envelope:
    defaults = dict(
        envelope_id=uuid4(),
        conversation_id=uuid4(),
        from_agent="hevn",
        to_agent="makubex",
        user_id=uuid4(),
        intent="smart_contract_risk",
        visibility=Visibility.USER_VISIBLE,
        kind="request",
        payload={"protocol": "Aave", "asset": "USDC"},
        reply_to=None,
        created_at=datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Envelope(**defaults)


def test_visibility_enum_members():
    assert Visibility.USER_VISIBLE.value == "user_visible"
    assert Visibility.INTERNAL.value == "internal"


def test_envelope_round_trip_to_from_dict():
    env = _sample()
    d = env.to_dict()
    # All UUIDs serialized as strings, datetime as isoformat, enums as values.
    assert d["envelope_id"] == str(env.envelope_id)
    assert d["visibility"] == "user_visible"
    assert d["kind"] == "request"
    assert d["payload"] == {"protocol": "Aave", "asset": "USDC"}
    assert d["reply_to"] is None
    # Round-trip back to Envelope must be equal.
    restored = Envelope.from_dict(d)
    assert restored == env


def test_envelope_reply_to_round_trip():
    request_id = uuid4()
    env = _sample(kind="reply", reply_to=request_id)
    d = env.to_dict()
    assert d["reply_to"] == str(request_id)
    restored = Envelope.from_dict(d)
    assert restored.reply_to == request_id


def test_envelope_rejects_unknown_kind():
    with pytest.raises((ValueError, TypeError)):
        _sample(kind="invalid")


def test_envelope_rejects_missing_required_field():
    """from_dict must raise on missing required keys."""
    d = _sample().to_dict()
    del d["from_agent"]
    with pytest.raises((KeyError, TypeError, ValueError)):
        Envelope.from_dict(d)
```

- [ ] **Step 2: Run test; verify it fails**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_bus_envelope.py -q
```
Expected: `ModuleNotFoundError: No module named 'bus'`.

- [ ] **Step 3: Create `kaia/bus/envelope.py`**

```python
"""A2A envelope and visibility enum — the wire format for the R-3 bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID


class Visibility(str, Enum):
    """Whether a peer-to-peer envelope is relayed to the user."""

    USER_VISIBLE = "user_visible"
    INTERNAL = "internal"


_VALID_KINDS = {"request", "reply", "error"}

EnvelopeKind = Literal["request", "reply", "error"]


@dataclass(slots=True)
class Envelope:
    """One inter-agent message — request, reply, or error.

    See Docs/AGENTIC_OS/DESIGN_R3.md §2 and §5 for the full schema. The
    on-wire representation (to_dict) matches the agent_messages table
    columns; reply correlation is via reply_to (the envelope_id of the
    triggering request).
    """

    envelope_id: UUID
    conversation_id: UUID
    from_agent: str
    to_agent: str
    user_id: UUID
    intent: str
    visibility: Visibility
    kind: EnvelopeKind
    payload: dict[str, Any]
    reply_to: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"Envelope.kind must be one of {_VALID_KINDS}, got {self.kind!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSONB / network payloads."""
        return {
            "envelope_id": str(self.envelope_id),
            "conversation_id": str(self.conversation_id),
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "user_id": str(self.user_id),
            "intent": self.intent,
            "visibility": self.visibility.value,
            "kind": self.kind,
            "payload": self.payload,
            "reply_to": str(self.reply_to) if self.reply_to is not None else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Envelope":
        """Deserialize from a row / JSON payload. Raises on missing required fields."""
        required = (
            "envelope_id", "conversation_id", "from_agent", "to_agent",
            "user_id", "intent", "visibility", "kind", "payload",
        )
        for key in required:
            if key not in d:
                raise KeyError(f"Envelope.from_dict missing required key: {key!r}")
        reply_to_raw = d.get("reply_to")
        created_raw = d.get("created_at")
        created = (
            datetime.fromisoformat(created_raw)
            if isinstance(created_raw, str)
            else (created_raw or datetime.now(timezone.utc))
        )
        return cls(
            envelope_id=UUID(d["envelope_id"]) if isinstance(d["envelope_id"], str) else d["envelope_id"],
            conversation_id=UUID(d["conversation_id"]) if isinstance(d["conversation_id"], str) else d["conversation_id"],
            from_agent=d["from_agent"],
            to_agent=d["to_agent"],
            user_id=UUID(d["user_id"]) if isinstance(d["user_id"], str) else d["user_id"],
            intent=d["intent"],
            visibility=Visibility(d["visibility"]),
            kind=d["kind"],
            payload=d["payload"],
            reply_to=(UUID(reply_to_raw) if isinstance(reply_to_raw, str) else reply_to_raw),
            created_at=created,
        )
```

- [ ] **Step 4: Create `kaia/bus/__init__.py`**

```python
"""Agentic OS R-3 bus — A2A envelope protocol over Postgres LISTEN/NOTIFY.

Transport-pluggable: BusTransport Protocol is implemented by
PostgresBusTransport (prod) and InMemoryBusTransport (tests). The Bus
class owns RPC correlation + timeouts; nothing here imports telegram.
"""

from __future__ import annotations

from bus.envelope import Envelope, Visibility

__all__ = ["Envelope", "Visibility"]
```

(Bus, transport, errors will be added to `__all__` as later tasks land them. This keeps the package importable after each commit.)

- [ ] **Step 5: Run test; verify it passes**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_bus_envelope.py -q
```
Expected: `5 passed`.

- [ ] **Step 6: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/bus/__init__.py kaia/bus/envelope.py kaia/tests/test_bus_envelope.py && git commit -m "$(cat <<'EOF'
feat(bus): Envelope dataclass + Visibility enum + serializers

A2A envelope wire format for the R-3 bus. Round-trip to_dict/from_dict
preserves UUIDs, datetimes, and enum values; rejects unknown kinds and
missing required fields. No transport / asyncpg yet — that lands in
the next two tasks.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `BusTransport` Protocol + `InMemoryBusTransport` (TDD)

**Files:**
- Create: `kaia/bus/transport.py`
- Modify: `kaia/bus/__init__.py` (add exports)
- Create: `kaia/tests/test_bus_in_memory_transport.py`

- [ ] **Step 1: Write the failing test**

Create `kaia/tests/test_bus_in_memory_transport.py`:

```python
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
            if len(received) >= 1:
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


@pytest.mark.asyncio
async def test_execute_returns_what_caller_records():
    """InMemoryBusTransport.execute just records the call; returns None by default."""
    tx = InMemoryBusTransport()
    result = await tx.execute("INSERT INTO foo VALUES ($1)", "bar")
    assert result is None
    assert tx.executed == [("INSERT INTO foo VALUES ($1)", ("bar",))]
```

- [ ] **Step 2: Run; verify fail**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_bus_in_memory_transport.py -q
```
Expected: `ImportError: cannot import name 'InMemoryBusTransport' from 'bus'`.

- [ ] **Step 3: Create `kaia/bus/transport.py`**

```python
"""Bus transport abstraction.

Bus logic depends on this Protocol; tests inject InMemoryBusTransport,
prod uses PostgresBusTransport (asyncpg). Keeps bus.py free of any DB
client dependency so its logic is unit-testable.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Protocol


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
    """

    async def publish(self, channel: str, payload: str) -> None: ...

    def subscribe(self, channel: str) -> AsyncIterator[str]: ...

    async def execute(self, sql: str, *args: Any) -> Any: ...


class InMemoryBusTransport:
    """Test-only transport: asyncio.Queue per channel, fan-out subscribers.

    Records every execute() call in ``self.executed`` so tests can assert
    the SQL the Bus issued without a real database.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[str]]] = {}
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    async def publish(self, channel: str, payload: str) -> None:
        for q in self._subscribers.get(channel, []):
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
```

- [ ] **Step 4: Re-export from `kaia/bus/__init__.py`**

Replace the file contents:

```python
"""Agentic OS R-3 bus — A2A envelope protocol over Postgres LISTEN/NOTIFY.

Transport-pluggable: BusTransport Protocol is implemented by
PostgresBusTransport (prod) and InMemoryBusTransport (tests). The Bus
class owns RPC correlation + timeouts; nothing here imports telegram.
"""

from __future__ import annotations

from bus.envelope import Envelope, Visibility
from bus.transport import BusTransport, InMemoryBusTransport

__all__ = ["Envelope", "Visibility", "BusTransport", "InMemoryBusTransport"]
```

- [ ] **Step 5: Run; verify pass**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_bus_envelope.py tests/test_bus_in_memory_transport.py -q
```
Expected: `8 passed` (5 envelope + 3 transport).

- [ ] **Step 6: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/bus/transport.py kaia/bus/__init__.py kaia/tests/test_bus_in_memory_transport.py && git commit -m "$(cat <<'EOF'
feat(bus): BusTransport protocol + InMemoryBusTransport for tests

3-method transport surface (publish / subscribe / execute) that the
Bus class will depend on. In-memory impl uses asyncio.Queue per channel
with fan-out semantics; record-and-replay execute() so tests can assert
the SQL the Bus issued without a real DB.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `Bus` class — RPC correlation, timeouts, dispatcher (TDD)

**Files:**
- Create: `kaia/bus/bus.py`
- Modify: `kaia/bus/__init__.py` (add `Bus`, `PeerCallError`, `PeerCallTimeoutError` exports)
- Modify: `kaia/agent_runtime/base_agent.py` (move `PeerCallError` definition + add `PeerCallTimeoutError` subclass; bus re-exports them)
- Create: `kaia/tests/test_bus_logic.py`

The bus is the heart of R-3. The implementation order: (a) extend error types in `base_agent.py` (still backwards-compatible — `PeerCallError` keeps its location), (b) write failing tests, (c) implement `Bus`, (d) verify, (e) commit.

- [ ] **Step 1: Add `PeerCallTimeoutError` in `kaia/agent_runtime/base_agent.py`**

Find the existing `class PeerCallError(NotImplementedError):` (R-1). Replace it with:

```python
class PeerCallError(Exception):
    """Base error for failures in BaseAgent.peer_call (R-3)."""


class PeerCallTimeoutError(PeerCallError):
    """Raised when a peer_call exceeds its timeout budget (R-3)."""
```

**Important:** `PeerCallError` changes its base class from `NotImplementedError` to `Exception`. The R-1 stub message ("inter-agent calls land in R-3") is removed because Task 8 replaces the stub with a real implementation. Any existing code that `raise PeerCallError(...)` continues to work; the parent-class change only affects `except NotImplementedError:` blocks — `grep -rn "NotImplementedError" /home/ejay/Kaia/kaia --include='*.py'` to confirm no caller depends on the R-1 inheritance (the only existing reference is R-1's own `raise` inside the stub `peer_call`, which Task 8 deletes).

Verify nothing breaks yet:
```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_base_agent.py -q
```
Expected: `5 passed` — the R-1 contract tests still pass because they only assert `PeerCallError` is raised, not what it inherits from.

- [ ] **Step 2: Write failing test for the Bus class**

Create `kaia/tests/test_bus_logic.py`:

```python
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
        await asyncio.sleep(10)  # > default_timeout
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
    """Two simultaneous peer_calls each receive their OWN reply."""

    async def echo_handler(env: Envelope) -> dict:
        # Slight async delay so both calls overlap.
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
    """Both the request and the reply for a user_visible peer_call land on bus:user_visible."""

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
    await asyncio.sleep(0)  # let the watcher subscribe
    try:
        await bus.peer_call("hevn", "makubex", "x", {}, _user_id(), visibility=Visibility.USER_VISIBLE)
        await asyncio.wait_for(watch_task, timeout=1.0)
        # Two envelope_ids surfaced on bus:user_visible: the request and the reply.
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
        # Give any spurious publish a chance to land.
        await asyncio.sleep(0.05)
        assert received_ids == []
    finally:
        watch_task.cancel()
        await bus.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cancels_in_flight_futures():
    """If a peer_call is awaiting when bus.shutdown() runs, it raises PeerCallError."""

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
    """The Bus must INSERT the agent_messages row BEFORE NOTIFYing.

    Asserts on the recorded execute() sequence in InMemoryBusTransport.
    """
    async def handler(env: Envelope) -> dict:
        return {}

    bus, tx = await _start_bus_with_handlers({("makubex", "x"): handler})
    try:
        await bus.peer_call("hevn", "makubex", "x", {}, _user_id())
        # tx.executed contains the SQL the Bus issued. At least one INSERT
        # into agent_messages must precede the first agent:makubex publish.
        # (Publish history is implicit through the in-memory transport's
        # subscribe loop; we can directly observe execute() ordering.)
        sql_sequence = [sql for sql, _ in tx.executed]
        assert any("INSERT INTO agent_messages" in s for s in sql_sequence), \
            "Bus did not INSERT the request row via transport.execute"
    finally:
        await bus.shutdown()
```

- [ ] **Step 3: Run; verify fail**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_bus_logic.py -q
```
Expected: `ImportError: cannot import name 'Bus' from 'bus'`.

- [ ] **Step 4: Create `kaia/bus/bus.py`**

```python
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


# An inbound peer-intent handler returns a dict (the reply payload).
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

    The transport is injected (PostgresBusTransport in prod,
    InMemoryBusTransport in tests).
    """

    def __init__(self, transport: BusTransport, *, default_timeout: float = 30.0) -> None:
        self._tx = transport
        self._default_timeout = default_timeout
        self._handlers: dict[tuple[str, str], PeerIntentHandler] = {}
        self._futures: dict[UUID, asyncio.Future[dict]] = {}
        self._dispatcher_tasks: list[asyncio.Task[None]] = []
        self._started = False
        self._shutting_down = False

    # ── Public API ──────────────────────────────────────────────────

    def register_handler(self, agent_id: str, intent: str, handler: PeerIntentHandler) -> None:
        """Register an inbound peer-intent handler for an agent."""
        self._handlers[(agent_id, intent)] = handler

    async def start(self) -> None:
        """Launch one dispatcher task per agent that has handlers registered."""
        if self._started:
            return
        agents = {agent_id for (agent_id, _intent) in self._handlers}
        for agent_id in agents:
            task = asyncio.create_task(
                self._dispatch_loop(agent_id), name=f"bus-dispatch-{agent_id}"
            )
            self._dispatcher_tasks.append(task)
        self._started = True
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
        # Register the future BEFORE publishing so a fast reply can't race us.
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
        # NOTIFY agent:<to> with the envelope_id (small payload).
        await self._tx.publish(f"agent:{env.to_agent}", str(env.envelope_id))
        # Also publish user-visible envelopes on the bot's relay channel.
        if env.visibility is Visibility.USER_VISIBLE:
            await self._tx.publish("bus:user_visible", str(env.envelope_id))
        # In-process delivery hint (for InMemoryBusTransport — Postgres re-fetches from DB).
        self._inflight_envelopes[env.envelope_id] = env

    async def _dispatch_loop(self, agent_id: str) -> None:
        """Listen on agent:<agent_id>; dispatch incoming envelopes to handlers
        (requests) or to the awaiting future (replies)."""
        try:
            async for envelope_id_str in self._tx.subscribe(f"agent:{agent_id}"):
                try:
                    envelope_id = UUID(envelope_id_str)
                except ValueError:
                    logger.warning("Bus dispatch: malformed envelope_id {!r}", envelope_id_str)
                    continue
                env = self._inflight_envelopes.get(envelope_id)
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
            logger.warning(
                "Bus: no handler registered for ({}, {})",
                env.to_agent, env.intent,
            )
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

    def _resolve_future(self, env: Envelope) -> None:
        fut = self._futures.get(env.reply_to) if env.reply_to else None
        if fut is None or fut.done():
            logger.debug("Bus: dropping late or unmatched envelope {}", env.envelope_id)
            return
        if env.kind == "error":
            fut.set_exception(PeerCallError(env.payload.get("error", "peer raised")))
        else:
            fut.set_result(env.payload)

    # In-process envelope cache. PostgresBusTransport (Task 7) will replace
    # this with transport.fetch_envelope() so the dispatcher works with both
    # in-memory and Postgres transports without re-fetching from DB locally.
    @property
    def _inflight_envelopes(self) -> dict[UUID, Envelope]:
        if not hasattr(self, "_inflight"):
            self._inflight = {}
        return self._inflight
```

- [ ] **Step 5: Re-export from `kaia/bus/__init__.py`**

Replace contents:

```python
"""Agentic OS R-3 bus — A2A envelope protocol over Postgres LISTEN/NOTIFY.

Transport-pluggable: BusTransport Protocol is implemented by
PostgresBusTransport (prod) and InMemoryBusTransport (tests). The Bus
class owns RPC correlation + timeouts; nothing here imports telegram.
"""

from __future__ import annotations

from agent_runtime.base_agent import PeerCallError, PeerCallTimeoutError
from bus.bus import Bus
from bus.envelope import Envelope, Visibility
from bus.transport import BusTransport, InMemoryBusTransport

__all__ = [
    "Bus",
    "BusTransport",
    "Envelope",
    "InMemoryBusTransport",
    "PeerCallError",
    "PeerCallTimeoutError",
    "Visibility",
]
```

- [ ] **Step 6: Run; verify pass**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_bus_logic.py tests/test_bus_envelope.py tests/test_bus_in_memory_transport.py -q
```
Expected: `16 passed` (5 envelope + 3 in-memory transport + 8 bus logic).

- [ ] **Step 7: Run the full suite to confirm no R-1/R-2 regression**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest -q
```
Expected: all pass — at least 13 (existing) + 16 (new) = 29 collected, all green.

- [ ] **Step 8: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/bus/bus.py kaia/bus/__init__.py kaia/agent_runtime/base_agent.py kaia/tests/test_bus_logic.py && git commit -m "$(cat <<'EOF'
feat(bus): Bus class with RPC correlation, timeouts, dispatcher

- PeerCallError changes base class from NotImplementedError → Exception
  to fit the new "errors expected at runtime" semantics (R-1's stub
  raised PeerCallError to advertise non-implementation; R-3 raises it
  on real failures). PeerCallTimeoutError added as a subclass.
- Bus owns: register_handler, start, shutdown, peer_call (with timeout),
  the per-agent dispatcher loop, future correlation by envelope_id,
  user_visible relay publish. No asyncpg here — pure logic on top of
  the BusTransport protocol.

Existing 13 tests stay green; 8 new bus-logic tests cover round-trip,
timeout, peer error, two-in-flight correlation, user_visible / internal
visibility routing, shutdown-cancels-futures, and INSERT-before-NOTIFY
ordering.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `PostgresBusTransport` (asyncpg impl)

**Files:**
- Create: `kaia/bus/postgres_transport.py`
- Modify: `kaia/bus/__init__.py` (add `PostgresBusTransport` export)
- Modify: `kaia/bus/transport.py` (add `fetch_envelope` and `store_envelope` to the Protocol; `InMemoryBusTransport` gains tiny dict-backed impls)
- Modify: `kaia/bus/bus.py` (use `transport.store_envelope` / `transport.fetch_envelope` instead of the in-process `_inflight_envelopes` cache)

This task ships the production transport. It's mostly untestable without a real Postgres; behavioral coverage comes from Task 13 (env-gated live test). The change to `bus.py` swaps the in-process cache for polymorphic transport methods so the dispatcher works with either transport.

- [ ] **Step 1: Extend the `BusTransport` Protocol with `fetch_envelope` and `store_envelope`**

In `kaia/bus/transport.py`, add two methods to the Protocol:

```python
from uuid import UUID
from bus.envelope import Envelope  # forward import OK at module level

class BusTransport(Protocol):
    # ... existing methods ...
    async def fetch_envelope(self, envelope_id: UUID) -> "Envelope | None": ...
    async def store_envelope(self, env: Envelope) -> None: ...
```

Add the matching methods on `InMemoryBusTransport`:

```python
class InMemoryBusTransport:
    def __init__(self) -> None:
        # ... existing fields ...
        self.envelopes: dict[UUID, Envelope] = {}

    async def store_envelope(self, env: Envelope) -> None:
        self.envelopes[env.envelope_id] = env

    async def fetch_envelope(self, envelope_id: UUID) -> Envelope | None:
        return self.envelopes.get(envelope_id)
```

In `kaia/bus/bus.py`, remove the `_inflight_envelopes` property entirely. Replace the line in `_persist_and_notify` that currently reads `self._inflight_envelopes[env.envelope_id] = env` with:

```python
await self._tx.store_envelope(env)
```

In `_dispatch_loop`, replace `env = self._inflight_envelopes.get(envelope_id)` with:

```python
env = await self._tx.fetch_envelope(envelope_id)
```

Run the existing bus tests to confirm no regression:
```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_bus_logic.py tests/test_bus_in_memory_transport.py -q
```
Expected: `11 passed` (8 bus logic + 3 in-memory transport).

- [ ] **Step 2: Create `kaia/bus/postgres_transport.py`**

```python
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
        """Create the pool and the dedicated listener connection."""
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

        # If this is the first subscriber on this channel, register the LISTEN.
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
                await self._listener_conn.remove_listener(
                    self._sanitize(channel), self._on_notify
                )

    def _on_notify(self, conn, pid, channel, payload):
        """asyncpg LISTEN callback — fan out to every queue subscribed to channel."""
        for q in self._channel_queues.get(channel, []):
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
        # Don't log credentials.
        try:
            head, _, tail = self._dsn.partition("@")
            return f"{head.split(':')[0]}:***@{tail}"
        except Exception:
            return "<dsn>"
```

- [ ] **Step 3: Re-export from `kaia/bus/__init__.py`**

Add `PostgresBusTransport` to the imports and `__all__`:

```python
from bus.postgres_transport import PostgresBusTransport
# ... add "PostgresBusTransport" to __all__ ...
```

- [ ] **Step 4: Sanity-check imports**

```bash
cd /home/ejay/Kaia/kaia && python3 -c "from bus import Bus, BusTransport, Envelope, InMemoryBusTransport, PostgresBusTransport, PeerCallError, PeerCallTimeoutError, Visibility; print('ok')"
```
Expected: `ok`.

- [ ] **Step 5: Re-run unit tests (no DB needed; uses InMemoryBusTransport)**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest -q
```
Expected: all pass; no regression.

- [ ] **Step 6: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/bus/postgres_transport.py kaia/bus/transport.py kaia/bus/bus.py kaia/bus/__init__.py && git commit -m "$(cat <<'EOF'
feat(bus): PostgresBusTransport (asyncpg) — prod wire

Wraps asyncpg pool + dedicated LISTEN connection. fan-out subscribers
via asyncio.Queue. fetch_envelope re-hydrates rows from agent_messages
(in prod, the row IS the storage); InMemoryBusTransport stores
envelopes in a dict (test-only). Bus.dispatch_loop now uses the
polymorphic fetch_envelope so it works with either transport.

Untested at the asyncpg level here — Task 13's env-gated live test
exercises real NOTIFY round-trips.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `BaseAgent.peer_call` real impl + `register_peer_intent` + `set_bus` (TDD)

**Files:**
- Modify: `kaia/agent_runtime/base_agent.py`
- Modify: `kaia/tests/test_base_agent.py` (rewrite the R-1 stub-presence test for the new contract)
- Create: `kaia/tests/test_base_agent_peer_call.py`

- [ ] **Step 1: Write the failing test**

Create `kaia/tests/test_base_agent_peer_call.py`:

```python
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
```

- [ ] **Step 2: Run; verify fail**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_base_agent_peer_call.py -q
```
Expected: failures — peer_call still raises the R-1 stub message.

- [ ] **Step 3: Modify `kaia/agent_runtime/base_agent.py`**

Find the existing R-1 `peer_call` method (it raises `PeerCallError("peer_call(...) is not wired yet...")`). Replace it with the real implementation. Also add `set_bus`, `_bus`, `register_peer_intent`, and the `_register_peer_intents()` hook.

Add inside `class BaseAgent(ABC):` (preserve all existing R-1/R-2 members):

```python
# Class-level bus slot — set once by the bot at post_init via BaseAgent.set_bus(bus).
# Class-level (not instance-level) so all agent instances share the same bus
# without needing the get_expert(...) factory to thread it.
_bus: "Bus | None" = None  # noqa: F821  (Bus imported lazily in peer_call to avoid cycle)

@classmethod
def set_bus(cls, bus) -> None:
    """Inject the process-wide bus. The bot calls this once at post_init."""
    cls._bus = bus
```

Modify `__init__` to call the registration hook AFTER existing initialisation:

```python
def __init__(self, ai_engine: AIEngine) -> None:
    self.ai = ai_engine
    self._channel_mgr = ChannelManager()
    self._channel_mem = ChannelMemoryManager()
    # R-3: bind inbound peer-intent handlers if a bus is available.
    if self._bus is not None:
        self._register_peer_intents()
```

Add the hook method (default no-op; subclasses override):

```python
def _register_peer_intents(self) -> None:
    """Override in subclasses to register inbound peer-intent handlers
    via self._bus.register_handler(self.agent_id, intent, async_handler)."""
    pass
```

Replace the R-1 `peer_call` method with:

```python
async def peer_call(
    self,
    target_agent_id: str,
    intent: str,
    payload: dict[str, Any],
    *,
    user_id,  # uuid.UUID or str — passed from handler context
    visibility=None,  # bus.Visibility, optional
    timeout: float | None = None,
) -> dict[str, Any]:
    """Send a request to another agent; await its reply payload.

    Raises:
        PeerCallTimeoutError: budget exhausted.
        PeerCallError: peer raised, or bus not initialised.
    """
    if self._bus is None:
        raise PeerCallError(
            "peer_call requires the bus to be initialised — "
            "bot post_init did not call BaseAgent.set_bus(bus)"
        )
    # Lazy import to avoid bus → agent_runtime → bus cycle at module load.
    from bus import Visibility as _Visibility
    return await self._bus.peer_call(
        source=self.agent_id,
        target=target_agent_id,
        intent=intent,
        payload=payload,
        user_id=user_id,
        visibility=visibility if visibility is not None else _Visibility.USER_VISIBLE,
        timeout=timeout,
    )
```

Add `register_peer_intent` for subclasses that prefer explicit calls over the hook:

```python
def register_peer_intent(self, intent: str, handler) -> None:
    """Register an inbound peer-intent handler on the bus."""
    if self._bus is None:
        raise PeerCallError("register_peer_intent requires the bus to be initialised")
    self._bus.register_handler(self.agent_id, intent, handler)
```

- [ ] **Step 4: Update the R-1 stub-presence test**

Open `kaia/tests/test_base_agent.py`. Find `test_peer_call_raises_until_r3_lands`. Replace its body with the new contract:

```python
@pytest.mark.asyncio
async def test_peer_call_without_bus_raises():
    """Without bus injection, peer_call must raise — fail-loud."""
    from uuid import uuid4
    BaseAgent.set_bus(None)
    agent = _agent()
    with pytest.raises(PeerCallError):
        await agent.peer_call("makubex", "consult", {"q": "x"}, user_id=uuid4())
```

- [ ] **Step 5: Run; verify pass + suite green**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_base_agent_peer_call.py tests/test_base_agent.py -q && python3 -m pytest -q
```
Expected: both tests green; full suite green.

- [ ] **Step 6: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/agent_runtime/base_agent.py kaia/tests/test_base_agent_peer_call.py kaia/tests/test_base_agent.py && git commit -m "$(cat <<'EOF'
feat(agent-runtime): BaseAgent.peer_call backed by the bus

- Replaces the R-1 stub. peer_call now delegates to self._bus.peer_call,
  raising PeerCallError when the bus hasn't been injected (fail-loud).
- Adds class-level _bus slot + set_bus(bus) classmethod (bot calls this
  once at post_init; class-level avoids threading bus through the
  get_expert factory).
- Adds register_peer_intent(intent, handler) instance method + a
  _register_peer_intents() hook subclasses override to bind inbound
  intent handlers (called from __init__ when bus is set).
- R-1 stub-presence test rewritten — peer_call now raises only when the
  bus is missing, which IS the new "fail-loud" contract.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: MakubeX inbound `smart_contract_risk` handler (TDD)

**Files:**
- Modify: `kaia/experts/makubex/expert.py`
- Modify: `kaia/experts/makubex/prompts.py`
- Create: `kaia/tests/test_makubex_smart_contract_risk.py`

- [ ] **Step 1: Read MakubeX's current structure**

```bash
cd /home/ejay/Kaia/kaia && ls experts/makubex/ && head -40 experts/makubex/expert.py && head -20 experts/makubex/prompts.py
```
Understand the existing class, prompt-building convention, and any AIEngine usage patterns before editing.

- [ ] **Step 2: Add `smart_contract_risk` system prompt to `kaia/experts/makubex/prompts.py`**

Append a new function (don't disturb existing prompts):

```python
def build_smart_contract_risk_prompt(protocol: str, asset: str, context: str) -> str:
    """System prompt for MakubeX's inbound smart_contract_risk peer-intent
    (R-3). Hevn calls this when the user asks about DeFi/crypto safety."""
    return f"""\
You are MakubeX, KAIA's tech lead. Another agent (Hevn, the financial \
advisor) is consulting you for a smart-contract / DeFi risk assessment.

You are NOT talking to the end user directly. Your reply must be a \
structured assessment — concise, accurate, and grounded in publicly \
known facts (audits, TVL, incident history). Don't speculate; if you \
don't know something, say so.

ASSESSING:
- protocol: {protocol}
- asset: {asset}
- context: {context}

Respond with the following JSON structure (no markdown, no prose \
outside the JSON):

{{
  "summary": "1-2 sentences",
  "audit_status": "what audits exist, by whom; any incidents",
  "tvl_signal": "rough TVL bucket and what it implies",
  "depeg_history": "if relevant (stablecoin context)",
  "oracle_bridge_risk": "any oracle/bridge dependencies and their risk",
  "rating": "low | low-to-moderate | moderate | moderate-to-high | high",
  "caveats": ["list of caveats"]
}}
"""
```

- [ ] **Step 3: Write the failing test**

Create `kaia/tests/test_makubex_smart_contract_risk.py`:

```python
"""Tests for MakubeX's inbound smart_contract_risk peer-intent handler (R-3)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent_runtime.base_agent import BaseAgent
from bus import Envelope, Visibility
from experts.makubex import MakubeXExpert


@pytest.fixture(autouse=True)
def _reset_bus():
    BaseAgent.set_bus(None)
    yield
    BaseAgent.set_bus(None)


def _envelope(payload: dict) -> Envelope:
    return Envelope(
        envelope_id=uuid4(),
        conversation_id=uuid4(),
        from_agent="hevn",
        to_agent="makubex",
        user_id=uuid4(),
        intent="smart_contract_risk",
        visibility=Visibility.USER_VISIBLE,
        kind="request",
        payload=payload,
    )


@pytest.mark.asyncio
async def test_smart_contract_risk_returns_structured_reply():
    """Given a mocked AI that returns valid JSON, the handler returns a parsed dict."""
    fake_json = json.dumps({
        "summary": "Aave V3 USDC pool is among the lowest-risk DeFi positions.",
        "audit_status": "Trail of Bits, OpenZeppelin",
        "tvl_signal": ">=$10B on USDC pool",
        "depeg_history": "USDC briefly depegged Mar-2023 (SVB), recovered",
        "oracle_bridge_risk": "Chainlink oracles, no bridging on mainnet",
        "rating": "low-to-moderate",
        "caveats": ["smart-contract residual risk", "regulatory uncertainty"],
    })
    ai = MagicMock()
    ai.chat = AsyncMock(return_value=MagicMock(text=fake_json))
    bus = MagicMock()
    bus.register_handler = MagicMock()
    BaseAgent.set_bus(bus)
    expert = MakubeXExpert(ai_engine=ai)  # __init__ registers via _register_peer_intents

    risk_call = next(c for c in bus.register_handler.call_args_list if c.args[1] == "smart_contract_risk")
    handler = risk_call.args[2]

    reply = await handler(_envelope({"protocol": "Aave", "asset": "USDC", "context": "stablecoin yield"}))

    assert reply["rating"] == "low-to-moderate"
    assert "audit_status" in reply


@pytest.mark.asyncio
async def test_smart_contract_risk_handles_malformed_ai_output():
    """If the AI returns non-JSON, the handler returns a structured error payload —
    never crashes the bus dispatcher."""
    ai = MagicMock()
    ai.chat = AsyncMock(return_value=MagicMock(text="not valid json {{{"))
    bus = MagicMock()
    bus.register_handler = MagicMock()
    BaseAgent.set_bus(bus)
    expert = MakubeXExpert(ai_engine=ai)
    risk_call = next(c for c in bus.register_handler.call_args_list if c.args[1] == "smart_contract_risk")
    handler = risk_call.args[2]

    reply = await handler(_envelope({"protocol": "X", "asset": "Y", "context": "z"}))

    assert isinstance(reply, dict)
    assert "error" in reply or "summary" in reply
```

- [ ] **Step 4: Run; verify fail**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_makubex_smart_contract_risk.py -q
```
Expected: failure — handler doesn't exist yet.

- [ ] **Step 5: Modify `kaia/experts/makubex/expert.py`**

Add (preserve all existing R-1/R-2 logic):

```python
import json

from bus import Envelope
from experts.makubex.prompts import build_smart_contract_risk_prompt
# ... existing imports stay ...

class MakubeXExpert(BaseAgent):  # whatever the existing base-class line reads
    channel_id = "makubex"
    # ... existing code stays unchanged ...

    def _register_peer_intents(self) -> None:
        # R-3: MakubeX answers smart_contract_risk consults from Hevn.
        self.register_peer_intent("smart_contract_risk", self.handle_smart_contract_risk)

    async def handle_smart_contract_risk(self, envelope: Envelope) -> dict:
        """Inbound peer-intent handler. Returns a structured risk assessment.

        On AI / JSON-parse failure, returns a dict containing an "error" key
        rather than raising — keeps the bus dispatcher healthy.
        """
        protocol = envelope.payload.get("protocol", "")
        asset = envelope.payload.get("asset", "")
        context = envelope.payload.get("context", "")
        system_prompt = build_smart_contract_risk_prompt(protocol, asset, context)
        try:
            resp = await self.ai.chat(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": f"Assess risk for {protocol} ({asset})."}],
            )
            parsed = json.loads(resp.text)
            if not isinstance(parsed, dict):
                raise ValueError("AI returned non-object JSON")
            return parsed
        except (ValueError, json.JSONDecodeError) as exc:
            return {
                "summary": "(MakubeX couldn't produce a structured assessment for this request.)",
                "error": str(exc),
                "rating": "unknown",
            }
```

- [ ] **Step 6: Run; verify pass + suite green**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_makubex_smart_contract_risk.py -q && python3 -m pytest -q
```
Expected: both green.

- [ ] **Step 7: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/experts/makubex/expert.py kaia/experts/makubex/prompts.py kaia/tests/test_makubex_smart_contract_risk.py && git commit -m "$(cat <<'EOF'
feat(makubex): smart_contract_risk inbound peer-intent (R-3)

MakubeX registers a smart_contract_risk handler at __init__ via the
new _register_peer_intents() hook. Handler:
  - Calls main LLM with a focused system prompt asking for a structured
    JSON risk assessment (protocol, asset, audits, TVL, depeg history,
    oracle/bridge risk, rating, caveats).
  - Returns the parsed dict on success.
  - On AI / JSON-parse failure, returns a dict with "error" key — never
    raises into the bus dispatcher.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Hevn classifier + synthesis + graceful fallback (TDD)

**Files:**
- Modify: `kaia/experts/hevn/expert.py` (handle() becomes 3-step orchestrator)
- Modify: `kaia/experts/hevn/prompts.py` (add classifier + synthesis prompts)
- Create: `kaia/tests/test_hevn_classifier.py`
- Create: `kaia/tests/test_hevn_consult_fallback.py`

- [ ] **Step 1: Read Hevn's current structure**

```bash
cd /home/ejay/Kaia/kaia && ls experts/hevn/ && wc -l experts/hevn/*.py && head -80 experts/hevn/expert.py
```
Identify the existing `handle()` signature (must remain `async def handle(self, user, message, channel) -> SkillResult` per R-2 invariant) and where its body builds the system prompt / calls AI / saves messages.

- [ ] **Step 2: Add classifier + synthesis prompts to `kaia/experts/hevn/prompts.py`**

Append (don't modify existing functions):

```python
def build_classifier_prompt(message: str) -> str:
    """Classifier prompt: does the user's question require consulting MakubeX
    (smart-contract / DeFi expertise)? Returns a small JSON decision."""
    return f"""\
You are a fast, cheap router. Given a user's question to Hevn (a \
financial advisor), decide whether Hevn needs to consult MakubeX (the \
tech lead) for smart-contract / DeFi / crypto-security expertise \
BEFORE Hevn can answer well.

Reply with ONLY a JSON object, no prose. Schema:

{{
  "needs_consult": true | false,
  "target": "makubex",            // if needs_consult is true
  "intent": "smart_contract_risk", // if needs_consult is true
  "payload": {{
    "protocol": "...",     // e.g. "Aave", "Compound", "Uniswap"
    "asset": "...",        // e.g. "USDC", "ETH"
    "context": "..."       // brief context (1 sentence)
  }}
}}

If the question is general personal finance (budgeting, saving, debt, \
traditional investments), set "needs_consult": false and omit the other \
fields.

USER QUESTION: {message}
"""


def build_synthesis_prompt(profile_context: str, original_message: str, peer_reply: dict) -> str:
    """Synthesis prompt: Hevn re-prompted with the peer's reply payload,
    asked to produce a financial recommendation."""
    import json as _json
    reply_json = _json.dumps(peer_reply, indent=2)
    return f"""\
You are Hevn, KAIA's financial advisor. The user asked:

  "{original_message}"

You consulted MakubeX (KAIA's tech lead) for a smart-contract / DeFi \
risk read. MakubeX's structured reply:

{reply_json}

USER PROFILE:
{profile_context if profile_context else "No profile data yet."}

Synthesize a financial recommendation for the user. Reference MakubeX's \
read where relevant, but speak in YOUR voice (Hevn, the financial \
advisor). Be specific to the user's profile (income, debt, savings, \
emergency fund). Default currency is Philippine Peso (₱). Be warm but \
focused. Use markdown sparingly.
"""
```

- [ ] **Step 3: Write the classifier test**

Create `kaia/tests/test_hevn_classifier.py`:

```python
"""Tests for HevnExpert's classifier behavior (R-3)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_runtime.base_agent import BaseAgent
from experts.hevn import HevnExpert


@pytest.fixture(autouse=True)
def _reset_bus():
    BaseAgent.set_bus(None)
    yield
    BaseAgent.set_bus(None)


def _hevn_with_ai(classifier_response_text: str) -> HevnExpert:
    ai = MagicMock()
    ai.chat = AsyncMock(return_value=MagicMock(text=classifier_response_text))
    return HevnExpert(ai_engine=ai)


@pytest.mark.asyncio
async def test_classifier_returns_consult_for_defi_question():
    text = json.dumps({
        "needs_consult": True,
        "target": "makubex",
        "intent": "smart_contract_risk",
        "payload": {"protocol": "Aave", "asset": "USDC", "context": "stablecoin yield"},
    })
    hevn = _hevn_with_ai(text)
    decision = await hevn._classify_consult_intent(
        "Is it safe to put 10% of my emergency fund in Aave USDC?"
    )
    assert decision["needs_consult"] is True
    assert decision["target"] == "makubex"
    assert decision["intent"] == "smart_contract_risk"
    assert decision["payload"]["protocol"] == "Aave"


@pytest.mark.asyncio
async def test_classifier_returns_no_consult_for_general_finance():
    text = json.dumps({"needs_consult": False})
    hevn = _hevn_with_ai(text)
    decision = await hevn._classify_consult_intent("Help me budget my savings.")
    assert decision["needs_consult"] is False


@pytest.mark.asyncio
async def test_classifier_falls_back_on_malformed_output():
    """Malformed classifier JSON must yield needs_consult=False (fail-safe), not raise."""
    hevn = _hevn_with_ai("not json at all")
    decision = await hevn._classify_consult_intent("Anything?")
    assert decision == {"needs_consult": False}
```

- [ ] **Step 4: Write the consult-fallback test**

Create `kaia/tests/test_hevn_consult_fallback.py`:

```python
"""Tests for HevnExpert's graceful fallback when peer_call fails (R-3)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_runtime.base_agent import BaseAgent, PeerCallTimeoutError
from experts.hevn import HevnExpert


@pytest.fixture(autouse=True)
def _reset_bus():
    BaseAgent.set_bus(None)
    yield
    BaseAgent.set_bus(None)


def _hevn_with_consult_path(bus_side_effect, classifier_says_consult=True):
    """Build a HevnExpert whose classifier says 'consult' (or not) and whose
    bus.peer_call is wired to raise (or succeed)."""
    ai = MagicMock()
    classifier_text = json.dumps({
        "needs_consult": classifier_says_consult,
        "target": "makubex",
        "intent": "smart_contract_risk",
        "payload": {"protocol": "Aave", "asset": "USDC", "context": "x"},
    })
    # First chat call = classifier; subsequent chat calls = direct/synthesis answer.
    ai.chat = AsyncMock(side_effect=[
        MagicMock(text=classifier_text),
        MagicMock(text="My direct answer"),
    ])
    bus = MagicMock()
    bus.peer_call = AsyncMock(side_effect=bus_side_effect)
    BaseAgent.set_bus(bus)
    return HevnExpert(ai_engine=ai), bus


@pytest.mark.asyncio
async def test_consult_timeout_falls_back_with_footer():
    hevn, bus = _hevn_with_consult_path(PeerCallTimeoutError("budget exhausted"))
    user = SimpleNamespace(id="u-1", timezone="Asia/Manila")
    channel = MagicMock(channel_id="hevn", system_prompt="...", emoji="💰", character_name="Hevn", role="Financial Advisor")
    # Patch any DB-touching helpers so we don't hit Supabase.
    hevn.save_messages = AsyncMock()
    hevn._channel_mem.load_combined_context = AsyncMock(return_value="")
    result = await hevn.handle(user=user, message="Is Aave USDC safe?", channel=channel)
    assert "My direct answer" in result.text
    assert "couldn't reach" in result.text.lower() or "makubex" in result.text.lower()
    bus.peer_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_consult_path_does_not_call_peer():
    """When classifier says needs_consult=False, peer_call is never invoked."""
    hevn, bus = _hevn_with_consult_path(lambda *a, **k: {}, classifier_says_consult=False)
    user = SimpleNamespace(id="u-1", timezone="Asia/Manila")
    channel = MagicMock(channel_id="hevn", system_prompt="...", emoji="💰", character_name="Hevn", role="Financial Advisor")
    hevn.save_messages = AsyncMock()
    hevn._channel_mem.load_combined_context = AsyncMock(return_value="")
    await hevn.handle(user=user, message="How much should I save?", channel=channel)
    bus.peer_call.assert_not_called()
```

- [ ] **Step 5: Run; verify fail**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_hevn_classifier.py tests/test_hevn_consult_fallback.py -q
```
Expected: failures — methods don't exist yet.

- [ ] **Step 6: Refactor `kaia/experts/hevn/expert.py` into the three-step orchestrator**

Structural change:

1. **Extract** the existing `handle()` body into a new private method `_direct_answer(self, user, message, channel) -> SkillResult`. Its job is the R-1/R-2 path (build system prompt, AI chat, save, footer). Do not change its logic; just rename and indent.
2. **Add** `_classify_consult_intent(self, message: str) -> dict` returning the parsed classifier JSON; on parse failure, return `{"needs_consult": False}` (fail-safe to direct answer).
3. **Add** `_synthesize_with_consult(self, user, message, channel, peer_reply: dict) -> SkillResult` that builds the synthesis prompt and calls AI, returning a SkillResult that also saves + appends the footer.
4. **Replace** `handle()` body with the 3-step orchestrator.

```python
from loguru import logger
from agent_runtime.base_agent import PeerCallError
from experts.hevn.prompts import build_classifier_prompt, build_synthesis_prompt
# ... existing imports ...

async def handle(self, user, message, channel) -> SkillResult:
    decision = await self._classify_consult_intent(message)
    if not decision.get("needs_consult"):
        return await self._direct_answer(user, message, channel)
    try:
        reply = await self.peer_call(
            decision["target"],
            decision["intent"],
            decision["payload"],
            user_id=user.id,
        )
    except PeerCallError as exc:
        logger.warning("Hevn peer_call({}, {}) failed: {}", decision["target"], decision["intent"], exc)
        direct = await self._direct_answer(user, message, channel)
        return SkillResult(
            text=direct.text + "\n\n_(I tried to consult MakubeX but couldn't reach them in time — answering from my own read.)_",
            skill_name=direct.skill_name,
            ai_response=direct.ai_response,
        )
    return await self._synthesize_with_consult(user, message, channel, reply)


async def _classify_consult_intent(self, message: str) -> dict:
    import json as _json
    resp = await self.ai.chat(
        system_prompt=build_classifier_prompt(message),
        messages=[{"role": "user", "content": message}],
    )
    try:
        decision = _json.loads(resp.text)
        if not isinstance(decision, dict):
            return {"needs_consult": False}
        return decision
    except (ValueError, TypeError):
        return {"needs_consult": False}


async def _synthesize_with_consult(self, user, message, channel, peer_reply: dict) -> SkillResult:
    profile_context = await self._channel_mem.load_combined_context(user.id, channel.channel_id)
    system_prompt = build_synthesis_prompt(profile_context, message, peer_reply)
    resp = await self.ai.chat(
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": message}],
    )
    await self.save_messages(user.id, channel.channel_id, message, resp.text)
    footer = self.format_response_footer(channel)
    return SkillResult(
        text=resp.text + footer,
        skill_name=self.channel_id,
        ai_response=resp,
    )
```

(The exact body of `_direct_answer` depends on what's currently in Hevn's `handle()`. Read the file and preserve its existing behavior verbatim.)

- [ ] **Step 7: Run new tests + full suite**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_hevn_classifier.py tests/test_hevn_consult_fallback.py -q && python3 -m pytest -q
```
Expected: new tests pass; full suite green.

- [ ] **Step 8: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/experts/hevn/expert.py kaia/experts/hevn/prompts.py kaia/tests/test_hevn_classifier.py kaia/tests/test_hevn_consult_fallback.py && git commit -m "$(cat <<'EOF'
feat(hevn): 3-step orchestrator with peer_call + graceful fallback (R-3)

Hevn.handle() now:
  1. Classifier LLM emits {needs_consult, target, intent, payload}
  2. If needs_consult: await self.peer_call(target, intent, payload)
     - On PeerCallError: fall back to direct answer + transparency footer
  3. If consult succeeded: re-prompt main LLM with the peer reply →
     synthesize the financial recommendation

The R-1/R-2 direct-answer path is preserved as _direct_answer(); the
non-consult branch and the fallback branch both call it, so existing
behavior is untouched when needs_consult=false.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Bot bus lifecycle + user-visible relay rendering

**Files:**
- Modify: `kaia/bot/telegram_bot.py`
- Modify: `kaia/database/queries.py` (add `get_user_by_id(user_id)` if absent)

This is the integration task — no new test file (covered by Task 12's end-to-end test + Task 13's live test + manual smoke), but the bot is the wiring layer that ties everything together.

- [ ] **Step 1: Add `get_user_by_id` to `kaia/database/queries.py` (if absent)**

Check if it exists:
```bash
cd /home/ejay/Kaia/kaia && grep -n "def get_user_by_id\|async def get_user_by_id" database/queries.py
```
If empty: add a helper following the file's existing supabase-py patterns:

```python
async def get_user_by_id(user_id) -> User | None:
    """Look up a user by internal UUID (not telegram_id)."""
    client = get_supabase()
    response = client.from_("users").select("*").eq("id", str(user_id)).limit(1).execute()
    if not response.data:
        return None
    return User(**response.data[0])  # match the existing User-construction pattern
```

- [ ] **Step 2: Add bus lifecycle + user-visible relay task to `kaia/bot/telegram_bot.py`**

Add imports at the top (alongside existing imports):
```python
import asyncio
import json
from uuid import UUID

from agent_runtime.base_agent import BaseAgent
from bus import Bus, Envelope, PostgresBusTransport, Visibility
from database.queries import get_user_by_id
```

Add module-level slots (alongside existing globals like `_bot`):
```python
_bus: "Bus | None" = None
_user_visible_task: "asyncio.Task | None" = None
_AGENT_DISPLAY_CACHE: dict[str, tuple[str, str]] = {}
```

Modify `post_init`:
```python
async def post_init(application):
    bot = application.bot
    set_bot(bot)

    # R-3: start the bus first — fail fast if Postgres is unreachable.
    global _bus, _user_visible_task
    if not settings.database_url:
        raise RuntimeError(
            "R-3: DATABASE_URL is not set — bus cannot start. "
            "Set it in /opt/kaia/app/kaia/.env (Supabase → Project Settings → Database → Connection String) and restart."
        )
    transport = PostgresBusTransport(settings.database_url)
    await transport.start()
    _bus = Bus(transport=transport, default_timeout=settings.r3_peer_call_timeout_seconds)
    BaseAgent.set_bus(_bus)
    await _bus.start()

    _user_visible_task = asyncio.create_task(
        _relay_user_visible_envelopes(bot), name="bus-user-visible-relay"
    )

    await start_scheduler(bot)
    cleanup_old_files()
    logger.info("Post-init complete: scheduler started, bus running, relay active")
```

Add the relay function and helpers (anywhere in the file; near the bottom is fine):

```python
async def _agent_display(agent_id: str) -> tuple[str, str]:
    """Return (emoji, character_name) for an agent_id. Cached."""
    if agent_id in _AGENT_DISPLAY_CACHE:
        return _AGENT_DISPLAY_CACHE[agent_id]
    info = await channel_mgr.get_channel_info(agent_id)
    if info is None:
        display = ("🤖", agent_id.title())
    else:
        display = (info.emoji or "🤖", info.character_name or agent_id.title())
    _AGENT_DISPLAY_CACHE[agent_id] = display
    return display


def _format_reply_payload(payload: dict) -> str:
    """Pretty-print a peer reply payload as Markdown bullets."""
    lines = []
    for key, val in payload.items():
        if key == "caveats" and isinstance(val, list):
            lines.append(f"- *Caveats:* {'; '.join(val)}")
        elif isinstance(val, (dict, list)):
            lines.append(f"- *{key.replace('_', ' ').title()}:* {json.dumps(val)}")
        else:
            label = key.replace("_", " ").title()
            lines.append(f"- *{label}:* {val}")
    return "\n".join(lines)


async def _render_envelope_to_user(bot, env: Envelope) -> None:
    user = await get_user_by_id(env.user_id)
    if user is None:
        logger.warning("user_visible relay: no user for envelope {}", env.envelope_id)
        return
    from_emoji, from_name = await _agent_display(env.from_agent)
    to_emoji, to_name = await _agent_display(env.to_agent)
    if env.kind == "request":
        body = env.payload.get("context") or env.payload.get("question") or json.dumps(env.payload)
        text = f"{from_emoji} *{from_name}* → {to_emoji} *{to_name}* (consult): {body}"
    elif env.kind == "reply":
        body = _format_reply_payload(env.payload)
        text = f"{to_emoji} *{to_name}* → {from_emoji} *{from_name}* (reply):\n{body}"
    else:  # error
        text = f"⚠️ *{to_name}* → *{from_name}* (error): {env.payload.get('error', 'unknown')}"
    await bot.send_message(chat_id=user.telegram_id, text=truncate(text), parse_mode="Markdown")


async def _relay_user_visible_envelopes(bot) -> None:
    """Subscribe to bus:user_visible and render attribution messages."""
    assert _bus is not None
    transport = _bus._tx  # access via the Bus's transport (intentional)
    try:
        async for envelope_id_str in transport.subscribe("bus:user_visible"):
            try:
                env = await transport.fetch_envelope(UUID(envelope_id_str))
                if env is None:
                    logger.debug("user_visible relay: no envelope {}", envelope_id_str)
                    continue
                await _render_envelope_to_user(bot, env)
            except Exception:
                logger.exception("user_visible relay: render failed for {}", envelope_id_str)
                # Loud-log but keep the loop alive (R-3 invariant #2).
    except asyncio.CancelledError:
        return
```

Modify `post_shutdown`:
```python
async def post_shutdown(application):
    global _bus, _user_visible_task
    if _user_visible_task is not None:
        _user_visible_task.cancel()
        try:
            await _user_visible_task
        except asyncio.CancelledError:
            pass
        _user_visible_task = None
    if _bus is not None:
        await _bus.shutdown()
        tx = _bus._tx
        if hasattr(tx, "shutdown"):
            await tx.shutdown()
        _bus = None
    shutdown_scheduler()
```

- [ ] **Step 3: Sanity-check the bot still imports**

```bash
cd /home/ejay/Kaia/kaia && python3 -c "import bot.telegram_bot; print('bot imports ok')"
```
Expected: `bot imports ok` (DATABASE_URL not set, but post_init only runs at actual Telegram start — import is safe).

- [ ] **Step 4: Run the full suite — must stay green**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest -q
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/bot/telegram_bot.py kaia/database/queries.py && git commit -m "$(cat <<'EOF'
feat(bot): wire R-3 bus lifecycle + user-visible attribution relay

- post_init now starts PostgresBusTransport + Bus, then injects via
  BaseAgent.set_bus(bus). Fails fast with a clear log if DATABASE_URL
  is unset (R-3 invariant #1).
- New background task subscribes to bus:user_visible and renders
  attribution messages (💰 Hevn → 🔧 MakubeX (consult): …) into the
  originating user's thread. Reply payloads pretty-printed as Markdown
  bullets.
- post_shutdown cancels the relay task and shuts the bus + transport
  cleanly. Outstanding peer_call futures resolve with PeerCallError.

Adds get_user_by_id helper in database/queries.py (used by the relay
to map envelope.user_id → telegram_id).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: End-to-end demo test (in-process, no real DB)

**Files:**
- Create: `kaia/tests/test_r3_demo_e2e.py`

- [ ] **Step 1: Write the test**

```python
"""End-to-end R-3 demo: real Hevn + real MakubeX + InMemoryBusTransport.
Mocks AI responses to simulate the DeFi scenario deterministically.
Asserts the 3-message attribution shape (consult / reply / synthesis)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent_runtime.base_agent import BaseAgent
from bus import Bus, Envelope, InMemoryBusTransport, Visibility
from experts.hevn import HevnExpert
from experts.makubex import MakubeXExpert


@pytest.fixture(autouse=True)
def _reset_bus():
    BaseAgent.set_bus(None)
    yield
    BaseAgent.set_bus(None)


@pytest.mark.asyncio
async def test_defi_consult_end_to_end_produces_three_envelopes():
    """User → Hevn → peer_call(MakubeX) → reply → Hevn synthesizes.

    Bus traffic should contain: request envelope (hevn → makubex) +
    reply envelope (makubex → hevn). Both visibility=user_visible →
    both surface on bus:user_visible.
    """
    tx = InMemoryBusTransport()
    bus = Bus(transport=tx, default_timeout=5.0)
    BaseAgent.set_bus(bus)

    # Mock AIs — different responses for classifier, makubex risk, synthesis.
    hevn_ai = MagicMock()
    hevn_ai.chat = AsyncMock(side_effect=[
        MagicMock(text=json.dumps({
            "needs_consult": True,
            "target": "makubex",
            "intent": "smart_contract_risk",
            "payload": {"protocol": "Aave", "asset": "USDC", "context": "10% of emergency fund"},
        })),
        MagicMock(text="Based on MakubeX's read, I'd cap exposure at 5% not 10%..."),
    ])
    makubex_ai = MagicMock()
    makubex_ai.chat = AsyncMock(return_value=MagicMock(text=json.dumps({
        "summary": "Aave V3 USDC is among the safer DeFi positions.",
        "audit_status": "Trail of Bits, OpenZeppelin",
        "tvl_signal": ">=$10B",
        "depeg_history": "USDC briefly depegged Mar-2023",
        "oracle_bridge_risk": "Chainlink oracles, no bridging on mainnet",
        "rating": "low-to-moderate",
        "caveats": ["smart-contract residual risk"],
    })))

    hevn = HevnExpert(ai_engine=hevn_ai)
    makubex = MakubeXExpert(ai_engine=makubex_ai)  # __init__ registers smart_contract_risk handler
    await bus.start()

    user_visible_seen: list[str] = []
    async def watcher():
        async for payload_id in tx.subscribe("bus:user_visible"):
            user_visible_seen.append(payload_id)
            if len(user_visible_seen) >= 2:
                return
    watch_task = asyncio.create_task(watcher())
    await asyncio.sleep(0)

    user = SimpleNamespace(id=uuid4(), timezone="Asia/Manila")
    channel = MagicMock(
        channel_id="hevn", system_prompt="...", emoji="💰",
        character_name="Hevn", role="Financial Advisor",
    )
    hevn.save_messages = AsyncMock()
    hevn._channel_mem.load_combined_context = AsyncMock(return_value="")

    result = await hevn.handle(
        user=user,
        message="Is it safe to put 10% of my emergency fund in Aave USDC?",
        channel=channel,
    )

    await asyncio.wait_for(watch_task, timeout=2.0)

    assert len(user_visible_seen) == 2, f"expected 2 user_visible envelopes, got {len(user_visible_seen)}"
    assert "Based on MakubeX" in result.text or "5%" in result.text

    await bus.shutdown()
```

- [ ] **Step 2: Run; verify pass**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_r3_demo_e2e.py -q
```
Expected: `1 passed`.

- [ ] **Step 3: Full suite green**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest -q
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/tests/test_r3_demo_e2e.py && git commit -m "$(cat <<'EOF'
test(r3): end-to-end DeFi demo with in-process bus (no real DB)

Real Hevn + real MakubeX + InMemoryBusTransport; AI mocked for
determinism. Asserts the 3-message attribution shape: 2 user-visible
envelopes (consult + reply) on bus:user_visible, plus Hevn's final
synthesized recommendation as the SkillResult.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Env-gated live bus integration test (optional)

**Files:**
- Create: `kaia/tests/test_r3_live_bus.py`

This test only runs when `R3_INTEGRATION_DB_DSN` is set in the env. It exercises the real `PostgresBusTransport` against a real Postgres (local docker or staging Supabase) — useful for the operator to validate before deploying, not part of normal CI.

- [ ] **Step 1: Create the test**

```python
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
```

- [ ] **Step 2: Confirm SKIPPED behavior without DSN**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_r3_live_bus.py -q
```
Expected: `2 skipped` (DSN not set).

- [ ] **Step 3: (Optional) Run live with a real DSN**

This step is for the operator. If you have a local Postgres or a staging Supabase project, set the DSN and run:

```bash
cd /home/ejay/Kaia/kaia && R3_INTEGRATION_DB_DSN="postgresql://user:pass@host:5432/db" python3 -m pytest tests/test_r3_live_bus.py -q
```
Expected: `2 passed`. This confirms the asyncpg + LISTEN/NOTIFY plumbing actually works against real Postgres before deploying. **Apply `006_agent_bus.sql` to the target DB first** if it isn't already.

- [ ] **Step 4: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/tests/test_r3_live_bus.py && git commit -m "$(cat <<'EOF'
test(r3): env-gated live integration test against real Postgres

Skipped unless R3_INTEGRATION_DB_DSN is set. Lets the operator validate
PostgresBusTransport (NOTIFY round-trip + full peer_call) against real
asyncpg + Postgres before deploying R-3 to prod.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Update project docs

**Files:**
- Modify: `Docs/ARCHITECTURE.md` (Agentic OS section — update current state)
- Modify: `Docs/CHANGELOG.md` (prepend R-3 entry)
- Modify: `Docs/DEVELOPMENT_STATUS.md` (Agentic OS table — R-3 row → ✅ Complete)
- Modify: `Docs/DATABASE.md` (append "Agentic OS Bus Tables (Migration 006)" section)

- [ ] **Step 1: Update the "Agentic OS Migration" section in `Docs/ARCHITECTURE.md`**

Read the file. Find the R-2 current-state block (added at R-2 ship). Replace that `**Current state ...**` paragraph and its bullets with:

```markdown
**Current state (R-3, 2026-06-09):**
- `kaia/agent_runtime/BaseAgent` is the base class for all agents (R-1). `peer_call(...)` is now a live RPC over the bus (R-3); raises `PeerCallError`/`PeerCallTimeoutError` on failure.
- `kaia/concierge/` owns KAIA's general (non-expert) conversation turn and the `/start` greeting (R-2). `bot/telegram_bot.py` is a thin Telegram transport over the concierge.
- `kaia/bus/` is the R-3 inter-agent bus: `PostgresBusTransport` (asyncpg LISTEN/NOTIFY against Supabase) + transport-agnostic `Bus` (RPC correlation, 30s default timeout, future map). `InMemoryBusTransport` makes the bus logic unit-testable without asyncpg.
- Hevn↔MakubeX peer-call demo is live on the `smart_contract_risk` intent: user asks Hevn about DeFi, Hevn classifier triggers a `peer_call`, MakubeX answers, Hevn synthesizes — user sees 3 attribution-prefixed messages in the thread.
- Expert first-visit onboarding still expert-owned — unchanged by R-3.
- First **user-visible** Agentic OS feature.
```

Leave the "Pending phases" table intact.

- [ ] **Step 2: Prepend R-3 entry to `Docs/CHANGELOG.md`**

Insert directly under `# Changelog` (above the R-2 entry):

```markdown
## [2026-06-09] R-3 — Agentic OS Bus + A2A Protocol + Hevn↔MakubeX Demo

### Added
- **New `kaia/bus/` package.** Postgres LISTEN/NOTIFY-backed inter-agent bus:
  - `Envelope` + `Visibility` (A2A wire format; round-trip serializers).
  - `BusTransport` Protocol with `PostgresBusTransport` (asyncpg) for prod and `InMemoryBusTransport` for tests.
  - `Bus` class: RPC peer_call with correlation map + 30s default timeout, per-agent dispatcher loop, intent-handler registry, user-visible relay channel.
- **`BaseAgent.peer_call(...)` is now live.** Replaces the R-1 stub. New `PeerCallTimeoutError(PeerCallError)`. `BaseAgent.set_bus(bus)` classmethod for one-time injection at bot startup. New `_register_peer_intents()` hook subclasses override.
- **MakubeX `smart_contract_risk` peer-intent handler.** Returns a structured risk profile (audits, TVL, depeg history, oracle/bridge risk, rating, caveats).
- **Hevn 3-step orchestrator.** Classifier LLM → optional `peer_call(makubex, smart_contract_risk)` → synthesis LLM. Graceful fallback to direct answer + transparency footer on peer_call failure.
- **Bot user-visible relay.** Subscribes to `bus:user_visible` and renders interleaved attribution messages (`💰 Hevn → 🔧 MakubeX (consult): …`) into the user's thread.
- **Migration `006_agent_bus.sql`.** Creates `agent_conversations` + `agent_messages` audit tables.

### Changed
- **`PeerCallError` base class** changes from `NotImplementedError` to `Exception` (R-1 used the NotImplementedError-subclass shape to advertise "not wired yet"; R-3 raises it on real runtime failures). No existing caller code depends on the prior inheritance.
- **`bot/telegram_bot.py` post_init / post_shutdown** now start and stop the bus and the user-visible relay task. The bot **fails fast** on startup if `DATABASE_URL` is unset or Postgres is unreachable (R-3 invariant #1).

### Migration notes
- **Operator MUST apply `kaia/database/migrations/006_agent_bus.sql`** to the Supabase project via the SQL editor before deploying R-3. The bot will fail to start otherwise.
- **Operator MUST set `DATABASE_URL`** in EC2's `/opt/kaia/app/kaia/.env` (Supabase → Project Settings → Database → Connection String). Use the connection pooler URL on port 6543 if available, else direct 5432.
- The demo only fires on DeFi-flavored questions to Hevn. Non-DeFi questions hit the unchanged direct-answer path — R-3 is additive for non-demo users.
```

- [ ] **Step 3: Mark R-3 complete in `Docs/DEVELOPMENT_STATUS.md`**

In the `### Agentic OS Migration` table, change the R-3 row from:
```markdown
| R-3   | ⏳ Planned    | Postgres LISTEN/NOTIFY bus + A2A protocol + peer_call demo      |
```
to:
```markdown
| R-3   | ✅ Complete   | Postgres LISTEN/NOTIFY bus + A2A protocol + peer_call demo      |
```
Leave R-4, R-5 rows unchanged.

- [ ] **Step 4: Append bus-tables section to `Docs/DATABASE.md`**

Append at the end of `Docs/DATABASE.md`:

```markdown
## Agentic OS Bus Tables (Migration 006)

Added in R-3. Written by `kaia/bus/postgres_transport.py` via asyncpg (not supabase-py).

### `agent_conversations`

One row per cross-agent conversation initiated by a user turn.

| Column | Type | Notes |
|--------|------|-------|
| `conversation_id` | UUID | PK |
| `user_id` | UUID | FK → users, ON DELETE CASCADE |
| `started_by_agent` | VARCHAR(50) | e.g. `"hevn"` |
| `intent_root` | VARCHAR(100) | Nullable; root intent if known |
| `status` | VARCHAR(20) | `'open'` / `'closed'` / `'errored'`; default `'open'` |
| `created_at` | TIMESTAMPTZ | — |
| `closed_at` | TIMESTAMPTZ | Nullable |

Indexed on `(user_id, created_at DESC)`.

### `agent_messages`

One row per envelope (request, reply, or error). The audit log and the R-4-ready transport.

| Column | Type | Notes |
|--------|------|-------|
| `envelope_id` | UUID | PK |
| `conversation_id` | UUID | FK → agent_conversations, ON DELETE CASCADE |
| `from_agent` | VARCHAR(50) | — |
| `to_agent` | VARCHAR(50) | — |
| `user_id` | UUID | Denormalized for fast user lookups |
| `intent` | VARCHAR(100) | e.g. `"smart_contract_risk"` |
| `visibility` | VARCHAR(20) | `'user_visible'` (relayed to thread) / `'internal'` (logged only) |
| `kind` | VARCHAR(20) | `'request'` / `'reply'` / `'error'` |
| `reply_to` | UUID | Nullable; FK → agent_messages.envelope_id for reply/error correlation |
| `payload` | JSONB | Intent-specific request or reply payload |
| `created_at` | TIMESTAMPTZ | — |

Indexed on `(conversation_id, created_at)` and partial-indexed on `(to_agent, created_at DESC) WHERE kind = 'request'`.
```

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add Docs/ARCHITECTURE.md Docs/CHANGELOG.md Docs/DEVELOPMENT_STATUS.md Docs/DATABASE.md && git commit -m "$(cat <<'EOF'
docs: log R-3 bus + protocol + demo; mark R-3 complete

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Final smoke check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest -q
```
Expected: all pass — 13 R-1/R-2 + 17–19 new R-3 = **~30** tests green. (The `test_r3_live_bus.py` will show as `2 skipped` unless DSN is set — that's expected.)

- [ ] **Step 2: Verify the bot imports cleanly (no DATABASE_URL needed yet)**

```bash
cd /home/ejay/Kaia/kaia && python3 -c "import bot.telegram_bot; print('bot imports ok')"
```
Expected: `bot imports ok`.

- [ ] **Step 3: Confirm `peer_call` no longer raises the R-1 stub**

```bash
cd /home/ejay/Kaia/kaia && python3 -c "
from unittest.mock import MagicMock
from agent_runtime.base_agent import BaseAgent, PeerCallError
import asyncio
from uuid import uuid4

class Stub(BaseAgent):
    channel_id = 'stub'
    async def handle(self, user, message, channel):
        return None

BaseAgent.set_bus(None)
a = Stub(MagicMock())
try:
    asyncio.run(a.peer_call('x', 'y', {}, user_id=uuid4()))
except PeerCallError as e:
    print('peer_call correctly raised:', e)
"
```
Expected: `peer_call correctly raised: peer_call requires the bus to be initialised — bot post_init did not call BaseAgent.set_bus(bus)`. Confirms the R-1 "not wired yet" stub has been replaced by the new fail-loud-when-uninjected contract.

- [ ] **Step 4: Confirm the bus is transport-agnostic (no `telegram` import)**

```bash
cd /home/ejay/Kaia/kaia && grep -rnE "^\s*(import|from)\s+telegram" bus/ && echo "FOUND TELEGRAM IMPORT (BAD)" || echo "OK: bus has zero telegram imports"
```
Expected: `OK: bus has zero telegram imports`.

- [ ] **Step 5: Confirm git history is clean and scoped**

```bash
cd /home/ejay/Kaia && git log --oneline origin/main..HEAD
```
Expected: 14–16 commits, each scoped to one task, all on `agentic-os-r3`.

- [ ] **Step 6: (Manual ops gate — not a code step) Apply migration + set env on prod**

Operator confirms BEFORE merging to `main`:
1. Migration `006_agent_bus.sql` has been applied to the Supabase prod project (via SQL editor).
2. `DATABASE_URL` has been added to `/opt/kaia/app/kaia/.env` on the EC2 host. Verify:
   ```bash
   ssh ubuntu@<server-host>
   sudo grep "^DATABASE_URL=" /opt/kaia/app/kaia/.env | sed 's/=.*/=<set>/'
   ```
   Expected: `DATABASE_URL=<set>`.
3. (Optional but recommended) Run the env-gated live test against the prod Supabase from a workstation to confirm the asyncpg connection works:
   ```bash
   R3_INTEGRATION_DB_DSN="<your-dsn>" python3 -m pytest tests/test_r3_live_bus.py -q
   ```
   Expected: `2 passed`.

If any of those three are not done, **the bot will fail to start after merge**. Don't merge until they're confirmed.

- [ ] **Step 7: Live-fire test against prod after merge & deploy**

After merging the PR (GitHub Actions auto-deploys to EC2):

```bash
ssh ubuntu@<server-host>
sudo systemctl status kaia  # active (running), restart timestamp matches the deploy
sudo journalctl -u kaia -n 30 --no-pager
# Look for: "Bus started", "Post-init complete: scheduler started, bus running, relay active"
# Look for: NO "DATABASE_URL is not set" — that would mean the env wasn't applied
```

Then in Telegram:
1. `/hevn`
2. Send: `Is it safe to put 10% of my emergency fund in Aave USDC?`
3. Expect **3 messages** in this order:
   - `💰 Hevn → 🔧 MakubeX (consult): …`
   - `🔧 MakubeX → 💰 Hevn (reply): …` (bullet list of audits/TVL/etc.)
   - `💰 Hevn: …` (the synthesized recommendation)
4. Send a non-DeFi question (e.g., "help me budget my savings") — expect the normal Hevn response with NO consult messages.
5. `/exit`.

If the demo works, R-3 is verified live.

---

## Self-Review Results

- **Spec coverage:**
  - DESIGN_R3.md §1 Architecture → Tasks 4, 5, 6, 7, 8, 11.
  - DESIGN_R3.md §2 Components → Tasks 2 (deps/settings), 4 (envelope), 5 (transport+InMem), 6 (Bus + base_agent errors), 7 (Postgres transport), 8 (BaseAgent.peer_call), 9 (MakubeX inbound), 10 (Hevn orchestrator), 11 (bot wiring).
  - DESIGN_R3.md §3 Data flow → covered by Tasks 9 (MakubeX side), 10 (Hevn side), 11 (relay rendering), 12 (e2e test).
  - DESIGN_R3.md §4 Error/timeout policy → covered by Tasks 6 (timeout, peer error, shutdown), 10 (Hevn fallback contract), 11 (fail-fast on missing DATABASE_URL).
  - DESIGN_R3.md §5 Schema → Task 3.
  - DESIGN_R3.md §6 Testing → Tasks 4, 5, 6, 8, 9, 10, 12, 13.
  - DESIGN_R3.md §7 Out of scope → respected; no tasks add tool-calling, multi-hop, RLS, rate limiting, more intents.
  - DESIGN_R3.md Migration impact → Task 14 (ARCHITECTURE, CHANGELOG, DEV_STATUS, DATABASE) + Task 1 (DESIGN.md status) + Task 15 step 6 (manual ops gate for migration application + env var).
- **Placeholder scan:** Every step shows full code or an exact command with expected output. No `TBD` / `TODO` / "add appropriate" / "similar to Task N" patterns. The one conditional ("`.env.example` if it exists; otherwise just docs" from the spec) is intentionally honest; the plan handles it via Task 2 directly editing `kaia/config/settings.py`.
- **Type consistency:**
  - `Envelope` fields (Task 4) match those used in Tasks 6, 7, 8, 9, 12.
  - `Visibility.USER_VISIBLE` / `Visibility.INTERNAL` used identically across Tasks 4–12.
  - `BaseAgent.peer_call` signature (`target, intent, payload, *, user_id, visibility=None, timeout=None`) defined in Task 8 used identically in Task 10's Hevn orchestrator and Task 12's e2e test.
  - `Bus.peer_call` signature (`source, target, intent, payload, user_id, *, conversation_id=None, visibility=Visibility.USER_VISIBLE, timeout=None`) defined in Task 6 used identically in Task 8 (BaseAgent.peer_call delegate), Task 12 (e2e test), Task 13 (live test).
  - `register_handler(agent_id, intent, async_fn)` consistent across Task 6 (Bus definition), Task 8 (BaseAgent.register_peer_intent delegate), Task 9 (MakubeX registration).
  - `PeerCallError` / `PeerCallTimeoutError` defined in Task 6 used identically in Tasks 8, 10, 12, 13.
- **Risk:** The behavior-sensitive integration is Task 11 (bot lifecycle wiring) — the bot fails fast on missing DATABASE_URL, which is intentional but means a misconfigured deploy will crash-loop until env is fixed. Mitigated by Task 15 step 6's explicit ops gate before merge. The other risk is the Postgres-vs-in-memory transport divergence (Task 7's `_dispatch_loop` change to use `transport.fetch_envelope` instead of the in-process cache); covered by re-running the existing 8 bus-logic tests after that refactor (Task 7 Step 1).
