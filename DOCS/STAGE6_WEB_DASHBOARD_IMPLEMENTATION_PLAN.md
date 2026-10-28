# Stage 6 Implementation Plan: Web Dashboard, Strategy Browser & Interactive Charts

> **Document Status:** Authoritative Implementation Plan  
> **Milestone / Gate Target:** **Milestone M6** $\to$ **Release Gate `G4`**  
> **Parent Authority:** Canonical Documents (`QUANTVIEW_MASTER_SPEC.md` §2.4, `QUANTVIEW_DATA_SPEC.md` §11, `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md` §14–§19, `DOCS/AGENTS.md` §6.8, §7)  
> **Architecture Approach:** **Approach 1 — Native ES6 Client in `apps/web/` + Single-Process FastAPI Gateway**  
> **External Reference:** `C:\Algo\quant-terminal` (Strictly Read-Only Reference)  
> **Scope Boundary:** Stage 6 Only. Stage 7 (Live Daemon & Upstox Order Routing) is strictly deferred post-Gate G4.

---

## 1. Executive Summary & Intent

### 1.1 Intent
QuantView requires an institutional-grade, desktop-first quantitative trading workstation specifically tailored for Indian index and options research (NSE NIFTY 50 and India VIX). The previous experimental Google Stitch UI was rejected for being "gamey, childish, and lacking candle density." 

We adopt the pixel-perfect, authentic TradingView visual layout and interaction architecture from the open-source trading terminal (`C:\Algo\quant-terminal`), porting its clean UI shell into `apps/web/` and driving it with QuantView's deterministic Python simulation engine, DuckDB Parquet historical lake, and integer-paise financial ledger (`services/api/`).

### 1.2 The Architecture Decision (Approach 1)
Among three evaluated architectural options:
- *Approach 1 (Chosen):* Native ES6 Modules in `apps/web/` mounted directly by FastAPI as `StaticFiles`.
- *Approach 2 (Rejected):* Full React + TypeScript rewrite. Rejected due to 5–20ms canvas jitter risk, excessive virtual DOM reconciliation overhead, tripling of code size (~7,000 lines), and 2–3 weeks of delivery delay.
- *Approach 3 (Rejected):* Vite-bundled vanilla TypeScript shell. Rejected due to unnecessary Node.js tooling dependencies and dual-server process friction for a local desktop workstation.

**Approach 1 delivers:**
1. **Bare-metal 60–120 FPS canvas rendering** using Lightweight Charts v5 and direct 2D canvas drawing overlays.
2. **Sub-50ms initial load time** with zero `node_modules` overhead (0 MB bundler bloat).
3. **Single-command workstation launch:** `python -m services.api.main` serves both the high-speed REST/WebSocket API and the full interactive web client on `http://localhost:8000`.
4. **Type-safety without runtime tax:** A lightweight `types.d.ts` schema file in `apps/web/` provides full IDE autocomplete for backend Pydantic models.

---

## 2. Goals, Non-Goals & Anti-Goals

