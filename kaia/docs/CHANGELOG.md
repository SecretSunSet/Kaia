# KAIA Changelog

All notable changes to this project are documented here.
Format: timestamped entries per phase, grouped by Added/Changed/Fixed/Notes.

---

## [2026-05-02] Hotfix — Time Awareness

### Added

- `utils/time_utils.py` — three new helpers:
  - `today_in_tz(tz_name)` — calendar date in user's timezone.
  - `format_current_context(tz_name)` — "Current date and time: …" block injected into every LLM call.
  - `format_relative_time(dt, tz_name)` — "yesterday at 3:45 PM" / "3 days ago (Tue, Apr 28)" / "2 months ago (Mar 03, 2026)" formatting.
  - `format_transaction_with_time(tx, tz_name, currency_symbol)` — one-line transaction line with relative timestamp.

### Changed

- `core/ai_engine.py` — `AIEngine.chat()` now auto-prepends a `# Current Time Context` block to the system prompt for every Claude/Groq call. Added optional `user_timezone` parameter (defaults to `settings.default_timezone`). This single chokepoint gives KAIA, every expert, onboarding, and memory extraction full time awareness with no per-call edits.
- `experts/base.py` — `BaseExpert.get_conversation_history()` now prefixes each message with `[<relative time>]` so experts can reason about *when* prior turns happened. Accepts optional `user_timezone`.
- `experts/hevn/expert.py`, `experts/makubex/expert.py`, `experts/placeholder.py` — pass `user.timezone` to `get_conversation_history()`.
- `experts/hevn/expert.py` — `_budget_summary` is now timezone-aware and appends the 5 most recent transactions formatted with relative timestamps so Hevn sees "logged 5 days ago" rather than just totals.
- `bot/telegram_bot.py` — general (non-channel) conversation history loaded for KAIA is also `[relative time]`-prefixed in both the text and voice flows.
- `core/channel_extractor.py`, `skills/memory/prompts.py` — extraction prompts now instruct the model to resolve relative phrases to absolute dates using the injected time context (e.g. store `"2026-04-25"`, never `"yesterday"`).
- `skills/budget/reports.py` — `resolve_period()` and `get_monthly_comparison()` accept `tz` and use `today_in_tz()` instead of UTC `date.today()`.
- `skills/budget/handler.py` — `_handle_summary`, `_handle_comparison`, `_handle_list_limits`, `_check_budget_warning` all use the user's timezone for "today".
- `skills/briefing/handler.py` — daily-brief header now carries the current date (e.g. "🌅 Good morning! Here's your daily briefing — Saturday, May 02, 2026:"); `_get_budget_section` is timezone-aware.

### Fixed

- KAIA no longer assumes the year/date from training-data cutoff. Asking "what year is it?" / "what's today's date?" now returns the live answer.
- Hevn no longer mis-labels week-old expenses as "yesterday" — every transaction in her budget context now carries its actual relative timestamp.
- `[relative time]` prefix on conversation history means experts can correctly answer "what did we discuss earlier this week?" by referencing real prior dates.
- `format_relative_time()` now accepts ISO-string timestamps (Supabase REST returns `created_at` as a string, not a `datetime`) — fixes a regression introduced by the initial hotfix where loading any conversation history crashed with `'str' object has no attribute 'tzinfo'`.
- `experts/hevn/expert.py:_budget_summary` now sorts recent transactions by `transaction_date` only (not the mixed `created_at or transaction_date` key, which would crash if any transaction lacked a `created_at`).

### Notes

- The `users.timezone` column already existed (default `Asia/Manila`); no migration needed.
- Per-expert prompt files (`experts/hevn/prompts.py`, `experts/makubex/prompts.py`) intentionally untouched — the `chat()` chokepoint covers them.
- Out of scope (potential follow-up): the remaining `date.today()` calls inside Hevn skill internals (`budget_coaching.py`, `bills_tracker.py`, `health_assessment.py`, `goals_manager.py`, `proactive.py`, `market_trends.py`) — these are 30/90-day relative windows where UTC vs local-tz drift is negligible. Can be swept in a follow-up if desired.

