"""Channel-specific memory extraction — domain-focused fact extraction per expert."""

from __future__ import annotations

import json
import uuid

from loguru import logger

from core.ai_engine import AIEngine
from database.queries import (
    get_channel_profile,
    upsert_channel_profile,
    add_memory_log,
)


# Domain-specific extraction prompts per channel
_CHANNEL_DOMAINS: dict[str, str] = {
    "hevn": (
        "Focus on FINANCIAL facts: income, expenses, debts, savings, insurance, "
        "financial goals, risk tolerance, retirement plans, dependents, spending habits, "
        "Philippine financial products (SSS, Pag-IBIG, PhilHealth, MP2, BIR)."
    ),
    "kazuki": (
        "Focus on INVESTMENT facts: portfolio holdings, investment experience, "
        "monthly investment budget, time horizon, asset preferences, platforms used, "
        "investment history, risk appetite, diversification goals."
    ),
    "akabane": (
        "Focus on TRADING facts: exchange accounts, trading capital, risk per trade, "
        "trading experience, preferred pairs, trading style (scalper/swing/position), "
        "daily loss limits, TP/SL preferences, trade journal entries."
    ),
    "makubex": (
        "Focus on TECH facts: current projects, tech stack, skill levels per technology, "
        "learning goals, work context (solo/team/company), dev environment, "
        "programming languages, frameworks, tools, infrastructure experience."
    ),
}


def _build_channel_extraction_prompt(channel_id: str) -> str:
    """Build the system prompt for channel-specific memory extraction."""
    domain_focus = _CHANNEL_DOMAINS.get(channel_id, "Extract any relevant personal facts.")

    return f"""\
You are a memory extraction engine for an AI expert channel.

Your job: analyse the conversation below and extract NEW facts about the user.

DOMAIN FOCUS:
{domain_focus}

RULES:
- Only extract facts relevant to this expert's domain.
- Only extract facts that are NOT already in the existing profile.
- If a fact UPDATES or CORRECTS an existing entry, include it.
- Be conservative — only extract things the user clearly stated or strongly implied.
- Each fact must be atomic (one piece of information).
- Use lowercase keys with underscores (e.g. "monthly_income", "preferred_pairs").
- For time-sensitive facts ("got my salary Friday", "started saving last month"), \
resolve the actual date using the Current Time Context above and store it in \
absolute form in the value (e.g. "2026-04-25"), never relative phrases like \
"yesterday" or "last week".

OUTPUT FORMAT — return a JSON array (nothing else). Each item:
{{
  "category": "<domain_category>",
  "key": "<short_snake_case_key>",
  "value": "<the fact>",
  "confidence": <0.0-1.0>,
  "source": "<explicit or inferred>"
}}

If no new facts were learned, return an empty array: []
"""


async def channel_extract_and_save(
    ai_engine: AIEngine,
    user_id: str,
    channel_id: str,
    conversation_messages: list[dict[str, str]],
) -> int:
    """Run domain-focused extraction on channel conversation.

    Returns:
        Number of new/updated profile entries saved.
    """
    if len(conversation_messages) < 2:
        return 0

    # Load existing channel profile
    existing = await get_channel_profile(user_id, channel_id)
    profile_summary = ""
    if existing:
        profile_summary = "\n".join(
            f"- [{e.category}] {e.key}: {e.value}" for e in existing
        )

    # Build extraction prompt
    system_prompt = _build_channel_extraction_prompt(channel_id)

    # Format conversation (last 10 messages)
    convo_text = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Expert'}: {m['content']}"
        for m in conversation_messages[-10:]
    )

    user_message = (
        f"EXISTING CHANNEL PROFILE:\n{profile_summary or '(empty — first conversation)'}\n\n"
        f"CONVERSATION:\n{convo_text}\n\n"
        "Extract any new domain-relevant facts as a JSON array:"
    )

    try:
        response = await ai_engine.chat(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=512,
        )

        facts = _parse_facts(response.text)
        if not facts:
            logger.debug("Channel extraction ({}): no new facts found", channel_id)
            return 0

        session_id = str(uuid.uuid4())[:8]
        saved = 0

        for fact in facts:
            try:
                await upsert_channel_profile(
                    user_id=user_id,
                    channel_id=channel_id,
                    category=fact["category"],
                    key=fact["key"],
                    value=fact["value"],
                    confidence=fact.get("confidence", 0.5),
                    source=fact.get("source", "inferred"),
                )
                await add_memory_log(
                    user_id=user_id,
                    session_id=session_id,
                    fact=f"[{channel_id}:{fact['category']}] {fact['key']}: {fact['value']}",
                    fact_type="channel_extraction",
                )
                saved += 1
            except Exception as exc:
                logger.warning("Failed to save channel fact {}: {}", fact.get("key"), exc)

        logger.info(
            "Channel extraction ({}): saved {}/{} facts (session={})",
            channel_id, saved, len(facts), session_id,
        )
        return saved

    except Exception as exc:
        logger.warning("Channel extraction ({}) failed: {}", channel_id, exc)
        return 0


def _parse_facts(text: str) -> list[dict]:
    """Parse the AI response into a list of fact dicts."""
    text = text.strip()

    if text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    logger.debug("Could not parse facts from channel extraction response")
    return []
