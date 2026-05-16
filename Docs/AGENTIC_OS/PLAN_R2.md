# R-2 Implementation Plan — Concierge Code Split

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract KAIA's general (non-expert) conversation flow and its `/start` onboarding text out of `bot/telegram_bot.py` into a new transport-agnostic `kaia/concierge/` package — with **zero user-visible behavior change**.

**Architecture:** Introduce `kaia/concierge/` owning the orchestration of a general KAIA turn (profile load → history build → skill routing → conversation persistence → expert suggestion → background extraction) behind one method, `Concierge.handle_general_turn(...)`, returning a transport-agnostic `ConciergeResult`. Telegram-specific concerns (reply rendering, Markdown, truncation, forum topic threading, voice TTS, `track_ai_usage` telemetry) stay in `bot/telegram_bot.py`. The duplicated general-flow block currently copy-pasted across `handle_message` (text) and `handle_voice` collapses to a single concierge call. KAIA's `/start` welcome string moves to `concierge/onboarding.py` as the single source of truth. This is the same migration shape as R-1: new package, behavior-preserving, thin transport shim, stable interface for R-3..R-5.

**Tech Stack:** Python 3.11+, asyncio, python-telegram-bot, loguru, pytest + pytest-asyncio (1.3.0, explicit `@pytest.mark.asyncio` markers — no `pytest.ini`). No new runtime dependencies.

---

## Scope Check

This plan covers a single subsystem (the concierge orchestration layer) and ships a working bot at every commit. Explicitly **out of scope** (each is its own later plan):

- **Expert first-visit onboarding stays with experts.** `BaseAgent.generate_onboarding(...)` and its call site in `cmd_channel_switch` are *not* touched. The DESIGN open question "should the concierge own onboarding for *all* agents?" is deliberately **not resolved here** — today each expert owns it, and R-2 keeps it that way. The only "onboarding" the concierge owns in R-2 is KAIA's own `/start` greeting.
- **No Postgres bus / A2A protocol** (R-3). `peer_call` remains the R-1 stub.
- **No per-bot tokens / Railway split** (R-4).
- **No transport extraction.** `bot/telegram_bot.py` keeps owning all Telegram I/O; the concierge never imports `telegram`.

**Dominant constraint:** R-2 is marked *not user-visible* in `DESIGN.md`. Behavior preservation outranks elegance everywhere they conflict. The current text-vs-voice divergence is preserved exactly (see Behavior-Preservation Invariants below).

### Behavior-Preservation Invariants

These must hold identically before and after R-2. Tasks 3 and 4 verify each:

1. **Conversation persistence:** user message then assistant message, both saved with `skill_used=result.skill_name`.
2. **Expert suggestion is text-path only.** `detect_expert_topic(...)` is **stateful** (module-level `_recent_suggestions` in `core/expert_detector.py`, mutated on every call). The voice handler never called it today; it must still never call it. The text handler calls it only when `result.skill_name == SKILL_CHAT`.
3. **History tagging:** each prior turn prefixed with `[<relative time>] ` using `format_relative_time(c.created_at, tz)` where `tz = user.timezone or settings.default_timezone`; `limit=settings.max_conversation_history`.
4. **Voice TTS decision** still keyed off the same `profile_context` string the turn was routed with (single profile load — no double load).
5. **`track_ai_usage(...)` and the `logger.info("msg handled ...")` line stay in the bot** (transport telemetry), reading `result.ai_response`.
6. **Forum/topic reply kwargs** (`message_thread_id`) remain built and applied in the bot, unchanged.
7. **Expert turn path** (`_handle_expert_turn`, `cmd_channel_switch`, `cmd_exit`, `cmd_team`) is untouched.
8. **`clear_suggestion_history` on channel switch** is untouched.
9. **Background extraction** remains fire-and-forget (`memory_mgr.run_background_extraction` creates a non-blocking asyncio task). It moves a few statements earlier (now inside the concierge call, before the reply is sent) on both paths. This is non-blocking and creates no user-visible ordering change — documented and accepted, not a regression.

---

## File Structure

```
kaia/
├── concierge/                  # NEW — KAIA's slim orchestrator (R-2)
│   ├── __init__.py             # exports Concierge, ConciergeResult, welcome_text
│   ├── result.py               # ConciergeResult dataclass (transport-agnostic turn output)
│   ├── onboarding.py           # welcome_text() — single source of truth for /start greeting
│   └── concierge.py            # Concierge class — handle_general_turn()
├── bot/
│   └── telegram_bot.py         # MODIFIED — cmd_start, handle_message, handle_voice delegate to concierge
└── tests/
    ├── test_concierge_onboarding.py   # NEW — welcome_text() contract
    └── test_concierge.py              # NEW — handle_general_turn() orchestration + invariants

Docs/AGENTIC_OS/
├── DESIGN.md                   # MODIFIED — status header line bumped to R-2 in progress
└── PLAN_R2.md                  # this file

Docs/
├── ARCHITECTURE.md             # MODIFIED — Agentic OS section: R-2 current state
├── CHANGELOG.md                # MODIFIED — R-2 entry
└── DEVELOPMENT_STATUS.md       # MODIFIED — R-2 marked complete in Agentic OS table
```

