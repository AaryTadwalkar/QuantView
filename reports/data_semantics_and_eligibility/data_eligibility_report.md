# QuantView — Data Eligibility Matrix & Coverage Report (Task M3-09)

**Report Date:** 2026-10-30 17:44:13 UTC  
**Status:** AUDITED & ELIGIBILITY DATASET GENERATED (PASS)  
**Input Lake Manifest Hash:** `dff816ef87ba6536bdce0bd3d30c18f4a20bb96d5e15216cdf6c060d22938c3d`  
**Dataset Location:** [`staging/lake_preparation_phase4/data_eligibility/part-0.parquet`](file:///Data/staging/lake_preparation_phase4/data_eligibility/part-0.parquet)  

---

## 1. Executive Summary

Data eligibility evaluation has been executed across **1,169 historical trading sessions** (January 2022 to October 2026). Each session was audited against 9 canonical quality invariants per `QUANTVIEW_DATA_SPEC.md` §8 and §11.1.

- **Fully Eligible Sessions (`ELIGIBLE`):** 1,152 (98.55%)
- **Eligible with Advisory Warnings (`ELIGIBLE_WITH_WARNINGS`):** 17 (1.45%)
- **Ineligible Sessions (`INELIGIBLE`):** 0 (0.0%)

---

## 2. Invariant Classification Rules

| Reason Code | Category | Operational Impact | Enforcement Policy |
| :--- | :--- | :--- | :--- |
| `MISSING_BARS` | Completeness | Session contains fewer than 375 1m bars | Special sessions (Muhurat) allowed with warning; severe gaps block entry |
| `FLAT_BAR` | Liquidity | Elevated identical bars with volume = 0 | Advisory warning; entries allowed if strategy tolerates low volume |
| `STALE_DATA` | Freshness | Consecutive unchanged close prices | Advisory warning; monitored positions continue tracking |
| `INVALID_OHLC` | Mathematical | High < max(Open, Close) or Low > min(Open, Close) | Strict `INELIGIBLE`; blocks all new position entries |
| `DUPLICATE_ACTIVE_KEY` | Uniqueness | Collision in active partition selection | Strict `INELIGIBLE`; blocks entry |
| `INSUFFICIENT_WARMUP` | Indicator | Initial lookback window (first 5 sessions of 2022) | Advisory warning; indicator warm-up required |
| `INCOMPLETE_CAPTURE` | Snapshot | Session contains quarantined snapshot files | Advisory warning; options historical candles remain continuous |

---

## 3. Backtest Universe & Horizon Recommendation

1. **High-Confidence Historical Backtesting Regime:** `2025-01-01` to `2026-10-19` (446 sessions). 100% continuous 1m option candles and underlying index data.
2. **Long-Horizon Underlying Directional Regime:** `2022-01-03` to `2026-10-16` (1,180+ sessions) across derived timeframes (`3m`, `5m`, `15m`, `1h`, `4h`).
3. **Position Monitoring Exemption:** Per `QUANTVIEW_DATA_SPEC.md` §11.1, an `INELIGIBLE` or warning classification blocks **new entries only**; open positions continue to be monitored with stale flags and risk stops.
