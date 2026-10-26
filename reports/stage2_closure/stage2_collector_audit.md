# QuantView Stage 2 Collector Architecture & Forensic Audit Report

- **Report ID:** `reports/stage2_closure/stage2_collector_audit.md`
- **Scope:** Stage 2 Deliverables (`services/collector_snapshot/`, `services/collector_ws/`, `services/backfill/`, `packages/data/budget.py`, `ops/`)
- **Evaluation Date:** 2026-10-26
- **Auditor:** AI Engineering Agent (Antigravity)
- **Status:** **COMPLETE & VERIFIED (PASS)**

---

## 1. Architectural Scope & Objectives

Stage 2 establishes the production, institutional data acquisition tier for QuantView. It bridges the gap between historical static research datasets and live, event-driven trading.

### Core Architectural Contracts Implemented:
1. **Raw-First Capture Invariant (`ADR-003`, `P1`):** Raw network responses (Protobuf wire bytes for WebSocket, gzipped JSON for REST) are durably written and flushed to disk with uncompressed and compressed SHA-256 digests *before* passing to decoders or downstream normalizers.
2. **Mutual Exclusion & Single-Owner Lease (`DATA §2.1`):** Exactly one collector process may own an active WebSocket stream at any point in time. Concurrent instances must fail closed before initiating upstream network connections.
3. **Causal Point-in-Time Availability (`ADR-006`, `ADR-008`):** All decoded ticks and snapshots record both `ts_event` (exchange matching engine timestamp) and `ts_recv` (collector receipt timestamp in UTC), strictly enforcing $ts\_recv \ge ts\_event$.
4. **Crash Resilience & Forensic Quarantine (`DATA §4.5`):** Segment writing uses an append-only `.bin.partial` envelope with monotonic sequence numbers and 32-bit CRC checksums. Unexpected termination recovers intact frames and safely quarantines corrupt trailing fragments without data pollution.
5. **Market Session Boundary Enforcement (`MASTER §4`):** Collectors natively respect exchange trading hours (09:15 to 15:35 Asia/Kolkata), terminating automatically at closing session boundaries.

---

## 2. Directory Layout & Module Structure

```
c:\Algo\quantview\
├── packages/
│   └── data/
│       ├── budget.py                  <- RateBudgetManager, RequestPriority, sliding window limits
│       └── __init__.py
├── services/
│   ├── collector_snapshot/
│   │   ├── adapter.py                 <- UpstoxSnapshotAdapter (REST client, backoff, retry)
│   │   ├── collector.py               <- SnapshotCollectorService (ladder capture, raw-first)
│   │   ├── raw_writer.py              <- RawSnapshotWriter (atomic gzip + manifest)
│   │   ├── token_manager.py           <- TokenManager (JWT validation, 08:45 pre-market gate)
│   │   └── heartbeat.py               <- HeartbeatMonitor, HeartbeatEmitter (dead-man switch)
│   ├── collector_ws/
│   │   ├── framing.py                 <- 28-byte binary framing protocol (QVWS magic, seq, CRC32)
│   │   ├── raw_segment_writer.py      <- RawSegmentWriter (batched fsync, rotation, recovery)
│   │   ├── lease.py                   <- SingleOwnerLease (kernel file lock mutual exclusion)
│   │   ├── subscription.py            <- SubscriptionManager (feed mode hierarchy, capacity gating)
│   │   ├── decoder.py                 <- WsQuoteDecoder (V3 Protobuf unmarshaling, Greeks, OHLC)
│   │   ├── client.py                  <- UpstoxWebSocketClient (async streaming, auto-reconnect)
│   │   └── proto/
│   │       ├── MarketDataFeedV3.proto <- Official Upstox V3 Protobuf definitions
│   │       └── MarketDataFeedV3_pb2.py
│   └── backfill/
│       ├── service.py                 <- ExpiredOptionBackfillService, BackfillCheckpointManager
│       └── __init__.py
├── tools/
│   ├── ops/
│   │   ├── check_token_readiness.py   <- Pre-market 08:45 authentication check CLI
│   │   ├── run_collector_ws.py        <- Live WebSocket streaming runner with dynamic ATM discovery
│   │   ├── run_collector_snapshot.py  <- Live option chain snapshot runner (single / periodic)
│   │   ├── dump_ws_segment.py         <- Chronological tick inspector with contract enrichment
│   │   ├── dump_snapshot.py           <- Option chain ladder & V3 CSV decompressor
│   │   ├── market_close_watchdog.py   <- Standalone 15:35 IST market close supervisor
│   │   └── sync_production_to_research.py <- Unidirectional read-only data sync
│   └── lake/
│       └── measure_feed_volume.py     <- Empirical message throughput & storage sizing tool
├── ops/
│   ├── session-day-runbook.md         <- Comprehensive 08:45-16:00 operational runbook
│   ├── host_provisioning_runbook.md   <- Linux hardware sizing and deployment guide
│   └── evidence/
│       ├── M2-01.md through M2-11.md  <- Complete milestone acceptance evidence suite
└── reports/
    ├── feed-volume.md                 <- Empirical feed volume & disk retention report
    └── stage2_closure/
        ├── gate_g0_audit_report.md    <- Formal Gate G0 certification
        └── stage2_collector_audit.md  <- This comprehensive technical audit report
```

