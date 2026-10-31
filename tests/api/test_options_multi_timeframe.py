"""
1. What this file does:
   Automated verification test suite for on-the-fly multi-timeframe option candlestick aggregation
   in QuantView FastAPI Gateway (Task 1). Validates resolution mapping ("1m", "3m", "5m", "15m",
   "30m", "1h", "4h", "1d"), DuckDB SQL aggregation math (arg_min, max, min, arg_max, sum),
   temporal spacing (300s for 5m, 900s for 15m), regex fallback support, and empty-lake degradation.

2. Overall design:
   Uses pytest and FastAPI TestClient to verify:
     - GET /api/v1/options/candles?resolution=1m returns raw 1m bars from v_candles_options.
     - GET /api/v1/options/candles?resolution=5m returns aggregated bars spaced at 300s intervals
       with mathematically exact open, high, low, close, and volume matching the constituent 1m bars.
     - GET /api/v1/options/candles?resolution=15m returns aggregated bars spaced at 900s intervals.
     - Higher timeframes ("3m", "30m", "1h", "4h", "1d") all aggregate cleanly without errors.
     - Regex fallback parsing handles formatted contract identifiers when querying aggregated bars.
     - Empty database connections gracefully return zero candles without HTTP 500 exceptions.

3. Elements in the file:
   - TestOptionsMultiTimeframe: Main test suite class covering multi-timeframe option candle aggregation.

4. Final output of the file:
   - Automated pass/fail test execution verifying on-the-fly option candle aggregation.
"""

from typing import Generator

import duckdb
from fastapi.testclient import TestClient

from services.api.deps import get_duckdb
from services.api.main import app


