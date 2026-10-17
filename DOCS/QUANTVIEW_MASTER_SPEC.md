# QuantView Architecture — Master Specification

**Document type:** Master Specification (Decision Register, Architecture Overview, and Owner Decisions)  
**Scope:** Single-user NIFTY 50 options research, backtesting and paper trading  
**Status vocabulary:** `DESIGNED` = decided on paper; `IMPLEMENTED` = code exists; `TESTED` = automated/manual tests passed; `VERIFIED` = checked against authoritative external behaviour or source data.  
**Current document status:** decisions are **DESIGNED** unless a project audit supplies evidence otherwise. This document does not claim implementation.

## ADR-001 — Product scope

**Status:** DESIGNED

**Context**  
QuantView is a single-user NIFTY 50 options research, backtesting, charting and paper-trading platform. It compares strategy hypotheses on audited data; it does not presume any strategy family or direction is profitable.

**Decision**  
Build a modular monolith in one repository. V1 is research and paper trading only: no real orders, multi-user SaaS, microservices or runtime Pine interpreter. Strategies are versioned, parameterized, loaded through a registry and receive read-only point-in-time context; they cannot access broker or database internals directly.

The position model is direction-agnostic and represents long/short CE/PE, multiple independent strategy deployments, and simple declared-leg groups. Single-leg long CE/PE is the first realistic-account slice; short/multi-leg realism is gated by margin, buying-power, fill/legging and settlement evidence. These gates constrain realism claims, not which hypotheses the research registry can represent.

**Authoritative v1 scope**

| Included in staged v1 | Deferred/gated | Excluded |
|---|---|---|
| Collectors and audited canonical data; deterministic backtests; CE/PE/BOTH and direction switching; long/short representation; declared-leg model; risk/fee assumptions with evidence labels; minimal feature registry; core chart/results UI; isolated paper accounts | Realistic-account short/multi-leg until margin and legging/settlement tests pass; optional cache until benchmarked; Redis/Valkey adapter until justified; advanced drawings; Renko; on-tick strategies; UI-3 option-chain/OI/layout features scheduled for v1.1 | Real orders; multi-user auth; microservices/Kubernetes; runtime Pine interpreter; autonomous/self-modifying ML |

**Rejected alternatives**  
Assuming long-only options are inherently preferable; claiming strategy profitability from general retail-loss statistics; enabling real orders by swapping the paper broker; runtime Pine interpretation; multi-tenant infrastructure for one user.

**Consequences / trade-offs**  
The system supports a broad hypothesis space, while realistic-account execution is enabled only where the relevant position-side, margin, fill and settlement semantics are tested. The implementation plan stages G2a before G2b to deliver the single-leg baseline sooner.

## ADR-002 — Storage and query stack

**Status:** DESIGNED

**Context**  
Market data is append-heavy and analytical; account, job, deployment and ledger state needs transactional constraints and concurrent writers. DuckDB should not be used as a multi-process shared writer.

**Decision**  
- **Parquet** is the canonical persistent store for normalized market data, derived feature caches and backtest run artifacts. Dataset manifests on disk are authoritative.
- **DuckDB** is the embedded analytical query engine over Parquet. Query processes read canonical files; ingestion jobs publish immutable files. DuckDB is not a shared multi-process writer.
- **PostgreSQL** is the operational system of record for accounts, paper orders/fills, event ledger, projections, registries, deployments, jobs, settings, layouts and drawings. For datasets, Postgres stores only a manifest index row (`id`, `path`, `sha256`, `status`), not a second authoritative manifest.
- Live transport uses a small `FrameBus` interface. Initial implementation is a local Unix socket/asyncio transport with monotonic `sequence_number` values and replay from durable raw segments. Redis/Valkey is an optional adapter only if measured p95 latency exceeds 500 ms or restart/resume requirements justify the extra service; it is never the durable source of truth.
- Raw source payloads are immutable files, compressed with zstd where suitable. Money is stored as integer paise or exact `NUMERIC`/`Decimal`, never binary float.
- Publish protocol: write to staging, validate schema/counts/keys/hashes, atomically rename finalized artifacts, then update the authoritative manifest pointer. A failed publish leaves the previous pointer intact. Optional feature-cache artifacts are content-addressed and write-once; concurrent writers race to publish and the loser discards its duplicate output.

**Rejected alternatives**  
TimescaleDB, QuestDB, ClickHouse, InfluxDB, MongoDB, SQLite as the multi-process ledger, and Delta/Iceberg table formats for v1. Reconsider only with measured bottlenecks or recovery requirements.

**Consequences / trade-offs**  
Parquet/DuckDB optimize local analytical scans while Postgres protects transactional state; developers must respect the separate ownership boundaries. A local FrameBus is simpler but requires raw replay to recover after process loss.

## ADR-003 — Raw-first ingestion and collector priority

**Status:** DESIGNED

**Context**  
Missed live sessions cannot be reconstructed later. Existing snapshot collection has late starts, gaps, early stops and schema drift. The expired-option candle inventory was audited (M0-01) and only one sample day (2025-04-24) exists; the bulk history is not yet downloaded.

