# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-20)
- **Approved Decisions (OWNER-DEC-01 to 06):** Formally logged in `ops/owner_decisions.md`.
- **M0 Milestones Cleared:**
  - `M0-01`: Refreshed inventory accepted (`ops/inventory.md`, 82,355 files, 2,131.18 MB).
  - `M0-06`: Secondary physical backup verified against `D:\Algo_Data_Final\Data` on `Cablet USB 3.0` (`ops/evidence/M0-06.md`).
  - `M0-08`: Isolated sandbox restore test verified with bit-for-bit SHA-256 identity (`ops/evidence/M0-08.md`).
  - `M0-07`: Bounded 7-request retention probe executed without token leak (`ops/evidence/M0-07.md`).
  - `M0-11`: Post-inventory acceptance contracts for M0-02 through M0-09 refined (`ops/evidence/M0-11.md`).
- **Phase A Retention Investigation Executed (OWNER-DEC-06):**
  - Dispatched 12 authorized read-only requests to `/v2/expired-instruments/option/contract` across exchange-verified dates.
  - `2024-12-26`: HTTP 200 OK, 281 contracts returned.
  - `2024-06-27` to `2019-06-27` (11 dates): HTTP 200 OK, 0 contracts returned (`data: []`).
  - Retention Cliff Identified: Between 2024-06-27 and 2024-12-26 (~1.8–2.3 years retention). Older history not available via this endpoint.
  - Budget exhausted (12/12 dispatched, 0 remaining). Live network acquisition halted.
- **Milestone M1-01 Cleared (VERIFIED):** Repository layout and boundaries established across `packages/*` (`domain`, `data`, `features`, `strategies`, `engine`, `risk`, `ledger`, `db`), `services/*`, `apps/web`, `config`. 18/18 tests passing (`test_package_boundaries.py`, `test_ingest_workflows.py`).
- **Endpoint Discrepancy Resolved:** Official expired-candle endpoint verified as `GET /v2/expired-instruments/historical-candle/{expired_instrument_key}/{interval}/{to_date}/{from_date}` (`to_date` precedes `from_date`).
- **Phase B0 Plan Prepared:** 1-request test on confirmed contract `NSE_FO|41685|26-12-2024` (NIFTY 23750 CE 26 DEC 24). Awaiting owner decision.
- **Next Offline Milestone:** `M1-02` (Establish tooling and CI). Zero live API calls active.

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

## Immediate Next Steps & Gates
- **Completed Surgical Pass (Read-Only Views, Streaming Tasks & Chart Scope):**
  - DATA: Added §4.9 defining read-only DuckDB views `v_candles_underlying` and `v_candles_options` (columns, source tables, point-in-time rules); updated M6-16 spec ref and acceptance to §4.9.
  - ENGINE §11.1: Replaced stale M7-07 citation with owning tasks (FrameBus transport M7-01; consumers M6-05 and M7-08).
  - AGENTS: De-duplicated chart scope so each of `overlays` (M6-17), `trade markers` (M6-03b), and `order lines` (M7-08) appears in exactly one task; M6-03 focused on basic candle chart rendering & viewport engine.
  - AGENTS V-09/V-10: Changed status from `COVERED` to `PARTIAL` to accurately reflect UI-1b delivered scope vs deferred UI-3 full panel.
  - Tooling: Updated `ops/verify_docs_consistency.py` to isolate UI-1b strictly to task bodies that mention it (M6-18) and added Check M verifying every named view/table in task acceptances exists in DATA.
- **Preservation & Consistency Status:** Verification `tools/qv_check.py lint DOCS stale.txt`: PASS (0 defects; tasks=114 active=113 days=262.5). Verification `ops/verify_docs_consistency.py`: PASS (0 defects across all 13 checks A–M).
- **Gated State:** M0-01 read-only inventory delivered in `ops/inventory.md`. Specification set fully locked, consistent, and verified.
- **Next Unblocked Task:** `M0-11` — Post-inventory contract refinement and owner approval.
- **Owner Action Required:** Review `ops/inventory.md` and approve M0-01 gate; approve destination medium for M0-06 backup before collector or data touching begins.
