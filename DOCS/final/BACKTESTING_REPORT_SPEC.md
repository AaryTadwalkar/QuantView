# QuantView — Backtesting Report and Click-to-Explain Metric Inspector Specification

| Field | Value |
|---|---|
| **Document ID** | `QV-SPEC-REPORT-001` (`DOCS/final/BACKTESTING_REPORT_SPEC.md`) |
| **Version** | `v1.4 (Hardened Implementation Baseline)` |
| **Release Date** | `2026-10-12` |
| **Authority Tier** | **Tier 4 · Specialized Contract** (subordinate to Tier 1 [`ADR_REGISTER.md`](ADR_REGISTER.md), Tier 2 [`HIGH_LEVEL_DESIGN.md`](HIGH_LEVEL_DESIGN.md), and Tier 3 [`LOW_LEVEL_DESIGN.md`](LOW_LEVEL_DESIGN.md)) |
| **Status** | `DESIGNED` — authoritative Tier 4 specification for `/backtests`, Backtest Report Artifacts, Result-Kind Separation, Normative Metric Basis, and Click-to-Explain Metric Inspector |
| **Parent Sections** | [`HIGH_LEVEL_DESIGN.md`](HIGH_LEVEL_DESIGN.md) (`§2 P3, P10, P12, P16, P18`, `§4`, `§16 ADR-003, ADR-016, ADR-031, ADR-032, ADR-034, ADR-036, ADR-038`), [`LOW_LEVEL_DESIGN.md`](LOW_LEVEL_DESIGN.md) (`§4.14`, `§8.4.6`, `§8.4.8`, `§8.5.4`, `§8.6.8`, `§8.10.5`, `§8.10.6`, `§13.10`) |
| **Subordination Rule** | This specification refines UI layout, metric inspection drawers, trade-risk attribution columns, and report completeness warnings for backtest and paper performance reports. Where any conflict arises with [`LOW_LEVEL_DESIGN.md`](LOW_LEVEL_DESIGN.md), [`HIGH_LEVEL_DESIGN.md`](HIGH_LEVEL_DESIGN.md), or an `OWNER_APPROVED` ADR in [`ADR_REGISTER.md`](ADR_REGISTER.md), the higher-tier document wins. |

---

## 1. Purpose and Architectural Principles

1. **Strict Result-Kind Separation (`P3`, `ADR-003`, `ADR-031`):**
   - **Mode B (`UNDERLYING_DIRECTIONAL`):** Evaluates signal quality on NIFTY 50 index points and R-multiples (`underlying.*` metrics). Mode B reports **never** display rupee (`₹`) values, option contract symbols, Sharpe/Sortino on cash equity, or brokerage charges (`T-RPT-5`, `T-ACC-13`).
   - **Mode C (`ACTUAL_OPTIONS`):** Evaluates executable option trades on observed historical option chains/quotes (`actual_options.*` metrics) in integer paise (`_paise`, displayed in `₹`) and net percentages after itemized Indian statutory and brokerage costs (`LLD §8.5`).
   - **Mode S (`SYNTHETIC_OPTIONS_ESTIMATE`):** Evaluates Black-76 synthetic option prices (`synthetic.*` metrics) solely for pre-archive scenario analysis, carrying a permanent red/amber `"SYNTHETIC OPTIONS ESTIMATE — NON-PROMOTABLE"` banner and calibration error against Mode C (`ADR-016`, `LLD §8.12.2`).
   - Metrics of different `result_kind` values can never be summed, averaged, or placed in the same leaderboard column without an explicit mode filter (`T-ACC-13`).
