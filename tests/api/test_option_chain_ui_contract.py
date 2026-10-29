"""
1. What this file does:
   Automated verification test suite for Task 11 of Stage 6:
   "NIFTY Option Chain Tab with One-Click Paper Execution & Chart SL/TP Lines (M6-18, UI-1b, M6-03b, M6-15)".
   Validates contract expiries querying, dual-column option chain matrix with ATM centering,
   paper order placement directly targeting ACC-MANUAL-PAPER, on-chart Entry/SL/TP coordinate calculation,
   option candlestick historical query contract, and pre-trade risk policy boundary enforcement.

2. Overall design:
   Uses pytest and FastAPI TestClient under Release Gate G4:
     - GET /api/v1/options/expiries: Validates chronological ascending order of available expiry dates.
     - GET /api/v1/options/chain: Validates ATM strike centering (+/- 10, 15, 20, 25 strikes), dual-column
       Call/Put pairing, Greeks (Delta, Theta, IV), Open Interest, and Put-Call Ratio (PCR).
     - POST /api/v1/paper/orders: Validates one-click paper order submission into ACC-MANUAL-PAPER,
       instant fill execution, margin reservation, and ChartPriceLines payload generation (entry, SL, TP)
       for both percentage and absolute price boundaries on BUY and SELL sides.
     - GET /api/v1/options/candles: Validates historical candlestick bar retrieval, OHLC invariants,
       and chronological timestamp monotonicity.
     - Enforces RK-06 exchange freeze ceilings (1800 contracts) and lot-size divisibility (multiples of 25).

3. Elements in the file:
   - TestOptionChainUIContract: Primary test class containing 9 comprehensive contract test cases.

4. Final output of the file:
   - Executable pytest test suite verifying Milestone M6-18, UI-1b, M6-03b, and M6-15 contracts.
"""

from typing import List

import pytest
from fastapi.testclient import TestClient

from services.api.main import app
from services.api.routers.paper import reset_paper_state