**Decision**  
Collectors are the first build phase. Run `collector_snapshot` and `collector_ws` independently with restart supervision, clock synchronization, heartbeat/lag metrics and alerts. **`collector_ws` is the sole owner of all Upstox WebSocket connections**. Its `SubscriptionManager` computes the union of subscriptions required by active deployments and chart requests, enforces only empirically verified limits, and exposes the effective subscription set and rejected requests to the UI. `collector_ws` persists raw messages before normalization. Until M7-01 is implemented and tested, it is raw-capture-only; it must not depend on a live consumer. M2 may define a typed no-op producer interface, but actual FrameBus publication/replay begins at M7-01. Replay reads finalized raw segments. Start with local transport and add a Redis/Valkey adapter only if measured latency or resume complexity justifies it. `live_daemon` never opens an Upstox WebSocket. Capture at least two representative market sessions as fixtures before implementing the decoder. Historical backfill jobs are checkpointed, idempotent and lower priority than snapshot capture.

**Rejected alternatives**  
Building the UI/backtest engine first and postponing collection; relying on the WebSocket to represent the full option chain; normalizing messages without retaining raw evidence.

**VERIFY**  
Check current Upstox V3 subscription/connection limits, feed modes, protobuf schema and fields, entitlement requirements, reconnect behaviour, token expiry, expired-instruments retention window and terms for retaining/offsite-backing-up market data. Record date and source. If expired-instrument retention is rolling, historical raw backfill is a data-preservation priority. Give `collector_snapshot` a reserved REST rate-limit quota; throttle/pause backfill during market hours unless the measured remaining budget permits it. Do not assume prior documentation remains current.

**Consequences / trade-offs**  
Collectors and raw retention precede UI polish, which costs early setup time but reduces irrecoverable history loss. Vendor limits and storage terms remain external gates.

## ADR-004 — Canonical timeframes and market clock

**Status:** DESIGNED

**Context**  
Vendor higher-timeframe files disagree on day coverage and can conceal whole missing sessions. Intraday bar timestamps and incomplete bars can otherwise cause look-ahead.

**Decision**  
Source of truth by interval: **1m = vendor source; 3m/5m/15m/1h/4h = derived from canonical 1m; 1d = vendor daily series; 1w/1M = derived from canonical vendor 1d**. Store vendor daily bars at `lake/underlying_candles/interval=1d/`. The reviewed inventory indicates daily history from 2021-02, but Phase 1 must verify coverage. A daily bar becomes available at the official session close (`available_at = session close`); the current session daily bar is never usable intraday. 1m-derived daily OHLC is diagnostic only. Vendor intraday higher-timeframe files remain comparison/checksum data. Use start-stamped intraday bars representing `[start, end)`; a closed intraday bar becomes available at `available_at = end`. Anchor each session to the calendar's `open_time_local`, not a hard-coded 09:15. Special sessions (including Muhurat or Budget-day sessions where applicable) generate their own bar grid. A regular-session 4h example is 09:15–13:15 and a partial 13:15–15:30 bar, subject to the versioned calendar. All internal instants are UTC; calendar rules and display use `Asia/Kolkata`.

**Rejected alternatives**  
Treating vendor higher timeframes as equal-authority sources; inferring missing candles; assuming every date is a normal trading session.

**Consequences / trade-offs**  
Using vendor daily bars preserves official daily semantics, while higher intraday intervals are reproducible derivatives. This means the daily series may not reconcile exactly with an intraday aggregation, which is reported rather than silently overwritten.

## ADR-005 — Calendar and contract truth

**Status:** DESIGNED

**Context**  
Expiry weekdays, lot sizes and holiday shifts have changed. Weekend-looking records may represent special sessions or bad data.

**Decision**  
Use a versioned exchange calendar cross-checked against official NSE holidays and special sessions. Maintain a validity-dated contract master from instrument metadata, including expiry, strike, option type, instrument key, lot size, tick size and validity interval. Never infer expiry or lot size solely from weekday/strike conventions. Every backtest resolves contracts using point-in-time master records.

**Rejected alternatives**  
Hard-coded Tuesday expiry logic; applying today's lot size to old contracts; treating all weekends as invalid without official calendar reconciliation.

**Consequences / trade-offs**  
Point-in-time calendar and contract metadata increase data-audit work but prevent hindsight contract selection and incorrect historical lot/tick assumptions.

## ADR-006 — Option-chain reconstruction and Greeks provenance

**Status:** DESIGNED

**Context**  
Observed snapshots are incomplete and begin in 2026. Option candles include per-contract OI and volume fields, but their precise semantics need audit. Historical option-candle coverage is not yet quantified.

**Decision**  
Create a `ChainProvider` with three explicitly labelled tiers: (1) live WebSocket state, (2) observed REST snapshots with capture/receive time and nullable fields, (3) reconstructed minute chain from option candles. Compute historical model IV/Greeks from option price, spot, time-to-expiry and a put-call-parity forward where inputs and assumptions permit. Label all model outputs `model_*`; never silently blend them with observed vendor values. Features declare which tier/fields they require and enforce maximum staleness. Keep every snapshot capture as captured; never fabricate a regular 30-second grid or fill missing fields with zero.

