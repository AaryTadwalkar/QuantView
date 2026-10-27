"""
1. What this file does:
   Implements point-in-time option-chain derived features for QuantView: Put-Call Ratio (PCR),
   Open Interest Rate of Change (OI ROC), ATM Straddle premium & synthetic IV, and Delta-band
   aggregate OI distributions (ENGINE §21.1, DATA §4.4, Task M5-12 / Gate G3).

2. Overall design:
   Evaluates aggregate market positioning and derivatives sentiment across reconstructed option chains:
   - PCR: Total and near-ATM Put-Call ratios by Open Interest and Traded Volume with division-by-zero guards.
   - OI ROC: Point-in-time percentage change in open interest per strike and aggregate.
   - ATM Straddle Premium: Combined price of ATM Call and Put, with Brenner-Subrahmanyam synthetic IV.
   - Delta-Band OI: Aggregate open interest categorized by Delta sensitivity buckets.

3. Elements in the file:
   - compute_pcr: Evaluates Put-Call ratio by OI or Volume.
   - compute_oi_roc: Evaluates rate of change in open interest.
   - compute_atm_straddle: Extracts combined ATM Straddle premium and synthetic ATM IV.
   - compute_delta_band_oi: Aggregates open interest into Delta buckets (Deep OTM, OTM, ATM, ITM).
   - register_pcr_feature, register_straddle_feature: FeatureRegistry registration helpers.

4. Final output of the file:
   - Causal, division-safe option chain positioning and volatility metrics.
"""

import math
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple
from packages.features.chain.lazy_chain import ReconstructedOptionChain
from packages.features.schemas import (
    FeatureDefinition,
    FeatureStatus,
    MemoryClass,
    RepaintClass,
    SourceTier,
)
from packages.features.registry import FeatureRegistry
from packages.features.volatility.black76 import black76_price
from packages.features.volatility.greeks_solver import ModelGreeksResult


class StraddleResult(NamedTuple):
    """
    1. The use of class:
       Immutable output record of ATM Straddle metrics.

    2. What the class contains:
       - atm_strike: At-The-Money strike price.
       - call_price: ATM Call closing price.
       - put_price: ATM Put closing price.
       - straddle_premium: Combined premium (Call + Put).
       - synthetic_iv: Annualized synthetic IV estimated from straddle premium.
       - is_valid: True if both Call and Put quotes were valid and present.

    3. Technologies used and why:
       NamedTuple for compact, zero-overhead storage.

    4. Key design and overall design of the class:
       Standard quantitative representation of market-implied daily expected move.
    """
    atm_strike: Optional[float]
    call_price: Optional[float]
    put_price: Optional[float]
    straddle_premium: Optional[float]
    synthetic_iv: Optional[float]
    is_valid: bool


def compute_pcr(
    chain: ReconstructedOptionChain,
    mode: str = "OI",
    near_atm_only: bool = False,
    n_strikes: int = 5,
    strike_step: float = 50.0,
) -> Tuple[Optional[float], List[str]]:
    """
    1. The use of function:
       Computes Put-Call Ratio (PCR) across the option chain.

    2. How does the specific function work:
       1. Filters eligible contracts:
          - If near_atm_only=True: restricts to ATM +/- n_strikes.
          - Else: considers all contracts in the chain.
       2. Sums Put values (OI or Volume) and Call values (OI or Volume).
       3. If call_sum == 0: returns (None, ['DIV_BY_ZERO']).
       4. Otherwise returns (round(put_sum / call_sum, 4), ['VALID']).

    3. Concepts used in the function:
       PCR sentiment indicator, fail-closed zero-denominator handling.

    4. Places where this function is imported and used:
       Used by market sentiment features, directional strategies, and unit tests.

    5. Final output of the function, before and after:
       Before: ReconstructedOptionChain and mode ('OI' or 'VOLUME').
       After: (pcr_float, quality_flags).
    """
    eligible_strikes = None
    if near_atm_only:
        atm = chain.get_atm_strike(strike_step)
        if atm is not None:
            eligible_strikes = set(
                atm + (offset * strike_step) for offset in range(-n_strikes, n_strikes + 1)
            )

    put_sum = 0
    call_sum = 0
    is_volume_mode = mode.upper() == "VOLUME"

    for r in chain._row_map.values():
        if not r.is_available:
            continue
        if eligible_strikes is not None and r.strike not in eligible_strikes:
            continue

        val = r.volume if is_volume_mode else r.oi
        if r.option_type == "PE":
            put_sum += val
        elif r.option_type == "CE":
            call_sum += val

    if call_sum == 0:
        return (None, ["DIV_BY_ZERO"])

    pcr = round(put_sum / float(call_sum), 4)
    return (pcr, ["VALID"])


def compute_oi_roc(
    current_oi: int,
    previous_oi: int,
    percentage: bool = True,
) -> Optional[float]:
    """
    1. The use of function:
       Computes Rate of Change (ROC) in Open Interest.

    2. How does the specific function work:
       If percentage=True:
         If previous_oi == 0: returns None if current_oi > 0 else 0.0.
         Else returns round((current_oi - previous_oi) / previous_oi, 4).
       If percentage=False:
         Returns float(current_oi - previous_oi).

    3. Concepts used in the function:
       Open interest buildup and unwinding analysis.

    4. Places where this function is imported and used:
       Used by strike-level and aggregate open interest momentum features.

    5. Final output of the function, before and after:
       Before: Current and previous integer OI. After: Float rate of change.
    """
    delta = current_oi - previous_oi
    if not percentage:
        return float(delta)

    if previous_oi == 0:
        return 0.0 if current_oi == 0 else None

    return round(delta / float(previous_oi), 4)


