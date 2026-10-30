# Stage 7 Implementation Plan: Real-Time Paper Trading, Live Daemon & FrameBus Bridge

> **Document Status:** Authoritative Architectural Design & Implementation Plan  
> **Milestone / Gate Target:** **Milestones M7-01 through M7-09** $\to$ **Release Gate `G5` (Paper Runtime)**  
> **Parent Authority:** Canonical Documents:
> - `DOCS/QUANTVIEW_MASTER_SPEC.md` §2.5 (Paper Trading & Daemon Architecture), §4 (Release Gates)
> - `DOCS/QUANTVIEW_DATA_SPEC.md` §2, §4.5 (WebSocket Feed, Protobuf, Ingestion Buffers), §11 (Source Semantics)
> - `DOCS/QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md` §20–§24 (Paper Broker, Live Daemon, State Recovery, Risk Catalogue)
> - `DOCS/AGENTS.md` §6.9 (`M7-01` through `M7-09`), §7 (Gate G5 Acceptance Contracts)  
> **Selected Approach:** **Approach 1 — Dual-Process Architecture with Local FrameBus Transport & 24/7 Tick Player**  
> **External Upstream Reference:** `C:\Algo\quant-terminal` (Strictly Read-Only Reference)  
> **Scope Boundary:** Stage 7 Live Paper Trading, Daemon Supervisor, Streaming Aggregation, Risk Enforcement, and Replay Simulation. Stage 9 (Live Upstox Broker Execution & Real Money) remains strictly locked (`NO-GO`) until Gate G5 certification.

---

## 1. Executive Summary & Intent

### 1.1 Intent
Stage 6 successfully delivered the interactive desktop trading workstation (`apps/web/`) and the single-process API gateway (`services/api/`) under Gate G4. However, live tick streaming, real-time strategy order execution, and continuous paper portfolio tracking currently lack the operational backend engine that powers them during exchange hours.

Stage 7 establishes QuantView's **real-time execution backbone**:
1. **Background Live Daemon (`services/live_daemon`):** A resilient supervisor running across market sessions (09:15 to 15:30 IST) that hosts active strategy deployments without interruption when the web browser or UI server restarts.
2. **Local FrameBus Transport (`M7-01`):** A zero-latency ring buffer with monotonic sequence numbers connecting the raw Upstox feed (`collector_ws`) to downstream consumers.
3. **Streaming Candle Builder (`M7-02`):** Continuous aggregation of raw ticks into provisional and finalized 1-minute and multi-timeframe candles with strict causal availability (`finalized_at = bar_end + grace_period`).
4. **Institutional Paper Broker & Risk Guard (`M7-03`):** Quote-based fill engine checking pre-trade risk policy boundaries (`RK-01` to `RK-26`) and recording financial transactions in integer-paise (`packages/ledger/`) under PostgreSQL (`qv_paper`).
5. **24/7 Recorded-Session Tick Player (`M7-01` & `M7-05`):** A built-in high-fidelity market tick player enabling complete off-market and weekend testing of real-time charts, flashing option chain rows, and automated paper trading at 1x, 2x, or 5x playback speed.

---

## 2. Evaluation of Architectural Approaches

Three distinct structural paradigms were evaluated for the Stage 7 live daemon:

| Evaluation Dimension | Approach 1: Dual-Process Hybrid (Selected) | Approach 2: Monolithic Gateway Worker (Rejected) | Approach 3: Subprocess Process Mesh (Rejected) |
| :--- | :--- | :--- | :--- |
| **Process Model** | 2 processes: FastAPI Gateway (Port 8000) + Live Daemon (`services/live_daemon`) | 1 process: Live Daemon embedded as `asyncio` task in Gateway | $2 + N$ processes: Gateway + Daemon + 1 OS process per strategy |
| **Spec Compliance** | **100% Compliant** with `ENGINE §20` and `MASTER §2.5` | **Fails `M7-07` Invariant:** Web restart halts trading | **100% Compliant**, but high IPC friction on Windows |
| **UI Crash Isolation** | Total: Gateway or UI crashes never interrupt active deployments | None: Any API reload or crash destroys live strategy state | Total: Strategy crash cannot touch other strategies |
| **Tick Latency** | $< 0.5\text{ ms}$ over localhost loopback / IPC socket | $< 0.1\text{ ms}$ in-memory async queue | $1.5 - 3.5\text{ ms}$ multi-process serialization |
| **Operational Ease** | High: Single supervisor script (`run_workstation.ps1`) manages both | Highest: Single command runs everything | Lowest: Complex process PID management on Windows 11 |

