"""
1. What this file does:
   Implements the Paper Trading, Risk Policy Inspection, and Macro Automated Strategy REST API endpoints
   for the QuantView FastAPI Gateway (Milestones M6-06, M6-14, M6-18, and Release Gate G4).

2. Overall design:
   Coordinates in-memory thread-safe simulation state for manual discretionary paper trading
   and macro automated strategy monitoring:
     - GET /api/v1/paper/accounts: Returns accounts with dynamic equity (cash + unrealized PnL) and free cash.
     - GET /api/v1/paper/risk-policy: Returns active risk limit boundaries (RK-01 to RK-26, RK-06 freeze 1800).
     - GET /api/v1/paper/strategies: Returns automated strategy performance records for macro dashboard view.
     - GET /api/v1/paper/positions: Returns open derivative positions with mark-to-market valuations.
     - POST /api/v1/paper/positions/square-off/{position_id}: Closes single position, computes realized PnL,
       releases margin collateral, and logs audit trade.
     - POST /api/v1/paper/positions/square-off-all: Liquidates all open derivative positions in batch.
     - GET /api/v1/paper/orders: Returns working and historical paper orders.
     - POST /api/v1/paper/orders/cancel/{order_id}: Cancels working pending paper orders.
     - POST /api/v1/paper/orders: Executes instant manual paper order with RK-06 pre-trade risk checks,
       contract price resolution, stop-loss and take-profit chart line calculations.
     - GET /api/v1/paper/trades: Returns itemized historical trade execution logs.

3. Elements in the file:
   - router: FastAPI APIRouter mounted at /api/v1/paper with tag "paper".
   - PaperSimulatorState: Thread-safe repository managing accounts, positions, orders, trades, and strategies.
   - get_paper_state: Accessor helper returning active simulation state repository.
   - reset_paper_state: Test and maintenance helper resetting state to initial baseline.
   - _resolve_contract_fill_price: Helper extracting execution price from lake candles or fallback.
   - _parse_contract_details: Helper resolving symbol, strike, option type, and expiry from contract ID.
   - _update_position_pnl: Helper computing mark-to-market PnL and return percentages.
   - get_paper_accounts: Endpoint handler for account balance summaries.
   - get_paper_account: Endpoint handler for single account balance query.
   - get_paper_risk_policy: Endpoint handler for active risk policy parameters.
   - get_paper_strategies: Endpoint handler for macro strategy telemetry.
   - get_paper_positions: Endpoint handler for active derivative positions.
   - square_off_position: Endpoint handler closing an individual position.
   - square_off_all_positions: Endpoint handler liquidating all open positions.
   - get_paper_orders: Endpoint handler for order history and working orders.
   - cancel_paper_order: Endpoint handler cancelling working orders.
   - place_paper_order: Endpoint handler executing new paper trading orders.
   - get_paper_trades: Endpoint handler for executed trade audit history.

4. Final output of the file:
   - Exported APIRouter instance for registration in services.api.main.
"""

import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, status

from packages.risk.rules import RiskRules
from services.api.deps import get_duckdb
from services.api.schemas.paper import (
    ChartPriceLines,
    PaperAccount,
    PaperOrder,
    PaperOrderRequest,
    PaperOrderResponse,
    PaperPosition,
    PaperStrategyMacro,
    PaperTrade,
    RiskPolicySummary,
)

router = APIRouter(prefix="/api/v1/paper", tags=["paper"])


