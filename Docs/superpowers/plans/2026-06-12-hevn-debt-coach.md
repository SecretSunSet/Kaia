# Hevn Debt Coach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Hevn structured debt tracking, a deterministic avalanche/snowball payoff engine, a guided debt audit conversation, and proactive accountability (due-date nudges + monthly progress review).

**Architecture:** DebtCoach is Hevn's 8th skill, wired exactly like the existing 7 (intent route → skill dispatch in `expert.py`). All payoff arithmetic lives in a pure-Python module `debt_math.py` — the LLM never computes numbers, only narrates them. Three new Supabase tables (`debts`, `debt_payments`, `debt_plans`) accessed via supabase-py in `database/queries.py`. The guided audit is an in-memory per-user state machine on the skill instance; each completed debt is persisted immediately.

**Tech Stack:** Python 3.12 (system interpreter), supabase-py, APScheduler (existing `core/scheduler.py`), loguru, pytest + pytest-asyncio. Migration applied manually via Supabase SQL editor (same as 001–006).

**Spec:** `Docs/superpowers/specs/2026-06-12-hevn-debt-coach-design.md`

**Working directory for all commands:** `/home/ejay/Kaia/kaia` (run tests as `python3 -m pytest …`; there is no venv — system Python is the interpreter).

**Repo-specific gotcha:** a GateGuard hook denies the FIRST Write/Edit to each new file path and the first Bash command per session, asking you to state facts. State the facts it asks for in your reply, then retry the identical operation — the retry passes. This is expected, not an error.

---

## File Structure

```
kaia/database/migrations/007_hevn_debt.sql   CREATE: 3 tables + indexes + RLS
kaia/database/models.py                      MODIFY: + Debt, DebtPayment, DebtPlan dataclasses
kaia/database/queries.py                     MODIFY: + debt CRUD section (goals/bills pattern)
kaia/experts/hevn/skills/debt_math.py        CREATE: pure payoff math (no LLM, no I/O)
kaia/experts/hevn/skills/debt_coach.py       CREATE: audit state machine, plan, progress, payments
kaia/experts/hevn/parser.py                  MODIFY: + parse_debt_mention, parse_debt_payment, parse_amount; debt intent short-circuit
kaia/experts/hevn/prompts.py                 MODIFY: + debt intent route, debts_summary in system prompt, PH debt knowledge
kaia/experts/hevn/expert.py                  MODIFY: + audit interception, debt route, debts_summary injection, scheduling hook
kaia/experts/hevn/skills/proactive.py        MODIFY: + debt nudges + monthly review renderers
kaia/core/scheduler.py                       MODIFY: + schedule_debt_reminders / _fire_debt_nudge / _fire_debt_review
kaia/tests/test_debt_math.py                 CREATE: golden math tests
kaia/tests/test_debt_coach.py                CREATE: audit/progress/payment tests (mocked db+ai)
kaia/tests/test_hevn_debt_routing.py         CREATE: intent routing tests
Docs/DATABASE.md                             MODIFY: + Migration 007 section
Docs/SKILLS.md                               MODIFY: + DebtCoach skill entry
Docs/ARCHITECTURE.md                         MODIFY: Hevn skill count/module map
Docs/DEVELOPMENT_STATUS.md                   MODIFY: D-1 phase entry
Docs/CHANGELOG.md                            MODIFY: D-1 entry
```

Task order: math first (pure, TDD), then storage, then parsers/prompts, then the skill, then wiring, then proactive/scheduler, then docs.

---

### Task 1: `debt_math.py` — rate normalization and date helper

**Files:**
- Create: `kaia/experts/hevn/skills/debt_math.py`
- Test: `kaia/tests/test_debt_math.py`

- [ ] **Step 1: Write the failing tests**

Create `kaia/tests/test_debt_math.py`:

```python
"""Golden tests for Hevn's deterministic debt payoff math (Phase D-1).

Every expected number in this file was hand-computed; if a test fails,
suspect the implementation, not the test.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from experts.hevn.skills import debt_math
from experts.hevn.skills.debt_math import DebtInput


def test_monthly_rate_passes_monthly_through():
    assert debt_math.monthly_rate(Decimal("3.5"), "monthly") == Decimal("0.035")


def test_monthly_rate_divides_yearly_by_twelve():
    assert debt_math.monthly_rate(Decimal("24"), "yearly") == Decimal("0.02")


def test_add_months_rolls_year():
    assert debt_math.add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_add_months_clamps_day_to_28():
    # Day 31 would not exist in Feb; clamp keeps dates valid in every month.
    assert debt_math.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_math.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experts.hevn.skills.debt_math'`

- [ ] **Step 3: Write the implementation**

Create `kaia/experts/hevn/skills/debt_math.py`:

```python
"""Deterministic debt payoff math — no LLM, no I/O (Phase D-1).

All money is Decimal. Quoted rates are percentages; monthly_rate()
normalizes them to per-month fractions (3.5%/mo -> Decimal("0.035")).
The LLM never computes these numbers — it only narrates results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# Beyond this the plan is treated as non-amortizing (50 years).
MAX_MONTHS = 600

# When a debt has no known minimum payment, simulate with
# max(3% of balance, ₱500) — the common PH credit-card convention.
DEFAULT_MIN_PCT = Decimal("0.03")
DEFAULT_MIN_FLOOR = Decimal("500")

_CENTS = Decimal("0.01")


def monthly_rate(rate: Decimal, rate_period: str) -> Decimal:
    """Normalize a quoted percentage rate to a per-month fraction."""
    pct = rate / Decimal("100")
    if rate_period == "yearly":
        return pct / Decimal("12")
    return pct


def add_months(d: date, months: int) -> date:
    """Add calendar months; day-of-month clamped to 28 so it always exists."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(d.day, 28))


def default_minimum(balance: Decimal) -> Decimal:
    """Fallback minimum payment when the user doesn't know theirs."""
    return max((balance * DEFAULT_MIN_PCT).quantize(_CENTS), DEFAULT_MIN_FLOOR)


@dataclass(frozen=True)
class DebtInput:
    """Snapshot of one debt fed into the simulator."""

    debt_id: str
    name: str
    balance: Decimal
    monthly_rate: Decimal  # per-month fraction, e.g. Decimal("0.035")
    minimum_payment: Decimal
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_math.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/experts/hevn/skills/debt_math.py kaia/tests/test_debt_math.py && git commit -m "feat(hevn): debt_math rate normalization + date helpers (D-1)"
```

---

### Task 2: `debt_math.amortize` — the payoff simulator

**Files:**
- Modify: `kaia/experts/hevn/skills/debt_math.py`
- Test: `kaia/tests/test_debt_math.py`

- [ ] **Step 1: Write the failing tests**

Append to `kaia/tests/test_debt_math.py`:

```python
def _debt(debt_id, name, balance, rate, minimum):
    return DebtInput(
        debt_id=debt_id,
        name=name,
        balance=Decimal(str(balance)),
        monthly_rate=Decimal(str(rate)),
        minimum_payment=Decimal(str(minimum)),
    )


START = date(2026, 6, 1)


def test_amortize_zero_interest_exact_months():
    # 10,000 at 0% paying 1,000/mo -> exactly 10 months, zero interest.
    plan = debt_math.amortize(
        [_debt("d1", "Loan", 10000, 0, 1000)], Decimal("1000"), "avalanche", START
    )
    assert plan.ok
    assert plan.months == 10
    assert plan.total_interest == Decimal("0")
    assert plan.debt_free_date == date(2027, 4, 1)


def test_amortize_single_debt_golden_numbers():
    # Hand-computed: 10,000 at 2%/mo, min 500, budget 2,000.
    # m1: +200.00 -> 10200.00, pay 2000 -> 8200.00
    # m2: +164.00 ->  8364.00, pay 2000 -> 6364.00
    # m3: +127.28 ->  6491.28, pay 2000 -> 4491.28
    # m4: + 89.83 ->  4581.11, pay 2000 -> 2581.11
    # m5: + 51.62 ->  2632.73, pay 2000 ->  632.73
    # m6: + 12.65 ->   645.38, pay  645.38 -> 0
    plan = debt_math.amortize(
        [_debt("d1", "BPI Card", 10000, 0.02, 500)], Decimal("2000"), "avalanche", START
    )
    assert plan.ok
    assert plan.months == 6
    assert plan.total_interest == Decimal("645.38")
    assert plan.payoffs[0].name == "BPI Card"
    assert plan.payoffs[0].payoff_month == 6


def test_avalanche_targets_highest_rate_snowball_smallest_balance():
    debts = [
        _debt("a", "Big High-Rate", 5000, 0.03, 250),
        _debt("b", "Small Low-Rate", 2000, 0.01, 100),
    ]
    av = debt_math.amortize(debts, Decimal("1000"), "avalanche", START)
    sn = debt_math.amortize(debts, Decimal("1000"), "snowball", START)
    assert av.ok and sn.ok
    # Avalanche saves interest; snowball clears the small debt first.
    assert av.total_interest < sn.total_interest
    assert sn.payoffs[0].name == "Small Low-Rate"
    assert av.payoffs[0].name == "Big High-Rate"


def test_shortfall_when_budget_below_minimums():
    debts = [
        _debt("a", "Card", 5000, 0.03, 250),
        _debt("b", "Loan", 2000, 0.01, 100),
    ]
    plan = debt_math.amortize(debts, Decimal("300"), "avalanche", START)
    assert not plan.ok
    assert plan.error == "shortfall"
    assert plan.shortfall == Decimal("50")


def test_non_amortizing_debt_detected():
    # 10,000 at 5%/mo with only a 100 payment: interest (500) > payment.
    plan = debt_math.amortize(
        [_debt("d1", "5-6 Loan", 10000, 0.05, 100)], Decimal("100"), "avalanche", START
    )
    assert not plan.ok
    assert plan.error == "non_amortizing"
    assert plan.problem_debts == ["5-6 Loan"]


def test_empty_debts_is_trivially_done():
    plan = debt_math.amortize([], Decimal("1000"), "avalanche", START)
    assert plan.ok
    assert plan.months == 0


def test_freed_minimum_rolls_into_surplus():
    # Once a debt is paid off, the full budget keeps flowing to the rest:
    # total paid over the plan == principal + total interest.
    debts = [
        _debt("a", "Card", 6000, 0.02, 300),
        _debt("b", "Loan", 4000, 0.015, 200),
    ]
    budget = Decimal("1500")
    plan = debt_math.amortize(debts, budget, "avalanche", START)
    assert plan.ok
    total_principal = Decimal("10000")
    paid_upper_bound = budget * plan.months
    assert total_principal + plan.total_interest <= paid_upper_bound
    # The final month is a partial payment, so strictly fewer full budgets:
    assert total_principal + plan.total_interest > budget * (plan.months - 1)
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_math.py -v`
Expected: first 4 PASS, new 7 FAIL with `AttributeError: ... no attribute 'amortize'`

- [ ] **Step 3: Write the implementation**

Append to `kaia/experts/hevn/skills/debt_math.py`:

