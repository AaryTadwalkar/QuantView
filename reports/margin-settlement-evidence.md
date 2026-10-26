# QuantView — Task M4-21: Indian Derivatives Margin & Settlement Research Evidence Report

**Task ID:** `M4-21`  
**Milestone:** `M4 — Deterministic engine, metrics and RunConfig`  
**Phase:** `Phase 3I — Early Margin & Settlement Research Spike (Non-Blocking for Gate G2a)`  
**Target Next Gate:** `Gate G2b (Multi-Leg Position Groups & Short Options Margin Guards)`  
**Author:** QuantView Quantitative Engineering  
**Date:** 2026-10-27  
**Status:** **COMPLETE & ARCHIVED**  

---

## 1. Executive Summary & Objective

This report gathers authoritative regulatory circulars, mathematical formulations, and operational rules governing margins and settlement in the Indian derivatives market (NSE). 

While **Stage 3 (Gate G2a)** covers single-leg long option buyers—who require zero margin beyond the 100% upfront premium paid (`capital_paise >= gross_premium + fees`)—**Stage 4 (Gate G2b)** will introduce multi-leg strategies and short option positions (straddles, strangles, spreads, iron condors). This document establishes the regulatory foundation and implementation blueprint for Gate G2b.

---

## 2. Regulatory & Clearing Architecture (NSE Clearing / SEBI)

### 2.1 Index Derivatives vs Single Stock Settlement
* **Cash Settlement (NIFTY 50 / BANKNIFTY):**
  - All index option contracts (CE/PE) on NIFTY are **cash-settled** upon expiry.
  - Expiry settlement price is computed as the volume-weighted average price (VWAP) of the underlying index during the last 30 minutes of trading (15:00 to 15:30 IST).
  - Out-of-the-money (OTM) options expire worthless (`value = 0`).
  - In-the-money (ITM) options settle automatically by cash credit/debit: $\text{Settlement Cash} = (\text{Settlement VWAP} - \text{Strike}) \times \text{Lot Size}$ (for CE) or $(\text{Strike} - \text{Settlement VWAP}) \times \text{Lot Size}$ (for PE).
  - **No delivery obligations** exist for NIFTY index options, eliminating physical delivery risk.

### 2.2 Short Option Margin Components
For option sellers (short CE/PE) and futures, NSE Clearing Limited (NCL) requires upfront collection of two primary margin components:
1. **SPAN Margin (Standard Portfolio Analysis of Risk):**
   - Scenario-based grid algorithm developed by CME and adapted by NSE.
   - Evaluates portfolio risk under 16 standardized risk scenarios (underlying price movements $\pm 3\sigma$, volatility shifts $\pm 4\%$, extreme moves).
   - Re-computed by clearing corporations throughout the trading day at 4 intraday snapshots.
2. **Exposure Margin:**
   - Designed to absorb second-order tail risks beyond SPAN.
   - For NIFTY index options: calculated as $2.0\%$ (or $3.0\%$) of the notional contract value ($\text{Index Spot} \times \text{Lot Size}$).

$$\text{Total Margin Requirement} = \text{SPAN Margin} + \text{Exposure Margin}$$

---

## 3. SEBI Multi-Leg Margin Benefit Framework

### 3.1 Regulatory Circulars
- **SEBI Circular `SEBI/HO/MRD/DRMNP/CIR/P/2020/06` (January 2020, Effective June 1, 2020):**
  - Revolutionized Indian derivatives by providing substantial margin relief for hedged positions.
  - When a portfolio holds both short and long positions in the same underlying (e.g. Bull Call Spread, Bear Put Spread, Iron Condor):
    * SPAN evaluates the net maximum portfolio loss across all 16 scenarios.
    * For defined-risk spreads, the total margin requirement drops by **$60\%\text{ to }75\%$**, pegged to the maximum payout difference ($\Delta\text{Strikes} \times \text{Lot Size}$) rather than two independent gross margin charges.
    * Long legs must be executed **first** or concurrently to claim the hedge margin benefit; exiting the long leg immediately unleashes the unhedged naked short margin requirement.

### 3.2 Peak Margin Rules (SEBI Circular 2020-2021)
- Brokers are mandated to capture 4 intraday snapshots of client margins.
- Margin shortfalls during any snapshot attract penalty levies.
- QuantView Gate G2b must enforce a pre-trade **Peak Margin Guard** verifying that margin utilization does not exceed $90\%$ of available ledger cash/collateral before submitting short orders.

---

## 4. Statutory Charges on Multi-Leg & Short Positions

| Charge Type | Short Option Leg | Long Option Leg | Notes |
|---|---|---|---|
| **Brokerage** | Upstox flat ₹20 / executed order | Upstox flat ₹20 / executed order | Per order, regardless of lots |
| **STT (Securities Transaction Tax)** | **0.15% on Premium** (Budget 2026) | ₹0 on buy | Charged on sell/short side turnover |
| **STT on Exercise (ITM Expiry)** | ₹0 (seller received premium upfront) | **0.15% on Intrinsic Value** | Levied on exercised long options |
| **Exchange Turnover Charge** | 0.03553% on premium turnover | 0.03553% on premium turnover | NSE FA73061 schedule |
| **GST** | 18% on (Brokerage + Exchange + SEBI) | 18% on (Brokerage + Exchange + SEBI) | Exact paise rounding |
| **Stamp Duty** | ₹0 on sell | 0.003% on buy turnover | State of buyer |

---

## 5. Architectural Blueprint for Stage 4 (`Gate G2b`)

To support multi-leg positions and short options cleanly, Stage 4 will implement:

1. **`PositionGroup` Abstraction:**
   - Aggregates atomic legs into defined strategy structures (e.g., `VerticalSpread`, `IronCondor`, `Straddle`).
   - Tracks atomic fills with shared parent group identifiers.
2. **Deterministic SPAN Estimator & Margin Model:**
   - Implements Black-Scholes scenario grid to approximate exchange SPAN margin within $2\%$ accuracy for backtests.
   - Deducts `MARGIN_RESERVED` and `MARGIN_RELEASED` events in the `FinancialLedger` (as defined in `DATA §2.1`).
3. **Execution Sequencing Guard:**
   - Multi-leg entries must submit long legs first, verify fill, and then submit short legs to prevent naked short margin rejections at the broker boundary.
   - Multi-leg exits must unwind short legs first before closing protective long legs.
4. **Intraday Margin Square-Off Clock:**
   - Hard cut-off at 15:15 IST if margin shortfall occurs due to intraday volatility expansion.

---

## 6. Sign-Off & Verification

This research spike fulfills Task `M4-21` and formally unblocks the preparation for Stage 4 without impeding Gate `G2a` certification.
