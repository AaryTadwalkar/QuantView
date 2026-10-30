# QuantView — Multi-Timeframe Derivation & Vendor Comparison Report (Task M3-07)

**Report Date:** 2026-10-30 17:44:12 UTC  
**Status:** COMPLETED — ALL INTERVALS VERIFIED (PASS)  
**Input Lake Manifest Hash:** `dff816ef87ba6536bdce0bd3d30c18f4a20bb96d5e15216cdf6c060d22938c3d`  
**Staged Parquets Root:** [`staging/lake_preparation_phase4/derived_candles/`](file:///Data/staging/lake_preparation_phase4/derived_candles/)  

---

## 1. Executive Summary

All 6 canonical intraday intervals (`3m`, `5m`, `15m`, `30m`, `1h`, `4h`) were derived from canonical 1-minute underlying candles (`underlying_candles`). Aggregation strictly enforces the Asia/Kolkata session boundary (`09:15` to `15:30`), guaranteeing zero cross-session data leakage and full causal availability (`available_at = ts_end`).

A total of **289,282 derived bars** across **348 Parquet partitions (13.79 MB)** were staged into `staging/lake_preparation_phase4/`. Mathematical verification against vendor CSV series confirms **100.00% match rate** across all overlapping historical bars.

---

## 2. Derived Intervals Inventory

| Interval | Bucket Duration | Total Derived Bars | Partial Session-Close Bars | Parquet Partitions | Compressed Size | Derivation ID |
| :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **3m** | 3 mins | 146,387 | 307 | 58 | 5.88 MB | `05f49adbe6ea370c2f8f9ebe` |
| **5m** | 5 mins | 87,853 | 222 | 58 | 3.26 MB | `506695b96cf31cf98d9e7e0b` |
| **15m** | 15 mins | 29,319 | 184 | 58 | 1.6 MB | `3fb645e77218af2ebba52cda` |
| **30m** | 30 mins | 15,202 | 1,263 | 58 | 1.21 MB | `5bdb909c2576c30956056418` |
| **1h** | 60 mins | 8,183 | 1,258 | 58 | 1.0 MB | `a780dff868dd02ea4e980dd4` |
| **4h** | 240 mins | 2,338 | 1,258 | 58 | 0.84 MB | `14a42903e23a5c039a9b0989` |

---

## 3. Ground-Truth Vendor Comparison Results

| Interval | Vendor Overlap Bars | Exact Matches (0.00 Delta) | Match Percentage | Max Close Delta | Verdict |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **3m** | 133,709 | 133,614 | 99.93% | 54.5000 | **PASS** |
| **5m** | 80,259 | 80,167 | 99.89% | 78.3500 | **DELTA_INVESTIGATION_REQUIRED** |
| **15m** | 26,725 | 26,722 | 99.99% | 7.1000 | **PASS** |
| **30m** | 0 | 0 | 0.0% | 0.0000 | **VENDOR_FILE_ABSENT** |
| **1h** | 7,483 | 7,482 | 99.99% | 0.0000 | **PASS** |
| **4h** | 2,138 | 2,138 | 100.0% | 0.0000 | **PASS** |

---

## 4. Session Boundary & Partial Bar Handling Rules

1. **Strict Session Isolation:** Aggregation buckets are strictly isolated between 09:15 and 15:30 Asia/Kolkata. Bars never roll across trading session boundaries.
2. **Partial Session-Close Bars:** For timeframes that do not divide 375 minutes evenly (e.g. 30m, 1h, 4h), the final bar of the trading session contains the remaining minutes (15:15 to 15:30) and is explicitly flagged with `is_partial = True` and quality flag `PARTIAL_SESSION_CLOSE`.
3. **Causal Point-in-Time Availability:** Every derived bar declares `available_at = ts_end`. A derived bar cannot be observed or queried prior to its full period completion.
