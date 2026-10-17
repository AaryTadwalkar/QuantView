# QuantView Docs — Full Analysis & Improvement Prompt
*My independent review of the four DOCS files against my_vision.txt, plus assessment of the other AI's review, and a final improvement prompt.*

---

## Part 1 — My Independent Analysis

### 1.1 Overall Assessment

The four files together form a **solid, unusually rigorous** architectural foundation. They are far better than typical "let's start coding" docs. The architecture is coherent, the ADRs are well-reasoned, and the task backlog in AGENTS.md is genuinely detailed. **The other AI's review is largely correct but overweights minor style issues and misses a few real gaps.** My independent verdict:

| Quality | Score | Rationale |
|---|---|---|
| Vision alignment | 8/10 | Core vision covered; 4-5 features partially/unaddressed |
| Architectural completeness | 7.5/10 | Missing: no concrete DB schema outline, no API request/response payloads |
| Agent-executeability | 7/10 | Task contracts are good; M0 acceptance conditions are still weak |
| Technical correctness | 8.5/10 | DSR formula is now present and well-specified (§20.2.1); minor issue |
| Duplication/drift risk | 6/10 | Writer matrix and phase/gate definitions exist in multiple places |

---

### 1.2 Vision Coverage — Detailed Alignment Table

| Vision Item | Vision Reference | Doc Coverage | Gap/Issue |
|---|---|---|---|
| Dashboard | vision #1 | ENGINE §18.1, M6-08 | ✅ Covered |
| Interactive chart (candlestick, time/price axes) | vision #2 | ENGINE §18.1, §18.3, M6-03 | ✅ Covered |
| Indicators + custom (Pine→Python) | vision 2A | ENGINE §9, §21, M5-03, M5-06, M5-07, M5-08 | ✅ Covered well |
| Multiple chart types (HA, Renko) | vision 2B | ENGINE §22, M5-09 | ✅ HA covered; Renko spec exists but deferred |
| Drawing tools (lines, boxes) | vision 2C | UI-2/UI-3 tiers | ⚠️ Basic drawings in UI-2, advanced in UI-3; no task for per-drawing persistence schema |
| Multi-chart layouts | vision 2D | UI-3 | ⚠️ Deferred, noted as committed for v1.1 |
| Per-strike option chart | vision 2E | UI-1 spec, M6-03 | ⚠️ UI-1 says "per-strike option chart" but no dedicated task; M6-03 covers chart+overlays generically |
| Option chain panel (live broker-like) | vision 2F | UI-3, ENGINE §18.1 | ⚠️ Deferred to v1.1 with API contract stub |
| OI levels separate tabs + overlay | vision 2G | UI-3 | ⚠️ Deferred but acknowledged |
| Timeline bottom / price vertical axis | vision 2H | ENGINE §18.3 | ✅ Covered |
| Same-page backtest results (TradingView style) | vision 2I | ENGINE §18.1, M6-09 | ✅ Covered |
| Drag SL/TP on chart | vision 2J | ENGINE §18.3, M7-08 | ✅ Covered |
| Backtest terminal (date range, CE/PE/both) | vision 3A-3D | ENGINE §19, §18.1, M4-18, M6-07, M6-09 | ✅ Covered; RunConfig §19 is thorough |
| No lookahead bias (close → next open fill) | vision step 4 | ENGINE §4, §89-90 | ✅ Covered, and the open question answered: "close-based signal fills at next bar open" |
| Ledger per backtest run | vision step 5 | ENGINE §8, M4-07 | ✅ Covered |
| SL/TP/trailing in backtest | vision step 6 | ENGINE §4, §6, M4-05 | ✅ Covered |
| Post-backtest metrics | vision step 7 | ENGINE §20, M4-15 | ✅ Covered well |
| Risk module (max trades, daily loss, drawdown, cooldown, kill switch) | vision risk | ENGINE §7, M4-05 | ✅ Covered — all controls listed |
| Signal→risk placement between steps 2-4 | vision step 2-4 Q | ENGINE §4 step 3 | ✅ Answered: risk runs pre-trade after intent, pre-fill |
| Ledger (immutable, all event types) | vision ledger | ENGINE §8 | ✅ Covered |
| Accounts (isolated paper environments) | vision accounts | ENGINE §8.2, M6-06 | ✅ Covered |
| ML: price prediction | vision ML 1 | ENGINE §23 R1 | ✅ Research baseline |
| ML: regime classification | vision ML 2 | ENGINE §23 R1 | ✅ Research baseline |
| ML: strategy meta-label (win/loss) | vision ML 3 | ENGINE §23 R1 | ✅ Research baseline |
| ML: option chain/tick pattern discovery | vision ML 4 | ENGINE §23 R2 | ✅ Covered with WS fixture gate |
| ML: chart/candlestick pattern discovery → indicator | vision ML 5 | ENGINE §23 R3 | ✅ Covered via frozen model contract |
| BOS/CHoCH indicators | vision 2A/B | ENGINE §3.3/§7, M5-06 | ⚠️ `pivot_time`/`confirmed_at` specified; no algorithm detail (pivot length rule, break rule) |
| PCR, OI ROC, delta bands | vision D option chain | ENGINE §21.1, M5-03 | ⚠️ Formula table in §21.1 is good; M5-03 task says "PCR/OI" only; MACD, Bollinger, VWAP, Supertrend, ADX have formulas in §21 but no dedicated implementation task beyond M5-08 |
| Feature settings modifiable from UI | vision features Q | ENGINE §18.1 (indicator controls/settings dialogs), M6-09 | ✅ Schema-driven forms specified |
| Compute vs store features decision | vision features Q | ADR-007, ENGINE §3.2 | ✅ On-demand first, cache only if benchmark justifies |
| Skip already-computed features | vision step skip | ENGINE §3.2 (content-addressed partitions) | ✅ Covered via cache partition key |
| WebSocket research (what do we get?) | vision data Q | DATA §4.5, ENGINE §10 | ⚠️ Deferred to fixtures+VERIFY; no speculative field list |
| DB design for backtesting | vision data Q | ADR-002, DATA §2-4 | ⚠️ Directory layout + Parquet schema specified; no Postgres DDL outline |
| Snapshot merging design | vision data Q | DATA §11.3 | ✅ No merging; daily compaction only; clear |
| india_vix, nifty_futures datasets | (implied by Greeks) | DATA §11.2 | ✅ Listed in required additional datasets |
| rates_dividends for model Greeks | (implied) | DATA §11.2, DATA §2 | ✅ Listed |
| Signal timing (close → next bar open answer) | vision step 4 Q | ENGINE §4 lines 88-90 | ✅ Answered explicitly |

