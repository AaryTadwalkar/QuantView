# AGENTS.md — QuantView Implementation Guide

**Purpose:** The single execution guide for an AI coding agent or junior developer implementing QuantView.  
**Authority:** Read this file together with the three final specifications listed below. These four files are the complete authoritative set for implementation.  
**Current state:** This is a design and plan, not proof of application implementation. Every task begins `DESIGNED`; no tests or live runs are implied by this document.

## 0. Required reading and source-of-truth rules

Read in this order:

1. `DOCS/QUANTVIEW_MASTER_SPEC.md` — product scope, architecture decisions, deployment and owner inputs.
2. `DOCS/QUANTVIEW_DATA_SPEC.md` — source semantics, schemas, data eligibility, manifests and data ownership.
3. `DOCS/QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md` — strategy timing, fills, risk, ledger, RunConfig, UI, metrics, indicators, transforms and models.
4. This `DOCS/AGENTS.md` — task order, acceptance evidence, gates, safe execution and change control.

**Path Convention:** All document references resolve from the repository root under `DOCS/`. All evidence and runtime state paths (e.g. `ops/evidence/...`, `ops/status.yaml`, `data/...`) resolve relative to the repository root.

The old `ARCHITECTURE.md`, `DATA_SPEC.md`, `ENGINE_AND_DEV_GUIDE.md`, `IMPLEMENTATION_PLAN.md`, `CHANGE_LOG.md`, `docs/engine/*`, `docs/status.yaml`, `docs/development.md`, and `docs/vision-traceability.md` are historical source material. They are **not** additional authorities and must not override the four final files. Do not create another parallel spec set.

If a conflict appears:
- Behavioural conflict → `QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md`.
- Dataset/schema/source conflict → `QUANTVIEW_DATA_SPEC.md`.
- Product scope/architecture conflict → `QUANTVIEW_MASTER_SPEC.md`.
- Task order, status or acceptance wording → this guide, but this guide cannot weaken the specifications.

Do not infer that a task is implemented because a document, file, stub or plan exists. Do not claim a command ran unless it actually ran and its output was retained.

## 1. Non-negotiable agent rules

1. **One task at a time.** Select the earliest unblocked task in the critical path. State the task ID and its acceptance contract before changing files.
2. **Read first, preserve first.** M0 is read-only inventory and preservation. Do not rename, delete, overwrite or migrate existing collector/data files before M0-01 inventory is accepted and a specific migration map is approved.
3. **No live side effects by default.** Do not call broker APIs, subscribe to a live feed, run broad backfills, alter host services, change drivers/hardware/system settings, or send external alerts without explicit owner approval. Use mocks, fixtures, dry runs and isolated temp directories first.
4. **Never place real orders.** Real-order execution is excluded from v1. No API route or UI control may submit a real order.
5. **No invented source facts.** External/broker semantics are `VERIFY` until supported by dated source evidence or a reproducible empirical comparison. Owner decisions are `PENDING_OWNER`.
6. **No look-ahead.** All timestamps are timezone-aware; internal instants UTC; exchange/session display `Asia/Kolkata`. A bar is usable only at `available_at`.
7. **No silent substitution or fabrication.** Never replace a missing option contract, invent missing bars, fill absent values with zero, or silently blend observed data with model outputs.
8. **Exact money.** Cash, fills, fees, and ledger amounts use integer paise or `Decimal` with explicit rounding; no binary float for money.
9. **Immutable provenance.** Raw payloads remain immutable. Dataset/run manifests and code/config/input hashes are pinned. Corrections create revisions, never silent overwrite.
10. **Single writer per durable dataset.** Follow the writer matrix in `QUANTVIEW_DATA_SPEC.md`. DuckDB query connections read Parquet; no shared multi-process DuckDB writer.
11. **Optional infrastructure stays optional.** No Redis/Valkey/external cache; optional adapter only if the ADR-002 measured-latency (> 500 ms p95) or restart/resume criteria are met, via an ADR (deferred until M7). No feature cache until benchmark evidence justifies it (M5-02). Do not add microservices/Kubernetes.
12. **Test-first engine.** Write hand-calculated golden expected results and get approval before implementing money/fill invariants. Correctness gates block performance claims.
13. **Keep exits/risk alive under degraded data.** Ineligible/stale data blocks new entries, but open-position monitoring, exits and risk checks continue using last valid marks with explicit stale flags.
14. **No in-process unbounded custom code.** Batch custom features execute in a subprocess with timeout/memory cap. Live feature time-budget breach marks it `UNAVAILABLE`, blocks dependent new entries, continues exits/risk, and alerts.
15. **No broad architecture rewrite.** Any change to a binding decision requires an ADR with context, decision, alternatives, migration impact, tests, rollback and the files updated in the same change.
16. **Status discipline.** `DESIGNED` = specified; `IMPLEMENTED` = code exists and was inspected; `TESTED` = actual test passed with retained output; `VERIFIED` = authoritative source/data semantics checked with evidence. Never promote status without evidence.
17. **Stop at gates.** At every gate, deliver the evidence report and wait for explicit user approval before crossing the gate.

## 2. Known environment facts and safe discovery

- Project runtime: **Python 3.11.9**.
- Python 3.13 is installed but is not the QuantView project runtime.
- OS/distro, PostgreSQL image/version, Docker/Compose version, Node.js version and package manager are `PENDING_OWNER`.
- `uv` is a proposed Python environment/dependency tool, not approved until owner confirmation.
- Production host is `PENDING_OWNER` until M0-07 records Upstox storage/offsite terms. Cloud VM in an India region if terms allow; otherwise dedicated Linux mini-PC with UPS and second disk. Disk sizing follows measured M2-10.
- WSL2 is suitable for development only; anything publishing the data lake must run on Linux or WSL2, not native Windows.
- Alerts: Telegram primary and email backup; destination/chat ID/test recipient are `PENDING_OWNER`.
- UI/browser-test stack is `PENDING_OWNER`.
- No secrets, tokens, raw broker credentials or private market-data payloads belong in Git, logs, fixtures or frontend bundles.

Before pinning dependencies, perform only read-only discovery and report actual output. Examples for the owner/developer to run and paste back:

**Windows PowerShell**
```powershell
python --version
py -0p
wsl --status
docker --version
docker compose version
node --version
npm --version
```

**Linux/WSL**
```bash
python3 --version
uname -a
cat /etc/os-release
docker --version
docker compose version
node --version
npm --version
```

PostgreSQL version must be discovered from the actual Compose image/container, not guessed. Do not run destructive Docker prune, volume removal, database reset, migration against a valuable database, or system service changes during discovery. Do not commit the output if it contains secrets or private paths.

## 3. Execution protocol

For each task:

1. Identify task ID, resolved dependencies and relevant clauses in the three specs.
2. Inspect the repository and existing files read-only. If the repo differs from the assumed structure, report the difference; do not overwrite to match a diagram.
3. Write or update a short task plan. For engine invariants, write expected results before implementation.
4. Implement the smallest complete slice with tests. Use synthetic data/mocks unless a task explicitly requires approved source evidence.
5. Run only relevant commands; record exact commands, exit codes and concise output. Never say “tests pass” if they were not run.
6. Save evidence under the task's `evidence_path` or a more specific path documented in the report. Do not use a verbal assertion as evidence.
7. Update the task status and the affected spec only when the implementation reveals a justified change. Never silently alter a spec to fit current code.
8. Report changed files, tests, evidence, open `VERIFY`/`PENDING_OWNER`, risks, rollback and next unblocked task.
9. Stop at each gate and wait for approval.

### 3.1 Typed acceptance/evidence

Every task has:
- `acceptance_type`: `command`, `file_check`, or `owner_attestation`.
- `acceptance_spec`: exact expected test, artifact, report or owner approval.
- `evidence_path`: durable output location.

`command` means execute the exact command and retain its output. `file_check` means inspect a specific artifact/schema/path and retain a report. For any code, engine, or data `file_check` task, the evidence file must contain the exact pytest command executed and its exit code 0. `owner_attestation` means the agent must not substitute its own guess: it requires explicit owner confirmation or authoritative external evidence. Evidence paths are targets until the artifacts exist.

### 3.2 M0 bounded exception

Before M0-01 is accepted, only these actions are allowed:
- read-only inventory of paths, file counts, timestamps, sizes and currently documented collector commands;
- read-only inspection of service/process state;
- copy/checksum verification to a separate destination if the owner has explicitly approved the destination and operation;
- source/document review without live API calls.

Do **not** edit/replace collector code, change dtype or schemas, start/stop a collector, alter host services, delete files, or run broad downloads before inventory and a task-specific plan are approved. M0-06 (backup), M0-07 (operational facts review), and M0-08 (backup restore verification) remain allowed under this exception following M0-01; collector code/schema/download tasks (M0-02, M0-03, M0-04, M0-05, M0-09) strictly require M0-11 contract refinement and explicit owner approval. M0-09 requires explicit owner approval of exact date/contract range and request budget before any download. No implicit approval token or free-text dependency is valid.

## 4. Status, task sizing and dependency rules

- Task sizes: `S = 0.5 person-day`, `M = 2 person-days`, `L = 5 person-days` upper-bound planning values. Split tasks larger than L. Several tasks introduced in the final repair pass use explicit custom day upper-bounds (e.g., S=1.0d for M6-12/M6-15, M=3.0d for M8-07), bringing the exact sum of the 109 tasks (108 active + 1 retired M1-07) to 258.5 person-days.
- The current 109-task plan sums to **258.5 person-days** at those upper bounds. This is a planning ceiling, not elapsed time or a delivery promise; it excludes owner waits, unknown data quality, and the required 20-session paper observation.
- Every `depends_on` entry must be either a task ID in this guide or a gate ID in §5. No free-text dependencies.
- No task is `IMPLEMENTED`, `TESTED` or `VERIFIED` until its evidence exists. Initially all tasks below are `DESIGNED`.
- Parallel work is allowed only where dependencies and single-writer ownership permit it. M2 collectors and M3 audit can overlap after safe inventory; retain separate reports and gates.

## 5. Gates and release boundaries (authoritative gate-task membership)

