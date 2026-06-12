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


@pytest.mark.asyncio
async def test_debt_keywords_use_word_boundaries():
    # "owe" must not fire inside "lower"/"power"/"lowest".
    ai = MagicMock()
    ai.chat = AsyncMock(
        return_value=MagicMock(text='{"skill": "general_chat", "confidence": 0.8}')
    )
    assert await classify_hevn_intent(ai, "what is the lowest rate available") == "education"
    assert await classify_hevn_intent(ai, "show my power bill") == "bills"


@pytest.mark.asyncio
async def test_educational_loan_questions_defer_to_education():
    ai = MagicMock()
    assert await classify_hevn_intent(ai, "explain how a salary loan works") == "education"
    assert await classify_hevn_intent(ai, "what is a home loan") == "education"
    ai.chat.assert_not_called()


@pytest.mark.asyncio
async def test_pay_off_bill_phrasing_routes_to_bills():
    ai = MagicMock()
    assert await classify_hevn_intent(ai, "how do I pay off my Netflix bill") == "bills"
    ai.chat.assert_not_called()


@pytest.mark.asyncio
async def test_action_debt_requests_beat_education_deferral():
    ai = MagicMock()
    assert await classify_hevn_intent(ai, "how do I get out of debt") == "debt"
    assert await classify_hevn_intent(ai, "how do I reduce my debt") == "debt"
    ai.chat.assert_not_called()


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