2. **Every Headline Number is Click-to-Explain (`P16`, `ADR-031`, `LLD §8.10.5`):** Clicking any summary metric card, table column header, or bootstrap confidence interval opens the `MetricInspectorDrawer` populated strictly from `GET /api/v1/backtests/{run_id}/metrics/{metric_id}` (or `GET /api/v1/paper/accounts/{id}/metrics/{metric_id}`). The browser performs zero metric arithmetic (`T-FE-UI-4`, `T-ACC-2`).
3. **Explicit Incomplete and Ambiguous Bounds (`P6`, `P12`, `ADR-034`, `ADR-036`, `LLD §8.4.6, §8.4.8`):** If unresolved trades exceed the thresholds of `LLD §8.4.5` (`> 2%` intraday) or `§8.4.7` (`> 10%` overnight), or if lower/upper exit-ordering bounds diverge by more than `25%` of `|net_pnl|` (`WIDE_BOUNDS`), the report header prominently displays `status = INCOMPLETE` or `WIDE_BOUNDS` alongside `[net_pnl_lower_bound_paise, net_pnl_upper_bound_paise]`.
4. **Exact Accounting vs. Analytical Attribution (`P10`, `P18`, `ADR-038`, `LLD §8.10.6`):** Every metric carries an explicit `attribution_nature ∈ {"EXACT_ACCOUNTING", "ANALYTICAL_CONVENTION"}` so users never confuse exact ledger/cash truth (`net_pnl_paise`, `gross_pnl_paise`, `total_charges_paise`) with convention-based per-deployment percentage returns or Sharpe ratios inside a shared `PORTFOLIO` account.

---

## 2. Backtest Report Workspace Layout (`/backtests`, `LLD §13.10`)

The `/backtests/{run_id}` workspace is organized into seven sections:

### 2.1 Section 1 — Run Header, Mandatory Assumptions Strip, and Honesty Banner
Every report header **must** display the following fields above the fold without requiring a drawer click:
- **Mode & Result-Kind Badge:**
  - Mode B: `MODE B — UNDERLYING DIRECTIONAL BACKTEST (POINTS / R ONLY)` (Blue `#2563EB`)
  - Mode C: `MODE C — ACTUAL HISTORICAL OPTIONS BACKTEST (₹ NET OF CHARGES)` (Emerald `#059669`)
  - Mode S: `MODE S — SYNTHETIC ESTIMATE ONLY (NON-PROMOTABLE)` (Amber/Red `#D97706`)
- **Mandatory Assumptions & Execution Strip:**
  - `fill_model` (`SPOT_NEXT_OPEN` / `OPT_SNAPSHOT_BIDASK` / `OPT_WS_QUOTE_BIDASK`), `latency` (`2s` / `500ms`), `slippage_ticks` (`1 tick = ₹0.05`), `fill_max_spread_rel` (`0.10`), `cost_model` (`version` + `VERIFIED` vs. `UNVERIFIED_BLOCKER`), `risk_profile` (`id@version`), `ceiling_mode` (`ENFORCE` vs. `RESEARCH_RELAXED`), and `n_trials_so_far`.
- **Mandatory Data Coverage & Sample Strip:**
  - `date_range`, `sessions_with_data / sessions_total`, `effective_sample {days_traded, closed_trades}`, `fill_source_mix {SNAPSHOT_30S, WS_QUOTE}`, and `schema_mix {v1, v2, v3, api_v4}`.
- **Completeness & Robustness Status Pills:**
  - `COMPLETE` (green)
  - `INCOMPLETE` (red — unresolved trades exceed threshold or required coverage cells failed)
  - `WIDE_BOUNDS` (amber — `|net_pnl_upper_bound - net_pnl_lower_bound| > 0.25 * |net_pnl|`)
  - `FRAGILE` (amber — `net_pnl <= 0` at `slippage_ticks = 2` or in `≥ 2` of the 8 parameter-perturbation grid neighbors, `LLD §8.9`)
  - `UNVERIFIED_BLOCKER` (red/amber — run executed while an external `[VERIFY]` parameter such as `upstox_nse_options.yaml` was not yet `VERIFIED`)

