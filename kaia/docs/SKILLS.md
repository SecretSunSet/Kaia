# KAIA Skills Reference

Skills are modular handlers that process user messages. Each skill extends `BaseSkill` and implements an async `handle()` method.

---

## Skill Registry

| Skill ID | Name | Directory | Status | Phase |
|----------|------|-----------|--------|-------|
| `chat` | Chat / Q&A | `skills/chat/` | ✅ Implemented | 1 |
| `memory` | Memory & Learning | `skills/memory/` | ✅ Implemented | 2 |
| `reminders` | Reminders | `skills/reminders/` | ✅ Implemented | 3 |
| `budget` | Budget Tracking | `skills/budget/` | ✅ Implemented | 4 |
| `briefing` | Daily Briefing | `skills/briefing/` | ✅ Implemented | 5 |
| `web_browse` | Web Browse | `skills/web_browse/` | ✅ Implemented | 5 |

---

## Skill Contract

Every skill must implement:

```python
class MySkill(BaseSkill):
    name = "my_skill"

    async def handle(
        self,
        user: User,
        message: str,
        conversation_history: list[dict[str, str]],
        profile_context: str,
    ) -> SkillResult:
        ...
```

**Parameters received:**
- `user` — `User` dataclass with DB ID, telegram_id, timezone, currency
- `message` — Raw text (already transcribed if voice)
- `conversation_history` — Last N messages as `[{"role": "user"|"assistant", "content": "..."}]`
- `profile_context` — Formatted user profile string for system prompt injection

**Returns:** `SkillResult(text, skill_name, ai_response)`

---

## Routing

The `IntentDetector` classifies each message using a Claude API call with a compact classification prompt (max 64 tokens). The `SkillRouter` dispatches to the matched handler. Unimplemented skills fall back to `chat`.

**Confidence threshold:** `0.6` (configurable via `INTENT_CONFIDENCE_THRESHOLD`). Below threshold → `chat` skill.

**Example routing:**

| Message | Intent | Skill |
|---------|--------|-------|
| "What's the meaning of life?" | general_qa | `chat` |
| "Remember that I'm allergic to shrimp" | memory_store | `memory` |
| "What do you know about me?" | memory_query | `memory` |
| "Remind me to take meds at 8pm" | reminder_create | `reminders` |
| "Spent ₱350 on lunch" | budget_expense | `budget` |
| "Give me my briefing" | briefing_request | `briefing` |
| "What's the latest news on AI?" | web_search | `web_browse` |

---

## Implemented Skills

### Chat (`skills/chat/`) — ✅ Implemented

**Purpose:** General conversation and Q&A. The default fallback for all unclassified messages.

**Files:**
- `handler.py` — `ChatSkill` class
- `prompts.py` — `build_chat_system_prompt(profile_context)`

**System prompt template:**

```
You are KAIA (Knowledge-Aware Intelligent Assistant), a personal AI assistant
on Telegram. You are friendly, helpful, and concise.

IMPORTANT RULES:
- Be warm but not overly chatty. Keep responses focused and useful.
- Use the user profile below to personalise your answers.
- If you learn something new about the user, note it naturally.
- Default currency is Philippine Peso (₱) unless told otherwise.
- Default timezone is Asia/Manila unless told otherwise.
- Use markdown formatting sparingly.
- If you don't know something, say so honestly.

USER PROFILE:
{profile_context}
```

**Flow:** Build system prompt → assemble message history → call `ai.chat()` → return `SkillResult`

---

## Pending Skills

### Memory (`skills/memory/`) — ✅ Implemented

**Purpose:** Handle explicit memory operations, profile queries, and background fact extraction.

**Files:**
- `handler.py` — `MemorySkill` class with store and query flows
- `extractor.py` — `extract_and_save()` background pipeline
- `prompts.py` — Three prompt builders (extraction, query, store)

**Triggers:** "Remember that...", "What do you know about me?", "My name is...", "Don't forget...", "Note that..."