### 2.2 Concrete IPC & Process Plane Architecture (Builder Resolutions)

To eliminate all architectural ambiguity between the Gateway and the Live Daemon, the communication boundaries are formally specified:
1. **Command Plane (Gateway $\to$ Daemon):**
   - The Live Daemon runs an internal administrative loopback HTTP server on `http://127.0.0.1:8001` (restricted strictly to localhost).
   - When the user triggers an emergency kill-switch (`POST /api/v1/daemon/kill-switch`), starts/stops a strategy (`POST /api/v1/daemon/start`), or modifies SL/TP brackets via chart drag (`PATCH /api/v1/paper/positions/{id}/brackets`), the Gateway (`services/api`) routes the request asynchronously via `httpx` to `http://127.0.0.1:8001/control/*`.
   - Result: Guaranteed sub-millisecond command acknowledgment with zero database polling latency.
2. **Data Plane (Daemon $\to$ Gateway $\to$ UI):**
   - The Live Daemon's `FrameBus` publishes decoded quote ticks and finalized 1-minute candle events.
   - The Gateway subscribes via local loopback socket / memory queue, broadcasting frames directly to connected browser clients via WebSocket `/ws/market` at 60 FPS.
3. **Collector WS Boundary:**
   - In live market operations, `collector_ws` runs as its own capture worker, publishing frames to `FrameBus`.
   - In simulated/replay mode, the **24/7 Tick Player** publishes recorded ticks directly to `FrameBus`, allowing full workstation testing without an active Upstox WebSocket session.
4. **Deterministic Replay & Backtest Parity (M7-05):**
   - For M7-05 validation, the paper broker executes in deterministic bar-open mode (matching `packages/engine/execution.py` next-bar open + 5 paise) when replaying recorded sessions, guaranteeing $\le 1\text{ paise}$ ledger delta against static backtests. In live streaming mode, it executes against live Bid/Ask quotes.
5. **Tick Player Data Source:**
   - The 24/7 Tick Player streams authentic tick records from raw segment files (`data/raw/upstox_ws/ticks/`) when available, and micro-tick OHLC sequences (`open -> low -> high -> close`) from DuckDB lake Parquet when replaying historical sessions.
6. **Strategy State Recovery & Indicator Warm-Up (M7-04 / M7-09):**
   - During checkpoint recovery, the strategy host feeds historical warm-up bars to the strategy in signal-suppressed mode (`is_warming_up=True`). This repopulates internal indicator windows (EMA, RSI) without dispatching duplicate orders. Once warm-up matches `last_seq_id`, the strategy transitions to `RUNNING`.
8. **Strategy Execution & Process Isolation Model (Owner Decision):**
   - Active strategy deployments run as **concurrent worker threads inside the single Live Daemon process**, managed by an isolated `ThreadPoolExecutor`.
   - **Thread Timeout Guard:** Every strategy's `on_bar()` and `on_tick()` execution is bounded by a strict 500ms timeout guard. If a user strategy freezes, deadlocks, or hangs, the daemon catches the timeout, isolates that single offending strategy deployment into `HALTED_TIMEOUT` status, alerts the UI, and continues running all peer strategies with zero interruption.
   - **Sub-Second Daemon Restart:** If the Live Daemon is ever stopped or restarted manually, cold startup takes under **300 milliseconds**.
   - **Zero-Loss Gap Sync Catch-Up:** If the daemon is restarted mid-session (e.g. down from 10:15 to 10:17), the recovery engine immediately pulls the missing 1-minute bars (`10:15`, `10:16`) from the DuckDB analytical lake / Upstox REST feed in under 50ms, feeds them into the strategy in signal-suppressed mode (`is_warming_up=True`) to re-sync indicator states (e.g. 20 EMA), and transitions seamlessly back to `RUNNING`. Zero candle data or indicator precision is ever lost.

