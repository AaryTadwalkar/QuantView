# QuantView Data Architecture Specification

**Document purpose:** Define the data architecture and implementation
decisions for QuantView.\
**Status:** Architectural baseline; implementation details marked as
such must be validated against the live provider and real dataset.\
**Provider currently tested:** Upstox\
**Canonical historical file format:** Parquet\
**Raw archive format:** JSON responses, preferably JSON Lines /
compressed JSON Lines where appropriate\
**Analytical query engine:** DuckDB\
**Transactional database:** PostgreSQL

------------------------------------------------------------------------

## 1. Decisions at a glance

  -----------------------------------------------------------------------
  Concern                             Decision
  ----------------------------------- -----------------------------------
  Permanent historical candle         Long format: one row per
  representation                      instrument/contract, timestamp and
                                      interval

  Canonical historical storage        Normalized Parquet files

  Raw source archive                  Original provider response
                                      payloads, stored separately and
                                      kept immutable

  Query historical files              DuckDB

  Application and transactional state PostgreSQL

  Canonical normalized row order      `timestamp`, `expiry`, `strike`,
                                      `option_type` (where those fields
                                      apply)

  Fetch one contract for a backtest   Filter by `instrument_key`, time
                                      range and interval using DuckDB

  ATM/ITM strategy                    Load underlying series and only the
                                      selected contract(s); no all-strike
                                      wide matrix required

  Cross-strike strategy               Optionally construct
                                      timestamp-aligned wide matrices in
                                      memory

  Missing data                        Preserve as missing; never turn
                                      missing prices into zero

  Forward-filled price                Allowed only in an explicitly
                                      labelled analytical series; not an
                                      observed execution price

  Current option-chain API            Capture snapshots over time if
                                      historical snapshots are required;
                                      the endpoint itself is not a
                                      historical snapshot query

  CSV                                 Inspection, debugging and exchange
                                      with small samples; not the
                                      canonical long-term store
  -----------------------------------------------------------------------

## 2. Storage architecture

QuantView uses different storage components for different workloads.
They are complementary, not interchangeable.

-   **Raw archive:** preserves what the provider returned, before
    QuantView transforms it.
-   **Normalized Parquet:** stores validated records in QuantView's
    consistent schemas.
-   **DuckDB:** queries Parquet files and prepares data for
    research/backtesting.
-   **PostgreSQL:** stores relational and transactional application
    state such as strategy definitions, job metadata, paper orders,
    positions, ledger entries, risk configuration and audit events.
-   **In-memory computation:** pandas/NumPy or another measured
    implementation creates the data shape required by the strategy.

PostgreSQL is not the primary store for the bulk historical OHLC candle
archive. Parquet is not a substitute for PostgreSQL's transactional
ledger. DuckDB is the analytical query engine, not the canonical data
archive.

### 2.1 Data flow

``` text
Ingestion worker
    |
    +--> Raw response archive
    |
    v
Normalize + validate
    |
    +--> Preliminary validation report
    |
    v
Write normalized Parquet to staging
    |
    v
Verify outputs and finalize dataset artifacts
    |
    v
Publish final manifest referencing verified artifacts
```

## 3. What is `raw/` and what is `normalized/`?

These folders have different purposes. Do not use them interchangeably.

### 3.1 `raw/`: provider source archive

`raw/` contains the original response payload from the API, before
renaming fields, changing types, adding derived flags, deduplicating,
sorting or pivoting.

Recommended contents:

-   Raw response body for each API request, such as the JSON response
    from the expired historical-candle endpoint.
-   Raw option-contract metadata response.
-   Raw expiry-list response.
-   Raw option-chain snapshot response.
-   Request metadata needed to interpret the response: endpoint,
    parameters (excluding secrets), collection timestamp, HTTP status,
    provider status, ingestion run ID and response checksum.
-   Error response bodies when safe and useful for diagnosis; never
    store authorization headers or tokens in logs.

**Recommended format:** JSON or JSON Lines. For many responses, one JSON
file per request/run or JSONL with one record per response plus metadata
is reasonable. Compression such as gzip can reduce space. Choose and
document one format for each raw dataset. The raw archive should
preserve the original provider fields and nested structures.

Raw data is not necessarily directly query-ready. Its purpose is
reproducibility, auditability and the ability to re-run normalization
without calling the API again.

### 3.2 `normalized/`: canonical QuantView datasets

