"""Tests for MakubeX's inbound smart_contract_risk peer-intent handler (R-3)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent_runtime.base_agent import BaseAgent
from bus import Envelope, Visibility
from experts.makubex import MakubeXExpert


@pytest.fixture(autouse=True)
def _reset_bus():
    BaseAgent.set_bus(None)
    yield
    BaseAgent.set_bus(None)


def _envelope(payload: dict) -> Envelope:
    return Envelope(
        envelope_id=uuid4(),
        conversation_id=uuid4(),
        from_agent="hevn",
        to_agent="makubex",
        user_id=uuid4(),
        intent="smart_contract_risk",
        visibility=Visibility.USER_VISIBLE,
        kind="request",
        payload=payload,
    )


@pytest.mark.asyncio
async def test_smart_contract_risk_returns_structured_reply():
    """Given a mocked AI that returns valid JSON, the handler returns a parsed dict."""
    fake_json = json.dumps({
        "summary": "Aave V3 USDC pool is among the lowest-risk DeFi positions.",
        "audit_status": "Trail of Bits, OpenZeppelin",
        "tvl_signal": ">=$10B on USDC pool",
        "depeg_history": "USDC briefly depegged Mar-2023 (SVB), recovered",
        "oracle_bridge_risk": "Chainlink oracles, no bridging on mainnet",
        "rating": "low-to-moderate",
        "caveats": ["smart-contract residual risk", "regulatory uncertainty"],
    })
    ai = MagicMock()
    ai.chat = AsyncMock(return_value=MagicMock(text=fake_json))
    bus = MagicMock()
    bus.register_handler = MagicMock()
    BaseAgent.set_bus(bus)
    expert = MakubeXExpert(ai_engine=ai)  # __init__ registers via _register_peer_intents

    risk_call = next(c for c in bus.register_handler.call_args_list if c.args[1] == "smart_contract_risk")
    handler = risk_call.args[2]

    reply = await handler(_envelope({"protocol": "Aave", "asset": "USDC", "context": "stablecoin yield"}))

    assert reply["rating"] == "low-to-moderate"
    assert "audit_status" in reply


@pytest.mark.asyncio
async def test_smart_contract_risk_handles_malformed_ai_output():
    """If the AI returns non-JSON, the handler returns a structured error payload —
    never crashes the bus dispatcher."""
    ai = MagicMock()
    ai.chat = AsyncMock(return_value=MagicMock(text="not valid json {{{"))
    bus = MagicMock()
    bus.register_handler = MagicMock()
    BaseAgent.set_bus(bus)
    expert = MakubeXExpert(ai_engine=ai)
    risk_call = next(c for c in bus.register_handler.call_args_list if c.args[1] == "smart_contract_risk")
    handler = risk_call.args[2]

    reply = await handler(_envelope({"protocol": "X", "asset": "Y", "context": "z"}))

    assert isinstance(reply, dict)
    assert "error" in reply or "summary" in reply
