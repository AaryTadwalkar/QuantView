# QuantView — Phase 2A: Full-Batch Staging Preparation Completion Report

**Report Date:** 2026-10-23  
**Status:** COMPLETED — ALL 4 DATASETS PASS  
**Execution Environment:** `c:\Algo\quantview` (Windows 11, Python 3.11)  
**Git HEAD Commit:** `e46530db272f4b46a898ddb00ab7261bae4e25ec`  
**Lake Publication Status:** **STRICTLY UNPUBLISHED** (`Data/lake/` was NOT created or modified; zero active manifests updated)  

---

## 1. Executive Summary & Verdicts

Phase 2A full-batch data preparation and validation in staging has been successfully completed in full compliance with the canonical specifications (`DOCS/QUANTVIEW_DATA_SPEC.md`, `DOCS/QUANTVIEW_MASTER_SPEC.md`, `DOCS/AGENTS.md`) and all Phase 2A operational boundaries.

All transformations were performed **100% offline**, reading strictly from immutable raw/staging sources and writing atomically into the dedicated Phase 2A isolation directory: `staging/lake_preparation_phase2a/`. The existing Phase 1 sample artifacts (`staging/lake_preparation/`) and all source datasets in `Data/` remain **100% untouched**.

| Dataset Workstream | Input Records / Files | Output Partitions / Rows | Status / Verdict | Key Validation Result |
| :--- | :--- | :--- | :--- | :--- |
| **A. Expired Options** | 446 CSVs / 20,332,421 rows | 95 Parquets / 20,332,421 rows | **PASS** | Exact 1:1 row reconciliation; exact `decimal128(9, 2)` strikes; 8 negative volumes clamped & flagged. |
| **B. NIFTY Underlying Candles** | 432,968 historical lines + 2 staged CSVs | 64 Parquets / 437,008 rows | **PASS** | 435,591 1m rows + 1,417 1d rows; Line 432594 quarantined with zero source modification; 0 duplicates. |
| **C. India VIX** | 2 staged CSVs (166,939 1m + 446 1d) | 25 Parquets / 167,385 rows | **PASS** | 100% session reconciliation (-311 delta bars accounted for); genuine 0 volume & non-derivative `oi = 0` enforced. |
| **D. Option Snapshots** | 82,283 files (127 sessions, 36 expiries) | 0 active lake writes (Deferred) | **PASS** | Full-batch compaction excluded; category arithmetic resolved (72,468 v3 + 9,806 v1 + 4 empty + 5 corrupt = 82,283). |
| **Phase 2A Manifest** | 184 Parquet files | 20,936,814 total rows (225.06 MB) | **PASS** | Cryptographic dry-run manifest compiled with SHA-256 hashes across all 184 files. |

---

## 2. Preflight Check Verification

All 6 mandatory preflight checks were executed and verified prior to and after batch execution:

1. **Repository Commit & Working Tree:**
   - Commit: `e46530db272f4b46a898ddb00ab7261bae4e25ec`.
   - Verified clean state; no unintended source edits.
2. **Canonical Schema Source of Truth:**
   - Exclusively sourced from `packages/data/schemas/` (`candles.py`, `snapshots.py`, `__init__.py`).
   - Zero competing or duplicate schema definitions exist in `tools/lake/`.
3. **Source Counts & Manifest Alignment:**
   - 446 daily expired option CSVs in `staging/expired_options/` verified.
   - 15,725 companion manifests in `Data/raw/upstox_rest/expired_api/` verified.
   - India VIX 1m (166,939 rows) and 1d (446 rows) verified.
   - NIFTY historical 1m (432,967 rows + 1 malformed line) verified.
   - Live option chain snapshots: 82,283 files in `Data/live/option_chain/nifty/` verified.
4. **Output Path Isolation:**
   - Destination isolated exclusively under `staging/lake_preparation_phase2a/`.
   - Phase 1 sample directory (`staging/lake_preparation/`) remains completely untouched.
   - Active lake directory `Data/lake/` was NOT created.
