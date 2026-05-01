"""DevOps skill — infrastructure review, CI/CD, monitoring, containerisation, scaling."""

from __future__ import annotations

from core.ai_engine import AIEngine


class DevOpsSkill:
    """Server management, CI/CD, monitoring, infrastructure."""

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine

    async def review_infrastructure(
        self,
        user_id: str,
        infra_summary: str,
        context_block: str = "",
    ) -> str:
        """Review a deployment setup for best-practice gaps.

        Callers pass a concise summary of the current infra (the KAIA
        project context is available in the shared profile); MakubeX
        audits it against a standard checklist.
        """
        system = (
            "You are MakubeX auditing a deployment setup. Check:\n"
            "- Security groups / firewall rules (ingress / egress).\n"
            "- Backup strategy (snapshots, PITR, retention).\n"
            "- Monitoring + alerting (logs, metrics, on-call path).\n"
            "- Secret management (where creds live, rotation story).\n"
            "- Cost optimisation (rightsizing, idle resources).\n"
            "- Disaster recovery (RPO/RTO).\n"
            "Return a prioritised list: critical → nit. Each item with a "
            "concrete fix, not a vague 'consider X'."
        )
        user_msg = (
            f"CURRENT INFRA:\n{infra_summary}\n\n"
            f"USER CONTEXT:\n{context_block or '(none)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=900,
        )
        return response.text

    async def design_cicd(
        self,
        user_id: str,
        project: str,
        context_block: str = "",
    ) -> str:
        """Propose a CI/CD pipeline for a project."""
        system = (
            "You are MakubeX designing a CI/CD pipeline. Output:\n"
            "1. Pipeline stages (in order): lint, test, build, deploy, notify.\n"
            "2. Concrete tooling per stage, biased to the user's stack.\n"
            "3. One example config snippet (GitHub Actions YAML or "
            "equivalent).\n"
            "4. Gotchas specific to this stack.\n"
        )
        user_msg = (
            f"PROJECT: {project}\n\nUSER CONTEXT:\n{context_block or '(none)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=1000,
        )
        return response.text

    async def monitoring_setup(
        self,
        user_id: str,
        stack: str,
        context_block: str = "",
    ) -> str:
        """Recommend monitoring / logging / alerting for a stack."""
        system = (
            "You are MakubeX recommending a monitoring setup. Cover:\n"
            "- Logs (collection, storage, retention).\n"
            "- Metrics (golden signals: latency, traffic, errors, "
            "saturation).\n"
            "- Traces (if distributed).\n"
            "- Alerting channels + on-call escalation.\n"
            "Prefer affordable options for small teams. Name tools."
        )
        user_msg = f"STACK: {stack}\n\nUSER CONTEXT:\n{context_block or '(none)'}"
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=800,
        )
        return response.text

    async def containerization_advice(
        self,
        user_id: str,
        app: str,
        context_block: str = "",
    ) -> str:
        """Dockerisation advice — multi-stage builds, image size, caching."""
        system = (
            "You are MakubeX advising on containerising an app. Cover:\n"
            "- Base image choice (distroless / slim / alpine trade-offs).\n"
            "- Multi-stage build example.\n"
            "- Layer ordering for cache reuse.\n"
            "- Security (non-root user, scanning).\n"
            "- Final image size target.\n"
            "Provide a concrete Dockerfile example."
        )
        user_msg = f"APP: {app}\n\nUSER CONTEXT:\n{context_block or '(none)'}"
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=900,
        )
        return response.text

    async def scaling_advice(
        self,
        user_id: str,
        current: str,
        growth: str,
        context_block: str = "",
    ) -> str:
        """When to scale up / out, add caching, read replicas, etc."""
        system = (
            "You are MakubeX advising on scaling. Given current load and "
            "projected growth, answer: should we scale up (bigger box), "
            "scale out (more replicas), add caching (Redis/CDN), or add "
            "read replicas? Give a clear recommendation with thresholds "
            "that trigger the next step."
        )
        user_msg = (
            f"CURRENT: {current}\nGROWTH: {growth}\n\n"
            f"USER CONTEXT:\n{context_block or '(none)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=700,
        )
        return response.text
