# QuantView Engine, UI, and Research Contract

**Authority:** This is the binding behavioural specification for strategy timing, execution, risk, accounting, live recovery, UI/API behaviour, metrics, indicators, transforms, and model integration. It is intentionally self-contained.  
**Status vocabulary:** `DESIGNED`, `IMPLEMENTED`, `TESTED`, `VERIFIED`. All rules are `DESIGNED` until implementation evidence exists. `PENDING_OWNER` denotes an owner choice; `VERIFY` denotes external/source semantics that need evidence.  
**Safety:** No real orders in v1. No future data. No silent contract substitution. No fake zero-fill. No hidden assumptions about fees, margin or settlement.

**Status:** DESIGN SPECIFICATION. This consolidated file is self-contained; status claims require project evidence.

## 1. Runtime and repository boundaries

```text
quantview/
  apps/web/                 # React + Vite + TypeScript SPA
  services/api/              # FastAPI; UI commands and query API
  services/collector_snapshot/ # REST snapshots, reserved rate-limit budget
  services/collector_ws/       # sole Upstox WS owner + SubscriptionManager + raw capture
  services/backfill/           # checkpointed, lower-priority historical requests
  services/worker_compute/    # backtests, features and research jobs; N leased workers
  services/worker_data/       # normalization/compaction; one exclusive leased worker
  services/live_daemon/       # persistent replay/paper runtime
  packages/domain/            # typed IDs, contracts, calendar, timestamps
  packages/data/              # schemas, raw adapters, Parquet writers, DuckDB queries
  packages/features/          # registry, built-ins, cache, chain provider
  packages/strategies/        # strategy interface and strategy families
  packages/engine/            # event loop, orders, fills, positions, accounting
  packages/risk/              # policy evaluation and halt controls
  packages/ledger/            # immutable events and projections
  tests/                      # unit, integration, golden, property, truncation tests
  config/                     # non-secret defaults and example configuration
  data/                       # local runtime data; excluded from git
```

Keep a modular monolith, but run `collector_snapshot`, `collector_ws`, `backfill`, API, `worker_compute`, `worker_data` and `live_daemon` as separate processes. `worker_compute` may have N instances and claims jobs through Postgres row leases; `worker_data` has one active instance enforced by an exclusive renewable Postgres lease (lease expiry means stop publishing and relinquish ownership). `collector_ws` alone owns Upstox WebSocket connections and publishes raw-first frames through `FrameBus`; the initial transport is a local socket/async queue with monotonic sequence numbers, and durable raw segments are the replay source. Redis/Valkey remains optional pending a measured need. `live_daemon` never connects directly to Upstox WebSocket. The SubscriptionManager computes the union of subscriptions for active deployments and chart requests within verified limits and exposes the effective set to the UI. UI restart must not stop collectors or live paper deployments. Production-host choice and read-only checksum-verified research sync are defined in `QUANTVIEW_MASTER_SPEC.md` ADR-015; process boundaries and worker leases are ADR-014. For development, keep repo/data inside WSL filesystem, never `/mnt/c`. Use systemd as the single supervisor for Linux services; a systemd boot unit starts the Postgres-only Compose stack. Strategies/features may not access DB, Redis or broker directly; use declared interfaces.

## 2. Time semantics (non-negotiable)

- Store timestamps as UTC-aware instants. Exchange session/calendar logic uses `Asia/Kolkata`.
- `ts_start` is inclusive, `ts_end` exclusive; bar represents `[ts_start, ts_end)`.
- `available_at` is the earliest time the closed observation can legally be consumed; for a completed bar this is `ts_end`.
- Keep `ts_event` (vendor/exchange event time, if supplied), `ts_recv` (local receive time), `available_at` (strategy-visible time) and `ingested_at` (persistence time) separate.
- For snapshots without exchange event time, `received_at` is their availability time. They may be used only if `received_at <= decision_time` and they pass freshness checks.
- Higher-timeframe bars become available only at their end. Example: a 5m bar starting 09:15 is available at 09:20. A developing bar is a separate feature type and must be labelled as such.
- A feature's pivot may be drawn at `pivot_time`, but strategy visibility begins at `confirmed_at`.
- A missing bar is a gap, not a flat bar. Any carry-forward policy must be explicit, marked synthetic and prohibited for fills unless separately justified.

## 3. Strategy and feature interfaces

### 3.1 Strategy contract

A strategy implementation provides:

- `declare()`: required features, timeframes, warm-up, contract selector, exit specification, overnight policy and supported instruments.
- `on_bar(ctx) -> list[OrderIntent]`: receives read-only data available at the decision timestamp.
- Order intents identify the intended position effect and side: `BUY_TO_OPEN`, `SELL_TO_OPEN`, `SELL_TO_CLOSE`, or `BUY_TO_CLOSE`; a strategy may also emit a market `EXIT` intent against a specific position/leg. A market `EXIT` follows the same next-eligible-contract-bar-open fill rule as other queued intents, including tick quantization against the trader; it does not fill on the signal bar. Position stop/target/trailing protection remains engine-owned as specified in §4.
- declared `legs` for a strategy position/group (each leg has option type, long/short side, contract selector, sizing and exit policy); one-leg strategies are the first implementation slice. Multi-leg orders are not presumed atomic: leg-level fill, missing-leg, partial-execution and unwind behavior must be modelled and tested before realistic-account enablement.
- serializable `state` for daemon restart/replay.
- stable strategy ID, `lineage_id`, code hash, parameter schema and declared version.

`ctx` contains the decision time, current closed bars, point-in-time features, selected contract candidates, current positions/account state and quality/freshness metadata. It must not expose future rows or mutable engine internals. Strategy code cannot query DB/broker directly.

### 3.2 Feature registry

Each feature declares `id`, `version`, parameter model (Pydantic), input columns/timeframes, output columns/types, warm-up, calculation function, availability rule, source tier requirements, plot metadata and memory class (`finite(W)` or `infinite`). Registry scanning discovers modules under `features/{category}/`: `oscillators`, `overlays`, `volatility`, `price_action`, `oi`, `option_chain`, `custom`.

Cache is partitioned monthly. Key: feature ID + code hash + canonical parameter hash + partition input hash + upstream state hash (hash of warm-up inputs or prior checkpoint), with instrument/contract, timeframe, session policy and calendar/contract versions in the manifest. Appending a day recomputes only affected partitions and downstream partitions whose upstream-state hash changes. Infinite-memory features checkpoint end-state per month; finite(W) features include warm-up inputs in the partition input hash. Cache artifacts are Parquet with a manifest. Only compute requested dependencies; reuse matching partitions. EMA(45) is a new parameter series and must not invalidate EMA(9/15/20/50).

Live dependency set is the union of visible chart features and strategy-required features. A strategy feature continues to run when hidden from the chart.

### 3.3 Truncation and parity contract

For every time-series feature, calculate outputs using data only through time `t`; the output at `t` must equal the output at `t` when calculated from the full series. Test several cut points, including warm-up boundaries and session boundaries. This catches future leakage/repainting but does not replace semantic tests for every indicator. For incremental/live implementations, compare against batch outputs within documented tolerance.

BOS/CHoCH and pivots must expose `pivot_time` and `confirmed_at`. Future-confirmed pivots may not be fed to strategies before confirmation. Heikin Ashi and Renko are chart transforms only; orders and P&L use canonical tradable option prices.

## 4. Bar-event order — authoritative simulation contract

The **master loop is the exchange calendar-minute grid**, not the union of observed contract bars. At minute `m`, “contract bar `k`” means that minute’s bar for each held or candidate contract. Per-minute work is limited to held contracts plus contracts needed for an active decision/pending order; when flat with no pending orders, skip directly to the next strategy decision time. Strategy decisions may be slower (for example, every completed 5m bar), but risk and held-position exits remain on the 1m grid. Benchmark the idle-skip and held-position paths. For each eligible contract bar `k` with start `s` and end `e`, process events in this exact order:

1. **At open of bar k:** apply the configured slippage/fill policy, then at the fill boundary: (a) validate `abs(price*100 - round(price*100)) < 1e-6` — else flag and reject the fill with stable reason code `PRICE_NOT_QUANTIZABLE`; (b) set `price_paise = int(round(price * 100))`; (c) apply slippage in integer paise; (d) quantize using `tick_paise` from the effective-dated contract master for that trade date (never a hardcoded constant) — buy rounds up to the nearest tick, sell rounds down to the nearest tick — using integer arithmetic only. Parquet candle columns remain `float64` and are not affected by this quantization. A required property test: for every `k` where `k * tick_paise` is representable, `quantize(k * tick_paise / 100) == k * tick_paise`. No float multiplication may feed cash, fees or realized P&L. Fill orders queued before this open at the quantized price. If a stop/target is already crossed at the open, use the open price, not the trigger level. Re-check position-side-specific exposure caps at the actual fill: long entries must satisfy premium/cash limits; short entries must satisfy the selected margin/buying-power and worst-case-risk policy. Reject with a structured reason if a constraint is exceeded. Sizing at decision uses last close plus a configurable safety buffer.
2. **Intrabar:** evaluate active position stop, target and trailing attributes using bar high/low. Positions opened at the open are exposed to the full bar. If stop and target are both touched and finer data cannot resolve order, stop wins by default. Trailing levels are computed from completed bars only, then treated as a stop; they never use a future or unfinished bar.
3. **At close of bar k:** update mark-to-market in the equity series (not as a ledger event); make the bar and features with `available_at <= e` visible; accept snapshot/WS observations only if `received_at <= e` and fresh enough; process required end-of-day exits; call strategy on its own timeframe's newly closed bars; resolve contract at this decision time; apply pre-trade risk; queue accepted order intents for the next eligible contract bar open.
4. **After fills:** record fill/fees and run post-fill risk checks/halts. A risk-halt flatten is a market exit queued for the next eligible bar open, subject to stale/expiry/EOD safety rules.

The `is_flat_bar` predicate is defined once in `QUANTVIEW_DATA_SPEC.md` §4. Missing bars, zero-volume non-flat bars and flat bars with nonzero volume remain distinct data-quality cases; this section defines only their execution consequences.

Additional rules:
- A signal based on a closed bar fills no earlier than the next eligible bar's open.
- An open-based signal cannot fill at that same bar's close and cannot fill at the same opening print that generated the signal. With 1m OHLC, earliest actionable fill is the next bar's open.
- If the selected contract has no eligible next bar, expire the order after the configured `N` eligible bars; never fill using another strike silently.
- Strategy signals fire on the calendar minute grid and their own timeframe, not merely on whichever underlying rows happen to exist. Missing underlying bars are flagged; policy is skip or explicit flagged carry-forward, never implicit fill.
- Stops and risk checks run on the 1m clock or finest available source regardless of strategy timeframe.
- Replay feeds recorded WebSocket messages through the same live runtime semantics. Live quote-level paper execution will not exactly match bar-level backtests; report the difference.

### Intrabar fill-price table (position-side agnostic; authoritative v1 baseline)

For a **long** option, the exit action is a sell; for a **short** option, the exit action is a buy-to-close. Apply configured slippage and tick quantization against the trader for the actual transaction side. Stops/targets are evaluated against the position's mark-to-market P&L and declared trigger convention, not by assuming every position is long.

| Situation | Fill / rule |
|---|---|
| Exit stop is crossed at open | Fill at the available open with adverse-side slippage for the closing transaction; do not pretend to fill at a better trigger price |
| Exit stop touched intrabar | Fill at stop with adverse-side slippage for the closing transaction |
| Profit target is crossed at open | Fill at the available open; no better-than-open price is assumed |
| Profit target touched intrabar | Fill at target under the configured trade-through policy; default requires one-tick trade-through |
| Target merely equals a bar extreme | Not filled by default; configurable only if named in the run manifest |
| Stop and target both hit in one bar | Stop first |
| Trailing exit | Compute level from completed bars only, then apply the position-side exit rule |
| Zero-volume flat option bar | Does not trigger exits and does not provide fills; wait for next non-flat bar. After `max_stale_minutes`, force exit at next valid open with worst-case configured slippage |
| Underlying-based trigger | Decide at underlying bar close; fill at the option's next eligible bar open. Never substitute index price for option price |
| Final-bar EOD exit | Close fill on final eligible option bar with `EOD_CLOSE_FILL` and an additional configured slippage penalty if no next bar exists |
| Multi-leg entry/exit group | Evaluate each leg's fill independently unless a separately tested execution model says otherwise; record legging exposure, rejected/missing legs and any configured unwind. Never assume atomic fills from simultaneous signals |

The manifest records fill-model ID and evidence tier. Baseline is bar-OHLC simulation; quote-based paper fills are a separate evidence tier, not proof of full available size at a quoted price.

### Order lifecycle and missing-data contract (v1)

Order lifecycle: `CREATED → RISK_REJECTED` or `CREATED → QUEUED → FILLED | EXPIRED | CANCELLED`. `EXPIRED` means no eligible contract bar occurred within configured `N` bars. Partial fills are deferred for a single leg in the first implementation slice; multi-leg strategies must use an explicit leg-group state machine and may not silently treat a partially filled group as complete. Stops/targets/trailing are position/leg attributes, not independent OCO orders in the initial implementation. Idempotency key is `hash(run_or_deployment, intent_id, phase)`. Event order is `(event_time, phase_priority from this section, sequence_number)`. In live cancel/fill races, first committed sequence wins. Duplicate/retried events are deduplicated by idempotency key.

Data eligibility is evaluated per session × contract × interval. `INELIGIBLE` blocks new entries; warning policy is explicit and versioned. With an open position, continue risk/exit monitoring using the last valid mark flagged `STALE`; after `max_stale_minutes`, exit at the next valid option open with worst-case configured slippage. If no valid data arrives by session end, mark using the last valid price with a run `WARNING`. In live mode, missing/invalid data sets `HALTED_DATA`, blocks entries, allows exits where the available data supports them, and alerts. If risk cannot be assessed safely, remain halted rather than guessing.

## 5. Contract selection and lifecycle

Supported v1 policies:

