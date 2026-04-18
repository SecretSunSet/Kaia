# API Reference — Expert Channel System

## Core Classes

### `ChannelManager` — `kaia/core/channel_manager.py`

Manages user channel state and switching. Stateless service class.

| Method | Returns | Description |
|--------|---------|-------------|
| `get_active_channel(user_id)` | `str` | Current channel_id or `"general"` |
| `switch_channel(user_id, channel_id)` | `Channel` | Switch + return channel info. Raises `ValueError` if channel unknown |
| `exit_channel(user_id)` | `None` | Reset to general |
| `get_channel_info(channel_id)` | `Channel \| None` | Load channel definition |
| `get_all_channels()` | `list[Channel]` | All active channels |
| `is_first_visit(user_id, channel_id)` | `bool` | True if user has zero messages in this channel |

### `ChannelMemoryManager` — `kaia/core/channel_memory.py`

Per-channel memory management and knowledge gap tracking.

| Method | Returns | Description |
|--------|---------|-------------|
| `load_channel_profile(user_id, channel_id)` | `str` | Formatted channel-specific profile |
| `load_combined_context(user_id, channel_id)` | `str` | Shared + channel profile merged |
| `update_channel_profile(...)` | `None` | Upsert one channel fact |
| `batch_update_channel_profile(user_id, channel_id, facts)` | `int` | Upsert many facts; returns saved count |
| `get_knowledge_gaps(channel_id, entries)` | `list[dict]` | Missing required knowledge, sorted by priority |
| `get_knowledge_score(channel_id, entries)` | `dict` | `{"score": int, "known": [...], "missing": [...]}` |
| `get_top_gap(channel_id, entries)` | `dict \| None` | Single highest-priority gap |

### `channel_extract_and_save()` — `kaia/core/channel_extractor.py`

Domain-focused fact extraction per channel.

```python
await channel_extract_and_save(ai_engine, user_id, channel_id, conversation_messages) -> int
```

Uses a channel-specific domain prompt (financial facts for Hevn, tech facts for MakubeX, etc.) and saves extracted facts to `channel_profile`. Returns count saved.

### `detect_expert_topic()` — `kaia/core/expert_detector.py`

Rule-based expert suggestion from general chat.

```python
detect_expert_topic(message, response, user_id=None) -> dict | None
# returns {"channel_id": "hevn", "suggestion": "..."} or None
```

Requires 2+ keyword matches to avoid false positives. Tracks per-user suggestion history to avoid nagging.

---

## Expert System

### `BaseExpert` — `kaia/experts/base.py`

Abstract base class for all expert channels.

| Method | Returns | Description |
|--------|---------|-------------|
| `handle(user, message, channel)` | `SkillResult` | **Abstract.** Process a message in this channel |
| `get_conversation_history(user_id, channel_id, limit=20)` | `list[dict]` | Recent channel messages as `[{role, content}, ...]` |
| `save_messages(user_id, channel_id, user_msg, assistant_msg)` | `None` | Save both sides of an exchange |
| `run_background_extraction(user_id, channel_id, messages)` | `None` | Fire-and-forget channel memory extraction |
| `generate_onboarding(user, channel, combined_context)` | `str` | First-visit greeting with top knowledge gap questions |
| `format_response_footer(channel)` | `str` | `"---\n💰 Hevn — Financial Advisor | /exit to return to KAIA"` |

### `PlaceholderExpert` — `kaia/experts/placeholder.py`

Default expert. Uses the channel's persona from DB with no specialized skills — all commands work immediately with in-character responses.

### Expert Registry — `kaia/experts/__init__.py`

```python
register_expert(channel_id, expert_cls) -> None
get_expert(channel_id, ai_engine) -> BaseExpert | None
```

`PlaceholderExpert` is auto-registered for all 4 non-general channels at import time. Phase CH-2+ will override these with specialized expert classes.

---

## Data Models — `kaia/database/models.py`

```python
@dataclass class Channel:
    channel_id, name, character_name, role, personality, system_prompt
    emoji="", is_active=True, created_at=None

@dataclass class UserChannelState:
    user_id, active_channel="general", id="", switched_at=None

@dataclass class ChannelProfileEntry:
    user_id, channel_id, category, key, value
    id="", confidence=0.5, source="inferred", updated_at=None

@dataclass class ChannelConversation:
    user_id, channel_id, role, content
    id="", created_at=None
```

---

## Database Query Functions — `kaia/database/queries.py`

| Function | Returns |
|----------|---------|
| `get_user_channel_state(user_id)` | `str` |
| `set_user_channel_state(user_id, channel_id)` | `None` |
| `get_channel_by_id(channel_id)` | `Channel \| None` |
| `get_all_active_channels()` | `list[Channel]` |
| `get_channel_profile(user_id, channel_id)` | `list[ChannelProfileEntry]` |
| `upsert_channel_profile(user_id, channel_id, category, key, value, confidence, source)` | `None` |
| `delete_channel_profile_entry(user_id, channel_id, category, key)` | `None` |
| `save_channel_conversation(user_id, channel_id, role, content)` | `None` |
| `get_channel_conversations(user_id, channel_id, limit=20)` | `list[ChannelConversation]` |
| `count_channel_conversations(user_id, channel_id)` | `int` |
