"""
1. What this file does:
   Implements Candle Bar Volume Delta Proxy based on intra-candle close location
   relative to high-low range (ENGINE §21.1, Gate G3).

2. Overall design:
   Estimates buying vs selling volume from bar geometry:
     Buy_Ratio = (close - low) / (high - low) if range > 0 else 0.5
     Est_Buy_Vol = volume * Buy_Ratio
     Est_Sell_Vol = volume * (1.0 - Buy_Ratio)
     Bar_Volume_Delta = Est_Buy_Vol - Est_Sell_Vol
   Clearly labelled as a Candle-Derived Volume Position Proxy; lacks tick buyer/seller
   aggressor flags and is never claimed as genuine order-flow trade arrival delta.

3. Elements in the file:
   - CandleDeltaResult: NamedTuple representing estimated buy/sell volumes and delta.
   - compute_candle_volume_delta: Core calculation function evaluating single bar delta.
   - compute_series_candle_delta: Vectorized / sequence evaluator across candle bars.
   - register_candle_delta_feature: Registry helper binding feature to FeatureRegistry.

4. Final output of the file:
   - Causal candle-derived volume imbalance proxy series with explicit quality flags.
"""

from typing import List, NamedTuple, Sequence

from packages.features.registry import FeatureRegistry
from packages.features.schemas import (
    FeatureDefinition,
    MemoryClass,
    RepaintClass,
    SourceTier,
)


class CandleDeltaResult(NamedTuple):
    """
    1. The use of class:
       Immutable point-in-time representation of estimated candle volume delta.

    2. What the class contains:
       - est_buy_volume: Estimated buying volume (float).
       - est_sell_volume: Estimated selling volume (float).
       - bar_volume_delta: Net volume delta (Buy - Sell).
       - buy_ratio: Ratio of close position within bar range [0.0, 1.0].
       - quality_flags: Diagnostic quality flags (e.g. ['VALID'], ['ZERO_VOLUME_BAR'], ['FLAT_BAR']).

    3. Technologies used and why:
       NamedTuple for compact, zero-overhead storage.

    4. Key design and overall design of the class:
       Encapsulates candle-derived volume proxies with explicit honest lineage tags.
    """
    est_buy_volume: float
    est_sell_volume: float
    bar_volume_delta: float
    buy_ratio: float
    quality_flags: List[str]


def compute_candle_volume_delta(
    high: float,
    low: float,
    close: float,
    volume: int,
) -> CandleDeltaResult:
    """
    1. The use of function:
       Computes estimated volume delta for an individual closed candle bar.

    2. How does the specific function work:
       1. Calculates bar range = high - low.
       2. If range <= 1e-9 (flat bar):
          buy_ratio = 0.5
       3. Else:
          buy_ratio = min(1.0, max(0.0, (close - low) / range))
       4. Computes est_buy_vol = volume * buy_ratio, est_sell_vol = volume * (1 - buy_ratio).
       5. Delta = est_buy_vol - est_sell_vol.
       6. Assigns flags: ZERO_VOLUME_BAR if volume == 0, FLAT_BAR if range == 0.

    3. Concepts used in the function:
       Bar close location value (CLV), volume positioning proxy.

    4. Places where this function is imported and used:
       Used by technical volume indicators, chart analytics, and unit tests.

    5. Final output of the function, before and after:
       Before: High, low, close, volume. After: CandleDeltaResult.
    """
    bar_range = high - low
    flags: List[str] = []

    if volume <= 0:
        flags.append("ZERO_VOLUME_BAR")
        return CandleDeltaResult(
            est_buy_volume=0.0,
            est_sell_volume=0.0,
            bar_volume_delta=0.0,
            buy_ratio=0.5,
            quality_flags=flags,
        )

    if bar_range <= 1e-9:
        flags.append("FLAT_BAR")
        buy_ratio = 0.5
    else:
        buy_ratio = max(0.0, min(1.0, (close - low) / bar_range))
        flags.append("VALID")

    est_buy = round(volume * buy_ratio, 2)
    est_sell = round(volume * (1.0 - buy_ratio), 2)
    delta = round(est_buy - est_sell, 2)

    return CandleDeltaResult(
        est_buy_volume=est_buy,
        est_sell_volume=est_sell,
        bar_volume_delta=delta,
        buy_ratio=round(buy_ratio, 4),
        quality_flags=flags,
    )


def compute_series_candle_delta(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[int],
) -> List[CandleDeltaResult]:
    """
    1. The use of function:
       Evaluates candle volume delta chronologically across a series of bars.

    2. How does the specific function work:
       Iterates t from 0 to N-1 and calls compute_candle_volume_delta for each bar.

    3. Concepts used in the function:
       Vectorized candle delta series evaluation.

    4. Places where this function is imported and used:
       Used by feature extractors and strategy contexts.

    5. Final output of the function, before and after:
       Before: OHLCV sequences. After: List of CandleDeltaResult.
    """
    n = len(closes)
    if len(highs) != n or len(lows) != n or len(volumes) != n:
        raise ValueError(
            f"Length mismatch: highs({len(highs)}), lows({len(lows)}), "
            f"closes({n}), volumes({len(volumes)})."
        )
    return [
        compute_candle_volume_delta(highs[t], lows[t], closes[t], volumes[t])
        for t in range(n)
    ]


def register_candle_delta_feature() -> str:
    """
    1. The use of function:
       Registers CANDLE_VOLUME_DELTA feature definition into FeatureRegistry.

    2. How does the specific function work:
       Constructs FeatureDefinition and registers into FeatureRegistry.

    3. Concepts used in the function:
       Feature registration, UNDERLYING_CANDLE source tier.

    4. Places where this function is imported and used:
       Called during package initialization.

    5. Final output of the function, before and after:
       Before: Unregistered. After: feature_id string.
    """
    defn = FeatureDefinition(
        name="CANDLE_VOLUME_DELTA",
        version="v1",
        params={},
        lookback_window=1,
        warm_up_bars=1,
        memory_class=MemoryClass.FINITE,
        source_tier=SourceTier.UNDERLYING_CANDLE,
        repaint_class=RepaintClass.NONE,
        output_schema={
            "bar_volume_delta": "float64",
            "est_buy_volume": "float64",
            "est_sell_volume": "float64",
            "buy_ratio": "float64",
        },
        description="Candle Bar Volume Delta proxy estimating buy/sell volume from bar close position.",
    )
    registry = FeatureRegistry()
    return registry.register(
        definition=defn,
        compute_fn=compute_series_candle_delta,
        metadata={"category": "orderflow_proxy"},
    )
