"""
1. What this file does:
   Defines comprehensive unit tests for the LeggingSequencer, multi-leg execution ordering,
   3x adverse tick slippage emergency unwind recovery, and session boundaries (Task M4-16).

2. Overall design:
   Enforces acceptance contracts for Gate G2b per DOCS/AGENTS.md §5 and QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §24:
     - Tests SEBI margin-optimal entry sequencing (long protective leg first, short financing second).
     - Tests entry cutoff boundary at 15:00 IST (rejects late intents).
     - Tests emergency unwind recovery on Leg 2 failure with 3x adverse tick slippage multiplier.
     - Tests margin-optimal exit ordering (short legs closed before long protective legs).
     - Tests group-level stop-loss, take-profit, trailing stop, and 15:25 force-flat exits.
     - Tests stale mark deferral: degraded data does not trigger false stops or targets.
     - Tests volume exceeded warnings on orders exceeding candle volume.
     - Tests 15:29 session close EOD close fill and fail-closed HALTED_UNRESOLVED on missing data.

3. Elements in the file:
   - Helper fixtures for contracts and sample groups.
   - 11 unit test functions testing sequencing, unwinds, stops, volume warnings, and session boundaries.

4. Final output of the file:
   - Executable pytest suite marked with @pytest.mark.gate_g2b.
"""

from datetime import date

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
    SequencingDirective,
)


def _sample_contract(strike: int, option_type: OptionType) -> ContractIdentifier:
    """Helper to generate sample contract identifier."""
    return ContractIdentifier(
        instrument_key=f"NSE_FO|NIFTY|{strike}|{option_type.value}",
        trading_symbol=f"NIFTY {strike} {option_type.value}",
        expiry_date="2025-01-09",
        strike_price=float(strike),
        option_type=option_type,
        lot_size=25,
    )


@pytest.mark.gate_g2b
def test_sequencer_spread_entry_ordering() -> None:
    """
    1. The use of function:
       Tests SEBI margin-optimal entry sequencing for a 2-leg vertical spread.

    2. How does the specific function work:
       - Creates Bull Call Spread intent at 10:00 IST.
       - Advances Step 1: verifies QUEUE_LEG_1 directive (target leg_1, slippage 1x).
       - Fills Leg 1 and transitions to LEG_1_FILLED.
       - Advances Step 2: verifies QUEUE_LEG_2 directive (target leg_2, slippage 1x).
       - Fills Leg 2 and transitions to GROUP_OPEN.

    3. Concepts used in the function:
       Sequential multi-leg execution ordering avoiding unhedged short margin spikes.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Raw intent. After: Sequenced order directives culminating in GROUP_OPEN.
    """
    sequencer = LeggingSequencer()
    grp = sequencer.create_position_group(
        group_id="grp_spread_001",
        strategy_id="BULL_CALL",
        intent=StrategyIntent.BULL_CALL_SPREAD,
        created_at=UtcEpochSec(100),
        current_time_ist="10:00",
    )
    assert grp is not None
    assert grp.state == LeggingState.INTENT_CREATED

    # 1. First directive: Queue Leg 1
    d1 = sequencer.sequence_entry("grp_spread_001")
    assert d1.action == SequencerActionType.QUEUE_LEG_1
    assert d1.target_leg_key == "leg_1"
    assert d1.slippage_multiplier == 1
    assert grp.state == LeggingState.LEG_1_QUEUED

    # Simulate Leg 1 fill
    leg1 = LegPosition(_sample_contract(24000, OptionType.CE), OrderSide.BUY, 25, Paise(15000), UtcEpochSec(101))
    grp.add_leg("leg_1", leg1)
    grp.transition_to(LeggingState.LEG_1_FILLED)

    # 2. Second directive: Queue Leg 2
    d2 = sequencer.sequence_entry("grp_spread_001")
    assert d2.action == SequencerActionType.QUEUE_LEG_2
    assert d2.target_leg_key == "leg_2"
    assert d2.slippage_multiplier == 1
    assert grp.state == LeggingState.LEG_2_QUEUED

    # Simulate Leg 2 fill
    leg2 = LegPosition(_sample_contract(24200, OptionType.CE), OrderSide.SELL, 25, Paise(6000), UtcEpochSec(102))
    grp.add_leg("leg_2", leg2)
    grp.transition_to(LeggingState.GROUP_OPEN)
    assert grp.state == LeggingState.GROUP_OPEN


