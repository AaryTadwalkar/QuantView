# QuantView HLD/LLD v1.1 → v1.2 — Change log, traceability and decisions for approval

Scope: owner architecture review of 2026-10-11 (Parts A–D). Method: surgical, anchored edits to the v1.1 files (no wholesale rewrite); every edit is marked **[v1.2]** in the documents.

**Status of everything below: `DESIGNED`.** Nothing is `IMPLEMENTED`, `TESTED` or `VERIFIED`; Phase 0 has not started. The living register is LLD Appendix C. Every acceptance test and gate added is `PENDING`, not `PASS`.

---

## 1. What I accepted, modified or pushed back on

"Spec status in v1.1" is a one-time classification of what the v1.1 documents already said (`SPECIFIED` / `PARTIAL` / `ABSENT`); the living maturity is in LLD App. C.

| Item | Spec status in v1.1 | Verdict | What changed and why |
|---|---|---|---|
| 2 Durable events | PARTIAL: "replay from `event_id` checkpoints" and a local socket, but the socket was the only transport and events had no sequence | **Accepted, modified** | Journal for market streams (fsync = committed; consumers see only committed events; segments double as the raw WebSocket log); Postgres tables are the outbox for trading streams; checkpoint advanced in the same transaction as effects; idempotency keys derived from event ids. **Not adopted:** one universal journal for everything (it would duplicate Postgres, which already gives atomic commit and a `bigserial` order). No broker. |
| 3 Paper/live isolation | PARTIAL: "separate schemas", no credential/role design | **Accepted, strengthened** | Separate databases and roles; `HttpGateway` allow-list; runtime `sys.modules` guard; composite FKs for mode/kind/origin. Schemas inside one database were judged too weak (ADR-026). |
| 4 Option execution and risk | PARTIAL: RK-08 already used full outlay without a premium stop; `ONE_LOT` was already subject to RK-07/08 | **Accepted** | Added what was missing: explicit statement that underlying stops are exit triggers not loss caps, stressed premium-stop estimate, RK-22 (unquantifiable risk), RK-23/24, exit priority, kill-switch modes, gap/spread/stale/missing-quote table, ONE_LOT cannot skip any rule. |
| 5 Data quality and coverage | PARTIAL: calendar bootstrap, CQ/OQ rules, dataset status, G0.1–G0.3 existed | **Accepted** | Added observation states (incl. `UNATTRIBUTED_GAP` because legacy data has no heartbeat history, so a collector failure cannot be told from a provider omission), two-tier coverage matrix, `calendar_version`, eligibility gate, G0.10. |
| 6 Option fill simulation | PARTIAL: snapshot fills specified; WS fills only for paper | **Accepted; one correction** | Mode C WS-quote fill model + `AUTO` source selection + provenance; exit-resolution classes with best/worst bounds; "never reconstruct before recording began" stated and tested. **Correction:** P2 said "bid/ask/LTP"; LTP is no longer allowed as an executable price. |
| 7 ML validation | MOSTLY SPECIFIED: walk-forward, purge, frozen holdout lifecycle, trial counting, promotion criteria, hashes (LLD §11.4–11.12) | **Accepted for the gaps only** | Added: trials counted at start (failed/aborted runs count), manual strategy changes logged, holdout guard on datasets, `ml reproduce`. **Pushback:** an embargo is not needed for forward-only splits (features use only the past, overlapping labels are purged); it is required and enforced (`EMBARGO_REQUIRED`) for any scheme that trains after a test block. |
| 8 Accounting and recovery | PARTIAL: append-only ledger, reversal, partial-fill test existed | **Accepted** | Posting rules for cancel/partial/correction/charge adjustment/instrument remap/expiry settlement; `eod_snapshots`; reconcile and restore procedures; historical lot/tick stored per order; expiry overrides. |
| 9 Charting | PARTIAL: lazy loading, IST, DQ ribbon, markers existed | **Accepted** | Gaps as whitespace, provisional vs final bars, marker/overlay *groups* (so one deployment cannot touch another's drawings), tooltips with raw UTC. |
| 10 Replay | ABSENT beyond one clause | **Accepted** | Full server-authoritative design: two kinds (`CHART_REPLAY`, `EVENT_REPLAY`), cursor clamps every read, `422` past the cursor, deterministic hashes, no synthesized deployment history. |
| 11 Live option chain | PARTIAL: snapshot picker only | **Accepted** | Live-only `/options` with per-cell source/age/state; historical snapshots moved to `/research/chain`; no `at`/`as_of` parameter exists; on-demand subscriptions; no full-chain real-time promise (constraint C10). |
| 12 Manual paper account | ABSENT | **Accepted** | `PAPER_MANUAL` account kind, `MANUAL` origin, `HARD_ONLY` profile, single execution path through `order_requests` outbox (no second engine). |
| 13 Deployment controls | PARTIAL: `paper_deployments` table and pause/resume/stop actions, no state semantics | **Accepted** | State machine with `DRAINING`; default stop never erases a position; explicit `FLATTEN_NOW`. |
| 14 Visualization controls | PARTIAL: generic markers only | **Accepted** | Persisted-event markers only, per-deployment toggles, off by default, read-only role split (P17), `TradeInspection`. |
| 15 Auto indicators (only when 14 is on) | ABSENT | **Accepted** | `FeatureDisplay`/`FeatureExplanation`/repaint flag; `chart-spec` resolved at pinned versions; renders only when the deployment's visualization and Indicators toggles are on; version drift refuses to render. |
| 16 Report and metric inspector | PARTIAL: metric definitions, bootstrap, sensitivity existed; no click-to-explain; **Sortino absent** | **Accepted** | Metric registry (`MetricDefinition`/`MetricDetail`), ids namespaced by result kind, Sortino added, Sharpe/Sortino `NOT_APPLICABLE` for Mode B. |
| 17 Retain workspaces | SPECIFIED | Kept | Nothing removed; `/options` semantics changed (see D9). |
| 18 Repository APIs | PARTIAL (candles, chain, quotes) | **Accepted** | Catalogue adds coverage, features, trade events, run results, live chain; import-linter blocks direct Parquet/DuckDB use. |
| 19 Schemas | PARTIAL | **Accepted** | DDL rewritten (§9.5): account kind/mode/origin, signal/order/fill timestamps, deployments, events, checkpoints, `viz_preferences`, `eod_snapshots`. |
| 20 Focused spec files | — | **Deferred** | You asked earlier for no other documents until HLD/LLD are final, and the review asks to avoid contradictory duplicates. Content is in LLD §4.15, §8.8, §8.10.5, §13.5–13.10. See D3. |
| 21 Acceptance tests | ABSENT | **Accepted** | `T-ACC-1…15` (LLD §15.1) plus T-EVT, T-ISO, T-CHN, T-MAN, T-DEP, T-VIZ, T-RPL, T-RPT. |
| 22 Implementation order | SPECIFIED (phases 0–10) | **Kept, mapped** | Phase numbers unchanged so no ticket reference breaks; your 10-step order is mapped onto phases in HLD §14. |

---

## 2. Requirement → document section → tickets

| Req | HLD | LLD | Tickets | Gate / tests |
|---|---|---|---|---|
| 1 Preserve architecture | §11, §16 | unchanged | — | — |
| 2 Durable events | P14, §5.7, ADR-027, §12 | §2.3, §4.10.5, §8.8.4, §14.5 | T0.9, T7.7 | G0.11, G7.1; T-EVT-1…13, T-ACC-11 |
| 3 Isolation | P15, §5.6, ADR-026 | §9.5, §10.5, §4.9.5 | T0.15, T1.6, T7.8 | G0.12, G7.2; T-ISO-1…8 |
| 4 Option risk | §9, ADR-032 | §8.2.1, §8.6.2, §8.6.8, §8.6.9 | T7.2, T7.9 | T-RK-27…31, T-SIM-15 |
| 5 Data quality | §7.7, ADR-036 | §4.4.1, §4.14, §3.2 | T0.14 | G0.10; T-MD-13…16 |
| 6 Fill simulation | §8, ADR-034 | §4.10.4, §8.4.2.1, §8.4.8 | T6.7 | T-SIM-16…18, T-MD-16 |
| 7 ML validation | ADR-015/017 | §11.13 (+§11.4–11.12) | T8.9 | T-ML-13…17 |
| 8 Accounting, recovery | §12 | §9.3, §9.5, §9.9, §3.7, §14.5 | T7.17 | G7.3; T-LG-11…18, T-INS-7…9, T-ACC-15 |
| 9 Charting | §10 | §13.2, §4.8.1 | T1.5 | T-FE-UI-1…3 |
| 10 Replay | §10.1, ADR-033 | §13.5 | T3.8 | G3; T-RPL-1…8, T-ACC-1 |
| 11 Live chain | C10, ADR-030 | §4.15, §13.6, §4.10.1 | T7.14, T7.15 | G7.7; T-CHN-1…10, T-ACC-12 |
| 12 Manual account | §5.6, §9, ADR-028 | §8.8.3, §8.6.9, §13.7 | T7.9, T7.10 | G7.4; T-MAN-1…8, T-ACC-3/4 |
| 13 Deployments | §9, ADR-029 | §8.8.2, §13.8 | T7.11 | G7.5; T-DEP-1…8 |
| 14 Visualization | P17, ADR-029 | §8.8.5, §6.6, §13.9 | T7.12, T7.13 | G7.6; T-VIZ-1…7, T-ACC-5/6/7/10 |
| 15 Auto indicators | ADR-035 | §5.1.9, §13.9 | T3.1, T3.5, T7.12 | T-FE-11…15, T-ACC-8/9 |
| 16 Metric inspector | P16, ADR-031 | §8.10.5, §13.10 | T5.7, T6.8 | G5.1; T-RPT-1…7, T-ACC-2/13 |
| 17 Retain workspaces | §10 | §13.3 | existing | — |
| 18 Repository APIs | §6 | §4.8.1 | T1.3, T0.14, T3.5, T7.12 | T-MD-17 |
| 19 Schemas | — | §9.5, §2.3, §6.6 | T1.6 | T-LG-18, T-ISO-5 |
| 20 Doc updates | §1–§17 | all | — | — |
| 21 Acceptance tests | §13, §14 | §15.1 | per phase | T-ACC-1…15 (all `PENDING`) |
| 22 Order | §14 | §17 | — | — |

**Schemas and API:** DDL in LLD §9.5; envelope and journal in §2.3; `LiveChainView` §4.15; `ChartEvent` §6.6; `MetricDefinition`/`MetricDetail` §8.10.5; `FeatureDisplay`/`FeatureExplanation` §5.1.9; `DataRequirement`/`EligibilityResult` §4.14; `ManualOrderRequest` §8.8.3; endpoints in §12.2–12.3; error codes in §12.4.

---

## 3. Decisions and contradictions that need your approval

| # | Item | Why it needs you |
|---|---|---|
| D1 | **Separate databases** (`qv_core`, `qv_paper`, later `qv_live`) instead of "schemas" (ADR-026) | Contradicts the v1.1 wording; adds three Alembic histories |
| D2 | **Journal segments are the raw WebSocket log**; trading events use Postgres as the outbox (ADR-027) | Changes where raw ticks live and how they are retained |
| D3 | The four focused spec files are **not created**; LLD holds the content | You asked both for them and for no extra documents yet; I can generate them later as non-authoritative extracts |
| D4 | P2 reworded: **LTP is never executable** | v1.1 allowed "bid/ask/LTP" |
| D5 | Manual account: **no CEILING rules, no entry windows**, but HARD rules, a 10-minute expiry cutoff and an **expiry force-exit at 15:15** apply to every account | "Not governed by strategy risk" vs "system-wide safety"; carrying into expiry would need a settlement price I will not invent |
| D6 | Manual positions are `CARRY` (never auto-flattened except at expiry); no intraday product for manual v1 | Simplest consistent rule; say if you want an intraday square-off |
| D7 | **LIMIT orders are designed but PENDING** (T7.16); the ticket is MARKET-only until you confirm | The simulator implements MARKET only; limit realism has no queue model (R20) |
| D8 | **One active deployment per strategy account** (previously "recommended") | Needed for clean attribution and the deployment state machine |
| D9 | `/options` becomes **live-only**; the snapshot picker moves to `/research/chain` | Changes the v1.1 Options workspace |
| D10 | Feature-version drift **refuses to render** indicators (no multi-version retention of old calculators) | Redeploy needed after a feature version bump |
| D11 | **Sharpe/Sortino not applicable to Mode B** (no equity); defined for options and paper equity only | Mode B is in points |
| D12 | `paper-runner` is **one process per paper database** hosting all deployments and the manual consumer (v1.1: "per deployment") | Simpler recovery; single point of failure noted as R21 |
| D13 | Embargo default 0 for forward-only splits (see §1, item 7) | Departs from the review's blanket wording |
| D14 | Replay speeds are bars-per-second (0.5…20), client-paced | UX choice |

---

## 4. Unresolved issues and `[VERIFY]` items (not decided by documents)

1. Whether Upstox issues a **read-only data token**; until proven, the gateway and import rules are the only barrier (T0.15, R16).
2. WebSocket `full` **instrument cap** and whether `full` carries Greeks (S10, `greeks_in_full_mode`); they bound live-chain breadth.
3. Statutory charges on **expiry settlement**, exchange-transaction rate, STT schedule (existing `[VERIFY]` items).
4. Owner-supplied **real contract notes** for fee reconciliation (T7.5).
5. Calendar verification (G0.1) and the existing audit ambiguities (432,967 vs 451,952 rows; session counts across timeframes) remain Phase 0 work.
6. On a single-user Windows laptop an OS-level credential barrier is weak; the effective barriers are configuration, code and tests until Phase 9 adds a separate OS user.
7. Journal growth, fsync latency and WebSocket volume must be **measured** (G0.8, G0.11) before retention decisions.

---

## 5. Gates added (all `PENDING`)

G0.10 coverage matrix · G0.11 journal fault injection · G0.12 token scope and gateway · G3 replay · G5.1 metric inspector · G7.1 durable consumers · G7.2 isolation · G7.3 ledger corrections/recovery · G7.4 manual account · G7.5 deployments · G7.6 visualization · G7.7 live chain · G7.8 data-quality blocking.