class PaperSimulatorState:
    """
    1. The use of class:
       Thread-safe in-memory state repository managing manual paper accounts,
       open derivative positions, working orders, executed trades, and macro strategy statuses.

    2. What the class contains:
       - _lock: threading.Lock protecting mutable state structures.
       - accounts: Dict[str, PaperAccount] mapping account_id to account models.
       - positions: Dict[str, PaperPosition] mapping position_id to open position models.
       - orders: List[PaperOrder] tracking chronological orders.
       - trades: List[PaperTrade] tracking filled trade logs.
       - strategies: List[PaperStrategyMacro] tracking active automated strategies for macro view.

    3. Technologies used and why:
       Python standard library threading.Lock for synchronized access across async FastAPI workers.
       Pydantic v2 models for typed, serialized financial payloads.

    4. Key design and overall design of the class:
       Central in-memory ledger isolating manual paper trading execution (ACC-MANUAL-PAPER)
       and macro automated strategy monitoring without persistence side-effects during tests.
    """

    def __init__(self) -> None:
        """
        1. The use of function:
           Initializes the PaperSimulatorState repository with baseline accounts and sample strategies.

        2. How does the specific function work:
           - Sets up threading.Lock.
           - Instantiates default ACC-MANUAL-PAPER account with ₹1,000,000 capital.
           - Instantiates empty collections for positions, orders, and trades.
           - Populates representative macro strategy records for the macro monitor view.

        3. Concepts used in the function:
           State initialization, thread synchronization.

        4. Places where this function is imported and used:
           Invoked at module load and during test state resets.

        5. Final output of the function, before and after:
           Before: Uninitialized memory. After: Ready-to-serve PaperSimulatorState instance.
        """
        self._lock = threading.Lock()
        self.accounts: Dict[str, PaperAccount] = {}
        self.positions: Dict[str, PaperPosition] = {}
        self.orders: List[PaperOrder] = []
        self.trades: List[PaperTrade] = []
        self.strategies: List[PaperStrategyMacro] = []
        self.reset()

    def reset(self) -> None:
        """
        1. The use of function:
           Resets all state attributes to canonical baseline configurations.

        2. How does the specific function work:
           Acquires thread lock, reinstates ACC-MANUAL-PAPER with ₹1,000,000 cash,
           clears open positions, orders, and trades, and re-registers sample automated strategies.

        3. Concepts used in the function:
           State re-initialization, isolation guarantees for testing.

        4. Places where this function is imported and used:
           Called in __init__ and by reset_paper_state().

        5. Final output of the function, before and after:
           Before: Arbitrary mutated state. After: Clean baseline state repository.
        """
        with self._lock:
            self.accounts = {
                "ACC-MANUAL-PAPER": PaperAccount(
                    account_id="ACC-MANUAL-PAPER",
                    name="Manual Paper Account",
                    mode="MANUAL_PAPER",
                    currency="INR",
                    initial_capital_rupees=1000000.0,
                    cash_balance_rupees=1000000.0,
                    margin_reserved_rupees=0.0,
                    free_cash_rupees=1000000.0,
                    unrealized_pnl_rupees=0.0,
                    realized_pnl_rupees=0.0,
                    equity_rupees=1000000.0,
                )
            }
            self.positions = {}
            self.orders = []
            self.trades = []
            self.strategies = [
                PaperStrategyMacro(
                    strategy_id="STRAT-CE-TREND",
                    strategy_name="LongCETrendFollowing",
                    mode="ACTUAL_OPTIONS",
                    status="Running",
                    allocated_lots=4,
                    today_pnl_rupees=12450.0,
                    win_rate_pct=64.2,
                    sharpe_ratio=1.85,
                ),
                PaperStrategyMacro(
                    strategy_id="STRAT-BULL-SPREAD",
                    strategy_name="BullCallSpreadStrategy",
                    mode="UNDERLYING_DIRECTIONAL",
                    status="Warming Up",
                    allocated_lots=2,
                    today_pnl_rupees=0.0,
                    win_rate_pct=58.0,
                    sharpe_ratio=1.42,
                ),
                PaperStrategyMacro(
                    strategy_id="STRAT-PE-MOMENTUM",
                    strategy_name="ShortPutSpreadMomentum",
                    mode="ACTUAL_OPTIONS",
                    status="Stopped",
                    allocated_lots=0,
                    today_pnl_rupees=-2300.0,
                    win_rate_pct=51.5,
                    sharpe_ratio=0.95,
                ),
            ]


_STATE = PaperSimulatorState()


def get_paper_state() -> PaperSimulatorState:
    """
    1. The use of function:
       Returns the shared singleton instance of PaperSimulatorState.

    2. How does the specific function work:
       Returns the module-level _STATE object reference.

    3. Concepts used in the function:
       Singleton pattern, dependency access.

    4. Places where this function is imported and used:
       Imported by router endpoints and automated testing suites.

    5. Final output of the function, before and after:
       Before: None. After: Active PaperSimulatorState singleton reference.
    """
    return _STATE


def reset_paper_state() -> PaperSimulatorState:
    """
    1. The use of function:
       Resets the in-memory simulation repository back to initial state.

    2. How does the specific function work:
       Invokes reset() on the module-level _STATE singleton under thread synchronization.

    3. Concepts used in the function:
       Test fixture isolation, state tear-down.

    4. Places where this function is imported and used:
       Imported by test fixtures and maintenance endpoints.

    5. Final output of the function, before and after:
       Before: Mutated simulation state. After: Clean baseline PaperSimulatorState singleton.
    """
    _STATE.reset()
    return _STATE


