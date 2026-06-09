# Agentic OS — R-3 Design (Postgres bus + A2A protocol + Hevn↔MakubeX peer-call demo)

> Status: R-3 (design — implementation pending).
> Owner: EJay. Last updated: 2026-06-09.
> Companion docs: [`DESIGN.md`](DESIGN.md) (overall locked architecture), [`PLAN_R1.md`](PLAN_R1.md) (shipped), [`PLAN_R2.md`](PLAN_R2.md) (shipped).

## Goal

Deliver the first **user-visible Agentic OS feature**: a real Postgres-backed inter-agent bus, the A2A envelope protocol, and a working Hevn↔MakubeX peer-call demo where the user watches the mesh happen in their Telegram thread. This phase upgrades the `peer_call(...)` stub from R-1 (raises `PeerCallError`) into a working RPC over Postgres `LISTEN`/`NOTIFY`, and proves cross-agent reasoning is genuinely valuable on the smart-contract / DeFi risk scenario.

Everything ships in **one Python process** (R-4 splits Telegram tokens). The bus is built for the multi-process world from day one — when R-4 lands, each agent service just runs its own listener task; nothing in the bus design changes.

## Locked design decisions (from brainstorming Q1–Q4)

| # | Decision | Rationale |
|---|----------|-----------|
| Q1 | **Bus carrier: asyncpg sidecar.** A second DB client just for the bus, running real Postgres `LISTEN`/`NOTIFY` against the same Supabase project that supabase-py talks to via PostgREST. | supabase-py is a REST client and cannot issue `LISTEN`/`NOTIFY`. asyncpg is the narrowest viable dep. Sets up cleanly for R-4 where each agent process already needs its own listener. |
| Q2 | **`peer_call` is RPC-with-await.** `async def peer_call(target, intent, payload) -> dict` returns the peer's reply payload; 30 s default timeout. | The R-1 stub's signature already commits us to this; the demo's "consult then synthesize" UX needs it; fire-and-forget would produce a disjointed user experience. |
| Q3 | **Demo scenario: Crypto/DeFi safety.** User asks Hevn about stablecoin DeFi yields → Hevn consults MakubeX for smart-contract risk → Hevn synthesizes a financial recommendation. | Strongest mesh value: genuinely needs both finance + tech domains; matches the established personas; provides interesting structured payload (risk profile) to relay user-visibly. |
| Q4 | **Trigger: lightweight LLM classifier in Hevn's `handle()`.** Hevn's handler does a small cheap LLM call first ("does this need MakubeX?") emitting a structured decision; only on a positive emits the `peer_call`. Two LLM calls per consult turn. | Agentic decision-making at low cost. Avoids full tool-calling infrastructure (out of scope). Reliable on the well-scoped DeFi prompt. |
| Q5 | **Relay UX: interleaved attribution.** When `visibility=user_visible`, the user sees three messages: (1) `💰 Hevn → 🔧 MakubeX (consult): <q>`, (2) `🔧 MakubeX → 💰 Hevn (reply): <a>`, (3) `💰 Hevn: <synthesized recommendation>`. | Maximum mesh transparency. The whole point of R-3 being marked "user-visible" in `DESIGN.md` is to show the mesh — interleaving is the demo. |

## Behavior-preservation constraints

R-3 adds behavior; it must not regress R-1 or R-2. The following invariants from prior phases continue to hold:

- All nine R-2 behavior-preservation invariants for the general (concierge) and expert paths.
- `BaseAgent` interface, `agent_id`, `AgentContext` from R-1 are unchanged in signature.
- The Telegram bot stays the only module importing `telegram`.
- supabase-py keeps owning all existing data (users, conversations, channels, channel_profile, reminders, budget, etc.). asyncpg only writes to the two new bus tables.

New R-3 invariants:

