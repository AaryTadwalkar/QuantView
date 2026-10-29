"""
1. What this file does:
   Automated contract verification test suite for Milestone M6-06, M6-14, Section 6.1, and Section 6.2
   (Paper Trading Macro/Micro Console, Pre-Trade Risk Policy Inspection, Indian Market Screener,
   and Quantitative Strategy Sensitivity Heatmap).

2. Overall design:
   Uses pytest and FastAPI TestClient under Gate G4 to validate:
     - Paper Trading Macro Strategy Bots catalog (telemetry, operating modes, Sharpe ratio, status).
     - Paper Trading Micro Discretionary Console (account ledger, dynamic equity, free cash, order book, trade logs).
     - Individual position square-off and atomic batch square-off-all action.
     - Pre-trade risk policy inspection parameters (RK-06 freeze 1,800 units, RK-26 ceiling 72 lots, ISOLATED mode).
     - Indian Market Screener data contracts for NSE:NIFTY50, INDIAVIX, and weekly ATM CE/PE option contracts.
     - Quantitative Strategy Sensitivity Heatmap 5x5 matrix structure and monthly returns calendar view.

3. Elements in the file:
   - TestPaperScreenerHeatmapContract: Primary test class containing comprehensive contract verification methods.

4. Final output of the file:
   - Executable pytest test suite tagged with @pytest.mark.gate_g4.
"""

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from services.api.main import app
from services.api.routers.paper import reset_paper_state


