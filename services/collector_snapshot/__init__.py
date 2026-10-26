"""
1. What this file does:
   Defines the service boundary for collector_snapshot (periodic REST option chain capture).
   Re-exports snapshot adapters, raw persistence engines, token lifecycle managers,
   and dead-man heartbeat monitors per QUANTVIEW_DATA_SPEC §4.3 and Task M2-01, M2-06.

2. Overall design:
   The collector_snapshot service coordinates:
     - Resilient HTTP requests with exponential backoff and token redaction (UpstoxSnapshotAdapter).
     - Crash-durable, atomic raw JSON persistence and self-describing manifests (RawSnapshotWriter).
     - End-to-end collection workflow and fail-safe decoder isolation (SnapshotCollectorService).
     - 08:45 AM pre-market authentication validation and WAITING_FOR_TOKEN gating (TokenManager).
     - Telemetry pulse recording and dead-man switch freshness monitoring (HeartbeatMonitor).

3. Elements in the file:
   - SERVICE_NAME: Constant service identifier ('collector_snapshot').
   - Re-exported classes from adapter, raw_writer, collector, token_manager, and heartbeat.

4. Final output of the file:
   - Public package interface for services.collector_snapshot.
"""

from services.collector_snapshot.adapter import SnapshotResponsePayload, UpstoxSnapshotAdapter
from services.collector_snapshot.collector import SnapshotCollectorService, generate_snapshot_id
from services.collector_snapshot.heartbeat import (
    HeartbeatEmitter,
    HeartbeatMonitor,
    HeartbeatRecord,
    MissingHeartbeatAlert,
)
from services.collector_snapshot.raw_writer import RawCaptureRecord, RawSnapshotWriter
from services.collector_snapshot.token_manager import TokenCheckResult, TokenManager, TokenState

SERVICE_NAME = "collector_snapshot"

__all__ = [
    "SERVICE_NAME",
    "UpstoxSnapshotAdapter",
    "SnapshotResponsePayload",
    "RawSnapshotWriter",
    "RawCaptureRecord",
    "SnapshotCollectorService",
    "generate_snapshot_id",
    "TokenManager",
    "TokenState",
    "TokenCheckResult",
    "HeartbeatMonitor",
    "HeartbeatEmitter",
    "HeartbeatRecord",
    "MissingHeartbeatAlert",
]