---

### 1.3 Real Gaps I Identify (P0 = blocker for agent)

#### P0-1: MASTER_SPEC is ADR register, not architecture document

The other AI reviewer is correct here. `QUANTVIEW_MASTER_SPEC.md` has no:
- Component boundary diagram or prose equivalent
- Data-flow description (e.g., collector → FrameBus → live_daemon → strategy host)
- Failure domain description
- End-to-end request lifecycle (e.g., UI click → API → worker → Parquet → response)

ENGINE §1 has the package tree but no data-flow narrative. An agent implementing M1 needs this.

#### P0-2: M0 acceptance conditions are tautological or unexecutable

- **M0-10 check:** `assert 'Required evidence report' in p.read_text()` — this string does NOT appear in the current AGENTS.md. The check will fail immediately. The correct string appears to be "Required evidence" but the exact phrase should match actual content.
- **M0-01:** "refine this acceptance contract before any collector-touching implementation" — this means M0-01 has no actual acceptance contract now; an agent cannot pass it.
- **M0 tasks all say:** "Pre-inventory safe acceptance only" — meaning the actual acceptance is deferred, but there's no placeholder that tells the agent what gate it's waiting on.

#### P0-3: No dedicated task for per-strike chart (UI-1 requirement)

Vision 2E and UI-1 spec both say "per-strike option chart with trade markers" is a UI-1 deliverable. M6-03 covers "Candle chart, overlays and trade markers" generically. There is no task that explicitly builds the per-strike chart view (strike selector, expiry selector, option candle series). This could get absorbed into M6-03 but the contract doesn't say so.

#### P0-4: MACD, Bollinger, VWAP, Supertrend, ADX have formulas but no implementation task

ENGINE §21 specifies these formulas, and M5-08 says "Document formula... for SMA, EMA, RSI, MACD, ATR, Bollinger Bands, session VWAP, Supertrend and ADX" — but M5-08's acceptance contract says `owner_attestation`, meaning it only documents the formula catalogue with owner approval. There is no task that says `implement MACD`, `implement Bollinger`, etc. Only EMA, RSI, ATR and PCR/OI have an implementation task (M5-03). An agent will not implement MACD/VWAP/Supertrend/ADX/Bollinger automatically.