def _resolve_contract_fill_price(
    contract_id: str,
    limit_price: Optional[float],
    conn: Optional[duckdb.DuckDBPyConnection] = None,
) -> float:
    """
    1. The use of function:
       Resolves deterministic fill price for paper order execution.

    2. How does the specific function work:
       - If limit_price is specified and positive, honors limit_price.
       - Otherwise attempts to query latest close price from v_candles_options in DuckDB.
       - If lake view is unavailable or returns no rows, defaults to a reasonable option premium (150.0).

    3. Concepts used in the function:
       Quote resolution, graceful degradation, fallback option pricing.

    4. Places where this function is imported and used:
       Called by place_paper_order in services.api.routers.paper.

    5. Final output of the function, before and after:
       Before: Raw contract_id and optional limit_price. After: Validated positive float fill price.
    """
    if limit_price is not None and limit_price > 0.0:
        return float(limit_price)

    if conn is not None:
        try:
            res = conn.execute(
                "SELECT close FROM v_candles_options WHERE contract_id = ? ORDER BY bar_start DESC LIMIT 1",
                [contract_id.strip()],
            ).fetchone()
            if res and res[0] is not None and float(res[0]) > 0.0:
                return float(res[0])

            sym, strike, opt_type, _ = _parse_contract_details(contract_id, conn)
            res2 = conn.execute(
                "SELECT close FROM v_candles_options WHERE symbol = ? AND strike = ? AND option_type = ? ORDER BY bar_start DESC LIMIT 1",
                [sym, strike, opt_type],
            ).fetchone()
            if res2 and res2[0] is not None and float(res2[0]) > 0.0:
                return float(res2[0])

            res3 = conn.execute(
                "SELECT ltp FROM v_snapshots_rows WHERE strike = ? AND option_type = ? AND ltp > 0 ORDER BY received_at DESC LIMIT 1",
                [strike, opt_type],
            ).fetchone()
            if res3 and res3[0] is not None and float(res3[0]) > 0.0:
                return float(res3[0])
        except duckdb.Error:
            pass

    return 150.0


def _parse_contract_details(
    contract_id: str,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
) -> Tuple[str, float, str, str]:
    """
    1. The use of function:
       Resolves symbol, strike, option_type, and expiry for a contract identifier.

    2. How does the specific function work:
       - First attempts to lookup contract metadata from v_candles_options.
       - If not found in lake, parses standard identifier conventions (e.g. OPT-NIFTY-20250109-22500-CE or NIFTY25JAN23000CE).
       - Falls back to safe defaults (symbol='NIFTY', strike=23000.0, option_type='CE', expiry='2025-01-30').

    3. Concepts used in the function:
       Metadata resolution, contract string parsing, fallback symbol derivation.

    4. Places where this function is imported and used:
       Called by place_paper_order in services.api.routers.paper.

    5. Final output of the function, before and after:
       Before: contract_id string. After: Tuple of (symbol, strike, option_type, expiry).
    """
    if conn is not None:
        try:
            res = conn.execute(
                "SELECT symbol, strike, option_type, CAST(expiry AS VARCHAR) "
                "FROM v_candles_options WHERE contract_id = ? LIMIT 1",
                [contract_id.strip()],
            ).fetchone()
            if res and len(res) == 4 and res[0] is not None:
                return str(res[0]), float(res[1]), str(res[2]), str(res[3])
        except duckdb.Error:
            pass

    parts = contract_id.strip().split("-")
    if len(parts) >= 5 and parts[0].upper() == "OPT":
        symbol = parts[1].upper()
        raw_expiry = parts[2]
        if len(raw_expiry) == 8 and raw_expiry.isdigit():
            expiry = f"{raw_expiry[:4]}-{raw_expiry[4:6]}-{raw_expiry[6:]}"
        else:
            expiry = raw_expiry
        try:
            strike = float(parts[3])
        except ValueError:
            strike = 23000.0
        option_type = parts[4].upper()
        return symbol, strike, option_type, expiry

    match = re.search(r"([A-Z]+)[-_ ]?(\d{4}-?\d{2}-?\d{2}|\d{2}[A-Z]{3})?[-_ ]?(\d+(?:\.\d+)?)[-_ ]?([CP]E)", contract_id.upper())
    if match:
        symbol = match.group(1)
        raw_expiry = match.group(2) or "2025-01-30"
        strike = float(match.group(3))
        option_type = match.group(4)
        return symbol, strike, option_type, raw_expiry

    return "NIFTY", 23000.0, "CE", "2025-01-30"


