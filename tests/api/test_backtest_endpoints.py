"""
1. What this file does:
   Automated verification test suite for Milestone M6-04, M6-07, M6-08, and M6-09
   (Backtest Runner, Status, Cancel, and Strategy Catalog API).
   Validates strategy discovery, synchronous backtest execution, performance metrics calculation,
   mark-to-market equity curves, itemized trade records, TradingView Lightweight Charts overlay markers,
   parameter validation errors (HTTP 422, HTTP 400), status tracking, and cancellation commands.

2. Overall design:
   Uses pytest and FastAPI TestClient under Release Gate G4:
     - GET /api/v1/backtest/strategies: Verifies discovery of registered strategies including
       LongCETrendFollowing and BullCallSpreadStrategy with default parameter schemas.
     - POST /api/v1/backtest/run: Verifies deterministic backtest simulation generating valid metrics,
       chronological equity curves, closed trade logs, and paired entry/exit chart markers.
     - Validates boundary rejections: negative capital (HTTP 422), zero lots (HTTP 422),
       unregistered strategy (HTTP 400), and inverted date ranges (HTTP 400).
     - GET /api/v1/backtest/status/{run_id}: Verifies status inquiry for completed and missing runs.
     - POST /api/v1/backtest/cancel/{run_id}: Verifies run cancellation and state transitions.

3. Elements in the file:
   - TestBacktestEndpoints: Primary test class containing 12 automated test cases.

4. Final output of the file:
   - Executable pytest test suite tagged with @pytest.mark.gate_g4.
"""

import pytest
from fastapi.testclient import TestClient

from services.api.main import app
from services.api.routers.backtest import get_backtest_job_store


