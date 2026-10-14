# QuantView — Charting, Replay, and Strategy Visualization Specification

| Field | Value |
|---|---|
| **Document ID** | `QV-SPEC-CHART-001` (`DOCS/final/CHARTING_UX.md`) |
| **Version** | `v1.4 (Hardened Implementation Baseline)` |
| **Release Date** | `2026-10-12` |
| **Authority Tier** | **Tier 4 · Specialized Contract** (subordinate to Tier 1 [`ADR_REGISTER.md`](ADR_REGISTER.md), Tier 2 [`HIGH_LEVEL_DESIGN.md`](HIGH_LEVEL_DESIGN.md), and Tier 3 [`LOW_LEVEL_DESIGN.md`](LOW_LEVEL_DESIGN.md)) |
| **Status** | `DESIGNED` — authoritative Tier 4 specification for `/chart`, Chart Replay, Indicator Overlays/Panes, and Per-Deployment Strategy Visualization |
| **Parent Sections** | [`HIGH_LEVEL_DESIGN.md`](HIGH_LEVEL_DESIGN.md) (`§2 P1, P6, P7, P16, P17`, `§10`, `§16 ADR-008, ADR-029, ADR-033, ADR-035, ADR-041`), [`LOW_LEVEL_DESIGN.md`](LOW_LEVEL_DESIGN.md) (`§3.3`, `§5.1.9`, `§6.6`, `§8.8.5`, `§13.2`, `§13.4`, `§13.5`, `§13.9`) |
| **Subordination Rule** | This specification refines frontend presentation, interaction flows, and UI edge-case handling for the charting subsystem. Where any conflict arises with [`LOW_LEVEL_DESIGN.md`](LOW_LEVEL_DESIGN.md), [`HIGH_LEVEL_DESIGN.md`](HIGH_LEVEL_DESIGN.md), or an `OWNER_APPROVED` ADR in [`ADR_REGISTER.md`](ADR_REGISTER.md), the higher-tier document wins. |

---

## 1. Purpose and Architectural Principles

The `/chart` workspace is the primary visual surface for market-data inspection, indicator verification, causal historical replay, and non-destructive inspection of strategy deployments and backtest runs.

1. **Zero Browser Trading or Indicator Math (`P1`, `P16`, `ADR-005`, `ADR-035`):** The browser renders bar arrays, indicator series, and chart events computed by the backend (`FeatureEngine`, `ReplayService`, `StrategyRunner`). It never computes indicators, resamples bars, or infers signals client-side.
2. **No Silent Fabrication (`P6`, `LLD §13.2`):** Expected-but-missing bars (`GAP_EXPECTED_MISSING`) are rendered as explicit whitespace on the time axis via `ChartAdapter.setGaps()`, never interpolated or forward-filled (`T-FE-UI-1`).
3. **Provisional vs. Final Separation (`P1`, `LLD §4.10.2`, `§13.2`):** Forming live or higher-timeframe bars (`isFinal = false`) are drawn with a hollow outline and `"FORMING"` badge and are **never** promoted to final bars until the backend emits the finalized bar (`isFinal = true`). Provisional bars never anchor finalized trade markers or non-repainting indicator points (`T-FE-UI-2`).
4. **Canonical UTC Timestamp & Isolated IST Display-Coordinate Contract (`P7`, `ADR-008`, `ADR-041`, `LLD §13.2`):** Every API request/response, WebSocket message, Zustand store slice, trade marker (`candle_start`), price level (`fromT`, `toT`), and replay cursor uses canonical **UTC epoch seconds (`UtcEpochSec`)**. IST (`Asia/Kolkata`, `UTC+05:30`, no DST) is applied strictly inside the isolated chart display formatter/adapter boundary (`toLwDisplayTime` / `fromLwDisplayTime`) and never leaks back into stores, markers, or API queries (`T-FE-TIME-1…5`).
5. **Visualization Never Controls Execution (`P17`, `ADR-029`, `LLD §8.8.5`):** Showing or hiding a deployment's markers, stop/target levels, or automatic indicators writes only to `qv_core.viz_preferences` using the restricted `qv_viz` database role (`SELECT` on `qv_paper`, zero write privileges on `qv_paper`, `T-VIZ-4`).
6. **Spot-Axis Price Honesty (`LLD §6.6`, `§8.8.5`):** When option trades (`OPT:NIFTY:...`) are overlaid on the NIFTY 50 spot chart (`IDX:NIFTY50`), markers are anchored vertically at `underlying_ref_px` (the NIFTY spot price at the event instant), while `option_fill_px` and contract symbol are displayed in the marker badge and inspection drawer. Option premiums (e.g., `₹142.55`) are never plotted on the `~24,500` spot Y-axis (`T-VIZ-3`).

