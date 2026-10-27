"""
1. What this file does:
   Implements rolling session high/low tracking and distance-to-high-water-mark features
   with automatic daily reset at session start (09:15 IST) for Indian equity markets.

2. Overall design:
   Processes OHLC candle sequences alongside timestamps, detecting session date transitions.
   Maintains point-in-time running session extreme highs and lows within the current trading
   day, preventing lookahead leakage across calendar day boundaries.

3. Elements in the file:
   - SessionHighWater: NamedTuple holding point-in-time session high/low and distance metrics.
   - compute_session_high_water: Core evaluation function computing rolling session extremes.
   - register_high_water_feature: Registry helper binding the feature to FeatureRegistry.

4. Final output of the file:
   - Causal session high/low feature series for breakout, support/resistance, and mean reversion models.
"""

from typing import List, NamedTuple, Optional, Sequence
from packages.features.schemas import (
    FeatureDefinition,
    FeatureStatus,
    MemoryClass,
    RepaintClass,
    SourceTier,
)
from packages.features.registry import FeatureRegistry
from packages.features.calendar.session import parse_utc_to_ist


class SessionHighWater(NamedTuple):
    """
    1. The use of class:
       Immutable point-in-time record of rolling intraday session extremes.

    2. What the class contains:
       - index: Candle index within the evaluated series.
       - session_date: Date string (YYYY-MM-DD) of the active session.
       - session_high: Maximum high recorded so far in the current session.
       - session_low: Minimum low recorded so far in the current session.
       - dist_to_high: Difference between session_high and current bar close (high - close).
       - dist_to_low: Difference between current bar close and session_low (close - low).
       - is_session_start: True on the first bar of a new trading session.

    3. Technologies used and why:
       NamedTuple for compact, immutable, zero-allocation feature emission.

    4. Key design and overall design of the class:
       Enforces daily boundary resets so yesterday's range does not pollute today's session high/low.
    """
    index: int
    session_date: str
    session_high: float
    session_low: float
    dist_to_high: float
    dist_to_low: float
    is_session_start: bool


def compute_session_high_water(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    timestamps: Sequence[int],
) -> List[SessionHighWater]:
    """
    1. The use of function:
       Computes rolling intraday high and low levels with session-date reset.

    2. How does the specific function work:
       Iterates chronologically through the candle bars:
       1. Converts timestamp to IST date.
       2. If IST date differs from current session date, resets session_high = highs[t]
          and session_low = lows[t], marking is_session_start = True.
       3. Otherwise updates session_high = max(session_high, highs[t])
          and session_low = min(session_low, lows[t]).
       4. Computes dist_to_high = session_high - closes[t] and dist_to_low = closes[t] - session_low.
       5. Appends SessionHighWater record to results.

    3. Concepts used in the function:
       Intraday boundary detection, running extrema, distance metrics.

    4. Places where this function is imported and used:
       Used by trading strategies, breakout detectors, and feature registry runners.

    5. Final output of the function, before and after:
       Before: OHLC sequences and timestamps. After: List of SessionHighWater records.
    """
    n = len(closes)
    if len(highs) != n or len(lows) != n or len(timestamps) != n:
        raise ValueError(
            f"Length mismatch: highs({len(highs)}), lows({len(lows)}), "
            f"closes({n}), timestamps({len(timestamps)})."
        )
    if n == 0:
        return []

    results: List[SessionHighWater] = []
    current_date = None
    curr_high = float("-inf")
    curr_low = float("inf")

    for t in range(n):
        dt_ist = parse_utc_to_ist(timestamps[t])
        bar_date = dt_ist.date()

        if current_date != bar_date:
            # New trading session: reset extremes
            current_date = bar_date
            curr_high = highs[t]
            curr_low = lows[t]
            is_start = True
        else:
            if highs[t] > curr_high:
                curr_high = highs[t]
            if lows[t] < curr_low:
                curr_low = lows[t]
            is_start = False

        c = closes[t]
        dist_h = curr_high - c
        dist_l = c - curr_low

        results.append(
            SessionHighWater(
                index=t,
                session_date=bar_date.isoformat(),
                session_high=curr_high,
                session_low=curr_low,
                dist_to_high=dist_h,
                dist_to_low=dist_l,
                is_session_start=is_start,
            )
        )

    return results


def register_high_water_feature() -> str:
    """
    1. The use of function:
       Registers SESSION_HIGH_WATER feature definition into FeatureRegistry.

    2. How does the specific function work:
       Constructs FeatureDefinition with ZERO_REPAINT class and binds compute_session_high_water.

    3. Concepts used in the function:
       Registry binding, session-reset indicator categorization.

    4. Places where this function is imported and used:
       Called during feature package discovery and registry initialization.

    5. Final output of the function, before and after:
       Before: Unregistered feature. After: Registered feature ID string.
    """
    defn = FeatureDefinition(
        name="SESSION_HIGH_WATER",
        version="v1",
        params={},
        lookback_window=375,
        warm_up_bars=1,
        memory_class=MemoryClass.FINITE,
        source_tier=SourceTier.UNDERLYING_CANDLE,
        repaint_class=RepaintClass.NONE,
        output_schema={
            "session_high": "float64",
            "session_low": "float64",
            "dist_to_high": "float64",
            "dist_to_low": "float64",
            "is_session_start": "bool",
        },
        description="Daily rolling session high/low and distance to peaks with daily 09:15 IST reset.",
    )
    registry = FeatureRegistry()
    return registry.register(
        definition=defn,
        compute_fn=compute_session_high_water,
        metadata={"category": "calendar"},
    )
