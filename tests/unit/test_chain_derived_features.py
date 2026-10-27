"""
1. What this file does:
   Comprehensive unit tests for QuantView Option-Chain Derived Features:
   PCR by OI/Volume, OI Rate of Change, ATM Straddle premium & synthetic IV,
   and Delta-band aggregate OI distribution (ENGINE §21.1, DATA §4.4, Task M5-12 / Gate G3).

2. Overall design:
   Validates point-in-time calculation of market positioning sentiment metrics,
   zero-division guards, Brenner-Subrahmanyam synthetic IV approximation,
   and Delta bucket aggregation.

3. Elements in the file:
   - TestPutCallRatio: Tests total/near-ATM PCR and zero-denominator guard.
   - TestOpenInterestRoc: Tests percentage and absolute OI rate of change.
   - TestAtmStraddleMetrics: Tests ATM straddle premium and synthetic IV.
   - TestDeltaBandOi: Tests Delta-weighted bucket aggregation.

4. Final output of the file:
   - Automated pytest suite certifying Task M5-12 under @pytest.mark.gate_g3.
"""

from datetime import date
import pytest

from packages.features.chain import (
    ChainRow,
    ReconstructedOptionChain,
    compute_atm_straddle,
    compute_delta_band_oi,
    compute_oi_roc,
    compute_pcr,
)
from packages.features.volatility import ModelGreeksResult


@pytest.mark.gate_g3
class TestPutCallRatio:
    """
    1. The use of class:
       Unit tests for compute_pcr.

    2. What the class contains:
       - test_pcr_by_oi_and_volume: Verifies ratio calculations.
       - test_pcr_zero_division: Verifies fail-closed DIV_BY_ZERO handling.

    3. Technologies used and why:
       pytest assertions on PCR ratios.

    4. Key design and overall design of the class:
       Guarantees sentiment indicators never crash on empty call books.
    """

    def test_pcr_by_oi_and_volume(self):
        test_expiry = date(2025, 1, 9)
        rows = [
            ChainRow(
                contract_id="CE-1",
                symbol="NIFTY",
                expiry=test_expiry,
                strike=22500.0,
                option_type="CE",
                as_of_minute=1000,
                available_at=1000,
                option_open=100.0,
                option_high=100.0,
                option_low=100.0,
                option_close=100.0,
                volume=1000,
                oi=20000,
                is_flat_bar=False,
                is_available=True,
                quality_flags=["VALID"],
            ),
            ChainRow(
                contract_id="PE-1",
                symbol="NIFTY",
                expiry=test_expiry,
                strike=22500.0,
                option_type="PE",
                as_of_minute=1000,
                available_at=1000,
                option_open=100.0,
                option_high=100.0,
                option_low=100.0,
                option_close=100.0,
                volume=1500,
                oi=30000,
                is_flat_bar=False,
                is_available=True,
                quality_flags=["VALID"],
            ),
        ]
        chain = ReconstructedOptionChain(
            symbol="NIFTY",
            expiry=test_expiry,
            as_of_minute=1000,
            spot_price=22500.0,
            rows=rows,
        )

        pcr_oi, flags_oi = compute_pcr(chain, mode="OI")
        # 30,000 / 20,000 = 1.5000
        assert pcr_oi == 1.5
        assert flags_oi == ["VALID"]

        pcr_vol, flags_vol = compute_pcr(chain, mode="VOLUME")
        # 1,500 / 1,000 = 1.5000
        assert pcr_vol == 1.5
        assert flags_vol == ["VALID"]

    def test_pcr_zero_division(self):
        test_expiry = date(2025, 1, 9)
        rows = [
            ChainRow(
                contract_id="PE-1",
                symbol="NIFTY",
                expiry=test_expiry,
                strike=22500.0,
                option_type="PE",
                as_of_minute=1000,
                available_at=1000,
                option_open=100.0,
                option_high=100.0,
                option_low=100.0,
                option_close=100.0,
                volume=500,
                oi=10000,
                is_flat_bar=False,
                is_available=True,
                quality_flags=["VALID"],
            )
        ]
        chain = ReconstructedOptionChain(
            symbol="NIFTY",
            expiry=test_expiry,
            as_of_minute=1000,
            spot_price=22500.0,
            rows=rows,
        )

        pcr, flags = compute_pcr(chain, mode="OI")
        assert pcr is None
        assert flags == ["DIV_BY_ZERO"]


@pytest.mark.gate_g3
class TestOpenInterestRoc:
    """Validates percentage and absolute open interest rate of change calculations."""

    def test_oi_roc_calculations(self):
        # 10% increase
        assert compute_oi_roc(current_oi=11000, previous_oi=10000) == 0.1000

        # 20% decrease
        assert compute_oi_roc(current_oi=8000, previous_oi=10000) == -0.2000

        # Absolute change
        assert compute_oi_roc(current_oi=12500, previous_oi=10000, percentage=False) == 2500.0

        # Zero previous OI
        assert compute_oi_roc(current_oi=0, previous_oi=0) == 0.0
        assert compute_oi_roc(current_oi=5000, previous_oi=0) is None


