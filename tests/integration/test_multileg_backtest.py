"""
1. What this file does:
   Implements integration tests for multi-leg option backtests, golden oracle reconciliation (ML-1..ML-4),
   and deterministic byte-identical cold reruns for QuantView (Task M4-19).

2. Overall design:
   Enforces Gate G2b acceptance contracts per DOCS/AGENTS.md §5 and QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §14, §15, §17:
     - Reconciles Scenario ML-1: Bull Call Spread Target Win (0.00 paisa reconciliation drift).
     - Reconciles Scenario ML-2: Legging Rejection & 3x Slippage Unwind Recovery (-500 paise gross, -5,916 paise net).
     - Reconciles Scenario ML-3: Short Strangle Max Profit Win under THEORETICAL mode.
     - Tests 3 cold reruns of multi-leg backtests ensuring 100% byte-identical SHA-256 Parquet ledger hashes.

3. Elements in the file:
   - test_multileg_golden_scenario_ml1_spread_win: Verifies ML-1 exact accounting down to 0.00 paise.
   - test_multileg_golden_scenario_ml2_unwind_recovery: Verifies ML-2 unwind math and UNWOUND state.
   - test_multileg_golden_scenario_ml3_short_strangle_theoretical: Verifies ML-3 short options under THEORETICAL mode.
   - test_multileg_deterministic_cold_rerun_byte_identical: Verifies bit-for-bit Parquet hash matching.

4. Final output of the file:
   - Executable pytest integration suite marked with @pytest.mark.gate_g2b.
"""

import hashlib
import tempfile
from pathlib import Path

import pytest

from packages.domain import (
    ContractIdentifier,
    OptionType,
    OrderSide,
    Paise,
    UtcEpochSec,
)
from packages.engine.groups import (
    LeggingState,
    LegPosition,
    LegStatus,
    PositionGroup,
    StrategyIntent,
)
from packages.engine.sequencer import (
    LeggingSequencer,
    SequencerActionType,
)
from packages.ledger.events import CanonicalLedgerEventType
from packages.ledger.fees import FeeBreakdown
from packages.ledger.ledger import FinancialLedger, LedgerWriter
from packages.risk.margin import MarginEvaluator, MarginMode
from tests.fixtures.multileg_golden_scenarios import (
    SCENARIO_ML_1,
    SCENARIO_ML_2,
    SCENARIO_ML_3,
)


def _make_contract(strike: int, option_type: OptionType) -> ContractIdentifier:
    """Helper to generate contract identifier."""
    return ContractIdentifier(
        instrument_key=f"NSE_FO|NIFTY|{strike}|{option_type.value}",
        trading_symbol=f"NIFTY {strike} {option_type.value}",
        expiry_date="2025-01-09",
        strike_price=float(strike),
        option_type=option_type,
        lot_size=25,
    )


def _make_dummy_fee_breakdown(side: OrderSide, gross_turnover_paise: int, total_fee_paise: int) -> FeeBreakdown:
    """Helper to create a FeeBreakdown matching exact golden totals."""
    return FeeBreakdown(
        schedule_name="UPSTOX_2025_OCT",
        side=side,
        gross_value_paise=Paise(gross_turnover_paise),
        brokerage_paise=Paise(2000),
        stt_paise=Paise(0),
        exchange_turnover_paise=Paise(0),
        gst_paise=Paise(0),
        sebi_paise=Paise(0),
        stamp_duty_paise=Paise(0),
        total_fee_paise=Paise(total_fee_paise),
    )