- Expiry policies (`expiry_policy`): `NEAREST_ELIGIBLE`, `NEAREST_EXCLUDING_0DTE`, `MIN_DTE` (requires `min_dte`), `EXACT_DATE` (requires `exact_expiry_date`), `MONTHLY` (all resolved using point-in-time contract master).
- Strike policies (`strike_policy`): `ATM` based on last closed underlying close and valid strike step, `ITM_1..10`, `OTM_1..10`, `TARGET_DELTA` (requires `target_delta`), and `EXACT_STRIKE` (requires `exact_strike`).
- Side: CE, PE or both if strategy supports it.
- Liquidity gate: reject zero-volume/flat-bar contracts or require recent traded volume/spread criteria, according to strategy config.

Contract resolution must return a contract valid at decision time, with lot size/tick size effective on that date. If no contract qualifies, emit a structured rejection event with reason. No silent strike substitution.

V1 is not long-only. The contract must support long and short CE/PE positions, multiple independent deployments, and declared multi-leg strategy groups. Implement and validate single-leg long/short semantics first. Realistic-account short entries require a versioned buying-power/margin model; until its source assumptions are verified, any such run is either blocked from account-feasibility claims or explicitly marked `THEORETICAL`. Multi-leg realistic-account runs remain disabled until legging, missing-leg/unwind, margin and reconciliation tests pass. There is no hard-coded ten-strike strategy requirement or name-based whitelist.

Define and version `last_entry_time`, `force_flat_time` and `last_tradable_time` separately. `force_flat_time` is configurable within 09:30..15:25 Asia/Kolkata in v1 so the exit can fill at a real next-bar open; if an exit is first decided on the final available bar, fill at that bar's close with `EOD_CLOSE_FILL` and a slippage penalty. `overnight_carry=false` means flatten by configured force-flat time before expiry. When `overnight_carry=true`, margin verification is required only for positions with any short leg (single-leg long CE/PE needs none); always force-flat before expiry unless carry/settlement is explicitly enabled and tested. The official settlement reference remains `VERIFY`; do not assume it equals the last 1m close or vendor 1d close. A missing settlement price leaves the position `UNSETTLED` and adds a run `WARNING`. Holiday-shifted expiries come from the versioned contract master. Settlement/exercise for ITM options follows a distinct charge path, including applicable STT on intrinsic value; rates and calculation basis remain `VERIFY` until reconciled. OTM settlement treatment also follows verified contract/exchange rules.

## 6. Fill models, slippage and fees

### Backtest fills

Baseline fills use `next_bar_open` with pluggable slippage:
- fixed ticks;
- percentage of premium;
- spread model calibrated against observed snapshot bid/ask, segmented by premium/moneyness/time-of-day where sample size supports it.

Orders: market entry/exit intents; stop, target and trailing are **position/leg attributes evaluated by the engine**, not independent OCO orders in the first implementation slice. Limit orders are deferred until a defensible trade-through/fill model exists. Short-option entry also requires an explicit margin/buying-power check. Multi-leg groups require a declared legging/unwind policy and leg-level fill evidence; simultaneous intent generation does not imply simultaneous execution. If a bar opens through a stop or target, use open price. Same-bar stop/target ambiguity defaults to stop-first. An explicitly named optimistic sensitivity run may reverse ambiguity policy but cannot be presented as baseline.

**Fill evidence tiers:** `bar_ohlc_baseline` (historical OHLC only) and `quote_based_paper` (valid bid/ask and quote age). Do not claim quote price/size guarantees a fill. Every run records fill-model ID, evidence tier and assumptions. A slippage sensitivity artifact with multipliers ×0, ×1, ×2 and ×3 against the configured baseline is mandatory for backtest reports.

### Paper fills

Use current valid quote/depth: buy at ask, sell at bid, apply configurable simulated latency (initial test range 300–1,000 ms), quantity/depth limits and stale-data guard. Log quote age, bid/ask, assumed latency and fill reason. This is still a simulation, not a guarantee of live execution.

### Fees

Implement effective-dated, versioned `fee_schedule` dataset entries for brokerage, STT, exchange charges, SEBI fee, stamp duty and GST, with a source citation/version and calculation rule. The selected schedule version is referenced by each run manifest. Store rates as configuration, not constants in strategy code. Report gross P&L, each charge category, slippage and net P&L separately. Small accounts require per-order charges to be modelled carefully. Use integer paise or exact `Decimal`/`NUMERIC` for cash/fills/fees, with a documented rounding rule for each charge.

**VERIFY:** current and historical charge rates and their calculation bases; reconcile representative transactions against official sources and Upstox's fee calculator. Do not ship a fee schedule as `VERIFIED` until those examples match.

## 7. Risk policy

Three layers:

1. Strategy-level exits and trade rules.
2. Optional account/deployment risk policy, versioned and frozen into the run/deployment manifest.
3. Simulation invariants that cannot be disabled in realistic mode (valid contract, causal data, valid order quantities, coherent accounting, no negative/invalid prices, no duplicate fill processing).

Risk check order: intent → pre-trade policy → accepted/rejected order → execution/fill → post-fill checks. Live guards include stale-data block, duplicate-order guard, order-rate cap and manual kill switch.

Independent optional controls:
- max entry fills per day;
- daily loss limit, realized + unrealized marked at bar close; breach flattens and halts for the day; report the overshoot metric. Optional worst-case intrabar mode uses the adverse mark for the position side (bar low for long options, bar high for short options);
- max drawdown from peak equity and optional cooldown;
- max consecutive losses;
- trading window, last-entry time and force-flat time;
- max open positions and max lots;
- max premium/capital at risk per trade; short-option margin/buying-power reservation and a configurable worst-case loss cap where a finite bound exists;
- min DTE / expiry-day filters;
- India VIX/volatility filter when valid data is available;
- liquidity/spread filter;
- loss cooldown;
- manual kill switch.

Each optional setting can be independently disabled, but simulation invariants cannot be disabled in realistic mode. Sizing options: fixed lots, fixed INR risk or percentage of capital; minimum tradable size is one lot. Long-option exposure includes premium paid plus costs/gaps; short-option sizing must account for margin/buying power and the selected worst-case-risk policy. INR-based caps should be available because a single lot can consume a large share of a small account.

The **`RiskRules` Pydantic schema** (authoritative definition in `packages/risk/`) is the shared type used by both `DATA §2.1 risk_policies.rules` (JSONB) and the inline `risk_controls` field in §19.1. This schema defines all control fields referenced above. See §19.1 for the field-by-field reference and override/precedence rules.

Modes:
- `REALISTIC_ACCOUNT`: applies account capital, lots, fees, slippage and risk policy.
- `THEORETICAL`: for analysis only; UI/report must prominently label it and never imply account feasibility.

Max-trades counts entry fills, not signals or exits. Daily loss includes realized plus unrealized P&L at the completed bar close. Post-fill breach triggers the configured halt/flatten policy.

## 8. Ledger, accounts and run manifest

### Event-sourced ledger

The Postgres `LedgerWriter` appends events only: enforce this with a dedicated application role that has no UPDATE/DELETE privileges and a database trigger rejecting UPDATE/DELETE on immutable event tables. Projections are rebuildable. Append and idempotency-key enforcement occur in one transaction; use the unique event/idempotency constraint to prevent duplicate financial events after retries.

Events are append-only and include at least: `sequence_num`, `event_id`, `idempotency_key`, `account_id`, `run_id`/`deployment_id`, `event_type`, `event_time`, `recorded_at`, `correlation_id`, `schema_version`, and typed payload. Require the same `correlation_id` to propagate signal → intent → order → fill → ledger; do not regenerate it at each stage. Event types are authoritatively defined by the canonical enum in `QUANTVIEW_DATA_SPEC.md §2.1 ledger_events.event_type` (including cash movement events `DEPOSIT` and `WITHDRAWAL`, trade/order lifecycle events, `FEE`, and margin events `MARGIN_RESERVED` and `MARGIN_RELEASED` used only when short/multi-leg realistic mode is enabled under `VERIFY`). Mark-to-market observations belong in the equity series, not the financial ledger. The `FEE` ledger event is the sole authoritative fee record; `paper_fills.fee_paise` is a denormalized convenience copy required to equal the sum of its linked `FEE` events (enforced as a reconciliation check in projection-rebuild tests). The `LedgerWriter` serialises appends per account via PostgreSQL per-account advisory lock; `sequence_num` is strictly monotonic per account.

- Postgres enforces append-only behaviour for paper ledger: application role cannot UPDATE/DELETE ledger rows; corrections are new compensating events.
- Backtest events spill to Parquet during the run. Register the completed run and manifest in Postgres only after artifacts validate and persist.
- One `LedgerWriter` interface has Postgres and Parquet implementations.
- Projections (positions, cash, equity, open orders, trade summary) are rebuildable by replaying events. Replay must reproduce the same projection hashes.
- `idempotency_key` prevents duplicate fill/settlement events after retries/restarts. For engine events use `hash(run_or_deployment_id, intent_id, phase)`; for raw WS dedupe use `message_id` from `QUANTVIEW_DATA_SPEC.md §4.5`. Event ordering is `(event_time, phase_priority from §4, sequence_num)`; live cancel/fill races resolve by first committed sequence. Partial fills are deferred in v1; log a quantity-vs-bar-volume warning rather than implying the whole bar volume was available to QuantView.

**Accounting contract (exact money):**

- `units = lots × lot_size`.
- At the fill boundary, validate and quantize `fill_price` following the full procedure in §4 step 1 (float validation, `price_paise` integer conversion, integer-paise slippage, then tick-paise quantization from the effective-dated contract master — buy rounds up, sell rounds down — using integer arithmetic only). Represent price and money as `Decimal` or integer paise. Do not calculate cash using binary floats.
- `entry_value_paise = quantized_entry_price_paise × units`; `exit_value_paise = quantized_exit_price_paise × units`. Quantize/convert before multiplication; use integer arithmetic for cash flows.
- Cash flow follows transaction side: a buy-to-open or buy-to-close subtracts `entry_value_paise`/`exit_value_paise` and fees; a sell-to-open or sell-to-close adds the proceeds and subtracts fees. Short-sale proceeds are not profit; margin/buying-power reservation is tracked separately.
- For a long position, `gross_realized_paise = (exit_price_paise - entry_price_paise) × units`; for a short position, `gross_realized_paise = (entry_price_paise - exit_price_paise) × units`. Net realized P&L subtracts entry/exit fees and allocated charges exactly once, all as integer paise.
- Track long assets and short-option liabilities separately: long open positions contribute positive mark value; short positions contribute a mark-to-market liability. `equity_paise = cash_paise + long_market_value_paise - short_liability_paise`, with reserved margin/buying power tracked separately rather than double-counted as a loss. The mark-price conversion and rounding policy is explicit. Floating-point indicators never feed cash or ledger amounts.
- `realized_pnl` is closed-position P&L; `unrealized_pnl` is mark-based P&L on open positions. Slippage is embedded in fill prices and reported separately for attribution; never subtract it a second time.
- Missing/stale marks retain the last valid mark with `STALE` provenance; after the configured stale limit, follow the forced-exit policy. Settlement is a separate event type and is not fabricated from a missing price.

**Illustrative accounting example (not actual fee rates):** one lot, lot size 25, buy at ₹100.00 and sell at ₹110.00. Units = 25; entry value = ₹2,500.00; exit value = ₹2,750.00; gross P&L = ₹250.00. If illustrative entry fees are ₹2.00 and exit fees are ₹2.00, net P&L = ₹246.00 before any separately attributed non-fee costs. These fee values are placeholders only and must not be treated as verified rates.

### Accounts

Account types: `BACKTEST_VIRTUAL` (one per run), `PAPER`. `LIVE` is removed from the v1 enum and introduced only by migration behind the future real-order release gate. Every deployment belongs to exactly one account. No shared positions, cash, risk state or ledger by default. Shared data/features are allowed. Strategy instances must not mutate another account's state.

### Decision-context artifacts

For every strategy decision, write an immutable artifact under `runs/{run_id}/decisions/`, keyed by `correlation_id`. Record decision timestamp, feature values or content hash plus artifact reference, contract candidates and point-in-time selector inputs, risk decision, allow/reject result and stable reason codes, intent IDs, and input manifest/version references. The audit panel reads this artifact rather than reconstructing context from mutable current state. Live decisions retain an equivalent durable event/artifact reference in Postgres.

### Run manifest

Freeze before execution: run ID, strategy ID/code hash/parameters, selected contracts/policies, dataset manifest IDs/hashes, calendar and contract-master versions, feature IDs/code hashes/parameter hashes, time zone/session policy, fee schedule version, margin/buying-power model ID and assumption/verification status where relevant, slippage/fill model ID and evidence tier, risk config (including the resolved effective `RiskRules` — merging referenced `risk_policy_id` policy with any inline `risk_controls` overrides — and its SHA-256 hash), seed, engine version, warnings and requested range. Include trial counter and whether a period is locked hold-out. Also record Python/library versions, DuckDB thread count, timezone database version, OS and CPU architecture. A run is `SUCCEEDED` only after all output artifacts are written, validated and registered. Byte-identical reproducibility applies to ledger events, fills, trades, selected contracts and manifest fields excluding `created_at`/host-specific fields; money must match exactly. Ratio/statistical metrics may be tolerance-compared (for example relative 1e-9), with the declared tolerance stored alongside results.

## 9. Pine-to-Python custom feature contract

AI-converted Pine-like code is trusted repository code, not a runtime Pine interpreter, and still requires review, constrained execution and tests. A custom indicator is one file under `features/custom/<name>.py` with registry decorator and Pydantic parameter model. Batch runs execute in a worker subprocess with timeout and memory cap. Live runs have a per-bar time budget; on breach the feature becomes `UNAVAILABLE`, new entries are blocked, exits/risk monitoring continue, and an alert fires. Function accepts a pandas DataFrame with timestamp/OHLCV and returns named output columns. No DB, broker, secrets or arbitrary network access is passed to it.

**Pine timing and semantic contract:** a feature row with `ts_start = s` for interval `Δ` uses data through `s + Δ` and is available at `s + Δ`; time-of-day logic uses `Asia/Kolkata`; session resets (e.g. VWAP) follow the versioned calendar; `barstate.isconfirmed` maps to closed-bar-only computation. Document exact window and NaN semantics for `ta.crossover`, `ta.crossunder`, `highest`, `lowest` and `stdev`. Any `bar_index` logic requires an explicit anchor. Each custom indicator declares repaint class: `none`, `confirmed-lag` or `true-repaint`; true-repaint outputs cannot drive causal strategy decisions without an explicit reviewed alternative.

