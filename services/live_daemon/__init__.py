"""
1. What this file does:
   Defines the service boundary for live_daemon (paper trading and live execution orchestrator).

2. Overall design:
   live_daemon consumes real-time frames from FrameBus / snapshots, checks data freshness
   (available_at <= decision_time), steps strategy instances on completed bars, evaluates risk
   rules, simulates order fills, and writes immutable events to relational ledger_events in integer paise.

3. Elements in the file:
   - Service metadata and lifecycle contract.
   - PaperBroker: Simulated execution and pre-trade risk guard engine.
   - CheckpointManager: Atomic bar checkpoint manager and crash recovery orchestrator.
   - StrategyCheckpoint, RecoveryResult: Checkpoint and recovery data models.
   - StrategyDeploymentHost, DeploymentStatus: Isolated execution host and lifecycle states.
   - LiveDaemonSupervisor, AccountAllocationMode: Supervisor orchestrator and ADR-038 allocation modes.
   - create_daemon_app: Factory for loopback admin FastAPI service.

4. Final output of the file:
   - Package interface for services.live_daemon.
"""

from services.live_daemon.broker import (
    ExecutionMode,
    PaperAccount,
    PaperBroker,
    PaperOrder,
    PaperPosition,
    PaperTrade,
)
from services.live_daemon.host import (
    DeploymentStatus,
    StrategyDeploymentHost,
)
from services.live_daemon.main import (
    create_daemon_app,
)
from services.live_daemon.recovery import (
    CheckpointManager,
    RecoveryResult,
    StrategyCheckpoint,
)
from services.live_daemon.supervisor import (
    AccountAllocationMode,
    LiveDaemonSupervisor,
)

SERVICE_NAME = "live_daemon"

__all__ = [
    "SERVICE_NAME",
    "PaperBroker",
    "PaperAccount",
    "PaperOrder",
    "PaperPosition",
    "PaperTrade",
    "ExecutionMode",
    "CheckpointManager",
    "StrategyCheckpoint",
    "RecoveryResult",
    "StrategyDeploymentHost",
    "DeploymentStatus",
    "LiveDaemonSupervisor",
    "AccountAllocationMode",
    "create_daemon_app",
]
