-- ============================================================
-- KAIA — Forum Topics Support (CH-1.1)
-- Run in Supabase SQL Editor after 002_channels.sql.
-- Maps Telegram forum-group topics to expert channels so each
-- expert gets its own thread in a group chat.
-- ============================================================

CREATE TABLE IF NOT EXISTS forum_topic_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id BIGINT NOT NULL,
    channel_id VARCHAR(50) NOT NULL,
    topic_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(chat_id, channel_id),
    UNIQUE(chat_id, topic_id)
);

-- ── Indexes ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_forum_topic_mappings_chat ON forum_topic_mappings(chat_id);

-- ── Row-Level Security ─────────────────────────────────────────────
ALTER TABLE forum_topic_mappings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all" ON forum_topic_mappings;

CREATE POLICY "service_role_all" ON forum_topic_mappings FOR ALL USING (true) WITH CHECK (true);
