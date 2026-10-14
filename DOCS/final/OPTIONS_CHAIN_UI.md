# QuantView — Live and Research Option-Chain Workspace Specification

**Document ID:** `QV-SPEC-CHAIN-001`  
**Version:** `v1.4 (Hardened Implementation Baseline)`  
**Release Date:** `2026-10-12`  
**Document Tier:** **Tier 4 · Specialized Contract** (`ADR-007`)  
**Status:** `DESIGNED` — authoritative subordinate specification for `/options` (Live Option Chain, Phase 7 `G7.7`) and `/research/chain` (Historical Snapshot Viewer, Phase 2 `T2.3`).  
**Parent Documents:** [`ADR_REGISTER.md`](ADR_REGISTER.md) (Tier 1), [`HIGH_LEVEL_DESIGN.md`](HIGH_LEVEL_DESIGN.md) (Tier 2 — `§2`, `§4.1`, `§9`, `§15`, `§16`), [`LOW_LEVEL_DESIGN.md`](LOW_LEVEL_DESIGN.md) (Tier 3 — `§4.10.1`, `§4.15`, `§12.2`, `§12.3`, `§13.3`, `§13.6`).  
**Governing Principles & ADRs:** `P2` (No invented option prices), `P6` (Missing is not zero), `P7` (Explicit time semantics), `P14` (Durable before visible), `P16` (Every number is inspectable), `P17` (Visualization never controls), `ADR-022` (Pin open-position contracts in WS `full` mode + 5-level depth), `ADR-030` (`/options` live-only chain vs `/research/chain` historical), `ADR-036` (Observation states, coverage matrix, & eligibility gate), `ADR-041` (Canonical `UtcEpochSec` timestamp contract & isolated IST display formatting).  
**Subordination Rule:** This Tier 4 specification refines UI layout, independent per-field-group provenance and freshness states, on-demand WebSocket subscription flows, and manual order ticket handoff for the option-chain workspaces. It may refine `LOW_LEVEL_DESIGN.md` (`Tier 3`) but must never contradict `ADR_REGISTER.md` (`Tier 1`), `HIGH_LEVEL_DESIGN.md` (`Tier 2`), or `LOW_LEVEL_DESIGN.md` (`Tier 3`).

---

## 1. Two Strictly Separated Option-Chain Workspaces (`ADR-030`, `LLD §4.15, §13.6`)

QuantView provides two separate routes so a historical snapshot can never be mistaken for a live tradable quote (`P2`, `P3`, `P7`):

| Property | Live Option-Chain Workspace (`/options`) | Historical Research Chain (`/research/chain`) |
|---|---|---|
| **Target Phase & Gate** | Phase 7 (`T7.14–T7.15`, Gate `G7.7`). Backend `T7.14` may be pulled forward once Phase 1 `T1.4` and Phase 2 `T2.1` gates pass. | Phase 2 (`T2.3`). |
| **Primary Purpose** | Real-time market monitoring and one-click manual paper order ticket launch during live NSE sessions. | Historical inspection of archived 30-second option-chain snapshots, Greeks quality flags, and option-chain features (`pcr_oi`, `iv_atm`, `iv_skew_25d`). |
| **API Endpoint** | `GET /api/v1/live/option-chain` + WebSocket `{"type": "live_chain", "expiry": "..."}` | `GET /api/v1/option-chain/snapshots`, `GET /api/v1/option-chain/snapshot?at=...`, `GET /api/v1/option-chain/features?at=...` |
| **Time Picker (`at` / `as_of`)** | **Forbidden.** Passing `at` or `as_of` to `/api/v1/live/option-chain` returns `422 VALIDATION_ERROR` (`T-CHN-1`). | **Mandatory.** User picks session date, snapshot timestamp (`at`), and expiry. |
| **Persistent Header Banner** | `LIVE MARKET DATA — PAPER TRADING WORKSPACE` (or `MARKET CLOSED — LAST SESSION VALUES` when `is_live = false`) | `HISTORICAL SNAPSHOT — RESEARCH ONLY (NOT LIVE)` |
| **Quick-Trade Action** | Clicking Bid/Ask opens the Manual Paper Order Ticket (`/paper` drawer) prefilled with that contract (`MARKET` order in v1). Submission always re-validates quote freshness server-side (`T-CHN-11`). | Disabled (no order ticket exists on `/research/chain`). |

---

## 2. Live Option-Chain Data Contract & Independent Field-Group Provenance (`LLD §4.15`, `P2`, `P6`, `P7`, `P16`)

