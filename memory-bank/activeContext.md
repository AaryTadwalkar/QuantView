# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-27 — Stage 3 Complete & Gate G2a Certified PASS)
- **GATE G2a FULLY CERTIFIED PASS:** 87/87 Gate G2a tests PASS, 222/222 full repo tests PASS in 8.99s. Full audit report published at [`reports/stage3_closure/gate_g2a_audit_report.md`](file:///c:/Algo/quantview/reports/stage3_closure/gate_g2a_audit_report.md).
- **DELIVERED MILESTONES (M4-01 through M4-22):**
  - **Phase 3A (`M4-01`):** Exact-money types (`Paise = NewType("Paise", int)`), adverse `TickQuantizer`, UTC epoch timestamps.
  - **Phase 3B (`M4-13`, `M4-02`):** Pre-implementation golden oracle across 9 scenarios. Fundamental balance equation verified.
  - **Phase 3C (`M4-06`, `M4-04`):** Effective-dated Indian fee engine (Budget 2026 STT 0.15%, NSE turnover 0.03553%) and PIT Contract Selector.
  - **Phase 3D (`M4-07`, `M4-11`):** 15 canonical ledger events, rebuildable projections, Parquet persistence, and PostgreSQL trigger enforcement.
  - **Phase 3E (`M4-03`, `M4-05`, `M4-22`):** SimulationClock (375 exchange minutes), IntrabarFillEngine (`STOP_FIRST`, 15:25 force-flat, `NO_NEXT_BAR` at 15:29).
  - **Phase 3F (`M4-20`, `M4-12`):** Pre-trade RiskPolicyEvaluator (RK-01..06) and StrategyRegistry with SHA-256 source code hashing.
  - **Phase 3G (`M4-18`, `M4-08`):** 39-field EngineRunConfig (mandatory capital > 0), CLI runner `tools/run_backtest.py`, and 5 provenance artifacts.
  - **Phase 3H (`M4-15`):** 22+ performance metrics, Bailey & López de Prado (2014) DSR with trial validity gate ($N < 2$ emits null).
  - **Phase 3I (`M4-09`, `M4-10`, `M4-21`):** Real-market benchmark on 446 DuckDB sessions, 5-yr synthetic scalability (1,250 sessions in 0.28s), 3-rerun byte-identical determinism, and non-blocking margin spike [`reports/margin-settlement-evidence.md`](file:///c:/Algo/quantview/reports/margin-settlement-evidence.md).
- **DOCUMENTATION & REPO CONSISTENCY:**
  - `tools/qv_check.py lint DOCS` PASS (0 defects).
  - `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
- **NEXT PHASE:** Stage 4 / Gate G2b (Multi-Leg Position Groups & Short Options Margin Guards).

## Canonical Architectural Contracts & Modes
- **Operating Modes:** `RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`.
- **Accounting Standard:** Event-sourced integer-paise ledger with deterministic projections ($\text{Cash} + \text{Long MV} == \text{Initial} + \text{Gross} + \text{Unrealized} - \text{Fees}$).
- **Causal Execution Model:** `feature.available_at <= decision_time`. Next-bar open fill. Final bar 15:29 rejection (`NO_NEXT_BAR`).
- **Release Gates:** Gate G0 (Collectors: PASS), Gate G1 (Data Foundation: PASS), Gate G2a (Single-Leg Engine: PASS), Gate G2b (Multi-Leg Engine: READY TO START).
