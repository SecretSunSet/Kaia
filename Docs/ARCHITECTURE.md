# Architecture — Expert Channel System

## Overview

KAIA runs as a Telegram bot with two parallel conversation paths:

1. **General KAIA flow** — intent detection → skill router → skill handler
2. **Expert channel flow** — direct route to `BaseExpert` subclass based on user's active channel

The channel router sits **above** the skill router. When a user is in a non-general channel, the intent detector is bypassed entirely.

## Dual-Mode Operation (CH-1.1)

KAIA detects the chat type on every incoming message and routes accordingly:

```
              incoming message
                     │
        ┌────────────┴────────────┐
        │                         │
   chat.is_forum?               DM (private)
        │                         │
        ▼                         ▼
  topic_id → channel         user_channel_state
  (ForumManager)             (ChannelManager)
        │                         │
        ▼                         ▼
  expert.handle(...)         expert.handle(...)
  reply with                 reply in single chat
  message_thread_id
```

- **DM mode**: `user_channel_state.active_channel` tracks which expert the user is talking to. `/hevn`, `/exit`, etc. mutate that state.
- **Forum mode**: the topic *is* the channel. No per-user state; the bot looks up the channel via `forum_topic_mappings.topic_id → channel_id` and replies with `message_thread_id` so the reply lands in the same topic.
- **Regular (non-forum) groups**: ignored for now — the bot does not respond.

---

## Message Flow

```
User message arrives
    │
    ▼
handle_message() (telegram_bot.py)
    │
    ├── Rate limit check
    ├── Get/create user
    │
    ├── channel_mgr.get_active_channel(user_id) ─┐
    │                                            │
    ├── if active != "general":                  │
    │       channel = get_channel_info(...)      │
    │       expert = get_expert(active, ai_engine)
    │              or PlaceholderExpert(ai_engine)
    │       result = await expert.handle(user, msg, channel)
    │       reply with truncated result.text
    │       return  ← EXPERT FLOW ENDS HERE
    │
    ├── else: (general KAIA flow)
    │       profile_context = memory_mgr.load_profile_context()
    │       history = get_recent_conversations(20)
    │       result = skill_router.route(...)
    │       save_conversation(user msg + bot reply)
    │       reply with truncated result.text
    │       if result.skill_name == "chat":
    │           suggestion = detect_expert_topic(text, response, user_id)
    │           if suggestion:
    │               reply with "💡 Want to connect with ...?"
    │       memory_mgr.run_background_extraction()
    │
    └── Track AI usage
```

---

## Channel Switching State Machine

```
       ┌──────────────────────────────────────┐
       │                                      │
       ▼                                      │
    ┌───────┐  /hevn, /kazuki, etc.  ┌────────────┐
    │general│ ─────────────────────▶ │expert ch.  │
    └───────┘                        └────────────┘
       ▲                                      │
       │ /exit                                │ /hevn, /kazuki...
       └──────────────────────────────────────┘
              (or any other expert command)
```

- State is stored in `user_channel_state.active_channel`
- Default is `"general"` (no row exists = treated as general)
- Switching clears the expert suggestion history so KAIA doesn't nag after user takes the suggestion

---

## Memory Layers

```
┌─────────────────────────────────────────────────────────────┐
│ SHARED USER PROFILE (user_profile table)                    │
│ — name, age, general preferences, habits                    │
│ — used by general KAIA + all experts                        │
└─────────────────────────────────────────────────────────────┘
         │
         ├────────────┬────────────┬────────────┬────────────┐
         ▼            ▼            ▼            ▼            ▼
    ┌─────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌─────────┐
    │hevn     │  │kazuki  │  │akabane │  │makubex │  │(general) │
    │channel_ │  │channel_│  │channel_│  │channel_│  │ (no      │
    │profile  │  │profile │  │profile │  │profile │  │  channel │
    │         │  │        │  │        │  │        │  │  profile)│
    └─────────┘  └────────┘  └────────┘  └────────┘  └─────────┘
    Financial    Investment   Trading    Tech        —
    facts        facts        facts      facts
```

