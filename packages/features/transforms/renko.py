"""
1. What this file does:
   Implements Renko brick mathematical contract, generation algorithm, and confirmation-time
   rules for QuantView (ENGINE §18.1, §22, Task M5-09 / Gate G3).

2. Overall design:
   Evaluates point-in-time Renko bricks with fixed brick sizes and standard 2-brick reversal rules:
   - Continuation: Price moves >= 1 brick_size beyond current brick close in trend direction.
   - Reversal: Price moves >= 2 * brick_size beyond current brick close in opposite direction.
   - Confirmation Time: Each brick is causally confirmed at the close timestamp of the candle bar
     that exceeded the brick threshold (confirmed_at = ts_close[t]).
   - Strict Invariant: Renko bricks are price action transforms only; they are non-tradable and
     must never be substituted for real market OHLC in execution or financial ledgers.

3. Elements in the file:
   - RenkoBrick: NamedTuple holding individual brick boundaries, direction, and confirmation timestamp.
   - compute_renko_bricks: Core algorithm generating causal Renko bricks from price sequences.
   - register_renko_feature: Registry helper binding transform to FeatureRegistry.

4. Final output of the file:
   - Causal sequence of confirmed Renko bricks with exact bar index and timestamp provenance.
"""

import math
from typing import List, NamedTuple, Optional, Sequence
from packages.features.schemas import (
    FeatureDefinition,
    FeatureStatus,
    MemoryClass,
    RepaintClass,
    SourceTier,
)
from packages.features.registry import FeatureRegistry


class RenkoBrick(NamedTuple):
    """
    1. The use of class:
       Immutable representation of a confirmed Renko brick.

    2. What the class contains:
       - brick_index: Sequential integer index of the brick.
       - bar_index: Index of the source candle bar that completed the brick.
       - confirmed_at: Timestamp when the brick causally completed.
       - open: Price level where the brick began.
       - close: Price level where the brick completed.
       - high: Maximum extent of the brick box.
       - low: Minimum extent of the brick box.
       - direction: +1 for Up (Bullish) brick, -1 for Down (Bearish) brick.
       - is_display_transform_only: Hard-coded True to guard against trade execution misuse.

    3. Technologies used and why:
       NamedTuple for compact, immutable storage.

    4. Key design and overall design of the class:
       Guarantees causal confirmation timing without future look-ahead.
    """
    brick_index: int
    bar_index: int
    confirmed_at: int
    open: float
    close: float
    high: float
    low: float
    direction: int
    is_display_transform_only: bool = True


