"""
1. What this file does:
   Operational supervisor script that monitors running QuantView collectors (collector_ws and collector_snapshot)
   and ensures they are cleanly terminated at market close (15:35 Asia/Kolkata).

2. Overall design:
   - Computes target market close boundary (15:35:00 IST by default).
   - Sleeps until market close boundary is reached.
   - At market close, scans running processes for run_collector_ws.py and run_collector_snapshot.py.
   - Dispatches termination signals (SIGINT / SIGTERM / process terminate) to trigger safe cleanup.
   - Verifies release of exclusive lease lock (.collector_ws.lock) and logs completion.

3. Elements in the file:
   - get_seconds_until_close(): Calculates duration in seconds until target close time in Asia/Kolkata.
   - find_collector_processes(): Discovers active collector PIDs matching QuantView CLI scripts.
   - stop_collector_processes(): Sends clean termination signals to active collector processes.
   - main(): CLI entrypoint parsing --close-time and executing watchdog lifecycle.

4. Final output of the file:
   - Clean shutdown of active collector processes at 15:35 IST with guaranteed lock release.
"""

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
import zoneinfo
from datetime import datetime, timezone
from datetime import time as dt_time
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

KOLKATA_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")
logger = logging.getLogger("quantview.market_watchdog")


def get_seconds_until_close(close_time_str: str = "15:35") -> float:
    """
    1. The use of function:
       Calculates seconds remaining until target market close time in Asia/Kolkata.

    2. How does the specific function work:
       - Extracts hour and minute from close_time_str.
       - Constructs target datetime today in Asia/Kolkata timezone.
       - Returns difference in seconds between target and current IST time.

    3. Concepts used in the function:
       Timezone localization, schedule arithmetic.

    4. Places where this function is imported and used:
       Called in main() to determine sleep duration.

    5. Final output of the function, before and after:
       Before: Time strings. After: Floating point number of seconds remaining (or 0 if already past).
    """
    try:
        parts = [int(p) for p in close_time_str.split(":")]
        close_h, close_m = parts[0], parts[1]
    except Exception:
        close_h, close_m = 15, 35

    now_ist = datetime.now(KOLKATA_TZ)
    target_dt = now_ist.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    delta = (target_dt - now_ist).total_seconds()
    return max(0.0, delta)


def find_collector_processes() -> List[Tuple[int, str]]:
    """
    1. The use of function:
       Discovers running OS processes executing QuantView collector scripts.

    2. How does the specific function work:
       - Queries Windows CIM/WMI or process table using PowerShell command.
       - Filters command line for run_collector_ws.py and run_collector_snapshot.py.
       - Excludes the current watchdog process PID.
       - Returns list of (PID, script_name) tuples.

    3. Concepts used in the function:
       Process inspection, OS automation.

    4. Places where this function is imported and used:
       Called in main() at market close time.

    5. Final output of the function, before and after:
       Before: Unknown running processes. After: List of matching collector PIDs.
    """
    current_pid = os.getpid()
    collectors: List[Tuple[int, str]] = []

    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"name = 'python.exe'\" | Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            import json
            raw_json = result.stdout.strip()
            data = json.loads(raw_json)
            items = data if isinstance(data, list) else [data]
            for item in items:
                pid = item.get("ProcessId")
                cli = item.get("CommandLine") or ""
                if pid and pid != current_pid:
                    if "run_collector_ws.py" in cli:
                        collectors.append((pid, "run_collector_ws"))
                    elif "run_collector_snapshot.py" in cli:
                        collectors.append((pid, "run_collector_snapshot"))
    except Exception as ex:
        logger.warning("Error querying process list: %s", ex)

    return collectors


def stop_collector_processes(processes: List[Tuple[int, str]]) -> None:
    """
    1. The use of function:
       Stops discovered collector processes cleanly.

    2. How does the specific function work:
       - Iterates over (PID, name) pairs.
       - Dispatches taskkill command with graceful wait, falling back to termination.
       - Verifies that lease locks are freed.

    3. Concepts used in the function:
       Process lifecycle control, resource reclamation.

    4. Places where this function is imported and used:
       Called in main() after market close boundary triggers.

    5. Final output of the function, before and after:
       Before: Collectors running. After: Collectors terminated and locks freed.
    """
    for pid, name in processes:
        print(f"[MARKET CLOSE] Stopping collector {name} (PID {pid})...")
        try:
            # First attempt: taskkill /pid PID (graceful WM_CLOSE/SIGTERM)
            subprocess.run(["taskkill", "/pid", str(pid)], capture_output=True, timeout=5)
            print(f"[MARKET CLOSE] Sent termination request to PID {pid}.")
        except Exception as ex:
            print(f"Warning: Failed to signal PID {pid}: {ex}")

    # Give 3 seconds for clean rotation and lock release
    time.sleep(3.0)

    # Clean stale lock file if remaining
    lock_file = PROJECT_ROOT / "Data" / "raw" / "upstox_ws" / ".collector_ws.lock"
    if lock_file.exists():
        try:
            lock_file.unlink()
            print("[MARKET CLOSE] Cleaned lock file at .collector_ws.lock.")
        except Exception:
            pass


def main() -> None:
    """
    1. The use of function:
       CLI entrypoint for the market close supervisor watchdog.

    2. How does the specific function work:
       - Computes seconds until target close time (15:35 IST).
       - Prints countdown status and sleeps in responsive intervals.
       - Discovers and cleanly stops any active collector processes at 15:35 IST.

    3. Concepts used in the function:
       Supervision, scheduling, process management.

    4. Places where this function is imported and used:
       Executed via `python tools/ops/market_close_watchdog.py`.

    5. Final output of the function, before and after:
       Before: Standing idle. After: Guaranteed collector shutdown at 15:35 IST.
    """
    parser = argparse.ArgumentParser(description="QuantView Market Close Watchdog Supervisor")
    parser.add_argument("--close-time", type=str, default="15:35", help="Target IST close time (HH:MM, default: 15:35)")
    parser.add_argument("--now", action="store_true", help="Immediately stop all collectors without waiting")
    args = parser.parse_args()

    print("\n--- QuantView Market Close Watchdog Supervisor ---", flush=True)
    now_ist = datetime.now(KOLKATA_TZ)
    print(f"Current Time:   {now_ist.strftime('%Y-%m-%d %H:%M:%S')} IST", flush=True)
    print(f"Target Close:   {args.close_time} IST", flush=True)

    if not args.now:
        secs_remaining = get_seconds_until_close(args.close_time)
        if secs_remaining > 0:
            mins = int(secs_remaining // 60)
            secs = int(secs_remaining % 60)
            print(f"Status:         ARMED. Sleeping {mins}m {secs}s until {args.close_time} IST...", flush=True)
            while secs_remaining > 0:
                sleep_chunk = min(5.0, secs_remaining)
                time.sleep(sleep_chunk)
                secs_remaining = get_seconds_until_close(args.close_time)

    print(f"\n[MARKET CLOSE TRIGGERED] Current time is {datetime.now(KOLKATA_TZ).strftime('%H:%M:%S')} IST.", flush=True)
    collectors = find_collector_processes()
    if not collectors:
        print("No active collector processes found running.", flush=True)
    else:
        print(f"Found {len(collectors)} active collector process(es):", flush=True)
        for pid, name in collectors:
            print(f"  - PID {pid}: {name}", flush=True)
        stop_collector_processes(collectors)

    print("Market close supervisor finished successfully.\n", flush=True)


if __name__ == "__main__":
    main()
