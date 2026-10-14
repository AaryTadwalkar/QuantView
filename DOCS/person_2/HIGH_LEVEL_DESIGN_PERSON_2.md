# QuantView — High-Level Design (HLD)

| Field | Value |
|---|---|
| Document | `docs/HIGH_LEVEL_DESIGN.md` |
| Companion | `docs/LOW_LEVEL_DESIGN.md` (LLD) — exact schemas, formulas, algorithms, tickets |
| Status | Baseline v1.2 (amends v1.1 and v1.0), supersedes `SYSTEM_ARCHITECTURE.md` and the architecture parts of `TECHNICAL_IMPLEMENTATION_SPEC.md`. **Nothing in this document is IMPLEMENTED, TESTED or VERIFIED yet** (see P12 and LLD App. C) |
| Evidence date | 2026-10-09 (repository + `data_status.md` audit; external facts researched 2026-10-10); v1.1 amendments 2026-10-10; v1.2 amendments 2026-10-11 (owner architecture review) |
| Audience | Project owner, coding agents, reviewers |
| Primary market | NSE index derivatives, starting with NIFTY 50 and NIFTY weekly options |
| Initial scope | Research, historical backtesting, live paper trading |
| Future scope | Controlled live execution through Upstox (gated, Phase 9) |

## Revision history
| Version | Change | Rationale |
|---|---|---|
| 1.0 | Initial baseline | — |
| 1.1 | **Layered risk model and account-size independence** (P13, ADR-018, LLD §8.6) | Owner wants any account size (₹20k … ₹20 lakh) and per-strategy risk. v1.0's ₹5 lakh profile with a 10% outlay cap would have rejected almost every ATM weekly on a ₹20k account. |
| 1.1 | **`duration_profile` INTRADAY / OVERNIGHT** with overnight Mode B and Mode C rules (ADR-019) | Owner trades BTST-style (enter near the close, exit next open). v1.0 hard-coded "no overnight positions" in six places. |
| 1.1 | **Futures are recorded as data only**; WebSocket recorder also pins held contracts and records depth (ADR-021, ADR-022) | Index volume is unusable; irreplaceable data; held contracts must never fall out of the live subscription. |
| 1.1 | **ML scope widened to roles** (general, strategy meta/gated, regime, pattern, overnight) with a label registry and a holdout lifecycle (ADR-023, ADR-015 accepted) | Owner wants to explore many models, including strategy-specific ones. |
| 1.1 | **Pine porting protocol** (ADR-024) and **`ml` moved above `simulation` in the layer stack** (ADR-025) | Pine ports are the owner's main strategy source; v1.0's layering forbade ML from calling the Mode B engine it needs. |
| 1.1 | Option snapshots collect nearest **and next** weekly expiry (LLD §4.9.3) | Overnight and roll-over strategies need the next expiry; costs ≈ 60 extra calls per 30 min. |
| 1.2 | **Durable event delivery** (P14, ADR-027, LLD §2.3): live market events are committed to an append-only journal before anyone acts on them; Postgres tables are the outbox for trading events; consumers checkpoint in the same transaction as their effects | v1.1 required an in-process bus/local socket *and* safe restart with replay; nothing made the two consistent |
| 1.2 | **Paper/live isolation** (P15, ADR-026, LLD §9.5, §10.5): separate databases and roles, no order-capable credential outside the Phase 9 live process, endpoint allow-list on every data client | v1.1 said "separate schemas"; schemas in one database can be crossed by one mis-scoped connection |
| 1.2 | **Option execution and risk quantification** (ADR-032, LLD §8.6.8): underlying stops are exit triggers, not loss caps; rule RK-22; exit priority; gap/spread/stale/missing-quote handling | v1.1 stated the outlay fallback but not exit priority or the "risk cannot be quantified" rejection |
| 1.2 | **Manual paper account**, account kinds and order origin (ADR-028, LLD §8.8.3) | Owner wants to take manual paper trades at any time with accounting fully separate from strategy paper accounts |
| 1.2 | **Deployment state machine**, persisted event history, optional per-deployment chart visualization with automatic indicators (ADR-029, ADR-035, P17; LLD §8.8.2, §8.8.5, §5.1.9, §13.9) | v1.1 had pause/resume/stop actions but no states, no stop semantics for open positions and only generic markers |
| 1.2 | **Live-only option-chain workspace** with field-level provenance (ADR-030, LLD §4.15, §13.6); historical snapshots move to a research route | v1.1 specified a snapshot picker; a 30 s REST snapshot is not a live chain |
| 1.2 | **Chart replay** (ADR-033, LLD §13.5) and **backend metric inspector** (ADR-031, P16, LLD §8.10.5, §13.10) | Replay was one clause; metrics had definitions but no click-to-explain contract |
| 1.2 | **Coverage matrix, observation states, eligibility** (ADR-036), **WS-quote fills and exit-resolution bounds** (ADR-034), **status vocabulary** (ADR-037) | Data-quality and fill-simulation gaps from the architecture review; claims must say DESIGNED / IMPLEMENTED / TESTED / VERIFIED |

**Authority rule.** HLD says *what the system is and why*. LLD says *exactly how to build it*. If they disagree, stop and record the conflict in the decision register (§16); do not choose silently.

**How an agent must use these two documents.** (v1.1 and v1.2 amendments are marked *[v1.1]* / *[v1.2]* in LLD headings.) Read HLD §1–§6 once. Before each ticket, read the LLD section named in the ticket. LLD contains defaults for every parameter; an agent must not invent numbers. If a value is missing from LLD, that is a documentation bug: stop, ask, and add it to LLD.

---

# 1. Purpose, scope and non-goals

## 1.1 Purpose
QuantView is a TradingView-inspired research and trading platform with a quantitative engine behind it. One platform must let the owner:

1. See validated historical and live NIFTY charts, indicators and option-chain data.
2. Author strategies (declarative spec first, Python second) and see their signals on the chart.
3. Run causally correct backtests that never see the future and never invent option prices.
4. Paper trade the same strategies against live data with a real order lifecycle, ledger, charges and risk gates.
5. Train and deploy ML signal models only after they beat simple baselines out of sample.
6. Eventually route approved orders to Upstox, behind separate safeguards.
7. Take **manual paper trades** at any time in an account that is independent of every strategy (v1.2).
8. **Inspect everything**: replay history without seeing the future, see exactly why each marker exists, toggle a deployed strategy's markers and indicators on the chart, and click any metric to see its formula, inputs and trades (v1.2).

## 1.2 Non-goals (v1)
- Reproducing every TradingView feature (drawing tools, social features) and executing Pine Script natively. Pine strategies and indicators are *ported* to specs or trusted Python under the protocol in LLD §6.9.
- Multi-leg option structures, option selling, margin-based strategies, and *trading* futures. NIFTY futures are **recorded as data only** (ADR-021).
- Any instrument other than NIFTY 50 index and NIFTY weekly/monthly options.
- Microservices, message brokers, Kubernetes, a time-series database (see §11 trigger table).
- LLMs in the market-data-to-order path.
- Guaranteeing profit. The platform's job is to avoid fooling the owner, not to promise returns.
- Guaranteeing full-chain real-time coverage (live breadth is bounded by the WebSocket subscription cap) or simulating queue position for resting orders (v1.2).

## 1.3 Success definition
The first proof is deliberately small and must pass before anything else is built:

> validated NIFTY 1m candles → chart in browser → one tested indicator → one deterministic strategy signal → leakage-safe directional backtest → visual report with assumptions.

Final success is the full chain: data → features → strategy → backtest → paper trade → ledger → report, with every number traceable to source records.

---

# 2. Non-negotiable principles (system invariants)