**Rejected alternatives**  
Treating snapshots as complete continuous history; pretending model Greeks are observed Greeks; synthetic 30-second snapshots; zero-filling absent fields.

**VERIFY**  
Audit whether option-candle `volume` is contracts, units or lots; whether `oi` is instantaneous/end-of-minute/cumulative and how zero-volume bars are emitted. Compare known contracts against Upstox examples or broker statements. Record the verified result and source evidence before using these fields in trading rules.

**Consequences / trade-offs**  
Incomplete observations reduce the number of eligible features/periods. Provenance labels are intentionally preferred over filling gaps or presenting model values as vendor-observed facts.

## ADR-007 — Feature registry and cache

**Status:** DESIGNED

**Context**  
Users need built-in indicators, custom indicators, option-chain metrics and price-action events. Recomputing all features for every chart/backtest is wasteful, but caching without provenance creates stale or non-reproducible results.

**Decision**  
Compute features on demand first. Add a content-addressed Parquet cache only if a representative benchmark shows recomputation is a material bottleneck. If enabled, partition monthly and key it by `feature_id + code_hash + params_hash + partition_input_hash + upstream_state_hash`; the upstream state hash covers warm-up inputs or the prior checkpoint. Appending a day then recomputes only affected monthly partitions and downstream partitions whose checkpoint/input hash changes. A registry decorator declares ID, version, parameter model, inputs, outputs, warm-up, live/batch capabilities and memory class: `finite(W)` for finite-window features or `infinite` for recursive/unbounded-memory features. Infinite-memory features store checkpointed end-state per monthly partition or recompute from the beginning of the declared data range. Chunk-equivalence tests use each feature's declared tolerance. The UI derives parameter forms from the schema. Chart and strategy dependencies are unioned; strategy features continue even when not drawn. Require truncation tests for all time-series features. BOS/CHoCH events expose `pivot_time` and `confirmed_at`; strategies may consume only after confirmation. Heikin Ashi/Renko are visual transforms, never execution prices.

**Rejected alternatives**  
Persist every possible feature; rely only on live calculation; runtime Pine interpretation; unversioned cache keys; sandboxing trusted repository code instead of testing it.

**Consequences / trade-offs**  
On-demand calculation is the simpler default and may repeat work; caching is added only after benchmarks show a material bottleneck. If enabled, cache invalidation and checkpoint provenance become additional correctness obligations.

## ADR-008 — One causal engine, three modes

**Status:** DESIGNED

**Context**  
Backtest and live runtimes can drift if they use different signal timing or strategy interfaces. The system needs deterministic research plus a persistent paper daemon.

**Decision**  
Share strategy interfaces and event semantics across `backtest`, `replay` and `live paper` modes. Strategies declare dependencies and receive a read-only point-in-time context; they do not access DBs or brokers directly. Backtest is deterministic, session-chunked and event-driven. The live daemon is a separate process with serializable strategy state and replay-on-restart.

**Rejected alternatives**  
Independent backtest and live strategy implementations; strategies issuing broker orders directly; coupling paper trading lifecycle to API process lifetime.

**Consequences / trade-offs**  
A shared causal engine reduces backtest/replay drift but requires deterministic event contracts and serialization of strategy state. Live quote fills and OHLC backtests remain different evidence tiers.

## ADR-009 — Execution timing and intrabar policy

**Status:** DESIGNED

**Context**  
OHLC bars cannot reveal the exact path of price within a minute. Filling on a signal's own close/open can introduce look-ahead.

**Decision**  
The authoritative event order, market EXIT timing, fill-price table, flat-bar handling and risk/exit evaluation rules live in `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md` §§3–6. V1 has no OCO orders. This ADR records the architectural decision; it does not duplicate the execution table.

**Rejected alternatives**  
Same-bar close fills for close-based signals; using an open print to fill an order that could only be decided after observing that open; optimistic intrabar ordering as default.

**Consequences / trade-offs**  
The single execution contract is authoritative in ENGINE to prevent duplicated, drifting rules. OHLC cannot reveal intrabar path, so stop-first and other conservative assumptions remain explicit model limitations.

## ADR-010 — V1 instrument and position scope

**Status:** DESIGNED

**Context**  
Long and short options have different cash-flow, risk, margin and expiry/settlement semantics. Multi-leg strategies add legging risk and cannot be assumed to fill atomically from OHLC bars.

**Decision**  
The engine is position-side agnostic and represents long/short CE/PE and declared multi-leg groups. Implement in two gates:

- **G2a:** deterministic single-leg long CE/PE, including direction-switching strategies that exit the existing position before entering the opposite option side. This is the first realistic-account strategy slice.
- **G2b:** short positions and declared multi-leg groups (long straddle/strangle, short strangle and simple vertical spread as supported by verified contracts), group-level exits, legging/failure/unwind states, and margin/buying-power interface.

