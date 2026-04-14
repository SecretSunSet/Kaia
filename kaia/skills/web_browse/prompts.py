"""Prompt builders for the web browse skill."""

from __future__ import annotations


def build_search_summary_prompt(query: str, formatted_results: str) -> str:
    """Prompt for summarising web search results."""
    return f"""\
The user asked: "{query}"

Here are web search results:
{formatted_results}

Based on these search results, provide a clear and concise answer to the user's question. \
If the results don't contain enough information, say so honestly. \
Cite the source briefly when stating facts. Keep your answer conversational and concise.
"""


def build_page_summary_prompt(query: str, url: str, page_content: str) -> str:
    """Prompt for summarising scraped page content."""
    return f"""\
The user asked: "{query}"

Here is content from {url}:
{page_content}

Summarize the relevant information that answers the user's question. \
Be concise and accurate. If the content doesn't address their question, say so.
"""


def build_news_summary_prompt(query: str | None, formatted_articles: str) -> str:
    """Prompt for summarising news results."""
    topic = f'"{query}"' if query else "top headlines"
    return f"""\
The user asked about {topic}.

Here are recent news articles:
{formatted_articles}

Summarize the key stories concisely. For each major story, include the headline and a one-sentence summary. \
Keep it scannable — no more than 5-7 items. Cite the source for each.
"""


def build_search_decision_prompt() -> str:
    """System prompt for deciding whether to search the web."""
    return """\
The user sent a message. Decide whether I need to search the web to answer it.

Consider:
- Is this asking about current events, prices, recent news, or real-time data? → SEARCH
- Is this a general knowledge question I can answer reliably? → NO SEARCH
- Is this asking about something that changes frequently? → SEARCH
- Is this a personal question about the user? → NO SEARCH (use memory)
- Is this asking me to look up, search, or find something? → SEARCH

Respond with ONLY a JSON object (no other text):
{"search": true, "query": "optimized search query if true"}
or
{"search": false}
"""


def format_search_results(results: list[dict]) -> str:
    """Format search results for injection into an AI prompt."""
    if not results:
        return "(No results found)"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r.get('title', 'Untitled')}]({r.get('url', '')})")
        snippet = r.get("snippet") or r.get("description") or ""
        if snippet:
            lines.append(f"   {snippet}")
        source = r.get("source")
        if source:
            lines.append(f"   Source: {source}")
        lines.append("")
    return "\n".join(lines)
