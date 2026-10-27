"""
1. What this file does:
   Implements the dead-man's switch heartbeat monitor and stale alert generator (HeartbeatMonitor).
   Records periodic service pulses to disk with atomic fsync, tracks lag against the 60-second
   staleness ceiling, and triggers dead-man alerts per QUANTVIEW_MASTER_SPEC §4, §10, and Task M2-06.

2. Overall design:
   Coordinates health and liveness tracking across collector processes:
     - HeartbeatMonitor: Manages atomic heartbeat JSON files in Data/raw/telemetry/.
     - Records process ID (PID), UTC ISO-8601 timestamp, status (HEALTHY, DEGRADED, CRITICAL), and metrics.
     - Enforces max lag threshold (default 60.0s per MASTER §4 target: "stale alert <= 60s").
     - On missing heartbeat or stale pulse exceeding threshold: emits MissingHeartbeatAlert and invokes alert handler.
     - HeartbeatEmitter: Optional background daemon thread emitting pulses at a configurable interval.

3. Elements in the file:
   - MissingHeartbeatAlert: Exception raised or returned on heartbeat breach.
   - HeartbeatRecord: Dataclass encapsulating single heartbeat pulse payload.
   - HeartbeatMonitor: Central class recording and auditing heartbeat files.
   - HeartbeatEmitter: Background threading loop emitting periodic heartbeats.

4. Final output of the file:
   - Exported HeartbeatMonitor, HeartbeatEmitter, HeartbeatRecord, and MissingHeartbeatAlert classes.
   - Atomically persisted telemetry files: Data/raw/telemetry/heartbeat_<service_name>.json.
"""

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("quantview.heartbeat")


class MissingHeartbeatAlert(RuntimeError):
    """
    1. The use of class:
       Exception indicating that a service heartbeat has ceased or exceeded the staleness threshold.

    2. What the class contains:
       Standard Exception constructor with diagnostic message and lag metrics.

    3. Technologies used and why:
       Standard Python RuntimeError subclass.

    4. Key design and overall design of the class:
       Allows health supervisors and monitoring daemons to handle dead-man switch events cleanly.
    """
    pass


@dataclass
class HeartbeatRecord:
    """
    1. The use of class:
       Encapsulates structured telemetry fields written during each service heartbeat pulse.

    2. What the class contains:
       - service_name: Identifier of the reporting service (e.g. 'collector_snapshot').
       - timestamp_utc: ISO-8601 UTC timestamp string.
       - epoch_sec: Floating-point UTC epoch seconds.
       - pid: Process identifier of the running collector.
       - status: Health status ('HEALTHY', 'DEGRADED', 'CRITICAL').
       - metadata: Optional dictionary containing capture counts, lag, and queue stats.

    3. Technologies used and why:
       Python dataclasses for structured serialization.

    4. Key design and overall design of the class:
       Standardized telemetry record format across all QuantView microservices.
    """
    service_name: str
    timestamp_utc: str
    epoch_sec: float
    pid: int
    status: str
    metadata: Dict[str, Any]