---

## 3. Goals, Non-Goals & Anti-Goals

### 3.1 Goals
1. **Durable Local FrameBus Transport (`M7-01`):** Monotonic sequence-numbered ring buffer dispatching ticks from raw feed to consumers; benchmarked at $\le 0.5\text{ ms}$ p95 dispatch latency.
2. **Streaming Candle Aggregation (`M7-02`):** Resilient bar builder assembling 1m, 3m, 5m, 15m, 30m, 1h candles with strict boundary quarantine (`09:15:00` open, `15:30:00` close).
3. **Multi-Account Allocation Modes (`ADR-038`):** Support both `ISOLATED` (single strategy deployment per account) and `PORTFOLIO` (multiple strategies sharing account margin ceilings).
4. **Pre-Trade Risk Engine (`RK-01` through `RK-26`):** Hardware-enforced kill switch (`RK-01`), hard order freeze limits (`RK-06` = 1,800 qty), advisory ceilings (`RK-26`), max daily loss (`RK-03`), and maximum drawdown halts (`RK-04`).
5. **Zero-Loss Replay & Checkpoint Recovery (`M7-04`):** Persistent strategy checkpoints on bar boundaries. Upon daemon restart, recovers state, replays uncommitted frames, verifies zero duplicate fills, and enters `WARMING_UP` prior to `RUNNING`.
6. **24/7 Offline Market Simulator:** Plays back authentic recorded market sessions from DuckDB/Parquet through `FrameBus` during weekends and off-market hours.
7. **Draggable Chart SL/TP Paper Orders (`M7-08`):** Synchronizes discretionary paper order levels between web chart and paper broker with server-authoritative acknowledgments.
8. **100% Pass on Gate G5 Contract Tests:** Pass all formal audit requirements for milestones `M7-01` through `M7-09`.

### 3.2 Non-Goals
1. **No Live Broker Execution (Stage 9 / Gate 05):** No real-money orders sent to Upstox API. Real broker routing remains disabled (`NO-GO`) until Gate G5 certification and owner signoff (`ADR-026`).
2. **No Redis or Valkey Dependency:** Canonical specs stipulate that local transport (`FrameBus`) and SQLite/PostgreSQL WAL journals are used; Redis/Valkey is prohibited unless measured p95 latency exceeds 500ms.
3. **No Distributed Cloud Infrastructure:** QuantView runs locally on Windows 11 as a dedicated institutional workstation.

### 3.3 Anti-Goals
1. **No Look-Ahead in Streaming Feeds:** Causal timestamps strictly enforced: `available_at = finalized_at = bar_end + grace_period`. Never backdate live bars to `bar_end`.
2. **No Unreconciled Trades:** Trades cannot be marked as filled without corresponding ledger entries in integer paise.
3. **No Silent Forward-Filling:** Missing feed ticks generate explicit data-gap flags; the system never invents fake prices.

---

## 4. System Architecture & Detailed Module Design

