"""
1. What this file does:
   Implements the core technical indicator suite, mathematical solvers, Wilder smoothing,
   and Realized Volatility features for QuantView (Milestones M5-03, M5-08, M5-11 / Gate G3).

2. Overall design:
   Provides strictly causal, deterministic implementations of moving averages (SMA, EMA),
   oscillators (Wilder RSI, MACD), volatility measures (ATR, NATR, Bollinger Bands, Realized
   Volatility), directional indicators (Supertrend, ADX with +DI/-DI), and IV-RV spread interface.
   All algorithms enforce strict anti-lookahead invariants, zero-denominator guards,
   and documented initialization/warm-up policies matching TradingView / Pine Script parity.

3. Elements in the file:
   - compute_sma: Rolling Simple Moving Average.
   - compute_ema: Exponential Moving Average supporting Pine Script (bar 0) and SMA-seed modes.
   - compute_wilder_rma: Wilder's Rolling Moving Average (alpha = 1/length).
   - compute_rsi: Wilder's Relative Strength Index with all edge-case boundary guards.
   - compute_macd: Moving Average Convergence Divergence with fast/slow/signal lines and histogram.
   - compute_atr: Average True Range via Wilder RMA over True Range.
   - compute_natr: Normalized ATR (100 * ATR / Close) with non-positive close guards.
   - compute_bollinger_bands: Middle SMA, Upper/Lower bands, Bandwidth, and %B with flat-series guards.
   - compute_supertrend: Supertrend line and directional state machine (+1 Bullish, -1 Bearish).
   - compute_adx: Average Directional Index with +DI and -DI via Wilder DMI algorithm.
   - compute_realized_volatility: Annualized rolling sample standard deviation of log returns.
   - compute_iv_rv_spread: Interface computing ATM IV minus Realized Volatility (fails safe on None).
   - register_all_statistical_features: Helper registering all feature definitions in FeatureRegistry.

4. Final output of the file:
   - Pure, deterministic, point-in-time technical indicator calculation functions and registered features.
"""

import math
from typing import List, Optional, Sequence, Tuple

from packages.features.registry import FeatureRegistry
from packages.features.schemas import (
    FeatureDefinition,
    MemoryClass,
    RepaintClass,
    SourceTier,
)


def compute_sma(source: Sequence[float], length: int) -> List[float]:
    """
    1. The use of function:
       Calculates the Simple Moving Average (SMA) of a numerical series over a rolling window.

    2. How does the specific function work:
       For indices i < length - 1, returns NaN. For i >= length - 1, computes the arithmetic mean
       of the contiguous slice source[i - length + 1 : i + 1].

    3. Concepts used in the function:
       Rolling window arithmetic mean, causal lookback.

    4. Places where this function is imported and used:
       Used directly as an indicator and as an initial seed for RMA and SMA-seeded EMA.

    5. Final output of the function, before and after:
       Before: Raw price series. After: List of rolling SMA values with initial NaNs.
    """
    if length < 1:
        raise ValueError(f"SMA length must be >= 1, got {length}.")
    n = len(source)
    if n == 0:
        return []

    result: List[float] = [float("nan")] * n
    for i in range(length - 1, n):
        result[i] = sum(source[i - length + 1 : i + 1]) / length

    return result


