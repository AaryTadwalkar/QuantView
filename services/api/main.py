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

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from services.api.config import ApiConfig, get_api_config
from services.api.routers import backtest, drawings, health, indicators, market, options, paper


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