```python
@dataclass
class DebtPayoff:
    """One debt's payoff record inside a simulated plan."""

    debt_id: str
    name: str
    payoff_month: int  # 1-based month index
    payoff_date: date
    interest_paid: Decimal


@dataclass
class PayoffPlan:
    """Result of an amortize() run. Check .ok before reading numbers."""

    ok: bool
    error: str | None = None  # None | "shortfall" | "non_amortizing"
    shortfall: Decimal | None = None
    problem_debts: list[str] = field(default_factory=list)
    months: int = 0
    debt_free_date: date | None = None
    total_interest: Decimal = Decimal("0")
    payoffs: list[DebtPayoff] = field(default_factory=list)


class _Account:
    """Mutable per-debt state during simulation."""

    __slots__ = ("debt", "balance", "interest")

    def __init__(self, debt: DebtInput) -> None:
        self.debt = debt
        self.balance = debt.balance
        self.interest = Decimal("0")


def _pick_target(active: dict[str, "_Account"], strategy: str) -> "_Account":
    accounts = [a for a in active.values() if a.balance > 0]
    if strategy == "snowball":
        # Smallest balance first; tie-break on higher rate.
        return min(accounts, key=lambda a: (a.balance, -a.debt.monthly_rate))
    # Avalanche: highest rate first; tie-break on smaller balance.
    return min(accounts, key=lambda a: (-a.debt.monthly_rate, a.balance))


def amortize(
    debts: list[DebtInput],
    monthly_budget: Decimal,
    strategy: str,
    start: date | None = None,
) -> PayoffPlan:
    """Simulate month-by-month payoff.

    Each month: accrue interest, pay every debt its minimum, then send the
    whole surplus to the strategy's target debt. Freed minimums roll into
    the surplus automatically because the budget is a fixed total.
    """
    start = start or date.today()
    active = {d.debt_id: _Account(d) for d in debts if d.balance > 0}
    if not active:
        return PayoffPlan(ok=True, months=0, debt_free_date=start)

    min_sum = sum((a.debt.minimum_payment for a in active.values()), Decimal("0"))
    if monthly_budget < min_sum:
        return PayoffPlan(
            ok=False, error="shortfall", shortfall=min_sum - monthly_budget
        )

    total_interest = Decimal("0")
    payoffs: list[DebtPayoff] = []
    month = 0
    while active and month < MAX_MONTHS:
        month += 1
        for acct in active.values():
            interest = (acct.balance * acct.debt.monthly_rate).quantize(_CENTS)
            acct.balance += interest
            acct.interest += interest
            total_interest += interest

        budget = monthly_budget
        for acct in active.values():
            pay = min(acct.debt.minimum_payment, acct.balance)
            acct.balance -= pay
            budget -= pay

        while budget > 0 and any(a.balance > 0 for a in active.values()):
            target = _pick_target(active, strategy)
            pay = min(budget, target.balance)
            target.balance -= pay
            budget -= pay

        for debt_id in [k for k, a in active.items() if a.balance <= 0]:
            acct = active.pop(debt_id)
            payoffs.append(
                DebtPayoff(
                    debt_id=acct.debt.debt_id,
                    name=acct.debt.name,
                    payoff_month=month,
                    payoff_date=add_months(start, month),
                    interest_paid=acct.interest,
                )
            )

    if active:
        return PayoffPlan(
            ok=False,
            error="non_amortizing",
            problem_debts=sorted(a.debt.name for a in active.values()),
        )
    return PayoffPlan(
        ok=True,
        months=month,
        debt_free_date=add_months(start, month),
        total_interest=total_interest,
        payoffs=payoffs,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_math.py -v`
Expected: 11 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/experts/hevn/skills/debt_math.py kaia/tests/test_debt_math.py && git commit -m "feat(hevn): amortize() payoff simulator with shortfall + non-amortizing detection (D-1)"
```

---

### Task 3: `debt_math` — strategy comparison and recommendation

**Files:**
- Modify: `kaia/experts/hevn/skills/debt_math.py`
- Test: `kaia/tests/test_debt_math.py`

- [ ] **Step 1: Write the failing tests**

Append to `kaia/tests/test_debt_math.py`:

```python
def test_compare_strategies_returns_both_plans_and_delta():
    debts = [
        _debt("a", "Big High-Rate", 5000, 0.03, 250),
        _debt("b", "Small Low-Rate", 2000, 0.01, 100),
    ]
    comp = debt_math.compare_strategies(debts, Decimal("1000"), START)
    assert comp.avalanche.ok and comp.snowball.ok
    assert comp.interest_saved_by_avalanche == (
        comp.snowball.total_interest - comp.avalanche.total_interest
    )
    assert comp.interest_saved_by_avalanche > 0


def test_recommend_avalanche_when_savings_material():
    debts = [
        _debt("a", "Card", 100000, 0.035, 3000),
        _debt("b", "Loan", 20000, 0.01, 1000),
    ]
    comp = debt_math.compare_strategies(debts, Decimal("10000"), START)
    strategy, reason = debt_math.recommend_strategy(comp)
    assert strategy == "avalanche"
    assert reason  # non-empty human-readable rationale


def test_recommend_snowball_when_savings_trivial_and_quick_win():
    # Nearly identical rates -> avalanche saves almost nothing; the small
    # debt's quick payoff makes snowball the better behavioral pick.
    debts = [
        _debt("a", "Loan A", 50000, 0.0201, 1500),
        _debt("b", "Loan B", 3000, 0.02, 300),
    ]
    comp = debt_math.compare_strategies(debts, Decimal("5000"), START)
    strategy, _reason = debt_math.recommend_strategy(comp)
    assert strategy == "snowball"
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_math.py -v`
Expected: prior 11 PASS, new 3 FAIL with `AttributeError: ... 'compare_strategies'`

- [ ] **Step 3: Write the implementation**

Append to `kaia/experts/hevn/skills/debt_math.py`:

```python
# Below this saving, avalanche's edge is too small to outweigh the
# motivational value of an early snowball win.
TRIVIAL_SAVINGS = Decimal("1000")


@dataclass
class StrategyComparison:
    avalanche: PayoffPlan
    snowball: PayoffPlan
    interest_saved_by_avalanche: Decimal = Decimal("0")


def compare_strategies(
    debts: list[DebtInput], monthly_budget: Decimal, start: date | None = None
) -> StrategyComparison:
    """Run both strategies on the same inputs."""
    av = amortize(debts, monthly_budget, "avalanche", start)
    sn = amortize(debts, monthly_budget, "snowball", start)
    saved = Decimal("0")
    if av.ok and sn.ok:
        saved = sn.total_interest - av.total_interest
    return StrategyComparison(
        avalanche=av, snowball=sn, interest_saved_by_avalanche=saved
    )


def recommend_strategy(comp: StrategyComparison) -> tuple[str, str]:
    """Deterministic recommendation: avalanche unless its savings are
    trivial AND snowball delivers a faster first win."""
    if not (comp.avalanche.ok and comp.snowball.ok):
        return "avalanche", "Pay the highest-rate debt first."
    first_av = comp.avalanche.payoffs[0].payoff_month if comp.avalanche.payoffs else 0
    first_sn = comp.snowball.payoffs[0].payoff_month if comp.snowball.payoffs else 0
    if comp.interest_saved_by_avalanche <= TRIVIAL_SAVINGS and first_sn < first_av:
        return "snowball", (
            "The interest difference is small here, and clearing your first "
            "debt sooner keeps you motivated."
        )
    return "avalanche", (
        "It saves you the most money by killing the highest-rate debt first."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_math.py -v`
Expected: 14 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/experts/hevn/skills/debt_math.py kaia/tests/test_debt_math.py && git commit -m "feat(hevn): strategy comparison + deterministic recommendation (D-1)"
```

---

### Task 4: Migration, models, and CRUD

The codebase has no DB-integration tests (queries.py is untested by convention — it is thin supabase-py plumbing). Follow that convention: no unit tests for this task; correctness is covered by the mocked-db skill tests in Tasks 7–8.

**Files:**
- Create: `kaia/database/migrations/007_hevn_debt.sql`
- Modify: `kaia/database/models.py` (append after the `RecurringBill` dataclass, before the MakubeX section)
- Modify: `kaia/database/queries.py` (append a new section after the recurring-bills section; extend the models import)

- [ ] **Step 1: Create the migration**

Create `kaia/database/migrations/007_hevn_debt.sql`:

```sql
-- ============================================================
-- KAIA Phase D-1 — Hevn Debt Coach tables
-- Run this in Supabase SQL Editor after 006_agent_bus.sql.
-- ============================================================

CREATE TABLE IF NOT EXISTS debts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    debt_type VARCHAR(30) NOT NULL DEFAULT 'other',
    balance DECIMAL(14,2) NOT NULL,
    interest_rate DECIMAL(8,4) NOT NULL,
    rate_period VARCHAR(10) NOT NULL DEFAULT 'monthly',  -- monthly, yearly
    rate_is_estimate BOOLEAN NOT NULL DEFAULT FALSE,
    minimum_payment DECIMAL(12,2),
    due_day INT CHECK (due_day >= 1 AND due_day <= 31),
    original_amount DECIMAL(14,2),
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, paid_off, archived
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS debt_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    debt_id UUID REFERENCES debts(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    amount DECIMAL(12,2) NOT NULL,
    paid_on DATE NOT NULL DEFAULT CURRENT_DATE,
    balance_after DECIMAL(14,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS debt_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    strategy VARCHAR(20) NOT NULL,                 -- avalanche, snowball
    monthly_budget DECIMAL(12,2) NOT NULL,
    baseline_payoff_date DATE NOT NULL,
    baseline_total_interest DECIMAL(14,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, completed, abandoned
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_debts_user_status ON debts(user_id, status);
CREATE INDEX IF NOT EXISTS idx_debt_payments_debt ON debt_payments(debt_id, paid_on DESC);
CREATE INDEX IF NOT EXISTS idx_debt_plans_user_status ON debt_plans(user_id, status);

-- ── Row-Level Security ─────────────────────────────────────────────
ALTER TABLE debts ENABLE ROW LEVEL SECURITY;
ALTER TABLE debt_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE debt_plans ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all" ON debts;
DROP POLICY IF EXISTS "service_role_all" ON debt_payments;
DROP POLICY IF EXISTS "service_role_all" ON debt_plans;

CREATE POLICY "service_role_all" ON debts FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON debt_payments FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON debt_plans FOR ALL USING (true) WITH CHECK (true);
```

**Note:** the migration is applied manually in the Supabase SQL editor (same as 001–006). Flag this in the final report — it must be run before deploying.

- [ ] **Step 2: Add the dataclasses**

In `kaia/database/models.py`, after the `RecurringBill` class and before the `# ── MakubeX (Phase CH-3) ──…` comment, insert:

```python
# ── Hevn Debt Coach (Phase D-1) ─────────────────────────────────────

@dataclass
class Debt:
    user_id: str
    name: str
    debt_type: str  # credit_card, salary_loan, personal_loan, five_six,
                    # pagibig_loan, sss_loan, auto_loan, mortgage, other
    balance: Decimal
    interest_rate: Decimal  # as quoted, in percent
    rate_period: str = "monthly"  # monthly, yearly
    rate_is_estimate: bool = False
    minimum_payment: Decimal | None = None
    due_day: int | None = None
    original_amount: Decimal | None = None
    id: str = ""
    status: str = "active"  # active, paid_off, archived
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class DebtPayment:
    debt_id: str
    user_id: str
    amount: Decimal
    paid_on: date
    balance_after: Decimal
    id: str = ""
    created_at: datetime | None = None


@dataclass
class DebtPlan:
    user_id: str
    strategy: str  # avalanche, snowball
    monthly_budget: Decimal
    baseline_payoff_date: date
    baseline_total_interest: Decimal
    id: str = ""
    status: str = "active"  # active, completed, abandoned
    created_at: datetime | None = None
```

(`Decimal`, `date`, `datetime`, `dataclass` are already imported at the top of models.py — verify before assuming, and add to the existing import lines if any is missing.)

- [ ] **Step 3: Add the CRUD section**

In `kaia/database/queries.py`:

a) Extend the `from database.models import (...)` line at the top with `Debt, DebtPayment, DebtPlan`.

