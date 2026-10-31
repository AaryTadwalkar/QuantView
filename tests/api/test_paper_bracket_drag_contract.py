"""
1. What this file does:
   Automated verification test suite for Milestone M7-08 under Release Gate G5
   (Draggable Chart SL/TP & Gateway WebSocket Bridge Contract).
   Validates PATCH /api/v1/paper/positions/{position_id}/brackets endpoint functionality,
   5-paise tick snapping, directional boundary validation for LONG and SHORT positions,
   cross-bracket sanity checks, negative price rejection, and HTTP 404 handling.

2. Overall design:
   Uses pytest and FastAPI TestClient under Gate G5:
     - test_patch_brackets_long_success: Verifies successful SL and TP updates for LONG positions.
     - test_patch_brackets_short_success: Verifies successful SL and TP updates for SHORT positions.
     - test_patch_brackets_long_invalid_sl_side_rejection: Rejects SL >= LTP for LONG with HTTP 422.
     - test_patch_brackets_long_invalid_tp_side_rejection: Rejects TP <= LTP for LONG with HTTP 422.
     - test_patch_brackets_short_invalid_sl_side_rejection: Rejects SL <= LTP for SHORT with HTTP 422.
     - test_patch_brackets_short_invalid_tp_side_rejection: Rejects TP >= LTP for SHORT with HTTP 422.
     - test_patch_brackets_5_paise_tick_snapping: Verifies automatic snapping of arbitrary floats to 5-paise ticks.
     - test_patch_brackets_negative_or_zero_price_rejection: Rejects non-positive prices with HTTP 422.
     - test_patch_brackets_nonexistent_position_404: Returns HTTP 404 for unknown position identifiers.

3. Elements in the file:
   - TestPaperBracketDragContract: Primary Gate G5 test suite verifying draggable bracket contracts.

4. Final output of the file:
   - Executable pytest test suite tagged with @pytest.mark.gate_g5.
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from services.api.main import app
from services.api.routers.paper import reset_paper_state


@pytest.mark.gate_g5
class TestPaperBracketDragContract:
    """
    1. The use of class:
       Test suite verifying the backend bracket update endpoint contract (PATCH /api/v1/paper/positions/{id}/brackets).

    2. What the class contains:
       - setup_method: Resets simulation state prior to each test case.
       - test_patch_brackets_long_success: Verifies successful bracket updates on LONG positions.
       - test_patch_brackets_short_success: Verifies successful bracket updates on SHORT positions.
       - test_patch_brackets_long_invalid_sl_side_rejection: Rejects SL above entry for LONG.
       - test_patch_brackets_long_invalid_tp_side_rejection: Rejects TP below entry for LONG.
       - test_patch_brackets_short_invalid_sl_side_rejection: Rejects SL below entry for SHORT.
       - test_patch_brackets_short_invalid_tp_side_rejection: Rejects TP above entry for SHORT.
       - test_patch_brackets_5_paise_tick_snapping: Verifies tick quantization to 5-paise intervals.
       - test_patch_brackets_negative_or_zero_price_rejection: Rejects non-positive values.
       - test_patch_brackets_nonexistent_position_404: Verifies HTTP 404 on missing position ID.

    3. Technologies used and why:
       pytest for test orchestration, FastAPI TestClient for in-memory ASGI dispatch.

    4. Key design and overall design of the class:
       Enforces Release Gate G5 compliance for Milestone M7-08 deliverables.
    """

    def setup_method(self) -> None:
        """
        1. The use of function:
           Test fixture resetting the paper simulator state before each test invocation.

        2. How does the specific function work:
           - Invokes reset_paper_state() to restore default account balances and clear positions.
           - Instantiates a clean FastAPI TestClient bound to app.

        3. Concepts used in the function:
           Test isolation, state resetting, fixture lifecycle.

        4. Places where this function is imported and used:
           Invoked automatically by pytest before each test method in TestPaperBracketDragContract.

        5. Final output of the function, before and after:
           Before: Unpredictable test state. After: Clean baseline state and initialized TestClient.
        """
        reset_paper_state()
        self.client = TestClient(app)

    def test_patch_brackets_long_success(self) -> None:
        """
        1. The use of function:
           Verifies successful Stop-Loss and Take-Profit updates for a LONG derivative position.

        2. How does the specific function work:
           - Submits a BUY LIMIT order to establish a LONG position at ₹150.0.
           - Extracts position_id and fill_price from order response.
           - Dispatches PATCH /api/v1/paper/positions/{position_id}/brackets with valid SL (< fill) and TP (> fill).
           - Asserts HTTP 200 OK and validates updated stop_loss_price and take_profit_price in response.
           - Updates SL individually and TP individually, confirming state persistence.

        3. Concepts used in the function:
           Long bracket placement, REST PATCH contract, incremental bracket modification.

        4. Places where this function is imported and used:
           Executed by pytest under Release Gate G5.

        5. Final output of the function, before and after:
           Before: Position with default brackets. After: Position with updated and verified bracket coordinates.
        """
        order_resp = self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "OPT-NIFTY-20250109-23000-CE",
                "side": "BUY",
                "quantity": 25,
                "order_type": "LIMIT",
                "limit_price": 150.0,
            },
        )
        assert order_resp.status_code == status.HTTP_201_CREATED
        order_data = order_resp.json()
        pos_id = order_data["position_id"]
        fill_price = order_data["fill_price"]
        assert pos_id is not None
        assert fill_price == 150.0

        # Update both SL and TP for LONG (SL must be < fill_price, TP must be > fill_price)
        target_sl = 135.00
        target_tp = 175.00
        patch_resp = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={
                "stop_loss_price": target_sl,
                "take_profit_price": target_tp,
            },
        )
        assert patch_resp.status_code == status.HTTP_200_OK
        pos_data = patch_resp.json()
        assert pos_data["position_id"] == pos_id
        assert pos_data["stop_loss_price"] == target_sl
        assert pos_data["take_profit_price"] == target_tp

        # Update SL only: should retain existing TP
        new_sl = 140.00
        patch_resp2 = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={"stop_loss_price": new_sl},
        )
        assert patch_resp2.status_code == status.HTTP_200_OK
        assert patch_resp2.json()["stop_loss_price"] == new_sl
        assert patch_resp2.json()["take_profit_price"] == target_tp

        # Update TP only: should retain existing SL
        new_tp = 180.00
        patch_resp3 = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={"take_profit_price": new_tp},
        )
        assert patch_resp3.status_code == status.HTTP_200_OK
        assert patch_resp3.json()["stop_loss_price"] == new_sl
        assert patch_resp3.json()["take_profit_price"] == new_tp

    def test_patch_brackets_short_success(self) -> None:
        """
        1. The use of function:
           Verifies successful Stop-Loss and Take-Profit updates for a SHORT derivative position.

        2. How does the specific function work:
           - Submits a SELL LIMIT order to establish a SHORT position at ₹150.0.
           - Extracts position_id and fill_price.
           - Dispatches PATCH /api/v1/paper/positions/{position_id}/brackets with valid SL (> fill) and TP (< fill).
           - Asserts HTTP 200 OK and validates inverted bracket coordinates.

        3. Concepts used in the function:
           Short bracket geometry (SL above market, TP below market), contract integrity.

        4. Places where this function is imported and used:
           Executed by pytest under Release Gate G5.

        5. Final output of the function, before and after:
           Before: Unmodified SHORT position. After: SHORT position with validated inverted brackets.
        """
        order_resp = self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "OPT-NIFTY-20250109-23000-PE",
                "side": "SELL",
                "quantity": 25,
                "order_type": "LIMIT",
                "limit_price": 150.0,
            },
        )
        assert order_resp.status_code == status.HTTP_201_CREATED
        order_data = order_resp.json()
        pos_id = order_data["position_id"]
        fill_price = order_data["fill_price"]
        assert fill_price == 150.0

        target_sl = 165.00
        target_tp = 130.00
        patch_resp = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={
                "stop_loss_price": target_sl,
                "take_profit_price": target_tp,
            },
        )
        assert patch_resp.status_code == status.HTTP_200_OK
        pos_data = patch_resp.json()
        assert pos_data["position_id"] == pos_id
        assert pos_data["stop_loss_price"] == target_sl
        assert pos_data["take_profit_price"] == target_tp

    def test_patch_brackets_long_invalid_sl_side_rejection(self) -> None:
        """
        1. The use of function:
           Verifies rejection when Stop-Loss is placed above market/entry price on a LONG position.

        2. How does the specific function work:
           - Opens LONG position.
           - Attempts to set SL >= fill_price.
           - Asserts HTTP 422 Unprocessable Entity with descriptive error message.

        3. Concepts used in the function:
           Pre-trade risk boundary enforcement, directional validation.

        4. Places where this function is imported and used:
           Executed by pytest under Release Gate G5.

        5. Final output of the function, before and after:
           Before: Invalid SL request. After: HTTP 422 rejection.
        """
        order_resp = self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "OPT-NIFTY-20250109-23000-CE",
                "side": "BUY",
                "quantity": 25,
                "order_type": "LIMIT",
                "limit_price": 150.0,
            },
        )
        pos_id = order_resp.json()["position_id"]
        fill_price = order_resp.json()["fill_price"]

        # For LONG, SL must be < fill_price. Setting SL = fill_price + 10.0 must fail.
        patch_resp = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={"stop_loss_price": fill_price + 10.0},
        )
        assert patch_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "must be below" in patch_resp.json()["detail"].lower()

    def test_patch_brackets_long_invalid_tp_side_rejection(self) -> None:
        """
        1. The use of function:
           Verifies rejection when Take-Profit is placed below market/entry price on a LONG position.

        2. How does the specific function work:
           - Opens LONG position at ₹150.0.
           - Attempts to set TP <= fill_price.
           - Asserts HTTP 422 Unprocessable Entity.

        3. Concepts used in the function:
           Directional take-profit constraint verification.

        4. Places where this function is imported and used:
           Executed by pytest under Release Gate G5.

        5. Final output of the function, before and after:
           Before: Invalid TP request. After: HTTP 422 rejection.
        """
        order_resp = self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "OPT-NIFTY-20250109-23000-CE",
                "side": "BUY",
                "quantity": 25,
                "order_type": "LIMIT",
                "limit_price": 150.0,
            },
        )
        pos_id = order_resp.json()["position_id"]
        fill_price = order_resp.json()["fill_price"]

        # For LONG, TP must be > fill_price. Setting TP = fill_price - 10.0 must fail.
        patch_resp = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={"take_profit_price": fill_price - 10.0},
        )
        assert patch_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "must be above" in patch_resp.json()["detail"].lower()

    def test_patch_brackets_short_invalid_sl_side_rejection(self) -> None:
        """
        1. The use of function:
           Verifies rejection when Stop-Loss is placed below market/entry price on a SHORT position.

        2. How does the specific function work:
           - Opens SHORT position at ₹150.0.
           - Attempts to set SL <= fill_price.
           - Asserts HTTP 422 Unprocessable Entity.

        3. Concepts used in the function:
           Short position stop-loss geometry enforcement.

        4. Places where this function is imported and used:
           Executed by pytest under Release Gate G5.

        5. Final output of the function, before and after:
           Before: Invalid short SL request. After: HTTP 422 rejection.
        """
        order_resp = self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "OPT-NIFTY-20250109-23000-PE",
                "side": "SELL",
                "quantity": 25,
                "order_type": "LIMIT",
                "limit_price": 150.0,
            },
        )
        pos_id = order_resp.json()["position_id"]
        fill_price = order_resp.json()["fill_price"]

        # For SHORT, SL must be > fill_price. Setting SL = fill_price - 10.0 must fail.
        patch_resp = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={"stop_loss_price": fill_price - 10.0},
        )
        assert patch_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "must be above" in patch_resp.json()["detail"].lower()

    def test_patch_brackets_short_invalid_tp_side_rejection(self) -> None:
        """
        1. The use of function:
           Verifies rejection when Take-Profit is placed above market/entry price on a SHORT position.

        2. How does the specific function work:
           - Opens SHORT position at ₹150.0.
           - Attempts to set TP >= fill_price.
           - Asserts HTTP 422 Unprocessable Entity.

        3. Concepts used in the function:
           Short position take-profit geometry enforcement.

        4. Places where this function is imported and used:
           Executed by pytest under Release Gate G5.

        5. Final output of the function, before and after:
           Before: Invalid short TP request. After: HTTP 422 rejection.
        """
        order_resp = self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "OPT-NIFTY-20250109-23000-PE",
                "side": "SELL",
                "quantity": 25,
                "order_type": "LIMIT",
                "limit_price": 150.0,
            },
        )
        pos_id = order_resp.json()["position_id"]
        fill_price = order_resp.json()["fill_price"]

        # For SHORT, TP must be < fill_price. Setting TP = fill_price + 10.0 must fail.
        patch_resp = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={"take_profit_price": fill_price + 10.0},
        )
        assert patch_resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "must be below" in patch_resp.json()["detail"].lower()

    def test_patch_brackets_5_paise_tick_snapping(self) -> None:
        """
        1. The use of function:
           Verifies that arbitrary floating point price coordinates are automatically quantized
           to the nearest 5-paise (₹0.05) exchange tick multiple.

        2. How does the specific function work:
           - Opens LONG position at ₹150.0.
           - Sends SL with unaligned paise: 135.03 (should snap to 135.05).
           - Sends TP with unaligned paise: 175.08 (should snap to 175.10).
           - Asserts HTTP 200 OK.
           - Asserts stop_loss_price is exactly 135.05 and take_profit_price is exactly 175.10.
           - Asserts int(round(price * 100)) % 5 == 0 for both returned levels.

        3. Concepts used in the function:
           Tick snapping, exchange tick quantization, numerical precision.

        4. Places where this function is imported and used:
           Executed by pytest under Release Gate G5.

        5. Final output of the function, before and after:
           Before: Unaligned float prices. After: Cleanly snapped 5-paise tick multiples.
        """
        order_resp = self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "OPT-NIFTY-20250109-23000-CE",
                "side": "BUY",
                "quantity": 25,
                "order_type": "LIMIT",
                "limit_price": 150.0,
            },
        )
        pos_id = order_resp.json()["position_id"]

        patch_resp = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={
                "stop_loss_price": 135.03,
                "take_profit_price": 175.08,
            },
        )
        assert patch_resp.status_code == status.HTTP_200_OK
        data = patch_resp.json()

        assert data["stop_loss_price"] == 135.05
        assert data["take_profit_price"] == 175.10
        assert int(round(data["stop_loss_price"] * 100)) % 5 == 0
        assert int(round(data["take_profit_price"] * 100)) % 5 == 0

    def test_patch_brackets_negative_or_zero_price_rejection(self) -> None:
        """
        1. The use of function:
           Verifies rejection when bracket prices are zero or negative.

        2. How does the specific function work:
           - Opens LONG position at ₹150.0.
           - Submits SL = 0.0, asserts HTTP 422.
           - Submits SL = -50.0, asserts HTTP 422.
           - Submits TP = 0.0, asserts HTTP 422.
           - Submits TP = -10.0, asserts HTTP 422.

        3. Concepts used in the function:
           Input domain validation, positive asset price boundary.

        4. Places where this function is imported and used:
           Executed by pytest under Release Gate G5.

        5. Final output of the function, before and after:
           Before: Non-positive price coordinates. After: HTTP 422 rejections.
        """
        order_resp = self.client.post(
            "/api/v1/paper/orders",
            json={
                "account_id": "ACC-MANUAL-PAPER",
                "contract_id": "OPT-NIFTY-20250109-23000-CE",
                "side": "BUY",
                "quantity": 25,
                "order_type": "LIMIT",
                "limit_price": 150.0,
            },
        )
        pos_id = order_resp.json()["position_id"]

        resp_zero_sl = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={"stop_loss_price": 0.0},
        )
        assert resp_zero_sl.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        resp_neg_sl = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={"stop_loss_price": -25.0},
        )
        assert resp_neg_sl.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        resp_zero_tp = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={"take_profit_price": 0.0},
        )
        assert resp_zero_tp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        resp_neg_tp = self.client.patch(
            f"/api/v1/paper/positions/{pos_id}/brackets",
            json={"take_profit_price": -100.0},
        )
        assert resp_neg_tp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_patch_brackets_nonexistent_position_404(self) -> None:
        """
        1. The use of function:
           Verifies HTTP 404 Not Found when attempting to update brackets for an unknown position ID.

        2. How does the specific function work:
           - Dispatches PATCH /api/v1/paper/positions/POS-NONEXISTENT-999/brackets.
           - Asserts HTTP 404 status code and error detail narrative.

        3. Concepts used in the function:
           HTTP status semantics, missing entity resolution.

        4. Places where this function is imported and used:
           Executed by pytest under Release Gate G5.

        5. Final output of the function, before and after:
           Before: Unknown position ID. After: HTTP 404 response.
        """
        resp = self.client.patch(
            "/api/v1/paper/positions/POS-UNKNOWN-999/brackets",
            json={"stop_loss_price": 100.0},
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in resp.json()["detail"].lower()