```
+----------------------------------------------------------------------------------------------------+
|                                    QUANTVIEW STAGE 7 RUNTIME                                       |
|                                                                                                    |
|  [UPSTOX MARKET FEED]             [RECORDED SESSION REPLAY]                                        |
|  Upstox WS Protobuf Feed           DuckDB Analytical Lake Parquet                                  |
|           |                                      |                                                 |
|           +------------------+-------------------+                                                 |
|                              |                                                             |
|                              v                                                             |
|                   +----------------------+                                                 |
|                   |  FRAME_BUS TRANSPORT | <--- Monotonic seq_id, in-memory ring buffer    |
|                   |       (M7-01)        | <--- Zero-copy IPC / Async queue dispatch       |
|                   +----------------------+                                                 |
|                              |                                                             |
|         +--------------------+---------------------+                                       |
|         |                                          |                                       |
|         v                                          v                                       |
|  +--------------------+                     +--------------------+                         |
|  |  CANDLE BUILDER    |                     |  LIVE DAEMON CORE  |                         |
|  |     (M7-02)        |                     |   (M7-03, M7-07)   |                         |
|  | 1m & Multi-TF Bars |                     | Session Supervisor |                         |
|  | Boundary Clocks    |                     | State Recovery     |                         |
|  +--------------------+                     +--------------------+                         |
|         |                                          |                                       |
|         v                                          v                                       |
|  +--------------------+                     +--------------------+                         |
|  | FEATURE WARM-UP    |                     | RISK POLICY ENGINE |                         |
|  |     (M7-09)        |                     | (RK-01 to RK-26)   |                         |
|  | Streaming EMAs/RSI |                     | Hard Freeze Limits |                         |
|  +--------------------+                     +--------------------+                         |
|         |                                          |                                       |
|         +--------------------+---------------------+                                       |
|                              |                                                             |
|                              v                                                             |
|                   +----------------------+                                                 |
|                   |  STRATEGY HOST POOL  | <--- Isolated runner per deployment             |
|                   |  (LongCE, BullCall)  | <--- Integer-paise paper broker                 |
|                   +----------------------+                                                 |
|                              |                                                             |
|         +--------------------+---------------------+                                       |
|         |                                          |                                       |
|         v                                          v                                       |
|  +--------------------+                     +--------------------+                         |
|  |  POSTGRESQL / WAL  |                     | FASTAPI GATEWAY    |                         |
|  |   `qv_paper` DB    |                     |  Port 8000 Server  |                         |
|  | Orders & Ledger    |                     | WebSocket /ws/live |                         |
|  +--------------------+                     +--------------------+                         |
|                                                            |                               |
|                                                            v                               |
|                                                     +--------------------+                 |
|                                                     | TRADINGVIEW CLIENT |                 |
|                                                     | 60 FPS Canvas UI   |                 |
|                                                     | Live Tick Motion   |                 |
|                                                     +--------------------+                 |
+----------------------------------------------------------------------------------------------------+
```

---

## 5. Milestone Breakdown (`M7-01` through `M7-09`)

### 5.1 Milestone M7-01: FrameBus Local Transport & Raw Replay
- **Deliverables:** `packages/transport/frame_bus.py`, `packages/transport/replay.py`
- **Key Design:**
  - Fast ring-buffer transport maintaining monotonic `sequence_id` (uint64).
  - Ring buffer capacity: 65,536 frames in pinned memory.
  - Subscription filtering by `instrument_key` (e.g. `NSE_INDEX|Nifty 50`, `OPT-NIFTY-...`).
  - Supports replay from finalized `.parquet` / raw CSV snapshot files.
- **Verification:** Unit tests confirming zero message dropping under 20,000 frames/sec load, strict monotonic ordering, and backpressure handling.

### 5.2 Milestone M7-02: Streaming Candle Builder & Bar Aggregation
- **Deliverables:** `packages/market_data/streaming_builder.py`
- **Key Design:**
  - Consumes tick frames from `FrameBus`.
  - Maintains state for active provisional candle (Open, High, Low, Close, Volume, Tick Count).
  - Emits provisional candle event on every tick (`is_closed=False`).
  - Emits finalized candle event on minute boundary (`is_closed=True`).
  - Strict Indian market session boundaries: Discards ticks before `09:15:00.000` IST and after `15:30:00.000` IST.
  - Late-tick quarantine: Ticks arriving $> 1.5\text{ s}$ after bar close are tagged as `LATE_QUARANTINED` and do not alter finalized bars.

