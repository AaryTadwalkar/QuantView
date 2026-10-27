"""
1. What this file does:
   Comprehensive unit tests for QuantView Black-76 European index option pricer,
   analytical Greeks sensitivities, bounded IV solver, and liquid ATM band evaluation
   (ENGINE §13, §21, DATA §4.7, Task M5-05 / Gate G3).

2. Overall design:
   Validates mathematical Put-Call Parity, boundary behavior at expiration (tau -> 0),
   solver precision and recovery of known IV, fail-closed rejection of arbitrage violations,
   and strict 'model_' field prefix enforcement across the liquid ATM +/- 5 strike band.

3. Elements in the file:
   - TestBlack76Pricing: Validates Black-76 analytical formulas and Put-Call parity.
   - TestImpliedVolatilitySolver: Validates bounded Brent solver precision and arbitrage guards.
   - TestLiquidAtmBandGreeks: Validates ATM +/- 5 band evaluation and 'model_' prefix enforcement.
   - TestVolatilitySkewAndFly: Validates 25-delta Risk Reversal and Butterfly smile extraction.

4. Final output of the file:
   - Automated pytest suite certifying Task M5-05 under @pytest.mark.gate_g3.
"""

import math
from datetime import date

import pytest

from packages.features.chain import (
    ChainRow,
    ReconstructedOptionChain,
)
from packages.features.volatility import (
    ModelGreeksResult,
    SkewResult,
    black76_delta,
    black76_gamma,
    black76_price,
    black76_theta,
    black76_vega,
    compute_iv_skew_and_fly,
    compute_liquid_atm_band_greeks,
    solve_implied_volatility,
)


@pytest.mark.gate_g3
class TestBlack76Pricing:
    """
    1. The use of class:
       Unit tests for Black-76 pricing and Greek sensitivity equations.

    2. What the class contains:
       - test_put_call_parity: Asserts Call - Put = exp(-r*tau)*(F - K).
       - test_boundary_at_expiration: Asserts exact intrinsic payoff when tau <= 0.
       - test_greeks_signs_and_bounds: Asserts Delta in bounds, Gamma > 0, Vega > 0.

    3. Technologies used and why:
       pytest assertions verifying closed-form financial equations.

    4. Key design and overall design of the class:
       Guarantees analytical pricer soundness.
    """

    def test_put_call_parity(self):
        f = 22500.0
        k = 22500.0
        tau = 7.0 / 365.0
        r = 0.065
        sigma = 0.16

        call = black76_price(f, k, tau, r, sigma, is_call=True)
        put = black76_price(f, k, tau, r, sigma, is_call=False)
        discount = math.exp(-r * tau)
        parity_diff = abs((call - put) - discount * (f - k))

        assert parity_diff < 1e-10

        # In-the-money Call test (K = 22400)
        k_itm = 22400.0
        c_itm = black76_price(f, k_itm, tau, r, sigma, is_call=True)
        p_otm = black76_price(f, k_itm, tau, r, sigma, is_call=False)
        assert abs((c_itm - p_otm) - discount * (f - k_itm)) < 1e-10

    def test_boundary_at_expiration(self):
        f = 22550.0
        k = 22500.0
        tau = 0.0
        r = 0.065
        sigma = 0.15

        # Call intrinsic = 50.0, Put intrinsic = 0.0
        c_payoff = black76_price(f, k, tau, r, sigma, is_call=True)
        p_payoff = black76_price(f, k, tau, r, sigma, is_call=False)
        assert c_payoff == 50.0
        assert p_payoff == 0.0

        # Delta at expiration
        assert black76_delta(f, k, tau, r, sigma, is_call=True) == 1.0
        assert black76_delta(f, k, tau, r, sigma, is_call=False) == 0.0

    def test_greeks_signs_and_bounds(self):
        f = 22500.0
        k = 22500.0
        tau = 14.0 / 365.0
        r = 0.065
        sigma = 0.18

        delta_c = black76_delta(f, k, tau, r, sigma, is_call=True)
        delta_p = black76_delta(f, k, tau, r, sigma, is_call=False)
        gamma = black76_gamma(f, k, tau, r, sigma)
        vega = black76_vega(f, k, tau, r, sigma)
        theta_c = black76_theta(f, k, tau, r, sigma, is_call=True)

        assert 0.0 < delta_c < 1.0
        assert -1.0 < delta_p < 0.0
        assert gamma > 0.0
        assert vega > 0.0
        assert theta_c < 0.0  # Option decay is negative