**Store flow:** AI responds with `<memory>[{...}]</memory>` tags containing structured facts. Tags are parsed and stripped before sending to user. Facts saved with `source="explicit"` and `confidence=1.0`.

**Query flow:** AI receives full profile context and presents it conversationally.

**Background extraction:** Runs after every conversation as fire-and-forget asyncio task. Last 10 messages + current profile sent to Claude with extraction prompt. Returns JSON array of `{category, key, value, confidence, source, fact_type}`.

### Reminders (`skills/reminders/`) — ✅ Implemented

**Purpose:** Natural language reminder management with inline Telegram buttons.

**Files:**
- `handler.py` — `RemindersSkill` with create, list, and cancel flows
- `parser.py` — `parse_reminder()` sends message to Claude for NLP parsing
- `prompts.py` — Parsing prompt, confirmation/list/fire message formatters

**Triggers:** "Remind me...", "Set alarm...", "Don't let me forget...", "What reminders do I have?", "Cancel reminder..."

**Create flow:** Message → Claude NLP parsing → structured `{title, datetime_utc, recurrence}` → save to DB → schedule with APScheduler → send confirmation.

**List flow:** Query active reminders from DB → format with titles, times (in user timezone), recurrence → display.

**Cancel flow:** Fuzzy title match or index number → deactivate in DB → remove from scheduler → confirm.

**Inline buttons on fire:** When a reminder fires, the user receives a message with buttons:
- `💤 5m` / `💤 15m` / `💤 1hr` — snooze for that duration
- `✅ Dismiss` — deactivate (one-time) or schedule next (recurring)

**Parsing prompt template:**
```
Parse this reminder request into structured data.
The user's timezone is {timezone}.
The current date/time in their timezone is {current_datetime}.

Return ONLY a JSON object:
{"title": "...", "datetime": "YYYY-MM-DDTHH:MM:SS", "recurrence": "none|daily|weekly|monthly", "is_relative": true|false}

Rules:
- "morning" = 07:00, "afternoon" = 14:00, "evening" = 18:00, "tonight" = 20:00
- "tomorrow" = next day at 09:00 unless time specified
- "in X minutes/hours" → add to current time, is_relative=true
- If no time specified, default to 09:00 next day
- If requested time already passed today, schedule next day
```

**Recurrence:** `none` (one-time), `daily`, `weekly`, `monthly`. Calculated via `dateutil.relativedelta`.

### Budget (`skills/budget/`) — ✅ Implemented

**Purpose:** Income/expense tracking with AI categorisation, budget limits, and spending summaries.

**Files:**
- `handler.py` — `BudgetSkill` class with sub-intent routing: log transaction, summary, comparison, set/list/delete budget limits, undo
- `parser.py` — `parse_transaction()` and `parse_budget_limit()` using Claude for NLP parsing
- `reports.py` — `get_period_summary()`, `get_monthly_comparison()`, period resolution, message formatters
- `prompts.py` — Parsing prompt, summary prompt, budget limit prompt, confirmation/warning formatters

**Triggers:** "Spent...", "Paid...", "Received...", "Lunch 250", monetary amounts, "Budget summary", "How much did I spend...", "Set budget...", "What are my budgets?", "Undo last transaction"

**Categories:** `food`, `transport`, `bills`, `entertainment`, `health`, `shopping`, `education`, `salary`, `freelance`, `family`, `subscriptions`, `savings`, `gifts`, `other`

**Transaction parsing prompt:**
```
Parse this message as a financial transaction. The user's default currency is {currency}.

If this IS a financial transaction, return ONLY this JSON:
{"amount": <number>, "type": "income" or "expense", "category": "<category>", "description": "<brief>", "date": "YYYY-MM-DD"}

If this is NOT a financial transaction, return: {"is_transaction": false}

Rules:
- "spent", "paid", "bought", "grabbed" = expense
- "received", "got", "earned", "payment" = income
- Detect the most specific category possible
- If amount has no currency symbol, assume {currency}
```

**Log flow:** Parse message → save to `transactions` table → check category budget limit → confirm with optional warning if near/over limit.

