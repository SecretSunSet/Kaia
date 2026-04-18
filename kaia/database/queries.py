"""Reusable database query functions (Supabase REST)."""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal

from loguru import logger

from database.connection import get_supabase
from database.models import (
    User,
    ProfileEntry,
    Conversation,
    Reminder,
    Transaction,
    BudgetLimit,
    Channel,
    UserChannelState,
    ChannelProfileEntry,
    ChannelConversation,
)


# ── User ─────────────────────────────────────────────────────────────

async def get_or_create_user(telegram_id: int, username: str | None = None) -> User:
    """Return existing user or create a new one."""
    sb = get_supabase()
    result = sb.table("users").select("*").eq("telegram_id", telegram_id).execute()

    if result.data:
        row = result.data[0]
        return User(
            id=row["id"],
            telegram_id=row["telegram_id"],
            username=row.get("username"),
            timezone=row.get("timezone", "Asia/Manila"),
            currency=row.get("currency", "PHP"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    # Create new user
    insert = {"telegram_id": telegram_id}
    if username:
        insert["username"] = username
    result = sb.table("users").insert(insert).execute()
    row = result.data[0]
    logger.info("Created new user: telegram_id={}", telegram_id)
    return User(
        id=row["id"],
        telegram_id=row["telegram_id"],
        username=row.get("username"),
        timezone=row.get("timezone", "Asia/Manila"),
        currency=row.get("currency", "PHP"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


# ── Profile ──────────────────────────────────────────────────────────

async def get_user_profile(user_id: str) -> list[ProfileEntry]:
    """Load the full profile for a user."""
    sb = get_supabase()
    result = sb.table("user_profile").select("*").eq("user_id", user_id).execute()
    return [
        ProfileEntry(
            id=r["id"],
            user_id=r["user_id"],
            category=r["category"],
            key=r["key"],
            value=r["value"],
            confidence=r.get("confidence", 0.5),
            source=r.get("source", "inferred"),
            updated_at=r.get("updated_at"),
        )
        for r in result.data
    ]


async def upsert_profile_entry(
    user_id: str,
    category: str,
    key: str,
    value: str,
    confidence: float = 0.5,
    source: str = "inferred",
) -> None:
    """Insert or update a single profile fact."""
    sb = get_supabase()
    sb.table("user_profile").upsert(
        {
            "user_id": user_id,
            "category": category,
            "key": key,
            "value": value,
            "confidence": confidence,
            "source": source,
            "updated_at": datetime.utcnow().isoformat(),
        },
        on_conflict="user_id,category,key",
    ).execute()


# ── Conversation history ─────────────────────────────────────────────

async def save_conversation(
    user_id: str, role: str, content: str, skill_used: str | None = None
) -> None:
    """Append a message to conversation history."""
    sb = get_supabase()
    sb.table("conversations").insert(
        {
            "user_id": user_id,
            "role": role,
            "content": content,
            "skill_used": skill_used,
        }
    ).execute()


async def get_recent_conversations(user_id: str, limit: int = 20) -> list[Conversation]:
    """Return the most recent messages for context injection."""
    sb = get_supabase()
    result = (
        sb.table("conversations")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = list(reversed(result.data))  # oldest-first for conversation context
    return [
        Conversation(
            id=r["id"],
            user_id=r["user_id"],
            role=r["role"],
            content=r["content"],
            skill_used=r.get("skill_used"),
            created_at=r.get("created_at"),
        )
        for r in rows
    ]


# ── Memory log ───────────────────────────────────────────────────────

async def add_memory_log(
    user_id: str, session_id: str, fact: str, fact_type: str = "general"
) -> None:
    """Record a learned fact."""
    sb = get_supabase()
    sb.table("memory_log").insert(
        {
            "user_id": user_id,
            "session_id": session_id,
            "fact": fact,
            "fact_type": fact_type,
        }
    ).execute()


# ── Reminders ────────────────────────────────────────────────────────

async def create_reminder(
    user_id: str,
    title: str,
    scheduled_time: str,
    recurrence: str = "none",
) -> Reminder:
    """Insert a new reminder and return it."""
    sb = get_supabase()
    result = sb.table("reminders").insert(
        {
            "user_id": user_id,
            "title": title,
            "scheduled_time": scheduled_time,
            "recurrence": recurrence,
        }
    ).execute()
    row = result.data[0]
    return _row_to_reminder(row)


async def get_active_reminders(user_id: str) -> list[Reminder]:
    """Return all active reminders for a user, ordered by scheduled time."""
    sb = get_supabase()
    result = (
        sb.table("reminders")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .order("scheduled_time")
        .execute()
    )
    return [_row_to_reminder(r) for r in result.data]


async def get_all_active_reminders() -> list[dict]:
    """Return ALL active reminders across all users (for scheduler startup).

    Returns dicts with reminder fields plus ``telegram_id`` from the users table.
    """
    sb = get_supabase()
    result = (
        sb.table("reminders")
        .select("*, users!inner(telegram_id)")
        .eq("is_active", True)
        .execute()
    )
    rows: list[dict] = []
    for r in result.data:
        reminder = _row_to_reminder(r)
        telegram_id = r["users"]["telegram_id"]
        rows.append({"reminder": reminder, "telegram_id": telegram_id})
    return rows


async def get_reminder_by_id(reminder_id: str) -> Reminder | None:
    """Fetch a single reminder by ID."""
    sb = get_supabase()
    result = sb.table("reminders").select("*").eq("id", reminder_id).execute()
    if not result.data:
        return None
    return _row_to_reminder(result.data[0])


async def update_reminder(reminder_id: str, **fields: object) -> None:
    """Update arbitrary fields on a reminder."""
    sb = get_supabase()
    sb.table("reminders").update(dict(fields)).eq("id", reminder_id).execute()


async def deactivate_reminder(reminder_id: str) -> None:
    """Mark a reminder as inactive."""
    await update_reminder(reminder_id, is_active=False)


async def get_user_for_reminder(reminder_id: str) -> User | None:
    """Get the user who owns a reminder (needed when firing)."""
    sb = get_supabase()
    result = (
        sb.table("reminders")
        .select("user_id, users!inner(telegram_id, timezone)")
        .eq("id", reminder_id)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    return User(
        id=row["user_id"],
        telegram_id=row["users"]["telegram_id"],
        timezone=row["users"].get("timezone", "Asia/Manila"),
    )


def _row_to_reminder(row: dict) -> Reminder:
    """Convert a Supabase row dict to a Reminder dataclass."""
    return Reminder(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        scheduled_time=datetime.fromisoformat(row["scheduled_time"]),
        recurrence=row.get("recurrence", "none"),
        is_active=row.get("is_active", True),
        snooze_count=row.get("snooze_count", 0),
        created_at=row.get("created_at"),
    )


# ── Transactions ────────────────────────────────────────────────────

def _row_to_transaction(row: dict) -> Transaction:
    """Convert a Supabase row dict to a Transaction dataclass."""
    return Transaction(
        id=row["id"],
        user_id=row["user_id"],
        amount=Decimal(str(row["amount"])),
        type=row["type"],
        category=row["category"],
        description=row.get("description"),
        transaction_date=date.fromisoformat(row["transaction_date"]) if row.get("transaction_date") else date.today(),
        created_at=row.get("created_at"),
    )


async def create_transaction(
    user_id: str,
    amount: float,
    type: str,
    category: str,
    description: str | None = None,
    transaction_date: str | None = None,
) -> Transaction:
    """Insert a new transaction and return it."""
    sb = get_supabase()
    data: dict = {
        "user_id": user_id,
        "amount": amount,
        "type": type,
        "category": category,
    }
    if description:
        data["description"] = description
    if transaction_date:
        data["transaction_date"] = transaction_date
    result = sb.table("transactions").insert(data).execute()
    row = result.data[0]
    return _row_to_transaction(row)


async def get_transactions(
    user_id: str,
    start_date: str,
    end_date: str,
    category: str | None = None,
) -> list[Transaction]:
    """Return transactions for a user within a date range."""
    sb = get_supabase()
    query = (
        sb.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .gte("transaction_date", start_date)
        .lte("transaction_date", end_date)
        .order("transaction_date", desc=True)
    )
    if category:
        query = query.eq("category", category)
    result = query.execute()
    return [_row_to_transaction(r) for r in result.data]


async def get_category_total(
    user_id: str,
    category: str,
    start_date: str,
    end_date: str,
) -> float:
    """Return total spending in a category for a date range."""
    sb = get_supabase()
    result = (
        sb.table("transactions")
        .select("amount")
        .eq("user_id", user_id)
        .eq("category", category)
        .eq("type", "expense")
        .gte("transaction_date", start_date)
        .lte("transaction_date", end_date)
        .execute()
    )
    return sum(float(r["amount"]) for r in result.data)


async def get_spending_by_category(
    user_id: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Return expense totals grouped by category for a date range.

    Returns a list of dicts: [{"category": "food", "total": 5200.0}, ...]
    sorted by total descending.
    """
    sb = get_supabase()
    result = (
        sb.table("transactions")
        .select("category, amount")
        .eq("user_id", user_id)
        .eq("type", "expense")
        .gte("transaction_date", start_date)
        .lte("transaction_date", end_date)
        .execute()
    )
    totals: dict[str, float] = {}
    for r in result.data:
        cat = r["category"]
        totals[cat] = totals.get(cat, 0.0) + float(r["amount"])
    return sorted(
        [{"category": c, "total": t} for c, t in totals.items()],
        key=lambda x: x["total"],
        reverse=True,
    )


async def get_income_total(
    user_id: str,
    start_date: str,
    end_date: str,
) -> float:
    """Return total income for a date range."""
    sb = get_supabase()
    result = (
        sb.table("transactions")
        .select("amount")
        .eq("user_id", user_id)
        .eq("type", "income")
        .gte("transaction_date", start_date)
        .lte("transaction_date", end_date)
        .execute()
    )
    return sum(float(r["amount"]) for r in result.data)


async def get_expense_total(
    user_id: str,
    start_date: str,
    end_date: str,
) -> float:
    """Return total expenses for a date range."""
    sb = get_supabase()
    result = (
        sb.table("transactions")
        .select("amount")
        .eq("user_id", user_id)
        .eq("type", "expense")
        .gte("transaction_date", start_date)
        .lte("transaction_date", end_date)
        .execute()
    )
    return sum(float(r["amount"]) for r in result.data)


async def get_last_transaction(user_id: str) -> Transaction | None:
    """Return the most recently created transaction for a user."""
    sb = get_supabase()
    result = (
        sb.table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return _row_to_transaction(result.data[0])


async def delete_transaction(transaction_id: str) -> None:
    """Delete a transaction by ID."""
    sb = get_supabase()
    sb.table("transactions").delete().eq("id", transaction_id).execute()


# ── Budget Limits ───────────────────────────────────────────────────

def _row_to_budget_limit(row: dict) -> BudgetLimit:
    """Convert a Supabase row dict to a BudgetLimit dataclass."""
    return BudgetLimit(
        id=row["id"],
        user_id=row["user_id"],
        category=row["category"],
        monthly_limit=Decimal(str(row["monthly_limit"])),
        is_active=row.get("is_active", True),
    )


async def create_or_update_budget_limit(
    user_id: str,
    category: str,
    monthly_limit: float,
) -> BudgetLimit:
    """Upsert a budget limit for a category."""
    sb = get_supabase()
    result = sb.table("budget_limits").upsert(
        {
            "user_id": user_id,
            "category": category,
            "monthly_limit": monthly_limit,
            "is_active": True,
        },
        on_conflict="user_id,category",
    ).execute()
    row = result.data[0]
    return _row_to_budget_limit(row)


async def get_budget_limits(user_id: str) -> list[BudgetLimit]:
    """Return all active budget limits for a user."""
    sb = get_supabase()
    result = (
        sb.table("budget_limits")
        .select("*")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    )
    return [_row_to_budget_limit(r) for r in result.data]


async def get_budget_limit(user_id: str, category: str) -> BudgetLimit | None:
    """Return the budget limit for a specific category."""
    sb = get_supabase()
    result = (
        sb.table("budget_limits")
        .select("*")
        .eq("user_id", user_id)
        .eq("category", category)
        .eq("is_active", True)
        .execute()
    )
    if not result.data:
        return None
    return _row_to_budget_limit(result.data[0])


async def deactivate_budget_limit(user_id: str, category: str) -> None:
    """Deactivate a budget limit for a category."""
    sb = get_supabase()
    sb.table("budget_limits").update({"is_active": False}).eq(
        "user_id", user_id
    ).eq("category", category).execute()


# ── Channel state ───────────────────────────────────────────────────

def _row_to_channel(row: dict) -> Channel:
    """Convert a Supabase row dict to a Channel dataclass."""
    return Channel(
        channel_id=row["channel_id"],
        name=row["name"],
        character_name=row["character_name"],
        role=row["role"],
        personality=row["personality"],
        system_prompt=row["system_prompt"],
        emoji=row.get("emoji", ""),
        is_active=row.get("is_active", True),
        created_at=row.get("created_at"),
    )


async def get_user_channel_state(user_id: str) -> str:
    """Return the user's active channel_id, or 'general' if none set."""
    sb = get_supabase()
    result = (
        sb.table("user_channel_state")
        .select("active_channel")
        .eq("user_id", user_id)
        .execute()
    )
    if result.data:
        return result.data[0]["active_channel"]
    return "general"


async def set_user_channel_state(user_id: str, channel_id: str) -> None:
    """Upsert the user's active channel."""
    sb = get_supabase()
    sb.table("user_channel_state").upsert(
        {
            "user_id": user_id,
            "active_channel": channel_id,
            "switched_at": datetime.utcnow().isoformat(),
        },
        on_conflict="user_id",
    ).execute()


async def get_channel_by_id(channel_id: str) -> Channel | None:
    """Fetch a single channel definition."""
    sb = get_supabase()
    result = (
        sb.table("channels")
        .select("*")
        .eq("channel_id", channel_id)
        .eq("is_active", True)
        .execute()
    )
    if not result.data:
        return None
    return _row_to_channel(result.data[0])


async def get_all_active_channels() -> list[Channel]:
    """Return all active channel definitions."""
    sb = get_supabase()
    result = (
        sb.table("channels")
        .select("*")
        .eq("is_active", True)
        .order("channel_id")
        .execute()
    )
    return [_row_to_channel(r) for r in result.data]


# ── Channel profile (per-channel memory) ───────────────────────────

async def get_channel_profile(
    user_id: str, channel_id: str
) -> list[ChannelProfileEntry]:
    """Load all channel-specific profile entries for a user + channel."""
    sb = get_supabase()
    result = (
        sb.table("channel_profile")
        .select("*")
        .eq("user_id", user_id)
        .eq("channel_id", channel_id)
        .execute()
    )
    return [
        ChannelProfileEntry(
            id=r["id"],
            user_id=r["user_id"],
            channel_id=r["channel_id"],
            category=r["category"],
            key=r["key"],
            value=r["value"],
            confidence=r.get("confidence", 0.5),
            source=r.get("source", "inferred"),
            updated_at=r.get("updated_at"),
        )
        for r in result.data
    ]


async def upsert_channel_profile(
    user_id: str,
    channel_id: str,
    category: str,
    key: str,
    value: str,
    confidence: float = 0.5,
    source: str = "inferred",
) -> None:
    """Insert or update a channel-specific profile fact."""
    sb = get_supabase()
    sb.table("channel_profile").upsert(
        {
            "user_id": user_id,
            "channel_id": channel_id,
            "category": category,
            "key": key,
            "value": value,
            "confidence": confidence,
            "source": source,
            "updated_at": datetime.utcnow().isoformat(),
        },
        on_conflict="user_id,channel_id,category,key",
    ).execute()


async def delete_channel_profile_entry(
    user_id: str, channel_id: str, category: str, key: str
) -> None:
    """Delete a specific channel profile entry."""
    sb = get_supabase()
    (
        sb.table("channel_profile")
        .delete()
        .eq("user_id", user_id)
        .eq("channel_id", channel_id)
        .eq("category", category)
        .eq("key", key)
        .execute()
    )


# ── Channel conversations ──────────────────────────────────────────

async def save_channel_conversation(
    user_id: str, channel_id: str, role: str, content: str
) -> None:
    """Append a message to channel-specific conversation history."""
    sb = get_supabase()
    sb.table("channel_conversations").insert(
        {
            "user_id": user_id,
            "channel_id": channel_id,
            "role": role,
            "content": content,
        }
    ).execute()


async def get_channel_conversations(
    user_id: str, channel_id: str, limit: int = 20
) -> list[ChannelConversation]:
    """Return the most recent channel messages, oldest-first."""
    sb = get_supabase()
    result = (
        sb.table("channel_conversations")
        .select("*")
        .eq("user_id", user_id)
        .eq("channel_id", channel_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = list(reversed(result.data))  # oldest-first for conversation context
    return [
        ChannelConversation(
            id=r["id"],
            user_id=r["user_id"],
            channel_id=r["channel_id"],
            role=r["role"],
            content=r["content"],
            created_at=r.get("created_at"),
        )
        for r in rows
    ]


async def count_channel_conversations(user_id: str, channel_id: str) -> int:
    """Return count of messages in a channel for a user."""
    sb = get_supabase()
    result = (
        sb.table("channel_conversations")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("channel_id", channel_id)
        .execute()
    )
    return result.count or 0
