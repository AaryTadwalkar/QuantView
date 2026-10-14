# QuantView — Live Option-Chain Workspace Specification

| Field | Value |
|---|---|
| Document | `docs/OPTIONS_CHAIN_UI.md` |
| Status | v1.2 — **DESIGNED** (not implemented/tested/verified; LLD Appendix C) |
| Authority | UI behaviour and feed semantics. Payload contract: LLD §12.2.1 (`LiveChain`, `Cell`); subscriptions: LLD §4.10.1; states: LLD §2.7.7. LLD wins on conflict. |
| Tickets | T2.4 (service + screens), T0.9 (recorder), T7.9 (ticket shortcut) |

## 1. Routes and the live-only rule
| Route | Content | Rule |
|---|---|---|
| `/options` | **Live** chain during market hours; market-closed state otherwise | Never renders a historical snapshot. A historical payload cannot carry `context: "LIVE"` and the shared table component takes `mode="LIVE" \| "HISTORICAL"`; only `LIVE` can render a LIVE chip (type-level and test-enforced). |
| `/research/options` | Historical snapshot picker (date/time), same table, option features | Persistent banner `HISTORICAL SNAPSHOT — NOT LIVE`, shows snapshot `observed_at` and schema version |

## 2. Feed architecture — what "live" actually means here
A REST snapshot every ≈ 30 s is **not** a continuously updating broker chain, so the screen is a **hybrid** and says so per value.
| Source | Instruments | Cadence | Supplies |
|---|---|---|---|
| **WebSocket `full`** (one connection, recorder-owned) | Index (`ltpc`); options of the nearest weekly expiry at ATM ± `N=10` strikes, CE and PE (≤ 42 keys); near-month future (1); pinned keys of open positions of every paper account | per message (≈ 1/s per instrument, measured in G0.8) | LTP, bid/ask and 5-level depth, volume (cumulative), OI, Greeks/IV where delivered, `source_ts` |
| **REST option-chain snapshot** (collector) | Whole chain, nearest **and next** expiry | ≈ 30 s, ~5 s availability lag | LTP (schemas that have it), bid/ask and top quantities, volume, OI, change in OI, IV, Greeks (v3/api_v4), spot |
- **Subscription limits.** Connections: 2 for non-Plus users; per-connection instrument cap `[VERIFY S10]`. If the total would exceed the cap, `N` shrinks first; the index, the future and pinned keys are never dropped. Strikes outside the WebSocket band are REST-only.
- **Re-centring** when spot moves ≥ 2 strike steps from the centre: new keys subscribed, stale unpinned keys released. During re-centring the new strikes show REST values flagged `DELAYED` until their first WebSocket message.
- **Promised:** per-value provenance and honest freshness; WebSocket-grade updates for the subscribed band while the feed is healthy. **Not promised:** full-chain real-time coverage, depth outside the band, or any quote history from before recording began.

### 2.1 Field → source table (per cell)
| Field | In WS band | Outside WS band | Notes |
|---|---|---|---|
| LTP | `WS_FULL` | `REST_SNAPSHOT` (null for schema v2 — `SCHEMA_NOT_COLLECTED`) | display only; never an executable price |
| Bid / Ask | `WS_FULL` | `REST_SNAPSHOT` | executable references for the manual ticket |
| Bid/Ask quantity | `WS_FULL` (top of 5 levels) | `REST_SNAPSHOT` (v3/api_v4) | |
| Depth ladder | `WS_FULL` | not available | drawer only |
| Volume | `WS_FULL` cumulative | `REST_SNAPSHOT` | cumulative; never summed |
| OI / change in OI | `REST_SNAPSHOT` (WS OI where present, flagged) | `REST_SNAPSHOT` | updates ≈ every 30 s |
| IV, Greeks | `WS_FULL` where delivered, else `REST_SNAPSHOT` | `REST_SNAPSHOT` | `greeks_status ∈ OK, MISSING_ZERO_SENTINEL, INVALID, NOT_COLLECTED`; IV unit normalised `[VERIFY S8]` |
| Spot | WS index `ltpc` | — | header |
Exact field availability per message type is confirmed by T0.7 fixtures before the table is frozen.

## 3. Layout
```
┌ NIFTY   Spot 24,512.35 (WS, 0.4 s)   ATM 24,500   Expiry [ 14 Oct ▾ | next ]   DTE 3.1 ┐
│ ● LIVE    last update 11:02:07 IST   quote age 0.6 s   feed OK                          │
├──────────────────────── CALLS ───────────┬──────┬────────── PUTS ───────────────────────┤
│ OI  ΔOI  Vol  IV  Δ  Bid×Qty  Ask×Qty  LTP│Strike│LTP  Bid×Qty  Ask×Qty  Δ  IV  Vol  ΔOI  OI │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```
- CE on the left, strike in the centre, PE on the right; ATM row highlighted; ITM shading per side.
- Band selector: ±5, ±10 (default), ±15, **All (REST-only beyond ±10)**. Expiry tabs: nearest, next. Column chooser (persisted per user).
- Row order is fixed by strike (no re-sorting jitter); the view is ATM-centred on load and when "Re-centre" is pressed; user scrolling is never overridden.
- Header always shows: spot with its source/age, ATM, expiry, DTE, feed chip, **last update time (IST)**, **worst quote age in the visible band**.