A long straddle smoke strategy may be represented in G2b; short strangle and any short-leg strategy are `THEORETICAL` until margin/buying-power, spread hedge benefit, margin changes, expiry/settlement and forced-exit assumptions are verified. A G2b implementation gate does not itself verify account feasibility. Short-option realistic-account use requires a versioned effective-dated margin model and verified settlement/fee assumptions.

Protective stop/target/trailing are engine-evaluated position/group attributes, not independent OCO orders. Group-level exits use combined group value; individual leg exits remain allowed. Partial fills are deferred from the first implementation slice; leg-1-filled/leg-2-failed must have an explicit unwind or unresolved-halt path.

Intraday is default. Overnight carry is explicit. Expiry settlement uses verified official rules/data; force-flat before expiry unless carry/settlement is explicitly enabled and tested. Contract unavailability or failed eligibility/liquidity/margin gates reject the order; never silently substitute another strike.

**Rejected alternatives**  
Long-only as a permanent architectural restriction; pretending short margin or multi-leg execution is trivial; silently swapping contracts; treating expiry-day options as ordinary post-close positions.

**Consequences / trade-offs**  
Research can represent more strategies before all account-realism evidence is available. Every result must make that evidence tier visible.

## ADR-011 — Risk, fees and account semantics

**Status:** DESIGNED

**Context**  
A realistic backtest needs trading costs and safety invariants, while research sometimes needs an unconstrained theoretical mode. Small accounts are sensitive to fixed per-order charges.

**Decision**  
Risk has strategy rules, optional versioned account policy and non-disableable simulation invariants. Run pre-trade risk after order intent and before execution, then post-fill checks. V1 defaults to realistic position-side-aware sizing. Provide clearly labelled `REALISTIC_ACCOUNT` and `THEORETICAL` modes. Fee/tax schedule is versioned by effective date and reports each cost separately. Max-trades counts entry fills. Daily-loss default is realized plus unrealized P&L evaluated at bar close; report the overshoot between threshold breach and flatten. An optional worst-case intrabar mode uses the adverse mark for the position side (bar low for a long option, bar high for a short option). The authoritative tick-quantization, exact-money accounting formulas, append-only ledger and account-isolation contracts are in `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md` §§4 and 8; this ADR does not duplicate those formulas.

**Rejected alternatives**  
One global account ledger shared by deployments; risk checks only after fills; hard-coding today's fees into all history; treating a theoretical backtest as account-feasible.

**VERIFY**  
Seed fee schedules from official effective-dated sources and cross-check sample transactions against the current Upstox calculator. Do not mark fee rates `VERIFIED` until the exact charge breakdown matches for representative dates/order types.

**Consequences / trade-offs**  
Exact money and append-only accounting cost implementation effort but are necessary for trustworthy P&L. Short-option premium proceeds cannot be treated as profit without mark-to-market liability and margin treatment.

## ADR-012 — Charting and custom indicator execution

**Status:** DESIGNED

**Context**  
The UI needs high-performance charts and overlays. Full TradingView Charting Library licensing may not fit a personal project.

**Decision**  
Primary candidate: TradingView Lightweight Charts v5 with a custom drawing/order-line layer. Fallback: KLineChart if custom drawing requirements are too expensive. Custom Pine-like indicators are AI-converted into trusted repository Python files; no runtime Pine interpreter in v1. Batch feature execution runs in a worker subprocess with timeout and memory cap. Live feature execution uses a per-bar time budget; on breach the feature becomes `UNAVAILABLE`, new entries are blocked, exits and risk monitoring continue, and an alert fires. Apply input validation, code review, mandatory truncation tests and process/resource isolation. Indicator code never receives broker credentials or database handles.

**Rejected alternatives**  
Assuming the full TradingView Charting Library is free to use; runtime Pine execution; letting strategy code call broker/database internals.

**VERIFY**  
Check the current licence and redistribution/attribution requirements for the exact chart library and version selected; record the licence text/version and comply before shipping.

**Consequences / trade-offs**  
Lightweight charting and reviewed Python indicators avoid uncertain licensing and runtime-code risk, but some TradingView-like features require custom implementation and explicit review.

## ADR-013 — Operations and release gates

**Status:** DESIGNED

**Context**  
Collectors can fail silently, raw feed data is irreplaceable, and eventual live orders require regulatory and broker-specific checks.