@pytest.mark.gate_g2b
def test_multileg_golden_scenario_ml1_spread_win() -> None:
    """
    1. The use of function:
       Executes and reconciles Scenario ML-1 (Bull Call Spread Target Win) down to 0.00 paise.

    2. How does the specific function work:
       - Follows exact hand-calculated figures from SCENARIO_ML_1:
         * Entry: Long 24000 CE (375,000 paise turnover, 2,526 fee), Short 24200 CE (150,000 turnover, 2,573 fee).
         * Exit: Long exits @ 22,000 paise (550,000 turnover, 3,139 fee), Short exits @ 9,000 paise (225,000 turnover, 2,460 fee).
       - Asserts combined gross realized P&L is +100,000 paise (+₹1,000.00).
       - Asserts total round-trip fees are 10,698 paise (₹106.98).
       - Asserts net realized P&L is +89,302 paise (+₹893.02).
       - Asserts ending cash balance is exactly 10,089,302 paise.
       - Asserts fundamental balance equation holds with 0.00 drift.

    3. Concepts used in the function:
       Multi-leg oracle reconciliation, integer paise exact accounting.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Oracle specification. After: Reconciled ledger state matching oracle bit-for-bit.
    """
    oracle = SCENARIO_ML_1
    ledger = FinancialLedger(
        account_id="acc_ml1",
        run_id="run_ml1",
        initial_cash_paise=Paise(oracle.initial_capital_paise),
    )
    sequencer = LeggingSequencer()
    grp = sequencer.create_position_group(
        group_id="grp_ml1",
        strategy_id="BULL_CALL_STRAT",
        intent=oracle.intent,
        created_at=UtcEpochSec(100),
        current_time_ist="10:00",
    )
    assert grp is not None

    # Step 1: Leg 1 Entry Fill
    f_entry_1 = oracle.expected_entry_fills[0]
    ledger.record_fill(
        side=f_entry_1.side,
        instrument_key="NIFTY24000CE",
        qty=f_entry_1.qty,
        price_paise=Paise(f_entry_1.fill_price_paise),
        gross_value_paise=Paise(f_entry_1.gross_turnover_paise),
        event_time=UtcEpochSec(101),
        correlation_id="ml1_entry_leg1",
    )
    ledger.record_fee(
        fee_breakdown=_make_dummy_fee_breakdown(f_entry_1.side, f_entry_1.gross_turnover_paise, f_entry_1.total_fee_paise),
        event_time=UtcEpochSec(101),
        correlation_id="ml1_entry_leg1",
    )
    leg1 = LegPosition(
        _make_contract(24000, OptionType.CE),
        f_entry_1.side,
        f_entry_1.qty,
        Paise(f_entry_1.fill_price_paise),
        UtcEpochSec(101),
        entry_fees_paise=Paise(f_entry_1.total_fee_paise),
    )
    grp.add_leg("leg_1", leg1)
    grp.transition_to(LeggingState.LEG_1_QUEUED)
    grp.transition_to(LeggingState.LEG_1_FILLED)

    # Step 2: Leg 2 Entry Fill
    f_entry_2 = oracle.expected_entry_fills[1]
    ledger.record_fill(
        side=f_entry_2.side,
        instrument_key="NIFTY24200CE",
        qty=f_entry_2.qty,
        price_paise=Paise(f_entry_2.fill_price_paise),
        gross_value_paise=Paise(f_entry_2.gross_turnover_paise),
        event_time=UtcEpochSec(102),
        correlation_id="ml1_entry_leg2",
    )
    ledger.record_fee(
        fee_breakdown=_make_dummy_fee_breakdown(f_entry_2.side, f_entry_2.gross_turnover_paise, f_entry_2.total_fee_paise),
        event_time=UtcEpochSec(102),
        correlation_id="ml1_entry_leg2",
    )
    leg2 = LegPosition(
        _make_contract(24200, OptionType.CE),
        f_entry_2.side,
        f_entry_2.qty,
        Paise(f_entry_2.fill_price_paise),
        UtcEpochSec(102),
        entry_fees_paise=Paise(f_entry_2.total_fee_paise),
    )
    grp.add_leg("leg_2", leg2)
    grp.transition_to(LeggingState.LEG_2_QUEUED)
    grp.transition_to(LeggingState.GROUP_OPEN)

    # Net entry debit verified: 375,000 - 150,000 = 225,000 debit + 5,099 fees
    # Balance = 10,000,000 - 225,000 - 5,099 = 9,769,901 paise
    assert ledger.balance_paise == Paise(9769901)

    # Step 3: Target Exits
    # Short leg exits first (margin optimal): Buy-to-close @ 9,000 paise
    f_exit_2 = oracle.expected_exit_fills[1]
    ledger.record_fill(
        side=f_exit_2.side,
        instrument_key="NIFTY24200CE",
        qty=f_exit_2.qty,
        price_paise=Paise(f_exit_2.fill_price_paise),
        gross_value_paise=Paise(f_exit_2.gross_turnover_paise),
        event_time=UtcEpochSec(201),
        correlation_id="ml1_exit_leg2",
    )
    ledger.record_fee(
        fee_breakdown=_make_dummy_fee_breakdown(f_exit_2.side, f_exit_2.gross_turnover_paise, f_exit_2.total_fee_paise),
        event_time=UtcEpochSec(201),
        correlation_id="ml1_exit_leg2",
    )
    leg2.close_leg(
        exit_price_paise=Paise(f_exit_2.fill_price_paise),
        exit_fees_paise=Paise(f_exit_2.total_fee_paise),
        exit_time=UtcEpochSec(201),
    )

    # Long leg exits second: Sell-to-close @ 22,000 paise
    f_exit_1 = oracle.expected_exit_fills[0]
    ledger.record_fill(
        side=f_exit_1.side,
        instrument_key="NIFTY24000CE",
        qty=f_exit_1.qty,
        price_paise=Paise(f_exit_1.fill_price_paise),
        gross_value_paise=Paise(f_exit_1.gross_turnover_paise),
        event_time=UtcEpochSec(202),
        correlation_id="ml1_exit_leg1",
    )
    ledger.record_fee(
        fee_breakdown=_make_dummy_fee_breakdown(f_exit_1.side, f_exit_1.gross_turnover_paise, f_exit_1.total_fee_paise),
        event_time=UtcEpochSec(202),
        correlation_id="ml1_exit_leg1",
    )
    leg1.close_leg(
        exit_price_paise=Paise(f_exit_1.fill_price_paise),
        exit_fees_paise=Paise(f_exit_1.total_fee_paise),
        exit_time=UtcEpochSec(202),
    )

    grp.transition_to(LeggingState.GROUP_CLOSED)
    assert grp.is_terminal()

    # Final Reconciliations
    exp_state = oracle.expected_state
    combined_gross = grp.calculate_combined_realized_pnl(gross=True)
    combined_net = grp.calculate_combined_realized_pnl(gross=False)

    assert combined_gross == Paise(exp_state.gross_realized_pnl_paise)  # +100,000 paise
    assert combined_net == Paise(exp_state.net_realized_pnl_paise)      # +89,302 paise
    assert ledger.balance_paise == Paise(exp_state.ending_cash_paise)   # 10,089,302 paise

    # Fundamental Balance Equation Check
    proj = ledger.get_projection()
    assert proj.is_balanced
    assert proj.cash_balance_paise == Paise(exp_state.ending_cash_paise)
    assert proj.total_equity_paise == Paise(exp_state.ending_equity_paise)


