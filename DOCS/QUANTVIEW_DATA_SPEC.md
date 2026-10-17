# QuantView Data Specification

**Status vocabulary:** `DESIGNED` / `IMPLEMENTED` / `TESTED` / `VERIFIED`. This document describes the target contract; unless backed by an implementation report, each item is `DESIGNED` only.

## 1. Data principles and truth layers

1. **Raw:** immutable source payloads and original files; preserve vendor bytes/schema and receive metadata.
2. **Canonical:** normalized, typed, versioned Parquet datasets. Never overwrite an existing partition; corrections produce a new revision.
3. **Derived:** higher timeframes, reconstructed chains, model Greeks, features and chart transforms. Every artifact declares input dataset IDs/hashes and code/config versions.
4. **Operational:** Postgres records jobs, accounts, orders, fills, ledger, run manifests, deployments and registries.
5. **Live transport:** a `FrameBus` interface carries live frames with monotonic sequence numbers; raw segments remain the durable source of truth. Initial transport is local socket/async queue plus replay. Redis/Valkey is optional and requires a measured justification.

Never fabricate missing rows, turn absent values into zero, or silently mix observed and modelled values. Keep source timestamp, receive/availability time and ingestion time distinct.

## 2. Storage directory layout

Use a configurable `QUANTVIEW_DATA_ROOT`; default repository-local development root is `data/`. Keep large mutable runtime data out of source control.

```text
data/
  raw/
    upstox_rest/{dataset}/trade_date=YYYY-MM-DD/part-*.json.gz
    upstox_rest/instruments_master/capture_date=YYYY-MM-DD/response.json.gz + manifest.json
    upstox_rest/expired_api/endpoint=<name>/capture_date=YYYY-MM-DD/response-<sha256>.json.gz + manifest.json
    upstox_ws/trade_date=YYYY-MM-DD/segment-<UTC-minute>-<connection-id>.pb.zst
    upstox_ws/manifests/trade_date=YYYY-MM-DD/*.json
  lake/
    underlying_candles/interval=1m/year=YYYY/month=MM/part-*.parquet
    underlying_candles/interval=1d/year=YYYY/part-*.parquet
    india_vix/interval=1m/year=YYYY/month=MM/part-*.parquet
    nifty_futures_candles/interval=1m/year=YYYY/month=MM/part-*.parquet
    rates_dividends/version=<assumption-version>/part-*.parquet
    fee_schedule/version=<schedule-version>/part-*.parquet
    risk_assumptions/version=<version>/part-*.parquet
    data_eligibility/audit_version=<audit-version>/part-*.parquet
    option_candles/underlying=NIFTY/expiry=YYYY-MM-DD/part-*.parquet
    option_snapshot_captures/trade_date=YYYY-MM-DD/part-*.parquet
    option_snapshot_rows/trade_date=YYYY-MM-DD/part-*.parquet
    # reconstructed_chain is a lazy DuckDB view by default; no physical directory unless explicitly materialized/versioned
    ws_quotes/trade_date=YYYY-MM-DD/underlying=NIFTY/part-*.parquet
    contract_master/as_of_date=YYYY-MM-DD/part-*.parquet
    calendar/version=<calendar-version>/part-*.parquet
  derived/
    candles/interval=<tf>/year=YYYY/month=MM/part-*.parquet
    chart_transform/transform_id=<id>/version=<version>/trade_date=YYYY-MM-DD/part-*.parquet
    model_greeks/model_version=<version>/trade_date=YYYY-MM-DD/part-*.parquet
    ml_feature_sets/feature_set_id=<id>/version=<version>/part-*.parquet
    features/feature_id=<id>/code_hash=<hash>/params_hash=<hash>/month=YYYY-MM/partition_input_hash=<hash>/upstream_state_hash=<hash>/part-*.parquet
  runs/{run_id}/manifest.json
  runs/{run_id}/metrics.json
  runs/{run_id}/ledger/part-*.parquet
  runs/{run_id}/trades/part-*.parquet
  runs/{run_id}/equity/part-*.parquet
  runs/{run_id}/decisions/part-*.parquet  # decision-context audit artifacts
  staging/                 # temporary writes; never queried as canonical
```

### 2.1 PostgreSQL operational schema outline (binding logical design contract)

PostgreSQL holds metadata, operational transactions, run indexes, and user preferences. Bulk historical market candles and option quotes remain in Parquet. The logical operational schema covers:

| Entity / Table | Primary Key | Foreign Keys / References | Key Columns & Constraints | Writer / Reader Ownership | Retention & Mutability |
|---|---|---|---|---|---|
| `accounts` | `account_id` (UUID) | None | `name` (text), `account_type` (enum: `BACKTEST_VIRTUAL`, `PAPER`), `initial_capital_paise` (int64 > 0), `currency` (`INR`), `status` (enum: `ACTIVE`, `FROZEN`, `CLOSED`), timestamps. Note: `BACKTEST_VIRTUAL` accounts exist only in run artifacts and execution contexts; persistent rows in this table represent `PAPER` accounts in v1. `LIVE` is removed from the v1 enum and introduced only by migration behind the future real-order release gate. | Writer: `api`; Reader: `api`, `live_daemon`, workers | Mutable operational record; audited status changes |
| `risk_policies` | `policy_id` (UUID) | `account_id` -> `accounts` | `version` (int), `rules` (JSONB, conforming to shared `RiskRules` Pydantic schema: max entries, daily loss limit, max drawdown, cooldown bars, exposure caps), `is_active` (bool), `hash` (sha256) | Writer: `api`; Reader: `api`, `worker_compute`, `live_daemon` | Versioned, immutable once assigned to a run/deployment |
| `deployments` | `deployment_id` (UUID) | `account_id` -> `accounts`, `policy_id` -> `risk_policies` | `strategy_id` (text), `run_config_hash` (text), `mode` (enum: `MANUAL_PAPER`, `STRATEGY_PAPER`), `status` (enum: `PENDING`, `RUNNING`, `HALTED`, `STOPPED`), `lease_owner` (text nullable), `heartbeat_at` (ts) | Writer: `api`, `live_daemon`; Reader: `api`, UI | Mutable operational state with lease heartbeats. Authoritative store for `live_daemon` instance ownership and lease tracking. |
| `jobs` / `leases` | `job_id` (UUID) | `deployment_id` (nullable) | `job_type` (enum: `BACKTEST`, `PAPER_SESSION`, `DATA_AUDIT`, `FEATURE_COMPUTE`, `PARAMETER_SWEEP`, `ML_TRAIN`, `DATA_PUBLISH`), `lease_token` (UUID nullable), `lease_expires_at` (ts nullable), `status` (enum: `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`), `attempts` (int) | Writer: `api` (enqueues), worker (claims lease); Reader: `api`, UI | Operational job queue; leases expire on worker crash. For live runtimes, `live_daemon` ownership is tracked authoritatively by `deployments.lease_owner` and `heartbeat_at`; a `PAPER_SESSION` job is a non-authoritative lifecycle dispatch/audit record. |
| `runs` | `run_id` (UUID) | `deployment_id` (nullable), `account_id` (nullable) | `strategy_id` (text), `run_config_hash` (text), `manifest_hash` (text), `git_commit` (text), `start_date` (date), `end_date` (date), `status` (enum: `STAGING`, `VALIDATED`, `SUCCEEDED`, `FAILED`, `CANCELLED`), `metrics_summary` (JSONB) | Writer: run-owning worker; Reader: `api`, UI | Immutable once published (`SUCCEEDED`); points to Parquet artifacts |
| `dataset_manifests` | `manifest_id` (UUID) | None | `dataset_key` (text), `version` (int), `row_count` (int64), `sha256_hash` (text unique), `uri_path` (text), `is_active` (bool), `created_at` (ts) | Writer: `worker_data` / dataset publisher; Reader: all workers, `api` | Immutable manifest registration; atomic active pointer update |
| `paper_orders` | `order_id` (UUID) | `deployment_id` -> `deployments` | `client_order_id` (text unique per deployment), `symbol` (text), `contract_id` (text nullable), `position_effect` (enum: `BUY_TO_OPEN`, `SELL_TO_OPEN`, `SELL_TO_CLOSE`, `BUY_TO_CLOSE`), `side` (enum: `BUY`, `SELL`, derived from `position_effect`), `qty` (int32 > 0), `order_type` (enum: `MARKET`), `status` (enum: `SUBMITTED`, `FILLED`, `REJECTED`, `CANCELLED`), `rejection_reason` (text nullable). `EXIT` is an intent kind resolved to a `*_TO_CLOSE` effect, not an order enum. | Writer: `api` / `live_daemon`; Reader: `api`, UI | Append-only transitions; immutable terminal status |
| `paper_fills` | `fill_id` (UUID) | `order_id` -> `paper_orders` | `fill_time` (timestamp UTC), `fill_price_paise` (int64), `fill_qty` (int32), `fee_paise` (int64), `slippage_paise` (int64), `fill_model_id` (text) | Writer: `live_daemon` / fill simulator; Reader: `api`, `ledger` | Strictly immutable append-only execution log. `fee_paise` is a denormalized convenience copy required to equal the sum of linked `FEE` ledger events. |
| `ledger_events` | `event_id` (UUID) | `account_id` -> `accounts`, `run_id` -> `runs` (nullable), `deployment_id` -> `deployments` (nullable) | `sequence_num` (int64 unique monotonically increasing per account), `event_id` (UUID), `account_id` (UUID), `run_id` (UUID nullable), `deployment_id` (UUID nullable), `event_type` (enum: `DEPOSIT`, `WITHDRAWAL`, `ORDER_INTENT`, `ORDER_ACCEPTED`, `ORDER_REJECTED`, `ORDER_EXPIRED`, `ORDER_CANCELLED`, `FILL`, `FEE`, `MARGIN_RESERVED`, `MARGIN_RELEASED`, `STOP_TARGET_UPDATE`, `RISK_BREACH`, `SETTLEMENT`, `COMPENSATING_EVENT`), `event_time` (timestamptz), `recorded_at` (timestamptz), `amount_paise` (int64), `balance_paise` (int64), `idempotency_key` (text unique), `correlation_id` (UUID), `schema_version` (int), `payload` (JSONB) | Writer: designated `LedgerWriter` transaction; Reader: `api`, UI | **Strictly immutable, append-only**. Financial truth in integer paise; corrections via `COMPENSATING_EVENT`. Cash movement is represented solely by `DEPOSIT` and `WITHDRAWAL`. `MARGIN_RESERVED` and `MARGIN_RELEASED` are used only when short/multi-leg realistic mode is enabled (gated by `VERIFY`). `FEE` ledger event is the authoritative fee record; `paper_fills.fee_paise` is a denormalized copy required to equal the sum of linked `FEE` events. `LedgerWriter` serialises appends per account via PostgreSQL per-account advisory lock; `sequence_num` is strictly monotonic per account. The backtest run ledger (Parquet, defined in DATA §4.7 / ENGINE §8) carries identical schema fields per event. |
| `chart_drawings` | `drawing_id` (UUID) | None | `chart_id` (text), `contract_id` (text nullable), `drawing_type` (enum: `HORIZONTAL_LINE`, `VERTICAL_LINE`, `TREND_LINE`, `RECTANGLE`), `anchors` (JSONB: time/price coordinates), `style` (JSONB: color, width, label), `schema_version` (int), `version` (int, optimistic lock), `created_at`, `updated_at` | Writer: `api`; Reader: `api`, UI | Versioned for optimistic locking; independent from strategy engine |
| `saved_layouts` | `layout_id` (UUID) | None | `name` (text), `user_id` (text), `pane_config` (JSONB: multi-chart grid, linked symbols, active interval), `schema_version` (int), `version` (int, optimistic lock), `created_at`, `updated_at` | Writer: `api`; Reader: `api`, UI | User preference entity; UI-3 target contract |
| `strategies_registry` | `strategy_id` (text) | None | `lineage_id` (text; stable across versions of one hypothesis family), `version` (text), `family` (text), `code_hash` (text), `params_schema` (JSONB), `supported_sides` (text[]), `is_active` (bool), `created_at` (ts) | Writer: `api`; Reader: `api`, UI, workers | Operational strategy registry; immutable code hash per version |
| `features_registry` | `feature_id` (text) | None | `version` (text), `category` (text), `code_hash` (text), `params_schema` (JSONB), `source_tiers` (text[]), `memory_class` (text), `is_active` (bool), `created_at` (ts) | Writer: `api`; Reader: `api`, UI, workers | Operational feature registry; immutable code hash per version |
| `models_registry` | `model_id` (text) | None | `version` (text), `model_type` (text), `artifact_uri` (text), `feature_set_id` (text), `hyperparams` (JSONB), `metrics` (JSONB), `created_at` (ts) | Writer: `worker_compute`; Reader: `api`, UI, workers | Operational ML model registry; immutable once published |
| `research_trials` | `trial_id` (UUID) | `run_id` -> `runs` (nullable) | `strategy_id` (text), `run_id` (UUID nullable), `config_hash` (text), `sharpe_daily` (numeric nullable), `n_obs` (int nullable), `search_space_id` (text), `created_at` (ts). Cross-trial Sharpe dispersion is computed from these columns (including trials without runs). Authoritative store; `ops/trials.jsonl` is an export. | Writer: `worker_compute`; Reader: `api`, UI | Append-only trial registry for DSR/hypothesis accounting |
| `holdout_ranges` | `holdout_config_version` (text) | None | `start_date` (date), `end_date` (date), `registered_at` (ts) | Writer: owner / `api`; Reader: `worker_compute`, UI | Authoritative registered holdout intervals |
| `final_evaluation_uses` | `holdout_config_version`, `lineage_id` | `run_id` -> `runs` | `holdout_config_version` (text), `lineage_id` (text), `strategy_id` (text), `strategy_version` (text), `run_id` (UUID), `used_at` (ts); `UNIQUE(holdout_config_version, lineage_id)` | Writer: `worker_compute`; Reader: `api`, UI | Single-use gate enforcing one holdout evaluation per hold-out range per strategy lineage. Override rules, defect logging requirements, and run labelling are governed authoritatively by ENGINE §12. |