---

## 2. Chart Adapter & Canonical Timestamp Contract (`ADR-041`, `LLD §13.2`)

### 2.1 Branded `UtcEpochSec` and `ChartAdapter` TypeScript Interface

```ts
// frontend/src/lib/time.ts
// Branded canonical UTC epoch seconds type; prevents mixing display-shifted numbers with UTC timestamps
export type UtcEpochSec = number & { readonly __brand: 'UtcEpochSec' };

export interface Bar {
  t: UtcEpochSec;     // Canonical UTC epoch seconds of bar_start (e.g. 09:15 IST = 03:45 UTC)
  o: number;
  h: number;
  l: number;
  c: number;
  v?: number;
  isFinal: boolean;   // false = ephemeral forming bar; true = finalized immutable bar
  flags: string[];    // e.g. ['PARTIAL_BAR', 'RECONCILED_DIFF', 'OUTSIDE_SESSION']
}

export interface Point {
  t: UtcEpochSec;     // Canonical UTC epoch seconds of bar_start
  v: number | null;   // null during warm-up or after gap invalidation
  reason?: string;    // e.g. 'WARMUP', 'GAP_RESET', 'STALE_SNAPSHOT'
}

export interface Marker {
  eventId: string;
  groupId: string;    // 'dep:<id>' | 'run:<id>' | 'replay:<id>'
  t: UtcEpochSec;     // candle_start (UTC epoch seconds of mapped bar_start per LLD §3.3)
  eventTimeIso: string; // Exact event timestamp in UTC ISO-8601Z
  yPrice: number;     // underlying_ref_px on IDX:NIFTY50 chart; option_fill_px on option chart
  optionFillPx?: number;
  instrumentId: string;
  kind:
    | 'SIGNAL_LONG'
    | 'SIGNAL_SHORT'
    | 'SIGNAL_EXIT'
    | 'ORDER_ACCEPTED'
    | 'ORDER_REJECTED'
    | 'FILL_ENTRY'
    | 'FILL_EXIT'
    | 'STOP_TRIGGERED'
    | 'TARGET_HIT'
    | 'TIME_EXIT'
    | 'EXPIRY_FORCE_EXIT';
  label: string;      // e.g. 'D3 ▲ BUY CE 24500 @ ₹142.55'
  color: string;
}

export interface HLine {
  id: string;
  groupId: string;
  fromT: UtcEpochSec; // entry fill candle_start (UTC epoch seconds)
  toT: UtcEpochSec;   // exit fill candle_start, or current bar / replay cursor while open
  price: number;      // underlying_ref_px stop/target level on spot chart
  kind: 'INITIAL_STOP' | 'TRAILING_STOP' | 'TARGET';
  style: 'dashed' | 'dotted' | 'solid';
  color: string;
}

export interface ChartAdapter {
  setBars(bars: Bar[]): void;
  prependBars(bars: Bar[]): void;
  setGaps(intervals: { from: UtcEpochSec; to: UtcEpochSec; reason: string }[]): void;
  updateBar(bar: Bar): void;
  setOverlay(groupId: string, id: string, kind: 'line' | 'band', points: Point[], style: Style): void;
  setPane(groupId: string, id: string, kind: 'line' | 'histogram', points: Point[], style: Style, scale: ScaleSpec): void;
  setMarkers(groupId: string, markers: Marker[]): void;
  setLevels(groupId: string, levels: HLine[]): void;
  removeGroup(groupId: string): void;
  setReplayCursor(t: UtcEpochSec | null): void;
  onVisibleRangeChange(cb: (from: UtcEpochSec, to: UtcEpochSec) => void): void;
}
```

### 2.2 Canonical Time Transformation Rules (`ADR-041`, Blocker 2)
To prevent the `5h30m` (`19,800`s) offset class of defects between candles, trade markers, crosshair readouts, and replay cursors, all frontend code must obey four strict rules:

