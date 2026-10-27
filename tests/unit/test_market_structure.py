"""
1. What this file does:
   Comprehensive unit, causality, boundary, and state-machine testing suite for QuantView
   deterministic BOS / CHoCH Market Structure Engine (ENGINE §21.2, Task M5-06 / Gate G3).

2. Overall design:
   Validates swing pivot detection with asymmetric tie-breaking, delayed causal confirmation timing
   (confirmed_at = ts_close(i + W_R)), one-time level consumption, and the canonical three-state
   market bias transition matrix (NEUTRAL, BULLISH, BEARISH) under close-through and touch criteria.
   Verifies anti-lookahead causality via Prefix Invariance and Future Perturbation protocols.

3. Elements in the file:
   - TestPivotConfirmationAndTiming: Asserts causal confirmation lag and prevents lookahead.
   - TestAsymmetricTieBreaking: Tests plateau and double-top/bottom earliest-bar selection.
   - TestBoundaryAndConsumption: Tests boundary close comparisons and one-time level consumption.
   - TestMarketBiasTransitions: Validates full classification matrix (BOS vs CHoCH) and resolved Bearish CHoCH.
   - TestAmbiguousDoubleBreak: Tests TOUCH double-break handling and AMBIGUOUS_DOUBLE_BREAK flag.
   - TestStructureCausalityProtocols: Runs Prefix Invariance and Future Perturbation verification.
   - TestDeterministicReplay: Asserts bitwise identical outputs across repeated runs.

4. Final output of the file:
   - Automated pytest suite certifying Phase 5C under @pytest.mark.gate_g3.
"""

import math
import pytest
from typing import List