**Summary flow:** Resolve time period from message → aggregate income/expenses/categories from DB → format with emoji breakdown and limit indicators.

**Budget limits:** Users can set monthly category limits. Every expense is checked against its limit — warnings at 80% usage, alerts when over.

**Undo:** "Undo last transaction" deletes the most recently logged transaction.

**Time periods:** today, yesterday, this week, last week, last 7 days, last month. Default: this month.

### Web Browse (`skills/web_browse/`) — ✅ Implemented

**Purpose:** Search the web, fetch news, check weather, and summarise results using Claude.

**Files:**
- `search.py` — `web_search()` (SerpAPI), `news_search()` (NewsAPI), `get_weather()` (OpenWeatherMap). All use `httpx.AsyncClient`.
- `scraper.py` — `scrape_page()` and `extract_article()` using BeautifulSoup for full page content extraction.
- `prompts.py` — Prompt builders: search summary, page summary, news summary, search decision. `format_search_results()` formatter.
- `handler.py` — `WebBrowseSkill` with sub-intent routing: weather, news, and general web search.

**Triggers:** "Search for...", "Look up...", "What's the latest...", "Google...", "What's the weather?", "News about...", current events, price queries.

**Search flow:** Optimize query via AI → `web_search()` → format results → summarise with Claude.

**Weather flow:** Extract location from message (or use default) → `get_weather()` → format display.

**News flow:** Extract topic → `news_search()` → format articles → summarise with Claude.

**API keys:** All three APIs (SerpAPI, NewsAPI, OpenWeatherMap) are optional. Missing keys = that feature is unavailable, others still work.

### Briefing (`skills/briefing/`) — ✅ Implemented

**Purpose:** Compiled daily briefing delivered automatically (scheduled) or on request.

**Files:**
- `handler.py` — `BriefingSkill` with `generate_briefing()` that compiles all sections via `asyncio.gather()`. Handles time change and enable/disable requests.
- `prompts.py` — `build_motivational_note_prompt()` for personalized morning note, `build_briefing_time_parse_prompt()` for time parsing.

**Triggers:** Auto-scheduled daily at `BRIEFING_TIME` (default 07:00), "Give me my briefing", "Morning update", `/briefing` command, "Change briefing to 6:30am", "Turn off briefing".

**Briefing sections** (gathered in parallel):
1. **Weather** — Current conditions for user's location (from profile or default)
2. **Today's Reminders** — Active reminders firing today
3. **Budget Snapshot** — Month spending, daily average, categories near limits
4. **Motivational Note** — Personalized 1-2 sentence note from Claude based on user profile

**Graceful degradation:** Each section is independent. Missing API key → skip that section. No reminders → skip. No budget data → skip. All empty → "Good morning! Not much on the agenda today."

**Scheduling:** CronTrigger-based in user's timezone. Auto-schedules for all users in `ALLOWED_TELEGRAM_IDS` on startup. Users can change time or disable via natural language.

---

## Expert Channels

Experts live outside the generic skill pipeline — they are full personas with channel-scoped memory, dedicated system prompts, and specialized skill sets. Each implements `BaseExpert` and is registered in `experts/__init__.py` against a `CHANNEL_*` constant.

### MakubeX — Tech Lead / CTO (`experts/makubex/`) — ✅ Implemented (CH-3)

Personality: systems thinker, hacker mindset, methodical, opinionated, progressive depth.

**Intent detection (`parser.py`)** — keyword short-circuits first (project markers, code-review markers, architecture markers, debugging markers, devops markers, security markers, research markers, learning markers). Fenced code blocks auto-route to `code_review`. Falls back to an AI classifier when no keyword hits.

**8 specialized skills:**