def _update_position_pnl(pos: PaperPosition) -> None:
    """
    1. The use of function:
       Updates mark-to-market unrealized PnL and percentage for a paper position.

    2. How does the specific function work:
       - Calculates pnl_rupees based on side (BUY: (current - entry) * qty, SELL: (entry - current) * qty).
       - Calculates pnl_pct based on entry_price.
       - Updates pos.pnl_rupees and pos.pnl_pct in place.

    3. Concepts used in the function:
       Mark-to-market valuation, directional derivative PnL accounting.

    4. Places where this function is imported and used:
       Internal helper in services.api.routers.paper.

    5. Final output of the function, before and after:
       Before: Position with previous PnL. After: Position with updated mark-to-market PnL.
    """
    if pos.side == "BUY":
        pos.pnl_rupees = round((pos.current_price - pos.entry_price) * pos.quantity, 2)
        pos.pnl_pct = round(((pos.current_price - pos.entry_price) / pos.entry_price) * 100.0, 2) if pos.entry_price > 0 else 0.0
    else:
        pos.pnl_rupees = round((pos.entry_price - pos.current_price) * pos.quantity, 2)
        pos.pnl_pct = round(((pos.entry_price - pos.current_price) / pos.entry_price) * 100.0, 2) if pos.entry_price > 0 else 0.0


@router.get(
    "/accounts",
    response_model=List[PaperAccount],
    summary="List Paper Trading Accounts",
    description="Returns registered paper trading accounts with dynamic equity and margin balances.",
)
def get_paper_accounts() -> List[PaperAccount]:
    """
    1. The use of function:
       FastAPI endpoint returning active paper trading accounts with computed financial balances.

    2. How does the specific function work:
       - Acquires thread lock on simulation state.
       - Recomputes unrealized PnL from active positions for each account.
       - Recomputes equity = cash_balance + unrealized_pnl.
       - Recomputes free_cash = cash_balance - margin_reserved.
       - Returns serialized list of PaperAccount models.

    3. Concepts used in the function:
       Mark-to-market portfolio accounting, thread-safe state inspection.

    4. Places where this function is imported and used:
       Mounted under GET /api/v1/paper/accounts.

    5. Final output of the function, before and after:
       Before: Query dispatch. After: List of PaperAccount instances.
    """
    state = get_paper_state()
    with state._lock:
        accounts_out: List[PaperAccount] = []
        for acc in state.accounts.values():
            pos_list = [p for p in state.positions.values() if p.account_id == acc.account_id]
            for p in pos_list:
                _update_position_pnl(p)
            acc.unrealized_pnl_rupees = round(sum(p.pnl_rupees for p in pos_list), 2)
            acc.equity_rupees = round(acc.cash_balance_rupees + acc.unrealized_pnl_rupees, 2)
            acc.free_cash_rupees = round(acc.cash_balance_rupees - acc.margin_reserved_rupees, 2)
            accounts_out.append(acc.model_copy())
        return accounts_out


@router.get(
    "/account",
    response_model=PaperAccount,
    summary="Get Single Paper Trading Account",
    description="Returns account balances and dynamic equity for a specific account.",
)
def get_paper_account(
    account_id: str = Query(default="ACC-MANUAL-PAPER", description="Account identifier"),
) -> PaperAccount:
    """
    1. The use of function:
       FastAPI endpoint returning a single active paper trading account with computed financial balances.

    2. How does the specific function work:
       - Acquires thread lock on simulation state.
       - Looks up account by account_id; raises HTTP 404 if not found.
       - Recomputes unrealized PnL from active positions for this account.
       - Recomputes equity = cash_balance + unrealized_pnl.
       - Recomputes free_cash = cash_balance - margin_reserved.
       - Returns serialized PaperAccount model.

    3. Concepts used in the function:
       Single account query, dynamic ledger equity computation.

    4. Places where this function is imported and used:
       Mounted under GET /api/v1/paper/account.

    5. Final output of the function, before and after:
       Before: Account ID string. After: Validated PaperAccount model instance.
    """
    state = get_paper_state()
    with state._lock:
        acc = state.accounts.get(account_id)
        if not acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account '{account_id}' not found",
            )
        pos_list = [p for p in state.positions.values() if p.account_id == acc.account_id]
        for p in pos_list:
            _update_position_pnl(p)
        acc.unrealized_pnl_rupees = round(sum(p.pnl_rupees for p in pos_list), 2)
        acc.equity_rupees = round(acc.cash_balance_rupees + acc.unrealized_pnl_rupees, 2)
        acc.free_cash_rupees = round(acc.cash_balance_rupees - acc.margin_reserved_rupees, 2)
        return acc.model_copy()


