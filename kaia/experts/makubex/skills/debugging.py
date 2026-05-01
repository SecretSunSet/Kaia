"""Debugging skill — explain errors, walk stack traces, diagnose performance."""

from __future__ import annotations

from core.ai_engine import AIEngine


class DebuggingSkill:
    """Help troubleshoot errors, trace issues, and explain stack traces."""

    def __init__(self, ai_engine: AIEngine) -> None:
        self.ai = ai_engine

    async def debug_error(
        self,
        user_id: str,
        error_message: str,
        code_context: str | None = None,
        stack_context: str = "",
    ) -> str:
        """Given an error, explain what it means and suggest fixes.

        Uses the user's known stack (via ``stack_context``) to give
        framework-specific advice.
        """
        system = (
            "You are MakubeX debugging an error. Respond with:\n"
            "1. What the error means in plain language.\n"
            "2. The most likely cause (given the user's stack).\n"
            "3. Top 3 things to check, most likely first.\n"
            "4. A concrete fix or diagnostic command.\n"
            "Prefer framework-specific advice if the stack is known."
        )
        parts = [f"ERROR:\n{error_message}"]
        if code_context:
            parts.append(f"\nCODE CONTEXT:\n```\n{code_context}\n```")
        parts.append(f"\nUSER STACK:\n{stack_context or '(unknown)'}")
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": "\n".join(parts)}],
            max_tokens=700,
        )
        return response.text

    async def explain_stack_trace(
        self,
        user_id: str,
        trace: str,
        stack_context: str = "",
    ) -> str:
        """Walk through a stack trace and identify the root call."""
        system = (
            "You are MakubeX walking through a stack trace. "
            "Identify the root cause call (deepest user-code frame), "
            "summarise the chain that led there, and explain what likely "
            "went wrong. End with 'Root cause: ...' on its own line."
        )
        user_msg = (
            f"STACK TRACE:\n```\n{trace}\n```\n\n"
            f"USER STACK:\n{stack_context or '(unknown)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=700,
        )
        return response.text

    async def suggest_debugging_steps(
        self,
        user_id: str,
        problem: str,
        stack_context: str = "",
    ) -> str:
        """Systematic debugging plan for a vague problem."""
        system = (
            "You are MakubeX teaching a systematic debugging process for "
            "this specific problem. Output 5 numbered steps mapping to: "
            "reproduce, isolate, hypothesize, test, fix. Each step needs "
            "a concrete action — no generic 'read the docs' fluff."
        )
        user_msg = (
            f"PROBLEM:\n{problem}\n\nUSER STACK:\n{stack_context or '(unknown)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=700,
        )
        return response.text

    async def diagnose_performance(
        self,
        user_id: str,
        symptoms: str,
        stack_context: str = "",
    ) -> str:
        """Diagnose performance issues: slow queries, memory leaks, high CPU."""
        system = (
            "You are MakubeX diagnosing a performance issue. Classify the "
            "symptoms (CPU / memory / I/O / network / DB). Give the 3 most "
            "likely causes and the fastest way to confirm each. Recommend "
            "the tool (profiler, flame graph, EXPLAIN ANALYZE, etc.) that "
            "fits the user's stack."
        )
        user_msg = (
            f"SYMPTOMS:\n{symptoms}\n\nUSER STACK:\n{stack_context or '(unknown)'}"
        )
        response = await self.ai.chat(
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=700,
        )
        return response.text
