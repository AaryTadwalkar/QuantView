"""
1. What this file does:
   Defines Pydantic data schemas and response containers for backtest orchestration,
   status reporting, strategy discovery, Lightweight Charts trade markers, equity curves,
   and performance metrics (Milestones M6-04, M6-07, M6-08, M6-09, and Gate G4).

2. Overall design:
   Provides strongly typed request models and immutable response envelopes:
     - BacktestRequest: Input parameters, temporal boundaries, and capital configuration.
     - ChartMarker: Lightweight Charts markers for trade entry/exit visualization.
     - EquityPoint: Mark-to-market equity, cash balance, and drawdown snapshots.
     - TradeRecord: Itemized audit records of completed round-trip trades.
     - BacktestMetricsSummary: Quantitative summary tear sheet metrics.
     - BacktestRunResponse: Full backtest execution payload.
     - StrategyInfo: Registered strategy metadata and schema defaults.
     - BacktestStatusResponse: Lifecycle query and cancellation status envelope.

3. Elements in the file:
   - BacktestRequest: Schema model for launching a backtest run.
   - ChartMarker: Overlay marker model for TradingView charts.
   - EquityPoint: Chronological equity point model.
   - TradeRecord: Detailed trade record model.
   - BacktestMetricsSummary: Performance metrics summary model.
   - BacktestRunResponse: Complete backtest execution result container.
   - StrategyInfo: Strategy registry metadata container.
   - BacktestStatusResponse: Status inquiry and cancellation response container.
   - HeatmapCell: Sensitivity matrix grid cell data model.
   - MonthlyReturnYear: Calendar monthly returns model for historical years.
   - StrategyHeatmapResponse: Strategy parameter sensitivity matrix and calendar container.

4. Final output of the file:
   - Exported Pydantic schemas for the QuantView backtest API gateway.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class BacktestRequest(BaseModel):
    """
    1. The use of class:
       Validates payload parameters required to launch a deterministic backtest run.

    2. What the class contains:
       - strategy_id: Strategy identifier registered in StrategyRegistry.
       - start_date, end_date: ISO 8601 calendar date bounds (YYYY-MM-DD).
       - timeframe: Simulation candle timeframe resolution (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d).
       - initial_capital_rupees: Starting portfolio capital in INR (strictly > 0).
       - mode: Backtest execution mode.
       - execution_mode: Execution mode alias for mode.
       - intrabar_stop_policy: Stop evaluation policy (e.g. STOP_FIRST, OHLC_PATH).
       - fee_schedule: Statutory brokerage and regulatory fee schedule.
       - lots: Sizing lot multiplier (strictly > 0).
       - strategy_params: Custom strategy parameter overrides.

    3. Technologies used and why:
       Pydantic BaseModel with ConfigDict for strict input validation and OpenAPI schema generation.

    4. Key design and overall design of the class:
       Guarantees positive initial capital and lot sizing before execution.
    """
    model_config = ConfigDict(extra="ignore")

    strategy_id: str = Field(..., description="Unique registered strategy identifier")
    start_date: str = Field(default="2025-01-01", description="Backtest start date (YYYY-MM-DD)")
    end_date: str = Field(default="2025-01-10", description="Backtest end date (YYYY-MM-DD)")
    timeframe: str = Field(
        default="1m",
        description="Simulation candle timeframe resolution (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d)",
    )
    initial_capital_rupees: float = Field(
        default=500000.0,
        gt=0.0,
        description="Initial account equity in INR (must be strictly positive)",
    )
    mode: str = Field(default="UNDERLYING_DIRECTIONAL", description="Execution simulation mode")
    execution_mode: Optional[str] = Field(
        default=None,
        description="Simulation mode alias for mode (e.g. UNDERLYING_DIRECTIONAL, ACTUAL_OPTIONS)",
    )
    intrabar_stop_policy: str = Field(default="STOP_FIRST", description="Intrabar order fill policy")
    fee_schedule: str = Field(
        default="UPSTOX_2026_V1",
        description="Statutory brokerage and regulatory fee schedule version",
    )
    lots: int = Field(default=1, gt=0, description="Order sizing lot multiplier (must be >= 1)")
    target_pct: Optional[float] = Field(
        default=None, description="Take-profit percentage target (e.g. 0.30 for 30%)"
    )
    stop_loss_pct: Optional[float] = Field(
        default=None, description="Stop-loss percentage ceiling (e.g. 0.15 for 15%)"
    )
    strike_policy: Optional[str] = Field(
        default="ATM",
        description="Strike selection policy (ATM, ITM_1, ITM_2, OTM_1, OTM_2)",
    )
    strategy_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom parameter dictionary matching strategy parameter schema",
    )


class ChartMarker(BaseModel):
    """
    1. The use of class:
       Represents an overlay event marker compatible with TradingView Lightweight Charts series markers.

    2. What the class contains:
       - time: UTC epoch seconds of marker position.
       - position: Visual placement relative to bar ('aboveBar' | 'belowBar').
       - color: CSS hex color code ('#26a69a' for buy, '#ef5350' for sell).
       - shape: Geometric marker glyph ('arrowUp' | 'arrowDown').
       - text: Informative label shown on hover or badge.

    3. Technologies used and why:
       Pydantic BaseModel for JSON serialization matching Lightweight Charts series.setMarkers() contract.

    4. Key design and overall design of the class:
       Visualizes causal entry and exit trade executions directly on candlestick charts.
    """
    model_config = ConfigDict(extra="ignore")

    time: int = Field(..., description="UTC epoch timestamp in seconds")
    position: str = Field(..., description="Marker position: aboveBar or belowBar")
    color: str = Field(..., description="Hex color string (#26a69a or #ef5350)")
    shape: str = Field(..., description="Marker shape: arrowUp or arrowDown")
    text: str = Field(..., description="Marker label text")


class EquityPoint(BaseModel):
    """
    1. The use of class:
       Represents a single chronological mark-to-market portfolio equity snapshot.

    2. What the class contains:
       - time: UTC epoch seconds of the bar boundary.
       - equity: Total account mark-to-market equity in INR.
       - cash: Unencumbered liquid cash balance in INR.
       - drawdown: Current peak-to-trough equity reduction in INR.

    3. Technologies used and why:
       Pydantic BaseModel for timeseries charting and equity curve rendering.

    4. Key design and overall design of the class:
       Provides floating-point rupee representations derived from exact integer paise ledger snapshots.
    """
    model_config = ConfigDict(extra="ignore")

    time: int = Field(..., description="UTC epoch timestamp in seconds")
    equity: float = Field(..., description="Total mark-to-market portfolio equity in INR")
    cash: float = Field(..., description="Available cash balance in INR")
    drawdown: float = Field(..., description="Peak-to-current drawdown in INR")


class TradeRecord(BaseModel):
    """
    1. The use of class:
       Represents a completed round-trip trade record with financial audit details.

    2. What the class contains:
       - trade_id: Unique trade execution identifier.
       - entry_time, exit_time: UTC epoch timestamps in seconds.
       - contract: Traded contract key or derivative symbol.
       - side: Order execution side (e.g. BUY, SELL).
       - quantity: Number of contracts traded.
       - entry_price, exit_price: Execution prices in INR.
       - gross_pnl_rupees, fees_rupees, net_pnl_rupees: Financial returns in INR.
       - pnl_pct: Percentage return on capital deployed.
       - exit_reason: Audit trigger explaining trade liquidation.

    3. Technologies used and why:
       Pydantic BaseModel for serializing trade logs into institutional audit tables.

    4. Key design and overall design of the class:
       Maps directly from IntrabarFillEngine trade history and ledger fill records.
    """
    model_config = ConfigDict(extra="ignore")

    trade_id: str = Field(..., description="Unique trade execution identifier")
    entry_time: int = Field(..., description="UTC epoch seconds of entry execution")
    exit_time: int = Field(..., description="UTC epoch seconds of exit execution")
    contract: str = Field(..., description="Traded contract identifier")
    side: str = Field(..., description="Trade position side (BUY or SELL)")
    quantity: int = Field(..., description="Filled contract quantity")
    entry_price: float = Field(..., description="Average fill price on entry in INR")
    exit_price: float = Field(..., description="Average fill price on exit in INR")
    gross_pnl_rupees: float = Field(..., description="Gross realized PnL in INR")
    fees_rupees: float = Field(..., description="Total brokerage and regulatory fees in INR")
    net_pnl_rupees: float = Field(..., description="Net realized PnL after all fees in INR")
    pnl_pct: float = Field(..., description="Percentage return on entry trade value")
    exit_reason: str = Field(..., description="Liquidation reason or exit rule trigger")


class BacktestMetricsSummary(BaseModel):
    """
    1. The use of class:
       Encapsulates quantitative summary performance and risk metrics for a backtest run.

    2. What the class contains:
       - sharpe_ratio: Annualized or daily Sharpe ratio.
       - sortino_ratio: Downside-risk adjusted return ratio.
       - max_drawdown_pct: Maximum peak-to-trough drawdown percentage.
       - win_rate_pct: Percentage of winning trades.
       - total_trades, winning_trades, losing_trades: Trade counts.
       - net_pnl_rupees: Total net profit/loss in INR.
       - total_return_pct: Total return percentage relative to initial capital.
       - deflated_sharpe_ratio: Bailey & López de Prado (2014) DSR statistic.
       - profit_factor: Gross profit divided by gross loss.

    3. Technologies used and why:
       Pydantic BaseModel for tear-sheet KPI metrics display.

    4. Key design and overall design of the class:
       Provides institutional metrics extracted from BacktestMetrics calculation engine.
    """
    model_config = ConfigDict(extra="ignore")

    sharpe_ratio: Optional[float] = Field(default=None, description="Annualized Sharpe ratio")
    sortino_ratio: Optional[float] = Field(default=None, description="Downside Sortino ratio")
    max_drawdown_pct: float = Field(default=0.0, description="Maximum peak-to-trough drawdown percentage")
    win_rate_pct: float = Field(default=0.0, description="Winning trades percentage")
    total_trades: int = Field(default=0, description="Total count of completed round-trip trades")
    winning_trades: int = Field(default=0, description="Count of profitable trades")
    losing_trades: int = Field(default=0, description="Count of loss-making trades")
    net_pnl_rupees: float = Field(default=0.0, description="Cumulative net realized PnL in INR")
    total_return_pct: Optional[float] = Field(
        default=None,
        description="Total return percentage relative to initial capital",
    )
    deflated_sharpe_ratio: Optional[float] = Field(
        default=None,
        description="Deflated Sharpe Ratio correcting for multiple testing",
    )
    profit_factor: Optional[float] = Field(default=None, description="Gross profit over gross loss")


class BacktestRunResponse(BaseModel):
    """
    1. The use of class:
       Complete result container returned upon successful execution of a backtest run.

    2. What the class contains:
       - run_id: Deterministic run identifier.
       - status: Execution state ('COMPLETED' | 'FAILED' | 'CANCELLED').
       - strategy_id: Strategy identifier executed.
       - mode: Backtest execution mode.
       - metrics: Comprehensive summary metrics tear-sheet.
       - equity_curve: Timeseries equity snapshots.
       - trades: List of completed round-trip trades.
       - chart_markers: Lightweight Charts overlay markers.
       - execution_time_ms: Wall-clock simulation duration in milliseconds.

    3. Technologies used and why:
       Pydantic BaseModel for comprehensive API response payload delivery.

    4. Key design and overall design of the class:
       Unifies metrics, equity curves, trade logs, and chart annotations in a single response.
    """
    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(..., description="Unique deterministic run identifier")
    status: str = Field(..., description="Execution status: COMPLETED, FAILED, or CANCELLED")
    strategy_id: str = Field(..., description="Identifier of executed strategy")
    mode: str = Field(..., description="Execution simulation mode")
    metrics: BacktestMetricsSummary = Field(..., description="Quantitative summary tear sheet")
    equity_curve: List[EquityPoint] = Field(
        default_factory=list,
        description="Chronological mark-to-market equity snapshots",
    )
    trades: List[TradeRecord] = Field(
        default_factory=list,
        description="Audit log of completed round-trip trades",
    )
    chart_markers: List[ChartMarker] = Field(
        default_factory=list,
        description="TradingView Lightweight Charts overlay markers",
    )
    execution_time_ms: float = Field(..., description="Simulation latency in milliseconds")


class StrategyInfo(BaseModel):
    """
    1. The use of class:
       Container describing a registered strategy, its documentation, and default parameters.

    2. What the class contains:
       - id: Strategy identifier in StrategyRegistry.
       - name: Human-readable strategy name.
       - description: Documentation summary describing strategy edge and logic.
       - version: Strategy semantic version string.
       - author: Strategy creator or maintainer.
       - regimes: List of supported market regimes (e.g. TRENDING_BULLISH, HIGH_MOMENTUM).
       - default_params: Default parameter key-value dictionary.

    3. Technologies used and why:
       Pydantic BaseModel for strategy catalog discovery in UI configuration forms.

    4. Key design and overall design of the class:
       Powers Strategy Browser UI (Milestone M6-08) and RunConfig form builders.
    """
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Unique registered strategy identifier")
    name: str = Field(..., description="Human-readable strategy name")
    description: str = Field(default="", description="Strategy methodology and logic description")
    version: str = Field(default="1.0.0", description="Semantic version string")
    author: str = Field(default="QuantView Engineering", description="Strategy author or maintainer")
    regimes: List[str] = Field(
        default_factory=list,
        description="Supported market regimes (e.g. TRENDING, VOLATILE, RANGING)",
    )
    default_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Default configuration parameters schema",
    )


class BacktestStatusResponse(BaseModel):
    """
    1. The use of class:
       Container reporting the execution status and lifecycle state of a backtest run.

    2. What the class contains:
       - run_id: Unique backtest run identifier.
       - status: Run lifecycle status ('PENDING' | 'RUNNING' | 'COMPLETED' | 'CANCELLED' | 'FAILED').
       - message: Optional status detail or diagnostic message.
       - execution_time_ms: Execution duration in milliseconds if completed.
       - result: Complete backtest execution result if completed.

    3. Technologies used and why:
       Pydantic BaseModel for asynchronous backtest polling and status inquiry.

    4. Key design and overall design of the class:
       Provides unified schema for status checks and cancellation commands.
    """
    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(..., description="Unique backtest run identifier")
    status: str = Field(
        ...,
        description="Run lifecycle status: PENDING, RUNNING, COMPLETED, CANCELLED, or FAILED",
    )
    message: Optional[str] = Field(default=None, description="Diagnostic message or cancellation note")
    execution_time_ms: Optional[float] = Field(
        default=None,
        description="Execution duration in milliseconds if finished",
    )
    result: Optional[BacktestRunResponse] = Field(
        default=None,
        description="Full backtest result payload if completed",
    )


class HeatmapCell(BaseModel):
    """
    1. The use of class:
       Data model for an individual parameter coordinate cell in the quantitative sensitivity matrix.

    2. What the class contains:
       - strike_offset: Strike offset parameter string (ATM-2, ATM-1, ATM, ATM+1, ATM+2).
       - stop_loss_pct: Stop-loss percentage value (10%, 20%, 30%, 40%, 50%).
       - net_pnl_rupees: Computed net P&L in INR.
       - return_pct: Percentage return on initial capital.
       - sharpe_ratio: Annualized risk-adjusted Sharpe ratio.
       - max_drawdown_pct: Maximum peak-to-trough drawdown percentage.

    3. Technologies used and why:
       Pydantic BaseModel with ConfigDict for strict JSON matrix serialization.

    4. Key design and overall design of the class:
       Encapsulates bivariate sensitivity results across strike offsets and stop-loss boundaries.
    """
    model_config = ConfigDict(extra="ignore")

    strike_offset: str = Field(description="Strike offset relative to ATM (ATM-2, ATM-1, ATM, ATM+1, ATM+2)")
    stop_loss_pct: float = Field(description="Stop-loss percentage (10.0, 20.0, 30.0, 40.0, 50.0)")
    net_pnl_rupees: float = Field(description="Net P&L in INR for parameter tuple")
    return_pct: float = Field(description="Total return percentage")
    sharpe_ratio: float = Field(description="Annualized Sharpe ratio")
    max_drawdown_pct: float = Field(description="Maximum peak-to-trough drawdown percentage")


class MonthlyReturnYear(BaseModel):
    """
    1. The use of class:
       Calendar model representing monthly return percentages for an entire historical year.

    2. What the class contains:
       - year: Calendar year (e.g. 2025, 2026).
       - months: Dictionary mapping month abbreviations (Jan..Dec) to percentage returns.
       - total_pct: Annual cumulative return percentage.

    3. Technologies used and why:
       Pydantic BaseModel for tabular calendar visualization in the Heatmap panel.

    4. Key design and overall design of the class:
       Provides monthly returns grid structure matching institutional tear sheet calendars.
    """
    model_config = ConfigDict(extra="ignore")

    year: int = Field(description="Calendar year")
    months: Dict[str, float] = Field(description="Dictionary mapping month name (Jan..Dec) to return percentage")
    total_pct: float = Field(description="Cumulative annual percentage return")


class StrategyHeatmapResponse(BaseModel):
    """
    1. The use of class:
       Response container for the Quantitative Strategy Sensitivity Heatmap and monthly calendar view.

    2. What the class contains:
       - strategy_id: Strategy identifier evaluated.
       - strategy_name: Friendly strategy display label.
       - strike_offsets: List of strike offset axis labels.
       - stop_loss_pcts: List of stop-loss percentage axis coordinates.
       - matrix: 5x5 list of HeatmapCell instances.
       - monthly_returns: Chronological list of MonthlyReturnYear calendar entries.

    3. Technologies used and why:
       Pydantic BaseModel for JSON envelope generation.

    4. Key design and overall design of the class:
       Unified response payload powering the 2D sensitivity matrix and monthly calendar grid.
    """
    model_config = ConfigDict(extra="ignore")

    strategy_id: str = Field(description="Strategy identifier")
    strategy_name: str = Field(description="Friendly strategy display name")
    strike_offsets: List[str] = Field(description="X-Axis strike offsets")
    stop_loss_pcts: List[float] = Field(description="Y-Axis stop loss percentages")
    matrix: List[HeatmapCell] = Field(description="25-cell sensitivity matrix")
    monthly_returns: List[MonthlyReturnYear] = Field(description="Monthly return calendar records")
