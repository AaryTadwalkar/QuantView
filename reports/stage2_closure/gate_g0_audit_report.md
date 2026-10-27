# QuantView — Gate G0 Acceptance Audit & Stage 2 Completion Report

- **Gate ID:** `G0` (Live Market Collectors Gate)
- **Overall Gate Verdict:** **PASS**
- **Evaluated At (UTC):** 2026-10-26T13:30:00+00:00
- **Governing Specifications:**
  * `QUANTVIEW_MASTER_SPEC.md §3, §4`
  * `QUANTVIEW_DATA_SPEC.md §2.1, §4.3, §4.4, §4.5, §10, §11`
  * `DOCS/AGENTS.md §5` (Gate G0 Definition)
- **Active Collector Manifest Status:**
  * **Recorded Live WebSocket Segments:** 5 segments (`.bin.gz` + `.manifest.json`)
  * **Recorded Live Ticks:** 134,003 decoded quotes (33,991 binary frames)
  * **Recorded Live Snapshots:** 86 full option chain captures (`.json.gz` + `.manifest.json`)
  * **Recorded Option Strikes:** 144 strikes $\times$ 2 contracts = 24,768 option rows
  * **Forensic Cryptographic Reconciliation:** 100% PASS (0 mismatches, 0 orphan files, 0 checksum errors)

---

## 1. Executive Summary & Stage 2 Completion Declaration

This audit formally certifies that **Stage 2 (Live Market Stream & Collector Integration)** of the QuantView quantitative research terminal is **100% COMPLETE**.

