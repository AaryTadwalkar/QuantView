"""
1. What this file does:
   Defines unit tests for PositionGroup, LegPosition, the 10-state legging state machine,
   stale mark propagation, and the fail-closed margin guard (Tasks M4-14, M4-16, M4-17).

2. Overall design:
   Enforces acceptance contracts for Gate G2b per DOCS/AGENTS.md §5 and QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §24:
     - Tests all legal transitions in the 10-state legging state machine.
     - Tests illegal transitions raising InvalidLeggingTransitionError.
     - Tests exact integer paise valuation across individual legs and multi-leg composite groups.
     - Tests stale mark propagation across multi-leg groups.
     - Tests fail-closed margin evaluation rejecting unverified short options in REALISTIC_ACCOUNT mode.

3. Elements in the file:
   - Test fixtures for contracts and timestamps.
   - Test cases: test_state_machine_legal_spread_flow, test_state_machine_illegal_transitions,
     test_leg_position_mark_and_realized_pnl, test_position_group_combined_pnl,
     test_position_group_stale_mark_propagation, test_margin_evaluator_fail_closed_guard.

4. Final output of the file:
   - Executable pytest suite marked with @pytest.mark.gate_g2b.
"""

from datetime import date

import pytest

from packages.domain import (
    ContractIdentifier,
    OperatingMode,
    OptionType,
    OrderSide,
    Paise,
    UtcEpochSec,
)
from packages.engine.groups import (
    InvalidLeggingTransitionError,
    LeggingState,
    LegPosition,
    LegStatus,
    PositionGroup,
    StrategyIntent,
)
from packages.risk.margin import (
    MarginEvaluator,
    MarginMode,
    RealisticMarginBlockedError,
)


def _make_sample_contract(strike: int, option_type: OptionType) -> ContractIdentifier:
    """Helper to generate consistent test contract identifiers."""
    return ContractIdentifier(
        instrument_key=f"NSE_FO|NIFTY|{strike}|{option_type.value}",
        trading_symbol=f"NIFTY {strike} {option_type.value}",
        expiry_date="2025-01-09",
        strike_price=float(strike),
        option_type=option_type,
        lot_size=25,
    )


@pytest.mark.gate_g2b
def test_legging_state_machine_legal_spread_flow() -> None:
    """
    1. The use of function:
       Tests the normal happy-path lifecycle of a 2-leg spread through the 10-state machine.

    2. How does the specific function work:
       - Creates PositionGroup at INTENT_CREATED.
       - Transitions sequentially through LEG_1_QUEUED -> LEG_1_FILLED -> LEG_2_QUEUED -> GROUP_OPEN -> GROUP_CLOSED.
       - Asserts current state and terminal status at each stage.

    3. Concepts used in the function:
       Finite state automaton transition validation.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Initial group. After: Verified valid transition sequence to terminal GROUP_CLOSED.
    """
    created_at = UtcEpochSec(1736413500)
    grp = PositionGroup(
        group_id="grp_bull_call_001",
        strategy_id="BULL_CALL_STRAT",
        intent=StrategyIntent.BULL_CALL_SPREAD,
        created_at=created_at,
    )

    assert grp.state == LeggingState.INTENT_CREATED
    assert not grp.is_terminal()

    grp.transition_to(LeggingState.LEG_1_QUEUED)
    assert grp.state == LeggingState.LEG_1_QUEUED

    grp.transition_to(LeggingState.LEG_1_FILLED)
    assert grp.state == LeggingState.LEG_1_FILLED

    grp.transition_to(LeggingState.LEG_2_QUEUED)
    assert grp.state == LeggingState.LEG_2_QUEUED

    grp.transition_to(LeggingState.GROUP_OPEN)
    assert grp.state == LeggingState.GROUP_OPEN
    assert not grp.is_terminal()

    grp.transition_to(LeggingState.GROUP_CLOSED)
    assert grp.state == LeggingState.GROUP_CLOSED
    assert grp.is_terminal()


