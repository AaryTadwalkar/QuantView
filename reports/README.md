# QuantView Reports Directory — Structured Architecture & Index

This directory serves as the centralized repository for all verification evidence, analytical audits, compliance reports, and validation artifacts produced across the lifecycle of the QuantView platform.

All reports are organized into 5 functional domains:

```text
reports/
  ├── stage1_closure/                  # Master Stage 1 & Gate G1 closure reports
  ├── phase_validations/               # Incremental phase execution & staging validation gates
  ├── data_semantics_and_eligibility/  # Invariant proofs, semantic registries, and tradability matrices
  ├── historical_options_acquisition/  # Option candle ingestion audits, contracts index & batch logs
  ├── post_incident_audit/             # Post-incident file integrity and recovery verification
  └── README.md                        # Master reports directory index (this file)
```

---

## 1. Stage 1 Closure (`reports/stage1_closure/`)
Official completion, master producer audit, and acceptance records for **Stage 1 (Historical Data Foundation)** and **Gate G1 (Data Foundation Gate)**:

- [`stage1_producer_audit.md`](file:///c:/Algo/quantview/reports/stage1_closure/stage1_producer_audit.md): **The Master Producer Audit of Stage 1**. Exhaustive, standalone reference explaining everything completed in Stage 1, how it was engineered, mathematical models, where every file resides, precision standards, and validation evidence.
- [`gate_g1_audit_report.md`](file:///c:/Algo/quantview/reports/stage1_closure/gate_g1_audit_report.md): Formal Gate G1 audit report verifying all 12 Stage 1 tasks (`M3-01` through `M3-12`), DuckDB analytical views, and active lake totals.
- [`gate_g1_validation_results.json`](file:///c:/Algo/quantview/reports/stage1_closure/gate_g1_validation_results.json): Machine-readable Gate G1 evidence payload with timestamps, manifest SHA-256 hashes, storage partition profiles, and query latency benchmarks.

---

## 2. Phase Validations (`reports/phase_validations/`)
Chronological evidence of the phased data preparation and active lake publication loop:

- [`phase1_tooling_compliance_report.md`](file:///c:/Algo/quantview/reports/phase_validations/phase1_tooling_compliance_report.md): Audit certifying offline tooling scaffolding (`tools/lake/`), canonical Pydantic/PyArrow schemas, and non-regression test coverage.
- [`phase1b_candidate_contracts.json`](file:///c:/Algo/quantview/reports/phase_validations/phase1b_candidate_contracts.json): Filtered contract manifest defining candidate strikes for initial ingestion.
- [`phase2a_staging_report.md`](file:///c:/Algo/quantview/reports/phase_validations/phase2a_staging_report.md): Full-batch staging report for 183 candle partitions (20,936,814 rows, 225.06 MB) staged under `staging/lake_preparation_phase2a/`.
- [`phase2a_staging_validation_results.json`](file:///c:/Algo/quantview/reports/phase_validations/phase2a_staging_validation_results.json): Initial machine validation results for Phase 2A.
- [`phase2a_closure_gate_evidence.json`](file:///c:/Algo/quantview/reports/phase_validations/phase2a_closure_gate_evidence.json): 9/9 read-only closure checks evidence for Phase 2A (row counts, checksums, precision, line 432594 defensive quarantine).
- [`phase2b_lake_publication_report.md`](file:///c:/Algo/quantview/reports/phase_validations/phase2b_lake_publication_report.md): Production Data Lake publication report documenting atomic promotion to `Data/lake/`, activation of Manifest v1, and initial DuckDB views.
- [`phase2b_publication_validation_results.json`](file:///c:/Algo/quantview/reports/phase_validations/phase2b_publication_validation_results.json): Cryptographic validation evidence for Manifest v1 activation.
- [`phase3_snapshot_compaction_report.md`](file:///c:/Algo/quantview/reports/phase_validations/phase3_snapshot_compaction_report.md): Task M3-06 compaction report auditing all 82,283 live snapshot files (82,274 valid captures + 9 quarantined; 0 lost) and Manifest v2 activation.
- [`phase3_snapshot_validation_results.json`](file:///c:/Algo/quantview/reports/phase_validations/phase3_snapshot_validation_results.json): 5/5 validation gates evidence for snapshot compaction.
- [`phase4_staging_validation_results.json`](file:///c:/Algo/quantview/reports/phase_validations/phase4_staging_validation_results.json): 6/6 validation gates evidence for derived multi-timeframe candles (`M3-07`) and data eligibility (`M3-09`).
- [`snapshot_inventory_audit.json`](file:///c:/Algo/quantview/reports/phase_validations/snapshot_inventory_audit.json): Classification of all 82,283 snapshot files into v1 (9,806), v3 (72,468), empty (4), and corrupt (5).

---

## 3. Data Semantics & Eligibility (`reports/data_semantics_and_eligibility/`)
Deep-dive semantic contracts, empirical quality distributions, and interval cross-validation:

- [`source-semantics.md`](file:///c:/Algo/quantview/reports/data_semantics_and_eligibility/source-semantics.md): Authoritative register auditing 6 semantic domains (Option vol/OI, Cash index zero-volume, India VIX `oi=0` invariant, Snapshot schema evolution, Black-Scholes Greeks units, WebSocket daily session resets).
- [`data_eligibility_report.md`](file:///c:/Algo/quantview/reports/data_semantics_and_eligibility/data_eligibility_report.md): Formal evaluation of 1,161 historical trading sessions against 9 quality invariants (1,144 `ELIGIBLE`, 17 `ELIGIBLE_WITH_WARNINGS`, 0 `INELIGIBLE`).
- [`derived_intervals_vendor_comparison.md`](file:///c:/Algo/quantview/reports/data_semantics_and_eligibility/derived_intervals_vendor_comparison.md): Mathematical ground-truth comparison between derived bars (`3m`, `5m`, `15m`, `30m`, `1h`, `4h`) and historical vendor CSVs (99.89% to 100.0% match fidelity).
- [`strike_coverage_policy.md`](file:///c:/Algo/quantview/reports/data_semantics_and_eligibility/strike_coverage_policy.md): Liquidity density analysis comparing $\pm 1000$ vs $\pm 1500$ strike ranges around ATM.
- [`india_vix_session_coverage_report.json`](file:///c:/Algo/quantview/reports/data_semantics_and_eligibility/india_vix_session_coverage_report.json): Mathematical session-by-session reconciliation of the 311-bar special session delta in India VIX.

---

## 4. Historical Options Acquisition (`reports/historical_options_acquisition/`)
Provenance records, contract catalogs, and audit logs for the full 446-session option backfill:

- [`option_history_acquisition_plan.md`](file:///c:/Algo/quantview/reports/historical_options_acquisition/option_history_acquisition_plan.md): Comprehensive historical backfill plan sizing 23 expiries, 446 sessions, and ~32,000 API payloads.
- [`option_history_phase1_pilot_report.md`](file:///c:/Algo/quantview/reports/historical_options_acquisition/option_history_phase1_pilot_report.md): Verification report on initial pilot contract acquisitions.
- [`expired_contracts_index.json`](file:///c:/Algo/quantview/reports/historical_options_acquisition/expired_contracts_index.json): Master contract catalog containing 32,232 expired option contracts mapped across 446 sessions and 23 expiries with strike decimal precision.
- [`historical_options_2025_h1_audit_report.md`](file:///c:/Algo/quantview/reports/historical_options_acquisition/historical_options_2025_h1_audit_report.md): Batch 1 ingestion audit (Jan 2025 – Jun 2025; 116 sessions, 5,118,315 bars, 6,106 manifests).
- [`historical_options_20250620_20260203_audit_report.md`](file:///c:/Algo/quantview/reports/historical_options_acquisition/historical_options_20250620_20260203_audit_report.md): Batch 2 ingestion audit (Jun 2025 – Feb 2026; 156 sessions, 7,003,462 bars, 10,510 manifests).
- [`historical_options_20260204_20261021_audit_report.md`](file:///c:/Algo/quantview/reports/historical_options_acquisition/historical_options_20260204_20261021_audit_report.md): Batch 3 ingestion audit (Feb 2026 – Oct 2026; 174 sessions, 8,210,644 bars, 15,616 manifests).
- [`live_collector_audit.md`](file:///c:/Algo/quantview/reports/historical_options_acquisition/live_collector_audit.md): Code audit of `Data_Collectors/live_option_chain.py` verifying header schema changes and capture mechanisms.

---

## 5. Post-Incident Repository Audit (`reports/post_incident_audit/`)
Complete directory inventories, SHA-256 baseline verification, and Recycle Bin audit logs verifying full repository recovery following the accidental folder deletion event.
