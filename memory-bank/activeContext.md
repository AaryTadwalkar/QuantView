# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-17)
- **Completed M0-10 & M0-01:** Executed bootstrap verification M0-10 (`ops/evidence/M0-10.txt`) and complete read-only repository/data inventory M0-01 (`ops/inventory.md`).
- **Core Findings & Discrepancies:**
  - **Data Volume:** 2,032.60 MB across 78,607 files in `Data/`. No Parquet, DuckDB, or SQLite databases exist.
  - **Snapshot Count:** Exactly 78,535 files across 121 unique trading days (v1: 1,036; v2: 8,770; v3: 68,720; 5 null-byte corrupted; 4 zero-byte empty).
  - **1m Underlying Candles:** `nifty.csv` has 432,967 rows (spec §11.6 said 451,952; the remaining 18,985 rows are in 57 live daily files). One corrupted line at line 432593 (`2026-10-08 0`).
  - **Backup Status:** **CRITICAL** — Zero backup on secondary physical medium. Drive C: has 67.83 GB free.
  - **Collector Health:** Zero active background collectors/services. Collector scripts contain path arithmetic and stale path bugs.
- **Readiness Verdicts:** Architecture: 8.5/10 | Docs: 8.5/10 | Technical Correctness: 6.5/10 (Runtime Unproven).

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