@pytest.mark.gate_g2b
def test_legging_state_machine_legal_single_leg_flow() -> None:
    """
    1. The use of function:
       Tests that a 1-leg position group can transition directly from LEG_1_FILLED to GROUP_OPEN.

    2. How does the specific function work:
       Transitions: INTENT_CREATED -> LEG_1_QUEUED -> LEG_1_FILLED -> GROUP_OPEN -> GROUP_CLOSED.

    3. Concepts used in the function:
       Single-leg lifecycle compliance in composite group abstraction.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Initial 1-leg group. After: Verified valid progression to GROUP_CLOSED.
    """
    grp = PositionGroup(
        group_id="grp_single_001",
        strategy_id="SINGLE_STRAT",
        intent=StrategyIntent.SINGLE_LEG_LONG,
        created_at=UtcEpochSec(1736413500),
    )
    grp.transition_to(LeggingState.LEG_1_QUEUED)
    grp.transition_to(LeggingState.LEG_1_FILLED)
    grp.transition_to(LeggingState.GROUP_OPEN)
    assert grp.state == LeggingState.GROUP_OPEN
    grp.transition_to(LeggingState.GROUP_CLOSED)
    assert grp.is_terminal()


@pytest.mark.gate_g2b
def test_legging_state_machine_unwind_recovery_flow() -> None:
    """
    1. The use of function:
       Tests the emergency unwind recovery sequence when Leg 2 is rejected.

    2. How does the specific function work:
       Transitions: INTENT_CREATED -> LEG_1_QUEUED -> LEG_1_FILLED -> LEG_2_QUEUED -> LEG_2_REJECTED -> UNWIND_QUEUED -> UNWOUND.

    3. Concepts used in the function:
       Deterministic unwind recovery state progression (ENGINE §24).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Initial group. After: Verified progression through unwind to terminal UNWOUND.
    """
    grp = PositionGroup(
        group_id="grp_unwind_001",
        strategy_id="BULL_CALL_STRAT",
        intent=StrategyIntent.BULL_CALL_SPREAD,
        created_at=UtcEpochSec(1736413500),
    )
    grp.transition_to(LeggingState.LEG_1_QUEUED)
    grp.transition_to(LeggingState.LEG_1_FILLED)
    grp.transition_to(LeggingState.LEG_2_QUEUED)
    grp.transition_to(LeggingState.LEG_2_REJECTED)
    assert grp.state == LeggingState.LEG_2_REJECTED

    grp.transition_to(LeggingState.UNWIND_QUEUED)
    assert grp.state == LeggingState.UNWIND_QUEUED
    assert not grp.is_terminal()

    grp.transition_to(LeggingState.UNWOUND)
    assert grp.state == LeggingState.UNWOUND
    assert grp.is_terminal()


@pytest.mark.gate_g2b
def test_legging_state_machine_halted_unresolved_transitions() -> None:
    """
    1. The use of function:
       Tests fail-closed transitions to HALTED_UNRESOLVED upon missing data or timeouts.

    2. How does the specific function work:
       Verifies that LEG_1_QUEUED, GROUP_OPEN, and UNWIND_QUEUED can each safely enter HALTED_UNRESOLVED.

    3. Concepts used in the function:
       Fail-closed market-halt handling (ENGINE §19.1).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Active states. After: Verified terminal HALTED_UNRESOLVED transitions.
    """
    # From LEG_1_QUEUED
    g1 = PositionGroup("g1", "s", StrategyIntent.BULL_CALL_SPREAD, UtcEpochSec(100))
    g1.transition_to(LeggingState.LEG_1_QUEUED)
    g1.transition_to(LeggingState.HALTED_UNRESOLVED)
    assert g1.state == LeggingState.HALTED_UNRESOLVED
    assert g1.is_terminal()

    # From GROUP_OPEN
    g2 = PositionGroup("g2", "s", StrategyIntent.BULL_CALL_SPREAD, UtcEpochSec(100))
    g2.transition_to(LeggingState.LEG_1_QUEUED)
    g2.transition_to(LeggingState.LEG_1_FILLED)
    g2.transition_to(LeggingState.GROUP_OPEN)
    g2.transition_to(LeggingState.HALTED_UNRESOLVED)
    assert g2.state == LeggingState.HALTED_UNRESOLVED
    assert g2.is_terminal()

    # From UNWIND_QUEUED
    g3 = PositionGroup("g3", "s", StrategyIntent.BULL_CALL_SPREAD, UtcEpochSec(100))
    g3.transition_to(LeggingState.LEG_1_QUEUED)
    g3.transition_to(LeggingState.LEG_1_FILLED)
    g3.transition_to(LeggingState.LEG_2_QUEUED)
    g3.transition_to(LeggingState.LEG_2_REJECTED)
    g3.transition_to(LeggingState.UNWIND_QUEUED)
    g3.transition_to(LeggingState.HALTED_UNRESOLVED)
    assert g3.state == LeggingState.HALTED_UNRESOLVED
    assert g3.is_terminal()


