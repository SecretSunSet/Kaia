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
    ForumTopicMapping,
    FinancialGoal,
    RecurringBill,
    TechProject,
    TechSkill,
    LearningLogEntry,
    CodeReview,
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


# ── Forum topic mappings ───────────────────────────────────────────

def _row_to_forum_mapping(row: dict) -> ForumTopicMapping:
    """Convert a Supabase row dict to a ForumTopicMapping dataclass."""
    return ForumTopicMapping(
        id=row["id"],
        chat_id=int(row["chat_id"]),
        channel_id=row["channel_id"],
        topic_id=int(row["topic_id"]),
        created_at=row.get("created_at"),
    )


async def save_forum_topic_mapping(
    chat_id: int, channel_id: str, topic_id: int
) -> None:
    """Upsert a (chat_id, channel_id) → topic_id mapping."""
    sb = get_supabase()
    sb.table("forum_topic_mappings").upsert(
        {
            "chat_id": chat_id,
            "channel_id": channel_id,
            "topic_id": topic_id,
        },
        on_conflict="chat_id,channel_id",
    ).execute()


async def get_forum_topic_mappings(chat_id: int) -> list[ForumTopicMapping]:
    """Return all topic mappings for a forum group chat."""
    sb = get_supabase()
    result = (
        sb.table("forum_topic_mappings")
        .select("*")
        .eq("chat_id", chat_id)
        .execute()
    )
    return [_row_to_forum_mapping(r) for r in result.data]


async def get_forum_mapping_by_topic(
    chat_id: int, topic_id: int
) -> ForumTopicMapping | None:
    """Find the channel_id mapped to a given topic in a chat."""
    sb = get_supabase()
    result = (
        sb.table("forum_topic_mappings")
        .select("*")
        .eq("chat_id", chat_id)
        .eq("topic_id", topic_id)
        .execute()
    )
    if not result.data:
        return None
    return _row_to_forum_mapping(result.data[0])


async def get_forum_mapping_by_channel(
    chat_id: int, channel_id: str
) -> ForumTopicMapping | None:
    """Find the topic_id for a given channel in a chat."""
    sb = get_supabase()
    result = (
        sb.table("forum_topic_mappings")
        .select("*")
        .eq("chat_id", chat_id)
        .eq("channel_id", channel_id)
        .execute()
    )
    if not result.data:
        return None
    return _row_to_forum_mapping(result.data[0])


async def delete_forum_topic_mappings(chat_id: int) -> None:
    """Delete all topic mappings for a chat (used when tearing down)."""
    sb = get_supabase()
    sb.table("forum_topic_mappings").delete().eq("chat_id", chat_id).execute()


# ── Financial goals (Hevn — Phase CH-2) ────────────────────────────