Conversations are also siloed per channel (`channel_conversations`) — Hevn's history ≠ MakubeX's ≠ general.

---

## Knowledge Gap System

Each expert channel defines a required knowledge list in `config/constants.py::CHANNEL_REQUIRED_KNOWLEDGE`:

```python
CHANNEL_HEVN = [
    ("income_info", "monthly_income", 1, "What's your monthly income?"),
    ("debt_info", "active_debts", 1, "Do you have any loans or credit card debt?"),
    ...
]
```

Each entry: `(category, key, priority, question_text)`.

`ChannelMemoryManager.get_top_gap()` returns the single highest-priority missing item. The expert system injects this into the prompt with instructions to "work ONE natural question about it into your response if appropriate." One question per response, maximum.

---

## Expert Class Hierarchy

```
BaseExpert (ABC)
    │
    ├── HevnExpert  ✅ (Phase CH-2 — live)
    │
    └── PlaceholderExpert  ← default for kazuki, akabane, makubex
            │                (will be replaced in CH-3/4/5)
            │
            ├── MakubeXExpert (Phase CH-3)
            ├── KazukiExpert  (Phase CH-4)
            └── AkabaneExpert (Phase CH-5)
```

`BaseExpert` provides: conversation history access, message saving, background extraction, onboarding generation, response footer formatting.

Subclasses only need to implement `handle()`.

---

## Expert Suggestions (General Chat)

When KAIA (general channel) handles a message via the `chat` skill, `detect_expert_topic()` runs on the message + response:

1. Count keyword matches per expert (keyword lists in `expert_detector.py`)
2. Require 2+ matches to suggest (reduces false positives)
3. Suggest the best match
4. Track suggestion in memory — never suggest the same expert twice to the same user (until bot restart)

This is **gentle** — KAIA never auto-switches, just suggests. User stays in control.

---

## Hevn — Data Flow (Phase CH-2)

```
                        User message in Hevn channel
                                    │
                                    ▼
                       HevnExpert.handle(user, msg, channel)
                                    │
                ┌───────────────────┼──────────────────────┐
                ▼                   ▼                      ▼
       first visit?           intent classify       persona AI reply
       ├─ Yes:                ├─ health_assessment  (market_trends,
       │  onboarding          ├─ budget_coaching     education,
       │  + schedule          ├─ goals               general_chat)
       │    weekly digest     ├─ bills               │
       │                      │                      ▼
       │                      ▼                 AIEngine.chat
       │              run specialized skill     + save messages
       │              (numbers-backed reply)    + fire extraction
       │                      │
       │                      ▼
       │              save messages
       │              + fire extraction
       ▼
   reply with footer
```

Read paths:
- **Budget summary**: `get_income_total` / `get_expense_total` / `get_spending_by_category` from the `transactions` table.
- **Goals**: `financial_goals` (CH-2 table).
- **Bills**: `recurring_bills` (CH-2 table).
- **Memory**: shared `user_profile` + Hevn's `channel_profile` slice.

Write paths:
- **Channel history** → `channel_conversations`.
- **Channel facts** → `channel_profile` (Hevn slice).
- **Mirror** → financial facts (`income_info`, `debt_info`, `savings`, `retirement`, `insurance`, `goals`) also written to shared `user_profile` under category `"finances"` so Kazuki (CH-4) can read them.
- **Goals / bills** → dedicated tables via query helpers.

Proactive paths:
- **Weekly digest** — scheduled on first `/hevn` visit; fires every Sunday 09:00 user TZ; delivered to Hevn's forum topic (if any) else DM.
- **Salary allocation** — the Budget skill calls back into Hevn when an income+salary transaction is logged, only if the user has met Hevn.
