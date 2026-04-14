# KAIA Development Status

**Last updated:** 2026-04-13
**Current phase:** All phases complete — v1.0
**Overall progress:** 100% (Phases 1–6 of 6)

---

## Phase Overview

| Phase | Name | Progress | Status |
|-------|------|----------|--------|
| 1 | Foundation | 100% | ✅ Complete |
| 2 | Memory System | 100% | ✅ Complete |
| 3 | Reminders | 100% | ✅ Complete |
| 4 | Budget | 100% | ✅ Complete |
| 5 | Briefing + Web Browse | 100% | ✅ Complete |
| 6 | Voice + Polish | 100% | ✅ Complete |

---

## Phase 1 — Foundation ✅

**Status:** Complete
**Date completed:** 2026-04-08

### What's done

- [x] `config/settings.py` — Pydantic settings with all env vars
- [x] `config/constants.py` — All constants (skills, categories, limits)
- [x] `database/migrations/001_initial.sql` — Full 7-table schema with indexes and RLS
- [x] `database/connection.py` — Supabase singleton client
- [x] `database/models.py` — Dataclass models for all tables
- [x] `database/queries.py` — Core query functions (user, profile, conversation, memory)
- [x] `core/ai_engine.py` — Claude + Groq fallback with token tracking
- [x] `skills/base.py` — Abstract base class + SkillResult
- [x] `skills/chat/handler.py` — Chat skill handler
- [x] `skills/chat/prompts.py` — Chat system prompt builder
- [x] `bot/telegram_bot.py` — Full entry point with commands and message handling
- [x] `.env.example`, `requirements.txt`, `Procfile`, `railway.json`
- [x] `README.md` — Full project documentation
- [x] `docs/` — All 8 documentation files

---

## Phase 2 — Memory System ✅

**Status:** Complete
**Date completed:** 2026-04-08

### What's done

- [x] `skills/memory/prompts.py` — Three prompt builders: extraction, query, and store
- [x] `skills/memory/extractor.py` — Background extraction pipeline: conversation → Claude → JSON facts → DB upsert
- [x] `skills/memory/handler.py` — `MemorySkill` with store flow (explicit "remember that...") and query flow ("what do you know about me?")
- [x] `core/memory_manager.py` — `MemoryManager` centralising profile loading/formatting and fire-and-forget background extraction
- [x] `core/intent_detector.py` — `IntentDetector` using Claude to classify messages → skill + confidence
- [x] `core/skill_router.py` — `SkillRouter` managing skill registry and intent-based dispatch
- [x] `bot/telegram_bot.py` — Updated to use `SkillRouter` + `MemoryManager` instead of hardcoded chat. Background extraction runs after every message.

### How to test

- Send messages → verify intent detection routes to correct skill in logs
- Say "Remember that I'm allergic to shrimp" → check `user_profile` table for explicit entry
- Ask "What do you know about me?" → get profile summary
- Have a few conversations → check `user_profile` for inferred facts and `memory_log` for extraction history

---

## Phase 3 — Reminders ✅

**Status:** Complete
**Date completed:** 2026-04-12

### What's done

- [x] `utils/time_utils.py` — Timezone utilities: `now_utc()`, `now_in_tz()`, `to_utc()`, `to_local()`, `format_local()`, `next_occurrence()`
- [x] `skills/reminders/prompts.py` — Prompt builders: NLP parsing, confirmation, list formatting, fire message
- [x] `skills/reminders/parser.py` — `parse_reminder()` NLP parsing via Claude: natural language → structured `{title, datetime_utc, recurrence}`
- [x] `core/scheduler.py` — Full APScheduler integration: singleton scheduler, job CRUD, snooze/dismiss handlers, startup restore from DB, recurring reminder advancement
- [x] `skills/reminders/handler.py` — `RemindersSkill` with sub-intent detection: create, list, cancel flows
- [x] `database/queries.py` — 7 new reminder query functions: create, get active, get all active (JOIN), get by ID, update, deactivate, get user for reminder
- [x] `core/skill_router.py` — Registered `RemindersSkill` in skill registry
- [x] `bot/telegram_bot.py` — `CallbackQueryHandler` for inline buttons, `post_init`/`post_shutdown` lifecycle hooks for scheduler, snooze/dismiss button handling
- [x] `requirements.txt` — Added `python-dateutil>=2.8.0`
- [x] Inline Telegram buttons: snooze (5m/15m/1hr) + dismiss on reminder fire