def compute_ema(
    source: Sequence[float],
    length: int,
    seed_policy: str = "PINE_SCRIPT",
) -> List[float]:
    """
    1. The use of function:
       Calculates the Exponential Moving Average (EMA) with configurable seed policies.

    2. How does the specific function work:
       Uses smoothing multiplier alpha = 2.0 / (length + 1.0).
       If seed_policy == "PINE_SCRIPT":
         - Bar 0 seeds immediately with source[0].
         - Bar t >= 1 applies: ema[t] = alpha * source[t] + (1 - alpha) * ema[t-1].
         - Yields bit-for-bit parity with TradingView Pine Script ta.ema from bar 0.
       If seed_policy == "SMA":
         - Bars t < length - 1 are NaN.
         - Bar t = length - 1 seeds with SMA(source[:length]).
         - Bar t >= length applies the exponential recurrence.

    3. Concepts used in the function:
       Exponential smoothing, infinite impulse response filter, Pine Script seed parity.

    4. Places where this function is imported and used:
       Used by trading strategies, MACD line, and indicator benchmarks.

    5. Final output of the function, before and after:
       Before: Price series. After: Causal EMA series.
    """
    if length < 1:
        raise ValueError(f"EMA length must be >= 1, got {length}.")
    n = len(source)
    if n == 0:
        return []

    policy = seed_policy.upper()
    if policy not in ("PINE_SCRIPT", "SMA"):
        raise ValueError(f"Unknown EMA seed_policy '{seed_policy}'. Expected 'PINE_SCRIPT' or 'SMA'.")

    alpha = 2.0 / (length + 1.0)
    result: List[float] = [float("nan")] * n

    if policy == "PINE_SCRIPT":
        # First valid numerical value initializes the recurrence chain
        first_valid_idx: Optional[int] = None
        for i in range(n):
            if not math.isnan(source[i]):
                first_valid_idx = i
                break

        if first_valid_idx is None:
            return result

        result[first_valid_idx] = source[first_valid_idx]
        for t in range(first_valid_idx + 1, n):
            val = source[t]
            if math.isnan(val):
                result[t] = result[t - 1]
            else:
                result[t] = alpha * val + (1.0 - alpha) * result[t - 1]
    else:  # "SMA" seed policy
        if n < length:
            return result
        # Initial seed is the SMA of first length bars
        sma_seed = sum(source[:length]) / length
        result[length - 1] = sma_seed
        for t in range(length, n):
            val = source[t]
            if math.isnan(val):
                result[t] = result[t - 1]
            else:
                result[t] = alpha * val + (1.0 - alpha) * result[t - 1]

    return result


def compute_wilder_rma(source: Sequence[float], length: int) -> List[float]:
    """
    1. The use of function:
       Calculates Wilder's Rolling Moving Average (RMA) used in RSI, ATR, and ADX.

    2. How does the specific function work:
       Uses smoothing factor alpha = 1.0 / length.
       Bars t < length - 1 are NaN.
       Bar t = length - 1 seeds with arithmetic SMA of the first length bars.
       Subsequent bars apply: rma[t] = alpha * source[t] + (1 - alpha) * rma[t-1].
       Matches TradingView Pine Script ta.rma exactly.

    3. Concepts used in the function:
       Wilder's smoothing, modified exponential moving average.

    4. Places where this function is imported and used:
       Used by compute_rsi, compute_atr, and compute_adx.

    5. Final output of the function, before and after:
       Before: Raw series. After: Wilder-smoothed RMA series.
    """
    if length < 1:
        raise ValueError(f"Wilder RMA length must be >= 1, got {length}.")
    n = len(source)
    if n == 0:
        return []

    result: List[float] = [float("nan")] * n
    if n < length:
        return result

    alpha = 1.0 / length
    # Initial SMA seed
    sma_seed = sum(source[:length]) / length
    result[length - 1] = sma_seed

    for t in range(length, n):
        val = source[t]
        if math.isnan(val):
            result[t] = result[t - 1]
        else:
            result[t] = alpha * val + (1.0 - alpha) * result[t - 1]

    return result


