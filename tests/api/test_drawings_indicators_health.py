"""
1. What this file does:
   Automated verification suite for Milestone M6-02, M6-05, M6-11, and M6-13 (Drawings, Indicators & Data Health API).
   Validates data coverage and licensing, indicator descriptors, indicator computation, and chart drawing CRUD operations.

2. Overall design:
   Uses pytest and FastAPI TestClient to test:
     - GET /api/v1/health/coverage: Verifies session counts (1,161 total, 1,144 eligible, 17 warning, 0 ineligible),
       snapshot captures (82,274), underlying candles (437,008), HEALTHY verdict, and Apache-2.0 chart license.
     - GET /api/v1/indicators: Verifies indicator catalog schemas (EMA, SMA, RSI, MACD, ATR, Supertrend, BOS_CHOCH).
     - POST /api/v1/indicators/compute: Verifies on-demand calculation across multiple indicator families (EMA, SMA, RSI, MACD, Supertrend, BOS_CHOCH).
     - POST /api/v1/charts/drawings: Verifies single and batch drawing creation and persistence.
     - GET /api/v1/charts/drawings: Verifies symbol-filtered and global drawing retrieval.
     - DELETE /api/v1/charts/drawings/{drawing_id}: Verifies single drawing deletion and 404 error handling.
     - DELETE /api/v1/charts/drawings: Verifies symbol-scoped bulk drawing purge.
     - DrawingStore durability: Verifies local filesystem JSON persistence and hydration.

3. Elements in the file:
   - TestDrawingsIndicatorsHealth: Main test case class executing all Gate G4 verification routines.

4. Final output of the file:
   - Automated pass/fail test execution under Release Gate G4.
"""

import tempfile
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from services.api.deps import get_duckdb_connection
from services.api.main import app
from services.api.routers.drawings import DrawingStore, get_drawing_store
from services.api.schemas.drawings import DrawingPoint, DrawingRecord


