# Database Schema

## Channel System Tables (Migration 002)

### `channels`

Expert persona definitions. Seeded with 5 rows (general, hevn, kazuki, akabane, makubex).

| Column | Type | Notes |
|--------|------|-------|
| `channel_id` | VARCHAR(50) | PK — e.g., `"hevn"` |
| `name` | VARCHAR(100) | Display name |
| `character_name` | VARCHAR(100) | In-character name |
| `role` | VARCHAR(200) | One-line role description |
| `personality` | TEXT | Personality traits |
| `system_prompt` | TEXT | Full system prompt for the AI |
| `emoji` | VARCHAR(10) | Channel emoji |
| `is_active` | BOOLEAN | Default `TRUE` |
| `created_at` | TIMESTAMPTZ | — |

### `user_channel_state`

Tracks which channel each user is currently in. No row = user is in `"general"`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID | FK → users, UNIQUE |
| `active_channel` | VARCHAR(50) | Default `"general"` |
| `switched_at` | TIMESTAMPTZ | Last switch time |

### `channel_profile`

Per-user per-channel memory facts. Separate from the shared `user_profile` table.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID | FK → users |
| `channel_id` | VARCHAR(50) | — |
| `category` | VARCHAR(50) | Domain category (e.g., `"income_info"`) |
| `key` | VARCHAR(100) | Snake_case key |
| `value` | TEXT | The fact |
| `confidence` | FLOAT | 0.0–1.0 |
| `source` | VARCHAR(20) | `"explicit"` or `"inferred"` |
| `updated_at` | TIMESTAMPTZ | — |

Unique constraint: `(user_id, channel_id, category, key)`.

### `channel_conversations`

Per-channel message history. Completely separate from the general `conversations` table.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID | FK → users |
| `channel_id` | VARCHAR(50) | — |
| `role` | VARCHAR(10) | `"user"` or `"assistant"` |
| `content` | TEXT | Message body |
| `created_at` | TIMESTAMPTZ | — |

Indexed on `(user_id, channel_id, created_at)`.

---

## Indexes

```sql
CREATE INDEX idx_user_channel_state_user ON user_channel_state(user_id);
CREATE INDEX idx_channel_profile_user_channel ON channel_profile(user_id, channel_id);
CREATE INDEX idx_channel_conversations_user_channel ON channel_conversations(user_id, channel_id, created_at);
```

## RLS Policies

All four tables have RLS enabled and a `service_role_all` policy (identical pattern to 001_initial.sql) allowing the bot's service-role key to perform all operations.

## Seed Data

5 channels inserted by the migration: `general`, `hevn`, `kazuki`, `akabane`, `makubex`. Uses `ON CONFLICT (channel_id) DO NOTHING` so re-running the migration is safe.