@router.get(
    "/risk-policy",
    response_model=RiskPolicySummary,
    summary="Active Risk Policy Summary",
    description="Returns active exchange and firm risk limit parameters including RK-06 freeze quantity.",
)
@router.get(
    "/risk-rules",
    response_model=RiskPolicySummary,
    summary="Active Risk Rules Summary (Alias)",
    description="Returns active exchange and firm risk limit parameters including RK-06 freeze quantity.",
)
def get_paper_risk_policy() -> RiskPolicySummary:
    """
    1. The use of function:
       FastAPI endpoint returning active risk parameters governing pre-trade validation.

    2. How does the specific function work:
       Instantiates canonical RiskRules model from packages.risk.rules and maps parameters
       to the public RiskPolicySummary response model with freeze_quantity=1800 (RK-06)
       and account_allocation_mode='ISOLATED'.

    3. Concepts used in the function:
       Risk policy telemetry, canonical risk governance.

    4. Places where this function is imported and used:
       Mounted under GET /api/v1/paper/risk-policy and GET /api/v1/paper/risk-rules.

    5. Final output of the function, before and after:
       Before: Query dispatch. After: RiskPolicySummary instance.
    """
    rules = RiskRules()
    return RiskPolicySummary(
        freeze_quantity=rules.freeze_quantity,
        advisory_lot_ceiling=rules.freeze_quantity // 25,
        max_loss_per_day_rupees=50000.0,
        max_drawdown_pct=rules.max_drawdown_pct or 10.0,
        trading_window_start=rules.trading_window_start,
        trading_window_end=rules.trading_window_end,
        margin_mode="THEORETICAL",
        account_allocation_mode="ISOLATED",
    )


@router.get(
    "/strategies",
    response_model=List[PaperStrategyMacro],
    summary="Macro Automated Strategies",
    description="Returns high-level automated paper trading strategy records for the macro monitor table.",
)
def get_paper_strategies() -> List[PaperStrategyMacro]:
    """
    1. The use of function:
       FastAPI endpoint returning macro automated strategy monitoring records.

    2. How does the specific function work:
       Acquires thread lock on simulation state and returns copies of registered PaperStrategyMacro records.

    3. Concepts used in the function:
       Macro dashboard monitoring, multi-strategy telemetry.

    4. Places where this function is imported and used:
       Mounted under GET /api/v1/paper/strategies.

    5. Final output of the function, before and after:
       Before: Query dispatch. After: List of PaperStrategyMacro models.
    """
    state = get_paper_state()
    with state._lock:
        return [s.model_copy() for s in state.strategies]


@router.get(
    "/positions",
    response_model=List[PaperPosition],
    summary="Open Paper Positions",
    description="Returns active open derivative positions with mark-to-market PnL values.",
)
def get_paper_positions(
    account_id: Optional[str] = Query(default=None, description="Optional filter by account ID"),
) -> List[PaperPosition]:
    """
    1. The use of function:
       FastAPI endpoint returning open paper positions.

    2. How does the specific function work:
       - Acquires thread lock.
       - Updates mark-to-market PnL for each position.
       - Filters by account_id if specified.
       - Returns list of open PaperPosition models.

    3. Concepts used in the function:
       Derivative position valuation, portfolio monitoring.

    4. Places where this function is imported and used:
       Mounted under GET /api/v1/paper/positions.

    5. Final output of the function, before and after:
       Before: Optional account filter. After: List of active PaperPosition models.
    """
    state = get_paper_state()
    with state._lock:
        positions_out: List[PaperPosition] = []
        for pos in state.positions.values():
            if account_id and pos.account_id != account_id:
                continue
            _update_position_pnl(pos)
            positions_out.append(pos.model_copy())
        return positions_out


