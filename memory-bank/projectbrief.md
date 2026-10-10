# QuantView — Project Brief

## Project identity
QuantView is a TradingView-inspired quantitative research and trading platform for Indian markets (NSE/NIFTY). It combines historical charting, validated market-data pipelines, custom indicators, strategy research, event-driven backtesting, paper trading, and a future broker-execution adapter (Upstox).

## Core goals
1. Reliable, auditable NIFTY market data (underlying candles + option chain) with provenance.
2. Quant research: indicators, features, strategy contracts, visual and Python strategies.
3. Event-driven backtesting with three distinct modes (underlying directional, synthetic, actual option P&L).
4. Paper trading using the same strategy/order contracts as future live execution.
5. Gated live broker execution (Upstox) — disabled until all safety gates pass.

## Non-negotiable constraints
- Raw collected data is NEVER overwritten without a checksummed backup.
- No look-ahead in features, joins, contract selection, or fill decisions.
- Underlying directional P&L is never reported as actual option P&L.
- Synthetic option estimates stay research-only.
- Live trading disabled until phases 0–5 gates pass and owner approves.
- No git commits or pushes (per workspace rules).

## Repository root
`C:\Algo\Options`

## Primary data paths
- Historical candles: `Data/historical/candles/index/nifty/{tf}/nifty.csv`
- Live daily candles: `Data/live/candles/index/nifty/1m/nifty_YYYY-MM-DD.csv`
- Option chain snapshots: `Data/live/option_chain/nifty/{expiry}/{trade_date}/snapshots/*.csv`

## Key documentation location
`DOCS/` — contains AGENTS.md, README.md, IMPLEMENTATION_PLAN.md, data_status.md, and `docs/` subdirectory with 22+ spec files.