@pytest.mark.gate_g3
class TestImpliedVolatilitySolver:
    """
    1. The use of class:
       Unit tests for bounded Brent implied volatility solver.

    2. What the class contains:
       - test_known_iv_recovery: Asserts solver recovers exact original sigma.
       - test_arbitrage_bound_violation: Asserts rejection when price <= lower bound.

    3. Technologies used and why:
       pytest assertions on numerical inversion convergence.

    4. Key design and overall design of the class:
       Guarantees robust fail-closed solver behavior.
    """

    def test_known_iv_recovery(self):
        f = 22500.0
        k = 22500.0
        tau = 10.0 / 365.0
        r = 0.065
        target_sigma = 0.155

        # Compute theoretical Call price
        market_price = black76_price(f, k, tau, r, target_sigma, is_call=True)

        # Invert via solver
        solved_iv, status = solve_implied_volatility(
            price=market_price,
            forward=f,
            strike=k,
            tau=tau,
            r=r,
            is_call=True,
        )

        assert status == "CONVERGED"
        assert solved_iv is not None
        assert abs(solved_iv - target_sigma) < 1e-4

    def test_arbitrage_bound_violation(self):
        f = 22500.0
        k = 22400.0
        tau = 10.0 / 365.0
        r = 0.065
        discount = math.exp(-r * tau)
        intrinsic_lower = discount * (f - k)  # ~ 99.82

        # Price violating lower bound (50.0 < 99.82)
        iv, status = solve_implied_volatility(
            price=50.0,
            forward=f,
            strike=k,
            tau=tau,
            r=r,
            is_call=True,
        )
        assert status == "ARBITRAGE_BOUND_VIOLATION"
        assert iv is None

        # Price violating upper bound (23000 > f)
        iv_up, status_up = solve_implied_volatility(
            price=23000.0,
            forward=f,
            strike=k,
            tau=tau,
            r=r,
            is_call=True,
        )
        assert status_up == "ARBITRAGE_BOUND_VIOLATION"
        assert iv_up is None


