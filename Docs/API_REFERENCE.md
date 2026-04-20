# API Reference — Expert Channel System

## Core Classes

### `ChannelManager` — `kaia/core/channel_manager.py`

Manages user channel state and switching. Stateless service class.

| Method | Returns | Description |
|--------|---------|-------------|
| `get_active_channel(user_id)` | `str` | Current channel_id or `"general"` |
| `switch_channel(user_id, channel_id)` | `Channel` | Switch + return channel info. Raises `ValueError` if channel unknown |
| `exit_channel(user_id)` | `None` | Reset to general |
| `get_channel_info(channel_id)` | `Channel \| None` | Load channel definition |
| `get_all_channels()` | `list[Channel]` | All active channels |
| `is_first_visit(user_id, channel_id)` | `bool` | True if user has zero messages in this channel |

### `ChannelMemoryManager` — `kaia/core/channel_memory.py`

Per-channel memory management and knowledge gap tracking.

| Method | Returns | Description |
|--------|---------|-------------|
| `load_channel_profile(user_id, channel_id)` | `str` | Formatted channel-specific profile |
| `load_combined_context(user_id, channel_id)` | `str` | Shared + channel profile merged |
| `update_channel_profile(...)` | `None` | Upsert one channel fact |
| `batch_update_channel_profile(user_id, channel_id, facts)` | `int` | Upsert many facts; returns saved count |
| `get_knowledge_gaps(channel_id, entries)` | `list[dict]` | Missing required knowledge, sorted by priority |
| `get_knowledge_score(channel_id, entries)` | `dict` | `{"score": int, "known": [...], "missing": [...]}` |
| `get_top_gap(channel_id, entries)` | `dict \| None` | Single highest-priority gap |

### `channel_extract_and_save()` — `kaia/core/channel_extractor.py`

Domain-focused fact extraction per channel.

```python
await channel_extract_and_save(ai_engine, user_id, channel_id, conversation_messages) -> int
```

Uses a channel-specific domain prompt (financial facts for Hevn, tech facts for MakubeX, etc.) and saves extracted facts to `channel_profile`. Returns count saved.

### `ForumManager` — `kaia/core/forum_manager.py`

Maps Telegram forum topics to expert channels. Stateless service; persistence is in the `forum_topic_mappings` table.

| Method | Returns | Description |
|--------|---------|-------------|
| `setup_forum_topics(bot, chat_id)` | `dict[str, int]` | Create the four expert topics in a group, persist the mappings, return `{channel_id: topic_id}`. Raises `ForumSetupError` (with `is_permission_error=True` when the bot lacks **Manage Topics**) |
| `get_channel_for_topic(chat_id, topic_id)` | `str \| None` | Map a topic back to a channel. Returns `"general"` when `topic_id` is `None` or `1` (the implicit General topic). Returns `None` for unmapped topics |
| `get_topic_for_channel(chat_id, channel_id)` | `int \| None` | Reverse lookup — topic_id for a channel in a group, or `None` if the channel is `"general"` / unmapped |
| `is_forum_setup(chat_id)` | `bool` | True if any mappings exist for this group |
| `load_topic_mappings(chat_id)` | `dict[str, int]` | All `{channel_id: topic_id}` entries for a group |
| `clear_mappings(chat_id)` | `None` | Delete all mappings for a group (e.g. if the bot is removed) |

`ForumSetupError` — raised by `setup_forum_topics` on Telegram API failure. Inspect `is_permission_error` to tell the user to grant **Manage Topics**.

### `detect_expert_topic()` — `kaia/core/expert_detector.py`

Rule-based expert suggestion from general chat.

```python
detect_expert_topic(message, response, user_id=None) -> dict | None
# returns {"channel_id": "hevn", "suggestion": "..."} or None
```

Requires 2+ keyword matches to avoid false positives. Tracks per-user suggestion history to avoid nagging.

---

## Expert System

### `BaseExpert` — `kaia/experts/base.py`

Abstract base class for all expert channels.

| Method | Returns | Description |
|--------|---------|-------------|
| `handle(user, message, channel)` | `SkillResult` | **Abstract.** Process a message in this channel |
| `get_conversation_history(user_id, channel_id, limit=20)` | `list[dict]` | Recent channel messages as `[{role, content}, ...]` |
| `save_messages(user_id, channel_id, user_msg, assistant_msg)` | `None` | Save both sides of an exchange |
| `run_background_extraction(user_id, channel_id, messages)` | `None` | Fire-and-forget channel memory extraction |
| `generate_onboarding(user, channel, combined_context)` | `str` | First-visit greeting with top knowledge gap questions |
| `format_response_footer(channel)` | `str` | `"---\n💰 Hevn — Financial Advisor | /exit to return to KAIA"` |

