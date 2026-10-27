"""
1. What this file does:
   Implements analytical closed-form Black-76 pricing and Greek sensitivity equations
   for European cash-settled index options (NIFTY on NSE) per ENGINE §13, §21, DATA §4.7.

2. Overall design:
   Evaluates forward-based European option pricing and exact closed-form first and second
   order partial derivatives:
   - Delta: dPrice/dForward (Call in [0, 1], Put in [-1, 0])
   - Gamma: d^2Price/dForward^2 (1/INR)
   - Vega: dPrice/dSigma (scaled to 1 percentage point IV change: INR / 1% IV)
   - Theta: dPrice/dt (scaled to 1 calendar day decay: INR / calendar day)
   Includes robust boundary handling for tau -> 0 (expiration intrinsic payoff) and sigma -> 0.

3. Elements in the file:
   - norm_cdf, norm_pdf: Standard Gaussian cumulative distribution and density functions.
   - black76_price: Analytical forward-based European option price.
   - black76_delta: Delta sensitivity with respect to underlying forward price.
   - black76_gamma: Gamma sensitivity (second derivative).
   - black76_vega: Vega sensitivity per 1% change in implied volatility.
   - black76_theta: Theta time decay per 1 calendar day.

4. Final output of the file:
   - Pure Python / math analytical pricer emitting exact IEEE-754 Black-76 sensitivities.
"""

import math
from typing import Tuple


