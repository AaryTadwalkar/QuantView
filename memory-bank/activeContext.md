# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-26)
- **Stage 2 In Progress — Tasks M2-01, M2-02, M2-06 Completed & Tested (100% PASS):**
  - **Task M2-01 (REST Raw-First Snapshot Collector):** `RawSnapshotWriter`, `UpstoxSnapshotAdapter`, and `SnapshotCollectorService` implemented. Guarantees raw byte gzip + fsync durability and companion manifest before parsing. 100% raw preservation on decoder parse errors. Evidence: [`ops/evidence/M2-01.md`](file:///c:/Algo/quantview/ops/evidence/M2-01.md).
  - **Task M2-02 (Snapshot REST Rate-Limit Budget & Priority):** `RateBudgetManager` in `packages/data/budget.py`. Configurable quotas (3 req/sec, 150 req/min), high-priority snapshot reservation, market-hours backfill pausing, 429 adaptive cooldown. Evidence: [`ops/evidence/M2-02.md`](file:///c:/Algo/quantview/ops/evidence/M2-02.md).
  - **Task M2-06 (Pre-Market Token Check & Dead-Man Heartbeat):** `TokenManager` (native JWT parsing, 08:45 AM check, `WAITING_FOR_TOKEN` transition), `HeartbeatMonitor` (atomic fsync pulses in `Data/raw/telemetry/`, lag $\le 60\text{s}$ alerts), and CLI tool `tools/ops/check_token_readiness.py`. Evidence: [`ops/evidence/M2-06.md`](file:///c:/Algo/quantview/ops/evidence/M2-06.md).
- **Active Lake & Historical Foundation (Stage 1 Closed):** 784 Parquet files, Manifest v3 active, 8 DuckDB views active ($\le 50\text{ms}$).
- **Automated Verification:** 88/88 automated unit tests PASS in 2.20s. `tools/qv_check.py lint DOCS` PASS (0 defects). `ops/verify_docs_consistency.py` PASS (0 defects). Package boundaries 100% clean.
- **Next Step:** Task M2-03 (WebSocket raw segment writer) and Task M2-04 (V3 Protobuf decoder scaffold).

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
