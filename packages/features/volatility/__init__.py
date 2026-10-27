"""
1. What this file does:
   Package exports for QuantView volatility and model Greeks features (Black-76, ATM band solver, Skew).

2. Overall design:
   Re-exports closed-form Black-76 pricer, Greeks sensitivities, bounded IV solver,
   and 25-delta Risk Reversal / Butterfly smile calculators.

3. Elements in the file:
   - black76_price, black76_delta, black76_gamma, black76_vega, black76_theta.
   - solve_implied_volatility, ModelGreeksResult, compute_liquid_atm_band_greeks, register_liquid_atm_greeks_feature.
   - SkewResult, compute_iv_skew_and_fly, register_skew_feature.

4. Final output of the file:
   - Clean public API for packages.features.volatility.
"""

from packages.features.volatility.black76 import (
    black76_delta,
    black76_gamma,
    black76_price,
    black76_theta,
    black76_vega,
    norm_cdf,
    norm_pdf,
)
from packages.features.volatility.greeks_solver import (
    ModelGreeksResult,
    compute_liquid_atm_band_greeks,
    register_liquid_atm_greeks_feature,
    solve_implied_volatility,
)
from packages.features.volatility.skew import (
    SkewResult,
    compute_iv_skew_and_fly,
    register_skew_feature,
)

__all__ = [
    "norm_cdf",
    "norm_pdf",
    "black76_price",
    "black76_delta",
    "black76_gamma",
    "black76_vega",
    "black76_theta",
    "solve_implied_volatility",
    "ModelGreeksResult",
    "compute_liquid_atm_band_greeks",
    "register_liquid_atm_greeks_feature",
    "SkewResult",
    "compute_iv_skew_and_fly",
    "register_skew_feature",
]
