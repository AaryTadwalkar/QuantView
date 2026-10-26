# QuantView Operational Runbook: Session-Day & Scheduled Jobs

- **Target Systems:** QuantView Production Collector Host (Linux / Windows)
- **Timezone:** `Asia/Kolkata` (IST, UTC+05:30)
- **Specification Reference:** `QUANTVIEW_MASTER_SPEC.md §4`, `QUANTVIEW_DATA_SPEC.md §10`, Task `M2-08`
- **Revision Date:** 2026-10-26

---

## 1. Daily Trading Session Timeline (Asia/Kolkata)

```
08:45 IST ─── Pre-Market Auth Gate (check_token_readiness.py)
09:00 IST ─── NSE Pre-Open Session
09:14 IST ─── Start WebSocket Collector (run_collector_ws.py --atm-count 5)
09:15 IST ─── Start Periodic Snapshot Loop (run_collector_snapshot.py --loop)
15:30 IST ─── NSE Continuous Trading Ends / Closing Auction Begins
15:35 IST ─── Automatic Clean Collector Shutdown (Flushes buffers, releases locks)
15:36 IST ─── Post-Close Segment Recovery & Cryptographic Reconciliation
16:00 IST ─── Daily Lake Compaction, Secondary Backup & Health Audit
```

---

## 2. Standard Operating Procedures (SOP)

### Step 1: 08:45 IST — Pre-Market Authentication Check
The operator or scheduled timer executes:
```powershell
.\venv\Scripts\python.exe tools/ops/check_token_readiness.py
```
- **Expected Output:**
  ```text
  =================================================================
   QUANTVIEW 08:45 ASIA/KOLKATA PRE-MARKET AUTHENTICATION CHECK
  =================================================================
   Status:        VALID
   Ready:         True
   Checked At:    2026-10-27T03:15:00+00:00
   Expires At:    2026-10-27T22:00:00+00:00
   Details:       Upstox token is valid until 2026-10-27T22:00:00+00:00.
  =================================================================
  ```
