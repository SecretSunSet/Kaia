# Agentic OS — Design

> Status: R-1 (BaseAgent refactor) — design locked, infra phases pending.
> Owner: EJay. Last updated: 2026-05-14.

## Goal

Evolve KAIA from a single Telegram bot with internal "expert channels" into a
**mesh of independent agent bots** that share one user, talk to each other
visibly, and are coordinated by a slim KAIA-concierge.

## Topology

| Bot account            | Identity                                | Process            |
|------------------------|-----------------------------------------|--------------------|
| `@KaiaConciergeBot`    | KAIA — orchestrator, briefings, digests | concierge service  |
| `@HevnFinanceBot`      | Hevn — financial advisor                | hevn service       |
| `@MakubexTechBot`      | MakubeX — tech lead                     | makubex service    |
| `@KazukiInvestBot`     | Kazuki — investment manager (CH-4)      | kazuki service     |
| `@AkabaneTradeBot`     | Akabane — trading strategist (CH-5)     | akabane service    |

Single monorepo, separate Railway services, one Telegram bot token per agent.

## Runtime layers

```
kaia/
├── agent_runtime/   # BaseAgent, AgentContext, PeerCallError (R-1)
├── bus/             # Postgres LISTEN/NOTIFY pub/sub (R-3)
├── protocol/        # A2A envelope: {from, to, conversation_id, visibility, intent, payload} (R-3)
├── concierge/       # KAIA's slim orchestrator (R-2)
├── experts/         # Hevn, MakubeX, ... subclass BaseAgent
├── skills/          # shared skill library
└── services/        # one entry script per bot (R-4): run_kaia.py, run_hevn.py, ...
```

## Inter-agent protocol (A2A)

Envelope (R-3):

```json
{
  "envelope_id": "uuid",
  "conversation_id": "uuid",
  "from": "hevn",
  "to": "makubex",
  "user_id": "uuid",
  "intent": "consult",
  "visibility": "user_visible",
  "payload": { "question": "...", "context": "..." }
}
```

- **visibility**: `user_visible` (default) — relayed back into the user's
  thread; `internal` — only logged.
- Default per the user decision: **all peer calls are user_visible.**

Bus carrier: **Postgres LISTEN/NOTIFY** on the existing Supabase database.
No new infra. Each agent subscribes to channel `agent:<agent_id>`.

## Memory model

| Scope                          | Owner         | Read access                                  |
|--------------------------------|---------------|----------------------------------------------|
| `channel_profile` (per-expert) | That expert   | Private by default; grant on `peer_call`     |
| `user_profile` (shared)        | All           | Read-all; only concierge writes summaries    |
| `agent_conversations` (R-3)    | bus           | Concierge + participating agents             |
| `agent_messages` (R-3)         | bus           | Same as conversation                         |

No schema change in R-1.

## Migration phases

| Phase | Deliverable                                                              | User-visible? |
|-------|--------------------------------------------------------------------------|---------------|
| R-1   | `BaseAgent` runtime + design doc (this plan)                             | No            |
| R-2   | Concierge code split: `kaia/concierge/` owns general flow + onboarding   | No            |
| R-3   | Postgres LISTEN/NOTIFY bus + A2A protocol + Hevn↔MakubeX peer_call demo  | Yes           |
| R-4   | Per-bot Telegram tokens, separate Railway services                       | Yes (major)   |
| R-5   | Cross-expert weekly digest via concierge; full mesh                      | Yes           |

CH-3 (MakubeX skills), CH-4 (Kazuki), CH-5 (Akabane) continue on top of
this — each becomes "add a new agent" not "add an expert to the monolith".

## Decisions locked

- Bus: **Postgres LISTEN/NOTIFY on Supabase** (no new broker).
- Deploy: **Railway services, one per bot.**
- Inter-agent visibility: **default user_visible.**
- KAIA role: **concierge / orchestrator**, no domain-expert duties.
- Migration order: R-1 → R-2 → R-3 → R-4 → R-5.

## Open questions (not blockers for R-1)

- Should the concierge own onboarding for *all* agents, or each agent owns
  its own first-visit flow? (Today: each expert owns it.)
- Rate limiting: per-user across all agents, or per-bot? (Cost concern at R-4.)
- Should `channel_profile` ever be readable peer-to-peer without `peer_call`?
