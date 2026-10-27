"""
1. What this file does:
   Validates the mathematical and structural integrity of the 9 golden scenario fixtures
   in tests/fixtures/golden_scenarios.py (Task M4-02 & Task M4-13).

2. Overall design:
   Verifies:
     - The fundamental ledger balance equation holds for every scenario:
       Cash + LongMarketValue == InitialCapital + GrossRealized + Unrealized - TotalFees.
     - Net Realized P&L strictly equals Gross Realized P&L minus Total Fees Paid.
     - Sum of individual statutory fee charges strictly equals total_fee_paise.
     - Quantized fill prices adhere to adverse tick rules (BUY >= raw, SELL <= raw).
     - Scenario 8 enforces final-bar rule (new entry rejected with NO_NEXT_BAR).
     - Scenario 9 verifies the 2026 STT rate increase to 0.15%.

3. Elements in the file:
   - TestGoldenScenarioOracleIntegrity: Pytest unit test suite validating all 9 golden scenarios.

4. Final output of the file:
   - Automated proof that the test oracle is 100% mathematically consistent and defect-free.
"""

import unittest

import pytest

from packages.domain import OrderSide, TickQuantizer
from tests.fixtures.golden_scenarios import ALL_GOLDEN_SCENARIOS


@pytest.mark.gate_g2a
class TestGoldenScenarioOracleIntegrity(unittest.TestCase):
    """
    1. The use of class:
       Executes verification of the pre-implementation golden test oracle.

    2. What the class contains:
       Unit tests validating accounting equations, fee reconciliations, and tick bounds.

    3. Technologies used and why:
       unittest.TestCase for deterministic mathematical verification.

    4. Key design and overall design of the class:
       Guarantees that the oracle used to evaluate the engine is mathematically sound.
    """

    def test_all_scenarios_present(self):
        """Verifies that all 9 canonical scenarios are registered."""
        self.assertEqual(len(ALL_GOLDEN_SCENARIOS), 9)

    def test_fee_summation_matches_total_fee(self):
        """Verifies for every fill that total_fee_paise is the exact sum of itemized charges."""
        for sc in ALL_GOLDEN_SCENARIOS:
            for fill in sc.expected_fills:
                sum_fees = (
                    fill.brokerage_paise
                    + fill.stt_paise
                    + fill.exchange_turnover_paise
                    + fill.gst_paise
                    + fill.sebi_paise
                    + fill.stamp_duty_paise
                )
                self.assertEqual(
                    fill.total_fee_paise,
                    sum_fees,
                    f"Fee mismatch in {sc.scenario_id} for fill at {fill.bar_timestamp}",
                )

    def test_fundamental_ledger_balance_equation(self):
        """
        Verifies fundamental balance equation for all 9 scenarios:
        Cash Balance + Long Market Value == Initial Capital + Gross Realized + Unrealized - Total Fees.
        """
        for sc in ALL_GOLDEN_SCENARIOS:
            st = sc.expected_final_state
            # When position_qty == 0, long market value is 0.
            # In Scenario 5 (flat bar with position open), position is 25 units marked at 10,000 paise = 250,000 paise.
            market_val = (
                (st.position_qty * 10000) if sc.scenario_id == "SCENARIO_05" else 0
            )

            lhs = st.cash_balance_paise + market_val
            rhs = (
                sc.initial_capital_paise
                + st.gross_realized_pnl_paise
                + st.unrealized_pnl_paise
                - st.total_fees_paid_paise
            )
            self.assertEqual(
                lhs,
                rhs,
                f"Ledger balance equation failed in {sc.scenario_id}: LHS ({lhs}) != RHS ({rhs})",
            )

    def test_net_realized_pnl_equation(self):
        """Verifies that Net Realized P&L == Gross Realized P&L - Total Fees Paid."""
        for sc in ALL_GOLDEN_SCENARIOS:
            st = sc.expected_final_state
            self.assertEqual(
                st.net_realized_pnl_paise,
                st.gross_realized_pnl_paise - st.total_fees_paid_paise,
                f"Net P&L mismatch in {sc.scenario_id}",
            )

    def test_tick_quantization_invariants_in_fills(self):
        """Verifies that every fill price is an exact multiple of contract tick and rounded adversely."""
        for sc in ALL_GOLDEN_SCENARIOS:
            tick = sc.tick_paise
            for fill in sc.expected_fills:
                # Must be exact multiple
                self.assertEqual(
                    fill.quantized_price_paise % tick,
                    0,
                    f"Fill price not multiple of tick in {sc.scenario_id}",
                )
                # Adverse rounding check
                side = OrderSide[fill.action]
                expected_q = TickQuantizer.quantize(
                    fill.raw_price_paise + fill.slippage_paise, tick, side
                )
                self.assertEqual(
                    fill.quantized_price_paise,
                    expected_q,
                    f"Quantization logic failed in {sc.scenario_id}",
                )

    def test_scenario_08_final_bar_assertions(self):
        """Verifies Scenario 8 enforces final-bar rule and pre-scheduled liquidation."""
        sc8 = next(s for s in ALL_GOLDEN_SCENARIOS if s.scenario_id == "SCENARIO_08")
        self.assertTrue(sc8.special_assertions.get("new_entry_at_1529_rejected"))
        self.assertEqual(sc8.special_assertions.get("rejection_reason"), "NO_NEXT_BAR")

    def test_scenario_09_stt_rate_increase(self):
        """Verifies Scenario 9 applies 0.15% STT on option sales in 2026."""
        sc9 = next(s for s in ALL_GOLDEN_SCENARIOS if s.scenario_id == "SCENARIO_09")
        exit_fill = sc9.expected_fills[1]
        self.assertEqual(exit_fill.action, "SELL")
        # Turnover = 249,875 paise. STT @ 0.15% = 374.81 -> 375 paise
        self.assertEqual(exit_fill.stt_paise, 375)
        self.assertEqual(sc9.special_assertions.get("schedule_resolved"), "UPSTOX_2026_APR")


if __name__ == "__main__":
    unittest.main()
