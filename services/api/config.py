"""
1. What this file does:
   Defines the central runtime configuration container and loader for the QuantView
   FastAPI Gateway (Milestone M6-01 / M6-05).

2. Overall design:
   Provides strongly-typed configuration for the REST API gateway, including host,
   port, database lake path, static web assets directory, and CORS origin policies.
   Supports zero-configuration local workstation defaults with environment variable overrides.

3. Elements in the file:
   - ApiConfig: Dataclass encapsulating gateway network, storage, and web mounting settings.
   - get_api_config: Factory and singleton provider returning the active ApiConfig instance.

4. Final output of the file:
   - Exported ApiConfig class and get_api_config factory function.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ApiConfig:
    """
    1. The use of class:
       Encapsulates all runtime configuration parameters for the QuantView FastAPI gateway service.

    2. What the class contains:
       - host: Loopback or network host address for the HTTP server.
       - port: Port integer for listening to HTTP and WebSocket requests.
       - lake_path: Filesystem path to the DuckDB analytical data lake file.
       - web_static_dir: Filesystem path to the static web frontend assets directory.
       - cors_origins: List of allowed origins for Cross-Origin Resource Sharing.

    3. Technologies used and why:
       Python dataclasses for lightweight, typed, and mutable configuration with default factory support.

    4. Key design and overall design of the class:
       Maintains strict defaults for local workstation security (loopback 127.0.0.1 and explicit localhost CORS).
    """

    host: str = "127.0.0.1"
    port: int = 8000
    lake_path: str = "Data/lake/quantview.duckdb"
    web_static_dir: str = "apps/web"
    cors_origins: List[str] = field(
        default_factory=lambda: ["http://localhost:8000", "http://127.0.0.1:8000"]
    )


_global_api_config: Optional[ApiConfig] = None


def get_api_config(
    host: Optional[str] = None,
    port: Optional[int] = None,
    lake_path: Optional[str] = None,
    web_static_dir: Optional[str] = None,
    cors_origins: Optional[List[str]] = None,
    reset: bool = False,
) -> ApiConfig:
    """
    1. The use of function:
       Retrieves or initializes the global ApiConfig singleton instance.

    2. How does the specific function work:
       Checks module-level cache; if unset or reset=True, constructs an ApiConfig instance
       evaluating environment variables with fallback to canonical defaults.

    3. Concepts used in the function:
       Singleton pattern, environment variable resolution, default configuration fallbacks.

    4. Places where this function is imported and used:
       Imported by services.api.deps, services.api.main, and test suites.

    5. Final output of the function, before and after:
       Before: None or existing config. After: Fully resolved, strongly-typed ApiConfig instance.
    """
    global _global_api_config

    if _global_api_config is not None and not reset:
        return _global_api_config

    env_host = os.getenv("QV_API_HOST", "127.0.0.1")
    env_port_str = os.getenv("QV_API_PORT", "8000")
    try:
        env_port = int(env_port_str)
    except ValueError:
        env_port = 8000

    env_lake = os.getenv("QV_LAKE_PATH", "Data/lake/quantview.duckdb")
    env_web = os.getenv("QV_WEB_STATIC_DIR", "apps/web")
    env_cors = os.getenv("QV_CORS_ORIGINS")

    resolved_cors: List[str]
    if cors_origins is not None:
        resolved_cors = cors_origins
    elif env_cors:
        resolved_cors = [origin.strip() for origin in env_cors.split(",") if origin.strip()]
    else:
        resolved_cors = ["http://localhost:8000", "http://127.0.0.1:8000"]

    config = ApiConfig(
        host=host or env_host,
        port=port if port is not None else env_port,
        lake_path=lake_path or env_lake,
        web_static_dir=web_static_dir or env_web,
        cors_origins=resolved_cors,
    )

    _global_api_config = config
    return config