### How to test

- Say "Remind me to take meds at 8pm" → verify confirmation message with title, time, recurrence
- Say "What reminders do I have?" → see numbered list of active reminders
- Say "Cancel the meds reminder" → fuzzy match and deactivate
- Wait for a reminder to fire → verify inline snooze/dismiss buttons work
- Test recurring: "Remind me to exercise every day at 7am" → verify next occurrence scheduling after dismiss

---

## Phase 4 — Budget Tracker ✅

**Status:** Complete
**Date completed:** 2026-04-12

### What's done

- [x] `skills/budget/prompts.py` — Prompt builders: transaction parsing, summary generation, budget limit parsing, confirmation/warning formatters
- [x] `skills/budget/parser.py` — `parse_transaction()` and `parse_budget_limit()` NLP parsing via Claude
- [x] `skills/budget/reports.py` — `get_period_summary()`, `get_monthly_comparison()`, `resolve_period()`, all message formatters
- [x] `skills/budget/handler.py` — `BudgetSkill` with 7 sub-intents: log, summary, comparison, set/list/delete limits, undo
- [x] `database/queries.py` — 13 new budget query functions (transactions CRUD, category aggregation, budget limits CRUD)
- [x] `config/constants.py` — `BUDGET_CATEGORIES`, `BUDGET_CATEGORY_EMOJIS`, `BUDGET_WARNING_THRESHOLD`
- [x] `core/skill_router.py` — Registered `BudgetSkill` in skill registry
- [x] `core/intent_detector.py` — Added budget edge case rules (plain numbers ≠ budget, need financial context)

### How to test

- Log expense: "Spent ₱500 on groceries" → verify confirmation, check `transactions` table
- Log income: "Received ₱30,000 salary" → verify income type
- Quick log: "Lunch 250" → should parse as expense, food, ₱250
- Summary: "How much did I spend this month?" → category breakdown with emojis
- Set budget: "Set food budget to ₱5,000 per month" → verify in `budget_limits` table
- Budget warning: Log food expenses until near ₱5,000 → verify warning appears
- Comparison: "How does this month compare to last month?" → month-over-month
- List limits: "What are my budget limits?" → show all active limits with spending
- Undo: "Undo last transaction" → deletes most recent entry
- Edge case: "I need 30 minutes" → should NOT be parsed as a transaction

---

## Phase 5 — Briefing + Web Browse ✅

**Status:** Complete
**Date completed:** 2026-04-12

### What's done

- [x] `skills/web_browse/search.py` — `web_search()` (SerpAPI), `news_search()` (NewsAPI), `get_weather()` (OpenWeatherMap) with httpx.AsyncClient
- [x] `skills/web_browse/scraper.py` — `scrape_page()` and `extract_article()` using BeautifulSoup
- [x] `skills/web_browse/prompts.py` — Search/news/page summary prompts, search decision prompt, result formatter
- [x] `skills/web_browse/handler.py` — `WebBrowseSkill` with weather, news, and search sub-intents
- [x] `skills/briefing/prompts.py` — Motivational note prompt, briefing time parse prompt
- [x] `skills/briefing/handler.py` — `BriefingSkill` with `generate_briefing()` (parallel data gathering), time change, enable/disable
- [x] `core/scheduler.py` — `schedule_daily_briefing()`, `cancel_daily_briefing()`, auto-schedule on startup via CronTrigger
- [x] `bot/telegram_bot.py` — `/briefing` command, updated `/help`
- [x] `config/settings.py` — `default_location`, `briefing_time`, `briefing_enabled` settings
- [x] `config/constants.py` — `BRIEFING_DEFAULT_TIME`, `DEFAULT_WEATHER_LOCATION`, `WEB_SEARCH_MAX_RESULTS`, `WEB_SCRAPE_MAX_CHARS`, `WEB_REQUEST_TIMEOUT`
- [x] `core/skill_router.py` — Registered both `BriefingSkill` and `WebBrowseSkill`. All 6 skills now active.

