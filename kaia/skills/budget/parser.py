"""NLP parsing of financial messages using Claude."""

from __future__ import annotations

import json
from datetime import date

from loguru import logger

from core.ai_engine import AIEngine
from skills.budget.prompts import build_parse_prompt, build_budget_limit_parse_prompt


async def parse_transaction(
    ai_engine: AIEngine,
    message: str,
    currency: str = "PHP",
) -> dict | None:
    """Parse a natural language financial message into structured data.

    Returns a dict with keys: amount, type, category, description, date.
    Returns None if the message is not a financial transaction.
    """
    today = date.today()
    system_prompt = build_parse_prompt(currency, today)

    try:
        response = await ai_engine.chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": message}],
            max_tokens=128,
        )
        return _parse_transaction_response(response.text)
    except Exception as exc:
        logger.error("Transaction parsing failed: {}", exc)
        return None


async def parse_budget_limit(
    ai_engine: AIEngine,
    message: str,
    currency: str = "PHP",
) -> dict | None:
    """Parse a budget limit setting request.

    Returns a dict with keys: category, amount.
    Returns None if the message is not a budget limit request.
    """
    system_prompt = build_budget_limit_parse_prompt(currency)

    try:
        response = await ai_engine.chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": message}],
            max_tokens=64,
        )
        return _parse_budget_limit_response(response.text)
    except Exception as exc:
        logger.error("Budget limit parsing failed: {}", exc)
        return None


def _parse_transaction_response(text: str) -> dict | None:
    """Extract transaction JSON from AI response."""
    data = _extract_json(text)
    if data is None:
        return None

    # Not a transaction
    if data.get("is_transaction") is False:
        return None

    # Validate required fields
    required = ("amount", "type", "category")
    if not all(k in data for k in required):
        logger.warning("Transaction parse missing fields: {}", data)
        return None

    try:
        amount = float(str(data["amount"]).replace(",", ""))
    except (ValueError, TypeError):
        logger.warning("Invalid amount: {}", data.get("amount"))
        return None

    if amount <= 0:
        return None

    return {
        "amount": amount,
        "type": data["type"],
        "category": data["category"],
        "description": data.get("description"),
        "date": data.get("date", date.today().isoformat()),
    }


def _parse_budget_limit_response(text: str) -> dict | None:
    """Extract budget limit JSON from AI response."""
    data = _extract_json(text)
    if data is None:
        return None

    if data.get("is_budget_limit") is False:
        return None

    if "category" not in data or "amount" not in data:
        return None

    try:
        amount = float(str(data["amount"]).replace(",", ""))
    except (ValueError, TypeError):
        return None

    if amount <= 0:
        return None

    return {"category": data["category"], "amount": amount}


def _extract_json(text: str) -> dict | None:
    """Extract a JSON object from text (handles wrapped responses)."""
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from budget response: {}", text[:100])
    return None
