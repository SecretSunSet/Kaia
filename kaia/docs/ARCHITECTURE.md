# KAIA Architecture

## Overview

KAIA is a **modular monolith** with a skills-based architecture. A single Python process handles all Telegram interactions, AI calls, database operations, and scheduled jobs.

## System Diagram

```
┌─────────────┐
│  Telegram    │
│  User        │
└──────┬───────┘
       │ Message (text / voice / command)
       ▼
┌──────────────────────────────────────────────────┐
│  bot/telegram_bot.py — Entry Point               │
│  ┌────────────────────────────────────────────┐  │
│  │ Commands: /start /help /status /briefing   │  │
│  │           /export /reset                   │  │
│  │ Handlers: handle_message, handle_voice,    │  │
│  │           handle_callback                  │  │
│  │ Middleware: rate limiting, AI cost tracking │  │
│  │ Access Control: _is_allowed()              │  │
│  └────────────────┬───────────────────────────┘  │
└───────────────────┼──────────────────────────────┘
                    │
       ┌────────────▼────────────┐
       │  core/intent_detector   │  ✅ Implemented
       │  (AI classification)    │
       └────────────┬────────────┘
                    │
       ┌────────────▼────────────┐
       │  core/skill_router      │  ✅ Implemented
       │  (dispatch to handler)  │
       └────────────┬────────────┘
                    │
   ┌────────────────┼────────────────────────────────────┐
   │                │                                    │
   ▼                ▼                ▼         ▼         ▼
┌────────┐  ┌────────────┐  ┌──────────┐ ┌────────┐ ┌────────┐
│  Chat  │  │  Memory    │  │ Reminders│ │ Budget │ │  Web   │
│ Skill  │  │  Skill     │  │  Skill   │ │ Skill  │ │ Browse │
└───┬────┘  └────────────┘  └──────────┘ └────────┘ └────────┘
    │           All skills share:
    ▼           ┌──────────────────────────────┐
┌─────────┐    │ core/ai_engine.py             │
│ Claude  │◄───│ - chat() with fallback        │
│  API    │    │ - auto-prepends Current Time  │
└─────────┘    │   Context to every system     │
               │   prompt (tz-aware)           │
               │ - AIResponse wrapper          │
               └──────────────────────────────┘
    │ fail?        │
    ▼              ▼
┌─────────┐    ┌──────────────────────────┐
│  Groq   │    │ database/                │
│  API    │    │ - connection.py (client)  │
│(fallback│    │ - queries.py (CRUD)       │
└─────────┘    │ - models.py (dataclasses) │
               └──────────────────────────┘
                       │
                       ▼
               ┌──────────────┐
               │   Supabase   │
               │  (PostgreSQL)│
               └──────────────┘
```

## Layer Responsibilities

### Bot Layer (`bot/`)

- Receives Telegram updates (polling) — text, voice, commands, callback queries
- Enforces access control (`ALLOWED_TELEGRAM_IDS`)
- Rate limiting (20 msg/min per user) via `bot/middleware.py`
- Voice message handling: download → transcribe (Groq Whisper) → process through skill pipeline → optional TTS reply (edge-tts)
- Sends typing indicators
- Dispatches to skill pipeline via `SkillRouter`
- Truncates responses to Telegram's 4096 char limit
- Tracks AI token usage and estimated cost
- Extended commands: `/status` (DB stats), `/export` (JSON data export), `/reset` (data deletion with confirmation)
- Inline callback handling for reminder snooze/dismiss buttons
- Handles errors gracefully with structured logging

### Core Layer (`core/`)

| Module | Responsibility | Status |
|--------|---------------|--------|
| `ai_engine.py` | Claude + Groq API calls, fallback logic, token tracking | Implemented |
| `intent_detector.py` | AI-powered message classification → skill ID + confidence | Implemented |
| `skill_router.py` | Maps intent → skill handler instance, manages skill registry | Implemented |
| `memory_manager.py` | Profile loading/formatting, background extraction orchestration | Implemented |
| `scheduler.py` | APScheduler job management for reminders + daily briefing scheduling | Implemented |

### Skills Layer (`skills/`)

Each skill extends `BaseSkill` and implements `handle()`. Skills are stateless — all state lives in the database. Skills receive full user context (profile + history) and return a `SkillResult`.

| Skill | Directory | Status |
|-------|-----------|--------|
| Chat | `skills/chat/` | Implemented |
| Memory | `skills/memory/` | Implemented |
| Reminders | `skills/reminders/` | Implemented |
| Budget | `skills/budget/` | Implemented |
| Briefing | `skills/briefing/` | Implemented |
| Web Browse | `skills/web_browse/` | Implemented |

### Database Layer (`database/`)

