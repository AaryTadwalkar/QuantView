# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-21)
- **Approved Decisions (OWNER-DEC-01 to 06):** Formally logged in `ops/owner_decisions.md`.
- **M0 & M1 Milestones Cleared (VERIFIED):**
  - `M0-01` (inventory), `M0-06` (backup verification), `M0-08` (sandbox restore), `M0-07` (retention probe), `M0-11` (contracts).
  - `M1-01` (repository layout across 19 directories), `M1-02` (tooling, CI workflow, failure tests, `ops/evidence/M1-02.md`).
- **Complete Historical Option Backfill (Horizon: 2025-01-01 to 2026-10-19, 446 Trading Days - 100% Complete):**
  - **446/446 Daily Trading Sessions Completed & Verified:** 100% of all sessions across 21.5 months (all active trading days, not just expiries).
  - **Batch 1 (`2025-01-01` to `2025-06-19`):** 116 sessions, 5,118,315 bars, 861.76 MB (`reports/historical_options_2025_h1_audit_report.md`).
  - **Batch 2 (`2025-06-20` to `2026-02-03`):** 156 sessions, 7,003,462 bars, 1,178.30 MB (`reports/historical_options_20250620_20260203_audit_report.md`).
  - **Batch 3 (`2026-02-04` to `2026-10-19`):** 174 sessions, 8,210,644 bars, 1,385.49 MB (`reports/historical_options_20260204_20261021_audit_report.md`).
  - **Grand Total Staged Dataset:** **20,332,421 continuous 1-minute option bars** across **3,425.55 MB (3.43 GB)** in 446 separate daily CSVs (`staging/expired_options/nifty_options_1m_{expiry}_{trade_date}.csv`).
  - **Data Integrity Scorecard:** **0 duplicates**, **0 nulls**, strictly sorted **chronologically ascending (`09:15:00` to `15:29:00`)**.
  - **Cryptographic Provenance:** **32,232 companion JSON manifests** and raw gzip payloads in `Data/raw/upstox_rest/expired_api/` verified bit-for-bit (0 SHA-256 mismatches across 383.41 MB compressed).
  - **Regulatory Expiry Shift:** Accurately handled Thursday -> Tuesday shift and holiday cycles through official Upstox metadata.
- **Next Steps:**
  1. Publish verified staged daily option datasets to canonical Parquet lake storage (`Data/lake/option_candles/underlying=NIFTY/expiry=YYYY-MM-DD/part-0.parquet`).
  2. Proceed to deterministic vertical slice backtesting or market data store integration.

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
