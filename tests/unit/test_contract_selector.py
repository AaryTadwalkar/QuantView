"""
1. What this file does:
   Comprehensive unit and integration test suite for the Point-in-Time (PIT) Contract Selector (Milestone M4-04).

2. Overall design:
   Uses pytest to verify:
     - Strike selection across discrete and non-uniform strike sets (ATM, ITM_k, OTM_k, EXACT).
     - Deterministic tie-breaking on midpoint spot values.
     - OptionType-specific moneyness (Call vs Put ITM/OTM inversions).
     - Strict enforcement of zero silent strike substitution (out-of-bounds depths reject fail-closed).
     - Expiry resolution policies (CURRENT_WEEK, NEXT_WEEK, MONTHLY, EXACT).
     - Integration with data eligibility filters (rejects INELIGIBLE contracts without substitution).
     - Production DuckDbContractMaster integration against Data/lake/quantview.duckdb.

3. Elements in the file:
   - TestPointInTimeContractSelector: Unit tests with InMemoryContractMaster.
   - TestDuckDbContractMasterIntegration: Integration test with the real QuantView DuckDB data lake.

4. Final output of the file:
   - Automated pass/fail test execution for Milestone M4-04.
"""

from datetime import date
from pathlib import Path

import pytest

from packages.domain import ContractIdentifier, OptionType
from packages.engine.selector import (
    ContractSelectionResult,
    DuckDbContractMaster,
    ExpirySelectionPolicy,
    InMemoryContractMaster,
    PointInTimeContractSelector,
    StrikePolicySpec,
    StrikeSelectionPolicy,
)


@pytest.fixture
def sample_contract_master() -> InMemoryContractMaster:
    """
    1. The use of function:
       Pytest fixture creating an InMemoryContractMaster with representative NIFTY contracts.

    2. How does the specific function work:
       Populates contracts across two weekly expiries (2025-01-09, 2025-01-16) and a monthly expiry (2025-01-30)
       for CE and PE across strikes 23800, 23900, 23950, 24000, 24050, 24100, 24200.

    3. Concepts used in the function:
       Test fixture generation with non-uniform strike steps.

    4. Places where this function is imported and used:
       Injected into test methods of TestPointInTimeContractSelector.

    5. Final output of the function, before and after:
       Before: Empty fixture. After: Seeded InMemoryContractMaster.
    """
    master = InMemoryContractMaster()
    expiries = ["2025-01-09", "2025-01-16", "2025-01-30"]
    strikes = [23800.0, 23900.0, 23950.0, 24000.0, 24050.0, 24100.0, 24200.0]

    for exp in expiries:
        for s in strikes:
            # Add CE
            master.add_contract(
                ContractIdentifier(
                    instrument_key=f"NSE_FO|NIFTY_{exp}_{s:.0f}_CE",
                    trading_symbol=f"NIFTY {s:.0f} CE {exp}",
                    expiry_date=exp,
                    strike_price=s,
                    option_type=OptionType.CE,
                    lot_size=25,
                )
            )
            # Add PE
            master.add_contract(
                ContractIdentifier(
                    instrument_key=f"NSE_FO|NIFTY_{exp}_{s:.0f}_PE",
                    trading_symbol=f"NIFTY {s:.0f} PE {exp}",
                    expiry_date=exp,
                    strike_price=s,
                    option_type=OptionType.PE,
                    lot_size=25,
                )
            )
    return master