### 2.2 Section 2 — Pre-Run Eligibility and Data Coverage Panel (`LLD §4.14, §8.4.6`)
Displays the persisted `CoverageReport` and `EligibilityResult`:
- Session counts: `sessions_total`, `sessions_with_option_data`, `eligible_sessions`, `degraded_sessions`, `ineligible_sessions`.
- Signal funnel: `decisions_total` → `decisions_executable` → rejections by reason (`NO_DATA_FOR_EXPIRY`, `STALE_SNAPSHOT`, `GREEKS_UNAVAILABLE`, `STRIKE_NOT_LISTED`, `NO_VALID_QUOTE`, `SPREAD_TOO_WIDE`, `SPREAD_WIDENED_AT_FILL`, `PREMIUM_TOO_LOW`, `NO_FILL_SNAPSHOT`, `RISK_*`) → `trades_total`.
- Exit resolution summary: `RESOLVED`, `GAP_FILL`, `PATH_UNOBSERVED`, `AMBIGUOUS` (evaluated under both pessimistic `STOP_FIRST` and optimistic `TARGET_FIRST`), `LATE_EXIT`, `STALE_EXIT`, `LATE_OPEN_EXIT`, and `UNRESOLVED` / `UNRESOLVED_OVERNIGHT`, with `[net_pnl_lower_bound_paise, net_pnl_upper_bound_paise]`.

### 2.3 Section 3 — Headline Metric Cards (All Clickable → `MetricInspectorDrawer`)
- **Mode B Headline Cards:** `underlying.net_points`, `underlying.profit_factor`, `underlying.win_rate`, `underlying.expectancy_points`, `underlying.expectancy_r`, `underlying.max_drawdown_points`, `underlying.trade_count`, `underlying.overnight_gap_points` (when `duration_profile = OVERNIGHT`).
- **Mode C & Paper Headline Cards:** `actual_options.net_pnl_paise` (or `paper.net_pnl_paise`), `actual_options.gross_pnl_paise`, `actual_options.total_charges_paise`, `actual_options.cost_drag_pct`, `actual_options.return_on_starting_equity_pct`, `actual_options.max_drawdown_paise`, `actual_options.max_drawdown_pct`, `actual_options.profit_factor`, `actual_options.win_rate`, `actual_options.sharpe_daily`, `actual_options.sortino_daily`, `actual_options.unresolved_trades_count`.

### 2.4 Section 4 — Equity, Drawdown, and Bounds Chart
- Plots cumulative net P&L (points in Mode B; `₹` in Mode C/Paper) and underwater drawdown curve.
- Toggle between **Mark-to-Market Equity Curve** (`equity_paise = cash_paise + Σ_open qty × mark_bid_paise`) and **Realized-Only Closed-Trade Equity Curve** (`starting_equity_paise + cumulative_realized_net_pnl_paise`).
- When `ambiguous_exits > 0` or `unresolved_exits > 0` in Mode C, renders a shaded band between `net_pnl_lower_bound_paise` and `net_pnl_upper_bound_paise`.

### 2.5 Section 5 — Trades Table and Per-Trade Risk Overshoot Attribution (`ADR-032`, `LLD §8.6.8`)
Paginated table (`GET /api/v1/backtests/{run_id}/trades`) with click-through to `/chart` centered on the trade (`T-VIZ-3`). In Mode C and Paper reports, each trade row includes explicit **Risk Estimation vs. Realized Loss Attribution**:

