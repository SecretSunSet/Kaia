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

| Phase | Expert | Skills |
|-------|--------|--------|
| CH-2 | Hevn | Budget coaching, savings goals, financial education |
| CH-3 | MakubeX | Code review, architecture, debugging, tech coaching |
| CH-4 | Kazuki | Portfolio tracking, allocation, market research |
| CH-5 | Akabane | Order management (Binance), risk control, trade journal |

Each phase replaces `PlaceholderExpert` in the registry with the specialized class.