Full SQL migrations (`packages/db/migrations/`) are implemented under M1-04/M1-09. This table outline constitutes the binding logical design contract.

### 2.2 Parquet profile (target; pin versions before production use)

- Pin DuckDB and pyarrow exact versions in the lockfile and record both in every run manifest.
- Use Zstandard (`zstd`) compression; default target row-group size is 250,000 rows, configurable per dataset and benchmarked before changing.
- Sort rows by stable query keys before writing: candles by `trade_date, ts_start, contract_id` (or `instrument_key` for underlying); snapshots by `received_at, expiry, strike, option_type`; quote records by `received_at, contract_id`.
- Write Parquet statistics for filter/sort columns and timestamp columns. Validate sorted-key monotonicity, row-group metadata, schema, counts and hashes before publish.
- This profile is `DESIGNED`; benchmark and compatibility tests must support any later change. Verify Upstox storage/offsite-backup terms before offsite copying source data.

### Partition and file rules

- Partition by fields used for pruning, not by high-cardinality contract IDs as directory levels.
- Underlying candles: 1m uses interval + year/month; vendor 1d uses interval + year only. Keep 1m canonical separate from derived intervals. India VIX and NIFTY futures 1m series use interval + year/month.
- Option candles: partition by underlying + expiry only; include `trade_date` as a column rather than year/month directory levels. Files sort by `trade_date, ts_start, contract_id`; an expiry partition lets a run load one or two expiries.
- Snapshot capture headers and snapshot rows use the matching schema names `option_snapshot_captures/` and `option_snapshot_rows/`, each partitioned by trade date. WS quotes use trade date and may additionally partition by underlying. Avoid one file per snapshot. Compact captures into daily files while preserving capture boundaries and raw references.
- Target Parquet row groups around 100k–1M rows where practical; target daily files roughly 64–512 MB compressed for large feeds, but allow smaller files for small datasets. These are tuning targets, not correctness rules.
- Every expired-API response is archived as the original response body wrapped in gzip, with SHA-256 calculated over the original uncompressed response bytes plus endpoint, request parameters (excluding secrets), receive time, status code and content type. Never normalize or reserialize this archival copy. Daily instruments-master response is preserved similarly.
- Compaction writes to a temporary path, validates schema/count/hash, then atomically publishes a new manifest pointer. Never let DuckDB query a partial write.
- Each worker process opens its own DuckDB connection and reads canonical Parquet. Only a designated writer publishes new files/manifests.

## 3. Canonical types and naming

- Timestamp columns: UTC-aware timestamp in Parquet (`timestamp[us, tz=UTC]` or equivalent supported type); source-local timestamps are preserved in raw records.
- Display timezone: `Asia/Kolkata`.
- Prices/quantities/Greeks: use float64 for prices and derived calculations where numerical reproducibility matters; use int64 for integer quantities/counts. Vendor IV/Greeks must not be downcast to float16.
- IDs: stable string IDs for contracts, captures, datasets and runs. Hashes use a documented algorithm such as SHA-256.
- `strike` is exact `decimal(9,2)` or an integer in the canonical strike unit; never use a binary float as a contract key. Cash, fills and fees are integer paise or `Decimal`/`NUMERIC` with a stated per-charge rounding rule. Float64 remains appropriate for market prices and derived statistics; exact currency reconciliation is performed using exact money types.
- Missing numeric values: null/NaN according to column type plus a quality flag where the reason matters. Zero is a real value only if the source explicitly provided zero.
- Enum examples: `option_type` = `CE|PE`; `source_kind` = `upstox_rest|upstox_ws|derived|model`.
- Use `ts_start`, `ts_end`, `available_at`, `received_at`, `ingested_at` consistently. Do not use ambiguous `timestamp` in canonical schemas.
- `UtcEpochSec`: int64 whole seconds since 1970-01-01T00:00:00Z. API/UI wire format only (chart times, trade markers, replay cursors), produced from canonical UTC timestamps by flooring to the second. Never stored in canonical Parquet; never used for `available_at` or sub-second logic.

## 4. Canonical schemas

**Machine-readable schema source:** canonical tables are defined once in `packages/data/schemas/` using Pydantic models for API/validation and matching PyArrow schemas for Parquet. Schema modules generate the canonical schema documentation and migration/change report; handwritten duplicate schema definitions are prohibited. Round-trip tests cover Pydantic → Arrow → Parquet → Arrow → Pydantic-compatible records, nullable fields, decimals, timestamps/timezones, enum values and schema-version compatibility. This is a target contract (`DESIGNED`) until evidence is recorded.

### Interval source-of-truth matrix

| Interval | Canonical source | Construction / availability rule |
|---|---|---|
| `1m` | Vendor source | Preserve vendor rows/revisions; `available_at = ts_end` for a completed bar |
| `3m`, `5m`, `15m`, `1h`, `4h` | Derived from canonical `1m` | Session-calendar anchored; `available_at = ts_end`; vendor versions are comparison/checksum inputs only |
| `1d` | Vendor daily series | Store under `lake/underlying_candles/interval=1d/`; `available_at` is official session close; never use the current session daily bar intraday |
| `1w`, `1M` | Derived from canonical vendor `1d` | Calendar-aware aggregation; only completed daily bars may contribute; availability follows the final constituent session close |

A 1m-derived daily OHLC series is diagnostic only and never replaces the vendor daily close. Phase 1 must report daily-series coverage and normalization idempotency.

