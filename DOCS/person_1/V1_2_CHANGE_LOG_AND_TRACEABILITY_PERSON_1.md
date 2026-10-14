# QuantView v1.2 — Review Verdicts, Change Log, Traceability and Decisions

| Field | Value |
|---|---|
| Document | `docs/V1_2_CHANGE_LOG_AND_TRACEABILITY.md` (review record; not an implementation contract) |
| Inputs | `HIGH_LEVEL_DESIGN.md` v1.1, `LOW_LEVEL_DESIGN.md` v1.1, the owner's consolidated review of 2026-10-11 |
| Outputs | HLD v1.2, LLD v1.2, `CHARTING_UX.md`, `OPTIONS_CHAIN_UI.md`, `PAPER_TRADING_UI.md`, `BACKTESTING_REPORT_SPEC.md`, this file |
| Method | Document review only. **The repository was not inspected**, so no requirement is `IMPLEMENTED`, `TESTED` or `VERIFIED`. Every v1.2 item is `DESIGNED`. |

**Status words** (LLD Appendix C): `DESIGNED` specified with tests named · `IMPLEMENTED` code merged with a completion report · `TESTED` named tests passed in CI with an artifact · `VERIFIED` checked on real data/session and signed off by the owner.
**Prior-spec column:** `SPECIFIED` already adequately in v1.1 · `PARTIAL` mentioned but incomplete or contradictory · `NEW` absent.

