# QuantView — Independent Review of the Four Specification Files

**Reviewed inputs:** `QUANTVIEW_MASTER_SPEC.md`, `QUANTVIEW_DATA_SPEC.md`, `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md`, `AGENTS.md`, `my_vision.txt`, the pasted review from the other AI, and `quantview_doc_analysis.md`.

**Purpose:** identify real blockers and errors without redesigning QuantView or restarting the architecture loop. This is a review artifact, not a fifth authoritative specification.

## Executive verdict

The four files are a strong design foundation and preserve most of the original vision. They are **not yet safe to freeze as agent-ready**. The remaining issues are not a reason to redesign the system; they are a finite set of missing contracts, incorrect cross-references, task/acceptance gaps, and schema/API inconsistencies.

The task count and estimate in the uploaded `AGENTS.md` are mechanically confirmed: **95 tasks, 233.5 person-days at the declared S/M/L upper-bound sizes**. That arithmetic is correct for the current task list. It must be recalculated after adding or splitting tasks. A task-level dependency scan finds no cycle among task IDs alone, but that does **not** prove the gate-expanded graph is acyclic: gate membership is not defined precisely enough to expand and verify it.

**Recommendation:** do not pass the other AI's review unchanged. Use the closed-list repair prompt in `QuantView_Final_Repair_Prompt.md`. Allow one targeted repair pass, run the listed mechanical checks, then freeze the specs. Do not invite another open-ended “improve anything” review.

## 1. Alignment with `my_vision.txt`

### Covered well

- Full-stack, single-user research/backtesting/paper-trading scope; no real-order execution in v1.
- Data-first and raw-first ingestion, immutable source preservation, canonical Parquet, DuckDB analytics and PostgreSQL operational state.
- Historical underlying candles, expired option candles, versioned option-chain snapshots, data eligibility and explicit source-semantics verification.
- Shared causal engine, next-eligible-bar execution, exact-money ledger, fees/slippage, risk policy concepts, separate accounts and reproducible run artifacts.
- RunConfig-driven CLI/UI, results and audit panel, core charting, per-strike chart as a stated UI-1 requirement, accounts/risk/capital, and paper monitoring as a stated screen.
- Feature registry, custom feature isolation, transforms that do not replace tradable OHLC, ML leakage controls, walk-forward validation and trial accounting.
- The deliberate deviations (on-demand features before optional cache; preserve separate snapshot captures rather than synthesize a continuous snapshot grid; UI staging) are stated openly.

### Partially covered or not agent-executable yet

1. **System architecture:** the Master file is explicitly an ADR/decision register. The Engine file has a process tree and some boundaries, but there is no single end-to-end architecture narrative with data flows, request lifecycle, ownership, failure domains and restart/recovery boundaries.
2. **Feature implementation:** M5-03 explicitly implements EMA, RSI, ATR and broad “PCR/OI” features. M5-08 is a formula/variant catalogue with owner approval, not an implementation task for MACD, Bollinger Bands, Supertrend, ADX or VWAP. Option-chain formulas exist, but their implementation task is too vague.
3. **BOS/CHoCH:** timing/confirmation fields are specified, but the actual swing-pivot, break, bias and event-classification algorithm is not.
4. **UI work:** per-strike chart, indicator settings dialogs, chart-type switch, drawings, `/paper`, and `/settings` are named in the screen/tier spec, but not all have explicit acceptance tasks. UI-3 is said to have contracts designed now, yet the payload/data contracts are not present.
5. **Data sources:** `india_vix`, `nifty_futures` and `rates_dividends` are in the target layout/requirements, but there is no clear canonicalization/availability task that gates dependent model Greeks and the VIX filter.
6. **Operational DB/API contracts:** the docs choose Postgres and FastAPI, but do not provide a table-level operational schema outline or concrete request/response payload schemas for all promised interfaces. The OpenAPI-at-implementation approach is reasonable for UI-1, but it does not satisfy the promise to define UI-3 contracts now.
7. **Traceability/live status:** the final four-file set has no V-ID-to-requirement/task mapping. `AGENTS.md` says M1-08 will create a machine-readable status registry later, but its current task schema does not fully spell out gate membership and evidence state. The fix can live inside the four-file set; no fifth authoritative spec is needed.

## 2. Defects confirmed in the actual uploaded files

### P0 — fix before the coding agent starts implementation

#### P0.1 — M0-10 acceptance command is broken

`AGENTS.md` M0-10 checks for the literal text `Required evidence report`, but that phrase is not present in the guide. The command is therefore tautological in intent and fails against the current file. It also checks `AGENTS.md` at repository root, while the user says the four documents are stored in `DOCS/`. The acceptance must check the real path and required headings/content, retain the command output, and write evidence to the M0-10 evidence path.