`is_flat_bar` is true exactly when `volume == 0 AND open == high == low == close`; do not classify a bar as flat from zero volume alone or equal OHLC alone. The execution consequence is defined once in `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md` §4.

### 4.1 `underlying_candles`

| Column | Type | Meaning |
|---|---|---|
| `instrument_key` | string | Vendor or internal stable instrument identifier |
| `underlying` | string | `NIFTY` for this scope |
| `interval` | string | `1m` vendor source; `3m/5m/15m/1h/4h` derived from 1m; `1d` vendor daily source; `1w/1M` derived from vendor 1d |
| `ts_start` | timestamp UTC | Inclusive start of bar |
| `ts_end` | timestamp UTC | Exclusive end of bar |
| `available_at` | timestamp UTC | Intraday: `ts_end`; daily: official session close. A current-day daily bar is unavailable to intraday decisions |
| `open`, `high`, `low`, `close` | float64 | OHLC |
| `volume` | int64 nullable | Source volume, semantics documented per source |
| `oi` | int64 nullable | Source OI, semantics documented per source |
| `source` | string | Source adapter ID |
| `source_version` | string | API/schema version or adapter version |
| `revision` | int32 | Immutable revision number |
| `is_active` | boolean (manifest-resolved view) | True only for the revision selected by the active dataset manifest; not mutated in historical revision files |
| `quality_flags` | list<string> | Missing/gap/duplicate/special-session/validation flags |
| `ingested_at` | timestamp UTC | Ingestion time |

Revision identity is `(instrument_key, interval, ts_start, revision)` and must be globally unique within the dataset. Active identity is `(instrument_key, interval, ts_start)` and must be unique among rows selected by one published manifest. The manifest-resolved view exposes `is_active`; historical revisions remain immutable and are never overwritten.

### 4.2 `option_candles`

Include all underlying candle fields plus:

| Column | Type | Meaning |
|---|---|---|
| `contract_id` | string | Stable internal contract ID |
| `instrument_key` | string | Vendor instrument key for that exact expiry contract |
| `trading_symbol` | string nullable | Vendor display symbol |
| `expiry` | date | Contract expiry date |
| `strike` | decimal(9,2) or integer | Exact strike key normalized to contract-master precision; never a binary float key |
| `option_type` | enum | `CE` or `PE` |
| `lot_size_at_source` | int32 nullable | Value returned with source record; not assumed current |
| `source` | string | e.g. expired historical candle endpoint |
| `interval` | string | Vendor source for 1m; higher intraday intervals are derived from canonical 1m |

Revision identity is `(contract_id, interval, ts_start, revision)` and must be globally unique. Active identity is `(contract_id, interval, ts_start)` and must be unique among rows selected by one published manifest. The manifest-resolved option-candle view exposes `is_active`; this flag is computed from the selected manifest and is not mutated in historical revision files. Historical revisions remain immutable and may coexist outside the active selection. Do not assume `volume` means contracts or lots or that `oi` has a specific update convention until audit is complete.

### 4.3 Snapshot capture header: `option_snapshot_captures`

One row per actual captured response/file, not one row per strike.

| Column | Type | Meaning |
|---|---|---|
| `snapshot_id` | string | Stable capture ID |
| `received_at` | timestamp UTC | Local receive time; availability time for the snapshot |
| `trade_date` | date | Session date in Asia/Kolkata |
| `underlying` | string | `NIFTY` |
| `expiry` | date nullable | Expiry requested/returned |
| `spot_price` | float64 nullable | Spot value if present in source version |
| `schema_version` | string | v1/v2/v3 or exact decoder version |
| `source_file` | string | Raw payload reference |
| `row_count` | int32 | Number of option rows in capture |
| `completeness` | float64 nullable | Estimated coverage only if defined against a known instrument universe |
| `field_presence_mask` | string/bitset | Which optional fields were present in the source schema |
| `quality_flags` | list<string> | Late start, gap, partial, parse warning, etc. |
| `ingested_at` | timestamp UTC | When persisted canonically |

### 4.4 Snapshot rows: `option_snapshot_rows`

One row per strike/type per capture.

Columns: `snapshot_id`, `received_at`, `trade_date`, `underlying`, `expiry`, `strike`, `option_type`, `spot_price`, `oi`, `prev_oi`, `volume`, `ltp`, `bid`, `ask`, `bid_qty`, `ask_qty`, `change`, `change_oi`, `iv_observed`, `delta_observed`, `gamma_observed`, `theta_observed`, `vega_observed`, `schema_version`, `field_presence_mask`, `quality_flags`, `source_file`.

All source-absent fields are null (including `prev_oi`, which is present in v1 snapshots but absent or named differently in later captures). The field names explicitly say `_observed` for vendor IV/Greeks. A snapshot row is keyed by `(snapshot_id, expiry, strike, option_type)`; duplicate keys inside one capture fail validation or are quarantined.

**Expiry Resolution from Directory Path:** When raw snapshot payloads lack an explicit `expiry` column (as in original v1/v2 captures where expiry was encoded in the folder hierarchy `live/option_chain/nifty/{expiry_date}/...`), the canonicalizer must parse the expiry date from the parent directory path. Record provenance as `path_derived` in `quality_flags`, preserve the original raw path in `source_file`, and quarantine any capture with ambiguous or unparseable directory structure into `quarantine/` rather than guessing.

### 4.5 `ws_quotes`

One row per decoded quote/update message, with a pointer to raw segment and decoder version:

`message_id`, `connection_id`, `collector_sequence_number` (monotonic local sequence, required), `vendor_sequence_number` nullable, `feed_type` (enum: `initial_feed`, `live_feed`, `market_info`), `instrument_key`, `contract_id` nullable, `ts_event` nullable, `ts_recv`, `available_at`, `ltp`, `ltq`, `ltt`, `cp`, `atp`, `volume_traded_today`, `oi`, `total_buy_qty`, `total_sell_qty`, `bid_px_1..5`, `bid_qty_1..5`, `ask_px_1..5`, `ask_qty_1..5`, `iv_observed`, `delta_observed`, `gamma_observed`, `theta_observed`, `vega_observed`, `rho_observed`, `vendor_ohlc` (list/map keyed by interval from V3 marketOHLC), `feed_mode` (e.g. `ltpc`, `full`, `full_d30`; note `full_d30` requires Upstox Plus), `decoder_version`, `raw_segment_ref`, `quality_flags`.