`normalized/` contains records transformed into documented QuantView
schemas. Values are typed, timestamps parsed consistently, contract
metadata associated, and validation results recorded. Raw provider
fields should not be silently changed; preserve the source archive and
record normalization/schema versions.

Recommended datasets:

  ---------------------------------------------------------------------------
  Dataset                     Contents                Grain / one row
                                                      represents
  --------------------------- ----------------------- -----------------------
  `spot_candles/`             NIFTY index/underlying  One underlying +
                              historical candles      timestamp + interval

  `option_candles/`           Historical individual   One contract +
                              option-contract candles timestamp + interval

  `contract_reference/`       Contract identity and   One contract metadata
                              attributes              version

  `option_chain_snapshots/`   Captured option-chain   One snapshot
                              state normalized from   timestamp + expiry +
                              the chain response      strike + option type

  `manifests/` (sibling folder)   Dataset/run metadata, source and interval,
                                schema version, coverage, row counts,
                                validation outcomes, checksums and failures.
                                One manifest per defined dataset partition
                                or ingestion run.
          
  ---------------------------------------------------------------------------

**Recommended normalized file format:** Parquet. It is typed, columnar
and suitable for analytical filtering. CSV may be used during the
current inspection stage but should not be the canonical bulk store once
the schema is validated.

### 3.3 Example folder layout

``` text
Data/
├── raw/
│   └── upstox/
│       ├── expiries/
│       ├── option_contracts/
│       ├── spot_candles/
│       ├── expired_option_candles/
│       └── option_chain_snapshots/
├── normalized/
│   ├── spot_candles/
│   ├── option_candles/
│   ├── contract_reference/
│   └── option_chain_snapshots/
├── manifests/
│   ├── ingestion_runs/
│   ├── coverage/
│   ├── validation/
│   └── failures/
└── research/
    └── backtest_artifacts/
```

The exact folder and partition names can be adjusted to match the
repository, but the raw/normalized distinction must remain clear.
### 3.4 Sidecar manifests: dataset metadata and provenance

A sidecar manifest is a small metadata file stored alongside or referenced by a normalized dataset. It describes the dataset or ingestion batch without repeating identical metadata in every market-data row.
**Safe publication and recovery:** Write normalized outputs to a staging location first. Validate the files, row counts, coverage and checksums before publishing them as a finalized dataset version. Publish the final manifest only after the referenced artifacts have been verified. If ingestion fails before finalization, retain the run as `FAILED` or `PARTIAL` in ingestion metadata and do not expose it as a complete dataset. Use atomic rename or an equivalent storage-specific publication mechanism where supported. Preserve the previous valid dataset version until the replacement is successfully published.

**Architectural decision:** QuantView uses a hybrid metadata model.

- **Data columns** hold values needed for row-level identity, filtering, joins and calculations.
- **Sidecar manifests** hold metadata that applies to a dataset, partition or ingestion run.
- **PostgreSQL** may store ingestion-job state and a reference to the manifest or artifact, but it is not the bulk historical-candle store.
- **Raw response archives** remain the source evidence. A manifest describes the ingestion and normalization process; it does not replace the raw payload.

#### Metadata placement rules

| Field | Default location | Rule |
|---|---|---|
| `instrument_key` | Normalized option-candle row | Required for identifying and retrieving the exact option contract. A dataset containing multiple contracts cannot use one manifest-level key as a substitute. |
| `underlying` | Row column when useful; otherwise manifest/reference data | Store it as a column when row-level filtering or joins benefit from it. A manifest value is sufficient only when the dataset or partition has one known underlying. |
| `interval` | Existing column for mixed-interval data; otherwise manifest | Keep the current `interval` column in the option-candle prototype. A manifest may declare the expected interval and validate that the records match it. |
| `source` | Row column when records may have different sources; otherwise manifest | Keep the current option-candle `source` column. The manifest records the source endpoint/provider and ingestion context for the batch. |
| `ingested_at` | Manifest/run metadata by default | Record the ingestion time for the run or dataset. Add a row-level ingestion timestamp only when individual records can arrive at different times or row-level lineage is required. |
| `schema_version` | Manifest | Version the normalized schema used to write the dataset. Do not repeat it in every row unless a specific mixed-version storage requirement is introduced. |

These are default placement rules, not a prohibition on columns. QuantView must choose a consistent policy for each dataset and validate it during ingestion.