| Column | Field Name | Description |
|---|---|---|
| Trade ID | `trade_id` | Stable ULID linking entry fill, exit fill(s), and `TradeInspection` |
| Owner Scope | `owner_scope_id` | `deployment_id`, `run_id`, or `'MANUAL'` (for manual paper trades) |
| Contract | `instrument_id` | Canonical ID (e.g., `OPT:NIFTY:2026-04-30:24500:CE`) |
| Entry / Exit Time | `entry_at`, `exit_at` | Displayed in IST with UTC on hover |
| Entry / Exit Spot | `entry_underlying_ref_px`, `exit_underlying_ref_px` | NIFTY 50 spot price at entry and exit |
| Entry / Exit Option Px | `entry_px_paise`, `exit_px_paise` | Option fill prices (`₹`) and `quote_provenance` badge (`WS_QUOTE` / `SNAPSHOT_30S`) |
| Qty | `qty_units` (`lots`) | Units and lot count (`lot_size_at_order` stored on trade) |
| Planned Risk (`RK-03/22`) | `planned_risk_paise` | Pre-trade stressed risk estimate (`max_loss_paise` using `stop_slip_ticks = 4` or full outlay if no premium stop) |
| Gross / Charges / Net P&L | `gross_pnl_paise`, `charges_paise`, `net_pnl_paise` | Exact integer-paise values reconciled to §8.5 cost model |
| Risk Overshoot | `overshoot_paise` | `max(0, -net_pnl_paise - planned_risk_paise)` when realized loss exceeds `planned_risk_paise` |
| Overshoot Cause | `overshoot_reason` | `NONE`, `OVERNIGHT_GAP`, `SNAPSHOT_GAP_SLIPPAGE`, `WIDE_SPREAD_EXIT`, or `FORCE_EXIT_SLIPPAGE` |
| Exit Resolution | `exit_reason` / `exit_resolution` | `STOP`, `TARGET`, `TIME_EXIT`, `EXPIRY_FORCE_EXIT`, `SIGNAL_EXIT` · `RESOLVED`, `GAP_FILL`, `PATH_UNOBSERVED`, `AMBIGUOUS`, `UNRESOLVED` |

### 2.6 Section 6 — Sensitivity Grids and Bootstrap Confidence Intervals (`LLD §8.9, §8.10.3`)
- **Slippage & Latency Grid:** Net P&L and Profit Factor across `slippage_ticks ∈ {0, 1, 2, 3}` and `latency_s ∈ {2, 5, 15, 30}` (or `{0.5, 1, 2, 5}` for WS quotes).
- **Parameter Perturbation Grid:** `±10%` and `±20%` perturbations around each numeric strategy parameter (`FRAGILE` flag if ≥ 2 of 8 immediate neighbors are negative).
- **Day-Block Bootstrap (`10,000` resamples, `seed = 20260101`):** 5th, 50th, and 95th percentile intervals for Net P&L, Profit Factor, Max Drawdown, and Sharpe, plus `n_trials` and Bonferroni-adjusted p-value (`LLD §11.12`).

### 2.7 Section 7 — Immutable Run Manifest (`LLD §8.9`)
Displays `run_id`, `strategy {id, version, spec_hash}`, `feature_versions`, `data_version`, `coverage_matrix_hash`, `calendar_version`, `cost_model {version, status}`, `risk_profile_id@version`, `seed`, `engine_version`, and the exact CLI reproducibility command (`qv backtest reproduce <run_id>`).

---

## 3. Normative Metric Basis & Click-to-Explain Inspector Contract (`ADR-031`, `LLD §8.10.5`)

### 3.1 Normative Metric Basis Table (Gross vs. Net, Realized vs. MTM, Per-Trade vs. Portfolio)

Every metric in `MetricRegistry` is governed by the following normative basis rules (no metric may mix gross and net or leave its equity series ambiguous):

