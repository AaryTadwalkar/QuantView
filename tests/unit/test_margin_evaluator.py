"""
1. What this file does:
   Defines unit tests for the MarginEvaluator, dated verification record, fail-closed guard,
   and ledger margin reservation events for QuantView (Task M4-17).

2. Overall design:
   Enforces acceptance contracts for Gate G2b per DOCS/AGENTS.md §5 and QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §14, §17:
     - Tests the dated regulatory VERIFY record linking to Task M4-21 empirical research.
     - Tests hard fail-closed gate rejecting short options under REALISTIC_ACCOUNT mode without clearing files.
     - Tests theoretical execution mode with prominent audit labels.
     - Tests buying power evaluation and free cash calculations.
     - Tests MARGIN_RESERVED and MARGIN_RELEASED financial ledger events, parquet serialization, and balance preservation.

3. Elements in the file:
   - Test cases: test_margin_verification_record_contract, test_realistic_mode_blocks_short_options,
     test_theoretical_mode_allows_short_options, test_buying_power_check,
     test_financial_ledger_margin_events_and_free_cash, test_ledger_margin_parquet_round_trip.

4. Final output of the file:
   - Executable pytest suite marked with @pytest.mark.gate_g2b.
"""

from pathlib import Path
import tempfile
import pytest

from packages.domain import OrderSide, Paise, UtcEpochSec
from packages.ledger.events import CanonicalLedgerEventType
from packages.ledger.ledger import FinancialLedger, LedgerWriter
from packages.risk.margin import (
    MARGIN_VERIFICATION_RECORD,
    MarginEvaluator,
    MarginMode,
    RealisticMarginBlockedError,
)


@pytest.mark.gate_g2b
def test_margin_verification_record_contract() -> None:
    """
    1. The use of function:
       Tests that MARGIN_VERIFICATION_RECORD fulfills the dated VERIFY requirements of Task M4-17.

    2. How does the specific function work:
       - Inspects record fields: verification task, research task reference, date, status, and enforcement action.
       - Asserts that clearing files are flagged as unavailable, triggering the fail-closed short option block.

    3. Concepts used in the function:
       Regulatory audit provenance and SEBI clearing file tracking.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Raw dictionary. After: Verified compliance with Task M4-17 acceptance contract.
    """
    rec = MARGIN_VERIFICATION_RECORD
    assert rec["verification_task"] == "M4-17"
    assert rec["research_task_ref"] == "M4-21"
    assert rec["research_report"] == "reports/margin-settlement-evidence.md"
    assert rec["date"] == "2026-10-27"
    assert rec["status"] == "VERIFY_SPAN_FILES_ABSENT"
    assert rec["clearing_files_available"] is False
    assert rec["span_risk_parameter_file_type"] == ".spn"
    assert rec["hedge_benefit_framework"] == "SEBI/HO/MRD/DRMNP/CIR/P/2020/06"
    assert rec["enforcement_action"] == "REJECT_REALISTIC_SHORT_OPTIONS"
    assert rec["theoretical_label_mandatory"] is True


@pytest.mark.gate_g2b
def test_realistic_mode_blocks_short_options() -> None:
    """
    1. The use of function:
       Tests that unverified REALISTIC_ACCOUNT mode strictly blocks short option orders and multi-leg groups.

    2. How does the specific function work:
       - Instantiates MarginEvaluator in REALISTIC_ACCOUNT mode (is_verified=False).
       - Confirms long option orders pass without error.
       - Confirms short option orders raise RealisticMarginBlockedError with MARGIN_NOT_VERIFIED.
       - Confirms multi-leg group containing short leg raises RealisticMarginBlockedError.

    3. Concepts used in the function:
       Fail-closed margin guard (ENGINE §14, §17).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Proposed orders. After: Verified fail-closed error with exact canonical rejection code.
    """
    evaluator = MarginEvaluator(mode=MarginMode.REALISTIC_ACCOUNT, is_verified=False)

    # Long option allowed
    evaluator.validate_order_safety(side=OrderSide.BUY, is_option=True)

    # Short option rejected
    with pytest.raises(RealisticMarginBlockedError) as exc_info:
        evaluator.validate_order_safety(side=OrderSide.SELL, is_option=True)
    assert exc_info.value.error_code == "MARGIN_NOT_VERIFIED"
    assert "Real-time clearing member SPAN risk parameter files" in str(exc_info.value)

    # Multi-leg group with short leg rejected
    spread_legs = [(OrderSide.BUY, True), (OrderSide.SELL, True)]
    with pytest.raises(RealisticMarginBlockedError):
        evaluator.validate_group_safety(spread_legs)


@pytest.mark.gate_g2b
def test_theoretical_mode_allows_short_options() -> None:
    """
    1. The use of function:
       Tests that THEORETICAL mode permits short options and spreads while maintaining visible audit labels.

    2. How does the specific function work:
       - Evaluator in THEORETICAL mode allows long and short option orders without error.
       - Evaluates group safety on spread with short leg: passes without error.
       - Verifies get_margin_status() emits audit_label='MARGIN_NOT_VERIFIED' and theoretical mode.

    3. Concepts used in the function:
       Theoretical execution labeling per AGENTS.md Task M4-17.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Orders in theoretical mode. After: Successful validation with transparent audit metadata.
    """
    evaluator = MarginEvaluator(mode=MarginMode.THEORETICAL)

    # Both long and short pass
    evaluator.validate_order_safety(side=OrderSide.BUY, is_option=True)
    evaluator.validate_order_safety(side=OrderSide.SELL, is_option=True)
    evaluator.validate_group_safety([(OrderSide.BUY, True), (OrderSide.SELL, True)])

    status = evaluator.get_margin_status()
    assert status["margin_mode"] == "THEORETICAL"
    assert status["is_verified"] is False
    assert status["audit_label"] == "MARGIN_NOT_VERIFIED"
    assert "verification_record" in status


