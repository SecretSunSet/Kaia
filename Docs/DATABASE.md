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

---

## Forum Topics Table (Migration 003)

### `forum_topic_mappings`

Maps Telegram forum-group topics to expert channels. One row per `(chat_id, channel_id)` pair; one row per `(chat_id, topic_id)` pair.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `chat_id` | BIGINT | Telegram group chat ID |
| `channel_id` | VARCHAR(50) | Expert channel ID (`hevn`, `kazuki`, …) |
| `topic_id` | BIGINT | `message_thread_id` of the topic in that group |
| `created_at` | TIMESTAMPTZ | — |

Unique constraints: `(chat_id, channel_id)` and `(chat_id, topic_id)`.

Indexed on `chat_id`. RLS enabled with `service_role_all` policy, matching the other tables.

---

## Hevn Tables (Migration 004)

### `financial_goals`

Per-user financial goals owned by Hevn.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID | FK → users (ON DELETE CASCADE) |
| `name` | VARCHAR(100) | e.g., `"Emergency Fund"` |
| `target_amount` | DECIMAL(12,2) | Target peso amount |
| `current_amount` | DECIMAL(12,2) | Progress so far (default 0) |
| `monthly_contribution` | DECIMAL(12,2) | Planned monthly contribution (nullable) |
| `deadline` | DATE | Optional target date |
| `priority` | INT | 1 (high) — 3 (low); default 1 |
| `status` | VARCHAR(20) | `active` / `paused` / `completed` |
| `created_at` | TIMESTAMPTZ | — |
| `updated_at` | TIMESTAMPTZ | — |

Indexed on `(user_id, status)`.

### `recurring_bills`

Per-user recurring bills and subscriptions tracked by Hevn.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID | FK → users (ON DELETE CASCADE) |
| `name` | VARCHAR(100) | e.g., `"Netflix"` |
| `amount` | DECIMAL(12,2) | Peso amount per charge |
| `category` | VARCHAR(50) | `"subscriptions"`, `"utilities"`, etc. |
| `due_day` | INT | 1–31 (nullable for non-monthly) |
| `recurrence` | VARCHAR(20) | `monthly` / `weekly` / `yearly` / `quarterly` |
| `is_active` | BOOLEAN | Default `TRUE` |
| `last_paid` | DATE | Updated by `mark_paid` |
| `notes` | TEXT | — |
| `created_at` | TIMESTAMPTZ | — |

Indexed on `(user_id, is_active)`. Both tables have RLS enabled with the standard `service_role_all` policy.

### Cross-channel hand-off

Hevn's extractor mirrors major financial facts (categories `income_info`, `debt_info`, `savings`, `retirement`, `insurance`, `goals`) from `channel_profile` to the shared `user_profile` table under category `"finances"` — so other experts (notably Kazuki in CH-4) can read the user's financial baseline.