## 1. Were the proposed improvements actual improvements? (verdicts)
| # | Proposal | Prior spec | Verdict | Why / what changed relative to the proposal |
|---|---|---|---|---|
| 1 | Preserve architecture | — | **Adopted unchanged** | Nothing in v1.2 adds a broker, Redis, Kafka, Kubernetes or a time-series DB. The only new infrastructure is a file journal and two Postgres tables. |
| 2 | Durable restart-safe events | PARTIAL (contradiction: checkpoint replay over a transport that stored nothing) | **Adopted with modification** | Proposal says "replay missed events". Replaying *quotes* would fill paper orders at vanished prices, so quotes are classed TELEMETRY and never replayed (stale, not catch-up). Control events are journaled; trading events use a Postgres outbox; checkpoints commit with the effects; replayed entries are gated (`STALE_REPLAY`). |
| 3 | Paper/live isolation | PARTIAL ("separate schemas" stated; DDL had one set; no roles/credentials rules) | **Adopted with modification** | Schemas + roles + process + credentials + installed code, rather than separate databases (the dangerous path is the credential/order code). Adds the caveat that the collector token may be order-capable `[VERIFY]`. Three-lock arming. |
| 4 | Option-specific execution and risk | PARTIAL (RK-08 used full outlay without a premium stop; priorities, gaps, kill-switch semantics undefined) | **Adopted with modification** | Explicit risk bases; RK-22; one-lot fallback cannot override hard limits; priority ladder; overshoot reporting. Also noted that a *premium* stop is not a loss bound either (path-blind, next-bid fills), hence overnight defaults to worst-case outlay (decision D-06). |
| 5 | Data-quality and coverage contract | PARTIAL (rules and dataset status exist; no coverage matrix, no reason taxonomy, no run eligibility gate) | **Adopted** | Versioned calendar, reason codes, 3-level matrix (kept small by aggregating strikes per day), eligibility gate, warnings. |
| 6 | Option fill simulation | PARTIAL | **Adopted with a correction** | HLD P2 listed LTP among executable sources — contradicts the fill models; fixed. Adds `OPT_QUOTE_BIDASK`/`HYBRID` (the real fix for the 30 s blind spot, only where the recorder ran), spread-widening expiry, exit-resolution bounds. |
| 7 | ML validation | **SPECIFIED** (purged walk-forward §11.4, holdout lifecycle §11.12, bootstrap vs baselines §11.8, trial counting) | **Mostly already done; only gaps closed** | Added: failed runs and spec edits count as trials, purge for rule-based walk-forward, reproducibility record, trial cap. No restatement of existing material. |
| 8 | Accounting and recovery | PARTIAL (reversals, rebuild, partial exit cost release existed) | **Adopted** | Charge adjustments, corrections as reversal+new fill, instrument rules stored per fill, migration/expiry-settlement recovery events, restore and pull-the-plug drills, execution-semantics register. |
| 9 | Accurate charting | PARTIAL (adapter, lazy load, IST shift trick, DQ ribbon) | **Adopted with modification** | Index-based time axis hides missing bars ⇒ explicit whitespace gaps. IST via formatters preferred over the +19 800 s shift (kept as isolated fallback). Marker price space made explicit. |
| 10 | Chart replay | PARTIAL (one line: slider, "no future bar") | **Adopted with modification** | Server-side clamping (client hiding cannot guarantee non-leakage), autoscale rule, forming-bar rule, three replay kinds. |
| 11 | Live option-chain workspace | PARTIAL (historical snapshot picker only) | **Adopted with modification** | Hybrid feed with per-cell provenance; no full-chain real-time promise; `/options` live-only, history moved to `/research/options`. |
| 12 | Manual paper account | NEW | **Adopted with modifications** | Same engine, separate account kind; MARKET + LIMIT only (what the simulator can honour — LIMIT is new work); single writer; ceilings *advisory*, hard safety rules enforced (decision D-05). |
| 13 | Deployment controls | PARTIAL (pause/resume/stop endpoint, no semantics) | **Adopted** | State machine, DRAIN default, confirmed FLATTEN, guardian in ERROR, one open deployment per account. |
| 14 | Strategy chart visualization | NEW | **Adopted with modification** | Markers from persisted rows; visualization prefs in a UI-only table; marker vertical position is the underlying anchor (option premium cannot be plotted on the index axis); premium-basis levels are not drawn on that axis. |
| 15 | Auto-display of strategy indicators | NEW | **Adopted** | Feature `display`/`explain`/`repaints` metadata, pins, persisted series, version-unavailable behaviour; only when master + indicators are on (decision D-07 confirms the toggle model). |
| 16 | Click-to-explain metrics | PARTIAL (metrics defined; no explanations; Sortino absent) | **Adopted** | `MetricDetail` produced by the same function as the value, independent recompute check, Sortino defined, ambiguities (flat days, breakeven) resolved without changing numbers. |
| 17 | Keep existing workspaces | SPECIFIED | **Adopted** | All retained; routes added. |
| 18–19 | Repository APIs and schemas | PARTIAL | **Adopted** | LLD §4.8.1, §9.5, §9.5.1. |
| 20 | Keep HLD concise; focused specs optional | — | **Adopted** | Four focused specs created: UI behaviour only; contracts stay in the LLD to avoid contradictory duplicates. |
| 21–22 | Tests and phase order | PARTIAL | **Adopted with one deviation** | Live-chain UI moves to Phase 2 (decision D-04). |

