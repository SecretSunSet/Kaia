# Changelog

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

## [2026-04-20] Hotfix — Budget Logging & Hevn Intent Detection

### Fixed
- **Budget: verbose log phrases misclassified as summary.** Messages like
  "log into expenses Tiktok Shop Elyse essentials 350 pesos" contained the
  word "expenses" and were routed to the summary handler instead of being
  logged as a transaction. `skills/budget/handler.py` now runs an explicit
  log-intent check (`_is_log_request`) before the summary check, so any
  phrasing starting with `log`, `add to expense(s)`, `record`, `paid`,
  `spent`, `bought` is routed to `_handle_log_transaction`.
- **Budget: single-line parser strips command verbs.** The parse prompt
  (`skills/budget/prompts.py`) now instructs the model to drop routing
  phrases ("log into expenses", "add to expense", "log these expenses:")
  from the description and accept free-form descriptions with merchants /
  modifiers / dash / colon separators.
- **Hevn: advice-style questions routed to goals.list().** "How much
  should my emergency fund be?" matched the "emergency fund" short-circuit
  and returned the "No active goals yet" boilerplate. `classify_hevn_intent`
  now has an `ADVICE_MARKERS` list (`"how much should"`, `"should i "`,
  `"is my "`, `"what's a good"`, etc.) that wins over all other
  short-circuits and routes to `general_chat` so Hevn answers with
  personalized advice. Goal short-circuit tightened to explicit markers
  like "set a goal", "show my goals", "create goal".
- **Hevn: goal references from conversation context.** `_run_goals` now
  pulls the last 6 Hevn messages via `get_channel_conversations` when the
  user says "let's set this as our first goal" / "set that as my goal",
  so the goal parser can resolve the target from Hevn's prior suggestion.
  If still unparseable, Hevn asks for the missing target + timeline
  instead of silently falling back to the goals list.

### Added
- **`parse_bulk_transactions`** (`skills/budget/parser.py`) — parses a
  multi-line transaction block (e.g. `log these expenses\n140 - Dishwashing
  Liquid\n120 - 1.5L Coconut oil\n177 - Eggs`) into a list of transactions.
  Header lines without numbers are skipped; lines are parsed concurrently.
- **`format_bulk_log_response`** (`skills/budget/prompts.py`) — per-category
  breakdown with totals for bulk log confirmations.
- **`HEVN_INTENT_PROMPT`** rewritten to explicitly distinguish ASKING
  ADVICE about goals vs MANAGING goal records.

---

## [2026-04-19] Phase CH-2 — Hevn (Financial Advisor) Full Implementation

### Added
- **Hevn expert** — replaces the generic `PlaceholderExpert` for the `hevn` channel with a full financial advisor with 7 specialized skills.
- **New database tables** (migration `004_hevn.sql`):
  - `financial_goals` — per-user goals with target, current progress, monthly contribution, deadline, priority, and status (`active`/`paused`/`completed`).
  - `recurring_bills` — per-user bills with amount, due_day, recurrence (`monthly`/`weekly`/`yearly`/`quarterly`), category, active flag, last_paid.
- **New model dataclasses**: `FinancialGoal`, `RecurringBill`.
- **New query helpers**: full CRUD for financial goals and recurring bills in `database/queries.py`.
- **`HevnExpert`** (`experts/hevn/expert.py`) — routes first-visit onboarding, intent classification, specialized-skill dispatch, and persona-driven AI response.
- **Seven Hevn skills** under `experts/hevn/skills/`:
  - `health_assessment` — weighted 1-100 financial health score across savings rate, debt ratio, emergency fund, income stability, expense control.
  - `budget_coaching` — spending pattern analysis, period-over-period change, waste detection (food delivery, subscriptions, repeated vendors).
  - `goals_manager` — create / track / project goals; milestone celebrations at 25/50/75/100%; salary allocation suggestions.
  - `bills_tracker` — recurring bills with computed next-due dates, upcoming-7-days view, monthly-total calculation, forgotten-subscription detection.
  - `market_trends` — BSP rate, PSEi, USD/PHP, PH financial news via web search; per-user impact explanation.
  - `education` — progressive topic catalog (basics → advanced, PH-specific); adapts explanations to user level; tracks learned topics.
  - `proactive` — weekly digest, spending alerts, goal milestones, salary-received allocation suggestions.
- **Hevn's memory extractor** (`experts/hevn/extractor.py`) — extends the channel extractor; major financial facts (income, debt, savings, retirement, insurance, goals) are mirrored to the shared `user_profile` under category `finances` so other experts (Kazuki, etc.) can read them.
- **Intent classifier** (`experts/hevn/parser.py`) — deterministic keyword short-circuit with AI JSON fallback; also includes goal and bill parsers.
- **Weekly digest scheduler** (`core/scheduler.py`: `schedule_hevn_weekly_digest`) — fires every Sunday at 09:00 user's timezone using APScheduler `CronTrigger`. Registered on the user's first `/hevn` visit (never before), so users don't receive digests they didn't ask for. Digest is delivered to the Hevn forum topic if one exists for that chat, otherwise to DM with a `/hevn to discuss` footer.
- **Budget Tracker integration** — when a salary income is logged, if the user has already met Hevn, a proactive allocation suggestion is appended to the transaction confirmation.
- **Four Hevn shortcut commands** (work in DM and Forum Topics mode):
  - `/hevn_health` — on-demand financial health report.
  - `/hevn_goals` — formatted goals overview.
  - `/hevn_bills` — upcoming bills (fallback to full bill list).
  - `/hevn_digest` — generate the weekly digest on demand.

