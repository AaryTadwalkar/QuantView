"""
1. What this file does:
   Implements the StrategyDeploymentHost for QuantView Live Daemon (Milestone M7-07, Gate G5).
   Wraps strategy instances in isolated bounded execution containers with strict 500ms timeout
   guards, lifecycle state machines, pre-trade signal order routing, and fault isolation.

2. Overall design:
   Enforces QUANTVIEW_MASTER_SPEC §2.2 and Milestone M7-07:
     - Bounded Thread Execution: Wraps on_bar() and on_tick() calls in a dedicated single-threaded
       executor with a strict 500ms timeout guard (default 0.5s).
     - Fault Isolation: Freezing, hanging, or crashing strategies are trapped and transitioned to
       HALTED_TIMEOUT or HALTED_FAULT without interrupting peer strategies in the supervisor pool.
     - Deterministic Status Lifecycle:
       INITIALIZING -> WARMING_UP -> RUNNING -> STOPPED (or HALTED_TIMEOUT / HALTED_FAULT / HALTED_DATA).
     - Signal Suppression: Suppresses order emission during historical warm-up replay (is_warming_up=True).
     - Pre-Trade Execution Bridge: Routes validated signals to the PaperBroker for pre-trade risk gating
       and integer-paise relational ledger persistence.
     - Bar Boundary Checkpointing: Integrates with CheckpointManager to persist atomic state checkpoints.

3. Elements in the file:
   - DeploymentStatus: Enumeration of deployment lifecycle states.
   - StrategyDeploymentHost: Isolated execution container managing strategy execution, timeout guards,
     and broker dispatch.

4. Final output of the file:
   - Exported DeploymentStatus and StrategyDeploymentHost classes for live daemon orchestration.
"""

import concurrent.futures
import inspect
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Union
from zoneinfo import ZoneInfo

from packages.domain import OrderSide
from packages.market_data.streaming_builder import StreamingCandle
from packages.strategies import SignalAction
from packages.transport.frame_bus import TickFrame
from services.live_daemon.broker import PaperBroker
from services.live_daemon.recovery import CheckpointManager

logger = logging.getLogger(__name__)

DEFAULT_STRATEGY_TIMEOUT_SEC: float = 0.5


class DeploymentStatus(str, Enum):
    """
    1. The use of class:
       Enumerates all lifecycle states for an individual strategy deployment host.

    2. What the class contains:
       - INITIALIZING: Host constructed and configuring internal state.
       - WARMING_UP: Ingesting historical warm-up bars with signal emission suppressed.
       - RUNNING: Actively processing real-time ticks and finalized bars.
       - STOPPED: Cleanly shut down by operator command.
       - HALTED_TIMEOUT: Strategy execution exceeded the 500ms execution timeout limit.
       - HALTED_FAULT: Strategy raised an uncaught runtime exception or crashed.
       - HALTED_DATA: Market quote feed stalled (> 60s without ticks).

    3. Technologies used and why:
       Python str and Enum for deterministic serialization and API reporting.

    4. Key design and overall design of the class:
       Standardizes state reporting across the supervisor, loopback admin, and web workstation UI.
    """

    INITIALIZING = "INITIALIZING"
    WARMING_UP = "WARMING_UP"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    HALTED_TIMEOUT = "HALTED_TIMEOUT"
    HALTED_FAULT = "HALTED_FAULT"
    HALTED_DATA = "HALTED_DATA"


