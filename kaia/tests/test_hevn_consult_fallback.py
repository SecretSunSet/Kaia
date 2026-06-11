"""Tests for HevnExpert's graceful fallback when peer_call fails (R-3)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
    # First AI call = R-3 consult classifier (returns JSON); all subsequent
    # calls (Hevn intent classifier, persona response, synthesis) return a plain
    # answer text.  A side_effect callable lets us serve the right response for
    # each position without hard-coding exact call counts.
    _call_count = [0]

    async def _chat_side_effect(**kwargs):
        _call_count[0] += 1
        if _call_count[0] == 1:
            return MagicMock(text=classifier_text)
        return MagicMock(text="My direct answer")

    ai.chat = AsyncMock(side_effect=_chat_side_effect)
    bus = MagicMock()
    bus.peer_call = AsyncMock(side_effect=bus_side_effect)
    BaseAgent.set_bus(bus)
    return HevnExpert(ai_engine=ai), bus


def _patch_db_helpers(hevn: HevnExpert) -> None:
    """Stub out all DB-touching instance helpers so tests stay unit-level."""
    hevn.save_messages = AsyncMock()
    hevn._channel_mem.load_combined_context = AsyncMock(return_value="")
    hevn.get_conversation_history = AsyncMock(return_value=[])
    hevn._budget_summary = AsyncMock(return_value="(no transactions logged this month)")
    hevn.goals.format_goals_overview = AsyncMock(return_value="(no goals)")
    hevn._channel_mem.get_top_gap = MagicMock(return_value=None)
    # is_first_visit → False so we skip onboarding and exercise routing
    hevn._channel_mgr.is_first_visit = AsyncMock(return_value=False)


# Patch the module-level db.get_channel_profile used inside _persona_response.
_DB_PATCH = "experts.hevn.expert.db.get_channel_profile"


@pytest.mark.asyncio
async def test_consult_timeout_falls_back_with_footer():
    hevn, bus = _hevn_with_consult_path(PeerCallTimeoutError("budget exhausted"))
    user = SimpleNamespace(id="u-1", timezone="Asia/Manila", currency="PHP")
    channel = MagicMock(channel_id="hevn", system_prompt="...", emoji="💰", character_name="Hevn", role="Financial Advisor")
    _patch_db_helpers(hevn)
    with patch(_DB_PATCH, new=AsyncMock(return_value=[])):
        result = await hevn.handle(user=user, message="Is Aave USDC safe?", channel=channel)
    assert "My direct answer" in result.text
    assert "couldn't reach" in result.text.lower() or "makubex" in result.text.lower()
    bus.peer_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_consult_path_does_not_call_peer():
    """When classifier says needs_consult=False, peer_call is never invoked."""
    hevn, bus = _hevn_with_consult_path(lambda *a, **k: {}, classifier_says_consult=False)
    user = SimpleNamespace(id="u-1", timezone="Asia/Manila", currency="PHP")
    channel = MagicMock(channel_id="hevn", system_prompt="...", emoji="💰", character_name="Hevn", role="Financial Advisor")
    _patch_db_helpers(hevn)
    with patch(_DB_PATCH, new=AsyncMock(return_value=[])):
        await hevn.handle(user=user, message="How much should I save?", channel=channel)
    bus.peer_call.assert_not_called()


@pytest.mark.asyncio
async def test_no_consult_path_uses_full_r1_r2_routing(monkeypatch):
    """When classifier says needs_consult=False, handle() must invoke the full
    R-1/R-2 routing in _direct_answer (not a plain AI chat). This locks in
    the spec requirement that non-DeFi behavior is preserved verbatim."""
    hevn, bus = _hevn_with_consult_path(lambda *a, **k: {}, classifier_says_consult=False)
    user = SimpleNamespace(id="u-1", timezone="Asia/Manila", currency="PHP")
    channel = MagicMock(channel_id="hevn", system_prompt="...", emoji="💰", character_name="Hevn", role="Financial Advisor")
    _patch_db_helpers(hevn)

    # Spy on _direct_answer to confirm it is invoked (the routing entry point).
    called = []
    original = hevn._direct_answer
    async def spy(user_, message_, channel_):
        called.append((user_, message_, channel_))
        return await original(user_, message_, channel_)
    hevn._direct_answer = spy

    with patch(_DB_PATCH, new=AsyncMock(return_value=[])):
        await hevn.handle(user=user, message="Help me budget", channel=channel)
    assert len(called) == 1
    bus.peer_call.assert_not_called()