### How to test

- "What's the weather in Manila?" → current weather display
- "Latest news on AI" → news search and summary (requires NEWS_API_KEY)
- "Search for best coffee shops in Makati" → web search (requires SERPAPI_KEY)
- "Give me my briefing" or `/briefing` → full daily briefing with all available sections
- "Change briefing to 6:30am" → verify schedule updates
- "Turn off daily briefing" → verify it stops
- Missing API keys → graceful "not configured" messages, never crashes

---

## Phase 6 — Voice + Polish ✅

**Status:** Complete
**Date completed:** 2026-04-13

### What's done

- [x] `utils/voice_stt.py` — Groq Whisper transcription (`whisper-large-v3-turbo`), 30s timeout, graceful degradation
- [x] `utils/voice_tts.py` — edge-tts audio generation (free), temp file management, cleanup utility
- [x] `utils/validators.py` — Input sanitization, amount/timezone/currency validation
- [x] `utils/formatters.py` — Telegram markdown escaping, currency formatting, datetime formatting, message truncation
- [x] `bot/commands.py` — Enhanced `/status` with DB stats, `/export` data export as JSON, `/reset` with confirmation flow
- [x] `bot/middleware.py` — Rate limiting (20 msg/min), AI token/cost tracking
- [x] `bot/telegram_bot.py` — Voice message handler, rate limiting integration, response truncation, AI usage tracking, updated `/start` and `/help`, registered `/export` + `/reset` + voice handler
- [x] All responses truncated to Telegram's 4096 char limit
- [x] Global error handler with exc_info logging

### How to test

- Send a voice note → transcribed and processed through skill pipeline
- "Reply with voice" → set preference, next voice message gets audio reply
- /status → full stats: profile facts, reminders, transactions, conversations, AI costs
- /export → receive JSON file with all data
- /reset → CONFIRM DELETE → data wiped
- Spam 25 messages quickly → rate limit kicks in
- Send a very long question → response is properly truncated

---

## Known Issues

