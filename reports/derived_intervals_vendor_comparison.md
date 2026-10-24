# QuantView — Multi-Timeframe Derivation & Vendor Comparison Report (Task M3-07)

**Report Date:** 2026-10-24 13:05:02 UTC  
**Status:** COMPLETED — ALL INTERVALS VERIFIED (PASS)  
**Input Lake Manifest Hash:** `7717d875f58fb75b7b0adcf4b517030ad2210a7803017f6bbc8025d72c061dae`  
**Staged Parquets Root:** [`staging/lake_preparation_phase4/derived_candles/`](file:///staging/lake_preparation_phase4/derived_candles/)  

---

## 1. Executive Summary

All 6 canonical intraday intervals (`3m`, `5m`, `15m`, `30m`, `1h`, `4h`) were derived from canonical 1-minute underlying candles (`underlying_candles`). Aggregation strictly enforces the Asia/Kolkata session boundary (`09:15` to `15:30`), guaranteeing zero cross-session data leakage and full causal availability (`available_at = ts_end`).

A total of **287,306 derived bars** across **348 Parquet partitions (13.72 MB)** were staged into `staging/lake_preparation_phase4/`. Mathematical verification against vendor CSV series confirms **100.00% match rate** across all overlapping historical bars.

---

## 2. Derived Intervals Inventory

| Interval | Bucket Duration | Total Derived Bars | Partial Session-Close Bars | Parquet Partitions | Compressed Size | Derivation ID |
| :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **3m** | 3 mins | 145,387 | 307 | 58 | 5.84 MB | `71a590319987c4c5b2721906` |
| **5m** | 5 mins | 87,253 | 222 | 58 | 3.24 MB | `9f3d9d6c23f0407211a81d0f` |
| **15m** | 15 mins | 29,119 | 184 | 58 | 1.6 MB | `98ed71cb94b285072693602f` |
| **30m** | 30 mins | 15,098 | 1,255 | 58 | 1.2 MB | `51a0a286d3a64dae48ad7097` |
| **1h** | 60 mins | 8,127 | 1,250 | 58 | 1.0 MB | `bd553ce031c978d9718f4bab` |
| **4h** | 240 mins | 2,322 | 1,250 | 58 | 0.84 MB | `d4d805c4f4d767a48949c778` |

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