Preserve event time and receive time independently. Define `message_id` as a stable hash of `(connection_id, collector_sequence_number, payload_checksum)`; the vendor sequence, when present, is retained separately for reconciliation. If an internal sequence cannot be assigned, use `(connection_id, ts_recv, payload_checksum)` and flag the weaker dedupe basis. WebSocket updates are quote-update events, not guaranteed complete trade tape. Where volume is cumulative, bar volume is a validated nonnegative delta with explicit reset/session-boundary handling.

Zero ask/bid depth and open interest (OI) reported on non-option instruments must be flagged in `quality_flags` (e.g. `ZERO_DEPTH`, `NON_OPTION_OI`), never treated as a liquid zero quote. The `full_d30` mode requires Upstox Plus account entitlement. Capture and record at least two representative live market sessions as permanent fixtures before finalizing decoder implementation.

### 4.6 Derived candles and chart transforms

Derived candle schema is the base OHLC schema plus `derivation_id`, `derivation_version`, `input_interval`, `input_manifest_hash`, `session_policy`, `is_partial`, and `quality_flags`. Heikin Ashi and Renko outputs use the separate `derived/chart_transform/transform_id=<id>/version=<version>/trade_date=YYYY-MM-DD/` layout; never label transformed values as tradable OHLC.

### 4.7 Versioned risk and margin assumptions

Risk/margin assumptions are versioned and frozen into every run/deployment manifest. Keep the selected `margin_model_id`, version, effective period, method, parameter hash, source/reference and verification status. Do not hard-code an exchange/broker margin formula or claim it is current without dated source evidence. A missing or unverified margin model blocks realistic-account short-option feasibility claims; theoretical runs must label the assumption and its limits.

### 4.8 Reconstructed option chain and model Greeks

`reconstructed_chain` is a **lazy DuckDB view** over canonical `option_candles`, contract master, calendar and eligible point-in-time snapshots; it is not a stored dataset by default. Its logical key is `(as_of_minute, expiry, strike, option_type, source_manifest_hash)`.

Columns exposed by the view include `as_of_minute`, `available_at`, contract identifiers, `spot_close_available`, `option_open/high/low/close`, `volume_source`, `oi_source`, `source_quality_flags`, and model inputs. Materialize only (a) explicitly named/versioned ML feature sets and (b) model Greeks for ATM +/- N liquid contracts. N and the liquidity rule are configuration values captured in the run/dataset manifest. `model_greeks` includes `model_version`, `model_iv`, `model_delta`, `model_gamma`, `model_theta`, `model_vega`, `forward_method`, `rate_assumption`, `dividend_assumption`, `time_to_expiry`, `solver_status`, and `quality_flags`. Model fields must not overwrite observed snapshot fields.

Only use values available at or before the declared `available_at`. An option bar's final close is not available before that bar closes. Spot/forward/volatility inputs must be point-in-time and documented.

## 5. Calendar and session model

Create a versioned `trading_calendar` Parquet dataset with a manifest and a corresponding Postgres index row. Columns:

`calendar_version`, `session_date`, `market`, `is_open`, `session_type` (`regular|special|closed`), `open_time_local`, `close_time_local`, `timezone`, `source_url_or_document`, `verified_at`, `notes`. The Parquet dataset manifest is authoritative; Postgres is only an index for locating/versioning it.

Store intraday breaks only if authoritative session rules require them. Maintain separate tables for official holiday records and special sessions, then generate the calendar version from those sources. A session inferred from market data is evidence to investigate, not automatic proof that the exchange was open.

- Regular NIFTY session baseline: 09:15–15:30 Asia/Kolkata, subject to the versioned calendar.
- Session-anchored intraday bars are `[start, end)`, with `available_at = end`.
- For 4h: 09:15–13:15 and 13:15–15:30 (partial final bar).
- A session with missing source bars stays flagged as incomplete. Do not create synthetic bars to fill gaps.
- Weekend/holiday records are quarantined until matched to official special-session evidence or corrected from source.
- prior inventory notes (audit leads only) observed a Saturday 2026-02-21 underlying row and Saturday 2026-07-04 snapshot collection; these are **audit leads**, not confirmed valid sessions.
- The observed 2026-04-13 expiry is consistent with a holiday-shifted expiry according to the review; calendar/contract master still must cite the official historical schedule before status is `VERIFIED`.

## 6. Contract master

Maintain a validity-dated `contract_master` with:

`contract_id`, `underlying`, `exchange`, `segment`, `instrument_key`, `trading_symbol`, `instrument_type`, `expiry`, `strike`, `option_type`, `lot_size`, `tick_paise` (int; vendor `tick_size` in rupees maps to `tick_paise` by ×100 and must be a whole number), `listing_date` nullable, `first_observed_at`, `valid_from`, `valid_to` nullable, `source`, `source_version`, `observed_at`, `revision`, `quality_flags`. If no reliable listing date exists, derive `first_observed_at` from the first candle for that contract and do not allow selection before it. `first_observed_at` is an observation bound, not proof of official listing date.

Use a separate source-observation table if vendor metadata revisions must be retained. Contract selection must resolve a single valid contract at the decision time. If multiple candidates exist or no contract is valid, reject the intent and log the reason. Do not replace a missing strike with a nearby strike without a strategy-declared fallback policy; v1 default is **no substitution**.

Lot size and tick_paise are effective-dated. Historical positions and fees use the contract values valid for the trade date, not current metadata.

## 7. Dataset and schema versioning

For every revisioned canonical dataset, revision identity is `(logical_key, ts_start, revision)` and must be globally unique within that dataset. Active identity is `(logical_key, ts_start)` and must be unique among rows selected by the published manifest. Manifest-resolved views expose `is_active`; this is a derived selection flag, not a mutable update to old immutable files.

Each canonical dataset has a `dataset_manifest.json` containing:

- `dataset_id`, logical dataset name, schema version, canonicalization code version;
- source names and source schema versions;
- created/updated timestamps, calendar version, time zone/session policy;
- partition file list, row counts, min/max timestamps, null/quality counts;
- SHA-256 content hash per file and aggregate manifest hash;
- parent manifest IDs for derived datasets;
- revision/correction notes.

Dataset revisions are immutable. Appending a day produces a new manifest that may reference unchanged prior partitions. Corrected historical partitions create new file revisions and a new manifest; old run manifests continue to reference the old manifest. Never invalidate historical runs by mutating the dataset behind their IDs.

Schema changes: add nullable fields where possible; preserve raw payloads; bump schema version for incompatible semantic/type changes; write explicit migrations and test old v1/v2/v3 snapshot fixtures. Unknown fields should be preserved in raw source and surfaced as decoder diagnostics.

## 8. Quality controls and migration