| Pine construct | Required Python mapping |
|---|---|
| `na` / `nz` | NaN / explicit, documented fill policy |
| `x[n]` | shift by `n` bars, preserving warm-up NaNs |
| `var` state | explicit serializable state or recursive calculation |
| `ta.ema`, `ta.rma`, `ta.rsi` | match Pine initialization/seeding exactly; EMA seeding from SMA of first N bars and RSI's RMA semantics must be tested |
| `ta.pivothigh` / `ta.pivotlow` | output pivot value/time plus `confirmed_at`; no pre-confirmation strategy use |
| `request.security` | explicit higher-timeframe input joined by `available_at`; `lookahead_on` forbidden |
| `plot` | named output column plus plot-style metadata |
| `alertcondition` | boolean output column |
| `strategy.entry/exit` | not converted directly to broker orders; output signal columns or a Strategy class |

Required acceptance tests: truncation at multiple points, declared warm-up NaN count, expected output schema/dtypes, no future data reads, hand-checked known values or TradingView export comparison when available, repainting declaration where relevant, and batch/live parity. Store original Pine source, conversion prompt/version and reviewer notes as metadata where permitted.

## 10. Live collector and daemon

### Collector

`collector_ws` is the sole owner of all Upstox WebSocket connections. Raw WS segments are written as `.partial`, fsynced in batches with a proposed maximum 1-second message loss window on process crash, then renamed to finalized segments. Manifests list finalized segments only; recovery scans `.partial` files and replays recoverable content after validating/truncating an incomplete frame tail, or quarantines it with a reason. There is no WebSocket acknowledgement guarantee, so this is a local durability contract, not a guarantee of zero upstream loss. `live_daemon` never opens its own Upstox WS connection.

- `collector_snapshot` persists each REST capture unchanged plus a capture header, records receive time, schema version and completeness diagnostics.
- `collector_ws` writes raw protobuf before decoding; frame records include receive timestamp, connection ID and feed mode. Keep raw files to permit decoder fixes later.
- A `SubscriptionManager` inside `collector_ws` computes the union of subscriptions required by active deployments and chart requests, within verified limits; it exposes the effective set and rejected requests to the UI.
- Subscribe to NIFTY index plus active/next expiry ATM±K contracts, re-centering as spot moves. K and feed modes depend on current Upstox limits.
- Initial documented candidate modes are `ltpc` for index and `full` for options; verify current availability/limits and fields before relying on them.
- Heartbeat includes last message time, last persisted time, reconnect count, subscription count and lag. Alert on any collector stop/gap or unexpected session delay.
- Before M7-01, `collector_ws` only writes raw segments. Starting at M7-01, frames are published through `FrameBus` to `live_daemon`; first adapter is local socket/async queue with monotonic sequence numbers and raw-segment replay. Redis/Valkey is not required unless measured latency/resume criteria in `QUANTVIEW_MASTER_SPEC.md` ADR-002 are met.
- Backfill jobs are keyed by contract/interval/range, checkpointed, rate-limit-aware and safe to rerun; snapshot collector has reserved quota and backfill pauses during market hours unless remaining budget permits.

**VERIFY:** current Upstox subscription/connection limits, exact protobuf schema/field presence per mode, `volume_traded_today` semantics, reconnect/resubscribe rules, auth expiry, expired-instruments retention and rate limits. Save at least two complete live-session fixtures and decoder tests before relying on the feed.

### Candle builder

Retain event and receive times. For cumulative volume, compute validated nonnegative deltas and handle session resets. Candles remain provisional until close plus configured late-event tolerance. Reconcile built 1m candles against vendor 1m candles after close. Never fabricate candles in a gap. Persist raw and normalized events; compact daily to Parquet.

### Live daemon

Run one OS subprocess per deployment, supervised by `live_daemon`; strategy hosts receive only declared context and IPC commands, never broker credentials or database handles. If one host stalls or exceeds its time/memory budget, kill that process, mark only its deployment `HALTED_DATA`, alert, and leave other deployments running.

Target pipeline after M7-01: `collector_ws` → `FrameBus` local transport + raw replay → normalizer → candle builder → feature windows → strategy host (one isolated instance per deployment) → risk/margin → paper broker → ledger → API/UI. `live_daemon` never owns an Upstox WebSocket connection. Persist serializable strategy state after each completed bar. The checkpoint contains last committed sequence, strategy state and open-order state. On restart, replay finalized raw messages and recovered `.partial` segment content after the checkpoint, dedupe by `message_id`, and enter `WARMING_UP`: no new entries until feature windows/checkpoints are refilled and orders/positions/cash/projections reconcile. Only then transition to `RUNNING`. If reconciliation fails, enter `HALTED_RECONCILIATION`; fail closed if state cannot be established. Late/out-of-order events never change a decision already made; closed-bar vendor corrections create a research-only revision. API/UI restart must not interrupt deployments. Default strategy decisions run on bar close; `on_tick` strategies are later scope. Live data ineligibility enters `HALTED_DATA`: block entries, continue exit/risk monitoring when possible, and alert.

### Session-day operations runbook and scheduler

Use **systemd timers** for calendar-driven tasks and systemd services for long-running processes (one supervisor model). The session-day runbook must include: 08:45 Asia/Kolkata token-readiness check and alert; daily raw instruments-master capture (lot size, tick size, listing metadata); pre-open disk/collector health check; market-session snapshot and WS monitoring; post-close manifest reconciliation and data-audit refresh; raw/canonical compaction; Postgres backup and permitted offsite backup sync; and a concise health report with gaps, retries, disk headroom and unresolved VERIFY items. Backfill is lower priority than snapshot capture and paused during market hours unless the reserved rate-limit budget permits it. Offsite copy remains blocked until Upstox terms are checked.

## 11. API and UI contracts

API is FastAPI + Pydantic/OpenAPI. Generate TypeScript types from API schemas. Long jobs use a Postgres jobs table plus worker processes; no Celery requirement for v1. Progress/live updates use WebSocket or SSE.

The command surface includes backtest launch/configuration and manual paper-order placement; order-line drag commands update SL/TP only after server acknowledgement. CRUD endpoints are required for accounts and versioned risk policies. The implementation tasks are listed in `AGENTS.md` §6; this section owns the API/UI contract.

Canonical API endpoint families (all mounted under `/api/v1` namespace):
- `/api/v1/health`, `/api/v1/data/health`, `/api/v1/data/coverage`
- `/api/v1/charts/series`, `/api/v1/charts/transforms`, `/api/v1/charts/drawings`
- `/api/v1/features`, `/api/v1/features/{id}/compute`, `/api/v1/features/{id}/metadata`
- `/api/v1/contracts`, `/api/v1/option-chain`, `/api/v1/option-chain/metrics`
- `/api/v1/strategies`, `/api/v1/strategies/{id}`
- `/api/v1/runs`, `/api/v1/runs/{run_id}`, `/api/v1/runs/{run_id}/manifest`, `/api/v1/runs/{run_id}/metrics`, `/api/v1/runs/{run_id}/trades`, `/api/v1/runs/{run_id}/ledger`, `/api/v1/runs/{run_id}/decisions`, `/api/v1/runs/{run_id}/cancel`
- `/api/v1/accounts`, `/api/v1/risk-policies`
- `/api/v1/paper/orders`, `/api/v1/paper/positions`, `/api/v1/paper/ledger`
- `/api/v1/deployments`, `/api/v1/deployments/{id}/start`, `/api/v1/deployments/{id}/stop`

UI is a React + Vite + TypeScript SPA. Charting candidate is Lightweight Charts v5 plus custom drawing/order lines; KLineChart is fallback. The full TradingView Charting Library is not assumed licensed. **VERIFY** the selected chart package's exact current licence/attribution/redistribution terms before implementation is considered `VERIFIED`.

Dragging stop/target lines sends a server command; UI commits the change only after server acknowledgement. Include data-health dashboard, backtest audit panel (signal → intent → risk → order → fill → fees with decision-time data), dependency viewer, run comparison, cost sensitivity, paper-vs-backtest reconciliation, trial count and hold-out indicator.

### 11.1 API request and response contracts

All endpoints are mounted under `/api/v1/` and exchange JSON over HTTP/REST. Streaming transport is specified and delivered by FrameBus transport M7-01 with consumers M6-05 and M7-08; REST polling is used until then.

**Common wire wrappers:**
- **Standard envelope and pagination:**
  ```json
  {
    "schema_version": 1,
    "items": [],
    "total": 0,
    "limit": 50,
    "offset": 0
  }
  ```
- **Error shape with stable reason codes:**
  ```json
  {
    "schema_version": 1,
    "error": {
      "code": "STABLE_REASON_CODE",
      "message": "Human-readable description",
      "details": {}
    }
  }
  ```

**Endpoint schemas:**

- **Wire price rule:** Chart series prices in UI endpoints are display floats rounded to the contract tick; execution, ledger, order, and position fields are strictly integer paise. Chart floats are never used for order matching or fill simulation.

- `GET /api/v1/charts/series`:
  - Request Query: `symbol` (str), `interval` (`1m`, `3m`, `5m`, `15m`, `1h`, `4h`, `1d`), `from_sec` (int64 `UtcEpochSec`), `to_sec` (int64 `UtcEpochSec`), `contract_id` (str, nullable).
  - Response: `{ "schema_version": 1, "symbol": str, "interval": str, "candles": [ { "time": int64, "open": float, "high": float, "low": float, "close": float, "volume": int64, "oi": int64/null } ] }`. Wire timestamps strictly conform to `UtcEpochSec` (`int64` UTC seconds).

- `GET /api/v1/charts/transforms`:
  - Request Query: `symbol` (str), `transform` (`HEIKIN_ASHI`, `RENKO`), `interval` (str), `from_sec` (int64), `to_sec` (int64), `brick_size` (float, optional for Renko per §22).
  - Response: `{ "schema_version": 1, "symbol": str, "transform": str, "candles": [ { "time": int64, "open": float, "high": float, "low": float, "close": float, "volume": int64 } ] }`.

- `/api/v1/charts/drawings`:
  - `GET`: Query `chart_id` (str), `contract_id` (str, nullable). Response: paginated items of `chart_drawings` (DATA §2.1: `drawing_id`, `chart_id`, `contract_id`, `drawing_type` enum `HORIZONTAL_LINE`, `VERTICAL_LINE`, `TREND_LINE`, `RECTANGLE`, `anchors`, `style`, `schema_version`, `version`, `created_at`, `updated_at`).
  - `POST`: Body matching `chart_drawings` create schema. Response: created drawing entity.
  - `PUT /api/v1/charts/drawings/{drawing_id}`: Body with updated `anchors`/`style` and `version` (optimistic lock). Response: updated entity.
  - `DELETE /api/v1/charts/drawings/{drawing_id}`: Response: `{ "schema_version": 1, "deleted": true, "drawing_id": str }`.

- `GET /api/v1/features`:
  - Request Query: optional `category`, `is_active` (bool).
  - Response: paginated list of items from `features_registry` (DATA §2.1: `feature_id`, `version`, `category`, `code_hash`, `params_schema`, `source_tiers`, `memory_class`, `is_active`, `created_at`).

- `POST /api/v1/features/{id}/compute`:
  - Request Body: `{ "symbol": str, "interval": str, "from_sec": int64, "to_sec": int64, "params": {} }`.
  - Response: `{ "schema_version": 1, "feature_id": str, "version": str, "timestamps": [int64], "columns": { "<col_name>": [float] }, "quality_flags": [str] }`.

- `GET /api/v1/features/{id}/metadata`:
  - Response: `{ "schema_version": 1, "feature_id": str, "version": str, "category": str, "code_hash": str, "params_schema": {}, "source_tiers": [str], "memory_class": str, "is_active": bool, "created_at": str }`.

- `GET /api/v1/contracts`:
  - Request Query: `underlying` (str), `expiry_date` (ISO date, optional), `strike` (Decimal string, optional), `option_type` (`CE`, `PE`, optional).
  - Response: paginated list of contract records (DATA §6: `contract_id`, `symbol`, `underlying`, `expiry_date`, `strike`, `option_type`, `lot_size`, `tick_paise`, `trading_symbol`, `is_active`).

- `GET /api/v1/strategies`:
  - Request Query: optional `family`, `is_active`.
  - Response: paginated list of `strategies_registry` rows (DATA §2.1: `strategy_id`, `lineage_id`, `version`, `family`, `code_hash`, `params_schema`, `supported_sides`, `is_active`, `created_at`).

- `/api/v1/runs`:
  - `GET /api/v1/runs`: Request Query: `strategy_id` (optional), `status` (optional), pagination. Response: paginated `runs` table rows (DATA §2.1: `run_id`, `strategy_id`, `run_config_hash`, `manifest_hash`, `git_commit`, `start_date`, `end_date`, `status`, `metrics_summary`, `created_at`).
  - `POST /api/v1/runs`: Request Body: `RunConfig` JSON schema (§19.1, including timing parameters `entry_delay_policy` enum `NEXT_BAR_OPEN` [default], `EXTRA_BARS_SENSITIVITY`, and `entry_delay_bars` int `1..5` nullable). Response: `{ "schema_version": 1, "run_id": str, "status": "QUEUED", "job_id": str }`.
  - `GET /api/v1/runs/{run_id}`: Response: full run execution status and summary metadata.
  - `GET /api/v1/runs/{run_id}/manifest`: Response: frozen `run_manifest.json` (§8, §19, §20).
  - `GET /api/v1/runs/{run_id}/metrics`: Response: `metrics.json` (§20).
  - `GET /api/v1/runs/{run_id}/trades`: Response: paginated closed/open trades array (§20.1) with entry/exit timestamps, fill prices, quantities, gross/net P&L in paise, fee breakdown, and `correlation_id`.
  - `GET /api/v1/runs/{run_id}/ledger`: Response: paginated `ledger_events` array for the run (DATA §2.1: `sequence_num`, `event_id`, `run_id`, `event_type`, `amount_paise`, `balance_paise`, `idempotency_key`, `correlation_id`, `event_time`, `recorded_at`, `schema_version`, `payload`).
  - `GET /api/v1/runs/{run_id}/decisions`: Response: paginated decision context artifacts (§8) keyed by `correlation_id` (decision timestamp, features hash/values, candidate contracts, risk checks, decision result/reason code).
  - `POST /api/v1/runs/{run_id}/cancel`: Request Body: empty or `{ "reason": str }`. Response: `{ "schema_version": 1, "run_id": str, "status": "CANCELLED" }`.