- **Error Remediation:**
  - If `Status: WAITING_FOR_TOKEN` or `EXPIRED`:
    1. Log in to [Upstox Developer Console](https://account.upstox.com/developer/apps).
    2. Regenerate active daily access token.
    3. Update `UPSTOX_ACCESS_TOKEN` in `.env`.
    4. Re-run `check_token_readiness.py`.

---

### Step 2: 09:14 IST — Launch Live WebSocket Collector
Launch the streaming WebSocket collector with dynamic ATM $\pm 5$ strike options:
```powershell
.\venv\Scripts\python.exe tools/ops/run_collector_ws.py --instruments "NSE_INDEX|Nifty 50" --atm-count 5
```
- **Operational Invariants:**
  - Single-owner kernel lock acquired at `Data/raw/upstox_ws/.collector_ws.lock`.
  - Discovers and subscribes to Nifty 50 + 22 active options (ATM $\pm 5$ strikes, CE and PE).
  - Raw binary frames streamed to `Data/raw/upstox_ws/ticks/trade_date=YYYY-MM-DD/`.
  - Auto-shutdown is **ACTIVE** by default for `15:35` IST.

---

### Step 3: 09:15 IST — Launch Periodic Option Chain Snapshot Loop
In a dedicated process or terminal:
```powershell
.\venv\Scripts\python.exe tools/ops/run_collector_snapshot.py --loop --interval-sec 60
```
- **Operational Invariants:**
  - Captures full 144-strike option chain ladder every 60 seconds.
  - Persists raw gzip payload + companion manifest to `Data/raw/upstox_rest/snapshots/trade_date=YYYY-MM-DD/`.
  - Auto-shutdown is **ACTIVE** by default for `15:35` IST.

---

### Step 4: 15:35 IST — Automatic Clean Collector Shutdown
- At `15:35:00` IST:
  - Both collectors detect session completion.
  - WebSocket client flushes in-flight frames, compresses active partial segment to `.bin.gz`, computes uncompressed/compressed SHA-256 digests, publishes `.manifest.json`, emits `STOPPED` heartbeat, and releases `.collector_ws.lock`.
  - Snapshot loop exits cleanly.

---

### Step 5: 15:36 IST — Forensic Session Reconciliation & Recovery
Execute post-market forensic audit to verify zero unfinalized segments and 100% cryptographic integrity:
```powershell
.\venv\Scripts\python.exe -c "from services.collector_ws.raw_segment_writer import RawSegmentWriter; RawSegmentWriter.recover_session_partials('YYYY-MM-DD'); rep = RawSegmentWriter.reconcile_session_directory('YYYY-MM-DD'); print(rep)"
```
- **Acceptance Criteria:**
  - `status: PASS`
  - `unmatched_bin_files: []`
  - `unmatched_manifest_files: []`
  - `orphan_files: []`
  - `checksum_errors: []`

---

### Step 6: 16:00 IST — Inspection & Secondary Backup
Inspect collected data using QuantView CLI utilities:
```powershell
# Inspect WebSocket segment quotes
.\venv\Scripts\python.exe tools/ops/dump_ws_segment.py --limit 25

# Inspect captured option chain snapshot
.\venv\Scripts\python.exe tools/ops/dump_snapshot.py --latest
```

---

## 3. Production Systemd Service Units (Linux)

For Linux deployment hosts, copy the following unit definitions to `/etc/systemd/system/`:

### 1. `quantview-token-check.service` & `.timer`
```ini
[Unit]
Description=QuantView Pre-Market Token Readiness Check
After=network.target

[Service]
Type=oneshot
User=quantview
WorkingDirectory=/opt/quantview
ExecStart=/opt/quantview/venv/bin/python tools/ops/check_token_readiness.py
```
```ini
[Unit]
Description=Timer for QuantView 08:45 Pre-Market Token Gate

[Timer]
OnCalendar=Mon..Fri *-*-* 08:45:00 Asia/Kolkata
Persistent=true

[Install]
WantedBy=timers.target
```

### 2. `quantview-collector-ws.service`
```ini
[Unit]
Description=QuantView Live WebSocket Market Data Collector
After=network.target

[Service]
Type=simple
User=quantview
WorkingDirectory=/opt/quantview
EnvironmentFile=/opt/quantview/.env
ExecStart=/opt/quantview/venv/bin/python tools/ops/run_collector_ws.py --instruments "NSE_INDEX|Nifty 50" --atm-count 5 --market-close-time 15:35
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

### 3. `quantview-collector-snapshot.service`
```ini
[Unit]
Description=QuantView Live Option Chain REST Snapshot Collector
After=network.target

[Service]
Type=simple
User=quantview
WorkingDirectory=/opt/quantview
EnvironmentFile=/opt/quantview/.env
ExecStart=/opt/quantview/venv/bin/python tools/ops/run_collector_snapshot.py --loop --interval-sec 60 --market-close-time 15:35
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

---

## 4. Failure Modes & Emergency Playbooks

| Anomaly | Immediate Impact | Resolution Playbook |
| :--- | :--- | :--- |
| **Duplicate Instance Error** (`DuplicateCollectorInstanceError`) | Second collector process fails closed immediately before network socket opens. | Check if existing process is running (`Get-Process python`). If process crashed without unlinking lock, inspect `Data/raw/upstox_ws/.collector_ws.lock` and remove stale lock only if PID is dead. |
| **Token Expired / Missing** | Pre-flight check fails with exit code 1; collectors refuse to start. | Generate valid bearer token from Upstox Developer Console and update `.env`. |
| **Network Disconnection / Upstox Disconnect** | Socket disconnects with EOF or socket error. | UpstoxWebSocketClient automatically reconnects using exponential backoff with jitter (1s $\to$ 2s $\to$ 4s ... max 30s) while persisting heartbeat telemetry. |
| **Sudden Power Loss / OS Crash** | Active segment left with `.bin.partial` extension. | Run `RawSegmentWriter.recover_session_partials()`. Incomplete frames are recovered, validated, and compressed to `.bin.gz` with `.manifest.json`. Zero valid frames lost. |
| **Low Disk Warning ($\le 10\text{ GB}$)** | Segment writer warns; emergency fail-closed if disk exhausts. | Free space or archive older historical raw segments to secondary external backup. |
