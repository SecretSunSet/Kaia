"""Security skill — project audit, auth review, API hardening, secrets, deps."""

from __future__ import annotations

from loguru import logger

from core.ai_engine import AIEngine
from database import queries as db
from skills.web_browse.search import web_search


class SecuritySkill:
    """Security review, vulnerability detection, best practices."""

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine

    async def audit_project(
        self,
        user_id: str,
        project_name: str,
        context_block: str = "",
    ) -> str:
        """Audit a project for common security issues using its tracked context."""
        project = await db.get_tech_project_by_name(user_id, project_name)
        project_block = "(project not tracked — speaking generally)"
        if project is not None:
            stack = ", ".join(project.tech_stack) if project.tech_stack else "unknown"
            project_block = (
                f"Name: {project.name}\nStack: {stack}\n"
                f"Description: {project.description or '(none)'}\n"
                f"Repo: {project.repo_url or '(none)'}"
            )

        system = (
            "You are MakubeX doing a security audit. Check:\n"
            "- Secret management (env vars, vaults, committed keys).\n"
            "- Auth / authorisation (session handling, role checks).\n"
            "- Input validation + output encoding (XSS, SSRF).\n"
            "- SQL injection vectors (parameterisation, ORMs).\n"
            "- Transport security (HTTPS, HSTS, cert pinning where "
            "relevant).\n"
            "- Dependency freshness (known CVEs).\n"
            "Output a prioritised list with concrete remediations."
        )
        user_msg = (
            f"PROJECT:\n{project_block}\n\nUSER CONTEXT:\n{context_block or '(none)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=900,
        )
        return response.text

    async def review_auth_flow(
        self,
        user_id: str,
        description: str,
        context_block: str = "",
    ) -> str:
        """Review an authentication / authorisation design."""
        system = (
            "You are MakubeX reviewing an auth design. Check: identity "
            "(who), authentication (prove it), session (where lives, "
            "expiry, rotation), authorisation (what allowed), audit "
            "(who did what). Flag any patterns that smell risky — "
            "rolling your own crypto, unsigned tokens, long-lived "
            "refresh tokens without rotation, etc."
        )
        user_msg = (
            f"AUTH DESIGN:\n{description}\n\n"
            f"USER CONTEXT:\n{context_block or '(none)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=800,
        )
        return response.text

    async def check_api_security(
        self,
        user_id: str,
        api_description: str,
        context_block: str = "",
    ) -> str:
        """Review an API for security concerns — rate limiting, auth, input."""
        system = (
            "You are MakubeX reviewing an API for security. Check: "
            "authentication on every endpoint, authorisation checks, "
            "rate limiting, input validation, output encoding, CORS, "
            "error messages that leak information, and sensitive data "
            "exposure in responses. Give prioritised fixes."
        )
        user_msg = (
            f"API:\n{api_description}\n\n"
            f"USER CONTEXT:\n{context_block or '(none)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=800,
        )
        return response.text

    async def secrets_best_practices(
        self,
        user_id: str,
        context_block: str = "",
    ) -> str:
        """Guide on managing API keys, credentials, secrets."""
        system = (
            "You are MakubeX explaining secret management. Cover: where "
            "secrets should live (env vars, vaults, SOPS, KMS), rotation "
            "cadence, access control, detection if leaked, and the "
            "minimum viable setup for a solo dev vs a team. Recommend a "
            "concrete path matching the user's stack."
        )
        user_msg = f"USER CONTEXT:\n{context_block or '(none)'}"
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=700,
        )
        return response.text

    async def dependency_audit(
        self,
        user_id: str,
        requirements: str,
        context_block: str = "",
    ) -> str:
        """Review requirements.txt / package.json for vulnerabilities or staleness."""
        web_context = ""
        try:
            results = await web_search(
                "latest CVE advisories python javascript 2026", num_results=4
            )
            if results:
                web_context = "\n".join(
                    f"- {r.get('title', '')} — {r.get('url', '')}"
                    for r in results
                )
        except Exception as exc:
            logger.debug("dependency_audit web fetch failed: {}", exc)

        system = (
            "You are MakubeX auditing a dependency manifest. Flag: "
            "pinned vs floating versions, packages known for CVEs, "
            "unmaintained libraries, obvious version laggers. Recommend "
            "safe upgrade paths. Note any packages you'd replace outright."
        )
        user_msg = (
            f"MANIFEST:\n{requirements}\n\n"
            f"USER CONTEXT:\n{context_block or '(none)'}\n\n"
            f"RECENT ADVISORIES:\n{web_context or '(unavailable)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=800,
        )
        return response.text
