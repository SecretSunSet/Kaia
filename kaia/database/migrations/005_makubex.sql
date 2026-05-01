-- ============================================================
-- KAIA Phase CH-3 — MakubeX (Tech Lead / CTO) tables
-- Run this in Supabase SQL Editor after 004_hevn.sql.
-- ============================================================

-- Tech projects (MakubeX's domain)
CREATE TABLE IF NOT EXISTS tech_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    tech_stack JSONB,               -- ["Python", "FastAPI", "PostgreSQL"]
    status VARCHAR(20) DEFAULT 'active',  -- active, paused, completed, archived
    repo_url VARCHAR(255),
    notes TEXT,
    priority INT DEFAULT 1,
    started_at DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Technical skills tracking per user
CREATE TABLE IF NOT EXISTS tech_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    skill VARCHAR(100) NOT NULL,        -- "python", "docker", "aws", "react"
    level VARCHAR(20) DEFAULT 'beginner',  -- beginner, intermediate, advanced, expert
    last_used DATE,
    notes TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, skill)
);

-- Learning topics covered
CREATE TABLE IF NOT EXISTS learning_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    topic VARCHAR(100) NOT NULL,
    category VARCHAR(50),               -- "concept", "tool", "pattern", "language"
    depth VARCHAR(20) DEFAULT 'intro', -- intro, solid, deep
    taught_at TIMESTAMPTZ DEFAULT NOW(),
    notes TEXT
);

-- Code review history (tracks what's been reviewed)
CREATE TABLE IF NOT EXISTS code_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    snippet_hash VARCHAR(64),           -- dedup repeat reviews
    language VARCHAR(50),
    summary TEXT,
    issues_found JSONB,                 -- array of issues
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_tech_projects_user_status ON tech_projects(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tech_skills_user ON tech_skills(user_id);
CREATE INDEX IF NOT EXISTS idx_learning_log_user_topic ON learning_log(user_id, topic);
CREATE INDEX IF NOT EXISTS idx_code_reviews_user_hash ON code_reviews(user_id, snippet_hash);

-- ── Row-Level Security ─────────────────────────────────────────────
ALTER TABLE tech_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE tech_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE code_reviews ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all" ON tech_projects;
DROP POLICY IF EXISTS "service_role_all" ON tech_skills;
DROP POLICY IF EXISTS "service_role_all" ON learning_log;
DROP POLICY IF EXISTS "service_role_all" ON code_reviews;

CREATE POLICY "service_role_all" ON tech_projects FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON tech_skills FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON learning_log FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all" ON code_reviews FOR ALL USING (true) WITH CHECK (true);
