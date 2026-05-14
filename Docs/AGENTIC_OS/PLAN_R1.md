# R-1 Implementation Plan — BaseAgent Refactor + Design Doc

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `BaseExpert` → `BaseAgent` under a new `agent_runtime/` package, ship the full Agentic OS design doc, and update project docs — all with zero behavior change for end users.

**Architecture:** Introduce a new `kaia/agent_runtime/` package owning the agent base class going forward. `experts.base.BaseExpert` becomes a thin deprecation alias re-exporting `BaseAgent` so every existing import (`HevnExpert`, `MakubeXExpert`, `PlaceholderExpert`) keeps working unchanged. `BaseAgent` adds a stable `agent_id` alias for `channel_id`, an `AgentContext` dataclass for future multi-arg handlers, and a `peer_call(...)` stub that raises a clear `NotImplementedError("inter-agent calls land in R-3")` — so R-3..R-5 land on a stable interface.

**Tech Stack:** Python 3.11+, asyncio, loguru, pytest. No new runtime dependencies in R-1.

---

## Scope Check

This plan covers a single subsystem (the agent runtime base class) and ships a working bot at every step. R-2..R-5 (concierge split, Postgres bus + protocol, per-bot deploy, cross-expert digest) are deliberately out of scope — each is its own plan.

## File Structure

```
kaia/
├── agent_runtime/            # NEW — agent runtime layer
│   ├── __init__.py           # exports BaseAgent, AgentContext, PeerCallError
│   ├── base_agent.py         # BaseAgent class (supersedes BaseExpert)
│   └── context.py            # AgentContext dataclass + visibility enum
├── experts/
│   └── base.py               # MODIFIED — becomes deprecation alias for BaseAgent
├── experts/__init__.py       # MODIFIED — adds get_agent() alias, no behavior change
└── tests/
    └── test_base_agent.py    # NEW — contract tests for BaseAgent

Docs/AGENTIC_OS/
├── DESIGN.md                 # NEW — full Agentic OS design (architecture, protocol, memory, phases)
└── PLAN_R1.md                # this file

Docs/
├── ARCHITECTURE.md           # MODIFIED — adds "Agentic OS Migration" section
├── CHANGELOG.md              # MODIFIED — R-1 entry
└── DEVELOPMENT_STATUS.md     # MODIFIED — adds R-1..R-5 phases
```

**Responsibility split:**
- `agent_runtime/base_agent.py` owns the agent abstraction (history, save, onboarding, footer, peer-call stub).
- `agent_runtime/context.py` owns the `AgentContext` dataclass and `Visibility` enum (will carry conversation_id/visibility into R-3).
- `experts/base.py` becomes a 3-line compatibility shim — keeps existing imports working.
- Design doc lives under `Docs/AGENTIC_OS/` to keep all multi-phase docs together.

---

## Task 1: Write the Agentic OS design doc

**Files:**
- Create: `Docs/AGENTIC_OS/DESIGN.md`

- [ ] **Step 1: Write `Docs/AGENTIC_OS/DESIGN.md` with the full architecture**

Contents:

````markdown
# Agentic OS — Design

> Status: R-1 (BaseAgent refactor) — design locked, infra phases pending.
> Owner: EJay. Last updated: 2026-05-14.

## Goal

Evolve KAIA from a single Telegram bot with internal "expert channels" into a
**mesh of independent agent bots** that share one user, talk to each other
visibly, and are coordinated by a slim KAIA-concierge.

## Topology

| Bot account            | Identity                                | Process            |
|------------------------|-----------------------------------------|--------------------|
| `@KaiaConciergeBot`    | KAIA — orchestrator, briefings, digests | concierge service  |
| `@HevnFinanceBot`      | Hevn — financial advisor                | hevn service       |
| `@MakubexTechBot`      | MakubeX — tech lead                     | makubex service    |
| `@KazukiInvestBot`     | Kazuki — investment manager (CH-4)      | kazuki service     |
| `@AkabaneTradeBot`     | Akabane — trading strategist (CH-5)     | akabane service    |

Single monorepo, separate Railway services, one Telegram bot token per agent.

## Runtime layers