#### P0.2 — M0 acceptance contracts are deferred but not operationally closed

M0-02 through M0-08 say “Pre-inventory safe acceptance only” and tell the agent to refine acceptance after M0-01, but no explicit task/gate tells the agent how to approve that refinement. M0-01 itself needs a precise read-only inventory checklist. Add an explicit post-inventory contract-refinement/owner-approval task; until approval, collector-touching work remains blocked.

#### P0.3 — Gate membership is missing

The guide defines gate evidence and blocking effects, but not the exact task IDs that contribute to each gate. This makes gate dependencies impossible to validate mechanically and leaves a potential cycle around M5-10 → M8-01 → G3. A task-only dependency scan has no cycle; the concern arises when gates are expanded to task membership. Define gate membership explicitly and remove M5-10's unnecessary dependency on M8-01: a frozen inference/artifact contract can be implemented before a trained model exists.

#### P0.4 — Vision UI requirements lack explicit implementation tasks

- UI-1 per-strike option chart is only generically covered by M6-03.
- Indicator settings dialogs are specified but no task explicitly implements their schema-driven forms.
- UI-2 Heikin Ashi chart-type switching has a transform task but no clear UI switch task.
- Basic line/rectangle drawings have no concrete persistence schema or implementation task.
- `/paper` and `/settings` have screen rows but no explicit screen implementation task.
- UI-3 is committed to v1.1 and the Master says contracts must exist now, but option-chain/OI/layout payload contracts are missing.

Add explicit tasks while retaining UI tiers: UI-1 remains core; UI-2 stays selective; UI-3 remains scheduled v1.1 unless the documented OI/PCR promotion trigger fires.

#### P0.5 — Risk-policy implementation is not sufficiently testable as a task

Engine §7 lists max entries, daily loss, drawdown, cooldown, exposure caps, stale-data guards, VIX/liquidity filters and kill switch. M4-05's acceptance contract primarily tests order/fill/position invariants and does not explicitly prove those policy behaviours. This is not a missing conceptual risk specification; it is a missing implementation/acceptance boundary. Add a dedicated risk-policy evaluator task or expand the task split so every listed control has deterministic golden/property tests and stable rejection/halt reasons.

#### P0.6 — Data schema/path errors

- `option_snapshot_rows` in DATA §4.4 omits `prev_oi`, even though snapshot v1 and the source-semantics audit name it.
- Original snapshots may encode expiry in the directory path. The canonicalization contract does not explicitly say to parse that path when expiry is absent from the payload, preserve derivation provenance, or quarantine ambiguous cases.
- `option_snapshot_captures` lists `spot_price` twice.
- DATA's directory layout omits `runs/{run_id}/metrics.json`, although the Engine requires it.
- DATA §9.1 incorrectly points production host/process ownership to ADR-001; host/sync is ADR-015 and process boundaries are ADR-014.
- The final files live under `DOCS/` per the user, but many guide cross-references and M0 checks use bare root-relative names. This is a Linux case/path issue, not just style. Define one path convention and apply it consistently.

#### P0.7 — API route schemes conflict

Engine §11 lists unversioned `/backtests`, `/charts/series`, etc.; §18.1 uses a mixture of `/api/v1/runs`, `/candles`, `/runs/{id}` and `/api/v1/...`. Select one canonical API prefix and one canonical run/chart resource naming scheme. Update every endpoint reference and avoid duplicate endpoints unless an alias is intentionally specified.

#### P0.8 — Required supporting datasets lack an owner task

The data layout includes `india_vix`, `nifty_futures_candles` and `rates_dividends`, but no explicit task owns availability, normalization, source evidence and eligibility. Model Greeks depend on rates/dividend/forward assumptions; the VIX filter depends on VIX data. Add a task that inventories and canonicalizes these where available, records unavailable sources as unavailable rather than fabricating values, and gates downstream features.

### P1 — correctness and completeness upgrades

#### P1.1 — Deflated Sharpe Ratio (DSR) formula is not fully correct as specified

The other review's concern is substantially valid; `quantview_doc_analysis.md` incorrectly dismisses it as resolved. In Engine §20.2.1, `Var(SR)` is defined as a sampling-variance expression involving `T`, skewness and kurtosis, then its square root is also used in the expected-maximum Sharpe term. Bailey–López de Prado's expected-maximum term uses the **variance across trial Sharpe estimates**; the PSR/DSR denominator uses the sampling uncertainty term. They are related but not automatically the same quantity. Also make explicit that the Sharpe used inside the DSR statistic is at the same per-period frequency as the `T` observations, not the annualized Sharpe reported in the UI. Record the estimator convention, cross-trial dispersion source/fallback, effective trial count and trial-registry hash. See the original paper: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf.