class TestOptionsMultiTimeframe:
    """
    1. The use of class:
       Test suite validating on-the-fly multi-timeframe aggregation for option candlestick series.

    2. What the class contains:
       - setup_method: Initializes TestClient before each test.
       - test_option_candles_1m_resolution: Validates querying raw 1m bars.
       - test_option_candles_5m_aggregation_and_math: Validates 5m bar spacing and exact OHLCV math.
       - test_option_candles_15m_aggregation_spacing: Validates 15m bar spacing (900s intervals).
       - test_option_candles_all_supported_timeframes: Validates all mapped resolutions (3m, 5m, 15m, 30m, 1h, 4h, 1d).
       - test_option_candles_fallback_regex_multi_timeframe: Validates regex fallback extraction with aggregation.
       - test_option_candles_empty_lake_fallback: Validates zero-exception degradation on empty in-memory lake.

    3. Technologies used and why:
       pytest for test orchestration, FastAPI TestClient for ASGI API simulation, DuckDB in-memory mock for fallback.

    4. Key design and overall design of the class:
       Enforces data integrity, temporal consistency, and algebraic accuracy of on-the-fly DuckDB aggregation.
    """

    def setup_method(self) -> None:
        """
        1. The use of function:
           Initializes TestClient before each test method execution.

        2. How does the specific function work:
           Constructs a TestClient instance bound to the FastAPI gateway application.

        3. Concepts used in the function:
           Test fixture initialization.

        4. Places where this function is imported and used:
           Invoked automatically by pytest runner before each test method.

        5. Final output of the function, before and after:
           Before: Uninitialized self.client. After: self.client ready for HTTP requests.
        """
        self.client = TestClient(app)

    def test_option_candles_1m_resolution(self) -> None:
        """
        1. The use of function:
           Validates that requesting resolution '1m' retrieves raw unaggregated 1m bars from v_candles_options.

        2. How does the specific function work:
           Sends GET /api/v1/options/candles with contract_id and resolution=1m. Asserts HTTP 200, matching
           resolution metadata, non-empty bars, chronological monotonicity, and valid OHLC bounds.

        3. Concepts used in the function:
           Raw 1m candlestick query, chronological timestamp ordering, OHLC price relationship invariants.

        4. Places where this function is imported and used:
           Run by pytest test runner under Task 1 verification suite.

        5. Final output of the function, before and after:
           Before: Unverified 1m option candles endpoint. After: Confirmed raw 1m candlestick integrity.
        """
        contract_id = "NIFTY_2025-01-02_22150.00_PE"
        response = self.client.get(f"/api/v1/options/candles?contract_id={contract_id}&resolution=1m&limit=100")
        assert response.status_code == 200
        data = response.json()

        assert data["contract_id"] == contract_id
        assert data["resolution"] == "1m"
        candles = data["candles"]
        assert len(candles) > 0

        for i in range(len(candles) - 1):
            assert candles[i]["time"] < candles[i + 1]["time"], "Candles must be strictly monotonic"

        for c in candles:
            assert c["high"] >= c["low"]
            assert c["high"] >= c["open"]
            assert c["high"] >= c["close"]
            assert c["low"] <= c["open"]
            assert c["low"] <= c["close"]
            assert c["volume"] >= 0

    def test_option_candles_5m_aggregation_and_math(self) -> None:
        """
        1. The use of function:
           Validates on-the-fly 5m aggregation, asserting 300-second temporal spacing and bit-for-bit
           OHLCV aggregation matching constituent 1-minute bars.

        2. How does the specific function work:
           - Requests 5m aggregated bars for contract NIFTY_2025-01-02_22150.00_PE.
           - Confirms consecutive bars in the continuous trading session are spaced by 300 seconds.
           - Queries raw 1m bars covering the exact 5-minute window of the first aggregated bar.
           - Asserts exact OHLCV mathematical equivalence:
             * 5m open equals the first 1m bar's open.
             * 5m close equals the last 1m bar's close.
             * 5m high equals max of constituent 1m highs.
             * 5m low equals min of constituent 1m lows.
             * 5m volume equals sum of constituent 1m volumes.

        3. Concepts used in the function:
           DuckDB time_bucket temporal bucketing, arg_min/arg_max stateful aggregation, constituent bar parity.

        4. Places where this function is imported and used:
           Run by pytest test runner under Task 1 verification suite.

        5. Final output of the function, before and after:
           Before: Unverified 5m aggregation. After: Confirmed 300s spacing and exact OHLCV aggregation math.
        """
        contract_id = "NIFTY_2025-01-02_22150.00_PE"
        res_5m = self.client.get(f"/api/v1/options/candles?contract_id={contract_id}&resolution=5m&limit=20")
        assert res_5m.status_code == 200
        data_5m = res_5m.json()

        assert data_5m["contract_id"] == contract_id
        assert data_5m["resolution"] == "5m"
        candles_5m = data_5m["candles"]
        assert len(candles_5m) >= 5

        for i in range(len(candles_5m) - 1):
            diff = candles_5m[i + 1]["time"] - candles_5m[i]["time"]
            assert diff == 300 or diff > 300, "5m bars must be spaced by at least 300s"
            if diff <= 600:
                assert diff == 300, f"Consecutive intraday 5m bars must have 300s delta, got {diff}"

        first_5m = candles_5m[0]
        start_ts = first_5m["time"]
        end_ts = start_ts + 240

        res_1m = self.client.get(
            f"/api/v1/options/candles?contract_id={contract_id}&resolution=1m&from_ts={start_ts}&to_ts={end_ts}&limit=10"
        )
        assert res_1m.status_code == 200
        candles_1m = res_1m.json()["candles"]
        assert len(candles_1m) == 5, f"Expected 5 constituent 1m bars for 5m window, got {len(candles_1m)}"

        expected_open = candles_1m[0]["open"]
        expected_close = candles_1m[-1]["close"]
        expected_high = max(c["high"] for c in candles_1m)
        expected_low = min(c["low"] for c in candles_1m)
        expected_volume = sum(c["volume"] for c in candles_1m)

        assert first_5m["open"] == expected_open, f"Open mismatch: {first_5m['open']} vs {expected_open}"
        assert first_5m["close"] == expected_close, f"Close mismatch: {first_5m['close']} vs {expected_close}"
        assert first_5m["high"] == expected_high, f"High mismatch: {first_5m['high']} vs {expected_high}"
        assert first_5m["low"] == expected_low, f"Low mismatch: {first_5m['low']} vs {expected_low}"
        assert first_5m["volume"] == expected_volume, f"Volume mismatch: {first_5m['volume']} vs {expected_volume}"

    def test_option_candles_15m_aggregation_spacing(self) -> None:
        """
        1. The use of function:
           Validates on-the-fly 15m aggregation, asserting 900-second temporal spacing and valid OHLC invariants.

        2. How does the specific function work:
           - Requests 15m aggregated bars for contract NIFTY_2025-01-02_22150.00_PE.
           - Asserts HTTP 200, matching metadata, and non-empty candle bars.
           - Verifies consecutive bars in the continuous trading session are spaced by 900 seconds.
           - Asserts OHLC price relationship invariants and positive volume.

        3. Concepts used in the function:
           Multi-timeframe 15m temporal aggregation, session spacing verification, OHLC consistency.

        4. Places where this function is imported and used:
           Run by pytest test runner under Task 1 verification suite.

        5. Final output of the function, before and after:
           Before: Unverified 15m aggregation. After: Confirmed 900s spacing and valid OHLC series.
        """
        contract_id = "NIFTY_2025-01-02_22150.00_PE"
        res_15m = self.client.get(f"/api/v1/options/candles?contract_id={contract_id}&resolution=15m&limit=10")
        assert res_15m.status_code == 200
        data_15m = res_15m.json()

        assert data_15m["contract_id"] == contract_id
        assert data_15m["resolution"] == "15m"
        candles_15m = data_15m["candles"]
        assert len(candles_15m) >= 3

        for i in range(len(candles_15m) - 1):
            diff = candles_15m[i + 1]["time"] - candles_15m[i]["time"]
            assert diff == 900 or diff > 900, "15m bars must be spaced by at least 900s"
            if diff <= 1800:
                assert diff == 900, f"Consecutive intraday 15m bars must have 900s delta, got {diff}"

        for c in candles_15m:
            assert c["high"] >= c["low"]
            assert c["high"] >= c["open"]
            assert c["high"] >= c["close"]
            assert c["low"] <= c["open"]
            assert c["low"] <= c["close"]
            assert c["volume"] >= 0

    def test_option_candles_all_supported_timeframes(self) -> None:
        """
        1. The use of function:
           Validates that all supported higher timeframes (3m, 5m, 15m, 30m, 1h, 4h, 1d) execute cleanly.

        2. How does the specific function work:
           Iterates through each supported resolution, executing GET /api/v1/options/candles.
           Asserts HTTP 200, matching resolution in response, non-empty bars, and valid OHLC invariants.

        3. Concepts used in the function:
           Resolution matrix verification, temporal aggregation coverage, schema compliance.

        4. Places where this function is imported and used:
           Run by pytest test runner under Task 1 verification suite.

        5. Final output of the function, before and after:
           Before: Unverified higher timeframes. After: Confirmed 100% operational coverage across all resolutions.
        """
        contract_id = "NIFTY_2025-01-02_22150.00_PE"
        resolutions = ["3m", "5m", "15m", "30m", "1h", "4h", "1d"]

        for res in resolutions:
            response = self.client.get(f"/api/v1/options/candles?contract_id={contract_id}&resolution={res}&limit=5")
            assert response.status_code == 200, f"Resolution {res} failed with status {response.status_code}"
            data = response.json()
            assert data["resolution"] == res
            candles = data["candles"]
            assert len(candles) > 0, f"Resolution {res} returned 0 candles"
            for c in candles:
                assert c["high"] >= c["low"]
                assert c["high"] >= c["open"]
                assert c["high"] >= c["close"]
                assert c["low"] <= c["open"]
                assert c["low"] <= c["close"]
                assert c["volume"] >= 0

    def test_option_candles_fallback_regex_multi_timeframe(self) -> None:
        """
        1. The use of function:
           Validates regex fallback query logic when requesting aggregated higher timeframe bars.

        2. How does the specific function work:
           Sends GET /api/v1/options/candles with a hyphen-delimited contract ID (NIFTY-2025-01-02-22150-PE)
           which fails direct contract_id match but triggers regex extraction of symbol, expiry, strike,
           and option_type, returning aggregated 5m bars.

        3. Concepts used in the function:
           Regex parsing fallback, query plan resilience, multi-timeframe aggregation in fallback path.

        4. Places where this function is imported and used:
           Run by pytest test runner under Task 1 verification suite.

        5. Final output of the function, before and after:
           Before: Unverified fallback regex aggregation. After: Confirmed regex fallback returns aggregated bars.
        """
        alt_contract_id = "NIFTY-2025-01-02-22150-PE"
        response = self.client.get(
            f"/api/v1/options/candles?contract_id={alt_contract_id}&resolution=5m&limit=10"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["resolution"] == "5m"
        assert len(data["candles"]) > 0
        assert data["strike"] == 22150.0
        assert data["option_type"] == "PE"

    def test_option_candles_empty_lake_fallback(self) -> None:
        """
        1. The use of function:
           Validates graceful zero-exception degradation when querying aggregated candles against an empty lake.

        2. How does the specific function work:
           Overrides the get_duckdb dependency with an empty in-memory DuckDB connection lacking
           v_candles_options. Queries resolution=5m and asserts HTTP 200 with an empty candle list
           rather than an HTTP 500 error.

        3. Concepts used in the function:
           Dependency injection overriding, graceful failure degradation, fault tolerance.

        4. Places where this function is imported and used:
           Run by pytest test runner under Task 1 verification suite.

        5. Final output of the function, before and after:
           Before: Unverified empty-lake behavior. After: Confirmed graceful empty-list response.
        """
        empty_conn = duckdb.connect(":memory:")

        def override_get_duckdb() -> Generator[duckdb.DuckDBPyConnection, None, None]:
            yield empty_conn

        app.dependency_overrides[get_duckdb] = override_get_duckdb
        try:
            client = TestClient(app)
            response = client.get(
                "/api/v1/options/candles?contract_id=NIFTY_2025-01-02_22150.00_PE&resolution=5m&limit=10"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["candles"] == []
            assert data["resolution"] == "5m"
        finally:
            app.dependency_overrides.pop(get_duckdb, None)
            empty_conn.close()
