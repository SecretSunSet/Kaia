"""Debt Coach skill — guided audit, payoff plan, progress, payments (D-1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from loguru import logger

from config.constants import CURRENCY_SYMBOLS
from database import queries as db
from database.models import Debt
from experts.hevn.skills import debt_math
from experts.hevn.skills.debt_math import DebtInput

# Typical PH monthly rates used (and labeled) when the user doesn't know.
RATE_DEFAULTS: dict[str, Decimal] = {
    "credit_card": Decimal("3.0"),
    "salary_loan": Decimal("1.25"),
    "personal_loan": Decimal("2.0"),
    "five_six": Decimal("20.0"),
    "pagibig_loan": Decimal("0.85"),
    "sss_loan": Decimal("0.83"),
    "auto_loan": Decimal("1.0"),
    "mortgage": Decimal("0.6"),
    "other": Decimal("2.0"),
}

MAX_MONTHLY_RATE = Decimal("25")  # sanity bound on quoted monthly %

UNSURE_MARKERS = ("not sure", "don't know", "dont know", "di ko alam", "idk", "no idea")
SKIP_MARKERS = ("skip", "none", "wala")
CANCEL_MARKERS = ("cancel", "stop", "never mind", "nevermind")


def to_debt_input(debt: Debt) -> DebtInput:
    """Convert a stored Debt into the simulator's input snapshot."""
    rate = debt_math.monthly_rate(debt.interest_rate, debt.rate_period)
    minimum = debt.minimum_payment or debt_math.default_minimum(debt.balance)
    return DebtInput(
        debt_id=debt.id,
        name=debt.name,
        balance=debt.balance,
        monthly_rate=rate,
        minimum_payment=minimum,
    )


@dataclass
class AuditSession:
    """In-memory cursor for one user's guided debt audit.

    Stages: collect -> more -> budget -> strategy. Each completed debt is
    persisted immediately, so losing this object never loses data.
    """

    stage: str = "collect"
    current: dict = field(default_factory=dict)
    captured: int = 0
    comparison: "debt_math.StrategyComparison | None" = None
    budget: Decimal | None = None


