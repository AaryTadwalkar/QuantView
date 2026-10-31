/**
 * 1. What this file does:
 *    Typed HTTP client and formatting utilities for the QuantView web workstation (apps/web).
 *    Wraps standard fetch calls targeting the FastAPI Gateway endpoints under /api/v1/*
 *    (Milestones M6-01, M6-02, M6-03, M6-03b, M6-04, M6-05, M6-06, M6-07, M6-13, M6-14, M6-15, M6-18, and Gate G4).
 *
 * 2. Overall design:
 *    - Implements an async HTTP request envelope sending JSON headers and handling structured errors.
 *    - Exposes typed query methods for market candles, quotes, symbols, option chains, expiries,
 *      option contract candles, backtests, paper trading execution, risk policies, drawings, and health telemetry.
 *    - Implements zero-drift monetary formatters in Indian Rupees (INR, en-IN locale), integer paise conversions,
 *      and deterministic UTC-to-IST (Asia/Kolkata, UTC+05:30) timestamp formatters.
 *
 * 3. Elements in the file:
 *    - req: Low-level async request wrapper over fetch.
 *    - api: Comprehensive REST API client object.
 *    - fmtPrice: Price formatter with adaptive precision.
 *    - fmtRupees: Currency formatter for rupee amounts using Indian numbering system.
 *    - fmtPaise: Integer paise to rupee string formatter.
 *    - fmtPct: Percentage formatter with signed delta display.
 *    - fmtTime: Deterministic IST timestamp formatter.
 *    - esc: HTML entity escape sanitizer.
 *
 * 4. Final output of the file:
 *    - Exported api client object and formatting helper functions for browser consumption.
 */

/**
 * 1. The use of function:
 *    Core asynchronous fetch wrapper delivering JSON payloads and handling HTTP error envelopes.
 *
 * 2. How does the specific function work:
 *    - Prepares request headers ('Content-Type: application/json' for mutations).
 *    - Dispatches native fetch() to the specified URL.
 *    - Parses JSON response or falls back to plain text.
 *    - Throws Error with server error message or HTTP status code if res.ok is false.
 *    - Returns parsed response data on success.
 *
 * 3. Concepts used in the function:
 *    Promise-based HTTP client, JSON serialization, structured error handling.
 *
 * 4. Places where this function is imported and used:
 *    Invoked internally by all api object methods in apps/web/js/api.js.
 *
 * 5. Final output of the function, before and after:
 *    Before: Method, URL, optional payload. After: Promise resolving to parsed response object or rejecting on error.
 */
async function req(method, url, body) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    const errorMsg = data?.detail || data?.error || data || `HTTP ${res.status}`;
    throw new Error(typeof errorMsg === "string" ? errorMsg : JSON.stringify(errorMsg));
  }
  return data;
}

/**
 * QuantView REST API Client routing to FastAPI /api/v1/*
 */