## 2. Change log
### 2.1 Additions
| Document | Section | Addition |
|---|---|---|
| HLD | §2 P14, P15 | Durable-events and account-isolation invariants |
| HLD | §4, §5.2, §5.4 | Account kinds/origin, process rows (`paper-runner` as sole writer, `live-executor`), manual and visualization flows |
| HLD | §7.3–7.4, §8, §9, §10 | Coverage matrix/gate, option execution/risk paragraph, manual/deployment/visualization/isolation decisions, rewritten workspace table |
| HLD | §11–§15 | Event-delivery row, failure rows, quality rows, new roadmap table with gates G0.10–G7.6, risks R15–R21 |
| HLD | §16, §17 | ADR-026…036, glossary |
| LLD | §2.7 | Durable event delivery (classes, journal, checkpoints, outbox, idempotency catalogue, feed states, T-EV-1…10) |
| LLD | §4.4.1, §4.8.1 | Calendar version, reason codes, coverage matrix, eligibility gate; extra repositories and `TradeChain` |
| LLD | §5.1.9 | Feature display/explain/repaint/pins, persisted deployment series |
| LLD | §8.4.8, §8.6.8–9 | Fill sources and quote fills; option risk semantics; exit priority |
| LLD | §8.8.2–8.8.4 | Manual paper trading; deployment state machine; partial fills/cancels/corrections |
| LLD | §8.10.5, §8.15 | Metric detail contract; execution-semantics register |
| LLD | §9.3.1, §9.5.1 | Additional ledger events; schema layout, triggers, new tables |
| LLD | §10.5, §11.7.1 | Isolation; ML experiment completeness |
| LLD | §12.2.1, §12.3, §12.4 | New/amended endpoints, `LiveChain`, channels and conflation, error codes |
| LLD | §13.2–13.4, §14.3.1, §15.1, App. C | Chart adapter v1.2, workspaces, restore/power-loss drills, acceptance matrix, gate register |
| LLD | §17 | Tickets T0.14, T0.15, T1.7, T1.8, T2.4, T3.8, T3.9, T4.7, T5.7, T5.8, T6.7, T6.8, T7.7–T7.13, T8.9, T9.3 |
### 2.2 Modifications
| Where | Change |
|---|---|
| HLD P2 | LTP removed from executable sources |
| HLD §5.2 | Process-communication paragraph rewritten; `paper-runner` row |
| HLD §14 | Roadmap table replaced (phases keep their numbers; Phase 7 split 7a/7b/7c) |
| LLD §4.10.5 | Event transport replaced by §2.7 |
| LLD §8.6.2 | RK-08 uses the resolved risk basis; RK-22 added; evaluation order updated; profile gains `overnight_risk_basis`; `ceiling_mode` gains `ADVISORY` (MANUAL accounts only) |
| LLD §9.5 | `accounts`, `ledger_events`, `orders`, `fills` DDL amended in place (kind, mode FK, origin, timestamps, order types, lot/tick, fill source); `paper_deployments` sketch superseded by `deployments` |
| LLD §12.2 | Option-chain rows and the deployment-action row marked superseded by §12.2.1 |
| LLD §13 | Chart adapter, workspaces and tests rewritten; `/options` becomes live-only |
| LLD §8.8, §8.9, §8.11 | References to §10.5/§2.7; manifest fields; purge and trial rules |
### 2.3 Unresolved issues (open, not decided by this review)
`[VERIFY]` items: S-token-scope (is the collector token order-capable?), S10 per-connection `full` subscription cap, WS field availability per message type (T0.7), IV unit (S8), exchange settlement price source, Postgres/OS settings on the dev host for fsync. Decisions D-01…D-12 below. Whether `lightweight-charts` at the pinned version supports time-zone formatting (T1.7 decides with evidence).