#### P0-5: BOS/CHoCH algorithm is underspecified

ENGINE §3.3 mentions `pivot_time` and `confirmed_at` but gives no algorithm. Vision says "BOS / CHoCH" indicators on the chart. The agent needs:
- Pivot length parameter (N bars left/right)
- Break rule (close through pivot high/low? or just touch?)
- CHoCH rule (break of last swing low after a HH series, etc.)

M5-06 acceptance says "Pivot/structure events and one reviewed Pine-to-Python conversion" — but if there's no algorithm, the agent has nothing to convert. This is an underspecified input task.

#### P0-6: No drawings persistence schema

UI-2 says "basic horizontal line and rectangle drawings" but there is no schema for how drawings are stored. Where do they go? Postgres table? What columns? What versioning? The chain: `GET /charts/drawings` endpoint exists in the endpoint list but no payload schema.

#### P0-7: Gate G2a membership check is ambiguous

AGENTS.md §5 says G2a blocks "Baseline single-leg paper runtime." M5-10 depends on M8-01, M8-01 depends on G1 and G3. The other AI raises a cycle concern (M5-10 → M8-01 → G3 which could include all of M5). Looking at the actual deps:
- M5-10 depends on `M5-01` and `M8-01`
- M8-01 depends on `G1, G3`
- G3 gates features but M5-10 is in M5 (features milestone)

The cycle is real: M5-10 (frozen model contract) depends on M8-01 (chronological dataset), which depends on G3 (features gate), but G3 contains M5 tasks including M5-10. The agent will get stuck.

---

### 1.4 P1 Issues (Wrong or Weak, Not Blockers)

#### P1-1: DSR formula — FIXED in this version

The other AI said the formula was wrong. It is now correct in ENGINE §20.2.1. The formula, `Var(SR)` using `(T-1)` and the `SR_expected_max` with Euler-Mascheroni constant, matches Bailey/López de Prado. The other AI's concern is resolved. The remaining valid concern: the doc should clarify that each slippage sensitivity scenario (0x/1x/2x/3x) is NOT counted as a separate trial for DSR purposes — it's the same hypothesis evaluated under different assumptions.

#### P1-2: Duplicated content

- **Writer matrix** appears in both `MASTER_SPEC ADR-016` and `DATA §11.5` — these are identical. One must be designated authoritative (DATA §11.5 is more detailed and correct); the MASTER one should be a pointer.
- **VERIFY register** appears in `ENGINE §16` and `AGENTS §9` — the ENGINE one is the more structured one; AGENTS should reference it.
- **Phase/gate definitions** appear in both `ENGINE §15` and `AGENTS §5` — ENGINE §15 has phases 0a through G6; AGENTS §5 has the gate table. They overlap but don't duplicate exactly. Still a drift risk.
- **"Status: DESIGN SPECIFICATION"** appears 4 times in ENGINE as concatenation artifact headers.
- **Source-semantics table** appears in `DATA §8` (partial) and `DATA §11` (full authoritative version) — the §8 version should be a reference to §11.

#### P1-3: RunConfig field list incomplete (the other AI is right)

ENGINE §19 lists required fields but is missing:
- `max_stale_minutes` (mentioned in fill table §4 and §7 but not in RunConfig schema)
- `order_expiry_bars` (N eligible bars before an order expires — mentioned in §4 but not RunConfig)
- `intrabar_stop_policy` (stop-first is default, but optimistic sensitivity mode is mentioned — where does the user set this?)
- `risk_free_rate` source/assumption (used in Sharpe/DSR; RunConfig says "risk-free assumption" but no field name)
- `vix_filter` is listed in §7 controls but not in RunConfig §19

#### P1-4: DATA §9.1 cross-reference

DATA §9.1 says: "Production host and process ownership are authoritative in `QUANTVIEW_MASTER_SPEC.md` ADR-001." It should say ADR-015 (host/sync). ADR-001 is product scope. This is a stale pointer.

#### P1-5: M4 task ordering is scrambled

M4-13 (prepare G2a golden expectations) precedes M4-02 (golden event-loop sign-off), but M4-13's ID is higher. Then M4-15 (metrics manifest) is between M4-14 and M4-16. The numeric ordering doesn't reflect dependency order, confusing for sequential reading. Not a blocker since `depends_on` is specified, but it will confuse an agent doing `select earliest unblocked task`.

#### P1-6: UI-3 contracts are incomplete

