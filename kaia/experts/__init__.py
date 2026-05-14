"""Expert registry — maps channel IDs to expert classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ai_engine import AIEngine
    from experts.base import BaseExpert

# Registry: channel_id → expert class
_EXPERT_REGISTRY: dict[str, type[BaseExpert]] = {}


def register_expert(channel_id: str, expert_cls: type[BaseExpert]) -> None:
    """Register an expert class for a channel."""
    _EXPERT_REGISTRY[channel_id] = expert_cls


def get_expert(channel_id: str, ai_engine: AIEngine) -> BaseExpert | None:
    """Get an expert instance by channel_id. Returns None if not registered."""
    cls = _EXPERT_REGISTRY.get(channel_id)
    if cls is None:
        return None
    return cls(ai_engine)


def get_agent(agent_id: str, ai_engine: AIEngine) -> BaseExpert | None:
    """Get an agent instance by agent_id. Alias for `get_expert` during the
    BaseExpert → BaseAgent migration (R-1). New call sites should prefer
    this name; existing `get_expert` callers continue to work."""
    return get_expert(agent_id, ai_engine)


def _register_defaults() -> None:
    """Register built-in experts. Called at import time."""
    from config.constants import (
        CHANNEL_HEVN,
        CHANNEL_KAZUKI,
        CHANNEL_AKABANE,
        CHANNEL_MAKUBEX,
    )
    from experts.hevn import HevnExpert
    from experts.makubex import MakubeXExpert
    from experts.placeholder import PlaceholderExpert

    register_expert(CHANNEL_HEVN, HevnExpert)
    register_expert(CHANNEL_MAKUBEX, MakubeXExpert)
    for channel_id in (CHANNEL_KAZUKI, CHANNEL_AKABANE):
        register_expert(channel_id, PlaceholderExpert)


_register_defaults()
