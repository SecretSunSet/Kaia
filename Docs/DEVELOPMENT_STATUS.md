# Development Status

## Phase Progress

| Phase | Status | Scope |
|-------|--------|-------|
| Phase 1 | ✅ Complete | Core bot: 6 skills, voice, AWS deployment |
| Phase CH-1 | ✅ Complete | Expert Channel System — Infrastructure |
| **Phase CH-1.1** | ✅ **Complete** | **Telegram Forum Topics support (dual-mode routing)** |
| Phase CH-2 | ⏳ Next | Hevn — Financial Advisor skills |
| Phase CH-3 | ⏳ Planned | MakubeX — Tech Lead skills |
| Phase CH-4 | ⏳ Planned | Kazuki — Investment Manager skills |
| Phase CH-5 | ⏳ Planned | Akabane — Trading Strategist skills |

---

## Phase CH-1.1 Deliverables

✅ Database migration `003_forum_topics.sql` — `forum_topic_mappings` table + RLS
✅ `core/forum_manager.py` — `ForumManager` + `ForumSetupError`
✅ `ForumTopicMapping` dataclass and full CRUD query set in `database/queries.py`
✅ `FORUM_MODE_ENABLED` setting (default True)
✅ `/setup_forum` command with permission-aware error handling
✅ `handle_message` and `handle_voice` auto-detect forum vs DM and route accordingly
✅ Expert replies (`_handle_expert_turn`) respect `message_thread_id`
✅ `/team`, `/hevn`-style commands, `/exit` adapted for forum mode
✅ Docs updated: CHANGELOG, API_REFERENCE, ARCHITECTURE, DATABASE, DEPLOYMENT, CONFIGURATION, SKILLS

## Phase CH-1.1 Testing Checklist

- [ ] Run `003_forum_topics.sql` in Supabase
- [ ] Create a test group, add the bot, make it admin with *Manage Topics*, enable Topics
- [ ] `/setup_forum` — 4 expert topics created
- [ ] Post in 💰 Hevn topic — Hevn replies in that thread (first-visit onboarding)
- [ ] Post in 🔧 MakubeX topic — MakubeX replies in that thread
- [ ] Post in General topic — KAIA replies via the normal skill router
- [ ] `/team` in forum — topic-based roster
- [ ] `/hevn` in forum — redirect message pointing to Hevn's topic
- [ ] `/exit` in forum — explanation message only
- [ ] Voice message inside a topic stays in that topic
- [ ] DM `/hevn` and `/exit` still switch persistent state as before

---

## Phase CH-1 Deliverables

✅ Database migration `002_channels.sql` with 4 new tables + 5 seeded channels
✅ 4 new core modules: `channel_manager`, `channel_memory`, `channel_extractor`, `expert_detector`
✅ Expert system: `BaseExpert` ABC + `PlaceholderExpert` + registry
✅ 6 new bot commands: `/hevn`, `/kazuki`, `/akabane`, `/makubex`, `/exit`, `/team`
✅ Channel routing in `handle_message` and `handle_voice`
✅ Per-channel memory, conversation history, knowledge gaps
✅ Expert topic detection with gentle suggestions in general chat
✅ Updated `/status`, `/export`, `/reset` for channel data
✅ Documentation: CHANGELOG, API_REFERENCE, ARCHITECTURE, DATABASE, SKILLS, CONFIGURATION, DEPLOYMENT

## Phase CH-1 Testing Checklist

- [ ] Run migration `002_channels.sql` in Supabase
- [ ] `/team` — shows full roster with all 5 members
- [ ] `/hevn` (first visit) — in-character onboarding message
- [ ] Send message in Hevn's channel — Hevn-style response with footer
- [ ] `/exit` — back to general KAIA
- [ ] `/hevn` (second visit) — direct greeting, no onboarding
- [ ] Send financial question in general — KAIA suggests Hevn
- [ ] `/makubex` — MakubeX onboarding in distinct tech persona
- [ ] Verify `channel_profile` rows land per expert
- [ ] Verify `channel_conversations` is siloed per expert
- [ ] `/status` — shows active channel + channel stats
- [ ] `/export` — JSON includes channel data
- [ ] `/reset` + CONFIRM DELETE — deletes all channel data too

---

## Architecture Summary

Phase CH-1 ships the foundation — after this phase:

- Users can switch to any of 4 expert channels and the bot responds in character
- Each expert has its own memory profile and conversation history
- Each expert knows what knowledge it still needs about the user and asks naturally
- General KAIA flow is unchanged; new flow only activates when user is in a non-general channel
- No specialized expert skills yet — `PlaceholderExpert` uses AI + persona only

Phase CH-2 through CH-5 will each replace `PlaceholderExpert` for one channel with a full specialized implementation (e.g., `HevnExpert` with budget coaching, savings goal tracking, financial education).