from packages.features import (
    FeatureRegistry,
    verify_future_perturbation,
    verify_prefix_invariance,
)
from packages.features.structure import (
    BreakCriterion,
    MarketBias,
    MarketStructureBar,
    MarketStructureEngine,
    StructuralEvent,
    compute_market_structure,
    register_market_structure_feature,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """
    1. The use of function:
       Ensures FeatureRegistry singleton is reset cleanly before and after each test.
    """
    registry = FeatureRegistry()
    registry.clear()
    yield
    registry.clear()


@pytest.mark.gate_g3
class TestPivotConfirmationAndTiming:
    """
    1. The use of class:
       Validates delayed causal confirmation: pivot at bar i becomes visible strictly at i + W_R.

    2. What the class contains:
       - test_pivot_confirmation_timing: Verifies swing high at i=5 confirmed at t=10 (W_L=5, W_R=5).
       - test_no_premature_pivot_visibility: Verifies level is invisible at bars t < i + W_R.
    """

    def test_pivot_confirmation_timing(self):
        """
        1. The use of function:
           Verifies that a swing high at bar index 5 is confirmed and visible strictly at bar 10.
        """
        # Create a series with a clear peak at index 5:
        # Bars 0..4: rising (10, 11, 12, 13, 14)
        # Bar 5: peak (20)
        # Bars 6..10: falling (14, 13, 12, 11, 10)
        highs = [10.0, 11.0, 12.0, 13.0, 14.0, 20.0, 14.0, 13.0, 12.0, 11.0, 10.0]
        lows = [h - 2.0 for h in highs]
        closes = [h - 1.0 for h in highs]

        engine = MarketStructureEngine(pivot_left=5, pivot_right=5)
        bars = engine.evaluate_series(highs, lows, closes)

        # At bars 0..9, no swing high is confirmed yet
        for t in range(10):
            assert bars[t].last_confirmed_high_price is None

        # At bar 10 (5 + 5), swing high from bar 5 is confirmed at price 20.0
        assert bars[10].last_confirmed_high_price == 20.0
        assert bars[10].last_confirmed_high_time == 5

    def test_no_premature_pivot_visibility(self):
        """
        1. The use of function:
           Asserts that no breakout can be triggered before confirmed_index, even if close exceeds pivot price.
        """
        # Peak at i=5 (high=20.0), but at bar 7 (before confirmation at bar 10), close spikes to 22.0
        highs = [10.0, 11.0, 12.0, 13.0, 14.0, 20.0, 14.0, 22.0, 12.0, 11.0, 10.0]
        lows = [h - 2.0 for h in highs]
        closes = [h - 1.0 for h in highs]

        engine = MarketStructureEngine(pivot_left=5, pivot_right=5)
        bars = engine.evaluate_series(highs, lows, closes)

        # Bar 7 close is 21.0 (> 20.0), but bar 5 was NOT confirmed (in fact bar 7 violates bar 5 peak!)
        # Therefore no breakout can fire at bar 7
        assert bars[7].structural_event == StructuralEvent.NONE


@pytest.mark.gate_g3
class TestAsymmetricTieBreaking:
    """
    1. The use of class:
       Validates strict left inequality vs non-strict right inequality for plateau tie-breaking.
    """

    def test_plateau_earliest_bar_selection(self):
        """
        1. The use of function:
           Verifies that when two consecutive bars share the maximum price (plateau),
           the earliest bar is selected as candidate, and the second bar is rejected.
        """
        # Peak plateau at bar 5 and bar 6 with high = 25.0
        highs = [10.0, 12.0, 14.0, 16.0, 18.0, 25.0, 25.0, 18.0, 16.0, 14.0, 12.0, 10.0]
        lows = [h - 2.0 for h in highs]
        closes = [h - 1.0 for h in highs]

        engine = MarketStructureEngine(pivot_left=5, pivot_right=5)
        bars = engine.evaluate_series(highs, lows, closes)

        # Bar 5 confirmed at bar 10 (5 + 5):
        # Bar 5 has high 25.0 > highs[0..4], and high 25.0 >= highs[6..10].
        # Bar 6 evaluated at bar 11: bar 6 high 25.0 is NOT strictly > bar 5 high (25.0), so rejected!
        assert bars[10].last_confirmed_high_price == 25.0
        assert bars[10].last_confirmed_high_time == 5

        # Bar 11 retains bar 5 as the confirmed pivot
        assert bars[11].last_confirmed_high_time == 5


@pytest.mark.gate_g3
class TestBoundaryAndConsumption:
    """
    1. The use of class:
       Validates boundary price comparisons (strict close-through) and one-time level consumption.
    """

    def test_close_through_strict_boundary(self):
        """
        1. The use of function:
           Verifies that close == level.price does NOT break, while close = level.price + 0.01 breaks.
        """
        # Set up a confirmed high at 100.0 (W_L=2, W_R=2 for compact test)
        highs = [80.0, 90.0, 100.0, 90.0, 80.0, 99.99, 100.0, 100.01]
        lows = [h - 5.0 for h in highs]
        # Closes: bar 5 closes at 99.99, bar 6 closes at 100.0 (touch), bar 7 closes at 100.01 (break)
        closes = [h - 2.0 for h in highs]
        closes[5] = 99.99
        closes[6] = 100.0
        closes[7] = 100.01

        engine = MarketStructureEngine(pivot_left=2, pivot_right=2)
        bars = engine.evaluate_series(highs, lows, closes)

        # Peak at i=2 (high=100.0) confirmed at t=4
        assert bars[4].last_confirmed_high_price == 100.0

        # Bar 5 (close=99.99): no break
        assert bars[5].structural_event == StructuralEvent.NONE

        # Bar 6 (close=100.0): equal to price, no break under CLOSE_THROUGH
        assert bars[6].structural_event == StructuralEvent.NONE

        # Bar 7 (close=100.01): penetrates level, triggers break!
        assert bars[7].structural_event == StructuralEvent.BULLISH_CHOCH
        assert bars[7].broken_level_price == 100.0

    def test_one_time_level_consumption(self):
        """
        1. The use of function:
           Verifies that a broken level is marked consumed and cannot trigger subsequent events.
        """
        highs = [80.0, 90.0, 100.0, 90.0, 80.0, 105.0, 110.0, 115.0]
        lows = [h - 5.0 for h in highs]
        closes = [h - 1.0 for h in highs]

        engine = MarketStructureEngine(pivot_left=2, pivot_right=2)
        bars = engine.evaluate_series(highs, lows, closes)

        # Level 100.0 broken on bar 5 (close=104.0)
        assert bars[5].structural_event == StructuralEvent.BULLISH_CHOCH
        assert bars[5].broken_level_price == 100.0

        # Bar 6 (close=109.0) and Bar 7 (close=114.0) are higher, but level 100.0 is consumed!
        # No subsequent breaks fire until a new confirmed high is created
        assert bars[6].structural_event == StructuralEvent.NONE
        assert bars[6].last_confirmed_high_price is None
        assert bars[7].structural_event == StructuralEvent.NONE


@pytest.mark.gate_g3
class TestMarketBiasTransitions:
    """
    1. The use of class:
       Validates the complete 6-row Market Bias and Event Classification matrix per ENGINE §21.2.
    """

    def test_full_classification_matrix(self):
        """
        1. The use of function:
           Verifies NEUTRAL CHoCH, BULLISH continuation BOS, BULLISH reversal to BEARISH CHoCH,
           BEARISH continuation BOS, and BEARISH reversal to BULLISH CHoCH.
        """
        engine = MarketStructureEngine(pivot_left=2, pivot_right=2)

        # 1. Starts NEUTRAL
        assert engine.current_bias == MarketBias.NEUTRAL

        # Establish confirmed high at 100.0 and low at 70.0
        # Peak at i=2 (high=100), Trough at i=4 (low=70)
        highs = [80.0, 90.0, 100.0, 90.0, 75.0, 78.0, 82.0]
        lows = [75.0, 78.0, 85.0, 78.0, 70.0, 72.0, 75.0]
        closes = [78.0, 85.0, 95.0, 82.0, 72.0, 75.0, 80.0]

        bars = engine.evaluate_series(highs, lows, closes)
        # High confirmed at bar 4 (price=100.0), Low confirmed at bar 6 (price=70.0)

        # --- Test 1: NEUTRAL + Break High -> BULLISH_CHOCH (New Bias: BULLISH) ---
        # Bar 7 breaks high 100.0
        h7 = [105.0]
        l7 = [80.0]
        c7 = [102.0]
        bars_7 = engine.evaluate_series(highs + h7, lows + l7, closes + c7)
        assert bars_7[7].structural_event == StructuralEvent.BULLISH_CHOCH
        assert bars_7[7].market_bias == MarketBias.BULLISH

        # --- Test 2: BULLISH + Break High -> BULLISH_BOS (New Bias: BULLISH) ---
        # Suppose a new high forms at 110.0 and is broken while bias is BULLISH
        engine_bull = MarketStructureEngine(pivot_left=2, pivot_right=2)
        engine_bull.current_bias = MarketBias.BULLISH
        engine_bull.active_swing_high = engine.active_swing_high._replace(price=110.0, confirmed_index=0, is_consumed=False)
        bars_bos = engine_bull.evaluate_series([115.0], [105.0], [112.0])
        assert bars_bos[0].structural_event == StructuralEvent.BULLISH_BOS
        assert bars_bos[0].market_bias == MarketBias.BULLISH

        # --- Test 3: BULLISH + Break Low -> BEARISH_CHOCH (New Bias: BEARISH) ---
        engine_rev_to_bear = MarketStructureEngine(pivot_left=2, pivot_right=2)
        engine_rev_to_bear.current_bias = MarketBias.BULLISH
        engine_rev_to_bear.active_swing_low = engine.active_swing_low._replace(price=70.0, confirmed_index=0, is_consumed=False)
        bars_rev = engine_rev_to_bear.evaluate_series([75.0], [65.0], [68.0])
        assert bars_rev[0].structural_event == StructuralEvent.BEARISH_CHOCH
        assert bars_rev[0].market_bias == MarketBias.BEARISH

        # --- Test 4: BEARISH + Break Low -> BEARISH_BOS (New Bias: BEARISH) ---
        engine_bear = MarketStructureEngine(pivot_left=2, pivot_right=2)
        engine_bear.current_bias = MarketBias.BEARISH
        engine_bear.active_swing_low = engine.active_swing_low._replace(price=60.0, confirmed_index=0, is_consumed=False)
        bars_bear_bos = engine_bear.evaluate_series([65.0], [50.0], [55.0])
        assert bars_bear_bos[0].structural_event == StructuralEvent.BEARISH_BOS
        assert bars_bear_bos[0].market_bias == MarketBias.BEARISH

        # --- Test 5: BEARISH + Break High -> BULLISH_CHOCH (New Bias: BULLISH) ---
        # (Resolving the documented convention: event is BULLISH_CHOCH, resulting bias is BULLISH)
        engine_rev_to_bull = MarketStructureEngine(pivot_left=2, pivot_right=2)
        engine_rev_to_bull.current_bias = MarketBias.BEARISH
        engine_rev_to_bull.active_swing_high = engine.active_swing_high._replace(price=100.0, confirmed_index=0, is_consumed=False)
        bars_bear_to_bull = engine_rev_to_bull.evaluate_series([105.0], [90.0], [102.0])
        assert bars_bear_to_bull[0].structural_event == StructuralEvent.BULLISH_CHOCH
        assert bars_bear_to_bull[0].market_bias == MarketBias.BULLISH

    def test_neutral_break_low_transition(self):
        """
        1. The use of function:
           Verifies NEUTRAL initial bias + break low -> BEARISH_CHOCH (New Bias: BEARISH).
        """
        engine = MarketStructureEngine(pivot_left=2, pivot_right=2)
        assert engine.current_bias == MarketBias.NEUTRAL

        highs = [80.0, 75.0, 70.0, 75.0, 80.0, 82.0, 60.0]
        lows = [70.0, 65.0, 60.0, 65.0, 70.0, 72.0, 50.0]
        closes = [72.0, 68.0, 62.0, 68.0, 72.0, 75.0, 55.0]

        bars = engine.evaluate_series(highs, lows, closes)
        # Trough at i=2 (low=60.0) confirmed at t=4
        # Bar 6 breaks low 60.0 with close 55.0
        assert bars[6].structural_event == StructuralEvent.BEARISH_CHOCH
        assert bars[6].market_bias == MarketBias.BEARISH


@pytest.mark.gate_g3
class TestAmbiguousDoubleBreak:
    """
    1. The use of class:
       Validates ambiguous double-break handling under TOUCH criterion per ENGINE §21.2.
    """

    def test_touch_double_break_flag_and_resolution(self):
        """
        1. The use of function:
           Verifies that an outside bar touching both high and low levels is flagged AMBIGUOUS_DOUBLE_BREAK
           and follows conservative trend-reversal policy.
        """
        engine = MarketStructureEngine(pivot_left=2, pivot_right=2, break_criterion=BreakCriterion.TOUCH)
        engine.current_bias = MarketBias.BULLISH

        from packages.features.structure.bos_choch import SwingLevel
        engine.active_swing_high = SwingLevel(price=100.0, pivot_index=0, pivot_time=0, confirmed_index=0, confirmed_at=0, is_consumed=False)
        engine.active_swing_low = SwingLevel(price=50.0, pivot_index=0, pivot_time=0, confirmed_index=0, confirmed_at=0, is_consumed=False)

        # Bar has high 105 (>100) and low 45 (<50) -> touches both
        bars = engine.evaluate_series([105.0], [45.0], [75.0])

        assert "AMBIGUOUS_DOUBLE_BREAK" in bars[0].quality_flags
        # Conservative reversal policy from BULLISH: bearish break takes precedence
        assert bars[0].structural_event == StructuralEvent.BEARISH_CHOCH
        assert bars[0].market_bias == MarketBias.BEARISH


@pytest.mark.gate_g3
class TestStructureCausalityProtocols:
    """
    1. The use of class:
       Validates Prefix Invariance and Future Perturbation on market structure engine.
    """

    @pytest.fixture
    def sample_ohlc(self):
        """
        1. The use of function:
           Generates 50 bars of synthetic staircase prices.
        """
        h: List[float] = []
        l: List[float] = []
        c: List[float] = []
        for i in range(50):
            base = 100.0 + 10.0 * (i // 10) + (i % 10) * 2.0
            h.append(base + 2.0)
            l.append(base - 2.0)
            c.append(base)
        return (h, l, c)

    def test_prefix_invariance_structure(self, sample_ohlc):
        """
        1. The use of function:
           Verifies that evaluating market structure on truncated series [0..t] yields identical
           last_confirmed_high_price as evaluating on full series [0..T].
        """
        h, l, c = sample_ohlc

        def get_confirmed_high(sub_c):
            sub_len = len(sub_c)
            bars = compute_market_structure(h[:sub_len], l[:sub_len], sub_c, pivot_left=3, pivot_right=3)
            return [b.last_confirmed_high_price if b.last_confirmed_high_price is not None else float("nan") for b in bars]

        assert verify_prefix_invariance(get_confirmed_high, c, cut_points=[15, 25, 35, 45]) is True

    def test_future_perturbation_structure(self, sample_ohlc):
        """
        1. The use of function:
           Verifies that mutating future prices does not alter confirmed levels or bias up to decision time.
        """
        h, l, c = sample_ohlc

        def get_confirmed_high_series(full_c):
            bars = compute_market_structure(h, l, full_c, pivot_left=3, pivot_right=3)
            return [b.last_confirmed_high_price if b.last_confirmed_high_price is not None else float("nan") for b in bars]

        assert verify_future_perturbation(get_confirmed_high_series, c, t_decision=25) is True


@pytest.mark.gate_g3
class TestDeterministicReplay:
    """
    1. The use of class:
       Validates bitwise determinism across repeated executions of market structure.
    """

    def test_replay_exact_equality(self):
        """
        1. The use of function:
           Verifies that two runs on the same series emit identical records.
        """
        h = [10.0, 12.0, 15.0, 14.0, 12.0, 11.0, 10.0, 9.0, 8.0, 12.0, 16.0]
        l = [8.0, 10.0, 13.0, 11.0, 10.0, 9.0, 8.0, 7.0, 6.0, 10.0, 14.0]
        c = [9.0, 11.0, 14.0, 12.0, 11.0, 10.0, 9.0, 8.0, 7.0, 11.0, 15.0]

        bars_1 = compute_market_structure(h, l, c, pivot_left=2, pivot_right=2)
        bars_2 = compute_market_structure(h, l, c, pivot_left=2, pivot_right=2)

        assert len(bars_1) == len(bars_2)
        for b1, b2 in zip(bars_1, bars_2):
            assert b1.structural_event == b2.structural_event
            assert b1.market_bias == b2.market_bias
            assert b1.last_confirmed_high_price == b2.last_confirmed_high_price
            assert b1.last_confirmed_low_price == b2.last_confirmed_low_price
            assert b1.broken_level_price == b2.broken_level_price
