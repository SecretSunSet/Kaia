# KAIA API Reference

Complete reference of all public classes, functions, and their signatures.

---

## config/settings.py

### `class Settings(BaseSettings)`

Pydantic settings loaded from environment variables / `.env` file.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `telegram_bot_token` | `str` | *required* | Telegram Bot API token |
| `allowed_telegram_ids` | `list[int]` | `[]` | Allowed Telegram user IDs (empty = all) |
| `anthropic_api_key` | `str` | *required* | Anthropic API key |
| `claude_model` | `str` | `"claude-sonnet-4-20250514"` | Claude model ID |
| `claude_max_tokens` | `int` | `1024` | Max tokens per response |
| `groq_api_key` | `str` | `""` | Groq API key (empty = no fallback) |
| `groq_model` | `str` | `"llama-3.3-70b-versatile"` | Groq model ID |
| `supabase_url` | `str` | *required* | Supabase project URL |
| `supabase_key` | `str` | *required* | Supabase anon/service key |
| `serpapi_key` | `str` | `""` | SerpAPI key |
| `openweather_api_key` | `str` | `""` | OpenWeather API key |
| `news_api_key` | `str` | `""` | NewsAPI key |
| `tts_voice` | `str` | `"en-US-AriaNeural"` | edge-tts voice name |
| `voice_replies_enabled` | `bool` | `False` | Voice replies on by default |
| `default_timezone` | `str` | `"Asia/Manila"` | Default timezone |
| `default_currency` | `str` | `"PHP"` | Default currency code |
| `intent_confidence_threshold` | `float` | `0.6` | Min confidence for skill routing |
| `max_conversation_history` | `int` | `20` | Recent messages for context |
| `log_level` | `str` | `"INFO"` | Loguru log level |

### `get_settings() -> Settings`

Returns a `Settings` instance. Reads from env vars / `.env` on each call.

---

## database/connection.py

### `get_supabase() -> Client`

Returns a singleton Supabase client. Initialises on first call using `SUPABASE_URL` and `SUPABASE_KEY`.

---

## database/models.py

### `@dataclass User`

| Field | Type | Default |
|-------|------|---------|
| `telegram_id` | `int` | *required* |
| `id` | `str` | `""` |
| `username` | `str \| None` | `None` |
| `timezone` | `str` | `"Asia/Manila"` |
| `currency` | `str` | `"PHP"` |
| `created_at` | `datetime \| None` | `None` |
| `updated_at` | `datetime \| None` | `None` |

### `@dataclass ProfileEntry`

| Field | Type | Default |
|-------|------|---------|
| `user_id` | `str` | *required* |
| `category` | `str` | *required* |
| `key` | `str` | *required* |
| `value` | `str` | *required* |
| `id` | `str` | `""` |
| `confidence` | `float` | `0.5` |
| `source` | `str` | `"inferred"` |
| `updated_at` | `datetime \| None` | `None` |

### `@dataclass MemoryLogEntry`

| Field | Type | Default |
|-------|------|---------|
| `user_id` | `str` | *required* |
| `session_id` | `str` | *required* |
| `fact` | `str` | *required* |
| `id` | `str` | `""` |
| `fact_type` | `str` | `"general"` |
| `created_at` | `datetime \| None` | `None` |

### `@dataclass Reminder`

| Field | Type | Default |
|-------|------|---------|
| `user_id` | `str` | *required* |
| `title` | `str` | *required* |
| `scheduled_time` | `datetime` | *required* |
| `id` | `str` | `""` |
| `recurrence` | `str` | `"none"` |
| `is_active` | `bool` | `True` |
| `snooze_count` | `int` | `0` |
| `created_at` | `datetime \| None` | `None` |

### `@dataclass Transaction`

| Field | Type | Default |
|-------|------|---------|
| `user_id` | `str` | *required* |
| `amount` | `Decimal` | *required* |
| `type` | `str` | *required* |
| `category` | `str` | *required* |
| `id` | `str` | `""` |
| `description` | `str \| None` | `None` |
| `transaction_date` | `date` | `date.today()` |
| `created_at` | `datetime \| None` | `None` |

