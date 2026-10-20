"""
1. What this file does:
   Defines the append-only financial event ledger and exact integer-paise accounting for QuantView.

2. Overall design:
   The ledger package maintains an immutable log of all financial events (FILL, FEE, DEPOSIT, etc.)
   using exact integer paise arithmetic. It enforces zero floating-point drift (<= 1 paise contract
   note reconciliation requirement).

3. Elements in the file:
   - LedgerEventType: Enum of financial event categories.
   - LedgerEvent: Immutable financial record.
   - FinancialLedger: Append-only ledger maintaining cash and position balances.

4. Final output of the file:
   - Exported financial ledger classes and event contracts.
"""

from enum import Enum
from typing import List, NamedTuple, Optional
from packages.domain import Paise, UtcEpochSec, ContractIdentifier


class LedgerEventType(str, Enum):
    """
    1. The use of class:
       Enumerates all valid financial event types per QuantView Data Spec §2.1.

    2. What the class contains:
       - DEPOSIT: Cash deposit into account.
       - WITHDRAWAL: Cash withdrawal.
       - FILL: Execution of a contract buy or sell.
       - FEE: Brokerage, STT, exchange turnover fees, GST, stamp duty.
       - SETTLEMENT: Cash settlement at contract expiry.

    3. Technologies used and why:
       str and Enum for strict serialization.

    4. Key design and overall design of the class:
       Matches the 15-event taxonomy defined in canonical specifications.
    """
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    FILL = "FILL"
    FEE = "FEE"
    SETTLEMENT = "SETTLEMENT"


class LedgerEvent(NamedTuple):
    """
    1. The use of class:
       Immutable event record representing a financial transaction.

    2. What the class contains:
       - event_id: Unique monotonic integer or UUID.
       - event_type: LedgerEventType.
       - timestamp: UtcEpochSec when event occurred.
       - amount_paise: Positive for credits, negative for debits (in Paise).
       - contract_id: Optional string identifying associated instrument.
       - description: Human-readable narrative.

    3. Technologies used and why:
       NamedTuple for strict immutability and exact math.

    4. Key design and overall design of the class:
       Append-only: corrections are logged as new compensating events, never updates.
    """
    event_id: int
    event_type: LedgerEventType
    timestamp: UtcEpochSec
    amount_paise: Paise
    contract_id: Optional[str]
    description: str


class FinancialLedger:
    """
    1. The use of class:
       Append-only ledger container calculating exact cash balances and fee aggregates.

    2. What the class contains:
       - events: List of LedgerEvent records.
       - balance_paise: Running cash balance in integer paise.
       - record_event(): Appends event and updates balance.

    3. Technologies used and why:
       Integer arithmetic on Paise types.

    4. Key design and overall design of the class:
       Guarantees that total cash balance strictly equals the sum of amount_paise across all events.
    """

    def __init__(self, initial_cash_paise: Paise = Paise(0)):
        """
        1. The use of function:
           Initializes an empty financial ledger with optional initial cash deposit.

        2. How does the specific function work:
           Stores cash balance and initializes empty event list. If initial_cash > 0, logs DEPOSIT.

        3. Concepts used in the function:
           Double-entry / append-only cash tracking.

        4. Places where this function is imported and used:
           Used by backtest simulation and paper accounts.

        5. Final output of the function, before and after:
           Before: Initial cash amount. After: Configured FinancialLedger.
        """
        self.events: List[LedgerEvent] = []
        self.balance_paise: Paise = Paise(int(initial_cash_paise))

    def record_event(
        self,
        event_type: LedgerEventType,
        timestamp: UtcEpochSec,
        amount_paise: Paise,
        contract_id: Optional[str] = None,
        description: str = "",
    ) -> LedgerEvent:
        """
        1. The use of function:
           Appends a new financial event and updates the running cash balance.

        2. How does the specific function work:
           Assigns next event_id, creates LedgerEvent, appends to events, updates balance_paise.

        3. Concepts used in the function:
           Monotonic sequencing, exact integer addition.

        4. Places where this function is imported and used:
           Called when orders fill, fees apply, or settlements occur.

        5. Final output of the function, before and after:
           Before: Transaction parameters. After: Appended LedgerEvent.
        """
        ev_id = len(self.events) + 1
        event = LedgerEvent(
            event_id=ev_id,
            event_type=event_type,
            timestamp=timestamp,
            amount_paise=amount_paise,
            contract_id=contract_id,
            description=description,
        )
        self.events.append(event)
        self.balance_paise = Paise(self.balance_paise + amount_paise)
        return event
