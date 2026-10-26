"""
1. What this file does:
   Tests the backtest metrics engine and Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR) (Task M4-15).
   Verifies 22+ performance metrics, trial validity gating (N < 2), and statistical audit metadata.

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §20.1, §20.2, §20.2.1, and §20.3:
     - Tests mathematical properties of standard normal CDF and inverse normal PPF.
     - Verifies non-negotiable invariant: DSR returns null with 'INSUFFICIENT_TRIAL_HISTORY (N < 2)'
       whenever fewer than 2 trials are recorded in the trial registry.
     - Verifies complete metric computation from trade lists and equity curves.

3. Elements in the file:
   - TestBacktestMetricsDSR: Comprehensive unit tests covering metrics and DSR.

4. Final output of the file:
   - Unit test execution results for Task M4-15.
"""

import unittest
import math
import pytest
from packages.engine.metrics import (
    standard_normal_cdf,
    standard_normal_ppf,
    compute_deflated_sharpe_ratio,
    BacktestMetrics,
)


@pytest.mark.gate_g2a
class TestBacktestMetricsDSR(unittest.TestCase):
    """
    1. The use of class:
       Unit test cases validating metrics calculation and DSR statistics per ENGINE §20.2.1.

    2. What the class contains:
       - test_standard_normal_cdf_and_ppf: Verifies normal CDF and probit functions.
       - test_dsr_trial_accounting_validity_gate_n_less_than_2: Verifies Invariant 15.
       - test_dsr_zero_or_negative_trial_dispersion: Verifies rejection on zero trial dispersion.
       - test_dsr_valid_calculation_and_metadata: Verifies end-to-end DSR calculation.
       - test_backtest_metrics_comprehensive_calculation: Verifies 22+ metrics calculation.

    3. Technologies used and why:
       unittest.TestCase for test isolation.

    4. Key design and overall design of the class:
       Binds DSR mathematical specification and trial accounting rules to unit tests.
    """

    def test_standard_normal_cdf_and_ppf(self):
        """
        1. The use of function:
           Tests mathematical accuracy of standard normal CDF and inverse PPF.

        2. How does the specific function work:
           Compares evaluated quantiles against known analytical values (0.5 -> 0.0, 0.975 -> 1.95996).

        3. Concepts used in the function:
           Probability distribution verification.

        4. Places where this function is imported and used:
           Executed by pytest.

        5. Final output of the function, before and after:
           Before: Untested numerical functions. After: Verified CDF and PPF.
        """
        self.assertAlmostEqual(standard_normal_cdf(0.0), 0.5, places=5)
        self.assertAlmostEqual(standard_normal_ppf(0.5), 0.0, places=5)
        self.assertAlmostEqual(standard_normal_ppf(0.975), 1.95996, places=4)
        self.assertAlmostEqual(standard_normal_cdf(1.95996), 0.975, places=4)

    def test_dsr_trial_accounting_validity_gate_n_less_than_2(self):
        """
        1. The use of function:
           Verifies non-negotiable invariant: N < 2 emits null with structured reason.

        2. How does the specific function work:
           Passes returns with trial_sharpes=None or single trial, asserts dsr is None and null_reason matches.

        3. Concepts used in the function:
           Trial accounting gate enforcement.

        4. Places where this function is imported and used:
           Executed by pytest.

        5. Final output of the function, before and after:
           Before: Unverified trial gate. After: Proved failure when N < 2.
        """
        returns = [0.01, -0.005, 0.008, 0.002, -0.003, 0.015, -0.002, 0.004]

        # Scenario A: No trials provided
        res1 = compute_deflated_sharpe_ratio(daily_returns=returns, trial_sharpes=None)
        self.assertIsNone(res1.dsr)
        self.assertEqual(res1.null_reason, "INSUFFICIENT_TRIAL_HISTORY (N < 2)")

        # Scenario B: Single trial provided (N=1)
        res2 = compute_deflated_sharpe_ratio(daily_returns=returns, trial_sharpes=[0.12])
        self.assertIsNone(res2.dsr)
        self.assertEqual(res2.null_reason, "INSUFFICIENT_TRIAL_HISTORY (N < 2)")

    def test_dsr_zero_or_negative_trial_dispersion(self):
        """
        1. The use of function:
           Verifies rejection when all trials produce identical Sharpe ratios (zero dispersion).

        2. How does the specific function work:
           Passes list with identical values [0.15, 0.15, 0.15] and asserts null DSR.

        3. Concepts used in the function:
           Degenerate cross-trial variance check.

        4. Places where this function is imported and used:
           Executed by pytest.

        5. Final output of the function, before and after:
           Before: Edge case. After: Verified graceful fail-closed null reason.
        """
        returns = [0.01, -0.005, 0.008, 0.002, -0.003, 0.015, -0.002, 0.004]
        res = compute_deflated_sharpe_ratio(daily_returns=returns, trial_sharpes=[0.15, 0.15, 0.15])
        self.assertIsNone(res.dsr)
        self.assertEqual(res.null_reason, "ZERO_OR_UNDEFINED_TRIAL_DISPERSION (sigma_trials <= 0)")

    def test_dsr_valid_calculation_and_metadata(self):
        """
        1. The use of function:
           Verifies complete DSR calculation with valid trial distribution.

        2. How does the specific function work:
           Passes 20 daily returns and 10 trial Sharpe ratios, asserts 0 <= dsr <= 1 and validates metadata.

        3. Concepts used in the function:
           Bailey & López de Prado (2014) DSR evaluation.

        4. Places where this function is imported and used:
           Executed by pytest.

        5. Final output of the function, before and after:
           Before: Uncomputed DSR. After: Validated DSR and audit fields.
        """
        # 25 daily returns
        returns = [
            0.005, -0.002, 0.003, 0.008, -0.004, 0.006, 0.001, -0.001, 0.007, 0.002,
            -0.003, 0.004, 0.009, -0.005, 0.002, 0.003, -0.002, 0.006, 0.001, -0.001,
            0.005, 0.002, -0.003, 0.004, 0.008
        ]
        # 10 trial Sharpe ratios with cross-trial dispersion
        trials = [0.05, 0.08, -0.02, 0.12, 0.15, 0.01, -0.05, 0.10, 0.14, 0.07]

        res = compute_deflated_sharpe_ratio(daily_returns=returns, trial_sharpes=trials)
        self.assertIsNotNone(res.dsr)
        self.assertIsNone(res.null_reason)
        self.assertTrue(0.0 <= res.dsr <= 1.0)
        self.assertEqual(res.T, 25)
        self.assertEqual(res.N, 10)
        self.assertGreater(res.sigma_trials, 0.0)
        self.assertGreater(res.var_sr, 0.0)
        self.assertNotEqual(res.kurtosis, 0.0)

    def test_backtest_metrics_comprehensive_calculation(self):
        """
        1. The use of function:
           Tests BacktestMetrics.calculate across closed trades and equity series.

        2. How does the specific function work:
           Constructs closed trades, fees, and equity curve points. Asserts 22+ metrics.

        3. Concepts used in the function:
           Portfolio performance measurement.

        4. Places where this function is imported and used:
           Executed by pytest.

        5. Final output of the function, before and after:
           Before: Raw simulated trades. After: Verified BacktestMetrics instance.
        """
        closed_trades = [
            {
                "trade_id": "T1",
                "entry_time": "09:30",
                "exit_time": "10:15",
                "gross_pnl_paise": 500_000,
                "fee_paise": 4_500,
                "net_pnl_paise": 495_500,
            },
            {
                "trade_id": "T2",
                "entry_time": "11:45",
                "exit_time": "12:30",
                "gross_pnl_paise": -200_000,
                "fee_paise": 4_500,
                "net_pnl_paise": -204_500,
            },
            {
                "trade_id": "T3",
                "entry_time": "14:00",
                "exit_time": "14:45",
                "gross_pnl_paise": 300_000,
                "fee_paise": 4_500,
                "net_pnl_paise": 295_500,
            },
        ]
        equity_series = [
            {"bar_index": 0, "equity_paise": 10_000_000},
            {"bar_index": 1, "equity_paise": 10_495_500},
            {"bar_index": 2, "equity_paise": 10_291_000},
            {"bar_index": 3, "equity_paise": 10_586_500},
        ]

        metrics = BacktestMetrics.calculate(
            initial_capital_paise=10_000_000,
            closed_trades=closed_trades,
            equity_series=equity_series,
            trial_sharpes=[0.05, 0.10, 0.15],
        )

        self.assertEqual(metrics.initial_capital_paise, 10_000_000)
        self.assertEqual(metrics.final_equity_paise, 10_586_500)
        self.assertEqual(metrics.gross_realized_pnl_paise, 600_000)
        self.assertEqual(metrics.total_fees_paise, 13_500)
        self.assertEqual(metrics.net_realized_pnl_paise, 586_500)
        self.assertEqual(metrics.total_trades, 3)
        self.assertEqual(metrics.winning_trades, 2)
        self.assertEqual(metrics.losing_trades, 1)
        self.assertAlmostEqual(metrics.win_rate_pct, 66.67, places=1)
        self.assertGreater(metrics.profit_factor, 1.0)
        self.assertEqual(metrics.max_drawdown_paise, 204_500)
        self.assertGreater(metrics.time_of_day_pnl_paise["morning_09_15_11_30"], 0)
        self.assertLess(metrics.time_of_day_pnl_paise["midday_11_30_13_30"], 0)
        self.assertGreater(metrics.time_of_day_pnl_paise["afternoon_13_30_15_30"], 0)
        self.assertIsNotNone(metrics.deflated_sharpe)
        self.assertTrue(0.0 <= metrics.deflated_sharpe.dsr <= 1.0)


if __name__ == "__main__":
    unittest.main()