---

## [2026-04-21] Phase CH-3 — MakubeX Tech Lead

### Added

- `database/migrations/005_makubex.sql` — 4 new tables with indexes and RLS policies: `tech_projects` (JSONB `tech_stack`, priority, status lifecycle), `tech_skills` (UNIQUE per user+skill, level 1–5), `learning_log` (append-only topic/depth entries), `code_reviews` (`snippet_hash` for dedup, JSONB `issues_found`).
- `database/models.py` — Dataclasses `TechProject`, `TechSkill`, `LearningLogEntry`, `CodeReview`.
- `database/queries.py` — CRUD for all 4 MakubeX tables: `create/get/update/delete_tech_project`, `get_tech_project_by_name`, `upsert_tech_skill`, `get_tech_skill(s)`, `add_learning_log`, `get_learning_log`, `get_learning_log_for_topic`, `save_code_review`, `get_code_review_by_hash`, `get_recent_code_reviews`.
- `experts/makubex/` — New expert package:
  - `expert.py` — `MakubeXExpert(BaseExpert)` with `channel_id="makubex"`. First-visit onboarding schedules the Monday-morning tech brief, then intent routing dispatches to 8 specialized skills; fallback is a persona-driven AI reply with full tech context.
  - `prompts.py` — `MAKUBEX_SYSTEM_PROMPT` (systems thinker / hacker mindset / methodical / progressive depth), `ONBOARDING_PROMPT`, `EXTRACTION_PROMPT`, `MAKUBEX_INTENT_PROMPT`, `build_makubex_system_prompt()`.
  - `parser.py` — `classify_makubex_intent()` with keyword short-circuits + AI fallback across 9 intents; fenced code blocks auto-route to `code_review`. Also `parse_project_creation()` and `extract_code_block()`.
  - `extractor.py` — `makubex_extract_and_save()` runs the generic channel extractor, then mirrors high-signal categories (`tech_stack`, `skills`, `projects`, `work_context`, `infrastructure`) to the shared `user_profile` under `technical`.
  - `skills/code_review.py` — `CodeReviewSkill` with SHA-256 snippet dedup via `code_reviews`, heuristic language detection (python/js/ts/go/rust/java/sql/bash/html/yaml), severity-sorted formatter.
  - `skills/architecture.py` — `ArchitectureSkill`: `design_system`, `review_schema`, `design_api`, `compare_approaches`.
  - `skills/debugging.py` — `DebuggingSkill`: `debug_error`, `explain_stack_trace`, `suggest_debugging_steps`, `diagnose_performance`.
  - `skills/tech_research.py` — `TechResearchSkill`: `compare_tools`, `recommend_tool`, `latest_on_topic`, `evaluate_trend`. Pulls fresh context via `skills.web_browse.search.web_search`.
  - `skills/devops.py` — `DevOpsSkill`: `review_infrastructure`, `design_cicd`, `monitoring_setup`, `containerization_advice`, `scaling_advice`.
  - `skills/security.py` — `SecuritySkill`: `audit_project`, `review_auth_flow`, `check_api_security`, `secrets_best_practices`, `dependency_audit` (web-search-augmented).
  - `skills/learning_coach.py` — `LearningCoachSkill` with `SKILL_TREES` for python/web_dev/devops/databases/security, depth progression (intro → solid → deep), `assess_level`, `explain_concept`, `suggest_next_topic`, `create_study_plan`, `quiz`.
  - `skills/project_manager.py` — `ProjectManagerSkill`: idempotent-by-name `create_project`, `list_projects`, `update_project`, `project_summary`, `suggest_next_step`.
  - `skills/proactive.py` — `MakubexProactiveSkill.generate_weekly_brief()` assembles active projects, this-week learning, recent code reviews, next-topic suggestion, web-sourced security advisories, and a rotating weekly tip.