#### Example sidecar manifest

A manifest may be stored as JSON alongside a normalized Parquet partition or in `Data/manifests/`, with a stable reference connecting it to the relevant dataset.

```json
{
  "manifest_version": "1.0",
  "dataset": "option_candles",
  "provider": "upstox",
  "source": "upstox_expired_historical_candle",
  "underlying": "NIFTY",
  "interval": "1minute",
  "schema_version": "1.0",
  "format": "parquet",
  "ingestion_run_id": "run-2026-10-13-example",
  "ingested_at": "2026-10-13T10:30:00+05:30",
  "coverage": {
    "start_timestamp": "2025-04-24T09:15:00+05:30",
    "end_timestamp": "2025-04-24T15:29:00+05:30"
  },
  "row_count": 0,
  "validation_status": "REVIEW_REQUIRED",
  "raw_response_checksums": [],
  "normalized_artifacts": []
}
```

The values above are illustrative. The ingestion implementation must populate actual timestamps, row counts, checksums, artifact references and validation status; it must not copy the example values as real metadata. `row_count: 0` and the empty arrays are placeholders, not a claim that a real dataset contains no rows or raw responses.

For datasets spanning multiple contracts or partitions, record the applicable contract/partition scope or list the artifact references explicitly. Do not describe a multi-contract dataset as if it contained only one instrument.

#### Manifest requirements

Each manifest should identify the dataset or ingestion run unambiguously and, where applicable, record:

- Provider, endpoint/source and request parameters excluding credentials.
- Ingestion run ID and ingestion timestamp.
- Normalized schema version and output format.
- Actual coverage range, row count and relevant partition identifiers.
- Validation status and a reference to the validation report.
- Raw response checksums and normalized artifact paths or identifiers.
- Failures, partial-coverage information and reconciliation notes.

Manifests must be updated or replaced through a documented ingestion procedure. Do not silently edit a manifest in a way that makes it appear that an earlier ingestion produced data or validation results that were added later. Preserve run history where auditability and reproducibility require it.

#### How manifests are used

1. The ingestion worker writes raw provider responses and records the ingestion run.
2. It normalizes and validates the records, then writes the Parquet output.
3. It writes a manifest containing the actual output paths, schema version, coverage, row count, checksums and validation result.
4. The data-loading layer can inspect the manifest before a backtest and reject incompatible schema versions, unexpected intervals or insufficient coverage.
5. A backtest records the dataset/manifest references it used so the input data can be identified when the result is reproduced.

A manifest improves traceability and validation; it does not prove that the provider's data is correct or complete. QuantView must still validate the actual records and timestamp coverage.


### 3.5 What normalization does

For example, Upstox returns a candle as an array:

``` json
[
  "2025-04-24T09:23:00+05:30",
  3997.8,
  3997.8,
  3962.1,
  3962.25,
  75,
  31200
]
```

Normalization maps the positions to named columns:

``` text
timestamp, open, high, low, close, volume, open_interest
```

For option candles, QuantView also joins the contract metadata to add
`instrument_key`, `trading_symbol`, `expiry`, `strike`, `option_type`
and other reference fields. The raw array remains preserved in `raw/`.

Normalization may parse timestamps and cast values to typed columns, but
it must not manufacture missing candles, replace missing prices with
zero, or silently alter source values.

------------------------------------------------------------------------

## 4. Canonical normalized schema: NIFTY underlying candles

The user's current underlying CSV has these columns:

``` text
timestamp,open,high,low,close,volume,open_interest
```

Example rows supplied from the existing dataset:

``` csv
timestamp,open,high,low,close,volume,open_interest
2022-01-03 09:15:00+05:30,17387.15,17438.4,17387.15,17428.9,0,0
2022-01-03 09:16:00+05:30,17428.4,17451.45,17428.4,17450.55,0,0
2022-01-03 09:17:00+05:30,17450.05,17459.55,17442.05,17457.7,0,0
```

This is the schema to preserve for compatibility with the current
dataset. The seven-position Upstox candle response is timestamp, open,
high, low, close, volume and open interest. The API supplies those
fields even if the user's NIFTY index CSV reports volume and open
interest as zero.

**Important interpretation:** the presence of `volume` and
`open_interest` fields in the generic candle response does not establish
that these values are meaningful for a cash index. Do not reinterpret or
replace the current zeros without validating the source and instrument
semantics. Keep the source values and document their limitations.

