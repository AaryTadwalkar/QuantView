"""
1. What this file does:
   Defines the routers package for QuantView FastAPI endpoints
   (Milestones M6-01, M6-02, M6-03, M6-03b, M6-04, M6-05, M6-06, M6-07, M6-08, M6-09, M6-11, M6-13, M6-14, M6-15, M6-16, M6-18, and Release Gate G4).

2. Overall design:
   Aggregates route sub-modules for health, market candles, option chains, Greeks,
   backtests, paper trading, technical indicators, and chart drawings into modular APIRouter controllers.

3. Elements in the file:
   - backtest: Backtest execution, status polling, and strategy catalog endpoints.
   - drawings: Chart drawing persistence and CRUD endpoints.
   - health: Health, heartbeat, and data coverage/licensing diagnostic endpoints.
   - indicators: Technical indicator descriptors and calculation endpoints.
   - market: Market data, symbol catalog, and historical/real-time OHLCV candle query endpoints.
   - options: Option chain matrix, expiry catalog, and per-contract option candle query endpoints.
   - paper: Paper trading accounts, positions, orders, trades, and risk policy endpoints.

4. Final output of the file:
   - Exported route controllers for services.api.
"""

from services.api.routers import backtest, drawings, health, indicators, market, options, paper

__all__ = ["backtest", "drawings", "health", "indicators", "market", "options", "paper"]
