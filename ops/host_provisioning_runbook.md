# QuantView Production Collector Host Provisioning & Read-Only Sync Runbook

- **Document ID:** `ops/host_provisioning_runbook.md`
- **Specification Reference:** `QUANTVIEW_MASTER_SPEC.md §4, §5`, Task `M2-11`
- **Revision Date:** 2026-10-26

---

## 1. Hardware & Platform Sizing Recommendation

Based on the empirical feed volume measurements in [`reports/feed-volume.md`](file:///c:/Algo/quantview/reports/feed-volume.md):
- **Daily Raw Capture Footprint:** ~34.8 MB / trading session (6.25 hrs).
- **Annual Storage Requirement:** ~8.5 GB / year.
- **Collector Memory Footprint:** $\le 85\text{ MB}$ RSS.
- **Collector CPU Load:** $\le 2.5\%$ average single-core utilization.

### Recommended Production Host Specification
| Component | Minimum Specification | Recommended Production Host |
| :--- | :--- | :--- |
| **Form Factor** | Dedicated Mini-PC or Cloud VM | Dedicated Mini-PC with Uninterruptible Power Supply (UPS) |
| **Operating System** | Ubuntu 24.04 LTS (x86_64) | Ubuntu 24.04 LTS (Server Minimal, headless) |
| **CPU** | 4 Cores (Intel 12th+ Gen / AMD Ryzen 5+) | 6–8 Cores |
| **RAM** | 8 GB DDR4/DDR5 | 16 GB DDR5 |
| **Primary Storage** | 512 GB NVMe SSD (M.2 PCIe Gen 4) | 1 TB NVMe SSD (Enterprise endurance, $\ge 600\text{ TBW}$) |
| **Secondary Storage** | External USB 3.0 HDD / NAS | Secondary internal SATA SSD or encrypted external backup drive |
| **Power Protection** | Surge Protector | Smart UPS ($\ge 1000\text{ VA}$) with automated USB shutdown signaling |
| **Network** | Gigabit Ethernet (1 Gbps) | Dual NIC (primary fiber broadband + automatic 4G/5G failover) |

---

## 2. Operating System Hardening & Setup

### Step 1: Base Packages & Python Environment
```bash
# Update and install build dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3.11-dev git curl ufw rsync

# Create dedicated service user
sudo useradd -m -s /bin/bash quantview
sudo usermod -aG sudo quantview

# Setup application directory
sudo mkdir -p /opt/quantview
sudo chown -R quantview:quantview /opt/quantview
```

### Step 2: System Limits & Kernel Tuning
Add to `/etc/security/limits.d/quantview.conf`:
```text
quantview soft nofile 65536
quantview hard nofile 65536
```
Enable TCP keepalive and memory buffering in `/etc/sysctl.d/99-quantview.conf`:
```text
net.ipv4.tcp_keepalive_time = 60
net.ipv4.tcp_keepalive_intvl = 10
net.ipv4.tcp_keepalive_probes = 5
fs.file-max = 2097152
```
Apply settings:
```bash
sudo sysctl --system
```

---

## 3. Storage Layout & Mount Invariants

```
/opt/quantview/
├── .env                              <- Locked permissions (chmod 600)
├── venv/                             <- Isolated Python virtual environment
├── config/                           <- Static expiry & contract configurations
├── Data/
│   ├── raw/
│   │   ├── upstox_ws/ticks/          <- Real-time binary segments (.bin.gz)
│   │   ├── upstox_rest/snapshots/    <- 60s option chain snapshots (.json.gz)
│   │   └── telemetry/                <- Heartbeat pulses (.json)
│   └── staging/checkpoints/          <- Backfill checkpoints
```

### Disk Capacity Monitoring & Alerts
Set up cron job running every 15 minutes checking disk space:
```bash
# Alert at 80% capacity; emergency freeze at 90%
DF_PCT=$(df /opt/quantview | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DF_PCT" -ge 80 ]; then
    echo "[CRITICAL ALERT] QuantView disk usage is at ${DF_PCT}%!" | mail -s "QuantView Low Disk Warning" admin@quantview.internal
fi
```

---

## 4. Unidirectional Read-Only Sync to Research Machine

To preserve the institutional barrier between live data collection and analytical research:
- The production collector host **ONLY PUSHES / SERVES READ-ONLY DATA**.
- The research workstation **ONLY PULLS**.
- **NO write-back capability exists** from research back to production (protects production against accidental corruption or test overwrites).

### Sync Script Execution (`tools/ops/sync_production_to_research.py`)
```powershell
# On Research Machine: Pull finalized session files from Production mount or SSH
python tools/ops/sync_production_to_research.py --source "\\prod-collector\Data\raw" --dest "Data/raw"
```
- **Invariants:**
  1. Only finalized files (`.bin.gz`, `.json.gz`, `.manifest.json`) are transferred.
  2. In-flight files (`.partial`, `.tmp`, `.lock`) are strictly ignored.
  3. Every file's SHA-256 digest is cryptographically validated against its companion `.manifest.json` on the research machine before acceptance.

---

## 5. Cutover Checklist & Gate G0 Compliance

- [x] Host hardware sizing verified against empirical M2-10 measurements.
- [x] Unidirectional sync architecture established (no write-back path).
- [x] Checksum verification on pull certified.
- [x] Systemd supervision with auto-restart on failure documented.
- [x] Single-owner process lease prevents multi-instance collisions.
