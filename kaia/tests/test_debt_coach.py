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


def _ai_seq(payloads: list[dict]) -> MagicMock:
    """AI mock returning each JSON payload in sequence."""
    ai = MagicMock()
    ai.chat = AsyncMock(
        side_effect=[MagicMock(text=json.dumps(p)) for p in payloads]
    )
    return ai


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


@pytest.mark.asyncio
async def test_audit_more_unsure_does_not_skip_to_budget(monkeypatch):
    # "not sure" at the "any other debts?" prompt must NOT be read as "no".
    skill = DebtCoachSkill()
    user = _user()
    monkeypatch.setattr(
        "experts.hevn.skills.debt_coach.db.create_debt",
        AsyncMock(return_value=_debt(id="new-1")),
    )
    ai = _ai_seq([{
        "name": "BPI Credit Card", "debt_type": "credit_card",
        "balance": 45000, "interest_rate": 3.5, "rate_period": "monthly",
        "minimum_payment": 2250, "due_day": 15,
    }])
    skill.start_audit(user.id)
    await skill.continue_audit(ai, user, "BPI card 45k 3.5% monthly min 2250 due 15", "PHP")
    # Now in 'more' stage. "not sure" must not be treated as "no".
    reply = await skill.continue_audit(_ai_seq([{
        "name": None, "debt_type": None, "balance": None, "interest_rate": None,
        "rate_period": None, "minimum_payment": None, "due_day": None,
    }]), user, "not sure", "PHP")
    # Should NOT have advanced to the budget question.
    assert "per month" not in reply.lower() and "toward debt each month" not in reply.lower()
    assert skill._sessions[user.id].stage != "budget"
