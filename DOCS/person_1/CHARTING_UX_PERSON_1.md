# QuantView — Charting and Replay UX Specification

| Field | Value |
|---|---|
| Document | `docs/CHARTING_UX.md` |
| Status | v1.2 — **DESIGNED** (nothing here is implemented, tested or verified; see LLD Appendix C) |
| Authority | UI behaviour only. Contracts (APIs, schemas, states) are in the LLD: §13.2 chart adapter, §12.2.1 replay/candle endpoints, §5.1.9 feature display, §4.8.1 repositories. On conflict the LLD wins. |
| Tickets | T1.7 (adapter), T3.8 (display metadata), T3.9 (replay), T7.11 (deployment overlays) |

## 1. Principles
1. **Accuracy over resemblance to TradingView.** Where fidelity and looks conflict, fidelity wins.
2. **The backend is authoritative.** The browser displays bars, indicator series, replay frames, markers and levels supplied by the API. It computes nothing that affects a decision or a number.
3. **Nothing is fabricated.** A missing bar is a visible gap with a reason; a provisional live bar never looks final; a marker never claims a price the order did not have.
4. **Lightweight Charts stays behind `ChartAdapter`.** The commercial Advanced Charting Library and native Pine Script execution are out of scope.

## 2. Data fidelity
| Topic | Rule |
|---|---|
| Timestamps | Data keeps `t_utc_ms`. The axis, crosshair and tooltips render **Asia/Kolkata** via the library's time formatters (fallback shift only if the pinned version cannot; T1.7 records the evidence). Tooltips show IST; hover-detail shows the raw UTC instant. Daily bars are keyed by `session_date`. |
| Missing bars | `/candles?include_gaps=true` returns whitespace entries for expected-but-absent bars. The chart draws an empty slot (not a connecting line) and the DQ ribbon marks it with its reason code (`COLLECTOR_GAP`, `PROVIDER_OMITTED`, …). Closed-market time (holiday, overnight) is not a gap and is not marked as one. |
| Bar states | **Final** (solid), **provisional** (live, outlined/hatched, labelled "forming"), **partial** (`PARTIAL_BAR`, dashed outline), **flagged** (amber ribbon: `SUSPECT_JUMP`, `FLAT_RUN`, `CONFLICT`, …), **invalid/quarantined** (not in canonical data: shown as a gap with reason). |
| DQ ribbon | Beneath the price pane: red = missing/partial, amber = flagged, grey = outside session. Clicking a ribbon cell opens the bar's quality details (flags, source, revision, `available_at`). |
| Live bar | Becomes final only on the `candle.finalized` event. Provisional bars are never used for indicator values or strategy markers. |
| Revisions | If reconciliation revises a live-built bar after the session, the chart shows the revised bar with a "revised" badge; recorded decisions are never redrawn. |

## 3. Navigation and lazy loading
- Instrument and timeframe selectors (instruments from `/instruments`, timeframes `1m…1d`). Changing timeframe keeps the centre timestamp.
- **Lazy loading:** page size 5 000 bars; fetch the visible range plus one page margin; prefetch older pages on scroll; evict distant pages above `chart.max_bars_in_memory` (50 000). The browser never holds the full 450k-bar history.
- **Jump to date/time** (session-aware picker; non-session dates are disabled with the calendar reason) and a **Live** button that follows the right edge.
- Budgets (measured, recorded in T1.7): first paint < 1 s; scroll fetch p95 < 300 ms; pan/zoom ≥ 30 fps on the dev machine.
- Smooth navigation across the full supported dataset (2022-01-03 → today) is acceptance-tested with a scripted scroll from the end to the start.

## 4. Indicators
- Add from the feature catalogue (`/features/catalogue`): name, parameters with defaults/ranges, outputs. Overlay vs pane placement, units, scale guides and default style come from the feature's `display` metadata (LLD §5.1.9), so the UI knows nothing about formulas.
- Every series shows `name@version(params)`; a **ƒ** button opens the mathematical explanation (`/features/{name}/explain`): formula, parameters, input series, outputs, warm-up.
- **Warm-up:** the not-ready region is shaded and values are absent (never zero). Reason codes (`NOT_READY`, `GAP_IN_WINDOW`) appear on hover.
- Hide/show is visual only. Indicators added by hand belong to group `manual`; those from a deployment belong to that deployment's group (PAPER_TRADING_UI.md §7). The chart never silently substitutes a different formula or version for a deployed strategy's feature.

## 5. Markers, levels and inspection (shared by backtests and deployments)
| Glyph | Event | Persisted source |
|---|---|---|
| small hollow arrow | **Signal** (strategy decision) | `decisions` / backtest decisions artifact |
| small dot | **Order accepted** | `order_events` (ACK) |
| filled arrow (up = BUY to open, circle = exit) | **Fill** | `fills` |
- **Price space.** A marker's vertical position is the **underlying reference level** (`underlying_ref`), because option fills are premiums and cannot sit on the index axis. The tooltip says "anchored at NIFTY <level>; fill ₹<premium>". Levels with `price_space = PREMIUM` are not drawn on this axis; they appear in the inspector and the option mini-pane. `UNDERLYING` levels are drawn from entry to exit.
- **Snapping.** A marker is placed on the displayed bar containing the event time (`bar_start ≤ t < bar_end` of the *displayed* timeframe). Signal, order and fill may therefore land on different bars, or the same bar; same-bar markers stack and the tooltip lists all.
- **Click** opens the marker inspector (PAPER_TRADING_UI.md §6; BACKTESTING_REPORT_SPEC.md §6).
- Markers and levels are grouped (`groupId` = deployment id or run id); clearing a group never affects another.

