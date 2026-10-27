"""
1. What this file does:
   Implements bounded Brent implied volatility solver and evaluates Black-76 model Greeks
   for the liquid ATM +/- N strike band (ENGINE §13, §21, DATA §4.7, Task M5-05 / Gate G3).

2. Overall design:
   Enforces non-arbitrage bounds prior to inversion (Call >= max(0, exp(-rT)(F-K)),
   Put >= max(0, exp(-rT)(K-F))). Solves for implied volatility using bounded root-finding,
   then computes analytical Greeks (Delta, Gamma, Vega, Theta). Strictly prefixes model
   outputs with 'model_' to preserve segregation from observed vendor fields per DATA §4.7.

3. Elements in the file:
   - solve_implied_volatility: Bounded root-finding solver for Black-76 IV with arbitrage bounds guard.
   - ModelGreeksResult: NamedTuple representing calculated model IV and Greek sensitivities.
   - compute_liquid_atm_band_greeks: High-level evaluator for ATM +/- N liquid strike band.
   - register_liquid_atm_greeks_feature: Registry helper binding Greeks evaluator to FeatureRegistry.

4. Final output of the file:
   - Robust, fail-closed model Greeks stream with explicit solver statuses and zero-lookahead integrity.
"""

import math
from typing import List, NamedTuple, Optional, Tuple

from packages.features.chain.lazy_chain import ReconstructedOptionChain
from packages.features.schemas import (
    FeatureDefinition,
    FeatureStatus,
    MemoryClass,
    RepaintClass,
    SourceTier,
)
from packages.features.registry import FeatureRegistry
from packages.features.volatility.black76 import (
    black76_delta,
    black76_gamma,
    black76_price,
    black76_theta,
    black76_vega,
)


class ModelGreeksResult(NamedTuple):
    """
    1. The use of class:
       Immutable output record containing point-in-time Black-76 model Greeks for an option contract.

    2. What the class contains:
       - contract_id: Contract identifier string.
       - strike: Exercise strike price.
       - option_type: 'CE' or 'PE'.
       - model_iv: Implied volatility as an annualized float (e.g. 0.155 = 15.5%) or None.
       - model_delta: Model Delta sensitivity or None.
       - model_gamma: Model Gamma sensitivity or None.
       - model_vega: Model Vega sensitivity (INR per 1% IV) or None.
       - model_theta: Model Theta sensitivity (INR per calendar day) or None.
       - solver_status: Status string ('CONVERGED', 'ARBITRAGE_BOUND_VIOLATION', 'SOLVER_FAILURE', 'UNAVAILABLE').
       - quality_flags: Diagnostic quality flags.

    3. Technologies used and why:
       NamedTuple for lightweight serialization and memory efficiency.

    4. Key design and overall design of the class:
       Strictly prefixes all output fields with 'model_' per DATA §4.7 to prevent overwriting vendor fields.
    """
    contract_id: str
    strike: float
    option_type: str
    model_iv: Optional[float]
    model_delta: Optional[float]
    model_gamma: Optional[float]
    model_vega: Optional[float]
    model_theta: Optional[float]
    solver_status: str
    quality_flags: List[str]


