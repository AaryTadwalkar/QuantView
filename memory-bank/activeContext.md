# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-26 — Live WS Dry-Run & Snapshot Verification PASS)
- **LIVE WEBSOCKET DRY-RUN VERIFIED PASS:**
  - Upstox V3 auth endpoint updated to `https://api.upstox.com/v3/feed/market-data-feed/authorize`.
  - Discovered and integrated official Upstox V3 Protobuf schema (`MarketDataFeedV3.proto`) with full support for `IndexFullFeed`, `MarketFullFeed`, `FirstLevelWithGreeks`, and `LTPC`.
  - Executed live dry run: connected, acquired `SingleOwnerLease`, streamed live Nifty 50 tick (LTP: 22,648.30, CP: 22,600.00), durably persisted `.bin.gz` segment + companion manifest, decoded quotes, and cleanly released lock. Result: `DRY-RUN RESULT: PASS`.
- **LIVE OPTION CHAIN SNAPSHOT VERIFIED PASS:**
  - Verified `SnapshotCollectorService` and created CLI runner `tools/ops/run_collector_snapshot.py`.
  - Captured live full option chain (144 strikes, CE & PE with LTP, volume, OI, bid/ask depth, and full Option Greeks: IV, Delta, Theta, Gamma, Vega, POP).
  - Durably persisted raw gzip (17,025 bytes) and companion manifest to `Data/raw/upstox_rest/snapshots/`.
- **OPERATIONAL TOOLS DELIVERED:**
  - `tools/ops/dump_ws_segment.py`: Inspects and exports binary WebSocket segment files (.bin.gz) into terminal tables or CSV.
  - `tools/ops/run_collector_snapshot.py`: Captures on-demand or periodic live full option chain snapshots.
- **Stage 2 In Progress — Tasks M2-01 through M2-06 100% Tested & Verified:**
  - 118/118 automated unit tests PASS in 3.46s. `tools/qv_check.py lint DOCS` PASS (0 defects). `ops/verify_docs_consistency.py` PASS (0 defects). Active Lake remains immutable.
- **Next Step:** Live continuous collection during market session and Tasks M2-07 through M2-11.

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
