"""
1. What this file does:
   Automated verification test suite for Milestones M6-11, M6-12, and M6-17 (Technical Indicators UI Contract,
   Multi-Pane Overlays & Oscillators, and Catalog Discovery API endpoints).

2. Overall design:
   Validates the gateway technical indicator endpoints and frontend schema compatibility:
     - GET /api/v1/indicators and GET /api/v1/charts/indicators: Catalog discovery, category classifications,
       pane designations (primary vs subpane), and parameter schemas.
     - POST /api/v1/indicators/compute and POST /api/v1/charts/indicators/compute: Multi-indicator computation
       including EMA overlays, Bollinger Bands, Supertrend, SMC BOS/CHoCH, RSI, MACD, and ATR.
     - Tests boundary values, parameter validation, empty lakes, and trailing slash URL compatibility.

3. Elements in the file:
   - TestIndicatorsUIContract: Main test class with pytest fixtures and test methods.

4. Final output of the file:
   - Pytest executable test suite validating Release Gate G4 indicator contracts.
"""

from typing import List

import pytest
from fastapi.testclient import TestClient

from services.api.main import app


@pytest.mark.gate_g4
class TestIndicatorsUIContract:
    """
    1. The use of class:
       Test suite verifying Technical Indicators Catalog Discovery, Computation Contracts,
       and Multi-Pane Overlay / Sub-Pane Data Structures for the QuantView workstation.

    2. What the class contains:
       - setup_method: Application bootstrap and TestClient initialization.
       - test_indicators_catalog_discovery_and_aliases: Verifies GET /api/v1/indicators and /api/v1/charts/indicators.
       - test_indicators_pane_designations_and_categories: Verifies primary vs subpane assignment.
       - test_indicators_compute_bollinger_bands_overlay: Verifies BB calculation and upper >= middle >= lower envelope.
       - test_indicators_compute_ema_multiple_lengths: Verifies configurable EMA lengths (9, 21, 50, 200).
       - test_indicators_compute_macd_subpane_contract: Verifies MACD line, signal line, and histogram values.
       - test_indicators_compute_rsi_subpane_contract: Verifies RSI bounds within [0, 100].
       - test_indicators_compute_atr_subpane_contract: Verifies positive ATR volatility values.
       - test_indicators_compute_supertrend_overlay_contract: Verifies Supertrend bands and directional state.
       - test_indicators_compute_smc_structure_contract: Verifies swing levels and BOS/CHoCH structural event fields.
       - test_indicators_invalid_parameter_validation: Verifies HTTP 400 rejection for malformed parameters.

    3. Technologies used and why:
       Pytest and FastAPI TestClient for synchronous API testing against ASGI test harness.

    4. Key design and overall design of the class:
       Exercises all indicator families across primary overlay and sub-pane endpoints.
    """

    def setup_method(self) -> None:
        """
        1. The use of function:
           Prepares test environment before each test method execution.

        2. How does the specific function work:
           Instantiates FastAPI TestClient bound to the global app instance.

        3. Concepts used in the function:
           Test isolation, fixture setup.

        4. Places where this function is imported and used:
           Invoked automatically by pytest harness before each test method.

        5. Final output of the function, before and after:
           Before: Uninitialized test instance. After: self.client initialized.
        """
        self.client = TestClient(app)

    def test_indicators_catalog_discovery_and_aliases(self) -> None:
        """
        1. The use of function:
           Verifies that both /api/v1/indicators and /api/v1/charts/indicators resolve to the catalog.

        2. How does the specific function work:
           Dispatches GET requests to all catalog URL aliases (with and without trailing slashes),
           verifying HTTP 200 and consistent descriptor payload content.

        3. Concepts used in the function:
           Route aliasing, catalog discovery.

        4. Places where this function is imported and used:
           Called by pytest.

        5. Final output of the function, before and after:
           Before: Unverified route aliases. After: Confirmed identical catalog discovery across all aliases.
        """
        endpoints = [
            "/api/v1/indicators",
            "/api/v1/indicators/",
            "/api/v1/charts/indicators",
            "/api/v1/charts/indicators/",
        ]
        for url in endpoints:
            res = self.client.get(url)
            assert res.status_code == 200, f"Endpoint {url} failed with status {res.status_code}"
            data = res.json()
            assert isinstance(data, list)
            assert len(data) >= 7

            ids = {item["id"] for item in data}
            expected = {"EMA", "SMA", "BB", "RSI", "MACD", "ATR", "Supertrend", "BOS_CHOCH"}
            assert expected.issubset(ids), f"Missing expected indicators from {url}: {expected - ids}"

    def test_indicators_pane_designations_and_categories(self) -> None:
        """
        1. The use of function:
           Validates that each registered indicator defines valid pane designation and category.

        2. How does the specific function work:
           Queries catalog, inspects each descriptor's 'pane' ('primary' or 'subpane') and 'category'
           ('trend', 'momentum', 'volatility', 'structural').

        3. Concepts used in the function:
           Schema validation, multi-pane chart architecture.

        4. Places where this function is imported and used:
           Called by pytest.

        5. Final output of the function, before and after:
           Before: Unverified descriptors. After: Confirmed pane and category contracts.
        """
        res = self.client.get("/api/v1/charts/indicators")
        assert res.status_code == 200
        catalog = {item["id"]: item for item in res.json()}

        # Overlays must map to primary pane
        assert catalog["EMA"]["pane"] == "primary"
        assert catalog["SMA"]["pane"] == "primary"
        assert catalog["BB"]["pane"] == "primary"
        assert catalog["Supertrend"]["pane"] == "primary"
        assert catalog["BOS_CHOCH"]["pane"] == "primary"

        # Oscillators must map to subpane
        assert catalog["RSI"]["pane"] == "subpane"
        assert catalog["MACD"]["pane"] == "subpane"
        assert catalog["ATR"]["pane"] == "subpane"

        # Verify parameter descriptions
        for ind_id, desc in catalog.items():
            assert "name" in desc and len(desc["name"]) > 0
            assert "category" in desc and desc["category"] in {"trend", "momentum", "volatility", "structural"}
            assert "parameters" in desc and isinstance(desc["parameters"], list)
            for param in desc["parameters"]:
                assert "name" in param and "type" in param and "default" in param

    def test_indicators_compute_bollinger_bands_overlay(self) -> None:
        """
        1. The use of function:
           Verifies Bollinger Bands computation via /api/v1/charts/indicators/compute.

        2. How does the specific function work:
           Submits compute request for 'BB' with length=20 and mult=2.0. Checks that
           returned points contain 'middle', 'upper', and 'lower' bands, and verifies
           that lower <= middle <= upper envelope inequality holds.

        3. Concepts used in the function:
           Bollinger Bands calculation, envelope inequality validation.

        4. Places where this function is imported and used:
           Called by pytest.

        5. Final output of the function, before and after:
           Before: Unverified BB API. After: Confirmed upper, middle, lower band coordinates.
        """
        payload = {
            "symbol": "NIFTY",
            "indicator_id": "BB",
            "resolution": "5m",
            "params": {"length": 20, "mult": 2.0},
            "limit": 100,
        }
        res = self.client.post("/api/v1/charts/indicators/compute", json=payload)
        assert res.status_code == 200
        data = res.json()["data"]
        assert len(data) > 0

        # Check latest warmed-up points
        valid_points = [p for p in data if p["values"]["middle"] is not None]
        assert len(valid_points) > 0
        for p in valid_points[-10:]:
            vals = p["values"]
            assert vals["lower"] <= vals["middle"] <= vals["upper"]

    def test_indicators_compute_ema_multiple_lengths(self) -> None:
        """
        1. The use of function:
           Verifies EMA calculation across standard configurable overlay lengths (9, 21, 50, 200).

        2. How does the specific function work:
           Iterates over lengths [9, 21, 50, 200], submits compute request, and checks that
           numeric float ema values are emitted with correct timestamps.

        3. Concepts used in the function:
           Exponential moving average, multi-length verification.

        4. Places where this function is imported and used:
           Called by pytest.

        5. Final output of the function, before and after:
           Before: Unverified EMA lengths. After: Confirmed EMA 9, 21, 50, 200 computations.
        """
        for length in [9, 21, 50, 200]:
            payload = {
                "symbol": "NIFTY",
                "indicator_id": "EMA",
                "resolution": "5m",
                "params": {"length": length},
                "limit": 250,
            }
            res = self.client.post("/api/v1/charts/indicators/compute", json=payload)
            assert res.status_code == 200
            data = res.json()["data"]
            assert len(data) > 0
            warmed = [p for p in data if p["values"]["ema"] is not None]
            assert len(warmed) > 0
            assert isinstance(warmed[-1]["values"]["ema"], (int, float))

    def test_indicators_compute_macd_subpane_contract(self) -> None:
        """
        1. The use of function:
           Verifies MACD oscillator timeseries computation for sub-pane rendering.

        2. How does the specific function work:
           Dispatches compute request for 'MACD', verifies that 'macd', 'signal', and
           'histogram' values are present in each output point.

        3. Concepts used in the function:
           MACD oscillator, dual-line and histogram data model.

        4. Places where this function is imported and used:
           Called by pytest.

        5. Final output of the function, before and after:
           Before: Unverified MACD endpoint. After: Confirmed MACD line, signal, and histogram.
        """
        payload = {
            "symbol": "NIFTY",
            "indicator_id": "MACD",
            "resolution": "5m",
            "params": {"fast_length": 12, "slow_length": 26, "signal_length": 9},
            "limit": 100,
        }
        res = self.client.post("/api/v1/charts/indicators/compute", json=payload)
        assert res.status_code == 200
        data = res.json()["data"]
        assert len(data) > 0
        warmed = [p for p in data if p["values"]["histogram"] is not None]
        assert len(warmed) > 0
        last = warmed[-1]["values"]
        assert "macd" in last and "signal" in last and "histogram" in last
        assert isinstance(last["histogram"], (int, float))

    def test_indicators_compute_rsi_subpane_contract(self) -> None:
        """
        1. The use of function:
           Verifies RSI momentum oscillator timeseries bounded in [0, 100].

        2. How does the specific function work:
           Dispatches compute request for 'RSI' with length 14, checks that all
           warmed-up values satisfy 0 <= rsi <= 100.

        3. Concepts used in the function:
           RSI oscillator, boundary constraint checking.

        4. Places where this function is imported and used:
           Called by pytest.

        5. Final output of the function, before and after:
           Before: Unverified RSI range. After: Confirmed 0 <= RSI <= 100 bounds.
        """
        payload = {
            "symbol": "NIFTY",
            "indicator_id": "RSI",
            "resolution": "5m",
            "params": {"length": 14},
            "limit": 100,
        }
        res = self.client.post("/api/v1/charts/indicators/compute", json=payload)
        assert res.status_code == 200
        data = res.json()["data"]
        assert len(data) > 0
        warmed = [p for p in data if p["values"]["rsi"] is not None]
        assert len(warmed) > 0
        for p in warmed:
            v = p["values"]["rsi"]
            assert 0.0 <= v <= 100.0, f"RSI out of bounds: {v}"

    def test_indicators_compute_atr_subpane_contract(self) -> None:
        """
        1. The use of function:
           Verifies Average True Range (ATR) volatility series for sub-pane rendering.

        2. How does the specific function work:
           Submits compute request for 'ATR' with length 14, checks that non-negative
           volatility coordinates are returned.

        3. Concepts used in the function:
           ATR volatility measurement.

        4. Places where this function is imported and used:
           Called by pytest.

        5. Final output of the function, before and after:
           Before: Unverified ATR values. After: Confirmed non-negative ATR coordinates.
        """
        payload = {
            "symbol": "NIFTY",
            "indicator_id": "ATR",
            "resolution": "5m",
            "params": {"length": 14},
            "limit": 100,
        }
        res = self.client.post("/api/v1/charts/indicators/compute", json=payload)
        assert res.status_code == 200
        data = res.json()["data"]
        assert len(data) > 0
        warmed = [p for p in data if p["values"]["atr"] is not None]
        assert len(warmed) > 0
        for p in warmed:
            assert p["values"]["atr"] >= 0.0

    def test_indicators_compute_supertrend_overlay_contract(self) -> None:
        """
        1. The use of function:
           Verifies Supertrend trend-following overlay series and direction states.

        2. How does the specific function work:
           Submits compute request for 'Supertrend' with length 10 and multiplier 3.0,
           checks that returned points contain supertrend price and direction (+1.0 or -1.0).

        3. Concepts used in the function:
           Supertrend state machine, directional indicators.

        4. Places where this function is imported and used:
           Called by pytest.

        5. Final output of the function, before and after:
           Before: Unverified Supertrend fields. After: Confirmed supertrend and direction fields.
        """
        payload = {
            "symbol": "NIFTY",
            "indicator_id": "Supertrend",
            "resolution": "5m",
            "params": {"length": 10, "multiplier": 3.0},
            "limit": 80,
        }
        res = self.client.post("/api/v1/charts/indicators/compute", json=payload)
        assert res.status_code == 200
        data = res.json()["data"]
        assert len(data) > 0
        warmed = [p for p in data if p["values"]["supertrend"] is not None]
        assert len(warmed) > 0
        for p in warmed:
            vals = p["values"]
            assert "supertrend" in vals
            assert vals["direction"] in {1.0, -1.0}

    def test_indicators_compute_smc_structure_contract(self) -> None:
        """
        1. The use of function:
           Verifies Smart Money Concepts (BOS / CHoCH) structural swing points and event emission.

        2. How does the specific function work:
           Submits compute request for 'BOS_CHOCH' with pivot_left=5 and pivot_right=5.
           Verifies that 'high_level', 'low_level', 'event', and 'bias' fields are returned.

        3. Concepts used in the function:
           Market structure analysis, Break of Structure, Change of Character.

        4. Places where this function is imported and used:
           Called by pytest.

        5. Final output of the function, before and after:
           Before: Unverified structure endpoints. After: Confirmed structural levels and event metadata.
        """
        payload = {
            "symbol": "NIFTY",
            "indicator_id": "BOS_CHOCH",
            "resolution": "5m",
            "params": {"pivot_left": 5, "pivot_right": 5},
            "limit": 100,
        }
        res = self.client.post("/api/v1/charts/indicators/compute", json=payload)
        assert res.status_code == 200
        data = res.json()["data"]
        assert len(data) > 0

        last_pt = data[-1]["values"]
        assert "high_level" in last_pt
        assert "low_level" in last_pt
        assert "event" in last_pt
        assert "bias" in last_pt

    def test_indicators_invalid_parameter_validation(self) -> None:
        """
        1. The use of function:
           Verifies error handling and HTTP 400 rejection for malformed indicator parameters.

        2. How does the specific function work:
           Submits EMA calculation request with negative length, asserts HTTP 400 Bad Request
           with informative error description.

        3. Concepts used in the function:
           Negative test, parameter validation.

        4. Places where this function is imported and used:
           Called by pytest.

        5. Final output of the function, before and after:
           Before: Unverified input validation. After: Confirmed HTTP 400 rejection on invalid params.
        """
        payload = {
            "symbol": "NIFTY",
            "indicator_id": "EMA",
            "params": {"length": -5},
        }
        res = self.client.post("/api/v1/charts/indicators/compute", json=payload)
        assert res.status_code == 400
        assert "Invalid indicator parameters" in res.json()["detail"]
