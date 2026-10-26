"""
1. What this file does:
   Tests the authoritative 39-field EngineRunConfig Pydantic model (Task M4-18).
   Verifies schema validation, mandatory positive capital, temporal validation, and deterministic config hash.

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §19.1:
     - Tests all required and default fields.
     - Rejects missing or non-positive capital_paise.
     - Rejects inverted date ranges.
     - Confirms SHA-256 config hash determinism and sensitivity.

3. Elements in the file:
   - TestEngineRunConfig: Test suite covering all M4-18 validation rules.

4. Final output of the file:
   - Unit test execution results for EngineRunConfig.
"""

import unittest
import pytest
from packages.engine.config import EngineRunConfig
from packages.domain import OperatingMode


@pytest.mark.gate_g2a
class TestEngineRunConfig(unittest.TestCase):
    """
    1. The use of class:
       Unit test cases validating EngineRunConfig according to ENGINE §19.1.

    2. What the class contains:
       - test_valid_default_run_config: Verifies valid configuration instantiation.
       - test_mandatory_capital_paise_required: Verifies rejection if capital is omitted.
       - test_negative_or_zero_capital_rejected: Verifies rejection if capital <= 0.
       - test_temporal_bounds_ordering: Verifies start_date <= end_date.
       - test_deterministic_config_hash: Verifies byte-identical hash stability and field sensitivity.
       - test_alias_reconciliation: Verifies initial_capital_paise and strategy_name cross-mapping.

    3. Technologies used and why:
       unittest.TestCase for test isolation.

    4. Key design and overall design of the class:
       Binds Invariant 14 to automated negative and positive unit tests.
    """

    def test_valid_default_run_config(self):
        """
        1. The use of function:
           Tests that a valid config with required fields instantiates cleanly with correct defaults.

        2. How does the specific function work:
           Provides minimal required fields and checks defaults.

        3. Concepts used in the function:
           Pydantic field validation.

        4. Places where this function is imported and used:
           Executed by pytest runner.

        5. Final output of the function, before and after:
           Before: Unvalidated parameters. After: Validated EngineRunConfig instance.
        """
        cfg = EngineRunConfig(
            start_date="2025-01-01",
            end_date="2025-01-31",
            strategy_id="LongCETrendFollowing",
            capital_paise=10_000_000,
        )
        self.assertEqual(cfg.capital_paise, 10_000_000)
        self.assertEqual(cfg.initial_capital_paise, 10_000_000)
        self.assertEqual(cfg.strategy_id, "LongCETrendFollowing")
        self.assertEqual(cfg.strategy_name, "LongCETrendFollowing")
        self.assertEqual(cfg.decision_timeframe, "5m")
        self.assertEqual(cfg.expiry_policy, "NEAREST_ELIGIBLE")
        self.assertEqual(cfg.intrabar_stop_policy, "STOP_FIRST")
        self.assertEqual(cfg.force_flat_time, "15:25")
        self.assertEqual(len(cfg.compute_config_hash()), 64)

    def test_mandatory_capital_paise_required(self):
        """
        1. The use of function:
           Tests that omitting capital raises a ValueError per Invariant 14.

        2. How does the specific function work:
           Attempts instantiation without capital_paise and asserts ValueError.

        3. Concepts used in the function:
           Mandatory non-null validation.

        4. Places where this function is imported and used:
           Executed by pytest runner.

        5. Final output of the function, before and after:
           Before: Missing capital. After: Raised ValueError.
        """
        with self.assertRaises(ValueError):
            EngineRunConfig(
                start_date="2025-01-01",
                end_date="2025-01-31",
                strategy_id="LongCETrendFollowing",
            )

    def test_negative_or_zero_capital_rejected(self):
        """
        1. The use of function:
           Tests that non-positive capital values are rejected.

        2. How does the specific function work:
           Passes 0 and -5000000 and asserts ValueError.

        3. Concepts used in the function:
           Strict boundary validation.

        4. Places where this function is imported and used:
           Executed by pytest runner.

        5. Final output of the function, before and after:
           Before: Invalid capital. After: Raised ValueError.
        """
        with self.assertRaises(ValueError):
            EngineRunConfig(
                start_date="2025-01-01",
                end_date="2025-01-31",
                strategy_id="LongCETrendFollowing",
                capital_paise=0,
            )

        with self.assertRaises(ValueError):
            EngineRunConfig(
                start_date="2025-01-01",
                end_date="2025-01-31",
                strategy_id="LongCETrendFollowing",
                capital_paise=-100_000,
            )

    def test_temporal_bounds_ordering(self):
        """
        1. The use of function:
           Tests that start_date > end_date is rejected.

        2. How does the specific function work:
           Passes start_date="2025-02-01" and end_date="2025-01-01" and asserts ValueError.

        3. Concepts used in the function:
           Causal temporal validation.

        4. Places where this function is imported and used:
           Executed by pytest runner.

        5. Final output of the function, before and after:
           Before: Inverted date range. After: Raised ValueError.
        """
        with self.assertRaises(ValueError):
            EngineRunConfig(
                start_date="2025-02-01",
                end_date="2025-01-01",
                strategy_id="LongCETrendFollowing",
                capital_paise=5_000_000,
            )

    def test_deterministic_config_hash(self):
        """
        1. The use of function:
           Verifies hash determinism and field sensitivity.

        2. How does the specific function work:
           Instantiates two configs with identical parameters and asserts equal hash.
           Modifies one parameter and asserts different hash.

        3. Concepts used in the function:
           SHA-256 cryptographic provenance.

        4. Places where this function is imported and used:
           Executed by pytest runner.

        5. Final output of the function, before and after:
           Before: Config instances. After: Validated hash equality and difference.
        """
        c1 = EngineRunConfig(
            run_id="run_fixed_id",
            start_date="2025-01-01",
            end_date="2025-01-31",
            strategy_id="LongCETrendFollowing",
            capital_paise=10_000_000,
        )
        c2 = EngineRunConfig(
            run_id="run_fixed_id",
            start_date="2025-01-01",
            end_date="2025-01-31",
            strategy_id="LongCETrendFollowing",
            capital_paise=10_000_000,
        )
        c3 = EngineRunConfig(
            run_id="run_fixed_id",
            start_date="2025-01-01",
            end_date="2025-01-31",
            strategy_id="LongCETrendFollowing",
            capital_paise=20_000_000,
        )
        self.assertEqual(c1.compute_config_hash(), c2.compute_config_hash())
        self.assertNotEqual(c1.compute_config_hash(), c3.compute_config_hash())

    def test_alias_reconciliation(self):
        """
        1. The use of function:
           Verifies initial_capital_paise and strategy_name cross-mapping.

        2. How does the specific function work:
           Instantiates using initial_capital_paise and strategy_name.

        3. Concepts used in the function:
           Parameter normalization.

        4. Places where this function is imported and used:
           Executed by pytest runner.

        5. Final output of the function, before and after:
           Before: Legacy aliases. After: Normalized fields.
        """
        cfg = EngineRunConfig(
            start_date="2025-01-01",
            end_date="2025-01-31",
            strategy_name="LongPEMeanReversion",
            initial_capital_paise=5_000_000,
            fee_schedule_name="UPSTOX_2026_MAR",
        )
        self.assertEqual(cfg.capital_paise, 5_000_000)
        self.assertEqual(cfg.strategy_id, "LongPEMeanReversion")
        self.assertEqual(cfg.fee_schedule_version, "UPSTOX_2026_MAR")


if __name__ == "__main__":
    unittest.main()
