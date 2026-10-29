/**
 * 1. What this file does:
 *    Provides TypeScript ambient type definitions and interface declarations for the QuantView web client
 *    (apps/web). Models exactly match the backend FastAPI Pydantic schemas in services/api/schemas/
 *    (Milestones M6-01, M6-03, M6-03b, M6-04, M6-06, M6-07, M6-09, M6-13, M6-14, M6-15, M6-18, and Gate G4).
 *
 * 2. Overall design:
 *    Defines strict structural interfaces for:
 *      - Market data (OHLCV candles, symbol catalog, quotes).
 *      - Option chain matrix, strike quotes, Greeks, and single-contract candles.
 *      - Backtest execution requests, real-time status, performance tear-sheet metrics, trade logs, and markers.
 *      - Paper trading accounts, open positions, order lifecycle, and on-chart SL/TP price lines.
 *      - Canvas drawing annotations, hit-testing points, and persistence envelopes.
 *      - System health, lake session coverage, and process telemetry diagnostics.
 *    Enforces the canonical UtcEpochSec (int64 seconds since Unix epoch) timestamp contract.
 *
 * 3. Elements in the file:
 *    - UtcEpochSec: Type alias for UTC epoch seconds.
 *    - Candle, SymbolInfo, MarketQuote, CandleResponse.
 *    - OptionStrikeQuote, OptionChainRow, OptionChainResponse, OptionCandleResponse.
 *    - BacktestRequest (BacktestRunRequest), ChartMarker, EquityPoint, TradeRecord (TradeLogItem),
 *      BacktestMetricsSummary (PerformanceMetrics), StrategyInfo, BacktestRunResponse, BacktestStatusResponse.
 *    - ChartPriceLines, ChartPriceLine, PaperAccount (PaperAccountResponse), PaperPosition (PaperPositionResponse),
 *      PaperOrderRequest, PaperOrderResponse, PaperOrder.
 *    - DrawingPoint, DrawingRecord (DrawingItem), DrawingDeleteResponse.
 *    - HealthResponse, HeartbeatResponse, DataCoverageResponse.
 *
 * 4. Final output of the file:
 *    - Ambient TypeScript declaration file providing full IDE autocomplete and compile-time contract enforcement.
 */

/**
 * 1. The use of type:
 *    Canonical timestamp representation across QuantView stores, APIs, charts, and replay cursors (ADR-041).
 *
 * 2. What the type contains:
 *    Integer number representing elapsed seconds since 1970-01-01T00:00:00Z UTC.
 *
 * 3. Technologies used and why:
 *    TypeScript number alias representing integer epoch seconds for zero-overhead Lightweight Charts compatibility.
 *
 * 4. Key design and overall design of the type:
 *    Guarantees no floating-point millisecond or timezone string ambiguities in temporal pipelines.
 */
export type UtcEpochSec = number;

/**
 * 1. The use of interface:
 *    Single OHLCV candlestick bar matching services.api.schemas.market.Candle.
 *
 * 2. What the interface contains:
 *    - time: UtcEpochSec timestamp of bar start.
 *    - open: Float opening price.
 *    - high: Float highest price during period.
 *    - low: Float lowest price during period.
 *    - close: Float closing price of period.
 *    - volume: Accumulated integer trade count or volume.
 *
 * 3. Technologies used and why:
 *    TypeScript interface matching Lightweight Charts CandlestickData contract.
 *
 * 4. Key design and overall design of the interface:
 *    Compact structure directly fed into series.setData() with sub-50ms rendering performance.
 */