5. **Disk Space Verification:**
   - Drive C free space: **66.84 GB free** (Total Phase 2A output: 225.06 MB).
6. **Tooling Destination Support:**
   - Added `--output-dir` / `--prep-root` CLI parameters with `<RULE[user_global]>` compliant docstrings across all tools in `tools/lake/`.

---

## 3. Detailed Workstream Execution & Reconciliation

### 3.1 Dataset A: Expired NIFTY Options
- **Source Input:** 446 daily CSV files (`staging/expired_options/nifty_options_1m_*.csv`) covering trading horizon `2025-01-01` to `2026-10-19`.
- **Source Row Count:** Exactly **20,332,421 rows**.
- **Lake Staging Output:** 95 expiry partitions under `staging/lake_preparation_phase2a/option_candles/underlying=NIFTY/expiry=YYYY-MM-DD/part-0.parquet`.
- **Output Row Count:** Exactly **20,332,421 rows** (**0 row discrepancy, 100% reconciled**).
- **Parquet Storage Size:** **205.27 MB** (215,242,484 bytes) compressed via zstd.
- **Data Quality & Compliance Invariants:**
  - **Exact Decimal Strikes:** Every strike price is stored strictly as `decimal128(9, 2)` (e.g. `24500.00`), preventing binary floating-point join inaccuracies.
  - **Negative-Volume Policy (DATA Spec §11.3):** Exactly **8 negative volume bars** were encountered (all 8 within Expiry `2025-02-06`), clamped to `0`, and tagged with `VENDOR_NEGATIVE_VOLUME` in `quality_flags`.
  - **Causal Point-in-Time Availability:** Intraday 1-minute bars strictly enforce `available_at = ts_end`.
  - **Deterministic Ordering:** Partitions are sorted stably by `(ts_start, strike, option_type, contract_id)`.
  - **Quarantined / Rejected Rows:** 0 rows quarantined or dropped.

### 3.2 Dataset B: NIFTY 50 Underlying Candles
- **Source Input:**
  - Historical 1-minute: `Data/historical/candles/index/nifty/1m/nifty.csv` (432,968 physical lines).
  - Staged October 1-minute extensions: `staging/underlying_candles/` (2,625 rows across 7 sessions: `2026-10-09` to `2026-10-19`).
  - Historical Daily: `Data/historical/candles/index/nifty/1d/nifty.csv` (1,410 rows) + staged October daily extensions (7 rows).
- **Defensive Quarantine of Malformed Physical Line:**
  - Physical Line 432594 (`'2026-10-08 0    \n'`) was defensively detected and quarantined into `quarantined_records` with flag `TRUNCATED_LINE`.
  - Zero modifications were made to the source historical CSV file.
- **Lake Staging Output:**
  - **1-Minute Series:** 58 monthly partitions (`interval=1m/year=YYYY/month=MM/part-0.parquet`) containing **435,591 rows** (432,966 valid historical + 2,625 staged October extensions; 0 duplicates, 1 quarantined).
  - **Daily Series:** 6 yearly partitions (`interval=1d/year=YYYY/part-0.parquet`) containing **1,417 rows** (1,410 historical + 7 staged October extensions; 0 quarantined).
- **Parquet Storage Size:** **15.41 MB** across 64 Parquet files.
- **Causal Availability Invariants:**
  - 1-minute bars enforce `available_at = ts_end`.
  - Daily bars enforce `available_at = 15:30:00 IST` (`10:00:00 UTC`, session close).

### 3.3 Dataset C: India VIX Index Candles
- **Source Input:** Staged 1-minute (`166,939 rows`) and daily (`446 rows`) CSV files under `staging/india_vix/`.
- **Lake Staging Output:**
  - **1-Minute Series:** 22 monthly partitions (`interval=1m/year=YYYY/month=MM/part-0.parquet`) containing **166,939 rows** across 446 sessions.
  - **Daily Series:** 3 yearly partitions (`interval=1d/year=YYYY/part-0.parquet`) containing **446 rows**.
