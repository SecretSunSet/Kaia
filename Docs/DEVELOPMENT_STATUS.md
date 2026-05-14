# Development Status

## Phase Progress

### Agentic OS Migration

| Phase | Status        | Scope                                                            |
|-------|---------------|------------------------------------------------------------------|
| R-1   | ✅ Complete   | `BaseAgent` runtime + design doc                                |
| R-2   | ⏳ Planned    | Concierge code split (`kaia/concierge/`)                        |
| R-3   | ⏳ Planned    | Postgres LISTEN/NOTIFY bus + A2A protocol + peer_call demo      |
| R-4   | ⏳ Planned    | Per-bot Telegram tokens; separate Railway services              |
| R-5   | ⏳ Planned    | Cross-expert weekly digest via concierge; full mesh             |

See [`AGENTIC_OS/DESIGN.md`](AGENTIC_OS/DESIGN.md) for the full design.

### Expert Channel Phases

| Phase | Status | Scope |
|-------|--------|-------|
| Phase 1 | ✅ Complete | Core bot: 6 skills, voice, AWS deployment |
| Phase CH-1 | ✅ Complete | Expert Channel System — Infrastructure |
| Phase CH-1.1 | ✅ Complete | Telegram Forum Topics support (dual-mode routing) |
| **Phase CH-2** | ✅ **Complete** | **Hevn — Financial Advisor (7 skills, digest, salary allocation)** |
| Phase CH-3 | ⏳ Next | MakubeX — Tech Lead skills |
| Phase CH-4 | ⏳ Planned | Kazuki — Investment Manager skills |
| Phase CH-5 | ⏳ Planned | Akabane — Trading Strategist skills |

---

## Phase CH-2 Deliverables

✅ Migration `004_hevn.sql` — `financial_goals`, `recurring_bills` tables + indexes + RLS
✅ New dataclasses `FinancialGoal`, `RecurringBill` and CRUD in `database/queries.py`
✅ `experts/hevn/` package: `expert.py`, `prompts.py`, `parser.py`, `extractor.py`
✅ Seven specialized skills under `experts/hevn/skills/`:
  `health_assessment`, `budget_coaching`, `goals_manager`, `bills_tracker`,
  `market_trends`, `education`, `proactive`
✅ `HevnExpert` registered for `CHANNEL_HEVN` in the expert registry
✅ Weekly digest scheduler (`schedule_hevn_weekly_digest`) — Sunday 09:00 user's TZ
✅ Digest respects forum topic routing, falls back to DM with footer
✅ Budget Tracker integration — proactive salary-allocation suggestion
✅ Channel-specific fact mirror: income/debt/savings/goals facts mirrored to shared `user_profile` under `finances`
✅ Four shortcut commands: `/hevn_health`, `/hevn_goals`, `/hevn_bills`, `/hevn_digest`
✅ `/reset` cascades through `financial_goals` and `recurring_bills`
✅ Docs updated: CHANGELOG, API_REFERENCE, ARCHITECTURE, DATABASE, SKILLS, DEVELOPMENT_STATUS

## Phase CH-2 Testing Checklist

- [ ] Run `004_hevn.sql` in Supabase
- [ ] `/hevn` (first visit) — Hevn's onboarding, weekly digest scheduled on first visit
- [ ] "I earn ₱45,000/month" — fact extracted to Hevn's channel_profile and mirrored to shared profile under `finances`
- [ ] "How am I doing financially?" — full weighted health report
- [ ] "Where am I wasting money?" — waste report with specific suggestions
- [ ] "I want to save ₱50,000 for emergency fund by Dec" — goal created, confirmation message
- [ ] `/hevn_goals` — formatted goals overview
- [ ] "Remind me my Netflix is ₱549 on the 20th" — bill added
- [ ] `/hevn_bills` — upcoming/active bills
- [ ] "What's happening with interest rates?" — market-trends persona response
- [ ] "Explain MP2" — level-adapted education, topic tracked in profile
- [ ] `/hevn_digest` — full digest on demand
- [ ] Log salary via budget ("received ₱45,000 salary") — Hevn appends allocation suggestion
- [ ] Wait for Sunday 09:00 user TZ — digest delivered (to Hevn's topic in forum, or DM)
- [ ] `/reset` + CONFIRM DELETE — `financial_goals` and `recurring_bills` deleted too

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

After Phase CH-2:

- Hevn is the first fully realized expert — 7 specialized skills, own extractor, scheduled weekly digest, budget tracker integration.
- Kazuki, Akabane, MakubeX continue on `PlaceholderExpert` until their respective phases.
- Shared `user_profile` under category `finances` is Hevn's cross-expert hand-off — Kazuki (CH-4) will read these facts when offering investment advice.
- Phase CH-3 (MakubeX — Tech Lead) is next.