- `bot/makubex_commands.py` — Slash-command shortcuts: `/makubex_review`, `/makubex_projects`, `/makubex_learn`, `/makubex_security`, `/makubex_brief`. Forum-topic-aware replies.
- `core/scheduler.py` — `schedule_makubex_weekly_brief()`, `cancel_makubex_weekly_brief()`, `_fire_makubex_brief()` (Monday 08:00 user timezone). Forum-mode delivery routes to MakubeX's topic when mapped.

### Changed

- `config/constants.py` — Added `"technical"` to `PROFILE_CATEGORIES` so MakubeX can mirror technical facts to the shared user profile.
- `experts/__init__.py` — Registered `MakubeXExpert` for `CHANNEL_MAKUBEX`; placeholder now only backs Kazuki and Akabane.
- `bot/commands.py` — `/reset` now also purges `tech_projects`, `tech_skills`, `learning_log`, `code_reviews`.
- `bot/telegram_bot.py` — Registered the 5 `/makubex_*` commands and added a MakubeX shortcuts block to `/help`.

### Notes

- Personality: MakubeX is a systems thinker with a hacker mindset — methodical, opinionated, never gatekeeping knowledge, explains at the user's current level.
- Memory mirror is selective: only structural technical facts (stack/skills/projects/work context/infrastructure) propagate to the shared profile; the rest stays channel-scoped.
- Code reviews dedupe on a SHA-256 of the normalized snippet so repeat pastes don't burn tokens.
- Weekly brief fires Mondays at 08:00 in the user's timezone (contrast with Hevn's Sunday 09:00 digest). Registration happens on first visit to `/makubex`, mirroring Hevn's digest.

---

## [2026-04-15] Deployment — AWS EC2

### Added

- `Dockerfile` — Python 3.11-slim base with ffmpeg for voice processing. Exposes port 8000.
- `.dockerignore` — excludes secrets, caches, tests, docs, deploy scripts from image.
- `deploy/setup-server.sh` — one-time bootstrap script for fresh Ubuntu 24.04 EC2 instance (installs python, ffmpeg, creates /opt/kaia, venv).
- `deploy/kaia.service` — systemd unit for auto-start/auto-restart. Runs as `ubuntu` user, reads `/opt/kaia/app/.env`, MemoryMax=1G, CPUQuota=80%, Restart=always with 10s delay.
- `deploy/update.sh` — manual pull/restart script on the server.
- `.github/workflows/deploy.yml` — GitHub Actions auto-deploy on push to `main` via SSH (appleboy/ssh-action). Requires secrets `SERVER_HOST` and `SSH_PRIVATE_KEY`.
- `requirements.txt` — added `aiohttp>=3.9.0` for future health-check endpoint / monitoring hooks.

### Changed

- `.gitignore` — consolidated at repo root. Now excludes `*.pem`, `deploy/kaia-key.pem`, `*.ogg`, `*.mp3`, `/tmp/kaia_tts/`, plus the existing venv/__pycache__/secrets patterns.

### Notes

- Target: AWS EC2 t4g.small (ARM, 2 vCPU, 2GB RAM, Ubuntu 24.04) at `3.106.134.24`.
- SSH: `ubuntu@3.106.134.24` with `kaia-key.pem`.
- Deploy flow: push to `main` → GitHub Actions SSHes in → `git pull` → `pip install` → `systemctl restart kaia`.
- systemd writes logs to journal: `journalctl -u kaia -f` to tail.

---

## [2026-04-13] Phase 6 — Voice Interface + Polish

### Added

- `utils/voice_stt.py` — `transcribe_voice()` using Groq Whisper API (`whisper-large-v3-turbo`). Accepts .ogg voice notes directly, 30s timeout. Returns transcribed text or None.
- `utils/voice_tts.py` — `text_to_speech()` using edge-tts (Microsoft, free). Generates .mp3 to temp dir. `cleanup_old_files()` removes stale files >1hr. `safe_delete()` helper.
- `utils/validators.py` — `sanitize_message()`, `is_valid_amount()`, `validate_timezone()`, `validate_currency()` — input validation utilities.
- `utils/formatters.py` — `escape_markdown()`, `format_currency()`, `format_datetime()`, `truncate()` — Telegram formatting helpers. Truncation ensures messages stay under 4096 char limit.
- `bot/commands.py` — Extended command handlers: `cmd_status_extended()` with full user stats from DB, `cmd_export()` exports all user data as JSON document, `cmd_reset()` with `CONFIRM DELETE` safety flow.
- `bot/middleware.py` — `check_rate_limit()` (20 msgs/min per user), `track_ai_usage()` token/cost tracking, `get_session_stats()`.

