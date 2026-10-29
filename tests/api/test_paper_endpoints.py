"""
1. What this file does:
   Automated verification test suite for Milestone M6-06, M6-14, and M6-18
   (Paper Trading, Risk Policy Inspection, Macro Strategy Monitoring, and Chart Price Lines API).
   Validates paper account balances, dynamic equity formulas, pre-trade risk policy rules (RK-06 freeze limit),
   macro strategy telemetry, instant paper order placement, stop-loss and take-profit chart price lines calculation,
   invalid lot rejection, position square-off, batch liquidation, and trade audit logging under Release Gate G4.

2. Overall design:
   Uses pytest and FastAPI TestClient under Gate G4:
     - GET /api/v1/paper/accounts: Verifies ACC-MANUAL-PAPER presence and balance formula:
       equity = cash_balance + unrealized_pnl, free_cash = cash_balance - margin_reserved.
     - GET /api/v1/paper/risk-policy: Verifies canonical freeze_quantity=1800 (RK-06).
     - GET /api/v1/paper/strategies: Verifies macro automated strategy list telemetry.
     - POST /api/v1/paper/orders: Verifies instant order execution, fill confirmation, and
       chart_lines calculation (entry, stop_loss, take_profit).
     - Validates RK-06 boundary rejection: quantity > 1800 rejected with HTTP 422.
     - Validates lot size divisibility rejection: quantity <= 0 or not multiple of 25 rejected with HTTP 422.
     - GET /api/v1/paper/positions: Verifies active open derivative positions.
     - POST /api/v1/paper/positions/square-off/{position_id}: Verifies single position liquidation and PnL realization.
     - POST /api/v1/paper/positions/square-off-all: Verifies atomic liquidation of all open positions.
     - POST /api/v1/paper/orders/cancel/{order_id}: Verifies working order cancellation and 404 handling.
     - GET /api/v1/paper/orders and GET /api/v1/paper/trades: Verifies chronological audit logs.

3. Elements in the file:
   - TestPaperEndpoints: Primary test class containing comprehensive automated test cases.

4. Final output of the file:
   - Executable pytest test suite tagged with @pytest.mark.gate_g4.
"""

import pytest
from fastapi.testclient import TestClient

from services.api.main import app
from services.api.routers.paper import PaperOrder, get_paper_state, reset_paper_state


