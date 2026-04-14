"""Web search, news search, and weather API clients."""

from __future__ import annotations

import httpx
from loguru import logger

from config.settings import get_settings
from config.constants import WEB_REQUEST_TIMEOUT


async def web_search(query: str, num_results: int = 5) -> list[dict]:
    """Search the web using SerpAPI.

    Returns list of: {"title": str, "url": str, "snippet": str}
    Returns empty list if SERPAPI_KEY is not configured or on error.
    """
    settings = get_settings()
    if not settings.serpapi_key:
        logger.debug("SerpAPI key not configured, skipping web search")
        return []

    try:
        async with httpx.AsyncClient(timeout=WEB_REQUEST_TIMEOUT) as client:
            resp = await client.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": settings.serpapi_key,
                    "num": num_results,
                    "engine": "google",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("organic_results", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return results

    except Exception as exc:
        logger.error("Web search failed: {}", exc)
        return []


async def news_search(query: str | None = None, num_results: int = 5) -> list[dict]:
    """Search for news using NewsAPI.

    Returns list of: {"title": str, "url": str, "description": str,
                      "source": str, "published_at": str}
    Returns empty list if NEWS_API_KEY is not configured or on error.
    """
    settings = get_settings()
    if not settings.news_api_key:
        logger.debug("NewsAPI key not configured, skipping news search")
        return []

    try:
        endpoint = "https://newsapi.org/v2/top-headlines" if not query else "https://newsapi.org/v2/everything"
        params: dict = {
            "apiKey": settings.news_api_key,
            "pageSize": num_results,
            "language": "en",
        }
        if query:
            params["q"] = query
        else:
            params["country"] = "ph"

        async with httpx.AsyncClient(timeout=WEB_REQUEST_TIMEOUT) as client:
            resp = await client.get(endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for article in data.get("articles", [])[:num_results]:
            results.append({
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                "description": article.get("description", ""),
                "source": article.get("source", {}).get("name", ""),
                "published_at": article.get("publishedAt", ""),
            })
        return results

    except Exception as exc:
        logger.error("News search failed: {}", exc)
        return []


async def get_weather(location: str = "Manila, Philippines") -> dict | None:
    """Get current weather using OpenWeatherMap API.

    Returns: {"temp": float, "feels_like": float, "description": str,
              "humidity": int, "wind_speed": float, "location": str}
    Returns None if OPENWEATHER_API_KEY is not configured or on error.
    """
    settings = get_settings()
    if not settings.openweather_api_key:
        logger.debug("OpenWeather API key not configured, skipping weather")
        return None

    try:
        async with httpx.AsyncClient(timeout=WEB_REQUEST_TIMEOUT) as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "q": location,
                    "appid": settings.openweather_api_key,
                    "units": "metric",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        weather_desc = data.get("weather", [{}])[0].get("description", "").title()
        main = data.get("main", {})

        return {
            "temp": main.get("temp", 0),
            "feels_like": main.get("feels_like", 0),
            "description": weather_desc,
            "humidity": main.get("humidity", 0),
            "wind_speed": data.get("wind", {}).get("speed", 0),
            "location": location,
        }

    except Exception as exc:
        logger.error("Weather fetch failed for '{}': {}", location, exc)
        return None
