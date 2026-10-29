# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-29 — Stage 6 Complete, Gate G4 Certified & Closed)
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
