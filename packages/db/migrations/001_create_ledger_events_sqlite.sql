-- QuantView Database Migration: 001_create_ledger_events_sqlite.sql
-- Milestone: M4-11 (Local SQLite Relational Mirror & Append-Only Triggers)
-- Spec Reference: QUANTVIEW_DATA_SPEC §2.1, QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §8

-- 1. Create ledger_events table
CREATE TABLE IF NOT EXISTS ledger_events (
    sequence_num INTEGER NOT NULL,
    event_id TEXT NOT NULL PRIMARY KEY,
    account_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_time INTEGER NOT NULL,
    recorded_at INTEGER NOT NULL,
    amount_paise INTEGER NOT NULL,
    balance_paise INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    correlation_id TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ledger_events_account_seq ON ledger_events(account_id, sequence_num);
CREATE INDEX IF NOT EXISTS idx_ledger_events_run_id ON ledger_events(run_id);
CREATE INDEX IF NOT EXISTS idx_ledger_events_event_type ON ledger_events(event_type);

-- 2. Trigger: Abort on UPDATE (Append-Only Enforcement)
CREATE TRIGGER IF NOT EXISTS trg_prevent_ledger_update
BEFORE UPDATE ON ledger_events
BEGIN
    SELECT RAISE(ABORT, 'ledger_events is append-only. UPDATE is forbidden.');
END;

-- 3. Trigger: Abort on DELETE (Append-Only Enforcement)
CREATE TRIGGER IF NOT EXISTS trg_prevent_ledger_delete
BEFORE DELETE ON ledger_events
BEGIN
    SELECT RAISE(ABORT, 'ledger_events is append-only. DELETE is forbidden.');
END;