@pytest.mark.gate_g2b
def test_sequencer_single_leg_entry_ordering() -> None:
    """
    1. The use of function:
       Tests that single-leg structures transition directly to GROUP_OPEN after Leg 1 fill.

    2. How does the specific function work:
       - Creates single-leg long intent.
       - Advances entry: emits QUEUE_LEG_1.
       - Simulates Leg 1 fill, transitions to LEG_1_FILLED.
       - Advances entry: sequencer recognizes 1-leg intent, transitions directly to GROUP_OPEN.

    3. Concepts used in the function:
       Single-leg vs multi-leg intent branching.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Single-leg group. After: Active GROUP_OPEN state.
    """
    sequencer = LeggingSequencer()
    grp = sequencer.create_position_group(
        group_id="grp_single_001",
        strategy_id="SINGLE_LONG",
        intent=StrategyIntent.SINGLE_LEG_LONG,
        created_at=UtcEpochSec(100),
        current_time_ist="10:00",
    )
    assert grp is not None
    d1 = sequencer.sequence_entry("grp_single_001")
    assert d1.action == SequencerActionType.QUEUE_LEG_1

    leg1 = LegPosition(_sample_contract(24000, OptionType.CE), OrderSide.BUY, 25, Paise(15000), UtcEpochSec(101))
    grp.add_leg("leg_1", leg1)
    grp.transition_to(LeggingState.LEG_1_FILLED)

    d2 = sequencer.sequence_entry("grp_single_001")
    assert d2.action == SequencerActionType.NO_ACTION
    assert grp.state == LeggingState.GROUP_OPEN


@pytest.mark.gate_g2b
def test_sequencer_entry_cutoff_at_1500() -> None:
    """
    1. The use of function:
       Tests hard rejection of new position group intents after 15:00 IST.

    2. How does the specific function work:
       - Attempts to create group intent at '15:01' IST.
       - Returns None and records REJECTED_PAST_ENTRY_CUTOFF warning.

    3. Concepts used in the function:
       Intraday cutoff window invariant (Stage 4 Plan §4).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Proposed late intent. After: None returned and warning emitted.
    """
    sequencer = LeggingSequencer()
    grp = sequencer.create_position_group(
        group_id="grp_late",
        strategy_id="STRAT",
        intent=StrategyIntent.BULL_CALL_SPREAD,
        created_at=UtcEpochSec(100),
        current_time_ist="15:01",
    )
    assert grp is None
    assert any("REJECTED_PAST_ENTRY_CUTOFF" in w for w in sequencer.warnings)


@pytest.mark.gate_g2b
def test_sequencer_leg_2_rejection_unwind_recovery() -> None:
    """
    1. The use of function:
       Tests emergency unwind recovery when Leg 2 fails with 3x adverse tick slippage.

    2. How does the specific function work:
       - Sets up group in LEG_2_QUEUED with Leg 1 filled.
       - Calls handle_leg_2_rejection with reason 'REJECTED_STRIKE_NOT_FOUND'.
       - Asserts directive action is TRIGGER_UNWIND, target is 'leg_1', slippage multiplier is 3.
       - Asserts group state is UNWIND_QUEUED.
       - Completes unwind: confirms Leg 1 status is UNWOUND and group state is UNWOUND.

    3. Concepts used in the function:
       Legging failure recovery contract with 3x adverse slippage (Stage 4 Plan §5).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Failed Leg 2. After: Reconciled UNWOUND terminal state.
    """
    sequencer = LeggingSequencer()
    grp = sequencer.create_position_group(
        group_id="grp_unwind_test",
        strategy_id="BULL_CALL",
        intent=StrategyIntent.BULL_CALL_SPREAD,
        created_at=UtcEpochSec(100),
        current_time_ist="10:00",
    )
    assert grp is not None
    grp.transition_to(LeggingState.LEG_1_QUEUED)
    leg1 = LegPosition(_sample_contract(24000, OptionType.CE), OrderSide.BUY, 25, Paise(15000), UtcEpochSec(101))
    grp.add_leg("leg_1", leg1)
    grp.transition_to(LeggingState.LEG_1_FILLED)
    grp.transition_to(LeggingState.LEG_2_QUEUED)

    # Leg 2 fails
    directive = sequencer.handle_leg_2_rejection("grp_unwind_test", reason="REJECTED_STRIKE_NOT_FOUND")
    assert directive.action == SequencerActionType.TRIGGER_UNWIND
    assert directive.target_leg_key == "leg_1"
    assert directive.slippage_multiplier == 3
    assert grp.state == LeggingState.UNWIND_QUEUED

    # Finalize unwind fill at 14,980 paise with 2,890 paise fee
    sequencer.confirm_unwind_completed(
        group_id="grp_unwind_test",
        exit_price_paise=Paise(14980),
        exit_fees_paise=Paise(2890),
        exit_time=UtcEpochSec(103),
    )
    assert grp.state == LeggingState.UNWOUND
    assert grp.is_terminal()
    assert leg1.status == LegStatus.UNWOUND
    assert leg1.exit_price_paise == Paise(14980)