@pytest.mark.gate_g2b
def test_legging_state_machine_illegal_transitions_raise_error() -> None:
    """
    1. The use of function:
       Ensures that any illegal transition attempt raises InvalidLeggingTransitionError.

    2. How does the specific function work:
       Tests illegal leaps such as INTENT_CREATED directly to GROUP_OPEN, or jumping from terminal states.

    3. Concepts used in the function:
       Fail-closed state validation and invariant protection.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Attempted invalid jump. After: InvalidLeggingTransitionError caught and verified.
    """
    grp = PositionGroup("g_err", "s", StrategyIntent.BULL_CALL_SPREAD, UtcEpochSec(100))

    # Cannot jump from INTENT_CREATED directly to GROUP_OPEN
    with pytest.raises(InvalidLeggingTransitionError) as exc_info:
        grp.transition_to(LeggingState.GROUP_OPEN)
    assert "cannot transition from INTENT_CREATED to GROUP_OPEN" in str(exc_info.value)

    # Cannot jump to UNWOUND directly
    with pytest.raises(InvalidLeggingTransitionError):
        grp.transition_to(LeggingState.UNWOUND)

    # Progress to GROUP_CLOSED
    grp.transition_to(LeggingState.LEG_1_QUEUED)
    grp.transition_to(LeggingState.LEG_1_FILLED)
    grp.transition_to(LeggingState.GROUP_OPEN)
    grp.transition_to(LeggingState.GROUP_CLOSED)

    # Terminal state GROUP_CLOSED cannot transition to anything
    with pytest.raises(InvalidLeggingTransitionError):
        grp.transition_to(LeggingState.GROUP_OPEN)

    with pytest.raises(InvalidLeggingTransitionError):
        grp.transition_to(LeggingState.INTENT_CREATED)


@pytest.mark.gate_g2b
def test_leg_position_mark_and_realized_pnl() -> None:
    """
    1. The use of function:
       Tests mark-to-market and realized P&L calculations for both long and short option legs.

    2. How does the specific function work:
       - Tests Long Leg (BUY 25 units @ 15,000 paise):
         * Mark at 16,000 paise -> unrealized P&L = +25,000 paise.
         * Close at 17,000 paise with fees (entry 2,526, exit 3,139) -> gross = +50,000, net = +44,335.
       - Tests Short Leg (SELL 25 units @ 6,000 paise):
         * Mark at 5,000 paise -> unrealized P&L = +25,000 paise.
         * Close at 7,000 paise with fees (entry 2,573, exit 2,460) -> gross = -25,000, net = -30,033.

    3. Concepts used in the function:
       Exact integer paise arithmetic, long/short directional payoff, round-trip fee deduction.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Raw prices. After: Reconciled P&L values accurate to the exact integer paisa.
    """
    # 1. Long Leg
    c_long = _make_sample_contract(24000, OptionType.CE)
    leg_long = LegPosition(
        contract=c_long,
        side=OrderSide.BUY,
        qty=25,
        entry_price_paise=Paise(15000),  # ₹150.00
        entry_time=UtcEpochSec(100),
        entry_fees_paise=Paise(2526),
    )
    assert leg_long.is_open()
    assert leg_long.gross_realized_pnl() == Paise(0)

    # Mark-to-market gain
    unrealized = leg_long.mark_unrealized_pnl(Paise(16000))  # ₹160.00 (+₹10.00 * 25 = +25,000 paise)
    assert unrealized == Paise(25000)
    assert leg_long.current_mark_paise == Paise(16000)

    # Close leg
    leg_long.close_leg(
        exit_price_paise=Paise(17000),  # ₹170.00 (+₹20.00 * 25 = +50,000 paise gross)
        exit_fees_paise=Paise(3139),
        exit_time=UtcEpochSec(200),
    )
    assert not leg_long.is_open()
    assert leg_long.status == LegStatus.CLOSED
    assert leg_long.gross_realized_pnl() == Paise(50000)
    assert leg_long.net_realized_pnl() == Paise(50000 - 2526 - 3139)  # 44,335 paise

    # 2. Short Leg
    c_short = _make_sample_contract(24200, OptionType.CE)
    leg_short = LegPosition(
        contract=c_short,
        side=OrderSide.SELL,
        qty=25,
        entry_price_paise=Paise(6000),  # ₹60.00
        entry_time=UtcEpochSec(100),
        entry_fees_paise=Paise(2573),
    )
    # Price drops to ₹50.00 -> Short makes money (+₹10.00 * 25 = +25,000 paise)
    unrealized_short = leg_short.mark_unrealized_pnl(Paise(5000))
    assert unrealized_short == Paise(25000)

    # Price rises to ₹70.00 at exit -> Short loses money (-₹10.00 * 25 = -25,000 paise gross)
    leg_short.close_leg(
        exit_price_paise=Paise(7000),
        exit_fees_paise=Paise(2460),
        exit_time=UtcEpochSec(200),
    )
    assert leg_short.gross_realized_pnl() == Paise(-25000)
    assert leg_short.net_realized_pnl() == Paise(-25000 - 2573 - 2460)  # -30,033 paise