@pytest.mark.gate_g2a
class TestPointInTimeContractSelector:
    """
    1. The use of class:
       Unit tests for PointInTimeContractSelector validating strike and expiry resolution.

    2. What the class contains:
       - test_atm_selection_and_tie_breaking: Tests closest distance and lower-strike tie-break.
       - test_ce_moneyness_depths: Tests CE ATM, ITM_1, ITM_2, OTM_1, OTM_2.
       - test_pe_moneyness_depths: Tests PE ATM, ITM_1, ITM_2, OTM_1, OTM_2.
       - test_exact_strike_policy: Tests explicit strike matching and rejection on missing strike.
       - test_zero_silent_substitution_on_depth_overflow: Tests fail-closed rejection on excessive depth.
       - test_expiry_resolution_policies: Tests CURRENT_WEEK, NEXT_WEEK, and MONTHLY.
       - test_data_eligibility_rejection: Tests rejection when contract is flagged INELIGIBLE.

    3. Technologies used and why:
       pytest assertions on ContractSelectionResult.

    4. Key design and overall design of the class:
       Guarantees mathematical correctness of strike selection and adherence to zero silent substitution.
    """

    def test_atm_selection_and_tie_breaking(self, sample_contract_master: InMemoryContractMaster):
        """
        1. The use of function:
           Tests ATM strike selection and lower-strike tie-breaking rule.

        2. How does the specific function work:
           - Spot at 24010 -> closest strike is 24000.
           - Spot at 24040 -> closest strike is 24050.
           - Spot at 24025 (exact midpoint between 24000 and 24050) -> tie-breaks to lower strike 24000.

        3. Concepts used in the function:
           Deterministic ATM strike resolution.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unverified ATM resolution. After: Verified nearest and tie-break behavior.
        """
        selector = PointInTimeContractSelector(sample_contract_master)

        # 1. Spot closer to 24000
        res1 = selector.select_contract(
            trade_date="2025-01-05",
            spot_price=24010.0,
            option_type=OptionType.CE,
            strike_policy="ATM",
        )
        assert res1.is_eligible is True
        assert res1.selected_contract is not None
        assert res1.selected_contract.strike_price == 24000.0

        # 2. Spot closer to 24050
        res2 = selector.select_contract(
            trade_date="2025-01-05",
            spot_price=24040.0,
            option_type=OptionType.CE,
            strike_policy="ATM",
        )
        assert res2.selected_contract is not None
        assert res2.selected_contract.strike_price == 24050.0

        # 3. Exact midpoint tie-break: 24000 vs 24050 (midpoint = 24025)
        res_tie = selector.select_contract(
            trade_date="2025-01-05",
            spot_price=24025.0,
            option_type=OptionType.CE,
            strike_policy="ATM",
        )
        assert res_tie.selected_contract is not None
        assert res_tie.selected_contract.strike_price == 24000.0

    def test_ce_moneyness_depths(self, sample_contract_master: InMemoryContractMaster):
        """
        1. The use of function:
           Tests Call option ITM and OTM depth progression.

        2. How does the specific function work:
           With spot at 24000 (ATM = 24000):
           - ITM_1: strike below 24000 -> 23950.
           - ITM_2: next strike below -> 23900.
           - OTM_1: strike above 24000 -> 24050.
           - OTM_2: next strike above -> 24100.

        3. Concepts used in the function:
           Call option moneyness.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unverified CE moneyness. After: Verified strike alignment.
        """
        selector = PointInTimeContractSelector(sample_contract_master)
        trade_date = "2025-01-05"
        spot = 24000.0

        itm1 = selector.select_contract(trade_date, spot, OptionType.CE, "ITM_1").selected_contract
        itm2 = selector.select_contract(trade_date, spot, OptionType.CE, "ITM_2").selected_contract
        otm1 = selector.select_contract(trade_date, spot, OptionType.CE, "OTM_1").selected_contract
        otm2 = selector.select_contract(trade_date, spot, OptionType.CE, "OTM_2").selected_contract

        assert itm1 is not None and itm1.strike_price == 23950.0
        assert itm2 is not None and itm2.strike_price == 23900.0
        assert otm1 is not None and otm1.strike_price == 24050.0
        assert otm2 is not None and otm2.strike_price == 24100.0

    def test_pe_moneyness_depths(self, sample_contract_master: InMemoryContractMaster):
        """
        1. The use of function:
           Tests Put option ITM and OTM depth progression.

        2. How does the specific function work:
           With spot at 24000 (ATM = 24000):
           - ITM_1: for Put, ITM is strictly above spot -> 24050.
           - ITM_2: next strike above -> 24100.
           - OTM_1: for Put, OTM is strictly below spot -> 23950.
           - OTM_2: next strike below -> 23900.

        3. Concepts used in the function:
           Put option moneyness inversion.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unverified PE moneyness. After: Verified strike alignment.
        """
        selector = PointInTimeContractSelector(sample_contract_master)
        trade_date = "2025-01-05"
        spot = 24000.0

        itm1 = selector.select_contract(trade_date, spot, OptionType.PE, "ITM_1").selected_contract
        itm2 = selector.select_contract(trade_date, spot, OptionType.PE, "ITM_2").selected_contract
        otm1 = selector.select_contract(trade_date, spot, OptionType.PE, "OTM_1").selected_contract
        otm2 = selector.select_contract(trade_date, spot, OptionType.PE, "OTM_2").selected_contract

        assert itm1 is not None and itm1.strike_price == 24050.0
        assert itm2 is not None and itm2.strike_price == 24100.0
        assert otm1 is not None and otm1.strike_price == 23950.0
        assert otm2 is not None and otm2.strike_price == 23900.0

    def test_exact_strike_policy(self, sample_contract_master: InMemoryContractMaster):
        """
        1. The use of function:
           Validates EXACT strike matching and rejection if the strike is not available.

        2. How does the specific function work:
           Requests EXACT:23950 (available) -> succeeds.
           Requests EXACT:23975 (not in available strikes) -> returns NO_ELIGIBLE_CONTRACT.

        3. Concepts used in the function:
           Exact strike selection and fail-closed rejection.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unverified exact matching. After: Verified match and rejection.
        """
        selector = PointInTimeContractSelector(sample_contract_master)

        # 1. Existing strike
        res_ok = selector.select_contract(
            "2025-01-05", 24000.0, OptionType.CE, "EXACT:23950"
        )
        assert res_ok.selected_contract is not None
        assert res_ok.selected_contract.strike_price == 23950.0

        # 2. Non-existent strike
        res_fail = selector.select_contract(
            "2025-01-05", 24000.0, OptionType.CE, "EXACT:23975"
        )
        assert res_fail.selected_contract is None
        assert res_fail.rejection_reason == "NO_ELIGIBLE_CONTRACT"

    def test_zero_silent_substitution_on_depth_overflow(self, sample_contract_master: InMemoryContractMaster):
        """
        1. The use of function:
           Verifies that requesting a depth exceeding available strikes fails closed without substitution.

        2. How does the specific function work:
           Requests ITM_10 when only 3 ITM strikes exist.
           Asserts selected_contract is None and rejection_reason is NO_ELIGIBLE_CONTRACT.

        3. Concepts used in the function:
           Zero silent strike substitution invariant.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unchecked boundary. After: Confirmed rejection without fallback.
        """
        selector = PointInTimeContractSelector(sample_contract_master)
        res = selector.select_contract(
            trade_date="2025-01-05",
            spot_price=24000.0,
            option_type=OptionType.CE,
            strike_policy="ITM_10",
        )
        assert res.selected_contract is None
        assert res.rejection_reason == "NO_ELIGIBLE_CONTRACT"

    def test_expiry_resolution_policies(self, sample_contract_master: InMemoryContractMaster):
        """
        1. The use of function:
           Tests CURRENT_WEEK, NEXT_WEEK, and MONTHLY expiry selection.

        2. How does the specific function work:
           Evaluates trade date 2025-01-05 against expiries [2025-01-09, 2025-01-16, 2025-01-30].

        3. Concepts used in the function:
           Temporal expiry selection.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unverified expiry policy. After: Verified resolution for all 3 policies.
        """
        selector = PointInTimeContractSelector(sample_contract_master)

        # 1. CURRENT_WEEK -> 2025-01-09
        res_cur = selector.select_contract(
            "2025-01-05", 24000.0, OptionType.CE, "ATM", ExpirySelectionPolicy.CURRENT_WEEK
        )
        assert res_cur.resolved_expiry == date(2025, 1, 9)

        # 2. NEXT_WEEK -> 2025-01-16
        res_nxt = selector.select_contract(
            "2025-01-05", 24000.0, OptionType.CE, "ATM", ExpirySelectionPolicy.NEXT_WEEK
        )
        assert res_nxt.resolved_expiry == date(2025, 1, 16)

        # 3. MONTHLY -> 2025-01-30 (last expiry of month)
        res_mon = selector.select_contract(
            "2025-01-05", 24000.0, OptionType.CE, "ATM", ExpirySelectionPolicy.MONTHLY
        )
        assert res_mon.resolved_expiry == date(2025, 1, 30)

    def test_data_eligibility_rejection(self, sample_contract_master: InMemoryContractMaster):
        """
        1. The use of function:
           Tests that contracts marked INELIGIBLE in data eligibility are rejected with CONTRACT_DATA_INELIGIBLE.

        2. How does the specific function work:
           Marks contract 'NSE_FO|NIFTY_2025-01-09_24000_CE' as ineligible for date 2025-01-05.
           Attempts selection and asserts rejection_reason is CONTRACT_DATA_INELIGIBLE.

        3. Concepts used in the function:
           Point-in-time data eligibility gating.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unchecked eligibility gate. After: Confirmed rejection with structured reason code.
        """
        sample_contract_master.mark_ineligible(date(2025, 1, 5), "NSE_FO|NIFTY_2025-01-09_24000_CE")
        selector = PointInTimeContractSelector(sample_contract_master)

        res = selector.select_contract(
            trade_date="2025-01-05",
            spot_price=24000.0,
            option_type=OptionType.CE,
            strike_policy="ATM",
        )
        assert res.is_eligible is False
        assert res.rejection_reason == "CONTRACT_DATA_INELIGIBLE"
        assert res.selected_contract is not None
        assert res.selected_contract.strike_price == 24000.0