### `@dataclass Conversation`

| Field | Type | Default |
|-------|------|---------|
| `user_id` | `str` | *required* |
| `role` | `str` | *required* |
| `content` | `str` | *required* |
| `id` | `str` | `""` |
| `skill_used` | `str \| None` | `None` |
| `created_at` | `datetime \| None` | `None` |

### `@dataclass BudgetLimit`

| Field | Type | Default |
|-------|------|---------|
| `user_id` | `str` | *required* |
| `category` | `str` | *required* |
| `monthly_limit` | `Decimal` | *required* |
| `id` | `str` | `""` |
| `is_active` | `bool` | `True` |

---

## database/queries.py

### `async get_or_create_user(telegram_id: int, username: str | None = None) -> User`

Finds an existing user by `telegram_id` or creates a new one. Returns a populated `User` dataclass.

### `async get_user_profile(user_id: str) -> list[ProfileEntry]`

Loads all profile entries for a user. Returns list of `ProfileEntry`.

### `async upsert_profile_entry(user_id: str, category: str, key: str, value: str, confidence: float = 0.5, source: str = "inferred") -> None`

Inserts or updates a single profile fact. Upserts on `(user_id, category, key)`.

### `async save_conversation(user_id: str, role: str, content: str, skill_used: str | None = None) -> None`

Appends a message to the conversation history table.

### `async get_recent_conversations(user_id: str, limit: int = 20) -> list[Conversation]`

Returns the most recent `limit` messages for a user, ordered oldest-first (suitable for context injection).

### `async add_memory_log(user_id: str, session_id: str, fact: str, fact_type: str = "general") -> None`

Records a learned fact to the memory log.

### `async create_reminder(user_id: str, title: str, scheduled_time: str, recurrence: str = "none") -> Reminder`

Creates a new reminder in the database. `scheduled_time` is an ISO 8601 UTC datetime string. Returns the created `Reminder` dataclass.

### `async get_active_reminders(user_id: str) -> list[Reminder]`

Returns all active (non-dismissed) reminders for a user, ordered by `scheduled_time`.

### `async get_all_active_reminders() -> list[dict]`

Returns all active reminders across all users with a JOIN to get `telegram_id`. Used by the scheduler on startup to restore all jobs. Each dict contains reminder fields plus `users.telegram_id`.

### `async get_reminder_by_id(reminder_id: str) -> Reminder | None`

Fetches a single reminder by ID. Returns `None` if not found.

### `async update_reminder(reminder_id: str, **fields) -> None`

Updates arbitrary fields on a reminder row. Accepts any column name as a keyword argument (e.g. `scheduled_time`, `snooze_count`, `is_active`).

### `async deactivate_reminder(reminder_id: str) -> None`

Sets `is_active = False` on a reminder. Used when dismissing one-time reminders or cancelling reminders.

### `async get_user_for_reminder(reminder_id: str) -> User | None`

Fetches the `User` who owns a given reminder. Returns `None` if the reminder or user doesn't exist.

### `_row_to_reminder(row: dict) -> Reminder`

Internal helper that converts a Supabase result row into a `Reminder` dataclass.

### `async create_transaction(user_id: str, amount: float, type: str, category: str, description: str | None = None, transaction_date: str | None = None) -> Transaction`

Inserts a new transaction and returns the `Transaction` dataclass.

### `async get_transactions(user_id: str, start_date: str, end_date: str, category: str | None = None) -> list[Transaction]`

Returns transactions for a user within a date range, optionally filtered by category. Ordered by `transaction_date` descending.

### `async get_category_total(user_id: str, category: str, start_date: str, end_date: str) -> float`

Returns total expense spending in a specific category for a date range.

### `async get_spending_by_category(user_id: str, start_date: str, end_date: str) -> list[dict]`

Returns expense totals grouped by category. Each dict: `{"category": str, "total": float}`, sorted by total descending.

### `async get_income_total(user_id: str, start_date: str, end_date: str) -> float`

Returns total income for a date range.

### `async get_expense_total(user_id: str, start_date: str, end_date: str) -> float`

Returns total expenses for a date range.

