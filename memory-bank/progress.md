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
  - **Task M2-07 (Checkpointed Expired-Data Backfill):**
    * Implemented `services/backfill/service.py` (`ExpiredOptionBackfillService`, `BackfillCheckpointManager`, `BackfillCheckpoint`). Enforces rate budget priorities (yielding on low capacity), idempotent skip of completed items, and atomic `.tmp` state saves.
    * Delivered 4 unit tests in `tests/unit/test_backfill_service.py` and evidence report [`ops/evidence/M2-07.md`](file:///c:/Algo/quantview/ops/evidence/M2-07.md) (`Status = VERIFIED`).
  - **Task M2-08 (Session-Day Runbook and Scheduled Jobs):**
    * Authored comprehensive operations runbook [`ops/session-day-runbook.md`](file:///c:/Algo/quantview/ops/session-day-runbook.md) covering 08:45 pre-market gate, 09:14 stream launch, 09:15 snapshot loop, 15:35 auto-close, 15:36 reconciliation, and 16:00 backup.
    * Defined systemd service and timer units for Linux hosts and emergency remediation playbooks.
    * Delivered evidence report [`ops/evidence/M2-08.md`](file:///c:/Algo/quantview/ops/evidence/M2-08.md) (`Status = VERIFIED`).
  - **Task M2-09 (Collector Fault-Injection Suite):**
    * Implemented 5 fault injection tests in `tests/integration/test_collector_fault_injection.py`: disk-full fail-closed, clock jump monotonic sequencing, duplicate collector lease collision, process crash `.partial` recovery and quarantine, and token expiry gating.
    * Delivered evidence report [`ops/evidence/M2-09.md`](file:///c:/Algo/quantview/ops/evidence/M2-09.md) (`Status = VERIFIED`).
  - **Task M2-10 (Measure Live-Feed Volume and Storage Growth):**
    * Implemented `tools/lake/measure_feed_volume.py` and published [`reports/feed-volume.md`](file:///c:/Algo/quantview/reports/feed-volume.md).
    * Empirically measured: 6.86:1 compression ratio (85.4% space savings), 7 ticks/sec p50 rate, ~34.8 MB daily storage (~8.5 GB/year), confirming a 512 GB NVMe SSD provides > 2.5 years of retention.
    * Delivered evidence report [`ops/evidence/M2-10.md`](file:///c:/Algo/quantview/ops/evidence/M2-10.md) (`Status = VERIFIED`).
  - **Task M2-11 (Provision Production Linux Host and Read-Only Sync):**
    * Delivered [`ops/host_provisioning_runbook.md`](file:///c:/Algo/quantview/ops/host_provisioning_runbook.md) and [`tools/ops/sync_production_to_research.py`](file:///c:/Algo/quantview/tools/ops/sync_production_to_research.py).
    * Enforced unidirectional pull with SHA-256 manifest verification and zero write-back capability.
    * Delivered evidence report [`ops/evidence/M2-11.md`](file:///c:/Algo/quantview/ops/evidence/M2-11.md) (`Status = VERIFIED`).
  - **Gate G0 Clearance & Stage 2 Completion:**
    * Published formal Gate G0 audit report [`reports/stage2_closure/gate_g0_audit_report.md`](file:///c:/Algo/quantview/reports/stage2_closure/gate_g0_audit_report.md) and technical audit [`reports/stage2_closure/stage2_collector_audit.md`](file:///c:/Algo/quantview/reports/stage2_closure/stage2_collector_audit.md).
    * **127/127 automated unit and integration tests PASS in 9.86s.**
    * `tools/qv_check.py lint DOCS` PASS (0 defects).
    * `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
    * **Stage 2 (M2-01 to M2-11) is 100% COMPLETE.** Stage 3 planning scheduled for next session.
- **[2026-10-27] Stage 3 Completion & Gate G2a Certification (100% Complete & Verified):**
  - **Phase 3A (`M4-01` Complete & Verified):**
    * Implemented `packages/domain/money.py`: `Paise = NewType("Paise", int)`, `to_paise()`, `from_rupees()`, strict `PriceUnquantizableError` (`PRICE_NOT_QUANTIZABLE`). Zero binary float in monetary paths.
    * Implemented `packages/domain/quantizer.py`: `TickQuantizer` adverse tick rounding (BUY rounds up, SELL rounds down) using pure integer arithmetic.
    * Implemented `packages/domain/timestamps.py`: `UtcEpochSec` with aware `Asia/Kolkata` projection and session boundary detection (09:15-15:30 IST).
    * Implemented `packages/domain/contracts.py`: Immutable `ContractIdentifier(NamedTuple)` and canonical enums.
    * 19/19 unit tests passing in `tests/unit/test_domain_exact_money.py`; delivered [`ops/evidence/M4-01.md`](file:///c:/Algo/quantview/ops/evidence/M4-01.md).
  - **Phase 3B (`M4-13` & `M4-02` Complete & Verified):**
    * Hand-calculated and froze 9 canonical scenarios in [`tests/fixtures/golden_scenarios.py`](file:///c:/Algo/quantview/tests/fixtures/golden_scenarios.py). Fundamental ledger balance equation verified on every scenario: $\text{Cash} + \text{Long Market Value} == \text{Capital} + \text{Gross Realized} + \text{Unrealized} - \text{Total Fees}$.
    * Automated oracle verification: 7/7 tests passing in `tests/unit/test_engine_golden_scenarios.py`; delivered [`ops/evidence/M4-13.md`](file:///c:/Algo/quantview/ops/evidence/M4-13.md).
  - **Phase 3C (`M4-06` & `M4-04` Complete & Verified):**
    * Implemented `packages/ledger/fees.py`: Versioned fee schedule engine (`UPSTOX_2025_OCT`, `UPSTOX_2026_MAR`, `UPSTOX_2026_APR`), Union Budget 2026 STT (0.15%), NSE FA73061 turnover charge (0.03553%), and `ROUND_HALF_UP` statutory rounding. 10/10 tests passing in `tests/unit/test_fee_schedule.py`, 100% agreement with all 17 golden fills; delivered [`ops/evidence/M4-06.md`](file:///c:/Algo/quantview/ops/evidence/M4-06.md).
    * Implemented `packages/engine/selector.py`: Point-in-Time Contract Selector eliminating hardcoded grids. ATM, ITM_k, OTM_k, EXACT strike policies, OptionType moneyness, zero silent substitution, DuckDB data lake integration (`DuckDbContractMaster`). 8/8 tests passing in `tests/unit/test_contract_selector.py`; delivered [`ops/evidence/M4-04.md`](file:///c:/Algo/quantview/ops/evidence/M4-04.md).
  - **Phase 3D (`M4-07` & `M4-11` Complete & Verified):**
    * Implemented `packages/ledger/events.py`, `ledger.py`, `projections.py`: 15 canonical event types, rebuildable projections verifying balance equation without double-counting fees, and `LedgerWriter` Parquet round-trip persistence preserving initial capital in PyArrow metadata. 7/7 tests pass in `tests/unit/test_financial_ledger.py`; delivered [`ops/evidence/M4-07.md`](file:///c:/Algo/quantview/ops/evidence/M4-07.md).
    * Implemented PostgreSQL / SQLite triggers and relational store `packages/db/` (`001_create_ledger_events.sql`, `ledger_repo.py`). Tested UPDATE/DELETE trigger aborts and unique idempotency constraints. 5/5 tests pass in `tests/integration/test_postgres_ledger.py`; delivered [`ops/evidence/M4-11.md`](file:///c:/Algo/quantview/ops/evidence/M4-11.md).
  - **Phase 3E (`M4-03`, `M4-05`, `M4-22` Complete & Verified):**
    * Implemented `packages/engine/clock.py`: SimulationClock generating 375 standard minutes (09:15-15:30 IST) with multi-timeframe close detection. 4/4 tests pass in `tests/unit/test_calendar_minute_loop.py`; delivered [`ops/evidence/M4-03.md`](file:///c:/Algo/quantview/ops/evidence/M4-03.md).
    * Implemented `packages/engine/execution.py`, `orders.py`, `positions.py`: IntrabarFillEngine with 4-step sequence (`ENGINE §4`), `STOP_FIRST` ambiguity resolution, zero-volume flat bar exclusion, stale-data force-exit (3x slippage penalty), causal 15:25 force-flat, final-bar 15:29 rejection (`NO_NEXT_BAR`), and pre-scheduled exit (`EOD_CLOSE_FILL`). 7/7 tests pass in `tests/unit/test_fill_engine_intrabar.py`; delivered [`ops/evidence/M4-05.md`](file:///c:/Algo/quantview/ops/evidence/M4-05.md) and [`ops/evidence/M4-22.md`](file:///c:/Algo/quantview/ops/evidence/M4-22.md).
  - **Phase 3F (`M4-20`, `M4-12` Complete & Verified):**
    * Implemented `packages/risk/`: RiskRules Pydantic schema and RiskPolicyEvaluator checking RK-01 (kill switch), RK-02 (trading window), RK-06 (freeze quantity 1,800), RK-03 (daily loss), RK-04 (max drawdown), RK-05 (max trade capital). 6/6 tests pass in `tests/unit/test_risk_evaluator.py`; delivered [`ops/evidence/M4-20.md`](file:///c:/Algo/quantview/ops/evidence/M4-20.md).
    * Implemented `packages/strategies/`: StrategyRegistry with deterministic SHA-256 source code hashing and parameter validation. 4/4 tests pass in `tests/unit/test_strategy_registry.py`; delivered [`ops/evidence/M4-12.md`](file:///c:/Algo/quantview/ops/evidence/M4-12.md).
  - **Phase 3G (`M4-18`, `M4-08` Complete & Verified):**
    * Implemented `packages/engine/config.py`: 39-field EngineRunConfig schema strictly enforcing Invariant 14 (positive capital required with no default) and SHA-256 config hash. 6/6 tests pass in `tests/unit/test_run_config.py`; delivered [`ops/evidence/M4-18.md`](file:///c:/Algo/quantview/ops/evidence/M4-18.md).
    * Implemented `tools/run_backtest.py`, `packages/engine/runner.py`, `manifest.py`: BacktestRunner CLI with --validate, --override, --output-dir, writing all 5 provenance artifacts (`manifest.json`, `metrics.json`, `ledger.parquet`, `trades.json`, `equity.json`). 5/5 tests pass in `tests/unit/test_backtest_runner.py`; delivered [`ops/evidence/M4-08.md`](file:///c:/Algo/quantview/ops/evidence/M4-08.md).
  - **Phase 3H (`M4-15` Complete & Verified):**
    * Implemented `packages/engine/metrics.py`: 22+ performance metrics and Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR) with daily frequency consistency and trial validity gating ($N < 2$ emits null with reason). 5/5 tests pass in `tests/unit/test_backtest_metrics_dsr.py`; delivered [`ops/evidence/M4-15.md`](file:///c:/Algo/quantview/ops/evidence/M4-15.md).
  - **Phase 3I (`M4-09`, `M4-10`, `M4-21` Complete & Verified):**
    * Implemented `packages/strategies/smoke.py`: `LongCETrendFollowing` and `LongPEMeanReversion`.
    * Implemented `tests/integration/test_backtest_reproducibility.py`: Real DuckDB lake execution across 446 sessions, slippage sensitivity grid (0x..3x), capital feasibility sweep (₹10k..₹200k), 5-year synthetic benchmark (1,250 sessions in 0.28s), and 3-rerun byte-identical determinism (SHA-256 match). Delivered [`ops/evidence/M4-09.md`](file:///c:/Algo/quantview/ops/evidence/M4-09.md) and [`ops/evidence/M4-10.md`](file:///c:/Algo/quantview/ops/evidence/M4-10.md).
    * Authored early margin and settlement research spike: [`reports/margin-settlement-evidence.md`](file:///c:/Algo/quantview/reports/margin-settlement-evidence.md) (`M4-21`).
  - **Gate G2a Formal Certification:**
    * Published formal Gate G2a audit report: [`reports/stage3_closure/gate_g2a_audit_report.md`](file:///c:/Algo/quantview/reports/stage3_closure/gate_g2a_audit_report.md).
    * **87/87 tests pass under `pytest -m gate_g2a` in 6.29s.**
    * **222/222 automated tests pass across full repository in 8.99s.**
    * `tools/qv_check.py lint DOCS` PASS (0 defects).
    * `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
    * **GATE G2a IS OFFICIALLY CERTIFIED PASS.** Ready for Stage 4 (Gate G2b).
- **[2026-10-27] Stage 4 Completion & Gate G2b Certification (100% Complete & Verified):**
  - **Phase 4A (`M4-14` Complete & Verified):**
    * Implemented `packages/engine/groups.py`: `LegStatus`, canonical 10-state `LeggingState` lifecycle machine with strict transition enforcement (`InvalidLeggingTransitionError`), `StrategyIntent`, `LegPosition` with exact integer-paise directional P&L, `PositionGroup` tracking composite mark, combined P&L, high-water mark peak trailing stops, and stale mark propagation.
    * Implemented `packages/risk/margin.py`: `MarginMode`, `MarginEvaluator`, and fail-closed safety guard (`RealisticMarginBlockedError: MARGIN_NOT_VERIFIED`).
    * Delivered 9 unit tests in `tests/unit/test_position_groups.py` and evidence report [`ops/evidence/M4-14.md`](file:///c:/Algo/quantview/ops/evidence/M4-14.md).
  - **Phase 4B (`M4-16` Complete & Verified):**
    * Implemented `packages/engine/sequencer.py`: `LeggingSequencer`, SEBI margin-optimal entry sequencing (long hedge filled first before queuing short leg), margin-optimal exit priority (short buyback before long sale), 15:00 IST entry cutoff (`ENTRY_AFTER_CUTOFF`), 15:25 IST force-flat (`FORCE_FLAT_1525`), emergency legging unwind with **3x adverse tick slippage penalty** ($3 \times 5 = 15\text{ paise}$), stale mark deferral, and 15:29:00 EOD boundary handling (`EOD_CLOSE_FILL` vs `HALTED_UNRESOLVED`).
    * Delivered 11 unit tests in `tests/unit/test_legging_sequencer.py` and evidence report [`ops/evidence/M4-16.md`](file:///c:/Algo/quantview/ops/evidence/M4-16.md).
  - **Phase 4C (`M4-17` Complete & Verified):**
    * Implemented dated regulatory `MARGIN_VERIFICATION_RECORD` in `packages/risk/margin.py` referencing Task M4-21 empirical research (`reports/margin-settlement-evidence.md`).
    * Implemented fail-closed block preventing short options under `REALISTIC_ACCOUNT` without verified clearing SPAN files (`.spn`), while allowing labelled `THEORETICAL` mode execution with prominent audit metadata.
    * Implemented `FinancialLedger.free_cash_paise` ($\text{Free Cash} = \text{Cash Balance} - \text{Total Margin Reserved}$) and `MARGIN_RESERVED`/`MARGIN_RELEASED` events with `amount_paise = Paise(0)`.
    * Delivered 6 unit tests in `tests/unit/test_margin_evaluator.py` and evidence report [`ops/evidence/M4-17.md`](file:///c:/Algo/quantview/ops/evidence/M4-17.md).
  - **Phase 4D (`M4-19` Complete & Verified):**
    * Implemented and registered four canonical multi-leg strategies in `packages/strategies/multileg.py`: `BullCallSpreadStrategy`, `BearPutSpreadStrategy`, `LongStraddleStrategy`, and `ShortStrangleTheoreticalStrategy` (registered in `StrategyRegistry`).
    * Authored independent integer-paise golden oracle fixture `tests/fixtures/multileg_golden_scenarios.py` with 4 hand-calculated scenarios (ML-1, ML-2, ML-3, ML-4).
    * Enhanced `packages/ledger/projections.py` to support short options (`qty < 0`), short coverage, short market liability, and verified fundamental balance equation down to **0.00 paise drift**.
    * Delivered 4 integration tests in `tests/integration/test_multileg_backtest.py` and evidence report [`ops/evidence/M4-19.md`](file:///c:/Algo/quantview/ops/evidence/M4-19.md).
  - **Phase 4E (Scalability Benchmark & Cold-Rerun Determinism):**
    * Authored `tests/integration/test_multileg_benchmark.py`: 500 simulated trading sessions $\times$ 75 bars = 37,500 bars, 1,000 PositionGroups, 50 unwinds completed in 0.007s ($> 5,000,000\text{ bars/sec}$), shattering the $\le 180$s SLA.
    * 3 cold reruns verified 100% byte-identical SHA-256 Parquet ledger hashes.
  - **Gate G2b Formal Certification:**
    * Published formal Gate G2b audit report: [`reports/stage4_closure/gate_g2b_audit_report.md`](file:///c:/Algo/quantview/reports/stage4_closure/gate_g2b_audit_report.md).
    * **31/31 tests pass under `pytest -m gate_g2b` in 1.06s.**
    * **255/255 automated tests pass across full repository in 13.22s.**
    * `tools/qv_check.py lint DOCS` PASS (0 defects).
    * `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
    * **GATE G2b IS OFFICIALLY CERTIFIED PASS.** Ready for Stage 5 (Gate G3).
- **[2026-10-27] Stage 5 — Gate G3 Phase 5A: Feature Registry, Schemas & Causality Harness (COMPLETE - ALL PASS):**
  - **Plan Frozen:** Delivered and finalized [`stage5_implementation_plan.md`](file:///C:/Users/Aary/.gemini/antigravity/brain/06a15e89-b29d-4bcb-80a8-a97856ca6a27/stage5_implementation_plan.md) with comprehensive formula audit (RV, IV-RV Spread, NATR, Straddle-IV inverter, Black-76 ACT/365F Greeks, Supertrend state machine, BOS/CHoCH tie-breaking, depth imbalance null guard, candle delta proxy, and 3 causality protocols).
  - **Task M5-01 Satisfied:**
    * Implemented `packages/features/schemas.py`: Canonical enums (`SourceTier`, `MemoryClass`, `RepaintClass`, `FeatureStatus`), immutable `FeatureDefinition` (`frozen=True`), and deterministic SHA-256 parameter hashing (`compute_param_hash`, `feature_id = f"{name}_{version}_{param_hash[:8]}"`).
    * Implemented `packages/features/registry.py`: Thread-safe `FeatureRegistry` singleton (`threading.RLock`), duplicate collision detection (`DuplicateFeatureRegistrationError`), `@register_feature` decorator, and `export_json_schema()` Draft 2020-12 export.
    * Implemented 3 causality test protocols: `verify_prefix_invariance` ($F([0 \dots t])_t \equiv F([0 \dots T])_t$), `verify_future_perturbation`, and `verify_availability_enforcement` (`TemporalLeakageError`).
    * Re-exported cleanly via `packages/features/__init__.py`.
  - **Automated Verification:**
    * Delivered 16 unit tests in `tests/unit/test_feature_registry.py` under `@pytest.mark.gate_g3` (16/16 PASS in 0.16s).
    * **271/271 tests PASS across entire repository in 15.42s** (0 regressions).
    * `tools/qv_check.py lint DOCS` PASS (0 defects).
    * `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
    * Published evidence report [`ops/evidence/M5-01.md`](file:///c:/Algo/quantview/ops/evidence/M5-01.md).
    * **Phase 5A Stop Condition Met:** Stopped prior to Phase 5B (Technical Indicators).
- **[2026-10-27] Stage 5 — Gate G3 Phase 5B: Technical Indicators & TradingView Oracle (COMPLETE - ALL PASS):**
  - **Tasks M5-03, M5-08, M5-11 Satisfied:**
    * Implemented `packages/features/statistical/indicators.py`: Moving averages (SMA, dual-seed EMA), oscillators (Wilder RSI, MACD), volatility measures (ATR, NATR, Bollinger Bands, Realized Volatility), directional indicators (Supertrend, ADX with +DI/-DI), and IV-RV Spread interface.
    * Implemented `packages/features/statistical/vwap_guard.py`: Fail-closed Session VWAP quarantine (`SessionVWAPQuarantinedError`, `BLOCKED_QUARANTINED`). Prohibits fake volume, tick counts, or synthetic proxies on NIFTY cash index.
    * Implemented `tests/fixtures/pine_indicator_oracle.py`: Hand-calculated numerical golden fixture and independent reference oracle reproducing TradingView Pine Script v5/v6 built-ins.
    * Conducted mandatory EMA parity investigation: `seed_policy="PINE_SCRIPT"` matches TradingView within $< 10^{-12}$ on every single bar from bar 0; `seed_policy="SMA"` initial deviation decays exponentially to $< 10^{-4}$ after $5N$ warm-up bars.
  - **Automated Verification:**
    * Delivered 31 unit tests in `tests/unit/test_causal_indicators.py` under `@pytest.mark.gate_g3` (31/31 PASS in 0.22s).
    * Total Gate G3 marker tests: **47/47 PASS in 6.90s**.
    * Full repository regression suite: **302/302 tests PASS in 15.42s** (0 regressions).
    * Linters: `tools/qv_check.py lint DOCS` PASS (0 defects); `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks); `tests/unit/test_package_boundaries.py` 7/7 PASS.
    * Published evidence reports: [`ops/evidence/M5-03.md`](file:///c:/Algo/quantview/ops/evidence/M5-03.md), [`ops/evidence/M5-08.md`](file:///c:/Algo/quantview/ops/evidence/M5-08.md), [`ops/evidence/M5-11.md`](file:///c:/Algo/quantview/ops/evidence/M5-11.md).
    * **Phase 5B Stop Condition Met:** Stopped prior to Phase 5C (Market Structure Engine BOS/CHoCH).
- **[2026-10-27] Stage 5 — Gate G3 Phase 5C: Deterministic BOS / CHoCH Market Structure Engine (COMPLETE - ALL PASS):**
  - **Task M5-06 Satisfied:**
    * Implemented `packages/features/structure/bos_choch.py` and `packages/features/structure/__init__.py`: Deterministic swing pivot detection with configurable windows ($W_L=5, W_R=5$).
    * Causal availability gating: Pivot at bar $i$ is causally invisible until bar $t = i + W_R$ closes (`confirmed_at = ts_close(i + W_R)`).
    * Asymmetric tie-breaking: Strict left inequality ($>$) and non-strict right inequality ($\ge$) guarantees earliest bar selection on flat plateaus.
    * One-time level consumption: Broken levels are consumed (`is_consumed=True`) and removed from active level tracking.
    * Break criteria: Default strict `CLOSE_THROUGH` and optional intrabar `TOUCH`. TOUCH double-break resolution with `AMBIGUOUS_DOUBLE_BREAK` flag.
    * Canonical transition matrix: Verified 6-state matrix (`NEUTRAL`, `BULLISH`, `BEARISH`), correctly implementing reversal from BEARISH to `BULLISH` (`BULLISH_CHOCH`) on break of swing high per `ENGINE §21.2`.
  - **Automated Verification:**
    * Delivered 11 unit tests in `tests/unit/test_market_structure.py` under `@pytest.mark.gate_g3` (11/11 PASS in 0.17s).
    * Total Gate G3 marker tests: **58/58 PASS in 1.14s**.
    * Full repository regression suite: **313/313 tests PASS in 14.61s** (0 regressions).
    * Linters: `tools/qv_check.py lint DOCS` PASS (0 defects); `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks); `tests/unit/test_package_boundaries.py` 7/7 PASS.
    * Published evidence report [`ops/evidence/M5-06.md`](file:///c:/Algo/quantview/ops/evidence/M5-06.md).
    * **Phase 5C Stop Condition Met:** Stopped prior to Phase 5D (Market Calendar & Trading Sessions).
- **[2026-10-27] Stage 5 — Gate G3 Phase 5D: Market Calendar, Session Progress & High-Water Features (COMPLETE - ALL PASS):**
  - **Task M5-07 Component Satisfied:**
    * Implemented `packages/features/calendar/session.py`: `SessionProgress`, point-in-time NSE regular trading hours (09:15-15:30 IST), minutes since open, countdown to 15:00 entry cutoff (RK-19), countdown to 15:25 force-flat (RK-20), session progress fraction, DOW, and DTE.
    * Implemented `packages/features/calendar/high_water.py`: `SessionHighWater`, rolling session high/low with daily 09:15 IST reset.
    * Delivered 6 unit tests in `tests/unit/test_calendar_features.py` under `@pytest.mark.gate_g3` (6/6 PASS in 0.15s).
- **[2026-10-27] Stage 5 — Gate G3 Phase 5E: Lazy Reconstructed Option Chain (COMPLETE - ALL PASS):**
  - **Task M5-04 Satisfied:**
    * Implemented `packages/features/chain/lazy_chain.py` and canonical DuckDB lazy view `v_snapshots_reconstructed_chain` (`SQL_CREATE_VIEW_RECONSTRUCTED_CHAIN`).
    * Zero-copy, lazy point-in-time queries strictly enforcing `available_at <= as_of_minute` (zero future rows).
    * Fail-closed missing contract reporting (`is_available=False`, `MISSING_STRIKE`), prohibiting silent substitution or interpolation.
    * ATM strike rounding (tie-broken to lower strike) and liquid ATM +/- N strike band extraction.
    * Delivered 6 unit tests in `tests/unit/test_lazy_chain.py` under `@pytest.mark.gate_g3` (6/6 PASS in 0.25s).
    * Published evidence report [`ops/evidence/M5-04.md`](file:///c:/Algo/quantview/ops/evidence/M5-04.md).
- **[2026-10-27] Stage 5 — Gate G3 Phase 5F: Liquid ATM Band Black-76 Model Greeks, Skew & Derived Features (COMPLETE - ALL PASS):**
  - **Tasks M5-05 & M5-12 Satisfied:**
    * Implemented `packages/features/volatility/black76.py`: Closed-form European index pricer, analytical Delta, Gamma, Vega, and daily Theta. Put-Call Parity verified to $< 10^{-10}$.
    * Implemented `packages/features/volatility/greeks_solver.py`: Bounded Brent IV solver with non-arbitrage bounds guard (`ARBITRAGE_BOUND_VIOLATION`), liquid ATM +/- 5 band evaluation, and strict `model_*` prefix segregation per DATA §4.7.
    * Implemented `packages/features/volatility/skew.py`: 25-delta Risk Reversal skew and 25-delta Butterfly smile curvature.
    * Implemented `packages/features/chain/derived.py`: Total and near-ATM Put-Call Ratio (PCR by OI/Volume) with zero-call division guard (`DIV_BY_ZERO`), OI Rate of Change (OI ROC), ATM Straddle premium with Brenner-Subrahmanyam synthetic IV, and Delta-band aggregate OI distribution (Deep OTM, OTM, ATM, ITM).
    * Delivered 12 unit tests across `tests/unit/test_black76_greeks.py` (7/7 PASS) and `tests/unit/test_chain_derived_features.py` (5/5 PASS) under `@pytest.mark.gate_g3`.
    * Total Gate G3 marker tests: **82/82 PASS in 1.26s**.
    * Full repository regression suite: **337/337 tests PASS in 14.09s** (0 regressions).
    * Linters: `tools/qv_check.py lint DOCS` PASS (0 defects); `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks); `tests/unit/test_package_boundaries.py` 7/7 PASS.
    * Published evidence reports: [`ops/evidence/M5-05.md`](file:///c:/Algo/quantview/ops/evidence/M5-05.md) and [`ops/evidence/M5-12.md`](file:///c:/Algo/quantview/ops/evidence/M5-12.md).
- **[2026-10-27] Stage 5 — Gate G3 Phases 5G, 5H, 5I: Order Flow, Transforms, Models, Runner & Gate Closure (COMPLETE - ALL PASS):**
  - **Tasks M5-02, M5-07, M5-09, M5-10, M5-12 Component Satisfied:**
    * Implemented `packages/features/orderflow/`: Top-of-Book Depth Imbalance proxy with fail-closed zero-depth guard (None rather than 0.0), and Candle Bar Volume Delta proxy with explicit honest lineage tags (`tests/unit/test_orderflow_proxies.py`, 5/5 PASS).
    * Implemented `packages/features/transforms/`: Heikin Ashi display transform with versioned seed and Renko brick generation with 2-brick reversal and confirmation timestamps. Strictly enforced non-tradable invariant (`is_display_transform_only=True`, `NonTradableTransformError`) per `ENGINE §22` (`tests/unit/test_transforms_and_models.py`, 3/3 PASS, [`ops/evidence/M5-09.md`](file:///c:/Algo/quantview/ops/evidence/M5-09.md)).
    * Implemented `packages/features/models/`: `FrozenModelContract` Pydantic model (`frozen=True`) and `ModelInferenceInterface` with absolute anti-training barrier (`NoInferenceTrainingAllowedError`) for R1 research baselines (`tests/unit/test_transforms_and_models.py`, 2/2 PASS, [`ops/evidence/M5-10.md`](file:///c:/Algo/quantview/ops/evidence/M5-10.md)).
    * Implemented `packages/features/runner/`: `IsolatedFeatureRunner` sandboxed process runner per ADR-012 with timeouts, memory supervision, crash containment, and fail-closed trade entry blocking (`tests/unit/test_subprocess_runner.py`, 5/5 PASS, [`ops/evidence/M5-07.md`](file:///c:/Algo/quantview/ops/evidence/M5-07.md)).
    * Benchmarked 8-indicator suite across 10,000 bars in **0.0414s** (**241,321 bars/sec**). Total recomputation across 446 sessions requires $\approx 0.69$s. Persistent disk caching is empirically unjustified and intentionally left unimplemented per `M5-02` (`tests/integration/test_feature_benchmark.py`, 1/1 PASS, [`ops/evidence/M5-02.md`](file:///c:/Algo/quantview/ops/evidence/M5-02.md)).
  - **Gate G3 Formal Certification:**
    * Published formal Gate G3 audit report: [`reports/stage5_closure/gate_g3_audit_report.md`](file:///c:/Algo/quantview/reports/stage5_closure/gate_g3_audit_report.md).
    * **98/98 tests pass under `pytest -m gate_g3` in 3.82s.**
    * **353/353 automated tests pass across full repository in 11.63s.**
    * `tools/qv_check.py lint DOCS` PASS (0 defects).
    * `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
    * `tests/unit/test_package_boundaries.py` 7/7 PASS.
    * **GATE G3 IS OFFICIALLY CERTIFIED PASS AND CLOSED.** Ready for Stage 6 (Gate G4).
- **[2026-10-28] Stage 6 — Task 8 (M6-13: Drawing Tools, Overlay Canvas & Long/Short Position Hit-Test Bug Fix) (COMPLETE - ALL PASS):**
  - **Milestone M6-13 Satisfied:**
    * Implemented `apps/web/js/drawings.js`: Complete 13-tool technical drawing suite + cursor/select mode, transparent overlay canvas, point coordinate conversions, vector rendering, and full FastAPI persistence lifecycle (POST, GET, DELETE single, DELETE by symbol).
    * Fixed the Long and Short position hit-test bounding box calculation so that clicking anywhere inside target, entry, or stop zones selects the box for immediate deletion or editing.
    * Integrated `DrawingLayer` with `QuantChart` in `apps/web/js/chart.js` and `apps/web/js/app.js`: overlay canvas mounting, resize synchronization, `#drawbar` toolbar UI buttons, and Delete/Backspace/Escape shortcuts.
    * Delivered 6 unit tests in `tests/api/test_drawings_hit_test.py` under `@pytest.mark.gate_g4` (6/6 PASS).
    * Total `tests/api` suite: **73/73 PASS in 20.50s**.
    * `ruff check .` output: **All checks passed!** (0 errors).
- **[2026-10-28] Stage 6 — Task 10 (M6-04, M6-07, M6-08, M6-09: Strategy Tester Panel & On-Chart Trade Markers Linkage) (COMPLETE - ALL PASS):**
  - **Milestones M6-04, M6-07, M6-08, M6-09 Satisfied:**
    * Strategy Browser & Dynamic Form (M6-08, M6-09): Discovers registered strategies from `/api/v1/backtest/strategies` with dynamic metadata card displaying author, version, regimes badges (`TRENDING_BULLISH`, `RANGE_BOUND`, etc.), and detailed logic descriptions. Form controls based on `RunConfig`: `strategy_id`, date range pickers (default 2025-01-02 to 2025-01-31), `initial_capital_rupees` (₹500,000), `lots` (1), `execution_mode` (`UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`), `intrabar_stop_policy` (`STOP_FIRST`, `OHLC_PATH`), and `fee_schedule` (`UPSTOX_2026_V1`, `UPSTOX_2025_OCT`), featuring an in-flight loading spinner on the Run button and an active Cancel button.
    * Backtest Execution & Status Monitoring (M6-07): Submits `POST /api/v1/backtest/run` and polls `GET /api/v1/backtest/status/{id}` until completed or cancelled.
    * Tear Sheet KPI Metrics Cards (M6-04): 8 institutional metrics: Net P&L (₹ formatted in Indian numbering with color green/red), Total Return (%), Sharpe Ratio, Deflated Sharpe Ratio (DSR), Max Drawdown (%), Win Rate (%), Total Trades, Profit Factor.
    * Equity Curve Sub-Chart (M6-04): Interactive visual rendering of the mark-to-market equity curve with peak equity, final balance, and drawdown stats using Lightweight Charts AreaSeries or high-DPI HTML5 canvas fallback.
    * Trade Log Audit Table (M6-04): Sortable audit table of all completed round-trip trades: Entry Time (IST), Exit Time (IST), Contract/Symbol, Side, Qty, Entry Price (₹), Exit Price (₹), Gross P&L (₹), Fees (₹), Net P&L (₹), Exit Reason. Interactive click-to-highlight centers chart on the trade entry candle via `chart.scrollToTime()`, plots dashed entry/exit price lines via `chart.highlightTrade()`, and displays a detailed Decision Audit Card with signal reasons and rule parameters.
    * On-Chart Trade Markers Linkage (M6-09): Automatically plots paired Lightweight Charts overlay markers upon backtest completion: green `arrowUp` below bar (`ENTRY BUY @ ₹...`) and red `arrowDown` above bar (`EXIT @ ₹... (Net: ₹...)`).
    * Backend API enhancements in `services/api/schemas/backtest.py` and `services/api/routers/backtest.py`: Added market regimes, `fee_schedule`, `execution_mode`, `total_return_pct`, and deduplicated strictly monotonic timestamps for the equity curve.
    * Delivered 8 automated contract tests in `tests/api/test_strategy_tester_ui_contract.py` (8/8 PASS).
    * Full `tests/api` test suite: **91/91 PASS in 12.84s**.
    * `ruff check .` output: **All checks passed!** (0 errors).
- **[2026-10-28] Stage 6 - Task 11 (M6-18, UI-1b, M6-03b, M6-15: NIFTY Option Chain Tab with One-Click Paper Execution & Chart SL/TP Lines) (COMPLETE - ALL PASS):**
  - **Milestones M6-18, UI-1b, M6-03b, M6-15 Satisfied:**
    * Option Chain Matrix Tab (`apps/web/js/app.js`, `apps/web/css/app.css`):
      - Controls Bar: Underlying selector (default NIFTY, supports BANKNIFTY, FINNIFTY), Expiry dropdown querying `/api/v1/options/expiries`, Strike range selector (10, 15, 20, 25 strikes), Spot price indicator with ATM strike display, and manual Refresh button.
      - Dual-Column Strike Matrix: Left Calls/CE (OI, OI Change, IV%, Delta, Theta, Bid, Ask, LTP, B/S buttons), Center Strike Price with ATM tag, Right Puts/PE (B/S buttons, LTP, Bid, Ask, Delta, Theta, IV%, OI Change, OI).
      - Shading & Centering: Distinct yellow/amber shading (`rgba(255, 193, 7, 0.08)`) for In-The-Money (ITM) strikes (Calls < Spot, Puts > Spot) vs OTM strikes; automatic viewport centering for ATM strike row upon data load.
      - Summary Badges: Total Calls OI, Total Puts OI, and dynamic Put-Call Ratio (PCR) with sentiment color indicator (Bullish >= 1.0, Bearish < 0.8, Neutral).
      - Strike Click to View Option Candlesticks (M6-03b, M6-16): Contextual trigger to load historical 1m option contract candles into QuantChart via `/api/v1/options/candles` with on-chart return banner.
    * One-Click Paper Order Routing & Modal (M6-18):
      - B/S buttons launch dedicated order modal for `ACC-MANUAL-PAPER` with lot multiplier (25 qty/lot), Market/Limit type, customizable % or ₹ Stop-Loss and Take-Profit levels, and estimated margin.
      - Submitting dispatches `POST /api/v1/paper/orders` returning HTTP 201 Created.
      - Tab Redirection Rule: Submitting paper orders strictly retains focus on the Option Chain tab without navigating away.
    * On-Chart SL/TP & Entry Lines (M6-18):
      - Solid Cyan/Blue line (`#00bcd4`) for Entry, dashed Red line (`#f44336`) for Stop-Loss, and dashed Green line (`#4caf50`) for Take-Profit plotted instantly on chart canvas with on-chart badge and cleanup action.
    * Backend API enhancements in `services/api/schemas/paper.py`, `services/api/routers/paper.py`, `services/api/schemas/options.py`, `services/api/routers/options.py`:
      - Added `stop_loss_price` and `take_profit_price` to `PaperOrderRequest`.
      - Added `total_ce_oi`, `total_pe_oi`, and `pcr` to `OptionChainResponse`.
      - Added fallback contract ID string resolution for option candles in DuckDB lake.
    * Delivered 9 automated contract tests in `tests/api/test_option_chain_ui_contract.py` (9/9 PASS).
    * Full `tests/api` test suite: **100/100 PASS in 18.88s**.
    * `ruff check .` output: **All checks passed!** (0 errors).
- **[2026-10-28] Stage 6 - Task 12 (M6-06, M6-14, Section 6.1, Section 6.2: Macro/Micro Paper Trading Console, Screener & Strategy Heatmap) (COMPLETE - ALL PASS):**
  - **Milestones M6-06, M6-14, Section 6.1, Section 6.2 Satisfied:**
    * **Paper Trading Tab (`paper`, M6-06, M6-14):**
      - Implemented complete dual-view structure with View Toggle Buttons: `[Micro: Discretionary Console]` (default) and `[Macro: Strategy Bots]`.
      - **Micro View for `ACC-MANUAL-PAPER`:**
        * 6 integer-paise financial ledger cards: Equity, Cash, Margin Reserved, Free Cash, Realized P&L, Unrealized P&L (all formatted with `fmtRupees`).
        * Sub-navigation bar with Positions, Orders, and Trade History sections, plus top red "Square Off All" button (`POST /api/v1/paper/square-off-all`).
        * Positions Table: Symbol/Contract, Side, Qty, Avg Price, LTP, P&L (₹), P&L %, and one-click "Square Off" button.
        * Orders Table: Order ID, Symbol, Side, Qty, Type, Price, Status (`PENDING`, `FILLED`, `CANCELLED`, `REJECTED`), Placed At, and "Cancel" button for pending orders (`POST /api/v1/paper/orders/cancel/{order_id}`).
        * Trade History Table: Itemized audit trail with execution timestamps (IST), symbols, sides, quantities, fill prices, statutory fees (`₹23.60`), and realized P&L.
      - **Macro View (Strategy Bots Monitor):**
        * High-level table for automated strategies with Strategy Name & ID, Operating Mode (`ACTUAL_OPTIONS`, `UNDERLYING_DIRECTIONAL`), Status (`Running`, `Warming Up`, `Stopped`), Allocated Lots, Today's P&L (₹), Win Rate %, and Sharpe Ratio.
      - **Risk Policy Card:**
        * Displays Account Allocation Mode (`ISOLATED`), Order Freeze Limit (`RK-06` = 1,800 units), Advisory Lot Ceiling (`RK-26` = 72 lots), Max Daily Loss (`₹50,000.00`), Max Drawdown (`10.0%`), and Trading Window (`09:15 - 15:25 IST`).
    * **Indian Market Screener Tab (`screener`, Section 6.1):**
      - Exclusively tailored for Indian derivatives (NIFTY & VIX) via `GET /api/v1/market/screener`:
        * Row 1: `NSE:NIFTY50`: Index Spot, Daily Change %, Day High, Day Low, 52-Week Range (`21,281.45 - 26,277.35`), Volume.
        * Row 2: `INDIAVIX`: Volatility level, regime categorization (`Low < 13`, `Normal 13–18`, `High > 18`).
        * Row 3: `NIFTY ATM CE`: Current weekly ATM call option premium, strike, daily change %, expiry.
        * Row 4: `NIFTY ATM PE`: Current weekly ATM put option premium, strike, daily change %, expiry.
      - Click-to-chart: Clicking any row switches the active main chart symbol to that instrument.
    * **Quantitative Strategy Sensitivity Heatmap Tab (`heatmap`, Section 6.2):**
      - 5x5 Sensitivity Matrix Grid via `GET /api/v1/backtest/heatmap`:
        * X-Axis: Strike Offset (`ATM-2`, `ATM-1`, `ATM`, `ATM+1`, `ATM+2`).
        * Y-Axis: Stop-Loss % (`10%`, `20%`, `30%`, `40%`, `50%`).
        * Metric toggle: `[Net P&L (₹)]` / `[Sharpe Ratio]` with dynamic green/red gradient shading.
        * Hover tooltips showing exact metrics (Return %, Sharpe, Max DD) for each parameter tuple.
      - Monthly Returns Calendar View:
        * Visual grid of months (Jan–Dec) and historical years (2025, 2026) showing monthly P&L percentages with green/red heatmap shading and annual total.
    * **Workstation Settings Modal (`/settings`, M6-14):**
      - Accessible via `#settingsBtn` in topbar with full 4-tab interface:
        * Tab 1: Database (DuckDB lake path, Parquet status, total sessions, capture count, analytical views).
        * Tab 2: Upstox API (token status, rate limit budget, latency, endpoints).
        * Tab 3: Risk Policy (`RK-01` to `RK-26`, freeze limit 1,800 units, advisory ceiling 72 lots, allocation mode `ISOLATED`).
        * Tab 4: UI Preferences (Theme, Web Audio fill sound, candle density, timezone IST).
    * **Backend API Gateway Enhancements:**
      - `services/api/schemas/paper.py` & `services/api/routers/paper.py`: Added `account_allocation_mode` to `RiskPolicySummary`, `statutory_fees_rupees` to `PaperTrade`, `/api/v1/paper/account` endpoint, `/api/v1/paper/square-off-all` and `/api/v1/paper/square-off/{id}` endpoints.
      - `services/api/schemas/market.py` & `services/api/routers/market.py`: Added `ScreenerItem`, `ScreenerResponse`, and `GET /api/v1/market/screener`.
      - `services/api/schemas/backtest.py` & `services/api/routers/backtest.py`: Added `HeatmapCell`, `MonthlyReturnYear`, `StrategyHeatmapResponse`, and `GET /api/v1/backtest/heatmap`.
      - `services/api/main.py`: Added public alias routes `/api/v1/screener` and `/api/v1/heatmap`.
    * **Delivered 7 automated contract tests in `tests/api/test_paper_screener_heatmap_contract.py` (7/7 PASS):**
      - Macro strategy bots catalog telemetry.
      - Micro account balances and integer-paise dynamic equity formulas.
      - Discretionary order execution, positions, working orders, trades audit trail, and single square-off.
      - Batch square-off-all liquidation.
      - Pre-trade risk policy inspection parameters (`RK-06`, `RK-26`, `ISOLATED`).
      - Indian market screener data contracts (NIFTY, VIX, ATM CE, ATM PE).
      - Strategy sensitivity heatmap matrix data structure and monthly calendar.
    * **Full test suite:** **107/107 PASS in 17.61s**.
    * `ruff check .` output: **All checks passed!** (0 errors).
- **[2026-10-29] Stage 6 - Task 13 (Full Gate G4 Test Suite, Ruff Linting, and Stage 6 Closure Audit Report) (COMPLETE - RELEASE GATE G4 PASS & CLOSED):**
  - **Milestone Matrix M6-01 through M6-18 Certified 100% Complete:**
    * `M6-01` (FastAPI Read/Query API and Typed Client): VERIFIED & CLOSED (`services/api/main.py`, `apps/web/js/api.js`, `apps/web/js/types.d.ts`).
    * `M6-02` (Data-Health and Coverage Page / Modal): VERIFIED & CLOSED (`services/api/routers/health.py`, `apps/web/index.html` `#coverageModal`).
    * `M6-03` (Candle Chart Rendering and Viewport Engine): VERIFIED & CLOSED (`apps/web/js/chart.js`, Lightweight Charts v4.2.1, 5,000 bars, 60 FPS).
    * `M6-03b` (Per-Strike Option Chart with Trade Markers): VERIFIED & CLOSED (`services/api/routers/options.py`, `setTradeMarkers`).
    * `M6-04` (Results and Audit Panel): VERIFIED & CLOSED (`apps/web/index.html` `#bottomDock`, Strategy Tester trade audit logs).
    * `M6-05` (Chart License and API Health): VERIFIED & CLOSED (`apps/web/vendor/lightweight-charts.LICENSE` Apache 2.0, `/health`, `/heartbeat`).
    * `M6-06` (Accounts and Risk-Policy CRUD): VERIFIED & CLOSED (`services/api/routers/paper.py`, `RK-06` 1,800 units, `RK-26` 72 lots, `ISOLATED`).
    * `M6-07` (Backtest Launch and Configuration Commands): VERIFIED & CLOSED (`services/api/routers/backtest.py`, `POST /api/v1/backtest/run`).
    * `M6-08` (Dashboard and Strategy Browser UI): VERIFIED & CLOSED (`apps/web/index.html`, strategy catalog and regime tags).
    * `M6-09` (RunConfig-Driven Backtest Form and Audit-Linked Flow): VERIFIED & CLOSED (`apps/web/js/app.js`, dynamic form generation, status polling).
    * `M6-10` (Live Streaming Bridge Preparation & Polling Fallback): VERIFIED & CLOSED (single-lease coordination, SSE/WS scaffolding).
    * `M6-11` (UI-1 Schema-Driven Indicator Settings & Visibility): VERIFIED & CLOSED (`services/api/routers/indicators.py`, SMA, EMA, RSI, MACD, ATR, Supertrend, SMC).
    * `M6-12` (UI-2 Heikin Ashi Chart-Type Switcher UI): VERIFIED & CLOSED (`apps/web/lib/series.js`, `#chartTypeSelect`).
    * `M6-13` (UI-2 Drawing Tools, Persistence & Deletion Bug Fix): VERIFIED & CLOSED (`apps/web/js/drawings.js`, long/short position hit-test padding fix, REST persistence).
    * `M6-14` (UI-1 /paper and /settings Screens Implementation): VERIFIED & CLOSED (Micro Console with "Square Off All", Macro Monitor, 4-tab Settings Modal).
    * `M6-15` (UI-3 API and Data Contract Freeze): VERIFIED & CLOSED (`services/api/schemas/*`, integer-paise amounts, ISO-8601 timestamps).
    * `M6-16` (Read-Only Historical and Expired-Option Candle Viewer): VERIFIED & CLOSED (`services/api/routers/options.py` `/api/v1/options/candles`).
    * `M6-17` (Indicator Sub-Panes and Chart Overlays): VERIFIED & CLOSED (multi-pane RSI/MACD/ATR, main pane overlays for Supertrend & SMC).
    * `M6-18` (UI-1b Option Chain Tab with One-Click Paper Execution & Chart Lines): VERIFIED & CLOSED (`#optionChainTab`, direct order routing, on-chart Entry/SL/TP lines).
  - **Comprehensive Audit Report Generated:** [`reports/stage6_closure/gate_g4_audit_report.md`](file:///c:/Algo/quantview/reports/stage6_closure/gate_g4_audit_report.md).
  - **Verification Suite Statistics:**
    * `pytest -m gate_g4`: **107/107 PASS** in 23.68s.
    * `pytest tests/unit/test_package_boundaries.py`: **7/7 PASS** in 0.47s.
    * Full Repository Suite (`pytest`): **460/460 PASS** with 0 regressions in 49.00s across 40 test files.
    * Static Linter (`ruff check .`): **0 errors, 0 warnings** (All checks passed!).
  - **Runtime Benchmarks Verified:**
    * 5,000-bar candle query latency: **79.26 ms** (SLA $\le 300\text{ ms}$, $+73.6\%$ margin).
    * Multi-strike option chain latency: **102.95 ms** (SLA $\le 300\text{ ms}$, $+65.7\%$ margin).
    * 5-year simulation throughput: **118,400 bars/s** ($11.8\times$ above SLA).
    * 5-year synthetic backtest runtime: **15.20 s** for 1.8M bars (SLA $\le 60.0\text{ s}$).
    * Gateway process memory: **58.4 MB idle RSS**, peak 168.2 MB (SLA $\le 300\text{ MB}$).
  - **Upstream Golden Reference Certified:** `C:\Algo\quant-terminal` bit-for-bit unmodified (0 mutations).
  - **Gate Lockout Confirmed:** Stage 7 Live Broker Daemon and Upstox order execution adapters remain strictly locked out (`NO-GO`) until authorized Stage 7 execution.
  - **FINAL VERDICT:** **GATE G4 PASS & CLOSED. STAGE 6 100% COMPLETE.**
