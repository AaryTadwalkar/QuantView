"""
1. What this file does:
   Comprehensive unit tests for QuantView Lazy Reconstructed Option Chain provider
   and DuckDB view queries (DATA §4.4, §4.8, MASTER §2, Task M5-04 / Gate G3).

2. Overall design:
   Validates as-of point-in-time filtering (strictly zero future rows), missing strike
   identification against expected universe, ATM strike and liquid band extraction,
   and execution of canonical DuckDB lazy view DDL.

3. Elements in the file:
   - TestLazyChainPointInTime: Tests temporal boundaries and future row rejection.
   - TestMissingStrikeUniverse: Tests fail-closed missing contract flags.
   - TestAtmBandExtraction: Tests ATM strike rounding and 2N+1 band extraction.
   - TestDuckDbViewIntegration: Tests DuckDB SQL query execution against reconstructed view.

4. Final output of the file:
   - Automated pytest suite certifying Task M5-04 under @pytest.mark.gate_g3.
"""

from datetime import date
import duckdb
import pytest

from packages.features.chain import (
    SQL_CREATE_VIEW_RECONSTRUCTED_CHAIN,
    ChainRow,
    LazyChainProvider,
    ReconstructedOptionChain,
    get_atm_band_strikes,
    get_atm_strike,
)


@pytest.mark.gate_g3
class TestLazyChainPointInTime:
    """
    1. The use of class:
       Validates strict point-in-time causality for reconstructed chains.

    2. What the class contains:
       - test_no_future_rows: Ensures records with available_at > as_of_minute are excluded.
       - test_as_of_valid_inclusion: Confirms records with available_at <= as_of_minute are included.

    3. Technologies used and why:
       pytest assertions on in-memory chain provider records.

    4. Key design and overall design of the class:
       Guarantees zero look-ahead bias in options data pipelines.
    """

    def test_no_future_rows(self):
        provider = LazyChainProvider()
        test_expiry = date(2025, 1, 9)

        # Record at 09:16:00 (avail_at = 1000)
        rec_past = {
            "symbol": "NIFTY",
            "expiry": test_expiry,
            "strike": 22500.0,
            "option_type": "CE",
            "contract_id": "OPT-NIFTY-20250109-22500-CE",
            "available_at": 1000,
            "close": 125.0,
            "volume": 500,
            "oi": 10000,
        }
        # Future record at 09:17:00 (avail_at = 1060)
        rec_future = {
            "symbol": "NIFTY",
            "expiry": test_expiry,
            "strike": 22500.0,
            "option_type": "PE",
            "contract_id": "OPT-NIFTY-20250109-22500-PE",
            "available_at": 1060,
            "close": 95.0,
            "volume": 300,
            "oi": 8000,
        }

        provider.set_in_memory_records([rec_past, rec_future])

        # Query at as_of_minute = 1000: future PE must NOT be returned!
        chain = provider.get_reconstructed_chain(
            symbol="NIFTY",
            expiry=test_expiry,
            as_of_minute=1000,
            spot_price=22510.0,
        )

        assert chain.get_contract(22500.0, "CE") is not None
        assert chain.get_contract(22500.0, "PE") is None


@pytest.mark.gate_g3
class TestMissingStrikeUniverse:
    """
    1. The use of class:
       Validates explicit reporting of absent strikes in expected universe.

    2. What the class contains:
       - test_missing_strike_flagging: Asserts MISSING_STRIKE flag on unobserved strikes.

    3. Technologies used and why:
       pytest assertions verifying DATA §4.8 missing-contract contracts.

    4. Key design and overall design of the class:
       Prevents silent strike substitution or forward-filling.
    """

    def test_missing_strike_flagging(self):
        provider = LazyChainProvider()
        test_expiry = date(2025, 1, 9)

        # Feed provides only 22500 CE
        provider.set_in_memory_records([
            {
                "symbol": "NIFTY",
                "expiry": test_expiry,
                "strike": 22500.0,
                "option_type": "CE",
                "contract_id": "OPT-NIFTY-20250109-22500-CE",
                "available_at": 1000,
                "close": 120.0,
                "volume": 100,
                "oi": 5000,
            }
        ])

        # Expected universe includes 22500 and 22550
        chain = provider.get_reconstructed_chain(
            symbol="NIFTY",
            expiry=test_expiry,
            as_of_minute=1000,
            spot_price=22500.0,
            expected_strikes=[22500.0, 22550.0],
        )

        ce_22500 = chain.get_contract(22500.0, "CE")
        assert ce_22500 is not None
        assert ce_22500.is_available is True
        assert ce_22500.option_close == 120.0

        # 22500 PE was not in feed -> missing
        pe_22500 = chain.get_contract(22500.0, "PE")
        assert pe_22500 is not None
        assert pe_22500.is_available is False
        assert "MISSING_STRIKE" in pe_22500.quality_flags

        # 22550 CE was not in feed -> missing
        ce_22550 = chain.get_contract(22550.0, "CE")
        assert ce_22550 is not None
        assert ce_22550.is_available is False
        assert "MISSING_STRIKE" in ce_22550.quality_flags


