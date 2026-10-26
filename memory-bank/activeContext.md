# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-26 — Updated after .env token fix)
- **BUG FIX APPLIED:** `tools/ops/run_collector_ws.py` line 104 changed from `os.environ.get("UPSTOX_ACCESS_TOKEN", "")` to `os.environ.get("UPSTOX_ACCESS_TOKEN") or None`. This ensures `TokenManager._discover_token()` auto-reads `.env` when no explicit CLI token or shell env var is set. 117/117 tests PASS. `check_token_readiness.py` confirmed VALID.
- **Stage 2 In Progress — Tasks M2-01, M2-02, M2-03, M2-04, M2-05, M2-06 Completed & Tested (100% PASS):**
  - **Task M2-01 (REST Raw-First Snapshot Collector):** `RawSnapshotWriter`, `UpstoxSnapshotAdapter`, and `SnapshotCollectorService`. Guarantees raw byte gzip + fsync durability and companion manifest before parsing. Evidence: [`ops/evidence/M2-01.md`](file:///c:/Algo/quantview/ops/evidence/M2-01.md).
  - **Task M2-02 (Snapshot REST Rate-Limit Budget & Priority):** `RateBudgetManager` in `packages/data/budget.py`. Configurable quotas (3 req/s, 150 req/min), high-priority snapshot reservation, market-hours backfill pausing. Evidence: [`ops/evidence/M2-02.md`](file:///c:/Algo/quantview/ops/evidence/M2-02.md).
  - **Task M2-03 (WebSocket Raw Segment Writer):** `RawSegmentWriter` and `framing.py` in `services/collector_ws/`. Binary envelope (`QVWS` magic + CRC32), batched fsync (loss window $\le 1\text{s}$), rotation, companion manifests, crash recovery (`recover_session_partials`). Evidence: [`ops/evidence/M2-03.md`](file:///c:/Algo/quantview/ops/evidence/M2-03.md).
  - **Task M2-04 (SubscriptionManager & Single-Owner Lease):** `SingleOwnerLease` (exclusive OS file lock, duplicate instance aborts closed) and `SubscriptionManager` (dynamic multi-source set union, feed mode hierarchy, quota guards, V3 JSON wire commands). Evidence: [`ops/evidence/M2-04.md`](file:///c:/Algo/quantview/ops/evidence/M2-04.md).
  - **Task M2-05 (WebSocket Client Lifecycle & V3 Protobuf Decoder):** `UpstoxWebSocketClient` (end-to-end async lifecycle, auto-reconnect, raw-first persistence), `WsQuoteDecoder` (`MarketDataFeedV3.proto` unmarshaling, Greeks/depth/OHLC mapping, `ZERO_DEPTH`/`NON_OPTION_OI` flags, scaffolded safeguard), and CLI runner `tools/ops/run_collector_ws.py`. Evidence: [`ops/evidence/M2-05.md`](file:///c:/Algo/quantview/ops/evidence/M2-05.md).
  - **Task M2-06 (Pre-Market Token Check & Dead-Man Heartbeat):** `TokenManager` (native JWT parsing, 08:45 AM check, `WAITING_FOR_TOKEN` transition), `HeartbeatMonitor` (atomic fsync pulses in `Data/raw/telemetry/`), and CLI tool `tools/ops/check_token_readiness.py`. Evidence: [`ops/evidence/M2-06.md`](file:///c:/Algo/quantview/ops/evidence/M2-06.md).
- **Active Lake & Historical Foundation (Stage 1 Closed):** 784 Parquet files, Manifest v3 active, 8 DuckDB views active ($\le 50\text{ms}$).
- **Automated Verification:** 117/117 automated unit tests PASS in 3.04s. `tools/qv_check.py lint DOCS` PASS (0 defects). `ops/verify_docs_consistency.py` PASS (0 defects). Package boundaries 100% clean. Active Lake unmodified.
- **Next Step:** **Run the dry-run** (`.\venv\Scripts\python.exe tools/ops/run_collector_ws.py --instruments "NSE_INDEX|Nifty 50" --mode full --dry-run`) to capture 1 live frame and confirm pipeline end-to-end. After that: live session recording (2 representative sessions for decoder certification) and Tasks M2-07 through M2-11.

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