@pytest.mark.gate_g4
class TestPaperScreenerHeatmapContract:
    """
    1. The use of class:
       Test suite verifying paper trading macro/micro contracts, risk policies, screener, and heatmaps.

    2. What the class contains:
       - setup_method: Resets simulation state prior to each test case.
       - test_paper_macro_strategy_bots_catalog_contract: Validates macro bot telemetry and operating modes.
       - test_paper_micro_account_balances_and_formulas: Validates account ledger dynamic equity and free cash.
       - test_paper_micro_positions_orders_and_square_off_single: Validates order submission, fill, and single square-off.
       - test_paper_square_off_all_action: Validates atomic liquidation of all open derivative positions.
       - test_risk_policy_inspection_rk06_rk26_isolated: Validates RK-06, RK-26, and ISOLATED allocation parameters.
       - test_screener_data_contracts_nifty_vix_atm_options: Validates Indian market screener rows and fields.
       - test_strategy_sensitivity_heatmap_matrix_structure: Validates 5x5 sensitivity matrix and monthly calendar.

    3. Technologies used and why:
       pytest for test orchestration, FastAPI TestClient for in-memory ASGI dispatch without network latency.

    4. Key design and overall design of the class:
       Enforces Release Gate G4 compliance for M6-06, M6-14, Section 6.1, and Section 6.2 deliverables.
    """

    def setup_method(self) -> None:
        """
        1. The use of function:
           Test fixture resetting the paper simulator state before each test invocation.

        2. How does the specific function work:
           - Calls reset_paper_state() to clear positions, orders, and reset balances.
           - Instantiates a clean FastAPI TestClient bound to app.

        3. Concepts used in the function:
           Test isolation, fixture setup.

        4. Places where this function is imported and used:
           Invoked automatically by pytest before each test method in TestPaperScreenerHeatmapContract.

        5. Final output of the function, before and after:
           Before: Dirty state. After: Clean baseline state and initialized client.
        """
        reset_paper_state()
        self.client = TestClient(app)

    def test_paper_macro_strategy_bots_catalog_contract(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/paper/strategies macro automated strategy bot telemetry contract.

        2. How does the specific function work:
           - Dispatches GET to /api/v1/paper/strategies.
           - Asserts HTTP 200 OK and list of strategy bot records.
           - Verifies essential fields: strategy_id, strategy_name, mode, status, allocated_lots,
             today_pnl_rupees, win_rate_pct, and sharpe_ratio.
           - Verifies operating modes include ACTUAL_OPTIONS and UNDERLYING_DIRECTIONAL.

        3. Concepts used in the function:
           Macro strategy monitoring, automated strategy telemetry.

        4. Places where this function is imported and used:
           Invoked by pytest during gate_g4 test suite execution.

        5. Final output of the function, before and after:
           Before: Unverified macro bots endpoint. After: Confirmed macro bots telemetry contract.
        """
        resp = self.client.get("/api/v1/paper/strategies")
        assert resp.status_code == 200
        strategies = resp.json()
        assert isinstance(strategies, list)
        assert len(strategies) >= 3

        strat_map: Dict[str, Dict[str, Any]] = {s["strategy_id"]: s for s in strategies}
        assert "STRAT-CE-TREND" in strat_map
        ce_trend = strat_map["STRAT-CE-TREND"]
        assert ce_trend["strategy_name"] == "LongCETrendFollowing"
        assert ce_trend["mode"] == "ACTUAL_OPTIONS"
        assert ce_trend["status"] == "Running"
        assert ce_trend["allocated_lots"] == 4
        assert ce_trend["today_pnl_rupees"] == 12450.0
        assert ce_trend["win_rate_pct"] == 64.2
        assert ce_trend["sharpe_ratio"] == 1.85

        assert "STRAT-BULL-SPREAD" in strat_map
        bull_spread = strat_map["STRAT-BULL-SPREAD"]
        assert bull_spread["mode"] == "UNDERLYING_DIRECTIONAL"
        assert bull_spread["status"] == "Warming Up"

    def test_paper_micro_account_balances_and_formulas(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/paper/account and /api/v1/paper/accounts for ACC-MANUAL-PAPER.

        2. How does the specific function work:
           - Dispatches GET to /api/v1/paper/account?account_id=ACC-MANUAL-PAPER.
           - Asserts HTTP 200 and matches ACC-MANUAL-PAPER attributes.
           - Asserts starting capital is ₹1,000,000.0.
           - Confirms the dynamic equity formula: equity == cash_balance + unrealized_pnl.
           - Confirms the free cash formula: free_cash == cash_balance - margin_reserved.

        3. Concepts used in the function:
           Ledger accounting invariants, integer-paise currency representations.

        4. Places where this function is imported and used:
           Invoked by pytest during gate_g4 test suite execution.

        5. Final output of the function, before and after:
           Before: Unverified account balances. After: Confirmed mathematical ledger integrity.
        """
        resp = self.client.get("/api/v1/paper/account?account_id=ACC-MANUAL-PAPER")
        assert resp.status_code == 200
        acc = resp.json()
        assert acc["account_id"] == "ACC-MANUAL-PAPER"
        assert acc["mode"] == "MANUAL_PAPER"
        assert acc["currency"] == "INR"
        assert acc["initial_capital_rupees"] == 1000000.0
        assert acc["cash_balance_rupees"] == 1000000.0
        assert acc["margin_reserved_rupees"] == 0.0
        assert acc["free_cash_rupees"] == 1000000.0
        assert acc["unrealized_pnl_rupees"] == 0.0
        assert acc["realized_pnl_rupees"] == 0.0
        assert acc["equity_rupees"] == 1000000.0

        # Formula checks
        assert acc["equity_rupees"] == acc["cash_balance_rupees"] + acc["unrealized_pnl_rupees"]
        assert acc["free_cash_rupees"] == acc["cash_balance_rupees"] - acc["margin_reserved_rupees"]

    def test_paper_micro_positions_orders_and_square_off_single(self) -> None:
        """
        1. The use of function:
           Verifies discretionary order execution, position opening, and single square-off liquidation.

        2. How does the specific function work:
           - Submits BUY order for 25 units via POST /api/v1/paper/orders.
           - Asserts fill confirmation, chart price lines (entry, stop-loss, take-profit).
           - Queries open positions via GET /api/v1/paper/positions?account_id=ACC-MANUAL-PAPER.
           - Queries order history via GET /api/v1/paper/orders?account_id=ACC-MANUAL-PAPER.
           - Queries trade history via GET /api/v1/paper/trades?account_id=ACC-MANUAL-PAPER and checks statutory fees.
           - Calls POST /api/v1/paper/square-off/{position_id} to close position.
           - Confirms position is liquidated and removed from open positions.

        3. Concepts used in the function:
           Discretionary paper execution, chart lines, position lifecycle, trade audit trail.

        4. Places where this function is imported and used:
           Invoked by pytest during gate_g4 test suite execution.

        5. Final output of the function, before and after:
           Before: Unverified lifecycle flow. After: Confirmed order-position-squareoff lifecycle.
        """
        order_payload = {
            "account_id": "ACC-MANUAL-PAPER",
            "contract_id": "OPT-NIFTY-20250109-23500-CE",
            "side": "BUY",
            "quantity": 25,
            "order_type": "MARKET",
            "stop_loss_pct": 20.0,
            "take_profit_pct": 40.0,
        }
        order_res = self.client.post("/api/v1/paper/orders", json=order_payload)
        assert order_res.status_code == 201
        data = order_res.json()
        assert data["status"] == "FILLED"
        assert data["side"] == "BUY"
        assert data["quantity"] == 25
        assert data["fill_price"] > 0.0
        assert data["chart_lines"]["entry"] == data["fill_price"]
        assert data["chart_lines"]["stop_loss"] < data["fill_price"]
        assert data["chart_lines"]["take_profit"] > data["fill_price"]

        # Verify Positions
        pos_res = self.client.get("/api/v1/paper/positions?account_id=ACC-MANUAL-PAPER")
        assert pos_res.status_code == 200
        positions = pos_res.json()
        assert len(positions) == 1
        pos = positions[0]
        assert pos["quantity"] == 25
        assert pos["side"] == "BUY"
        pos_id = pos["position_id"]

        # Verify Orders
        ord_res = self.client.get("/api/v1/paper/orders?account_id=ACC-MANUAL-PAPER")
        assert ord_res.status_code == 200
        orders = ord_res.json()
        assert len(orders) >= 1
        assert orders[0]["status"] == "FILLED"

        # Verify Trades (with statutory fees)
        trd_res = self.client.get("/api/v1/paper/trades?account_id=ACC-MANUAL-PAPER")
        assert trd_res.status_code == 200
        trades = trd_res.json()
        assert len(trades) >= 1
        assert trades[0]["statutory_fees_rupees"] > 0.0

        # Square Off Single Position via /api/v1/paper/square-off/{pos_id}
        sq_res = self.client.post(f"/api/v1/paper/square-off/{pos_id}")
        assert sq_res.status_code == 200
        sq_data = sq_res.json()
        assert sq_data["status"] == "CLOSED"
        assert sq_data["position_id"] == pos_id

        # Verify 0 open positions remain
        pos_res2 = self.client.get("/api/v1/paper/positions?account_id=ACC-MANUAL-PAPER")
        assert pos_res2.status_code == 200
        assert len(pos_res2.json()) == 0

    def test_paper_square_off_all_action(self) -> None:
        """
        1. The use of function:
           Verifies atomic batch liquidation of multiple open positions via POST /api/v1/paper/square-off-all.

        2. How does the specific function work:
           - Places two distinct orders (CE and PE, 25 qty each).
           - Verifies 2 open positions exist.
           - Dispatches POST /api/v1/paper/square-off-all.
           - Asserts status is SUCCESS and closed_positions_count is 2.
           - Asserts subsequent positions query returns 0 items.

        3. Concepts used in the function:
           Emergency portfolio liquidation, atomic batch execution.

        4. Places where this function is imported and used:
           Invoked by pytest during gate_g4 test suite execution.

        5. Final output of the function, before and after:
           Before: Unverified batch liquidation. After: Confirmed batch liquidation contract.
        """
        # Place CE position
        self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "OPT-NIFTY-20250109-23500-CE",
                "side": "BUY",
                "quantity": 25,
                "order_type": "MARKET",
            },
        )
        # Place PE position
        self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "OPT-NIFTY-20250109-23500-PE",
                "side": "BUY",
                "quantity": 50,
                "order_type": "MARKET",
            },
        )

        # Confirm 2 positions
        p_res = self.client.get("/api/v1/paper/positions?account_id=ACC-MANUAL-PAPER")
        assert p_res.status_code == 200
        assert len(p_res.json()) == 2

        # Square Off All
        all_res = self.client.post("/api/v1/paper/square-off-all?account_id=ACC-MANUAL-PAPER")
        assert all_res.status_code == 200
        res_data = all_res.json()
        assert res_data["status"] == "SUCCESS"
        assert res_data["closed_positions_count"] == 2

        # Verify open positions empty
        p_res_empty = self.client.get("/api/v1/paper/positions?account_id=ACC-MANUAL-PAPER")
        assert p_res_empty.status_code == 200
        assert len(p_res_empty.json()) == 0

    def test_risk_policy_inspection_rk06_rk26_isolated(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/paper/risk-policy returns canonical risk limits including RK-06, RK-26, and ISOLATED mode.

        2. How does the specific function work:
           - Dispatches GET to /api/v1/paper/risk-policy.
           - Asserts HTTP 200.
           - Asserts freeze_quantity == 1800 (RK-06).
           - Asserts advisory_lot_ceiling == 72 (RK-26 = 1800 / 25).
           - Asserts account_allocation_mode == 'ISOLATED'.
           - Asserts max_loss_per_day_rupees == 50000.0.
           - Asserts max_drawdown_pct == 10.0.
           - Asserts trading_window_start == '09:15' and trading_window_end == '15:25'.

        3. Concepts used in the function:
           Pre-trade risk policy inspection, canonical firm boundaries.

        4. Places where this function is imported and used:
           Invoked by pytest during gate_g4 test suite execution.

        5. Final output of the function, before and after:
           Before: Unverified risk policy endpoint. After: Confirmed risk policy contract.
        """
        resp = self.client.get("/api/v1/paper/risk-policy")
        assert resp.status_code == 200
        policy = resp.json()
        assert policy["freeze_quantity"] == 1800  # RK-06
        assert policy["advisory_lot_ceiling"] == 72  # RK-26
        assert policy["account_allocation_mode"] == "ISOLATED"
        assert policy["max_loss_per_day_rupees"] == 50000.0
        assert policy["max_drawdown_pct"] == 10.0
        assert policy["trading_window_start"] == "09:15"
        assert policy["trading_window_end"] == "15:25"
        assert policy["margin_mode"] == "THEORETICAL"

    def test_screener_data_contracts_nifty_vix_atm_options(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/market/screener data contract for Indian market indices and weekly ATM options (Section 6.1).

        2. How does the specific function work:
           - Dispatches GET to /api/v1/market/screener.
           - Asserts HTTP 200 and ScreenerResponse structure.
           - Verifies Row 1: NSE:NIFTY50 (Spot, Daily Change %, Day High, Day Low, 52-Week Range, Volume).
           - Verifies Row 2: INDIAVIX (Volatility level, Regime Low/Normal/High).
           - Verifies Row 3: NIFTY ATM CE (Call option premium, strike, daily change %, expiry).
           - Verifies Row 4: NIFTY ATM PE (Put option premium, strike, daily change %, expiry).

        3. Concepts used in the function:
           Market screener contract, Indian index and derivative quotation, regime classification.

        4. Places where this function is imported and used:
           Invoked by pytest during gate_g4 test suite execution.

        5. Final output of the function, before and after:
           Before: Unverified screener contract. After: Confirmed 4-row Indian market screener contract.
        """
        resp = self.client.get("/api/v1/market/screener")
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamp" in data
        assert "items" in data
        items = data["items"]
        assert len(items) == 4

        # Row 1: NSE:NIFTY50
        nifty = items[0]
        assert nifty["symbol"] == "NSE:NIFTY50"
        assert nifty["type"] == "INDEX"
        assert nifty["last_price"] > 0.0
        assert nifty["high"] >= nifty["low"]
        assert "21,281.45 - 26,277.35" in (nifty["range_52w"] or "")
        assert nifty["volume"] >= 0

        # Row 2: INDIAVIX
        vix = items[1]
        assert vix["symbol"] == "INDIAVIX"
        assert vix["type"] == "VOLATILITY"
        assert vix["last_price"] > 0.0
        assert vix["regime"] in ["Low (< 13)", "Normal (13–18)", "High (> 18)"]

        # Row 3: NIFTY ATM CE
        ce = items[2]
        assert ce["symbol"] == "NIFTY ATM CE"
        assert ce["type"] == "OPTION_CE"
        assert ce["strike"] is not None and ce["strike"] > 0.0
        assert ce["contract_id"] is not None and "CE" in ce["contract_id"]
        assert ce["last_price"] > 0.0
        assert ce["expiry"] is not None

        # Row 4: NIFTY ATM PE
        pe = items[3]
        assert pe["symbol"] == "NIFTY ATM PE"
        assert pe["type"] == "OPTION_PE"
        assert pe["strike"] is not None and pe["strike"] > 0.0
        assert pe["contract_id"] is not None and "PE" in pe["contract_id"]
        assert pe["last_price"] > 0.0
        assert pe["expiry"] is not None

        # Verify convenience alias route /api/v1/screener
        alias_resp = self.client.get("/api/v1/screener")
        assert alias_resp.status_code == 200
        assert len(alias_resp.json()["items"]) == 4

    def test_strategy_sensitivity_heatmap_matrix_structure(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/backtest/heatmap data contract for 5x5 sensitivity matrix and monthly calendar (Section 6.2).

        2. How does the specific function work:
           - Dispatches GET to /api/v1/backtest/heatmap?strategy_id=STRAT-CE-TREND.
           - Asserts HTTP 200 and StrategyHeatmapResponse model.
           - Verifies X-Axis: 5 Strike Offsets (ATM-2, ATM-1, ATM, ATM+1, ATM+2).
           - Verifies Y-Axis: 5 Stop-Loss % (10%, 20%, 30%, 40%, 50%).
           - Verifies 25 interactive cells with net P&L (₹), return %, Sharpe ratio, and max drawdown %.
           - Verifies Monthly Returns Calendar View for 2025 and 2026.

        3. Concepts used in the function:
           Bivariate sensitivity analysis, Sharpe ratio optimization, monthly returns calendar grid.

        4. Places where this function is imported and used:
           Invoked by pytest during gate_g4 test suite execution.

        5. Final output of the function, before and after:
           Before: Unverified heatmap endpoint. After: Confirmed 25-cell sensitivity matrix and monthly calendar contract.
        """
        resp = self.client.get("/api/v1/backtest/heatmap?strategy_id=STRAT-CE-TREND")
        assert resp.status_code == 200
        data = resp.json()

        assert data["strategy_id"] == "STRAT-CE-TREND"
        assert data["strategy_name"] == "Long CE Trend Following"

        expected_offsets = ["ATM-2", "ATM-1", "ATM", "ATM+1", "ATM+2"]
        expected_sls = [10.0, 20.0, 30.0, 40.0, 50.0]

        assert data["strike_offsets"] == expected_offsets
        assert data["stop_loss_pcts"] == expected_sls

        matrix = data["matrix"]
        assert len(matrix) == 25

        for cell in matrix:
            assert cell["strike_offset"] in expected_offsets
            assert cell["stop_loss_pct"] in expected_sls
            assert isinstance(cell["net_pnl_rupees"], (int, float))
            assert isinstance(cell["return_pct"], (int, float))
            assert isinstance(cell["sharpe_ratio"], (int, float))
            assert isinstance(cell["max_drawdown_pct"], (int, float))

        # Check Monthly Returns Calendar View
        monthly_returns = data["monthly_returns"]
        assert len(monthly_returns) >= 2
        years = {yr["year"] for yr in monthly_returns}
        assert 2025 in years
        assert 2026 in years

        for yr in monthly_returns:
            assert len(yr["months"]) == 12
            assert "Jan" in yr["months"]
            assert "Dec" in yr["months"]
            assert isinstance(yr["total_pct"], (int, float))

        # Verify convenience alias route /api/v1/heatmap
        alias_resp = self.client.get("/api/v1/heatmap")
        assert alias_resp.status_code == 200
        assert len(alias_resp.json()["matrix"]) == 25
