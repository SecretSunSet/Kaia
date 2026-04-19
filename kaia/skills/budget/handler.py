"""Budget skill handler — transaction logging, summaries, and budget limits."""

from __future__ import annotations

import re
from datetime import date

from loguru import logger

from config.constants import (
    BUDGET_WARNING_THRESHOLD,
    CURRENCY_SYMBOLS,
    SKILL_BUDGET,
)
from core.ai_engine import AIEngine
from database import queries as db
from database.models import User
from skills.base import BaseSkill, SkillResult
from skills.budget.parser import parse_transaction, parse_budget_limit
from skills.budget.prompts import (
    format_transaction_confirmation,
    format_budget_warning,
)
from skills.budget.reports import (
    format_budget_limits_message,
    format_comparison_message,
    format_summary_message,
    get_monthly_comparison,
    get_period_summary,
    resolve_period,
)


class BudgetSkill(BaseSkill):
    """Handles budget tracking: logging transactions, summaries, and limits."""

    name = SKILL_BUDGET

    def __init__(self, ai_engine: AIEngine) -> None:
        super().__init__(ai_engine)

    async def handle(
        self,
        user: User,
        message: str,
        conversation_history: list[dict[str, str]],
        profile_context: str,
    ) -> SkillResult:
        msg = message.lower().strip()

        # Route to sub-handlers
        if _is_undo_request(msg):
            return await self._handle_undo(user)
        if _is_budget_limit_list_request(msg):
            return await self._handle_list_limits(user)
        if _is_budget_limit_delete_request(msg):
            return await self._handle_delete_limit(user, message)
        if _is_budget_limit_request(msg):
            return await self._handle_set_limit(user, message)
        if _is_comparison_request(msg):
            return await self._handle_comparison(user)
        if _is_summary_request(msg):
            return await self._handle_summary(user, message)

        # Default: try to parse as a transaction
        return await self._handle_log_transaction(user, message)

    # ── Log transaction ──────────────────────────────────────────────

    async def _handle_log_transaction(
        self, user: User, message: str
    ) -> SkillResult:
        currency = user.currency or "PHP"
        parsed = await parse_transaction(self.ai, message, currency)

        if parsed is None:
            return SkillResult(
                text="I couldn't parse that as a transaction. Try something like 'Spent 500 on lunch' or 'Received 30,000 salary'.",
                skill_name=self.name,
            )

        symbol = CURRENCY_SYMBOLS.get(currency, currency)

        # Save to DB
        txn = await db.create_transaction(
            user_id=user.id,
            amount=parsed["amount"],
            type=parsed["type"],
            category=parsed["category"],
            description=parsed.get("description"),
            transaction_date=parsed.get("date"),
        )
        logger.info(
            "Transaction logged: {} {} {} ({})",
            parsed["type"],
            parsed["amount"],
            parsed["category"],
            user.telegram_id,
        )

        # Build confirmation
        text = format_transaction_confirmation(
            amount=parsed["amount"],
            type=parsed["type"],
            category=parsed["category"],
            description=parsed.get("description"),
            currency_symbol=symbol,
        )

        # Check budget limit for this category
        if parsed["type"] == "expense":
            warning = await self._check_budget_warning(
                user.id, parsed["category"], symbol
            )
            if warning:
                text += warning

        # Proactive salary allocation suggestion (if Hevn has been met)
        if parsed["type"] == "income" and parsed["category"] == "salary":
            try:
                suggestion = await self._hevn_salary_allocation(
                    user, float(parsed["amount"])
                )
                if suggestion:
                    text += f"\n\n{suggestion}"
            except Exception as exc:
                logger.debug("Hevn salary allocation skipped: {}", exc)

        return SkillResult(text=text, skill_name=self.name)

    async def _hevn_salary_allocation(
        self, user: User, amount: float
    ) -> str | None:
        """Ask Hevn for a salary allocation suggestion — only if user has met her."""
        convos = await db.count_channel_conversations(user.id, "hevn")
        if convos == 0:
            return None
        from experts.hevn.skills.proactive import ProactiveAlertsSkill
        skill = ProactiveAlertsSkill()
        return await skill.handle_salary_received(
            user.id, amount, user.currency or "PHP"
        )

    async def _check_budget_warning(
        self, user_id: str, category: str, currency_symbol: str
    ) -> str | None:
        """Check if spending in a category is near or over its budget limit."""
        limit = await db.get_budget_limit(user_id, category)
        if limit is None:
            return None

        today = date.today()
        start_of_month = today.replace(day=1).isoformat()
        spent = await db.get_category_total(
            user_id, category, start_of_month, today.isoformat()
        )
        monthly_limit = float(limit.monthly_limit)

        if spent >= monthly_limit or spent >= monthly_limit * BUDGET_WARNING_THRESHOLD:
            return format_budget_warning(
                category, spent, monthly_limit, currency_symbol
            )
        return None

    # ── Summary ──────────────────────────────────────────────────────

    async def _handle_summary(self, user: User, message: str) -> SkillResult:
        start_date, end_date, label = resolve_period(message)
        currency = user.currency or "PHP"
        symbol = CURRENCY_SYMBOLS.get(currency, currency)

        data = await get_period_summary(user.id, start_date, end_date)
        limits = await db.get_budget_limits(user.id)

        text = format_summary_message(data, symbol, label, limits)
        return SkillResult(text=text, skill_name=self.name)

    # ── Comparison ───────────────────────────────────────────────────

    async def _handle_comparison(self, user: User) -> SkillResult:
        currency = user.currency or "PHP"
        symbol = CURRENCY_SYMBOLS.get(currency, currency)

        data = await get_monthly_comparison(user.id)
        text = format_comparison_message(data, symbol)
        return SkillResult(text=text, skill_name=self.name)

    # ── Set budget limit ─────────────────────────────────────────────

    async def _handle_set_limit(self, user: User, message: str) -> SkillResult:
        currency = user.currency or "PHP"
        symbol = CURRENCY_SYMBOLS.get(currency, currency)

        parsed = await parse_budget_limit(self.ai, message, currency)
        if parsed is None:
            return SkillResult(
                text="I couldn't parse that budget limit. Try: 'Set food budget to 5,000 per month'",
                skill_name=self.name,
            )

        await db.create_or_update_budget_limit(
            user_id=user.id,
            category=parsed["category"],
            monthly_limit=parsed["amount"],
        )

        return SkillResult(
            text=f"✅ Budget set: {parsed['category'].title()} — {symbol}{parsed['amount']:,.2f}/month",
            skill_name=self.name,
        )

    # ── List budget limits ───────────────────────────────────────────

    async def _handle_list_limits(self, user: User) -> SkillResult:
        currency = user.currency or "PHP"
        symbol = CURRENCY_SYMBOLS.get(currency, currency)

        limits = await db.get_budget_limits(user.id)

        # Get current month spending per category
        today = date.today()
        start_of_month = today.replace(day=1).isoformat()
        end = today.isoformat()

        category_spending: dict[str, float] = {}
        for bl in limits:
            spent = await db.get_category_total(
                user.id, bl.category, start_of_month, end
            )
            category_spending[bl.category] = spent

        text = format_budget_limits_message(limits, category_spending, symbol)
        return SkillResult(text=text, skill_name=self.name)

    # ── Delete budget limit ──────────────────────────────────────────

    async def _handle_delete_limit(self, user: User, message: str) -> SkillResult:
        # Try to find a category name in the message
        limits = await db.get_budget_limits(user.id)
        if not limits:
            return SkillResult(
                text="You don't have any budget limits to remove.",
                skill_name=self.name,
            )

        msg = message.lower()
        matched = None
        for bl in limits:
            if bl.category in msg:
                matched = bl
                break

        if matched is None:
            cats = ", ".join(bl.category for bl in limits)
            return SkillResult(
                text=f"Which budget limit do you want to remove? Your active limits: {cats}",
                skill_name=self.name,
            )

        await db.deactivate_budget_limit(user.id, matched.category)
        return SkillResult(
            text=f"✅ Removed budget limit for {matched.category.title()}.",
            skill_name=self.name,
        )

    # ── Undo last transaction ────────────────────────────────────────

    async def _handle_undo(self, user: User) -> SkillResult:
        txn = await db.get_last_transaction(user.id)
        if txn is None:
            return SkillResult(
                text="No recent transaction to undo.",
                skill_name=self.name,
            )

        currency = user.currency or "PHP"
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        desc = f" ({txn.description})" if txn.description else ""

        await db.delete_transaction(txn.id)
        return SkillResult(
            text=f"↩️ Deleted last transaction: {symbol}{float(txn.amount):,.2f} {txn.type} — {txn.category.title()}{desc}",
            skill_name=self.name,
        )


