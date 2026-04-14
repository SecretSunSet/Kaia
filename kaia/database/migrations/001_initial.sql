-- ============================================================
-- KAIA v1.0 — Initial Schema
-- Run this in Supabase SQL Editor to create all tables.
-- ============================================================

-- Users
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(100),
    timezone VARCHAR(50) DEFAULT 'Asia/Manila',
    currency VARCHAR(10) DEFAULT 'PHP',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Evolving AI-generated user profile (core of memory system)
CREATE TABLE IF NOT EXISTS user_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL,
    key VARCHAR(100) NOT NULL,
    value TEXT NOT NULL,
    confidence FLOAT DEFAULT 0.5,
    source VARCHAR(20) DEFAULT 'inferred',
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, category, key)
);

-- Timestamped log of facts learned per conversation
CREATE TABLE IF NOT EXISTS memory_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR(50) NOT NULL,
    fact TEXT NOT NULL,
    fact_type VARCHAR(30) DEFAULT 'general',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Reminders
CREATE TABLE IF NOT EXISTS reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    scheduled_time TIMESTAMPTZ NOT NULL,
    recurrence VARCHAR(50) DEFAULT 'none',
    is_active BOOLEAN DEFAULT TRUE,
    snooze_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Budget transactions
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    amount DECIMAL(12, 2) NOT NULL,
    type VARCHAR(10) NOT NULL,
    category VARCHAR(50) NOT NULL,
    description TEXT,
    transaction_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Conversation history
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL,
    content TEXT NOT NULL,
    skill_used VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Budget limits per category
CREATE TABLE IF NOT EXISTS budget_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL,
    monthly_limit DECIMAL(12, 2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(user_id, category)
);

-- ── Indexes ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_user_profile_user ON user_profile(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_log_user ON memory_log(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_log_session ON memory_log(session_id);
CREATE INDEX IF NOT EXISTS idx_reminders_user_active ON reminders(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_reminders_scheduled ON reminders(scheduled_time) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(user_id, transaction_date);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(user_id, created_at);

-- ── Row-Level Security (enable for Supabase) ────────────────────────
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE budget_limits ENABLE ROW LEVEL SECURITY;

-- Allow service-role full access (bot runs as service role)
-- DROP first to make this script idempotent (CREATE POLICY has no IF NOT EXISTS)
DROP POLICY IF EXISTS "service_role_all" ON users;
DROP POLICY IF EXISTS "service_role_all" ON user_profile;
DROP POLICY IF EXISTS "service_role_all" ON memory_log;
DROP POLICY IF EXISTS "service_role_all" ON reminders;
DROP POLICY IF EXISTS "service_role_all" ON transactions;
DROP POLICY IF EXISTS "service_role_all" ON conversations;
DROP POLICY IF EXISTS "service_role_all" ON budget_limits;

CREATE POLICY "service_role_all" ON users FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON user_profile FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON memory_log FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON reminders FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON transactions FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON conversations FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON budget_limits FOR ALL USING (true) WITH CHECK (true);