The normalized underlying-candle dataset must retain the existing seven-column schema for compatibility:

`timestamp,open,high,low,close,volume,open_interest`

Dataset-level metadata should be recorded in a sidecar manifest where possible:

- `instrument_key`: the exact underlying instrument identity, such as the configured NIFTY index key.
- `underlying`: the canonical QuantView name, such as `NIFTY`.
- `interval`: the declared candle interval, such as `1minute`.
- `source`: the provider and endpoint or source identifier.
- `ingested_at`: the ingestion-run timestamp.
- `schema_version`: the normalized dataset schema version.

These fields do not all need to become additional columns in the underlying-candle Parquet file. If a dataset or partition contains a single underlying, interval and source, its manifest can declare those values. If the dataset mixes values that must be filtered or joined per row, the relevant fields must be explicit columns or otherwise unambiguously associated with each record.

The manifest must describe the actual dataset written. It must not be used to infer that volume or open-interest values are meaningful when the source instrument does not provide meaningful values for those fields.

The existing CSV remains an input/source artifact. Normalization can write the canonical Parquet dataset and its manifest without destructively rewriting the original CSV.



------------------------------------------------------------------------

## 5. Canonical normalized schema: individual option candles

**Grain:** one row per option contract, timestamp and interval.

The extracted CSV already uses this long-form shape:

``` text
timestamp,instrument_key,trading_symbol,expiry,strike,option_type,lot_size,open,high,low,close,volume,oi,source,interval
```

This is the current normalized prototype schema. Preserve these field
names for compatibility unless a deliberate schema migration is made. In
particular, the source field is named `oi` in the current option CSV; do
not rename it silently. The underlying candle dataset currently calls
its final field `open_interest`. A future schema version may standardize
the name, but that requires an explicit migration and compatibility
plan.

  ------------------------------------------------------------------------------------
  Column                  Type                    Meaning
  ----------------------- ----------------------- ------------------------------------
  `timestamp`             timezone-aware          Candle time, interpreted in
                          timestamp               `Asia/Kolkata`

  `instrument_key`        string                  Provider's exact option-contract key

  `trading_symbol`        string                  Human-readable symbol

  `expiry`                date                    Contract expiry

  `strike`                integer/numeric         Strike price

  `option_type`           enum/string             `CE` or `PE`

  `lot_size`              integer                 Contract lot size from contract
                                                  metadata

  `open`                  numeric                 Candle open

  `high`                  numeric                 Candle high

  `low`                   numeric                 Candle low

  `close`                 numeric                 Candle close

  `volume`                integer/numeric         Volume returned by provider

  `oi`                    integer/numeric         Open interest returned by provider

  `source`                string                  E.g.
                                                  `upstox_expired_historical_candle`

  `interval`              string                  E.g. `1minute`
  ------------------------------------------------------------------------------------

The current option-candle schema already contains `instrument_key`, `source` and `interval`. Preserve these columns for compatibility and for row-level contract retrieval, filtering and provenance.

Use the sidecar manifest to record dataset/run-level metadata, including `underlying`, `schema_version`, `ingested_at`, the declared interval and source, actual coverage, row count, validation status, checksums and normalized artifact references.

Because the dataset may contain multiple contracts, `instrument_key` must remain attached to each option-candle row. Keep `source` and `interval` as row columns in the current prototype; the manifest should also declare the expected values and ingestion context. This allows validation to detect unexpected mixed sources or intervals instead of silently assuming uniformity.

`schema_version` applies to the normalized dataset or partition by default and belongs in the manifest. Row-level `ingested_at` is optional and should be added only if individual-record ingestion history is required.

### 5.1 Example rows from the user's current CSV

These are actual examples provided by the user, not mock data:

``` csv
timestamp,instrument_key,trading_symbol,expiry,strike,option_type,lot_size,open,high,low,close,volume,oi,source,interval
2025-04-24 09:23:00+05:30,NSE_FO|79196|24-04-2025,NIFTY 20350 CE 24 APR 25,2025-04-24,20350.0,CE,75,3997.8,3997.8,3962.1,3962.25,75,31200,upstox_expired_historical_candle,1minute
2025-04-24 09:24:00+05:30,NSE_FO|79196|24-04-2025,NIFTY 20350 CE 24 APR 25,2025-04-24,20350.0,CE,75,3962.25,3962.25,3962.25,3962.25,0,31200,upstox_expired_historical_candle,1minute
2025-04-24 09:25:00+05:30,NSE_FO|79196|24-04-2025,NIFTY 20350 CE 24 APR 25,2025-04-24,20350.0,CE,75,3962.25,3962.25,3962.25,3962.25,0,31200,upstox_expired_historical_candle,1minute
```