### `PlaceholderExpert` — `kaia/experts/placeholder.py`

Default expert. Uses the channel's persona from DB with no specialized skills — all commands work immediately with in-character responses.

### Expert Registry — `kaia/experts/__init__.py`

```python
register_expert(channel_id, expert_cls) -> None
get_expert(channel_id, ai_engine) -> BaseExpert | None
```

`HevnExpert` is registered for `CHANNEL_HEVN` (CH-2). The other 3 non-general channels still resolve to `PlaceholderExpert` and will be overridden in CH-3 / CH-4 / CH-5.

---

## Budget Skill — `kaia/skills/budget/`

### Parser — `kaia/skills/budget/parser.py`

| Function | Returns | Description |
|----------|---------|-------------|
| `parse_transaction(ai_engine, message, currency="PHP")` | `dict \| None` with `amount, type, category, description, date` | Parse a single natural-language line into a transaction. Tolerates verbose descriptions ("Tiktok Shop Elyse essentials 350 pesos") and dash/colon separators ("140 - Dishwashing Liquid"). Strips routing verbs like "log into expenses". |
| `parse_bulk_transactions(ai_engine, message, currency="PHP")` | `list[dict]` | Parse a multi-line block (header lines like "log these expenses:" are skipped). Each line is parsed concurrently via `parse_transaction`. Returns only successfully-parsed transactions. |
| `parse_budget_limit(ai_engine, message, currency="PHP")` | `dict \| None` with `category, amount` | Parse a budget limit request. |

### Handler routing — `kaia/skills/budget/handler.py`

Order of precedence in `BudgetSkill.handle`:
1. Undo → list limits → delete limit → set limit → comparison
2. **Log intent** (`_is_log_request`) — messages starting with `log`, `add to expense(s)`, `record`, `paid`, `spent`, `bought`, OR any multi-line block with ≥2 numeric lines (`_is_bulk_entry`). Wins over summary so "log into expenses ..." logs correctly.
3. Summary (`_is_summary_request`) — "summary", "how much", "spending", "expenses", etc.
4. Fallback: try to log as a single transaction.

### Prompts & formatters — `kaia/skills/budget/prompts.py`

| Function | Description |
|----------|-------------|
| `build_parse_prompt(currency, today)` | Single-line parser prompt |
| `build_budget_limit_parse_prompt(currency)` | Budget limit parser prompt |
| `build_summary_prompt(period, transaction_data, currency_symbol)` | Summary narrative prompt |
| `format_transaction_confirmation(amount, type, category, description, currency_symbol)` | Single log confirmation |
| `format_bulk_log_response(logged, failed, currency_symbol)` | Bulk log — per-category breakdown with totals and a "couldn't parse N" tail when some lines failed |
| `format_budget_warning(category, spent, limit, currency_symbol)` | Budget-limit alert string |

---

## Hevn Expert (Phase CH-2)

### `HevnExpert` — `kaia/experts/hevn/expert.py`

Replaces `PlaceholderExpert` for `channel_id = "hevn"`.

| Method | Returns | Description |
|--------|---------|-------------|
| `handle(user, message, channel)` | `SkillResult` | Main route: first-visit → schedule digest → intent → specialized skill OR persona response |
| `_run_health(user_id, currency)` | `str` | Run `FinancialHealthSkill` and format report |
| `_run_goals(user, message, currency)` | `str` | Create a goal (if parseable) or show goals overview |
| `_run_bills(user, message, currency)` | `str` | Upcoming view, add-bill (if parseable), or full list |
| `_run_coaching(user_id, currency)` | `str` | Pattern + waste analysis combined |
| `_persona_response(user, message, channel, intent)` | `AIResponse` | AI reply with Hevn's system prompt + budget + goals + gap context |

### Hevn's skills — `kaia/experts/hevn/skills/`

| Class | Key Methods |
|-------|-------------|
| `FinancialHealthSkill` | `assess(user_id, currency) -> dict` / `format_health_report(assessment, currency)` |
| `BudgetCoachingSkill` | `analyze_patterns(user_id, period_days)` / `identify_waste(user_id)` / formatters |
| `GoalsManagerSkill` | `create_goal` / `update_progress` (returns `(goal, milestones_hit)`) / `get_goals` / `project_timeline` / `suggest_allocation(user_id, available)` / `format_goals_overview` |
| `BillsTrackerSkill` | `add_bill` / `list_bills` (adds `next_due`) / `get_upcoming(days)` / `calculate_monthly_total` / `identify_forgotten_subscriptions` / `mark_paid` |
| `MarketTrendsSkill` | `get_bsp_rate` / `get_psei_snapshot` / `get_usd_php_rate` / `get_financial_news_ph` / `explain_impact(ai, topic, user_profile_text)` |
| `EducationSkill` | `get_user_level(user_id)` / `explain_topic(ai, user_id, topic)` / `suggest_next_topic` / `quiz_user` |
| `ProactiveAlertsSkill` | `generate_weekly_digest(user_id, currency)` / `check_spending_alerts` / `check_goal_milestones` / `handle_salary_received(user_id, amount, currency)` |