class StrategyDeploymentHost:
    """
    1. The use of class:
       Isolated execution container hosting an individual strategy instance within the Live Daemon.

    2. What the class contains:
       - deployment_id: Unique deployment identifier (e.g. 'DEP-LONGCE-01').
       - strategy_id: Strategy class name or identifier (e.g. 'LongCETrendFollowing').
       - strategy: Strategy instance conforming to Strategy(Protocol) or duck-typed test mock.
       - broker: PaperBroker instance for paper order submission and risk checks.
       - account_id: Allocated paper trading account ID.
       - status: Current DeploymentStatus enum.
       - timeout_sec: Maximum permitted execution duration for on_bar and on_tick (default 0.5s).
       - _executor: Dedicated ThreadPoolExecutor isolating execution from other strategies.
       - checkpoint_mgr: Optional CheckpointManager for atomic bar-boundary persistence.
       - start(): Transitions deployment to RUNNING and invokes strategy on_start.
       - step_bar(): Dispatches completed bar to strategy within strict timeout guard.
       - step_tick(): Dispatches tick frame to strategy within strict timeout guard.
       - stop(): Safely shuts down executor and cleans up strategy resources.
       - to_dict(): Serializes host telemetry for supervisor and admin API endpoints.

    3. Technologies used and why:
       - concurrent.futures.ThreadPoolExecutor for bounded thread execution with hard timeout enforcement.
       - Python reflection and signature inspection for adaptive strategy protocol interoperability.
       - Thread-safe state machines for fault-tolerant algorithmic execution.

    4. Key design and overall design of the class:
       Guarantees fault isolation per Milestone M7-07: an infinite loop, blocking I/O, or uncaught
       crash in one strategy is isolated to that specific deployment (marked HALTED_TIMEOUT or
       HALTED_FAULT) without stalling or affecting any peer strategies running in the daemon.
    """

    def __init__(
        self,
        deployment_id: str,
        strategy_id: str,
        strategy: Any,
        broker: PaperBroker,
        account_id: str = "ACC-PAPER-MAIN",
        params: Optional[Dict[str, Any]] = None,
        timeout_sec: float = DEFAULT_STRATEGY_TIMEOUT_SEC,
        checkpoint_manager: Optional[CheckpointManager] = None,
        instrument_key: Optional[str] = None,
    ) -> None:
        """
        1. The use of function:
           Initializes a StrategyDeploymentHost instance with isolated thread execution and broker bindings.

        2. How does the specific function work:
           - Records deployment metadata, allocated account, timeout ceiling, and optional parameters.
           - Sets initial status to DeploymentStatus.INITIALIZING.
           - Spawns a dedicated single-threaded ThreadPoolExecutor for bounded callback isolation.
           - Initializes metric counters (bars_processed, ticks_processed, orders_placed).

        3. Concepts used in the function:
           Dependency injection, worker thread isolation, state initialization.

        4. Places where this function is imported and used:
           Constructed by LiveDaemonSupervisor.register_deployment() and unit test harnesses.

        5. Final output of the function, before and after:
           Before: Uninitialized deployment. After: Configured host ready to start and process data.
        """
        self.deployment_id = deployment_id
        self.strategy_id = strategy_id
        self.strategy = strategy
        self.broker = broker
        self.account_id = account_id
        self.params: Dict[str, Any] = params or {}
        self.timeout_sec = float(timeout_sec)
        self.checkpoint_manager = checkpoint_manager
        self.instrument_key = instrument_key or self.params.get("instrument_key", "NSE_INDEX|Nifty 50")

        self.status: DeploymentStatus = DeploymentStatus.INITIALIZING
        self.last_error: Optional[str] = None
        self.created_at: float = time.time()
        self.last_bar_time: Optional[int] = None
        self.last_tick_time: Optional[int] = None
        self.bars_processed: int = 0
        self.ticks_processed: int = 0
        self.orders_placed: int = 0

        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"Host-{self.deployment_id}",
        )

    def start(self) -> None:
        """
        1. The use of function:
           Starts the strategy deployment lifecycle, invoking on_start and transitioning state to RUNNING.

        2. How does the specific function work:
           - Checks if strategy implements on_start; if present, invokes with configured parameters.
           - If on_start raises an uncaught exception, marks status as HALTED_FAULT and records error.
           - Otherwise, transitions status to DeploymentStatus.RUNNING.

        3. Concepts used in the function:
           Lifecycle progression, duck-typed initialization, exception containment.

        4. Places where this function is imported and used:
           Invoked by LiveDaemonSupervisor.start_deployment() and direct test runners.

        5. Final output of the function, before and after:
           Before: Status INITIALIZING. After: Status RUNNING (or HALTED_FAULT if start hook crashed).
        """
        if hasattr(self.strategy, "on_start") and callable(self.strategy.on_start):
            try:
                self.strategy.on_start(self.params)
            except Exception as exc:
                self.status = DeploymentStatus.HALTED_FAULT
                self.last_error = f"Strategy on_start crashed: {exc}"
                logger.error(f"[{self.deployment_id}] on_start failure: {exc}", exc_info=True)
                return

        self.status = DeploymentStatus.RUNNING
        logger.info(f"[{self.deployment_id}] Strategy host transitioned to RUNNING.")

    def step_bar(
        self,
        bar: Union[StreamingCandle, Dict[str, Any]],
        is_warming_up: bool = False,
    ) -> Optional[Any]:
        """
        1. The use of function:
           Executes strategy logic on bar completion within the strict 500ms timeout boundary.

        2. How does the specific function work:
           - Verifies status: if already halted or stopped, rejects execution immediately.
           - Updates status to WARMING_UP if warming up, or ensures RUNNING if warm-up completes.
           - Dispatches strategy on_bar() to dedicated worker thread with timeout enforcement.
           - Traps TimeoutError (> 500ms): transitions host to HALTED_TIMEOUT without affecting peers.
           - Traps Exception: transitions host to HALTED_FAULT without crashing caller.
           - If is_warming_up is True, suppresses order generation.
           - If not warming up and valid trade signal emitted, routes order to PaperBroker.
           - If CheckpointManager is configured and bar closed, triggers atomic checkpoint persistence.

        3. Concepts used in the function:
           Bounded execution guard, fault containment, signal suppression, order routing.

        4. Places where this function is imported and used:
           Called by LiveDaemonSupervisor.on_bar() and test fixtures.

        5. Final output of the function, before and after:
           Before: Unprocessed completed bar. After: Processed bar, updated metrics, routed orders.
        """
        if self.status in (
            DeploymentStatus.HALTED_TIMEOUT,
            DeploymentStatus.HALTED_FAULT,
            DeploymentStatus.HALTED_DATA,
            DeploymentStatus.STOPPED,
        ):
            return None

        if is_warming_up:
            self.status = DeploymentStatus.WARMING_UP
        elif self.status == DeploymentStatus.WARMING_UP:
            self.status = DeploymentStatus.RUNNING

        try:
            future = self._executor.submit(self._execute_bar_callback, bar, is_warming_up)
            signal = future.result(timeout=self.timeout_sec)
        except concurrent.futures.TimeoutError:
            self.status = DeploymentStatus.HALTED_TIMEOUT
            self.last_error = (
                f"Bar execution exceeded timeout ceiling of {int(self.timeout_sec * 1000)}ms"
            )
            logger.error(f"[{self.deployment_id}] {self.last_error}")
            return None
        except Exception as exc:
            self.status = DeploymentStatus.HALTED_FAULT
            self.last_error = f"Bar execution crashed with uncaught error: {exc}"
            logger.error(f"[{self.deployment_id}] {self.last_error}", exc_info=True)
            return None

        self.bars_processed += 1
        now_epoch = int(time.time())
        self.last_bar_time = now_epoch

        # If warming up, suppress trading signals
        if is_warming_up:
            return signal

        # Dispatch trading intent to paper broker if in RUNNING status
        if signal is not None and self.status == DeploymentStatus.RUNNING:
            self._route_signal_to_broker(signal, bar)

        # Checkpoint persistence on finalized bar
        if self.checkpoint_manager is not None:
            self._persist_checkpoint(bar)

        return signal

    def step_tick(
        self,
        tick: Union[TickFrame, Dict[str, Any]],
    ) -> Optional[Any]:
        """
        1. The use of function:
           Executes optional tick-level strategy logic within the strict 500ms timeout boundary.

        2. How does the specific function work:
           - Verifies host is in RUNNING status; if halted or stopped, returns None.
           - Checks if strategy defines on_tick hook; if absent, records tick and returns.
           - Dispatches strategy on_tick() to worker thread with timeout enforcement.
           - Traps TimeoutError: transitions host to HALTED_TIMEOUT.
           - Traps Exception: transitions host to HALTED_FAULT.
           - Increments ticks_processed counter on success.

        3. Concepts used in the function:
           Tick-level event dispatching, non-blocking fault isolation, execution boundary timeout.

        4. Places where this function is imported and used:
           Called by LiveDaemonSupervisor.on_tick() for high-frequency or tick-level models.

        5. Final output of the function, before and after:
           Before: Incoming market tick frame. After: Evaluated tick, updated tick counters.
        """
        if self.status != DeploymentStatus.RUNNING:
            return None

        if not hasattr(self.strategy, "on_tick") or not callable(self.strategy.on_tick):
            self.ticks_processed += 1
            self.last_tick_time = int(time.time())
            return None

        try:
            future = self._executor.submit(self._execute_tick_callback, tick)
            res = future.result(timeout=self.timeout_sec)
        except concurrent.futures.TimeoutError:
            self.status = DeploymentStatus.HALTED_TIMEOUT
            self.last_error = (
                f"Tick execution exceeded timeout ceiling of {int(self.timeout_sec * 1000)}ms"
            )
            logger.error(f"[{self.deployment_id}] {self.last_error}")
            return None
        except Exception as exc:
            self.status = DeploymentStatus.HALTED_FAULT
            self.last_error = f"Tick execution crashed with uncaught error: {exc}"
            logger.error(f"[{self.deployment_id}] {self.last_error}", exc_info=True)
            return None

        self.ticks_processed += 1
        self.last_tick_time = int(time.time())
        return res

    def _execute_bar_callback(
        self,
        bar: Union[StreamingCandle, Dict[str, Any]],
        is_warming_up: bool,
    ) -> Any:
        """
        1. The use of function:
           Internal worker method invoking strategy on_bar() with dynamic signature inspection.

        2. How does the specific function work:
           - Normalizes bar data into dict representation.
           - Inspects parameter signature of strategy.on_bar():
             * If accepts is_warming_up argument: passes bar and is_warming_up.
             * If accepts (timestamp, features) protocol: unpacks epoch and features dict.
             * Otherwise: passes bar as single argument.
           - Returns the resulting signal or None.

        3. Concepts used in the function:
           Dynamic argument unpacking, inspect.signature inspection, structural subtyping.

        4. Places where this function is imported and used:
           Submitted to self._executor by step_bar().

        5. Final output of the function, before and after:
           Before: Unexecuted bar callback. After: Returned strategy signal or None.
        """
        bar_dict = bar.to_dict() if hasattr(bar, "to_dict") else dict(bar)
        if "close" not in bar_dict and "close_paise" in bar_dict:
            bar_dict["close"] = float(bar_dict["close_paise"]) / 100.0
        if "open" not in bar_dict and "open_paise" in bar_dict:
            bar_dict["open"] = float(bar_dict["open_paise"]) / 100.0
        if "high" not in bar_dict and "high_paise" in bar_dict:
            bar_dict["high"] = float(bar_dict["high_paise"]) / 100.0
        if "low" not in bar_dict and "low_paise" in bar_dict:
            bar_dict["low"] = float(bar_dict["low_paise"]) / 100.0
        if "time_str" not in bar_dict and "bar_start_epoch_sec" in bar_dict:
            bar_start = bar_dict["bar_start_epoch_sec"]
            bar_dict["time_str"] = (
                datetime.fromtimestamp(bar_start, tz=timezone.utc)
                .astimezone(ZoneInfo("Asia/Kolkata"))
                .strftime("%H:%M")
            )

        on_bar_fn = getattr(self.strategy, "on_bar")
        sig = inspect.signature(on_bar_fn)
        param_names = list(sig.parameters.keys())

        if "is_warming_up" in param_names:
            return on_bar_fn(bar_dict, is_warming_up=is_warming_up)

        if len(param_names) >= 2:
            timestamp = bar_dict.get("bar_end_epoch_sec", int(time.time()))
            return on_bar_fn(timestamp, bar_dict)

        return on_bar_fn(bar_dict)

    def _execute_tick_callback(
        self,
        tick: Union[TickFrame, Dict[str, Any]],
    ) -> Any:
        """
        1. The use of function:
           Internal worker method invoking strategy on_tick() with normalized tick payload.

        2. How does the specific function work:
           Invokes self.strategy.on_tick(tick) and returns output.

        3. Concepts used in the function:
           Tick dispatching, delegate execution.

        4. Places where this function is imported and used:
           Submitted to self._executor by step_tick().

        5. Final output of the function, before and after:
           Before: Unexecuted tick callback. After: Returned tick handler result.
        """
        return self.strategy.on_tick(tick)

    def _route_signal_to_broker(
        self,
        signal: Any,
        bar: Union[StreamingCandle, Dict[str, Any]],
    ) -> None:
        """
        1. The use of function:
           Translates a generated StrategySignal into a PaperBroker order or position liquidation.

        2. How does the specific function work:
           - Extracts action (ENTER_LONG, ENTER_SHORT, EXIT, HOLD).
           - Resolves instrument key and traded price from bar.
           - Submits buy/sell orders for entries via broker.submit_order().
           - Triggers position square-off for exit signals via broker.square_off_position().
           - Increments orders_placed metric counter.

        3. Concepts used in the function:
           Order translation, broker integration, position liquidation.

        4. Places where this function is imported and used:
           Called internally by step_bar() when valid signal is emitted in RUNNING state.

        5. Final output of the function, before and after:
           Before: Unexecuted signal. After: Routed paper order and updated position inventory.
        """
        action = getattr(signal, "action", None)
        if action is None or action == SignalAction.HOLD:
            return

        bar_dict = bar.to_dict() if hasattr(bar, "to_dict") else dict(bar)
        ltp_paise = bar_dict.get("close_paise", 0)
        current_time_str = bar_dict.get("time_str")
        if not current_time_str and "bar_start_epoch_sec" in bar_dict:
            bar_start = bar_dict["bar_start_epoch_sec"]
            current_time_str = (
                datetime.fromtimestamp(bar_start, tz=timezone.utc)
                .astimezone(ZoneInfo("Asia/Kolkata"))
                .strftime("%H:%M")
            )
        current_epoch_sec = bar_dict.get("bar_end_epoch_sec")
        instrument_key = (
            getattr(signal, "target_contract", None).instrument_key
            if getattr(signal, "target_contract", None)
            else self.instrument_key
        )
        trading_symbol = instrument_key.split("|")[-1] if "|" in instrument_key else instrument_key
        quantity = self.params.get(
            "quantity",
            self.params.get("lots", 1) * 65 if "lots" in self.params else 25,
        )

        if action == SignalAction.ENTER_LONG:
            self.broker.submit_order(
                account_id=self.account_id,
                instrument_key=instrument_key,
                trading_symbol=trading_symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                order_type="MARKET",
                strategy_id=self.strategy_id,
                ltp_paise=ltp_paise,
                current_time_str=current_time_str,
                current_epoch_sec=current_epoch_sec,
            )
            self.orders_placed += 1
        elif action == SignalAction.ENTER_SHORT:
            self.broker.submit_order(
                account_id=self.account_id,
                instrument_key=instrument_key,
                trading_symbol=trading_symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                order_type="MARKET",
                strategy_id=self.strategy_id,
                ltp_paise=ltp_paise,
                current_time_str=current_time_str,
                current_epoch_sec=current_epoch_sec,
            )
            self.orders_placed += 1
        elif action == SignalAction.EXIT:
            self.broker.square_off_position(
                account_id=self.account_id,
                instrument_key=instrument_key,
                exit_price_paise=ltp_paise,
                current_epoch_sec=current_epoch_sec,
            )

    def _persist_checkpoint(
        self,
        bar: Union[StreamingCandle, Dict[str, Any]],
    ) -> None:
        """
        1. The use of function:
           Persists atomic strategy state checkpoint to SQLite WAL and atomic JSON files.

        2. How does the specific function work:
           - Reads account balances and position from the broker.
           - Gathers working orders.
           - Delegates serialization to CheckpointManager.save_checkpoint().

        3. Concepts used in the function:
           Atomic dual persistence, checkpointing, state serialization.

        4. Places where this function is imported and used:
           Invoked at the conclusion of step_bar() when checkpoint_manager is configured.

        5. Final output of the function, before and after:
           Before: Uncheckpointed bar boundary. After: Serialized checkpoint record on disk.
        """
        if self.checkpoint_manager is None:
            return

        bar_dict = bar.to_dict() if hasattr(bar, "to_dict") else dict(bar)
        bar_epoch = bar_dict.get("bar_end_epoch_sec", int(time.time()))
        account = self.broker.get_account(self.account_id)
        pos = self.broker.get_position(self.account_id, self.instrument_key)
        working_orders = [
            o.to_dict() for o in self.broker.get_working_orders(self.account_id)
        ]

        try:
            self.checkpoint_manager.save_checkpoint(
                strategy_id=self.deployment_id,
                last_seq_id=self.bars_processed,
                active_position=pos.to_dict() if pos else None,
                working_orders=working_orders,
                cash_paise=account.cash_paise if account else 0,
                unrealized_pnl_paise=account.unrealized_pnl_paise if account else 0,
                bar_epoch_sec=bar_epoch,
            )
        except Exception as exc:
            logger.warning(f"[{self.deployment_id}] Failed to save bar checkpoint: {exc}")

    def stop(self) -> None:
        """
        1. The use of function:
           Shuts down the deployment host, invokes strategy cleanup hook, and drains executor.

        2. How does the specific function work:
           - Sets status to DeploymentStatus.STOPPED.
           - Checks if strategy implements on_stop hook; if present, invokes it safely.
           - Shuts down worker thread pool without blocking on hung tasks.

        3. Concepts used in the function:
           Clean resource teardown, executor drainage, graceful stop.

        4. Places where this function is imported and used:
           Invoked by LiveDaemonSupervisor.stop_deployment() and shutdown procedures.

        5. Final output of the function, before and after:
           Before: Active host. After: Terminated host with released thread resources.
        """
        self.status = DeploymentStatus.STOPPED
        if hasattr(self.strategy, "on_stop") and callable(self.strategy.on_stop):
            try:
                self.strategy.on_stop()
            except Exception as exc:
                logger.warning(f"[{self.deployment_id}] Error in strategy on_stop: {exc}")

        self._executor.shutdown(wait=False, cancel_futures=True)
        logger.info(f"[{self.deployment_id}] Strategy host shut down.")

    def to_dict(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Serializes current host status, configuration, and telemetry to a dictionary.

        2. How does the specific function work:
           Constructs dictionary containing deployment_id, strategy_id, status, metrics, and error info.

        3. Concepts used in the function:
           State serialization, REST API payload mapping.

        4. Places where this function is imported and used:
           Used by supervisor telemetry, loopback admin endpoints, and test assertions.

        5. Final output of the function, before and after:
           Before: StrategyDeploymentHost instance. After: JSON-serializable telemetry dictionary.
        """
        return {
            "deployment_id": self.deployment_id,
            "strategy_id": self.strategy_id,
            "account_id": self.account_id,
            "status": self.status.value,
            "timeout_sec": self.timeout_sec,
            "instrument_key": self.instrument_key,
            "bars_processed": self.bars_processed,
            "ticks_processed": self.ticks_processed,
            "orders_placed": self.orders_placed,
            "last_bar_time": self.last_bar_time,
            "last_tick_time": self.last_tick_time,
            "last_error": self.last_error,
            "created_at": self.created_at,
        }
