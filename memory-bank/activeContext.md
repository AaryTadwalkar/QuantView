# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-27 — Stage 4 / Gate G2b Fully Certified PASS)
- **STAGE 2 / GATE G0 FULLY CERTIFIED PASS & CLOSED:** 67/67 tests PASS. Live streaming verified.
- **STAGE 3 / GATE G2a FULLY CERTIFIED PASS & CLOSED:** 89/89 Gate G2a tests PASS. Reconciled to 0.00 paisa drift.
- **STAGE 4 / GATE G2b FULLY CERTIFIED PASS & CLOSED:**
  - **M4-14 (Position Groups & Declared Legs):** Canonical 10-state legging lifecycle, composite mark, combined P&L, high-water trailing stops, and stale mark propagation (`tests/unit/test_position_groups.py`).
  - **M4-16 (Legging Sequencer & Unwind Engine):** Margin-optimal entry/exit sequencing, 15:00 entry cutoff, 15:25 force-flat, emergency unwind recovery with **3x adverse tick slippage penalty** ($3 \times 5 = 15\text{ paise}$), and EOD boundary handling (`tests/unit/test_legging_sequencer.py`).
  - **M4-17 (Margin Evaluator & Realistic Mode Guard):** Fail-closed block preventing short options under `REALISTIC_ACCOUNT` (`MARGIN_NOT_VERIFIED`), `THEORETICAL` mode audit labelling, and ledger `free_cash_paise` reservation (`tests/unit/test_margin_evaluator.py`).
  - **M4-19 (Multi-Leg Golden Scenarios & Integration):** 4 hand-calculated golden oracle scenarios (ML-1..ML-4) passing with 0.00 paisa drift, 3 cold reruns byte-identical SHA-256 Parquet ledger hashes (`tests/integration/test_multileg_backtest.py`), and 500-session scalability benchmark (37,500 bars in 0.007s, `tests/integration/test_multileg_benchmark.py`).
  - **Formal Gate G2b Audit Report:** [`reports/stage4_closure/gate_g2b_audit_report.md`](file:///c:/Algo/quantview/reports/stage4_closure/gate_g2b_audit_report.md).
  - **Test Suite Status:** **31/31 Gate G2b tests PASS in 1.06s** (`pytest -m gate_g2b`). Full regression suite: **255/255 PASS in 13.22s**.
- **DOCUMENTATION & CONSISTENCY:**
  - `tools/qv_check.py lint DOCS` PASS (0 defects).
  - `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
- **NEXT PHASE:** Stage 5 (Gate G3: Market Features, Order Flow Imbalance, Volatility Surface & Indicators).

## Canonical Architectural Contracts & Modes
- **Operating Modes:** `RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`.
- **Accounting Standard:** Event-sourced integer-paise ledger with deterministic projections ($\text{Free Cash} = \text{Cash} - \text{Margin Reserved}$; $\text{Equity} = \text{Cash} + \text{Long MV} - \text{Short Liability}$).
- **Causal Execution Model:** `feature.available_at <= decision_time`. Next-bar open fill. Final bar 15:29 rejection (`NO_NEXT_BAR`).
- **Release Gates:** Gate G0 (PASS), Gate G1 (PASS), Gate G2a (PASS), Gate G2b (PASS), Gate G3 (Pending).
