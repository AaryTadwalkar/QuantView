# QuantView — Project Brief

## Project identity
QuantView is a TradingView-inspired quantitative research, backtesting, and paper/live trading platform for Indian markets (NSE/NIFTY). It combines historical charting, validated market-data pipelines, point-in-time indicators/features, rule-based strategies (`Strategy(Protocol)`), optional offline ML strategy research (`ADR-040`), event-driven backtesting, isolated/portfolio/manual paper trading, and a future gated broker-execution adapter (Upstox).

## Core goals
1. Reliable, auditable NIFTY market data (underlying candles + option chain) with strict point-in-time provenance (`bar_start`, `bar_end`, `available_at`, `ingested_at`).
2. Deterministic strategy & feature research (`Strategy(Protocol)`) with optional ML workflows (`ADR-040` — ML is an optional extension, never required for deterministic baseline).
3. Event-driven backtesting with strictly separated modes (`UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`).
4. Paper trading (`ISOLATED`, `PORTFOLIO`, and `MANUAL_PAPER` modes) sharing the same strategy, risk (`RK-01–RK-26`), and append-only ledger contracts as future live execution.
5. Gated live broker execution (Upstox Phase 9) — disabled by default (`NO-GO`) until all safety gates (`GATE-01–GATE-05`), contract-note reconciliations (`<= 1 paise`), and Three-Lock Live Arming (`ADR-026`) pass.

## Non-negotiable constraints (`P1–P18`)
- Raw collected data is NEVER overwritten without a checksummed backup (`P1`, `ADR-003`).
- No look-ahead in features, joins (`available_at <= decision_ts`), ML training, contract selection, or fill decisions (`P4`, `ADR-006`, `ADR-008`).
- Underlying directional P&L is never reported as actual option P&L (`P5`, `ADR-009`).
- Synthetic option estimates stay research-only (`SYNTHETIC_OPTIONS_ESTIMATE`).
- Live trading disabled (`NO-GO`) until Phases 0–7 gates pass and owner signs `readiness_signed.yaml` (`P7`, `ADR-012`, `ADR-026`).
- External (`VER-01–VER-06`) and Phase-0 empirical (`S1–S12`) items act as `UNVERIFIED_BLOCKER` hard gates for dependent tickets (`P12`).
- No git commits or pushes (per workspace rules).

## Repository & Documentation Authority (`ADR-007`)
- **Active Workspace:** `c:\Algo\quantview` (legacy data/collector root: `C:\Algo\Options`).
- **Canonical Documentation Suite (`DOCS/final/`, `v1.4`, `2026-10-12`):**
  - **Entrypoint:** `DOCS/final/SOURCE_OF_TRUTH_INDEX.md`
  - **Tier 1 (Authority):** `DOCS/final/ADR_REGISTER.md` (`ADR-001–ADR-041` where `status == OWNER_APPROVED`)
  - **Tier 2 (System Contract):** `DOCS/final/HIGH_LEVEL_DESIGN.md`
  - **Tier 3 (Build Contract):** `DOCS/final/LOW_LEVEL_DESIGN.md`
  - **Tier 4 (Specialized Contracts):** `CHARTING_UX.md`, `BACKTESTING_REPORT_SPEC.md`, `OPTIONS_CHAIN_UI.md`, `PAPER_TRADING_UI.md`
  - **Cross-Cutting Controls:** `TRACEABILITY_MATRIX.md`, `RECONCILIATION_AND_CHANGE_LOG.md`, `UNRESOLVED_DECISIONS_REGISTER.md`, `SOURCE_OF_TRUTH_INDEX.md`, `VALIDATION_REPORT.md`
  - **Archived Historical Inputs (Do Not Implement From):** `DOCS/person_1/` and `DOCS/person_2/`