The unchanged close with zero volume is preserved as returned. It may
represent a no-trade interval or provider-specific candle behavior; do
not assume it proves an executable price.

------------------------------------------------------------------------

## 6. Canonical row order: long format sorted by timestamp

The data remains long format. Sort normalized option rows by:

``` python
df = df.sort_values(
    ["timestamp", "expiry", "strike", "option_type"],
    ascending=[True, True, True, True],
).reset_index(drop=True)
```

This gives a time-first layout such as:

  timestamp     strike option_type     close
  ----------- -------- ------------- -------
  09:15          24200 CE                ...
  09:15          24200 PE                ...
  09:15          24250 CE                ...
  09:15          24250 PE                ...
  09:16          24200 CE                ...
  09:16          24200 PE                ...

The example values are placeholders. The actual dataset can have missing
contracts or timestamps.

**Why timestamp first?** It makes visual inspection and chronological
batch processing easier. It does not itself make lookups efficient or
guarantee that all contracts have a candle at every minute. DuckDB
filtering, contract keys and timestamp joins are what make targeted
retrieval efficient.

For stable CE-before-PE order, define an explicit sort rank rather than
relying on alphabetical ordering:

``` python
option_rank = {"CE": 0, "PE": 1}
df["_option_rank"] = df["option_type"].map(option_rank)

df = (
    df.sort_values(
        ["timestamp", "expiry", "strike", "_option_rank"]
    )
    .drop(columns="_option_rank")
    .reset_index(drop=True)
)
```

Use the expiry and instrument key in queries; strike and option type
alone are not globally unique across expiries.

------------------------------------------------------------------------

## 7. How a specific strike/contract is retrieved for backtesting

The backtester should not scan every row in Python for each signal.
DuckDB queries the normalized Parquet dataset by date/time and contract
identity.

Example DuckDB query:

``` sql
SELECT
    timestamp,
    instrument_key,
    expiry,
    strike,
    option_type,
    open,
    high,
    low,
    close,
    volume,
    oi
FROM read_parquet('Data/normalized/option_candles/**/*.parquet')
WHERE expiry = DATE '2025-04-24'
  AND strike = 24200
  AND option_type = 'CE'
  AND timestamp >= TIMESTAMPTZ '2025-04-24 09:15:00+05:30'
  AND timestamp <  TIMESTAMPTZ '2025-04-24 15:30:00+05:30'
ORDER BY timestamp;
```

For production queries, prefer filtering by the exact `instrument_key`
once the strategy's contract selector resolves the intended contract.
The key prevents ambiguity and is the strongest provider-specific
identity.

### ATM/ITM1/ITM2/ITM3 strategies

1.  Query the underlying series for the strategy's date/time range.
2.  At each permitted selection time, apply the configured
    strike-selection rule using only information available at that time.
3.  Resolve the actual contract from the contract-reference dataset.
4.  Query or retrieve that contract's option series.
5.  Keep the selected `instrument_key` attached to each decision and
    trade.
6.  If the selected strike changes, track the new contract as a
    different instrument; do not pretend it is the same option position.
7.  Apply the execution-eligibility rules before allowing a simulated
    fill.

The exact meaning of `ITM1`, `ITM2`, etc. must be defined in strategy
configuration (for example, one/two listed strike steps ITM), not
inferred as a fixed point distance.

------------------------------------------------------------------------

## 8. Layer 2: strategy-dependent computation format

Layer 2 is an in-memory representation prepared from normalized data for
one backtest. It is **not** a second permanent canonical schema.

### 8.1 Single-contract mode

For a strategy that selects ATM/ITM1/ITM2/ITM3 and trades one option at
a time, load:

-   the underlying series;
-   the selected option series;
-   selection/contract identity metadata;
-   any extra data actually required by that strategy.

No matrix containing every strike is needed.

### 8.2 Small multi-contract mode

For a few legs or candidate contracts, use timestamp-aligned long
tables, indexed series, or a small matrix. Choose the simplest
representation that meets performance requirements.

### 8.3 Wide matrix mode