**Decision**  
Use structured logs, health endpoints, collector heartbeat/lag alerts, and offsite sync of raw/Parquet data **only after Upstox storage/offsite-backup terms are verified**. Proposed recovery targets (not measured claims): raw capture loss window <= 1 second of messages on process crash using batched fsync, <= 1 minute on host crash; collector auto-restart <= 5 minutes; monthly restore drill. For Postgres, select and document either hourly logical dumps with a tested restore (target RPO <= 1 hour) or WAL archiving with point-in-time restore. If neither is implemented and tested, explicitly restate the operational target as RPO <= 24 hours with replay-based rebuild; do not retain an unsupported <=1-hour claim. Add an external dead-man's-switch heartbeat, disk-space/growth alert and an `AlertPort` with a configured channel (Telegram or email). The daily Upstox token flow is a human morning login that stores the token in a secure local store; at 08:45 Asia/Kolkata, check token readiness; if no valid token is present, the collector enters `WAITING_FOR_TOKEN` and alerts. Add daily raw instruments-master capture (lot size, tick size, listing metadata), gzip+SHA-256 archival of every expired-API response exactly as downloaded, and a reserved REST budget that throttles/pauses backfill during market hours. The operational sequence and session-day runbook are specified in `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md` §10. API hardening: bind to loopback/private network, require a token on every command, check `Origin`, and do not use wildcard CORS. Use Alembic for Postgres migrations and explicit schema versions for Parquet. Secrets stay in environment/keychain/secure local store and never in repo, DB or logs. Real orders are not part of v1; keep a `BrokerPort` interface and `PaperBroker`. Real-order work requires a separate release gate checking current SEBI/NSE retail-algo rules, broker API terms/order policies, risk controls and operational readiness.

**Rejected alternatives**  
Enabling live orders by simply swapping the paper broker; treating raw feed files as disposable; exposing the API publicly without authentication/private network controls.

**Additional VERIFY items**
- Expired-instruments API retention window and whether history is rolling; if rolling, backfill is a data-preservation priority.
- Upstox terms permitting local retention and offsite backup of market data.
- Pin DuckDB/pyarrow versions and verify the Parquet profile: zstd compression, row-group size, sorted key order and statistics settings.
- Verify whether instrument-master records contain a reliable listing date; otherwise derive `first_observed_at` from the first candle and prohibit selection earlier than it.

**Consequences / trade-offs**  
Recovery guarantees depend on the chosen backup implementation and vendor terms. Until restore evidence exists, RPO remains a target rather than a verified capability.

## ADR-014 — Process model and worker responsibilities

**Status:** DESIGNED

**Context**  
The product needs independently restartable capture and live processes, while a single developer needs to keep deployment and maintenance burden proportionate.

**Decision**  
Use the modular-monolith process boundaries: `collector_snapshot`, `collector_ws`, checkpointed `backfill`, `api`, `worker_compute`, `worker_data`, `live_daemon`, and `web`. `worker_compute` may run N instances and claims independent jobs with Postgres row leases. `worker_data` has exactly one active instance under an exclusive renewable lease and must stop publishing if the lease expires. `collector_ws` is the only owner of Upstox WebSocket connections. `live_daemon` is independent of API/UI restarts and supervises one OS process per deployment. Live daemon lease ownership is authoritatively tracked by `deployments.lease_owner` and `heartbeat_at` in PostgreSQL (DATA §2.1); jobs queue rows are non-authoritative lifecycle references. Start with a lightweight Postgres job runner using `FOR UPDATE SKIP LOCKED` and leases; do not introduce a separate queue framework unless measurements justify it.

**Consequences and trade-offs**  
Process boundaries improve fault isolation but increase operational work. Keep only the boundaries that protect capture, canonical publication, and live deployments; don't split every Python package into a service.

## ADR-015 — Production host and research sync

**Status:** DESIGNED; owner choice PENDING

**Decision**  
Run `collector_snapshot` and `collector_ws` on a dedicated always-on Linux host, either a small cloud VM in an India region if Upstox storage/offsite terms permit it, or a dedicated Linux mini-PC with UPS and a second physical disk if cloud storage is not permitted. The owner choice is PENDING until M0-07 records the terms and M2-10 measures storage growth. WSL2 on personal Windows is development-only. Run production Linux services under systemd as the single supervisor; do not combine application Docker restart policies with systemd supervision. Keep the repository and development data inside the WSL Linux filesystem, never `/mnt/c`. Sync selected data to the research machine as a read-only, checksum-verified copy; research must never write back to canonical/raw collector paths. A cloud VM/offsite market-data copy or backup remains disabled until Upstox storage/retention terms are verified. Record data-volume measurements and disk headroom before sizing the host.

**Consequences and trade-offs**  
A cloud VM simplifies uptime but is itself offsite storage and may be restricted by vendor terms. A dedicated machine avoids that specific cloud-storage choice but still needs power/network monitoring and a second physical backup. The owner must choose; the documents do not pretend the choice has been made.

## ADR-016 — Single-writer ownership matrix

**Status:** DESIGNED

**Architectural Decision:** To eliminate data corruption, split-brain writes, and concurrency races across the filesystem and databases, QuantView enforces a strict single-writer process model. Each storage path, dataset directory, and database table has exactly one designated writer process. All other components read canonically published, immutable artifacts or query through authorized transactional interfaces.

The binding, authoritative Single-Writer Ownership Matrix defining processes, datasets, readers, and transport mechanisms is specified in `DOCS/QUANTVIEW_DATA_SPEC.md §11.5`.

---

## System Architecture Overview

This section establishes the binding component architecture, process boundaries, data flows, failure domains, and request lifecycles for QuantView. It describes the physical instantiation of the decisions recorded in ADR-001 through ADR-016 without introducing unapproved infrastructure.

