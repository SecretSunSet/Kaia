# Skills & Expert Channels

## General KAIA Skills

These run in the general channel through the intent detector + skill router:

| Skill | Triggers | Description |
|-------|----------|-------------|
| `chat` | General conversation | Q&A using user profile context |
| `memory` | "What do you know about me?", "Remember that..." | Profile queries + explicit storage |
| `reminders` | "Remind me..." | Create, list, edit, cancel reminders |
| `budget` | "Spent ₱500...", "How much did I spend?" | Log transactions, summaries, budget limits |
| `briefing` | "/briefing", "morning update" | Daily briefing with weather, news, agenda |
| `web_browse` | "Search for...", "What's the weather?" | Web search + summary |

---

## Expert Channels (Phase CH-1)

The team. All 4 channels work immediately via `PlaceholderExpert` — they respond in character using the channel persona from the DB. Specialized skills ship in subsequent phases.

| Command | Name | Role | Personality |
|---------|------|------|-------------|
| — (default) | 👑 KAIA | Team Lead | Warm, adaptive, main assistant. Routes to experts when relevant. |
| `/hevn` | 💰 Hevn | Financial Advisor | Business-minded, money-savvy, caring but direct. Knows PH finances. |
| `/kazuki` | 📈 Kazuki | Investment Manager | Elegant, strategic, patient. Long-term thinker, calm under volatility. |
| `/akabane` | ⚔️ Akabane | Trading Strategist | Surgical precision, fast execution, safety-first. Confirms every order. |
| `/makubex` | 🔧 MakubeX | Tech Lead / CTO | Systems thinker, hacker mindset, teaches at your level. |

### Meta-commands

| Command | Action |
|---------|--------|
| `/team` | Show full roster (topic-based layout in forum mode) |
| `/exit` | Return to general KAIA (DM mode only) |
| `/setup_forum` | Create expert topics in a forum-enabled group (CH-1.1) |

### Channel switching — DM vs Forum (CH-1.1)

| Mode | How the active channel is chosen | Where the reply goes |
|------|----------------------------------|----------------------|
| DM (private chat) | `/hevn`, `/kazuki`, …, `/exit` mutate `user_channel_state` | The DM |
| Forum group | The topic the message was posted in (via `forum_topic_mappings`) | Same topic (`message_thread_id` preserved) |
| Regular group (non-forum) | Ignored | — |

In forum mode the command-based switches are unnecessary — each expert has their own thread. The expert commands still work but redirect the user to the relevant topic rather than switching persistent state.

---

## Phase CH-1 Behavior (PlaceholderExpert)

Each expert channel, via `PlaceholderExpert`:

1. **Loads the channel's persona** from `channels.system_prompt` in the DB
2. **Loads combined context**: shared user profile + channel-specific profile
3. **First visit**: generates an in-character introduction with the top 2–3 knowledge gap questions woven in
4. **Subsequent visits**: responds in character using channel conversation history + one natural knowledge gap question (max)
5. **Saves conversation** to `channel_conversations` (separate from general KAIA history)
6. **Background extraction** with domain-focused prompt — only extracts domain-relevant facts (financial facts for Hevn, tech facts for MakubeX, etc.) to `channel_profile`
7. **Footer**: every response ends with `---\n💰 Hevn — Financial Advisor | /exit to return to KAIA`

---

## Specialized Skills Roadmap

| Phase | Expert | Status | Skills |
|-------|--------|--------|--------|
| CH-2 | Hevn | ✅ Done | Health assessment, budget coaching, goals, bills, market trends, education, proactive alerts |
| CH-3 | MakubeX | ⏳ Next | Code review, architecture, debugging, tech coaching |
| CH-4 | Kazuki | ⏳ Planned | Portfolio tracking, allocation, market research |
| CH-5 | Akabane | ⏳ Planned | Order management (Binance), risk control, trade journal |

Each phase replaces `PlaceholderExpert` in the registry with the specialized class.

---

## Hevn — Financial Advisor (Phase CH-2)

Replaces `PlaceholderExpert` with `HevnExpert` (`experts/hevn/expert.py`). Routing on every message:

1. **First-visit onboarding** — in-character intro, asks for income to bootstrap the profile; schedules the weekly digest.
2. **Intent classification** (`experts/hevn/parser.py`) — keyword short-circuit with AI JSON fallback, across 7 intents.
3. **Specialized routes** — for `health_assessment`, `goals`, `bills`, `budget_coaching` Hevn calls the skill directly and returns a deterministic, numbers-backed response.
4. **Persona-driven response** — for `market_trends`, `education`, `general_chat` Hevn replies via the AI with a system prompt enriched by the user's budget summary, goals overview, and current knowledge gap.
5. **Fire-and-forget extraction** — `hevn_extract_and_save` extracts financial facts into `channel_profile` and mirrors income/debt/savings/retirement/insurance/goals into the shared `user_profile` under category `"finances"`.

### The 7 Skills

| Skill | File | Highlights |
|-------|------|-----------|
| Financial Health | `skills/health_assessment.py` | Weighted 1–100 score across 5 components (savings 25%, debt 25%, emergency fund 25%, income stability 15%, expense control 10%). Uses 90-day transactions + Hevn's channel_profile. |
| Budget Coaching | `skills/budget_coaching.py` | Pattern analysis (top categories, weekend/weekday split, spike days, repeated vendors). Waste detection: food delivery, subscriptions > 5% of income, recurring micro-vendors. |
| Goals Manager | `skills/goals_manager.py` | Create/update/list goals; project timeline (on-track vs needed monthly); milestone celebrations at 25/50/75/100%; priority-weighted allocation suggestions. |
| Bills Tracker | `skills/bills_tracker.py` | Bills with computed `next_due`, 7-day upcoming view, monthly-total (normalized across recurrences), forgotten-subscription detection via transaction cross-reference. |
| Market Trends | `skills/market_trends.py` | BSP rate, PSEi, USD/PHP via web search; PH-filtered financial news; personalized impact explanations. |
| Education | `skills/education.py` | Topic catalog (basics/saving/investing/ph_specific/insurance/advanced); level inference from profile; level-adapted explanations; next-topic suggestions. |
| Proactive Alerts | `skills/proactive.py` | Weekly digest (Sunday 09:00), spending alerts, goal milestones, salary allocation on income-salary events. |

### Hevn Shortcut Commands

| Command | Action |
|---------|--------|
| `/hevn_health` | Run `FinancialHealthSkill` and reply with the report |
| `/hevn_goals` | Reply with the formatted goals overview |
| `/hevn_bills` | Reply with upcoming (7-day) bills, falling back to the full bill list |
| `/hevn_digest` | Generate the weekly digest on demand |

All four work in DM and Forum Topics mode (they respect `message_thread_id`).

### Scheduled Weekly Digest

- Registered on the user's first `/hevn` visit via `core.scheduler.schedule_hevn_weekly_digest`
- Fires every Sunday at 09:00 in the user's timezone (`CronTrigger(day_of_week='sun', hour=9)`)
- Delivered to Hevn's forum topic if `ForumManager.get_topic_for_channel` returns one, else DM with a `/hevn to discuss` footer

### Budget Tracker Integration

When the Budget skill logs an income transaction with category `salary`, it calls `_hevn_salary_allocation`. If the user has met Hevn (checked via `count_channel_conversations > 0`), `ProactiveAlertsSkill.handle_salary_received` suggests a 30% split across active goals and the suggestion is appended to the transaction confirmation.