## 3. Requirement traceability
HLD § / LLD § / focused doc § / tickets / tests / status. Status is `DESIGNED` for every row.
| Req | Topic | HLD | LLD | Focused doc | Tickets | Tests |
|---|---|---|---|---|---|---|
| 1 | Preserve architecture | §2, §11, §16 | §0–§1 | — | — | import-linter (existing) |
| 2 | Durable restart-safe events | P14, §5.2, §12, ADR-026 | §2.7, §4.10.5, §8.8, §9.5.1 | — | T0.15, T0.9, T7.7 | T-EV-1…10 |
| 3 | Paper/live isolation | P15, §4, §12, ADR-027 | §10.5, §9.5/9.5.1 | — | T1.8, T7.12, T9.3 | T-ISO-1…10 |
| 4 | Option execution and risk | §8, ADR-028, R17 | §8.6.2, §8.6.8, §8.6.9 | BACKTESTING §1.9 | T7.8, T6.8 | T-RK-27…32 |
| 5 | Data quality / coverage | §7.3–7.4, ADR-036, G0.10–11 | §4.4.1 | BACKTESTING §1.3 | T0.14 | T-DQ-1…6 |
| 6 | Option fill simulation | P2, §8, ADR-035, R19 | §8.4.8 | BACKTESTING §1.7 | T6.7 | T-SIM-15…19 |
| 7 | ML validation | §14 Ph.8 | §11.4, §11.7.1, §11.8, §11.12 | — | T8.9 (+T8.2, T8.8) | T-ML-2, 11, 13…16 |
| 8 | Accounting and recovery | §12 | §9.3.1, §8.8.4, §8.15, §14.3.1 | — | T7.13 | T-AC-1…4, T-LG-11…13, T-EV-6 |
| 9 | Charting | §10 | §13.2, §12.2.1 (`include_gaps`) | CHARTING §2–5 | T1.5, T1.7 | T-CH-1…6 |
| 10 | Chart replay | §10, ADR-032 | §12.2.1, §13.2, §15.1 row 1 | CHARTING §6 | T3.9, T5.8 | T-RP-1…8 |
| 11 | Live option chain | §10, ADR-033, R20 | §12.2.1 (`LiveChain`), §4.10.1, §2.7.7 | OPTIONS_CHAIN_UI | T2.4 | T-LC-1…8 |
| 12 | Manual paper account | §4, §9, ADR-029 | §8.8.2, §9.5/9.5.1, §12.2.1 | PAPER §1–3 | T7.9 | T-MN-1…13 |
| 13 | Deployment controls | §9, ADR-030 | §8.8.3, §9.5.1 | PAPER §4 | T7.10 | T-DP-1…10 |
| 14 | Strategy visualization | §9, §10, ADR-031 | §4.8.1, §6.6, §9.5.1, §12.2.1 | PAPER §5–6, CHARTING §5 | T7.11 | T-VZ-1…10 |
| 15 | Auto indicators | §10 | §5.1.9, §12.2.1 | PAPER §7 | T3.8, T4.7, T7.11 | T-FE-11/12, T-ST-13, T-VZ-6/7 |
| 16 | Metric inspector | ADR-034 | §8.10.5, §12.2.1 | BACKTESTING §3–5 | T5.7, T5.8, T6.8 | T-MI-1…6, T-RPT-1…4 |
| 17 | Retain workspaces | §10 | §13.3 | — | — | — |
| 18 | Canonical data access | §6, §7 | §4.8, §4.8.1 | — | T1.3, T3.8 | T-MD-5 + T-CH, T-RP |
| 19 | Account/event schemas | P15 | §9.5, §9.5.1, §2.7.2 | — | T1.8 | T-ISO-3/4/5 |
| 20 | HLD/LLD update, focused docs | header, §16 | header | the four specs | — | — |
| 21 | 15 acceptance tests | §13 | §15.1 | each spec §acceptance | per gate | see LLD §15.1 |
| 22 | Implementation order | §14 | §17 | — | all | gate register (App. C) |

