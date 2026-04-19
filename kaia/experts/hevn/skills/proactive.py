"""Proactive financial alerts, weekly digest, and salary allocation."""

from __future__ import annotations

from datetime import date, timedelta

from loguru import logger

from config.constants import CURRENCY_SYMBOLS
from database import queries as db
from experts.hevn.skills.bills_tracker import BillsTrackerSkill
from experts.hevn.skills.goals_manager import GoalsManagerSkill
from experts.hevn.skills.health_assessment import FinancialHealthSkill


class ProactiveAlertsSkill:
    """Event-triggered alerts and scheduled digests."""

    def __init__(self) -> None:
        self._bills = BillsTrackerSkill()
        self._goals = GoalsManagerSkill()
        self._health = FinancialHealthSkill()

    async def generate_weekly_digest(
        self, user_id: str, currency: str = "PHP"
    ) -> str:
        """Compile a weekly financial digest."""
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        today = date.today()
        week_start = today - timedelta(days=7)
        prev_start = today - timedelta(days=14)
        prev_end = today - timedelta(days=8)

        current_expenses = await db.get_expense_total(
            user_id, week_start.isoformat(), today.isoformat()
        )
        last_expenses = await db.get_expense_total(
            user_id, prev_start.isoformat(), prev_end.isoformat()
        )
        current_income = await db.get_income_total(
            user_id, week_start.isoformat(), today.isoformat()
        )

        savings_rate = None
        if current_income > 0:
            savings_rate = max((current_income - current_expenses) / current_income, 0) * 100

        upcoming = await self._bills.get_upcoming(user_id, days=7)
        goals = await self._goals.get_goals(user_id, status="active")

        lines: list[str] = [
            f"💰 *Hevn's Weekly Digest — {today.strftime('%b %d, %Y')}*",
            "",
        ]

        # Week's spending
        if current_expenses > 0 or last_expenses > 0:
            lines.append(
                f"💸 Spending this week: {symbol}{current_expenses:,.0f}"
            )
            if last_expenses > 0:
                change = (current_expenses - last_expenses) / last_expenses * 100
                arrow = "📈" if change > 0 else "📉"
                lines.append(
                    f"   vs last week: {arrow} {change:+.0f}% ({symbol}{last_expenses:,.0f})"
                )

        # Income
        if current_income > 0:
            lines.append(f"💵 Income this week: {symbol}{current_income:,.0f}")

        # Savings rate
        if savings_rate is not None:
            lines.append(f"📊 Savings rate: {savings_rate:.0f}%")

        # Goals
        if goals:
            lines.append("")
            lines.append("🎯 *Goal progress:*")
            for g in goals[:3]:
                pct = (float(g.current_amount) / float(g.target_amount) * 100) if float(g.target_amount) > 0 else 0
                lines.append(
                    f"  • {g.name}: {symbol}{float(g.current_amount):,.0f} / "
                    f"{symbol}{float(g.target_amount):,.0f} ({pct:.0f}%)"
                )

        # Bills
        if upcoming:
            lines.append("")
            lines.append("📅 *Bills due this week:*")
            for entry in upcoming[:5]:
                bill = entry["bill"]
                nd = entry["next_due"]
                lines.append(
                    f"  • {nd.strftime('%b %d')} — {bill.name}: "
                    f"{symbol}{float(bill.amount):,.0f}"
                )

        # Insight — simple heuristic
        if last_expenses > 0 and current_expenses > last_expenses * 1.2:
            lines.append("")
            lines.append(
                "⚠️ Spending spike this week — worth a quick review."
            )
        elif savings_rate is not None and savings_rate >= 30:
            lines.append("")
            lines.append("✅ Great savings rate this week — keep it going.")

        # Tip of the week (rotating short tip)
        lines.append("")
        lines.append(f"💡 _Tip:_ {_tip_of_the_week(today)}")

        return "\n".join(lines)

    async def check_spending_alerts(
        self, user_id: str, currency: str = "PHP"
    ) -> list[str]:
        """Check for spending anomalies deserving alerts."""
        alerts: list[str] = []
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        today = date.today()
        start_of_month = today.replace(day=1)
        days_passed = (today - start_of_month).days + 1
        days_remaining = _days_in_month(today) - today.day

        try:
            limits = await db.get_budget_limits(user_id)
        except Exception as exc:
            logger.warning("spending_alerts: limit fetch failed: {}", exc)
            return alerts

        for lim in limits:
            spent = await db.get_category_total(
                user_id,
                lim.category,
                start_of_month.isoformat(),
                today.isoformat(),
            )
            monthly = float(lim.monthly_limit)
            if monthly <= 0:
                continue
            pct = spent / monthly * 100
            if pct >= 100:
                alerts.append(
                    f"🚨 *{lim.category.title()}* over budget: "
                    f"{symbol}{spent:,.0f} / {symbol}{monthly:,.0f}"
                )
            elif pct >= 80 and days_remaining >= 7:
                alerts.append(
                    f"⚠️ *{lim.category.title()}* at {pct:.0f}% of budget with "
                    f"{days_remaining} days left this month"
                )

        # Daily-average spike check
        total_month = await db.get_expense_total(
            user_id, start_of_month.isoformat(), today.isoformat()
        )
        if days_passed > 0:
            daily_avg = total_month / days_passed
            last_day_total = await db.get_expense_total(
                user_id, today.isoformat(), today.isoformat()
            )
            if daily_avg > 0 and last_day_total > 2 * daily_avg:
                alerts.append(
                    f"📈 Today's spend {symbol}{last_day_total:,.0f} is more than 2× "
                    f"your daily average ({symbol}{daily_avg:,.0f})"
                )

        return alerts

    async def check_goal_milestones(
        self, user_id: str, currency: str = "PHP"
    ) -> list[str]:
        """Check if any goals newly crossed 25/50/75/100% thresholds.

        Note: purely informational — this inspects current state only. Real
        milestone celebrations happen inline on `update_progress`.
        """
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        goals = await self._goals.get_goals(user_id, status="active")
        messages: list[str] = []
        for g in goals:
            target = float(g.target_amount)
            current = float(g.current_amount)
            if target <= 0:
                continue
            pct = current / target * 100
            for threshold in (100, 75, 50, 25):
                if pct >= threshold:
                    messages.append(
                        f"✨ {g.name}: {threshold}%+ reached "
                        f"({symbol}{current:,.0f} / {symbol}{target:,.0f})"
                    )
                    break
        return messages

    async def handle_salary_received(
        self,
        user_id: str,
        amount: float,
        currency: str = "PHP",
    ) -> str:
        """Suggest allocation when salary is received."""
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        allocations = await self._goals.suggest_allocation(user_id, amount * 0.3)
        total_allocated = sum(a["amount"] for a in allocations)
        remaining = amount - total_allocated

        lines = [
            f"💰 *Your salary of {symbol}{amount:,.0f} just landed!*",
            "",
        ]
        if allocations:
            lines.append("Based on your goals, here's a suggested split:")
            for a in allocations:
                lines.append(
                    f"  • {symbol}{a['amount']:,.0f} → {a['name']}"
                )
            lines.append(f"  • {symbol}{remaining:,.0f} for monthly expenses")
        else:
            lines.append(
                "No active goals yet — tell me what you're saving for and I'll "
                "suggest an allocation next time."
            )
        lines.append("")
        lines.append("Want me to log these transfers?")
        return "\n".join(lines)


_TIPS: tuple[str, ...] = (
    "Automate your savings transfer on payday — pay yourself first.",
    "Check if your emergency fund is earning interest in a high-yield account.",
    "MP2 is tax-free and often beats a regular savings account over 5 years.",
    "Track subscriptions quarterly — you'll almost always find one to cancel.",
    "Compare your expense categories to income percentages, not absolute pesos.",
    "A 20% savings rate is solid; 30%+ unlocks serious compounding.",
    "Review BIR tax bracket yearly — big raises can push you into a new bracket.",
)


def _tip_of_the_week(today: date) -> str:
    return _TIPS[today.isocalendar().week % len(_TIPS)]


def _days_in_month(d: date) -> int:
    from calendar import monthrange
    return monthrange(d.year, d.month)[1]
