"""
1. What this file does:
   Defines the schemas package and exports common data transfer objects for the QuantView API
   (Milestones M6-01, M6-02, M6-03, M6-03b, M6-04, M6-05, M6-06, M6-07, M6-08, M6-09, M6-11, M6-13, M6-14, M6-15, M6-16, M6-18, and Release Gate G4).

2. Overall design:
   Aggregates domain-specific Pydantic schema models for market candles, quotes, symbols,
   option chains, Greeks, option candles, backtests, trade logs, chart markers, paper trading accounts,
   positions, orders, trades, risk policy summaries, indicator definitions, compute responses, and chart drawings
   into a unified import namespace.

3. Elements in the file:
   - Candle: Single OHLCV bar schema.
   - CandleResponse: Candle list response envelope.
   - MarketQuote: Ticker and market quote schema.
   - SymbolInfo: Symbol specification schema.
   - OptionStrikeQuote: Individual option strike quote with Greeks.
   - OptionChainRow: Paired Call/Put strike matrix row.
   - OptionChainResponse: Full option chain response container.
   - OptionCandleResponse: Per-contract option candlestick response container.
   - BacktestRequest: Backtest configuration launch schema.
   - ChartMarker: Lightweight Charts series marker schema.
   - EquityPoint: Mark-to-market equity timeseries point schema.
   - TradeRecord: Itemized round-trip trade record schema.
   - BacktestMetricsSummary: Quantitative metrics summary schema.
   - BacktestRunResponse: Complete backtest execution result container.
   - StrategyInfo: Strategy registry metadata schema.
   - BacktestStatusResponse: Backtest lifecycle status response container.
   - ChartPriceLines: Visual entry price, SL, and TP line coordinates schema.
   - PaperAccount: Paper trading account financial ledger schema.
   - PaperPosition: Real-time open derivative paper position schema.
   - PaperOrderRequest: Discretionary order submission schema.
   - PaperOrderResponse: Order execution and fill confirmation schema.
   - PaperOrder: Working and historical order state schema.
   - PaperTrade: Executed trade transaction audit schema.
   - PaperStrategyMacro: Automated strategy macro telemetry schema.
   - RiskPolicySummary: Pre-trade risk policy limit configuration schema.
   - DataCoverageResponse: Lake session coverage and licensing schema.
   - DrawingPoint: Chart coordinate point schema.
   - DrawingRecord: Persistent chart drawing annotation schema.
   - DrawingDeleteResponse: Drawing deletion confirmation schema.
   - IndicatorParameter: Configurable indicator parameter definition schema.
   - IndicatorDescriptor: Indicator specification schema.
   - IndicatorComputeRequest: On-demand indicator calculation request schema.
   - IndicatorValuePoint: Indicator timestamped output point schema.
   - IndicatorComputeResponse: Computed indicator series response schema.

4. Final output of the file:
   - Re-exported schema models for services.api.
"""

from services.api.routers.health import (
    DataCoverageResponse,
    HealthResponse,
    HeartbeatResponse,
)
from services.api.schemas.backtest import (
    BacktestMetricsSummary,
    BacktestRequest,
    BacktestRunResponse,
    BacktestStatusResponse,
    ChartMarker,
    EquityPoint,
    StrategyInfo,
    TradeRecord,
)
from services.api.schemas.drawings import (
    DrawingDeleteResponse,
    DrawingPoint,
    DrawingRecord,
)
from services.api.schemas.indicators import (
    IndicatorComputeRequest,
    IndicatorComputeResponse,
    IndicatorDescriptor,
    IndicatorParameter,
    IndicatorValuePoint,
)
from services.api.schemas.market import (
    Candle,
    CandleResponse,
    MarketQuote,
    SymbolInfo,
)
from services.api.schemas.options import (
    OptionCandleResponse,
    OptionChainResponse,
    OptionChainRow,
    OptionStrikeQuote,
)
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

__all__ = [
    "BacktestMetricsSummary",
    "BacktestRequest",
    "BacktestRunResponse",
    "BacktestStatusResponse",
    "Candle",
    "CandleResponse",
    "ChartMarker",
    "ChartPriceLines",
    "DataCoverageResponse",
    "DrawingDeleteResponse",
    "DrawingPoint",
    "DrawingRecord",
    "EquityPoint",
    "HealthResponse",
    "HeartbeatResponse",
    "IndicatorComputeRequest",
    "IndicatorComputeResponse",
    "IndicatorDescriptor",
    "IndicatorParameter",
    "IndicatorValuePoint",
    "MarketQuote",
    "OptionCandleResponse",
    "OptionChainResponse",
    "OptionChainRow",
    "OptionStrikeQuote",
    "PaperAccount",
    "PaperOrder",
    "PaperOrderRequest",
    "PaperOrderResponse",
    "PaperPosition",
    "PaperStrategyMacro",
    "PaperTrade",
    "RiskPolicySummary",
    "StrategyInfo",
    "SymbolInfo",
    "TradeRecord",
]
