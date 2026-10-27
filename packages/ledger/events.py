"""
1. What this file does:
   Defines the 15 canonical financial ledger event types, immutable event record models,
   and idempotency key generators for QuantView (Task M4-07).

2. Overall design:
   Enforces the authoritative event-sourced accounting taxonomy from QUANTVIEW_DATA_SPEC §2.1:
     - 15 discrete event categories covering cash flows, order lifecycle, execution, fees, risk, and settlement.
     - Immutable event structures with monotonic sequencing, integer-paise amounts, running balances,
       and cryptographic idempotency keys.
     - Strict append-only discipline: mutations are rejected, corrections are posted as COMPENSATING_EVENT.

3. Elements in the file:
   - CanonicalLedgerEventType: Enumeration of all 15 canonical ledger event categories.
   - FinancialEventRecord: Immutable NamedTuple representing a single logged financial event.
   - generate_idempotency_key(): Cryptographic helper producing deterministic idempotency tokens.

4. Final output of the file:
   - Exported CanonicalLedgerEventType, FinancialEventRecord, and idempotency generation utilities.
"""

import hashlib
from enum import Enum
from typing import Any, Dict, NamedTuple, Optional

from packages.domain import Paise, UtcEpochSec


class CanonicalLedgerEventType(str, Enum):
    """
    1. The use of class:
       Enumerates all 15 authoritative financial event types per QUANTVIEW_DATA_SPEC §2.1.

    2. What the class contains:
       - DEPOSIT: External capital credit.
       - WITHDRAWAL: External capital debit.
       - ORDER_INTENT: Strategy emits order intention.
       - ORDER_ACCEPTED: Risk policy accepts order.
       - ORDER_REJECTED: Risk policy or market rejects order.
       - ORDER_EXPIRED: Unfilled order reaches time-in-force limit.
       - ORDER_CANCELLED: Explicit order cancellation.
       - FILL: Execution of a buy or sell transaction.
       - FEE: Statutory and broker transaction charges.
       - MARGIN_RESERVED: Collateral blocked for short positions (Stage 4).
       - MARGIN_RELEASED: Collateral unblocked upon square-off (Stage 4).
       - STOP_TARGET_UPDATE: Modification of intrabar stop-loss or take-profit price.
       - RISK_BREACH: Circuit breaker or daily drawdown limit triggered.
       - SETTLEMENT: Expiry cash settlement.
       - COMPENSATING_EVENT: Reversal or correction of a prior transaction.

    3. Technologies used and why:
       str and Enum for JSON serializability and exact string representation in databases.

    4. Key design and overall design of the class:
       Strictly satisfies DATA §2.1 and ENGINE §8 financial event taxonomy.
    """
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    ORDER_INTENT = "ORDER_INTENT"
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_EXPIRED = "ORDER_EXPIRED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    FILL = "FILL"
    FEE = "FEE"
    MARGIN_RESERVED = "MARGIN_RESERVED"
    MARGIN_RELEASED = "MARGIN_RELEASED"
    STOP_TARGET_UPDATE = "STOP_TARGET_UPDATE"
    RISK_BREACH = "RISK_BREACH"
    SETTLEMENT = "SETTLEMENT"
    COMPENSATING_EVENT = "COMPENSATING_EVENT"


class FinancialEventRecord(NamedTuple):
    """
    1. The use of class:
       Immutable event record representing an authoritative financial or operational transaction.

    2. What the class contains:
       - sequence_num: Monotonic positive integer sequence number within the account/run.
       - event_id: Unique monotonic integer or UUID string identifying this event.
       - account_id: Account identifier.
       - run_id: Backtest run identifier or live session ID.
       - event_type: CanonicalLedgerEventType.
       - event_time: UtcEpochSec representing when the event occurred in simulation time.
       - recorded_at: UtcEpochSec representing when the record was written to the ledger.
       - amount_paise: Net cash delta in integer Paise (positive = credit, negative = debit, 0 = non-cash).
       - balance_paise: Running cash balance in integer Paise after applying amount_paise.
       - idempotency_key: Cryptographic token preventing duplicate postings.
       - correlation_id: Associated order ID, fill ID, or intent ID.
       - metadata: Additional event details (instrument, prices, lots, itemized charges).

    3. Technologies used and why:
       NamedTuple for immutability, compact memory footprint, and fast property access.

    4. Key design and overall design of the class:
       Matches the 12-column ledger schema defined in ENGINE §8 and DATA §2.1.
    """
    sequence_num: int
    event_id: Any  # int or str
    account_id: str
    run_id: str
    event_type: CanonicalLedgerEventType
    event_time: UtcEpochSec
    recorded_at: UtcEpochSec
    amount_paise: Paise
    balance_paise: Paise
    idempotency_key: str
    correlation_id: str
    metadata: Dict[str, Any]

    @property
    def timestamp(self) -> UtcEpochSec:
        """Compatibility accessor returning event_time."""
        return self.event_time

    @property
    def description(self) -> str:
        """Compatibility accessor returning description from metadata."""
        return str(self.metadata.get("description", ""))

    @property
    def contract_id(self) -> Optional[str]:
        """Compatibility accessor returning contract_id from metadata."""
        return self.metadata.get("contract_id") or self.metadata.get("instrument_key")


def generate_idempotency_key(run_id: str, correlation_id: str, event_type: str, phase: str = "") -> str:
    """
    1. The use of function:
       Generates a deterministic SHA-256 idempotency key for a financial posting.

    2. How does the specific function work:
       Constructs a canonical string tuple (run_id, correlation_id, event_type, phase) and hashes it.

    3. Concepts used in the function:
       Idempotency tokens, cryptographic duplicate rejection.

    4. Places where this function is imported and used:
       Used by FinancialLedger.record_event and order execution services.

    5. Final output of the function, before and after:
       Before: Raw transaction IDs. After: 32-character hex SHA-256 prefix string.
    """
    raw = f"{run_id}:{correlation_id}:{event_type}:{phase}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
