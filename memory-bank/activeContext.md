# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-20)
- **Approved Decisions (OWNER-DEC-01 to 06):** Formally logged in `ops/owner_decisions.md`.
- **M0 & M1 Milestones Cleared (VERIFIED):**
  - `M0-01` (inventory), `M0-06` (backup verification), `M0-08` (sandbox restore), `M0-07` (retention probe), `M0-11` (contracts).
  - `M1-01` (repository layout across 19 directories), `M1-02` (tooling, CI workflow, failure tests, `ops/evidence/M1-02.md`).
- **Phase 1 Pilot Execution & Offline Audit Outcome (`2025-01-02`):**
  - **Offline Audit:** 120 manifests validated (0 errors); 120 raw gzip checksums verified bit-for-bit (0 mismatches); 120 checkpoint contracts verified; staged CSV verified (41,496 rows across 113 unique contracts, 0 duplicates, 0 nulls); 35/35 unit tests passing.
  - **Sorting Fixed:** Timestamp ordering corrected in staged CSV and importer to strictly ascending (`09:15:00` to `15:29:00`) per `QUANTVIEW_DATA_SPEC.md` §2.1.
  - **Band Sizing & Upstox Quota Confirmed:** Retained $\pm 1,500$-point band (~120 contracts per expiry day; covers >96% volume/OI) to prevent quota burn on deep OTM untraded contracts.
  - **Master Expiry Calendar Generated:** Created [`config/nse_nifty_expiries_2025_2026.json`](file:///c:/Algo/quantview/config/nse_nifty_expiries_2025_2026.json) with 93 official weekly/monthly NIFTY expiries (Jan 2025 – Oct 2026).
  - **Simplified Roadmap Published:** Created [`DOCS/SIMPLIFIED_IMPLEMENTATION_PLAN.md`](file:///c:/Algo/quantview/DOCS/SIMPLIFIED_IMPLEMENTATION_PLAN.md) detailing all stages and data flows in plain English for the project owner.
- **Next Steps:** Execute automated bulk historical options ingestion (Jan 1, 2025 to Oct 2026) across the 93 expiries using daily staging CSVs, followed by Parquet lake publishing (`Data/lake/`).

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
