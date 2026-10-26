-- QuantView Database Migration: 001_create_ledger_events.sql
-- Milestone: M4-11 (PostgreSQL & Relational Append-Only Ledger Verification)
-- Spec Reference: QUANTVIEW_DATA_SPEC §2.1, QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §8

-- 1. Create authoritative ledger_events table
CREATE TABLE IF NOT EXISTS ledger_events (
    sequence_num BIGINT NOT NULL,
    event_id VARCHAR(64) NOT NULL PRIMARY KEY,
    account_id VARCHAR(64) NOT NULL,
    run_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    event_time BIGINT NOT NULL,
    recorded_at BIGINT NOT NULL,
    amount_paise BIGINT NOT NULL,
    balance_paise BIGINT NOT NULL,
    idempotency_key VARCHAR(64) NOT NULL UNIQUE,
    correlation_id VARCHAR(64) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- 2. Indexes for fast sequential querying and audit lookup
CREATE INDEX IF NOT EXISTS idx_ledger_events_account_seq ON ledger_events(account_id, sequence_num);
CREATE INDEX IF NOT EXISTS idx_ledger_events_run_id ON ledger_events(run_id);
CREATE INDEX IF NOT EXISTS idx_ledger_events_event_type ON ledger_events(event_type);

-- 3. PostgreSQL Append-Only Enforcement Trigger Function
CREATE OR REPLACE FUNCTION trg_prevent_ledger_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'ledger_events is append-only. UPDATE and DELETE operations are forbidden.';
END;
$$ LANGUAGE plpgsql;

-- 4. Attach Append-Only Trigger
DROP TRIGGER IF EXISTS trg_ledger_events_append_only ON ledger_events;
CREATE TRIGGER trg_ledger_events_append_only
BEFORE UPDATE OR DELETE ON ledger_events
FOR EACH ROW
EXECUTE FUNCTION trg_prevent_ledger_mutation();