- `/api/v1/accounts`:
  - `GET`: Query `status` (optional). Response: paginated list of `accounts` (DATA §2.1: `account_id`, `name`, `account_type` enum `BACKTEST_VIRTUAL`, `PAPER`, `initial_capital_paise`, `currency`, `status`, `created_at`).
  - `POST`: Request Body: `{ "name": str, "account_type": "PAPER", "initial_capital_paise": int64 }`. Response: created account entity.

- `/api/v1/risk-policies`:
  - `GET`: Query `account_id` (optional), `is_active` (optional). Response: paginated `risk_policies` rows (DATA §2.1: `policy_id`, `account_id`, `version`, `rules`: `RiskRules`, `is_active`, `hash`, `created_at`).
  - `POST`: Request Body: `{ "account_id": str, "rules": {} }`. Response: created versioned policy entity.
  - `PUT /api/v1/risk-policies/{policy_id}`: Request Body: updated rules creating new version. Response: new version entity.

- `/api/v1/paper/orders`:
  - `GET`: Query `deployment_id` (optional), `status` (optional), pagination. Response: paginated list of `paper_orders` (DATA §2.1: `order_id`, `deployment_id`, `client_order_id`, `symbol`, `contract_id`, `position_effect`, `side`, `qty`, `order_type`, `status`, `rejection_reason`, `created_at`).
  - `POST`: Request Body: `{ "deployment_id": str, "client_order_id": str, "symbol": str, "contract_id": str, "position_effect": str, "qty": int, "order_type": "MARKET" }`. Response: created order entity with initial status (`SUBMITTED` or `REJECTED`).

- `GET /api/v1/paper/positions`:
  - Request Query: `account_id` (optional), `deployment_id` (optional).
  - Response: `{ "schema_version": 1, "positions": [ { "position_id": str, "version": int, "deployment_id": str, "contract_id": str, "symbol": str, "side": str, "qty": int, "entry_price_paise": int64, "current_mark_paise": int64, "unrealized_pnl_paise": int64, "realized_pnl_paise": int64, "updated_at": str } ] }`.

- `PATCH /api/v1/paper/positions/{position_id}/exits`:
  - Request Body: `{ "version": int, "stop_price_paise": int64 (optional), "target_price_paise": int64 (optional), "trailing_stop_pct": str (optional) }`.
  - Response: updated position entity with incremented `version`.
  - Error Response: `409 STALE_VERSION` returning current `version` on concurrency conflict.
  - Behavior: Appends a `STOP_TARGET_UPDATE` ledger event.

- `GET /api/v1/paper/ledger`:
  - Request Query: `account_id` (str, required), `from_sequence` (int64, optional), pagination.
  - Response: paginated `ledger_events` rows (DATA §2.1: `sequence_num`, `event_id`, `account_id`, `deployment_id`, `event_type`, `amount_paise`, `balance_paise`, `idempotency_key`, `correlation_id`, `event_time`, `recorded_at`, `schema_version`, `payload`) for the specified account.

- `/api/v1/deployments`:
  - `GET`: Query `account_id` (optional), `status` (optional). Response: paginated list of `deployments` (DATA §2.1: `deployment_id`, `account_id`, `policy_id`, `strategy_id`, `run_config_hash`, `mode`, `status`, `lease_owner`, `heartbeat_at`).
  - `POST`: Request Body: deployment creation parameters (`account_id`, `policy_id`, `strategy_id`, `run_config`, `mode`). Response: created deployment row in `PENDING` status.
  - `POST /api/v1/deployments/{id}/start`: Transitions deployment to `RUNNING` (triggers `live_daemon` lease acquisition and supervisor start). Response: `{ "schema_version": 1, "deployment_id": str, "status": "RUNNING" }`.
  - `POST /api/v1/deployments/{id}/stop`: Transitions deployment to `STOPPED` (triggers graceful position flattening / risk halt). Response: `{ "schema_version": 1, "deployment_id": str, "status": "STOPPED" }`.

- `GET /api/v1/data/health`:
  - Response: `{ "schema_version": 1, "collector_status": { "snapshot": str, "ws": str }, "last_heartbeat_at": str, "latest_snapshot_ts": str, "disk_free_gb": float, "active_quarantine_files": int, "unresolved_verify_items": [str] }`.

- `GET /api/v1/data/coverage`:
  - Request Query: `dataset_key` (str, optional).
  - Response: `{ "schema_version": 1, "datasets": [ { "dataset_key": str, "start_date": str, "end_date": str, "total_sessions": int, "missing_sessions": int, "known_gaps": [str], "eligibility_status": str } ] }`.

## 12. Research and ML safeguards

Build chronological datasets with declared label horizon and point-in-time features. Use purged walk-forward with embargo; reserve a locked hold-out period never used during tuning. Count every parameter/model trial in PostgreSQL `research_trials`. Start with tabular baselines (e.g. gradient-boosted trees) for regime, direction or meta-label filtering. Models are versioned registry artifacts in PostgreSQL `models_registry` and never auto-deploy. Strategies are registered in `strategies_registry`, and features in `features_registry`.

No post-entry fields in pre-entry predictions, no future-confirmed pivots, no snapshots received after decision time, and no use of future bars in labels/features. Observed snapshot coverage is limited and gappy; reconstructed option candles/model Greeks are a different source tier and must be tracked in the manifest. Register hold-out ranges in PostgreSQL `holdout_ranges`. The worker refuses any run overlapping a registered hold-out unless `final_evaluation=true`; this override is logged and enforced single-use per hold-out range per strategy lineage via PostgreSQL `final_evaluation_uses` (`UNIQUE(holdout_config_version, lineage_id)`). The single-use default and unique constraint remain the baseline enforcement. An override path for `final_evaluation_uses` is allowed only with a defect ID from the decision log and reason code `ENGINE_DEFECT`; the strategy lineage and parameters must be unchanged; the run is labelled `HOLDOUT_REUSED` in the manifest and UI; the `research_trials` count is never reset; every use is listed in the run manifest. A workflow convention alone is not an enforceable hold-out boundary.

## 13. Tests and required evidence

### Unit and property tests
- Schema normalization for snapshot v1/v2/v3, null preservation, unknown-field diagnostics and float precision.
- Calendar session boundaries, special sessions, holiday-shifted expiries and timezone conversion.
- 1m → 3m/5m/15m/1h/4h aggregation, including partial final 4h bar and missing minutes.
- Contract master validity dates, lot-size history and no-substitution behaviour.
- Fee calculation by effective date and order type.
- Risk toggles independently enabled/disabled; realistic invariants cannot be disabled.
- Ledger idempotency, append-only enforcement, compensating events and projection rebuild parity.
- Property-based tests (Hypothesis): reprocessing never duplicates events; chunked and single-pass features agree within each declared memory/tolerance contract; appending future rows never changes past decisions; chart visibility never changes strategy results; ledger rebuild reproduces balances/positions; changing only fee schedule changes costs/P&L but not signal times or contract selection.
- Fault injection using process kill at five points: raw segment write, ledger commit, checkpoint write, manifest publish and order queue. Recovery must either resume deterministically or fail closed.

### Engine tests
- Golden hand-computed backtest: every signal, selected contract, order, fill, slippage, fee, position, equity and P&L reconciles.
- Golden cases: 0DTE expiry settlement; open position with missing bars; force-flat; flat-bar stop; halted day; special session; mid-history lot-size change; strike-step change; two-account isolation fuzzing.
- Close signal fills next bar open, never same bar.
- Open signal cannot fill at the triggering open/own close.
- Gap-through stop/target fills at open.
- Same-bar stop+target uses stop-first.
- Trailing update uses completed bars only.
- Higher-timeframe values appear only at `available_at`.
- Missing bars and unavailable contracts produce explicit rejections.
- Replay determinism and idempotent restart.
- Backtest and live share strategy logic and event semantics.

### Feature/custom-code tests
- Truncation test across warm-up, random cut points, session boundary and final bar.
- Declared warm-up behaviour and output schema.
- Batch/live parity within feature-specific tolerance.
- Pine reference values for EMA/RMA/RSI/pivots where known.
- No look-ahead in BOS/CHoCH and multi-timeframe joins.

### Collector/integration tests
- Raw-first persistence survives decoder failure.
- Duplicate messages/backfill reruns do not duplicate canonical records.
- Reconnect and resubscribe; heartbeat/lag alert; token expiry handling.
- Snapshot gaps remain gaps; no synthetic capture grid.
- Compaction verifies row counts/hashes before manifest publication.
- Backup restore test for Postgres and a sampled Parquet/raw partition.

### Fault-injection tests

Required scenarios: disk-full during raw write and canonical publish; system clock jump forward/backward; duplicate collector instance (lease/lock prevents a second active writer); process kill with `.partial` recovery; token expiry; and supervisor restart. A duplicate collector must fail closed before opening a second WebSocket connection. Each test records injected fault, expected state, actual output, recovery result and whether data loss/duplication occurred.

## 14. Numeric acceptance targets

These are proposed v1 targets and must be measured on a named reference machine/dataset. If hardware differs, record the benchmark environment and adjust via ADR rather than silently weakening tests.

| Area | Acceptance target | Evidence/status |
|---|---|---|
| Full ~5-year 1m single-strategy backtest | ≤ 5 min cold; ≤ 1 min only if an optional cache is implemented after a benchmark justifies it | Benchmark report with dataset/strategy/host hash |
| Calendar-minute loop idle-skip / held-position path | Benchmark one full session flat with no pending orders and one full session with a held position; report grid minutes, contract-bar evaluations and wall time | Repeatable benchmark with host/config hash; no correctness change when skipping idle minutes |
| Chart series response, 5,000 bars | ≤ 300 ms server-side data-ready latency under local workload | Repeatable API benchmark |
| Live quote to UI | p95 ≤ 500 ms from local receive to UI update while connected | Timestamped end-to-end measurement |
| Collector session uptime | ≥ 99% of scheduled session minutes; every gap alerts | Session coverage report; no silent gaps |
| Replay determinism | identical manifest + input produces identical event sequence and output hashes across 3 reruns | Golden replay test |
| Data normalization idempotency | 0 duplicate canonical keys after 2 identical reruns | Audit query/test |
| Feature truncation | 100% registered causal features pass all required cut points | CI report |
| Ledger projection rebuild | cash/positions/equity agree exactly at currency precision; event count/hash matches | Replay test |
| Snapshot capture preservation | 100% of source captures retained or explicitly quarantined with reason | Raw-to-canonical reconciliation |
| Chart load initial payload | ≤ 5,000 bars for initial visible window unless user requests more | UI/API test |
| API/worker health | all processes expose health/heartbeat; stale collector alert within 60 s of configured threshold | Integration test |

`DESIGNED` means target agreed; `IMPLEMENTED` means measurement path exists; `TESTED` means a result is attached; `VERIFIED` means the target is repeatedly met on the declared environment.

## 15. Phased build order and gates

**Authority Note:** This section defines the architectural development phases and their substantive engineering criteria. Phase-to-milestone mapping: Phase 0a = M1, Phase 0 = M0 + M2, Phase 1 = M3, Phase 2 = M4, Phase 3 = M5, Phase 4 = M6, Phase 5 = M7, Phase 6 = M8. The authoritative task-to-gate membership mapping (exact task IDs belonging to G0a, G0, G1, G2a, G2b, G3, G4, G5, G6) is maintained exclusively in `DOCS/AGENTS.md §5` to prevent duplicate maintenance or dependency drift.

### Phase 0a — Repository skeleton (before collector implementation)
- Create repository/package skeleton, config loading, structured logging, CI, import-boundary rules and migration scaffolding.
- Add schema/status conventions and a minimal smoke-test pipeline. This is a proposed schedule, not a completed-work claim.

**Gate (G0a):** clean environment can run lint/type/import checks and migrations against a disposable local database; no real collector/hardware integration is implied.

### Phase 0 — Collectors first (first priority)
- Capture the instruments master daily, including lot size, tick size and listing metadata; gzip and SHA-256 archive every expired-API response exactly as downloaded.
- Build raw-first WebSocket capture with `.partial` recovery, sole connection ownership, SubscriptionManager and at least two recorded sessions as fixtures.
- Implement checkpointed historical backfill under a reserved REST budget; pause/throttle it during market hours behind snapshot collection.
- Configure systemd supervisor, external dead-man alert, disk-space alert, session-day runbook and permitted offsite backup. Verify data-storage terms before enabling offsite sync.
- Verify Upstox limits/schema/auth/retention details before setting the production subscription plan.

**Gate (G0):** raw data survives decoder failures; capture manifests reconcile to source; heartbeat and restart tests pass; `VERIFY` questions are explicitly tracked.

Phase 0 collector work and the Phase 1 audit may proceed in parallel, but they have separate acceptance gates and must not be treated as interchangeable.

### Phase 1 — Data audit and canonical foundation
- Build official calendar and validity-dated contract master.
- Normalize canonical vendor underlying 1m and vendor daily (`1d`) candles into Parquet; daily `available_at` is session close, and the current-day daily bar is unavailable intraday.
- Normalize 1m option candles into canonical Parquet; version manifests.
- Derive 3m/5m/15m/1h/4h from 1m and 1w/1M from vendor 1d; compare vendor intraday intervals as checksums only. 1m-derived daily OHLC is diagnostic only.
- Normalize snapshot v1/v2/v3 into superset schemas with nulls.

**Gate (G1):** all data quality reports exist; no unexplained duplicate keys; gaps are explicit; canonical normalization idempotent; source-semantics table has evidence-backed decisions or explicit unresolved `VERIFY` entries with dependent uses blocked.