export const api = {
  // Generic HTTP verbs
  get: (url) => req("GET", url),
  post: (url, body) => req("POST", url, body ?? {}),
  put: (url, body) => req("PUT", url, body ?? {}),
  patch: (url, body) => req("PATCH", url, body ?? {}),
  del: (url) => req("DELETE", url),

  // Market Data (M6-01, M6-03, M6-16)
  /**
   * 1. The use of function:
   *    Fetches chronologically sorted OHLCV candles from DuckDB analytical lake views.
   *
   * 2. How does the specific function work:
   *    Constructs query parameters for symbol, resolution, limit, and optional time boundaries,
   *    then dispatches GET /api/v1/market/candles.
   *
   * 3. Concepts used in the function:
   *    Time-series query parameterization, URL encoding.
   *
   * 4. Places where this function is imported and used:
   *    Imported by apps/web/js/chart.js and apps/web/js/app.js to load chart data.
   *
   * 5. Final output of the function, before and after:
   *    Before: Query arguments. After: Promise<CandleResponse>.
   */
  getCandles: (symbol, resolution = "1m", limit = 5000, from_ts = null, to_ts = null) => {
    const params = new URLSearchParams({
      symbol: symbol || "NSE:NIFTY50",
      resolution: resolution || "1m",
      limit: String(limit || 5000),
    });
    if (from_ts != null) params.set("from_ts", String(from_ts));
    if (to_ts != null) params.set("to_ts", String(to_ts));
    return req("GET", `/api/v1/market/candles?${params.toString()}`);
  },

  /**
   * 1. The use of function:
   *    Fetches real-time price quote and daily metrics for topbar tickers and watchlists.
   *
   * 2. How does the specific function work:
   *    Formulates parameterized URL targeting /api/v1/market/quote with encoded symbol and calls req("GET", ...).
   *
   * 3. Concepts used in the function:
   *    URL encoding, REST GET retrieval, ticker telemetry.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by fetchQuotes() and renderScreener() in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Symbol string. After: Promise resolving to MarketQuote object.
   */
  getQuote: (symbol) =>
    req("GET", `/api/v1/market/quote?symbol=${encodeURIComponent(symbol || "NSE:NIFTY50")}`),

  /**
   * 1. The use of function:
   *    Fetches supported instruments and benchmark indices catalog.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/market/symbols and parses array of SymbolInfo objects.
   *
   * 3. Concepts used in the function:
   *    Instrument catalog discovery, contract specifications.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by symbol picker modal in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Promise resolving to SymbolInfo[].
   */
  getSymbols: () => req("GET", "/api/v1/market/symbols"),

  // Option Chain & Derivatives (M6-03b, M6-15, M6-18)
  /**
   * 1. The use of function:
   *    Retrieves distinct sorted option contract expiry dates available in data lake.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/options/expiries with encoded underlying query parameter.
   *
   * 3. Concepts used in the function:
   *    Options expiry calendar, DuckDB view query.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by renderOptionChain() in apps/web/js/app.js to populate expiry selector.
   *
   * 5. Final output of the function, before and after:
   *    Before: Underlying string. After: Promise resolving to sorted string array of YYYY-MM-DD expiries.
   */
  getOptionExpiries: (underlying = "NIFTY") =>
    req("GET", `/api/v1/options/expiries?underlying=${encodeURIComponent(underlying)}`),

  /**
   * 1. The use of function:
   *    Reconstructs option chain matrix centered around ATM spot with CE/PE quotes and Greeks.
   *
   * 2. How does the specific function work:
   *    Prepares query parameters for strike_count, underlying, expiry_date, and spot_price, and dispatches GET /api/v1/options/chain.
   *
   * 3. Concepts used in the function:
   *    ATM centering, option chain reconstruction, Black-Scholes Greeks projection.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by loadChain() in apps/web/js/app.js to populate Option Chain tab.
   *
   * 5. Final output of the function, before and after:
   *    Before: Filter parameters. After: Promise resolving to OptionChainResponse.
   */
  getOptionChain: (expiry = null, spot = null, strikeCount = 15, underlying = "NIFTY") => {
    const params = new URLSearchParams({
      strike_count: String(strikeCount || 15),
      underlying: underlying || "NIFTY",
    });
    if (expiry) params.set("expiry_date", expiry);
    if (spot != null) params.set("spot_price", String(spot));
    return req("GET", `/api/v1/options/chain?${params.toString()}`);
  },

  /**
   * 1. The use of function:
   *    Fetches candlestick bars for a single option contract by contract ID.
   *
   * 2. How does the specific function work:
   *    Formulates query parameters with contract_id, resolution, limit, from_ts, to_ts, and calls GET /api/v1/options/candles.
   *
   * 3. Concepts used in the function:
   *    Derivative historical series, multi-timeframe resolution, contract identification.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by loadCandles() in apps/web/js/chart.js when chart symbol is an option contract.
   *
   * 5. Final output of the function, before and after:
   *    Before: Contract ID and query options. After: Promise resolving to OptionCandleResponse.
   */
  getOptionCandles: (contractId, resolution = "1m", limit = 5000, from_ts = null, to_ts = null) => {
    const params = new URLSearchParams({
      contract_id: contractId,
      resolution: resolution || "1m",
      limit: String(limit || 5000),
    });
    if (from_ts != null) params.set("from_ts", String(from_ts));
    if (to_ts != null) params.set("to_ts", String(to_ts));
    return req("GET", `/api/v1/options/candles?${params.toString()}`);
  },

  // Backtest Orchestration (M6-04, M6-07, M6-08, M6-09)
  /**
   * 1. The use of function:
   *    Launches deterministic backtest simulation in Python engine and returns full tear sheet.
   *
   * 2. How does the specific function work:
   *    Dispatches POST request with BacktestRequest JSON payload to /api/v1/backtest/run.
   *
   * 3. Concepts used in the function:
   *    Event-driven backtesting, deterministic simulation, tear-sheet performance metrics.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Strategy Tester run button in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Configuration object. After: Promise resolving to BacktestRunResponse.
   */
  runBacktest: (config) => req("POST", "/api/v1/backtest/run", config),

  /**
   * 1. The use of function:
   *    Inquires real-time lifecycle status of an ongoing or completed backtest.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/backtest/status/{run_id} with encoded run ID.
   *
   * 3. Concepts used in the function:
   *    Asynchronous job polling, simulation lifecycle tracking.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by backtest polling monitors in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Run ID string. After: Promise resolving to BacktestStatusResponse.
   */
  getBacktestStatus: (runId) => req("GET", `/api/v1/backtest/status/${encodeURIComponent(runId)}`),

  /**
   * 1. The use of function:
   *    Cancels an in-flight backtest execution.
   *
   * 2. How does the specific function work:
   *    Dispatches POST request to /api/v1/backtest/cancel/{run_id} to gracefully halt engine clock.
   *
   * 3. Concepts used in the function:
   *    Simulation clock interruption, task cancellation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by user cancel button in Strategy Tester.
   *
   * 5. Final output of the function, before and after:
   *    Before: Run ID string. After: Promise resolving to BacktestStatusResponse with CANCELLED state.
   */
  cancelBacktest: (runId) => req("POST", `/api/v1/backtest/cancel/${encodeURIComponent(runId)}`),

  /**
   * 1. The use of function:
   *    Lists registered strategies in StrategyRegistry with parameter schemas.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/backtest/strategies returning strategy catalog metadata.
   *
   * 3. Concepts used in the function:
   *    Strategy discovery, protocol registry, parameter introspection.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Strategy Tester strategy dropdown in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Promise resolving to array of StrategyInfo objects.
   */
  getStrategies: () => req("GET", "/api/v1/backtest/strategies"),

  // Paper Trading & Risk Controls (M6-06, M6-14, M6-18)
  /**
   * 1. The use of function:
   *    Retrieves active paper trading account ledger balances and equity metrics.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/paper/account with target account ID query parameter.
   *
   * 3. Concepts used in the function:
   *    Ledger projections, integer-paise financial accounting, margin reservation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by renderPaperTrading() in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Account ID string. After: Promise resolving to PaperAccount object.
   */
  getPaperAccount: (accountId = "ACC-MANUAL-PAPER") =>
    req("GET", `/api/v1/paper/account?account_id=${encodeURIComponent(accountId)}`),

  /**
   * 1. The use of function:
   *    Retrieves list of active open derivative paper positions.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/paper/positions for specified account.
   *
   * 3. Concepts used in the function:
   *    Mark-to-market position tracking, real-time PnL computation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by renderPaperTrading() in apps/web/js/app.js to populate positions table.
   *
   * 5. Final output of the function, before and after:
   *    Before: Account ID string. After: Promise resolving to array of PaperPosition objects.
   */
  getPaperPositions: (accountId = "ACC-MANUAL-PAPER") =>
    req("GET", `/api/v1/paper/positions?account_id=${encodeURIComponent(accountId)}`),

  /**
   * 1. The use of function:
   *    Submits discretionary or one-click paper order returning fill price and chart lines.
   *
   * 2. How does the specific function work:
   *    Dispatches POST request with PaperOrderRequest JSON payload to /api/v1/paper/orders.
   *
   * 3. Concepts used in the function:
   *    One-click order execution, pre-trade risk validation, on-chart price line calculation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Option Chain Buy/Sell buttons in executePaperOrderFromChain() in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: PaperOrderRequest payload. After: Promise resolving to PaperOrderResponse with chart lines.
   */
  submitPaperOrder: (order) => req("POST", "/api/v1/paper/orders", order),

  /**
   * 1. The use of function:
   *    Retrieves audit log of historical and working paper orders.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/paper/orders for specified account.
   *
   * 3. Concepts used in the function:
   *    Order audit trail, order state machine.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Paper Trading console in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Account ID string. After: Promise resolving to array of PaperOrder objects.
   */
  getPaperOrders: (accountId = "ACC-MANUAL-PAPER") =>
    req("GET", `/api/v1/paper/orders?account_id=${encodeURIComponent(accountId)}`),

  /**
   * 1. The use of function:
   *    Executes one-click square off for an active paper position.
   *
   * 2. How does the specific function work:
   *    Dispatches POST request to /api/v1/paper/square-off/{position_id} with account ID query parameter.
   *
   * 3. Concepts used in the function:
   *    Position liquidation, offsetting order submission, immediate fill.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by "Square Off" buttons in positions table in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Position ID and account ID. After: Promise resolving to liquidation PaperOrderResponse.
   */
  squareOffPaperPosition: (positionId, accountId = "ACC-MANUAL-PAPER") =>
    req("POST", `/api/v1/paper/square-off/${encodeURIComponent(positionId)}?account_id=${encodeURIComponent(accountId)}`),

  /**
   * 1. The use of function:
   *    Updates Stop-Loss and Take-Profit price brackets on an active open paper derivative position.
   *
   * 2. How does the specific function work:
   *    Dispatches PATCH request to /api/v1/paper/positions/{position_id}/brackets with updated price levels.
   *
   * 3. Concepts used in the function:
   *    REST PATCH mutation, interactive bracket adjustment, 5-paise tick snapping.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by on-chart draggable SL/TP line drop handlers in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Position ID and bracket levels payload. After: Promise resolving to updated PaperPosition.
   */
  updatePositionBrackets: (positionId, brackets) =>
    req("PATCH", `/api/v1/paper/positions/${encodeURIComponent(positionId)}/brackets`, brackets),

  /**
   * 1. The use of function:
   *    Retrieves automated strategy monitoring records for macro dashboard view.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/paper/strategies returning macro bot telemetry.
   *
   * 3. Concepts used in the function:
   *    Macro strategy supervision, multi-bot performance aggregation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Paper Trading macro view in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Promise resolving to array of PaperStrategyMacro objects.
   */
  getPaperStrategies: () => req("GET", "/api/v1/paper/strategies"),

  /**
   * 1. The use of function:
   *    Retrieves active risk management rules and boundary thresholds (RK-01 to RK-26).
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/paper/risk-policy returning frozen policy boundaries.
   *
   * 3. Concepts used in the function:
   *    Pre-trade risk policy, hard freeze ceiling (RK-06), daily loss limits.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by settings modal and risk card in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Promise resolving to RiskPolicySummary object.
   */
  getRiskRules: () => req("GET", "/api/v1/paper/risk-policy"),
  getPaperRiskPolicy: () => req("GET", "/api/v1/paper/risk-policy"),

  /**
   * 1. The use of function:
   *    Liquidates all active open derivative positions in batch.
   *
   * 2. How does the specific function work:
   *    Dispatches POST request to /api/v1/paper/square-off-all with optional account filter.
   *
   * 3. Concepts used in the function:
   *    Emergency portfolio liquidation, atomic batch execution.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by "Square Off All" button in Paper Trading micro view in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Optional account ID. After: Promise resolving to liquidation summary.
   */
  squareOffAllPositions: (accountId = null) =>
    req(
      "POST",
      accountId
        ? `/api/v1/paper/square-off-all?account_id=${encodeURIComponent(accountId)}`
        : "/api/v1/paper/square-off-all",
    ),

  /**
   * 1. The use of function:
   *    Cancels an active pending paper order.
   *
   * 2. How does the specific function work:
   *    Dispatches POST request to /api/v1/paper/orders/cancel/{orderId}.
   *
   * 3. Concepts used in the function:
   *    Order lifecycle management, pending order cancellation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Cancel button in Orders table in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Order ID string. After: Promise resolving to cancellation confirmation.
   */
  cancelPaperOrder: (orderId) =>
    req("POST", `/api/v1/paper/orders/cancel/${encodeURIComponent(orderId)}`),

  /**
   * 1. The use of function:
   *    Retrieves executed paper trade transaction history.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/paper/trades for specified account.
   *
   * 3. Concepts used in the function:
   *    Trade ledger audit logging, itemized transaction reporting.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Trade History table in Paper Trading console in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Account ID string. After: Promise resolving to array of PaperTrade objects.
   */
  getPaperTrades: (accountId = "ACC-MANUAL-PAPER") =>
    req("GET", `/api/v1/paper/trades?account_id=${encodeURIComponent(accountId)}`),

  // Screener & Heatmap (Section 6.1, Section 6.2)
  /**
   * 1. The use of function:
   *    Retrieves Indian market derivative screener data for NIFTY, VIX, and ATM options.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/market/screener.
   *
   * 3. Concepts used in the function:
   *    Market screening, index and derivative quotation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by renderScreener in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Promise resolving to ScreenerResponse object.
   */
  getScreener: () => req("GET", "/api/v1/market/screener"),

  /**
   * 1. The use of function:
   *    Retrieves parameter sensitivity heatmap matrix and monthly returns calendar.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/backtest/heatmap with strategy ID query parameter.
   *
   * 3. Concepts used in the function:
   *    Bivariate sensitivity analysis, monthly performance calendar.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by renderHeatmap in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: Strategy ID string. After: Promise resolving to StrategyHeatmapResponse object.
   */
  getHeatmap: (strategyId = "STRAT-CE-TREND") =>
    req("GET", `/api/v1/backtest/heatmap?strategy_id=${encodeURIComponent(strategyId)}`),

  // Chart Drawings Persistence (M6-13)
  /**
   * 1. The use of function:
   *    Retrieves saved chart drawing annotations for a symbol.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/charts/drawings with encoded symbol query parameter.
   *
   * 3. Concepts used in the function:
   *    Drawing persistence, chart annotation restoration.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by DrawingLayer in apps/web/js/drawings.js upon symbol loading.
   *
   * 5. Final output of the function, before and after:
   *    Before: Symbol string. After: Promise resolving to array of DrawingRecord objects.
   */
  getDrawings: (symbol = "NSE:NIFTY50") =>
    req("GET", `/api/v1/charts/drawings?symbol=${encodeURIComponent(symbol)}`),

  /**
   * 1. The use of function:
   *    Saves or updates a chart drawing annotation.
   *
   * 2. How does the specific function work:
   *    Dispatches POST request with DrawingRecord JSON payload to /api/v1/charts/drawings.
   *
   * 3. Concepts used in the function:
   *    Drawing state persistence, geometry serialization.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by DrawingLayer upon completing or moving an annotation.
   *
   * 5. Final output of the function, before and after:
   *    Before: Drawing object. After: Promise resolving to saved DrawingRecord.
   */
  saveDrawing: (drawing) => req("POST", "/api/v1/charts/drawings", drawing),

  /**
   * 1. The use of function:
   *    Deletes a specific chart drawing by ID.
   *
   * 2. How does the specific function work:
   *    Dispatches DELETE request to /api/v1/charts/drawings/{drawing_id}.
   *
   * 3. Concepts used in the function:
   *    REST DELETE resource removal, hit-test deletion.
   *
   * 4. Places where this function is imported and used:
   *    Invoked when user presses Delete key on an active drawing selection.
   *
   * 5. Final output of the function, before and after:
   *    Before: Drawing ID string. After: Promise resolving to DrawingDeleteResponse.
   */
  deleteDrawing: (drawingId) =>
    req("DELETE", `/api/v1/charts/drawings/${encodeURIComponent(drawingId)}`),

  /**
   * 1. The use of function:
   *    Clears all chart drawings for a symbol.
   *
   * 2. How does the specific function work:
   *    Dispatches DELETE request to /api/v1/charts/drawings?symbol=... without path ID.
   *
   * 3. Concepts used in the function:
   *    Bulk annotation deletion, canvas cleanup.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by drawing toolbar clear icon.
   *
   * 5. Final output of the function, before and after:
   *    Before: Symbol string. After: Promise resolving to DrawingDeleteResponse.
   */
  clearDrawings: (symbol = "NSE:NIFTY50") =>
    req("DELETE", `/api/v1/charts/drawings?symbol=${encodeURIComponent(symbol)}`),

  // Technical Indicators & Feature Schemas (M6-11, M6-17)
  /**
   * 1. The use of function:
   *    Retrieves catalog of available technical indicators from the FastAPI Gateway descriptor registry.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/charts/indicators returning IndicatorDescriptor records.
   *
   * 3. Concepts used in the function:
   *    Catalog discovery pattern, schema reflection, REST GET endpoint.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Indicators Catalog Dialog in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Promise resolving to array of IndicatorDescriptor objects.
   */
  getIndicatorsCatalog: () => req("GET", "/api/v1/charts/indicators"),

  /**
   * 1. The use of function:
   *    Computes server-side indicator timeseries on historical or live candles.
   *
   * 2. How does the specific function work:
   *    Dispatches POST request to /api/v1/charts/indicators/compute with IndicatorComputeRequest payload.
   *
   * 3. Concepts used in the function:
   *    Causal indicator evaluation, Lightweight Charts line coordinate timeseries.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by QuantChart in apps/web/js/chart.js for server-computed indicators (e.g. BOS/CHoCH).
   *
   * 5. Final output of the function, before and after:
   *    Before: Compute request object. After: Promise resolving to IndicatorComputeResponse.
   */
  computeIndicator: (payload) => req("POST", "/api/v1/charts/indicators/compute", payload),

  /**
   * 1. The use of function:
   *    Retrieves catalog of available technical features registered in Python FeatureRegistry.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/indicators/features returning feature definitions.
   *
   * 3. Concepts used in the function:
   *    Feature registry introspection, causal feature metadata.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by Indicators modal in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Promise resolving to array of feature summary objects.
   */
  getIndicatorFeatures: () => req("GET", "/api/v1/charts/indicators"),

  /**
   * 1. The use of function:
   *    Retrieves JSON Schema definitions for indicator parameter forms.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/indicators/schemas returning Draft 2020-12 schemas.
   *
   * 3. Concepts used in the function:
   *    Dynamic form generation, schema validation.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by indicator parameter configuration dialogs.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Promise resolving to schema dictionary.
   */
  getIndicatorSchemas: () => req("GET", "/api/v1/charts/indicators"),

  // System Health & Diagnostics (M6-02, M6-05)
  /**
   * 1. The use of function:
   *    Queries data lake session eligibility, capture counts, and chart licensing status.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/health/coverage querying DuckDB analytical lake views.
   *
   * 3. Concepts used in the function:
   *    Data lake telemetry, calendar coverage, license verification (M6-02, M6-05).
   *
   * 4. Places where this function is imported and used:
   *    Invoked by checkLakeStatus() and showHealthModal() in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Promise resolving to DataCoverageResponse.
   */
  getCoverage: () => req("GET", "/api/v1/health/coverage"),

  /**
   * 1. The use of function:
   *    Retrieves real-time process heartbeat diagnostics and runtime uptime.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/health/heartbeat returning PID and uptime.
   *
   * 3. Concepts used in the function:
   *    Process diagnostics, dead-man heartbeat telemetry.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by showHealthModal() in apps/web/js/app.js.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Promise resolving to HeartbeatResponse.
   */
  getHeartbeat: () => req("GET", "/api/v1/health/heartbeat"),

  /**
   * 1. The use of function:
   *    Retrieves canonical gateway service readiness status.
   *
   * 2. How does the specific function work:
   *    Dispatches GET request to /api/v1/health returning service name, status, and version.
   *
   * 3. Concepts used in the function:
   *    Service liveness probe, health checking.
   *
   * 4. Places where this function is imported and used:
   *    Invoked by gateway readiness pingers.
   *
   * 5. Final output of the function, before and after:
   *    Before: None. After: Promise resolving to HealthResponse.
   */
  getHealth: () => req("GET", "/api/v1/health"),
};

