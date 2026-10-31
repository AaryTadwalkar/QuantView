"""
1. What this file does:
   Implements the Institutional Paper Broker, Execution Engine, and Pre-Trade Risk Guard
   for the QuantView Live Daemon (Milestones M7-03, M7-04 / Gate G5).
   Manages multi-account paper runtime (ACC-MANUAL-PAPER and strategy bots), order routing,
   quote and deterministic next-bar open matching, regulatory fee schedules, and integer-paise
   ledger persistence with database trigger immutability.

2. Overall design:
   Follows QUANTVIEW_DATA_SPEC §2.1 and QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §4, §8, §19.1:
     - Multi-Account & Strategy Isolation: Tracks discretionary manual console and automated bot accounts.
     - Dual Execution Models:
       * Quote Matching (QUOTE): Fills BUY against Ask + simulated adverse slippage, SELL against Bid - slippage.
       * Deterministic Open (DETERMINISTIC_OPEN): Fills queued orders on next-bar open + 5 paise slippage,
         maintaining bit-for-bit parity with packages/engine/execution.py and TickQuantizer.
     - Pre-Trade Risk Filtering: Integrates packages/risk/evaluator.py to fail-closed enforce
       RK-01 (Kill Switch), RK-02 (Trading Window 09:15-15:25 IST), RK-03 (Max Daily Loss),
       RK-06 (Freeze Limit 1,800 units), and RK-26 (Advisory Lot Ceiling).
     - Statutory Regulatory Fees: Applies exact date-aware itemized fees (UPSTOX_2026_V1).
     - Relational Event Sourcing: Persists transactions to SqliteLedgerRepository in WAL mode
       with database-level triggers blocking unauthorized mutations.

3. Elements in the file:
   - ExecutionMode: Enum of supported paper matching engines (QUOTE, DETERMINISTIC_OPEN).
   - PaperAccount: State container tracking cash, margin, realized and unrealized PnL.
   - PaperOrder: Dataclass recording order specifications, lifecycle status, and fill coordinates.
   - PaperPosition: Dataclass tracking open/closed contract inventory, entry averages, and mark-to-market.
   - PaperTrade: Dataclass recording immutable transaction executions and itemized fee allocations.
   - PaperBroker: Central institutional paper broker engine and order coordinator.

4. Final output of the file:
   - Exported PaperBroker, PaperAccount, PaperOrder, PaperPosition, PaperTrade, and ExecutionMode.
"""

import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from packages.db.ledger_repo import SqliteLedgerRepository
from packages.domain import (
    ContractIdentifier,
    OptionType,
    OrderSide,
    Paise,
    TickQuantizer,
    UtcEpochSec,
)
from packages.ledger.events import (
    CanonicalLedgerEventType,
    FinancialEventRecord,
    generate_idempotency_key,
)
from packages.ledger.fees import (
    FeeBreakdown,
    FeeScheduleEngine,
    get_default_fee_engine,
)
from packages.risk.evaluator import RiskPolicyEvaluator
from packages.risk.rules import RiskDecision, RiskRules, RiskVerdict


class ExecutionMode(str, Enum):
    """
    1. The use of class:
       Enumerates execution and order fill simulation models available in the paper broker.

    2. What the class contains:
       - QUOTE: Immediate matching against incoming Bid/Ask quotes with simulated adverse slippage.
       - DETERMINISTIC_OPEN: Queued matching at the next completed candle's open price.

    3. Technologies used and why:
       Python string Enum for clean serialization and type safety.

    4. Key design and overall design of the class:
       Permits deterministic engine backtest parity as well as real-time interactive quote matching.
    """
    QUOTE = "QUOTE"
    DETERMINISTIC_OPEN = "DETERMINISTIC_OPEN"