### Phase 2 — Minimal deterministic backtest
- Implement the event loop in §4 with long/short CE/PE semantics, next-eligible-bar-open fills, stop-first ambiguity, effective-dated fee model, ledger writer, run manifest and decision-context artifacts. Start with single-leg behavior; add simple multi-leg groups after golden tests.
- After M3-09 reports actual coverage, the owner selects and signs the locked hold-out range before the first real-data strategy run. Register it in PostgreSQL `holdout_ranges` and track trial counts in `research_trials`. Worker refuses overlapping runs unless `final_evaluation=true`; that flag is logged and enforced single-use per hold-out range per strategy lineage via PostgreSQL `final_evaluation_uses`.
- Build one simple strategy and a hand-computed golden test before adding many strategies.

**Gate (G2a / G2b):** golden backtest passes; three identical reruns hash-identical under declared deterministic settings; cost breakdown and audit trail reconcile. Performance gates remain non-blocking until all correctness gates pass.

### Phase 3 — Feature registry and reconstructed chain
- Add built-in EMA/RSI/ATR, OI/PCR features and a lazy DuckDB reconstructed-chain view; materialize only named ML feature sets and configured ATM +/- N liquid-contract model Greeks.
- Add model IV/Greeks with explicit assumptions/provenance; compare against observed snapshot values only as a diagnostic, not as identity.

**Gate (G3):** no future data; source tiers are visible in outputs. Cache invalidation is tested only if the M5-02 benchmark justifies implementing the optional cache.

### Phase 4 — API, chart and results UI
- Add data-health, audit panel, run comparison and cost sensitivity.
- Verify chart licence before release.

**Gate (G4):** 5k-bar latency target, chart lines server-authoritative, API schema tests pass.

### Phase 5 — Live daemon and paper accounts
- Compare paper fills to backtest fills and measure slippage.

**Gate (G5):** restart/replay determinism, no duplicate fills, stale-data/kill-switch tests, session uptime target.

### Phase 6 — Research and robustness
- ML is research-only until separately reviewed and frozen.

**Gate (G6):** leakage tests pass; final evaluation is enforced by a registered, single-use `final_evaluation=true` worker guard per hold-out range per strategy lineage via PostgreSQL `final_evaluation_uses` (not merely by workflow convention); every experiment/run records a manifest and trial-counter update in PostgreSQL `research_trials`.

### Future release gate — Real orders
No real orders in v1. Before enabling a live broker adapter, verify current SEBI/NSE retail-algo rules, current Upstox order/API terms, required approvals/controls, order rate limits, kill-switch and monitoring. A `BrokerPort` interface exists so the simulation is not coupled to the broker.

## 16. Explicit VERIFY register

| Item | Exact verification task | Must remain unverified until |
|---|---|---|
| Upstox WebSocket limits | Check current docs/account entitlement for max connections, instruments/subscriptions, feed modes, depth and rate limits | limits captured with date and source link; fixture confirms decoder fields |
| Upstox protobuf fields | Capture raw 1–2 sessions; compare decoder fields with current `.proto` and docs | field-by-field fixture tests pass |
| Upstox auth/token | Verify access-token expiry, refresh/re-auth flow and unattended collector policy | restart/token-expiry integration test passes |
| Option candle volume | Establish unit and whether values are interval volume/cumulative/lot-scaled using docs plus sample reconciliation | semantics recorded in data dictionary and test fixture |
| Option candle OI | Establish snapshot/end-of-minute/update semantics and how zeros/nulls are represented | semantics recorded and sample transitions audited |
| Fee rates | Seed effective-dated charges from official sources and reconcile sample trades with Upstox calculator | sample transactions match charge-by-charge |
| Chart licence | Check exact current licence/attribution/redistribution terms for selected chart library/version | licence evidence stored with project |
| Historical calendar/expiry | Cross-check holiday-shifted expiries and special sessions against official historical NSE calendar | source and verification date attached to calendar version |
| Snapshot naive timestamp timezone | Verify the assumption that naive snapshot timestamps are Asia/Kolkata by comparison with source/candle times | comparison evidence and documented rule attached |
| Vendor IV/Greek units | Verify fraction vs percent, theta time basis and vega volatility basis for all vendor Greeks | field-by-field source evidence and fixture tests attached |
| `chng_oi` / `prev_oi` semantics | Establish reference interval, units and reset/update semantics | data dictionary and sample reconciliation attached |
| Option-candle history/strike coverage | Audit first available date, strikes per expiry/session and missing-contract coverage | versioned coverage report attached |
| Settlement reference | Verify official expiry settlement source/value and whether it differs from 1m/1d closes | authoritative source and reconciled examples attached |
| Exercise STT | Verify rate and base for applicable ITM option exercise/settlement charges by effective date | official source and hand-reconciled examples attached |
| VIX / NIFTY futures availability | Verify India VIX and expired NIFTY futures history availability through current expired-instruments/API path | successful retrieval fixtures and coverage report attached |
| DuckDB determinism | Measure multi-threaded float aggregation differences and select ordered aggregation or `threads=1` where required | repeatable test report and run-manifest settings attached |
| Expired-instruments retention | Determine current retention window and whether rolling; prioritize backfill if rolling | dated official-source evidence and observed API response fixture attached |
| Market-data storage/offsite terms | Verify Upstox terms for local storage, retention and offsite backups | terms/version/date recorded; offsite sync enabled only if permitted |
| REST quota and priority | Verify rate limits and enforce snapshot reserved budget with backfill throttle/pause | measured counters and priority/fault tests pass |
| Instrument listing date | Verify master field reliability; otherwise use first candle as first-observed bound | source evidence or explicit fallback tests |
| Parquet profile | Pin DuckDB/pyarrow and verify zstd, row groups, sort keys and statistics | lockfile plus schema/metadata/benchmark report |

### Delivery principles, evidence reports and cut list

- Build a thin vertical slice early: one synthetic data source → one canonical bar stream → one strategy decision → one tick-quantized fill → ledger/equity → decision-context artifact → minimal result view. Keep the first slice synthetic and deterministic.
- Develop the engine on synthetic fixtures in parallel with data collection/audit; do not wait for all historical data to implement causal invariants. Do not evaluate profitability on synthetic data.
- Every gate ends with an evidence report: changed files, commands and actual outputs, status labels (`DESIGNED`/`IMPLEMENTED`/`TESTED`/`VERIFIED`), audit/benchmark links, unresolved VERIFY items, known gaps, and explicit pass/fail against each acceptance target.
- Timeboxes are planning proposals, not promises. Stop at each gate and obtain approval before moving to the next milestone.
- Cut list if schedule slips: ML, drawings/layouts, Renko, option-chain overlays, multi-account UI, model Greeks beyond ATM; preserve raw capture, audit, causal engine, money correctness and recovery tests.

## 17. Developer workflow and change control

1. Before coding, read this specification (`QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md`) and `QUANTVIEW_DATA_SPEC.md`; check the current `dataset_manifest` and status report.
2. Implement one phase/gate at a time. Do not start UI polish while collection/data gates are failing.
3. Any deviation from a binding decision requires an ADR: context, decision, alternatives, migration impact, tests and rollback plan.
4. Never mark a task `TESTED` without the command and result; never mark it `VERIFIED` without external/source evidence.
5. Keep secrets out of code and fixtures. Keep `data/`, run artifacts and local tokens out of git.
6. Every run must be reproducible from manifest + input data + strategy/feature code hashes + configuration.
7. Report changed files, commands to run tests, known gaps and status for each acceptance gate. Do not claim a command or test ran if it did not.

## 18. UI screen and route specification

The frontend is a React + Vite + TypeScript single-user SPA on a private/loopback interface. Chart library is a candidate decision, not yet licensed/verified. Use Lightweight Charts v5 plus custom drawings/order lines as the first candidate; KLineChart is the fallback. Do not assume the full TradingView Charting Library is licensed. Chart library selection requires exact licence evidence.

### 18.1 Screen catalogue

| Screen | Route | Purpose and required components | Data/API contracts | Empty/loading/error states | Editable settings and acceptance |
|---|---|---|---|---|---|
| Dashboard | `/` | Health summary, collector status, data coverage warnings, latest runs, active paper deployments/accounts, shortcuts to chart/strategies/backtest/accounts/risk/results | `GET /api/v1/health`, `GET /api/v1/data/coverage`, `GET /api/v1/runs?limit=...`, `GET /api/v1/accounts`, `GET /api/v1/deployments` | Distinguish no data, stale feed, partial coverage, API unavailable; never show stale values as live | User can navigate to all core screens; each health indicator links to detail |
| Strategy browser | `/strategies` | Strategy list, family/tags, version, side support, required features/source tiers, parameter schema, test status | `GET /api/v1/strategies`, `GET /api/v1/strategies/{id}` | Empty registry, invalid plugin, unavailable feature, unverified source semantics are explicit | Select strategy/version; inspect params and supported modes; launch config prefilled from schema |
| Backtest terminal | `/backtests/new` | Date range, strategy/version/params, CE/PE/both, expiry/strike policy (with min_dte/exact_expiry_date/target_delta/exact_strike inputs), decision timeframe (1m..1d), required capital_paise (no default)/sizing, saved risk_policy_id and inline risk_controls, SL/TP/trailing (Decimal string), trading windows, carry, fee/slippage/fill/mode/hold-out/seed; launch and job progress | Shared `RunConfig` schema; `POST /api/v1/runs`, `GET /api/v1/runs/{id}`, `POST /api/v1/runs/{id}/cancel` | Validate before submit; show data-eligibility block and structured reason; cancel state and failed jobs visible | UI and CLI validate against the same schema; invalid config cannot create a run |
| Chart workspace | `/chart` | Candles, bottom time axis/side price axis, symbol/expiry/strike selector, interval, indicator list and settings dialogs, trade markers, same-page collapsible results panel; per-strike option chart in UI-1 | `GET /api/v1/charts/series`, `GET /api/v1/contracts`, `GET /api/v1/features`, `GET /api/v1/runs/{id}/trades`, `GET /api/v1/runs/{id}/metrics` | No bars, incomplete session, stale live feed, feature unavailable, unsupported transform, permission/license error | Changing visibility/layout never changes strategy result. Indicator params are schema-driven. Trade markers link to audit. |
| Accounts, risk and capital | `/accounts` and `/risk` | Separate paper accounts, capital, current cash/equity, position exposure, versioned risk policy, optional rule toggles, run/deployment assignment | `GET/POST /api/v1/accounts`, `GET/POST /api/v1/risk-policies`, `GET /api/v1/deployments` | Empty account, invalid policy, open position with stale mark, unavailable margin evidence | Changes create new policy versions; historical runs retain old version; accounts do not share cash/positions/ledger |
| Results and audit | `/runs/:runId` | Equity/drawdown, metrics, trade table, cost breakdown, slippage sensitivity, long/short and CE/PE splits, time-of-day/expiry breakdown, decision context, selected contract, feature values, manifest, warnings | `GET /api/v1/runs/{id}`, `GET /api/v1/runs/{id}/metrics`, `GET /api/v1/runs/{id}/trades`, `GET /api/v1/runs/{id}/ledger`, `GET /api/v1/runs/{id}/decisions`, `GET /api/v1/runs/{id}/manifest` | Partial run vs failed run vs complete run are distinct; metrics not available until calculation succeeds | Every metric has a click-to-explain definition; every trade links to its signal/intent/fill/ledger events |
| Paper/live monitor | `/paper` | Deployment health, feed age, WARMING_UP/HALTED_DATA state, orders/positions, alerts, paper P&L; chart order/position markers | `GET /api/v1/deployments`, `GET /api/v1/paper/positions`, `GET/POST /api/v1/paper/orders`, `GET /api/v1/paper/ledger`, `GET /api/v1/health` | Stale data visibly halts entries but continues exits; reconnect and reconciliation states explicit | Manual paper order is acknowledged by server before UI commit; no real-order control exists |
| Settings / research registry | `/settings` | Fee schedule versions, calendar/contract versions, feature/model registry, data eligibility, hold-out config, alert destination | Read/write APIs (`/api/v1/features`, `/api/v1/contracts`, etc.) with validation and audit records | Unverified source semantics prominently flagged | Editing creates versioned records; changes never mutate past run manifests |

### 18.2 UI release tiers

- **UI-1 core:** dashboard; strategy browser; backtest terminal; core candlestick chart; per-strike option chart with trade markers; indicator controls/settings dialogs; same-page results panel; accounts/risk/capital; results/audit.
- **UI-1b (promoted sub-slice):** minimal OI overlay + read-only option-chain table, promoted into scope once M3-08 reports verified OI semantics (or owner promotes earlier). Uses §26 contracts. Signals still cannot consume unverified OI.
- **UI-2 selective:** Heikin Ashi view; basic horizontal line and rectangle drawings.
- **UI-3 (scheduled v1.1, still committed):** Renko; saved multi-chart layouts; advanced drawings; interactive option-chain matrix; multi-tab OI visualizations. API/data contracts are specified in §26. If a baseline/candidate strategy depends on OI/PCR, promote the required option-chain/OI UI slice before declaring the strategy fully inspectable.
- UI test stack is `PENDING_OWNER`. Do not silently choose a browser automation framework. Unit/API contract tests are required regardless.

### 18.3 Chart and order-line invariants

- Time axis is bottom; price axis is vertical. Chart timeframe and chart transform are display choices, not changes to source truth.
- Per-strike option charts use the exact selected contract and point-in-time contract master. No silent strike substitution.
- Trade markers derive from persisted run/deployment artifacts and identify entry/exit, direction, leg/group, timestamp, fill price and event IDs.
- Order/position stop/target/trailing lines are server-authoritative. Dragging sends a versioned command; UI updates only after acknowledgement. Stale version conflicts must be shown and reconciled. Draggable order lines and drawing tools are custom components built on top of the chart library (not provided natively by it) and are sized accordingly as custom engineering tasks in AGENTS.md.
- Chart visibility, drawings, layout, colors and zoom cannot affect strategy outputs.
- Heikin Ashi/Renko values are visual transform outputs and must never be used as tradable OHLC unless a future separately approved strategy contract explicitly uses them as features (not fill prices).

## 19. Shared `RunConfig` contract (CLI, config file, and UI)