### Changed

- `bot/telegram_bot.py` — Major rewrite:
  - Added `handle_voice()` — downloads voice file, transcribes via Groq Whisper, processes through skill pipeline, optionally replies with TTS audio.
  - Integrated rate limiting (`check_rate_limit`) before every message/voice handler.
  - All responses truncated via `truncate()` before sending.
  - AI token usage tracked via `track_ai_usage()` after every skill response.
  - `/status` now uses `cmd_status_extended` with full DB stats.
  - Added `/export` and `/reset` command handlers.
  - `/start` and `/help` messages rewritten with full feature list including voice.
  - Voice handler registered: `filters.VOICE | filters.AUDIO`.
  - Reset confirmation handled inline in `handle_message()`.
  - TTS cleanup on startup via `cleanup_old_files()`.
  - Enhanced error handler with exc_info logging.

### Notes

- Voice transcription requires `GROQ_API_KEY` (Groq Whisper is free). Without it, voice messages get a "not available" response.
- TTS uses edge-tts which is completely free (Microsoft Edge voices). No API key needed.
- Voice reply preference is read from user profile (`voice_replies: true`). Users say "reply with voice" to enable.
- Rate limit is 20 messages per 60-second window per user. Prevents accidental API cost spikes.
- `/reset` requires typing exact "CONFIRM DELETE" within 2 minutes. Deletes all data across all tables.
- `/export` sends a JSON file via Telegram document attachment with profile, reminders, transactions, and recent conversations.

---

## [2026-04-12] Phase 5 — Daily Briefing & Web Browse

### Added

- `skills/web_browse/search.py` — `web_search()` (SerpAPI), `news_search()` (NewsAPI), `get_weather()` (OpenWeatherMap). All use `httpx.AsyncClient` with configurable timeout. Each function degrades gracefully if its API key is missing.
- `skills/web_browse/scraper.py` — `scrape_page()` fetches and extracts main text content from a URL using BeautifulSoup. `extract_article()` extracts title + body. Strips scripts/styles/nav, truncates to `WEB_SCRAPE_MAX_CHARS`.
- `skills/web_browse/prompts.py` — Prompt builders: `build_search_summary_prompt()`, `build_page_summary_prompt()`, `build_news_summary_prompt()`, `build_search_decision_prompt()`. `format_search_results()` for AI prompt injection.
- `skills/web_browse/handler.py` — `WebBrowseSkill` with sub-intent routing: weather queries, news queries, and general web search. AI-optimized search queries. Handles missing API keys gracefully.
- `skills/briefing/prompts.py` — `build_motivational_note_prompt()` for personalized morning note, `build_briefing_time_parse_prompt()` for time change requests.
- `skills/briefing/handler.py` — `BriefingSkill` with `generate_briefing()` that compiles weather, reminders, budget snapshot, and motivational note via `asyncio.gather()`. Handles briefing time changes and enable/disable. All sections degrade gracefully.
- `core/scheduler.py` — Added `schedule_daily_briefing()`, `cancel_daily_briefing()`, `_fire_briefing()`, `_schedule_briefings_for_all_users()`. CronTrigger-based daily scheduling in user's local timezone. Briefings auto-schedule for all allowed users on startup.
- `config/settings.py` — Added `default_location`, `briefing_time`, `briefing_enabled` settings.
- `config/constants.py` — Added `BRIEFING_DEFAULT_TIME`, `DEFAULT_WEATHER_LOCATION`, `WEB_SEARCH_MAX_RESULTS`, `WEB_SCRAPE_MAX_CHARS`, `WEB_REQUEST_TIMEOUT`.

### Changed