@pytest.mark.gate_g2b
def test_position_group_combined_pnl_and_trailing() -> None:
    """
    1. The use of function:
       Tests multi-leg combined unrealized P&L, peak high-water mark, and trailing stop levels.

    2. How does the specific function work:
       - Configures Bull Call Spread with Long 24000 CE and Short 24200 CE.
       - Marks both legs and asserts combined unrealized P&L = Long P&L + Short P&L.
       - Verifies that peak_unrealized_pnl_paise tracks the maximum attained combined mark.
       - Verifies dynamic trailing stop calculation.

    3. Concepts used in the function:
       Group mark-to-market aggregation, high-water mark peak tracking.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Separate leg marks. After: Reconciled composite group valuation.
    """
    grp = PositionGroup(
        group_id="grp_spread_001",
        strategy_id="BULL_CALL_STRAT",
        intent=StrategyIntent.BULL_CALL_SPREAD,
        created_at=UtcEpochSec(100),
        group_trailing_stop_paise=Paise(50000),  # ₹500.00 trailing distance
    )

    leg1 = LegPosition(_make_sample_contract(24000, OptionType.CE), OrderSide.BUY, 25, Paise(15000), UtcEpochSec(100))
    leg2 = LegPosition(_make_sample_contract(24200, OptionType.CE), OrderSide.SELL, 25, Paise(6000), UtcEpochSec(100))

    grp.add_leg("leg1", leg1)
    grp.add_leg("leg2", leg2)

    # Initial mark: no movement -> combined = 0
    leg1.mark_unrealized_pnl(Paise(15000))
    leg2.mark_unrealized_pnl(Paise(6000))
    assert grp.calculate_combined_unrealized_pnl() == Paise(0)

    # Rally: Leg 1 rises to 20,000 (+5,000 * 25 = +125,000), Leg 2 rises to 8,000 (-2,000 * 25 = -50,000)
    # Net combined unrealized = +75,000 paise (₹750.00)
    leg1.mark_unrealized_pnl(Paise(20000))
    leg2.mark_unrealized_pnl(Paise(8000))
    combined = grp.calculate_combined_unrealized_pnl()
    assert combined == Paise(75000)
    assert grp.peak_unrealized_pnl_paise == Paise(75000)

    # Trailing stop trigger = peak (75,000) - trailing (50,000) = 25,000 paise
    assert grp.update_trailing_stops() == Paise(25000)

    # Pullback: Leg 1 falls to 18,000 (+75,000), Leg 2 falls to 7,000 (-25,000) -> Net = +50,000
    leg1.mark_unrealized_pnl(Paise(18000))
    leg2.mark_unrealized_pnl(Paise(7000))
    combined_after = grp.calculate_combined_unrealized_pnl()
    assert combined_after == Paise(50000)
    # Peak remains at 75,000 (high water mark)
    assert grp.peak_unrealized_pnl_paise == Paise(75000)
    assert grp.update_trailing_stops() == Paise(25000)