@router.post(
    "/positions/square-off/{position_id}",
    summary="Square Off Open Position",
    description="Closes specified position at current market price, realizes PnL, and releases margin.",
)
@router.post(
    "/square-off/{position_id}",
    summary="Square Off Open Position (Alias)",
    description="Closes specified position at current market price, realizes PnL, and releases margin.",
)
def square_off_position(position_id: str) -> Dict[str, Any]:
    """
    1. The use of function:
       FastAPI endpoint closing an individual open derivative paper position.

    2. How does the specific function work:
       - Looks up target position by position_id; raises HTTP 404 if not found.
       - Calculates realized PnL from entry and current prices.
       - Adjusts account cash balance, cumulative realized PnL, and releases reserved margin collateral.
       - Logs audit trade record in trades log and filled order in orders log.
       - Removes position from active positions repository.

    3. Concepts used in the function:
       Position liquidation, PnL realization, margin release, audit logging.

    4. Places where this function is imported and used:
       Mounted under POST /api/v1/paper/positions/square-off/{position_id}.

    5. Final output of the function, before and after:
       Before: Target position_id. After: Confirmation dictionary with realized PnL.
    """
    state = get_paper_state()
    with state._lock:
        pos = state.positions.get(position_id)
        if not pos:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Position '{position_id}' not found",
            )

        _update_position_pnl(pos)
        realized_pnl = pos.pnl_rupees
        acc = state.accounts.get(pos.account_id)
        if acc:
            acc.cash_balance_rupees = round(acc.cash_balance_rupees + realized_pnl, 2)
            acc.realized_pnl_rupees = round(acc.realized_pnl_rupees + realized_pnl, 2)
            margin_release = pos.entry_price * pos.quantity
            acc.margin_reserved_rupees = max(0.0, round(acc.margin_reserved_rupees - margin_release, 2))
            acc.free_cash_rupees = round(acc.cash_balance_rupees - acc.margin_reserved_rupees, 2)

        closing_side = "SELL" if pos.side == "BUY" else "BUY"
        now_ts = int(time.time())
        trade = PaperTrade(
            trade_id=f"TRD-{uuid.uuid4().hex[:8].upper()}",
            account_id=pos.account_id,
            contract_id=pos.contract_id,
            side=closing_side,
            quantity=pos.quantity,
            price=pos.current_price,
            timestamp=now_ts,
            pnl_rupees=realized_pnl,
            statutory_fees_rupees=23.60,
        )
        state.trades.append(trade)

        order = PaperOrder(
            order_id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
            account_id=pos.account_id,
            contract_id=pos.contract_id,
            side=closing_side,
            quantity=pos.quantity,
            order_type="MARKET",
            price=pos.current_price,
            status="FILLED",
            created_at=now_ts,
            filled_at=now_ts,
        )
        state.orders.append(order)

        del state.positions[position_id]

        return {
            "status": "CLOSED",
            "position_id": position_id,
            "realized_pnl_rupees": realized_pnl,
            "message": f"Position {position_id} squared off successfully",
        }


@router.post(
    "/positions/square-off-all",
    summary="Square Off All Open Positions",
    description="Liquidates all active open derivative positions across all accounts in a single atomic batch.",
)
@router.post(
    "/square-off-all",
    summary="Square Off All Open Positions (Alias)",
    description="Liquidates all active open derivative positions across all accounts in a single atomic batch.",
)
def square_off_all_positions(
    account_id: Optional[str] = Query(default=None, description="Optional account filter"),
) -> Dict[str, Any]:
    """
    1. The use of function:
       FastAPI endpoint liquidating all open derivative paper positions in batch.

    2. How does the specific function work:
       - Iterates through open positions matching optional account_id.
       - Invokes square-off mechanics on each: realizes PnL, updates cash, releases margin, logs audit records.
       - Returns aggregate count of closed positions and cumulative realized PnL.

    3. Concepts used in the function:
       Emergency portfolio liquidation, atomic batch execution.

    4. Places where this function is imported and used:
       Mounted under POST /api/v1/paper/positions/square-off-all.

    5. Final output of the function, before and after:
       Before: Batch request. After: Summary dictionary with count and total realized PnL.
    """
    state = get_paper_state()
    with state._lock:
        target_ids = [
            pid for pid, p in state.positions.items()
            if not account_id or p.account_id == account_id
        ]
        total_pnl = 0.0
        now_ts = int(time.time())

        for pid in target_ids:
            pos = state.positions[pid]
            _update_position_pnl(pos)
            realized_pnl = pos.pnl_rupees
            total_pnl += realized_pnl

            acc = state.accounts.get(pos.account_id)
            if acc:
                acc.cash_balance_rupees = round(acc.cash_balance_rupees + realized_pnl, 2)
                acc.realized_pnl_rupees = round(acc.realized_pnl_rupees + realized_pnl, 2)
                margin_release = pos.entry_price * pos.quantity
                acc.margin_reserved_rupees = max(0.0, round(acc.margin_reserved_rupees - margin_release, 2))
                acc.free_cash_rupees = round(acc.cash_balance_rupees - acc.margin_reserved_rupees, 2)

            closing_side = "SELL" if pos.side == "BUY" else "BUY"
            state.trades.append(
                PaperTrade(
                    trade_id=f"TRD-{uuid.uuid4().hex[:8].upper()}",
                    account_id=pos.account_id,
                    contract_id=pos.contract_id,
                    side=closing_side,
                    quantity=pos.quantity,
                    price=pos.current_price,
                    timestamp=now_ts,
                    pnl_rupees=realized_pnl,
                    statutory_fees_rupees=23.60,
                )
            )
            state.orders.append(
                PaperOrder(
                    order_id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
                    account_id=pos.account_id,
                    contract_id=pos.contract_id,
                    side=closing_side,
                    quantity=pos.quantity,
                    order_type="MARKET",
                    price=pos.current_price,
                    status="FILLED",
                    created_at=now_ts,
                    filled_at=now_ts,
                )
            )
            del state.positions[pid]

        return {
            "status": "SUCCESS",
            "closed_positions_count": len(target_ids),
            "total_realized_pnl_rupees": round(total_pnl, 2),
            "message": f"Successfully squared off {len(target_ids)} open positions",
        }