// ============================================================================
// Data Formatting Utilities
// ============================================================================

/**
 * 1. The use of function:
 *    Formats numeric asset prices with adaptive decimal precision.
 *
 * 2. How does the specific function work:
 *    Inspects magnitude of price value and formats with 2 to 4 decimal places.
 *    Returns em dash ('—') for null, undefined, or non-finite values.
 *
 * 3. Concepts used in the function:
 *    Adaptive precision rounding, number formatting.
 *
 * 4. Places where this function is imported and used:
 *    Imported across UI components for displaying prices, quotes, and strike levels.
 *
 * 5. Final output of the function, before and after:
 *    Before: Numeric price (e.g. 24850.5). After: Formatted string ("24,850.50").
 */
export function fmtPrice(v) {
  if (v == null || !Number.isFinite(v)) return "—";
  const absVal = Math.abs(v);
  const decimals = absVal >= 100 ? 2 : absVal >= 1 ? 2 : 4;
  return v.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: decimals,
  });
}

/**
 * 1. The use of function:
 *    Formats monetary values in Indian Rupees (INR) with currency symbol using Indian numbering system.
 *
 * 2. How does the specific function work:
 *    Uses Intl.NumberFormat with 'en-IN' locale and 'INR' currency style.
 *
 * 3. Concepts used in the function:
 *    Indian numbering system (lakhs, crores), currency formatting.
 *
 * 4. Places where this function is imported and used:
 *    Used in account cards, P&L columns, ledger tear sheets, and order modals.
 *
 * 5. Final output of the function, before and after:
 *    Before: Number (e.g. 1500000). After: Formatted string ("₹15,00,000.00").
 */
