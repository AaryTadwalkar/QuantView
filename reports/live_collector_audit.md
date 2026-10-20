# QuantView — Live Snapshot Collector Read-Only Inspection Report

**Target Script:** `Data_Collectors/live_option_chain.py`  
**Host Context:** Script runs continuously on dedicated collector machine (PC B, Windows 11)  
**Execution Date:** 2026-10-20  
**Inspection Type:** Strictly Read-Only Source Code & Empirical Output Audit  
**Operating Constraint:** In strict compliance with Owner Directive, the running live collector was **NOT** modified, stopped, restarted, or altered in any way.

---

## 1. Process & Architecture Overview

The script is a standalone Python polling process designed to collect 30-second live option chain snapshots for NIFTY 50 during Indian market hours (`09:15` to `15:30` IST).

- **Endpoints Consumed:**
  1. `GET https://api.upstox.com/v2/option/chain` (Base chain, strikes, underlying spot price, quotes)
  2. `GET https://api.upstox.com/v3/market-quote/option-greek` (Batch queries of up to 50 instruments for IV, Delta, Gamma, Theta, Vega)
- **Output Destination:**  
  `Data/live/option_chain/nifty/{EXPIRY_DATE}/{TRADE_DATE}/snapshots/{HH-MM-SS}.csv`
- **Cadence & Filtering:**  
  Sleeps 30 seconds between iterations. Employs `OptionChainSanityFilter` which suppresses saving unless spot price, total CE OI, total PE OI, or total volume changes, or the minute clock rolls over.

---

## 2. Key Technical Findings & Data Spec Discrepancies

| # | Inspection Category | Current Collector Reality | QuantView Data Spec Requirement | Discrepancy & Ingestion Impact |
|---|---|---|---|---|
| **1** | **Raw Payload Preservation** | Raw HTTP response JSONs are **discarded** in memory after parsing. | Mandatory raw archival of all API responses (`Data/raw/...`). | Historical raw responses are unrecoverable; canonical normalization must rely on saved CSV snapshots as surrogate raw source. |
| **2** | **Capture vs Row Separation** | Flattens capture metadata into every CSV row (`timestamp`, `spot_price` repeated across all strikes). | Relational separation: `option_snapshot_captures` (1 row per capture) and `option_snapshot_rows` (1 row per strike/side). | Downstream normalization (`M3-06`) must separate capture header from strike rows and assign deterministic `snapshot_id`. |
| **3** | **Timestamp Semantics** | Uses naive local system clock `now = datetime.now()`. No timezone offset. | Canonical timestamps must be UTC (`ts_start`, `received_at`) with explicit IST exchange display offset. | PC B local clock drift directly affects snapshot timestamp accuracy; timestamps must be localized to `Asia/Kolkata` during normalization. |
| **4** | **Sanity Filter & Gaps** | `OptionChainSanityFilter` skips writes if aggregate state does not change within the same minute. | Downstream engines must not assume continuous 30-second grid. | Irregular intervals (30s, 60s, 90s) between files are expected and legitimate; normalization must preserve gaps rather than interpolating. |
| **5** | **Path Arithmetic Defect** | Line 20: `PROJECT_ROOT = Path(__file__).resolve().parents[3]`. Evaluates to `C:\`. | Standard repository root anchoring. | In current repository layout, script would attempt writes to `C:\Data\...` instead of workspace root. Must be corrected when new collectors are built. |
| **6** | **Credential Exposure** | Line 15: `print(f"ACCESS_TOKEN USED: {ACCESS_TOKEN}")` prints raw secret to stdout. | Strict API Security Rules: No credentials in logs or output. | Severe security hazard in legacy script. New ingestion tools strictly redact credentials. |
| **7** | **Zero Field Imputation** | Lines 245–260: Missing values default to `0` (e.g. `ce_market.get("oi") or 0`). | Missing fields must remain `null` with explicit quality flags. | Normalization must distinguish true zero quotes from absent/unquoted strikes. |

---

## 3. Conclusion & Preservation Policy

The live snapshot collector on PC B continues to run undisturbed, successfully writing Schema v3 snapshot files. Its outputs are treated as immutable raw captures by the QuantView ingestion pipeline. All downstream canonicalization will handle its schema variations, timestamp peculiarities, and zero-imputation artifacts via the documented staging, quarantine, and normalization rules (`M3-06`).
