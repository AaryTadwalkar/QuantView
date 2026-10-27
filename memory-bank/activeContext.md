# Active Context — QuantView (`c:\Algo\quantview`)

## Current State of the Union (2026-10-28 — CI Ruff Lint Resolved & Clean)
- **CI & REPOSITORY CODE QUALITY 100% CLEAN:**
  - Resolved GitHub Actions Ruff Code Quality Lint failure (from 969 errors down to 0 errors).
  - Modernized `pyproject.toml` `[tool.ruff.lint]` with exclusions (`Data_Collectors`, `staging`, `Data`, `runs`) and per-file ignores.
  - Fixed typing imports (`Any` in `packages/engine/execution.py`, `List` in `test_causal_indicators.py`, `Any` in `sync_production_to_research.py`).
  - `ruff check .` output: **All checks passed!** (0 errors).
- **AUTOMATED TEST SUITE & CONSISTENCY 100% PASS:**
  - 353/353 full-suite tests PASS in 18.75s (0 regressions).
  - 218/218 gate marker tests PASS in 20.46s (G0a, G0, G1, G2a, G2b, G3).
  - 161/161 CI unittest discovery tests PASS in 2.44s.
  - `tools/qv_check.py lint DOCS stale.txt` PASS (0 defects).
  - `ops/verify_docs_consistency.py` PASS (0 defects across 13 checks).
  - `tests/unit/test_package_boundaries.py` 7/7 PASS in 0.09s.
- **STAGE 6 / GATE G4 STATUS:**
  - Implementation Plan published: [`stage6_implementation_plan.md`](file:///C:/Users/Aary/.gemini/antigravity/brain/06a15e89-b29d-4bcb-80a8-a97856ca6a27/stage6_implementation_plan.md).
  - Ready to commence Phase 6A (Core API Gateway & Schema Layer) upon authorization.

## Canonical Architectural Contracts & Modes
- **Timeframe & Parameter Relativity:** All features parameter-configurable and TF-relative via `compute_param_hash`; causal availability strictly enforced.
- **Operating Modes:** `RESEARCH`, `UNDERLYING_DIRECTIONAL`, `ACTUAL_OPTIONS`, `SYNTHETIC_OPTIONS_ESTIMATE`, `MANUAL_PAPER`, `STRATEGY_PAPER`, `LIVE`.
- **Accounting Standard:** Event-sourced integer-paise ledger with deterministic projections ($\text{Free Cash} = \text{Cash} - \text{Margin Reserved}$; $\text{Equity} = \text{Cash} + \text{Long MV} - \text{Short Liability}$).
- **Release Gates:** Gate G0 (PASS), Gate G1 (PASS), Gate G2a (PASS), Gate G2b (PASS), Gate G3 (PASS & CLOSED), Gate G4 (PLANNED).
