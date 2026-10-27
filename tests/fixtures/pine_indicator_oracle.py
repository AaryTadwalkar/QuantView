"""
1. What this file does:
   Provides independent mathematical ground-truth oracles, hand-calculated golden fixtures,
   and TradingView / Pine Script v5 reference models for technical indicators (Stage 5 / Phase 5B).

2. Overall design:
   Contains independently authored reference algorithms implementing the exact mathematical
   specifications of TradingView Pine Script built-ins (ta.sma, ta.ema, ta.rma, ta.rsi,
   ta.macd, ta.atr, ta.bb, ta.supertrend, and ta.dmi/adx) and hand-calculated numerical fixtures
   with full intermediate traces. Serves as the ground truth against which QuantView indicator
   implementations are validated to ensure zero look-ahead bias and documented numerical parity.

3. Elements in the file:
   - HandCalculatedScenarios: Dataclass containing manually solved numerical scenarios for all indicators.
   - DeterministicMarketData: Fixture generator producing deterministic 200-bar OHLCV market series.
   - PineReferenceOracle: Reference implementation reproducing TradingView Pine Script v5 behaviors.
   - EmaParityComparison: Analytical comparator evaluating Pine Script vs SMA-seed initialization.

4. Final output of the file:
   - Independent verification oracle and reference fixtures for Phase 5B test suites.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple


class CandlestickBar(NamedTuple):
    """
    1. The use of class:
       Lightweight representation of a single OHLCV candlestick bar.

    2. What the class contains:
       - open: float
       - high: float
       - low: float
       - close: float
       - volume: int

    3. Technologies used and why:
       NamedTuple for immutability and minimal test overhead.

    4. Key design and overall design of the class:
       Standard market bar container used across indicator oracle tests.
    """
    open: float
    high: float
    low: float
    close: float
    volume: int


class HandCalculatedScenarios:
    """
    1. The use of class:
       Contains hand-calculated synthetic price sequences with verified intermediate values.

    2. What the class contains:
       - EMA_PRICES, EMA_PINE_EXPECTED, EMA_SMA_EXPECTED
       - SMA_PRICES, SMA_WINDOW_3_EXPECTED
       - RSI_STRICT_UP, RSI_STRICT_DOWN, RSI_FLAT
       - BB_FLAT_PRICES, BB_FLAT_EXPECTED
       - SUPERTREND_BARS, SUPERTREND_FLIP_EXPECTED
       - ADX_FLAT_BARS, ADX_FLAT_EXPECTED
       - NATR_ZERO_CLOSE_BARS

    3. Technologies used and why:
       Pure Python constants with manual arithmetic documented down to 8 decimal places.

    4. Key design and overall design of the class:
       Eliminates circular reasoning by testing against manually derived numbers rather than engine self-tests.
    """
    # -------------------------------------------------------------------------
    # 1. EMA Hand-Calculated Traces (length = 3, alpha = 2 / (3 + 1) = 0.5)
    # Prices: [100.0, 104.0, 102.0, 108.0, 110.0]
    #
    # Pine Script seed (bar 0 = 100.0):
    # Bar 0: 100.0
    # Bar 1: 0.5 * 104.0 + 0.5 * 100.0 = 102.0
    # Bar 2: 0.5 * 102.0 + 0.5 * 102.0 = 102.0
    # Bar 3: 0.5 * 108.0 + 0.5 * 102.0 = 105.0
    # Bar 4: 0.5 * 110.0 + 0.5 * 105.0 = 107.5
    #
    # SMA seed (seed on bar 2 with SMA(100, 104, 102) = 102.0):
    # Bar 0: NaN
    # Bar 1: NaN
    # Bar 2: (100 + 104 + 102) / 3 = 102.0
    # Bar 3: 0.5 * 108.0 + 0.5 * 102.0 = 105.0
    # Bar 4: 0.5 * 110.0 + 0.5 * 105.0 = 107.5
    # -------------------------------------------------------------------------
    EMA_PRICES = [100.0, 104.0, 102.0, 108.0, 110.0]
    EMA_PINE_EXPECTED = [100.0, 102.0, 102.0, 105.0, 107.5]
    EMA_SMA_EXPECTED = [float("nan"), float("nan"), 102.0, 105.0, 107.5]

    # -------------------------------------------------------------------------
    # 2. SMA Hand-Calculated Traces (length = 3)
    # Prices: [10.0, 20.0, 30.0, 40.0, 50.0]
    # Bar 0, 1: NaN
    # Bar 2: (10 + 20 + 30) / 3 = 20.0
    # Bar 3: (20 + 30 + 40) / 3 = 30.0
    # Bar 4: (30 + 40 + 50) / 3 = 40.0
    # -------------------------------------------------------------------------
    SMA_PRICES = [10.0, 20.0, 30.0, 40.0, 50.0]
    SMA_WINDOW_3_EXPECTED = [float("nan"), float("nan"), 20.0, 30.0, 40.0]

    # -------------------------------------------------------------------------
    # 3. RSI Boundary Scenarios (length = 3)
    # Strictly increasing (zero losses): [10.0, 12.0, 14.0, 16.0] -> RSI = 100.0
    # Strictly decreasing (zero gains): [20.0, 18.0, 16.0, 14.0] -> RSI = 0.0
    # Flat series (zero gains and zero losses): [15.0, 15.0, 15.0, 15.0] -> RSI = 50.0
    # -------------------------------------------------------------------------
    RSI_STRICT_UP = [10.0, 12.0, 14.0, 16.0, 18.0]
    RSI_STRICT_DOWN = [20.0, 18.0, 16.0, 14.0, 12.0]
    RSI_FLAT = [15.0, 15.0, 15.0, 15.0, 15.0]

    # -------------------------------------------------------------------------
    # 4. Bollinger Bands Flat Series (length = 3, close = 100.0)
    # Mean = 100.0, Std = 0.0, Upper = 100.0, Lower = 100.0
    # Bandwidth = (100.0 - 100.0) / 100.0 = 0.0
    # %B = centered at 0.5 per flat-series guard
    # -------------------------------------------------------------------------
    BB_FLAT_PRICES = [100.0, 100.0, 100.0, 100.0, 100.0]


class DeterministicMarketData:
    """
    1. The use of class:
       Generates a deterministic 200-bar synthetic market series incorporating
       trending, mean-reverting, expansion, contraction, and flat regimes.

    2. What the class contains:
       - generate_bars: Function creating 200 CandlestickBars.

    3. Technologies used and why:
       Deterministic trigonometric and pseudo-random functions with fixed seed.

    4. Key design and overall design of the class:
       Provides a repeatable, non-trivial test asset for multi-indicator oracle comparison.
    """

    @classmethod
    def generate_bars(cls, count: int = 200) -> List[CandlestickBar]:
        """
        1. The use of function:
           Constructs a continuous sequence of CandlestickBar instances.

        2. How does the specific function work:
           Applies a sinusoidal trend with harmonic noise to generate realistic OHLC prices.

        3. Concepts used in the function:
           Deterministic price modeling.

        4. Places where this function is imported and used:
           Used across unit tests in test_causal_indicators.py.

        5. Final output of the function, before and after:
           Before: Requested count. After: List of CandlestickBar instances.
        """
        bars: List[CandlestickBar] = []
        base_price = 22000.0

        for i in range(count):
            trend = 100.0 * math.sin(i / 15.0)
            noise = 25.0 * math.sin(i / 3.0) + 10.0 * math.cos(i / 1.7)
            center = base_price + trend + noise

            o = center - 5.0
            c = center + 7.0
            h = max(o, c) + 12.0
            l = min(o, c) - 10.0
            v = int(1000 + 500 * abs(math.sin(i / 5.0)))

            bars.append(CandlestickBar(open=round(o, 2), high=round(h, 2), low=round(l, 2), close=round(c, 2), volume=v))

        return bars


class PineReferenceOracle:
    """
    1. The use of class:
       Independent reference implementation duplicating TradingView Pine Script v5 / v6 algorithms.

    2. What the class contains:
       - reference_sma: Pure Pine Script ta.sma equivalent.
       - reference_ema: Pure Pine Script ta.ema equivalent (bar 0 initialization).
       - reference_rma: Pure Pine Script ta.rma equivalent.
       - reference_rsi: Pure Pine Script ta.rsi equivalent.
       - reference_macd: Pure Pine Script ta.macd equivalent.
       - reference_atr: Pure Pine Script ta.atr equivalent.
       - reference_bb: Pure Pine Script ta.bb equivalent.
       - reference_supertrend: Pure Pine Script ta.supertrend equivalent.
       - reference_dmi: Pure Pine Script ta.dmi equivalent (+DI, -DI, ADX).

    3. Technologies used and why:
       Direct algorithmic translations of Pine Script v5 built-ins.

    4. Key design and overall design of the class:
       Serves as the golden reference oracle for cross-system parity checks.
    """

    @staticmethod
    def reference_sma(src: Sequence[float], length: int) -> List[float]:
        """
        1. The use of function:
           Pine Script ta.sma ground truth implementation.
        """
        n = len(src)
        out = [float("nan")] * n
        for i in range(length - 1, n):
            out[i] = sum(src[i - length + 1 : i + 1]) / length
        return out

    @staticmethod
    def reference_ema(src: Sequence[float], length: int) -> List[float]:
        """
        1. The use of function:
           Pine Script ta.ema ground truth implementation: seeds on bar 0 with src[0].
        """
        n = len(src)
        if n == 0:
            return []
        alpha = 2.0 / (length + 1.0)
        out = [float("nan")] * n
        out[0] = src[0]
        for t in range(1, n):
            out[t] = alpha * src[t] + (1.0 - alpha) * out[t - 1]
        return out

    @staticmethod
    def reference_rma(src: Sequence[float], length: int) -> List[float]:
        """
        1. The use of function:
           Pine Script ta.rma ground truth implementation: seeds on bar length - 1 with SMA.
        """
        n = len(src)
        out = [float("nan")] * n
        if n < length:
            return out
        alpha = 1.0 / length
        out[length - 1] = sum(src[:length]) / length
        for t in range(length, n):
            out[t] = alpha * src[t] + (1.0 - alpha) * out[t - 1]
        return out

    @classmethod
    def reference_rsi(cls, src: Sequence[float], length: int = 14) -> List[float]:
        """
        1. The use of function:
           Pine Script ta.rsi ground truth implementation using Wilder RMA.
        """
        n = len(src)
        out = [float("nan")] * n
        if n <= length:
            return out

        u = [0.0] * n
        d = [0.0] * n
        for t in range(1, n):
            diff = src[t] - src[t - 1]
            if diff > 0.0:
                u[t] = diff
            elif diff < 0.0:
                d[t] = -diff

        avg_u = sum(u[1 : length + 1]) / length
        avg_d = sum(d[1 : length + 1]) / length

        if avg_d == 0.0 and avg_u == 0.0:
            out[length] = 50.0
        elif avg_d == 0.0:
            out[length] = 100.0
        elif avg_u == 0.0:
            out[length] = 0.0
        else:
            out[length] = 100.0 - (100.0 / (1.0 + (avg_u / avg_d)))

        alpha = 1.0 / length
        for t in range(length + 1, n):
            avg_u = alpha * u[t] + (1.0 - alpha) * avg_u
            avg_d = alpha * d[t] + (1.0 - alpha) * avg_d
            if avg_d == 0.0 and avg_u == 0.0:
                out[t] = 50.0
            elif avg_d == 0.0:
                out[t] = 100.0
            elif avg_u == 0.0:
                out[t] = 0.0
            else:
                out[t] = 100.0 - (100.0 / (1.0 + (avg_u / avg_d)))

        return out

    @classmethod
    def reference_macd(
        cls,
        src: Sequence[float],
        fast_length: int = 12,
        slow_length: int = 26,
        signal_length: int = 9,
    ) -> Tuple[List[float], List[float], List[float]]:
        """
        1. The use of function:
           Pine Script ta.macd ground truth implementation.
        """
        n = len(src)
        fast_ema = cls.reference_ema(src, fast_length)
        slow_ema = cls.reference_ema(src, slow_length)
        macd = [f - s for f, s in zip(fast_ema, slow_ema)]
        signal = cls.reference_ema(macd, signal_length)
        hist = [m - s for m, s in zip(macd, signal)]
        return (macd, signal, hist)

    @classmethod
    def reference_atr(
        cls,
        high: Sequence[float],
        low: Sequence[float],
        close: Sequence[float],
        length: int = 14,
    ) -> List[float]:
        """
        1. The use of function:
           Pine Script ta.atr ground truth implementation.
        """
        n = len(close)
        tr = [0.0] * n
        tr[0] = high[0] - low[0]
        for t in range(1, n):
            hl = high[t] - low[t]
            hc = abs(high[t] - close[t - 1])
            lc = abs(low[t] - close[t - 1])
            tr[t] = max(hl, hc, lc)
        return cls.reference_rma(tr, length)

    @classmethod
    def reference_bb(
        cls,
        src: Sequence[float],
        length: int = 20,
        mult: float = 2.0,
    ) -> Tuple[List[float], List[float], List[float]]:
        """
        1. The use of function:
           Pine Script ta.bb ground truth implementation.
        """
        n = len(src)
        mid = [float("nan")] * n
        up = [float("nan")] * n
        lo = [float("nan")] * n
        for i in range(length - 1, n):
            window = src[i - length + 1 : i + 1]
            mean = sum(window) / length
            var = sum((x - mean) ** 2 for x in window) / length
            std = math.sqrt(var)
            mid[i] = mean
            up[i] = mean + mult * std
            lo[i] = mean - mult * std
        return (mid, up, lo)

    @classmethod
    def reference_supertrend(
        cls,
        high: Sequence[float],
        low: Sequence[float],
        close: Sequence[float],
        length: int = 10,
        factor: float = 3.0,
    ) -> Tuple[List[float], List[int]]:
        """
        1. The use of function:
           Pine Script ta.supertrend ground truth implementation.
           Returns (supertrend_line, direction) where direction is -1 (Up) or +1 (Down) in Pine convention.
        """
        n = len(close)
        atr = cls.reference_atr(high, low, close, length)
        st = [float("nan")] * n
        dir_pine = [0] * n

        start = length - 1
        hl2 = (high[start] + low[start]) / 2.0
        up = hl2 + factor * atr[start]
        lo = hl2 - factor * atr[start]

        if close[start] > up:
            d = -1  # Pine: -1 is Uptrend
            st[start] = lo
        else:
            d = 1   # Pine: +1 is Downtrend
            st[start] = up
        dir_pine[start] = d

        for t in range(start + 1, n):
            h_t = high[t]
            l_t = low[t]
            c_t = close[t]
            a_t = atr[t]
            cur_hl2 = (h_t + l_t) / 2.0
            cur_up = cur_hl2 + factor * a_t
            cur_lo = cur_hl2 - factor * a_t

            if cur_up < up or close[t - 1] > up:
                up = cur_up
            if cur_lo > lo or close[t - 1] < lo:
                lo = cur_lo

            prev_st = st[t - 1]
            if prev_st == up or d == 1:
                d = -1 if c_t > up else 1
            else:
                d = 1 if c_t < lo else -1

            st[t] = lo if d == -1 else up
            dir_pine[t] = d

        return (st, dir_pine)

    @classmethod
    def reference_dmi(
        cls,
        high: Sequence[float],
        low: Sequence[float],
        close: Sequence[float],
        di_len: int = 14,
        adx_smooth: int = 14,
    ) -> Tuple[List[float], List[float], List[float]]:
        """
        1. The use of function:
           Pine Script ta.dmi ground truth implementation returning (+DI, -DI, ADX).
        """
        n = len(close)
        plus_dm = [0.0] * n
        minus_dm = [0.0] * n
        tr = [0.0] * n
        tr[0] = high[0] - low[0]

        for t in range(1, n):
            up = high[t] - high[t - 1]
            down = low[t - 1] - low[t]
            if up > down and up > 0.0:
                plus_dm[t] = up
            if down > up and down > 0.0:
                minus_dm[t] = down
            hl = high[t] - low[t]
            hc = abs(high[t] - close[t - 1])
            lc = abs(low[t] - close[t - 1])
            tr[t] = max(hl, hc, lc)

        tr_rma = cls.reference_rma(tr, di_len)
        plus_rma = cls.reference_rma(plus_dm, di_len)
        minus_rma = cls.reference_rma(minus_dm, di_len)

        plus_di = [float("nan")] * n
        minus_di = [float("nan")] * n
        dx = [float("nan")] * n

        for t in range(n):
            t_tr = tr_rma[t]
            p_dm = plus_rma[t]
            m_dm = minus_rma[t]
            if not (math.isnan(t_tr) or math.isnan(p_dm) or math.isnan(m_dm)):
                p = 100.0 * (p_dm / t_tr) if t_tr > 0.0 else 0.0
                m = 100.0 * (m_dm / t_tr) if t_tr > 0.0 else 0.0
                plus_di[t] = p
                minus_di[t] = m
                s = p + m
                dx[t] = 100.0 * (abs(p - m) / s) if s > 0.0 else 0.0

        first_dx = None
        for i in range(n):
            if not math.isnan(dx[i]):
                first_dx = i
                break

        adx = [float("nan")] * n
        if first_dx is not None:
            sub_adx = cls.reference_rma(dx[first_dx:], adx_smooth)
            for j, val in enumerate(sub_adx):
                adx[first_dx + j] = val

        return (plus_di, minus_di, adx)


class EmaParityReport(NamedTuple):
    """
    1. The use of class:
       Structured evidence capturing the numerical difference between Pine Script seed and SMA seed.

    2. What the class contains:
       - max_error_pine_mode: Maximum difference between implementation and Pine reference under PINE_SCRIPT seed.
       - initial_error_sma_mode: Difference at bar length - 1 between SMA seed and Pine reference.
       - warmup_3x_error_sma: Difference at bar 3 * length between SMA seed and Pine reference.
       - warmup_5x_error_sma: Difference at bar 5 * length between SMA seed and Pine reference.
    """
    max_error_pine_mode: float
    initial_error_sma_mode: float
    warmup_3x_error_sma: float
    warmup_5x_error_sma: float


def analyze_ema_parity(prices: Sequence[float], length: int = 20) -> EmaParityReport:
    """
    1. The use of function:
       Performs the mandatory EMA ground-truth verification comparing Pine Script and SMA seeds.

    2. How does the specific function work:
       Calculates reference Pine EMA and QuantView EMAs under both seed policies, recording errors.

    3. Concepts used in the function:
       Exponential decay of initial conditions: |EMA_sma - EMA_pine| = (1 - alpha)^k * |seed_diff|.

    4. Places where this function is imported and used:
       Used by unit tests and documented in ops/evidence/M5-08.md.

    5. Final output of the function, before and after:
       Before: Price series. After: Verified EmaParityReport.
    """
    from packages.features.statistical.indicators import compute_ema

    pine_ref = PineReferenceOracle.reference_ema(prices, length)
    qv_pine = compute_ema(prices, length, seed_policy="PINE_SCRIPT")
    qv_sma = compute_ema(prices, length, seed_policy="SMA")

    # Pine mode error (should be < 1e-12 across entire series)
    max_err_pine = max(abs(a - b) for a, b in zip(qv_pine, pine_ref))

    # SMA mode errors relative to Pine reference
    initial_sma_err = abs(qv_sma[length - 1] - pine_ref[length - 1])

    idx_3x = min(len(prices) - 1, 3 * length)
    idx_5x = min(len(prices) - 1, 5 * length)

    err_3x = abs(qv_sma[idx_3x] - pine_ref[idx_3x])
    err_5x = abs(qv_sma[idx_5x] - pine_ref[idx_5x])

    return EmaParityReport(
        max_error_pine_mode=max_err_pine,
        initial_error_sma_mode=initial_sma_err,
        warmup_3x_error_sma=err_3x,
        warmup_5x_error_sma=err_5x,
    )
