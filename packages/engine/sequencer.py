"""
1. What this file does:
   Implements the LeggingSequencer, multi-leg execution ordering, volume warning guards,
   and 3x adverse tick slippage emergency unwind recovery engine for QuantView (Task M4-16).

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §14, §15, §16, §24 and QUANTVIEW_DATA_SPEC §2.1:
     - SEBI Margin-Optimal Entry Sequencing: Long hedge legs are queued and filled first (Bar t+1 Open);
       short risk legs queue only after confirmed long fill (Bar t+2 Open).
     - Margin-Optimal Exit Sequencing: Short legs exit first (buy-to-close) before selling long protective legs.
     - Deterministic Unwind Recovery: If Leg 2 is rejected or fails, Leg 1 is unwound at next bar open with
       3x adverse tick slippage penalty (15 paise), transitioning to UNWOUND.
     - Volume Exceeded Warnings: Emits VOLUME_EXCEEDED_WARNING when order quantity exceeds candle volume (no partial fills).
     - Session Cutoff Boundaries: Entries strictly blocked after 15:00 IST; force-flat at 15:25 IST;
       last recovery bar 15:29 Open; 15:29 Close executes EOD_CLOSE_FILL or transitions to HALTED_UNRESOLVED if data is missing.

3. Elements in the file:
   - SequencerActionType: Enumeration of sequencer action directives.
   - SequencingDirective: Immutable container specifying next execution action and leg target.
   - LeggingSequencer: Core multi-leg state progression, exit coordination, and recovery engine.

4. Final output of the file:
   - Exported SequencerActionType, SequencingDirective, and LeggingSequencer classes.
"""

from enum import Enum
from typing import Dict, List, NamedTuple, Optional, Tuple, Union

from packages.domain import (
    ContractIdentifier,
    OrderSide,
    Paise,
    TickQuantizer,
    UtcEpochSec,
)
from packages.engine.clock import SimulationMinute
from packages.engine.groups import (
    InvalidLeggingTransitionError,
    LegPosition,
    LegStatus,
    LeggingState,
    PositionGroup,
    StrategyIntent,
)


class SequencerActionType(str, Enum):
    """
    1. The use of class:
       Enumeration of discrete order actions emitted by the LeggingSequencer.

    2. What the class contains:
       - QUEUE_LEG_1: Queue first declared leg order for next bar open.
       - QUEUE_LEG_2: Queue second declared leg order for next bar open.
       - TRIGGER_UNWIND: Queue emergency market exit for Leg 1 with 3x adverse slippage.
       - QUEUE_COORDINATED_EXIT: Queue exit orders for active group legs (short first, then long).
       - EXECUTE_EOD_FILL: Execute terminal 15:29 candle close fill.
       - HALT_UNRESOLVED: Mark group as HALTED_UNRESOLVED due to missing data or expired recovery window.
       - NO_ACTION: No sequencer action required for this bar.

    3. Technologies used and why:
       String Enum for clean serialization and diagnostic logging.

    4. Key design and overall design of the class:
       Standardizes instructions passed from sequencer to fill engine and order router.
    """
    QUEUE_LEG_1 = "QUEUE_LEG_1"
    QUEUE_LEG_2 = "QUEUE_LEG_2"
    TRIGGER_UNWIND = "TRIGGER_UNWIND"
    QUEUE_COORDINATED_EXIT = "QUEUE_COORDINATED_EXIT"
    EXECUTE_EOD_FILL = "EXECUTE_EOD_FILL"
    HALT_UNRESOLVED = "HALT_UNRESOLVED"
    NO_ACTION = "NO_ACTION"


class SequencingDirective(NamedTuple):
    """
    1. The use of class:
       Immutable container describing the action directed by the sequencer for a PositionGroup.

    2. What the class contains:
       - action: SequencerActionType.
       - group_id: Unique string ID of target PositionGroup.
       - target_leg_key: Key of specific leg targeted by action (or None for group actions).
       - slippage_multiplier: Adverse slippage multiplier (1 for normal, 3 for unwind, 2 for EOD close).
       - reason: Diagnostic string explanation of the directive.

    3. Technologies used and why:
       NamedTuple for fast immutable message passing between engine layers.

    4. Key design and overall design of the class:
       Separates execution sequencing decisions from direct order queue mutations.
    """
    action: SequencerActionType
    group_id: str
    target_leg_key: Optional[str]
    slippage_multiplier: int
    reason: str