b) After the recurring-bills section (after `get_recurring_bill_by_id`), append:

```python
# ── Debts (Hevn — Phase D-1) ────────────────────────────────────────

def _row_to_debt(row: dict) -> Debt:
    """Convert a Supabase row dict to a Debt dataclass."""
    minimum = row.get("minimum_payment")
    original = row.get("original_amount")
    return Debt(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        debt_type=row.get("debt_type", "other"),
        balance=Decimal(str(row["balance"])),
        interest_rate=Decimal(str(row["interest_rate"])),
        rate_period=row.get("rate_period", "monthly"),
        rate_is_estimate=row.get("rate_is_estimate", False),
        minimum_payment=Decimal(str(minimum)) if minimum is not None else None,
        due_day=row.get("due_day"),
        original_amount=Decimal(str(original)) if original is not None else None,
        status=row.get("status", "active"),
        notes=row.get("notes"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


async def create_debt(
    user_id: str,
    name: str,
    balance: float,
    interest_rate: float,
    debt_type: str = "other",
    rate_period: str = "monthly",
    rate_is_estimate: bool = False,
    minimum_payment: float | None = None,
    due_day: int | None = None,
    original_amount: float | None = None,
    notes: str | None = None,
) -> Debt:
    """Insert a new debt and return it."""
    sb = get_supabase()
    data: dict = {
        "user_id": user_id,
        "name": name,
        "debt_type": debt_type,
        "balance": balance,
        "interest_rate": interest_rate,
        "rate_period": rate_period,
        "rate_is_estimate": rate_is_estimate,
    }
    if minimum_payment is not None:
        data["minimum_payment"] = minimum_payment
    if due_day is not None:
        data["due_day"] = due_day
    if original_amount is not None:
        data["original_amount"] = original_amount
    if notes:
        data["notes"] = notes
    result = sb.table("debts").insert(data).execute()
    return _row_to_debt(result.data[0])


async def get_debts(user_id: str, status: str | None = "active") -> list[Debt]:
    """Return debts for a user (optionally filtered by status)."""
    sb = get_supabase()
    query = sb.table("debts").select("*").eq("user_id", user_id)
    if status:
        query = query.eq("status", status)
    result = query.order("balance", desc=True).execute()
    return [_row_to_debt(r) for r in result.data]


async def get_debt_by_id(debt_id: str) -> Debt | None:
    """Fetch a single debt by ID."""
    sb = get_supabase()
    result = sb.table("debts").select("*").eq("id", debt_id).execute()
    if not result.data:
        return None
    return _row_to_debt(result.data[0])


async def update_debt(debt_id: str, **fields: object) -> None:
    """Update arbitrary fields on a debt."""
    if not fields:
        return
    sb = get_supabase()
    payload = dict(fields)
    payload["updated_at"] = datetime.utcnow().isoformat()
    sb.table("debts").update(payload).eq("id", debt_id).execute()


async def create_debt_payment(
    debt_id: str,
    user_id: str,
    amount: float,
    balance_after: float,
    paid_on: str | None = None,
) -> None:
    """Log a payment against a debt."""
    sb = get_supabase()
    data: dict = {
        "debt_id": debt_id,
        "user_id": user_id,
        "amount": amount,
        "balance_after": balance_after,
    }
    if paid_on:
        data["paid_on"] = paid_on
    sb.table("debt_payments").insert(data).execute()


async def get_debt_payments(debt_id: str, limit: int = 12) -> list[DebtPayment]:
    """Recent payments for one debt, newest first."""
    sb = get_supabase()
    result = (
        sb.table("debt_payments")
        .select("*")
        .eq("debt_id", debt_id)
        .order("paid_on", desc=True)
        .limit(limit)
        .execute()
    )
    return [
        DebtPayment(
            id=r["id"],
            debt_id=r["debt_id"],
            user_id=r["user_id"],
            amount=Decimal(str(r["amount"])),
            paid_on=date.fromisoformat(r["paid_on"]),
            balance_after=Decimal(str(r["balance_after"])),
            created_at=r.get("created_at"),
        )
        for r in result.data
    ]


async def get_active_debt_plan(user_id: str) -> DebtPlan | None:
    """The user's single active payoff plan, if any."""
    sb = get_supabase()
    result = (
        sb.table("debt_plans")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )
    if not result.data:
        return None
    r = result.data[0]
    return DebtPlan(
        id=r["id"],
        user_id=r["user_id"],
        strategy=r["strategy"],
        monthly_budget=Decimal(str(r["monthly_budget"])),
        baseline_payoff_date=date.fromisoformat(r["baseline_payoff_date"]),
        baseline_total_interest=Decimal(str(r["baseline_total_interest"])),
        status=r.get("status", "active"),
        created_at=r.get("created_at"),
    )


async def create_debt_plan(
    user_id: str,
    strategy: str,
    monthly_budget: float,
    baseline_payoff_date: str,
    baseline_total_interest: float,
) -> DebtPlan:
    """Create the active payoff plan, retiring any previous active plan."""
    sb = get_supabase()
    sb.table("debt_plans").update({"status": "abandoned"}).eq(
        "user_id", user_id
    ).eq("status", "active").execute()
    result = (
        sb.table("debt_plans")
        .insert(
            {
                "user_id": user_id,
                "strategy": strategy,
                "monthly_budget": monthly_budget,
                "baseline_payoff_date": baseline_payoff_date,
                "baseline_total_interest": baseline_total_interest,
            }
        )
        .execute()
    )
    r = result.data[0]
    return DebtPlan(
        id=r["id"],
        user_id=r["user_id"],
        strategy=r["strategy"],
        monthly_budget=Decimal(str(r["monthly_budget"])),
        baseline_payoff_date=date.fromisoformat(r["baseline_payoff_date"]),
        baseline_total_interest=Decimal(str(r["baseline_total_interest"])),
        status=r.get("status", "active"),
        created_at=r.get("created_at"),
    )


async def update_debt_plan(plan_id: str, **fields: object) -> None:
    """Update arbitrary fields on a debt plan."""
    if not fields:
        return
    sb = get_supabase()
    sb.table("debt_plans").update(dict(fields)).eq("id", plan_id).execute()
```

- [ ] **Step 4: Sanity-check imports compile**

Run: `cd /home/ejay/Kaia/kaia && python3 -c "from database.models import Debt, DebtPayment, DebtPlan; from database import queries; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Run the full existing suite to confirm no regression**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/ -q`
Expected: all pass (same count as before this task, plus the 14 from Tasks 1–3)