### 2.1 `LiveChainView` and `LiveChainRow` Schema
`GET /api/v1/live/option-chain?expiry=YYYY-MM-DD&band=15` returns:

```json
{
  "underlying_id": "IDX:NIFTY50",
  "expiry": "2026-10-15",
  "server_time": "2026-10-12T04:15:12.410Z",
  "server_time_epoch_s": 1791778512,
  "is_live": true,
  "feed_state": "LIVE",
  "spot": {
    "ltp": 22418.35,
    "change_pct": 0.42,
    "as_of": "2026-10-12T04:15:12.180Z",
    "age_ms": 230,
    "state": "LIVE"
  },
  "atm_strike": 22400.0,
  "strike_step": 50.0,
  "subscription_budget": {
    "ws_band_strikes": 10,
    "active_full_keys": 45,
    "max_full_keys": 100,
    "on_demand_active": 2,
    "on_demand_max": 6,
    "on_demand_ttl_s": 300
  },
  "summary": {
    "median_quote_age_ms": 340,
    "oldest_quote_age_ms": 4120,
    "greeks_valid_count": 42,
    "greeks_invalid_count": 2
  },
  "rows": [
    {
      "strike": 22400.0,
      "is_atm": true,
      "in_ws_band": true,
      "ce": { "instrument_id": "OPTIDX:NIFTY50:2026-10-15:CE:22400", "...": "LegQuote" },
      "pe": { "instrument_id": "OPTIDX:NIFTY50:2026-10-15:PE:22400", "...": "LegQuote" }
    }
  ]
}
```

### 2.2 Independent Field-Group Provenance on Every `LegQuote` (`T-CHN-3`, `P2`, `P6`, `P16`)
In live market feeds, Last Traded Price (`LTP`), Best Bid/Ask (`BBO`), Volume/Open Interest (`Vol/OI`), and Option Greeks (`IV/Delta/Gamma/Theta/Vega`) do not always update on the same tick or from the same transport. A strike may have a sub-second `WS_FULL` BBO update while its last trade (`ltp`) occurred 40 seconds ago, or its Greeks came from a 30-second REST snapshot.

To prevent a fresh BBO timestamp from falsely making stale Greeks or stale LTP appear current, each `LegQuote` (`ce` or `pe`) carries **four independent field-group provenance envelopes** alongside top-level convenience aliases:

| Field Group | Value Fields | Provenance & Freshness Fields (`UTC` ISO-8601 + `age_ms` relative to `server_time`) | Allowed Source & State Values |
|---|---|---|---|
| **1. Best Bid / Ask (`bbo` — authoritative for trading)** | `bid`, `bid_qty`, `ask`, `ask_qty`, `spread_px`, `spread_rel` | `bbo_source`, `bbo_as_of`, `bbo_age_ms`, `bbo_state` *(aliased at top level as `quote_source`, `quote_as_of`, `quote_age_ms`, `quote_state`)* | `bbo_source ∈ {"WS_FULL", "REST_SNAPSHOT", "NONE"}`<br>`bbo_state ∈ {"LIVE", "SNAPSHOT", "STALE", "HIDDEN_STALE", "MISSING", "INVALID"}` |
| **2. Last Traded Price (`ltp`)** | `ltp`, `ltp_change_pct` | `ltp_source`, `ltp_as_of`, `ltp_age_ms`, `ltp_state` | `ltp_source ∈ {"WS_FULL", "REST_SNAPSHOT", "NONE"}`<br>`ltp_state ∈ {"LIVE", "SNAPSHOT", "STALE", "HIDDEN_STALE", "MISSING"}` |
| **3. Volume & Open Interest (`vol_oi`)** | `volume`, `oi`, `oi_change` | `vol_oi_source`, `vol_oi_as_of`, `vol_oi_age_ms`, `vol_oi_state` | `vol_oi_source ∈ {"WS_FULL", "REST_SNAPSHOT", "NONE"}`<br>`vol_oi_state ∈ {"LIVE", "SNAPSHOT", "STALE", "NOT_COLLECTED", "MISSING"}` |
| **4. IV & Option Greeks (`greeks`)** | `iv`, `delta`, `gamma`, `theta`, `vega` | `greeks_source`, `greeks_as_of`, `greeks_age_ms`, `greeks_state`, `quality_flags[]` (`OQ-01…OQ-18`) | `greeks_source ∈ {"WS_FULL", "REST_SNAPSHOT", "COMPUTED_BS76", "NONE"}`<br>`greeks_state ∈ {"LIVE", "SNAPSHOT", "STALE", "NOT_COLLECTED", "INVALID"}` |

