# QuantView — Paper Trading UI Specification (manual account, deployments, strategy visualization)

| Field | Value |
|---|---|
| Document | `docs/PAPER_TRADING_UI.md` |
| Status | v1.2 — **DESIGNED** (not implemented/tested/verified; LLD Appendix C) |
| Authority | UI behaviour. Contracts: LLD §8.8.2 (manual), §8.8.3 (deployments), §8.6.8–9 (risk), §4.8.1 (`TradeChain`), §5.1.9 (feature pins), §9.5.1 (viz table), §12.2.1 (APIs). LLD wins on conflict. |
| Tickets | T7.9 (manual), T7.10 (deployments), T7.11 (visualization) |

## 1. Identity and separation
- `/paper` = **strategy** paper accounts. `/paper/manual` = the **manual** paper account. Different routes, different account badges (`STRATEGY ACCOUNT · <name>` / `MANUAL ACCOUNT`), same amber "PAPER — SIMULATED" banner. A manual order can never be entered from a strategy account page and vice versa.
- Order rows show an **origin badge** (`MANUAL` / `STRATEGY · <deployment>`); every table can filter by account and origin.
- All money figures on a page come from that one account's ledger. There is no combined total across accounts.

## 2. Manual account page (`/paper/manual`)
Summary cards (cash, equity, realised, unrealised, charges, day P&L) · positions table (instrument, qty, avg cost, bid mark, unrealised, **Exit** and **Exit all**) · order ticket · orders blotter (status, cancel) · fills · ledger · performance (the same metric panels as backtests with `result_kind = PAPER`, origin `MANUAL`, Sharpe/Sortino only when ≥ 60 trading days). **Reset account** archives it and creates a new one after a typed confirmation; history remains viewable.
Positions are never auto-closed: the page states "Manual positions carry across sessions until you exit them."

## 3. Manual order ticket
| Field | Control | Validation / source |
|---|---|---|
| Contract | Expiry select → strike select → CE/PE toggle (or prefilled from the live chain) | must be listed and quoted within the age limit |
| Action | BUY (opens) / SELL (closes) | SELL ≤ open quantity; no shorting (RK-01) |
| Quantity | Lots (integer ≥ 1); shows units = lots × lot size | ≤ freeze quantity; multiple of lot size |
| Order type | MARKET / LIMIT only | others are not offered (simulator does not implement them) |
| Limit price | numeric, tick 0.05 | required for LIMIT; BUY limit above ask or SELL limit below bid shows "marketable" note |
| Validity | DAY (fixed) | expires at 15:30 |
Live panel: bid × qty, ask × qty, spread, quote age, feed chip (from the live chain feed). **Estimate panel** (from `POST /manual/orders/validate`, debounced, labelled *estimate*): estimated fill price (ask or limit-capped), outlay, estimated charges (cost model), cash after. **Advisory panel**: ceiling warnings from the manual profile (e.g. "outlay 72% of equity — reference 60%") that do **not** block. **Hard failures** (block submit, shown in red): feed stale/down, no valid ask, insufficient cash incl. charges, quantity/tick errors, kill switch on, market closed.
Submit → `202 command_id` → ticket shows `QUEUED → ACCEPTED → OPEN → PARTIALLY FILLED → FILLED / REJECTED / EXPIRED / CANCELLED` driven by outbox events. `client_order_id` is generated per ticket so a double click creates one order. If the runner is down the ticket shows "Paper runner unavailable — nothing was sent" (503). A command not handled within 30 s shows `EXPIRED — nothing was executed`. Cancel is available while `OPEN`/`PARTIALLY FILLED`; a partial fill keeps its filled quantity.
Error text map: `RISK_REJECTED[RK-xx]` and `RISK_UNQUANTIFIABLE` display the rule and the human reason; `ACCOUNT_MODE_MISMATCH`, `ORDER_TYPE_UNSUPPORTED`, `RUNNER_UNAVAILABLE`, `COMMAND_EXPIRED`, `STREAM_DEGRADED` each have fixed wording (no raw codes alone). Exit controls: **Exit** opens the ticket with SELL prefilled (quantity = open, MARKET or LIMIT); **Exit all** asks for confirmation. No "stop-loss" field exists for manual orders in v1.

## 4. Strategy paper: deployments
List columns: name, strategy@version, account, state chip, started, open position, today's net P&L (account), last error. Detail tabs: **Overview** (config snapshot: versions, params, feature pins, risk profile@version, data/engine versions), **Events** (`deployment_events`), **Trades** (`TradeChain` table), **Indicators**, **Orders/Fills**, **Ledger & P&L** (account), **Health**.
Controls offered per state (the UI offers only legal transitions; the API enforces them):
| State | Buttons |
|---|---|
| CREATED | Start |
| STARTING | — (progress; pre-flight results listed) |
| RUNNING | Pause · Stop… |
| PAUSED_USER | Resume · Stop… |
| PAUSED_AUTO | Resume (shows the health-gate reason) · Stop… |
| DRAINING | Flatten now… (explicit) |
| STOPPED | Redeploy (creates a new deployment) |
| ERROR | Acknowledge error · Stop… (banner: "Engine-owned stops are still active; strategy signal exits are not") |
**Stop dialog** has two radio options with consequences spelled out: *Stop new entries and manage the open position until flat* (**default**) and *Stop and liquidate now* (requires ticking "I understand this will exit the position"). Closing a deployment never hides an open position: the Overview shows it until flat.