## 4. Contradictions and decisions requiring your approval
Recommended default in bold; nothing below is final until you confirm.
| ID | Issue | Options | Recommendation |
|---|---|---|---|
| D-01 | **Journal location**: file journal owned by `collect_live` (survives Postgres outage) vs a Postgres events table | File journal / Postgres table | **File journal for control events; Postgres outbox for trading events.** Collector must not depend on Postgres. Quotes are not journaled (they already go to Parquet). |
| D-02 | Replayed entries after downtime | Block / allow | **Block entries older than 120 s (`STALE_REPLAY`)**, always run exits and feature updates. |
| D-03 | Isolation depth | Separate DB now / schemas+roles now, DB re-evaluated at Phase 9 | **Schemas + roles + process/credential/code separation.** |
| D-04 | Your step 8 (live chain after paper) vs step 6 (manual ticket) and the Phase 2 recorder | Keep your order / build the live-chain UI in Phase 2 | **Phase 2.** It depends only on the recorder and API; the manual ticket works without it and gains a shortcut later. |
| D-05 | Manual account governance | No ceilings at all / advisory ceilings with hard rules enforced / ENFORCE | **ADVISORY** (new third `ceiling_mode`, MANUAL accounts only). Hard rules (long-only, quote age, feed health, cash, kill switch) stay enforced even for manual orders; this is your "basic validity and system-wide safety" carve-out made concrete. |
| D-06 | Risk basis for OVERNIGHT entries | `WORST_CASE_OUTLAY` / `PLANNED_PREMIUM_STOP` | **`WORST_CASE_OUTLAY`.** Consequence: on small accounts (e.g. ₹20k) one ATM lot usually breaches a 5% per-trade ceiling, so overnight entries are rejected until the owner raises the ceiling or uses a larger account. Run `profile_feasibility` first. |
| D-07 | Visualization toggle model (your #14 granular toggles vs #15 "only when #14 is on") | master + three sub-toggles / three independent | **Master eye + Markers/Indicators/Levels sub-toggles**, default master **off** (`viz.default_visible_on_deploy` can flip it). |
| D-08 | Manual order types | MARKET only / MARKET + LIMIT | **MARKET + LIMIT, DAY.** Needed for cancel/partial-fill to be meaningful; LIMIT matching is new simulator work (T7.9). SL/IOC/AMO/modify excluded. |
| D-09 | One manual account | one active / many | **One active**, reset = archive + new. |
| D-10 | Deployments per account | one open / several | **One open deployment per strategy account**; two strategies ⇒ two accounts (keeps attribution and P&L clean). |
| D-11 | Stop policy | DRAIN default + FLATTEN / add LEAVE | **DRAIN default, FLATTEN with confirmation, no LEAVE.** |
| D-12 | IST rendering | formatter / +19 800 s shift | **Formatter**, shift kept as isolated fallback pending T1.7 evidence. |
Other corrections made without needing a choice: HLD P2 LTP wording; Sharpe/Sortino day-count ambiguity (clarified, numbers unchanged); `paper_deployments.checkpoint_event_id` replaced by `consumer_checkpoints`.

## 5. Defects found in v1.1 (all fixed in v1.2 unless noted)
1. HLD P2 allowed LTP as an executable source; every fill model uses bid/ask only.
2. §4.10.5 transport had no persistence while §8.8 and the HLD promised checkpoint replay.
3. HLD said paper and live use separate schemas; the DDL defined one set of unqualified tables.
4. `accounts.mode` allowed only BACKTEST/PAPER/LIVE — no way to distinguish manual from strategy accounts; orders had no origin, deployment link, order-type constraint or accepted/signal timestamps.
5. `decisions` were never persisted (only `feature_snapshot` inside the Decision model), so signal-vs-order-vs-fill history for the chart could not be reconstructed after restart.
6. `/options` was a historical snapshot picker; the LLD did not define live-only semantics.
7. RK-08 fell back to full outlay without saying how that interacts with `risk_pct` sizing on small accounts (made explicit; see D-06).
8. Kill-switch behaviour with open positions was undefined (now BLOCK_ENTRIES vs BLOCK_AND_FLATTEN).
9. Metric explanations, Sortino and the flat-day convention for daily returns were undefined.
10. **Not fixed (needs data, not design):** Phase 0 data ambiguities (row-count conflict, session-count differences, option timezone) remain open until G0.1–G0.4 produce evidence; v1.2 adds the coverage matrix and reason codes that make them auditable.

## 6. What was deliberately not done
No microservices, Kafka, Redis, Kubernetes or time-series database; no short options, spreads or futures trading; no SL/IOC/AMO orders; no claim that any feature exists or works; no full-chain real-time promise; no attempt to reconstruct quote history before the recorder started; no Pine execution; no Advanced Charting Library.
