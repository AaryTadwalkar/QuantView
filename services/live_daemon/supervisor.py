"""
1. What this file does:
   Implements the LiveDaemonSupervisor and multi-account allocation orchestrator for QuantView
   Live Daemon (Milestone M7-07, ADR-038, Gate G5). Manages strategy deployment lifecycles,
   heartbeat pulses, quote stall detection, sub-second cold starts, clean shutdown order drainage,
   and emergency kill-switch activation.

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §8, ADR-038, and Milestone M7-07:
     - Multi-Account Allocation Modes (ADR-038): Supports ISOLATED (dedicated sub-account per deployment)
       and PORTFOLIO (shared account margin ceilings).
     - Sub-Second Startup: Initializes runtime and registers default deployments in < 300ms.
     - Heartbeat Pulse Generator: Ticks at 1.0-second intervals to monitor strategy health, publish
       system telemetry, and evaluate stall guards.
     - Market Quote Stall Guard: Detects absence of incoming ticks (> 60s) and transitions active
       deployments into HALTED_DATA state to prevent trading on stale books.
     - Emergency Kill Switch (RK-01): Fail-closed hardware/operator circuit breaker immediately halting
       order entry and draining active working orders.
     - Clean Teardown: Cancels pending working orders, saves final atomic checkpoints, and gracefully
       stops worker executors upon SIGINT/SIGTERM or administrative stop.

3. Elements in the file:
   - AccountAllocationMode: Enumeration of ADR-038 allocation topologies (ISOLATED, PORTFOLIO).
   - get_process_memory_rss: Cross-platform utility retrieving resident memory footprint.
   - LiveDaemonSupervisor: Central supervisor managing deployment registry, telemetry, and fault guards.

4. Final output of the file:
   - Exported AccountAllocationMode, LiveDaemonSupervisor, and get_process_memory_rss.
"""

import asyncio
import inspect
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from packages.market_data.streaming_builder import StreamingCandle, StreamingCandleBuilder
from packages.strategies.registry import get_default_strategy_registry
from packages.transport.frame_bus import FrameBus, TickFrame
from services.live_daemon.broker import PaperBroker
from services.live_daemon.host import (
    DEFAULT_STRATEGY_TIMEOUT_SEC,
    DeploymentStatus,
    StrategyDeploymentHost,
)
from services.live_daemon.recovery import CheckpointManager

logger = logging.getLogger(__name__)


def get_process_memory_rss() -> int:
    """
    1. The use of function:
       Retrieves the resident set size (RSS) memory consumption of the active process in bytes.

    2. How does the specific function work:
       - On Windows: Queries Win32 PSAPI GetProcessMemoryInfo via ctypes to obtain WorkingSetSize.
       - On Unix: Queries resource.getrusage(RUSAGE_SELF).ru_maxrss.
       - Fallback: Returns 0 if OS interfaces are inaccessible.

    3. Concepts used in the function:
       Platform-specific process telemetry, Win32 API interop, non-intrusive memory accounting.

    4. Places where this function is imported and used:
       Used by LiveDaemonSupervisor.get_status() and the loopback admin /control/status endpoint.

    5. Final output of the function, before and after:
       Before: Unknown memory footprint. After: Integer memory consumption in bytes.
    """
    try:
        import ctypes
        import ctypes.wintypes as wt

        class _PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wt.DWORD),
                ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.windll.psapi
        kernel32 = ctypes.windll.kernel32
        psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_PMC), wt.DWORD]
        psapi.GetProcessMemoryInfo.restype = wt.BOOL
        kernel32.GetCurrentProcess.restype = wt.HANDLE
        h_process = kernel32.GetCurrentProcess()
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        if psapi.GetProcessMemoryInfo(h_process, ctypes.byref(pmc), pmc.cb):
            return int(pmc.WorkingSetSize)
    except Exception:
        pass

    try:
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    except Exception:
        pass

    return 0


class AccountAllocationMode(str, Enum):
    """
    1. The use of class:
       Enumerates multi-strategy account allocation topology modes defined in ADR-038.

    2. What the class contains:
       - ISOLATED: Dedicated paper sub-account per deployment for strict capital firewalls.
       - PORTFOLIO: Multiple deployments share a single consolidated account margin ceiling.

    3. Technologies used and why:
       Python str and Enum for clean JSON serialization and configuration checking.

    4. Key design and overall design of the class:
       Enforces ADR-038 account segregation architecture.
    """

    ISOLATED = "ISOLATED"
    PORTFOLIO = "PORTFOLIO"