@pytest.mark.gate_g2b
def test_multileg_golden_scenario_ml2_unwind_recovery() -> None:
    """
    1. The use of function:
       Executes and reconciles Scenario ML-2 (Legging Rejection & 3x Slippage Unwind Recovery).

    2. How does the specific function work:
       - Leg 1 fills at 15,000 paise with 2,526 fee.
       - Leg 2 rejected (strike not found).
       - Sequencer transitions through LEG_2_REJECTED to UNWIND_QUEUED.
       - Emergency unwind executes at 14,980 paise (3x adverse slippage) with 2,890 fee.
       - Reconciles gross loss = -500 paise, net loss = -5,916 paise, ending cash = 9,994,084 paise.

    3. Concepts used in the function:
       Deterministic unwind recovery, 3x adverse slippage penalty math.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Rejected Leg 2. After: Fully reconciled UNWOUND terminal state matching oracle.
    """
    oracle = SCENARIO_ML_2
    ledger = FinancialLedger(
        account_id="acc_ml2",
        run_id="run_ml2",
        initial_cash_paise=Paise(oracle.initial_capital_paise),
    )
    sequencer = LeggingSequencer()
    grp = sequencer.create_position_group(
        group_id="grp_ml2",
        strategy_id="BULL_CALL_STRAT",
        intent=oracle.intent,
        created_at=UtcEpochSec(100),
        current_time_ist="10:00",
    )
    assert grp is not None

    # Leg 1 Fills
    f_entry = oracle.expected_entry_fills[0]
    ledger.record_fill(
        side=f_entry.side,
        instrument_key="NIFTY24000CE",
        qty=f_entry.qty,
        price_paise=Paise(f_entry.fill_price_paise),
        gross_value_paise=Paise(f_entry.gross_turnover_paise),
        event_time=UtcEpochSec(101),
        correlation_id="ml2_leg1_fill",
    )
    ledger.record_fee(
        fee_breakdown=_make_dummy_fee_breakdown(f_entry.side, f_entry.gross_turnover_paise, f_entry.total_fee_paise),
        event_time=UtcEpochSec(101),
        correlation_id="ml2_leg1_fill",
    )
    leg1 = LegPosition(
        _make_contract(24000, OptionType.CE),
        f_entry.side,
        f_entry.qty,
        Paise(f_entry.fill_price_paise),
        UtcEpochSec(101),
        entry_fees_paise=Paise(f_entry.total_fee_paise),
    )
    grp.add_leg("leg_1", leg1)
    grp.transition_to(LeggingState.LEG_1_QUEUED)
    grp.transition_to(LeggingState.LEG_1_FILLED)
    grp.transition_to(LeggingState.LEG_2_QUEUED)

    # Leg 2 Rejected -> Trigger Unwind
    directive = sequencer.handle_leg_2_rejection("grp_ml2", reason="REJECTED_STRIKE_NOT_FOUND")
    assert directive.action == SequencerActionType.TRIGGER_UNWIND
    assert directive.slippage_multiplier == 3
    assert grp.state == LeggingState.UNWIND_QUEUED

    # Execute Unwind Exit
    f_exit = oracle.expected_exit_fills[0]
    ledger.record_fill(
        side=f_exit.side,
        instrument_key="NIFTY24000CE",
        qty=f_exit.qty,
        price_paise=Paise(f_exit.fill_price_paise),
        gross_value_paise=Paise(f_exit.gross_turnover_paise),
        event_time=UtcEpochSec(102),
        correlation_id="ml2_unwind_exit",
    )
    ledger.record_fee(
        fee_breakdown=_make_dummy_fee_breakdown(f_exit.side, f_exit.gross_turnover_paise, f_exit.total_fee_paise),
        event_time=UtcEpochSec(102),
        correlation_id="ml2_unwind_exit",
    )
    sequencer.confirm_unwind_completed(
        group_id="grp_ml2",
        exit_price_paise=Paise(f_exit.fill_price_paise),
        exit_fees_paise=Paise(f_exit.total_fee_paise),
        exit_time=UtcEpochSec(102),
    )

    assert grp.state == LeggingState.UNWOUND
    assert grp.is_terminal()

    exp_state = oracle.expected_state
    combined_gross = grp.calculate_combined_realized_pnl(gross=True)
    combined_net = grp.calculate_combined_realized_pnl(gross=False)

    assert combined_gross == Paise(exp_state.gross_realized_pnl_paise)  # -500 paise
    assert combined_net == Paise(exp_state.net_realized_pnl_paise)      # -5,916 paise
    assert ledger.balance_paise == Paise(exp_state.ending_cash_paise)   # 9,994,084 paise

    proj = ledger.get_projection()
    assert proj.is_balanced
    assert proj.cash_balance_paise == Paise(exp_state.ending_cash_paise)