For a strategy that compares many strikes at the same timestamps, build
wide matrices in memory on demand. Example:

  ----------------------------------------------------------------------------
  timestamp     spot_close     24200 CE     24200 PE     24250 CE     24250 PE
                                  close        close        close        close
  ----------- ------------ ------------ ------------ ------------ ------------
  09:15                ...          ...          ...          ...          ...

  09:16                ...          ...          ...          ...          ...
  ----------------------------------------------------------------------------

Build only the fields and contracts needed. Use a structured
contract-to-column mapping or MultiIndex columns. Do not save a huge
wide matrix as the canonical historical dataset.

### 8.4 Missingness and fill rules

-   A missing candle remains missing in the execution-price series.
-   A zero-volume candle is preserved and flagged.
-   Forward-filled values may be used in a separate analytical series
    only if marked as imputed.
-   An imputed price is not an observed executable price.
-   Positive volume alone does not prove that an order could fill at the
    candle close.
-   Execution eligibility depends on the declared fill model, data
    quality, freshness, market/contract state and order rules.

------------------------------------------------------------------------

## 9. Option-chain snapshot schema --- verified against Upstox response

Upstox's documented `GET /v2/option/chain` response has one object per
strike. Each strike object includes:

-   `expiry`
-   `pcr`
-   `strike_price`
-   `underlying_key`
-   `underlying_spot_price`
-   `call_options`
-   `put_options`

Each call/put object contains `instrument_key`, `market_data`, and
`option_greeks`.

The documented `market_data` fields are:

-   `ltp`
-   `volume`
-   `oi`
-   `close_price`
-   `bid_price`
-   `bid_qty`
-   `ask_price`
-   `ask_qty`
-   `prev_oi`

The documented `option_greeks` fields are:

-   `vega`
-   `theta`
-   `gamma`
-   `delta`
-   `iv`
-   `pop`

These fields are documented by Upstox. A particular response can still
contain nulls or omit values; preserve null/missing values rather than
inventing data.

### 9.1 Normalized snapshot table

The API response does not itself include a historical
`snapshot_timestamp` representing when an arbitrary past chain state
occurred. QuantView must attach its own collection timestamp when the
response is received.

**Grain:** one row per
`snapshot_timestamp + expiry + strike + option_type`.

  -----------------------------------------------------------------------
  Column                              Source / meaning
  ----------------------------------- -----------------------------------
  `snapshot_timestamp`                QuantView's timestamp when the API
                                      response was collected

  `underlying_key`                    Upstox response field

  `underlying`                        QuantView canonical name derived
                                      from configured underlying

  `expiry`                            Upstox response field

  `strike`                            Mapped from `strike_price`

  `option_type`                       Derived from `call_options` (`CE`)
                                      or `put_options` (`PE`)

  `instrument_key`                    `call_options.instrument_key` or
                                      `put_options.instrument_key`

  `underlying_spot_price`             Upstox response field

  `pcr`                               Upstox strike-object field;
                                      preserve source semantics and
                                      document its level

  `ltp`                               `market_data.ltp`

  `volume`                            `market_data.volume`

  `oi`                                `market_data.oi`

  `close_price`                       `market_data.close_price`

  `bid_price`                         `market_data.bid_price`

  `bid_qty`                           `market_data.bid_qty`

  `ask_price`                         `market_data.ask_price`

  `ask_qty`                           `market_data.ask_qty`

  `prev_oi`                           `market_data.prev_oi`

  `vega`                              `option_greeks.vega`

  `theta`                             `option_greeks.theta`

  `gamma`                             `option_greeks.gamma`

  `delta`                             `option_greeks.delta`

  `iv`                                `option_greeks.iv`

  `pop`                               `option_greeks.pop`

  `source`                            `upstox_option_chain`

  `ingested_at`                       QuantView ingestion timestamp / run
                                      metadata

  `schema_version`                    Normalized schema version
  -----------------------------------------------------------------------

The fields above are the documented response fields mapped into the
normalized representation. Nullability should be supported at the
storage level because real responses can have unavailable values.

### 9.2 Example source-to-normalized mapping

Source fragment from the documented response shape:

