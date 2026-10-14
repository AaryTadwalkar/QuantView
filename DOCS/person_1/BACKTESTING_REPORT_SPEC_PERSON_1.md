# QuantView — Backtest Report and Metric Inspector Specification

| Field | Value |
|---|---|
| Document | `docs/BACKTESTING_REPORT_SPEC.md` |
| Status | v1.2 — **DESIGNED** (not implemented/tested/verified; LLD Appendix C) |
| Authority | Report layout, metric catalogue text and inspector behaviour. Metric *definitions* and the `MetricDetail` contract are LLD §8.10 and §8.10.5; endpoints LLD §12.2.1. Test T-MI-3 requires the ids below to equal the ids the backend exposes. LLD wins on conflict. |
| Tickets | T5.7, T5.8, T6.8 |

## 1. Report structure (top to bottom)
1. **Header:** `result_kind` badge (`UNDERLYING_DIRECTIONAL` blue-outline "POINTS ONLY", `ACTUAL_OPTIONS` "₹ NET OF CHARGES", `SYNTHETIC_ESTIMATE` hatched "SCENARIO — NOT RESULTS"), run id, strategy `id@version`, status `COMPLETE` / `INCOMPLETE`, `RISK_RELAXED — NOT DEPLOYABLE AS IS` when applicable.
2. **Warnings strip:** `INCOMPLETE`, `PARTIAL_COVERAGE`, `DEGRADED_SESSIONS_INCLUDED(n)`, `UNVERIFIED_CALENDAR`, `UNVERIFIED_PARAM`, `UNRESOLVED_EXITS(n)`, `AMBIGUOUS_EXITS(n)`, `FRAGILE`, `SYNTHETIC` — each links to the panel that explains it.
3. **Eligibility & coverage:** `EligibilityReport` (sessions included/excluded with reasons, calendar version) and the coverage matrix heat-map (session × expiry; click → L3 strike detail).
4. **Summary metrics:** one tile per metric of §3; **every tile is clickable** (§4).
5. **Equity curve and drawdown** (Mode C/PAPER; Mode B shows cumulative points and point drawdown instead).
6. **Trades:** table (entry/exit time, direction, instrument, qty, entry/exit price, gross, charges, net, exit reason, `exit_resolution`, `fill_source`, flags) + chart markers; click a row or marker → per-trade drawer.
7. **Execution assumptions:** fill model(s) and versions, latency, slippage, quote requirements, fill-source mix, cost-model version and `status` (`VERIFIED`/`UNVERIFIED_PARAM`), risk mode and profile `id@version`.
8. **Charge breakdown:** brokerage, STT, exchange, SEBI, IPFT, stamp, GST — totals and per-trade average.
9. **Risk panel (Mode C/PAPER):** planned vs realised risk — share of losing trades with overshoot ratio > 1, p95 ratio, `RISK_CLAMPED`/`RISK_BELOW_ONE_LOT` counts. *No "maximum loss" is ever derived from an underlying stop.*
10. **Sensitivity grids** (§LLD 8.10.4, `FRAGILE` flag) and **bootstrap confidence intervals** (day-block, `ci95`, `p`, `p_adj`, `n_trials_so_far`) where supported.
11. **Reproducibility:** manifest (data/calendar/rules/semantics hashes, strategy `id@version` + `spec_hash` + params, feature versions, fill/cost models, engine version, seed, `manifest_hash`, `result_hash`) and a **Re-run & verify** button (determinism check).

## 2. Kind separation (never mixed)
Metric ids are namespaced `<result_kind>.<name>`. The UI never sums, averages or compares headline metrics across kinds, never places two kinds in one chart axis, and refuses to render a `MetricDetail` whose kind differs from the run's (T-MI-4). Comparing two runs is allowed only within one kind and shows both manifests. Mode B never displays ₹. Paper and live results are separate kinds with their own banners.

## 3. Metric catalogue
Common treatment rules: **breakeven** (`net = 0`) counts in `n_trades`, in the denominator of `win_rate` and in `expectancy`, but is neither win nor loss for averages or profit factor; **open at end** (OVERNIGHT) is excluded from realised metrics, marked to bid in equity and listed `OPEN_AT_END`; **UNRESOLVED** trades are excluded, listed, and bounded (`net_pnl_if_unresolved_total_loss`); **INCOMPLETE** runs carry the label on every affected tile.