ENGINE §18 lists the screen catalogue but option-chain panel, OI tabs/overlays, Renko, and saved layouts are "API/data contracts must be designed now" (MASTER §UI-3) without actually designing them. The endpoint families list includes `/option-chain` and `/option-chain/metrics` but no payload schemas. An agent cannot implement UI-3 from what exists.

#### P1-7: Provenance of specific facts

- **Python 3.11.9** — stated as fact in AGENTS §2. MASTER §ADR-016 owner decisions also state this. Is this verified? It's plausible (the user's venv likely uses this) but flagged.
- **DATA §11.7 specific gap dates** — stated as "audit leads from the 2026-10-12 inventory report." These are from a previous agent session's memory, not verified against current files. They're correctly labeled as leads, not facts. Acceptable.
- **"Telegram primary/email backup"** — in MASTER ADR-016 owner decisions. Acceptable as a stated preference.

---

### 1.5 Assessment of the Other AI's Review

The other AI review is **largely correct** with some important caveats:

**Where the other AI is right:**
- ✅ MASTER_SPEC is an ADR register, not an architecture document (P0)
- ✅ Missing tasks for BOS/CHoCH algorithm, option-chain features, per-strike chart, risk-policy evaluation
- ✅ No live state / vision traceability replacement
- ✅ M0 tautological check
- ✅ RunConfig is a field list without types/ranges/defaults table
- ✅ UI-3 contracts missing payloads
- ✅ DATA §9.1 wrong ADR reference

**Where the other AI is partially wrong or outdated:**
- ❌ **DSR formula:** The other AI says it's wrong. The current ENGINE §20.2.1 has a correct and complete DSR formula with the Bailey/López de Prado formulation, `Var(SR)`, Euler-Mascheroni constant, etc. This is resolved in the current docs.
- ❌ **Risk module missing:** The other AI says "no task implements risk-policy evaluation." ENGINE §7 is a complete risk policy spec with all controls listed, and M4-05 implements them. What's missing is a *separate* dedicated risk-engine task (the risk runs inside M4-05 which also covers fills/positions). A separate M4-20 task would be cleaner.
- ❌ **Missing tasks for MACD/Bollinger/VWAP/Supertrend/ADX:** The other AI says no implementation task. M5-08 exists for documentation/catalogue, but the other AI is correct that there's no `implement MACD` task per se. However, these are likely expected to be done as part of M5-03 extension or follow-on tasks. The spec implies they'll be built; the gap is just the missing explicit task.
- ❌ **Two URL schemes:** The other AI says ENGINE §11 uses `/backtests` and `/charts/series` while §18 uses `/api/v1/runs` and `/candles`. Looking at the actual docs, ENGINE §11 API contract uses `/backtests/{run_id}`, `/charts/series`, etc., while §18.1 table uses `/api/v1/runs` and `/candles`. This inconsistency is real and needs fixing.
- ✅ **"Is open-based signal at close entry correct?"** — The other AI says this question is never answered. Actually, ENGINE §4 lines 89-90 says: "An open-based signal cannot fill at that same bar's close and cannot fill at the same opening print that generated the signal. With 1m OHLC, earliest actionable fill is the next bar's open." This answers the question. The other AI may have missed it.

---

### 1.6 Two Data Leads the Other AI Identified — My Assessment

**Lead 1: Volume/OI as contracts vs units**

The other AI observed that OI values (31,200 = 416 × 75; 2,629,705 = 40,457 × 65) appear to be in units (contracts × lot_size), and lot size appears to have changed from 75 to 65. This is a valid audit lead. DATA §11 correctly marks these as `VERIFY` and instructs M3-08 to audit semantics. The observation about lot-size change (75 → 65) is consistent with the sample data in vision.txt. This should be elevated to a known lead in DATA §11.6.

**Lead 2: Row count inconsistency**

The other AI estimated that 1m has ~1,205 sessions while 1d has ~1,181 and intraday (3m/5m/15m) has ~1,155-1,158 — a ~50-session discrepancy. This is already noted in ADR-004 ("Vendor higher-timeframe files disagree on day coverage") and M3-07 (derive intervals and vendor checksum report). The specific number should be added to DATA §11.6 as an audit lead.

---

## Part 2 — Final Improvement Prompt

> **Instructions for AI making the documents:**
> Copy the exact text below and give it to the document-making AI. This prompt PRESERVES ALL EXISTING ARCHITECTURE and adds targeted fixes only. Do NOT rewrite or restructure documents.

---

### THE PROMPT (copy this exactly to AI1)

