"""A2A envelope and visibility enum — the wire format for the R-3 bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID


class Visibility(str, Enum):
    """Whether a peer-to-peer envelope is relayed to the user."""

    USER_VISIBLE = "user_visible"
    INTERNAL = "internal"


_VALID_KINDS = {"request", "reply", "error"}

EnvelopeKind = Literal["request", "reply", "error"]


@dataclass(slots=True)
class Envelope:
    """One inter-agent message — request, reply, or error.

    See Docs/AGENTIC_OS/DESIGN_R3.md §2 and §5 for the full schema. The
    on-wire representation (to_dict) matches the agent_messages table
    columns; reply correlation is via reply_to (the envelope_id of the
    triggering request).
    """

    envelope_id: UUID
    conversation_id: UUID
    from_agent: str
    to_agent: str
    user_id: UUID
    intent: str
    visibility: Visibility
    kind: EnvelopeKind
    payload: dict[str, Any]
    reply_to: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"Envelope.kind must be one of {_VALID_KINDS}, got {self.kind!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSONB / network payloads."""
        return {
            "envelope_id": str(self.envelope_id),
            "conversation_id": str(self.conversation_id),
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "user_id": str(self.user_id),
            "intent": self.intent,
            "visibility": self.visibility.value,
            "kind": self.kind,
            "payload": self.payload,
            "reply_to": str(self.reply_to) if self.reply_to is not None else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Envelope":
        """Deserialize from a row / JSON payload. Raises on missing required fields."""
        required = (
            "envelope_id", "conversation_id", "from_agent", "to_agent",
            "user_id", "intent", "visibility", "kind", "payload",
        )
        for key in required:
            if key not in d:
                raise KeyError(f"Envelope.from_dict missing required key: {key!r}")
        reply_to_raw = d.get("reply_to")
        created_raw = d.get("created_at")
        created = (
            datetime.fromisoformat(created_raw)
            if isinstance(created_raw, str)
            else (created_raw or datetime.now(timezone.utc))
        )
        return cls(
            envelope_id=UUID(d["envelope_id"]) if isinstance(d["envelope_id"], str) else d["envelope_id"],
            conversation_id=UUID(d["conversation_id"]) if isinstance(d["conversation_id"], str) else d["conversation_id"],
            from_agent=d["from_agent"],
            to_agent=d["to_agent"],
            user_id=UUID(d["user_id"]) if isinstance(d["user_id"], str) else d["user_id"],
            intent=d["intent"],
            visibility=Visibility(d["visibility"]),
            kind=d["kind"],
            payload=d["payload"],
            reply_to=(UUID(reply_to_raw) if isinstance(reply_to_raw, str) else reply_to_raw),
            created_at=created,
        )
