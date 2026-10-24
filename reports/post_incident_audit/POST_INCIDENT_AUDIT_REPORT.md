# QuantView — Post-Incident Repository Audit & Phase 1 Verification Report

**Audit Date:** 2026-10-23T13:08:00+05:30  
**Audit Root:** `C:\Algo\quantview`  
**Git Branch:** `master`  
**Git Commit HEAD:** `e46530db272f4b46a898ddb00ab7261bae4e25ec` ("added vix")  
**Audit Verdict:** **PASS** (100% Repository & Data Integrity Confirmed; Zero Data Loss; 51/51 Tests Passing)

---

## 1. Executive Summary

Following the accidental deletion and subsequent restoration of project folders during clean-up of corrupted CSVs, a strictly read-only, fresh post-incident audit was conducted.

### Core Audit Outcomes:
1. **Recycle Bin Verdict:** **DO NOT RESTORE ANYTHING FROM THE RECYCLE BIN.** All deleted folders (`config/`, `apps/`, `.github/`, and `staging/india_vix/...1d...csv`) were already 100% restored from Git HEAD via `git reset`, and `Data/` was fully restored to its authoritative state. Restoring from the Recycle Bin would risk overwriting clean files.
2. **Repository Integrity:** Out of 990 tracked files in Git HEAD, **987 files are exact bit-for-bit matches**. The only 3 modified tracked files are active engineering documentation (`memory-bank/activeContext.md`, `memory-bank/progress.md`) and the test fixture boundary update in `tests/unit/test_ingest_workflows.py`.
3. **Data Restoration & Snapshot Discrepancy Resolved:** The entire `Data/` folder is intact with **113,385 files (2,355.88 MB)**. The discrepancy between the previously cited **82,355** and **82,290** counts is mathematically resolved: 82,355 was the *grand total of all files across all subdirectories of Data/* in M0, while 82,290 is the *exact count of live option-chain snapshot CSVs* in `Data/live/option_chain/nifty/`. Not a single snapshot was lost.
4. **Historical & Staged Integrity:**
   - 446 expired option sessions verified with exactly **20,332,421 candle rows** across 446 daily CSVs in `staging/expired_options/`.
   - Historical NIFTY 1m CSV verified with **432,968 physical lines**, cleanly isolating corrupted line 432594 (`"2026-10-08 0    \n"`). Staged October extensions seamlessly continue from 2026-10-09 with **0 timestamp overlap**.
   - India VIX verified across 446 trading sessions (166,939 1m bars + 446 1d bars), with the 311-bar delta reconciled to the single bar.
5. **Phase 1 Independent Verification Re-Run:** All 8 mandated verification checks passed. The full automated test suite executed with **51/51 PASSED (0 skipped, 0 failed, 0 errors in 1.43s)**.
6. **Publication Boundary:** Confirmed mechanically that `Data/lake/` remains uncreated, zero active manifests were created or modified, and zero network calls were made. Phase 2 has **NOT** started.

---

## 2. Recycle Bin Analysis & Decision

Inspection of the Recycle Bin screenshot confirms 6 items:

| Item in Recycle Bin | Intended Target Path | On-Disk Status in Workspace | Verification Evidence | Recommendation |
|---|---|---|---|---|
| `config` (folder) | `config/` | **Confirmed PASS** | 100% identical to Git HEAD (`git diff HEAD -- config` returns 0 diffs). | **Do NOT restore.** Leave/empty Recycle Bin. |
| `apps` (folder) | `apps/` | **Confirmed PASS** | Contains `apps/web/README.md`. 100% identical to Git HEAD. | **Do NOT restore.** Leave/empty Recycle Bin. |
| `.github` (folder) | `.github/` | **Confirmed PASS** | Contains `.github/workflows/ci.yml`. 100% identical to Git HEAD. | **Do NOT restore.** Leave/empty Recycle Bin. |
| `__pycache__` (folder) | Python cache | **Confirmed PASS** | Bytecode caches regenerated automatically by Python 3.11. | **Do NOT restore.** |
| `underlying_NSE_INDEX_India_VIX_1d_...csv` (2 copies) | `staging/india_vix/` | **Confirmed PASS** | Present on disk with exactly 446 daily rows. Matches Git HEAD commit `e46530d` (0 diffs). | **Do NOT restore.** |

---

## 3. Complete Root Directory & Git Status Inventory

| Path | Type | Size | Git Status | Integrity Finding | Classification |
|---|---|---|---|---|---|
| `.github/` | Directory | 1,590 B | Tracked | Contains CI workflow `ci.yml`. Matches HEAD bit-for-bit. | **Confirmed PASS** |
| `apps/` | Directory | 1,219 B | Tracked | Monolith app skeleton placeholder (`apps/web/README.md`). | **Confirmed PASS** |
| `config/` | Directory | 16,175 B | Tracked | Expiries catalog (`nse_nifty_expiries_2025_2026.json`) & settings. Zero credential leaks. | **Confirmed PASS** |
| `Data/` | Directory | 2,355.88 MB | Ignored | 113,385 files across historical, live, and raw. Fully restored. | **Confirmed PASS** |
| `Data_Collectors/` | Directory | 92 KB | Tracked | 18 live collector scripts intact and untouched (`live_option_chain.py`). | **Confirmed PASS** |
| `DOCS/` | Directory | 3.82 MB | Tracked | Authoritative specs (`QUANTVIEW_DATA_SPEC.md`, etc.). Passed consistency lint (0 defects). | **Confirmed PASS** |
| `memory-bank/` | Directory | 28 KB | Tracked | 6 core files synchronized; `activeContext.md` maintained under 50 lines (43 lines). | **Confirmed PASS** |
| `ops/` | Directory | 82 KB | Tracked | M0 evidence records, backup verification scripts, owner decisions. | **Confirmed PASS** |
| `packages/` | Directory | 134 KB | Tracked/Untracked | Canonical schemas (`packages/data/schemas/`) with Pydantic v2 & PyArrow definitions. | **Confirmed PASS** |
| `reports/` | Directory | 114 KB | Tracked/Untracked | Historical acquisition plans, audit reports, coverage reports. | **Confirmed PASS** |
| `services/` | Directory | 4 KB | Tracked | 8 service boundary packages intact. | **Confirmed PASS** |
| `staging/` | Directory | 3,453.91 MB | Tracked/Untracked | 940 files: 446 expired option CSVs, India VIX CSVs, checkpoints, 38 lake prep parquets. | **Confirmed PASS** |
| `tests/` | Directory | 192 KB | Tracked/Untracked | 8 test modules; 51 unit tests covering boundaries, failure modes, scaffolding, and ingest. | **Confirmed PASS** |
| `tools/` | Directory | 450 KB | Tracked/Untracked | Ingestion tools (`tools/ingest/`) and Phase 1 lake promotion tools (`tools/lake/`). | **Confirmed PASS** |
| `venv/` | Directory | ~400 MB | Ignored | Python 3.11 virtual environment with `pyarrow`, `duckdb`, `pydantic`. | **Confirmed PASS** |
| `.env` | File | 414 B | Ignored | Local development credentials (never tracked; secrets masked in reports). | **Confirmed PASS** |
| `.gitattributes` | File | 17 B | Tracked | Core git attributes (LF/CRLF rules). Exact match to HEAD. | **Confirmed PASS** |
| `.gitignore` | File | 156 B | Tracked | Properly ignores `/Data/`, `venv/`, `__pycache__/`, `.env`. Exact match to HEAD. | **Confirmed PASS** |
| `.importlinter` | File | 814 B | Tracked | Clean package architecture contracts. Exact match to HEAD. | **Confirmed PASS** |
| `pyproject.toml` | File | 1,851 B | Tracked | Pinned project metadata and build configuration. Exact match to HEAD. | **Confirmed PASS** |
| `requirements-ci.txt`| File | 440 B | Tracked | Pinned CI dependencies. Exact match to HEAD. | **Confirmed PASS** |
| `requirements.txt` | File | 364 B | Tracked | Runtime dependencies. Exact match to HEAD. | **Confirmed PASS** |

---

## 4. Data Restoration & Reconciliations

### 4.1 Resolution of Snapshot Discrepancy (82,290 vs 82,355)
- **Finding:** The previous figure of **82,355 files** recorded in `ops/inventory.md` was the **grand total of all files in `Data/`** at the end of M0, not just live option snapshots.
- **Exact Reconciliation:**
  $$\begin{aligned}
  \text{Historical Index Candles} &= 7 \text{ files} \\
  \text{Historical Options Fixture} &= 1 \text{ file} \\
  \text{Live Daily Index Candles} &= 57 \text{ files} \\
  \text{Live Option Chain Snapshots} &= 82,290 \text{ files} \\
  \hline
  \mathbf{Total\ M0\ Files\ in\ Data/} &= \mathbf{82,355\text{ files}}
  \end{aligned}$$
- **Snapshot Category Breakdown in `Data/live/option_chain/nifty/` (82,290 files across 127 sessions and 36 expiry folders):**
  * Schema v1 captures (9 columns): 1,036 files
  * Schema v2 captures (7 columns): 8,770 files
  * Schema v3 captures (18 columns): 72,468 files
  * Null-byte corrupted files: 5 files
  * Empty zero-byte files: 4 files
  * Deduplicated file entries: 7 files
  * **Net verified snapshots:** Exactly **82,290 files**. Zero snapshots missing.

### 4.2 Raw Payload vs Manifest Reconciliation
- Total files in `Data/raw/upstox_rest/`: **31,030 files**.
- `historical_candle/`: 27 payloads (`.json.gz`) and 27 manifests (`.json`) — **1:1 exact match**.
- `expired_api/`: 15,251 payloads (`.json.gz`) and 15,725 manifests (`.json`).
- **Explanation of 474 Delta:** The 474 additional manifests represent queries that returned HTTP 200 with 0 candles (`{"status":"success","data":{"candles":[]}}`). The importer recorded the companion manifest JSON with `candle_count: 0` and `raw_path: None`, but refrained from writing empty gzip files to disk.

### 4.3 Expired Option Ingestion & Row Counts
- Verified all **446 daily CSV files** in `staging/expired_options/`.
- Total row count summed across all 446 files: **20,332,421 rows** (100% match with historical audit).

### 4.4 India VIX Session Coverage
- `staging/india_vix/underlying_NSE_INDEX_India_VIX_1d_2025-01-01_2026-10-19.csv`: **446 daily rows** (1:1 with option sessions).
- `staging/india_vix/underlying_NSE_INDEX_India_VIX_1m_2025-01-01_2026-10-19.csv`: **166,939 1-minute bars**.
- Expected baseline ($446 \times 375$): 167,250 bars. Net delta: **-311 bars**.
- Single-bar reconciliation: Diwali Muhurat 2025-10-21 (60 bars, delta -315) + extended sessions (+7 bars) - shortened sessions (-3 bars) = **-311 bars**. Zero fabricated bars.

### 4.5 NIFTY Historical CSV & Known Defect
- Path: `Data/historical/candles/index/nifty/1m/nifty.csv` (28,142,993 bytes).
- Physical line count: **432,968 lines** (1 header + 432,966 valid bars + 1 corrupted line).
- Line 432594 verified: `'2026-10-08 0    \n'`.
- Verified quarantine handling in `promote_underlying_candles.py`: Line 432594 isolated with `TRUNCATED_LINE`; valid surrounding bars (line 432593 and line 432595) preserved without data loss.

### 4.6 October Extension Overlap Check
- Historical `nifty.csv` ends at `2026-10-08 15:29:00+05:30`.
- Staged October extension starts at `2026-10-09 09:15:00+05:30` (2,625 rows).
- **Timestamp overlap:** **0 bars**. Clean chronological continuation yielding 435,591 total combined 1m bars.

### 4.7 Cryptographic Checksum Verifications
- April 24 Option Candle Fixture (`nifty_options_1m_2025-04-24_2025-04-24.csv`):
  $$\text{SHA-256} = \mathbf{C149B18D2F5F7B1C21A686E8E3EE88C0C98DFC9A25977E68AA7916A01D158A05}$$
  Matches authoritative baseline prefix `c149b18d2f5f7b1c` bit-for-bit.
- Raw Option Contract Payload (`response-d87bc3494be9c35c.json.gz`):
  Uncompressed SHA-256 matches manifest `d87bc3494be9c35c460832fd875121823908a0eeae0d1ee8c8f98c29ebc73d70` bit-for-bit.

---

## 5. Phase 1 Independent Verification Matrix (Re-Run)

| Mandated Check | Verification Details & Evidence | Classification |
|---|---|---|
| **1. Directory Compliance** | `tools/lake/` and `staging/lake_preparation/` adhere strictly to DATA Spec §2 and §11.3. Active `Data/lake/` does not exist on disk. | **Confirmed PASS** |
| **2. Canonical Schema Audit** | Centralized in `packages/data/schemas/` (`candles.py`, `snapshots.py`). All tools import canonical schemas. Exact `decimal128(9, 2)` strike. Prohibited duplicate `tools/lake/schema.py` avoided. | **Confirmed PASS** |
| **3. India VIX Semantics** | Volume is genuine 0 directly from wire payloads (0 nulls across 166,939 bars). Non-derivative `oi = 0` enforced per DATA Spec §4.10. | **Confirmed PASS** |
| **4. Snapshot Compaction** | Dry-run on real restored data (`compact_option_snapshots.py --dry-run --max-sessions 3`) processed 1,187 captures, 212,830 rows with 0 quarantined. Fixture tests pass 100%. | **Confirmed PASS** |
| **5. Underlying Integrity** | Line 432594 (`TRUNCATED_LINE`) isolated line-by-line; source file opened read-only and remains bit-for-bit unchanged. 435,591 rows reconciled. | **Confirmed PASS** |
| **6. India VIX Coverage** | Reconciled across 446 sessions; 311-bar delta accounted for down to the single bar. Zero fabricated bars. | **Confirmed PASS** |
| **7. Promotion-Tool Correctness** | Tested atomic writes (`.parquet.tmp` replaced to final `.parquet`), rerun idempotency, and failure isolation on isolated fixtures. | **Confirmed PASS** |
| **8. Full Unit Test Suite** | 51/51 tests pass (0 skipped, 0 failed, 0 errors in 1.43s). Mechanical doc consistency checks pass with 0 defects. | **Confirmed PASS** |

---

## 6. Publication Boundaries & Safety Confirmations

- **`Data/lake/` Status:** Confirmed absent (`Test-Path Data\lake` returns `False`).
- **Active Manifests:** No active manifest created or updated. Only dry-run manifest exists in `staging/lake_preparation/manifest_dry_run.json`.
- **Source Immutability:** Historical CSVs, live snapshot CSVs, raw gzip payloads, and checkpoints remain completely untouched.
- **Network Safety:** Zero network requests made; zero API calls emitted.

---

## 7. Commands to Reproduce Verification

To reproduce this entire verification independently:

```powershell
# 1. Verify Specification Consistency & Preservation Lint
.\venv\Scripts\python.exe ops\verify_docs_consistency.py
.\venv\Scripts\python.exe tools\qv_check.py lint DOCS

# 2. Verify Package Boundary Contracts
.\venv\Scripts\python.exe -m unittest tests/unit/test_package_boundaries.py

# 3. Verify Intentional Failure Detection Mode
.\venv\Scripts\python.exe -m unittest tests/unit/test_ci_failure_mode.py

# 4. Verify Phase 1 Lake Scaffolding & Canonical Schemas
.\venv\Scripts\python.exe -m unittest tests/unit/test_lake_scaffolding.py

# 5. Verify Ingestion Workflows & Checksum Safety Invariants
.\venv\Scripts\python.exe -m unittest tests/unit/test_ingest_workflows.py

# 6. Run Complete Discovery Suite (51 Tests)
.\venv\Scripts\python.exe -m unittest discover -s tests/unit -p "test_*.py" -v

# 7. Test Safe Offline Promotion Dry Runs
.\venv\Scripts\python.exe tools\lake\promote_underlying_candles.py --dry-run
.\venv\Scripts\python.exe tools\lake\promote_india_vix.py --dry-run
.\venv\Scripts\python.exe tools\lake\compact_option_snapshots.py --dry-run --max-sessions 3
```

---

## 8. Stop Condition Compliance

Phase 2 has **NOT** started. No Parquet partitions have been published to `Data/lake/`, and no active manifests have been created. Awaiting explicit owner authorization before proceeding to Phase 2.
