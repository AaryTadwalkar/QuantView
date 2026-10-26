# Progress — QuantView (`c:\Algo\quantview`)

## Completed Milestones
- **[2026-10-11] Stage A — Pre-Edit Inspection, Comparison & Reconciliation Matrix:**
  - Read all 10 source Markdown files across `DOCS/person_1/` and `DOCS/person_2/` in full and recorded baseline SHA-256 hashes.
  - Identified and presented the 6 material architectural questions (`Q1–Q6`) to the owner; owner approved all 6 with explicit constraints.
- **[2026-10-11] Stage B — Reconciled Final Documentation Baseline (`DOCS/final/`):**
  - Created all 12 required deliverables (`A` through `I`) in `c:\Algo\quantview\DOCS\final\`.
- **[2026-10-11] Documentation Audit Correction Pass (`v1.3`, `BLK-01` – `BLK-06`):**
  - Unified all 12 files to `v1.3` and `2026-10-11`; established 4-Tier Document Hierarchy + 6 Conflict Rules (`ADR-007`).
  - Added `ADR-039`, `ADR-040`, `ADR-041`, worked 2-lot integer-paise financial fixture (`LLD §8.5.4`), 6-boundary crash matrix (`B1–B6`), and `UNVERIFIED_BLOCKER` enforcement.
- **[2026-10-12] Documentation Hardening & Implementation Gate Baseline (`v1.4`, `REC-24` – `REC-30`):**
  - Unified all 12 files in `DOCS/final/` to **`Version: v1.4 (Hardened Implementation Baseline)`** and **`Release Date: 2026-10-12`**.
  - Established canonical operating modes (`RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`) and allocation modes (`ISOLATED`, `PORTFOLIO`).
  - Clarified causal availability: `available_at = bar_end` under `HISTORICAL_ASSUMED_AVAILABILITY` for backtests; `available_at = finalized_at = bar_end + grace_period` in live streams.
  - Disambiguated Risk Rules into canonical catalogue `RK-01` through `RK-26`, cleanly splitting `RK-06` (hard freeze limit) and `RK-26` (advisory lot ceiling).
  - Clarified release gates: Phase 7 `GATE-04` ($\ge 10$ paper sessions; paper evaluation only) vs Phase 9 `GATE-05` ($\ge 30$ paper sessions, $\le 1\text{ paise}$ zero-drift fee reconciliation across $\ge 5$ contract notes, live capital authorization).
  - Defined safe Phase 1 deterministic vertical slice backtest runner (`T1.7`) with zero broker or option-chain dependencies.
  - Programmatically verified 0 broken links, 12/12 header checks, 100% ID alignment (`P1–P18`, `ADR-001–ADR-041`, `CAP-01–CAP-24`, `RK-01–RK-26`), 10/10 untouched source hashes, and exact integer-paise fixture math (`validation_evidence.json`).
- **[2026-10-15] 4-Document Final Specification Repair Pass & Mechanical Validation:**
  - Applied bounded repair pass across all 4 canonical specifications (`QUANTVIEW_DATA_SPEC.md`, `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md`, `QUANTVIEW_MASTER_SPEC.md`, `AGENTS.md`) per `QuantView_Final_Repair_Prompt.md`.
  - Added System Architecture Overview to MASTER; added PostgreSQL operational schema and `prev_oi` to DATA; standardized routes to `/api/v1/`; corrected Bailey & López de Prado DSR math and added deterministic BOS/CHoCH algorithm to ENGINE; completed RunConfig schema and UI-3 contracts.
  - Expanded task registry in `AGENTS.md` from 95 tasks (233.5 person-days) to 109 unique tasks (258.5 upper-bound person-days) with 0 graph cycles; added full `V-01` to `V-35` Vision Traceability Matrix.
  - Automated mechanical validation suite (`verify_docs.py`) passed 100% checks with 0 errors.
- **[2026-10-17] M0-10 & M0-01 — Bootstrap Verification & Read-Only Data/Repository Inventory:**
  - Verified `DOCS/AGENTS.md` bootstrap integrity contract (`ops/evidence/M0-10.txt`).
  - Completed comprehensive read-only audit across 86,647 files (~2.21 GB) in `c:\Algo\quantview`.
  - Audited historical index candles (432,967 1m rows + 18,985 live daily rows = 451,952 total; discovered truncated line 432593 `'2026-10-08 0'`).
  - Audited 78,535 live option chain snapshots across 121 unique trading days and 35 expiries; classified into v1 (1,036), v2 (8,770), v3 (68,720), 5 null-byte corrupted, and 4 zero-byte empty files.
  - Delivered exhaustive inventory deliverable: `ops/inventory.md`.
- **[2026-10-20] Ingestion Tooling, M0 Gate Clearances, Smoke Test & Phase A Probe (OWNER-DEC-01 to 06):**
  - Accepted refreshed M0-01 inventory with 3,748 PC B snapshots (82,283 captures across 127 days; 82,355 files, 2,131.18 MB).
  - Executed M0-06 secondary backup verification against `D:\Algo_Data_Final\Data` on `Cablet USB 3.0` (`ops/evidence/M0-06.md`).
  - Executed M0-08 isolated restore verification with 100% SHA-256 match (`ops/evidence/M0-08.md`).
  - Executed M0-07 bounded 7-request retention probe respecting strict budget without credential leaks (`ops/evidence/M0-07.md`).
  - Delivered M0-11 acceptance contract refinements for M0-02 through M0-09 (`ops/evidence/M0-11.md`).
  - Executed single authenticated smoke test (`OWNER-DEC-05`): `GET /v2/expired-instruments/option/contract` for `2025-04-24` returned HTTP 200 OK with 232 contracts.
  - Executed Phase A retention investigation (`OWNER-DEC-06`): Dispatched 12 authorized read-only requests. `2024-12-26` returned 281 contracts (HTTP 200); `2024-06-27` to `2019-06-27` returned 0 contracts (HTTP 200). Retention cliff confirmed between 2024-06-27 and 2024-12-26 (~1.8–2.3 years retention).
  - Completed Milestone `M1-01` (`VERIFIED`, `ops/evidence/M1-01.md`): Scaffolding across 19 deliverable directories (`packages/*`, `services/*`, `apps/web`, `config`).
  - Completed Milestone `M1-02` (`VERIFIED`, `ops/evidence/M1-02.md`): Tooling configs (`pyproject.toml`, `.importlinter`, `requirements-ci.txt`), CI pipeline (`.github/workflows/ci.yml`), intentional failing fixture suite (`tests/unit/test_ci_failure_mode.py`).
  - Hardened option candle importer (`tools/ingest/import_expired_option_candles.py`) with atomic `.tmp` staging, Content-Type recording, safe null handling, and offline contracts loading.
  - Sized full option history backfill (Dec 2024 – Oct 2026, 23 expiries, 460 sessions, ~2,760 contracts, ~3,194 requests) in `reports/option_history_acquisition_plan.md`.
  - Refuted earlier 98.7% liquidity claim: empirical measurement on 2025-04-24 reveals 91.58% for $\pm 1,000$ vs 95.91% for $\pm 1,500$.
  - 35/35 unit tests passing in 1.68s; `tools/qv_check.py lint` PASS (0 defects); `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks A–M).

## Implementation & Readiness Status (`Appendix C` of `LOW_LEVEL_DESIGN.md`)
- **M0 Tasks Completed:** `M0-10` (`TESTED`), `M0-01` (`VERIFIED`), `M0-06` (`VERIFIED`), `M0-07` (`VERIFIED`), `M0-08` (`VERIFIED`), `M0-11` (`IMPLEMENTED`).
- **M1 Tasks Completed:** `M1-01` (`VERIFIED`), `M1-02` (`VERIFIED`).
- **All Capabilities (`CAP-01` – `CAP-24`):** `Design Status = DESIGNED`, `Implementation Status = PENDING`, `Test Execution Status = NOT_RUN`.
- **Readiness Verdicts:** **Phase 0 (`T0.1–T0.15`):** `GO` | **Full Build (`Phases 1–8`):** `CONDITIONAL GO` | **Live Execution (`Phase 9`):** `NO-GO`.
- **Option Ingestion Pipeline & Complete Daily Historical Backfill (2025-01-01 to 2026-10-19, 446 Trading Days - 100% Complete):**
  - Consolidated all bulk range backfill, pre-flight verification, and auditing capabilities directly into canonical `tools/ingest/import_expired_option_candles.py`.
  - **Batch 1 (`2025-01-01` to `2025-06-19`):** 116 sessions, 5,118,315 bars, 861.76 MB staged CSVs, 6,106 manifests (`reports/historical_options_2025_h1_audit_report.md`).
  - **Batch 2 (`2025-06-20` to `2026-02-03`):** 156 sessions, 7,003,462 bars, 1,178.30 MB staged CSVs, 10,510 manifests (`reports/historical_options_20250620_20260203_audit_report.md`).
  - **Batch 3 (`2026-02-04` to `2026-10-19`):** 174 sessions, 8,210,644 bars, 1,385.49 MB staged CSVs, 15,616 manifests (`reports/historical_options_20260204_20261021_audit_report.md`).
  - **Grand Total Ingestion:** **446/446 trading sessions** verified `PASS` (100.0%).
  - Staged **20,332,421 continuous 1-minute option candle bars** across **3,425.55 MB (3.43 GB)** in 446 separate daily CSV files (`staging/expired_options/nifty_options_1m_{expiry}_{trade_date}.csv`).
  - 100% data integrity verified: **0 duplicates**, **0 null values**, strictly sorted **chronologically ascending (`09:15:00` to `15:29:00`)**.
  - Cryptographic provenance verified: **32,232 companion JSON manifests** and raw gzip payloads in `Data/raw/upstox_rest/expired_api/` verified bit-for-bit (0 SHA-256 mismatches across 383.41 MB compressed).
  - All 446 daily trading sessions verified valid and ready for canonical Lake Parquet publishing.
- **Phase 1 Tooling Scaffolding & Canonical Lake Validation (2026-10-22 - COMPLETE):**
  - Delivered exhaustive Pre-Implementation Compliance Report (`reports/phase1_tooling_compliance_report.md`).
  - Integrated canonical schemas as single source of truth in `packages/data/schemas/` (`candles.py`, `snapshots.py`, `__init__.py`). Prohibited duplicate schemas avoided.
  - Implemented offline tooling scaffolding under `tools/lake/`:
    * `promote_option_candles.py`: Vectorized PyArrow table builder with exact Decimal(9, 2) strikes and negative-volume clamping (`VENDOR_NEGATIVE_VOLUME`).
    * `promote_underlying_candles.py`: Line 432594 (`TRUNCATED_LINE`) defensive quarantine, interval partitioning (`1m` monthly, `1d` yearly).
    * `promote_india_vix.py`: Non-derivative index invariants (`oi=0`, `is_derivative=False`), session-by-session reconciliation (`reports/india_vix_session_coverage_report.json`).
    * `compact_option_snapshots.py`: Daily Parquet compaction preserving discrete capture identity (`captures` and `rows` tables) without synthetic chain merging.
    * `prepare_dry_run_manifest.py`: Cryptographic dry-run manifest generator (`staging/lake_preparation/manifest_dry_run.json`).
  - Implemented automated test suite (`tests/unit/test_lake_scaffolding.py`): 16/16 tests passing in 0.92s.
  - Staged 38 sample partitions (1,176,311 rows, 15.65 MB) in `staging/lake_preparation/` and produced dry-run manifest (`staging/lake_preparation/manifest_dry_run.json`).
  - Active lake `Data/lake/` remains 100% UNPUBLISHED and isolated pending owner review.
- **[2026-10-23] Post-Incident Folder Audit & Phase 1 Verification Re-run (COMPLETE):**
  - **Recycle Bin & Folder Audit:** Audited all 6 items in Recycle Bin screenshot (`config`, `apps`, `.github`, `__pycache__`, and 2 copies of `underlying_NSE_INDEX_India_VIX_1d_...csv`). Verified they are already 100% restored and up-to-date in repository via `git reset` and manual restoration. Restoring from Recycle Bin is NOT required.
  - **Comprehensive Folder Audit:** Audited all 14 workspace directories (`apps`, `config`, `Data`, `Data_Collectors`, `.github`, `DOCS`, `memory-bank`, `ops`, `packages`, `reports`, `services`, `staging`, `tests`, `tools`). `Data/` verified restored with 113,385 files (2,355.88 MB), including 82,290 live option chain snapshot files and full NIFTY historical candles (432,967 rows).
  - **Phase 1 Independent Verification Re-run (8/8 PASS):**
    1. Directory compliance: PASS (`tools/lake/` and `staging/lake_preparation/`).
    2. Canonical schema audit: PASS (`packages/data/schemas/` matches DATA Spec §4.1, §4.2, §4.3, §4.4, §4.10).
    3. India VIX semantics: PASS (Source preservation verified: volume is genuine 0, `oi=0`).
    4. Snapshot compaction status: PASS on real data (82,290 files, 127 sessions discovered in `Data/live/option_chain/nifty`; 3-session dry run validated 1,187 captures, 212,830 rows, 0 quarantined) + PASS on synthetic fixtures.
    5. Underlying candle integrity: PASS (`promote_underlying_candles.py` parses 435,591 1m rows + 1,417 1d rows; safely quarantines line 432594 with zero source mutation).
    6. India VIX session coverage: PASS (311-bar delta reconciled to the single bar; 0 fabricated bars).
    7. Promotion-tool correctness: PASS (Atomic writes, deterministic sort keys, provenance, 0 writes to `Data/lake/`).
    8. Full test suite execution: PASS (51/51 tests pass with 0 skipped, 0 failures, 0 errors in 1.42s).
  - **Phase 2 Gate Status:** Phase 2A and Phase 2B COMPLETE. Production Data Lake `Data/lake/` is active and queryable. Ready for Phase 3 (Snapshot Compaction).
- **[2026-10-23] Phase 2A — Full-Batch Staging Preparation & Closure Gate (COMPLETE - ALL 9 CHECKS PASS):**
  - Staged 183 Parquet files (20,936,814 rows, 225.06 MB) into isolated directory `staging/lake_preparation_phase2a/`.
  - Delivered comprehensive reports: `reports/phase2a_staging_report.md` and `reports/phase2a_closure_gate_evidence.json`.
- **[2026-10-23] Phase 2B — Production Data Lake Publication & Verification (COMPLETE - ALL PASS):**
  - Atomically published all 183 Parquet files (20,936,814 rows, 225.06 MB) to active production lake `Data/lake/`.
  - Activated official production manifest `Data/lake/manifest_active.json` (`is_active = true`, 183/183 SHA-256 bit-for-bit verified).
  - Registered canonical DuckDB views in `Data/lake/quantview.duckdb` (`v_candles_underlying`, `v_candles_options`, `v_candles_vix`).
  - Verified point-in-time analytical query benchmarks ($\le 36\text{ms}$, 0 daily bar leaks).
  - 51/51 automated unit tests PASS in 1.44s. Linter & consistency suite PASS (0 defects).
  - Delivered comprehensive report: `reports/phase2b_lake_publication_report.md`.
- **[2026-10-24] Phase 3 — Full Option Snapshot Compaction & Lake Publication (COMPLETE - ALL PASS):**
  - **Task M3-06 Satisfied:** Compacted full inventory of 82,283 option chain snapshot CSVs across 36 expiries and 126 sessions into canonical Parquet tables (`option_snapshot_captures` and `option_snapshot_rows`).
  - **100% Inventory-to-Disposition Reconciliation:** 82,274 valid captures + 9 quarantined files (4 0-byte empty + 5 null-byte corrupt) = 82,283 files. Discrepancy: exactly 0. Quarantines recorded in `staging/lake_preparation_phase3/quarantine/quarantine_report.json`.
  - **Canonical Schemas & Precision:** Exact `Decimal(9, 2)` strikes (`decimal128(9, 2)`), full IEEE-754 64-bit float observed Greeks, UTC microsecond timestamps (naive localized to `Asia/Kolkata` -> `UTC`), zero duplicate capture identities or strike keys.
  - **Staged Artifacts:** 252 Parquet partitions (17,528,006 rows, 381.21 MB) staged under `staging/lake_preparation_phase3/` and verified against `manifest_phase3.json`.
  - **Production Lake Publication & Manifest v2 Live:**
    * Atomically promoted 252 snapshot partitions to `Data/lake/option_snapshot_captures/` and `Data/lake/option_snapshot_rows/`.
    * Retained all 183 Phase 2B candle partitions byte-for-byte intact (0 SHA-256 mismatches).
    * Archived manifest v1 to `Data/lake/manifest_v1_archive.json`.
    * Activated manifest v2 at [`Data/lake/manifest_active.json`](file:///c:/Algo/quantview/Data/lake/manifest_active.json) (435 Parquets, 38,464,820 rows, 606.27 MB).
  - **DuckDB Canonical Views in `Data/lake/quantview.duckdb` (All 6 Active, All $\le 36\text{ms}$):**
    * `v_candles_underlying`: 437,008 rows | `v_candles_options`: 20,332,421 rows | `v_candles_vix`: 167,385 rows
    * `v_snapshots_captures`: 82,274 rows (23.99 ms)
    * `v_snapshots_rows`: 17,445,732 rows (26.09 ms)
    * `v_snapshots_reconstructed_chain`: 17,445,732 rows (19.30 ms)
  - **Tests & Linters:** 52/52 automated unit tests PASS in 1.58s. `tools/qv_check.py lint DOCS` PASS (0). `ops/verify_docs_consistency.py` PASS (0).
  - Delivered comprehensive reports: `reports/phase3_snapshot_compaction_report.md` and `reports/phase3_snapshot_validation_results.json`.
- **[2026-10-24] Phase 4 — Multi-Timeframe Derivation, Source-Semantics Audit & Eligibility Matrix (COMPLETE - ALL PASS):**
  - **Task M3-07 Satisfied (Multi-Timeframe Derivation):** Derived all 6 canonical intraday timeframes (`3m`, `5m`, `15m`, `30m`, `1h`, `4h`) from 1m canonical underlying candles. Session boundaries strictly enforced (09:15 to 15:30 Asia/Kolkata; zero bar spill across session boundary). Staged 348 Parquet partitions (287,306 rows, 13.72 MB). High-fidelity ground truth cross-validation against vendor CSVs: 4h (100.0%), 1h (99.99%), 15m (99.99%), 5m (99.89%), 3m (99.93%). Deliverable: `reports/derived_intervals_vendor_comparison.md`.
  - **Task M3-08 Satisfied (Source-Semantics Audit):** Audited all 6 semantic domains across active lake (option volume/OI, cash index volume, India VIX `oi=0` invariant, snapshot v1 vs v3 format, observed Greeks Black-Scholes units, WS session reset at 09:15:00 IST). Deliverable: `reports/source-semantics.md`.
  - **Task M3-09 Satisfied (Data Eligibility Matrix):** Evaluated all 1,161 historical trading sessions (2022 to 2026) against 9 canonical quality invariants (`MISSING_BARS`, `FLAT_BAR`, `STALE_DATA`, `INVALID_OHLC`, `DUPLICATE_ACTIVE_KEY`, `CONTRACT_INVALID`, `INSUFFICIENT_WARMUP`, `SOURCE_SEMANTICS_UNVERIFIED`, `INCOMPLETE_CAPTURE`). Staged Parquet dataset: `staging/lake_preparation_phase4/data_eligibility/part-0.parquet` (1,161 rows: 1,144 `ELIGIBLE`, 17 `ELIGIBLE_WITH_WARNINGS`, 0 `INELIGIBLE`). Deliverable: `reports/data_eligibility_report.md`.
  - **Phase 4 Manifest & Validation Suite:** Staged manifest `staging/lake_preparation_phase4/manifest_phase4.json` (349 files, 288,467 rows, 13.73 MB, SHA-256: `a6c348fac38b421b8c484069297937afcc89f7a45f69d22ebb6f7109be50a72b`). All 6 validation gates PASS (`reports/phase4_staging_validation_results.json`).
  - **Automated Verification:** 54/54 automated unit tests PASS in 1.60s. `tools/qv_check.py lint DOCS` PASS (0 defects). `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks). Active lake partitions remain 100% byte-for-byte immutable.
- **[2026-10-24] Phase 5 & Stage 1 Gate G1 Closure (COMPLETE - 100% PASS):**
  - **Stage 1 (Historical Data Foundation) Officially Closed:** Formally passed Gate G1 per `DOCS/AGENTS.md` §5. All 12 Stage 1 tasks (`M3-01` to `M3-12`) verified and certified with zero defects.
  - **Active Production Lake (`Data/lake/` - Manifest Version 3 Live):**
    * Promoted 349 Phase 4 Parquet partitions (`derived_candles` and `data_eligibility`) into `Data/lake/`.
    * Retained all 435 baseline candle and snapshot Parquets byte-for-byte immutable (0 SHA-256 mismatches).
    * Archived manifest v2 to `Data/lake/manifest_v2_archive.json`.
    * Activated manifest v3 at [`Data/lake/manifest_active.json`](file:///c:/Algo/quantview/Data/lake/manifest_active.json) (784 Parquets, 38,753,287 records, 620.00 MB).
  - **8 Canonical DuckDB Views in `Data/lake/quantview.duckdb`:**
    * `v_candles_underlying`: 437,008 rows | `v_candles_options`: 20,332,421 rows | `v_candles_vix`: 167,385 rows
    * `v_snapshots_captures`: 82,274 rows | `v_snapshots_rows`: 17,445,732 rows | `v_snapshots_reconstructed_chain`: 17,445,732 rows
    * `v_candles_derived`: 287,306 rows | `v_data_eligibility`: 1,161 rows
    * Point-in-time analytical query benchmarks all verified ($\le 50\text{ms}$).
  - **Tasks M3-10, M3-11, M3-12 Satisfied:**
    * Task M3-10: Parquet Profile & DuckDB Benchmarks (`ops/evidence/M3-10.md`).
    * Task M3-11: Exploratory Strategy Spike on 5m trend and 0-DTE straddle (`ops/evidence/M3-11.md`).
    * Task M3-12: Supporting Datasets Canonicalization (`ops/evidence/M3-12.md`).
  - **Audit Deliverables:** [`reports/gate_g1_audit_report.md`](file:///c:/Algo/quantview/reports/gate_g1_audit_report.md) and [`reports/gate_g1_validation_results.json`](file:///c:/Algo/quantview/reports/gate_g1_validation_results.json).
  - **Automated Verification:** 56/56 automated unit tests PASS in 3.16s. `tools/qv_check.py lint DOCS` PASS (0 defects). `ops/verify_docs_consistency.py` PASS (0 defects).
  - Next: Stage 2 — Live Market Stream & Collector Integration (`M2-01` to `M2-11`, Gate G0).
- **[2026-10-26] Stage 2 — Live Market Stream & Collector Integration (Tasks M2-01, M2-02, M2-03, M2-06 COMPLETE - ALL PASS):**
  - **Task M2-01 (REST Raw-First Snapshot Collector):**
    * Implemented `services/collector_snapshot/raw_writer.py` (`RawSnapshotWriter`, `RawCaptureRecord`) guaranteeing raw gzip write, hardware `fsync()`, and self-describing manifest before parsing.
    * Implemented `services/collector_snapshot/adapter.py` (`UpstoxSnapshotAdapter`) with exponential backoff + jitter on 429/5xx, fail-closed on 401/403, and token redaction.
    * Implemented `services/collector_snapshot/collector.py` (`SnapshotCollectorService`) with dynamic expiry resolution and fail-safe decoder isolation (100% raw byte retention on corrupt JSON).
    * Delivered 12 unit tests in `tests/unit/test_collector_snapshot.py` and evidence report [`ops/evidence/M2-01.md`](file:///c:/Algo/quantview/ops/evidence/M2-01.md) (`Status = TESTED`).
  - **Task M2-02 (Snapshot REST Rate-Limit Budget & Priority):**
    * Implemented `packages/data/budget.py` (`RateBudgetManager`, `BudgetConfig`, `RequestPriority`) with thread-safe sliding window tracking (1s and 60s).
    * Enforced market-hours detection (09:15-15:30 IST), snapshot capacity reservation, market-hours backfill pause/throttle interface, and adaptive 429 cooldown.
    * Re-exported cleanly from `packages/data/__init__.py` without broker SDK leaks.
    * Delivered 10 unit tests in `tests/unit/test_rate_budget.py` and evidence report [`ops/evidence/M2-02.md`](file:///c:/Algo/quantview/ops/evidence/M2-02.md) (`Status = TESTED`).
  - **Task M2-03 (WebSocket Raw Segment Writer):**
    * Implemented `services/collector_ws/framing.py` (`pack_frame`, `unpack_frames_from_bytes`, `ParsedFrame`): 28-byte binary framing envelope (`QVWS` magic, monotonic uint64 seq, microsecond arrival timestamp, uint32 payload length, uint32 CRC32 checksum).
    * Implemented `services/collector_ws/raw_segment_writer.py` (`RawSegmentWriter`, `SegmentManifest`): streaming to `.bin.partial` files with batched fsync (loss window $\le 1\text{ s}$), rotation to `.bin.gz`, and companion manifests with uncompressed and compressed SHA-256 digests.
    * Implemented automated crash recovery (`recover_session_partials`): parses incomplete `.partial` files, recovers 100% of complete frames, and safely quarantines corrupt trailing fragments with explicit diagnostic reports.
    * Implemented forensic session reconciliation (`reconcile_session_directory`).
    * Delivered 9 unit tests in `tests/unit/test_collector_ws.py` and evidence report [`ops/evidence/M2-03.md`](file:///c:/Algo/quantview/ops/evidence/M2-03.md) (`Status = TESTED`).
  - **Task M2-06 (Pre-Market Token Check & Dead-Man Heartbeat):**
    * Implemented `services/collector_snapshot/token_manager.py` (`TokenManager`) with native JWT expiry decoding, 08:45 AM pre-flight gate, `WAITING_FOR_TOKEN` state transition, and alert dispatching.
    * Implemented `services/collector_snapshot/heartbeat.py` (`HeartbeatMonitor`, `HeartbeatEmitter`) with atomic fsync JSON telemetry under `Data/raw/telemetry/` and dead-man switch alerting for lag $> 60\text{s}$.
    * Implemented standalone CLI tool `tools/ops/check_token_readiness.py` with exit codes 0 (valid) / 1 (waiting/expired).
    * Delivered 10 unit tests in `tests/unit/test_token_and_heartbeat.py` and evidence report [`ops/evidence/M2-06.md`](file:///c:/Algo/quantview/ops/evidence/M2-06.md) (`Status = TESTED`).
  - **Task M2-04 (SubscriptionManager and Single-Owner Lease):**
    * Implemented `services/collector_ws/lease.py` (`SingleOwnerLease`, `LeaseMetadata`, `DuplicateCollectorInstanceError`): kernel-level mutual exclusion (`msvcrt.locking` on Windows, `fcntl.flock` on POSIX) targeting `Data/raw/upstox_ws/.collector_ws.lock` with atomic companion metadata. Guarantees duplicate instances fail closed before opening any network sockets.
    * Implemented `services/collector_ws/subscription.py` (`SubscriptionManager`, `FeedMode`, `SubscriptionConfig`, `SubscriptionRejection`): multi-source set union across active deployments and chart windows, feed mode hierarchy resolution (`full_d30` > `full` > `ltpc`), capacity quota gating (max 500 keys), structured rejection logging, and Upstox V3 JSON wire commands (`method: "sub"`).
    * Delivered 9 unit tests in `tests/unit/test_subscription_and_lease.py` and evidence report [`ops/evidence/M2-04.md`](file:///c:/Algo/quantview/ops/evidence/M2-04.md) (`Status = TESTED`).
  - **Task M2-05 (WebSocket Decoder and Client Connection Lifecycle):**
    * Compiled Upstox official V3 Protobuf definitions into `services/collector_ws/proto/MarketDataFeedV3_pb2.py` with full support for `IndexFullFeed`, `MarketFullFeed`, `FirstLevelWithGreeks`, `MarketInfo`, and `LTPC`.
    * Implemented `services/collector_ws/decoder.py` (`WsQuote`, `WsQuoteDecoder`): unmarshals binary `FeedResponse` into canonical `ws_quotes` schema per `DATA SPEC §4.5`, maps 5-level depth books, Option Greeks, and vendor OHLC series. Tags `ZERO_DEPTH`, `NON_OPTION_OI`, and `SCAFFOLDED_DECODER_UNVERIFIED_FIXTURE` quality flags.
    * Implemented `services/collector_ws/client.py` (`UpstoxWebSocketClient`, `WebSocketClientConfig`): end-to-end async streaming loop with pre-flight lease acquisition, authorized redirect URI resolution via V3 endpoint (`/v3/feed/market-data-feed/authorize`), raw-first segment write before decoding, periodic atomic heartbeats, observer notification, and exponential backoff with jitter on disconnect.
    * Implemented dedicated operator CLI runner [`tools/ops/run_collector_ws.py`](file:///c:/Algo/quantview/tools/ops/run_collector_ws.py) and inspection tool [`tools/ops/dump_ws_segment.py`](file:///c:/Algo/quantview/tools/ops/dump_ws_segment.py).
    * Executed live dry run with real Upstox token: successfully connected, subscribed to Nifty 50, captured and decoded live index tick (LTP: 22,648.30), durably persisted `.bin.gz` segment + companion manifest, released single-owner lease cleanly. Result: `DRY-RUN RESULT: PASS`.
    * Delivered 7 decoder tests in `tests/unit/test_ws_decoder.py`, 5 client lifecycle tests in `tests/unit/test_collector_ws_client.py`, and evidence report [`ops/evidence/M2-05.md`](file:///c:/Algo/quantview/ops/evidence/M2-05.md) (`Status = TESTED`).
    * Enhanced `tools/ops/dump_ws_segment.py` with chronological timestamp sorting, full contract metadata enrichment (`trading_symbol`, `strike_price`, `option_type`, `expiry`), underlying Nifty 50 spot tracking (`underlying_spot_ltp`), all Option Greeks, market depth, and day/1m candle OHLC. Verified across 70,904 live quotes.
    * Added market-close auto-shutdown protections at 15:35 Asia/Kolkata across `tools/ops/run_collector_ws.py`, `tools/ops/run_collector_snapshot.py`, and deployed standalone background watchdog `tools/ops/market_close_watchdog.py`.
    * Completed full market session recording (2026-10-26): 134,003 live WebSocket ticks across 5 compressed segments (.bin.gz) and 86 full option chain snapshots (.json.gz). Forensic audit `reconcile_session_directory` confirmed 100% integrity (0 mismatches, 0 orphan files, 0 checksum errors).
  - **Automated Verification:** 118/118 automated unit tests PASS in 3.43s. `tools/qv_check.py lint DOCS` PASS (0 defects). `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks). All package boundaries intact. Active Lake remains 100% immutable.
  - Next: Live continuous session recording capture and Tasks M2-07 through M2-11.