def norm_cdf(x: float) -> float:
    """
    1. The use of function:
       Standard Gaussian cumulative distribution function N(x).

    2. How does the specific function work:
       Computes 0.5 * (1.0 + math.erf(x / math.sqrt(2.0))).

    3. Concepts used in the function:
       Gaussian error function approximation.

    4. Places where this function is imported and used:
       Used by Black-76 price, delta, and theta calculations.

    5. Final output of the function, before and after:
       Before: Real number x. After: Cumulative probability in (0, 1).
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    """
    1. The use of function:
       Standard Gaussian probability density function N'(x).

    2. How does the specific function work:
       Computes (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x).

    3. Concepts used in the function:
       Standard normal distribution density.

    4. Places where this function is imported and used:
       Used by Gamma, Vega, and Theta analytical derivatives.

    5. Final output of the function, before and after:
       Before: Real number x. After: Probability density float.
    """
    return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)


def _compute_d1_d2(
    forward: float,
    strike: float,
    tau: float,
    sigma: float,
) -> Tuple[float, float]:
    """Internal helper computing d1 and d2 under Black-76."""
    if tau <= 0.0 or sigma <= 0.0 or forward <= 0.0 or strike <= 0.0:
        raise ValueError(
            f"Invalid inputs for d1/d2: forward={forward}, strike={strike}, tau={tau}, sigma={sigma}."
        )
    sigma_sqrt_tau = sigma * math.sqrt(tau)
    d1 = (math.log(forward / strike) + 0.5 * sigma * sigma * tau) / sigma_sqrt_tau
    d2 = d1 - sigma_sqrt_tau
    return (d1, d2)


def black76_price(
    forward: float,
    strike: float,
    tau: float,
    r: float,
    sigma: float,
    is_call: bool,
) -> float:
    """
    1. The use of function:
       Computes closed-form European option price under Black-76 model.

    2. How does the specific function work:
       If tau <= 0: returns discounted intrinsic payoff:
         Call: exp(-r*tau) * max(0, forward - strike)
         Put:  exp(-r*tau) * max(0, strike - forward)
       If sigma <= 0: returns discounted intrinsic payoff.
       Otherwise:
         Call = exp(-r * tau) * [F * N(d1) - K * N(d2)]
         Put  = exp(-r * tau) * [K * N(-d2) - F * N(-d1)]

    3. Concepts used in the function:
       Black-76 model for European futures / index options, discounted expected payoffs.

    4. Places where this function is imported and used:
       Used by Greeks solver, synthetic straddle inverter, and unit tests.

    5. Final output of the function, before and after:
       Before: Parameters (F, K, tau, r, sigma, is_call). After: Theoretical option price float.
    """
    discount = math.exp(-r * max(0.0, tau))

    if tau <= 1e-7 or sigma <= 1e-7:
        if is_call:
            return discount * max(0.0, forward - strike)
        else:
            return discount * max(0.0, strike - forward)

    d1, d2 = _compute_d1_d2(forward, strike, tau, sigma)

    if is_call:
        price = discount * (forward * norm_cdf(d1) - strike * norm_cdf(d2))
    else:
        price = discount * (strike * norm_cdf(-d2) - forward * norm_cdf(-d1))

    return max(0.0, price)


def black76_delta(
    forward: float,
    strike: float,
    tau: float,
    r: float,
    sigma: float,
    is_call: bool,
) -> float:
    """
    1. The use of function:
       Computes option Delta sensitivity (dPrice / dForward).

    2. How does the specific function work:
       If tau <= 0:
         Call: 1.0 if forward > strike else 0.0
         Put: -1.0 if forward < strike else 0.0
       Otherwise:
         Call Delta = exp(-r * tau) * N(d1)
         Put Delta  = -exp(-r * tau) * N(-d1) = Call Delta - exp(-r * tau)

    3. Concepts used in the function:
       First-order directional sensitivity with respect to underlying forward.

    4. Places where this function is imported and used:
       Used by liquid ATM band Greeks evaluator, skew features, and delta binning.

    5. Final output of the function, before and after:
       Before: Option parameters. After: Delta float in [0, 1] for Call, [-1, 0] for Put.
    """
    discount = math.exp(-r * max(0.0, tau))

    if tau <= 1e-7 or sigma <= 1e-7:
        if is_call:
            return discount if forward > strike else 0.0
        else:
            return -discount if forward < strike else 0.0

    d1, _ = _compute_d1_d2(forward, strike, tau, sigma)

    if is_call:
        return discount * norm_cdf(d1)
    else:
        return -discount * norm_cdf(-d1)


def black76_gamma(
    forward: float,
    strike: float,
    tau: float,
    r: float,
    sigma: float,
) -> float:
    """
    1. The use of function:
       Computes option Gamma sensitivity (d^2Price / dForward^2).

    2. How does the specific function work:
       Gamma = exp(-r * tau) * N'(d1) / (forward * sigma * sqrt(tau))
       Gamma is identical for both Call and Put under Put-Call parity.
       If tau <= 0 or sigma <= 0, returns 0.0.

    3. Concepts used in the function:
       Second-order curvature sensitivity per index point (1/INR).

    4. Places where this function is imported and used:
       Used by liquid ATM band Greeks evaluator.

    5. Final output of the function, before and after:
       Before: Option parameters. After: Gamma float.
    """
    if tau <= 1e-7 or sigma <= 1e-7 or forward <= 0.0:
        return 0.0

    discount = math.exp(-r * tau)
    d1, _ = _compute_d1_d2(forward, strike, tau, sigma)
    denominator = forward * sigma * math.sqrt(tau)
    if denominator <= 0.0:
        return 0.0
    return (discount * norm_pdf(d1)) / denominator


def black76_vega(
    forward: float,
    strike: float,
    tau: float,
    r: float,
    sigma: float,
) -> float:
    """
    1. The use of function:
       Computes option Vega sensitivity per 1 percentage point change in IV.

    2. How does the specific function work:
       Continuous Vega = forward * exp(-r * tau) * N'(d1) * sqrt(tau)
       Scaled Vega = 0.01 * Continuous Vega (INR / 1% IV change).
       Vega is identical for Call and Put. If tau <= 0, returns 0.0.

    3. Concepts used in the function:
       First-order volatility sensitivity scaled to market-standard 1% IV shift.

    4. Places where this function is imported and used:
       Used by liquid ATM band Greeks evaluator.

    5. Final output of the function, before and after:
       Before: Option parameters. After: Vega float (INR / 1% IV).
    """
    if tau <= 1e-7 or sigma <= 1e-7:
        return 0.0

    discount = math.exp(-r * tau)
    d1, _ = _compute_d1_d2(forward, strike, tau, sigma)
    continuous_vega = forward * discount * norm_pdf(d1) * math.sqrt(tau)
    return 0.01 * continuous_vega


def black76_theta(
    forward: float,
    strike: float,
    tau: float,
    r: float,
    sigma: float,
    is_call: bool,
) -> float:
    """
    1. The use of function:
       Computes option Theta time decay per 1 calendar day (1/365 year).

    2. How does the specific function work:
       Computes continuous time derivative dPrice/dt and divides by 365:
       Call Theta = (1/365) * [ -(F * exp(-r*tau) * N'(d1) * sigma) / (2 * sqrt(tau))
                                - r * K * exp(-r*tau) * N(d2)
                                + r * F * exp(-r*tau) * N(d1) ]
       Put Theta  = (1/365) * [ -(F * exp(-r*tau) * N'(d1) * sigma) / (2 * sqrt(tau))
                                + r * K * exp(-r*tau) * N(-d2)
                                - r * F * exp(-r*tau) * N(-d1) ]

    3. Concepts used in the function:
       Analytical time decay per calendar day.

    4. Places where this function is imported and used:
       Used by liquid ATM band Greeks evaluator.

    5. Final output of the function, before and after:
       Before: Option parameters. After: Theta float (INR / calendar day).
    """
    if tau <= 1e-7 or sigma <= 1e-7:
        return 0.0

    discount = math.exp(-r * tau)
    d1, d2 = _compute_d1_d2(forward, strike, tau, sigma)
    sqrt_tau = math.sqrt(tau)

    term1 = -(forward * discount * norm_pdf(d1) * sigma) / (2.0 * sqrt_tau)

    if is_call:
        term2 = -r * strike * discount * norm_cdf(d2)
        term3 = r * forward * discount * norm_cdf(d1)
        theta_annual = term1 + term2 + term3
    else:
        term2 = r * strike * discount * norm_cdf(-d2)
        term3 = -r * forward * discount * norm_cdf(-d1)
        theta_annual = term1 + term2 + term3

    return theta_annual / 365.0