```
You are improving the QuantView specification documents. 
CRITICAL RULE: Preserve ALL existing content, ALL existing ADRs, ALL existing task entries, ALL existing section numbering, ALL existing formulas, tables, and architectural decisions. You are adding and fixing, NOT rewriting.

Apply the following targeted changes to the four specification files. Make each change in the exact location specified. Do not alter surrounding text unless explicitly instructed.

---

### CHANGE 1 — QUANTVIEW_MASTER_SPEC.md: Add System Architecture section after ADR-016

After the closing paragraph of ADR-016 (the writer matrix table), insert a new section:

## System Architecture Overview

**Runtime process map and data flow (authoritative; deviations require an ADR)**

```text
                         ┌─────────────────────────────────────────────────┐
                         │               Live Market Hours                  │
                         │                                                  │
  Upstox REST API ──────►│ collector_snapshot  (rate-limit reserved quota) │
  (option chain)         │   ↓ raw REST files + capture manifest           │
                         │                                                  │
  Upstox WebSocket ─────►│ collector_ws  (sole WS owner)                  │
  (quotes/ticks)         │   ↓ .partial → fsync → finalized segments       │
                         │   ↓ FrameBus (local socket, after M7-01)        │
                         │                                                  │
  Upstox Expired API ───►│ backfill  (lower priority, checkpointed)        │
                         └─────────────────────────────────────────────────┘
                                    ↓ (all raw → data/)
                         ┌─────────────────────────────────────────────────┐
                         │          worker_data  (exclusive lease)          │
                         │  Stage → validate → atomic publish → manifest    │
                         │  Canonical Parquet (lake/) + Postgres index     │
                         └──────────────┬──────────────────────────────────┘
                                        │ (read-only; DuckDB queries)
              ┌─────────────────────────┼──────────────────────────────┐
              ↓                         ↓                              ↓
  ┌──────────────────┐    ┌────────────────────────┐    ┌────────────────────┐
  │  worker_compute  │    │    services/api         │    │   live_daemon      │
  │  (N leased jobs) │    │  FastAPI + Pydantic     │    │  (one per deploy)  │
  │  Backtests,      │    │  REST + WebSocket/SSE   │    │  strategy host     │
  │  features,       │    │  Command + Query        │    │  paper broker      │
  │  research        │    │  ↑ from apps/web        │    │  risk guards       │
  │  ↓ run artifacts │    └────────────────────────┘    │  ledger writer     │
  └──────────────────┘                                   └────────────────────┘
              ↓                                                    ↓
  runs/{run_id}/manifest.json                      Postgres: ledger, orders,
  runs/{run_id}/ledger/                            positions, deployments,
  runs/{run_id}/trades/                            accounts, job queue
  runs/{run_id}/equity/
  runs/{run_id}/decisions/
  runs/{run_id}/metrics.json
