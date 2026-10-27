"""
1. What this file does:
   Implements the Heikin Ashi derived chart display transform for QuantView (ENGINE §22, Task M5-09 / Gate G3).

2. Overall design:
   Evaluates versioned Heikin Ashi candles from underlying OHLC series:
     HA_Close = (Open + High + Low + Close) / 4
     HA_Open_0 = (Open_0 + Close_0) / 2
     HA_Open_t = (HA_Open_{t-1} + HA_Close_{t-1}) / 2
     HA_High = max(High, HA_Open, HA_Close)
     HA_Low  = min(Low, HA_Open, HA_Close)
   Enforces strict non-negotiable invariant per ENGINE §22: Heikin Ashi values are
   visual display transforms ONLY. They must NEVER become tradable OHLC and must NEVER
   be used for simulated order fills, slippage calculations, or ledger P&L evaluation.

3. Elements in the file:
   - NonTradableTransformError: Exception raised if transform prices are passed to fill engine.
   - HeikinAshiBar: NamedTuple holding transformed visual candle values.
   - compute_heikin_ashi: Pure calculation function transforming OHLC arrays.
   - register_heikin_ashi_feature: Registry helper binding transform to FeatureRegistry.

4. Final output of the file:
   - Smoothed Heikin Ashi candle series strictly flagged as is_display_transform_only=True.
"""

from typing import List, NamedTuple, Sequence

from packages.features.registry import FeatureRegistry
from packages.features.schemas import (
    FeatureDefinition,
    MemoryClass,
    RepaintClass,
    SourceTier,
)


class NonTradableTransformError(RuntimeError):
    """Raised if an engine component attempts to execute orders or compute P&L using transform values."""
    pass


class HeikinAshiBar(NamedTuple):
    """
    1. The use of class:
       Immutable point-in-time representation of a Heikin Ashi display candle.

    2. What the class contains:
       - index: Original bar index.
       - ha_open: Smoothed Heikin Ashi open.
       - ha_high: Smoothed Heikin Ashi high.
       - ha_low: Smoothed Heikin Ashi low.
       - ha_close: Smoothed Heikin Ashi close.
       - is_display_transform_only: Hard-coded True to guard against trade execution misuse.

    3. Technologies used and why:
       NamedTuple for compact memory and fast serialization.

    4. Key design and overall design of the class:
       Guarantees architectural separation between display transforms and tradable prices.
    """
    index: int
    ha_open: float
    ha_high: float
    ha_low: float
    ha_close: float
    is_display_transform_only: bool = True


def compute_heikin_ashi(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> List[HeikinAshiBar]:
    """
    1. The use of function:
       Computes Heikin Ashi display candles with canonical TradingView seeding.

    2. How does the specific function work:
       1. Validates equal sequence lengths.
       2. Bar 0 seed:
          ha_close_0 = (opens[0] + highs[0] + lows[0] + closes[0]) / 4.0
          ha_open_0  = (opens[0] + closes[0]) / 2.0
          ha_high_0  = max(highs[0], ha_open_0, ha_close_0)
          ha_low_0   = min(lows[0], ha_open_0, ha_close_0)
       3. Subsequent bars t:
          ha_close_t = (opens[t] + highs[t] + lows[t] + closes[t]) / 4.0
          ha_open_t  = (ha_open_{t-1} + ha_close_{t-1}) / 2.0
          ha_high_t  = max(highs[t], ha_open_t, ha_close_t)
          ha_low_t   = min(lows[t], ha_open_t, ha_close_t)
       4. Emits list of HeikinAshiBar with is_display_transform_only=True.

    3. Concepts used in the function:
       Heikin Ashi autoregressive smoothing, non-tradable display invariant.

    4. Places where this function is imported and used:
       Used by UI chart endpoints, visual viewers, and unit tests.

    5. Final output of the function, before and after:
       Before: Standard OHLC sequences. After: List of HeikinAshiBar.
    """
    n = len(closes)
    if len(opens) != n or len(highs) != n or len(lows) != n:
        raise ValueError(
            f"Length mismatch: opens({len(opens)}), highs({len(highs)}), "
            f"lows({len(lows)}), closes({n})."
        )
    if n == 0:
        return []

    results: List[HeikinAshiBar] = []

    # Bar 0 Seed
    c0 = (opens[0] + highs[0] + lows[0] + closes[0]) / 4.0
    o0 = (opens[0] + closes[0]) / 2.0
    h0 = max(highs[0], o0, c0)
    l0 = min(lows[0], o0, c0)

    results.append(
        HeikinAshiBar(
            index=0,
            ha_open=round(o0, 4),
            ha_high=round(h0, 4),
            ha_low=round(l0, 4),
            ha_close=round(c0, 4),
            is_display_transform_only=True,
        )
    )

    prev_o = o0
    prev_c = c0

    for t in range(1, n):
        c_t = (opens[t] + highs[t] + lows[t] + closes[t]) / 4.0
        o_t = (prev_o + prev_c) / 2.0
        h_t = max(highs[t], o_t, c_t)
        l_t = min(lows[t], o_t, c_t)

        results.append(
            HeikinAshiBar(
                index=t,
                ha_open=round(o_t, 4),
                ha_high=round(h_t, 4),
                ha_low=round(l_t, 4),
                ha_close=round(c_t, 4),
                is_display_transform_only=True,
            )
        )
        prev_o = o_t
        prev_c = c_t

    return results


def register_heikin_ashi_feature() -> str:
    """
    1. The use of function:
       Registers HEIKIN_ASHI transform definition into FeatureRegistry.

    2. How does the specific function work:
       Constructs FeatureDefinition and registers into FeatureRegistry.

    3. Concepts used in the function:
       Feature registration, INFINITE memory class (autoregressive open).

    4. Places where this function is imported and used:
       Called during package initialization.

    5. Final output of the function, before and after:
       Before: Unregistered. After: feature_id string.
    """
    defn = FeatureDefinition(
        name="HEIKIN_ASHI",
        version="v1",
        params={},
        lookback_window=1,
        warm_up_bars=1,
        memory_class=MemoryClass.INFINITE,
        source_tier=SourceTier.UNDERLYING_CANDLE,
        repaint_class=RepaintClass.NONE,
        output_schema={
            "ha_open": "float64",
            "ha_high": "float64",
            "ha_low": "float64",
            "ha_close": "float64",
            "is_display_transform_only": "bool",
        },
        description="Heikin Ashi display transform (ENGINE §22). Strictly non-tradable display values.",
    )
    registry = FeatureRegistry()
    return registry.register(
        definition=defn,
        compute_fn=compute_heikin_ashi,
        metadata={"category": "display_transform", "tradable": False},
    )