- `core/skill_router.py` — Registered `BriefingSkill` and `WebBrowseSkill` in the skill registry. All 6 skills now implemented.
- `core/intent_detector.py` — Enhanced web_browse rules (weather, news, look up patterns) and briefing rules (time change, enable/disable).
- `bot/telegram_bot.py` — Added `/briefing` command handler for on-demand briefing. Updated `/help` to include `/briefing`. Imports `BriefingSkill`.

### Notes

- All three external APIs (SerpAPI, NewsAPI, OpenWeatherMap) are optional. If keys are not configured, those features are unavailable but the bot continues working without them.
- Daily briefing uses `asyncio.gather()` to fetch all sections in parallel — compiles in ~2-3 seconds.
- Briefing auto-schedules on startup for all users in `ALLOWED_TELEGRAM_IDS`. Default time is 07:00 in user's timezone.
- Web search uses AI to optimize the search query before calling SerpAPI.
- Page scraping is available but not used by default — search snippets are usually sufficient.

---

## [2026-04-12] Phase 4 — Budget Tracker

### Added

- `skills/budget/prompts.py` — Prompt builders: `build_parse_prompt()` for NLP transaction parsing, `build_summary_prompt()` for AI-generated summaries, `build_budget_limit_parse_prompt()` for limit setting, `format_transaction_confirmation()` and `format_budget_warning()` for display.
- `skills/budget/parser.py` — `parse_transaction()` sends natural language to Claude, returns structured `{amount, type, category, description, date}`. `parse_budget_limit()` parses budget limit requests. Handles currency symbols, commas, relative dates.
- `skills/budget/reports.py` — `get_period_summary()` aggregates income/expenses/categories, `get_monthly_comparison()` compares current vs last month, `format_summary_message()` / `format_comparison_message()` / `format_budget_limits_message()` for Telegram display, `resolve_period()` maps natural language time periods to date ranges.
- `skills/budget/handler.py` — `BudgetSkill` with sub-intent detection: log transaction (parse + save + budget warning), summary (period resolve + aggregate + format), comparison (month-over-month), set/list/delete budget limits, undo last transaction.
- `database/queries.py` — 13 new budget query functions: `create_transaction()`, `get_transactions()`, `get_category_total()`, `get_spending_by_category()`, `get_income_total()`, `get_expense_total()`, `get_last_transaction()`, `delete_transaction()`, `create_or_update_budget_limit()`, `get_budget_limits()`, `get_budget_limit()`, `deactivate_budget_limit()`, plus `_row_to_transaction()` and `_row_to_budget_limit()` helpers.
- `config/constants.py` — Added `BUDGET_CATEGORIES` (14 categories), `BUDGET_CATEGORY_EMOJIS` (emoji per category), `BUDGET_WARNING_THRESHOLD` (0.8 = 80%).

### Changed

- `core/skill_router.py` — Registered `BudgetSkill` in the skill registry.
- `core/intent_detector.py` — Added edge case rules for budget classification: plain numbers alone are NOT budget, need financial context; added budget limit and undo patterns.

### Notes

- Claude handles all transaction parsing — no regex needed. Natural language like "lunch 250", "spent ₱500 on groceries", "received 30k salary" all work.
- Budget warnings are proactive: every expense is checked against its category limit after logging.
- Summaries are structured (not AI-generated) for consistency. Category breakdown with emoji indicators and budget limit status.
- Undo feature deletes the most recent transaction. No full edit capability yet (Phase 6 polish).
- All amounts stored as plain DECIMAL in DB. Currency symbol added on display only.

---

## [2026-04-12] Phase 3 — Reminders System

### Added

