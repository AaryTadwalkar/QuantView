"""
1. What this file does:
   Entry point and application factory for the QuantView FastAPI Gateway service
   (Milestones M6-01 to M6-18, M7-08, and Release Gates G4/G5).
   Provides REST API endpoints and the real-time WebSocket market bridge (/ws/market)
   connecting to Live Daemon (ws://127.0.0.1:8001/ws/stream) or local FrameBus,
   broadcasting ticks and candle events to web clients at 60 FPS.

2. Overall design:
   Initializes the FastAPI application instance:
     - Configures Cross-Origin Resource Sharing (CORS) restricted to local loopback origins.
     - Registers modular route controllers: health, market candles, option chains/candles, backtest runner,
       paper trading simulation, technical indicators, chart drawings, and live daemon proxy.
     - Coordinates MarketStreamManager for 60 FPS WebSocket fan-out from Live Daemon or FrameBus to browser clients.
     - Mounts the web frontend directory (apps/web) as StaticFiles at root ("/") with html=True fallback.
     - Exposes the global application instance and execution hooks for uvicorn.

3. Elements in the file:
   - MarketStreamManager: 60 FPS WebSocket broadcast hub bridging Live Daemon and FrameBus to web clients.
   - market_stream_manager: Shared singleton MarketStreamManager instance.
   - create_app: Application factory constructing and configuring the FastAPI instance.
   - app: Global FastAPI instance used by ASGI servers.

4. Final output of the file:
   - Configured FastAPI application instance ready for production serving or testing.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional, Set

import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from services.api.config import ApiConfig, get_api_config
from services.api.routers import backtest, daemon, drawings, health, indicators, market, options, paper

logger = logging.getLogger(__name__)


class MarketStreamManager:
    """
    1. The use of class:
       Coordinates active WebSocket subscriber connections for real-time market ticks,
       subscribes to Live Daemon (ws://127.0.0.1:8001/ws/stream) or local FrameBus,
       and broadcasts streaming tick frames and finalized candle events at 60 FPS.

    2. What the class contains:
       - active_connections: Set of connected client WebSocket instances.
       - daemon_stream_url: Upstream Live Daemon WebSocket URL (ws://127.0.0.1:8001/ws/stream).
       - frame_bus: Optional local FrameBus reference for in-process streaming.
       - _queue: Paced broadcasting queue enforcing 60 FPS maximum throughput.
       - connect(): Registers new WebSocket client.
       - disconnect(): Removes closed WebSocket client.
       - broadcast(): Enqueues payload for 60 FPS distribution.
       - start(): Launches background upstream consumer and 60 FPS pacer tasks.
       - stop(): Cancels background streaming tasks and cleans up resources.
       - attach_frame_bus(): Hooks a local FrameBus instance for in-process pub/sub fan-out.

    3. Technologies used and why:
       FastAPI WebSockets, asyncio, and websockets library for low-latency non-blocking streaming.

    4. Key design and overall design of the class:
       In-memory event hub bridging external Live Daemon or local FrameBus to web workstation clients.
    """

    def __init__(self, daemon_stream_url: str = "ws://127.0.0.1:8001/ws/stream") -> None:
        """
        1. The use of function:
           Initializes MarketStreamManager with empty connections and default configuration.

        2. How does the specific function work:
           Sets up active_connections set, specifies upstream daemon URL, and initializes task pointers.

        3. Concepts used in the function:
           Object initialization, stream configuration.

        4. Places where this function is imported and used:
           Instantiated at module level in services.api.main.

        5. Final output of the function, before and after:
           Before: Uninitialized memory. After: Ready MarketStreamManager instance.
        """
        self.active_connections: Set[WebSocket] = set()
        self.daemon_stream_url: str = daemon_stream_url
        self.frame_bus: Any = None
        self._running: bool = False
        self._bridge_task: Optional[asyncio.Task] = None
        self._framebus_task: Optional[asyncio.Task] = None
        self._pacer_task: Optional[asyncio.Task] = None
        self._queue: Optional[asyncio.Queue[Dict[str, Any]]] = None

    def start(self) -> None:
        """
        1. The use of function:
           Starts background upstream WebSocket bridge and 60 FPS pacer tasks.

        2. How does the specific function work:
           - Sets _running to True.
           - Allocates asyncio.Queue with maxsize 1000.
           - Spawns _pacer_loop and _daemon_bridge_loop as background asyncio tasks.

        3. Concepts used in the function:
           Background task orchestration, non-blocking asynchronous event loop.

        4. Places where this function is imported and used:
           Called in FastAPI lifespan startup and upon client WebSocket connection.

        5. Final output of the function, before and after:
           Before: Idle stream manager. After: Active streaming bridge and pacer tasks running.
        """
        if self._running:
            return
        self._running = True
        self._queue = asyncio.Queue(maxsize=1000)
        try:
            loop = asyncio.get_running_loop()
            self._pacer_task = loop.create_task(self._pacer_loop())
            self._bridge_task = loop.create_task(self._daemon_bridge_loop())
            if self.frame_bus is not None:
                self._framebus_task = loop.create_task(self._framebus_loop())
        except RuntimeError:
            pass

    async def stop(self) -> None:
        """
        1. The use of function:
           Stops all background bridge and pacer tasks and cleans up resources.

        2. How does the specific function work:
           - Sets _running to False.
           - Cancels active background tasks and waits for completion.
           - Clears connection set.

        3. Concepts used in the function:
           Graceful shutdown, task cancellation.

        4. Places where this function is imported and used:
           Called during FastAPI lifespan shutdown.

        5. Final output of the function, before and after:
           Before: Running stream manager. After: Cleanly stopped stream manager.
        """
        self._running = False
        for task in (self._pacer_task, self._bridge_task, self._framebus_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._pacer_task = None
        self._bridge_task = None
        self._framebus_task = None
        self._queue = None

    def attach_frame_bus(self, frame_bus: Any) -> None:
        """
        1. The use of function:
           Attaches a local FrameBus instance for in-process streaming fan-out.

        2. How does the specific function work:
           Stores frame_bus reference and launches framebus subscriber loop if manager is running.

        3. Concepts used in the function:
           Dependency injection, pub/sub bridge.

        4. Places where this function is imported and used:
           Called by test suites or in-process daemon configurations.

        5. Final output of the function, before and after:
           Before: No local FrameBus hook. After: FrameBus attached and active subscriber loop running.
        """
        self.frame_bus = frame_bus
        if self._running and self._framebus_task is None:
            try:
                loop = asyncio.get_running_loop()
                self._framebus_task = loop.create_task(self._framebus_loop())
            except RuntimeError:
                pass

    async def connect(self, websocket: WebSocket) -> None:
        """
        1. The use of function:
           Accepts incoming client WebSocket and registers in active subscriber pool.

        2. How does the specific function work:
           Calls await websocket.accept() and adds websocket to active_connections set.

        3. Concepts used in the function:
           WebSocket handshake, connection registration.

        4. Places where this function is imported and used:
           Called in /ws/market endpoint handler.

        5. Final output of the function, before and after:
           Before: Unregistered socket. After: Accepted and registered in active subscribers.
        """
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """
        1. The use of function:
           Unregisters a closed WebSocket client from active subscribers.

        2. How does the specific function work:
           Removes websocket from active_connections set.

        3. Concepts used in the function:
           Subscriber cleanup.

        4. Places where this function is imported and used:
           Called in /ws/market on disconnect or error.

        5. Final output of the function, before and after:
           Before: Registered client. After: Removed client.
        """
        self.active_connections.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """
        1. The use of function:
           Enqueues a JSON payload for paced distribution to all connected clients.

        2. How does the specific function work:
           - Returns immediately if no clients are connected.
           - If queue is available and running, enqueues message (dropping oldest if full to avoid latency lag).
           - Otherwise directly invokes _send_to_active.

        3. Concepts used in the function:
           Asynchronous buffering, drop-oldest backpressure control.

        4. Places where this function is imported and used:
           Called by bridge loops, POST /api/v1/market/tick, and incoming WebSocket handler.

        5. Final output of the function, before and after:
           Before: Payload ready. After: Enqueued for 60 FPS delivery.
        """
        if not self.active_connections:
            return

        if self._queue is not None and self._running:
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except Exception:
                    pass
            try:
                self._queue.put_nowait(message)
                return
            except Exception:
                pass

        await self._send_to_active(message)

    async def _send_to_active(self, message: Dict[str, Any]) -> None:
        """
        1. The use of function:
           Internal dispatch helper sending a JSON message to all active WebSocket clients.

        2. How does the specific function work:
           Iterates over copy of active_connections, calls send_json(), and prunes dead sockets.

        3. Concepts used in the function:
           Fan-out broadcasting, stale connection cleanup.

        4. Places where this function is imported and used:
           Called by broadcast and _pacer_loop.

        5. Final output of the function, before and after:
           Before: Message pending delivery. After: Dispatched to all healthy connections.
        """
        dead: Set[WebSocket] = set()
        for conn in list(self.active_connections):
            try:
                await conn.send_json(message)
            except Exception:
                dead.add(conn)
        for conn in dead:
            self.disconnect(conn)

    async def _pacer_loop(self) -> None:
        """
        1. The use of function:
           Background loop enforcing 60 FPS broadcast ceiling (~16.6ms intervals) to prevent client flooding.

        2. How does the specific function work:
           - Continuously pops messages from _queue.
           - Sends message to active clients via _send_to_active().
           - Awaits 16.6ms sleep (0.016s) to pace output frame rate.

        3. Concepts used in the function:
           Frame pacing, 60 FPS rate limiting, asynchronous sleep.

        4. Places where this function is imported and used:
           Launched by start() as background task.

        5. Final output of the function, before and after:
           Before: Unpaced stream. After: Smooth 60 FPS delivered stream.
        """
        while self._running:
            if self._queue is None:
                break
            try:
                message = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                await self._send_to_active(message)
                self._queue.task_done()
                await asyncio.sleep(0.016)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Pacer loop error: %s", exc)

    async def _daemon_bridge_loop(self) -> None:
        """
        1. The use of function:
           Background consumer subscribing to Live Daemon's internal data stream (ws://127.0.0.1:8001/ws/stream).

        2. How does the specific function work:
           - Sleeps while active_connections is empty.
           - Connects to daemon_stream_url using websockets.connect().
           - Receives raw JSON frame messages and forwards them via broadcast().
           - Reconnects automatically on failure with backoff sleep.

        3. Concepts used in the function:
           Upstream WebSocket bridge, automatic reconnection with backoff.

        4. Places where this function is imported and used:
           Launched by start() as background task.

        5. Final output of the function, before and after:
           Before: Isolated gateway. After: Gateway bridged to Live Daemon market stream.
        """
        while self._running:
            if not self.active_connections:
                await asyncio.sleep(1.0)
                continue
            try:
                async with websockets.connect(self.daemon_stream_url) as ws:
                    logger.info("Connected to Live Daemon stream bridge at %s", self.daemon_stream_url)
                    while self._running and len(self.active_connections) > 0:
                        raw = await ws.recv()
                        try:
                            payload = json.loads(raw)
                            await self.broadcast(payload)
                        except Exception:
                            pass
            except asyncio.CancelledError:
                break
            except (ConnectionRefusedError, OSError, Exception) as exc:
                logger.debug("Live Daemon stream unavailable at %s (%s); retrying in 2s...", self.daemon_stream_url, exc)
                await asyncio.sleep(2.0)

    async def _framebus_loop(self) -> None:
        """
        1. The use of function:
           Background consumer reading from a local FrameBus instance for in-process tick streaming.

        2. How does the specific function work:
           - Subscribes queue to frame_bus.
           - Awaits incoming TickFrame objects.
           - Forwards payload {"type": "tick", "data": frame.to_dict()} via broadcast().

        3. Concepts used in the function:
           In-process ring buffer subscription, pub/sub forwarding.

        4. Places where this function is imported and used:
           Launched by start() or attach_frame_bus().

        5. Final output of the function, before and after:
           Before: Unconsumed FrameBus. After: FrameBus frames broadcasted to active clients.
        """
        if self.frame_bus is None:
            return
        queue = self.frame_bus.subscribe()
        try:
            while self._running:
                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=1.0)
                    payload = {"type": "tick", "data": frame.to_dict()}
                    await self.broadcast(payload)
                    queue.task_done()
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            if self.frame_bus:
                self.frame_bus.unsubscribe(queue)


market_stream_manager = MarketStreamManager()


def create_app(config: Optional[ApiConfig] = None) -> FastAPI:
    """
    1. The use of function:
       Constructs and configures the QuantView FastAPI application gateway.

    2. How does the specific function work:
       - Obtains the ApiConfig (from argument or singleton).
       - Instantiates FastAPI with OpenAPI metadata and lifespan management.
       - Attaches CORSMiddleware configured with authorized origins.
       - Includes /api/v1/health, /api/v1/market, /api/v1/options, /api/v1/backtest,
         /api/v1/paper, /api/v1/indicators, /api/v1/charts/drawings, and /api/v1/daemon routers.
       - Configures WebSocket /ws/market and POST /api/v1/market/tick endpoints.
       - Resolves static web assets directory and mounts it at '/' if available on disk.

    3. Concepts used in the function:
       Application factory pattern, ASGI middleware stack, route registration, static file serving.

    4. Places where this function is imported and used:
       Imported by services.api.main for module global, and by test suites.

    5. Final output of the function, before and after:
       Before: None or raw ApiConfig. After: Fully configured FastAPI application.
    """
    api_config = config or get_api_config()

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncGenerator[None, None]:
        """
        1. The use of function:
           Lifespan context manager starting and stopping MarketStreamManager.

        2. How does the specific function work:
           Invokes market_stream_manager.start() on startup and market_stream_manager.stop() on shutdown.

        3. Concepts used in the function:
           FastAPI lifespan protocol, async resource lifecycle management.

        4. Places where this function is imported and used:
           Configured as lifespan on FastAPI application instance.

        5. Final output of the function, before and after:
           Before: Unmanaged lifecycle. After: Managed startup and graceful shutdown.
        """
        market_stream_manager.start()
        yield
        await market_stream_manager.stop()

    application = FastAPI(
        title="QuantView Gateway",
        description="Deterministic algorithmic trading, backtesting, and paper engine gateway for Indian index options.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=api_config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router)
    application.include_router(market.router)
    application.include_router(options.router)
    application.include_router(backtest.router)
    application.include_router(paper.router)
    application.include_router(indicators.router)
    application.include_router(drawings.router)
    application.include_router(daemon.router)

    # Public convenience aliases for Section 6.1 and 6.2 endpoints
    application.add_api_route(
        "/api/v1/screener",
        market.get_market_screener,
        methods=["GET"],
        tags=["market"],
        summary="Indian Market Derivatives Screener (Alias)",
    )
    application.add_api_route(
        "/api/v1/heatmap",
        backtest.get_strategy_heatmap,
        methods=["GET"],
        tags=["backtest"],
        summary="Quantitative Strategy Sensitivity Heatmap (Alias)",
    )

    @application.websocket("/ws/market")
    async def websocket_market_endpoint(websocket: WebSocket) -> None:
        """
        1. The use of function:
           WebSocket endpoint serving real-time market ticks, live candle streams, and option chain updates.

        2. How does the specific function work:
           Ensures market_stream_manager is started, accepts client connection, listens for incoming messages,
           and broadcasts payloads across all connected clients at 60 FPS.

        3. Concepts used in the function:
           WebSocket protocol, real-time message dispatch, publish-subscribe event routing.

        4. Places where this function is imported and used:
           Mounted directly on FastAPI application gateway at /ws/market.

        5. Final output of the function, before and after:
           Before: Unconnected socket. After: Bidirectional streaming conduit for real-time market data.
        """
        if not market_stream_manager._running:
            market_stream_manager.start()
        await market_stream_manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                    await market_stream_manager.broadcast(payload)
                except Exception:
                    pass
        except WebSocketDisconnect:
            market_stream_manager.disconnect(websocket)
        except Exception:
            market_stream_manager.disconnect(websocket)

    @application.post("/api/v1/market/tick", tags=["market"])
    async def broadcast_market_tick(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        1. The use of function:
           REST API endpoint allowing external collectors to push real-time market ticks into the WebSocket stream.

        2. How does the specific function work:
           Receives tick payload JSON and dispatches it asynchronously via market_stream_manager.broadcast().

        3. Concepts used in the function:
           Webhook ingestion, cross-protocol event bridging (HTTP -> WebSocket).

        4. Places where this function is imported and used:
           Mounted under POST /api/v1/market/tick.

        5. Final output of the function, before and after:
           Before: Raw incoming tick. After: Broadcasted message and subscriber confirmation response.
        """
        await market_stream_manager.broadcast(payload)
        return {"status": "broadcasted", "subscribers": len(market_stream_manager.active_connections)}

    web_path = Path(api_config.web_static_dir)
    if not web_path.is_absolute():
        repo_root = Path(__file__).resolve().parent.parent.parent
        candidate = repo_root / api_config.web_static_dir
        if candidate.is_dir():
            web_path = candidate

    if web_path.is_dir():
        application.mount(
            "/",
            StaticFiles(directory=str(web_path), html=True),
            name="web_static",
        )

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    server_cfg = get_api_config()
    uvicorn.run(
        "services.api.main:app",
        host=server_cfg.host,
        port=server_cfg.port,
        reload=server_cfg.reload,
        log_level=server_cfg.log_level.lower(),
    )



app = create_app()


if __name__ == "__main__":
    import uvicorn

    server_cfg = get_api_config()
    uvicorn.run(
        "services.api.main:app",
        host=server_cfg.host,
        port=server_cfg.port,
        reload=server_cfg.reload,
        log_level=server_cfg.log_level.lower(),
    )