| Metric ID (`<ns>.<name>`) | Basis (Gross vs. Net) | Equity / Return Series Basis | Aggregation Scope | Attribution Nature (`P18`) | Degenerate / Edge-Case Rule |
|---|---|---|---|---|---|
| `underlying.net_points` | Raw index points (slippage grid reported separately; no `₹` or charges) | Sum of closed resolved trade point deltas | Per closed resolved trade | `EXACT_ACCOUNTING` (points) | Excludes `UNRESOLVED_OVERNIGHT` trades (`INCOMPLETE` if `> 0`) |
| `<ns>.gross_pnl_paise` (`actual_options`, `paper`) | **Gross** of charges (`Σ (exit_proceeds_paise - entry_cost_paise)`) | Realized closed trades (`positions` proportional cost release) | Per closed resolved trade / fill leg | `EXACT_ACCOUNTING` | `0` when `closed_trades == 0`; excludes `UNRESOLVED` trades |
| `<ns>.total_charges_paise` | Itemized statutory + brokerage charges (`brokerage + txn + sebi + ipft + stamp + stt + gst`) | Sum across all executed fills (including entry fills of open trades in account ledger view; closed-trade charges in trade-summary view, explicitly labelled) | Per executed fill | `EXACT_ACCOUNTING` | Reconciles to 0 paise with `EXPENSE:*` journal lines (`T-COST-3`, `T-LG-19`) |
| `<ns>.net_pnl_paise` | **Net** of all itemized charges (`gross_pnl_paise - closed_trade_charges_paise`) | Realized closed resolved trades | Per closed resolved trade | `EXACT_ACCOUNTING` | Primary headline P&L; accompanied by `[net_pnl_lower_bound_paise, net_pnl_upper_bound_paise]` |
| `<ns>.profit_factor` | **Net** of charges (`Σ_{net_pnl > 0} net_pnl_paise / |Σ_{net_pnl < 0} net_pnl_paise|`); Gross PF is a separate secondary field `gross_profit_factor` | Realized closed resolved trades | Per closed resolved trade | `EXACT_ACCOUNTING` | If `losing_trades == 0` and `winning_trades > 0`: `value = null`, `status = "DEGENERATE_NO_LOSSES"`, display `"∞ (No Losing Trades)"`. If `closed_trades == 0`: `status = "NO_TRADES"` (`T-RPT-4`) |
| `<ns>.win_rate` | **Net** of charges (`count(net_pnl_paise > 0) / count(closed_resolved_trades)`) | Realized closed resolved trades | Per closed resolved trade | `EXACT_ACCOUNTING` | Breakeven trades (`net_pnl_paise == 0`) are in the denominator (`closed_resolved_trades`) and not in the numerator |
| `<ns>.max_drawdown_paise` & `<ns>.max_drawdown_pct` | **Net** of charges, **Mark-to-Market (`MTM`)** (`max_{t} (peak_equity_paise(t) - equity_paise(t))`, where `equity_paise(t)` uses non-stale snapshot/quote `bid_paise`) | Intraday + EOD Mark-to-Market (`MTM`) equity series (Realized-only drawdown is served separately as `realized_max_drawdown_paise`) | Account or single-strategy run time series | `EXACT_ACCOUNTING` at account/isolated level; `ANALYTICAL_CONVENTION` for per-deployment % in `SHARED_POOL` portfolio | `0` when equity never declines below peak; stale marks (`> limit`) excluded per `LLD §9.4` |
| `<ns>.return_on_starting_equity_pct` | **Net** of charges (`(ending_equity_paise - starting_equity_paise) / starting_equity_paise × 100`) | EOD Mark-to-Market equity (equals realized net P&L when flat) | Account / isolated run / deployment | `EXACT_ACCOUNTING` for `ISOLATED` & `PAPER_MANUAL`; **`ANALYTICAL_CONVENTION`** for a deployment inside a `PORTFOLIO` (uses `allocated_equity_paise` in `FIXED_BUDGET` or `account.starting_equity_paise` in `SHARED_POOL`, explicitly badged) | Refuses to sum percentages across separate accounts (`T-PRT-10`) |
| `<ns>.sharpe_daily` & `<ns>.sortino_daily` | **Net** of charges (`mean(r_d) / std_sample(r_d) × √252`, risk-free rate `0`, where $r_d = (\text{equity}_{\text{EOD},d} - \text{equity}_{\text{EOD},d-1}) / \text{equity}_{\text{EOD},d-1}$) | Daily EOD Mark-to-Market net return series $r_d$ across all trading sessions in the run window | Daily session aggregation (`√252`) | `EXACT_ACCOUNTING` for `ISOLATED` account; `ANALYTICAL_CONVENTION` for per-deployment slice in `PORTFOLIO` | **Mode B:** `NOT_APPLICABLE`. **Sample `< 60` sessions:** `status = "LOW_SAMPLE_WARNING"`. **Zero variance (`std_sample(r_d) == 0` or `downside_std == 0`):** `value = null`, `status = "DEGENERATE_ZERO_VARIANCE"`, display `"N/A (Zero Return Variance)"` (`T-RPT-4`, `T-RPT-5`) |

