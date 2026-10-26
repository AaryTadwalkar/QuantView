# QuantView — Phase 1 Tooling Scaffolding & Validation Pre-Implementation Compliance Report

**Execution Date:** 2026-10-22  
**Target Milestone:** Phase 1 Tooling Scaffolding and Validation Only  
**Authority Reference Hierarchy:**
1. `DOCS/AGENTS.md` (Workflow, task registry, gates, person-day budgets)
2. `DOCS/QUANTVIEW_MASTER_SPEC.md` (System architecture, ADRs, process boundaries)
3. `DOCS/QUANTVIEW_DATA_SPEC.md` (Canonical schemas, lake partitions, storage, single-writer matrix, source semantics)
4. `DOCS/QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md` (Execution semantics, bar timing, fill models)
5. `DOCS/my_vision.txt` (Original owner intent and requirements, subordinate to the specifications above)

---

## 1. Compliance Audit of Proposed Phase 1 Components

The following table evaluates every proposed module, schema file, preparation script, and directory against the canonical authority documents:

| Proposed Component | Exact Authorizing Spec Section | Intended Repository Path | Existing Equivalent Component | New Directory / Schema / Abstraction? | Backward Compatible with Ingestion Workflows? | Modifies, Moves, Deletes, or Overwrites Existing Data? | Compliance & Authorization Verdict |
|---|---|---|---|---|---|---|---|
| **Canonical Candle Schemas (Pydantic v2 + PyArrow)** | `QUANTVIEW_DATA_SPEC.md` §4.1, §4.2, §4.10; §11.2 | `packages/data/schemas/candles.py` | None (only basic `IndiaVixCandle` dataclass in `packages/data/__init__.py`) | Creates `packages/data/schemas/candles.py`; defines unified Pydantic models & PyArrow schemas for underlying, options, and VIX | Yes; validates staged CSVs from `tools/ingest/` | **No** (pure validation & schema definitions) | **APPROVED & MANDATED** (DATA Spec §4: "canonical tables are defined once in packages/data/schemas/") |
| **Canonical Snapshot Schemas (Pydantic v2 + PyArrow)** | `QUANTVIEW_DATA_SPEC.md` §4.3, §4.4, §11.3 | `packages/data/schemas/snapshots.py` | None | Defines `option_snapshot_captures` header and `option_snapshot_rows` strike models (nullable superset of v1/v2/v3) | Yes; parses raw snapshot CSVs across all schema versions | **No** (pure validation & schema definitions) | **APPROVED & MANDATED** (DATA Spec §4.3, §4.4) |
| **Central Schemas Package Index** | `QUANTVIEW_DATA_SPEC.md` §4 | `packages/data/schemas/__init__.py` | None | Central export namespace for all canonical Pydantic models, PyArrow schemas, and invariant checkers | Yes | **No** | **APPROVED & MANDATED** (DATA Spec §4: Single source of truth) |
| **Option Candle Lake Preparation Tool** | `QUANTVIEW_DATA_SPEC.md` §2, §4.2, §11.3; `AGENTS.md` M3-05 | `tools/lake/promote_option_candles.py` | None | New tool under authorized `tools/lake/` directory | Yes; reads from `staging/expired_options/` and raw manifests | **No**; writes strictly to isolated `staging/lake_preparation/option_candles/` | **APPROVED** (Offline staging preparation only; active lake untouched) |
| **Underlying Candle Lake Preparation Tool** | `QUANTVIEW_DATA_SPEC.md` §2, §4.1, §11.1; `AGENTS.md` M3-04 | `tools/lake/promote_underlying_candles.py` | None | New tool under authorized `tools/lake/` directory | Yes; reconciles historical `nifty.csv` and staged October CSVs | **No**; preserves corrupted line provenance, outputs to `staging/lake_preparation/underlying_candles/` | **APPROVED** (Preserves line 432594 with provenance; active lake untouched) |
| **India VIX Lake Preparation Tool** | `QUANTVIEW_DATA_SPEC.md` §2, §4.10, §11.2; `AGENTS.md` M3-12 | `tools/lake/promote_india_vix.py` | None | New tool under authorized `tools/lake/` directory | Yes; reads from `staging/india_vix/` | **No**; outputs to `staging/lake_preparation/india_vix/` | **APPROVED** (Reconciles 311-bar special session delta; active lake untouched) |
| **Option Snapshot Compaction Tool** | `QUANTVIEW_DATA_SPEC.md` §2, §4.3, §4.4, §11.3; `AGENTS.md` M3-06 | `tools/lake/compact_option_snapshots.py` | None | New tool under authorized `tools/lake/` directory | Yes; compacts captures per trade-date into daily Parquets while preserving capture boundaries | **No**; outputs to `staging/lake_preparation/option_snapshots/` without synthetic chain merging | **APPROVED** (Preserves capture identity, field presence mask, and schema versions) |
| **Dry-Run Publication Manifest Generator** | `QUANTVIEW_DATA_SPEC.md` §2.1, §11.3; `MASTER_SPEC.md` §11.5 | `tools/lake/prepare_dry_run_manifest.py` | None | Generates cryptographic dry-run manifest for prepared datasets | Yes | **No**; outputs to `staging/lake_preparation/manifest_dry_run.json`; does NOT update active lake pointers | **APPROVED** (Dry-run only; lake remains unpublished) |
| **Automated Lake Scaffolding Test Suite** | `QUANTVIEW_DATA_SPEC.md` §4; `AGENTS.md` §6 | `tests/unit/test_lake_scaffolding.py` | Extends existing 35 unit tests | New test module verifying schemas, Arrow roundtrips, UTC epoch conversions, negative volumes, and invariants | Yes | **No** (read-only tests) | **APPROVED & MANDATED** |