class DebtCoachSkill:
    """Professional debt payoff coaching backed by deterministic math."""

    def __init__(self) -> None:
        self._sessions: dict[str, AuditSession] = {}

    # ── Session plumbing ────────────────────────────────────────────

    def has_session(self, user_id: str) -> bool:
        return user_id in self._sessions

    def clear_session(self, user_id: str) -> None:
        self._sessions.pop(user_id, None)

    # ── Summaries / progress ────────────────────────────────────────

    async def debts_summary(self, user_id: str, currency: str = "PHP") -> str:
        """One-line-per-debt summary injected into Hevn's system prompt.

        Returns "" when the user has no active debts (caller substitutes
        the placeholder).
        """
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        debts = await db.get_debts(user_id, status="active")
        if not debts:
            return ""
        lines = []
        for d in debts:
            est = " (rate est.)" if d.rate_is_estimate else ""
            minimum = (
                f", min {symbol}{float(d.minimum_payment):,.0f}"
                if d.minimum_payment
                else ""
            )
            lines.append(
                f"- {d.name} [{d.debt_type}]: {symbol}{float(d.balance):,.0f} "
                f"at {float(d.interest_rate)}%/{d.rate_period[:2]}{est}{minimum}"
            )
        plan = await db.get_active_debt_plan(user_id)
        if plan:
            lines.append(
                f"Active payoff plan: {plan.strategy}, "
                f"{symbol}{float(plan.monthly_budget):,.0f}/mo, "
                f"baseline debt-free {plan.baseline_payoff_date.strftime('%b %Y')}"
            )
        return "\n".join(lines)

    async def format_progress(self, user_id: str, currency: str = "PHP") -> str:
        """Recompute the plan from current balances vs the baseline."""
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        debts = await db.get_debts(user_id, status="active")
        plan = await db.get_active_debt_plan(user_id)

        if not debts and plan:
            await db.update_debt_plan(plan.id, status="completed")
            return (
                "🎉 *You are DEBT-FREE!* Every debt on your plan is paid off. "
                "I'm genuinely proud of you. Next: let's redirect that monthly "
                "budget into your goals."
            )
        if not debts:
            return (
                "You have no debts on file. If you want to start a payoff "
                "plan, just say *help me get out of debt* and I'll run a "
                "quick debt audit with you."
            )
        if plan is None:
            total = sum(float(d.balance) for d in debts)
            return (
                f"You have {len(debts)} debt(s) totalling {symbol}{total:,.0f}, "
                "but no payoff plan yet. Say *help me get out of debt* and "
                "I'll build one with you."
            )

        result = debt_math.amortize(
            [to_debt_input(d) for d in debts],
            plan.monthly_budget,
            plan.strategy,
            date.today(),
        )
        lines = [f"📊 *Debt Plan Progress* ({plan.strategy})", ""]
        for d in debts:
            lines.append(f"• {d.name}: {symbol}{float(d.balance):,.0f}")
        lines.append("")
        if not result.ok:
            lines.append(
                "⚠️ At your current balances the plan no longer closes out — "
                "let's revisit your monthly budget. Say *help me get out of "
                "debt* to rebuild the plan."
            )
            return "\n".join(lines)

        projected = result.debt_free_date
        baseline = plan.baseline_payoff_date
        months_delta = (baseline.year - projected.year) * 12 + (
            baseline.month - projected.month
        )
        lines.append(
            f"Projected debt-free: *{projected.strftime('%b %Y')}* "
            f"(baseline {baseline.strftime('%b %Y')})"
        )
        if months_delta > 0:
            lines.append(f"✅ You're {months_delta} month(s) AHEAD of plan. 🎉")
        elif months_delta < 0:
            lines.append(
                f"⚠️ You're {-months_delta} month(s) behind plan — small "
                "catch-up payments fix this faster than you'd think."
            )
        else:
            lines.append("✅ Right on schedule.")
        lines.append(
            f"Remaining interest if you stay the course: "
            f"{symbol}{float(result.total_interest):,.0f}"
        )
        return "\n".join(lines)

    # ── Payments ────────────────────────────────────────────────────

    async def record_payment(
        self, ai, user, message: str, currency: str = "PHP"
    ) -> str | None:
        """Parse and apply a payment. Returns None when no match (caller
        falls through to other handling)."""
        from experts.hevn.parser import parse_debt_payment

        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        parsed = await parse_debt_payment(ai, message)
        if not parsed:
            return None
        debts = await db.get_debts(user.id, status="active")
        if not debts:
            return None

        name = (parsed.get("debt_name") or "").casefold()
        match: Debt | None = None
        if name:
            for d in debts:
                if name in d.name.casefold() or d.name.casefold() in name:
                    match = d
                    break
        elif len(debts) == 1:
            match = debts[0]
        if match is None:
            return None

        amount = Decimal(str(parsed["amount"]))
        if amount <= 0:
            return None
        new_balance = max(match.balance - amount, Decimal("0"))
        if new_balance == 0:
            await db.update_debt(match.id, balance=float(new_balance), status="paid_off")
        else:
            await db.update_debt(match.id, balance=float(new_balance))
        await db.create_debt_payment(
            debt_id=match.id,
            user_id=user.id,
            amount=float(amount),
            balance_after=float(new_balance),
            paid_on=date.today().isoformat(),
        )
        if new_balance == 0:
            return (
                f"🎉 *{match.name} is PAID OFF!* That {symbol}{float(amount):,.0f} "
                "closed it out completely. One debt down — your freed-up payment "
                "now hits the next debt on the plan even harder."
            )
        return (
            f"✅ Logged {symbol}{float(amount):,.0f} against *{match.name}* — "
            f"new balance {symbol}{float(new_balance):,.0f}. Ask me *how's my "
            f"debt progress* anytime."
        )

    # ── Guided audit state machine ──────────────────────────────────

    AUDIT_FIELDS = ("name", "balance", "interest_rate", "minimum_payment", "due_day")

    AUDIT_QUESTIONS = {
        "name": (
            "Who do you owe, and what kind of debt is it? "
            "(e.g. *BPI credit card*, *SSS salary loan*, *5-6*)"
        ),
        "balance": "How much is the current outstanding balance?",
        "interest_rate": (
            "What's the interest rate? (If you're not sure, say *not sure* "
            "and I'll use a typical rate for that type.)"
        ),
        "minimum_payment": (
            "What's the minimum monthly payment? (*not sure* is fine.)"
        ),
        "due_day": "What day of the month is it due? (1–31, or *skip*)",
    }

    def start_audit(self, user_id: str) -> str:
        """Open an audit session and return Hevn's intro + first question."""
        self._sessions[user_id] = AuditSession()
        return (
            "💪 Let's get you out of debt — for real, with a plan.\n\n"
            "First I need a quick *debt audit*: I'll ask about each debt "
            "one at a time (who you owe, balance, rate, minimum payment). "
            "Takes 2 minutes, zero judgment.\n\n"
            f"{self.AUDIT_QUESTIONS['name']}"
        )

    async def entry_point(self, ai, user, message: str, currency: str) -> str:
        """'Help me get out of debt' router: audit, budget, or progress."""
        debts = await db.get_debts(user.id, status="active")
        if not debts:
            return self.start_audit(user.id)
        plan = await db.get_active_debt_plan(user.id)
        if plan is None:
            session = AuditSession(stage="budget", captured=len(debts))
            self._sessions[user.id] = session
            symbol = CURRENCY_SYMBOLS.get(currency, currency)
            total = sum(float(d.balance) for d in debts)
            return (
                f"I already have {len(debts)} debt(s) on file totalling "
                f"{symbol}{total:,.0f}. One number and I'll build your plan: "
                "how much can you put toward debt each month, in total "
                "(minimums included)?"
            )
        return await self.format_progress(user.id, currency)

    async def continue_audit(self, ai, user, message: str, currency: str) -> str:
        """Advance the audit state machine by one user message."""
        session = self._sessions.get(user.id)
        if session is None:
            return await self.entry_point(ai, user, message, currency)

        low = message.lower().strip()
        if any(m in low for m in CANCEL_MARKERS):
            self.clear_session(user.id)
            return (
                "No problem — everything you've told me so far is saved. "
                "Say *help me get out of debt* anytime to resume."
            )

        if session.stage == "collect":
            return await self._audit_collect(ai, user, message, low, session, currency)
        if session.stage == "more":
            return await self._audit_more(ai, user, message, low, session, currency)
        if session.stage == "budget":
            return await self._audit_budget(ai, user, message, session, currency)
        if session.stage == "strategy":
            return await self._audit_strategy(user, low, session, currency)
        # Unknown stage — fail safe by closing the session.
        self.clear_session(user.id)
        return "Let's start over — say *help me get out of debt*."

    def _next_missing(self, current: dict) -> str | None:
        for fld in self.AUDIT_FIELDS:
            if fld not in current:
                return fld
        return None

    async def _audit_collect(
        self, ai, user, message: str, low: str, session: AuditSession, currency: str
    ) -> str:
        from experts.hevn.parser import parse_debt_mention

        pending = self._next_missing(session.current)

        if any(m in low for m in UNSURE_MARKERS) and pending in (
            "interest_rate", "minimum_payment"
        ):
            if pending == "interest_rate":
                debt_type = session.current.get("debt_type") or "other"
                session.current["interest_rate"] = RATE_DEFAULTS.get(
                    debt_type, RATE_DEFAULTS["other"]
                )
                session.current["rate_period"] = "monthly"
                session.current["rate_is_estimate"] = True
            else:
                session.current["minimum_payment"] = None
        elif any(m in low for m in SKIP_MARKERS) and pending == "due_day":
            session.current["due_day"] = None
        else:
            parsed = await parse_debt_mention(ai, message)
            if parsed:
                for key, value in parsed.items():
                    if value is not None and key not in session.current:
                        session.current[key] = value
            elif pending is not None:
                return (
                    "I didn't catch that — "
                    f"{self.AUDIT_QUESTIONS[pending]}"
                )

        # Sanity: cap absurd monthly rates rather than store garbage.
        rate = session.current.get("interest_rate")
        if rate is not None and Decimal(str(rate)) > MAX_MONTHLY_RATE:
            del session.current["interest_rate"]
            return (
                f"That rate looks unusually high (above {MAX_MONTHLY_RATE}%/mo). "
                "Can you double-check it? Quote it exactly as the lender states it."
            )

        nxt = self._next_missing(session.current)
        if nxt is not None:
            return self.AUDIT_QUESTIONS[nxt]
        return await self._audit_save_current(user, session, currency)

    async def _audit_save_current(
        self, user, session: AuditSession, currency: str
    ) -> str:
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        cur = session.current
        debt = await db.create_debt(
            user_id=user.id,
            name=str(cur["name"]),
            balance=float(cur["balance"]),
            interest_rate=float(cur["interest_rate"]),
            debt_type=str(cur.get("debt_type") or "other"),
            rate_period=str(cur.get("rate_period") or "monthly"),
            rate_is_estimate=bool(cur.get("rate_is_estimate", False)),
            minimum_payment=(
                float(cur["minimum_payment"])
                if cur.get("minimum_payment") is not None
                else None
            ),
            due_day=cur.get("due_day"),
        )
        session.captured += 1
        session.current = {}
        session.stage = "more"
        est = " (estimated rate)" if debt.rate_is_estimate else ""
        return (
            f"✅ Got it: *{debt.name}* — {symbol}{float(debt.balance):,.0f} at "
            f"{float(debt.interest_rate)}%/{debt.rate_period[:2]}{est}.\n\n"
            "Any other debts? (yes / no)"
        )

    async def _audit_more(
        self, ai, user, message: str, low: str, session: AuditSession, currency: str
    ) -> str:
        from experts.hevn.parser import parse_debt_mention

        if low.startswith("no") or "that's all" in low or "thats all" in low or "wala na" in low:
            session.stage = "budget"
            return (
                f"That's {session.captured} debt(s) on file. Now the key "
                "number: how much can you put toward debt each month, in "
                "TOTAL (minimum payments included)?"
            )
        session.stage = "collect"
        # The "yes" may already carry details ("yes, a Home Credit loan, 30k").
        parsed = None
        if len(low) > 8 or not low.startswith("yes"):
            parsed = await parse_debt_mention(ai, message)
        if parsed:
            session.current = {k: v for k, v in parsed.items() if v is not None}
        nxt = self._next_missing(session.current)
        if nxt is not None:
            return self.AUDIT_QUESTIONS[nxt]
        return await self._audit_save_current(user, session, currency)

    async def _audit_budget(
        self, ai, user, message: str, session: AuditSession, currency: str
    ) -> str:
        from experts.hevn.parser import parse_amount

        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        amount = await parse_amount(ai, message)
        if amount is None or amount <= 0:
            return (
                "Give me one number — how many pesos per month can go to "
                "debt in total? (e.g. *10,000*)"
            )
        budget = Decimal(str(amount))
        debts = await db.get_debts(user.id, status="active")
        inputs = [to_debt_input(d) for d in debts]
        comp = debt_math.compare_strategies(inputs, budget, date.today())

        if not comp.avalanche.ok and comp.avalanche.error == "shortfall":
            self.clear_session(user.id)
            short = comp.avalanche.shortfall or Decimal("0")
            minimums = budget + short
            return (
                f"⚠️ Real talk: your minimum payments alone are "
                f"{symbol}{float(minimums):,.0f}/mo — "
                f"{symbol}{float(budget):,.0f} won't cover them "
                f"(short {symbol}{float(short):,.0f}).\n\n"
                "This is fixable. Your options:\n"
                "1. *Balance transfer* — move card debt to a lower-rate card\n"
                "2. *Consolidation loan* — one lower-rate loan pays off the rest\n"
                "3. *Restructure* — call your bank; they'd rather restructure "
                "than have you default\n"
                "4. *Pag-IBIG MPL / SSS salary loan* — much cheaper money "
                "if you qualify\n\n"
                "Want to talk through any of these? Or if you can free up "
                "more per month, say *help me get out of debt* and we'll "
                "rebuild the plan."
            )
        if not comp.avalanche.ok and comp.avalanche.error == "non_amortizing":
            self.clear_session(user.id)
            names = ", ".join(comp.avalanche.problem_debts)
            return (
                f"⚠️ At that budget, *{names}* never pays off — the payment "
                "doesn't even cover its monthly interest. That debt needs "
                "either a bigger payment or a restructure/consolidation. "
                "Let's free up more budget or talk restructuring options."
            )

        session.budget = budget
        session.comparison = comp
        session.stage = "strategy"
        strategy, reason = debt_math.recommend_strategy(comp)
        av, sn = comp.avalanche, comp.snowball
        first_sn = sn.payoffs[0] if sn.payoffs else None
        lines = [
            f"💪 With {symbol}{float(budget):,.0f}/mo, two ways to attack this:",
            "",
            "🏔️ *Avalanche* (highest rate first)",
            f"   Debt-free: *{av.debt_free_date.strftime('%b %Y')}* — total "
            f"interest {symbol}{float(av.total_interest):,.0f}",
            "",
            "⛄ *Snowball* (smallest balance first)",
            f"   Debt-free: *{sn.debt_free_date.strftime('%b %Y')}* — total "
            f"interest {symbol}{float(sn.total_interest):,.0f}",
        ]
        if comp.interest_saved_by_avalanche > 0:
            lines.append(
                f"   (costs {symbol}{float(comp.interest_saved_by_avalanche):,.0f} "
                "more than avalanche)"
            )
        if first_sn:
            lines.append(
                f"   First debt cleared in {first_sn.payoff_month} month(s) — "
                "quick win."
            )
        lines.extend([
            "",
            f"🎯 My recommendation: *{strategy}*. {reason}",
            "",
            "Which one do you want — *avalanche* or *snowball*?",
        ])
        return "\n".join(lines)

    async def _audit_strategy(
        self, user, low: str, session: AuditSession, currency: str
    ) -> str:
        symbol = CURRENCY_SYMBOLS.get(currency, currency)
        if "avalanche" in low:
            strategy = "avalanche"
        elif "snowball" in low:
            strategy = "snowball"
        else:
            return "Just say the word: *avalanche* or *snowball*?"

        comp = session.comparison
        chosen = comp.avalanche if strategy == "avalanche" else comp.snowball
        await db.create_debt_plan(
            user_id=user.id,
            strategy=strategy,
            monthly_budget=float(session.budget),
            baseline_payoff_date=chosen.debt_free_date.isoformat(),
            baseline_total_interest=float(chosen.total_interest),
        )
        self.clear_session(user.id)
        return (
            f"🎯 *Your {strategy} plan is live.*\n\n"
            f"• {symbol}{float(session.budget):,.0f}/mo toward debt\n"
            f"• Debt-free date: *{chosen.debt_free_date.strftime('%B %Y')}*\n"
            f"• Total interest on plan: {symbol}{float(chosen.total_interest):,.0f}\n\n"
            "I'll nudge you before due dates and review progress monthly. "
            "When you make a payment, just tell me — *paid 5k on my BPI card* "
            "— and I'll track it. Let's go. 💪"
        )