**Responsibility split:**
- `concierge/result.py` — `ConciergeResult`: the transport-agnostic output of one general turn (`text`, `skill_name`, `ai_response`, `suggestion`, `profile_context`).
- `concierge/onboarding.py` — `welcome_text()`: pure function returning KAIA's `/start` greeting string. No deps; trivially testable.
- `concierge/concierge.py` — `Concierge`: composes the existing `SkillRouter` + `MemoryManager` (dependency-injected, reusing the bot's existing global instances — no double-instantiation, fully mockable). Owns one general turn's orchestration end to end.
- `bot/telegram_bot.py` — keeps 100% of Telegram I/O. Becomes a thin shim that calls the concierge and renders the result.

> **Plan location note:** the writing-plans skill default is `docs/superpowers/plans/`. This project's established convention (set by `Docs/AGENTIC_OS/PLAN_R1.md`) overrides it — all Agentic OS phase plans live under `Docs/AGENTIC_OS/`.

---

## Task 1: Bump DESIGN.md status and commit this plan

**Files:**
- Modify: `Docs/AGENTIC_OS/DESIGN.md:3-4`
- Create: `Docs/AGENTIC_OS/PLAN_R2.md` (this file — already written)

- [ ] **Step 1: Update the status header in `Docs/AGENTIC_OS/DESIGN.md`**

Replace these two lines (lines 3–4):

```markdown
> Status: R-1 (BaseAgent refactor) — design locked, infra phases pending.
> Owner: EJay. Last updated: 2026-05-14.
```

with:

```markdown
> Status: R-2 (concierge code split) — in progress. R-1 shipped.
> Owner: EJay. Last updated: 2026-05-16.
```

Do not change any other line in `DESIGN.md` — the design is locked.

- [ ] **Step 2: Commit the design status bump and this plan**

```bash
git add Docs/AGENTIC_OS/DESIGN.md Docs/AGENTIC_OS/PLAN_R2.md
git commit -m "docs(agentic-os): R-2 concierge split plan; mark R-2 in progress"
```

---

## Task 2: Create the `concierge/` package — `ConciergeResult` + `welcome_text` (TDD)

These two pieces have no dependency on `Concierge` itself, are pure, and are written test-first. The package imports cleanly after this task (it exports only `ConciergeResult` and `welcome_text`; `Concierge` is added in Task 3).

**Files:**
- Create: `kaia/concierge/result.py`
- Create: `kaia/concierge/onboarding.py`
- Create: `kaia/concierge/__init__.py`
- Create: `kaia/tests/test_concierge_onboarding.py`

- [ ] **Step 1: Write the failing test for `welcome_text()`**

Create `kaia/tests/test_concierge_onboarding.py`:

```python
"""Contract tests for concierge.onboarding.welcome_text."""

from __future__ import annotations

from concierge import welcome_text


def test_welcome_text_is_nonempty_str():
    text = welcome_text()
    assert isinstance(text, str)
    assert len(text) > 0


def test_welcome_text_mentions_kaia_and_team_commands():
    text = welcome_text()
    # Single source of truth for the /start greeting — these anchors must
    # stay so the message keeps onboarding the user to the expert team.
    assert "KAIA" in text
    assert "/hevn" in text
    assert "/makubex" in text
    assert "/team" in text


def test_welcome_text_is_stable_across_calls():
    assert welcome_text() == welcome_text()
```

- [ ] **Step 2: Run the test; verify it fails**

Run:
```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_concierge_onboarding.py -q
```
Expected: collection/import error — `ModuleNotFoundError: No module named 'concierge'`.

- [ ] **Step 3: Create `kaia/concierge/result.py`**

```python
"""Transport-agnostic output of one general KAIA turn."""

from __future__ import annotations

from dataclasses import dataclass

from core.ai_engine import AIResponse


@dataclass(slots=True)
class ConciergeResult:
    """What a general (non-expert) KAIA turn produced.

    The concierge owns orchestration (routing, persistence, suggestion,
    extraction); the transport (Telegram bot) owns rendering. This object
    carries everything the transport needs and nothing Telegram-specific.

    Attributes:
        text: The assistant reply to send to the user.
        skill_name: Which skill produced ``text`` (e.g. ``"chat"``).
        ai_response: Token/provider usage for telemetry, or ``None``.
        suggestion: Expert-suggestion line to send as a follow-up message,
            or ``None``. Only ever populated on the text path (see R-2
            behavior-preservation invariant #2).
        profile_context: The formatted profile string the turn was routed
            with. Returned so the voice transport can make its TTS decision
            off the same string without a second profile load.
    """

    text: str
    skill_name: str
    ai_response: AIResponse | None = None
    suggestion: str | None = None
    profile_context: str = ""
```

- [ ] **Step 4: Create `kaia/concierge/onboarding.py`**

The string is moved verbatim from `bot/telegram_bot.py` `cmd_start` (current lines 114–133). Do not reword it — R-2 is not user-visible.

```python
"""KAIA's first-contact onboarding — the /start greeting.

Single source of truth for the welcome message. The Telegram transport
calls ``welcome_text()`` and renders it; no other copy of this string
should exist in the codebase.
"""

from __future__ import annotations

_WELCOME = (
    "👋 Hi! I'm *KAIA* — your personal AI assistant.\n\n"
    "I can help you with:\n"
    "🗣️ Chat & advice — just talk to me naturally\n"
    "🧠 Memory — I learn about you over time\n"
    "⏰ Reminders — \"Remind me to take meds at 8pm daily\"\n"
    "💰 Budget — \"Spent ₱500 on groceries\"\n"
    "🌅 Briefing — Daily morning summary\n"
    "🌐 Web search — \"What's the latest news about...\"\n"
    "🎙️ Voice — Send me voice messages!\n\n"
    "👥 *Meet my team of experts:*\n"
    "💰 /hevn — Financial advisor\n"
    "📈 /kazuki — Investment manager\n"
    "⚔️ /akabane — Trading strategist\n"
    "🔧 /makubex — Tech lead\n"
    "Type /team to see everyone.\n\n"
    "Just talk to me like a friend. No commands needed!\n"
    "Type /help for more details."
)


def welcome_text() -> str:
    """Return KAIA's /start greeting."""
    return _WELCOME
```

- [ ] **Step 5: Create `kaia/concierge/__init__.py`**

```python
"""Concierge — KAIA's slim orchestrator (Agentic OS R-2).

Owns the general (non-expert) conversation turn and KAIA's onboarding
greeting. Transport-agnostic: nothing here imports ``telegram``.
"""

from __future__ import annotations

from concierge.onboarding import welcome_text
from concierge.result import ConciergeResult

__all__ = ["ConciergeResult", "welcome_text"]
```

- [ ] **Step 6: Run the test; verify it passes**

Run:
```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_concierge_onboarding.py -q
```
Expected: `3 passed`.

- [ ] **Step 7: Commit**

```bash
git add kaia/concierge/__init__.py kaia/concierge/result.py kaia/concierge/onboarding.py kaia/tests/test_concierge_onboarding.py
git commit -m "feat(concierge): add concierge package skeleton (ConciergeResult, welcome_text)"
```

---

## Task 3: Implement `Concierge.handle_general_turn` (TDD)

**Files:**
- Create: `kaia/concierge/concierge.py`
- Modify: `kaia/concierge/__init__.py` (add `Concierge` export)
- Create: `kaia/tests/test_concierge.py`

- [ ] **Step 1: Write the failing test**

Create `kaia/tests/test_concierge.py`. These tests inject mocked collaborators so no Telegram, DB, or AI is touched. They assert the behavior-preservation invariants directly.

```python
"""Orchestration tests for concierge.Concierge.handle_general_turn."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from concierge import Concierge, ConciergeResult
from config.constants import ROLE_ASSISTANT, ROLE_USER, SKILL_CHAT
from skills.base import SkillResult


def _user():
    return SimpleNamespace(id="u-1", timezone="Asia/Manila")


def _convo(role: str, content: str):
    # Mimics a database conversation row (has .role, .content, .created_at).
    return SimpleNamespace(role=role, content=content, created_at=None)


def _make_concierge(skill_result: SkillResult):
    router = MagicMock()
    router.route = AsyncMock(return_value=skill_result)
    memory = MagicMock()
    memory.load_profile_context = AsyncMock(return_value="PROFILE")
    memory.run_background_extraction = MagicMock()
    c = Concierge(ai_engine=MagicMock(), skill_router=router, memory_mgr=memory)
    return c, router, memory


@pytest.mark.asyncio
async def test_general_turn_routes_and_returns_result():
    sr = SkillResult(text="hello back", skill_name=SKILL_CHAT)
    c, router, memory = _make_concierge(sr)

    with patch("concierge.concierge.get_recent_conversations",
               AsyncMock(return_value=[_convo(ROLE_USER, "earlier")])), \
         patch("concierge.concierge.save_conversation", AsyncMock()) as save, \
         patch("concierge.concierge.detect_expert_topic", return_value=None):
        result = await c.handle_general_turn(_user(), "hi", suggest_experts=True)

    assert isinstance(result, ConciergeResult)
    assert result.text == "hello back"
    assert result.skill_name == SKILL_CHAT
    assert result.profile_context == "PROFILE"
    router.route.assert_awaited_once()
    # Invariant #1: user then assistant, tagged with skill name.
    assert save.await_args_list[0].args[1] == ROLE_USER
    assert save.await_args_list[1].args[1] == ROLE_ASSISTANT
    assert save.await_args_list[0].kwargs["skill_used"] == SKILL_CHAT
    # Invariant #9: extraction fired (fire-and-forget).
    memory.run_background_extraction.assert_called_once()


@pytest.mark.asyncio
async def test_suggestion_only_when_chat_and_suggest_enabled():
    sr = SkillResult(text="r", skill_name=SKILL_CHAT)
    c, *_ = _make_concierge(sr)
    with patch("concierge.concierge.get_recent_conversations", AsyncMock(return_value=[])), \
         patch("concierge.concierge.save_conversation", AsyncMock()), \
         patch("concierge.concierge.detect_expert_topic",
               return_value={"channel_id": "hevn", "suggestion": "try /hevn"}) as det:
        result = await c.handle_general_turn(_user(), "budget help", suggest_experts=True)
    assert result.suggestion == "try /hevn"
    det.assert_called_once()


@pytest.mark.asyncio
async def test_voice_path_never_calls_detector():
    """Invariant #2: suggest_experts=False must not touch the stateful detector."""
    sr = SkillResult(text="r", skill_name=SKILL_CHAT)
    c, *_ = _make_concierge(sr)
    with patch("concierge.concierge.get_recent_conversations", AsyncMock(return_value=[])), \
         patch("concierge.concierge.save_conversation", AsyncMock()), \
         patch("concierge.concierge.detect_expert_topic") as det:
        result = await c.handle_general_turn(_user(), "budget help", suggest_experts=False)
    assert result.suggestion is None
    det.assert_not_called()


@pytest.mark.asyncio
async def test_no_suggestion_for_non_chat_skill():
    sr = SkillResult(text="reminder set", skill_name="reminders")
    c, *_ = _make_concierge(sr)
    with patch("concierge.concierge.get_recent_conversations", AsyncMock(return_value=[])), \
         patch("concierge.concierge.save_conversation", AsyncMock()), \
         patch("concierge.concierge.detect_expert_topic") as det:
        result = await c.handle_general_turn(_user(), "remind me", suggest_experts=True)
    assert result.suggestion is None
    det.assert_not_called()
```

- [ ] **Step 2: Run the test; verify it fails**

Run:
```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_concierge.py -q
```
Expected: `ImportError: cannot import name 'Concierge' from 'concierge'`.

- [ ] **Step 3: Create `kaia/concierge/concierge.py`**

This is the duplicated general-flow block from `handle_message`/`handle_voice`, lifted verbatim into one place. Module-level names are referenced by tests via `patch("concierge.concierge.<name>")`, so import them directly (not via `module.attr`).

```python
"""Concierge — orchestrates one general (non-expert) KAIA turn.

Lifted verbatim from the duplicated block in bot/telegram_bot.py
(handle_message / handle_voice). Transport-agnostic: returns a
ConciergeResult; the caller renders it. See Docs/AGENTIC_OS/DESIGN.md
and Docs/AGENTIC_OS/PLAN_R2.md (behavior-preservation invariants).
"""

from __future__ import annotations

from config.constants import ROLE_ASSISTANT, ROLE_USER, SKILL_CHAT
from config.settings import get_settings
from core.ai_engine import AIEngine
from core.expert_detector import detect_expert_topic
from core.memory_manager import MemoryManager
from core.skill_router import SkillRouter
from database.models import User
from database.queries import get_recent_conversations, save_conversation
from utils.time_utils import format_relative_time

from concierge.result import ConciergeResult

settings = get_settings()


class Concierge:
    """KAIA's slim orchestrator for general (non-expert) conversation.

    Composes the existing SkillRouter + MemoryManager. The bot injects its
    already-constructed singletons so behavior and instances are identical
    to pre-R-2 (no double instantiation of skills/AI).
    """

    def __init__(
        self,
        ai_engine: AIEngine,
        *,
        skill_router: SkillRouter,
        memory_mgr: MemoryManager,
    ) -> None:
        self._ai = ai_engine
        self._router = skill_router
        self._memory = memory_mgr

    async def handle_general_turn(
        self,
        user: User,
        message: str,
        *,
        suggest_experts: bool,
    ) -> ConciergeResult:
        """Run one general KAIA turn.

        Args:
            user: The current user record.
            message: The incoming text (already transcribed for voice).
            suggest_experts: Whether to run the stateful expert-topic
                detector. ``True`` for the text path, ``False`` for voice
                — preserves the exact pre-R-2 divergence (invariant #2).

        Returns:
            ConciergeResult — transport renders it.
        """
        profile_context = await self._memory.load_profile_context(user.id)

        recent_convos = await get_recent_conversations(
            user.id, limit=settings.max_conversation_history
        )
        tz = user.timezone or settings.default_timezone
        history: list[dict[str, str]] = []
        for c in recent_convos:
            rel = format_relative_time(c.created_at, tz) if c.created_at else ""
            content = f"[{rel}] {c.content}" if rel else c.content
            history.append({"role": c.role, "content": content})

        result = await self._router.route(
            user=user,
            message=message,
            conversation_history=history,
            profile_context=profile_context,
        )

        await save_conversation(
            user.id, ROLE_USER, message, skill_used=result.skill_name
        )
        await save_conversation(
            user.id, ROLE_ASSISTANT, result.text, skill_used=result.skill_name
        )

        suggestion: str | None = None
        if suggest_experts and result.skill_name == SKILL_CHAT:
            hit = detect_expert_topic(message, result.text, user_id=user.id)
            if hit:
                suggestion = hit["suggestion"]

        updated_history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": result.text},
        ]
        self._memory.run_background_extraction(user.id, updated_history)

        return ConciergeResult(
            text=result.text,
            skill_name=result.skill_name,
            ai_response=result.ai_response,
            suggestion=suggestion,
            profile_context=profile_context,
        )
```

- [ ] **Step 4: Add `Concierge` to `kaia/concierge/__init__.py`**

Replace the file with:

```python
"""Concierge — KAIA's slim orchestrator (Agentic OS R-2).

Owns the general (non-expert) conversation turn and KAIA's onboarding
greeting. Transport-agnostic: nothing here imports ``telegram``.
"""

from __future__ import annotations

from concierge.concierge import Concierge
from concierge.onboarding import welcome_text
from concierge.result import ConciergeResult

__all__ = ["Concierge", "ConciergeResult", "welcome_text"]
```

- [ ] **Step 5: Run the new tests; verify they pass**

Run:
```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_concierge.py tests/test_concierge_onboarding.py -q
```
Expected: `7 passed` (4 concierge + 3 onboarding). _(As shipped: a 5th
concierge regression test for the time-tagged-history branch — invariant
#3 — was added during code review, so the final count is `8 passed`.)_

- [ ] **Step 6: Sanity-check the package imports cleanly**

Run:
```bash
cd /home/ejay/Kaia/kaia && python3 -c "from concierge import Concierge, ConciergeResult, welcome_text; print('ok')"
```
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add kaia/concierge/concierge.py kaia/concierge/__init__.py kaia/tests/test_concierge.py
git commit -m "feat(concierge): Concierge.handle_general_turn orchestrator"
```

---

## Task 4: Wire the Telegram bot to the concierge

Now collapse the two duplicated general-flow blocks and the inline welcome string into concierge calls. This is the only behavior-sensitive task — follow the replacements exactly.

**Files:**
- Modify: `kaia/bot/telegram_bot.py` (imports; globals; `cmd_start`; `handle_message` general block; `handle_voice` general block)

- [ ] **Step 1: Add the concierge import and global instance**

In `kaia/bot/telegram_bot.py`, find the import line (currently line 58):

```python
from experts.placeholder import PlaceholderExpert
```

Add immediately after it:

```python
from concierge import Concierge, welcome_text
```

Then find the globals block (currently lines 67–74):

```python
# ── Globals (initialised in main) ────────────────────────────────────
settings = get_settings()
ai_engine = AIEngine()
memory_mgr = MemoryManager(ai_engine)
skill_router = SkillRouter(ai_engine)
channel_mgr = ChannelManager()
channel_mem = ChannelMemoryManager()
forum_mgr = ForumManager()
```

Add the concierge as the last global (after `forum_mgr`), reusing the existing singletons:

```python
concierge = Concierge(ai_engine, skill_router=skill_router, memory_mgr=memory_mgr)
```

- [ ] **Step 2: Replace the `cmd_start` welcome body**

In `cmd_start`, replace this call (currently lines 114–133):

```python
    await update.message.reply_text(
        "👋 Hi! I'm *KAIA* — your personal AI assistant.\n\n"
        "I can help you with:\n"
        "🗣️ Chat & advice — just talk to me naturally\n"
        "🧠 Memory — I learn about you over time\n"
        "⏰ Reminders — \"Remind me to take meds at 8pm daily\"\n"
        "💰 Budget — \"Spent ₱500 on groceries\"\n"
        "🌅 Briefing — Daily morning summary\n"
        "🌐 Web search — \"What's the latest news about...\"\n"
        "🎙️ Voice — Send me voice messages!\n\n"
        "👥 *Meet my team of experts:*\n"
        "💰 /hevn — Financial advisor\n"
        "📈 /kazuki — Investment manager\n"
        "⚔️ /akabane — Trading strategist\n"
        "🔧 /makubex — Tech lead\n"
        "Type /team to see everyone.\n\n"
        "Just talk to me like a friend. No commands needed!\n"
        "Type /help for more details.",
        parse_mode="Markdown",
    )
```

with:

```python
    await update.message.reply_text(welcome_text(), parse_mode="Markdown")
```

- [ ] **Step 3: Replace the general-flow block in `handle_message`**

In `handle_message`, replace this block (currently lines 566–625, from the `# ── General KAIA flow` comment through the end of the `if result.ai_response:` logging):

```python
        # ── General KAIA flow (DM general OR forum General topic) ────

        profile_context = await memory_mgr.load_profile_context(user.id)
        recent_convos = await get_recent_conversations(
            user.id, limit=settings.max_conversation_history
        )
        tz = user.timezone or settings.default_timezone
        history: list[dict[str, str]] = []
        for c in recent_convos:
            rel = format_relative_time(c.created_at, tz) if c.created_at else ""
            content = f"[{rel}] {c.content}" if rel else c.content
            history.append({"role": c.role, "content": content})

        result = await skill_router.route(
            user=user,
            message=text,
            conversation_history=history,
            profile_context=profile_context,
        )

        await save_conversation(user.id, ROLE_USER, text, skill_used=result.skill_name)
        await save_conversation(
            user.id, ROLE_ASSISTANT, result.text, skill_used=result.skill_name
        )

        reply_kwargs: dict = {"parse_mode": "Markdown"}
        if is_forum and topic_id is not None:
            reply_kwargs["message_thread_id"] = topic_id

        await update.message.reply_text(truncate(result.text), **reply_kwargs)

        # Suggest expert if the message was handled by chat skill
        if result.skill_name == SKILL_CHAT:
            suggestion = detect_expert_topic(text, result.text, user_id=user.id)
            if suggestion:
                await update.message.reply_text(
                    f"💡 _{suggestion['suggestion']}_",
                    **reply_kwargs,
                )

        updated_history = history + [
            {"role": "user", "content": text},
            {"role": "assistant", "content": result.text},
        ]
        memory_mgr.run_background_extraction(user.id, updated_history)

        if result.ai_response:
            track_ai_usage(
                result.ai_response.input_tokens,
                result.ai_response.output_tokens,
                result.ai_response.provider,
            )
            logger.info(
                "msg handled | user={} skill={} provider={} tokens={}+{}",
                tg_user.id,
                result.skill_name,
                result.ai_response.provider,
                result.ai_response.input_tokens,
                result.ai_response.output_tokens,
            )
```

with:

```python
        # ── General KAIA flow (DM general OR forum General topic) ────
        # Orchestration lives in the concierge (R-2). The bot only renders.

        result = await concierge.handle_general_turn(
            user, text, suggest_experts=True
        )

        reply_kwargs: dict = {"parse_mode": "Markdown"}
        if is_forum and topic_id is not None:
            reply_kwargs["message_thread_id"] = topic_id

        await update.message.reply_text(truncate(result.text), **reply_kwargs)

        # Suggest expert (text path only — preserves pre-R-2 behavior).
        if result.suggestion:
            await update.message.reply_text(
                f"💡 _{result.suggestion}_",
                **reply_kwargs,
            )

        if result.ai_response:
            track_ai_usage(
                result.ai_response.input_tokens,
                result.ai_response.output_tokens,
                result.ai_response.provider,
            )
            logger.info(
                "msg handled | user={} skill={} provider={} tokens={}+{}",
                tg_user.id,
                result.skill_name,
                result.ai_response.provider,
                result.ai_response.input_tokens,
                result.ai_response.output_tokens,
            )
```

- [ ] **Step 4: Replace the general-flow block in `handle_voice`**

In `handle_voice`, replace this block (currently lines 709–757, from the `# General KAIA flow` comment through the end of the `if result.ai_response:` block):

```python
        # General KAIA flow
        profile_context = await memory_mgr.load_profile_context(user.id)
        recent_convos = await get_recent_conversations(
            user.id, limit=settings.max_conversation_history
        )
        tz = user.timezone or settings.default_timezone
        history: list[dict[str, str]] = []
        for c in recent_convos:
            rel = format_relative_time(c.created_at, tz) if c.created_at else ""
            content = f"[{rel}] {c.content}" if rel else c.content
            history.append({"role": c.role, "content": content})

        result = await skill_router.route(
            user=user,
            message=transcribed,
            conversation_history=history,
            profile_context=profile_context,
        )

        # Save conversation
        await save_conversation(user.id, ROLE_USER, transcribed, skill_used=result.skill_name)
        await save_conversation(user.id, ROLE_ASSISTANT, result.text, skill_used=result.skill_name)

        # Send text response (in the same topic if applicable)
        await update.message.reply_text(truncate(result.text), **reply_kwargs)

        # Optionally reply with voice
        if _should_reply_with_voice(profile_context):
            tts_path = await text_to_speech(result.text, voice=settings.tts_voice)
            if tts_path:
                voice_kwargs: dict = {}
                if is_forum and topic_id is not None:
                    voice_kwargs["message_thread_id"] = topic_id
                with open(tts_path, "rb") as audio:
                    await update.message.reply_voice(voice=audio, **voice_kwargs)

        # Background extraction
        updated_history = history + [
            {"role": "user", "content": transcribed},
            {"role": "assistant", "content": result.text},
        ]
        memory_mgr.run_background_extraction(user.id, updated_history)

        if result.ai_response:
            track_ai_usage(
                result.ai_response.input_tokens,
                result.ai_response.output_tokens,
                result.ai_response.provider,
            )
```

with:

```python
        # General KAIA flow — orchestration via concierge (R-2).
        # suggest_experts=False: the voice path never ran the stateful
        # expert detector pre-R-2; that divergence is preserved.
        result = await concierge.handle_general_turn(
            user, transcribed, suggest_experts=False
        )

        # Send text response (in the same topic if applicable)
        await update.message.reply_text(truncate(result.text), **reply_kwargs)

        # Optionally reply with voice — keyed off the same profile_context
        # the turn was routed with (single profile load).
        if _should_reply_with_voice(result.profile_context):
            tts_path = await text_to_speech(result.text, voice=settings.tts_voice)
            if tts_path:
                voice_kwargs: dict = {}
                if is_forum and topic_id is not None:
                    voice_kwargs["message_thread_id"] = topic_id
                with open(tts_path, "rb") as audio:
                    await update.message.reply_voice(voice=audio, **voice_kwargs)

        if result.ai_response:
            track_ai_usage(
                result.ai_response.input_tokens,
                result.ai_response.output_tokens,
                result.ai_response.provider,
            )
```

- [ ] **Step 5: Verify the bot imports cleanly**

Run:
```bash
cd /home/ejay/Kaia/kaia && python3 -c "import bot.telegram_bot; print('bot imports ok')"
```
Expected: `bot imports ok`

- [ ] **Step 6: Behavior-preservation review checklist**

Read the modified `handle_message`, `handle_voice`, and `cmd_start`. Confirm every box:

- [ ] `cmd_start` sends `welcome_text()` with `parse_mode="Markdown"` — no other change.
- [ ] Text path calls `concierge.handle_general_turn(user, text, suggest_experts=True)`.
- [ ] Voice path calls `concierge.handle_general_turn(user, transcribed, suggest_experts=False)`.
- [ ] Text path still sends `💡 _{result.suggestion}_` with the same `reply_kwargs`, only when `result.suggestion` is truthy.
- [ ] Voice path sends **no** suggestion message and never references `detect_expert_topic` (not used in the new voice block).
- [ ] Voice TTS gate uses `result.profile_context` (the same string the turn routed with).
- [ ] `track_ai_usage(...)` and the `logger.info("msg handled ...")` line remain in the bot on both paths.
- [ ] Forum/topic `reply_kwargs` / `voice_kwargs` (`message_thread_id`) construction is unchanged.
- [ ] `_handle_expert_turn`, `cmd_channel_switch`, `cmd_exit`, `cmd_team`, `cmd_setup_forum` are byte-for-byte unchanged.

- [ ] **Step 7: Remove only now-unused imports, then commit**

`cmd_channel_switch`, `cmd_briefing`, and `cmd_team` still use `memory_mgr`, `get_channel_profile`, `channel_mem`, etc. Do **not** remove any import without grepping first:

```bash
cd /home/ejay/Kaia/kaia && for sym in get_recent_conversations save_conversation format_relative_time detect_expert_topic skill_router memory_mgr; do echo -n "$sym: "; grep -c "\b$sym\b" bot/telegram_bot.py; done
```

For each symbol whose count is `1` (only its import line remains), delete that import line. For any count `> 1`, leave the import. Then verify and commit:

```bash
cd /home/ejay/Kaia/kaia && python3 -c "import bot.telegram_bot; print('imports clean')"
git add kaia/bot/telegram_bot.py
git commit -m "refactor(bot): delegate general flow + onboarding to concierge"
```

---

## Task 5: Update docs (standing rule: every code change updates docs/)

**Files:**
- Modify: `Docs/ARCHITECTURE.md` (Agentic OS Migration section — update current state)
- Modify: `Docs/CHANGELOG.md` (prepend R-2 entry)
- Modify: `Docs/DEVELOPMENT_STATUS.md` (Agentic OS table — mark R-2 complete)

- [ ] **Step 1: Update the "Agentic OS Migration" section in `Docs/ARCHITECTURE.md`**

Find the R-1 current-state block added in R-1 (it begins with `**Current state (R-1, 2026-05-14):**`). Replace that `**Current state ...**` paragraph and its bullet list with:

```markdown
**Current state (R-2, 2026-05-16):**
- `kaia/agent_runtime/BaseAgent` is the base class for all agents (R-1).
- `kaia/concierge/` owns KAIA's general (non-expert) conversation turn
  (`Concierge.handle_general_turn`) and the `/start` greeting
  (`welcome_text`). `bot/telegram_bot.py` is now a thin Telegram transport
  over the concierge; the previously duplicated text/voice general-flow
  block is unified.
- Expert first-visit onboarding still lives with each expert
  (`BaseAgent.generate_onboarding`) — unchanged by R-2.
- No user-visible changes.
```

Leave the "Pending phases" table intact (do not duplicate or delete it).

- [ ] **Step 2: Prepend the R-2 changelog entry in `Docs/CHANGELOG.md`**

Insert directly below `# Changelog` (above the existing R-1 entry):

```markdown
## [2026-05-16] R-2 — Agentic OS Concierge Code Split

### Added
- **New `kaia/concierge/` package.** `Concierge.handle_general_turn(...)`
  owns the orchestration of a general (non-expert) KAIA turn: profile
  load, history build, skill routing, conversation persistence, expert
  suggestion, background extraction. Returns a transport-agnostic
  `ConciergeResult`.
- **`concierge.welcome_text()`.** Single source of truth for KAIA's
  `/start` greeting.

### Changed
- **`bot/telegram_bot.py` is now a thin Telegram transport.** `cmd_start`,
  `handle_message`, and `handle_voice` delegate to the concierge. The
  general-flow block previously duplicated across the text and voice
  handlers is unified into one `Concierge.handle_general_turn` call.

### Migration notes
- No behavior change. The text path runs the (stateful) expert-topic
  detector; the voice path still does not (`suggest_experts=False`) —
  the pre-R-2 divergence is preserved exactly.
- Expert first-visit onboarding is unchanged (still expert-owned). The
  DESIGN open question on concierge-owned onboarding remains open.
- Background memory extraction stays fire-and-forget; it now starts a few
  statements earlier (inside the concierge call). Non-blocking, not
  user-visible.
```

- [ ] **Step 3: Mark R-2 complete in `Docs/DEVELOPMENT_STATUS.md`**

In the `### Agentic OS Migration` table added in R-1, change the R-2 row from:

```markdown
| R-2   | ⏳ Planned    | Concierge code split (`kaia/concierge/`)                        |
```

to:

```markdown
| R-2   | ✅ Complete   | Concierge code split (`kaia/concierge/`)                        |
```

Leave the R-1, R-3, R-4, R-5 rows unchanged.

- [ ] **Step 4: Commit**

```bash
git add Docs/ARCHITECTURE.md Docs/CHANGELOG.md Docs/DEVELOPMENT_STATUS.md
git commit -m "docs: log R-2 concierge split; mark R-2 complete"
```

---

## Task 6: Final smoke check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run:
```bash
cd /home/ejay/Kaia/kaia && python3 -m pytest -q
```
Expected: all pass — the 5 pre-existing `test_base_agent.py` tests plus the 8 new concierge tests (5 in `test_concierge.py` + 3 in `test_concierge_onboarding.py`) = **13 passed** (the other `tests/test_*.py` files are empty stubs and collect nothing).

- [ ] **Step 2: Verify the bot imports cleanly**

Run:
```bash
cd /home/ejay/Kaia/kaia && python3 -c "import bot.telegram_bot; print('bot imports ok')"
```
Expected: `bot imports ok`

- [ ] **Step 3: Confirm the welcome string has exactly one source**

Run:
```bash
cd /home/ejay/Kaia/kaia && grep -rn "your personal AI assistant" --include='*.py' .
```
Expected: exactly **one** match — `concierge/onboarding.py`. (Proves the `/start` string is no longer duplicated in `bot/telegram_bot.py`.)

- [ ] **Step 4: Confirm the general-flow block is no longer duplicated**

Run:
```bash
cd /home/ejay/Kaia/kaia && echo -n "skill_router.route in bot: "; grep -c "skill_router.route(" bot/telegram_bot.py; echo -n "concierge.handle_general_turn call sites: "; grep -c "concierge.handle_general_turn(" bot/telegram_bot.py
```
Expected: `skill_router.route in bot: 0` and `concierge.handle_general_turn call sites: 2` (text + voice).

- [ ] **Step 5: Verify the concierge never imports Telegram (transport-agnostic)**

Run:
```bash
cd /home/ejay/Kaia/kaia && grep -rn "telegram" concierge/ || echo "clean: concierge has zero telegram imports"
```
Expected: `clean: concierge has zero telegram imports`

- [ ] **Step 6: Verify R-2 git history is clean**

Run:
```bash
git log --oneline -7
```
Expected: 5–6 R-2 commits, each scoped to one task, all on `add-expert-channel-system`, sitting on top of the R-1 commits.

- [ ] **Step 7: Confirm R-2 added no changes under `agent_runtime/` or `experts/`**

Run:
```bash
git diff f137fd0..HEAD --stat -- kaia/agent_runtime kaia/experts
```
(`f137fd0` is the commit just before R-1's runtime work began.) Expected: only the R-1 files appear (`agent_runtime/*`, `experts/base.py`, `experts/__init__.py`); **no file with an R-2 commit** is listed. R-2 must not modify R-1 runtime or any expert.

---

## Self-Review Results

- **Spec coverage:**
  - `DESIGN.md` "R-2: Concierge code split: `kaia/concierge/` owns general flow + onboarding" → Tasks 2 (skeleton + onboarding), 3 (general flow), 4 (wiring).
  - "Not user-visible" → enforced by the 9 Behavior-Preservation Invariants, verified in Task 3 (unit tests) and Task 4 Step 6 (review checklist) + Task 6 Steps 3–4.
  - Standing docs rule (`MEMORY.md` → every code change updates docs/) → Tasks 1 and 5.
  - DESIGN open question on concierge-owned onboarding → explicitly **left open** (Scope Check), not silently decided.
- **Placeholder scan:** Every step shows full code or an exact command with expected output. No `TBD`/`TODO`/"add appropriate"/"similar to Task N" patterns.
- **Type consistency:** `ConciergeResult` fields (`text`, `skill_name`, `ai_response`, `suggestion`, `profile_context`) defined in Task 2 are used identically in Task 3 (constructed) and Task 4 (`result.text`, `result.suggestion`, `result.ai_response`, `result.profile_context`). `Concierge.handle_general_turn(user, message, *, suggest_experts: bool)` signature is identical across the Task 3 definition, Task 3 tests, and both Task 4 call sites. `welcome_text()` is identical in Tasks 2, 3, 4, 6.
- **Risk:** The behavior-sensitive change is Task 4. Controlled by: (a) the `suggest_experts` flag preserving the stateful text/voice detector divergence (invariant #2, unit-tested in Task 3); (b) returning `profile_context` so voice TTS keeps a single profile load off the same string (invariant #4); (c) the Task 4 Step 6 line-by-line checklist; (d) Task 6 Step 7 proving R-1/experts untouched. The one accepted, documented difference is background extraction starting a few statements earlier — fire-and-forget, non-blocking, not user-visible (invariant #9).