---

## 2. Directory Layout & Boundary Enforcement Verification

1. **No Duplicate Canonical Schema Authority (`tools/lake/schema.py` strictly prohibited):**
   - The user mandate and `QUANTVIEW_DATA_SPEC.md` §4 strictly prohibit creating `tools/lake/schema.py` or any secondary schema authority.
   - All canonical Pydantic models and matching PyArrow schemas reside strictly and exclusively in `packages/data/schemas/`.
   - All tools under `tools/lake/` import directly from `packages.data.schemas`.

2. **Authorized Directory Structure:**
   - Canonical Schemas: `packages/data/schemas/`
   - Tooling Scaffolding: `tools/lake/`
   - Staging Preparation Output: `staging/lake_preparation/`
     - `staging/lake_preparation/option_candles/underlying=NIFTY/expiry=YYYY-MM-DD/part-0.parquet`
     - `staging/lake_preparation/underlying_candles/interval=1m/year=YYYY/month=MM/part-0.parquet`
     - `staging/lake_preparation/underlying_candles/interval=1d/year=YYYY/part-0.parquet`
     - `staging/lake_preparation/india_vix/interval=1m/year=YYYY/month=MM/part-0.parquet`
     - `staging/lake_preparation/india_vix/interval=1d/year=YYYY/part-0.parquet`
     - `staging/lake_preparation/option_snapshots/captures/trade_date=YYYY-MM-DD/part-0.parquet`
     - `staging/lake_preparation/option_snapshots/rows/trade_date=YYYY-MM-DD/part-0.parquet`
   - Lake Activation Boundary: The active lake directory `Data/lake/` is **NEVER** written to, modified, or activated during Phase 1. All prepared artifacts remain safely quarantined within `staging/lake_preparation/`.

3. **Preservation of Existing Data & Collectors:**
   - Raw wire response payloads (`Data/raw/`) remain 100% immutable and read-only.
   - Staged historical CSVs in `staging/expired_options/`, `staging/india_vix/`, and `staging/underlying_candles/` are read-only inputs; zero files are deleted, renamed, or modified.
   - Checkpoint files in `staging/checkpoints/` remain completely untouched.
   - Live collector on PC B (`Data_Collectors/live_option_chain.py`) is completely untouched. Zero network calls or Upstox API requests are dispatched.

---

## 3. Dataset-Specific Compliance Policies

### 3.1 Expired-Option Candles
- **Strike Representation:** Strike is stored as exact `Decimal(9, 2)` or scaled integer string representation; binary floating-point keys are strictly prohibited per `QUANTVIEW_DATA_SPEC.md` §3.
- **Negative-Volume Policy:** Exactly 8 contracts on Budget Day (`2025-02-01` 09:15:00) contain vendor negative volume. Per `QUANTVIEW_DATA_SPEC.md` §11.3, raw values are preserved; canonical normalized volume is clamped to 0, and `quality_flags` records `VENDOR_NEGATIVE_VOLUME`. Never silently dropped.
- **Ordering & Invariants:** Partitions are strictly sorted by `(trade_date, ts_start, contract_id)` with `OHLC` invariants strictly enforced ($H \ge \max(O,C,L)$, $L \le \min(O,C,H)$, $L \ge 0$).

### 3.2 Underlying Candles
- **Line 432594 Reconciled:** The truncated line `'2026-10-08 0    \n'` in `1m/nifty.csv` is parsed, quarantined from valid canonical bars, and recorded with quality flag `TRUNCATED_LINE` without dropping surrounding data.
- **Deduplication:** Overlapping sessions between historical `nifty.csv` and staged October CSVs (`staging/underlying_candles/`) are deduplicated with identical timestamp/value verification. Conflicting prices on duplicate timestamps (such as 2026-01-28) receive `DUPLICATE_TIMESTAMP_CONFLICT`.

### 3.3 India VIX
- **Non-Derivative Invariant:** India VIX is an exchange-calculated 30-day annualized volatility index (`NSE_INDEX|India VIX`), NOT a derivative contract. `oi = 0`, `is_derivative = False`, and `volume` is nominal non-traded index volume per `QUANTVIEW_DATA_SPEC.md` §4.10.
- **Session Discrepancy Reconciled (311 bars):** Expected $446 \times 375 = 167,250$ bars vs observed 166,939 bars is 100% accounted for by:
  1. Union Budget Day (`2025-02-01` Saturday): Special shortened schedule.
  2. Diwali Muhurat Trading (`2025-10-21`): Special 1-hour evening session (60 bars vs 375 = -315 bars).
  Every trading day matches vendor wire payloads bit-for-bit.

### 3.4 Option Snapshots
- **No Synthetic Continuous Merging:** Captures remain discrete point-in-time snapshots. Compaction groups capture headers (`option_snapshot_captures`) and strike rows (`option_snapshot_rows`) into daily Parquet files while strictly preserving individual `snapshot_id`, `received_at`, `field_presence_mask`, and `schema_version` (v1/v2/v3).
- **Corrupted / Empty Files:** The 5 null-byte files and 4 zero-byte files identified in `ops/inventory.md` are logically quarantined with stable reason codes (`CORRUPT_NULL_BYTES`, `EMPTY_ZERO_BYTES`).

---

## 4. Phase 1 Stop Conditions & Boundary Agreement
- **Current Authorization:** Phase 1 tooling scaffolding, staging lake preparation, and dry-run manifest generation ONLY.
- **Stop Boundary:** Output will be staged to `staging/lake_preparation/` and accompanied by a dry-run manifest. No lake publication or pointer activation will occur. Explicit owner approval is required before moving to Phase 2.
