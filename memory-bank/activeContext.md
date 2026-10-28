# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-28 — Stage 6 Architecture & Plan Finalized)
- **STAGE 6 IMPLEMENTATION PLAN FINALIZED & SIGNED OFF:**
  - Authoritative document: [`DOCS/STAGE6_WEB_DASHBOARD_IMPLEMENTATION_PLAN.md`](file:///c:/Algo/quantview/DOCS/STAGE6_WEB_DASHBOARD_IMPLEMENTATION_PLAN.md).
  - Scope: Milestone M6 (`M6-01` through `M6-18`) strictly mapped to Release Gate `G4`.
  - Architecture: **Approach 1 — Native ES6 Client in `apps/web/` + Single-Process FastAPI Gateway in `services/api/`**.
  - Upstream Reference: `C:\Algo\quant-terminal` (Strictly Read-Only golden reference; never mutate external folders).
  - Builder check completed and approved:
    1. Paper Trading in Stage 6: Instant-fill manual simulator for `ACC-MANUAL-PAPER` with on-chart entry/SL/TP lines; live multi-session execution daemon deferred to Stage 7 (`M7-01` to `M7-14` / Gate G5).
    2. Market Data Sourcing: Full DuckDB analytical lake playback (1,161 sessions, 20M+ option candles, 2025–2026 expiries) + Upstox REST snapshot polling for live market hours.
    3. Indicators: Standard indicators computed in client JS at 60 FPS; proprietary SMC BOS/CHoCH & Supertrend computed in Python (`packages/features/`).
    4. Option Chain Tab: Primary bottom dock tab with direct paper order routing to `ACC-MANUAL-PAPER` without tab redirection.
    5. Drawing Bug Fix: Long/Short position hit-test bounding box corrected in `apps/web/js/drawings.js`.
- **CI & REPOSITORY CODE QUALITY 100% CLEAN:**
  - 353/353 full-suite tests PASS in 18.75s (0 regressions).
  - 218/218 gate marker tests PASS in 20.46s (G0a, G0, G1, G2a, G2b, G3).
  - `ruff check .` output: **All checks passed!** (0 errors).
  - `tests/unit/test_package_boundaries.py` 7/7 PASS in 0.09s.
- **IMMEDIATE NEXT STEP:**
  - Commence Stage 6 Phase 6A (FastAPI Backend Gateway in `services/api/`) and Phase 6B (UI Shell Integration into `apps/web/`).

## Canonical Architectural Contracts & Modes
- **Timeframe & Parameter Relativity:** All features parameter-configurable and TF-relative via `compute_param_hash`; causal availability strictly enforced (`available_at <= decision_time`).
- **Operating Modes:** `RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`.
- **Accounting Standard:** Event-sourced integer-paise ledger with deterministic projections ($\text{Free Cash} = \text{Cash} - \text{Margin Reserved}$; $\text{Equity} = \text{Cash} + \text{Long MV} - \text{Short Liability}$).
- **Release Gates:** Gate G0 (PASS), Gate G1 (PASS), Gate G2a (PASS), Gate G2b (PASS), Gate G3 (PASS & CLOSED), Gate G4 (PLANNED & READY TO EXECUTE).