### 3.2 `MetricDetail` Payload Schema (`GET /api/v1/backtests/{run_id}/metrics/{metric_id}`)

```json
{
  "metric_id": "actual_options.profit_factor",
  "display_name": "Net Profit Factor (Actual Options)",
  "result_kind": "ACTUAL_OPTIONS",
  "attribution_nature": "EXACT_ACCOUNTING",
  "unit": "ratio",
  "value": 1.642,
  "formatted_value": "1.64",
  "status": "COMPLETE",
  "formula_latex": "\\mathrm{PF}_{\\mathrm{net}} = \\frac{\\sum_{i \\in W} \\mathrm{net\\_pnl\\_paise}_i}{\\left|\\sum_{j \\in L} \\mathrm{net\\_pnl\\_paise}_j\\right|}",
  "formula_text": "sum(net_pnl_paise for net_pnl_paise > 0) / abs(sum(net_pnl_paise for net_pnl_paise < 0))",
  "substitution": "418710 paise (₹4,187.10 across 19 winners) / 255000 paise (₹2,550.00 across 14 losers) = 1.6420",
  "variables": [
    {"symbol": "W", "meaning": "Closed resolved trades with net_pnl_paise > 0", "value": 19},
    {"symbol": "L", "meaning": "Closed resolved trades with net_pnl_paise < 0", "value": 14},
    {"symbol": "net_wins_paise", "meaning": "Sum of net_pnl_paise over W", "value": 418710},
    {"symbol": "net_losses_paise", "meaning": "Absolute sum of net_pnl_paise over L", "value": 255000}
  ],
  "steps": [
    {"step": 1, "label": "Filter closed resolved trades", "value": "34 closed trades (1 breakeven, 0 open, 0 unresolved)"},
    {"step": 2, "label": "Sum net P&L of winning trades (after itemized charges)", "value": "418,710 paise (₹4,187.10)"},
    {"step": 3, "label": "Sum absolute net P&L of losing trades (after itemized charges)", "value": "255,000 paise (₹2,550.00)"},
    {"step": 4, "label": "Divide winning sum by losing sum", "value": "418710 / 255000 = 1.642000"}
  ],
  "window": {
    "from_session": "2026-01-20",
    "to_session": "2026-04-30",
    "eligible_sessions": 68,
    "sampling": "PER_CLOSED_TRADE",
    "annualization": "NONE"
  },
  "edge_case_counts": {
    "winning_trades": 19,
    "losing_trades": 14,
    "breakeven_trades": 1,
    "open_trades_excluded": 0,
    "unresolved_trades_excluded": 0,
    "ambiguous_trades_included_as_stop_first": 1
  },
  "assumptions_and_limitations": [
    "Computed net of itemized Upstox + NSE statutory charges (cost_model 2026-10-10).",
    "1 ambiguous same-bar exit is included using the pessimistic STOP_FIRST rule; optimistic upper-bound PF is 1.71."
  ],
  "contributing_trade_ids": ["trd_01J...", "trd_01J..."]
}
```

