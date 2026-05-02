"""MakubeX — the Tech Lead / CTO expert."""

from __future__ import annotations

import asyncio

from loguru import logger

from core.ai_engine import AIEngine, build_message_history
from database import queries as db
from database.models import Channel, User
from experts.base import BaseExpert
from experts.makubex.extractor import makubex_extract_and_save
from experts.makubex.parser import (
    classify_makubex_intent,
    extract_code_block,
    parse_project_creation,
)
from experts.makubex.prompts import build_makubex_system_prompt
from experts.makubex.skills.architecture import ArchitectureSkill
from experts.makubex.skills.code_review import CodeReviewSkill
from experts.makubex.skills.debugging import DebuggingSkill
from experts.makubex.skills.devops import DevOpsSkill
from experts.makubex.skills.learning_coach import LearningCoachSkill
from experts.makubex.skills.proactive import MakubexProactiveSkill
from experts.makubex.skills.project_manager import ProjectManagerSkill
from experts.makubex.skills.security import SecuritySkill
from experts.makubex.skills.tech_research import TechResearchSkill
from skills.base import SkillResult


class MakubeXExpert(BaseExpert):
    """MakubeX — Tech Lead / CTO. Routes to 8 specialized skills + weekly brief."""

    channel_id = "makubex"

    def __init__(self, ai_engine: AIEngine) -> None:
        super().__init__(ai_engine)
        self.code_review = CodeReviewSkill(ai_engine)
        self.architecture = ArchitectureSkill(ai_engine)
        self.debugging = DebuggingSkill(ai_engine)
        self.research = TechResearchSkill(ai_engine)
        self.devops = DevOpsSkill(ai_engine)
        self.security = SecuritySkill(ai_engine)
        self.learning = LearningCoachSkill(ai_engine)
        self.projects = ProjectManagerSkill(ai_engine)
        self.proactive = MakubexProactiveSkill(ai_engine)

    # ── Main entry ──────────────────────────────────────────────────

    async def handle(
        self,
        user: User,
        message: str,
        channel: Channel,
    ) -> SkillResult:
        """Route the message through MakubeX's pipeline."""
        # First-visit onboarding
        if await self._channel_mgr.is_first_visit(user.id, channel.channel_id):
            combined_context = await self._channel_mem.load_combined_context(
                user.id, channel.channel_id
            )
            onboarding = await self.generate_onboarding(user, channel, combined_context)
            footer = self.format_response_footer(channel)
            await self.save_messages(
                user.id, channel.channel_id, message, onboarding
            )
            try:
                from core.scheduler import schedule_makubex_weekly_brief
                await schedule_makubex_weekly_brief(
                    user_id=user.id,
                    telegram_id=user.telegram_id,
                    timezone=user.timezone or "Asia/Manila",
                )
            except Exception as exc:
                logger.warning("Failed to schedule MakubeX brief: {}", exc)
            return SkillResult(
                text=f"{onboarding}{footer}",
                skill_name=channel.channel_id,
            )

        # Detect sub-intent
        intent = await classify_makubex_intent(self.ai, message)
        logger.debug("MakubeX intent: {} (user={})", intent, user.id)

        # Route to specialized skill when we can answer deterministically
        specialized_text: str | None = None
        try:
            if intent == "code_review":
                specialized_text = await self._run_code_review(user.id, message)
            elif intent == "project_manager":
                specialized_text = await self._run_project_manager(user, message)
            elif intent == "architecture":
                specialized_text = await self._run_architecture(user, message)
            elif intent == "debugging":
                specialized_text = await self._run_debugging(user, message)
            elif intent == "devops":
                specialized_text = await self._run_devops(user, message)
            elif intent == "security":
                specialized_text = await self._run_security(user, message)
            elif intent == "tech_research":
                specialized_text = await self._run_research(user, message)
            elif intent == "learning_coach":
                specialized_text = await self._run_learning(user, message)
        except Exception as exc:
            logger.warning("MakubeX specialized route '{}' failed: {}", intent, exc)
            specialized_text = None

        if specialized_text is not None:
            footer = self.format_response_footer(channel)
            full_text = f"{specialized_text}{footer}"
            await self.save_messages(user.id, channel.channel_id, message, specialized_text)
            self._fire_extraction(user.id, channel.channel_id, message, specialized_text)
            return SkillResult(text=full_text, skill_name=channel.channel_id)

        # Persona-driven response for general_chat (and fallback cases)
        ai_response = await self._persona_response(
            user=user,
            message=message,
            channel=channel,
            intent=intent,
        )
        footer = self.format_response_footer(channel)
        full_text = f"{ai_response.text}{footer}"
        await self.save_messages(
            user.id, channel.channel_id, message, ai_response.text
        )
        self._fire_extraction(user.id, channel.channel_id, message, ai_response.text)
        return SkillResult(
            text=full_text,
            skill_name=channel.channel_id,
            ai_response=ai_response,
        )

    # ── Specialized routes ──────────────────────────────────────────

    async def _run_code_review(self, user_id: str, message: str) -> str | None:
        code, lang_hint = extract_code_block(message)
        if not code:
            return None
        review = await self.code_review.review_code(user_id, code, language=lang_hint)
        return self.code_review.format_review(review)

    async def _run_project_manager(self, user: User, message: str) -> str:
        low = message.lower()

        create_markers = (
            "add a new project", "add a project", "new project",
            "create project", "register project", "track this project",
        )
        view_markers = (
            "list my projects", "show my projects", "my projects",
            "project status", "status on",
        )

        if any(m in low for m in create_markers):
            parsed = await parse_project_creation(self.ai, message)
            if parsed:
                project = await self.projects.create_project(
                    user_id=user.id,
                    name=parsed["name"],
                    description=parsed.get("description"),
                    tech_stack=parsed.get("tech_stack"),
                    repo_url=parsed.get("repo_url"),
                    priority=parsed.get("priority", 2),
                )
                stack = ", ".join(project.tech_stack) if project.tech_stack else "(stack not set)"
                return (
                    f"🔧 Project tracked: *{project.name}* — _{stack}_.\n\n"
                    f"Ask me any time: 'status on {project.name}' or "
                    f"'suggest next step for {project.name}'."
                )
            return (
                "Tell me a bit more — the project name plus the stack you're "
                "using. For example: 'Add a new project: Kaia bot in Python, "
                "FastAPI, Supabase.'"
            )

        if any(m in low for m in view_markers) or "my projects" in low:
            projects = await self.projects.list_projects(user.id, status="active")
            return self.projects.format_projects_list(projects)

        projects = await self.projects.list_projects(user.id, status="active")
        return self.projects.format_projects_list(projects)

    async def _run_architecture(self, user: User, message: str) -> str:
        context_block = await self._tech_context_block(user.id)
        low = message.lower()
        if "schema" in low or "database" in low and ("design" in low or "review" in low):
            return await self.architecture.review_schema(
                user.id, message, context_block=context_block
            )
        if "api" in low and ("design" in low or "rest" in low or "endpoint" in low):
            return await self.architecture.design_api(
                user.id, resource=message, context_block=context_block
            )
        return await self.architecture.design_system(
            user.id, requirements=message, context_block=context_block
        )

    async def _run_debugging(self, user: User, message: str) -> str:
        stack = await self._stack_string(user.id)
        low = message.lower()
        if "traceback" in low or "stack trace" in low or "at line" in low:
            return await self.debugging.explain_stack_trace(
                user.id, trace=message, stack_context=stack
            )
        if any(k in low for k in ("slow", "memory", "high cpu", "latency", "perf")):
            return await self.debugging.diagnose_performance(
                user.id, symptoms=message, stack_context=stack
            )
        return await self.debugging.debug_error(
            user.id, error_message=message, stack_context=stack
        )

    async def _run_devops(self, user: User, message: str) -> str:
        context_block = await self._tech_context_block(user.id)
        low = message.lower()
        if "docker" in low or "container" in low:
            return await self.devops.containerization_advice(
                user.id, app=message, context_block=context_block
            )
        if "ci" in low or "cd" in low or "github actions" in low or "pipeline" in low:
            return await self.devops.design_cicd(
                user.id, project=message, context_block=context_block
            )
        if "monitor" in low or "grafana" in low or "prometheus" in low or "alert" in low:
            return await self.devops.monitoring_setup(
                user.id, stack=message, context_block=context_block
            )
        if "scale" in low or "replica" in low or "cache" in low:
            return await self.devops.scaling_advice(
                user.id, current=message, growth="(not specified)",
                context_block=context_block,
            )
        return await self.devops.review_infrastructure(
            user.id, infra_summary=message, context_block=context_block
        )

    async def _run_security(self, user: User, message: str) -> str:
        context_block = await self._tech_context_block(user.id)
        low = message.lower()
        if "auth" in low or "oauth" in low or "jwt" in low:
            return await self.security.review_auth_flow(
                user.id, description=message, context_block=context_block
            )
        if "api" in low and ("secure" in low or "review" in low):
            return await self.security.check_api_security(
                user.id, api_description=message, context_block=context_block
            )
        if "secret" in low or "api key" in low or "credential" in low:
            return await self.security.secrets_best_practices(
                user.id, context_block=context_block
            )
        if "requirements.txt" in low or "package.json" in low or "dependency" in low:
            return await self.security.dependency_audit(
                user.id, requirements=message, context_block=context_block
            )
        # Fall through: audit the first active project if available, else generic.
        projects = await db.get_tech_projects(user.id, status="active")
        project_name = projects[0].name if projects else ""
        return await self.security.audit_project(
            user.id, project_name=project_name, context_block=context_block
        )

    async def _run_research(self, user: User, message: str) -> str:
        context_block = await self._tech_context_block(user.id)
        low = message.lower()

        # Try vs comparison: "X vs Y"
        if " vs " in low:
            parts = [p.strip() for p in message.split(" vs ")]
            if len(parts) >= 2:
                tools = [parts[0], parts[1]]
                return await self.research.compare_tools(
                    user.id, tools=tools, use_case=message,
                    context_block=context_block,
                )

        if "latest" in low or "new in" in low or "updates" in low:
            return await self.research.latest_on_topic(
                user.id, topic=message, context_block=context_block
            )
        if "worth" in low or "hype" in low or "adopt" in low:
            return await self.research.evaluate_trend(
                user.id, trend=message, context_block=context_block
            )
        return await self.research.recommend_tool(
            user.id, need=message, context_block=context_block
        )

    async def _run_learning(self, user: User, message: str) -> str:
        context_block = await self._tech_context_block(user.id)
        low = message.lower()

        if "study plan" in low or "learning plan" in low or "roadmap" in low:
            return await self.learning.create_study_plan(
                user.id, goal=message, weeks=8, context_block=context_block
            )
        if "quiz" in low or "test me" in low:
            return await self.learning.quiz(
                user.id, topic=message, context_block=context_block
            )
        if "what should i learn" in low or "next topic" in low:
            suggestion = await self.learning.suggest_next_topic(user.id)
            if not suggestion.get("topic"):
                return (
                    "You're in good shape on the topics I'm tracking. "
                    "Tell me what you want to level up on and I'll map a plan."
                )
            label = suggestion["topic"]
            reason = (
                "needed by an active project" if suggestion.get("project_driven")
                else "next rung up from where you are"
            )
            return f"🎯 *Next up:* {label} — {reason}."

        return await self.learning.explain_concept(
            user.id, concept=message, context_block=context_block
        )

    # ── Persona response for open-ended intents ─────────────────────

    async def _persona_response(
        self,
        user: User,
        message: str,
        channel: Channel,
        intent: str,
    ):
        """Build a MakubeX-voiced AI response with full tech context."""
        history = await self.get_conversation_history(
            user.id, channel.channel_id, user_timezone=user.timezone
        )

        active_projects = await self._format_active_projects(user.id)
        tech_skills = await self._format_tech_skills(user.id)
        recent_learning = await self._format_recent_learning(user.id)

        shared_profile = await self._shared_profile_string(user.id)
        makubex_profile = await self._channel_mem.load_channel_profile(
            user.id, channel.channel_id
        )

        channel_entries = await db.get_channel_profile(user.id, channel.channel_id)
        top_gap = self._channel_mem.get_top_gap(channel.channel_id, channel_entries)
        current_gap = top_gap["question"] if top_gap else ""

        system_prompt = build_makubex_system_prompt(
            active_projects=active_projects,
            tech_skills=tech_skills,
            recent_learning=recent_learning,
            shared_profile=shared_profile,
            makubex_profile=makubex_profile,
            current_gap=current_gap,
        )

        messages = build_message_history(history, message)
        return await self.ai.chat(system_prompt=system_prompt, messages=messages)

    # ── Context helpers ─────────────────────────────────────────────

    async def _tech_context_block(self, user_id: str) -> str:
        """Compact tech context block for specialized-skill calls."""
        projects = await db.get_tech_projects(user_id, status="active")
        skills = await db.get_tech_skills(user_id)

        parts: list[str] = []
        if projects:
            project_lines = []
            for p in projects[:5]:
                stack = ", ".join(p.tech_stack) if p.tech_stack else "(no stack set)"
                project_lines.append(f"- {p.name} ({stack})")
            parts.append("Active projects:\n" + "\n".join(project_lines))

        if skills:
            skill_lines = [f"- {s.skill}: {s.level}" for s in skills[:10]]
            parts.append("Known skills:\n" + "\n".join(skill_lines))

        return "\n\n".join(parts) if parts else "(no tech context tracked yet)"

    async def _stack_string(self, user_id: str) -> str:
        """Short description of the user's primary stack for debugging prompts."""
        projects = await db.get_tech_projects(user_id, status="active")
        stacks: list[str] = []
        for p in projects[:3]:
            if p.tech_stack:
                stacks.extend(p.tech_stack)
        if not stacks:
            skills = await db.get_tech_skills(user_id)
            stacks = [s.skill for s in skills[:6]]
        # Deduplicate preserving order
        seen: set[str] = set()
        unique = []
        for s in stacks:
            if s.lower() in seen:
                continue
            seen.add(s.lower())
            unique.append(s)
        return ", ".join(unique) if unique else "(unknown)"

    async def _format_active_projects(self, user_id: str) -> str:
        projects = await db.get_tech_projects(user_id, status="active")
        if not projects:
            return ""
        lines = []
        for p in projects[:5]:
            stack = ", ".join(p.tech_stack) if p.tech_stack else "no stack set"
            desc = f" — {p.description}" if p.description else ""
            lines.append(f"- {p.name} ({stack}){desc}")
        return "\n".join(lines)

    async def _format_tech_skills(self, user_id: str) -> str:
        skills = await db.get_tech_skills(user_id)
        if not skills:
            return ""
        return "\n".join(f"- {s.skill}: {s.level}" for s in skills[:12])

    async def _format_recent_learning(self, user_id: str) -> str:
        entries = await db.get_learning_log(user_id, limit=8)
        if not entries:
            return ""
        return "\n".join(
            f"- {e.topic.replace('_', ' ')} ({e.depth})" for e in entries
        )

    async def _shared_profile_string(self, user_id: str) -> str:
        entries = await db.get_user_profile(user_id)
        if not entries:
            return ""
        # Highlight technical facts first, then the rest compactly.
        tech = [e for e in entries if e.category == "technical"]
        other = [e for e in entries if e.category != "technical"]
        lines: list[str] = []
        for e in tech[:10]:
            lines.append(f"[TECHNICAL] {e.key}: {e.value}")
        for e in other[:6]:
            lines.append(f"[{e.category.upper()}] {e.key}: {e.value}")
        return "\n".join(lines)

    # ── Extraction hook (MakubeX-specific mirror) ───────────────────

    def _fire_extraction(
        self,
        user_id: str,
        channel_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Fire-and-forget MakubeX's extractor (includes shared profile mirror)."""
        messages = [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ]

        async def _run() -> None:
            try:
                saved = await makubex_extract_and_save(
                    ai_engine=self.ai,
                    user_id=user_id,
                    conversation_messages=messages,
                )
                if saved:
                    logger.info("MakubeX extraction: {} facts saved", saved)
            except Exception as exc:
                logger.warning("MakubeX extraction error: {}", exc)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_run())
        except RuntimeError:
            logger.warning("No running event loop for MakubeX extraction")