@pytest.mark.gate_g2a
class TestDuckDbContractMasterIntegration:
    """
    1. The use of class:
       Integration tests verifying PointInTimeContractSelector against production quantview.duckdb.

    2. What the class contains:
       - test_duckdb_real_contract_selection: Queries actual lake view v_candles_options.

    3. Technologies used and why:
       duckdb queries against real Parquet-backed lake data.

    4. Key design and overall design of the class:
       Confirms end-to-end integration with the historical data lake.
    """

    def test_duckdb_real_contract_selection(self):
        """
        1. The use of function:
           Tests that DuckDbContractMaster queries real lake data and selects a valid historical contract.

        2. How does the specific function work:
           Initializes DuckDbContractMaster on Data/lake/quantview.duckdb, queries NIFTY options on 2025-01-02,
           and selects ATM CE.

        3. Concepts used in the function:
           End-to-end lake integration.

        4. Places where this function is imported and used:
           Run by pytest suite.

        5. Final output of the function, before and after:
           Before: Unverified lake query. After: Verified real contract selected with correct lot size.
        """
        duckdb_path = Path("Data/lake/quantview.duckdb")
        if not duckdb_path.exists():
            pytest.skip("Data/lake/quantview.duckdb not present")

        provider = DuckDbContractMaster(str(duckdb_path))
        selector = PointInTimeContractSelector(provider)

        # On 2025-01-02, NIFTY spot was around 24000
        res = selector.select_contract(
            trade_date="2025-01-02",
            spot_price=24000.0,
            option_type=OptionType.CE,
            strike_policy="ATM",
            underlying_symbol="NIFTY",
        )

        assert res.selected_contract is not None
        assert res.is_eligible is True
        assert res.selected_contract.expiry_date == "2025-01-02"
        assert res.selected_contract.option_type == OptionType.CE
        assert res.selected_contract.lot_size == 75  # 2025 lot size at source was 75
        assert len(res.candidate_strikes) > 0
