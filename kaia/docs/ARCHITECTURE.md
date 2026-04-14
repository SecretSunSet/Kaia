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
    ▼           ┌─────────────────────────┐
┌─────────┐    │ core/ai_engine.py        │
│ Claude  │◄───│ - chat() with fallback   │
│  API    │    │ - AIResponse wrapper     │
└─────────┘    └─────────────────────────┘
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
| `time_utils.py` | Timezone conversion, UTC helpers, recurrence calculation |
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
8. get_recent_conversations() — load last N messages
9. IntentDetector.detect() — classify message → skill + confidence
10. SkillRouter.route() — dispatch to matched skill handler
11. skill.handle() — build system prompt, call AI, get response
12. save_conversation() — persist user message + bot response
13. reply_text() — send truncated response back to Telegram
14. memory_mgr.run_background_extraction() — fire-and-forget async task
15. track_ai_usage() — record token counts and estimated cost
```

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

## Design Decisions

1. **Modular monolith over microservices** — Single process simplifies deployment and debugging. Skills are isolated modules that could be split out later if needed.
2. **Supabase over raw PostgreSQL** — Hosted DB with REST API, auth, and dashboard. No connection pool management needed.
3. **Dataclasses over ORM** — Lightweight, no migration tooling needed. Supabase REST handles serialisation.
4. **Async handlers, sync DB client** — python-telegram-bot v20 requires async handlers. Supabase-py is sync but wraps HTTP calls that are fast enough for single-user use. Query functions are declared `async` for interface consistency.
5. **Profile injection over RAG** — The full user profile is small enough to fit in the system prompt. No vector DB or embedding search needed.
6. **Polling over webhooks** — Simpler deployment, no public URL needed. Suitable for single-user bot.