class HeartbeatMonitor:
    """
    1. The use of class:
       Audits service heartbeats and fires alerts when a process hangs or crashes.

    2. What the class contains:
       - telemetry_dir: Directory where heartbeat files are stored (Data/raw/telemetry).
       - alert_handler: Optional callback invoked on stale or missing pulse.
       - record_pulse(): Writes atomic heartbeat JSON with fsync.
       - check_freshness(): Evaluates lag against threshold and generates alerts.

    3. Technologies used and why:
       pathlib.Path, json, and atomic rename with os.fsync for crash resilience.

    4. Key design and overall design of the class:
       Enforces dead-man's switch invariant: if a collector process dies, the absence of pulse
       triggers an alert within <= 60 seconds without requiring in-process participation.
    """

    def __init__(
        self,
        telemetry_dir: Optional[Path] = None,
        alert_handler: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """
        1. The use of function:
           Initializes HeartbeatMonitor with telemetry path and alert callback.

        2. How does the specific function work:
           Resolves storage path (defaulting to Data/raw/telemetry) and creates directory if needed.

        3. Concepts used in the function:
           Path configuration, directory management.

        4. Places where this function is imported and used:
           Used by collectors, daemon supervisors, and test fixtures.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Ready HeartbeatMonitor instance.
        """
        if telemetry_dir is None:
            project_root = Path(__file__).resolve().parents[2]
            self.telemetry_dir = project_root / "Data" / "raw" / "telemetry"
        else:
            self.telemetry_dir = Path(telemetry_dir)

        self.telemetry_dir.mkdir(parents=True, exist_ok=True)
        self.alert_handler = alert_handler

    def _get_heartbeat_path(self, service_name: str) -> Path:
        """Helper to get path for service heartbeat file."""
        return self.telemetry_dir / f"heartbeat_{service_name}.json"

    def record_pulse(
        self,
        service_name: str,
        status: str = "HEALTHY",
        metadata: Optional[Dict[str, Any]] = None,
        now_ts: Optional[float] = None,
    ) -> HeartbeatRecord:
        """
        1. The use of function:
           Records an atomic heartbeat pulse to disk with hardware fsync.

        2. How does the specific function work:
           - Constructs HeartbeatRecord.
           - Serializes to temporary file `.tmp`.
           - Flushes and calls os.fsync().
           - Atomically renames to finalized path heartbeat_<service_name>.json.

        3. Concepts used in the function:
           Atomic writes, fsync durability.

        4. Places where this function is imported and used:
           Called by HeartbeatEmitter and collector capture loops.

        5. Final output of the function, before and after:
           Before: Stale heartbeat on disk. After: Fresh heartbeat record durably written.
        """
        ts = now_ts if now_ts is not None else time.time()
        dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        record = HeartbeatRecord(
            service_name=service_name,
            timestamp_utc=dt_str,
            epoch_sec=ts,
            pid=os.getpid(),
            status=status,
            metadata=metadata or {},
        )

        final_path = self._get_heartbeat_path(service_name)
        tmp_path = final_path.with_suffix(".json.tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(asdict(record), f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        if final_path.exists():
            final_path.unlink()
        tmp_path.rename(final_path)

        return record

    def check_freshness(
        self,
        service_name: str,
        max_lag_sec: float = 60.0,
        now_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        1. The use of function:
           Evaluates the freshness of a service heartbeat and dispatches alerts on staleness.

        2. How does the specific function work:
           - Reads heartbeat file for service_name.
           - If missing: flags MISSING and fires alert.
           - If lag > max_lag_sec: flags STALE, computes exact lag, and fires alert.
           - If lag <= max_lag_sec: returns OK.

        3. Concepts used in the function:
           Dead-man switch evaluation, lag threshold comparison.

        4. Places where this function is imported and used:
           Called by health supervisors, runbook checks, and unit tests.

        5. Final output of the function, before and after:
           Before: Unmeasured health state. After: Structured dictionary detailing freshness or alert.
        """
        now = now_ts if now_ts is not None else time.time()
        h_path = self._get_heartbeat_path(service_name)

        if not h_path.exists():
            alert_payload = {
                "event": "MISSING_HEARTBEAT_ALERT",
                "service_name": service_name,
                "status": "MISSING",
                "message": f"No heartbeat file found for service '{service_name}' at {h_path}.",
                "checked_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            }
            if self.alert_handler is not None:
                self.alert_handler(alert_payload)
            return alert_payload

        try:
            with open(h_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            last_epoch = float(data.get("epoch_sec", 0.0))
            lag_sec = max(0.0, now - last_epoch)
        except Exception as ex:
            alert_payload = {
                "event": "CORRUPT_HEARTBEAT_ALERT",
                "service_name": service_name,
                "status": "CORRUPT",
                "message": f"Failed to parse heartbeat file for '{service_name}': {ex}",
                "checked_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            }
            if self.alert_handler is not None:
                self.alert_handler(alert_payload)
            return alert_payload

        if lag_sec > max_lag_sec:
            alert_payload = {
                "event": "STALE_HEARTBEAT_ALERT",
                "service_name": service_name,
                "status": "STALE",
                "lag_sec": round(lag_sec, 2),
                "max_lag_sec": max_lag_sec,
                "last_seen_utc": data.get("timestamp_utc"),
                "service_status": data.get("status"),
                "message": f"Heartbeat gap for '{service_name}' is {lag_sec:.2f}s, exceeding limit of {max_lag_sec:.1f}s.",
                "checked_at": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            }
            if self.alert_handler is not None:
                self.alert_handler(alert_payload)
            return alert_payload

        return {
            "status": "OK",
            "service_name": service_name,
            "lag_sec": round(lag_sec, 2),
            "max_lag_sec": max_lag_sec,
            "last_seen_utc": data.get("timestamp_utc"),
            "service_status": data.get("status"),
        }


class HeartbeatEmitter:
    """
    1. The use of class:
       Background daemon thread periodically calling record_pulse() for a service.

    2. What the class contains:
       - monitor: HeartbeatMonitor instance.
       - service_name: Identifier of service to report.
       - interval_sec: Frequency of heartbeat pulses (default 15.0s).
       - _stop_event: threading.Event to signal graceful shutdown.
       - _thread: threading.Thread running the pulse loop.

    3. Technologies used and why:
       threading.Thread and threading.Event for non-blocking daemon operation.

    4. Key design and overall design of the class:
       Runs asynchronously alongside collectors to maintain active heartbeat pulse.
    """

    def __init__(
        self,
        monitor: HeartbeatMonitor,
        service_name: str,
        interval_sec: float = 15.0,
    ) -> None:
        """
        1. The use of function:
           Initializes HeartbeatEmitter with monitor, service name, and interval.

        2. How does the specific function work:
           Configures stop event and daemon thread.

        3. Concepts used in the function:
           Daemon thread initialization.

        4. Places where this function is imported and used:
           Started by collector daemons.

        5. Final output of the function, before and after:
           Before: Unstarted emitter. After: Initialized HeartbeatEmitter.
        """
        self.monitor = monitor
        self.service_name = service_name
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """
        1. The use of function:
           Starts the background heartbeat emitting daemon thread.

        2. How does the specific function work:
           Spawns threading.Thread with daemon=True targeting _run_loop().

        3. Concepts used in the function:
           Thread lifecycle.

        4. Places where this function is imported and used:
           Collector startup.

        5. Final output of the function, before and after:
           Before: Dormant thread. After: Running heartbeat thread.
        """
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name=f"HeartbeatEmitter-{self.service_name}")
        self._thread.start()

    def stop(self) -> None:
        """
        1. The use of function:
           Signals the heartbeat emitter thread to terminate cleanly.

        2. How does the specific function work:
           Sets _stop_event and joins thread with 2.0s timeout.

        3. Concepts used in the function:
           Graceful thread shutdown.

        4. Places where this function is imported and used:
           Collector shutdown.

        5. Final output of the function, before and after:
           Before: Active thread. After: Stopped thread.
        """
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run_loop(self) -> None:
        """Internal loop emitting heartbeat until stopped."""
        # Initial immediate pulse
        self.monitor.record_pulse(self.service_name)
        while not self._stop_event.wait(timeout=self.interval_sec):
            try:
                self.monitor.record_pulse(self.service_name)
            except Exception as ex:
                logger.error("HeartbeatEmitter failed to emit pulse: %s", ex)