Required audits before the backtest phase:

1. Inventory option candles: rows, distinct contracts/expiries, date coverage, strikes per session, duplicates, missing minutes, zero-volume/flat bars, OHLC violations, OI null/zero transitions, lot-size consistency and symbol/key consistency.
2. Reconcile 1m underlying coverage against the official calendar; explicitly investigate the 2026-02-12/16 gaps, recurring 15:29 omissions in Feb–Mar 2026, isolated gaps, and Saturday 2026-02-21.
3. Derive all higher intraday timeframes from canonical 1m and compare vendor files as a checksum. Do not treat “no gaps within active days” as proof that whole days are present.
4. Snapshot capture audit: 71,617 captures across 110 collected trading days were reported in a previous audit and are stale until M3-01 recounts them, with late starts/gaps/early stops; preserve real capture times. Do not infer full 30-second coverage.
5. Snapshot schema migration: map v1/v2/v3 into nullable superset schema; preserve `schema_version`, source file and field-presence mask. Observed bid/ask and IV/Greeks coverage differ by schema version; never backfill unobserved Greeks.
6. Preserve IV/Greeks at float32 or float64. The reviewed sample suggests IV quantization consistent with float16; verify against raw files before asserting the cause.
7. Use an idempotent staging → validate → publish pipeline. Duplicate reruns must not duplicate canonical rows.
8. Produce `data_eligibility` per `(session, contract, interval)` with `status` = `ELIGIBLE`, `ELIGIBLE_WITH_WARNINGS` or `INELIGIBLE`, plus stable reason codes. Minimum checks: missing bars, stale observations, invalid OHLC, duplicate active keys, invalid contract validity, insufficient feature warm-up and flat bars. A strategy/run declares which warning codes block entries. `INELIGIBLE` blocks new entries; it never disables monitoring of an already-open position. Store audit version, input manifest hash and policy version with every result.
9. Snapshot timestamps with no timezone are currently assumed to be `Asia/Kolkata`; keep this as a `VERIFY` item against candle times/source docs. Audit option-candle history start and strike coverage by expiry/session before Phase 2.
10. Source-semantics audit table: Authoritative contract is defined in §11. Every field × source must record meaning, unit, observation type, availability time, null/zero/reset behavior, permitted uses, verification evidence and status. Rows remain `VERIFY` until empirical evidence is recorded under M3-08.

A reconstructed chain must expose the observed contract set, missing contracts relative to the known contract master/universe, source tier, latest source age and coverage/quality flags. Reconstruction is not a claim that a complete historical chain was observed.

## 9. DuckDB and query contracts

- Use DuckDB for analytical scans, window functions and point-in-time `ASOF JOIN` operations over canonical Parquet.
- Every as-of join declares join direction and maximum staleness; do not align a future observation backward in time.
- Filter partitions before wide joins; select only needed columns; expose query plans and scan bytes in profiling mode.
- One DuckDB connection per process; no shared multi-process writer to a DuckDB database file.
- Postgres holds metadata and operational transactions, not bulk candle history.
- DuckDB multi-threaded floating-point aggregations may differ in the last bits. If byte-identical artifacts are required, use integer money, ordered aggregation or `threads=1`; otherwise define numerical tolerances and record DuckDB/thread settings in the run manifest.

## 9.1 Cross-document rule ownership

This document is authoritative for canonical storage paths, table schemas, partitions, normalization, data eligibility and source semantics. Execution treatment of `is_flat_bar`, stale bars and fills is authoritative only in `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md` §4. Production host and research synchronization are authoritative in `QUANTVIEW_MASTER_SPEC.md` ADR-015; process boundaries and worker responsibilities are authoritative in `QUANTVIEW_MASTER_SPEC.md` ADR-014. Single-writer ownership across all paths is defined authoritatively in this document at §11.5.

## 10. Data-status labels

- `DESIGNED`: target schema/layout decided.
- `IMPLEMENTED`: ingestion/schema code exists and has been inspected.
- `TESTED`: schema, invariants and failure cases passed automated tests.
- `VERIFIED`: source semantics or external facts checked against an authoritative source or documented empirical reconciliation.

A dataset may be implemented but not verified. Example: option candle OI/volume fields may be present (`IMPLEMENTED`) while their economic units/meaning remain `VERIFY` and must not be represented as `VERIFIED`.


## 11. Binding source-semantics audit contract

The source-semantics table is a required M3 artifact at `reports/source-semantics.md` and must be completed before G1. It is not optional documentation. Every row records source, field, meaning/unit, observation type, event/availability time, null/zero/reset behaviour, permitted use, evidence, and status.

| Field × source | Meaning/unit | Observation type | Availability time | Null/zero/reset rule | Permitted use before verification | Status/evidence |
|---|---|---|---|---|---|---|
| Underlying candle `volume` / Upstox historical candle | Source emits 0 in the known index sample; it is **not a usable measurement** unless semantics prove otherwise | Interval field, semantic ambiguity | Bar close | Preserve explicit source zero but mark `NOT_A_MEASUREMENT` for index-volume semantics; never use as evidence of no trading | Display/provenance only; not a liquidity signal | `VERIFY` |
| Underlying candle `oi` / Upstox historical candle | Source emits 0 in known index sample; not a usable index OI measurement | Interval field, semantic ambiguity | Bar close | Preserve raw zero with quality flag; not a real measurement | Display/provenance only | `VERIFY` |
| Option-candle `volume` | Contracts/lots/units and bar aggregation semantics unknown until audit | Interval aggregate or vendor-defined field | Bar close | Do not infer units; distinguish true zero from synthetic/flat bar | Display and non-volume-dependent OHLC simulation only; block volume/liquidity rules | `VERIFY` |
| Option-candle `oi` | Snapshot/end-of-minute/cumulative semantics unknown | Interval aggregate or snapshot, pending evidence | Bar close | Preserve null/zero transitions and flags; never forward-fill silently | Display/provenance only until verified | `VERIFY` |
| Snapshot `oi`, `volume`, `chng`, `chng_oi`, `prev_oi` | Units, baselines, sign, reset and timestamp reference require source/schema audit | Snapshot | `received_at` is availability time | Missing fields are null, not zero; preserve capture schema and field-presence mask | Visualize as observed data with caveat; block signal use until verified | `VERIFY` |
| Vendor snapshot IV/Greeks | Confirm IV fraction vs percent; Greeks scaling/time units; theta per day/year; vega per 1% or 100% vol | Snapshot/model vendor field | `received_at` | Keep `_observed`; no conversion without recorded rule | Display labelled observed value; do not compare/model-calibrate until units verified | `VERIFY` |
| WebSocket `volume_traded_today` | Cumulative or other vendor semantics, reset boundary and unit unknown until fixtures | Cumulative/stream update, pending evidence | `ts_recv` and verified `ts_event` separately | Derive bar volume only from validated nonnegative deltas; handle resets/session boundary explicitly | Raw capture only until semantics verified | `VERIFY` |
| Snapshot naive timestamp | Original examples omit offset; assumed `Asia/Kolkata` only as a normalization hypothesis | Snapshot timestamp | Capture receive time governs availability | Preserve original string; record timezone assumption and compare to candle/feed times | Use `received_at` for causal availability; normalized source time remains flagged | `VERIFY` |
| Expired option candle history/strike coverage | Start date, endpoint retention and contract universe coverage unknown | Historical source | Vendor timestamp plus receipt time | Missing contracts/minutes remain missing; no substitution | Eligible only where coverage report permits | `VERIFY` |
| Expiry settlement reference and exercise charges | Official reference, settlement event and charge basis need dated official evidence | Settlement event | Only at authoritative settlement availability | Missing settlement price -> `UNSETTLED` plus run warning; do not substitute last candle | No realistic settlement claim | `VERIFY` |
| VIX/futures/rates/dividends | Endpoint coverage and sources not yet established | Dataset/assumption series | Source-specific as-of | Assumptions versioned, never silently treated as observed | Only when source tier is declared | `VERIFY` |

