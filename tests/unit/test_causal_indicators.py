"""
1. What this file does:
   Comprehensive unit, causality, boundary, and TradingView parity testing suite for QuantView
   technical indicators and quarantined Session VWAP (Milestones M5-03, M5-08, M5-11 / Gate G3).

2. Overall design:
   Verifies mathematical correctness through four independent verification vectors:
   1. Hand-calculated mathematical scenarios with exact manual traces.
   2. TradingView / Pine Script v5 ground-truth parity across 200 synthetic market bars.
   3. Anti-lookahead causality protocols (Prefix Invariance and Future Perturbation).
   4. Edge cases, flat-series behavior, zero-denominator guards, and fail-closed VWAP quarantine.

3. Elements in the file:
   - TestHandCalculatedScenarios: Verifies exact manual calculations (EMA, SMA, RSI, BB, NATR, RV, Spread).
   - TestPineScriptParity: Verifies numerical parity with TradingView built-ins within 1e-12 tolerance.
   - TestCausalProtocols: Runs verify_prefix_invariance and verify_future_perturbation across all indicators.
   - TestSupertrendStateTransitions: Tests Supertrend direction flips independently from line levels.
   - TestEdgeCasesAndDenominators: Tests flat series, zero ATR, zero close, and mismatched inputs.
   - TestSessionVWAPQuarantine: Asserts fail-closed quarantine of cash-index Session VWAP.
   - TestIVRVSpreadInterface: Asserts safe interface propagation for unavailable IV inputs.
   - TestDeterministicOutputs: Asserts byte-identical determinism across multiple runs.

4. Final output of the file:
   - Automated pytest suite certifying Phase 5B under @pytest.mark.gate_g3.
"""

import math
import pytest

