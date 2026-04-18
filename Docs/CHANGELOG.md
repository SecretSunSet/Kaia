# Changelog

## [2026-04-19] Phase CH-1.1 — Forum Topics Support

### Added
- **Dual-mode operation**: KAIA now runs in either DM mode (existing `/hevn`, `/exit` command switching) or Forum Topics mode (each expert gets a dedicated sub-thread in a Telegram forum group). The message handler auto-detects the mode per incoming message.
- **New `forum_topic_mappings` table** (migration `003_forum_topics.sql`) mapping `(chat_id, channel_id) ↔ topic_id`.
- **`/setup_forum`** command — one-time setup that creates four expert topics in a forum-enabled group and saves the mappings.
- **`ForumManager`** (`kaia/core/forum_manager.py`) — create topics via `bot.create_forum_topic`, look up channel-for-topic / topic-for-channel, store mappings.
- **Forum-aware routing**: in a forum group the user's current topic determines which expert replies; no per-user channel state is used. Expert replies are sent with `message_thread_id` so they stay in the correct topic.
- **Configuration flag**: `FORUM_MODE_ENABLED` (default `True`) in `config/settings.py`.

### Changed
- `bot/telegram_bot.py` — `handle_message` and `handle_voice` now branch on forum vs DM; a shared `_handle_expert_turn()` helper unifies expert dispatch.
- `/team` renders a topic-based roster in forum mode.
- Expert commands (`/hevn`, `/kazuki`, `/akabane`, `/makubex`) in forum mode redirect the user to the expert's topic instead of switching DM state.
- `/exit` in forum mode explains that topics replace explicit switching.

### Notes
- Bot must be a group admin with the **Manage Topics** permission before `/setup_forum` can create threads; the command reports a clear error if that permission is missing.
- Migration `003_forum_topics.sql` must be run in Supabase before this version is deployed.

---

## Phase CH-1 — Expert Channel System (Infrastructure)

### Added
- **Expert Channel System** foundation: KAIA now has a team of 4 named AI experts (Hevn, Kazuki, Akabane, MakubeX) plus herself as team lead.
- **New database tables**: `channels`, `user_channel_state`, `channel_profile`, `channel_conversations` (migration `002_channels.sql`).
- **Channel commands**: `/hevn`, `/kazuki`, `/akabane`, `/makubex`, `/exit`, `/team`.
- **Per-channel memory**: separate memory profile per expert via `channel_profile` table.
- **Per-channel conversation history**: separate message history per expert via `channel_conversations`.
- **Knowledge gap detection**: priority-based per-channel required knowledge lists drive proactive questioning (one question per response max).
- **Expert suggestions in general chat**: KAIA gently suggests relevant experts when a topic matches their domain (rule-based keyword matching, no extra AI cost).
- **PlaceholderExpert**: generic expert that uses channel persona from DB — all commands work immediately with the correct in-character response, even before specialized skills ship.

### New Modules
- `kaia/core/channel_manager.py` — channel switching state
- `kaia/core/channel_memory.py` — per-channel memory + knowledge gap tracking
- `kaia/core/channel_extractor.py` — domain-focused fact extraction per channel
- `kaia/core/expert_detector.py` — suggest experts from general chat
- `kaia/experts/base.py` — `BaseExpert` abstract class
- `kaia/experts/__init__.py` — expert registry
- `kaia/experts/placeholder.py` — default expert using channel persona

### Changed
- `bot/telegram_bot.py` — `handle_message` and `handle_voice` now check active channel and route to expert system for non-general channels; general flow now suggests experts when chat skill handles financial/investment/trading/tech topics.
- `bot/commands.py` — `/status` shows active channel + channel stats; `/export` includes channel data; `/reset` deletes all channel data.
- `config/constants.py` — added channel IDs, emojis, and `CHANNEL_REQUIRED_KNOWLEDGE` dict.
- `database/models.py` — added `Channel`, `UserChannelState`, `ChannelProfileEntry`, `ChannelConversation` dataclasses.
- `database/queries.py` — ~10 new channel-related query functions.

### Notes
- Phase CH-1 is infrastructure only. Each expert's specialized skills (Hevn's budget coaching, MakubeX's code review, etc.) ship in subsequent phases (CH-2 through CH-5).
- Migration `002_channels.sql` must be run in Supabase SQL editor before deploying.

---

## Phase 1 — Initial Release

- Telegram bot with 6 skills: chat, memory, reminders, budget, briefing, web search
- Voice input (Groq Whisper) and voice output (edge-tts)
- Deployed on AWS EC2 with Docker + systemd + GitHub Actions CI/CD