def compute_atm_straddle(
    chain: ReconstructedOptionChain,
    tau: Optional[float] = None,
    r: float = 0.065,
    strike_step: float = 50.0,
) -> StraddleResult:
    """
    1. The use of function:
       Extracts point-in-time ATM Straddle premium and computes synthetic implied volatility.

    2. How does the specific function work:
       1. Finds ATM strike from spot_price.
       2. Looks up ATM CE and ATM PE contracts.
       3. If both quotes exist:
          premium = ce.close + pe.close
          If tau is provided and tau > 0:
            Calculates synthetic IV via Brenner-Subrahmanyam formula:
              sigma_synth = premium / (0.8 * spot * sqrt(tau))
          Emits StraddleResult with is_valid=True.
       4. Otherwise emits StraddleResult with is_valid=False.

    3. Concepts used in the function:
       ATM Straddle pricing, expected daily range, Brenner-Subrahmanyam IV approximation.

    4. Places where this function is imported and used:
       Used by straddle trading strategies, volatility cones, and unit tests.

    5. Final output of the function, before and after:
       Before: ReconstructedOptionChain and optional tau. After: StraddleResult.
    """
    atm_strike = chain.get_atm_strike(strike_step)
    if atm_strike is None or chain.spot_price is None:
        return StraddleResult(
            atm_strike=None,
            call_price=None,
            put_price=None,
            straddle_premium=None,
            synthetic_iv=None,
            is_valid=False,
        )

    ce = chain.get_contract(atm_strike, "CE")
    pe = chain.get_contract(atm_strike, "PE")

    if (
        ce is not None
        and pe is not None
        and ce.is_available
        and pe.is_available
        and ce.option_close is not None
        and pe.option_close is not None
    ):
        premium = round(ce.option_close + pe.option_close, 2)
        synth_iv = None
        if tau is not None and tau > 1e-6 and chain.spot_price > 0.0:
            # Brenner & Subrahmanyam (1988) ATM Straddle Inversion
            # Straddle ~ 0.8 * S * sigma * sqrt(tau)
            bs_iv = premium / (0.8 * chain.spot_price * math.sqrt(tau))
            synth_iv = round(max(0.01, min(5.0, bs_iv)), 4)

        return StraddleResult(
            atm_strike=atm_strike,
            call_price=ce.option_close,
            put_price=pe.option_close,
            straddle_premium=premium,
            synthetic_iv=synth_iv,
            is_valid=True,
        )

    return StraddleResult(
        atm_strike=atm_strike,
        call_price=ce.option_close if (ce and ce.is_available) else None,
        put_price=pe.option_close if (pe and pe.is_available) else None,
        straddle_premium=None,
        synthetic_iv=None,
        is_valid=False,
    )


def compute_delta_band_oi(
    chain: ReconstructedOptionChain,
    greeks_results: Sequence[ModelGreeksResult],
) -> Dict[str, int]:
    """
    1. The use of function:
       Aggregates Open Interest across Delta sensitivity buckets.

    2. How does the specific function work:
       Categorizes each contract into one of four Delta bins based on absolute model_delta:
       - DEEP_OTM: |Delta| < 0.15
       - OTM:      0.15 <= |Delta| < 0.35
       - ATM:      0.35 <= |Delta| < 0.65
       - ITM:      |Delta| >= 0.65
       Sums open interest for eligible contracts in each bin.

    3. Concepts used in the function:
       Delta-weighted market positioning distribution.

    4. Places where this function is imported and used:
       Used by delta-band positioning features and risk evaluators.

    5. Final output of the function, before and after:
       Before: Chain and ModelGreeksResult list. After: Dict mapping bucket name to total OI int.
    """
    buckets: Dict[str, int] = {
        "DEEP_OTM": 0,
        "OTM": 0,
        "ATM": 0,
        "ITM": 0,
        "UNASSIGNED": 0,
    }

    # Map (strike, option_type) -> model_delta
    delta_map = {
        (g.strike, g.option_type): g.model_delta for g in greeks_results if g.model_delta is not None
    }

    for r in chain._row_map.values():
        if not r.is_available or r.oi <= 0:
            continue
        key = (r.strike, r.option_type)
        delta = delta_map.get(key)
        if delta is None:
            buckets["UNASSIGNED"] += r.oi
            continue

        abs_d = abs(delta)
        if abs_d < 0.15:
            buckets["DEEP_OTM"] += r.oi
        elif abs_d < 0.35:
            buckets["OTM"] += r.oi
        elif abs_d < 0.65:
            buckets["ATM"] += r.oi
        else:
            buckets["ITM"] += r.oi

    return buckets


def register_pcr_feature() -> str:
    """
    1. The use of function:
       Registers PCR feature definition into FeatureRegistry.

    2. How does the specific function work:
       Constructs FeatureDefinition and registers into FeatureRegistry.

    3. Concepts used in the function:
       Feature registration.

    4. Places where this function is imported and used:
       Called during package initialization.

    5. Final output of the function, before and after:
       Before: Unregistered. After: feature_id string.
    """
    defn = FeatureDefinition(
        name="PCR",
        version="v1",
        params={"mode": "OI", "near_atm_only": False},
        lookback_window=1,
        warm_up_bars=1,
        memory_class=MemoryClass.FINITE,
        source_tier=SourceTier.OPTION_CANDLE,
        repaint_class=RepaintClass.NONE,
        output_schema={"pcr": "float64"},
        description="Point-in-time Put-Call Ratio by Open Interest or Volume with zero division guard.",
    )
    registry = FeatureRegistry()
    return registry.register(
        definition=defn,
        compute_fn=compute_pcr,
        metadata={"category": "chain_derived"},
    )