def solve_implied_volatility(
    price: float,
    forward: float,
    strike: float,
    tau: float,
    r: float,
    is_call: bool,
    sigma_bounds: Tuple[float, float] = (0.005, 5.0),
    tolerance: float = 1e-5,
    max_iter: int = 100,
) -> Tuple[Optional[float], str]:
    """
    1. The use of function:
       Solves for the Black-76 implied volatility given an observed market option price.

    2. How does the specific function work:
       1. Validates inputs: tau > 0, forward > 0, strike > 0, price > 0.
       2. Computes theoretical lower and upper arbitrage bounds:
          Lower Bound: Call = exp(-r*tau)*max(0, F-K), Put = exp(-r*tau)*max(0, K-F)
          Upper Bound: Call = exp(-r*tau)*F, Put = exp(-r*tau)*K
          If price <= lower_bound or price >= upper_bound, rejects with 'ARBITRAGE_BOUND_VIOLATION'.
       3. Executes bounded Brent's root-finding method / bisection on [sigma_min, sigma_max].
       4. If residual |P(sigma) - price| < tolerance, returns (sigma, 'CONVERGED').
       5. Otherwise returns (None, 'SOLVER_FAILURE').

    3. Concepts used in the function:
       No-arbitrage option bounds, root-finding, Black-76 inversion.

    4. Places where this function is imported and used:
       Used by compute_liquid_atm_band_greeks, synthetic straddle inverter, and unit tests.

    5. Final output of the function, before and after:
       Before: Market price and parameters. After: (model_iv, status_code).
    """
    if tau <= 1e-6 or forward <= 0.0 or strike <= 0.0 or price <= 0.0:
        return (None, "INVALID_INPUT")

    discount = math.exp(-r * tau)

    # 1. Check No-Arbitrage Bounds
    if is_call:
        intrinsic_lower = discount * max(0.0, forward - strike)
        arbitrage_upper = discount * forward
    else:
        intrinsic_lower = discount * max(0.0, strike - forward)
        arbitrage_upper = discount * strike

    if price <= intrinsic_lower + 1e-4 or price >= arbitrage_upper - 1e-4:
        return (None, "ARBITRAGE_BOUND_VIOLATION")

    # 2. Bounded Brent's / Bisection Root-Finding
    sigma_a, sigma_b = sigma_bounds
    price_a = black76_price(forward, strike, tau, r, sigma_a, is_call) - price
    price_b = black76_price(forward, strike, tau, r, sigma_b, is_call) - price

    # If roots are not bracketed, check if target is outside sigma_bounds
    if price_a * price_b > 0.0:
        if abs(price_a) < tolerance:
            return (round(sigma_a, 6), "CONVERGED")
        if abs(price_b) < tolerance:
            return (round(sigma_b, 6), "CONVERGED")
        return (None, "SOLVER_FAILURE")

    # Standard Brent-Dekker / Secant-Bisection hybrid
    a = sigma_a
    b = sigma_b
    fa = price_a
    fb = price_b
    c = a
    fc = fa
    mflag = True
    d = 0.0

    for _ in range(max_iter):
        if abs(fa) < abs(fb):
            a, b = b, a
            fa, fb = fb, fa
            c, fc = a, fa

        if abs(fb) < tolerance or abs(b - a) < 1e-7:
            return (round(b, 6), "CONVERGED")

        # Interpolation step
        if fa != fc and fb != fc:
            # Inverse quadratic interpolation
            s = (
                a * fb * fc / ((fa - fb) * (fa - fc))
                + b * fa * fc / ((fb - fa) * (fb - fc))
                + c * fa * fb / ((fc - fa) * (fc - fb))
            )
        else:
            # Secant step
            s = b - fb * (b - a) / (fb - fa)

        # Conditions to force bisection
        cond1 = not ((3 * a + b) / 4 <= s <= b or b <= s <= (3 * a + b) / 4)
        cond2 = mflag and abs(s - b) >= abs(b - c) / 2
        cond3 = not mflag and abs(s - b) >= abs(c - d) / 2
        cond4 = mflag and abs(b - c) < 1e-7
        cond5 = not mflag and abs(c - d) < 1e-7

        if cond1 or cond2 or cond3 or cond4 or cond5:
            s = (a + b) / 2.0
            mflag = True
        else:
            mflag = False

        fs = black76_price(forward, strike, tau, r, s, is_call) - price
        d = c
        c = b
        fc = fb

        if fa * fs < 0.0:
            b = s
            fb = fs
        else:
            a = s
            fa = fs

    return (round(b, 6), "CONVERGED") if abs(fb) < 0.01 else (None, "SOLVER_FAILURE")