### 3.3 Hand-Calculated Integer-Paise Report Verification Fixture (`LLD §8.5.4`, `T-COST-3`, `T-LG-19`, `T-RPT-1`)
Every Mode C and Paper report implementation must pass a unit and integration fixture built on the **2-Lot Entry + Two Partial Exits** trade of `LLD §8.5.4` (starting account equity = `2,000,000` paise = `₹20,000.00`, `lot_size = 75`, `tick_paise = 5`, `slippage_ticks = 1`):
- **Entry Fill (`ord_01`):** `BUY 150` units @ `10,005`p (`₹100.05`) → `entry_cost_paise = 1,500,750`p, `charges_paise = 3,039`p (`₹30.39`).
- **Partial Exit #1 (`ord_02`):** `SELL 75` units @ `11,995`p (`₹119.95`) → released cost `750,375`p, `gross_pnl_paise = +149,250`p, `charges_paise = 4,040`p (`₹40.40`), `net_pnl_paise = +145,210`p (`₹1,452.10`).
- **Final Exit #2 (`ord_03`):** `SELL 75` units @ `10,995`p (`₹109.95`) → released cost `750,375`p, `gross_pnl_paise = +74,250`p, `charges_paise = 3,908`p (`₹39.08`), `net_pnl_paise = +70,342`p (`₹703.42`).
- **Required Report Metric Outputs (`MetricRegistry` assertions):**
  - `actual_options.gross_pnl_paise` = `223500` (`+₹2,235.00`)
  - `actual_options.total_charges_paise` = `10987` (`₹109.87`)
  - `actual_options.net_pnl_paise` = `212513` (`+₹2,125.13`)
  - `actual_options.cost_drag_pct` = `10987 / 223500 × 100 = 4.915884%` (`"4.92%"`, `substitution: "10,987 paise / 223,500 paise = 4.9159%"`)
  - `actual_options.return_on_starting_equity_pct` = `212513 / 2000000 × 100 = 10.62565%` (`"+10.63%"`, `substitution: "212,513 paise / 2,000,000 paise = +10.6257%"`)
  - Ending `cash_paise` = Ending `equity_paise` = `2,212,513` paise (`₹22,125.13`).

---

## 4. Verification Test Mapping

| Test ID | Description |
|---|---|
| `T-RPT-1` | Every metric in `MetricRegistry` has a complete `MetricDefinition`; recomputing from `MetricDetail.variables` reproduces `MetricDetail.value` within `1e-9` and matches the §3.3 hand-calculated integer-paise fixture (`T-COST-3`, `T-LG-19`) |
| `T-RPT-2` | `MetricDetail.substitution` contains the exact numeric numerator/denominator values used in the calculation |
| `T-RPT-3` | Clicking any metric in `/backtests` or `/paper` opens the drawer and renders the exact server `MetricDetail` payload without client-side math (`T-FE-UI-4`, `T-ACC-2`) |
| `T-RPT-4` | Zero-loss (`DEGENERATE_NO_LOSSES`), zero-trade (`NO_TRADES`), all-breakeven, and zero-return-variance (`DEGENERATE_ZERO_VARIANCE` on Sharpe/Sortino) fixtures produce explicit status codes and never `NaN`, `Infinity`, or HTTP `500` |
| `T-RPT-5` | Mode B never exposes `₹` metrics or `sharpe_daily`; Mode C never mixes `underlying.*` and `actual_options.*`; `LOW_SAMPLE_WARNING` appears when `< 60` sessions (`T-ACC-13`) |
| `T-RPT-6` | Unresolved or ambiguous exits set `INCOMPLETE` / `WIDE_BOUNDS` and populate `[net_pnl_lower_bound_paise, net_pnl_upper_bound_paise]` |
| `T-RPT-7` | Per-trade `planned_risk_paise`, `overshoot_paise`, and `overshoot_reason` match the entry `RiskDecision` and realized exit fill (`ADR-032`) |
