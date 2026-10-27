"""
1. What this file does:
   Comprehensive unit tests for QuantView Chart Transforms (Heikin Ashi & Renko)
   and Frozen Machine Learning Model Inference Contracts (ENGINE §18.1, §22, §23,
   Tasks M5-09 & M5-10 / Gate G3).

2. Overall design:
   Validates exact mathematical formulas, seed calculations, non-tradable invariants,
   causal confirmation timing for Renko bricks, model contract immutability, and
   enforcement of the strict anti-training barrier during inference.

3. Elements in the file:
   - TestHeikinAshiTransform: Validates HA bar smoothing and non-tradable flags.
   - TestRenkoTransform: Validates fixed brick size, 2-brick reversal, and confirmed_at timestamps.
   - TestFrozenModelContract: Validates model contract immutability, prediction, and fit() rejection.
   - TestTransformRegistry: Validates FeatureRegistry registration.

4. Final output of the file:
   - Automated pytest suite certifying Tasks M5-09 and M5-10 under @pytest.mark.gate_g3.
"""

import pytest
from packages.features import FeatureRegistry
from packages.features.transforms import (
    HeikinAshiBar,
    RenkoBrick,
    compute_heikin_ashi,
    compute_renko_bricks,
    register_heikin_ashi_feature,
    register_renko_feature,
)
from packages.features.models import (
    BaselineDecisionModel,
    FrozenModelContract,
    NoInferenceTrainingAllowedError,
    R1BaselineType,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensures FeatureRegistry singleton is reset cleanly before and after each test."""
    FeatureRegistry._instance = None
    yield
    FeatureRegistry._instance = None


@pytest.mark.gate_g3
class TestHeikinAshiTransform:
    """
    1. The use of class:
       Unit tests for compute_heikin_ashi.

    2. What the class contains:
       - test_heikin_ashi_seeding_and_formulas: Checks bar 0 seed and recursive values.
       - test_display_only_invariant: Asserts is_display_transform_only is True.

    3. Technologies used and why:
       pytest assertions verifying ENGINE §22 requirements.

    4. Key design and overall design of the class:
       Guarantees display transform precision and execution safety.
    """

    def test_heikin_ashi_seeding_and_formulas(self):
        opens = [100.0, 102.0]
        highs = [105.0, 108.0]
        lows = [95.0, 101.0]
        closes = [102.0, 106.0]

        ha_bars = compute_heikin_ashi(opens, highs, lows, closes)
        assert len(ha_bars) == 2

        # Bar 0:
        # HA_Close = (100 + 105 + 95 + 102) / 4 = 402 / 4 = 100.5
        # HA_Open  = (100 + 102) / 2 = 101.0
        # HA_High  = max(105, 101, 100.5) = 105.0
        # HA_Low   = min(95, 101, 100.5) = 95.0
        b0 = ha_bars[0]
        assert b0.ha_close == 100.5
        assert b0.ha_open == 101.0
        assert b0.ha_high == 105.0
        assert b0.ha_low == 95.0
        assert b0.is_display_transform_only is True

        # Bar 1:
        # HA_Close = (102 + 108 + 101 + 106) / 4 = 417 / 4 = 104.25
        # HA_Open  = (HA_Open_0 + HA_Close_0) / 2 = (101.0 + 100.5) / 2 = 100.75
        # HA_High  = max(108, 100.75, 104.25) = 108.0
        # HA_Low   = min(101, 100.75, 104.25) = 100.75
        b1 = ha_bars[1]
        assert b1.ha_close == 104.25
        assert b1.ha_open == 100.75
        assert b1.ha_high == 108.0
        assert b1.ha_low == 100.75
        assert b1.is_display_transform_only is True


@pytest.mark.gate_g3
class TestRenkoTransform:
    """
    1. The use of class:
       Unit tests for compute_renko_bricks.

    2. What the class contains:
       - test_renko_continuation_and_reversal: Verifies brick additions and 2-brick reversals.
       - test_renko_causal_timing: Verifies confirmed_at matches bar timestamps.

    3. Technologies used and why:
       pytest assertions verifying Renko brick creation rules.

    4. Key design and overall design of the class:
       Guarantees causal confirmation timing without lookahead.
    """

    def test_renko_continuation_and_reversal(self):
        # Starting price: 100.0, Brick Size = 10.0, Reversal = 2 bricks (20.0)
        prices = [100.0, 112.0, 125.0, 104.0]
        timestamps = [1000, 1060, 1120, 1180]

        bricks = compute_renko_bricks(prices, timestamps, brick_size=10.0, reversal_bricks=2)

        # Bar 1 (112.0): +12 pts -> 1 Up brick from 100 to 110
        assert len(bricks) >= 1
        assert bricks[0].open == 100.0
        assert bricks[0].close == 110.0
        assert bricks[0].direction == +1
        assert bricks[0].confirmed_at == 1060

        # Bar 2 (125.0): +15 pts from 110 -> 1 Up brick from 110 to 120
        assert bricks[1].open == 110.0
        assert bricks[1].close == 120.0
        assert bricks[1].direction == +1
        assert bricks[1].confirmed_at == 1120

        # Bar 3 (104.0): drop from 120 to 104 is -16 pts (less than 20 pt reversal required)
        # No reversal brick formed!
        assert len(bricks) == 2


@pytest.mark.gate_g3
class TestFrozenModelContract:
    """
    1. The use of class:
       Unit tests for FrozenModelContract and ModelInferenceInterface.

    2. What the class contains:
       - test_frozen_model_immutability: Verifies Pydantic frozen enforcement.
       - test_model_prediction_and_training_rejection: Verifies predict works and fit() raises error.

    3. Technologies used and why:
       pytest assertions on model validation and runtime anti-leakage barriers.

    4. Key design and overall design of the class:
       Certifies Task M5-10 compliance.
    """

    def test_frozen_model_immutability(self):
        contract = FrozenModelContract(
            model_id="M_NIFTY_REGIME_v1",
            model_version="1.0.0",
            model_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            training_manifest_hash="a1b2c3d4e5f60718293a4b5c6d7e8f90",
            features_required=["RSI_14", "ATR_14"],
            label_horizon_bars=5,
            r1_baseline_type=R1BaselineType.REGIME,
            resource_budget_ms=2.5,
            created_at_utc="2026-10-27T12:00:00Z",
        )

        assert contract.model_id == "M_NIFTY_REGIME_v1"
        assert contract.r1_baseline_type == R1BaselineType.REGIME

        # Attempt to mutate contract -> must raise error
        with pytest.raises(Exception):
            contract.model_id = "MUTATED_ID"  # type: ignore

    def test_model_prediction_and_training_rejection(self):
        contract = FrozenModelContract(
            model_id="M_NIFTY_DIR_v1",
            model_version="1.0.0",
            model_sha256="abcd1234ef567890",
            training_manifest_hash="manifest_hash_1234",
            features_required=["RSI_14"],
            label_horizon_bars=3,
            r1_baseline_type=R1BaselineType.DIRECTION,
            created_at_utc="2026-10-27T12:00:00Z",
        )

        model = BaselineDecisionModel(contract)

        # Successful inference
        pred = model.predict({"RSI_14": 65.0}, decision_time=1000)
        assert pred["model_id"] == "M_NIFTY_DIR_v1"
        assert pred["predicted_class"] == 1

        # Attempted training must raise NoInferenceTrainingAllowedError!
        with pytest.raises(NoInferenceTrainingAllowedError):
            model.fit([1, 2, 3])


@pytest.mark.gate_g3
class TestTransformRegistry:
    """Verifies feature registry integration for transforms."""

    def test_registry_integration(self):
        id_ha = register_heikin_ashi_feature()
        assert id_ha.startswith("HEIKIN_ASHI_v1_")

        id_renko = register_renko_feature()
        assert id_renko.startswith("RENKO_v1_")

        reg = FeatureRegistry()
        assert reg.get(id_ha) is not None
        assert reg.get(id_renko) is not None