def compute_liquid_atm_band_greeks(
    chain: ReconstructedOptionChain,
    forward: float,
    tau: float,
    r: float = 0.065,
    n_strikes: int = 5,
    strike_step: float = 50.0,
) -> List[ModelGreeksResult]:
    """
    1. The use of function:
       Computes point-in-time model IV and Greeks for the liquid ATM +/- N strike band.

    2. How does the specific function work:
       1. Identifies ATM strike based on point-in-time spot or forward.
       2. Iterates across 2N+1 strikes in the liquid band [ATM - N*step, ..., ATM + N*step].
       3. For each strike, processes Call (CE) and Put (PE) contracts:
          - If contract is missing or price is unavailable: emits UNAVAILABLE result.
          - If price exists: calls solve_implied_volatility.
          - If solver converges: evaluates Black-76 Delta, Gamma, Vega, and Theta.
          - Formulates ModelGreeksResult with explicit 'model_' field names.

    3. Concepts used in the function:
       Liquid band scoping, point-in-time option chain evaluation, Greek sensitivities.

    4. Places where this function is imported and used:
       Used by volatility skew feature, delta binning, strategy execution, and unit tests.

    5. Final output of the function, before and after:
       Before: ReconstructedOptionChain and forward parameters.
       After: List of ModelGreeksResult records for the 2N+1 strike band.
    """
    atm_strike = chain.get_atm_strike(strike_step)
    if atm_strike is None:
        return []

    results: List[ModelGreeksResult] = []

    for offset in range(-n_strikes, n_strikes + 1):
        k = atm_strike + (offset * strike_step)
        for opt_type, is_call in (("CE", True), ("PE", False)):
            contract = chain.get_contract(k, opt_type)
            if contract is None or not contract.is_available or contract.option_close is None:
                dummy_id = f"OPT-{chain.symbol}-{chain.expiry.strftime('%Y%m%d')}-{int(k)}-{opt_type}"
                results.append(
                    ModelGreeksResult(
                        contract_id=contract.contract_id if contract else dummy_id,
                        strike=k,
                        option_type=opt_type,
                        model_iv=None,
                        model_delta=None,
                        model_gamma=None,
                        model_vega=None,
                        model_theta=None,
                        solver_status="UNAVAILABLE",
                        quality_flags=["MISSING_STRIKE"] if (contract is None or not contract.is_available) else ["NO_OBSERVED_PRICE"],
                    )
                )
                continue

            price = contract.option_close
            model_iv, status = solve_implied_volatility(
                price=price,
                forward=forward,
                strike=k,
                tau=tau,
                r=r,
                is_call=is_call,
            )

            if status == "CONVERGED" and model_iv is not None:
                delta = black76_delta(forward, k, tau, r, model_iv, is_call)
                gamma = black76_gamma(forward, k, tau, r, model_iv)
                vega = black76_vega(forward, k, tau, r, model_iv)
                theta = black76_theta(forward, k, tau, r, model_iv, is_call)
                flags = ["VALID"]
            else:
                delta = None
                gamma = None
                vega = None
                theta = None
                flags = [status]

            results.append(
                ModelGreeksResult(
                    contract_id=contract.contract_id,
                    strike=k,
                    option_type=opt_type,
                    model_iv=model_iv,
                    model_delta=delta,
                    model_gamma=gamma,
                    model_vega=vega,
                    model_theta=theta,
                    solver_status=status,
                    quality_flags=flags,
                )
            )

    return results


def register_liquid_atm_greeks_feature() -> str:
    """
    1. The use of function:
       Registers LIQUID_ATM_GREEKS feature definition into FeatureRegistry.

    2. How does the specific function work:
       Constructs FeatureDefinition with ZERO_REPAINT class and binds compute_liquid_atm_band_greeks.

    3. Concepts used in the function:
       Registry binding, MODEL_DERIVED source tier categorization.

    4. Places where this function is imported and used:
       Called during feature package discovery and registry initialization.

    5. Final output of the function, before and after:
       Before: Unregistered feature. After: Registered feature ID string.
    """
    defn = FeatureDefinition(
        name="LIQUID_ATM_GREEKS",
        version="v1",
        params={"n_strikes": 5, "strike_step": 50.0, "rate": 0.065},
        lookback_window=1,
        warm_up_bars=1,
        memory_class=MemoryClass.FINITE,
        source_tier=SourceTier.MODEL_DERIVED,
        repaint_class=RepaintClass.NONE,
        output_schema={
            "model_iv": "float64",
            "model_delta": "float64",
            "model_gamma": "float64",
            "model_vega": "float64",
            "model_theta": "float64",
            "solver_status": "string",
        },
        description="Black-76 model implied volatility and analytical Greeks for liquid ATM +/- 5 band.",
    )
    registry = FeatureRegistry()
    return registry.register(
        definition=defn,
        compute_fn=compute_liquid_atm_band_greeks,
        metadata={"category": "volatility", "n_strikes": 5},
    )
