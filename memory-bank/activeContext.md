# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-24)
- **Phase 5 & Stage 1 Gate G1 Closure (100% COMPLETE - ALL PASS):**
  - **Stage 1 (Historical Data Foundation) Officially Closed:** All 12 milestones (`M3-01` to `M3-12`) passed with zero defects. Formal Gate G1 audit report: [`reports/gate_g1_audit_report.md`](file:///c:/Algo/quantview/reports/gate_g1_audit_report.md); evidence: [`reports/gate_g1_validation_results.json`](file:///c:/Algo/quantview/reports/gate_g1_validation_results.json).
  - **Active Production Lake (`Data/lake/` - Manifest Version 3 Live):**
    * 784 Parquet files, 38,753,287 records, 620.00 MB active, partitioned, and verified bit-for-bit.
    * 7 Canonical Datasets: `option_candles` (20.33M), `underlying_candles` (437K), `india_vix` (167K), `option_snapshot_captures` (82K), `option_snapshot_rows` (17.45M), `derived_candles` (287K across 3m, 5m, 15m, 30m, 1h, 4h), `data_eligibility` (1,161 sessions).
    * Manifest Version 3 active: [`Data/lake/manifest_active.json`](file:///c:/Algo/quantview/Data/lake/manifest_active.json); Manifest v2 archived: `manifest_v2_archive.json`.
  - **8 DuckDB Analytical Views Active in `Data/lake/quantview.duckdb`:**
    * `v_candles_underlying`, `v_candles_options`, `v_candles_vix`, `v_snapshots_captures`, `v_snapshots_rows`, `v_snapshots_reconstructed_chain`, `v_candles_derived`, `v_data_eligibility`. All queries $\le 50\text{ms}$.
  - **Tasks M3-10, M3-11, M3-12 Satisfied:**
    * `M3-10`: Parquet profile & DuckDB benchmarks verified (`ops/evidence/M3-10.md`).
    * `M3-11`: Exploratory strategy feasibility spike verified on 5m trend & 0-DTE straddle (`ops/evidence/M3-11.md`).
    * `M3-12`: Supporting datasets audited (`ops/evidence/M3-12.md`).
- **Automated Verification:** 56/56 unit tests PASS in 3.16s. `tools/qv_check.py lint DOCS` PASS (0 defects). `ops/verify_docs_consistency.py` PASS (0 defects).
- **Next Step:** Stage 2 — Live Market Stream & Collector Integration (`M2-01` to `M2-11`, Gate G0).

## Canonical Architectural Contracts & Modes
- **Operating Modes:** `RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`.
- **Allocation Modes:** `ISOLATED`, `PORTFOLIO` (`ADR-038`).
- **Causal Availability Model:** `available_at = bar_end` under `HISTORICAL_ASSUMED_AVAILABILITY` for backtests; `available_at = finalized_at = bar_end + grace_period` in live streams. Invariant: `feature.available_at <= decision_time`.
- **Risk Catalogue (`RK-01–RK-26`):** `RK-06` (hard freeze limit) vs `RK-26` (advisory lot ceiling).
- **Release Gates:** Phase 7 `GATE-04` ($\ge 10$ paper sessions) vs Phase 9 `GATE-05` ($\ge 30$ paper sessions, $\le 1\text{ paise}$ fee reconciliation, live capital authorization).

## 4-Tier Document Hierarchy (`ADR-007`, `SOURCE_OF_TRUTH_INDEX.md`)
1. **Tier 1 (Authority):** `ADR_REGISTER.md` (`ADR-001–ADR-041`, where `status == OWNER_APPROVED`).
2. **Tier 2 (System Contract):** `HIGH_LEVEL_DESIGN.md` (`P1–P18`, `L0–L7`, `G0.1–G7.9`, `GATE-01–GATE-05`).
3. **Tier 3 (Build Contract):** `LOW_LEVEL_DESIGN.md` (`RK-01–RK-26`, `CAP-01–CAP-24`, `B1–B6`, `T0.1–T9.2`).
4. **Tier 4 (Specialized Contracts):** `CHARTING_UX.md`, `BACKTESTING_REPORT_SPEC.md`, `OPTIONS_CHAIN_UI.md`, `PAPER_TRADING_UI.md`.
5. **Cross-Cutting Controls:** `TRACEABILITY_MATRIX.md`, `RECONCILIATION_AND_CHANGE_LOG.md`, `UNRESOLVED_DECISIONS_REGISTER.md`, `SOURCE_OF_TRUTH_INDEX.md`, `VALIDATION_REPORT.md`.