@router.get(
    "/orders",
    response_model=List[PaperOrder],
    summary="Working and Historical Orders",
    description="Returns list of submitted, working, cancelled, and filled paper orders.",
)
def get_paper_orders(
    account_id: Optional[str] = Query(default=None, description="Optional account filter"),
) -> List[PaperOrder]:
    """
    1. The use of function:
       FastAPI endpoint returning historical and working paper orders.

    2. How does the specific function work:
       Acquires thread lock, filters orders by optional account_id, and returns copies in reverse chronological order.

    3. Concepts used in the function:
       Order book history query.

    4. Places where this function is imported and used:
       Mounted under GET /api/v1/paper/orders.

    5. Final output of the function, before and after:
       Before: Query dispatch. After: List of PaperOrder models.
    """
    state = get_paper_state()
    with state._lock:
        if account_id:
            return [o.model_copy() for o in reversed(state.orders) if o.account_id == account_id]
        return [o.model_copy() for o in reversed(state.orders)]


@router.post(
    "/orders/cancel/{order_id}",
    summary="Cancel Working Order",
    description="Cancels an active pending paper order.",
)
def cancel_paper_order(order_id: str) -> Dict[str, Any]:
    """
    1. The use of function:
       FastAPI endpoint cancelling an unfulfilled pending paper order.

    2. How does the specific function work:
       - Searches order repository by order_id; raises HTTP 404 if not found.
       - If status is 'PENDING', transitions status to 'CANCELLED'.
       - If status is already terminal ('FILLED', 'CANCELLED', 'REJECTED'), returns idempotent status.

    3. Concepts used in the function:
       Order lifecycle management, idempotent cancellation.

    4. Places where this function is imported and used:
       Mounted under POST /api/v1/paper/orders/cancel/{order_id}.

    5. Final output of the function, before and after:
       Before: Target order_id. After: Confirmation dictionary with cancellation status.
    """
    state = get_paper_state()
    with state._lock:
        found_order: Optional[PaperOrder] = None
        for o in state.orders:
            if o.order_id == order_id:
                found_order = o
                break

        if not found_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{order_id}' not found",
            )

        if found_order.status == "PENDING":
            found_order.status = "CANCELLED"
            return {
                "status": "CANCELLED",
                "order_id": order_id,
                "message": "Order cancelled successfully",
            }

        return {
            "status": found_order.status,
            "order_id": order_id,
            "message": f"Order is already {found_order.status}",
        }


