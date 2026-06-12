# Hevn Debt Coach — Design

> Status: Approved design — implementation pending.
> Owner: EJay. Date: 2026-06-12.
> Phase 1 of "Hevn professional advisor" track. Phase 2 (future/family
> planning: emergency fund, insurance, retirement, education funds) is out
> of scope and gets its own design.

## Goal

Upgrade Hevn from advice-by-prompt to a professional-grade debt advisor:
capture the user's debts as structured data, compute a mathematically
correct payoff plan (avalanche vs snowball), and hold the user accountable
with proactive nudges and monthly progress reviews — so the user can
actually get out of debt.

## Problem

Today debt exists only as free-text profile facts (`debt_info` category,
`active_debts` key). `FinancialHealthSkill._score_debt_ratio` pattern-matches
text like "no debt". Without balances, interest rates, and minimum payments
as structured data, Hevn cannot compute payoff dates, interest costs, or
strategy comparisons — its debt advice is necessarily generic.

## Locked decisions (from brainstorming)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Debt payoff engine ships first; future/family planning is phase 2. | "Get out of debt" is the foundation; planning advice is generic until debts are known precisely. |
| D2 | Intake = guided debt audit + ongoing chat capture. | First-session audit like a real advisor; afterwards debts/payments mentioned in chat are auto-captured (same pattern as goals/bills). |
| D3 | Strategy: Hevn computes BOTH avalanche and snowball, presents the comparison in pesos, recommends one, user decides. | What a professional advisor does; respects both math and motivation. |
| D4 | Proactive accountability: due-date nudges per debt + monthly progress review. | Plans die without accountability; extends existing `ProactiveAlertsSkill`. |
| D5 | All payoff math is deterministic pure Python (`debt_math.py`). The LLM never does arithmetic — it only narrates computed results. | Wrong math is disqualifying for a financial advisor; LLMs are unreliable at compound-interest arithmetic; pure functions are unit-testable. |

## Architecture

DebtCoach is Hevn's 8th skill, wired identically to the existing 7:

```
experts/hevn/skills/debt_coach.py   ← skill: audit flow, plan creation, progress, payments
experts/hevn/skills/debt_math.py    ← pure functions: amortization, strategy comparison (no LLM, no I/O)
experts/hevn/parser.py              ← + parse_debt_mention(), parse_debt_payment()
experts/hevn/prompts.py             ← + "debt" route in HEVN_INTENT_PROMPT; debts_summary in system prompt;
                                        PH debt-landscape persona additions
experts/hevn/expert.py              ← instantiate DebtCoachSkill; route "debt" intent
experts/hevn/skills/proactive.py    ← + debt due-date nudges, monthly progress review
core/scheduler.py                   ← + schedule_debt_nudges / schedule_debt_monthly_review
                                        (same pattern as schedule_hevn_weekly_digest)
database/models.py                  ← + Debt, DebtPayment, DebtPlan dataclasses
database/queries.py                 ← + CRUD for the three new tables (supabase-py, same as goals/bills)
```

Constraints preserved:
- supabase-py owns all data access for the new tables (asyncpg stays bus-only, per R-3).
- The Telegram bot remains the only module importing `telegram`.
- No changes to `BaseAgent` / bus / peer-call machinery.

## Data model

Three new tables, mirroring `FinancialGoal`/`RecurringBill` conventions
(money as `Decimal`, snake_case, `status` strings):

**`debts`**
| field | type | notes |
|---|---|---|
| id | uuid | |
| user_id | str | |
| name | str | "BPI Credit Card" |
| debt_type | str | credit_card, salary_loan, personal_loan, five_six, pagibig_loan, sss_loan, auto_loan, mortgage, other |
| balance | Decimal | current outstanding |
| interest_rate | Decimal | as quoted |
| rate_period | str | "monthly" \| "yearly" — PH credit cards quote monthly |
| rate_is_estimate | bool | true when a type-default was used because the user didn't know |
| minimum_payment | Decimal \| null | |
| due_day | int \| null | 1–31 |
| original_amount | Decimal \| null | |
| status | str | active, paid_off, archived |
| notes | str \| null | |
| created_at / updated_at | timestamps | |

**`debt_payments`**
| field | type | notes |
|---|---|---|
| id | uuid | |
| debt_id | uuid | |
| user_id | str | |
| amount | Decimal | |
| paid_on | date | |
| balance_after | Decimal | balance snapshot after applying payment |

**`debt_plans`** (one active row per user)
| field | type | notes |
|---|---|---|
| id | uuid | |
| user_id | str | |
| strategy | str | "avalanche" \| "snowball" |
| monthly_budget | Decimal | total ₱/month committed to debt |
| baseline_payoff_date | date | projected at plan creation |
| baseline_total_interest | Decimal | projected at plan creation |
| status | str | active, completed, abandoned |
| created_at | timestamp | |

The month-by-month schedule is **never persisted** — it is recomputed
deterministically from current debts + plan params, so it cannot go stale.
Progress = recompute today, compare against the baseline snapshot.

**Audit session state** is in-memory per-user on the skill instance
(codebase precedent: `_recent_suggestions` dict in `core/expert_detector.py`).
Each debt is persisted the moment it is fully captured, so a restart
mid-audit loses only the conversational cursor, never data.

## debt_math.py contract