There is one versioned schema for command line, YAML/JSON config, API, and UI forms. Backtests must be launchable by CLI before M6 is complete. UI forms are generated from this schema; there must not be separate UI-only defaults.

### 19.1 Typed `RunConfig` field schema

**RiskRules schema note:** A shared `RiskRules` Pydantic model (in `packages/risk/`) is used by both `DATA §2.1 risk_policies.rules` (JSONB) and the inline `risk_controls` field below. Fields in `risk_controls` override the referenced policy; the run manifest freezes the resolved effective policy and its SHA-256 hash. Trading windows (`entry_window_start`, `last_entry_time`, `force_flat_time`) and `overnight_carry` remain top-level fields. `vix_filter_enabled` remains a top-level field (see §7). Each risk control lives in exactly one place.

| Field | Type | Range / Allowed Values | Required? | Default | Validation & Behaviour Rules |
|---|---|---|---|---|---|
| `schema_version` | string | SemVer (e.g. `"1.0.0"`) | Yes | `"1.0.0"` | Must match supported runner schema versions |
| `run_id` | UUID / str | Valid UUIDv4 format | No | Generated UUIDv4 | Unique identifier for run directory and DB record |
| `seed` | int | Non-negative integer | No | `42` | Pinned for tie-breaking and random-element reproducibility |
| `instrument_universe`| string | `"NIFTY_OPTIONS"` | Yes | `"NIFTY_OPTIONS"` | Underlying is NIFTY; contracts validated against contract master |
| `start_date` | string (ISO date)| `YYYY-MM-DD` | Yes | None | Must exist in calendar; `start_date <= end_date` |
| `end_date` | string (ISO date)| `YYYY-MM-DD` | Yes | None | Must exist in calendar and have eligible data |
| `strategy_id` | string | Registered strategy identifier | Yes | None | Must exist in Strategy Registry |
| `strategy_version` | string | SemVer | Yes | None | Pinned version; code hash verified against registry |
| `strategy_params` | object | JSON object | No | `{}` | Validated against strategy's parameter schema |
| `option_side` | enum | `CE`, `PE`, `BOTH` | Yes | `BOTH` | Determines tradable contract types |
| `decision_timeframe`| string | `"1m"`, `"3m"`, `"5m"`, `"15m"`, `"1h"`, `"4h"`, `"1d"` | Yes | `"5m"` | Master evaluation clock; risk remains on 1m grid. `"1d"` requires `overnight_carry=true` (signal available at session close, fills next open); else rejected with stable reason code `DAILY_TF_REQUIRES_CARRY`. `"1h"`/`"4h"` decisions that cannot fill before `force_flat_time` are rejected as entries with reason code `DECISION_TOO_LATE_FOR_FILL`. |
| `expiry_policy` | enum | `NEAREST_ELIGIBLE`, `NEAREST_EXCLUDING_0DTE`, `MIN_DTE`, `EXACT_DATE`, `MONTHLY` | Yes | `NEAREST_ELIGIBLE` | Resolves expiry from point-in-time contract master. `MIN_DTE` requires `min_dte`. `EXACT_DATE` requires `exact_expiry_date`. |
| `min_dte` | int nullable | `>= 0` | If `MIN_DTE` | null | Minimum days-to-expiry required; only used when `expiry_policy=MIN_DTE` |
| `exact_expiry_date` | string nullable | ISO date `YYYY-MM-DD` | If `EXACT_DATE` | null | Exact expiry date; only used when `expiry_policy=EXACT_DATE` |
| `strike_policy` | string | `ATM`, `ITM_1..10`, `OTM_1..10`, `TARGET_DELTA`, `EXACT_STRIKE` | Yes | `ATM` | Resolves strike relative to decision-time spot. `TARGET_DELTA` requires `target_delta`. `EXACT_STRIKE` requires `exact_strike`. |
| `target_delta` | Decimal string nullable | e.g. `"0.40"` | If `TARGET_DELTA` | null | Target option delta; only used when `strike_policy=TARGET_DELTA` |
| `exact_strike` | Decimal string nullable | e.g. `"24000.00"` | If `EXACT_STRIKE` | null | Exact strike price; only used when `strike_policy=EXACT_STRIKE` |
| `mode` | enum | `REALISTIC_ACCOUNT`, `THEORETICAL` | Yes | `REALISTIC_ACCOUNT`| `REALISTIC_ACCOUNT` requires G2a and verified data/margin |
| `capital_paise` | int64 | `> 0` | **Yes — REQUIRED, no default** | None | Exact money in integer paise; user enters at launch. No single starting capital assumed (see MASTER, section 'Binding UI tiers and owner inputs', subsection 'Owner decisions'). `§19.2` sample value `2000000` is an example only. |
| `sizing_mode` | enum | `FIXED_LOTS`, `FIXED_RISK_INR`, `PERCENT_CAPITAL`| Yes | `FIXED_LOTS` | Re-checked at actual fill boundary; rejects if unaffordable |
| `lots` | int32 | `> 0` | If `FIXED_LOTS` | `1` | Rejected with structured reason if capital insufficient |
| `risk_inr_paise` | int64 nullable| `> 0` | If `FIXED_RISK_INR` | null | Target risk amount in integer paise; sizing derives lots from SL distance |
| `risk_policy_id` | UUID nullable | Valid UUIDv4, ref `risk_policies.policy_id` | No | null | Optional reference to a saved risk policy; inline `risk_controls` override it; resolved effective policy and hash frozen in run manifest |
| `risk_controls` | object nullable | `RiskRules` Pydantic schema (same schema as `risk_policies.rules`) | No | null | Inline risk controls; each control is `{enabled: bool, value}`. Controls: `max_entry_fills_per_day`, `daily_loss_limit_paise`, `max_drawdown_pct` (Decimal string), `max_consecutive_losses`, `cooldown_bars`, `max_open_positions`, `max_lots`, `max_premium_per_trade_paise`, `risk_min_dte_entry`, `liquidity_filter`. Overrides referenced policy field-by-field where `enabled=true`. |
| `intrabar_stop_policy`| enum | `STOP_FIRST`, `TARGET_FIRST_SENSITIVITY` | Yes | `STOP_FIRST` | Baseline: if both SL and TP are touched in one bar, stop wins. `TARGET_FIRST_SENSITIVITY` is permitted only in a run explicitly named as a sensitivity run (see §6); such a run is labelled `SENSITIVITY_NOT_BASELINE` in the manifest and UI and is never the primary result. |
| `entry_delay_policy` | enum | `NEXT_BAR_OPEN`, `EXTRA_BARS_SENSITIVITY` | No | `NEXT_BAR_OPEN` | Baseline default is `NEXT_BAR_OPEN` (fills at next eligible bar open per §4). `EXTRA_BARS_SENSITIVITY` adds a configurable extra delay in whole 1m bars for timing sensitivity sweeps; such a run is labelled `SENSITIVITY_NOT_BASELINE` in the manifest and UI and is never the primary baseline result. |
| `entry_delay_bars` | int nullable | `1..5` | If `EXTRA_BARS_SENSITIVITY` | null | Extra entry delay in whole decision bars (1..5); required when `entry_delay_policy=EXTRA_BARS_SENSITIVITY`, otherwise null. When `entry_delay_bars > 0`, the `order_expiry_bars` clock starts after the delay. |
| `max_stale_minutes` | int | `1..60` | Yes (in realistic) | `5` | Max tolerated missing/flat bars before force-flat at next open (owner-configurable) |
| `order_expiry_bars` | int | `1..10` | Yes | `1` | Unfilled market/limit intents cancel after N decision bars |
| `stop_loss_pct` | Decimal string nullable | `"0.01"` .. `"1.0"` | No | null | Optional percentage stop from entry fill price; stored as exact Decimal string |
| `take_profit_pct` | Decimal string nullable | `"0.01"` .. `"5.0"` | No | null | Optional percentage target from entry fill price; stored as exact Decimal string |
| `trailing_stop_pct`| Decimal string nullable | `"0.01"` .. `"1.0"` | No | null | Computed only from completed bars; never intrabar peak; stored as exact Decimal string |
| `entry_window_start`| string (HH:MM)| `09:15 .. 15:00` | Yes | `"09:20"` | No entries before this time (Asia/Kolkata) |
| `last_entry_time` | string (HH:MM)| `09:30 .. 15:15` | Yes | `"15:00"` | New entries blocked after this time |
| `force_flat_time` | string (HH:MM)| `09:30 .. 15:25` | Yes | `"15:25"` | Intraday force-exit time for open positions; maximum 15:25 so exit can fill at a real next-bar open |
| `overnight_carry` | boolean | `true`, `false` | Yes | `false` | v1 default false; margin verification required only for positions with any short leg; single-leg long CE/PE needs none. See ENGINE §5 expiry/settlement rule. |
| `fee_schedule_version`| string | Registered schedule ID | Yes | `"UPSTOX_2026_V1"` | Exact charge schedule pinned in run manifest |
| `slippage_model_id`| enum | `FIXED_TICKS`, `PERCENT`, `ZERO`| Yes | `FIXED_TICKS` | Slippage model applied against trader |
| `slippage_ticks` | int | `>= 0` | If `FIXED_TICKS` | `1` | Adverse tick adjustment to fill price |
| `slippage_multiplier`| Decimal string | `"0"`, `"1"`, `"2"`, `"3"` | Yes | `"1"` | Primary run multiplier; sensitivities written as child rows |
| `risk_free_rate_source`| string | Registered rate series | Yes | `"ZERO_ASSUMPTION"` | Series or explicit zero assumption for Sharpe/Sortino |
| `vix_filter_enabled`| boolean | `true`, `false` | Yes | `false` | If true, requires canonical `india_vix` dataset from M3-12 |
| `holdout_config_version`| string nullable| Registered holdout ID | No | null | Overlapping hold-out dates rejected unless `final_evaluation=true` |
| `final_evaluation` | boolean | `true`, `false` | Yes | `false` | Audited single-use flag to evaluate locked holdout period |

*Guardrails:* A run is rejected with a structured error response if any required field is missing or unverified. In `REALISTIC_ACCOUNT` mode, unverified fee schedules or undefined `max_stale_minutes` halt execution. `capital_paise` is always required with no default; runs without it are rejected.

### 19.2 Canonical `RunConfig` file example (`run_config.json`)

```json
{
  "schema_version": "1.0.0",
  "run_id": "b7e289c0-6f29-4d2a-9e12-3f14892c9001",
  "seed": 42,
  "instrument_universe": "NIFTY_OPTIONS",
  "start_date": "2025-01-01",
  "end_date": "2025-06-30",
  "strategy_id": "ema_cross_baseline",
  "strategy_version": "1.0.0",
  "strategy_params": {
    "fast_period": 9,
    "slow_period": 21
  },
  "option_side": "BOTH",
  "decision_timeframe": "5m",
  "expiry_policy": "NEAREST_ELIGIBLE",
  "strike_policy": "ATM",
  "mode": "REALISTIC_ACCOUNT",
  "capital_paise": 2000000,
  "sizing_mode": "FIXED_LOTS",
  "lots": 1,
  "risk_policy_id": null,
  "risk_controls": null,
  "intrabar_stop_policy": "STOP_FIRST",
  "entry_delay_policy": "NEXT_BAR_OPEN",
  "entry_delay_bars": null,
  "max_stale_minutes": 5,
  "order_expiry_bars": 1,
  "stop_loss_pct": "0.20",
  "take_profit_pct": "0.40",
  "trailing_stop_pct": null,
  "entry_window_start": "09:20",
  "last_entry_time": "15:00",
  "force_flat_time": "15:25",
  "overnight_carry": false,
  "fee_schedule_version": "UPSTOX_2026_V1",
  "slippage_model_id": "FIXED_TICKS",
  "slippage_ticks": 1,
  "slippage_multiplier": "1",
  "risk_free_rate_source": "ZERO_ASSUMPTION",
  "vix_filter_enabled": false,
  "holdout_config_version": null,
  "final_evaluation": false
}
```

### 19.3 CLI command interface

The backtest CLI uses the exact same `RunConfig` schema as the REST API and UI:

```bash
# Validate RunConfig without executing
python -m quantview.cli backtest validate --config run_config.json

# Execute backtest run from configuration file
python -m quantview.cli backtest run --config run_config.json --output-dir data/runs/

# Execute with sensitivity sweep override
python -m quantview.cli backtest run --config run_config.json --slippage-sweep 0,1,2,3
```

*Note on Baseline Smoke Strategy:* The built-in 5m EMA(9)/EMA(21) strategy is strictly an engineering plumbing and deterministic verification baseline. It demonstrates end-to-end data feeds, signal generation, contract selection, and exact-money ledger attribution. It is not tuned for profitability and makes no market edge claims.

## 20. Backtest metrics contract

Every completed run writes `runs/{run_id}/metrics.json`. It is recomputed from the immutable ledger, fills, trades and equity series; never trust strategy-side summary counters. The metrics file includes schema/version, source hashes, run/strategy IDs, metric values, units, null reasons and a human-readable `definition` for every metric. The results UI provides click-to-explain from this definition.

### 20.1 Accounting basis

- `gross_price_pnl`: realized price P&L at actual simulated fill prices before explicit fees/charges. For long position units `q`: `(exit_fill - entry_fill) × q`; for short position units `q`: `(entry_fill - exit_fill) × q`. Convert currency result to integer paise with the declared per-charge/cash rounding rule.
- `gross_reference_pnl`: optional diagnostic using a named reference price before slippage; never substitute it for executable gross P&L.
- `slippage_cost`: attribution = adverse difference between reference and actual fill price × quantity, reported separately. Slippage is already embedded in actual fill prices and is **not deducted twice**.
- `net_pnl = gross_price_pnl - sum(explicit fees/charges)`; settlement/exercise charges are included when applicable. Report both aggregate and per-charge categories. Unknown fee rates are `VERIFY`, not guessed.
- Open-position unrealized P&L is shown separately and valued from last valid mark with staleness flags. Equity = cash + signed market value/liability of positions. Marks belong in the equity series, not the financial event ledger.

### 20.2 Required metrics and formulas

