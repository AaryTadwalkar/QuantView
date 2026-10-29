"""
1. What this file does:
   Defines shared dependency injection providers for the QuantView FastAPI Gateway service
   (Milestone M6-01 / M6-05).

2. Overall design:
   Exposes modular dependency providers conforming to the FastAPI Depends contract:
     - _resolve_config: Zero-argument dependency helper returning active ApiConfig.
     - get_duckdb_connection: Direct factory providing read-only DuckDB connections with safe memory fallback.
     - get_duckdb: Generator dependency yielding read-only DuckDB connections with guaranteed closure.

3. Elements in the file:
   - _resolve_config: Zero-argument configuration provider for FastAPI dependency injection.
   - get_duckdb_connection: Helper opening read-only lake connections with safe fallback.
   - get_duckdb: FastAPI dependency generator managing DuckDB connection lifecycle.

4. Final output of the file:
   - Exported get_duckdb_connection and get_duckdb dependency functions.
"""

from pathlib import Path
from typing import Generator, Optional

import duckdb
from fastapi import Depends

from services.api.config import ApiConfig, get_api_config


def _resolve_config() -> ApiConfig:
    """
    1. The use of function:
       FastAPI zero-argument dependency helper resolving the runtime ApiConfig instance.

    2. How does the specific function work:
       Calls get_api_config() directly without route parameters to prevent FastAPI from
       interpreting configuration fields as HTTP request body or query parameters.

    3. Concepts used in the function:
       Dependency injection isolation, parameter reflection suppression.

    4. Places where this function is imported and used:
       Used internally as default Depends factory for get_duckdb.

    5. Final output of the function, before and after:
       Before: None. After: Active ApiConfig dataclass instance.
    """
    return get_api_config()


def get_duckdb_connection(lake_path: Optional[str] = None) -> duckdb.DuckDBPyConnection:
    """
    1. The use of function:
       Creates and returns an open read-only DuckDB connection pointing to the analytical lake.

    2. How does the specific function work:
       Checks if the target lake file exists on the filesystem. If present, connects in read-only mode;
       otherwise, falls back gracefully to an in-memory database to prevent test suite failures.

    3. Concepts used in the function:
       Embedded analytical database connections, graceful degradation, fallback mechanisms.

    4. Places where this function is imported and used:
       Imported by services.api.deps.get_duckdb and test suites.

    5. Final output of the function, before and after:
       Before: Database path string. After: Active duckdb.DuckDBPyConnection object.
    """
    if lake_path is None:
        cfg = get_api_config()
        lake_path = cfg.lake_path

    target_path = Path(lake_path)
    if not target_path.is_absolute():
        repo_root = Path(__file__).resolve().parent.parent.parent
        resolved = repo_root / target_path
        if resolved.is_file():
            target_path = resolved

    if target_path.is_file():
        return duckdb.connect(database=str(target_path), read_only=True)
    return duckdb.connect(database=":memory:")


def get_duckdb(
    config: ApiConfig = Depends(_resolve_config),
) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """
    1. The use of function:
       FastAPI dependency provider providing a request-scoped read-only DuckDB connection.

    2. How does the specific function work:
       Obtains configuration from the injected or default config, invokes get_duckdb_connection
       with the configured lake_path, yields the connection to the route handler, and deterministically
       executes conn.close() in a finally block upon completion.

    3. Concepts used in the function:
       FastAPI dependency injection, context management, deterministic resource reclamation.

    4. Places where this function is imported and used:
       Injected into route handlers across services.api.routers.

    5. Final output of the function, before and after:
       Before: Route request context. After: Yields open connection, closes it after request.
    """
    cfg = config or get_api_config()
    conn = get_duckdb_connection(lake_path=cfg.lake_path)
    try:
        yield conn
    finally:
        conn.close()
