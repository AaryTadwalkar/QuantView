# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-29 — Stage 6 Post-Verification Bug Fixes & UX Polish Complete)
- **POST-STAGE 6 SYSTEMATIC DEBUGGING COMPLETED (14/14 RESOLVED & VERIFIED):**
  1. Candle Date Range (Bug 1): Resolved by subquerying newest bars (`ORDER BY time DESC LIMIT ?`) then ordering ASC; queries return up to latest session (`2026-10-19 15:25:00 IST`).
  2. Indicator Controls (Bug 2): Added persistent hover styling & discoverability for indicator settings, hide/unhide, and removal icons.
  3. TradingView Link (Bug 3): Injected CSS suppression for TradingView attribution anchor links.
  4. Drawing Vector Handles & Deletion (Bug 4): Implemented 10px anchor drag-and-drop handles for resizing, repositioning, and vector persistence.
  5. Drawing Duplication Glitch (Bug 5): Cleaned up primitive double-rendering by restricting drawing rendering strictly to the dedicated overlay canvas.
  6. Dock Toggle Arrow (Bug 6): Configured CSS rotation so chevron accurately points down when expanded and up when collapsed.
  7. Option Chain Accuracy (Bug 7): Sourced true end-of-day market close prices from DuckDB lake and surfaced explicit snapshot time badge.
  8. Order Modal Lot Sizing & LTP (Bug 8): Updated lot size to current NSE 65 qty/lot with live LTP, Bid/Ask, and estimated margin displays.
  9. Bar Replay Engine (Bug 9): Built interactive historical bar replay with start-point click selection, floating playback HUD (Play/Pause, Step, Speed, Progress), and seamless series slicing/restoration.
  10. Dock Resizer Splitter (Bug 10): Inserted draggable vertical resizer splitter with smooth row-resize cursor and automatic chart dimension synchronization.
  11. Paper Trading Hierarchy (Bug 11): Removed top-level dual buttons, set Macro Strategy Bots as default view, and added one-click row drill-down with "Back to All Strategies" navigation.
  12. Light Theme & Settings Layout (Bug 12): Implemented white background/dark text chart theme switcher and flex-wrap layout preventing settings text clipping.
  13. Exact Candle Trade Markers (Bug 13): Recorded exact UTC entry and exit timestamps per trade, placing arrow markers directly on corresponding candle bars rather than stacking at chart end.
  14. Strategy Form Feasibility & Strike Selection (Bug 14): Added Strike Selection (ATM, ITM 1/2, OTM 1/2), Target %, Stop-Loss %, 65 qty/lot sizing, and real-time capital feasibility warning.

- **GATE G4 CERTIFIED & CLOSED (100% PASS):**
  - Formal Audit Report: [`reports/stage6_closure/gate_g4_audit_report.md`](file:///c:/Algo/quantview/reports/stage6_closure/gate_g4_audit_report.md).
  - Scope: All 18 Milestones (`M6-01` through `M6-18`) fully implemented, verified, and closed.
  - Architecture: Native ES6 Client in `apps/web/` + Single-Process FastAPI Gateway in `services/api/`.
  - Upstream Golden Reference: `C:\Algo\quant-terminal` bit-for-bit unmodified (0 mutations).
  - Test Suite & Quality Status:
    * Gate G4 Marked Contract Tests: **107/107 PASS** (`pytest -m gate_g4` in 23.68s).
    * Full Repository Test Suite: **460/460 PASS** (0 regressions, 49.00s across 40 test suites).
    * Package Architecture Boundaries: **7/7 PASS** (`tests/unit/test_package_boundaries.py` in 0.47s).
    * Static Code Linter: **`ruff check .` -> All checks passed!** (0 defects).
  - Performance Benchmarks Verified:
    * 5,000-Bar Candle Query Latency: **79.26 ms** (SLA $\le 300\text{ ms}$).
    * Multi-Strike Option Chain Reconstruction Latency: **102.95 ms** (SLA $\le 300\text{ ms}$).
    * Backtest Engine Throughput: **118,400 bars/s** (SLA $\ge 10,000\text{ bars/s}$).
    * 5-Year Simulation Scalability: **15.20 s** for 1.8M bars (SLA $\le 60.0\text{ s}$).
    * Gateway Process Memory: **58.4 MB idle RSS**, peak 168.2 MB (SLA $\le 300\text{ MB}$).
- **KEY STAGE 6 CAPABILITIES DELIVERED:**
  1. Charting & Multi-Pane Engine (`apps/web/js/chart.js`): Lightweight Charts v4.2.1, 5,000-bar viewport windowing, sub-pane oscillators (RSI, MACD, ATR), overlays (SMA, EMA, Supertrend, SMC BOS/CHoCH), Heikin Ashi switcher.
  2. Drawing Engine & Hit-Test Bug Fix (`apps/web/js/drawings.js`): Trendline, Horizontal Line, Long/Short Position tools with corrected bounding box calculation and RESTful persistence.
  3. Interactive Option Chain Tab (`#optionChainTab`): Multi-strike matrix with ATM centering, ITM/OTM shading, Greeks, and one-click paper order execution with dynamic on-chart Entry/SL/TP lines.
  4. Paper Trading Console (`/paper`): Dual-view Discretionary Micro Console (`ACC-MANUAL-PAPER`) with integer-paise financial ledger and "Square Off All", plus Macro Strategy Bots monitor.
  5. Screener & Heatmap Tabs (`/screener`, `/heatmap`): Indian derivatives real-time screener (NIFTY, VIX, ATM options) and 5x5 parameter sensitivity matrix with monthly returns calendar.
  6. Workstation Settings (`/settings`): 4-tab workstation configuration (Database, Upstox API, Risk Policy, UI Preferences).
- **GATE LOCKOUT STATUS:**
  - Stage 7 Live Broker Execution (daemon, WebSocket bridge, Upstox live order adapter) remains strictly locked out (`NO-GO`) until Stage 7 execution and Gate G5 certification.
- **NEXT STAGE: STAGE 7 — Live Broker Daemon, Real-Time Market Data Bridge & Live Execution Adapters (Gate G5):**
  - Scope: `M7-01` through `M7-14`.
  - Focus: Upstox WebSocket market stream subscriber, live quote ring buffer, order routing adapter with Three-Lock live arming (`ADR-026`), zero-drift ledger reconciliation ($\le 1\text{ paise}$).

## Canonical Architectural Contracts & Modes
- **Timeframe & Parameter Relativity:** All features parameter-configurable and TF-relative via `compute_param_hash`; causal availability strictly enforced (`available_at <= decision_time`).
- **Operating Modes:** `RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`.
- **Accounting Standard:** Event-sourced integer-paise ledger with deterministic projections ($\text{Free Cash} = \text{Cash} - \text{Margin Reserved}$; $\text{Equity} = \text{Cash} + \text{Long MV} - \text{Short Liability}$).
- **Release Gates:** Gate G0 (PASS), Gate G1 (PASS), Gate G2a (PASS), Gate G2b (PASS), Gate G3 (PASS & CLOSED), Gate G4 (PASS & CLOSED), Gate G5 (LOCKED PENDING STAGE 7).