### 5.3 Milestone M7-03: Strategy Host, Risk Engine & Paper Broker
- **Deliverables:** `services/live_daemon/broker.py`, `services/live_daemon/host.py`, `packages/risk/evaluator.py`
- **Key Design:**
  - Evaluates pre-trade risk policy rules `RK-01` through `RK-26`:
    - `RK-01`: Global Kill-Switch (blocks all order submission if triggered).
    - `RK-02`: Market Session Window (orders allowed only `09:15` to `15:25` IST).
    - `RK-03`: Max Daily Loss Ceiling.
    - `RK-04`: Max Daily Drawdown Percentage.
    - `RK-06`: Exchange Freeze Limit (rejects quantity $> 1,800$ for NIFTY).
    - `RK-26`: Advisory Lot Ceiling.
  - Fill engine simulates real market fills using bid/ask quotes:
    - Market BUY fills at `Ask` price (with simulated adverse slippage).
    - Market SELL fills at `Bid` price.
  - Deducts statutory exchange fees per `UPSTOX_2026_V1` fee schedule.
  - Records all events directly in append-only financial ledger (`packages/ledger/`).

### 5.4 Milestone M7-04: Checkpoint, Replay & Reconciliation
- **Deliverables:** `services/live_daemon/recovery.py`
- **Key Design:**
  - Persists atomic strategy checkpoint JSON + SQLite/Postgres state at every bar close.
  - Checkpoint schema: `last_seq_id`, `active_position`, `pending_orders`, `cash_paise`, `unrealized_pnl_paise`.
  - Recovery sequence upon daemon startup:
    1. Read latest valid checkpoint.
    2. Query ledger balance: verify `Cash + Margin Reserved == Initial Capital + Realized PnL`.
    3. Replay uncommitted tick frames from `last_seq_id` to current.
    4. Deduplicate fills by `fill_id`.
    5. Set state to `WARMING_UP`.

### 5.5 Milestone M7-05: End-to-End Recorded-Session Comparison
- **Deliverables:** `tests/simulation/test_recorded_session_parity.py`
- **Key Design:**
  - Plays back 1 complete historical trading session through `FrameBus` into the live daemon.
  - Executes `LongCETrendFollowing` live.
  - Compares the generated live trade logs, fills, fee deductions, and final equity bit-for-bit against a static historical backtest.
  - Requires zero variance in trade count and $\le 1\text{ paise}$ difference in financial ledger totals.

### 5.6 Milestone M7-06: Live Operational Fault Suite
- **Deliverables:** `tests/live/test_operational_faults.py`
- **Key Design:**
  - Injects operational anomalies in an automated test harness:
    - Sudden Upstox WebSocket disconnect and auto-reconnect backoff (1s, 2s, 4s, max 16s).
    - Stale market quote stream (no ticks for $> 60\text{ s}$ transitions state to `HALTED_DATA`).
    - Emergency Kill Switch activation via REST/WebSocket call.
    - Token expiration during session.

### 5.7 Milestone M7-07: Deployment Process Isolation & Supervisor
- **Deliverables:** `services/live_daemon/supervisor.py`, `services/live_daemon/main.py`
- **Key Design:**
  - Supervised daemon managing deployment lifecycles.
  - Tracks heartbeat pulses every 1.0 second.
  - Transitions failed deployments to `HALTED_FAULT` without affecting active peer strategies.
  - Provides REST management endpoints: `/api/v1/daemon/status`, `/api/v1/daemon/start`, `/api/v1/daemon/stop`, `/api/v1/daemon/kill-switch`.

### 5.8 Milestone M7-08: Manual Paper Orders & Chart SL/TP Drag
- **Deliverables:** `apps/web/js/chart.js`, `apps/web/js/app.js`, `services/api/routers/paper.py`
- **Key Design:**
  - Enables user to click and drag the horizontal Stop-Loss and Take-Profit lines rendered on the candlestick chart.
  - Pointer drop event dispatches `PATCH /api/v1/paper/positions/{id}/brackets` with new `stop_loss` or `take_profit` price.
  - Server validates against current spot price (SL must remain below entry for BUY, TP above) and acknowledges.
  - Client updates visual lines only after server acknowledgment.

