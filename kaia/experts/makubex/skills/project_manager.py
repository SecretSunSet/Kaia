"""Project manager skill — CRUD over tech projects + contextual summaries."""

from __future__ import annotations

from datetime import date

from loguru import logger

from core.ai_engine import AIEngine
from database import queries as db
from database.models import TechProject


_STATUS_EMOJI = {
    "active": "🟢",
    "paused": "⏸️",
    "completed": "✅",
    "archived": "📦",
}


class ProjectManagerSkill:
    """Track the user's active tech projects."""

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine

    async def create_project(
        self,
        user_id: str,
        name: str,
        description: str | None = None,
        tech_stack: list[str] | None = None,
        repo_url: str | None = None,
        priority: int = 2,
    ) -> TechProject:
        """Add a new project (or return the existing one by name)."""
        existing = await db.get_tech_project_by_name(user_id, name)
        if existing is not None:
            return existing
        project = await db.create_tech_project(
            user_id=user_id,
            name=name,
            description=description,
            tech_stack=tech_stack,
            repo_url=repo_url,
            priority=priority,
            started_at=date.today().isoformat(),
        )
        return project

    async def list_projects(
        self,
        user_id: str,
        status: str | None = "active",
    ) -> list[TechProject]:
        """Get projects for the user."""
        return await db.get_tech_projects(user_id, status=status)

    async def update_project(
        self,
        user_id: str,
        project_id: str,
        updates: dict,
    ) -> TechProject | None:
        """Update project fields; returns the refreshed project."""
        project = await db.get_tech_project_by_id(project_id)
        if project is None or project.user_id != user_id:
            return None

        allowed = {
            "name", "description", "tech_stack", "status", "repo_url",
            "notes", "priority", "started_at",
        }
        payload = {k: v for k, v in updates.items() if k in allowed}
        if not payload:
            return project
        await db.update_tech_project(project_id, **payload)
        return await db.get_tech_project_by_id(project_id)

    async def project_summary(
        self,
        user_id: str,
        project_id: str,
    ) -> str:
        """Full summary of a project."""
        project = await db.get_tech_project_by_id(project_id)
        if project is None or project.user_id != user_id:
            return "Project not found."
        return self._format_detail(project)

    async def suggest_next_step(
        self,
        user_id: str,
        project_id: str,
        context_block: str = "",
    ) -> str:
        """Given a project's state, suggest what to work on next."""
        project = await db.get_tech_project_by_id(project_id)
        if project is None or project.user_id != user_id:
            return "Project not found."

        system = (
            "You are MakubeX suggesting the next concrete step on a "
            "project. Base the suggestion on the project's stack, notes, "
            "and status. Be specific — name a file, function, or task, "
            "not a vague direction. One paragraph, max."
        )
        user_msg = (
            f"PROJECT:\n{self._format_detail(project)}\n\n"
            f"USER CONTEXT:\n{context_block or '(none)'}"
        )
        try:
            response = await self.ai.chat(
                system_prompt=system,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=400,
            )
            return response.text
        except Exception as exc:
            logger.debug("suggest_next_step failed: {}", exc)
            return "Couldn't generate a suggestion right now."

    # ── Formatters ────────────────────────────────────────────────────

    def format_projects_list(self, projects: list[TechProject]) -> str:
        """Format a project list for Telegram."""
        if not projects:
            return (
                "🔧 No projects tracked yet.\n\n"
                "Tell me what you're building — e.g. "
                "'Add a new project: KAIA bot in Python / FastAPI / Supabase.'"
            )
        lines = ["🔧 *Your Tech Projects*", ""]
        for i, p in enumerate(projects, start=1):
            emoji = _STATUS_EMOJI.get(p.status, "•")
            stack = ", ".join(p.tech_stack) if p.tech_stack else "(no stack recorded)"
            lines.append(f"{i}. {emoji} *{p.name}* — _{stack}_")
            if p.description:
                lines.append(f"   {p.description}")
            if p.repo_url:
                lines.append(f"   🔗 {p.repo_url}")
        return "\n".join(lines)

    def _format_detail(self, project: TechProject) -> str:
        emoji = _STATUS_EMOJI.get(project.status, "•")
        lines = [
            f"{emoji} *{project.name}* ({project.status})",
            f"Stack: {', '.join(project.tech_stack) if project.tech_stack else 'unknown'}",
        ]
        if project.description:
            lines.append(f"Description: {project.description}")
        if project.repo_url:
            lines.append(f"Repo: {project.repo_url}")
        if project.notes:
            lines.append(f"Notes: {project.notes}")
        if project.started_at:
            lines.append(f"Started: {project.started_at.isoformat()}")
        return "\n".join(lines)