- [ ] **Step 6: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/database/migrations/007_hevn_debt.sql kaia/database/models.py kaia/database/queries.py && git commit -m "feat(db): debts, debt_payments, debt_plans tables + models + CRUD (D-1)"
```

---

### Task 5: Parsers — debt mention, payment, amount

**Files:**
- Modify: `kaia/experts/hevn/parser.py`
- Test: `kaia/tests/test_hevn_debt_routing.py`

- [ ] **Step 1: Write the failing tests**

Create `kaia/tests/test_hevn_debt_routing.py`:

```python
"""Tests for Hevn's debt parsing and intent routing (Phase D-1)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from experts.hevn.parser import (
    classify_hevn_intent,
    parse_amount,
    parse_debt_mention,
    parse_debt_payment,
)


def _ai_returning(payload: dict) -> MagicMock:
    ai = MagicMock()
    ai.chat = AsyncMock(return_value=MagicMock(text=json.dumps(payload)))
    return ai


@pytest.mark.asyncio
async def test_parse_debt_mention_full_details():
    ai = _ai_returning(
        {
            "name": "BPI Credit Card",
            "debt_type": "credit_card",
            "balance": 45000,
            "interest_rate": 3.5,
            "rate_period": "monthly",
            "minimum_payment": 2250,
            "due_day": 15,
        }
    )
    parsed = await parse_debt_mention(ai, "I owe 45k on my BPI card at 3.5% monthly")
    assert parsed["name"] == "BPI Credit Card"
    assert parsed["balance"] == 45000
    assert parsed["due_day"] == 15


@pytest.mark.asyncio
async def test_parse_debt_mention_partial_fields_kept():
    # During the audit, answers like "3.5% monthly" carry no name —
    # partial dicts must still come back so the audit can merge them.
    ai = _ai_returning(
        {
            "name": None,
            "debt_type": None,
            "balance": None,
            "interest_rate": 3.5,
            "rate_period": "monthly",
            "minimum_payment": None,
            "due_day": None,
        }
    )
    parsed = await parse_debt_mention(ai, "it's 3.5% monthly")
    assert parsed is not None
    assert parsed["interest_rate"] == 3.5


@pytest.mark.asyncio
async def test_parse_debt_mention_no_debt_returns_none():
    ai = _ai_returning(
        {
            "name": None,
            "debt_type": None,
            "balance": None,
            "interest_rate": None,
            "rate_period": None,
            "minimum_payment": None,
            "due_day": None,
        }
    )
    parsed = await parse_debt_mention(ai, "nice weather today")
    assert parsed is None


@pytest.mark.asyncio
async def test_parse_debt_payment():
    ai = _ai_returning({"debt_name": "BPI", "amount": 5000})
    parsed = await parse_debt_payment(ai, "paid 5k on my BPI card")
    assert parsed == {"debt_name": "BPI", "amount": 5000}


@pytest.mark.asyncio
async def test_parse_amount():
    ai = _ai_returning({"amount": 15000})
    assert await parse_amount(ai, "I can do 15k a month") == 15000


@pytest.mark.asyncio
async def test_intent_short_circuit_debt_keywords():
    # Keyword short-circuit must not hit the AI at all.
    ai = MagicMock()
    assert await classify_hevn_intent(ai, "help me get out of debt") == "debt"
    assert await classify_hevn_intent(ai, "I owe 45k on my credit card") == "debt"
    ai.chat.assert_not_called()


@pytest.mark.asyncio
async def test_advice_questions_still_win_over_debt_keywords():
    ai = MagicMock()
    intent = await classify_hevn_intent(ai, "Should I pay off debt or invest?")
    assert intent == "general_chat"
    ai.chat.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_hevn_debt_routing.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_amount'`

- [ ] **Step 3: Write the implementation**

In `kaia/experts/hevn/parser.py`:

a) Add a debt short-circuit inside `classify_hevn_intent`, AFTER the `ADVICE_MARKERS` check and BEFORE the `health_assessment` check (debt keywords must beat the "bills" check because "loan … due" overlaps):

```python
    if any(p in low for p in (
        "debt", "owe", "utang", "loan", "credit card balance",
        "get out of debt", "pay off", "payoff",
    )):
        return "debt"
```

b) In the same function, add `"debt"` to the valid-skill set in the AI-fallback branch:

```python
            if skill in {
                "health_assessment", "budget_coaching", "goals", "bills",
                "market_trends", "education", "general_chat", "debt",
            }:
```

c) Append three parsers at the end of the file (same try/except + brace-extraction shape as `parse_goal_creation`):

```python
async def parse_debt_mention(ai: AIEngine, message: str) -> dict | None:
    """Parse debt details from a message. Returns a dict of the keys below
    (values None when not stated), or None when NO field was found.

    Partial results matter: during the guided audit the user answers one
    field at a time ("3.5% monthly"), so callers merge dicts.
    """
    system = (
        "Extract debt details from the user's message. Return ONLY a JSON "
        "object with these keys (null if not stated): "
        '{"name": string or null (lender/product, e.g. "BPI Credit Card"), '
        '"debt_type": "credit_card"|"salary_loan"|"personal_loan"|"five_six"'
        '|"pagibig_loan"|"sss_loan"|"auto_loan"|"mortgage"|"other"|null, '
        '"balance": number or null (pesos), '
        '"interest_rate": number or null (percent, as quoted), '
        '"rate_period": "monthly"|"yearly"|null, '
        '"minimum_payment": number or null, '
        '"due_day": integer 1-31 or null}. '
        "Treat shorthand like '45k' as 45000. If the message has no debt "
        "details at all, return every key as null."
    )
    try:
        response = await ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": message}],
            max_tokens=200,
        )
        text = response.text.strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            return None
        keys = (
            "name", "debt_type", "balance", "interest_rate",
            "rate_period", "minimum_payment", "due_day",
        )
        result = {k: parsed.get(k) for k in keys}
        if all(v is None for v in result.values()):
            return None
        return result
    except Exception as exc:
        logger.debug("parse_debt_mention failed: {}", exc)
        return None


async def parse_debt_payment(ai: AIEngine, message: str) -> dict | None:
    """Parse 'paid 5k on my BPI card' -> {"debt_name": ..., "amount": ...}."""
    system = (
        "The user reports paying money toward a debt. Return ONLY a JSON "
        'object: {"debt_name": string or null, "amount": number or null '
        "(pesos; treat '5k' as 5000)}. If this is not a debt payment, "
        "return both as null."
    )
    try:
        response = await ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": message}],
            max_tokens=80,
        )
        text = response.text.strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict) or parsed.get("amount") is None:
            return None
        return {"debt_name": parsed.get("debt_name"), "amount": parsed["amount"]}
    except Exception as exc:
        logger.debug("parse_debt_payment failed: {}", exc)
        return None


async def parse_amount(ai: AIEngine, message: str) -> float | None:
    """Parse a single peso amount from a free-form answer."""
    system = (
        "Extract the single peso amount the user states. Return ONLY a JSON "
        'object: {"amount": number or null}. Treat \'15k\' as 15000.'
    )
    try:
        response = await ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": message}],
            max_tokens=40,
        )
        text = response.text.strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        parsed = json.loads(text[start:end + 1])
        amount = parsed.get("amount") if isinstance(parsed, dict) else None
        return float(amount) if amount is not None else None
    except Exception as exc:
        logger.debug("parse_amount failed: {}", exc)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_hevn_debt_routing.py tests/test_intent_detector.py -v`
Expected: all PASS (including pre-existing intent tests — the new short-circuit must not break them)

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/experts/hevn/parser.py kaia/tests/test_hevn_debt_routing.py && git commit -m "feat(hevn): debt/payment/amount parsers + debt intent short-circuit (D-1)"
```

---

### Task 6: Prompts — debt route, debts_summary, PH debt expertise

**Files:**
- Modify: `kaia/experts/hevn/prompts.py`
- Test: `kaia/tests/test_hevn_debt_routing.py`

- [ ] **Step 1: Write the failing tests**

Append to `kaia/tests/test_hevn_debt_routing.py`:

```python
from experts.hevn.prompts import HEVN_INTENT_PROMPT, build_hevn_system_prompt


def test_intent_prompt_includes_debt_skill():
    assert "- debt:" in HEVN_INTENT_PROMPT


def test_system_prompt_includes_debts_summary():
    prompt = build_hevn_system_prompt(
        user_context="",
        budget_summary="",
        goals_summary="",
        current_gap="",
        debts_summary="2 active debts, ₱65,000 total",
    )
    assert "2 active debts" in prompt
    assert "Debt Counseling Expertise" in prompt


def test_system_prompt_debts_summary_defaults_empty():
    prompt = build_hevn_system_prompt(
        user_context="", budget_summary="", goals_summary="", current_gap=""
    )
    assert "(no debts on file)" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_hevn_debt_routing.py -v`
Expected: new 3 FAIL (`assert "- debt:" in …` / `TypeError: unexpected keyword argument 'debts_summary'`)

- [ ] **Step 3: Implement the prompt changes**

In `kaia/experts/hevn/prompts.py`:

a) In `HEVN_SYSTEM_PROMPT`, after the `# Your Communication Style` block and before `# Proactive Information Gathering`, insert:

```
# Debt Counseling Expertise
- You are also a debt counselor: zero judgment, all plan.
- PH debt landscape you know cold: credit-card monthly add-on rates and the
  BSP finance-charge cap, bank salary loans, 5-6 informal lending (~20%/mo
  effective), Pag-IBIG MPL and SSS salary loan terms, balance-transfer
  promos, bank debt-consolidation products.
- Avalanche = highest rate first (cheapest). Snowball = smallest balance
  first (most motivating). The right one depends on the user, not just math.
- NEVER do payoff arithmetic yourself — the debt engine computes all
  numbers. You present and explain them.
```

b) In `HEVN_SYSTEM_PROMPT`, after the `# Their Active Goals\n{goals_summary}` block, insert:

```
# Their Debts & Payoff Plan
{debts_summary}
```

c) In `HEVN_INTENT_PROMPT`, add to the skills list (after the `- bills:` line):

```
- debt: User wants to RECORD or MANAGE debts, payments, or their payoff
  plan. "I owe 45k on my credit card", "I paid 5k on my loan", "help me
  get out of debt", "show my debt plan", "how's my debt progress".
```

and extend the CRITICAL examples block at the top with:

```
  "Should I pay off debt or invest?"        → general_chat (wants advice)
  "I paid 5,000 on my BPI card"             → debt (records a payment)
```

d) Update `build_hevn_system_prompt`:

```python
def build_hevn_system_prompt(
    user_context: str,
    budget_summary: str,
    goals_summary: str,
    current_gap: str,
    debts_summary: str = "",
) -> str:
    """Render Hevn's full system prompt with runtime context."""
    return HEVN_SYSTEM_PROMPT.format(
        current_gap=current_gap or "(none — all critical info known)",
        user_context=user_context or "(no profile data yet)",
        budget_summary=budget_summary or "(no recent budget data)",
        goals_summary=goals_summary or "(no active goals yet)",
        debts_summary=debts_summary or "(no debts on file)",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_hevn_debt_routing.py tests/test_hevn_classifier.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/experts/hevn/prompts.py kaia/tests/test_hevn_debt_routing.py && git commit -m "feat(hevn): debt intent route + debts_summary + PH debt expertise in prompts (D-1)"
```

---

### Task 7: `DebtCoachSkill` — summaries, progress, payments

**Files:**
- Create: `kaia/experts/hevn/skills/debt_coach.py`
- Test: `kaia/tests/test_debt_coach.py`

- [ ] **Step 1: Write the failing tests**

Create `kaia/tests/test_debt_coach.py`:

```python
"""Tests for DebtCoachSkill (Phase D-1) — db and AI fully mocked."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from database.models import Debt, DebtPlan
from experts.hevn.skills.debt_coach import DebtCoachSkill


def _debt(**kw) -> Debt:
    base = dict(
        id="debt-1",
        user_id="u1",
        name="BPI Credit Card",
        debt_type="credit_card",
        balance=Decimal("45000"),
        interest_rate=Decimal("3.5"),
        rate_period="monthly",
        minimum_payment=Decimal("2250"),
        due_day=15,
    )
    base.update(kw)
    return Debt(**base)


def _plan(**kw) -> DebtPlan:
    base = dict(
        id="plan-1",
        user_id="u1",
        strategy="avalanche",
        monthly_budget=Decimal("10000"),
        baseline_payoff_date=date(2027, 1, 1),
        baseline_total_interest=Decimal("5000"),
    )
    base.update(kw)
    return DebtPlan(**base)


def _user():
    user = MagicMock()
    user.id = "u1"
    user.telegram_id = 12345
    user.currency = "PHP"
    user.timezone = "Asia/Manila"
    return user


def _ai_returning(payload: dict) -> MagicMock:
    ai = MagicMock()
    ai.chat = AsyncMock(return_value=MagicMock(text=json.dumps(payload)))
    return ai


@pytest.mark.asyncio
async def test_debts_summary_lists_debts_and_plan(monkeypatch):
    skill = DebtCoachSkill()
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_debts",
        AsyncMock(return_value=[_debt()]),
    )
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_active_debt_plan",
        AsyncMock(return_value=_plan()),
    )
    text = await skill.debts_summary("u1", "PHP")
    assert "BPI Credit Card" in text
    assert "45,000" in text
    assert "avalanche" in text


@pytest.mark.asyncio
async def test_debts_summary_empty_when_no_debts(monkeypatch):
    skill = DebtCoachSkill()
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_debts", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_active_debt_plan",
        AsyncMock(return_value=None),
    )
    assert await skill.debts_summary("u1", "PHP") == ""


@pytest.mark.asyncio
async def test_record_payment_updates_balance_and_logs(monkeypatch):
    skill = DebtCoachSkill()
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_debts",
        AsyncMock(return_value=[_debt()]),
    )
    update = AsyncMock()
    log_payment = AsyncMock()
    monkeypatch.setattr("experts.hevn.skills.debt_coach.db.update_debt", update)
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.create_debt_payment", log_payment
    )
    ai = _ai_returning({"debt_name": "BPI", "amount": 5000})

    text = await skill.record_payment(ai, _user(), "paid 5k on my BPI card", "PHP")

    assert text is not None and "40,000" in text
    update.assert_awaited_once_with("debt-1", balance=40000.0)
    log_payment.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_payment_full_payoff_celebrates(monkeypatch):
    skill = DebtCoachSkill()
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_debts",
        AsyncMock(return_value=[_debt(balance=Decimal("5000"))]),
    )
    update = AsyncMock()
    monkeypatch.setattr("experts.hevn.skills.debt_coach.db.update_debt", update)
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.create_debt_payment", AsyncMock()
    )
    ai = _ai_returning({"debt_name": "BPI", "amount": 5000})

    text = await skill.record_payment(ai, _user(), "paid the last 5k on BPI", "PHP")

    assert "🎉" in text
    update.assert_awaited_once_with("debt-1", balance=0.0, status="paid_off")


@pytest.mark.asyncio
async def test_record_payment_unknown_debt_returns_none(monkeypatch):
    skill = DebtCoachSkill()
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_debts",
        AsyncMock(return_value=[_debt()]),
    )
    ai = _ai_returning({"debt_name": "Home Credit", "amount": 5000})
    text = await skill.record_payment(ai, _user(), "paid 5k on Home Credit", "PHP")
    assert text is None


@pytest.mark.asyncio
async def test_format_progress_reports_ahead_or_behind(monkeypatch):
    skill = DebtCoachSkill()
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_debts",
        AsyncMock(return_value=[_debt(balance=Decimal("20000"))]),
    )
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_active_debt_plan",
        AsyncMock(return_value=_plan(baseline_payoff_date=date(2030, 1, 1))),
    )
    text = await skill.format_progress("u1", "PHP")
    assert "Debt Plan Progress" in text
    assert "20,000" in text


@pytest.mark.asyncio
async def test_format_progress_without_plan_prompts_audit(monkeypatch):
    skill = DebtCoachSkill()
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_debts", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_active_debt_plan",
        AsyncMock(return_value=None),
    )
    text = await skill.format_progress("u1", "PHP")
    assert "audit" in text.lower() or "get out of debt" in text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_coach.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'experts.hevn.skills.debt_coach'`

- [ ] **Step 3: Write the implementation**

Create `kaia/experts/hevn/skills/debt_coach.py`:

```python
"""Debt Coach skill — guided audit, payoff plan, progress, payments (D-1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from loguru import logger

from config.constants import CURRENCY_SYMBOLS
from database import queries as db
from database.models import Debt
from experts.hevn.skills import debt_math
from experts.hevn.skills.debt_math import DebtInput

# Typical PH monthly rates used (and labeled) when the user doesn't know.
RATE_DEFAULTS: dict[str, Decimal] = {
    "credit_card": Decimal("3.0"),
    "salary_loan": Decimal("1.25"),
    "personal_loan": Decimal("2.0"),
    "five_six": Decimal("20.0"),
    "pagibig_loan": Decimal("0.85"),
    "sss_loan": Decimal("0.83"),
    "auto_loan": Decimal("1.0"),
    "mortgage": Decimal("0.6"),
    "other": Decimal("2.0"),
}

MAX_MONTHLY_RATE = Decimal("25")  # sanity bound on quoted monthly %

UNSURE_MARKERS = ("not sure", "don't know", "dont know", "di ko alam", "idk", "no idea")
SKIP_MARKERS = ("skip", "none", "wala")
CANCEL_MARKERS = ("cancel", "stop", "never mind", "nevermind")


def to_debt_input(debt: Debt) -> DebtInput:
    """Convert a stored Debt into the simulator's input snapshot."""
    rate = debt_math.monthly_rate(debt.interest_rate, debt.rate_period)
    minimum = debt.minimum_payment or debt_math.default_minimum(debt.balance)
    return DebtInput(
        debt_id=debt.id,
        name=debt.name,
        balance=debt.balance,
        monthly_rate=rate,
        minimum_payment=minimum,
    )


@dataclass
class AuditSession:
    """In-memory cursor for one user's guided debt audit.

    Stages: collect -> more -> budget -> strategy. Each completed debt is
    persisted immediately, so losing this object never loses data.
    """

    stage: str = "collect"
    current: dict = field(default_factory=dict)
    captured: int = 0
    comparison: "debt_math.StrategyComparison | None" = None
    budget: Decimal | None = None


class DebtCoachSkill:
    """Professional debt payoff coaching backed by deterministic math."""

    def __init__(self) -> None:
        self._sessions: dict[str, AuditSession] = {}

    # ── Session plumbing ────────────────────────────────────────────

    def has_session(self, user_id: str) -> bool:
        return user_id in self._sessions

    def clear_session(self, user_id: str) -> None:
        self._sessions.pop(user_id, None)

    # ── Summaries / progress ────────────────────────────────────────

    async def debts_summary(self, user_id: str, currency: str = "PHP") -> str:
        """One-line-per-debt summary injected into Hevn's system prompt.

        Returns "" when the user has no active debts (caller substitutes
        the placeholder).
        """
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        debts = await db.get_debts(user_id, status="active")
        if not debts:
            return ""
        lines = []
        for d in debts:
            est = " (rate est.)" if d.rate_is_estimate else ""
            minimum = (
                f", min {symbol}{float(d.minimum_payment):,.0f}"
                if d.minimum_payment
                else ""
            )
            lines.append(
                f"- {d.name} [{d.debt_type}]: {symbol}{float(d.balance):,.0f} "
                f"at {float(d.interest_rate)}%/{d.rate_period[:2]}{est}{minimum}"
            )
        plan = await db.get_active_debt_plan(user_id)
        if plan:
            lines.append(
                f"Active payoff plan: {plan.strategy}, "
                f"{symbol}{float(plan.monthly_budget):,.0f}/mo, "
                f"baseline debt-free {plan.baseline_payoff_date.strftime('%b %Y')}"
            )
        return "\n".join(lines)

    async def format_progress(self, user_id: str, currency: str = "PHP") -> str:
        """Recompute the plan from current balances vs the baseline."""
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        debts = await db.get_debts(user_id, status="active")
        plan = await db.get_active_debt_plan(user_id)

        if not debts and plan:
            await db.update_debt_plan(plan.id, status="completed")
            return (
                "🎉 *You are DEBT-FREE!* Every debt on your plan is paid off. "
                "I'm genuinely proud of you. Next: let's redirect that monthly "
                "budget into your goals."
            )
        if not debts:
            return (
                "You have no debts on file. If you want to start a payoff "
                "plan, just say *help me get out of debt* and I'll run a "
                "quick debt audit with you."
            )
        if plan is None:
            total = sum(float(d.balance) for d in debts)
            return (
                f"You have {len(debts)} debt(s) totalling {symbol}{total:,.0f}, "
                "but no payoff plan yet. Say *help me get out of debt* and "
                "I'll build one with you."
            )

        result = debt_math.amortize(
            [to_debt_input(d) for d in debts],
            plan.monthly_budget,
            plan.strategy,
            date.today(),
        )
        lines = [f"📊 *Debt Plan Progress* ({plan.strategy})", ""]
        for d in debts:
            lines.append(f"• {d.name}: {symbol}{float(d.balance):,.0f}")
        lines.append("")
        if not result.ok:
            lines.append(
                "⚠️ At your current balances the plan no longer closes out — "
                "let's revisit your monthly budget. Say *help me get out of "
                "debt* to rebuild the plan."
            )
            return "\n".join(lines)

        projected = result.debt_free_date
        baseline = plan.baseline_payoff_date
        months_delta = (baseline.year - projected.year) * 12 + (
            baseline.month - projected.month
        )
        lines.append(
            f"Projected debt-free: *{projected.strftime('%b %Y')}* "
            f"(baseline {baseline.strftime('%b %Y')})"
        )
        if months_delta > 0:
            lines.append(f"✅ You're {months_delta} month(s) AHEAD of plan. 🎉")
        elif months_delta < 0:
            lines.append(
                f"⚠️ You're {-months_delta} month(s) behind plan — small "
                "catch-up payments fix this faster than you'd think."
            )
        else:
            lines.append("✅ Right on schedule.")
        lines.append(
            f"Remaining interest if you stay the course: "
            f"{symbol}{float(result.total_interest):,.0f}"
        )
        return "\n".join(lines)

    # ── Payments ────────────────────────────────────────────────────

    async def record_payment(
        self, ai, user, message: str, currency: str = "PHP"
    ) -> str | None:
        """Parse and apply a payment. Returns None when no match (caller
        falls through to other handling)."""
        from experts.hevn.parser import parse_debt_payment

        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        parsed = await parse_debt_payment(ai, message)
        if not parsed:
            return None
        debts = await db.get_debts(user.id, status="active")
        if not debts:
            return None

        name = (parsed.get("debt_name") or "").casefold()
        match: Debt | None = None
        if name:
            for d in debts:
                if name in d.name.casefold() or d.name.casefold() in name:
                    match = d
                    break
        elif len(debts) == 1:
            match = debts[0]
        if match is None:
            return None

        amount = Decimal(str(parsed["amount"]))
        if amount <= 0:
            return None
        new_balance = max(match.balance - amount, Decimal("0"))
        if new_balance == 0:
            await db.update_debt(match.id, balance=float(new_balance), status="paid_off")
        else:
            await db.update_debt(match.id, balance=float(new_balance))
        await db.create_debt_payment(
            debt_id=match.id,
            user_id=user.id,
            amount=float(amount),
            balance_after=float(new_balance),
            paid_on=date.today().isoformat(),
        )
        if new_balance == 0:
            return (
                f"🎉 *{match.name} is PAID OFF!* That {symbol}{float(amount):,.0f} "
                "closed it out completely. One debt down — your freed-up payment "
                "now hits the next debt on the plan even harder."
            )
        return (
            f"✅ Logged {symbol}{float(amount):,.0f} against *{match.name}* — "
            f"new balance {symbol}{float(new_balance):,.0f}. Ask me *how's my "
            f"debt progress* anytime."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_coach.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/experts/hevn/skills/debt_coach.py kaia/tests/test_debt_coach.py && git commit -m "feat(hevn): DebtCoachSkill summaries, progress, payment recording (D-1)"
```

---

### Task 8: `DebtCoachSkill` — the guided audit state machine

**Files:**
- Modify: `kaia/experts/hevn/skills/debt_coach.py`
- Test: `kaia/tests/test_debt_coach.py`

- [ ] **Step 1: Write the failing tests**

Append to `kaia/tests/test_debt_coach.py`:

```python
def _ai_seq(payloads: list[dict]) -> MagicMock:
    """AI mock returning each JSON payload in sequence."""
    ai = MagicMock()
    ai.chat = AsyncMock(
        side_effect=[MagicMock(text=json.dumps(p)) for p in payloads]
    )
    return ai


_NULL_DEBT = {
    "name": None, "debt_type": None, "balance": None, "interest_rate": None,
    "rate_period": None, "minimum_payment": None, "due_day": None,
}


@pytest.mark.asyncio
async def test_audit_full_flow_one_debt_to_plan(monkeypatch):
    skill = DebtCoachSkill()
    user = _user()
    created: list[dict] = []

    async def fake_create_debt(**kw):
        created.append(kw)
        return _debt(id="new-1", name=kw["name"], balance=Decimal(str(kw["balance"])))

    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.create_debt", fake_create_debt
    )
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_debts",
        AsyncMock(return_value=[
            _debt(id="new-1", balance=Decimal("45000"),
                  minimum_payment=Decimal("2250"))
        ]),
    )
    plan_created: list[dict] = []

    async def fake_create_plan(**kw):
        plan_created.append(kw)
        return _plan(strategy=kw["strategy"])

    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.create_debt_plan", fake_create_plan
    )

    # Start
    intro = skill.start_audit(user.id)
    assert "debt" in intro.lower()
    assert skill.has_session(user.id)

    # One message gives everything for debt #1
    ai = _ai_seq([{
        "name": "BPI Credit Card", "debt_type": "credit_card",
        "balance": 45000, "interest_rate": 3.5, "rate_period": "monthly",
        "minimum_payment": 2250, "due_day": 15,
    }])
    reply = await skill.continue_audit(
        ai, user, "BPI credit card, 45k at 3.5% monthly, min 2250 due on the 15th", "PHP"
    )
    assert created and created[0]["name"] == "BPI Credit Card"
    assert "other debts" in reply.lower()

    # No more debts -> asks for budget
    ai2 = MagicMock()  # "no" is keyword-detected; AI must not be called
    reply = await skill.continue_audit(ai2, user, "no, that's all", "PHP")
    assert "month" in reply.lower()  # asks for monthly budget

    # Budget -> comparison presented
    ai3 = _ai_seq([{"amount": 10000}])
    reply = await skill.continue_audit(ai3, user, "10k a month", "PHP")
    assert "Avalanche" in reply and "Snowball" in reply

    # Strategy choice -> plan persisted, session ends
    ai4 = MagicMock()
    reply = await skill.continue_audit(ai4, user, "avalanche", "PHP")
    assert plan_created and plan_created[0]["strategy"] == "avalanche"
    assert not skill.has_session(user.id)