- `connection.py` — Singleton Supabase client
- `models.py` — Dataclass models (not ORM — lightweight)
- `queries.py` — Async query functions wrapping Supabase REST API
- `migrations/` — SQL files for Supabase SQL Editor

### Config Layer (`config/`)

- `settings.py` — Pydantic settings (env vars → typed Python)
- `constants.py` — Enums-as-lists, magic numbers, category definitions

### Utils Layer (`utils/`)

Stateless helper functions. No business logic.

| Module | Purpose |
|--------|---------|
| `time_utils.py` | Timezone conversion, UTC helpers, recurrence calculation, current-time-context formatter for prompt injection, relative-time formatter for conversation history and transactions |
| `voice_stt.py` | Groq Whisper speech-to-text transcription |
| `voice_tts.py` | edge-tts text-to-speech generation, temp file management |
| `validators.py` | Input sanitisation, amount/timezone/currency validation |
| `formatters.py` | Telegram markdown escaping, currency formatting, truncation |

## Data Flow — Text Message Processing

```
1. Telegram delivers update to bot
2. handle_message() fires
3. Access control check (_is_allowed)
4. Reset confirmation check (handle_reset_confirmation)
5. Rate limit check (check_rate_limit)
6. get_or_create_user() — ensure user exists in DB
7. memory_mgr.load_profile_context() — load + format profile
8. get_recent_conversations() — load last N messages, each prefixed with [<relative time>] so the model can reason about *when* prior turns happened
9. IntentDetector.detect() — classify message → skill + confidence
10. SkillRouter.route() — dispatch to matched skill handler
11. skill.handle() — build system prompt, call AI (which auto-prepends a Current Time Context block to the system prompt — see "Time Awareness" below), get response
12. save_conversation() — persist user message + bot response
13. reply_text() — send truncated response back to Telegram
14. memory_mgr.run_background_extraction() — fire-and-forget async task
15. track_ai_usage() — record token counts and estimated cost
```

## Time Awareness

LLMs have no inherent knowledge of the current date — without explicit injection they fall back to their training-data cutoff (KAIA was answering as if it were 2024 in 2026). KAIA injects "now" at a single chokepoint:

- `AIEngine.chat()` automatically prepends a `# Current Time Context` block to every `system_prompt` it forwards to Claude/Groq. The block is formatted by `utils.time_utils.format_current_context()` and includes the current weekday, full date, time, year, IANA timezone, and UTC offset. An optional `user_timezone` parameter overrides the default (`settings.default_timezone`, "Asia/Manila").
- Conversation history loaders (`BaseExpert.get_conversation_history()` for channel turns, `bot/telegram_bot.py` for general turns) prefix every prior message with a relative-time tag (`[3 days ago]`, `[yesterday at 3:45 PM]`) using `utils.time_utils.format_relative_time()`.
- Hevn's `_budget_summary` appends the most recent transactions formatted with `utils.time_utils.format_transaction_with_time()` so she sees "logged 5 days ago" rather than just totals.
- The memory extractor prompts (general + channel) include a clause instructing the model to resolve relative phrases ("yesterday", "last week") into absolute ISO dates using the injected time context.
- Budget period resolution (`resolve_period`, `_check_budget_warning`) and the daily-briefing header use `utils.time_utils.today_in_tz()` instead of the UTC-bound `date.today()` so "today" lines up with the user's local calendar day.

This combination means every Claude call across KAIA, every expert, onboarding, and memory extraction is time-aware with no per-prompt edits.

## Data Flow — Voice Message Processing

```
1. Telegram delivers voice/audio update
2. handle_voice() fires
3. Access control + rate limit checks
4. Download .ogg file from Telegram servers
5. transcribe_voice() — Groq Whisper STT → text
6. Reply: "🎙️ I heard: {transcribed text}"
7. Steps 6–15 from text message flow (using transcribed text)
8. If voice_replies enabled → text_to_speech() → reply with audio
9. Cleanup temp files (voice .ogg + TTS .mp3)
```

## Data Flow — Memory Learning

```
1. After each conversation exchange (steps 1–11 above)
2. run_background_extraction() creates an asyncio task
3. extract_and_save() loads current profile, sends conversation to Claude
4. Claude returns JSON array of structured facts
5. _parse_facts() extracts facts from AI response
6. upsert_profile_entry() for each new/updated fact
7. add_memory_log() to record what was learned + session ID
8. Next conversation loads updated profile at step 5
```

## External APIs

