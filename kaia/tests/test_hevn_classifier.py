"""Tests for HevnExpert's classifier behavior (R-3)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_runtime.base_agent import BaseAgent
from experts.hevn import HevnExpert


@pytest.fixture(autouse=True)
def _reset_bus():
    BaseAgent.set_bus(None)
    yield
    BaseAgent.set_bus(None)


def _hevn_with_ai(classifier_response_text: str) -> HevnExpert:
    ai = MagicMock()
    ai.chat = AsyncMock(return_value=MagicMock(text=classifier_response_text))
    return HevnExpert(ai_engine=ai)


@pytest.mark.asyncio
async def test_classifier_returns_consult_for_defi_question():
    text = json.dumps({
        "needs_consult": True,
        "target": "makubex",
        "intent": "smart_contract_risk",
        "payload": {"protocol": "Aave", "asset": "USDC", "context": "stablecoin yield"},
    })
    hevn = _hevn_with_ai(text)
    decision = await hevn._classify_consult_intent(
        "Is it safe to put 10% of my emergency fund in Aave USDC?"
    )
    assert decision["needs_consult"] is True
    assert decision["target"] == "makubex"
    assert decision["intent"] == "smart_contract_risk"
    assert decision["payload"]["protocol"] == "Aave"


@pytest.mark.asyncio
async def test_classifier_returns_no_consult_for_general_finance():
    text = json.dumps({"needs_consult": False})
    hevn = _hevn_with_ai(text)
    decision = await hevn._classify_consult_intent("Help me budget my savings.")
    assert decision["needs_consult"] is False


@pytest.mark.asyncio
async def test_classifier_falls_back_on_malformed_output():
    """Malformed classifier JSON must yield needs_consult=False (fail-safe), not raise."""
    hevn = _hevn_with_ai("not json at all")
    decision = await hevn._classify_consult_intent("Anything?")
    assert decision == {"needs_consult": False}