@pytest.mark.gate_g2b
def test_sequencer_group_exits_short_before_long() -> None:
    """
    1. The use of function:
       Verifies that coordinated group exits order short option legs first before long legs.

    2. How does the specific function work:
       - Configures spread with Long Call and Short Call.
       - Calls get_exit_order_sequence().
       - Asserts that Short Call is first in list and Long Call is second.

    3. Concepts used in the function:
       SEBI margin optimal exit ordering (short liability eliminated first).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Unordered legs. After: Verified short-first exit priority.
    """
    sequencer = LeggingSequencer()
    grp = sequencer.create_position_group(
        group_id="grp_exit_priority",
        strategy_id="BULL_CALL",
        intent=StrategyIntent.BULL_CALL_SPREAD,
        created_at=UtcEpochSec(100),
        current_time_ist="10:00",
    )
    assert grp is not None
    leg_long = LegPosition(_sample_contract(24000, OptionType.CE), OrderSide.BUY, 25, Paise(15000), UtcEpochSec(100))
    leg_short = LegPosition(_sample_contract(24200, OptionType.CE), OrderSide.SELL, 25, Paise(6000), UtcEpochSec(100))

    # Add in arbitrary order (long first)
    grp.add_leg("long_leg", leg_long)
    grp.add_leg("short_leg", leg_short)

    ordered = sequencer.get_exit_order_sequence("grp_exit_priority")
    assert len(ordered) == 2
    assert ordered[0][0] == "short_leg"
    assert ordered[0][1].side == OrderSide.SELL
    assert ordered[1][0] == "long_leg"
    assert ordered[1][1].side == OrderSide.BUY


@pytest.mark.gate_g2b
def test_sequencer_group_stop_loss_trigger() -> None:
    """
    1. The use of function:
       Tests that group stop-loss triggers QUEUE_COORDINATED_EXIT when combined loss exceeds limit.

    2. How does the specific function work:
       - Configures Bull Call Spread with group stop loss at -100,000 paise (-₹1,000.00).
       - Updates marks such that combined loss is -125,000 paise.
       - Evaluates exits: asserts QUEUE_COORDINATED_EXIT is emitted.

    3. Concepts used in the function:
       Group-level stop loss risk enforcement (ENGINE §14).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Breached stop threshold. After: Emitted QUEUE_COORDINATED_EXIT directive.
    """
    sequencer = LeggingSequencer()
    grp = sequencer.create_position_group(
        group_id="grp_stop_test",
        strategy_id="BULL_CALL",
        intent=StrategyIntent.BULL_CALL_SPREAD,
        created_at=UtcEpochSec(100),
        current_time_ist="10:00",
        group_stop_loss_paise=Paise(-100000),
    )
    assert grp is not None
    grp.state = LeggingState.GROUP_OPEN

    leg1 = LegPosition(_sample_contract(24000, OptionType.CE), OrderSide.BUY, 25, Paise(15000), UtcEpochSec(100))
    leg2 = LegPosition(_sample_contract(24200, OptionType.CE), OrderSide.SELL, 25, Paise(6000), UtcEpochSec(100))
    grp.add_leg("leg_1", leg1)
    grp.add_leg("leg_2", leg2)

    # Leg 1 falls by 6,000 paise (-150,000 paise loss), Leg 2 falls by 1,000 paise (+25,000 gain)
    # Net combined P&L = -125,000 paise (<= -100,000 paise stop)
    leg1.mark_unrealized_pnl(Paise(9000), is_stale=False)
    leg2.mark_unrealized_pnl(Paise(5000), is_stale=False)

    directive = sequencer.evaluate_group_risk_and_exits("grp_stop_test", current_time_ist="11:30")
    assert directive.action == SequencerActionType.QUEUE_COORDINATED_EXIT
    assert "Group Stop-Loss triggered" in directive.reason