Pure functions, `Decimal` in/out, no I/O:

- `monthly_rate(rate, rate_period) -> Decimal` — normalize yearly→monthly.
- `amortize(debts, monthly_budget, strategy) -> PayoffSchedule` — simulates
  month by month: every active debt gets its minimum, the surplus goes to
  the strategy's target debt (highest rate for avalanche, smallest balance
  for snowball). Returns per-debt payoff month, total interest paid,
  debt-free date, and the full schedule (for narration, not storage).
- `compare_strategies(debts, monthly_budget) -> StrategyComparison` — runs
  both, returns the deltas (interest saved, first-debt-cleared month).
- Shortfall detection: if `monthly_budget < Σ minimum_payments`, return a
  structured shortfall result instead of a schedule.
- Never-pays-off detection: if a debt's payment ≤ its monthly interest, or
  the simulation exceeds a hard cap of 600 months, return a structured
  "non-amortizing" result identifying the offending debt.

## User flows

**Flow 1 — Guided debt audit.** "Help me get out of my debt" → intent
router → `debt` → no active debts on file → audit starts. Hevn explains
what she needs and why, then collects one debt at a time, one question at
a time (lender → balance → rate → minimum → due day), parsing each answer
with the existing `parse_*` LLM pattern. Unknown rate → labeled type
default (e.g. credit card 3.5%/mo, `rate_is_estimate=true`). After each
completed debt: "any other debts?" Audit is resumable: captured debts are
already saved; the next debt-intent message offers to resume or finish.

**Flow 2 — Plan creation.** Audit complete → Hevn asks for the monthly
debt budget (one number) → `compare_strategies` → Hevn presents both plans
with real numbers ("Avalanche: debt-free Aug 2028, ₱X total interest.
Snowball: first debt cleared in 4 months, costs ₱Y more.") → recommends
one for this user's profile → user picks → plan + baseline saved.

**Flow 3 — Ongoing coaching.**
- "Paid ₱5k on my BPI card" → `parse_debt_payment` → log to
  `debt_payments`, decrement balance; debt hits zero → celebrate, mark
  `paid_off`, surplus rolls to next target automatically (inherent in
  recomputation).
- New debt mentioned in chat → captured like goals/bills today.
- Monthly progress review (proactive): recompute vs baseline → ahead/behind,
  updated debt-free date.
- Due-date nudges: 3 days before each active debt's `due_day`, scheduled
  via `core/scheduler.py` (same mechanism as the Hevn weekly digest),
  rendered by `ProactiveAlertsSkill`. The monthly progress review is
  scheduled the same way, on the plan's creation day-of-month.
- `debts_summary` is injected into `HEVN_SYSTEM_PROMPT` next to
  `budget_summary`/`goals_summary`, so all Hevn conversations are
  debt-aware.

**Routing note.** `HEVN_INTENT_PROMPT` gains a `debt` skill entry with the
same advice-vs-records disambiguation the goals entry has: "should I pay
debt or invest?" → general_chat (advice); "I paid my card" / "add my loan"
/ "how's my debt plan" → debt (records/plan).

## Persona upgrade

`HEVN_SYSTEM_PROMPT` gains a PH debt-landscape knowledge block: credit
card monthly add-on rates and BSP caps, salary loans, 5-6 informal
lending, balance transfer offers, Pag-IBIG/SSS loan terms, debt
consolidation options. Tone for debt: zero judgment, all plan.

## Error handling

| Case | Behavior |
|---|---|
| Budget < Σ minimums | No plan is built. Hevn states the shortfall amount plainly and shifts to options: restructuring, balance transfer, Pag-IBIG/SSS consolidation. The advisor moment, not an error message. |
| Payment ≤ monthly interest | Calculator returns "non-amortizing" naming the debt; Hevn explains that debt never pays off at this rate and what minimum payment changes it. |
| Malformed parser/LLM output | Fall through to Hevn's `_direct_answer` path (existing pattern in `expert.py`). |
| Audit abandoned mid-way | Saved debts persist; next debt message resumes or restarts the cursor cleanly. |
| Input validation | `Decimal` everywhere; reject negative balances/payments; rate sanity bounds (0–25%/mo) with a confirm prompt for outliers. |

## Testing

- **`debt_math` golden tests** (no mocks): hand-verified amortization
  cases, avalanche vs snowball ordering and interest deltas, shortfall
  detection, non-amortizing detection, 600-month cap, Decimal rounding.
- **Parser tests**: debt mention and payment parsing (mocked AI engine,
  same as existing parser tests).
- **Skill tests**: audit multi-turn flow persists debts; plan creation
  persists plan + baseline; payment updates balance and detects payoff
  (mocked DB, pattern of `test_hevn_classifier.py`).
- **Routing test**: `HEVN_INTENT_PROMPT` debt-vs-advice disambiguation.

## Documentation updates (mandatory)

`DATABASE.md` (3 new tables), `SKILLS.md` (DebtCoach), `ARCHITECTURE.md`
(skill count + module map), `DEVELOPMENT_STATUS.md`.

## Out of scope

- Phase 2: future/family financial planning (emergency fund sizing,
  insurance gap, SSS/MP2/PERA retirement, education funds) — separate
  design on top of this foundation.
- Bank/e-wallet integrations; statement parsing.
- Changes to bus/A2A/peer-call machinery.
