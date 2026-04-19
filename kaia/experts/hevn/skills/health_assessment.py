"""Financial health assessment — weighted 1-100 score with component breakdown."""

from __future__ import annotations

from datetime import date, timedelta

from loguru import logger

from config.constants import CURRENCY_SYMBOLS
from database import queries as db


class FinancialHealthSkill:
    """Calculates and explains a 1-100 financial health score."""

    # Component weights (sum to 1.0)
    _WEIGHTS = {
        "savings_rate": 0.25,
        "debt_ratio": 0.25,
        "emergency_fund": 0.25,
        "income_stability": 0.15,
        "expense_control": 0.10,
    }

    async def assess(self, user_id: str, currency: str = "PHP") -> dict:
        """Analyze a user's complete financial picture."""
        today = date.today()

        # Use last 3 months for income/expense base rate
        three_months_ago = (today - timedelta(days=90)).isoformat()
        last_month_end = today.replace(day=1) - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        total_income_90d = await db.get_income_total(
            user_id, three_months_ago, today.isoformat()
        )
        total_expenses_90d = await db.get_expense_total(
            user_id, three_months_ago, today.isoformat()
        )
        last_month_income = await db.get_income_total(
            user_id, last_month_start.isoformat(), last_month_end.isoformat()
        )
        last_month_expenses = await db.get_expense_total(
            user_id, last_month_start.isoformat(), last_month_end.isoformat()
        )

        monthly_income_avg = total_income_90d / 3.0 if total_income_90d else 0.0
        monthly_expenses_avg = total_expenses_90d / 3.0 if total_expenses_90d else 0.0

        # Channel profile — Hevn's memory
        profile_entries = await db.get_channel_profile(user_id, "hevn")
        profile_map = {e.key: e.value for e in profile_entries}

        # Components
        savings_comp = _score_savings_rate(monthly_income_avg, monthly_expenses_avg)
        debt_comp = _score_debt_ratio(monthly_income_avg, profile_map)
        emergency_comp = await _score_emergency_fund(
            user_id, monthly_expenses_avg, profile_map
        )
        income_comp = _score_income_stability(profile_map, last_month_income)
        expense_comp = _score_expense_control(
            monthly_expenses_avg, last_month_expenses
        )

        components = {
            "savings_rate": savings_comp,
            "debt_ratio": debt_comp,
            "emergency_fund": emergency_comp,
            "income_stability": income_comp,
            "expense_control": expense_comp,
        }

        score = int(
            round(sum(components[k]["score"] * w for k, w in self._WEIGHTS.items()))
        )
        grade = _grade(score)

        strengths = [v["note"] for v in components.values() if v["score"] >= 80]
        weaknesses = [v["note"] for v in components.values() if v["score"] < 60]

        priority_action = _priority_action(components, currency)

        return {
            "score": score,
            "grade": grade,
            "components": components,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "priority_action": priority_action,
            "monthly_income_avg": monthly_income_avg,
            "monthly_expenses_avg": monthly_expenses_avg,
        }

    def format_health_report(self, assessment: dict, currency: str = "PHP") -> str:
        """Format the assessment into a Telegram-ready message."""
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        score = assessment["score"]
        grade = assessment["grade"]
        comps = assessment["components"]

        lines = [
            f"📊 *Financial Health Score: {score}/100 — {grade}*",
            "",
            f"💵 Avg monthly income: {symbol}{assessment['monthly_income_avg']:,.0f}",
            f"💸 Avg monthly expenses: {symbol}{assessment['monthly_expenses_avg']:,.0f}",
            "",
            "*Components:*",
        ]

        for key in ("savings_rate", "debt_ratio", "emergency_fund",
                    "income_stability", "expense_control"):
            c = comps[key]
            label = key.replace("_", " ").title()
            lines.append(f"  • {label}: {c['score']}/100 — {c['note']}")

        if assessment["strengths"]:
            lines.append("")
            lines.append("✅ *Strengths:*")
            for s in assessment["strengths"][:3]:
                lines.append(f"  • {s}")

        if assessment["weaknesses"]:
            lines.append("")
            lines.append("⚠️ *Needs Attention:*")
            for w in assessment["weaknesses"][:3]:
                lines.append(f"  • {w}")

        lines.append("")
        lines.append(f"🎯 *Priority:* {assessment['priority_action']}")
        return "\n".join(lines)