### 11.1 `data_eligibility` dataset

One row per `session_date × contract_id × interval × dataset_manifest_hash`:

- `session_date`, `contract_id` nullable for underlying-only intervals, `interval`, `manifest_hash`
- `status`: `ELIGIBLE | ELIGIBLE_WITH_WARNINGS | INELIGIBLE`
- `reason_codes`: stable array of codes including `MISSING_BARS`, `STALE_DATA`, `INVALID_OHLC`, `DUPLICATE_ACTIVE_KEY`, `CONTRACT_INVALID`, `INSUFFICIENT_WARMUP`, `FLAT_BAR`, `SOURCE_SEMANTICS_UNVERIFIED`, `INCOMPLETE_CAPTURE`
- `checked_at`, `audit_version`, `details_ref`

Eligibility is point-in-time and versioned. An ineligible contract/session blocks **new entries**. It never disables monitoring of an already-open position: use last valid mark with `STALE` flag, continue exits/risk checks, and after `max_stale_minutes` force exit at next valid open with worst-case slippage. If no valid observation exists before session end, mark from last valid price with run `WARNING`.

### 11.2 Required additional datasets

- `india_vix`: source, source version, OHLC, timestamp/availability and quality flags; availability remains `VERIFY`.
- `nifty_futures_candles`: contract ID, expiry, OHLC, volume/OI source fields; expired-instrument API availability is `VERIFY`.
- `rates_dividends`: versioned assumption series for model Greeks; each point has effective date, source/assumption label, unit, and manifest hash.
- `fee_schedule`: effective-dated and versioned per-charge rates/formulas, source URL/document, effective start/end, rounding rule, verification status; run manifest pins its exact version.
- `data_eligibility`: as defined above.
- `trading_calendar`: versioned Parquet manifest plus Postgres index row.
- `option_snapshot_captures`: one row per actual response/file; do not manufacture a 30-second grid.

### 11.3 Revision, active-row and manifest rules

- Revision key `(logical_key, ts_start, revision)` is globally unique.
- Active key `(logical_key, ts_start)` is unique among records selected by a manifest. Do not rely on a mutable `is_active` field without the manifest selection rule; if materialized, it must be reproducible from the manifest.
- The manifest file is authoritative. Postgres holds only `(id, path, sha256, status)` and other index metadata, not a second mutable copy of the manifest.
- Publish: write to `staging/`, validate schema/counts/hash, atomically rename to immutable target, then update manifest pointer. If publishing fails, the old manifest pointer remains valid.
- `ws_quotes.message_id` is deterministic for dedupe: SHA-256 of `connection_id`, sequence number where available, and payload checksum. Preserve `collector_sequence_number` as a separate nullable field.
- Keep raw captures immutable. Normalize snapshots v1/v2/v3 to a nullable superset while retaining original schema version, raw path and field-presence mask.
- Capture compaction preserves each `snapshot_id` and original `received_at`. Never interpolate gaps or merge separate captures into a fabricated continuous series.

### 11.4 Reproducibility and numerical determinism

A byte-identical artifact requires deterministic ordering, exact integer/Decimal money, fixed schema/code/config versions and pinned input manifest hashes. DuckDB multi-threaded floating-point aggregation can differ in final bits. For byte-identical outputs, use integer/ordered aggregation or `threads=1`; otherwise declare a tolerance comparison and record DuckDB thread count and environment in the run manifest.

### 11.5 Dataset writer ownership matrix (authoritative platform contract)

This matrix is the sole authoritative definition of single-writer boundaries across all files and stores in QuantView. All processes, services, and tasks must obey these boundaries:

| Dataset/store | Single writer | Readers | Publish/transport |
|---|---|---|---|
| Raw REST snapshot payloads | `collector_snapshot` | `worker_data`, audit tools | Immutable raw file + capture manifest |
| Raw WebSocket segments | `collector_ws` | replay, decoder, audit | `.partial` → batched fsync → final rename; manifest lists finalized segments only |
| Historical expired API payloads | `backfill` | `worker_data` | Checkpointed raw archive and checksums |
| Canonical Parquet datasets | `worker_data` / designated dataset publisher | API, `worker_compute`, `live_daemon` read-only | Stage → validate → atomic publish → manifest pointer |
| Feature cache, if enabled | `worker_compute` cache publisher | API, workers | Content-addressed write-once; losing concurrent writer discards |
| Run manifest and Parquet artifacts | Run-owning worker | API, report tools | Manifest file authoritative; Postgres row is index |
| Postgres account/orders/fills/ledger | `api` commands / `live_daemon` through transaction service; append-only ledger writer owns events | API, workers, projections | DB transaction and idempotency keys |
| Calendar/contract master | `worker_data` | all consumers read-only | Versioned dataset manifest |
| Live transport | `collector_ws` publishes after M7-01; before then raw-only | `live_daemon`, API/UI | `FrameBus`; Redis adapter only if later justified |

### 11.6 Measured inventory facts and known leads (citing `ops/inventory.md`)