export function fmtRupees(v) {
  if (v == null || !Number.isFinite(v)) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v);
}

/**
 * 1. The use of function:
 *    Converts exact integer paise from backend ledger events to a formatted Indian Rupee string.
 *
 * 2. How does the specific function work:
 *    Divides integer paise by 100.0 and passes to fmtRupees().
 *
 * 3. Concepts used in the function:
 *    Integer-paise zero-drift conversion, currency formatting.
 *
 * 4. Places where this function is imported and used:
 *    Used wherever backend returns raw paise values (e.g. ledger projections).
 *
 * 5. Final output of the function, before and after:
 *    Before: Integer paise (e.g. 100050). After: Formatted string ("₹1,000.50").
 */
export function fmtPaise(v) {
  if (v == null || !Number.isFinite(v)) return "—";
  return fmtRupees(v / 100.0);
}

/**
 * 1. The use of function:
 *    Formats percentage values with explicit positive/negative sign indicator.
 *
 * 2. How does the specific function work:
 *    Returns sign prefix ('+' for positive, '' for negative) followed by fixed 2-decimal percentage.
 *
 * 3. Concepts used in the function:
 *    Signed percentage representation.
 *
 * 4. Places where this function is imported and used:
 *    Used in quotes, daily changes, returns tear sheets, and option Greeks displays.
 *
 * 5. Final output of the function, before and after:
 *    Before: Float 1.456. After: "+1.46%".
 */
