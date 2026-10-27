"""
1. What this file does:
   Implements 25-delta Risk Reversal Skew and 25-delta Butterfly Volatility Smile metrics
   for European index options (ENGINE §21.1, Task M5-12 / Gate G3).

2. Overall design:
   Extracts point-in-time model IV values from liquid ATM band Greeks results:
   - 25-Delta Skew = IV(25-Delta Put) - IV(25-Delta Call)
   - 25-Delta Fly  = [IV(25-Delta Call) + IV(25-Delta Put)] / 2.0 - IV(ATM)
   Provides quantitative metrics for market downside crash risk pricing and volatility curvature.

3. Elements in the file:
   - SkewResult: NamedTuple representing 25-delta skew and fly outputs.
   - compute_iv_skew_and_fly: Core calculation locating 25-delta contracts and evaluating skew/fly.
   - register_skew_feature: Registry helper binding skew feature to FeatureRegistry.

4. Final output of the file:
   - Causal volatility surface skew and smile feature stream.
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
from packages.features.volatility.greeks_solver import ModelGreeksResult


class SkewResult(NamedTuple):
    """
    1. The use of class:
       Immutable point-in-time record of 25-delta volatility skew and butterfly smile.

    2. What the class contains:
       - iv_skew_25d: 25-delta Put IV minus 25-delta Call IV (annualized float) or None.
       - iv_fly_25d: 25-delta Butterfly curvature relative to ATM IV or None.
       - call_25d_strike: Strike of the selected ~25-delta Call contract.
       - put_25d_strike: Strike of the selected ~25-delta Put contract.
       - atm_iv: ATM implied volatility.
       - is_valid: True if both 25-delta legs and ATM IV were validly resolved.

    3. Technologies used and why:
       NamedTuple for compact, zero-overhead storage.

    4. Key design and overall design of the class:
       Standard quantitative representation of volatility surface skew and wing curvature.
    """
    iv_skew_25d: Optional[float]
    iv_fly_25d: Optional[float]
    call_25d_strike: Optional[float]
    put_25d_strike: Optional[float]
    atm_iv: Optional[float]
    is_valid: bool


def compute_iv_skew_and_fly(
    greeks_results: Sequence[ModelGreeksResult],
    atm_strike: float,
) -> SkewResult:
    """
    1. The use of function:
       Calculates 25-delta Risk Reversal Skew and Butterfly curvature.

    2. How does the specific function work:
       1. Finds ATM IV from contract at strike == atm_strike.
       2. Finds Call contract whose model_delta is closest to +0.25 (within [0.10, 0.40]).
       3. Finds Put contract whose model_delta is closest to -0.25 (within [-0.40, -0.10]).
       4. If all three have valid model_iv:
          skew = put_iv - call_iv
          fly  = (call_iv + put_iv) / 2.0 - atm_iv
          is_valid = True
       5. Else returns SkewResult with None values and is_valid=False.

    3. Concepts used in the function:
       Delta-neutral straddle skew, 25-delta risk reversal, smile curvature.

    4. Places where this function is imported and used:
       Used by volatility trading strategies, market regime detectors, and unit tests.

    5. Final output of the function, before and after:
       Before: ModelGreeksResult list. After: SkewResult NamedTuple.
    """
    atm_calls = [r for r in greeks_results if r.strike == atm_strike and r.option_type == "CE" and r.model_iv is not None]
    atm_puts = [r for r in greeks_results if r.strike == atm_strike and r.option_type == "PE" and r.model_iv is not None]

    if atm_calls and atm_puts:
        atm_iv = 0.5 * (atm_calls[0].model_iv + atm_puts[0].model_iv)  # type: ignore[operator]
    elif atm_calls:
        atm_iv = atm_calls[0].model_iv
    elif atm_puts:
        atm_iv = atm_puts[0].model_iv
    else:
        atm_iv = None

    # Find 25-delta Call (target delta +0.25)
    best_call: Optional[ModelGreeksResult] = None
    min_call_diff = float("inf")
    for r in greeks_results:
        if r.option_type == "CE" and r.model_delta is not None and r.model_iv is not None:
            if 0.10 <= r.model_delta <= 0.40:
                diff = abs(r.model_delta - 0.25)
                if diff < min_call_diff:
                    min_call_diff = diff
                    best_call = r

    # Find 25-delta Put (target delta -0.25)
    best_put: Optional[ModelGreeksResult] = None
    min_put_diff = float("inf")
    for r in greeks_results:
        if r.option_type == "PE" and r.model_delta is not None and r.model_iv is not None:
            if -0.40 <= r.model_delta <= -0.10:
                diff = abs(r.model_delta - (-0.25))
                if diff < min_put_diff:
                    min_put_diff = diff
                    best_put = r

    if (
        best_call is not None
        and best_put is not None
        and atm_iv is not None
        and best_call.model_iv is not None
        and best_put.model_iv is not None
    ):
        skew = round(best_put.model_iv - best_call.model_iv, 6)
        fly = round(0.5 * (best_call.model_iv + best_put.model_iv) - atm_iv, 6)
        return SkewResult(
            iv_skew_25d=skew,
            iv_fly_25d=fly,
            call_25d_strike=best_call.strike,
            put_25d_strike=best_put.strike,
            atm_iv=round(atm_iv, 6),
            is_valid=True,
        )

    return SkewResult(
        iv_skew_25d=None,
        iv_fly_25d=None,
        call_25d_strike=best_call.strike if best_call else None,
        put_25d_strike=best_put.strike if best_put else None,
        atm_iv=round(atm_iv, 6) if atm_iv is not None else None,
        is_valid=False,
    )


def register_skew_feature() -> str:
    """
    1. The use of function:
       Registers IV_SKEW_25D feature definition into FeatureRegistry.

    2. How does the specific function work:
       Constructs FeatureDefinition with ZERO_REPAINT class and binds compute_iv_skew_and_fly.

    3. Concepts used in the function:
       Registry binding, MODEL_DERIVED source tier.

    4. Places where this function is imported and used:
       Called during feature package discovery and registry initialization.

    5. Final output of the function, before and after:
       Before: Unregistered feature. After: Registered feature ID string.
    """
    defn = FeatureDefinition(
        name="IV_SKEW_25D",
        version="v1",
        params={},
        lookback_window=1,
        warm_up_bars=1,
        memory_class=MemoryClass.FINITE,
        source_tier=SourceTier.MODEL_DERIVED,
        repaint_class=RepaintClass.NONE,
        output_schema={
            "iv_skew_25d": "float64",
            "iv_fly_25d": "float64",
            "atm_iv": "float64",
            "is_valid": "bool",
        },
        description="25-delta Risk Reversal Skew and 25-delta Butterfly Volatility Smile metrics.",
    )
    registry = FeatureRegistry()
    return registry.register(
        definition=defn,
        compute_fn=compute_iv_skew_and_fly,
        metadata={"category": "volatility"},
    )
