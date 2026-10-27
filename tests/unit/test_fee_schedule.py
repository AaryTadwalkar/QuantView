"""
1. What this file does:
   Provides comprehensive unit and regression tests for the versioned, effective-dated regulatory
   fee schedule engine (Milestone M4-06).

2. Overall design:
   Uses pytest to verify:
     - Exact dynamic schedule resolution across statutory transition boundaries (2025-10-01, 2026-03-01, 2026-04-01).
     - Fail-closed behavior on unregistered historical trade dates.
     - Robust trade_date input normalization (str, date, datetime).
     - Exact statutory rounding for STT, NSE turnover charges, GST, SEBI fee, and stamp duty.
     - 100% byte-identical reconciliation against all 9 authoritative golden scenarios in tests/fixtures/golden_scenarios.py.
     - Custom fee schedule registration and parameter validation.

3. Elements in the file:
   - TestFeeScheduleEngine: Unit tests for schedule lookup, rate calculation, and statutory transitions.
   - TestGoldenScenariosFeeReconciliation: End-to-end reconciliation against hand-calculated test oracle.

4. Final output of the file:
   - Automated pass/fail test execution for Milestone M4-06.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from packages.domain import OrderSide, Paise
from packages.ledger.fees import (
    UPSTOX_2025_OCT,
    UPSTOX_2026_APR,
    UPSTOX_2026_MAR,
    FeeBreakdown,
    FeeSchedule,
    FeeScheduleEngine,
    get_default_fee_engine,
)
from tests.fixtures.golden_scenarios import ALL_GOLDEN_SCENARIOS


@pytest.mark.gate_g2a
class TestFeeScheduleEngine:
    """
    1. The use of class:
       Unit test suite for the versioned Indian regulatory fee engine.

    2. What the class contains:
       - test_dynamic_schedule_resolution_across_boundaries: Validates date interval lookups.
       - test_unregistered_trade_date_fails_closed: Asserts fail-closed ValueError on missing schedule.
       - test_date_normalization_types: Verifies date, datetime, and ISO string inputs.
       - test_buy_itemized_fee_structure: Validates stamp duty presence and STT absence on buy.
       - test_sell_itemized_fee_structure: Validates STT presence and stamp duty absence on sell.
       - test_stt_rate_transition_2026: Verifies 10 bps to 15 bps STT hike on April 1, 2026.
       - test_nse_turnover_rate_transition_2026: Verifies turnover charge increase on March 1, 2026.
       - test_negative_gross_value_raises_value_error: Verifies invalid parameter rejection.
       - test_custom_schedule_registration: Verifies engine extensibility.

    3. Technologies used and why:
       pytest assertions and parameterizations for boundary testing.

    4. Key design and overall design of the class:
       Covers all statutory calculation branches defined in Milestone M4-06.
    """

    def test_dynamic_schedule_resolution_across_boundaries(self):
        """
        1. The use of function:
           Tests that FeeScheduleEngine resolves the correct schedule across temporal boundaries.

        2. How does the specific function work:
           Tests boundary dates for OCT 2025, MAR 2026, and APR 2026 schedules.

        3. Concepts used in the function:
           Effective-dating and date-interval boundary testing.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unverified lookup. After: Verified resolution for each milestone date.
        """
        engine = get_default_fee_engine()

        # 1. Active under UPSTOX_2025_OCT (2024-10-01 to 2026-02-28)
        self.assertEqual_schedule = engine.resolve_schedule("2024-10-01")
        assert self.assertEqual_schedule.name == "UPSTOX_2025_OCT"

        mid_2025 = engine.resolve_schedule(date(2025, 6, 15))
        assert mid_2025.name == "UPSTOX_2025_OCT"

        end_feb_2026 = engine.resolve_schedule("2026-02-28")
        assert end_feb_2026.name == "UPSTOX_2025_OCT"

        # 2. Active under UPSTOX_2026_MAR (2026-03-01 to 2026-03-31)
        start_mar_2026 = engine.resolve_schedule(date(2026, 3, 1))
        assert start_mar_2026.name == "UPSTOX_2026_MAR"

        end_mar_2026 = engine.resolve_schedule("2026-03-31")
        assert end_mar_2026.name == "UPSTOX_2026_MAR"

        # 3. Active under UPSTOX_2026_APR (2026-04-01 onwards)
        start_apr_2026 = engine.resolve_schedule(date(2026, 4, 1))
        assert start_apr_2026.name == "UPSTOX_2026_APR"

        late_2026 = engine.resolve_schedule("2026-10-26")
        assert late_2026.name == "UPSTOX_2026_APR"

    def test_unregistered_trade_date_fails_closed(self):
        """
        1. The use of function:
           Verifies that requesting a fee schedule for an uncovered historical date fails closed.

        2. How does the specific function work:
           Passes 2024-01-01 (prior to 2024-10-01) and asserts that ValueError is raised.

        3. Concepts used in the function:
           Fail-closed safety principle.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unhandled date. After: Confirmed ValueError exception.
        """
        engine = FeeScheduleEngine()
        with pytest.raises(ValueError, match="No effective fee schedule found"):
            engine.resolve_schedule("2024-01-01")

    def test_date_normalization_types(self):
        """
        1. The use of function:
           Validates that resolve_schedule transparently accepts date, datetime, and ISO string inputs.

        2. How does the specific function work:
           Passes date, datetime, and ISO 8601 string representations of the same day.

        3. Concepts used in the function:
           Input normalization.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Raw date variations. After: Verified resolution across all types.
        """
        engine = get_default_fee_engine()
        d_date = date(2025, 5, 10)
        d_dt = datetime(2025, 5, 10, 14, 30, 0)
        d_str = "2025-05-10T14:30:00+05:30"

        assert engine.resolve_schedule(d_date).name == "UPSTOX_2025_OCT"
        assert engine.resolve_schedule(d_dt).name == "UPSTOX_2025_OCT"
        assert engine.resolve_schedule(d_str).name == "UPSTOX_2025_OCT"

    def test_buy_itemized_fee_structure(self):
        """
        1. The use of function:
           Tests exact itemized statutory charge calculations for a buy option order.

        2. How does the specific function work:
           Evaluates a buy order of Rs 2,501.25 (250,125 paise) on 2025-01-09.
           Checks flat brokerage (2000), STT (0), stamp duty (8), exch charges (88), and GST (376).

        3. Concepts used in the function:
           Contract note reconciliation and exact integer paise accounting.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unchecked buy fees. After: Verified itemized breakdown matching Indian regulations.
        """
        engine = get_default_fee_engine()
        breakdown = engine.calculate_order_fees(
            trade_date="2025-01-09",
            side=OrderSide.BUY,
            gross_value_paise=Paise(250125),
        )

        assert breakdown.brokerage_paise == 2000
        assert breakdown.stt_paise == 0  # No STT on buy
        assert breakdown.exchange_turnover_paise == 88  # 2501.25 * 0.0003503 = 0.8761 -> 88 paise
        assert breakdown.gst_paise == 376  # 18% of (2000 + 88) = 375.84 -> 376 paise
        assert breakdown.sebi_paise == 0
        assert breakdown.stamp_duty_paise == 8  # 0.003% of 2501.25 = 0.0750 -> 8 paise
        assert breakdown.total_fee_paise == 2472
        assert breakdown.total_fee_paise == (
            breakdown.brokerage_paise
            + breakdown.stt_paise
            + breakdown.exchange_turnover_paise
            + breakdown.gst_paise
            + breakdown.sebi_paise
            + breakdown.stamp_duty_paise
        )

    def test_sell_itemized_fee_structure(self):
        """
        1. The use of function:
           Tests exact itemized statutory charge calculations for a sell option order.

        2. How does the specific function work:
           Evaluates a sell order of Rs 2,748.75 (274,875 paise) on 2025-01-09.
           Checks STT (275), flat brokerage (2000), stamp duty (0), exch charges (96), and GST (377).

        3. Concepts used in the function:
           Contract note reconciliation for derivative sales.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unchecked sell fees. After: Verified itemized breakdown matching Indian regulations.
        """
        engine = get_default_fee_engine()
        breakdown = engine.calculate_order_fees(
            trade_date="2025-01-09",
            side=OrderSide.SELL,
            gross_value_paise=Paise(274875),
        )

        assert breakdown.brokerage_paise == 2000
        assert breakdown.stt_paise == 275  # 2748.75 * 0.0010 = 2.74875 -> 275 paise
        assert breakdown.exchange_turnover_paise == 96  # 2748.75 * 0.0003503 = 0.9628 -> 96 paise
        assert breakdown.gst_paise == 377  # 18% of (2000 + 96) = 377.28 -> 377 paise
        assert breakdown.sebi_paise == 0
        assert breakdown.stamp_duty_paise == 0  # No stamp duty on sell
        assert breakdown.total_fee_paise == 2748
        assert breakdown.total_fee_paise == (
            breakdown.brokerage_paise
            + breakdown.stt_paise
            + breakdown.exchange_turnover_paise
            + breakdown.gst_paise
            + breakdown.sebi_paise
            + breakdown.stamp_duty_paise
        )

    def test_stt_rate_transition_2026(self):
        """
        1. The use of function:
           Validates the statutory increase in STT from 0.10% to 0.15% on April 1, 2026.

        2. How does the specific function work:
           Compares identical Rs 2,498.75 sell trades executed on 2026-03-31 vs 2026-04-01.

        3. Concepts used in the function:
           Union Budget 2026 regulatory impact verification.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unverified transition. After: STT confirmed at 250 paise vs 375 paise.
        """
        engine = get_default_fee_engine()
        gross = Paise(249875)  # Rs 2,498.75

        # Before April 1, 2026: STT is 0.10% -> 2498.75 * 0.0010 = 2.498 -> 250 paise
        mar_fees = engine.calculate_order_fees("2026-03-31", OrderSide.SELL, gross)
        assert mar_fees.stt_paise == 250

        # On or after April 1, 2026: STT is 0.15% -> 2498.75 * 0.0015 = 3.748 -> 375 paise
        apr_fees = engine.calculate_order_fees("2026-04-01", OrderSide.SELL, gross)
        assert apr_fees.stt_paise == 375
        assert apr_fees.stt_paise - mar_fees.stt_paise == 125

    def test_nse_turnover_rate_transition_2026(self):
        """
        1. The use of function:
           Validates the NSE turnover charge adjustment from 0.03503% to 0.03553% on March 1, 2026.

        2. How does the specific function work:
           Compares exchange charges for a Rs 100,000 trade across February 2026 and March 2026.

        3. Concepts used in the function:
           NSE Circular FA73061 verification.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unverified turnover charge adjustment. After: Verified rate hike.
        """
        engine = get_default_fee_engine()
        turnover = Paise(10000000)  # Rs 1,00,000

        feb_fees = engine.calculate_order_fees("2026-02-28", OrderSide.BUY, turnover)
        mar_fees = engine.calculate_order_fees("2026-03-01", OrderSide.BUY, turnover)

        # Feb: 100,000 * 0.0003503 = 35.03 Rs -> 3503 paise
        assert feb_fees.exchange_turnover_paise == 3503
        # Mar: 100,000 * 0.0003553 = 35.53 Rs -> 3553 paise
        assert mar_fees.exchange_turnover_paise == 3553

    def test_negative_gross_value_raises_value_error(self):
        """
        1. The use of function:
           Ensures that calculate_order_fees rejects negative gross amounts.

        2. How does the specific function work:
           Passes Paise(-500) and asserts that ValueError is raised.

        3. Concepts used in the function:
           Defensive parameter validation.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Invalid input. After: Rejection via ValueError.
        """
        engine = get_default_fee_engine()
        with pytest.raises(ValueError, match="gross_value_paise must be non-negative"):
            engine.calculate_order_fees("2025-01-09", OrderSide.BUY, Paise(-500))

    def test_custom_schedule_registration(self):
        """
        1. The use of function:
           Verifies that custom fee schedules can be registered and resolved by the engine.

        2. How does the specific function work:
           Constructs a custom schedule with zero brokerage and registers it with a custom engine.

        3. Concepts used in the function:
           Engine extensibility and open-closed principle.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unregistered custom schedule. After: Custom schedule active and producing zero brokerage.
        """
        custom_sched = FeeSchedule(
            name="ZERO_BROKERAGE_PROMO",
            effective_from=date(2025, 1, 1),
            effective_to=date(2025, 1, 31),
            brokerage_per_order_paise=Paise(0),
        )
        custom_engine = FeeScheduleEngine(schedules=[custom_sched])
        breakdown = custom_engine.calculate_order_fees("2025-01-15", OrderSide.BUY, Paise(100000))
        assert breakdown.schedule_name == "ZERO_BROKERAGE_PROMO"
        assert breakdown.brokerage_paise == 0


@pytest.mark.gate_g2a
class TestGoldenScenariosFeeReconciliation:
    """
    1. The use of class:
       Reconciles FeeScheduleEngine outputs against the 9 frozen golden oracle scenarios.

    2. What the class contains:
       - test_reconcile_all_golden_scenario_fills: Asserts exact paisa-for-paisa agreement.

    3. Technologies used and why:
       pytest iterating over tests/fixtures/golden_scenarios.py.

    4. Key design and overall design of the class:
       Guarantees zero divergence between the hand-calculated oracle and the fee engine implementation.
    """

    def test_reconcile_all_golden_scenario_fills(self):
        """
        1. The use of function:
           Reconciles every fill in all 9 golden scenarios against the dynamic fee engine.

        2. How does the specific function work:
           Iterates over ALL_GOLDEN_SCENARIOS and each ExpectedFill, passes gross_value and side to engine,
           and asserts 100% equality on every itemized fee component down to the exact paisa.

        3. Concepts used in the function:
           Golden test oracle reconciliation.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unchecked fills. After: All 9 scenarios reconciled with zero paisa difference.
        """
        engine = get_default_fee_engine()
        total_fills_checked = 0

        for scenario in ALL_GOLDEN_SCENARIOS:
            for fill in scenario.expected_fills:
                side = OrderSide.BUY if fill.action == "BUY" else OrderSide.SELL
                actual = engine.calculate_order_fees(
                    trade_date=fill.bar_timestamp,
                    side=side,
                    gross_value_paise=Paise(fill.gross_value_paise),
                )

                assert actual.brokerage_paise == fill.brokerage_paise, (
                    f"[{scenario.scenario_id}] Brokerage mismatch: expected {fill.brokerage_paise}, got {actual.brokerage_paise}"
                )
                assert actual.stt_paise == fill.stt_paise, (
                    f"[{scenario.scenario_id}] STT mismatch: expected {fill.stt_paise}, got {actual.stt_paise}"
                )
                assert actual.exchange_turnover_paise == fill.exchange_turnover_paise, (
                    f"[{scenario.scenario_id}] Exchange charge mismatch: expected {fill.exchange_turnover_paise}, got {actual.exchange_turnover_paise}"
                )
                assert actual.gst_paise == fill.gst_paise, (
                    f"[{scenario.scenario_id}] GST mismatch: expected {fill.gst_paise}, got {actual.gst_paise}"
                )
                assert actual.sebi_paise == fill.sebi_paise, (
                    f"[{scenario.scenario_id}] SEBI mismatch: expected {fill.sebi_paise}, got {actual.sebi_paise}"
                )
                assert actual.stamp_duty_paise == fill.stamp_duty_paise, (
                    f"[{scenario.scenario_id}] Stamp duty mismatch: expected {fill.stamp_duty_paise}, got {actual.stamp_duty_paise}"
                )
                assert actual.total_fee_paise == fill.total_fee_paise, (
                    f"[{scenario.scenario_id}] Total fee mismatch: expected {fill.total_fee_paise}, got {actual.total_fee_paise}"
                )
                total_fills_checked += 1

        assert total_fills_checked >= 17, f"Expected at least 17 fills across 9 scenarios, got {total_fills_checked}"