| Metric | Definition |
|---|---|
| Gross/net P&L | Sum of closed-trade `gross_price_pnl` and `net_pnl`; report open unrealized separately |
| Fee breakdown | Sum each effective-dated charge category from the fee schedule; report `UNKNOWN/VERIFY` if unavailable; do not silently omit |
| Drawdown amount | For equity \(E_t\), running peak \(P_t=\max_{u\le t}E_u\); `DD_amount_t = P_t - E_t`; max drawdown is max over t |
| Drawdown % | `DD_pct_t = (P_t - E_t)/P_t` for positive peaks; report null/reason where denominator is non-positive |
| Drawdown duration | Elapsed time and number of bars/sessions from peak until equity recovers to that peak; unresolved duration remains open at run end |
| Win rate | Count of closed trades with net P&L > 0 divided by closed trades; zero-P&L trades are separately counted and not wins |
| Average win/loss | Mean net P&L among positive/negative closed trades; report loss as signed and absolute forms |
| Profit factor | Sum of positive closed-trade net P&L divided by absolute sum of negative closed-trade net P&L; null if no losses |
| Expectancy | Mean closed-trade net P&L; also show `p(win) × avg_win - p(loss) × avg_abs_loss` reconciliation |
| Exposure | Time with nonzero open position divided by eligible session time; separately report gross notional exposure and capital utilization where computable |
| Trade count | Distinct closed trade/group IDs, with open trades separately counted; no counting of legs as separate strategy trades unless requested |
| Long/short, CE/PE splits | Same P&L, fees, win/loss, count and drawdown basis grouped by position direction and option type |
| Time-of-day breakdown | Fixed Asia/Kolkata session buckets recorded in metrics schema; preserve empty buckets as zero-count with explicit status |
| Expiry-day breakdown | Separate expiry-day vs non-expiry-day; define expiry-day from versioned contract/calendar data |
| MAE/MFE | For each trade, max adverse/favourable excursion based only on available option-contract price path during holding period; report the sampling/fill evidence tier |
| Sharpe | Annualized mean periodic net excess return divided by standard deviation, with return frequency, risk-free assumption, annualization factor and missing-period policy recorded |
| Sortino | Annualized mean periodic net excess return divided by downside deviation, with target return and annualization recorded |
| Deflated Sharpe Ratio | Compute using the registered number of trials, sample length, observed Sharpe, skewness and kurtosis; use a documented Bailey/López de Prado formulation. Record every input, estimator convention, and trial-registry hash; do not compute as a plain Sharpe threshold |
| Return/capital | Return on initial capital and peak capital required; theoretical runs must not label return as account-feasible |
| Fill quality | Fill model ID/evidence tier, number of stale/flat-bar waits, EOD close fills, rejected intents, slippage sensitivity and fill warnings |

All metric outputs include `value`, `unit`, `definition`, `source_event_types`, `calculation_version`, and `null_reason` when not defined.

### 20.2.1 Risk-adjusted metric conventions

- Build daily simple returns from session-close equity: `r_t = E_t / E_{t-1} - 1`, using only consecutive valid session closes and recording any excluded/missing session. Default risk-free return is zero only as an explicit labelled assumption unless a versioned risk-free series is supplied.
- `Sharpe_daily = mean(r_t - rf_t) / sample_std(r_t - rf_t)`; annualized Sharpe is `Sharpe_daily × sqrt(252)`. If sample standard deviation is zero or the valid sample is too short for a meaningful estimate, return null with a reason.
- `DownsideDeviation = sqrt(mean(min(r_t - target_t, 0)^2))`; `Sortino_annualized = mean(r_t - rf_t) / DownsideDeviation × sqrt(252)`. Record target-return convention; default target is the declared risk-free return.
- For Deflated Sharpe Ratio (DSR), implement the authoritative Bailey & López de Prado (2014) formulation (*The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality*). Distinguish clearly between:
  1. The **sampling variance** of the chosen strategy's estimated Sharpe ratio \(\widehat{SR}\), derived from sample size \(T\), skewness \(s\), and non-excess kurtosis \(k\):
     \[
     \text{Var}(\widehat{SR}) = \frac{1 - s \cdot \widehat{SR} + \frac{k - 1}{4} \widehat{SR}^2}{T - 1}
     \]
  2. The **expected maximum Sharpe ratio** \(SR^* = E[\max_n \{SR_n\}]\) across \(N\) independent trials under the null hypothesis of zero skill:
     \[
     SR^* \approx \sigma_{\text{trials}} \cdot \left[ (1 - \gamma)\Phi^{-1}\left(1 - \frac{1}{N}\right) + \gamma\Phi^{-1}\left(1 - \frac{1}{N \cdot e}\right) \right]
     \]
     where \(\gamma \approx 0.5772156649\) is the Euler–Mascheroni constant, \(\Phi\) is the standard-normal CDF, and \(\sigma_{\text{trials}} = \sqrt{V(\{SR_n\})}\) is the **sample standard deviation across the \(N\) trial Sharpe ratio estimates** (cross-trial dispersion), **NOT** the sampling uncertainty \(\text{Var}(\widehat{SR})\). Cross-trial Sharpe dispersion is computed across trials (including run-less trials) from `research_trials.sharpe_daily`, `n_obs`, and `search_space_id` (DATA §2.1). If trial history has \(N=1\) or cross-trial dispersion is undefined, emit null with reason or use an explicitly declared benchmark dispersion.
  3. The resulting Deflated Sharpe Ratio statistic:
     \[
     \text{DSR} = \Phi\left( \frac{\widehat{SR} - SR^*}{\sqrt{\text{Var}(\widehat{SR})}} \right)
     \]
  - **Frequency Consistency Invariant:** All Sharpe ratios (\(\widehat{SR}\), \(SR^*\), \(\sigma_{\text{trials}}\)) inside the DSR formula must be calculated at the exact same per-period observation frequency as \(T\) (e.g. daily), **never** annualized Sharpe. Annualized Sharpe (\(\text{Sharpe}_{\text{daily}} \times \sqrt{252}\)) is reported separately in the UI.
  - **Audit Metadata:** Every calculation records: `T`, `s` (skewness), `k` (kurtosis), `N` (registered trial count), `sigma_trials`, `sr_expected_max`, `trial_registry_hash`, and estimator conventions. Reference fixtures must validate the implementation.
- Default time-of-day buckets in `Asia/Kolkata` for a regular session: `[09:15,10:00)`, `[10:00,11:00)`, `[11:00,12:00)`, `[12:00,13:00)`, `[13:00,14:00)`, `[14:00,15:00)`, `[15:00,15:30]`. For special sessions, derive analogous buckets from calendar open/close and store the exact boundaries in metrics metadata.

### 20.3 Determinism, audit and trial accounting

- Recompute metrics from the same frozen ledger/equity artifacts. Same inputs and calculation version must produce the same `metrics.json` hash under the declared deterministic profile.
- Store metrics schema/version and calculation code hash in run manifest.
- For floating ratios, either enforce deterministic aggregation/order/threads or declare tolerance-comparison; money totals are exact integer paise.
- **Trial Accounting Policy:**
  - Record every configuration and result that could influence strategy or model selection in the authoritative PostgreSQL `research_trials` table (persisting `sharpe_daily`, `n_obs`, `search_space_id` per DATA §2.1 for cross-trial Sharpe dispersion). The filesystem file `ops/trials.jsonl` is a machine-readable export of `research_trials` for external audit and local tooling.
  - Do **not** inflate \(N\) by blindly counting diagnostic sensitivity rows: the 0x/1x/2x/3x slippage sensitivity rows and capital-affordability sweeps (₹10k..₹200k) are child evaluation scenarios belonging to the parent hypothesis run, not independent trials.
  - Count every genuinely tried parameter set, indicator combination, feature subset, or rule variation inspected by the researcher. If \(N\) is unconstrained, document the search space bounds.

## 21. Indicator and feature formula catalogue

The first built-in catalogue is proposed pending owner approval. Every feature declares: stable ID/version; formula; source inputs and source tier; parameter schema; warm-up; availability time; repaint class (`none`, `confirmed-lag`, `true-repaint`); memory class (`finite(W)` or `infinite`); live/batch support; null semantics; numerical tolerance; and chart/strategy eligibility.

| Indicator | Formula/definition | Common/default variant | Warm-up and causal rule | Repaint/memory |
|---|---|---|---|---|
| SMA(n) | Arithmetic mean of last n closes | Close, n=20 common | n valid closed bars; available at bar close | none; finite(n) |
| EMA(n) | `EMA_t = αx_t + (1-α)EMA_{t-1}`, `α=2/(n+1)` | EMA, close; smoke n=9 and 21 | Seed policy must be explicit (first value or SMA seed); warm-up declared; available after close | none; infinite (checkpoint state) |
| RSI(n) | `100 - 100/(1 + RMA(gain,n)/RMA(loss,n))` | Wilder RMA, n=14 | n changes plus smoothing warm-up; zero-loss/zero-gain behavior defined and tested | none; infinite for RMA |
| MACD | `EMA(fast)-EMA(slow)`; signal = EMA(MACD, signal_n); histogram = MACD-signal | 12/26/9 | slow EMA plus signal warm-up; closed-bar only | none; infinite |
| ATR(n) | `TR=max(H-L, abs(H-prevClose), abs(L-prevClose))`; ATR=RMA(TR,n) by default | Wilder RMA, n=14 | needs prior close and declared smoothing warm-up | none; infinite |
| Bollinger Bands | middle=SMA(close,n); upper/lower=middle ± k × rolling standard deviation | n=20, k=2, population/sample stdev choice explicitly fixed | n closed bars; standard-deviation convention in manifest | none; finite(n) for rolling window |
| Session VWAP | `sum(typical_price × volume)/sum(volume)`, typical price `(H+L+C)/3` | Reset each verified session | Requires source volume semantics: index volume is not a measurement, and volume-based features use the NIFTY futures series (dataset from M3-12) once available and verified; otherwise they remain `UNAVAILABLE`, not fabricated | none; infinite within session, reset by calendar |
| Supertrend | ATR bands around `(H+L)/2`, with final-band carry-forward and direction switching | ATR 10, multiplier 3 common; exact band algorithm versioned | Requires ATR warm-up; closed-bar confirmed only | none; infinite state |
| ADX(n) | Directional movement + Wilder-smoothed DI+/DI−, then `DX=100×|DI+−DI−|/(DI++DI−)`, ADX=RMA(DX,n) | n=14 | Multiple smoothing windows; formula versioned and known-value tested | none; infinite |

Variant policy:
- Do not call one formula “universally best”. Each formula/variant is named and versioned; TradingView/Pine defaults are a compatibility target only after matching the exact Pine semantics.
- For EMA, record seed and first-valid index. For RSI/ATR/ADX, record Wilder RMA vs EMA/SMA choice. For Bollinger, record population vs sample standard deviation. For VWAP, record session reset and volume-source eligibility.
- The owner must approve the initial indicator list (`PENDING_OWNER`). Additional indicators may be registered without changing old versions.

### 21.1 Option-chain features and source requirements

| Feature | Formula/meaning | Source tier and availability | Gate |
|---|---|---|---|
| PCR by OI | Sum PE OI / sum CE OI over declared expiry and strike band | Observed snapshots first; option candles only after OI semantics verified; available at capture receipt/bar close | `VERIFY` OI semantics, coverage and zero denominator handling |
| PCR by volume | Sum PE volume / sum CE volume over declared band | Snapshot or option-candle volume only after unit/reset semantics verified | `VERIFY` volume semantics |
| OI change by strike band | `OI_t - OI_{t-k}` for each contract/band with explicit baseline | Snapshot/candle tier; never bridge missing captures without warning | `VERIFY` `chng_oi`/`prev_oi` semantics; independently compute change only when comparable OI observations exist |
| OI rate of change | `(OI_t - OI_{t-k}) / abs(OI_{t-k})`; null when denominator zero/invalid | Same as OI change | Requires verified OI units and interval |
| ATM straddle price | CE price + PE price for matched expiry/strike/as-of time; use mid only when both sides valid and freshness passes | Snapshot bid/ask or option candles; label close vs mid source | No mixing different expiries/times; staleness threshold in feature params |
| Delta-band OI | Sum OI over contracts whose declared observed/model delta lies in a band; label `observed` vs `model` delta | Observed Greeks only after unit verification; otherwise model Greeks tier | Never silently blend vendor and model Greeks |
| Model IV skew | Difference between model IVs at matched absolute delta bands, expiry and as-of time | Model tier, with rates/dividend/forward/time assumptions pinned | Label `model_*`; solver failures and missing strikes explicit |
| Multi-strike OI distribution | OI per strike and change/ROC across a declared band around ATM | Snapshot/candle tier; coverage and contract universe shown | Do not assume snapshot is a complete chain |

The feature output must include `source_tier`, `source_manifest_hash`, `available_at`, `staleness`, `quality_flags`, and missing-contract list. No signal can consume a feature while its required source semantics remain `VERIFY`.

### 21.2 Deterministic BOS / CHoCH algorithm specification

This section establishes the binding, versioned algorithm for swing structure, Break of Structure (BOS), and Change of Character (CHoCH) under `derived/features/bos_choch/`.

#### 1. Pivot parameterization and identification
- **Window Parameters:** `pivot_left` (\(W_L\)) and `pivot_right` (\(W_R\)), default \(W_L = 5, W_R = 5\).
- **Swing High at bar \(i\):**
  \[
  \text{high}[i] > \text{high}[i - l] \quad \forall l \in [1, W_L] \quad \text{and} \quad \text{high}[i] \ge \text{high}[i + r] \quad \forall r \in [1, W_R]
  \]
- **Swing Low at bar \(i\):**
  \[
  \text{low}[i] < \text{low}[i - l] \quad \forall l \in [1, W_L] \quad \text{and} \quad \text{low}[i] \le \text{low}[i + r] \quad \forall r \in [1, W_R]
  \]
- **Tie-Breaking Rule:** Strict inequality on the left side ensures that in plateau or double-top situations, the earliest bar index is selected as candidate.
- **Causal Confirmation Rule:** A swing pivot occurring at bar \(i\) is confirmed strictly at the close of bar \(i + W_R\):
  \[
  \text{confirmed\_at} = \text{ts\_close}(i + W_R)
  \]
  **Universal Invariant:** No strategy, feature, or signal may observe or reference a swing pivot prior to `confirmed_at`. The pivot’s economic timestamp `pivot_time = ts_close(i)` is retained for line-drawing and geometry, but causal availability is strictly governed by `confirmed_at`.

