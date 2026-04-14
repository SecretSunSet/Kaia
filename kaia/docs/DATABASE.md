# KAIA Database Schema

**Engine:** PostgreSQL via Supabase
**Migration file:** `database/migrations/001_initial.sql`

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

**Category values:** `identity`, `health`, `finances`, `personality`, `preferences`, `goals`, `patterns`

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

## Row-Level Security

RLS is enabled on all 7 tables. A `service_role_all` policy grants full access since the bot connects with a service-role key.

## Entity Relationships

```
users (1) ──── (N) user_profile
users (1) ──── (N) memory_log
users (1) ──── (N) reminders
users (1) ──── (N) transactions
users (1) ──── (N) conversations
users (1) ──── (N) budget_limits
```

All foreign keys use `ON DELETE CASCADE` — deleting a user removes all their data.
