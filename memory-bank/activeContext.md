# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-15)
- **Completed Baseline:** QuantView v1.4 Hardened Implementation Baseline (`v1.4`, `Release Date: 2026-10-12`) across all 12 canonical documents in `c:\Algo\quantview\DOCS\final\`.
- **Readiness Verdicts:**
  - **Architecture Quality:** `8.5 / 10` (Modular monolith, hybrid PostgreSQL + Parquet/DuckDB storage, 5-layer isolation).
  - **Documentation Completeness:** `8.5 / 10` (Full coverage across tiers, schemas, APIs, tickets, tests).
  - **Verified Technical Correctness:** `6.5 / 10` (`Runtime Unproven` — `Implementation Status = PENDING`, `Test Execution Status = NOT_RUN`).
  - **Ready for Phase 0 (`T0.1–T0.15`):** **`GO`** (Repository scaffolding, raw data audit, empirical verification scripts).
  - **Ready for Full Build (`Phases 1–8`):** **`CONDITIONAL GO`** (Gated on `UNVERIFIED_BLOCKER` items `VER-01–06`, `S1–12`, checkpoints `REV-01–04`; includes safe Phase 1 vertical slice `T1.7`).
  - **Ready for Live Execution (`Phase 9`):** **`NO-GO`** (Requires $\ge 30$ paper sessions, $\le 1\text{ paise}$ zero-drift fee reconciliation across $\ge 5$ contract notes, 3-lock live arming, `readiness_signed.yaml`).

## Canonical Architectural Contracts & Modes
- **Operating Modes:** `RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`.
- **Allocation Modes:** `ISOLATED`, `PORTFOLIO` (`ADR-038`). Ambiguous "Mode A/B" labels retired.
- **Causal Availability Model:** `available_at = bar_end` under `HISTORICAL_ASSUMED_AVAILABILITY` for backtests; `available_at = finalized_at = bar_end + grace_period` in live streams. Invariant: `feature.available_at <= decision_time`.
- **Risk Catalogue (`RK-01–RK-26`):** `RK-06` (`HARD_ORDER_FREEZE_LIMIT`, pre-submit hard block) split from `RK-26` (`ADVISORY_ORDER_LOT_CEILING`, non-blocking advisory in manual paper).
- **Release Gates:** Phase 7 `GATE-04` ($\ge 10$ paper sessions; paper engine evaluation only) vs Phase 9 `GATE-05` ($\ge 30$ paper sessions, $\le 1\text{ paise}$ fee reconciliation, live capital authorization).
- **Phase 1 Vertical Slice (`T1.7`):** Minimal feature engine, deterministic underlying strategy, causal backtest, run manifest, reproducible report, `T-ACC-1`; zero broker or option dependencies.
- **Order Safety:** Manual orders market-only in v1; LIMIT orders deferred post-v1 (`ADR-039`); `EXPIRY_UNRESOLVED` handles ambiguous settlements without inventing prices.

## 4-Tier Document Hierarchy (`ADR-007`, `SOURCE_OF_TRUTH_INDEX.md`)
1. **Tier 1 (Authority):** `ADR_REGISTER.md` (`ADR-001–ADR-041`, where `status == OWNER_APPROVED`).
2. **Tier 2 (System Contract):** `HIGH_LEVEL_DESIGN.md` (`P1–P18`, `L0–L7`, `G0.1–G7.9`, `GATE-01–GATE-05`).
3. **Tier 3 (Build Contract):** `LOW_LEVEL_DESIGN.md` (`RK-01–RK-26`, `CAP-01–CAP-24`, `B1–B6`, `T0.1–T9.2`).
4. **Tier 4 (Specialized Contracts):** `CHARTING_UX.md`, `BACKTESTING_REPORT_SPEC.md`, `OPTIONS_CHAIN_UI.md`, `PAPER_TRADING_UI.md`.
5. **Cross-Cutting Controls:** `TRACEABILITY_MATRIX.md`, `RECONCILIATION_AND_CHANGE_LOG.md`, `UNRESOLVED_DECISIONS_REGISTER.md`, `SOURCE_OF_TRUTH_INDEX.md`, `VALIDATION_REPORT.md` (+ `validation_evidence.json`).
- **Historical Sources (`DOCS/person_1/`, `DOCS/person_2/`):** 10/10 files preserved byte-identical; never implement from.
- **Recent Corrections (2026-10-12):** Completed HLD v1.5.1 targeted corrections in `DOCS/HIGH_LEVEL_DESIGN (1).md` per `DOCS/HLD_MANUAL_CORRECTION_GUIDE.md` (Patches 2B–6 applied).
- **Next Step:** Ready to begin Phase 0 (`T0.1` Archive legacy data with manifest).

## 2026-10-15 — Final Specification Repair & Alignment Pass
- **Completed:** Executed the bounded repair pass and subsequent 7-item surgical text alignment across all 4 canonical documents (`DOCS/QUANTVIEW_DATA_SPEC.md`, `DOCS/QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md`, `DOCS/QUANTVIEW_MASTER_SPEC.md`, and `DOCS/AGENTS.md`).
- **Key Alignments Applied:**
  1. *MASTER:* Replaced hardcoded Windows path with Linux/WSL2 repo root per ADR-015 in Architectural Non-Negotiables.
  2. *DATA & AGENTS:* Standardized `chart_drawings` table name, `('HORIZONTAL_LINE', 'VERTICAL_LINE', 'TREND_LINE', 'RECTANGLE')` enum, and `/api/v1/charts/drawings` endpoint.
  3. *ENGINE & AGENTS:* Aligned UI-3 endpoint paths to `/api/v1/option-chain`, `/api/v1/option-chain/metrics`, `/api/v1/charts/layouts`.
  4. *RunConfig Schema:* Added `FIXED_RISK_INR`, `risk_inr_paise`, and `max_stale_minutes: 5` default in ENGINE §19.1.
  5. *Gates & Skeleton:* Appended `M2-08..M2-10` to Gate G0; explicitly added `packages/db` to `M1-01`; documented custom day bounds in §4 (109 tasks, 258.5 person-days).
  6. *Traceability Citations:* Aligned V-01 (React+Vite SPA), V-08/11 (DATA §3, ENGINE §2, §18.3 UtcEpochSec), V-15/16/17 (DATA §4.1–§4.4, §11.1–§11.2), and ADR references across V-21, V-26, V-27, V-29, V-31, V-33.
- **Verification Result:** Automated mechanical test suite `verify_docs.py` passed with 0 errors.
- **Next Step:** Awaiting owner go-ahead to execute M0-10 (`python` verification check to `ops/evidence/M0-10.txt`) and M0-01 (read-only inventory to `ops/inventory.md`).


