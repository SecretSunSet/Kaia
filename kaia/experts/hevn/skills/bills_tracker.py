"""Recurring bills and subscription tracking."""

from __future__ import annotations

from datetime import date, timedelta

from config.constants import CURRENCY_SYMBOLS
from database import queries as db
from database.models import RecurringBill


class BillsTrackerSkill:
    """Track recurring bills and subscriptions."""

    async def add_bill(
        self,
        user_id: str,
        name: str,
        amount: float,
        due_day: int | None = None,
        category: str | None = None,
        recurrence: str = "monthly",
    ) -> RecurringBill:
        """Add a new recurring bill."""
        return await db.create_recurring_bill(
            user_id=user_id,
            name=name,
            amount=amount,
            due_day=due_day,
            category=category,
            recurrence=recurrence,
        )

    async def list_bills(
        self, user_id: str, active_only: bool = True
    ) -> list[dict]:
        """List bills with next-due-date computed."""
        bills = await db.get_recurring_bills(user_id, active_only=active_only)
        return [_with_next_due(b) for b in bills]

    async def get_upcoming(
        self, user_id: str, days: int = 7
    ) -> list[dict]:
        """Bills due within the next N days (monthly recurrence only)."""
        bills = await db.get_recurring_bills(user_id, active_only=True)
        today = date.today()
        cutoff = today + timedelta(days=days)
        result: list[dict] = []
        for b in bills:
            enriched = _with_next_due(b)
            nd = enriched.get("next_due")
            if nd and today <= nd <= cutoff:
                result.append(enriched)
        result.sort(key=lambda x: x["next_due"])
        return result

    async def calculate_monthly_total(self, user_id: str) -> dict:
        """Total monthly bill spend with a category breakdown."""
        bills = await db.get_recurring_bills(user_id, active_only=True)
        by_category: dict[str, float] = {}
        total = 0.0
        for b in bills:
            monthly = _to_monthly_amount(b)
            total += monthly
            cat = b.category or "other"
            by_category[cat] = by_category.get(cat, 0.0) + monthly
        return {"total": total, "by_category": by_category, "count": len(bills)}

    async def identify_forgotten_subscriptions(self, user_id: str) -> list[dict]:
        """Flag subscriptions that may still be charging without recent use.

        Cross-references `recurring_bills` with `transactions` — best-effort.
        """
        bills = await db.get_recurring_bills(user_id, active_only=True)
        today = date.today()
        ninety_days_ago = (today - timedelta(days=90)).isoformat()
        transactions = await db.get_transactions(
            user_id, ninety_days_ago, today.isoformat()
        )

        flagged: list[dict] = []
        for b in bills:
            if (b.category or "").lower() != "subscriptions":
                continue
            # Any matching transaction in last 90 days?
            name_lower = b.name.lower()
            has_match = any(
                t.description and name_lower in t.description.lower()
                for t in transactions
            )
            if not has_match:
                flagged.append({
                    "bill_id": b.id,
                    "name": b.name,
                    "amount": float(b.amount),
                    "note": "No matching transactions in the last 90 days",
                })
        return flagged

    async def mark_paid(self, bill_id: str) -> RecurringBill:
        """Mark a bill as paid and update last_paid."""
        today = date.today().isoformat()
        await db.update_recurring_bill(bill_id, last_paid=today)
        bill = await db.get_recurring_bill_by_id(bill_id)
        if bill is None:
            raise ValueError(f"Bill {bill_id} not found")
        return bill

    def format_bills_list(
        self, bills: list[dict], currency: str = "PHP"
    ) -> str:
        """Render a bills list for Telegram."""
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        if not bills:
            return (
                "🧾 No recurring bills tracked yet.\n\n"
                "Tell me one — e.g., 'Netflix is ₱549 on the 20th'."
            )
        lines = ["🧾 *Recurring Bills*", ""]
        total = 0.0
        for b in bills:
            bill: RecurringBill = b["bill"]
            amt = float(bill.amount)
            total += _to_monthly_amount(bill)
            next_due = b.get("next_due")
            due_part = (
                f" — next: {next_due.strftime('%b %d')}"
                if next_due
                else ""
            )
            cat = f" [{bill.category}]" if bill.category else ""
            lines.append(
                f"• *{bill.name}*{cat} — {symbol}{amt:,.0f}{due_part}"
            )
        lines.append("")
        lines.append(f"_Monthly equivalent total: {symbol}{total:,.0f}_")
        return "\n".join(lines)

    def format_upcoming(
        self, upcoming: list[dict], currency: str = "PHP"
    ) -> str:
        """Render upcoming bills."""
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        if not upcoming:
            return "✅ No bills due in the next 7 days."
        lines = ["📅 *Bills due in the next 7 days:*", ""]
        total = 0.0
        for entry in upcoming:
            bill: RecurringBill = entry["bill"]
            nd = entry["next_due"]
            amt = float(bill.amount)
            total += amt
            lines.append(
                f"• {nd.strftime('%b %d')} — *{bill.name}*: {symbol}{amt:,.0f}"
            )
        lines.append("")
        lines.append(f"_Total owed this week: {symbol}{total:,.0f}_")
        return "\n".join(lines)


def _next_due_date(due_day: int | None, today: date | None = None) -> date | None:
    """Return the next occurrence of `due_day` in a calendar month."""
    if due_day is None:
        return None
    today = today or date.today()
    year, month = today.year, today.month
    # Clamp day for short months
    day = min(due_day, _days_in_month(year, month))
    candidate = date(year, month, day)
    if candidate < today:
        # Next month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        day = min(due_day, _days_in_month(year, month))
        candidate = date(year, month, day)
    return candidate


def _days_in_month(year: int, month: int) -> int:
    from calendar import monthrange
    return monthrange(year, month)[1]


def _with_next_due(bill: RecurringBill) -> dict:
    return {
        "bill": bill,
        "next_due": _next_due_date(bill.due_day),
    }


def _to_monthly_amount(bill: RecurringBill) -> float:
    """Convert recurrence to a monthly-equivalent amount."""
    rec = (bill.recurrence or "monthly").lower()
    amt = float(bill.amount)
    if rec == "weekly":
        return amt * 4.33
    if rec == "yearly":
        return amt / 12
    if rec == "quarterly":
        return amt / 3
    return amt  # monthly (default)