### `async get_last_transaction(user_id: str) -> Transaction | None`

Returns the most recently created transaction for a user. Used by the undo feature.

### `async delete_transaction(transaction_id: str) -> None`

Deletes a transaction by ID.

### `async create_or_update_budget_limit(user_id: str, category: str, monthly_limit: float) -> BudgetLimit`

Upserts a budget limit for a category. Returns the `BudgetLimit` dataclass.

### `async get_budget_limits(user_id: str) -> list[BudgetLimit]`

Returns all active budget limits for a user.

### `async get_budget_limit(user_id: str, category: str) -> BudgetLimit | None`

Returns the budget limit for a specific category, or `None` if not set.

### `async deactivate_budget_limit(user_id: str, category: str) -> None`

Deactivates a budget limit by setting `is_active = False`.

### `_row_to_transaction(row: dict) -> Transaction`

Internal helper that converts a Supabase result row into a `Transaction` dataclass.

### `_row_to_budget_limit(row: dict) -> BudgetLimit`

Internal helper that converts a Supabase result row into a `BudgetLimit` dataclass.

---

## core/ai_engine.py

### `@dataclass AIResponse`

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | The AI's response text |
| `provider` | `str` | `"claude"` or `"groq"` |
| `model` | `str` | Model ID used |
| `input_tokens` | `int` | Input tokens consumed |
| `output_tokens` | `int` | Output tokens generated |

### `class AIEngine`

#### `__init__(self) -> None`

Initialises Claude client (always) and Groq client (if `GROQ_API_KEY` is set).

#### `async chat(self, system_prompt: str, messages: list[dict[str, str]], max_tokens: int | None = None) -> AIResponse`

Sends a chat request to Claude. Falls back to Groq on any Claude failure. Raises `RuntimeError` if both fail (or Groq is not configured).

**Parameters:**
- `system_prompt` — System message (persona + user profile)
- `messages` — Conversation as `[{"role": "user"|"assistant", "content": "..."}]`
- `max_tokens` — Override default max tokens (optional)

### `build_message_history(conversations: list[dict[str, str]], current_message: str) -> list[dict[str, str]]`

Appends the current user message to an existing conversation history list. Returns the combined list.

---

## skills/base.py

### `@dataclass SkillResult`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | `str` | *required* | Response text to send to user |
| `skill_name` | `str` | *required* | Which skill produced this |
| `ai_response` | `AIResponse \| None` | `None` | AI metadata (tokens, provider) |

### `class BaseSkill(ABC)`

Abstract base class. All skills inherit from this.

**Attributes:**
- `name: str` — Skill identifier (e.g. `"chat"`)
- `ai: AIEngine` — Shared AI engine instance

#### `__init__(self, ai_engine: AIEngine) -> None`

Stores the AI engine reference.

#### `@abstractmethod async handle(self, user: User, message: str, conversation_history: list[dict[str, str]], profile_context: str) -> SkillResult`

Process a user message and return a response. Every skill must implement this.

---

## skills/chat/prompts.py

### `build_chat_system_prompt(profile_context: str) -> str`

Builds the KAIA persona system prompt for general chat. Injects the user profile string into a template that defines personality, rules, and defaults (currency: PHP, timezone: Asia/Manila).

---

## skills/chat/handler.py

### `class ChatSkill(BaseSkill)`

General Q&A handler. The default fallback skill.

- `name = "chat"`

#### `async handle(self, user: User, message: str, conversation_history: list[dict[str, str]], profile_context: str) -> SkillResult`

Builds system prompt via `build_chat_system_prompt()`, assembles message history, calls `ai.chat()`, returns `SkillResult`.

---

## core/memory_manager.py

### `class MemoryManager`

Centralises profile operations and background memory extraction.

#### `__init__(self, ai_engine: AIEngine) -> None`

Stores AI engine reference.

#### `async load_profile_context(self, user_id: str) -> str`

Loads profile entries from DB and formats them for system prompt injection.

#### `async load_profile_entries(self, user_id: str) -> list[ProfileEntry]`

Returns raw `ProfileEntry` list from the database.