**Contract & Risk Metadata per `LegQuote`:**
- `instrument_id`, `lot_size`, `freeze_qty`, `is_pinned_open_position` (`ADR-022`: true when held by any open paper/live position, ensuring `WS_FULL` subscription regardless of distance from ATM), and `is_expired` (`true` once the contract's session close on expiry date has passed).

### 2.3 Cell State Machine, Thresholds, and Zero-Sentinel Honesty (`LLD §4.15, §16.1`, `P6`)
Every cell in a row renders according to its own field-group state (`bbo_state`, `ltp_state`, `vol_oi_state`, `greeks_state`):

| Cell State | Condition | Visual Rendering & Interaction Rule |
|---|---|---|
| `LIVE` | `source == "WS_FULL"` and `age_ms <= 5000` (`live_quote_stale_s = 5`) | High-contrast primary typography; 180ms green/red background flash on tick update. Hover tooltip shows exact `as_of` in IST (`HH:MM:SS.mmm IST`) and `age_ms`. |
| `SNAPSHOT` | `source == "REST_SNAPSHOT"` (or `"COMPUTED_BS76"`) and `age_ms <= 75000` (`max_snapshot_age_s = 75`) | Standard value with compact `"30s"` (or `"BS76"`) badge indicating non-WS provenance. Clicking Bid/Ask on a `SNAPSHOT` cell triggers on-demand `WS_FULL` promotion before order submission is enabled (`§4`). |
| `STALE` | `age_ms > 5000` (for `WS_FULL`) or `> 75000` (for `REST_SNAPSHOT`) and `<= 120000` (`live_quote_hide_s = 120`) | Amber text with inline age chip (`"18s old"`). Clicking Bid/Ask opens the ticket in warning state; `RK-04` (`max_live_quote_age_s = 5s`) blocks submission until a fresh tick arrives. |
| `HIDDEN_STALE` / `MISSING` | `age_ms > 120000` (`live_quote_hide_s = 120`) or `source == "NONE"` (no quote ever received) | **Never renders `0` or stale numeric prices (`P2`, `P6`).** Numeric value is replaced by `"—"` with tooltip: `"Quote older than 120s (last seen HH:MM:SS IST) — hidden for safety"` or `"No quote received"` (`T-CHN-4`). |
| `NOT_COLLECTED` | Field not provided by feed (e.g., Greeks when `greeks_in_full_mode == false` and no REST snapshot/BS76 fallback) | **Never renders `0` (`P6`).** Renders `"n/a"` with tooltip `"Not collected in current feed mode"`. |
| `INVALID` | Failed `OQ-01…OQ-18` (e.g., `bid > ask` `OQ-03`, `iv <= 0` `OQ-11`, or all-zero sentinel Greeks `delta=gamma=theta=vega=0` `OQ-13`) | **Never renders raw `0.00` sentinel Greeks as valid (`P6`).** Renders struck-through grey value (or `"— [INVALID]"` for zero-sentinel Greeks) with red warning dot and tooltip listing the exact failing `OQ-*` rule (`T-CHN-6`). |

---

## 3. Layout, Status Header, and WebSocket Diff Protocol (`LLD §12.3, §13.6`, `ADR-041`)

### 3.1 Top Status Bar
Always pinned at the top of `/options`:
1. **Feed State Pill:** `LIVE` (green), `STALE` (amber), `RECONNECTING` (amber pulsing), `DOWN` (red — all trade actions disabled), or `MARKET CLOSED` (slate grey).
2. **Underlying Spot Ticker:** `NIFTY 50` LTP, net change, `%` change, and exact IST display timestamp (`HH:MM:SS.mmm IST`, formatted from canonical UTC via `ADR-041`).
3. **Expiry Selector:** Dropdown populated from `GET /api/v1/live/option-chain/expiries` (`NEAREST` weekly default, `NEXT` weekly, monthly), showing days-to-expiry (`DTE`), an amber `"EXPIRY DAY — RK-23 CUTOFF ACTIVE"` badge when `DTE == 0`, and `"EXPIRED — READ ONLY"` if `is_expired == true`.
4. **Strike Band Selector:** `±10 Strikes (WS Live Band)` (default), `±15 Strikes`, `±25 Strikes`, or `All Strikes`. Strikes outside the `±10` WebSocket `full` band display a `"SNAPSHOT ONLY"` chip unless promoted via an on-demand subscription or pinned by an open position (`is_pinned_open_position == true`, `ADR-022`).
5. **Subscription Budget Meter:** Shows `WS Full: 45/100 | Pinned Positions: 2 | On-Demand: 2/6 (TTL 300s)`.

### 3.2 Broker-Style Split Table
- **Left Side (CALLS / CE):** `OI`, `Chg OI`, `Vol`, `IV`, `Delta`, `Bid Qty`, `Bid`, `Ask`, `Ask Qty`, `LTP` (with optional toggleable columns `Gamma`, `Theta`, `Vega`, `Spread %`).
- **Center Spine:** `Strike` (bold, ATM row highlighted with a horizontal accent bar and `"ATM"` pill; ITM call background tinted subtle warm/indigo; rows with open paper positions badged with `"OPEN POS"` pill).
- **Right Side (PUTS / PE):** Mirror order (`LTP`, `Bid Qty`, `Bid`, `Ask`, `Ask Qty`, `Delta`, `IV`, `Vol`, `Chg OI`, `OI`).

### 3.3 WebSocket `live_chain` Diff Stream, Disconnect Handling, and Gap Resync (`T-CHN-8`)
- Subscribing to `{"type": "live_chain", "expiry": "YYYY-MM-DD"}` delivers incremental cell-diff messages throttled to `live_chain_push_ms = 1000` (1 push/second), each carrying a strictly sequential `push_seq`, canonical `server_time` (UTC), and per-field-group updated fields (`bbo`, `ltp`, `vol_oi`, `greeks`).
- **Sequence Gap Resync:** If the client detects a gap in `push_seq` (`msg.push_seq != last_push_seq + 1`), it immediately discards its in-memory diff state, sets the status pill to `RECONNECTING`, and re-fetches the full snapshot via `GET /api/v1/live/option-chain` before applying new diffs (`T-CHN-8`).
- **WebSocket Disconnect Degradation:** If the WebSocket connection drops or misses heartbeats for `> 5s`, the top status bar transitions immediately to `RECONNECTING` / `DOWN`, all cell ages continue incrementing against the local monotonic timer so cells naturally transition to `STALE` (`> 5s`) and `HIDDEN_STALE` (`> 120s`), and order-ticket submission is blocked (`T-CHN-11`).

---

## 4. On-Demand WebSocket Subscriptions, Quick-Trade Handoff, and Server-Side Submit Re-Validation (`LLD §4.10.1, §8.6.9, §13.6, §13.7`, `P17`)

1. **In-Band Click (`in_ws_band == true` or `is_pinned_open_position == true`):** Clicking `Bid` (to Sell/Exit an existing long position) or `Ask` (to Buy) on any contract inside the `±10` strike band opens the **Manual Paper Order Ticket Drawer** (`/paper` manual ticket component, [`PAPER_TRADING_UI.md`](PAPER_TRADING_UI.md) `§2`) prefilled with:
   - Active `PAPER_MANUAL` account (last selected active manual account)
   - `instrument_id`, `side` (`BUY` on Ask click; `SELL` on Bid click only if closing an existing long position on that account, since naked shorting is blocked in v1 by `RK-01`)
   - `order_type = "MARKET"` (v1 manual paper orders are `MARKET`-only; `ADR-028`, `ADR-039`)
   - `lots = 1` (`qty = lot_size`)
2. **Out-of-Band Click (`in_ws_band == false` and `is_pinned_open_position == false`):**
   - Because `OPT_LIVE_BIDASK` requires a fresh live WebSocket quote (`bbo_source == "WS_FULL"`, `bbo_age_ms <= max_live_quote_age_s * 1000` under `RK-04`), clicking an out-of-band strike automatically fires `POST /api/v1/live/subscriptions/on-demand` with `{"instrument_id": "..."}`.
   - Up to `on_demand_max = 6` contracts can be promoted to WebSocket `full` mode concurrently with a sliding `on_demand_ttl_s = 300` (5 minutes).
   - While awaiting the first WebSocket tick, the order ticket shows `NO_LIVE_QUOTE — Subscribing to live quote stream…` and keeps the **Submit Market Order** button disabled. As soon as the first `WS_FULL` BBO tick arrives (`< 1–2s` during market hours), the row upgrades to `LIVE` and the ticket enables submission (`T-CHN-9`).
3. **Mandatory Server-Side Quote Freshness Re-Validation on Order Submit (`T-CHN-11`, `P14`, `P17`):**
   - The UI's cell state (`LIVE` vs `STALE`) and pre-trade preview (`/api/v1/manual/orders/preview`) are **advisory display aids only** (`P17`).
   - When the operator clicks **Submit Market Order** (`POST /api/v1/manual/orders`) and `paper_runner` consumes the `order_request`, `paper_runner` independently re-validates against its authoritative in-memory market state at the exact execution instant:
     1. `bbo_source == "WS_FULL"` (never fills a live/paper market order off a 30-second `REST_SNAPSHOT` quote);
     2. `bbo_age_ms <= max_live_quote_age_s * 1000` (default `5,000 ms`, `HARD` rule `RK-04`);
     3. `bid > 0 AND ask >= bid` (`OQ-03`, `HARD` rule `RK-22`) and `(ask - bid) / mid <= max_spread_rel` (`CEILING`/`ADVISORY` rule `RK-05`);
     4. The contract is not expired (`is_expired == false`) and, for `BUY` entries on expiry day, current session time is before `session_close - expiry_entry_cutoff_minutes_before_close` (`HARD` rule `RK-23`).
   - If a quote was `LIVE` when the operator opened the drawer from `/options` but became `STALE`, crossed, or disconnected while the drawer was open, `paper_runner` rejects the order with `status = 'REJECTED'`, `reject_code = 'RK-04_STALE_QUOTE'` (or `'RK-23_EXPIRY_CUTOFF'`), and the UI displays the server rejection toast with the exact quote age at rejection time (`T-CHN-11`, `T-CHN-12`).

---

## 5. Verification Test Mapping

| Test ID | Description |
|---|---|
| `T-CHN-1` | `GET /api/v1/live/option-chain?at=...` or `?as_of=...` is rejected with `422 VALIDATION_ERROR` (`ADR-030`) |
| `T-CHN-2` | Outside market hours (`is_live = false`), `/options` renders `"MARKET CLOSED — LAST SESSION VALUES"` and never serves a historical `/research/chain` snapshot as live |
| `T-CHN-3` | Every strike cell exposes independent provenance and timestamps for `bbo` (`bbo_as_of`), `ltp` (`ltp_as_of`), `vol_oi` (`vol_oi_as_of`), and `greeks` (`greeks_as_of`); a fresh `bbo` tick never overwrites `greeks_as_of` or `ltp_as_of` |
| `T-CHN-4` | Quotes with `age_ms > live_quote_hide_s * 1000 (120,000 ms)` transition to `HIDDEN_STALE` and render `"—"` instead of stale numeric prices or `0` (`P2`, `P6`) |
| `T-CHN-5` | Strikes outside `±10` ATM band show `SNAPSHOT` (`30s` badge) until promoted via on-demand subscription or pinned by an open position |
| `T-CHN-6` | Invalid Greeks (`OQ-13` all-zero sentinel `delta=gamma=theta=vega=0` or `OQ-03` `bid > ask`) are flagged `INVALID` and rendered struck-through / `"— [INVALID]"` with failing `OQ-*` rule tooltip (`P6`) |
| `T-CHN-7` | Expiry selector lists active expiries with accurate `DTE` and highlights expiry-day `RK-23` cutoff window |
| `T-CHN-8` | Simulated `push_seq` gap or WebSocket disconnect/reconnect on `live_chain` marks feed `RECONNECTING` and triggers automatic full REST resync via `GET /api/v1/live/option-chain` |
| `T-CHN-9` | Clicking an out-of-band contract calls `POST /api/v1/live/subscriptions/on-demand`, enforces `on_demand_max = 6` and `TTL = 300s`, and enables the manual ticket only after a live `WS_FULL` BBO quote arrives |
| `T-CHN-10` | Held positions (`pin_open_positions = true`, `ADR-022`) remain subscribed in `WS_FULL` even when spot moves `> 10` strikes away |
| `T-CHN-11` | **Server-side submit freshness re-check:** Opening the manual order ticket on a `LIVE` quote from `/options`, waiting until `bbo_age_ms > max_live_quote_age_s * 1000` (or disconnecting the feed), and submitting the order results in deterministic server-side rejection (`RK-04_STALE_QUOTE`) with zero fills |
| `T-CHN-12` | **Expired / cutoff contract protection:** Clicking or submitting a `BUY` order on an expired contract or inside the expiry-day `RK-23` cutoff window is blocked in the UI and rejected server-side (`RK-23_EXPIRY_CUTOFF`) |
| `T-ACC-12` | End-to-end owner acceptance test for live option-chain honesty, independent field-group timestamps, and staleness handling (Phase 7 Gate `G7.7`) |