def _grade(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 55:
        return "Fair"
    if score >= 40:
        return "Needs Work"
    return "Critical"


def _score_savings_rate(income: float, expenses: float) -> dict:
    if income <= 0:
        return {
            "score": 0,
            "value": 0,
            "benchmark": 20,
            "note": "No income data logged",
        }
    saved = max(income - expenses, 0.0)
    rate = (saved / income) * 100
    # 0% → 0 points; 20% → 80 points; 30%+ → 100
    score = int(min(round((rate / 30.0) * 100), 100))
    note = f"Saving {rate:.0f}% of income"
    return {"score": score, "value": rate, "benchmark": 20, "note": note}


def _score_debt_ratio(monthly_income: float, profile_map: dict) -> dict:
    if monthly_income <= 0:
        return {
            "score": 50,
            "value": 0,
            "benchmark": 36,
            "note": "Debt ratio unknown",
        }
    debt_text = (profile_map.get("active_debts") or "").lower()
    if not debt_text or "no debt" in debt_text or "none" in debt_text:
        return {
            "score": 100,
            "value": 0,
            "benchmark": 36,
            "note": "No active debt",
        }
    # Can't reliably parse amount; assume moderate when mentioned
    return {
        "score": 55,
        "value": 30,
        "benchmark": 36,
        "note": f"Active debts noted: {debt_text[:60]}",
    }


async def _score_emergency_fund(
    user_id: str, monthly_expenses: float, profile_map: dict
) -> dict:
    months = 0.0
    try:
        goals = await db.get_financial_goals(user_id, status="active")
        ef = next((g for g in goals if "emergency" in g.name.lower()), None)
        if ef is not None and monthly_expenses > 0:
            months = float(ef.current_amount) / monthly_expenses
    except Exception as exc:
        logger.debug("Emergency fund lookup failed: {}", exc)

    if months == 0.0:
        emf_text = (profile_map.get("emergency_fund") or "").lower()
        if emf_text and ("none" in emf_text or "0" in emf_text or "no" in emf_text):
            months = 0.0
        elif emf_text and monthly_expenses > 0:
            # Unknown amount — conservative estimate if they said they have one
            months = 1.0

    # 6+ months → 100
    score = int(min(round((months / 6.0) * 100), 100))
    note = (
        f"{months:.1f} months of expenses covered"
        if monthly_expenses > 0
        else "Emergency fund unknown (no expense baseline)"
    )
    return {"score": score, "months": months, "target": 6, "note": note}


def _score_income_stability(profile_map: dict, last_month_income: float) -> dict:
    freq = (profile_map.get("income_frequency") or "").lower()
    sources = (profile_map.get("income_sources") or "").lower()
    if "monthly" in freq or "salary" in freq or "regular" in freq:
        score = 85
        note = "Regular monthly income"
    elif "bi-weekly" in freq or "weekly" in freq:
        score = 80
        note = "Regular bi-weekly income"
    elif "freelance" in sources or "irregular" in freq:
        score = 55
        note = "Irregular income — plan buffers"
    elif last_month_income > 0:
        score = 65
        note = "Some income logged; pattern unclear"
    else:
        score = 40
        note = "Income pattern not yet tracked"
    return {"score": score, "note": note}


def _score_expense_control(current_expenses: float, last_expenses: float) -> dict:
    if last_expenses <= 0:
        return {"score": 70, "note": "Not enough history to compare"}
    change = (current_expenses - last_expenses) / last_expenses
    if change <= -0.05:
        return {"score": 90, "note": "Expenses down vs last month"}
    if change <= 0.05:
        return {"score": 80, "note": "Expenses stable month-over-month"}
    if change <= 0.15:
        return {"score": 60, "note": "Expenses up slightly vs last month"}
    return {"score": 35, "note": f"Expenses up {change*100:.0f}% vs last month"}


def _priority_action(components: dict, currency: str) -> str:
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    # Pick the lowest-scoring component for the priority
    lowest_key = min(components, key=lambda k: components[k]["score"])
    c = components[lowest_key]

    if lowest_key == "emergency_fund":
        months = c.get("months", 0.0)
        target = c.get("target", 6)
        gap_months = max(target - months, 0)
        return f"Build emergency fund to {target} months of expenses ({gap_months:.1f} months to go)"
    if lowest_key == "savings_rate":
        return "Raise your savings rate toward 20% — automate a monthly transfer"
    if lowest_key == "debt_ratio":
        return "Tackle high-interest debt first; list balances and rates"
    if lowest_key == "income_stability":
        return "Log your income consistently so I can spot patterns"
    if lowest_key == "expense_control":
        return "Rein in expense growth — I can show you the top drivers"
    return "Keep logging transactions so I can refine this assessment"