export interface Candle {
  time: UtcEpochSec;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/**
 * 1. The use of interface:
 *    Metadata describing a tradeable or index instrument matching services.api.schemas.market.SymbolInfo.
 */
export interface SymbolInfo {
  symbol: string;
  name: string;
  type: string;
  tick_size: number;
  lot_size: number;
  description?: string | null;
}

/**
 * 1. The use of interface:
 *    Real-time price quote and daily performance metrics matching services.api.schemas.market.MarketQuote.
 */
export interface MarketQuote {
  symbol: string;
  last_price: number;
  change: number;
  change_pct: number;
  high: number;
  low: number;
  volume: number;
  timestamp: UtcEpochSec;
}

export type MarketQuoteResponse = MarketQuote;

/**
 * 1. The use of interface:
 *    Historical and real-time candlestick series container matching services.api.schemas.market.CandleResponse.
 */
export interface CandleResponse {
  symbol: string;
  resolution: string;
  candles: Candle[];
}

/**
 * 1. The use of interface:
 *    Individual option strike contract quote with Greeks and pricing matching services.api.schemas.options.OptionStrikeQuote.
 */
export interface OptionStrikeQuote {
  trading_symbol: string;
  strike: number;
  option_type: "CE" | "PE" | string;
  ltp: number;
  change: number;
  change_pct: number;
  bid: number;
  ask: number;
  oi: number;
  oi_change: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  volume: number;
}

/**
 * 1. The use of interface:
 *    Paired strike row in option chain matrix matching services.api.schemas.options.OptionChainRow.
 */
export interface OptionChainRow {
  strike: number;
  ce: OptionStrikeQuote | null;
  pe: OptionStrikeQuote | null;
}

/**
 * 1. The use of interface:
 *    Option chain matrix response centered around ATM spot matching services.api.schemas.options.OptionChainResponse.
 */
export interface OptionChainResponse {
  underlying: string;
  expiry_date: string;
  spot_price: number;
  atm_strike: number;
  timestamp: UtcEpochSec;
  strikes: OptionChainRow[];
}

/**
 * 1. The use of interface:
 *    Historical candle response for a specific option contract matching services.api.schemas.options.OptionCandleResponse.
 */
export interface OptionCandleResponse {
  contract_id: string;
  symbol: string;
  expiry: string;
  strike: number;
  option_type: "CE" | "PE" | string;
  resolution: string;
  candles: Candle[];
}

/**
 * 1. The use of interface:
 *    Backtest launch request payload matching services.api.schemas.backtest.BacktestRequest.
 */
export interface BacktestRequest {
  strategy_id: string;
  start_date: string;
  end_date: string;
  initial_capital_rupees: number;
  mode?: "UNDERLYING_DIRECTIONAL" | "ACTUAL_OPTIONS" | "SYNTHETIC_OPTIONS_ESTIMATE" | string;
  execution_mode?: "UNDERLYING_DIRECTIONAL" | "ACTUAL_OPTIONS" | "SYNTHETIC_OPTIONS_ESTIMATE" | string;
  intrabar_stop_policy?: "STOP_FIRST" | "OHLC_PATH" | string;
  fee_schedule?: "UPSTOX_2026_V1" | "UPSTOX_2025_OCT" | string;
  lots?: number;
  strategy_params?: Record<string, any>;
}

export type BacktestRunRequest = BacktestRequest;

/**
 * 1. The use of interface:
 *    TradingView Lightweight Charts overlay trade marker matching services.api.schemas.backtest.ChartMarker.
 */
export interface ChartMarker {
  time: UtcEpochSec;
  position: "aboveBar" | "belowBar" | "inBar";
  color: string;
  shape: "arrowUp" | "arrowDown" | "circle" | "square";
  text: string;
}

/**
 * 1. The use of interface:
 *    Mark-to-market equity curve point matching services.api.schemas.backtest.EquityPoint.
 */
export interface EquityPoint {
  time: UtcEpochSec;
  equity: number;
  cash: number;
  drawdown: number;
}

/**
 * 1. The use of interface:
 *    Completed round-trip trade record matching services.api.schemas.backtest.TradeRecord.
 */
export interface TradeRecord {
  trade_id: string;
  entry_time: UtcEpochSec;
  exit_time: UtcEpochSec;
  contract: string;
  side: "BUY" | "SELL" | string;
  quantity: number;
  entry_price: number;
  exit_price: number;
  gross_pnl_rupees: number;
  fees_rupees: number;
  net_pnl_rupees: number;
  pnl_pct: number;
  exit_reason: string;
}

export type TradeLogItem = TradeRecord;

/**
 * 1. The use of interface:
 *    Tear sheet summary metrics matching services.api.schemas.backtest.BacktestMetricsSummary.
 */
export interface BacktestMetricsSummary {
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  max_drawdown_pct: number;
  win_rate_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  net_pnl_rupees: number;
  total_return_pct?: number | null;
  deflated_sharpe_ratio: number | null;
  profit_factor: number | null;
}

export type PerformanceMetrics = BacktestMetricsSummary;

/**
 * 1. The use of interface:
 *    Registered strategy metadata matching services.api.schemas.backtest.StrategyInfo.
 */
export interface StrategyInfo {
  id: string;
  name: string;
  description: string;
  version: string;
  author: string;
  regimes?: string[];
  default_params: Record<string, any>;
}

/**
 * 1. The use of interface:
 *    Complete backtest result envelope matching services.api.schemas.backtest.BacktestRunResponse.
 */
export interface BacktestRunResponse {
  run_id: string;
  status: "COMPLETED" | "FAILED" | "CANCELLED" | string;
  strategy_id: string;
  mode: string;
  metrics: BacktestMetricsSummary;
  equity_curve: EquityPoint[];
  trades: TradeRecord[];
  chart_markers: ChartMarker[];
  execution_time_ms: number;
}

/**
 * 1. The use of interface:
 *    Backtest lifecycle status envelope matching services.api.schemas.backtest.BacktestStatusResponse.
 */
export interface BacktestStatusResponse {
  run_id: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "CANCELLED" | "FAILED" | string;
  message?: string | null;
  execution_time_ms?: number | null;
  result?: BacktestRunResponse | null;
}

/**
 * 1. The use of interface:
 *    Visual coordinates for rendering Entry, SL, and TP lines matching services.api.schemas.paper.ChartPriceLines.
 */
export interface ChartPriceLines {
  entry: number;
  stop_loss?: number | null;
  take_profit?: number | null;
}

/**
 * 1. The use of interface:
 *    Generic price line configuration for Lightweight Charts series.createPriceLine().
 */
export interface ChartPriceLine {
  price: number;
  color?: string;
  lineWidth?: number;
  lineStyle?: number;
  axisLabelVisible?: boolean;
  title?: string;
}

/**
 * 1. The use of interface:
 *    Paper trading account ledger model matching services.api.schemas.paper.PaperAccount.
 */
export interface PaperAccount {
  account_id: string;
  name: string;
  mode: string;
  currency: string;
  initial_capital_rupees: number;
  cash_balance_rupees: number;
  margin_reserved_rupees: number;
  free_cash_rupees: number;
  unrealized_pnl_rupees: number;
  realized_pnl_rupees: number;
  equity_rupees: number;
}

export type PaperAccountResponse = PaperAccount;

/**
 * 1. The use of interface:
 *    Active open derivative paper position model matching services.api.schemas.paper.PaperPosition.
 */
export interface PaperPosition {
  position_id: string;
  account_id: string;
  contract_id: string;
  symbol: string;
  strike: number;
  option_type: "CE" | "PE" | string;
  expiry: string;
  quantity: number;
  side: "BUY" | "SELL" | string;
  entry_price: number;
  current_price: number;
  pnl_rupees: number;
  pnl_pct: number;
  entry_time: UtcEpochSec;
}

export type PaperPositionResponse = PaperPosition;

/**
 * 1. The use of interface:
 *    Discretionary or one-click paper order submission request matching services.api.schemas.paper.PaperOrderRequest.
 */
export interface PaperOrderRequest {
  account_id?: string;
  contract_id: string;
  side: "BUY" | "SELL" | string;
  quantity?: number;
  order_type?: "MARKET" | "LIMIT" | string;
  limit_price?: number | null;
  stop_loss_pct?: number | null;
  take_profit_pct?: number | null;
}

/**
 * 1. The use of interface:
 *    Paper order fill confirmation envelope matching services.api.schemas.paper.PaperOrderResponse.
 */
export interface PaperOrderResponse {
  order_id: string;
  account_id: string;
  contract_id: string;
  status: "FILLED" | "PENDING" | "REJECTED" | string;
  side: "BUY" | "SELL" | string;
  quantity: number;
  fill_price: number;
  chart_lines: ChartPriceLines;
  message: string;
  timestamp: UtcEpochSec;
}

/**
 * 1. The use of interface:
 *    Working or historical order record matching services.api.schemas.paper.PaperOrder.
 */
export interface PaperOrder {
  order_id: string;
  account_id: string;
  contract_id: string;
  side: "BUY" | "SELL" | string;
  quantity: number;
  order_type: "MARKET" | "LIMIT" | string;
  price: number;
  status: "FILLED" | "PENDING" | "CANCELLED" | "REJECTED" | string;
  created_at: UtcEpochSec;
  filled_at?: UtcEpochSec | null;
}

/**
 * 1. The use of interface:
 *    Chart anchor coordinate point matching services.api.schemas.drawings.DrawingPoint.
 */
export interface DrawingPoint {
  time: UtcEpochSec;
  price: number;
}

/**
 * 1. The use of interface:
 *    Chart drawing annotation entity matching services.api.schemas.drawings.DrawingRecord.
 */
export interface DrawingRecord {
  id: string;
  symbol: string;
  type: "trendline" | "horizontal_line" | "rectangle" | "long" | "short" | "fibonacci" | "measure" | string;
  points: DrawingPoint[];
  properties: Record<string, any>;
  created_at: UtcEpochSec;
  updated_at: UtcEpochSec;
}

export type DrawingItem = DrawingRecord;

/**
 * 1. The use of interface:
 *    Drawing deletion confirmation matching services.api.schemas.drawings.DrawingDeleteResponse.
 */
export interface DrawingDeleteResponse {
  deleted_count: number;
  message: string;
}

/**
 * 1. The use of interface:
 *    Gateway readiness response matching services.api.routers.health.HealthResponse.
 */
export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

/**
 * 1. The use of interface:
 *    Process heartbeat diagnostics matching services.api.routers.health.HeartbeatResponse.
 */
export interface HeartbeatResponse {
  status: string;
  service: string;
  timestamp_utc: string;
  epoch_sec: UtcEpochSec;
  uptime_seconds: number;
  pid: number;
}

/**
 * 1. The use of interface:
 *    Data lake session coverage and chart licensing response matching services.api.routers.health.DataCoverageResponse.
 */
export interface DataCoverageResponse {
  status: string;
  verdict: "HEALTHY" | "WARNING" | "DEGRADED" | string;
  chart_license: string;
  duckdb_lake_path: string;
  total_sessions: number;
  start_date: string;
  end_date: string;
  eligible_sessions: number;
  warning_sessions: number;
  ineligible_sessions: number;
  snapshots_captures: number;
  candles_underlying: number;
}

/**
 * 1. The use of interface:
 *    Parameter schema definition for technical indicators matching services.api.schemas.indicators.IndicatorParameter.
 */
export interface IndicatorParameter {
  name: string;
  type: "int" | "float" | "str" | string;
  default: number | string | boolean | null;
  min_value?: number | null;
  max_value?: number | null;
  description: string;
}

/**
 * 1. The use of interface:
 *    Technical indicator discovery descriptor matching services.api.schemas.indicators.IndicatorDescriptor.
 */
export interface IndicatorDescriptor {
  id: string;
  name: string;
  category: "trend" | "momentum" | "volatility" | "structural" | string;
  description: string;
  pane: "primary" | "subpane";
  parameters: IndicatorParameter[];
}

/**
 * 1. The use of interface:
 *    Request model for on-demand indicator calculation matching services.api.schemas.indicators.IndicatorComputeRequest.
 */
export interface IndicatorComputeRequest {
  symbol: string;
  indicator_id: string;
  resolution?: string;
  params?: Record<string, any>;
  from_ts?: UtcEpochSec | null;
  to_ts?: UtcEpochSec | null;
  limit?: number;
}

/**
 * 1. The use of interface:
 *    Calculated indicator timeseries point matching services.api.schemas.indicators.IndicatorValuePoint.
 */
export interface IndicatorValuePoint {
  time: UtcEpochSec;
  values: Record<string, number | string | null>;
}

/**
 * 1. The use of interface:
 *    Calculated indicator response container matching services.api.schemas.indicators.IndicatorComputeResponse.
 */
export interface IndicatorComputeResponse {
  indicator_id: string;
  symbol: string;
  resolution: string;
  data: IndicatorValuePoint[];
}

/**
 * 1. The use of interface:
 *    Active chart indicator instance representation in QuantChart and QuantApp.
 */
export interface IndicatorInstance {
  uid: string;
  id: string;
  params?: Record<string, any>;
  colors?: Record<string, string>;
  hidden?: boolean;
  tf?: string;
}