### Changed
- `experts/__init__.py` — registers `HevnExpert` for `CHANNEL_HEVN`; other channels remain on `PlaceholderExpert`.
- `skills/budget/handler.py` — `_handle_log_transaction` appends Hevn's salary allocation suggestion for income+salary transactions when the user has met Hevn.
- `bot/commands.py` — `/reset` now cascades through `financial_goals` and `recurring_bills`.
- `bot/telegram_bot.py` — registers the four new Hevn commands and lists them under "Hevn shortcuts" in `/help`.

### Notes
- Migration `004_hevn.sql` must be run in Supabase before this version is deployed.
- The digest respects the user's timezone stored in `users.timezone` (defaults to `Asia/Manila`).

---

## [2026-04-19] Phase CH-1.1 — Forum Topics Support

### Added
- **Dual-mode operation**: KAIA now runs in either DM mode (existing `/hevn`, `/exit` command switching) or Forum Topics mode (each expert gets a dedicated sub-thread in a Telegram forum group). The message handler auto-detects the mode per incoming message.
- **New `forum_topic_mappings` table** (migration `003_forum_topics.sql`) mapping `(chat_id, channel_id) ↔ topic_id`.
- **`/setup_forum`** command — one-time setup that creates four expert topics in a forum-enabled group and saves the mappings.
- **`ForumManager`** (`kaia/core/forum_manager.py`) — create topics via `bot.create_forum_topic`, look up channel-for-topic / topic-for-channel, store mappings.
- **Forum-aware routing**: in a forum group the user's current topic determines which expert replies; no per-user channel state is used. Expert replies are sent with `message_thread_id` so they stay in the correct topic.
- **Configuration flag**: `FORUM_MODE_ENABLED` (default `True`) in `config/settings.py`.

### Changed
- `bot/telegram_bot.py` — `handle_message` and `handle_voice` now branch on forum vs DM; a shared `_handle_expert_turn()` helper unifies expert dispatch.
- `/team` renders a topic-based roster in forum mode.
- Expert commands (`/hevn`, `/kazuki`, `/akabane`, `/makubex`) in forum mode redirect the user to the expert's topic instead of switching DM state.
- `/exit` in forum mode explains that topics replace explicit switching.

### Notes
- Bot must be a group admin with the **Manage Topics** permission before `/setup_forum` can create threads; the command reports a clear error if that permission is missing.
- Migration `003_forum_topics.sql` must be run in Supabase before this version is deployed.

---

## Phase CH-1 — Expert Channel System (Infrastructure)

### Added
- **Expert Channel System** foundation: KAIA now has a team of 4 named AI experts (Hevn, Kazuki, Akabane, MakubeX) plus herself as team lead.
- **New database tables**: `channels`, `user_channel_state`, `channel_profile`, `channel_conversations` (migration `002_channels.sql`).
- **Channel commands**: `/hevn`, `/kazuki`, `/akabane`, `/makubex`, `/exit`, `/team`.
- **Per-channel memory**: separate memory profile per expert via `channel_profile` table.
- **Per-channel conversation history**: separate message history per expert via `channel_conversations`.
- **Knowledge gap detection**: priority-based per-channel required knowledge lists drive proactive questioning (one question per response max).
- **Expert suggestions in general chat**: KAIA gently suggests relevant experts when a topic matches their domain (rule-based keyword matching, no extra AI cost).
- **PlaceholderExpert**: generic expert that uses channel persona from DB — all commands work immediately with the correct in-character response, even before specialized skills ship.

### New Modules
- `kaia/core/channel_manager.py` — channel switching state
- `kaia/core/channel_memory.py` — per-channel memory + knowledge gap tracking
- `kaia/core/channel_extractor.py` — domain-focused fact extraction per channel
- `kaia/core/expert_detector.py` — suggest experts from general chat
- `kaia/experts/base.py` — `BaseExpert` abstract class
- `kaia/experts/__init__.py` — expert registry
- `kaia/experts/placeholder.py` — default expert using channel persona

### Changed
- `bot/telegram_bot.py` — `handle_message` and `handle_voice` now check active channel and route to expert system for non-general channels; general flow now suggests experts when chat skill handles financial/investment/trading/tech topics.
- `bot/commands.py` — `/status` shows active channel + channel stats; `/export` includes channel data; `/reset` deletes all channel data.
- `config/constants.py` — added channel IDs, emojis, and `CHANNEL_REQUIRED_KNOWLEDGE` dict.
- `database/models.py` — added `Channel`, `UserChannelState`, `ChannelProfileEntry`, `ChannelConversation` dataclasses.
- `database/queries.py` — ~10 new channel-related query functions.

### Notes
- Phase CH-1 is infrastructure only. Each expert's specialized skills (Hevn's budget coaching, MakubeX's code review, etc.) ship in subsequent phases (CH-2 through CH-5).
- Migration `002_channels.sql` must be run in Supabase SQL editor before deploying.

---

## Phase 1 — Initial Release

- Telegram bot with 6 skills: chat, memory, reminders, budget, briefing, web search
- Voice input (Groq Whisper) and voice output (edge-tts)
- Deployed on AWS EC2 with Docker + systemd + GitHub Actions CI/CD
