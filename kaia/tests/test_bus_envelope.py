"""Contract tests for bus.Envelope and Visibility."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from bus import Envelope, Visibility


def _sample(**overrides) -> Envelope:
    defaults = dict(
        envelope_id=uuid4(),
        conversation_id=uuid4(),
        from_agent="hevn",
        to_agent="makubex",
        user_id=uuid4(),
        intent="smart_contract_risk",
        visibility=Visibility.USER_VISIBLE,
        kind="request",
        payload={"protocol": "Aave", "asset": "USDC"},
        reply_to=None,
        created_at=datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Envelope(**defaults)


def test_visibility_enum_members():
    assert Visibility.USER_VISIBLE.value == "user_visible"
    assert Visibility.INTERNAL.value == "internal"


def test_envelope_round_trip_to_from_dict():
    env = _sample()
    d = env.to_dict()
    # All UUIDs serialized as strings, datetime as isoformat, enums as values.
    assert d["envelope_id"] == str(env.envelope_id)
    assert d["visibility"] == "user_visible"
    assert d["kind"] == "request"
    assert d["payload"] == {"protocol": "Aave", "asset": "USDC"}
    assert d["reply_to"] is None
    # Round-trip back to Envelope must be equal.
    restored = Envelope.from_dict(d)
    assert restored == env


def test_envelope_reply_to_round_trip():
    request_id = uuid4()
    env = _sample(kind="reply", reply_to=request_id)
    d = env.to_dict()
    assert d["reply_to"] == str(request_id)
    restored = Envelope.from_dict(d)
    assert restored.reply_to == request_id


def test_envelope_rejects_unknown_kind():
    with pytest.raises(ValueError, match="Envelope.kind must be one of"):
        _sample(kind="invalid")


def test_envelope_rejects_missing_required_field():
    """from_dict must raise on missing required keys."""
    d = _sample().to_dict()
    del d["from_agent"]
    with pytest.raises(KeyError, match="from_dict missing required key"):
        Envelope.from_dict(d)


def test_envelope_round_trip_internal_visibility_and_error_kind():
    """Cover the Visibility.INTERNAL value and kind='error' branch in to_dict/from_dict."""
    env = _sample(
        visibility=Visibility.INTERNAL,
        kind="error",
        payload={"error": "no handler for intent 'foo'"},
        reply_to=uuid4(),
    )
    d = env.to_dict()
    assert d["visibility"] == "internal"
    assert d["kind"] == "error"
    restored = Envelope.from_dict(d)
    assert restored == env
    assert restored.visibility is Visibility.INTERNAL


def test_envelope_from_dict_rejects_invalid_visibility():
    """from_dict must reject an unknown visibility string (enum-guarded)."""
    d = _sample().to_dict()
    d["visibility"] = "bogus"
    with pytest.raises(ValueError):
        Envelope.from_dict(d)