@pytest.mark.gate_g2b
def test_buying_power_check() -> None:
    """
    1. The use of function:
       Tests free cash sufficiency check against required initial margin.

    2. How does the specific function work:
       - Free cash 1,000,000 paise vs required margin 800,000 paise -> returns True.
       - Free cash 500,000 paise vs required margin 800,000 paise -> returns False.

    3. Concepts used in the function:
       Free cash buying power verification (ENGINE §8).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Capital and requirement. After: Boolean buying power verdict.
    """
    evaluator = MarginEvaluator(mode=MarginMode.THEORETICAL)
    assert evaluator.check_buying_power(free_cash_paise=Paise(1000000), required_margin_paise=Paise(800000))
    assert not evaluator.check_buying_power(free_cash_paise=Paise(500000), required_margin_paise=Paise(800000))


@pytest.mark.gate_g2b
def test_financial_ledger_margin_events_and_free_cash() -> None:
    """
    1. The use of function:
       Tests that MARGIN_RESERVED and MARGIN_RELEASED events update free cash without mutating cash balance.

    2. How does the specific function work:
       - Initializes ledger with ₹100,000.00 (10,000,000 paise).
       - Asserts cash_balance == 10,000,000 paise and free_cash == 10,000,000 paise.
       - Reserves ₹25,000.00 margin (2,500,000 paise):
         * Verifies cash_balance remains 10,000,000 paise (0 cash movement).
         * Verifies reserved_margin is 2,500,000 paise and free_cash is 7,500,000 paise.
         * Verifies event is recorded as MARGIN_RESERVED.
       - Releases margin:
         * Verifies cash_balance remains 10,000,000 paise.
         * Verifies reserved_margin returns to 0 and free_cash returns to 10,000,000 paise.
         * Verifies event is recorded as MARGIN_RELEASED.
       - Reconstructs projection via get_projection() and asserts balance equation is perfectly preserved.

    3. Concepts used in the function:
       Collateral reservation vs cash movement separation (ENGINE §8).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Initial balance. After: Reconciled ledger state with verified free cash and balance equation.
    """
    ledger = FinancialLedger(initial_cash_paise=Paise(10000000))
    assert ledger.balance_paise == Paise(10000000)
    assert ledger.free_cash_paise == Paise(10000000)
    assert ledger.reserved_margin_paise == Paise(0)

    # 1. Reserve Margin
    ev_res = ledger.record_margin_reserved(
        margin_paise=Paise(2500000),
        event_time=UtcEpochSec(100),
        correlation_id="corr_margin_1",
        description="Initial margin for short call",
    )
    assert ev_res.event_type == CanonicalLedgerEventType.MARGIN_RESERVED
    assert ev_res.amount_paise == Paise(0)  # Cash balance unaffected!
    assert ledger.balance_paise == Paise(10000000)
    assert ledger.reserved_margin_paise == Paise(2500000)
    assert ledger.free_cash_paise == Paise(7500000)
    assert ev_res.metadata["reserved_margin_paise"] == 2500000
    assert ev_res.metadata["free_cash_paise"] == 7500000

    # 2. Release Margin
    ev_rel = ledger.record_margin_released(
        margin_paise=Paise(2500000),
        event_time=UtcEpochSec(200),
        correlation_id="corr_margin_2",
        description="Release margin on square-off",
    )
    assert ev_rel.event_type == CanonicalLedgerEventType.MARGIN_RELEASED
    assert ev_rel.amount_paise == Paise(0)
    assert ledger.balance_paise == Paise(10000000)
    assert ledger.reserved_margin_paise == Paise(0)
    assert ledger.free_cash_paise == Paise(10000000)

    # 3. Verify Fundamental Balance Equation
    proj = ledger.get_projection()
    assert proj.is_balanced
    assert proj.cash_balance_paise == Paise(10000000)
    assert proj.total_equity_paise == Paise(10000000)


@pytest.mark.gate_g2b
def test_ledger_margin_parquet_round_trip() -> None:
    """
    1. The use of function:
       Tests that MARGIN_RESERVED and MARGIN_RELEASED events serialize to Parquet and reconstruct bit-identical state.

    2. How does the specific function work:
       - Creates ledger with deposit and margin reservation.
       - Writes to temporary Parquet file via LedgerWriter.save_to_parquet.
       - Reloads via LedgerWriter.load_from_parquet.
       - Verifies that balance, reserved margin, and free cash are identical.

    3. Concepts used in the function:
       Deterministic Parquet persistence and replay for margin events.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: In-memory ledger. After: Reconstructed ledger with identical margin attributes.
    """
    ledger = FinancialLedger(initial_cash_paise=Paise(10000000))
    ledger.record_margin_reserved(
        margin_paise=Paise(3000000),
        event_time=UtcEpochSec(100),
        correlation_id="margin_pq_1",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        pq_path = Path(tmp_dir) / "ledger.parquet"
        LedgerWriter.save_to_parquet(ledger, pq_path)

        reloaded = LedgerWriter.load_from_parquet(pq_path)
        assert len(reloaded.events) == 1
        assert reloaded.balance_paise == Paise(10000000)
        assert reloaded.reserved_margin_paise == Paise(3000000)
        assert reloaded.free_cash_paise == Paise(7000000)