# ── Sub-intent detection helpers ─────────────────────────────────────

def _is_summary_request(msg: str) -> bool:
    patterns = [
        "summary", "how much", "spending", "expenses", "show me",
        "my finances", "budget report", "what did i spend",
        "what have i spent", "breakdown",
    ]
    return any(p in msg for p in patterns)


def _is_comparison_request(msg: str) -> bool:
    patterns = ["compare", "comparison", "vs last month", "month over month", "compared to"]
    return any(p in msg for p in patterns)


def _is_budget_limit_request(msg: str) -> bool:
    patterns = [
        "set budget", "set my budget", "budget to", "budget is",
        "limit to", "my budget for", "monthly budget",
    ]
    return any(p in msg for p in patterns)


def _is_budget_limit_list_request(msg: str) -> bool:
    patterns = [
        "my budgets", "budget limits", "what are my budget",
        "show budget", "list budget", "show my budget",
        "what budgets",
    ]
    return any(p in msg for p in patterns)


def _is_budget_limit_delete_request(msg: str) -> bool:
    patterns = [
        "remove budget", "delete budget", "remove my budget",
        "delete my budget", "cancel budget", "remove limit",
        "delete limit",
    ]
    return any(p in msg for p in patterns)


def _is_undo_request(msg: str) -> bool:
    patterns = ["undo", "delete last", "remove last", "undo last", "cancel last"]
    return any(p in msg for p in patterns)
