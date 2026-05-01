"""Architecture skill — system / schema / API design and approach comparison."""

from __future__ import annotations

from core.ai_engine import AIEngine


class ArchitectureSkill:
    """System design, schema design, API design."""

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine

    async def design_system(
        self,
        user_id: str,
        requirements: str,
        context_block: str = "",
    ) -> str:
        """Given free-text requirements, propose a system architecture.

        Returns a markdown block with components, data flow, and
        recommended tech (biased toward the user's existing stack when
        it fits)."""
        system = (
            "You are MakubeX, a tech lead designing a pragmatic system. "
            "Given REQUIREMENTS, output a concise architecture plan with:\n"
            "1. One-paragraph summary.\n"
            "2. Components (bullet list, each with one-line responsibility).\n"
            "3. Data flow (numbered steps).\n"
            "4. Recommended tech per component, matching the user's stack "
            "when possible.\n"
            "5. Risks and trade-offs.\n"
            "Use fenced diagrams if helpful. Prefer simple over trendy."
        )
        user_msg = f"REQUIREMENTS:\n{requirements}\n\nUSER CONTEXT:\n{context_block or '(none)'}"
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=900,
        )
        return response.text

    async def review_schema(
        self,
        user_id: str,
        schema: str,
        context_block: str = "",
    ) -> str:
        """Review a database schema for normalization, indexes, relationships."""
        system = (
            "You are MakubeX reviewing a database schema. Check: "
            "normalization, primary/foreign keys, indexes (especially on "
            "columns used in WHERE/JOIN), constraints (NOT NULL, UNIQUE, "
            "CHECK), naming consistency, data type choices, and migration "
            "safety. Return a prioritized list of concrete changes."
        )
        user_msg = f"SCHEMA:\n```sql\n{schema}\n```\n\nUSER CONTEXT:\n{context_block or '(none)'}"
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=900,
        )
        return response.text

    async def design_api(
        self,
        user_id: str,
        resource: str,
        operations: list[str] | None = None,
        context_block: str = "",
    ) -> str:
        """Propose REST API endpoints for a resource."""
        ops = operations or ["list", "create", "read", "update", "delete"]
        ops_text = ", ".join(ops)
        system = (
            "You are MakubeX designing a REST API. For the given resource, "
            "propose endpoints covering the requested operations. For each, "
            "output: method, path, purpose, request body (if any), response "
            "shape, and status codes (success + key errors). Prefer "
            "plural-noun paths, idempotent PUT semantics, and 2xx/4xx/5xx "
            "conventions."
        )
        user_msg = (
            f"RESOURCE: {resource}\n"
            f"OPERATIONS: {ops_text}\n\n"
            f"USER CONTEXT:\n{context_block or '(none)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=900,
        )
        return response.text

    async def compare_approaches(
        self,
        user_id: str,
        option_a: str,
        option_b: str,
        context: str = "",
    ) -> str:
        """Compare two architectural approaches with pros/cons and a recommendation."""
        system = (
            "You are MakubeX comparing two architectural approaches. "
            "Return:\n"
            "1. Short framing of the decision.\n"
            "2. Pros/cons table for each option (concise bullets).\n"
            "3. Which one fits the user's situation better and why.\n"
            "4. What could make you change your mind.\n"
            "Opinionated but honest — no hype."
        )
        user_msg = (
            f"OPTION A: {option_a}\nOPTION B: {option_b}\n\n"
            f"CONTEXT: {context or '(none)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=800,
        )
        return response.text