### Hevn's parsers — `kaia/experts/hevn/parser.py`

| Function | Returns |
|----------|---------|
| `classify_hevn_intent(ai, message)` | One of `health_assessment` / `budget_coaching` / `goals` / `bills` / `market_trends` / `education` / `general_chat`. Advice-style questions (`ADVICE_MARKERS`: "how much should", "should i ", "what's a good", "is my ", "do you recommend", "what would you") win over all other short-circuits and return `general_chat`, so Hevn answers from her persona instead of hitting the goals list. |
| `parse_goal_creation(ai, message)` | `dict \| None` with `name, target, deadline, monthly, priority`. Caller can prepend recent conversation context to help the model resolve references like "set this as our first goal". |
| `parse_bill_creation(ai, message)` | `dict \| None` with `name, amount, due_day, category, recurrence` |

### Hevn's extractor — `kaia/experts/hevn/extractor.py`

```python
await hevn_extract_and_save(ai_engine, user_id, conversation_messages) -> int
```

Delegates to `channel_extract_and_save(channel_id="hevn", ...)` and then mirrors entries whose category is in `{income_info, debt_info, savings, retirement, insurance, goals}` into the shared `user_profile` table under category `"finances"`.

### Scheduler hooks — `kaia/core/scheduler.py`

| Function | Description |
|----------|-------------|
| `schedule_hevn_weekly_digest(user_id, telegram_id, timezone)` | Register the Sunday 09:00 digest job; called on first `/hevn` visit |
| `cancel_hevn_weekly_digest(user_id)` | Remove the job |
| `_fire_hevn_digest(...)` | Internal cron callback — generates digest via `ProactiveAlertsSkill` and routes to the forum topic or DM |

### New data models — `kaia/database/models.py`

```python
@dataclass class FinancialGoal:
    user_id, name, target_amount
    id="", current_amount=Decimal("0"), monthly_contribution=None
    deadline=None, priority=1, status="active", created_at=None, updated_at=None

@dataclass class RecurringBill:
    user_id, name, amount
    id="", category=None, due_day=None, recurrence="monthly"
    is_active=True, last_paid=None, notes=None, created_at=None
```

### New query functions — `kaia/database/queries.py`

| Function | Returns |
|----------|---------|
| `create_financial_goal(...)` | `FinancialGoal` |
| `get_financial_goals(user_id, status=None)` | `list[FinancialGoal]` |
| `get_financial_goal_by_id(goal_id)` | `FinancialGoal \| None` |
| `update_financial_goal(goal_id, **fields)` | `FinancialGoal` |
| `delete_financial_goal(goal_id)` | `None` |
| `create_recurring_bill(...)` | `RecurringBill` |
| `get_recurring_bills(user_id, active_only=True)` | `list[RecurringBill]` |
| `get_recurring_bill_by_id(bill_id)` | `RecurringBill \| None` |
| `update_recurring_bill(bill_id, **fields)` | `RecurringBill` |
| `delete_recurring_bill(bill_id)` | `None` |

---

## Data Models — `kaia/database/models.py`

```python
@dataclass class Channel:
    channel_id, name, character_name, role, personality, system_prompt
    emoji="", is_active=True, created_at=None

@dataclass class UserChannelState:
    user_id, active_channel="general", id="", switched_at=None

@dataclass class ChannelProfileEntry:
    user_id, channel_id, category, key, value
    id="", confidence=0.5, source="inferred", updated_at=None

@dataclass class ChannelConversation:
    user_id, channel_id, role, content
    id="", created_at=None
```

---

## Database Query Functions — `kaia/database/queries.py`

| Function | Returns |
|----------|---------|
| `get_user_channel_state(user_id)` | `str` |
| `set_user_channel_state(user_id, channel_id)` | `None` |
| `get_channel_by_id(channel_id)` | `Channel \| None` |
| `get_all_active_channels()` | `list[Channel]` |
| `get_channel_profile(user_id, channel_id)` | `list[ChannelProfileEntry]` |
| `upsert_channel_profile(user_id, channel_id, category, key, value, confidence, source)` | `None` |
| `delete_channel_profile_entry(user_id, channel_id, category, key)` | `None` |
| `save_channel_conversation(user_id, channel_id, role, content)` | `None` |
| `get_channel_conversations(user_id, channel_id, limit=20)` | `list[ChannelConversation]` |
| `count_channel_conversations(user_id, channel_id)` | `int` |
