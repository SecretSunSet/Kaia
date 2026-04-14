"""Web browse skill handler — search the web, fetch news, and summarise results."""

from __future__ import annotations

import json

from loguru import logger

from config.constants import SKILL_WEB_BROWSE
from config.settings import get_settings
from core.ai_engine import AIEngine
from database.models import User
from skills.base import BaseSkill, SkillResult
from skills.web_browse.prompts import (
    build_news_summary_prompt,
    build_page_summary_prompt,
    build_search_decision_prompt,
    build_search_summary_prompt,
    format_search_results,
)
from skills.web_browse.scraper import scrape_page
from skills.web_browse.search import get_weather, news_search, web_search


class WebBrowseSkill(BaseSkill):
    """Handles web search, news lookup, and weather queries."""

    name = SKILL_WEB_BROWSE

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

        # Direct weather request
        if _is_weather_request(msg):
            return await self._handle_weather(user, message)

        # Direct news request
        if _is_news_request(msg):
            return await self._handle_news(message)

        # Web search
        return await self._handle_search(message)

    # ── Weather ──────────────────────────────────────────────────────

    async def _handle_weather(self, user: User, message: str) -> SkillResult:
        settings = get_settings()
        if not settings.openweather_api_key:
            return SkillResult(
                text="Weather isn't configured yet. Add an OpenWeatherMap API key to enable this.",
                skill_name=self.name,
            )

        # Try to extract location from message, fall back to default
        location = _extract_location(message) or settings.default_location

        weather = await get_weather(location)
        if weather is None:
            return SkillResult(
                text=f"Couldn't fetch weather for {location}. Please try again.",
                skill_name=self.name,
            )

        text = (
            f"🌤️ Weather — {weather['location']}\n\n"
            f"🌡️ {weather['temp']:.0f}°C (feels like {weather['feels_like']:.0f}°C)\n"
            f"☁️ {weather['description']}\n"
            f"💧 Humidity: {weather['humidity']}%\n"
            f"💨 Wind: {weather['wind_speed']:.1f} m/s"
        )
        return SkillResult(text=text, skill_name=self.name)

    # ── News ──────���──────────────────────────────────────────────────

    async def _handle_news(self, message: str) -> SkillResult:
        settings = get_settings()
        if not settings.news_api_key:
            return SkillResult(
                text="News search isn't configured yet. Add a NewsAPI key to enable this.",
                skill_name=self.name,
            )

        # Extract topic from message, or get general headlines
        query = _extract_news_topic(message)
        articles = await news_search(query=query, num_results=5)

        if not articles:
            return SkillResult(
                text="Couldn't find any recent news. Please try again.",
                skill_name=self.name,
            )

        formatted = format_search_results(articles)
        prompt = build_news_summary_prompt(query, formatted)

        response = await self.ai.chat(
            system_prompt=prompt,
            messages=[{"role": "user", "content": message}],
        )
        return SkillResult(
            text=response.text,
            skill_name=self.name,
            ai_response=response,
        )

    # ── Web search ───────────────────────────────────────────────────

    async def _handle_search(self, message: str) -> SkillResult:
        settings = get_settings()
        if not settings.serpapi_key:
            return SkillResult(
                text="Web search isn't configured yet. Add a SerpAPI key to enable this.",
                skill_name=self.name,
            )

        # Optimize the search query via AI
        search_query = await self._optimize_query(message)

        results = await web_search(search_query, num_results=5)
        if not results:
            return SkillResult(
                text=f"No search results found for: {search_query}",
                skill_name=self.name,
            )

        # Summarise search results
        formatted = format_search_results(results)
        prompt = build_search_summary_prompt(message, formatted)

        response = await self.ai.chat(
            system_prompt=prompt,
            messages=[{"role": "user", "content": message}],
        )
        return SkillResult(
            text=response.text,
            skill_name=self.name,
            ai_response=response,
        )

    async def _optimize_query(self, message: str) -> str:
        """Use AI to create an optimized search query from the user message."""
        try:
            response = await self.ai.chat(
                system_prompt=build_search_decision_prompt(),
                messages=[{"role": "user", "content": message}],
                max_tokens=64,
            )
            data = json.loads(response.text.strip())
            return data.get("query", message)
        except Exception:
            # Fall back to using the raw message as the query
            return message


# ── Sub-intent detection helpers ─────────────────────────────────────

def _is_weather_request(msg: str) -> bool:
    patterns = ["weather", "temperature", "how hot", "how cold", "is it raining"]
    return any(p in msg for p in patterns)


def _is_news_request(msg: str) -> bool:
    patterns = [
        "news", "headlines", "what's happening", "latest on",
        "recent developments", "current events",
    ]
    return any(p in msg for p in patterns)


def _extract_location(message: str) -> str | None:
    """Try to extract a location from a weather query."""
    msg = message.lower()
    # Common patterns: "weather in <location>", "weather for <location>"
    for prefix in ("weather in ", "weather for ", "weather at "):
        if prefix in msg:
            loc = msg.split(prefix, 1)[1].strip().rstrip("?.")
            if loc:
                return loc.title()
    return None


def _extract_news_topic(message: str) -> str | None:
    """Try to extract a topic from a news query. None = general headlines."""
    msg = message.lower()
    for prefix in (
        "news about ", "news on ", "latest on ", "latest news on ",
        "latest news about ", "what's happening with ", "updates on ",
    ):
        if prefix in msg:
            topic = msg.split(prefix, 1)[1].strip().rstrip("?.")
            if topic:
                return topic
    # If it's just "news" or "headlines", return None for general
    if msg.strip().rstrip("?.") in ("news", "headlines", "latest news", "top news", "what's the news"):
        return None
    return None
