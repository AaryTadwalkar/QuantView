"""
1. What this file does:
   Defines the append-only financial event ledger, exact integer-paise accounting, deterministic
   rebuildable projections, and effective-dated fee schedule engine for QuantView.

2. Overall design:
   The ledger package maintains an immutable log of all financial events (FILL, FEE, DEPOSIT, etc.)
   using exact integer paise arithmetic. It enforces zero floating-point drift (<= 1 paise contract
   note reconciliation requirement), rejects mutations via append-only triggers, and verifies
   the fundamental balance equation after every transaction.

3. Elements in the file:
   - CanonicalLedgerEventType, LedgerEventType: Enums of the 15 canonical financial event categories.
   - FinancialEventRecord, LedgerEvent: Immutable financial event records.
   - FinancialLedger: Append-only ledger maintaining cash and position balances.
   - LedgerWriter: Columnar Parquet persistence and replay utility.
   - DuplicateEventError: Fail-closed exception for duplicate transaction postings.
   - FinancialProjectionState, PositionState, LedgerProjectionEngine: Deterministic state projections.
   - FeeBreakdown, FeeSchedule, FeeScheduleEngine: Versioned regulatory fee schedule engine.

4. Final output of the file:
   - Exported financial ledger classes, event contracts, projection models, and fee engine.
"""

from packages.domain import ContractIdentifier, Paise, UtcEpochSec
from packages.ledger.events import (
    CanonicalLedgerEventType,
    FinancialEventRecord,
    generate_idempotency_key,
)
from packages.ledger.fees import (
    UPSTOX_2025_OCT,
    UPSTOX_2026_APR,
    UPSTOX_2026_MAR,
    UPSTOX_2026_V1,
    FeeBreakdown,
    FeeSchedule,
    FeeScheduleEngine,
    get_default_fee_engine,
)
from packages.ledger.ledger import (
    LEDGER_EVENTS_PARQUET_SCHEMA,
    DuplicateEventError,
    FinancialLedger,
    LedgerWriter,
)
from packages.ledger.projections import (
    FinancialProjectionState,
    LedgerProjectionEngine,
    PositionState,
)

# Backwards compatibility aliases
LedgerEventType = CanonicalLedgerEventType
LedgerEvent = FinancialEventRecord

__all__ = [
    # Event Types & Records
    "CanonicalLedgerEventType",
    "LedgerEventType",
    "FinancialEventRecord",
    "LedgerEvent",
    "generate_idempotency_key",
    # Financial Ledger & Persistence
    "FinancialLedger",
    "LedgerWriter",
    "DuplicateEventError",
    "LEDGER_EVENTS_PARQUET_SCHEMA",
    # Projections
    "PositionState",
    "FinancialProjectionState",
    "LedgerProjectionEngine",
    # Fee Engine
    "FeeBreakdown",
    "FeeSchedule",
    "FeeScheduleEngine",
    "UPSTOX_2025_OCT",
    "UPSTOX_2026_MAR",
    "UPSTOX_2026_APR",
    "UPSTOX_2026_V1",
    "get_default_fee_engine",
]