| Gate | Meaning | Contributing Tasks (Exact IDs) | Required evidence | Blocks |
|---|---|---|---|---|
| G0a — Skeleton and tooling | Repository skeleton, tooling, CI, migrations and schema contracts established | `M1-01`, `M1-02`, `M1-03`, `M1-04`, `M1-05`, `M1-06`, `M1-08`, `M1-09`, `M1-10`, `M1-11`, `M1-12` | Clean clone passes tooling, lint, type checks, import boundaries and disposable database migrations; schema modules round-trip | G0 and G2a (both depend on G0a) |
| G0 — Collectors | Raw capture is durable and observable | `M0-01`, `M0-02`, `M0-03`, `M0-04`, `M0-05`, `M0-06`, `M0-07`, `M0-08`, `M0-09`, `M0-10`, `M0-11`, `M2-01`, `M2-02`, `M2-03`, `M2-04`, `M2-05`, `M2-06`, `M2-07`, `M2-08`, `M2-09`, `M2-10`, `M2-11` | Raw-to-manifest reconciliation; raw survives decoder failure; `.partial` recovery; token/restart/heartbeat/duplicate-instance/disk/clock tests; every gap alerts; no unexplained capture loss | Live data-dependent features and M7 runtime |
| G1 — Data | Canonical data and eligibility are audited | `M3-01`, `M3-02`, `M3-03`, `M3-04`, `M3-05`, `M3-06`, `M3-07`, `M3-08`, `M3-09`, `M3-10`, `M3-11`, `M3-12` | Full inventory; calendar/contract master; source-semantics table; data eligibility and coverage report; idempotent normalization; zero unexplained duplicate active keys; gaps explicit; current-day daily bars unavailable intraday | Real-data strategy claims and G2a real-data integration |
| G2a — Single-leg engine | Deterministic long CE/PE engine is correct | `M4-01`, `M4-02`, `M4-03`, `M4-04`, `M4-05`, `M4-06`, `M4-07`, `M4-08`, `M4-09`, `M4-10`, `M4-11`, `M4-12`, `M4-13`, `M4-15`, `M4-18`, `M4-20`, `M4-21` | Owner-approved golden expectations; exact paise ledger; fill/stop/EOD/missing-data tests; 3 identical reruns under declared deterministic settings; CLI RunConfig; metrics manifest; long CE/PE cost/slippage report | Baseline single-leg paper runtime |
| G2b — Position groups and short/multi-leg representation | Group exits/legging/theoretical behaviour correct | `M4-14`, `M4-16`, `M4-17`, `M4-19` | Position-group ledger and exits; leg failure/unwind tests; short/multi-leg theoretical smoke suite; margin guard and visible `THEORETICAL` labels | Short/multi-leg paper features; realistic account use still separately blocked by margin `VERIFY` |
| G3 — Features | Causal features and chain have source-aware outputs | `M5-01`, `M5-02`, `M5-03`, `M5-04`, `M5-05`, `M5-06`, `M5-07`, `M5-08`, `M5-09`, `M5-10`, `M5-11`, `M5-12` | Truncation/no-future tests; memory class/chunk equivalence; optional cache invalidation only if cache exists; chain source tier/missing contracts; observed/model separation | Strategy features that require these sources |
| G4 — API/UI | Core workflows are usable and auditable | `M6-01`, `M6-02`, `M6-03`, `M6-03b`, `M6-04`, `M6-05`, `M6-06`, `M6-07`, `M6-08`, `M6-09`, `M6-11`, `M6-12`, `M6-13`, `M6-14`, `M6-15` | OpenAPI/schema tests; data-health first; 5k-bar target measured; server-authoritative order lines; UI empty/loading/error states; licence evidence; RunConfig form matches schema | Core app readiness |
| G5 — Paper runtime | Replay/restart/paper execution are safe | `M7-01`, `M7-02`, `M7-03`, `M7-04`, `M7-05`, `M7-06`, `M7-07`, `M7-08` | Recorded-session replay comparison; no duplicate fills; restart reconciliation; stale-data/kill-switch tests; per-deployment isolation; uptime measured | Trusting paper observations |
| G6 — Research | Robustness workflow prevents leakage | `M8-01`, `M8-02`, `M8-03`, `M8-04`, `M8-05`, `M8-06`, `M8-07` | Registered hold-out; purged walk-forward/embargo; trial counter; single-use final evaluation; reproducible manifests; model leakage reports | Research conclusions beyond exploratory status |

**Gate dependency rule:** `G0` and `G2a` depend on `G0a`. `M1-07` is retired and exempt from gate membership. Each gate report must include the single command that runs that gate's whole automated suite (`pytest -m gate_<id>`) with its actual command output and exit code 0.

**Targets, not achieved claims:** collector uptime ≥99% of scheduled session minutes; stale alert ≤60 s; restart ≤5 min; raw process-crash loss window ≤1 s of messages with batched fsync and host-crash window ≤1 min; Postgres RPO ≤1 hour during sessions only after a tested hourly logical dump or WAL/PITR setup (otherwise report a ≤24-hour target with replay-based rebuild); 5k-bar server-side data-ready latency ≤300 ms; live quote-to-UI p95 ≤500 ms when measured; cold ~5-year single-strategy run ≤5 min. The ≤1 min cached-run target applies only if an optional cache is benchmark-justified and actually implemented. Correctness gates block performance gates.

After G5, observe at least 20 actual paper sessions and report uptime/alerts/reconciliation. This is a minimum observation period, not an automatic approval to place real orders.

## 6. Milestones and task registry

The task register below is the binding implementation backlog. Tasks are ordered by milestone and then by dependencies; numeric task IDs are identifiers, not a promise that a lower number is unblocked first. Detailed acceptance contracts refer back to the three final specifications. Do not infer success from an evidence path name.


### M0 — Preserve existing data and establish safe facts

#### M0-10 — Create bootstrap `AGENTS.md` before M0 work

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** —  
- **Needs:** owner  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `command`  
- **Evidence path:** `ops/evidence/M0-10.txt`
- **Acceptance contract:** Run verifiable check: `python -c "from pathlib import Path; p=Path('DOCS/AGENTS.md'); text=p.read_text(encoding='utf-8'); assert '## 0. Required reading' in text and '## 12. Required milestone report' in text; print('M0-10: DOCS/AGENTS.md verified')"` and redirect output to `ops/evidence/M0-10.txt`. The command must exit with code 0, check the actual `DOCS/AGENTS.md` path, and retain actual stdout evidence.

#### M0-01 — Inventory current collector and data

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M0-10  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/inventory.md`
- **Acceptance contract:** Pre-inventory safe acceptance only. Check/record: Read-only inventory; compare file counts and timestamps without mutating source data Deliverable target: `ops/inventory.md`; list of collector command, service state, raw/snapshot paths, disk use, known gaps Do not modify or delete existing collector files or raw data. After M0-01 inventory is accepted, refine this acceptance contract before any collector-touching implementation.

#### M0-02 — Supervise existing snapshot collector

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M0-01, M0-11  
- **Needs:** owner  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M0-02.md`
- **Acceptance contract:** Pre-inventory safe acceptance only. Check/record: Kill-process test; restart test; heartbeat timeout test Deliverable target: systemd service/unit, heartbeat and restart configuration, external dead-man alert wiring Do not modify or delete existing collector files or raw data. After M0-01 inventory is accepted, refine this acceptance contract before any collector-touching implementation.

#### M0-03 — Preserve numeric precision going forward

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M0-01, M0-11  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M0-03.md`
- **Acceptance contract:** Pre-inventory safe acceptance only. Check/record: Fixture round-trip and dtype check; compare raw source values to stored values Deliverable target: Snapshot writer change from float16 to float32/float64 where applicable; schema/version note Do not modify or delete existing collector files or raw data. After M0-01 inventory is accepted, refine this acceptance contract before any collector-touching implementation.

#### M0-04 — Daily instruments-master archive

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M0-01, M0-11  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M0-04.md`
- **Acceptance contract:** Pre-inventory safe acceptance only. Check/record: Mocked response test; duplicate-day idempotency; parse-failure preserves raw response Deliverable target: Daily raw master capture, metadata for lot size/tick size/listing date, checksum manifest Do not modify or delete existing collector files or raw data. After M0-01 inventory is accepted, refine this acceptance contract before any collector-touching implementation.

#### M0-05 — Archive expired-API responses byte-faithfully

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M0-01, M0-11  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M0-05.md`
- **Acceptance contract:** Pre-inventory safe acceptance only. Check/record: Synthetic binary/JSON payload round-trip; checksum validation; interrupted-write recovery Deliverable target: Raw response archive wrapper: original response body compressed with gzip plus SHA-256 of original bytes and capture metadata Do not modify or delete existing collector files or raw data. After M0-01 inventory is accepted, refine this acceptance contract before any collector-touching implementation.

#### M0-06 — Backup current raw/snapshot data

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M0-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M0-06.md`
- **Acceptance contract:** Pre-inventory safe acceptance only. Check/record: Copy/checksum verification; restore test is tracked by M0-08 Deliverable target: Backup manifest and copy procedure for existing `data/raw` and snapshot files to a second physical local medium (external disk/NAS) Do not modify or delete existing collector files or raw data. After M0-01 inventory is accepted, refine this acceptance contract before any collector-touching implementation.

#### M0-07 — Record critical Upstox operational facts

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M0-01  
- **Needs:** owner/credentials  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M0-07.md`
- **Acceptance contract:** Pre-inventory safe acceptance only. Check/record: Review official documentation and account-specific behavior; no live tests without approval Deliverable target: Dated VERIFY entries for expired API retention, WebSocket limits and token expiry Do not modify or delete existing collector files or raw data. After M0-01 inventory is accepted, refine this acceptance contract before any collector-touching implementation.

#### M0-08 — Verify second-medium backup restore

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M0-06  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M0-08.md`
- **Acceptance contract:** Pre-inventory safe acceptance only. Check/record: Restore representative raw and snapshot files from the second physical medium into an isolated directory; compare checksums end-to-end Deliverable target: External disk/NAS restore evidence and checksum report Do not modify or delete existing collector files or raw data. After M0-01 inventory is accepted, refine this acceptance contract before any collector-touching implementation.

#### M0-09 — Preserve oldest missing expired data if retention rolls

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M0-07, M0-11  
- **Needs:** owner approval/credentials  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M0-09.md`
- **Acceptance contract:** Record retention risk and a proposed bounded request plan. Do not execute a broad download. Before any request, require explicit owner approval of exact date/contract range and request budget; then archive raw response bytes, checksum, and checkpoint evidence. If approval is absent, retain a blocked status and evidence note. Deliverable: ops/evidence/M0-09.md.

#### M0-11 — Post-inventory contract refinement and owner approval

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M0-01  
- **Needs:** owner approval  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M0-11.md`
- **Acceptance contract:** Following M0-01 read-only inventory, refine acceptance contracts for M0-02 through M0-09 with exact paths, tool commands, and deliverable targets. Submit refined contracts to owner for explicit approval. Until M0-11 is approved by the owner, no collector code modifications, schema changes, system service adjustments, or broad API downloads may be executed.

### M1 — Repository skeleton and developer workflow