## 4. Freshness and status (the truth rules)
Computed on the **server** from its own clock (`server_now` in every message); the browser only ticks a display counter from that offset and never decides freshness alone.
| Chip | Condition | Behaviour |
|---|---|---|
| `● LIVE` | market `OPEN`, feed `OK`, index tick age ≤ 10 s | normal |
| `◐ DELAYED` | market open and feed OK but the visible values are REST-only (age ≤ `stale_snapshot_s` 75 s) | per-cell `DELAYED` style |
| `○ STALE` | feed `STALE`, or visible WS values older than `stale_quote_s` 5 s, or REST older than 75 s | cells dimmed with a clock icon; ticket disabled; banner states since when |
| `✕ FEED DOWN` | socket closed / stale > 60 s | values frozen and labelled with their age; nothing animates |
| `◼ MARKET CLOSED` / `PRE-OPEN` / `HOLIDAY` | calendar | the chain area shows a **market-closed panel**: state, reason (e.g. "Exchange holiday"), and "Last successful update: 2026-10-09 15:29:58 IST" with an optional **read-only "last session close" view** clearly titled *Not live*. Historical research lives only at `/research/options`. |
Cell rules: a missing or unusable field shows `—` with a tooltip carrying the reason code (`SCHEMA_NOT_COLLECTED`, `QUOTE_ONE_SIDED`, `MISSING_ZERO_SENTINEL`, …); a stale field is dimmed, never hidden and never replaced by an older value; crossed/one-sided quotes show the bid and ask but the ticket treats them as non-executable. A displayed "freshness" claim must equal the data source's real age (T-LC-2).

## 5. Update semantics
- Pushes are **conflated latest-wins** every 500 ms (`live_chain.push_conflate_ms`); the client never queues; on reconnect it shows `STALE` immediately, re-fetches `GET /live/option-chain`, then resumes pushes.
- Changed cells flash briefly (respecting reduced-motion); a cell whose `as_of` did not change does not flash.
- Re-centring and expiry changes re-request the full payload; partial updates are keyed by `(strike, side, field)`.

## 6. Interactions
- Click a bid or ask → opens the **manual order ticket** prefilled with contract and side (PAPER_TRADING_UI.md §3). Disabled with an explanation when STALE/DOWN/CLOSED or when the quote is non-executable. The manual ticket also works without the chain (contract pickers), so the order of delivery does not block manual trading.
- Click a row → contract drawer: 5-level depth (WS contracts only), last 5 minutes of 1-second quote bars from the recorder, Greeks status, whether the contract is pinned by an open position.
- Subscription management is in Settings (read-only pinned union here).

## 7. Operations hooks
The chip links to `/operations` feed detail. A stream `DEGRADED` state (LLD §2.7.4) also shows `STALE` here because new entries are blocked.

## 8. Research context
`/research/options`: date/time picker limited to sessions with snapshots; shows `observed_at`, `available_at`, schema version (v1/v2/v3/api_v4) and per-field reason codes; option features panel; never auto-refreshes; no ticket shortcut.

## 9. Acceptance (all **PENDING**; gate G2.1)
| ID | Check |
|---|---|
| T-LC-1 | Historical payload can never render a LIVE chip (type test + runtime) |
| T-LC-2 | Cell `age_s`/`freshness` equal the source's real age within 1 s; server clock authority (browser clock skewed ±5 min changes nothing) |
| T-LC-3 | Feed stop ⇒ `STALE` within `stale_quote_s`, `FEED DOWN` after 60 s; no value is replaced or "refreshed" by older data |
| T-LC-4 | Market closed/holiday ⇒ market-closed panel with last successful update; no live chip; no historical snapshot in `/options` |
| T-LC-5 | Per-cell `source` correct inside/outside the WS band; re-centre keeps pinned keys and marks new strikes `DELAYED` until first WS message |
| T-LC-6 | Missing/zero-sentinel/one-sided fields render `—` with reason, never 0 |
| T-LC-7 | Conflation: a 50 msg/s burst yields ≤ 2 renders/s per cell and the final state is correct |
| T-LC-8 | Ticket shortcut disabled in STALE/DOWN/CLOSED and for non-executable quotes |
| (VERIFIED) | A recorded live session reviewed by the owner against the broker's own chain screen |