| ID | Invariant | Enforced by |
|---|---|---|
| P1 | **No look-ahead.** A decision at time `t` may use only records with `available_at <= t`. | As-of join API; truncate-and-recompute test (LLD §5.1.7); simulation clock |
| P2 | **No invented option prices.** Actual-options P&L uses only observed bid/ask from stored snapshots or recorded quotes. LTP is never an executable price (it feeds display, features and labelled marks only). Synthetic premiums never enter fills, ledger or the headline metric. | `ResultKind` type separation; fill-model whitelist per mode (LLD §8) |
| P3 | **Result kinds are never mixed.** `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_ESTIMATE`, `PAPER`, `LIVE` are distinct types with distinct fields. | Pydantic discriminated unions; DB check constraints |
| P4 | **One strategy contract, many environments.** Backtest, paper and live consume the same `Decision` objects through the same risk and order lifecycle. Only the clock, data feed and fill source differ. *[v1.2]* Manual orders enter the same order lifecycle as a `ManualOrderRequest` (origin `MANUAL`), never as a `Decision`. | `Engine` composition (LLD §8.1) |
| P5 | **Raw data is immutable.** Originals are never overwritten, repaired or deleted. Normalised and derived data is versioned and reproducible from raw. | Read-only raw directory; checksums; migration rules (LLD §4.1) |
| P6 | **Missing is not zero.** Absent values are null with a reason code. Missing snapshots are never interpolated or forward-filled for execution. | Canonical schemas with nullable fields; DQ rules (LLD §4.4) |
| P7 | **Explicit time semantics.** Every record carries separate `bar_start`, `bar_end`, `source_ts`, `ingested_at`, `available_at` as applicable. A bare `timestamp` is not allowed in canonical data. | Schema validators; lint test |
| P8 | **Fail safe.** Stale data, missing features, feed loss, unknown broker state or breached limits block new orders. | Risk engine + strategy health gate (LLD §8.6) |
| P9 | **Reproducible runs.** Every backtest persists data version, strategy hash, parameters, cost model, fill model, engine version and seed. | `RunManifest` (LLD §8.9) |
| P10 | **Money is exact.** Cash, fees, fills and ledger use integer paise. Floats are for indicators only. | `Paise` type; ruff rule; unit tests |
| P11 | **Boundaries are mechanical.** Module boundaries are enforced by import-linter in CI, not by convention. | LLD §1.3 |
| P12 | **Evidence before claims.** No gate is "passed" without a recorded artifact (report, test output, checksum). Every capability carries exactly one status: `DESIGNED` (spec text exists), `IMPLEMENTED` (code merged), `TESTED` (named tests pass, output attached) or `VERIFIED` (gate artifact reviewed by the owner). A document never upgrades a status. | Completion report (LLD §17.3), feature register (LLD App. C) |
| P13 | **Risk is layered; strategies tighten, owners loosen.** Hard safety rules are never overridable. Account ceilings are owner policy. A strategy may declare its own risk only at or below the ceilings. Relaxing ceilings is possible only in an explicitly labelled research run, or by the owner publishing a new versioned account profile. | Risk engine rule classes and `RESEARCH_RELAXED` labelling (LLD §8.6) |
| P14 | **Durable before visible.** An event is acted on only after it is committed to durable storage. Consumers are idempotent and resume from checkpoints; a sequence gap or a stale feed blocks new entries. | Journal, outbox and checkpoints (LLD §2.3); fault-injection suite (T-EVT) |
| P15 | **Accounts are isolated.** Every order, fill and ledger event carries `mode`, `account_kind` and `origin`, validated by database constraints. Paper processes hold no order-capable credential and cannot reach the live database. | Separate databases and roles; composite foreign keys; endpoint allow-list (LLD §9.5, §10.5) |
| P16 | **Every number is inspectable.** Each displayed metric, marker and indicator resolves to a backend-supplied definition, inputs and source records. The frontend never computes authoritative values. | Metric registry, chart-event and feature-explain contracts (LLD §8.10.5, §6.6, §5.1.9) |
| P17 | **Visualization never controls.** Showing, hiding or filtering markers, levels and indicators reads persisted history and cannot start, stop, pause or alter a deployment, order or account. | Read-only visualization endpoints and database role split (LLD §8.8.5) |

---

# 3. Context and constraints

## 3.1 Actors and external systems
```mermaid
flowchart LR
    OWNER["Owner (single user)"]
    AGENT["Coding agent(s)"]
    UPSTOX_REST["Upstox REST<br/>historical candles, option chain,<br/>option contracts, orders (future)"]
    UPSTOX_WS["Upstox WebSocket v3<br/>market data feed (protobuf)"]
    NSE["NSE circulars / holiday list<br/>(manual, curated into YAML)"]
    QV["QuantView"]
    OWNER --> QV
    AGENT --> QV
    UPSTOX_REST --> QV
    UPSTOX_WS --> QV
    NSE -. curated by owner .-> QV
    QV -. future, gated .-> UPSTOX_REST
```

## 3.2 Hard constraints (verified facts and owner decisions)

| # | Constraint | Consequence |
|---|---|---|
| C1 | Owner has **no Upstox Plus**. The expired-instrument historical candle API is unavailable. | Historical option prices exist only in the owner's own snapshots (from 2026-01-20). Actual-options backtests are limited to that window. Alternatives (licensed data) are a separate decision, not assumed. |
| C2 | Option-chain REST accepts one underlying and one expiry per call, and calling faster than about every 30 s triggers server errors (community-reported, to be re-verified in Phase 0). | 30 s is a provider-imposed snapshot floor; finer option data must come from the WebSocket feed. |
| C3 | Standard Upstox APIs: 50 req/s, 500/min, 2000/30 min. Order APIs for non-registered algos: 10 req/s. Source: Upstox rate-limit page. | Rate limiter is a mandatory component (LLD §4.9). |
| C4 | WebSocket v3: 2 connections per non-Plus user; modes `ltpc`, `full` (5-level depth + greeks), `option_greeks`; `full_d30` is Plus-only. | Quote recorder uses `full` for ≈ 45 instruments on one connection; limits re-verified in Phase 0 and stored in config. |
| C5 | NIFTY weekly expiry is Tuesday for contracts expiring on or after 2025-09-02; earlier Thursday. Lot size is 65 for expiries from 2026-01-06; 75 before (back to Nov 2024). | Expiry, lot size and strike step are effective-dated reference data (LLD §3). |
| C6 | Options STT on premium sold: 0.0625% → 0.10% (2024-10-01) → 0.15% (2026-04-01). Brokerage on Upstox options: flat ₹20 per executed order. | Cost model is effective-dated and verified against owner contract notes (LLD §8.5). |
| C7 | Owner develops on Windows (repo `C:\Algo\quantview`); collector currently started manually; `Data/` is git-ignored. | Collector automation, backups and path-agnostic code are Phase 0 work. Case-sensitivity and path rules in LLD §1.2. |
| C8 | Solo developer with coding agents. | Fewer moving parts: Parquet + DuckDB for market data, one Postgres for state, one repo, one deployable. |
| C9 | The owner trades by **buying** NIFTY CE/PE, intraday and overnight (BTST-style: buy near the close, sell the next morning). | v1 supports single-leg long options only, with `duration_profile` INTRADAY or OVERNIGHT (ADR-019). Short options and spreads are out of scope. |
| C10 | The WebSocket `full` subscription cap (≈ 45 instruments on one connection, verified in Phase 0) bounds how many strikes can update live. The REST option chain refreshes about every 30 s for every strike. | The live chain shows per-field source and age; strikes outside the subscribed band are labelled `SNAPSHOT ONLY` and are never presented as live (ADR-030, LLD §4.15). Full-chain real-time coverage is not promised. |

## 3.3 Current data reality (audit baseline)
Facts below come from `data_status.md` (2026-10-09) and the repository audit. Items marked ⚠ are unresolved and are Phase 0 tasks, not assumptions.