``` json
{
  "expiry": "2025-02-13",
  "pcr": 7515.3,
  "strike_price": 21100,
  "underlying_key": "NSE_INDEX|Nifty 50",
  "underlying_spot_price": 22976.2,
  "call_options": {
    "instrument_key": "NSE_FO|51059",
    "market_data": {
      "ltp": 2449.9,
      "volume": 0,
      "oi": 750,
      "close_price": 2449.9,
      "bid_price": 1856.65,
      "bid_qty": 1125,
      "ask_price": 1941.65,
      "ask_qty": 1125,
      "prev_oi": 1500
    },
    "option_greeks": {
      "vega": 4.1731,
      "theta": -472.8941,
      "gamma": 0.0001,
      "delta": 0.743,
      "iv": 262.31,
      "pop": 40.56
    }
  }
}
```

This is an example from the official documentation, not a claim about
current market values. Normalize it into a CE row for that strike;
normalize `put_options` into a separate PE row. Attach the actual
collection timestamp when capturing a live/current response.

------------------------------------------------------------------------

## 10. Contract-reference dataset

Maintain a normalized contract-reference dataset built from the relevant
option-contract endpoint response.

Suggested fields:

  Column             Description
  ------------------ ------------------------------
  `instrument_key`   Provider contract identity
  `underlying_key`   Provider underlying identity
  `underlying`       QuantView canonical name
  `trading_symbol`   Provider symbol
  `expiry`           Expiry date
  `strike`           Strike
  `option_type`      CE/PE
  `lot_size`         Contract lot size
  `tick_size`        Tick size
  `source`           Endpoint/source
  `ingested_at`      When metadata was collected
  `schema_version`   Normalized schema version

Only persist fields actually returned by the endpoint or derived through
a documented mapping. Additional provider metadata can be retained in
raw responses. If contract attributes change over time, retain
versions/effective dates where needed for historically correct
backtests.

------------------------------------------------------------------------

## 11. API endpoint reference

The APIs below support the current design. API endpoints supply data;
they do not dictate the canonical storage format.

  -----------------------------------------------------------------------------------------------------------------------------------------------
  Need                                Upstox endpoint
  ----------------------------------- -----------------------------------------------------------------------------------------------------------
  Discover expired expiry dates       `GET /v2/expired-instruments/expiries`

  Get expired contracts for an expiry `GET /v2/expired-instruments/option/contract`

  Fetch expired option candles        `GET /v2/expired-instruments/historical-candle/{expired_instrument_key}/{interval}/{to_date}/{from_date}`

  Fetch NIFTY underlying candles      `GET /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}`

  Get active option contracts         `GET /v2/option/contract`

  Get current option chain            `GET /v2/option/chain`
  -----------------------------------------------------------------------------------------------------------------------------------------------

Use the provider's exact instrument keys. URL-encode keys when
constructing requests. Keep tokens in environment variables and exclude
secrets from logs and raw request metadata.

Official documentation: - Expiries:
https://upstox.com/developer/api-documentation/get-expiries/ - Expired
option contracts:
https://upstox.com/developer/api-documentation/get-expired-option-contracts/ -
Expired historical candles:
https://upstox.com/developer/api-documentation/get-expired-historical-candle-data/ -
Historical candles v3:
https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/ -
Active option contracts:
https://upstox.com/developer/api-documentation/get-option-contracts/ -
Current option chain:
https://upstox.com/developer/api-documentation/get-pc-option-chain/

------------------------------------------------------------------------

## 12. Loading, validation and recovery

### 12.1 Ingestion workflow

1.  Discover the required expiry dates.
2.  Fetch contract metadata for each expiry.
3.  Apply the selected strategy/data-coverage policy to determine which
    contracts to download.
4.  Fetch underlying candles and option candles through the appropriate
    endpoints.
5.  Capture current option-chain responses periodically if historical
    chain snapshots are required.
6.  Store raw payloads with request/collection metadata.
7.  Normalize field names and types; parse timestamps with timezone
    awareness.
8.  Validate records and create coverage/failure reports.
9.  Write normalized Parquet partitions.
10. Query Parquet through DuckDB for a backtest's selected dates,
    contracts and fields.
11. Build the strategy-specific Layer 2 representation.
12. Run the backtest and persist job/results metadata in PostgreSQL.

### 12.2 Validation checks

-   HTTP status and provider-level `status`.
-   Expected response structure and candle field count.
-   Contract key and metadata consistency.
-   Timestamp timezone and requested date range.
-   Duplicate `(instrument_key, timestamp, interval)` records.
-   OHLC rules: `low <= open <= high`, `low <= close <= high`, and
    `low <= high`.