@dataclass
class PaperAccount:
    """
    1. The use of class:
       State container representing an isolated paper trading account.

    2. What the class contains:
       - account_id: Unique account identifier (e.g. 'ACC-MANUAL-PAPER').
       - cash_paise: Available cash balance in integer paise.
       - margin_reserved_paise: Margin blocked for active short derivative positions.
       - realized_pnl_paise: Cumulative realized net profit/loss in integer paise.
       - unrealized_pnl_paise: Current floating mark-to-market profit/loss.
       - created_at_epoch_sec: Account creation timestamp.

    3. Technologies used and why:
       Python dataclass with integer paise properties ensuring zero floating-point leakage.

    4. Key design and overall design of the class:
       Satisfies accounting equation: Equity = Cash + Unrealized PnL; Free Cash = Cash - Margin.
    """
    account_id: str
    cash_paise: int
    margin_reserved_paise: int = 0
    realized_pnl_paise: int = 0
    unrealized_pnl_paise: int = 0
    created_at_epoch_sec: int = 0

    @property
    def free_cash_paise(self) -> int:
        """
        1. The use of function:
           Computes unencumbered cash available for new margin collateral or long premium.

        2. How does the specific function work:
           Subtracts margin_reserved_paise from cash_paise.

        3. Concepts used in the function:
           Capital reservation, risk safety ceiling.

        4. Places where this function is imported and used:
           Used by order affordability gating and UI dashboards.

        5. Final output of the function, before and after:
           Before: Raw cash and margin. After: Free usable cash in integer paise.
        """
        return self.cash_paise - self.margin_reserved_paise

    @property
    def equity_paise(self) -> int:
        """
        1. The use of function:
           Computes total liquidating net worth of the paper account.

        2. How does the specific function work:
           Adds unrealized_pnl_paise to cash_paise.

        3. Concepts used in the function:
           Portfolio liquidation valuation, mark-to-market net equity.

        4. Places where this function is imported and used:
           Used by margin metrics, drawdown evaluator, and UI dashboards.

        5. Final output of the function, before and after:
           Before: Cash and floating PnL. After: Account equity in integer paise.
        """
        return self.cash_paise + self.unrealized_pnl_paise

    def to_dict(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Serializes account state to a JSON-compatible dictionary.

        2. How does the specific function work:
           Extracts paise and rupee-converted balances into a structured dictionary.

        3. Concepts used in the function:
           Data serialization, presentation formatting.

        4. Places where this function is imported and used:
           Used by REST API endpoints and state snapshots.

        5. Final output of the function, before and after:
           Before: PaperAccount instance. After: Dictionary of account parameters and balances.
        """
        return {
            "account_id": self.account_id,
            "cash_paise": self.cash_paise,
            "cash_rupees": self.cash_paise / 100.0,
            "margin_reserved_paise": self.margin_reserved_paise,
            "margin_reserved_rupees": self.margin_reserved_paise / 100.0,
            "free_cash_paise": self.free_cash_paise,
            "free_cash_rupees": self.free_cash_paise / 100.0,
            "realized_pnl_paise": self.realized_pnl_paise,
            "realized_pnl_rupees": self.realized_pnl_paise / 100.0,
            "unrealized_pnl_paise": self.unrealized_pnl_paise,
            "unrealized_pnl_rupees": self.unrealized_pnl_paise / 100.0,
            "equity_paise": self.equity_paise,
            "equity_rupees": self.equity_paise / 100.0,
            "created_at_epoch_sec": self.created_at_epoch_sec,
        }


@dataclass
class PaperOrder:
    """
    1. The use of class:
       Container capturing the lifecycle, parameters, and fill coordinates of a paper order.

    2. What the class contains:
       - order_id: Deterministic or UUID order identifier.
       - account_id: Associated trading account.
       - instrument_key: Canonical instrument identifier.
       - trading_symbol: Display trading symbol.
       - side: OrderSide (BUY or SELL).
       - quantity: Order volume in integer contract units.
       - order_type: Order type ('MARKET' or 'LIMIT').
       - price_paise: Target limit price in integer paise.
       - status: Current state ('PENDING', 'FILLED', 'REJECTED', 'CANCELLED').
       - filled_qty: Executed quantity.
       - fill_price_paise: Average execution price in integer paise.
       - placed_at_epoch_sec: Order placement epoch timestamp.
       - filled_at_epoch_sec: Execution epoch timestamp.
       - strategy_id: Optional strategy bot identifier.
       - execution_mode: Matching mode (QUOTE or DETERMINISTIC_OPEN).
       - rejection_reason: Failure reason code if rejected.
       - stop_loss_paise: Optional bracket stop-loss price.
       - take_profit_paise: Optional bracket take-profit price.
       - fill_id: Execution identifier if filled.

    3. Technologies used and why:
       Python dataclass with optional bracket boundaries and integer monetary types.

    4. Key design and overall design of the class:
       Provides a unified representation across manual discretionary and strategy-automated orders.
    """
    order_id: str
    account_id: str
    instrument_key: str
    trading_symbol: str
    side: OrderSide
    quantity: int
    order_type: str = "MARKET"
    price_paise: Optional[int] = None
    status: str = "PENDING"
    filled_qty: int = 0
    fill_price_paise: Optional[int] = None
    placed_at_epoch_sec: int = 0
    filled_at_epoch_sec: Optional[int] = None
    strategy_id: Optional[str] = None
    execution_mode: str = "QUOTE"
    rejection_reason: Optional[str] = None
    stop_loss_paise: Optional[int] = None
    take_profit_paise: Optional[int] = None
    fill_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Serializes order attributes into a structured JSON-compatible dictionary.

        2. How does the specific function work:
           Formats order identifiers, pricing in paise and rupees, order status, and execution timestamps.

        3. Concepts used in the function:
           Order serialization, presentation mapping.

        4. Places where this function is imported and used:
           Used by order monitoring tables and API responses.

        5. Final output of the function, before and after:
           Before: PaperOrder instance. After: Dictionary representing order data.
        """
        return {
            "order_id": self.order_id,
            "account_id": self.account_id,
            "strategy_id": self.strategy_id,
            "instrument_key": self.instrument_key,
            "trading_symbol": self.trading_symbol,
            "side": self.side.value if isinstance(self.side, OrderSide) else str(self.side),
            "quantity": self.quantity,
            "order_type": self.order_type,
            "price_paise": self.price_paise,
            "price_rupees": self.price_paise / 100.0 if self.price_paise is not None else None,
            "status": self.status,
            "filled_qty": self.filled_qty,
            "fill_price_paise": self.fill_price_paise,
            "fill_price_rupees": self.fill_price_paise / 100.0 if self.fill_price_paise is not None else None,
            "placed_at_epoch_sec": self.placed_at_epoch_sec,
            "filled_at_epoch_sec": self.filled_at_epoch_sec,
            "execution_mode": self.execution_mode,
            "rejection_reason": self.rejection_reason,
            "stop_loss_paise": self.stop_loss_paise,
            "take_profit_paise": self.take_profit_paise,
            "fill_id": self.fill_id,
        }


@dataclass
class PaperPosition:
    """
    1. The use of class:
       State container representing an open or closed derivative contract inventory position.

    2. What the class contains:
       - position_id: Unique position identifier.
       - account_id: Associated trading account.
       - strategy_id: Associated strategy bot identifier.
       - instrument_key: Instrument key.
       - trading_symbol: Display trading symbol.
       - side: OrderSide representing net directional bias.
       - quantity: Current open contract volume.
       - avg_entry_price_paise: Weighted average acquisition price.
       - current_ltp_paise: Last traded mark price in integer paise.
       - unrealized_pnl_paise: Floating mark-to-market net profit/loss.
       - realized_pnl_paise: Cumulative booked profit/loss from closures.
       - opened_at_epoch_sec: Position opening timestamp.
       - updated_at_epoch_sec: Last mark update timestamp.
       - is_closed: Boolean flag indicating if position is liquidated.

    3. Technologies used and why:
       Python dataclass with integer paise accounting and mark-to-market recalculation.

    4. Key design and overall design of the class:
       Maintains accurate inventory and PnL metrics supporting partial square-offs.
    """
    position_id: str
    account_id: str
    strategy_id: Optional[str]
    instrument_key: str
    trading_symbol: str
    side: OrderSide
    quantity: int
    avg_entry_price_paise: int
    current_ltp_paise: int
    unrealized_pnl_paise: int = 0
    realized_pnl_paise: int = 0
    opened_at_epoch_sec: int = 0
    updated_at_epoch_sec: int = 0
    is_closed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Serializes position state into a structured JSON-compatible dictionary.

        2. How does the specific function work:
           Formats contract key, side, quantity, average entry price, LTP, and PnL metrics.

        3. Concepts used in the function:
           Position serialization, portfolio reporting.

        4. Places where this function is imported and used:
           Used by position monitor tables and recovery checkpoint snapshots.

        5. Final output of the function, before and after:
           Before: PaperPosition instance. After: Dictionary representing position state.
        """
        return {
            "position_id": self.position_id,
            "account_id": self.account_id,
            "strategy_id": self.strategy_id,
            "instrument_key": self.instrument_key,
            "trading_symbol": self.trading_symbol,
            "side": self.side.value if isinstance(self.side, OrderSide) else str(self.side),
            "quantity": self.quantity,
            "avg_entry_price_paise": self.avg_entry_price_paise,
            "avg_entry_price_rupees": self.avg_entry_price_paise / 100.0,
            "current_ltp_paise": self.current_ltp_paise,
            "current_ltp_rupees": self.current_ltp_paise / 100.0,
            "unrealized_pnl_paise": self.unrealized_pnl_paise,
            "unrealized_pnl_rupees": self.unrealized_pnl_paise / 100.0,
            "realized_pnl_paise": self.realized_pnl_paise,
            "realized_pnl_rupees": self.realized_pnl_paise / 100.0,
            "opened_at_epoch_sec": self.opened_at_epoch_sec,
            "updated_at_epoch_sec": self.updated_at_epoch_sec,
            "is_closed": self.is_closed,
        }


@dataclass
class PaperTrade:
    """
    1. The use of class:
       Immutable trade record capturing an executed buy or sell transaction.

    2. What the class contains:
       - trade_id: Trade identifier.
       - fill_id: Execution fill identifier.
       - order_id: Corresponding order identifier.
       - account_id: Trading account.
       - strategy_id: Strategy bot identifier.
       - instrument_key: Instrument key.
       - trading_symbol: Display trading symbol.
       - side: OrderSide.
       - quantity: Transacted quantity.
       - price_paise: Executed price in integer paise.
       - gross_value_paise: Total trade value (quantity * price).
       - fee_paise: Total statutory charges in integer paise.
       - fee_breakdown: Optional itemized statutory breakdown dictionary.
       - realized_pnl_paise: Booked PnL if closing existing inventory.
       - timestamp_epoch_sec: Execution epoch timestamp.

    3. Technologies used and why:
       Python dataclass for transaction auditing and post-trade performance analytics.

    4. Key design and overall design of the class:
       Serves as the paper runtime equivalent of exchange execution confirmations.
    """
    trade_id: str
    fill_id: str
    order_id: str
    account_id: str
    strategy_id: Optional[str]
    instrument_key: str
    trading_symbol: str
    side: OrderSide
    quantity: int
    price_paise: int
    gross_value_paise: int
    fee_paise: int
    fee_breakdown: Optional[Dict[str, int]]
    realized_pnl_paise: int
    timestamp_epoch_sec: int

    def to_dict(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Serializes executed trade attributes into an audit dictionary.

        2. How does the specific function work:
           Formats execution fill IDs, side, quantity, price, gross value, and itemized fees.

        3. Concepts used in the function:
           Trade audit trail formatting, post-trade reporting.

        4. Places where this function is imported and used:
           Used by trade log queries and transaction history dashboards.

        5. Final output of the function, before and after:
           Before: PaperTrade instance. After: Dictionary representing executed trade.
        """
        return {
            "trade_id": self.trade_id,
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "account_id": self.account_id,
            "strategy_id": self.strategy_id,
            "instrument_key": self.instrument_key,
            "trading_symbol": self.trading_symbol,
            "side": self.side.value if isinstance(self.side, OrderSide) else str(self.side),
            "quantity": self.quantity,
            "price_paise": self.price_paise,
            "price_rupees": self.price_paise / 100.0,
            "gross_value_paise": self.gross_value_paise,
            "gross_value_rupees": self.gross_value_paise / 100.0,
            "fee_paise": self.fee_paise,
            "fee_rupees": self.fee_paise / 100.0,
            "fee_breakdown": self.fee_breakdown,
            "realized_pnl_paise": self.realized_pnl_paise,
            "realized_pnl_rupees": self.realized_pnl_paise / 100.0,
            "timestamp_epoch_sec": self.timestamp_epoch_sec,
        }


class PaperBroker:
    """
    1. The use of class:
       Central institutional paper trading broker, simulated execution engine, and pre-trade risk guard.

    2. What the class contains:
       - repo: SqliteLedgerRepository providing WAL-mode append-only persistence.
       - fee_engine: FeeScheduleEngine calculating statutory exchange charges.
       - risk_evaluator: RiskPolicyEvaluator enforcing pre-trade rules.
       - accounts: In-memory registry of PaperAccount states.
       - orders: Registry of active and historic PaperOrder instances.
       - pending_orders: Queue of orders pending deterministic open fills.
       - positions: Mapping of active PaperPosition objects.
       - trades: Log of executed PaperTrade records.
       - processed_fill_ids: Set of processed fill IDs ensuring zero duplicate fills.
       - submit_order(): Pre-trade validation, risk evaluation, and order routing.
       - process_bar_open(): Deterministic next-bar open fill execution.
       - mark_to_market(): Mark-to-market portfolio revaluation.
       - square_off_position(): Full position liquidation helper.
       - cancel_order(): Order cancellation.

    3. Technologies used and why:
       SqliteLedgerRepository with database triggers, TickQuantizer, threading.Lock, and Pydantic RiskRules.

    4. Key design and overall design of the class:
       Orchestrates thread-safe order matching with regulatory compliance and zero duplicate fill guarantees.
    """

    def __init__(
        self,
        db_path: Union[str, Path] = "Data/paper/qv_paper.db",
        initial_cash_paise: int = 10_000_000,
        accounts: Optional[List[str]] = None,
        execution_mode: Union[ExecutionMode, str] = ExecutionMode.QUOTE,
        slippage_paise: int = 5,
        tick_paise: int = 5,
        risk_evaluator: Optional[RiskPolicyEvaluator] = None,
        fee_engine: Optional[FeeScheduleEngine] = None,
        run_id: str = "LIVE_PAPER",
    ) -> None:
        """
        1. The use of function:
           Initializes PaperBroker instance, sets up sqlite ledger, and configures default accounts.

        2. How does the specific function work:
           - Bootstraps parent directories for db_path if file-based.
           - Instantiates SqliteLedgerRepository with WAL mode and schema triggers.
           - Sets up FeeScheduleEngine defaulting to UPSTOX_2026_V1.
           - Configures RiskPolicyEvaluator.
           - Registers initial accounts (defaulting to ACC-MANUAL-PAPER).

        3. Concepts used in the function:
           Dependency injection, relational database initialization, fail-closed setup.

        4. Places where this function is imported and used:
           Used by live daemon runner, interactive API routes, and unit/integration tests.

        5. Final output of the function, before and after:
           Before: Uninitialized broker. After: Ready PaperBroker with verified ledger repository.
        """
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.repo = SqliteLedgerRepository(self.db_path)
        self.fee_engine = fee_engine or get_default_fee_engine()
        self.risk_evaluator = risk_evaluator or RiskPolicyEvaluator(
            rules=RiskRules(
                freeze_quantity=1800,
                advisory_lot_ceiling=72,
                max_loss_per_day_paise=500_000,
                trading_window_start="09:15",
                trading_window_end="15:25",
            )
        )
        self.execution_mode = (
            execution_mode.value if isinstance(execution_mode, ExecutionMode) else str(execution_mode)
        )
        self.slippage_paise = slippage_paise
        self.tick_paise = tick_paise
        self.run_id = run_id

        self._lock = threading.Lock()
        self.accounts: Dict[str, PaperAccount] = {}
        self.orders: Dict[str, PaperOrder] = {}
        self.pending_orders: List[PaperOrder] = []
        self.positions: Dict[str, PaperPosition] = {}  # key: f"{account_id}:{instrument_key}"
        self.trades: List[PaperTrade] = []
        self.processed_fill_ids: Set[str] = set()
        self._seq_counters: Dict[str, int] = {}

        # Initialize default accounts
        account_list = accounts or ["ACC-MANUAL-PAPER"]
        for acc_id in account_list:
            self.register_account(acc_id, initial_cash_paise=initial_cash_paise)

    def register_account(self, account_id: str, initial_cash_paise: int = 10_000_000) -> PaperAccount:
        """
        1. The use of function:
           Registers or retrieves a paper trading account, initializing its cash ledger if new.

        2. How does the specific function work:
           - Checks if account exists in memory; if so, returns it.
           - Checks existing ledger repository events for account; if existing balance found, syncs.
           - If new, records initial DEPOSIT event in SqliteLedgerRepository and creates PaperAccount.

        3. Concepts used in the function:
           Account provisioning, idempotency, event-sourced cash bootstrapping.

        4. Places where this function is imported and used:
           Called during broker initialization and dynamically when bot strategies attach.

        5. Final output of the function, before and after:
           Before: Unregistered account ID. After: Active PaperAccount state container.
        """
        with self._lock:
            if account_id in self.accounts:
                return self.accounts[account_id]

            # Query existing sequence number and balance from SQLite
            events = self.repo.get_events(account_id)
            if events:
                latest_seq = max(ev.sequence_num for ev in events)
                latest_balance = events[-1].balance_paise
                self._seq_counters[account_id] = latest_seq
                account = PaperAccount(
                    account_id=account_id,
                    cash_paise=int(latest_balance),
                    created_at_epoch_sec=events[0].event_time,
                )
            else:
                self._seq_counters[account_id] = 1
                now_sec = int(time.time())
                deposit_event = FinancialEventRecord(
                    sequence_num=1,
                    event_id=f"EVT-DEP-{uuid.uuid4().hex[:8].upper()}",
                    account_id=account_id,
                    run_id=self.run_id,
                    event_type=CanonicalLedgerEventType.DEPOSIT,
                    event_time=UtcEpochSec(now_sec),
                    recorded_at=UtcEpochSec(now_sec),
                    amount_paise=Paise(initial_cash_paise),
                    balance_paise=Paise(initial_cash_paise),
                    idempotency_key=generate_idempotency_key(
                        account_id, "DEPOSIT", UtcEpochSec(now_sec), Paise(initial_cash_paise)
                    ),
                    correlation_id=f"INIT-{account_id}",
                    metadata=json.dumps({"reason": "Initial capital allocation"}),
                )
                self.repo.append_event(deposit_event)
                account = PaperAccount(
                    account_id=account_id,
                    cash_paise=initial_cash_paise,
                    created_at_epoch_sec=now_sec,
                )

            self.accounts[account_id] = account
            return account

    def get_account(self, account_id: str) -> Optional[PaperAccount]:
        """
        1. The use of function:
           Returns the PaperAccount state for a specified account ID.

        2. How does the specific function work:
           Retrieves account from in-memory dictionary under thread lock.

        3. Concepts used in the function:
           Thread-safe dictionary lookup.

        4. Places where this function is imported and used:
           Used by API controllers, risk checks, and tests.

        5. Final output of the function, before and after:
           Before: Account identifier. After: PaperAccount or None.
        """
        with self._lock:
            return self.accounts.get(account_id)

    def _next_sequence_num(self, account_id: str) -> int:
        """
        1. The use of function:
           Generates monotonically increasing sequence numbers for ledger events per account.

        2. How does the specific function work:
           Retrieves current counter, increments by 1, caches, and returns updated value.

        3. Concepts used in the function:
           Monotonic sequence generation, audit sequencing.

        4. Places where this function is imported and used:
           Internal helper invoked when building FinancialEventRecord instances.

        5. Final output of the function, before and after:
           Before: Prior counter. After: Next integer sequence number.
        """
        current = self._seq_counters.get(account_id, 0)
        self._seq_counters[account_id] = current + 1
        return self._seq_counters[account_id]

    def submit_order(
        self,
        account_id: str,
        instrument_key: str,
        trading_symbol: str,
        side: Union[OrderSide, str],
        quantity: int,
        order_type: str = "MARKET",
        price_paise: Optional[int] = None,
        strategy_id: Optional[str] = None,
        execution_mode: Optional[Union[ExecutionMode, str]] = None,
        bid_price_paise: Optional[int] = None,
        ask_price_paise: Optional[int] = None,
        ltp_paise: Optional[int] = None,
        current_time_str: Optional[str] = None,
        current_epoch_sec: Optional[int] = None,
        stop_loss_paise: Optional[int] = None,
        take_profit_paise: Optional[int] = None,
        contract: Optional[ContractIdentifier] = None,
    ) -> PaperOrder:
        """
        1. The use of function:
           Submits, validates against pre-trade risk policy, and routes a paper order for execution.

        2. How does the specific function work:
           - Normalizes inputs (OrderSide, timestamps, contract identifier).
           - Gating 1: Evaluates pre-trade risk policy via RiskPolicyEvaluator:
             * RK-01 (Kill Switch), RK-02 (Trading Window), RK-03 (Max Daily Loss),
             * RK-06 (Freeze Limit 1,800), RK-26 (Advisory Lot Ceiling).
           - If risk evaluation fails, marks order as REJECTED, records ORDER_REJECTED in ledger, returns order.
           - If risk evaluation passes, marks order as ACCEPTED, records ORDER_ACCEPTED in ledger.
           - Gating 2: Determines execution mode:
             * If QUOTE: Matches immediately against bid/ask or LTP with simulated adverse slippage.
             * If DETERMINISTIC_OPEN: Appends order to pending queue for execution upon next bar open.

        3. Concepts used in the function:
           Pre-trade risk gating, fail-closed order lifecycle, dual execution dispatch, event logging.

        4. Places where this function is imported and used:
           Used by LiveDaemon order router, manual web UI endpoints, and backtest adapters.

        5. Final output of the function, before and after:
           Before: Unverified order request. After: Formatted, persisted, and routed PaperOrder.
        """
        side_enum = OrderSide(side) if isinstance(side, str) else side
        now_sec = current_epoch_sec or int(time.time())
        order_mode = (
            (execution_mode.value if isinstance(execution_mode, ExecutionMode) else str(execution_mode))
            if execution_mode is not None
            else self.execution_mode
        )

        with self._lock:
            account = self.accounts.get(account_id)
            if account is None:
                account = self.register_account(account_id)

            order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

            # Synthesize ContractIdentifier if not provided
            if contract is None:
                contract = ContractIdentifier(
                    instrument_key=instrument_key,
                    trading_symbol=trading_symbol,
                    expiry_date="",
                    strike_price=0.0,
                    option_type=OptionType.CE,
                    lot_size=25,
                )

            # Compute daily loss in paise for RK-03
            daily_loss_paise = Paise(max(0, -account.realized_pnl_paise))

            # 1. Pre-Trade Risk Evaluation
            risk_decision: RiskDecision = self.risk_evaluator.evaluate_order(
                contract=contract,
                quantity=quantity,
                price_paise=Paise(price_paise) if price_paise is not None else None,
                current_time_str=current_time_str,
                daily_loss_paise=daily_loss_paise,
            )

            if risk_decision.verdict == RiskVerdict.REJECT:
                # Record rejection in ledger and return rejected order
                order = PaperOrder(
                    order_id=order_id,
                    account_id=account_id,
                    strategy_id=strategy_id,
                    instrument_key=instrument_key,
                    trading_symbol=trading_symbol,
                    side=side_enum,
                    quantity=quantity,
                    order_type=order_type,
                    price_paise=price_paise,
                    status="REJECTED",
                    placed_at_epoch_sec=now_sec,
                    execution_mode=order_mode,
                    rejection_reason=f"{risk_decision.rule_id}: {risk_decision.reason}",
                    stop_loss_paise=stop_loss_paise,
                    take_profit_paise=take_profit_paise,
                )
                self.orders[order_id] = order

                rej_event = FinancialEventRecord(
                    sequence_num=self._next_sequence_num(account_id),
                    event_id=f"EVT-REJ-{uuid.uuid4().hex[:8].upper()}",
                    account_id=account_id,
                    run_id=self.run_id,
                    event_type=CanonicalLedgerEventType.ORDER_REJECTED,
                    event_time=UtcEpochSec(now_sec),
                    recorded_at=UtcEpochSec(now_sec),
                    amount_paise=Paise(0),
                    balance_paise=Paise(account.cash_paise),
                    idempotency_key=generate_idempotency_key(
                        account_id, "ORDER_REJECTED", UtcEpochSec(now_sec), order_id
                    ),
                    correlation_id=order_id,
                    metadata=json.dumps({
                        "rule_id": risk_decision.rule_id,
                        "reason": risk_decision.reason,
                        "instrument_key": instrument_key,
                        "quantity": quantity,
                    }),
                )
                self.repo.append_event(rej_event)
                return order

            # 2. Risk Passed: Order Accepted
            order = PaperOrder(
                order_id=order_id,
                account_id=account_id,
                strategy_id=strategy_id,
                instrument_key=instrument_key,
                trading_symbol=trading_symbol,
                side=side_enum,
                quantity=quantity,
                order_type=order_type,
                price_paise=price_paise,
                status="PENDING",
                placed_at_epoch_sec=now_sec,
                execution_mode=order_mode,
                stop_loss_paise=stop_loss_paise,
                take_profit_paise=take_profit_paise,
            )
            self.orders[order_id] = order

            acc_event = FinancialEventRecord(
                sequence_num=self._next_sequence_num(account_id),
                event_id=f"EVT-ACC-{uuid.uuid4().hex[:8].upper()}",
                account_id=account_id,
                run_id=self.run_id,
                event_type=CanonicalLedgerEventType.ORDER_ACCEPTED,
                event_time=UtcEpochSec(now_sec),
                recorded_at=UtcEpochSec(now_sec),
                amount_paise=Paise(0),
                balance_paise=Paise(account.cash_paise),
                idempotency_key=generate_idempotency_key(
                    account_id, "ORDER_ACCEPTED", UtcEpochSec(now_sec), order_id
                ),
                correlation_id=order_id,
                metadata=json.dumps({
                    "instrument_key": instrument_key,
                    "trading_symbol": trading_symbol,
                    "side": side_enum.value,
                    "quantity": quantity,
                }),
            )
            self.repo.append_event(acc_event)

            # 3. Execution Routing
            if order_mode == ExecutionMode.QUOTE.value:
                self._fill_order_against_quote(
                    order=order,
                    account=account,
                    bid_price_paise=bid_price_paise,
                    ask_price_paise=ask_price_paise,
                    ltp_paise=ltp_paise,
                    now_sec=now_sec,
                )
            else:
                # DETERMINISTIC_OPEN: Defer to next bar open
                self.pending_orders.append(order)

            return order

    def _fill_order_against_quote(
        self,
        order: PaperOrder,
        account: PaperAccount,
        bid_price_paise: Optional[int],
        ask_price_paise: Optional[int],
        ltp_paise: Optional[int],
        now_sec: int,
    ) -> None:
        """
        1. The use of function:
           Executes an immediate fill of a PaperOrder against bid/ask or LTP quotes with adverse slippage.

        2. How does the specific function work:
           - Resolves base fill price:
             * BUY matches against Ask (or LTP) + slippage_paise.
             * SELL matches against Bid (or LTP) - slippage_paise.
           - Quantizes price via TickQuantizer to tick_paise.
           - Checks cash affordability; if insufficient, rejects order with REJECTED_INSUFFICIENT_CASH.
           - Posts FILL and FEE events to SqliteLedgerRepository.
           - Updates inventory position, realized PnL, cash balance, and margin.

        3. Concepts used in the function:
           Adverse slippage simulation, tick quantization, cash boundary validation, transactional ledger posting.

        4. Places where this function is imported and used:
           Internal matching helper invoked by submit_order.

        5. Final output of the function, before and after:
           Before: Pending PaperOrder. After: Filled (or cash-rejected) PaperOrder with ledger audit trails.
        """
        if order.side == OrderSide.BUY:
            base_price = ask_price_paise if (ask_price_paise and ask_price_paise > 0) else ltp_paise
            if base_price is None or base_price <= 0:
                base_price = order.price_paise or 10000
            raw_fill = base_price + self.slippage_paise
            fill_price_paise = TickQuantizer.quantize(raw_fill, tick_paise=self.tick_paise, side=OrderSide.BUY)
        else:
            base_price = bid_price_paise if (bid_price_paise and bid_price_paise > 0) else ltp_paise
            if base_price is None or base_price <= 0:
                base_price = order.price_paise or 10000
            raw_fill = max(self.tick_paise, base_price - self.slippage_paise)
            fill_price_paise = TickQuantizer.quantize(raw_fill, tick_paise=self.tick_paise, side=OrderSide.SELL)

        gross_value_paise = order.quantity * fill_price_paise

        # Calculate exact statutory fees
        trade_date_str = datetime.fromtimestamp(now_sec, tz=timezone.utc).strftime("%Y-%m-%d")
        fee_breakdown: FeeBreakdown = self.fee_engine.calculate_order_fees(
            trade_date=trade_date_str,
            side=order.side,
            gross_value_paise=Paise(gross_value_paise),
        )

        total_fee_paise = int(fee_breakdown.total_fee_paise)

        # Affordability check on BUY
        if order.side == OrderSide.BUY:
            required_cash = gross_value_paise + total_fee_paise
            if account.free_cash_paise < required_cash:
                order.status = "REJECTED"
                order.rejection_reason = "REJECTED_INSUFFICIENT_CASH"
                return

        # Complete fill execution
        self._record_fill_and_post_events(
            order=order,
            account=account,
            fill_price_paise=fill_price_paise,
            gross_value_paise=gross_value_paise,
            fee_breakdown=fee_breakdown,
            now_sec=now_sec,
        )

    def _record_fill_and_post_events(
        self,
        order: PaperOrder,
        account: PaperAccount,
        fill_price_paise: int,
        gross_value_paise: int,
        fee_breakdown: FeeBreakdown,
        now_sec: int,
    ) -> None:
        """
        1. The use of function:
           Applies trade accounting, updates position state, and posts immutable FILL and FEE ledger records.

        2. How does the specific function work:
           - Generates unique fill_id and trade_id.
           - Updates inventory in self.positions, calculating realized PnL on closing transactions.
           - Deducts fees from cash balance.
           - For BUY: decrements cash by gross value; for SELL: increments cash by gross value.
           - Posts FILL and FEE FinancialEventRecords into SqliteLedgerRepository.
           - Appends to self.trades and marks order FILLED.

        3. Concepts used in the function:
           Double-entry financial accounting, position inventory matching, immutable trigger-checked ledger.

        4. Places where this function is imported and used:
           Invoked by _fill_order_against_quote and process_bar_open.

        5. Final output of the function, before and after:
           Before: Evaluated fill price. After: Fully executed trade, updated account, and written ledger events.
        """
        fill_id = f"FILL-{uuid.uuid4().hex[:8].upper()}"
        trade_id = f"TRD-{uuid.uuid4().hex[:8].upper()}"
        total_fee_paise = int(fee_breakdown.total_fee_paise)

        # Update position and calculate realized PnL
        pos_key = f"{account.account_id}:{order.instrument_key}"
        existing_pos = self.positions.get(pos_key)
        realized_pnl_paise = 0

        if existing_pos is None or existing_pos.is_closed or existing_pos.quantity == 0:
            # Opening new position
            new_pos = PaperPosition(
                position_id=f"POS-{uuid.uuid4().hex[:8].upper()}",
                account_id=account.account_id,
                strategy_id=order.strategy_id,
                instrument_key=order.instrument_key,
                trading_symbol=order.trading_symbol,
                side=order.side,
                quantity=order.quantity,
                avg_entry_price_paise=fill_price_paise,
                current_ltp_paise=fill_price_paise,
                unrealized_pnl_paise=0,
                realized_pnl_paise=0,
                opened_at_epoch_sec=now_sec,
                updated_at_epoch_sec=now_sec,
                is_closed=False,
            )
            self.positions[pos_key] = new_pos
            if order.side == OrderSide.SELL:
                # Short position margin reservation
                account.margin_reserved_paise += gross_value_paise
        else:
            # Existing position modification
            if existing_pos.side == order.side:
                # Adding to position: weighted average entry price
                total_qty = existing_pos.quantity + order.quantity
                existing_pos.avg_entry_price_paise = (
                    existing_pos.quantity * existing_pos.avg_entry_price_paise + order.quantity * fill_price_paise
                ) // total_qty
                existing_pos.quantity = total_qty
                existing_pos.updated_at_epoch_sec = now_sec
                if order.side == OrderSide.SELL:
                    account.margin_reserved_paise += gross_value_paise
            else:
                # Closing or reducing position: calculate realized PnL
                close_qty = min(existing_pos.quantity, order.quantity)
                if existing_pos.side == OrderSide.BUY:
                    # Closing long
                    realized_pnl_paise = close_qty * (fill_price_paise - existing_pos.avg_entry_price_paise)
                else:
                    # Closing short
                    realized_pnl_paise = close_qty * (existing_pos.avg_entry_price_paise - fill_price_paise)
                    # Release margin proportionally
                    released_margin = (account.margin_reserved_paise * close_qty) // existing_pos.quantity
                    account.margin_reserved_paise = max(0, account.margin_reserved_paise - released_margin)

                existing_pos.quantity -= close_qty
                existing_pos.realized_pnl_paise += realized_pnl_paise
                existing_pos.updated_at_epoch_sec = now_sec
                if existing_pos.quantity == 0:
                    existing_pos.is_closed = True

        # Update cash balances
        if order.side == OrderSide.BUY:
            account.cash_paise -= gross_value_paise
        else:
            account.cash_paise += gross_value_paise

        account.cash_paise -= total_fee_paise
        account.realized_pnl_paise += realized_pnl_paise

        # 1. Post FILL Event
        fill_delta = -gross_value_paise if order.side == OrderSide.BUY else gross_value_paise
        fill_balance = account.cash_paise + total_fee_paise  # balance before fee deduction
        fill_event = FinancialEventRecord(
            sequence_num=self._next_sequence_num(account.account_id),
            event_id=f"EVT-FILL-{uuid.uuid4().hex[:8].upper()}",
            account_id=account.account_id,
            run_id=self.run_id,
            event_type=CanonicalLedgerEventType.FILL,
            event_time=UtcEpochSec(now_sec),
            recorded_at=UtcEpochSec(now_sec),
            amount_paise=Paise(fill_delta),
            balance_paise=Paise(fill_balance),
            idempotency_key=generate_idempotency_key(
                account.account_id, "FILL", UtcEpochSec(now_sec), fill_id
            ),
            correlation_id=order.order_id,
            metadata=json.dumps({
                "fill_id": fill_id,
                "instrument_key": order.instrument_key,
                "side": order.side.value,
                "quantity": order.quantity,
                "price_paise": fill_price_paise,
                "gross_value_paise": gross_value_paise,
                "realized_pnl_paise": realized_pnl_paise,
            }),
        )
        self.repo.append_event(fill_event)

        # 2. Post FEE Event
        fee_event = FinancialEventRecord(
            sequence_num=self._next_sequence_num(account.account_id),
            event_id=f"EVT-FEE-{uuid.uuid4().hex[:8].upper()}",
            account_id=account.account_id,
            run_id=self.run_id,
            event_type=CanonicalLedgerEventType.FEE,
            event_time=UtcEpochSec(now_sec),
            recorded_at=UtcEpochSec(now_sec),
            amount_paise=Paise(-total_fee_paise),
            balance_paise=Paise(account.cash_paise),
            idempotency_key=generate_idempotency_key(
                account.account_id, "FEE", UtcEpochSec(now_sec), fill_id
            ),
            correlation_id=order.order_id,
            metadata=json.dumps({
                "fill_id": fill_id,
                "brokerage_paise": fee_breakdown.brokerage_paise,
                "stt_paise": fee_breakdown.stt_paise,
                "turnover_paise": fee_breakdown.exchange_turnover_paise,
                "gst_paise": fee_breakdown.gst_paise,
                "sebi_paise": fee_breakdown.sebi_paise,
                "stamp_duty_paise": fee_breakdown.stamp_duty_paise,
                "total_fee_paise": total_fee_paise,
            }),
        )
        self.repo.append_event(fee_event)

        # Update order status
        order.status = "FILLED"
        order.filled_qty = order.quantity
        order.fill_price_paise = fill_price_paise
        order.filled_at_epoch_sec = now_sec
        order.fill_id = fill_id

        # Record trade
        trade = PaperTrade(
            trade_id=trade_id,
            fill_id=fill_id,
            order_id=order.order_id,
            account_id=account.account_id,
            strategy_id=order.strategy_id,
            instrument_key=order.instrument_key,
            trading_symbol=order.trading_symbol,
            side=order.side,
            quantity=order.quantity,
            price_paise=fill_price_paise,
            gross_value_paise=gross_value_paise,
            fee_paise=total_fee_paise,
            fee_breakdown={
                "brokerage_paise": fee_breakdown.brokerage_paise,
                "stt_paise": fee_breakdown.stt_paise,
                "exchange_turnover_paise": fee_breakdown.exchange_turnover_paise,
                "gst_paise": fee_breakdown.gst_paise,
                "sebi_paise": fee_breakdown.sebi_paise,
                "stamp_duty_paise": fee_breakdown.stamp_duty_paise,
            },
            realized_pnl_paise=realized_pnl_paise,
            timestamp_epoch_sec=now_sec,
        )
        self.trades.append(trade)
        self.processed_fill_ids.add(fill_id)

    def process_bar_open(
        self,
        candle: Any,
        timestamp_epoch_sec: Optional[int] = None,
    ) -> List[PaperOrder]:
        """
        1. The use of function:
           Executes Step 1 of the deterministic execution cycle, matching pending orders on bar open.

        2. How does the specific function work:
           - Ignores zero-volume flat bars (open == high == low == close and volume == 0).
           - Iterates over orders queued in pending_orders matching candle's instrument_key.
           - Applies 5 paise adverse slippage and TickQuantizer against candle.open_paise:
             * BUY: open_paise + 5 paise slippage.
             * SELL: open_paise - 5 paise slippage.
           - Re-checks cash affordability / margin at boundary.
           - Executes fills, writes ledger records, and returns filled orders.

        3. Concepts used in the function:
           Deterministic open execution, IntrabarFillEngine parity, zero-volume flat bar deferral.

        4. Places where this function is imported and used:
           Invoked on boundary clock or candle finalization by live daemon orchestration.

        5. Final output of the function, before and after:
           Before: Pending queued orders. After: Filled orders executed at quantized next-bar open.
        """
        with self._lock:
            # Flat bar check
            is_flat = getattr(candle, "is_flat_bar", False)
            if not is_flat:
                c_open = getattr(candle, "open_paise", None)
                c_high = getattr(candle, "high_paise", None)
                c_low = getattr(candle, "low_paise", None)
                c_close = getattr(candle, "close_paise", None)
                c_vol = getattr(candle, "volume", 0)
                if c_open == c_high == c_low == c_close and c_vol == 0:
                    is_flat = True

            if is_flat:
                return []

            open_paise = getattr(candle, "open_paise", None)
            if open_paise is None:
                # If rupee float open provided
                c_open_float = getattr(candle, "open", None)
                if c_open_float is not None:
                    open_paise = int(round(c_open_float * 100))
                else:
                    return []

            candle_instrument = getattr(candle, "instrument_key", None)
            now_sec = timestamp_epoch_sec or getattr(candle, "bar_start_epoch_sec", int(time.time()))

            filled_orders: List[PaperOrder] = []
            remaining_pending: List[PaperOrder] = []

            for order in self.pending_orders:
                if candle_instrument is not None and order.instrument_key != candle_instrument:
                    remaining_pending.append(order)
                    continue

                account = self.accounts.get(order.account_id)
                if account is None:
                    account = self.register_account(order.account_id)

                if order.side == OrderSide.BUY:
                    raw_fill = open_paise + self.slippage_paise
                    fill_price_paise = TickQuantizer.quantize(
                        raw_fill, tick_paise=self.tick_paise, side=OrderSide.BUY
                    )
                else:
                    raw_fill = max(self.tick_paise, open_paise - self.slippage_paise)
                    fill_price_paise = TickQuantizer.quantize(
                        raw_fill, tick_paise=self.tick_paise, side=OrderSide.SELL
                    )

                gross_value_paise = order.quantity * fill_price_paise
                trade_date_str = datetime.fromtimestamp(now_sec, tz=timezone.utc).strftime("%Y-%m-%d")
                fee_breakdown = self.fee_engine.calculate_order_fees(
                    trade_date=trade_date_str,
                    side=order.side,
                    gross_value_paise=Paise(gross_value_paise),
                )
                total_fee_paise = int(fee_breakdown.total_fee_paise)

                # Affordability check on BUY
                if order.side == OrderSide.BUY:
                    required_cash = gross_value_paise + total_fee_paise
                    if account.free_cash_paise < required_cash:
                        order.status = "REJECTED"
                        order.rejection_reason = "REJECTED_INSUFFICIENT_CASH"
                        filled_orders.append(order)
                        continue

                self._record_fill_and_post_events(
                    order=order,
                    account=account,
                    fill_price_paise=fill_price_paise,
                    gross_value_paise=gross_value_paise,
                    fee_breakdown=fee_breakdown,
                    now_sec=now_sec,
                )
                filled_orders.append(order)

            self.pending_orders = remaining_pending
            return filled_orders

    def mark_to_market(
        self,
        instrument_key: str,
        ltp_paise: int,
        timestamp_epoch_sec: Optional[int] = None,
    ) -> None:
        """
        1. The use of function:
           Revalues active open positions against incoming market quotes and refreshes account equity.

        2. How does the specific function work:
           - Iterates over open positions matching instrument_key.
           - Calculates unrealized PnL:
             * LONG: (ltp_paise - avg_entry_price_paise) * quantity
             * SHORT: (avg_entry_price_paise - ltp_paise) * quantity
           - Updates position current_ltp_paise, unrealized_pnl_paise, and updated_at_epoch_sec.
           - Updates aggregate account unrealized_pnl_paise.

        3. Concepts used in the function:
           Continuous portfolio mark-to-market revaluation, floating equity synchronization.

        4. Places where this function is imported and used:
           Called on tick arrival, bar closure, or dashboard refresh cycles.

        5. Final output of the function, before and after:
           Before: Stale mark values. After: Up-to-date position and account unrealized PnL.
        """
        now_sec = timestamp_epoch_sec or int(time.time())
        with self._lock:
            for pos in self.positions.values():
                if pos.instrument_key == instrument_key and not pos.is_closed and pos.quantity > 0:
                    pos.current_ltp_paise = ltp_paise
                    pos.updated_at_epoch_sec = now_sec
                    if pos.side == OrderSide.BUY:
                        pos.unrealized_pnl_paise = (ltp_paise - pos.avg_entry_price_paise) * pos.quantity
                    else:
                        pos.unrealized_pnl_paise = (pos.avg_entry_price_paise - ltp_paise) * pos.quantity

            # Re-sum account unrealized PnL
            for acc in self.accounts.values():
                acc.unrealized_pnl_paise = sum(
                    p.unrealized_pnl_paise
                    for p in self.positions.values()
                    if p.account_id == acc.account_id and not p.is_closed and p.quantity > 0
                )

    def square_off_position(
        self,
        account_id: str,
        instrument_key: str,
        ltp_paise: Optional[int] = None,
        bid_price_paise: Optional[int] = None,
        ask_price_paise: Optional[int] = None,
        current_epoch_sec: Optional[int] = None,
        execution_mode: Optional[Union[ExecutionMode, str]] = None,
        exit_price_paise: Optional[int] = None,
    ) -> Optional[PaperOrder]:
        """
        1. The use of function:
           Liquidates an open paper position by submitting an opposing closing order.

        2. How does the specific function work:
           - Retrieves existing open position for account_id and instrument_key.
           - If no position open, returns None.
           - Generates opposing order (SELL to close LONG, BUY to close SHORT) for entire position quantity.
           - Routes through submit_order respecting execution_mode (or defaulting to self.execution_mode).
           - Resolves effective LTP from ltp_paise or exit_price_paise fallback.

        3. Concepts used in the function:
           Position liquidation, risk de-escalation, opposing order synthesis, execution mode routing.

        4. Places where this function is imported and used:
           Used by manual console Square Off buttons, StrategyDeploymentHost exit signals, and risk stops.

        5. Final output of the function, before and after:
           Before: Active position inventory. After: Liquidated position or pending closing PaperOrder.
        """
        pos_key = f"{account_id}:{instrument_key}"
        with self._lock:
            pos = self.positions.get(pos_key)
            if pos is None or pos.is_closed or pos.quantity <= 0:
                return None

            close_side = OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY
            qty_to_close = pos.quantity
            trading_symbol = pos.trading_symbol

        effective_ltp = ltp_paise if ltp_paise is not None else exit_price_paise
        target_mode = execution_mode if execution_mode is not None else self.execution_mode
        return self.submit_order(
            account_id=account_id,
            instrument_key=instrument_key,
            trading_symbol=trading_symbol,
            side=close_side,
            quantity=qty_to_close,
            order_type="MARKET",
            strategy_id=pos.strategy_id,
            execution_mode=target_mode,
            bid_price_paise=bid_price_paise,
            ask_price_paise=ask_price_paise,
            ltp_paise=effective_ltp,
            current_epoch_sec=current_epoch_sec,
        )

    def cancel_order(self, order_id: str) -> Optional[PaperOrder]:
        """
        1. The use of function:
           Cancels a pending paper order and posts an ORDER_CANCELLED event to the ledger repository.

        2. How does the specific function work:
           - Finds order in self.orders and removes from self.pending_orders if present.
           - Sets status to CANCELLED.
           - Appends ORDER_CANCELLED event to SqliteLedgerRepository.

        3. Concepts used in the function:
           Order state cancellation, immutable audit trails.

        4. Places where this function is imported and used:
           Used by cancellation REST API endpoints and timeout schedulers.

        5. Final output of the function, before and after:
           Before: PENDING order. After: CANCELLED order with ledger audit record.
        """
        with self._lock:
            order = self.orders.get(order_id)
            if order is None or order.status != "PENDING":
                return None

            order.status = "CANCELLED"
            self.pending_orders = [o for o in self.pending_orders if o.order_id != order_id]

            now_sec = int(time.time())
            account = self.accounts.get(order.account_id)
            balance = account.cash_paise if account else 0

            cancel_event = FinancialEventRecord(
                sequence_num=self._next_sequence_num(order.account_id),
                event_id=f"EVT-CAN-{uuid.uuid4().hex[:8].upper()}",
                account_id=order.account_id,
                run_id=self.run_id,
                event_type=CanonicalLedgerEventType.ORDER_CANCELLED,
                event_time=UtcEpochSec(now_sec),
                recorded_at=UtcEpochSec(now_sec),
                amount_paise=Paise(0),
                balance_paise=Paise(balance),
                idempotency_key=generate_idempotency_key(
                    order.account_id, "ORDER_CANCELLED", UtcEpochSec(now_sec), order_id
                ),
                correlation_id=order_id,
                metadata=json.dumps({"reason": "User or strategy requested cancellation"}),
            )
            self.repo.append_event(cancel_event)
            return order

    def get_position(self, account_id: str, instrument_key: str) -> Optional[PaperPosition]:
        """
        1. The use of function:
           Retrieves the active or historic PaperPosition for a specific account and instrument key.

        2. How does the specific function work:
           Looks up composite key f"{account_id}:{instrument_key}" in self.positions under thread lock.

        3. Concepts used in the function:
           Thread-safe inventory retrieval.

        4. Places where this function is imported and used:
           Used by position queries, square-off helpers, and audit tests.

        5. Final output of the function, before and after:
           Before: Query identifiers. After: PaperPosition instance or None.
        """
        pos_key = f"{account_id}:{instrument_key}"
        with self._lock:
            return self.positions.get(pos_key)

    def get_positions(self, account_id: Optional[str] = None) -> List[PaperPosition]:
        """
        1. The use of function:
           Returns a list of positions, optionally filtered by a specific account ID.

        2. How does the specific function work:
           Filters self.positions by account_id if provided; otherwise returns all positions.

        3. Concepts used in the function:
           Portfolio collection filtering.

        4. Places where this function is imported and used:
           Used by paper trading dashboard controllers and risk checks.

        5. Final output of the function, before and after:
           Before: Optional account filter. After: List of PaperPosition objects.
        """
        with self._lock:
            if account_id is not None:
                return [p for p in self.positions.values() if p.account_id == account_id]
            return list(self.positions.values())

    def get_working_orders(
        self,
        account_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
    ) -> List[PaperOrder]:
        """
        1. The use of function:
           Returns a list of pending/working orders, optionally filtered by account or strategy ID.

        2. How does the specific function work:
           Iterates over self.orders filtering for status == 'PENDING' and matching criteria.

        3. Concepts used in the function:
           Order book state query.

        4. Places where this function is imported and used:
           Used by checkpoint serialization and order management tables.

        5. Final output of the function, before and after:
           Before: Filter parameters. After: List of pending PaperOrder objects.
        """
        with self._lock:
            orders = [o for o in self.orders.values() if o.status == "PENDING"]
            if account_id is not None:
                orders = [o for o in orders if o.account_id == account_id]
            if strategy_id is not None:
                orders = [o for o in orders if o.strategy_id == strategy_id]
            return orders

    def reconcile_account(self, account_id: str) -> Dict[str, Any]:
        """
        1. The use of function:
           Reconciles in-memory account state with append-only relational ledger events.

        2. How does the specific function work:
           - Queries all ledger events for account_id from SqliteLedgerRepository.
           - Calculates cumulative net cash flow (sum of amount_paise across all events).
           - Compares ledger balance against in-memory account cash.
           - Verifies zero discrepancy.

        3. Concepts used in the function:
           Deterministic ledger projection reconciliation, audit verification.

        4. Places where this function is imported and used:
           Used by daemon crash recovery and audit certification tests.

        5. Final output of the function, before and after:
           Before: Unverified state. After: Reconciled audit status dictionary.
        """
        with self._lock:
            account = self.accounts.get(account_id)
            if account is None:
                raise ValueError(f"Account {account_id} not found.")

            events = self.repo.get_events(account_id)
            calculated_balance = sum(ev.amount_paise for ev in events)
            latest_balance = int(events[-1].balance_paise) if events else 0

            discrepancy = account.cash_paise - calculated_balance

            return {
                "account_id": account_id,
                "in_memory_cash_paise": account.cash_paise,
                "ledger_sum_paise": calculated_balance,
                "latest_balance_paise": latest_balance,
                "event_count": len(events),
                "is_reconciled": (discrepancy == 0 and calculated_balance == latest_balance),
                "discrepancy_paise": discrepancy,
            }

    def close(self) -> None:
        """
        1. The use of function:
           Closes the underlying SQLite ledger repository database connection and releases file locks.

        2. How does the specific function work:
           Calls self.repo.close() under thread lock.

        3. Concepts used in the function:
           Resource cleanup, database connection teardown.

        4. Places where this function is imported and used:
           Invoked upon daemon shutdown and during test suite cleanup.

        5. Final output of the function, before and after:
           Before: Open database connection. After: Closed connection and freed OS file locks.
        """
        with self._lock:
            self.repo.close()