@pytest.mark.asyncio
async def test_audit_unknown_rate_uses_labeled_default(monkeypatch):
    skill = DebtCoachSkill()
    user = _user()
    created: list[dict] = []

    async def fake_create_debt(**kw):
        created.append(kw)
        return _debt(id="new-1")

    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.create_debt", fake_create_debt
    )

    skill.start_audit(user.id)
    ai = _ai_seq([{
        "name": "Citibank Card", "debt_type": "credit_card", "balance": 30000,
        "interest_rate": None, "rate_period": None,
        "minimum_payment": 1500, "due_day": 10,
    }])
    await skill.continue_audit(ai, user, "Citibank card, 30k, min 1500 due 10th", "PHP")

    # rate missing -> asked; "not sure" applies the credit_card default
    ai2 = MagicMock()
    await skill.continue_audit(ai2, user, "not sure", "PHP")
    assert created
    assert created[0]["interest_rate"] == 3.0
    assert created[0]["rate_is_estimate"] is True


@pytest.mark.asyncio
async def test_audit_shortfall_ends_without_plan(monkeypatch):
    skill = DebtCoachSkill()
    user = _user()
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.create_debt",
        AsyncMock(return_value=_debt(id="new-1")),
    )
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_debts",
        AsyncMock(return_value=[
            _debt(id="new-1", balance=Decimal("45000"),
                  minimum_payment=Decimal("2250"))
        ]),
    )
    create_plan = AsyncMock()
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.create_debt_plan", create_plan
    )

    skill.start_audit(user.id)
    ai = _ai_seq([{
        "name": "BPI Credit Card", "debt_type": "credit_card",
        "balance": 45000, "interest_rate": 3.5, "rate_period": "monthly",
        "minimum_payment": 2250, "due_day": 15,
    }])
    await skill.continue_audit(ai, user, "BPI card 45k 3.5% monthly min 2250 due 15", "PHP")
    await skill.continue_audit(MagicMock(), user, "no", "PHP")

    # Budget below the 2,250 minimum -> shortfall advice, no plan, session ends
    ai2 = _ai_seq([{"amount": 2000}])
    reply = await skill.continue_audit(ai2, user, "2000", "PHP")
    assert "minimum" in reply.lower()
    create_plan.assert_not_awaited()
    assert not skill.has_session(user.id)