def compute_rsi(source: Sequence[float], length: int = 14) -> List[float]:
    """
    1. The use of function:
       Calculates Wilder's Relative Strength Index (RSI) bounded in [0.0, 100.0].

    2. How does the specific function work:
       1. Computes delta = source[t] - source[t-1], gain = max(delta, 0), loss = max(-delta, 0).
       2. Applies compute_wilder_rma over gain and loss.
       3. Handles edge cases:
          - Insufficient history (t < length): returns NaN.
          - Zero average loss with positive gain: returns 100.0.
          - Zero average gain with positive loss: returns 0.0.
          - Zero average gain and zero average loss (flat series): returns 50.0.
          - Otherwise: RS = avg_gain / avg_loss, RSI = 100.0 - (100.0 / (1.0 + RS)).

    3. Concepts used in the function:
       Wilder RMA smoothing, division-by-zero guards, boundary preservation.

    4. Places where this function is imported and used:
       Used by mean-reversion and momentum strategies.

    5. Final output of the function, before and after:
       Before: Price series. After: Bounded [0, 100] RSI series.
    """
    if length < 1:
        raise ValueError(f"RSI length must be >= 1, got {length}.")
    n = len(source)
    if n == 0:
        return []

    result: List[float] = [float("nan")] * n
    if n <= length:
        return result

    gains: List[float] = [0.0] * n
    losses: List[float] = [0.0] * n

    for t in range(1, n):
        diff = source[t] - source[t - 1]
        if diff > 0.0:
            gains[t] = diff
        elif diff < 0.0:
            losses[t] = -diff

    # Wilder smoothing begins on bar index 1..length (length bars total)
    # To match Pine Script ta.rsi, gains[1:length+1] forms the initial SMA window on bar length
    avg_gain = sum(gains[1 : length + 1]) / length
    avg_loss = sum(losses[1 : length + 1]) / length

    # Bar length evaluation
    if avg_loss == 0.0 and avg_gain == 0.0:
        result[length] = 50.0
    elif avg_loss == 0.0:
        result[length] = 100.0
    elif avg_gain == 0.0:
        result[length] = 0.0
    else:
        rs = avg_gain / avg_loss
        result[length] = 100.0 - (100.0 / (1.0 + rs))

    alpha = 1.0 / length
    for t in range(length + 1, n):
        avg_gain = alpha * gains[t] + (1.0 - alpha) * avg_gain
        avg_loss = alpha * losses[t] + (1.0 - alpha) * avg_loss

        if avg_loss == 0.0 and avg_gain == 0.0:
            result[t] = 50.0
        elif avg_loss == 0.0:
            result[t] = 100.0
        elif avg_gain == 0.0:
            result[t] = 0.0
        else:
            rs = avg_gain / avg_loss
            result[t] = 100.0 - (100.0 / (1.0 + rs))

    return result


def compute_macd(
    source: Sequence[float],
    fast_length: int = 12,
    slow_length: int = 26,
    signal_length: int = 9,
    seed_policy: str = "PINE_SCRIPT",
) -> Tuple[List[float], List[float], List[float]]:
    """
    1. The use of function:
       Calculates Moving Average Convergence Divergence (MACD line, signal line, and histogram).

    2. How does the specific function work:
       1. Computes fast_ema and slow_ema via compute_ema.
       2. Computes macd_line = fast_ema - slow_ema.
       3. Computes signal_line = compute_ema(macd_line, signal_length).
       4. Computes histogram = macd_line - signal_line.

    3. Concepts used in the function:
       Dual exponential moving average differential, signal line smoothing.

    4. Places where this function is imported and used:
       Used by trend and momentum strategies.

    5. Final output of the function, before and after:
       Before: Price series. After: (macd_line, signal_line, histogram).
    """
    if fast_length < 1 or slow_length < 1 or signal_length < 1:
        raise ValueError("MACD fast, slow, and signal lengths must be >= 1.")
    if fast_length >= slow_length:
        raise ValueError(f"fast_length ({fast_length}) must be < slow_length ({slow_length}).")

    n = len(source)
    if n == 0:
        return ([], [], [])

    fast_ema = compute_ema(source, fast_length, seed_policy=seed_policy)
    slow_ema = compute_ema(source, slow_length, seed_policy=seed_policy)

    macd_line: List[float] = [float("nan")] * n
    for i in range(n):
        f = fast_ema[i]
        s = slow_ema[i]
        if not (math.isnan(f) or math.isnan(s)):
            macd_line[i] = f - s

    # Calculate signal line over macd_line ignoring leading NaNs
    signal_line: List[float] = [float("nan")] * n
    first_valid = None
    for i in range(n):
        if not math.isnan(macd_line[i]):
            first_valid = i
            break

    if first_valid is not None:
        valid_macd = macd_line[first_valid:]
        valid_signal = compute_ema(valid_macd, signal_length, seed_policy=seed_policy)
        for j, val in enumerate(valid_signal):
            signal_line[first_valid + j] = val

    histogram: List[float] = [float("nan")] * n
    for i in range(n):
        m = macd_line[i]
        s = signal_line[i]
        if not (math.isnan(m) or math.isnan(s)):
            histogram[i] = m - s

    return (macd_line, signal_line, histogram)


