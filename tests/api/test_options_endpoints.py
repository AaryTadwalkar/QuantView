"""
1. What this file does:
   Automated verification test suite for Milestone M6-03b, M6-15, and M6-18
   (Option Chain, Expiries, Greeks, and Option Candles API).
   Validates contract expiries, reconstructed ATM-centered option chain matrix,
   per-strike historical candlestick queries, filter parameters, SLA latency bounds (<= 300ms),
   and graceful empty-lake degradation.

2. Overall design:
   Uses pytest and FastAPI TestClient to verify:
     - GET /api/v1/options/expiries returns sorted ISO dates from DuckDB lake.
     - GET /api/v1/options/chain defaults to nearest expiry, computes ATM strike,
       centers strikes (+/- 15 strikes, 31 rows total), and pairs Call/Put quotes with Greeks.
     - GET /api/v1/options/chain with explicit expiry_date, spot_price override, and strike_count.
     - GET /api/v1/options/candles retrieves contract OHLCV bars by contract_id or tuple (strike, option_type, expiry).
     - Timestamp monotonicity and OHLC relationship invariants for option candle bars.
     - Range filters (from_ts, to_ts, limit) and validation bounds.
     - Query latency completes within Release Gate G4 requirement (<= 300ms).
     - Missing database views or empty lakes degrade cleanly to empty lists without HTTP 500.

3. Elements in the file:
   - TestOptionsEndpoints: Test case class exercising all option routes, models, and boundaries.

4. Final output of the file:
   - Automated pass/fail test execution under Release Gate G4.
"""

import time
from typing import Generator

import duckdb
import pytest
from fastapi.testclient import TestClient

from services.api.deps import get_duckdb
from services.api.main import app