@pytest.mark.asyncio
async def test_audit_cancel_clears_session():
    skill = DebtCoachSkill()
    user = _user()
    skill.start_audit(user.id)
    reply = await skill.continue_audit(MagicMock(), user, "cancel", "PHP")
    assert not skill.has_session(user.id)
    assert "resume" in reply.lower() or "anytime" in reply.lower()


@pytest.mark.asyncio
async def test_entry_point_routes_by_state(monkeypatch):
    skill = DebtCoachSkill()
    user = _user()
    # No debts -> starts the audit
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_debts", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_active_debt_plan",
        AsyncMock(return_value=None),
    )
    text = await skill.entry_point(MagicMock(), user, "help me get out of debt", "PHP")
    assert skill.has_session(user.id)
    assert "audit" in text.lower() or "one at a time" in text.lower()
    skill.clear_session(user.id)

    # Debts but no plan -> jumps straight to the budget question
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.get_debts",
        AsyncMock(return_value=[_debt()]),
    )
    text = await skill.entry_point(MagicMock(), user, "help me get out of debt", "PHP")
    assert skill.has_session(user.id)
    assert skill._sessions[user.id].stage == "budget"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_coach.py -v`
Expected: prior 7 PASS, new 5 FAIL with `AttributeError: ... 'start_audit'`

- [ ] **Step 3: Write the implementation**

Append to the `DebtCoachSkill` class in `kaia/experts/hevn/skills/debt_coach.py`:

```python
    # ── Guided audit state machine ──────────────────────────────────

    AUDIT_FIELDS = ("name", "balance", "interest_rate", "minimum_payment", "due_day")

    AUDIT_QUESTIONS = {
        "name": (
            "Who do you owe, and what kind of debt is it? "
            "(e.g. *BPI credit card*, *SSS salary loan*, *5-6*)"
        ),
        "balance": "How much is the current outstanding balance?",
        "interest_rate": (
            "What's the interest rate? (If you're not sure, say *not sure* "
            "and I'll use a typical rate for that type.)"
        ),
        "minimum_payment": (
            "What's the minimum monthly payment? (*not sure* is fine.)"
        ),
        "due_day": "What day of the month is it due? (1–31, or *skip*)",
    }

    def start_audit(self, user_id: str) -> str:
        """Open an audit session and return Hevn's intro + first question."""
        self._sessions[user_id] = AuditSession()
        return (
            "💪 Let's get you out of debt — for real, with a plan.\n\n"
            "First I need a quick *debt audit*: I'll ask about each debt "
            "one at a time (who you owe, balance, rate, minimum payment). "
            "Takes 2 minutes, zero judgment.\n\n"
            f"{self.AUDIT_QUESTIONS['name']}"
        )

    async def entry_point(self, ai, user, message: str, currency: str) -> str:
        """'Help me get out of debt' router: audit, budget, or progress."""
        debts = await db.get_debts(user.id, status="active")
        if not debts:
            return self.start_audit(user.id)
        plan = await db.get_active_debt_plan(user.id)
        if plan is None:
            session = AuditSession(stage="budget", captured=len(debts))
            self._sessions[user.id] = session
            symbol = CURRENCY_SYMBOLS.get(currency, currency)
            total = sum(float(d.balance) for d in debts)
            return (
                f"I already have {len(debts)} debt(s) on file totalling "
                f"{symbol}{total:,.0f}. One number and I'll build your plan: "
                "how much can you put toward debt each month, in total "
                "(minimums included)?"
            )
        return await self.format_progress(user.id, currency)

    async def continue_audit(self, ai, user, message: str, currency: str) -> str:
        """Advance the audit state machine by one user message."""
        session = self._sessions.get(user.id)
        if session is None:
            return await self.entry_point(ai, user, message, currency)

        low = message.lower().strip()
        if any(m in low for m in CANCEL_MARKERS):
            self.clear_session(user.id)
            return (
                "No problem — everything you've told me so far is saved. "
                "Say *help me get out of debt* anytime to resume."
            )

        if session.stage == "collect":
            return await self._audit_collect(ai, user, message, low, session, currency)
        if session.stage == "more":
            return await self._audit_more(ai, user, message, low, session, currency)
        if session.stage == "budget":
            return await self._audit_budget(ai, user, message, session, currency)
        if session.stage == "strategy":
            return await self._audit_strategy(user, low, session, currency)
        # Unknown stage — fail safe by closing the session.
        self.clear_session(user.id)
        return "Let's start over — say *help me get out of debt*."

    def _next_missing(self, current: dict) -> str | None:
        for fld in self.AUDIT_FIELDS:
            if fld not in current:
                return fld
        return None

    async def _audit_collect(
        self, ai, user, message: str, low: str, session: AuditSession, currency: str
    ) -> str:
        from experts.hevn.parser import parse_debt_mention

        pending = self._next_missing(session.current)

        if any(m in low for m in UNSURE_MARKERS) and pending in (
            "interest_rate", "minimum_payment"
        ):
            if pending == "interest_rate":
                debt_type = session.current.get("debt_type") or "other"
                session.current["interest_rate"] = RATE_DEFAULTS.get(
                    debt_type, RATE_DEFAULTS["other"]
                )
                session.current["rate_period"] = "monthly"
                session.current["rate_is_estimate"] = True
            else:
                session.current["minimum_payment"] = None
        elif any(m in low for m in SKIP_MARKERS) and pending == "due_day":
            session.current["due_day"] = None
        else:
            parsed = await parse_debt_mention(ai, message)
            if parsed:
                for key, value in parsed.items():
                    if value is not None and key not in session.current:
                        session.current[key] = value
            elif pending is not None:
                return (
                    "I didn't catch that — "
                    f"{self.AUDIT_QUESTIONS[pending]}"
                )

        # Sanity: cap absurd monthly rates rather than store garbage.
        rate = session.current.get("interest_rate")
        if rate is not None and Decimal(str(rate)) > MAX_MONTHLY_RATE:
            del session.current["interest_rate"]
            return (
                f"That rate looks unusually high (above {MAX_MONTHLY_RATE}%/mo). "
                "Can you double-check it? Quote it exactly as the lender states it."
            )

        nxt = self._next_missing(session.current)
        if nxt is not None:
            return self.AUDIT_QUESTIONS[nxt]
        return await self._audit_save_current(user, session, currency)

    async def _audit_save_current(
        self, user, session: AuditSession, currency: str
    ) -> str:
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        cur = session.current
        debt = await db.create_debt(
            user_id=user.id,
            name=str(cur["name"]),
            balance=float(cur["balance"]),
            interest_rate=float(cur["interest_rate"]),
            debt_type=str(cur.get("debt_type") or "other"),
            rate_period=str(cur.get("rate_period") or "monthly"),
            rate_is_estimate=bool(cur.get("rate_is_estimate", False)),
            minimum_payment=(
                float(cur["minimum_payment"])
                if cur.get("minimum_payment") is not None
                else None
            ),
            due_day=cur.get("due_day"),
        )
        session.captured += 1
        session.current = {}
        session.stage = "more"
        est = " (estimated rate)" if debt.rate_is_estimate else ""
        return (
            f"✅ Got it: *{debt.name}* — {symbol}{float(debt.balance):,.0f} at "
            f"{float(debt.interest_rate)}%/{debt.rate_period[:2]}{est}.\n\n"
            "Any other debts? (yes / no)"
        )

    async def _audit_more(
        self, ai, user, message: str, low: str, session: AuditSession, currency: str
    ) -> str:
        from experts.hevn.parser import parse_debt_mention

        if low.startswith("no") or "that's all" in low or "thats all" in low or "wala na" in low:
            session.stage = "budget"
            return (
                f"That's {session.captured} debt(s) on file. Now the key "
                "number: how much can you put toward debt each month, in "
                "TOTAL (minimum payments included)?"
            )
        session.stage = "collect"
        # The "yes" may already carry details ("yes, a Home Credit loan, 30k").
        parsed = await parse_debt_mention(ai, message) if not low.startswith("yes") or len(low) > 8 else None
        if parsed:
            session.current = {k: v for k, v in parsed.items() if v is not None}
        nxt = self._next_missing(session.current)
        return self.AUDIT_QUESTIONS[nxt] if nxt else await self._audit_save_current(
            user, session, currency
        )

    async def _audit_budget(
        self, ai, user, message: str, session: AuditSession, currency: str
    ) -> str:
        from experts.hevn.parser import parse_amount

        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        amount = await parse_amount(ai, message)
        if amount is None or amount <= 0:
            return (
                "Give me one number — how many pesos per month can go to "
                "debt in total? (e.g. *10,000*)"
            )
        budget = Decimal(str(amount))
        debts = await db.get_debts(user.id, status="active")
        inputs = [to_debt_input(d) for d in debts]
        comp = debt_math.compare_strategies(inputs, budget, date.today())

        if not comp.avalanche.ok and comp.avalanche.error == "shortfall":
            self.clear_session(user.id)
            short = comp.avalanche.shortfall or Decimal("0")
            minimums = budget + short
            return (
                f"⚠️ Real talk: your minimum payments alone are "
                f"{symbol}{float(minimums):,.0f}/mo — "
                f"{symbol}{float(budget):,.0f} won't cover them "
                f"(short {symbol}{float(short):,.0f}).\n\n"
                "This is fixable. Your options:\n"
                "1. *Balance transfer* — move card debt to a lower-rate card\n"
                "2. *Consolidation loan* — one lower-rate loan pays off the rest\n"
                "3. *Restructure* — call your bank; they'd rather restructure "
                "than have you default\n"
                "4. *Pag-IBIG MPL / SSS salary loan* — much cheaper money "
                "if you qualify\n\n"
                "Want to talk through any of these? Or if you can free up "
                "more per month, say *help me get out of debt* and we'll "
                "rebuild the plan."
            )
        if not comp.avalanche.ok and comp.avalanche.error == "non_amortizing":
            self.clear_session(user.id)
            names = ", ".join(comp.avalanche.problem_debts)
            return (
                f"⚠️ At that budget, *{names}* never pays off — the payment "
                "doesn't even cover its monthly interest. That debt needs "
                "either a bigger payment or a restructure/consolidation. "
                "Let's free up more budget or talk restructuring options."
            )

        session.budget = budget
        session.comparison = comp
        session.stage = "strategy"
        strategy, reason = debt_math.recommend_strategy(comp)
        av, sn = comp.avalanche, comp.snowball
        first_sn = sn.payoffs[0] if sn.payoffs else None
        lines = [
            f"💪 With {symbol}{float(budget):,.0f}/mo, two ways to attack this:",
            "",
            f"🏔️ *Avalanche* (highest rate first)",
            f"   Debt-free: *{av.debt_free_date.strftime('%b %Y')}* — total "
            f"interest {symbol}{float(av.total_interest):,.0f}",
            "",
            f"⛄ *Snowball* (smallest balance first)",
            f"   Debt-free: *{sn.debt_free_date.strftime('%b %Y')}* — total "
            f"interest {symbol}{float(sn.total_interest):,.0f}",
        ]
        if comp.interest_saved_by_avalanche > 0:
            lines.append(
                f"   (costs {symbol}{float(comp.interest_saved_by_avalanche):,.0f} "
                "more than avalanche)"
            )
        if first_sn:
            lines.append(
                f"   First debt cleared in {first_sn.payoff_month} month(s) — "
                "quick win."
            )
        lines.extend([
            "",
            f"🎯 My recommendation: *{strategy}*. {reason}",
            "",
            "Which one do you want — *avalanche* or *snowball*?",
        ])
        return "\n".join(lines)

    async def _audit_strategy(
        self, user, low: str, session: AuditSession, currency: str
    ) -> str:
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        if "avalanche" in low:
            strategy = "avalanche"
        elif "snowball" in low:
            strategy = "snowball"
        else:
            return "Just say the word: *avalanche* or *snowball*?"

        comp = session.comparison
        chosen = comp.avalanche if strategy == "avalanche" else comp.snowball
        await db.create_debt_plan(
            user_id=user.id,
            strategy=strategy,
            monthly_budget=float(session.budget),
            baseline_payoff_date=chosen.debt_free_date.isoformat(),
            baseline_total_interest=float(chosen.total_interest),
        )
        self.clear_session(user.id)
        return (
            f"🎯 *Your {strategy} plan is live.*\n\n"
            f"• {symbol}{float(session.budget):,.0f}/mo toward debt\n"
            f"• Debt-free date: *{chosen.debt_free_date.strftime('%B %Y')}*\n"
            f"• Total interest on plan: {symbol}{float(chosen.total_interest):,.0f}\n\n"
            "I'll nudge you before due dates and review progress monthly. "
            "When you make a payment, just tell me — *paid 5k on my BPI card* "
            "— and I'll track it. Let's go. 💪"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_coach.py -v`
Expected: 12 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/experts/hevn/skills/debt_coach.py kaia/tests/test_debt_coach.py && git commit -m "feat(hevn): guided debt audit state machine + plan creation (D-1)"
```

---

### Task 9: Wire DebtCoach into `HevnExpert`

**Files:**
- Modify: `kaia/experts/hevn/expert.py`
- Test: `kaia/tests/test_debt_coach.py`

- [ ] **Step 1: Write the failing test**

Append to `kaia/tests/test_debt_coach.py`:

```python
from experts.hevn import HevnExpert


def test_hevn_expert_has_debt_skill():
    ai = MagicMock()
    hevn = HevnExpert(ai_engine=ai)
    assert isinstance(hevn.debt, DebtCoachSkill)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_coach.py::test_hevn_expert_has_debt_skill -v`
Expected: FAIL — `AttributeError: 'HevnExpert' object has no attribute 'debt'`

- [ ] **Step 3: Implement the wiring**

In `kaia/experts/hevn/expert.py`:

a) Add the import (with the other skill imports):