#### M1-01 — Create repository and package boundaries

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M0-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M1-01.md`
- **Acceptance contract:** Check/record: Import-boundary check; package import smoke tests Deliverable target: `apps/web`, `services/collector_snapshot`, `services/collector_ws`, `services/backfill`, `services/api`, `services/worker_compute`, `services/worker_data`, `services/live_daemon`, `packages/*` (including `packages/db`), `tests`, `config`, `ops` Evidence must support: Clean clone produces the intended layout; imports obey dependency direction

#### M1-02 — Establish tooling and CI

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M1-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M1-02.md`
- **Acceptance contract:** Check/record: CI on clean clone; intentional failing fixture confirms checks fail correctly Deliverable target: Lint, type checking, pytest, import-linter, CI workflow, pinned dependency lockfile Evidence must support: Green clean-clone run with recorded versions and command output

#### M1-03 — Add configuration, logs and correlation IDs

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M1-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M1-03.md`
- **Acceptance contract:** Check/record: Config validation, secret-redaction and correlation propagation tests Deliverable target: Typed settings, non-secret example config, structured logs and correlation ID middleware/context Evidence must support: Test output shows malformed config rejected and secrets absent from logs

#### M1-04 — Postgres-only Compose and migration baseline

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M1-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M1-04.md`
- **Acceptance contract:** Check/record: Start/stop disposable database; migration up/down or documented forward-only test Deliverable target: Compose definition for Postgres only; Alembic baseline; systemd boot unit for Compose Evidence must support: Migration status and DB health command output; no Redis service before Phase 5

#### M1-05 — Status, ADR and evidence-report templates

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M1-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M1-05.md`
- **Acceptance contract:** Check/record: Template completeness review Deliverable target: `docs/status-template.md`, ADR template, milestone evidence-report template Evidence must support: Templates require status, commands/output, VERIFY status, gaps and next-gate prerequisites

#### M1-06 — Synthetic-data generator stub

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M1-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M1-06.md`
- **Acceptance contract:** Check/record: Same seed yields same fixture hash; schema validation Deliverable target: Seeded synthetic candles/contracts fixture generator Evidence must support: Fixture hash and schema-validation output retained

#### M1-07 — [RESERVED / RETIRED]

- **Size:** S (0 person-days)  
- **Depends on:** None  
- **Needs:** —  
- **Initial status:** `RETIRED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M1-07.md`
- **Acceptance contract:** Task ID intentionally reserved/retired to preserve stable numbering across external specifications and tools.

#### M1-08 — Add machine-readable task/ADR/VERIFY status registry

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M1-05  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M1-08.md`
- **Acceptance contract:** Check/record: Schema validation; fixture proves `TESTED`/`VERIFIED` without evidence link fails CI. Deliverable target: `ops/status.yaml` as a generated/mirrored runtime status registry (mirroring `DOCS/AGENTS.md` task definitions, never competing with it as an authority). Include automated graph cycle checker validating that the task dependency graph and gate expansion graph are strictly acyclic. Deliverable includes CI status and graph validator.

#### M1-09 — Canonical machine-readable schema modules

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M1-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M1-09.md`
- **Acceptance contract:** Check/record: Schema round-trip, nullable/decimal/timezone/enum and compatibility tests Deliverable target: Pydantic/PyArrow schema modules in `packages/data/schemas/`, generated schema docs Evidence must support: Canonical schema docs generated from modules; round-trip report retained

#### M1-10 — Production-host and sync configuration decision record

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M1-03, M0-07  
- **Needs:** owner  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M1-10.md`
- **Acceptance contract:** Check/record: Config validation and negative test for write-back; storage-terms gate check Deliverable target: `docs/owner-decisions.md`, host deployment profile, read-only checksum sync design Evidence must support: Owner decisions recorded or explicitly `PENDING`; cloud/offsite market-data sync cannot enable before VERIFY closure

#### M1-11 — Lightweight Postgres job claim and leased worker runner

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M1-04, M1-03  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M1-11.md`
- **Acceptance contract:** Check/record: Concurrent claim, lease expiry, worker crash, duplicate execution and single `worker_data` lease tests Deliverable target: Minimal jobs schema and runner using `FOR UPDATE SKIP LOCKED`, lease/heartbeat/retry fields, `worker_compute` and `worker_data` entrypoints; no separate queue service/library Evidence must support: Exactly one active `worker_data` lease; compute jobs claim safely; expired lease cannot publish canonical data

#### M1-12 — Port existing collectors and download scripts

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M0-01, M1-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M1-12.md`
- **Acceptance contract:** Check/record: CLI contract fixtures, output checksums/row counts and dry-run path tests Deliverable target: `ops/migration-map.md`; ported scripts/adapters under new `services/collector_snapshot`, `services/backfill` without changing their semantics silently Evidence must support: Each existing script is mapped to a new entrypoint, with behavior differences recorded and output parity evidence


### M2 — Collectors v1

#### M2-01 — Snapshot collector raw-first rewrite

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M0-02, M1-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M2-01.md`
- **Acceptance contract:** Check/record: Mocked API tests; raw retained on parse failure; duplicate and interrupted-write tests Deliverable target: `collector_snapshot` adapter, raw response capture, capture header, atomic manifest publish Evidence must support: Raw-to-manifest reconciliation report; no source response lost on decoder failure

#### M2-02 — Snapshot REST budget and priority

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M2-01, M0-07  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M2-02.md`
- **Acceptance contract:** Check/record: Simulated budget exhaustion; snapshot reservation; market-hours backfill pause test Deliverable target: Reserved REST quota config; request budget counters; backfill pause/throttle interface Evidence must support: Test proves snapshot quota remains reserved and backfill yields when budget is insufficient

#### M2-03 — WebSocket raw segment writer

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M1-01, M0-07  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M2-03.md`
- **Acceptance contract:** Check/record: Mocked frame stream; kill process at write boundary; checksum and recovery tests Deliverable target: `collector_ws`, `.partial` segment protocol, batched fsync, finalization manifest, connection IDs Evidence must support: Segment/manifest reconciliation; recovered `.partial` content included or quarantined with reason

#### M2-04 — SubscriptionManager and single-owner lease

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M2-03  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M2-04.md`
- **Acceptance contract:** Check/record: Mocked limit enforcement; duplicate collector start; add/remove deployment/chart subscription tests Deliverable target: Subscription set union from active deployments and chart requests; lease/lock; UI-readable effective subscription state Evidence must support: Exactly one owner can connect; duplicate instance fails before opening a second WS; effective set and rejections are inspectable

#### M2-05 — WebSocket decoder and fixtures

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M2-03, M0-07  
- **Needs:** market-hours/credentials  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M2-05.md`
- **Acceptance contract:** Inspect current dated official documentation and account-specific capabilities, record exact source URLs/date, distinguish documented fields from fixture-observed fields and unknowns, capture approved representative fixtures, and produce a field-presence/units/availability/reconnect/reset table. Implement decoded schema per `QUANTVIEW_DATA_SPEC.md §4.5` including `feed_type` (`initial_feed|live_feed|market_info`), `rho_observed`, and `vendor_ohlc` as a list keyed by interval (V3 marketOHLC). Ensure zero ask/bid depth and OI on non-option instruments are flagged in `quality_flags`, never treated as liquid zero quotes. Note `full_d30` requires Upstox Plus. Do not invent protobuf fields or claim the feed is a complete tick tape or complete chain. Deliverable target: Versioned protobuf decoder, at least two recorded session fixtures, field-presence diagnostics, and documented field mapping report. Unverified semantics remain `VERIFY`.

#### M2-06 — Token lifecycle and systemd operations

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M2-03, M1-04  
- **Needs:** owner/credentials  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M2-06.md`
- **Acceptance contract:** Check/record: Expired/missing token mock; process restart; heartbeat alert ≤60s Deliverable target: `WAITING_FOR_TOKEN` state, 08:45 token check, systemd services/timers, external dead-man alert, disk alert Evidence must support: Test output for token state, supervisor restart, alert latency and disk alert

#### M2-07 — Checkpointed expired-data backfill

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M2-02, M0-07  
- **Needs:** owner/credentials  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M2-07.md`
- **Acceptance contract:** Check/record: Mocked rate limit, restart from checkpoint, duplicate response, pause/resume tests Deliverable target: `backfill` job, per-contract/range checkpoint, retry/idempotency, throttling Evidence must support: Coverage/checkpoint report; request budget respected; no live broad download without explicit approval

#### M2-08 — Session-day runbook and scheduled jobs

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M2-01, M2-03, M2-06  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M2-08.md`
- **Acceptance contract:** Check/record: Dry-run schedule; missing-token, low-disk and failed-job paths Deliverable target: `ops/session-day-runbook.md`, systemd timers for capture, compaction, audit refresh, backup, health report Evidence must support: Runbook includes 08:45 token check, instruments master, post-close reconciliation, compaction, backup, health report

#### M2-09 — Collector fault-injection suite

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M2-01, M2-03, M2-06  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M2-09.md`
- **Acceptance contract:** Check/record: Inject each fault in isolated temp paths/mocks; no production data path Deliverable target: Tests for disk-full, clock jump, duplicate collector lease, `.partial` recovery, token expiry and supervisor restart Evidence must support: Fault matrix with expected fail-closed state and actual test results

#### M2-10 — Measure live-feed volume and storage growth

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M2-03, M2-05  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M2-10.md`
- **Acceptance contract:** Check/record: Replay recorded fixtures and measure serialization/compression at representative settings Deliverable target: `reports/feed-volume.md`: observed messages/sec by feed mode, compressed/raw GB per session/day, peak burst, retention projection and disk headroom estimate Evidence must support: Report includes methodology, fixture IDs, p50/p95/peak rates, GB/session and GB/day; host/disk sizing is based on evidence, not guesses

#### M2-11 — Provision production Linux host and read-only sync

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M1-10, M0-06, M2-06, M0-07, M2-10  
- **Needs:** owner/credentials  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M2-11.md`
- **Acceptance contract:** Check/record: Disposable/staging cutover, checksum mismatch, permissions/write-back negative test, restart test Deliverable target: Host provisioning/cutover runbook, systemd service config, disk alerts, read-only checksum-verified sync to research machine; no write-back path Evidence must support: Host decision is recorded; services supervised by systemd; sync is read-only and checksum-verified; offsite source-data storage remains disabled until terms VERIFY closes


### M3 — Data audit and canonical foundation

#### M3-01 — Read-only inventory of all datasets

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M0-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M3-01.md`
- **Acceptance contract:** Check/record: Repeatable read-only inventory; source checksums Deliverable target: `reports/data-inventory.md`; source paths, schemas, row counts, date coverage, contracts, duplicate/gap stats Evidence must support: Full inventory including expired option candles, snapshots, WS, VIX, futures, daily and intraday series

#### M3-02 — Calendar, holidays and special sessions

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M3-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M3-02.md`
- **Acceptance contract:** Check/record: Calendar uniqueness, session-boundary and known special-session tests Deliverable target: Versioned calendar dataset and source register Evidence must support: Calendar report with official source URLs, versions and verification dates; unknowns flagged

#### M3-03 — Validity-dated contract master

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M3-01, M3-02  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M3-03.md`
- **Acceptance contract:** Check/record: Effective-date selection, no-substitution and first-observation bounds Deliverable target: Contract master schema and normalizer, lot size/tick size/listing metadata, `first_observed_at` fallback Evidence must support: Contract coverage report; no contract selectable before listing date or first-observed bound

#### M3-04 — Canonical vendor underlying 1m and 1d

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M3-02, M3-03  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M3-04.md`
- **Acceptance contract:** Check/record: Idempotent normalization, duplicate/revision handling, daily close availability Deliverable target: `lake/underlying_candles/interval=1m/` and `interval=1d/`, manifests Evidence must support: 1m/1d coverage report; current-day daily bar cannot be selected intraday; 1m-derived daily remains diagnostic

#### M3-05 — Canonical option 1m candles

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M3-03  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M3-05.md`
- **Acceptance contract:** Check/record: OHLC constraints, contract mapping, duplicate active keys, zero/flat bar tests Deliverable target: `lake/option_candles/`, revisioned manifest Evidence must support: Contract/expiry coverage report; no unexplained duplicates; gaps and invalid rows explicit

#### M3-06 — Normalize snapshots v1/v2/v3 and captures

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M3-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M3-06.md`
- **Acceptance contract:** Check/record: Fixture migrations, dtype checks, duplicate keys, source-capture reconciliation Deliverable target: `option_snapshot_captures`, `option_snapshot_rows`, field-presence masks, nullable superset Evidence must support: 100% source captures retained or explicitly quarantined; IV/Greek dtypes preserved as float32/64

#### M3-07 — Derive intervals and vendor checksum report

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M3-04  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M3-07.md`
- **Acceptance contract:** Check/record: Session-boundary, partial-bar, daily-availability and checksum tests Deliverable target: Derived 3m/5m/15m/1h/4h from 1m; weekly/monthly from vendor daily; comparison report Evidence must support: Report documents deltas against vendor intervals; daily 1m aggregation is diagnostic only

#### M3-08 — Source-semantics audit

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M3-01, M3-05, M3-06  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M3-08.md`
- **Acceptance contract:** Check/record: Raw-fixture reconciliation and null/zero/reset transition tests Deliverable target: `reports/source-semantics.md` covering option volume/OI, index volume/OI, snapshot change/OI fields, Greeks and WS cumulative volume Evidence must support: Each field has source, unit/meaning, availability, permitted uses, evidence and status; unresolved VERIFY blocks dependent use

#### M3-09 — Data eligibility and coverage report

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M3-02, M3-03, M3-04, M3-05, M3-06, M3-07, M3-08  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M3-09.md`
- **Acceptance contract:** Check/record: Missing bars, stale data, invalid OHLC, contract validity, warm-up, flat bars and warning policy tests Deliverable target: `data_eligibility` dataset, stable reason codes, chosen backtest period/universe report Evidence must support: Gaps explicit; eligibility reproducible from manifest+policy; period/universe justified by actual coverage

#### M3-10 — Pin and verify Parquet profile

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M1-02, M3-04  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M3-10.md`
- **Acceptance contract:** Check/record: Metadata inspection, compatibility test, small benchmark Deliverable target: Locked DuckDB/pyarrow versions; zstd/row-group/sorted keys/statistics profile Evidence must support: Lockfile and Parquet profile report; changes require measured evidence/ADR

#### M3-11 — Exploratory strategy-family feasibility spike

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M3-09  
- **Needs:** owner  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M3-11.md`
- **Acceptance contract:** Check/record: Chronological slices, realistic cost ranges where known, null/permutation or simple baseline comparison, leakage review Deliverable target: Small DuckDB/notebook report on a predeclared set of simple directional and premium-selling hypotheses; no full engine or UI dependency Evidence must support: Report states whether any candidate merits a proper backtest; exploratory result is not a profitability claim and does not touch locked hold-out

#### M3-12 — Supporting datasets inventory & canonicalization (india_vix, nifty_futures, rates_dividends)

- **Size:** M (2.0 person-day upper bound)  
- **Depends on:** M3-01, M3-02  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M3-12.md`
- **Acceptance contract:** Check/record: Inventory, coverage, and canonicalization of supporting series: `india_vix` 1m candles, `nifty_futures_candles` 1m series, and versioned `rates_dividends` assumption series. Produce per-dataset schema, coverage, availability, and VERIFY report. Unavailable sources must remain explicitly unavailable/null with structured reason codes rather than fabricating estimates. Downstream features (model Greeks in M5-05 and the VIX filter) depend on this dataset being verified or explicitly declared as an assumption.


### M4 — Deterministic engine, metrics and RunConfig

#### M4-01 — Domain IDs, time and exact-money types

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M1-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-01.md`
- **Acceptance contract:** Check/record: Tick rounding against trader, decimal/paisa conversions, overflow and currency invariants Deliverable target: `packages/domain`: UTC timestamps, contract/order/run IDs, paise/Decimal types, tick quantizer Evidence must support: Unit test report; no binary float enters cash/fee/P&L paths

#### M4-11 — Postgres append-only LedgerWriter enforcement

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M1-04, M4-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-11.md`
- **Acceptance contract:** Check/record: Transaction rollback, duplicate idempotency key, forbidden mutation and projection rebuild tests Deliverable target: `packages/ledger` Postgres writer, append-only DB role and UPDATE/DELETE rejection trigger Evidence must support: Tests prove append-only behavior and exactly-once event application under retry

#### M4-12 — Strategy registry and plugin loader

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M1-01, M4-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-12.md`
- **Acceptance contract:** Check/record: Duplicate ID/version, invalid parameter schema, load failure isolation Deliverable target: Versioned strategy registry, entry-point/plugin discovery, schema validation and code hash Evidence must support: Registry lists each strategy/version and refuses invalid or ambiguous plugins

#### M4-13 — Prepare G2a golden expectations and approval

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M4-01  
- **Needs:** owner sign-off  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M4-13.md`
- **Acceptance contract:** Before implementation, hand-calculate expected event sequence, fills, cash/positions/equity and charge rounding for long CE/PE entry, next-open fill, stop/target gap, same-bar stop+target, market EXIT, flat bar, stale/missing data, force-flat/EOD close and tick quantization. Obtain owner approval of G2a expected outputs. Keep separate G2b golden additions for short cash flows, groups, legging and margin guard.

#### M4-02 — Golden event-loop scenarios and pre-implementation sign-off

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-01, M4-13  
- **Needs:** owner sign-off  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M4-02.md`
- **Acceptance contract:** Use M4-13's owner-approved G2a expected outputs as the test oracle before coding. Synthetic fixtures cover next-open fill, gap-through stop/target, same-bar stop+target, zero-volume flat bar, final-bar EOD, missing data and expiry; G2b-specific short/group expectations are added before M4-19.

#### M4-03 — Calendar-minute loop and event skipping

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-02, M3-02  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-03.md`
- **Acceptance contract:** Check/record: Event-order property tests; compare skip/no-skip outputs; session edge tests Deliverable target: `packages/engine` event loop, held-contract path, pending-order path, idle skip Evidence must support: Same outputs with and without idle skipping; benchmark full session flat and held-position paths

#### M4-04 — Contract selector and lifecycle

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-01, M3-03, M4-13  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-04.md`
- **Acceptance contract:** Check/record: Missing/ambiguous contract, first-observed bound, expiry-time tests Deliverable target: Point-in-time selector, no substitution, last-entry/force-flat/last-tradable constraints Evidence must support: Decision reason codes and selector evidence; no silent contract swap

#### M4-05 — Order/fill/position/risk invariants

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M4-02, M4-03, M4-04  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-05.md`
- **Acceptance contract:** Check/record: Property tests for every row of intrabar fill table; zero-volume and stale-wait scenarios Deliverable target: Order lifecycle, position-level stop/target/trailing, stop-first policy, stale-data and EOD behavior Evidence must support: Golden fill table passes; no same-bar optimistic fill; no fills on flat zero-volume bars

#### M4-06 — Fee schedule and cost attribution

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-01, M4-13  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-06.md`
- **Acceptance contract:** Check/record: Hand-computed fee examples, rounding tests, official-source reconciliation when available Deliverable target: Effective-dated fee config and per-charge calculation rules, source metadata Evidence must support: Gross, each fee, slippage and net P&L reconcile; unverified rates labelled `VERIFY`

#### M4-07 — Append-only ledger and projections

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M4-01, M4-05, M4-06  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-07.md`
- **Acceptance contract:** Check/record: Crash/retry idempotency, duplicate fill/fee, projection rebuild, settlement ordering tests Deliverable target: `packages/ledger`, `LedgerWriter`, events, projections, equity series Evidence must support: Cash/positions/equity reconcile exactly in paise; event count/hash matches after replay

#### M4-08 — Run manifest, decision context and hold-out guard

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-03, M4-07, M3-09  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-08.md`
- **Acceptance contract:** Check/record: Correlation ID propagation; overlapping-run refusal; single-use final-evaluation flag; manifest completeness Deliverable target: `runs/{run_id}/manifest.json`, `decisions/`, `config/research.yaml`, trial counter Evidence must support: Each decision has timestamp/features-or-hash/candidates/risk/reasons; hold-out override logged and single-use per strategy version

#### M4-09 — G2a long CE/PE strategy smoke suite and cost sensitivity

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-05, M4-06, M4-07, M4-08, M3-09  
- **Needs:** owner/hold-out  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M4-09.md`
- **Acceptance contract:** Run only the predeclared single-leg long CE and long PE smoke strategies, including direction switching as exit-then-entry. Produce slippage 0x/1x/2x/3x sensitivity, cost breakdown and capital-feasibility grid. Short-option and multi-leg cases belong to M4-19/G2b. No profitability claim before data/owner gates.

#### M4-10 — Backtest benchmark and reproducibility report

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-07, M4-08, M4-09  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-10.md`
- **Acceptance contract:** Three identical reruns match declared byte-identical outputs (ledger events, fills, trades, selected contracts and manifest excluding volatile host/created_at fields); money exact in paise; ratio metrics within declared tolerance. Measure cold ~5-year run against ≤5 min target. ≤1 min cached target applies only if M5-02 benchmark justifies and the cache is actually implemented; otherwise report uncached timing.

#### M4-15 — Ledger-derived metrics manifest and metric definitions

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-07, M4-08, M4-10  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-15.md`
- **Acceptance contract:** Write runs/{run_id}/metrics.json from immutable ledger/trade/equity artifacts. Implement and test gross/net P&L, per-charge costs, drawdown amount/percent/duration, win rate, average win/loss, profit factor, expectancy, exposure, trade count, long/short and CE/PE splits, time-of-day/expiry-day splits, MAE/MFE, Sharpe/Sortino and trial-count-aware Deflated Sharpe. Every metric carries value, unit, formula/definition, source events, calculation version and null reason. Same inputs/calculation version produce same metrics hash.

#### M4-14 — G2b position-side, declared-leg and margin-interface contract

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M4-02, M4-03, M4-04, M4-06, M4-07, M4-11, M4-12, G2a, M4-15  
- **Needs:** owner sign-off  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M4-14.md`
- **Acceptance contract:** Represent long/short CE/PE and one/two-leg groups with explicit legging failure/unwind states. Keep short/multi-leg realistic-account mode blocked until M4-17 verifies margin, buying power, hedge benefit, expiry changes and settlement. Theoretical tests may proceed with labelled assumptions.

#### M4-16 — Position-group exits and legging failure recovery

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M4-14, M4-05, M4-07  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-16.md`
- **Acceptance contract:** Implement PositionGroup combined marked P&L, group stop/target/trailing, coordinated exit intent, leg-level exit allowance, strategy/account exposure limits, and one-leg-filled/second-leg-failed/unwind states. Stops/targets are position/group attributes, not independent OCO orders. Partial fills remain deferred; quantity-vs-bar-volume warning is required. Golden and failure tests are required before G2b.

#### M4-17 — Margin/buying-power verification and realistic-mode guard

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-14, M4-21, M3-08, M3-09  
- **Needs:** owner/authoritative sources  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-17.md`
- **Acceptance contract:** Create a dated VERIFY record for initial/maintenance margin, spread hedge benefit, intraday/expiry margin changes, buying-power reservation, forced exits, settlement/exercise and relevant charges, consuming empirical research from M4-21. Implement a versioned interface and hard guard. If evidence is absent, short-option and short-leg REALISTIC_ACCOUNT runs are rejected or forced to THEORETICAL with a visible reason. Do not invent a margin formula.

#### M4-18 — Single RunConfig schema and CLI/config launch path

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-01, M4-08  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-18.md`
- **Acceptance contract:** Create one versioned RunConfig schema shared by CLI, YAML/JSON config, API and UI. Include dates, strategy/version/params, CE/PE/BOTH, expiry/strike policies (with min_dte/exact_expiry_date/target_delta/exact_strike fields), timeframe (1m..1d), capital_paise (required, no default)/sizing, nullable risk_policy_id and inline risk_controls (conforming to shared RiskRules Pydantic schema with override precedence), SL/TP/trailing as Decimal strings, entry/exit windows (force_flat_time 09:30..15:25), carry, fee version, slippage 0x/1x/2x/3x, fill model/evidence tier, REALISTIC_ACCOUNT/THEORETICAL, hold-out/final_evaluation, seed and frozen manifest IDs. Backtest must launch by CLI before M6. Invalid/unaffordable configs fail with stable reason codes.

#### M4-19 — G2b short/multi-leg theoretical smoke suite

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-14, M4-16, M4-17, M4-15, M3-09  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-19.md`
- **Acceptance contract:** Test short CE, short PE, long straddle/strangle and a declared spread as applicable. Test position-side accounting, group-level exits, one-leg failure/unwind, margin guard and THEORETICAL labeling. Do not claim realistic-account feasibility unless M4-17 is VERIFIED. Register each case/trial and include cost/slippage outputs.

#### M4-20 — Risk-policy evaluator engine and acceptance suite

- **Size:** M (2.0 person-day upper bound)  
- **Depends on:** M4-01, M4-05, M4-07  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-20.md`
- **Acceptance contract:** Implement `packages/risk/RiskEvaluator` executing all controls defined in ENGINE §7 using the shared `RiskRules` Pydantic schema (shared between `DATA §2.1 risk_policies.rules` and `ENGINE §19.1 risk_controls` with inline override precedence): max entry fills/day, daily loss ceiling (with realized + unrealized marks and intra-bar overshoot handling), max drawdown ceiling, max open positions/lots/gross exposure, premium/cash limits, trading windows/force-flat timing (09:30..15:25), consecutive losses and cooldown bars, stale-data entry block and open-position exit policy, min DTE and VIX/liquidity filter guards, and manual kill switch. Provide a comprehensive deterministic test suite proving each control triggers rejection or exit with stable reason codes and freezes the effective policy hash in run manifests. Strategy logic, position structure, and risk policy must remain strictly decoupled.

#### M4-21 — Early margin, buying-power & settlement schedule research

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M4-01  
- **Needs:** authoritative sources / circulars  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M4-21.md`
- **Acceptance contract:** Gather and document dated authoritative exchange circulars and broker documentation for NSE NIFTY options regarding: initial margin, SPAN/exposure requirements, spread hedge benefit offsets, intraday-to-carry margin increases, physical delivery/settlement rules, exercise fees, and forced square-off timelines. Deliver `reports/margin-settlement-evidence.md`. This research unblocks the engine guard implementation in M4-17 without waiting for position-group coding.


### M5 — Features, chain, transforms and model contract

#### M5-01 — Feature registry and schemas

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M1-01, M4-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M5-01.md`
- **Acceptance contract:** Check/record: Duplicate IDs, schema stability, warm-up declaration tests Deliverable target: Registry/decorator, Pydantic params, generated JSON schema, source tiers and memory class Evidence must support: Registry dump lists every feature's input/output/availability/warm-up/memory class

#### M5-02 — Optional feature cache after benchmark

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M5-01, M3-04  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M5-02.md`
- **Acceptance contract:** Check/record: Baseline vs cached wall-time/memory; if enabled, invalidation and checkpoint tests Deliverable target: Benchmark report first; implement monthly content-addressed cache only if measured recomputation is material Evidence must support: If benchmark does not justify caching, record the result and leave cache unimplemented; if enabled, invalidation tests pass

#### M5-03 — Built-in causal features

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M5-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M5-03.md`
- **Acceptance contract:** Check/record: Known-value, truncation and chunk-equivalence tests Deliverable target: EMA, RSI, ATR, PCR/OI features with metadata Evidence must support: 100% registered causal features pass required cut points and declared tolerance

#### M5-04 — Lazy reconstructed chain

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M3-05, M3-06, M5-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M5-04.md`
- **Acceptance contract:** Check/record: As-of joins, no future rows, missing-contract universe, point-in-time eligibility Deliverable target: DuckDB view; explicit source coverage and quality flags Evidence must support: View is lazy; no default stored chain dataset; source tier and missing contracts visible

#### M5-05 — Model Greeks for configured liquid ATM band

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M5-04, M3-12  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M5-05.md`
- **Acceptance contract:** Check/record: Solver failure, no-arbitrage sanity checks, point-in-time input tests Deliverable target: Model IV/Greeks for ATM +/- N liquid contracts, configuration and manifest fields Evidence must support: `model_*` fields remain separate from observed values; N/liquidity rule recorded in manifest

#### M5-06 — BOS/CHoCH and custom conversion acceptance

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M5-01, M5-03  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M5-06.md`
- **Acceptance contract:** Check/record: `pivot_time`/`confirmed_at`, repainting and truncation tests Deliverable target: Pivot/structure events and one reviewed Pine-to-Python conversion Evidence must support: Strategy cannot consume event before confirmation; conversion test meets §9 contract

#### M5-07 — Isolated subprocess feature runner

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M5-01, M1-02  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M5-07.md`
- **Acceptance contract:** Check/record: Timeout, memory exhaustion, malformed output and attempted unavailable dependency tests Deliverable target: Feature subprocess protocol, timeout, memory cap and structured failure result per ADR-012 Evidence must support: Faulty feature is terminated and marked `UNAVAILABLE`; other feature jobs continue; entries are blocked per engine contract

#### M5-08 — Indicator formula/variant catalogue and compatibility tests

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M5-01, M5-03  
- **Needs:** owner approval for final list  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M5-08.md`
- **Acceptance contract:** Document formula, standard variants, Pine/TradingView default compatibility target, seed/smoothing, warm-up, availability, repaint class, memory class and known-value tests for SMA, EMA, RSI, MACD, ATR, Bollinger Bands, session VWAP, Supertrend and ADX. Owner approves initial list. VWAP/volume-dependent features are unavailable until source-volume semantics are verified.

#### M5-09 — Chart transform registry and Heikin Ashi/Renko contract

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M5-01, M3-04  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M5-09.md`
- **Acceptance contract:** Implement Heikin Ashi as a derived/chart_transform output with exact versioned seed and formulas. Specify Renko brick-size, source, reversal, wick, gap/multiple-brick and confirmation-time rules; Renko UI remains UI-3/v1.1. No transform values may become tradable OHLC. Plugins declare schema, params, memory, warm-up, code hash and causal availability; pass truncation/chunk tests.

#### M5-10 — Frozen model artifact and strategy inference contract

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M5-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M5-10.md`
- **Acceptance contract:** Specify model hash/version, training data manifest, feature list and as-of semantics, label/horizon, split/embargo, inference interface, availability time, resource budget and run-manifest binding. No training inside backtest/live decision loop. R1 baselines: direction, regime, meta-labeling. R2 pattern discovery requires WS fixtures. R3 converts patterns to indicators only via frozen model contract and human review.

#### M5-11 — Core indicator implementation (MACD, Bollinger Bands, Supertrend, ADX; VWAP blocked)

- **Size:** L (5.0 person-day upper bound)  
- **Depends on:** M5-01, M5-03, M5-08  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M5-11.md`
- **Acceptance contract:** Implement vectorized and incremental causal evaluators for catalogued indicators in ENGINE §21: MACD(12,26,9), Bollinger Bands(20,2), Supertrend(10,3), and ADX(14). Implement TradingView/Pine test harness validating output equivalence across 5,000 bars. Verify session VWAP implementation remains strictly blocked/quarantined until M3-08 resolves volume semantics.

#### M5-12 — Option-chain derived features implementation (PCR, OI ROC, ATM Straddle, Delta-band OI)

- **Size:** M (2.0 person-day upper bound)  
- **Depends on:** M5-01, M5-04, M3-08  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M5-12.md`
- **Acceptance contract:** Implement causal evaluators for option-chain derived features in ENGINE §21.1: Put-Call Ratio (PCR by OI and volume, total and near-ATM), OI Rate of Change (per strike and total), ATM Straddle / Strangle premium and synthetic IV series, Delta-band aggregate OI distribution, and model IV smile/skew metrics. Require point-in-time checks verifying no look-ahead across expiry buckets or snapshots.


### M6 — API and core UI

#### M6-01 — FastAPI read/query API and typed client

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M3-09, M4-08  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-01.md`
- **Acceptance contract:** Check/record: Schema snapshots, validation, auth/origin/CORS checks Deliverable target: `services/api`, OpenAPI schema, generated TypeScript client Evidence must support: API schema tests pass; command endpoints require local auth; no wildcard CORS

#### M6-02 — Data-health and coverage page

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M6-01, M3-09  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-02.md`
- **Acceptance contract:** Check/record: API/UI contract tests; empty/partial data behavior Deliverable target: First UI page for coverage, gaps, eligibility and VERIFY flags Evidence must support: User can inspect missing sessions/contracts and reasons before running research

#### M6-03 — Chart and overlays

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M6-01, M5-03  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-03.md`
- **Acceptance contract:** Check/record: 5k-bar benchmark; chart transform correctness Deliverable target: Candle chart, overlays and trade markers; server-authoritative order lines Evidence must support: 5,000-bar data-ready latency ≤300 ms server-side; initial payload ≤5,000 bars

#### M6-04 — Results and audit panel

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M6-01, M4-08  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-04.md`
- **Acceptance contract:** Check/record: Correlation links from trade to decision artifact; pagination Deliverable target: Equity, trades, decision-context audit panel, run comparison, cost sensitivity Evidence must support: Audit panel reproduces decision inputs/reason codes from stored artifacts

#### M6-05 — Chart licence and API health

- **Size:** S (0.5 person-day upper bound)  
- **Depends on:** M6-03  
- **Needs:** owner/licence review  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M6-05.md`
- **Acceptance contract:** Check/record: Health/heartbeat and stale collector alert tests Deliverable target: Exact library/version licence evidence; process health endpoints Evidence must support: Licence status documented; all processes have health/heartbeat; stale alert ≤60s

#### M6-06 — Accounts and risk-policy CRUD

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M6-01, M4-04  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-06.md`
- **Acceptance contract:** Check/record: Validation, policy version immutability, account isolation and auth tests Deliverable target: `/accounts` and `/risk-policies` create/read/update/version endpoints and UI forms Evidence must support: Accounts and versioned risk policies can be managed; historical runs retain their frozen policy version

#### M6-07 — Backtest launch/configuration commands

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M6-01, M4-08  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-07.md`
- **Acceptance contract:** Check/record: Invalid config, overlapping-run guard, cancellation and command authorization tests Deliverable target: Backtest configuration form, launch/cancel/status command endpoints, job progress and validation Evidence must support: User can configure and launch a bounded run; all commands are logged with correlation IDs and manifest config

#### M6-08 — Dashboard and strategy browser UI

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M6-01, M6-02, M4-12  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-08.md`
- **Acceptance contract:** Implement dashboard routes/status widgets and strategy browser with family/tags, version, CE/PE/both support, required features/source tiers, params schema, data/run/deployment health, and navigation. Empty, loading, stale, partial and error states must be tested. Do not imply strategy profitability or VERIFIED status from registration alone.

#### M6-09 — RunConfig-driven backtest form and audit-linked chart flow

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M6-01, M4-18, M6-03, M6-04  
- **Needs:** UI test approach PENDING_OWNER  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-09.md`
- **Acceptance contract:** Generate UI form from the exact RunConfig schema used by CLI/API; include all required fields and validation, CE/PE/BOTH, capital, risk toggles, fee/slippage/fill/mode, hold-out and seed. Results panel remains on the chart page and links trade markers to decision context, selected contract, fills, ledger and metrics definitions. UI test framework remains PENDING_OWNER; API/schema/component tests still required.

#### M6-03b — UI-1 Per-strike option chart with trade markers

- **Size:** M (2.0 person-day upper bound)  
- **Depends on:** M6-01, M6-03, M5-04  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-03b.md`
- **Acceptance contract:** Implement strike-specific option candle chart visualization in the primary UI. Support selecting CE/PE and strike from backtest trade markers or contract selector. Overlay entry, exit, stop-loss, and target execution lines directly on option price candles using `UtcEpochSec` coordinates. Point-in-time checks verify only historical bars up to current replay/audit cursor are visible.

#### M6-11 — UI-1 Schema-driven indicator settings dialogs & visibility controls

- **Size:** M (2.0 person-day upper bound)  
- **Depends on:** M6-01, M6-03, M5-01, M5-08  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-11.md`
- **Acceptance contract:** Implement interactive settings dialog for all catalogued indicators (EMA, SMA, RSI, MACD, ATR, Bollinger, Supertrend, ADX). Render parameter inputs dynamically from feature registry Pydantic JSON schemas. Allow toggling indicator visibility, color/style, and pane allocation without triggering a full page reload or chart recreation.

#### M6-12 — UI-2 Heikin Ashi chart-type switcher UI

- **Size:** S (1.0 person-day upper bound)  
- **Depends on:** M6-03, M5-09  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-12.md`
- **Acceptance contract:** Implement chart-type toggle control (Standard Candlestick vs Heikin Ashi) in UI header. Wire to M5-09 Heikin Ashi transform API. Display a clear visual indicator that Heikin Ashi candles are synthetic transforms and cannot be used as tradable execution levels.

#### M6-13 — UI-2 Basic drawings persistence & rendering

- **Size:** M (2.0 person-day upper bound)  
- **Depends on:** M6-01, M6-03  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-13.md`
- **Acceptance contract:** Implement basic drawing tools on the main candle chart: horizontal price line, vertical time line, trend line, and rectangular zone. Drawing objects serialize to JSON (`UtcEpochSec` time, price coordinates, styling) and persist to PostgreSQL `chart_drawings` table via `/api/v1/charts/drawings` REST endpoints. Support drawing reload upon chart navigation and symbol change.

#### M6-14 — UI-1 /paper and /settings screens implementation

- **Size:** M (2.0 person-day upper bound)  
- **Depends on:** M6-01, M6-06, M6-08  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-14.md`
- **Acceptance contract:** Implement `/paper` overview screen (active deployments, open positions, daily P&L, margin utilization, kill-switch status, and manual paper trade ticket) and `/settings` screen (data paths, collector supervision statuses, database connection states, and API key presence).

#### M6-15 — UI-3 API and data contract freeze

- **Size:** S (1.0 person-day upper bound)  
- **Depends on:** M6-01, M5-04, M5-12  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M6-15.md`
- **Acceptance contract:** Formally freeze and validate OpenAPI contracts for UI-3 features in `services/api`: `/api/v1/option-chain`, `/api/v1/option-chain/metrics`, and `/api/v1/charts/layouts` per ENGINE §26. Verify mock and fixture responses conform strictly to pydantic schemas. UI implementation of full chain matrix and multi-chart layouts remains deferred to UI-3/v1.1.


### M7 — Live runtime and paper accounts

#### M7-01 — FrameBus local transport and raw replay

- **Size:** M (2 person-day upper bound)  
- **Depends on:** G0, G1, G2a, M1-04  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M7-01.md`
- **Acceptance contract:** Check/record: Duplicate/reordered/gapped frames, restart offset, replay and backpressure tests; measure p95 Deliverable target: `FrameBus` interface with monotonic sequence numbers, local socket/async queue adapter and resume/replay from raw segments; Redis/Valkey adapter remains optional Evidence must support: Local transport passes replay tests; add Redis/Valkey only if p95 exceeds 500 ms or a documented resume requirement justifies it; raw remains durable truth

#### M7-02 — Candle builder and feature warm-up

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M7-01, G3  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M7-02.md`
- **Acceptance contract:** Check/record: Vendor reconciliation, late event, missing minute and warm-up tests Deliverable target: Provisional/closed candle builder, late-event tolerance, feature window restoration Evidence must support: Restart enters `WARMING_UP`; no entries before warm-up and reconciliation complete

#### M7-03 — Strategy host, risk and paper broker

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M7-02, G2a  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M7-03.md`
- **Acceptance contract:** Implement isolated strategy host, quote-based paper broker, risk guards and account isolation for the G2a single-leg slice. Short/multi-leg paper deployments require G2b and verified margin/settlement; otherwise reject or visibly force THEORETICAL. Record quote age/depth/latency evidence and kill-switch tests.

#### M7-04 — Checkpoint, replay and reconciliation

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M7-02, M7-03  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M7-04.md`
- **Acceptance contract:** Check/record: Restart at every commit boundary; `.partial` recovery; duplicate fill/fee and failed reconciliation Deliverable target: Durable checkpoint and recovery; idempotent event/ledger replay Evidence must support: Three identical replay runs; no duplicate fills; reconciliation failure blocks entries

#### M7-05 — End-to-end recorded-session comparison

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M7-04, G2a  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M7-05.md`
- **Acceptance contract:** Replay one recorded session through live runtime and compare event sequence, decisions, orders, fills and state with a backtest. G2a single-leg parity is required for baseline paper; short/multi-leg comparisons require G2b and must explain differences by declared fill-evidence tier.

#### M7-06 — Live operational fault suite

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M7-04  
- **Needs:** market-hours/credentials  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M7-06.md`
- **Acceptance contract:** Check/record: Full fault injection in isolated environment Deliverable target: Disk-full, clock jump, duplicate collector lease, token expiry, stale feed, supervisor restart, alert paths Evidence must support: Session uptime ≥99% over measured sessions; every gap alerts; live quote-to-UI p95 ≤500 ms when measured

#### M7-07 — Deployment process isolation and halt behavior

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M7-03, M7-04  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M7-07.md`
- **Acceptance contract:** Check/record: Stall one host while another trades synthetic feed; kill and restart isolation tests Deliverable target: One OS process per deployment, `live_daemon` supervisor, heartbeat/time-budget controls Evidence must support: Stalled deployment enters `HALTED_DATA`; unrelated deployments continue unaffected

#### M7-08 — Manual paper orders and chart SL/TP drag

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M6-03, M7-03  
- **Needs:** owner  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `owner_attestation`  
- **Evidence path:** `ops/evidence/M7-08.md`
- **Acceptance contract:** Check/record: Order validation, acknowledgement-before-UI-commit, stale version conflict and audit event tests Deliverable target: Manual paper-order placement UI/API and draggable server-authoritative SL/TP chart lines Evidence must support: Manual paper orders are recorded; drag changes only commit after server acknowledgement; no real orders


### M8 — Research and robustness

#### M8-01 — Chronological dataset and leakage guards

- **Size:** M (2 person-day upper bound)  
- **Depends on:** G1, G3  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M8-01.md`
- **Acceptance contract:** Check/record: Future-feature, overlapping-window, post-entry leakage tests Deliverable target: Time-split dataset builder, labels/features provenance, locked hold-out config Evidence must support: Leakage report passes; hold-out is registered in config and cannot be accessed accidentally

#### M8-02 — Purged walk-forward and embargo

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M8-01, G2a  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M8-02.md`
- **Acceptance contract:** Reproducible purged walk-forward folds and embargo boundaries. G2a deterministic engine must pass first; short/multi-leg strategy folds additionally require G2b. Include synthetic boundary/overlap cases.

#### M8-03 — Trial counter and final-evaluation control

- **Size:** M (2 person-day upper bound)  
- **Depends on:** M4-08, M8-01  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M8-03.md`
- **Acceptance contract:** Check/record: Overlapping run rejection, repeated final-evaluation rejection, audit log Deliverable target: Persistent trial counter and single-use `final_evaluation=true` guard per strategy version Evidence must support: Worker refuses overlapping runs unless allowed; final-evaluation flag logged and single-use per version

#### M8-04 — Parameter sweeps and model registry

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M8-02, M8-03  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M8-04.md`
- **Acceptance contract:** Check/record: Budget limits, deterministic config, leakage and duplicate-run tests Deliverable target: Bounded sweep runner, experiment registry, model/version records Evidence must support: Every trial/run is counted and manifested; no hold-out leakage

#### M8-05 — ML baselines (research only)

- **Size:** L (5 person-day upper bound)  
- **Depends on:** M8-01, M8-02, M8-03, M8-04  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M8-05.md`
- **Acceptance contract:** Check/record: Time-split, feature leakage, repeatability and ablation tests Deliverable target: Simple baseline model pipeline, feature provenance and evaluation report Evidence must support: Research-only report with baseline and leakage evidence; no automatic promotion to live

#### M8-06 — R2 option-chain and tick pattern research path

- **Size:** L (5.0 person-day upper bound)  
- **Depends on:** M8-01, M8-04, M2-05, M5-10  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M8-06.md`
- **Acceptance contract:** Research-only discovery on point-in-time option-chain and recorded WebSocket/tick data. Require verified field semantics, manifest provenance, purged walk-forward/embargo, trial counting and hold-out protection. Candidate patterns are not strategies until converted through the frozen model/feature contract, validated out of sample and reviewed. No automatic promotion to paper/live.

#### M8-07 — R3 candle and chart pattern research path

- **Size:** M (3.0 person-day upper bound)  
- **Depends on:** M8-01, M8-04, M5-10  
- **Needs:** —  
- **Initial status:** `DESIGNED`  
- **Acceptance type:** `file_check`  
- **Evidence path:** `ops/evidence/M8-07.md`
- **Acceptance contract:** Research-only discovery of multi-bar candlestick patterns and geometric chart formations using canonical 1m/derived index candles. Decoupled from WebSocket feeds; operates strictly on historical OHLCV data under purged walk-forward evaluation. Converting candidate formations to indicators requires frozen model/feature contract and explicit human review.

## 7. Milestone order, expected duration and critical path

These are solo-developer planning ranges, not commitments. Unknown source semantics and owner waits may extend them.

| Stage | Purpose | Expected planning range | Exit |
|---|---|---:|---|
| M0 | Preservation, inventory, retention facts, backup | 5–8 working days plus later 3-session observation | M0 task evidence; do not confuse with G0 |
| M1 / G0a | Clean repository skeleton, CI, config, logs, migrations, leases | 8–12 working days | G0a: clean clone passes tooling/import/migration checks |
| M2 + M3 | Collectors and audit in parallel | 3–5 weeks each, overlap allowed | G0 and G1 independently |
| M4a / G2a | Single-leg long CE/PE engine, ledger, metrics, RunConfig | 3–5 weeks after data/golden prerequisites; engine scaffolding may run earlier on synthetic data | G2a |
| M4b / G2b | Group exits, short/multi-leg representation, margin guard | 2–4 additional weeks plus external VERIFY wait | G2b theoretical/representation gate; realistic margin eligibility may remain blocked |
| M5 | Features, chain, transforms, custom-code runner | 3–5 weeks | G3 |
| M6 | API, dashboard, strategy browser, chart, backtest form/results | 5–8 weeks | G4 |
| M7 | FrameBus, live daemon, paper broker, replay/recovery | 5–8 weeks | G5 |
| M8 | Robustness, walk-forward, ML baselines and research | 6–12+ weeks then ongoing | G6 |

Critical path for the first useful single-leg paper system: M0 → M1/G0a → M2/G0 and M3/G1 (parallel where safe; G0 and G2a depend on G0a) → M4a/G2a → M5/G3 → M6/G4 → M7/G5. A rough calendar expectation is **about 6–9 months to initial paper readiness**, plus at least 20 market sessions of observation (roughly another month if not overlapped). G6 robustness may extend total time to **8–12+ months**. Short/multi-leg paper work adds M4b and may wait on margin/settlement evidence. Recalculate from actual task durations after each milestone; do not treat this estimate as a promise.

## 8. Baseline strategy, capital sensitivity and trial accounting

Baseline smoke strategy:
- Signal input: canonical NIFTY underlying 5-minute candles.
- EMA(9)/EMA(21) bullish cross: buy ATM CE; bearish cross: buy ATM PE.
- Exit on opposite cross, configured stop/target/trailing, or force-flat no later than 15:25 Asia/Kolkata.
- Close-based signal is available only after close and queues execution for the next eligible option bar open. Do not fill on the same candle's close.
- This is a plumbing smoke test, not tuned and not evidence of edge. It must not depend on unverified option volume/OI.

Capital sensitivity levels: ₹10,000, ₹20,000, ₹50,000, ₹100,000, ₹200,000, plus any owner-added levels. Each distinct config/parameter/capital attempt is recorded in the trial registry. A rejected one-lot trade must have a stable rejection reason. Report affordability separately from edge where sizing does not bind. No single starting capital is assumed.

## 9. Owner decisions and `VERIFY` register

### `PENDING_OWNER`
- OS/distro, PostgreSQL Compose image/version, Docker/Compose, Node.js and package manager; approve or reject `uv`.
- Production host after Upstox storage/offsite terms are documented.
- Telegram recipient/chat ID and email backup recipient/test.
- Hold-out date range after M3-09 coverage report and before strategy tuning.
- Initial indicator list approval.
- UI/browser test approach.
- Any owner-added capital sensitivity levels.
- Any bounded download plan: exact contract/date range, request budget and explicit approval before network execution.

### `VERIFY` before dependent use
- Upstox expired API retention and whether historical option coverage is rolling/limited.
- WebSocket limits, feed modes, protobuf field presence/units, `volume_traded_today`, sequence/reconnect/auth/token expiry.
- Option-candle volume/OI semantics; snapshot `oi`, `volume`, `chng`, `chng_oi`, `prev_oi`; naive snapshot timezone.
- Vendor IV/Greek units and conventions.
- Historical expiry/settlement reference, exercise/settlement charges including STT basis, holiday-shifted expiries.
- Fee schedule effective dates and charge bases.
- Initial/maintenance margin, spread hedge benefit, buying-power reservation, margin changes/forced exits.
- VIX and NIFTY futures availability from current/expired endpoints.
- Chart library exact version/licence/attribution.
- Data storage/offsite terms.
- DuckDB determinism profile and cache benchmark if a cache is proposed.

Never delete a `VERIFY` item. Close it only with dated evidence and record which feature/strategy was unblocked.

## 10. Risk register

| Risk | Required mitigation / trigger |
|---|---|
| Expired API retention is short/rolling | M0-07 dated evidence; preserve raw responses; M0-09 only after bounded-download approval |
| WebSocket limits/fields/token differ from assumptions | Recorded fixtures; decoder field-presence tests; dated source-semantics report |
| Option candles are shorter/sparser than assumed | M3-01 inventory and M3-09 coverage/eligibility gate |
| OI/volume/Greek semantics misunderstood | M3-08 table; block dependent signals until verified |
| Fee/tax schedule inaccurate | Versioned fee schedule and representative transaction reconciliation |
| Short/multi-leg account risk misrepresented | M4-17 margin guard; theoretical-only until verified |
| Custom indicator conversion drift | Review, code hash, known-value, truncation and leakage tests |
| Data licensing/storage terms restrict copies | Verify before cloud/offsite sync |
| Crash/replay duplicates or loses ledger events | Idempotency, append-only DB role, five fault-injection points, projection rebuild |
| Solo-developer scope/maintenance grows | Gate approvals, UI tiers, cut list; no scope expansion without decision |
| Stale data causes unmonitored open positions | Entries halt; exits/risk continue; stale flags and forced-exit policy |
| Hold-out contamination/overfitting | Registered ranges, trial counter, purged walk-forward, single-use final evaluation |

## 11. Cut list if schedule slips

Cut in this order: ML beyond R1; G2b short-option and multi-leg implementation; advanced drawings and saved layouts; Renko implementation; option-chain/OI UI detail until the scheduled v1.1 slice (unless strategy dependency promotes it); multi-account UI polish; model Greeks beyond configured ATM band; nonessential performance work before correctness.

Never cut: raw-first capture, source preservation, M3 audit/eligibility, exact-money accounting, causal event ordering, golden tests, fee/slippage reporting, ledger idempotency/rebuild, `.partial` recovery, stale-data/risk halts, hold-out/trial accounting, or open `VERIFY` tracking.

## 12. Required milestone report and stop condition

Every milestone report must contain:
- Task IDs completed and files changed.
- Exact commands run and actual outputs/exit codes.
- Evidence paths and status per item.
- Gate checklist with `PASS`, `FAIL`, `PENDING_OWNER`, `VERIFY`, or `NOT_RUN`; distinguish correctness from performance.
- Open/closed VERIFY items and dated evidence for closures.
- Known gaps, deviations/ADRs, rollback instructions and next prerequisites.
- Actual duration vs estimate and revised critical path.

At each gate, stop and wait for the user's explicit approval. Do not automatically continue into the next milestone.

## 13. Versioning and change control

- Any changed decision requires an ADR: context, decision, alternatives, migration impact, tests, rollback, affected files.
- Update the relevant spec and task acceptance in the same change; no spec-only drift after implementation.
- Keep manifests, schemas, feature/model versions and run configs immutable once referenced by a run.
- Use Alembic for PostgreSQL migrations and explicit schema versions/migrations for Parquet.
- API command endpoints bind to loopback/private network, require a token on every command, check Origin and never use wildcard CORS. No roles/multi-user auth in v1.
- Keep secrets in a secure local store/environment, not in source, logs, database fields or frontend bundles.
- No unconditional Redis, feature cache, or extra infrastructure. Add only after a measured need and an ADR.

## Appendix: Vision Traceability Matrix (V-IDs)

Every numbered/lettered requirement and substantive question in `my_vision.txt` is assigned a stable V-ID below. This matrix maps user vision items to specifications and task implementations. Every item is categorized as `COVERED` or `DEFERRED`. No vision item is silently dropped.

| V-ID | Vision Item Text (from `my_vision.txt`) | Spec Section | Task ID(s) | Status | Architectural & Scope Note |
|---|---|---|---|---|---|
| `V-01` | Core full-stack architecture (UI, backend, DB, 10 core modules) | MASTER §1–§3, DATA §1–§3, ENGINE §1 | `M1-01` to `M1-06`, `M6-01` | `COVERED` | Modular monolith in Python/React + Vite + TypeScript SPA/PostgreSQL. No unnecessary microservices. |
| `V-02` | Dashboard (backtesting, launch chart, strategies, accounts, risk management, capital) | ENGINE §18.1 | `M6-08` | `COVERED` | Central operational navigation dashboard with health widgets. |
| `V-03` | Interactive chart indicators (standard market indicators + custom Pine-to-Python indicators) | ENGINE §18.1, §21 | `M5-03`, `M5-08`, `M5-11`, `M6-03` | `COVERED` | EMA, SMA, RSI, MACD, ATR, Bollinger, Supertrend, ADX; session VWAP blocked until volume semantics verified. |
| `V-04` | Indicator settings dialogs & visibility controls (parameters, colors, per-pane toggle) | ENGINE §18.1 | `M6-11` | `COVERED` | Dynamic JSON schema-driven indicator configuration dialog. |
| `V-05` | Multiple chart types switcher (candlestick, Heikin Ashi, etc.) | ENGINE §18.1, §22 | `M5-09`, `M6-12` | `COVERED` | Heikin Ashi switcher in v1; Renko UI deferred to v1.1 per ADR-007. |
| `V-06` | Chart drawing tools (lines, boxes, zones with coordinate persistence) | ENGINE §18.1, DATA §2.1 | `M6-13` | `COVERED` | Basic drawings (lines, zones) persisted in PostgreSQL `chart_drawings` table via `/api/v1/charts/drawings`. |
| `V-07` | Multiple chart layouts (multi-pane, split screens) | ENGINE §18.1, §26 | `M6-15` | `DEFERRED` | UI implementation deferred to UI-3/v1.1; REST API schema frozen in M6-15. |
| `V-08` | Per-strike option candle chart with trade markers | DATA §3, ENGINE §2, §18.1, §18.3 | `M6-03b` | `COVERED` | Displays strike-specific option OHLC with execution markers; `UtcEpochSec` integer seconds are the API/UI wire format derived from canonical UTC timestamps. |
| `V-09` | Option chain live broker panel | ENGINE §18.1, §26 | `M6-15` | `DEFERRED` | Matrix UI deferred to UI-3/v1.1; OpenAPI endpoint schemas frozen in M6-15. |
| `V-10` | OI levels visualization (separate tabs and on-chart overlay) | ENGINE §18.1, §26 | `M6-15` | `DEFERRED` | Advanced visualization deferred to UI-3/v1.1; schemas frozen in M6-15. |
| `V-11` | Timeline horizontal axis, price vertical axis (`UtcEpochSec` contract) | DATA §3, ENGINE §2, §18.3 | `M6-03` | `COVERED` | `UtcEpochSec` integer seconds wire contract for charts, markers, and replay cursor, derived from canonical UTC timestamps. |
| `V-12` | Same-page backtest results drawer & metrics display linked to chart | ENGINE §18.1, §19, §20 | `M6-04`, `M6-09` | `COVERED` | Results drawer on chart page links trade markers to ledger, fills, and metrics. |
| `V-13` | On-chart paper trade order placement & draggable SL/TP lines | ENGINE §18.1, §18.3 | `M7-08` | `COVERED` | Server-authoritative draggable SL/TP lines; market orders in v1 paper. |
| `V-14` | Backtesting terminal (strategy selection, date range from/to, CE/PE/BOTH direction) | ENGINE §19 | `M4-18`, `M6-09` | `COVERED` | Unified RunConfig schema drives CLI, API, and UI form. |
| `V-15` | Historical candle data ingestion (1m canonical, derived 3m/5m/15m/1h/4h/1d) | DATA §4.1, §11.1 | `M3-04`, `M3-07` | `COVERED` | 1m canonical Parquet lake (`DATA §4.1`); derived intervals and data eligibility audit (`DATA §11.1`). |
| `V-16` | 30-second live option chain snapshots archive & multi-version migration (v1 `prev_oi`, v2, v3) | DATA §4.3, §4.4 | `M0-01`, `M0-06`, `M3-05`, `M3-06` | `COVERED` | Schema migration preserves `prev_oi`, handles missing headers and expiry from directory (`option_snapshot_captures/rows` in `DATA §4.3, §4.4`). |
| `V-17` | Expired option candle data ingestion (1m OHLC, strike/expiry/lot_size) | DATA §4.2, §11.2 | `M3-01`, `M3-03` | `COVERED` | Canonical expired contracts schema (`option_candles` in `DATA §4.2`), contract master, and required additional datasets (`DATA §11.2`). |
| `V-18` | WebSocket live tick-by-tick stream research, schema & local storage | DATA §4.5, §11.4 | `M2-05`, `M7-01` | `COVERED` | Upstox WebSocket protobuf field analysis, local FrameBus transport. |
| `V-19` | Data transition, gap handling & source-semantics audit | DATA §8, §11.5, §11.6, §11.7 | `M3-08`, `M3-09` | `COVERED` | Comprehensive audit: volume/OI units, gaps, lot-size 75->65 transition, eligibility flags. |
| `V-20` | PostgreSQL operational database design + Parquet/DuckDB hybrid storage | MASTER ADR-002, ADR-004, DATA §2, §2.1 | `M1-04`, `M1-09`, `M4-11` | `COVERED` | PostgreSQL for transactional state/ledger; Parquet/DuckDB for analytical market data. |
| `V-21` | Snapshot merge design & lazy reconstructed chain view | MASTER ADR-006, DATA §4.4, DATA §4.8 | `M3-05`, `M5-04` | `COVERED` | DuckDB lazy view over normalized snapshots; no default massive stored chain table. |
| `V-22` | Technical indicators compute vs store & monthly content-addressed feature cache | MASTER ADR-007, ENGINE §21 | `M5-01`, `M5-02` | `COVERED` | Stated deviation: on-the-fly computation default; cache conditional on benchmark justification. |
| `V-23` | Custom PineScript-to-Python conversion & indicator isolation | MASTER ADR-012, ENGINE §9, §21 | `M5-06`, `M5-07`, `M5-08` | `COVERED` | Subprocess isolation with memory/time cap; strict causal confirmation rules. |
| `V-24` | Price action structure overlay (BOS / CHoCH deterministic detection) | ENGINE §3.3, §21.2 | `M5-06` | `COVERED` | Full deterministic algorithm: swing pivots, break validation, confirmed_at timing. |
| `V-25` | Chart transforms (Heikin Ashi & Renko brick contracts) | ENGINE §22 | `M5-09`, `M6-12` | `COVERED` | Heikin Ashi UI-ready; Renko mathematical contract defined, UI deferred to v1.1. |
| `V-26` | Option chain derived features (PCR, OI ROC, ATM Straddle, Delta-band OI, model Greeks) | ENGINE §21.1, DATA §4.8 | `M5-05`, `M5-12` | `COVERED` | Causal evaluators for PCR, OI ROC, ATM straddle, delta-band OI, and model Greeks. |
| `V-27` | Point-in-time causal backtesting engine (7-step loop, calendar-minute tick clock) | MASTER ADR-008, ADR-009, ENGINE §4, §5, §8 | `M4-01` to `M4-05` | `COVERED` | Deterministic event clock, causal tick delivery, idle skipping, no look-ahead. |
| `V-28` | Look-ahead bias prevention & execution timing question (Close signal -> next open fill; Open signal -> close fill rejected) | ENGINE §3.1, §4, AGENTS §8 | `M4-02`, `M4-05` | `COVERED` | Explicitly answers question: open-based signal at close entry is rejected; fills at next open. |
| `V-29` | Point-in-time contract selector & lifecycle management | ENGINE §5, MASTER ADR-005 | `M4-04` | `COVERED` | Point-in-time selection by delta/moneyness, expiry bounds, zero silent substitution. |
| `V-30` | Risk-policy module with configurable pre-backtest toggles & intraday monitoring | ENGINE §7, §19 | `M4-20`, `M6-06` | `COVERED` | Decoupled RiskEvaluator executing kill switch, daily loss ceiling, max drawdown, cooldown bars, stale-data halt, VIX/liquidity gates, exposure caps, and trading windows. |
| `V-31` | Append-only financial ledger with integer paise arithmetic | MASTER ADR-002, ADR-011, ENGINE §8 | `M4-01`, `M4-07`, `M4-11` | `COVERED` | Exact paise integer math; append-only PostgreSQL enforcement; projection rebuild. |
| `V-32` | Backtest metrics manifest (P&L, drawdown, Sharpe, Sortino, DSR) | ENGINE §20 | `M4-15` | `COVERED` | Metrics manifest with exact mathematical formulas and Bailey & López de Prado DSR. |
| `V-33` | Account segregation (isolated deployments, independent capital/ledger/risk) | MASTER ADR-011, ADR-014, ENGINE §8 | `M6-06`, `M6-14`, `M7-07` | `COVERED` | Isolated process and account boundaries for multi-strategy evaluation. |
| `V-34` | Machine learning baselines (R1: price movement, regime classification, strategy meta-labeling) | ENGINE §23 | `M5-10`, `M8-05` | `COVERED` | Research baselines under purged walk-forward; optional strategy integration. |
| `V-35` | Machine learning research (R2: option-chain/tick patterns; R3: candlestick & chart pattern discovery) | ENGINE §23 | `M8-06`, `M8-07` | `COVERED` | R2 option-chain/tick discovery and R3 candlestick pattern discovery decoupled from WS. |
| `V-36` | Live feature engine dependency evaluation (active strategy features + visible chart features) | ENGINE §3.2 | `M5-01`, `M7-02`, `M7-03` | `COVERED` | Live feature engine computes only the union of visible chart features and active strategy features; strategy features continue executing even when hidden from the chart. |
