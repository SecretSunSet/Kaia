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
