"""General chat / Q&A skill handler."""

from __future__ import annotations

from core.ai_engine import AIEngine, build_message_history
from database.models import User
from skills.base import BaseSkill, SkillResult
from skills.chat.prompts import build_chat_system_prompt


class ChatSkill(BaseSkill):
    """Handles general conversation — the default fallback skill."""

    name = "chat"

    def __init__(self, ai_engine: AIEngine) -> None:
        super().__init__(ai_engine)

    async def handle(
        self,
        user: User,
        message: str,
        conversation_history: list[dict[str, str]],
        profile_context: str,
    ) -> SkillResult:
        system_prompt = build_chat_system_prompt(profile_context)
        messages = build_message_history(conversation_history, message)

        ai_resp = await self.ai.chat(system_prompt=system_prompt, messages=messages)

        return SkillResult(
            text=ai_resp.text,
            skill_name=self.name,
            ai_response=ai_resp,
        )
