# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-27 — Stage 5 / Gate G3 Fully Certified PASS & Closed)
- **STAGE 2 / GATE G0 FULLY CERTIFIED PASS & CLOSED:** 67/67 tests PASS. Live streaming verified.
- **STAGE 3 / GATE G2a FULLY CERTIFIED PASS & CLOSED:** 89/89 Gate G2a tests PASS. Reconciled to 0.00 paisa drift.
- **STAGE 4 / GATE G2b FULLY ACCEPTED & CLOSED:** 31/31 Gate G2b tests PASS. ML-3 synchronized.
- **STAGE 5 / GATE G3 FULLY CERTIFIED PASS & CLOSED:**
  - Published Formal Gate G3 Audit Report: [`reports/stage5_closure/gate_g3_audit_report.md`](file:///c:/Algo/quantview/reports/stage5_closure/gate_g3_audit_report.md).
  - All 12 Milestones Verified: `M5-01` to `M5-12` mapped with independent evidence reports in `ops/evidence/`.
  - Feature Architecture:
    * Schemas, Registry & 3 Causality Protocols (`M5-01`).
    * Technical Indicators & Pine Script Parity ($< 10^{-12}$) (`M5-03, M5-08, M5-11`).
    * Deterministic BOS/CHoCH Engine ($W_L=5, W_R=5$) (`M5-06`).
    * Market Calendar, 15:00/15:25 Countdowns & High-Water Mark (`M5-07`).
    * Lazy Reconstructed Option Chain View (`v_snapshots_reconstructed_chain`) (`M5-04`).
    * Black-76 Greeks & Bounded Brent IV Solver with strict `model_*` prefix (`M5-05`).
    * Option-Chain Derived Features (PCR, OI ROC, Straddle, Delta-band OI, 25d Skew) (`M5-12`).
    * Order Flow & Depth Proxies (Top-of-Book Depth Imbalance, Bar Volume Delta) (`M5-12`).
    * Non-Tradable Display Transforms (Heikin Ashi & Renko) (`M5-09`).
    * Frozen Model Artifact Contract & Anti-Training Barrier (`M5-10`).
    * Isolated Subprocess Runner with Timeouts and Crash Containment (`M5-07`).
    * Benchmark Throughput: 241,321 bars/sec; disk cache unjustified and left unimplemented (`M5-02`).
  - Automated Verification: **98/98 Gate G3 tests PASS**; **353/353 full-suite tests PASS in 11.63s** (0 regressions).
- **DOCUMENTATION & CONSISTENCY:**
  - `tools/qv_check.py lint DOCS` PASS (0 defects).
  - `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
  - `tests/unit/test_package_boundaries.py` 7/7 PASS.
- **NEXT ACTION:** Ready to begin Stage 6 / Gate G4 (FastAPI Query Service, Core UI & Chart Workflows).

## Canonical Architectural Contracts & Modes
- **Timeframe & Parameter Relativity:** All features parameter-configurable and TF-relative via `compute_param_hash`; causal availability strictly enforced.
- **Operating Modes:** `RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`.
- **Accounting Standard:** Event-sourced integer-paise ledger with deterministic projections ($\text{Free Cash} = \text{Cash} - \text{Margin Reserved}$; $\text{Equity} = \text{Cash} + \text{Long MV} - \text{Short Liability}$).
- **Release Gates:** Gate G0 (PASS), Gate G1 (PASS), Gate G2a (PASS), Gate G2b (PASS), Gate G3 (PASS & CLOSED).