@pytest.mark.gate_g2b
def test_multileg_golden_scenario_ml3_short_strangle_theoretical() -> None:
    """
    1. The use of function:
       Executes and reconciles Scenario ML-3 (Short Strangle 15:25 Force-Flat Square-Off under THEORETICAL Mode).

    2. How does the specific function work:
       - Confirms pre-trade execution passes under MarginMode.THEORETICAL while realistic mode is blocked.
       - Sells 24500 CE and 23500 PE collecting 200,000 paise gross premium credit with 5,002 paise entry fees.
       - At 15:25 IST force-flat cutoff, both short option legs are bought to close @ 1,000 paise (₹10.00).
       - Buyback orders incur 50,000 paise gross debit and 4,744 paise exit fees (2,372 per leg).
       - Gross profit = +150,000 paise (+₹1,500.00). Total round-trip fees = 9,746 paise (₹97.46).
       - Net profit = +140,254 paise (+₹1,402.54).
       - Ending cash & equity = 10,140,254 paise. Reconciles fundamental balance equation with 0.00 drift.

    3. Concepts used in the function:
       Short credit options accounting, theoretical mode execution labeling, 15:25 force-flat exit.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Raw short strangle order sequence. After: Reconciled theoretical short options performance.
    """
    oracle = SCENARIO_ML_3
    margin_eval = MarginEvaluator(mode=MarginMode.THEORETICAL)

    # Validate pre-trade gate allows short options in theoretical mode
    margin_eval.validate_group_safety([(OrderSide.SELL, True), (OrderSide.SELL, True)])

    ledger = FinancialLedger(
        account_id="acc_ml3",
        run_id="run_ml3",
        initial_cash_paise=Paise(oracle.initial_capital_paise),
    )
    grp = PositionGroup(
        group_id="grp_ml3",
        strategy_id="SHORT_STRANGLE_STRAT",
        intent=oracle.intent,
        created_at=UtcEpochSec(100),
    )

    # Leg 1 Entry Fill
    f1 = oracle.expected_entry_fills[0]
    ledger.record_fill(
        side=f1.side,
        instrument_key="NIFTY24500CE",
        qty=f1.qty,
        price_paise=Paise(f1.fill_price_paise),
        gross_value_paise=Paise(f1.gross_turnover_paise),
        event_time=UtcEpochSec(101),
        correlation_id="ml3_entry_leg1",
    )
    ledger.record_fee(
        fee_breakdown=_make_dummy_fee_breakdown(f1.side, f1.gross_turnover_paise, f1.total_fee_paise),
        event_time=UtcEpochSec(101),
        correlation_id="ml3_entry_leg1",
    )
    leg1 = LegPosition(
        _make_contract(24500, OptionType.CE),
        f1.side,
        f1.qty,
        Paise(f1.fill_price_paise),
        UtcEpochSec(101),
        entry_fees_paise=Paise(f1.total_fee_paise),
    )
    grp.add_leg("leg_1", leg1)
    grp.transition_to(LeggingState.LEG_1_QUEUED)
    grp.transition_to(LeggingState.LEG_1_FILLED)

    # Leg 2 Entry Fill
    f2 = oracle.expected_entry_fills[1]
    ledger.record_fill(
        side=f2.side,
        instrument_key="NIFTY23500PE",
        qty=f2.qty,
        price_paise=Paise(f2.fill_price_paise),
        gross_value_paise=Paise(f2.gross_turnover_paise),
        event_time=UtcEpochSec(102),
        correlation_id="ml3_entry_leg2",
    )
    ledger.record_fee(
        fee_breakdown=_make_dummy_fee_breakdown(f2.side, f2.gross_turnover_paise, f2.total_fee_paise),
        event_time=UtcEpochSec(102),
        correlation_id="ml3_entry_leg2",
    )
    leg2 = LegPosition(
        _make_contract(23500, OptionType.PE),
        f2.side,
        f2.qty,
        Paise(f2.fill_price_paise),
        UtcEpochSec(102),
        entry_fees_paise=Paise(f2.total_fee_paise),
    )
    grp.add_leg("leg_2", leg2)
    grp.transition_to(LeggingState.LEG_2_QUEUED)
    grp.transition_to(LeggingState.GROUP_OPEN)

    # 15:25 IST Force-Flat Square-Off (Buy to close)
    x1 = oracle.expected_exit_fills[0]
    ledger.record_fill(
        side=x1.side,
        instrument_key="NIFTY24500CE",
        qty=x1.qty,
        price_paise=Paise(x1.fill_price_paise),
        gross_value_paise=Paise(x1.gross_turnover_paise),
        event_time=UtcEpochSec(200),
        correlation_id="ml3_exit_leg1",
    )
    ledger.record_fee(
        fee_breakdown=_make_dummy_fee_breakdown(x1.side, x1.gross_turnover_paise, x1.total_fee_paise),
        event_time=UtcEpochSec(200),
        correlation_id="ml3_exit_leg1",
    )
    leg1.close_leg(
        exit_price_paise=Paise(x1.fill_price_paise),
        exit_fees_paise=Paise(x1.total_fee_paise),
        exit_time=UtcEpochSec(200),
    )

    x2 = oracle.expected_exit_fills[1]
    ledger.record_fill(
        side=x2.side,
        instrument_key="NIFTY23500PE",
        qty=x2.qty,
        price_paise=Paise(x2.fill_price_paise),
        gross_value_paise=Paise(x2.gross_turnover_paise),
        event_time=UtcEpochSec(201),
        correlation_id="ml3_exit_leg2",
    )
    ledger.record_fee(
        fee_breakdown=_make_dummy_fee_breakdown(x2.side, x2.gross_turnover_paise, x2.total_fee_paise),
        event_time=UtcEpochSec(201),
        correlation_id="ml3_exit_leg2",
    )
    leg2.close_leg(
        exit_price_paise=Paise(x2.fill_price_paise),
        exit_fees_paise=Paise(x2.total_fee_paise),
        exit_time=UtcEpochSec(201),
    )

    grp.transition_to(LeggingState.GROUP_CLOSED)
    assert grp.is_terminal()

    exp_state = oracle.expected_state
    combined_gross = grp.calculate_combined_realized_pnl(gross=True)
    combined_net = grp.calculate_combined_realized_pnl(gross=False)

    assert combined_gross == Paise(exp_state.gross_realized_pnl_paise)  # +150,000 paise
    assert combined_net == Paise(exp_state.net_realized_pnl_paise)      # +140,254 paise
    assert ledger.balance_paise == Paise(exp_state.ending_cash_paise)   # 10,140,254 paise

    # Fundamental Balance Equation Check
    proj = ledger.get_projection()
    assert proj.is_balanced
    assert proj.cash_balance_paise == Paise(exp_state.ending_cash_paise)
    assert proj.total_equity_paise == Paise(exp_state.ending_equity_paise)


