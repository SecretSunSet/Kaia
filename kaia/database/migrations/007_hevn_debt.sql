-- ============================================================
-- KAIA Phase D-1 — Hevn Debt Coach tables
-- Run this in Supabase SQL Editor after 006_agent_bus.sql.
-- ============================================================

CREATE TABLE IF NOT EXISTS debts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    debt_type VARCHAR(30) NOT NULL DEFAULT 'other',
    balance DECIMAL(14,2) NOT NULL,
    interest_rate DECIMAL(8,4) NOT NULL,
    rate_period VARCHAR(10) NOT NULL DEFAULT 'monthly',  -- monthly, yearly
    rate_is_estimate BOOLEAN NOT NULL DEFAULT FALSE,
    minimum_payment DECIMAL(12,2),
    due_day INT CHECK (due_day >= 1 AND due_day <= 31),
    original_amount DECIMAL(14,2),
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, paid_off, archived
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS debt_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    debt_id UUID REFERENCES debts(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    amount DECIMAL(12,2) NOT NULL,
    paid_on DATE NOT NULL DEFAULT CURRENT_DATE,
    balance_after DECIMAL(14,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS debt_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    strategy VARCHAR(20) NOT NULL,                 -- avalanche, snowball
    monthly_budget DECIMAL(12,2) NOT NULL,
    baseline_payoff_date DATE NOT NULL,
    baseline_total_interest DECIMAL(14,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, completed, abandoned
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_debts_user_status ON debts(user_id, status);
CREATE INDEX IF NOT EXISTS idx_debt_payments_debt ON debt_payments(debt_id, paid_on DESC);
CREATE INDEX IF NOT EXISTS idx_debt_plans_user_status ON debt_plans(user_id, status);

-- ── Row-Level Security ─────────────────────────────────────────────
ALTER TABLE debts ENABLE ROW LEVEL SECURITY;
ALTER TABLE debt_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE debt_plans ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all" ON debts;
DROP POLICY IF EXISTS "service_role_all" ON debt_payments;
DROP POLICY IF EXISTS "service_role_all" ON debt_plans;

CREATE POLICY "service_role_all" ON debts FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON debt_payments FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON debt_plans FOR ALL USING (true) WITH CHECK (true);