def compute_atr(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    length: int = 14,
) -> List[float]:
    """
    1. The use of function:
       Calculates the Average True Range (ATR) using Wilder's RMA over True Range.

    2. How does the specific function work:
       1. Asserts high, low, close have identical lengths.
       2. Computes TR[0] = high[0] - low[0].
       3. For t >= 1: TR[t] = max(high[t] - low[t], |high[t] - close[t-1]|, |low[t] - close[t-1]|).
       4. Applies compute_wilder_rma(TR, length).

    3. Concepts used in the function:
       True Range calculation, Wilder RMA smoothing.

    4. Places where this function is imported and used:
       Used by volatility estimators, Supertrend, ADX, and NATR.

    5. Final output of the function, before and after:
       Before: High, low, close series. After: Bounded ATR volatility series.
    """
    if length < 1:
        raise ValueError(f"ATR length must be >= 1, got {length}.")
    n = len(close)
    if len(high) != n or len(low) != n:
        raise ValueError(f"Lengths of high ({len(high)}), low ({len(low)}), and close ({n}) must match.")
    if n == 0:
        return []

    tr: List[float] = [0.0] * n
    tr[0] = high[0] - low[0]

    for t in range(1, n):
        hl = high[t] - low[t]
        hc = abs(high[t] - close[t - 1])
        lc = abs(low[t] - close[t - 1])
        tr[t] = max(hl, hc, lc)

    return compute_wilder_rma(tr, length)


def compute_natr(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    length: int = 14,
) -> List[float]:
    """
    1. The use of function:
       Calculates Normalized Average True Range (NATR = 100.0 * ATR / Close).

    2. How does the specific function work:
       Computes ATR via compute_atr, divides by close[t] and multiplies by 100.0.
       If close[t] <= 0 or ATR is NaN, safely outputs NaN without ZeroDivisionError.

    3. Concepts used in the function:
       Regime-invariant normalized volatility percentage.

    4. Places where this function is imported and used:
       Used in risk sizing, dynamic trailing stop evaluation, and multi-year volatility comparisons.

    5. Final output of the function, before and after:
       Before: OHLC series. After: Percentage NATR series.
    """
    atr = compute_atr(high, low, close, length)
    n = len(close)
    result: List[float] = [float("nan")] * n

    for t in range(n):
        c = close[t]
        a = atr[t]
        if math.isnan(a) or c <= 0.0:
            result[t] = float("nan")
        else:
            result[t] = 100.0 * (a / c)

    return result


def compute_bollinger_bands(
    close: Sequence[float],
    length: int = 20,
    mult: float = 2.0,
) -> Tuple[List[float], List[float], List[float], List[float], List[float]]:
    """
    1. The use of function:
       Calculates Bollinger Bands (Middle, Upper, Lower, Bandwidth, and %B).

    2. How does the specific function work:
       1. Middle band is the length-period SMA.
       2. Standard deviation uses population formula (sum((x - mean)^2) / length)^0.5.
       3. Upper = Middle + mult * std, Lower = Middle - mult * std.
       4. Guards:
          - Bandwidth: (Upper - Lower) / Middle if Middle > 0 else 0.0.
          - %B: (Close - Lower) / (Upper - Lower) if Upper != Lower else 0.5 (centered).

    3. Concepts used in the function:
       Gaussian envelope, population dispersion, division-by-zero guards.

    4. Places where this function is imported and used:
       Used by volatility compression and mean-reversion strategies.

    5. Final output of the function, before and after:
       Before: Close prices. After: Tuple of (middle, upper, lower, bandwidth, percent_b).
    """
    if length < 1:
        raise ValueError(f"Bollinger Bands length must be >= 1, got {length}.")
    n = len(close)
    if n == 0:
        return ([], [], [], [], [])

    middle: List[float] = [float("nan")] * n
    upper: List[float] = [float("nan")] * n
    lower: List[float] = [float("nan")] * n
    bandwidth: List[float] = [float("nan")] * n
    percent_b: List[float] = [float("nan")] * n

    for i in range(length - 1, n):
        window = close[i - length + 1 : i + 1]
        mean = sum(window) / length
        var = sum((x - mean) ** 2 for x in window) / length
        std = math.sqrt(var)

        up = mean + mult * std
        lo = mean - mult * std
        band_w = up - lo

        middle[i] = mean
        upper[i] = up
        lower[i] = lo

        # Bandwidth division guard
        if mean > 0.0:
            bandwidth[i] = band_w / mean
        else:
            bandwidth[i] = 0.0

        # %B division guard
        if band_w > 0.0:
            percent_b[i] = (close[i] - lo) / band_w
        else:
            percent_b[i] = 0.5  # Flat series convention: mid-band

    return (middle, upper, lower, bandwidth, percent_b)


