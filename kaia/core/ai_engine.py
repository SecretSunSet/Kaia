"""Claude API client with Groq fallback, prompt builder, and response handling."""

from __future__ import annotations

from dataclasses import dataclass

import anthropic
from groq import AsyncGroq
from loguru import logger

from config.settings import get_settings
from utils.time_utils import format_current_context


@dataclass
class AIResponse:
    """Standardised wrapper for AI responses regardless of provider."""

    text: str
    provider: str  # "claude" | "groq"
    model: str
    input_tokens: int
    output_tokens: int


class AIEngine:
    """Manages Claude (primary) and Groq (fallback) API calls."""

    def __init__(self) -> None:
        self._settings = get_settings()

        # Claude (primary)
        self._claude = anthropic.AsyncAnthropic(api_key=self._settings.anthropic_api_key)

        # Groq (fallback)
        self._groq: AsyncGroq | None = None
        if self._settings.groq_api_key:
            self._groq = AsyncGroq(api_key=self._settings.groq_api_key)

    # ── Public API ───────────────────────────────────────────────────

    async def chat(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        user_timezone: str | None = None,
    ) -> AIResponse:
        """Send a chat request. Falls back to Groq on Claude failure.

        Auto-prepends a "Current Time Context" block to the system prompt so
        every caller (general chat, every expert, onboarding, extraction)
        gets time awareness with no per-call changes.
        """
        max_tokens = max_tokens or self._settings.claude_max_tokens
        tz = user_timezone or self._settings.default_timezone
        full_system = (
            f"# Current Time Context\n{format_current_context(tz)}\n\n"
            "When the user mentions relative time (\"yesterday\", \"last week\", "
            "\"earlier\"), compute against the time above. Never assume a "
            "different year or date. When you reference past events, use the "
            "actual timestamps in the data, not your assumption.\n\n---\n\n"
            f"{system_prompt}"
        )
        try:
            return await self._call_claude(full_system, messages, max_tokens)
        except Exception as exc:
            logger.warning("Claude API failed ({}), falling back to Groq", exc)
            if self._groq is None:
                raise RuntimeError("Claude failed and no Groq API key configured") from exc
            return await self._call_groq(full_system, messages, max_tokens)

    # ── Claude ───────────────────────────────────────────────────────

    async def _call_claude(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> AIResponse:
        response = await self._claude.messages.create(
            model=self._settings.claude_model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        text = response.content[0].text
        usage = response.usage
        logger.debug(
            "Claude | in={} out={} model={}",
            usage.input_tokens,
            usage.output_tokens,
            self._settings.claude_model,
        )
        return AIResponse(
            text=text,
            provider="claude",
            model=self._settings.claude_model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

    # ── Groq (fallback) ─────────────────────────────────────────────

    async def _call_groq(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> AIResponse:
        assert self._groq is not None
        groq_messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]
        response = await self._groq.chat.completions.create(
            model=self._settings.groq_model,
            messages=groq_messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
        )
        text = response.choices[0].message.content or ""
        usage = response.usage
        input_tok = usage.prompt_tokens if usage else 0
        output_tok = usage.completion_tokens if usage else 0
        logger.debug(
            "Groq | in={} out={} model={}",
            input_tok,
            output_tok,
            self._settings.groq_model,
        )
        return AIResponse(
            text=text,
            provider="groq",
            model=self._settings.groq_model,
            input_tokens=input_tok,
            output_tokens=output_tok,
        )


def build_message_history(
    conversations: list[dict[str, str]],
    current_message: str,
) -> list[dict[str, str]]:
    """Build the messages list for the AI from conversation history + new message."""
    messages: list[dict[str, str]] = []
    for conv in conversations:
        messages.append({"role": conv["role"], "content": conv["content"]})
    messages.append({"role": "user", "content": current_message})
    return messages
