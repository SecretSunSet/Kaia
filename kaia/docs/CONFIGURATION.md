# KAIA Configuration Reference

All configuration is managed through two files:
- `config/settings.py` — Runtime settings loaded from environment variables
- `config/constants.py` — Compile-time constants (categories, limits, defaults)

---

## Settings (`config/settings.py`)

Pydantic `BaseSettings` class. Values are loaded from environment variables or a `.env` file in the working directory. Environment variables take precedence over `.env` values.

### Telegram

| Setting | Env Var | Type | Default | Description |
|---------|---------|------|---------|-------------|
| `telegram_bot_token` | `TELEGRAM_BOT_TOKEN` | `str` | *required* | Bot token from @BotFather |
| `allowed_telegram_ids` | `ALLOWED_TELEGRAM_IDS` | `list[int]` | `[]` | Authorised user IDs. Empty list = allow everyone |

### AI — Claude (Primary)

| Setting | Env Var | Type | Default | Description |
|---------|---------|------|---------|-------------|
| `anthropic_api_key` | `ANTHROPIC_API_KEY` | `str` | *required* | Anthropic API key |
| `claude_model` | `CLAUDE_MODEL` | `str` | `claude-sonnet-4-20250514` | Model ID |
| `claude_max_tokens` | `CLAUDE_MAX_TOKENS` | `int` | `1024` | Max tokens per response |

### AI — Groq (Fallback)

| Setting | Env Var | Type | Default | Description |
|---------|---------|------|---------|-------------|
| `groq_api_key` | `GROQ_API_KEY` | `str` | `""` | Groq API key. Empty = fallback disabled |
| `groq_model` | `GROQ_MODEL` | `str` | `llama-3.3-70b-versatile` | Groq model ID |

### Database

| Setting | Env Var | Type | Default | Description |
|---------|---------|------|---------|-------------|
| `supabase_url` | `SUPABASE_URL` | `str` | *required* | Supabase project URL |
| `supabase_key` | `SUPABASE_KEY` | `str` | *required* | Supabase service-role key |

### External Services

| Setting | Env Var | Type | Default | Description |
|---------|---------|------|---------|-------------|
| `serpapi_key` | `SERPAPI_KEY` | `str` | `""` | SerpAPI key for web search |
| `openweather_api_key` | `OPENWEATHER_API_KEY` | `str` | `""` | OpenWeather API key |
| `news_api_key` | `NEWS_API_KEY` | `str` | `""` | NewsAPI key |

### Voice

| Setting | Env Var | Type | Default | Description |
|---------|---------|------|---------|-------------|
| `tts_voice` | `TTS_VOICE` | `str` | `en-US-AriaNeural` | edge-tts voice |
| `voice_replies_enabled` | `VOICE_REPLIES_ENABLED` | `bool` | `False` | Auto voice replies |

### Briefing & Location

| Setting | Env Var | Type | Default | Description |
|---------|---------|------|---------|-------------|
| `default_location` | `DEFAULT_LOCATION` | `str` | `Manila, Philippines` | Default weather location |
| `briefing_time` | `BRIEFING_TIME` | `str` | `07:00` | Default daily briefing time (HH:MM) |
| `briefing_enabled` | `BRIEFING_ENABLED` | `bool` | `True` | Enable scheduled daily briefing |

### Behaviour

| Setting | Env Var | Type | Default | Description |
|---------|---------|------|---------|-------------|
| `default_timezone` | `DEFAULT_TIMEZONE` | `str` | `Asia/Manila` | New user timezone |
| `default_currency` | `DEFAULT_CURRENCY` | `str` | `PHP` | New user currency |
| `intent_confidence_threshold` | `INTENT_CONFIDENCE_THRESHOLD` | `float` | `0.6` | Min confidence for non-chat routing |
| `max_conversation_history` | `MAX_CONVERSATION_HISTORY` | `int` | `20` | Messages to include as AI context |
| `log_level` | `LOG_LEVEL` | `str` | `INFO` | Loguru level |

---

## Constants (`config/constants.py`)

Hardcoded values used throughout the application. Change these by editing the file directly.

### Skill Identifiers

```python
SKILL_CHAT = "chat"
SKILL_MEMORY = "memory"
SKILL_REMINDERS = "reminders"
SKILL_BUDGET = "budget"
SKILL_BRIEFING = "briefing"
SKILL_WEB_BROWSE = "web_browse"
```

### Budget Categories

**Expense:** `food`, `transport`, `utilities`, `rent`, `groceries`, `entertainment`, `health`, `shopping`, `subscriptions`, `education`, `personal_care`, `gifts`, `travel`, `savings`, `other`

**Income:** `salary`, `freelance`, `gift`, `refund`, `investment`, `other`

### Profile Categories

`identity`, `health`, `finances`, `personality`, `preferences`, `goals`, `patterns`

### Memory Fact Types

`correction`, `preference`, `habit`, `mood`, `goal`, `general`

### Memory Source Types

`explicit` (user stated directly), `inferred` (AI detected)

### Budget Categories

`food`, `transport`, `bills`, `entertainment`, `health`, `shopping`, `education`, `salary`, `freelance`, `family`, `subscriptions`, `savings`, `gifts`, `other`

### Budget Category Emojis

| Category | Emoji | Category | Emoji |
|----------|-------|----------|-------|
| `food` | 🍔 | `salary` | 💼 |
| `transport` | 🚗 | `freelance` | 💻 |
| `bills` | 🏠 | `family` | 👨‍👩‍👧 |
| `entertainment` | 🎮 | `subscriptions` | 📱 |
| `health` | 💊 | `savings` | 🏦 |
| `shopping` | 🛍️ | `gifts` | 🎁 |
| `education` | 📚 | `other` | 📦 |

### Reminder Recurrence

`none`, `daily`, `weekly`, `monthly`

### Conversation Roles

`user`, `assistant`

### Limits & Defaults

| Constant | Value | Description |
|----------|-------|-------------|
| `MAX_TELEGRAM_MESSAGE_LENGTH` | `4096` | Telegram's max message size |
| `MAX_SNOOZE_COUNT` | `5` | Max times a reminder can be snoozed |
| `DEFAULT_SNOOZE_MINUTES` | `10` | Default snooze duration |
| `DEFAULT_BRIEFING_HOUR` | `7` | 7:00 AM local time |
| `DEFAULT_CONFIDENCE` | `0.5` | Initial confidence for inferred facts |
| `BUDGET_WARNING_THRESHOLD` | `0.8` | Warn when category spending reaches 80% of limit |
| `BRIEFING_DEFAULT_TIME` | `"07:00"` | Default daily briefing time |
| `DEFAULT_WEATHER_LOCATION` | `"Manila, Philippines"` | Default weather location |
| `WEB_SEARCH_MAX_RESULTS` | `5` | Max search results to fetch |
| `WEB_SCRAPE_MAX_CHARS` | `3000` | Max chars to extract from a web page |
| `WEB_REQUEST_TIMEOUT` | `10` | HTTP request timeout in seconds |

### Currency Symbols

| Code | Symbol |
|------|--------|
| `PHP` | `₱` |
| `USD` | `$` |
| `EUR` | `€` |
| `GBP` | `£` |
| `JPY` | `¥` |
