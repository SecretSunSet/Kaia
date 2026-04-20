"""Prompt builders for the budget skill."""

from __future__ import annotations

from datetime import date, timedelta

from config.constants import BUDGET_CATEGORIES, BUDGET_CATEGORY_EMOJIS


CATEGORIES_STR = ", ".join(BUDGET_CATEGORIES)


def build_parse_prompt(currency: str, today: date) -> str:
    """Build the system prompt for transaction parsing."""
    yesterday = today - timedelta(days=1)
    return f"""\
Parse this message as a financial transaction. The user's default currency is {currency}.

If this IS a financial transaction, return ONLY this JSON:
{{
  "amount": <number, no commas or currency symbols>,
  "type": "income" or "expense",
  "category": "<one of: {CATEGORIES_STR}>",
  "description": "<brief clean description>",
  "date": "<YYYY-MM-DD, use today {today.isoformat()} unless message specifies otherwise>"
}}

If this is NOT a financial transaction, return: {{"is_transaction": false}}

Rules:
- "log", "add", "record", "spent", "paid", "bought", "grabbed" = expense (unless
  the line explicitly says salary/income/received)
- "received", "got", "earned", "salary", "payment" (when receiving) = income
- Strip command phrases — "log into expenses", "add to expense", "log expense",
  "log these expenses:" are routing verbs, NOT part of the description
- Accept free-form descriptions with multiple words, merchants, and modifiers
  (e.g. "Tiktok Shop Elyse essentials 350 pesos" → amount 350,
  description "Tiktok Shop Elyse essentials")
- Accept dash/colon separators ("140 - Dishwashing Liquid", "Siopao: 135")
- Detect the most specific category possible. If unsure, pick "other"
- If amount has no currency symbol, assume {currency}
- "yesterday" = {yesterday.isoformat()}, "last week" = approximate
- Numbers with commas like "1,500" or "15,000" = strip commas
- Do NOT treat non-financial numbers as transactions (e.g. "30 minutes", "chapter 5")
"""


def build_summary_prompt(
    period: str,
    transaction_data: str,
    currency_symbol: str,
) -> str:
    """Build the system prompt for generating a budget summary."""
    return f"""\
Here is the user's transaction data for {period}:

{transaction_data}

Generate a concise, friendly budget summary. Include:
- Total income and total expenses
- Net (income - expenses)
- Top spending categories with amounts
- Any notable patterns or observations
- If budget limits are provided, mention categories that are close to or over limit

Keep it conversational, not robotic. Use the currency symbol {currency_symbol}.
"""


def build_budget_limit_parse_prompt(currency: str) -> str:
    """Build the system prompt for parsing budget limit requests."""
    return f"""\
Parse this budget limit setting request.

Return ONLY a JSON object:
{{
  "category": "<one of: {CATEGORIES_STR}>",
  "amount": <number, no commas or currency symbols>
}}

If this is NOT a budget limit request, return: {{"is_budget_limit": false}}

The user's default currency is {currency}.
"""


def format_transaction_confirmation(
    amount: float,
    type: str,
    category: str,
    description: str | None,
    currency_symbol: str,
) -> str:
    """Format a transaction log confirmation message."""
    icon = "💵" if type == "income" else "💸"
    desc = f" ({description})" if description else ""
    return f"{icon} Logged: {currency_symbol}{amount:,.2f} {type} — {category.title()}{desc}"


def format_bulk_log_response(
    logged: list[dict],
    failed: list[dict],
    currency_symbol: str,
) -> str:
    """Format a summary response for a bulk transaction log."""
    if not logged:
        return "❌ Couldn't log any of those transactions. Check the format?"

    total = sum(float(t["amount"]) for t in logged)
    lines = [
        f"✅ Logged {len(logged)} transactions — total "
        f"{currency_symbol}{total:,.2f}",
        "",
    ]

    by_cat: dict[str, list[dict]] = {}
    for t in logged:
        by_cat.setdefault(t["category"], []).append(t)

    for cat, items in by_cat.items():
        cat_total = sum(float(i["amount"]) for i in items)
        emoji = BUDGET_CATEGORY_EMOJIS.get(cat, "📦")
        lines.append(f"{emoji} {cat.title()}: {currency_symbol}{cat_total:,.2f}")
        for item in items:
            desc = item.get("description") or cat.title()
            lines.append(
                f"  • {desc}: {currency_symbol}{float(item['amount']):,.2f}"
            )

    if failed:
        lines.append("")
        lines.append(
            f"⚠️ Couldn't parse {len(failed)} line(s) — try again with amounts."
        )
    return "\n".join(lines)


def format_budget_warning(
    category: str,
    spent: float,
    limit: float,
    currency_symbol: str,
) -> str:
    """Format a budget warning message."""
    pct = (spent / limit) * 100 if limit > 0 else 0
    remaining = limit - spent

    if spent >= limit:
        return (
            f"\n\n🚨 Over budget! {category.title()}: "
            f"{currency_symbol}{spent:,.2f} / {currency_symbol}{limit:,.2f} "
            f"({pct:.0f}%) — {currency_symbol}{abs(remaining):,.2f} over"
        )
    return (
        f"\n\n⚠️ Budget alert! {category.title()}: "
        f"{currency_symbol}{spent:,.2f} / {currency_symbol}{limit:,.2f} "
        f"({pct:.0f}%) — {currency_symbol}{remaining:,.2f} left"
    )