```

**Failure domains:**
- `collector_snapshot` and `collector_ws` fail independently; the other continues. A dead collector triggers an alert within 60 s.
- `worker_data` lease expiry stops canonical publishing; other readers continue reading the last valid manifest.
- A stalled `live_daemon` deployment process is killed by the supervisor; unrelated deployments are unaffected.
- API/UI restart never stops collectors or live deployments.
- `worker_compute` crashes leave run in `FAILED` state; no partial run artifact is promoted.

**End-to-end request lifecycle (backtest launch):**
1. User submits RunConfig via UI form or CLI.
2. `api` validates schema, resolves manifest IDs/hashes, checks hold-out guard, creates job row in Postgres.
3. `worker_compute` claims the job via `FOR UPDATE SKIP LOCKED`.
4. Worker reads canonical Parquet via DuckDB; runs event loop; writes artifacts to `runs/{run_id}/` under `staging/`.
5. Worker validates artifacts (schema, hash, counts), renames to canonical target, writes `manifest.json`, registers run in Postgres.
6. `api` exposes run artifacts; UI displays equity/trades/metrics.

**Single-writer invariant summary:** Every durable store has exactly one writer process at a time; see ADR-016 and DATA §11.5 for the full matrix.

---

### CHANGE 2 — QUANTVIEW_MASTER_SPEC.md: Fix DATA §9.1 cross-reference

In the Cross-document rule ownership section (§9.1 of DATA — but this cross-reference appears in MASTER), find and fix:

FIND: "Production host and process ownership are authoritative in `QUANTVIEW_MASTER_SPEC.md` ADR-001."
REPLACE WITH: "Production host and process ownership are authoritative in `QUANTVIEW_MASTER_SPEC.md` ADR-015."

(This same fix must be applied in QUANTVIEW_DATA_SPEC.md §9.1 as well.)

---

### CHANGE 3 — QUANTVIEW_DATA_SPEC.md §9.1: Fix ADR reference

Find:
"Production host and process ownership are authoritative in `QUANTVIEW_MASTER_SPEC.md` ADR-001."

Replace with:
"Production host and process ownership are authoritative in `QUANTVIEW_MASTER_SPEC.md` ADR-015."

---

### CHANGE 4 — QUANTVIEW_DATA_SPEC.md §11.6: Add lot-size change audit lead

After the existing content in §11.6, add:

- **Lot-size change lead**: Sample data in the original vision shows April 2025 option candle with `lot_size=75` (OI 31,200 = 416 × 75) and July 2026 snapshot with quantities divisible by 65. This suggests the NIFTY lot size changed from 75 to 65 at some point between these dates. The contract master must be validity-dated with an effective lot-size change record. M3-03 must audit lot-size history against instruments-master captures and official NSE announcements before any backtest uses lot size for P&L.
- **Row-count discrepancy lead**: The reported row counts suggest 1m has approximately 50 more session-days of data than the 3m/5m/15m series, and about 24 more than the 1d series. This is consistent with ADR-004 (vendor higher-timeframe files disagree on day coverage). M3-07 must specifically reconcile the 1m session count against the other intervals and report the discrepancy before deriving canonical higher-timeframe bars.

---

### CHANGE 5 — QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md §19 RunConfig: Add missing fields

In the RunConfig §19, after the `data_manifest_ids, calendar_version, contract_master_version` line, add the following to the Required fields list:

- `max_stale_minutes` (integer, default 5): maximum minutes an open position mark can be stale before forcing an exit at next valid open with worst-case slippage. Referenced in §4 fill table and §7 risk controls but missing from config schema.
- `order_expiry_bars` (integer, default 3): number of eligible contract bars after which a queued order expires as `EXPIRED`. Referenced in §4 but missing from config schema.
- `intrabar_stop_policy` (`STOP_FIRST` | `OPTIMISTIC`): default is `STOP_FIRST` (same-bar stop+target → stop wins). `OPTIMISTIC` mode is only permitted in a named sensitivity run and must be visible in the run manifest and results UI. Setting `OPTIMISTIC` as a baseline is rejected.
- `risk_free_rate_source` (string enum: `ZERO_EXPLICIT` | versioned `rates_dividends` manifest ID): governs Sharpe/Sortino/DSR denominator. `ZERO_EXPLICIT` means assume zero risk-free return with a visible label.
- `vix_filter_enabled` (boolean, default false): enables India VIX volatility filter from §7; only valid when `india_vix` dataset is available and not `VERIFY`-blocked.

In the Defaults and guardrails section of §19, add:

- Slippage sensitivity scenarios (`0x, 1x, 2x, 3x`) are one run produced as child scenarios of the parent run. They are NOT counted as separate DSR trials. The trial registry increments only for genuinely different strategy hypotheses or parameter choices, not for sensitivity diagnostics of the same run.

---

### CHANGE 6 — QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md: Fix URL scheme inconsistency

In §11 (API and UI contracts), the endpoint family list uses `/backtests`, `/charts/series`, etc. In §18.1 screen catalogue, the Data/API contracts column uses `/api/v1/runs` and `/candles`. Standardize to the `/api/v1/` prefix throughout.

In §11, replace the suggested endpoint families list with:

```
- `/api/v1/health`, `/api/v1/data/health`, `/api/v1/data/coverage`
- `/api/v1/candles`, `/api/v1/charts/series`, `/api/v1/charts/transforms`, `/api/v1/charts/drawings`
- `/api/v1/features`, `/api/v1/features/{id}/compute`, `/api/v1/features/{id}/metadata`
- `/api/v1/contracts`, `/api/v1/option-chain`, `/api/v1/option-chain/metrics`
- `/api/v1/strategies`, `/api/v1/runs`, `/api/v1/runs/{run_id}`, `/api/v1/runs/{run_id}/artifacts`
- `/api/v1/accounts`, `/api/v1/risk-policies`, `/api/v1/paper/orders`, `/api/v1/paper/positions`, `/api/v1/paper/ledger`
- `/api/v1/deployments`, `/api/v1/deployments/{id}/start`, `/api/v1/deployments/{id}/stop`
```

In §18.1 screen catalogue, update the Data/API contracts column to use the same `/api/v1/` prefix consistently.

---

### CHANGE 7 — AGENTS.md §0: Fix M0-10 acceptance check

The M0-10 acceptance check contains a string that does not appear in the actual AGENTS.md file:

FIND:
```
python -c "from pathlib import Path; p=Path('AGENTS.md'); assert p.exists() and 'Required evidence report' in p.read_text(encoding='utf-8')"
```

REPLACE WITH:
```
python -c "from pathlib import Path; p=Path('DOCS/AGENTS.md'); assert p.exists() and 'Required evidence' in p.read_text(encoding='utf-8')"
```

---

### CHANGE 8 — AGENTS.md §6: Add missing implementation tasks

After the last task in M5 (M5-10), add:

#### M5-11 — Implement MACD, Bollinger Bands, Supertrend, ADX built-in features

- **Size:** M (2 person-day upper bound)
- **Depends on:** M5-08
- **Needs:** owner approval of final list (M5-08 owner_attestation must pass first)
- **Initial status:** `DESIGNED`
- **Acceptance type:** `file_check`
- **Evidence path:** `ops/evidence/M5-11.md`
- **Acceptance contract:** Implement MACD (12/26/9 default), Bollinger Bands (20/2 default, population vs sample stdev explicit), Supertrend (ATR 10 / multiplier 3 default, exact band algorithm versioned), and ADX (14 default, Wilder RMA). VWAP is gated on volume semantics VERIFY; do not implement VWAP until M3-08 closes the volume-semantics VERIFY entry. Each feature: truncation test at multiple cut points, warm-up NaN count, known-value test against hand-computed or TradingView reference, batch/live parity within declared tolerance. Memory class and repaint class declared per §21 catalogue.

---

After M6-03, add:

#### M6-03b — Per-strike option chart view

- **Size:** M (2 person-day upper bound)
- **Depends on:** M6-03, M3-05, M5-04
- **Needs:** —
- **Initial status:** `DESIGNED`
- **Acceptance type:** `file_check`
- **Evidence path:** `ops/evidence/M6-03b.md`
- **Acceptance contract:** Build the per-strike option chart as a separate view within the chart workspace: expiry selector (from contract master, point-in-time), strike selector, CE/PE toggle, option OHLC series from `lake/option_candles/`, trade markers from run/deployment artifacts, indicator overlays. No silent strike substitution. Selector uses point-in-time contract master only (no weekday inference). 5k-bar latency target applies. Per-strike chart uses option-candle OHLC, never index/underlying prices as tradable levels.

---

### CHANGE 9 — AGENTS.md §6: Fix M5-10 dependency cycle

M5-10 currently depends on `M5-01, M8-01`. M8-01 depends on `G1, G3`. G3 gates features and contains M5 tasks. This creates a cycle: M5-10 ∈ M5 milestone which is part of G3, but M5-10 depends on G3 via M8-01.

Resolution: M5-10's dependency on M8-01 is for the ML model artifact contract, not for the ML research execution. The frozen model artifact contract (inference interface, hash, manifest binding) can be specified without a trained model existing.

Change M5-10's depends_on to: `M5-01` only. Add a note:

"The frozen model artifact *contract* (inference interface, feature schema, manifest binding) is implemented here. Actual trained model artifacts from M8-01/M8-02/M8-04/M8-05 are loaded into this contract at research time. M5-10 does not depend on M8 milestones completing; it only defines the interface that M8 artifacts must satisfy."

---

### CHANGE 10 — AGENTS.md §6: Clarify M0 acceptance contracts

For each M0 task that says "Pre-inventory safe acceptance only... After M0-01 inventory is accepted, refine this acceptance contract before any collector-touching implementation":

Add after that sentence: "The agent must stop after M0-01 is accepted and explicitly request owner approval of the refined acceptance contract for this task before proceeding. The task ID and evidence path are reserved; status remains `DESIGNED` until the refined contract is approved."

This makes the conditional-acceptance pattern explicit and prevents an agent from treating the pre-inventory text as the actual acceptance contract.

---

### CHANGE 11 — QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md §21.1: Add missing BOS/CHoCH algorithm

In §21.1 (Option-chain features), there is already a feature table. In §3.3 (Truncation and parity contract), BOS/CHoCH is mentioned but no algorithm is given. Add a new subsection after §21.1:

### 21.2 BOS/CHoCH algorithm contract (authoritative)

The pivot-based algorithm must be declared and versioned in the feature registry. The following is the v1 reference algorithm; variations must be registered as separate IDs.

| Parameter | Meaning | Default |
|---|---|---|
| `pivot_left` | Number of bars to the left of the pivot that must have lower highs (for pivot high) or higher lows (for pivot low) | 5 |
| `pivot_right` | Number of bars to the right of the pivot that must have lower highs/higher lows | 5 |
| `break_rule` | `CLOSE_THROUGH` (close beyond pivot level) or `TOUCH` (high/low reaches pivot level) | `CLOSE_THROUGH` |
| `choch_rule` | `LAST_SWING_BREAK` (break of last opposite-direction swing) | `LAST_SWING_BREAK` |

**Pivot detection:** A pivot high at bar `b` is confirmed when `pivot_right` bars after `b` have all closed with highs ≤ `high[b]`. `pivot_time = ts_start[b]`; `confirmed_at = ts_end[b + pivot_right]`. A pivot low is the mirror.

**BOS (Break of Structure):** After a pivot high is confirmed, a BOS-bearish event fires at the first bar whose close (under `CLOSE_THROUGH`) or low (under `TOUCH`) is below the most recent confirmed pivot low. `confirmed_at` is that bar's close time.

**CHoCH (Change of Character):** After a series of higher highs establishing an uptrend, a CHoCH-bearish fires when the most recent confirmed pivot high is broken downward by a close below the last confirmed pivot low — same break rule as BOS but the preceding bias must be the opposite direction. Implementation must track current bias state explicitly.

**Causal requirement:** Strategy code may not consume a pivot event or a BOS/CHoCH event before its `confirmed_at`. The `pivot_time` is for display only. Repainting class: `confirmed-lag` (the pivot appears in the past once confirmed; no true-repaint occurs if the implementation correctly waits for `confirmed_at`). Memory class: `infinite` (bias state carries across bars). Requires truncation tests with at least 3 cut points in a dataset with known pivot sequences.

---

### CHANGE 12 — QUANTVIEW_MASTER_SPEC.md: Eliminate duplicate writer matrix

In ADR-016, the writer matrix table is a near-duplicate of DATA §11.5. Replace the table in ADR-016 with:

"The binding single-writer ownership matrix is maintained in `QUANTVIEW_DATA_SPEC.md §11.5`. ADR-016 records the architectural decision that each durable store has exactly one writer at a time, enforced by process boundaries, Postgres leases, and atomic publish protocols. Refer to §11.5 for the current authoritative table; this ADR does not maintain a separate copy."

---

### CHANGE 13 — AGENTS.md: Add machine-readable status for M1-08

The existing M1-08 task (machine-readable task/ADR/VERIFY status registry) should include an explicit schema reference. After the existing acceptance contract, add:

"The `docs/status.yaml` schema must include at minimum: `task_id`, `status` (one of DESIGNED/IMPLEMENTED/TESTED/VERIFIED), `evidence_path`, `evidence_exists` (boolean), `evidence_command_or_hash`, `depends_on` (list of task/gate IDs), `gate_id` (if this task contributes to a gate), and `verify_items_blocked` (list of VERIFY item IDs this task resolves). The CI validator must reject any entry where `status` is TESTED or VERIFIED but `evidence_exists` is false."

---

END OF TARGETED CHANGES

Do not alter anything else. After applying all 13 changes, produce a short diff-style summary showing what was added or changed, with section references. Do not create new documents or restructure existing sections.
```

---

## Part 3 — Quick Reference: What the Docs Still Don't Answer

After all fixes above, the following remain as intentional open questions that require owner input or external verification:

| Open Item | Where to close it |
|---|---|
| Postgres DDL outline (tables, columns, indexes) | A new appendix in DATA or a separate `schema.sql` file; add as M1-09 deliverable |
| API payload schemas (request/response bodies for each endpoint) | OpenAPI spec is the authoritative source; generated from FastAPI models at M6-01 |
| `option_chain` panel payload (UI-3) | Define when strategy needs OI/PCR promotes it; add a placeholder `TBD_PROMOTED_FROM_UI3` to M6-03b |
| CLI shape (command names, flag names, help text) | Add one example in AGENTS §8 baseline section |
| Upstox WS field list (what does protobuf return?) | M2-05 deliverable; cannot speculate before fixtures |
| Official lot size change date (75 → 65) | M3-03 contract master; instruments-master daily archive resolves this |
