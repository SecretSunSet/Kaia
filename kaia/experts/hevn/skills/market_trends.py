"""PH financial market awareness — BSP rate, PSEi, USD/PHP, news, and impact."""

from __future__ import annotations

from datetime import date

from loguru import logger

from skills.web_browse.search import news_search, web_search


class MarketTrendsSkill:
    """Wraps PH-relevant market lookups and contextualizes them for the user."""

    async def get_bsp_rate(self) -> dict:
        """Fetch the current BSP policy rate via web search (best-effort)."""
        results = await web_search("current BSP policy rate Philippines", num_results=3)
        return {
            "as_of": date.today().isoformat(),
            "source": "web_search",
            "results": results,
            "summary": results[0]["snippet"] if results else None,
        }

    async def get_psei_snapshot(self) -> dict:
        """Current PSEi level and daily change (best-effort)."""
        results = await web_search("PSEi index level today", num_results=3)
        return {
            "as_of": date.today().isoformat(),
            "source": "web_search",
            "results": results,
            "summary": results[0]["snippet"] if results else None,
        }

    async def get_usd_php_rate(self) -> dict:
        """USD → PHP exchange rate (best-effort)."""
        results = await web_search("USD to PHP exchange rate today", num_results=3)
        return {
            "as_of": date.today().isoformat(),
            "source": "web_search",
            "results": results,
            "summary": results[0]["snippet"] if results else None,
        }

    async def get_financial_news_ph(
        self, topic: str | None = None, num_results: int = 5
    ) -> list[dict]:
        """Fetch PH financial news. Filters loosely for PH relevance."""
        query = topic if topic else "Philippines finance BSP peso"
        articles = await news_search(query=query, num_results=num_results * 2)
        ph_terms = ("bsp", "bir", "sss", "pse", "peso", "philippine", "manila",
                    "pag-ibig", "philhealth", "gcash", "maya")
        filtered: list[dict] = []
        for a in articles:
            blob = f"{a.get('title', '')} {a.get('description', '')}".lower()
            if any(term in blob for term in ph_terms):
                filtered.append(a)
        return (filtered or articles)[:num_results]

    async def explain_impact(
        self,
        ai_engine,
        topic: str,
        user_profile_text: str,
    ) -> str:
        """Use the AI to explain how a market event affects the user specifically."""
        # Gather some context first
        try:
            bsp = await self.get_bsp_rate() if "rate" in topic.lower() else None
            psei = await self.get_psei_snapshot() if "psei" in topic.lower() or "stock" in topic.lower() else None
            fx = await self.get_usd_php_rate() if "peso" in topic.lower() or "usd" in topic.lower() or "dollar" in topic.lower() else None
            news = await self.get_financial_news_ph(topic, num_results=3)
        except Exception as exc:
            logger.warning("market_trends context fetch failed: {}", exc)
            bsp = psei = fx = None
            news = []

        context_lines: list[str] = []
        if bsp and bsp.get("summary"):
            context_lines.append(f"BSP rate snippet: {bsp['summary']}")
        if psei and psei.get("summary"):
            context_lines.append(f"PSEi snippet: {psei['summary']}")
        if fx and fx.get("summary"):
            context_lines.append(f"USD/PHP snippet: {fx['summary']}")
        for a in news[:3]:
            context_lines.append(
                f"- {a.get('title', '')}: {a.get('description', '')}"
            )

        context_text = "\n".join(context_lines) or "(no fresh market data retrieved)"

        system = (
            "You are Hevn, a Philippine financial advisor. Explain how this market "
            "topic affects THIS user specifically using their profile. Show estimated "
            "peso impact where possible. Keep to 4-6 short lines. Use ₱ for pesos."
        )
        user_msg = (
            f"TOPIC: {topic}\n\n"
            f"MARKET CONTEXT:\n{context_text}\n\n"
            f"USER PROFILE:\n{user_profile_text}\n\n"
            "Explain the impact on this user specifically."
        )
        response = await ai_engine.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=400,
        )
        return response.text