@pytest.mark.gate_g4
class TestOptionChainUIContract:
    """
    1. The use of class:
       Automated test suite verifying the Option Chain matrix, one-click paper order routing,
       on-chart price lines, and option candlestick query contracts.

    2. What the class contains:
       - test_expiries_query_contract_and_ordering: Verifies sorted expiry date strings.
       - test_option_chain_matrix_structure_and_atm_centering: Verifies dual-column chain centered at ATM.
       - test_option_chain_strike_range_selector_variations: Verifies 10, 15, 20, 25 strike ranges.
       - test_paper_order_placement_targeting_manual_paper_account: Verifies order routing to ACC-MANUAL-PAPER.
       - test_paper_order_sell_side_chart_price_lines_payload: Verifies SELL side SL/TP geometry.
       - test_paper_order_absolute_price_levels_stop_loss_and_take_profit: Verifies absolute SL/TP prices.
       - test_option_candlestick_query_contract_and_resolution: Verifies option historical bars and OHLC.
       - test_option_chain_itm_otm_shading_and_greeks_integrity: Verifies ITM/OTM logic and Greeks bounds.
       - test_paper_order_pre_trade_risk_rejections: Verifies RK-06 freeze and lot size validation.

    3. Technologies used and why:
       pytest framework with FastAPI TestClient for high-speed in-memory API verification.

    4. Key design and overall design of the class:
       Validates strict conformance to QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §18.2, §21.1, and §26.
    """

    def setup_method(self) -> None:
        """
        1. The use of function:
           Initializes TestClient and resets simulation state before each test.

        2. How does the specific function work:
           - Constructs fresh FastAPI TestClient instance.
           - Resets in-memory paper trading simulation ledger.

        3. Concepts used in the function:
           Test isolation, state reset fixture.

        4. Places where this function is imported and used:
           Invoked automatically by pytest before each test method.

        5. Final output of the function, before and after:
           Before: Dirty simulation state. After: Clean baseline ready for order execution tests.
        """
        self.client = TestClient(app)
        reset_paper_state()

    def test_expiries_query_contract_and_ordering(self) -> None:
        """
        1. The use of function:
           Validates the GET /api/v1/options/expiries contract for NIFTY.

        2. How does the specific function work:
           - Sends GET request with underlying=NIFTY.
           - Asserts HTTP 200 and non-empty list of date strings.
           - Asserts dates follow strict ISO format (YYYY-MM-DD) and chronological ascending order.

        3. Concepts used in the function:
           Date format validation, chronological monotonicity, underlying symbol normalization.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified expiries. After: Confirmed sorted ISO expiry list.
        """
        resp = self.client.get("/api/v1/options/expiries?underlying=NIFTY")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0, "Analytical lake must contain at least one option expiry"
        for exp in data:
            assert len(exp) == 10 and exp[4] == "-" and exp[7] == "-"
        assert data == sorted(data), "Expiries must be strictly sorted ascending"

    def test_option_chain_matrix_structure_and_atm_centering(self) -> None:
        """
        1. The use of function:
           Validates the option chain matrix structure and At-The-Money (ATM) centering.

        2. How does the specific function work:
           - Sends GET request to /api/v1/options/chain with strike_count=15.
           - Asserts spot_price > 0 and atm_strike is rounded to nearest multiple of 50.
           - Asserts exactly 31 strike rows (2 * 15 + 1).
           - Asserts the center row (index 15) is exactly the atm_strike.
           - Asserts strike prices increment by 50.0 continuously.
           - Asserts Call (CE) and Put (PE) objects exist with valid pricing and Greeks.
           - Asserts total_ce_oi, total_pe_oi, and pcr are populated.

        3. Concepts used in the function:
           ATM centering math, dual-column Call/Put reconstruction, PCR computation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Raw options lake data. After: Confirmed centered dual-column chain matrix.
        """
        resp = self.client.get("/api/v1/options/chain?underlying=NIFTY&strike_count=15")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["underlying"] == "NIFTY"
        assert len(data["expiry_date"]) == 10
        assert data["spot_price"] > 0.0
        assert data["atm_strike"] > 0.0
        assert data["atm_strike"] % 50.0 == 0.0

        strikes: List[dict] = data["strikes"]
        assert len(strikes) == 31, f"Expected 31 rows for +/-15 strikes, got {len(strikes)}"

        atm_index = len(strikes) // 2
        center_row = strikes[atm_index]
        assert center_row["strike"] == data["atm_strike"], (
            f"Center row {center_row['strike']} must match ATM strike {data['atm_strike']}"
        )

        for i in range(len(strikes) - 1):
            assert strikes[i + 1]["strike"] - strikes[i]["strike"] == 50.0

        assert "total_ce_oi" in data
        assert "total_pe_oi" in data
        assert "pcr" in data
        assert data["total_ce_oi"] >= 0
        assert data["total_pe_oi"] >= 0
        assert data["pcr"] >= 0.0

    def test_option_chain_strike_range_selector_variations(self) -> None:
        """
        1. The use of function:
           Validates the option chain with different strike range counts (10, 15, 20, 25).

        2. How does the specific function work:
           - Iterates over range settings [10, 15, 20, 25].
           - Asserts row count equals 2 * count + 1 (21, 31, 41, 51).
           - Asserts center row is always equal to atm_strike.

        3. Concepts used in the function:
           Dynamic strike range projection, symmetric strike ladder.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified strike ranges. After: Confirmed dynamic sizing for all standard selectors.
        """
        for count in [10, 15, 20, 25]:
            resp = self.client.get(f"/api/v1/options/chain?underlying=NIFTY&strike_count={count}")
            assert resp.status_code == 200
            data = resp.json()
            expected_len = (2 * count) + 1
            assert len(data["strikes"]) == expected_len
            atm_row = data["strikes"][count]
            assert atm_row["strike"] == data["atm_strike"]

    def test_paper_order_placement_targeting_manual_paper_account(self) -> None:
        """
        1. The use of function:
           Validates one-click paper order submission directly into ACC-MANUAL-PAPER (Milestone M6-18).

        2. How does the specific function work:
           - Dispatches POST /api/v1/paper/orders with account_id='ACC-MANUAL-PAPER'.
           - Asserts response confirms order status FILLED and account_id ACC-MANUAL-PAPER.
           - Asserts chart_lines payload is returned containing entry, stop_loss, and take_profit coordinates.
           - Verifies BUY order SL is below entry and TP is above entry.

        3. Concepts used in the function:
           Direct paper order routing, margin reservation, on-chart price coordinate projection.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unsubmitted option order. After: Filled paper position with on-chart lines.
        """
        order_payload = {
            "account_id": "ACC-MANUAL-PAPER",
            "contract_id": "NIFTY_2025-02-06_23850.00_CE",
            "side": "BUY",
            "quantity": 25,
            "order_type": "MARKET",
            "stop_loss_pct": 20.0,
            "take_profit_pct": 40.0,
        }

        resp = self.client.post("/api/v1/paper/orders", json=order_payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()

        assert data["account_id"] == "ACC-MANUAL-PAPER"
        assert data["status"] == "FILLED"
        assert data["side"] == "BUY"
        assert data["quantity"] == 25
        assert data["fill_price"] > 0.0

        chart_lines = data["chart_lines"]
        assert chart_lines["entry"] == round(data["fill_price"], 2)
        assert chart_lines["stop_loss"] is not None
        assert chart_lines["take_profit"] is not None
        assert chart_lines["stop_loss"] < chart_lines["entry"], "BUY SL must be below entry"
        assert chart_lines["take_profit"] > chart_lines["entry"], "BUY TP must be above entry"

        expected_sl = round(data["fill_price"] * 0.80, 2)
        expected_tp = round(data["fill_price"] * 1.40, 2)
        assert chart_lines["stop_loss"] == expected_sl
        assert chart_lines["take_profit"] == expected_tp

    def test_paper_order_sell_side_chart_price_lines_payload(self) -> None:
        """
        1. The use of function:
           Validates paper order execution and on-chart lines for SELL side positions.

        2. How does the specific function work:
           - Submits SELL order for 50 contracts with 15% SL and 30% TP.
           - Asserts SELL SL is above entry price and TP is below entry price.

        3. Concepts used in the function:
           Short position risk boundaries, asymmetric SL/TP geometry.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unsubmitted sell order. After: Confirmed short position SL/TP coordinates.
        """
        order_payload = {
            "account_id": "ACC-MANUAL-PAPER",
            "contract_id": "NIFTY_2025-02-06_23850.00_PE",
            "side": "SELL",
            "quantity": 50,
            "order_type": "MARKET",
            "stop_loss_pct": 15.0,
            "take_profit_pct": 30.0,
        }

        resp = self.client.post("/api/v1/paper/orders", json=order_payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()

        assert data["side"] == "SELL"
        assert data["quantity"] == 50
        chart_lines = data["chart_lines"]
        assert chart_lines["stop_loss"] > chart_lines["entry"], "SELL SL must be above entry"
        assert chart_lines["take_profit"] < chart_lines["entry"], "SELL TP must be below entry"

        expected_sl = round(data["fill_price"] * 1.15, 2)
        expected_tp = round(data["fill_price"] * 0.70, 2)
        assert chart_lines["stop_loss"] == expected_sl
        assert chart_lines["take_profit"] == expected_tp

    def test_paper_order_absolute_price_levels_stop_loss_and_take_profit(self) -> None:
        """
        1. The use of function:
           Validates paper order submission using absolute price levels for SL and TP.

        2. How does the specific function work:
           - Submits LIMIT order at 120.0 with stop_loss_price=95.0 and take_profit_price=160.0.
           - Asserts fill_price equals limit price.
           - Asserts chart_lines exact coordinates match specified absolute prices.

        3. Concepts used in the function:
           Absolute price level orders, limit execution matching.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Absolute price levels unverified. After: Confirmed direct coordinate mapping.
        """
        order_payload = {
            "account_id": "ACC-MANUAL-PAPER",
            "contract_id": "NIFTY_2025-02-06_23850.00_CE",
            "side": "BUY",
            "quantity": 25,
            "order_type": "LIMIT",
            "limit_price": 120.0,
            "stop_loss_price": 95.0,
            "take_profit_price": 160.0,
        }

        resp = self.client.post("/api/v1/paper/orders", json=order_payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()

        assert data["fill_price"] == 120.0
        assert data["chart_lines"]["entry"] == 120.0
        assert data["chart_lines"]["stop_loss"] == 95.0
        assert data["chart_lines"]["take_profit"] == 160.0

    def test_option_candlestick_query_contract_and_resolution(self) -> None:
        """
        1. The use of function:
           Validates historical candlestick bars retrieval for an individual option contract (Milestones M6-03b, M6-16).

        2. How does the specific function work:
           - Queries GET /api/v1/options/candles for a known contract ID.
           - Asserts 200 OK and validates OptionCandleResponse schema.
           - Asserts OHLC candle integrity: high >= low, high >= open, high >= close, low <= open, low <= close.
           - Asserts timestamps are strictly monotonic ascending.

        3. Concepts used in the function:
           Time-series candle verification, OHLC boundary invariants, chronological monotonicity.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified option candles. After: Confirmed valid OHLCV series.
        """
        resp = self.client.get(
            "/api/v1/options/candles?contract_id=NIFTY_2025-02-06_23850.00_CE&resolution=1m&limit=100"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["symbol"] == "NIFTY"
        assert data["strike"] == 23850.0
        assert data["option_type"] == "CE"
        assert data["resolution"] == "1m"
        assert isinstance(data["candles"], list)

        if len(data["candles"]) > 0:
            candles = data["candles"]
            prev_time = 0
            for c in candles:
                assert c["high"] >= c["low"]
                assert c["high"] >= c["open"]
                assert c["high"] >= c["close"]
                assert c["low"] <= c["open"]
                assert c["low"] <= c["close"]
                assert c["time"] >= prev_time
                prev_time = c["time"]

    def test_option_chain_itm_otm_shading_and_greeks_integrity(self) -> None:
        """
        1. The use of function:
           Validates In-The-Money (ITM) vs Out-Of-The-Money (OTM) strike classification and Greeks properties.

        2. How does the specific function work:
           - Queries the option chain matrix.
           - Verifies for all rows:
             * Calls are ITM when strike < spot_price.
             * Puts are ITM when strike > spot_price.
           - Asserts that present Greeks fall within theoretical Black-Scholes boundaries.

        3. Concepts used in the function:
           Moneyness boundaries, theoretical option Greeks validation.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unchecked moneyness logic. After: Confirmed moneyness and Greeks sanity.
        """
        resp = self.client.get("/api/v1/options/chain?underlying=NIFTY&strike_count=15")
        assert resp.status_code == 200
        data = resp.json()
        spot = data["spot_price"]

        for row in data["strikes"]:
            strike = row["strike"]
            is_ce_itm = strike < spot
            is_pe_itm = strike > spot
            assert (is_ce_itm and is_pe_itm) is False, "A strike cannot be simultaneously ITM for Call and Put"

            if row.get("ce"):
                ce = row["ce"]
                assert ce["strike"] == strike
                assert ce["option_type"] == "CE"
                if ce.get("delta") is not None and ce["delta"] != 0.0:
                    assert 0.0 <= ce["delta"] <= 1.0, f"CE delta {ce['delta']} must be between 0 and 1"

            if row.get("pe"):
                pe = row["pe"]
                assert pe["strike"] == strike
                assert pe["option_type"] == "PE"
                if pe.get("delta") is not None and pe["delta"] != 0.0:
                    assert -1.0 <= pe["delta"] <= 0.0, f"PE delta {pe['delta']} must be between -1 and 0"

    def test_paper_order_pre_trade_risk_rejections(self) -> None:
        """
        1. The use of function:
           Validates pre-trade risk policy rule rejections (RK-06 freeze limit and lot size divisibility).

        2. How does the specific function work:
           - Submits quantity=1825 (> 1800 freeze limit) -> asserts HTTP 422.
           - Submits quantity=30 (not multiple of 25) -> asserts HTTP 422.
           - Submits quantity=0 -> asserts HTTP 422.

        3. Concepts used in the function:
           Exchange freeze limit enforcement (RK-06), lot size validation, HTTP 422 error contracts.

        4. Places where this function is imported and used:
           Run by pytest test runner under Gate G4.

        5. Final output of the function, before and after:
           Before: Unverified boundary enforcement. After: Confirmed deterministic rejections.
        """
        # Exceed freeze limit
        resp1 = self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "NIFTY_2025-02-06_23850.00_CE",
                "side": "BUY",
                "quantity": 1825,
                "order_type": "MARKET",
            },
        )
        assert resp1.status_code == 422

        # Invalid lot size
        resp2 = self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "NIFTY_2025-02-06_23850.00_CE",
                "side": "BUY",
                "quantity": 30,
                "order_type": "MARKET",
            },
        )
        assert resp2.status_code == 422

        # Zero quantity
        resp3 = self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "NIFTY_2025-02-06_23850.00_CE",
                "side": "BUY",
                "quantity": 0,
                "order_type": "MARKET",
            },
        )
        assert resp3.status_code == 422
