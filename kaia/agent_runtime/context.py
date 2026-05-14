"""Agent runtime context — carries per-turn data between agents and the harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from database.models import Channel, User


class Visibility(str, Enum):
    """Whether a peer-to-peer agent call is shown to the user."""

    USER_VISIBLE = "user_visible"
    INTERNAL = "internal"


@dataclass(slots=True)
class AgentContext:
    """Per-turn context passed into an agent's handler.

    R-1: carries user + channel + message (parity with BaseExpert.handle args).
    R-3: gains conversation_id + visibility + peer-call routing.
    """

    user: User
    channel: Channel
    message: str
    conversation_id: UUID = field(default_factory=uuid4)
    visibility: Visibility = Visibility.USER_VISIBLE
    metadata: dict[str, Any] = field(default_factory=dict)