```python
from experts.hevn.skills.debt_coach import DebtCoachSkill
```

b) In `__init__`, after `self.proactive = ProactiveAlertsSkill()`:

```python
        self.debt = DebtCoachSkill()
```

c) In `_direct_answer`, immediately after the `currency = …` line and BEFORE the first-visit onboarding block, add the audit interception (mid-audit replies like "3.5%" must never go through intent classification):

```python
        # Mid-audit messages bypass intent classification entirely.
        if self.debt.has_session(user.id):
            text = await self.debt.continue_audit(self.ai, user, message, currency)
            await self._after_debt_turn(user)
            footer = self.format_response_footer(channel)
            await self.save_messages(user.id, channel.channel_id, message, text)
            return SkillResult(text=f"{text}{footer}", skill_name=channel.channel_id)
```

d) In the intent dispatch block of `_direct_answer`, add a route (after the `budget_coaching` elif):

```python
        elif intent == "debt":
            specialized_text = await self._run_debt(user, message, currency)
```

e) Add the route handler with the other specialized routes (after `_run_coaching`):

```python
    async def _run_debt(self, user: User, message: str, currency: str) -> str:
        """Debt intent router: payment > progress > entry (audit/plan)."""
        low = message.lower()
        if any(k in low for k in ("paid", "i pay", "nabayaran", "binayaran", "payment")):
            text = await self.debt.record_payment(self.ai, user, message, currency)
            if text is not None:
                await self._after_debt_turn(user)
                return text
        if any(k in low for k in ("progress", "how's my debt", "hows my debt", "debt plan", "status")):
            return await self.debt.format_progress(user.id, currency)
        text = await self.debt.entry_point(self.ai, user, message, currency)
        await self._after_debt_turn(user)
        return text

    async def _after_debt_turn(self, user: User) -> None:
        """Keep debt reminder jobs scheduled while an active plan exists.

        Idempotent (replace_existing jobs) — called after any debt turn so
        jobs survive bot restarts without a persistent job store.
        """
        try:
            plan = await db.get_active_debt_plan(user.id)
            if plan is None:
                return
            from core.scheduler import schedule_debt_reminders
            await schedule_debt_reminders(
                user_id=user.id,
                telegram_id=user.telegram_id,
                timezone=user.timezone or "Asia/Manila",
            )
        except Exception as exc:
            logger.warning("Failed to schedule debt reminders: {}", exc)
```

f) In `_persona_response`, after the `goals_summary = …` assignment, add:

```python
        debts_summary = await self.debt.debts_summary(
            user.id, user.currency or "PHP"
        )
```

and pass it through in the `build_hevn_system_prompt(...)` call:

```python
        system_prompt = build_hevn_system_prompt(
            user_context=user_context,
            budget_summary=budget_summary,
            goals_summary=goals_summary,
            current_gap=current_gap,
            debts_summary=debts_summary,
        )
```

(Note: `schedule_debt_reminders` doesn't exist until Task 10 — the import is inside the function and wrapped in try/except, so nothing breaks before then; the warning log is expected until Task 10 lands.)

- [ ] **Step 4: Run the full suite**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/ -q`
Expected: all PASS (the R-3 classifier/fallback tests exercise `handle()`; they must stay green)

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/experts/hevn/expert.py kaia/tests/test_debt_coach.py && git commit -m "feat(hevn): wire DebtCoach into expert routing + audit interception (D-1)"
```

---

### Task 10: Proactive nudges + scheduler jobs

**Files:**
- Modify: `kaia/experts/hevn/skills/proactive.py`
- Modify: `kaia/core/scheduler.py`
- Test: `kaia/tests/test_debt_coach.py`

- [ ] **Step 1: Write the failing tests**

Append to `kaia/tests/test_debt_coach.py`:

```python
from experts.hevn.skills.proactive import ProactiveAlertsSkill


@pytest.mark.asyncio
async def test_debt_nudge_fires_three_days_before_due(monkeypatch):
    skill = ProactiveAlertsSkill()
    target_day = (date.today() + __import__("datetime").timedelta(days=3)).day
    monkeypatch.setattr(
        "experts.hevn.skills.proactive.db.get_debts",
        AsyncMock(return_value=[
            _debt(due_day=target_day, minimum_payment=Decimal("2250"))
        ]),
    )
    text = await skill.generate_debt_nudges("u1", currency="PHP")
    assert text is not None
    assert "BPI Credit Card" in text
    assert "2,250" in text


@pytest.mark.asyncio
async def test_debt_nudge_quiet_when_nothing_due(monkeypatch):
    skill = ProactiveAlertsSkill()
    far_day = (date.today() + __import__("datetime").timedelta(days=10)).day
    monkeypatch.setattr(
        "experts.hevn.skills.proactive.db.get_debts",
        AsyncMock(return_value=[_debt(due_day=far_day)]),
    )
    assert await skill.generate_debt_nudges("u1", currency="PHP") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/test_debt_coach.py -v`
Expected: new 2 FAIL with `AttributeError: ... 'generate_debt_nudges'`

- [ ] **Step 3: Implement the proactive renderers**

In `kaia/experts/hevn/skills/proactive.py`:

a) Add to the imports: `from experts.hevn.skills.debt_coach import DebtCoachSkill`

b) In `__init__`, add: `self._debt = DebtCoachSkill()`

c) Add two methods to `ProactiveAlertsSkill`:

```python
    async def generate_debt_nudges(
        self, user_id: str, days_ahead: int = 3, currency: str = "PHP"
    ) -> str | None:
        """Due-date nudge for debts whose due_day is exactly days_ahead away.

        Returns None when nothing is due (caller sends no message).
        """
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        target = date.today() + timedelta(days=days_ahead)
        debts = await db.get_debts(user_id, status="active")
        due = [d for d in debts if d.due_day == target.day]
        if not due:
            return None
        lines = ["⏰ *Debt payment heads-up*", ""]
        for d in due:
            amount = (
                f"{symbol}{float(d.minimum_payment):,.0f} minimum"
                if d.minimum_payment
                else "your payment"
            )
            lines.append(
                f"• *{d.name}* — {amount} due {target.strftime('%b %d')} "
                f"(day {d.due_day})"
            )
        lines.append("")
        lines.append("Pay on time = zero late fees + your plan stays on track. 💪")
        return "\n".join(lines)

    async def generate_debt_monthly_review(
        self, user_id: str, currency: str = "PHP"
    ) -> str | None:
        """Monthly progress review. None when there is no active plan."""
        plan = await db.get_active_debt_plan(user_id)
        if plan is None:
            return None
        progress = await self._debt.format_progress(user_id, currency)
        return f"🗓️ *Monthly debt check-in*\n\n{progress}"
```

(`date`, `timedelta`, `db`, and `CURRENCY_SYMBOLS` are already imported in proactive.py.)

d) In `kaia/core/scheduler.py`, after the Hevn weekly digest section, add:

