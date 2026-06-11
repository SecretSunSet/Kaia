-- 006_agent_bus.sql — Agentic OS R-3: inter-agent bus tables.

CREATE TABLE agent_conversations (
  conversation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  started_by_agent  VARCHAR(50)  NOT NULL,
  intent_root       VARCHAR(100),                          -- nullable; root intent if known
  status            VARCHAR(20)  NOT NULL DEFAULT 'open',  -- 'open' | 'closed' | 'errored'
  created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  closed_at         TIMESTAMPTZ
);

CREATE INDEX idx_agent_conv_user
  ON agent_conversations(user_id, created_at DESC);

CREATE TABLE agent_messages (
  envelope_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES agent_conversations(conversation_id) ON DELETE CASCADE,
  from_agent      VARCHAR(50)  NOT NULL,
  to_agent        VARCHAR(50)  NOT NULL,
  user_id         UUID         NOT NULL,                          -- denormalized for fast user lookups
  intent          VARCHAR(100) NOT NULL,
  visibility      VARCHAR(20)  NOT NULL DEFAULT 'user_visible',   -- 'user_visible' | 'internal'
  kind            VARCHAR(20)  NOT NULL,                          -- 'request' | 'reply' | 'error'
  reply_to        UUID REFERENCES agent_messages(envelope_id),    -- correlates reply → request
  payload         JSONB        NOT NULL,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_msg_conv
  ON agent_messages(conversation_id, created_at);

CREATE INDEX idx_agent_msg_to_pending
  ON agent_messages(to_agent, created_at DESC)
  WHERE kind = 'request';