@pytest.mark.gate_g3
class TestAtmBandExtraction:
    """Validates ATM strike rounding and liquid ATM +/- N strike band extraction."""

    def test_atm_strike_rounding(self):
        assert get_atm_strike(22512.0, 50.0) == 22500.0
        assert get_atm_strike(22530.0, 50.0) == 22550.0
        assert get_atm_strike(22525.0, 50.0) == 22500.0  # Tie breaks to lower strike
        assert get_atm_strike(22526.0, 50.0) == 22550.0

    def test_atm_band_strikes(self):
        strikes = get_atm_band_strikes(22500.0, n_strikes=2, strike_step=50.0)
        assert strikes == [22400.0, 22450.0, 22500.0, 22550.0, 22600.0]
        assert len(strikes) == 5

    def test_atm_band_extraction_pairs(self):
        test_expiry = date(2025, 1, 9)
        rows = [
            ChainRow(
                contract_id=f"OPT-NIFTY-20250109-{int(k)}-CE",
                symbol="NIFTY",
                expiry=test_expiry,
                strike=k,
                option_type="CE",
                as_of_minute=1000,
                available_at=1000,
                option_open=100.0,
                option_high=105.0,
                option_low=95.0,
                option_close=100.0,
                volume=10,
                oi=100,
                is_flat_bar=False,
                is_available=True,
                quality_flags=["VALID"],
            )
            for k in [22450.0, 22500.0, 22550.0]
        ]
        chain = ReconstructedOptionChain(
            symbol="NIFTY",
            expiry=test_expiry,
            as_of_minute=1000,
            spot_price=22500.0,
            rows=rows,
        )

        band = chain.get_atm_band(n_strikes=1, strike_step=50.0)
        assert len(band) == 3  # 22450, 22500, 22550
        assert band[1][0] is not None
        assert band[1][0].strike == 22500.0
        assert band[1][0].option_type == "CE"
        assert band[1][1] is None  # PE was not provided


@pytest.mark.gate_g3
class TestDuckDbViewIntegration:
    """Verifies that SQL_CREATE_VIEW_RECONSTRUCTED_CHAIN executes and queries cleanly in DuckDB."""

    def test_duckdb_view_execution(self):
        con = duckdb.connect(":memory:")
        # Create mock v_candles_options table
        con.execute("""
            CREATE TABLE v_candles_options (
                bar_end BIGINT,
                available_at BIGINT,
                contract_id VARCHAR,
                symbol VARCHAR,
                expiry DATE,
                strike DOUBLE,
                option_type VARCHAR,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                oi BIGINT,
                is_flat_bar BOOLEAN,
                quality_flags VARCHAR[],
                source_manifest_hash VARCHAR,
                is_active BOOLEAN
            );
        """)

        # Insert 1 test row
        con.execute("""
            INSERT INTO v_candles_options VALUES (
                1000, 1000, 'OPT-NIFTY-20250109-22500-CE', 'NIFTY',
                DATE '2025-01-09', 22500.0, 'CE',
                110.0, 115.0, 105.0, 112.0, 500, 10000, false,
                ['VALID'], 'sha256_mock_hash', true
            );
        """)

        # Create lazy view
        con.execute(SQL_CREATE_VIEW_RECONSTRUCTED_CHAIN)

        # Query through LazyChainProvider
        provider = LazyChainProvider(duckdb_connection=con)
        chain = provider.get_reconstructed_chain(
            symbol="NIFTY",
            expiry=date(2025, 1, 9),
            as_of_minute=1000,
            spot_price=22500.0,
        )

        ce_contract = chain.get_contract(22500.0, "CE")
        assert ce_contract is not None
        assert ce_contract.strike == 22500.0
        assert ce_contract.option_close == 112.0
        assert ce_contract.volume == 500
