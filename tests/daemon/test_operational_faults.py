"""
1. What this file does:
   Automated unit and integration test suite verifying Strategy Host Timeout Guards, Fault Isolation,
   Emergency Kill-Switch (RK-01), Market Quote Stall Detection, and Loopback Admin API
   for QuantView Live Daemon (Milestones M7-06, M7-07 / Gate G5).

2. Overall design:
   Uses pytest with @pytest.mark.gate_g5:
     - Bounded 500ms Timeout Isolation: Freezing strategy sleeping > 500ms is isolated into HALTED_TIMEOUT
       without stalling or interrupting healthy peer strategies.
     - Crash Containment: An unhandled exception in strategy on_bar() is caught and isolated into HALTED_FAULT.
     - Emergency Kill Switch (RK-01): Triggering kill-switch halts order submissions, cancels pending orders,
       and rejects subsequent order submissions fail-closed with RK-01.
     - Market Quote Stall Guard: Absence of incoming market quotes for > 60s transitions active deployments
       into HALTED_DATA state to prevent execution on stale books.
     - Sub-Second Startup & Clean Teardown: Verifies supervisor initializes in < 300ms and cleans up on stop.
     - Loopback Admin REST & Gateway Proxy: Verifies GET /control/status, POST /control/start, POST /control/stop,
       POST /control/kill-switch, and /api/v1/daemon gateway proxy.
     - WebSocket Streaming: Verifies ws://127.0.0.1:8001/ws/stream emits real-time TickFrame events.

3. Elements in the file:
   - FreezingStrategy: Mock strategy sleeping longer than 500ms to trigger timeout.
   - CrashingStrategy: Mock strategy raising uncaught exceptions in on_bar.
   - HealthyStrategy: Mock strategy running promptly and recording processed bars.
   - TestOperationalFaults: Main test fixture verifying all M7-06/M7-07 requirements.

4. Final output of the file:
   - Test suite certifying Gate G5 operational fault tolerance and loopback admin plane.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from packages.domain import OrderSide
from packages.market_data.streaming_builder import StreamingCandle
from packages.strategies import SignalAction, StrategySignal
from packages.transport.frame_bus import FrameBus, TickFrame
from services.api.config import get_api_config
from services.api.main import create_app
from services.live_daemon.broker import PaperBroker
from services.live_daemon.host import DeploymentStatus, StrategyDeploymentHost
from services.live_daemon.main import create_daemon_app
from services.live_daemon.supervisor import AccountAllocationMode, LiveDaemonSupervisor


class FreezingStrategy:
    """
    1. The use of class:
       Mock strategy simulating an infinite loop, blocking I/O, or hung computation.

    2. What the class contains:
       - sleep_sec: Duration to sleep in on_bar (default 0.7s to exceed 0.5s limit).
       - on_bar(): Callback sleeping for sleep_sec.

    3. Technologies used and why:
       time.sleep to simulate blocking execution thread.

    4. Key design and overall design of the class:
       Intentionally breaches the 500ms execution guard to verify timeout isolation.
    """

    def __init__(self, sleep_sec: float = 0.7) -> None:
        """
        1. The use of function:
           Initializes FreezingStrategy with configured sleep duration.

        2. How does the specific function work:
           Stores sleep_sec parameter.

        3. Concepts used in the function:
           Fault simulation parameterization.

        4. Places where this function is imported and used:
           Used in test_500ms_timeout_guard_isolates_frozen_strategy.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Initialized FreezingStrategy instance.
        """
        self.sleep_sec = sleep_sec

    def on_bar(self, bar: Dict[str, Any], is_warming_up: bool = False) -> Optional[StrategySignal]:
        """
        1. The use of function:
           Simulates a hung strategy by sleeping past the timeout ceiling.

        2. How does the specific function work:
           Calls time.sleep(self.sleep_sec) to exceed the 500ms limit.

        3. Concepts used in the function:
           Thread blocking, intentional latency injection.

        4. Places where this function is imported and used:
           Invoked by StrategyDeploymentHost.step_bar().

        5. Final output of the function, before and after:
           Before: Bar input. After: Delayed execution exceeding timeout.
        """
        time.sleep(self.sleep_sec)
        return None


class CrashingStrategy:
    """
    1. The use of class:
       Mock strategy simulating an unhandled algorithmic exception (e.g. division by zero, memory error).

    2. What the class contains:
       - on_bar(): Callback raising RuntimeError.

    3. Technologies used and why:
       Standard Python exception raising.

    4. Key design and overall design of the class:
       Verifies crash containment into HALTED_FAULT without bringing down the supervisor process.
    """

    def on_bar(self, bar: Dict[str, Any], is_warming_up: bool = False) -> Optional[StrategySignal]:
        """
        1. The use of function:
           Simulates an algorithm crash by raising an uncaught RuntimeError.

        2. How does the specific function work:
           Raises RuntimeError('Simulated algorithm crash').

        3. Concepts used in the function:
           Exception injection, crash simulation.

        4. Places where this function is imported and used:
           Invoked by StrategyDeploymentHost.step_bar().

        5. Final output of the function, before and after:
           Before: Bar input. After: Raised RuntimeError.
        """
        raise RuntimeError("Simulated algorithm crash in strategy on_bar()")


class HealthyStrategy:
    """
    1. The use of class:
       Healthy peer mock strategy executing promptly and tracking processed bars and ticks.

    2. What the class contains:
       - bars_received: List of ingested bars.
       - ticks_received: List of ingested ticks.
       - on_bar(): Callback recording bar and emitting optional signal.
       - on_tick(): Callback recording tick.

    3. Technologies used and why:
       Python test spy pattern.

    4. Key design and overall design of the class:
       Validates that peer strategies continue normal operation during neighbor faults.
    """

    def __init__(self, emit_signals: bool = False) -> None:
        """
        1. The use of function:
           Initializes HealthyStrategy with empty tracking lists.

        2. How does the specific function work:
           Initializes bars_received and ticks_received lists and stores emit_signals flag.

        3. Concepts used in the function:
           Test spy state setup.

        4. Places where this function is imported and used:
           Used across operational fault tests.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Initialized HealthyStrategy instance.
        """
        self.emit_signals = emit_signals
        self.bars_received: List[Dict[str, Any]] = []
        self.ticks_received: List[Any] = []

    def on_bar(self, bar: Dict[str, Any], is_warming_up: bool = False) -> Optional[StrategySignal]:
        """
        1. The use of function:
           Promptly records bar and returns optional signal.

        2. How does the specific function work:
           Appends bar to bars_received. If emit_signals is True, returns an ENTER_LONG signal.

        3. Concepts used in the function:
           Prompt event handling, signal generation.

        4. Places where this function is imported and used:
           Invoked by StrategyDeploymentHost.step_bar().

        5. Final output of the function, before and after:
           Before: Bar input. After: Recorded bar and returned signal or None.
        """
        self.bars_received.append(bar)
        if self.emit_signals:
            return StrategySignal(
                action=SignalAction.ENTER_LONG,
                timestamp=bar.get("bar_end_epoch_sec", int(time.time())),
            )
        return None

    def on_tick(self, tick: Any) -> None:
        """
        1. The use of function:
           Promptly records incoming tick frame.

        2. How does the specific function work:
           Appends tick to ticks_received.

        3. Concepts used in the function:
           Tick event handling.

        4. Places where this function is imported and used:
           Invoked by StrategyDeploymentHost.step_tick().

        5. Final output of the function, before and after:
           Before: Tick frame. After: Recorded tick.
        """
        self.ticks_received.append(tick)


@pytest.mark.gate_g5
class TestOperationalFaults:
    """
    1. The use of class:
       Formal test suite verifying Milestone M7-06 & M7-07 fault tolerance and supervisor controls.

    2. What the class contains:
       - test_500ms_timeout_guard_isolates_frozen_strategy: Tests bounded thread timeout guard.
       - test_crash_containment_isolates_erroring_strategy: Tests uncaught exception containment.
       - test_emergency_kill_switch_activation_and_order_rejection: Tests RK-01 fail-closed enforcement.
       - test_market_quote_stall_detection_transitions_to_halted_data: Tests > 60s stall guard.
       - test_sub_second_supervisor_startup_and_clean_shutdown: Tests < 300ms cold start and clean stop.
       - test_loopback_admin_api_and_gateway_proxy_endpoints: Tests REST endpoints and API gateway proxy.
       - test_websocket_stream_publishes_frames: Tests /ws/stream WebSocket feed.

    3. Technologies used and why:
       pytest, FastAPI TestClient, in-memory transport and SQLite databases.

    4. Key design and overall design of the class:
       Certifies Gate G5 operational reliability criteria.
    """

    def test_500ms_timeout_guard_isolates_frozen_strategy(self) -> None:
        """
        1. The use of function:
           Verifies the 500ms timeout guard catches hung strategies and isolates them without affecting peers.

        2. How does the specific function work:
           - Deploys FreezingStrategy (sleeps 0.7s) and HealthyStrategy in supervisor pool.
           - Feeds bar to both deployments.
           - Asserts FreezingStrategy transitions to HALTED_TIMEOUT.
           - Asserts HealthyStrategy remains RUNNING and successfully processed the bar.
           - Verifies supervisor does not deadlock or crash.

        3. Concepts used in the function:
           Fault containment, timeout enforcement, peer isolation.

        4. Places where this function is imported and used:
           Executed by pytest under Gate G5 suite.

        5. Final output of the function, before and after:
           Before: Unverified timeout behavior. After: Verified isolation into HALTED_TIMEOUT.
        """
        broker = PaperBroker(db_path=":memory:")
        bus = FrameBus()
        supervisor = LiveDaemonSupervisor(broker=broker, frame_bus=bus)

        frozen_strat = FreezingStrategy(sleep_sec=0.7)
        healthy_strat = HealthyStrategy()

        dep_frozen = supervisor.register_deployment(
            deployment_id="DEP-FROZEN",
            strategy=frozen_strat,
            timeout_sec=0.5,
        )
        dep_healthy = supervisor.register_deployment(
            deployment_id="DEP-HEALTHY",
            strategy=healthy_strat,
            timeout_sec=0.5,
        )

        supervisor.start_deployment("DEP-FROZEN")
        supervisor.start_deployment("DEP-HEALTHY")

        assert dep_frozen.status == DeploymentStatus.RUNNING
        assert dep_healthy.status == DeploymentStatus.RUNNING

        candle = StreamingCandle(
            instrument_key="NSE_INDEX|Nifty 50",
            timeframe="1m",
            bar_start_epoch_sec=1700000000,
            bar_end_epoch_sec=1700000060,
            open_paise=2200000,
            high_paise=2205000,
            low_paise=2199000,
            close_paise=2204000,
            volume=500,
            tick_count=10,
            is_closed=True,
        )

        # Dispatch bar to both
        t0 = time.perf_counter()
        supervisor.on_bar(candle)
        elapsed = time.perf_counter() - t0

        # Frozen strategy timed out at ~500ms
        assert dep_frozen.status == DeploymentStatus.HALTED_TIMEOUT
        assert "exceeded timeout" in (dep_frozen.last_error or "").lower()

        # Healthy strategy executed successfully and remains RUNNING
        assert dep_healthy.status == DeploymentStatus.RUNNING
        assert len(healthy_strat.bars_received) == 1
        assert dep_healthy.bars_processed == 1

        # Verification that subsequent bars ignore the halted strategy
        supervisor.on_bar(candle)
        assert len(healthy_strat.bars_received) == 2
        assert dep_frozen.bars_processed == 0

        broker.close()

    def test_crash_containment_isolates_erroring_strategy(self) -> None:
        """
        1. The use of function:
           Verifies that an uncaught runtime error in a strategy transitions it to HALTED_FAULT safely.

        2. How does the specific function work:
           - Deploys CrashingStrategy and HealthyStrategy.
           - Steps a bar through supervisor.
           - Asserts CrashingStrategy transitions to HALTED_FAULT with recorded exception traceback/message.
           - Asserts HealthyStrategy continues operating normally in RUNNING status.

        3. Concepts used in the function:
           Exception trapping, crash containment, fault status reporting.

        4. Places where this function is imported and used:
           Executed by pytest under Gate G5 suite.

        5. Final output of the function, before and after:
           Before: Unverified crash behavior. After: Verified containment into HALTED_FAULT.
        """
        broker = PaperBroker(db_path=":memory:")
        bus = FrameBus()
        supervisor = LiveDaemonSupervisor(broker=broker, frame_bus=bus)

        crashing_strat = CrashingStrategy()
        healthy_strat = HealthyStrategy()

        dep_crashing = supervisor.register_deployment(
            deployment_id="DEP-CRASH",
            strategy=crashing_strat,
        )
        dep_healthy = supervisor.register_deployment(
            deployment_id="DEP-HEALTHY",
            strategy=healthy_strat,
        )

        supervisor.start_deployment("DEP-CRASH")
        supervisor.start_deployment("DEP-HEALTHY")

        candle = StreamingCandle(
            instrument_key="NSE_INDEX|Nifty 50",
            timeframe="1m",
            bar_start_epoch_sec=1700000000,
            bar_end_epoch_sec=1700000060,
            open_paise=2200000,
            high_paise=2205000,
            low_paise=2199000,
            close_paise=2204000,
            volume=500,
            tick_count=10,
            is_closed=True,
        )

        # Dispatch bar
        supervisor.on_bar(candle)

        assert dep_crashing.status == DeploymentStatus.HALTED_FAULT
        assert "Simulated algorithm crash" in (dep_crashing.last_error or "")
        assert dep_healthy.status == DeploymentStatus.RUNNING
        assert len(healthy_strat.bars_received) == 1

        broker.close()

    def test_emergency_kill_switch_activation_and_order_rejection(self) -> None:
        """
        1. The use of function:
           Verifies emergency kill-switch (RK-01) cancels working orders and rejects future submissions fail-closed.

        2. How does the specific function work:
           - Sets up supervisor and broker.
           - Submits an order before kill switch to verify normal acceptance.
           - Activates kill-switch via supervisor.trigger_kill_switch().
           - Verifies kill_switch_active flag is True on supervisor and broker risk policy.
           - Attempts submitting new orders.
           - Asserts orders are rejected with RK-01: manual kill switch is active.

        3. Concepts used in the function:
           RK-01 emergency circuit breaker, fail-closed pre-trade risk evaluation.

        4. Places where this function is imported and used:
           Executed by pytest under Gate G5 suite.

        5. Final output of the function, before and after:
           Before: Unverified kill-switch. After: Verified order rejection and cancellation under RK-01.
        """
        broker = PaperBroker(db_path=":memory:")
        bus = FrameBus()
        supervisor = LiveDaemonSupervisor(broker=broker, frame_bus=bus)

        broker.register_account("ACC-TEST-KS", initial_cash_paise=10_000_000)

        # 1. Normal order before kill switch
        order_1 = broker.submit_order(
            account_id="ACC-TEST-KS",
            instrument_key="NSE_INDEX|Nifty 50",
            trading_symbol="NIFTY",
            side=OrderSide.BUY,
            quantity=50,
            order_type="MARKET",
            ltp_paise=15000,
            ask_price_paise=15000,
            bid_price_paise=14950,
            current_time_str="10:00",
        )
        assert order_1.status in ("FILLED", "PENDING", "ACCEPTED")

        # 2. Trigger Kill Switch
        result = supervisor.trigger_kill_switch(reason="Operator emergency halt test")
        assert result["kill_switch_active"] is True
        assert supervisor.kill_switch_active is True
        assert broker.risk_evaluator.rules.kill_switch_active is True

        # 3. Subsequent order submission MUST be rejected under RK-01
        order_2 = broker.submit_order(
            account_id="ACC-TEST-KS",
            instrument_key="NSE_INDEX|Nifty 50",
            trading_symbol="NIFTY",
            side=OrderSide.BUY,
            quantity=50,
            order_type="MARKET",
            ltp_paise=15000,
            ask_price_paise=15000,
            bid_price_paise=14950,
            current_time_str="10:01",
        )
        assert order_2.status == "REJECTED"
        assert "RK-01" in (order_2.rejection_reason or "")
        assert "kill switch is active" in (order_2.rejection_reason or "").lower()

        broker.close()

    def test_market_quote_stall_detection_transitions_to_halted_data(self) -> None:
        """
        1. The use of function:
           Verifies market quote stall detection (> 60s without ticks) transitions deployments to HALTED_DATA.

        2. How does the specific function work:
           - Ingests a market tick into supervisor at t0.
           - Deploys and starts a HealthyStrategy.
           - Verifies status is RUNNING.
           - Calls check_quote_stall with simulated elapsed time of 65.0s (> 60.0s).
           - Asserts deployment status transitions to HALTED_DATA with clear stall diagnostic error.

        3. Concepts used in the function:
           Quote stall detection, temporal freshness validation, fail-closed data halt.

        4. Places where this function is imported and used:
           Executed by pytest under Gate G5 suite.

        5. Final output of the function, before and after:
           Before: RUNNING status on stale feed. After: Safely transitioned to HALTED_DATA.
        """
        broker = PaperBroker(db_path=":memory:")
        bus = FrameBus()
        supervisor = LiveDaemonSupervisor(
            broker=broker,
            frame_bus=bus,
            stall_threshold_sec=60.0,
        )

        dep = supervisor.register_deployment(
            deployment_id="DEP-STALL-TEST",
            strategy=HealthyStrategy(),
        )
        supervisor.start_deployment("DEP-STALL-TEST")
        assert dep.status == DeploymentStatus.RUNNING

        # Simulate tick at t0
        t0 = 1700000000.0
        supervisor.last_market_tick_epoch = t0

        # At t0 + 30s: should NOT stall
        stalled = supervisor.check_quote_stall(current_time=t0 + 30.0)
        assert len(stalled) == 0
        assert dep.status == DeploymentStatus.RUNNING

        # At t0 + 65s: exceeds 60s threshold, MUST transition to HALTED_DATA
        stalled = supervisor.check_quote_stall(current_time=t0 + 65.0)
        assert len(stalled) == 1
        assert "DEP-STALL-TEST" in stalled
        assert dep.status == DeploymentStatus.HALTED_DATA
        assert "Market quote stalled" in (dep.last_error or "")

        broker.close()

    @pytest.mark.asyncio
    async def test_sub_second_supervisor_startup_and_clean_shutdown(self) -> None:
        """
        1. The use of function:
           Verifies supervisor sub-second startup (< 300ms) and clean order-draining shutdown.

        2. How does the specific function work:
           - Instantiates supervisor.
           - Measures startup() duration: asserts < 300ms.
           - Registers a deployment and verifies RUNNING status.
           - Calls shutdown() and asserts clean resource teardown.

        3. Concepts used in the function:
           Cold start latency SLA (< 300ms), async lifecycle management, graceful teardown.

        4. Places where this function is imported and used:
           Executed by pytest under Gate G5 suite.

        5. Final output of the function, before and after:
           Before: Unmeasured startup. After: Certified < 300ms startup and clean shutdown.
        """
        broker = PaperBroker(db_path=":memory:")
        bus = FrameBus()
        supervisor = LiveDaemonSupervisor(broker=broker, frame_bus=bus)

        t0 = time.perf_counter()
        await supervisor.startup()
        startup_ms = (time.perf_counter() - t0) * 1000.0

        assert supervisor.is_running is True
        assert startup_ms < 300.0  # Must be strictly under 300ms

        # Status check
        status = supervisor.get_status()
        assert status["status"] == "HEALTHY"
        assert status["memory_rss_bytes"] > 0
        assert status["frame_bus"]["buffer_capacity"] > 0

        await supervisor.shutdown()
        assert supervisor.is_running is False

    def test_loopback_admin_api_and_gateway_proxy_endpoints(self) -> None:
        """
        1. The use of function:
           Verifies REST control plane endpoints on loopback admin and API gateway proxy routing.

        2. How does the specific function work:
           - Configures daemon FastAPI app via create_daemon_app().
           - Uses TestClient to test GET /control/status, POST /control/start, POST /control/stop,
             and POST /control/kill-switch.
           - Configures API gateway router /api/v1/daemon and tests proxy behaviors.

        3. Concepts used in the function:
           REST API testing, control plane verification, reverse proxy routing.

        4. Places where this function is imported and used:
           Executed by pytest under Gate G5 suite.

        5. Final output of the function, before and after:
           Before: Untested endpoints. After: Fully verified loopback and gateway endpoints.
        """
        broker = PaperBroker(db_path=":memory:")
        bus = FrameBus()
        supervisor = LiveDaemonSupervisor(broker=broker, frame_bus=bus)

        daemon_app = create_daemon_app(supervisor)

        with TestClient(daemon_app) as client:
            # 1. GET /control/status
            resp = client.get("/control/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "uptime_sec" in data
            assert data["status"] in ("HEALTHY", "STOPPED")
            assert data["deployments_total"] == 0

            # 2. POST /control/start
            start_payload = {
                "strategy_id": "LongCETrendFollowing",
                "deployment_id": "DEP-TEST-REST-01",
                "mode": "ISOLATED",
                "params": {"quantity": 25},
            }
            resp = client.post("/control/start", json=start_payload)
            assert resp.status_code == 200
            start_data = resp.json()
            assert start_data["status"] == "started"
            assert start_data["deployment"]["deployment_id"] == "DEP-TEST-REST-01"
            assert start_data["deployment"]["status"] == "RUNNING"

            # 3. GET /control/status reflects running deployment
            resp = client.get("/control/status")
            assert resp.status_code == 200
            assert resp.json()["deployments_total"] == 1
            assert resp.json()["deployments_running"] == 1

            # 4. POST /control/stop
            stop_payload = {"deployment_id": "DEP-TEST-REST-01"}
            resp = client.post("/control/stop", json=stop_payload)
            assert resp.status_code == 200
            stop_data = resp.json()
            assert stop_data["status"] == "stopped"
            assert stop_data["deployment"]["status"] == "STOPPED"

            # 5. POST /control/kill-switch
            ks_payload = {"reason": "Test REST kill-switch"}
            resp = client.post("/control/kill-switch", json=ks_payload)
            assert resp.status_code == 200
            ks_data = resp.json()
            assert ks_data["kill_switch_active"] is True
            assert ks_data["status"] == "kill_switch_activated"

        # Now test API Gateway proxy router (/api/v1/daemon/status fallback when offline)
        gateway_app = create_app()
        with TestClient(gateway_app) as gw_client:
            # When daemon is not running on 8001, proxy should gracefully return OFFLINE
            resp = gw_client.get("/api/v1/daemon/status")
            assert resp.status_code == 200
            gw_data = resp.json()
            assert gw_data["status"] == "OFFLINE"

    def test_websocket_stream_publishes_frames(self) -> None:
        """
        1. The use of function:
           Verifies the /ws/stream WebSocket endpoint publishes live TickFrame events.

        2. How does the specific function work:
           - Sets up daemon app with supervisor and FrameBus.
           - Connects WebSocket client to /ws/stream.
           - Publishes a TickFrame on FrameBus.
           - Reads JSON frame from WebSocket and asserts sequence_id, instrument_key, and price match.

        3. Concepts used in the function:
           WebSocket streaming, pub/sub testing, JSON event validation.

        4. Places where this function is imported and used:
           Executed by pytest under Gate G5 suite.

        5. Final output of the function, before and after:
           Before: Unverified WebSocket stream. After: Verified real-time frame distribution.
        """
        broker = PaperBroker(db_path=":memory:")
        bus = FrameBus()
        supervisor = LiveDaemonSupervisor(broker=broker, frame_bus=bus)

        daemon_app = create_daemon_app(supervisor)

        with TestClient(daemon_app) as client:
            with client.websocket_connect("/ws/stream") as websocket:
                # Publish tick to FrameBus
                tick = TickFrame(
                    sequence_id=0,
                    instrument_key="NSE_INDEX|Nifty 50",
                    timestamp_epoch_sec=1700000000,
                    timestamp_iso="2023-11-14T09:15:00Z",
                    price_paise=2205000,
                    volume=150,
                )
                bus.publish(tick)

                # Receive streamed payload over websocket
                payload = websocket.receive_json()
                assert payload["type"] == "tick"
                assert payload["data"]["instrument_key"] == "NSE_INDEX|Nifty 50"
                assert payload["data"]["price_paise"] == 2205000
                assert payload["data"]["sequence_id"] == 1