### 2.1 Goals
1. **Pixel-Perfect TradingView UI:** Authentic dark theme (`#131722`), left drawing toolbar, topbar navigation, high candle density, and a resizable bottom dock with `#bottomToggle`.
2. **Deterministic Backtest Visualizer:** Strategy Tester tab executing QuantView's Python engine (`packages/engine/runner.py`) via `/api/v1/backtest/run`, rendering institutional tear sheets (Sharpe, Sortino, Max Drawdown %, Win Rate) and plotting trade entry/exit markers directly on the chart candlesticks (`series.setMarkers`).
3. **NIFTY Option Chain Tab:** Live/Historical option chain centered at ATM spot ($\pm 15$ strikes), Greeks ($\Delta, \Gamma, \Theta, \nu$), IV, and Open Interest.
4. **Seamless Manual Paper Execution:** Clicking **Buy** or **Sell** on the Option Chain instantly places an order into the dedicated manual paper account (`ACC-MANUAL-PAPER`) without navigating away from the Option Chain tab. Immediately renders entry price lines and Stop-Loss (SL) / Take-Profit (TP) levels across the main candlestick chart.
5. **Macro & Micro Paper Trading Views:** Macro table of automated strategies (status `Running` or `Warming Up`, lots, today's P&L, historical runs) and micro console for inspecting a single strategy's telemetry and trade logs.
6. **Drawing Tool Bug Fix:** Fix the hit-test bounding box bug in `drawings.js` so that Long and Short position risk/reward boxes can be selected and deleted immediately.
7. **Screener & Heatmap Customization:** Tailored for Indian derivatives: `NSE:NIFTY50`, `INDIAVIX`, and strategy parameter sensitivity heatmaps.
8. **100% Pass on Gate G4:** Satisfy all formal acceptance contracts for tasks `M6-01` through `M6-18`.

### 2.2 Non-Goals
1. **No Live Broker Trading in Stage 6:** Real-money live trading with Upstox is strictly locked until Stage 9 / Gate 05 (`ADR-012`, `ADR-026`).
2. **No Live Execution Daemon in Stage 6:** The background multi-session supervisor daemon is the deliverable of Stage 7 (`M7-01` to `M7-14` / Gate G5). Stage 6 focuses on the web dashboard, interactive charts, and API gateway.
3. **No Crypto or US Stock Endpoints:** All mock Binance, Alpaca, and Yahoo Finance feeds from the open-source terminal are completely stripped out.

### 2.3 Anti-Goals
1. **No "Gamey" or Cluttered UI:** No oversized buttons, neon cartoon badges, or excessive low-contrast whitespace.
2. **No Floating-Point Financial Calculations in Frontend:** All monetary values, margins, fees, and P&L calculations originate from QuantView's integer-paise ledger (`packages/ledger/`) and are formatted into rupee strings for display only.
3. **No Look-Ahead or Unaligned Timestamps:** All chart data, trade markers, and indicators strictly respect the `UtcEpochSec` contract and causal point-in-time constraints (`available_at <= decision_time`).

---

## 3. Directory Layout & Architecture Migration

### 3.1 Workspace Layout
```
c:\Algo\quantview/
├── apps/
│   └── web/                                 # Stage 6 Frontend Client (Native ES6)
│       ├── index.html                       # Main workstation shell (Topbar, Drawbar, Chart, Bottom Dock)
│       ├── css/
│       │   └── app.css                      # TradingView dark theme tokens & component styles
│       ├── js/
│       │   ├── app.js                       # Main application orchestrator & state manager
│       │   ├── api.js                       # Typed client routing to FastAPI /api/v1/*
│       │   ├── chart.js                     # Lightweight Charts v5 manager & multi-timeframe engine
│       │   ├── drawings.js                  # Canvas drawing overlay (with Long/Short fix)
│       │   ├── panels.js                    # Bottom dock panels (Tester, Paper, Chain, Screener, Heatmap)
│       │   ├── sound.js                     # Web Audio API fill notifications
│       │   └── types.d.ts                   # TypeScript definition contract mirroring Pydantic models
│       └── lib/
│           └── lightweight-charts.standalone.production.js  # TradingView Lightweight Charts v5
├── services/
│   └── api/                                 # Stage 6 FastAPI Gateway
│       ├── __init__.py
│       ├── main.py                          # FastAPI application factory & StaticFiles mount
│       ├── config.py                        # CORS, host, port, auth settings
│       ├── deps.py                          # Database & ledger dependencies
│       └── routers/
│           ├── __init__.py
│           ├── market.py                    # /api/v1/market (Candles, Quotes, Viewport)
│           ├── options.py                   # /api/v1/options (Chain, Expiries, Strikes)
│           ├── backtest.py                  # /api/v1/backtest (Run, Status, Tear Sheet, Markers)
│           ├── paper.py                     # /api/v1/paper (Accounts, Orders, Positions, Strategies)
│           ├── indicators.py               # /api/v1/indicators (Features, Schemas, Values)
│           ├── drawings.py                  # /api/v1/charts/drawings (CRUD persistence)
│           └── health.py                    # /api/v1/health (Data health, process status)
├── tests/
│   └── api/                                 # Stage 6 API & Gate G4 Test Suite
│       ├── test_market_endpoints.py
│       ├── test_options_endpoints.py
│       ├── test_backtest_endpoints.py
│       ├── test_paper_endpoints.py
│       └── test_gate_g4_contract.py
└── DOCS/
    └── STAGE6_WEB_DASHBOARD_IMPLEMENTATION_PLAN.md  # This authoritative plan
```

---

## 4. Phase-by-Phase Technical Implementation Plan

```mermaid
flowchart TD
    subgraph Phase 6A: Backend API Gateway
        A1["FastAPI Application & Mount\n(services/api/main.py)"] --> A2["Market & Candles API\n(M6-01, M6-03, M6-16)"]
        A2 --> A3["Option Chain & Expiries API\n(M6-15, M6-18)"]
        A3 --> A4["Backtest Runner API\n(M6-07, M6-09)"]
        A4 --> A5["Paper Trading & Risk API\n(M6-06, M6-14)"]
        A5 --> A6["Drawings & Settings API\n(M6-13, M6-02, M6-05)"]
    end

    subgraph Phase 6B: Frontend Shell & Chart Viewport
        B1["Port UI Shell to apps/web/\n(index.html, app.css, lib/)"] --> B2["Lightweight Charts v5 Adapter\n(UtcEpochSec + IST format)"]
        B2 --> B3["Fix Long/Short Drawing Bug\n(drawings.js hitTest)"]
        B3 --> B4["Indicator Overlays & Sub-panes\n(M6-11, M6-12, M6-17)"]
    end

    subgraph Phase 6C: Bottom Dock Panels & Option Chain
        C1["Strategy Tester Panel\n(Python Backtest & On-Chart Markers)"] --> C2["NIFTY Option Chain Tab\n(Live Greeks, OI, ATM Centering)"]
        C2 --> C3["One-Click Paper Execution\n(Direct to ACC-MANUAL-PAPER)"]
        C3 --> C4["On-Chart SL/TP Price Lines\n(Entry, Stop, Target rendering)"]
        C4 --> C5["Paper Trading Macro/Micro Views\n(Active Bots vs Manual Console)"]
        C5 --> C6["Screener & Heatmap Customization\n(NIFTY 50, VIX, Sensitivity)"]
    end

    subgraph Phase 6D: Gate G4 Verification
        D1["Automated API Test Suite\n(pytest -m gate_g4)"] --> D2["End-to-End Workstation Walkthrough"]
        D2 --> D3["Gate G4 Audit Report & Signoff"]
    end

    Phase 6A --> Phase 6B
    Phase 6B --> Phase 6C
    Phase 6C --> Phase 6D
```

---

## 5. Detailed Milestone Mapping (`M6-01` to `M6-18`)

### M6-01 — FastAPI Read/Query API and Typed Client
- **Spec refs:** ENGINE §11, §11.1, §18
- **Deliverables:**
  - `services/api/main.py`: FastAPI application configuring local CORS, middleware, static files mount (`apps/web`), and error handlers.
  - `services/api/routers/`: Modular route controllers for market, options, backtest, paper, and health.
  - `apps/web/js/types.d.ts`: TypeScript definition contracts mirroring Pydantic schemas.
- **Acceptance Contract:** API schema validation tests pass; command endpoints require local authorization; no wildcard CORS in production mode.

### M6-02 — Data-Health and Coverage Page / Modal
- **Spec refs:** DATA §8, ENGINE §18.1
- **Deliverables:**
  - `services/api/routers/health.py`: Endpoint `GET /api/v1/health/coverage` inspecting DuckDB Parquet coverage, missing sessions, gap counts, and data eligibility.
  - Frontend Health Modal in Topbar: Displays session coverage (1,161 sessions), raw snapshot status, and data verification flags.
- **Acceptance Contract:** User can inspect missing sessions, data freshness, and contract coverage before launching backtests.

### M6-03 — Candle Chart Rendering and Viewport Engine
- **Spec refs:** ENGINE §18, §18.1, §18.3
- **Deliverables:**
  - `apps/web/js/chart.js`: Lightweight Charts v5 configuration managing time scale, price scale, crosshairs, and volume histogram.
  - Canonical `UtcEpochSec` timestamp contract with IST (`Asia/Kolkata`, `UTC+05:30`) display formatting.
  - Server-side candle endpoint `GET /api/v1/market/candles` supporting 1m, 5m, 15m, 1h, and 1d aggregations from DuckDB.
- **Acceptance Contract:** 5,000-bar data-ready latency $\le 300\text{ ms}$ server-side; initial payload $\le 5,000$ bars; smooth 60 FPS panning and zooming.

### M6-03b — UI-1 Per-Strike Option Chart with Trade Markers
- **Spec refs:** DATA §3, ENGINE §2, §18.1, §18.3
- **Deliverables:**
  - Strike chart mode in `apps/web/js/chart.js`: Ability to switch symbol from `NSE:NIFTY50` to a specific option strike (e.g., `NIFTY26OCT24200CE`).
  - Renders option OHLC historical candles directly from DuckDB view `v_candles_options`.
  - Trade markers plotted on option candles using `series.setMarkers()` for option-level fills.
- **Acceptance Contract:** Strike-specific candle visualization with trade markers at exact `UtcEpochSec` coordinates; point-in-time causal checks ensure future bars are not revealed.

### M6-04 — Results and Audit Panel
- **Spec refs:** ENGINE §18.1, §20
- **Deliverables:**
  - Results sub-view in Strategy Tester tab: Equity curve, monthly returns calendar, drawdown chart, and trade list.
  - Trade log table with sortable columns: Entry Time, Exit Time, Contract, Side, Qty, Entry Price, Exit Price, Gross P&L, Fees, Net P&L (in paise and rupees).
  - Traceable decision audit: Clicking a trade highlights the entry candle and reveals the signal reason code and rule parameters.
- **Acceptance Contract:** Audit panel reproduces decision inputs, fill prices, and statutory fees directly from stored backtest run artifacts.

### M6-05 — Chart License and API Health
- **Spec refs:** ENGINE §11.1, §18.3, MASTER §5
- **Deliverables:**
  - `ops/evidence/M6-05.md`: Formal license documentation confirming TradingView Lightweight Charts v5 Apache 2.0 open-source status.
  - `services/api/routers/health.py`: Endpoints `GET /api/v1/health` and `GET /api/v1/health/heartbeat`.
- **Acceptance Contract:** License status formally documented; process health checks return HTTP 200 within $\le 50\text{ ms}$; stale collector alert triggers if last tick $> 60\text{ s}$ during market hours.

### M6-06 — Accounts and Risk-Policy CRUD
- **Spec refs:** DATA §2.1, ENGINE §7, §8
- **Deliverables:**
  - `services/api/routers/paper.py`: Endpoints for managing accounts (`ACC-MANUAL-PAPER`, `ACC-STRAT-*`) and viewing active risk policies (`RK-01` to `RK-26`).
  - Frontend Risk Settings panel: Inspecting account allocation mode (`ISOLATED` vs `PORTFOLIO`), maximum drawdown limit, order freeze limit (`RK-06`), and daily loss locks.
- **Acceptance Contract:** Accounts and risk policies are partitioned; historical backtests retain their frozen policy versions without retro-active mutation.

### M6-07 — Backtest Launch and Configuration Commands
- **Spec refs:** ENGINE §11.1, §18.1, §19
- **Deliverables:**
  - `services/api/routers/backtest.py`:
    - `POST /api/v1/backtest/run`: Validates `RunConfig`, executes `packages/engine/runner.py`, and returns complete execution results.
    - `POST /api/v1/backtest/cancel`: Graceful cancellation of in-flight backtest.
    - `GET /api/v1/backtest/status/{run_id}`: Real-time progress monitoring.
- **Acceptance Contract:** Bounded execution; invalid parameters rejected with HTTP 422 and structured field error messages; cancellation cleanly halts clock progression.

### M6-08 — Dashboard and Strategy Browser UI
- **Spec refs:** ENGINE §18.1, MASTER §1
- **Deliverables:**
  - Dashboard header and status banner: Market status (Open/Closed), NIFTY 50 spot, India VIX, DuckDB lake connection state.
  - Strategy Browser modal/dropdown: Lists registered strategies in `packages/strategies/` with metadata (name, author, description, supported regimes, tunable parameters).
- **Acceptance Contract:** Strategy browser lists registered strategies; handles empty, loading, and error states gracefully; does not claim profitability or verified status without run evidence.

### M6-09 — RunConfig-Driven Backtest Form and Audit-Linked Flow
- **Spec refs:** ENGINE §18.1, §19, §20
- **Deliverables:**
  - Dynamic Form in Strategy Tester tab generated from QuantView's Pydantic `RunConfig`:
    - Strategy selector
    - Date range picker (`start_date`, `end_date`)
    - Initial capital (₹, default: ₹500,000)
    - Execution mode (`UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`)
    - Intrabar stop policy (`STOP_FIRST` vs `OHLC_PATH`)
    - Fee schedule selector (`UPSTOX_2026_V1`)
  - Trade Marker Linkage: Upon completion, backtest results trigger `chart.setMarkers()` on the main chart, plotting green `arrowUp` entries and red `arrowDown` exits.
- **Acceptance Contract:** Form fields validate strictly against `RunConfig` schema; chart markers link directly to audit log rows.

### M6-11 — UI-1 Schema-Driven Indicator Settings & Visibility
- **Spec refs:** ENGINE §18.1, §21
- **Deliverables:**
  - Indicator Legend on chart top-left: Lists active indicators with interactive micro-buttons:
    - Eye Icon: Toggle visibility on/off.
    - Gear Icon: Open parameter settings modal (e.g., EMA Length, RSI Period).
    - X Icon: Remove indicator from chart.
  - Indicator Dialog: Dynamically generated from feature registry schemas (`packages/features/`).
- **Acceptance Contract:** Indicator parameters can be adjusted and toggled dynamically without reloading the page or recreating the chart canvas.

### M6-12 — UI-2 Heikin Ashi Chart-Type Switcher UI
- **Spec refs:** ENGINE §18.1, §18.2, §22
- **Deliverables:**
  - Chart Type selector in Topbar: Standard Candlestick, Heikin Ashi, Line, Area.
  - Heikin Ashi transform calculation wired to `packages/features/` or client-side transform.
  - Clear visual banner: Displays an advisory badge when Heikin Ashi is active: *"Heikin Ashi candles are synthetic price transforms and cannot be used for execution levels."*
- **Acceptance Contract:** Clean switching between candle modes; advisory badge visible on synthetic transforms.

### M6-13 — UI-2 Drawing Tools, Persistence & Deletion Bug Fix
- **Spec refs:** DATA §2.1, ENGINE §18.1
- **Deliverables:**
  - Full Drawing Toolbar on left sidebar: Trendline, Horizontal Line, Ray, Extended Line, Fibonacci Retracement, Rectangle, Long Position, Short Position, Ruler/Measure, Text Note.
  - **The Crucial Bug Fix in `apps/web/js/drawings.js`:**
    ```javascript
    // Fixed hitTest for Long and Short Position drawings
    else if (["long", "short"].includes(d.type)) {
      const dir = d.type === "long" ? 1 : -1;
      const risk = Math.abs(a.price - b.price) || a.price * 0.01;
      const stop = a.price - dir * risk;
      const target = a.price + dir * risk * (d.rr || 2);
      const ys = this.y(stop);
      const yt = this.y(target);
      const minY = Math.min(a.y, ys, yt) - 6;
      const maxY = Math.max(a.y, ys, yt) + 6;
      const minX = Math.min(a.x, b.x) - 4;
      const maxX = Math.max(a.x, b.x, a.x + 40) + 4;
      const inside = x >= minX && x <= maxX && y >= minY && y <= maxY;
      dist = inside ? 3 : Infinity;
    }
    ```
  - Persistence endpoints: `GET /api/v1/charts/drawings` and `POST /api/v1/charts/drawings` persisting drawing JSON to DuckDB/JSON store.
- **Acceptance Contract:** Long and short position boxes can be selected by clicking anywhere in the entry, stop, or target zones, and deleted instantly with the `Delete` key or trash icon.

### M6-14 — UI-1 /paper and /settings Screens Implementation
- **Spec refs:** ENGINE §18.1, §18.2, DATA §2.1
- **Deliverables:**
  - **Paper Trading Tab in Bottom Dock:**
    - **Macro View:** Table of all automated paper trading strategies:
      - Strategy Name & ID
      - Operating Mode (`ACTUAL_OPTIONS`, `UNDERLYING_DIRECTIONAL`)
      - Status (`Running`, `Warming Up`)
      - Allocated Lots
      - Today's P&L (₹)
      - Win Rate & Sharpe
      - Past executed paper strategies with historical tear sheet inspector.
    - **Micro View (Manual Discretionary Console):**
      - Account balance cards: Equity, Cash, Margin Reserved, Free Cash.
      - Open Positions table with one-click "Square Off" button.
      - Working Orders table with "Cancel" button.
      - Trade History audit table.
  - **Settings Modal:** Configurable data paths, DuckDB lake connection status, Upstox API token status, and risk ceiling overrides.
- **Acceptance Contract:** Complete separation between macro multi-strategy monitoring and micro manual execution; real-time margin reservation calculation.

### M6-15 — UI-3 API and Data Contract Freeze
- **Spec refs:** ENGINE §18.1, §18.2, §26
- **Deliverables:**
  - OpenAPI schema generation and validation: Formally freeze `/api/v1/options/chain`, `/api/v1/market/candles`, and `/api/v1/backtest/run`.
  - Pydantic models in `services/api/schemas/` tested for strict serialization without null leaks or float rounding.
- **Acceptance Contract:** OpenAPI contract validation passes; mock responses match Pydantic schemas 100%.

### M6-16 — Read-Only Historical and Expired-Option Candle Viewer
- **Spec refs:** DATA §4.1, §4.2, §4.9, ENGINE §18.3
- **Deliverables:**
  - Direct integration with DuckDB views `v_candles_underlying` and `v_candles_options`.
  - Date and expiry selector allowing instant visual inspection of historical NIFTY sessions from January 1, 2025 to present day.
- **Acceptance Contract:** Instant visual rendering of any historical session without modifying lake data or requiring live network connection.

### M6-17 — Indicator Sub-Panes and Chart Overlays
- **Spec refs:** ENGINE §18, §18.1, §18.3
- **Deliverables:**
  - Multi-pane chart layout:
    - Primary Pane: Candlesticks, Volume overlay, EMA overlays (9, 21, 50, 200), Supertrend, and SMC Break of Structure (BOS) / Change of Character (CHoCH) swing labels.
    - Sub-Panes: RSI (14) with 70/30 bands, MACD histogram with signal line, and ATR volatility.
  - Panes resize smoothly when adjusting the bottom dock.
- **Acceptance Contract:** Sub-panes render at 60 FPS; crosshairs and time scales synchronize perfectly across all vertical panes.

### M6-18 — UI-1b: Option Chain Tab with One-Click Paper Execution & Chart Lines
- **Spec refs:** ENGINE §18.2, §21.1, §26
- **Deliverables:**
  - **Option Chain Primary Tab in Bottom Dock:**
    - Expiry dropdown (weekly/monthly Thursday dates).
    - Strike ladder centered on spot ($\pm 15$ strikes).
    - Left (Calls): OI, OI Change, IV, Delta, Bid/Ask, LTP, **Buy Button**, **Sell Button**.
    - Center: Strike Price.
    - Right (Puts): **Buy Button**, **Sell Button**, LTP, Bid/Ask, Delta, IV, OI Change, OI.
  - **One-Click Paper Order Routing:**
    - Clicking "Buy" or "Sell" on any strike opens a sleek inline popover (Lots: default 1 lot = 25 units, Market/Limit, optional SL/TP %).
    - Submitting dispatches `POST /api/v1/paper/orders` specifically for account `ACC-MANUAL-PAPER`.
    - **Tab Redirection Rule:** The bottom dock **does not redirect** away from the Option Chain. You remain on the Option Chain to maintain market visibility.
  - **On-Chart SL/TP & Entry Lines:**
    - The instant the order fills, `chart.createPriceLine()` plots:
      - Blue/Green line for Entry Price.
      - Red dashed line for Stop-Loss level.
      - Green dashed line for Take-Profit target level.
- **Acceptance Contract:** Order routes to `ACC-MANUAL-PAPER`; bottom dock stays on Option Chain; entry, SL, and TP lines render immediately on the main chart.

---

## 6. Screener & Heatmap Customization for NIFTY 50

### 6.1 Screener Tab (`screener`)
- Strips out US stocks and crypto tickers.
- Dedicated Indian Market Rows:
  1. `NSE:NIFTY50`: Index Spot, Daily Change %, Day High, Day Low, 52-Week Range.
  2. `INDIAVIX`: Volatility level, regime categorization (Low < 13, Normal 13–18, High > 18).
  3. `NIFTY ATM CE` & `NIFTY ATM PE`: Current weekly at-the-money option premiums and daily percentage change.

### 6.2 Heatmap Tab (`heatmap`)
- Repurposed from S&P 500 market-cap tiles into a **Quantitative Strategy Sensitivity Heatmap**:
  - X-Axis: Strike Offset ($\text{ATM}-2, \text{ATM}-1, \text{ATM}, \text{ATM}+1, \text{ATM}+2$).
  - Y-Axis: Stop-Loss % ($10\%, 20\%, 30\%, 40\%, 50\%$).
  - Tile Color: Net P&L / Sharpe Ratio gradient (Deep Green = High Return, Deep Red = High Drawdown).
  - Monthly Returns Calendar view showing daily/monthly P&L percentages for the active backtest.

---

## 7. Gate G4 Verification Protocol & Acceptance Criteria

To officially certify Gate G4 and close Stage 6, the system must satisfy the following automated verification checks:

1. **Lint & Static Quality:**
   - `ruff check .` passes with **0 errors**.
   - `tests/unit/test_package_boundaries.py` passes with **0 boundary violations**.
2. **Backend Automated Test Suite:**
   - All 353 existing core tests continue to pass with **0 regressions**.
   - New API test suite `pytest tests/api/ -m gate_g4` passes with **100% exit code 0**.
   - Validates all `/api/v1` routes: market candles, options chain, backtest execution, and paper trading orders.
3. **End-to-End Workstation Walkthrough:**
   - Launch FastAPI: `python -m uvicorn services.api.main:app --port 8000`.
   - Open browser to `http://localhost:8000`.
   - Verify candlestick chart renders `NSE:NIFTY50` with high candle density.
   - Verify long/short position drawing can be placed, selected by clicking anywhere in the box, and deleted immediately with `Delete`.
   - Open Option Chain tab, click **Buy** on an ATM Call, confirm order routes to `ACC-MANUAL-PAPER` without tab redirection, and verify entry/SL/TP lines render on the chart.
   - Open Strategy Tester tab, launch a backtest, verify tear sheet displays Sharpe/drawdown metrics, and confirm trade markers appear on the candles.
4. **Gate G4 Audit Report:**
   - Published to `reports/stage6_closure/gate_g4_audit_report.md` with complete evidence logs and owner signoff.

---

## 8. Commitments & Safety Rules
- **No Git Commit / Push:** Strictly adhere to the workspace rule.
- **External Folder Read-Only:** `C:\Algo\quant-terminal` remains completely untouched as our pristine reference.
- **Stage 7 Locked:** No live Upstox order execution or autonomous daemon processes until Gate G4 is officially closed.

