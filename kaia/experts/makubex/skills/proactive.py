"""MakubeX proactive alerts and weekly tech brief."""

from __future__ import annotations

from datetime import date, timedelta

from loguru import logger

from core.ai_engine import AIEngine
from database import queries as db
from skills.web_browse.search import web_search


_TIPS: tuple[str, ...] = (
    "Pin your dependency versions and audit them quarterly.",
    "Keep CI green — a red pipeline tolerated for a day becomes a week.",
    "Profile before optimising. 'Probably slow' is not a bottleneck.",
    "Put schema migrations in version control — never hand-edit prod.",
    "Secrets belong in a vault, not environment variables committed by accident.",
    "Logs should answer 'why did this request fail at 03:00?' — not 'it worked'.",
    "A small focused PR reviews faster and ships sooner than a big one.",
)


class MakubexProactiveSkill:
    """Weekly tech brief for the user."""

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine

    async def generate_weekly_brief(self, user_id: str) -> str:
        """Compile MakubeX's weekly brief."""
        today = date.today()
        projects = await db.get_tech_projects(user_id, status="active")
        skills = await db.get_tech_skills(user_id)
        learning = await db.get_learning_log(user_id, limit=10)
        recent_reviews = await db.get_recent_code_reviews(user_id, limit=3)

        lines: list[str] = [
            f"🔧 *MakubeX Weekly Brief — {today.strftime('%b %d, %Y')}*",
            "",
        ]

        if projects:
            lines.append("*Active projects:*")
            for p in projects[:5]:
                stack = ", ".join(p.tech_stack) if p.tech_stack else "no stack set"
                lines.append(f"  • {p.name} — _{stack}_")
        else:
            lines.append("*Active projects:* none tracked yet.")

        this_week = today - timedelta(days=7)
        recent_learning = [
            e for e in learning
            if _entry_date(e.taught_at) and _entry_date(e.taught_at) >= this_week
        ]
        if recent_learning:
            lines.append("")
            lines.append("*Learned this week:*")
            for e in recent_learning[:5]:
                lines.append(f"  • {e.topic.replace('_', ' ')} ({e.depth})")

        if recent_reviews:
            lines.append("")
            lines.append("*Recent code reviews:*")
            for r in recent_reviews:
                lang = r.language or "code"
                lines.append(f"  • {lang}: {(r.summary or '').strip()[:80]}")

        next_topic = await _pick_next_topic(projects, skills)
        if next_topic:
            lines.append("")
            lines.append(f"*Suggested next:* {next_topic}")

        advisories = await _security_advisories()
        if advisories:
            lines.append("")
            lines.append("*Spotted on the wire:*")
            for a in advisories[:3]:
                lines.append(f"  • {a}")

        lines.append("")
        lines.append(f"💡 _Tip:_ {_tip_of_the_week(today)}")

        return "\n".join(lines)


async def _security_advisories() -> list[str]:
    """Best-effort fetch of the latest notable security advisories."""
    try:
        results = await web_search(
            "software security advisory this week 2026", num_results=4
        )
    except Exception as exc:
        logger.debug("advisory fetch failed: {}", exc)
        return []
    items: list[str] = []
    for r in results:
        title = (r.get("title") or "").strip()
        if title:
            items.append(title[:120])
    return items


async def _pick_next_topic(projects, skills) -> str | None:
    """Pick a learning topic that would unblock active projects."""
    known = {s.skill.lower() for s in skills}
    for project in projects:
        for tech in project.tech_stack or []:
            if tech.lower() not in known:
                return f"go deeper on {tech} (needed for {project.name})"
    return None


def _entry_date(value) -> date | None:
    """Coerce a datetime-ish value to a date, or None."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        try:
            return value.date()
        except Exception:
            return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        return None


def _tip_of_the_week(today: date) -> str:
    return _TIPS[today.isocalendar().week % len(_TIPS)]