#### 2. Level tracking and break rules
- **Active Structural Levels:** The engine maintains `active_swing_high` (price, `pivot_time`, `confirmed_at`, `consumed=false`) and `active_swing_low` (price, `pivot_time`, `confirmed_at`, `consumed=false`).
- **Break Criterion:** Default variant is **close-through**:
  - Bullish break: `close[t] > active_swing_high.price` where `ts_close(t) >= active_swing_high.confirmed_at`.
  - Bearish break: `close[t] < active_swing_low.price` where `ts_close(t) >= active_swing_low.confirmed_at`.
  - (Optional touch variant where `high[t] > active_swing_high.price` is configurable as a separate named parameter variant).
- **One-Time Level Consumption:** When an active swing level is broken by an eligible bar, its state immediately transitions to `consumed = true`. A consumed level cannot generate subsequent break events.

#### 3. Market bias and event classification
- **Market Bias State Machine:** Bias states are `NEUTRAL` (run initiation), `BULLISH`, and `BEARISH`.
- **Classification Matrix:**
  | Current Bias | Triggered Break Event | Event Label | New Bias State | Semantic Meaning |
  |---|---|---|---|---|
  | `NEUTRAL` | `close[t] > active_swing_high` | `BULLISH_CHOCH` | `BULLISH` | Initial trend establishment |
  | `NEUTRAL` | `close[t] < active_swing_low` | `BEARISH_CHOCH` | `BEARISH` | Initial trend establishment |
  | `BULLISH` | `close[t] > active_swing_high` | `BULLISH_BOS` | `BULLISH` | Trend continuation |
  | `BULLISH` | `close[t] < active_swing_low` | `BEARISH_CHOCH` | `BEARISH` | Structural trend reversal |
  | `BEARISH` | `close[t] < active_swing_low` | `BEARISH_BOS` | `BEARISH` | Trend continuation |
  | `BEARISH` | `close[t] > active_swing_high` | `BULLISH_CHOCH` | `BULLISH` | Structural trend reversal |

*Note on Convention:* The `NEUTRAL` first-break labelling (`BULLISH_CHOCH` / `BEARISH_CHOCH`) is a nomenclature convention. Downstream strategies should consume `market_bias` transitions (`NEUTRAL` -> `BULLISH`, `BEARISH` -> `BULLISH`, etc.) rather than relying solely on the event label.

#### 4. Ambiguous double-break bar handling
The double-break case applies **only to the optional `TOUCH` variant**. Under the default `CLOSE_THROUGH` criterion, a single scalar `close[t]` cannot be both above `active_swing_high` and below `active_swing_low` simultaneously.

Under the optional `TOUCH` variant, if an extraordinary bar \(t\) has both `high[t] > active_swing_high` and `low[t] < active_swing_low`:
- Flag bar with quality attribute `AMBIGUOUS_DOUBLE_BREAK`.
- If tick data or 1m sub-bars exist within the decision bar, evaluate the breaks in chronological sequence.
- If only the current bar's OHLC is available, apply the conservative trend-reversal policy (prior bias breaks first into CHoCH, followed by continuation in the opposite direction). Do not introduce new enum values.

#### 5. Output record schema
Each evaluated bar emits:
- `ts_event`: bar close time
- `available_at`: availability timestamp
- `last_confirmed_high_price`, `last_confirmed_high_time`
- `last_confirmed_low_price`, `last_confirmed_low_time`
- `structural_event`: enum (`NONE`, `BULLISH_BOS`, `BEARISH_BOS`, `BULLISH_CHOCH`, `BEARISH_CHOCH`)
- `market_bias`: enum (`NEUTRAL`, `BULLISH`, `BEARISH`)
- `broken_level_price`, `broken_level_time` (nullable)
- `quality_flags`: array of strings

Known-sequence reference fixtures and truncation-equivalence tests are mandatory before implementation acceptance.

## 22. Chart transforms and custom transform contract

All transforms live under `derived/chart_transform/` and have their own ID/version, parameters, input manifest hash, code hash, availability timestamps, and quality flags. They are display transforms, not canonical or tradable OHLC.

### Heikin Ashi
- `HA_close=(O+H+L+C)/4`
- `HA_open=(previous_HA_open + previous_HA_close)/2`; first seed is explicitly versioned (e.g. `(O+C)/2`)
- `HA_high=max(H, HA_open, HA_close)`
- `HA_low=min(L, HA_open, HA_close)`
- Output timestamp maps to the source bar; it becomes available only when that source bar closes. Never use HA open/high/low/close as fill prices.

### Renko
- Deferred to UI-3 but API/data contract is specified now.
- Brick size is a required versioned parameter: fixed absolute price or a causal ATR-derived size calculated only from data available before the brick is confirmed. Brick algorithm (close-based vs high/low-based), reversal threshold, wick policy, gap/multiple-brick handling and seed policy are all versioned.
- A brick's `event_time`/`source_ts` points to the source bar/event that confirms it; `available_at` is confirmation time, not a backdated idealized time. If a single source bar implies multiple bricks but intrabar order is unknown, record ambiguity and use a conservative declared rule.
- No transform output is inserted into `underlying_candles`/`option_candles`; never fill trades at transform values.

### Plugin contract
A transform plugin declares input schema, output schema, parameters, causal availability, state/memory class, warm-up, deterministic seed, code hash, version and tests. It must pass truncation/no-future-data and chunk-equivalence tests. A custom transform is reviewed repository code, not uploaded/executed directly from the browser.

## 23. Frozen model artifact and ML roadmap

No training occurs inside a backtest or live decision process. A strategy can optionally consume a frozen model through a typed inference interface.

Every model artifact has:
- `model_id`, semantic version, artifact SHA-256, model format/runtime version;
- training code hash, training dataset manifest IDs/hashes and date range;
- feature IDs/versions/parameter hashes, source tiers and explicit `available_at`/as-of semantics;
- label definition, target horizon, split/embargo/walk-forward metadata, trial IDs and evaluation report;
- inference interface/schema, expected feature names/order/dtypes, null handling, deterministic settings and resource budget;
- `trained_at`, `available_from`, and model registry status; no artifact is promoted automatically.

At run start, the model hash and full model manifest are frozen into the run manifest. Inference may only consume features available at the decision timestamp. A model unavailable, late, invalid or over its time budget becomes `UNAVAILABLE`; dependent new entries are blocked while exits/risk continue.

Roadmap:
- **R1 research baselines:** direction/price-movement prediction, market-regime classification, strategy-specific meta-labeling (win/loss filtering). All are research-only.
- **R2 pattern discovery:** option-chain and tick/WebSocket pattern discovery; blocked until recorded WS sessions, semantics and data-quality gates pass.
- **R3 pattern-to-indicator:** discovered patterns become a versioned indicator only through the frozen-model contract, with out-of-sample validation and human review.
- No self-modifying live strategies; no training data from future or overlapping label windows; purged walk-forward with embargo; registered trial counter; hold-out final evaluation is single-use per hold-out range per strategy lineage.

## 24. Position groups, margin and legging contract

- A `PositionGroup` groups declared legs under one strategy intent, with group ID, entry timestamp, entry premium/debit/credit, leg fills, combined marked P&L, group stop/target/trailing configuration, exposure and coordinated exit intent.
- Stops/targets/trailing are engine-evaluated position/group attributes, not independent OCO orders in the first implementation slice.
- Group-level stop/target is evaluated on the combined position value using each leg's own valid mark. Missing/stale leg marks make the group mark stale and block new entries; exits continue under the stale-data policy.
- Individual leg exits are allowed. The group records partial closure and remaining exposure.
- Legging state machine includes `INTENT_CREATED`, `LEG_1_QUEUED`, `LEG_1_FILLED`, `LEG_2_QUEUED`, `GROUP_OPEN`, `LEG_2_REJECTED`, `UNWIND_QUEUED`, `UNWOUND`, `GROUP_CLOSED`, `HALTED_UNRESOLVED`. A second-leg failure must trigger the configured unwind/recovery policy; do not pretend the intended group opened.
- Partial fills are deferred from initial implementation. If a simulated bar suggests order quantity exceeds observed bar volume, emit a quantity-vs-volume warning; do not invent partial-fill precision.
- Exposure limits apply at strategy and account level, including per-leg and group gross/net exposure.
- Margin/buying-power is a `VERIFY` requirement: verify initial/maintenance margin, hedge benefit for spreads, intraday/expiry margin changes, forced exit, settlement and short-option risk. Until verified, short-option and short-leg realistic-account runs are rejected or labelled `THEORETICAL` with the reason visible in config, manifest and UI.

## 25. Cross-cutting execution invariants and evidence

- Every signal/intent/order/fill/ledger record propagates `correlation_id`; idempotency key hashes deployment/run ID + intent ID + phase.
- No independent OCO stop/target orders in v1; position/group attributes avoid orphaned exit orders.
- Live cancel/fill races are resolved by first committed sequence; duplicate/reordered messages are deduplicated by `message_id`.
- `collector_ws` writes `.partial` raw segments, fsyncs batches no slower than 1 second under normal operation, renames finalized files atomically, and manifests only finalized segments. WebSocket has no acknowledgement protocol; the explicit target loss windows are in the Master Spec and are not achieved claims.
- Restart checkpoint = last committed collector sequence + strategy state + open orders/positions. Restart replays raw messages after checkpoint, dedupes, reconciles before new decisions and fails closed if state cannot be established.
- Late/out-of-order events never alter an already-made decision. Closed-bar vendor corrections create a research-only revision and do not rewrite past live decisions.
- Fault injection at minimum: raw segment write, ledger commit, checkpoint write, manifest publish, order queue.
- Batch feature/custom code runs in a subprocess with timeout and memory cap. Live feature code is budgeted per bar; a breach makes that feature `UNAVAILABLE`, blocks dependent entries, continues exits/risk, and alerts.
- Performance gates are non-blocking until correctness gates pass. Cache-related performance claims are conditional on a cache actually being justified and implemented.

## 26. UI-3 Contract Skeletons (Scheduled v1.1, Designed Now)

Per Master Spec and UI tiers, UI-3 features (Option Chain Panel, OI Tabs/Overlays, Saved Multi-Chart Layouts) are scheduled for v1.1 but have their binding API and data contracts specified now.

### 26.1 Option chain panel contract (`GET /api/v1/option-chain`)

- **Query Parameters:**
  - `underlying`: string (e.g. `"NIFTY"`)
  - `expiry`: string (ISO date, e.g. `"2025-06-26"`)
  - `as_of`: timestamp UTC nullable (defaults to latest available)
  - `strike_range`: int (number of strikes above/below ATM, default 10)
- **Response Schema (`OptionChainResponse`):**
  - `schema_version`: string
  - `as_of_time`: timestamp UTC
  - `received_at`: timestamp UTC
  - `underlying_spot`: float64
  - `atm_strike`: float64
  - `source_tier`: enum (`OBSERVED_SNAPSHOT`, `RECONSTRUCTED_CANDLE`, `MODEL_ESTIMATE`)
  - `is_stale`: boolean
  - `staleness_seconds`: float64
  - `coverage_completeness`: float64 (0.0 .. 1.0)
  - `missing_strikes`: array of float64
  - `quality_flags`: array of strings
  - `strikes`: array of `OptionChainStrikeRow`:
    - `strike`: float64
    - `ce`: `OptionContractQuote`
    - `pe`: `OptionContractQuote`
- **`OptionContractQuote` fields:**
  - `contract_id`: string
  - `trading_symbol`: string
  - `ltp`: float64 nullable
  - `bid`: float64 nullable, `ask`: float64 nullable
  - `bid_qty`: int64 nullable, `ask_qty`: int64 nullable
  - `volume`: int64 nullable, `oi`: int64 nullable, `prev_oi`: int64 nullable, `change_oi`: int64 nullable
  - `iv`: float64 nullable, `iv_source`: enum (`OBSERVED`, `MODEL`)
  - `delta`: float64 nullable, `gamma`: float64 nullable, `theta`: float64 nullable, `vega`: float64 nullable

*Invariant:* Never present partial or stale snapshot data as a complete, live chain without prominent warning flags.

### 26.2 OI metrics and overlay contract (`GET /api/v1/option-chain/metrics`)

- **Query Parameters:** `underlying`, `expiry`, `as_of`, `window_minutes` (default 15)
- **Response Schema (`OptionChainMetricsResponse`):**
  - `as_of_time`: timestamp UTC
  - `total_ce_oi`: int64, `total_pe_oi`: int64
  - `pcr_oi`: float64 nullable (`total_pe_oi / total_ce_oi`)
  - `total_ce_volume`: int64 nullable, `total_pe_volume`: int64 nullable
  - `pcr_volume`: float64 nullable
  - `max_pain_strike`: float64 nullable
  - `atm_straddle_price`: float64 nullable
  - `strike_oi_distribution`: array of `{strike: float64, ce_oi: int64, pe_oi: int64, ce_oi_roc: float64, pe_oi_roc: float64}`
  - `delta_band_oi`: array of `{band_name: string, ce_oi: int64, pe_oi: int64}`
  - `source_tier`: string, `quality_flags`: array of strings

### 26.3 Saved multi-chart layouts (`/api/v1/charts/layouts`)

- **`POST /api/v1/charts/layouts` / `GET /api/v1/charts/layouts/{id}` Payload:**
  - `layout_id`: UUID
  - `name`: string
  - `user_id`: string
  - `grid_type`: enum (`1x1`, `2x1`, `2x2`, `3x1`)
  - `panes`: array of `ChartPaneConfig`:
    - `pane_id`: string
    - `symbol`: string
    - `interval`: string
    - `chart_type`: enum (`CANDLESTICK`, `HEIKIN_ASHI`, `RENKO`)
    - `indicators`: array of `{indicator_id: string, params: object, visible: boolean}`
    - `linked_cursor`: boolean
  - `schema_version`: int
  - `version`: int (optimistic lock token)

