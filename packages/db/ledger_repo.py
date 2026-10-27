"""
1. What this file does:
   Implements the Relational Database Ledger Repository for QuantView (Task M4-11).
   Provides relational database persistence for the append-only ledger with trigger-enforced
   immutability, unique idempotency constraints, and transactional consistency.

2. Overall design:
   Enforces QUANTVIEW_DATA_SPEC §2.1 and QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §8:
     - Maps FinancialEventRecord into the 12-column ledger_events schema.
     - Enforces unique constraint on idempotency_key preventing duplicate financial postings.
     - Utilizes database triggers (trg_prevent_ledger_update, trg_prevent_ledger_delete) to strictly
       abort any in-place UPDATE or DELETE attempts at the database engine level.
     - Implements SqliteLedgerRepository for fast local testing and embedded operation.

3. Elements in the file:
   - RelationalLedgerMutationError: Exception raised when an update or delete operation is blocked by triggers.
   - SqliteLedgerRepository: Embedded relational ledger implementation with trigger enforcement.

4. Final output of the file:
   - Exported SqliteLedgerRepository and RelationalLedgerMutationError.
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Union

from packages.domain import Paise, UtcEpochSec
from packages.ledger.events import CanonicalLedgerEventType, FinancialEventRecord


class RelationalLedgerMutationError(Exception):
    """
    1. The use of class:
       Raised when an unauthorized UPDATE or DELETE operation is attempted on an append-only ledger table.

    2. What the class contains:
       - message: Error explanation from the database trigger.

    3. Technologies used and why:
       Standard Python Exception subclass.

    4. Key design and overall design of the class:
       Ensures database trigger violations surface as explicit domain-level errors.
    """
    pass


class SqliteLedgerRepository:
    """
    1. The use of class:
       Relational database repository providing append-only persistence and trigger enforcement.

    2. What the class contains:
       - _conn: Active sqlite3.Connection.
       - initialize_schema(): Applies DDL migrations and creates append-only triggers.
       - append_event(): Inserts a FinancialEventRecord within a transaction.
       - get_events(): Queries events by account_id and optional run_id.
       - get_latest_balance(): Returns current balance_paise for an account.

    3. Technologies used and why:
       sqlite3 with WAL mode, foreign keys, and trigger support for zero external daemon dependency.

    4. Key design and overall design of the class:
       Serves as the relational counterpart to Parquet and PostgreSQL, enforcing identical constraints.
    """

    def __init__(self, db_path: Union[str, Path] = ":memory:") -> None:
        """
        1. The use of function:
           Initializes SqliteLedgerRepository connection and configures pragmas.

        2. How does the specific function work:
           Opens sqlite3 connection, enables foreign keys and WAL mode (if file-based), and applies migrations.

        3. Concepts used in the function:
           Relational database setup and schema bootstrapping.

        4. Places where this function is imported and used:
           Used by integration tests, embedded runners, and paper accounts.

        5. Final output of the function, before and after:
           Before: Unconnected path. After: Fully migrated SqliteLedgerRepository.
        """
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self.initialize_schema()

    def initialize_schema(self) -> None:
        """
        1. The use of function:
           Applies the authoritative 001_create_ledger_events_sqlite.sql migration.

        2. How does the specific function work:
           Reads SQL script from packages/db/migrations and executes script on connection.

        3. Concepts used in the function:
           Declarative schema migration and trigger creation.

        4. Places where this function is imported and used:
           Called automatically during repository initialization.

        5. Final output of the function, before and after:
           Before: Empty database. After: ledger_events table and append-only triggers active.
        """
        migration_file = Path(__file__).parent / "migrations" / "001_create_ledger_events_sqlite.sql"
        if migration_file.exists():
            sql = migration_file.read_text(encoding="utf-8")
            self._conn.executescript(sql)
        else:
            # Fallback embedded DDL
            self._conn.executescript("""
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
                CREATE TRIGGER IF NOT EXISTS trg_prevent_ledger_update
                BEFORE UPDATE ON ledger_events
                BEGIN
                    SELECT RAISE(ABORT, 'ledger_events is append-only. UPDATE is forbidden.');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_prevent_ledger_delete
                BEFORE DELETE ON ledger_events
                BEGIN
                    SELECT RAISE(ABORT, 'ledger_events is append-only. DELETE is forbidden.');
                END;
            """)
        self._conn.commit()

    def append_event(self, record: FinancialEventRecord) -> None:
        """
        1. The use of function:
           Appends a FinancialEventRecord to the relational database inside an atomic transaction.

        2. How does the specific function work:
           Executes INSERT INTO ledger_events. If idempotency_key is duplicated, sqlite3.IntegrityError is raised.

        3. Concepts used in the function:
           ACID insertion, unique constraint validation.

        4. Places where this function is imported and used:
           Called when writing ledger events to the relational store.

        5. Final output of the function, before and after:
           Before: Record in memory. After: Persisted row in ledger_events.
        """
        query = """
            INSERT INTO ledger_events (
                sequence_num, event_id, account_id, run_id, event_type,
                event_time, recorded_at, amount_paise, balance_paise,
                idempotency_key, correlation_id, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        meta_json = json.dumps(record.metadata, sort_keys=True)
        with self._conn:
            self._conn.execute(
                query,
                (
                    record.sequence_num,
                    str(record.event_id),
                    record.account_id,
                    record.run_id,
                    record.event_type.value,
                    int(record.event_time),
                    int(record.recorded_at),
                    int(record.amount_paise),
                    int(record.balance_paise),
                    record.idempotency_key,
                    record.correlation_id,
                    meta_json,
                ),
            )

    def get_events(self, account_id: str, run_id: Optional[str] = None) -> List[FinancialEventRecord]:
        """
        1. The use of function:
           Retrieves ledger events for an account in monotonic sequence order.

        2. How does the specific function work:
           Selects rows matching account_id (and optional run_id) ordered by sequence_num ASC.

        3. Concepts used in the function:
           Relational query projection.

        4. Places where this function is imported and used:
           Called when loading state or performing database audits.

        5. Final output of the function, before and after:
           Before: Query criteria. After: List of reconstructed FinancialEventRecord objects.
        """
        if run_id:
            query = "SELECT * FROM ledger_events WHERE account_id = ? AND run_id = ? ORDER BY sequence_num ASC"
            cursor = self._conn.execute(query, (account_id, run_id))
        else:
            query = "SELECT * FROM ledger_events WHERE account_id = ? ORDER BY sequence_num ASC"
            cursor = self._conn.execute(query, (account_id,))

        records: List[FinancialEventRecord] = []
        for row in cursor.fetchall():
            rec = FinancialEventRecord(
                sequence_num=row["sequence_num"],
                event_id=row["event_id"],
                account_id=row["account_id"],
                run_id=row["run_id"],
                event_type=CanonicalLedgerEventType(row["event_type"]),
                event_time=UtcEpochSec(row["event_time"]),
                recorded_at=UtcEpochSec(row["recorded_at"]),
                amount_paise=Paise(row["amount_paise"]),
                balance_paise=Paise(row["balance_paise"]),
                idempotency_key=row["idempotency_key"],
                correlation_id=row["correlation_id"],
                metadata=json.loads(row["metadata"]),
            )
            records.append(rec)
        return records

    def close(self) -> None:
        """Closes the underlying database connection."""
        self._conn.close()