### 5.9 Milestone M7-09: Streaming Feature Warm-Up & State Sync
- **Deliverables:** `packages/research/streaming_features.py`
- **Key Design:**
  - When daemon starts or recovers mid-day, queries DuckDB analytical lake for preceding bars (e.g. 50 bars) to seed exponential moving averages (EMA 9, EMA 21) and RSI 14.
  - Prevents "cold-start" strategy distortion by holding strategy in `WARMING_UP` status until all indicator buffers reach required lookback depth.

---

## 6. Directory Layout & Deliverable Artifacts

```
c:\Algo\quantview/
├── packages/
│   ├── transport/                           # Milestone M7-01
│   │   ├── __init__.py
│   │   ├── frame_bus.py                     # High-performance in-memory ring buffer
│   │   └── replay_player.py                # 24/7 Recorded-session tick player (1x/2x/5x)
│   ├── market_data/
│   │   └── streaming_builder.py             # Milestone M7-02: 1m streaming candle aggregator
│   └── research/
│       └── streaming_features.py            # Milestone M7-09: Streaming indicator warm-up
├── services/
│   ├── live_daemon/                         # Milestones M7-03, M7-04, M7-07
│   │   ├── __init__.py
│   │   ├── main.py                          # Daemon process entrypoint & session loop
│   │   ├── supervisor.py                    # Multi-deployment process supervisor
│   │   ├── broker.py                        # Paper broker fill engine with quote execution
│   │   ├── host.py                          # Strategy deployment host
│   │   └── recovery.py                      # Bar checkpointing and WAL state replay
│   └── api/
│       └── routers/
│           ├── daemon.py                    # Gateway endpoints to inspect/control daemon
│           └── paper.py                     # Enhanced with bracket drag SL/TP patch (M7-08)
├── tests/
│   ├── transport/
│   │   └── test_frame_bus.py                # Monotonic sequence & ring buffer benchmarks
│   ├── daemon/
│   │   ├── test_streaming_builder.py        # Candle aggregation & boundary tests
│   │   ├── test_paper_broker_risk.py        # RK-01 to RK-26 enforcement
│   │   ├── test_checkpoint_recovery.py      # Idempotent state replay & zero duplicate fills
│   │   └── test_operational_faults.py      # Fault injection & disconnect handling
│   └── gate_g5/
│       └── test_gate_g5_certification.py    # Formal Gate G5 contract verification
└── run_workstation.ps1                      # Unified launcher for Gateway + Daemon
```

---

## 7. Gate G5 Verification & Success Criteria

Release Gate `G5` (Paper Runtime) will be formally audited and certified against the following verifiable thresholds:

1. **Tick Dispatch Latency (`M7-01`):** p95 dispatch latency across `FrameBus` $\le 0.5\text{ ms}$ under 20,000 frames/sec load.
2. **Deterministic Parity (`M7-05`):** 100% trade match and $\le 1\text{ paise}$ ledger delta between live daemon paper execution and historical backtest on identical feed data.
3. **Pre-Trade Risk Blocking (`M7-03`):** 100% rejection rate for orders violating `RK-01` (kill-switch), `RK-02` (off-hours), or `RK-06` (freeze limit $> 1,800$ qty).
4. **Crash Recovery Parity (`M7-04`):** Zero duplicate order fills, zero orphaned positions, and zero ledger discrepancies following sudden process kill and restart.
5. **24/7 Tick Player Verification:** Smooth 60 FPS live candle building, live quote updates, and interactive chart paper executions verified during off-market hours.
6. **Codebase Standards:**
   - Strict 4-part file docstrings, 4-part class docstrings, and 5-part function docstrings on all newly authored modules.
   - 0 `ruff` lint defects.
   - Upstream golden reference `C:\Algo\quant-terminal` bit-for-bit unmodified.
   - Strictly zero git commits or pushes per workspace rules.

