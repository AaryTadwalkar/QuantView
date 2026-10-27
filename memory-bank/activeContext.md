# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-27 — Stage 5 / Gate G3 Phase 5B Complete)
- **STAGE 2 / GATE G0 FULLY CERTIFIED PASS & CLOSED:** 67/67 tests PASS. Live streaming verified.
- **STAGE 3 / GATE G2a FULLY CERTIFIED PASS & CLOSED:** 89/89 Gate G2a tests PASS. Reconciled to 0.00 paisa drift.
- **STAGE 4 / GATE G2b FULLY ACCEPTED & CLOSED:** 31/31 Gate G2b tests PASS. ML-3 synchronized across fixtures, evidence, and audit reports.
- **STAGE 5 / GATE G3 IN PROGRESS (Phase 5B Complete):**
  - Frozen Plan: [`stage5_implementation_plan.md`](file:///C:/Users/Aary/.gemini/antigravity/brain/06a15e89-b29d-4bcb-80a8-a97856ca6a27/stage5_implementation_plan.md) fully audited and frozen.
  - Phase 5A (`M5-01` COMPLETE & TESTED): Registry, schemas, deterministic SHA-256 parameter hashing, 3 causality protocols. Evidence: [`ops/evidence/M5-01.md`](file:///c:/Algo/quantview/ops/evidence/M5-01.md).
  - Phase 5B (`M5-03`, `M5-08`, `M5-11` COMPLETE & TESTED):
    * `packages/features/statistical/indicators.py`: SMA, EMA (Pine seed & SMA seed), Wilder RSI, MACD, ATR, NATR, Bollinger Bands, Supertrend, ADX, Realized Volatility, IV-RV Spread interface.
    * `packages/features/statistical/vwap_guard.py`: Fail-closed Session VWAP quarantine (`SessionVWAPQuarantinedError`, `BLOCKED_QUARANTINED`).
    * `tests/fixtures/pine_indicator_oracle.py`: Ground-truth oracle matching TradingView Pine Script v5 within $< 10^{-12}$.
    * `tests/unit/test_causal_indicators.py`: 31/31 unit tests PASS under `@pytest.mark.gate_g3`.
    * Evidence Reports: [`ops/evidence/M5-03.md`](file:///c:/Algo/quantview/ops/evidence/M5-03.md), [`ops/evidence/M5-08.md`](file:///c:/Algo/quantview/ops/evidence/M5-08.md), [`ops/evidence/M5-11.md`](file:///c:/Algo/quantview/ops/evidence/M5-11.md).
  - Test Baseline: **302/302 PASS in 15.42s** (47 Gate G3 tests PASS in 6.90s).
- **DOCUMENTATION & CONSISTENCY:**
  - `tools/qv_check.py lint DOCS` PASS (0 defects).
  - `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
- **NEXT ACTION:** Await user review of Phase 5B delivery report before proceeding to Phase 5C (Deterministic Market Structure Engine BOS/CHoCH).

## Canonical Architectural Contracts & Modes
- **Operating Modes:** `RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`.
- **Accounting Standard:** Event-sourced integer-paise ledger with deterministic projections ($\text{Free Cash} = \text{Cash} - \text{Margin Reserved}$; $\text{Equity} = \text{Cash} + \text{Long MV} - \text{Short Liability}$).
- **Causal Execution Model:** `feature.available_at <= decision_time`. Next-bar open fill. Final bar 15:29 rejection (`NO_NEXT_BAR`).
- **Release Gates:** Gate G0 (PASS), Gate G1 (PASS), Gate G2a (PASS), Gate G2b (PASS), Gate G3 (Phase 5B Complete, In Progress).
