"""AI-powered message classification — determines which skill should handle a message."""

from __future__ import annotations

import json
from dataclasses import dataclass

from loguru import logger

from config.constants import ALL_SKILLS, SKILL_CHAT
from config.settings import get_settings
from core.ai_engine import AIEngine


SKILLS_STR = ", ".join(ALL_SKILLS)

CLASSIFICATION_PROMPT = f"""\
You are an intent classifier for a personal AI assistant called KAIA.

Given a user message, classify it into exactly ONE skill:

SKILLS:
- chat — General questions, advice, casual conversation, anything that doesn't fit other categories
- memory — User asks what you know about them, or tells you to remember/forget something
- reminders — Creating, listing, editing, or deleting reminders and alarms
- budget — Logging income/expenses, asking about spending, budget summaries, financial tracking
- briefing — Requesting a daily briefing or morning update, changing briefing time, turning briefing on/off
- web_browse — Searching the web, looking up current info, news, weather, prices, real-time data

RULES:
- If the message could fit multiple skills, pick the MOST specific one.
- If unsure, default to "chat".
- "Remember that..." or "What do you know about me?" → memory
- Any mention of money amounts with context (spent, paid, received, earned, lunch, groceries, salary) → budget
- Plain numbers alone ("500") are NOT budget — need financial context ("spent 500", "lunch 500")
- "Set budget", "budget limit", "how much did I spend", "budget summary" → budget
- "Undo last transaction", "delete last entry" → budget
- "Remind me...", "Set alarm..." → reminders
- "Search for...", "Look up...", "What's the latest...", "Google..." → web_browse
- Weather queries ("What's the weather?", "Is it raining?") → web_browse
- "What's the news?", "Latest news on...", "Headlines" → web_browse
- "Give me my briefing", "Morning update", "Change briefing time" → briefing
- "Turn off briefing", "Disable briefing" → briefing

Respond with ONLY a JSON object (no other text):
{{"skill": "<skill_id>", "confidence": <0.0-1.0>}}
"""


@dataclass
class IntentResult:
    """Result of intent classification."""

    skill: str
    confidence: float


class IntentDetector:
    """Classifies user messages into skill categories using AI."""

    def __init__(self, ai_engine: AIEngine) -> None:
        self._ai = ai_engine
        self._settings = get_settings()

    async def detect(self, message: str) -> IntentResult:
        """Classify a message and return the target skill + confidence."""
        try:
            response = await self._ai.chat(
                system_prompt=CLASSIFICATION_PROMPT,
                messages=[{"role": "user", "content": message}],
                max_tokens=64,
            )
            result = _parse_intent(response.text)
            logger.debug(
                "Intent: '{}' → skill={} conf={:.2f}",
                message[:50],
                result.skill,
                result.confidence,
            )

            # Fall back to chat if confidence is too low
            if result.confidence < self._settings.intent_confidence_threshold:
                logger.debug(
                    "Confidence {:.2f} < threshold {:.2f}, defaulting to chat",
                    result.confidence,
                    self._settings.intent_confidence_threshold,
                )
                return IntentResult(skill=SKILL_CHAT, confidence=result.confidence)

            return result

        except Exception as exc:
            logger.warning("Intent detection failed ({}), defaulting to chat", exc)
            return IntentResult(skill=SKILL_CHAT, confidence=0.0)


def _parse_intent(text: str) -> IntentResult:
    """Parse the AI's JSON response into an IntentResult."""
    text = text.strip()

    # Try direct parse
    try:
        data = json.loads(text)
        skill = data.get("skill", SKILL_CHAT)
        confidence = float(data.get("confidence", 0.5))
        if skill not in ALL_SKILLS:
            skill = SKILL_CHAT
        return IntentResult(skill=skill, confidence=confidence)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to find JSON within text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            skill = data.get("skill", SKILL_CHAT)
            confidence = float(data.get("confidence", 0.5))
            if skill not in ALL_SKILLS:
                skill = SKILL_CHAT
            return IntentResult(skill=skill, confidence=confidence)
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning("Could not parse intent response: {}", text[:100])
    return IntentResult(skill=SKILL_CHAT, confidence=0.0)