#### `run_background_extraction(self, user_id: str, conversation_messages: list[dict[str, str]]) -> None`

Creates a fire-and-forget asyncio task that runs `extract_and_save()`. Does not block the caller. Logs errors but does not raise.

### `format_profile(profile_entries: list[ProfileEntry]) -> str`

Module-level helper. Converts profile entries into a formatted string grouped by category:

```
[CATEGORY]
  key: value (confidence: 80%)
```

---

## core/intent_detector.py

### `@dataclass IntentResult`

| Field | Type | Description |
|-------|------|-------------|
| `skill` | `str` | Target skill ID (e.g. `"chat"`, `"memory"`) |
| `confidence` | `float` | Classification confidence (0.0–1.0) |

### `class IntentDetector`

#### `__init__(self, ai_engine: AIEngine) -> None`

Stores AI engine and loads settings (for confidence threshold).

#### `async detect(self, message: str) -> IntentResult`

Sends the message to Claude with a classification prompt. Returns `IntentResult`. Falls back to `chat` with `confidence=0.0` on any error, or when confidence is below `intent_confidence_threshold`.

---

## core/skill_router.py

### `class SkillRouter`

#### `__init__(self, ai_engine: AIEngine) -> None`

Creates `IntentDetector` and registers all implemented skill instances.

#### `async route(self, user: User, message: str, conversation_history: list[dict[str, str]], profile_context: str) -> SkillResult`

Detects intent, looks up the skill handler, and calls `skill.handle()`. If the detected skill is not yet implemented, falls back to `chat`.

#### `intent_detector -> IntentDetector` *(property)*

Exposes the internal intent detector for direct use.

---

## skills/memory/prompts.py

### `build_extraction_prompt() -> str`

System prompt for background memory extraction. Instructs the AI to return a JSON array of new facts with `category`, `key`, `value`, `confidence`, `source`, `fact_type`.

### `build_memory_query_prompt(profile_context: str) -> str`

System prompt for when the user asks about their profile ("What do you know about me?").

### `build_memory_store_prompt(profile_context: str) -> str`

System prompt for explicit "remember that..." requests. Instructs the AI to include facts in `<memory>` XML tags for machine parsing, with a natural language response after.

---

## skills/memory/extractor.py

### `async extract_and_save(ai_engine: AIEngine, user_id: str, conversation_messages: list[dict[str, str]]) -> int`

Runs the full extraction pipeline:
1. Loads current profile from DB
2. Sends last 10 messages + profile to AI with extraction prompt
3. Parses returned JSON facts
4. Upserts each fact to `user_profile` and logs to `memory_log`

Returns the count of facts saved. Returns 0 on error or if no new facts found.

---

## skills/memory/handler.py

### `class MemorySkill(BaseSkill)`

Handles memory queries and explicit fact storage.

- `name = "memory"`

#### `async handle(self, user: User, message: str, conversation_history: list[dict[str, str]], profile_context: str) -> SkillResult`

Detects store vs query using `_is_store_request()` heuristic, then dispatches to `_handle_store()` or `_handle_query()`.

**Store flow:** Calls AI with store prompt → parses `<memory>` tags → upserts facts with `source="explicit"` → strips tags from visible response.

**Query flow:** Calls AI with query prompt → returns profile summary naturally.

### `_is_store_request(message: str) -> bool`

Heuristic check. Returns `True` if the message contains patterns like "remember that", "my name is", "don't forget", etc.

### `_extract_memory_tags(text: str) -> list[dict]`

Parses `<memory>[...]</memory>` tags from AI response text. Returns a list of fact dicts, or empty list if no valid tags found.

---

## utils/time_utils.py

### `now_utc() -> datetime`

Returns current UTC time (timezone-aware).

### `now_in_tz(tz_name: str = "Asia/Manila") -> datetime`

Returns current time in the given timezone.

### `to_utc(dt: datetime, from_tz: str = "Asia/Manila") -> datetime`

Converts a naive or local datetime to UTC. Naive datetimes are assumed to be in `from_tz`.

### `to_local(dt: datetime, to_tz: str = "Asia/Manila") -> datetime`

Converts a UTC datetime to a local timezone.

