"""Lightweight dataclass models mirroring the database tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal


@dataclass
class User:
    telegram_id: int
    id: str = ""
    username: str | None = None
    timezone: str = "Asia/Manila"
    currency: str = "PHP"
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ProfileEntry:
    user_id: str
    category: str
    key: str
    value: str
    id: str = ""
    confidence: float = 0.5
    source: str = "inferred"
    updated_at: datetime | None = None


@dataclass
class MemoryLogEntry:
    user_id: str
    session_id: str
    fact: str
    id: str = ""
    fact_type: str = "general"
    created_at: datetime | None = None


@dataclass
class Reminder:
    user_id: str
    title: str
    scheduled_time: datetime
    id: str = ""
    recurrence: str = "none"
    is_active: bool = True
    snooze_count: int = 0
    created_at: datetime | None = None


@dataclass
class Transaction:
    user_id: str
    amount: Decimal
    type: str  # 'income' | 'expense'
    category: str
    id: str = ""
    description: str | None = None
    transaction_date: date = field(default_factory=date.today)
    created_at: datetime | None = None


@dataclass
class Conversation:
    user_id: str
    role: str  # 'user' | 'assistant'
    content: str
    id: str = ""
    skill_used: str | None = None
    created_at: datetime | None = None


@dataclass
class BudgetLimit:
    user_id: str
    category: str
    monthly_limit: Decimal
    id: str = ""
    is_active: bool = True


# ── Channels / Expert system ────────────────────────────────────────

@dataclass
class Channel:
    channel_id: str
    name: str
    character_name: str
    role: str
    personality: str
    system_prompt: str
    emoji: str = ""
    is_active: bool = True
    created_at: datetime | None = None


@dataclass
class UserChannelState:
    user_id: str
    active_channel: str = "general"
    id: str = ""
    switched_at: datetime | None = None


@dataclass
class ChannelProfileEntry:
    user_id: str
    channel_id: str
    category: str
    key: str
    value: str
    id: str = ""
    confidence: float = 0.5
    source: str = "inferred"
    updated_at: datetime | None = None


@dataclass
class ChannelConversation:
    user_id: str
    channel_id: str
    role: str
    content: str
    id: str = ""
    created_at: datetime | None = None


@dataclass
class ForumTopicMapping:
    chat_id: int
    channel_id: str
    topic_id: int
    id: str = ""
    created_at: datetime | None = None
