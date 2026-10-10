# Active Context

## Session 2026-10-10 — Phase 0A completed
**Task completed:** Documentation baseline and git safety checkpoint (read-only, no files modified).

## Phase 0A findings (key)
- **BLOCKED for G1** by one correctable issue: dev spec filename has "(2)" suffix.
- Both authoritative docs exist at `docs/` (lowercase, committed):
  - `docs/QUANTVIEW_MASTER_SYSTEM_BLUEPRINT.md` (68,815 bytes) ✅
  - `docs/QUANTVIEW_DEVELOPER_IMPLEMENTATION_SPEC (2).md` (41,359 bytes) ⚠️ wrong filename
- `AGENTS.md` lives at `docs/AGENTS.md` and `DOCS/AGENTS.md` — not at repo root.
- `DOCS/` (uppercase) is a full untracked duplicate of `docs/` — NOT authoritative.
- `docs/` (lowercase) is committed and authoritative (matches AGENTS.md path references).
- 8 contradictions found and documented — none block G1 itself after the rename.
- **One required action before G1:** rename `docs/QUANTVIEW_DEVELOPER_IMPLEMENTATION_SPEC (2).md` → `docs/QUANTVIEW_DEVELOPER_IMPLEMENTATION_SPEC.md`

## Module boundary resolution (C1 contradiction)
- 6 domains (AGENTS.md): `market_data`, `instruments`, `research`, `simulation`, `ledger`, `api`
- 12 fine-grained modules (Blueprint repo layout): nested within those 6 domains
- `research` = `features/` + `strategies/` + `contract_selection/`
- `simulation` = `backtesting/` + `paper_trading/` + `risk/`
- Record as ADR in DECISIONS.md before first code task.

## Session 2026-10-09 — Phase 0 audit

## Audit findings summary
- **Overall status: NO-GO for Phase 1+.** All 8 Phase 0 gates unmet.
- Repository has one git commit; all DOCS are untracked (never committed).
- No application module code exists (market_data, instruments, research, simulation, ledger, api, frontend — all absent).
- No tests, no CI, no Parquet pipeline operational.

## Critical data facts discovered
- Historical 1m candle rows: **432,967** (observed) vs. 451,952 (reported in data_status.md) — 19k discrepancy unresolved.
- Option chain snapshot files: **78,535** CSV files (vs. 71,617 reported — additional collection since report).
- **3 non-zero-padded expiry folder names:** `2026-02-3`, `2026-03-2`, `2026-04-7` — break naive date parsers.
- 3 option chain schema versions (V1=aggregated?, V3=current with Greeks).
- Option chain timestamps: sub-second, no timezone suffix — **timezone ambiguous**.
- Volume=0, OI=0 in all NIFTY candle rows — index behavior, needs documentation.
- `nifty_2026-02-21.csv` (live) has 1 row on a Saturday — quarantine needed.
- `data_status.py` uses `pd.date_range(freq="B")` — does NOT exclude Indian holidays.

## Broken scripts (wrong hardcoded paths)
- `data_gap_checker.py` → `C:\Algo\Data\...` (wrong)
- `data_gap_filler.py` → `C:\Algo\storage\...` (wrong)
- `migrate_options.py` → `storage/live/...` (wrong)
- `parquet_quality_checker.py` → `C:/Algo/Data/...` (wrong)
- `pyarrow` not in requirements.txt — Parquet cannot work.

## Next recommended task (smallest safe step)
**G1: Build NSE session/holiday calendar** — dependency for G2, G3, G4, G8.
- Source from NSE website official holiday lists.
- Include effective-dated NIFTY weekly expiry (Thursday → Tuesday change; verify exact NSE circular date before coding).
- Acceptance: 15+ spot-checked dates pass as unit tests.

## Open questions / decisions needed
1. Exact NSE circular date for NIFTY Tuesday expiry change (approx. April 2025 — verify).
2. Resolve 1m row count discrepancy (432,967 vs 451,952).
3. Confirm Upstox Plus plan / expired candle API access (G5).
4. Decide live 1m candle merging strategy (live per-day CSVs vs. historical bulk CSV).
5. Commit DOCS to git before next task (P1-7).
6. Clarify V1 option chain actual per-strike schema vs. aggregated structure.
