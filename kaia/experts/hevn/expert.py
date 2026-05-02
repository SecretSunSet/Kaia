"""Hevn — the Financial Advisor expert."""

from __future__ import annotations

import asyncio

from loguru import logger

from config.constants import CURRENCY_SYMBOLS
from core.ai_engine import AIEngine, build_message_history
from database import queries as db
from database.models import Channel, User
from experts.base import BaseExpert
from experts.hevn.extractor import hevn_extract_and_save
from experts.hevn.parser import (
    classify_hevn_intent,
    parse_bill_creation,
    parse_goal_creation,
)
from experts.hevn.prompts import build_hevn_system_prompt
from experts.hevn.skills.bills_tracker import BillsTrackerSkill
from experts.hevn.skills.budget_coaching import BudgetCoachingSkill
from experts.hevn.skills.education import EducationSkill
from experts.hevn.skills.goals_manager import GoalsManagerSkill
from experts.hevn.skills.health_assessment import FinancialHealthSkill
from experts.hevn.skills.market_trends import MarketTrendsSkill
from experts.hevn.skills.proactive import ProactiveAlertsSkill
from skills.base import SkillResult


class HevnExpert(BaseExpert):
    """Hevn — Financial Advisor. Routes to 7 specialized skills."""

    channel_id = "hevn"

    def __init__(self, ai_engine: AIEngine) -> None:
        super().__init__(ai_engine)
        self.health = FinancialHealthSkill()
        self.coaching = BudgetCoachingSkill()
        self.goals = GoalsManagerSkill()
        self.bills = BillsTrackerSkill()
        self.market = MarketTrendsSkill()
        self.education = EducationSkill()
        self.proactive = ProactiveAlertsSkill()

    # ── Main entry ──────────────────────────────────────────────────

    async def handle(
        self,
        user: User,
        message: str,
        channel: Channel,
    ) -> SkillResult:
        """Route the message through Hevn's pipeline."""
        currency = user.currency or "PHP"

        # First-visit onboarding
        if await self._channel_mgr.is_first_visit(user.id, channel.channel_id):
            combined_context = await self._channel_mem.load_combined_context(
                user.id, channel.channel_id
            )
            onboarding = await self.generate_onboarding(user, channel, combined_context)
            footer = self.format_response_footer(channel)
            await self.save_messages(
                user.id, channel.channel_id, message, onboarding
            )
            # Register the weekly digest now that the user has met Hevn.
            try:
                from core.scheduler import schedule_hevn_weekly_digest
                await schedule_hevn_weekly_digest(
                    user_id=user.id,
                    telegram_id=user.telegram_id,
                    timezone=user.timezone or "Asia/Manila",
                )
            except Exception as exc:
                logger.warning("Failed to schedule Hevn digest: {}", exc)
            return SkillResult(
                text=f"{onboarding}{footer}",
                skill_name=channel.channel_id,
            )

        # Detect sub-intent
        intent = await classify_hevn_intent(self.ai, message)
        logger.debug("Hevn intent: {} (user={})", intent, user.id)

        # Route to specialized skill when we can answer deterministically
        specialized_text: str | None = None
        if intent == "health_assessment":
            specialized_text = await self._run_health(user.id, currency)
        elif intent == "goals":
            specialized_text = await self._run_goals(user, message, currency)
        elif intent == "bills":
            specialized_text = await self._run_bills(user, message, currency)
        elif intent == "budget_coaching":
            specialized_text = await self._run_coaching(user.id, currency)

        if specialized_text is not None:
            footer = self.format_response_footer(channel)
            full_text = f"{specialized_text}{footer}"
            await self.save_messages(user.id, channel.channel_id, message, specialized_text)
            self._fire_extraction(user.id, channel.channel_id, message, specialized_text)
            return SkillResult(text=full_text, skill_name=channel.channel_id)

        # Persona-driven response for market_trends, education, general_chat
        ai_response = await self._persona_response(
            user=user,
            message=message,
            channel=channel,
            intent=intent,
        )
        footer = self.format_response_footer(channel)
        full_text = f"{ai_response.text}{footer}"
        await self.save_messages(
            user.id, channel.channel_id, message, ai_response.text
        )
        self._fire_extraction(user.id, channel.channel_id, message, ai_response.text)
        return SkillResult(
            text=full_text,
            skill_name=channel.channel_id,
            ai_response=ai_response,
        )

    # ── Specialized routes ──────────────────────────────────────────

    async def _run_health(self, user_id: str, currency: str) -> str:
        assessment = await self.health.assess(user_id, currency)
        return self.health.format_health_report(assessment, currency)

    async def _run_goals(self, user: User, message: str, currency: str) -> str:
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        low = message.lower()
        create_markers = (
            "save", "goal", "set a goal", "set this as", "set that as",
            "let's set", "emergency fund", "start saving", "create a goal",
            "make this my goal", "new goal",
        )
        view_markers = ("show", "list", "my goals", "progress", "how am i doing on")

        wants_create = any(m in low for m in create_markers)
        has_explicit_numbers = any(ch.isdigit() for ch in message)
        references_prior = any(
            ref in low for ref in ("this goal", "that goal", "set this as", "set that as", "let's set", "first goal")
        )

        if wants_create and (has_explicit_numbers or references_prior):
            parse_input = message
            # Pull in recent Hevn conversation so references like "set this as
            # our first goal" can be resolved from what Hevn just suggested.
            if references_prior or not has_explicit_numbers:
                recent = await db.get_channel_conversations(
                    user.id, "hevn", limit=6
                )
                if recent:
                    context_block = "\n".join(
                        f"{m.role}: {m.content}" for m in recent
                    )
                    parse_input = (
                        f"Recent conversation (resolve references like "
                        f"'this goal' / 'that goal' from here):\n"
                        f"{context_block}\n\nCurrent message: {message}"
                    )

            parsed = await parse_goal_creation(self.ai, parse_input)
            if parsed:
                goal = await self.goals.create_goal(
                    user_id=user.id,
                    name=parsed["name"],
                    target=parsed["target"],
                    deadline=parsed["deadline"],
                    monthly=parsed["monthly"],
                    priority=parsed["priority"],
                )
                deadline_str = (
                    f" by {goal.deadline.strftime('%b %Y')}" if goal.deadline else ""
                )
                monthly_str = (
                    f" with {symbol}{float(goal.monthly_contribution):,.0f}/mo" if goal.monthly_contribution else ""
                )
                return (
                    f"🎯 Goal created: *{goal.name}* — target "
                    f"{symbol}{float(goal.target_amount):,.0f}{deadline_str}{monthly_str}.\n\n"
                    f"I'll track progress for you."
                )
            if references_prior:
                return (
                    "Happy to lock that in — can you remind me of the target "
                    "amount and roughly when you want to hit it?"
                )

        if any(m in low for m in view_markers) or "my goals" in low:
            return await self.goals.format_goals_overview(user.id, currency)

        # Fall back to overview
        return await self.goals.format_goals_overview(user.id, currency)

    async def _run_bills(self, user: User, message: str, currency: str) -> str:
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        low = message.lower()

        if any(kw in low for kw in ("upcoming", "due this week", "next 7 days")):
            upcoming = await self.bills.get_upcoming(user.id, days=7)
            return self.bills.format_upcoming(upcoming, currency)

        if any(kw in low for kw in ("remind me", "add bill", "track", "add subscription")):
            parsed = await parse_bill_creation(self.ai, message)
            if parsed:
                bill = await self.bills.add_bill(
                    user_id=user.id,
                    name=parsed["name"],
                    amount=parsed["amount"],
                    due_day=parsed["due_day"],
                    category=parsed["category"],
                    recurrence=parsed["recurrence"],
                )
                due_text = (
                    f" on day {bill.due_day} of each month" if bill.due_day else ""
                )
                return (
                    f"🧾 Bill added: *{bill.name}* — "
                    f"{symbol}{float(bill.amount):,.0f}{due_text}."
                )

        bills = await self.bills.list_bills(user.id)
        return self.bills.format_bills_list(bills, currency)

    async def _run_coaching(self, user_id: str, currency: str) -> str:
        waste = await self.coaching.identify_waste(user_id)
        patterns = await self.coaching.analyze_patterns(user_id, period_days=30)
        parts = [
            self.coaching.format_patterns_report(patterns, currency),
            "",
            self.coaching.format_waste_report(waste, currency),
        ]
        return "\n".join(parts)

    # ── Persona response for open-ended intents ─────────────────────

    async def _persona_response(
        self,
        user: User,
        message: str,
        channel: Channel,
        intent: str,
    ):
        """Build a Hevn-voiced AI response with full context."""
        history = await self.get_conversation_history(
            user.id, channel.channel_id, user_timezone=user.timezone
        )
        user_context = await self._channel_mem.load_combined_context(
            user.id, channel.channel_id
        )
        budget_summary = await self._budget_summary(
            user.id, user.currency or "PHP", user_timezone=user.timezone
        )
        goals_summary = await self.goals.format_goals_overview(
            user.id, user.currency or "PHP"
        )

        channel_entries = await db.get_channel_profile(user.id, channel.channel_id)
        top_gap = self._channel_mem.get_top_gap(channel.channel_id, channel_entries)
        current_gap = (
            top_gap["key"].replace("_", " ") if top_gap else ""
        )

        system_prompt = build_hevn_system_prompt(
            user_context=user_context,
            budget_summary=budget_summary,
            goals_summary=goals_summary,
            current_gap=current_gap,
        )

        # If education intent, attach user's level so Hevn adapts
        if intent == "education":
            level = await self.education.get_user_level(user.id)
            system_prompt += (
                f"\n\nEDUCATION CONTEXT: user's level is {level['level']}. "
                f"Topics already covered: {', '.join(level['topics_covered']) or '(none)'}."
            )

        if intent == "market_trends":
            system_prompt += (
                "\n\nMARKET CONTEXT: when the user asks about rates, markets, or "
                "economic events, explain how it affects THEIR specific finances."
            )

        messages = build_message_history(history, message)
        return await self.ai.chat(system_prompt=system_prompt, messages=messages)

    async def _budget_summary(
        self, user_id: str, currency: str, user_timezone: str | None = None
    ) -> str:
        from utils.time_utils import format_transaction_with_time, today_in_tz
        from config.settings import get_settings

        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        tz = user_timezone or get_settings().default_timezone
        today = today_in_tz(tz)
        month_start = today.replace(day=1)

        income = await db.get_income_total(
            user_id, month_start.isoformat(), today.isoformat()
        )
        expenses = await db.get_expense_total(
            user_id, month_start.isoformat(), today.isoformat()
        )
        categories = await db.get_spending_by_category(
            user_id, month_start.isoformat(), today.isoformat()
        )
        if income == 0 and expenses == 0:
            return "(no transactions logged this month)"

        top = categories[:3]
        top_str = ", ".join(
            f"{c['category']}: {symbol}{c['total']:,.0f}" for c in top
        )

        # Pull the 5 most recent transactions so Hevn can reason about *when*
        recent_txs = await db.get_transactions(
            user_id, month_start.isoformat(), today.isoformat()
        )
        recent_lines = ""
        if recent_txs:
            tail = sorted(
                recent_txs,
                key=lambda t: t.created_at or t.transaction_date,
                reverse=True,
            )[:5]
            recent_lines = "\nRecent transactions:\n" + "\n".join(
                f"  • {format_transaction_with_time(t, tz, currency_symbol=symbol)}"
                for t in tail
            )

        return (
            f"Month-to-date: income {symbol}{income:,.0f}, "
            f"expenses {symbol}{expenses:,.0f}. "
            f"Top: {top_str or '(none)'}.{recent_lines}"
        )

    # ── Extraction hook (Hevn-specific mirror) ──────────────────────

    def _fire_extraction(
        self,
        user_id: str,
        channel_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Fire-and-forget Hevn's extractor (includes shared profile mirror)."""
        messages = [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]

        async def _run() -> None:
            try:
                saved = await hevn_extract_and_save(
                    ai_engine=self.ai,
                    user_id=user_id,
                    conversation_messages=messages,
                )
                if saved:
                    logger.info("Hevn extraction: {} facts saved", saved)
            except Exception as exc:
                logger.warning("Hevn extraction error: {}", exc)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_run())
        except RuntimeError:
            logger.warning("No running event loop for Hevn extraction")