### `format_local(dt: datetime, to_tz: str = "Asia/Manila") -> str`

Formats a datetime for display in the user's timezone. Returns e.g. `"Mon Apr 14 08:00 PM"`.

### `next_occurrence(dt: datetime, recurrence: str) -> datetime`

Calculates the next occurrence of a recurring reminder. Supports `"daily"`, `"weekly"`, `"monthly"` (via `dateutil.relativedelta`).

---

## core/scheduler.py

### `get_scheduler() -> AsyncIOScheduler`

Returns the singleton APScheduler instance.

### `async start_scheduler(bot: Bot) -> None`

Starts the scheduler and loads all active reminders from the database.

### `shutdown_scheduler() -> None`

Gracefully shuts down the scheduler.

### `async load_all_reminders(bot: Bot) -> None`

Loads all active reminders from DB and schedules them. Handles missed reminders: advances recurring ones to next future occurrence, deactivates expired one-time reminders.

### `async schedule_reminder(reminder_id: str, telegram_id: int, title: str, fire_time_utc: datetime, bot: Bot) -> None`

Adds a new reminder job to the scheduler.

### `async cancel_reminder(reminder_id: str) -> None`

Removes a reminder job from the scheduler.

### `async reschedule_reminder(reminder_id: str, new_time_utc: datetime) -> None`

Reschedules an existing reminder to a new time.

### `async handle_snooze(reminder_id: str, minutes: int, bot: Bot) -> str`

Snoozes a reminder by the given minutes. Updates DB (`scheduled_time`, `snooze_count`), reschedules job. Returns status message.

### `async handle_dismiss(reminder_id: str) -> str`

Dismisses a reminder. One-time: deactivates. Recurring: schedules next occurrence. Returns status message.

---

## skills/reminders/prompts.py

### `build_parse_prompt(user_timezone: str, current_datetime: str) -> str`

System prompt for NLP reminder parsing. Instructs the AI to return JSON with `title`, `datetime`, `recurrence`, `is_relative`.

### `format_confirmation(title: str, display_time: str, recurrence: str) -> str`

Formats a Telegram confirmation message after creating a reminder.

### `format_reminder_list(reminders: list[dict]) -> str`

Formats a numbered list of active reminders for display.

### `format_fire_message(title: str) -> str`

Formats the message sent when a reminder fires.

---

## skills/reminders/parser.py

### `async parse_reminder(ai_engine: AIEngine, message: str, user_timezone: str = "Asia/Manila") -> dict | None`

Parses a natural-language reminder into structured data. Returns `{"title": str, "datetime_utc": datetime, "recurrence": str}` or `None` on failure.

---

## skills/reminders/handler.py

### `set_bot(bot: Bot) -> None`

Stores the bot reference for use by the scheduler when creating new reminders.

### `class RemindersSkill(BaseSkill)`

- `name = "reminders"`

#### `async handle(self, user, message, conversation_history, profile_context) -> SkillResult`

Detects sub-intent (list/cancel/create) and dispatches.

- **Create:** Parses message → saves to DB → schedules → confirms.
- **List:** Queries active reminders → formats list.
- **Cancel:** Fuzzy match title or index number → deactivates → confirms.

---

## skills/budget/prompts.py

### `build_parse_prompt(currency: str, today: date) -> str`

System prompt for NLP transaction parsing. Instructs the AI to return JSON with `amount`, `type`, `category`, `description`, `date`, or `{"is_transaction": false}`.

### `build_summary_prompt(period: str, transaction_data: str, currency_symbol: str) -> str`

System prompt for generating natural language budget summaries from transaction data.

### `build_budget_limit_parse_prompt(currency: str) -> str`

System prompt for parsing budget limit setting requests into `{category, amount}`.

### `format_transaction_confirmation(amount: float, type: str, category: str, description: str | None, currency_symbol: str) -> str`

Formats a confirmation message after logging a transaction.

### `format_budget_warning(category: str, spent: float, limit: float, currency_symbol: str) -> str`

Formats a warning message when spending is near or over a category budget limit.

---

## skills/budget/parser.py