@pytest.mark.gate_g2b
def test_sequencer_group_take_profit_trigger() -> None:
    """
    1. The use of function:
       Tests that group take-profit triggers QUEUE_COORDINATED_EXIT when target is achieved.

    2. How does the specific function work:
       - Configures spread with take-profit at +200,000 paise (+₹2,000.00).
       - Marks legs such that combined unrealized P&L is +225,000 paise.
       - Asserts QUEUE_COORDINATED_EXIT directive is emitted.

    3. Concepts used in the function:
       Group-level take profit target enforcement (ENGINE §14).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Achieved profit target. After: Emitted QUEUE_COORDINATED_EXIT directive.
    """
    sequencer = LeggingSequencer()
    grp = sequencer.create_position_group(
        group_id="grp_tp_test",
        strategy_id="BULL_CALL",
        intent=StrategyIntent.BULL_CALL_SPREAD,
        created_at=UtcEpochSec(100),
        current_time_ist="10:00",
        group_take_profit_paise=Paise(200000),
    )
    assert grp is not None
    grp.state = LeggingState.GROUP_OPEN

    leg1 = LegPosition(_sample_contract(24000, OptionType.CE), OrderSide.BUY, 25, Paise(15000), UtcEpochSec(100))
    leg2 = LegPosition(_sample_contract(24200, OptionType.CE), OrderSide.SELL, 25, Paise(6000), UtcEpochSec(100))
    grp.add_leg("leg_1", leg1)
    grp.add_leg("leg_2", leg2)

    # Leg 1 rises to 25,000 (+10,000 * 25 = +250,000), Leg 2 rises to 7,000 (-1,000 * 25 = -25,000)
    # Net combined P&L = +225,000 paise (>= +200,000 paise target)
    leg1.mark_unrealized_pnl(Paise(25000), is_stale=False)
    leg2.mark_unrealized_pnl(Paise(7000), is_stale=False)

    directive = sequencer.evaluate_group_risk_and_exits("grp_tp_test", current_time_ist="12:00")
    assert directive.action == SequencerActionType.QUEUE_COORDINATED_EXIT
    assert "Group Take-Profit triggered" in directive.reason


@pytest.mark.gate_g2b
def test_sequencer_stale_mark_defers_stops() -> None:
    """
    1. The use of function:
       Tests invariant that degraded/stale data defers stop/target checks without triggering false exits.

    2. How does the specific function work:
       - Configures spread with stop loss at -100,000 paise.
       - Marks Leg 1 as stale (is_mark_stale=True).
       - Evaluates exits: asserts NO_ACTION is returned with reason citing stale data.

    3. Concepts used in the function:
       Degraded data invariant (ENGINE §24): missing/stale leg marks defer stop/target evaluation.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Stale leg mark. After: Deferred evaluation (NO_ACTION).
    """
    sequencer = LeggingSequencer()
    grp = sequencer.create_position_group(
        group_id="grp_stale_stop",
        strategy_id="BULL_CALL",
        intent=StrategyIntent.BULL_CALL_SPREAD,
        created_at=UtcEpochSec(100),
        current_time_ist="10:00",
        group_stop_loss_paise=Paise(-100000),
    )
    assert grp is not None
    grp.state = LeggingState.GROUP_OPEN

    leg1 = LegPosition(_sample_contract(24000, OptionType.CE), OrderSide.BUY, 25, Paise(15000), UtcEpochSec(100))
    leg2 = LegPosition(_sample_contract(24200, OptionType.CE), OrderSide.SELL, 25, Paise(6000), UtcEpochSec(100))
    grp.add_leg("leg_1", leg1)
    grp.add_leg("leg_2", leg2)

    leg1.mark_unrealized_pnl(Paise(8000), is_stale=True)  # Marked stale!
    leg2.mark_unrealized_pnl(Paise(5000), is_stale=False)

    directive = sequencer.evaluate_group_risk_and_exits("grp_stale_stop", current_time_ist="11:30")
    assert directive.action == SequencerActionType.NO_ACTION
    assert "Stale or missing leg mark detected" in directive.reason


