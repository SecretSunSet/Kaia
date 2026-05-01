# KAIA Database Schema

**Engine:** PostgreSQL via Supabase
**Migration files:**
- `database/migrations/001_initial.sql` — users, user_profile, memory_log, reminders, transactions, conversations, budget_limits
- `database/migrations/002_channels.sql` — channels, active_channel, channel_conversations, channel_profile
- `database/migrations/003_hevn.sql` — financial_goals, bills, debts, insurance_policies, retirement_accounts
- `database/migrations/004_forum.sql` — forum topic ↔ channel mappings
- `database/migrations/005_makubex.sql` — tech_projects, tech_skills, learning_log, code_reviews

---

## Tables

### `users`

Registered Telegram users.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key |
| `telegram_id` | BIGINT | NO | — | Telegram user ID (unique) |
| `username` | VARCHAR(100) | YES | — | Telegram username |
| `timezone` | VARCHAR(50) | YES | `'Asia/Manila'` | User timezone |
| `currency` | VARCHAR(10) | YES | `'PHP'` | Preferred currency |
| `created_at` | TIMESTAMPTZ | YES | `NOW()` | Account creation |
| `updated_at` | TIMESTAMPTZ | YES | `NOW()` | Last update |

**Constraints:** `UNIQUE(telegram_id)`

---

### `user_profile`

Evolving AI-generated user profile. Core of the memory system.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | YES | — | FK → `users(id)` ON DELETE CASCADE |
| `category` | VARCHAR(50) | NO | — | Profile category (see below) |
| `key` | VARCHAR(100) | NO | — | Fact name |
| `value` | TEXT | NO | — | Fact value |
| `confidence` | FLOAT | YES | `0.5` | AI confidence score (0.0–1.0) |
| `source` | VARCHAR(20) | YES | `'inferred'` | `'explicit'` or `'inferred'` |
| `updated_at` | TIMESTAMPTZ | YES | `NOW()` | Last update |

**Constraints:** `UNIQUE(user_id, category, key)` — upserts update existing facts.

**Category values:** `identity`, `health`, `finances`, `technical`, `personality`, `preferences`, `goals`, `patterns`

---

### `memory_log`

Timestamped log of facts learned per conversation session.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | YES | — | FK → `users(id)` ON DELETE CASCADE |
| `session_id` | VARCHAR(50) | NO | — | Groups facts from one conversation |
| `fact` | TEXT | NO | — | The learned fact |
| `fact_type` | VARCHAR(30) | YES | `'general'` | See fact types below |
| `created_at` | TIMESTAMPTZ | YES | `NOW()` | When learned |

**Fact types:** `correction`, `preference`, `habit`, `mood`, `goal`, `general`

---

### `reminders`

User-created reminders with optional recurrence.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | YES | — | FK → `users(id)` ON DELETE CASCADE |
| `title` | VARCHAR(255) | NO | — | Reminder text |
| `scheduled_time` | TIMESTAMPTZ | NO | — | When to fire |
| `recurrence` | VARCHAR(50) | YES | `'none'` | `none`, `daily`, `weekly`, `monthly`, or cron |
| `is_active` | BOOLEAN | YES | `TRUE` | Active flag |
| `snooze_count` | INT | YES | `0` | Times snoozed |
| `created_at` | TIMESTAMPTZ | YES | `NOW()` | Creation time |

---

### `transactions`

Budget tracking — income and expense records.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | YES | — | FK → `users(id)` ON DELETE CASCADE |
| `amount` | DECIMAL(12,2) | NO | — | Transaction amount |
| `type` | VARCHAR(10) | NO | — | `'income'` or `'expense'` |
| `category` | VARCHAR(50) | NO | — | Auto-categorised (see below) |
| `description` | TEXT | YES | — | Optional note |
| `transaction_date` | DATE | YES | `CURRENT_DATE` | Date of transaction |
| `created_at` | TIMESTAMPTZ | YES | `NOW()` | Record creation |

**Expense categories:** `food`, `transport`, `utilities`, `rent`, `groceries`, `entertainment`, `health`, `shopping`, `subscriptions`, `education`, `personal_care`, `gifts`, `travel`, `savings`, `other`

**Income categories:** `salary`, `freelance`, `gift`, `refund`, `investment`, `other`

---

### `conversations`

Chat history for AI context injection.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | YES | — | FK → `users(id)` ON DELETE CASCADE |
| `role` | VARCHAR(10) | NO | — | `'user'` or `'assistant'` |
| `content` | TEXT | NO | — | Message text |
| `skill_used` | VARCHAR(50) | YES | — | Which skill handled this |
| `created_at` | TIMESTAMPTZ | YES | `NOW()` | Message timestamp |

---

### `budget_limits`

Per-category monthly spending limits.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | YES | — | FK → `users(id)` ON DELETE CASCADE |
| `category` | VARCHAR(50) | NO | — | Budget category |
| `monthly_limit` | DECIMAL(12,2) | NO | — | Spending cap |
| `is_active` | BOOLEAN | YES | `TRUE` | Active flag |