## 5. Strategy overlays on the chart (visualization controls)
A **Strategy overlays** side panel on `/chart` (and a toggle on each deployment card) lists deployments. Per deployment:
| Control | Meaning |
|---|---|
| Master eye | Show this deployment on the chart at all (default **off**; `viz.default_visible_on_deploy` may change it) |
| Markers | entry/exit markers (signal / order accepted / fill glyphs) |
| Indicators | the strategy's required indicators (§7) |
| Levels | stop/target/trail levels with `UNDERLYING` price space |
| Per-series eyes, colour chip, letter glyph | hide a single series; each deployment keeps a stable colour slot and letter |
| Filters | deployment, strategy version, instrument, date range |
Rules:
- **Visualization, not execution.** The panel carries the text "Visualization only — does not affect trading." Toggles call `PUT /viz/deployments/{id}`, which can write **only** `viz_preferences`; they never pause, stop, restart or modify a deployment, order or account (T-VZ-4).
- Master off ⇒ markers, indicators and levels of that deployment are all hidden; the sub-toggles remember their values. Indicators auto-appear (§7) **only** when master and *Indicators* are on.
- Re-enabling re-reads persisted history from the API (`trade-events`, `indicator-series`); it creates no orders.
- Several deployments can be on at once; markers and series are grouped per deployment, never merged, and each marker's tooltip names the deployment and `strategy@version`.
- Large histories load by visible range; the panel shows counts ("142 events in view").

## 6. Marker inspector (drawer)
Opened by clicking any marker or a Trades-tab row. Shows the **chain** as a timeline — Signal → Order created → Order accepted → Fill(s) → Exit trigger → Exit order → Exit fill — each with IST time (UTC on hover) and a note when events share a bar. Fields (from `TradeChain`):
1. Strategy name, `strategy@version`, spec hash, deployment id, account.
2. Instrument: expiry, strike, CE/PE, lot size.
3. Candle timeframe and signal candle timestamp (`signal_bar_start`); signal timestamp (`decision_at`).
4. Order creation and acceptance timestamps; simulated fill timestamp(s), fill price(s) in ₹, `fill_source`, fill model; quantity (units/lots).
5. Exit reason (`STOP`, `TARGET`, `TRAIL`, `TIME_EXIT`, `FORCE_FLAT`, `SIGNAL_EXIT`, `OPERATOR_FLATTEN`, …).
6. **Indicator values used by the decision** (`feature_snapshot`) with `name@version`.
7. Stop/target/trailing values with basis and price space; for `PREMIUM` basis, planned risk and — once closed — realised loss and overshoot ratio (§LLD 8.6.8).
8. Gross P&L, charges, net P&L **from that account's ledger** (shows "open — unrealised ₹x at bid, live" while open).
9. Links: order, fills, ledger entries, "jump to candle".
Signals, accepted orders and fills are always shown as separate events; a signal without an accepted order (risk-rejected, stale replay) shows its rejection reason and has no fill marker.

## 7. Indicators of a deployed strategy
- On enabling, the chart creates one group per deployment from `GET /paper/deployments/{id}/indicators`: every feature pin (`name@version(params)`, outputs, warm-up) placed by its display metadata (overlay vs pane, units, scale guides, default style). Example: EMA 20 and EMA 50 on the price pane; RSI 14 in its own pane with 30/70 guides.
- Values come from the **persisted deployment series** (what the strategy actually used). A series recomputed because rows are missing carries a `RECOMPUTED` badge; if the pinned version cannot be loaded, the legend shows "version unavailable" and nothing is drawn — the chart never uses a different formula or parameters.
- Timeframe rule: drawn as-is when chart timeframe = strategy timeframe; as a causal step line on a lower timeframe; not drawn (with a legend note) on a higher one.
- Hiding an indicator is visual only; the strategy keeps calculating it.
- Custom indicators use the same feature definitions and version as the strategy engine.

## 8. Reload and restart behaviour
Reloading the browser or restarting the paper runner restores preferences and history from the API: markers are keyed by `fill_id`/`decision_id`, so nothing duplicates and nothing is lost; outbox resync fills any missed live events.

## 9. Acceptance scenarios (all **PENDING**)
| ID | Scenario |
|---|---|
| T-VZ-1 | Deploy a strategy that produces an entry and an exit; each marker corresponds to a persisted decision/order/fill row |
| T-VZ-2 | Marker candle and timestamps match the stored `signal_at`, `accepted_at`, `filled_at` (snapped to the displayed bar) |
| T-VZ-3 | A marker with no persisted fill/decision is a test failure (no reconstruction from indicator crossings) |
| T-VZ-4 | Hide markers while the deployment keeps trading: orders, positions, ledger and P&L unchanged; DB write audit shows only `viz_preferences` |
| T-VZ-5 | Re-enable: historical markers reappear; no new order created |
| T-VZ-6 | Selecting a deployment with EMA 20/50 + RSI 14 shows the three series in the right panes automatically (master and Indicators on) and nothing when master is off |
| T-VZ-7 | Series use the deployment's pinned feature versions/parameters; unavailable pin ⇒ no series |
| T-VZ-8 | Two deployments: markers/indicators distinguishable (colour + letter), independently hideable |
| T-VZ-9 | Filtering by version/instrument/date affects only the view |
| T-VZ-10 | Restart the runner and reload the frontend: no duplicate events, no missing history |
| T-MN-* / T-DP-* | LLD §8.8.2 / §8.8.3 (UI-visible parts: ticket states, stop dialog, control matrix) |