```
kaia/
├── agent_runtime/   # BaseAgent, AgentContext, PeerCallError (R-1)
├── bus/             # Postgres LISTEN/NOTIFY pub/sub (R-3)
├── protocol/        # A2A envelope: {from, to, conversation_id, visibility, intent, payload} (R-3)
├── concierge/       # KAIA's slim orchestrator (R-2)
├── experts/         # Hevn, MakubeX, ... subclass BaseAgent
├── skills/          # shared skill library
└── services/        # one entry script per bot (R-4): run_kaia.py, run_hevn.py, ...
```

## Inter-agent protocol (A2A)

Envelope (R-3):

```json
{
  "envelope_id": "uuid",
  "conversation_id": "uuid",
  "from": "hevn",
  "to": "makubex",
  "user_id": "uuid",
  "intent": "consult",
  "visibility": "user_visible",
  "payload": { "question": "...", "context": "..." }
}
```

- **visibility**: `user_visible` (default) — relayed back into the user's
  thread; `internal` — only logged.
- Default per the user decision: **all peer calls are user_visible.**

Bus carrier: **Postgres LISTEN/NOTIFY** on the existing Supabase database.
No new infra. Each agent subscribes to channel `agent:<agent_id>`.

## Memory model

| Scope                          | Owner         | Read access                                  |
|--------------------------------|---------------|----------------------------------------------|
| `channel_profile` (per-expert) | That expert   | Private by default; grant on `peer_call`     |
| `user_profile` (shared)        | All           | Read-all; only concierge writes summaries    |
| `agent_conversations` (R-3)    | bus           | Concierge + participating agents             |
| `agent_messages` (R-3)         | bus           | Same as conversation                         |

No schema change in R-1.

## Migration phases

| Phase | Deliverable                                                              | User-visible? |
|-------|--------------------------------------------------------------------------|---------------|
| R-1   | `BaseAgent` runtime + design doc (this plan)                             | No            |
| R-2   | Concierge code split: `kaia/concierge/` owns general flow + onboarding   | No            |
| R-3   | Postgres LISTEN/NOTIFY bus + A2A protocol + Hevn↔MakubeX peer_call demo  | Yes           |
| R-4   | Per-bot Telegram tokens, separate Railway services                       | Yes (major)   |
| R-5   | Cross-expert weekly digest via concierge; full mesh                      | Yes           |

CH-3 (MakubeX skills), CH-4 (Kazuki), CH-5 (Akabane) continue on top of
this — each becomes "add a new agent" not "add an expert to the monolith".

## Decisions locked

- Bus: **Postgres LISTEN/NOTIFY on Supabase** (no new broker).
- Deploy: **Railway services, one per bot.**
- Inter-agent visibility: **default user_visible.**
- KAIA role: **concierge / orchestrator**, no domain-expert duties.
- Migration order: R-1 → R-2 → R-3 → R-4 → R-5.

## Open questions (not blockers for R-1)

- Should the concierge own onboarding for *all* agents, or each agent owns
  its own first-visit flow? (Today: each expert owns it.)
- Rate limiting: per-user across all agents, or per-bot? (Cost concern at R-4.)
- Should `channel_profile` ever be readable peer-to-peer without `peer_call`?
````

- [ ] **Step 2: Commit the design doc and this plan**

```bash
git add Docs/AGENTIC_OS/DESIGN.md Docs/AGENTIC_OS/PLAN_R1.md
git commit -m "docs(agentic-os): add R-1..R-5 design doc and R-1 plan"
```

---

## Task 2: Create the `agent_runtime/` package skeleton

**Files:**
- Create: `kaia/agent_runtime/__init__.py`
- Create: `kaia/agent_runtime/context.py`

- [ ] **Step 1: Create `kaia/agent_runtime/context.py`**

```python
"""Agent runtime context — carries per-turn data between agents and the harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from database.models import Channel, User


class Visibility(str, Enum):
    """Whether a peer-to-peer agent call is shown to the user."""

    USER_VISIBLE = "user_visible"
    INTERNAL = "internal"


@dataclass(slots=True)
class AgentContext:
    """Per-turn context passed into an agent's handler.

    R-1: carries user + channel + message (parity with BaseExpert.handle args).
    R-3: gains conversation_id + visibility + peer-call routing.
    """

    user: User
    channel: Channel
    message: str
    conversation_id: UUID = field(default_factory=uuid4)
    visibility: Visibility = Visibility.USER_VISIBLE
    metadata: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 2: Create `kaia/agent_runtime/__init__.py` (will not import cleanly until Task 3 lands — do not commit yet)**

```python
"""Agent runtime — base class and shared types for all KAIA agents."""