Trial accounting also needs a policy: capital affordability and slippage sensitivity scenarios should be recorded, but must not automatically be treated as independent strategy hypotheses for DSR. Count every configuration/result that could influence hypothesis selection, document correlations/diagnostics, and do not inflate `N` by blindly counting each sensitivity row as an independent trial.

#### P1.2 — RunConfig is a field list, not a typed schema

RunConfig is thoughtfully broad, but lacks a complete type/range/default/requiredness table and a canonical example file/CLI shape. Add typed fields and validation for at least:

- `max_stale_minutes` / stale-position policy;
- `order_expiry_bars`;
- `intrabar_stop_policy` (STOP_FIRST as the default invariant; any optimistic mode, if retained, must be an explicitly labelled sensitivity only);
- `risk_free_rate_source` / assumption;
- `vix_filter_enabled` and the conditions under which it is unavailable;
- exact slippage model parameters, not only ID/multiplier;
- fee schedule, capital, sizing, stop/target units, time windows and hold-out settings.

Do not invent owner-approved numeric defaults. Where a default materially changes behaviour and is not already fixed, label it `PENDING_OWNER` or require explicit RunConfig input. Provide one example config and CLI invocation that use the same schema as API/UI.

#### P1.3 — Postgres logical schema and API payloads are missing

Add a table-level logical outline for operational entities and their primary/foreign keys, uniqueness/idempotency constraints and critical indexes: accounts, versioned risk policies, deployments, jobs/leases, run index, dataset manifest index, paper orders/fills, append-only ledger events, rebuildable projections/positions, settings, feature/model/experiment registries, drawings and layouts. This is a design contract; M1 migrations implement it later. Do not store bulk candle history in Postgres.

Define typed request/response contracts now for UI-3 (option-chain rows and freshness/coverage, OI metrics/tabs/overlays, layouts, drawing objects). OpenAPI remains generated from FastAPI/Pydantic at implementation time; it is not a substitute for specifying promised UI-3 semantics.

#### P1.4 — Indicator and option-chain implementation gaps

- M5-03 explicitly implements EMA, RSI, ATR and generic PCR/OI only.
- M5-08 is catalogue/approval/compatibility, not implementation for MACD, Bollinger, Supertrend and ADX.
- No dedicated task implements PCR-by-OI/volume, OI change/ROC by strike band, ATM straddle, delta-band OI, model IV skew and multi-strike OI distribution.
- Session VWAP must remain unavailable until volume semantics are verified; do not silently use the underlying index's zero-valued volume.

Add separate tasks for remaining standard indicators and option-chain features. Keep each feature's source tier, warm-up, availability, formula variant, repaint/memory class and truncation/known-value tests explicit.

#### P1.5 — BOS/CHoCH algorithm needs a deterministic versioned definition

The current docs specify `pivot_time` and `confirmed_at` but not the actual algorithm. Define left/right pivot windows, tie handling, confirmation time, break rule, one-time level-cross handling, initial bias, BOS vs CHoCH classification, ambiguous double-break behaviour, and tests. The proposed algorithm in the attached review is a useful start but its text is internally ambiguous (for example, its pivot definition does not fully state the left-window rule and its BOS/CHoCH event definitions are not sufficiently distinct). Do not paste it verbatim without tightening those rules.

#### P1.6 — Research tasks are coupled too tightly in places

- M3-06 historical snapshot normalization depends on M2-01 collector rewrite even though historical v1/v2/v3 fixtures can be normalized independently. Remove the dependency or define exactly which part truly needs M2-01.
- M4-03/M4-04 depend on the real calendar/contract master despite the stated ability to build engine scaffolding with synthetic fixtures. Separate interface/golden work from production-data integration or explain why the dependency is essential.
- Margin/settlement research in M4-17 should start earlier; it is mostly source/assumption verification and should not wait for the full position-group contract. Separate early research from engine guard integration if needed.
- M8-06 bundles R2 option-chain/tick discovery (requires WS fixtures) and R3 candle/chart-pattern discovery (can start from historical candles). Separate those dependencies so R3 is not unnecessarily blocked by WebSocket collection.

#### P1.7 — Duplication and cross-reference drift