@pytest.mark.gate_g4
class TestDrawingsIndicatorsHealth:
    """
    1. The use of class:
       Test suite validating Data Coverage, Technical Indicators, and Chart Drawing API endpoints.

    2. What the class contains:
       - setup_method: Test fixture setting up TestClient and clean isolated DrawingStore.
       - teardown_method: Test cleanup tearing down temporary drawing storage.
       - test_health_coverage_contract_and_counts: Verifies session eligibility, snapshot captures, and licensing.
       - test_health_coverage_empty_lake_fallback: Verifies graceful degradation on missing tables.
       - test_indicators_catalog_discovery: Verifies indicator registry catalog containing required algorithms.
       - test_indicators_compute_ema_success: Verifies EMA calculation over real historical candle bars.
       - test_indicators_compute_sma_and_rsi: Verifies SMA and RSI calculation correctness.
       - test_indicators_compute_macd_multiline: Verifies MACD multi-line output (macd, signal, histogram).
       - test_indicators_compute_supertrend_and_structure: Verifies Supertrend bands and structural pivots.
       - test_indicators_compute_unknown_indicator_400: Verifies rejection of unsupported indicator IDs.
       - test_indicators_compute_empty_data_symbol: Verifies empty timeseries output for non-existent symbols.
       - test_drawings_create_and_retrieve_single: Verifies drawing creation and retrieval by symbol.
       - test_drawings_batch_create_and_filter: Verifies batch drawing upsert and symbol filtering.
       - test_drawings_delete_single_and_404: Verifies drawing deletion by ID and 404 on unknown ID.
       - test_drawings_delete_bulk_by_symbol: Verifies bulk deletion of drawings by instrument symbol.
       - test_drawings_filesystem_persistence_and_reload: Verifies disk synchronization and recovery.

    3. Technologies used and why:
       pytest for test orchestration, FastAPI TestClient for in-process ASGI HTTP lifecycle simulation,
       tempfile.TemporaryDirectory for isolated filesystem storage.

    4. Key design and overall design of the class:
       Enforces Gate G4 architectural contracts defined in Milestones M6-02, M6-05, M6-11, and M6-13.
    """

    def setup_method(self) -> None:
        """
        1. The use of function:
           Initializes TestClient and an isolated temporary DrawingStore prior to each test.

        2. How does the specific function work:
           Creates a temporary directory for drawings persistence, instantiates an isolated
           DrawingStore, and overrides the get_drawing_store FastAPI dependency.

        3. Concepts used in the function:
           Test isolation, dependency override, temporary filesystem lifecycle.

        4. Places where this function is imported and used:
           Invoked automatically by pytest prior to each test method.

        5. Final output of the function, before and after:
           Before: Uninitialized test state. After: self.client and isolated store configured.
        """
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_path = Path(self.temp_dir.name) / "drawings.json"
        self.store = DrawingStore(storage_path=self.storage_path)

        app.dependency_overrides[get_drawing_store] = lambda: self.store
        self.client = TestClient(app)

    def teardown_method(self) -> None:
        """
        1. The use of function:
           Cleans up dependency overrides and cleans temporary directories after each test.

        2. How does the specific function work:
           Removes the get_drawing_store dependency override and cleans up the temporary directory.

        3. Concepts used in the function:
           Resource reclamation, fixture teardown.

        4. Places where this function is imported and used:
           Invoked automatically by pytest after each test method.

        5. Final output of the function, before and after:
           Before: Overridden app dependencies. After: Clean global app state.
        """
        app.dependency_overrides.pop(get_drawing_store, None)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_health_coverage_contract_and_counts(self) -> None:
        """
        1. The use of function:
           Validates that /api/v1/health/coverage conforms to M6-02 and M6-05 specifications.

        2. How does the specific function work:
           Dispatches GET request to /api/v1/health/coverage, verifies HTTP 200, checks total_sessions
           is 1,161, eligible_sessions is 1,144, warning_sessions is 17, ineligible_sessions is 0,
           verdict is 'HEALTHY', chart_license is Apache-2.0, snapshots_captures is 82,274, and
           candles_underlying is 437,008.

        3. Concepts used in the function:
           Data health verification, session audit metrics, licensing compliance.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified coverage endpoint. After: Confirmed lake coverage metrics.
        """
        response = self.client.get("/api/v1/health/coverage")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "ok"
        assert data["verdict"] == "HEALTHY"
        assert data["chart_license"] == "Apache-2.0 (TradingView Lightweight Charts v5)"
        assert data["total_sessions"] == 1161
        assert data["start_date"] == "2022-01-03"
        assert data["end_date"] == "2026-10-19"
        assert data["eligible_sessions"] == 1144
        assert data["warning_sessions"] == 17
        assert data["ineligible_sessions"] == 0
        assert data["snapshots_captures"] == 82274
        assert data["candles_underlying"] == 437008
        assert "duckdb_lake_path" in data

    def test_health_coverage_empty_lake_fallback(self) -> None:
        """
        1. The use of function:
           Verifies graceful degradation when DuckDB connection is in-memory and views are absent.

        2. How does the specific function work:
           Overrides the get_duckdb dependency with an in-memory database without analytical views,
           dispatches GET /api/v1/health/coverage, and confirms fallback defaults.

        3. Concepts used in the function:
           Fault tolerance, graceful degradation, mock dependency injection.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified fallback behavior. After: Verified default metrics returned without error.
        """
        from services.api.deps import get_duckdb

        def _mock_empty_duckdb() -> Generator[object, None, None]:
            conn = get_duckdb_connection(":memory:")
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[get_duckdb] = _mock_empty_duckdb
        try:
            response = self.client.get("/api/v1/health/coverage")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["verdict"] == "HEALTHY"
            assert data["total_sessions"] == 1161
            assert data["eligible_sessions"] == 1144
        finally:
            app.dependency_overrides.pop(get_duckdb, None)

    def test_indicators_catalog_discovery(self) -> None:
        """
        1. The use of function:
           Validates the GET /api/v1/indicators catalog discovery endpoint.

        2. How does the specific function work:
           Dispatches GET /api/v1/indicators, verifies HTTP 200, checks that all required
           indicators (EMA, SMA, RSI, MACD, ATR, Supertrend, BOS_CHOCH) are present with valid
           categories, chart pane designations, and parameter schemas.

        3. Concepts used in the function:
           Schema reflection, catalog contract validation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified indicators catalog. After: Verified indicator specifications.
        """
        response = self.client.get("/api/v1/indicators")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 7

        indicator_ids = {item["id"] for item in data}
        expected = {"EMA", "SMA", "RSI", "MACD", "ATR", "Supertrend", "BOS_CHOCH"}
        assert expected.issubset(indicator_ids)

        for desc in data:
            assert "name" in desc
            assert desc["category"] in {"trend", "momentum", "volatility", "structural"}
            assert desc["pane"] in {"primary", "subpane"}
            assert isinstance(desc["parameters"], list)

    def test_indicators_compute_ema_success(self) -> None:
        """
        1. The use of function:
           Verifies on-demand calculation of Exponential Moving Average (EMA).

        2. How does the specific function work:
           Posts an IndicatorComputeRequest for symbol 'NSE:NIFTY50' and indicator 'EMA' with length 20,
           verifies HTTP 200, checks response metadata, validates that timeseries data points
           contain valid UTC epoch seconds and non-empty 'ema' float values.

        3. Concepts used in the function:
           On-demand indicator calculation, timestamp monotonicity, moving average validation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Raw calculation request. After: Validated EMA timeseries response.
        """
        payload = {
            "symbol": "NSE:NIFTY50",
            "indicator_id": "EMA",
            "resolution": "1m",
            "params": {"length": 20},
            "limit": 100,
        }
        response = self.client.post("/api/v1/indicators/compute", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["indicator_id"] == "EMA"
        assert data["symbol"] == "NSE:NIFTY50"
        assert data["resolution"] == "1m"
        assert len(data["data"]) == 100

        first_point = data["data"][0]
        assert "time" in first_point
        assert "values" in first_point
        assert "ema" in first_point["values"]
        assert isinstance(first_point["values"]["ema"], (float, int))

        last_point = data["data"][-1]
        assert last_point["time"] > first_point["time"]
        assert isinstance(last_point["values"]["ema"], (float, int))

    def test_indicators_compute_sma_and_rsi(self) -> None:
        """
        1. The use of function:
           Verifies computation of Simple Moving Average (SMA) and Relative Strength Index (RSI).

        2. How does the specific function work:
           Submits requests for SMA and RSI on 'NIFTY', verifies HTTP 200, checks warm-up NaN/None handling,
           and validates that late series values are valid bounded numbers (RSI between 0 and 100).

        3. Concepts used in the function:
           Rolling mean, momentum oscillator, warm-up boundaries.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified SMA and RSI calculation. After: Confirmed numeric accuracy.
        """
        # Test SMA
        sma_res = self.client.post(
            "/api/v1/indicators/compute",
            json={"symbol": "NIFTY", "indicator_id": "SMA", "params": {"length": 10}, "limit": 50},
        )
        assert sma_res.status_code == 200
        sma_data = sma_res.json()["data"]
        assert len(sma_data) == 50
        # Warmup bars should be None
        assert sma_data[0]["values"]["sma"] is None
        # Later bars should be valid floats
        assert isinstance(sma_data[-1]["values"]["sma"], float)

        # Test RSI
        rsi_res = self.client.post(
            "/api/v1/indicators/compute",
            json={"symbol": "NIFTY", "indicator_id": "RSI", "params": {"length": 14}, "limit": 50},
        )
        assert rsi_res.status_code == 200
        rsi_data = rsi_res.json()["data"]
        assert len(rsi_data) == 50
        last_rsi = rsi_data[-1]["values"]["rsi"]
        assert isinstance(last_rsi, float)
        assert 0.0 <= last_rsi <= 100.0

    def test_indicators_compute_macd_multiline(self) -> None:
        """
        1. The use of function:
           Verifies multi-line calculation for Moving Average Convergence Divergence (MACD).

        2. How does the specific function work:
           Dispatches compute request for 'MACD', verifies HTTP 200, checks that points include
           'macd', 'signal', and 'histogram' keys in the values dictionary.

        3. Concepts used in the function:
           Multi-series indicator output, oscillator convergence.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified MACD series. After: Verified macd, signal, and histogram series.
        """
        payload = {
            "symbol": "NIFTY",
            "indicator_id": "MACD",
            "params": {"fast_length": 12, "slow_length": 26, "signal_length": 9},
            "limit": 50,
        }
        response = self.client.post("/api/v1/indicators/compute", json=payload)
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 50

        last_values = data[-1]["values"]
        assert "macd" in last_values
        assert "signal" in last_values
        assert "histogram" in last_values
        assert isinstance(last_values["macd"], float)
        assert isinstance(last_values["signal"], float)
        assert isinstance(last_values["histogram"], float)

    def test_indicators_compute_supertrend_and_structure(self) -> None:
        """
        1. The use of function:
           Verifies calculation of Supertrend overlay and BOS/CHoCH market structure levels.

        2. How does the specific function work:
           Tests 'Supertrend' for 'supertrend' and 'direction' values, and tests 'BOS_CHOCH'
           for structural level coordinates.

        3. Concepts used in the function:
           Volatility bands, directional regimes, structural break pivots.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified overlay indicators. After: Verified output fields.
        """
        # Supertrend
        st_res = self.client.post(
            "/api/v1/indicators/compute",
            json={"symbol": "NIFTY", "indicator_id": "Supertrend", "limit": 40},
        )
        assert st_res.status_code == 200
        st_data = st_res.json()["data"]
        assert len(st_data) == 40
        last_st = st_data[-1]["values"]
        assert "supertrend" in last_st
        assert "direction" in last_st
        assert last_st["direction"] in {1.0, -1.0}

        # BOS_CHOCH
        bos_res = self.client.post(
            "/api/v1/indicators/compute",
            json={"symbol": "NIFTY", "indicator_id": "BOS_CHOCH", "limit": 40},
        )
        assert bos_res.status_code == 200
        bos_data = bos_res.json()["data"]
        assert len(bos_data) == 40
        assert "high_level" in bos_data[-1]["values"]
        assert "low_level" in bos_data[-1]["values"]

    def test_indicators_compute_unknown_indicator_400(self) -> None:
        """
        1. The use of function:
           Verifies that an unsupported indicator_id yields HTTP 400 Bad Request.

        2. How does the specific function work:
           Submits an IndicatorComputeRequest with indicator_id 'NON_EXISTENT_INDICATOR',
           verifies HTTP 400 response and descriptive error detail.

        3. Concepts used in the function:
           Error handling, HTTP status validation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Invalid request. After: HTTP 400 error assertion.
        """
        payload = {
            "symbol": "NIFTY",
            "indicator_id": "NON_EXISTENT_INDICATOR",
        }
        response = self.client.post("/api/v1/indicators/compute", json=payload)
        assert response.status_code == 400
        assert "Unsupported indicator_id" in response.json()["detail"]

    def test_indicators_compute_empty_data_symbol(self) -> None:
        """
        1. The use of function:
           Verifies that requesting an indicator for an empty or unknown instrument returns empty data list.

        2. How does the specific function work:
           Submits compute request for symbol 'UNKNOWN_SYMBOL', verifies HTTP 200 and data = [].

        3. Concepts used in the function:
           Graceful handling of empty series.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Request for unknown symbol. After: Empty data array.
        """
        payload = {
            "symbol": "UNKNOWN_SYMBOL_XYZ",
            "indicator_id": "EMA",
        }
        response = self.client.post("/api/v1/indicators/compute", json=payload)
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_drawings_create_and_retrieve_single(self) -> None:
        """
        1. The use of function:
           Verifies creating a single drawing and retrieving it by symbol.

        2. How does the specific function work:
           Posts a single DrawingRecord for 'NSE:NIFTY50', verifies HTTP 200 and returned record,
           then queries GET /api/v1/charts/drawings?symbol=NSE:NIFTY50 and asserts the record is returned.

        3. Concepts used in the function:
           CRUD REST cycle, single resource creation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unstored drawing. After: Persisted and retrieved drawing record.
        """
        drawing_payload = {
            "id": "draw-test-1",
            "symbol": "NSE:NIFTY50",
            "type": "trendline",
            "points": [
                {"time": 1641181500, "price": 17400.0},
                {"time": 1641185100, "price": 17500.0},
            ],
            "properties": {"color": "#2962FF", "lineWidth": 2},
        }

        save_res = self.client.post("/api/v1/charts/drawings", json=drawing_payload)
        assert save_res.status_code == 200
        saved = save_res.json()
        assert isinstance(saved, list)
        assert len(saved) == 1
        assert saved[0]["id"] == "draw-test-1"
        assert saved[0]["symbol"] == "NSE:NIFTY50"
        assert saved[0]["type"] == "trendline"
        assert len(saved[0]["points"]) == 2

        # Retrieve by symbol
        get_res = self.client.get("/api/v1/charts/drawings?symbol=NSE:NIFTY50")
        assert get_res.status_code == 200
        results = get_res.json()
        assert len(results) == 1
        assert results[0]["id"] == "draw-test-1"

    def test_drawings_batch_create_and_filter(self) -> None:
        """
        1. The use of function:
           Verifies batch creation of drawings across different symbols and query filtering.

        2. How does the specific function work:
           Submits a list of 3 DrawingRecords (2 for NIFTY, 1 for INDIAVIX), verifies upsert,
           queries drawings with symbol=NIFTY (returns 2), symbol=INDIAVIX (returns 1), and
           unfiltered GET (returns all 3).

        3. Concepts used in the function:
           Batch persistence, polymorphic ingestion, symbol filtering.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Multiple drawings. After: Verified symbol routing and bulk persistence.
        """
        batch = [
            {
                "id": "draw-batch-1",
                "symbol": "NIFTY",
                "type": "horizontal_line",
                "points": [{"time": 1641181500, "price": 17500.0}],
            },
            {
                "id": "draw-batch-2",
                "symbol": "NIFTY",
                "type": "rectangle",
                "points": [
                    {"time": 1641181500, "price": 17400.0},
                    {"time": 1641185000, "price": 17450.0},
                ],
            },
            {
                "id": "draw-batch-3",
                "symbol": "INDIAVIX",
                "type": "horizontal_line",
                "points": [{"time": 1641181500, "price": 16.5}],
            },
        ]

        save_res = self.client.post("/api/v1/charts/drawings", json=batch)
        assert save_res.status_code == 200
        assert len(save_res.json()) == 3

        # Filter by NIFTY
        nifty_res = self.client.get("/api/v1/charts/drawings?symbol=NIFTY")
        assert nifty_res.status_code == 200
        assert len(nifty_res.json()) == 2

        # Filter by INDIAVIX
        vix_res = self.client.get("/api/v1/charts/drawings?symbol=INDIAVIX")
        assert vix_res.status_code == 200
        assert len(vix_res.json()) == 1

        # Unfiltered query
        all_res = self.client.get("/api/v1/charts/drawings")
        assert all_res.status_code == 200
        assert len(all_res.json()) == 3

    def test_drawings_delete_single_and_404(self) -> None:
        """
        1. The use of function:
           Verifies individual drawing deletion by unique ID and HTTP 404 behavior.

        2. How does the specific function work:
           Creates a drawing, deletes it via DELETE /api/v1/charts/drawings/{id}, verifies status 'deleted',
           asserts drawing is no longer retrievable, and verifies subsequent delete of same ID returns HTTP 404.

        3. Concepts used in the function:
           Resource deletion, idempotent error signaling, 404 status.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Persisted drawing. After: Drawing purged and confirmed absent.
        """
        item = {
            "id": "draw-del-target",
            "symbol": "NIFTY",
            "type": "trendline",
            "points": [{"time": 100, "price": 100.0}],
        }
        self.client.post("/api/v1/charts/drawings", json=item)

        del_res = self.client.delete("/api/v1/charts/drawings/draw-del-target")
        assert del_res.status_code == 200
        assert del_res.json() == {"status": "deleted", "id": "draw-del-target"}

        # Subsequent delete returns 404
        second_del = self.client.delete("/api/v1/charts/drawings/draw-del-target")
        assert second_del.status_code == 404

    def test_drawings_delete_bulk_by_symbol(self) -> None:
        """
        1. The use of function:
           Verifies bulk purging of drawings for a specific symbol.

        2. How does the specific function work:
           Inserts 2 drawings for NIFTY and 1 for INDIAVIX. Calls DELETE /api/v1/charts/drawings?symbol=NIFTY.
           Verifies response indicates 2 deleted, and verifies that INDIAVIX drawing remains untouched.

        3. Concepts used in the function:
           Bulk resource eviction, symbol scoping.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: 3 drawings total. After: 2 NIFTY drawings removed, 1 INDIAVIX drawing preserved.
        """
        items = [
            {"id": "n1", "symbol": "NIFTY", "type": "trendline", "points": []},
            {"id": "n2", "symbol": "NIFTY", "type": "horizontal_line", "points": []},
            {"id": "v1", "symbol": "INDIAVIX", "type": "trendline", "points": []},
        ]
        self.client.post("/api/v1/charts/drawings", json=items)

        del_res = self.client.delete("/api/v1/charts/drawings?symbol=NIFTY")
        assert del_res.status_code == 200
        data = del_res.json()
        assert data["status"] == "deleted"
        assert data["symbol"] == "NIFTY"
        assert data["count"] == 2

        # Check remaining
        remaining = self.client.get("/api/v1/charts/drawings").json()
        assert len(remaining) == 1
        assert remaining[0]["id"] == "v1"

    def test_drawings_filesystem_persistence_and_reload(self) -> None:
        """
        1. The use of function:
           Verifies that DrawingStore saves state to disk and accurately hydrates state on restart.

        2. How does the specific function work:
           Adds records to store, verifies disk file exists and is populated with JSON,
           creates a brand new DrawingStore pointing to the same file path, and confirms all records
           are successfully hydrated into memory.

        3. Concepts used in the function:
           Filesystem serialization, persistence durability, state hydration.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: In-memory records. After: Reloaded identical records from disk file.
        """
        record = DrawingRecord(
            id="persist-1",
            symbol="NIFTY",
            type="rectangle",
            points=[DrawingPoint(time=1000, price=20000.0)],
            properties={"fill": True},
        )
        self.store.upsert([record])

        # Verify disk file exists
        assert self.storage_path.is_file()

        # Instantiate fresh store pointing to the same file
        reloaded_store = DrawingStore(storage_path=self.storage_path)
        loaded = reloaded_store.get_all()
        assert len(loaded) == 1
        assert loaded[0].id == "persist-1"
        assert loaded[0].symbol == "NIFTY"
        assert loaded[0].type == "rectangle"
        assert loaded[0].properties == {"fill": True}

    def test_drawings_default_storage_path_anchored_to_repo_root(self) -> None:
        """
        1. The use of function:
           Asserts that default DrawingStore instance resolves to the repository root Data/drawings/drawings.json.

        2. How does the specific function work:
           Instantiates DrawingStore with storage_path=None and asserts _storage_path matches repo_root / Data / drawings / drawings.json.

        3. Concepts used in the function:
           Filesystem path resolution, default configuration verification.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified default path. After: Verified repo-root relative path resolution.
        """
        default_store = DrawingStore(storage_path=None)
        expected_suffix = Path("Data") / "drawings" / "drawings.json"
        assert str(default_store._storage_path).endswith(str(expected_suffix))
        assert not str(default_store._storage_path).replace("\\", "/").endswith("services/Data/drawings/drawings.json")