@pytest.mark.gate_g3
class TestAtmStraddleMetrics:
    """Validates ATM Straddle premium extraction and synthetic IV calculation."""

    def test_straddle_premium_and_synthetic_iv(self):
        test_expiry = date(2025, 1, 9)
        f = 22500.0
        rows = [
            ChainRow(
                contract_id="ATM-CE",
                symbol="NIFTY",
                expiry=test_expiry,
                strike=22500.0,
                option_type="CE",
                as_of_minute=1000,
                available_at=1000,
                option_open=140.0,
                option_high=140.0,
                option_low=140.0,
                option_close=140.0,
                volume=100,
                oi=5000,
                is_flat_bar=False,
                is_available=True,
                quality_flags=["VALID"],
            ),
            ChainRow(
                contract_id="ATM-PE",
                symbol="NIFTY",
                expiry=test_expiry,
                strike=22500.0,
                option_type="PE",
                as_of_minute=1000,
                available_at=1000,
                option_open=110.0,
                option_high=110.0,
                option_low=110.0,
                option_close=110.0,
                volume=100,
                oi=5000,
                is_flat_bar=False,
                is_available=True,
                quality_flags=["VALID"],
            ),
        ]
        chain = ReconstructedOptionChain(
            symbol="NIFTY",
            expiry=test_expiry,
            as_of_minute=1000,
            spot_price=f,
            rows=rows,
        )

        tau = 7.0 / 365.0
        res = compute_atm_straddle(chain, tau=tau)

        assert res.is_valid is True
        assert res.atm_strike == 22500.0
        assert res.call_price == 140.0
        assert res.put_price == 110.0
        # Premium = 140 + 110 = 250.0
        assert res.straddle_premium == 250.0
        assert res.synthetic_iv is not None
        assert 0.05 < res.synthetic_iv < 0.30


@pytest.mark.gate_g3
class TestDeltaBandOi:
    """Validates aggregation of open interest into Delta buckets."""

    def test_delta_band_binning(self):
        test_expiry = date(2025, 1, 9)
        rows = [
            ChainRow(
                contract_id="C-ATM",
                symbol="NIFTY",
                expiry=test_expiry,
                strike=22500.0,
                option_type="CE",
                as_of_minute=1000,
                available_at=1000,
                option_open=100.0,
                option_high=100.0,
                option_low=100.0,
                option_close=100.0,
                volume=10,
                oi=10000,
                is_flat_bar=False,
                is_available=True,
                quality_flags=["VALID"],
            ),
            ChainRow(
                contract_id="C-OTM",
                symbol="NIFTY",
                expiry=test_expiry,
                strike=22700.0,
                option_type="CE",
                as_of_minute=1000,
                available_at=1000,
                option_open=30.0,
                option_high=30.0,
                option_low=30.0,
                option_close=30.0,
                volume=10,
                oi=25000,
                is_flat_bar=False,
                is_available=True,
                quality_flags=["VALID"],
            ),
            ChainRow(
                contract_id="P-DOTM",
                symbol="NIFTY",
                expiry=test_expiry,
                strike=21800.0,
                option_type="PE",
                as_of_minute=1000,
                available_at=1000,
                option_open=5.0,
                option_high=5.0,
                option_low=5.0,
                option_close=5.0,
                volume=10,
                oi=50000,
                is_flat_bar=False,
                is_available=True,
                quality_flags=["VALID"],
            ),
        ]
        chain = ReconstructedOptionChain(
            symbol="NIFTY",
            expiry=test_expiry,
            as_of_minute=1000,
            spot_price=22500.0,
            rows=rows,
        )

        greeks = [
            ModelGreeksResult(
                contract_id="C-ATM",
                strike=22500.0,
                option_type="CE",
                model_iv=0.15,
                model_delta=0.52,  # ATM bucket [0.35, 0.65)
                model_gamma=0.001,
                model_vega=5.0,
                model_theta=-10.0,
                solver_status="CONVERGED",
                quality_flags=["VALID"],
            ),
            ModelGreeksResult(
                contract_id="C-OTM",
                strike=22700.0,
                option_type="CE",
                model_iv=0.15,
                model_delta=0.22,  # OTM bucket [0.15, 0.35)
                model_gamma=0.0008,
                model_vega=3.0,
                model_theta=-6.0,
                solver_status="CONVERGED",
                quality_flags=["VALID"],
            ),
            ModelGreeksResult(
                contract_id="P-DOTM",
                strike=21800.0,
                option_type="PE",
                model_iv=0.20,
                model_delta=-0.08,  # Deep OTM bucket < 0.15
                model_gamma=0.0002,
                model_vega=1.0,
                model_theta=-2.0,
                solver_status="CONVERGED",
                quality_flags=["VALID"],
            ),
        ]

        buckets = compute_delta_band_oi(chain, greeks)

        assert buckets["ATM"] == 10000
        assert buckets["OTM"] == 25000
        assert buckets["DEEP_OTM"] == 50000
        assert buckets["ITM"] == 0
        assert buckets["UNASSIGNED"] == 0