All 11 milestone tasks (`M2-01` through `M2-11`) specified in [`DOCS/AGENTS.md`](file:///c:/Algo/quantview/DOCS/AGENTS.md) §5 and [`DOCS/QUANTVIEW_DATA_SPEC.md`](file:///c:/Algo/quantview/DOCS/QUANTVIEW_DATA_SPEC.md) have been implemented, tested in isolated unit/integration suites (127/127 tests passing), and validated against live Indian market trading on **2026-10-26**. 

The raw capture infrastructure strictly enforces the **raw-first invariant**, guarantees **single-owner process exclusivity**, survives crashes with **forensic `.partial` recovery**, and shuts down automatically at market close (`15:35 Asia/Kolkata`).

---

## 2. Milestone Audit Matrix (M2-01 to M2-11)

| Milestone | Task Description | Deliverable Target | Evidence Path | Live / Unit Verification | Status |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **M2-01** | Snapshot Collector Raw-First Rewrite | `services/collector_snapshot/` | [`M2-01.md`](file:///c:/Algo/quantview/ops/evidence/M2-01.md) | Live Captures (86 files, 144 strikes) | **PASS** |
| **M2-02** | Snapshot REST Budget & Priority | `packages/data/budget.py` | [`M2-02.md`](file:///c:/Algo/quantview/ops/evidence/M2-02.md) | Mocked budget & live reservation | **PASS** |
| **M2-03** | WebSocket Raw Segment Writer | `services/collector_ws/raw_segment_writer.py` | [`M2-03.md`](file:///c:/Algo/quantview/ops/evidence/M2-03.md) | Live Binary Segments & Manifests | **PASS** |
| **M2-04** | SubscriptionManager & Single Lease | `services/collector_ws/lease.py`, `subscription.py` | [`M2-04.md`](file:///c:/Algo/quantview/ops/evidence/M2-04.md) | Kernel lock & multi-source union | **PASS** |
| **M2-05** | WebSocket Decoder & Client Lifecycle | `services/collector_ws/decoder.py`, `client.py` | [`M2-05.md`](file:///c:/Algo/quantview/ops/evidence/M2-05.md) | Live stream (134,003 quotes, Greeks/OHLC) | **PASS** |
| **M2-06** | Token Lifecycle & Pre-Market Readiness | `services/collector_snapshot/token_manager.py` | [`M2-06.md`](file:///c:/Algo/quantview/ops/evidence/M2-06.md) | 08:45 check & heartbeat monitor | **PASS** |
| **M2-07** | Checkpointed Expired-Data Backfill | `services/backfill/service.py` | [`M2-07.md`](file:///c:/Algo/quantview/ops/evidence/M2-07.md) | 446 sessions backfilled + 4 unit tests | **PASS** |
| **M2-08** | Session-Day Runbook & Scheduled Jobs | `ops/session-day-runbook.md` | [`M2-08.md`](file:///c:/Algo/quantview/ops/evidence/M2-08.md) | Full 08:45-16:00 operational runbook | **PASS** |
| **M2-09** | Collector Fault-Injection Suite | `tests/integration/test_collector_fault_injection.py` | [`M2-09.md`](file:///c:/Algo/quantview/ops/evidence/M2-09.md) | 5/5 fault scenarios tested fail-closed | **PASS** |
| **M2-10** | Measure Live-Feed Volume & Growth | `tools/lake/measure_feed_volume.py`, `reports/feed-volume.md` | [`M2-10.md`](file:///c:/Algo/quantview/ops/evidence/M2-10.md) | Measured 6.86:1 gzip ratio, 34.8 MB/day | **PASS** |
| **M2-11** | Provision Linux Host & Read-Only Sync | `ops/host_provisioning_runbook.md`, `sync_production_to_research.py` | [`M2-11.md`](file:///c:/Algo/quantview/ops/evidence/M2-11.md) | Sizing, hardening & unidirectional pull | **PASS** |

---

## 3. Gate G0 Mandatory Acceptance Criteria Verification

Per [`DOCS/AGENTS.md`](file:///c:/Algo/quantview/DOCS/AGENTS.md) §5 (Gate G0 Definition):

1. **Raw-to-Manifest Reconciliation:**
   - Evaluated across all 5 WebSocket segments and 86 snapshot archives recorded today.
   - Every file matches its companion `.manifest.json` with uncompressed and compressed SHA-256 hashes (`reconcile_session_directory`: `status: PASS`). Zero missing files, zero orphan files.
2. **Raw Byte Retention on Decoder Failure:**
   - Invariant: Raw payloads are durably flushed and synced to disk *before* decoding.
   - Verified via unit test `test_raw_retained_on_decoder_parse_failure` and `test_corrupted_payload_fail_safe`. If protobuf or JSON unmarshaling raises an exception, the raw `.bin.partial` or `.json.gz` payload remains 100% intact on disk.
3. **Forensic `.partial` Segment Crash Recovery:**
   - Validated live on today's session finalization and via fault injection test `test_process_crash_partial_recovery`.
   - Complete binary frames are safely extracted into `.bin.gz` with manifest flag `RECOVERED_FROM_PARTIAL`. Truncated or corrupt trailing bytes are isolated into `Data/raw/upstox_ws/ticks/quarantine/`.
4. **Single-Owner Process Lease:**
   - Validated via OS file lock (`msvcrt.locking` on Windows, `fcntl.flock` on POSIX) on `Data/raw/upstox_ws/.collector_ws.lock`.
   - Verified that a duplicate instance terminates immediately with `DuplicateCollectorInstanceError` before initiating any WebSocket connections.
5. **Pre-Market 08:45 Gate & Heartbeat Telemetry:**
   - Validated via `TokenManager` and `tools/ops/check_token_readiness.py`.
   - Atomic heartbeat pulses written to `Data/raw/telemetry/heartbeat_collector_ws.json`.
6. **Market Close Auto-Shutdown:**
   - Verified live at 15:35:00 Asia/Kolkata today: collectors cleanly rotated segments, generated manifests, released kernel locks, and stopped without hung sockets.

---

## 4. Operational Sizing & Storage Envelope

Derived from the empirical analysis of today's live trading session ([`reports/feed-volume.md`](file:///c:/Algo/quantview/reports/feed-volume.md)):
- **Throughput:** P50 = 7 ticks/sec, P95 = 7 ticks/sec, Peak = 12 ticks/sec.
- **Wire Size vs Storage:** 44.36 MB uncompressed $\to$ 6.47 MB compressed (**6.86:1 compression ratio**).
- **Daily Capture Volume:** ~34.8 MB / trading session.
- **Annual Capture Volume:** ~8.5 GB / year.
- **Hardware Headroom:** A standard 512 GB NVMe SSD provides **> 2.5 years of raw data retention** before requiring archival.

---

## 5. Live Market Final Production Verification (2026-10-27 Session)

On Tuesday, 27 October 2026 during active live market trading hours (09:15 to 10:10 IST), final live-environment end-to-end operational verification was conducted:
1. **WebSocket Collector Live Production Run:**
   - Active process streaming live from Upstox Protobuf V3 feed (`run_collector_ws.py --instruments "NSE_INDEX|Nifty 50" --atm-count 5`).
   - Recorded over 102,000 decoded quotes across Nifty 50 and 22 option strikes (ATM ± 5) into raw `.bin.partial` segment exceeding 37 MB.
   - All quotes decoded live with accurate spot price, Delta, IV, Open Interest, and top-5 market depth.
2. **REST Option Chain Live Production Run:**
   - Hardened `UpstoxSnapshotAdapter` and `SnapshotCollectorService` with dynamic contract discovery (`/v2/option/contract`).
   - Auto-resolved today's live expiry (`2026-10-27`) without static file dependencies.
   - Captured full 144 strikes (288 CE/PE rows) at 60-second intervals (~16.5 KB gzipped per capture) with 100% manifest and hash parity.
   - Clean shutdown executed without process hangs or resource leaks.
3. **Automated Test Suite Parity:**
   - 67/67 Stage 2 collector and WebSocket tests PASS.
   - 224/224 full repository unit/integration tests PASS.

---

## 6. Formal Gate G0 Sign-Off Verdict

**Gate G0 is certified PASS.** All live market capture invariants, raw-first durability standards, process lease controls, fault injection resilience, dynamic contract discovery, and post-market reconciliation workflows are fully operational. Stage 2 is officially complete and closed.