from __future__ import annotations

from agent_runtime.base_agent import BaseAgent, PeerCallError
from agent_runtime.context import AgentContext, Visibility

__all__ = ["BaseAgent", "PeerCallError", "AgentContext", "Visibility"]
```

- [ ] **Step 3: Do NOT commit yet — Task 3 finishes this unit**

---

## Task 3: Create `BaseAgent` and `PeerCallError`

**Files:**
- Create: `kaia/agent_runtime/base_agent.py`

- [ ] **Step 1: Write `kaia/agent_runtime/base_agent.py`**

Port every method from `kaia/experts/base.py` verbatim, then add the new pieces (`agent_id` alias, `peer_call` stub, `handle_turn` shim).

```python
"""Base class for all KAIA agents — supersedes experts.base.BaseExpert."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from agent_runtime.context import AgentContext
from config.settings import get_settings
from core.ai_engine import AIEngine
from core.channel_manager import ChannelManager
from core.channel_memory import ChannelMemoryManager
from core.channel_extractor import channel_extract_and_save
from config.constants import ROLE_USER, ROLE_ASSISTANT
from database.models import Channel, User
from database.queries import (
    get_channel_conversations,
    save_channel_conversation,
    get_channel_profile,
)
from skills.base import SkillResult
from utils.time_utils import format_relative_time


class PeerCallError(NotImplementedError):
    """Raised when an agent attempts a peer call before the R-3 bus lands."""


class BaseAgent(ABC):
    """Base class for all KAIA agents.

    Backwards-compatible with the former `BaseExpert`: subclasses set
    `channel_id` and implement `handle(user, message, channel)`. The new
    `agent_id` property is a stable alias for `channel_id` going forward.
    """

    # Subclasses set this. `agent_id` reads it; both names are supported.
    channel_id: str = ""

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine
        self._channel_mgr = ChannelManager()
        self._channel_mem = ChannelMemoryManager()

    # ── Identity ────────────────────────────────────────────────────

    @property
    def agent_id(self) -> str:
        """Stable name for this agent. Aliases `channel_id` during the
        BaseExpert → BaseAgent migration."""
        return self.channel_id

    # ── Handlers ────────────────────────────────────────────────────

    @abstractmethod
    async def handle(
        self,
        user: User,
        message: str,
        channel: Channel,
    ) -> SkillResult:
        """Handle a user message. Existing subclasses already implement this."""
        ...

    async def handle_turn(self, ctx: AgentContext) -> SkillResult:
        """Context-object handler. Default impl delegates to `handle()` so
        existing subclasses keep working without changes. R-3 callers
        (the bus) will use this entry point so conversation_id and
        visibility are preserved."""
        return await self.handle(ctx.user, ctx.message, ctx.channel)

    # ── Peer-to-peer (stub until R-3) ──────────────────────────────

    async def peer_call(
        self,
        target_agent_id: str,
        intent: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a message to another agent. Lands in R-3."""
        raise PeerCallError(
            f"peer_call({target_agent_id!r}, {intent!r}, ...) is not wired yet. "
            "Inter-agent messaging arrives in phase R-3 (Postgres LISTEN/NOTIFY). "
            "See Docs/AGENTIC_OS/DESIGN.md."
        )

    # ── History / persistence (verbatim from BaseExpert) ───────────

    async def get_conversation_history(
        self,
        user_id: str,
        channel_id: str,
        limit: int = 20,
        user_timezone: str | None = None,
    ) -> list[dict[str, str]]:
        """Load recent channel-specific conversation history.

        Each message's content is prefixed with a relative-time tag
        (e.g. "[3 days ago] ...") so the agent can reason about *when*
        prior turns happened rather than treating them as undated.
        """
        tz = user_timezone or get_settings().default_timezone
        convos = await get_channel_conversations(user_id, channel_id, limit)
        out: list[dict[str, str]] = []
        for c in convos:
            rel = format_relative_time(c.created_at, tz) if c.created_at else ""
            content = f"[{rel}] {c.content}" if rel else c.content
            out.append({"role": c.role, "content": content})
        return out

    async def save_messages(
        self,
        user_id: str,
        channel_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Save both user and assistant messages to channel history."""
        await save_channel_conversation(user_id, channel_id, ROLE_USER, user_msg)
        await save_channel_conversation(user_id, channel_id, ROLE_ASSISTANT, assistant_msg)

    def run_background_extraction(
        self,
        user_id: str,
        channel_id: str,
        messages: list[dict[str, str]],
    ) -> None:
        """Fire-and-forget channel memory extraction after conversation."""

        async def _extract() -> None:
            try:
                saved = await channel_extract_and_save(
                    ai_engine=self.ai,
                    user_id=user_id,
                    channel_id=channel_id,
                    conversation_messages=messages,
                )
                if saved:
                    logger.info(
                        "Channel extraction ({}): {} facts saved for user {}",
                        channel_id, saved, user_id,
                    )
            except Exception as exc:
                logger.warning("Channel extraction error ({}): {}", channel_id, exc)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_extract())
        except RuntimeError:
            logger.warning("No running event loop for channel extraction")

    async def generate_onboarding(
        self,
        user: User,
        channel: Channel,
        combined_context: str,
    ) -> str:
        """Generate the first-time onboarding message for this agent."""
        channel_entries = await get_channel_profile(user.id, channel.channel_id)
        gaps = self._channel_mem.get_knowledge_gaps(channel.channel_id, channel_entries)
        top_questions = [g["question"] for g in gaps[:3]]

        questions_text = ""
        if top_questions:
            questions_text = (
                "\n\nTo get started, ask these critical questions naturally in your greeting:\n"
                + "\n".join(f"- {q}" for q in top_questions)
            )

        system_prompt = (
            f"{channel.system_prompt}\n\n"
            f"USER CONTEXT:\n{combined_context}\n\n"
            f"INSTRUCTION: This is the user's FIRST TIME meeting you. "
            f"Introduce yourself in character — who you are, what you can do for them, "
            f"and your personality. Keep it warm and concise (2-3 short paragraphs). "
            f"Weave in the critical questions naturally, don't list them.{questions_text}"
        )

        response = await self.ai.chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": "Hello!"}],
        )
        return response.text

    def format_response_footer(self, channel: Channel) -> str:
        """Return the channel indicator footer."""
        return (
            f"\n\n---\n"
            f"_{channel.emoji} {channel.character_name} — {channel.role}_ | "
            f"/exit to return to KAIA"
        )
```

- [ ] **Step 2: Sanity-check the import works**

Run:
```bash
cd /home/ejay/Kaia/kaia && python -c "from agent_runtime import BaseAgent, AgentContext, PeerCallError, Visibility; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: Commit Tasks 2 + 3 together**

```bash
git add kaia/agent_runtime/
git commit -m "feat(agent-runtime): add BaseAgent, AgentContext, PeerCallError"
```

---

## Task 4: Convert `experts/base.py` into a deprecation alias

**Files:**
- Modify: `kaia/experts/base.py` (full replacement — file shrinks from 151 lines to ~15)

- [ ] **Step 1: Replace `kaia/experts/base.py` contents**

```python
"""Deprecated — use `agent_runtime.BaseAgent` directly going forward.

Kept as a compatibility shim during the BaseExpert → BaseAgent migration
(R-1). The full class implementation lives in `agent_runtime.base_agent`.
All existing imports `from experts.base import BaseExpert` continue to
resolve to the same class.

Schedule for removal: after R-5 ships (full agent mesh deployed).
"""

from __future__ import annotations

from agent_runtime.base_agent import BaseAgent as BaseExpert

__all__ = ["BaseExpert"]
```

- [ ] **Step 2: Verify Hevn, MakubeX, and PlaceholderExpert still import cleanly**

Run:
```bash
cd /home/ejay/Kaia/kaia && python -c "from experts.hevn import HevnExpert; from experts.makubex import MakubeXExpert; from experts.placeholder import PlaceholderExpert; print('ok', HevnExpert.__mro__[1].__name__)"
```
Expected: `ok BaseAgent` (proves `BaseExpert` resolves to the new `BaseAgent`).

- [ ] **Step 3: Verify `agent_id` works on a Hevn instance**

Run:
```bash
cd /home/ejay/Kaia/kaia && python -c "from unittest.mock import MagicMock; from experts.hevn import HevnExpert; h = HevnExpert(MagicMock()); print(h.channel_id, h.agent_id)"
```
Expected: `hevn hevn`

- [ ] **Step 4: Commit**

```bash
git add kaia/experts/base.py
git commit -m "refactor(experts): convert BaseExpert to deprecation alias for BaseAgent"
```

---

## Task 5: Add `get_agent()` alias to the registry

**Files:**
- Modify: `kaia/experts/__init__.py` (add alias after existing `get_expert`)

- [ ] **Step 1: Add the alias**

Insert immediately after the `get_expert` function:

```python
def get_agent(agent_id: str, ai_engine: AIEngine) -> BaseExpert | None:
    """Get an agent instance by agent_id. Alias for `get_expert` during the
    BaseExpert → BaseAgent migration (R-1). New call sites should prefer
    this name; existing `get_expert` callers continue to work."""
    return get_expert(agent_id, ai_engine)
```

- [ ] **Step 2: Verify**

Run:
```bash
cd /home/ejay/Kaia/kaia && python -c "from unittest.mock import MagicMock; from experts import get_expert, get_agent; ai = MagicMock(); print(type(get_expert('hevn', ai)).__name__, type(get_agent('hevn', ai)).__name__)"
```
Expected: `HevnExpert HevnExpert`

- [ ] **Step 3: Commit**

```bash
git add kaia/experts/__init__.py
git commit -m "feat(experts): add get_agent() alias on the registry"
```

---

## Task 6: Contract tests for `BaseAgent`

**Files:**
- Create: `kaia/tests/test_base_agent.py`

- [ ] **Step 1: Write the test file**

```python
"""Contract tests for agent_runtime.BaseAgent."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from agent_runtime import BaseAgent, AgentContext, PeerCallError, Visibility
from skills.base import SkillResult


class _StubAgent(BaseAgent):
    """Minimal concrete subclass for testing."""

    channel_id = "stub"

    async def handle(self, user, message, channel) -> SkillResult:  # noqa: D401
        return SkillResult(text=f"echo:{message}", skill_name=self.channel_id)


def _agent() -> _StubAgent:
    return _StubAgent(ai_engine=MagicMock())


def test_agent_id_aliases_channel_id():
    assert _agent().agent_id == "stub"


def test_baseexpert_alias_resolves_to_base_agent():
    """experts.base.BaseExpert must be the same class as BaseAgent."""
    from experts.base import BaseExpert  # alias

    assert BaseExpert is BaseAgent


@pytest.mark.asyncio
async def test_handle_turn_delegates_to_handle():
    agent = _agent()
    user = MagicMock()
    channel = MagicMock()
    ctx = AgentContext(user=user, channel=channel, message="hi")

    result = await agent.handle_turn(ctx)

    assert result.text == "echo:hi"
    assert result.skill_name == "stub"


@pytest.mark.asyncio
async def test_peer_call_raises_until_r3_lands():
    agent = _agent()
    with pytest.raises(PeerCallError) as exc:
        await agent.peer_call("makubex", "consult", {"q": "x"})

    msg = str(exc.value)
    assert "R-3" in msg
    assert "makubex" in msg


def test_visibility_default_is_user_visible():
    """Per design decision: peer calls default to user-visible."""
    user = MagicMock()
    channel = MagicMock()
    ctx = AgentContext(user=user, channel=channel, message="hi")
    assert ctx.visibility is Visibility.USER_VISIBLE
```

- [ ] **Step 2: Run the tests; verify all pass**

Run:
```bash
cd /home/ejay/Kaia/kaia && python -m pytest tests/test_base_agent.py -v
```
Expected: 5 passed.

If async tests fail with "coroutine never awaited" or similar, check `kaia/requirements.txt` and existing tests (`tests/test_intent_detector.py`, `tests/test_memory_extractor.py`) for the project's async test convention. If `pytest-asyncio` is not present, either add it to `requirements.txt` and `pytest.ini` (`asyncio_mode = auto`), or rewrite the async tests using `asyncio.run(...)` inside synchronous wrappers. Match what other test files in the repo already do.

- [ ] **Step 3: Run the full existing test suite to confirm no regressions**

Run:
```bash
cd /home/ejay/Kaia/kaia && python -m pytest -v
```
Expected: all tests pass, no new failures vs. baseline.

- [ ] **Step 4: Commit**

```bash
git add kaia/tests/test_base_agent.py
git commit -m "test(agent-runtime): contract tests for BaseAgent and PeerCallError"
```

---

## Task 7: Update `Docs/ARCHITECTURE.md`

**Files:**
- Modify: `Docs/ARCHITECTURE.md` (append new top-level section after the existing "Message Flow" section)

- [ ] **Step 1: Append the new section at the end of the file**

```markdown
---

## Agentic OS Migration (R-1 → R-5)

KAIA is evolving from a single-bot architecture with internal "expert channels" into a **mesh of independent agent bots** coordinated by a slim concierge. See [`AGENTIC_OS/DESIGN.md`](AGENTIC_OS/DESIGN.md) for the full design.

**Current state (R-1, 2026-05-14):**
- `kaia/agent_runtime/BaseAgent` is the new base class for all agents.
- `experts.base.BaseExpert` is a deprecation alias re-exporting `BaseAgent` — every existing subclass (`HevnExpert`, `MakubeXExpert`, `PlaceholderExpert`) is unchanged.
- `BaseAgent.peer_call(...)` is stubbed; raises `PeerCallError` pointing to R-3.
- No user-visible changes.

**Pending phases:**

| Phase | Deliverable                                                         |
|-------|---------------------------------------------------------------------|
| R-2   | Concierge code split: `kaia/concierge/` owns KAIA's orchestrator   |
| R-3   | Postgres LISTEN/NOTIFY bus + A2A protocol + visible peer calls     |
| R-4   | Per-bot Telegram tokens; separate Railway services                 |
| R-5   | Cross-expert weekly digest via concierge; full mesh                |

The current expert channel flow described above continues to operate unchanged through R-2. R-3 introduces the first user-visible change (inter-agent messages relayed into threads).
```

- [ ] **Step 2: Commit**

```bash
git add Docs/ARCHITECTURE.md
git commit -m "docs(architecture): document Agentic OS migration R-1..R-5"
```

---

## Task 8: Update `Docs/CHANGELOG.md` and `Docs/DEVELOPMENT_STATUS.md`

**Files:**
- Modify: `Docs/CHANGELOG.md` (prepend new entry directly under `# Changelog`)
- Modify: `Docs/DEVELOPMENT_STATUS.md` (add an Agentic OS subsection under `## Phase Progress`)

- [ ] **Step 1: Prepend changelog entry**

Insert directly below `# Changelog`:

```markdown
## [2026-05-14] R-1 — Agentic OS BaseAgent Refactor

### Added
- **New `kaia/agent_runtime/` package.** Introduces `BaseAgent` (supersedes
  `BaseExpert`), `AgentContext` dataclass, `Visibility` enum, and
  `PeerCallError`. Lays the foundation for the multi-bot Agentic OS mesh
  described in `Docs/AGENTIC_OS/DESIGN.md`.
- **`BaseAgent.peer_call(...)` stub.** Raises `PeerCallError` with a
  message pointing to R-3 (Postgres LISTEN/NOTIFY bus). Establishes the
  interface now so R-3..R-5 can land on a stable signature.
- **`BaseAgent.handle_turn(ctx: AgentContext)`.** Context-object handler;
  default impl delegates to the existing `handle(user, message, channel)`.
  R-3 callers (the bus) will route through this entry point.
- **`agent_id` property.** Stable alias for `channel_id` on every agent.
- **`get_agent()` registry alias.** Mirrors `get_expert()`; new call sites
  should prefer this name.
- **Design doc.** `Docs/AGENTIC_OS/DESIGN.md` — topology, A2A protocol,
  memory model, R-1..R-5 migration phases, locked decisions.
- **Tests.** `tests/test_base_agent.py` — contract tests for the alias,
  `handle_turn`, peer-call stub, and default visibility.

### Changed
- **`kaia/experts/base.py` is now a 3-line compatibility shim** that
  re-exports `BaseAgent` as `BaseExpert`. Existing imports continue to
  work unchanged; scheduled for removal after R-5.

### Migration notes
- No behavior change: Hevn, MakubeX, and PlaceholderExpert run identically.
- New code SHOULD subclass `agent_runtime.BaseAgent` directly.
- New code SHOULD use `get_agent()` over `get_expert()`.
```

- [ ] **Step 2: Add an Agentic OS section to `Docs/DEVELOPMENT_STATUS.md`**

Read the file first to confirm the exact heading level used by `## Phase Progress`. Then insert this new sub-section directly under that heading, above the existing CH-N phase table:

```markdown
### Agentic OS Migration

| Phase | Status        | Scope                                                            |
|-------|---------------|------------------------------------------------------------------|
| R-1   | ✅ Complete   | `BaseAgent` runtime + design doc                                |
| R-2   | ⏳ Planned    | Concierge code split (`kaia/concierge/`)                        |
| R-3   | ⏳ Planned    | Postgres LISTEN/NOTIFY bus + A2A protocol + peer_call demo      |
| R-4   | ⏳ Planned    | Per-bot Telegram tokens; separate Railway services              |
| R-5   | ⏳ Planned    | Cross-expert weekly digest via concierge; full mesh             |

See [`AGENTIC_OS/DESIGN.md`](AGENTIC_OS/DESIGN.md) for the full design.

### CH-N Expert Phases
```

(The trailing `### CH-N Expert Phases` heading visually separates the new section from the existing Phase 1 / CH-1 / CH-2 table below. If the existing table already has a heading, keep it; do not duplicate.)

- [ ] **Step 3: Commit**

```bash
git add Docs/CHANGELOG.md Docs/DEVELOPMENT_STATUS.md
git commit -m "docs: log R-1 in CHANGELOG and add Agentic OS phases to status"
```

---

## Task 9: Final smoke check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run:
```bash
cd /home/ejay/Kaia/kaia && python -m pytest -v
```
Expected: all tests pass, including the 5 new `test_base_agent.py` tests.

- [ ] **Step 2: Verify the bot imports cleanly**

Run:
```bash
cd /home/ejay/Kaia/kaia && python -c "import bot.telegram_bot; print('bot imports ok')"
```
Expected: `bot imports ok` (no import errors, no warnings about missing `BaseExpert`).

- [ ] **Step 3: Verify R-1 git history is clean**

Run:
```bash
git log --oneline -8
```
Expected: 6–8 commits, each scoped to one task, all on `add-expert-channel-system`.

- [ ] **Step 4: Confirm zero behavior change in concrete experts**

Run:
```bash
git diff main..HEAD -- kaia/experts/hevn kaia/experts/makubex kaia/experts/placeholder.py
```
Expected: **empty diff.** R-1 must not touch any concrete expert implementation.

---

## Self-Review Results

- **Spec coverage:**
  - "BaseAgent refactor" → Tasks 2, 3, 4, 5.
  - "Design doc" → Task 1.
  - "No behavior change" → enforced by Task 9 step 4 (empty diff in concrete experts) and Task 4 step 2 (subclasses still resolve).
  - "Update docs per standing rule" → Tasks 1, 7, 8.
  - "Tests" → Task 6.
- **Placeholder scan:** Every step shows the full code or exact command. No `TBD`/`TODO`/"implement later"/"add appropriate" patterns remain.
- **Type consistency:** `AgentContext`, `Visibility`, `BaseAgent`, `PeerCallError`, `agent_id`, `get_agent` used identically across Tasks 2, 3, 5, and 6. `channel_id` kept as the subclass-facing field name; `agent_id` is only a read-only property alias — never written, never renamed.
- **Risk:** The one moving piece is `experts.base` no longer defining `BaseExpert` directly. Task 4 Step 2 verifies subclasses still resolve before commit. Task 9 Step 4 enforces zero diff in concrete experts.
