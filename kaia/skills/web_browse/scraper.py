"""Web page content scraper using BeautifulSoup."""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from config.constants import WEB_REQUEST_TIMEOUT, WEB_SCRAPE_MAX_CHARS

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

_STRIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"}


async def scrape_page(url: str, max_chars: int = WEB_SCRAPE_MAX_CHARS) -> str | None:
    """Fetch a web page and extract its main text content.

    Returns cleaned text truncated to *max_chars*. Returns None on failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=WEB_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove unwanted elements
        for tag in soup.find_all(_STRIP_TAGS):
            tag.decompose()

        # Try to find main content
        main = soup.find("article") or soup.find("main") or soup.find("body")
        if main is None:
            return None

        text = main.get_text(separator="\n", strip=True)
        text = _clean_text(text)

        if not text:
            return None

        return text[:max_chars]

    except Exception as exc:
        logger.error("Failed to scrape {}: {}", url, exc)
        return None


async def extract_article(url: str) -> dict | None:
    """Extract article content: title, text, and optional metadata.

    Returns {"title": str, "text": str} or None on failure.
    """
    try:
        async with httpx.AsyncClient(
            timeout=WEB_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract title
        title = ""
        title_tag = soup.find("h1") or soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Remove unwanted elements
        for tag in soup.find_all(_STRIP_TAGS):
            tag.decompose()

        # Find article body
        article = soup.find("article") or soup.find("main") or soup.find("body")
        if article is None:
            return None

        text = article.get_text(separator="\n", strip=True)
        text = _clean_text(text)

        if not text:
            return None

        return {
            "title": title,
            "text": text[:WEB_SCRAPE_MAX_CHARS],
        }

    except Exception as exc:
        logger.error("Failed to extract article from {}: {}", url, exc)
        return None


def _clean_text(text: str) -> str:
    """Clean extracted text: collapse whitespace, remove excess blank lines."""
    # Collapse multiple spaces
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