1. **Bus startup is a hard prerequisite.** If asyncpg can't connect to Postgres on boot, the bot fails fast with a clear log — it does NOT silently start without the bus.
2. **`visibility=user_visible` envelopes are always rendered.** The bot's user-visible subscriber must produce the attribution message; if rendering fails, log loud, do not silently drop.
3. **No silent drops of peer_call failures.** Timeouts, peer errors, and bus DB write failures all surface to the caller as raised exceptions (`PeerCallTimeoutError`, `PeerCallError`). Hevn catches and falls back gracefully (Section §4).
4. **Late replies after timeout never raise.** The dispatcher drops them with a DEBUG log; the caller's future has already resolved.
5. **Stateful expert-suggestion divergence preserved** (R-2 invariant #2). R-3 does not change `suggest_experts` behavior; peer-call messages relayed to the user are NOT subject to the expert-suggestion follow-up.

## §1 Architecture

```
┌────────────────────────────── single Python process (R-3) ──────────────────────────────┐
│                                                                                          │
│  Telegram → bot → /hevn channel → HevnExpert.handle()                                    │
│        ┌────────────────────────────────────────────────────────────┐                    │
│        │  1. classifier LLM ("need MakubeX?")                       │                    │
│        │  2. if yes:  await self.peer_call("makubex",               │                    │
│        │                                  "smart_contract_risk",    │                    │
│        │                                  payload)  ──┐             │                    │
│        │     else:    answer directly (today's path)  │             │                    │
│        │  3. synthesize: re-prompt with peer reply    │             │                    │
│        └────────────────────────────────────────────────────────────┘                    │
│                          ▲                            │                                  │
│                          │ reply future               ▼ envelope                         │
│           ┌────────── kaia/bus (asyncpg) ──────────────────────┐                         │
│           │  • LISTEN agent:hevn          • LISTEN agent:makubex                         │
│           │  • LISTEN bus:user_visible  (bot subscribes here)  │                         │
│           │  • NOTIFY agent:<to>, <envelope_id>                │                         │
│           │  • In-process future map keyed by envelope_id      │                         │
│           │    for RPC await; 30 s timeout default             │                         │
│           └──────────────┬─────────────────────────────────────┘                         │
│                          │ INSERT (audit + R-4-ready transport)                          │
│                          ▼                            ▲ handle_peer(envelope)            │
│                ┌──── Supabase Postgres ────┐    ┌────────────────────────┐               │
│                │  agent_conversations       │    │  MakubeXExpert         │               │
│                │  agent_messages            │    │   .smart_contract_risk │               │
│                └────────────────────────────┘    └────────────────────────┘               │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

Three subsystems:

- **The bus** (`kaia/bus/`) — asyncpg sidecar. Owns LISTEN/NOTIFY, NOTIFY publish, RPC future correlation, audit-table writes.
- **Hevn's orchestrator** — `HevnExpert.handle()` becomes a three-step flow (classify → optional consult → synthesize). MakubeX gains an inbound peer-intent handler.
- **The bot's user-visible relay** — `bot/telegram_bot.py` subscribes to `bus:user_visible` and renders attribution messages into the user's thread.

Single process today. The bus is designed for the multi-process world: every peer call publishes through Postgres NOTIFY and routes via LISTEN, so it works exactly the same way whether the two agents share a process (R-3) or each have their own (R-4).

## §2 Components

| Module | Responsibility |
|---|---|
| `kaia/bus/__init__.py` | exports `Bus`, `Envelope`, `Visibility`, `PeerCallError`, `PeerCallTimeoutError` |
| `kaia/bus/envelope.py` | `Envelope` dataclass — `envelope_id` (UUID), `conversation_id` (UUID), `from_agent` (str), `to_agent` (str), `user_id` (UUID), `intent` (str), `visibility` (enum), `kind` (enum: `request` / `reply` / `error`), `payload` (dict), `reply_to` (Optional[UUID]), `created_at`. Serialization: `to_dict()` / `from_dict()` for JSONB; required-field enforcement. |
| `kaia/bus/bus.py` | `Bus` class: asyncpg pool (single shared); per-agent LISTEN dispatcher task; NOTIFY publisher; in-process `dict[UUID, asyncio.Future]` for RPC correlation; timeout enforcement (default 30 s); startup/shutdown lifecycle (`start()`, `shutdown()`); intent-handler registration (`register_handler(agent_id, intent, async_fn)`); `publish_user_visible(envelope)` for the bot's relay subscriber. |
| `kaia/database/migrations/006_agent_bus.sql` | creates `agent_conversations`, `agent_messages` tables + indexes. |
| `kaia/agent_runtime/base_agent.py` *(modified)* | replaces R-1 `peer_call(...)` stub with the bus-backed implementation. Adds `register_peer_intent(intent: str, handler: Callable[[Envelope], Awaitable[dict]])` so subclasses bind inbound intent handlers at construction time. Adds `_bus: Bus \| None` injected by the bot at startup. |
| `kaia/experts/hevn/expert.py` *(modified)* | `handle()` becomes the three-step orchestrator. Adds `_classify_consult_intent(message)` (cheap LLM) and `_synthesize_with_consult(message, reply)` (main LLM re-prompt). |
| `kaia/experts/hevn/prompts.py` *(modified)* | adds the classifier prompt and the synthesis prompt. |
| `kaia/experts/makubex/expert.py` *(modified)* | registers `smart_contract_risk` peer-intent handler returning a structured risk profile. |
| `kaia/experts/makubex/prompts.py` *(modified)* | adds the `smart_contract_risk` system prompt. |
| `kaia/bot/telegram_bot.py` *(modified)* | starts the bus in `post_init` (and fails fast on bus error); subscribes to `bus:user_visible` envelopes; renders attribution messages (`💰 Hevn → 🔧 MakubeX (consult): …`) into the user's thread; cancels listener tasks in `post_shutdown`. |
| `kaia/config/settings.py` *(modified)* | adds `DATABASE_URL` env var for the asyncpg DSN (Supabase exposes this — Project Settings → Database → Connection String). Optional override `R3_PEER_CALL_TIMEOUT_SECONDS` (default 30). |
| `kaia/requirements.txt` *(modified)* | adds `asyncpg>=0.29.0`. |

Each module has one clear responsibility and a well-defined interface — same shape as R-1/R-2. The bus interface (`publish`, `subscribe`, `register_handler`, `peer_call`) is small enough to swap carriers later (e.g., if R-5+ moves to NATS) without touching agents.

## §3 Data flow — the DeFi demo, end-to-end

User in `/hevn` channel sends: *"Is it safe to put 10% of my emergency fund into stablecoin DeFi like Aave?"*

1. **Telegram receive** → `handle_message` → expert path → `HevnExpert.handle(user, msg, channel)`.
2. **Classifier LLM call.** Hevn calls `await self._classify_consult_intent(msg)`. Returns:
   ```json
   {
     "needs_consult": true,
     "target": "makubex",
     "intent": "smart_contract_risk",
     "payload": { "protocol": "Aave", "asset": "USDC", "context": "stablecoin DeFi yield, ~10% of emergency fund" }
   }
   ```
   If `needs_consult` were `false`, Hevn would skip to its existing direct-answer path. R-3 adds the consult path; it does not break the direct path.
3. **Peer call:** `reply = await self.peer_call("makubex", "smart_contract_risk", payload)`.
   - `Bus.peer_call` opens or reuses an `agent_conversations` row (one per user-initiated turn that involves consult; on reuse if Hevn is already mid-conversation), assigns a new `envelope_id`, INSERTs an `agent_messages` row with `kind='request'`, `visibility='user_visible'`, `from_agent='hevn'`, `to_agent='makubex'`, the payload JSONB. Then `NOTIFY agent:makubex, '<envelope_id>'` AND `NOTIFY bus:user_visible, '<envelope_id>'`. Notify payloads stay small (just the ID); the envelope body lives in the row.
   - Bus registers `envelope_id → Future` in its in-process correlation map and `await`s the future with a 30 s timeout.
   - **Bot's `bus:user_visible` subscriber** receives the NOTIFY, fetches the row, renders **user message 1**:
     ```
     💰 Hevn → 🔧 MakubeX (consult): What's the smart-contract risk profile for putting an emergency fund into Aave USDC?
     ```
4. **MakubeX dispatcher** receives the `agent:makubex` NOTIFY, fetches the row, dispatches to its registered handler for `smart_contract_risk`. The handler invokes MakubeX's main LLM with a focused system prompt ("you are MakubeX assessing smart-contract risk for protocol={protocol} asset={asset}") and returns a structured reply:
   ```json
   {
     "summary": "Aave V3 USDC pool is among the lowest-risk DeFi positions...",
     "audit_status": "Multiple audits (Trail of Bits, OpenZeppelin); last incident 2023 (oracle, contained)",
     "tvl_signal": "≥$10B TVL on USDC pool — established liquidity",
     "depeg_history": "USDC briefly depegged Mar-2023 (SVB)...recovered",
     "oracle_bridge_risk": "Chainlink oracles, no bridging required if held on Ethereum mainnet",
     "rating": "low-to-moderate",
     "caveats": ["smart-contract residual risk", "regulatory uncertainty", "yield variability"]
   }
   ```
5. **Bus writes the reply.** INSERTs an `agent_messages` row with `kind='reply'`, `reply_to=<request envelope_id>`, `from_agent='makubex'`, `to_agent='hevn'`. Then `NOTIFY agent:hevn` AND `NOTIFY bus:user_visible`.
   - Bot renders **user message 2**:
     ```
     🔧 MakubeX → 💰 Hevn (reply):
     - Audit status: …
     - TVL: …
     - Depeg history: …
     - Oracle/bridge risk: …
     - Rating: low-to-moderate
     - Caveats: …
     ```
6. **Hevn's awaited future resolves** with MakubeX's reply payload. Hevn calls `await self._synthesize_with_consult(original_msg, reply_payload)` — the main Hevn LLM is re-prompted with the user's original question + MakubeX's risk read + Hevn's existing system prompt and profile context.
7. Hevn returns the synthesized recommendation as a normal `SkillResult`, which the existing expert path renders. **User message 3**:
   ```
   💰 Hevn: Based on MakubeX's read, Aave USDC is among the safer DeFi options...
   Given your emergency-fund context: I'd cap exposure at ≤5% of the fund, not 10%...
   ```
8. The normal post-turn flow runs: conversation saved to the existing `conversations` table via supabase-py (no change), background memory extraction fires (no change), expert footer appended.

**Total user-visible messages: 3.** The mesh IS the demo.

If `needs_consult` was `false` in step 2, Hevn skips steps 3–6 and goes straight to its existing direct answer — only one user-visible message. R-3 strictly adds capability; the non-consult path is untouched.

## §4 Error / timeout policy

- **Default `peer_call` timeout: 30 s** (overrideable via `R3_PEER_CALL_TIMEOUT_SECONDS` env or explicit `timeout=` kwarg). On expiry: raise `PeerCallTimeoutError` (subclass of R-1's `PeerCallError`).
- **Caller fallback pattern (Hevn):**
  ```python
  try:
      reply = await self.peer_call("makubex", "smart_contract_risk", payload)
      return await self._synthesize_with_consult(msg, reply)
  except PeerCallError as exc:
      logger.warning("Hevn peer_call failed: {}", exc)
      direct = await self._direct_answer(user, msg, channel)
      # Append a brief, honest footer so the user knows we tried.
      return SkillResult(
          text=direct.text + "\n\n_(I tried to consult MakubeX but couldn't reach them in time — answering from my own read.)_",
          skill_name=direct.skill_name,
          ai_response=direct.ai_response,
      )
  ```
  User experience on failure: 1 message instead of 3, with a one-line transparency footer. No silent degradation.
- **Peer-handler exception:** bus catches it, writes a `kind='error'` row with the exception summary in `payload['error']`, NOTIFYs the caller's channel. `peer_call` raises `PeerCallError` carrying `payload['error']`.
- **Late replies after timeout:** dispatcher inspects the future map; if absent or already resolved, log at DEBUG and drop. The future does not raise — `peer_call` already returned (timeout exception path).
- **DB write failure inside `peer_call`:** transaction rolls back; no NOTIFY fires; `peer_call` raises immediately with the asyncpg error wrapped in `PeerCallError`. No orphaned NOTIFYs ever.
- **NOTIFY-before-row race (defensive):** the bus does `INSERT ... ; NOTIFY ...` inside one transaction, so a NOTIFY without a corresponding row should not occur. As a safety net, listeners that get a NOTIFY for an `envelope_id` with no row log at DEBUG and drop the event — never crash the dispatcher.
- **Bus startup failure** (DB unreachable, migration not applied, `DATABASE_URL` missing): the bot's `post_init` propagates the asyncpg exception, the systemd service exits, and `Restart=on-failure` (already configured) restarts it. The error appears in `journalctl` clearly. The bot does NOT silently start without the bus — R-3 is a hard dependency.
- **Shutdown:** `post_shutdown` calls `Bus.shutdown()` which cancels listener tasks and resolves outstanding futures with `PeerCallError("bus shutting down")`. No hung awaits.

## §5 Schema — migration `006_agent_bus.sql`

Follows the project's existing migration pattern (`001`..`005` are plain SQL files manually applied via the Supabase SQL editor; `006` is applied the same way before R-3 is deployed). The R-3 plan will include explicit "apply this migration" steps with the SQL inlined.

```sql
-- 006_agent_bus.sql — Agentic OS R-3: inter-agent bus tables.

CREATE TABLE agent_conversations (
  conversation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  started_by_agent  VARCHAR(50)  NOT NULL,
  intent_root       VARCHAR(100),                          -- nullable; root intent if known
  status            VARCHAR(20)  NOT NULL DEFAULT 'open',  -- 'open' | 'closed' | 'errored'
  created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  closed_at         TIMESTAMPTZ
);

CREATE INDEX idx_agent_conv_user
  ON agent_conversations(user_id, created_at DESC);

CREATE TABLE agent_messages (
  envelope_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES agent_conversations(conversation_id) ON DELETE CASCADE,
  from_agent      VARCHAR(50)  NOT NULL,
  to_agent        VARCHAR(50)  NOT NULL,
  user_id         UUID         NOT NULL,                          -- denormalized for fast user lookups
  intent          VARCHAR(100) NOT NULL,
  visibility      VARCHAR(20)  NOT NULL DEFAULT 'user_visible',   -- 'user_visible' | 'internal'
  kind            VARCHAR(20)  NOT NULL,                          -- 'request' | 'reply' | 'error'
  reply_to        UUID REFERENCES agent_messages(envelope_id),    -- correlates reply → request
  payload         JSONB        NOT NULL,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_msg_conv
  ON agent_messages(conversation_id, created_at);

CREATE INDEX idx_agent_msg_to_pending
  ON agent_messages(to_agent, created_at DESC)
  WHERE kind = 'request';
```

Notes:

- `gen_random_uuid()` requires `pgcrypto` — enabled by default on Supabase.
- `ON DELETE CASCADE` on `user_id` matches existing project patterns (the `/reset` command wipes a user's cross-agent traffic too).
- Partial index `idx_agent_msg_to_pending` exists for replay/audit queries; the LISTEN/NOTIFY path is the hot path, not polling.
- No row-level security policies in this migration — the asyncpg connection uses the same Supabase service-role credentials as supabase-py (single user/service); RLS can be added later if R-4 introduces per-bot service principals.

## §6 Testing strategy

R-3 raises the test count from 13 to ~30. Existing 13 tests must stay green throughout.

| Test file | What it covers |
|---|---|
| `kaia/tests/test_bus_envelope.py` *(new)* | Envelope `to_dict`/`from_dict` symmetry; required fields enforced; `kind` enum guarded; `visibility` enum guarded; rejects malformed input. |
| `kaia/tests/test_bus_peer_call.py` *(new)* | With asyncpg mocked at the `Connection`/`Pool` boundary: envelope round-trip request→reply (one in-flight call); timeout fires after the configured budget and raises `PeerCallTimeoutError`; late reply dropped without raising; two concurrent in-flight calls keep their futures correlated; malformed NOTIFY payload does not crash the dispatcher; peer-handler exception → bus writes `kind='error'` row → caller raises `PeerCallError` carrying the error payload. |
| `kaia/tests/test_base_agent_peer_call.py` *(new)* | `BaseAgent.peer_call` on a fake subclass with a mocked bus returns peer reply payload on success; raises `PeerCallTimeoutError` on timeout; raises `PeerCallError` on peer error; `register_peer_intent` correctly binds an inbound handler. |
| `kaia/tests/test_hevn_classifier.py` *(new)* | With mocked AI: DeFi prompt → classifier emits `{"needs_consult": true, "target": "makubex", "intent": "smart_contract_risk", ...}`; non-DeFi prompt → `{"needs_consult": false}`; malformed classifier output → falls back to direct answer (no exception bubbling to user). |
| `kaia/tests/test_hevn_consult_fallback.py` *(new)* | With Hevn wired to a mocked bus that raises `PeerCallTimeoutError`: Hevn's `handle()` returns the direct-answer `SkillResult` with the transparency footer appended; one user-visible message, not three. |
| `kaia/tests/test_r3_demo_e2e.py` *(new)* | End-to-end with no real DB: real `HevnExpert` + real `MakubeXExpert` + in-process fake bus shim that mimics LISTEN/NOTIFY against an asyncio queue. Asserts the three-message attribution transcript shape (consult / reply / synthesis) for the DeFi scenario. |
| `kaia/tests/test_r3_live_bus.py` *(new, env-gated, optional)* | Skipped when `R3_INTEGRATION_DB_DSN` env var is not set. When set, runs against a real Postgres (local docker, staging Supabase project) to verify the actual NOTIFY round-trip works with real asyncpg. Not in CI's default path; lets the developer validate against Supabase before deploying. |

All 13 R-1/R-2 tests must remain green. The full suite target post-R-3 is ~30 tests.

## §7 Out of scope (deferred to later phases)

The phase intentionally does NOT deliver these — each is its own initiative:

- **R-4: per-bot Telegram tokens / Railway service split.** The bus is designed for the multi-process world (each agent process simply runs its own listener; no code change in `bus/`). Nothing in R-3 blocks the R-4 split.
- **R-5: cross-expert weekly digest, full mesh, more intents.**
- **Tool-calling inside Hevn's main LLM** (the brainstorming Q4 Approach B). Cleaner agentic pattern long-term, but its own initiative; not needed to prove R-3.
- **Intents beyond `smart_contract_risk`.** Each new intent is small follow-up work; R-3 ships exactly one demo intent.
- **Rate limiting per-user across peer calls.** Open question in `DESIGN.md` (cost concern at R-4); not blocking R-3.
- **`channel_profile` peer-readable without `peer_call`.** Another `DESIGN.md` open question; explicitly left open.
- **Multi-hop consults** (MakubeX peer-calls Kazuki while answering Hevn). Architecture supports it; not in the R-3 demo.
- **Row-level security on the bus tables.** Single service principal today; revisit at R-4.
- **Bus replay / dead-letter handling.** The audit tables make replay tractable later; R-3 ships only the live path.

## Migration impact

Documents that change when R-3 ships (the implementation plan will instruct each edit):

- `Docs/AGENTIC_OS/DESIGN.md` — status header line bumped to "R-3 (bus + protocol + demo) — in progress" (then "shipped" on completion). Runtime-layers diagram already lists `bus/` and `protocol/`; no other DESIGN.md edits.
- `Docs/AGENTIC_OS/PLAN_R3.md` *(new)* — implementation plan generated by the writing-plans skill.
- `Docs/ARCHITECTURE.md` — Agentic OS section: "Current state" bullet list extended to mention `kaia/bus/`, the live peer-call path, and the user-visible attribution rendering.
- `Docs/CHANGELOG.md` — prepend the R-3 entry (Added: bus, A2A protocol, smart_contract_risk consult; Changed: BaseAgent.peer_call now functional; Migration notes: requires `006_agent_bus.sql` and `DATABASE_URL` env var on prod).
- `Docs/DEVELOPMENT_STATUS.md` — Agentic OS table: R-3 row from ⏳ Planned to ✅ Complete.
- `Docs/DATABASE.md` — append a section documenting the two new tables.
- `kaia/.env.example` *(if it exists; otherwise just docs)* — add `DATABASE_URL=` and optional `R3_PEER_CALL_TIMEOUT_SECONDS=`.

Ops preconditions for the deploy:

- Apply `006_agent_bus.sql` to Supabase via the SQL editor.
- Set `DATABASE_URL` in EC2's `/opt/kaia/app/kaia/.env` (Supabase exposes the direct Postgres connection string in Project Settings → Database → Connection String — use the connection pooler URL on port 6543 if available, otherwise the direct 5432 URL).
- `sudo systemctl restart kaia` (the existing deploy workflow handles this automatically on merge to `main`).