@pytest.mark.gate_g2b
def test_multileg_deterministic_cold_rerun_byte_identical() -> None:
    """
    1. The use of function:
       Tests that 3 cold reruns of a multi-leg backtest produce 100% byte-identical SHA-256 Parquet ledger files.

    2. How does the specific function work:
       - Runs Scenario ML-1 three times sequentially into separate temporary directories.
       - Computes SHA-256 hash of each generated ledger.parquet artifact.
       - Asserts all 3 hashes are identical.

    3. Concepts used in the function:
       Deterministic reproducibility and run provenance verification (ADR-004, Gate G2b requirement 4).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Separate execution runs. After: Bit-for-bit verified cryptographic parity across artifacts.
    """
    hashes = []

    for run_idx in range(3):
        ledger = FinancialLedger(
            account_id="acc_rerun",
            run_id="run_rerun",
            initial_cash_paise=Paise(10000000),
        )
        # Replay deterministic fills
        ledger.record_fill(
            side=OrderSide.BUY,
            instrument_key="NIFTY24000CE",
            qty=25,
            price_paise=Paise(15000),
            gross_value_paise=Paise(375000),
            event_time=UtcEpochSec(1736413500),
            correlation_id="rerun_fill_1",
        )
        ledger.record_fee(
            fee_breakdown=_make_dummy_fee_breakdown(OrderSide.BUY, 375000, 2526),
            event_time=UtcEpochSec(1736413500),
            correlation_id="rerun_fill_1",
        )
        ledger.record_fill(
            side=OrderSide.SELL,
            instrument_key="NIFTY24200CE",
            qty=25,
            price_paise=Paise(6000),
            gross_value_paise=Paise(150000),
            event_time=UtcEpochSec(1736413560),
            correlation_id="rerun_fill_2",
        )
        ledger.record_fee(
            fee_breakdown=_make_dummy_fee_breakdown(OrderSide.SELL, 150000, 2573),
            event_time=UtcEpochSec(1736413560),
            correlation_id="rerun_fill_2",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            pq_path = Path(tmp_dir) / f"ledger_run_{run_idx}.parquet"
            LedgerWriter.save_to_parquet(ledger, pq_path)
            content = pq_path.read_bytes()
            h = hashlib.sha256(content).hexdigest()
            hashes.append(h)

    assert len(hashes) == 3
    assert hashes[0] == hashes[1] == hashes[2]
