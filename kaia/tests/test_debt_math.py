"""Golden tests for Hevn's deterministic debt payoff math (Phase D-1).

Every expected number in this file was hand-computed; if a test fails,
suspect the implementation, not the test.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from experts.hevn.skills import debt_math
from experts.hevn.skills.debt_math import DebtInput


def test_monthly_rate_passes_monthly_through():
    assert debt_math.monthly_rate(Decimal("3.5"), "monthly") == Decimal("0.035")


def test_monthly_rate_divides_yearly_by_twelve():
    assert debt_math.monthly_rate(Decimal("24"), "yearly") == Decimal("0.02")


def test_monthly_rate_rejects_unknown_period():
    with pytest.raises(ValueError):
        debt_math.monthly_rate(Decimal("3.5"), "annual")


def test_add_months_rolls_year():
    assert debt_math.add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_add_months_clamps_day_to_28():
    # Day 31 doesn't exist in Feb; clamp lands on the month's real last day.
    assert debt_math.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert debt_math.add_months(date(2026, 3, 31), 1) == date(2026, 4, 30)


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
    assert comp.interest_saved_by_avalanche < debt_math.TRIVIAL_SAVINGS
    strategy, _reason = debt_math.recommend_strategy(comp)
    assert strategy == "snowball"


def test_default_minimum_uses_percentage_when_above_floor():
    # 3% of 20,000 = 600 > 500
    assert debt_math.default_minimum(Decimal("20000")) == Decimal("600.00")


def test_default_minimum_uses_floor_for_small_balances():
    # 3% of 5,000 = 150 < 500
    assert debt_math.default_minimum(Decimal("5000")) == Decimal("500")