def _row_to_financial_goal(row: dict) -> FinancialGoal:
    """Convert a Supabase row dict to a FinancialGoal dataclass."""
    deadline_val = row.get("deadline")
    monthly = row.get("monthly_contribution")
    return FinancialGoal(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        target_amount=Decimal(str(row["target_amount"])),
        current_amount=Decimal(str(row.get("current_amount") or 0)),
        monthly_contribution=Decimal(str(monthly)) if monthly is not None else None,
        deadline=date.fromisoformat(deadline_val) if deadline_val else None,
        priority=row.get("priority", 1),
        status=row.get("status", "active"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


async def create_financial_goal(
    user_id: str,
    name: str,
    target_amount: float,
    deadline: str | None = None,
    monthly_contribution: float | None = None,
    priority: int = 1,
) -> FinancialGoal:
    """Insert a new financial goal and return it."""
    sb = get_supabase()
    data: dict = {
        "user_id": user_id,
        "name": name,
        "target_amount": target_amount,
        "priority": priority,
    }
    if deadline:
        data["deadline"] = deadline
    if monthly_contribution is not None:
        data["monthly_contribution"] = monthly_contribution
    result = sb.table("financial_goals").insert(data).execute()
    return _row_to_financial_goal(result.data[0])


async def get_financial_goals(
    user_id: str, status: str | None = "active"
) -> list[FinancialGoal]:
    """Return financial goals for a user (optionally filtered by status)."""
    sb = get_supabase()
    query = sb.table("financial_goals").select("*").eq("user_id", user_id)
    if status:
        query = query.eq("status", status)
    result = query.order("priority").execute()
    return [_row_to_financial_goal(r) for r in result.data]


async def get_financial_goal_by_id(goal_id: str) -> FinancialGoal | None:
    """Fetch a single goal by ID."""
    sb = get_supabase()
    result = sb.table("financial_goals").select("*").eq("id", goal_id).execute()
    if not result.data:
        return None
    return _row_to_financial_goal(result.data[0])


async def update_financial_goal(goal_id: str, **fields: object) -> None:
    """Update arbitrary fields on a financial goal."""
    if not fields:
        return
    sb = get_supabase()
    payload = dict(fields)
    payload["updated_at"] = datetime.utcnow().isoformat()
    sb.table("financial_goals").update(payload).eq("id", goal_id).execute()


async def delete_financial_goal(goal_id: str) -> None:
    """Delete a financial goal by ID."""
    sb = get_supabase()
    sb.table("financial_goals").delete().eq("id", goal_id).execute()


# ── Recurring bills (Hevn — Phase CH-2) ────────────────────────────

def _row_to_recurring_bill(row: dict) -> RecurringBill:
    """Convert a Supabase row dict to a RecurringBill dataclass."""
    last_paid_val = row.get("last_paid")
    return RecurringBill(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        amount=Decimal(str(row["amount"])),
        category=row.get("category"),
        due_day=row.get("due_day"),
        recurrence=row.get("recurrence", "monthly"),
        is_active=row.get("is_active", True),
        last_paid=date.fromisoformat(last_paid_val) if last_paid_val else None,
        notes=row.get("notes"),
        created_at=row.get("created_at"),
    )


async def create_recurring_bill(
    user_id: str,
    name: str,
    amount: float,
    due_day: int | None = None,
    category: str | None = None,
    recurrence: str = "monthly",
    notes: str | None = None,
) -> RecurringBill:
    """Insert a new recurring bill and return it."""
    sb = get_supabase()
    data: dict = {
        "user_id": user_id,
        "name": name,
        "amount": amount,
        "recurrence": recurrence,
    }
    if due_day is not None:
        data["due_day"] = due_day
    if category:
        data["category"] = category
    if notes:
        data["notes"] = notes
    result = sb.table("recurring_bills").insert(data).execute()
    return _row_to_recurring_bill(result.data[0])


async def get_recurring_bills(
    user_id: str, active_only: bool = True
) -> list[RecurringBill]:
    """Return recurring bills for a user."""
    sb = get_supabase()
    query = sb.table("recurring_bills").select("*").eq("user_id", user_id)
    if active_only:
        query = query.eq("is_active", True)
    result = query.order("due_day").execute()
    return [_row_to_recurring_bill(r) for r in result.data]


async def update_recurring_bill(bill_id: str, **fields: object) -> None:
    """Update arbitrary fields on a recurring bill."""
    if not fields:
        return
    sb = get_supabase()
    sb.table("recurring_bills").update(dict(fields)).eq("id", bill_id).execute()


async def delete_recurring_bill(bill_id: str) -> None:
    """Delete a recurring bill by ID."""
    sb = get_supabase()
    sb.table("recurring_bills").delete().eq("id", bill_id).execute()


async def get_recurring_bill_by_id(bill_id: str) -> RecurringBill | None:
    """Fetch a single recurring bill by ID."""
    sb = get_supabase()
    result = sb.table("recurring_bills").select("*").eq("id", bill_id).execute()
    if not result.data:
        return None
    return _row_to_recurring_bill(result.data[0])


# ── Tech projects (MakubeX — Phase CH-3) ───────────────────────────

def _row_to_tech_project(row: dict) -> TechProject:
    """Convert a Supabase row dict to a TechProject dataclass."""
    started_val = row.get("started_at")
    stack = row.get("tech_stack") or []
    if isinstance(stack, str):
        import json as _json
        try:
            stack = _json.loads(stack)
        except Exception:
            stack = []
    return TechProject(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        description=row.get("description"),
        tech_stack=stack,
        status=row.get("status", "active"),
        repo_url=row.get("repo_url"),
        notes=row.get("notes"),
        priority=row.get("priority", 1),
        started_at=date.fromisoformat(started_val) if started_val else None,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


async def create_tech_project(
    user_id: str,
    name: str,
    description: str | None = None,
    tech_stack: list[str] | None = None,
    repo_url: str | None = None,
    notes: str | None = None,
    priority: int = 1,
    started_at: str | None = None,
) -> TechProject:
    """Insert a new tech project and return it."""
    sb = get_supabase()
    data: dict = {
        "user_id": user_id,
        "name": name,
        "priority": priority,
    }
    if description:
        data["description"] = description
    if tech_stack:
        data["tech_stack"] = tech_stack
    if repo_url:
        data["repo_url"] = repo_url
    if notes:
        data["notes"] = notes
    if started_at:
        data["started_at"] = started_at
    result = sb.table("tech_projects").insert(data).execute()
    return _row_to_tech_project(result.data[0])


async def get_tech_projects(
    user_id: str, status: str | None = "active"
) -> list[TechProject]:
    """Return tech projects for a user (optionally filtered by status)."""
    sb = get_supabase()
    query = sb.table("tech_projects").select("*").eq("user_id", user_id)
    if status:
        query = query.eq("status", status)
    result = query.order("priority").execute()
    return [_row_to_tech_project(r) for r in result.data]


async def get_tech_project_by_id(project_id: str) -> TechProject | None:
    """Fetch a single tech project by ID."""
    sb = get_supabase()
    result = sb.table("tech_projects").select("*").eq("id", project_id).execute()
    if not result.data:
        return None
    return _row_to_tech_project(result.data[0])


async def get_tech_project_by_name(
    user_id: str, name: str
) -> TechProject | None:
    """Fetch a tech project by (user_id, name), case-insensitive."""
    sb = get_supabase()
    result = (
        sb.table("tech_projects")
        .select("*")
        .eq("user_id", user_id)
        .ilike("name", name)
        .execute()
    )
    if not result.data:
        return None
    return _row_to_tech_project(result.data[0])


async def update_tech_project(project_id: str, **fields: object) -> None:
    """Update arbitrary fields on a tech project."""
    if not fields:
        return
    sb = get_supabase()
    payload = dict(fields)
    payload["updated_at"] = datetime.utcnow().isoformat()
    sb.table("tech_projects").update(payload).eq("id", project_id).execute()


async def delete_tech_project(project_id: str) -> None:
    """Delete a tech project by ID."""
    sb = get_supabase()
    sb.table("tech_projects").delete().eq("id", project_id).execute()


# ── Tech skills (MakubeX — Phase CH-3) ─────────────────────────────

def _row_to_tech_skill(row: dict) -> TechSkill:
    """Convert a Supabase row dict to a TechSkill dataclass."""
    last_used_val = row.get("last_used")
    return TechSkill(
        id=row["id"],
        user_id=row["user_id"],
        skill=row["skill"],
        level=row.get("level", "beginner"),
        last_used=date.fromisoformat(last_used_val) if last_used_val else None,
        notes=row.get("notes"),
        updated_at=row.get("updated_at"),
    )


async def upsert_tech_skill(
    user_id: str,
    skill: str,
    level: str = "beginner",
    last_used: str | None = None,
    notes: str | None = None,
) -> TechSkill:
    """Insert or update a user's skill level."""
    sb = get_supabase()
    data: dict = {
        "user_id": user_id,
        "skill": skill,
        "level": level,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if last_used:
        data["last_used"] = last_used
    if notes:
        data["notes"] = notes
    result = sb.table("tech_skills").upsert(
        data, on_conflict="user_id,skill"
    ).execute()
    return _row_to_tech_skill(result.data[0])


async def get_tech_skills(user_id: str) -> list[TechSkill]:
    """Return all tracked skills for a user."""
    sb = get_supabase()
    result = (
        sb.table("tech_skills")
        .select("*")
        .eq("user_id", user_id)
        .order("skill")
        .execute()
    )
    return [_row_to_tech_skill(r) for r in result.data]


async def get_tech_skill(user_id: str, skill: str) -> TechSkill | None:
    """Fetch a single skill entry."""
    sb = get_supabase()
    result = (
        sb.table("tech_skills")
        .select("*")
        .eq("user_id", user_id)
        .eq("skill", skill)
        .execute()
    )
    if not result.data:
        return None
    return _row_to_tech_skill(result.data[0])


# ── Learning log (MakubeX — Phase CH-3) ────────────────────────────

def _row_to_learning_log(row: dict) -> LearningLogEntry:
    """Convert a Supabase row dict to a LearningLogEntry dataclass."""
    return LearningLogEntry(
        id=row["id"],
        user_id=row["user_id"],
        topic=row["topic"],
        category=row.get("category"),
        depth=row.get("depth", "intro"),
        taught_at=row.get("taught_at"),
        notes=row.get("notes"),
    )


async def add_learning_log(
    user_id: str,
    topic: str,
    category: str | None = None,
    depth: str = "intro",
    notes: str | None = None,
) -> LearningLogEntry:
    """Record a taught topic. Returns the created entry."""
    sb = get_supabase()
    data: dict = {
        "user_id": user_id,
        "topic": topic,
        "depth": depth,
    }
    if category:
        data["category"] = category
    if notes:
        data["notes"] = notes
    result = sb.table("learning_log").insert(data).execute()
    return _row_to_learning_log(result.data[0])


async def get_learning_log(
    user_id: str, limit: int = 50
) -> list[LearningLogEntry]:
    """Return the most recent learning log entries for a user."""
    sb = get_supabase()
    result = (
        sb.table("learning_log")
        .select("*")
        .eq("user_id", user_id)
        .order("taught_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [_row_to_learning_log(r) for r in result.data]


async def get_learning_log_for_topic(
    user_id: str, topic: str
) -> list[LearningLogEntry]:
    """Return all entries for a specific topic (used to judge depth progression)."""
    sb = get_supabase()
    result = (
        sb.table("learning_log")
        .select("*")
        .eq("user_id", user_id)
        .eq("topic", topic)
        .order("taught_at", desc=True)
        .execute()
    )
    return [_row_to_learning_log(r) for r in result.data]


# ── Code reviews (MakubeX — Phase CH-3) ────────────────────────────

def _row_to_code_review(row: dict) -> CodeReview:
    """Convert a Supabase row dict to a CodeReview dataclass."""
    issues = row.get("issues_found") or []
    if isinstance(issues, str):
        import json as _json
        try:
            issues = _json.loads(issues)
        except Exception:
            issues = []
    return CodeReview(
        id=row["id"],
        user_id=row["user_id"],
        snippet_hash=row.get("snippet_hash"),
        language=row.get("language"),
        summary=row.get("summary"),
        issues_found=issues,
        created_at=row.get("created_at"),
    )


async def save_code_review(
    user_id: str,
    snippet_hash: str,
    language: str | None,
    summary: str,
    issues_found: list[dict],
) -> CodeReview:
    """Record a completed code review."""
    sb = get_supabase()
    result = sb.table("code_reviews").insert(
        {
            "user_id": user_id,
            "snippet_hash": snippet_hash,
            "language": language,
            "summary": summary,
            "issues_found": issues_found,
        }
    ).execute()
    return _row_to_code_review(result.data[0])


async def get_code_review_by_hash(
    user_id: str, snippet_hash: str
) -> CodeReview | None:
    """Find a previous review for the same snippet hash (dedup)."""
    sb = get_supabase()
    result = (
        sb.table("code_reviews")
        .select("*")
        .eq("user_id", user_id)
        .eq("snippet_hash", snippet_hash)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return _row_to_code_review(result.data[0])


async def get_recent_code_reviews(
    user_id: str, limit: int = 10
) -> list[CodeReview]:
    """Return the most recent code reviews for a user."""
    sb = get_supabase()
    result = (
        sb.table("code_reviews")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [_row_to_code_review(r) for r in result.data]
