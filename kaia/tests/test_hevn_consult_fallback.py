"""Tests for HevnExpert's graceful fallback when peer_call fails (R-3)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_runtime.base_agent import BaseAgent, PeerCallTimeoutError
from experts.hevn import HevnExpert


@pytest.fixture(autouse=True)
def _reset_bus():
    BaseAgent.set_bus(None)
    yield
    BaseAgent.set_bus(None)


def _hevn_with_consult_path(bus_side_effect, classifier_says_consult=True):
    """Build a HevnExpert whose classifier says 'consult' (or not) and whose
    bus.peer_call is wired to raise (or succeed)."""
    ai = MagicMock()
    classifier_text = json.dumps({
        "needs_consult": classifier_says_consult,
        "target": "makubex",
        "intent": "smart_contract_risk",
        "payload": {"protocol": "Aave", "asset": "USDC", "context": "x"},
    })
    # First chat call = classifier; subsequent chat calls = direct/synthesis answer.
    ai.chat = AsyncMock(side_effect=[
        MagicMock(text=classifier_text),
        MagicMock(text="My direct answer"),
    ])
    bus = MagicMock()
    bus.peer_call = AsyncMock(side_effect=bus_side_effect)
    BaseAgent.set_bus(bus)
    return HevnExpert(ai_engine=ai), bus


@pytest.mark.asyncio
async def test_consult_timeout_falls_back_with_footer():
    hevn, bus = _hevn_with_consult_path(PeerCallTimeoutError("budget exhausted"))
    user = SimpleNamespace(id="u-1", timezone="Asia/Manila")
    channel = MagicMock(channel_id="hevn", system_prompt="...", emoji="💰", character_name="Hevn", role="Financial Advisor")
    # Patch any DB-touching helpers so we don't hit Supabase.
    hevn.save_messages = AsyncMock()
    hevn._channel_mem.load_combined_context = AsyncMock(return_value="")
    result = await hevn.handle(user=user, message="Is Aave USDC safe?", channel=channel)
    assert "My direct answer" in result.text
    assert "couldn't reach" in result.text.lower() or "makubex" in result.text.lower()
    bus.peer_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_consult_path_does_not_call_peer():
    """When classifier says needs_consult=False, peer_call is never invoked."""
    hevn, bus = _hevn_with_consult_path(lambda *a, **k: {}, classifier_says_consult=False)
    user = SimpleNamespace(id="u-1", timezone="Asia/Manila")
    channel = MagicMock(channel_id="hevn", system_prompt="...", emoji="💰", character_name="Hevn", role="Financial Advisor")
    hevn.save_messages = AsyncMock()
    hevn._channel_mem.load_combined_context = AsyncMock(return_value="")
    await hevn.handle(user=user, message="How much should I save?", channel=channel)
    bus.peer_call.assert_not_called()