| Boundary | Canonical Representation | Transformation Rule | Verification Test |
|---|---|---|---|
| **Backend REST & WebSocket payloads** (`/candles`, `/features/compute`, `chart-events`, `/replay/sessions/*`) | UTC epoch ms (`t_ms`) or UTC ISO-8601 (`...Z`) | Converted immediately at `lib/api.ts` / `lib/ws.ts` ingress into branded `UtcEpochSec` (`Math.floor(t_ms / 1000)`). Never shifted by `+19,800`s in `api.ts`, `ws.ts`, or Zustand stores. | `T-FE-TIME-1`, `T-FE-TIME-5` |
| **Candle `bar_start` vs. Causal `available_at`** | `bar.t` = `bar_start` (`UtcEpochSec`); `available_at` = `bar_end` (`UtcEpochSec`) | A `1m` bar for `09:15–09:16 IST` has `bar.t = 03:45:00 UTC` and `available_at = 03:46:00 UTC`. Trade events occurring inside `[bar_start, bar_end]` carry `candle_start = bar_start` (`UtcEpochSec`) from the server (`LLD §3.3`, `§6.6`). | `T-FE-TIME-2`, `T-VIZ-3` |
| **Isolated Chart Display Boundary (`LightweightChartsAdapter`)** | Internal canvas rendering only | IST (`Asia/Kolkata`, `UTC+05:30`, no DST) is formatted via `localization.timeFormatter` and `timeScale.tickMarkFormatter` using `Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata' })`. If `LightweightChartsAdapter` applies a private `+19,800`s coordinate shift for internal Lightweight Charts tick alignment, that shift is encapsulated strictly inside private `toLwDisplayTime(t: UtcEpochSec)` and `fromLwDisplayTime(lw): UtcEpochSec` methods inside `LightweightChartsAdapter` and **never** escapes `ChartAdapter`. | `T-FE-TIME-1`, `T-FE-TIME-2`, `T-FE-TIME-4` |
| **Crosshair, Marker Tooltips, & Replay Seek Bar** | Dual IST + UTC display from `UtcEpochSec` | Every tooltip and replay cursor readout formats the same `UtcEpochSec` value as `"2026-01-20 09:15:00 IST (03:45:00 UTC)"`. User time inputs in the Replay Seek picker (`"11:30:00 IST"`) are parsed via `parseIstToUtcEpochSec()` (`06:00:00 UTC`) before calling `/replay/sessions/{id}/seek`. | `T-FE-TIME-3`, `T-FE-TIME-4` |

### 2.3 Pagination, Memory Bound, and Data-Quality Ribbon (`DqRibbon`)
1. **Windowed Fetching:** Initial load requests `GET /api/v1/candles?limit=5000` ending at the latest completed session bar (or replay cursor). Scrolling within 500 bars of the left edge triggers a cursor-paginated `prependBars()` call using unshifted `UtcEpochSec` bounds (`T-FE-TIME-5`). Browser memory is capped at at most 50,000 bars in the active store; older off-screen pages are evicted when panning far forward.
2. **Data-Quality Ribbon (`DqRibbon`):** A 12px horizontal track directly above the time axis color-codes each bar:
   - **Normal (`OBSERVED_VALID`):** transparent/neutral
   - **Amber (`FLAGGED` / `PARTIAL_BAR` / `RECONCILED_DIFF`):** warning indicator
   - **Red (`GAP_EXPECTED_MISSING` / `INVALID`):** missing-bar gap or corrupt bar
   - **Grey (`OUTSIDE_SESSION` / `HOLIDAY`):** non-trading interval
   Clicking any ribbon segment opens a popover listing the exact DQ flags and `CoverageMatrix` cell state.

---

## 3. Indicator Overlays, Panes, and Explainability (`ADR-035`, `LLD §5.1.9`)

### 3.1 Placement and Scale Rules
Every registered feature in `FeatureRegistry` (`GET /api/v1/features/catalogue`) declares `display_spec`:
- `placement: "overlay"` — rendered on the main price canvas (`scale_kind = "price"`, e.g., `sma`, `ema`, `vwap`, `bbands`, `supertrend`, `donchian`, `keltner`, `orb_high`, `orb_low`, `prev_day_high/low/close`).
- `placement: "pane"` — rendered in a dedicated sub-pane below the main canvas:
  - `scale_kind = "bounded_0_100"` (e.g., `rsi`, `adx`, `stoch_k`, `stoch_d`, with reference lines at `30/70` or `20/80`).
  - `scale_kind = "unbounded_zero"` (e.g., `macd`, `macd_signal`, `macd_hist`, `roc`, `cci`).
  - `scale_kind = "positive"` (e.g., `atr`, `rv`, `hv`, `iv_atm`, `pcr_oi`, `pcr_vol`).

