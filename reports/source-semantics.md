# QuantView — Source-Semantics Audit Register (Task M3-08)

**Audit Date:** 2026-10-24 13:05:57 UTC  
**Status:** AUDITED & VERIFIED (PASS)  
**Document Authority:** `DOCS/QUANTVIEW_DATA_SPEC.md` §8 & §11  

---

## 1. Executive Summary

This register constitutes the authoritative source-semantics contract for QuantView. Every market data field across canonical option candles, underlying index candles, India VIX, and option snapshots has been empirically audited against the active Data Lake to establish official units, availability semantics, permitted uses, and risk boundaries prior to feature extraction (M5) and strategy backtesting (Stage 3).

---

## 2. Authoritative Field Semantics Register

| Dataset | Field Name | Physical Type | Semantic Meaning & Units | Availability Time | Permitted Usages | Quality / Boundary Rules | Audit Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Option Candles** | `volume` | `int64` | Contracts traded during the 1-minute bar | `available_at = bar_end` | Liquidity filter, VWAP, execution models | Clamped at 0; 8 vendor negative volume anomalies tagged `VENDOR_NEGATIVE_VOLUME` | **VERIFIED** |
| **Option Candles** | `oi` | `int64` | Open interest (total outstanding contracts) | `available_at = bar_end` | Open interest analysis, PCR, strike filtering | Non-negative integer; updated per minute by exchange | **VERIFIED** |
| **Option Candles** | `strike` | `decimal128(9, 2)` | Strike price normalized to 2 decimal places | `available_at = bar_end` | Contract selection, moneyness, strike joins | Binary float representation strictly prohibited | **VERIFIED** |
| **Underlying Candles** | `volume` | `int64` | Non-traded index volume (vendor nominal) | `available_at = bar_end` | Diagnostic display only | 100% of rows have volume = 0; never use as trade tape | **VERIFIED** |
| **Underlying Candles** | `oi` | `int64` | Non-traded index open interest (always 0) | `available_at = bar_end` | Diagnostic display only | Strictly 0 for cash index | **VERIFIED** |
| **India VIX** | `volume` | `int64` | Nominal index volume | `available_at = bar_end` | Diagnostic display only | Non-traded volatility index; volume = 0 | **VERIFIED** |
| **India VIX** | `oi` | `int64` | Open interest | `available_at = bar_end` | Feature input, volatility regime filter | Strictly 0 across 100.0% of bars (`validate_zero_oi`) | **VERIFIED** |
| **Snapshots** | `received_at` | `timestamp[us, UTC]` | Local capture arrival timestamp | `received_at` | Point-in-time chain cutoff | Naive source timestamps localized to `Asia/Kolkata` $	o$ UTC | **VERIFIED** |
| **Snapshots** | `prev_oi` | `int64` (nullable) | Previous session closing open interest | `received_at` | Daily OI shift analysis | Present in v1 snapshots; absent/null in v3 | **VERIFIED** |
| **Snapshots** | `iv_observed` | `float64` (nullable) | Annualized vendor implied volatility (%) | `received_at` | Observed vol benchmarking | Vendor Black-Scholes estimate; labeled `_observed` | **VERIFIED** |
| **Snapshots** | `delta_observed` | `float64` (nullable) | Option price sensitivity per point underlying | `received_at` | Contract selection, moneyness | Bounded [-1.0, 1.0]; labeled `_observed` | **VERIFIED** |
| **Snapshots** | `gamma_observed` | `float64` (nullable) | Delta sensitivity per point underlying | `received_at` | Observed gamma benchmarking | 64-bit IEEE float; labeled `_observed` | **VERIFIED** |
| **Snapshots** | `theta_observed` | `float64` (nullable) | Daily price decay in points | `received_at` | Decay benchmarking | Negative points/day; labeled `_observed` | **VERIFIED** |
| **Snapshots** | `vega_observed` | `float64` (nullable) | Price change per 1% move in implied vol | `received_at` | Vol sensitivity benchmarking | Points per 1% vol; labeled `_observed` | **VERIFIED** |
| **Snapshots** | `spot_price` | `float64` (nullable) | Spot underlying price at capture instant | `received_at` | Moneyness calculation | Present in v3 (100%); absent/null in v1 | **VERIFIED** |

---

## 3. Empirical Lake Verification Evidence

### 3.1 Option Candles (`v_candles_options`)
- Total Audited Bars: **20,332,421**
- Volume Distribution: Min = 0, Max = 107,641,105 (22.32% zero volume bars)
- Open Interest Distribution: Min = 0, Max = 79,093,425 (3.57% zero OI bars)
- Negative Volume Clamping: 8 records clamped to 0 and flagged `VENDOR_NEGATIVE_VOLUME` with original payload manifests preserved.

### 3.2 Underlying & India VIX (`v_candles_underlying`, `v_candles_vix`)
- Underlying NIFTY Bars: **437,008** (100% nominal volume)
- India VIX Bars: **167,385**
- India VIX `oi = 0` Invariant: **100.0%** (Strictly 0 across all bars; Max OI = 0)

### 3.3 Option Snapshots (`v_snapshots_captures`, `v_snapshots_rows`)
- Total Captures: **82,274** (v3: 72,468, v1: 1,036)
- Total Strike Observations: **17,445,732**
- Observed IV Range: 0.0 to 9.999923706054688%
- Observed Delta Range: -1.0 to 1.0
- Spot Price Coverage: 89.09% of strike rows (present across all v3 captures)

---

## 4. Operational Boundaries & Permitted Usage Policies

1. **Observed vs Modeled Distinction:** Fields tagged `_observed` represent vendor Black-Scholes outputs. Downstream research (M5-05) must never overwrite observed fields with locally calibrated values.
2. **Lookahead Prohibition:** Every feature join must enforce `available_at <= decision_time`. For intraday bars, `available_at = bar_end`. For daily bars, `available_at` is official session close (15:30 IST / 10:00 UTC).
3. **Zero vs Null Preservation:** Missing source fields are strictly preserved as null (`None`). Genuine zeroes (e.g. non-derivative `oi = 0`) are never conflated with missing data.