def compute_supertrend(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    length: int = 10,
    multiplier: float = 3.0,
) -> Tuple[List[float], List[int]]:
    """
    1. The use of function:
       Calculates the Supertrend indicator line and trend direction state machine.

    2. How does the specific function work:
       1. Computes hl2 = (high + low) / 2.0 and ATR(length).
       2. Basic upper = hl2 + multiplier * ATR, basic lower = hl2 - multiplier * ATR.
       3. Updates final bands recursively based on previous close.
       4. Direction is +1 for Bullish (line is below price) and -1 for Bearish (line is above price).
       5. Initial bar t0: Direction = +1 if close > basic_upper else -1.
       6. Transitions: Swaps state when close crosses the active opposing final band.

    3. Concepts used in the function:
       Non-repainting state machine, trailing volatility envelope.

    4. Places where this function is imported and used:
       Used by trend-following strategies for entries, trailing stops, and directional bias.

    5. Final output of the function, before and after:
       Before: High, low, close series. After: Tuple of (supertrend_line, direction).
    """
    if length < 1:
        raise ValueError(f"Supertrend length must be >= 1, got {length}.")
    n = len(close)
    if len(high) != n or len(low) != n:
        raise ValueError("High, low, and close series lengths must match.")
    if n == 0:
        return ([], [])

    atr = compute_atr(high, low, close, length)
    supertrend: List[float] = [float("nan")] * n
    direction: List[int] = [0] * n

    # Find first bar where ATR is valid
    start_idx: Optional[int] = None
    for i in range(n):
        if not math.isnan(atr[i]):
            start_idx = i
            break

    if start_idx is None:
        return (supertrend, direction)

    hl2_start = (high[start_idx] + low[start_idx]) / 2.0
    basic_upper = hl2_start + multiplier * atr[start_idx]
    basic_lower = hl2_start - multiplier * atr[start_idx]

    final_upper = basic_upper
    final_lower = basic_lower

    if close[start_idx] > basic_upper:
        curr_dir = 1
        supertrend[start_idx] = final_lower
    else:
        curr_dir = -1
        supertrend[start_idx] = final_upper
    direction[start_idx] = curr_dir

    for t in range(start_idx + 1, n):
        hl2 = (high[t] + low[t]) / 2.0
        cur_basic_up = hl2 + multiplier * atr[t]
        cur_basic_lo = hl2 - multiplier * atr[t]

        # Final upper band logic
        if cur_basic_up < final_upper or close[t - 1] > final_upper:
            final_upper = cur_basic_up

        # Final lower band logic
        if cur_basic_lo > final_lower or close[t - 1] < final_lower:
            final_lower = cur_basic_lo

        # Direction state transition
        prev_st = supertrend[t - 1]
        if prev_st == final_upper or curr_dir == -1:
            if close[t] > final_upper:
                curr_dir = 1
            else:
                curr_dir = -1
        else:  # prev_st == final_lower or curr_dir == 1
            if close[t] < final_lower:
                curr_dir = -1
            else:
                curr_dir = 1

        supertrend[t] = final_lower if curr_dir == 1 else final_upper
        direction[t] = curr_dir

    return (supertrend, direction)


