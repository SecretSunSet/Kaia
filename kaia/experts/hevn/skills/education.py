"""Progressive financial education adapted to user's knowledge level."""

from __future__ import annotations

from database import queries as db


class EducationSkill:
    """Topic catalog + progressive teaching with knowledge tracking."""

    TOPIC_CATALOG: dict[str, list[str]] = {
        "basics": ["budgeting", "emergency_fund", "credit_score", "debt_types"],
        "saving": ["high_yield_savings", "time_deposits", "money_market", "MP2"],
        "investing": [
            "stocks_basics", "mutual_funds", "uitf", "etf", "bonds",
            "REITs", "crypto_basics", "index_funds",
        ],
        "ph_specific": [
            "SSS_contributions", "pagibig_MP2", "philhealth_benefits",
            "BIR_taxes", "TRAIN_law", "personal_equity_plan",
        ],
        "insurance": [
            "health_insurance", "life_insurance", "hmo_vs_health",
            "vul_explained", "term_vs_whole_life",
        ],
        "advanced": [
            "portfolio_theory", "asset_allocation", "tax_optimization",
            "estate_planning", "fire_movement",
        ],
    }

    # Learning progression: if user hasn't covered X, suggest Y next.
    _PROGRESSION: dict[str, list[str]] = {
        "budgeting": ["emergency_fund", "debt_types"],
        "emergency_fund": ["high_yield_savings", "time_deposits"],
        "high_yield_savings": ["MP2", "time_deposits"],
        "MP2": ["uitf", "mutual_funds"],
        "mutual_funds": ["uitf", "etf"],
        "uitf": ["stocks_basics", "index_funds"],
        "stocks_basics": ["REITs", "index_funds"],
        "index_funds": ["asset_allocation", "bonds"],
        "SSS_contributions": ["pagibig_MP2", "philhealth_benefits"],
        "BIR_taxes": ["TRAIN_law", "personal_equity_plan"],
    }

    async def get_user_level(self, user_id: str) -> dict:
        """Assess user's knowledge level from channel_profile entries."""
        entries = await db.get_channel_profile(user_id, "hevn")
        known: list[str] = []
        for e in entries:
            if e.category == "financial_knowledge":
                known.append(e.key)

        if not known:
            level = "beginner"
        elif len(known) < 5:
            level = "beginner"
        elif len(known) < 12:
            level = "intermediate"
        else:
            level = "advanced"

        suggested = self._next_topics(known)
        return {
            "level": level,
            "topics_covered": known,
            "suggested_next": suggested,
        }

    def _next_topics(self, known: list[str]) -> list[str]:
        """Suggest up to 3 topics progressively based on what's known."""
        suggestions: list[str] = []
        known_set = set(known)
        for k in known:
            for nxt in self._PROGRESSION.get(k, []):
                if nxt not in known_set and nxt not in suggestions:
                    suggestions.append(nxt)
                if len(suggestions) >= 3:
                    return suggestions
        # Fallback — start from budgeting basics
        if not suggestions:
            for fallback in ("budgeting", "emergency_fund", "MP2"):
                if fallback not in known_set:
                    suggestions.append(fallback)
        return suggestions[:3]

    async def explain_topic(
        self,
        ai_engine,
        user_id: str,
        topic: str,
        user_profile_text: str,
    ) -> str:
        """Ask the AI to explain a topic tailored to user's level, then mark it learned."""
        level_info = await self.get_user_level(user_id)
        level = level_info["level"]

        system = (
            "You are Hevn, a Philippine financial advisor teaching a user. "
            f"The user's level is: {level}. Explain the topic clearly at that level. "
            "Prefer concrete PH-specific examples. Use ₱. "
            "Keep to 6-10 short lines. End with one suggestion for what to learn next."
        )
        user_msg = (
            f"TOPIC: {topic}\n\nUSER PROFILE:\n{user_profile_text}\n\n"
            f"Topics already covered: {', '.join(level_info['topics_covered']) or '(none)'}"
        )
        response = await ai_engine.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=500,
        )

        # Mark topic as learned
        try:
            await db.upsert_channel_profile(
                user_id=user_id,
                channel_id="hevn",
                category="financial_knowledge",
                key=_normalize_topic(topic),
                value=f"explained on {level} level",
                confidence=0.9,
                source="inferred",
            )
        except Exception:
            pass

        return response.text

    async def suggest_next_topic(self, user_id: str) -> dict:
        """Return the next recommended topic with rationale."""
        info = await self.get_user_level(user_id)
        suggested = info["suggested_next"]
        if not suggested:
            return {"topic": None, "reason": "You're across the basics — ask me about any specific area."}
        return {
            "topic": suggested[0],
            "options": suggested,
            "reason": f"Based on your {info['level']} level, this is a natural next step.",
        }

    async def quiz_user(
        self, ai_engine, topic: str, user_profile_text: str
    ) -> str:
        """Generate a short quiz question on a topic."""
        system = (
            "You are Hevn. Create ONE short, practical quiz question about the "
            "topic to check the user's understanding. Include 3 multiple-choice "
            "options (a/b/c). Do not reveal the answer yet."
        )
        user_msg = f"TOPIC: {topic}\n\nUSER PROFILE:\n{user_profile_text}"
        response = await ai_engine.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=250,
        )
        return response.text


def _normalize_topic(topic: str) -> str:
    return topic.lower().strip().replace(" ", "_").replace("-", "_")