- `utils/time_utils.py` — Timezone utilities: `now_utc()`, `now_in_tz()`, `to_utc()`, `to_local()`, `format_local()`, `next_occurrence()` (daily/weekly/monthly via `dateutil.relativedelta`).
- `skills/reminders/prompts.py` — Prompt builders: `build_parse_prompt()` for NLP parsing, `format_confirmation()`, `format_reminder_list()`, `format_fire_message()` for Telegram display.
- `skills/reminders/parser.py` — `parse_reminder()` sends natural language to Claude, returns structured `{title, datetime_utc, recurrence}`. Handles absolute times, relative times ("in 30 minutes"), and recurrence patterns.
- `core/scheduler.py` — Full APScheduler integration: `AsyncIOScheduler` singleton, `start_scheduler()` / `shutdown_scheduler()` lifecycle, `schedule_reminder()` / `cancel_reminder()` / `reschedule_reminder()` job management, `handle_snooze()` / `handle_dismiss()` for inline button actions, `load_all_reminders()` on startup to restore from DB, `_fire_reminder()` sends Telegram message with inline snooze/dismiss buttons, recurring reminders auto-schedule next occurrence.
- `skills/reminders/handler.py` — `RemindersSkill` with sub-intent detection: create (parse + save + schedule), list (query DB + format), cancel (fuzzy title match or index-based). `set_bot()` stores bot reference for scheduler use.
- `database/queries.py` — 7 new reminder query functions: `create_reminder()`, `get_active_reminders()`, `get_all_active_reminders()` (with JOIN for telegram_id), `get_reminder_by_id()`, `update_reminder()`, `deactivate_reminder()`, `get_user_for_reminder()`.

### Changed

- `core/skill_router.py` — Registered `RemindersSkill` in the skill registry.
- `bot/telegram_bot.py` — Added `CallbackQueryHandler` for snooze/dismiss buttons, `post_init()` callback to start scheduler and store bot reference, `post_shutdown()` for graceful scheduler shutdown, updated `/start` message to include reminders.
- `requirements.txt` — Added `python-dateutil>=2.8.0`.

### Notes