### 3.2 Warm-Up, Gap Invalidation, and Repaint Contract
- Points where the feature is warming up or invalidated by a data gap (`gap > gap_tolerance_bars`) arrive from the backend as `v: null` with `reason: "WARMUP" | "GAP_RESET" | "STALE_SNAPSHOT"`.
- The chart adapter breaks the line across `null` points (no straight-line bridging across gaps or overnight resets for session-scoped features like `vwap`).
- All registered features satisfy `repaint_policy = "FINAL_BAR_ONLY"`: historical points on closed bars never change when new bars arrive.

### 3.3 Click-to-Explain Indicator Legend (`GET /api/v1/features/{name}/explain`)
Each active indicator appears in the top-left legend with its canonical column name (e.g., `ema_close_20`, `rsi_14_close`), current value at the crosshair, and an `(i)` button. Clicking `(i)` calls `GET /api/v1/features/{name}/explain?params=...` and opens the `FeatureExplanationDrawer` showing:
1. Symbolic mathematical formula and parameter-substituted formula (`formula_substituted`).
2. Warm-up bar count (`warmup_bars`), reset policy (`SESSION` vs. `CONTINUOUS`), and gap policy.
3. Exact `version` and `availability_rule` (`bar_end` or `snapshot.available_at`).
4. For deployment-attached indicators, whether the series source is `PERSISTED` (exact values recorded by `StrategyRunner` during execution) or `RECOMPUTED` (re-evaluated at the deployment's pinned `feature_versions`).

---

## 4. Per-Deployment Strategy Visualization (`ADR-029`, `ADR-035`, `P17`, `LLD §6.6, §8.8.5, §13.9`)

### 4.1 Strategy Overlay Panel
The right-hand collapsible **Deployments & Runs Overlay Panel** lists all paper deployments (`GET /api/v1/paper/deployments`) and pinned backtest runs:
- **Master Toggle (`Show on chart`):** Off by default (`viz.default_enabled = false`).
- **Sub-Toggles per Group (`dep:<id>`):**
  - `Markers` (signals, order acceptances/rejections, entry/exit fills)
  - `Stop / Target Levels` (horizontal lines spanning entry fill `bar_start` to exit fill `bar_start` or current bar)
  - `Indicators` (automatic rendering of every feature declared in the strategy's `required_columns()`)
- **Filters:** Portfolio, deployment, strategy version, contract (`instrument_id`), time window, and event kind (`SIGNALS`, `ORDERS`, `FILLS`, `EXITS`).
- **Execution Isolation Banner:** The panel header displays: *"Visualization Controls Only — Toggling overlays never pauses, stops, or modifies strategy execution."* Preferences persist via `PUT /api/v1/viz/preferences/{deployment_id}` (`qv_core.viz_preferences`).

### 4.2 Automatic Indicator Resolution and `FEATURE_VERSION_DRIFT`
When `Show on chart` and `Indicators` are enabled for `deployment_id`:
1. The UI calls `GET /api/v1/paper/deployments/{id}/chart-spec?tf=...&from=...&to=...`.
2. The backend checks whether the current `FeatureRegistry` version for every required feature matches `deployments.feature_versions`:
   - **Match:** Returns the resolved indicator series (`source: "PERSISTED"` where stored in `FeatureStore`, otherwise `"RECOMPUTED"` at the pinned version) and plots them in the group's namespace (`dep:<id>:<col>`).
   - **Mismatch (`409 FEATURE_VERSION_DRIFT`):** If a feature's code version in `FeatureRegistry` differs from the deployment's pinned version and no `PERSISTED` series covers the window, the backend returns `409 FEATURE_VERSION_DRIFT`. The UI displays an amber banner on that deployment row (*"Indicator version differs from deployed version; indicator not drawn"*) while still rendering persisted trade markers and levels (`T-FE-14`, `T-ACC-9`).

### 4.3 Multi-Deployment Visual Disambiguation
When multiple deployments (either across isolated accounts or within a combined `PORTFOLIO` account) are enabled simultaneously:
- Each deployment is assigned a deterministic distinct color token (`D1` Amber `#F59E0B`, `D2` Cyan `#06B6D4`, `D3` Violet `#8B5CF6`, `D4` Emerald `#10B981`, `D5` Rose `#F43F5E`) and short prefix badge (`D1`, `D2`, …).
- If two deployments share an identical indicator column (e.g., both use `ema_close_20` at version `1`), both remain bound to their own `groupId` (`dep:<id1>`, `dep:<id2>`) so calling `removeGroup('dep:<id1>')` when `D1` is toggled off never removes `D2`'s indicator line (`T-FE-UI-3`, `T-VIZ-5`, `T-ACC-10`).
- When two markers land on the same candle `bar_start`, markers stack vertically with a 14px offset and preserve independent click hitboxes.

### 4.4 Marker Click and `TradeInspection` Drawer (`LLD §8.8.5`)
Clicking any marker calls `GET /api/v1/paper/events/{event_ref}` and opens the **Trade & Signal Inspection Drawer**, displaying:
- Identity: `deployment_id`, `account_id`, `portfolio_id` (if applicable), `strategy_id@version`, `decision_id`, `order_id`, `fill_id`.
- Instrument & Price Context: `instrument_id`, candle `tf` and `bar_start` / `bar_end`, `underlying_ref_px` (spot price at event), `option_fill_px` (option execution price), `qty_units` (units and lots), `quote_provenance`.
- Timestamps (both IST and UTC): `signal_at`, `order_created_at`, `order_accepted_at`, `fill_at`.
- Indicator Snapshot: exact key-value map of `feature_snapshot` (`ema_close_20`, `rsi_14_close`, etc.) that caused the entry/exit decision.
- Risk & Accounting: initial stop, trailing stop, target, exit reason (`STOP`, `TARGET`, `TIME_EXIT`, `EXPIRY_FORCE_EXIT`, `KILL_FLATTEN`), `planned_risk_paise`, `gross_pnl_paise`, itemized `charges_paise`, and `net_pnl_paise` (`EXACT_ACCOUNTING` from the owning deployment and account, `T-VIZ-7`).

---

## 5. Historical Chart Replay (`ADR-033`, `LLD §13.5`)

### 5.1 Three Explicit Replay Modes (`replay_sessions.kind`)
The Replay Bar supports three explicit modes, enforced by `CHECK (kind IN ('CHART_REPLAY','EVENT_REPLAY','BACKTEST_REPLAY'))` in `qv_core.replay_sessions` (`LLD §9.5`) when creating a replay session (`POST /api/v1/replay/sessions`):

| Replay Kind | Required Source | What is Revealed at Cursor `T` (`available_at <= T`) | Banner Text |
|---|---|---|---|
| `CHART_REPLAY` | `instrument`, `tf`, `start_at`, optional `features[]` | Completed candles (`bar_end <= T`), optional forming HTF bar (`PROVISIONAL`), and causal indicator values (`available_at <= T`). No trade markers. | `REPLAY (CHART) — Historical Market Data Only` |
| `EVENT_REPLAY` | Above + `deployment_id` | Above + persisted signals, orders, fills, and active stop/target levels recorded during `deployment_id`'s actual `STARTED…STOPPED` lifetime with `event_time <= T`. | `REPLAY (DEPLOYMENT EVENTS) — Historical Recorded Deployment` |
| `BACKTEST_REPLAY` | Above + `run_id` | Above + persisted decisions, orders, fills, and active stop/target levels from backtest `run_id` with `event_time <= T`. | `REPLAY (BACKTEST RUN) — Historical Simulation` |

**Non-Fabrication Rule (`T-RPL-6`):** In `EVENT_REPLAY`, if the cursor is outside the deployment's recorded `[started_at, stopped_at]` window, the UI displays *"No recorded deployment activity at cursor"* and never synthesizes hypothetical paper trades.

### 5.2 Server-Authoritative Cursor and Zero-Leakage Guarantee
1. **Cursor Snapping (`T-RPL-8`):** Selecting a start timestamp snaps `cursor_at` to the `bar_end` of the latest completed base-timeframe bar `<= start_at`. If `start_at` falls inside a missing-bar gap, the gap is rendered as whitespace up to the cursor without fabricating a bar.
2. **Clamped Reads & `422 REPLAY_FUTURE_REQUEST` (`T-RPL-1`, `T-RPL-3`):** Every `/replay/sessions/{id}/bars`, `/features`, and `/events` query is validated on the server against `cursor_at`. Any request with `to > cursor_at` is rejected with `422 REPLAY_FUTURE_REQUEST` (`Cache-Control: no-store`). The browser Zustand store never pre-fetches or caches future bars beyond `cursor_at`.
3. **Open-Trade Level Clamping (`T-RPL-7`):** If a trade entered at `t_entry <= cursor_at` and exited at `t_exit > cursor_at`, its horizontal stop and target lines are drawn only from `t_entry` to `cursor_at`, and its realized P&L badge and exit marker remain hidden until `cursor_at >= t_exit`.
4. **Controls & Determinism (`T-RPL-4`, `T-RPL-5`):**
   - Transport controls: `Play`, `Pause`, `Step +1`, `Step +N`, `Step -1`, `Step -N`, `Seek to Timestamp`, and speed selector `{0.5, 1, 2, 5, 10, 20}` bars/second.
   - Keyboard shortcuts (active when focus is not in an input field): `Space` (Play/Pause), `RightArrow` (Step +1), `LeftArrow` (Step -1), `Shift+RightArrow` (Step +5), `Shift+LeftArrow` (Step -5).
   - Stepping backward (`Step -1`) truncates the browser store to `<= new_cursor_at`; stepping forward again yields byte-identical JSON payloads (`T-RPL-4`, `T-RPL-5`).

---

## 6. Edge-Case Matrix and Acceptance Tests

| Scenario | Required UI & Backend Behavior | Verification Test ID |
|---|---|---|
| **Opening (`09:15 IST`) and closing (`15:29 IST`) bar timestamp round-trip** | `2026-01-20 09:15:00 IST` (`1768880700` `UtcEpochSec`) and `15:29:00 IST` (`1768903140` `UtcEpochSec`) display as `09:15` and `15:29` IST on axis while `onVisibleRangeChange` emits exact unshifted `UtcEpochSec` | `T-FE-TIME-1` |
| **Marker-to-candle alignment across `1m`, `5m`, `15m` timeframes** | A fill at `09:17:04 IST` (`03:47:04 UTC`) anchors to `09:17 IST` (`1m`), `09:15 IST` (`5m`), and `09:15 IST` (`15m`) candle `bar_start` with zero `5h30m` (`19,800`s) offset | `T-FE-TIME-2`, `T-VIZ-3` |
| **Crosshair & marker tooltip dual-time formatting** | Hovering any bar or marker renders both `"YYYY-MM-DD HH:MM:SS IST"` and `"(HH:MM:SS UTC)"` from the single canonical `UtcEpochSec` | `T-FE-TIME-3` |
| **Replay seek & step timestamp round-trip** | Seeking to `"11:30:00 IST"` sends `cursor_at = "2026-01-20T06:00:00Z"` to backend and draws the replay cursor on the `11:25–11:30 IST` (`5m`) bar | `T-FE-TIME-4` |
| **Viewport scroll lazy-load pagination round-trip** | Panning left calls `/candles?from=...&to=...` with unshifted `UtcEpochSec`; prepended bars join cleanly without duplicate or missing boundary bars | `T-FE-TIME-5` |
| Missing 1m bars inside session (`11:14–11:16`) | `setGaps()` draws whitespace; `DqRibbon` shows red segment; indicators with `gap > gap_tolerance_bars` break line (`v: null, reason: 'GAP_RESET'`) | `T-FE-UI-1`, `T-MD-5` |
| Live bar still forming (`11:17:22`, `isFinal = false`) | Drawn hollow with `"FORMING"` pill; never promoted to final bar without backend `isFinal = true` event; excluded from finalized indicator values and strategy markers | `T-FE-UI-2` |
| Option fill marker on NIFTY spot chart | Marker plotted at `underlying_ref_px` (e.g., `24,518.30`) with badge `D3 ▲ BUY CE 24500 @ ₹142.55`; Y-axis never rescales to `142.55` | `T-VIZ-3`, `T-ACC-7` |
| Toggling deployment overlay off during live paper run | `removeGroup('dep:<id>')` removes drawings; `PUT /viz/preferences/{id}` writes `qv_core`; zero effect on `StrategyRunner` or `qv_paper` | `T-FE-UI-3`, `T-VIZ-1`, `T-VIZ-4`, `T-ACC-5`, `T-ACC-6` |
| Feature code edited after deployment started | `GET /paper/deployments/{id}/chart-spec` returns `409 FEATURE_VERSION_DRIFT` if no persisted series exists; UI shows drift warning and suppresses indicator line | `T-FE-14`, `T-ACC-9` |
| Replay step with poisoned post-cursor data | Replacing all Parquet rows after `cursor_at` with `NaN` produces byte-identical bars, features, and events | `T-RPL-1…8`, `T-ACC-1` |
| Two deployments sharing `ema_close_20` on same chart | Distinct group namespaces (`dep:1`, `dep:2`), distinct colors/labels; hiding `dep:1` leaves `dep:2` intact | `T-VIZ-5`, `T-ACC-8`, `T-ACC-10` |
