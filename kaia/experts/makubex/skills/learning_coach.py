"""Learning coach — track skill progression and suggest next topics."""

from __future__ import annotations

from loguru import logger

from core.ai_engine import AIEngine
from database import queries as db


_DEPTH_PROGRESSION = ["intro", "solid", "deep"]


class LearningCoachSkill:
    """Track the user's tech skill progression and suggest next topics."""

    SKILL_TREES: dict[str, dict[str, list[str]]] = {
        "python": {
            "beginner": ["syntax", "data_types", "control_flow", "functions", "modules"],
            "intermediate": [
                "classes", "decorators", "context_managers", "generators",
                "typing", "virtualenvs",
            ],
            "advanced": [
                "async_await", "asyncio_internals", "metaclasses",
                "descriptors", "packaging", "c_extensions",
            ],
        },
        "web_dev": {
            "beginner": ["html_basics", "css_basics", "javascript_basics", "http"],
            "intermediate": ["dom", "fetch_api", "rest_apis", "auth_basics"],
            "advanced": ["ssr_vs_csr", "graphql", "service_workers", "web_perf"],
        },
        "devops": {
            "beginner": ["linux_basics", "ssh", "shell_scripting", "git"],
            "intermediate": ["docker", "ci_cd", "systemd", "reverse_proxy"],
            "advanced": ["kubernetes", "terraform", "observability", "slo_sli"],
        },
        "databases": {
            "beginner": ["sql_basics", "joins", "indexes", "normalization"],
            "intermediate": ["transactions", "query_planning", "explain_analyze", "migrations"],
            "advanced": ["replication", "sharding", "cdc", "vector_indexes"],
        },
        "security": {
            "beginner": ["auth_vs_authz", "password_hashing", "https", "input_validation"],
            "intermediate": ["oauth", "jwt", "secret_management", "threat_modeling"],
            "advanced": ["pen_testing", "zero_trust", "mtls", "siem"],
        },
    }

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine

    async def assess_level(self, user_id: str, topic: str) -> dict:
        """Determine the user's current level on a topic.

        Uses ``tech_skills`` (if tracked) then falls back to the
        ``learning_log`` count for this topic.
        """
        tracked = await db.get_tech_skill(user_id, _normalise(topic))
        if tracked is not None:
            return {
                "topic": topic,
                "level": tracked.level,
                "source": "tech_skills",
                "last_used": tracked.last_used.isoformat() if tracked.last_used else None,
            }

        log_entries = await db.get_learning_log_for_topic(user_id, _normalise(topic))
        if not log_entries:
            return {
                "topic": topic,
                "level": "beginner",
                "source": "default",
            }
        depths = [e.depth for e in log_entries]
        level = "beginner"
        if "deep" in depths:
            level = "advanced"
        elif "solid" in depths:
            level = "intermediate"
        return {
            "topic": topic,
            "level": level,
            "source": "learning_log",
            "sessions": len(log_entries),
        }

    async def explain_concept(
        self,
        user_id: str,
        concept: str,
        context_block: str = "",
    ) -> str:
        """Explain a tech concept adapted to user's level. Records in learning_log."""
        assessment = await self.assess_level(user_id, concept)
        level = assessment["level"]

        # Next depth: progress naturally if the user has already seen this.
        prior = await db.get_learning_log_for_topic(user_id, _normalise(concept))
        prior_depths = {e.depth for e in prior}
        next_depth = "intro"
        for depth in _DEPTH_PROGRESSION:
            if depth not in prior_depths:
                next_depth = depth
                break

        system = (
            f"You are MakubeX explaining a tech concept. User level: {level}. "
            f"Target depth for this explanation: {next_depth}. "
            "Open with a one-sentence intuition. Then give a concrete "
            "example (code block if useful). End with one suggestion for "
            "what to learn next after this."
        )
        user_msg = (
            f"CONCEPT: {concept}\n\nUSER CONTEXT:\n{context_block or '(none)'}\n\n"
            f"PRIOR DEPTHS COVERED: {', '.join(sorted(prior_depths)) or '(none)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=800,
        )

        try:
            await db.add_learning_log(
                user_id=user_id,
                topic=_normalise(concept),
                category="concept",
                depth=next_depth,
            )
        except Exception as exc:
            logger.debug("learning_log write failed for {}: {}", concept, exc)

        return response.text

    async def suggest_next_topic(
        self,
        user_id: str,
        domain: str | None = None,
    ) -> dict:
        """Suggest what to learn next based on skills + active projects."""
        skills = await db.get_tech_skills(user_id)
        projects = await db.get_tech_projects(user_id, status="active")
        known_topics = {_normalise(s.skill) for s in skills}

        # Project-driven suggestions first: things that would unblock work.
        project_suggestions: list[str] = []
        for proj in projects:
            for tech in proj.tech_stack or []:
                key = _normalise(tech)
                if key not in known_topics:
                    project_suggestions.append(tech)

        # Then fall through to the skill tree progression.
        tree = self.SKILL_TREES.get(domain or "", {}) if domain else {}
        tree_suggestions: list[str] = []
        for bucket in ("intermediate", "advanced"):
            for item in tree.get(bucket, []):
                if item not in known_topics:
                    tree_suggestions.append(item)

        suggestion = (
            project_suggestions[0] if project_suggestions
            else (tree_suggestions[0] if tree_suggestions else None)
        )
        return {
            "topic": suggestion,
            "project_driven": bool(project_suggestions),
            "options": project_suggestions[:3] or tree_suggestions[:3],
        }

    async def create_study_plan(
        self,
        user_id: str,
        goal: str,
        weeks: int,
        context_block: str = "",
    ) -> str:
        """Given a learning goal, create a weekly plan."""
        weeks = max(1, min(weeks, 26))
        system = (
            "You are MakubeX building a study plan. Output a Markdown "
            "table with columns: Week, Focus, Resources, Deliverable. "
            "Ramp from basics to applied within the given timeframe. "
            "Deliverables should be small, shippable, and linked to the "
            "user's stack when possible."
        )
        user_msg = (
            f"GOAL: {goal}\nWEEKS: {weeks}\n\n"
            f"USER CONTEXT:\n{context_block or '(none)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=900,
        )
        return response.text

    async def quiz(
        self,
        user_id: str,
        topic: str,
        context_block: str = "",
    ) -> str:
        """Test understanding with a single targeted question."""
        assessment = await self.assess_level(user_id, topic)
        system = (
            f"You are MakubeX quizzing the user on {topic}. Level: "
            f"{assessment['level']}. Ask ONE practical question that "
            "forces them to apply the concept (not just recite). "
            "Include 3 choices (a/b/c). Do not reveal the answer yet."
        )
        user_msg = f"USER CONTEXT:\n{context_block or '(none)'}"
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=300,
        )
        return response.text


def _normalise(topic: str) -> str:
    return topic.lower().strip().replace(" ", "_").replace("-", "_")
