# QuantView — Phase 3: Full Option Snapshot Compaction Report

**Report Date:** 2026-10-24  
**Status:** COMPLETED — PRODUCTION LAKE MANIFEST V2 ACTIVE (ALL GATES PASS)  
**Execution Environment:** `c:\Algo\quantview` (Windows 11, Python 3.11)  
**Git HEAD Commit:** `e46530db272f4b46a898ddb00ab7261bae4e25ec`  
**Production Lake Location:** [`Data/lake/`](file:///c:/Algo/quantview/Data/lake/)  
**Active Production Manifest:** [`Data/lake/manifest_active.json`](file:///c:/Algo/quantview/Data/lake/manifest_active.json) (Version 2)  
**Archived Production Manifest:** [`Data/lake/manifest_v1_archive.json`](file:///c:/Algo/quantview/Data/lake/manifest_v1_archive.json) (Version 1)  
**Canonical DuckDB Analytical Database:** [`Data/lake/quantview.duckdb`](file:///c:/Algo/quantview/Data/lake/quantview.duckdb)  
**Validation Evidence Artifact:** [`reports/phase3_snapshot_validation_results.json`](file:///c:/Algo/quantview/reports/phase3_snapshot_validation_results.json)  

---

## 1. Executive Summary & Verdict

QuantView Phase 3 (Task M3-06: Full Option Snapshot Compaction) has been **successfully executed, 100% validated, and published to the active data lake**.

The complete inventory of **82,283 option-chain snapshot CSV files** collected between April 2026 and October 2026 across 36 expiries and 126 trading sessions has been converted into canonical Parquet tables (`option_snapshot_captures` and `option_snapshot_rows`). The compaction was executed with 100% mathematical reconciliation, strictly isolating discrete capture identities, normalizing naive timestamps to `Asia/Kolkata` -> `UTC`, preserving exact Decimal(9, 2) strikes and float64 observed Greeks, and explicitly quarantining all corrupted and empty files with zero data fabrication.

All 252 generated Parquet partitions were validated in staging (`staging/lake_preparation_phase3/`) and atomically promoted to the active lake (`Data/lake/`). The active manifest has been updated to **Version 2** (`Data/lake/manifest_active.json`), retaining all 183 Phase 2B candle partitions byte-for-byte intact while integrating the 252 snapshot partitions. Canonical DuckDB views (`v_snapshots_captures`, `v_snapshots_rows`, and `v_snapshots_reconstructed_chain`) have been registered and verified with sub-30ms query latency.

| Dataset Workstream | Partitions | Active Rows | Size (Compressed) | DuckDB View | Query Latency | Status / Verdict |
| :--- | :---: | :---: | :---: | :--- | :---: | :---: |
| **A. Expired Option Candles (Phase 2B)** | 95 | 20,332,421 | 205.27 MB | `v_candles_options` | 34.14 ms | **PASS (Intact)** |
| **B. Underlying NIFTY Candles (Phase 2B)** | 64 | 437,008 | 15.41 MB | `v_candles_underlying` | 35.39 ms | **PASS (Intact)** |
| **C. India VIX Index Candles (Phase 2B)** | 24 | 167,385 | 4.37 MB | `v_candles_vix` | 7.05 ms | **PASS (Intact)** |
| **D. Option Snapshot Captures (Phase 3)** | 126 | 82,274 | 2.97 MB | `v_snapshots_captures` | 23.99 ms | **PASS (NEW)** |
| **E. Option Snapshot Rows (Phase 3)** | 126 | 17,445,732 | 378.24 MB | `v_snapshots_rows` | 26.09 ms | **PASS (NEW)** |
| **F. Reconstructed Chain (Lazy View)** | — | 17,445,732 | — | `v_snapshots_reconstructed_chain` | 19.30 ms | **PASS (NEW)** |
| **Total Active Production Data Lake** | **435 Parquets** | **38,464,820 rows** | **606.27 MB** | **All 6 Views Active** | **All $\le 36\text{ms}$** | **ALL PASS** |

---

## 2. Complete Inventory-to-Disposition Reconciliation

Every single one of the 82,283 inventoried snapshot files was accounted for with exactly one terminal disposition:

| Category | Count | Percentage | Terminal Disposition |
| :--- | :---: | :---: | :--- |
| **Valid Schema v3 Captures (18 cols, Greeks)** | 72,468 | 88.07% | Compacted to daily Parquet (`option_snapshot_captures`, `option_snapshot_rows`) |
| **Valid Schema v1 Captures (9 cols, legacy)** | 9,806 | 11.92% | Compacted to daily Parquet (`option_snapshot_captures`, `option_snapshot_rows`) |
| **Zero-Byte Empty CSVs** | 4 | 0.005% | Explicitly Quarantined (`EMPTY_ZERO_BYTES`) |
| **Null-Byte Corrupted CSVs** | 5 | 0.006% | Explicitly Quarantined (`CORRUPT_NULL_BYTES`) |
| **Total Source Files Audited** | **82,283** | **100.00%** | **Reconciliation Discrepancy: 0** |

$$\text{Compacted Captures } (82,274) + \text{Quarantined Files } (9) = 82,283 \equiv \text{Discrepancy } 0$$

### Quarantined Files Detail
Recorded authoritatively in [`staging/lake_preparation_phase3/quarantine/quarantine_report.json`](file:///c:/Algo/quantview/staging/lake_preparation_phase3/quarantine/quarantine_report.json):

| File Path | Expiry Date | Trade Date | Size | Reason Code | Defect Description |
| :--- | :---: | :---: | :---: | :--- | :--- |
| `Data/live/option_chain/nifty/2026-08-04/2026-07-29/snapshots/14-28-03.csv` | `2026-08-04` | `2026-07-29` | 3,822 B | `CORRUPT_NULL_BYTES` | Payload contains binary null bytes (`\x00`) from crashed socket write |
| `Data/live/option_chain/nifty/2026-08-11/2026-08-06/snapshots/13-36-34.csv` | `2026-08-11` | `2026-08-06` | 3,822 B | `CORRUPT_NULL_BYTES` | Payload contains binary null bytes (`\x00`) |
| `Data/live/option_chain/nifty/2026-08-11/2026-08-11/snapshots/15-23-34.csv` | `2026-08-11` | `2026-08-11` | 3,822 B | `CORRUPT_NULL_BYTES` | Payload contains binary null bytes (`\x00`) |
| `Data/live/option_chain/nifty/2026-09-08/2026-09-03/snapshots/12-08-03.csv` | `2026-09-08` | `2026-09-03` | 3,822 B | `CORRUPT_NULL_BYTES` | Payload contains binary null bytes (`\x00`) |
| `Data/live/option_chain/nifty/2026-09-08/2026-09-04/snapshots/12-15-33.csv` | `2026-09-08` | `2026-09-04` | 3,822 B | `CORRUPT_NULL_BYTES` | Payload contains binary null bytes (`\x00`) |
| `Data/live/option_chain/nifty/2026-09-15/2026-09-15/snapshots/12-27-33.csv` | `2026-09-15` | `2026-09-15` | 0 B | `EMPTY_ZERO_BYTES` | Truncated 0-byte file created during collector restart |
| `Data/live/option_chain/nifty/2026-09-15/2026-09-15/snapshots/12-28-03.csv` | `2026-09-15` | `2026-09-15` | 0 B | `EMPTY_ZERO_BYTES` | Truncated 0-byte file |
| `Data/live/option_chain/nifty/2026-09-15/2026-09-15/snapshots/12-28-33.csv` | `2026-09-15` | `2026-09-15` | 0 B | `EMPTY_ZERO_BYTES` | Truncated 0-byte file |
| `Data/live/option_chain/nifty/2026-09-15/2026-09-15/snapshots/12-38-03.csv` | `2026-09-15` | `2026-09-15` | 0 B | `EMPTY_ZERO_BYTES` | Truncated 0-byte file |

---

## 3. Specification Compliance with Canonical Documents

The snapshot compaction was executed in strict adherence to the project specifications:

1. **`DOCS/QUANTVIEW_DATA_SPEC.md`:**
   - **§2 & §2.2 (Directory Layout & Storage Profile):** Staged and published partitions follow canonical layout:
     * `Data/lake/option_snapshot_captures/trade_date=YYYY-MM-DD/part-0.parquet` (126 daily partitions)
     * `Data/lake/option_snapshot_rows/trade_date=YYYY-MM-DD/part-0.parquet` (126 daily partitions)
     * Compressed with Zstandard (`zstd`), row group size 250,000.
     * Rows deterministically pre-sorted before serialization: captures sorted by `(received_at, expiry)`; rows sorted by `(received_at, expiry, strike, option_type)`.
   - **§4.3 (Snapshot Capture Header: `option_snapshot_captures`):** Exactly one header record per physical capture. Generates globally unique, deterministic `snapshot_id` (SHA-256 hash of expiry, trade date, filename, timestamp, and row count). Includes `schema_version` (`v1` or `v3`), `source_file`, `row_count`, `field_presence_mask`, and `quality_flags`.
   - **§4.4 (Snapshot Strike Rows: `option_snapshot_rows`):** Individual option-contract observations belonging to their original capture. Keyed by `(snapshot_id, expiry, strike, option_type)` with 0 duplicate collisions.
   - **§4.8 (Reconstructed Option Chain):** Registered lazy DuckDB view `v_snapshots_reconstructed_chain` joining `v_snapshots_captures` with `v_snapshots_rows` on `snapshot_id`.
   - **§11 (Timezone Semantics & Naive Normalization):** Naive source timestamps recorded by the local collector were localized to `Asia/Kolkata` (IST, UTC+05:30) and converted to UTC (`us` precision), flagged with `NAIVE_TIMESTAMP_ASSUMED_IST`. Timestamps align second-for-second with candle market open (03:45:00 UTC).
   - **Strike Precision:** Enforces exact `Decimal(9, 2)` (`decimal128(9, 2)` in PyArrow/Parquet), strictly rejecting binary floats.
   - **Observed Greeks Precision:** Vendor IV and observed Greeks (`delta`, `gamma`, `theta`, `vega`) stored in full IEEE-754 64-bit float precision (`double`).

2. **`DOCS/AGENTS.md` (Milestone M3):**
   - **Task M3-06:** Fully satisfied. Complete snapshot inventory compacted without lookahead or continuous chain fabrication.

---

## 4. Source-to-Canonical Schema Mapping

| Canonical Field | Type | Source v1 (9 cols) | Source v3 (18 cols) | Canonical Handling & Normalization |
| :--- | :--- | :--- | :--- | :--- |
| `snapshot_id` | `string` | Generated | Generated | Deterministic SHA-256 hash (24 chars) |
| `received_at` | `timestamp[us, UTC]` | `timestamp` | `timestamp` | Naive string localized to `Asia/Kolkata` $\to$ UTC |
| `trade_date` | `date32` | Path-derived | Path-derived | Parsed from `{trade_date}/snapshots/` folder |
| `underlying` | `string` | `"NIFTY"` | `"NIFTY"` | Fixed canonical underlying |
| `expiry` | `date32` | Path-derived | Path-derived | Parsed from `{expiry_date}/` directory level |
| `strike` | `decimal128(9, 2)` | `strike` | `strike` | Converted to exact Decimal (`24800.00`) |
| `option_type` | `string` | `type` | `type` | Normalized to `'CE'` or `'PE'` |
| `spot_price` | `double` | Absent (`null`) | `spot_price` | 64-bit float; null for v1 |
| `oi` | `int64` | `oi` | `oi` | Non-negative integer |
| `prev_oi` | `int64` | `prev_oi` | Absent (`null`) | Present in v1 only; null in v3 |
| `volume` | `int64` | `volume` | `volume` | Integer volume traded |
| `ltp` | `double` | `ltp` | `ltp` | Last traded price |
| `bid`, `ask` | `double` | `bid`, `ask` | `bid`, `ask` | Best bid/ask quote prices |
| `bid_qty`, `ask_qty` | `int32` | Absent (`null`) | `bid_qty`, `ask_qty` | Top-of-book depth quantities |
| `change` | `double` | Absent (`null`) | `chng` | Price change |
| `change_oi` | `int64` | Absent (`null`) | `chng_oi` | Open interest change |
| `iv_observed` | `double` | Absent (`null`) | `iv` | Vendor implied volatility |
| `delta_observed` | `double` | Absent (`null`) | `delta` | Vendor Black-Scholes Delta |
| `gamma_observed` | `double` | Absent (`null`) | `gamma` | Vendor Gamma |
| `theta_observed` | `double` | Absent (`null`) | `theta` | Vendor Theta |
| `vega_observed` | `double` | Absent (`null`) | `vega` | Vendor Vega |
| `schema_version` | `string` | `"v1"` | `"v3"` | Explicit source schema tag |
| `field_presence_mask` | `string` | `compute_mask()` | `compute_mask()` | Pipe-delimited present fields (e.g. `spot\|oi\|greeks`) |
| `quality_flags` | `list<string>` | Quality tags | Quality tags | `['VALID', 'PATH_DERIVED_EXPIRY', 'NAIVE_TIMESTAMP_ASSUMED_IST']` |
| `source_file` | `string` | Path reference | Path reference | Relative path to raw source CSV |

---

## 5. Active Production Manifest v2 Verification

The official active manifest was atomically activated at [`Data/lake/manifest_active.json`](file:///c:/Algo/quantview/Data/lake/manifest_active.json):

- **Manifest Version:** `2`
- **Is Active:** `true`
- **Activated At:** `2026-10-23T18:43:42.706591+00:00`
- **Active Lake Root:** `Data/lake`
- **Active Manifest SHA-256:** `7717d875f58fb75b7b0adcf4b517030ad2210a7803017f6bbc8025d72c061dae`
- **Previous Manifest Archive:** [`Data/lake/manifest_v1_archive.json`](file:///c:/Algo/quantview/Data/lake/manifest_v1_archive.json) (SHA-256: `6aae362397956523987b96f9438d16e28f0d308ef9dd1f445eb8fdf7453a72d3`)
- **Total Registered Datasets:** 5
- **Total Parquet Partitions:** 435 files
- **Total Active Rows:** 38,464,820 rows
- **Total Compressed Size:** 606.27 MB

### Dataset Inventory Summary in Manifest v2

```json
{
  "manifest_type": "QUANTVIEW_ACTIVE_LAKE_MANIFEST",
  "manifest_version": 2,
  "is_active": true,
  "aggregate_totals": {
    "total_files": 435,
    "total_rows": 38464820,
    "total_bytes": 635720871,
    "total_mb": 606.27
  },
  "datasets": {
    "option_candles": {
      "file_count": 95,
      "total_rows": 20332421,
      "total_bytes": 215242484
    },
    "underlying_candles": {
      "file_count": 64,
      "total_rows": 437008,
      "total_bytes": 16160352
    },
    "india_vix": {
      "file_count": 24,
      "total_rows": 167385,
      "total_bytes": 4585589
    },
    "option_snapshot_captures": {
      "file_count": 126,
      "total_rows": 82274,
      "total_bytes": 3110996
    },
    "option_snapshot_rows": {
      "file_count": 126,
      "total_rows": 17445732,
      "total_bytes": 396619450
    }
  }
}
```

---

## 6. DuckDB Analytical Query Verification & Benchmarks

All 6 canonical analytical views are registered and operational in [`Data/lake/quantview.duckdb`](file:///c:/Algo/quantview/Data/lake/quantview.duckdb). Every query runs in sub-40ms execution time:

| Analytical View | Underlying Dataset | Row Count | Query Benchmark | Latency |
| :--- | :--- | :---: | :--- | :---: |
| `v_candles_underlying` | `underlying_candles` | 437,008 | `SELECT count(*) FROM v_candles_underlying` | 35.39 ms |
| `v_candles_options` | `option_candles` | 20,332,421 | `SELECT count(*) FROM v_candles_options` | 34.14 ms |
| `v_candles_vix` | `india_vix` | 167,385 | `SELECT count(*) FROM v_candles_vix` | 7.05 ms |
| `v_snapshots_captures` | `option_snapshot_captures` | 82,274 | `SELECT count(*) FROM v_snapshots_captures` | 23.99 ms |
| `v_snapshots_rows` | `option_snapshot_rows` | 17,445,732 | `SELECT count(*) FROM v_snapshots_rows` | 26.09 ms |
| `v_snapshots_reconstructed_chain` | `captures JOIN rows` | 17,445,732 | Point-in-time chain cutoff query | 19.30 ms |

### Point-in-Time Availability Verification
Point-in-time causal filtering was tested on a representative trading session (`2026-10-14`):

```sql
SELECT count(*) 
FROM v_snapshots_rows 
WHERE trade_date = '2026-10-14' 
  AND received_at <= '2026-10-14 04:00:00+00:00';
```
- **Visible Rows at 04:00:00 UTC (09:30:00 IST):** 5,616 contract observations.
- **Future Observations Leaked:** 0 rows.
- **Execution Latency:** 19.30 ms.

---

## 7. Automated Test Suite & Consistency Results

1. **Unit Test Suite:**
   ```bash
   .\venv\Scripts\python.exe -m unittest discover -s tests/unit -p "test_*.py"
   ```
   **Result:** `Ran 52 tests in 1.578s — OK (52/52 PASS, 0 failures, 0 errors)`

2. **Documentation Task Linter:**
   ```bash
   .\venv\Scripts\python.exe tools/qv_check.py lint DOCS
   ```
   **Result:** `tasks=114 active=113 days=262.5 gates=G0a,G0,G1,G2a,G2b,G3,G4,G5,G6 — LINT: PASS (0)`

3. **Cross-Specification Consistency Suite:**
   ```bash
   .\venv\Scripts\python.exe ops/verify_docs_consistency.py
   ```
   **Result:** `PASSED: 0 defects found across all 13 checks (A through M)!`

4. **Phase 3 Validation Suite:**
   ```bash
   .\venv\Scripts\python.exe tools/lake/validate_phase3_snapshots.py
   ```
   **Result:** `5/5 Gates PASS (Overall: PASS)`

---

## 8. Milestone M3-06 Completion Sign-Off

- **Task ID:** `M3-06` (Option Snapshot Compaction)
- **Status:** `COMPLETED` / `VERIFIED`
- **Deliverables Produced:**
  * Tooling: `tools/lake/compact_option_snapshots.py`, `tools/lake/prepare_phase3_manifest.py`, `tools/lake/publish_snapshots_to_lake.py`, `tools/lake/validate_phase3_snapshots.py`.
  * Staged Artifacts: `staging/lake_preparation_phase3/` (252 Parquet files, `manifest_phase3.json`, `quarantine_report.json`).
  * Published Lake: `Data/lake/option_snapshot_captures/` (126 partitions), `Data/lake/option_snapshot_rows/` (126 partitions).
  * Active Manifest: `Data/lake/manifest_active.json` (Version 2, 435 partitions, 38,464,820 rows).
  * DuckDB Views: `v_snapshots_captures`, `v_snapshots_rows`, `v_snapshots_reconstructed_chain` in `Data/lake/quantview.duckdb`.
  * Evidence: `reports/phase3_snapshot_validation_results.json` and this completion report.
- **Next Stage 1 Milestones:**
  * Phase 4: Multi-Timeframe Derivation (`M3-07`) & Data Eligibility Matrix (`M3-09`).
  * Phase 5: Formal Gate G1 Review & Sign-Off $\to$ Stage 1 100% Complete.
