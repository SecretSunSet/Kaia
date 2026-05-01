"""Intent classifier and simple command parsers for MakubeX."""

from __future__ import annotations

import json
import re

from loguru import logger

from core.ai_engine import AIEngine
from experts.makubex.prompts import MAKUBEX_INTENT_PROMPT


# Patterns that short-circuit the AI classifier.
_CODE_BLOCK_RE = re.compile(r"```[\s\S]+?```")


CODE_REVIEW_MARKERS = (
    "review this", "review my code", "code review", "look at this code",
    "is this good", "is this correct", "check my code", "anything wrong",
    "spot any bugs", "refactor this", "improve this code",
)

ARCHITECTURE_MARKERS = (
    "how should i structure", "how do i structure", "system design",
    "design the database", "design a schema", "design the api",
    "propose an architecture", "architecture for", "data flow",
    "schema for", "microservice", "monolith", "microservices vs",
)

DEBUGGING_MARKERS = (
    "error", "exception", "traceback", "stack trace", "stacktrace",
    "crashing", "crashes", "crash loop", "segfault", "keyerror", "typeerror",
    "valueerror", "nullpointer", "not working", "broken", "why is this slow",
    "memory leak", "high cpu", "debug", "debugging",
)

RESEARCH_MARKERS = (
    " vs ", "versus", "which is better", "compare ", "latest on",
    "latest in", "should i use", "should i switch", "worth learning",
    "is it worth", "best framework", "best library", "best tool",
)

DEVOPS_MARKERS = (
    "deploy", "deployment", "ci/cd", "ci pipeline", "cd pipeline",
    "github actions", "dockerize", "docker compose", "kubernetes",
    "k8s", "systemd", "nginx", "reverse proxy", "monitoring",
    "grafana", "prometheus", "ec2", "aws", "terraform", "infra",
    "infrastructure",
)

SECURITY_MARKERS = (
    "secure", "insecure", "vulnerability", "vulnerabilities", "cve",
    "sql injection", "xss", "csrf", "auth flow", "jwt", "oauth",
    "secrets", "api key", "credential", "threat model", "pen test",
    "penetration test", "owasp",
)

LEARNING_MARKERS = (
    "explain ", "explain how", "what is ", "what's ", "teach me",
    "walk me through", "how does ", "how do ", "learn about",
    "study plan", "learning plan", "roadmap", "what should i learn",
    "quiz me",
)

PROJECT_MARKERS = (
    "add a project", "add a new project", "new project", "create project",
    "register project", "track this project", "list my projects",
    "show my projects", "my projects", "project status", "status on ",
    "update my project",
)


async def classify_makubex_intent(ai: AIEngine, message: str) -> str:
    """Classify a message into one of MakubeX's skills."""
    low = message.lower().strip()

    # Code block almost always means review request.
    if _CODE_BLOCK_RE.search(message) and len(message) > 60:
        return "code_review"

    if any(m in low for m in PROJECT_MARKERS):
        return "project_manager"
    if any(m in low for m in CODE_REVIEW_MARKERS):
        return "code_review"
    if any(m in low for m in ARCHITECTURE_MARKERS):
        return "architecture"
    if any(m in low for m in DEBUGGING_MARKERS):
        return "debugging"
    if any(m in low for m in DEVOPS_MARKERS):
        return "devops"
    if any(m in low for m in SECURITY_MARKERS):
        return "security"
    if any(m in low for m in RESEARCH_MARKERS):
        return "tech_research"
    if any(m in low for m in LEARNING_MARKERS):
        return "learning_coach"

    # Fall back to AI classifier.
    try:
        response = await ai.chat(
            system_prompt="You are a strict intent classifier. Reply only with JSON.",
            messages=[{"role": "user", "content": MAKUBEX_INTENT_PROMPT.format(message=message)}],
            max_tokens=60,
        )
        text = response.text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            parsed = json.loads(text[start:end + 1])
            skill = parsed.get("skill", "general_chat")
            if skill in {
                "code_review", "architecture", "debugging", "tech_research",
                "devops", "security", "learning_coach", "project_manager",
                "general_chat",
            }:
                return skill
    except Exception as exc:
        logger.debug("MakubeX intent classification fallback: {}", exc)
    return "general_chat"


async def parse_project_creation(
    ai: AIEngine, message: str
) -> dict | None:
    """Parse an 'add a new project' request into params."""
    system = (
        "Extract a tech project from the user's message. Return ONLY a JSON object: "
        "{\"name\": string, \"description\": string or null, "
        "\"tech_stack\": [list of strings] or null, "
        "\"repo_url\": string or null, \"priority\": 1|2|3}. "
        "If not a project creation, return {\"name\": null}."
    )
    try:
        response = await ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": message}],
            max_tokens=200,
        )
        text = response.text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return None
        parsed = json.loads(text[start:end + 1])
        if not parsed.get("name"):
            return None
        stack = parsed.get("tech_stack")
        if stack is not None and not isinstance(stack, list):
            stack = None
        return {
            "name": parsed["name"],
            "description": parsed.get("description"),
            "tech_stack": stack,
            "repo_url": parsed.get("repo_url"),
            "priority": int(parsed.get("priority", 2)),
        }
    except Exception as exc:
        logger.debug("Project parse failed: {}", exc)
        return None


def extract_code_block(message: str) -> tuple[str | None, str | None]:
    """Extract the first fenced code block from a message.

    Returns (code, language_hint). If no code block found returns (None, None).
    """
    match = re.search(r"```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```", message)
    if not match:
        # Fall back: treat very long plain messages with newlines as code.
        if message.count("\n") >= 3 and len(message) > 120:
            return message.strip(), None
        return None, None
    lang = (match.group(1) or "").strip().lower() or None
    code = match.group(2).strip()
    if not code:
        return None, None
    return code, lang
