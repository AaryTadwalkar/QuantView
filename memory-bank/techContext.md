# Tech Context

## Runtime
- Python 3.11 (venv at `C:\Algo\Options\venv\` and `c:\Algo\quantview`)
- Node.js / TypeScript for Next.js frontend
- OS: Windows 11

## Core Python Dependencies (v1.4 Target Architecture)
- pandas 3.0.6, numpy 2.4.6
- pyarrow (Parquet columnar storage)
- duckdb (analytical queries on historical candles and options)
- psycopg / asyncpg (PostgreSQL transactional state for `qv_core`, `qv_paper`, `qv_live`)
- fastapi, uvicorn, websockets (REST and real-time streaming API)
- pydantic v2 (canonical schema validation)
- pytest, pytest-asyncio, hypothesis (testing framework)
- import-linter (clean package boundary enforcement)

## Frontend Dependencies
- Next.js 14+ (App Router), React 18+
- TradingView Lightweight Charts (isolated inside `LightweightChartsAdapter` per `ADR-041`)
- Zustand (client state management using canonical `UtcEpochSec` integer timestamps)
- Tailwind CSS

## Upstox Integration
- API version: v3 (historical candle), v3 (market data feed WebSocket)
- Auth: Bearer token from `UPSTOX_ACCESS_TOKEN` in `.env`
- Rate limiting: handled with `time.sleep(0.5)` and 3-retry on 429
- Token type: Short-lived OAuth access token (expires daily)
- Instrument key: `NSE_INDEX|Nifty 50`
- Historical candle endpoint: `https://api.upstox.com/v3/historical-candle/{key}/{unit}/{interval}/{to}/{from}`
- Live market data feed WebSocket for ticks and market depth

## Data Storage Structure
```
C:\Algo\Options\
  Data/
    historical/candles/index/nifty/{1m,3m,5m,15m,1h,4h,1d}/nifty.csv
    live/candles/index/nifty/1m/nifty_YYYY-MM-DD.csv
    live/option_chain/nifty/{expiry_date}/{trade_date}/snapshots/HH-MM-SS.csv
```

## Database Topology
- Three physically isolated PostgreSQL databases:
  1. `qv_core`: Master metadata, user preferences, instrument catalog, backtest runs.
  2. `qv_paper`: Paper accounts, paper orders, paper positions, paper ledger events.
  3. `qv_live`: Phase 9 live trading database (strictly isolated, locked until `GATE-05`).

## Timezone & Timestamp Handling (`ADR-006`, `ADR-008`, `ADR-041`)
- Exchange timezone: Asia/Kolkata (IST, UTC+05:30, no DST).
- Canonical Chart Timestamps: `UtcEpochSec` (`int64` UTC epoch seconds) used universally across stores, APIs, markers, and replay cursors. IST display offset strictly isolated inside `LightweightChartsAdapter`.
- Causal Availability: `available_at = bar_end` under `HISTORICAL_ASSUMED_AVAILABILITY` for backtests; `available_at = finalized_at = bar_end + grace_period` in live streams.

## Development Constraints
- No git commits or pushes (workspace rule).
- Raw data archive is strictly immutable (`P1`, `ADR-003`).
