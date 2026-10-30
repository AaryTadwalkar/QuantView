# QuantView — Operational Market Data Update Runbook

> **Authoritative Operational Guide** for periodic market data updates (weekly / bi-weekly / monthly) across historical candlestick series, expired option contracts, and PC B live option chain order book snapshots.

---

## 1. System Architecture & Data Lifecycle

QuantView follows a strict **three-tier immutable data architecture** (`P1`, `ADR-003`, `QUANTVIEW_DATA_SPEC §4`):

```
+----------------------------------------------------------------------------------------------------+
|                                      TIER 1: RAW INGESTION LAYER                                   |
|                                                                                                    |
|  Upstox REST API v3 / v2                 PC B Live Snapshot Collector                              |
|  (Underlying & Expired Candles)          (WebSocket 1-sec Option Chain)                            |
|       |                                        |                                                   |
|       v                                        v                                                   |
|  Data/raw/upstox_rest/expired_api/       D:\Algo_Data_Final\Data\live\option_chain\nifty\           |
|  (Content-addressed .json.gz + SHA)      ({expiry}/{trade_date}/*.json)                            |
+----------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+----------------------------------------------------------------------------------------------------+
|                                    TIER 2: STAGING NORMALIZATION                                   |
|                                                                                                    |
|  Data/staging/underlying_candles/        Data/staging/lake_preparation_phase3/                     |
|  (Normalized daily/1m NIFTY & VIX CSVs)  (option_snapshot_{captures,rows}/ trade_date partitions)  |
|                                                                                                    |
|  Data/staging/expired_options/           Data/staging/lake_preparation_phase2a/                    |
|  (Normalized daily option 1m CSVs)       (option_candles/, underlying_candles/, india_vix/)        |
|                                                                                                    |
|  Data/staging/lake_preparation_phase4/                                                             |
|  (derived_candles/ 3m, 5m, 15m, 30m, 1h, 4h & data_eligibility/)                                   |
+----------------------------------------------------------------------------------------------------+
                                                 |
                                                 v
+----------------------------------------------------------------------------------------------------+
|                                  TIER 3: CANONICAL PRODUCTION LAKE                                 |
|                                                                                                    |
|  Data/lake/                              Data/lake/manifest_active.json (Manifest Version 3)       |
|    - underlying_candles/                 Data/lake/quantview.duckdb (Zero-copy Analytical Views)   |
|    - india_vix/                            * v_candles_underlying                                  |
|    - option_candles/                       * v_candles_vix                                         |
|    - option_snapshot_captures/             * v_candles_options                                     |
|    - option_snapshot_rows/                 * v_candles_derived                                     |
|    - derived_candles/                      * v_data_eligibility                                    |
|    - data_eligibility/                     * v_snapshots_captures                                  |
|                                            * v_snapshots_rows                                      |
|                                            * v_snapshots_reconstructed_chain                       |
+----------------------------------------------------------------------------------------------------+
```