- Supabase-py client is synchronous — query functions are declared `async` but don't truly await I/O. Not a problem for single-user load. Consider `asyncpg` if scaling is needed.
- No virtual environment created yet on the dev machine (requires `python3-venv` package install with sudo). Dependencies installed with `--break-system-packages` for now.
- Intent detection adds one extra AI call per message (~64 output tokens). Minimal cost but doubles API calls. Consider caching or keyword-based pre-filtering for common patterns.
- Background memory extraction errors are silently logged — no retry mechanism. A failed extraction means facts from that conversation may be lost.
- Voice transcription requires Groq API key — without it, voice messages get a "not available" response. No fallback STT provider.
- Rate limiter state is in-memory only — resets on bot restart. Not an issue for single-instance deployment.
- Session AI cost tracking is in-memory — resets on restart. For persistent cost tracking, consider writing to DB.
- `/reset` deletes data from all child tables but does not delete the `users` row itself. User record persists for re-use.

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-08 | Use dataclasses over SQLAlchemy ORM | Lightweight, Supabase REST handles serialisation |
| 2026-04-08 | Polling over webhooks | Simpler deployment, no public URL needed |
| 2026-04-08 | Profile injection over RAG | Profile is small enough for system prompt |
| 2026-04-08 | Fire-and-forget asyncio task for extraction | Don't block user response; failed extractions are acceptable |
| 2026-04-08 | `<memory>` XML tags for structured data in AI response | Clean separation of machine-parseable facts from user-facing text |
| 2026-04-08 | Heuristic `_is_store_request()` before AI classification | Avoids burning an extraction call when we can cheaply detect "remember that..." patterns |
| 2026-04-08 | 64-token max for intent detection | Keeps classification fast and cheap — only need `{"skill":"x","confidence":0.9}` |
| 2026-04-12 | Own persistence over APScheduler job stores | All reminders stored in our `reminders` table, loaded into scheduler on startup. Gives us full control over state and portability |
| 2026-04-12 | UTC storage, local display for reminders | Store all times in UTC in DB, convert to user timezone only for display. Avoids DST ambiguity |
| 2026-04-12 | NLP parsing via Claude over regex | Natural language time parsing ("in 30 minutes", "tomorrow evening", "every Monday") handled by Claude rather than brittle regex patterns |
| 2026-04-12 | Claude for transaction parsing | Natural language financial inputs ("lunch 250", "spent ₱500 on groceries") parsed by Claude, not regex. Handles currency symbols, commas, categories |
| 2026-04-12 | Proactive budget warnings | Check category limit on every expense log, warn at 80% and alert when over — don't wait for user to ask |
| 2026-04-12 | Structured summaries over AI-generated | Budget summaries built from DB aggregates directly, not AI paraphrasing. Consistent format, faster, cheaper |
| 2026-04-12 | asyncio.gather for briefing sections | Fetch weather, reminders, budget, and AI note in parallel — briefing compiles in 2-3s instead of 10+ |
| 2026-04-12 | All external APIs optional | SerpAPI, NewsAPI, OpenWeatherMap each degrade gracefully. Bot works with zero, one, or all configured |
| 2026-04-12 | Template-first briefing, AI-enhanced | Structured format with emojis for scannability. Only motivational note uses Claude — keeps it fast and cheap |
| 2026-04-12 | CronTrigger for daily briefing | APScheduler CronTrigger in user's local timezone, auto-scheduled on startup for all allowed users |
| 2026-04-13 | Groq Whisper for STT over OpenAI Whisper | Free tier (30 req/min), same Whisper model, already have Groq client for AI fallback |
| 2026-04-13 | edge-tts over Google/ElevenLabs TTS | Completely free (Microsoft Edge voices), no API key needed, good quality |
| 2026-04-13 | In-memory rate limiter over DB-backed | Single-instance bot, no need for distributed rate limiting. 20 msg/min per user prevents API cost spikes |
| 2026-04-13 | Profile-based voice reply preference | User says "reply with voice" → stored in profile → checked on each voice message. No global flag needed |
| 2026-04-13 | CONFIRM DELETE safety flow for /reset | Irreversible data deletion requires exact text match within 2-minute window. Prevents accidental data loss |

---

## v1.0 — Feature Summary

All 6 phases complete. Every planned feature is implemented and functional.

### Core Features

- **Chat & Q&A** — General conversation with Claude, Groq fallback, user profile personalisation
- **Memory System** — Background fact extraction, explicit "remember that..." storage, profile queries
- **Intent Detection** — AI-powered message classification routes to correct skill automatically
- **Skill Router** — Modular dispatch to 6 skill handlers based on intent

### Skills

- **Reminders** — NLP time parsing, one-time and recurring (daily/weekly/monthly), inline snooze/dismiss buttons, APScheduler persistence
- **Budget Tracker** — NLP transaction parsing, 14 categories with auto-detection, budget limits with proactive warnings, period summaries, month-over-month comparison, undo
- **Daily Briefing** — Parallel-compiled morning summary (weather, reminders, budget snapshot, motivational note), auto-scheduled via CronTrigger, configurable time
- **Web Browse** — SerpAPI web search, NewsAPI news search, OpenWeatherMap weather, AI-summarised results

### Voice

- **Speech-to-Text** — Groq Whisper transcription of voice messages, processes through full skill pipeline
- **Text-to-Speech** — edge-tts audio replies when user preference is enabled

### Polish

- **Rate Limiting** — 20 messages/minute per user
- **Input Validation** — Message sanitisation, amount/timezone/currency validation
- **Telegram Formatting** — Markdown escaping, currency formatting, datetime display, message truncation (4096 char limit)
- **Enhanced /status** — Full DB stats (profile facts, reminders, transactions, conversations, AI costs)
- **Data Export** — `/export` sends complete user data as JSON file
- **Data Reset** — `/reset` with CONFIRM DELETE safety flow
- **Error Handling** — Global error handler with structured logging, graceful degradation throughout
