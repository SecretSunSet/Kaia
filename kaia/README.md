# KAIA — Knowledge-Aware Intelligent Assistant

A Telegram-based personal AI assistant that answers questions, learns about you over time, manages reminders, tracks your budget, delivers daily briefings, and browses the web — all through natural language.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Configuration Reference](#configuration-reference)
- [Database Schema](#database-schema)
- [Core Systems](#core-systems)
  - [AI Engine](#ai-engine)
  - [Skill System](#skill-system)
  - [Memory & Learning](#memory--learning)
  - [Intent Detection & Routing](#intent-detection--routing)
  - [Voice Interface](#voice-interface)
- [Skills Reference](#skills-reference)
- [Telegram Commands](#telegram-commands)
- [Development Phases](#development-phases)
- [Deployment](#deployment)
- [Cost & Usage Notes](#cost--usage-notes)

---

## Features

| Feature | Description |
|---------|-------------|
| **Chat & Q&A** | General conversation powered by Claude AI with full user context |
| **Evolving Memory** | Learns about you over time — explicit facts and inferred patterns |
| **Reminders** | Natural language reminders with recurrence, snooze, and inline buttons |
| **Budget Tracking** | Log income/expenses, auto-categorise, set limits, get summaries |
| **Daily Briefing** | Scheduled morning briefing with weather, tasks, budget, and news |
| **Web Browsing** | Search the web and summarise results for real-time information |
| **Voice** | Send voice notes (transcribed via Whisper) and receive voice replies |

All interactions happen through **natural language** on Telegram. No commands required — though slash commands are available as shortcuts.

---

## Architecture

```
User (Telegram) → Telegram API → Bot Server (Python, async)
                                      │
                                      ▼
                                Intent Detector (AI classifies message)
                                      │
                                      ▼
                                Skill Router → [Chat | Memory | Reminders | Budget | Briefing | Web Browse]
                                      │
                                      ▼
                                Claude API (with full user profile injected as system context)
                                      │
                                      ▼
                                Response → Telegram → User

Background:  Memory Extractor runs post-conversation → updates user profile in DB
Scheduler:   APScheduler fires reminders + daily briefing at configured times
Voice:       Voice notes transcribed via Whisper → processed as text through same pipeline
```

The system is a **modular monolith** with a skills-based architecture. Each skill is an isolated handler that receives a user message (with full context) and returns a response. The intent detector classifies incoming messages and the skill router dispatches to the correct handler.

---

## Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python 3.11+ | Async throughout |
| Bot Framework | python-telegram-bot v20+ | Async Telegram API wrapper |
| AI (Primary) | Claude API (Anthropic) | Model: `claude-sonnet-4-20250514` |
| AI (Fallback) | Groq API (Llama 3) | Free tier, automatic fallback |
| Database | Supabase (PostgreSQL) | Hosted PostgreSQL with REST API |
| Scheduler | APScheduler | In-process, for reminders + briefing |
| Web Search | SerpAPI | 100 free searches/month |
| Web Scraping | BeautifulSoup + httpx | Page content extraction |
| Speech-to-Text | Groq Whisper API | Free tier |
| Text-to-Speech | edge-tts (Microsoft) | Free, no API key needed |
| Audio Processing | pydub + ffmpeg | OGG/MP3 conversion |
| Config | pydantic-settings + python-dotenv | Typed env var loading |
| Logging | loguru | Structured, coloured logging |
| Hosting | Railway | Free tier → $5/mo |

---

## Project Structure

```
kaia/
├── bot/                              # Telegram bot layer
│   ├── __init__.py
│   ├── telegram_bot.py               # Main entry point, message handlers, inline buttons
│   ├── middleware.py                  # Pre/post processing: logging, rate limiting
│   └── commands.py                   # Slash command handlers (/start, /help, /status)
│
├── core/                             # Core engine modules
│   ├── __init__.py
│   ├── ai_engine.py                  # Claude API client, Groq fallback, response wrapper
│   ├── intent_detector.py            # AI-powered message classification and routing
│   ├── skill_router.py               # Maps detected intent → skill handler
│   ├── memory_manager.py             # Profile loading, injection, post-conversation extraction
│   └── scheduler.py                  # APScheduler setup, job management
│
├── skills/                           # Modular skill handlers
│   ├── __init__.py
│   ├── base.py                       # Abstract base class for all skills
│   ├── chat/
│   │   ├── handler.py                # General Q&A processing
│   │   └── prompts.py                # Chat-specific system prompts
│   ├── memory/
│   │   ├── handler.py                # Profile queries, fact management
│   │   ├── extractor.py              # Post-conversation fact extraction
│   │   └── prompts.py                # Memory extraction prompts
│   ├── reminders/
│   │   ├── handler.py                # Create, edit, delete, list reminders
│   │   ├── parser.py                 # NLP parsing of reminder requests
│   │   └── prompts.py                # Reminder-specific prompts
│   ├── budget/
│   │   ├── handler.py                # Transaction logging, summaries, budget checks
│   │   ├── parser.py                 # NLP parsing of financial messages
│   │   ├── reports.py                # Weekly/monthly report generation
│   │   └── prompts.py                # Budget-specific prompts
│   ├── briefing/
│   │   ├── handler.py                # Compile and send daily briefing
│   │   └── prompts.py                # Briefing composition prompts
│   └── web_browse/
│       ├── handler.py                # Search orchestration, result summarisation
│       ├── search.py                 # SerpAPI / Google Custom Search client
│       ├── scraper.py                # BeautifulSoup web page reader
│       └── prompts.py                # Web browse prompts
│
├── database/                         # Data layer
│   ├── __init__.py
│   ├── connection.py                 # Supabase client (singleton)
│   ├── models.py                     # Dataclass models mirroring DB tables
│   ├── queries.py                    # Reusable database query functions
│   └── migrations/
│       └── 001_initial.sql           # Initial schema creation (run in Supabase SQL Editor)
│
├── config/                           # Configuration
│   ├── __init__.py
│   ├── settings.py                   # Pydantic settings with env var loading
│   └── constants.py                  # App-wide constants (categories, limits, defaults)
│
├── utils/                            # Utilities
│   ├── __init__.py
│   ├── formatters.py                 # Telegram message formatting helpers
│   ├── validators.py                 # Input validation utilities
│   ├── time_utils.py                 # Timezone conversion, date parsing
│   ├── voice_stt.py                  # Speech-to-text: Groq Whisper transcription
│   └── voice_tts.py                  # Text-to-speech: edge-tts audio generation
│
├── tests/                            # Test suite
│   ├── test_intent_detector.py
│   ├── test_budget_parser.py
│   ├── test_reminder_parser.py
│   ├── test_memory_extractor.py
│   └── test_voice.py
│
├── .env.example                      # Environment variable template
├── .gitignore
├── requirements.txt                  # Python dependencies
├── Procfile                          # Railway worker process
├── railway.json                      # Railway deployment config
└── README.md                         # This file
```

---

## Setup & Installation

### Prerequisites

- Python 3.11 or higher
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- An Anthropic API key (from [console.anthropic.com](https://console.anthropic.com))
- A Supabase project (from [supabase.com](https://supabase.com))
- *(Optional)* Groq API key for fallback AI
- *(Optional)* SerpAPI key for web search
- *(Optional)* ffmpeg installed for voice message processing

### Step 1 — Clone and install dependencies

```bash
cd kaia
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 2 — Create the database

1. Go to your Supabase project dashboard
2. Open the **SQL Editor**
3. Paste the contents of `database/migrations/001_initial.sql`
4. Click **Run** to create all tables, indexes, and RLS policies

### Step 3 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys (see [Configuration Reference](#configuration-reference) below).

### Step 4 — Run the bot

```bash
python -m bot.telegram_bot
```

Send a message to your bot on Telegram. You should get a Claude-powered response.

---

## Configuration Reference

All configuration is loaded from environment variables (or a `.env` file) via Pydantic settings.

### Required

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `SUPABASE_URL` | Supabase project URL (e.g. `https://abc.supabase.co`) |
| `SUPABASE_KEY` | Supabase service-role or anon key |

### Optional — AI

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Claude model ID |
| `CLAUDE_MAX_TOKENS` | `1024` | Max tokens per Claude response |
| `GROQ_API_KEY` | *(empty)* | Groq API key; enables automatic fallback if Claude fails |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model ID |

### Optional — Services

| Variable | Default | Description |
|----------|---------|-------------|
| `SERPAPI_KEY` | *(empty)* | SerpAPI key for web search skill |
| `NEWS_API_KEY` | *(empty)* | NewsAPI key for daily briefing |
| `OPENWEATHER_API_KEY` | *(empty)* | OpenWeather key for briefing weather data |

### Optional — Voice

| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_VOICE` | `en-US-AriaNeural` | Microsoft edge-tts voice name |
| `VOICE_REPLIES_ENABLED` | `false` | Reply with voice audio by default |

### Optional — Behaviour

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLOWED_TELEGRAM_IDS` | *(empty)* | Comma-separated Telegram user IDs allowed to use the bot. Empty = allow all |
| `DEFAULT_TIMEZONE` | `Asia/Manila` | Default timezone for new users |
| `DEFAULT_CURRENCY` | `PHP` | Default currency for new users |
| `INTENT_CONFIDENCE_THRESHOLD` | `0.6` | Minimum confidence to route to a non-chat skill |
| `MAX_CONVERSATION_HISTORY` | `20` | Number of recent messages included as AI context |
| `LOG_LEVEL` | `INFO` | Loguru log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## Database Schema

Seven tables in Supabase PostgreSQL. All tables include `user_id` foreign keys to support multi-user scaling.

### `users`

Stores registered Telegram users.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `telegram_id` | BIGINT (unique) | Telegram user ID |
| `username` | VARCHAR(100) | Telegram username |
| `timezone` | VARCHAR(50) | User's timezone (default: `Asia/Manila`) |
| `currency` | VARCHAR(10) | Preferred currency (default: `PHP`) |
| `created_at` | TIMESTAMPTZ | Account creation time |
| `updated_at` | TIMESTAMPTZ | Last update time |

### `user_profile`

Evolving AI-generated user profile — the core of the memory system.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `user_id` | UUID (FK → users) | Owner |
| `category` | VARCHAR(50) | One of: `identity`, `health`, `finances`, `personality`, `preferences`, `goals`, `patterns` |
| `key` | VARCHAR(100) | Fact name (e.g. `name`, `daily_medication`) |
| `value` | TEXT | Fact value |
| `confidence` | FLOAT | 0.0–1.0, how confident the AI is in this fact |
| `source` | VARCHAR(20) | `explicit` (user stated it) or `inferred` (AI detected it) |
| `updated_at` | TIMESTAMPTZ | Last time this fact was updated |

Unique constraint on `(user_id, category, key)` — upserts update existing facts.

### `memory_log`

Timestamped log of every fact learned per conversation session.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `user_id` | UUID (FK → users) | Owner |
| `session_id` | VARCHAR(50) | Groups facts from the same conversation |
| `fact` | TEXT | The learned fact |
| `fact_type` | VARCHAR(30) | One of: `correction`, `preference`, `habit`, `mood`, `goal`, `general` |
| `created_at` | TIMESTAMPTZ | When the fact was learned |

### `reminders`

User-created reminders with optional recurrence.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `user_id` | UUID (FK → users) | Owner |
| `title` | VARCHAR(255) | Reminder text |
| `scheduled_time` | TIMESTAMPTZ | When to fire |
| `recurrence` | VARCHAR(50) | `none`, `daily`, `weekly`, `monthly`, or cron expression |
| `is_active` | BOOLEAN | Whether the reminder is active |
| `snooze_count` | INT | Number of times snoozed |
| `created_at` | TIMESTAMPTZ | Creation time |

### `transactions`

Budget tracking — income and expense records.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `user_id` | UUID (FK → users) | Owner |
| `amount` | DECIMAL(12,2) | Transaction amount |
| `type` | VARCHAR(10) | `income` or `expense` |
| `category` | VARCHAR(50) | Auto-categorised (see constants) |
| `description` | TEXT | Optional description |
| `transaction_date` | DATE | Date of transaction |
| `created_at` | TIMESTAMPTZ | Record creation time |

**Expense categories:** `food`, `transport`, `utilities`, `rent`, `groceries`, `entertainment`, `health`, `shopping`, `subscriptions`, `education`, `personal_care`, `gifts`, `travel`, `savings`, `other`

**Income categories:** `salary`, `freelance`, `gift`, `refund`, `investment`, `other`

### `conversations`

Chat history for context injection into AI prompts.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `user_id` | UUID (FK → users) | Owner |
| `role` | VARCHAR(10) | `user` or `assistant` |
| `content` | TEXT | Message text |
| `skill_used` | VARCHAR(50) | Which skill handled this message |
| `created_at` | TIMESTAMPTZ | Message timestamp |

### `budget_limits`

Per-category monthly spending limits for budget alerts.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated |
| `user_id` | UUID (FK → users) | Owner |
| `category` | VARCHAR(50) | Budget category |
| `monthly_limit` | DECIMAL(12,2) | Spending cap |
| `is_active` | BOOLEAN | Whether the limit is active |

---

## Core Systems

### AI Engine

**File:** `core/ai_engine.py`

The AI engine wraps both Claude (primary) and Groq (fallback) behind a unified interface.

- **`AIEngine.chat(system_prompt, messages, max_tokens)`** — Sends a request to Claude. If Claude fails (rate limit, network error, etc.), automatically retries with Groq.
- **`AIResponse`** — Standardised response wrapper containing: `text`, `provider` ("claude" or "groq"), `model`, `input_tokens`, `output_tokens`.
- **`build_message_history(conversations, current_message)`** — Converts conversation history + new message into the `[{role, content}]` format expected by both APIs.

Every API call is logged with token counts for cost monitoring.

### Skill System

**Files:** `skills/base.py`, `skills/*/handler.py`

Every skill extends `BaseSkill` and implements a single async method:

```python
async def handle(self, user, message, conversation_history, profile_context) -> SkillResult
```

- `user` — The `User` dataclass from the database
- `message` — The incoming text (already transcribed if voice)
- `conversation_history` — Recent messages as `[{role, content}]`
- `profile_context` — Pre-formatted user profile string for system prompt injection

Returns a `SkillResult` containing the response text, skill name, and optional AI response metadata.

**Available skills:**

| Skill | ID | Description |
|-------|----|-------------|
| Chat | `chat` | General Q&A — the default fallback |
| Memory | `memory` | "What do you know about me?", "Remember that..." |
| Reminders | `reminders` | "Remind me to...", "What reminders do I have?" |
| Budget | `budget` | "Spent ₱500 on food", "Budget summary" |
| Briefing | `briefing` | "Give me my briefing" (also auto-scheduled) |
| Web Browse | `web_browse` | "Search for...", "What's the latest on..." |

### Memory & Learning

**Files:** `core/memory_manager.py`, `skills/memory/extractor.py`

The memory system has three layers:

1. **Explicit Facts** — Things the user states directly ("My name is EJ", "I take metformin daily")
2. **Inferred Patterns** — Things the AI detects over time (spending habits, mood shifts, schedule preferences)
3. **Evolving Profile** — After each conversation, a background process asks the AI: *"What new facts did I learn about this user?"* and merges results into the `user_profile` table

**The learning loop:**

```
1. User sends a message
2. Bot loads FULL profile + recent conversation history from DB
3. Profile is injected into the Claude system prompt as structured context
4. Claude answers with full awareness of who the user is
5. After conversation → AI extracts new learnings in background
6. Profile is updated silently (upsert on user_id + category + key)
7. Next conversation → Claude knows more than before
```

**Profile categories:** `identity`, `health`, `finances`, `personality`, `preferences`, `goals`, `patterns`

Each profile entry has a **confidence score** (0.0–1.0) and a **source** (`explicit` or `inferred`). Explicit facts from the user get higher confidence than AI-inferred ones. The profile is formatted and injected into every system prompt so the AI always has full user context.

### Intent Detection & Routing

**Files:** `core/intent_detector.py`, `core/skill_router.py`

When a message arrives, the intent detector sends it to Claude with a classification prompt. Claude returns which skill should handle it along with a confidence score.

**Routing rules:**
- If confidence is below `0.6` (configurable via `INTENT_CONFIDENCE_THRESHOLD`), default to the `chat` skill
- Voice messages are first transcribed, then routed through the same pipeline
- The intent detector also handles multi-intent messages (e.g. "remind me to buy groceries and how's my budget?")

**Skill mapping examples:**

| Message | Detected Intent | Skill |
|---------|----------------|-------|
| "What's the meaning of life?" | chat | `chat` |
| "Remember that I'm allergic to shrimp" | memory | `memory` |
| "Remind me to take meds at 8pm" | reminders | `reminders` |
| "Spent ₱350 on lunch" | budget | `budget` |
| "Give me my briefing" | briefing | `briefing` |
| "What's the latest news on AI?" | web_browse | `web_browse` |

### Voice Interface

**Files:** `utils/voice_stt.py`, `utils/voice_tts.py`

- **Inbound:** User sends a Telegram voice note (.ogg) → bot downloads → converts to supported format → sends to Groq Whisper API → transcribed text routes through the normal skill pipeline
- **Outbound:** Bot replies with voice audio using edge-tts. Triggered when the user sends a voice note (reply in kind) or when voice replies are enabled in user preferences
- Voice preference is stored in `user_profile` (preferred voice, voice replies on/off)

---

## Skills Reference

### Chat (`skills/chat/`)

The default skill for general conversation and Q&A. Claude receives the full user profile as system context so it can personalise responses. Falls back to Groq if Claude is unavailable.

**Prompt structure:**
```
System: KAIA persona + rules + user profile
Messages: Recent conversation history + current message
```

### Memory (`skills/memory/`)

Handles explicit memory operations and runs silently after every conversation.

- **Explicit:** "Remember that I like sushi", "What do you know about me?", "Forget my old address"
- **Background extraction:** After each conversation, the extractor analyses the exchange and identifies new facts to save
- **Profile queries:** "What do you know about my health?", "What are my goals?"

### Reminders (`skills/reminders/`)

Natural language reminder management with APScheduler.

- **Create:** "Remind me to take meds at 8pm daily", "Set alarm for Monday 9am"
- **List:** "What reminders do I have?", "Show my schedule"
- **Edit/Delete:** "Cancel the meds reminder", "Change my morning alarm to 7am"
- **Snooze:** Inline Telegram buttons on reminder notifications (snooze 5/10/30 min or dismiss)
- **Recurrence:** `none`, `daily`, `weekly`, `monthly`

### Budget (`skills/budget/`)

Income/expense tracking with AI-powered categorisation.

- **Log:** "Spent ₱500 on groceries", "Received ₱25,000 salary", "Paid ₱2,000 for utilities"
- **Summaries:** "Budget summary", "How much did I spend this week?", "Show my expenses for March"
- **Limits:** "Set food budget to ₱5,000/month" — warns when approaching or exceeding limits
- **Reports:** Weekly and monthly breakdowns with category totals

The AI auto-categorises transactions into predefined categories. Default currency is Philippine Peso (₱).

### Briefing (`skills/briefing/`)

Compiles and sends a daily morning briefing.

- **Scheduled:** Fires automatically at `DEFAULT_BRIEFING_HOUR` (default: 7:00 AM local time)
- **On-demand:** "Give me my briefing", "Morning update"
- **Contents:** Weather, active reminders for the day, budget snapshot, news headlines, any pending tasks

### Web Browse (`skills/web_browse/`)

Real-time web search and page summarisation.

- **Search:** Uses SerpAPI (100 free/month) to find relevant results
- **Scrape:** BeautifulSoup + httpx to read page content
- **Summarise:** Claude summarises scraped content into a concise answer
- **Triggers:** "Search for...", "What's the latest...", current events, price queries, "Google..."

---

## Telegram Commands

These are optional shortcuts — everything works via natural language.

| Command | Description |
|---------|-------------|
| `/start` | Introduction and feature overview |
| `/help` | List available commands |
| `/status` | Bot health check (AI provider, fallback status, timezone) |

---

## Development Phases

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 1** | Foundation — config, database, AI engine, chat skill, Telegram bot | Complete |
| **Phase 2** | Memory system — memory manager, extractor, intent detector, skill router | Pending |
| **Phase 3** | Reminders — scheduler, reminder skill, inline buttons, snooze/dismiss | Pending |
| **Phase 4** | Budget — transaction logging, summaries, limits, reports | Pending |
| **Phase 5** | Briefing + Web — daily briefing, web search, scraping | Pending |
| **Phase 6** | Voice + Polish — STT/TTS, error handling, rate limiting, tests | Pending |

---

## Deployment

### Railway

The project includes Railway configuration files:

- **`Procfile`** — Defines the worker process: `python -m bot.telegram_bot`
- **`railway.json`** — Build (Nixpacks) and deploy settings with restart-on-failure

**Deploy steps:**

1. Push the repo to GitHub
2. Connect the repo to a Railway project
3. Add all environment variables from `.env.example` in the Railway dashboard
4. Railway will auto-detect the Procfile and deploy as a worker

### Other platforms

The bot runs as a long-polling process (no web server needed). It can run on any platform that supports persistent Python workers:

- **Render:** Use a Background Worker
- **Fly.io:** Use a `[processes]` entry in `fly.toml`
- **VPS:** Run with `systemd` or `supervisord`
- **Docker:** `CMD ["python", "-m", "bot.telegram_bot"]`

---

## Cost & Usage Notes

| Service | Free Tier | Paid |
|---------|-----------|------|
| Claude API | Pay-per-use | ~$3/MTok input, ~$15/MTok output (Sonnet) |
| Groq | 30 req/min, 14,400 req/day | Free tier sufficient for fallback |
| Supabase | 500 MB DB, 2 GB bandwidth | $25/mo Pro |
| SerpAPI | 100 searches/month | $50/mo for 5,000 |
| edge-tts | Unlimited | Free |
| Groq Whisper | Included in Groq free tier | Free |
| Railway | $5 trial credit | $5/mo Hobby |

**Token tracking:** Every AI API call is logged with input/output token counts via loguru. Monitor your logs to track costs.

**Design decisions:**
- Single-user by default, but the schema supports multi-user scaling (every table has `user_id`)
- Async throughout for non-blocking I/O
- Graceful degradation — if Claude fails, Groq takes over automatically
- APScheduler persists jobs so reminders survive bot restarts
