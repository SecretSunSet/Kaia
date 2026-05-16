"""Contract tests for concierge.onboarding.welcome_text."""

from __future__ import annotations

from concierge import welcome_text


def test_welcome_text_is_nonempty_str():
    text = welcome_text()
    assert isinstance(text, str)
    assert len(text) > 0


def test_welcome_text_mentions_kaia_and_team_commands():
    text = welcome_text()
    # Single source of truth for the /start greeting — these anchors must
    # stay so the message keeps onboarding the user to the expert team.
    assert "KAIA" in text
    assert "/hevn" in text
    assert "/makubex" in text
    assert "/team" in text


def test_welcome_text_is_stable_across_calls():
    assert welcome_text() == welcome_text()