**Constraints:** `UNIQUE(user_id, category)`

---

---

### `tech_projects`

MakubeX-tracked tech projects (Phase CH-3).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | NO | — | FK → `users(id)` ON DELETE CASCADE |
| `name` | VARCHAR(120) | NO | — | Project name |
| `description` | TEXT | YES | — | Short description |
| `tech_stack` | JSONB | YES | `'[]'` | Array of stack items (strings) |
| `status` | VARCHAR(20) | YES | `'active'` | `active` / `paused` / `completed` / `archived` |
| `repo_url` | TEXT | YES | — | Source control URL |
| `notes` | TEXT | YES | — | Free-form notes |
| `priority` | INT | YES | `2` | 1 (high) / 2 / 3 (low) |
| `started_at` | DATE | YES | — | Start date |
| `created_at` | TIMESTAMPTZ | YES | `NOW()` | Record creation |
| `updated_at` | TIMESTAMPTZ | YES | `NOW()` | Last update |

---

### `tech_skills`

Per-technology skill tracking for MakubeX (Phase CH-3).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | NO | — | FK → `users(id)` ON DELETE CASCADE |
| `skill` | VARCHAR(80) | NO | — | Normalised skill name |
| `level` | INT | NO | `1` | 1 (beginner) – 5 (expert) |
| `last_used` | DATE | YES | — | Most recent usage |
| `created_at` | TIMESTAMPTZ | YES | `NOW()` | Record creation |
| `updated_at` | TIMESTAMPTZ | YES | `NOW()` | Last update |

**Constraints:** `UNIQUE(user_id, skill)` — upserts update existing rows.

---

### `learning_log`

Append-only log of topics MakubeX has walked the user through (Phase CH-3).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | NO | — | FK → `users(id)` ON DELETE CASCADE |
| `topic` | VARCHAR(120) | NO | — | Snake-cased topic |
| `category` | VARCHAR(60) | YES | `'concept'` | e.g. `concept`, `tool`, `pattern` |
| `depth` | VARCHAR(20) | YES | `'intro'` | `intro` / `solid` / `deep` |
| `taught_at` | TIMESTAMPTZ | YES | `NOW()` | When the session happened |

---

### `code_reviews`

Cached structured code reviews for MakubeX (Phase CH-3).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NO | `gen_random_uuid()` | Primary key |
| `user_id` | UUID | NO | — | FK → `users(id)` ON DELETE CASCADE |
| `snippet_hash` | VARCHAR(64) | NO | — | SHA-256 of normalised snippet |
| `language` | VARCHAR(40) | YES | — | Detected or hinted language |
| `summary` | TEXT | YES | — | One-liner summary |
| `issues_found` | JSONB | YES | `'[]'` | Structured issue records |
| `created_at` | TIMESTAMPTZ | YES | `NOW()` | When review ran |

**Constraints:** `UNIQUE(user_id, snippet_hash)` — repeat reviews hit the cache instead of the model.

---

## Indexes

| Index | Table | Columns | Condition |
|-------|-------|---------|-----------|
| `idx_user_profile_user` | `user_profile` | `user_id` | — |
| `idx_memory_log_user` | `memory_log` | `user_id` | — |
| `idx_memory_log_session` | `memory_log` | `session_id` | — |
| `idx_reminders_user_active` | `reminders` | `user_id, is_active` | — |
| `idx_reminders_scheduled` | `reminders` | `scheduled_time` | `WHERE is_active = TRUE` |
| `idx_transactions_user` | `transactions` | `user_id` | — |
| `idx_transactions_date` | `transactions` | `user_id, transaction_date` | — |
| `idx_conversations_user` | `conversations` | `user_id` | — |
| `idx_conversations_created` | `conversations` | `user_id, created_at` | — |
| `idx_tech_projects_user` | `tech_projects` | `user_id, status` | — |
| `idx_tech_skills_user` | `tech_skills` | `user_id` | — |
| `idx_learning_log_user` | `learning_log` | `user_id, taught_at DESC` | — |
| `idx_learning_log_topic` | `learning_log` | `user_id, topic` | — |
| `idx_code_reviews_user` | `code_reviews` | `user_id, created_at DESC` | — |
| `idx_code_reviews_hash` | `code_reviews` | `user_id, snippet_hash` | — |

## Row-Level Security

RLS is enabled on every table, including the four MakubeX tables. A `service_role_all` policy grants full access since the bot connects with a service-role key.

## Entity Relationships

```
users (1) ──── (N) user_profile
users (1) ──── (N) memory_log
users (1) ──── (N) reminders
users (1) ──── (N) transactions
users (1) ──── (N) conversations
users (1) ──── (N) budget_limits
users (1) ──── (N) tech_projects
users (1) ──── (N) tech_skills
users (1) ──── (N) learning_log
users (1) ──── (N) code_reviews
```

All foreign keys use `ON DELETE CASCADE` — deleting a user removes all their data.
