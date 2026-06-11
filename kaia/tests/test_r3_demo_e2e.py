"""End-to-end R-3 demo: real Hevn + real MakubeX + InMemoryBusTransport.
Mocks AI responses to simulate the DeFi scenario deterministically.
Asserts the 3-message attribution shape (consult / reply / synthesis)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agent_runtime.base_agent import BaseAgent
from bus import Bus, Envelope, InMemoryBusTransport, Visibility
from experts.hevn import HevnExpert
from experts.makubex import MakubeXExpert


@pytest.fixture(autouse=True)
def _reset_bus():
    BaseAgent.set_bus(None)
    yield
    BaseAgent.set_bus(None)


@pytest.mark.asyncio
async def test_defi_consult_end_to_end_produces_three_envelopes():
    """User → Hevn → peer_call(MakubeX) → reply → Hevn synthesizes.

    Bus traffic should contain: request envelope (hevn → makubex) +
    reply envelope (makubex → hevn). Both visibility=user_visible →
    both surface on bus:user_visible.

    The "three" in the test name refers to the 3 user-visible MESSAGES
    in the Telegram thread (consult question + reply payload + Hevn's
    synthesis), not 3 envelopes — only 2 envelopes flow through the bus
    (request + reply); the synthesis is returned as a SkillResult.
    """
    tx = InMemoryBusTransport()
    bus = Bus(transport=tx, default_timeout=5.0)
    BaseAgent.set_bus(bus)

    # Mock AIs — different responses for classifier, makubex risk, synthesis.
    hevn_ai = MagicMock()
    hevn_ai.chat = AsyncMock(side_effect=[
        MagicMock(text=json.dumps({
            "needs_consult": True,
            "target": "makubex",
            "intent": "smart_contract_risk",
            "payload": {"protocol": "Aave", "asset": "USDC", "context": "10% of emergency fund"},
        })),
        MagicMock(text="Based on MakubeX's read, I'd cap exposure at 5% not 10%..."),
    ])
    makubex_ai = MagicMock()
    makubex_ai.chat = AsyncMock(return_value=MagicMock(text=json.dumps({
        "summary": "Aave V3 USDC is among the safer DeFi positions.",
        "audit_status": "Trail of Bits, OpenZeppelin",
        "tvl_signal": ">=$10B",
        "depeg_history": "USDC briefly depegged Mar-2023",
        "oracle_bridge_risk": "Chainlink oracles, no bridging on mainnet",
        "rating": "low-to-moderate",
        "caveats": ["smart-contract residual risk"],
    })))

    hevn = HevnExpert(ai_engine=hevn_ai)
    makubex = MakubeXExpert(ai_engine=makubex_ai)  # __init__ registers smart_contract_risk handler
    await bus.start()

    user_visible_seen: list[str] = []
    async def watcher():
        async for payload_id in tx.subscribe("bus:user_visible"):
            user_visible_seen.append(payload_id)
            if len(user_visible_seen) >= 2:
                return
    watch_task = asyncio.create_task(watcher())
    await asyncio.sleep(0)

    user = SimpleNamespace(id=uuid4(), timezone="Asia/Manila")
    channel = MagicMock(
        channel_id="hevn", system_prompt="...", emoji="💰",
        character_name="Hevn", role="Financial Advisor",
    )
    hevn.save_messages = AsyncMock()
    hevn._channel_mem.load_combined_context = AsyncMock(return_value="")
    # Mock _fire_extraction to avoid spawning tasks that hit the real extractor/DB.
    hevn._fire_extraction = MagicMock()

    result = await hevn.handle(
        user=user,
        message="Is it safe to put 10% of my emergency fund in Aave USDC?",
        channel=channel,
    )

    await asyncio.wait_for(watch_task, timeout=2.0)

    assert len(user_visible_seen) == 2, f"expected 2 user_visible envelopes, got {len(user_visible_seen)}"
    assert "Based on MakubeX" in result.text or "5%" in result.text

    # Tighten: prove the synthesis prompt actually received MakubeX's
    # structured reply (and not a stale dict or empty payload). The
    # synthesis call is Hevn's SECOND ai.chat invocation; its system
    # prompt should contain the rating field from the risk profile.
    synthesis_call = hevn_ai.chat.call_args_list[1]
    synthesis_system_prompt = synthesis_call.kwargs.get("system_prompt", "")
    assert "low-to-moderate" in synthesis_system_prompt, \
        "MakubeX's rating did not reach Hevn's synthesis prompt"

    await bus.shutdown()