| API | Used By | Purpose |
|-----|---------|---------|
| Telegram Bot API | `bot/telegram_bot.py` | Message send/receive, commands, inline buttons |
| Anthropic Claude | `core/ai_engine.py` | Primary AI for all skills |
| Groq | `core/ai_engine.py` | Fallback AI when Claude fails |
| Supabase REST | `database/connection.py` | All database operations |
| SerpAPI | `skills/web_browse/search.py` | Web search (Phase 5) |
| OpenWeather | `skills/briefing/handler.py` | Weather data for briefing (Phase 5) |
| NewsAPI | `skills/briefing/handler.py` | Headlines for briefing (Phase 5) |
| Groq Whisper | `utils/voice_stt.py` | Voice transcription (Phase 6) |
| edge-tts | `utils/voice_tts.py` | Text-to-speech replies (Phase 6) |

## Deployment Flow

```
┌──────────────────┐       push to main        ┌────────────────────┐
│   Developer      │ ─────────────────────────▶│   GitHub (main)    │
│   local repo     │                           └──────────┬─────────┘
└──────────────────┘                                      │
                                                          │ triggers
                                                          ▼
                                         ┌─────────────────────────────┐
                                         │ GitHub Actions              │
                                         │ .github/workflows/deploy.yml│
                                         │ (appleboy/ssh-action)       │
                                         └──────────────┬──────────────┘
                                                        │ SSH (secret key)
                                                        ▼
┌────────────────────────────────────────────────────────────────────┐
│ AWS EC2 t4g.small — 3.106.134.24 — Ubuntu 24.04 (ARM, 2 vCPU, 2GB) │
│                                                                    │
│  /opt/kaia/                                                        │
│   ├── venv/              (Python 3.11 virtualenv)                  │
│   └── app/               (git clone of repo)                       │
│        ├── .env          (API keys — created on server, not in git)│
│        └── deploy/                                                 │
│             ├── setup-server.sh    (one-time bootstrap)            │
│             ├── kaia.service       (systemd unit)                  │
│             └── update.sh          (manual pull & restart)         │
│                                                                    │
│  systemd  ─▶  kaia.service  ─▶  python -m bot.telegram_bot         │
│              (auto-restart, journal logs, MemoryMax=1G, CPU=80%)   │
└────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                   Telegram / Anthropic / Supabase / Groq
```

On push to `main`:
1. GitHub Actions SSHes into EC2 as `ubuntu`.
2. `git pull origin main` in `/opt/kaia/app`.
3. `pip install -r requirements.txt` inside the venv.
4. `sudo systemctl restart kaia` — systemd restarts the bot, keeping it alive.

## Data Flow — MakubeX (Tech Lead) Turn

```
1. Message arrives in /makubex channel (DM) or MakubeX forum topic
2. MakubeXExpert.handle(user, message, channel)
3. First visit? → generate_onboarding() + schedule_makubex_weekly_brief()
                  (CronTrigger: Mon 08:00 user timezone)
4. Otherwise classify_makubex_intent() runs keyword short-circuits over 8
   intents (code_review / architecture / debugging / devops / security /
   tech_research / learning_coach / project_manager) with fenced code
   blocks auto-routing to code_review. Falls back to an AI classifier.
5. Specialized _run_* handler dispatches:
   - code_review → extract_code_block() → CodeReviewSkill.review_code()
     → SHA-256 hash lookup in code_reviews for dedup → format_review()
   - project_manager → parse_project_creation() OR format_projects_list()
   - architecture / devops / security / research / learning → matching
     skill method, seeded with a tech context block built from active
     tech_projects + tech_skills
6. If no deterministic route → _persona_response() builds the full
   MakubeX system prompt (active projects / skills / recent learning /
   shared profile / channel profile / top knowledge gap) and streams
   AI chat.
7. save_messages() persists the turn to channel_conversations.
8. _fire_extraction() spawns makubex_extract_and_save() which runs the
   generic channel extractor, then mirrors selected categories
   (tech_stack / skills / projects / work_context / infrastructure) into
   user_profile under the "technical" category.
9. Weekly brief cron fires Monday 08:00 → MakubeX proactive skill
   assembles active projects + this-week learning + recent reviews +
   next topic + web-sourced security advisories → delivered to the
   MakubeX topic when mapped, otherwise DM with /makubex footer.
```

## Design Decisions

1. **Modular monolith over microservices** — Single process simplifies deployment and debugging. Skills are isolated modules that could be split out later if needed.
2. **Supabase over raw PostgreSQL** — Hosted DB with REST API, auth, and dashboard. No connection pool management needed.
3. **Dataclasses over ORM** — Lightweight, no migration tooling needed. Supabase REST handles serialisation.
4. **Async handlers, sync DB client** — python-telegram-bot v20 requires async handlers. Supabase-py is sync but wraps HTTP calls that are fast enough for single-user use. Query functions are declared `async` for interface consistency.
5. **Profile injection over RAG** — The full user profile is small enough to fit in the system prompt. No vector DB or embedding search needed.
6. **Polling over webhooks** — Simpler deployment, no public URL needed. Suitable for single-user bot.