@router.post(
    "/orders",
    response_model=PaperOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit Paper Trading Order",
    description="Submits and immediately fills a paper order, returning computed chart price lines.",
)
def place_paper_order(
    order_req: PaperOrderRequest,
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb),
) -> PaperOrderResponse:
    """
    1. The use of function:
       FastAPI endpoint executing an instant manual paper order submission.

    2. How does the specific function work:
       - Evaluates pre-trade risk policy rules:
         * Rejects if quantity > 1800 with HTTP 422 (RK-06 freeze limit).
         * Rejects if quantity <= 0 or not a multiple of lot size 25 with HTTP 422.
       - Resolves fill price from DuckDB options lake view or fallback premium.
       - Computes stop-loss (SL) and take-profit (TP) price coordinates based on side.
       - Reserves margin collateral, updates account ledger, and registers open position.
       - Emits audit records for filled order and executed trade.
       - Returns PaperOrderResponse containing ChartPriceLines coordinates for immediate chart overlay.

    3. Concepts used in the function:
       Instant simulated matching engine, pre-trade risk validation (RK-06), chart lines calculation.

    4. Places where this function is imported and used:
       Mounted under POST /api/v1/paper/orders.

    5. Final output of the function, before and after:
       Before: Validated PaperOrderRequest. After: PaperOrderResponse containing chart price lines.
    """
    if order_req.quantity > 1800:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="RK-06: Order exceeds freeze limit 1800",
        )
    if order_req.quantity <= 0 or order_req.quantity % 25 != 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Quantity must be a positive multiple of lot size 25",
        )

    fill_price = _resolve_contract_fill_price(
        contract_id=order_req.contract_id,
        limit_price=order_req.limit_price,
        conn=conn,
    )

    sl: Optional[float] = None
    if order_req.stop_loss_pct is not None:
        if order_req.side == "BUY":
            sl = round(fill_price * (1.0 - order_req.stop_loss_pct / 100.0), 2)
        else:
            sl = round(fill_price * (1.0 + order_req.stop_loss_pct / 100.0), 2)
    elif order_req.stop_loss_price is not None:
        sl = round(order_req.stop_loss_price, 2)

    tp: Optional[float] = None
    if order_req.take_profit_pct is not None:
        if order_req.side == "BUY":
            tp = round(fill_price * (1.0 + order_req.take_profit_pct / 100.0), 2)
        else:
            tp = round(fill_price * (1.0 - order_req.take_profit_pct / 100.0), 2)
    elif order_req.take_profit_price is not None:
        tp = round(order_req.take_profit_price, 2)

    chart_lines = ChartPriceLines(
        entry=round(fill_price, 2),
        stop_loss=sl,
        take_profit=tp,
    )

    symbol, strike, option_type, expiry = _parse_contract_details(
        contract_id=order_req.contract_id,
        conn=conn,
    )

    state = get_paper_state()
    now_ts = int(time.time())
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    pos_id = f"POS-{uuid.uuid4().hex[:8].upper()}"
    trade_id = f"TRD-{uuid.uuid4().hex[:8].upper()}"

    with state._lock:
        acc = state.accounts.get(order_req.account_id)
        if not acc:
            acc = PaperAccount(
                account_id=order_req.account_id,
                name=f"Account {order_req.account_id}",
                mode="MANUAL_PAPER",
                initial_capital_rupees=1000000.0,
                cash_balance_rupees=1000000.0,
                margin_reserved_rupees=0.0,
                free_cash_rupees=1000000.0,
                unrealized_pnl_rupees=0.0,
                realized_pnl_rupees=0.0,
                equity_rupees=1000000.0,
            )
            state.accounts[order_req.account_id] = acc

        margin_to_reserve = round(fill_price * order_req.quantity, 2)
        acc.margin_reserved_rupees = round(acc.margin_reserved_rupees + margin_to_reserve, 2)
        acc.free_cash_rupees = round(acc.cash_balance_rupees - acc.margin_reserved_rupees, 2)

        new_position = PaperPosition(
            position_id=pos_id,
            account_id=order_req.account_id,
            contract_id=order_req.contract_id,
            symbol=symbol,
            strike=strike,
            option_type=option_type,
            expiry=expiry,
            quantity=order_req.quantity,
            side=order_req.side,
            entry_price=fill_price,
            current_price=fill_price,
            pnl_rupees=0.0,
            pnl_pct=0.0,
            entry_time=now_ts,
        )
        state.positions[pos_id] = new_position

        filled_order = PaperOrder(
            order_id=order_id,
            account_id=order_req.account_id,
            contract_id=order_req.contract_id,
            side=order_req.side,
            quantity=order_req.quantity,
            order_type=order_req.order_type,
            price=fill_price,
            status="FILLED",
            created_at=now_ts,
            filled_at=now_ts,
        )
        state.orders.append(filled_order)

        executed_trade = PaperTrade(
            trade_id=trade_id,
            account_id=order_req.account_id,
            contract_id=order_req.contract_id,
            side=order_req.side,
            quantity=order_req.quantity,
            price=fill_price,
            timestamp=now_ts,
            pnl_rupees=0.0,
            statutory_fees_rupees=23.60,
        )
        state.trades.append(executed_trade)

    return PaperOrderResponse(
        order_id=order_id,
        account_id=order_req.account_id,
        contract_id=order_req.contract_id,
        status="FILLED",
        side=order_req.side,
        quantity=order_req.quantity,
        fill_price=round(fill_price, 2),
        chart_lines=chart_lines,
        message="Paper order executed and filled successfully",
        timestamp=now_ts,
    )


@router.get(
    "/trades",
    response_model=List[PaperTrade],
    summary="Executed Trade History",
    description="Returns itemized chronological audit records of all executed paper trades.",
)
def get_paper_trades(
    account_id: Optional[str] = Query(default=None, description="Optional account filter"),
) -> List[PaperTrade]:
    """
    1. The use of function:
       FastAPI endpoint returning executed paper trade transactions.

    2. How does the specific function work:
       Acquires thread lock, filters trade records by optional account_id, and returns reverse chronological list.

    3. Concepts used in the function:
       Trade ledger audit logging.

    4. Places where this function is imported and used:
       Mounted under GET /api/v1/paper/trades.

    5. Final output of the function, before and after:
       Before: Query dispatch. After: List of PaperTrade audit models.
    """
    state = get_paper_state()
    with state._lock:
        if account_id:
            return [t.model_copy() for t in reversed(state.trades) if t.account_id == account_id]
        return [t.model_copy() for t in reversed(state.trades)]