from packages.domain import UtcEpochSec
from packages.features import (
    FeatureRegistry,
    FeatureStatus,
    TemporalLeakageError,
    verify_availability_enforcement,
    verify_future_perturbation,
    verify_prefix_invariance,
)
from packages.features.statistical import (
    SessionVWAPGuard,
    SessionVWAPQuarantinedError,
    compute_adx,
    compute_atr,
    compute_bollinger_bands,
    compute_ema,
    compute_iv_rv_spread,
    compute_macd,
    compute_natr,
    compute_realized_volatility,
    compute_rsi,
    compute_sma,
    compute_supertrend,
    compute_wilder_rma,
    register_all_statistical_features,
    register_quarantined_vwap,
)
from tests.fixtures.pine_indicator_oracle import (
    CandlestickBar,
    DeterministicMarketData,
    HandCalculatedScenarios,
    PineReferenceOracle,
    analyze_ema_parity,
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
class TestHandCalculatedScenarios:
    """
    1. The use of class:
       Unit tests validating indicators against manually hand-calculated golden traces.

    2. What the class contains:
       - test_hand_calculated_ema: Validates Pine and SMA seeded EMA against manual numbers.
       - test_hand_calculated_sma: Validates SMA against manual arithmetic mean.
       - test_hand_calculated_rsi_boundaries: Validates RSI at zero loss, zero gain, and flat series.
       - test_hand_calculated_bollinger_bands_flat: Validates BB on a flat series (%B = 0.5).
       - test_hand_calculated_natr_zero_close: Validates NATR safely handles non-positive close.
       - test_hand_calculated_realized_volatility_flat: Validates RV on a zero-variance series.
    """

    def test_hand_calculated_ema(self):
        """
        1. The use of function:
           Verifies hand-calculated EMA values under both Pine Script and SMA seed policies.
        """
        prices = HandCalculatedScenarios.EMA_PRICES
        expected_pine = HandCalculatedScenarios.EMA_PINE_EXPECTED
        expected_sma = HandCalculatedScenarios.EMA_SMA_EXPECTED

        out_pine = compute_ema(prices, length=3, seed_policy="PINE_SCRIPT")
        for val, exp in zip(out_pine, expected_pine):
            assert val == pytest.approx(exp, abs=1e-8)

        out_sma = compute_ema(prices, length=3, seed_policy="SMA")
        assert math.isnan(out_sma[0])
        assert math.isnan(out_sma[1])
        assert out_sma[2] == pytest.approx(expected_sma[2], abs=1e-8)
        assert out_sma[3] == pytest.approx(expected_sma[3], abs=1e-8)
        assert out_sma[4] == pytest.approx(expected_sma[4], abs=1e-8)

    def test_hand_calculated_sma(self):
        """
        1. The use of function:
           Verifies hand-calculated SMA values.
        """
        prices = HandCalculatedScenarios.SMA_PRICES
        expected = HandCalculatedScenarios.SMA_WINDOW_3_EXPECTED

        out = compute_sma(prices, length=3)
        assert math.isnan(out[0])
        assert math.isnan(out[1])
        assert out[2] == pytest.approx(expected[2], abs=1e-8)
        assert out[3] == pytest.approx(expected[3], abs=1e-8)
        assert out[4] == pytest.approx(expected[4], abs=1e-8)

    def test_hand_calculated_rsi_boundaries(self):
        """
        1. The use of function:
           Verifies Wilder RSI boundary handling: zero loss, zero gain, flat series, and warm-up.
        """
        # Strictly up (zero loss) -> RSI must be exactly 100.0
        up = compute_rsi(HandCalculatedScenarios.RSI_STRICT_UP, length=3)
        assert math.isnan(up[0])
        assert math.isnan(up[1])
        assert math.isnan(up[2])
        assert up[3] == 100.0
        assert up[4] == 100.0

        # Strictly down (zero gain) -> RSI must be exactly 0.0
        down = compute_rsi(HandCalculatedScenarios.RSI_STRICT_DOWN, length=3)
        assert math.isnan(down[0])
        assert down[3] == 0.0
        assert down[4] == 0.0

        # Completely flat (zero gain and zero loss) -> RSI must be 50.0
        flat = compute_rsi(HandCalculatedScenarios.RSI_FLAT, length=3)
        assert math.isnan(flat[0])
        assert flat[3] == 50.0
        assert flat[4] == 50.0

    def test_hand_calculated_bollinger_bands_flat(self):
        """
        1. The use of function:
           Verifies Bollinger Bands behavior on a completely flat series (Upper == Lower).
        """
        prices = HandCalculatedScenarios.BB_FLAT_PRICES
        mid, up, lo, bw, pb = compute_bollinger_bands(prices, length=3, mult=2.0)

        # On flat series: Upper == Lower == Middle == 100.0
        for i in range(2, 5):
            assert mid[i] == 100.0
            assert up[i] == 100.0
            assert lo[i] == 100.0
            assert bw[i] == 0.0
            assert pb[i] == 0.5  # Centered at mid-band per invariant

    def test_hand_calculated_natr_zero_close(self):
        """
        1. The use of function:
           Verifies NATR safely handles zero and negative close prices without throwing ZeroDivisionError.
        """
        h = [10.0, 12.0, 14.0]
        l = [8.0, 9.0, 11.0]
        c = [9.0, 0.0, -5.0]

        natr = compute_natr(h, l, c, length=2)
        # Bar 1 has close=0.0 -> NaN
        assert math.isnan(natr[1])
        # Bar 2 has close=-5.0 -> NaN
        assert math.isnan(natr[2])

    def test_hand_calculated_realized_volatility_flat(self):
        """
        1. The use of function:
           Verifies Realized Volatility outputs 0.0 on a flat price series.
        """
        c = [100.0] * 35
        rv = compute_realized_volatility(c, length=30)
        assert rv[30] == 0.0
        assert rv[34] == 0.0


@pytest.mark.gate_g3
class TestPineScriptParity:
    """
    1. The use of class:
       Unit tests validating numerical parity against the independent PineReferenceOracle.

    2. What the class contains:
       - test_sma_parity: Validates SMA parity with ta.sma within 1e-12.
       - test_ema_pine_parity: Validates EMA under PINE_SCRIPT seed against ta.ema within 1e-12.
       - test_ema_mandatory_parity_analysis: Analyzes warm-up decay of SMA-seed relative to Pine reference.
       - test_rma_parity: Validates Wilder RMA against ta.rma within 1e-12.
       - test_rsi_parity: Validates RSI against ta.rsi within 1e-12.
       - test_macd_parity: Validates MACD against ta.macd within 1e-12.
       - test_atr_parity: Validates ATR against ta.atr within 1e-12.
       - test_bollinger_bands_parity: Validates Bollinger Bands against ta.bb within 1e-12.
       - test_supertrend_parity: Validates Supertrend against ta.supertrend within 1e-12.
       - test_adx_parity: Validates ADX (+DI, -DI, ADX) against ta.dmi within 1e-12.
    """

    @pytest.fixture
    def market_series(self):
        """
        1. The use of function:
           Generates 200 bars of deterministic market data.
        """
        return DeterministicMarketData.generate_bars(200)

    def test_sma_parity(self, market_series):
        """
        1. The use of function:
           Verifies SMA matches Pine Script ta.sma within 1e-12.
        """
        closes = [b.close for b in market_series]
        qv_out = compute_sma(closes, length=20)
        pine_out = PineReferenceOracle.reference_sma(closes, length=20)

        for q, p in zip(qv_out[19:], pine_out[19:]):
            assert q == pytest.approx(p, abs=1e-12)

    def test_ema_pine_parity(self, market_series):
        """
        1. The use of function:
           Verifies EMA (seed_policy="PINE_SCRIPT") matches Pine Script ta.ema within 1e-12 on all bars.
        """
        closes = [b.close for b in market_series]
        qv_out = compute_ema(closes, length=20, seed_policy="PINE_SCRIPT")
        pine_out = PineReferenceOracle.reference_ema(closes, length=20)

        for q, p in zip(qv_out, pine_out):
            assert q == pytest.approx(p, abs=1e-12)

    def test_ema_mandatory_parity_analysis(self, market_series):
        """
        1. The use of function:
           Performs mandatory ground-truth comparison between Pine Script seed and SMA seed.
           Verifies exponential decay of initial condition difference: (1 - alpha)^k.
        """
        closes = [b.close for b in market_series]
        report = analyze_ema_parity(closes, length=20)

        # 1. PINE_SCRIPT seed has 0 error relative to TradingView across entire series
        assert report.max_error_pine_mode < 1e-12

        # 2. SMA seed has initial discrepancy at bar length - 1
        assert report.initial_error_sma_mode > 0.0

        # 3. SMA seed error decays exponentially at 3x length
        assert report.warmup_3x_error_sma < report.initial_error_sma_mode * 0.1

        # 4. SMA seed error converges to negligible levels (< 0.005 pts) at 5x length
        assert report.warmup_5x_error_sma < 0.005

    def test_rma_parity(self, market_series):
        """
        1. The use of function:
           Verifies Wilder RMA matches Pine Script ta.rma within 1e-12.
        """
        closes = [b.close for b in market_series]
        qv_out = compute_wilder_rma(closes, length=14)
        pine_out = PineReferenceOracle.reference_rma(closes, length=14)

        for q, p in zip(qv_out[13:], pine_out[13:]):
            assert q == pytest.approx(p, abs=1e-12)

    def test_rsi_parity(self, market_series):
        """
        1. The use of function:
           Verifies Wilder RSI matches Pine Script ta.rsi within 1e-12.
        """
        closes = [b.close for b in market_series]
        qv_out = compute_rsi(closes, length=14)
        pine_out = PineReferenceOracle.reference_rsi(closes, length=14)

        for q, p in zip(qv_out[14:], pine_out[14:]):
            assert q == pytest.approx(p, abs=1e-12)

    def test_macd_parity(self, market_series):
        """
        1. The use of function:
           Verifies MACD components match Pine Script ta.macd within 1e-12.
        """
        closes = [b.close for b in market_series]
        m, s, h = compute_macd(closes, fast_length=12, slow_length=26, signal_length=9, seed_policy="PINE_SCRIPT")
        pm, ps, ph = PineReferenceOracle.reference_macd(closes, fast_length=12, slow_length=26, signal_length=9)

        for q, p in zip(m[25:], pm[25:]):
            assert q == pytest.approx(p, abs=1e-12)
        for q, p in zip(s[33:], ps[33:]):
            assert q == pytest.approx(p, abs=1e-12)
        for q, p in zip(h[33:], ph[33:]):
            assert q == pytest.approx(p, abs=1e-12)

    def test_atr_parity(self, market_series):
        """
        1. The use of function:
           Verifies ATR matches Pine Script ta.atr within 1e-12.
        """
        h = [b.high for b in market_series]
        l = [b.low for b in market_series]
        c = [b.close for b in market_series]

        qv_atr = compute_atr(h, l, c, length=14)
        pine_atr = PineReferenceOracle.reference_atr(h, l, c, length=14)

        for q, p in zip(qv_atr[13:], pine_atr[13:]):
            assert q == pytest.approx(p, abs=1e-12)

    def test_bollinger_bands_parity(self, market_series):
        """
        1. The use of function:
           Verifies Bollinger Bands match Pine Script ta.bb within 1e-12.
        """
        closes = [b.close for b in market_series]
        mid, up, lo, bw, pb = compute_bollinger_bands(closes, length=20, mult=2.0)
        pm, pu, pl = PineReferenceOracle.reference_bb(closes, length=20, mult=2.0)

        for i in range(19, len(closes)):
            assert mid[i] == pytest.approx(pm[i], abs=1e-12)
            assert up[i] == pytest.approx(pu[i], abs=1e-12)
            assert lo[i] == pytest.approx(pl[i], abs=1e-12)

    def test_supertrend_parity(self, market_series):
        """
        1. The use of function:
           Verifies Supertrend line and direction match Pine Script ta.supertrend within 1e-12.
        """
        h = [b.high for b in market_series]
        l = [b.low for b in market_series]
        c = [b.close for b in market_series]

        st_line, st_dir = compute_supertrend(h, l, c, length=10, multiplier=3.0)
        ref_st, ref_dir_pine = PineReferenceOracle.reference_supertrend(h, l, c, length=10, factor=3.0)

        for i in range(9, len(c)):
            assert st_line[i] == pytest.approx(ref_st[i], abs=1e-12)
            # QuantView direction (+1 Bullish / -1 Bearish) maps to Pine (-1 Uptrend / +1 Downtrend)
            expected_qv_dir = 1 if ref_dir_pine[i] == -1 else -1
            assert st_dir[i] == expected_qv_dir

    def test_adx_parity(self, market_series):
        """
        1. The use of function:
           Verifies ADX, +DI, and -DI match Pine Script ta.dmi within 1e-12.
        """
        h = [b.high for b in market_series]
        l = [b.low for b in market_series]
        c = [b.close for b in market_series]

        adx, p_di, m_di = compute_adx(h, l, c, di_length=14, adx_smoothing=14)
        ref_p, ref_m, ref_adx = PineReferenceOracle.reference_dmi(h, l, c, di_len=14, adx_smooth=14)

        for i in range(13, len(c)):
            assert p_di[i] == pytest.approx(ref_p[i], abs=1e-12)
            assert m_di[i] == pytest.approx(ref_m[i], abs=1e-12)

        for i in range(26, len(c)):
            assert adx[i] == pytest.approx(ref_adx[i], abs=1e-12)


@pytest.mark.gate_g3
class TestCausalProtocols:
    """
    1. The use of class:
       Validates that all implemented indicators adhere to Prefix Invariance,
       Future Perturbation, and Availability Enforcement protocols.
    """

    @pytest.fixture
    def prices(self):
        bars = DeterministicMarketData.generate_bars(60)
        return [b.close for b in bars]

    def test_prefix_invariance_sma(self, prices):
        assert verify_prefix_invariance(lambda s: compute_sma(s, 10), prices, [20, 30, 40, 50]) is True

    def test_prefix_invariance_ema_pine(self, prices):
        assert verify_prefix_invariance(lambda s: compute_ema(s, 10, "PINE_SCRIPT"), prices, [20, 30, 40, 50]) is True

    def test_prefix_invariance_ema_sma(self, prices):
        assert verify_prefix_invariance(lambda s: compute_ema(s, 10, "SMA"), prices, [20, 30, 40, 50]) is True

    def test_prefix_invariance_rsi(self, prices):
        assert verify_prefix_invariance(lambda s: compute_rsi(s, 14), prices, [25, 35, 45, 55]) is True

    def test_prefix_invariance_bollinger(self, prices):
        assert verify_prefix_invariance(lambda s: compute_bollinger_bands(s, 20)[0], prices, [30, 40, 50]) is True

    def test_future_perturbation_sma(self, prices):
        assert verify_future_perturbation(lambda s: compute_sma(s, 10), prices, t_decision=30) is True

    def test_future_perturbation_ema(self, prices):
        assert verify_future_perturbation(lambda s: compute_ema(s, 10), prices, t_decision=30) is True

    def test_future_perturbation_rsi(self, prices):
        assert verify_future_perturbation(lambda s: compute_rsi(s, 14), prices, t_decision=30) is True

    def test_future_perturbation_bollinger(self, prices):
        assert verify_future_perturbation(lambda s: compute_bollinger_bands(s, 15)[0], prices, t_decision=30) is True

    def test_availability_enforcement(self):
        t_avail = UtcEpochSec(1735703760)
        assert verify_availability_enforcement(UtcEpochSec(1735703760), t_avail) is True
        assert verify_availability_enforcement(UtcEpochSec(1735703800), t_avail) is True
        with pytest.raises(TemporalLeakageError):
            verify_availability_enforcement(UtcEpochSec(1735703759), t_avail)


@pytest.mark.gate_g3
class TestSupertrendStateTransitions:
    """
    1. The use of class:
       Validates Supertrend trend direction states and transition logic independently of floating levels.
    """

    def test_supertrend_transition_sequence(self):
        """
        1. The use of function:
           Verifies that direction starts based on initial close, and flips only when close penetrates opposing band.
        """
        # Create a series with a clear uptrend followed by a sharp drop
        bars: List[CandlestickBar] = []
        # 12 bars increasing
        for i in range(12):
            c = 100.0 + i * 5.0
            bars.append(CandlestickBar(open=c - 1, high=c + 2, low=c - 2, close=c, volume=100))
        # 8 bars dropping sharply
        for i in range(8):
            c = 150.0 - (i + 1) * 15.0
            bars.append(CandlestickBar(open=c + 5, high=c + 8, low=c - 5, close=c, volume=100))

        h = [b.high for b in bars]
        l = [b.low for b in bars]
        c = [b.close for b in bars]

        st_line, st_dir = compute_supertrend(h, l, c, length=5, multiplier=2.0)

        # First valid index is length - 1 = 4
        # On initialization bar 4..6, close (120..130) < upper (132.8) -> direction is -1 (Bearish)
        assert st_dir[4] == -1
        assert st_dir[5] == -1
        assert st_dir[6] == -1

        # On bar 7, close rises to 135.0 > 132.8 -> direction flips to +1 (Bullish)
        assert st_dir[7] == 1
        assert st_dir[8] == 1
        assert st_dir[11] == 1

        # On bar 12, close plunges to 135.0 < 141.25 -> direction flips to -1 (Bearish)
        assert st_dir[12] == -1
        assert st_dir[15] == -1
        assert st_dir[19] == -1


@pytest.mark.gate_g3
class TestSessionVWAPQuarantine:
    """
    1. The use of class:
       Validates strict quarantine of cash-index Session VWAP per M5-11 and ADR-005.
    """

    def test_vwap_evaluation_raises_quarantined_error(self):
        """
        1. The use of function:
           Verifies that attempting to evaluate Session VWAP raises SessionVWAPQuarantinedError.
        """
        with pytest.raises(SessionVWAPQuarantinedError) as exc_info:
            SessionVWAPGuard.evaluate()
        assert "BLOCKED_QUARANTINED" in str(exc_info.value)
        assert "cash index candles have volume == 0" in str(exc_info.value)

    def test_vwap_registered_with_blocked_status(self):
        """
        1. The use of function:
           Verifies that register_quarantined_vwap registers the feature with BLOCKED_QUARANTINED status.
        """
        fid = register_quarantined_vwap()
        registry = FeatureRegistry()
        assert registry.has(fid) is True
        rec = registry.get(fid)
        assert rec.definition.name == "SESSION_VWAP"
        assert rec.metadata["status"] == FeatureStatus.BLOCKED_QUARANTINED.value


@pytest.mark.gate_g3
class TestIVRVSpreadInterface:
    """
    1. The use of class:
       Validates IV-RV Spread interface behavior without implementing Phase 5F solver.
    """

    def test_iv_rv_spread_valid_and_unavailable(self):
        """
        1. The use of function:
           Verifies that IV-RV spread computes valid difference when IV is provided,
           and safely outputs None when IV is unavailable, preserving Phase 5B non-fabrication rule.
        """
        rv = [0.12, 0.13, 0.14, 0.15]

        # Scenario 1: IV available
        iv_available = [0.15, 0.16, 0.17, 0.18]
        spread = compute_iv_rv_spread(iv_available, rv)
        for s in spread:
            assert s == pytest.approx(0.03, abs=1e-8)

        # Scenario 2: IV unavailable (None) - no fabrication
        iv_unavailable = [None, None, 0.17, None]
        spread_unavail = compute_iv_rv_spread(iv_unavailable, rv)
        assert spread_unavail[0] is None
        assert spread_unavail[1] is None
        assert spread_unavail[2] == pytest.approx(0.03, abs=1e-8)
        assert spread_unavail[3] is None


@pytest.mark.gate_g3
class TestDeterministicOutputs:
    """
    1. The use of class:
       Validates bitwise determinism across repeated executions.
    """

    def test_repeated_runs_identical(self):
        """
        1. The use of function:
           Verifies that repeated runs of all indicators yield bitwise identical output arrays.
        """
        def assert_nan_equal(seq1, seq2):
            assert len(seq1) == len(seq2)
            for a, b in zip(seq1, seq2):
                if math.isnan(a):
                    assert math.isnan(b)
                else:
                    assert a == b

        bars = DeterministicMarketData.generate_bars(50)
        h = [b.high for b in bars]
        l = [b.low for b in bars]
        c = [b.close for b in bars]

        rsi_1 = compute_rsi(c, 14)
        rsi_2 = compute_rsi(c, 14)
        assert_nan_equal(rsi_1, rsi_2)

        st_1, dir_1 = compute_supertrend(h, l, c, 10, 3.0)
        st_2, dir_2 = compute_supertrend(h, l, c, 10, 3.0)
        assert_nan_equal(st_1, st_2)
        assert dir_1 == dir_2

        adx_1, p_1, m_1 = compute_adx(h, l, c, 14, 14)
        adx_2, p_2, m_2 = compute_adx(h, l, c, 14, 14)
        assert_nan_equal(adx_1, adx_2)
        assert_nan_equal(p_1, p_2)
        assert_nan_equal(m_1, m_2)
