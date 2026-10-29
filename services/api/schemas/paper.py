"""
1. What this file does:
   Defines Pydantic data schemas and response containers for manual paper trading,
   discretionary execution, risk policy inspection, and macro automated strategy monitoring
   (Milestones M6-06, M6-14, M6-18, and Release Gate G4).

2. Overall design:
   Provides strongly typed request models and immutable response containers:
     - PaperAccount: Account financial ledger snapshot with dynamic equity and margin balances.
     - PaperPosition: Real-time open derivative position with mark-to-market PnL metrics.
     - ChartPriceLines: Visual entry price, stop-loss, and take-profit chart overlay coordinates.
     - PaperOrderRequest: Validated payload for discretionary or one-click paper order submission.
     - PaperOrderResponse: Immediate fill confirmation payload containing computed chart lines.
     - PaperOrder: Historical and working order state container.
     - PaperTrade: Executed trade audit record.
     - PaperStrategyMacro: High-level automated strategy monitoring record for macro dashboard view.
     - RiskPolicySummary: Active exchange and firm risk limit boundaries (RK-01 to RK-26).

3. Elements in the file:
   - PaperAccount: Account ledger summary schema.
   - PaperPosition: Derivative position tracking schema.
   - ChartPriceLines: Lightweight Charts price lines schema.
   - PaperOrderRequest: Discretionary order submission schema.
   - PaperOrderResponse: Order execution and fill confirmation schema.
   - PaperOrder: Working and historical order schema.
   - PaperTrade: Executed trade transaction schema.
   - PaperStrategyMacro: Macro strategy telemetry schema.
   - RiskPolicySummary: Pre-trade risk policy configuration schema.

4. Final output of the file:
   - Exported Pydantic schemas for the QuantView paper trading and risk API gateway.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChartPriceLines(BaseModel):
    """
    1. The use of class:
       Coordinates for rendering entry price, stop-loss, and take-profit horizontal lines on charts.

    2. What the class contains:
       - entry: Execution fill price level.
       - stop_loss: Computed stop-loss price boundary level.
       - take_profit: Computed take-profit price boundary level.

    3. Technologies used and why:
       Pydantic BaseModel with ConfigDict for strict schema serialization to TradingView Lightweight Charts.

    4. Key design and overall design of the class:
       Provides unified visual price coordinates immediately following order submission.
    """
    model_config = ConfigDict(extra="ignore")

    entry: float = Field(..., description="Executed fill price level")
    stop_loss: Optional[float] = Field(default=None, description="Stop-loss price level")
    take_profit: Optional[float] = Field(default=None, description="Take-profit price level")


class PaperAccount(BaseModel):
    """
    1. The use of class:
       Represents an active paper trading account ledger with balance, margin, and equity metrics.

    2. What the class contains:
       - account_id: Unique account identifier string (e.g. ACC-MANUAL-PAPER).
       - name: Human-readable account display name.
       - mode: Trading operational mode (MANUAL_PAPER).
       - currency: Settlement fiat currency denomination (INR).
       - initial_capital_rupees: Initial starting capital allocation in INR.
       - cash_balance_rupees: Net cash balance in INR.
       - margin_reserved_rupees: Collateral margin reserved for open positions in INR.
       - free_cash_rupees: Available unreserved capital in INR.
       - unrealized_pnl_rupees: Net unrealized mark-to-market PnL across open positions in INR.
       - realized_pnl_rupees: Cumulative realized PnL across closed trades in INR.
       - equity_rupees: Total account mark-to-market equity in INR.

    3. Technologies used and why:
       Pydantic BaseModel for JSON serialization and client validation.

    4. Key design and overall design of the class:
       Enforces the dynamic equity formula: equity = cash_balance + unrealized_pnl.
    """
    model_config = ConfigDict(extra="ignore")

    account_id: str = Field(default="ACC-MANUAL-PAPER", description="Unique account identifier")
    name: str = Field(default="Manual Paper Account", description="Account display name")
    mode: str = Field(default="MANUAL_PAPER", description="Operational trading mode")
    currency: str = Field(default="INR", description="Denomination currency")
    initial_capital_rupees: float = Field(default=1000000.0, description="Starting capital in INR")
    cash_balance_rupees: float = Field(default=1000000.0, description="Available cash balance in INR")
    margin_reserved_rupees: float = Field(default=0.0, description="Reserved margin collateral in INR")
    free_cash_rupees: float = Field(default=1000000.0, description="Unreserved cash balance in INR")
    unrealized_pnl_rupees: float = Field(default=0.0, description="Net unrealized PnL in INR")
    realized_pnl_rupees: float = Field(default=0.0, description="Cumulative realized PnL in INR")
    equity_rupees: float = Field(default=1000000.0, description="Total account equity in INR")


class PaperPosition(BaseModel):
    """
    1. The use of class:
       Represents an active open derivative paper position with real-time mark-to-market PnL.

    2. What the class contains:
       - position_id: Unique position identifier.
       - account_id: Associated account identifier.
       - contract_id: Unique option or underlying contract identifier.
       - symbol: Root underlying symbol (e.g. NIFTY).
       - strike: Option strike price in INR.
       - option_type: Option contract type ('CE' or 'PE').
       - expiry: ISO expiry date string (YYYY-MM-DD).
       - quantity: Active position size in lots/shares.
       - side: Position direction ('BUY' for long, 'SELL' for short).
       - entry_price: Volume-weighted execution fill price in INR.
       - current_price: Mark-to-market latest price in INR.
       - pnl_rupees: Net open profit or loss in INR.
       - pnl_pct: Percentage return on investment relative to entry value.
       - entry_time: Unix epoch timestamp seconds of initial position fill.

    3. Technologies used and why:
       Pydantic BaseModel with ConfigDict for micro console table rendering.

    4. Key design and overall design of the class:
       Encapsulates all attributes required for one-click square-off and risk monitoring.
    """
    model_config = ConfigDict(extra="ignore")

    position_id: str = Field(..., description="Unique position identifier")
    account_id: str = Field(default="ACC-MANUAL-PAPER", description="Account identifier")
    contract_id: str = Field(..., description="Instrument contract identifier")
    symbol: str = Field(..., description="Root underlying symbol")
    strike: float = Field(..., description="Option strike price")
    option_type: str = Field(..., description="Option type ('CE' | 'PE')")
    expiry: str = Field(..., description="Contract expiry date (YYYY-MM-DD)")
    quantity: int = Field(..., gt=0, description="Open contract quantity")
    side: str = Field(..., description="Position direction ('BUY' | 'SELL')")
    entry_price: float = Field(..., description="Entry fill price in INR")
    current_price: float = Field(..., description="Current market price in INR")
    pnl_rupees: float = Field(default=0.0, description="Unrealized mark-to-market PnL in INR")
    pnl_pct: float = Field(default=0.0, description="Unrealized PnL percentage")
    entry_time: int = Field(..., description="Entry timestamp in UTC epoch seconds")


class PaperOrderRequest(BaseModel):
    """
    1. The use of class:
       Validates payload parameters for submitting a discretionary or one-click paper order.

    2. What the class contains:
       - account_id: Target account identifier (default 'ACC-MANUAL-PAPER').
       - contract_id: Target contract identifier (e.g. OPT-NIFTY-20250109-22500-CE).
       - side: Order side ('BUY' or 'SELL').
       - quantity: Order quantity in contracts (must be multiple of 25, <= 1800 freeze limit).
       - order_type: Execution type ('MARKET' or 'LIMIT').
       - limit_price: Optional limit execution price.
       - stop_loss_pct: Optional stop-loss percentage offset relative to fill price.
       - take_profit_pct: Optional take-profit percentage offset relative to fill price.

    3. Technologies used and why:
       Pydantic BaseModel with strict field validators enforcing exchange lot size and RK-06 freeze ceiling.

    4. Key design and overall design of the class:
       Serves as the primary ingress model for one-click Option Chain and chart trade execution.
    """
    model_config = ConfigDict(extra="ignore")

    account_id: str = Field(default="ACC-MANUAL-PAPER", description="Target paper account ID")
    contract_id: str = Field(..., description="Unique contract identifier")
    side: str = Field(..., description="Order side ('BUY' | 'SELL')")
    quantity: int = Field(default=25, description="Contract quantity (must be positive multiple of 25, <= 1800)")
    order_type: str = Field(default="MARKET", description="Order execution type ('MARKET' | 'LIMIT')")
    limit_price: Optional[float] = Field(default=None, description="Limit price for LIMIT orders")
    stop_loss_pct: Optional[float] = Field(default=None, description="Stop-loss percentage relative to entry")
    take_profit_pct: Optional[float] = Field(default=None, description="Take-profit percentage relative to entry")
    stop_loss_price: Optional[float] = Field(default=None, description="Absolute stop-loss price level")
    take_profit_price: Optional[float] = Field(default=None, description="Absolute take-profit price level")

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        """
        1. The use of function:
           Validates lot size divisibility and exchange hard freeze limit (RK-06).

        2. How does the specific function work:
           - Verifies v > 0.
           - Verifies v is a multiple of standard NIFTY lot size (25).
           - Enforces RK-06 freeze ceiling of 1800 contracts.

        3. Concepts used in the function:
           Pydantic field validation, pre-trade exchange boundary enforcement.

        4. Places where this function is imported and used:
           Invoked automatically during PaperOrderRequest deserialization.

        5. Final output of the function, before and after:
           Before: Raw integer quantity. After: Validated quantity or raises ValueError.
        """
        if v <= 0:
            raise ValueError("Quantity must be greater than 0")
        if v % 25 != 0:
            raise ValueError("Quantity must be a positive multiple of lot size 25")
        if v > 1800:
            raise ValueError("RK-06: Order exceeds freeze limit 1800")
        return v

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        """
        1. The use of function:
           Normalizes and validates order side direction.

        2. How does the specific function work:
           Strips whitespace and converts to uppercase, asserting membership in ('BUY', 'SELL').

        3. Concepts used in the function:
           String normalization, domain enumeration validation.

        4. Places where this function is imported and used:
           Invoked automatically during PaperOrderRequest deserialization.

        5. Final output of the function, before and after:
           Before: Raw string. After: Normalized 'BUY' or 'SELL'.
        """
        v_upper = v.strip().upper()
        if v_upper not in ("BUY", "SELL"):
            raise ValueError("Side must be 'BUY' or 'SELL'")
        return v_upper

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        """
        1. The use of function:
           Normalizes and validates order execution type.

        2. How does the specific function work:
           Strips whitespace and converts to uppercase, asserting membership in ('MARKET', 'LIMIT').

        3. Concepts used in the function:
           Order type validation.

        4. Places where this function is imported and used:
           Invoked automatically during PaperOrderRequest deserialization.

        5. Final output of the function, before and after:
           Before: Raw string. After: Normalized 'MARKET' or 'LIMIT'.
        """
        v_upper = v.strip().upper()
        if v_upper not in ("MARKET", "LIMIT"):
            raise ValueError("Order type must be 'MARKET' or 'LIMIT'")
        return v_upper


class PaperOrderResponse(BaseModel):
    """
    1. The use of class:
       Immediate response envelope returned following paper order placement.

    2. What the class contains:
       - order_id: Unique assigned order identifier string.
       - account_id: Associated account identifier string.
       - contract_id: Executed contract identifier string.
       - status: Execution state ('FILLED', 'PENDING', 'REJECTED').
       - side: Order side direction ('BUY' | 'SELL').
       - quantity: Filled contract quantity.
       - fill_price: Executed fill price level in INR.
       - chart_lines: Coordinate lines for rendering entry, SL, and TP on charts.
       - message: Human-readable execution status narrative.
       - timestamp: Unix epoch timestamp seconds of execution.

    3. Technologies used and why:
       Pydantic BaseModel for deterministic JSON API serialization.

    4. Key design and overall design of the class:
       Returns chart price lines directly so the UI can plot markers without second round-trip.
    """
    model_config = ConfigDict(extra="ignore")

    order_id: str = Field(..., description="Unique order identifier")
    account_id: str = Field(..., description="Target account identifier")
    contract_id: str = Field(..., description="Contract identifier")
    status: str = Field(..., description="Order execution status ('FILLED' | 'PENDING' | 'REJECTED')")
    side: str = Field(..., description="Order side ('BUY' | 'SELL')")
    quantity: int = Field(..., description="Executed order quantity")
    fill_price: float = Field(..., description="Execution fill price in INR")
    chart_lines: ChartPriceLines = Field(..., description="Chart price lines overlay levels")
    message: str = Field(default="Paper order executed successfully", description="Execution narrative")
    timestamp: int = Field(..., description="Execution timestamp in UTC epoch seconds")


class PaperOrder(BaseModel):
    """
    1. The use of class:
       Audit model representing a working or historical paper order.

    2. What the class contains:
       - order_id: Unique order identifier string.
       - account_id: Associated account identifier string.
       - contract_id: Executed contract identifier string.
       - side: Order side ('BUY' | 'SELL').
       - quantity: Order quantity in contracts.
       - order_type: Order type ('MARKET' | 'LIMIT').
       - price: Submitted or executed price in INR.
       - status: Order status ('FILLED', 'PENDING', 'CANCELLED', 'REJECTED').
       - created_at: Unix epoch seconds when order was placed.
       - filled_at: Optional Unix epoch seconds when order was filled.

    3. Technologies used and why:
       Pydantic BaseModel for JSON serialization.

    4. Key design and overall design of the class:
       Provides audit trail of all manual and simulated orders for the working orders console.
    """
    model_config = ConfigDict(extra="ignore")

    order_id: str = Field(..., description="Unique order identifier")
    account_id: str = Field(..., description="Account identifier")
    contract_id: str = Field(..., description="Contract identifier")
    side: str = Field(..., description="Order side ('BUY' | 'SELL')")
    quantity: int = Field(..., description="Order quantity")
    order_type: str = Field(..., description="Order type ('MARKET' | 'LIMIT')")
    price: float = Field(..., description="Order price in INR")
    status: str = Field(..., description="Current order status")
    created_at: int = Field(..., description="Creation epoch timestamp in seconds")
    filled_at: Optional[int] = Field(default=None, description="Fill epoch timestamp in seconds")


class PaperTrade(BaseModel):
    """
    1. The use of class:
       Immutable audit record of an executed trade fill.

    2. What the class contains:
       - trade_id: Unique trade execution identifier string.
       - account_id: Associated account identifier string.
       - contract_id: Executed contract identifier string.
       - side: Trade execution side ('BUY' | 'SELL').
       - quantity: Number of contracts executed.
       - price: Execution trade price in INR.
       - timestamp: Unix epoch seconds of fill execution.
       - pnl_rupees: Realized PnL attributable to closing trade (0.0 for opening).

    3. Technologies used and why:
       Pydantic BaseModel with extra='ignore' for audit log tables.

    4. Key design and overall design of the class:
       Itemized log record for trade history tables and regulatory audit compliance.
    """
    model_config = ConfigDict(extra="ignore")

    trade_id: str = Field(..., description="Unique trade execution identifier")
    account_id: str = Field(..., description="Account identifier")
    contract_id: str = Field(..., description="Contract identifier")
    side: str = Field(..., description="Trade side ('BUY' | 'SELL')")
    quantity: int = Field(..., description="Executed trade quantity")
    price: float = Field(..., description="Execution fill price in INR")
    timestamp: int = Field(..., description="Execution timestamp in UTC epoch seconds")
    pnl_rupees: float = Field(default=0.0, description="Realized PnL in INR")
    statutory_fees_rupees: float = Field(default=23.60, description="Statutory STT, GST, and exchange fees in INR")


class PaperStrategyMacro(BaseModel):
    """
    1. The use of class:
       Telemetry summary record for an automated strategy in the macro dashboard monitor.

    2. What the class contains:
       - strategy_id: Registered strategy identifier string.
       - strategy_name: Friendly strategy display name.
       - mode: Execution simulation mode (e.g. ACTUAL_OPTIONS).
       - status: Active operating state ('Running', 'Warming Up', 'Stopped').
       - allocated_lots: Number of lots assigned to strategy.
       - today_pnl_rupees: Daily net mark-to-market PnL in INR.
       - win_rate_pct: Cumulative win percentage.
       - sharpe_ratio: Annualized risk-adjusted Sharpe ratio.

    3. Technologies used and why:
       Pydantic BaseModel for macro table serialization.

    4. Key design and overall design of the class:
       Decoupled macro monitoring model separating multi-strategy oversight from micro console execution.
    """
    model_config = ConfigDict(extra="ignore")

    strategy_id: str = Field(..., description="Registered strategy identifier")
    strategy_name: str = Field(..., description="Display name of the strategy")
    mode: str = Field(..., description="Operating execution mode")
    status: str = Field(..., description="Operating status ('Running' | 'Warming Up' | 'Stopped')")
    allocated_lots: int = Field(..., description="Assigned lot sizing allocation")
    today_pnl_rupees: float = Field(..., description="Today's mark-to-market PnL in INR")
    win_rate_pct: float = Field(..., description="Cumulative win rate percentage")
    sharpe_ratio: float = Field(..., description="Annualized Sharpe ratio")


class RiskPolicySummary(BaseModel):
    """
    1. The use of class:
       Active risk management policy limits and regulatory boundary parameters.

    2. What the class contains:
       - freeze_quantity: Exchange hard ceiling per single order (RK-06, default 1,800).
       - advisory_lot_ceiling: Maximum lot size threshold for advisory warnings (default 72).
       - max_loss_per_day_rupees: Firm-wide daily loss ceiling in INR.
       - max_drawdown_pct: Maximum peak-to-trough portfolio drawdown percentage limit.
       - trading_window_start: Daily entry trading session opening time ('09:15').
       - trading_window_end: Daily entry trading session cutoff time ('15:25').
       - margin_mode: Active margin accounting mode ('THEORETICAL' | 'REALISTIC_ACCOUNT').
       - account_allocation_mode: Account allocation mode ('ISOLATED' | 'PORTFOLIO').

    3. Technologies used and why:
       Pydantic BaseModel for risk setting inspection panels.

    4. Key design and overall design of the class:
       Exposes pre-trade risk policy limits governed by packages.risk.rules.
    """
    model_config = ConfigDict(extra="ignore")

    freeze_quantity: int = Field(default=1800, description="Exchange order freeze quantity ceiling (RK-06)")
    advisory_lot_ceiling: int = Field(default=72, description="Advisory lot warning ceiling")
    max_loss_per_day_rupees: float = Field(default=50000.0, description="Maximum daily loss threshold in INR")
    max_drawdown_pct: float = Field(default=10.0, description="Maximum peak-to-trough drawdown percentage")
    trading_window_start: str = Field(default="09:15", description="Daily entry trading window open time")
    trading_window_end: str = Field(default="15:25", description="Daily entry trading window cutoff time")
    margin_mode: str = Field(default="THEORETICAL", description="Active margin calculation mode")
    account_allocation_mode: str = Field(default="ISOLATED", description="Account allocation mode ('ISOLATED' | 'PORTFOLIO')")