### `async parse_transaction(ai_engine: AIEngine, message: str, currency: str = "PHP") -> dict | None`

Parses a natural language financial message into structured data. Returns `{"amount": float, "type": str, "category": str, "description": str, "date": str}` or `None` if not a transaction.

### `async parse_budget_limit(ai_engine: AIEngine, message: str, currency: str = "PHP") -> dict | None`

Parses a budget limit setting request. Returns `{"category": str, "amount": float}` or `None`.

---

## skills/budget/reports.py

### `async get_period_summary(user_id: str, start_date: str, end_date: str) -> dict`

Returns aggregated data: `income`, `expenses`, `net`, `categories` (list of `{category, total}`), `transaction_count`.

### `async get_category_spending(user_id: str, category: str, start_date: str, end_date: str) -> float`

Returns total spending in a category for a date range.

### `async get_monthly_comparison(user_id: str) -> dict`

Compares current month vs last month: expenses, income, change percentage.

### `format_summary_message(data: dict, currency_symbol: str, period_label: str, limits: list[BudgetLimit] | None = None) -> str`

Formats aggregated budget data into a Telegram message with emoji category breakdown and budget limit warnings.

### `format_comparison_message(data: dict, currency_symbol: str) -> str`

Formats month-over-month comparison message.

### `format_budget_limits_message(limits: list[BudgetLimit], category_spending: dict[str, float], currency_symbol: str) -> str`

Formats budget limits with current spending and status indicators.

### `resolve_period(message: str) -> tuple[str, str, str]`

Determines date range from natural language. Returns `(start_date, end_date, label)`. Supports: today, yesterday, this week, last week, last 7 days, last month. Defaults to current month.

---

## skills/budget/handler.py

### `class BudgetSkill(BaseSkill)`

- `name = "budget"`

#### `async handle(self, user, message, conversation_history, profile_context) -> SkillResult`

Detects sub-intent and dispatches to the appropriate flow:

- **Log transaction:** Parses message → saves to DB → checks budget limit → confirms with optional warning.
- **Summary:** Resolves time period → queries aggregated data → formats breakdown.
- **Comparison:** Compares current vs last month spending.
- **Set limit:** Parses category + amount → upserts budget limit → confirms.
- **List limits:** Shows all active limits with current spending.
- **Delete limit:** Fuzzy matches category → deactivates → confirms.
- **Undo:** Deletes the most recent transaction → confirms.

---

## skills/web_browse/search.py

### `async web_search(query: str, num_results: int = 5) -> list[dict]`

Searches the web using SerpAPI. Returns list of `{"title": str, "url": str, "snippet": str}`. Returns empty list if `SERPAPI_KEY` is not configured or on error.

### `async news_search(query: str | None = None, num_results: int = 5) -> list[dict]`

Searches for news using NewsAPI. Returns list of `{"title": str, "url": str, "description": str, "source": str, "published_at": str}`. `None` query returns top headlines. Returns empty list if `NEWS_API_KEY` is not configured.

### `async get_weather(location: str = "Manila, Philippines") -> dict | None`

Fetches current weather from OpenWeatherMap. Returns `{"temp": float, "feels_like": float, "description": str, "humidity": int, "wind_speed": float, "location": str}`. Returns `None` if not configured or on error.

---

## skills/web_browse/scraper.py

### `async scrape_page(url: str, max_chars: int = 3000) -> str | None`

Fetches a web page and extracts main text content using BeautifulSoup. Strips scripts, styles, nav elements. Returns cleaned text truncated to `max_chars`, or `None` on failure.

### `async extract_article(url: str) -> dict | None`

Extracts article content. Returns `{"title": str, "text": str}` or `None` on failure.

---

## skills/web_browse/prompts.py

### `build_search_summary_prompt(query: str, formatted_results: str) -> str`

Prompt for summarising web search results.

### `build_page_summary_prompt(query: str, url: str, page_content: str) -> str`

Prompt for summarising scraped page content.

### `build_news_summary_prompt(query: str | None, formatted_articles: str) -> str`

Prompt for summarising news results.

### `build_search_decision_prompt() -> str`

System prompt for AI to decide whether a web search is needed.

