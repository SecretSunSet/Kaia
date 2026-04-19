"""Financial goals skill — create, track, project, and allocate."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from loguru import logger

from config.constants import CURRENCY_SYMBOLS
from database import queries as db
from database.models import FinancialGoal


class GoalsManagerSkill:
    """Manages financial goals with progress tracking and projections."""

    async def create_goal(
        self,
        user_id: str,
        name: str,
        target: float,
        deadline: date | None = None,
        monthly: float | None = None,
        priority: int = 1,
    ) -> FinancialGoal:
        """Create a new financial goal."""
        return await db.create_financial_goal(
            user_id=user_id,
            name=name,
            target_amount=target,
            deadline=deadline.isoformat() if deadline else None,
            monthly_contribution=monthly,
            priority=priority,
        )

    async def update_progress(
        self, goal_id: str, amount: float
    ) -> tuple[FinancialGoal, list[int]]:
        """Add progress to a goal.

        Returns (updated_goal, milestones_hit). Milestones are the
        newly-crossed thresholds out of [25, 50, 75, 100].
        """
        goal = await db.get_financial_goal_by_id(goal_id)
        if goal is None:
            raise ValueError(f"Goal {goal_id} not found")

        prev_pct = _pct_complete(goal)
        new_amount = goal.current_amount + Decimal(str(amount))
        update_fields: dict[str, object] = {"current_amount": float(new_amount)}
        if new_amount >= goal.target_amount:
            update_fields["status"] = "completed"
        await db.update_financial_goal(goal_id, **update_fields)

        # Reload for current snapshot
        updated = await db.get_financial_goal_by_id(goal_id)
        if updated is None:
            raise RuntimeError("Goal vanished after update")
        new_pct = _pct_complete(updated)

        hit: list[int] = []
        for threshold in (25, 50, 75, 100):
            if prev_pct < threshold <= new_pct:
                hit.append(threshold)
        return updated, hit

    async def get_goals(
        self, user_id: str, status: str | None = "active"
    ) -> list[FinancialGoal]:
        """List all goals with their raw records."""
        return await db.get_financial_goals(user_id, status=status)

    def project_timeline(self, goal: FinancialGoal) -> dict:
        """Project when goal completes at current contribution rate."""
        remaining = float(goal.target_amount) - float(goal.current_amount)
        monthly = float(goal.monthly_contribution or 0)
        today = date.today()

        result: dict = {
            "remaining": remaining,
            "monthly": monthly,
            "months_remaining": None,
            "projected_completion_date": None,
            "on_track": None,
            "monthly_needed_to_meet_deadline": None,
        }

        if remaining <= 0:
            result["on_track"] = True
            result["months_remaining"] = 0
            result["projected_completion_date"] = today
            return result

        if monthly > 0:
            months = remaining / monthly
            result["months_remaining"] = months
            # Approximate: add months to today (30-day months)
            days_ahead = int(round(months * 30))
            result["projected_completion_date"] = _add_days(today, days_ahead)

        if goal.deadline:
            months_left = _months_between(today, goal.deadline)
            if months_left > 0:
                needed = remaining / months_left
                result["monthly_needed_to_meet_deadline"] = needed
                if monthly > 0:
                    result["on_track"] = monthly >= needed
                else:
                    result["on_track"] = False
            else:
                result["on_track"] = float(goal.current_amount) >= float(goal.target_amount)

        return result

    async def suggest_allocation(
        self, user_id: str, available: float
    ) -> list[dict]:
        """Given an amount, suggest allocation across active goals.

        Heuristic:
          1. Sort goals by urgency (deadline soonest first, then priority).
          2. For goals with monthly_needed_to_meet_deadline, fill that first.
          3. Distribute remaining proportionally to remaining target amounts.
        """
        goals = await db.get_financial_goals(user_id, status="active")
        if not goals or available <= 0:
            return []

        projections = [(g, self.project_timeline(g)) for g in goals]

        # Phase 1 — deadline obligations
        allocations: dict[str, float] = {g.id: 0.0 for g in goals}
        remaining_budget = float(available)

        deadline_goals = [
            (g, p) for g, p in projections
            if p.get("monthly_needed_to_meet_deadline") is not None
        ]
        deadline_goals.sort(
            key=lambda gp: (
                gp[0].deadline if gp[0].deadline else date.max,
                gp[0].priority,
            )
        )
        for g, p in deadline_goals:
            if remaining_budget <= 0:
                break
            needed = min(p["monthly_needed_to_meet_deadline"], p["remaining"])
            alloc = min(needed, remaining_budget)
            if alloc > 0:
                allocations[g.id] += alloc
                remaining_budget -= alloc

        # Phase 2 — distribute remainder by priority weight
        if remaining_budget > 0:
            remaining_goals = [g for g in goals if float(g.current_amount) < float(g.target_amount)]
            weights = [max(6 - g.priority, 1) for g in remaining_goals]  # p=1 → 5, p=5 → 1
            total_weight = sum(weights) or 1
            for g, w in zip(remaining_goals, weights):
                gap = float(g.target_amount) - float(g.current_amount) - allocations[g.id]
                if gap <= 0:
                    continue
                share = remaining_budget * (w / total_weight)
                alloc = min(share, gap)
                allocations[g.id] += alloc

        return [
            {
                "goal_id": g.id,
                "name": g.name,
                "amount": round(allocations[g.id], 2),
                "priority": g.priority,
            }
            for g in goals
            if allocations[g.id] > 0
        ]

    async def format_goals_overview(
        self, user_id: str, currency: str = "PHP"
    ) -> str:
        """Format goals list for Telegram."""
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        goals = await db.get_financial_goals(user_id, status="active")
        if not goals:
            return (
                "🎯 No active goals yet.\n\n"
                "Tell me what you're saving for — e.g., "
                "'I want to save ₱50,000 for an emergency fund by December'."
            )

        lines = ["🎯 *Your Goals*", ""]
        for i, g in enumerate(goals, start=1):
            pct = _pct_complete(g)
            proj = self.project_timeline(g)
            line1 = (
                f"{i}. *{g.name}* (priority: {_priority_label(g.priority)})"
            )
            line2 = (
                f"   {symbol}{float(g.current_amount):,.0f} / "
                f"{symbol}{float(g.target_amount):,.0f} ({pct:.0f}%)"
            )
            lines.extend([line1, line2])

            tail: str | None = None
            if g.monthly_contribution:
                tail_parts = [f"At {symbol}{float(g.monthly_contribution):,.0f}/mo"]
                if proj.get("projected_completion_date"):
                    tail_parts.append(
                        f"→ done by {proj['projected_completion_date'].strftime('%b %Y')}"
                    )
                if proj.get("on_track") is True:
                    tail_parts.append("✅ On track")
                elif proj.get("on_track") is False:
                    needed = proj.get("monthly_needed_to_meet_deadline") or 0
                    tail_parts.append(
                        f"⚠️ Need {symbol}{needed:,.0f}/mo to meet deadline"
                    )
                tail = "   📅 " + " ".join(tail_parts)
            elif g.deadline:
                needed = proj.get("monthly_needed_to_meet_deadline")
                if needed:
                    tail = (
                        f"   📅 Target {g.deadline.strftime('%b %Y')} → "
                        f"need {symbol}{needed:,.0f}/mo"
                    )

            if tail:
                lines.append(tail)
            lines.append("")

        return "\n".join(lines).rstrip()

    async def format_progress_celebration(
        self,
        goal: FinancialGoal,
        milestones: list[int],
        currency: str = "PHP",
    ) -> str | None:
        """Render a celebration if a milestone was hit, else None."""
        if not milestones:
            return None
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        highest = max(milestones)
        if highest == 100:
            return (
                f"🎉 *Goal complete: {goal.name}!*\n"
                f"You hit your target of {symbol}{float(goal.target_amount):,.0f}. "
                f"Brilliant work."
            )
        return (
            f"✨ *{highest}% to goal: {goal.name}*\n"
            f"{symbol}{float(goal.current_amount):,.0f} of "
            f"{symbol}{float(goal.target_amount):,.0f} — keep going."
        )


def _pct_complete(goal: FinancialGoal) -> float:
    target = float(goal.target_amount)
    if target <= 0:
        return 0.0
    return min((float(goal.current_amount) / target) * 100, 100.0)


def _priority_label(priority: int) -> str:
    if priority <= 1:
        return "high"
    if priority == 2:
        return "medium"
    return "low"


def _add_days(d: date, days: int) -> date:
    from datetime import timedelta
    return d + timedelta(days=days)


def _months_between(start: date, end: date) -> float:
    days = (end - start).days
    return days / 30.0
