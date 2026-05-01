"""Code review skill — analyse code snippets and return structured feedback."""

from __future__ import annotations

import hashlib
import json
import re

from loguru import logger

from core.ai_engine import AIEngine
from database import queries as db


_SEVERITY_ORDER = ("critical", "high", "medium", "low", "nit")
_SEVERITY_EMOJI = {
    "critical": "🚨",
    "high": "🔴",
    "medium": "🟠",
    "low": "🟡",
    "nit": "💬",
}


_LANGUAGE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("python", re.compile(r"\b(def |import |from \w+ import |async def |self\.)")),
    ("javascript", re.compile(r"\b(const |let |var |=> |require\(|module\.exports)")),
    ("typescript", re.compile(r"\b(interface |type \w+ =|: string|: number|: boolean)\b")),
    ("go", re.compile(r"\b(func |package |import \(|:= )")),
    ("rust", re.compile(r"\b(fn |let mut |impl |pub fn |struct |::)")),
    ("java", re.compile(r"\b(public class |private |import java)")),
    ("sql", re.compile(r"\b(SELECT |INSERT INTO|UPDATE |DELETE FROM|CREATE TABLE)", re.IGNORECASE)),
    ("bash", re.compile(r"(^#!/bin/bash|\$\{?\w+\}?|\b(apt-get|grep|awk|sed)\b)")),
    ("html", re.compile(r"</?(html|body|div|span|section|a|p|ul|li)\b", re.IGNORECASE)),
    ("yaml", re.compile(r"(^\s*[a-zA-Z_][\w\-]*:\s|---\n)", re.MULTILINE)),
]


class CodeReviewSkill:
    """Review code snippets, suggest improvements, catch issues."""

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine

    async def review_code(
        self,
        user_id: str,
        code: str,
        language: str | None = None,
    ) -> dict:
        """Analyse code and return a structured review dict.

        Deduplicates on snippet hash — repeat reviews return the cached
        result instead of burning tokens.
        """
        lang = language or self.detect_language(code)
        snippet_hash = _hash_snippet(code)

        cached = await db.get_code_review_by_hash(user_id, snippet_hash)
        if cached is not None:
            return {
                "language": cached.language or lang,
                "summary": cached.summary or "",
                "issues": cached.issues_found or [],
                "improvements": [],
                "strengths": [],
                "from_cache": True,
            }

        system = (
            "You are MakubeX, a senior tech lead doing a code review. "
            "Review the code and return ONLY a JSON object with this shape:\n"
            "{\n"
            "  \"language\": string,\n"
            "  \"summary\": string (<= 160 chars),\n"
            "  \"issues\": [ {\"severity\": \"critical|high|medium|low|nit\", "
            "\"line\": int or null, \"issue\": string, \"suggestion\": string } ],\n"
            "  \"improvements\": [string, ...],\n"
            "  \"strengths\": [string, ...]\n"
            "}\n"
            "Check: correctness (bugs, logic errors, races), security "
            "(injection, XSS, exposed secrets), performance (N+1, blocking "
            "calls, inefficient loops), readability (naming, complexity), "
            "best practices (language/framework idioms), error handling "
            "(missing try/except, silent failures)."
        )

        user_msg = f"LANGUAGE HINT: {lang or 'unknown'}\n\nCODE:\n```{lang or ''}\n{code}\n```"

        try:
            response = await self.ai.chat(
                system_prompt=system,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=1200,
            )
            parsed = _extract_json(response.text)
        except Exception as exc:
            logger.warning("Code review failed: {}", exc)
            parsed = None

        review: dict = {
            "language": lang,
            "summary": "",
            "issues": [],
            "improvements": [],
            "strengths": [],
            "from_cache": False,
        }
        if isinstance(parsed, dict):
            review["language"] = parsed.get("language") or lang
            review["summary"] = parsed.get("summary", "") or ""
            review["issues"] = _normalise_issues(parsed.get("issues"))
            review["improvements"] = _as_str_list(parsed.get("improvements"))
            review["strengths"] = _as_str_list(parsed.get("strengths"))

        try:
            await db.save_code_review(
                user_id=user_id,
                snippet_hash=snippet_hash,
                language=review["language"],
                summary=review["summary"],
                issues_found=review["issues"],
            )
        except Exception as exc:
            logger.debug("Failed to persist code review: {}", exc)

        return review

    def detect_language(self, code: str) -> str | None:
        """Quick heuristic detector. Prefer caller-provided hint when available."""
        for name, pattern in _LANGUAGE_PATTERNS:
            if pattern.search(code):
                return name
        return None

    def format_review(self, review: dict) -> str:
        """Format a review dict for Telegram display."""
        lang = review.get("language") or "code"
        summary = review.get("summary") or "Review complete."
        lines = [f"🔧 *MakubeX Code Review — {lang}*", "", f"_{summary}_"]

        issues = sorted(
            review.get("issues", []),
            key=lambda i: _SEVERITY_ORDER.index(i.get("severity", "low"))
            if i.get("severity") in _SEVERITY_ORDER else len(_SEVERITY_ORDER),
        )
        if issues:
            lines.append("")
            lines.append("*Issues:*")
            for issue in issues:
                severity = issue.get("severity", "low")
                emoji = _SEVERITY_EMOJI.get(severity, "•")
                line_ref = ""
                if issue.get("line"):
                    line_ref = f" (line {issue['line']})"
                lines.append(
                    f"{emoji} *{severity.title()}*{line_ref}: {issue.get('issue', '').strip()}"
                )
                suggestion = (issue.get("suggestion") or "").strip()
                if suggestion:
                    lines.append(f"   → {suggestion}")

        improvements = review.get("improvements", [])
        if improvements:
            lines.append("")
            lines.append("*Improvements:*")
            for item in improvements:
                lines.append(f"• {item}")

        strengths = review.get("strengths", [])
        if strengths:
            lines.append("")
            lines.append("*Strengths:*")
            for item in strengths:
                lines.append(f"✅ {item}")

        if not issues and not improvements and not strengths:
            lines.append("")
            lines.append("No blocking issues spotted. Looks clean.")

        if review.get("from_cache"):
            lines.append("")
            lines.append("_(cached — already reviewed this snippet before)_")

        return "\n".join(lines)


def _hash_snippet(code: str) -> str:
    """Stable hash for dedup — ignores trailing whitespace."""
    normalised = "\n".join(line.rstrip() for line in code.strip().splitlines())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of the model response."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _normalise_issues(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    issues: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "low")).lower()
        if severity not in _SEVERITY_ORDER:
            severity = "low"
        line = item.get("line")
        try:
            line = int(line) if line is not None else None
        except (TypeError, ValueError):
            line = None
        issues.append(
            {
                "severity": severity,
                "line": line,
                "issue": str(item.get("issue", "")).strip(),
                "suggestion": str(item.get("suggestion", "")).strip(),
            }
        )
    return issues


def _as_str_list(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]