Authoritative physical inventory measurements from `ops/inventory.md` (completed 2026-10-17 under M0-01) supersede prior estimates:
- **1m Underlying Candles:** Exactly 432,967 historical rows in `historical/candles/index/nifty/1m/nifty.csv` plus 18,985 rows across 57 live daily files in `live/candles/index/nifty/1m/` (this explains the old 451,952 figure: 432,967 + 18,985 = 451,952). One corrupted line detected at line 432593 (`2026-10-08 0`). Conflicting duplicate timestamps detected on 2026-01-28 between historical and live files; exactly 19 trading sessions are present only in the live daily files.
- **Snapshot Captures:** Exactly 78,535 snapshot CSV files across 121 unique trade dates (2026-01-20 through 2026-10-09). Actual schema version counts: v1 = 1,036 files; v2 = 8,770 files; v3 = 68,720 files. 5 null-byte corrupted files and 4 zero-byte empty files detected.
- **Expired-Option Candles:** Audited inventory (M0-01) confirmed that only one sample day (2025-04-24) exists on disk under `Data/historical/candles/options/2025-04-24/`. Bulk historical coverage is not yet downloaded and will be ingested via the approved Upstox workflow (M0-05, M0-09, M2-07, M3-05). No spec text assumes the bulk dataset exists.
- **Historical Interval Files:** 3m 144,428; 5m 86,728; 15m 28,944; 1h 8,232; 4h 2,352; 1d 1,410 rows. Reported range begins 2022-01-03 for intraday and 2021-02-01 for daily; last date 2026-10-08. (Non-binding lead; to be reconciled against derived 1m in M3-07).
- **Empirical Audit Lead — Lot Size Evolution (Non-binding):** Sample rows show quantities as exact multiples of 75 in early sample (April 2025 candle volume 75, OI 31,200 = 416 × 75) and 65 in late sample (July 2026 snapshot OI 2,629,705 = 40,457 × 65, volume 310,245 = 4,773 × 65). This provides a strong lead that vendor quantities/OI are expressed in units rather than contracts, and that lot sizes changed from 75 to 65. M3-03 must establish official effective-dated lot sizes from NSE circulars and contract-master history rather than hardcoding assumptions.
- **Measured Interval Session Coverage (citing `ops/inventory.md`):** Measured unique calendar dates across historical index files show exact date counts rather than naive division estimates: 1m historical, 3m, 5m, and 15m each cover exactly 1,154 unique trading dates (2022-01-03 through 2026-10-08); 1h and 4h each cover 1,176 unique dates (a 22-day difference of earlier/extra sessions); and 1d covers 1,410 unique dates (earliest date 2021-02-01). M3-01/M3-07 reconcile these measured session sets against official NSE exchange trading calendars.
- **Supporting Datasets Ownership:** Availability, inventory, and canonicalization of supporting series (`india_vix`, `nifty_futures_candles`, `rates_dividends`) are owned under dedicated task M3-12. Unavailable sources remain null and block dependent Greek models or VIX filters rather than fabricating values.
- Known audit leads (non-binding): gaps around 2026-02-12/16, recurring 15:29 omissions in Feb–Mar 2026, a reported Saturday 2026-02-21 underlying row, Saturday 2026-07-04 snapshot collection, and a reported 2026-04-13 expiry. Each is an unverified lead, not an assertion of a valid exchange session or data defect until audited.

### 11.7 Specific historical coverage leads and inventory reconciliation

These remain **reported audit leads** (clearly labelled non-binding) pending full verification under M3-01 and M3-07 against official exchange calendars:

| Dataset | Reported lead | Required treatment |
|---|---|---|
| Underlying 1m | Missing 3 bars on 2022-03-07 (10:22–10:24); single-bar gaps on 2024-12-12 09:42, 2025-03-25 10:42, 2025-04-04 11:57, 2025-04-23 10:36 | Recount and compare to official session calendar/source response; do not fill gaps |
| Underlying 1m | Repeated missing 15:29 bar reported on 2026-02-04, 02-05, 02-06, 02-10, 02-11, 02-13, 02-17, 02-25, 02-26, 02-27, 2026-03-02, 03-04, 03-05, 03-06 | Determine whether source endpoint omits final minute by design or collection has gaps; preserve as quality flags |
| Underlying 1m | 2026-02-12 reported 96 missing bars from 13:54–15:29; 2026-02-16 reported 72 missing bars including 09:15–10:25 and 15:29; 2026-02-23 reported 57 missing bars 14:33–15:29 | Treat those sessions as potentially ineligible until source/calendar reconciliation |
| Underlying 1m | 2026-02-21 reported 374 missing bars from 09:16–15:29 | Confirm whether session was officially open/special or the row is bad data; do not infer from weekday alone |
| Snapshot capture | Prior reports showed late starts, early ends, gaps and missing collection days across expiry windows (e.g. 2026-01-20 10:15:54 first capture, 62s gap; 2026-02-16 late start at 10:25:36) | Preserved exactly per `ops/inventory.md`. Recompute expiry × session coverage; never assume a complete chain from 30s cadence |
| Expiry master | 2026-04-13 appeared as a Monday expiry in prior reports | Check official historical expiry schedule and calendar; do not hard-code a weekday correction |

The inventory report states that no missing candles were detected **within active trading days** for 3m/5m/15m/1h/4h/1d at the time, but this does not prove whole-session coverage and does not override the rule that those intraday intervals are derived from canonical 1m. Recompute after the source inventory and calendar audit.

### 11.8 Source-handling, quarantine and live daily file rules

- **Live daily index candle registration and precedence:** Live daily index candle files (`Data/live/candles/index/nifty/1m/nifty_YYYY-MM-DD.csv`) are a registered source alongside historical `nifty.csv`. On overlap dates, normalization compares timestamps and values. If identical, the record is deduplicated. If conflicting duplicate timestamps exist (such as on 2026-01-28), both conflicting records are quarantined with reason code `DUPLICATE_TIMESTAMP_CONFLICT`; the normalizer must never choose one silently.
- **Corrupted and empty file quarantine:** Snapshot files that are 0-byte (empty), contain null bytes (such as the 5 identified in `ops/inventory.md`), or contain truncated CSV lines (such as line 432593 of `1m/nifty.csv`) are moved to `quarantine/` with structured metadata and stable reason codes (`CORRUPT_NULL_BYTES`, `EMPTY_ZERO_BYTES`, `TRUNCATED_LINE`). They are excluded from canonical Parquet tables.
- **Path-derived expiry validation:** Expiry dates derived from directory paths must satisfy `trade_date <= expiry`. Path parsers must handle unpadded month/day folder names (e.g. `2026-02-3`). Files violating the date ordering or path format are quarantined with reason code `INVALID_EXPIRY_PATH`.