@pytest.mark.gate_g2b
def test_sequencer_1525_force_flat_trigger() -> None:
    """
    1. The use of function:
       Tests that mandatory force-flat triggers at 15:25 IST regardless of P&L or marks.

    2. How does the specific function work:
       - Evaluates active group at current_time_ist = '15:25'.
       - Asserts QUEUE_COORDINATED_EXIT directive is emitted.

    3. Concepts used in the function:
       Intraday causal force-flat boundary (Stage 4 Plan §4).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Active group at 15:25. After: Coordinated exit directive emitted.
    """
    sequencer = LeggingSequencer()
    grp = sequencer.create_position_group(
        group_id="grp_ff_test",
        strategy_id="BULL_CALL",
        intent=StrategyIntent.BULL_CALL_SPREAD,
        created_at=UtcEpochSec(100),
        current_time_ist="10:00",
    )
    assert grp is not None
    grp.state = LeggingState.GROUP_OPEN

    directive = sequencer.evaluate_group_risk_and_exits("grp_ff_test", current_time_ist="15:25")
    assert directive.action == SequencerActionType.QUEUE_COORDINATED_EXIT
    assert "Mandatory intraday force-flat triggered" in directive.reason


@pytest.mark.gate_g2b
def test_sequencer_volume_exceeded_warning() -> None:
    """
    1. The use of function:
       Tests volume warning guard when order quantity exceeds candle volume.

    2. How does the specific function work:
       - Checks order qty 500 against candle volume 200: asserts warning emitted.
       - Checks order qty 100 against candle volume 200: asserts no warning (None).

    3. Concepts used in the function:
       Volume warning requirement (ENGINE §24): partial fills deferred; warn on large orders.

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Order sizes. After: Verified warning emission behavior.
    """
    sequencer = LeggingSequencer()
    w1 = sequencer.check_volume_warning(order_qty=500, bar_volume=200, instrument_key="NIFTY24000CE")
    assert w1 is not None
    assert "VOLUME_EXCEEDED_WARNING" in w1
    assert any("VOLUME_EXCEEDED_WARNING" in item for item in sequencer.warnings)

    w2 = sequencer.check_volume_warning(order_qty=100, bar_volume=200, instrument_key="NIFTY24000CE")
    assert w2 is None


@pytest.mark.gate_g2b
def test_sequencer_session_boundary_eod_fill_vs_halted() -> None:
    """
    1. The use of function:
       Tests final 15:29:00 session bar boundary contracts: EOD fill with 2x slippage vs HALTED_UNRESOLVED on missing data.

    2. How does the specific function work:
       - With data present: emits EXECUTE_EOD_FILL with slippage multiplier 2.
       - With missing data: transitions group to HALTED_UNRESOLVED and emits HALT_UNRESOLVED.

    3. Concepts used in the function:
       Final bar EOD close fill vs fail-closed missing data halt (Stage 4 Plan §4).

    4. Places where this function is imported and used:
       Executed by pytest runner for Gate G2b verification.

    5. Final output of the function, before and after:
       Before: Group at session close. After: Verified EOD close fill vs fail-closed halt.
    """
    sequencer = LeggingSequencer()

    # Case 1: Final bar close with valid data -> EXECUTE_EOD_FILL
    grp1 = sequencer.create_position_group("grp_eod_ok", "s", StrategyIntent.BULL_CALL_SPREAD, UtcEpochSec(100), "10:00")
    assert grp1 is not None
    grp1.state = LeggingState.GROUP_OPEN
    d1 = sequencer.handle_session_boundary("grp_eod_ok", is_final_bar_close=True, has_missing_data=False)
    assert d1.action == SequencerActionType.EXECUTE_EOD_FILL
    assert d1.slippage_multiplier == 2

    # Case 2: Final bar close with missing data -> HALT_UNRESOLVED
    grp2 = sequencer.create_position_group("grp_eod_missing", "s", StrategyIntent.BULL_CALL_SPREAD, UtcEpochSec(100), "10:00")
    assert grp2 is not None
    grp2.state = LeggingState.GROUP_OPEN
    d2 = sequencer.handle_session_boundary("grp_eod_missing", is_final_bar_close=True, has_missing_data=True)
    assert d2.action == SequencerActionType.HALT_UNRESOLVED
    assert grp2.state == LeggingState.HALTED_UNRESOLVED
    assert grp2.is_terminal()
