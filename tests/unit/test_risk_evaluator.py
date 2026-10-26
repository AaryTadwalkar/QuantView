"""
1. What this file does:
   Comprehensive unit tests for the RiskPolicyEvaluator and canonical RiskRules (Task M4-20).

2. Overall design:
   Uses pytest to verify pre-trade risk evaluation branches:
     - RK-01: Manual kill switch halts all order routing.
     - RK-02: Orders outside the permitted trading window are rejected.
     - RK-06: Orders exceeding the 1,800 lot freeze limit are rejected fail-closed.
     - RK-03: Orders exceeding the daily loss limit are rejected.
     - RK-04: Orders exceeding the maximum drawdown ceiling are rejected.
     - RK-05: Orders exceeding maximum capital per trade are rejected.
     - Compliant orders return RiskDecision with verdict PASS.

3. Elements in the file:
   - TestRiskPolicyEvaluator: Unit test suite for pre-trade risk rules.

4. Final output of the file:
   - Automated pass/fail test execution for Task M4-20.
"""

import pytest

from packages.domain import ContractIdentifier, OptionType, Paise
from packages.risk import RiskDecision, RiskPolicyEvaluator, RiskRules, RiskVerdict


@pytest.fixture
def sample_contract() -> ContractIdentifier:
    """Fixture returning sample contract."""
    return ContractIdentifier(
        instrument_key="NSE_FO|NIFTY_24000_CE",
        trading_symbol="NIFTY 24000 CE",
        expiry_date="2025-01-09",
        strike_price=24000.0,
        option_type=OptionType.CE,
        lot_size=25,
    )


@pytest.mark.gate_g2a
class TestRiskPolicyEvaluator:
    """
    1. The use of class:
       Unit test suite validating all pre-trade risk checks.
    """

    def test_freeze_quantity_rk06_enforcement(self, sample_contract):
        """Tests that orders exceeding freeze_quantity (1,800) are rejected under RK-06."""
        evaluator = RiskPolicyEvaluator(freeze_quantity=1800)

        # 1800 lots: PASS
        pass_dec = evaluator.evaluate_order(sample_contract, quantity=1800)
        assert pass_dec.verdict == RiskVerdict.PASS

        # 1825 lots: REJECT under RK-06
        reject_dec = evaluator.evaluate_order(sample_contract, quantity=1825)
        assert reject_dec.verdict == RiskVerdict.REJECT
        assert reject_dec.rule_id == "RK-06"

    def test_kill_switch_rk01_enforcement(self, sample_contract):
        """Tests that active kill switch halts orders under RK-01."""
        rules = RiskRules(kill_switch_active=True)
        evaluator = RiskPolicyEvaluator(rules=rules)

        dec = evaluator.evaluate_order(sample_contract, quantity=25)
        assert dec.verdict == RiskVerdict.REJECT
        assert dec.rule_id == "RK-01"

    def test_trading_window_rk02_enforcement(self, sample_contract):
        """Tests that orders outside 09:15-15:25 are rejected under RK-02."""
        rules = RiskRules(trading_window_start="09:15", trading_window_end="15:25")
        evaluator = RiskPolicyEvaluator(rules=rules)

        # 09:14 (pre-market): REJECT
        dec_early = evaluator.evaluate_order(sample_contract, quantity=25, current_time_str="09:14")
        assert dec_early.verdict == RiskVerdict.REJECT
        assert dec_early.rule_id == "RK-02"

        # 15:26 (post-cutoff): REJECT
        dec_late = evaluator.evaluate_order(sample_contract, quantity=25, current_time_str="15:26")
        assert dec_late.verdict == RiskVerdict.REJECT
        assert dec_late.rule_id == "RK-02"

        # 10:00 (within window): PASS
        dec_ok = evaluator.evaluate_order(sample_contract, quantity=25, current_time_str="10:00")
        assert dec_ok.verdict == RiskVerdict.PASS

    def test_daily_loss_limit_rk03_enforcement(self, sample_contract):
        """Tests that orders are rejected when daily net loss reaches limit under RK-03."""
        rules = RiskRules(max_loss_per_day_paise=500_000)  # Rs 5,000 max loss
        evaluator = RiskPolicyEvaluator(rules=rules)

        # Loss of 400,000 paise: PASS
        dec_pass = evaluator.evaluate_order(sample_contract, quantity=25, daily_loss_paise=Paise(400_000))
        assert dec_pass.verdict == RiskVerdict.PASS

        # Loss of 500,000 paise: REJECT
        dec_reject = evaluator.evaluate_order(sample_contract, quantity=25, daily_loss_paise=Paise(500_000))
        assert dec_reject.verdict == RiskVerdict.REJECT
        assert dec_reject.rule_id == "RK-03"

    def test_max_drawdown_rk04_enforcement(self, sample_contract):
        """Tests that orders are rejected when drawdown reaches maximum percentage under RK-04."""
        rules = RiskRules(max_drawdown_pct=15.0)  # 15% max drawdown
        evaluator = RiskPolicyEvaluator(rules=rules)

        # Drawdown 10%: PASS
        assert evaluator.evaluate_order(sample_contract, quantity=25, drawdown_pct=10.0).verdict == RiskVerdict.PASS
        # Drawdown 15.5%: REJECT
        dec = evaluator.evaluate_order(sample_contract, quantity=25, drawdown_pct=15.5)
        assert dec.verdict == RiskVerdict.REJECT
        assert dec.rule_id == "RK-04"

    def test_max_capital_per_trade_rk05_enforcement(self, sample_contract):
        """Tests that orders exceeding single trade capital ceiling are rejected under RK-05."""
        rules = RiskRules(max_capital_per_trade_paise=1_000_000)  # Rs 10,000
        evaluator = RiskPolicyEvaluator(rules=rules)

        # 25 units @ Rs 100 (10,000 paise) = 250,000 paise: PASS
        assert evaluator.evaluate_order(sample_contract, quantity=25, price_paise=Paise(10000)).verdict == RiskVerdict.PASS

        # 250 units @ Rs 100 = 2,500,000 paise: REJECT
        dec = evaluator.evaluate_order(sample_contract, quantity=250, price_paise=Paise(10000))
        assert dec.verdict == RiskVerdict.REJECT
        assert dec.rule_id == "RK-05"
