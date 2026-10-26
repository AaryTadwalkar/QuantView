# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-26 — Stage 2 Closed & Gate G0 Certified PASS)
- **STAGE 2 IS 100% COMPLETE & GATE G0 CERTIFIED PASS:**
  - All 11 Stage 2 milestones (`M2-01` through `M2-11`) are fully implemented, verified, and audited with zero defects.
  - Formal Gate G0 closure reports published:
    * [`reports/stage2_closure/gate_g0_audit_report.md`](file:///c:/Algo/quantview/reports/stage2_closure/gate_g0_audit_report.md)
    * [`reports/stage2_closure/stage2_collector_audit.md`](file:///c:/Algo/quantview/reports/stage2_closure/stage2_collector_audit.md)
  - Complete evidence reports delivered in [`ops/evidence/`](file:///c:/Algo/quantview/ops/evidence/) (`M2-01.md` through `M2-11.md`).
- **DELIVERABLES COMPLETED & AUDITED:**
  - `M2-01` to `M2-06`: Live WebSocket streaming, V3 Protobuf decoder, ATM discovery, single-owner lease, REST snapshot collection, 08:45 pre-market gate, dead-man heartbeat telemetry. Tested live on 2026-10-26 (134,003 ticks, 86 snapshots).
  - `M2-07`: `services/backfill/service.py` (`ExpiredOptionBackfillService`, `BackfillCheckpointManager`) with rate budgeting and atomic checkpoints.
  - `M2-08`: `ops/session-day-runbook.md` with complete 08:45-16:00 SOP, systemd units, and failure playbooks.
  - `M2-09`: `tests/integration/test_collector_fault_injection.py` verifying fail-closed state across disk full, clock skew, duplicate lease, crash recovery, and token expiry.
  - `M2-10`: `tools/lake/measure_feed_volume.py` and `reports/feed-volume.md` measuring 6.86:1 compression ratio, 7 ticks/sec, ~34.8 MB/session, and 512 GB SSD hardware headroom (> 2.5 yrs retention).
  - `M2-11`: `ops/host_provisioning_runbook.md` and `tools/ops/sync_production_to_research.py` with unidirectional read-only pull and SHA-256 verification (no write-back path).
- **TEST SUITE & CODE QUALITY VERIFIED:**
  - **127/127 automated unit and integration tests PASS** in 9.86s.
  - `tools/qv_check.py lint DOCS` PASS (0 defects).
  - `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
- **NEXT PHASE:** Stage 3 (Data Audit & Canonical Lake Foundation) will be planned and initiated in the next session.

## Canonical Architectural Contracts & Modes
- **Operating Modes:** `RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`.
- **Allocation Modes:** `ISOLATED`, `PORTFOLIO` (`ADR-038`).
- **Causal Availability Model:** `available_at = bar_end` under `HISTORICAL_ASSUMED_AVAILABILITY` for backtests; `available_at = finalized_at = bar_end + grace_period` in live streams. Invariant: `feature.available_at <= decision_time`.
- **Risk Catalogue (`RK-01–RK-26`):** `RK-06` (hard freeze limit) vs `RK-26` (advisory lot ceiling).
- **Release Gates:** Gate G0 (Collectors: PASS), Gate G1 (Data Foundation: PASS), Phase 7 `GATE-04` ($\ge 10$ paper sessions) vs Phase 9 `GATE-05` ($\ge 30$ paper sessions, $\le 1\text{ paise}$ fee reconciliation, live capital authorization).

## 4-Tier Document Hierarchy (`ADR-007`, `SOURCE_OF_TRUTH_INDEX.md`)
1. **Tier 1 (Authority):** `ADR_REGISTER.md` (`ADR-001–ADR-041`, where `status == OWNER_APPROVED`).
2. **Tier 2 (System Contract):** `HIGH_LEVEL_DESIGN.md` (`P1–P18`, `L0–L7`, `G0.1–G7.9`, `GATE-01–GATE-05`).
3. **Tier 3 (Build Contract):** `LOW_LEVEL_DESIGN.md` (`RK-01–RK-26`, `CAP-01–CAP-24`, `B1–B6`, `T0.1–T9.2`).
4. **Tier 4 (Specialized Contracts):** `CHARTING_UX.md`, `BACKTESTING_REPORT_SPEC.md`, `OPTIONS_CHAIN_UI.md`, `PAPER_TRADING_UI.md`.
5. **Cross-Cutting Controls:** `TRACEABILITY_MATRIX.md`, `RECONCILIATION_AND_CHANGE_LOG.md`, `UNRESOLVED_DECISIONS_REGISTER.md`, `SOURCE_OF_TRUTH_INDEX.md`, `VALIDATION_REPORT.md`.