| Dataset | Evidence | Confidence |
|---|---|---|
| NIFTY 1m candles, 2022-01-03 → 2026-10-08, IST-aware timestamps, bar-open labelled (first 09:15, last 15:29) | Report + file samples | High on range; ⚠ row count: report 451,952 vs direct count 432,967 (432,967 ÷ 375 ≈ 1,154.6 sessions, consistent with 3m/5m/15m ≈ 1,156 sessions; the report's count is the outlier) |
| 3m, 5m, 15m (≈ 1,156 sessions), 1h and 4h (1,176 sessions each), 1d from 2021-02-01 (1,410 rows) | Row counts ÷ bars per session | ⚠ Session counts differ across timeframes by ≈ 20; cause unknown until the calendar-driven audit runs |
| 1m gaps: ≈ 15 days (Feb–Mar 2026) missing the 15:29 bar; 2026-02-12 missing 96 bars; 2026-02-16 missing 72; 2026-02-23 missing 57; 2026-02-21 is a Saturday with a single row | Report | Treat as *candidate* gaps until calendar-checked |
| Option-chain snapshots, 71,617 over 110 trading days from 2026-01-20; ≈ 651/day vs 750 expected at 30 s | Report | Counts depend on the audit parser; ⚠ three expiry folders (`2026-02-3`, `2026-03-2`, `2026-04-7`) are not zero-padded and appear to be missing from the report's expiry list |
| Three schemas: v1 (from 2026-01-20: ltp, oi, prev_oi, volume, bid, ask), v2 (from 2026-01-23: **no ltp**), v3 (from 2026-02-12: spot, bid/ask qty, chng, chng_oi, iv, delta, gamma, theta, vega) | Report | High |
| Option snapshot timestamps are timezone-naive | Repository audit | ⚠ Timezone resolved by the deterministic test in LLD §4.3 |
| Some Greeks recorded as 0 | Repository audit | Zero-sentinel rule in LLD §4.5 |
| Snapshot storage: one CSV file per snapshot under `Data/live/option_chain/nifty/<expiry>/<date>/snapshots/HH-MM-SS.csv` (≈ 71k files and growing) | Screenshots | High; compaction required |
| Only the nearest weekly expiry is collected | Folder structure | High; limits roll-over strategies |
| Collector start is manual; many sessions start late (09:30–10:50) and show gaps of 5–25 minutes | Report | Automation is Phase 0 |

**Consequence for research tracks** (carried into every result label):

| Track | Data window | Allowed claims |
|---|---|---|
| Underlying directional (Mode B) | 2022-01-03 → today (≈ 4.8 years) | Direction/point statistics on NIFTY. Never rupee option P&L. |
| Actual options (Mode C) | 2026-01-20 → today (~8.5 months), with Greeks only from 2026-02-12 | Option P&L with explicit coverage, using bid/ask snapshots. Statistical power is limited; reports must show effective sample size (days, trades). |
| Synthetic estimate (Mode S) | Any | Labelled scenario analysis only. Must be calibrated against Mode C on the overlap window and show the error (LLD §8.12). |

---

# 4. Operating modes

| Mode | Name | Data source | Fill source | Output kind | Orders leave the machine? |
|---|---|---|---|---|---|
| A | Research / charting | Historical + live | none | none | No |
| B | Underlying directional backtest | NIFTY candles | Simulated on spot (next bar) | `UNDERLYING_DIRECTIONAL` (points, % return) | No |
| C | Actual-options backtest | NIFTY candles + option snapshots/quotes | Simulated on observed bid/ask | `ACTUAL_OPTIONS` (₹, net of charges) | No |
| S | Synthetic option estimate | NIFTY candles + pricing model | Model price | `SYNTHETIC_ESTIMATE` (labelled) | No |
| D | Live paper trading | Live feed | Simulated on live quotes | `PAPER` | No (adapter has no broker import) |
| E | Live broker execution | Live feed | Broker-reported | `LIVE` | Yes — disabled by default, Phase 9 gate |

The mode, the account kind (`BACKTEST`, `PAPER_STRATEGY`, `PAPER_MANUAL`, `LIVE`) and the order origin (`STRATEGY` or `MANUAL`) are stored on every run, order, fill and ledger event and shown in the UI header. Paper and live use separate processes, credentials and **databases** (ADR-026). Manual and strategy paper trading use separate accounts, ledgers and P&L but the same order state machine, fill models and market-data services (§5.6).

**Duration (v1.1).** Every strategy declares `duration_profile ∈ {INTRADAY, OVERNIGHT}`. INTRADAY positions are flattened at `force_flat_time`. OVERNIGHT positions are carried across sessions. Mode B can evaluate overnight strategies over the full 2022→today candle history because it needs only index candles (entry near the close, exit at the next session's open bar). Mode C can evaluate overnight strategies only where the option snapshots cover the next morning's open; coverage is reported and unresolved exits are never invented (LLD §8.4.7).

---

# 5. System architecture

## 5.1 Logical view
```mermaid
flowchart TD
    subgraph SRC["External sources"]
        UREST["Upstox REST"]
        UWS["Upstox WebSocket v3"]
        FILES["Existing CSV files (legacy)"]
        CALCFG["Curated calendar / rule YAML"]
    end

    subgraph MD["market_data"]
        ING["Ingestion adapters"]
        RAWA["Raw archive (immutable)"]
        NORM["Parsers + normalisers"]
        DQ["Validation + quality reports"]
        CANON["Canonical store<br/>Parquet + DuckDB"]
        LIVEB["Live candle builder"]
        QREC["Option quote recorder"]
        RECON["Reconciliation"]
    end

    subgraph INS["instruments"]
        CAL["Exchange calendar"]
        EXP["Expiry / lot / strike rules"]
        MASTER["Contract master"]
    end

    subgraph RES["research"]
        FEAT["features"]
        STRAT["strategies"]
        SEL["contract_selection"]
        MLM["ml (offline train, online infer)"]
    end

    subgraph TR["trading core"]
        RISK["risk"]
        SIM["simulation<br/>backtest + paper runner"]
        EXEC["execution<br/>paper adapter / Upstox adapter (future)"]
        LEDG["ledger"]
    end

    subgraph APP["application"]
        API["api (REST + WebSocket)"]
        UI["frontend (Next.js)"]
        PG[("PostgreSQL<br/>state, runs, ledger")]
    end

    UREST --> ING
    UWS --> ING
    FILES --> ING
    ING --> RAWA --> NORM --> DQ --> CANON
    UWS --> LIVEB --> CANON
    UWS --> QREC --> CANON
    CANON --> RECON
    CALCFG --> CAL
    CAL --> DQ
    CAL --> EXP
    EXP --> SEL
    MASTER --> SEL
    CANON --> FEAT --> STRAT --> SEL --> RISK --> SIM
    SIM --> EXEC --> LEDG
    SIM --> LEDG
    CANON --> SIM
    FEAT <--> MLM
    LEDG --> PG
    SIM --> PG
    STRAT --> PG
    CANON --> API
    PG --> API
    SIM --> API
    API <--> UI
```

## 5.2 Runtime processes (one repository, several entry points)

| Process | Entry point | Runs when | Writes to | Notes |
|---|---|---|---|---|
| `collector-snapshots` | `python -m quantview.apps.collect_snapshots` | Scheduled 09:00 IST, trading days | `data/raw/option_chain_api`, canonical Parquet | Replaces the manual collector; heartbeat file; auto-restart |
| `collector-live` | `python -m quantview.apps.collect_live` | Scheduled 09:00 IST | Ticks, live candles, option quotes, near-month futures quotes and candles (Parquet) | One WebSocket connection; candle builder + quote recorder in one process |
| `eod-jobs` | `python -m quantview.apps.eod` | 16:30 IST | Historical candle fetch, reconciliation, compaction, backup | Idempotent; safe to rerun |
| `api` | `uvicorn quantview.api.main:app` | Always on | Postgres (state), reads Parquet | Also serves WebSocket to the UI |
| `paper-runner` | `python -m quantview.apps.paper_runner` | Always on during sessions (one process per paper database) | `qv_paper` (orders, ledger, deployments); reads the journal and `qv_core` | Hosts every strategy deployment and the manual-order consumer as separate, checkpointed tasks; never imports a broker SDK; holds no order-capable credential |
| `backtest-worker` | In-process task or `python -m quantview.apps.backtest` | On demand | Postgres (runs), Parquet (result artifacts) | CPU-bound; separate process to keep the API responsive |
| `frontend` | `next start` | Always on | — | Talks only to `api` |

Processes communicate through (a) files/Parquet partitions, (b) the **durable event journal** written by `collector-live` for market and health streams (LLD §2.3.1), and (c) Postgres tables, which are the outbox for trading events (`order_events`, `ledger_events`, `deployment_events`, `decisions`; LLD §9.5). No external broker in v1. The local socket carries only low-latency *notifications* of events that are already committed; a consumer that misses or doubts a notification reads the journal from its checkpoint. A single-process dev mode uses the same interfaces with an in-memory journal.

## 5.3 Dependency layers (enforced)
```
L7  api, apps                       (entry points and composition roots; may import anything below)
L6+ ml                              (datasets, labels, training, evaluation, predictor; may import simulation)  [v1.1]
L6  simulation                      (engine, paper runner, fill/cost models, metrics)
L5  execution                       (order interfaces; paper adapter; future upstox adapter)
L4  risk, ledger                    (independent; no import of each other)
L3  research (features, strategies, contract_selection)
L2  market_data
L1  instruments
L0  shared                          (ids, time, money, events, errors, config)
```
Rules: a package may import only from lower layers; `simulation`, `research` and `risk` never import `ml` — a trained model reaches the feature engine only through the `ExternalFeatureProvider` protocol (defined in `research.features`, implemented by `ml.predictor`, registered by `apps` at start-up) [v1.1, ADR-025]; `execution.upstox` may be imported only by `apps` and `api`; `research` and `simulation` must never import `upstox_client` or `execution.upstox`; `ledger` never imports `execution`; the frontend never contains trading or accounting logic.

## 5.4 Core data flows

### Historical path (research)
`CSV/API → raw archive → parser(version) → canonical rows + DQ flags → Parquet → DuckDB view → features (as-of) → strategy → simulation → report`

### Live path (paper)
`WebSocket tick → validate → journal commit (fsync) → candle builder → provisional (ephemeral) / final (journaled) candle events → incremental features → strategy runner → contract selection → risk → paper adapter (fill on live quote) → ledger → UI events`
After the session: `historical candle fetch → reconcile with live-built candles → revision records` (decisions already made are never rewritten).

### Backtest path
`RunConfig → DataProvider (as-of) → Clock → features → strategy → selection → risk → fill model → ledger → metrics → RunManifest + artifacts`

## 5.5 Result-kind separation (type-level)
```mermaid
flowchart LR
    S["Strategy Decision"] --> B["Mode B engine"] --> RB["UnderlyingDirectionalResult<br/>points, % return, horizon stats"]
    S --> C["Mode C engine"] --> RC["ActualOptionsResult<br/>₹ gross, charges, net, coverage"]
    S --> M["Mode S estimator"] --> RS["SyntheticEstimateResult<br/>scenario only"]
```
`RunSummary` is a discriminated union on `result_kind`. The API and UI never sum or compare headline metrics across kinds.


## 5.6 Account model and isolation [v1.2]
| Account kind | Mode | Created by | Orders originate from | Risk profile kind | Ledger |
|---|---|---|---|---|---|
| `BACKTEST` | B / C / S | each run | the engine | `ENFORCE` or `RESEARCH_RELAXED` | in memory, discarded with the run (artifacts are kept) |
| `PAPER_STRATEGY` | PAPER | owner, in Settings | strategy deployments (`STRATEGY`) | `ENFORCE` account profile; strategy `risk` clamped to its ceilings | `qv_paper`, own account id |
| `PAPER_MANUAL` | PAPER | owner, in Settings | the manual order ticket (`MANUAL`) | `HARD_ONLY`: safety rules only, no strategy risk, no strategy sizing | `qv_paper`, own account id |
| `LIVE` | LIVE | Phase 9 only | strategies and/or manual | live profile | `qv_live` |

**Shared** between manual and strategy paper trading: the order state machine, the paper adapter and fill models, the cost model, the risk engine's HARD rules and the market-data services. **Never shared**: account id, ledger events, positions, P&L, performance reports, risk profile. A manual order cannot be attached to a strategy account and a strategy order cannot be attached to a manual account (composite foreign key plus CHECK, LLD §9.5).

| Isolation layer | Mechanism |
|---|---|
| Database | `qv_core` (strategies, versions, runs, risk profiles, audit, visualization preferences), `qv_paper` (paper accounts, orders, fills, ledger, deployments), `qv_live` (created only in Phase 9). Each has its own roles; the paper role has no `CONNECT` on `qv_live` and only `SELECT` on `qv_core` |
| Process and credential | Only the Phase 9 live process ever receives an order-capable Upstox credential. The paper runner, API and collectors do not hold one (LLD §10.5) |
| Network and code | Every data client goes through `HttpGateway`, which allow-lists data endpoints and refuses order paths; import-linter forbids paper-side modules from importing `execution.upstox` |
| Configuration | `QV_ENV` must match the database name and the account mode; a mismatch aborts start-up |
| Test | T-ISO-1…8: a paper configuration cannot submit an order to Upstox, even with live credentials present in the environment |

## 5.7 Durable event delivery [v1.2]
```mermaid
flowchart LR
    WS["Upstox WebSocket"] --> V["validate"] --> J[("journal segment<br/>fsync = committed")]
    J --> CB["candle builder"] --> J
    J -->|"seq notification"| R["paper-runner"]
    J -->|"seq notification"| A["api"]
    R -->|"one transaction: effects + checkpoint"| PG[("qv_paper<br/>orders, fills, ledger,<br/>deployment events")]
    PG -->|"outbox tail by seq"| A
```
Rules: (1) an event is *committed* when its journal write is fsynced, and only committed events are published; (2) every event has a stream and a gap-free sequence number; (3) a consumer applies an event and advances its checkpoint in **one** Postgres transaction, and every effect carries an idempotency key derived from the event id, so replay cannot duplicate orders, fills or ledger entries; (4) after a restart a consumer replays from its checkpoint; (5) a sequence gap that cannot be filled from the journal marks the stream `DEGRADED` and blocks new entries (RK-17). Provisional candles are ephemeral: never journaled, never replayed, never used for decisions. A broker is not added; the trigger is in §11.

---

# 6. Module catalogue

Each module lists purpose, ownership, interface, and the LLD section that specifies it.

| Module | Layer | Purpose | Owns | Exposes (public contract) | LLD |
|---|---|---|---|---|---|
| `shared` | L0 | Cross-cutting primitives | IDs, time helpers, `Paise`, event envelope, **event journal**, **HTTP gateway (endpoint allow-list)**, errors, config loader, clock | `Clock`, `new_id()`, `to_utc()`, `Paise`, `EventEnvelope`, `JournalWriter`/`JournalReader`, `HttpGateway`, error classes | §2 |
| `instruments` | L1 | Identity and time-dependent exchange rules | Calendar, expiry rules, lot/tick/strike rules, contract master | `Calendar`, `ExpiryRules`, `ContractMaster` | §3 |
| `market_data` | L2 | Ingest, preserve, normalise, validate, serve, collect live | Raw archive, canonical Parquet, DQ reports, live builder, quote recorder, reconciliation | `MarketDataRepository`, `OptionChainRepository`, `QuoteRepository`, `DQReport` | §4 |
| `research.features` | L3 | Indicators and option-chain features | Feature registry, batch + incremental calculators | `FeatureRegistry`, `FeatureEngine` | §5 |
| `research.strategies` | L3 | Strategy spec, runner, Python interface | Spec schema, evaluator, versioning | `StrategySpec`, `Strategy` protocol, `StrategyRunner`, `Decision` | §6 |
| `research.contract_selection` | L3 | Intent → eligible contract | Policies, tie-breaks, rejection reasons | `ContractSelector.select()` | §7 |
| `ml` | L6+ | Datasets, label registry, training, evaluation, registry, inference | Model artifacts, evaluation reports, experiment and holdout ledgers | `ModelRegistry`, `Predictor`, `LabelRegistry` | §11 |
| `risk` | L4 | Approve or reject intents | Rule set, risk profiles, kill switch | `RiskEngine.evaluate()` | §8.6 |
| `ledger` | L4 | Auditable accounting | Journal, positions projection, P&L | `Ledger.post_*()`, `Ledger.rebuild()` | §9 |
| `execution` | L5 | Order interface and adapters | Order state machine types, paper adapter, (future) Upstox adapter | `ExecutionAdapter` protocol | §8.7, §10 |
| `simulation` | L6 | Backtest engines, paper runner, fill/cost models, metrics, **replay, deployments, manual orders, chart-event history, metric registry** | Run manifests, reports, deployment state | `BacktestEngine`, `PaperRunner`, `ReplayService`, `DeploymentManager`, `ManualOrderService`, `FillModel`, `CostModel`, `MetricRegistry` | §8 |
| `api` | L7 | REST + WebSocket gateway | Request/response models | OpenAPI schema | §12 |
| `frontend` | — | Visual workspaces | Components, chart adapter, replay, live chain, order ticket, deployment and visualization controls, metric inspector | — | §13 |

## 6.1 Module responsibilities in one line each
- **market_data** answers "what did we know, and when did we know it?"
- **instruments** answers "what could be traded, with what rules, at that time?"
- **features** answers "what can be measured from what was known?"
- **strategies** answers "what do we want to do?" (never "how")
- **contract_selection** answers "which exact option does that mean?"
- **risk** answers "are we allowed to?"
- **simulation/execution** answers "what would have happened, and what actually happened?"
- **ledger** answers "what do we own, what did it cost, what did we make?"
- **ml** answers "does a model add value beyond a simple rule?"

---

# 7. Data architecture

## 7.1 Layers
| Layer | Location | Mutability | Content |
|---|---|---|---|
| Raw | `data/raw/` (read-only after write; includes legacy `Data/` mirrored by checksum manifest) | Append-only | Original CSVs, API JSON (gz), WebSocket tick logs; `MANIFEST.sha256` per directory |
| Canonical | `data/canonical/` | Rebuildable from raw | Parquet with fixed schemas, partitioned; `revision` column for corrections |
| Derived | `data/derived/` | Rebuildable | Resampled candles, feature tables, labels, model datasets; each with a lineage JSON |
| Quality | `data/quality/` | Append-only reports | DQ reports, quarantine files, reconciliation results |
| State | PostgreSQL | Transactional | Strategies, versions, runs, orders, fills, ledger, audit |

## 7.2 Time glossary (used everywhere)
| Term | Meaning |
|---|---|
| `bar_start` | Start of the candle interval (UTC instant). Source CSVs label bars by this. |
| `bar_end` | `min(bar_start + timeframe, session_close)`; for partial last bars the true session close, not the nominal interval end. |
| `source_ts` | Timestamp provided by the source (exchange/provider), if any. |
| `ingested_at` | When our system stored the record. |
| `available_at` | Earliest instant at which a decision may use the record. Candles: `bar_end`. Option snapshots: `observed_at + snapshot_available_lag` (LLD §4.3). Live: actual finalisation time. |
| `decision_at` | The instant a strategy evaluates (≥ `available_at` of every input). |
| `session_date` | Exchange-local (IST) trading date. |
All instants are stored as UTC with microsecond precision and rendered in `Asia/Kolkata`.

## 7.3 Quality states
Every record gets `quality_flags[]` (empty = clean). A *dataset-level* status is derived per `(dataset, session_date)`: `CLEAN`, `DEGRADED` (known gaps within tolerance), `UNUSABLE`, `UNVERIFIED` (calendar not confirmed). Backtests declare the minimum status they accept; the default is `CLEAN` or `DEGRADED` with excluded intervals reported.

## 7.4 Missing-data policy (summary; rules in LLD §4.4)
| Situation | Treatment |
|---|---|
| Exchange holiday / non-session | No rows expected; not a gap |
| Provider omitted a bar | Flag `MISSING_BAR`; never fabricate |
| No trade in interval | Not applicable to index (always has ticks); flag if volume-bearing instrument |
| Collector outage | Flag `COLLECTOR_GAP`; strategies needing fresh data are ineligible |
| Option snapshot late/missing | Decision rejected if latest snapshot older than `max_snapshot_age_s` |
| Schema lacks field (e.g. v2 LTP) | Field null, `greeks_status`/`ltp_status` explain |

## 7.5 Backups
Nightly checksummed copy of `data/raw`, `data/canonical`, `data/quality` and a Postgres dump to a second physical location (external drive or cloud bucket), with a monthly restore drill that rebuilds canonical data from raw and compares checksums. The option-chain history is irreplaceable and is backed up first.

## 7.6 Storage budget for the live feed (v1.1)
The 10–30 M rows/year figure in §11 covers **30-second REST snapshots only**. The WebSocket recorder is a different order of magnitude: if each of ≈ 45 subscribed contracts updates about once per second during a 6.25-hour session, that is on the order of 1 M raw rows per day, or ≈ 250 M rows per year (an assumption to be replaced by a measurement). Phase 0 gate G0.8 therefore requires a measured `ws_budget.json` (rows/day, MB/day compressed, quote update rate per instrument). Policy: raw ticks are kept compressed and immutable; derived 1-second quote bars are kept permanently; a daily size over `ws_daily_budget_mb` raises an alert, not a silent drop. Retention beyond 12 months is decided from the measurement.


## 7.7 Observation states, coverage matrix and eligibility [v1.2]
Quality *flags* describe a record; an **observation state** explains why an expected observation exists or does not. Every expected observation (session × expiry × strike × source schema × timeframe or snapshot slot) is assigned exactly one state, derived from the calendar, collector heartbeats, the snapshot index and the schema, and never from the absence of a row alone:

| State | Meaning | Usable for fills/features? |
|---|---|---|
| `OBSERVED_OK` | Present and valid | Yes |
| `CLOSED_MARKET` | Calendar says no session or outside session hours | Not expected; not a gap |
| `COLLECTOR_DOWN` | Expected, but the collector heartbeat shows it was not running | No; counts against coverage |
| `MISSING_OBSERVATION` | Collector was up, provider returned nothing or the request failed (`FAILED` snapshot row) | No |
| `UNATTRIBUTED_GAP` | Expected but absent in legacy data recorded before collector heartbeat history existed; the cause cannot be known and is never relabelled as a collector failure or a provider omission | No; reported separately |
| `STALE_QUOTE` | Present but older than the limit for its use | Display only |
| `NOT_COLLECTED_BY_DESIGN` | The schema never carried the field (for example v2 has no LTP) | No; reported as such |
| `INVALID` | Failed a validity rule (crossed, zero-sentinel, out of range) | No; nulls with reason code |
| `UNVERIFIED_CALENDAR` | The calendar is not verified for that date | Findings carry `CALENDAR_UNVERIFIED` |

The **coverage matrix** (`data/quality/coverage_matrix/`, LLD §4.14) stores these states by session, expiry, strike, source schema and quote source (REST snapshot or WebSocket). It is versioned with the calendar version and is an input to every backtest. **Eligibility:** a run or deployment declares the minimum dataset status and per-day coverage it needs; if the data does not meet it, the run is refused with the failing cells, or the excluded intervals are listed and the result is labelled `INCOMPLETE`. A paper deployment is blocked from starting, and new entries are blocked while running, when the data it needs is `UNUSABLE` or stale (RK-17).

---

# 8. Backtesting architecture (overview)

One deterministic, event-driven `Engine` runs all simulated modes. Components are injected:

| Component | Mode B | Mode C | Paper |
|---|---|---|---|
| Clock | `HistoricalClock` | `HistoricalClock` | `WallClock` |
| DataFeed | candles by `available_at` | candles + snapshots by `available_at` | live events |
| FillModel | `SPOT_NEXT_OPEN` / `SPOT_NEXT_CLOSE` | `OPT_SNAPSHOT_BIDASK` or `OPT_WS_QUOTE_BIDASK` (per session, recorded in every fill) | `OPT_LIVE_BIDASK` |
| CostModel | none (points) with hurdle sensitivity | `UPSTOX_NSE_OPTIONS` (effective-dated) | same as Mode C |
| Ledger | none | yes | yes |

Event ordering is deterministic: `(available_at, stream_priority, sequence)`. Strategies are evaluated once per finalized bar after all events at that instant are applied. Stops and targets are resolved with conservative rules (LLD §8.3, §8.4). Full algorithm in LLD §8.

**Look-ahead defence in depth:** (1) as-of data API cannot return rows with `available_at > now`; (2) feature truncate-and-recompute tests; (3) a "poisoned future" test that replaces all future data with NaN and requires identical decisions; (4) fill models can only read data with `available_at ≥ order_submitted_at + latency`.

**Risk in simulation (v1.1).** Mode C and paper run the layered risk engine (§9, LLD §8.6) with an account profile whose equity is a parameter. For strategy research that should not be distorted by account size, runs use the `research_relaxed` profile with fixed 1 lot: ceilings are measured and reported but not enforced, and every such result carries `risk_mode = RESEARCH_RELAXED` and cannot be deployed to paper without an enforced re-run of the same strategy version or an explicit, audited acknowledgement (LLD §8.6.5).

**Fill provenance (v1.2, ADR-034).** Every Mode C and paper fill records its quote source (`SNAPSHOT_30S`, `WS_QUOTE`, `LIVE_QUOTE`), quote age, spread and visible depth. A snapshot fill never claims to know the price path between snapshots. WebSocket quote history exists only from the first recorded session and is never back-filled or reconstructed for earlier dates. Ambiguous and unresolved exits are classified, counted, bounded (best case and worst case) and shown in every report (LLD §8.4.8).

**Eligibility (v1.2, ADR-036).** A run starts only if the data it needs meets its declared minimum quality, coverage and calendar status; otherwise it is refused with the failing matrix cells (§7.7, LLD §4.14).

**Inspectability (v1.2, P16, ADR-031).** Every metric in a result carries a `metric_id`. The backend serves its formula, variable definitions, intermediate values and trade references; the frontend only renders them (LLD §8.10.5).

---

# 9. Risk, paper trading and live-readiness (overview)

- **Risk engine** is a pure function `(intent, account, market_health, profile) → Approved | Rejected(rule_ids)`; no strategy can bypass it. Rules fall in three classes: **HARD** (kill switch, stale or missing data, instrument/side allowed, idempotency, account-state certainty, cash) — never overridable; **CEILING** (lots, outlay, risk per trade, daily loss, drawdown, entries, spread, expiry-day) — owner policy that strategies may only tighten; **PERMISSION** (entry windows, overnight allowed). Rules, defaults and boundary tests are in LLD §8.6.
- **Who defines risk (v1.1, ADR-018).** The *account profile* (owner, versioned, any equity) defines ceilings and the default risk per trade. Each *strategy* declares its own `risk` block (sizing, max risk per trade, max lots, daily loss) which is clamped to the ceilings and flagged `RISK_CLAMPED` when it asks for more. An account is the unit of risk; one strategy per account is recommended for clean attribution.
- **Paper trading** uses the same order state machine as live; fills are labelled `SIMULATED` with the fill-model name; every restart replays unacknowledged events idempotently.
- **Live execution** is a separate adapter behind an explicit enable flag, separate credentials and a manual go/no-go; see Phase 9. Outcome-unknown submissions block resubmission until reconciled.

- **Option risk quantification (v1.2, ADR-032).** A long option's loss is bounded only by its outlay plus charges. An underlying-basis stop is an *exit trigger*, not a loss cap: it creates an exit order that fills at the next observable bid, which can be far from the level. Sizing therefore uses a premium stop with a stressed estimate or the full outlay; an order whose risk cannot be quantified is rejected (`RISK_UNQUANTIFIABLE`, RK-22); a one-lot fallback never overrides HARD, affordability or outlay rules. Exit priority when several triggers coincide: kill-switch/hard flatten, then forced exits (force-flat, expiry), then stops, targets, signal exits, time exits; one open exit order per position (LLD §8.2.1, §8.6.8).
- **Manual paper trading (v1.2, ADR-028).** A dedicated `PAPER_MANUAL` account has its own capital, orders, fills, positions, P&L, charges, ledger and reports. It runs under `HARD_ONLY` rules (instrument allowed, long options only, quote fresh and tradable, lot and freeze quantity, cash, expiry safety, idempotency, kill switch) and is never governed by a strategy risk profile or sizing. Manual and strategy orders share the order state machine, fill models and cost model but never accounting (§5.6, LLD §8.8.3).
- **Deployments (v1.2, ADR-029).** States: `CREATED, RUNNING, PAUSED_USER, PAUSED_AUTO, DRAINING, STOPPED, ERROR`. Stopping never deletes a position: the default `STOP_NEW_ENTRIES` keeps managing exits until flat (`DRAINING`), and `FLATTEN_NOW` is an explicit, audited action. One active deployment per strategy account. Start, stop and every state change are recorded with strategy version, parameters, account, feature and data versions (LLD §8.8.2).
- **Visualization (v1.2, ADR-029, P17).** Per-deployment markers, stop/target levels and indicators are drawn from persisted signal, order and fill rows, off by default and independently toggleable. Toggling is a read operation; it cannot alter a deployment. Indicators appear automatically, and only while the deployment's visualization is on, from the feature definitions the strategy actually uses, at the version it was deployed with; a version mismatch refuses to render rather than computing a different formula (ADR-035, LLD §5.1.9, §8.8.5).
- **Isolation (v1.2, ADR-026).** Paper and live do not share a database, role or credential; see §5.6 and LLD §10.5.
---

# 10. Frontend architecture (overview)

| Workspace | Purpose | Key data |
|---|---|---|
| Market `/chart` | Candles (historical and live), indicator overlays and panes, DQ ribbon, provisional vs final bars, missing bars as gaps, **chart replay**, optional per-deployment overlays (markers, levels, indicators; off by default) | `/candles`, `/features`, `/replay/*`, `/paper/deployments/{id}/chart-*` |
| Options `/options` | **Live-only** broker-style chain (CE and PE around the strike) with per-field source, age and validity, a market-closed state, and quick-trade into the manual ticket | `/live/option-chain`, WS `live_chain` |
| Research chain `/research/chain` | Historical snapshot picker and option features; never labelled live | `/option-chain/*` |
| Strategy | Spec editor (JSON form first), Python file reference, versions, validation, templates | `/strategies/*` |
| Backtest | Config, progress, summary, equity, drawdown, trades, coverage and eligibility, assumptions, sensitivity, bootstrap CI, **click-to-explain metric inspector**, run manifest | `/backtests/*` |
| Paper `/paper` | Strategy deployments with state controls; **manual account and order ticket**; orders, fills, positions, P&L and ledger per account | `/paper/*`, `/manual/*`, WS order/account/deployment events |
| Operations | Collector health, feed lag, journal and consumer lag, stream state, DQ status, kill switch, audit | `/health`, `/data-quality/*`, `/ops/*` |
| Settings | Risk profiles (create, version, compare), accounts by kind (equity, profile), strategy risk declarations, instrument subscriptions and pinned contracts | `/risk/profiles`, `/paper/accounts`, `/manual/accounts` |

Rules: the backend is the only source of decisions and numbers; charts, tables and inspectors render backend-provided series, markers, formulas and states and never compute authoritative trading values (P16); every marker carries `deployment_id` or `run_id` and `strategy_version`; paper/backtest/live views use different colour themes and a persistent banner; visualization controls read persisted history and never control execution (P17). Chart library: TradingView **Lightweight Charts** (open source; attribution notice required) behind a `ChartAdapter` interface (LLD §13.2). The commercial Advanced Charting Library and native Pine execution are out of scope unless licensed.

## 10.1 Required user workflows [v1.2] (detailed contracts in LLD §13.5–13.10)
1. **Replay** a historical start point: play, pause, step either way, change speed, see the exact replay time; no future bar, indicator value or label is ever sent to the browser; deterministic. Ordinary chart replay is not a strategy replay and never implies a paper deployment existed.
2. **Live option chain**: live during market hours only, with last-update time, quote age, feed status and Greeks validity on every row; market-closed state afterwards; historical snapshots live in the research route.
3. **Manual paper trade** at any time without any strategy: ticket, estimate, validation, submit, cancel, explicit exit; independent account.
4. **Deploy, pause, resume, stop** a strategy with defined semantics for open positions.
5. **Visualize** a deployment: markers (signal vs order vs fill), stop/target levels and automatically resolved indicators, per deployment, without side effects.
6. **Inspect** any entry or exit down to signal, order and fill timestamps, indicator values and the correct account's P&L.
7. **Explain** any backtest metric: exact formula, variables, intermediate values, period, treatment of open/unresolved/breakeven trades, and the trades behind it.

---

# 11. Technology baseline (fixed decisions)

| Concern | Decision | Rationale | Revisit trigger |
|---|---|---|---|
| Language | Python 3.12 (backend), TypeScript 5 (frontend) | Owner's stack | — |
| API | FastAPI + Pydantic v2 + Uvicorn | Typed contracts, OpenAPI | — |
| Market data store | Parquet (zstd) + DuckDB | Zero-ops, fast scans; fits ≈ 0.5M 1m rows and ≈ 10–30M option rows/yr | Query p95 > 2 s on 1y chain scan after tuning |
| State store | PostgreSQL 16 (Docker compose in dev) | ACID ledger, JSONB, constraints | — |
| Numerics | NumPy, pandas (indicator I/O), numba **not** used in v1 | Simplicity; parity tests keep correctness | Backtest of 1 run > 10 min |
| Config | YAML files validated by Pydantic; env vars for secrets | Versionable | — |
| Logging | `structlog` JSON, correlation IDs | Traceability | — |
| Scheduling | OS scheduler (Windows Task Scheduler / systemd timers) + in-process APScheduler | No new infra | Multi-host |
| Event delivery | Append-only journal files (market streams) + Postgres outbox tables (trading streams) + local socket for notifications; no broker | Restart-safe and replayable with no new infrastructure | Consumers on more than one host, or journal commit lag p99 > 250 ms after tuning |
| ML | scikit-learn, LightGBM (XGBoost optional; any other family only through the same evaluation protocol) | Tabular first; many roles, one governance protocol | Baselines beaten and data justifies deep models |
| Frontend | Next.js (App Router), React, TanStack Query, Zustand, Tailwind, Lightweight Charts | Standard stack | — |
| Tests | pytest, hypothesis, import-linter, Playwright (E2E) | Mechanical boundaries | — |
| Packaging | `uv` + `pyproject.toml`; `ruff`, `mypy --strict` on `shared`, `ledger`, `risk` | Fast, strict where money lives | — |

**Not adopted by default:** Redis, Kafka, Kubernetes, TimescaleDB, microservices, numba. Each has a written trigger above.

---

# 12. Security, reliability and observability

| Area | Requirement |
|---|---|
| Secrets | `.env` only, never committed; access tokens in a token file with 0600/ACL; Upstox access token expires daily — the token manager (LLD §4.9) refreshes by owner-approved login flow |
| Environments | `dev`, `paper`, `live` config profiles; live requires `QV_LIVE_ENABLED=1` **and** a signed-off checklist file |
| Isolation (v1.2) | Order-capable credentials exist only in the Phase 9 live process environment. Collectors and the API use the data token through `HttpGateway` (data-endpoint allow-list; order paths refused). Whether Upstox can issue a read-only data token is `[VERIFY]` in Phase 0 (G0.12); until proven, the gateway and import rules are the barrier. Paper and live databases have separate roles (LLD §10.5) |
| Strategy code | Trusted local modules only in v1; Python strategies loaded by explicit allow-list; arbitrary upload execution is out of scope until a sandbox design exists |
| Logging | JSON logs with `correlation_id`, `run_id`, `strategy_version`, `order_id`; no secrets |
| Metrics | Feed lag, candle finalisation lag, reconnect count, snapshot success ratio, DQ status, strategy eval latency, order latency, ledger invariant check result |
| Health | `/health/live`, `/health/ready`, collector heartbeat files; alerting by local notification (email/Telegram optional) |
| Recovery | Restart is safe: the journal tolerates torn tails (only uncommitted bytes are dropped), consumers resume from checkpoints committed in the same transaction as their effects, duplicate events are idempotent, a sequence gap blocks new entries, and the ledger rebuild equals the live projection (LLD §2.3, §9.9, §14.5) |
| Audit | Append-only `audit_events` for config changes, deployments, kill-switch use, risk overrides |

## 12.1 Failure-mode table
| Failure | Detection | Automatic response | Operator action |
|---|---|---|---|
| WebSocket disconnect | No ticks for `feed_stale_s` | Mark instruments stale; strategies pause; reconnect with backoff | None unless > 5 min |
| Snapshot REST error / 5xx | HTTP status | Retry within the tick window; record `FAILED` row | Review if > 5% of day |
| Late/duplicate tick | `source_ts` ≤ last or after bar grace | Drop from candle, keep in tick log, flag | None |
| Postgres down | Connection error | Runner halts new orders; keeps cancelling/closing logic read-only | Restore DB |
| Ledger invariant fails | Post-event check | Kill switch trips; trading halts | Investigate; rebuild from journal |
| Token expired | 401 | Stop order/data calls; alert | Re-login |
| Unknown broker order state | Timeout on submit | Mark `UNKNOWN`; block duplicate; reconcile | Manual review |
| Collector not started | Missing heartbeat by 09:20 | Alert | Start/diagnose |
| Journal torn tail after crash or power loss | CRC/newline check at writer start | Drop the uncommitted tail only; log `JOURNAL_TORN_TAIL_REPAIRED`; sequence continues | None |
| Journal corruption mid-file | CRC mismatch on read | Stream `DEGRADED`; new entries blocked; exits only on fresh quotes | Restore segment from backup and replay |
| Consumer sequence gap | `seq ≠ last + 1` | Read the journal; if the events are absent, stream `DEGRADED` | Investigate |
| Paper-runner crash | Heartbeat / PID | Restart, replay from checkpoint, no duplicate orders | Review `deployment_events` |
| Deployment enters `ERROR` | Exception or invariant failure | New entries blocked; open position stays managed, or is flagged `POSITION_UNMANAGED` with an alert | Resolve, then explicit resume |
| No executable quote for an exit | No valid bid by the deadline | Retry, alert, flag `EXIT_PENDING_NO_QUOTE`; a price is never fabricated | Manual review |

---

# 13. Quality strategy and gates

| Layer | Examples | Gate |
|---|---|---|
| Unit | Formula tests against hand-computed fixtures (LLD §5) | 100% of registered features have a fixture |
| Property | Candle invariants, ledger conservation, order state legality | hypothesis, ≥ 200 examples per property |
| Parity | Batch vs incremental features within 1e-9; vectorised vs event backtest on a sample | Zero failures |
| Look-ahead | Truncate-and-recompute; poisoned-future | Zero failures, run in CI |
| Replay | Record live day → replay through backtest engine → compare orders | Order intents identical; fills within model tolerance |
| Integration | Parquet round trip; Postgres migrations; API contract tests | CI |
| Data | DQ rule suite per canonical dataset | Reports committed as artifacts |
| End-to-end | Playwright: chart → run backtest → view report | Phase 5+ |
| Fault injection (v1.2) | Kill -9 and discarded-unsynced-bytes tests on the journal, consumer crash between effect and checkpoint, Postgres down mid-apply | Zero duplicate orders/fills/ledger entries; recovery within documented limits (LLD §2.3.4, §14.5) |
| Acceptance (v1.2) | The 15 owner acceptance tests `T-ACC-1…15` (LLD §15.1) | Each phase gate lists the T-ACC tests it owns; untested = `NOT RUN`, never `PASS` |
| UI contract (v1.2) | Playwright against a recorded API: replay leakage, ticket, visualization toggles, metric inspector | PR from Phase 3 for replay, Phase 5 for inspector, Phase 7 for the rest |

A phase gate is *passed* only if its checklist items each have a linked artifact (test log, report, checksum). The agent's completion report (LLD §17.3) must list each item as `PASS` / `FAIL` / `NOT RUN`.

---

# 14. Phased roadmap with go/no-go gates

Phases are ordered by dependency, not dates. A phase starts only when the previous gate is `PASS`.

| Phase | Name | Goal | Exit gate (all must pass) |
|---|---|---|---|
| 0 | Audit and collector hardening | Know what data is trustworthy; stop losing data | G0.1 Calendar YAML verified against NSE sources for 2021–2026 · G0.2 Audit v2 (calendar-driven) published; session counts equal across timeframes or exceptions listed · G0.3 All expiry folders parsed; missing-day report recomputed · G0.4 Timestamp semantics + option timezone resolved by the LLD §4.3 test · G0.5 1m → higher-timeframe resample matches fetched series ≥ 99.9% of bars · G0.6 Parquet conversion round-trips with checksums · G0.7 Scheduled collectors + heartbeat + nightly backup operating for 10 consecutive sessions with ≥ 95% snapshot coverage · G0.8 Quote recorder (WebSocket: index + ATM±10 options + near-month future + pinned held contracts, depth recorded) writing for ≥ 5 sessions, with a measured `ws_budget.json` (§7.6) · G0.9 Look-ahead test harness in CI · G0.10 Observation states and the coverage matrix published; calendar version recorded (LLD §4.14) · G0.11 Journal fault-injection suite green: torn tail, mid-file corruption, kill -9, duplicate delivery (LLD §2.3.4) · G0.12 Token-scope evidence and `HttpGateway` allow-list test: the data token cannot reach order endpoints through any QuantView client (LLD §4.9.5) |
| 1 | Skeleton and charts | Repo, CI, API, chart of validated candles | Repo layout per LLD §1; import-linter green; `/candles` serves 1m–1d; chart renders 450k-row history with lazy loading < 1 s per viewport; DQ ribbon shows flagged bars · missing bars render as gaps (never interpolated) and provisional vs final bars look different · databases `qv_core` and `qv_paper` and their roles exist and the T-ISO isolation tests pass (`qv_live` is not created until Phase 9) |
| 2 | Live data | Live candles, option quotes, reconciliation | Builder passes fixture tests; disconnect/reconnect test; EOD reconciliation report over 5 sessions within tolerance (LLD §4.11) |
| 3 | Feature engine | Tested catalogue | All catalogue features have fixtures; batch/incremental parity; truncate-and-recompute passes · every catalogue feature has display and explanation metadata (LLD §5.1.9) · chart replay passes T-ACC-1 and T-RPL-*: no future bar, indicator value or label reaches the browser, and replay is deterministic |
| 4 | Strategy engine | Spec + Python strategies, runner | Two reference strategies produce identical signals from spec and Python forms on the same data |
| 5 | Directional backtester (Mode B) | Leakage-safe spot research, INTRADAY and OVERNIGHT strategies | Determinism, poisoned-future, accounting-free invariants; sensitivity tables; report in UI · every Mode B metric opens the backend inspector (T-ACC-2) · report shows coverage, eligibility and unresolved/ambiguous exits |
| 6 | Actual-options backtester (Mode C) | Option P&L from snapshots | Contract selection tests; coverage report; fill + cost tests; Mode S vs Mode C calibration report · WS-quote fills and exit-resolution bounds tested · T-ACC-13 (result kinds never mixed; incomplete and synthetic results labelled) |
| 7 | Paper trading, ledger, accounts, deployments, live chain | Strategy and manual paper accounts, durable event handling, deployment controls, optional visualization, live-only option chain | **G7.1** durable consumers: T-EVT-4…12, T-ACC-11 · **G7.2** isolation: T-ISO-*, a paper configuration cannot submit to Upstox · **G7.3** ledger: rebuild equality, T-LG-11…18, T-ACC-15; 10 paper sessions without invariant violation; fee reconciliation vs owner's real contract notes within ₹1 per trade · **G7.4** manual account: T-ACC-3, T-ACC-4, T-MAN-* · **G7.5** deployments: T-DEP-* · **G7.6** visualization: T-ACC-5…10 · **G7.7** live chain: T-ACC-12, T-CHN-* · **G7.8** T-ACC-14 (data-quality failures block unsupported backtests and unsafe paper orders) |
| 8 | ML | Baselines, then models in several roles (general, strategy-specific, regime, pattern, overnight) | Walk-forward + purged evaluation; holdout untouched; promotion criteria (LLD §11.8) · experiment log complete, including failed runs and strategy edits (LLD §11.13) |
| 9 | Live broker (optional) | Controlled Upstox execution | Written readiness checklist signed by owner; tiny size; kill switch tested; regulatory check |
| 10 | Hardening | Performance, ops | Measured triggers only |

**Owner build order (v1.2) mapped onto phases.** (1) Resolve data and timestamp uncertainties → Phase 0. (2) Canonical data access, feature contracts, charting → Phases 1 and 3. (3) Chart replay and indicator rendering → Phase 3. (4) Strategy contracts, deterministic backtesting, interactive reports → Phases 4–6. (5) Paper accounts, order lifecycle, durable events, ledger → Phase 7 (G7.1–G7.3). (6) Manual paper account and ticket → Phase 7 (G7.4). (7) Deployment controls and optional visualization → Phase 7 (G7.5–G7.6). (8) Live option-chain presentation → Phase 7 (G7.7). (9) ML → Phase 8. (10) Live broker → Phase 9. **No UI ticket in a later step starts before the foundational data, execution and accounting gates of the earlier steps pass.**

**First end-to-end milestone (end of Phase 5):** pick a documented strategy, run Mode B over 2022-01 → 2026-10 with a walk-forward report, view equity/drawdown/trades on the chart, rerun and get an identical manifest hash.

---

# 15. Risks and open items

| ID | Risk / unknown | Impact | Mitigation / owner task |
|---|---|---|---|
| R1 | Only ~8.5 months of option snapshots | Weak statistical power; regime coverage limited | Report effective sample size; do not tune on the holdout; start quote recording now; evaluate licensed data separately |
| R2 | Snapshot cadence floor (~30 s) | Stops/targets cannot be resolved inside a snapshot | Path-blind rules (LLD §8.4); WebSocket recording for future data |
| R3 | Audit correctness (parser skipped folders; row-count conflict) | Wrong coverage claims | Phase 0 gates G0.2–G0.3 |
| R4 | Cost parameters change (STT, exchange charges) | Misstated net P&L | Effective-dated YAML + reconciliation with real contract notes (G7) |
| R5 | NSE exchange transaction rate for index options: sources show 0.03503% (Oct 2024) and 0.03553% (later) | ±0.00050% of premium turnover | Use the higher until verified in an NSE circular |
| R6 | Upstox feed field semantics (cumulative volume, index volume, timestamps) | Wrong volume/time features | Phase 0 fixture capture from a live session; document in LLD addendum table (§4.7) |
| R7 | Single developer + agents → inconsistent changes | Drift | Two-document authority, tickets, CI gates |
| R8 | Regulatory/broker rules for algorithmic orders | Live blocked | Verify current SEBI/Upstox/NSE requirements before Phase 9 (registration, static IP, order-rate caps, strategy identification) |
| R9 | Windows paths/case, laptop sleep | Gaps, bugs | Path utilities, power settings, always-on host recommended |
| R10 | Overfitting through many experiments | False confidence | Experiment registry counts trials; holdout lock; bootstrap CIs |
| R11 | Model-selection bias: many models, labels and features tried on the same history | A best-looking model is partly luck; false confidence | Trial counting per experiment family, holdout lifecycle with a cap on looks, forward shadow period (LLD §11.12) |
| R12 | Small accounts vs 65-unit lots | A single ATM lot can be 30–60% of a ₹20k account; percentage risk rules cannot be honoured | Account-size-independent research profile; explicit `RISK_BELOW_ONE_LOT` rejections surfaced in reports (LLD §8.6) |
| R13 | WebSocket volume is far larger than snapshot volume | Disk growth, slow scans | Measured budget in G0.8; derived 1-second bars; retention policy (§7.6) |
| R14 | Overnight holds add gap, theta and IV-change risk that index-only Mode B cannot price | Overstated BTST edge | Overnight hurdle report (LLD §8.12.3); Mode C evidence accumulates from now; labelled `OVERNIGHT` in every report |
| R15 | Journal growth and fsync latency on the owner's laptop | Disk fills; commit lag delays candles | Measured in G0.8 / G0.11; segment roll and compaction; `journal_commit_lag_ms` metric; alert thresholds (LLD §14.5) |
| R16 | The Upstox data token may also carry order permission | A bug or mis-set environment could reach order endpoints | `HttpGateway` allow-list, import-linter, no live process on the data host; read-only token if the provider offers one (G0.12, `[VERIFY]`) |
| R17 | WebSocket cap limits live chain breadth | Far strikes cannot be live | Per-field source and age on every cell; `SNAPSHOT ONLY` label; on-demand subscriptions for the ticket (LLD §4.15) |
| R18 | Chart replay mistaken for strategy history | Owner believes a deployment ran when it did not | Two named replay kinds (`CHART_REPLAY`, `EVENT_REPLAY`); event replay only for recorded deployments (LLD §13.5) |
| R19 | Formulas shown in the UI drift from the code | Wrong explanation of a metric or indicator | Explanations are generated from the same registry entries that compute the values; contract test recomputes each metric from its served inputs (LLD §8.10.5) |
| R20 | Resting-limit-order realism in paper | Optimistic limit fills | Conservative rule: fill only when the observed opposite side crosses, at the observed price; no queue-position claims; limit orders are `DESIGNED` and marked pending (LLD §8.7.3) |
| R21 | One paper-runner process hosts manual and strategy tasks | A crash stops both | Independent checkpointed tasks, restart tests (T-ACC-11); a second process per account is a later option |

---

# 16. Decision register

| ID | Status | Decision | Rationale | Affected |
|---|---|---|---|---|
| ADR-001 | Accepted | Modular monolith; one repo; entry-point processes | Solo dev; simple deploy | all |
| ADR-002 | Accepted | Raw immutable; canonical/derived rebuildable | Provenance | market_data |
| ADR-003 | Accepted | Result kinds are separate types | Prevent misleading claims | simulation, api, ui |
| ADR-004 | Accepted | No broker SDK imports outside `execution.upstox`, `apps`, `api` | Strategy independence | all |
| ADR-005 | Accepted | Point-in-time access uses `available_at`, backward as-of, explicit freshness limits | No look-ahead | features, simulation |
| ADR-006 | Accepted | Ten packages in layers L0–L7 (§5.3), `risk` separate from `simulation` | Risk is shared by paper and live | all |
| ADR-007 | Accepted (supersedes "exactly two docs" wording) | Two maintained specs: this HLD and the LLD | Clear split: why vs how | docs |
| ADR-008 | Accepted | `available_at = bar_end`, where `bar_end` is clipped to the real session close for partial bars | Reviewer correction | market_data |
| ADR-009 | Accepted | 1m is the canonical intraday series; higher timeframes are derived; provider-native timeframes are kept for reconciliation only | One source of truth | market_data |
| ADR-010 | Accepted | Parquet + DuckDB for market data; PostgreSQL for state; no Redis/Timescale/Kafka | Simplicity | storage |
| ADR-011 | Accepted | v1 trades single-leg **long** options only | Matches owner's trading; avoids margin modelling | selection, risk, ledger |
| ADR-012 | Accepted | Option fills in Mode C use observed bid/ask from the first snapshot at/after `decision_at + latency`; stops are path-blind (checked only at snapshots) | Honest about 30 s resolution | simulation |
| ADR-013 | Accepted | Strategy spec (JSON AST) and trusted Python modules first; visual builder UI later | Cost/value | strategies, ui |
| ADR-014 | Accepted | Record option quotes via WebSocket from now on | Irrecoverable data | market_data |
| ADR-015 | Accepted (v1.1) | Holdouts are chronological blocks frozen before tuning and governed by a lifecycle (`FROZEN → LOOKED_AT (≤ 3 looks per experiment family) → BURNED`); a burned holdout is replaced by a forward holdout made of sessions recorded after the burn date. Mode B default: 2026-01-01 → freeze date. Mode C: chosen after the coverage review (LLD §8.11, §11.12) | Selection bias; not "last 30 days" | simulation, ml |
| ADR-016 | Proposed | Synthetic-option acceptance thresholds are set per use-case before the calibration run, not a fixed 15% | Reviewer correction | simulation |
| ADR-017 | Accepted | ML starts after Phase 5 baselines; LightGBM + logistic baseline; promotion by bootstrap CI on frozen holdout | Avoid unvalidated models | ml |
| ADR-018 | Accepted (v1.1) | Layered risk: HARD rules, owner CEILING rules in a versioned account profile with any equity, strategy `risk` clamped to ceilings (`RISK_CLAMPED`), `RESEARCH_RELAXED` runs for strategies needing more risk (labelled, never promotable). Paper/live ceilings change only by a new profile version with an audit event | Strategies need their own risk; owners need control; nothing is bypassed silently | risk, simulation, strategies, api, ui |
| ADR-019 | Accepted (v1.1) | `duration_profile` INTRADAY / OVERNIGHT on every strategy; overnight entry window, exit by `exit_session_offset` + `time_exit`, carried positions in ledger and recorder, overnight hurdle. Mode B evaluates BTST on index candles; Mode C only where the open is covered | Owner trades BTST; index candles cover 4.8 years | strategies, simulation, ledger, risk, market_data |
| ADR-020 | Accepted (v1.1) | Strategy research uses a capital-agnostic profile (`research_relaxed`, 1 lot, results per lot) before any account-sized paper run | Account size must not decide which strategies look good | simulation |
| ADR-021 | Accepted (v1.1) | NIFTY near-month futures are recorded as data only (WebSocket `full` + EOD 1m candles). No futures trading. Futures features are optional and built only on owner request | Index has no volume; recording is cheap and irrecoverable | market_data, features |
| ADR-022 | Accepted (v1.1) | WebSocket recorder pins every contract with an open position in `full` mode regardless of the strike band, and records 5-level depth | A held contract must never go unmonitored; order-flow research needs depth history | market_data, simulation |
| ADR-023 | Accepted (v1.1) | ML roles: GENERAL, STRATEGY_META, STRATEGY_GATED, REGIME, PATTERN, OVERNIGHT; labels live in a registry; strategy-specific models are bound to a strategy `spec_hash` | Owner wants strategy-specific and general models | ml |
| ADR-024 | Accepted (v1.1) | Pine Script is never executed; it is ported under the LLD §6.9 protocol with TradingView-export parity tests and look-ahead/repaint review | Pine ports are the main strategy source and the main look-ahead risk | strategies, features |
| ADR-025 | Accepted (v1.1) | `ml` sits above `simulation` in the layer stack; trained models reach features only through `ExternalFeatureProvider` registered in `apps` | ML evaluation and strategy-outcome labels need the Mode B engine; v1.0's layering forbade that | all |
| ADR-026 | Proposed (v1.2) | Paper and live use **separate databases** (`qv_paper`, `qv_live`) with separate roles; shared reference data in `qv_core` is read-only to paper; order-capable credentials exist only in the Phase 9 live process; data clients go through an endpoint allow-list gateway. Replaces "separate schemas" | A schema boundary inside one database is crossed by one mis-scoped connection | storage, execution, apps, api |
| ADR-027 | Proposed (v1.2) | Durable events: journal files for live market streams (committed = fsynced; consumers see only committed events; the journal segments are the raw WebSocket log), Postgres tables as outbox for trading streams, consumer checkpoints in the same transaction as effects, idempotency keys derived from event ids, sequence-gap detection; provisional candles are ephemeral. No broker | Satisfies "safe restart and replay" without adding infrastructure | shared, market_data, simulation, api |
| ADR-028 | Proposed (v1.2) | Account kinds `PAPER_STRATEGY` and `PAPER_MANUAL`, order origin `MANUAL` / `STRATEGY`, enforced by composite foreign keys; manual accounts run `HARD_ONLY` rules; one execution path for both | Independent accounting without a second engine | ledger, risk, simulation, api, ui |
| ADR-029 | Proposed (v1.2) | Deployment state machine (`CREATED, RUNNING, PAUSED_USER, PAUSED_AUTO, DRAINING, STOPPED, ERROR`); stop never discards a position (default `STOP_NEW_ENTRIES`, explicit `FLATTEN_NOW`); one active deployment per strategy account; chart markers come only from persisted signal/order/fill rows; visualization is read-only | Turning a strategy off must not hide or erase risk | simulation, api, ui |
| ADR-030 | Proposed (v1.2) | `/options` is live-only with per-field source, age and state; strikes outside the WebSocket band are `SNAPSHOT ONLY`; historical snapshots move to `/research/chain`; no full-chain real-time promise | UI freshness must equal the real data source | market_data, api, ui |
| ADR-031 | Proposed (v1.2) | Backend metric registry: every metric has a `metric_id`, definition, variables, inputs and trade references served by the API; the frontend never computes authoritative metrics; metric ids are namespaced by result kind | Inspectability without mixing result kinds | simulation, api, ui |
| ADR-032 | Proposed (v1.2) | Underlying stops are exit triggers, not loss caps; risk is a premium-stop stressed estimate or the full outlay; RK-22 rejects unquantifiable risk; one-lot fallback never overrides HARD/outlay rules; exit priority order | Never imply a premium-loss guarantee | risk, simulation |
| ADR-033 | Proposed (v1.2) | Replay is server-authoritative: the browser receives only data with `available_at ≤ replay cursor`; `CHART_REPLAY` vs `EVENT_REPLAY` are distinct; deterministic for the same data version and config | Replay must not leak the future | simulation, api, ui |
| ADR-034 | Proposed (v1.2) | Mode C adds fill source `OPT_WS_QUOTE_BIDASK` for sessions with recorded quotes; fills record provenance; ambiguous/unresolved exits get best/worst-case bounds; LTP is never executable; quote history is never back-filled | Honest resolution limits | simulation, market_data |
| ADR-035 | Proposed (v1.2) | Feature definitions carry display metadata, explanation and repaint flag; a deployment pins feature versions; the chart renders a deployed strategy's indicators only at the pinned version (mismatch refuses to render) | The chart must not silently compute another formula | features, api, ui |
| ADR-036 | Proposed (v1.2) | Observation states, versioned coverage matrix and run/deployment eligibility gate | Data-quality claims must be checkable per cell | market_data, simulation |
| ADR-037 | Proposed (v1.2) | Capability status vocabulary `DESIGNED / IMPLEMENTED / TESTED / VERIFIED` with a living register (LLD App. C) | A design is not an implementation | all |

Rule: a decision may change only by adding a new ADR that supersedes it, with consequences and migration notes.

---

# 17. Glossary
| Term | Meaning |
|---|---|
| ATM | At-the-money: strike nearest to the spot at decision time |
| DTE | Days (or fraction) to expiry |
| IPFT | NSE Investor Protection Fund Trust charge |
| OI | Open interest |
| STT | Securities Transaction Tax |
| MIS | Intraday product type (positions squared off by the broker at day end) |
| As-of join | Join each row to the latest right-side row with `available_at ≤` left `decision_at` |
| Mode B/C/S | Underlying directional / actual-options / synthetic backtest |
| Hurdle | Underlying move needed to cover costs and option decay (LLD §8.12) |
| Duration profile | `INTRADAY` (flat by `force_flat_time`) or `OVERNIGHT` (may be carried across sessions) |
| BTST | Buy today, sell tomorrow: an OVERNIGHT strategy that enters near the close and exits at the next open |
| Pinned key | A WebSocket instrument kept subscribed because a position in it is open |
| Gate | A pass/fail checklist with linked evidence |
| Account kind | `BACKTEST`, `PAPER_STRATEGY`, `PAPER_MANUAL` or `LIVE`; decides the risk profile kind and which order origins are legal |
| Origin | `STRATEGY` (from a `Decision`) or `MANUAL` (from the order ticket) |
| Journal | Append-only, fsynced event log; an event is *committed* when its write is durable |
| Outbox | Postgres tables (`order_events`, `ledger_events`, `deployment_events`, `decisions`) that downstream readers tail by sequence number |
| Observation state | Why an expected observation is or is not present (`OBSERVED_OK`, `COLLECTOR_DOWN`, `CLOSED_MARKET`, …) |
| Coverage matrix | Observation states by session, expiry, strike, schema and quote source |
| Chart replay / Event replay | Reveal history bar by bar from a start time / replay recorded strategy and order events of a deployment that actually ran |
| Provisional candle | A bar still forming; display only, never journaled or used for decisions |
| DESIGNED / IMPLEMENTED / TESTED / VERIFIED | Capability status words (P12) |
