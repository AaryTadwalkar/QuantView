"""
1. What this file does:
   Integration tests for relational and PostgreSQL append-only ledger verification (Task M4-11).

2. Overall design:
   Uses pytest to verify relational database invariants:
     - Relational schema creation with all 12 canonical fields per QUANTVIEW_DATA_SPEC §2.1.
     - Database-level trigger enforcement: UPDATE operations are strictly aborted.
     - Database-level trigger enforcement: DELETE operations are strictly aborted.
     - Idempotency key uniqueness: duplicate transaction insertions fail closed with integrity violation.
     - Sequential querying and projection reconstruction matching FinancialLedger.

3. Elements in the file:
   - TestRelationalLedgerRepository: Integration tests executing DDL, DML, and trigger assertions.

4. Final output of the file:
   - Automated pass/fail test execution for Milestone M4-11.
"""

import sqlite3
from pathlib import Path

import pytest

from packages.db.ledger_repo import SqliteLedgerRepository
from packages.domain import Paise, UtcEpochSec
from packages.ledger.events import CanonicalLedgerEventType, FinancialEventRecord
from packages.ledger.projections import LedgerProjectionEngine


@pytest.mark.gate_g2a
class TestRelationalLedgerRepository:
    """
    1. The use of class:
       Integration test suite validating relational ledger append-only triggers and constraints.

    2. What the class contains:
       - test_append_event_and_query_sequence: Validates insert and order by sequence_num.
       - test_trigger_aborts_update_operation: Validates UPDATE triggers abort with RAISE(ABORT).
       - test_trigger_aborts_delete_operation: Validates DELETE triggers abort with RAISE(ABORT).
       - test_unique_idempotency_key_constraint: Validates duplicate key rejection.
       - test_reconstructed_projection_from_db_records: Validates projection equality from DB rows.

    3. Technologies used and why:
       sqlite3 and SqliteLedgerRepository with active triggers and schema.

    4. Key design and overall design of the class:
       Directly proves Task M4-11 relational trigger and append-only invariants.
    """

    def test_append_event_and_query_sequence(self):
        """Tests inserting events into relational store and querying them in sequence."""
        repo = SqliteLedgerRepository(":memory:")
        t = UtcEpochSec(1735200000)

        r1 = FinancialEventRecord(
            sequence_num=1,
            event_id="ev_001",
            account_id="acc_test",
            run_id="run_001",
            event_type=CanonicalLedgerEventType.DEPOSIT,
            event_time=t,
            recorded_at=t,
            amount_paise=Paise(10_000_000),
            balance_paise=Paise(10_000_000),
            idempotency_key="idem_001",
            correlation_id="corr_001",
            metadata={"note": "seed"},
        )
        repo.append_event(r1)

        events = repo.get_events("acc_test")
        assert len(events) == 1
        assert events[0].event_id == "ev_001"
        assert events[0].balance_paise == 10_000_000

    def test_trigger_aborts_update_operation(self):
        """
        1. The use of function:
           Verifies that the database trigger forbids any UPDATE on ledger_events.

        2. How does the specific function work:
           Attempts raw SQL UPDATE statement and asserts that sqlite3.OperationalError or
           sqlite3.DatabaseError is raised with the trigger's message: 'ledger_events is append-only'.

        3. Concepts used in the function:
           Append-only trigger enforcement at database level.
        """
        repo = SqliteLedgerRepository(":memory:")
        t = UtcEpochSec(1735200000)

        r1 = FinancialEventRecord(
            sequence_num=1,
            event_id="ev_001",
            account_id="acc_test",
            run_id="run_001",
            event_type=CanonicalLedgerEventType.DEPOSIT,
            event_time=t,
            recorded_at=t,
            amount_paise=Paise(10_000_000),
            balance_paise=Paise(10_000_000),
            idempotency_key="idem_001",
            correlation_id="corr_001",
            metadata={},
        )
        repo.append_event(r1)

        # Raw attempt to update balance_paise
        with pytest.raises(sqlite3.DatabaseError) as exc_info:
            repo._conn.execute("UPDATE ledger_events SET balance_paise = 0 WHERE event_id = 'ev_001';")
        assert "ledger_events is append-only" in str(exc_info.value)

    def test_trigger_aborts_delete_operation(self):
        """
        1. The use of function:
           Verifies that the database trigger forbids any DELETE on ledger_events.

        2. How does the specific function work:
           Attempts raw SQL DELETE statement and asserts that the trigger raises error.

        3. Concepts used in the function:
           Append-only trigger enforcement at database level.
        """
        repo = SqliteLedgerRepository(":memory:")
        t = UtcEpochSec(1735200000)

        r1 = FinancialEventRecord(
            sequence_num=1,
            event_id="ev_001",
            account_id="acc_test",
            run_id="run_001",
            event_type=CanonicalLedgerEventType.DEPOSIT,
            event_time=t,
            recorded_at=t,
            amount_paise=Paise(10_000_000),
            balance_paise=Paise(10_000_000),
            idempotency_key="idem_001",
            correlation_id="corr_001",
            metadata={},
        )
        repo.append_event(r1)

        # Raw attempt to delete row
        with pytest.raises(sqlite3.DatabaseError) as exc_info:
            repo._conn.execute("DELETE FROM ledger_events WHERE event_id = 'ev_001';")
        assert "ledger_events is append-only" in str(exc_info.value)

    def test_unique_idempotency_key_constraint(self):
        """
        1. The use of function:
           Verifies that duplicate idempotency keys violate the unique constraint.

        2. How does the specific function work:
           Inserts two distinct records with identical idempotency_key 'duplicate_key'.
           Asserts sqlite3.IntegrityError is raised.
        """
        repo = SqliteLedgerRepository(":memory:")
        t = UtcEpochSec(1735200000)

        r1 = FinancialEventRecord(
            sequence_num=1,
            event_id="ev_001",
            account_id="acc_test",
            run_id="run_001",
            event_type=CanonicalLedgerEventType.DEPOSIT,
            event_time=t,
            recorded_at=t,
            amount_paise=Paise(10_000_000),
            balance_paise=Paise(10_000_000),
            idempotency_key="duplicate_key",
            correlation_id="corr_001",
            metadata={},
        )
        repo.append_event(r1)

        r2 = FinancialEventRecord(
            sequence_num=2,
            event_id="ev_002",
            account_id="acc_test",
            run_id="run_001",
            event_type=CanonicalLedgerEventType.ORDER_INTENT,
            event_time=t,
            recorded_at=t,
            amount_paise=Paise(0),
            balance_paise=Paise(10_000_000),
            idempotency_key="duplicate_key",  # Duplicate key!
            correlation_id="corr_002",
            metadata={},
        )
        with pytest.raises(sqlite3.IntegrityError):
            repo.append_event(r2)

    def test_reconstructed_projection_from_db_records(self):
        """
        1. The use of function:
           Verifies that querying events from the database and projecting state reproduces exact math.
        """
        repo = SqliteLedgerRepository(":memory:")
        t = UtcEpochSec(1735200000)

        # 1. Deposit
        repo.append_event(
            FinancialEventRecord(
                sequence_num=1,
                event_id="ev_1",
                account_id="acc_proj",
                run_id="run_p",
                event_type=CanonicalLedgerEventType.DEPOSIT,
                event_time=t,
                recorded_at=t,
                amount_paise=Paise(10_000_000),
                balance_paise=Paise(10_000_000),
                idempotency_key="id_1",
                correlation_id="c_1",
                metadata={},
            )
        )
        # 2. Fill Buy
        repo.append_event(
            FinancialEventRecord(
                sequence_num=2,
                event_id="ev_2",
                account_id="acc_proj",
                run_id="run_p",
                event_type=CanonicalLedgerEventType.FILL,
                event_time=t,
                recorded_at=t,
                amount_paise=Paise(-250125),
                balance_paise=Paise(9749875),
                idempotency_key="id_2",
                correlation_id="c_2",
                metadata={"side": "BUY", "instrument_key": "NIFTY_CE", "qty": 25, "price_paise": 10005, "gross_value_paise": 250125},
            )
        )
        # 3. Fee
        repo.append_event(
            FinancialEventRecord(
                sequence_num=3,
                event_id="ev_3",
                account_id="acc_proj",
                run_id="run_p",
                event_type=CanonicalLedgerEventType.FEE,
                event_time=t,
                recorded_at=t,
                amount_paise=Paise(-2472),
                balance_paise=Paise(9747403),
                idempotency_key="id_3",
                correlation_id="c_2",
                metadata={"total_fee_paise": 2472},
            )
        )

        db_events = repo.get_events("acc_proj", "run_p")
        proj = LedgerProjectionEngine.reconstruct_state(db_events)
        assert proj.cash_balance_paise == 9747403
        assert proj.total_fees_paid_paise == 2472
        assert proj.positions["NIFTY_CE"].qty == 25
        assert proj.is_balanced is True