def compute_renko_bricks(
    prices: Sequence[float],
    timestamps: Sequence[int],
    brick_size: float = 10.0,
    reversal_bricks: int = 2,
) -> List[RenkoBrick]:
    """
    1. The use of function:
       Constructs Renko bricks from an underlying price sequence and timestamps.

    2. How does the specific function work:
       1. Validates brick_size > 0 and reversal_bricks >= 1.
       2. Iterates chronologically through price points:
          - Initializes first brick once price moves >= brick_size from starting price.
          - In Bullish trend (direction = +1):
            * Continuation: If price >= current_close + brick_size:
              generates one or more Up bricks (close = current_close + brick_size).
            * Reversal: If price <= current_close - (reversal_bricks * brick_size):
              generates Down brick(s) (direction = -1).
          - In Bearish trend (direction = -1):
            * Continuation: If price <= current_close - brick_size:
              generates one or more Down bricks.
            * Reversal: If price >= current_close + (reversal_bricks * brick_size):
              generates Up brick(s) (direction = +1).
       3. Stamps each brick with confirmed_at = timestamps[t].

    3. Concepts used in the function:
       Renko brick generation, multi-brick gap handling, causal confirmation timing.

    4. Places where this function is imported and used:
       Used by chart rendering endpoints, price-action transforms, and unit tests.

    5. Final output of the function, before and after:
       Before: Price sequence and timestamps. After: List of confirmed RenkoBrick records.
    """
    if brick_size <= 0.0:
        raise ValueError(f"brick_size must be > 0, got {brick_size}.")
    if reversal_bricks < 1:
        raise ValueError(f"reversal_bricks must be >= 1, got {reversal_bricks}.")
    n = len(prices)
    if len(timestamps) != n:
        raise ValueError(f"Length mismatch: prices({n}) vs timestamps({len(timestamps)}).")
    if n == 0:
        return []

    bricks: List[RenkoBrick] = []
    current_direction = 0  # 0: Unset, +1: Up, -1: Down
    current_close = prices[0]
    brick_count = 0

    for t in range(1, n):
        p = prices[t]
        ts = timestamps[t]

        if current_direction == 0:
            # Initializing direction
            diff = p - current_close
            if diff >= brick_size:
                num_bricks = int(diff // brick_size)
                for _ in range(num_bricks):
                    b_open = current_close
                    b_close = current_close + brick_size
                    bricks.append(
                        RenkoBrick(
                            brick_index=brick_count,
                            bar_index=t,
                            confirmed_at=ts,
                            open=round(b_open, 4),
                            close=round(b_close, 4),
                            high=round(max(b_open, b_close), 4),
                            low=round(min(b_open, b_close), 4),
                            direction=+1,
                        )
                    )
                    brick_count += 1
                    current_close = b_close
                current_direction = +1

            elif diff <= -brick_size:
                num_bricks = int(abs(diff) // brick_size)
                for _ in range(num_bricks):
                    b_open = current_close
                    b_close = current_close - brick_size
                    bricks.append(
                        RenkoBrick(
                            brick_index=brick_count,
                            bar_index=t,
                            confirmed_at=ts,
                            open=round(b_open, 4),
                            close=round(b_close, 4),
                            high=round(max(b_open, b_close), 4),
                            low=round(min(b_open, b_close), 4),
                            direction=-1,
                        )
                    )
                    brick_count += 1
                    current_close = b_close
                current_direction = -1

        elif current_direction == +1:
            # Current Up Trend
            if p >= current_close + brick_size:
                # Continuation
                num_bricks = int((p - current_close) // brick_size)
                for _ in range(num_bricks):
                    b_open = current_close
                    b_close = current_close + brick_size
                    bricks.append(
                        RenkoBrick(
                            brick_index=brick_count,
                            bar_index=t,
                            confirmed_at=ts,
                            open=round(b_open, 4),
                            close=round(b_close, 4),
                            high=round(max(b_open, b_close), 4),
                            low=round(min(b_open, b_close), 4),
                            direction=+1,
                        )
                    )
                    brick_count += 1
                    current_close = b_close

            elif p <= current_close - (reversal_bricks * brick_size):
                # Reversal: First brick forms at current_close - brick_size
                diff = current_close - p
                num_bricks = int(diff // brick_size)
                # First reversal brick
                b_open = current_close
                b_close = current_close - (reversal_bricks * brick_size)
                bricks.append(
                    RenkoBrick(
                        brick_index=brick_count,
                        bar_index=t,
                        confirmed_at=ts,
                        open=round(b_open, 4),
                        close=round(b_close, 4),
                        high=round(max(b_open, b_close), 4),
                        low=round(min(b_open, b_close), 4),
                        direction=-1,
                    )
                )
                brick_count += 1
                current_close = b_close
                current_direction = -1

                # Any additional continuation bricks from this large bar
                rem_diff = current_close - p
                if rem_diff >= brick_size:
                    extra_bricks = int(rem_diff // brick_size)
                    for _ in range(extra_bricks):
                        b_open = current_close
                        b_close = current_close - brick_size
                        bricks.append(
                            RenkoBrick(
                                brick_index=brick_count,
                                bar_index=t,
                                confirmed_at=ts,
                                open=round(b_open, 4),
                                close=round(b_close, 4),
                                high=round(max(b_open, b_close), 4),
                                low=round(min(b_open, b_close), 4),
                                direction=-1,
                            )
                        )
                        brick_count += 1
                        current_close = b_close

        elif current_direction == -1:
            # Current Down Trend
            if p <= current_close - brick_size:
                # Continuation
                num_bricks = int((current_close - p) // brick_size)
                for _ in range(num_bricks):
                    b_open = current_close
                    b_close = current_close - brick_size
                    bricks.append(
                        RenkoBrick(
                            brick_index=brick_count,
                            bar_index=t,
                            confirmed_at=ts,
                            open=round(b_open, 4),
                            close=round(b_close, 4),
                            high=round(max(b_open, b_close), 4),
                            low=round(min(b_open, b_close), 4),
                            direction=-1,
                        )
                    )
                    brick_count += 1
                    current_close = b_close

            elif p >= current_close + (reversal_bricks * brick_size):
                # Reversal
                b_open = current_close
                b_close = current_close + (reversal_bricks * brick_size)
                bricks.append(
                    RenkoBrick(
                        brick_index=brick_count,
                        bar_index=t,
                        confirmed_at=ts,
                        open=round(b_open, 4),
                        close=round(b_close, 4),
                        high=round(max(b_open, b_close), 4),
                        low=round(min(b_open, b_close), 4),
                        direction=+1,
                    )
                )
                brick_count += 1
                current_close = b_close
                current_direction = +1

                rem_diff = p - current_close
                if rem_diff >= brick_size:
                    extra_bricks = int(rem_diff // brick_size)
                    for _ in range(extra_bricks):
                        b_open = current_close
                        b_close = current_close + brick_size
                        bricks.append(
                            RenkoBrick(
                                brick_index=brick_count,
                                bar_index=t,
                                confirmed_at=ts,
                                open=round(b_open, 4),
                                close=round(b_close, 4),
                                high=round(max(b_open, b_close), 4),
                                low=round(min(b_open, b_close), 4),
                                direction=+1,
                            )
                        )
                        brick_count += 1
                        current_close = b_close

    return bricks


def register_renko_feature() -> str:
    """
    1. The use of function:
       Registers RENKO transform definition into FeatureRegistry.

    2. How does the specific function work:
       Constructs FeatureDefinition and registers into FeatureRegistry.

    3. Concepts used in the function:
       Feature registration, CONFIRMED_LAG repaint class.

    4. Places where this function is imported and used:
       Called during package initialization.

    5. Final output of the function, before and after:
       Before: Unregistered. After: feature_id string.
    """
    defn = FeatureDefinition(
        name="RENKO",
        version="v1",
        params={"brick_size": 10.0, "reversal_bricks": 2},
        lookback_window=1,
        warm_up_bars=1,
        memory_class=MemoryClass.INFINITE,
        source_tier=SourceTier.UNDERLYING_CANDLE,
        repaint_class=RepaintClass.CONFIRMED_LAG,
        output_schema={
            "open": "float64",
            "close": "float64",
            "direction": "int32",
            "confirmed_at": "int64",
            "is_display_transform_only": "bool",
        },
        description="Renko brick display transform with causal confirmation timing (ENGINE §22).",
    )
    registry = FeatureRegistry()
    return registry.register(
        definition=defn,
        compute_fn=compute_renko_bricks,
        metadata={"category": "display_transform", "tradable": False},
    )
