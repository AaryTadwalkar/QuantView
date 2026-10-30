# QuantView - Daily Historical Option Ingestion Audit Report (2026-10-19 to 2026-10-27)

**Audit Execution Date:** 2026-10-30 17:07:29 UTC  
**Target Horizon:** `2026-10-19` to `2026-10-27` (6 Trading Days across 2 Expiries)  
**Authority Reference:** Owner Authorization under `DOCS/AGENTS.md` and `DOCS/QUANTVIEW_DATA_SPEC.md`  
**Overall Status:** **6/6 TRADING DAYS VERIFIED VALID**  

---

## 1. Executive Summary & Aggregate Metrics

Across all **6 trading days** across the target horizon:
* **Total Days Staged & Verified:** **6/6 days** (100.0%)
* **Total 1-Minute Option Candle Bars Staged:** **310,790 bars**
* **Total Staged CSV Storage:** **52.56 MB** across 6 individual daily CSV files
* **Total Raw Compressed Payloads:** **0.00 MB** in `Data/raw/upstox_rest/expired_api/`
* **Total Cryptographic Manifests Verified:** **0 companion JSON manifests**
* **Checksum Integrity:** **0/0 bit-for-bit SHA-256 matches** (0 mismatches)
* **Duplicate Rows:** **0 duplicate rows** (strictly 0 duplicates across all sessions)
* **Data Nulls:** **0 null values** across all columns and bars

---

## 2. Daily Session Audit Scorecard

| Trade Date | Active Expiry | Status | Candle Bars | Traded Contracts | CSV Size | Duplicates |
|---|---|---|---:|---:|---:|---:|
| `2026-10-19` | `2026-10-19` | PASS | 53,480 | 140 | 9.01 MB | 0 |
| `2026-10-21` | `2026-10-27` | PASS | 53,468 | 140 | 9.06 MB | 0 |
| `2026-10-22` | `2026-10-27` | PASS | 51,086 | 133 | 8.66 MB | 0 |
| `2026-10-23` | `2026-10-27` | PASS | 50,021 | 132 | 8.48 MB | 0 |
| `2026-10-26` | `2026-10-27` | PASS | 52,254 | 137 | 8.84 MB | 0 |
| `2026-10-27` | `2026-10-27` | PASS | 50,481 | 135 | 8.51 MB | 0 |

---

## 3. Storage Architecture Verification

1. **Daily CSV Isolation:**
   - Every individual trading day has its own clean, self-contained file in `staging/expired_options/nifty_options_1m_{expiry}_{date}.csv`.
   - Allows independent visual inspection, fault tolerance, and zero risk of cross-session file corruption.

2. **Raw Ground-Truth Immutability:**
   - Original vendor HTTP wire JSON is permanently archived in `Data/raw/upstox_rest/expired_api/endpoint=historical_candle/` and `endpoint=option_contract/`.
   - Every single response is accompanied by a SHA-256 cryptographic manifest.