### `format_search_results(results: list[dict]) -> str`

Formats search results for injection into an AI prompt.

---

## skills/web_browse/handler.py

### `class WebBrowseSkill(BaseSkill)`

- `name = "web_browse"`

#### `async handle(self, user, message, conversation_history, profile_context) -> SkillResult`

Detects sub-intent and dispatches:

- **Weather:** Extract location → `get_weather()` → format display.
- **News:** Extract topic → `news_search()` → summarise with Claude.
- **Search:** Optimize query via AI → `web_search()` → summarise with Claude.

---

## skills/briefing/prompts.py

### `build_motivational_note_prompt(profile_context: str, recent_patterns: str) -> str`

Prompt for generating a personalized 1-2 sentence morning note based on user profile.

### `build_briefing_time_parse_prompt(timezone: str) -> str`

Prompt for parsing briefing time change requests into `{"time": "HH:MM"}`.

---

## skills/briefing/handler.py

### `class BriefingSkill(BaseSkill)`

- `name = "briefing"`

#### `async handle(self, user, message, conversation_history, profile_context) -> SkillResult`

Detects sub-intent: disable briefing, change time, or generate briefing.

#### `async generate_briefing(self, user: User, profile_context: str = "") -> str`

Compiles the daily briefing. Gathers all sections in parallel via `asyncio.gather()`:
- Today's reminders (from DB)
- Budget snapshot (current month aggregates + limit warnings)
- Weather (OpenWeatherMap for user's location)
- Motivational note (Claude, based on user profile)

Each section degrades gracefully — missing data or API errors → skip that section.

---

## core/scheduler.py — Briefing Functions

### `async schedule_daily_briefing(user_id: str, telegram_id: int, time_str: str = "07:00", timezone: str = "Asia/Manila", bot: Bot | None = None) -> None`

Schedules (or reschedules) a daily briefing using APScheduler CronTrigger in the user's timezone.

### `async cancel_daily_briefing(user_id: str) -> None`

Cancels the daily briefing for a user.

---

## bot/telegram_bot.py

### Module-Level Globals

- `settings: Settings` — App settings
- `ai_engine: AIEngine` — Shared AI engine
- `memory_mgr: MemoryManager` — Profile + background extraction
- `skill_router: SkillRouter` — Intent detection + skill dispatch

### `_is_allowed(telegram_id: int) -> bool`

Returns `True` if the user is authorised. Empty `allowed_telegram_ids` = allow everyone.

### `async cmd_start(update, context) -> None`

Handles `/start`. Greets the user, creates DB record if new.

### `async cmd_help(update, context) -> None`

Handles `/help`. Shows available commands.

### `async cmd_status(update, context) -> None`

Handles `/status`. Shows bot health: AI model, fallback status, timezone.

### `async cmd_briefing(update, context) -> None`

Handles `/briefing`. Triggers an on-demand daily briefing using `BriefingSkill.generate_briefing()`.

### `async handle_message(update, context) -> None`

Main message handler. Full pipeline:
1. Access control check
2. Load/create user
3. Load profile context via `MemoryManager`
4. Load conversation history
5. Route to skill via `SkillRouter` (intent detection → dispatch)
6. Save conversation to DB
7. Reply to user
8. Run background memory extraction (fire-and-forget)
9. Log token usage

### `async handle_callback(update, context) -> None`

Processes inline button presses from reminder messages. Parses callback data format:
- `snooze_{minutes}_{reminder_id}` → calls `handle_snooze()`
- `dismiss_{reminder_id}` → calls `handle_dismiss()`

Edits the original message to show the result (e.g. "Snoozed until...").

### `async error_handler(update, context) -> None`

Catches and logs unhandled telegram-bot framework errors.

### `async post_init(application) -> None`

Called after Application initialises. Starts the scheduler and stores bot reference for reminder handler.

### `async post_shutdown(application) -> None`

Called on shutdown. Gracefully stops the scheduler.

### `_should_reply_with_voice(profile_context: str) -> bool`

Checks if the user wants voice replies based on their profile (looks for `voice_replies: true` or `voice replies: enabled`).

### `async handle_voice(update, context) -> None`

Handles voice messages. Downloads `.ogg` file, transcribes via Groq Whisper, sends "I heard: ..." confirmation, processes transcribed text through the full skill pipeline (route → save → extract). Optionally replies with TTS audio if voice reply preference is enabled.

### `async post_init(application) -> None`

Called after Application initialises. Starts the scheduler, stores bot reference for reminder handler, cleans up stale TTS files.

### `async post_shutdown(application) -> None`

Called on shutdown. Gracefully stops the scheduler.

### `main() -> None`

Configures loguru, builds the Telegram `Application` with `post_init`/`post_shutdown` lifecycle hooks, registers all handlers (commands, messages, voice, callback queries), starts polling. Entry point when run as `python -m bot.telegram_bot`.

---

## bot/commands.py

### `cmd_status_extended(update, context) -> None`

Enhanced `/status` handler. Queries Supabase for user stats: profile fact count, active reminders, transactions, conversations, member-since date. Also includes session AI call count and estimated cost.

### `cmd_export(update, context) -> None`

Handles `/export`. Gathers all user data (profile, reminders, transactions, recent conversations), writes to a temp JSON file, sends as a Telegram document attachment.

### `cmd_reset(update, context) -> None`

Handles `/reset`. Sets a pending reset flag with a 2-minute timeout. User must type exact `CONFIRM DELETE` to proceed.

### `handle_reset_confirmation(update) -> bool`

Called at the start of `handle_message()`. Checks if text is `CONFIRM DELETE` within timeout window. If so, deletes all user data across all child tables. Returns `True` if handled (caller should return early).

---

## bot/middleware.py

### `check_rate_limit(telegram_id: int) -> bool`

Sliding-window rate limiter. Returns `True` if user is within limits (20 messages per 60-second window), `False` if exceeded. Tracks per-user timestamps in memory.

### `track_ai_usage(input_tokens: int, output_tokens: int, provider: str = "claude") -> None`

Tracks token usage and estimated cost for the current session. Cost calculated at Claude Sonnet rates ($3/M input, $15/M output).

### `get_session_stats() -> dict`

Returns `{"total_input_tokens", "total_output_tokens", "total_calls", "estimated_cost_usd"}`.

---

## utils/voice_stt.py

### `async transcribe_voice(file_path: str) -> str | None`

Transcribes a voice file using Groq Whisper API (`whisper-large-v3-turbo`). Accepts `.ogg` files directly. Returns transcribed text, or `None` if `GROQ_API_KEY` is not set or on error. 30-second timeout.

---

## utils/voice_tts.py

### `async text_to_speech(text: str, voice: str = "en-US-AriaNeural", output_path: str | None = None) -> str | None`

Generates speech audio using edge-tts (free Microsoft voices). Writes `.mp3` to temp directory. Truncates input to 2000 chars. Returns file path, or `None` on error.

### `cleanup_old_files(max_age_seconds: int = 3600) -> None`

Removes TTS temp files older than `max_age_seconds` from the `/tmp/kaia_tts/` directory.

### `safe_delete(file_path: str) -> None`

Deletes a file, silently ignoring errors if it doesn't exist.

---

## utils/validators.py

### `sanitize_message(text: str) -> str`

Strips leading/trailing whitespace and limits message length.

### `is_valid_amount(text: str) -> bool`

Checks if a string looks like a valid monetary amount.

### `validate_timezone(tz: str) -> bool`

Returns `True` if `tz` is a valid IANA timezone name.

### `validate_currency(code: str) -> bool`

Returns `True` if `code` is a recognized currency code.

---

## utils/formatters.py

### `escape_markdown(text: str) -> str`

Escapes Telegram MarkdownV2 special characters.

### `format_currency(amount: float, currency: str = "PHP") -> str`

Formats a number with the appropriate currency symbol (e.g. `₱1,500.00`).

### `format_datetime(dt: datetime, timezone: str = "Asia/Manila") -> str`

Formats a datetime for display in the user's timezone.

### `truncate(text: str, max_length: int = 4096) -> str`

Truncates text to fit Telegram's message limit, appending `...` if truncated.
