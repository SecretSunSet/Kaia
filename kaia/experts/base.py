"""Deprecated — use `agent_runtime.BaseAgent` directly going forward.

Kept as a compatibility shim during the BaseExpert → BaseAgent migration
(R-1). The full class implementation lives in `agent_runtime.base_agent`.
All existing imports `from experts.base import BaseExpert` continue to
resolve to the same class.

Schedule for removal: after R-5 ships (full agent mesh deployed).
"""

from __future__ import annotations

from agent_runtime.base_agent import BaseAgent as BaseExpert

__all__ = ["BaseExpert"]