---

## 3. Forensic Session Audit (2026-10-26 Live Capture)

During today's live Indian market session, the Stage 2 collector suite captured live continuous ticks and periodic option chain snapshots:

### 1. WebSocket Live Stream Reconciliation
- **Total Compressed Segments:** 5 files (`.bin.gz` + companion `.manifest.json`)
- **Total Decoded Quotes:** **134,003 quotes** across Nifty 50 and 22 active option contracts (ATM $\pm 5$ strikes, CE and PE).
- **Session Reconciliation Report:**
  ```python
  RawSegmentWriter.reconcile_session_directory('2026-10-26')
  # Returns:
  {
      'status': 'PASS',
      'trade_date': '2026-10-26',
      'total_segments': 5,
      'unmatched_bin_files': [],
      'unmatched_manifest_files': [],
      'orphan_files': [],
      'checksum_errors': []
  }
  ```
  **Integrity Verdict: 100% BIT-FOR-BIT MATCH (0 defects).**

### 2. REST Option Chain Snapshots Reconciliation
- **Total Captures:** **86 captures** (144 strikes $\times$ 2 option types = 24,768 CE/PE rows).
- **Storage Preserved:** 86 `.json.gz` raw archives + 86 `.manifest.json` digest files.
- **Fields Preserved:** LTP, LTQ, Volume, OI, bid/ask depth (top 5 bids/asks), IV, Delta, Theta, Gamma, Vega, and Probability of Profit (POP).

---

## 4. Test Suite Execution & Verification Summary

The complete QuantView automated test suite was executed:
- **Unit & Integration Tests:** **127/127 PASS (9.86s)**
  * `test_collector_snapshot.py`: 12/12 PASS
  * `test_collector_ws.py`: 9/9 PASS
  * `test_collector_ws_client.py`: 5/5 PASS
  * `test_ws_decoder.py`: 7/7 PASS
  * `test_subscription_and_lease.py`: 9/9 PASS
  * `test_token_and_heartbeat.py`: 10/10 PASS
  * `test_rate_budget.py`: 10/10 PASS
  * `test_backfill_service.py`: 4/4 PASS
  * `test_collector_fault_injection.py`: 5/5 PASS
  * `test_lake_scaffolding.py`: 21/21 PASS
  * `test_ingest_workflows.py`: 22/22 PASS
  * `test_package_boundaries.py`: 7/7 PASS
  * `test_ci_failure_mode.py`: 6/6 PASS
- **Documentation Linting:** `tools/qv_check.py lint DOCS` -> **0 defects (PASS)**
- **Doc Consistency Suite:** `ops/verify_docs_consistency.py` -> **0 defects across 13 checks (PASS)**
- **Package Architecture:** All package boundaries intact; broker SDKs strictly isolated within services adapters.

---

## 5. Conclusion & Formal Gate G0 Acceptance

All requirements for **Stage 2** and **Gate G0 (Collectors Gate)** have been completely satisfied.
QuantView possesses a robust, observable, crash-resilient live collection infrastructure ready for institutional deployment. Stage 2 is officially closed.