@pytest.mark.gate_g4
class TestBacktestEndpoints:
    """
    1. The use of class:
       Test suite verifying backtest launch, execution, status, cancellation, and strategy discovery.

    2. What the class contains:
       - test_backtest_strategies_catalog: Validates /api/v1/backtest/strategies catalog.
       - test_backtest_run_success: Validates /api/v1/backtest/run executing cleanly with metrics and markers.
       - test_backtest_run_validation_negative_capital_422: Validates HTTP 422 on negative capital.
       - test_backtest_run_validation_zero_capital_422: Validates HTTP 422 on zero capital.
       - test_backtest_run_validation_invalid_lots_422: Validates HTTP 422 on lots < 1.
       - test_backtest_run_unknown_strategy_400: Validates HTTP 400 on unregistered strategy ID.
       - test_backtest_run_invalid_date_order_400: Validates HTTP 400 when start_date > end_date.
       - test_backtest_status_query_completed: Validates /api/v1/backtest/status/{run_id} for finished run.
       - test_backtest_status_unknown_run_404: Validates HTTP 404 for unrecognized run ID.
       - test_backtest_cancel_registered_run: Validates /api/v1/backtest/cancel/{run_id} transitions to CANCELLED.
       - test_backtest_cancel_unregistered_run: Validates cancel handling on new run ID.
       - test_backtest_multileg_strategy_run: Validates multi-leg strategy execution.

    3. Technologies used and why:
       pytest for test orchestration, FastAPI TestClient for in-memory ASGI dispatch.

    4. Key design and overall design of the class:
       Enforces Gate G4 compliance for backtest execution and auditing requirements.
    """

    def setup_method(self) -> None:
        """
        1. The use of function:
           Initializes TestClient and resets job store before each test.

        2. How does the specific function work:
           Constructs a TestClient instance bound to the FastAPI application and clears _RUN_STORE.

        3. Concepts used in the function:
           Test isolation, fixture setup.

        4. Places where this function is imported and used:
           Invoked automatically by pytest prior to each test method.

        5. Final output of the function, before and after:
           Before: Uninitialized client. After: Ready TestClient and clean job store.
        """
        self.client = TestClient(app)
        get_backtest_job_store().clear()

    def test_backtest_strategies_catalog(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/backtest/strategies returns registered strategies with metadata.

        2. How does the specific function work:
           - Sends GET request to /api/v1/backtest/strategies.
           - Asserts status code is 200.
           - Checks that LongCETrendFollowing and BullCallSpreadStrategy are present in the list.
           - Validates metadata fields: id, name, description, version, author, and default_params.
           - Confirms default_params for LongCETrendFollowing contains fast_period and slow_period.

        3. Concepts used in the function:
           Strategy discovery, schema reflection.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Unverified endpoint. After: Confirmed strategy catalog with schema defaults.
        """
        response = self.client.get("/api/v1/backtest/strategies")
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2

        strategy_map = {item["id"]: item for item in data}
        assert "LongCETrendFollowing" in strategy_map
        assert "BullCallSpreadStrategy" in strategy_map

        ce_strat = strategy_map["LongCETrendFollowing"]
        assert ce_strat["name"] == "LongCETrendFollowing"
        assert len(ce_strat["description"]) > 0
        assert "fast_period" in ce_strat["default_params"]
        assert ce_strat["default_params"]["fast_period"] == 9
        assert ce_strat["default_params"]["slow_period"] == 21

    def test_backtest_run_success(self) -> None:
        """
        1. The use of function:
           Verifies POST /api/v1/backtest/run executes cleanly and produces full result payload.

        2. How does the specific function work:
           - Sends POST payload configuring a single-leg LongCETrendFollowing backtest.
           - Asserts HTTP 200 response with status 'COMPLETED'.
           - Verifies metrics tear-sheet contains win_rate_pct, max_drawdown_pct, total_trades, net_pnl_rupees.
           - Verifies equity_curve has non-empty list of points with time, equity, cash, drawdown.
           - Verifies trades has itemized trade records with gross_pnl_rupees, fees_rupees, net_pnl_rupees.
           - Verifies chart_markers has paired entry ('arrowUp', 'belowBar', '#26a69a') and exit markers.

        3. Concepts used in the function:
           End-to-end backtest execution, financial reconciliation, TradingView marker generation.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Request payload. After: Verified BacktestRunResponse with metrics and markers.
        """
        payload = {
            "strategy_id": "LongCETrendFollowing",
            "start_date": "2025-01-02",
            "end_date": "2025-01-02",
            "initial_capital_rupees": 500000.0,
            "mode": "UNDERLYING_DIRECTIONAL",
            "intrabar_stop_policy": "STOP_FIRST",
            "lots": 1,
            "strategy_params": {"fast_period": 9, "slow_period": 21},
        }
        response = self.client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["run_id"].startswith("run_")
        assert data["status"] == "COMPLETED"
        assert data["strategy_id"] == "LongCETrendFollowing"
        assert data["mode"] == "UNDERLYING_DIRECTIONAL"
        assert data["execution_time_ms"] > 0

        # Verify quantitative metrics summary
        metrics = data["metrics"]
        assert "total_trades" in metrics
        assert metrics["total_trades"] >= 1
        assert "win_rate_pct" in metrics
        assert "max_drawdown_pct" in metrics
        assert "net_pnl_rupees" in metrics

        # Verify mark-to-market equity curve
        equity_curve = data["equity_curve"]
        assert len(equity_curve) > 0
        first_pt = equity_curve[0]
        assert "time" in first_pt
        assert "equity" in first_pt
        assert "cash" in first_pt
        assert "drawdown" in first_pt
        assert first_pt["equity"] > 0

        # Verify trade records
        trades = data["trades"]
        assert len(trades) >= 1
        trade = trades[0]
        assert trade["trade_id"].startswith("TRD-")
        assert trade["entry_time"] > 0
        assert trade["exit_time"] >= trade["entry_time"]
        assert trade["quantity"] == 65
        assert trade["entry_price"] > 0
        assert trade["exit_price"] > 0
        assert "gross_pnl_rupees" in trade
        assert "fees_rupees" in trade
        assert "net_pnl_rupees" in trade
        assert "pnl_pct" in trade
        assert len(trade["exit_reason"]) > 0

        # Verify TradingView Lightweight Charts overlay markers
        markers = data["chart_markers"]
        assert len(markers) >= 2
        entry_marker = markers[0]
        exit_marker = markers[1]

        assert entry_marker["position"] == "belowBar"
        assert entry_marker["shape"] == "arrowUp"
        assert entry_marker["color"] == "#26a69a"
        assert "BUY" in entry_marker["text"]

        assert exit_marker["position"] == "aboveBar"
        assert exit_marker["shape"] == "arrowDown"
        assert exit_marker["color"] == "#ef5350"
        assert "EXIT" in exit_marker["text"]

    def test_backtest_run_validation_negative_capital_422(self) -> None:
        """
        1. The use of function:
           Verifies POST /api/v1/backtest/run rejects negative capital with HTTP 422.

        2. How does the specific function work:
           Sends payload with initial_capital_rupees = -50000.0, asserting HTTP 422.

        3. Concepts used in the function:
           Pydantic input boundary validation.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Invalid payload. After: Confirmed HTTP 422 Unprocessable Entity.
        """
        payload = {
            "strategy_id": "LongCETrendFollowing",
            "start_date": "2025-01-02",
            "end_date": "2025-01-02",
            "initial_capital_rupees": -50000.0,
        }
        response = self.client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 422, response.text

    def test_backtest_run_validation_zero_capital_422(self) -> None:
        """
        1. The use of function:
           Verifies POST /api/v1/backtest/run rejects zero capital with HTTP 422.

        2. How does the specific function work:
           Sends payload with initial_capital_rupees = 0.0, asserting HTTP 422.

        3. Concepts used in the function:
           Pydantic strict gt=0 constraint enforcement.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Invalid zero capital. After: Confirmed HTTP 422.
        """
        payload = {
            "strategy_id": "LongCETrendFollowing",
            "start_date": "2025-01-02",
            "end_date": "2025-01-02",
            "initial_capital_rupees": 0.0,
        }
        response = self.client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 422, response.text

    def test_backtest_run_validation_invalid_lots_422(self) -> None:
        """
        1. The use of function:
           Verifies POST /api/v1/backtest/run rejects non-positive lot multipliers with HTTP 422.

        2. How does the specific function work:
           Sends payload with lots = 0, asserting HTTP 422.

        3. Concepts used in the function:
           Lot sizing constraint validation.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Invalid lots value. After: Confirmed HTTP 422.
        """
        payload = {
            "strategy_id": "LongCETrendFollowing",
            "start_date": "2025-01-02",
            "end_date": "2025-01-02",
            "initial_capital_rupees": 500000.0,
            "lots": 0,
        }
        response = self.client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 422, response.text

    def test_backtest_run_unknown_strategy_400(self) -> None:
        """
        1. The use of function:
           Verifies POST /api/v1/backtest/run returns HTTP 400 for unregistered strategy names.

        2. How does the specific function work:
           Sends payload with strategy_id = 'NonExistentStrategy123', asserting HTTP 400.

        3. Concepts used in the function:
           Strategy catalog validation.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Unregistered strategy request. After: Confirmed HTTP 400 Bad Request.
        """
        payload = {
            "strategy_id": "NonExistentStrategy123",
            "start_date": "2025-01-02",
            "end_date": "2025-01-02",
            "initial_capital_rupees": 500000.0,
        }
        response = self.client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 400, response.text
        assert "not registered" in response.json()["detail"].lower()

    def test_backtest_run_invalid_date_order_400(self) -> None:
        """
        1. The use of function:
           Verifies POST /api/v1/backtest/run returns HTTP 400 when start_date is after end_date.

        2. How does the specific function work:
           Sends payload with start_date = '2025-01-10' and end_date = '2025-01-01', asserting HTTP 400.

        3. Concepts used in the function:
           Temporal ordering validation.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Inverted date range. After: Confirmed HTTP 400 Bad Request.
        """
        payload = {
            "strategy_id": "LongCETrendFollowing",
            "start_date": "2025-01-10",
            "end_date": "2025-01-01",
            "initial_capital_rupees": 500000.0,
        }
        response = self.client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 400, response.text
        assert "start_date" in response.json()["detail"].lower()

    def test_backtest_status_query_completed(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/backtest/status/{run_id} returns execution status for completed run.

        2. How does the specific function work:
           - Launches a run via POST /api/v1/backtest/run and extracts run_id.
           - Queries GET /api/v1/backtest/status/{run_id}.
           - Asserts HTTP 200, status == 'COMPLETED', and embedded result presence.

        3. Concepts used in the function:
           Job status inquiry, response verification.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Active run ID. After: Confirmed status endpoint response.
        """
        payload = {
            "strategy_id": "LongCETrendFollowing",
            "start_date": "2025-01-02",
            "end_date": "2025-01-02",
            "initial_capital_rupees": 500000.0,
        }
        run_resp = self.client.post("/api/v1/backtest/run", json=payload)
        assert run_resp.status_code == 200, run_resp.text
        run_id = run_resp.json()["run_id"]

        status_resp = self.client.get(f"/api/v1/backtest/status/{run_id}")
        assert status_resp.status_code == 200, status_resp.text
        status_data = status_resp.json()
        assert status_data["run_id"] == run_id
        assert status_data["status"] == "COMPLETED"
        assert status_data["result"] is not None
        assert status_data["result"]["run_id"] == run_id

    def test_backtest_status_unknown_run_404(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/backtest/status/{run_id} returns HTTP 404 for non-existent run ID.

        2. How does the specific function work:
           Sends GET request for 'run_non_existent_999999', asserting HTTP 404.

        3. Concepts used in the function:
           Missing resource error handling.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Non-existent run query. After: Confirmed HTTP 404 Not Found.
        """
        response = self.client.get("/api/v1/backtest/status/run_non_existent_999999")
        assert response.status_code == 404, response.text
        assert "not found" in response.json()["detail"].lower()

    def test_backtest_cancel_registered_run(self) -> None:
        """
        1. The use of function:
           Verifies POST /api/v1/backtest/cancel/{run_id} transitions a known run to CANCELLED.

        2. How does the specific function work:
           - Launches run via POST /api/v1/backtest/run and obtains run_id.
           - Calls POST /api/v1/backtest/cancel/{run_id}.
           - Asserts HTTP 200 and status == 'CANCELLED'.
           - Queries GET /api/v1/backtest/status/{run_id} to verify persisted CANCELLED state.

        3. Concepts used in the function:
           Run cancellation command pattern, state mutation verification.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Completed/active run. After: Confirmed cancellation transition.
        """
        payload = {
            "strategy_id": "LongCETrendFollowing",
            "start_date": "2025-01-02",
            "end_date": "2025-01-02",
            "initial_capital_rupees": 500000.0,
        }
        run_resp = self.client.post("/api/v1/backtest/run", json=payload)
        assert run_resp.status_code == 200, run_resp.text
        run_id = run_resp.json()["run_id"]

        cancel_resp = self.client.post(f"/api/v1/backtest/cancel/{run_id}")
        assert cancel_resp.status_code == 200, cancel_resp.text
        cancel_data = cancel_resp.json()
        assert cancel_data["run_id"] == run_id
        assert cancel_data["status"] == "CANCELLED"

        # Verify state persistence in status query
        status_resp = self.client.get(f"/api/v1/backtest/status/{run_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "CANCELLED"

    def test_backtest_cancel_unregistered_run(self) -> None:
        """
        1. The use of function:
           Verifies POST /api/v1/backtest/cancel/{run_id} gracefully records cancellation for new ID.

        2. How does the specific function work:
           Sends cancel request for arbitrary new run_id, asserting HTTP 200 and status == 'CANCELLED'.

        3. Concepts used in the function:
           Idempotent cancellation handling.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Unregistered run ID. After: Confirmed CANCELLED response.
        """
        response = self.client.post("/api/v1/backtest/cancel/run_unregistered_test_123")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["run_id"] == "run_unregistered_test_123"
        assert data["status"] == "CANCELLED"

    def test_backtest_multileg_strategy_run(self) -> None:
        """
        1. The use of function:
           Verifies POST /api/v1/backtest/run executes cleanly for multi-leg strategies.

        2. How does the specific function work:
           - Sends backtest request for BullCallSpreadStrategy.
           - Asserts HTTP 200 and status == 'COMPLETED'.
           - Verifies valid equity_curve and metrics structure.

        3. Concepts used in the function:
           Multi-leg backtest execution compatibility.

        4. Places where this function is imported and used:
           Executed by pytest test runner.

        5. Final output of the function, before and after:
           Before: Multi-leg backtest request. After: Verified HTTP 200 response.
        """
        payload = {
            "strategy_id": "BullCallSpreadStrategy",
            "start_date": "2025-01-02",
            "end_date": "2025-01-02",
            "initial_capital_rupees": 1000000.0,
            "mode": "UNDERLYING_DIRECTIONAL",
            "lots": 1,
        }
        response = self.client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "COMPLETED"
        assert data["strategy_id"] == "BullCallSpreadStrategy"
        assert len(data["equity_curve"]) > 0
        assert "metrics" in data