- The writer matrix is duplicated in Master ADR-016 and DATA §11.5; designate DATA §11.5 as the only detailed authority and make ADR-016 a pointer/decision.
- Source-semantics information is duplicated between DATA §8 and §11; keep the complete table in §11 and make the earlier section a pointer.
- VERIFY information and phase/gate summaries are duplicated between Engine and AGENTS. Name one authoritative register and make other sections short pointers/summaries.
- The Engine contains repeated `Status: DESIGN SPECIFICATION` lines, including a duplicated §20 heading/content block. Remove concatenation residue without renumbering substantive sections.
- M1-07 is absent from the task sequence. Do not renumber stable IDs; mark M1-07 intentionally reserved/retired if it is not to be used.

### Claims in the other AI review that need qualification

| Claim | Assessment |
|---|---|
| Master is not a detailed architecture document | Correct. Engine §1 helps, but a consolidated architecture/data-flow/failure-boundary section is still warranted in Master. |
| M0-10 check is broken | Correct. The expected literal is absent and the path may be wrong for `DOCS/`. |
| Missing per-strike chart task | Correct; generic M6-03 does not make acceptance explicit enough. |
| No task for remaining standard indicators | Correct. M5-08 documents formulas but does not implement those indicators. |
| Risk module entirely missing | Too strong. Engine §7 defines controls, but M4-05 acceptance does not explicitly prove all policy controls. A dedicated implementation task/acceptance is needed. |
| DSR is wrong | Substantially correct. The current formula conflates cross-trial Sharpe variance with sampling variance and does not clearly enforce per-period Sharpe units. |
| Open-based signal question is unanswered | Incorrect. Engine §4 lines 89–90 explicitly says an open-based signal cannot fill at that same opening print and the earliest OHLC fill is the next bar's open. Preserve this rule. |
| “About 50 more sessions” from row counts | Treat as an audit hypothesis, not a verified count. Recompute unique sessions and expected bars against the official calendar; do not hard-code the estimated discrepancy. |
| Lot size 75 → 65 is verified | Not verified. The samples are a useful lead, but effective dates must come from instrument-master history/official evidence. |
| Python 3.11.9 and Telegram/email are invented | Not necessarily. They were supplied as owner inputs in prior context. Keep Python 3.11.9 as owner-provided project-runtime information pending read-only environment confirmation; keep alert channels as owner preference with destination still `PENDING_OWNER`. Do not present either as externally verified. |
| There is definitely a task dependency cycle | Not proven by task IDs alone. There is a potential cycle once gate membership is expanded; define gate membership and remove M5-10 → M8-01 to make the graph unambiguous. |
| M4 task numeric ordering is a blocker | Not a correctness blocker. IDs are stable identifiers; dependency order is authoritative. Do not renumber. |

## 3. Data leads that should remain leads, not conclusions

1. **Option quantity units / lot-size history:** the supplied examples are consistent with multiples of 75 in one sample and 65 in another. This is evidence to investigate, not proof of the vendor's units or exact effective date.
2. **Historical session-count differences:** row counts suggest coverage differences across intervals, but row-count division by a typical session bar count is only approximate. M3-01/M3-07 must compute actual unique session dates, expected bars by calendar, duplicates, and missing bars from the actual files.
3. **Specific missing dates and special sessions:** retain them as audit leads from prior reports; recompute from the user's files and official calendar before marking a data defect or valid session.
4. **WebSocket payloads:** no exact protobuf field semantics should be invented. M2-05 should combine current dated official documentation/account behavior with recorded fixtures and clearly separate documented, observed and unknown fields.

## 4. What should be frozen after the repair

- Preserve all current ADR numbers and architectural decisions unless a specific contradiction is proven; any real architecture change requires a new ADR.
- Preserve existing task IDs. New tasks use unused IDs; do not renumber existing work.
- Do not create more authoritative spec files. Put the architecture overview in Master, schemas in Data, behaviour/UI/research contracts in Engine, and execution/task/traceability/status rules in AGENTS.
- Include an in-guide vision traceability matrix with stable V-IDs for every numbered/lettered vision requirement and question. Each item maps to a spec section and task, or is explicitly `DEFERRED` with a reason and promotion trigger.
- `AGENTS.md` task list is the authoritative planned work; a runtime `ops/status.yaml` is the machine-readable status/evidence mirror created by M1-08. It must not become a competing task-definition source.
- Gate membership, task dependencies and all relative paths must be mechanically checked. Keep all unverified external facts `VERIFY` and unresolved owner choices `PENDING_OWNER`.
- After the closed-list repair and checker pass, freeze the documents. Later changes require evidence of a concrete blocker, not another broad style review.

## 5. Sources consulted

- User-supplied `my_vision.txt` and the four uploaded specification files.
- User-supplied other-AI review and `quantview_doc_analysis.md`.
- Bailey & López de Prado, *The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality*: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf. The key distinction is variance across trial Sharpe estimates for the expected-maximum threshold versus sampling uncertainty in the PSR/DSR statistic.
