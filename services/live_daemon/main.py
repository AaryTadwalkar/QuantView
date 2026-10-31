"""
1. What this file does:
   Live Daemon process entrypoint and internal loopback administrative control server
   (Milestone M7-07, Gate G5). Exposes HTTP endpoints on http://127.0.0.1:8001 for status,
   deployment lifecycle control, emergency kill-switch, and high-speed WebSocket market streaming.

2. Overall design:
   Enforces QUANTVIEW_MASTER_SPEC §2.2 and Milestone M7-07:
     - Internal Loopback Control Plane: Binds to 127.0.0.1:8001 (isolated from external public interfaces).
     - REST Telemetry & Control:
       * GET /control/status: Operational health, uptime, active deployments, memory RSS, FrameBus stats.
       * POST /control/start: Launches or registers a strategy deployment with dynamic parameters.
       * POST /control/stop: Stops an active strategy deployment and drains its working orders.
       * POST /control/kill-switch: Triggers emergency circuit breaker RK-01 fail-closed rejection.
     - High-Speed Stream Bridge: WebSocket ws://127.0.0.1:8001/ws/stream publishing real-time TickFrame
       and StreamingCandle events directly from FrameBus transport to local subscribers.
     - Lifespan State Management: Coordinates sub-second startup (< 300ms) and clean shutdown.

3. Elements in the file:
   - StartDeploymentRequest: Pydantic request model for starting/registering a strategy deployment.
   - StopDeploymentRequest: Pydantic request model for stopping a deployment.
   - KillSwitchRequest: Pydantic request model for triggering emergency RK-01 circuit breaker.
   - DaemonStreamManager: Connection hub broadcasting ticks and streaming candles to WebSockets.
   - create_daemon_app: Factory constructing configured FastAPI application.
   - app: Global application instance for ASGI servers (uvicorn).

4. Final output of the file:
   - FastAPI application instance and CLI entrypoint for running the QuantView Live Daemon service.
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from packages.market_data.streaming_builder import StreamingCandleBuilder
from packages.transport.frame_bus import FrameBus, TickFrame
from packages.transport.replay_player import PlaybackSpeed, ReplayPlayer
from services.live_daemon.broker import PaperBroker
from services.live_daemon.host import StrategyDeploymentHost
from services.live_daemon.supervisor import AccountAllocationMode, LiveDaemonSupervisor

logger = logging.getLogger(__name__)


class StartDeploymentRequest(BaseModel):
    """
    1. The use of class:
       Pydantic validation schema for requests to start or register a strategy deployment.

    2. What the class contains:
       - strategy_id: Strategy class identifier or registered catalog name.
       - deployment_id: Optional unique identifier; auto-generated if omitted.
       - account_id: Optional specific paper account ID.
       - instrument_key: Target financial instrument key (default 'NSE_INDEX|Nifty 50').
       - params: Optional strategy initialization parameter dictionary.
       - mode: Optional account allocation mode ('ISOLATED' or 'PORTFOLIO').
       - timeout_sec: Optional per-step execution timeout ceiling (default 0.5s).

    3. Technologies used and why:
       Pydantic v2 BaseModel for strict request validation and schema introspection.

    4. Key design and overall design of the class:
       Standardizes input payloads for POST /control/start.
    """

    model_config = ConfigDict(extra="ignore")

    strategy_id: str = Field(..., description="Registered strategy class name or identifier")
    deployment_id: Optional[str] = Field(None, description="Unique deployment identifier")
    account_id: Optional[str] = Field(None, description="Target paper account ID")
    instrument_key: Optional[str] = Field("NSE_INDEX|Nifty 50", description="Financial instrument key")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Strategy parameters")
    mode: Optional[str] = Field(None, description="ADR-038 allocation mode: ISOLATED or PORTFOLIO")
    timeout_sec: Optional[float] = Field(0.5, description="Execution timeout limit in seconds")


class StopDeploymentRequest(BaseModel):
    """
    1. The use of class:
       Pydantic validation schema for requests to stop an active strategy deployment.

    2. What the class contains:
       - deployment_id: Unique deployment identifier of the strategy host to halt.

    3. Technologies used and why:
       Pydantic v2 BaseModel with frozen configuration for deterministic stop requests.

    4. Key design and overall design of the class:
       Standardizes input payload for POST /control/stop.
    """

    model_config = ConfigDict(extra="ignore")

    deployment_id: str = Field(..., description="Unique deployment identifier to stop")


class KillSwitchRequest(BaseModel):
    """
    1. The use of class:
       Pydantic validation schema for triggering the emergency kill-switch (RK-01).

    2. What the class contains:
       - reason: Diagnostic explanation recorded in audit logs and ledger events.

    3. Technologies used and why:
       Pydantic v2 BaseModel for circuit breaker commands.

    4. Key design and overall design of the class:
       Standardizes input payload for POST /control/kill-switch.
    """

    model_config = ConfigDict(extra="ignore")

    reason: Optional[str] = Field(
        "Operator emergency kill-switch",
        description="Audit reason for kill-switch activation",
    )


class DaemonStreamManager:
    """
    1. The use of class:
       Coordinates active WebSocket subscriber connections for real-time tick and candle streaming.

    2. What the class contains:
       - active_connections: Set of connected client WebSocket instances.
       - connect(): Accepts and registers new WebSocket client.
       - disconnect(): Unregisters disconnected WebSocket client.
       - broadcast(): Distributes JSON message to all connected clients.

    3. Technologies used and why:
       FastAPI WebSockets and asyncio for low-latency non-blocking streaming.

    4. Key design and overall design of the class:
       Lightweight in-memory hub bridging FrameBus and CandleBuilder events to loopback clients.
    """

    def __init__(self) -> None:
        """
        1. The use of function:
           Initializes empty subscriber set for DaemonStreamManager.

        2. How does the specific function work:
           Allocates empty set for active WebSocket references.

        3. Concepts used in the function:
           State initialization, connection registry.

        4. Places where this function is imported and used:
           Instantiated in create_daemon_app.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Initialized connection hub.
        """
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """
        1. The use of function:
           Accepts incoming WebSocket handshake and adds to active subscriber pool.

        2. How does the specific function work:
           Calls await websocket.accept() and adds websocket to active_connections set.

        3. Concepts used in the function:
           WebSocket handshake, connection registration.

        4. Places where this function is imported and used:
           Called in /ws/stream endpoint handler.

        5. Final output of the function, before and after:
           Before: Pending connection. After: Accepted registered connection.
        """
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """
        1. The use of function:
           Removes a disconnected WebSocket from the active subscriber pool.

        2. How does the specific function work:
           Discards websocket from active_connections set.

        3. Concepts used in the function:
           Safe teardown, set cleanup.

        4. Places where this function is imported and used:
           Called in /ws/stream endpoint on disconnect or network error.

        5. Final output of the function, before and after:
           Before: Registered connection. After: Cleanly unregistered connection.
        """
        self.active_connections.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """
        1. The use of function:
           Asynchronously broadcasts a JSON payload to all currently connected WebSocket clients.

        2. How does the specific function work:
           Iterates over connections, attempts send_json(), and prunes failed sockets.

        3. Concepts used in the function:
           Async fan-out, dead-connection pruning.

        4. Places where this function is imported and used:
           Invoked when ticks or candles are emitted.

        5. Final output of the function, before and after:
           Before: Message pending delivery. After: Delivered to all healthy connected clients.
        """
        dead: Set[WebSocket] = set()
        for conn in list(self.active_connections):
            try:
                await conn.send_json(message)
            except Exception:
                dead.add(conn)

        for conn in dead:
            self.disconnect(conn)


def create_daemon_app(
    supervisor: Optional[LiveDaemonSupervisor] = None,
) -> FastAPI:
    """
    1. The use of function:
       Constructs and configures the FastAPI loopback administrative application for the Live Daemon.

    2. How does the specific function work:
       - Instantiates default PaperBroker, FrameBus, StreamingCandleBuilder, and LiveDaemonSupervisor if not passed.
       - Sets up lifespan context to handle sub-second startup (< 300ms) and clean shutdown.
       - Registers REST route controllers: /control/status, /control/start, /control/stop, /control/kill-switch.
       - Registers WebSocket endpoint /ws/stream.
       - Returns configured FastAPI application.

    3. Concepts used in the function:
       Application factory pattern, ASGI lifespan hooks, RESTful API design.

    4. Places where this function is imported and used:
       Imported by main execution entrypoint and integration test suites.

    5. Final output of the function, before and after:
       Before: Unconfigured environment. After: Fully configured FastAPI application.
    """
    if supervisor is None:
        frame_bus = FrameBus()
        broker = PaperBroker(db_path="Data/paper/qv_paper.db")
        candle_builder = StreamingCandleBuilder()
        daemon_supervisor = LiveDaemonSupervisor(
            broker=broker,
            frame_bus=frame_bus,
            candle_builder=candle_builder,
            allocation_mode=AccountAllocationMode.ISOLATED,
        )
    else:
        daemon_supervisor = supervisor

    stream_manager = DaemonStreamManager()

    # Configure 24/7 Replay Player if requested via environment
    replay_mode = os.environ.get("QUANTVIEW_REPLAY", "").lower() in ("1", "true", "yes")
    replay_speed_str = os.environ.get("QUANTVIEW_REPLAY_SPEED", "2x").lower()
    replay_player: Optional[ReplayPlayer] = None

    if replay_mode:
        speed_map = {
            "1x": PlaybackSpeed.REALTIME,
            "2x": PlaybackSpeed.FAST_2X,
            "5x": PlaybackSpeed.FAST_5X,
            "asap": PlaybackSpeed.ASAP,
        }
        speed = speed_map.get(replay_speed_str, PlaybackSpeed.FAST_2X)
        trade_date = os.environ.get("QUANTVIEW_REPLAY_DATE", None)
        replay_player = ReplayPlayer(
            bus=daemon_supervisor.frame_bus,
            trade_date=trade_date,
            speed=speed,
        )

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
        """
        1. The use of function:
           Async context manager managing supervisor startup, optional replay player, and shutdown lifecycle.

        2. How does the specific function work:
           - Awaits supervisor.startup().
           - Starts replay_player if configured.
           - Yields control to FastAPI.
           - On app termination, stops replay_player and awaits supervisor.shutdown().

        3. Concepts used in the function:
           ASGI lifespan protocol, async resource management, 24/7 background playback.

        4. Places where this function is imported and used:
           Passed as lifespan argument to FastAPI constructor.

        5. Final output of the function, before and after:
           Before: App starting. After: App shut down cleanly.
        """
        await daemon_supervisor.startup()
        if replay_player is not None:
            replay_player.start()
            logger.info("24/7 Historical Tick ReplayPlayer started (speed: %s)", replay_player.speed)
        yield
        if replay_player is not None:
            replay_player.stop()
        await daemon_supervisor.shutdown()

    app_instance = FastAPI(
        title="QuantView Live Daemon Loopback Admin",
        description="Internal loopback control plane and real-time streaming bridge for QuantView Live Daemon.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Attach supervisor to app state for handler access
    app_instance.state.supervisor = daemon_supervisor
    app_instance.state.stream_manager = stream_manager
    app_instance.state.replay_player = replay_player

    @app_instance.get("/control/status", tags=["control"])
    async def get_daemon_status() -> Dict[str, Any]:
        """
        1. The use of function:
           Retrieves consolidated operational health, uptime, deployments, memory RSS, and FrameBus stats.

        2. How does the specific function work:
           Calls daemon_supervisor.get_status() and returns dictionary response.

        3. Concepts used in the function:
           Operational health telemetry, process state reporting.

        4. Places where this function is imported and used:
           Handled under GET /control/status.

        5. Final output of the function, before and after:
           Before: Telemetry request. After: Complete system status payload.
        """
        return daemon_supervisor.get_status()

    @app_instance.post("/control/start", tags=["control"])
    async def start_deployment_endpoint(req: StartDeploymentRequest) -> Dict[str, Any]:
        """
        1. The use of function:
           Registers and starts a strategy deployment in the Live Daemon supervisor pool.

        2. How does the specific function work:
           - Derives unique deployment_id if not provided.
           - Registers deployment with supervisor if not already registered.
           - Invokes supervisor.start_deployment().
           - Returns confirmation payload with deployment telemetry.

        3. Concepts used in the function:
           Strategy lifecycle orchestration, dynamic deployment provisioning.

        4. Places where this function is imported and used:
           Handled under POST /control/start.

        5. Final output of the function, before and after:
           Before: Unstarted strategy. After: Running deployment with status RUNNING.
        """
        dep_id = req.deployment_id or f"DEP-{req.strategy_id.upper()}-{uuid.uuid4().hex[:4].upper()}"

        host: Optional[StrategyDeploymentHost] = daemon_supervisor.get_deployment(dep_id)
        if host is None:
            try:
                host = daemon_supervisor.register_deployment(
                    deployment_id=dep_id,
                    strategy=req.strategy_id,
                    account_id=req.account_id,
                    params=req.params,
                    mode=req.mode,
                    instrument_key=req.instrument_key,
                    timeout_sec=req.timeout_sec or 0.5,
                )
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Failed to register deployment: {exc}")

        try:
            started_host = daemon_supervisor.start_deployment(dep_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to start deployment: {exc}")

        return {
            "status": "started",
            "deployment": started_host.to_dict(),
        }

    @app_instance.post("/control/stop", tags=["control"])
    async def stop_deployment_endpoint(req: StopDeploymentRequest) -> Dict[str, Any]:
        """
        1. The use of function:
           Stops an active strategy deployment and drains its working orders.

        2. How does the specific function work:
           - Queries supervisor for deployment_id.
           - Invokes supervisor.stop_deployment().
           - Returns confirmation payload with updated host status (STOPPED).

        3. Concepts used in the function:
           Graceful strategy shutdown, order drainage.

        4. Places where this function is imported and used:
           Handled under POST /control/stop.

        5. Final output of the function, before and after:
           Before: Active deployment. After: Stopped deployment.
        """
        try:
            stopped_host = daemon_supervisor.stop_deployment(req.deployment_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to stop deployment: {exc}")

        return {
            "status": "stopped",
            "deployment": stopped_host.to_dict(),
        }

    @app_instance.post("/control/kill-switch", tags=["control"])
    async def trigger_kill_switch_endpoint(req: KillSwitchRequest) -> Dict[str, Any]:
        """
        1. The use of function:
           Triggers the emergency fail-closed kill switch (RK-01), rejecting future orders and canceling pending orders.

        2. How does the specific function work:
           - Invokes daemon_supervisor.trigger_kill_switch(reason).
           - Returns audit summary of canceled orders and activation timestamp.

        3. Concepts used in the function:
           Emergency circuit breaker, fail-closed order rejection.

        4. Places where this function is imported and used:
           Handled under POST /control/kill-switch.

        5. Final output of the function, before and after:
           Before: Kill switch inactive. After: Kill switch active, audit payload returned.
        """
        reason = req.reason or "Operator emergency kill-switch"
        result = daemon_supervisor.trigger_kill_switch(reason=reason)
        return result

    @app_instance.websocket("/ws/stream")
    async def websocket_stream_endpoint(websocket: WebSocket) -> None:
        """
        1. The use of function:
           WebSocket streaming endpoint publishing live TickFrame and StreamingCandle events.

        2. How does the specific function work:
           - Accepts WebSocket connection.
           - Subscribes an isolated queue to FrameBus.
           - Continuously pops frames and dispatches JSON payload {"type": "tick", "data": frame.to_dict()}.
           - Handles disconnect gracefully and unsubscribes queue from FrameBus.

        3. Concepts used in the function:
           High-speed WebSocket streaming, pub/sub subscriber bridge, decoupled queuing.

        4. Places where this function is imported and used:
           Handled under WebSocket /ws/stream.

        5. Final output of the function, before and after:
           Before: Unconnected socket. After: High-speed streaming conduit for tick and candle frames.
        """
        await stream_manager.connect(websocket)
        queue = daemon_supervisor.frame_bus.subscribe()

        try:
            while True:
                try:
                    frame: TickFrame = await asyncio.wait_for(queue.get(), timeout=1.0)
                    payload = {
                        "type": "tick",
                        "data": frame.to_dict(),
                    }
                    await websocket.send_json(payload)
                    queue.task_done()
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat pulse check
                    pass
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.debug(f"WebSocket client stream error: {exc}")
        finally:
            daemon_supervisor.frame_bus.unsubscribe(queue)
            stream_manager.disconnect(websocket)

    return app_instance


app = create_daemon_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.live_daemon.main:app",
        host="127.0.0.1",
        port=8001,
        reload=False,
        log_level="info",
    )
