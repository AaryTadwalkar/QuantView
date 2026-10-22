# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-22)
- **Approved Decisions (OWNER-DEC-01 to 06):** Formally logged in `ops/owner_decisions.md`.
- **M0 & M1 Milestones Cleared (VERIFIED):**
  - `M0-01` (inventory), `M0-06` (backup verification), `M0-08` (sandbox restore), `M0-07` (retention probe), `M0-11` (contracts).
  - `M1-01` (repository layout across 19 directories), `M1-02` (tooling, CI workflow, failure tests, `ops/evidence/M1-02.md`).
- **Complete Historical Ingestion & Staging (Horizon: 2025-01-01 to 2026-10-19):**
  - **NIFTY Option Candles (446 sessions):** 20,332,421 bars (3.43 GB staged CSVs). 0 nulls, 0 duplicates, 100% sorted ascending. 32,232 manifests in `Data/raw/` with 0 SHA mismatches.
  - **India VIX Candles (`NSE_INDEX|India VIX`):** 100% backfilled across `2025-01-01` to `2026-10-19`.
    * **1-Minute Series:** 166,939 continuous bars across all 446 sessions (`staging/india_vix/`). 0 nulls, 0 dups, 0 OHLC violations, `oi=0`.
    * **Daily Series:** 446 daily bars matching 1:1 with option sessions (`staging/india_vix/`).
    * **Raw Wire Provenance:** 25 raw gzipped payloads and SHA-256 manifests archived in `Data/raw/upstox_rest/historical_candle/instrument=NSE_INDEX_India_VIX/`.
  - **Underlying Candles (`NSE_INDEX|Nifty 50`):** 435,592 1m bars + 1,417 1d bars staged & audited.
- **Next Steps:**
  1. Phase 1: Tooling Scaffolding (`tools/lake/schema.py`, promotion scripts for options, underlying, VIX, snapshots).
  2. Phase 2: Compaction & Staging Lake Preparation (`staging/lake_preparation/`).
  3. Phase 3: Canonical Parquet Lake Promotion & DuckDB View Registration (`v_candles_underlying`, `v_candles_options`).

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
