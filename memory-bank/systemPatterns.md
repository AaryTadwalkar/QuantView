# System Patterns

## Architecture pattern
Modular monolith — six bounded packages sharing one process initially. Extract only when measured need exists.

## System Modules & Low-Level Sub-modules
1. **Frontend** 
   - Charting: TradingView-like UI for historical and live visualization (`UtcEpochSec` timestamp contract via `LightweightChartsAdapter`).
   - UI Controls: Forms for backtest execution and paper trading.
   - Data Quality Dashboard: Surfaces data gaps and freshness metrics.
2. **API (`api`)**
   - REST Endpoints: Serves historical data, handles configuration.
   - WebSocket Streaming: Real-time price updates and execution states.
   - Orchestration Layer: Connects decoupled backend modules without business logic duplication.
3. **Simulation (`simulation`)**
   - Event Clock: Orchestrates point-in-time ticks for historical backtests.
   - Fill Models: Approximates live execution using historical/paper data.
   - Position Tracker: Maintains state of held contracts during backtests.
   - P&L Engine: Separates canonical result types (`UNDERLYING_DIRECTIONAL`, `SYNTHETIC_OPTIONS_ESTIMATE`, `ACTUAL_OPTIONS`).
4. **Research (`research`)**
   - Feature Extraction: Builds lag features, technical indicators, and data transformations without look-ahead bias (`available_at <= decision_time`).
   - ML Offline (`ADR-040`): Strictly optional data preparation, model evaluation metrics, and local dataset caching.
   - ML Training Strategies: Optional training pipelines across distinct time regimes.
   - Contract Selection: Logic for selecting which strike/expiry to trade based on signals.
5. **Ledger (`ledger`)**
   - Financial Events: Append-only log of trades and deposits in integer paise (`ROUND_HALF_UP`).
   - P&L Projections: Reconciles theoretical vs realized profits.
6. **Market Data (`market_data`)**
   - Adapters: Connects to broker endpoints.
   - Raw Archive: Immutable CSV storage.
   - Normalization: Converts varied formats to standard parquets.
   - Quality Checker: Flags missing rows and verifies timestamps.
   - Candle Builder: Aggregates 1m data to higher timeframes.
7. **Instruments (`instruments`)**
   - Master Catalog: Metadata for all tradable assets.
   - Exchange Calendar: Valid trading days and session timings.
   - Expiry Rules: Effective-dated logic for weekly and monthly expiries.

## Dependency rules (from ADR-002)
- `api` → all other modules (orchestrate, not reimplement)
- `research` → `market_data`, `instruments`
- `simulation` → `market_data`, `instruments`, `research`, `ledger`
- `research` ✗ broker adapters
- `market_data` ✗ broker adapters
- Enforce with `import-linter` in CI

## Storage decisions (ADR-004)
- Raw CSVs: immutable archive (never overwrite without checksummed backup)
- Historical/analytical: Parquet + DuckDB
- Transactional (orders, ledger, accounts): PostgreSQL (`qv_core`, `qv_paper`, `qv_live` isolated)

## Time semantics & Causal Availability (ADR-006, ADR-008, ADR-041)
- `bar_start`, `bar_end`, `available_at`, `ingested_at`, `source_ts` are distinct fields.
- Historical Backtests: `available_at = bar_end` under `HISTORICAL_ASSUMED_AVAILABILITY` (clipped to session close).
- Live Streaming: `available_at = finalized_at = bar_end + grace_period` (where `grace_period` accounts for finalization/network latency; never backdated to `bar_end`).
- Universal Invariant: `feature.available_at <= decision_time`.
- Frontend Charting: Branded `UtcEpochSec` (`int64` UTC seconds) canonical contract across stores, APIs, markers, and replay cursors; IST (`Asia/Kolkata`, `UTC+05:30`) display offset strictly isolated inside `LightweightChartsAdapter`.

## Canonical Operating & Allocation Modes
- **Operating Modes:** `RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`.
- **Allocation Modes (`ADR-038`):** `ISOLATED` (single active deployment per account) and `PORTFOLIO` (multiple deployments sharing account risk ceilings).
- **Risk Catalogue (`RK-01–RK-26`):** `RK-06` (`HARD_ORDER_FREEZE_LIMIT`, pre-submit exchange block) vs `RK-26` (`ADVISORY_ORDER_LOT_CEILING`, non-blocking advisory in manual paper).

## Key ADRs
- ADR-003: Raw archive immutable
- ADR-005: 1m candles are canonical source
- ADR-007: 4-tier document hierarchy and 6 conflict resolution rules
- ADR-008: Causal availability model (live vs historical distinction)
- ADR-009: Strict separation of underlying directional vs actual options P&L
- ADR-012: Live trading gated — disabled by default (`NO-GO`) until Phase 9 `GATE-05`
- ADR-026: Three-Lock Live Arming
- ADR-038: Account allocation modes (`ISOLATED` vs `PORTFOLIO`)
- ADR-039: Conservative `LIMIT` orders deferred post-v1 (v1 manual orders market-only)
- ADR-040: Optional ML extension over `Strategy(Protocol)`
- ADR-041: Canonical `UtcEpochSec` chart timestamp contract

## Data integrity invariants
- No look-ahead in any join, feature, or contract selection (`available_at <= decision_time`).
- Missing data → null + quality flag; never silently forward-fill.
- Ledger events are append-only in integer paise; corrections via reversal entries.
