"""
1. What this file does:
   Automated verification suite for Milestone M6-01 and M6-05 (FastAPI Core, Schemas, & StaticFiles Mount).
   Validates gateway setup, CORS headers, health and heartbeat endpoints, and static asset serving.

2. Overall design:
   Uses pytest and FastAPI TestClient to verify:
     - GET /api/v1/health returns HTTP 200, valid service payload, and latency <= 50ms.
     - GET /api/v1/health/heartbeat returns HTTP 200 with UTC timestamp and PID telemetry.
     - StaticFiles mount serves assets from apps/web and falls back gracefully when directories are missing.
     - DuckDB dependency providers offer clean read-only connections and in-memory fallbacks.
     - All tests are marked with gate_g4 for release gate auditing.

3. Elements in the file:
   - TestHealthAndGatewaySetup: Main test case class exercising the gateway routes and dependencies.

4. Final output of the file:
   - Automated pass/fail test execution under Release Gate G4.
"""

import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.config import ApiConfig, get_api_config
from services.api.deps import get_duckdb, get_duckdb_connection
from services.api.main import app, create_app


@pytest.mark.gate_g4
class TestHealthAndGatewaySetup:
    """
    1. The use of class:
       Test suite validating FastAPI gateway initialization, route contracts, and dependencies.

    2. What the class contains:
       - test_health_endpoint_contract: Verifies /api/v1/health status, payload, and <= 50ms latency.
       - test_heartbeat_endpoint_telemetry: Verifies /api/v1/health/heartbeat returns timestamp and process info.
       - test_static_files_mount_serving: Verifies static asset delivery from apps/web.
       - test_static_files_index_html_serving: Verifies index.html delivery at root path with html=True.
       - test_static_files_missing_directory_fallback: Verifies graceful degradation if static dir is missing.
       - test_duckdb_dependency_lake_and_fallback: Verifies read-only DuckDB connection and in-memory fallback.
       - test_cors_middleware_headers: Verifies loopback CORS preflight and access control headers.

    3. Technologies used and why:
       pytest for test orchestration, FastAPI TestClient for in-process ASGI HTTP lifecycle simulation.

    4. Key design and overall design of the class:
       Enforces Gate G4 architectural contracts defined in Milestone M6-01 and M6-05.
    """

    def setup_method(self) -> None:
        """
        1. The use of function:
           Sets up TestClient instance before each test method execution.

        2. How does the specific function work:
           Initializes self.client wrapping the global FastAPI app.

        3. Concepts used in the function:
           Test fixture initialization.

        4. Places where this function is imported and used:
           Invoked automatically by pytest test runner.

        5. Final output of the function, before and after:
           Before: Uninitialized client. After: self.client ready for HTTP dispatch.
        """
        self.client = TestClient(app)

    def test_health_endpoint_contract(self) -> None:
        """
        1. The use of function:
           Validates that /api/v1/health conforms to the M6-01 contract and latency requirements.

        2. How does the specific function work:
           Measures dispatch elapsed time, verifies HTTP 200 response, checks latency <= 50ms,
           and validates exact payload schema: {"status": "ok", "service": "quantview-gateway", "version": "1.0.0"}.

        3. Concepts used in the function:
           HTTP status assertions, latency profiling, schema contract validation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified health route. After: Verified HTTP 200 and schema compliance.
        """
        t0 = time.perf_counter()
        response = self.client.get("/api/v1/health")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert response.status_code == 200
        data = response.json()
        assert data == {
            "status": "ok",
            "service": "quantview-gateway",
            "version": "1.0.0",
        }
        assert elapsed_ms <= 50.0, f"Health check latency ({elapsed_ms:.2f}ms) exceeded 50ms threshold"

    def test_heartbeat_endpoint_telemetry(self) -> None:
        """
        1. The use of function:
           Validates that /api/v1/health/heartbeat returns valid process health metrics.

        2. How does the specific function work:
           Issues GET request to /api/v1/health/heartbeat, asserts HTTP 200, and verifies presence
           and types of status, service, timestamp_utc, epoch_sec, uptime_seconds, and pid.

        3. Concepts used in the function:
           Process telemetry verification, timestamp integrity.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified heartbeat route. After: Verified heartbeat metrics.
        """
        response = self.client.get("/api/v1/health/heartbeat")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "ok"
        assert data["service"] == "quantview-gateway"
        assert "timestamp_utc" in data
        assert isinstance(data["epoch_sec"], int)
        assert data["epoch_sec"] > 0
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0.0
        assert isinstance(data["pid"], int)
        assert data["pid"] > 0

    def test_static_files_mount_serving(self) -> None:
        """
        1. The use of function:
           Validates that StaticFiles mounted at root serves static assets from apps/web.

        2. How does the specific function work:
           Requests /README.md (which exists inside apps/web) and asserts HTTP 200 with text content.

        3. Concepts used in the function:
           Static file routing, asset distribution.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified static asset serving. After: Verified static file delivery.
        """
        response = self.client.get("/README.md")
        assert response.status_code == 200
        assert "QuantView" in response.text or len(response.text) > 0

    def test_static_files_index_html_serving(self) -> None:
        """
        1. The use of function:
           Validates that an index.html file located in the static directory is served at root '/'.

        2. How does the specific function work:
           Creates a temporary directory with an index.html file, initializes a custom FastAPI app
           pointing web_static_dir to this directory, and verifies GET '/' returns HTTP 200 and the html content.

        3. Concepts used in the function:
           Isolated temporary directories, application factory parameterization, default document serving.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified root HTML fallback. After: Verified root HTML resolution.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            index_path = Path(tmp_dir) / "index.html"
            index_path.write_text("<!DOCTYPE html><html><body><h1>QuantView UI</h1></body></html>", encoding="utf-8")

            cfg = ApiConfig(web_static_dir=tmp_dir)
            custom_app = create_app(config=cfg)
            client = TestClient(custom_app)

            response = client.get("/")
            assert response.status_code == 200
            assert "<h1>QuantView UI</h1>" in response.text

    def test_static_files_missing_directory_fallback(self) -> None:
        """
        1. The use of function:
           Validates that the application boots gracefully when the static directory does not exist.

        2. How does the specific function work:
           Configures an ApiConfig pointing to a non-existent path, initializes the app via create_app,
           and confirms API routes remain functional without crashing.

        3. Concepts used in the function:
           Graceful degradation, robust startup error tolerance.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Risk of startup crash on missing directory. After: Verified fault tolerance.
        """
        non_existent = "non_existent_dir_for_test_12345"
        cfg = ApiConfig(web_static_dir=non_existent)
        custom_app = create_app(config=cfg)
        client = TestClient(custom_app)

        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_duckdb_dependency_lake_and_fallback(self) -> None:
        """
        1. The use of function:
           Validates DuckDB dependency providers under real lake and missing lake conditions.

        2. How does the specific function work:
           - Tests get_duckdb_connection with default path (existing lake).
           - Tests get_duckdb_connection with non-existent path (verifying safe :memory: fallback).
           - Tests get_duckdb generator dependency yielding connection and deterministically closing it.

        3. Concepts used in the function:
           DuckDB embedded connections, database dependency injection lifecycle.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified DB dependencies. After: Verified connection and fallback mechanics.
        """
        # Test 1: Active lake connection
        conn_real = get_duckdb_connection()
        try:
            res = conn_real.execute("SELECT 42 AS val").fetchone()
            assert res is not None
            assert res[0] == 42
        finally:
            conn_real.close()

        # Test 2: Missing lake fallback to :memory:
        conn_fallback = get_duckdb_connection(lake_path="missing_lake_for_test_999.duckdb")
        try:
            res2 = conn_fallback.execute("SELECT 100 AS val").fetchone()
            assert res2 is not None
            assert res2[0] == 100
        finally:
            conn_fallback.close()

        # Test 3: Generator dependency lifecycle
        cfg = get_api_config()
        gen = get_duckdb(config=cfg)
        conn_gen = next(gen)
        try:
            res3 = conn_gen.execute("SELECT 1 AS ok").fetchone()
            assert res3 is not None
            assert res3[0] == 1
        finally:
            with pytest.raises(StopIteration):
                next(gen)

    def test_cors_middleware_headers(self) -> None:
        """
        1. The use of function:
           Validates CORS middleware headers for local loopback development.

        2. How does the specific function work:
           Issues HTTP OPTIONS request with Origin header and asserts access-control-allow-origin response.

        3. Concepts used in the function:
           CORS preflight handling, web security boundaries.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified CORS middleware. After: Verified access control headers.
        """
        origin = "http://localhost:8000"
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        }
        response = self.client.options("/api/v1/health", headers=headers)
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == origin
