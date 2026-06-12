"""AI-driven parsers for Hevn — goal, bill, and intent classification."""

from __future__ import annotations

import json
import re
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

# Word-boundary regex prevents substring false positives ("owe" in "lower",
# "loan" in nothing common — but \b keeps it honest). "pay off" is NOT here:
# it collides with bill phrasing; payment messages reach debt via the AI
# fallback instead.
_DEBT_INTENT_RE = re.compile(
    r"\b(debts?|owes?|owed|owing|utang|loans?|payoff)\b"
    r"|get out of debt|credit card balance"
)

# Conceptual/educational questions about debt instruments should reach the
# education route further down the chain, not the debt-records skill.
_EDUCATION_DEFER_MARKERS = (
    "explain", "what is", "what's", "teach me", "learn about",
    "how does", "how do",
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

    if _DEBT_INTENT_RE.search(low) and not any(
        m in low for m in _EDUCATION_DEFER_MARKERS
    ):
        return "debt"

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
                "market_trends", "education", "general_chat", "debt",
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


async def parse_debt_mention(ai: AIEngine, message: str) -> dict | None:
    """Parse debt details from a message. Returns a dict of the keys below
    (values None when not stated), or None when NO field was found.

    Partial results matter: during the guided audit the user answers one
    field at a time ("3.5% monthly"), so callers merge dicts.
    """
    system = (
        "Extract debt details from the user's message. Return ONLY a JSON "
        "object with these keys (null if not stated): "
        '{"name": string or null (lender/product, e.g. "BPI Credit Card"), '
        '"debt_type": "credit_card"|"salary_loan"|"personal_loan"|"five_six"'
        '|"pagibig_loan"|"sss_loan"|"auto_loan"|"mortgage"|"other"|null, '
        '"balance": number or null (pesos), '
        '"interest_rate": number or null (percent, as quoted), '
        '"rate_period": "monthly"|"yearly"|null, '
        '"minimum_payment": number or null, '
        '"due_day": integer 1-31 or null}. '
        "Treat shorthand like '45k' as 45000. If the message has no debt "
        "details at all, return every key as null."
    )
    try:
        response = await ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": message}],
            max_tokens=200,
        )
        text = response.text.strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict):
            return None
        keys = (
            "name", "debt_type", "balance", "interest_rate",
            "rate_period", "minimum_payment", "due_day",
        )
        result = {k: parsed.get(k) for k in keys}
        if all(v is None for v in result.values()):
            return None
        return result
    except Exception as exc:
        logger.debug("parse_debt_mention failed: {}", exc)
        return None


async def parse_debt_payment(ai: AIEngine, message: str) -> dict | None:
    """Parse 'paid 5k on my BPI card' -> {"debt_name": ..., "amount": ...}."""
    system = (
        "The user reports paying money toward a debt. Return ONLY a JSON "
        'object: {"debt_name": string or null, "amount": number or null '
        "(pesos; treat '5k' as 5000)}. If this is not a debt payment, "
        "return both as null."
    )
    try:
        response = await ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": message}],
            max_tokens=80,
        )
        text = response.text.strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        parsed = json.loads(text[start:end + 1])
        if not isinstance(parsed, dict) or parsed.get("amount") is None:
            return None
        return {"debt_name": parsed.get("debt_name"), "amount": parsed["amount"]}
    except Exception as exc:
        logger.debug("parse_debt_payment failed: {}", exc)
        return None


async def parse_amount(ai: AIEngine, message: str) -> float | None:
    """Parse a single peso amount from a free-form answer."""
    system = (
        "Extract the single peso amount the user states. Return ONLY a JSON "
        'object: {"amount": number or null}. Treat \'15k\' as 15000.'
    )
    try:
        response = await ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": message}],
            max_tokens=40,
        )
        text = response.text.strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        parsed = json.loads(text[start:end + 1])
        amount = parsed.get("amount") if isinstance(parsed, dict) else None
        return float(amount) if amount is not None else None
    except Exception as exc:
        logger.debug("parse_amount failed: {}", exc)
        return None