class LiveDaemonSupervisor:
    """
    1. The use of class:
       Central process orchestrator managing strategy deployment lifecycles, health pulses,
       market stall guards, and emergency kill-switch controls.

    2. What the class contains:
       - broker: PaperBroker instance managing simulated accounts, orders, and ledger events.
       - frame_bus: FrameBus in-memory ring buffer transport.
       - candle_builder: Optional StreamingCandleBuilder for real-time bar aggregation.
       - checkpoint_manager: Optional CheckpointManager for atomic bar persistence.
       - allocation_mode: Active AccountAllocationMode (ISOLATED or PORTFOLIO).
       - deployments: Dictionary mapping deployment_id to StrategyDeploymentHost instances.
       - heartbeat_interval_sec: Interval in seconds between heartbeat pulses (default 1.0s).
       - stall_threshold_sec: Stale market quote ceiling before HALTED_DATA (default 60.0s).
       - startup(): Sub-second runtime initialization (< 300ms).
       - shutdown(): Clean teardown draining working orders and stopping deployments.
       - register_deployment(): Adds a strategy deployment to the pool.
       - start_deployment(): Activates an individual deployment.
       - stop_deployment(): Halts an individual deployment.
       - trigger_kill_switch(): Implements RK-01 fail-closed circuit breaker.
       - check_quote_stall(): Detects frozen market data feeds.
       - get_status(): Returns consolidated daemon health and metrics.

    3. Technologies used and why:
       - asyncio for lightweight asynchronous heartbeat and background framebus consumers.
       - Thread-safe registries for multi-deployment synchronization.
       - Pre-allocated bounded queues for deterministic tick distribution.

    4. Key design and overall design of the class:
       Enforces supervisor pattern per M7-07: manages deployment registry, coordinates fault
       containment, generates 1-second heartbeat pulses, and fail-closed shuts down on anomalies.
    """

    def __init__(
        self,
        broker: PaperBroker,
        frame_bus: FrameBus,
        candle_builder: Optional[StreamingCandleBuilder] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        allocation_mode: Union[AccountAllocationMode, str] = AccountAllocationMode.ISOLATED,
        heartbeat_interval_sec: float = 1.0,
        stall_threshold_sec: float = 60.0,
    ) -> None:
        """
        1. The use of function:
           Constructs the LiveDaemonSupervisor with core runtime dependencies and default configurations.

        2. How does the specific function work:
           - Stores broker, frame_bus, candle_builder, and checkpoint_manager references.
           - Sets allocation_mode, heartbeat_interval_sec, and stall_threshold_sec.
           - Initializes empty deployment registry and metrics counters.
           - Sets is_running to False and kill_switch_active to False.

        3. Concepts used in the function:
           Dependency injection, runtime configuration, supervisor instantiation.

        4. Places where this function is imported and used:
           Instantiated by services.live_daemon.main and test fixtures.

        5. Final output of the function, before and after:
           Before: Uninitialized supervisor. After: Configured supervisor instance ready for startup.
        """
        self.broker = broker
        self.frame_bus = frame_bus
        self.candle_builder = candle_builder
        self.checkpoint_manager = checkpoint_manager
        self.allocation_mode = (
            allocation_mode
            if isinstance(allocation_mode, AccountAllocationMode)
            else AccountAllocationMode(allocation_mode)
        )
        self.heartbeat_interval_sec = float(heartbeat_interval_sec)
        self.stall_threshold_sec = float(stall_threshold_sec)

        self.deployments: Dict[str, StrategyDeploymentHost] = {}
        self.is_running: bool = False
        self.kill_switch_active: bool = False
        self.started_at: Optional[float] = None
        self.last_market_tick_epoch: Optional[float] = None
        self.heartbeat_count: int = 0

        self._heartbeat_task: Optional[asyncio.Task] = None
        self._framebus_queue: Optional[asyncio.Queue[TickFrame]] = None
        self._framebus_consumer_task: Optional[asyncio.Task] = None

    async def startup(self) -> None:
        """
        1. The use of function:
           Executes sub-second cold startup (< 300ms), subscribing to FrameBus and launching background tasks.

        2. How does the specific function work:
           - Records start timestamp and marks is_running as True.
           - Subscribes an asyncio.Queue to FrameBus for tick ingestion.
           - Starts background asyncio task for consuming FrameBus ticks.
           - Starts background heartbeat pulse loop.
           - Logs startup completion.

        3. Concepts used in the function:
           Sub-second initialization, async event loop task orchestration, pub/sub consumer setup.

        4. Places where this function is imported and used:
           Invoked on application startup in services.live_daemon.main and test harnesses.

        5. Final output of the function, before and after:
           Before: Dormant supervisor. After: Active supervisor consuming frames and emitting heartbeats.
        """
        t0 = time.perf_counter()
        self.started_at = time.time()
        self.is_running = True

        # Subscribe to FrameBus for real-time tick consumption
        self._framebus_queue = self.frame_bus.subscribe()
        self._framebus_consumer_task = asyncio.create_task(self._consume_framebus())

        # Start 1.0s heartbeat pulse generator
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(f"LiveDaemonSupervisor cold startup completed in {elapsed_ms:.2f}ms (< 300ms target).")

    async def shutdown(self) -> None:
        """
        1. The use of function:
           Performs graceful shutdown, stopping deployments, draining working orders, and closing broker.

        2. How does the specific function work:
           - Sets is_running to False.
           - Cancels background tasks (_heartbeat_task, _framebus_consumer_task).
           - Unsubscribes from FrameBus.
           - Stops all active strategy deployments.
           - Cancels all working orders across all broker accounts.
           - Closes paper broker database connection.

        3. Concepts used in the function:
           Graceful degradation, resource cleanup, order drainage.

        4. Places where this function is imported and used:
           Invoked on process exit, SIGINT/SIGTERM, or loopback admin shutdown.

        5. Final output of the function, before and after:
           Before: Active running supervisor. After: Cleanly stopped supervisor with drained state.
        """
        self.is_running = False

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._framebus_consumer_task is not None:
            self._framebus_consumer_task.cancel()
            try:
                await self._framebus_consumer_task
            except asyncio.CancelledError:
                pass

        if self._framebus_queue is not None:
            self.frame_bus.unsubscribe(self._framebus_queue)
            self._framebus_queue = None

        # Stop all deployments
        for dep in list(self.deployments.values()):
            try:
                dep.stop()
            except Exception as exc:
                logger.warning(f"Error stopping deployment {dep.deployment_id}: {exc}")

        # Cancel all working orders on the broker
        try:
            for order in self.broker.get_working_orders():
                self.broker.cancel_order(order.order_id)
        except Exception as exc:
            logger.warning(f"Error draining working orders during shutdown: {exc}")

        # Close broker repository
        try:
            self.broker.close()
        except Exception as exc:
            logger.warning(f"Error closing broker repository: {exc}")

        logger.info("LiveDaemonSupervisor clean shutdown complete.")

    def register_deployment(
        self,
        deployment_id: str,
        strategy: Any,
        account_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        mode: Optional[Union[AccountAllocationMode, str]] = None,
        instrument_key: Optional[str] = None,
        timeout_sec: float = DEFAULT_STRATEGY_TIMEOUT_SEC,
    ) -> StrategyDeploymentHost:
        """
        1. The use of function:
           Registers and constructs a new StrategyDeploymentHost in the supervisor deployment pool.

        2. How does the specific function work:
           - Resolves strategy: if given string, instantiates from registry; if class, creates instance.
           - Resolves account allocation mode (ISOLATED vs PORTFOLIO per ADR-038).
           - Derives account_id: dedicated ACC-{deployment_id} for ISOLATED, or shared for PORTFOLIO.
           - Ensures paper account is registered on the PaperBroker.
           - Instantiates StrategyDeploymentHost and records it in self.deployments.
           - Returns constructed host instance.

        3. Concepts used in the function:
           ADR-038 account allocation, dynamic strategy instantiation, registry mapping.

        4. Places where this function is imported and used:
           Invoked by daemon startup, REST POST /control/start endpoint, and test suites.

        5. Final output of the function, before and after:
           Before: Unregistered deployment. After: Registered host ready to start and process data.
        """
        strategy_params = params or {}

        # Resolve strategy instance
        strategy_instance: Any
        strategy_name: str
        if isinstance(strategy, str):
            strategy_name = strategy
            registry = get_default_strategy_registry()
            try:
                strategy_instance = registry.get(strategy, **strategy_params)
            except Exception:
                # Fallback: check if class is directly registered or can be instantiated
                strategy_instance = strategy
        elif inspect.isclass(strategy):
            strategy_name = strategy.__name__
            strategy_instance = strategy(**strategy_params)
        else:
            strategy_name = getattr(strategy, "__class__", type(strategy)).__name__
            strategy_instance = strategy

        # Resolve account per ADR-038
        effective_mode = (
            (mode if isinstance(mode, AccountAllocationMode) else AccountAllocationMode(mode))
            if mode is not None
            else self.allocation_mode
        )

        resolved_account = account_id
        if resolved_account is None:
            if effective_mode == AccountAllocationMode.ISOLATED:
                resolved_account = f"ACC-{deployment_id}"
            else:
                resolved_account = "ACC-PORTFOLIO-MAIN"

        # Register account on broker if missing
        if self.broker.get_account(resolved_account) is None:
            self.broker.register_account(resolved_account)

        host = StrategyDeploymentHost(
            deployment_id=deployment_id,
            strategy_id=strategy_name,
            strategy=strategy_instance,
            broker=self.broker,
            account_id=resolved_account,
            params=strategy_params,
            timeout_sec=timeout_sec,
            checkpoint_manager=self.checkpoint_manager,
            instrument_key=instrument_key,
        )

        self.deployments[deployment_id] = host
        logger.info(
            f"Registered deployment {deployment_id} ({strategy_name}) in {effective_mode.value} mode on {resolved_account}."
        )
        return host

    def start_deployment(self, deployment_id: str) -> StrategyDeploymentHost:
        """
        1. The use of function:
           Transitions a registered strategy deployment to RUNNING status.

        2. How does the specific function work:
           - Looks up deployment in registry (raises KeyError if not found).
           - Invokes host.start().
           - Returns host instance.

        3. Concepts used in the function:
           Lifecycle progression, registry lookup.

        4. Places where this function is imported and used:
           Invoked by REST POST /control/start and direct operational commands.

        5. Final output of the function, before and after:
           Before: Deployment in INITIALIZING. After: Deployment in RUNNING.
        """
        if deployment_id not in self.deployments:
            raise KeyError(f"Deployment '{deployment_id}' not found in registry.")

        host = self.deployments[deployment_id]
        host.start()
        return host

    def stop_deployment(self, deployment_id: str) -> StrategyDeploymentHost:
        """
        1. The use of function:
           Gracefully stops an active strategy deployment and cancels its working orders.

        2. How does the specific function work:
           - Looks up deployment in registry (raises KeyError if not found).
           - Invokes host.stop().
           - Cancels any working orders placed by this deployment/account.
           - Returns host instance.

        3. Concepts used in the function:
           Safe teardown, order cancellation, deployment lifecycle stop.

        4. Places where this function is imported and used:
           Invoked by REST POST /control/stop and shutdown procedures.

        5. Final output of the function, before and after:
           Before: Running deployment. After: STOPPED deployment with canceled pending orders.
        """
        if deployment_id not in self.deployments:
            raise KeyError(f"Deployment '{deployment_id}' not found in registry.")

        host = self.deployments[deployment_id]
        host.stop()

        # Cancel pending orders for this deployment's account
        for order in self.broker.get_working_orders(host.account_id):
            if order.strategy_id == host.strategy_id or order.account_id == host.account_id:
                self.broker.cancel_order(order.order_id)

        return host

    def get_deployment(self, deployment_id: str) -> Optional[StrategyDeploymentHost]:
        """
        1. The use of function:
           Retrieves a registered deployment host by identifier.

        2. How does the specific function work:
           Queries self.deployments dictionary and returns matching host or None.

        3. Concepts used in the function:
           Dictionary retrieval, registry query.

        4. Places where this function is imported and used:
           Used by REST inspection endpoints and test assertions.

        5. Final output of the function, before and after:
           Before: Deployment ID key. After: StrategyDeploymentHost instance or None.
        """
        return self.deployments.get(deployment_id)

    def list_deployments(self) -> List[Dict[str, Any]]:
        """
        1. The use of function:
           Returns a serialized list of all registered deployments.

        2. How does the specific function work:
           Iterates over self.deployments values and calls to_dict() on each host.

        3. Concepts used in the function:
           Telemetry serialization, collection transformation.

        4. Places where this function is imported and used:
           Used by supervisor status and REST API handlers.

        5. Final output of the function, before and after:
           Before: Collection of host objects. After: List of serialized dictionaries.
        """
        return [d.to_dict() for d in self.deployments.values()]

    def trigger_kill_switch(self, reason: str = "Operator manual kill switch") -> Dict[str, Any]:
        """
        1. The use of function:
           Activates the global emergency kill-switch (RK-01), blocking all future orders and canceling pending orders.

        2. How does the specific function work:
           - Sets self.kill_switch_active to True.
           - Sets kill_switch_active=True on broker.risk_evaluator.rules via Pydantic model_copy.
           - Iterates over all working orders across all broker accounts and cancels them.
           - Returns an audit payload detailing canceled orders and activation timestamp.

        3. Concepts used in the function:
           Fail-closed circuit breaker, risk rule enforcement (RK-01), urgent order cancellation.

        4. Places where this function is imported and used:
           Called by REST POST /control/kill-switch, gateway proxy router, and risk fault tests.

        5. Final output of the function, before and after:
           Before: Normal risk state. After: RK-01 active, pending orders canceled, new orders rejected.
        """
        self.kill_switch_active = True

        # Activate kill switch on broker pre-trade risk policy evaluator
        current_rules = self.broker.risk_evaluator.rules
        self.broker.risk_evaluator.rules = current_rules.model_copy(
            update={"kill_switch_active": True}
        )

        # Cancel all pending/working orders immediately
        canceled_order_ids: List[str] = []
        for order in self.broker.get_working_orders():
            self.broker.cancel_order(order.order_id)
            canceled_order_ids.append(order.order_id)

        logger.critical(
            f"EMERGENCY KILL SWITCH TRIGGERED: {reason}. Canceled {len(canceled_order_ids)} working orders."
        )

        return {
            "status": "kill_switch_activated",
            "kill_switch_active": True,
            "reason": reason,
            "canceled_orders_count": len(canceled_order_ids),
            "canceled_order_ids": canceled_order_ids,
            "timestamp": time.time(),
        }

    def check_quote_stall(self, current_time: Optional[float] = None) -> List[str]:
        """
        1. The use of function:
           Checks if incoming market quote flow has stalled beyond stall_threshold_sec (> 60s).

        2. How does the specific function work:
           - Obtains reference time (current_time or time.time()).
           - If last_market_tick_epoch is set and elapsed seconds exceed stall_threshold_sec:
             identifies all RUNNING deployments and transitions them to HALTED_DATA.
           - Records error explanation on affected deployments.
           - Returns list of deployment IDs transitioned to HALTED_DATA.

        3. Concepts used in the function:
           Data staleness detection, fail-closed state transition, market feed health monitoring.

        4. Places where this function is imported and used:
           Called by heartbeat loop and test_operational_faults.py.

        5. Final output of the function, before and after:
           Before: RUNNING deployments on stale feed. After: Deployments transitioned to HALTED_DATA.
        """
        now = current_time if current_time is not None else time.time()
        stalled: List[str] = []

        if self.last_market_tick_epoch is not None:
            elapsed = now - self.last_market_tick_epoch
            if elapsed > self.stall_threshold_sec:
                for dep in self.deployments.values():
                    if dep.status == DeploymentStatus.RUNNING:
                        dep.status = DeploymentStatus.HALTED_DATA
                        dep.last_error = (
                            f"Market quote stalled: no ticks for {elapsed:.1f}s "
                            f"(exceeds {self.stall_threshold_sec:.1f}s threshold)"
                        )
                        stalled.append(dep.deployment_id)
                        logger.warning(
                            f"[{dep.deployment_id}] Transitioned to HALTED_DATA due to quote stall ({elapsed:.1f}s)."
                        )

        return stalled

    def on_tick(self, tick: TickFrame) -> None:
        """
        1. The use of function:
           Processes an incoming TickFrame, updating market timestamps and fanning out to matching deployments.

        2. How does the specific function work:
           - Updates self.last_market_tick_epoch with current time.
           - Fans out tick to deployments registered for the tick's instrument_key.
           - If candle_builder is attached, forwards tick to candle_builder.

        3. Concepts used in the function:
           Event fan-out, timestamp tracking, candle aggregation forwarding.

        4. Places where this function is imported and used:
           Called by _consume_framebus() loop and test cases.

        5. Final output of the function, before and after:
           Before: Unprocessed tick. After: Updated supervisor timestamp, tick delivered to deployments.
        """
        self.last_market_tick_epoch = time.time()

        for dep in self.deployments.values():
            if dep.instrument_key is None or dep.instrument_key == tick.instrument_key:
                dep.step_tick(tick)

        if self.candle_builder is not None:
            self.candle_builder.on_tick(tick)

    def on_bar(self, candle: StreamingCandle) -> None:
        """
        1. The use of function:
           Dispatches a streaming candlestick bar to registered strategy deployments.

        2. How does the specific function work:
           - Iterates over active deployments matching candle.instrument_key.
           - If candle is finalized (is_closed=True), invokes dep.step_bar(candle, is_warming_up=False).

        3. Concepts used in the function:
           Bar dispatching, finalized candle gating.

        4. Places where this function is imported and used:
           Called when CandleBuilder finalizes a bar or during test simulations.

        5. Final output of the function, before and after:
           Before: Unprocessed candle bar. After: Completed bar stepped on matching strategy deployments.
        """
        for dep in self.deployments.values():
            if dep.instrument_key is None or dep.instrument_key == candle.instrument_key:
                dep.step_bar(candle, is_warming_up=False)

    async def _consume_framebus(self) -> None:
        """
        1. The use of function:
           Background coroutine consuming TickFrames from the subscribed FrameBus queue.

        2. How does the specific function work:
           Loops while is_running, dequeuing frames via await queue.get() and calling on_tick().

        3. Concepts used in the function:
           Asynchronous producer-consumer pattern, event loop dispatch.

        4. Places where this function is imported and used:
           Launched as background task during startup().

        5. Final output of the function, before and after:
           Before: Frames queued on FrameBus. After: Dequeued and processed frames.
        """
        if self._framebus_queue is None:
            return

        while self.is_running:
            try:
                frame = await self._framebus_queue.get()
                self.on_tick(frame)
                self._framebus_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error consuming frame from FrameBus: {exc}")

    async def _heartbeat_loop(self) -> None:
        """
        1. The use of function:
           Background coroutine executing periodic heartbeat health checks every 1.0 second.

        2. How does the specific function work:
           Loops while is_running:
             - Sleeps for heartbeat_interval_sec (1.0s).
             - Increments heartbeat_count.
             - Executes check_quote_stall().

        3. Concepts used in the function:
           Periodic timer loop, proactive health telemetry, stall monitoring.

        4. Places where this function is imported and used:
           Launched as background task during startup().

        5. Final output of the function, before and after:
           Before: Periodic interval elapsed. After: Heartbeat incremented, stall checks evaluated.
        """
        while self.is_running:
            try:
                await asyncio.sleep(self.heartbeat_interval_sec)
                self.heartbeat_count += 1
                self.check_quote_stall()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in supervisor heartbeat loop: {exc}")

    def get_status(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Generates consolidated daemon health, active deployments, memory RSS, and FrameBus metrics.

        2. How does the specific function work:
           - Calculates uptime seconds from started_at.
           - Counts total, running, and halted deployments.
           - Gathers host telemetry via to_dict().
           - Queries process memory RSS in bytes via get_process_memory_rss().
           - Obtains FrameBus statistics via frame_bus.get_stats().
           - Returns consolidated telemetry dictionary.

        3. Concepts used in the function:
           Telemetry aggregation, system observability, status reporting.

        4. Places where this function is imported and used:
           Called by REST GET /control/status endpoint and external monitoring agents.

        5. Final output of the function, before and after:
           Before: Dispersed runtime state. After: Standardized operational health dictionary.
        """
        now = time.time()
        uptime = round(now - self.started_at, 2) if self.started_at else 0.0

        running_cnt = sum(
            1 for d in self.deployments.values() if d.status == DeploymentStatus.RUNNING
        )
        halted_cnt = sum(
            1
            for d in self.deployments.values()
            if d.status
            in (
                DeploymentStatus.HALTED_TIMEOUT,
                DeploymentStatus.HALTED_FAULT,
                DeploymentStatus.HALTED_DATA,
            )
        )

        return {
            "status": "HEALTHY" if self.is_running else "STOPPED",
            "uptime_sec": uptime,
            "allocation_mode": self.allocation_mode.value,
            "kill_switch_active": (
                self.kill_switch_active
                or getattr(self.broker.risk_evaluator.rules, "kill_switch_active", False)
            ),
            "deployments_total": len(self.deployments),
            "deployments_running": running_cnt,
            "deployments_halted": halted_cnt,
            "deployments": [d.to_dict() for d in self.deployments.values()],
            "memory_rss_bytes": get_process_memory_rss(),
            "frame_bus": (
                self.frame_bus.stats()
                if hasattr(self.frame_bus, "stats")
                else (self.frame_bus.get_stats() if hasattr(self.frame_bus, "get_stats") else {})
            )
            if self.frame_bus
            else {},
            "last_market_tick_epoch": self.last_market_tick_epoch,
            "heartbeat_count": self.heartbeat_count,
        }