```python
# ── Hevn Debt Coach reminders (Phase D-1) ──────────────────────────

async def schedule_debt_reminders(
    user_id: str,
    telegram_id: int,
    timezone: str = "Asia/Manila",
    bot: Bot | None = None,
) -> None:
    """Daily 9 AM due-date nudge check + monthly progress review.

    Idempotent: replace_existing=True, so calling after every debt turn
    keeps jobs alive across restarts without a persistent job store.
    """
    scheduler = get_scheduler()
    the_bot = bot or _bot_ref
    if the_bot is None:
        logger.warning("Cannot schedule debt reminders — no bot reference")
        return

    scheduler.add_job(
        _fire_debt_nudge,
        trigger=CronTrigger(hour=9, minute=0, timezone=ZoneInfo(timezone)),
        id=f"debt_nudge_{user_id}",
        args=[user_id, telegram_id, the_bot],
        replace_existing=True,
    )
    scheduler.add_job(
        _fire_debt_review,
        trigger=CronTrigger(day=1, hour=9, minute=30, timezone=ZoneInfo(timezone)),
        id=f"debt_review_{user_id}",
        args=[user_id, telegram_id, the_bot],
        replace_existing=True,
    )
    logger.info("Debt reminders scheduled for user {} ({})", user_id, timezone)


async def cancel_debt_reminders(user_id: str) -> None:
    """Remove a user's debt nudge + review jobs."""
    scheduler = get_scheduler()
    for job_id in (f"debt_nudge_{user_id}", f"debt_review_{user_id}"):
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    logger.info("Debt reminders cancelled for user {}", user_id)


async def _fire_debt_nudge(user_id: str, telegram_id: int, bot: Bot) -> None:
    """Daily check: send a nudge only when a due date is 3 days out."""
    try:
        from experts.hevn.skills.proactive import ProactiveAlertsSkill
        from core.forum_manager import ForumManager

        user = await get_or_create_user(telegram_id)
        skill = ProactiveAlertsSkill()
        text = await skill.generate_debt_nudges(user.id, currency=user.currency or "PHP")
        if text is None:
            return

        forum_mgr = ForumManager()
        topic_id = await forum_mgr.get_topic_for_channel(telegram_id, "hevn")
        kwargs: dict = {"parse_mode": "Markdown"}
        if topic_id is not None:
            kwargs["message_thread_id"] = topic_id
        await bot.send_message(chat_id=telegram_id, text=text, **kwargs)
    except Exception as exc:
        logger.error("Failed to send debt nudge to {}: {}", telegram_id, exc)


async def _fire_debt_review(user_id: str, telegram_id: int, bot: Bot) -> None:
    """Monthly debt progress review (1st of the month, 9:30 AM)."""
    try:
        from experts.hevn.skills.proactive import ProactiveAlertsSkill
        from core.forum_manager import ForumManager

        user = await get_or_create_user(telegram_id)
        skill = ProactiveAlertsSkill()
        text = await skill.generate_debt_monthly_review(
            user.id, currency=user.currency or "PHP"
        )
        if text is None:
            return

        forum_mgr = ForumManager()
        topic_id = await forum_mgr.get_topic_for_channel(telegram_id, "hevn")
        kwargs: dict = {"parse_mode": "Markdown"}
        if topic_id is not None:
            kwargs["message_thread_id"] = topic_id
        await bot.send_message(chat_id=telegram_id, text=text, **kwargs)
    except Exception as exc:
        logger.error("Failed to send debt review to {}: {}", telegram_id, exc)
```

(Match the exact import names already at the top of scheduler.py — `Bot`, `CronTrigger`, `ZoneInfo`, `get_or_create_user`, `_bot_ref`, `get_scheduler` are all already in use by the Hevn digest section. If `timedelta` is missing from proactive.py's imports, it is already there — it is used by `generate_weekly_digest`.)

- [ ] **Step 4: Run the full suite**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/ -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add kaia/experts/hevn/skills/proactive.py kaia/core/scheduler.py kaia/tests/test_debt_coach.py && git commit -m "feat(hevn): debt due-date nudges + monthly review jobs (D-1)"
```

---

### Task 11: Documentation updates (MANDATORY per project rule)

**Files:**
- Modify: `Docs/DATABASE.md`
- Modify: `Docs/SKILLS.md`
- Modify: `Docs/ARCHITECTURE.md`
- Modify: `Docs/DEVELOPMENT_STATUS.md`
- Modify: `Docs/CHANGELOG.md`

**Note:** `Docs/` (capital D, repo root) is the live doc tree. `kaia/docs/` is stale — do not touch it.

- [ ] **Step 1: DATABASE.md — append after the "Agentic OS Bus Tables (Migration 006)" section**

```markdown
---

## Hevn Debt Coach Tables (Migration 007)

Added in D-1. Accessed via supabase-py in `database/queries.py` (asyncpg remains bus-only).

### `debts`

One row per debt the user owes. Captured by the guided debt audit or chat mentions.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID | FK → users (ON DELETE CASCADE) |
| `name` | VARCHAR(100) | e.g., `"BPI Credit Card"` |
| `debt_type` | VARCHAR(30) | `credit_card`, `salary_loan`, `personal_loan`, `five_six`, `pagibig_loan`, `sss_loan`, `auto_loan`, `mortgage`, `other` |
| `balance` | DECIMAL(14,2) | Current outstanding |
| `interest_rate` | DECIMAL(8,4) | As quoted, percent |
| `rate_period` | VARCHAR(10) | `monthly` / `yearly` — PH cards quote monthly |
| `rate_is_estimate` | BOOLEAN | TRUE when a type-default rate was used |
| `minimum_payment` | DECIMAL(12,2) | Nullable; simulator falls back to max(3% of balance, ₱500) |
| `due_day` | INT | 1–31, nullable |
| `original_amount` | DECIMAL(14,2) | Nullable |
| `status` | VARCHAR(20) | `active` / `paid_off` / `archived` |
| `notes` | TEXT | — |
| `created_at` / `updated_at` | TIMESTAMPTZ | — |

Indexed on `(user_id, status)`.

### `debt_payments`

Payment history — what makes "ahead/behind plan" computable.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `debt_id` | UUID | FK → debts (ON DELETE CASCADE) |
| `user_id` | UUID | FK → users (ON DELETE CASCADE) |
| `amount` | DECIMAL(12,2) | — |
| `paid_on` | DATE | Default CURRENT_DATE |
| `balance_after` | DECIMAL(14,2) | Balance snapshot after the payment |
| `created_at` | TIMESTAMPTZ | — |

Indexed on `(debt_id, paid_on DESC)`.

### `debt_plans`

One active payoff plan per user. The month-by-month schedule is never stored — it is recomputed deterministically from current debts + plan params; progress compares today's recompute against the baseline snapshot.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID | FK → users (ON DELETE CASCADE) |
| `strategy` | VARCHAR(20) | `avalanche` / `snowball` |
| `monthly_budget` | DECIMAL(12,2) | Total ₱/month committed to debt |
| `baseline_payoff_date` | DATE | Projected at plan creation |
| `baseline_total_interest` | DECIMAL(14,2) | Projected at plan creation |
| `status` | VARCHAR(20) | `active` / `completed` / `abandoned` |
| `created_at` | TIMESTAMPTZ | — |

Indexed on `(user_id, status)`. All three tables: RLS enabled, standard `service_role_all` policy.
```

- [ ] **Step 2: SKILLS.md — add a DebtCoach entry under Hevn's skills section**

Open `Docs/SKILLS.md`, find Hevn's skill list, and add (matching the surrounding format):

```markdown
### DebtCoach (`experts/hevn/skills/debt_coach.py`) — Phase D-1

Professional debt payoff coaching backed by deterministic math (`debt_math.py` — the LLM never does arithmetic):

- **Guided debt audit** — "help me get out of debt" triggers a one-debt-at-a-time intake (lender → balance → rate → minimum → due day). Unknown rates get labeled PH type-defaults (`rate_is_estimate`). Each completed debt is saved immediately; the audit is resumable and cancellable.
- **Payoff plan** — computes BOTH avalanche and snowball via `debt_math.compare_strategies`, presents the peso comparison, recommends one (`recommend_strategy`), user picks; plan + baseline snapshot persisted.
- **Payments** — "paid 5k on my BPI card" logs to `debt_payments`, decrements the balance, celebrates payoffs.
- **Progress** — recomputes the plan from live balances vs the baseline: ahead/behind in months, updated debt-free date.
- **Proactive** — due-date nudges 3 days ahead (daily 9:00 check) + monthly review (1st, 9:30) via `core/scheduler.py`.
- **Edge handling** — budget below minimums → shortfall advice (restructure, balance transfer, consolidation), no plan built; payment ≤ monthly interest → non-amortizing warning naming the debt.
```

- [ ] **Step 3: ARCHITECTURE.md — update Hevn's skill count and module map**

Find Hevn's section in `Docs/ARCHITECTURE.md` (it lists 7 skills) and update the count to 8, adding `debt_coach.py` and `debt_math.py` to the module list with one-line descriptions:

```markdown
- `experts/hevn/skills/debt_coach.py` — guided debt audit, payoff plan, payments, progress (D-1)
- `experts/hevn/skills/debt_math.py` — pure-Python amortization engine; no LLM, no I/O (D-1)
```

- [ ] **Step 4: DEVELOPMENT_STATUS.md and CHANGELOG.md**

Add to `Docs/DEVELOPMENT_STATUS.md` (matching its phase-entry format):

```markdown
### Phase D-1 — Hevn Debt Coach (2026-06-12) ✅

Structured debt tracking (migration 007: debts, debt_payments, debt_plans),
deterministic avalanche/snowball payoff engine, guided debt audit
conversation, payment logging, due-date nudges + monthly progress review.
Spec: `Docs/superpowers/specs/2026-06-12-hevn-debt-coach-design.md`.
**Deploy note: run `007_hevn_debt.sql` in the Supabase SQL editor.**
```

Add to `Docs/CHANGELOG.md` under a new dated heading (matching its format):

```markdown
## 2026-06-12 — D-1: Hevn Debt Coach

- NEW: guided debt audit ("help me get out of debt") capturing debts one at a time
- NEW: avalanche vs snowball payoff plans with real amortization math (LLM-free)
- NEW: payment logging via chat ("paid 5k on my BPI card") with payoff celebrations
- NEW: due-date nudges (3 days ahead) and monthly progress reviews
- NEW: tables `debts`, `debt_payments`, `debt_plans` (migration 007)
- CHANGED: Hevn's system prompt now includes a debts summary + PH debt-counseling expertise
```

- [ ] **Step 5: Commit**

```bash
cd /home/ejay/Kaia && git add Docs/ && git commit -m "docs: Hevn Debt Coach (D-1) — DATABASE, SKILLS, ARCHITECTURE, STATUS, CHANGELOG"
```

---

### Task 12: Final verification

- [ ] **Step 1: Full test suite**

Run: `cd /home/ejay/Kaia/kaia && python3 -m pytest tests/ -v 2>&1 | tail -30`
Expected: ALL tests pass — the pre-existing suite (bus, concierge, classifier, parsers, R-3 e2e) plus ~26 new debt tests. Zero failures, zero errors.

- [ ] **Step 2: Import smoke test**

Run: `cd /home/ejay/Kaia/kaia && python3 -c "from experts.hevn import HevnExpert; from experts.hevn.skills.debt_coach import DebtCoachSkill; from experts.hevn.skills import debt_math; from core import scheduler; print('all imports ok')"`
Expected: `all imports ok`

- [ ] **Step 3: Verify nothing references the stale doc tree**

Run: `cd /home/ejay/Kaia && git status --short`
Expected: clean tree (everything committed)

- [ ] **Step 4: Report deploy prerequisite**

Remind the user in the final report: **`007_hevn_debt.sql` must be run in the Supabase SQL editor before deploying** — the bot will error on debt features until the tables exist.

---

## Self-Review (completed at plan-writing time)

- **Spec coverage:** D1 (debt engine first) → Tasks 1–3; D2 (audit + chat capture) → Tasks 5, 8, 9; D3 (compare + recommend, user decides) → Tasks 3, 8; D4 (nudges + monthly review) → Task 10; D5 (no LLM arithmetic) → Tasks 1–3 (pure module). Data model → Task 4. Persona/prompts → Task 6. Error handling (shortfall/non-amortizing/cancel/sanity bounds) → Tasks 2, 8. Testing section → Tasks 1–3, 5–10. Mandatory docs → Task 11.
- **Placeholder scan:** none — every step carries complete code/commands.
- **Type consistency:** `DebtInput`/`PayoffPlan`/`StrategyComparison` defined in Tasks 1–3 and consumed with identical names in Tasks 7–8; `db.*` function names in Tasks 7–10 match Task 4's definitions; `build_hevn_system_prompt(debts_summary=…)` matches Task 6's signature; `schedule_debt_reminders` defined in Task 10 matches the deferred import in Task 9 (try/except-guarded until it lands).
