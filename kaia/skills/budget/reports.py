"""Budget report generation and formatting."""

from __future__ import annotations

from datetime import date, timedelta

from config.constants import BUDGET_CATEGORY_EMOJIS, CURRENCY_SYMBOLS
from database import queries as db
from database.models import BudgetLimit


async def get_period_summary(
    user_id: str,
    start_date: str,
    end_date: str,
) -> dict:
    """Return aggregated budget data for a date range.

    Returns dict with: income, expenses, net, categories (list of
    {category, total}), transaction_count.
    """
    income = await db.get_income_total(user_id, start_date, end_date)
    expenses = await db.get_expense_total(user_id, start_date, end_date)
    categories = await db.get_spending_by_category(user_id, start_date, end_date)
    transactions = await db.get_transactions(user_id, start_date, end_date)

    return {
        "income": income,
        "expenses": expenses,
        "net": income - expenses,
        "categories": categories,
        "transaction_count": len(transactions),
        "start_date": start_date,
        "end_date": end_date,
    }


async def get_category_spending(
    user_id: str,
    category: str,
    start_date: str,
    end_date: str,
) -> float:
    """Return total spending in a specific category for a date range."""
    return await db.get_category_total(user_id, category, start_date, end_date)


async def get_monthly_comparison(user_id: str) -> dict:
    """Compare current month vs last month spending."""
    today = date.today()

    # Current month
    current_start = today.replace(day=1).isoformat()
    current_end = today.isoformat()

    # Last month
    last_month_end = today.replace(day=1) - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1).isoformat()
    last_month_end_str = last_month_end.isoformat()

    current_expenses = await db.get_expense_total(user_id, current_start, current_end)
    last_expenses = await db.get_expense_total(user_id, last_month_start, last_month_end_str)

    current_income = await db.get_income_total(user_id, current_start, current_end)
    last_income = await db.get_income_total(user_id, last_month_start, last_month_end_str)

    if last_expenses > 0:
        expense_change_pct = ((current_expenses - last_expenses) / last_expenses) * 100
    else:
        expense_change_pct = 0.0

    return {
        "current_month_expenses": current_expenses,
        "last_month_expenses": last_expenses,
        "current_month_income": current_income,
        "last_month_income": last_income,
        "expense_change_pct": expense_change_pct,
    }


def format_summary_message(
    data: dict,
    currency_symbol: str,
    period_label: str,
    limits: list[BudgetLimit] | None = None,
) -> str:
    """Format a budget summary into a Telegram message."""
    income = data["income"]
    expenses = data["expenses"]
    net = data["net"]
    categories = data["categories"]

    sign = "+" if net >= 0 else ""
    lines = [
        f"📊 Budget Summary — {period_label}",
        "",
        f"💵 Income: {currency_symbol}{income:,.2f}",
        f"💸 Expenses: {currency_symbol}{expenses:,.2f}",
        f"📈 Net: {sign}{currency_symbol}{net:,.2f}",
    ]

    if categories:
        # Build a lookup of limits by category
        limit_map: dict[str, float] = {}
        if limits:
            limit_map = {bl.category: float(bl.monthly_limit) for bl in limits}

        lines.append("")
        lines.append("📂 Top Categories:")
        for entry in categories[:8]:
            cat = entry["category"]
            total = entry["total"]
            emoji = BUDGET_CATEGORY_EMOJIS.get(cat, "📦")
            limit_info = ""
            if cat in limit_map:
                lim = limit_map[cat]
                if total >= lim:
                    limit_info = f" ({currency_symbol}{lim:,.0f} limit 🚨)"
                elif total >= lim * 0.8:
                    limit_info = f" ({currency_symbol}{lim:,.0f} limit ⚠️)"
                else:
                    limit_info = f" ({currency_symbol}{lim:,.0f} limit)"
            lines.append(f"  {emoji} {cat.title()}: {currency_symbol}{total:,.2f}{limit_info}")

    if data.get("transaction_count", 0) == 0:
        lines.append("")
        lines.append("No transactions found for this period.")

    return "\n".join(lines)


def format_comparison_message(
    data: dict,
    currency_symbol: str,
) -> str:
    """Format month-over-month comparison."""
    current = data["current_month_expenses"]
    last = data["last_month_expenses"]
    change = data["expense_change_pct"]

    lines = [
        "📊 Month-over-Month Comparison",
        "",
        f"This month: {currency_symbol}{current:,.2f} spent",
        f"Last month: {currency_symbol}{last:,.2f} spent",
    ]

    if last > 0:
        if change > 0:
            lines.append(f"📈 Spending up {change:.0f}%")
        elif change < 0:
            lines.append(f"📉 Spending down {abs(change):.0f}% — nice!")
        else:
            lines.append("➡️ Same as last month")
    else:
        lines.append("No data for last month to compare.")

    return "\n".join(lines)


def format_budget_limits_message(
    limits: list[BudgetLimit],
    category_spending: dict[str, float],
    currency_symbol: str,
) -> str:
    """Format budget limits with current spending."""
    if not limits:
        return "No budget limits set. Use 'Set food budget to ₱5,000' to create one."

    lines = ["📋 Budget Limits\n"]
    for bl in limits:
        cat = bl.category
        lim = float(bl.monthly_limit)
        spent = category_spending.get(cat, 0.0)
        pct = (spent / lim * 100) if lim > 0 else 0
        emoji = BUDGET_CATEGORY_EMOJIS.get(cat, "📦")

        if pct >= 100:
            status = "🚨"
        elif pct >= 80:
            status = "⚠️"
        else:
            status = "✅"

        lines.append(
            f"{status} {emoji} {cat.title()}: "
            f"{currency_symbol}{spent:,.2f} / {currency_symbol}{lim:,.2f} "
            f"({pct:.0f}%)"
        )

    return "\n".join(lines)


def resolve_period(message: str) -> tuple[str, str, str]:
    """Determine date range from a natural language period reference.

    Returns (start_date, end_date, label) where dates are ISO format strings.
    """
    today = date.today()
    msg = message.lower()

    if "today" in msg:
        s = today.isoformat()
        return s, s, "Today"

    if "yesterday" in msg:
        y = (today - timedelta(days=1)).isoformat()
        return y, y, "Yesterday"

    if "last 7 days" in msg or "past week" in msg or "past 7 days" in msg:
        s = (today - timedelta(days=7)).isoformat()
        return s, today.isoformat(), "Last 7 Days"

    if "this week" in msg:
        monday = today - timedelta(days=today.weekday())
        return monday.isoformat(), today.isoformat(), "This Week"

    if "last week" in msg:
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        last_sunday = this_monday - timedelta(days=1)
        return last_monday.isoformat(), last_sunday.isoformat(), "Last Week"

    if "last month" in msg:
        first_this = today.replace(day=1)
        last_day_prev = first_this - timedelta(days=1)
        first_prev = last_day_prev.replace(day=1)
        return first_prev.isoformat(), last_day_prev.isoformat(), last_day_prev.strftime("%B %Y")

    # Default: this month
    first_of_month = today.replace(day=1)
    return first_of_month.isoformat(), today.isoformat(), today.strftime("%B %Y")