- **Parquet Storage Size:** **4.38 MB** across 25 Parquet files.
- **Non-Derivative Invariants:**
  - Index invariant `oi = 0` and `is_derivative = False` strictly enforced.
  - Source-provided genuine `volume = 0` preserved bit-for-bit without synthetic fabrication.
- **Session-by-Session Coverage & Reconciliation:**
  - Expected regular bars ($446 \times 375$): 167,250 bars.
  - Actual observed continuous bars: 166,939 bars.
  - Net Delta: **-311 bars**, reconciled down to the single bar:
    * Diwali Muhurat Trading (`2025-10-21`): 60 bars (Delta: **-315 bars**).
    * Extended sessions (e.g. `2025-04-25`, `2025-05-08`): **+7 bars**.
    * Shortened sessions (e.g. `2025-03-25`, `2025-04-04`, `2025-04-23`): **-3 bars**.
    * Net Discrepancy: Exactly **0 unexplained bars**.
  - Documented in `reports/india_vix_session_coverage_report.json`.

---

## 4. Dataset D: Snapshot Inventory Category Arithmetic Audit

Full-batch snapshot compaction was **strictly excluded** from Phase 2A per Section 3.D. An offline, high-performance directory entry audit was performed across `Data/live/option_chain/nifty/` and the root `Data/` folder to resolve category arithmetic and catalog pre-compaction inventory:

### 4.1 Snapshot Header & File-Version Breakdown
Every single snapshot CSV file was inspected by reading its physical header:
- **Total Snapshot Files:** **82,283 files** (2,044.53 MB raw uncompressed) across 36 expiries and 127 trading sessions.
- **Version 3 (Full with Greeks / $\ge 20$ columns):** **72,468 files** (88.07%).
- **Version 1 (Legacy / $\le 12$ columns):** **9,806 files** (11.92%).
- **Version 2 (Intermediate / 13–19 columns):** **0 files** (0.00%).
- **0-Byte Empty Files:** **4 files** (0.005%):
  * `2026-09-15/2026-09-15/snapshots/12-27-33.csv`
  * `2026-09-15/2026-09-15/snapshots/12-28-03.csv`
  * `2026-09-15/2026-09-15/snapshots/12-28-33.csv`
  * `2026-09-15/2026-09-15/snapshots/12-38-03.csv`
- **Null-Byte / Corrupted Files:** **5 files** (0.006%):
  * `2026-08-04/2026-07-29/snapshots/14-28-03.csv`
  * `2026-08-11/2026-08-06/snapshots/13-36-34.csv`
  * `2026-08-11/2026-08-11/snapshots/15-23-34.csv`
  * `2026-09-08/2026-09-03/snapshots/12-08-03.csv`
  * `2026-09-08/2026-09-04/snapshots/12-15-33.csv`
- **Other / Unclassified:** **0 files**.
- **Category Sum:** $72,468 + 9,806 + 4 + 5 = \mathbf{82,283\text{ files}}$. **Discrepancy = 0**.

### 4.2 Resolution of `Data/` Category Arithmetic
The exact file count arithmetic across the entire `Data/` directory (113,385 total files) is resolved:
1. `Data/live/option_chain/nifty/`: **82,283 files** (Option chain snapshots).
2. `Data/live/candles/index/nifty/1m/`: **64 files** (Live daily NIFTY candles).
   - Total `Data/live/`: $82,283 + 64 = \mathbf{82,347\text{ files}}$.
3. `Data/raw/upstox_rest/`: **31,030 files** ($15,251\text{ gz} + 15,725\text{ manifests} + 27\text{ vix gz} + 27\text{ vix manifests}$).
4. `Data/historical/candles/index/nifty/`: **8 files** (Historical CSV series across intervals).
   - **Grand Total in `Data/`:** $82,347 + 31,030 + 8 = \mathbf{113,385\text{ files}}$ (Exact bit-for-bit reconciliation).

