"""
1. What this file does:
   Comprehensive unit tests for QuantView Order Flow and Depth Proxies:
   Snapshot Top-of-Book Depth Imbalance and Candle Bar Volume Delta Proxy
   (ENGINE §21.1, Gate G3).

2. Overall design:
   Validates ratio formulas, strict fail-closed zero-depth guards (null rather than 0.0),
   candle position volume attribution, and edge-case handling for flat and zero-volume bars.

3. Elements in the file:
   - TestDepthImbalance: Tests depth imbalance ratios and empty book null guards.
   - TestCandleVolumeDelta: Tests close location value attribution, flat bars, and zero-volume bars.
   - TestOrderflowRegistry: Tests feature registry integration.

4. Final output of the file:
   - Automated pytest suite certifying Phase 5G under @pytest.mark.gate_g3.
"""

import pytest
from packages.features import FeatureRegistry
from packages.features.orderflow import (
    DepthImbalanceResult,
    CandleDeltaResult,
    compute_depth_imbalance,
    compute_candle_volume_delta,
    compute_series_candle_delta,
    register_depth_imbalance_feature,
    register_candle_delta_feature,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensures FeatureRegistry singleton is reset cleanly before and after each test."""
    FeatureRegistry._instance = None
    yield
    FeatureRegistry._instance = None


@pytest.mark.gate_g3
class TestDepthImbalance:
    """
    1. The use of class:
       Unit tests for compute_depth_imbalance.

    2. What the class contains:
       - test_depth_imbalance_ratios: Asserts bounded ratios in [-1.0, +1.0].
       - test_zero_depth_guard: Asserts that empty order book emits None, NOT 0.0.

    3. Technologies used and why:
       pytest assertions on mathematical edge cases.

    4. Key design and overall design of the class:
       Guarantees market depth proxies fail-closed on missing liquidity.
    """

    def test_depth_imbalance_ratios(self):
        # Heavy bid: (300 - 100) / 400 = +0.5000
        res_bid = compute_depth_imbalance(bid_qty=300, ask_qty=100)
        assert res_bid.is_valid is True
        assert res_bid.depth_imbalance == 0.5000
        assert res_bid.total_depth_qty == 400
        assert res_bid.quality_flags == ["VALID"]

        # Heavy ask: (100 - 300) / 400 = -0.5000
        res_ask = compute_depth_imbalance(bid_qty=100, ask_qty=300)
        assert res_ask.is_valid is True
        assert res_ask.depth_imbalance == -0.5000

        # Perfect symmetry: (200 - 200) / 400 = 0.0000
        res_sym = compute_depth_imbalance(bid_qty=200, ask_qty=200)
        assert res_sym.is_valid is True
        assert res_sym.depth_imbalance == 0.0000

    def test_zero_depth_guard(self):
        # Empty order book: Must return None, NEVER 0.0!
        res_empty = compute_depth_imbalance(bid_qty=0, ask_qty=0)
        assert res_empty.is_valid is False
        assert res_empty.depth_imbalance is None
        assert res_empty.total_depth_qty == 0
        assert "EMPTY_ORDER_BOOK" in res_empty.quality_flags


@pytest.mark.gate_g3
class TestCandleVolumeDelta:
    """
    1. The use of class:
       Unit tests for compute_candle_volume_delta and compute_series_candle_delta.

    2. What the class contains:
       - test_candle_delta_attribution: Tests bull, bear, and neutral close positions.
       - test_zero_volume_and_flat_bar: Tests volume=0 and high=low edge cases.

    3. Technologies used and why:
       pytest assertions verifying bar volume delta formulas.

    4. Key design and overall design of the class:
       Validates candle position proxy mechanics.
    """

    def test_candle_delta_attribution(self):
        # Bull bar: close at high (CLV = 1.0) -> 100% buy volume
        res_bull = compute_candle_volume_delta(high=110.0, low=100.0, close=110.0, volume=1000)
        assert res_bull.buy_ratio == 1.0
        assert res_bull.est_buy_volume == 1000.0
        assert res_bull.est_sell_volume == 0.0
        assert res_bull.bar_volume_delta == 1000.0

        # Bear bar: close at low (CLV = 0.0) -> 100% sell volume
        res_bear = compute_candle_volume_delta(high=110.0, low=100.0, close=100.0, volume=1000)
        assert res_bear.buy_ratio == 0.0
        assert res_bear.est_buy_volume == 0.0
        assert res_bear.est_sell_volume == 1000.0
        assert res_bear.bar_volume_delta == -1000.0

        # Doji bar: close at midpoint (CLV = 0.5) -> 50% buy, 50% sell, delta = 0
        res_doji = compute_candle_volume_delta(high=110.0, low=100.0, close=105.0, volume=1000)
        assert res_doji.buy_ratio == 0.5
        assert res_doji.est_buy_volume == 500.0
        assert res_doji.est_sell_volume == 500.0
        assert res_doji.bar_volume_delta == 0.0

    def test_zero_volume_and_flat_bar(self):
        # Zero volume
        res_zv = compute_candle_volume_delta(high=105.0, low=100.0, close=102.0, volume=0)
        assert res_zv.bar_volume_delta == 0.0
        assert "ZERO_VOLUME_BAR" in res_zv.quality_flags

        # Flat bar (H = L = C)
        res_flat = compute_candle_volume_delta(high=100.0, low=100.0, close=100.0, volume=500)
        assert res_flat.buy_ratio == 0.5
        assert res_flat.bar_volume_delta == 0.0
        assert "FLAT_BAR" in res_flat.quality_flags


@pytest.mark.gate_g3
class TestOrderflowRegistry:
    """Verifies orderflow feature registration in FeatureRegistry."""

    def test_registry_integration(self):
        id_depth = register_depth_imbalance_feature()
        assert id_depth.startswith("DEPTH_IMBALANCE_v1_")

        id_delta = register_candle_delta_feature()
        assert id_delta.startswith("CANDLE_VOLUME_DELTA_v1_")

        reg = FeatureRegistry()
        assert reg.get(id_depth) is not None
        assert reg.get(id_delta) is not None
