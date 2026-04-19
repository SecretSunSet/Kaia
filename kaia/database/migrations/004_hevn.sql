-- ============================================================
-- KAIA Phase CH-2 — Hevn (Financial Advisor) tables
-- Run this in Supabase SQL Editor after 003_forum_topics.sql.
-- ============================================================

-- Financial goals (Hevn's domain)
CREATE TABLE IF NOT EXISTS financial_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    target_amount DECIMAL(12,2) NOT NULL,
    current_amount DECIMAL(12,2) DEFAULT 0,
    monthly_contribution DECIMAL(12,2),
    deadline DATE,
    priority INT DEFAULT 1,
    status VARCHAR(20) DEFAULT 'active',  -- active, paused, completed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Recurring bills tracking
CREATE TABLE IF NOT EXISTS recurring_bills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    category VARCHAR(50),
    due_day INT CHECK (due_day >= 1 AND due_day <= 31),
    recurrence VARCHAR(20) DEFAULT 'monthly',
    is_active BOOLEAN DEFAULT TRUE,
    last_paid DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_financial_goals_user_status ON financial_goals(user_id, status);
CREATE INDEX IF NOT EXISTS idx_recurring_bills_user_active ON recurring_bills(user_id, is_active);

-- ── Row-Level Security ─────────────────────────────────────────────
ALTER TABLE financial_goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE recurring_bills ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all" ON financial_goals;
DROP POLICY IF EXISTS "service_role_all" ON recurring_bills;

CREATE POLICY "service_role_all" ON financial_goals FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON recurring_bills FOR ALL USING (true) WITH CHECK (true);