---

## 5. Phase 2A Manifest & Cryptographic Provenance

The Phase 2A publication manifest was generated at [`staging/lake_preparation_phase2a/manifest_phase2a.json`](file:///c:/Algo/quantview/staging/lake_preparation_phase2a/manifest_phase2a.json) recording SHA-256 hashes, byte sizes, and row counts for every single prepared partition:

- **Manifest Type:** `QUANTVIEW_LAKE_DRY_RUN_PUBLICATION_MANIFEST`
- **Lake Preparation Root:** `staging/lake_preparation_phase2a`
- **Active Lake Published Status:** `false`
- **Active Pointer Updated Status:** `false`
- **Total Prepared Files:** **184 Parquet files**
- **Total Prepared Rows:** **20,936,814 rows**
- **Total Prepared Size:** **225.06 MB** (235,997,274 bytes)

### Summary Breakdown by Dataset
```
  * option_candles            :  95 files | 20,332,421 rows |   205.27 MB
  * underlying_candles        :  64 files |    437,008 rows |    15.41 MB
  * india_vix                 :  25 files |    167,385 rows |     4.38 MB
  * option_snapshot_captures  :   0 files |          0 rows |     0.00 MB  (Excluded in 2A)
  * option_snapshot_rows      :   0 files |          0 rows |     0.00 MB  (Excluded in 2A)
```

---

## 6. Test Suite & Specification Verification

- **Automated Unit & Contract Tests:**
  - Command: `.\venv\Scripts\python.exe -m unittest discover -s tests/unit -p "test_*.py"`
  - Result: **Ran 51 tests in 1.40s. OK (0 skipped, 0 failures, 0 errors)**.
- **Documentation Linter:**
  - Command: `.\venv\Scripts\python.exe tools/qv_check.py lint DOCS`
  - Result: `tasks=114 active=113 days=262.5 gates=G0a,G0,G1,G2a,G2b,G3,G4,G5,G6 | LINT: PASS (0)`.
- **Documentation Consistency Suite:**
  - Command: `.\venv\Scripts\python.exe ops/verify_docs_consistency.py`
  - Result: **Checks A through M PASS with 0 defects**.

---

## 7. Exact Reproduction Commands

To reproduce the Phase 2A staging preparation end-to-end:

```powershell
# 1. India VIX preparation
.\venv\Scripts\python.exe tools/lake/promote_india_vix.py --output-dir staging/lake_preparation_phase2a/india_vix

# 2. Underlying NIFTY candles preparation
.\venv\Scripts\python.exe tools/lake/promote_underlying_candles.py --output-dir staging/lake_preparation_phase2a/underlying_candles

# 3. Expired option candles preparation
.\venv\Scripts\python.exe tools/lake/promote_option_candles.py --output-dir staging/lake_preparation_phase2a/option_candles

# 4. Phase 2A dry-run manifest generation
.\venv\Scripts\python.exe tools/lake/prepare_dry_run_manifest.py --prep-root staging/lake_preparation_phase2a --manifest-filename manifest_phase2a.json

# 5. Full test suite validation
.\venv\Scripts\python.exe -m unittest discover -s tests/unit -p "test_*.py"
.\venv\Scripts\python.exe tools/qv_check.py lint DOCS
.\venv\Scripts\python.exe ops/verify_docs_consistency.py
```

---

## 8. Mandatory Stop Condition & Sign-off

Phase 2A is **100% COMPLETE**. Per Section 6 of the authorization prompt:
- **`Data/lake/` was NOT created or written to.**
- **Zero active manifests or database pointers have been updated.**
- **No data has been published to the active data lake.**
- **Full-batch snapshot compaction has NOT been executed.**
- **Zero git commits or pushes have been performed.**

Execution is now halted. Awaiting explicit owner authorization before proceeding to Phase 2B or active lake publication.