### 1. Component and Process Model

QuantView is structured as a **modular monolith** running on a single dedicated host. Components communicate via clean in-process package interfaces, loopback REST APIs, and local storage engines (Parquet/DuckDB and PostgreSQL).

```text
+-----------------------------------------------------------------------------------+
|                                  USER INTERFACE                                   |
|               React + Vite + TypeScript Single-Page Application (SPA)             |
+-----------------------------------------------------------------------------------+
                                          |
                                          | HTTP / WebSocket (/api/v1/...)
                                          v
+-----------------------------------------------------------------------------------+
|                                FASTAPI API SERVICE                                |
|   - Request validation (Pydantic)         - RunConfig validation & launch        |
|   - Chart candle & transform streaming    - Operational state CRUD (Postgres)    |
|   - Job queueing & status reporting       - Manual paper trading endpoints       |
+-----------------------------------------------------------------------------------+
         |                                |                               |
         | IPC / DB Leases                | Read-only Queries             | DB Writes
         v                                v                               v
+--------------------+           +--------------------+          +------------------+
|   WORKER PROCESSES |           |  ANALYTICAL STORE  |          | OPERATIONAL DB   |
| worker_compute:    |           | DuckDB + Parquet   |          | PostgreSQL:      |
|  - Backtest engine |           | - Underlying 1m    |          | - accounts       |
|  - Feature runner  |           | - Option candles   |          | - risk_policies  |
|  - Parameter sweep |           | - Snapshot rows    |          | - deployments    |
| worker_data:       |           | - Contract master  |          | - jobs & leases  |
|  - Normalization   |           | - Trading calendar |          | - runs index     |
|  - Lake compaction |           | - Derived features |          | - paper orders   |
|  - Manifest pub    |           +--------------------+          | - ledger events  |
+--------------------+                     ^                     +------------------+
         ^                                 |                              ^
         | Write Staged Parquet            | Atomic Manifest Reads        | Ledger Events
+--------------------+                     |                              |
| COLLECTOR SERVICES |                     |                              |
| collector_snapshot |---------------------+                              |
| collector_ws (raw) |                                                    |
| backfill (REST)    |                                                    |
+--------------------+                                                    |
         |                                                                |
         | Local Ring Buffer (M7-01+)                                     |
         v                                                                |
+-------------------------------------------------------------------------+---------+
|                              LIVE DAEMON (live_daemon)                            |
|   - Subscribes to FrameBus (M7+)          - Evaluates pre-trade risk policy       |
|   - Replays calendar-minute grid          - Executes paper orders & fills         |
|   - Tracks open position groups           - Commits immutable ledger events       |
+-----------------------------------------------------------------------------------+
```

#### Package and Domain Boundaries (`packages/*`)
- `packages/domain`: Exact-money integer types (`paise`), timestamps, contract models, and entity identifiers.
- `packages/data`: Parquet reader/writer, DuckDB query abstractions, dataset manifest validation.
- `packages/features`: Point-in-time technical indicators, option-chain features, and chart transforms.
- `packages/strategies`: Strategy protocol interfaces (`Strategy(Protocol)`), parameter definitions, and signal generation.
- `packages/engine`: Exchange calendar-minute master loop, event ordering, contract selection, and fill models.
- `packages/risk`: Dedicated risk-policy evaluator (max loss, drawdown, exposure caps, stale data guards, kill switch).
- `packages/ledger`: Strictly append-only financial event ledger, position projections, and fee calculations.
- `packages/db`: PostgreSQL connection management, migration scripts, and transactional repositories.

*Dependency Invariant:* Strategies, features, and core engine code must **never** import broker SDKs directly or query raw collector files. All market data passes through canonical Parquet or the validated `FrameBus`.

### 2. End-to-End Data Flows

1. **Historical Backfill Flow:**
   `backfill` service queries Upstox REST endpoints under rate-limit budgets $\to$ writes uncompressed-hash-verified `.json.gz` responses to `data/raw/` $\to$ `worker_data` parses and normalizes rows $\to$ writes Parquet files to `staging/` $\to$ validates schema and row counts $\to$ atomically renames into `data/lake/` and publishes dataset manifest.
2. **REST Snapshot Ingestion Flow:**
   `collector_snapshot` fetches option-chain captures on a scheduled cadence $\to$ archives raw payloads in `data/raw/upstox_rest/` $\to$ records local arrival timestamp `received_at` $\to$ writes capture headers and strike rows into daily staging Parquet $\to$ atomically publishes `option_snapshot_captures` and `option_snapshot_rows`.
3. **Live WebSocket Streaming Flow:**
   `collector_ws` owns the sole Upstox WebSocket connection $\to$ writes incoming frames into `.partial` raw segment files $\to$ fsyncs in batches (loss window $\le 1\text{ s}$) $\to$ renames to finalized segments $\to$ **remains raw-capture-only until M7-01**. Starting at M7-01, decoded quote updates are published to local `FrameBus` for real-time paper execution and UI streaming.