def compute_adx(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    di_length: int = 14,
    adx_smoothing: int = 14,
) -> Tuple[List[float], List[float], List[float]]:
    """
    1. The use of function:
       Calculates the Average Directional Index (ADX) along with +DI and -DI.

    2. How does the specific function work:
       1. Computes directional movements:
          up = high[t] - high[t-1], down = low[t-1] - low[t].
          +DM = up if (up > down and up > 0) else 0.
          -DM = down if (down > up and down > 0) else 0.
       2. Smoothes TR, +DM, -DM with Wilder RMA(di_length).
       3. +DI = 100 * (+DM_rma / TR_rma), -DI = 100 * (-DM_rma / TR_rma).
       4. DX = 100 * |+DI - -DI| / (+DI + -DI).
       5. ADX = Wilder RMA(DX, adx_smoothing).
       6. Applies zero-denominator guards at each step.

    3. Concepts used in the function:
       Wilder DMI algorithm, directional movement smoothing.

    4. Places where this function is imported and used:
       Used by trend strength filters and regime detection.

    5. Final output of the function, before and after:
       Before: High, low, close series. After: (adx, plus_di, minus_di).
    """
    if di_length < 1 or adx_smoothing < 1:
        raise ValueError("ADX di_length and adx_smoothing must be >= 1.")
    n = len(close)
    if len(high) != n or len(low) != n:
        raise ValueError("High, low, and close series lengths must match.")
    if n == 0:
        return ([], [], [])

    plus_dm: List[float] = [0.0] * n
    minus_dm: List[float] = [0.0] * n
    tr: List[float] = [0.0] * n

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

    tr_rma = compute_wilder_rma(tr, di_length)
    plus_rma = compute_wilder_rma(plus_dm, di_length)
    minus_rma = compute_wilder_rma(minus_dm, di_length)

    plus_di: List[float] = [float("nan")] * n
    minus_di: List[float] = [float("nan")] * n
    dx: List[float] = [float("nan")] * n

    for t in range(n):
        t_tr = tr_rma[t]
        p_dm = plus_rma[t]
        m_dm = minus_rma[t]

        if not (math.isnan(t_tr) or math.isnan(p_dm) or math.isnan(m_dm)):
            p_val = 100.0 * (p_dm / t_tr) if t_tr > 0.0 else 0.0
            m_val = 100.0 * (m_dm / t_tr) if t_tr > 0.0 else 0.0
            plus_di[t] = p_val
            minus_di[t] = m_val

            di_sum = p_val + m_val
            if di_sum > 0.0:
                dx[t] = 100.0 * (abs(p_val - m_val) / di_sum)
            else:
                dx[t] = 0.0

    adx: List[float] = [float("nan")] * n
    # Find first valid DX index
    first_dx = None
    for i in range(n):
        if not math.isnan(dx[i]):
            first_dx = i
            break

    if first_dx is not None:
        valid_dx = dx[first_dx:]
        valid_adx = compute_wilder_rma(valid_dx, adx_smoothing)
        for j, val in enumerate(valid_adx):
            adx[first_dx + j] = val

    return (adx, plus_di, minus_di)


def compute_realized_volatility(
    close: Sequence[float],
    length: int = 30,
    periods_per_year: float = 94500.0,
) -> List[float]:
    """
    1. The use of function:
       Calculates annualized Realized Volatility (RV) from close-to-close log returns.

    2. How does the specific function work:
       1. Computes r[t] = ln(close[t] / close[t-1]).
       2. Over sliding window of length returns (length + 1 prices):
          Computes sample variance s^2 = sum((r - mean)^2) / (length - 1).
       3. Annualizes: RV[t] = sqrt(s^2 * periods_per_year).
       4. On flat price series (variance = 0), returns 0.0.

    3. Concepts used in the function:
       Logarithmic returns, unbiased sample variance, volatility annualization.

    4. Places where this function is imported and used:
       Used by volatility research strategies and the IV-RV spread feature.

    5. Final output of the function, before and after:
       Before: Close prices. After: Annualized RV series (e.g. 0.15 = 15%).
    """
    if length < 2:
        raise ValueError(f"Realized Volatility length must be >= 2 for sample variance, got {length}.")
    n = len(close)
    if n == 0:
        return []

    result: List[float] = [float("nan")] * n
    if n <= length:
        return result

    # Log returns
    log_returns: List[float] = [0.0] * n
    for t in range(1, n):
        c_prev = close[t - 1]
        c_curr = close[t]
        if c_prev > 0.0 and c_curr > 0.0:
            log_returns[t] = math.log(c_curr / c_prev)
        else:
            log_returns[t] = float("nan")

    ann_factor = math.sqrt(periods_per_year)
    for t in range(length, n):
        window = log_returns[t - length + 1 : t + 1]
        if any(math.isnan(x) for x in window):
            result[t] = float("nan")
            continue

        mean = sum(window) / length
        sample_var = sum((x - mean) ** 2 for x in window) / (length - 1)
        if sample_var >= 0.0:
            result[t] = math.sqrt(sample_var) * ann_factor
        else:
            result[t] = 0.0

    return result


