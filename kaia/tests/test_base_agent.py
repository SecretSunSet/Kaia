"""Contract tests for agent_runtime.BaseAgent."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from agent_runtime import BaseAgent, AgentContext, PeerCallError, Visibility
from skills.base import SkillResult


class _StubAgent(BaseAgent):
    """Minimal concrete subclass for testing."""

    channel_id = "stub"

    async def handle(self, user, message, channel) -> SkillResult:  # noqa: D401
        return SkillResult(text=f"echo:{message}", skill_name=self.channel_id)


def _agent() -> _StubAgent:
    return _StubAgent(ai_engine=MagicMock())


def test_agent_id_aliases_channel_id():
    assert _agent().agent_id == "stub"


def test_baseexpert_alias_resolves_to_base_agent():
    """experts.base.BaseExpert must be the same class as BaseAgent."""
    from experts.base import BaseExpert  # alias

    assert BaseExpert is BaseAgent


@pytest.mark.asyncio
async def test_handle_turn_delegates_to_handle():
    agent = _agent()
    user = MagicMock()
    channel = MagicMock()
    ctx = AgentContext(user=user, channel=channel, message="hi")

    result = await agent.handle_turn(ctx)

    assert result.text == "echo:hi"
    assert result.skill_name == "stub"


@pytest.mark.asyncio
async def test_peer_call_raises_until_r3_lands():
    agent = _agent()
    with pytest.raises(PeerCallError) as exc:
        await agent.peer_call("makubex", "consult", {"q": "x"})

    msg = str(exc.value)
    assert "R-3" in msg
    assert "makubex" in msg


def test_visibility_default_is_user_visible():
    """Per design decision: peer calls default to user-visible."""
    user = MagicMock()
    channel = MagicMock()
    ctx = AgentContext(user=user, channel=channel, message="hi")
    assert ctx.visibility is Visibility.USER_VISIBLE
