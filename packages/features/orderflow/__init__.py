"""
1. What this file does:
   Package exports for QuantView order flow and depth proxy features.

2. Overall design:
   Re-exports top-of-book depth imbalance and candle bar volume delta proxies.

3. Elements in the file:
   - DepthImbalanceResult, compute_depth_imbalance, register_depth_imbalance_feature.
   - CandleDeltaResult, compute_candle_volume_delta, compute_series_candle_delta, register_candle_delta_feature.

4. Final output of the file:
   - Clean public API for packages.features.orderflow.
"""

from packages.features.orderflow.depth_imbalance import (
    DepthImbalanceResult,
    compute_depth_imbalance,
    register_depth_imbalance_feature,
)
from packages.features.orderflow.candle_delta import (
    CandleDeltaResult,
    compute_candle_volume_delta,
    compute_series_candle_delta,
    register_candle_delta_feature,
)

__all__ = [
    "DepthImbalanceResult",
    "compute_depth_imbalance",
    "register_depth_imbalance_feature",
    "CandleDeltaResult",
    "compute_candle_volume_delta",
    "compute_series_candle_delta",
    "register_candle_delta_feature",
]
