# QuantView — Low-Level Design (LLD)

| Field | Value |
|---|---|
| Document | `docs/LOW_LEVEL_DESIGN.md` |
| Companion | `docs/HIGH_LEVEL_DESIGN.md` (HLD) |
| Focused specs (UI behaviour; contracts stay in this LLD, which wins on any conflict) | `docs/CHARTING_UX.md`, `docs/OPTIONS_CHAIN_UI.md`, `docs/PAPER_TRADING_UI.md`, `docs/BACKTESTING_REPORT_SPEC.md`; review record: `docs/V1_2_CHANGE_LOG_AND_TRACEABILITY.md` |
| Status | Baseline v1.2 (amends v1.1) — implementation contract. Every v1.2 item is **DESIGNED** only (Appendix C) |
| Purpose | Give a coding agent every schema, formula, default, algorithm, test and ticket needed to build without making design decisions |

## How to read this document
1. Every section is **prescriptive**. "Must" and "default" mean exactly that. An agent must not substitute its own numbers or conventions.
2. Values tagged **`[VERIFY]`** are external facts researched on 2026-10-10 that must be confirmed against the primary source during the named ticket; until then the stated default is used and the run is labelled `UNVERIFIED_PARAM`.
3. Values tagged **`[OWNER]`** are owner policy choices with a safe starting default; changing them needs an ADR in HLD §16.
4. If a needed value is absent, stop and ask. Do not guess.
5. Code blocks are normative signatures/pseudo-code unless labelled *example*.
6. **[v1.2] Status words.** `DESIGNED`, `IMPLEMENTED`, `TESTED`, `VERIFIED` are used exactly as defined in Appendix C. A section that says DESIGNED does not claim anything exists.

## Revision history
| Version | Sections changed | Why |
|---|---|---|
| 1.0 | — | Initial baseline |
| 1.1 | §1.3, §3.1, §4.9.3–4.9.4, §4.10.1, §4.10.6, §5.4.10–5.4.11, §6.1, §6.2, §6.9, §7, §8.2–8.4, §8.6 (rewritten), §8.8.1, §8.9, §8.12.3, §9.4, §11 (roles, label registry, §11.11–11.12), §12.2, §13.3, §16, §17, App. B | ADR-018…025 in HLD §16: layered risk with any account size; INTRADAY/OVERNIGHT duration; futures recorded as data; pinned subscriptions; ML roles and holdout lifecycle; Pine porting; `ml` above `simulation`. Headings and tables changed in v1.1 are marked **[v1.1]**. |
| 1.2 | §0, §1.1, §2.3, **§2.7 (new)**, §4.4.1 (new), §4.8.1 (new), §4.10.1, §4.10.5, §5.1.2, §5.1.9 (new), §6.1, §6.6, §8.4.8 (new), §8.6.2, §8.6.4, §8.6.8–8.6.9 (new), §8.8, §8.8.2–8.8.4 (new), §8.9, §8.10.5 (new), §8.11, §8.15 (new), §9.2–9.6, §9.3.1/§9.5.1 (new), **§10.5 (new)**, §11.7.1 (new), §12.2–12.4, §13.1–13.4, §14.2–14.4, §15, §15.1 (new), §16.1, §17, App. B, **App. C (new)** | ADR-026…036 in HLD §16: durable events, paper/live isolation, option risk semantics, manual paper account, deployment state machine, strategy visualization, server-side replay, live chain, metric inspector, quote fills, coverage matrix. Sections changed in v1.2 are marked **[v1.2]**; each carries a status of DESIGNED until Appendix C says otherwise. |

## Table of contents
0 Conventions · 1 Repository, boundaries, config · 2 Shared kernel · 3 Instruments and calendar · 4 Market data · 5 Features · 6 Strategies · 7 Contract selection · 8 Simulation, risk, fills, costs, metrics · 9 Ledger · 10 Execution · 11 ML · 12 API · 13 Frontend · 14 Operations · 15 Test catalogue · 16 Configuration reference · 17 Build tickets · Appendices A–C

---

# 0. Conventions

| Topic | Rule |
|---|---|
| Python | 3.12, `from __future__ import annotations`, full type hints, `mypy --strict` for `shared`, `ledger`, `risk`, `instruments` |
| Models | Cross-module contracts: Pydantic v2 `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`. Hot loops: `@dataclass(slots=True, frozen=True)` |
| Names | Packages/modules `snake_case`; classes `PascalCase`; enums `UPPER_SNAKE` members; Parquet/SQL columns `snake_case`; feature ids `snake_case` |
| Time | Aware `datetime` in UTC internally; `IST = ZoneInfo("Asia/Kolkata")`; naive datetimes are a bug and must raise `NaiveDatetimeError` |
| Money | Integer paise (`int`); price tick comparisons in paise; INR only |
| IDs | ULID strings (`python-ulid`), generated through `shared.ids.new_id(prefix)` → e.g. `ord_01J...` |
| Floats | Indicators use `float64`; `NaN` is "not ready" inside arrays, converted to `None` at API boundary |
| Errors | Typed exceptions (§2.5); never `except Exception: pass`; API maps to error codes (§12.4) |
| Logging | `structlog`; mandatory bound keys when available: `correlation_id`, `run_id`, `strategy_id`, `strategy_version`, `instrument_id` |
| Randomness | Any randomness takes an explicit `seed: int`; default seed 20260101 recorded in manifests |
| Parquet | zstd level 3, row group ≈ 128k rows, `pyarrow` schemas defined in code (single source), schema version column `schema_version: int32` |
| Paths | Always build paths with `pathlib.Path` from `QV_DATA_DIR`; never hard-code drive letters; compare paths case-sensitively in tests |
| Dates in files | `YYYY-MM-DD` zero-padded everywhere. Legacy non-padded folders are *read* via a tolerant parser and never renamed in place (§4.1) |

---

# 1. Repository, boundaries, configuration

## 1.1 Repository layout (exact)
```text
quantview/                      # repo root (current: C:\Algo\Options)
  AGENTS.md                     # operational rules; points to the two docs
  README.md
  docs/
    HIGH_LEVEL_DESIGN.md
    LOW_LEVEL_DESIGN.md
    CHARTING_UX.md  OPTIONS_CHAIN_UI.md  PAPER_TRADING_UI.md  BACKTESTING_REPORT_SPEC.md   # [v1.2] focused UI specs
    V1_2_CHANGE_LOG_AND_TRACEABILITY.md
  config/
    settings.yaml               # §16.1
    calendar/
      nse_sessions.yaml         # §3.2
      special_sessions.yaml
    rules/
      nifty_rules.yaml          # §3.4
    costs/
      upstox_nse_options.yaml   # §8.5
    risk/
      profiles/                 # paper_default.yaml, research_relaxed.yaml (§8.6.4)
    strategies/                 # versioned spec files (reference strategies)
  data/                         # git-ignored (QV_DATA_DIR)
    raw/ canonical/ derived/ quality/ models/ runs/
  legacy/                       # frozen copy of Data_Collectors/ (read-only reference)
  backend/
    pyproject.toml
    src/quantview/
      shared/        {ids.py,time.py,money.py,events.py,journal.py,errors.py,config.py,clock.py,logging.py}
      instruments/   {models.py,calendar.py,expiry_rules.py,contract_master.py,contracts.py}
      market_data/
        contracts.py                       # public: repositories, DTOs
        models.py schemas.py               # private
        raw_archive.py
        parsers/ {candles_csv.py,option_chain_v1.py,option_chain_v2.py,option_chain_v3.py,upstox_api.py}
        normalize.py validate.py quality.py
        resample.py repository.py duckdb_views.py
        live/ {feed.py,decode.py,candle_builder.py,quote_recorder.py,health.py}
        collectors/ {snapshot_collector.py,historical_fetcher.py,token_manager.py,rate_limiter.py}
        reconcile.py
      research/
        features/ {registry.py,base.py,price.py,trend.py,volatility.py,volume.py,session.py,levels.py,option_chain.py,mtf.py,engine.py}
        strategies/ {spec.py,evaluator.py,python_api.py,runner.py,registry.py,reference/}
        contract_selection/ {policies.py,selector.py}
      ml/ {datasets.py,labels.py,cv.py,train.py,evaluate.py,registry.py,predictor.py}
      risk/ {models.py,rules.py,engine.py,profiles.py}
      ledger/ {models.py,accounts.py,posting.py,positions.py,pnl.py,fees.py,repository.py,rebuild.py}
      execution/ {contracts.py,order_state.py,paper_adapter.py,upstox/ (Phase 9)}
      simulation/ {engine.py,clock.py,data_feed.py,fills.py,costs.py,stops.py,metrics.py,metric_details.py,manifest.py,report.py,paper_runner.py,manual_orders.py,deployments.py,replay.py,mode_b.py,mode_c.py,mode_s.py}
      api/ {main.py,deps.py,errors.py,routes/,ws/}
      apps/ {collect_snapshots.py,collect_live.py,eod.py,auth_login.py,paper_runner.py,backtest.py}
    tests/ {unit,property,parity,lookahead,integration,replay,e2e,fixtures}
  frontend/                    # Next.js app (§13)
  scripts/                     # one-off audit scripts (never mutate raw)
```
Do not create empty packages ahead of the ticket that needs them.

## 1.2 Windows and path rules
- Use `pathlib`; no backslash literals; no reliance on case-insensitivity (`Data/` vs `data/` are different on Linux).
- `data/raw/legacy_upstox/` is a **copy** of existing `Data/` created by `scripts/archive_legacy_data.py`, which writes `MANIFEST.sha256` and then sets files read-only. The original `Data/` is left untouched until the owner deletes it manually after G0.6.
- The legacy `merge_extensions.py` overwrote the primary candle CSV. **Never run any legacy script**. They live in `legacy/` for reference only.

## 1.3 Boundary enforcement (`backend/pyproject.toml`, normative)
```toml
[tool.importlinter]
root_packages = ["quantview"]

[[tool.importlinter.contracts]]
name = "Layered architecture"
type = "layers"
layers = [
  "quantview.api | quantview.apps",
  "quantview.ml",            # [v1.1] above simulation: ml may call the Mode B engine; nothing below may import ml
  "quantview.simulation",
  "quantview.execution",
  "quantview.risk | quantview.ledger",
  "quantview.research",
  "quantview.market_data",
  "quantview.instruments",
  "quantview.shared",
]

[[tool.importlinter.contracts]]
name = "No broker SDK outside adapters"
type = "forbidden"
source_modules = ["quantview.research", "quantview.simulation", "quantview.ledger", "quantview.risk", "quantview.ml", "quantview.market_data.parsers", "quantview.instruments"]
forbidden_modules = ["upstox_client", "quantview.execution.upstox"]

[[tool.importlinter.contracts]]
name = "Ledger and risk independent"
type = "independence"
modules = ["quantview.ledger", "quantview.risk"]

[[tool.importlinter.contracts]]
name = "Cross-module access only through contracts"
type = "forbidden"
source_modules = ["quantview.simulation", "quantview.research", "quantview.ml", "quantview.api"]
forbidden_modules = ["quantview.market_data.models", "quantview.market_data.schemas", "quantview.market_data.repository"]
```
Public access points: `quantview.<package>.contracts`. A CI step fails the build if `import-linter` fails.

## 1.4 Dependencies (`pyproject.toml`)
Runtime: `pydantic>=2`, `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2`, `alembic`, `psycopg[binary]`, `duckdb`, `pyarrow`, `pandas`, `numpy`, `scipy`, `pyyaml`, `structlog`, `httpx`, `websockets`, `protobuf`, `python-ulid`, `tenacity`, `apscheduler`, `python-dotenv`, `lightgbm`, `scikit-learn`. Dev: `pytest`, `hypothesis`, `import-linter`, `ruff`, `mypy`, `pytest-cov`, `freezegun`. Pin exact versions in `uv.lock`; `pyarrow` is **required** (it was missing from the legacy `requirements.txt`).

---

# 2. Shared kernel (`quantview.shared`)

## 2.1 `time.py`
```python
IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

def to_utc(value: datetime | str, *, assume_tz: tzinfo | None = None) -> datetime:
    """Aware -> UTC. Naive -> requires assume_tz else raises NaiveDatetimeError."""

def ist_date(ts: datetime) -> date: ...                 # exchange-local session date
def at_ist(d: date, hh: int, mm: int, ss: int = 0) -> datetime: ...  # -> UTC instant
def floor_to_grid(ts: datetime, period_s: int, offset_s: int = 0) -> datetime: ...
def ceil_to_grid(ts: datetime, period_s: int, offset_s: int = 0) -> datetime: ...
def ms_to_utc(ms: int) -> datetime: ...                 # epoch milliseconds -> UTC
```
`floor_to_grid` works on epoch seconds: `floor((epoch - offset) / period) * period + offset`.

## 2.2 `money.py`
```python
Paise = int
def to_paise(x: Decimal | str | int | float, rounding=ROUND_HALF_UP) -> Paise:
    # float inputs are converted via Decimal(str(x)); quantize to 0.01 rupee
def paise_to_rupees(p: Paise) -> Decimal: ...
def round_to_tick(price_paise: Paise, tick_paise: int, mode: Literal["nearest","up","down"]) -> Paise: ...
def mul_rate(amount_paise: Paise, rate: Decimal, rounding=ROUND_HALF_UP) -> Paise: ...
```
Tick size for NIFTY options is 0.05 → `tick_paise = 5`.

## 2.3 `events.py` — event envelope
```python
class EventEnvelope(BaseModel):
    event_id: str                # ULID
    event_type: str              # dotted, e.g. "candle.finalized"
    schema_version: int = 1
    occurred_at: datetime        # when it happened (UTC)
    published_at: datetime       # when emitted
    correlation_id: str          # links candle -> decision -> order -> fill -> ledger
    causation_id: str | None
    source: str                  # module name
    payload: dict                # JSON-serialisable, validated by type-specific model
```
Registered event types (v1): `candle.provisional`, `candle.finalized`, `option.snapshot`, `option.quote`, `feed.health`, `feature.row`, `decision.created`, `intent.created`, `risk.approved`, `risk.rejected`, `order.submitted`, `order.updated`, `fill.recorded`, `ledger.posted`, `position.updated`, `run.progress`, `run.completed`, `kill_switch.changed`; **[v1.2]** `feed.state_changed`, `feed.gap`, `producer.restarted`, `deployment.state_changed`, `manual.command.updated`. Envelope additions and delivery guarantees: §2.7.

## 2.4 `clock.py`
```python
class Clock(Protocol):
    def now(self) -> datetime: ...          # aware UTC
class WallClock: ...
class HistoricalClock:                       # advanced only by the simulation engine
    def set(self, ts: datetime) -> None: ... # must be >= current; else raises InvariantViolationError
```

## 2.5 `errors.py`
`QuantViewError` (base) → `ValidationError`, `NaiveDatetimeError`, `DataQualityError`, `DataUnavailableError`, `StaleDataError`, `ConflictError`, `RiskRejectedError`, `ExternalServiceError`, `ExternalOutcomeUnknownError`, `InvariantViolationError`, `ConfigError`, `LookAheadError`. Each carries `code` (stable string), `message`, `details: dict`.

## 2.6 `config.py`
Load order: `config/settings.yaml` → environment variables `QV_*` → CLI flags. Validate into `Settings` (Pydantic). Secrets (`UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, `UPSTOX_REDIRECT_URI`, `DATABASE_URL`) come only from env/`.env`. Fail fast on unknown keys.

## 2.7 [v1.2] Durable event delivery (ADR-026) — status: DESIGNED
**Problem in v1.1.** §4.10.5 delivered events over a plain TCP stream with no persistence, while §8.8 and the HLD require "replay from `event_id` checkpoints" and `paper_deployments.checkpoint_event_id`. Nothing stored the events a checkpoint could point into, so restart-safety was claimed but not achievable. This section closes that gap **without a broker**.

### 2.7.1 Three event classes, three delivery guarantees
| Class | Examples | Rate | Delivery | After a consumer restart |
|---|---|---|---|---|
| **CONTROL** | `candle.finalized`, `candle.missing`, `option.snapshot` (metadata + partition reference, never rows), `feed.state_changed`, `feed.gap`, `producer.restarted`, `kill_switch.changed` | ≈ 1–5 / min | **Durable journal** (§2.7.3), fsync before the event counts as emitted | **Replayed** from the consumer checkpoint |
| **TELEMETRY** | `option.quote`, `candle.provisional`, `feed.health` heartbeat, index ticks | up to ≈ 50 / s | Best-effort stream with a per-stream contiguous `seq` (TCP wake-up path); the *raw* quote/tick log is written by the recorder to Parquet (§4.10.4) | **Not replayed.** A gap means "stale", never "catch up" |
| **TRADING** | `decision.created`, `order.*`, `fill.recorded`, `ledger.posted`, `position.updated`, `deployment.state_changed` | low | **Transactional outbox** in Postgres (§2.7.5), written in the same transaction as the state change | Served to the UI by `outbox.seq` |
**Why quotes are not replayed.** A paper order created after downtime must never fill against a quote that no longer exists. Quotes must be *current or absent*. Candles are different: a missed bar is a legitimate decision trigger, so CONTROL events are replayed — but with the gating rule in §2.7.4.

### 2.7.2 Envelope additions
```python
class EventEnvelope(BaseModel):          # §2.3 fields unchanged, plus:
    stream: str                          # "live.control" | "live.telemetry" | "trading.<account_id>"
    producer_epoch: int                  # +1 at every producer start; persisted in <journal>/<stream>/EPOCH
    seq: int                             # 1.. contiguous within (stream, producer_epoch)
    dedupe_key: str                      # logical identity, e.g. "candle.finalized:IDX:NIFTY50:5m:2026-03-12T04:45:00Z:rev0"
    account_mode: Literal["PAPER","LIVE"] | None = None   # mandatory on trading.* streams
```
`event_id` stays a ULID (unique per emission). Consumers de-duplicate transport on `(stream, producer_epoch, seq)` and **effects** on the natural idempotency keys of §2.7.6.

### 2.7.3 Control journal (`shared/journal.py`)
- **Layout.** `data/journal/<stream>/epoch=000012/seg-00000001.jrnl`. Record framing: `[u32 length][u32 crc32c][utf-8 JSON EventEnvelope]`.
- **Write rule (journal-first).** An event is *committed* when `write + fsync` returns. Only then is it published to consumers. The live-built candle OHLC travels **inside** the `candle.finalized` payload, so after a crash the canonical `live_built` Parquet is rebuilt from the journal by the `canonical-writer` consumer; the journal, not the Parquet buffer, is the durable source for live-built candles.
- **fsync policy.** `fsync: every_record` for CONTROL (≤ 5 records/min — cost is irrelevant). Directory fsync on segment creation and on `EPOCH` replacement (write temp + rename + fsync).
- **Single writer.** `collect_live` holds an exclusive lock on the stream directory.
- **Start-up repair.** Scan the last segment; truncate at the first record with a bad length or CRC (torn write); append `producer.restarted{new_epoch, last_good_seq, truncated_bytes}` as the first record of the new epoch.
- **Rotation / retention.** 16 MB or UTC-midnight; segments kept 90 days (`journal.retention_days`).
- **Tailing.** Consumers poll file size every `journal.poll_ms` (200 ms; works on Windows with shared-read open flags). The TCP socket remains only as a low-latency wake-up and as the TELEMETRY path.

### 2.7.4 Consumer checkpoints and replay
```sql
CREATE TABLE consumer_checkpoints (                 -- one per Postgres schema that hosts a consumer
  consumer_id text NOT NULL, stream text NOT NULL, producer_epoch int NOT NULL, seq bigint NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (consumer_id, stream));
```
**Exactly-once effect rule.** The checkpoint advances **in the same Postgres transaction** as every effect of handling that event (decision rows, orders, order events, fills, ledger events, outbox rows, feature rows index). A crash before commit ⇒ the event is handled again; a crash after commit ⇒ it is not. Effects are additionally idempotent (§2.7.6) so a defect in this rule cannot create duplicate money movements.
```
consumer start:
  cp = checkpoints[consumer, stream] (absent => start at current tail, never at beginning)
  for record in journal.read_after(cp):
      if same epoch and record.seq != cp.seq + 1:  -> GAP_DETECTED: set stream DEGRADED, block entries (RK-17), alert, continue reading
      if epoch changed: require producer.restarted record; log PRODUCER_RESTART
      handle(record, replay = record.occurred_at older than max_replay_decision_age_s)
      commit(effects + checkpoint)
  if cp is beyond journal end (journal restored from an older backup) -> STREAM_REWOUND: block entries, alert; owner runs `qv journal reset-checkpoint` (audited)
```
**Replay gating (`max_replay_decision_age_s = 120`).** While `replay = true` the runner still updates features and exit logic from the replayed bar, but **entries are blocked** with reason `STALE_REPLAY` (the signal is real but the quote it would fill against is not contemporaneous). Exits and stop/timer logic always run. Duplicate decisions are impossible by the `decisions.idempotency_key` (§9.5.1).

### 2.7.5 Trading outbox (Postgres)
`outbox(seq bigserial PK, stream, event_id UNIQUE, event_type, payload jsonb, created_at)` is inserted in the **same transaction** as the state change it describes (§9.5.1). `api` forwards rows to WebSocket clients using `LISTEN/NOTIFY` as a wake-up and a `seq` poll as the source of truth; `{"op":"resync","since_event_id":…}` (§12.3) is served from the outbox (retained 30 days). Postgres is not a message broker here: it is the system of record that the events are *about*.

### 2.7.6 Idempotency catalogue (every effect has a unique key)
| Effect | Key | Enforced by |
|---|---|---|
| Decision | `decisions.idempotency_key` = `deployment_id:spec_hash:timeframe:bar_start_iso:action` (`run_id := deployment_id` for PAPER) | UNIQUE |
| Order | `orders.idempotency_key` = `<decision key>:<leg>` (strategy) or `client_order_id` (manual) | UNIQUE |
| Order event | `order_events.event_id` | PK |
| Fill | `fills.idempotency_key` = `<order_id>:<fill_seq>` | UNIQUE |
| Ledger event | `ledger_events.idempotency_key` = `fill:<fill_id>` (or `charge_adj:…`, `reversal:…`) | UNIQUE |
| Outbox | `(stream, seq)` / `event_id` | PK / UNIQUE |
| Deployment event | `(deployment_id, seq)` | PK |
| Feature row for chart | `(deployment_id, strategy_tf bar_start)` | upsert-by-key |

### 2.7.7 Feed states and stale-feed behaviour
Per stream and per instrument: `OK → STALE` (no tick for `feed_stale_s = 10` for the index, `option_stale_s = 30` per option) `→ DOWN` (stale > 60 s or socket closed). Each transition is a durable `feed.state_changed` CONTROL event. **STALE/DOWN ⇒ RK-17 blocks all new entries** (strategy and manual). Exits keep trying whenever a valid quote exists (age ≤ `max_live_quote_age_s`); with no valid quote an exit order waits and retries every 5 s (§8.8) and an alert escalates at 60 s. "Required data unavailable" (features not ok, chain older than `max_snapshot_age_s`, dataset status `UNUSABLE`) blocks entries with the existing reason codes. The UI shows the state verbatim (OPTIONS_CHAIN_UI.md §5).

### 2.7.8 What this design does not promise
It does not make the collector highly available. Ticks that arrive while `collect_live` is down are lost (the provider offers no replay); they are recorded as `COLLECTOR_GAP`, never reconstructed.

### 2.7.9 Recovery and crash tests (all **PENDING**; gate G0.12 / G7.1)
| ID | Test |
|---|---|
| T-EV-1 | `kill -9` of `collect_live` mid-session → restart: epoch + 1, `producer.restarted` journaled, no fabricated candle for the dead minute (`candle.missing`/`PARTIAL_BAR`), consumers continue |
| T-EV-2 | Fault hook kills the runner after handling `candle.finalized` but before commit → restart → exactly one decision and one order, checkpoint advanced once |
| T-EV-3 | Property test: duplicate delivery of random journal records → no second effect (decisions, orders, fills, ledger, outbox) |
| T-EV-4 | Journal truncated mid-record and a record with a flipped bit → start-up repair; no partial record is ever delivered; CRC fault ⇒ stream `DEGRADED` |
| T-EV-5 | A record removed from the middle → consumer reports `GAP_DETECTED` and blocks entries |
| T-EV-6 | **Crash-consistency harness**: a file-layer wrapper "crashes" the process at every enumerated write/fsync/rename point of the journal and the transactional path; after each crash, recovery restores all invariants (§9.7 `verify()`, journal framing, checkpoint ≤ journal tail). Plus one **real pull-the-plug drill** on the dev host before gate G7.6, recorded in `data/quality/powerloss_drill_<date>.json` |
| T-EV-7 | Postgres stopped for 10 minutes → runner blocks entries, checkpoint not advanced; after restore the backlog replays with `STALE_REPLAY` gating and no duplicates |
| T-EV-8 | Runner down 5 minutes → no fill uses a quote older than `max_wait_s`; quotes are not replayed |
| T-EV-9 | Kill between ledger commit and WebSocket delivery → reconnecting client gets the event from the outbox exactly once (`event_id` dedupe) |
| T-EV-10 | Epoch rollover and "checkpoint beyond journal end" ⇒ `STREAM_REWOUND`, entries blocked until audited reset |

---

# 3. Instruments and calendar (`quantview.instruments`)

## 3.1 Identity rules
| Entity | `instrument_id` format | Example |
|---|---|---|
| Index | `IDX:<SYMBOL>` | `IDX:NIFTY50` |
| Option | `OPT:<UNDERLYING>:<expiry YYYY-MM-DD>:<strike as integer>:<CE\|PE>` | `OPT:NIFTY:2026-04-21:24500:CE` |
| Future **[v1.1]** | `FUT:<UNDERLYING>:<expiry YYYY-MM-DD>` (monthly expiry) | `FUT:NIFTY:2026-10-27` |
| Provider key | stored separately in `provider_key` (e.g. `NSE_INDEX\|Nifty 50`, `NSE_FO\|<token>`) | — |
Option ids are **structural**, so historical snapshots (which lack provider tokens) and live feeds map to the same id. Strikes are integers (NIFTY strikes are whole numbers; assert `strike == int(strike)`).

## 3.2 Calendar
### Data model
```yaml
# config/calendar/nse_sessions.yaml
exchange: NSE
timezone: Asia/Kolkata
regular_session: {open: "09:15", close: "15:30"}      # 375 one-minute bars
status: UNVERIFIED            # becomes VERIFIED only after G0.1
holidays:                      # weekday non-sessions
  - {date: 2026-04-14, reason: "Dr. Ambedkar Jayanti", source: "NSE holiday circular URL"}
  # ... full list 2021-2026 filled during ticket T0.2
special_sessions:              # config/calendar/special_sessions.yaml
  - {date: 2024-11-01, open: "18:00", close: "19:00", kind: MUHURAT, verify: true}
  - {date: 2023-11-12, open: "18:15", close: "19:15", kind: MUHURAT, verify: true}
  - {date: 2022-10-24, open: "18:15", close: "19:15", kind: MUHURAT, verify: true}
  - {date: 2025-10-21, open: "13:45", close: "14:45", kind: MUHURAT, verify: true}
weekend_sessions: []           # Saturday/Sunday special trading days; empty until confirmed
```
### Calendar API
```python
class Calendar:
    def is_session(self, d: date) -> bool
    def session_bounds(self, d: date) -> tuple[datetime, datetime]       # UTC open/close
    def expected_bars(self, d: date, tf: Timeframe) -> list[tuple[datetime, datetime]]  # (bar_start, bar_end)
    def sessions_between(self, a: date, b: date) -> list[date]
    def prev_session(self, d: date) -> date
    def next_session(self, d: date) -> date
    def minutes_since_open(self, ts: datetime) -> float
    def minutes_to_close(self, ts: datetime) -> float
```
### Bootstrap algorithm (ticket T0.2) — deterministic
1. Load the 1m candle file. For each IST date, count bars `n(d)`.
2. `observed_sessions = {d : weekday(d) < 5 and n(d) >= 300}`.
3. `candidate_holidays = {weekdays in [first,last] not in observed_sessions}`.
4. `irregular_days = {d : 0 < n(d) < 375}` and `{d : weekday(d) >= 5 and n(d) > 0}`.
5. Emit `scripts/out/calendar_candidates.csv`: columns `date, weekday, bar_count, bucket` where `bucket ∈ {CANDIDATE_HOLIDAY, IRREGULAR_SESSION, WEEKEND_ROWS}`.
6. The owner (or agent with web access) resolves each row against NSE's holiday list / circulars and fills the YAML with a source URL. Only then set `status: VERIFIED`.
7. While `status: UNVERIFIED`, DQ reports tag every missing-bar finding `CALENDAR_UNVERIFIED` and gates G0.1/G0.2 stay open.
**The calendar is never inferred silently from data after this step.**

## 3.3 Timeframes and bar boundaries
```python
class Timeframe(Enum): M1=60; M3=180; M5=300; M15=900; H1=3600; H4=14400; D1=0  # D1 = whole session
```
For a regular session starting 09:15 with `k = floor(minutes_since_open / tf_minutes)`:
```
bar_start = open + k * tf
bar_end   = min(bar_start + tf, close)          # clipped at the real close (15:30)
```
Resulting expected bars per regular session: 1m=375, 3m=125, 5m=75, 15m=25, 1h=7 (last bar 15:15–15:30), 4h=2 (09:15–13:15, 13:15–15:30), 1d=1. For special sessions, `open/close` come from `special_sessions.yaml` and the same formula applies. Daily candles use `bar_start = open`, `bar_end = close`, `available_at = close`.

## 3.4 Expiry, lot, tick and strike rules
```yaml
# config/rules/nifty_rules.yaml
underlying: NIFTY
weekly_expiry_weekday_by_expiry_date:    # keyed by the EXPIRY date, not the trade date
  - {from: 2000-01-01, to: 2025-08-31, weekday: THU}
  - {from: 2025-09-01, to: null,        weekday: TUE}      # [VERIFY] NSE circular: first Tuesday weekly = 2025-09-02
monthly_expiry:                           # last <weekday> of month, same regime boundaries
  rule: last_weekday_of_month
holiday_shift: previous_session           # expiry on non-session -> previous session
lot_size_by_expiry_date:
  - {from: 2000-01-01, to: 2025-12-30, lot: 75, note: "75 since Nov 2024; earlier values not needed (no option data)"}
  - {from: 2026-01-06, to: null, lot: 65}                    # [VERIFY] NSE revision circular: weekly 06-Jan-2026, monthly 27-Jan-2026
tick_size_paise: 5                         # 0.05 [VERIFY]
strike_step_default: 50                    # [VERIFY] from chain data: modal adjacent difference within +-5% of spot
quantity_freeze_units: 1800                # [VERIFY] NSE circular (revised 2026-09-01 per forum report)
```
### Algorithms
```python
class ExpiryRules:
    def weekday_for(self, expiry_date: date) -> int
    def nominal_weekly_expiries(self, a: date, b: date) -> list[date]
        # for each date d in [a,b]: include d if d.weekday()==weekday_for(d)
    def actual_expiry(self, nominal: date, cal: Calendar) -> date
        # while not cal.is_session(nominal): nominal = cal.prev_session(nominal)
    def weekly_expiries(self, a, b, cal) -> list[date]       # actual_expiry applied, de-duplicated, sorted
    def monthly_expiries(self, a, b, cal) -> list[date]
    def nearest_expiry(self, trade_date: date, cal, *, min_calendar_days: int = 0) -> date
        # smallest expiry >= trade_date + min_calendar_days
    def lot_size(self, expiry: date) -> int
```
**Acceptance test T-INS-1:** for each of the 32 expiry dates in `data_status.md` (all listed Tuesdays plus `2026-04-13`), `weekly_expiries(2026-01-20, 2026-10-13, cal)` contains the date; and for 2025-08-21, 2025-08-28 (Thursdays) and 2025-09-02, 2025-09-09 (Tuesdays) the function returns the correct regime. Additionally `2026-04-14` (holiday) must not appear while `2026-04-13` must.

## 3.5 Contract master
- **Live/forward:** daily download of the Upstox instrument master and `GET /v2/option/contract` for NIFTY, stored raw at `data/raw/instruments/date=YYYY-MM-DD/`. `[VERIFY]` exact endpoint/file names in Upstox docs during T0.10.
- **Historical (Mode C):** no external master is available. A contract is *eligible at time t* iff it appears with a valid quote in the as-of snapshot at `t` (§7). This removes dependence on today's contract list.
- Table `instruments` (Parquet `data/canonical/instruments/`): `instrument_id, kind, underlying_id, expiry_date, strike, option_type, lot_size, tick_paise, provider_key, first_seen_at, last_seen_at, source`.

## 3.6 Tests (instruments)
| ID | Test |
|---|---|
| T-INS-1 | Expiry regimes as above |
| T-INS-2 | `expected_bars` counts per timeframe for a regular session: 1m=375, 3m=125, 5m=75, 15m=25, 1h=7, 4h=2, 1d=1 |
| T-INS-3 | Last 1h bar `15:15–15:30` and last 4h bar `13:15–15:30` have `bar_end = 15:30` |
| T-INS-4 | Holiday shift: expiry on holiday moves to previous session |
| T-INS-5 | Lot size boundary: expiry 2025-12-30 → 75; 2026-01-06 → 65 |
| T-INS-6 | Calendar bootstrap on a fixture file yields the expected candidate CSV |

---

# 4. Market data (`quantview.market_data`)

## 4.1 Raw archive and legacy migration
**Layout**
```text
data/raw/
  legacy_upstox/                       # copy of existing Data/ (read-only, MANIFEST.sha256)
    historical/candles/index/nifty/{1m,3m,5m,15m,1h,4h,1d}/nifty.csv
    live/option_chain/nifty/<expiry>/<date>/snapshots/HH-MM-SS.csv
  option_chain_api/date=YYYY-MM-DD/expiry=YYYY-MM-DD/HHMMSS_mmm.json.gz    # new collector (raw API JSON)
  candles_api/instrument=IDX_NIFTY50/tf=1m/date=YYYY-MM-DD.json.gz         # raw historical API JSON
  ticks/date=YYYY-MM-DD/<instrument>.ndjson.gz                             # raw WS messages, decoded to JSON
  instruments/date=YYYY-MM-DD/...
```
**Rules.** (1) Files are written once; opened `"xb"`. (2) After writing, compute SHA-256 and append to the directory's `MANIFEST.sha256`. (3) A nightly job verifies the manifest; mismatches raise `DataQualityError` and a P1 alert. (4) Legacy folders with non-padded dates (`2026-02-3`, `2026-03-2`, `2026-04-7`) are read with `parse_loose_date()`:
```python
def parse_loose_date(s: str) -> date:
    y, m, d = (int(p) for p in s.split("-"))   # accepts "2026-02-3"
    return date(y, m, d)
```
and recorded in the manifest with both the original and the canonical (zero-padded) name; the original directory is never renamed.

## 4.2 Parsers (pure functions)
Signature for every parser: `parse(source: Path | bytes, ctx: ParseContext) -> ParseResult(rows: pa.Table, rejects: list[Reject], meta: dict)`; no I/O besides reading the source; deterministic.

### 4.2.1 Candle CSV (legacy and API-derived)
| Source column | Canonical | Rule |
|---|---|---|
| `timestamp` | `bar_start` | Parse ISO-8601. Legacy files carry `+05:30`; convert to UTC. Naive value → `NaiveDatetimeError` for intraday files (do not guess) |
| `open,high,low,close` | same | float64, finite, > 0 |
| `volume` | `volume` | int64 nullable; `0` kept as 0 but dataset-level `volume_valid` computed (CQ-10) |
| `open_interest` | `oi` | int64 nullable |
| (derived) | `bar_end` | Calendar rule §3.3 for timeframe `tf` (taken from the directory name) |
| (derived) | `available_at` | `= bar_end` |
| (derived) | `session_date` | IST date of `bar_start` |
| (constant) | `instrument_id` | `IDX:NIFTY50` |
| (constant) | `source` | `legacy_csv` (or `upstox_hist`) |
Daily files: `timestamp` is a date at 00:00 (IST); map to `bar_start = session_open`, `bar_end = session_close`.

### 4.2.2 Option chain CSV (legacy v1/v2/v3)
Schema detection by exact column set (order-insensitive):
| Version | Columns |
|---|---|
| v1 | `timestamp,strike,type,ltp,oi,prev_oi,volume,bid,ask` |
| v2 | `timestamp,strike,type,oi,volume,bid,ask` |
| v3 | `timestamp,spot_price,strike,type,oi,volume,ltp,bid,ask,bid_qty,ask_qty,chng,chng_oi,iv,delta,gamma,theta,vega` |
Anything else → `UNKNOWN_SCHEMA`, whole file rejected to quarantine.

Per file: derive `expiry_date` and `folder_session_date` from the path (`.../<expiry>/<date>/snapshots/HH-MM-SS.csv`, loose date parser). Normalise `type`: `{"CE","CALL","C"} → "CE"`, `{"PE","PUT","P"} → "PE"` (case-insensitive), else reject row.

Canonical option-chain row (long format, one row per contract per snapshot) — see §4.5 for the Arrow schema. Mapping rules:
| Field | v1 | v2 | v3 |
|---|---|---|---|
| `spot_price` | null | null | column |
| `ltp` | column | **null** (`ltp_status=NOT_COLLECTED`) | column |
| `bid/ask` | column | column | column |
| `bid_qty/ask_qty` | null | null | column |
| `oi` | column | column | column |
| `prev_oi` | column | null | null |
| `chng_oi` | null | null | column |
| `chng` | null | null | column |
| `iv, delta, gamma, theta, vega` | null (`greeks_status=NOT_COLLECTED`) | null (same) | column, then §4.5 validation |
`src_schema` stores `v1|v2|v3|api_v4`. Never fill a null from another version.

### 4.2.3 Upstox API option chain (`api_v4`, new collector)
`[VERIFY]` field names against the Upstox option-chain response during ticket T0.10; expected structure per strike: `strike_price`, `underlying_spot_price`, `call_options{instrument_key, market_data{ltp, volume, oi, close_price, bid_price, bid_qty, ask_price, ask_qty, prev_oi}, option_greeks{vega,theta,gamma,delta,iv,pop}}` and the same for `put_options`. Map to the same canonical row; add `provider_key = instrument_key`. `request_sent_at`, `response_received_at` are stored in the snapshot index row (§4.5.4).

## 4.3 Option-snapshot timestamp semantics (resolved by test, not assumption)
Legacy `timestamp` has no timezone. Procedure `scripts/resolve_option_tz.py` (ticket T0.4), deterministic:
1. Take up to 2,000 v3 snapshots spread evenly over dates.
2. For hypothesis `H ∈ {IST, UTC}`: interpret `timestamp` under `H` → `observed_at(H)`. Locate the 1m bar with `bar_start = floor_minute(observed_at(H))`.
3. `hit_rate(H) = mean(bar.low − 2 ≤ spot_price ≤ bar.high + 2)` (points).
4. Accept `H* = argmax hit_rate` only if `hit_rate(H*) ≥ 0.95` and `hit_rate(other) ≤ 0.50`. Otherwise gate G0.4 FAILS and the owner decides; no default is applied.
5. Persist result in `config/data_semantics.yaml` (`option_snapshot_tz: IST`) with the evidence numbers and timestamp.

`available_at` for snapshots = `observed_at + snapshot_available_lag_s` where `snapshot_available_lag_s = 5` **[OWNER]** (conservative: covers request latency and the uncertainty whether the stamp is request-time or response-time). For `api_v4` snapshots, `available_at = response_received_at`.

## 4.4 Data-quality rules
Severity: `ERROR` = row/file quarantined (not in canonical); `WARN` = kept, flagged; `INFO` = report only. Every rule has an ID; reports list counts and examples (max 20) per rule per dataset.

### Candle rules
| ID | Rule | Sev | Action / flag |
|---|---|---|---|
| CQ-01 | Required columns parse to expected types | ERROR | Quarantine row |
| CQ-02 | Timestamp is timezone-aware (intraday) | ERROR | Quarantine file |
| CQ-03 | `bar_start` lies on the timeframe grid and inside an expected bar of the calendar | ERROR if off-grid; WARN `OUT_OF_SESSION` if grid-aligned but not in a session | Off-grid quarantined; out-of-session moved to `quality/out_of_session/` and classified by date (holiday/weekend/special) |
| CQ-04 | `high ≥ max(open,close,low)`, `low ≤ min(open,close,high)`, all finite and > 0 | ERROR | Quarantine row |
| CQ-05 | Duplicate `(instrument, tf, bar_start)` | INFO if identical (drop duplicate); ERROR if conflicting | Conflict: keep earliest-ingested, flag `CONFLICT`, list for owner |
| CQ-06 | Missing expected bar (calendar-driven) | WARN | Flag `MISSING_BAR`; report contiguous intervals; no fabrication |
| CQ-07 | 1m close-to-close jump > 3% | WARN | `SUSPECT_JUMP` |
| CQ-08 | ≥ 10 consecutive bars with `high == low` | WARN | `FLAT_RUN` |
| CQ-09 | Session with bar count ≠ expected | WARN | Report per session |
| CQ-10 | Dataset volume field all zero/null | INFO | `volume_valid=false` for the instrument/timeframe, stored in `config/data_semantics.yaml` |
| CQ-11 | Derived (resampled) vs native timeframe OHLC equal within 1e-9 | ERROR at gate level | G0.5 ≥ 99.9% of bars equal; mismatches listed |
| CQ-12 | Distinct session count equal across timeframes (after calendar) | ERROR at gate level | Explain every exception |
| CQ-13 | Calendar status `UNVERIFIED` | WARN | Tag every finding `CALENDAR_UNVERIFIED` |

### Option-chain rules
| ID | Rule | Sev | Action / flag |
|---|---|---|---|
| OQ-01 | Schema matches v1/v2/v3/api_v4 exactly | ERROR | Quarantine file |
| OQ-02 | One distinct `timestamp` per file | ERROR | Quarantine file |
| OQ-03 | `observed_at` inside session bounds | WARN | `OUT_OF_SESSION` (e.g. the 2026-07-04 Saturday test run); excluded from canonical, kept in quality |
| OQ-04 | Strike integer; type ∈ {CE,PE} | ERROR | Quarantine row |
| OQ-05 | Both CE and PE present per strike | WARN | `ASYMMETRIC_STRIKE` |
| OQ-06 | `bid ≤ ask` when both > 0 | WARN | `quote_status=CROSSED`, bid/ask kept, excluded from fills |
| OQ-07 | `bid` or `ask` missing/0 | INFO | `quote_status=ONE_SIDED` or `EMPTY` |
| OQ-08 | Negative price/qty/OI | ERROR | Quarantine row |
| OQ-09 | IV unit detection: if median ATM IV > 3 ⇒ percent; store as fraction (divide by 100) | INFO | Record detected unit per day |
| OQ-10 | Zero-sentinel Greeks: `iv == 0` OR (`delta==gamma==theta==vega==0`) | WARN | Set all Greeks null, `greeks_status=MISSING_ZERO_SENTINEL` |
| OQ-11 | Greek sanity: CE `0 ≤ delta ≤ 1`, PE `−1 ≤ delta ≤ 0`, `gamma ≥ 0`, `vega ≥ 0`, `0.01 ≤ iv ≤ 3.0` (fraction) | WARN | Greeks null, `greeks_status=INVALID` |
| OQ-12 | Duplicate snapshot at same `observed_at` | INFO/ERROR | Identical → drop; conflicting → keep first, flag |
| OQ-13 | Cadence: gap > 45 s between consecutive snapshots in a session | WARN | `SNAPSHOT_GAP(len_s)` in snapshot index; late start (> 09:20) `LATE_START`; early end (< 15:25) `EARLY_END` |
| OQ-14 | Chain breadth: < 20 strikes per expiry | WARN | `THIN_CHAIN` |
| OQ-15 | v3 spot vs 1m candle: spot outside `[low−25, high+25]` | WARN | `SPOT_MISMATCH` |
| OQ-16 | Expiry not in `ExpiryRules` for that date | WARN | `UNEXPECTED_EXPIRY` |
| OQ-17 | Filename time vs `observed_at` differ > 120 s | WARN | `FILENAME_TIME_MISMATCH` |
| OQ-18 | Folder `expiry`/`date` vs row-derived values differ | WARN | `FOLDER_MISMATCH` |

### Dataset-level status per `(dataset, session_date)`
`CLEAN` if no ERROR and no `MISSING_BAR`/`SNAPSHOT_GAP > 120 s`; `DEGRADED` if only WARN-level gaps; `UNUSABLE` if bar coverage < 80% (candles) or snapshot coverage < 40% (options); `UNVERIFIED` if calendar unverified. Written to `data/quality/status/dataset=<name>/part.parquet`.

### 4.4.1 [v1.2] Calendar version, absence reason codes, coverage matrix, eligibility gate — status: DESIGNED
**Calendar is versioned.** `config/calendar/nse_sessions.yaml` carries `calendar_version` (semver), `status`, `verified_through`, `sources[]`. Its sha256 and version are part of every `data_version`, DQ report, run manifest and deployment snapshot. Any change to a session row bumps the version and invalidates cached dataset statuses (recomputed by the next EOD run). Gate G0.1 stays the authority for `VERIFIED`.

**Absence reason codes.** Every expected-but-absent or unusable observation gets exactly one code (never an empty reason, never `UNKNOWN`):
| Code | Meaning | Counts as failure? |
|---|---|---|
| `CLOSED_HOLIDAY`, `CLOSED_WEEKEND` | Exchange closed (calendar) | No |
| `NOT_YET_LISTED` | Strike/expiry not yet listed at that time | No |
| `COLLECTOR_NOT_RUNNING`, `COLLECTOR_GAP`, `LATE_START`, `EARLY_END` | Our collector was not collecting | Yes (ours) |
| `REQUEST_FAILED` | A `FAILED`/`PARTIAL` row in `snapshot_index` | Yes |
| `PROVIDER_OMITTED` | Provider returned no bar/row we expected | Yes (provider) |
| `SCHEMA_NOT_COLLECTED` | Field absent in that source schema (e.g. v2 `ltp`) | No (documented limitation) |
| `QUOTE_ONE_SIDED`, `QUOTE_CROSSED`, `QUOTE_STALE`, `QUOTE_ZERO_SENTINEL`, `INVALID_VALUE`, `QUARANTINED` | Present but not executable/usable | Yes |
| `UNVERIFIED_CALENDAR` | Calendar not confirmed | Warning |
Closed-market periods are therefore never confused with collector failures, stale quotes or invalid data. Prices are never imputed; missing stays `null` + code (P6).

**Coverage matrix** (`data/quality/coverage_matrix/dataset=<d>/part.parquet`, rebuilt by EOD; 3 levels so the size stays small):
| Level | Grain | Columns |
|---|---|---|
| L1 | `session_date × dataset` | `status`, `calendar_version`, `expected`, `present`, `reason_counts` |
| L2 | `session_date × expiry × src_schema × hour` | `snapshots_expected/ok/failed/late`, `max_gap_s`, `median_latency_ms`, `quote_rows_expected/present`, `ws_ticks`, `ws_max_silence_s` |
| L3 | `session_date × expiry × strike × option_type` | `n_snapshots`, `quote_valid_ratio` (two-sided, uncrossed), `ltp_ratio`, `greeks_ok_ratio`, `ws_quote_ratio`, `first_seen`, `last_seen`, `reason_counts` |
Per-snapshot, per-strike detail stays in the canonical rows' `quality_flags` (not duplicated). API: `GET /data-quality/coverage-matrix` (§12.2.1). Gate G0.10 requires the matrix for all history; G0.11 requires **zero** unexplained absences.

**Backtest eligibility gate.** `RunConfig.dq` (defaults in `settings.dq_gate`): `min_session_status` (`DEGRADED`), `min_snapshot_coverage_ratio` (Mode C, 0.85), `max_excluded_session_ratio` (0.20), `min_sessions` (20), `require_calendar_verified` (true). At submission the engine computes an `EligibilityReport {sessions_included, sessions_excluded{reason}, calendar_version, status}` and **refuses** the run (`DATA_QUALITY`, 409) when the calendar is `UNVERIFIED` (unless `allow_unverified_calendar=true`, which labels the result `UNVERIFIED_CALENDAR`, forbids `purpose=holdout` and promotion), when included sessions `< min_sessions`, or when excluded sessions exceed the ratio. The report is stored in the manifest and rendered at the top of every report (BACKTESTING_REPORT_SPEC §1).
**Paper start-up gate.** `STARTING` (§8.8.3) requires: calendar `VERIFIED`, feed `OK`, strategy warm-up history present (`warmup_bars` of CLEAN/DEGRADED candles for the last `preflight_warmup_sessions` sessions), a fresh chain when options are required. Continuous protection is RK-17/§8.6.7 (new entries — strategy **and** manual — are blocked when data are unavailable).
**Incomplete-result warnings** shown wherever results are shown: `INCOMPLETE`, `PARTIAL_COVERAGE`, `DEGRADED_SESSIONS_INCLUDED(n)`, `UNVERIFIED_CALENDAR`, `UNVERIFIED_PARAM`, `UNRESOLVED_EXITS(n)`, `AMBIGUOUS_EXITS(n)`, `FRAGILE`, `RISK_RELAXED`, `SYNTHETIC`.
Tests: T-DQ-1 every absence has one code (property test over a synthetic month incl. holidays, outage, failed request); T-DQ-2 holiday ≠ gap; T-DQ-3 matrix totals reconcile with `snapshot_index`; T-DQ-4 gate refuses `UNVERIFIED` calendar; T-DQ-5 gate refuses over-excluded range; T-DQ-6 an executable price is never imputed (a `QUOTE_ONE_SIDED` row cannot reach a fill model).

## 4.5 Canonical schemas (Arrow; single source of truth in code)

### 4.5.1 `candles` (`data/canonical/candles/instrument_id=…/timeframe=…/year=YYYY/part-*.parquet`)
| Column | Type | Null | Notes |
|---|---|---|---|
| `instrument_id` | string | no | `IDX:NIFTY50` |
| `timeframe` | string | no | `1m,3m,5m,15m,1h,4h,1d` |
| `bar_start` | timestamp[us, UTC] | no | |
| `bar_end` | timestamp[us, UTC] | no | clipped at session close |
| `available_at` | timestamp[us, UTC] | no | `= bar_end` historical; live: actual finalisation |
| `session_date` | date32 | no | IST date |
| `open,high,low,close` | float64 | no | |
| `volume` | int64 | yes | |
| `oi` | int64 | yes | |
| `n_constituents` | int16 | yes | for derived bars |
| `is_final` | bool | no | |
| `source` | string | no | `legacy_csv, upstox_hist, derived_1m, live_built` |
| `revision` | int32 | no | 0 original; +1 per provider correction |
| `quality_flags` | list<string> | no | |
| `ingested_at` | timestamp[us, UTC] | no | |
| `schema_version` | int32 | no | 1 |
Primary key: `(instrument_id, timeframe, bar_start, source, revision)`.

### 4.5.2 `option_chain` (`…/option_chain/underlying=NIFTY/session_date=YYYY-MM-DD/part-*.parquet`)
| Column | Type | Null | Notes |
|---|---|---|---|
| `snapshot_id` | string | no | `snap_` + first 16 hex of `sha256("{underlying}abs({expiry}){observed_at_iso}")` |
| `underlying_id` | string | no | `IDX:NIFTY50` |
| `instrument_id` | string | no | structural option id |
| `provider_key` | string | yes | |
| `observed_at` | timestamp[us, UTC] | no | after §4.3 tz resolution |
| `available_at` | timestamp[us, UTC] | no | |
| `session_date` | date32 | no | |
| `expiry_date` | date32 | no | |
| `strike` | int32 | no | |
| `option_type` | string | no | `CE`/`PE` |
| `spot_price` | float64 | yes | |
| `ltp, bid, ask` | float64 | yes | rupees per unit |
| `bid_qty, ask_qty` | int64 | yes | |
| `volume, oi, prev_oi, chng_oi` | int64 | yes | |
| `chng` | float64 | yes | |
| `iv` | float64 | yes | fraction (0.15 = 15%) |
| `delta, gamma, theta, vega` | float64 | yes | |
| `quote_status` | string | no | `OK, ONE_SIDED, EMPTY, CROSSED, NOT_COLLECTED` |
| `ltp_status` | string | no | `OBSERVED, NOT_COLLECTED, MISSING` |
| `greeks_status` | string | no | `OBSERVED, NOT_COLLECTED, MISSING_ZERO_SENTINEL, INVALID` |
| `src_schema` | string | no | `v1,v2,v3,api_v4` |
| `source_file` | string | yes | relative raw path |
| `quality_flags` | list<string> | no | |
| `schema_version` | int32 | no | 1 |

### 4.5.3 `option_quotes` (WebSocket; `…/option_quotes/session_date=YYYY-MM-DD/hour=HH/part-*.parquet`)
`instrument_id, received_at (UTC), source_ts (UTC, nullable), ltp, ltq, bid1, bid1_qty, ask1, ask1_qty, bids list<struct<price:float64,qty:int64>>, asks (same), oi, volume_cum, iv, delta, gamma, theta, vega, available_at (= received_at), quality_flags`. All values are as delivered; `volume_cum` is cumulative and must **never** be summed.

### 4.5.4 `snapshot_index` (one row per attempted snapshot)
`snapshot_id, underlying_id, expiry_date, session_date, observed_at, available_at, request_sent_at (nullable for legacy), response_received_at (nullable), latency_ms, http_status, status (OK|FAILED|PARTIAL), n_rows, n_strikes, src_schema, quality_flags, source_file`.

### 4.5.5 `ticks` (index, live)
`instrument_id, received_at, source_ts, ltp, ltq, cp, flags` — kept for replay and reconciliation.

## 4.6 Resampling (derived timeframes)
Input: canonical 1m candles. Output: `3m,5m,15m,1h,4h,1d` stored as `source='derived_1m'`.
```python
def resample(candles_1m: pd.DataFrame, tf: Timeframe, cal: Calendar) -> pd.DataFrame:
    # 1. For each session_date: (open, close) = cal.session_bounds(d)
    # 2. minute_index = (bar_start - open) / 1min
    # 3. bucket_start = open + floor(minute_index / tf_minutes) * tf   (tf=1d -> open)
    # 4. group by (session_date, bucket_start) in chronological order:
    #      open  = first(open)   high = max(high)   low = min(low)   close = last(close)
    #      volume = sum(volume) if volume_valid else null
    #      oi = last(oi)
    #      n_constituents = count
    #      bar_end = min(bucket_start + tf, close)
    #      available_at = bar_end
    #      quality_flags = union(flags) + ["PARTIAL_BAR"] if n_constituents < expected_constituents
```
`expected_constituents = (bar_end - bucket_start) / 1min`. Buckets never straddle sessions. Result must equal provider-native series except where the native series is wrong; mismatches feed CQ-11.

## 4.7 Provider-semantics checklist (fixtures to capture, ticket T0.10)
Capture from a live session and the API, store under `tests/fixtures/upstox/`, and write findings into `config/data_semantics.yaml`:
| # | Question | Evidence needed | Used by |
|---|---|---|---|
| S1 | Historical candle `timestamp` is bar-open? | First/last bar of a day (09:15 / 15:29 for 1m) | Resample, availability |
| S2 | Does the intraday endpoint include the in-progress minute? | Call at 10:15:30 and inspect last bar | Live reconciliation |
| S3 | Index candle volume: zero, null or meaningful? | Sample | `volume_valid` |
| S4 | Index candle OI present? | Sample | features |
| S5 | WS `ltpc.ltt` unit and relation to receive time | 1,000 ticks | Candle builder bucket time |
| S6 | WS option `vtt` (volume) cumulative within the day? | Monotonic check | Volume bars |
| S7 | WS index tick frequency | Ticks/min | `feed_stale_s` |
| S8 | Option-chain API IV unit (percent vs fraction) | ATM sample | OQ-09 |
| S9 | Option-chain `prev_oi`, `chng` semantics | Compare vs prior day | features |
| S10 | Maximum instruments per `full` subscription for this account | Docs + test | recorder |
| S11 | Option-chain call frequency floor | Soak test at 30 s for 2 hours | collector |
| S12 | Greeks `0` values: real or sentinel? | Count zeros by moneyness | OQ-10 |

## 4.8 Repository contracts (`market_data.contracts`)
```python
@dataclass(frozen=True)
class CoverageReport:
    expected: int; present: int; missing_intervals: list[tuple[datetime, datetime]]; flags: Counter[str]; status: Literal["CLEAN","DEGRADED","UNUSABLE","UNVERIFIED"]

class CandleRepository(Protocol):
    def get(self, instrument_id: str, tf: Timeframe, start: datetime, end: datetime, *,
            as_of: datetime | None = None, source: str = "preferred",
            strict: bool = False, allow_partial: bool = True) -> pd.DataFrame: ...
    # Returns rows with bar_start in [start,end) AND available_at <= as_of (if given), sorted by bar_start.
    # source="preferred": upstox_hist/legacy_csv over derived_1m over live_built, per bar, highest revision.
    # strict=True: raises DataUnavailableError if CoverageReport.missing_intervals non-empty.
    def last_available(self, instrument_id: str, tf: Timeframe, as_of: datetime) -> CandleRow | None: ...
    def coverage(self, instrument_id: str, tf: Timeframe, start: date, end: date) -> CoverageReport: ...

@dataclass(frozen=True)
class SnapshotView:
    snapshot_id: str; observed_at: datetime; available_at: datetime; expiry_date: date; spot_price: float | None
    rows: pd.DataFrame            # canonical columns, one row per contract
    age_s: float                  # as_of - available_at

class OptionChainRepository(Protocol):
    def snapshot_as_of(self, underlying_id: str, expiry: date, as_of: datetime, *, max_age_s: int | None) -> SnapshotView | None: ...
    def next_snapshot_after(self, underlying_id: str, expiry: date, t: datetime, *, max_wait_s: int) -> SnapshotView | None: ...
        # first snapshot with available_at >= t, only if available_at - t <= max_wait_s
    def snapshots_between(self, underlying_id: str, start: datetime, end: datetime, expiry: date | None = None) -> Iterator[SnapshotView]: ...
    def snapshot_index(self, session_date: date) -> pd.DataFrame: ...

class QuoteRepository(Protocol):
    def quote_as_of(self, instrument_id: str, as_of: datetime, *, max_age_s: float) -> QuoteRow | None: ...
    def next_quote_after(self, instrument_id: str, t: datetime, *, max_wait_s: float) -> QuoteRow | None: ...
```
`next_*_after` exist **only** for fill simulation (they look forward from an order timestamp by design); features and strategies receive the as-of-only interface `AsOfView` (§5.3) that cannot call them.

DuckDB: one read-only connection per process; views `v_candles`, `v_option_chain`, `v_option_quotes` created from Parquet globs with Hive partitioning; every query filters on partition columns first.

## 4.8.1 [v1.2] Additional repository contracts — status: DESIGNED
Chart, replay, strategies, visualization and reports read market data, features, trade events and results **only** through these contracts. No UI-facing or strategy code opens CSV/Parquet files or a DuckDB connection (import-linter forbids `duckdb`, `pyarrow.parquet` and `csv` outside `market_data.repository` and `ml.datasets`). All of them carry the same causal rule: **`as_of` is mandatory wherever time is involved** and rows with `available_at > as_of` are never returned.
```python
class QuoteRepository(Protocol):                       # additions to §4.8
    def quotes_between(self, instrument_id: str, start: datetime, end: datetime, *,
                       as_of: datetime, limit: int = 5000, cursor: str | None = None) -> QuotePage: ...
    def quote_coverage(self, session_date: date, instrument_ids: Sequence[str] | None = None) -> list[QuoteCoverageRow]: ...
    # QuoteCoverageRow: instrument_id, ticks_by_hour, max_silence_s, first_received_at, last_received_at

class FeatureSeriesRepository(Protocol):               # research.features.contracts
    def series(self, instrument_id: str, tf: str, start: datetime, end: datetime, columns: Sequence[ColumnRef], *,
               as_of: datetime, version_pins: Mapping[str, str] | None = None) -> FeatureSeries: ...
        # computed by FeatureEngine (same code as strategies); unavailable pinned version => VERSION_UNAVAILABLE, never a silent newer version
    def deployment_series(self, deployment_id: str, start: datetime, end: datetime) -> FeatureSeries: ...
        # the values the deployment actually saw (persisted rows, §5.1.9); flag source="PERSISTED"

class TradeEventRepository(Protocol):                  # simulation.contracts (reads Postgres only)
    def chains(self, *, account_id: str | None = None, deployment_id: str | None = None,
               start: datetime | None = None, end: datetime | None = None,
               strategy_version: int | None = None, instrument: str | None = None,
               state: Literal["OPEN","CLOSED"] | None = None, limit: int = 1000, cursor: str | None = None) -> TradeChainPage: ...
    def chain(self, chain_id: str) -> TradeChain: ...

class ResultRepository(Protocol):                      # simulation.contracts
    def run(self, run_id: str) -> RunRecord: ...
    def artifact(self, run_id: str, name: str, *, limit: int, cursor: str | None) -> ArtifactPage: ...
    def metric_detail(self, run_id: str, metric_id: str) -> MetricDetail: ...      # §8.10.5
```
```python
class TradeChain(BaseModel):          # one entry→exit round trip; markers are derived from persisted rows only
    chain_id: str                     # = correlation_id of the entry decision (strategy) or the manual order
    origin: Literal["MANUAL","STRATEGY"]; account_id: str; deployment_id: str | None
    strategy_id: str | None; strategy_name: str | None; strategy_version: int | None; spec_hash: str | None
    direction: Direction | None
    instrument: {instrument_id, expiry: date, strike: int, option_type: Literal["CE","PE"], lot_size: int}
    strategy_timeframe: str | None
    signal_bar_start: datetime | None; signal_at: datetime | None              # DECISION, not an order
    entry: LegTimes; exit: LegTimes | None                                      # see below
    indicators: dict[str, float | None]                                         # decisions.feature_snapshot at signal (entry) / exit decision
    feature_pins: list[FeaturePin]
    levels: list[LevelRecord]                                                   # STOP/TARGET/TRAIL: basis, price, price_space, set_at, hit_at
    underlying_ref: {signal_px: float | None, entry_fill_px: float | None, exit_fill_px: float | None}   # chart anchors only
    qty_units: int; exit_reason: ReasonCode | None
    pnl: {gross_paise: int, charges_paise: int, net_paise: int} | None          # None while OPEN; always from that account's ledger
    state: Literal["OPEN","CLOSED"]; flags: list[str]
class LegTimes(BaseModel):            # signal ≠ order ≠ fill: three separate facts
    decision_id: str | None; order_id: str
    order_created_at: datetime; order_accepted_at: datetime | None
    fills: list[{fill_id, filled_at, qty_units, price_paise, fill_source, fill_model}]
```
Markers are rendered from `TradeChain` rows; a marker without a persisted `fill_id` (or, for a SIGNAL glyph, a persisted `decision_id`) is a defect (T-VZ-3).

## 4.9 Collectors
### 4.9.1 Rate limiter (`collectors/rate_limiter.py`)
Token buckets for Upstox standard APIs: 50/s, 500/min, 2000/30 min (all three must have tokens). Budget split: `snapshot collector` ≤ 1,200 per 30 min (needs ≈ 60 per 30 min); `historical fetcher` uses the remainder; `orders` (Phase 9) separate 10/s bucket. Exceeding a bucket blocks (never drops) with jittered wait; HTTP 429 → exponential backoff 2,4,8,… up to 60 s and `ExternalServiceError` after 5 attempts.

### 4.9.2 Token manager (`collectors/token_manager.py`)
- Token file: `data/secrets/upstox_token.json` `{access_token, obtained_at, expires_at}`; created by `python -m quantview.apps.auth_login` (OAuth code flow with a localhost redirect). No credentials beyond API key/secret are stored.
- Upstox access tokens expire daily (≈ 03:30 IST) `[VERIFY]`; collectors check expiry before each tick and on 401. If expired: log `TOKEN_EXPIRED`, raise alert, sleep 60 s, re-read file (so the owner can re-login without restarting). Evaluate Upstox "extended token" for read-only data `[VERIFY]`; adopt only after confirming scope and terms.

### 4.9.3 Option-snapshot collector (`apps/collect_snapshots.py`)
```
on start: calendar.is_session(today) else exit(0); wait until 09:10 IST
loop until 15:35 IST:
    tick = ceil_to_grid(now, 30 s, offset=3 s)           # :03 and :33 past each minute (matches later legacy files)
    sleep until tick
    expiry = ExpiryRules.nearest_expiry(today, cal)       # nearest weekly >= today
    t_req = now(); resp = GET /v2/option/chain?instrument_key=NSE_INDEX|Nifty 50&expiry_date=expiry   [VERIFY params]
    t_resp = now()
    write raw json.gz (immutable) ; parse -> canonical rows ; append to buffer
    write snapshot_index row (status OK/FAILED, latency)
    retries: on HTTP 5xx/timeout retry at +2 s and +5 s only if still before next tick - 3 s
    heartbeat file update (last_success_at, consecutive_failures)
every 10 minutes: flush buffer -> part-<HHMM>.parquet
on stop/crash: raw JSON files remain; EOD job rebuilds missing canonical parts
```
Timeouts: connect 3 s, read 10 s. If `consecutive_failures ≥ 10` → alert. Never poll faster than 30 s (constraint C2).

**[v1.1] Two expiries.** `snapshot_collector.expiries` defaults to `[NEAREST, NEXT]` (`NEXT` = the weekly expiry after the nearest). Within each 30 s period the NEAREST request runs at the grid time (`offset_s`), the NEXT request `next_offset_s` (default 12 s) later, each with its own raw JSON, canonical partition and `snapshot_index` row. Cost ≈ 60 extra calls per 30 minutes, inside the 1,200 budget. Constraint C2 (about one call per 30 s) is believed to apply per request target; **T0.8 must verify** this against the provider. If the NEXT call triggers server errors, the collector disables it for the session, records `NEXT_EXPIRY_DISABLED` in the heartbeat and continues with NEAREST only. Purpose: overnight and roll-over strategies, the `NEXT` expiry policy, and monthly-expiry research.


### 4.9.4 Historical candle fetcher (`collectors/historical_fetcher.py`)
EOD job: for the session date `d`, fetch 1m candles for `IDX:NIFTY50` (and native `5m,15m,1h,4h,1d` for reconciliation only) via `GET /v3/historical-candle/...` `[VERIFY]` parameter format. Store raw JSON gz, parse via `upstox_api.py`, write canonical with `source='upstox_hist'`. Fetch is idempotent: if canonical rows for `d` exist with identical OHLC, skip; if differing, write `revision+1` and a reconciliation record. Hard rule: **never overwrite** an existing file or row.

**[v1.1] Futures candles.** The EOD job also fetches 1m candles (with volume and open interest where the provider returns them) for the current near-month NIFTY future `FUT:NIFTY:<expiry>` through the same endpoint family `[VERIFY: expired contracts need Plus; the current contract should be available]`, stored raw → canonical with `source='upstox_hist'`, never overwritten. History therefore begins when this job first runs, plus whatever look-back the provider returns for the live contract. Futures are data only (ADR-021): no orders, no contract selection, no ledger.


## 4.10 Live subsystem (`apps/collect_live.py`)
### 4.10.1 Connection
1. `GET /v3/feed/market-data-feed/authorize` → `authorized_redirect_uri` `[VERIFY]`.
2. Connect with `websockets`; send binary-encoded JSON subscribe message `{"guid": "<uuid>", "method": "sub", "data": {"mode": "<mode>", "instrumentKeys": [...]}}`.
3. Decode with the vendored Upstox `MarketDataFeedV3.proto` (record the source URL and commit hash in `market_data/live/proto/PROVENANCE.md`).
4. Subscriptions: `NSE_INDEX|Nifty 50` in `ltpc`; in `full`: option contracts for the nearest weekly expiry, ATM ± `N=10` strikes both CE and PE (≤ 42 keys); **[v1.1]** the near-month NIFTY future (1 key); **[v1.1] pinned keys** — the instrument key of every contract with an open paper (later live) position — **[v1.2] union over all ACTIVE paper accounts, strategy and manual** — loaded from Postgres at process start (before 09:15) and refreshed on every fill. A pinned key is never unsubscribed while its position is open, even if its strike leaves the band or its expiry is not the nearest weekly. Re-centre when `|spot − centre| ≥ 2 × strike_step`: subscribe new keys, unsubscribe stale unpinned ones, never both lists empty. If the total exceeds the provider cap `[VERIFY S-limits]`, shrink `N` first; never drop the index, the future or pinned keys. Recorded per `full` message: ltp, ltq, cumulative volume, oi, 5 bid and 5 ask levels (price, quantity, orders), Greeks where present, `source_ts`, `received_at`.
5. Reconnect policy: delays `1,2,4,8,16,30` s then 30 s, ±20% jitter; after reconnect, resubscribe and require a tick within 5 s else cycle. Index stale if no tick for `feed_stale_s = 10` during session; options stale per instrument after 30 s.

### 4.10.2 Tick validation
Reject-to-log (not applied) if: unknown instrument; `ltp ≤ 0`; `source_ts` more than 10 s before `received_at` or 2 s after (`CLOCK_SKEW`); `source_ts` earlier than the instrument's last applied `source_ts` (`OUT_OF_ORDER`). All raw messages are written to the `ticks` raw log regardless.

### 4.10.3 Live candle builder (`live/candle_builder.py`)
State per (instrument, tf=1m): `bucket_start, o,h,l,c, n_ticks, last_cum_vol_before_bar, first_ts, last_ts`.
```
on_tick(t):
    ts = t.source_ts if valid else t.received_at
    if not cal.in_session(ts): store tick only; return
    bs = bucket_start(ts, 1m)
    if state is None: start(bs, price) and flag PARTIAL_BAR if ts - bs > 5 s     # joined mid-bar
    elif bs == state.bucket_start: update h,l,c,n_ticks
    elif bs > state.bucket_start: finalize(state, now); start(bs, t.ltp)
    else: LATE tick (bs < current): drop from candle, flag LATE_TICK, keep in tick log
timer every 250 ms:
    if now >= state.bar_end + grace_s (2 s) and not finalized: finalize(state, now)
finalize(state, now):
    if state.n_ticks == 0: emit candle.missing (no fabricated bar)
    else: emit candle.finalized with open=first tick price, available_at=max(bar_end, now), is_final=True, source='live_built'
          append canonical row; publish event
provisional: emit candle.provisional at most every 500 ms while the bar forms
```
Volume for instruments with cumulative volume: `bar_volume = cum_at_last_tick − cum_before_bar` (never summed). Index volume is null unless S3 shows it is valid.
Restart mid-session: state is not restored; the first bar is `PARTIAL_BAR`; strategies with `allow_partial_bars=false` skip it. Gaps > 60 s of feed silence add `FEED_GAP` to affected bars.

### 4.10.4 Quote recorder (`live/quote_recorder.py`)
Consumes `full`-mode messages for subscribed options; appends rows to an in-memory buffer; flushes Parquet every 60 s (and on shutdown) into `…/hour=HH/part-<ts>.parquet`. Backpressure: bounded queue (50k); on overflow drop oldest *derived* work, never the raw log; increment metric `quotes_dropped`.

### 4.10.5 Event transport **[v1.2: replaced by §2.7]**
`collect_live` writes CONTROL events (`candle.finalized`, `candle.missing`, `option.snapshot` metadata, `feed.state_changed`, `producer.restarted`, `kill_switch.changed`) to the **durable journal** with fsync before publishing (§2.7.3). TELEMETRY (`candle.provisional`, `option.quote`, `feed.health`, ticks) is published as newline-delimited JSON `EventEnvelope`s on TCP `127.0.0.1:<settings.event_bus_port>` with a per-stream contiguous `seq`; it is never replayed and a gap means *stale* (§2.7.1). `paper-runner` and `api` connect as clients with reconnect and read CONTROL events from the journal with checkpoints (§2.7.4). Dev mode may run in one process, but the in-memory bus must use the same journal interface (journal in a temp directory) so tests exercise the production path.

### 4.10.6 [v1.1] Volume and retention budget
`apps/collect_live` writes `data/ops/ws_budget_YYYY-MM-DD.json` every session: `{rows_total, rows_by_instrument, msgs_per_second_p50_p95_max, raw_mb_compressed, derived_1s_mb, dropped_quotes}`. Gate G0.8 requires at least 5 such files and a recorded estimate of annual size. Derived **1-second quote bars** (last bid/ask/ltp, update count, summed 5-level depth, cumulative-volume delta) are written alongside the raw ticks and kept permanently; raw tick Parquet is immutable (P5). Settings: `live.ws_daily_budget_mb` (default 500): exceeding it raises an alert; nothing is silently dropped except per the bounded-queue rule in §4.10.4. Retention beyond 12 months of raw ticks is an owner decision taken from the measured numbers (new ADR).


## 4.11 Reconciliation (`reconcile.py`)
For each session date `d` after close: join `live_built` 1m with `upstox_hist` 1m on `bar_start`.
| Check | Tolerance (defaults, **[OWNER]**, tune after 10 sessions then freeze by ADR) | Result |
|---|---|---|
| `abs(open_live − open_hist)` | ≤ 1.0 point | `OK` / `DIFF` |
| `abs(close_live − close_hist)` | ≤ 1.0 point | |
| `abs(high_live − high_hist)`, `abs(low_live − low_hist)` | ≤ 2.0 points | |
| Bar present in hist but missing live | — | `MISSED_LIVE` |
| Bar present live but missing hist | — | `MISSED_HIST` |
Session passes if ≥ 99% of bars are `OK`. Output: `data/quality/reconciliation/date=d/part.parquet` + summary JSON. **No decision history is rewritten.** Backtests use the `upstox_hist` series; replay of paper days uses `live_built`.

## 4.12 EOD pipeline (`apps/eod.py`) — ordered, idempotent
1. Verify raw manifests. 2. Fetch historical candles (§4.9.4). 3. Parse/canonicalise any unparsed raw option files. 4. Compact today's option partitions into `part-0.parquet` (keep the small parts for 7 days). 5. Resample derived timeframes for today. 6. Run DQ rules; write status. 7. Reconciliation (§4.11). 8. Backup job. 9. Write `data/quality/eod_summary_<date>.json` and exit non-zero if any ERROR-level result.

## 4.13 Market-data tests
| ID | Test |
|---|---|
| T-MD-1 | Each parser: golden-file test per schema version (3 legacy + API + candle) with expected Arrow table |
| T-MD-2 | `parse_loose_date("2026-02-3") == date(2026,2,3)`; folder discovery returns the three non-padded expiries |
| T-MD-3 | Zero-sentinel Greeks become null with `MISSING_ZERO_SENTINEL`; real small Greeks remain |
| T-MD-4 | v2 rows have `ltp` null and `ltp_status=NOT_COLLECTED` |
| T-MD-5 | `candles.get(as_of=t)` never returns a row with `available_at > t` (property test over random `t`) |
| T-MD-6 | Resample reproduces hand-computed 5m/1h/4h bars for a fixture day, including last partial bars |
| T-MD-7 | Candle builder: tick sequences covering normal bar, empty bar (→ `candle.missing`), late tick, mid-bar start, boundary tick exactly at `bar_end` |
| T-MD-8 | Reconnect test with a fake WS server dropping connection; no fabricated candles during outage |
| T-MD-9 | Rate limiter never exceeds 50/s, 500/min, 2000/30 min over a simulated 40-minute load |
| T-MD-10 | Raw archive refuses overwrite; manifest mismatch is detected |
| T-MD-11 | Option timezone test (§4.3) passes on a synthetic fixture with known shift and fails when shift is ambiguous |
| T-MD-12 | Snapshot collector grid: ticks fall on `:03/:33`; skipped tick records `FAILED` row, not a silent gap |

---

# 5. Feature engine (`quantview.research.features`)

## 5.1 Contracts

### 5.1.1 Bar input
Features consume completed bars only. Each bar passed to a feature has:
`seq` (int, position in the continuous expected-bar timeline of the calendar; consecutive expected bars differ by 1, overnight does **not** add expected bars), `bar_start`, `bar_end`, `available_at`, `session_date`, `open, high, low, close`, `volume` (nullable), `oi` (nullable), `is_session_first` (bool), `quality_flags`.

### 5.1.2 Feature definition
```python
@dataclass(frozen=True)
class FeatureDef:
    name: str                       # "ema"
    version: str                    # "1.0.0" (semver; bump on any numeric change)
    family: Literal["price","trend","volatility","volume","session","levels","option","transform"]
    param_order: tuple[str, ...]    # order used in column names
    defaults: dict[str, Any]
    inputs: tuple[str, ...]         # e.g. ("close",) or ("high","low","close")
    outputs: tuple[str, ...]        # ("value",) or ("macd","signal","hist")
    depends_on: tuple[FeatureRef, ...] = ()
    warmup_bars: Callable[[dict], int]            # bars required before first valid value
    lookback_bars: Callable[[dict], int]          # span used for the gap test (defaults to warmup_bars)
    session_anchored: bool = False                # resets at each session start
    requires_volume: bool = False
    batch: Callable[[BarFrame, dict], pd.DataFrame]
    incremental: type[IncrementalFeature]
    reference_fixture: str                        # path to hand-checked fixture
    # [v1.2] display: tuple[SeriesDisplay, ...]; explain: FeatureExplain; repaints: bool = False; depends_on_completed_bars: bool = True   (§5.1.9)
```
```python
class IncrementalFeature(Protocol):
    def __init__(self, params: dict): ...
    def update(self, bar: Bar) -> dict[str, float | int | None]: ...   # one call per completed bar, in order
    def reset_session(self) -> None: ...                                # called at session start if session_anchored
```

### 5.1.3 Column naming
`col = name + "_" + "_".join(str(params[p]) for p in param_order)`; multi-output adds `__<output>`.
Examples: `ema_close_21`, `rsi_14_close`, `macd_12_26_9_close__hist`, `bbands_20_2.0_close__upper`. Params with floats use Python `repr` (`2.0`). Every feature column has a sibling validity column `<col>__ok` (bool) — see §5.1.4.

### 5.1.4 Readiness and gap rule (applies to every feature unless it states otherwise)
- `warmup_ok`: number of bars seen ≥ `warmup_bars(params)`.
- `gaps_in_lookback = (seq_t − seq_{t−L+1}) − (L − 1)` where `L = lookback_bars` and `seq_{t−L+1}` is the bar L−1 positions back among **present** bars (the number of expected bars missing inside the window).
- `ok = warmup_ok and gaps_in_lookback ≤ gap_tolerance` with `gap_tolerance = 2` **[OWNER]**.
- Value is computed on the present-bar sequence regardless; when `ok` is false the value is emitted as `NaN`/`None` with reason code `NOT_READY` or `GAP_IN_WINDOW` in the metadata channel.
- Recursive features (EMA, RMA/Wilder, MACD, ADX, Supertrend, EWMA vol) carry state across gaps ≤ `gap_tolerance`; if a gap exceeds the tolerance they **reset** (state cleared, warm-up restarts) and the event is logged.
- Price features are continuous across sessions (the overnight move is included in returns and true range). `session_anchored` features reset at session start.

### 5.1.5 Availability rule
A bar-based feature value for bar `b` becomes available at `b.available_at` (= `b.bar_end`). It may be used for decisions at `decision_at ≥ b.available_at`. Option-chain features become available at `snapshot.available_at`.

### 5.1.6 Batch/incremental parity
Both implementations must produce identical outputs for identical input: `np.testing.assert_allclose(batch, incremental, rtol=1e-9, atol=1e-9, equal_nan=True)` on the 1,000-bar synthetic fixture and on one real 20-session slice. Recommended implementation: write the incremental class first; batch may be NumPy/pandas vectorised **only** if parity passes; otherwise batch simply loops the incremental class.

### 5.1.7 Truncate-and-recompute (look-ahead test, mandatory for every feature)
```python
def test_no_lookahead(feature, params, bars, probes=range(100, 1000, 37)):
    full = feature.batch(bars, params)
    for t in probes:
        part = feature.batch(bars.iloc[: t + 1], params)
        np.testing.assert_allclose(full.iloc[t].to_numpy(float), part.iloc[-1].to_numpy(float),
                                   rtol=1e-9, atol=1e-9, equal_nan=True)
```
Plus the **poisoned-future test**: replace `bars.iloc[t+1:]` with NaN; outputs at rows ≤ t must be unchanged.

### 5.1.8 Registry and caching
`FeatureRegistry.get(name)`, `.catalogue()` returns JSON for the UI (name, family, params with defaults/types/min/max, outputs, warmup, description). Computation results are cached at `data/derived/features/<sha256(feature versions + params + data_version)>/part.parquet`; `data_version` = hash of the manifest of the input candle partitions.

### 5.1.9 [v1.2] Feature display metadata, explanation and persisted deployment series — status: DESIGNED
`FeatureDef` (§5.1.2) gains the fields below so the chart can show exactly what a strategy computed without the UI knowing any formula:
```python
class SeriesDisplay(BaseModel):
    output: str                                   # one of FeatureDef.outputs, e.g. "hist"
    label: str; unit: Literal["price","points","percent","ratio","count","level","none"]
    kind: Literal["line","histogram","band_upper","band_lower","step","points"]
    placement: Literal["OVERLAY","PANE"]; pane_group: str | None     # outputs sharing one pane (macd, signal, hist)
    scale: dict | None                            # e.g. {"min":0,"max":100,"guides":[30,70]} for RSI
    default_style: {color_role: str, width: int, dash: str | None}; default_visible: bool = True
class FeatureExplain(BaseModel):                  # required for every catalogue feature
    formula_text: str; formula_tex: str; variables: list[{symbol, meaning, unit}]; notes: list[str]
# added to FeatureDef:
#   display: tuple[SeriesDisplay, ...]
#   explain: FeatureExplain
#   repaints: bool = False            # True only if a value already published for a completed bar can change later
#   depends_on_completed_bars: bool = True
```
- **Repaint rule.** All catalogue features are `repaints=False`. A custom (Python/ported) feature with `repaints=True` is rejected by strategy validation (`REPAINTING_FEATURE`) and is chart-only, labelled "may repaint".
- **Feature pins.** `required_feature_pins(spec)` (called by `POST /strategies/validate`, §12.2) returns `FeaturePin{column, name, version, params, timeframe, outputs, warmup_bars}` for every column the strategy reads after `$param` substitution. A deployment stores its pins in `deployments.feature_pins` and in the config snapshot. `FeatureRegistry.get(name, version)` keeps **every released version** of a feature implementation (old numeric behaviour is never deleted), so a pin remains computable.
- **Explanation.** `GET /features/{name}/explain?version=` returns name, version, parameters (defaults, ranges), inputs, outputs, warm-up and `FeatureExplain`. Test T-FE-11: every catalogue feature has `explain` + `display`, and `explain.formula_text` is generated from the same doc-block the fixture test imports (no free-floating copy).
- **Persisted deployment series (source of truth for the chart).** After each decision the paper runner upserts one row per strategy-timeframe bar to `data/derived/paper_features/deployment_id=<id>/date=YYYY-MM-DD/part.parquet`: `bar_start, <columns>, <col>__ok, reasons, feature_versions_hash`. The chart displays **these rows** (`source="PERSISTED"`), not a fresh recomputation, so it shows the values the strategy actually used even if live-built bars were later revised by reconciliation (§4.11). If rows are missing (e.g. runner down) the API may recompute with the pinned versions and flags the series `RECOMPUTED`; if a pinned version cannot be loaded it returns `VERSION_UNAVAILABLE` and the chart shows nothing rather than a different formula (T-FE-12).
- **Timeframe rule on the chart.** A series is drawn on a chart whose timeframe equals the deployment's strategy timeframe. On a lower-timeframe chart it is drawn as a step line that changes only at `available_at` of the strategy bar (causal, §5.4.8); on a higher-timeframe chart it is not drawn and the legend says why.

## 5.2 As-of view given to strategies
```python
class AsOfView:
    now: datetime
    def bar(self, tf: str, offset: int = 0) -> Bar | None            # last completed bar (offset 0) or earlier
    def f(self, col: str, tf: str | None = None, offset: int = 0) -> float | None   # value or None if not ok
    def ok(self, cols: Sequence[str], tf: str | None = None) -> bool
    def chain(self) -> ChainView | None                              # latest snapshot as-of now (age-checked)
    def session(self) -> SessionInfo                                 # open/close, minutes since open/to close
```
`AsOfView` has no method that looks forward and no access to repositories. `tf=None` means the strategy's base timeframe. For a higher timeframe, the view returns the latest HTF bar with `available_at ≤ now` (MTF rule, §5.4.8).

## 5.3 Notation
`x_t` = current completed bar value; `x_{t−k}` = k bars earlier; `src` ∈ {open, high, low, close, hl2=(h+l)/2, hlc3=(h+l+c)/3, ohlc4=(o+h+l+c)/4}. `SMA_n(x)_t = (1/n) Σ_{i=0}^{n−1} x_{t−i}`. `NaN` = not ready.

## 5.4 Catalogue (v1 — build exactly these, in this order)

### 5.4.1 Price, returns and candle geometry (family `price`)
| Feature | Params (default) | Formula | Warm-up | Notes |
|---|---|---|---|---|
| `ret` | n=1 | `close_t / close_{t−n} − 1` | n+1 | fraction |
| `logret` | n=1 | `ln(close_t / close_{t−n})` | n+1 | |
| `session_gap_pct` | — | `open_first_bar_of_session / close_last_bar_of_prev_session − 1`, constant for all bars of the session | needs prior session | session-constant |
| `body` | — | `close − open` | 1 | |
| `range` | — | `high − low` | 1 | |
| `upper_wick` | — | `high − max(open, close)` | 1 | |
| `lower_wick` | — | `min(open, close) − low` | 1 | |
| `body_ratio` | — | `abs(close − open) / (high − low)`; NaN if range = 0 | 1 | |
| `close_loc` | — | `(close − low) / (high − low)`; NaN if range = 0 | 1 | |
| `candle_dir` | — | `sign(close − open)` ∈ {−1, 0, +1} | 1 | |
| `streak` | — | if `dir_t = 0`: 0; elif `dir_t = dir_{t−1}`: `streak_{t−1} + dir_t`; else `dir_t` | 1 | signed run length |
| `prior_high` | n=20 | `max(high_{t−n..t−1})` (**excludes** current bar) | n | |
| `prior_low` | n=20 | `min(low_{t−n..t−1})` (excludes current) | n | |
| `breakout_up` | n=20 | `1 if close_t > prior_high_n else 0` | n | uses prior bars only |
| `breakout_down` | n=20 | `1 if close_t < prior_low_n else 0` | n | |
| `dist_prior_high` | n=20 | `close_t − prior_high_n` | n | points |
| `dist_prior_low` | n=20 | `close_t − prior_low_n` | n | points |
| `donchian` | n=20 | outputs `upper = max(high_{t−n+1..t})`, `lower = min(low_{t−n+1..t})`, `mid = (upper+lower)/2` (**includes** current bar) | n | name says "donchian", not "prior": inclusion differs on purpose |

### 5.4.2 Trend and momentum (family `trend`)
| Feature | Params (default) | Definition (exact) | Warm-up |
|---|---|---|---|
| `sma` | src=close, n=20 | `SMA_n(src)_t` | n |
| `ema` | src=close, n=20 | `α = 2/(n+1)`. First value at bar n−1 (0-based) = `SMA_n(src)`; then `EMA_t = α·src_t + (1−α)·EMA_{t−1}` | n |
| `rma` | src=close, n=14 | Wilder: `α = 1/n`. First value = `SMA_n(src)`; then `RMA_t = (RMA_{t−1}·(n−1) + src_t)/n` | n |
| `macd` | fast=12, slow=26, signal=9, src=close | `macd = EMA_fast − EMA_slow` (each seeded as above); `signal = EMA_signal(macd)` seeded by `SMA_signal` of the first `signal` valid macd values; `hist = macd − signal`. Outputs `macd, signal, hist` | slow + signal − 1 |
| `rsi` | n=14, src=close | `Δ_t = src_t − src_{t−1}`; `gain = max(Δ,0)`; `loss = max(−Δ,0)`. First `AG, AL` = simple mean of the first n gains/losses (available at bar index n); then `AG_t = (AG_{t−1}(n−1)+gain_t)/n`, same for AL. `RSI = 100 − 100/(1 + AG/AL)`; if `AL = 0`: `RSI = 100` when `AG > 0`, else `50` | n+1 |
| `roc` | n=10, src=close | `100·(src_t / src_{t−n} − 1)` | n+1 |
| `mom` | n=10, src=close | `src_t − src_{t−n}` | n+1 |
| `adx` | n=14 | `up = high_t − high_{t−1}`, `dn = low_{t−1} − low_t`; `+DM = up if up>dn and up>0 else 0`; `−DM = dn if dn>up and dn>0 else 0`; `TR` as in 5.4.3. Wilder sums: first `S = Σ` of first n values (bar index n), then `S_t = S_{t−1} − S_{t−1}/n + x_t` for TR, +DM, −DM. `+DI = 100·S(+DM)/S(TR)`, `−DI = 100·S(−DM)/S(TR)`, `DX = 100·abs(+DI − −DI)/(+DI + −DI)` (0 if denominator 0). First `ADX` = mean of the first n DX (bar index 2n−1), then `ADX_t = (ADX_{t−1}(n−1)+DX_t)/n`. Outputs `adx, plus_di, minus_di` | 2n |
| `supertrend` | n=10, mult=3.0 | `ATR_n` (Wilder), `hl2`, `bu = hl2 + mult·ATR`, `bl = hl2 − mult·ATR`. `fu_t = bu_t if (bu_t < fu_{t−1} or close_{t−1} > fu_{t−1}) else fu_{t−1}`; `fl_t = bl_t if (bl_t > fl_{t−1} or close_{t−1} < fl_{t−1}) else fl_{t−1}`. Init (first valid bar): `fu=bu, fl=bl`, `dir = +1 if close ≥ hl2 else −1`, `st = fl if dir=+1 else fu`. Next: if `dir_{t−1} = −1`: `dir_t = +1 if close_t > fu_t else −1`; if `dir_{t−1} = +1`: `dir_t = −1 if close_t < fl_t else +1`; `st_t = fl_t if dir_t=+1 else fu_t`. Outputs `st, dir` | n |
| `dist_sma_pct` | n=20, src=close | `100·(src_t − SMA_n)/SMA_n` | n |

### 5.4.3 Volatility (family `volatility`)
| Feature | Params (default) | Definition | Warm-up |
|---|---|---|---|
| `tr` | — | `max(high−low, abs(high − close_{t−1}), abs(low − close_{t−1}))`; first bar: `high − low` | 1 |
| `atr` | n=14 | `RMA_n(TR)`; seed = SMA of first n TR | n |
| `atr_pct` | n=14 | `100·ATR_n / close_t` | n |
| `stdev_ret` | n=20 | sample std (ddof=1) of `logret(1)` over the last n returns | n+1 |
| `realized_vol` | n=20 | `stdev_ret_n · sqrt(252·375/tf_minutes)` (annualised fraction; `tf_minutes` = base timeframe in minutes; for 1d: `sqrt(252)`) | n+1 |
| `parkinson` | n=20 | `sqrt( (1/(4·n·ln 2)) · Σ_{i<n} (ln(high_{t−i}/low_{t−i}))² )` per-bar | n |
| `garman_klass` | n=20 | `sqrt( (1/n) · Σ_{i<n} [0.5·(ln(high/low))² − (2 ln 2 − 1)·(ln(close/open))²] )` per-bar | n |
| `ewma_vol` | lam=0.94 | `r_t = logret(1)`; seed `σ²` = mean of `r²` over first 20 returns; `σ²_t = lam·σ²_{t−1} + (1−lam)·r_t²`; output `sqrt(σ²_t)` per-bar | 21 |
| `bbands` | n=20, k=2.0, src=close | `mid = SMA_n`; `sd` = **population** std (ddof=0) over n; `upper = mid + k·sd`, `lower = mid − k·sd`; `width = (upper − lower)/mid`; `pctb = (src − lower)/(upper − lower)` (NaN if equal). Outputs `mid, upper, lower, width, pctb` | n |

### 5.4.4 Generic transforms (family `transform`; apply to any numeric feature column `x`)
| Feature | Params | Definition |
|---|---|---|
| `rank` | w=252 | `count(x_{t−w..t−1} < x_t) / w` — percentile among the **previous** w values (excludes current) |
| `zscore` | w=60 | `(x_t − mean(x_{t−w+1..t})) / std0(x_{t−w+1..t})` (ddof=0; NaN if std 0) |
| `diff` | k=1 | `x_t − x_{t−k}` |
| `lag` | k=1 | `x_{t−k}` |
| `cross_state` | a, b | `+1` if `a_t > b_t`, `−1` if `a_t < b_t`, `0` if equal (used by the strategy evaluator for crosses) |

### 5.4.5 Session and calendar (family `session`, no price input)
| Feature | Definition |
|---|---|
| `min_since_open` | `(available_at − session_open) / 60 s` (09:16 bar-end → 1.0 for a 1m bar) |
| `min_to_close` | `(session_close − available_at) / 60 s` |
| `dow` | Monday = 0 … Friday = 4 |
| `is_weekly_expiry_day` | 1 if `session_date` equals the actual weekly expiry (§3.4) for that week |
| `is_monthly_expiry_day` | 1 if `session_date` equals the monthly expiry |
| `expiry_regime` | 0 if `session_date` < 2025-09-01 (Thursday regime), else 1 (Tuesday regime) |
| `dte_calendar` | params `expiry`: `(expiry_date − session_date)` in calendar days |
| `t_expiry_years` | `(expiry_close − available_at) / (365 days)`, `expiry_close` = 15:30 IST on expiry date; floor at 1e-6 |
| `or_high`, `or_low` | params `m=15`: max high / min low of bars with `bar_start < open + m min`; **null until `available_at ≥ open + m`**; session-anchored |
| `or_width` | `or_high − or_low` |
| `or_break_up` / `or_break_down` | `close_t > or_high` / `close_t < or_low` after formation, else 0 |

### 5.4.6 Prior-session levels (family `levels`)
From the previous session's bars (computed from 1m or 1d): `prev_open, prev_high, prev_low, prev_close`. Pivots (classic): `P = (H+L+C)/3`, `R1 = 2P − L`, `S1 = 2P − H`, `R2 = P + (H − L)`, `S2 = P − (H − L)`. Running session values (anchored): `session_open`, `session_high = max(high so far)`, `session_low`, `session_avg_price = mean(hlc3 so far)`, `dist_session_open = close − session_open`, `dist_prev_close = close − prev_close`.
`session_vwap = Σ(hlc3·volume)/Σ(volume)` is **available only if `volume_valid`** (CQ-10); for the NIFTY index it returns NaN with reason `NO_VOLUME`.

### 5.4.7 Volume (family `volume`, `requires_volume=True`; NaN with `NO_VOLUME` if invalid)
`vol_sma(n=20)`, `rel_vol_tod(days=20)` = `volume_t / mean(volume at the same minute-of-day over the previous `days` sessions)`.

### 5.4.8 Multi-timeframe (`mtf`)
`mtf(col, tf)`: the value of feature column `col` computed on timeframe `tf`'s series at the **latest completed** HTF bar with `available_at ≤ decision_at`. The in-progress HTF bar is never exposed in v1. Example: at 10:14 on a 5m strategy, `mtf(ema_close_21, 1h)` uses the 09:15–10:15 bar only after 10:15; at 10:14 it returns the previous completed 1h bar (none before 10:15 on the first hour → NaN).

### 5.4.9 Option-chain features (family `option`, computed per snapshot)
**Common definitions** for snapshot `S` with `available_at = a`, expiry `E`:
- Spot `s`: `S.spot_price` if present, else `close` of the latest 1m bar with `available_at ≤ a` (`spot_source ∈ {SNAPSHOT, CANDLE}`).
- Step `Δ` = `strike_step` (config; default 50). `atm = Δ · ceil(s/Δ − 0.5)` (ties go to the lower strike).
- Band `B_k = {K : |K − atm| ≤ k·Δ}`; default `k = 10`.
- `mid = (bid+ask)/2` if `quote_status = OK`; `px = mid` if available else `ltp` (flag `price_source`).
- Freshness: `snap_age_s = decision_at − a`. All option features are `NaN` with reason `STALE` if `snap_age_s > max_snapshot_age_s` (default 75 s **[OWNER]**).
- Lookback snapshot for change features with lookback `L` seconds (default `L ∈ {300, 900}`): the latest snapshot with `available_at ≤ a − L`, accepted only if its age relative to `a − L` is ≤ 45 s; else NaN `NO_LOOKBACK`. Changes use the **intersection of contracts** present in both snapshots.
- A contract's Greeks are used only if `greeks_status = OBSERVED`.

| Feature | Definition | Needs |
|---|---|---|
| `atm_strike`, `atm_dist` | `atm`, `s − atm` | spot |
| `ce_atm_px`, `pe_atm_px` | `px` of the ATM CE / PE | quotes |
| `straddle_atm` | `ce_atm_px + pe_atm_px` | both |
| `straddle_pct` | `100·straddle_atm / s` | both |
| `pcr_oi_band` (k=10) | `Σ_{K∈B_k} OI_PE / Σ_{K∈B_k} OI_CE` (NaN if denominator 0) | OI |
| `pcr_oi_total` | same over all strikes | OI |
| `pcr_vol_band` (k=10) | same with `volume` | volume |
| `oi_imbalance` (k=10) | `(ΣOI_PE − ΣOI_CE)/(ΣOI_PE + ΣOI_CE)` over band | OI |
| `oi_resistance` | strike with max CE OI among `K ≥ atm` (ties: nearest to `s`) | OI |
| `oi_support` | strike with max PE OI among `K ≤ atm` | OI |
| `dist_resistance`, `dist_support` | `oi_resistance − s`, `s − oi_support` | OI |
| `oi_com_ce`, `oi_com_pe` (k=10) | `Σ K·OI / Σ OI` per side over band | OI |
| `max_pain` | `argmin_{K_j} [ Σ_i OI_CE(K_i)·max(K_j − K_i, 0) + Σ_i OI_PE(K_i)·max(K_i − K_j, 0) ]`, `K_j` ranging over all listed strikes; ties → closest to `s` | OI |
| `max_pain_dist` | `s − max_pain` | OI |
| `d_oi_ce_band(L)`, `d_oi_pe_band(L)` | `Σ_band OI(a) − Σ_band OI(a − L)` per side over common contracts | lookback |
| `d_pcr_band(L)` | `pcr_oi_band(a) − pcr_oi_band(a − L)` | lookback |
| `atm_ce_buildup(L)`, `atm_pe_buildup(L)` | with `dp = px_a − px_{a−L}`, `doi = OI_a − OI_{a−L}` for the ATM contract: `+1` long buildup (dp>0, doi>0), `−1` short buildup (dp<0, doi>0), `+2` short covering (dp>0, doi<0), `−2` long unwinding (dp<0, doi<0), else 0 | lookback |
| `iv_atm` | mean of valid `iv` of ATM CE and PE (if only one valid, use it and set `iv_atm__n=1`) | Greeks |
| `iv_skew_2` | `iv_PE(atm − 2Δ) − iv_CE(atm + 2Δ)` | Greeks |
| `d_iv_atm(L)` | `iv_atm(a) − iv_atm(a − L)` | Greeks, lookback |
| `iv_pctile` (w=20 sessions) | percentile of current `iv_atm` among `iv_atm` values at the same minute-of-day over the previous `w` sessions; requires ≥ 10 sessions of history else NaN `NO_HISTORY` | Greeks, history |
| `delta_atm_ce`, `gamma_atm`, `theta_atm`, `vega_atm` | raw ATM Greeks (gamma/theta/vega averaged over CE/PE) | Greeks |
| `spread_abs_atm_ce`, `spread_abs_atm_pe` | `ask − bid` | quotes |
| `spread_rel_atm` | `(ask − bid)/mid` for the ATM CE and PE separately | quotes |
| `qty_imb_atm` | `(bid_qty − ask_qty)/(bid_qty + ask_qty)` per ATM contract | v3/api_v4 only |
| `gex_net` *(EXPERIMENTAL; flag `EXPERIMENTAL`)* | `Σ_{K∈B_k} sgn · γ_K · OI_K · lot · s² · 0.01`, `sgn=+1` for CE, `−1` for PE; assumes dealers long calls and short puts | Greeks, OI |
| `snap_age_s`, `n_strikes`, `n_valid_quotes_band`, `snapshot_ok` | `snapshot_ok = (snap_age_s ≤ max_age) and (n_strikes ≥ 20) and (n_valid_quotes_band ≥ 8)` | — |

Option features that need Greeks are `NaN` with reason `GREEKS_UNAVAILABLE` for all snapshots from schema v1/v2 and for any contract failing OQ-10/OQ-11. A strategy must declare which option features it requires; a missing required feature makes the decision `FEATURE_NOT_READY` (no trade), never a fallback.

### 5.4.10 [v1.1] Quote-stream (order-flow) features (family `flow`, EXPERIMENTAL)
Source: recorded WebSocket `full` quotes (§4.10), not the 30 s snapshots. Available only for sessions with quote-recorder coverage; otherwise `NaN` with reason `NO_QUOTE_STREAM`. Contract `c` = ATM CE and ATM PE as in §5.4.9 at `decision_at`. Window `W` seconds (default 60); quotes are those with `received_at ∈ (a − W, a]`, `a = decision_at`.
| Feature | Definition |
|---|---|
| `depth_imb_l1(c)` | `(bid_qty1 − ask_qty1) / (bid_qty1 + ask_qty1)` from the latest quote |
| `depth_imb_l5(c)` | `(Σ_{i≤5} bid_qty_i − Σ_{i≤5} ask_qty_i) / (Σ bid_qty_i + Σ ask_qty_i)` from the latest quote |
| `spread_rel_w(c)` | mean over `W` of `(ask1 − bid1)/mid` for quotes with both sides present |
| `quote_rate_w(c)` | number of quote updates in `W` divided by `W` |
| `tick_flow_w(c)` | `Σ sign_j·Δvol_j / Σ Δvol_j` over `W`, where `Δvol_j` = increase in cumulative volume between consecutive quotes (≥ 0; negative or reset ⇒ skipped) and `sign_j = sign(ltp_j − ltp_{j−1})`, with a zero change inheriting the last non-zero sign. `NaN` if `Σ Δvol = 0` or cumulative volume is not validated (S3) |
These are approximations of order flow: the tick rule is not the exchange aggressor flag. Strategies using them must declare `required_option_features` and are testable only on data recorded since the recorder started (no historical back-fill exists).

### 5.4.11 [v1.1] Futures features (family `fut`, OPTIONAL — built only on owner request, ticket T3.7)
Source: `FUT:NIFTY:<expiry>` 1m candles and quotes (ADR-021). Near-month = the monthly contract with the smallest expiry ≥ `session_date`; roll on the first session after its expiry. Any feature whose look-back crosses a roll is `NaN` with reason `ROLL`.
| Feature | Definition |
|---|---|
| `fut_basis` | `fut_close − spot_close` for the same bar; `fut_basis_pct = 100·fut_basis/spot_close` |
| `fut_vol` | bar volume from cumulative volume deltas (never summed twice) |
| `fut_vwap_session` | `Σ(hlc3·vol)/Σ(vol)` since session open; `fut_dist_vwap = fut_close − fut_vwap_session` |
| `fut_rel_vol_tod(days=20)` | as `rel_vol_tod` (§5.4.7) on futures volume |
| `fut_doi(k)`, `fut_buildup(k)` | open-interest change over `k` bars; buildup code as `atm_buildup` (§5.4.9) using futures price and OI |
Strategies that use volume must declare the volume source explicitly (`volume_source: "FUT"`); the index's own volume stays `NO_VOLUME`.


## 5.5 Feature engine service
```python
class FeatureEngine:
    def __init__(self, registry, requests: list[FeatureRequest])   # (name, params, tf)
    def compute_batch(self, repo: CandleRepository, chain_repo, instrument_id, tf, start, end) -> pd.DataFrame
    def start_live(self) -> None
    def on_bar(self, tf: str, bar: Bar) -> FeatureRow                # incremental, topologically ordered
    def on_snapshot(self, snap: SnapshotView) -> OptionFeatureRow
```
`FeatureRow = {bar_start, available_at, values: dict[col, float|None], ok: dict[col, bool], reasons: dict[col, str]}`. Dependencies resolve through a DAG (`depends_on`); cycles are a startup error. `compute_batch` for 2022–2026 1m (≈ 433k bars × ≈ 40 columns) must finish in ≤ 120 s on the dev machine **[OWNER]**; if not, vectorise the slow features (parity tests protect correctness).

## 5.6 Feature tests (each ID applies to every registered feature unless noted)
| ID | Test |
|---|---|
| T-FE-1 | Reference fixture: output equals hand-computed values (Appendix A for sma/ema/rsi/atr/macd/bbands) within `rtol=1e-6` |
| T-FE-2 | Batch/incremental parity (§5.1.6) |
| T-FE-3 | Truncate-and-recompute (§5.1.7) |
| T-FE-4 | Poisoned-future test |
| T-FE-5 | Warm-up: first valid index equals `warmup_bars − 1`; earlier values NaN |
| T-FE-6 | Gap behaviour: deleting 1–2 bars keeps recursive state; deleting 3 resets and re-warms |
| T-FE-7 | Constant series edge cases (range 0, RSI 50, BB width 0 → pctb NaN) |
| T-FE-8 | Option features: golden snapshot fixtures (v1, v2, v3) for `atm_strike`, `pcr_oi_band`, `max_pain`, buildup classes; stale snapshot → NaN `STALE`; v2 → `GREEKS_UNAVAILABLE` |
| T-FE-9 | `breakout_up` equals manual computation using prior bars only; changing the current bar's high does not change `prior_high` |
| T-FE-10 | MTF: no value from an incomplete HTF bar at any minute of the session (property test) |

---

# 6. Strategies (`quantview.research.strategies`)

## 6.1 Core types (Pydantic, frozen)
```python
class Direction(str, Enum):   BULLISH="BULLISH"; BEARISH="BEARISH"          # view on the underlying
class Action(str, Enum):      ENTER="ENTER"; EXIT="EXIT"; NO_ACTION="NO_ACTION"
class Basis(str, Enum):       UNDERLYING="UNDERLYING"; PREMIUM="PREMIUM"
class ReasonCode(str, Enum):
    SIGNAL_ENTRY; SIGNAL_EXIT; STOP; TARGET; TRAIL; TIME_EXIT; FORCE_FLAT
    FEATURE_NOT_READY; STALE_DATA; PARTIAL_BAR; OUTSIDE_WINDOW; CONFLICTING_SIGNALS
    COOLDOWN; MAX_ENTRIES; RISK_REJECTED; NO_ELIGIBLE_CONTRACT; KILL_SWITCH
    RISK_CLAMPED; RISK_BELOW_ONE_LOT; OVERNIGHT_CARRY; NO_FILL_BAR_IN_SESSION      # [v1.1]

class StopLeg(BaseModel):          # one of stop/target/trailing
    type: Literal["points","pct","atr_mult","level","r_multiple","premium_pct"]
    value: float | None = None     # points / percent / multiple / R
    feature: str | None = None     # for type="level": feature column frozen at entry
    atr_col: str | None = None     # for atr_mult: ATR column evaluated at entry bar
    basis: Basis

class ExitRules(BaseModel):
    stop: StopLeg | None
    target: StopLeg | None
    trailing: StopLeg | None       # points/atr_mult/premium_pct only
    max_bars: int | None           # exit at the close of the Nth bar after entry
    time_exit: str | None          # "HH:MM" IST on the exit session; INTRADAY default = profile force_flat_time (15:15)
    exit_session_offset: int = 0   # [v1.1] 0 = same session; n ≥ 1 = n-th next session (OVERNIGHT only; BTST = 1, "09:15")

class Sizing(BaseModel):
    type: Literal["fixed_lots","risk_pct","fixed_inr_risk"]
    lots: int | None               # fixed_lots
    pct: float | None              # risk_pct: % of account equity risked between entry and PREMIUM stop (clamped to the effective ceiling, §8.6.3)
    inr_risk_paise: int | None     # [v1.1] fixed_inr_risk: rupees risked between entry and PREMIUM stop (clamped likewise)
    if_below_one_lot: Literal["REJECT","ONE_LOT"] = "REJECT"   # [v1.1] action when sizing yields 0 lots; ONE_LOT is still subject to RK-07/RK-08

class OptionPolicy(BaseModel):
    expiry: ExpiryPolicy           # {"mode":"NEAREST","min_calendar_days":0,"min_minutes_to_expiry":30}
    strike: StrikePolicy           # {"mode":"ATM"} | {"mode":"OFFSET","steps":1} | {"mode":"DELTA","target":0.5,"tol":0.05} | {"mode":"EXPLICIT","strike":24500}
    max_spread_rel: float = 0.04
    min_premium: float = 5.0       # rupees; ask must be >= this
    max_snapshot_age_s: int = 75
    allow_nearest_listed: bool = False

class DurationProfile(str, Enum):     # [v1.1]
    INTRADAY = "INTRADAY"             # flat by force_flat_time
    OVERNIGHT = "OVERNIGHT"           # may be carried across sessions (needs exit_session_offset >= 1)

class RiskSpec(BaseModel):            # [v1.1] strategy-declared risk; every field optional; None = inherit the account profile
    max_risk_pct: float | None = None         # per-trade risk cap, % of equity
    max_outlay_pct: float | None = None
    max_lots_per_order: int | None = None
    daily_loss_limit_pct: float | None = None
    max_consecutive_losses: int | None = None
    # A value above the account ceiling is clamped by the risk engine and flagged RISK_CLAMPED (§8.6.3); a strategy can never raise a ceiling.

class Decision(BaseModel):
    decision_id: str; strategy_id: str; strategy_version: int; spec_hash: str
    run_id: str; mode: Literal["B","C","S","PAPER","LIVE"]      # [v1.2] for PAPER, run_id == deployment_id
    deployment_id: str | None = None                             # [v1.2]
    underlying_ref_px: float | None = None                       # [v1.2] index level at decision: chart anchor only
    decision_at: datetime; bar_start: datetime; timeframe: str
    action: Action
    direction: Direction | None          # for ENTER
    exit_reason: ReasonCode | None       # for EXIT
    sizing: Sizing | None
    exit_rules: ExitRules | None         # frozen at ENTER
    duration_profile: DurationProfile = DurationProfile.INTRADAY   # [v1.1]
    risk: RiskSpec | None = None          # [v1.1] copied from the strategy, resolved in §8.6.3
    option_policy: OptionPolicy | None   # None in Mode B
    reasons: list[ReasonCode]
    feature_snapshot: dict[str, float | None]   # every feature the strategy read
    idempotency_key: str                 # f"{strategy_id}:{spec_hash}:{run_id}:{timeframe}:{bar_start_iso}:{action}"
```
`Direction.BULLISH` ⇒ buy a **CE**; `BEARISH` ⇒ buy a **PE** (ADR-011: long options only). A strategy never names an instrument.

## 6.2 Strategy specification (declarative JSON AST)
### 6.2.1 Top level
```json
{
  "schema_version": "1.0",
  "id": "ema_cross_adx", "name": "EMA cross with ADX filter", "version": 1,
  "timeframe": "5m",
  "params": {"fast": 9, "slow": 21, "adx_n": 14, "adx_min": 20, "atr_n": 14, "stop_atr": 1.0, "target_atr": 2.0},
  "features": [
    {"name": "ema", "params": {"src": "close", "n": "$fast"}},
    {"name": "ema", "params": {"src": "close", "n": "$slow"}},
    {"name": "adx", "params": {"n": "$adx_n"}},
    {"name": "atr", "params": {"n": "$atr_n"}}
  ],
  "trading_window": {"start": "09:30", "end": "14:45"},
  "entry": {
    "bullish": {"all": [{"cross_above": [{"f": "ema_close_9"}, {"f": "ema_close_21"}]},
                        {"gte": [{"f": "adx_14__adx"}, {"p": "adx_min"}]}]},
    "bearish": {"all": [{"cross_below": [{"f": "ema_close_9"}, {"f": "ema_close_21"}]},
                        {"gte": [{"f": "adx_14__adx"}, {"p": "adx_min"}]}]}
  },
  "signal_exit": {
    "bullish": {"cross_below": [{"f": "ema_close_9"}, {"f": "ema_close_21"}]},
    "bearish": {"cross_above": [{"f": "ema_close_9"}, {"f": "ema_close_21"}]}
  },
  "exit_rules": {
    "bullish": {"stop": {"type": "atr_mult", "value": "$stop_atr", "atr_col": "atr_14", "basis": "UNDERLYING"},
                "target": {"type": "atr_mult", "value": "$target_atr", "atr_col": "atr_14", "basis": "UNDERLYING"},
                "time_exit": "15:15"},
    "bearish": {"stop": {"type": "atr_mult", "value": "$stop_atr", "atr_col": "atr_14", "basis": "UNDERLYING"},
                "target": {"type": "atr_mult", "value": "$target_atr", "atr_col": "atr_14", "basis": "UNDERLYING"},
                "time_exit": "15:15"}
  },
  "sizing": {"type": "fixed_lots", "lots": 1},
  "option_policy": {"expiry": {"mode": "NEAREST", "min_calendar_days": 0, "min_minutes_to_expiry": 30},
                    "strike": {"mode": "ATM"}},
  "limits": {"max_entries_per_day": 4, "cooldown_bars": 2},
  "duration_profile": "INTRADAY",
  "risk": {},
  "allow_partial_bars": false,
  "required_option_features": []
}
```
Literal `"$name"` inside `params` of a feature or inside `value` fields substitutes `params[name]` **before** column names are derived (`n: "$fast"` with `fast=9` → `ema_close_9`). Feature references in expressions use the final column names (§5.1.3); validation fails if a referenced column is not produced by `features` after substitution. `{"p": "adx_min"}` references a parameter in expressions.

**[v1.1] New top-level fields.** `duration_profile` (`INTRADAY` default | `OVERNIGHT`); `risk` (a `RiskSpec`; `{}` inherits the account profile); optional `setup` (an `Expr` from §6.2.2 that is true on the bars where the strategy is willing to look for a trade; required for ML role `STRATEGY_GATED`, §11.1); `volume_source` (`"NONE"` default | `"FUT"`, §5.4.11). Validation rules: an `OVERNIGHT` strategy must give `exit_rules.<dir>.exit_session_offset` in `1..max_exit_session_offset` (default 5) **and** `time_exit`; otherwise error `OVERNIGHT_NEEDS_EXIT`. An `INTRADAY` strategy with `exit_session_offset ≠ 0` is an error. An `OVERNIGHT` strategy's `option_policy.expiry.min_calendar_days` is raised to at least 1 by the selector (§7.2 step 2a).
*Example fragment (BTST-style, illustrative parameters):*
```json
{ "duration_profile": "OVERNIGHT",
  "trading_window": {"start": "15:00", "end": "15:25"},
  "exit_rules": {"bullish": {"stop": {"type": "premium_pct", "value": 30, "basis": "PREMIUM"},
                              "time_exit": "09:15", "exit_session_offset": 1}},
  "option_policy": {"expiry": {"mode": "NEAREST", "min_calendar_days": 1, "min_minutes_to_expiry": 30}, "strike": {"mode": "ATM"}},
  "sizing": {"type": "risk_pct", "pct": 3.0, "if_below_one_lot": "REJECT"},
  "risk": {"max_risk_pct": 3.0} }
```

### 6.2.2 Expression grammar (complete)
```
Expr    := Compare | Logic | TimeCond
Value   := {"f": col, "tf"?: tf, "off"?: int>=0}        # feature value (off = bars back; tf = higher timeframe via MTF rule)
         | {"bar": "open"|"high"|"low"|"close", "off"?: int>=0}
         | {"c": number} | {"p": param_name}
Compare := {"gt"|"gte"|"lt"|"lte"|"eq": [Value, Value]}
         | {"between": [Value, Value, Value]}            # inclusive lo/hi
         | {"cross_above"|"cross_below": [Value, Value]}
Logic   := {"all": [Expr,...]} | {"any": [Expr,...]} | {"not": Expr}
TimeCond:= {"time_between": ["HH:MM","HH:MM"]}           # IST; start inclusive, end exclusive, on decision_at
         | {"dow_in": [0..4,...]} | {"expiry_day": true|false}
```
Semantics:
- `cross_above(A,B)` at bar t ⇔ `A_{t−1} ≤ B_{t−1}` **and** `A_t > B_t`; requires all four values `ok`. `cross_below` mirrors.
- Any comparison with a non-ok (NaN) operand evaluates to **UNKNOWN**; `all` with any UNKNOWN child ⇒ UNKNOWN; `any` with a true child ⇒ true else UNKNOWN if any child UNKNOWN else false; `not UNKNOWN` ⇒ UNKNOWN. An UNKNOWN entry condition ⇒ `NO_ACTION` with reason `FEATURE_NOT_READY`.
- Evaluation uses only `AsOfView` (§5.2).

### 6.2.3 Exit-rule semantics
All distances are measured from the **entry reference price** `p_e` (Mode B: fill price; Mode C UNDERLYING basis: spot at fill snapshot; PREMIUM basis: option fill price).
| `type` | Bullish/long distance | Level formula |
|---|---|---|
| `points` | `value` points | stop `p_e − v` / target `p_e + v` (mirrored for bearish) |
| `pct` | `value` percent | stop `p_e·(1 − v/100)` / target `p_e·(1 + v/100)` |
| `atr_mult` | `value × ATR(atr_col at entry bar)` | frozen at entry |
| `level` | feature value at entry bar (`feature` column) | frozen at entry (e.g. `or_low_15` as stop for a bullish ORB) |
| `r_multiple` (target only) | `value × abs(p_e − stop_level)` | target `p_e + v·R` |
| `premium_pct` (PREMIUM basis) | `value` percent of option fill price | stop `px·(1 − v/100)`, target `px·(1 + v/100)` |
`trailing` (UNDERLYING): level follows the best close since entry by the stated distance; it only moves in the favourable direction; checked at bar close in v1 (not intrabar) unless Mode B's intrabar rules say otherwise (§8.3). `max_bars`: exit decision at the close of bar number `max_bars` after the entry bar. `time_exit`: exit decision at the first bar close at or after the time. For INTRADAY strategies the account profile's `force_flat_time` (default 15:15) always applies. For OVERNIGHT strategies the exit is defined by `exit_session_offset` + `time_exit` (§8.3.6, §8.4.7); `force_flat_time` does not apply to a carried position.

## 6.3 Runner semantics (`StrategyRunner`)
```
on_finalized_bar(bar, view, position, run_ctx):
    gates (any false => emit NO_ACTION with reason, return):
        strategy enabled and mode matches                                  -> KILL_SWITCH
        bar.quality_flags has PARTIAL_BAR and not allow_partial_bars       -> PARTIAL_BAR
        decision_at within trading_window (entries only)                   -> OUTSIDE_WINDOW
        view.ok(required feature columns)                                  -> FEATURE_NOT_READY
        if options required: chain fresh (age <= policy.max_snapshot_age_s) -> STALE_DATA
    if position is FLAT:
        if cooldown active                                                 -> COOLDOWN
        if entries_today >= limits.max_entries_per_day                     -> MAX_ENTRIES
        b = eval(entry.bullish); s = eval(entry.bearish)
        if b is True and s is True                                         -> CONFLICTING_SIGNALS (no trade)
        if b is True -> Decision(ENTER, BULLISH) ; elif s is True -> Decision(ENTER, BEARISH)
        else NO_ACTION
    else (in position):
        if eval(signal_exit[position.direction]) is True -> Decision(EXIT, reason=SIGNAL_EXIT)
        (stops/targets/trailing/time exits are executed by the engine, not by the strategy)
    attach feature_snapshot = values of every column the spec reads
    set idempotency_key; skip if key already processed
```
A strategy is evaluated **once per finalized bar** of its timeframe, only after all events with `available_at ≤ decision_at` are applied. No same-bar re-entry after an exit on that bar.

## 6.4 Python strategy interface (trusted local modules only)
```python
class StrategyMeta(BaseModel):
    id: str; name: str; version: int; timeframe: str
    features: list[FeatureRequest]
    warmup_bars: int
    params_schema: dict               # JSON-schema for params
    allow_partial_bars: bool = False
    required_option_features: list[str] = []

class Strategy(ABC):
    meta: ClassVar[StrategyMeta]
    def __init__(self, params: dict[str, Any]) -> None: ...
    def on_start(self, ctx: StartContext) -> None: ...                     # optional
    @abstractmethod
    def on_bar(self, view: AsOfView, pos: PositionView, state: dict) -> Decision | None: ...
```
Rules enforced at load time by a static AST check in `strategies/registry.py`: only `math`, `statistics`, `numpy`, `dataclasses`, `typing`, `quantview.research.strategies.python_api` may be imported; no `open`, `eval`, `exec`, `__import__`, `os`, `sys`, `socket`, `subprocess`, `time`, `datetime.now`, `random` (use `ctx.rng(seed)`); `state` is a JSON-serialisable dict persisted by the runner (survives restarts). Python strategies are registered through an **allow-list** `config/strategies/allowlist.yaml` (module path + sha256 of file). `python_api` exposes helpers `enter(direction, sizing, exit_rules, option_policy, reasons)`, `exit_(reason)`, `no_action(reason)`.

## 6.5 Versioning and hashing
`spec_hash = sha256(canonical_json(spec))` where `canonical_json = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` after parameter substitution is **not** applied (hash the spec as authored, params included). A strategy version is immutable once referenced by a run or a deployment; editing creates `version+1`. Python strategies hash the file bytes plus params. Every Decision, run and order stores `strategy_id, strategy_version, spec_hash`.

## 6.6 Chart annotation contract (so the UI never parses strategy code)
```python
class Annotation(BaseModel):
    kind: Literal["marker","hline","zone","line_point"]
    time: datetime                       # anchor
    price: float | None
    price_to: float | None               # zone upper bound
    label: str | None
    shape: Literal["arrow_up","arrow_down","circle","square"] | None
    color_role: Literal["entry","exit","stop","target","info"]
    ref: dict                            # {decision_id|order_id|fill_id}
    event_kind: Literal["SIGNAL","ORDER_ACCEPTED","FILL","LEVEL","INFO"] = "INFO"   # [v1.2] a signal, an accepted order and a fill are different events
    deployment_id: str | None = None                                                  # [v1.2]
    price_space: Literal["UNDERLYING","PREMIUM"] = "UNDERLYING"                        # [v1.2] PREMIUM annotations are never drawn on the index axis
```
The engine automatically emits annotations: `ENTER` (arrow), `EXIT` (circle), stop/target levels (hline from entry to exit), and signal-vs-order-vs-fill distinction via `ref` and `color_role`. Strategies may add `info` annotations through `python_api.annotate(...)`. **[v1.2]** For paper deployments annotations are derived from persisted `decisions`/`orders`/`fills` (`TradeChain`, §4.8.1), never reconstructed from indicator crossings; see PAPER_TRADING_UI.md §5–§6.

## 6.7 Reference strategies (must exist; used for parity gate)
**R1 `ema_cross_adx`** — the JSON in §6.2.1 (defaults as shown).
**R2 `orb_15`** — opening-range breakout, timeframe `5m`:
```json
{
  "schema_version": "1.0", "id": "orb_15", "name": "Opening range breakout 15m", "version": 1, "timeframe": "5m",
  "params": {"or_m": 15, "ema_n": 20, "rr": 1.5},
  "features": [
    {"name": "or_high", "params": {"m": "$or_m"}}, {"name": "or_low", "params": {"m": "$or_m"}},
    {"name": "ema", "params": {"src": "close", "n": "$ema_n"}}
  ],
  "trading_window": {"start": "09:30", "end": "13:30"},
  "entry": {
    "bullish": {"all": [{"gt": [{"bar": "close"}, {"f": "or_high_15"}]}, {"gt": [{"bar": "close"}, {"f": "ema_close_20"}]},
                        {"lte": [{"bar": "close", "off": 1}, {"f": "or_high_15", "off": 1}]}]},
    "bearish": {"all": [{"lt": [{"bar": "close"}, {"f": "or_low_15"}]}, {"lt": [{"bar": "close"}, {"f": "ema_close_20"}]},
                        {"gte": [{"bar": "close", "off": 1}, {"f": "or_low_15", "off": 1}]}]}
  },
  "signal_exit": {"bullish": {"lt": [{"bar": "close"}, {"f": "ema_close_20"}]}, "bearish": {"gt": [{"bar": "close"}, {"f": "ema_close_20"}]}},
  "exit_rules": {
    "bullish": {"stop": {"type": "level", "feature": "or_low_15", "basis": "UNDERLYING"},
                "target": {"type": "r_multiple", "value": "$rr", "basis": "UNDERLYING"}, "time_exit": "15:15"},
    "bearish": {"stop": {"type": "level", "feature": "or_high_15", "basis": "UNDERLYING"},
                "target": {"type": "r_multiple", "value": "$rr", "basis": "UNDERLYING"}, "time_exit": "15:15"}
  },
  "sizing": {"type": "fixed_lots", "lots": 1},
  "option_policy": {"expiry": {"mode": "NEAREST", "min_calendar_days": 0, "min_minutes_to_expiry": 30}, "strike": {"mode": "ATM"}},
  "limits": {"max_entries_per_day": 2, "cooldown_bars": 3},
  "allow_partial_bars": false, "required_option_features": []
}
```
Each reference strategy also exists as a Python class in `strategies/reference/`. **Gate (Phase 4):** on the same 20-session fixture, spec-evaluator and Python versions produce identical `(decision_at, action, direction, reasons, feature_snapshot)` sequences.

## 6.8 Strategy tests
| ID | Test |
|---|---|
| T-ST-1 | Schema validation rejects unknown keys, bad `off`, undefined columns, negative sizes |
| T-ST-2 | `$param` substitution produces the expected column names |
| T-ST-3 | Cross semantics incl. UNKNOWN handling (truth-table test) |
| T-ST-4 | Runner: gates produce correct `NO_ACTION` reasons (partial bar, window, not ready, stale) |
| T-ST-5 | Idempotency: replaying the same bar twice yields one decision |
| T-ST-6 | Conflicting bullish+bearish ⇒ no trade |
| T-ST-7 | Spec vs Python parity on reference strategies |
| T-ST-8 | AST allow-list rejects forbidden imports/builtins |
| T-ST-9 | `spec_hash` stable across key order; changes when any param changes |
| T-ST-10 | **[v1.1]** `OVERNIGHT` without `exit_session_offset ≥ 1` + `time_exit` is rejected; `INTRADAY` with a non-zero offset is rejected |
| T-ST-11 | **[v1.1]** `risk` block: `{}` inherits; values above a ceiling are clamped and flagged `RISK_CLAMPED` (see T-RK-23) |
| T-ST-12 | **[v1.1]** `setup` expression evaluated per bar yields the same candidate set in batch and live replay |
| T-ST-13 | **[v1.2]** `required_feature_pins(spec)` lists every column the spec reads after `$param` substitution with name, version, params, timeframe, outputs and warm-up; a column not produced by `features` fails validation |

## 6.9 [v1.1] Pine Script porting protocol (Pine is never executed)
TradingView indicators and strategies are the owner's main strategy source. They are *ported* by an AI or by hand into a JSON spec (§6.2) or a trusted Python strategy (§6.4). Porting is the highest-risk step for look-ahead and semantic drift, so it follows this protocol:
1. **Provenance.** The original Pine source is stored unmodified at `strategies/pine_sources/<strategy_id>.pine` with its TradingView URL or author and the date. It is documentation only and is never run.
2. **Feature mapping.** Every `ta.*` call is mapped to a catalogue feature (§5.4) when one exists (`ta.ema`→`ema`, `ta.rma`→`rma`, `ta.rsi`→`rsi`, `ta.atr`→`atr`, `ta.supertrend`→`supertrend`, `ta.bb`→`bbands`, `ta.macd`→`macd`, `ta.dmi`→`adx`). A missing function is added as a catalogue feature with a hand-computed fixture (T-FE-1) before the strategy is accepted.
3. **Parity test (PINE-1).** The owner exports the indicator values from TradingView ("Export chart data") for ≥ 500 consecutive bars of the same symbol and timeframe. The ported feature must match the export within `1e-6` after the warm-up period. Known, documented seed differences are listed in the port's `PORT_NOTES.md`; any other difference blocks acceptance.
4. **Look-ahead and repaint review (PINE-2).** Reject or rewrite: `request.security` / `security()` with `lookahead = barmerge.lookahead_on`; use of the in-progress higher-timeframe bar (our MTF rule §5.4.8 exposes only completed bars, so a port will intentionally differ from TradingView's realtime repainting); `barstate.isrealtime`/`isconfirmed` branches; `varip`; `calc_on_every_tick`; any reference to a future bar offset (`close[-1]`). The review result (PASS / REWRITTEN / REJECTED + reasons) is stored with the port.
5. **Execution semantics (PINE-3).** Pine strategies by default evaluate at bar close and fill at the next bar's open (`process_orders_on_close = false`), which matches `SPOT_NEXT_OPEN`. Pine's intrabar stop/limit resolution differs from our path-blind rule (§8.3.4); QuantView results are expected to be more conservative and are not required to equal TradingView's strategy tester.
6. **State (PINE-4).** `var` variables become keys of the strategy `state` dict (§6.4); Pine `na` ↔ `NaN`/`None`; `bar_index` ↔ the calendar-driven `seq`.
7. **Acceptance.** A port passes only with: PINE-1 report, PINE-2 review, a reference run in Mode B whose first 20 signals are listed with timestamps for the owner to eyeball against the TradingView chart, and the standard strategy tests T-ST-1…12.



---

# 7. Contract selection (`quantview.research.contract_selection`)

## 7.1 Interface
```python
class SelectionRequest(BaseModel):
    decision_at: datetime
    direction: Direction
    policy: OptionPolicy
    underlying_id: str = "IDX:NIFTY50"
    mode: Literal["C","PAPER","LIVE"]
    duration_profile: DurationProfile = DurationProfile.INTRADAY   # [v1.1]

class SelectionResult(BaseModel):
    status: Literal["OK","REJECTED"]
    instrument_id: str | None
    option_type: Literal["CE","PE"] | None
    expiry_date: date | None; strike: int | None
    lot_size: int | None; tick_paise: int | None
    snapshot_id: str | None; snapshot_age_s: float | None
    quote: dict | None                 # {bid, ask, ltp, mid, bid_qty, ask_qty, quote_status}
    spot_used: float | None; spot_source: Literal["SNAPSHOT","CANDLE"] | None
    reasons: list[str]                 # rejection codes (empty when OK)
    candidates: list[dict]             # up to 5 evaluated contracts with the first failing filter
    policy_version: str = "1.0.0"

class ContractSelector:
    def select(self, req: SelectionRequest) -> SelectionResult
```
It reads only through `OptionChainRepository.snapshot_as_of` and the as-of candle API (never `next_*`).

## 7.2 Algorithm (deterministic, in this order)
1. `option_type = CE if direction == BULLISH else PE`.
2. **Expiry.** `E = ExpiryRules.nearest_expiry(session_date, cal, min_calendar_days=policy.expiry.min_calendar_days)`. If `E == session_date` and minutes to 15:30 `< policy.expiry.min_minutes_to_expiry` → `E = next weekly expiry after E`. Mode `NEXT` takes the following expiry; mode `EXPLICIT` takes the given date.
2a. **[v1.1] Overnight.** If `duration_profile == OVERNIGHT`, the effective `min_calendar_days = max(policy.expiry.min_calendar_days, 1)` so that the contract is still alive at the exit session's open; a contract expiring on `session_date` is never selected. If the exit session (`exit_session_offset`) falls after `E`, the result is `REJECTED` with `EXPIRY_BEFORE_EXIT`. If `E` is the very next session the result carries the warning `EXPIRY_NEXT_SESSION` (allowed; the report counts it).
3. **Snapshot.** `snap = snapshot_as_of(underlying, E, decision_at, max_age_s=policy.max_snapshot_age_s)`. None ⇒ `REJECTED` with `NO_DATA_FOR_EXPIRY` (no snapshot exists for `E`; the collector stores only the nearest weekly) or `STALE_SNAPSHOT` (exists but too old). **No fallback to another expiry.**
4. **Spot.** `s = snap.spot_price` if not null, else the close of the latest 1m bar with `available_at ≤ decision_at`; record `spot_source`.
5. **ATM.** `atm = Δ · ceil(s/Δ − 0.5)` with `Δ = strike_step` (config; default 50).
6. **Target strike.**
   - `ATM`: `atm`.
   - `OFFSET(steps = n)`: CE → `atm + n·Δ`; PE → `atm − n·Δ` (positive n = OTM, negative n = ITM).
   - `EXPLICIT`: the given strike.
   - `DELTA(target, tol)`: among contracts of `option_type` with `greeks_status = OBSERVED`, pick argmin `| |delta| − target |`; tie-break: smaller `|K − s|`, then lower strike; require the gap ≤ `tol` (default 0.05), else `NO_DELTA_MATCH`; if no contract has observed Greeks ⇒ `GREEKS_UNAVAILABLE` (no fallback to ATM unless the policy declares `"fallback": "ATM"`, in which case `reasons` records `FALLBACK_ATM`).
7. **Listing.** The contract `(E, strike, option_type)` must exist in `snap.rows`; else `STRIKE_NOT_LISTED` (no nearest-listed substitution unless `allow_nearest_listed = true`; then the listed strike with the smallest `|K − target|`, ties → lower strike, and `reasons` records `NEAREST_LISTED`).
8. **Quote filters on that contract**, evaluated in order, first failure recorded: `quote_status == OK` else `NO_VALID_QUOTE`; `ask ≥ policy.min_premium` else `PREMIUM_TOO_LOW`; `(ask − bid)/mid ≤ policy.max_spread_rel` else `SPREAD_TOO_WIDE`; optional `ask ≤ policy.max_premium` else `PREMIUM_TOO_HIGH`; optional `volume ≥ policy.min_volume` else `LOW_VOLUME`.
9. **Output** `OK` with lot size from `ExpiryRules.lot_size(E)`, tick 0.05, the quote, `snapshot_id` and age.

Every rejection reason is also forwarded to the runner as `ReasonCode.NO_ELIGIBLE_CONTRACT` with the specific code in `details`.

## 7.3 Tests
| ID | Test |
|---|---|
| T-SEL-1 | ATM rounding incl. exact half (`24525` → `24500`) and negative offsets |
| T-SEL-2 | Weekly expiry on expiry day: after the cutoff selects the next expiry, and rejects with `NO_DATA_FOR_EXPIRY` when data lack it |
| T-SEL-3 | Stale snapshot ⇒ `STALE_SNAPSHOT`; boundary at exactly `max_snapshot_age_s` |
| T-SEL-4 | DELTA policy: tie-break, tolerance failure, `GREEKS_UNAVAILABLE` on v1/v2 data |
| T-SEL-5 | v2 snapshot (no LTP) still selects using bid/ask |
| T-SEL-6 | Determinism: 100 repeated calls identical |
| T-SEL-7 | The selector never calls any `next_*` repository method (spy test) |
| T-SEL-8 | **[v1.1]** OVERNIGHT on an expiry day selects the next expiry; never selects a contract expiring today; `EXPIRY_BEFORE_EXIT` when the exit session is after expiry |
| T-SEL-9 | **[v1.1]** `NEXT` expiry policy works only when the NEXT snapshot partition exists, else `NO_DATA_FOR_EXPIRY` |

---

# 8. Simulation, risk, fills, costs, metrics (`quantview.simulation`, `quantview.risk`)

## 8.1 Engine composition
One `Engine` runs Mode B, Mode C and paper trading. Behaviour differs only through injected components:
```python
class Engine:
    def __init__(self, clock: Clock, feed: DataFeed, features: FeatureEngine, runner: StrategyRunner,
                 selector: ContractSelector | None, risk: RiskEngine, fills: FillModel,
                 costs: CostModel | None, ledger: Ledger | None, recorder: Recorder, cfg: RunConfig): ...
    def run(self) -> RunResult
```
| Component | Mode B | Mode C | Paper |
|---|---|---|---|
| `clock` | `HistoricalClock` | `HistoricalClock` | `WallClock` |
| `feed` | `HistoricalFeed(candles 1m + strategy tf)` | `HistoricalFeed(candles + snapshots)` | `LiveFeed` (event bus) |
| `selector` | none | `ContractSelector` | `ContractSelector` (live snapshot/quotes) |
| `fills` | `SpotFill` | `OptSnapshotBidAsk` | `OptLiveBidAsk` |
| `costs` | none (points) | `UpstoxNseOptions` | same |
| `ledger` | none | in-memory `Ledger` (same code, SQLite-memory/Postgres schema) | Postgres `Ledger` |

## 8.2 Event loop and ordering
### Event types and priority (lower runs first at equal `available_at`)
| Priority | Event | Payload |
|---|---|---|
| 10 | `CandleFinal` (1m and higher TFs) | bar |
| 20 | `SnapshotAvailable` | `SnapshotView` |
| 30 | `QuoteUpdate` (paper/live only) | quote |
| 40 | `TimerEvent` (e.g. force-flat 15:15 for INTRADAY positions, session end, **[v1.1]** overnight exit timers) | name |
| 50 | `OrderDue` (orders whose earliest-fill time has arrived) | order id |
Sort key: `(available_at, priority, seq)` where `seq` is a global monotonically increasing counter assigned at load time (stable, deterministic).

### Loop (Mode B/C)
```
for session in calendar.sessions_between(cfg.start, cfg.end):
    load events of the session (candles 1m + strategy tf, snapshots) sorted by key
    position, orders = INTRADAY positions never cross a session boundary (force-flat timer); OVERNIGHT positions, their frozen levels and exit timers are carried into the next session [v1.1]
    for each distinct timestamp T in order:
        clock.set(T)
        apply all events with available_at == T in priority order:
            CandleFinal : features.on_bar ; stops.check_candle(bar) ; (collect strategy-tf bars finalised at T)
            Snapshot    : features.on_snapshot ; stops.check_snapshot(snap) ; fills.on_snapshot(snap)
            Timer       : force-flat orders
            OrderDue    : fills.try_fill(order)
        after applying all events at T:
            for each strategy-tf bar finalised at T:
                decision = runner.on_finalized_bar(...)
                if ENTER: intent = selector.select(...) (Mode C) -> risk.evaluate -> order created (earliest_fill = T + latency)
                if EXIT : risk exits bypass (except RK-01/RK-13) -> order created
    at session end: any open INTRADAY position without a fill path => UNRESOLVED handling (§8.4.5); OVERNIGHT positions are carried (§8.3.6, §8.4.7)
finalize: metrics, report, manifest
```
Critical invariants asserted at runtime (raise `LookAheadError` on violation): every record read has `available_at ≤ clock.now`, except fill models reading `next_*` data with `available_at ≥ order.earliest_fill`; `clock` never moves backwards; an order's fill timestamp ≥ its `earliest_fill`.

## 8.3 Mode B — underlying directional simulation
### 8.3.1 Purpose and output
Mode B evaluates the *directional usefulness* of signals on NIFTY. It produces `UnderlyingDirectionalResult` in **index points**; it has no premium, quantity in lots, charges or rupees. One position at a time; BULLISH = long underlying exposure, BEARISH = short.

### 8.3.2 Execution timeframe
Strategy timeframe is arbitrary (`1m…1d` allowed; default `5m`). **Execution and stop resolution always use the 1m series** (`execution_tf = 1m`) so that intrabar paths are as fine as the data allow.

### 8.3.3 Fill models
| Model | Entry/exit price | Rationale |
|---|---|---|
| `SPOT_NEXT_OPEN` (default) | `open` of the first 1m bar with `bar_start ≥ decision_at + latency_s` (`latency_s = 0`) ± `slippage_points` adverse | Decision made at bar close; next tradable instant is the next bar's open. Optimistic by construction. |
| `SPOT_NEXT_CLOSE` | `close` of that same 1m bar ± slippage | Models ≈ 60 s of delay; used as the pessimistic comparison |
Every Mode B report must include **both** models and slippage sensitivity `slippage_points ∈ {0, 1, 2, 3}` (adverse points per side).

### 8.3.4 Stop/target/trailing resolution (path-blind, conservative) — exact rules
Let the position be long (BULLISH); short is the mirror image. Levels are frozen at entry (§6.2.3). For each 1m bar `b` after (and, for `SPOT_NEXT_OPEN`, including) the entry bar, in order:
1. If `b.open ≤ stop` (gap through stop): exit at `b.open` (reason `STOP`, `gap=true`).
2. Else if `b.low ≤ stop` **and** `b.high ≥ target`: exit at `stop` (reason `STOP`, `ambiguous=true` — conservative: the loss is assumed to occur first).
3. Else if `b.low ≤ stop`: exit at `stop`.
4. Else if `b.high ≥ target`: exit at `target` (for a gap above target use `target`, not the better open — conservative).
5. Else update trailing level from this bar's **close** (effective from the next bar) and continue.
For `SPOT_NEXT_CLOSE` the entry bar is skipped for stop/target checks (the position starts at its close).
Signal/time/force-flat exits: decision at the strategy bar close (or timer) → fill by the selected fill model.
`slippage_points` is added adversely to every stop/target/market fill price.
Trade record fields: `entry_ts, entry_px, exit_ts, exit_px, direction, pnl_points (= (exit−entry) for BULLISH, (entry−exit) for BEARISH, after slippage), ret_pct = pnl_points / entry_px × 100, exit_reason, bars_held, mfe_points, mae_points, ambiguous, gap`.

### 8.3.5 Mode B metrics (§8.10.1) and hurdle table
Report `net_points(h) = Σ(pnl_points − h)` and `expectancy(h)` for round-trip hurdles `h ∈ {0, 2, 4, 6, 8}` points, plus the option-aware hurdle estimate from Mode C data (§8.12.1) when available. **Mode B never states rupee or option P&L.**

### 8.3.6 [v1.1] OVERNIGHT (carry) positions in Mode B
Applies when the strategy declares `duration_profile = OVERNIGHT`. Notation: `sign = +1` BULLISH, `−1` BEARISH.
- **Entry.** Decision at a strategy-bar close inside the account's `overnight_entry_window` (default up to 15:25) and the strategy's own `trading_window`; fill by the selected fill model on the 1m series (§8.3.3). A decision whose fill bar would fall after the last 1m bar of the session is rejected `NO_FILL_BAR_IN_SESSION`. Sessions whose last bar (15:29) is missing (≈ 15 historical days, HLD §3.3) are flagged `DEGRADED_CLOSE`; entries on them are skipped unless `allow_degraded_close = true` (default false).
- **Carry.** The position, its frozen stop/target levels and its trailing state persist across sessions. 1m bar iteration continues across the session boundary; the first bar of a new session is tested by rule 1 of §8.3.4 (gap through the stop exits at that bar's open, `gap = true`). Target gaps use the target, never the better open (conservative, unchanged).
- **Exit.** A timer at `time_exit` on the `exit_session_offset`-th next session (calendar-driven, so Friday → Monday is offset 1). BTST default: offset 1, `"09:15"`. The exit decision is created at the timer; `SPOT_NEXT_OPEN` fills at the open of the 09:15 bar (the opening print) and `SPOT_NEXT_CLOSE` at that bar's close (≈ 09:16, the pessimistic comparison); both are always reported. If the calendar lists the exit session but no candles exist, the trade is `UNRESOLVED_OVERNIGHT`, excluded from metrics and counted.
- **Trade record additions.** `duration_profile, sessions_held, calendar_days_held, gap_points, session_points`, where `gap_points = Σ_{boundaries crossed} (first_open_of_next_session − last_close_of_previous_session) × sign` and `session_points = pnl_points − gap_points` (computed on raw prices; slippage is reported separately).
- **Metrics.** In addition to §8.10.1: expectancy by `sessions_held`, mean `gap_points` vs mean `session_points`, share of trades whose sign is decided by the gap, and the overnight hurdle table (§8.12.3). Mode B still states no rupee or option P&L.


## 8.4 Mode C — actual-options simulation
### 8.4.1 Data and eligibility
Window: sessions with option data (from 2026-01-20). A decision is executable only if (a) the selector returns `OK` with a snapshot not older than `max_snapshot_age_s` (75 s), and (b) a fill snapshot exists within `max_fill_wait_s` (75 s) after `decision_at + latency_s`. Otherwise the decision is **rejected with a reason** and counted; no premium is invented.

### 8.4.2 Fill model `OPT_SNAPSHOT_BIDASK`
Parameters (defaults, **[OWNER]**): `latency_s = 2`, `max_fill_wait_s = 75`, `slippage_ticks = 1` (tick = ₹0.05), `respect_top_of_book = false`.
```
order.earliest_fill = order.created_at + latency_s
fill_snapshot = first snapshot with available_at >= earliest_fill and available_at - earliest_fill <= max_fill_wait_s
contract row = fill_snapshot row for order.instrument_id        # must exist and quote_status == OK
BUY : price = round_up_to_tick(ask)  + slippage_ticks * tick
SELL: price = round_down_to_tick(bid) - slippage_ticks * tick   (floor at one tick)
if respect_top_of_book and qty > ask_qty/bid_qty (v3/api_v4 only): partial fill = available qty; remainder EXPIRES
else: full fill, flag LIQUIDITY_UNCHECKED when qty > top-of-book qty (counted in coverage)
fill_ts = fill_snapshot.available_at
```
If no qualifying snapshot or the contract row is missing/one-sided: entry order → `EXPIRED` (reason `NO_FILL_SNAPSHOT` / `NO_VALID_QUOTE`), no trade. For exits see §8.4.5.

### 8.4.3 Exit triggers
| Trigger | Detected when | Order created at |
|---|---|---|
| Signal exit | strategy bar close | `decision_at` |
| UNDERLYING-basis stop/target/trailing | at the close of a 1m bar whose high/low touched the level using the **§8.3.4 rules** (so detection is at `bar_end`, never intrabar) | `bar_end` of that 1m bar |
| PREMIUM-basis stop | a snapshot with `bid ≤ stop_px` | that snapshot's `available_at` |
| PREMIUM-basis target | a snapshot with `bid ≥ target_px` | that snapshot's `available_at` |
| PREMIUM trailing | trailing level = `max(bid seen since entry) × (1 − v/100)`; trigger when `bid ≤ level` | that snapshot's `available_at` |
| `max_bars` / `time_exit` / force flat | timer at the stated bar close/time | the timer time |
All exits are **market orders filled by the same rule as entries** (first snapshot ≥ `created_at + latency_s`). A stop detected at snapshot *k* therefore fills at snapshot *k+1*'s bid — deliberately path-blind and delay-honest; it can be better or worse than the stop level (never clipped to it).

### 8.4.4 Positions, sizing, marking
One open position at a time **[OWNER]**; further ENTER decisions are ignored with `ALREADY_IN_POSITION`. Quantity: `fixed_lots` → `lots × lot_size`; `risk_pct` → `lots = floor( (pct/100 × equity) / ((ask − stop_px) × lot_size) )` using a PREMIUM stop (else rejected `RISK_SIZE_UNDEFINED`), when lots = 0 the strategy's `sizing.if_below_one_lot` decides (`REJECT` → rejection `RISK_BELOW_ONE_LOT`; `ONE_LOT` → 1 lot, still subject to RK-07/RK-08); lots are always capped by the effective RK-06 ceiling (§8.6.3). Equity marks at every snapshot using the **bid** (liquidation value) for the open position. INTRADAY positions are forced flat at `force_flat_time` (default 15:15). OVERNIGHT positions are carried (§8.4.7).

### 8.4.5 End-of-session handling for open INTRADAY positions
1. Try the normal fill rule from the force-flat order (created 15:15:00).
2. If no snapshot within the wait window: use the first snapshot until 15:29:00, trade flag `LATE_EXIT`.
3. Else use the last snapshot bid before 15:15, flag `STALE_EXIT`.
4. Else (no snapshot after entry at all): trade is `UNRESOLVED`, excluded from performance metrics, listed in the report. If unresolved trades exceed 2% of trades the run status is `INCOMPLETE` and the headline metric carries that label.

### 8.4.6 Coverage report (mandatory in every Mode C result)
`sessions_total, sessions_with_option_data, decisions_total, decisions_executable, rejections_by_reason {NO_DATA_FOR_EXPIRY, STALE_SNAPSHOT, GREEKS_UNAVAILABLE, STRIKE_NOT_LISTED, NO_VALID_QUOTE, SPREAD_TOO_WIDE, PREMIUM_TOO_LOW, NO_FILL_SNAPSHOT, RISK_*}, trades_total, trades_unresolved, late_exits, stale_exits, liquidity_unchecked_fills, overnight_trades, overnight_unresolved, late_open_exits, risk_mode, rejections `RISK_BELOW_ONE_LOT`/`RISK_CLAMPED` counts, schema_mix {v1,v2,v3,api_v4 sessions}, effective_sample {days_traded, trades}`.

### 8.4.7 [v1.1] OVERNIGHT positions in Mode C
- **Eligibility.** The selector (§7.2 step 2a) guarantees the contract is alive at the exit session.
- **Carry and marks.** The position persists; its end-of-session mark is the **bid of the last valid snapshot of the entry session**, flagged `OVERNIGHT_MARK` (not `STALE`, §9.4).
- **Exit timer.** At `time_exit` of the exit session (BTST default 09:15). Fill rule: the first snapshot with `available_at ≥ timer + latency_s` within `overnight_exit_max_wait_s` (default 600 s **[OWNER]**; longer than the intraday 75 s because collectors have often started late). If no snapshot qualifies, the first snapshot of that session at or before 10:30 is used and the trade is flagged `LATE_OPEN_EXIT` (its P&L is *not* an opening-exit result and is reported separately). If none by 10:30 the trade is `UNRESOLVED_OVERNIGHT`: excluded from metrics, listed, and when more than 10% of overnight trades are unresolved the headline carries `INCOMPLETE`.
- **Stops across sessions.** PREMIUM stops/targets trigger at the first snapshot satisfying the condition, including the first snapshot of the next session (a gap), and fill at the next snapshot's bid per §8.4.3. UNDERLYING stops use the 1m path across sessions with §8.3.6 rule 1.
- **Honesty banner.** Every Mode C report with overnight trades states: "Option snapshots cover only sessions since 2026-01-20; sessions whose collector started after 09:20 cannot evaluate opening exits." Index-only overnight research belongs in Mode B.


## 8.4.8 [v1.2] Fill sources, quote quality and the Mode C quote fill model — status: DESIGNED
**(a) LTP is never executable.** LTP is used only for display, features and sanity checks. Not for fills, marks, stop/target triggers, equity or charges. Marks and PREMIUM triggers on a long option use the **bid**; entry fills use the **ask** (corrects HLD P2 wording in v1.1).

**(b) Fill source.** Every simulated fill carries `fill_source ∈ {SNAPSHOT, QUOTE}`.
- `OPT_SNAPSHOT_BIDASK` (default, §8.4.2) → `SNAPSHOT`: only the 30-second REST chain exists, so nothing between two snapshots is known.
- `OPT_QUOTE_BIDASK` → `QUOTE`: uses the recorded WebSocket quotes (`QuoteRepository.next_quote_after`) and exists **only for sessions and contracts the recorder actually covered** (`quote_coverage`). The recorder started at gate G0.8 (date stored in `data/ops/recorder_start.json`); **nothing earlier can be reconstructed** and no report may say otherwise.
- `OPT_HYBRID`: use `QUOTE` when a qualifying quote exists within `quote_max_wait_s` (5), else `SNAPSHOT` (`settings.fills.mode_c_quote_fallback`: `REJECT` default for `OPT_QUOTE_BIDASK`, `SNAPSHOT` for `OPT_HYBRID`). The fill-source mix is reported; a HYBRID run is never compared with a SNAPSHOT-only run without that label.

**(c) Quote requirements (both sources).**
| Requirement | SNAPSHOT | QUOTE |
|---|---|---|
| Age at decision/selection | ≤ `max_snapshot_age_s` (75 s) | ≤ `max_live_quote_age_s` (5 s) |
| Fill timing | first snapshot with `available_at ≥ created_at + latency_s` within 75 s | first quote with `received_at ≥ created_at + latency_ms` within 5 s |
| Two-sided & sane | `bid > 0`, `ask > 0`, `bid ≤ ask`, else `NO_VALID_QUOTE` | same |
| Spread | RK-05 at decision; at fill `spread_rel > fills.fill_max_spread_rel` (0.10) ⇒ entry `EXPIRED` `SPREAD_WIDENED`; **exits are never blocked** (flag `EXIT_WIDE_SPREAD`) | same |
| Depth | top-of-book quantity only (v3/api_v4); `LIQUIDITY_UNCHECKED` counted | 5-level depth walk (VWAP across levels); insufficient visible depth ⇒ partial fill, entry remainder `EXPIRES`, exit remainder continues |
| Latency | `latency_s` = 2 | `latency_ms` = 500 |

**(d) Gaps through stops.** A PREMIUM stop is detected at the first quote/snapshot with `bid ≤ stop_px` and fills at the next eligible bid, **never clipped to the stop** (§8.4.3). Record `gap_overshoot_paise = (stop_px − fill_px) × qty`. If the first observation already shows both stop and target conditions satisfied, the stop is assumed first (`ambiguous=true`).

**(e) Resolution of every exit.** `exit_resolution ∈ {NORMAL, LATE_EXIT, STALE_EXIT, LATE_OPEN_EXIT, AMBIGUOUS, UNRESOLVED}`. Reports show counts per value and give **bounds**: headline `net_pnl` (excluding unresolved, as in §8.4.5) **and** `net_pnl_if_unresolved_total_loss` (each unresolved long option valued at a zero exit) so the reader sees how much the omission could matter.
Tests: T-SIM-15 LTP never reaches a fill/mark/trigger (a fixture whose LTP is wildly off the bid/ask); T-SIM-16 `QUOTE` fill uses ask/depth walk and respects 5 s wait; T-SIM-17 `HYBRID` mix is reported and fallback honours the setting; T-SIM-18 `SPREAD_WIDENED` expires an entry but not an exit; T-SIM-19 a session before `recorder_start` can never yield a `QUOTE` fill.

## 8.5 Cost model (`simulation/costs.py`)
### 8.5.1 Config (`config/costs/upstox_nse_options.yaml`)
```yaml
version: "2026-10-10"
segment: NSE_INDEX_OPTIONS
currency: INR
brokerage:   {type: flat_per_executed_order, amount_paise: 2000}        # [VERIFY] Upstox charge list: flat Rs 20 per executed order
stt_sell_premium_rate:                                                   # charged on SELL side premium turnover only
  - {from: 1900-01-01, to: 2024-09-30, rate: 0.000625}
  - {from: 2024-10-01, to: 2026-03-31, rate: 0.001}
  - {from: 2026-04-01, to: null,       rate: 0.0015}                     # Budget 2026, effective 2026-04-01 [VERIFY via NSE/Upstox contract note]
exchange_txn_rate:                                                       # premium turnover, both sides
  - {from: 1900-01-01, to: 2024-09-30, rate: 0.000495}
  - {from: 2024-10-01, to: null,       rate: 0.0003553}                  # sources show 0.03503% (Oct 2024) and 0.03553% (later); higher used until verified
ipft_rate: 0.000001                                                      # Rs 10 per crore, both sides [VERIFY: may be inside the exchange charge; included separately as in Upstox's GST base]
sebi_rate: 0.000001                                                      # Rs 10 per crore, both sides
stamp_buy_rate: 0.00003                                                  # 0.003% on BUY premium turnover
gst_rate: 0.18
gst_base: [brokerage, exchange_txn, sebi, ipft]
rounding: {component: paise_half_up, stt: nearest_rupee_half_up}         # [VERIFY] against owner's real contract notes
brokerage_counted: once_per_order_id                                     # partial fills of one order share one brokerage charge
status: UNVERIFIED_PARAM                                                 # becomes VERIFIED after ticket T7.x reconciliation
```
### 8.5.2 Formulas
For a fill with `qty` units at price `p` (₹): turnover `T = qty × p`.
```
brokerage = 20.00 (once per order)
txn   = round(T × exchange_txn_rate)           sebi = round(T × sebi_rate)       ipft = round(T × ipft_rate)
stamp = round(T × stamp_buy_rate)  (BUY only)  stt  = round_rupee(T × stt_rate) (SELL only)
gst   = round(gst_rate × (brokerage + txn + sebi + ipft))
total = brokerage + txn + sebi + ipft + stamp + stt + gst
```
### 8.5.3 Worked example (must be reproduced by test T-COST-1)
Buy 65 @ ₹100.00 (T = 6,500.00): brokerage 20.00, txn 2.31, sebi 0.01, ipft 0.01, stamp 0.20, stt 0, gst 4.02 → **₹26.55**.
Sell 65 @ ₹120.00 (T = 7,800.00): brokerage 20.00, txn 2.77, sebi 0.01, ipft 0.01, stamp 0, stt 12 (0.15% × 7,800 = 11.70 → 12), gst 4.10 → **₹38.89**.
Round trip charges ₹65.44; gross P&L ₹1,300.00; **net ₹1,234.56**.

## 8.6 Risk engine (`quantview.risk`)
```python
class RiskDecision(BaseModel):
    approved: bool; rule_ids_failed: list[str]; details: dict[str, Any]
    profile_version: str; evaluated_at: datetime

class RiskEngine:
    def evaluate(self, intent: OrderIntent, account: AccountView, market: MarketHealth, ctx: RiskContext) -> RiskDecision
```
All rules are evaluated (no short-circuit) so the audit shows every failure; the decision is rejected if any fails. **Exits** (SELL closing an open long) are exempt from every rule except RK-01 and RK-13, so risk can never trap a position.

### 8.6.1 [v1.1] Rule classes and who may change what
| Class | Meaning | May be overridden? |
|---|---|---|
| **HARD** | Safety and integrity (kill switch, stale data, allowed instrument/side, idempotency, account-state certainty, cash) | Never: not by a strategy, not by a profile, not in research runs |
| **CEILING** | Owner risk policy (lots, outlay, risk per trade, daily loss, drawdown, entries, spread, expiry-day) | A strategy may only **tighten** a ceiling. Ceilings are relaxed only (a) in a `RESEARCH_RELAXED` research run (§8.6.5) or (b) by publishing a new versioned account profile (audited) |
| **PERMISSION** | What may be done when (entry windows, overnight allowed) | Profile-controlled per `duration_profile` |

### 8.6.2 Rules (IDs are stable)
| ID | Class | Rule | Default (`paper_default` profile) |
|---|---|---|---|
| RK-01 | HARD | Instrument allowed: NIFTY CE/PE only; side BUY-to-open or SELL-to-close; **no SELL_TO_OPEN** | — |
| RK-02 | HARD | Global and per-strategy kill switch off | off |
| RK-03 | PERMISSION | Entry window by duration: INTRADAY `entry_window_intraday`, OVERNIGHT `overnight_entry_window`; `decision_at` must also lie inside the strategy's `trading_window` | 09:20–15:00; 09:20–15:25 |
| RK-04 | HARD | Quote/snapshot age ≤ limit | snapshot 75 s; live quote 5 s |
| RK-05 | CEILING | Spread `(ask−bid)/mid ≤ max_spread_rel` | 0.04 |
| RK-06 | CEILING (qty multiple of lot and ≤ `freeze_units` are HARD) | `lots ≤ effective max_lots_per_order` | 2 lots; 1,800 units `[VERIFY]` |
| RK-07 | CEILING | Outlay `ask × qty ≤ effective max_outlay_pct × equity` | 60% |
| RK-08 | CEILING | Risk per trade ≤ `effective max_risk_pct × equity`, where risk is the amount of the resolved **risk basis** (§8.6.8: `PLANNED_PREMIUM_STOP` or `WORST_CASE_OUTLAY`) | 5% |
| RK-09 | CEILING | Open positions in the account < `max_open_positions` | 1 |
| RK-10 | CEILING | `entries_today < max_entries_per_day`; `orders_today < max_orders_per_day` | 6; 20 |
| RK-11 | CEILING | Daily loss (realised + unrealised, against start-of-day equity **including carried positions marked at the previous close**) `< effective daily_loss_limit_pct`; breach ⇒ no entries and flatten all positions | 10% |
| RK-12 | CEILING | Consecutive losing trades today `< effective max_consecutive_losses` | 3 |
| RK-13 | HARD | Idempotency key not already used | — |
| RK-14 | CEILING | Orders in the last 60 s `< max_orders_per_minute` | 6 |
| RK-15 | CEILING | If expiry day: minutes to expiry `≥ min_minutes_to_expiry` (entries) | 30 |
| RK-16 | HARD | Account state certain (ledger invariants OK; reconciliation not failed) | — |
| RK-17 | HARD | Feed/collector healthy (paper/live): index tick age ≤ `feed_stale_s`, DQ status not `UNUSABLE` | 10 s |
| RK-18 | HARD | Cash covers `outlay + estimated charges` | — |
| RK-19 | PERMISSION **[v1.1]** | OVERNIGHT entries only if `allow_overnight` and the selected contract's expiry is after `session_date` | allowed |
| RK-20 | CEILING **[v1.1]** | Account drawdown: `equity ≥ (1 − max_drawdown_pct/100) × peak_equity`; breach ⇒ no entries until the owner clears it (audited) | 25% |
| RK-21 | HARD **[v1.1]** | Sizing feasibility: `lots ≥ 1` after sizing (§8.6.3); else rejection `RISK_BELOW_ONE_LOT` | — |
| RK-22 | HARD **[v1.2]** | Risk quantifiable: valid ask, resolved quantity/lot, PREMIUM stop present and valid when risk-based sizing is requested, equity known (§8.6.8); else rejection `RISK_UNQUANTIFIABLE`. Not relaxable, not bypassed by `ONE_LOT` | — |
Exits (SELL closing an open long) are exempt from every rule except RK-01 and RK-13. Evaluation order for reporting: RK-02, RK-16, RK-17, RK-01, RK-13, RK-03, RK-19, RK-15, RK-04, RK-05, RK-09, RK-10, RK-12, RK-11, RK-20, RK-21, RK-22, RK-06, RK-18, RK-07, RK-08, RK-14.

### 8.6.3 [v1.1] Effective limits and sizing (strategy risk inside account ceilings)
For every CEILING `L` with account value `a_L` and a strategy-declared value `s_L` (from `RiskSpec`, or `None`): `effective_L = min(s_L, a_L)` for maxima (and the more conservative value for any minimum); `None` inherits `a_L`. A strategy that omits `risk` therefore runs on the account defaults (for example the 5% per-trade ceiling). A strategy that asks for more than a ceiling is **clamped** and its decisions carry `RISK_CLAMPED` with `details = {limit, requested, effective}`; clamp counts appear in every report so the owner sees "this strategy wants 8% but the account allows 5%".
Sizing, evaluated at order creation (`ask`, `stop_px`, `lot_size`, `equity` as of the decision):
```
r_eff     = min(requested_pct, effective max_risk_pct)               # risk_pct sizing; fixed_inr_risk: min(inr, effective max_risk_pct/100 × equity)
lots_risk = floor( (r_eff/100 × equity) / ((ask − stop_px) × lot_size) )    # needs a PREMIUM stop, else RISK_SIZE_UNDEFINED
lots_cap  = floor( effective max_outlay_pct/100 × equity / (ask × lot_size) )
lots      = min(lots_risk or sizing.lots, effective max_lots_per_order, lots_cap)
if lots < 1: ONE_LOT → lots = 1 (RK-07/RK-08 still decide) ; REJECT → rejection RISK_BELOW_ONE_LOT (RK-21)
```
Account size is a parameter, not a constant: every ceiling is a percentage of equity, and the only absolute numbers in the risk system are tick size, lot size and freeze quantity.

### 8.6.4 [v1.1] Account profiles (`config/risk/profiles/<profile_id>.yaml`, versioned, audited)
```yaml
profile_id: paper_default
version: "1.1.0"
account: {starting_equity_paise: 2000000, currency: INR}   # any amount; a paper account chooses its own equity at creation (₹20,000 shown)  [OWNER]
ceiling_mode: ENFORCE              # ENFORCE | RESEARCH_RELAXED | ADVISORY (ADVISORY: MANUAL accounts only, §8.8.2)
allow_overnight: true
entry_window_intraday: {start: "09:20", end: "15:00"}
overnight_entry_window: {start: "09:20", end: "15:25"}
force_flat_time: "15:15"           # INTRADAY positions only
max_lots_per_order: 2
max_outlay_pct: 60.0               # starting values derived by arithmetic for a ₹20k account with 65-unit lots; revisit per account size  [OWNER]
max_risk_pct: 5.0                  # default and ceiling for risk per trade                                              [OWNER]
max_open_positions: 1
max_entries_per_day: 6
max_orders_per_day: 20
max_orders_per_minute: 6
daily_loss_limit_pct: 10.0
max_drawdown_pct: 25.0
max_consecutive_losses: 3
max_spread_rel: 0.04
max_snapshot_age_s: 75
max_live_quote_age_s: 5
feed_stale_s: 10
min_minutes_to_expiry: 30
freeze_units: 1800
overnight_risk_basis: WORST_CASE_OUTLAY   # [v1.2] WORST_CASE_OUTLAY | PLANNED_PREMIUM_STOP (owner decision D-06, §8.6.8)
live_enabled: false
```
A second shipped profile, `research_relaxed.yaml`, is identical except `ceiling_mode: RESEARCH_RELAXED`, `starting_equity_paise: 50000000` and `allowed_modes: [B, C, S]` (it cannot be bound to a paper or live account). Editing a profile through the API or UI creates a new immutable version; an account binds to `profile_id@version`; moving to a new version is an audited event. Live profiles are separate files, default disabled, and require an owner-signed checklist (Phase 9).

### 8.6.5 [v1.1] `RESEARCH_RELAXED` runs (how a high-risk, high-reward strategy is tested)
- Allowed only in Modes B/C/S and only with `purpose ∈ {exploration, tuning, validation}`; never for `holdout` or for paper/live.
- CEILING rules are still *evaluated and counted* (`would_reject` per rule) but do not reject; sizing uses the strategy's own `RiskSpec` unclamped. HARD rules stay enforced.
- The manifest records `ceiling_mode = RESEARCH_RELAXED`; every report, API response and chart header shows "RISK RELAXED — NOT DEPLOYABLE AS IS".
- Deployment to a paper account is permitted only after an ENFORCE run of the same strategy version exists, or with an explicit, audited `ack_relaxed_only = true`. In paper the account's ceilings apply, so an aggressive strategy needs an account profile whose ceilings the owner has deliberately raised (for example a separate "experimental" account with its own equity). The strategy never bypasses a ceiling by itself.
- For capital-agnostic research, use `fixed_lots = 1` and read results per lot (points and ₹ per lot); percentage-risk sizing is meaningful only against a real account size.

### 8.6.6 [v1.1] Profile validation (loader raises `PROFILE_INCONSISTENT` / emits warnings)
Errors: `max_risk_pct > max_outlay_pct` (a long option cannot lose more than its outlay); `max_outlay_pct > 100`; `force_flat_time ≤ entry_window_intraday.end`; unknown keys. Warnings: `daily_loss_limit_pct < 2 × max_risk_pct` (two stop-outs end the day); `max_drawdown_pct < daily_loss_limit_pct`; `starting_equity × max_outlay_pct/100 < lot_size × min_premium` (`ACCOUNT_BELOW_ONE_LOT`). Tool `scripts/profile_feasibility.py <profile> <equity>` replays the last N sessions of ATM snapshots and reports the share of snapshots on which one lot fits inside RK-07/RK-08 — the answer to "can this account trade this strategy at all?" before any backtest.

### 8.6.7 Strategy health gate (before risk)
A strategy deployment is **paused** automatically when: feed stale; required features not ok for > 5 consecutive bars; DQ status `UNUSABLE`; ledger invariant failure; kill switch. Pausing blocks new entries; open positions are managed (stops/exits) if data allow, else flattened at the first valid quote. **[v1.1]** Pausing never silently carries an INTRADAY position: it is flattened at `force_flat_time` if data allow, else at the first valid quote of the next session with the flag `FORCED_CARRY` and an alert.


### 8.6.8 [v1.2] Option-specific risk semantics (ADR-028) — status: DESIGNED
**Principle.** A stop on the *underlying* is a trigger for an exit **decision**, not a statement about premium loss. For a long option only one loss bound is guaranteed: **premium paid + charges**. Everything between entry and that bound is an estimate and is labelled as such. No screen, report or log may show "maximum loss = X" derived from an underlying stop.

**Risk bases.** Resolved at order creation and stored on the order (`risk_basis`, `risk_amount_paise`):
| Basis | Amount | Used when |
|---|---|---|
| `PLANNED_PREMIUM_STOP` | `(ask − premium_stop_px) × qty` — *planned, not guaranteed* (path-blind detection, fill at the next eligible bid, gaps) | INTRADAY entry that carries a PREMIUM-basis stop |
| `WORST_CASE_OUTLAY` | `ask × qty + estimated entry charges` | everything else: UNDERLYING-basis stops only, no stop, and (default) every OVERNIGHT entry (`overnight_risk_basis`, owner decision D-06) |
RK-08 compares the amount of the resolved basis with `effective max_risk_pct × equity`. There is **no** translation of underlying points into premium points inside risk or sizing (a delta-based estimate belongs to Mode S and is never used for limits).

**How an underlying exit executes.** Detection at the close of a 1m bar by the §8.3.4 touch rules → exit decision → SELL MARKET on the option at the next eligible quote (§8.4.3, §8.8). Realised loss may be smaller or larger than any planned figure. Every trade therefore stores `planned_risk_paise` (nullable), `realised_loss_paise` and `risk_overshoot_ratio = realised_loss / planned_risk` (null without a plan). Reports show the share of losing trades with ratio > 1 and the p95 ratio (BACKTESTING_REPORT_SPEC §7).

**Sizing without a premium stop.** Only `fixed_lots` is meaningful. `risk_pct` / `fixed_inr_risk` ⇒ rejection `RISK_SIZE_UNDEFINED`. The outlay cap and RK-06 still apply. With basis `WORST_CASE_OUTLAY`, one lot on a small account often breaches RK-08 — the correct outcome, surfaced beforehand by `profile_feasibility` (extended to print the basis used).

**RK-22 (HARD) — risk must be quantifiable.** An entry is rejected `RISK_UNQUANTIFIABLE` (with one sub-reason) when: (1) no valid ask (missing, one-sided, crossed, zero) within the age limit; (2) quantity or lot size unresolved; (3) risk-based sizing was requested but no PREMIUM stop exists; (4) the PREMIUM stop is `≤ 0` or `≥ ask`; (5) equity unknown (RK-16 failing); (6) the effective profile lacks a ceiling needed by the sizing rule. RK-22 cannot be relaxed (`RESEARCH_RELAXED` keeps it enforced), clamped, or bypassed by `ONE_LOT`.

**The one-lot fallback can never override a hard or affordability limit.** `if_below_one_lot = ONE_LOT` changes *sizing* from 0 to 1 lot and nothing else. The resulting order is then evaluated by **every** rule — RK-06, RK-07, RK-08, RK-18 (cash incl. estimated charges), RK-22 — and is rejected if any fails. In `RESEARCH_RELAXED`, CEILING rules (RK-07/08) are counted not enforced; HARD rules (RK-18, RK-22) still reject. Test T-RK-27.

**Gaps, spreads, stale quotes, overnight.**
| Situation | Entry | Exit |
|---|---|---|
| Spread above `max_spread_rel` at decision | RK-05 rejects | not blocked; flag `EXIT_WIDE_SPREAD` |
| Spread widens decision → fill | entry `EXPIRED` `SPREAD_WIDENED` | not blocked |
| Quote missing / stale | RK-04 / RK-22 reject | order waits, retries every 5 s, alert at 60 s; **LTP is never substituted** |
| Gap through a premium stop | n/a | fills at next eligible bid, `gap=true`, overshoot recorded |
| Overnight gap | RK-19; basis `WORST_CASE_OUTLAY`; gap loss counts in next day's RK-11 | stops evaluated from the first quote; fill at that bid |
| Expiry day | RK-15 | INTRADAY force-flat applies; OVERNIGHT cannot exist across expiry (selector §7.2 2a) |

### 8.6.9 [v1.2] Exit/entry priority — who wins (ADR-028) — status: DESIGNED
At most **one live exit order per position**. Reasons are ranked; a lower rank number wins.
| Rank | Source | Reason | Notes |
|---|---|---|---|
| 0 | Operator | `KILL_SWITCH` with `action = BLOCK_AND_FLATTEN` (global or `strategy:<id>`), `OPERATOR_FLATTEN` | market exit immediately, retried until flat |
| 1 | Risk engine | `RISK_FORCED_FLATTEN` (RK-11 breach); RK-16 uncertainty ⇒ hold and alert (never trade on an uncertain ledger) | |
| 2 | Engine timers | `FORCE_FLAT` (INTRADAY), overnight exit timer, `TIME_EXIT`, `max_bars` | |
| 3 | Engine | `STOP`, `TARGET`, `TRAIL` (engine-owned, frozen at entry) | |
| 4 | Strategy | `SIGNAL_EXIT` | |
Rules: **(a)** a reason of lower rank than the live exit order's replaces it (live order `CANCEL_REQ`, new order with `supersedes_order_id`; if the old one fills first the new one is dropped `EXIT_NOT_NEEDED`); **(b)** an equal or higher rank number while an exit order is live is recorded `EXIT_ALREADY_PENDING` and ignored; **(c)** entries are blocked whenever any rank 0–1 condition is active for the account/strategy, and always by HARD rules; **(d)** risk rejection applies to entries only — an exit is never rejected by a CEILING rule; **(e)** `kill_switch.action ∈ {BLOCK_ENTRIES (default), BLOCK_AND_FLATTEN}`; both block every new entry including manual ones. `BLOCK_ENTRIES` never leaves a position unmanaged: stops and timers keep running; **(f)** an owner's explicit exit on a manual-account position is always accepted (exempt from CEILINGs); with no valid quote it waits and shows why, it is never silently dropped.
Tests: T-RK-28 priority matrix (every pair of ranks); T-RK-29 supersede-and-race; T-RK-30 `BLOCK_ENTRIES` keeps stops alive; T-RK-31 `BLOCK_AND_FLATTEN` retries to flat; T-RK-32 RK-22 sub-reasons and non-overridability.

## 8.7 Order lifecycle (`quantview.execution.order_state`)
### 8.7.1 States
`INTENT_CREATED, RISK_REJECTED, APPROVED, SUBMITTED, OPEN, PARTIALLY_FILLED, FILLED, CANCEL_PENDING, CANCELLED, REJECTED, EXPIRED, UNKNOWN` (UNKNOWN only for live submissions with unconfirmed outcome).
### 8.7.2 Legal transitions (everything else raises `ConflictError`)
| From | Event | To |
|---|---|---|
| INTENT_CREATED | `RISK_APPROVE` | APPROVED |
| INTENT_CREATED | `RISK_REJECT` | RISK_REJECTED (terminal) |
| APPROVED | `SUBMIT` | SUBMITTED |
| SUBMITTED | `ACK` | OPEN |
| SUBMITTED | `REJECT` | REJECTED (terminal) |
| SUBMITTED | `TIMEOUT_UNKNOWN` (live) | UNKNOWN |
| OPEN | `PARTIAL_FILL` | PARTIALLY_FILLED |
| OPEN / PARTIALLY_FILLED | `FILL` (cumulative = qty) | FILLED (terminal) |
| PARTIALLY_FILLED | `PARTIAL_FILL` | PARTIALLY_FILLED |
| OPEN / PARTIALLY_FILLED | `CANCEL_REQ` | CANCEL_PENDING |
| CANCEL_PENDING | `CANCEL_ACK` | CANCELLED (terminal; partial qty remains filled) |
| CANCEL_PENDING | `FILL` | FILLED (terminal) |
| OPEN / PARTIALLY_FILLED | `EXPIRE` | EXPIRED (terminal; keeps filled qty) |
| UNKNOWN | `RECONCILE_OPEN` / `RECONCILE_FILLED` / `RECONCILE_REJECTED` | OPEN / FILLED / REJECTED |
Rules: events carry `event_id` (ULID) — duplicates are ignored (idempotent); events arriving for a terminal order are stored as `LATE_EVENT` without state change; `SUBMIT` requires a prior `APPROVE`; the simulated adapters auto-emit `ACK` immediately. Every transition writes an `order_events` row.

## 8.8 Paper trading (`simulation/paper_runner.py`)
- **Process.** Subscribes to `candle.finalized`, `option.quote`, `feed.health` events; maintains per-deployment state in Postgres (`deployments`, §8.8.3) and is the **sole writer** for paper accounts, including the manual account (§8.8.2).
- **Strategy loop.** Same `StrategyRunner`, `ContractSelector` (live snapshot via the latest snapshot or quotes), `RiskEngine`, order state machine and `Ledger` as the engine.
- **Fill model `OPT_LIVE_BIDASK`** (defaults **[OWNER]**): `latency_ms = 500`, `max_wait_s = 5`, `slippage_ticks = 1`. Entry: first recorded quote for the contract with `received_at ≥ submit_time + latency` within `max_wait_s`; price = ask1 (walk visible depth levels if `qty > ask1_qty`: volume-weighted across levels; if the visible depth is insufficient, fill what is visible and `EXPIRE` the remainder) + slippage. Exit mirrors on bid levels. If no quote arrives within `max_wait_s`, the order `EXPIRES` (entries) or retries every 5 s up to force-flat (exits).
- **Live stop monitoring.** PREMIUM-basis stops/targets are checked on every quote; UNDERLYING-basis at every finalised 1m bar using §8.3.4 touch rules.
- **Restart recovery.** On start: load open orders/positions, replay the CONTROL journal from the consumer checkpoint inside the exactly-once transaction rule (§2.7.4), re-run `ledger.verify()`; if verification fails the deployment stays paused and alerts.
- **Isolation.** Full specification in §10.5 (schema `qv_paper`, restricted roles, no credentials, no broker code, tests T-ISO-*).
- All fills are labelled `simulated=true` with the fill-model name and version.

### 8.8.1 [v1.1] Overnight positions in paper trading
At start-up (before 09:15) the runner loads open positions from Postgres, `collect_live` pins their instrument keys (§4.10.1), and each position's frozen stop/target levels and exit timer are restored. Carried positions are marked at the previous session's last bid (`OVERNIGHT_MARK`) until the first live quote. The exit timer (BTST: 09:15) creates the exit order; fill by `OPT_LIVE_BIDASK` (§8.8). If no quote arrives within `max_wait_s`, the exit retries every 5 s until 10:30, then alerts and flags `LATE_OPEN_EXIT`. Stops are checked from the first quote, so a gap beyond the stop exits at that quote's bid (never clipped to the stop). In live mode (Phase 9) overnight positions require the broker's carry-forward product type rather than the intraday one; this is verified in the Phase 9 checklist.


### 8.8.2 [v1.2] Manual paper trading (ADR-029) — status: DESIGNED
A separate workflow from strategy paper trading. It reuses the order state machine (§8.7), the paper adapter and `OPT_LIVE_BIDASK` (§8.8), `CostModel` and the `Ledger` class — instantiated for a **different account** — and **no** second execution engine.

**Account.** `accounts.account_kind = 'MANUAL'`, `mode = 'PAPER'`. Created with `POST /manual/account` (starting equity any positive amount; default `manual_paper.default_equity_paise`). Exactly one ACTIVE manual account exists (partial unique index, §9.5). "Reset" archives the account and creates a new one; history stays queryable and nothing is deleted. It has its own cash, orders, fills, positions, realised/unrealised P&L, charges, ledger and performance reports. Strategy-paper accounts can never contain MANUAL orders and manual accounts can never contain STRATEGY orders (trigger, §9.5).

**Profile `manual_paper@1.0.0`** (`ceiling_mode: ADVISORY`, a third mode valid **only** for MANUAL accounts; `RESEARCH_RELAXED` remains invalid for paper). Manual orders are **not** governed by a strategy risk profile, strategy `RiskSpec`, sizing logic, entry windows (RK-03), `duration_profile`, force-flat or overnight permission. Applied rules:
| Rules | Behaviour for manual orders |
|---|---|
| HARD: RK-01 (long-only: BUY opens, SELL closes), RK-02 (global kill switch), RK-04 (quote age), RK-06 lot multiple and freeze quantity, RK-13, RK-16, RK-17 (feed healthy, DQ not `UNUSABLE`), RK-18 (cash incl. estimated charges), RK-22 (a valid ask exists) | **Enforced** |
| CEILING: RK-05, RK-07, RK-08, RK-09, RK-10, RK-11, RK-12, RK-14, RK-15, RK-20 | **Evaluated and returned as `advisories[]`** shown in the ticket (for example "outlay 72% of equity vs 60% reference"); not blocking unless the owner publishes a manual profile version with `ceiling_mode: ENFORCE` |
| PERMISSION: RK-03, RK-19 | Not applied; orders need an open session and a healthy feed only |
Manual positions are **never auto-flattened**; they carry across sessions under §9.4 overnight marks and their contract keys are pinned in the recorder (§4.10.1: pinned set = union over all ACTIVE paper accounts). Manual positions have no engine-owned stops; exits are explicit (§8.6.9 f).

**Order types (only what the simulator implements).** `MARKET` (fills per `OPT_LIVE_BIDASK`) and `LIMIT` (new, below). Validity `DAY` only (expires at 15:30, reason `DAY_END`). No SL, SL-M, IOC, AMO or modify (modify = cancel + new) in v1; the API returns `ORDER_TYPE_UNSUPPORTED` and the UI does not offer them.
- **LIMIT BUY** rests `OPEN` and fills against recorded quotes received **after** submission: visible ask levels with price `≤ limit` are walked (VWAP); price never exceeds the limit; `slippage_ticks` is not applied beyond the limit; depth shortfall ⇒ `PARTIALLY_FILLED` and the order keeps resting. **LIMIT SELL** mirrors on bid levels `≥ limit`. No retroactive fills.
- **MARKET** entry remainder `EXPIRES` after `max_wait_s`; MARKET exit retries until filled (§8.8).

**Validation (`POST /manual/orders/validate`, a dry run that returns exactly what `submit` will decide):** contract listed and quoted within the age limit; quantity a positive multiple of lot size and ≤ freeze quantity; price a multiple of 5 paise; SELL quantity ≤ open quantity; cash covers `est_fill × qty + est_charges` (cost model, labelled `ESTIMATE`; actual charges are posted at fill); returns `est_fill_price`, `est_outlay_paise`, `est_charges_paise`, `cash_after_paise`, `advisories[]`, `hard_failures[]`.

**Single writer.** The API never posts orders or fills. `POST /manual/orders` inserts a row into `order_commands` (`client_order_id` UNIQUE ⇒ double-click safe) and returns `202`. The `paper-runner` process (sole writer for paper accounts) consumes commands, creates the order with `origin = MANUAL`, runs risk, emits `ACK`, fills, posts the ledger and writes the outbox in one transaction. If the runner heartbeat is older than 15 s the API returns `RUNNER_UNAVAILABLE` (503) instead of queueing; a command not handled within `manual_paper.command_ttl_s` (30) becomes `EXPIRED` — a stale click can never execute later.

**Independence invariants (each has a test):** I-M1 distinct `account_id`s; I-M2 no table row combines two accounts' cash or positions; I-M3 projections are per account; I-M4 manual fills never invoke `StrategyRunner` or risk-profile sizing; I-M5 a deployment cannot target a MANUAL account (`DEPLOYMENT_TARGET_INVALID`) and a manual order cannot target a STRATEGY or LIVE account (`ACCOUNT_MODE_MISMATCH`); I-M6 every report filters by `account_id` and `origin`; I-M7 the only shared state is market data, the kill switch and the pinned-key union.
Tests: T-MN-1 independent ledger (buy+sell, charges, realised P&L equal hand values, `verify()` green); T-MN-2 manual trade leaves a strategy account's cash/positions/ledger/metrics byte-identical; T-MN-3 strategy fills leave the manual account unchanged; T-MN-4 LIMIT fill rules (price cap, no retroactive fill, partial); T-MN-5 validation parity (`validate` ≡ `submit` decision); T-MN-6 double submit ⇒ one order; T-MN-7 runner down ⇒ 503, stale command expires; T-MN-8 HARD rules enforced, CEILINGs advisory; T-MN-9 SELL > open quantity rejected; T-MN-10 restart with open manual position and resting LIMIT ⇒ state restored, no duplicates; T-MN-11 cancel while partially filled keeps filled quantity; T-MN-12 reset archives, never deletes; T-MN-13 origin recorded on order, fill and ledger event.

### 8.8.3 [v1.2] Deployment state machine (ADR-030) — status: DESIGNED
Applies to strategy paper deployments only. `run_id := deployment_id`.
| State | New entries | Exits, stops, timers | Meaning |
|---|---|---|---|
| `CREATED` | no | n/a | Row written, nothing running |
| `STARTING` | no | n/a | Pre-flight (below); on success → `RUNNING`, on failure → `ERROR` with reason |
| `RUNNING` | yes | yes | Normal operation |
| `PAUSED_USER` | no | yes (engine-owned **and** strategy signal exits) | Owner pause |
| `PAUSED_AUTO` | no | yes | Health gate (§8.6.7): feed stale, features not ok, DQ `UNUSABLE`, ledger failure, kill switch. Resumes only by owner action unless `auto_resume = true` |
| `DRAINING` | no | yes | Stop requested: manage the open position until flat (INTRADAY ends at force-flat; OVERNIGHT at its exit timer), then → `STOPPED` automatically |
| `STOPPED` | no | n/a | Terminal. A new run of the same strategy is a **new** deployment (clean attribution) |
| `ERROR` | no | **Position guardian**: engine-owned stops, targets, trailing, timers and force-flat keep running from the persisted frozen `ExitRules`; strategy signal exits are **not** evaluated (strategy code is not trusted after a fault) | Runner exception or invariant failure inside this deployment. Owner `acknowledge-error` → `PAUSED_USER`, or `stop` |
**Commands.** `start` (CREATED→STARTING→RUNNING); `pause` (RUNNING→PAUSED_USER); `resume` (PAUSED_*→RUNNING, pre-flight repeated); `stop {position_policy}`; `acknowledge-error`.
**Stop semantics — a stop never silently erases a position.**
- `position_policy = DRAIN` (**default**): stop new entries, keep managing the open position (stops, targets, signal exits, timers) until flat → `STOPPED`.
- `position_policy = FLATTEN`: an explicit liquidation. Requires `confirm_flatten = true`. Creates a rank-0 `OPERATOR_FLATTEN` exit (§8.6.9), state `DRAINING` until filled, then `STOPPED`.
- There is no "leave the position unmanaged" option in v1.
**Pre-flight (`STARTING`).** Account is ACTIVE, `account_kind = STRATEGY`, mode PAPER, risk profile bound and valid; strategy version immutable and valid; `RESEARCH_RELAXED`-only strategies need an ENFORCE run or an audited `ack_relaxed_only` (§8.6.5); no other non-terminal deployment on the account (`deployments.max_active_per_account = 1`; run two strategies in two strategy accounts so P&L stays attributable); feed `OK`; warm-up history present; calendar `VERIFIED`; contract keys of any carried position pinned.
**Recorded at start (`deployment_events`, append-only):** strategy id/version/`spec_hash`/params, `feature_pins`, account, risk profile `id@version` and `ceiling_mode`, fill-model and cost-model versions, `data_version` (calendar sha, rules sha), engine version (git SHA + dirty flag), actor, time. Every later transition appends `from_state, to_state, actor (OWNER | RUNNER | HEALTH_GATE), reason`.
**No duplicates on restart/replay.** Decision key = `deployment_id:spec_hash:timeframe:bar_start_iso:action`; order key = decision key + leg (§2.7.6). On runner start, deployments in `STARTING|RUNNING|PAUSED_*|DRAINING|ERROR` are re-loaded, positions and frozen exit levels restored, then journal replay applies §2.7.4 gating.
**Visualization is not part of this machine.** Toggling chart visibility (§12.2.1 `/viz`) never writes to `deployments`, `orders`, `fills` or `ledger_*` (T-VZ-4).
Tests: T-DP-1 legal/illegal transitions table; T-DP-2 `stop` default is DRAIN and the position stays managed to flat; T-DP-3 FLATTEN requires confirmation and exits; T-DP-4 ERROR ⇒ guardian still stops out, no signal exit evaluated; T-DP-5 PAUSED_AUTO needs owner resume (default); T-DP-6 second active deployment on one account refused; T-DP-7 deployment targeting a MANUAL account refused; T-DP-8 restart in each state restores it with no duplicate order; T-DP-9 config snapshot complete and immutable; T-DP-10 STOPPED cannot restart.

### 8.8.4 [v1.2] Partial fills, cancellations and corrections — status: DESIGNED
- Each partial fill is its own `fills` row (`fill_seq`) and its own `Ledger.post_fill`; position quantity and cost accumulate; order state follows §8.7.2.
- Cancel while partially filled: remainder cancelled, filled quantity stays and stays in the ledger. `CANCEL_PENDING` + `FILL` races resolve by the transition table (FILLED wins).
- A cancelled or expired order has **no ledger effect**; only fills move money.
- Fill corrections are never edits: `post_correction` = `REVERSAL` of the original fill event + a new fill with `corrects_fill_id`, in one transaction (§9.3.1).
Tests: T-AC-1 partial entry + partial exit + cancel of the rest (cash, cost release, `verify()`); T-AC-2 cancel/fill race; T-AC-3 correction leaves original events untouched; T-AC-4 invariants after restart + replay.

## 8.9 Run manifest and reproducibility (`simulation/manifest.py`)
```python
class RunManifest(BaseModel):
    run_id: str; created_at: datetime; mode: Literal["B","C","S","PAPER"]
    engine_version: str                      # git SHA + dirty flag
    data_version: dict                       # {candles_sha256, chain_sha256, calendar_sha256, rules_sha256, semantics_sha256}
    date_range: tuple[date, date]; execution_tf: str
    strategy: {id, version, spec_hash, params}
    feature_versions: dict[str, str]
    selection_policy_version: str | None
    fill_model: {name, version, params}; cost_model: {version, status} | None
    risk_profile_hash: str
    risk_profile_id: str | None; risk_profile_version: str | None     # [v1.1]
    ceiling_mode: Literal["ENFORCE","RESEARCH_RELAXED"] | None       # [v1.1]
    account_equity_paise: int | None                                   # [v1.1] Mode C / PAPER
    seed: int                                 # default 20260101
    purpose: Literal["exploration","tuning","validation","holdout"]
    holdout_registry_id: str | None
    n_trials_so_far: int                      # trials for this strategy family
    warnings: list[str]
    calendar_version: str; eligibility: dict           # [v1.2] §4.4.1 EligibilityReport
    metric_definition_versions: dict[str, str]         # [v1.2] §8.10.5
    deployment_id: str | None                          # [v1.2] PAPER (run_id == deployment_id)
    manifest_hash: str                        # sha256 of canonical JSON of all fields EXCEPT run_id, created_at
    result_hash: str                          # sha256 of the canonical trades table (sorted, fixed float format)
```
**Determinism requirement:** two runs with the same `manifest_hash` must have the same `result_hash` (test T-SIM-3).

## 8.10 Metrics (exact definitions)
### 8.10.1 Mode B (points)
| Metric | Definition |
|---|---|
| `n_trades`, `n_days` | counts |
| `hit_rate` | `#(pnl_points > 0)/n` |
| `expectancy_points` | mean `pnl_points` |
| `avg_win`, `avg_loss` | mean of positive / negative `pnl_points` |
| `payoff` | `avg_win / abs(avg_loss)` |
| `profit_factor` | `Σ wins / abs(Σ losses)` (∞ if no losses → reported as null with note) |
| `cum_points` | cumulative sum by trade order; `max_drawdown_points` = max over t of `(running_max − cum)` |
| `avg_bars_held`, `avg_minutes_held` | mean |
| `mfe_mean`, `mae_mean` | mean favourable / adverse excursion |
| `by_regime` | all of the above split by `expiry_regime` (0/1), by year, by weekday |
### 8.10.2 Mode C (₹)
Per trade: `gross_pnl = (exit_px − entry_px) × qty` (long option), `charges` (entry + exit), `net_pnl = gross − charges`, `r_multiple = net_pnl / initial_risk` where `initial_risk = (entry_px − premium_stop) × qty` if a premium stop exists else null.
| Metric | Definition |
|---|---|
| `net_pnl_total`, `charges_total`, `cost_drag` | `Σ net`, `Σ charges`, `Σ charges / Σ max(gross,0)` |
| `win_rate`, `expectancy_inr`, `profit_factor`, `payoff` | as above on `net_pnl` |
| `equity_curve` | equity marked at each snapshot (bid-based) and at fills; starting equity from the risk profile |
| `max_drawdown_inr`, `max_drawdown_pct` | peak-to-trough on the equity curve |
| `daily_returns` | `(equity_close_d / equity_close_{d−1}) − 1` |
| `sharpe_daily` | `mean(daily_returns)/std(daily_returns, ddof=1) × √252` — reported **only if ≥ 60 trading days with trades**, else null with note `INSUFFICIENT_DAYS`; risk-free 0 |
| `exposure_time` | fraction of session minutes in position |
| `by_day`, `by_expiry_weekday`, `by_schema_version` | splits |
### 8.10.3 Uncertainty (mandatory with every headline expectancy)
Day-block bootstrap (resample **sessions with replacement**, `B = 10,000`, seed from manifest): for each resample, concatenate that day's trades and compute mean net P&L per trade. Report the 2.5th/97.5th percentiles (`ci95`) and `p_value_one_sided = fraction of resamples with mean ≤ 0`. Also report `n_trials_so_far` and `p_adj = min(1, p × n_trials)`. A strategy is labelled **"not distinguishable from zero"** if `ci95` contains 0.
### 8.10.4 Sensitivity tables (mandatory)
Mode B: `{fill model} × {slippage_points 0,1,2,3}` → expectancy and net points; hurdle table. Mode C: `slippage_ticks ∈ {0,1,2,4}` × `latency_s ∈ {2,5,15,30}` → net P&L and expectancy. A result that is positive only at the most optimistic cell is flagged `FRAGILE`.

### 8.10.5 [v1.2] Metric detail contract — click-to-explain (ADR-034) — status: DESIGNED
Every metric is produced by a backend function returning `MetricResult(value, detail)`. The *same* function computes the value and captures the intermediates, so the explanation cannot drift from the number. Formula text/TeX and variable definitions are attached to the function by a `@metric(id=…, formula_text=…, formula_tex=…, variables=…)` decorator. The frontend renders `MetricDetail`; it never computes a trading metric.
```python
class MetricDetail(BaseModel):
    metric_id: str                       # "<result_kind>.<name>", e.g. "ACTUAL_OPTIONS.profit_factor"
    label: str; result_kind: ResultKind; unit: Literal["points","paise","ratio","percent","count","days","none"]
    value: float | int | None
    status: Literal["OK","NULL_INSUFFICIENT_DATA","NULL_UNDEFINED","INCOMPLETE"]; null_reason: str | None
    formula_text: str; formula_tex: str
    variables: list[{symbol: str, meaning: str, unit: str}]
    inputs: dict[str, float | int | str | ArtifactRef]    # the actual intermediates (Σ wins, Σ losses, n, mean, std, …)
    substitution: str                    # the formula with the numbers substituted, produced by the backend
    period: {start: date, end: date, sessions: int, trades_included: int, trades_excluded: dict[str, int]}
    aggregation: str                     # e.g. "sum over CLOSED trades of per-trade net P&L after charges"
    treatment: {breakeven: str, open_positions: str, unresolved: str, incomplete: str}
    annualization: {factor: float, convention: str, applied: bool} | None
    assumptions: list[str]; limitations: list[str]
    trade_filter: {run_id: str, predicate: str} | None    # opens the trade table pre-filtered ("wins", "losses", "excluded:UNRESOLVED")
    definition_version: str              # semver of the metric definition; recorded in the RunManifest
    verified_by_recompute: bool          # an independent evaluator re-derived `value` from `inputs` at report build
```
**Kind separation.** Metric ids are namespaced by `result_kind`; the API refuses to return a detail whose kind differs from the run's, and the UI refuses to render a mismatched one. Mode B (points), Mode C (₹), Mode S (labelled), PAPER and LIVE never share a metric id or an aggregate.
**Clarifications of v1.1 definitions (no number changes).** `daily_returns` are computed over **all included sessions of the run** (flat days contribute 0); the `≥ 60 trading days with trades` rule gates whether Sharpe/Sortino are reported. Breakeven (`net_pnl = 0`) counts in `n_trades`, in the denominator of `win_rate` and in `expectancy`, but is neither a win nor a loss for `avg_win`, `avg_loss` or `profit_factor`. A trade still open at the end of a run (OVERNIGHT at the range end) is excluded from realised metrics, marked to bid in equity and listed `OPEN_AT_END`. `UNRESOLVED` trades are excluded and bounded (§8.4.8 e).
**Added definition — `sortino_daily`** (Mode C / PAPER): `mean(r_d) / DD × √252`, `DD = sqrt( (1/N) Σ_d min(r_d − MAR, 0)² )`, `MAR = 0`, `N` = number of included sessions; null with `INSUFFICIENT_DAYS` under 60 days with trades or `NULL_UNDEFINED` when `DD = 0`. Mode B reports no Sharpe/Sortino (it has no equity curve).
**Endpoints** (§12.2.1): `GET /backtests/{run_id}/metrics` (list: id, value, unit, status) and `/metrics/{metric_id}` (`MetricDetail`). Per-metric catalogue and panel behaviour: `BACKTESTING_REPORT_SPEC.md` §3–§4.
Tests: T-MI-1 clicking any listed metric returns formula, variables, inputs, period, treatment, annualization (where applicable), assumptions and trade links; T-MI-2 an independent per-metric evaluator re-derives `value` from `inputs` for every metric of a fixture run; T-MI-3 catalogue ids in `BACKTESTING_REPORT_SPEC.md` ≡ ids the backend exposes; T-MI-4 kind mismatch is refused by API and UI; T-MI-5 breakeven/open/unresolved treatment fixtures; T-MI-6 frontend contains no metric arithmetic (lint rule forbids `reduce`/`Math.sqrt` on trade arrays under `features/backtests`).

## 8.11 Walk-forward, holdout, trial accounting
- **Parameter selection (rule-based strategies).** Walk-forward: in-sample 12 months, out-of-sample 3 months, step 3 months, starting at the first full quarter of data; choose parameters on in-sample by the pre-declared objective (`expectancy_points` for Mode B; `expectancy_inr` for Mode C), report only the concatenated out-of-sample results. **[v1.2] Purge:** trades whose entry lies in an in-sample window but whose exit reaches the out-of-sample start are removed from in-sample; OVERNIGHT strategies add an embargo of the maximum `sessions_held` (§11.7.1).
- **Holdout registry** (`holdouts` table: `id, mode, start, end, frozen_at, data_hash`). Mode B default holdout: **2026-01-01 → latest available at freeze time** **(ADR-015 proposed)**. Mode C holdout: the final contiguous block holding ≥ 20% of eligible sessions **and** ≥ 25 sessions **and** at least one full monthly-expiry cycle, chosen *after* the coverage review and frozen **before any Mode C tuning**. `scripts/freeze_holdout.py` writes the registry row once; later runs with `purpose="holdout"` may execute only once per strategy version; the engine refuses `purpose in {"exploration","tuning"}` runs whose date range intersects a frozen holdout.
- **Trial accounting.** Every run with `purpose in {"exploration","tuning"}` increments the strategy family's `n_trials`. Reports always show it. **[v1.2]** Failed/aborted runs and every new strategy version in the family also count (§11.7.1).

## 8.12 Option-aware hurdle and Mode S (synthetic estimate)
### 8.12.1 Break-even hurdle (from Mode C data)
For an ATM long option held `h` minutes, with observed `spread_abs`, `|delta|`, `theta` (₹ per unit per day `[VERIFY units — S12]`), charges `C_rt` (round trip, ₹) and quantity `q`:
```
hurdle_points(h) = [ spread_abs + 2·slippage_ticks·tick + C_rt/q + |theta|·(h/375) ] / |delta|
```
Report median and p90 of `hurdle_points(h)` over ATM snapshots for `h ∈ {5, 15, 30, 60}` and compare Mode B expectancy against it. The hurdle is an estimate and is **never** added to Mode B P&L.

### 8.12.2 Mode S estimator (labelled scenario analysis only)
Black–Scholes European price, no dividends:
```
T  = t_expiry_years (§5.4.5);  d1 = (ln(S/K) + (r + σ²/2)·T) / (σ·√T);  d2 = d1 − σ·√T
Call = S·N(d1) − K·e^{−rT}·N(d2);   Put = K·e^{−rT}·N(−d2) − S·N(−d1)
```
`r = 0.065` **[OWNER]**; strike by the same selection policy using the model chain (ATM/offset only; no delta policy); `σ` source: observed `iv_atm` as-of when available (Greeks from 2026-02-12), else `σ = k × realized_vol_20(daily)` with `k = median(iv_atm / realized_vol_20)` fitted on the overlap window. Model quotes: `mid = model price`, `bid = mid × (1 − 0.5·s)`, `ask = mid × (1 + 0.5·s)`, `s = 0.02` **[OWNER]**; fills use the same Mode C rules on model quotes. Output type `SYNTHETIC_ESTIMATE` — never combined with Mode C results.
**Calibration (ADR-016):** before running, write `config/modeS_calibration.yaml` containing the metrics and acceptance thresholds for the intended use, hash it, and record the hash in the manifest. Run the same strategy and period in Mode C and Mode S on the overlap window and report: per-trade P&L error (MAE ₹, median absolute % error), Spearman rank correlation of trade P&Ls, sign agreement rate, and difference in total net P&L. Mode S results outside the overlap window carry the calibration verdict (`PASS/FAIL against pre-registered thresholds`) in every report header.

### 8.12.3 [v1.1] Overnight hurdle
For an OVERNIGHT trade held `n` calendar days (weekend/holiday carries count every calendar day), with observed `spread_abs`, `|delta|`, `theta` (₹ per unit per calendar day `[VERIFY units — S12]`), round-trip charges `C_rt`, quantity `q`:
```
hurdle_points_overnight(n) = [ spread_abs + 2·slippage_ticks·tick + C_rt/q + |theta|·n ] / |delta|
```
Reported (median and p90 over entry-time ATM snapshots, Greeks era only) next to the Mode B `gap_points` and `session_points` distributions. It excludes overnight IV change and event gaps, which cannot be estimated from index candles; the report states this. Like §8.12.1 it is never added to Mode B P&L.


## 8.13 Report artifacts
Written to `data/runs/<run_id>/`: `manifest.json`, `summary.json` (discriminated by `result_kind`), `trades.parquet`, `equity.parquet`, `decisions.parquet` (every decision incl. NO_ACTION reasons), `rejections.parquet`, `annotations.parquet`, `coverage.json`, `sensitivity.json`, `bootstrap.json`. The API serves these; the UI renders them.

## 8.14 Simulation and risk tests
| ID | Test |
|---|---|
| T-SIM-1 | Poisoned-future: replace all data after `t` with NaN → decisions up to `t` unchanged |
| T-SIM-2 | Lookahead guard: a deliberately peeking feature raises `LookAheadError` |
| T-SIM-3 | Determinism: same manifest ⇒ same `result_hash` (run twice, plus once in a fresh process) |
| T-SIM-4 | Mode B stop/target rules: table-driven bars covering gap-through-stop, both-touched (stop wins, `ambiguous=true`), target only, trailing move, `NEXT_OPEN` vs `NEXT_CLOSE` entry-bar handling |
| T-SIM-5 | Mode C fills: entry at first snapshot ≥ `created_at + latency`, ask + 1 tick; exit at bid − 1 tick; wait window exceeded ⇒ `EXPIRED` |
| T-SIM-6 | PREMIUM stop detected at snapshot k fills at snapshot k+1 bid |
| T-SIM-7 | End-of-session fallbacks (`LATE_EXIT`, `STALE_EXIT`, `UNRESOLVED`) |
| T-SIM-8 | Event ordering: equal `available_at` events apply by priority then `seq` |
| T-SIM-9 | Holdout guard refuses tuning runs overlapping a frozen holdout |
| T-SIM-10 | Replay parity: record a paper day, replay through the engine with the paper fill model, compare order intents (identical) and fills (identical given same quotes) |
| T-COST-1 | Worked example §8.5.3 reproduced to the paisa |
| T-COST-2 | STT regime boundaries (2024-10-01, 2026-04-01) switch rates on the trade date |
| T-RK-1…21 | One boundary test per rule (just inside / just outside) plus exit-exemption test |
| T-RK-22 | **[v1.1]** Layering: `effective = min(strategy, account)` for every CEILING; a strategy value above the ceiling never raises it |
| T-RK-23 | **[v1.1]** Clamp: a strategy asking for 8% on a 5% ceiling is sized at 5% and flagged `RISK_CLAMPED` with `{requested, effective}` |
| T-RK-24 | **[v1.1]** `RESEARCH_RELAXED`: ceilings counted as `would_reject` but not enforced; HARD rules still reject; refused for `purpose=holdout` and for paper accounts |
| T-RK-25 | **[v1.1]** Profile validation errors/warnings of §8.6.6, including `ACCOUNT_BELOW_ONE_LOT` |
| T-RK-26 | **[v1.1]** Sizing: 0 lots ⇒ `RISK_BELOW_ONE_LOT` under `REJECT`; `ONE_LOT` yields 1 lot that RK-07/RK-08 may still reject; same strategy sized correctly at equities of ₹20k, ₹1 lakh, ₹20 lakh |
| T-SIM-11 | **[v1.1]** Mode B overnight: entry at 15:25 bar, exit at next 09:15 open; Friday→Monday is one session offset; gap through stop exits at the open; `gap_points + session_points = pnl_points` |
| T-SIM-12 | **[v1.1]** Mode B overnight on a session with missing 15:29 bar: skipped unless `allow_degraded_close`; missing exit session ⇒ `UNRESOLVED_OVERNIGHT` |
| T-SIM-13 | **[v1.1]** Mode C overnight: exit fill within 600 s of 09:15; else `LATE_OPEN_EXIT` until 10:30; else `UNRESOLVED_OVERNIGHT`; `INCOMPLETE` above 10% unresolved |
| T-SIM-14 | **[v1.1]** Overnight positions: ledger carries them, `OVERNIGHT_MARK` is not `STALE`, RK-11 base equals previous end-of-day equity |
| T-OS-1 | Order state machine: every legal transition accepted, every illegal one raises; duplicate `event_id` ignored; late event after terminal state stored without state change |
| T-PP-1 | Paper restart: kill the runner mid-position, restart, no duplicate order, ledger verify OK |

## 8.15 [v1.2] Execution-semantics difference register — status: DESIGNED
Strategy code is identical across environments (P4); what the *world* does around it is not. This register is the single place that lists the differences, so a backtest, a paper result and a (future) live result are never read as the same experiment.
| Aspect | Mode B | Mode C | Paper | Live (Phase 9) |
|---|---|---|---|---|
| Decision time | strategy-bar close | strategy-bar close | strategy-bar close, wall clock | same |
| Price source | spot 1m open/close | bid/ask from 30 s snapshots (or recorded quotes, §8.4.8) | live recorded quotes, 5-level depth | broker fills |
| Latency | 0 s / ≈ 60 s variants | 2 s (`latency_s`) | 500 ms (`latency_ms`) | measured |
| Stop detection | 1m bars, path-blind | UNDERLYING: 1m bar close; PREMIUM: snapshot bid | UNDERLYING: 1m bar close; PREMIUM: every quote | broker + local |
| Partial fills | none | top-of-book flag only | depth walk | broker |
| Charges | none (points) | cost model | cost model | broker contract note |
| Between-observation path | unknown | unknown (≥ 30 s blind) | recorded | real |
| Look-ahead guard | `available_at` + truncate-recompute | same | wall clock | same |
| Result kind | `UNDERLYING_DIRECTIONAL` | `ACTUAL_OPTIONS` | `PAPER` | `LIVE` |
Parity checks that make the register trustworthy: T-SIM-10 replay parity (order intents identical); the Pine porting protocol (§6.9) for repainting and look-ahead; the repaint rule (§5.1.9); truncate-and-recompute for every feature (§5.1.7). A report must never state that paper results "confirm" a backtest unless the differences above are reported next to the comparison.


---

# 9. Ledger and accounting (`quantview.ledger`)

## 9.1 Principles
Append-only events; double-entry journal; balances and positions are **projections** rebuildable from events; integer paise; a signal never changes cash or positions; an unfilled order is not a trade; corrections are reversal events, never edits.

## 9.2 Chart of accounts (per paper/live account)
| Ledger account | Normal side | Meaning |
|---|---|---|
| `ASSET:CASH` | debit | Cash balance |
| `ASSET:OPTIONS_AT_COST` | debit | Cost basis of open option positions |
| `EQUITY:CAPITAL` | credit | Capital introduced |
| `INCOME:REALIZED_PNL` | credit | Realised gross profit (credit) / loss (debit) |
| `EXPENSE:BROKERAGE`, `EXPENSE:STT`, `EXPENSE:EXCHANGE_TXN`, `EXPENSE:SEBI`, `EXPENSE:IPFT`, `EXPENSE:STAMP`, `EXPENSE:GST` | debit | Charges |
Every journal entry satisfies `Σ debit_paise = Σ credit_paise`.

## 9.3 Posting rules (exact)
Notation: `q` units, `p` price in paise per unit (integer; option prices are multiples of 5 paise), `cost = q × p` (exact integer).
| Event | Journal |
|---|---|
| `ACCOUNT_OPENED(C)` | Dr CASH C · Cr CAPITAL C |
| `FILL_BUY(q, p)` | Dr OPTIONS_AT_COST `q×p` · Cr CASH `q×p` |
| `FILL_SELL(q_c, p)` (closes `q_c` of position with total qty `Q`, total cost `K`) | `released = K` if `q_c = Q` else `round_half_up(K × q_c / Q)` using integer/`Fraction` arithmetic; `proceeds = q_c × p`; Dr CASH `proceeds` · Cr OPTIONS_AT_COST `released` · and `proceeds − released > 0` ⇒ Cr REALIZED_PNL that amount, `< 0` ⇒ Dr REALIZED_PNL the absolute amount |
| `CHARGES(fill)` (same event as the fill) | For each component `c` with amount `a_c > 0`: Dr `EXPENSE:c` · Cr CASH |
| `REVERSAL(event_id)` | Opposite journal of the referenced event; links `reverses_event_id` |
| `MARK(instrument, bid_paise, ts)` | **No journal**; stored in `marks` for audit and unrealised P&L |
Short positions are impossible (RK-01); a SELL larger than the open quantity raises `InvariantViolationError`.

## 9.3.1 [v1.2] Additional ledger events — status: DESIGNED
History is never mutated. Beyond `REVERSAL` (§9.3):
| Event | Journal | Notes |
|---|---|---|
| `CHARGE_ADJUSTMENT(fill_id, component, delta_paise, reason)` | `delta > 0`: Dr `EXPENSE:<c>` · Cr CASH; `delta < 0`: Dr CASH · Cr `EXPENSE:<c>` | Broker charge corrections/refunds. The fill's recorded `charges_paise` is never edited; links `adjusts_fill_id` |
| `FILL_CORRECTION` | `REVERSAL` of the fill's event + a new fill event with `corrects_fill_id` | One atomic transaction (`Ledger.post_correction`); positions rebuilt from events |
| `CANCELLATION` | none | Order event only; a cancelled order has no ledger effect |
| `INSTRUMENT_MIGRATION(old_id, new_id, qty, cost)` | closes at cost basis on the old key and opens at the same cost on the new key; zero P&L | Only through an owner-approved command; positions are never silently re-keyed (not expected for NIFTY index options; kept for completeness) |
| `EXPIRY_SETTLEMENT(instrument_id, settlement_px_paise)` | like `FILL_SELL` at the owner-supplied official settlement value `[VERIFY]` | v1 forbids carrying through expiry (§7.2 2a, force-flat), so this exists only as an audited recovery command if a feed outage strands a position |
**Instrument rules at the time of the fill.** Each fill stores `lot_size`, `tick_paise` and an `instrument_snapshot` (`expiry`, `strike`, `option_type`, `underlying`, `calendar_version`) so a later lot-size or tick change never reinterprets a historical quantity. Positions are in **units**. If a calendar update moves an open position's expiry date, the runner raises `EXPIRY_RULE_CHANGED` and does not reinterpret the position.
**Rebuild and reconcile.** `Ledger.rebuild(account_id)` (projection from events) must equal the live projection (T-LG-6); per-account reconciliation compares projection to broker in Phase 9 and to owner contract notes for fee checks (T7.5). Restore/power-loss procedures are in §14.3.1.

## 9.4 Derived quantities
```
position_qty(i), position_cost(i)               from fills replay
unrealized(i) = qty × mark_bid_paise − cost      (mark = latest bid with available_at ≤ now; stale > limit ⇒ unrealized marked STALE and excluded from equity)
equity = cash + Σ qty × mark_bid_paise
realized_net = Σ INCOME:REALIZED_PNL − Σ EXPENSES
IDENTITY: equity − capital = realized_net + Σ unrealized          (checked by verify())
```
**[v1.1] Overnight positions.** Positions persist across `session_date`. At each session end the ledger stores an `EOD_MARK` per open position (the last valid bid of that session; stored in `marks`, no journal). Until the first valid quote of the next session the position is marked at that `EOD_MARK` with flag `OVERNIGHT_MARK`; this is **not** `STALE`, so unrealised P&L stays in equity and `start_of_day_equity = previous end-of-day equity`. A gap loss at the open therefore counts against the new day's RK-11 limit. A position carried past its exit session without a mark ≥ one valid quote raises an alert.

## 9.5 Postgres schema (normative DDL)
```sql
CREATE TABLE accounts (                                               -- [v1.2] kind, name, status, composite key for mode validation
  account_id text PRIMARY KEY,
  mode text NOT NULL CHECK (mode IN ('BACKTEST','PAPER','LIVE')),
  account_kind text NOT NULL CHECK (account_kind IN ('STRATEGY','MANUAL')),
  name text NOT NULL, status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ARCHIVED')),
  currency text NOT NULL DEFAULT 'INR', created_at timestamptz NOT NULL,
  risk_profile_ref text NOT NULL,                                     -- id@version
  config jsonb NOT NULL,
  UNIQUE (account_id, mode),                                          -- target of the (account_id, account_mode) foreign keys below
  CHECK (NOT (account_kind = 'MANUAL' AND mode <> 'PAPER')));         -- v1: no manual live, no manual backtest
CREATE UNIQUE INDEX one_active_manual_account ON accounts ((1)) WHERE account_kind = 'MANUAL' AND mode = 'PAPER' AND status = 'ACTIVE';

CREATE TABLE ledger_events (
  seq bigserial UNIQUE, event_id text PRIMARY KEY,
  account_id text NOT NULL, account_mode text NOT NULL,               -- [v1.2] mode recorded and validated on every ledger event
  event_type text NOT NULL, occurred_at timestamptz NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now(),
  correlation_id text NOT NULL, causation_id text, idempotency_key text NOT NULL UNIQUE,
  reverses_event_id text REFERENCES ledger_events(event_id), adjusts_fill_id text, corrects_fill_id text,
  payload jsonb NOT NULL,                                             -- includes origin (MANUAL | STRATEGY) for fill events
  FOREIGN KEY (account_id, account_mode) REFERENCES accounts (account_id, mode));

CREATE TABLE journal_lines (
  line_id bigserial PRIMARY KEY, event_id text NOT NULL REFERENCES ledger_events,
  ledger_account text NOT NULL, debit_paise bigint NOT NULL DEFAULT 0, credit_paise bigint NOT NULL DEFAULT 0,
  CHECK (debit_paise >= 0 AND credit_paise >= 0 AND (debit_paise = 0 OR credit_paise = 0)));

-- append-only enforcement
CREATE FUNCTION forbid_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'append-only table'; END $$ LANGUAGE plpgsql;
CREATE TRIGGER t_events_ro BEFORE UPDATE OR DELETE ON ledger_events FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER t_lines_ro  BEFORE UPDATE OR DELETE ON journal_lines FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

CREATE TABLE orders (                                                 -- [v1.2] origin, deployment link, supported order types, event timestamps
  order_id text PRIMARY KEY,
  account_id text NOT NULL, account_mode text NOT NULL,
  origin text NOT NULL CHECK (origin IN ('MANUAL','STRATEGY')),
  intent_id text NOT NULL,
  decision_id text REFERENCES decisions,                              -- NULL for MANUAL and for engine-owned exits
  deployment_id text REFERENCES deployments,                          -- NULL for MANUAL; (BACKTEST ledgers omit these two FKs)
  strategy_id text, strategy_version int, spec_hash text, run_id text, mode text NOT NULL,
  instrument_id text NOT NULL, side text NOT NULL CHECK (side IN ('BUY','SELL')), qty_units int NOT NULL CHECK (qty_units > 0),
  order_type text NOT NULL DEFAULT 'MARKET' CHECK (order_type IN ('MARKET','LIMIT')),   -- exactly what the simulator implements
  limit_price_paise bigint CHECK (limit_price_paise > 0 AND limit_price_paise % 5 = 0),
  validity text NOT NULL DEFAULT 'DAY' CHECK (validity IN ('DAY')),
  state text NOT NULL,
  signal_at timestamptz,                                              -- decision_at of the originating Decision (NULL for MANUAL)
  created_at timestamptz NOT NULL,                                    -- order/intent created
  accepted_at timestamptz,                                            -- time of the ACK (OPEN) order event
  earliest_fill timestamptz,
  underlying_ref_px numeric(12,2),                                    -- index level when created: a CHART ANCHOR, not a price of this order
  risk_basis text CHECK (risk_basis IN ('PLANNED_PREMIUM_STOP','WORST_CASE_OUTLAY')), risk_amount_paise bigint,
  exit_reason text, supersedes_order_id text, calendar_version text,
  idempotency_key text NOT NULL UNIQUE, simulated boolean NOT NULL, fill_model text,
  FOREIGN KEY (account_id, account_mode) REFERENCES accounts (account_id, mode),
  CONSTRAINT origin_shape CHECK (
       (origin = 'STRATEGY' AND strategy_id IS NOT NULL AND (deployment_id IS NOT NULL OR mode = 'BACKTEST')
                            AND (side = 'SELL' OR decision_id IS NOT NULL OR mode = 'BACKTEST'))
    OR (origin = 'MANUAL'   AND decision_id IS NULL AND deployment_id IS NULL AND strategy_id IS NULL AND mode = 'PAPER')));

CREATE TABLE order_events (
  event_id text PRIMARY KEY, order_id text NOT NULL REFERENCES orders, seq bigserial,
  event_type text NOT NULL, from_state text, to_state text, occurred_at timestamptz NOT NULL, payload jsonb NOT NULL);

CREATE TABLE fills (                                                  -- [v1.2] account mode + origin, instrument rules at fill time, fill source
  fill_id text PRIMARY KEY, order_id text NOT NULL REFERENCES orders, fill_seq int NOT NULL,
  account_id text NOT NULL, account_mode text NOT NULL, origin text NOT NULL CHECK (origin IN ('MANUAL','STRATEGY')),
  qty_units int NOT NULL CHECK (qty_units > 0), price_paise bigint NOT NULL CHECK (price_paise > 0),
  lot_size int NOT NULL, tick_paise int NOT NULL, instrument_snapshot jsonb NOT NULL,
  fill_source text NOT NULL CHECK (fill_source IN ('SNAPSHOT','QUOTE')),
  underlying_ref_px numeric(12,2),                                    -- chart anchor only
  filled_at timestamptz NOT NULL, simulated boolean NOT NULL, source_ref jsonb NOT NULL,   -- snapshot_id / quote ts / broker trade id
  charges_paise jsonb NOT NULL, cost_model_version text, corrects_fill_id text, idempotency_key text NOT NULL UNIQUE,
  FOREIGN KEY (account_id, account_mode) REFERENCES accounts (account_id, mode),
  UNIQUE (order_id, fill_seq));

CREATE TABLE positions (               -- projection, rebuilt by Ledger.rebuild()
  account_id text NOT NULL, instrument_id text NOT NULL, qty_units int NOT NULL CHECK (qty_units >= 0),
  cost_paise bigint NOT NULL CHECK (cost_paise >= 0), opened_at timestamptz, updated_at timestamptz NOT NULL,
  PRIMARY KEY (account_id, instrument_id));

CREATE TABLE marks (account_id text, instrument_id text, ts timestamptz, bid_paise bigint, source text, PRIMARY KEY (account_id, instrument_id, ts));
```
Supporting state tables (columns specified in the ticket that creates them): `strategies`, `strategy_versions(strategy_id, version, spec jsonb, spec_hash, created_at)`, `runs(run_id, manifest jsonb, summary jsonb, status)`, [v1.2: `deployments`, `decisions`, `deployment_events`, `order_commands`, `outbox`, `consumer_checkpoints`, `viz_preferences` are defined in §9.5.1 and §2.7.4], `holdouts`, `experiments`, `audit_events(event_id, actor, action, payload, at)`, `kill_switch(scope, enabled, changed_at, reason)`.
Migrations with Alembic only; the first migration creates exactly the tables above.

### 9.5.1 [v1.2] Schema layout, triggers and new tables — status: DESIGNED
**Schemas (ADR-027, §10.5).** `qv_paper` holds `accounts, ledger_events, journal_lines, orders, order_events, fills, positions, marks, decisions, deployments, deployment_events, order_commands, outbox, consumer_checkpoints`. `qv_core` holds `strategies, strategy_versions, runs, holdouts, ml_experiments, ml_holdout_looks, audit_events, kill_switch, risk_profiles, viz_preferences`. `qv_live` gets the same DDL as `qv_paper` **only** by the Phase 9 migration. The DDL in §9.5 applies to PAPER/LIVE schemas; a BACKTEST ledger uses the same tables without the `decisions`/`deployments` foreign keys (`ddl.for_backtest()`).
**Triggers (raise on violation).** `orders_kind_guard`: `origin='MANUAL'` requires `accounts.account_kind='MANUAL'` and `origin='STRATEGY'` requires `'STRATEGY'`; `fills_match_order`: `fills.account_id/account_mode/origin` equal the parent order's; `schema_mode_guard`: in `qv_paper` every `account_mode` must be `'PAPER'` (and `'LIVE'` in `qv_live`); `deployments_kind_guard`: a deployment's account must be `STRATEGY` kind; append-only triggers (as §9.5) on `deployment_events`, `order_events`, `outbox`.
```sql
CREATE TABLE decisions (
  decision_id text PRIMARY KEY, deployment_id text NOT NULL REFERENCES deployments,
  strategy_id text NOT NULL, strategy_version int NOT NULL, spec_hash text NOT NULL,
  timeframe text NOT NULL, bar_start timestamptz NOT NULL, decision_at timestamptz NOT NULL,   -- decision_at = signal time
  action text NOT NULL, direction text, exit_reason text, reasons jsonb NOT NULL,
  feature_snapshot jsonb NOT NULL, feature_versions jsonb NOT NULL,
  underlying_ref_px numeric(12,2), idempotency_key text NOT NULL UNIQUE, created_at timestamptz NOT NULL);

CREATE TABLE deployments (                    -- supersedes the v1.1 one-line sketch; checkpoint now lives in consumer_checkpoints
  deployment_id text PRIMARY KEY,
  account_id text NOT NULL, account_mode text NOT NULL CHECK (account_mode = 'PAPER'),
  strategy_id text NOT NULL, strategy_version int NOT NULL, spec_hash text NOT NULL, params jsonb NOT NULL,
  feature_pins jsonb NOT NULL, risk_profile_ref text NOT NULL, config_snapshot jsonb NOT NULL,
  state text NOT NULL CHECK (state IN ('CREATED','STARTING','RUNNING','PAUSED_USER','PAUSED_AUTO','DRAINING','STOPPED','ERROR')),
  stop_policy text CHECK (stop_policy IN ('DRAIN','FLATTEN')), auto_resume boolean NOT NULL DEFAULT false, last_error jsonb,
  created_at timestamptz NOT NULL, started_at timestamptz, stopped_at timestamptz,
  FOREIGN KEY (account_id, account_mode) REFERENCES accounts (account_id, mode));
CREATE UNIQUE INDEX one_open_deployment_per_account ON deployments (account_id)
  WHERE state IN ('STARTING','RUNNING','PAUSED_USER','PAUSED_AUTO','DRAINING','ERROR');

CREATE TABLE deployment_events (              -- append-only
  deployment_id text NOT NULL REFERENCES deployments, seq int NOT NULL, event_type text NOT NULL,
  from_state text, to_state text, actor text NOT NULL CHECK (actor IN ('OWNER','RUNNER','HEALTH_GATE')),
  reason text, payload jsonb NOT NULL, at timestamptz NOT NULL, PRIMARY KEY (deployment_id, seq));

CREATE TABLE order_commands (                 -- the only table the API role may INSERT into on the trading side
  command_id text PRIMARY KEY, client_order_id text NOT NULL UNIQUE, account_id text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('PLACE','CANCEL','EXIT')), payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED','ACCEPTED','REJECTED','EXPIRED')),
  reject_code text, order_id text, created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL, handled_at timestamptz);

CREATE TABLE outbox (                         -- §2.7.5, written in the same transaction as the state change
  seq bigserial PRIMARY KEY, stream text NOT NULL, event_id text NOT NULL UNIQUE, event_type text NOT NULL,
  payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX outbox_stream_seq ON outbox (stream, seq);

-- qv_core
CREATE TABLE viz_preferences (                -- UI-only state; the sole table the visualization endpoints may write
  deployment_id text PRIMARY KEY,             -- plain text key, no foreign key into the trading schema
  visible boolean NOT NULL DEFAULT false,     -- master switch
  markers boolean NOT NULL DEFAULT true, indicators boolean NOT NULL DEFAULT true, levels boolean NOT NULL DEFAULT true,
  hidden_series jsonb NOT NULL DEFAULT '[]', filters jsonb NOT NULL DEFAULT '{}',
  color_slot int NOT NULL, updated_at timestamptz NOT NULL DEFAULT now());
```
`consumer_checkpoints` is defined in §2.7.4. `strategy_versions` (§9.5) additionally stores `edit_source ∈ {MANUAL, AI_ASSISTED, PARAM_SWEEP}` and `parent_version` (used for trial accounting, §8.11). Backtest result artifacts (trades, equity, `metrics_detail.json`, coverage, eligibility) stay in `data/runs/<run_id>/` Parquet/JSON, referenced from `runs.summary`.

## 9.6 Service API
```python
class Ledger:
    def open_account(self, account_id: str, capital_paise: int, mode: str) -> None
    def post_fill(self, fill: Fill, charges: ChargeBreakdown) -> LedgerEventId         # one atomic DB transaction: fill row + ledger event + journal lines + position projection
    def post_reversal(self, event_id: str, reason: str) -> LedgerEventId
    def post_charge_adjustment(self, fill_id: str, component: str, delta_paise: int, reason: str) -> LedgerEventId   # [v1.2] §9.3.1
    def post_correction(self, fill_id: str, corrected: Fill, charges: ChargeBreakdown, reason: str) -> LedgerEventId  # [v1.2] reversal + new fill, atomic
    def record_mark(self, instrument_id: str, bid_paise: int, ts: datetime) -> None
    def balance(self, account_id) -> int;  def position(self, account_id, instrument_id) -> PositionView
    def equity(self, account_id, marks: Mapping[str,int]) -> EquityView
    def verify(self, account_id) -> VerifyReport                                       # §9.7
    def rebuild(self, account_id) -> None                                              # recompute projections from events
```
`post_fill` is idempotent on `fill.idempotency_key` (second call returns the original event id, writes nothing).

## 9.7 `verify()` checks (all must pass; run after every fill in paper/live and at every EOD)
1. Every event's journal balances. 2. Cash projection = `Σ(CASH debits − credits)`. 3. Positions projection = replay of fills (`qty`, `cost`). 4. No duplicate fill/idempotency keys. 5. No negative position. 6. Equity identity (§9.4) within 0 paise using non-stale marks. 7. Each fill has charges recorded when a cost model is configured. A failure sets `RK-16` (account uncertain) and trips the kill switch.

## 9.8 Ledger tests
| ID | Test |
|---|---|
| T-LG-1 | Buy then sell: journals, cash, realised P&L equal hand-computed values (use the §8.5.3 example: cash change = ₹1,300.00 − ₹65.44) |
| T-LG-2 | Partial entry and partial exit: proportional cost release with remainder exactness on the final close |
| T-LG-3 | Duplicate fill delivery ignored (idempotent) |
| T-LG-4 | Reversal restores prior balances; original events untouched |
| T-LG-5 | Property test (hypothesis): random valid fill sequences keep `verify()` green and `Σ debit = Σ credit` |
| T-LG-6 | Rebuild equals live projection |
| T-LG-7 | UPDATE/DELETE on `ledger_events`/`journal_lines` raise |
| T-LG-8 | SELL beyond open quantity raises `InvariantViolationError` |
| T-LG-9 | Stale mark excluded from equity and flagged |
| T-LG-10 | **[v1.1]** Overnight carry: `EOD_MARK` stored, equity continuous across the session boundary, next-day realised P&L correct, `verify()` green |
| T-LG-11 | **[v1.2]** `CHARGE_ADJUSTMENT` posts and leaves the original fill/charges untouched; `verify()` green |
| T-LG-12 | **[v1.2]** `FILL_CORRECTION` is reversal + new fill in one transaction; rebuild equals projection |
| T-LG-13 | **[v1.2]** Lot size/tick stored per fill: a later rules change does not alter historical quantity or cost |

---

# 10. Execution (`quantview.execution`)

## 10.1 Common contract
```python
class AdapterCapabilities(BaseModel):
    supports_cancel: bool; supports_modify: bool; supports_depth: bool; simulated: bool

class ExecutionAdapter(Protocol):
    capabilities: AdapterCapabilities
    def submit(self, order: Order) -> SubmitResult                 # may raise ExternalOutcomeUnknownError (live only)
    def cancel(self, order_id: str) -> CancelResult
    def status(self, order_id: str) -> OrderStatus
    def open_orders(self) -> list[OrderStatus]
    def fills_since(self, cursor: str | None) -> tuple[list[Fill], str]
    def positions(self) -> list[PositionView]
    def funds(self) -> FundsView
```
Adapters emit order events; **the runner** (not the adapter) posts fills to the ledger, so adapters never import `ledger`.

## 10.2 Paper adapter (`paper_adapter.py`)
Wraps a `FillModel`. `submit` creates the local order, emits `ACK`, schedules fill evaluation per the model (§8.4.2 / §8.8), emits `PARTIAL_FILL`/`FILL`/`EXPIRE`. Idempotent on `order.idempotency_key`. Labels fills `simulated=true`. Contains **no** import from `upstox_client` or `execution.upstox`.

## 10.3 Upstox adapter (Phase 9 only; do not start before the gate)
Hard requirements (details verified against current Upstox docs at that time `[VERIFY]`):
1. Disabled unless `QV_LIVE_ENABLED=1` **and** `config/live/readiness_signed.yaml` exists with owner signature, date and checklist hash **[v1.2] and the per-session arming command (three locks, §10.5)**.
2. Separate credentials/profile; never reachable from the paper process.
3. **Persist before submit:** write the order (`APPROVED→SUBMITTED`) to Postgres, then call the broker. Use a client tag/idempotency identifier unique per order `[VERIFY]`.
4. Timeout or ambiguous response ⇒ `UNKNOWN` state, **no resubmission** until the order is found or confirmed absent via the broker's order book/trade book.
5. Reconcile every 5 s while orders are open and every 60 s otherwise: broker orders, trades, positions, funds vs local; any mismatch not explained by in-flight events ⇒ kill switch + alert. Broker records are authoritative for actual fills and charges.
6. Respect order-API limits (10 req/s for non-registered algos) and current SEBI/NSE/Upstox retail-algo requirements (registration, static IP, order-rate thresholds, strategy identification) `[VERIFY before enabling]`.
7. Hard limits independent of strategy: max lots, max outlay, daily loss, manual kill switch, flatten-all command.
8. First live deployment: one lot, manual supervision, owner-chosen window.

## 10.4 Execution tests
| ID | Test |
|---|---|
| T-EX-1 | Paper adapter idempotency and event sequences (fill, partial + expire, expire) |
| T-EX-2 | Import-linter: no broker symbol reachable from `simulation`, `research`, `ledger`, `risk` |
| T-EX-3 | (Phase 9) fake broker server: timeout after acceptance ⇒ UNKNOWN ⇒ reconcile ⇒ FILLED without duplicate |

## 10.5 [v1.2] Paper/live isolation (ADR-027) — status: DESIGNED
**Decision.** One PostgreSQL cluster, **separate schemas and separate roles**; the live schema does not exist until the Phase 9 migration; paper and live run as **different processes with different credentials and different installed code**. A separate *database* is not adopted now: the dangerous path is the broker credential and the order code, not table adjacency, and a second database would add backup/migration cost without closing that path. T9.1 re-evaluates a separate database for live.
| Layer | Paper (now) | Live (Phase 9 only) |
|---|---|---|
| Schema | `qv_paper` | `qv_live` (created by the Phase 9 migration) |
| DB role | `qv_paper_rw`: read/write `qv_paper`; read `qv_core`; insert `qv_core.audit_events` | `qv_live_rw` (same shape on `qv_live`) |
| API role `qv_api` | SELECT on `qv_paper`; INSERT **only** on `qv_paper.order_commands`; read/write `qv_core.viz_preferences`; **no** INSERT/UPDATE/DELETE on orders, fills, ledger, positions | same, never `qv_live` order tables |
| Process | `paper-runner` | `live-executor` (`apps/live_executor.py`, absent before the gate) |
| Credentials | **No** `UPSTOX_*` variable and no token file readable by the process (OS ACL); start-up check fails with `CREDENTIAL_LEAK` otherwise | token file readable only by `live-executor` |
| Installed code | extras `[paper]` exclude the broker SDK; import-linter forbids `upstox_client` and `execution.upstox` anywhere in the `paper-runner` import closure | extras `[live]` |
| Config | `environment: paper`; `QV_LIVE_ENABLED` present ⇒ refuses to start (`ENV_CONFLICT`) | requires the three locks below |
| Network | host firewall rule denies the paper-runner process to broker order hosts; tests use a fake broker that records any request | order-host access only for `live-executor` |
| Account mode | every order, fill, ledger event and trading-stream envelope carries `account_mode`; composite FK `(account_id, account_mode)`; `schema_mode_guard` trigger (§9.5.1) | same, `'LIVE'` |
**Collector credential caveat `[VERIFY S-token-scope]`.** The market-data collectors need an Upstox token. Unless Upstox issues read-only scoped tokens, that token may also be order-capable. Mitigations: collectors use `UpstoxReadClient`, a wrapper exposing only whitelisted GET endpoints; `market_data` may not import order modules; a static test greps the collector package for order URLs; the token file ACL admits only collector processes; the Phase 9 checklist records whether a separate order token is used.
**Live enablement — three independent locks, all required.** (1) `QV_LIVE_ENABLED=1` in the `live-executor` environment only; (2) `config/live/readiness_signed.yaml` with owner signature, checklist hash and an expiry (re-signed every 90 days); (3) a per-session `qv live arm --until HH:MM` command with typed confirmation, written to `audit_events`. Any lock missing ⇒ the executor starts `DISARMED` and raises `LIVE_NOT_ARMED` on submit. Hard limits (max lots, outlay, daily loss) live in a file separate from strategy profiles and are enforced **inside the broker adapter**, in addition to the risk engine. Adding manual paper trading does not touch any lock: the manual path has no broker code at all.
Tests (PENDING; gates G7.2 / G9): T-ISO-1 a full simulated day with the fake broker records **zero** requests and no `upstox` module in `sys.modules`; T-ISO-2 import-linter closure check for `paper-runner`; T-ISO-3 `qv_paper_rw` cannot read `qv_live`, and an order with `account_mode='LIVE'` cannot be inserted into `qv_paper`; T-ISO-4 `qv_api` cannot INSERT into orders/fills/ledger_events but can into `order_commands`; T-ISO-5 mismatched `(account_id, account_mode)` and wrong origin/kind are rejected; T-ISO-6 `QV_LIVE_ENABLED` in a paper environment ⇒ `ENV_CONFLICT`; T-ISO-7 `UPSTOX_*` in the paper environment ⇒ `CREDENTIAL_LEAK`; T-ISO-8 executor without all three locks starts `DISARMED`; T-ISO-9 `POST /manual/orders` against a LIVE or STRATEGY account ⇒ 403 `ACCOUNT_MODE_MISMATCH`; T-ISO-10 collector package contains no order endpoint.

---

# 11. Machine learning (`quantview.ml`) — starts after Phase 5

## 11.1 Scope and roles [v1.1]
Purpose: let the owner explore every model type that might help, under one governance protocol so that exploration cannot fool us. Models never place orders. They emit features (`ml_*`) that strategies consume, or act as filters configured inside a strategy spec. No LLM is in any decision path.
A model has exactly one **role**:
| Role | Learns | Dataset rows | Label (§11.3.1) | Output feature |
|---|---|---|---|---|
| `GENERAL` | direction of the next move on any bar | every eligible 5m bar | `tb_v1` | `ml_p_up_<id>`, `ml_p_dn_<id>` |
| `STRATEGY_META` | whether *this strategy's* signals work | only bars where strategy `S` (bound by `spec_hash`) emits ENTER | `strat_outcome_v1` (the strategy's own exit rules decide the outcome) | `ml_p_win_<id>` (strategy takes, skips or sizes) |
| `STRATEGY_GATED` | direction, but only inside the strategy's setup | bars where the strategy's `setup` expression is true: the strategy defines *when to look*, the model decides *which way* | `tb_v1` from the setup bar | `ml_p_up_<id>`, `ml_p_dn_<id>` |
| `REGIME` | volatility / trend regime | every eligible bar | `vol_regime_v1` | `ml_regime_<id>` (class probabilities) |
| `PATTERN` | whether a detected pattern event (range break, trendline break, opening-range break) holds | bars where a catalogue pattern feature fires | `pattern_hold_v1` | `ml_p_hold_<id>` |
| `OVERNIGHT` | next-open return from the day's close (BTST) | one row per session at the decision time (default 15:20) | `overnight_gap_v1` | `ml_p_gap_up_<id>` |
Model families: baselines B0/B1/B2, M1 LightGBM, M2 XGBoost (optional), any other family (for example a small sequence model) only after baselines are beaten and ≥ 3 years of data exist. Every family goes through the same evaluation (§11.6), trial counting and holdout lifecycle (§11.12). Models trained on option-chain features stay `EXPLORATORY` until ≥ 18 months of chain data exist. A model never "invents" signals from nothing: strategy-specific learning is expressed through `STRATEGY_META` and `STRATEGY_GATED` (§11.11).


## 11.2 Dataset
- Base timeframe `5m`; one sample per finalised 5m bar between 09:30 and 14:30 IST (decision at `bar_end`).
- Features (all `ok` required, else sample dropped and counted), scale-free:
  `ret_1, ret_3, ret_6, ret_12`; `body_ratio, close_loc, upper_wick/atr_14, lower_wick/atr_14, streak`; `dist_sma_pct_20, dist_sma_pct_50`; `rsi_14`; `macd_12_26_9__hist / atr_14`; `adx_14__adx, adx_14__plus_di − adx_14__minus_di`; `atr_pct_14, realized_vol_20, parkinson_20, ewma_vol_0.94, bbands_20_2.0__pctb, bbands_20_2.0__width`; `min_since_open, dow, expiry_regime, is_weekly_expiry_day, session_gap_pct, dist_prev_close/atr_14, dist_session_open/atr_14, dist_prior_high_20/atr_14, dist_prior_low_20/atr_14`; `mtf rsi_14 @1h`, `mtf dist_sma_pct_20 @1h`.
- Dataset file: `data/derived/ml/<dataset_hash>/{X.parquet,y.parquet,meta.json}`; `dataset_hash` covers data version, feature versions, label params.

## 11.3 Labels (triple barrier on the 1m path)
For sample at decision time `T` (5m bar end): entry price `p0 = open` of the 1m bar starting at `T`; `A = atr_14` (5m) at the decision bar; barriers `U = p0 + k·A`, `L = p0 − k·A` with `k = 1.0`; vertical barrier at `min(T + H, force_flat_time)` with `H = 60 minutes`. Scan 1m bars from `T`:
- first bar with `high ≥ U` and `low > L` ⇒ label `+1`; first with `low ≤ L` and `high < U` ⇒ label `−1`;
- a bar touching both ⇒ label `0` (ambiguous, conservative);
- no touch by the vertical barrier ⇒ label `0`.
Targets: `y_up = (label == +1)`, `y_dn = (label == −1)`. Store `label_end_time` per sample (time of touch or vertical barrier).
**Uniqueness weights:** concurrency `c_t` = number of samples whose `[T_i, label_end_i]` covers 1m bar `t`; `w_i = mean_{t ∈ span_i}(1 / c_t)`; normalise weights to mean 1.

### 11.3.1 [v1.1] Label registry
```python
class LabelSpec(BaseModel):
    label_id: str; version: int
    event_source: Literal["BARS","STRATEGY_ENTER","SETUP","PATTERN","SESSION"]
    params: dict; horizon: str; path_resolution: Literal["1m"]
    code_sha256: str                       # hash of ml/labels/<label_id>.py
```
Rules: labels are code in `ml/labels/<label_id>.py` with hand-built fixtures; registered in table `ml_labels`; **immutable once any dataset or model references them** (a change creates a new version); the label function receives only data with `available_at ≤ label_end_time` and returns `label_end_time` per row (needed for purging, §11.4). Adding a label needs its fixture test (T-ML-1 style) and a registry row.
Registry v1:
- **`tb_v1`** — the triple-barrier label of §11.3 (default parameters unchanged).
- **`strat_outcome_v1`** — event = a strategy ENTER decision; simulate the strategy's own exit rules from the Mode B fill with the path-blind rules of §8.3.4; `y_win = 1` if `pnl_points − h > 0` (hurdle `h` default 4 points) else 0; also store `y_r = pnl_points / initial_risk_points` when the stop is defined. `label_end_time = exit_ts`. Requires UNDERLYING-basis exits (PREMIUM-basis outcomes need Mode C data and are exploratory).
- **`vol_regime_v1`** — `fv` = realised volatility of 1m log returns over the next `H` (default 60 min, annualised as §5.4.3). Class = LOW/MID/HIGH by terciles of `fv` at the same minute-of-day, with tercile cut-points computed only from each fold's training block; regression target `log(fv / rv_20_now)`. `label_end_time = t + H`.
- **`pattern_hold_v1`** — event when a catalogue pattern feature fires (`or_break_*`, range or trendline breakout features ported under §6.9). For an up-break through level `Lv` with `A = ATR(14)`: success barrier `Lv + 1.0·A`, failure barrier `Lv − 0.25·A` (mirrored for down-breaks), vertical `H = 60 min`; first touch decides; both touched in one bar ⇒ failure (conservative); timeout ⇒ failure unless the owner configures a third class.
- **`overnight_gap_v1`** — one row per session at decision time `t_dec` (default 15:20, bar_end): `p0` = open of the first 1m bar at or after `t_dec`; `p1` = open of the first 1m bar of the next session; `y_ret = ln(p1/p0)`; classes UP / FLAT / DOWN by `±θ·ATR_14(1d)` (default `θ = 0.25`). `label_end_time` = next session open.


## 11.4 Splits (leakage-safe)
- Final holdout: governed by the holdout lifecycle of §11.12 (Mode B default 2026-01-01 → freeze date). Touched only for finalists; never used to choose between candidates. `OVERNIGHT` datasets have ≈ 60 rows per quarter: use semi-annual folds and require ≥ 250 out-of-sample sessions in total, else status `INSUFFICIENT_EVENTS`.
- Walk-forward folds: test blocks of 3 calendar months from 2024-01-01 to 2025-12-31 (8 folds). For fold with test start `S`: train = samples with `label_end_time < S` (**purge**: remove any sample whose label span reaches `S`); inner validation = last 10% (chronological) of the train set, again purged by `H` from the train tail. No embargo is needed for forward-only splits; if combinatorial or backward-looking CV is ever added, embargo = `H` after each test block.
- Preprocessing (standardisation for logistic) fitted on the train part only.

## 11.5 Models and fixed hyper-parameters
| Model | Specification |
|---|---|
| B0 | No trades |
| B1 | The reference strategy `ema_cross_adx` signals taken as filter (same bars) |
| B2 | Logistic regression, L2, `C = 1.0`, `class_weight="balanced"`, `max_iter = 1000`, standardised features, one model per target |
| M1 | LightGBM binary, `learning_rate=0.03`, `n_estimators=2000` with early stopping 100 rounds on the inner validation block, `num_leaves ∈ {15, 31}`, `min_child_samples ∈ {200, 500, 1000}` (choose on inner validation log-loss; each combination counts as a trial), `feature_fraction=0.7`, `bagging_fraction=0.7`, `bagging_freq=1`, `lambda_l2=5.0`, `seed=20260101`, sample weights = uniqueness weights |
Calibration: isotonic regression fitted on the inner validation block; report reliability bins and Brier score.

## 11.6 Evaluation
Per fold and concatenated OOS: log-loss, ROC-AUC, Brier, calibration slope. **Trading utility** is measured through the Mode B engine with the model as an entry filter: BULLISH entry if `p_up ≥ τ_up` and `p_up − p_dn ≥ δ`, BEARISH mirrored; `τ` and `δ` are chosen on the inner validation block to maximise expectancy at hurdle `h = 4` points; exits use the strategy's standard exit rules (`atr_mult` stop/target = barrier distances). Report against B0/B1/B2 on identical bars, including the hurdle table and day-block bootstrap CI (§8.10.3).

## 11.7 Experiment tracking
Every training/eval run writes `data/models/<model_id>/{model.txt|model.pkl, metadata.json, eval.json}`; `metadata.json` holds dataset hash, feature schema (names, order, versions, SHA-256), label parameters, split definition, hyper-parameters, seed, library versions, trial count, metrics. The registry table: `models(model_id, family, status {candidate, approved, retired}, created_at, metadata_ref, parent_model_id)`; promotion changes status only through a command that checks §11.8 and records an audit event; rollback = set the previous approved model active.

### 11.7.1 [v1.2] Experiment completeness (gaps closed; §11.4, §11.8, §11.12 already specify purge, holdout lifecycle and promotion) — status: DESIGNED
Review result: chronological/walk-forward validation, purging, a frozen final holdout, bootstrap promotion tests against simple baselines (B0/B1/B2) and trial counting are **already specified**. Remaining gaps:
- **Failed and aborted runs count.** `ml_experiments` gains `status ∈ {COMPLETED, FAILED, ABORTED}` and `error`; a failed or aborted run still increments `n_trials` of its family (a crash after seeing a bad fold is still a look).
- **Manual strategy changes count.** Every new `strategy_versions` row in a family counts as ≥ 1 trial even if no run finished, tagged `edit_source ∈ {MANUAL, AI_ASSISTED, PARAM_SWEEP}` with `parent_version`; the trial ledger view (`GET /experiments/trials?family=`) lists models, labels, features, thresholds **and** spec edits.
- **Purge for rule-based walk-forward (§8.11).** Trades whose entry lies in a training window but whose exit reaches the test window start are removed from the training set; OVERNIGHT strategies add an embargo equal to the maximum `sessions_held`.
- **Reproducibility record.** `metadata.json` additionally stores `strategy spec_hash`, `manifest_hash` of the evaluating Mode B run, `calendar_version`, `data_version` and `feature_versions`; promotion refuses a candidate whose recorded versions cannot be loaded.
- **No promotion on in-sample results or on trial volume.** The promotion command fails (`PROMOTION_CRITERIA`) unless criteria 1–7 of §11.8 hold on out-of-sample data **with `p_adj` reported**; a candidate whose `n_trials` exceeds `ml.max_trials_per_family` (default 200 **[OWNER]**) needs a new frozen forward holdout first.
Tests: T-ML-13 failed run increments `n_trials`; T-ML-14 a spec edit increments the family counter; T-ML-15 rule-based purge removes crossing trades; T-ML-16 promotion refuses an unloadable recorded version.

## 11.8 Promotion criteria (defaults **[OWNER]**; all required)
1. Walk-forward ROC-AUC (up/down targets averaged) ≥ 0.52 in at least 6 of 8 folds and mean ≥ 0.53.
2. Concatenated OOS net expectancy at `h = 4` points > 0 with day-block bootstrap `ci95` lower bound > 0 and `p_adj` reported.
3. Beats the best baseline's expectancy; the paired day-block bootstrap of the difference has lower bound > 0.
4. Holdout evaluated **once**: expectancy > 0 and calibration slope within [0.8, 1.2].
5. Single-row inference latency p99 ≤ 5 ms (measured, 10,000 calls, same process).
6. Feature schema hash stored; inference refuses mismatched schemas.
7. Owner review recorded; then ≥ 20 paper sessions in inference-only (shadow) mode before any strategy may use the model.

**[v1.1] Role-specific adjustments.** For `STRATEGY_META`, `STRATEGY_GATED`, `PATTERN` and `OVERNIGHT`, criterion 1 (6-of-8 fold AUC) is replaced by: concatenated out-of-sample AUC ≥ 0.53 with a day-block bootstrap lower bound > 0.50 and ≥ 300 out-of-sample events (≥ 250 sessions for `OVERNIGHT`), else status `INSUFFICIENT_EVENTS`. Their baseline for the utility criteria is the strategy's own trades (`STRATEGY_META`: expectancy with the model filter versus without, same hurdle, paired day-block bootstrap lower bound > 0). `REGIME` models are promoted on calibration and stability (log-loss against the class-frequency baseline, Brier skill, per-fold stability) and are only *used* as filters; their usefulness is judged by the strategies that use them under Mode B.


## 11.9 Inference (`predictor.py`)
```python
class Predictor:
    def __init__(self, model_id: str): ...          # loads artifact, verifies schema hash
    def predict(self, row: FeatureRow) -> Prediction | None   # None unless every required feature is ok
```
Exposed to strategies as feature family `ml` (`ml_p_up_<id>`, `ml_p_dn_<id>`, `ml_p_win_<id>`, `ml_p_hold_<id>`, `ml_regime_<id>`, `ml_p_gap_up_<id>`) **[v1.1]** through the `ExternalFeatureProvider` protocol — defined in `research.features.contracts` (`columns() -> list[str]`, `compute(row: FeatureRow) -> dict[str, float | None]`, `feature_version: str`), implemented by `ml.predictor.Predictor` and registered by the `apps` composition root — so `research`, `simulation` and `risk` never import `ml` (ADR-025). Values are computed at bar close from as-of features only; training never runs in the live process. The `Predictor` refuses to load a strategy-bound model whose `spec_hash` differs from the running strategy version (`STALE_BINDING`).

## 11.10 ML tests
| ID | Test |
|---|---|
| T-ML-1 | Triple-barrier labels on hand-built 1m paths (up first, down first, both-in-bar ⇒ 0, vertical, force-flat truncation) |
| T-ML-2 | Purge: no training sample's `label_end_time` ≥ test start |
| T-ML-3 | Leakage canary: shuffled labels give AUC within 0.5 ± 0.02 on OOS folds; a feature with future info (injected) is detected by the truncate-and-recompute test |
| T-ML-4 | Determinism: same seed ⇒ identical predictions |
| T-ML-5 | Schema mismatch raises at load; latency test p99 ≤ 5 ms |
| T-ML-6 | Uniqueness weights sum/normalisation on a crafted overlap example |
| T-ML-7 | **[v1.1]** Label registry: referenced label versions are immutable; each registered label passes its hand-built fixture; `label_end_time` present on every row |
| T-ML-8 | **[v1.1]** `STRATEGY_META` dataset events equal the strategy's ENTER decisions on the same data (batch vs engine replay) |
| T-ML-9 | **[v1.1]** `vol_regime_v1` tercile cut-points use training data only (poisoned-future test) |
| T-ML-10 | **[v1.1]** `overnight_gap_v1` hand-built example incl. Friday → Monday and a holiday |
| T-ML-11 | **[v1.1]** Holdout lifecycle: the 4th look raises `HOLDOUT_LOCKED`; a non-finalist candidate is refused; `n_trials` increments per experiment |
| T-ML-12 | **[v1.1]** `Predictor` refuses a model whose bound `spec_hash` differs (`STALE_BINDING`); `research` does not import `ml` (import-linter) |

## 11.11 [v1.1] Strategy-specific models (configured with AI help)
1. The owner (or an AI assistant) names `strategy_id@version` and a role (`STRATEGY_META` or `STRATEGY_GATED`) plus optional `extra_features` from the catalogue.
2. `ml.datasets.from_strategy()` derives the event set from the spec (ENTER decisions, or the `setup` expression), takes the strategy's own feature columns plus `extra_features`, attaches the role's label (§11.3.1) and records `spec_hash` in the dataset hash. The model never sees other strategies' events: it learns only this strategy.
3. The trained model is bound to `spec_hash`. Changing the strategy creates a new version and the old model becomes `STALE_BINDING`; it must be retrained.
4. To use it, the strategy spec requests the feature (`{"name": "ml_p_win", "params": {"model": "<id>"}}`) and adds a condition such as `{"gte": [{"f": "ml_p_win_<id>"}, {"p": "ml_tau"}]}` to `entry`; `ml_tau` is a strategy parameter chosen on inner validation, never on the holdout.
5. `STRATEGY_META` keeps the strategy's side and exits and only decides take / skip / size. `STRATEGY_GATED` lets the strategy define the setup bars and the model choose direction (`entry.bullish` uses `ml_p_up`, `entry.bearish` uses `ml_p_dn`).

## 11.12 [v1.1] Exploration, trials and holdouts
**Why this exists.** Models are independent algorithms, but the *choice* among them is not independent of the data used to judge them. If you try N models, labels, feature sets or thresholds and keep the best on the same evaluation data, the winner is partly selected for luck: among N candidates with no real skill the best observed score grows roughly like `σ·√(2·ln N)`. Running experiments in isolated environments protects against code and data leakage, not against this; only data that was never used to choose does.
| Zone | Data | Allowed use |
|---|---|---|
| EXPLORE | Walk-forward folds (§11.4) | Unlimited experimentation. Every combination of model family × label × feature set × hyper-parameters is one trial and increments `n_trials` of its experiment family |
| HOLDOUT | Frozen block (ADR-015) | Finalists only, at most 3 looks per experiment family in total; every look is logged with the candidate hash. After the 3rd look, or any look used to choose between candidates, the holdout is `BURNED` |
| FORWARD | Sessions recorded after the freeze or burn date | A fresh holdout block is frozen from sessions recorded after a burn; every deployed model also runs ≥ 20 paper sessions in shadow mode (§11.8.7) |
**Experiment family** = `(role, label_id, strategy_id | None)`. `n_trials` appears in every report; promotion p-values are Bonferroni-adjusted by `n_trials` (conservative because trials are correlated).
**Tables.** `ml_experiments(experiment_id, family, dataset_hash, model_family, params_hash, folds_metrics jsonb, created_at)` and `ml_holdout_looks(holdout_id, family, candidate_hash, looked_at, purpose)`. `ml evaluate --holdout` refuses a burned holdout (`HOLDOUT_LOCKED`, §12.4) and any candidate the owner has not marked `FINALIST`.

---

# 12. API (`quantview.api`)

## 12.1 Conventions
Base path `/api/v1`; JSON; UTC ISO-8601 timestamps with `Z`; numbers as JSON numbers (prices float, money fields suffixed `_paise` as integers). Pagination: `limit` (default 1000, max 20000) + `cursor`. All responses carry `X-Correlation-Id`. Errors (§12.4). The OpenAPI document is generated from Pydantic models and committed as `docs/openapi.json` by CI (not a third specification — a generated artifact).

## 12.2 REST resources
| Method & path | Purpose | Key params → response |
|---|---|---|
| `GET /health/live`, `/health/ready` | Liveness / readiness | `{status, checks{db, duckdb, collectors}}` |
| `GET /instruments` | Instrument list | `kind, underlying` → `[Instrument]` |
| `GET /calendar/sessions` | Sessions and bounds | `from,to` → `[{date, open, close, kind}]` |
| `GET /candles` | Candle bars | `instrument, tf, from, to, limit, cursor, source=preferred, as_of?` → `{bars:[[t_ms,o,h,l,c,v,flags]], coverage, next_cursor}` |
| `GET /candles/coverage` | Calendar-driven coverage | `instrument, tf, from, to` → `CoverageReport` |
| `GET /features/catalogue` | Registered features | → `[FeatureInfo]` |
| `POST /features/compute` | Compute feature series | `{instrument, tf, from, to, features:[{name,params}]}` → `{columns, rows, ok, reasons}` (cached) |
| `GET /option-chain/snapshots` **[superseded by `/research/option-chain/snapshots`, §12.2.1]** | Snapshot index | `date, expiry?` → `[SnapshotIndexRow]` |
| `GET /option-chain/snapshot` **[superseded, §12.2.1]** | One snapshot | `at, expiry, max_age_s?` → `SnapshotView` (rows, age, flags) |
| `GET /option-chain/features` **[superseded, §12.2.1]** | Option features for a time | `at, expiry` → feature dict with reasons |
| `GET/POST /strategies` | List / create (spec or python ref) | → `Strategy` |
| `POST /strategies/{id}/versions` | New immutable version | spec → `{version, spec_hash, validation}` |
| `POST /strategies/validate` | Validate a spec | spec → `{ok, errors[], columns[], warmup_bars}` |
| `POST /backtests` | Start a run | `{mode: B, C or S, strategy{id,version,params}, range, fill_model, cost_model?, purpose, risk_profile?, account_equity_paise?, ceiling_mode?, execution params}` → `{run_id}` (202) |
| `GET /backtests/{run_id}` | Status, manifest, summary | |
| `GET /backtests/{run_id}/{artifact}` where artifact is one of trades, equity, decisions, rejections, annotations, coverage, sensitivity, bootstrap | Artifacts | paginated |
| `GET /paper/accounts`, `POST /paper/accounts` | Paper accounts; creation takes `{name, starting_equity_paise (any amount), risk_profile: id@version}` | |
| `GET/POST /risk/profiles`, `POST /risk/profiles/{id}/versions` | **[v1.1]** Account risk profiles; an edit creates a new immutable version; audited | profile → `{version, hash, validation{errors, warnings}}` |
| `POST /risk/profiles/validate`, `POST /risk/profiles/feasibility` | **[v1.1]** Validate (§8.6.6); feasibility: share of recent ATM snapshots on which one lot fits the ceilings at a given equity | → report |
| `POST /paper/deployments`, `POST /paper/deployments/{id}/{action}` **[superseded by the state machine endpoints, §12.2.1]** | Deploy strategy to paper | |
| `GET /paper/orders`, `/paper/fills`, `/paper/positions`, `/paper/ledger`, `/paper/equity` | Account views | `account_id`, range |
| `POST /kill-switch` | Toggle scope `global` or `strategy:<id>` | `{enabled, reason}` → audited |
| `GET /data-quality/status` | Dataset status by day | `dataset, from, to` |
| `GET /data-quality/reports/{date}` | DQ report | |
| `GET /ops/collectors` | Heartbeats, last success, lag | |
Endpoints that start long work return 202 + `run_id`; progress via WebSocket `run.progress` and polling.

### 12.2.1 [v1.2] Additional and amended resources — status: DESIGNED
Where this table and the v1.1 table above disagree, **this table wins** (it replaces the `/option-chain/*` paths, the single `/paper/deployments/{id}/{action}` row and the `/paper/accounts` creation semantics).
| Method & path | Purpose | Key params → response |
|---|---|---|
| `GET /candles` (amended) | adds `include_gaps=true`: expected-but-missing bars are returned as `{t_ms, gap:true, reason}` so the chart shows holes; `as_of` mandatory with `replay_id` | |
| `POST /replay/sessions` | Start a replay | `{kind: CHART\|EVENT\|BACKTEST, instrument, tf, start_at, features[], deployment_ids[]?, run_id?, speed}` → `{replay_id, now, kind}` |
| `POST /replay/{id}/step` · `/play` · `/pause` · `/seek` · `GET /replay/{id}/state` · `DELETE /replay/{id}` | Control | step `{direction: FWD\|BACK, n, unit: BAR\|MINUTE}`; play `{speed}`; seek `{to}` → `{now, state}` |
| `GET /replay/{id}/candles`, `/features`, `/events` | Data **clamped server-side** to `now`; asking beyond `now` ⇒ `REPLAY_FUTURE_ACCESS` | `/events` only for EVENT/BACKTEST kinds |
| `GET /live/option-chain` | Live chain (hybrid feed) | `expiry, band=10, center=ATM` → `LiveChain` (below) |
| `GET /live/option-chain/status` | Feed/market state for the chain | → `{market_state, feed_state, last_update_at, server_now}` |
| `GET /research/option-chain/snapshots`, `/snapshot`, `/features` | Historical snapshots (the v1.1 `/option-chain/*` endpoints, renamed); responses carry `context:"HISTORICAL"` | |
| `GET/POST /manual/account`, `POST /manual/account/reset` | Manual paper account (create; archive-and-recreate with `confirm`) | |
| `GET /manual/account/summary` | Equity, cash, realised/unrealised, charges (that account only) | |
| `POST /manual/orders/validate` | Dry run = exactly what submit decides | `{instrument_id, side, qty_lots, order_type, limit_price_paise?}` → `{est_fill_price_paise, est_outlay_paise, est_charges_paise, cash_after_paise, advisories[], hard_failures[]}` |
| `POST /manual/orders` | Place (asynchronous, single writer) | `{client_order_id, …same}` → 202 `{command_id}`; 503 `RUNNER_UNAVAILABLE` |
| `POST /manual/orders/{order_id}/cancel` | Cancel | → 202 |
| `POST /manual/positions/{instrument_id}/exit`, `POST /manual/positions/exit-all` | Explicit exits | `{qty_lots\|"ALL", order_type, limit_price_paise?, client_order_id}` |
| `GET /manual/orders`, `/fills`, `/positions`, `/ledger`, `/equity`, `/performance` | Account views | range, cursor |
| `GET/POST /paper/accounts` (amended) | **STRATEGY** accounts only (`account_kind` fixed); manual accounts use `/manual/*` | `{name, starting_equity_paise, risk_profile: id@version}` |
| `POST /paper/deployments` | Create (CREATED) | `{account_id, strategy_id, version, params?, auto_resume?}` |
| `POST /paper/deployments/{id}/start` · `/pause` · `/resume` · `/acknowledge-error` | State commands (§8.8.3) | → deployment |
| `POST /paper/deployments/{id}/stop` | Stop | `{position_policy: DRAIN\|FLATTEN, confirm_flatten?: bool}` (FLATTEN without confirmation ⇒ 422) |
| `GET /paper/deployments`, `/{id}`, `/{id}/events` | State, errors, config snapshot, `deployment_events` | |
| `GET /paper/deployments/{id}/trade-events` | `TradeChain[]` from persisted rows | `strategy_version, instrument, from, to, state, cursor` |
| `GET /paper/deployments/{id}/indicators` | Feature pins + display metadata + warm-up + default visibility | |
| `GET /paper/deployments/{id}/indicator-series` | Persisted series (`source: PERSISTED \| RECOMPUTED`) | `from, to, tf` |
| `GET /paper/orders`, `/fills`, `/positions`, `/ledger`, `/equity` (amended) | Strategy-account views | `account_id`, `origin?`, range |
| `GET /viz/deployments`, `PUT /viz/deployments/{id}` | **UI-only** visualization preferences | `{visible, markers, indicators, levels, hidden_series[], filters{deployment, version, instrument, from, to}}`; writes only `qv_core.viz_preferences` |
| `GET /features/{name}/explain` | Mathematical definition (§5.1.9) | `version?` |
| `POST /features/compute` (amended) | adds `version_pins` | |
| `GET /backtests/{run_id}/metrics`, `/metrics/{metric_id}` | Metric list; `MetricDetail` (§8.10.5) | |
| `GET /backtests/{run_id}/coverage-matrix`, `/eligibility`, `/execution-assumptions`, `/charges`, `/risk-overshoot`, `/trades/{trade_id}` | Report panels | |
| `GET /data-quality/coverage-matrix` | Matrix levels L1–L3 (§4.4.1) | `dataset, level, from, to` |
| `GET /ops/streams`, `POST /ops/streams/{consumer}/reset-checkpoint` | Journal lag, epochs, checkpoints; audited reset | |
| `POST /kill-switch` (amended) | adds `action: BLOCK_ENTRIES\|BLOCK_AND_FLATTEN` | |
```python
class LiveChain(BaseModel):                       # authoritative payload for the live-only screen (OPTIONS_CHAIN_UI.md)
    context: Literal["LIVE"] = "LIVE"             # a historical payload can never carry this literal (type-level separation)
    server_now: datetime; market_state: Literal["PRE_OPEN","OPEN","CLOSED","HOLIDAY"]
    feed_state: Literal["OK","STALE","DOWN"]; last_update_at: datetime | None
    expiry: date; dte_days: float; spot: Cell[float]; atm_strike: int
    rows: list[ChainRow]                          # one per strike, ascending; ce/pe each a ChainSide
class Cell(BaseModel, Generic[T]):                # every displayed value carries its provenance and freshness
    value: T | None; source: Literal["WS_FULL","REST_SNAPSHOT"] | None
    as_of: datetime | None; age_s: float | None
    freshness: Literal["LIVE","DELAYED","STALE","MISSING"]; reason: str | None     # reason codes of §4.4.1 / greeks_status
class ChainSide(BaseModel):
    ltp: Cell[float]; bid: Cell[float]; ask: Cell[float]; bid_qty: Cell[int]; ask_qty: Cell[int]
    volume: Cell[int]; oi: Cell[int]; chg_oi: Cell[int]; iv: Cell[float]
    delta: Cell[float]; gamma: Cell[float]; theta: Cell[float]; vega: Cell[float]; greeks_status: str
    ws_subscribed: bool; depth: list[DepthLevel] | None      # depth only for WS-subscribed contracts
```
The server computes `age_s` and `freshness` from its own clock; the browser never derives freshness from its clock alone.

## 12.3 WebSocket `/ws/v1/stream`
Client → server messages: `{"op":"subscribe","channels":[...]}`, `{"op":"unsubscribe","channels":[...]}`, `{"op":"resync","channel":..., "since_event_id":...}`, `{"op":"ping"}`.
Channel objects: `{"type":"candles","instrument":"IDX:NIFTY50","tf":"1m"}`, `{"type":"option_chain","expiry":"YYYY-MM-DD"}`, `{"type":"orders","account_id":"..."}`, `{"type":"positions","account_id":"..."}`, `{"type":"ledger","account_id":"..."}`, `{"type":"health"}`, `{"type":"run","run_id":"..."}`.
Server → client: `EventEnvelope` (§2.3) plus `channel` and a per-connection monotonically increasing `ws_seq`. Heartbeat `{"type":"pong"}` every 15 s; the client reconnects with backoff 1–30 s and **always** re-fetches authoritative state over REST (latest candle page, open orders, positions) before applying new events; events with `event_id` already applied are dropped.

**[v1.2] Channels and delivery.** New channels: `{"type":"live_option_chain","expiry":"YYYY-MM-DD","band":10}`, `{"type":"replay","replay_id":"…"}`, `{"type":"deployments"}`, `{"type":"manual"}`. TELEMETRY channels (`candles` provisional, `live_option_chain`) are **conflated latest-wins** every `live_chain.push_conflate_ms` (500 ms; 250 ms for candles): slow clients receive the newest state, never a queue, and every message carries `server_now` and `feed_state`. TRADING channels (`orders`, `positions`, `ledger`, `deployments`, `manual`) carry the outbox `seq`; `{"op":"resync","since_event_id":…}` is answered from the outbox (§2.7.5), so a reconnecting client loses nothing and applies each `event_id` once.

## 12.4 Errors
Body: `{"code": "...", "message": "...", "details": {...}, "correlation_id": "..."}`.
| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Bad request/spec |
| `DATA_UNAVAILABLE` | 404/409 | Required data absent (strict mode) |
| `STALE_DATA` | 409 | Data older than policy |
| `DATA_QUALITY` | 409 | Data fails quality requirement |
| `RISK_REJECTED` | 409 | Intent rejected (rule ids in details) |
| `CONFLICT` | 409 | Illegal state transition / duplicate |
| `LOOKAHEAD_VIOLATION` | 500 | Engine guard tripped (a bug) |
| `HOLDOUT_LOCKED` | 403 | Tuning run overlaps a frozen holdout |
| `EXTERNAL_SERVICE` | 502 | Provider error |
| `OUTCOME_UNKNOWN` | 502 | Broker outcome uncertain |
| `ACCOUNT_MODE_MISMATCH` | 403 | Order/command targets an account of the wrong mode or kind (§10.5, §8.8.2) |
| `RUNNER_UNAVAILABLE` | 503 | `paper-runner` heartbeat older than 15 s; nothing queued |
| `COMMAND_EXPIRED` | 409 | Manual command not handled within its TTL |
| `ORDER_TYPE_UNSUPPORTED` | 422 | Order type/validity not implemented by the simulator |
| `REPLAY_FUTURE_ACCESS` | 400 | Request beyond the replay cursor |
| `DEPLOYMENT_TARGET_INVALID` | 409 | Deployment targets a non-STRATEGY or non-ACTIVE account |
| `RISK_UNQUANTIFIABLE` | 409 | RK-22 (sub-reason in `details`) |
| `STREAM_DEGRADED` | 503 | Journal gap/rewind detected; entries blocked (§2.7.4) |
| `INTERNAL` | 500 | Unexpected |

---

# 13. Frontend (`frontend/`)

## 13.1 Stack and structure
Next.js (App Router) + TypeScript (strict) + Tailwind + TanStack Query (server state) + Zustand (UI state) + Lightweight Charts. Types generated from `docs/openapi.json` (`openapi-typescript`). No trading or accounting logic in the browser.
```text
frontend/src/
  app/ (routes)  chart/  options/  research/options/  strategies/  backtests/  paper/  paper/manual/  operations/  settings/   # [v1.2]
  features/ chart/ replay/ options/ strategies/ backtests/ paper/ manual/ viz/ ops/
  lib/ api.ts ws.ts time.ts format.ts
  components/ ModeBanner.tsx DqRibbon.tsx Table.tsx ...
```

## 13.2 Chart adapter (replaceable) — [v1.2] extended
Focused UX specification: `CHARTING_UX.md`. Lightweight Charts stays behind `ChartAdapter`; the commercial Advanced Charting Library and native Pine execution remain out of scope.
```ts
type Bar = { t_utc_ms: number; o: number; h: number; l: number; c: number; v?: number | null;
             flags: string[]; final: boolean; session_date: string };       // final=false => provisional (drawn differently)
type GapBar = { t_utc_ms: number; gap: true; reason: string };               // whitespace for an expected-but-missing bar
interface ChartAdapter {
  setBars(bars: (Bar | GapBar)[]): void;   prependBars(bars: (Bar | GapBar)[]): void;   updateBar(bar: Bar): void;
  setSeries(groupId: string, specs: SeriesSpec[], data: Record<string, Point[]>): void;  // indicators; groupId = "manual" | deployment_id
  removeGroup(groupId: string): void;
  setPaneLayout(panes: PaneSpec[]): void;
  setMarkers(groupId: string, markers: Marker[]): void;  clearMarkers(groupId: string): void;   // per-deployment, never shared
  setLevels(groupId: string, levels: Level[]): void;     clearLevels(groupId: string): void;
  setReplayCursor(t_utc_ms: number | null): void;        // adapter never renders or autoscales beyond the cursor
  setAutoscaleScope(scope: "ALL" | "REVEALED"): void;
  onVisibleRangeChange(cb: (fromMs: number, toMs: number) => void): void;
  onMarkerClick(cb: (ref: MarkerRef) => void): void;     destroy(): void;
}
```
Rules (acceptance in CHARTING_UX.md §10):
- **Time.** The data layer keeps `t_utc_ms`. Display uses Lightweight Charts' time formatters with `Asia/Kolkata` (`localization.timeFormatter`, `tickMarkFormatter`). The v1.1 trick of adding 19 800 s to every time value is kept **only** as an isolated fallback if the pinned library version cannot format by time zone; T1.7 decides with a Vitest round-trip and records the evidence. Daily bars use the `session_date` business-day string, not a shifted epoch.
- **Gaps are visible.** Lightweight Charts spaces bars by index, so a missing 1m bar would be invisible. `/candles?include_gaps=true` supplies `GapBar` whitespace entries and the DQ ribbon explains each reason.
- **Provisional vs final.** `final=false` bars use a distinct style (hatched/outlined) and are never fed to indicator series; a live bar becomes final only on `candle.finalized`.
- **Marker anchoring.** Markers snap to the displayed bar containing the event time (`bar_start ≤ t < bar_end` of the displayed timeframe). Their vertical position is the **underlying** reference level (`underlying_ref`), never the option premium; the premium is in the tooltip. Levels with `price_space = PREMIUM` are **not** drawn on the NIFTY axis (they appear in the inspector and in the option mini-pane); levels with `price_space = UNDERLYING` are drawn as lines from entry to exit.
- **Groups.** Markers, levels and series belong to a `groupId`; clearing one group never touches another. Each deployment has a stable colour slot and a letter glyph (colour-blind-safe palette + shape), so two deployments' markers are always distinguishable.
- **Memory.** Page size 5 000 bars; at most `chart.max_bars_in_memory` (50 000) retained, distant pages evicted; the browser never holds the whole history.
- **Replay.** The adapter obtains only server-clamped data (§12.2.1) and `setAutoscaleScope("REVEALED")`; it must not receive a bar later than the cursor.

## 13.3 Workspaces (acceptance per screen) — [v1.2]
| Route | Must show | Acceptance |
|---|---|---|
| `/chart` | Instrument/timeframe selector; candles (final vs provisional); gap whitespace + DQ ribbon; manual indicators (overlay/pane, version label, ƒ explain link); **replay** (CHARTING_UX.md §6); **Strategy overlays** panel (PAPER_TRADING_UI.md §5); mode banner | 450k-bar history navigable; first paint < 1 s; no future bar/feature/label in replay (T-RP-*); toggling overlays changes nothing but the view (T-VZ-4) |
| `/options` | **Live-only** chain (OPTIONS_CHAIN_UI.md): CE · strike · PE, ATM-centred band, expiry tabs, per-cell freshness, status chip, last update, quote age; market-closed state; order-ticket shortcut | Never labels historical data live; freshness comes from the server (T-LC-*) |
| `/research/options` | Historical snapshot picker + chain table + option features; banner "HISTORICAL SNAPSHOT — NOT LIVE" | Shares the table component with `mode="HISTORICAL"`, which cannot render a LIVE chip |
| `/strategies` | Spec editor (schema validation, column list), pins preview from validate, version history (with `edit_source`), templates | Invalid spec shows server errors; save creates a new version |
| `/backtests`, `/backtests/[run_id]` | Report per BACKTESTING_REPORT_SPEC.md: eligibility, warnings, summary metrics (each clickable → inspector), equity/drawdown, trades table + chart markers, per-trade drawer, coverage matrix, assumptions & charges, sensitivity, bootstrap CI, reproducibility | Mode B never shows ₹; kinds never mixed; every metric click shows backend formula + inputs (T-MI-1) |
| `/paper` | Tabs: Deployments (state machine controls), Orders, Fills, Positions, Ledger, Performance, Risk rejections; **strategy accounts only**; persistent "PAPER — SIMULATED" banner and account-kind badge | Reconnect restores state without gaps (outbox resync); controls offered match the allowed transitions |
| `/paper/manual` | Manual account summary, positions with Exit, **order ticket**, orders blotter (cancel), fills, ledger, performance; "MANUAL ACCOUNT" badge | Independent ledger/P&L (T-MN-*); ticket per PAPER_TRADING_UI.md §3 |
| `/operations` | Collector heartbeats, feed lag, DQ calendar + coverage matrix, **streams** (journal lag, epochs, consumer checkpoints), kill switch with action, audit log | Kill-switch round trip audited; stream gap visible |
| `/settings` | Risk profiles (versioned, diff), strategy accounts, **manual profile**, risk declarations and clamp warnings, recorder instrument set, pinned keys (read-only union), viz default | Editing a profile creates a version with an audit entry |
Colour themes: backtest = blue accent, paper = amber, live = red with persistent banner (live screens do not exist until Phase 9). Strategy-deployment marker colours come from a separate palette and never reuse the mode accent.

## 13.4 Frontend tests — [v1.2]
Vitest: `lib/time.ts` IST round trip; marker snapping; gap rendering; no-metric-arithmetic lint (T-MI-6); freshness chip state table. Component tests: banners, DQ ribbon, mode-typed chain table. Playwright (Phase 5+): open chart → add EMA → run Mode B → summary + markers → reload → same `result_hash`; replay leak scenario; manual ticket scenario; deployment visualization scenario (PAPER_TRADING_UI.md §9).

---

# 14. Operations

## 14.1 Schedules (IST, trading days only)
| Time | Job | Process |
|---|---|---|
| 08:45 | Token check; instrument master download | `apps/eod.py --morning` |
| 09:00 | Start `collect_snapshots` and `collect_live` | scheduler |
| 09:20 | Heartbeat check: alert if absent | watchdog |
| 15:35 | Collectors stop | self |
| 16:30 | EOD pipeline (§4.12) | `apps/eod.py` |
| 17:30 | Backup | `apps/eod.py --backup` |
Scheduler: Windows Task Scheduler or systemd timers (provide both templates in `scripts/ops/`); power settings must prevent sleep during 08:45–17:30.

## 14.2 Observability
- Logs: JSON via structlog to `data/logs/<app>/YYYY-MM-DD.log` (rotating, 30 days).
- Metrics (Prometheus-style names, exposed at `/metrics`, also appended to `data/quality/metrics.parquet` daily): `feed_lag_seconds`, `candle_finalize_lag_seconds`, `ws_reconnects_total`, `snapshot_success_ratio`, `snapshot_latency_ms`, `dq_status{dataset}`, `strategy_eval_ms`, `order_latency_ms`, `ledger_verify_ok`, `quotes_dropped_total`, `risk_rejections_total{rule}`; **[v1.2]** `journal_write_lag_ms`, `consumer_lag_events`, `outbox_pending`, `order_commands_queued`, `stream_gap_total`.
- Health JSON per collector at `data/ops/heartbeat_<name>.json`: `{pid, started_at, last_success_at, consecutive_failures, state}`.
- Alerts (v1: desktop notification + email via SMTP settings, optional Telegram): missing heartbeat 09:20; `consecutive_failures ≥ 10`; reconnect storms (> 10/5 min); DQ `UNUSABLE`; ledger verify fail; kill switch toggled; manifest mismatch.

## 14.3 Backups and restore drill
Nightly: copy `data/raw`, `data/canonical`, `data/quality`, `data/models`, `data/runs` and a `pg_dump` to the second location with `rsync`/`robocopy` + checksum manifest. Monthly drill (`scripts/ops/restore_drill.py`): restore raw to a temp dir, rebuild canonical for one month, compare Parquet content hashes against production; write the result to `data/quality/restore_drill_<date>.json`.

### 14.3.1 [v1.2] Restore and power-loss procedures — status: DESIGNED
| Drill | Cadence | Procedure | Pass criteria / artifact |
|---|---|---|---|
| Postgres restore | monthly | Restore the latest `pg_dump` into a scratch database; run `Ledger.verify()` and `rebuild()` for every account; compare row counts and `ledger_events` hash chain with production | `verify()` green, rebuild ≡ projection; `data/quality/pg_restore_drill_<date>.json` |
| Journal recovery | monthly | Copy the journal directory, corrupt the tail, start a consumer | Torn tail truncated, consumer resumes, no duplicate effects (T-EV-4) |
| Canonical rebuild | monthly (existing) | §14.3 | hashes equal |
| Power loss | CI nightly (fault-injection harness, T-EV-6) + one **real pull-the-plug drill** before gate G7.6 | Cut power during a session with an open position and a resting LIMIT order; reboot; start services | All invariants hold: ledger `verify()`, one position, no duplicate order, checkpoint ≤ journal tail, candle gap flagged not fabricated; `data/quality/powerloss_drill_<date>.json` |
Settings required: Postgres `fsync=on`, `synchronous_commit=on`, `full_page_writes=on`; on laptops disable the drive's volatile write cache or accept (and record) the residual risk. Targets: ledger RPO = 0 committed transactions, RTO < 15 minutes. Scheduler/host power rules of §14.1 still apply. Added metrics: `journal_write_lag_ms`, `consumer_lag_events{consumer}`, `outbox_pending`, `order_commands_queued`, `stream_gap_total`.

## 14.4 Startup checks (every process)
Config validates; data directories writable; calendar status shown (warn if UNVERIFIED); token valid (collectors); Postgres reachable (api/paper); migration version equals code; clock sanity (NTP offset < 1 s via a one-shot check); **[v1.2]** journal tail repair (collector), consumer checkpoint ≤ journal tail, `ENV_CONFLICT`/`CREDENTIAL_LEAK` checks (paper-runner), DB role sanity (api).

---

# 15. Test catalogue and CI

| Layer | Location | Run |
|---|---|---|
| Unit | `tests/unit` | every commit |
| Property | `tests/property` (hypothesis, ≥ 200 examples) | every commit |
| Parity | `tests/parity` | every commit |
| Look-ahead | `tests/lookahead` | every commit |
| Integration | `tests/integration` (Postgres via docker, Parquet round trip, API contract) | PR |
| Replay | `tests/replay` | nightly |
| E2E | `tests/e2e` + Playwright | PR from Phase 5 |
| Recovery (**v1.2**) | `tests/recovery` (crash-consistency harness, journal/ledger chaos, restore drills) | nightly + before every gate |
CI steps: `ruff`, `mypy`, `import-linter`, `pytest -q --cov`, OpenAPI regeneration check, frontend lint/test. Test IDs used in this document (`T-INS-*`, `T-MD-*`, `T-FE-*`, `T-ST-*`, `T-SEL-*`, `T-SIM-*`, `T-COST-*`, `T-RK-*`, `T-OS-*`, `T-PP-*`, `T-LG-*`, `T-EX-*`, `T-ML-*`; **[v1.2]** `T-EV-*`, `T-DQ-*`, `T-ISO-*`, `T-MN-*`, `T-DP-*`, `T-AC-*`, `T-CH-*`, `T-RP-*`, `T-LC-*`, `T-VZ-*`, `T-MI-*`, `T-RPT-*`) must appear in test names or docstrings so the completion report can map tests to requirements.

## 15.1 [v1.2] Acceptance matrix for the owner's 15 required tests
All entries are **PENDING** (status DESIGNED). A row becomes `TESTED` only with a CI artifact and `VERIFIED` only with the evidence named in Appendix C.
| # | Required test | Test IDs | Layer | Gate |
|---|---|---|---|---|
| 1 | Chart replay never reveals future bars or feature values | T-RP-1 (server clamps every endpoint to `now`), T-RP-2 (poisoned-future: NaN everything after `now`, visible output identical), T-RP-3 (features at `now` equal truncate-and-recompute), T-RP-4 (autoscale ignores future), T-RP-5 (forming higher-TF bar built from 1m ≤ `now`), T-RP-6 (determinism: same inputs ⇒ same frame hashes), T-RP-7 (step back ≡ seek), T-RP-8 (EVENT replay shows only events with `occurred_at ≤ now`; a window with no recorded deployment says so) | unit + Playwright | G3.1 |
| 2 | Metric click shows exact backend formula and inputs | T-MI-1, T-MI-2, T-MI-3, T-MI-5, T-MI-6 | unit + Playwright | G5.1 |
| 3 | Manual paper uses an independent account, ledger, P&L | T-MN-1, T-MN-12, T-MN-13, T-ISO-5 | integration | G7.3 |
| 4 | Manual trades do not affect strategy paper accounts | T-MN-2, T-MN-3 (byte-identical projections/metrics) | integration | G7.3 |
| 5 | Hiding visualization does not change deployment behaviour | T-VZ-4 (DB write audit: only `viz_preferences` changes; deployment keeps trading) | integration | G7.5 |
| 6 | Re-enabling restores persisted entry/exit events | T-VZ-5 | integration + Playwright | G7.5 |
| 7 | Markers match persisted fills and timestamps | T-VZ-1, T-VZ-2, T-VZ-3 | integration | G7.5 |
| 8 | Deployed strategies automatically expose required indicators | T-VZ-6, T-ST-13 | integration | G7.5 |
| 9 | Chart indicators use the right feature versions and parameters | T-VZ-7, T-FE-12 | integration | G7.5 |
| 10 | Several strategies visualized independently | T-VZ-8, T-VZ-9 | Playwright | G7.5 |
| 11 | Runner restarts do not duplicate orders or lose history | T-EV-2, T-EV-3, T-EV-8, T-DP-8, T-VZ-10, T-PP-1 | recovery | G7.1 |
| 12 | Live-only chain never shows stale/historical data as live | T-LC-1 … T-LC-8 | unit + Playwright | G2.1 |
| 13 | Backtest reports separate actual-options, underlying-directional, incomplete/synthetic | T-MI-4, T-RPT-1 (kind banner/warnings), T-RPT-2 (no cross-kind aggregate), T-RPT-3 (INCOMPLETE/SYNTHETIC labels) | unit + Playwright | G5.1 |
| 14 | Data-quality failures block unsupported backtests / unsafe new paper orders | T-DQ-4, T-DQ-5, T-DQ-6, T-RK-5/RK-17 boundary, T-MN-8 | integration | G0.10 / G7.3 |
| 15 | Ledger invariants after cancel, partial fill, restart, replay | T-AC-1…4, T-LG-5, T-LG-6, T-EV-3 | property + recovery | G7.6 |
Additional v1.2 tests defined in their sections: T-EV-* (§2.7.9), T-DQ-* (§4.4.1), T-ISO-* (§10.5), T-MN-* and T-DP-* (§8.8), T-AC-* (§8.8.4), T-SIM-15…19 (§8.4.8), T-RK-27…32 (§8.6.8–9), T-FE-11/12 (§5.1.9), T-MI-* (§8.10.5), T-ML-13…16 (§11.7.1), T-CH-1…6 (chart fidelity: IST labels, whitespace gaps, provisional style, marker snapping, memory cap, group isolation), T-LC-* (OPTIONS_CHAIN_UI.md §9), T-VZ-* (PAPER_TRADING_UI.md §9).

---

# 16. Configuration reference

## 16.1 `config/settings.yaml`
```yaml
environment: dev                       # dev | paper | live
data_dir: ./data                       # overridden by QV_DATA_DIR
database_url_env: DATABASE_URL
underlying: {id: "IDX:NIFTY50", provider_key: "NSE_INDEX|Nifty 50"}
calendar: {sessions_file: config/calendar/nse_sessions.yaml, special_file: config/calendar/special_sessions.yaml}
rules_file: config/rules/nifty_rules.yaml
semantics_file: config/data_semantics.yaml
snapshot_collector: {period_s: 30, offset_s: 3, request_timeout_s: 10, retry_offsets_s: [2, 5], start: "09:10", stop: "15:35", flush_minutes: 10, expiries: [NEAREST, NEXT], next_offset_s: 12}
live: {strike_band: 10, recenter_steps: 2, feed_stale_s: 10, option_stale_s: 30, bar_grace_s: 2, event_bus_port: 8765, futures: true, pin_open_positions: true, ws_daily_budget_mb: 500}
snapshot_available_lag_s: 5
max_snapshot_age_s: 75
gap_tolerance_bars: 2
rate_limits: {per_second: 50, per_minute: 500, per_30min: 2000, collector_budget_30min: 1200, order_per_second: 10}
reconciliation_tolerance_points: {open: 1.0, close: 1.0, high: 2.0, low: 2.0, pass_ratio: 0.99}
backtest: {execution_tf: 1m, default_seed: 20260101, bootstrap_resamples: 10000}
mode_b: {fill_model: SPOT_NEXT_OPEN, latency_s: 0, slippage_points: 0}
mode_c: {fill_model: OPT_SNAPSHOT_BIDASK, latency_s: 2, max_fill_wait_s: 75, slippage_ticks: 1, respect_top_of_book: false}
paper: {fill_model: OPT_LIVE_BIDASK, latency_ms: 500, max_wait_s: 5, slippage_ticks: 1}
strike_step: 50
risk_profile_dir: config/risk/profiles      # [v1.1] replaces risk_profile_file
default_risk_profile: paper_default
research_risk_profile: research_relaxed
costs_file: config/costs/upstox_nse_options.yaml
alerts: {email: null, telegram: null}
journal: {dir: data/journal, segment_mb: 16, fsync: every_record, retention_days: 90, poll_ms: 200, max_replay_decision_age_s: 120}
isolation: {paper_schema: qv_paper, core_schema: qv_core, live_schema: qv_live, forbid_credentials_in_paper: true}
manual_paper: {enabled: true, default_equity_paise: 2000000, profile: "manual_paper@1.0.0", command_ttl_s: 30, order_types: [MARKET, LIMIT], validity: [DAY]}
deployments: {max_active_per_account: 1, auto_resume: false, default_stop_policy: DRAIN, preflight_warmup_sessions: 3}
kill_switch: {default_action: BLOCK_ENTRIES}
viz: {default_visible_on_deploy: false}
replay: {max_sessions: 4, idle_ttl_s: 900, speeds_min_per_s: [1, 2, 5, 10, 30, 60], granularity: 1m}
live_chain: {default_band: 10, push_conflate_ms: 500, stale_quote_s: 5, stale_snapshot_s: 75}
chart: {page_bars: 5000, max_bars_in_memory: 50000}
dq_gate: {min_session_status: DEGRADED, min_snapshot_coverage_ratio: 0.85, max_excluded_session_ratio: 0.20, min_sessions: 20, require_calendar_verified: true}
fills: {mode_c_quote_fallback: REJECT, fill_max_spread_rel: 0.10, quote_max_wait_s: 5}
ml: {max_trials_per_family: 200}
```

## 16.2 `config/data_semantics.yaml` (written by Phase 0 tickets, never hand-edited without evidence)
```yaml
candles:
  timestamp_semantics: bar_open            # S1 evidence ref: tests/fixtures/upstox/hist_1m_sample.json
  index_volume_valid: null                 # set true/false by CQ-10 / S3
  index_oi_valid: null
option_snapshot_tz: null                   # set by T0.4 (IST|UTC) with evidence numbers
option_snapshot_available_lag_s: 5
iv_unit: null                              # fraction | percent (S8/OQ-09)
greeks_zero_is_sentinel: true              # S12 default; confirm
ws:
  ltt_unit: ms                             # S5
  option_volume_cumulative: null           # S6
  index_tick_rate_per_min: null            # S7
evidence: {}                               # tool-written: {key: {date, artifact_path, numbers}}
```

---

# 17. Build tickets

## 17.1 Rules for every ticket
1. Inspect the repository state before starting; list files you will change. 2. Implement only the ticket. 3. Add the tests named in the ticket. 4. Run the full test suite, `ruff`, `mypy`, `import-linter`. 5. Never modify raw data; never run legacy scripts. 6. Produce the completion report (§17.3). 7. If anything in HLD/LLD is missing or contradictory: stop and ask.

## 17.2 Ticket list (order matters; `→` = depends on)
### Phase 0 — Audit and collector hardening
| ID | Ticket | Deliverables / DoD |
|---|---|---|
| T0.1 | Archive legacy data with manifest | `scripts/archive_legacy_data.py` copies `Data/` to `data/raw/legacy_upstox/`, writes `MANIFEST.sha256`, sets read-only; verification script passes; original untouched |
| T0.2 | Calendar bootstrap | Script per §3.2 → `calendar_candidates.csv`; owner/agent resolves rows into `nse_sessions.yaml` + `special_sessions.yaml` with source URLs; `status: VERIFIED` only when every candidate is resolved (**G0.1**); tests T-INS-6 |
| T0.3 | Audit v2 | `scripts/audit_v2.py` implementing CQ-01…13 and OQ-01…18 with the calendar, tolerant folder parser, canonical counting (**recount 1m rows**; explain 432,967 vs 451,952), per-timeframe session counts, report to `data/quality/audit_v2/` (**G0.2, G0.3**); tests T-MD-2/3/4 |
| T0.4 | Option timestamp timezone | `scripts/resolve_option_tz.py` per §4.3 → `data_semantics.yaml`; test T-MD-11 (**G0.4**) |
| T0.5 | Resampler | `market_data/resample.py` + tests T-MD-6; compare derived vs native; report mismatches (**G0.5**) |
| T0.6 | Canonical conversion | Parsers (candle CSV, v1/v2/v3), schemas §4.5, Parquet writers, round-trip row counts + content hash vs raw (**G0.6**); tests T-MD-1 |
| T0.7 | Provider semantics capture | Fixtures + `data_semantics.yaml` entries for S1–S12 (requires owner token) |
| T0.8 | Collectors with scheduler | Rate limiter, token manager + `auth_login`, snapshot collector (§4.9.3), heartbeat, scheduler templates; tests T-MD-9, T-MD-12; 10 consecutive sessions ≥ 95% coverage (**G0.7**) |
| T0.9 | Quote recorder + live builder (data-only) | WS client, decode (index `ltpc`; options, near-month future and **pinned held contracts** in `full`, 5-level depth), candle builder, quote recorder, derived 1-second bars, `ws_budget` report, journal-backed event transport (§2.7, → T0.15); tests T-MD-7/8 and pinned-key tests (a held contract outside the band stays subscribed; re-centre never drops it); ≥ 5 sessions recorded (**G0.8**) |
| T0.13 | Next-expiry snapshots + futures candles | §4.9.3 `NEXT` call with fallback, §4.9.4 futures EOD candles `[VERIFY]`; tests for partitioning and `NEXT_EXPIRY_DISABLED` |
| T0.10 | Contract master archive | Daily instrument master + option contract download (verify endpoints) |
| T0.11 | Backup + restore drill | §14.3 jobs; first drill passes |
| T0.12 | Look-ahead harness | `tests/lookahead/` utilities (truncate-recompute, poisoned future) running in CI (**G0.9**) |
| T0.14 | **[v1.2]** Calendar versioning, absence reason codes, coverage matrix L1–L3, eligibility-gate library | §4.4.1; `calendar_version` in `data_version`; matrix for all history (**G0.10**); zero unexplained absences (**G0.11**); T-DQ-1…6. → T0.2, T0.3, T0.6 |
| T0.15 | **[v1.2]** Event journal, consumer-checkpoint library, crash-consistency harness | §2.7.2–2.7.4; framing/CRC/fsync/epoch repair; fault-injection layer; T-EV-1, 3, 4, 5, 6(harness), 10 (**G0.12**). T0.9 depends on this |
### Phase 1 — Skeleton and charts
| ID | Ticket | Deliverables / DoD |
|---|---|---|
| T1.0 | Repo scaffolding | Layout §1.1, `pyproject.toml` (§1.3–1.4), `AGENTS.md` (points to HLD+LLD; states the ticket rules), CI workflow, pre-commit |
| T1.1 | Shared kernel | §2 modules + tests (naive datetime rejection, paise rounding, ULIDs, clock) |
| T1.2 | Instruments + calendar + expiry rules | §3 with tests T-INS-1…6 |
| T1.3 | Repositories + DuckDB views | §4.8; tests T-MD-5 |
| T1.4 | API skeleton | health, instruments, calendar, candles, coverage, DQ status; OpenAPI committed |
| T1.5 | Frontend chart | `/chart` with adapter, lazy loading, DQ ribbon, mode banner |
| T1.6 | Postgres + Alembic baseline | §9.5 tables |
| T1.7 | **[v1.2]** Chart adapter v1.2 | §13.2: `GapBar` whitespace, IST formatter (decide formatter vs fallback shift with Vitest evidence), provisional bar style, grouped markers/levels/series, replay-cursor hook, memory cap; T-CH-1…6. → T1.5 |
| T1.8 | **[v1.2]** Schemas, roles, account/order DDL | §9.5 amended DDL, §9.5.1 triggers, §10.5 roles (`qv_paper_rw`, `qv_api`); T-ISO-3/4/5. → T1.6 |
### Phase 2 — Live data
| T2.1 | Live subsystem integration | collectors from T0.8/T0.9 under the app layout; event bus; `/ws` candle/health channels |
| T2.2 | Reconciliation + EOD pipeline | §4.11–4.12; 5 sessions within tolerance |
| T2.3 | Option-chain viewer | `/options` + snapshot APIs |
| T2.4 | **[v1.2]** Live option-chain service and screens | `GET /live/option-chain`, WS `live_option_chain` (conflated), `Cell` provenance/freshness, `/options` live-only + `/research/options` split; OPTIONS_CHAIN_UI.md; T-LC-1…8 (**G2.1**). → T0.9, T2.1, T2.3 |
### Phase 3 — Features
| T3.1 | Feature framework | §5.1 registry, naming, readiness/gap rule, parity & look-ahead harnesses |
| T3.2 | Price/trend/volatility/levels/session catalogue | §5.4.1–5.4.6 in the stated order, each with fixture + T-FE-1…7 (Appendix A fixture is mandatory for sma/ema/rsi/atr/macd/bbands) |
| T3.3 | MTF + transforms | §5.4.4, §5.4.8, T-FE-10 |
| T3.4 | Option-chain features | §5.4.9 with golden fixtures T-FE-8 |
| T3.5 | Feature API + chart overlays | `/features/*` + UI panes |
| T3.6 | *(optional)* Quote-stream features | §5.4.10 with fixtures; only after recorder data exist |
| T3.7 | *(optional, owner request)* Futures features | §5.4.11 with fixtures |
| T3.8 | **[v1.2]** Feature display/explain metadata and persisted-series schema | §5.1.9 (`display`, `explain`, `repaints`, version retention); `/features/{name}/explain`; T-FE-11/12. → T3.1, T3.5 |
| T3.9 | **[v1.2]** Replay service and UI (CHART kind) | Server-side `ReplaySession`, endpoints §12.2.1, CHARTING_UX.md §6; T-RP-1…7 (**G3.1**). → T3.5, T1.7 |
### Phase 4 — Strategies
| T4.1 | Spec schema + validator + hash | §6.1–6.2, §6.5; T-ST-1/2/9 |
| T4.2 | Evaluator + runner | §6.2.2, §6.3; T-ST-3…6 |
| T4.3 | Python interface + AST allow-list | §6.4; T-ST-8 |
| T4.4 | Reference strategies + parity gate | §6.7; T-ST-7 |
| T4.5 | Strategy UI | `/strategies` |
| T4.6 | Pine porting protocol harness | §6.9: PINE-1 parity test runner against TradingView exports, PINE-2 review checklist template, `PORT_NOTES.md` template; `setup`/`risk`/`duration_profile` spec fields; T-ST-10…12 |
| T4.7 | **[v1.2]** `required_feature_pins()` and validate response | §5.1.9; pins shown in `/strategies`; T-ST-13. → T4.1, T3.8 |
### Phase 5 — Mode B
| T5.1 | Engine core + ordering + guards | §8.1–8.2; T-SIM-1/2/8 |
| T5.2 | Mode B fills/stops | §8.3; T-SIM-4 |
| T5.3 | Metrics, bootstrap, sensitivity, manifest | §8.9–8.10; T-SIM-3 |
| T5.4 | Holdout registry + walk-forward | §8.11; T-SIM-9 |
| T5.5 | Backtest API + UI + annotations | `/backtests`; E2E test |
| T5.6 | Mode B overnight | §8.3.6; T-SIM-11/12; BTST reference spec (illustrative) + report with gap/session decomposition |
| T5.7 | **[v1.2]** Metric detail framework and inspector UI (Mode B) | §8.10.5, BACKTESTING_REPORT_SPEC.md §3–4; T-MI-1…6 (**G5.1** part 1). → T5.3, T5.5 |
| T5.8 | **[v1.2]** Report completeness | Eligibility panel, execution assumptions, kind banners, warnings, reproducibility panel, BACKTEST-kind replay; T-RPT-1…3, T-RP-8 (backtest part). → T5.5, T0.14 |
### Phase 6 — Mode C
| T6.1 | Contract selector | §7; T-SEL-* |
| T6.2 | Cost model | §8.5; T-COST-1/2 |
| T6.3 | Mode C engine | §8.4; T-SIM-5/6/7 |
| T6.4 | Coverage report + hurdle | §8.4.6, §8.12.1 |
| T6.5 | Mode S + calibration config/report | §8.12.2 (ADR-016 thresholds recorded **before** running) |
| T6.6 | Mode C overnight | §8.4.7, §8.12.3; T-SIM-13; selector rule §7.2 step 2a (T-SEL-8/9) |
| T6.7 | **[v1.2]** Fill sources and Mode C quote fill model | §8.4.8: LTP rule, `OPT_QUOTE_BIDASK`/`OPT_HYBRID`, spread-widening expiry, exit-resolution bounds; T-SIM-15…19. → T6.3, G0.8 data |
| T6.8 | **[v1.2]** Mode C metric details (₹), Sortino, risk-overshoot panel | §8.6.8, §8.10.5; T-MI-2/5 for Mode C. → T6.3, T5.7 |
### Phase 7 — Paper trading and ledger
| T7.1 | Ledger | §9; T-LG-* |
| T7.2 | Layered risk engine + account profiles | §8.6 (rule classes, effective limits, sizing, `RESEARCH_RELAXED`, validation, feasibility tool); T-RK-1…26 |
| T7.3 | Order state machine + paper adapter | §8.7, §10.2; T-OS-1, T-EX-1/2 |
| T7.4 | Paper runner + deployments + UI | §8.8; T-PP-1, T-SIM-10 |
| T7.5 | Fee reconciliation | Owner supplies ≥ 5 real contract-note trades; compare per-component; update YAML `status: VERIFIED` only if each trade total matches within ₹1 (**gate**) |
| T7.6 | Risk profiles API/UI + overnight paper | `/risk/profiles`, `/settings`, accounts with any equity; §8.8.1 overnight restore and pinned keys; T-SIM-14, T-LG-10 |
| T7.7 | **[v1.2]** Durable delivery in paper | Consumers with checkpoint-in-transaction, outbox + WS resync, `order_commands`, feed state machine, `STALE_REPLAY`; T-EV-2, 3, 7, 8, 9 (**G7.1**). → T0.15, T7.3 |
| T7.8 | **[v1.2]** Option risk semantics and priority ladder | §8.6.8–9: risk bases, RK-22, kill-switch action, supersede rules, overshoot fields; T-RK-27…32. → T7.2 |
| T7.9 | **[v1.2]** Manual paper account | §8.8.2: account kind, `manual_paper` profile (ADVISORY), MARKET+LIMIT, validation, single-writer commands, `/manual/*`, `/paper/manual` UI; PAPER_TRADING_UI.md §2–3; T-MN-1…13 (**G7.3**). → T7.1, T7.3, T7.7, T1.8 |
| T7.10 | **[v1.2]** Deployment state machine and controls | §8.8.3: states, pre-flight, DRAIN/FLATTEN, guardian, `deployment_events`; deployments UI; T-DP-1…10 (**G7.4**). → T7.4, T7.7 |
| T7.11 | **[v1.2]** Strategy visualization | `viz_preferences`, `TradeChain` API, markers/levels/indicators, marker inspector, persisted deployment series; PAPER_TRADING_UI.md §5–8; T-VZ-1…10 (**G7.5**). → T7.10, T3.8, T1.7 |
| T7.12 | **[v1.2]** Isolation controls | §10.5: env guards, credential check, import closure, fake-broker test, DB role tests; T-ISO-1, 2, 6, 7, 9, 10 (**G7.2**). → T1.8 |
| T7.13 | **[v1.2]** Accounting additions and recovery drills | §9.3.1, §8.8.4, §14.3.1: charge adjustments, corrections, lot/tick persisted, restore + pull-the-plug drills; T-AC-1…4, T-LG-11…13 (**G7.6**). → T7.1, T7.7 |
### Phase 8 — ML (after Phase 5)
| T8.1 | Dataset + labels + uniqueness weights | §11.2–11.3; T-ML-1/6 |
| T8.2 | Walk-forward CV with purge | §11.4; T-ML-2 |
| T8.3 | Baselines + LightGBM + calibration | §11.5; T-ML-3/4 |
| T8.4 | Evaluation through Mode B + promotion command | §11.6–11.8 |
| T8.5 | Registry + predictor + latency test | §11.7, §11.9; T-ML-5 |
| T8.6 | Label registry + roles | §11.1, §11.3.1; T-ML-7/9/10 |
| T8.7 | Strategy-specific dataset builder | §11.11; T-ML-8/12 |
| T8.8 | Experiment and holdout lifecycle guard | §11.12; T-ML-11 |
| T8.9 | **[v1.2]** Experiment completeness | §11.7.1: failed runs, spec edits as trials, rule-based purge, reproducibility record; T-ML-13…16. → T8.8, T5.4 |
### Phase 9 — Live (only after owner approval; not scheduled)
| T9.1 | Readiness checklist + regulatory verification | Owner-signed file |
| T9.2 | Upstox adapter | §10.3; T-EX-3 |
| T9.3 | **[v1.2]** Three-lock arming and database-isolation review | §10.5 locks (1)–(3); decide separate database for live; T-ISO-8. → T9.2 |

## 17.3 Completion report (required at the end of every ticket)
```markdown
### Ticket <ID> — <title>
**Changed:** files + one-line reason each
**Requirements covered:** HLD/LLD sections and test IDs
**Tests run:** exact commands and results (pass/fail counts); tests NOT run and why
**Gate status:** list every gate item touched → PASS / FAIL / NOT RUN, each with an artifact path
**Data/schema migrations:** none | description + rollback
**Known limitations / assumptions:** …
**Open questions for the owner:** …
**Next safe ticket:** <ID>
```
An agent must not mark a gate item PASS without an artifact.

## 17.4 `AGENTS.md` (required content, ≤ 40 lines)
Read `docs/HIGH_LEVEL_DESIGN.md` and `docs/LOW_LEVEL_DESIGN.md` before any work; work one ticket at a time; never edit raw data or run `legacy/` scripts; never import broker SDKs outside `execution/upstox`, `apps`, `api`; never invent numbers missing from the LLD — stop and ask; always add tests with the IDs named in the ticket; produce the completion report; live trading stays disabled.

---

# Appendix A — Hand-checkable indicator fixture (mandatory for T-FE-1)
Bars (20, `i = 0…19`), values below produced by independent reference implementations of §5.4 (SMA, EMA, Wilder RSI/ATR, population-std Bollinger, MACD(3,6,3) with SMA-seeded EMAs). Tests compare to these at `rtol = 1e-6`. Parameters: `sma n=5`, `ema n=5`, `rsi n=5`, `atr n=5`, `bbands n=5 k=2.0`, `macd fast=3 slow=6 signal=3`. "—" = not ready (NaN).

| i | open | high | low | close | sma_close_5 | ema_close_5 | rsi_5_close | tr | atr_5 | bb_mid | bb_upper | bb_lower | macd(3,6,3) | signal | hist |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 100.0 | 101.5 | 99.5 | 101.0 | — | — | — | 2.00 | — | — | — | — | — | — | — |
| 1 | 101.0 | 102.5 | 100.5 | 102.0 | — | — | — | 2.00 | — | — | — | — | — | — | — |
| 2 | 102.5 | 103.0 | 101.0 | 101.5 | — | — | — | 2.00 | — | — | — | — | — | — | — |
| 3 | 101.5 | 103.5 | 100.5 | 103.0 | — | — | — | 3.00 | — | — | — | — | — | — | — |
| 4 | 103.0 | 104.5 | 102.5 | 104.0 | 102.3000 | 102.3000 | — | 2.00 | 2.2000 | 102.3000 | 104.4541 | 100.1459 | — | — | — |
| 5 | 104.5 | 105.0 | 103.5 | 103.5 | 102.8000 | 102.7000 | 77.778 | 1.50 | 2.0600 | 102.8000 | 104.6547 | 100.9453 | 0.8125 | — | — |
| 6 | 103.5 | 104.5 | 102.0 | 102.0 | 102.8000 | 102.4667 | 54.902 | 2.50 | 2.1480 | 102.8000 | 104.6547 | 100.9453 | 0.2991 | — | — |
| 7 | 102.0 | 103.5 | 101.5 | 103.0 | 103.1000 | 102.6444 | 63.780 | 2.00 | 2.1184 | 103.1000 | 104.4266 | 101.7734 | 0.2873 | 0.4663 | -0.1790 |
| 8 | 103.0 | 105.0 | 102.5 | 105.0 | 103.5000 | 103.4296 | 75.726 | 2.50 | 2.1947 | 103.5000 | 105.5000 | 101.5000 | 0.6706 | 0.5685 | 0.1022 |
| 9 | 105.0 | 106.5 | 104.5 | 106.0 | 103.9000 | 104.2864 | 79.874 | 2.00 | 2.1558 | 103.9000 | 106.7566 | 101.0434 | 0.9260 | 0.7472 | 0.1788 |
| 10 | 106.5 | 107.0 | 105.0 | 105.5 | 104.3000 | 104.6909 | 72.166 | 2.00 | 2.1246 | 104.3000 | 107.3725 | 101.2275 | 0.7778 | 0.7625 | 0.0153 |
| 11 | 105.5 | 106.5 | 104.0 | 104.0 | 104.7000 | 104.4606 | 52.989 | 2.50 | 2.1997 | 104.7000 | 106.8541 | 102.5459 | 0.2923 | 0.5274 | -0.2351 |
| 12 | 104.0 | 105.5 | 103.5 | 104.5 | 105.0000 | 104.4738 | 57.675 | 2.00 | 2.1598 | 105.0000 | 106.4142 | 103.5858 | 0.1843 | 0.3559 | -0.1716 |
| 13 | 104.5 | 106.0 | 103.5 | 106.0 | 105.2000 | 104.9825 | 69.192 | 2.50 | 2.2278 | 105.2000 | 106.8248 | 103.5752 | 0.4408 | 0.3983 | 0.0425 |
| 14 | 106.0 | 107.5 | 105.5 | 107.0 | 105.4000 | 105.6550 | 74.886 | 2.00 | 2.1822 | 105.4000 | 107.5354 | 103.2646 | 0.6838 | 0.5411 | 0.1427 |
| 15 | 107.5 | 108.0 | 106.5 | 106.5 | 105.6000 | 105.9367 | 67.131 | 1.50 | 2.0458 | 105.6000 | 107.9152 | 103.2848 | 0.5657 | 0.5534 | 0.0123 |
| 16 | 106.5 | 107.5 | 105.0 | 105.0 | 105.8000 | 105.6244 | 48.353 | 2.50 | 2.1366 | 105.8000 | 107.6547 | 103.9453 | 0.1213 | 0.3373 | -0.2160 |
| 17 | 105.0 | 106.5 | 104.5 | 106.0 | 106.1000 | 105.7496 | 58.116 | 2.00 | 2.1093 | 106.1000 | 107.4266 | 104.7734 | 0.1595 | 0.2484 | -0.0889 |
| 18 | 106.0 | 108.0 | 105.5 | 108.0 | 106.5000 | 106.4998 | 71.558 | 2.50 | 2.1874 | 106.5000 | 108.5000 | 104.5000 | 0.5790 | 0.4137 | 0.1653 |
| 19 | 108.0 | 109.0 | 107.0 | 108.5 | 106.8000 | 107.1665 | 74.150 | 2.00 | 2.1500 | 106.8000 | 109.3768 | 104.2232 | 0.7532 | 0.5835 | 0.1698 |

Fixture notes: `tr` at `i = 0` is `high − low`; ATR seed at `i = 4` is the mean of the first five TR values (= 2.2000); RSI first value at `i = 5` uses the first five deltas; MACD first value at `i = 5` (slow EMA 6 seeds at `i = 5`); signal seeds at `i = 7` as the mean of macd at `i = 5, 6, 7`. Save the table as `tests/fixtures/features/ref_20bars.csv` plus an `expected.csv` with these outputs at 6-decimal precision (regenerate with the reference script in `scripts/fixtures/make_ref_fixture.py`, which must implement the §5.4 formulas independently of production code).

# Appendix B — Quick reference of defaults (all **[OWNER]** unless noted)
| Parameter | Default | Section |
|---|---|---|
| Snapshot period / grid | 30 s, offset 3 s | 4.9.3 |
| `snapshot_available_lag_s` | 5 | 4.3 |
| `max_snapshot_age_s` | 75 | 5.4.9, 7 |
| `gap_tolerance_bars` | 2 | 5.1.4 |
| Strike step / band | 50 / ±10 strikes | 3.4, 5.4.9 |
| Mode B fill / slippage grid | `SPOT_NEXT_OPEN` + `SPOT_NEXT_CLOSE`; 0,1,2,3 pts | 8.3 |
| Mode C latency / wait / slippage | 2 s / 75 s / 1 tick | 8.4.2 |
| Force-flat time (INTRADAY only) | 15:15 IST | 8.6.4 |
| Entry windows INTRADAY / OVERNIGHT | 09:20–15:00 / 09:20–15:25 | 8.6.4 |
| BTST exit | `time_exit` 09:15, `exit_session_offset` 1 | 6.2, 8.3.6 |
| Overnight exit max wait (Mode C) | 600 s, then `LATE_OPEN_EXIT` until 10:30 | 8.4.7 |
| Starting paper equity | any amount per account; ₹20,000 in `paper_default`; ₹5,00,000 in `research_relaxed` | 8.6.4 |
| Max lots / outlay / risk per trade | 2 / 60% / 5% (account ceilings; strategies may only tighten) | 8.6.2–8.6.3 |
| Daily loss limit / max drawdown | 10% / 25% | 8.6.2 |
| Bootstrap | 10,000 day-block resamples, seed 20260101 | 8.10.3 |
| ML label | triple barrier k=1.0·ATR14, H=60 min | 11.3 |
| ML walk-forward / holdout | 8 quarterly folds 2024-01 → 2025-12; holdout 2026-01 → freeze date; ≤ 3 holdout looks per experiment family | 11.4, 11.12 |
| Reconciliation tolerance | O/C 1.0, H/L 2.0 points, 99% bars | 4.11 |
| Journal fsync / segment / retention | every record / 16 MB / 90 days | 2.7.3 |
| Max replay decision age | 120 s (entries blocked as `STALE_REPLAY`) | 2.7.4 |
| Manual command TTL / runner heartbeat limit | 30 s / 15 s | 8.8.2 |
| Overnight risk basis | `WORST_CASE_OUTLAY` (owner decision D-06) | 8.6.8 |
| Fill max spread / quote max wait | 0.10 / 5 s | 8.4.8 |
| Live chain conflation / stale quote / stale snapshot | 500 ms / 5 s / 75 s | 12.3, OPTIONS_CHAIN_UI |
| DQ gate | DEGRADED, coverage ≥ 0.85, excluded ≤ 20%, ≥ 20 sessions | 4.4.1 |
| Chart page / memory cap | 5 000 / 50 000 bars | 13.2 |

---

# Appendix C — Status vocabulary and v1.2 gate register
| Status | Meaning (a feature moves only forward, only with the named evidence) |
|---|---|
| `DESIGNED` | Specified in HLD/LLD with tests named. **Nothing else is implied.** |
| `IMPLEMENTED` | Code merged under a ticket with a completion report (§17.3). Not a claim that it works. |
| `TESTED` | The named tests exist and passed in CI; the log/artifact path is recorded. |
| `VERIFIED` | Checked against reality: a recorded live/paper session or real data, reviewed and signed by the owner; artifact path recorded. |
This review changed documents only and did not inspect the repository, so **no v1.2 requirement is IMPLEMENTED, TESTED or VERIFIED**. All rows below are `PENDING`.
| Gate | Evidence required | Status |
|---|---|---|
| G0.10 Coverage matrix L1–L3 for all history | `data/quality/coverage_matrix/` + report | PENDING |
| G0.11 Zero unexplained absences | reason-code audit report | PENDING |
| G0.12 Journal crash/duplicate/gap tests | T-EV-1, 3, 4, 5, 6 (harness), 10 logs | PENDING |
| G1.1 Chart fidelity | T-CH-1…6 + Playwright log | PENDING |
| G2.1 Live chain truthfulness | T-LC-1…8 + a recorded live session screenshot set reviewed by owner (VERIFIED) | PENDING |
| G3.1 Replay leak-proofing | T-RP-1…7 | PENDING |
| G5.1 Metric inspector and report kinds | T-MI-1…6, T-RPT-1…3 | PENDING |
| G6.1 Quote fills | T-SIM-15…19 | PENDING |
| G7.1 Restart safety | T-EV-2, 3, 7, 8, 9; T-DP-8; T-PP-1 | PENDING |
| G7.2 Paper/live isolation | T-ISO-1…10 | PENDING |
| G7.3 Manual account independence | T-MN-1…13 | PENDING |
| G7.4 Deployment controls | T-DP-1…10 | PENDING |
| G7.5 Strategy visualization | T-VZ-1…10, T-ST-13, T-FE-12 | PENDING |
| G7.6 Accounting and recovery | T-AC-1…4, T-LG-11…13, T-EV-6 + pull-the-plug drill artifact | PENDING |