@pytest.mark.gate_g3
class TestLiquidAtmBandGreeks:
    """
    1. The use of class:
       Validates liquid ATM +/- N strike band Greeks evaluation.

    2. What the class contains:
       - test_atm_band_coverage_and_model_prefix: Asserts 11 strikes and 'model_' field naming.

    3. Technologies used and why:
       pytest assertions on ModelGreeksResult list.

    4. Key design and overall design of the class:
       Enforces DATA §4.7 model/observed field segregation.
    """

    def test_atm_band_coverage_and_model_prefix(self):
        test_expiry = date(2025, 1, 9)
        f = 22500.0
        tau = 7.0 / 365.0
        r = 0.065
        sigma = 0.16

        # Build mock chain for ATM +/- 5 strikes (22250 to 22750 in steps of 50)
        rows = []
        for offset in range(-5, 6):
            k = 22500.0 + (offset * 50.0)
            c_price = black76_price(f, k, tau, r, sigma, is_call=True)
            p_price = black76_price(f, k, tau, r, sigma, is_call=False)

            rows.append(
                ChainRow(
                    contract_id=f"OPT-NIFTY-20250109-{int(k)}-CE",
                    symbol="NIFTY",
                    expiry=test_expiry,
                    strike=k,
                    option_type="CE",
                    as_of_minute=1000,
                    available_at=1000,
                    option_open=c_price,
                    option_high=c_price,
                    option_low=c_price,
                    option_close=c_price,
                    volume=100,
                    oi=5000,
                    is_flat_bar=False,
                    is_available=True,
                    quality_flags=["VALID"],
                )
            )
            rows.append(
                ChainRow(
                    contract_id=f"OPT-NIFTY-20250109-{int(k)}-PE",
                    symbol="NIFTY",
                    expiry=test_expiry,
                    strike=k,
                    option_type="PE",
                    as_of_minute=1000,
                    available_at=1000,
                    option_open=p_price,
                    option_high=p_price,
                    option_low=p_price,
                    option_close=p_price,
                    volume=100,
                    oi=5000,
                    is_flat_bar=False,
                    is_available=True,
                    quality_flags=["VALID"],
                )
            )

        chain = ReconstructedOptionChain(
            symbol="NIFTY",
            expiry=test_expiry,
            as_of_minute=1000,
            spot_price=f,
            rows=rows,
        )

        results = compute_liquid_atm_band_greeks(chain, forward=f, tau=tau, r=r, n_strikes=5)

        # 11 strikes * 2 (CE/PE) = 22 contracts
        assert len(results) == 22

        for res in results:
            # DATA §4.7 rule: All calculated fields must be 'model_*'
            assert hasattr(res, "model_iv")
            assert hasattr(res, "model_delta")
            assert hasattr(res, "model_gamma")
            assert hasattr(res, "model_vega")
            assert hasattr(res, "model_theta")

            assert res.solver_status == "CONVERGED"
            assert res.model_iv is not None
            assert abs(res.model_iv - sigma) < 1e-4
            assert res.model_delta is not None
            assert res.model_gamma is not None


@pytest.mark.gate_g3
class TestVolatilitySkewAndFly:
    """Validates 25-delta Risk Reversal and Butterfly smile calculations."""

    def test_25_delta_skew_and_fly_evaluation(self):
        # Create mock Greeks results where Call 25d has IV=0.15 and Put 25d has IV=0.17
        results = [
            ModelGreeksResult(
                contract_id="ATM-CE",
                strike=22500.0,
                option_type="CE",
                model_iv=0.16,
                model_delta=0.50,
                model_gamma=0.001,
                model_vega=5.0,
                model_theta=-10.0,
                solver_status="CONVERGED",
                quality_flags=["VALID"],
            ),
            ModelGreeksResult(
                contract_id="ATM-PE",
                strike=22500.0,
                option_type="PE",
                model_iv=0.16,
                model_delta=-0.50,
                model_gamma=0.001,
                model_vega=5.0,
                model_theta=-10.0,
                solver_status="CONVERGED",
                quality_flags=["VALID"],
            ),
            ModelGreeksResult(
                contract_id="25D-CE",
                strike=22700.0,
                option_type="CE",
                model_iv=0.15,
                model_delta=0.25,
                model_gamma=0.0008,
                model_vega=4.0,
                model_theta=-8.0,
                solver_status="CONVERGED",
                quality_flags=["VALID"],
            ),
            ModelGreeksResult(
                contract_id="25D-PE",
                strike=22300.0,
                option_type="PE",
                model_iv=0.17,
                model_delta=-0.25,
                model_gamma=0.0008,
                model_vega=4.0,
                model_theta=-8.0,
                solver_status="CONVERGED",
                quality_flags=["VALID"],
            ),
        ]

        skew_res = compute_iv_skew_and_fly(results, atm_strike=22500.0)

        assert skew_res.is_valid is True
        assert skew_res.atm_iv == 0.16
        # Skew = Put IV (0.17) - Call IV (0.15) = +0.02 (Put skew premium)
        assert abs(skew_res.iv_skew_25d - 0.02) < 1e-5
        # Fly = (0.15 + 0.17)/2 - 0.16 = 0.16 - 0.16 = 0.0
        assert abs(skew_res.iv_fly_25d - 0.0) < 1e-5