4. **Backtest Execution Flow:**
   API or CLI receives `RunConfig` $\to$ validates against schema $\to$ enqueues job in PostgreSQL `jobs` table $\to$ `worker_compute` claims lease $\to$ pins dataset manifests (calendar, contracts, 1m candles, snapshots) $\to$ executes causal calendar-minute loop $\to$ writes run artifacts to `staging/runs/{run_id}/` $\to$ verifies financial ledger $\to$ atomically publishes to `data/runs/{run_id}/` $\to$ registers run in PostgreSQL `runs` $\to$ UI fetches results via `/api/v1/runs/{run_id}`.
5. **Live Paper Trading Flow:**
   `live_daemon` consumes feeds from `FrameBus` / snapshots $\to$ checks data freshness (`available_at <= decision_time`) $\to$ steps strategy on completed bars $\to$ evaluates risk rules via `RiskEvaluator` $\to$ simulates order fills against contract tick rules $\to$ writes immutable events to PostgreSQL `ledger_events` in integer paise.

### 3. Failure Domains and System Resilience

| Failure Scenario | Impacted Component | Surviving Components | Recovery and Containment Behavior |
|---|---|---|---|
| **Web UI / Browser Crash** | SPA state lost | API, workers, collectors, daemon | UI reloads from `/api/v1/runs` and `/api/v1/deployments`. No impact on data or active execution. |
| **FastAPI Service Crash** | In-flight REST requests fail | Collectors, daemon, running workers | Systemd restarts API service immediately. Active background jobs continue via PostgreSQL worker leases. |
| **Worker Process Crash** | Active backtest fails | API, collectors, other workers | PostgreSQL lease expires after heartbeat timeout (`lease_expires_at`). Job is marked `FAILED` or retried. Uncommitted files in `staging/` are purged; canonical lake is untouched. |
| **Snapshot Collector Failure** | Snapshot stream gaps | WebSocket collector, API, workers | Systemd restarts collector. Gaps are recorded as quality flags in `data_eligibility`. Stale data policies halt new strategy entries. |
| **WebSocket Collector Crash** | Live tick capture paused | Snapshot collector, API, workers | Batched fsync ensures at most 1 second of raw messages lost. On restart, recovery scans `.partial` files, recovers complete frames, and resumes. |
| **PostgreSQL Unavailability** | Transactional writes blocked | Raw file collectors keep writing | Collectors write to raw filesystem without database dependency. Engine halts new entries and fails closed. |

### 4. End-to-End Backtest Request Lifecycle

```text
[ User / CLI ]
      |
      | 1. Submit RunConfig (JSON/YAML)
      v
[ FastAPI API / CLI Parser ]
      |
      | 2. Pydantic validation (ranges, allowed modes, dates)
      | 3. Enqueue job row in Postgres `jobs` (status = 'QUEUED')
      v
[ PostgreSQL Job Queue ]
      |
      | 4. `worker_compute` claims job with unique `lease_token` (status = 'RUNNING')
      v
[ Backtest Worker (worker_compute) ]
      |
      | 5. Freeze Manifests: resolve active calendar, contract master, lake datasets
      | 6. Initialize Staging: create `staging/runs/{run_id}/`
      | 7. Causal Simulation Loop:
      |      For each calendar minute:
      |        - Process pending fills at open (with slippage & tick rounding)
      |        - Evaluate intrabar stops/targets (STOP_FIRST invariant)
      |        - Evaluate strategy decisions on closed bars (`available_at <= ts_close`)
      |        - Check pre-trade risk controls (capital, drawdowns, limits)
      |        - Queue eligible order intents for next bar open
      | 8. Ledger Reconciliation: recompute gross/net P&L, fees, integer-paise balance
      | 9. Compute Metrics: write `metrics.json` (DSR, Sharpe, Sortino, drawdowns)
      | 10. Atomic Publish: rename `staging/runs/{run_id}/` -> `data/runs/{run_id}/`
      | 11. Register Run: update Postgres `runs` record (status = 'SUCCEEDED')
      | 12. Release Lease: mark job 'SUCCEEDED'
      v
[ UI / Report Consumer ]
      |
      | 13. Query `GET /api/v1/runs/{run_id}` -> Render interactive charts & audit metrics
```

### 5. Architectural Non-Negotiables

1. **No External Cache / Redis:** No Redis/Valkey/external cache; state lives in PostgreSQL and Parquet files. An optional adapter is permitted only if the ADR-002 measured-latency (> 500 ms p95) or restart/resume criteria are met, via an ADR.
2. **No Microservices Complexity:** Monolithic codebase in the repository root inside the Linux/WSL2 filesystem (never /mnt/c per ADR-015); modular process boundaries managed via standard systemd services.
3. **No Unconditional Feature Cache:** Features are calculated causal-on-demand. A persistent feature cache is added only if benchmarked and justified under M5-02.
4. **No Real Broker Orders in v1:** All live trading paths in v1 are simulated paper trading (`MANUAL_PAPER`, `STRATEGY_PAPER`). Real order routes do not exist.
5. **Exact Integer Money:** All cash balances, premiums, fill prices, fees, and ledger entries are represented in integer paise (`1 INR = 100 paise`) or exact `Decimal`/`NUMERIC`. No floating-point math for ledger state.

