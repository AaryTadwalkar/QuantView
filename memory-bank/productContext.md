# Product Context

## What QuantView is
A research-first quantitative trading terminal for Indian markets (NSE NIFTY focus). Inspired by TradingView but designed specifically for quantitative researchers who want to go from historical chart analysis through backtesting to live automated trading with full auditability.

## Problems it solves
1. **Data quality opacity:** Existing collected data has unknown gaps, schema variations, and unclear timestamp semantics — QuantView will surface all of this explicitly.
2. **Look-ahead contamination:** Standard backtests silently use future data. QuantView enforces point-in-time correctness at every layer.
3. **P&L confusion:** Underlying directional strategy results are often mistakenly presented as options P&L. QuantView separates these into three distinct modes.
4. **Broker coupling:** Strategy code often imports broker SDKs directly. QuantView enforces strict module boundaries.
5. **Ungated live trading:** The platform defaults everything to research/paper mode with explicit gating for live execution.

## User experience goals
- A TradingView-like chart interface with gaps and data quality visible.
- Strategy development in Python with a versioned interface.
- Backtest results that explicitly show limitations, data coverage, and assumptions.
- Paper trading that uses the same contracts as eventual live trading.
- Clear operational visibility: data freshness, collector health, account state.

## Target user (current phase)
Single developer/researcher — no multi-tenancy concerns in Phase 0-2.

## What it is NOT
- Not a real-time trading platform (until Phase 7 gates pass).
- Not a black-box signal generator.
- Not a tool for sharing or redistributing market data.
- Not a guarantee of profitable strategies.

## Current phase
Phase 0 — Data infrastructure and quality audit. No strategy development until G1-G8 pass.
