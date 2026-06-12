"""Deterministic debt payoff math — no LLM, no I/O (Phase D-1).

All money is Decimal. Quoted rates are percentages; monthly_rate()
normalizes them to per-month fractions (3.5%/mo -> Decimal("0.035")).
The LLM never computes these numbers — it only narrates results.
"""

from __future__ import annotations

import calendar
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
    if rate_period not in ("monthly", "yearly"):
        raise ValueError(f"Unknown rate_period: {rate_period!r}")
    pct = rate / Decimal("100")
    if rate_period == "yearly":
        return pct / Decimal("12")
    return pct


def add_months(d: date, months: int) -> date:
    """Add calendar months; day-of-month clamped to the target month's last day."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


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
    assert accounts, "_pick_target called with no accounts with positive balance"
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
        return "avalanche", (
            "A full comparison wasn't possible here — paying the "
            "highest-rate debt first is the safe default."
        )
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