## 6. Chart replay
### 6.1 Three different things (never confused, always labelled by a banner)
| Kind | What it replays | Banner | Strategy events? |
|---|---|---|---|
| **CHART** | Historical candles (and indicators computed causally) for visual study | `CHART REPLAY — historical market data only` | none |
| **EVENT** | Persisted decisions, orders and fills of a **recorded** paper deployment, against the candles | `EVENT REPLAY — recorded deployment <name>` | only what was persisted; a window with no recorded deployment says "no recorded strategy events in this window" and shows none |
| **BACKTEST** | The trades of a stored backtest run, revealed in time order | `BACKTEST REPLAY — run <id>, <result_kind>` | the run's trades; never described as paper trading |
A historical paper deployment is never implied to have existed unless its events were recorded. Running a strategy over history is a backtest, not a replay.

### 6.2 Controls
| Control | Behaviour |
|---|---|
| Start point | Date + time within a session, snapped to a 1m boundary; invalid slots disabled with a reason |
| Play / Pause | Replay clock advances in **market minutes per wall-clock second** (speeds 1, 2, 5, 10, 30, 60); never faster than the server can deliver |
| Step | `+1 bar` / `−1 bar` of the displayed timeframe, and `+1 min` / `−1 min` |
| Seek | Click on the timeline or enter a timestamp; seeking backwards re-evaluates from the start point (deterministic) |
| Readout | Always shows the exact replay timestamp in IST, e.g. `REPLAY 2026-03-12 10:14 IST — bar 10:10–10:15 forming` |
| Keyboard | Space play/pause, `→`/`←` step, `Shift+→/←` ±1 min, `[`/`]` speed |
States: `IDLE → READY → PLAYING ⇄ PAUSED → END_OF_DATA`, plus `ERROR`. Reaching the end of available data stops playback and says so.

### 6.3 No-leak rules (enforced on the server; the UI cannot weaken them)
1. Every replay endpoint is clamped to the replay clock `now`; a request beyond it returns `REPLAY_FUTURE_ACCESS`. The browser is never *sent* a future bar, indicator value, marker or label, so there is nothing to hide.
2. Bars use `available_at ≤ now`. For a chart timeframe above 1m, the **forming** bar is built only from 1m bars up to `now`, drawn as provisional, and carries no indicator values.
3. Indicators are produced by the same feature engine as strategies, fed incrementally with bars `≤ now`; values at `now` equal truncate-and-recompute (T-RP-3). Warm-up and reason codes behave as in live use.
4. **Autoscale** considers only revealed data; the right-hand area beyond the cursor is empty. No "fit content" over the full range.
5. Lazy-loaded older pages are also clamped; the visible-range prefetch never reads past `now`.
6. Labels and tooltips (P&L of a trade, exit reason, "stopped out") appear only at or after the event time that determines them. In EVENT/BACKTEST replay a trade's marker appears at its entry fill; its exit marker and P&L appear when the exit fill time is reached.
7. Gaps replay as gaps: the clock passes through the empty slot; nothing is skipped silently.

### 6.4 Determinism
Same data version, same configuration and same start ⇒ identical frame sequence. The replay session records `{data_version, calendar_version, feature_versions, start_at, kind}`; frame hashes are compared in T-RP-6. Replay speed changes pacing only, never content.

### 6.5 Strategy visibility during replay
Historical strategy signals and trade events can be inspected only when persisted records exist (EVENT or BACKTEST kind). CHART replay shows none and offers no "what would the strategy have done" button; that question is answered by a backtest.

## 7. Strategy overlays on the chart
Per-deployment show/hide of markers, indicators and levels, and the marker inspector, are specified in PAPER_TRADING_UI.md §5–§8. They are visualization controls only.

## 8. States and messages
| Situation | Display |
|---|---|
| Live feed stale/down | Banner "LIVE FEED STALE since 10:41:07 IST"; last bar stays provisional-styled; no auto-finalization |
| Data gap | Whitespace + ribbon + tooltip with reason |
| Page load failure | Inline retry on the affected range; already loaded bars stay |
| Calendar unverified | Ribbon note `CALENDAR_UNVERIFIED` |
| Pinned feature version unavailable | Series absent, legend entry "version unavailable" (no substitute) |

## 9. Accessibility and ergonomics
Colour-blind-safe marker palette plus shape and letter, never colour alone; all controls keyboard reachable; tooltips readable at 100% zoom; mode banner persistent (backtest blue, paper amber, live red when it exists).

## 10. Acceptance (all **PENDING**)
| ID | Check |
|---|---|
| T-CH-1 | IST labels correct at tick marks and crosshair; raw UTC preserved; DST-free round trip |
| T-CH-2 | A removed 1m bar renders as a gap with the right reason; a holiday does not |
| T-CH-3 | Provisional bar styled distinctly and never feeds an indicator |
| T-CH-4 | Marker snaps to the right displayed bar for 1m/5m/1h views; stacking works |
| T-CH-5 | Memory stays under the cap during a full-history scripted scroll |
| T-CH-6 | Clearing one marker/level/series group leaves others untouched |
| T-RP-1…8 | LLD §15.1 row 1 (future bars/values never leak; determinism; step back ≡ seek; EVENT replay honesty) |