class LeggingSequencer:
    """
    1. The use of class:
       Coordinates multi-leg order progression, unwind recovery, volume warnings, and session cutoffs per ENGINE §24.

    2. What the class contains:
       - groups: In-memory registry of active and historical PositionGroup instances.
       - default_slippage_paise: Standard adverse slippage in integer Paise (default 5 paise).
       - tick_paise: Minimum tick size in integer Paise (default 5 paise).
       - last_entry_time_ist: Cutoff time string after which new entries are blocked ('15:00').
       - force_flat_time_ist: Cutoff time string triggering mandatory intraday exits ('15:25').
       - warnings: List of emitted warning strings (e.g. VOLUME_EXCEEDED_WARNING).
       - create_position_group(): Validates timing and registers new PositionGroup.
       - sequence_next_action(): Determines next causal action for a group.
       - handle_leg_2_rejection(): Enforces emergency unwind state transition with 3x slippage.
       - evaluate_group_exits(): Checks stops, targets, trailing stops, and force-flat boundaries.
       - check_volume_warning(): Emits volume warning if order size exceeds candle volume.

    3. Technologies used and why:
       Pure Python state coordinator with exact integer Paise math and deterministic clock checks.

    4. Key design and overall design of the class:
       Eliminates legging race conditions, guarantees SEBI margin optimal sequencing, and prevents orphaned legs.
    """

    def __init__(
        self,
        default_slippage_paise: int = 5,
        tick_paise: int = 5,
        last_entry_time_ist: str = "15:00",
        force_flat_time_ist: str = "15:25",
    ) -> None:
        self.groups: Dict[str, PositionGroup] = {}
        self.default_slippage_paise = default_slippage_paise
        self.tick_paise = tick_paise
        self.last_entry_time_ist = last_entry_time_ist
        self.force_flat_time_ist = force_flat_time_ist
        self.warnings: List[str] = []

    def create_position_group(
        self,
        group_id: str,
        strategy_id: str,
        intent: StrategyIntent,
        created_at: UtcEpochSec,
        current_time_ist: str,
        group_stop_loss_paise: Optional[Paise] = None,
        group_take_profit_paise: Optional[Paise] = None,
        group_trailing_stop_paise: Optional[Paise] = None,
    ) -> Optional[PositionGroup]:
        """
        1. The use of function:
           Creates and registers a new PositionGroup if within permitted entry timing windows.

        2. How does the specific function work:
           - Checks if current_time_ist exceeds last_entry_time_ist (15:00 IST).
           - If after 15:00 IST, rejects intent and logs warning (returns None).
           - Otherwise, instantiates PositionGroup in INTENT_CREATED state and registers in self.groups.

        3. Concepts used in the function:
           Intraday trading window enforcement, late-day legging race prevention (Stage 4 Plan §4).

        4. Places where this function is imported and used:
           Used by Strategy Runner when multi-leg signal triggers.

        5. Final output of the function, before and after:
           Before: Strategy signal intent. After: Registered PositionGroup or None if rejected by cutoff.
        """
        if current_time_ist > self.last_entry_time_ist:
            self.warnings.append(
                f"REJECTED_PAST_ENTRY_CUTOFF: Group intent {group_id} at {current_time_ist} IST exceeds entry cutoff {self.last_entry_time_ist}."
            )
            return None

        group = PositionGroup(
            group_id=group_id,
            strategy_id=strategy_id,
            intent=intent,
            created_at=created_at,
            group_stop_loss_paise=group_stop_loss_paise,
            group_take_profit_paise=group_take_profit_paise,
            group_trailing_stop_paise=group_trailing_stop_paise,
        )
        self.groups[group_id] = group
        return group

    def sequence_entry(self, group_id: str) -> SequencingDirective:
        """
        1. The use of function:
           Determines the next sequential entry order directive based on current group legging state.

        2. How does the specific function work:
           - If INTENT_CREATED: transitions to LEG_1_QUEUED, returns QUEUE_LEG_1 directive (1x slippage).
           - If LEG_1_FILLED:
             * For multi-leg spread/straddle/strangle: transitions to LEG_2_QUEUED, returns QUEUE_LEG_2.
             * For single-leg: transitions directly to GROUP_OPEN, returns NO_ACTION.
           - For all other states, returns NO_ACTION.

        3. Concepts used in the function:
           SEBI margin optimal sequencing (long protective leg first, short financing leg second).

        4. Places where this function is imported and used:
           Used by BacktestRunner at bar close (decision time) to schedule orders for next bar open.

        5. Final output of the function, before and after:
           Before: Current group state. After: Advanced group state and returned SequencingDirective.
        """
        group = self.groups[group_id]

        if group.state == LeggingState.INTENT_CREATED:
            group.transition_to(LeggingState.LEG_1_QUEUED)
            return SequencingDirective(
                action=SequencerActionType.QUEUE_LEG_1,
                group_id=group_id,
                target_leg_key="leg_1",
                slippage_multiplier=1,
                reason="Queueing Leg 1 entry order for next bar open.",
            )

        elif group.state == LeggingState.LEG_1_FILLED:
            if group.intent in (
                StrategyIntent.BULL_CALL_SPREAD,
                StrategyIntent.BEAR_PUT_SPREAD,
                StrategyIntent.LONG_STRADDLE,
                StrategyIntent.SHORT_STRANGLE,
                StrategyIntent.LONG_STRANGLE,
                StrategyIntent.IRON_CONDOR,
            ):
                group.transition_to(LeggingState.LEG_2_QUEUED)
                return SequencingDirective(
                    action=SequencerActionType.QUEUE_LEG_2,
                    group_id=group_id,
                    target_leg_key="leg_2",
                    slippage_multiplier=1,
                    reason="Leg 1 confirmed filled. Queueing Leg 2 entry order for next bar open.",
                )
            else:
                # Single leg structure
                group.transition_to(LeggingState.GROUP_OPEN)
                return SequencingDirective(
                    action=SequencerActionType.NO_ACTION,
                    group_id=group_id,
                    target_leg_key=None,
                    slippage_multiplier=1,
                    reason="Single leg filled. Group is now active.",
                )

        return SequencingDirective(
            action=SequencerActionType.NO_ACTION,
            group_id=group_id,
            target_leg_key=None,
            slippage_multiplier=1,
            reason="No entry sequencing required.",
        )

    def handle_leg_2_rejection(self, group_id: str, reason: str = "REJECTED_STRIKE_NOT_FOUND") -> SequencingDirective:
        """
        1. The use of function:
           Handles failure of Leg 2 fill by triggering an emergency unwind recovery of Leg 1.

        2. How does the specific function work:
           - Transitions PositionGroup: LEG_2_QUEUED -> LEG_2_REJECTED -> UNWIND_QUEUED.
           - Emits TRIGGER_UNWIND directive targeting leg_1 with 3x adverse tick slippage multiplier.
           - Appends diagnostic warning.

        3. Concepts used in the function:
           Deterministic legging recovery contract with 3x penalty slippage (Stage 4 Plan §5).

        4. Places where this function is imported and used:
           Used by IntrabarFillEngine when second leg cannot fill due to missing strike or margin rejection.

        5. Final output of the function, before and after:
           Before: Failed Leg 2 state. After: Group in UNWIND_QUEUED and directive to unwind Leg 1 with 3x slippage.
        """
        group = self.groups[group_id]
        group.transition_to(LeggingState.LEG_2_REJECTED)
        group.transition_to(LeggingState.UNWIND_QUEUED)

        warning_msg = f"LEGGING_FAILURE_UNWIND_TRIGGERED: Group {group_id} Leg 2 rejected ({reason}). Queuing Leg 1 emergency unwind with 3x adverse slippage."
        self.warnings.append(warning_msg)

        return SequencingDirective(
            action=SequencerActionType.TRIGGER_UNWIND,
            group_id=group_id,
            target_leg_key="leg_1",
            slippage_multiplier=3,
            reason=f"Emergency unwind triggered due to Leg 2 rejection: {reason}",
        )

    def confirm_unwind_completed(
        self,
        group_id: str,
        exit_price_paise: Paise,
        exit_fees_paise: Paise,
        exit_time: UtcEpochSec,
    ) -> None:
        """
        1. The use of function:
           Finalizes the emergency unwind sequence and closes the group in the UNWOUND state.

        2. How does the specific function work:
           - Retrieves Leg 1 from group.legs.
           - Invokes leg.close_leg with is_unwind=True.
           - Transitions group to UNWOUND (terminal).

        3. Concepts used in the function:
           Terminal recovery state finalization.

        4. Places where this function is imported and used:
           Used by fill engine when the emergency unwind order fills at next bar open.

        5. Final output of the function, before and after:
           Before: Group in UNWIND_QUEUED. After: Leg 1 UNWOUND and group in UNWOUND.
        """
        group = self.groups[group_id]
        if "leg_1" in group.legs:
            group.legs["leg_1"].close_leg(
                exit_price_paise=exit_price_paise,
                exit_fees_paise=exit_fees_paise,
                exit_time=exit_time,
                is_unwind=True,
            )
        group.transition_to(LeggingState.UNWOUND)

    def evaluate_group_risk_and_exits(
        self,
        group_id: str,
        current_time_ist: str,
    ) -> SequencingDirective:
        """
        1. The use of function:
           Evaluates group-level stops, targets, trailing stops, and 15:25 force-flat boundaries.

        2. How does the specific function work:
           - If group is not in GROUP_OPEN, returns NO_ACTION.
           - Checks if group mark is stale (is_group_mark_stale()); if stale, skips stop/target checks.
           - Calculates combined unrealized P&L.
           - Checks group stop loss: if combined P&L <= group_stop_loss_paise, triggers coordinated exit.
           - Checks group take profit: if combined P&L >= group_take_profit_paise, triggers coordinated exit.
           - Checks trailing stop: if trailing stop active and combined P&L <= trailing trigger, triggers coordinated exit.
           - Checks force-flat: if current_time_ist >= force_flat_time_ist (15:25), triggers coordinated exit.
           - Orders exits: Short legs first (buy-to-close), Long legs second (sell-to-close).

        3. Concepts used in the function:
           Group-level risk controls, coordinated exit sequencing, SEBI margin-optimal exit ordering.

        4. Places where this function is imported and used:
           Used by IntrabarFillEngine in Step 2 and Step 3 loops.

        5. Final output of the function, before and after:
           Before: Unchecked group risk. After: Returned SequencingDirective (QUEUE_COORDINATED_EXIT or NO_ACTION).
        """
        group = self.groups[group_id]
        if group.state != LeggingState.GROUP_OPEN:
            return SequencingDirective(
                action=SequencerActionType.NO_ACTION,
                group_id=group_id,
                target_leg_key=None,
                slippage_multiplier=1,
                reason="Group is not active in GROUP_OPEN state.",
            )

        # 1. 15:25 Force-Flat Check (highest priority at/after force-flat boundary)
        if current_time_ist >= self.force_flat_time_ist:
            return SequencingDirective(
                action=SequencerActionType.QUEUE_COORDINATED_EXIT,
                group_id=group_id,
                target_leg_key=None,
                slippage_multiplier=1,
                reason=f"Mandatory intraday force-flat triggered at {current_time_ist} IST (>= {self.force_flat_time_ist}).",
            )

        # 2. Stale mark check: if any open leg is stale, skip stop/target checks (ENGINE §24)
        if group.is_group_mark_stale():
            return SequencingDirective(
                action=SequencerActionType.NO_ACTION,
                group_id=group_id,
                target_leg_key=None,
                slippage_multiplier=1,
                reason="Stale or missing leg mark detected; group stop/target evaluation deferred.",
            )

        combined_pnl = group.calculate_combined_unrealized_pnl()

        # 3. Group Stop Loss Check
        if group.group_stop_loss_paise is not None:
            if int(combined_pnl) <= int(group.group_stop_loss_paise):
                return SequencingDirective(
                    action=SequencerActionType.QUEUE_COORDINATED_EXIT,
                    group_id=group_id,
                    target_leg_key=None,
                    slippage_multiplier=1,
                    reason=f"Group Stop-Loss triggered: combined P&L ({combined_pnl} paise) <= stop limit ({group.group_stop_loss_paise} paise).",
                )

        # 4. Group Take Profit Target Check
        if group.group_take_profit_paise is not None:
            if int(combined_pnl) >= int(group.group_take_profit_paise):
                return SequencingDirective(
                    action=SequencerActionType.QUEUE_COORDINATED_EXIT,
                    group_id=group_id,
                    target_leg_key=None,
                    slippage_multiplier=1,
                    reason=f"Group Take-Profit triggered: combined P&L ({combined_pnl} paise) >= target limit ({group.group_take_profit_paise} paise).",
                )

        # 5. Group Trailing Stop Check
        trailing_trigger = group.update_trailing_stops()
        if trailing_trigger is not None:
            if int(combined_pnl) <= int(trailing_trigger):
                return SequencingDirective(
                    action=SequencerActionType.QUEUE_COORDINATED_EXIT,
                    group_id=group_id,
                    target_leg_key=None,
                    slippage_multiplier=1,
                    reason=f"Group Trailing-Stop triggered: combined P&L ({combined_pnl} paise) <= trailing trigger ({trailing_trigger} paise).",
                )

        return SequencingDirective(
            action=SequencerActionType.NO_ACTION,
            group_id=group_id,
            target_leg_key=None,
            slippage_multiplier=1,
            reason="Group P&L is within bounds; no exit triggered.",
        )

    def get_exit_order_sequence(self, group_id: str) -> List[Tuple[str, LegPosition]]:
        """
        1. The use of function:
           Returns open legs ordered for margin-optimal exit sequencing (short legs first, long legs second).

        2. How does the specific function work:
           - Filters open legs in group.legs.
           - Sorts legs so that short legs (side == SELL) appear before long legs (side == BUY).
           - Returns ordered list of (leg_key, LegPosition) tuples.

        3. Concepts used in the function:
           SEBI margin optimal square-off: buy short options to extinguish liability before selling long hedges.

        4. Places where this function is imported and used:
           Used by fill engine when processing QUEUE_COORDINATED_EXIT directives.

        5. Final output of the function, before and after:
           Before: Unordered leg dictionary. After: Margin-ordered leg sequence (shorts first, longs second).
        """
        group = self.groups[group_id]
        open_legs = [(k, leg) for k, leg in group.legs.items() if leg.is_open()]
        # Sort key: short options (SELL) get priority 0, long options (BUY) get priority 1
        open_legs.sort(key=lambda item: 0 if item[1].side == OrderSide.SELL else 1)
        return open_legs

    def check_volume_warning(self, order_qty: int, bar_volume: int, instrument_key: str) -> Optional[str]:
        """
        1. The use of function:
           Emits a structured warning if proposed order quantity exceeds the observed candle volume.

        2. How does the specific function work:
           - Compares order_qty against bar_volume.
           - If order_qty > bar_volume, generates VOLUME_EXCEEDED_WARNING string, appends to self.warnings, and returns it.
           - If volume is sufficient, returns None.

        3. Concepts used in the function:
           ENGINE §24 partial-fill deferral contract: atomic execution with visible volume warning.

        4. Places where this function is imported and used:
           Used by order queue and fill engine at step 1 open.

        5. Final output of the function, before and after:
           Before: Uninspected order quantity. After: Warning string if exceeded, else None.
        """
        if order_qty > bar_volume:
            warning = (
                f"VOLUME_EXCEEDED_WARNING: Order quantity {order_qty} for {instrument_key} "
                f"exceeds observed candle volume {bar_volume}. Filled atomically at next-bar open; partial fills deferred."
            )
            self.warnings.append(warning)
            return warning
        return None

    def handle_session_boundary(
        self,
        group_id: str,
        is_final_bar_close: bool,
        has_missing_data: bool = False,
    ) -> SequencingDirective:
        """
        1. The use of function:
           Enforces final 15:29:00 session bar boundary contracts and fail-closed halt transitions.

        2. How does the specific function work:
           - If not final bar close, returns NO_ACTION.
           - If final bar close (15:29:00 close):
             * If has_missing_data is True, transitions group to HALTED_UNRESOLVED (fail-closed, never fabricates prices).
             * If data is present, emits EXECUTE_EOD_FILL with 2x slippage multiplier.

        3. Concepts used in the function:
           NO_NEXT_BAR final bar rule, fail-closed market data halt invariant (Stage 4 Plan §4).

        4. Places where this function is imported and used:
           Used by BacktestRunner at 15:29 IST session conclusion.

        5. Final output of the function, before and after:
           Before: Unresolved group at EOD. After: HALT_UNRESOLVED or EXECUTE_EOD_FILL directive.
        """
        if not is_final_bar_close:
            return SequencingDirective(
                action=SequencerActionType.NO_ACTION,
                group_id=group_id,
                target_leg_key=None,
                slippage_multiplier=1,
                reason="Not at session boundary.",
            )

        group = self.groups[group_id]
        if has_missing_data:
            group.transition_to(LeggingState.HALTED_UNRESOLVED)
            warning_msg = f"HALTED_UNRESOLVED: Group {group_id} could not be cleanly closed due to missing session close data. Zero unverified fills fabricated."
            self.warnings.append(warning_msg)
            return SequencingDirective(
                action=SequencerActionType.HALT_UNRESOLVED,
                group_id=group_id,
                target_leg_key=None,
                slippage_multiplier=1,
                reason="Missing market data at session boundary; transitioned to HALTED_UNRESOLVED.",
            )

        return SequencingDirective(
            action=SequencerActionType.EXECUTE_EOD_FILL,
            group_id=group_id,
            target_leg_key=None,
            slippage_multiplier=2,
            reason="Executing EOD_CLOSE_FILL with 2x slippage penalty on final session bar close.",
        )