export function fmtPct(v) {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

/**
 * 1. The use of function:
 *    Deterministically formats UTC epoch seconds into Indian Standard Time (IST, UTC+05:30) string.
 *
 * 2. How does the specific function work:
 *    Applies an exact 19,800-second offset (+5 hours 30 minutes) to the UTC epoch timestamp
 *    and extracts UTC calendar components. This completely isolates the display from client
 *    operating system timezone variations. Supports 'datetime' (default), 'time', or 'date' formats.
 *
 * 3. Concepts used in the function:
 *    Deterministic timezone projection, calendar component padding.
 *
 * 4. Places where this function is imported and used:
 *    Used in chart time scale tooltips, trade log timestamps, option chain snapshot timestamps.
 *
 * 5. Final output of the function, before and after:
 *    Before: UtcEpochSec (e.g. 1735703700). After: IST formatted string ("01/01/2025 09:15").
 */
export function fmtTime(utcSec, mode = "datetime") {
  if (utcSec == null || !Number.isFinite(utcSec) || utcSec <= 0) return "—";
  // Add 19800 seconds (5 hours 30 mins) for Asia/Kolkata
  const istDate = new Date((utcSec + 19800) * 1000);
  const pad = (n) => String(n).padStart(2, "0");

  const day = pad(istDate.getUTCDate());
  const month = pad(istDate.getUTCMonth() + 1);
  const year = istDate.getUTCFullYear();
  const hours = pad(istDate.getUTCHours());
  const mins = pad(istDate.getUTCMinutes());
  const secs = pad(istDate.getUTCSeconds());

  if (mode === "time") {
    return `${hours}:${mins}:${secs}`;
  }
  if (mode === "shortTime") {
    return `${hours}:${mins}`;
  }
  if (mode === "date") {
    return `${day}/${month}/${year}`;
  }
  return `${day}/${month}/${year} ${hours}:${mins}`;
}

/**
 * 1. The use of function:
 *    Escapes raw string inputs to prevent Cross-Site Scripting (XSS) when rendering dynamic HTML.
 *
 * 2. How does the specific function work:
 *    Replaces characters &, <, >, ", ' with their corresponding HTML entity codes.
 *
 * 3. Concepts used in the function:
 *    HTML entity escaping, defensive frontend security.
 *
 * 4. Places where this function is imported and used:
 *    Used across dynamic table and card generators in apps/web/js/app.js.
 *
 * 5. Final output of the function, before and after:
 *    Before: "<script>". After: "&lt;script&gt;".
 */
export function esc(str) {
  return String(str ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c],
  );
}