### Core Invariants & Rules:
1. **Raw Immutability:** Raw files (`Data/raw/` and `D:\Algo_Data_Final\`) are read-only and never modified or deleted.
2. **Causal Availability (`ADR-008`):** Intraday bars become available at `available_at = ts_end`. Daily bars become available at `available_at = 15:30 IST` (`10:00 UTC`) on the trade date.
3. **Candidate Strike Band:** Expired option candle fetching strictly enforces $\pm 1500.0$ points around session spot open (~61 strikes per session), capturing $>95.9\%$ of trading liquidity while preventing API rate exhaustion.
4. **Active Lake Isolation:** All promotion scripts write atomic temporary files (`.parquet.tmp`), verify SHA-256 byte-for-byte, and replace targets atomically.
5. **Virtual Environment:** Always execute with `.\venv\Scripts\python.exe` from `C:\Algo\quantview`.

---

## 2. Prerequisites & Pre-Flight Checklist

Before running the update pipeline:

1. **Verify Python Virtual Environment:**
   ```powershell
   .\venv\Scripts\python.exe -c "import duckdb, pyarrow, pandas, requests; print('Environment OK')"
   ```
2. **Verify Active Upstox Token:**
   - In `.env`, ensure `UPSTOX_ACCESS_TOKEN` is present and active (valid for the trading session).
   - Test connectivity:
     ```powershell
     .\venv\Scripts\python.exe -c "import os, requests; from dotenv import load_dotenv; load_dotenv(); t = os.getenv('UPSTOX_ACCESS_TOKEN'); r = requests.get('https://api.upstox.com/v2/user/profile', headers={'Authorization': f'Bearer {t}'}); print('Token Status:', r.status_code)"
     ```
3. **Verify PC B Live Snapshot Drive:**
   - Ensure external drive or network share `D:\Algo_Data_Final\Data\live\option_chain\nifty` is connected and accessible.

---

## 3. End-to-End Execution Sequence

Execute each step sequentially in PowerShell from `C:\Algo\quantview`:

### Step 1: Ingest Underlying Candles (NIFTY 50 & India VIX)
Fetch 1-minute and 1-day candles for the elapsed interval:

```powershell
# NIFTY 50 Index (1-minute and 1-day)
.\venv\Scripts\python.exe tools/ingest/import_underlying_candles_v3.py --from-date "YYYY-MM-DD" --to-date "YYYY-MM-DD" --instrument-key "NSE_INDEX|Nifty 50" --unit minutes --interval 1 --staging-dir "Data/staging/underlying_candles"
.\venv\Scripts\python.exe tools/ingest/import_underlying_candles_v3.py --from-date "YYYY-MM-DD" --to-date "YYYY-MM-DD" --instrument-key "NSE_INDEX|Nifty 50" --unit days --interval 1 --staging-dir "Data/staging/underlying_candles"

# India VIX Index (1-minute and 1-day)
.\venv\Scripts\python.exe tools/ingest/import_underlying_candles_v3.py --from-date "YYYY-MM-DD" --to-date "YYYY-MM-DD" --instrument-key "NSE_INDEX|India VIX" --unit minutes --interval 1 --staging-dir "Data/staging/underlying_candles"
.\venv\Scripts\python.exe tools/ingest/import_underlying_candles_v3.py --from-date "YYYY-MM-DD" --to-date "YYYY-MM-DD" --instrument-key "NSE_INDEX|India VIX" --unit days --interval 1 --staging-dir "Data/staging/underlying_candles"
```
*Note: If updating during current trade date before Upstox batch settlement runs overnight, intraday bars are queried from `/v2/historical-candle/intraday/{instrument_key}/1minute`.*

---

### Step 2: Compact Live Option Chain Snapshots (PC B Data)
Compacts raw JSON snapshots into partitioned Parquet format in `Data/staging/lake_preparation_phase3/`:

```powershell
.\venv\Scripts\python.exe tools/lake/compact_option_snapshots.py --skip-existing --source-dir "D:\Algo_Data_Final\Data\live\option_chain\nifty"
```
*Note: `--skip-existing` leverages cached parquet metadata to skip previously compacted sessions in milliseconds.*

---

### Step 3: Register Snapshot Manifest & Publish to Lake
Compile the Phase 3 staging manifest and atomically publish snapshots to `Data/lake/`:

```powershell
# 1. Regenerate snapshot staging manifest
.\venv\Scripts\python.exe tools/lake/prepare_phase3_manifest.py

# 2. Publish snapshots to active lake and register DuckDB snapshot views
.\venv\Scripts\python.exe tools/lake/publish_snapshots_to_lake.py
```

---

### Step 4: Update Expiry Catalog & Ingest Expired Option Candles
For any newly completed expiry cycle:

1. **Verify/Add Expiry to `config/nse_nifty_expiries_2025_2026.json`:**
   ```json
   {
     "expiry_date": "YYYY-MM-DD",
     "day_of_week": "Tuesday",
     "year": 2026,
     "month": 10
   }
   ```
2. **Ingest Expired 1m Option Candles from Upstox:**
   ```powershell
   .\venv\Scripts\python.exe tools/ingest/import_expired_option_candles.py --backfill-from YYYY-MM-DD --backfill-to YYYY-MM-DD --candidate-band-pts 1500.0
   ```
   *Note: Only expiries that have already passed (expired) return data from this endpoint. Future active expiries (e.g. 2026-11-03) are captured live via PC B snapshots and cannot be backfilled until post-expiry.*

---

### Step 5: Promote Candles to Lake Staging (Phase 2A)
Normalize raw and extension CSVs into canonical lake partitions:

```powershell
# 1. Underlying NIFTY candles (1m & 1d)
.\venv\Scripts\python.exe tools/lake/promote_underlying_candles.py

# 2. India VIX candles (1m & 1d)
.\venv\Scripts\python.exe tools/lake/promote_india_vix.py

# 3. Expired option candles (1m)
.\venv\Scripts\python.exe tools/lake/promote_option_candles.py --skip-existing
```

---

### Step 6: Regenerate Phase 2A Manifest & Publish Active Lake
Reconcile Phase 2A staging partitions and atomically publish into `Data/lake/`:

```powershell
# 1. Regenerate Phase 2A staging manifest
.\venv\Scripts\python.exe tools/lake/prepare_dry_run_manifest.py --prep-root "Data/staging/lake_preparation_phase2a" --manifest-filename "manifest_phase2a.json"

# 2. Atomically publish to Data/lake and register core DuckDB views
.\venv\Scripts\python.exe tools/lake/publish_active_lake.py
```

---

### Step 7: Re-derive Multi-Timeframe Candles & Compute Eligibility
Derive higher timeframes (3m, 5m, 15m, 30m, 1h, 4h) and generate session eligibility records:

```powershell
# 1. Resample 1m underlying bars into multi-timeframe partitions
.\venv\Scripts\python.exe tools/lake/derive_underlying_candles.py

# 2. Recompute point-in-time data eligibility matrix
.\venv\Scripts\python.exe tools/lake/compute_data_eligibility.py

# 3. Generate Phase 4 staging manifest
.\venv\Scripts\python.exe tools/lake/prepare_phase4_manifest.py
```

---

### Step 8: Complete Stage 1 Promotion (Manifest Version 3)
Promote derived candles and eligibility into `Data/lake/`, activate Manifest Version 3, and register all 8 canonical DuckDB views:

```powershell
.\venv\Scripts\python.exe tools/lake/publish_stage1_completion.py
```

---

### Step 9: Verification & Automated Gate G1 Audit
Verify that all data integrity invariants pass and analytical queries remain sub-50ms:

```powershell
# 1. Automated Gate G1 Verification Suite (12/12 Milestones)
.\venv\Scripts\python.exe tools/lake/run_gate_g1_verification.py

# 2. Scaffolding Unit Tests (21/21 Contract Tests)
.\venv\Scripts\python.exe -m pytest tests/unit/test_lake_scaffolding.py

# 3. Package Boundary Enforcement (7/7 Boundaries)
.\venv\Scripts\python.exe -m pytest tests/unit/test_package_boundaries.py
```

---

## 4. Verification & Inspection Queries

Use Python/DuckDB to quickly inspect the status of the updated active lake:

```powershell
.\venv\Scripts\python.exe -c "import duckdb; con = duckdb.connect('Data/lake/quantview.duckdb', read_only=True); print('Max underlying:', con.execute('SELECT max(bar_start) FROM v_candles_underlying').fetchone()[0]); print('Max VIX:', con.execute('SELECT max(bar_start) FROM v_candles_vix').fetchone()[0]); print('Max Options Expiry:', con.execute('SELECT max(expiry) FROM v_candles_options').fetchone()[0]); print('Max Snapshot Trade Date:', con.execute('SELECT max(trade_date) FROM v_snapshots_rows').fetchone()[0]); print('Max Derived 5m:', con.execute('SELECT max(ts_start) FROM v_candles_derived WHERE interval=\'5m\'').fetchone()[0])"
```

---

## 5. Troubleshooting & FAQ

### Q1: Why does VS Code display red squiggles under DuckDB view names in Python scripts?
* **Explanation:** VS Code's Python language server attempts to statically parse SQL strings using a generic SQL linter. Because `v_snapshots_rows` and `v_candles_underlying` are registered at runtime inside `Data/lake/quantview.duckdb`, the IDE static parser doesn't have an active connection and flags them as unrecognized table names.
* **Resolution:** This is purely an editor cosmetic warning. The runtime execution in Python/DuckDB is 100% valid and executes with sub-50ms latency.

### Q2: Why does Upstox API return `{"status":"success","data":[]}` for an active upcoming expiry (e.g. 2026-11-03)?
* **Explanation:** The `/v2/expired-instruments/` API only contains contracts that have *already reached their expiry date*. For ongoing/future expiries, order book data is captured in real-time by PC B's snapshot collector and stored in `D:\Algo_Data_Final\Data\live\option_chain\nifty`. Once the expiry date passes, the expired contracts endpoint can be queried to backfill official historical 1m candle bars.

### Q3: Why does `ModuleNotFoundError: No module named 'pydantic'` occur?
* **Explanation:** You ran `python` using the system Python interpreter instead of the workspace virtual environment.
* **Resolution:** Always use `.\venv\Scripts\python.exe`.

### Q4: Where must staging files be placed?
* **Explanation:** All staging files MUST be located inside `Data/staging/` (`Data/staging/underlying_candles`, `Data/staging/expired_options`, `Data/staging/lake_preparation_phase2a`, `Data/staging/lake_preparation_phase3`, `Data/staging/lake_preparation_phase4`). Never place data folders directly at the repository root (`staging/`). All QuantView tools are configured to default to `Data/staging/`.

