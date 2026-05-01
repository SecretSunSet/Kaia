"""Tech research skill — evaluate tools and frameworks, track latest trends."""

from __future__ import annotations

from loguru import logger

from core.ai_engine import AIEngine
from skills.web_browse.search import web_search


class TechResearchSkill:
    """Evaluate tools, frameworks, libraries. Latest tech trends."""

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine

    async def compare_tools(
        self,
        user_id: str,
        tools: list[str],
        use_case: str,
        context_block: str = "",
    ) -> str:
        """Compare tools/frameworks for a specific use case.

        Pulls fresh context from a web search when available, then asks
        MakubeX to decide.
        """
        web_context = await self._fresh_web_context(
            f"{' vs '.join(tools)} {use_case} 2026"
        )
        system = (
            "You are MakubeX comparing tools. Output:\n"
            "1. 1-line framing of the decision.\n"
            "2. Short table: each tool's strengths / weaknesses for THIS use case.\n"
            "3. Recommendation with a concrete reason (tie to user's stack).\n"
            "4. When the other option would win.\n"
            "Use current info from the web context if provided. No hype."
        )
        user_msg = (
            f"TOOLS: {', '.join(tools)}\nUSE CASE: {use_case}\n\n"
            f"USER CONTEXT:\n{context_block or '(none)'}\n\n"
            f"WEB CONTEXT:\n{web_context or '(unavailable)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=900,
        )
        return response.text

    async def recommend_tool(
        self,
        user_id: str,
        need: str,
        context_block: str = "",
    ) -> str:
        """Given a specific need, recommend the best tool. Considers user's stack."""
        web_context = await self._fresh_web_context(f"best tool for {need} 2026")
        system = (
            "You are MakubeX recommending a single tool. Give a direct "
            "pick, the reason it wins for THIS need, and the top runner-up "
            "as a fallback. Bias toward the user's existing stack when the "
            "quality difference is marginal."
        )
        user_msg = (
            f"NEED: {need}\n\nUSER CONTEXT:\n{context_block or '(none)'}\n\n"
            f"WEB CONTEXT:\n{web_context or '(unavailable)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=700,
        )
        return response.text

    async def latest_on_topic(
        self,
        user_id: str,
        topic: str,
        context_block: str = "",
    ) -> str:
        """Summarise the latest developments on a technology."""
        web_context = await self._fresh_web_context(f"latest {topic} updates 2026")
        system = (
            "You are MakubeX catching the user up on a technology. "
            "Output 4-6 short bullet points covering recent versions, "
            "notable changes, deprecations, and anything that impacts the "
            "user's stack. Cite sources inline as [1], [2], ... if the "
            "web context contains URLs."
        )
        user_msg = (
            f"TOPIC: {topic}\n\nUSER CONTEXT:\n{context_block or '(none)'}\n\n"
            f"WEB CONTEXT:\n{web_context or '(unavailable)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=700,
        )
        return response.text

    async def evaluate_trend(
        self,
        user_id: str,
        trend: str,
        context_block: str = "",
    ) -> str:
        """Is this trend worth adopting? Analysis of maturity, ecosystem, fit."""
        web_context = await self._fresh_web_context(f"{trend} adoption production 2026")
        system = (
            "You are MakubeX evaluating a tech trend. Score it on: "
            "maturity, ecosystem depth, operational cost, and fit for the "
            "user's stack. Be skeptical — most trends aren't worth chasing. "
            "End with 'Adopt / Watch / Skip' and one sentence of reasoning."
        )
        user_msg = (
            f"TREND: {trend}\n\nUSER CONTEXT:\n{context_block or '(none)'}\n\n"
            f"WEB CONTEXT:\n{web_context or '(unavailable)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=600,
        )
        return response.text

    async def _fresh_web_context(self, query: str, limit: int = 4) -> str:
        """Fetch a compact web-search context string. Degrades to '' on failure."""
        try:
            results = await web_search(query, num_results=limit)
        except Exception as exc:
            logger.debug("tech_research web fetch failed: {}", exc)
            return ""
        if not results:
            return ""
        lines: list[str] = []
        for i, r in enumerate(results, start=1):
            title = r.get("title", "").strip()
            url = r.get("url", "").strip()
            snippet = r.get("snippet", "").strip()
            if not (title or snippet):
                continue
            lines.append(f"[{i}] {title} — {url}\n    {snippet}")
        return "\n".join(lines)
