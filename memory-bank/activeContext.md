# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-26 — Market Session Close & Post-Market Audit PASS)
- **POST-MARKET SESSION CLOSURE & RECONCILIATION VERIFIED PASS:**
  - Market closed cleanly at 15:35 Asia/Kolkata. All collector processes safely stopped.
  - Executed automated forensic session reconciliation (`reconcile_session_directory('2026-10-26')`): Status = `PASS`, 0 unmatched segments, 0 orphan files, 0 checksum errors.
  - Final session partial cleanly recovered and rotated to `.bin.gz` with cryptographic companion manifest.
- **RECORDED MARKET DATA TOTALS FOR 2026-10-26:**
  - **Live WebSocket Ticks**: 5 finalized compressed segments containing **134,003 decoded quotes** across Nifty 50 and active ATM $\pm 5$ option strikes with complete depth, volume, OI, and Option Greeks.
  - **Full Option Chain Snapshots**: **86 complete option chain snapshots** (144 strikes each = 24,768 CE/PE rows) durably persisted in `Data/raw/upstox_rest/snapshots/trade_date=2026-10-26/`.
- **OPERATIONAL TOOLING STATUS:**
  - `tools/ops/dump_ws_segment.py`: Chronological sorting, full contract metadata enrichment (`trading_symbol`, `strike_price`, `option_type`, `expiry`), underlying Nifty 50 spot tracking (`underlying_spot_ltp`), all Option Greeks, market depth, and day/1m candle OHLC.
  - `tools/ops/dump_snapshot.py`: Decompresses raw snapshots into terminal ladders or canonical Version 3 CSV.
  - `tools/ops/run_collector_ws.py` & `tools/ops/run_collector_snapshot.py`: Built-in auto-shutdown at 15:35 IST active and verified.
- **TEST SUITE & CODE QUALITY VERIFIED:**
  - 118/118 automated unit tests PASS (3.43s).
  - `tools/qv_check.py lint DOCS` PASS (0 defects).
  - `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
- **Next Step:** Stage 2 Task M2-07 (Post-market reconciliation and ingestion into historical lake).

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