-   Missing expected minute intervals, accounting for exchange sessions
    and holidays.
-   Null, negative or implausible prices, volume and OI.
-   Zero-volume candles and suspicious unchanged-price runs.
-   Coverage by expiry, strike and option type.
-   API failures and contracts for which no candles were returned.

Do not assume exactly 375 candles for every contract in a normal
session. It is only a rough full-session reference for one-minute NSE
candles, not proof that each option contract must have that many
records. Compare actual timestamps with the expected trading-session
calendar.

Suggested internal coverage statuses: `COMPLETE`, `PARTIAL`, `NO_DATA`,
`FAILED`, `REVIEW_REQUIRED`.

### 12.3 Idempotency and resumability

- Assign each ingestion run a unique ID.
- Record endpoint, parameters (excluding credentials), date range, interval, contract count, successes/failures, row counts, validation results and raw response checksums.
- Store per-contract failures and retry state.
- Use a logical key such as `(instrument_key, timestamp, interval)` within an explicitly defined source/schema policy.
- Do not silently overwrite conflicting provider records; record conflicts and apply a documented reconciliation rule.
- Keep raw responses so normalization can be rerun without repeated API calls.
- After writing normalized Parquet, write a manifest that references the actual output artifacts and records the schema version, coverage range, row count, ingestion run, validation status and relevant checksums.
- Mark incomplete or failed ingestion explicitly. Do not publish a manifest that labels a partially downloaded dataset as complete.
- Preserve the association between each ingestion run, its raw inputs, normalized outputs and validation report so that data preparation can be reproduced.
- Ensure that rerunning an ingestion does not create ambiguous manifests or silently replace historical provenance. Use a documented versioning or supersession policy for revised outputs.

------------------------------------------------------------------------

## 13. Partitioning and persistent storage

Suggested normalized layout:

``` text
Data/normalized/spot_candles/
Data/normalized/option_candles/
Data/normalized/contract_reference/
Data/normalized/option_chain_snapshots/
```

Candidate partition dimensions include underlying, year, month, interval
and expiry. Final partitioning must be measured against actual query
patterns and file sizes. Avoid creating one tiny Parquet file per
contract per minute.

Parquet must live on persistent disk or a persistent Docker-mounted
volume, not only inside an ephemeral container filesystem. The raw
archive and normalized datasets should be recoverable independently.

------------------------------------------------------------------------

## 14. Known data coverage and caveats

Previously observed project inventory (revalidate before production
use):

-   NIFTY index one-minute candles: approximately 2022-01-03 through
    2026-10-08.
-   Option-chain snapshots: approximately from 2026-01-20, collected at
    roughly 30-second intervals in the existing dataset.
-   Expired individual option candles: currently being tested with
    Upstox's expired-instruments API.

These datasets have different historical coverage and must not be
assumed to overlap completely.

The user's current NIFTY index CSV contains `volume=0` and
`open_interest=0`. Preserve those source values while validating whether
the fields are meaningful for the index instrument. The expired
option-candle CSV includes `oi`; do not silently rename it to
`open_interest` without a versioned migration.

The current option-chain endpoint provides a current response, not
arbitrary historical chain snapshots. For historical snapshots,
QuantView must have collected and retained those responses at the time.

------------------------------------------------------------------------

## 15. Final architectural rules

1.  **Raw means source payload; normalized means typed, validated
    QuantView records.**
2.  **Long format is canonical.** One row per instrument/contract,
    timestamp and interval.
3.  **Sort by timestamp first** for inspection and chronological
    processing, with expiry/strike/type as tie-breakers.
4.  **Use DuckDB to select a specific contract/time range.** Prefer the
    resolved `instrument_key` when available.
5.  **Layer 2 is strategy-dependent.** A single ATM/ITM contract needs a
    series, not a giant matrix. Multi-strike strategies may use wide
    matrices.
6.  **Store normalized history in Parquet;** use CSV for current
    inspection/debugging.
7.  **Use PostgreSQL for transactional state;** do not make it the bulk
    historical candle store.
8.  **Keep missing prices missing.** Preserve zero-volume observations,
    flag them and enforce a declared execution model.
9.  **Preserve provenance.** Raw responses, schema versions, ingestion
    manifests and coverage reports must allow reproducible data
    preparation.
10. **Do not infer data completeness from request success or from a
    target candle count.** Validate coverage per contract and session.