---

## Binding UI tiers and owner inputs

### UI release tiers

| Tier | Required scope |
|---|---|
| UI-1 core | Dashboard; strategy browser; backtest terminal; candlestick chart; per-strike option chart with trade markers; indicator controls/settings; same-page results panel; accounts/risk/capital; results/audit. |
| UI-1b promoted sub-slice | Minimal OI overlay + read-only option-chain table; promoted into scope once M3-08 reports verified OI semantics (or owner chooses earlier). Uses §26 contracts. |
| UI-2 selective | Heikin Ashi view; basic horizontal line and rectangle drawings. |
| UI-3, scheduled v1.1 and still committed | Renko; saved multi-chart layouts; advanced drawings; interactive option-chain matrix; multi-tab OI visualizations. API/data contracts are specified in `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md`. If a baseline/candidate uses OI/PCR, promote the required OI UI slice before declaring that strategy fully inspectable. |

### Owner decisions

- Python project runtime is 3.11.9; Python 3.13 is installed but not the project runtime. OS/distro, Postgres image/version, Docker/Compose, Node/package manager are `PENDING_OWNER`; `uv` is a proposal, not approved.
- Production host remains `PENDING_OWNER` until M0-07 storage/offsite terms are documented. Cloud India region if allowed; otherwise Linux mini-PC + UPS + second disk. Size disk from M2-10.
- Telegram is primary alert channel, email backup; recipient/destination is `PENDING_OWNER`.
- Baseline smoke strategy: 5m EMA(9)/EMA(21) cross on NIFTY. Bullish → long ATM CE; bearish → long ATM PE. Exit on opposite cross, configured SL/TP or force-flat before 15:25 Asia/Kolkata. This is plumbing only, not tuned, and does not rely on unverified option volume/OI.
- No single starting capital. Sensitivity grid: ₹10k, ₹20k, ₹50k, ₹100k, ₹200k plus owner-added levels; record each trial, report unaffordable lots with stable reason codes, and separate small-account feasibility from edge.
- Indicator list approval, UI test approach, and hold-out dates after M3-09 are `PENDING_OWNER`.
- Chart library licence, Upstox retention/storage terms, source field semantics, fee rates, margin/settlement and data coverage are `VERIFY`, not owner choices.

### Intentional deviations from the original vision

- **Feature persistence/recompute skipping:** the vision proposed skipping already-computed features whenever settings change. QuantView intentionally does not promise universal precomputation or automatic reuse in v1. It computes on demand first and adds content-addressed caching only after a benchmark shows material benefit. If cache is enabled, exact input/code/parameter/state hashes and invalidation tests are mandatory. This avoids persisting every possible parameter combination without evidence that it improves the actual workload.
- **Snapshot merging:** individual 30-second captures are not merged into a synthetic continuous grid. Capture times, schema versions, missing intervals and field-presence masks are preserved; daily compaction is storage compaction only.
- **Visual transforms:** Heikin Ashi/Renko are derived display transforms and never replace tradable OHLC.
- **UI staging:** UI-1 prioritizes the per-strike chart, trade markers, same-page results and indicator settings. UI-1b (minimal OI overlay + read-only option-chain table) is promoted into scope once M3-08 reports verified OI semantics (or earlier by owner choice). Layouts, Renko, and advanced drawings remain scheduled for v1.1 (UI-3).
- **Run ledger storage:** The vision describes exporting run ledgers into database tables. QuantView stores backtest run ledgers as partitioned Parquet artifacts with a PostgreSQL index row (`runs`), keeping the transactional database lean while preserving exact-money replayability.
- **Live data semantics:** a WebSocket quote/update stream is not assumed to be a complete tick tape or a complete option chain; actual feed fields and semantics require recorded fixtures and VERIFY evidence.

### Authority of the final spec set

The final source of truth is these four files: `QUANTVIEW_MASTER_SPEC.md`, `QUANTVIEW_DATA_SPEC.md`, `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md`, and `AGENTS.md`. Legacy documents may be consulted only for provenance; they do not override the final contracts. The most specific behavioural rule lives in the Engine/UI/Research Contract; schema/source truth lives in the Data Contract.

## Cross-document rule ownership

Detailed, executable bar/order/fill semantics live only in `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md` §4 and its §6 fill-model references; this ADR records the decision and points there. Canonical table schemas and partitions live only in `QUANTVIEW_DATA_SPEC.md` §§2–4. Operational procedures live in ENGINE §10; fault-injection requirements live in §13. `AGENTS.md` maps each rule to task IDs rather than redefining its semantics. ADR-014 owns process boundaries/worker leases; ADR-015 owns production-host and sync policy; ADR-016 owns the writer-ownership matrix.

## Decision implementation status

No ADR becomes `IMPLEMENTED`, `TESTED` or `VERIFIED` solely because it is written here. Each status change must link to code, test output, data audit, or external source evidence in the project decision log.
