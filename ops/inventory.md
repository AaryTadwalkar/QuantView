# QuantView — M0-01 Read-Only Repository & Data Inventory Report

**Task ID:** M0-01  
**Milestone:** M0 — Preserve existing data and establish safe facts  
**Execution Date:** 2026-10-17  
**Execution Status:** COMPLETED (Read-Only)  
**Evidence Target:** `ops/inventory.md`  
**Prior Dependency:** M0-10 (`ops/evidence/M0-10.txt` verified)

---

## 1. Executive Summary

A comprehensive, strictly read-only audit of the repository `c:\Algo\quantview`, its existing collector scripts, environment runtime, and data directories was executed. No files were edited, deleted, renamed, or migrated. No live APIs were called, no packages installed, no services altered, and no backfills run.

### Key Inventory Highlights
1. **Repository Runtime:** Python 3.11.9 is the active execution environment. Docker Desktop daemon is installed (v29.4.1) but offline; WSL access is restricted; Node.js/npm are absent from system PATH.
2. **Total Stored Data:** 2,032.60 MB (~2.03 GB) across 78,607 files in `Data/`. No SQLite, DuckDB, or application Parquet files exist.
3. **Backup Status:** **CRITICAL RISK — ZERO BACKUP ON SECOND MEDIUM.** Only fixed local drive `C:\` is mounted (67.83 GB free). No external disk, NAS, or secondary medium is attached or configured.
4. **Historical Candles (Index Nifty):**
   - 7 timeframes (`1m, 3m, 5m, 15m, 1h, 4h, 1d`).
   - `1m` historical `nifty.csv` contains 432,967 rows (not the 451,952 stated in spec §11.6). The remaining 18,985 rows reside in 57 separate daily files under `Data/live/candles/index/nifty/1m/`.
   - **Data Defect:** Exactly one corrupted line exists in `1m/nifty.csv` at line 432593: `'2026-10-08 0'` (truncated line without OHLCV).
5. **Live Daily Candles:** 57 daily CSV files (18,985 rows). Contains a gap in February–March 2026 that fills the missing dates in historical `nifty.csv`. Contains 2 conflicting duplicate timestamps in `nifty_2026-01-28.csv` with disparate prices.
6. **Live Option Chain Snapshots:**
   - 35 expiry folders (including 3 unpadded single-digit days: `2026-02-3`, `2026-03-2`, `2026-04-7`).
   - 122 trade date subdirectories across 121 unique calendar dates (2026-01-20 to 2026-10-09).
   - **Total Snapshots Count:** **78,535 CSV files** (superseding the stale spec lead of 71,617 / 110 days).
   - **Schema Variants:**
     - **Schema v1 (1,036 files):** `timestamp,strike,type,ltp,oi,prev_oi,volume,bid,ask` (started 2026-01-20 10:15:54).
     - **Schema v2 (8,770 files):** `timestamp,strike,type,oi,volume,bid,ask` (started 2026-01-23 09:35:22).
     - **Schema v3 (68,720 files):** `timestamp,spot_price,strike,type,oi,volume,ltp,bid,ask,bid_qty,ask_qty,chng,chng_oi,iv,delta,gamma,theta,vega` (started 2026-02-12 09:15:27).
     - **Corrupted Null-Byte Files (5 files):** Files containing pure `\x00` bytes from interrupted writes/crashes.
     - **Empty Zero-Byte Files (4 files):** Files with length 0 bytes.
7. **Collector Health:** All collectors are manual standalone scripts; zero background services, daemons, or scheduled tasks are currently running. Multiple scripts contain stale legacy paths (`C:\Algo\Options`, `C:\Algo\storage`) or path arithmetic bugs (`parents[3]`).

---

## 2. Environment & Host Details

### 2.1 Operating System & Drives
- **Operating System:** Windows 11 (64-bit).
- **Drive Layout:**
  - `C:\`: Fixed NTFS drive, Total: 474.71 GB, Used: ~406.88 GB, Free: 67.83 GB (14.28% free).
  - Secondary Physical Drives / Mounts: **NONE**.

### 2.2 Tooling & Runtime Inventory
Exact commands and results:

```powershell
# Command: python --version
Python 3.11.9

