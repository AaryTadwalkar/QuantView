# Final bounded repair prompt for the QuantView document-making agent

Copy everything inside the block below to the agent that owns the QuantView documents. This is a **single closed-list repair pass**, not a redesign request.

---

```text
You are repairing the existing QuantView specification set. The current architecture is substantially approved. Do not restart design, replace the stack, rewrite the specs from scratch, or introduce another review loop.

SOURCE LAYOUT
- The four authoritative files are in DOCS/: DOCS/QUANTVIEW_MASTER_SPEC.md, DOCS/QUANTVIEW_DATA_SPEC.md, DOCS/QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md, DOCS/AGENTS.md.
- my_vision.txt is in the repository root and is the source requirement input. Read it; do not move or edit it.
- Run commands from the repository root. Linux paths are case-sensitive. Fix references consistently for DOCS/ and keep runtime evidence paths (ops/...) relative to the repository root.

NON-NEGOTIABLE PRESERVATION RULES
1. Preserve the existing architecture, all ADR numbers, existing task IDs, existing formulas except the specifically requested DSR correction, current behavioural decisions, and existing requirements. Do not silently delete scope.
2. Do not renumber existing tasks. New tasks must use unused IDs. Mark M1-07 as intentionally reserved/retired if it remains unused.
3. Do not claim code exists, tests passed, data was inspected, or external facts were verified unless actual evidence exists. Initial implementation status remains DESIGNED.
4. Keep owner choices as PENDING_OWNER and external/broker/data semantics as VERIFY. Do not invent numeric defaults for behaviour-changing fields.
5. Do not add Redis/Valkey, a feature cache, microservices, Kubernetes, real orders, or other unconditional infrastructure. Keep the existing raw-first Parquet/DuckDB/Postgres modular-monolith architecture and process boundaries.
6. Do not create a fifth authoritative spec. Put architecture in Master, storage/schema/eligibility in Data, behaviour/API/UI/research contracts in Engine, and tasks/gates/status/traceability in AGENTS.
7. Make only the changes below plus the minimal cross-references and task-size/dependency arithmetic required by those changes. Do not perform unrelated style rewrites.

PHASE A — FIX PATHS AND INTERNAL CONSISTENCY
A1. In DOCS/AGENTS.md, make the canonical reading order and all references to the three specs resolve from repository root under DOCS/. State the path convention once. Correct M0-10 to inspect DOCS/AGENTS.md, not an assumed root AGENTS.md.
A2. Replace the M0-10 tautological/broken acceptance command. It must check the real DOCS/AGENTS.md file and at least the required title/sections (including required reading and milestone-report/stop rule), exit non-zero on failure, and save actual output at ops/evidence/M0-10.txt. Do not check for a phrase that only appears inside the command itself.
A3. Fix DATA §9.1: host/sync points to Master ADR-015; process boundaries/leases point to ADR-014. Audit every cross-document ADR/section/path reference for stale or nonexistent targets.
A4. Standardize every API path to one canonical /api/v1 namespace and one naming scheme. Use /api/v1/runs as the run resource and /api/v1/charts/series as the chart-series resource; use /api/v1/candles only if it is explicitly defined as a distinct alias/resource. Update §11, §18.1, task acceptance text and examples consistently. Do not leave mixed unversioned paths.
A5. Remove the duplicated spot_price column from DATA §4.3. Add nullable prev_oi to the snapshot-row canonical schema, with field-presence and source-version handling. State how expiry is resolved from the original expiry directory path when the raw payload lacks it; record that it was path-derived, preserve the original path, and quarantine ambiguous/missing expiry rather than guessing. Add runs/{run_id}/metrics.json to the DATA layout.
A6. Remove concatenation residue in Engine (repeated “Status: DESIGN SPECIFICATION” lines and duplicated §20 heading/content). Keep one authoritative status note and one §20 section without renumbering substantive sections.
A7. Make one source-semantics table authoritative in DATA §11; replace the earlier partial duplicate with a pointer. Make DATA §11.5 the only detailed writer matrix; replace the Master ADR-016 duplicate table with the architecture decision and a pointer to DATA §11.5. Make Engine §16 the authoritative VERIFY register and convert other full duplicates into concise pointers/summaries. Make AGENTS §5 the authoritative task-to-gate membership definition; Engine §15 may describe phases but must not define a conflicting gate membership.

PHASE B — ADD A REAL ARCHITECTURE OVERVIEW WITHOUT CHANGING THE ADRS
B1. Add “System Architecture Overview” in DOCS/QUANTVIEW_MASTER_SPEC.md after ADR-016 and before the binding UI tiers (or immediately before the authority section). Keep all existing ADRs/numbers intact.
B2. Include:
- a component/process map for web UI, API, collector_snapshot, collector_ws, backfill, worker_data, worker_compute, live_daemon, packages/domain/data/features/strategies/engine/risk/ledger, Parquet, DuckDB, Postgres and FrameBus;
- data flows for historical REST/backfill, snapshot collection, WebSocket raw capture, canonical publication, CLI/UI backtest, and live paper replay;
- explicit component ownership and allowed/forbidden dependencies;
- failure domains and what keeps running when API/UI/worker/collector/deployment processes fail;
- end-to-end backtest request lifecycle from RunConfig validation through job lease, manifest-pinned data reads, staging artifacts, validation/atomic publish, Postgres registration and results UI;
- restart/replay/reconciliation lifecycle and single-writer boundaries;
- explicit rule that collector_ws remains raw-capture-only until M7-01; FrameBus publication/replay starts at M7-01;
- no claim that Redis, cache, cloud host or offsite backup is enabled.
This section documents the existing architecture; it must not silently change it.

PHASE C — CLOSE DATA CONTRACT GAPS
C1. Add a logical PostgreSQL operational schema outline in DATA (or the current operational-schema section) and expand M1-04/M1-09 acceptance accordingly. For each table/entity specify purpose, primary key, foreign keys, key columns, uniqueness/idempotency constraints, critical indexes, writer/reader ownership and retention/immutability rule. At minimum cover accounts, versioned risk policies, deployments, jobs/leases, run index, dataset-manifest index, paper orders/fills, append-only ledger events, rebuildable position/equity projections, app settings, feature/model/experiment registries, chart drawings and saved layouts. Keep bulk candles/market history in Parquet; do not duplicate the canonical market-data lake in Postgres. Full SQL migrations are implemented later; this is the binding logical design contract.
C2. Add an explicit task (new ID M3-12) for availability/inventory and canonicalization of india_vix, nifty_futures_candles and rates_dividends where sources exist. Acceptance must produce per-dataset source, coverage, schema, availability and VERIFY report; unavailable sources remain unavailable/null and block dependent VIX/model-Greek features rather than being fabricated. Make M5-05 and the VIX filter depend on the relevant verified/eligible dataset or explicit versioned assumptions.
C3. Extend M2-05 WebSocket research acceptance: inspect current dated official documentation and account-specific capabilities, record the exact source URLs/date, distinguish documented fields from fixture-observed fields and unknowns, capture approved representative fixtures, and produce a field-presence/units/availability/reconnect/reset table. Do not invent protobuf fields or claim the feed is a complete tick tape/complete chain.
C4. Add a lot-size 75-versus-65 observation only as an audit lead, not a fact. M3-03 must resolve effective dates using instruments-master history and authoritative evidence. Do not state the exact effective date until verified. Row-count-derived session discrepancies are also leads only; M3-01/M3-07 must recompute unique sessions and expected bars against the versioned calendar.

PHASE D — MAKE RUNCONFIG AND METRICS AGENT-EXECUTABLE
D1. Expand Engine §19 into a typed field table: field, type, allowed values/range, requiredness, default, validation, and whether owner input/source verification is needed. Cover existing fields plus max_stale_minutes/stale-position policy, order_expiry_bars, intrabar_stop_policy, risk_free_rate_source, vix_filter_enabled, and explicit slippage model parameters. Preserve the already-set STOP_FIRST default and explicit-zero risk-free assumption if used. Do not invent numerical defaults for stale timeout/order expiry or other behaviour-changing controls; mark PENDING_OWNER or require explicit per-run input. A run must be rejected with a structured reason if a required setting is unresolved.
D2. Add one canonical example RunConfig file and a CLI shape using the same schema as API/UI (for example, a validate command and a run command taking --config). Label the CLI naming as a designed interface, not an existing implementation. Include the baseline 5m EMA(9)/EMA(21) smoke strategy but clearly label it as plumbing-only, not tuned or profitable.
D3. Correct Engine §20.2.1 DSR math. Distinguish:
- cross-trial variance of Sharpe estimates, used to estimate the expected-maximum Sharpe threshold across N trials;
- sampling uncertainty of the selected Sharpe statistic, used in the PSR/DSR denominator with T, skewness and raw kurtosis.
Do not reuse one symbol/value for these two quantities unless an explicitly justified fallback estimator is defined. Sharpe ratios inside the DSR formula must be at the same per-observation frequency as T; report annualized Sharpe separately. Record formula/version, T, skew, raw kurtosis, effective N, trial-registry hash and estimator/fallback convention. Add a reference fixture/test requirement for the implementation task. Cite Bailey & López de Prado (2014) in the spec.
D4. Define trial accounting: record every configuration and result that could influence selection; do not blindly count every slippage sensitivity row or capital-affordability diagnostic as an independent hypothesis. Sensitivity rows are child scenarios of a parent run unless a documented research choice turns them into a separately selected hypothesis. Do not undercount genuinely inspected/discarded configurations either.

PHASE E — COMPLETE FEATURE AND ENGINE ACCEPTANCE
E1. Add a deterministic, versioned BOS/CHoCH algorithm contract in Engine §21 (or its own subsection) with: pivot_left/pivot_right; complete left and right comparison rules; tie policy; confirmation time; close-through default and optional touch variant if retained; level-cross consumed-once behaviour; initial neutral bias; exact definitions for bullish/bearish BOS vs CHoCH; double-break/ambiguous-bar handling; output schema including pivot_time and confirmed_at; and known-sequence/truncation tests. Do not paste the current draft algorithm verbatim unless these ambiguities are resolved. Strategy consumption is forbidden before confirmed_at.
E2. Keep M5-03's initial implementation scope explicit (EMA, RSI, ATR and only those option-chain features that have been named). Add a separate new task M5-11 for MACD, Bollinger Bands, Supertrend and ADX with formula variants, warm-up, known-value/truncation/chunk-equivalence tests. Add a separate new task M5-12 for option-chain features: PCR by OI, PCR by volume, OI change and ROC by strike band, ATM straddle, delta-band OI, model IV skew and multi-strike OI distribution. VWAP is not eligible until source-volume semantics pass VERIFY; either add a separate task or explicitly include it as a blocked subtask that cannot be marked implemented until then.
E3. Add a dedicated risk-policy evaluator task (new ID M4-20). It must explicitly test max entry fills/day, daily loss with realized+unrealized marks and overshoot, max drawdown, max positions/lots/exposure, premium/capital caps, windows/force-flat, cooldown/consecutive losses, stale-data entry block and open-position exit policy, VIX/liquidity filter availability, manual kill switch, stable reason codes, pre-trade and post-fill checks. Risk invariants that cannot be disabled in realistic mode remain enforced. Keep strategy logic, position structure and risk/execution policy separate.
E4. Start margin/settlement research earlier. If M4-17 cannot begin until the position-group interface exists, add a small early research task (new ID M4-21) that records dated authoritative margin, hedge-benefit, buying-power, expiry/settlement and forced-exit evidence; make M4-17 consume that evidence and implement the mode guard. Do not enable realistic short/multi-leg account claims until the required evidence and tests pass.
E5. Remove unnecessary dependencies only where the acceptance can be split cleanly: historical snapshot normalization can run on original v1/v2/v3 fixtures without waiting for the new collector rewrite; the engine loop/selector can be developed against synthetic calendar/contract interfaces before real datasets exist, with real-data integration still blocked by G1. Make the task text explicit so “synthetic first” does not conflict with dependency rules.
E6. Separate M8 R2 option-chain/tick pattern discovery (requires WS fixtures and verified field semantics) from R3 candle/chart-pattern discovery (can begin from eligible historical candles). R3 still requires causal features, purged walk-forward, trial accounting, hold-out controls, frozen model contract and human review, but must not be blocked on WS unless it actually consumes WS/tick inputs.
E7. Remove M5-10's dependency on M8-01. M5-10 defines the frozen model artifact/inference contract; trained models later conform to it. Ensure the expanded task+gate graph has no cycles.

PHASE F — COMPLETE UI CONTRACTS AND TASKS WHILE KEEPING RELEASE TIERS
F1. Keep UI-1 as dashboard, strategy browser, backtest terminal, core chart, per-strike option chart with trade markers, indicator controls/settings dialogs, same-page results panel, accounts/risk/capital and results/audit. Keep UI-2 as Heikin Ashi switch and basic horizontal-line/rectangle drawings. Keep UI-3 (Renko, saved multi-chart layouts, advanced drawings, option-chain panel and OI tabs/overlays) scheduled for v1.1 and committed; promote OI UI only if the documented strategy dependency trigger fires.
F2. Add explicit new task IDs (do not renumber existing tasks) for:
- UI-1 per-strike option chart: expiry/strike/CE-PE selectors from point-in-time contract master, option-candle OHLC, trade markers, no substitution;
- UI-1 schema-driven indicator settings dialogs and feature visibility controls;
- UI-2 Heikin Ashi chart-type switch;
- UI-2 basic drawing persistence and UI/API (horizontal line + rectangle);
- `/paper` and `/settings` screens or explicit acceptance mapping to existing tasks if genuinely covered;
- UI-3 API/data-contract freeze now, while implementation remains scheduled v1.1.
F3. Specify a versioned Postgres drawing/layout model. Drawing fields must include ID, chart/contract identity, drawing type, time/price anchors, style, visibility/order, schema version, timestamps and optimistic version for conflict detection. Do not allow chart drawings/layouts to affect strategy results.
F4. Define request/response schemas now for UI-3 option chain, OI metrics/tabs/overlays and saved layouts. Include as-of/received_at, freshness, source tier, coverage/completeness, schema version, missing-field/warning flags, expiry/strike/type and observed-vs-modelled labels. Never present stale/partial snapshots as a complete live chain. These are API/data contracts only until UI-3 is promoted.
F5. Standardize all screen endpoint examples to the canonical /api/v1 routes. The UI may optimistically show a pending drag, but server acknowledgement/version conflict is authoritative. No real-order route/control may exist.

PHASE G — TASK/GATE REGISTRY, TRACEABILITY AND ESTIMATES
G1. Keep the task list in AGENTS authoritative. Extend M1-08 so it creates ops/status.yaml as a generated/mirrored runtime status registry, not a competing task-definition source. Minimum task fields: task_id, status, evidence_path, evidence_exists, evidence_command_or_hash, depends_on, gate_id, acceptance_type/spec, verify_items_blocked. CI must reject TESTED/VERIFIED when evidence is missing; VERIFIED additionally needs dated authoritative/empirical evidence. Keep all tasks initially DESIGNED.
G2. Add a vision-traceability appendix inside AGENTS.md (do not create a new authoritative file). Give every numbered/lettered requirement and substantive question in my_vision.txt a stable V-ID, short text, spec section, task ID(s), status COVERED/PARTIAL/DEFERRED/GAP, and note. Every item must map to a task or a reasoned DEFERRED entry with a promotion trigger. Add a CI-checkable validation rule; no unrepresented vision item may be silently dropped.
G3. Define exact gate membership by task ID for G0, G1, G2a, G2b, G3, G4, G5 and G6. State entry/exit evidence and which downstream tasks/gates each blocks. Ensure M5-10 no longer causes a gate-expanded cycle. Add a graph checker for task dependencies plus gate expansion.
G4. Add M0-11 (or another unused M0 ID) for refining and obtaining owner approval of M0-02..M0-09 acceptance contracts after M0-01 inventory. Until that task is approved, no collector code/schema/service changes or broad download may occur. Make M0-01 a precise read-only inventory contract with exact deliverable fields and safe commands that run only within the repository/approved paths. M0-09 still requires explicit approval of exact date/contract range and request budget.
G5. Add every new task to dependency references, gates, status schema and vision traceability. Ensure task IDs are unique, every dependency resolves, no task/gate cycles exist, evidence paths are unique unless explicitly shared, all acceptance types are valid, and all task sizes are present.
G6. Recalculate task count, person-day ceiling and critical path from the final task list; update all copies of those totals. Keep task IDs as identifiers, not execution order. Do not preserve the old 95/233.5 total after adding tasks unless the recalculation independently produces it.
G7. Keep one authoritative phase/gate definition. In Engine §15, point to AGENTS for gate membership instead of maintaining a conflicting table. Make owner facts correctly labelled: Python 3.11.9 is owner-provided QuantView runtime info pending read-only environment confirmation; Python 3.13 is installed but not the project runtime. Telegram/email are owner-preferred channels but recipient remains PENDING_OWNER. Specific gap dates and 75-to-65 lot-size history remain audit leads until checked.

FINAL MECHANICAL CHECKS — MUST RUN AND REPORT ACTUAL OUTPUT
1. Parse all YAML/JSON examples; validate the RunConfig example against its declared schema or clearly state that implementation validation is pending because code does not yet exist.
2. Parse the task registry and status registry schema; task IDs unique; all dependencies resolve; all gate IDs exist; gate-expanded graph has no cycles; every task has size, acceptance type/spec, evidence path and initial status.
3. Recompute task count and S/M/L person-day total from the final file, not by hand. Check unique evidence paths.
4. Check every V-ID maps to a spec section and task or explicit DEFERRED record; compare the traceability set against every numbered/lettered vision item and question in root my_vision.txt.
5. Check all relative spec paths resolve from repository root, all section/ADR references resolve, no stale ADR-001 host pointer remains, no conflicting API paths remain, and metrics.json is in DATA layout.
6. Check no duplicated spot_price column; prev_oi exists in canonical snapshot rows; expiry path fallback is explicit; source semantics and writer matrices each have one detailed authority; no duplicated §20/status residue remains.
7. Verify no unconditional Redis/Valkey/cache assumption and no real-order path was introduced. Do not run broker/live collection or broad downloads as part of document validation.
8. Do not claim the docs are implemented. Produce a concise diff-style report listing each closed item, section/task IDs changed, validation commands and actual results, remaining PENDING_OWNER/VERIFY items, and any item not completed.

STOP CONDITION
This is the last planned document repair pass. Do not make any additional improvements outside the closed list. After the checks above, stop and wait. Do not solicit another broad architecture review or create more spec files.
```

---

## How to use this prompt

1. Give the agent the prompt above and the existing four files plus `my_vision.txt`.
2. Ask it to edit those four files in place and return the actual diff plus checker output.
3. If it reports an unresolved point, accept it only if it is a genuine `PENDING_OWNER`/`VERIFY` item or a concrete blocker—not a style preference.
4. Freeze the files after the closed-list checks pass. Do not ask another AI to redesign them; use future reviews only for reproducible P0/P1 defects tied to code or a specific spec clause.