### 3.1 `ACTUAL_OPTIONS` (₹) and `PAPER` (same formulas, different kind id)
| Metric id | Formula (text) | Variables / intermediates shown | Notes |
|---|---|---|---|
| `…gross_pnl_total` | Σ_i (exit_px_i − entry_px_i) × qty_i | n_closed, Σ per-trade gross | long options only |
| `…charges_total` | Σ_i (entry charges_i + exit charges_i), per component | component totals | cost model version |
| `…net_pnl_total` | Σ_i (gross_i − charges_i) | gross_total, charges_total | headline; excludes UNRESOLVED |
| `…cost_drag` | charges_total / Σ_i max(gross_i, 0) | numerator, denominator | null if denominator 0 |
| `…win_rate` | #(net_i > 0) / n_closed | wins, breakeven, losses, n_closed | |
| `…avg_win` / `…avg_loss` | mean of net_i over net_i > 0 / over net_i < 0 | counts, sums | loss reported negative |
| `…payoff` | avg_win / abs(avg_loss) | both | null if no losses |
| `…profit_factor` | Σ wins / abs(Σ losses) | Σ wins, Σ losses | null with note if no losses; breakeven excluded |
| `…expectancy` | (Σ_i net_i) / n_closed | Σ net, n_closed | per trade, ₹ |
| `…max_drawdown_inr` / `…max_drawdown_pct` | max_t (running_max_equity_t − equity_t) / that ÷ running_max | peak time, trough time, peak, trough | equity marked at bid at every snapshot/fill |
| `…sharpe_daily` | mean(r_d) / std(r_d, ddof=1) × √252 | mean, std, N, risk-free = 0 | r_d = equity_close_d / equity_close_{d−1} − 1 over all included sessions (flat days = 0); null `INSUFFICIENT_DAYS` if < 60 days with trades; annualization 252 shown |
| `…sortino_daily` | mean(r_d) / DD × √252, DD = √((1/N) Σ min(r_d − 0, 0)²) | mean, DD, N, MAR = 0 | same gating; null if DD = 0 |
| `…exposure_time` | in-position session minutes / total session minutes | both | |
| `…risk_overshoot_p95` | 95th percentile of realised_loss / planned_risk over losing trades with a plan | n, ratios artifact | null without planned risk |
| `…bootstrap_ci95`, `…p_one_sided`, `…p_adj` | day-block bootstrap, B = 10,000, seed from manifest; p_adj = min(1, p × n_trials) | resamples, seed, n_trials | "not distinguishable from zero" if ci95 contains 0 |
| `…effective_sample` | days traded, trades | counts | shown with every headline |

### 3.2 `UNDERLYING_DIRECTIONAL` (points)
`hit_rate`, `expectancy_points`, `avg_win`, `avg_loss`, `payoff`, `profit_factor`, `cum_points`, `max_drawdown_points`, `net_points(h)` and `expectancy(h)` for `h ∈ {0,2,4,6,8}`, `avg_bars_held`, `mfe_mean`, `mae_mean`, and for OVERNIGHT: `gap_points_mean`, `session_points_mean`, `gap_decided_share`. Formulas as LLD §8.10.1 and §8.3.5–§8.3.6 (`pnl_points = exit − entry` BULLISH / `entry − exit` BEARISH, after slippage). Mode B has no Sharpe/Sortino (no equity curve) and no ₹.

### 3.3 Features/indicators
Each feature has an explanation panel (formula, parameters, input series, outputs, warm-up behaviour, repaint flag) from `/features/{name}/explain`; the backtest report links to every feature version its strategy used.

## 4. Click-to-explain inspector
Clicking a tile opens a right-hand drawer rendered from `GET /backtests/{run_id}/metrics/{metric_id}` (`MetricDetail`). Sections, in this order:
1. **Formula** — `formula_tex` rendered, `formula_text` copyable.
2. **Variables** — symbol, meaning, unit.
3. **Actual values used** — `inputs` (e.g. Σ wins = ₹48 210, Σ losses = ₹31 905, n = 64) and the backend-produced **substitution** line with the numbers inserted; large series are artifact links (open as a table/chart).
4. **Calculation period and aggregation** — dates, sessions, trades included and excluded by reason, aggregation sentence.
5. **Treatment** of breakeven, open, unresolved and incomplete trades.
6. **Annualization and sampling** — factor (e.g. 252), convention, whether applied; `NULL_INSUFFICIENT_DATA` reason when null.
7. **Assumptions and limitations**, and **links to trade-level records** (`trade_filter` opens the trades table pre-filtered: wins, losses, `excluded:UNRESOLVED`, …).
Footer: `definition_version`, `verified_by_recompute` badge (an independent evaluator re-derived the value from the shown inputs at report build), copy-as-JSON. The frontend contains **no metric arithmetic** (lint rule, T-MI-6); everything shown is backend text and numbers.

## 5. Per-trade drawer
Entry and exit chain (signal → order → fill, with `fill_source`, `exit_resolution`, flags `gap`, `ambiguous`, `LIQUIDITY_UNCHECKED`, `LATE_EXIT`…), contract details, indicator values at decision, stop/target/trail values with basis, planned risk vs realised loss, gross/charges/net with component breakdown, links to the chart candle and to the snapshots/quotes used.

## 6. Chart markers for backtests
Same glyphs and anchoring rules as CHARTING_UX.md §5; group id = run id; tooltips show `run_id` and `strategy_version`. Underlying-basis stops are drawn on the index axis; premium-basis levels appear only in the drawer.

## 7. Exports
Trades CSV, equity CSV, manifest JSON, `metrics_detail.json`. Exports carry `result_kind` and `manifest_hash` in the header/filename.

## 8. Acceptance (all **PENDING**; gate G5.1)
| ID | Check |
|---|---|
| T-MI-1…6 | LLD §8.10.5 |
| T-RPT-1 | Kind badge, banner and warnings correct for B, C, S and an INCOMPLETE run |
| T-RPT-2 | No aggregate or chart combines two kinds; comparison across kinds is refused |
| T-RPT-3 | `INCOMPLETE`, `SYNTHETIC`, `FRAGILE`, `UNRESOLVED_EXITS` labels appear on the tiles they affect and in exports |
| T-RPT-4 | Reproducibility panel: re-run yields identical `manifest_hash` and `result_hash` |
