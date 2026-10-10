# System Patterns

## Architecture pattern
Modular monolith — six bounded packages sharing one process initially. Extract only when measured need exists.

## Six bounded packages (none implemented yet)
1. `market_data` — adapters, raw archive, normalization, quality, candle builder
2. `instruments` — instrument master, exchange calendar, effective-dated expiry rules
3. `research` — indicators/features, strategy contracts, Python runtime, contract selection
4. `simulation` — event clock, event loop, fill models (historical + paper), positions
5. `ledger` — append-only financial events, cash/positions/P&L projections
6. `api` — REST + WebSocket endpoints (no business logic duplication)
7. Frontend — Next.js + Lightweight Charts (separate project)

## Dependency rules (from ADR-002)
- `api` → all other modules (orchestrate, not reimplement)
- `research` → `market_data`, `instruments`
- `simulation` → `market_data`, `instruments`, `research`, `ledger`
- `research` ✗ broker adapters
- `market_data` ✗ broker adapters
- Enforce with `import-linter` in CI

## Storage decisions (ADR-004 Provisional)
- Raw CSVs: immutable archive (never overwrite without checksummed backup)
- Historical/analytical: Parquet + DuckDB
- Transactional (orders, ledger, accounts): PostgreSQL
- Defer: TimescaleDB, Redis, Kafka

## Time semantics (ADR-006)
- `bar_start`, `bar_end`, `available_at`, `ingested_at`, `source_ts` are distinct fields
- `bar_end` computed from interval + session calendar, NOT `bar_start + timeframe`
- All intraday joins are backward/as-of using `available_at`
- All timestamps stored/compared in IST (Asia/Kolkata) or UTC with explicit conversion

## Candle timestamp convention (observed in existing data)
- Intraday: bar_start labeled (e.g., `09:15:00+05:30` = 09:15–09:16 bar)
- Daily: midnight IST label (`00:00:00+05:30`) — NOT availability time
- `bar_end` and `available_at` NOT yet stored — must be added

## Key ADRs
- ADR-003: Raw archive immutable — never overwrite source CSVs
- ADR-005: 1m candles are canonical source for derived intraday TFs; retain native TFs for reconciliation
- ADR-009: Three separate P&L modes — underlying directional / synthetic / actual-options (never mixed)
- ADR-010: Upstox expired options is provisional until API access confirmed
- ADR-012: Live trading gated — disabled by default always

## Expiry rules (NIFTY)
- Thursday weekly expiry until approx. April 2025
- Tuesday weekly expiry from approx. April 2025 (exact date per NSE circular — not yet confirmed)
- Must be stored as effective-dated rules, not hardcoded weekday

## Data integrity invariants
- No look-ahead in any join, feature, or contract selection
- Missing data → null + quality flag; never silently forward-fill or zero-fill
- Options: synthetic prices ≠ actual fill prices; always separate
- Ledger events are append-only; corrections via reversal entries

## Current critical patterns (anti-patterns to fix)
- Scripts use hardcoded absolute paths → fix with `PROJECT_ROOT` constant
- `merge_extensions.py` overwrites raw `nifty.csv` → add backup before merge
- `data_status.py` uses `freq="B"` for expected sessions → replace with G1 calendar
