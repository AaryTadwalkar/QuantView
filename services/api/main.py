"""
1. What this file does:
   Entry point and application factory for the QuantView FastAPI Gateway service
   (Milestones M6-01, M6-02, M6-03, M6-03b, M6-04, M6-05, M6-06, M6-07, M6-08, M6-09, M6-11, M6-13, M6-14, M6-15, M6-16, M6-18, and Release Gate G4).

2. Overall design:
   Initializes the FastAPI application instance:
     - Configures Cross-Origin Resource Sharing (CORS) restricted to local loopback origins.
     - Registers modular route controllers: health, market candles, option chains/candles, backtest runner,
       paper trading simulation, technical indicators, and chart drawings.
     - Mounts the web frontend directory (apps/web) as StaticFiles at root ("/") with html=True fallback.
     - Exposes the global application instance and execution hooks for uvicorn.

3. Elements in the file:
   - create_app: Application factory constructing and configuring the FastAPI instance.
   - app: Global FastAPI instance used by ASGI servers.

4. Final output of the file:
   - Configured FastAPI application instance ready for production serving or testing.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from services.api.config import ApiConfig, get_api_config
from services.api.routers import backtest, drawings, health, indicators, market, options, paper

logger = logging.getLogger(__name__)


class MarketStreamManager:
    """
    1. The use of class:
       Coordinates active WebSocket subscriber connections for real-time market ticks and option updates.

    2. What the class contains:
       - active_connections: Set of connected client WebSocket instances.
       - connect(): Registers new WebSocket connection.
       - disconnect(): Removes disconnected WebSocket client.
       - broadcast(): Distributes JSON message to all connected clients.

    3. Technologies used and why:
       FastAPI WebSockets and asyncio for asynchronous low-latency bidirectional market streaming.

    4. Key design and overall design of the class:
       In-memory event hub bridging external collectors/market tickers to web workstation clients.
    """

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accepts and registers incoming client WebSocket."""
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Removes closed WebSocket from active subscribers."""
        self.active_connections.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Dispatches JSON payload to all active client connections."""
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.disconnect(conn)


market_stream_manager = MarketStreamManager()


def create_app(config: Optional[ApiConfig] = None) -> FastAPI:
    """
    1. The use of function:
       Constructs and configures the QuantView FastAPI application gateway.

    2. How does the specific function work:
       - Obtains the ApiConfig (from argument or singleton).
       - Instantiates FastAPI with OpenAPI metadata.
       - Attaches CORSMiddleware configured with authorized origins.
       - Includes /api/v1/health, /api/v1/market, /api/v1/options, /api/v1/backtest,
         /api/v1/paper, /api/v1/indicators, and /api/v1/charts/drawings routers.
       - Resolves static web assets directory and mounts it at '/' if available on disk.

    3. Concepts used in the function:
       Application factory pattern, ASGI middleware stack, route registration, static file serving.

    4. Places where this function is imported and used:
       Imported by services.api.main for module global, and by test suites.

    5. Final output of the function, before and after:
       Before: None or raw ApiConfig. After: Fully configured FastAPI application.
    """
    api_config = config or get_api_config()

    application = FastAPI(
        title="QuantView Gateway",
        description="Deterministic algorithmic trading, backtesting, and paper engine gateway for Indian index options.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
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
           Accepts client connection, registers with market_stream_manager, listens for incoming tick payloads
           from external collectors or client publishers, and broadcasts them across all connected clients.

        3. Concepts used in the function:
           WebSocket protocol, real-time message dispatch, publish-subscribe event routing.

        4. Places where this function is imported and used:
           Mounted directly on FastAPI application gateway at /ws/market.

        5. Final output of the function, before and after:
           Before: Unconnected socket. After: Bidirectional streaming conduit for real-time market data.
        """
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