def compute_iv_rv_spread(
    atm_iv: Sequence[Optional[float]],
    rv: Sequence[float],
) -> List[Optional[float]]:
    """
    1. The use of function:
       Computes the Implied Volatility minus Realized Volatility spread (IV - RV).

    2. How does the specific function work:
       For each index t:
         If atm_iv[t] is None or math.isnan(atm_iv[t]) or math.isnan(rv[t]):
           Emits None.
         Else:
           Emits atm_iv[t] - rv[t].
       Strictly honors Phase 5B non-fabrication constraint: does NOT fabricate IV inputs.

    3. Concepts used in the function:
       Volatility risk premium spread, fail-safe unavailable input propagation.

    4. Places where this function is imported and used:
       Used in options premium selling strategies and volatility regime tracking.

    5. Final output of the function, before and after:
       Before: atm_iv and rv series. After: List of spread floats or None.
    """
    n = len(rv)
    if len(atm_iv) != n:
        raise ValueError("Lengths of atm_iv and rv must match.")

    result: List[Optional[float]] = [None] * n
    for t in range(n):
        iv = atm_iv[t]
        r = rv[t]
        if iv is None or math.isnan(iv) or math.isnan(r):
            result[t] = None
        else:
            result[t] = iv - r

    return result


def register_all_statistical_features() -> None:
    """
    1. The use of function:
       Registers all core statistical indicators into the central FeatureRegistry.

    2. How does the specific function work:
       Instantiates FeatureDefinition records for SMA, EMA, RSI, MACD, ATR, NATR,
       Bollinger Bands, Supertrend, ADX, RV, and IV-RV Spread, binding them to their solvers.

    3. Concepts used in the function:
       Centralized declarative feature catalog registration.

    4. Places where this function is imported and used:
       Called during package initialization and feature discovery.

    5. Final output of the function, before and after:
       Before: Unregistered indicators. After: All core indicators registered in FeatureRegistry.
    """
    registry = FeatureRegistry()

    # SMA
    registry.register(
        FeatureDefinition(
            name="SMA",
            version="v1",
            params={"length": 20},
            lookback_window=20,
            warm_up_bars=20,
            memory_class=MemoryClass.FINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            repaint_class=RepaintClass.NONE,
            output_schema={"sma": "float64"},
            description="Simple Moving Average over rolling window.",
        ),
        compute_fn=compute_sma,
    )

    # EMA
    registry.register(
        FeatureDefinition(
            name="EMA",
            version="v1",
            params={"length": 20, "seed_policy": "PINE_SCRIPT"},
            lookback_window=20,
            warm_up_bars=60,
            memory_class=MemoryClass.INFINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            repaint_class=RepaintClass.NONE,
            output_schema={"ema": "float64"},
            description="Exponential Moving Average with Pine Script parity.",
        ),
        compute_fn=compute_ema,
    )

    # RSI
    registry.register(
        FeatureDefinition(
            name="RSI",
            version="v1",
            params={"length": 14},
            lookback_window=14,
            warm_up_bars=70,
            memory_class=MemoryClass.INFINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            repaint_class=RepaintClass.NONE,
            output_schema={"rsi": "float64"},
            description="Wilder's Relative Strength Index bounded in [0, 100].",
        ),
        compute_fn=compute_rsi,
    )

    # MACD
    registry.register(
        FeatureDefinition(
            name="MACD",
            version="v1",
            params={"fast_length": 12, "slow_length": 26, "signal_length": 9, "seed_policy": "PINE_SCRIPT"},
            lookback_window=35,
            warm_up_bars=100,
            memory_class=MemoryClass.INFINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            repaint_class=RepaintClass.NONE,
            output_schema={"macd": "float64", "signal": "float64", "histogram": "float64"},
            description="Moving Average Convergence Divergence with fast/slow/signal.",
        ),
        compute_fn=compute_macd,
    )

    # ATR
    registry.register(
        FeatureDefinition(
            name="ATR",
            version="v1",
            params={"length": 14},
            lookback_window=14,
            warm_up_bars=70,
            memory_class=MemoryClass.INFINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            repaint_class=RepaintClass.NONE,
            output_schema={"atr": "float64"},
            description="Average True Range via Wilder RMA smoothing.",
        ),
        compute_fn=compute_atr,
    )

    # NATR
    registry.register(
        FeatureDefinition(
            name="NATR",
            version="v1",
            params={"length": 14},
            lookback_window=14,
            warm_up_bars=70,
            memory_class=MemoryClass.INFINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            repaint_class=RepaintClass.NONE,
            output_schema={"natr": "float64"},
            description="Normalized ATR as a percentage of close price (100 * ATR / Close).",
        ),
        compute_fn=compute_natr,
    )

    # Bollinger Bands
    registry.register(
        FeatureDefinition(
            name="BB",
            version="v1",
            params={"length": 20, "mult": 2.0},
            lookback_window=20,
            warm_up_bars=20,
            memory_class=MemoryClass.FINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            repaint_class=RepaintClass.NONE,
            output_schema={"middle": "float64", "upper": "float64", "lower": "float64", "bandwidth": "float64", "percent_b": "float64"},
            description="Bollinger Bands with population std and flat-series guards.",
        ),
        compute_fn=compute_bollinger_bands,
    )

    # Supertrend
    registry.register(
        FeatureDefinition(
            name="Supertrend",
            version="v1",
            params={"length": 10, "multiplier": 3.0},
            lookback_window=10,
            warm_up_bars=40,
            memory_class=MemoryClass.INFINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            repaint_class=RepaintClass.NONE,
            output_schema={"supertrend": "float64", "direction": "int8"},
            description="Supertrend volatility envelope and trend direction state machine.",
        ),
        compute_fn=compute_supertrend,
    )

    # ADX
    registry.register(
        FeatureDefinition(
            name="ADX",
            version="v1",
            params={"di_length": 14, "adx_smoothing": 14},
            lookback_window=28,
            warm_up_bars=70,
            memory_class=MemoryClass.INFINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            repaint_class=RepaintClass.NONE,
            output_schema={"adx": "float64", "plus_di": "float64", "minus_di": "float64"},
            description="Average Directional Index with +DI and -DI via Wilder DMI.",
        ),
        compute_fn=compute_adx,
    )

    # Realized Volatility
    registry.register(
        FeatureDefinition(
            name="RV",
            version="v1",
            params={"length": 30, "periods_per_year": 94500.0},
            lookback_window=31,
            warm_up_bars=31,
            memory_class=MemoryClass.FINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            repaint_class=RepaintClass.NONE,
            output_schema={"rv": "float64"},
            description="Annualized sample standard deviation of rolling log returns.",
        ),
        compute_fn=compute_realized_volatility,
    )

    # IV-RV Spread
    registry.register(
        FeatureDefinition(
            name="IV_RV_SPREAD",
            version="v1",
            params={},
            lookback_window=31,
            warm_up_bars=31,
            memory_class=MemoryClass.FINITE,
            source_tier=SourceTier.MODEL_DERIVED,
            repaint_class=RepaintClass.NONE,
            output_schema={"iv_rv_spread": "float64"},
            description="Spread between ATM Implied Volatility and Realized Volatility.",
        ),
        compute_fn=compute_iv_rv_spread,
    )
