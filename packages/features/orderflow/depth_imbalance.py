"""
1. What this file does:
   Implements Snapshot Top-of-Book Depth Imbalance proxy for option contracts
   and underlying markets (ENGINE §21.1, Task M5-12 / Gate G3).

2. Overall design:
   Evaluates resting top-of-book depth imbalance:
     Depth_Imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty)
   Enforces strict fail-closed zero-depth guard: when bid_qty + ask_qty == 0,
   returns None (null / unavailable), NEVER 0.0 (which would falsely represent perfect symmetry).
   Explicitly classified as a Top-of-Book Depth Imbalance Proxy, NOT trade arrival order flow.

3. Elements in the file:
   - DepthImbalanceResult: NamedTuple containing point-in-time depth imbalance and total depth.
   - compute_depth_imbalance: Pure calculation function with zero-depth guard.
   - register_depth_imbalance_feature: Registry helper binding feature to FeatureRegistry.

4. Final output of the file:
   - Causal, bounded ratio in [-1.0, +1.0] representing resting liquidity imbalance.
"""

from typing import List, NamedTuple, Optional

from packages.features.registry import FeatureRegistry
from packages.features.schemas import (
    FeatureDefinition,
    MemoryClass,
    RepaintClass,
    SourceTier,
)


class DepthImbalanceResult(NamedTuple):
    """
    1. The use of class:
       Immutable point-in-time representation of top-of-book resting depth imbalance.

    2. What the class contains:
       - depth_imbalance: Bounded float in [-1.0, +1.0] or None if depth is zero.
       - total_depth_qty: Integer sum of bid_qty and ask_qty.
       - is_valid: True if total depth > 0; False if order book depth was zero.
       - quality_flags: Diagnostic quality flags (e.g. ['VALID'], ['EMPTY_ORDER_BOOK']).

    3. Technologies used and why:
       NamedTuple for compact, zero-overhead storage.

    4. Key design and overall design of the class:
       Differentiates empty order books (None) from balanced order books (0.0).
    """
    depth_imbalance: Optional[float]
    total_depth_qty: int
    is_valid: bool
    quality_flags: List[str]


def compute_depth_imbalance(bid_qty: int, ask_qty: int) -> DepthImbalanceResult:
    """
    1. The use of function:
       Computes normalized resting top-of-book depth imbalance with zero-depth guard.

    2. How does the specific function work:
       1. Validates quantities are non-negative.
       2. Sums bid_qty and ask_qty into total_depth.
       3. If total_depth == 0:
          Returns DepthImbalanceResult(depth_imbalance=None, total_depth_qty=0,
                                       is_valid=False, quality_flags=['EMPTY_ORDER_BOOK']).
       4. Otherwise:
          imbalance = (bid_qty - ask_qty) / total_depth
          Returns DepthImbalanceResult(depth_imbalance=round(imbalance, 4),
                                       total_depth_qty=total_depth,
                                       is_valid=True, quality_flags=['VALID']).

    3. Concepts used in the function:
       Resting depth imbalance proxy, fail-closed empty book handling.

    4. Places where this function is imported and used:
       Used by option chain snapshots, market microstructure features, and unit tests.

    5. Final output of the function, before and after:
       Before: Bid and ask integer quantities. After: DepthImbalanceResult.
    """
    if bid_qty < 0 or ask_qty < 0:
        raise ValueError(f"Quantities cannot be negative: bid_qty={bid_qty}, ask_qty={ask_qty}.")

    total_depth = bid_qty + ask_qty
    if total_depth == 0:
        return DepthImbalanceResult(
            depth_imbalance=None,
            total_depth_qty=0,
            is_valid=False,
            quality_flags=["EMPTY_ORDER_BOOK"],
        )

    imbalance = (bid_qty - ask_qty) / float(total_depth)
    return DepthImbalanceResult(
        depth_imbalance=round(imbalance, 4),
        total_depth_qty=total_depth,
        is_valid=True,
        quality_flags=["VALID"],
    )


def register_depth_imbalance_feature() -> str:
    """
    1. The use of function:
       Registers DEPTH_IMBALANCE feature definition into FeatureRegistry.

    2. How does the specific function work:
       Constructs FeatureDefinition with ZERO_REPAINT class and registers into FeatureRegistry.

    3. Concepts used in the function:
       Feature registration, SNAPSHOT_CHAIN source tier.

    4. Places where this function is imported and used:
       Called during package initialization.

    5. Final output of the function, before and after:
       Before: Unregistered. After: feature_id string.
    """
    defn = FeatureDefinition(
        name="DEPTH_IMBALANCE",
        version="v1",
        params={},
        lookback_window=1,
        warm_up_bars=1,
        memory_class=MemoryClass.FINITE,
        source_tier=SourceTier.SNAPSHOT_CHAIN,
        repaint_class=RepaintClass.NONE,
        output_schema={
            "depth_imbalance": "float64",
            "total_depth_qty": "int64",
            "is_valid": "bool",
        },
        description="Top-of-book resting depth imbalance proxy with fail-closed zero depth guard.",
    )
    registry = FeatureRegistry()
    return registry.register(
        definition=defn,
        compute_fn=compute_depth_imbalance,
        metadata={"category": "orderflow_proxy"},
    )