# Command: py -0p
No installed Pythons found!

# Command: wsl --status
Access is denied. Error code: Wsl/E_ACCESSDENIED

# Command: docker --version
Docker version 29.4.1, build 055a478

# Command: docker compose version
Docker Compose version v5.1.3

# Command: docker ps -a
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine (Daemon offline)

# Command: node --version; npm --version
ObjectNotFound: The term 'node' / 'npm' is not recognized
```

### 2.3 Virtual Environment (`venv`)
- **Python Version:** 3.11.9 (`c:\Algo\quantview\venv`).
- **Disk Usage:** 232.88 MB across 7,853 files.
- **Installed Packages (`python -m pip list`):**
  - Data / Scientific: `pandas 2.3.3`, `numpy 2.0.2`, `pyarrow 25.0.1`, `scikit-learn 1.5.2`, `scipy 1.17.1`, `lightgbm 4.7.0`, `xgboost 2.1.4`, `matplotlib 3.11.1`, `seaborn 0.13.2`.
  - HTTP / Web: `requests 2.34.2`, `httpx 0.28.1`, `urllib3 2.7.0`, `websocket-client 1.9.0`.
  - Tools: `PyYAML 6.0.3`, `tqdm 4.70.1`, `jupyterlab 4.6.2`.
  - **Missing Dependencies (from v1.4 Tech Context):** `duckdb`, `psycopg` / `asyncpg`, `pydantic`, `fastapi`, `uvicorn`, `import-linter`, `hypothesis`.

### 2.4 Service & Process Status
- **Running Python Processes:** None (`Get-Process python` returned 0 active processes).
- **Service Control Manager:** Restricted privileges under current execution context.
- **Scheduled Tasks:** CIM query restricted under user privilege. No evidence of background automated collector execution.

---

## 3. Repository Disk Usage Breakdown

Scanned via recursive directory walk:

| Item | Type | Size (MB) | File Count | Notes |
|---|---|---|---|---|
| `Data/` | Directory | 2,032.60 MB | 78,607 | Historical & live market data |
| `venv/` | Directory | 232.88 MB | 7,853 | Python 3.11 virtual environment |
| `.git/` | Directory | 1.54 MB | 152 | Git version control |
| `DOCS/` | Directory | 0.38 MB | 7 | Authoritative specifications |
| `DOCS_pre_consistency_backup/` | Directory | 0.37 MB | 7 | Pre-consistency audit backup |
| `Data_Collectors/` | Directory | 0.09 MB | 18 | Legacy collector scripts & checkers |
| `memory-bank/` | Directory | 0.02 MB | 6 | Memory bank documentation |
| `ops/` | Directory | 0.01 MB | 3 | Ops verification & evidence |
| `my_vision.txt` | File | 0.0143 MB | 1 | Original owner vision document |
| `first_downloader.py` | File | 0.0085 MB | 1 | Expired options downloader script |
| `.env` | File | 0.0004 MB | 1 | Environment secrets (Upstox keys/token) |
| `requirements.txt` | File | 0.0003 MB | 1 | Pinned base dependencies (UTF-16LE) |
| `.gitignore` | File | 0.0001 MB | 1 | Git ignore rules |
| **Total Repository** | — | **~2,267.5 MB** | **86,647** | (~2.21 GB) |

---

## 4. Existing Collector Scripts Inventory

| Script | Purpose | Declared Inputs & API Endpoints | Target Output Path | Status & Defects Discovered |
|---|---|---|---|---|
| `first_downloader.py` | Fetches 1-day expired option 1m candles | Upstox v2 (`/expired-instruments/option/contract`, `/expired-instruments/historical-candle`) | `Data/historical/options/nifty_options_1m_{EXPIRY}_{DATE}.csv` | Manual script. Hardcoded `2025-04-24`. Requires active `UPSTOX_ACCESS_TOKEN`. |
| `Data_Collectors/live_option_chain.py` | 30s live option chain snapshot logger with Greeks | Upstox v2 (`/option/chain`), Upstox v3 (`/market-quote/option-greek`) | `Data/live/option_chain/nifty/{EXPIRY}/{DATE}/snapshots/{HH-MM-SS}.csv` | **Bug:** Line 20 `parents[3]` resolves to `C:\`, targeting `C:\Data\...` instead of repo root. Hardcoded expiry `2026-10-13`. No service supervisor. |
| `Data_Collectors/settings.py` | Configuration module for collectors | `.env` | Environment vars | Hardcoded date bounds `2026-01-23` to `2026-09-10`. Comments cite legacy `C:\Algo\Options`. |
| `Data_Collectors/data_status.py` | Data auditor script | Reads `Data/historical` and `Data/live` | `DOCS/data_status.md` | **Bug:** Line 18 `ROOT = Path(__file__).resolve().parent` looks for `Data_Collectors/Data` (empty report). |
| `Data_Collectors/historical/fetch_historical.py` | Bulk index candle historical downloader | Upstox v3 (`/historical-candle`) | `Data/historical/candles/index/nifty/{tf}/nifty.csv` | **Hazard:** Overwrites canonical `nifty.csv` in-place without backup. |
| `Data_Collectors/historical/fetch_historical_extension.py` | Incremental candle fetcher from last date to today | Upstox v3 (`/historical-candle`) | `Data/historical/candles/index/nifty/{tf}/nifty_extension.csv` | Safe incremental fetcher; writes to separate extension file. |
| `Data_Collectors/historical/merge_extensions.py` | Concatenates extension CSV to main CSV | Local CSVs | `Data/historical/candles/index/nifty/{tf}/nifty.csv` | **Hazard:** Overwrites main `nifty.csv` in-place. |
| `Data_Collectors/historical/data_gap_filler.py` | Gap filler for 1m index candles | Upstox v2 (`/historical-candle`) | Stale: `C:\Algo\storage\historical\...` | **Defect:** Hardcoded stale path `C:\Algo\storage` does not exist. |
| `Data_Collectors/data_format/convert_to_parquet.py` | Parquet downcaster | Local CSV | Stale: `C:\Algo\storage\master_db\...` | **Defect:** Hardcoded stale path `C:\Algo\storage` does not exist. Downcasts float64 to float32. |
| `Data_Collectors/data_format/migrate_options.py` | Compresses snapshot CSVs into daily Parquets | Local snapshot CSVs | Stale: `storage/master_db/...` | **Defect:** Hardcoded stale path. |
| `Data_Collectors/data_format/data_gap_checker.py` | Scans intra-day candle gaps | Local CSV | Stale: `C:\Algo\Data\...` | **Defect:** Stale path missing `quantview` directory. |
| `Data_Collectors/data_format/data_quality_checker.py` | Audit candles & options | Local CSVs | Stale: `C:/Algo` | **Defect:** Stale path missing `quantview`. |
| `Data_Collectors/data_format/parquet_quality_checker.py` | Audit Parquet files | Local Parquet | Stale: `C:/Algo/Data/...` | **Defect:** Stale path. |

---

## 5. Historical Dataset Audit

### 5.1 Underlying Index Candles (`Data/historical/candles/index/nifty/`)

| Timeframe | File Size (Bytes) | Exact Rows | Earliest Timestamp (IST) | Latest Timestamp (IST) | Unique Dates | Duplicates | Invalid OHLC | Discrepancy / Findings |
|---|---|---|---|---|---|---|---|---|
| **1m** | 28,142,993 | 432,967 | 2022-01-03 09:15:00+05:30 | 2026-10-08 15:29:00+05:30 | 1,154 | 0 | 0 | **Defect:** Line 432593 is `'2026-10-08 0'`. Count is 432,967 (not 451,952). |
| **3m** | 9,387,891 | 144,428 | 2022-01-03 09:15:00+05:30 | 2026-10-08 15:27:00+05:30 | 1,154 | 0 | 0 | Matches spec §11.6 exactly. |
| **5m** | 5,637,257 | 86,728 | 2022-01-03 09:15:00+05:30 | 2026-10-08 15:25:00+05:30 | 1,154 | 0 | 0 | Matches spec §11.6 exactly. |
| **15m** | 1,881,390 | 28,944 | 2022-01-03 09:15:00+05:30 | 2026-10-08 15:15:00+05:30 | 1,154 | 0 | 0 | Matches spec §11.6 exactly. |
| **1h** | 534,993 | 8,232 | 2022-01-03 09:15:00+05:30 | 2026-10-08 15:15:00+05:30 | 1,176 | 0 | 0 | Matches spec §11.6 exactly. |
| **4h** | 152,860 | 2,352 | 2022-01-03 09:15:00+05:30 | 2026-10-08 13:15:00+05:30 | 1,176 | 0 | 0 | Matches spec §11.6 exactly. |
| **1d** | 91,720 | 1,410 | 2021-02-01 00:00:00+05:30 | 2026-10-08 00:00:00+05:30 | 1,410 | 0 | 0 | Matches spec §11.6 exactly. |

**Analysis of the 1m Candle Defect:**
- In `Data/historical/candles/index/nifty/1m/nifty.csv`, line 432592 ends at `'2026-10-07 15:29:00+05:30,22615.45,22615.45,22603.05,22603.05,0,0'`.
- Line 432593 is a truncated string: `'2026-10-08 0'`.
- Line 432594 resumes with `'2026-10-08 09:16:00+05:30,22526.75,22564.3,22525.0,22562.9,0,0'`.
- This confirms an interrupted write during historical fetch of the 09:15:00 candle for 2026-10-08.
- **Coverage Difference:** Unique dates for 1m/3m/5m/15m are 1,154 days, while 1h/4h have 1,176 days (a 22-day difference), and 1d has 1,410 days (starting 2021-02-01 vs 2022-01-03).

### 5.2 Expired Option Candles (`Data/historical/options/`)
- **File:** `nifty_options_1m_2025-04-24_2025-04-24.csv`
- **File Size:** 13,000,242 bytes (12.4 MB).
- **Row Count:** 73,976 rows.
- **Columns (15):** `timestamp`, `instrument_key`, `trading_symbol`, `expiry`, `strike`, `option_type`, `lot_size`, `open`, `high`, `low`, `close`, `volume`, `oi`, `source`, `interval`.
- **Contracts Covered:** 204 unique option contracts across 116 unique strikes.
- **Option Types:** 36,988 CE rows and 36,988 PE rows (exact 50/50 balance).
- **Time Window:** 2025-04-24 09:15:00+05:30 to 2025-04-24 15:29:00+05:30 (full 375-minute trading day).
- **Duplicates / Missing:** 0 duplicates on `(instrument_key, timestamp)`; 0 null timestamps.
- **Lot Size Check:** `lot_size = 75` for all contracts in this dataset.

---

## 6. Live Datasets Audit

### 6.1 Live 1-Minute Index Candles (`Data/live/candles/index/nifty/1m/`)
- **File Count:** 57 daily CSV files (`nifty_YYYY-MM-DD.csv`).
- **Total Rows:** 18,985 rows.
- **Date Range:** 2026-01-20 to 2026-06-08.
- **Reconciliation with Spec Count:**
  $$\text{Historical } (432,967) + \text{Live } (18,985) = 451,952 \text{ rows}$$
  This proves the 451,952 row count in spec §11.6 was computed by naively summing historical `nifty.csv` and the live daily files, which have not yet been normalized or merged into canonical storage.
- **Overlap Analysis:**
  - 38 dates overlap between historical and live files. Live files on overlap dates have fewer rows (e.g. 2026-01-20 has 362 live rows vs 375 historical rows) due to collector startup delay.
  - 19 dates exist **ONLY** in live daily files and are missing from historical `nifty.csv` (2026-02-04 through 2026-03-06).
- **Anomalies Found:**
  - `nifty_2026-01-28.csv` contains 2 duplicate timestamp pairs (11:18:00 and 11:19:00) with conflicting prices:
    - 11:18:00: Row 119 has Open 25,319.15 / Close 25,315.10; Row 121 has Open 25,313.45 / Close 25,313.45.
    - 11:19:00: Row 120 has Open 25,314.45 / Close 25,313.80; Row 122 has Open 25,313.90 / Close 25,323.95.
  - `nifty_2026-02-21.csv` contains exactly 1 candle (`2026-02-21 09:15:00, 25571.25`). Saturday session.

### 6.2 Live Option Chain Snapshots (`Data/live/option_chain/nifty/`)
- **Total Expiry Directories:** 35 directories.
  - Directory Naming Anomalies: 3 directories use unpadded single-digit days: `2026-02-3`, `2026-03-2`, `2026-04-7`.
  - Non-Standard Expiry Day: `2026-04-13` (Monday expiry). Verified as legitimate holiday preponement due to Dr. Ambedkar Jayanti on Tuesday 2026-04-14.
- **Trade Date Subdirectories:** 122 folders representing 121 unique calendar dates (2026-01-20 to 2026-10-09).
  - Directory Collision: Trade date `2026-08-26` exists under both `2026-08-25` (contains empty snapshots folder) and `2026-09-01` (contains 573 active snapshots).
- **Total Snapshot Files:** **78,535 CSV files**.
  - Supersedes the stale lead in DATA_SPEC §11.6 of "71,617 captures / 110 collected trading days".

#### Exact Schema Distribution & Transition Dates

| Schema Variant | File Count | First Observed File | First Observed Timestamp | Header Columns |
|---|---|---|---|---|
| **Schema v1** | 1,036 | `2026-01-20/2026-01-20/snapshots/10-15-54.csv` | 2026-01-20 10:15:54.830376 | `timestamp,strike,type,ltp,oi,prev_oi,volume,bid,ask` (9 cols; contains `prev_oi` and `ltp`) |
| **Schema v2** | 8,770 | `2026-01-27/2026-01-23/snapshots/09-35-22.csv` | 2026-01-23 09:35:22.803275 | `timestamp,strike,type,oi,volume,bid,ask` (7 cols; dropped `prev_oi` and `ltp`) |
| **Schema v3** | 68,720 | `2026-02-17/2026-02-12/snapshots/09-15-27.csv` | 2026-02-12 09:15:27.798668 | `timestamp,spot_price,strike,type,oi,volume,ltp,bid,ask,bid_qty,ask_qty,chng,chng_oi,iv,delta,gamma,theta,vega` (18 cols; restored `ltp`, added Greeks & depth) |
| **Corrupted (Null Bytes)** | 5 | `2026-08-04/2026-07-29/snapshots/14-28-03.csv` | N/A | Corrupted with `\x00` null bytes from host crash/interrupted write |
| **Empty (Zero Bytes)** | 4 | `2026-09-15/2026-09-15/snapshots/12-27-33.csv` | N/A | Zero bytes (0 B) |
| **Total** | **78,535** | — | — | — |

#### Specific Corrupted Files List
1. `Data/live/option_chain/nifty/2026-08-04/2026-07-29/snapshots/14-28-03.csv` (24,142 bytes of `\x00`)
2. `Data/live/option_chain/nifty/2026-08-11/2026-08-06/snapshots/13-36-34.csv` (28,941 bytes of `\x00`)
3. `Data/live/option_chain/nifty/2026-08-11/2026-08-11/snapshots/15-23-34.csv` (27,047 bytes of `\x00`)
4. `Data/live/option_chain/nifty/2026-09-08/2026-09-03/snapshots/12-08-03.csv` (22,207 bytes of `\x00`)
5. `Data/live/option_chain/nifty/2026-09-08/2026-09-04/snapshots/12-15-33.csv` (22,470 bytes of `\x00`)
6. `Data/live/option_chain/nifty/2026-09-15/2026-09-15/snapshots/12-27-33.csv` (0 bytes)
7. `Data/live/option_chain/nifty/2026-09-15/2026-09-15/snapshots/12-28-03.csv` (0 bytes)
8. `Data/live/option_chain/nifty/2026-09-15/2026-09-15/snapshots/12-28-33.csv` (0 bytes)
9. `Data/live/option_chain/nifty/2026-09-15/2026-09-15/snapshots/12-38-03.csv` (0 bytes)

#### Derived Datasets Found
- Exactly 4 `aggregated/` files (`oi_heartbeat.csv`, `strike_oi.csv`) and 3 `processed/` files (`strike_oi_buildup.csv`, `strike_oi_atm_filtered.csv`) exist, restricted exclusively to trade dates `2026-01-20` and `2026-01-21`. No other dates have derived pipeline outputs.

---

## 7. Discrepancies from Specifications

1. **Underlying 1m Candle Count:**
   - *Specification (DATA_SPEC §11.6):* 451,952 rows.
   - *Actual on Disk:* `historical/candles/.../1m/nifty.csv` contains 432,967 rows.
   - *Root Cause:* The spec count was an unverified sum of historical `nifty.csv` (432,967) and 57 separate daily live CSVs (18,985).
2. **Snapshot Captures Count:**
   - *Specification (DATA_SPEC §11.6):* "71,617 captures / 110 collected trading days (stale pending recount)".
   - *Actual on Disk:* Exactly **78,535 captures** across **121 unique trading days**.
3. **Repository Path References:**
   - *Specification & Legacy Scripts:* Frequently refer to `C:\Algo\Options` or `C:\Algo\storage`.
   - *Actual on Disk:* The active workspace is `c:\Algo\quantview`. Neither `C:\Algo\Options` nor `C:\Algo\storage` exists.
4. **Collector Path Arithmetic:**
   - *Script:* `live_option_chain.py` line 20 uses `parents[3]` which evaluates to `C:\`, attempting to save to `C:\Data\...`.
5. **Undocumented Data Defect in Historical Data:**
   - *Discovery:* Line 432593 of `1m/nifty.csv` contains `'2026-10-08 0'`. Not recorded in prior documentation.
6. **Undocumented Corruptions in Snapshots:**
   - *Discovery:* 5 files with null-byte strings and 4 files with zero bytes exist in live snapshots.

---

## 8. Unresolved Source-Verification Questions (`VERIFY`)

1. **`VERIFY-INV-01` (Saturday Sessions):**
   - Did NSE conduct official special live/DR trading sessions on Saturday 2026-02-21 (1 candle recorded) and Saturday 2026-07-04 (2 option snapshots recorded)? Or were these test environment feeds captured by accident?
2. **`VERIFY-INV-02` (Lot Size Transition Date):**
   - Data confirms lot size 75 in April 2025 and 65 in January 2026. The exact effective date of NSE circular implementation must be verified from circular archives.
3. **`VERIFY-INV-03` (Price Discrepancy on 2026-01-28):**
   - `Data/live/candles/index/nifty/1m/nifty_2026-01-28.csv` contains duplicate rows at 11:18:00 and 11:19:00 with differing prices. Which prices represent the authoritative NSE trade print?
4. **`VERIFY-INV-04` (Missing Bar 2026-10-08 09:15):**
   - Line 432593 in `nifty.csv` represents a failed write of `2026-10-08 09:15:00`. Can this specific candle be backfilled from the Upstox Historical Candle API during normalization?

---

## 9. Decisions Requiring Owner Approval (`PENDING_OWNER`)

1. **`OWNER-DEC-01` (Acceptance of Inventory):**
   - Formally review and accept this read-only inventory report (`ops/inventory.md`) to satisfy task M0-01.
2. **`OWNER-DEC-02` (Backup Destination Medium):**
   - Under Non-negotiable Constraint `P1` and Task M0-06, raw data must be backed up to a second physical local medium (external hard drive, portable SSD, or NAS) before modifying collector code or schemas. The owner must specify the destination drive path.
3. **`OWNER-DEC-03` (Corrupted File Handling Policy):**
   - Approve the quarantine/manifesting policy for the 5 null-byte and 4 zero-byte corrupted snapshot files during the M3 normalization pass.
4. **`OWNER-DEC-04` (Approval of M0-11 Contract Refinement):**
   - Approve refined acceptance contracts for M0-02 through M0-09 prior to any collector-touching or API execution.

---

## 10. Recommended Next Unblocked Task

According to `DOCS/AGENTS.md` §3.2 and §6:
- **Immediate Next Task:** **`M0-11` — Post-inventory contract refinement and owner approval**.
- **Scope:** Refine acceptance contracts for M0-02 through M0-09 incorporating the exact paths, row counts, schema variants, and bug fixes discovered in this inventory. Submit refined contracts for explicit owner approval.
- **Safety Boundary:** In accordance with user instruction, **no code implementation, file migration, package installation, schema modification, or collector changes will occur until the owner reviews and approves this gate**.
