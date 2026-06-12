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