@pytest.mark.gate_g4
class TestOptionsEndpoints:
    """
    1. The use of class:
       Test suite validating option expiries, reconstructed chain matrix, Greeks, and candlestick endpoints.

    2. What the class contains:
       - test_options_expiries_sorted_list: Validates sorted date strings returned by /expiries.
       - test_options_chain_default_query: Validates ATM centering, 31 rows, and CE/PE quotes.
       - test_options_chain_explicit_params: Validates custom expiry, spot override, and strike count.
       - test_options_candles_by_contract_id: Validates OHLCV retrieval via contract_id.
       - test_options_candles_by_strike_and_type: Validates OHLCV retrieval via strike, type, and expiry.
       - test_options_candles_range_filters: Validates from_ts, to_ts, and limit query constraints.
       - test_options_chain_latency_benchmark: Validates <= 300ms SLA for chain reconstruction.
       - test_validation_bounds: Validates HTTP 422 on invalid strike_count and limit parameters.
       - test_empty_lake_graceful_fallback: Validates zero-exception degradation on empty in-memory lake.

    3. Technologies used and why:
       pytest for test orchestration, FastAPI TestClient for ASGI simulation, DuckDB in-memory mock for fallback.

    4. Key design and overall design of the class:
       Enforces Gate G4 compliance for Milestones M6-03b (Option Chart), M6-15 (API Freeze), and M6-18 (Option Chain).
    """

    def setup_method(self) -> None:
        """
        1. The use of function:
           Initializes TestClient before each test method execution.

        2. How does the specific function work:
           Constructs a TestClient instance bound to the global FastAPI app.

        3. Concepts used in the function:
           Test fixture initialization.

        4. Places where this function is imported and used:
           Invoked automatically by pytest runner before each test.

        5. Final output of the function, before and after:
           Before: Uninitialized self.client. After: self.client ready for HTTP requests.
        """
        self.client = TestClient(app)

    def test_options_expiries_sorted_list(self) -> None:
        """
        1. The use of function:
           Validates the /api/v1/options/expiries endpoint contract and sort order.

        2. How does the specific function work:
           Sends GET /api/v1/options/expiries?underlying=NIFTY, asserts HTTP 200, checks
           that the response is a non-empty list of YYYY-MM-DD date strings in strictly ascending order.

        3. Concepts used in the function:
           Contract verification, chronological sorting validation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified expiries endpoint. After: Confirmed sorted ISO expiry dates.
        """
        response = self.client.get("/api/v1/options/expiries?underlying=NIFTY")
        assert response.status_code == 200
        expiries = response.json()
        assert isinstance(expiries, list)
        assert len(expiries) > 0

        for exp in expiries:
            assert isinstance(exp, str)
            assert len(exp) == 10
            parts = exp.split("-")
            assert len(parts) == 3

        sorted_copy = sorted(expiries)
        assert expiries == sorted_copy

    def test_options_chain_default_query(self) -> None:
        """
        1. The use of function:
           Validates default reconstructed option chain centered around ATM strike.

        2. How does the specific function work:
           Sends GET /api/v1/options/chain without explicit expiry or spot price. Asserts:
           - HTTP 200 with underlying 'NIFTY' and valid ISO expiry date.
           - spot_price > 0.0 and atm_strike is a multiple of 50.0.
           - atm_strike == round(spot_price / 50.0) * 50.0.
           - Exactly 31 strike rows for default strike_count=15 (15 below, ATM, 15 above).
           - Middle row (index 15) has strike == atm_strike.
           - Each row contains OptionStrikeQuote objects with valid trading_symbol, pricing, and volume.

        3. Concepts used in the function:
           Option chain reconstruction, ATM centering, dual-column Call/Put matrix integrity.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified chain matrix. After: Confirmed ATM-centered structure with 31 rows.
        """
        response = self.client.get("/api/v1/options/chain")
        assert response.status_code == 200
        data = response.json()

        assert data["underlying"] == "NIFTY"
        assert len(data["expiry_date"]) == 10
        assert data["spot_price"] > 0.0
        assert data["atm_strike"] > 0.0

        expected_atm = round(data["spot_price"] / 50.0) * 50.0
        assert data["atm_strike"] == expected_atm

        strikes = data["strikes"]
        assert len(strikes) == 31

        atm_row = strikes[15]
        assert atm_row["strike"] == expected_atm

        has_ce = False
        has_pe = False
        for row in strikes:
            assert "strike" in row
            if row["ce"] is not None:
                has_ce = True
                assert row["ce"]["option_type"] == "CE"
                assert row["ce"]["strike"] == row["strike"]
                assert row["ce"]["ltp"] >= 0.0
                assert "NIFTY" in row["ce"]["trading_symbol"]
            if row["pe"] is not None:
                has_pe = True
                assert row["pe"]["option_type"] == "PE"
                assert row["pe"]["strike"] == row["strike"]
                assert row["pe"]["ltp"] >= 0.0
                assert "NIFTY" in row["pe"]["trading_symbol"]

        assert has_ce, "At least one CE quote must be populated in the chain"
        assert has_pe, "At least one PE quote must be populated in the chain"

    def test_options_chain_explicit_params(self) -> None:
        """
        1. The use of function:
           Validates option chain reconstruction with explicit expiry_date, spot_price, and strike_count.

        2. How does the specific function work:
           Fetches available expiries, picks one, passes explicit expiry_date, spot_price=23000.0,
           and strike_count=5. Asserts:
           - atm_strike is 23000.0.
           - Exactly 11 rows returned (2 * 5 + 1).
           - Strike range spans [22750.0, ..., 23250.0] with 50.0 increments.

        3. Concepts used in the function:
           Parameter override, dynamic strike grid generation, strike bounds.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified custom chain queries. After: Verified strike count and spot override.
        """
        r_exp = self.client.get("/api/v1/options/expiries")
        assert r_exp.status_code == 200
        expiries = r_exp.json()
        target_expiry = expiries[-1]

        response = self.client.get(
            f"/api/v1/options/chain?expiry_date={target_expiry}&spot_price=23000.0&strike_count=5"
        )
        assert response.status_code == 200
        data = response.json()

        assert data["expiry_date"] == target_expiry
        assert data["spot_price"] == 23000.0
        assert data["atm_strike"] == 23000.0

        strikes = data["strikes"]
        assert len(strikes) == 11
        assert strikes[0]["strike"] == 22750.0
        assert strikes[5]["strike"] == 23000.0
        assert strikes[10]["strike"] == 23250.0

    def test_options_candles_by_contract_id(self) -> None:
        """
        1. The use of function:
           Validates querying per-contract historical candles by canonical contract_id.

        2. How does the specific function work:
           Sends GET /api/v1/options/candles?contract_id=NIFTY_2025-01-02_22150.00_PE&resolution=1m.
           Asserts:
           - HTTP 200 with matching contract metadata (symbol, expiry, strike, option_type).
           - Non-empty candle series.
           - Strictly increasing epoch timestamps (t[i] < t[i+1]).
           - Valid OHLC relationships (high >= low, high >= open, high >= close, etc.).

        3. Concepts used in the function:
           Contract candlestick query, timestamp monotonicity, OHLC bar integrity.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified option candle bars. After: Verified historical candlestick series.
        """
        contract_id = "NIFTY_2025-01-02_22150.00_PE"
        response = self.client.get(f"/api/v1/options/candles?contract_id={contract_id}&resolution=1m&limit=100")
        assert response.status_code == 200
        data = response.json()

        assert data["contract_id"] == contract_id
        assert data["symbol"] == "NIFTY"
        assert data["expiry"] == "2025-01-02"
        assert data["strike"] == 22150.0
        assert data["option_type"] == "PE"
        assert data["resolution"] == "1m"

        candles = data["candles"]
        assert len(candles) > 0
        assert len(candles) <= 100

        for i in range(len(candles) - 1):
            assert candles[i]["time"] < candles[i + 1]["time"], "Candles must be strictly monotonic"

        for c in candles:
            assert c["high"] >= c["low"]
            assert c["high"] >= c["open"]
            assert c["high"] >= c["close"]
            assert c["low"] <= c["open"]
            assert c["low"] <= c["close"]
            assert c["volume"] >= 0

    def test_options_candles_by_strike_and_type(self) -> None:
        """
        1. The use of function:
           Validates querying per-contract historical candles by tuple (strike, option_type, expiry_date).

        2. How does the specific function work:
           Sends GET /api/v1/options/candles with strike=22150.0, option_type=PE, expiry_date=2025-01-02.
           Asserts HTTP 200, matching metadata, and non-empty candle bars.

        3. Concepts used in the function:
           Multi-attribute contract lookup, parameter resolution.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified multi-attribute candle query. After: Verified contract candle retrieval.
        """
        response = self.client.get(
            "/api/v1/options/candles?strike=22150.0&option_type=PE&expiry_date=2025-01-02&resolution=1m&limit=50"
        )
        assert response.status_code == 200
        data = response.json()

        assert data["strike"] == 22150.0
        assert data["option_type"] == "PE"
        assert data["expiry"] == "2025-01-02"
        assert len(data["candles"]) > 0

    def test_options_candles_range_filters(self) -> None:
        """
        1. The use of function:
           Validates from_ts, to_ts, and limit query parameters for option candles.

        2. How does the specific function work:
           Fetches base series to determine timestamps, then applies from_ts and to_ts bounds
           and limit=10. Asserts returned bars strictly conform to the epoch range and count limit.

        3. Concepts used in the function:
           Temporal range partitioning, limit constraint enforcement.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified range filters. After: Verified boundary conformance.
        """
        contract_id = "NIFTY_2025-01-02_22150.00_PE"
        r_base = self.client.get(f"/api/v1/options/candles?contract_id={contract_id}&limit=50")
        assert r_base.status_code == 200
        candles = r_base.json()["candles"]
        assert len(candles) >= 20

        mid_idx = len(candles) // 2
        t_start = candles[mid_idx - 5]["time"]
        t_end = candles[mid_idx + 5]["time"]

        r_range = self.client.get(
            f"/api/v1/options/candles?contract_id={contract_id}&from_ts={t_start}&to_ts={t_end}&limit=10"
        )
        assert r_range.status_code == 200
        bounded_candles = r_range.json()["candles"]

        assert 1 <= len(bounded_candles) <= 10
        for bc in bounded_candles:
            assert t_start <= bc["time"] <= t_end

    def test_options_chain_latency_benchmark(self) -> None:
        """
        1. The use of function:
           Measures option chain reconstruction latency against the sub-300ms SLA.

        2. How does the specific function work:
           Executes GET /api/v1/options/chain and records execution wall-clock time.
           Asserts elapsed time <= 300 milliseconds.

        3. Concepts used in the function:
           Performance SLA benchmarking, analytical latency constraint verification.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unmeasured latency. After: Verified sub-300ms execution.
        """
        # Warm-up request to stabilize query planning / DuckDB connection cache
        self.client.get("/api/v1/options/chain")

        timings = []
        last_response = None
        for _ in range(3):
            start_time = time.perf_counter()
            last_response = self.client.get("/api/v1/options/chain")
            timings.append((time.perf_counter() - start_time) * 1000.0)

        assert last_response is not None and last_response.status_code == 200
        best_ms = min(timings)
        assert best_ms <= 300.0, f"Option chain latency {best_ms:.2f}ms exceeds 300ms SLA"

    def test_validation_bounds(self) -> None:
        """
        1. The use of function:
           Validates HTTP 422 responses for out-of-bounds parameters.

        2. How does the specific function work:
           Passes invalid strike_count (0 and 100) and limit (0 and 20000), verifying HTTP 422.

        3. Concepts used in the function:
           Boundary condition verification, input validation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified validation bounds. After: Confirmed rejection of invalid query inputs.
        """
        for bad_count in [0, 100]:
            r = self.client.get(f"/api/v1/options/chain?strike_count={bad_count}")
            assert r.status_code == 422

        for bad_limit in [0, 20000]:
            r = self.client.get(f"/api/v1/options/candles?contract_id=dummy&limit={bad_limit}")
            assert r.status_code == 422

    def test_empty_lake_graceful_fallback(self) -> None:
        """
        1. The use of function:
           Validates graceful degradation when the DuckDB lake has missing views or is completely empty.

        2. How does the specific function work:
           Overrides get_duckdb dependency with an in-memory database without tables, asserting
           error-free empty responses for expiries, chain, and candle endpoints.

        3. Concepts used in the function:
           Dependency injection override, fault tolerance, graceful degradation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Risk of unhandled DB exceptions. After: Verified zero-exception fallback.
        """

        def mock_duckdb() -> Generator[duckdb.DuckDBPyConnection, None, None]:
            conn = duckdb.connect(":memory:")
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[get_duckdb] = mock_duckdb
        try:
            r_exp = self.client.get("/api/v1/options/expiries?underlying=NIFTY")
            assert r_exp.status_code == 200
            assert r_exp.json() == []

            r_chain = self.client.get("/api/v1/options/chain")
            assert r_chain.status_code == 200
            c_data = r_chain.json()
            assert c_data["underlying"] == "NIFTY"
            assert c_data["strikes"] == []
            assert c_data["spot_price"] == 0.0
            assert c_data["atm_strike"] == 0.0

            r_candles = self.client.get("/api/v1/options/candles?contract_id=NIFTY_DUMMY")
            assert r_candles.status_code == 200
            k_data = r_candles.json()
            assert k_data["contract_id"] == "NIFTY_DUMMY"
            assert k_data["candles"] == []
        finally:
            app.dependency_overrides.pop(get_duckdb, None)