- Scheduler manages persistence ourselves (not APScheduler's built-in job stores). All reminders stored in our `reminders` table, loaded into scheduler on startup.
- All times stored in UTC in DB, converted to user timezone only for display.
- Missed one-time reminders (past fire time on startup) are deactivated. Missed recurring reminders are advanced to next future occurrence.
- Snooze increments `snooze_count` in DB for future smart adaptation (Phase 6).
- The `handle_dismiss()` function has a limitation: for recurring reminders, it can't re-add the scheduler job after dismiss because the bot reference isn't easily accessible. The next bot restart will pick it up via `load_all_reminders()`.

---

## [2026-04-08] Bugfix — SQL Migration Policy Syntax

### Fixed

- `database/migrations/001_initial.sql` — `CREATE POLICY IF NOT EXISTS` is not valid PostgreSQL syntax. Replaced with `DROP POLICY IF EXISTS` + `CREATE POLICY` to make the script idempotent.

---

## [2026-04-08] Phase 2 — Memory System, Intent Detection & Skill Routing

### Added

- `skills/memory/prompts.py` — Three prompt builders: `build_extraction_prompt()` for background fact extraction, `build_memory_query_prompt()` for profile queries, `build_memory_store_prompt()` for explicit "remember that..." with `<memory>` tag parsing.
- `skills/memory/extractor.py` — `extract_and_save()` — background pipeline that sends recent conversation to Claude, parses returned JSON array of facts, and upserts them into `user_profile` + `memory_log`. Handles malformed JSON gracefully.
- `skills/memory/handler.py` — `MemorySkill` — handles two flows: store requests ("remember that...") with `<memory>` tag extraction, and query requests ("what do you know about me?"). Includes `_is_store_request()` heuristic and `_extract_memory_tags()` parser.
- `core/memory_manager.py` — `MemoryManager` class centralising profile operations. `load_profile_context()` loads and formats profile for system prompt. `run_background_extraction()` fires an asyncio task after each conversation to extract facts without blocking the user response.
- `core/intent_detector.py` — `IntentDetector` class that sends messages to Claude with a classification prompt. Returns `IntentResult(skill, confidence)`. Falls back to `chat` if confidence < threshold (default 0.6) or on any error. Robust JSON parsing handles wrapped responses.
- `core/skill_router.py` — `SkillRouter` class that holds all skill instances, uses `IntentDetector` to classify messages, and dispatches to the matched handler. Unimplemented skills fall back to chat gracefully.

### Changed

- `bot/telegram_bot.py` — Replaced hardcoded `ChatSkill` with `SkillRouter` for intent-based dispatch. Added `MemoryManager` for profile loading and background extraction. Profile formatting moved from `_format_profile()` local helper to `MemoryManager.load_profile_context()`. After each response, background memory extraction runs as a fire-and-forget asyncio task.

### Notes

- Intent detection adds one extra AI call per message (with `max_tokens=64` for minimal cost). The classification prompt is designed to return a compact JSON object.
- Background memory extraction runs asynchronously — it doesn't delay the user's response. Failures are logged but don't affect the conversation.
- The `MemorySkill` store flow uses `<memory>` XML tags in the AI response to separate machine-readable facts from the user-facing reply. Tags are stripped before sending.
- `SkillRouter` currently registers `chat` and `memory` skills. Slots for `reminders`, `budget`, `briefing`, and `web_browse` are ready for Phase 3+.

---

## [2026-04-08] Phase 1 — Foundation

### Added

- `config/settings.py` — Pydantic settings class loading all env vars with typed defaults. Supports `.env` file and environment variable override.
- `config/constants.py` — App-wide constants: skill IDs (`chat`, `memory`, `reminders`, `budget`, `briefing`, `web_browse`), expense/income categories, profile categories, recurrence options, fact types, currency symbols, message limits.
- `database/migrations/001_initial.sql` — Full PostgreSQL schema: 7 tables (`users`, `user_profile`, `memory_log`, `reminders`, `transactions`, `conversations`, `budget_limits`), indexes on all foreign keys and common query patterns, RLS policies for Supabase.
- `database/connection.py` — Singleton Supabase client factory via `get_supabase()`.
- `database/models.py` — Python dataclass models mirroring all 7 database tables: `User`, `ProfileEntry`, `MemoryLogEntry`, `Reminder`, `Transaction`, `Conversation`, `BudgetLimit`.
- `database/queries.py` — Reusable async query functions: `get_or_create_user()`, `get_user_profile()`, `upsert_profile_entry()`, `save_conversation()`, `get_recent_conversations()`, `add_memory_log()`.
- `core/ai_engine.py` — `AIEngine` class wrapping Claude (primary) and Groq (fallback) behind a unified `chat()` method. Returns `AIResponse` dataclass with text, provider, model, and token counts. `build_message_history()` helper for conversation formatting.
- `skills/base.py` — `BaseSkill` abstract class defining the skill contract: `handle(user, message, conversation_history, profile_context) -> SkillResult`. `SkillResult` dataclass wraps response text, skill name, and optional AI metadata.
- `skills/chat/prompts.py` — `build_chat_system_prompt(profile_context)` — builds the KAIA persona system prompt with user profile injection.
- `skills/chat/handler.py` — `ChatSkill` — general Q&A handler. Builds system prompt, assembles message history, calls AI engine, returns result.
- `bot/telegram_bot.py` — Main entry point. Handlers for `/start`, `/help`, `/status` commands. Text message handler: loads user from DB, fetches profile + conversation history, routes to chat skill, saves conversation, replies. Includes access control via `ALLOWED_TELEGRAM_IDS`, typing indicators, and error handling.
- `.env.example` — Template for all environment variables with grouping and comments.
- `requirements.txt` — All 13 Python dependencies with minimum versions.
- `Procfile` — Railway worker process definition.
- `railway.json` — Railway deployment config (Nixpacks builder, restart on failure).
- `README.md` — Full project documentation covering features, architecture, setup, config, schema, core systems, skills, deployment, and costs.

### Notes

- All handlers are async (python-telegram-bot v20 requirement).
- In Phase 1, all messages route directly to the chat skill. Intent detection and skill routing come in Phase 2.
- Supabase client is synchronous (the `supabase-py` library wraps REST calls); query functions are marked `async` for future compatibility and to match the async handler contract.
- Groq fallback is only activated if `GROQ_API_KEY` is provided. Without it, Claude failures will raise `RuntimeError`.
