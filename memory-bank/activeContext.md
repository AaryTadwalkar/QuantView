# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-20)
- **Approved Decisions (OWNER-DEC-01 to 06):** Formally logged in `ops/owner_decisions.md`.
- **M0 & M1 Milestones Cleared (VERIFIED):**
  - `M0-01` (inventory), `M0-06` (backup verification), `M0-08` (sandbox restore), `M0-07` (retention probe), `M0-11` (contracts).
  - `M1-01` (repository layout across 19 directories), `M1-02` (tooling, CI workflow, failure tests, `ops/evidence/M1-02.md`).
- **2025 H1 Full Daily Historical Option Ingestion (Horizon: 2025-01-01 to 2025-06-19, 116 Trading Days):**
  - **116/116 Daily Trading Sessions Completed & Verified:** 100% of all trading sessions in 2025 H1 (not just expiries, but all Mondays, Tuesdays, Wednesdays, Thursdays, Fridays).
  - **Staged Dataset:** **5,118,315 continuous 1-minute option bars** across **861.76 MB** of separate daily CSV files (`staging/expired_options/nifty_options_1m_{expiry}_{trade_date}.csv`).
  - **Data Integrity:** **0 duplicates**, **0 nulls**, strictly sorted **chronologically ascending (`09:15:00` to `15:29:00`)**.
  - **Provenance:** **6,106 cryptographic companion manifests** and raw gzip payloads in `Data/raw/upstox_rest/expired_api/` verified bit-for-bit (0 SHA-256 mismatches across 52.16 MB).
  - **Tooling Architecture Consolidated:** Removed redundant ad-hoc scripts; unified all multi-day range backfill, pre-flight validation, and post-import auditing directly into canonical `tools/ingest/import_expired_option_candles.py`.
  - **Audit Report Published:** Comprehensive 116-session scorecard delivered in [`reports/historical_options_2025_h1_audit_report.md`](file:///c:/Algo/quantview/reports/historical_options_2025_h1_audit_report.md).
- **Next Steps:** Proceed to publish verified staged daily option datasets to canonical Parquet lake storage (`Data/lake/option_candles/underlying=NIFTY/expiry=YYYY-MM-DD/part-0.parquet`).

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