@pytest.mark.gate_g2b
def test_position_group_stale_mark_propagation() -> None:
    """
    1. The use of function:
       Tests the invariant that a single stale leg mark flags the entire PositionGroup mark as stale.

    2. How does the specific function work:
       - With 2 fresh legs, is_group_mark_stale() is False.
       - When Leg 2 has is_mark_stale = True, is_group_mark_stale() must be True.
       - When Leg 1 has current_mark_paise = None, is_group_mark_stale() must be True.

    3. Concepts used in the function:
       Stale data propagation invariant (QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §24).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Open legs. After: Verified fail-closed stale mark detection.
    """
    grp = PositionGroup("g_stale", "s", StrategyIntent.BULL_CALL_SPREAD, UtcEpochSec(100))
    leg1 = LegPosition(_make_sample_contract(24000, OptionType.CE), OrderSide.BUY, 25, Paise(15000), UtcEpochSec(100))
    leg2 = LegPosition(_make_sample_contract(24200, OptionType.CE), OrderSide.SELL, 25, Paise(6000), UtcEpochSec(100))
    grp.add_leg("leg1", leg1)
    grp.add_leg("leg2", leg2)

    # Initial state: marks not yet set -> stale
    assert grp.is_group_mark_stale()

    # Set fresh marks on both legs
    leg1.mark_unrealized_pnl(Paise(15000), is_stale=False)
    leg2.mark_unrealized_pnl(Paise(6000), is_stale=False)
    assert not grp.is_group_mark_stale()

    # Flag leg2 as stale
    leg2.mark_unrealized_pnl(Paise(6000), is_stale=True)
    assert grp.is_group_mark_stale()


@pytest.mark.gate_g2b
def test_margin_evaluator_fail_closed_guard() -> None:
    """
    1. The use of function:
       Tests the fail-closed margin guard for short options under REALISTIC_ACCOUNT vs THEORETICAL modes.

    2. How does the specific function work:
       - Evaluator in REALISTIC_ACCOUNT mode:
         * Long option order passes.
         * Short option order strictly raises RealisticMarginBlockedError with MARGIN_NOT_VERIFIED.
       - Evaluator in THEORETICAL mode:
         * Short option order passes without error.
       - Group safety: multi-leg spread with a short leg raises error in REALISTIC_ACCOUNT mode.

    3. Concepts used in the function:
       SEBI clearing member margin verification guard, fail-closed pre-trade safety (Tasks M4-14, M4-17).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Proposed orders. After: Verified hard block on unverified short options.
    """
    # 1. Realistic Mode (Unverified) -> Fail-Closed Block
    realistic_eval = MarginEvaluator(mode=MarginMode.REALISTIC_ACCOUNT, is_verified=False)

    # Long option is permitted (buyer risk capped at debit)
    realistic_eval.validate_order_safety(side=OrderSide.BUY, is_option=True)

    # Short option MUST be blocked
    with pytest.raises(RealisticMarginBlockedError) as exc_info:
        realistic_eval.validate_order_safety(side=OrderSide.SELL, is_option=True)
    assert "MARGIN_NOT_VERIFIED" in str(exc_info.value)
    assert exc_info.value.error_code == "MARGIN_NOT_VERIFIED"

    # Multi-leg group with a short leg MUST fail closed
    spread_legs = [(OrderSide.BUY, True), (OrderSide.SELL, True)]
    with pytest.raises(RealisticMarginBlockedError):
        realistic_eval.validate_group_safety(spread_legs)

    # 2. Theoretical Mode -> Permitted with audit label
    theoretical_eval = MarginEvaluator(mode=MarginMode.THEORETICAL)
    # Both long and short pass
    theoretical_eval.validate_order_safety(side=OrderSide.BUY, is_option=True)
    theoretical_eval.validate_order_safety(side=OrderSide.SELL, is_option=True)
    theoretical_eval.validate_group_safety(spread_legs)

    # Status check
    status = theoretical_eval.get_margin_status()
    assert status["margin_mode"] == "THEORETICAL"
    assert status["is_verified"] is False
    assert status["audit_label"] == "MARGIN_NOT_VERIFIED"
