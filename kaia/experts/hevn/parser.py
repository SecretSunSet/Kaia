"""AI-driven parsers for Hevn — goal, bill, and intent classification."""

from __future__ import annotations

import json
from datetime import date

from loguru import logger

from core.ai_engine import AIEngine
from experts.hevn.prompts import HEVN_INTENT_PROMPT


ADVICE_MARKERS = (
    "how much should", "how much do i need", "what's a good",
    "what is a good", "should i ", "is my ", "is it better",
    "would you recommend", "do you recommend", "recommend",
    "what would you", "what do you think",
)

GOAL_CREATE_MARKERS = (
    "set a goal", "set this as", "set that as", "let's set",
    "create a goal", "create goal", "make this my goal",
    "add a goal", "new goal",
)

GOAL_VIEW_MARKERS = (
    "show my goals", "list my goals", "my goals", "show goals",
    "progress on my goals", "goal progress",
)


async def classify_hevn_intent(ai: AIEngine, message: str) -> str:
    """Classify a message into one of Hevn's skills."""
    # Short-circuit obvious patterns (no AI cost).
    low = message.lower().strip()

    # Advice-style questions ALWAYS win over goal/bill keyword matches — a
    # user asking "how much should my emergency fund be?" is not trying to
    # list goals.
    if any(m in low for m in ADVICE_MARKERS):
        return "general_chat"

    if any(p in low for p in (
        "financial health", "how am i doing", "how's my finances", "my finances",
        "score", "assessment",
    )):
        return "health_assessment"
    # Goal creation/view — narrow markers only; "goal" alone isn't enough.
    if any(m in low for m in GOAL_CREATE_MARKERS) or any(
        m in low for m in GOAL_VIEW_MARKERS
    ):
        return "goals"
    if any(p in low for p in (
        "bill", "bills", "subscription", "netflix", "spotify", "due",
    )):
        return "bills"
    if any(p in low for p in (
        "bsp", "interest rate", "psei", "market", "economy", "peso", "usd",
        "exchange rate", "news",
    )):
        return "market_trends"
    if any(p in low for p in (
        "explain", "what is", "what's", "teach me", "learn about",
        "how do", "mp2", "uitf", "stocks", "bonds", "reit",
    )):
        return "education"
    if any(p in low for p in (
        "wasting", "waste", "cut back", "spending pattern", "where am i spending",
        "budget coaching", "analyze",
    )):
        return "budget_coaching"

    # Fall back to AI classifier
    try:
        response = await ai.chat(
            system_prompt="You are a strict intent classifier. Reply only with JSON.",
            messages=[{"role": "user", "content": HEVN_INTENT_PROMPT.format(message=message)}],
            max_tokens=60,
        )
        text = response.text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            parsed = json.loads(text[start:end + 1])
            skill = parsed.get("skill", "general_chat")
            if skill in {
                "health_assessment", "budget_coaching", "goals", "bills",
                "market_trends", "education", "general_chat",
            }:
                return skill
    except Exception as exc:
        logger.debug("Hevn intent classification fallback: {}", exc)
    return "general_chat"


async def parse_goal_creation(
    ai: AIEngine, message: str
) -> dict | None:
    """Parse a 'save X for Y by Z' message into goal params."""
    system = (
        "Extract a financial goal from the user's message. Return ONLY a JSON object "
        "with these keys (null if unknown): "
        "{\"name\": string, \"target\": number (pesos), "
        "\"deadline\": \"YYYY-MM-DD\" or null, "
        "\"monthly\": number or null, "
        "\"priority\": 1|2|3}. "
        "If the message isn't about creating a goal, return {\"name\": null}."
    )
    try:
        response = await ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": message}],
            max_tokens=150,
        )
        text = response.text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return None
        parsed = json.loads(text[start:end + 1])
        if not parsed.get("name") or parsed.get("target") in (None, 0):
            return None
        deadline = None
        if parsed.get("deadline"):
            try:
                deadline = date.fromisoformat(parsed["deadline"])
            except ValueError:
                deadline = None
        return {
            "name": parsed["name"],
            "target": float(parsed["target"]),
            "deadline": deadline,
            "monthly": float(parsed["monthly"]) if parsed.get("monthly") else None,
            "priority": int(parsed.get("priority", 2)),
        }
    except Exception as exc:
        logger.debug("Goal parse failed: {}", exc)
        return None


async def parse_bill_creation(
    ai: AIEngine, message: str
) -> dict | None:
    """Parse a 'remind me my Netflix is ₱549 on the 20th' message."""
    system = (
        "Extract a recurring bill from the user's message. Return ONLY a JSON object: "
        "{\"name\": string, \"amount\": number (pesos), "
        "\"due_day\": int (1-31) or null, \"category\": string or null, "
        "\"recurrence\": \"monthly\"|\"weekly\"|\"yearly\"|\"quarterly\"}. "
        "If not a bill, return {\"name\": null}."
    )
    try:
        response = await ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": message}],
            max_tokens=120,
        )
        text = response.text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return None
        parsed = json.loads(text[start:end + 1])
        if not parsed.get("name") or not parsed.get("amount"):
            return None
        due_day = parsed.get("due_day")
        if isinstance(due_day, int) and (due_day < 1 or due_day > 31):
            due_day = None
        return {
            "name": parsed["name"],
            "amount": float(parsed["amount"]),
            "due_day": due_day if isinstance(due_day, int) else None,
            "category": parsed.get("category") or "subscriptions",
            "recurrence": parsed.get("recurrence") or "monthly",
        }
    except Exception as exc:
        logger.debug("Bill parse failed: {}", exc)
        return None
