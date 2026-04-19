"""Smart budget pattern analysis and waste detection."""

from __future__ import annotations

from datetime import date, timedelta

from config.constants import CURRENCY_SYMBOLS
from database import queries as db


class BudgetCoachingSkill:
    """Deep spending pattern analysis beyond basic tracking."""

    async def analyze_patterns(self, user_id: str, period_days: int = 30) -> dict:
        """Deep analysis of recent spending patterns."""
        today = date.today()
        start = (today - timedelta(days=period_days)).isoformat()
        end = today.isoformat()

        transactions = await db.get_transactions(user_id, start, end)
        expenses = [t for t in transactions if t.type == "expense"]

        total = sum(float(t.amount) for t in expenses) or 0.0

        categories: dict[str, float] = {}
        weekday_totals: dict[int, float] = {}
        day_of_month_totals: dict[int, float] = {}
        vendor_counts: dict[str, int] = {}
        vendor_totals: dict[str, float] = {}

        for t in expenses:
            amt = float(t.amount)
            categories[t.category] = categories.get(t.category, 0.0) + amt
            d = t.transaction_date
            weekday_totals[d.weekday()] = weekday_totals.get(d.weekday(), 0.0) + amt
            day_of_month_totals[d.day] = day_of_month_totals.get(d.day, 0.0) + amt
            vendor = (t.description or "").strip().lower()
            if vendor:
                vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1
                vendor_totals[vendor] = vendor_totals.get(vendor, 0.0) + amt

        top_categories = sorted(
            [
                {
                    "category": c,
                    "total": amount,
                    "pct": (amount / total * 100) if total > 0 else 0.0,
                }
                for c, amount in categories.items()
            ],
            key=lambda x: x["total"],
            reverse=True,
        )

        # Weekend (Sat/Sun) vs weekday aggregate
        weekend = sum(weekday_totals.get(d, 0.0) for d in (5, 6))
        weekday_amt = sum(weekday_totals.get(d, 0.0) for d in range(5))

        # Spending spikes = any day more than 2x the daily average
        if period_days > 0 and total > 0:
            daily_avg = total / period_days
            spike_days = [
                {"day": d, "amount": amt}
                for d, amt in day_of_month_totals.items()
                if amt > 2 * daily_avg
            ]
        else:
            daily_avg = 0.0
            spike_days = []

        # Repeated vendors (>= 5 hits in period)
        repeated_vendors = [
            {"vendor": v, "count": c, "total": vendor_totals[v]}
            for v, c in vendor_counts.items()
            if c >= 5
        ]
        repeated_vendors.sort(key=lambda x: x["total"], reverse=True)

        # Compare to previous period
        prev_start = (today - timedelta(days=period_days * 2)).isoformat()
        prev_end = (today - timedelta(days=period_days + 1)).isoformat()
        prev_expenses = await db.get_expense_total(user_id, prev_start, prev_end)

        return {
            "period_days": period_days,
            "total_expenses": total,
            "top_categories": top_categories[:5],
            "weekend_total": weekend,
            "weekday_total": weekday_amt,
            "daily_avg": daily_avg,
            "spike_days": spike_days[:5],
            "repeated_vendors": repeated_vendors[:5],
            "previous_period_total": prev_expenses,
            "change_vs_previous": (
                ((total - prev_expenses) / prev_expenses * 100)
                if prev_expenses > 0
                else 0.0
            ),
        }

    async def identify_waste(self, user_id: str) -> list[dict]:
        """Identify specific waste opportunities."""
        today = date.today()
        start = today.replace(day=1).isoformat()
        end = today.isoformat()

        income = await db.get_income_total(user_id, start, end)
        categories = await db.get_spending_by_category(user_id, start, end)
        transactions = await db.get_transactions(user_id, start, end)

        cat_totals = {c["category"]: c["total"] for c in categories}
        opportunities: list[dict] = []

        # Food delivery heuristic — if 'food' category has high concentration of
        # descriptions mentioning delivery-style services
        food_total = cat_totals.get("food", 0.0)
        delivery_terms = ("grab", "foodpanda", "delivery", "jollibee", "mcdo")
        delivery_spend = sum(
            float(t.amount)
            for t in transactions
            if t.type == "expense"
            and t.category == "food"
            and t.description
            and any(term in t.description.lower() for term in delivery_terms)
        )
        if food_total > 0 and delivery_spend / food_total > 0.4:
            monthly_save = delivery_spend * 0.4
            opportunities.append({
                "category": "food_delivery",
                "monthly_spend": delivery_spend,
                "suggestion": f"Cooking a few more meals/week could save ~₱{monthly_save:,.0f}/month",
                "annual_impact": monthly_save * 12,
            })

        # Subscriptions as share of income
        subs = cat_totals.get("subscriptions", 0.0)
        if income > 0 and subs / income > 0.05:
            opportunities.append({
                "category": "subscriptions",
                "monthly_spend": subs,
                "suggestion": "Subscriptions exceed 5% of income — audit what you actually use",
                "annual_impact": subs * 12 * 0.5,  # assume 50% cuttable
            })

        # Repeated small vendors (coffee runs, snacks)
        vendor_counts: dict[str, int] = {}
        vendor_totals: dict[str, float] = {}
        for t in transactions:
            if t.type != "expense" or not t.description:
                continue
            v = t.description.strip().lower()
            vendor_counts[v] = vendor_counts.get(v, 0) + 1
            vendor_totals[v] = vendor_totals.get(v, 0.0) + float(t.amount)
        for v, cnt in vendor_counts.items():
            if cnt >= 8 and vendor_totals[v] >= 500:
                opportunities.append({
                    "category": v,
                    "monthly_spend": vendor_totals[v],
                    "suggestion": f"{cnt} visits to '{v}' this month — cut by half to save ₱{vendor_totals[v]/2:,.0f}",
                    "annual_impact": vendor_totals[v] * 6,
                })

        return opportunities

    def format_patterns_report(self, data: dict, currency: str = "PHP") -> str:
        """Human-readable patterns summary."""
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        lines = [
            f"📊 *Spending Patterns — last {data['period_days']} days*",
            "",
            f"Total spent: {symbol}{data['total_expenses']:,.0f}",
            f"Daily average: {symbol}{data['daily_avg']:,.0f}",
        ]
        prev = data["previous_period_total"]
        if prev > 0:
            change = data["change_vs_previous"]
            arrow = "📈" if change > 0 else "📉"
            lines.append(
                f"vs previous period: {arrow} {change:+.0f}% ({symbol}{prev:,.0f})"
            )

        if data["top_categories"]:
            lines.append("")
            lines.append("*Top categories:*")
            for c in data["top_categories"]:
                lines.append(
                    f"  • {c['category'].title()}: {symbol}{c['total']:,.0f} ({c['pct']:.0f}%)"
                )

        total_weekly = data["weekend_total"] + data["weekday_total"]
        if total_weekly > 0:
            weekend_pct = data["weekend_total"] / total_weekly * 100
            lines.append("")
            lines.append(
                f"Weekend vs weekday: {weekend_pct:.0f}% weekends / "
                f"{100-weekend_pct:.0f}% weekdays"
            )

        if data["repeated_vendors"]:
            lines.append("")
            lines.append("*Repeat vendors:*")
            for v in data["repeated_vendors"][:3]:
                lines.append(
                    f"  • {v['vendor']}: {v['count']}× — {symbol}{v['total']:,.0f}"
                )

        return "\n".join(lines)

    def format_waste_report(self, opportunities: list[dict], currency: str = "PHP") -> str:
        """Render waste-identification results."""
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        if not opportunities:
            return (
                "✅ I couldn't spot any obvious waste this month. "
                "Keep logging transactions and I'll keep watching."
            )
        lines = ["💡 *Waste opportunities this month:*", ""]
        total_annual = 0.0
        for op in opportunities:
            lines.append(
                f"• *{op['category'].replace('_', ' ').title()}* — "
                f"{symbol}{op['monthly_spend']:,.0f}/mo"
            )
            lines.append(f"  {op['suggestion']}")
            total_annual += op["annual_impact"]
        if total_annual > 0:
            lines.append("")
            lines.append(f"Potential annual impact: ~{symbol}{total_annual:,.0f}")
        return "\n".join(lines)
