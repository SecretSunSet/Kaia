"""Orchestration tests for concierge.Concierge.handle_general_turn."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from concierge import Concierge, ConciergeResult
from config.constants import ROLE_ASSISTANT, ROLE_USER, SKILL_CHAT
from skills.base import SkillResult


def _user():
    return SimpleNamespace(id="u-1", timezone="Asia/Manila")


def _convo(role: str, content: str):
    # Mimics a database conversation row (has .role, .content, .created_at).
    return SimpleNamespace(role=role, content=content, created_at=None)


def _make_concierge(skill_result: SkillResult):
    router = MagicMock()
    router.route = AsyncMock(return_value=skill_result)
    memory = MagicMock()
    memory.load_profile_context = AsyncMock(return_value="PROFILE")
    memory.run_background_extraction = MagicMock()
    c = Concierge(ai_engine=MagicMock(), skill_router=router, memory_mgr=memory)
    return c, router, memory


@pytest.mark.asyncio
async def test_general_turn_routes_and_returns_result():
    sr = SkillResult(text="hello back", skill_name=SKILL_CHAT)
    c, router, memory = _make_concierge(sr)

    with patch("concierge.concierge.get_recent_conversations",
               AsyncMock(return_value=[_convo(ROLE_USER, "earlier")])), \
         patch("concierge.concierge.save_conversation", AsyncMock()) as save, \
         patch("concierge.concierge.detect_expert_topic", return_value=None):
        result = await c.handle_general_turn(_user(), "hi", suggest_experts=True)

    assert isinstance(result, ConciergeResult)
    assert result.text == "hello back"
    assert result.skill_name == SKILL_CHAT
    assert result.profile_context == "PROFILE"
    router.route.assert_awaited_once()
    # Invariant #1: user then assistant, tagged with skill name.
    assert save.await_args_list[0].args[1] == ROLE_USER
    assert save.await_args_list[1].args[1] == ROLE_ASSISTANT
    assert save.await_args_list[0].kwargs["skill_used"] == SKILL_CHAT
    # Invariant #9: extraction fired (fire-and-forget).
    memory.run_background_extraction.assert_called_once()


@pytest.mark.asyncio
async def test_suggestion_only_when_chat_and_suggest_enabled():
    sr = SkillResult(text="r", skill_name=SKILL_CHAT)
    c, *_ = _make_concierge(sr)
    with patch("concierge.concierge.get_recent_conversations", AsyncMock(return_value=[])), \
         patch("concierge.concierge.save_conversation", AsyncMock()), \
         patch("concierge.concierge.detect_expert_topic",
               return_value={"channel_id": "hevn", "suggestion": "try /hevn"}) as det:
        result = await c.handle_general_turn(_user(), "budget help", suggest_experts=True)
    assert result.suggestion == "try /hevn"
    det.assert_called_once()


@pytest.mark.asyncio
async def test_voice_path_never_calls_detector():
    """Invariant #2: suggest_experts=False must not touch the stateful detector."""
    sr = SkillResult(text="r", skill_name=SKILL_CHAT)
    c, *_ = _make_concierge(sr)
    with patch("concierge.concierge.get_recent_conversations", AsyncMock(return_value=[])), \
         patch("concierge.concierge.save_conversation", AsyncMock()), \
         patch("concierge.concierge.detect_expert_topic") as det:
        result = await c.handle_general_turn(_user(), "budget help", suggest_experts=False)
    assert result.suggestion is None
    det.assert_not_called()


@pytest.mark.asyncio
async def test_no_suggestion_for_non_chat_skill():
    sr = SkillResult(text="reminder set", skill_name="reminders")
    c, *_ = _make_concierge(sr)
    with patch("concierge.concierge.get_recent_conversations", AsyncMock(return_value=[])), \
         patch("concierge.concierge.save_conversation", AsyncMock()), \
         patch("concierge.concierge.detect_expert_topic") as det:
        result = await c.handle_general_turn(_user(), "remind me", suggest_experts=True)
    assert result.suggestion is None
    det.assert_not_called()