| Skill class | File | Highlights |
|-------------|------|------------|
| `CodeReviewSkill` | `skills/code_review.py` | Structured JSON review with severity tiers; SHA-256 snippet dedup via `code_reviews`; heuristic language detection. |
| `ArchitectureSkill` | `skills/architecture.py` | System design, DB schema review, REST API design, A-vs-B approach comparison. |
| `DebuggingSkill` | `skills/debugging.py` | Error explanation, stack-trace walk, systematic debugging plan, performance diagnosis. |
| `TechResearchSkill` | `skills/tech_research.py` | Compare tools, recommend a single tool, latest-on-topic, trend evaluation (all web-search augmented). |
| `DevOpsSkill` | `skills/devops.py` | Infra review, CI/CD design, monitoring setup, containerisation, scaling advice. |
| `SecuritySkill` | `skills/security.py` | Project audit, auth-flow review, API security, secrets guidance, dependency audit with fresh CVE context. |
| `LearningCoachSkill` | `skills/learning_coach.py` | `SKILL_TREES` for python/web_dev/devops/databases/security; depth progression (intro → solid → deep); study plans and quizzes. |
| `ProjectManagerSkill` | `skills/project_manager.py` | CRUD on `tech_projects`, summaries, "suggest next step" for a project. |

**Proactive layer:** `MakubexProactiveSkill.generate_weekly_brief()` runs Mondays 08:00 local (via `core/scheduler.schedule_makubex_weekly_brief`) and compiles active projects, this-week learning, recent code reviews, next-topic suggestion, web-sourced security advisories, and a rotating tip.

**Memory mirror (`extractor.py`):** structural categories (`tech_stack`, `skills`, `projects`, `work_context`, `infrastructure`) propagate to the shared `user_profile` under category `"technical"`; everything else stays channel-scoped.

**Slash shortcuts (`bot/makubex_commands.py`):** `/makubex_review`, `/makubex_projects`, `/makubex_learn`, `/makubex_security`, `/makubex_brief`.

---

## Voice Pipeline (Utility Layer)

Voice is not a skill — it's a transport layer that feeds into the skill pipeline.

**Speech-to-Text:** `utils/voice_stt.py` — Groq Whisper API (`whisper-large-v3-turbo`). Accepts `.ogg` voice notes from Telegram. Returns transcribed text.

**Text-to-Speech:** `utils/voice_tts.py` — edge-tts (free Microsoft voices). Generates `.mp3` audio. Triggered when user has `voice_replies: true` in their profile.

**Flow:**
1. User sends voice message → Telegram delivers `.ogg` file
2. `handle_voice()` downloads file → `transcribe_voice()` → transcribed text
3. Bot replies: "🎙️ I heard: {text}"
4. Transcribed text enters the normal skill pipeline (intent detection → skill routing → response)
5. If voice reply preference is enabled → `text_to_speech()` → reply with audio

**Requirements:**
- `GROQ_API_KEY` — required for transcription (Groq Whisper is free tier)
- No API key needed for TTS (edge-tts is completely free)

---

## Bot Commands

| Command | Handler | Description |
|---------|---------|-------------|
| `/start` | `cmd_start` | Welcome message, DB user creation |
| `/help` | `cmd_help` | Full feature guide |
| `/status` | `cmd_status_extended` | Bot health + user stats (profile, reminders, transactions, AI costs) |
| `/briefing` | `cmd_briefing` | On-demand daily briefing |
| `/export` | `cmd_export` | Export all user data as JSON file |
| `/reset` | `cmd_reset` | Delete all data (requires CONFIRM DELETE) |
| `/makubex_review` | `cmd_makubex_review` | Run MakubeX code review on a pasted snippet |
| `/makubex_projects` | `cmd_makubex_projects` | List tracked tech projects |
| `/makubex_learn` | `cmd_makubex_learn` | Suggest the next topic to study |
| `/makubex_security` | `cmd_makubex_security` | Security audit a tracked project |
| `/makubex_brief` | `cmd_makubex_brief` | Weekly tech brief on demand |

---

## Middleware

| Function | Purpose |
|----------|---------|
| `check_rate_limit()` | 20 messages per 60-second window per user |
| `track_ai_usage()` | Token counting and cost estimation per session |
| `get_session_stats()` | Returns cumulative AI usage stats |