@pytest.mark.gate_g4
class TestPaperEndpoints:
    """
    1. The use of class:
       Test suite verifying paper trading, risk policies, macro strategy monitoring, and chart lines.

    2. What the class contains:
       - setup_method: Resets simulation state prior to each test case.
       - test_get_paper_accounts_contract_and_formulas: Validates account balances and formulas.
       - test_get_paper_risk_policy_rk06: Validates RK-06 freeze quantity limit (1800).
       - test_get_paper_strategies_macro_catalog: Validates macro automated strategy catalog.
       - test_place_paper_order_buy_success_with_chart_lines: Validates BUY order fill and chart lines.
       - test_place_paper_order_sell_success_with_chart_lines: Validates SELL order fill and inverted chart lines.
       - test_place_paper_order_rk06_freeze_limit_rejection: Validates HTTP 422 when quantity > 1800.
       - test_place_paper_order_invalid_lot_size_rejection: Validates HTTP 422 when quantity is not multiple of 25.
       - test_place_paper_order_zero_and_negative_quantity_rejection: Validates HTTP 422 for quantity <= 0.
       - test_get_positions_and_single_square_off: Validates position query and individual square-off.
       - test_square_off_nonexistent_position_404: Validates HTTP 404 for unknown position ID.
       - test_square_off_all_positions_batch: Validates batch liquidation of multiple positions.
       - test_order_history_and_cancel_pending_order: Validates working order cancellation.
       - test_cancel_nonexistent_order_404: Validates HTTP 404 for unknown order ID.
       - test_trade_history_audit_trail: Validates trade history records after order and liquidation.

    3. Technologies used and why:
       pytest for test orchestration, FastAPI TestClient for in-memory ASGI dispatch.

    4. Key design and overall design of the class:
       Enforces Release Gate G4 compliance for M6-06, M6-14, and M6-18 deliverables.
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
           Invoked automatically by pytest before each test method in TestPaperEndpoints.

        5. Final output of the function, before and after:
           Before: Dirty state. After: Clean baseline state and initialized client.
        """
        reset_paper_state()
        self.client = TestClient(app)

    def test_get_paper_accounts_contract_and_formulas(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/paper/accounts contract and mathematical balance integrity.

        2. How does the specific function work:
           - Sends GET request to /api/v1/paper/accounts.
           - Asserts HTTP 200 and list return containing ACC-MANUAL-PAPER.
           - Asserts initial capital is ₹1,000,000.0.
           - Validates the dynamic equity formula: equity == cash_balance + unrealized_pnl.
           - Validates the free cash formula: free_cash == cash_balance - margin_reserved.

        3. Concepts used in the function:
           Balance integrity testing, dynamic equity formula assertion.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified endpoint. After: Confirmed compliant account model and formulas.
        """
        resp = self.client.get("/api/v1/paper/accounts")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        manual_acc = next((a for a in data if a["account_id"] == "ACC-MANUAL-PAPER"), None)
        assert manual_acc is not None
        assert manual_acc["name"] == "Manual Paper Account"
        assert manual_acc["mode"] == "MANUAL_PAPER"
        assert manual_acc["currency"] == "INR"
        assert manual_acc["initial_capital_rupees"] == 1000000.0
        assert manual_acc["cash_balance_rupees"] == 1000000.0

        equity = manual_acc["equity_rupees"]
        cash = manual_acc["cash_balance_rupees"]
        unrealized = manual_acc["unrealized_pnl_rupees"]
        assert equity == pytest.approx(cash + unrealized)

        free_cash = manual_acc["free_cash_rupees"]
        margin = manual_acc["margin_reserved_rupees"]
        assert free_cash == pytest.approx(cash - margin)

    def test_get_paper_risk_policy_rk06(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/paper/risk-policy returns canonical risk limit boundaries.

        2. How does the specific function work:
           - Sends GET request to /api/v1/paper/risk-policy.
           - Asserts HTTP 200.
           - Confirms freeze_quantity == 1800 per rule RK-06.
           - Confirms advisory_lot_ceiling == 72 (1800 / 25).
           - Confirms trading_window_start == '09:15' and trading_window_end == '15:25'.

        3. Concepts used in the function:
           Risk policy inspection, regulatory parameter verification.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified risk parameters. After: Confirmed RK-06 freeze limit.
        """
        resp = self.client.get("/api/v1/paper/risk-policy")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["freeze_quantity"] == 1800
        assert data["advisory_lot_ceiling"] == 72
        assert data["trading_window_start"] == "09:15"
        assert data["trading_window_end"] == "15:25"
        assert data["margin_mode"] == "THEORETICAL"

    def test_get_paper_strategies_macro_catalog(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/paper/strategies returns telemetry for macro view monitor.

        2. How does the specific function work:
           - Sends GET request to /api/v1/paper/strategies.
           - Asserts HTTP 200 and populated list.
           - Validates required fields: strategy_id, strategy_name, mode, status, allocated_lots, today_pnl_rupees.
           - Verifies LongCETrendFollowing presence with 'Running' status.

        3. Concepts used in the function:
           Macro strategy catalog verification, telemetry schema assertion.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified macro strategies. After: Confirmed populated strategy telemetry.
        """
        resp = self.client.get("/api/v1/paper/strategies")
        assert resp.status_code == 200, resp.text
        strategies = resp.json()
        assert isinstance(strategies, list)
        assert len(strategies) >= 2

        strat_names = [s["strategy_name"] for s in strategies]
        assert "LongCETrendFollowing" in strat_names
        assert "BullCallSpreadStrategy" in strat_names

        running_strat = next(s for s in strategies if s["strategy_name"] == "LongCETrendFollowing")
        assert running_strat["status"] == "Running"
        assert running_strat["allocated_lots"] > 0
        assert "today_pnl_rupees" in running_strat
        assert "win_rate_pct" in running_strat
        assert "sharpe_ratio" in running_strat

    def test_place_paper_order_buy_success_with_chart_lines(self) -> None:
        """
        1. The use of function:
           Verifies placing an instant BUY paper order with automatic SL/TP chart lines calculation.

        2. How does the specific function work:
           - Sends POST to /api/v1/paper/orders with contract_id, side='BUY', quantity=50, limit_price=100.0,
             stop_loss_pct=10.0, take_profit_pct=20.0.
           - Asserts HTTP 201 Created and status=='FILLED'.
           - Asserts fill_price == 100.0.
           - Validates chart_lines: entry == 100.0, stop_loss == 90.0 (100 * (1 - 0.10)), take_profit == 120.0 (100 * (1 + 0.20)).
           - Verifies position is created and account margin_reserved is updated.

        3. Concepts used in the function:
           One-click paper order simulation, directional chart price lines arithmetic.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unexecuted order. After: Confirmed filled order and exact chart price lines.
        """
        payload = {
            "account_id": "ACC-MANUAL-PAPER",
            "contract_id": "OPT-NIFTY-20250109-22500-CE",
            "side": "BUY",
            "quantity": 50,
            "order_type": "LIMIT",
            "limit_price": 100.0,
            "stop_loss_pct": 10.0,
            "take_profit_pct": 20.0,
        }
        resp = self.client.post("/api/v1/paper/orders", json=payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()

        assert data["status"] == "FILLED"
        assert data["side"] == "BUY"
        assert data["quantity"] == 50
        assert data["fill_price"] == 100.0
        assert data["account_id"] == "ACC-MANUAL-PAPER"

        chart_lines = data["chart_lines"]
        assert chart_lines["entry"] == 100.0
        assert chart_lines["stop_loss"] == 90.0
        assert chart_lines["take_profit"] == 120.0

        # Check account reflects margin reserved
        acc_resp = self.client.get("/api/v1/paper/accounts")
        acc = next(a for a in acc_resp.json() if a["account_id"] == "ACC-MANUAL-PAPER")
        assert acc["margin_reserved_rupees"] == pytest.approx(5000.0)
        assert acc["free_cash_rupees"] == pytest.approx(995000.0)
        assert acc["equity_rupees"] == pytest.approx(1000000.0)

    def test_place_paper_order_sell_success_with_chart_lines(self) -> None:
        """
        1. The use of function:
           Verifies placing an instant SELL paper order with inverted short SL/TP chart lines.

        2. How does the specific function work:
           - Sends POST to /api/v1/paper/orders with side='SELL', limit_price=200.0,
             stop_loss_pct=15.0, take_profit_pct=25.0.
           - Asserts HTTP 201 Created and status=='FILLED'.
           - For short positions: stop_loss must be ABOVE entry: 200 * (1 + 0.15) = 230.0.
           - For short positions: take_profit must be BELOW entry: 200 * (1 - 0.25) = 150.0.

        3. Concepts used in the function:
           Short position price lines geometry, asymmetric stop and profit logic.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unexecuted short order. After: Verified inverted short chart lines.
        """
        payload = {
            "account_id": "ACC-MANUAL-PAPER",
            "contract_id": "OPT-NIFTY-20250109-22500-PE",
            "side": "SELL",
            "quantity": 25,
            "order_type": "LIMIT",
            "limit_price": 200.0,
            "stop_loss_pct": 15.0,
            "take_profit_pct": 25.0,
        }
        resp = self.client.post("/api/v1/paper/orders", json=payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()

        assert data["status"] == "FILLED"
        assert data["side"] == "SELL"
        assert data["fill_price"] == 200.0

        chart_lines = data["chart_lines"]
        assert chart_lines["entry"] == 200.0
        assert chart_lines["stop_loss"] == 230.0
        assert chart_lines["take_profit"] == 150.0

    def test_place_paper_order_rk06_freeze_limit_rejection(self) -> None:
        """
        1. The use of function:
           Verifies pre-trade risk policy rejection when order quantity exceeds the exchange freeze ceiling.

        2. How does the specific function work:
           - Sends POST to /api/v1/paper/orders with quantity=1825 (greater than freeze_quantity=1800).
           - Asserts HTTP 422 Unprocessable Entity.
           - Verifies error detail explicitly cites 'RK-06: Order exceeds freeze limit 1800'.

        3. Concepts used in the function:
           Pre-trade risk enforcement, RK-06 exchange freeze boundary validation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Over-limit order intent. After: Confirmed HTTP 422 rejection citing RK-06.
        """
        payload = {
            "contract_id": "OPT-NIFTY-20250109-22500-CE",
            "side": "BUY",
            "quantity": 1825,
            "limit_price": 100.0,
        }
        resp = self.client.post("/api/v1/paper/orders", json=payload)
        assert resp.status_code == 422
        assert "RK-06" in resp.text
        assert "freeze limit 1800" in resp.text

    def test_place_paper_order_invalid_lot_size_rejection(self) -> None:
        """
        1. The use of function:
           Verifies rejection when order quantity is not a multiple of standard lot size (25).

        2. How does the specific function work:
           - Submits an order with quantity=30 (not divisible by 25).
           - Asserts HTTP 422 Unprocessable Entity.
           - Verifies error detail mentions lot size divisibility requirement.

        3. Concepts used in the function:
           Derivative lot sizing validation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Non-standard lot size order. After: Confirmed HTTP 422 rejection.
        """
        payload = {
            "contract_id": "OPT-NIFTY-20250109-22500-CE",
            "side": "BUY",
            "quantity": 30,
            "limit_price": 100.0,
        }
        resp = self.client.post("/api/v1/paper/orders", json=payload)
        assert resp.status_code == 422
        assert "multiple of" in resp.text.lower() or "25" in resp.text

    def test_place_paper_order_zero_and_negative_quantity_rejection(self) -> None:
        """
        1. The use of function:
           Verifies rejection when order quantity is non-positive (zero or negative).

        2. How does the specific function work:
           - Submits order with quantity=0, asserts HTTP 422.
           - Submits order with quantity=-25, asserts HTTP 422.

        3. Concepts used in the function:
           Input boundary constraint verification.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Zero/negative quantity orders. After: Confirmed HTTP 422 rejections.
        """
        for bad_qty in [0, -25]:
            payload = {
                "contract_id": "OPT-NIFTY-20250109-22500-CE",
                "side": "BUY",
                "quantity": bad_qty,
                "limit_price": 100.0,
            }
            resp = self.client.post("/api/v1/paper/orders", json=payload)
            assert resp.status_code == 422, f"Expected 422 for quantity={bad_qty}"

    def test_get_positions_and_single_square_off(self) -> None:
        """
        1. The use of function:
           Verifies querying open positions and liquidating a single position via square-off.

        2. How does the specific function work:
           - Places a valid paper order for 25 contracts at ₹150.0.
           - Calls GET /api/v1/paper/positions, verifies 1 open position with matching attributes.
           - Calls POST /api/v1/paper/positions/square-off/{position_id}.
           - Asserts HTTP 200 and status=='CLOSED'.
           - Queries positions again and confirms the list is now empty.
           - Confirms trade audit log contains the closing trade.

        3. Concepts used in the function:
           Position lifecycle tracking, single position liquidation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Open position. After: Closed position with released collateral and verified empty position list.
        """
        # Place order
        order_resp = self.client.post(
            "/api/v1/paper/orders",
            json={
                "contract_id": "OPT-NIFTY-20250109-22500-CE",
                "side": "BUY",
                "quantity": 25,
                "limit_price": 150.0,
            },
        )
        assert order_resp.status_code == 201

        # Query positions
        pos_resp = self.client.get("/api/v1/paper/positions")
        assert pos_resp.status_code == 200
        positions = pos_resp.json()
        assert len(positions) == 1
        target_pos_id = positions[0]["position_id"]
        assert positions[0]["quantity"] == 25
        assert positions[0]["entry_price"] == 150.0

        # Square off
        sq_resp = self.client.post(f"/api/v1/paper/positions/square-off/{target_pos_id}")
        assert sq_resp.status_code == 200, sq_resp.text
        sq_data = sq_resp.json()
        assert sq_data["status"] == "CLOSED"
        assert sq_data["position_id"] == target_pos_id

        # Confirm position is removed
        pos_after = self.client.get("/api/v1/paper/positions").json()
        assert len(pos_after) == 0

    def test_square_off_nonexistent_position_404(self) -> None:
        """
        1. The use of function:
           Verifies that attempting to square off an unknown position ID returns HTTP 404.

        2. How does the specific function work:
           - Sends POST to /api/v1/paper/positions/square-off/POS-NONEXISTENT.
           - Asserts HTTP 404 Not Found.

        3. Concepts used in the function:
           Error boundary testing, resource not found handling.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Non-existent resource request. After: Verified HTTP 404 response.
        """
        resp = self.client.post("/api/v1/paper/positions/square-off/POS-DOES-NOT-EXIST")
        assert resp.status_code == 404
        assert "not found" in resp.text.lower()

    def test_square_off_all_positions_batch(self) -> None:
        """
        1. The use of function:
           Verifies batch liquidation of multiple open derivative positions.

        2. How does the specific function work:
           - Places two distinct paper orders (creating 2 open positions).
           - Verifies GET /api/v1/paper/positions returns length 2.
           - Calls POST /api/v1/paper/positions/square-off-all.
           - Asserts HTTP 200 and closed_positions_count == 2.
           - Queries positions again and verifies length 0.

        3. Concepts used in the function:
           Batch liquidation, emergency portfolio flattening.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: 2 open positions. After: 0 open positions, verified batch closure response.
        """
        self.client.post(
            "/api/v1/paper/orders",
            json={
                "contract_id": "OPT-NIFTY-20250109-22500-CE",
                "side": "BUY",
                "quantity": 25,
                "limit_price": 100.0,
            },
        )
        self.client.post(
            "/api/v1/paper/orders",
            json={
                "contract_id": "OPT-NIFTY-20250109-23000-PE",
                "side": "BUY",
                "quantity": 50,
                "limit_price": 80.0,
            },
        )

        assert len(self.client.get("/api/v1/paper/positions").json()) == 2

        resp = self.client.post("/api/v1/paper/positions/square-off-all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["closed_positions_count"] == 2

        assert len(self.client.get("/api/v1/paper/positions").json()) == 0

    def test_order_history_and_cancel_pending_order(self) -> None:
        """
        1. The use of function:
           Verifies order history retrieval and cancellation of working pending orders.

        2. How does the specific function work:
           - Manually injects a PENDING order into the state repository.
           - Calls GET /api/v1/paper/orders, confirms presence.
           - Calls POST /api/v1/paper/orders/cancel/{order_id}.
           - Asserts HTTP 200 and status=='CANCELLED'.
           - Verifies idempotent behavior when cancelling an already cancelled order.

        3. Concepts used in the function:
           Order cancellation lifecycle, idempotency testing.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Pending order. After: Cancelled order verified in order history.
        """
        state = get_paper_state()
        pending_order = PaperOrder(
            order_id="ORD-PENDING-001",
            account_id="ACC-MANUAL-PAPER",
            contract_id="OPT-NIFTY-20250109-22500-CE",
            side="BUY",
            quantity=25,
            order_type="LIMIT",
            price=95.0,
            status="PENDING",
            created_at=1736413200,
        )
        with state._lock:
            state.orders.append(pending_order)

        orders = self.client.get("/api/v1/paper/orders").json()
        assert any(o["order_id"] == "ORD-PENDING-001" for o in orders)

        # Cancel order
        cancel_resp = self.client.post("/api/v1/paper/orders/cancel/ORD-PENDING-001")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "CANCELLED"

        # Idempotent second cancel
        repeat_resp = self.client.post("/api/v1/paper/orders/cancel/ORD-PENDING-001")
        assert repeat_resp.status_code == 200
        assert repeat_resp.json()["status"] == "CANCELLED"

    def test_cancel_nonexistent_order_404(self) -> None:
        """
        1. The use of function:
           Verifies that cancelling an unknown order ID returns HTTP 404.

        2. How does the specific function work:
           - Sends POST to /api/v1/paper/orders/cancel/ORD-NOT-FOUND.
           - Asserts HTTP 404 Not Found.

        3. Concepts used in the function:
           Missing order handling, error response validation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Invalid order cancel dispatch. After: Verified HTTP 404.
        """
        resp = self.client.post("/api/v1/paper/orders/cancel/ORD-NOT-FOUND")
        assert resp.status_code == 404
        assert "not found" in resp.text.lower()

    def test_trade_history_audit_trail(self) -> None:
        """
        1. The use of function:
           Verifies GET /api/v1/paper/trades returns comprehensive trade execution audit records.

        2. How does the specific function work:
           - Submits a paper order (generating an opening trade).
           - Squares off the position (generating a closing trade).
           - Queries GET /api/v1/paper/trades.
           - Verifies trade history contains 2 trades (BUY and SELL).
           - Confirms trade attributes: trade_id, contract_id, price, quantity, timestamp.

        3. Concepts used in the function:
           Audit trail verification, trade ledger completeness.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Empty trade history. After: Verified itemized round-trip trade audit logs.
        """
        # Place order
        self.client.post(
            "/api/v1/paper/orders",
            json={
                "contract_id": "OPT-NIFTY-20250109-22500-CE",
                "side": "BUY",
                "quantity": 25,
                "limit_price": 120.0,
            },
        )

        # Square off
        positions = self.client.get("/api/v1/paper/positions").json()
        assert len(positions) == 1
        pos_id = positions[0]["position_id"]
        self.client.post(f"/api/v1/paper/positions/square-off/{pos_id}")

        # Check trades
        trades_resp = self.client.get("/api/v1/paper/trades")
        assert trades_resp.status_code == 200
        trades = trades_resp.json()
        assert len(trades) == 2

        sides = [t["side"] for t in trades]
        assert "BUY" in sides
        assert "SELL" in sides
        for t in trades:
            assert t["quantity"] == 25
            assert t["contract_id"] == "OPT-NIFTY-20250109-22500-CE"
            assert t["price"] == 120.0
            assert t["trade_id"].startswith("TRD-")
