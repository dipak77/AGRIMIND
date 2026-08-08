-- Flywheel feedback events (Postgres durable store)
-- Applied by PostgresFeedbackStore.ensure_schema() / migrate CLI

CREATE TABLE IF NOT EXISTS feedback_events (
    event_id       TEXT PRIMARY KEY,
    feedback_type  TEXT NOT NULL,
    query_id       TEXT,
    user_id        TEXT,
    query_text     TEXT NOT NULL DEFAULT '',
    answer_text    TEXT NOT NULL DEFAULT '',
    confidence     DOUBLE PRECISION,
    intent         TEXT,
    model_version  TEXT,
    trace_id       TEXT,
    reason         TEXT,
    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id      TEXT
);

CREATE INDEX IF NOT EXISTS idx_feedback_events_feedback_type
    ON feedback_events (feedback_type);

CREATE INDEX IF NOT EXISTS idx_feedback_events_created_at
    ON feedback_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_feedback_events_tenant_id
    ON feedback_events (tenant_id)
    WHERE tenant_id IS NOT NULL;
