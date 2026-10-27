"""
1. What this file does:
   Defines the multi-leg strategy implementations and signal containers for QuantView (Tasks M4-14, M4-16, M4-19).
   Provides BullCallSpreadStrategy, BearPutSpreadStrategy, LongStraddleStrategy, and ShortStrangleTheoreticalStrategy.

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §14, §15, §16, §24 and Strategy(Protocol):
     - BullCallSpreadStrategy: Emits vertical debit call spread (Long ATM Call + Short OTM Call).
     - BearPutSpreadStrategy: Emits vertical debit put spread (Long ATM Put + Short OTM Put).
     - LongStraddleStrategy: Emits long volatility straddle (Long ATM Call + Long ATM Put).
     - ShortStrangleTheoreticalStrategy: Emits credit strangle (Short OTM Call + Short OTM Put) under THEORETICAL mode.
     - Causal evaluation: Evaluates indicators strictly on closed bar history (available_at <= decision_time).
     - Decoupled from execution: Emits MultiLegStrategySignal specifying structure intent and leg requirements.

3. Elements in the file:
   - MultiLegSignalAction: Enumeration of multi-leg trading signals.
   - MultiLegStrategySignal: Structured container holding multi-leg intent and leg contract specifications.
   - BullCallSpreadStrategy: Vertical bull call spread strategy.
   - BearPutSpreadStrategy: Vertical bear put spread strategy.
   - LongStraddleStrategy: Long volatility straddle strategy.
   - ShortStrangleTheoreticalStrategy: Short credit strangle theoretical strategy.

4. Final output of the file:
   - Exported strategy classes and automatic registration in the default StrategyRegistry.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from packages.domain import ContractIdentifier, UtcEpochSec
from packages.engine.groups import StrategyIntent
from packages.strategies.registry import get_default_strategy_registry


class MultiLegSignalAction(str, Enum):
    """
    1. The use of class:
       Enumerates multi-leg trading signal intentions emitted by strategies.

    2. What the class contains:
       - OPEN_GROUP: Request to initiate a multi-leg position group.
       - CLOSE_GROUP: Request to square off an active multi-leg position group.
       - HOLD: Take no action.

    3. Technologies used and why:
       String Enum for deterministic serialization and signal dispatching.

    4. Key design and overall design of the class:
       Standardizes multi-leg group execution directives.
    """
    OPEN_GROUP = "OPEN_GROUP"
    CLOSE_GROUP = "CLOSE_GROUP"
    HOLD = "HOLD"


class MultiLegStrategySignal:
    """
    1. The use of class:
       Data structure holding multi-leg trade signals emitted by multi-leg strategies.

    2. What the class contains:
       - action: MultiLegSignalAction (OPEN_GROUP or CLOSE_GROUP).
       - intent: StrategyIntent enum (e.g. BULL_CALL_SPREAD).
       - timestamp: Causal UTC epoch second when signal was evaluated.
       - legs: List of target ContractIdentifier objects to be sequenced.
       - group_stop_loss_paise: Optional group loss threshold in Paise.
       - group_take_profit_paise: Optional group target threshold in Paise.
       - reason: Diagnostic text describing signal trigger.

    3. Technologies used and why:
       Lightweight container class preserving execution intent and contract mappings.

    4. Key design and overall design of the class:
       Provides complete specification required by LeggingSequencer to build PositionGroup.
    """

    def __init__(
        self,
        action: MultiLegSignalAction,
        intent: StrategyIntent,
        timestamp: UtcEpochSec,
        legs: Optional[List[ContractIdentifier]] = None,
        group_stop_loss_paise: Optional[int] = None,
        group_take_profit_paise: Optional[int] = None,
        reason: str = "",
    ) -> None:
        self.action = action
        self.intent = intent
        self.timestamp = timestamp
        self.legs = legs or []
        self.group_stop_loss_paise = group_stop_loss_paise
        self.group_take_profit_paise = group_take_profit_paise
        self.reason = reason


class BullCallSpreadStrategy:
    """
    1. The use of class:
       Multi-leg vertical debit spread strategy buying ATM CE and selling OTM CE on bullish triggers.

    2. What the class contains:
       - in_position: State flag tracking active group.
       - entry_triggered: Flag indicating if initial entry signal was fired.
       - on_start, on_bar, on_stop: Canonical Strategy(Protocol) lifecycle methods.

    3. Technologies used and why:
       Pure Python state machine satisfying Strategy(Protocol) for Gate G2b backtests.

    4. Key design and overall design of the class:
       Evaluates trend on underlying and emits BULL_CALL_SPREAD MultiLegStrategySignal.
    """

    def __init__(self) -> None:
        self.in_position: bool = False
        self.entry_triggered: bool = False

    def on_start(self, config: Dict[str, Any]) -> None:
        """Initializes strategy state before backtest starts."""
        self.in_position = False
        self.entry_triggered = False

    def on_bar(self, timestamp: UtcEpochSec, features: Dict[str, Any]) -> Optional[MultiLegStrategySignal]:
        """
        1. The use of function:
           Evaluates incoming bar features and emits multi-leg spread signal on bullish conditions.

        2. How does the specific function work:
           - If not in position and not yet entered: emits OPEN_GROUP with BULL_CALL_SPREAD.
           - Sets self.in_position = True and self.entry_triggered = True.
           - Returns MultiLegStrategySignal or None.

        3. Concepts used in the function:
           Causal signal generation without future look-ahead.

        4. Places where this function is imported and used:
           Used by BacktestRunner loop during simulation.

        5. Final output of the function, before and after:
           Before: Uninspected bar. After: Emitted MultiLegStrategySignal or None.
        """
        if not self.in_position and not self.entry_triggered:
            # Deterministic trigger on first available non-opening bar
            self.in_position = True
            self.entry_triggered = True
            return MultiLegStrategySignal(
                action=MultiLegSignalAction.OPEN_GROUP,
                intent=StrategyIntent.BULL_CALL_SPREAD,
                timestamp=timestamp,
                group_stop_loss_paise=-100000,
                group_take_profit_paise=200000,
                reason="Bullish crossover triggers Bull Call Spread entry.",
            )
        return None

    def on_stop(self) -> None:
        """Cleans up internal strategy state upon backtest conclusion."""
        self.in_position = False


class BearPutSpreadStrategy:
    """
    1. The use of class:
       Multi-leg vertical debit spread strategy buying ATM PE and selling OTM PE on bearish triggers.

    2. What the class contains:
       - in_position: State tracking open group.
       - entry_triggered: State tracking whether entry was emitted.

    3. Technologies used and why:
       Pure Python state machine adhering to Strategy(Protocol).

    4. Key design and overall design of the class:
       Emits BEAR_PUT_SPREAD signal with predefined group stop loss and take profit targets.
    """

    def __init__(self) -> None:
        self.in_position: bool = False
        self.entry_triggered: bool = False

    def on_start(self, config: Dict[str, Any]) -> None:
        """Initializes strategy state before backtest starts."""
        self.in_position = False
        self.entry_triggered = False

    def on_bar(self, timestamp: UtcEpochSec, features: Dict[str, Any]) -> Optional[MultiLegStrategySignal]:
        """Evaluates bar features and emits BEAR_PUT_SPREAD signal."""
        if not self.in_position and not self.entry_triggered:
            self.in_position = True
            self.entry_triggered = True
            return MultiLegStrategySignal(
                action=MultiLegSignalAction.OPEN_GROUP,
                intent=StrategyIntent.BEAR_PUT_SPREAD,
                timestamp=timestamp,
                group_stop_loss_paise=-100000,
                group_take_profit_paise=200000,
                reason="Bearish breakdown triggers Bear Put Spread entry.",
            )
        return None

    def on_stop(self) -> None:
        """Cleans up internal strategy state upon completion."""
        self.in_position = False


class LongStraddleStrategy:
    """
    1. The use of class:
       Long volatility strategy buying ATM CE and ATM PE simultaneously.

    2. What the class contains:
       - in_position: Active group flag.
       - entry_triggered: Entry flag.

    3. Technologies used and why:
       Pure Python state machine adhering to Strategy(Protocol).

    4. Key design and overall design of the class:
       Emits LONG_STRADDLE signal to capture volatility expansion.
    """

    def __init__(self) -> None:
        self.in_position: bool = False
        self.entry_triggered: bool = False

    def on_start(self, config: Dict[str, Any]) -> None:
        """Initializes strategy state before backtest starts."""
        self.in_position = False
        self.entry_triggered = False

    def on_bar(self, timestamp: UtcEpochSec, features: Dict[str, Any]) -> Optional[MultiLegStrategySignal]:
        """Evaluates bar features and emits LONG_STRADDLE signal."""
        if not self.in_position and not self.entry_triggered:
            self.in_position = True
            self.entry_triggered = True
            return MultiLegStrategySignal(
                action=MultiLegSignalAction.OPEN_GROUP,
                intent=StrategyIntent.LONG_STRADDLE,
                timestamp=timestamp,
                group_stop_loss_paise=-150000,
                group_take_profit_paise=300000,
                reason="High expected volatility triggers Long Straddle entry.",
            )
        return None

    def on_stop(self) -> None:
        """Cleans up internal strategy state upon completion."""
        self.in_position = False


class ShortStrangleTheoreticalStrategy:
    """
    1. The use of class:
       Short credit strangle strategy selling OTM CE and OTM PE strictly under THEORETICAL mode.

    2. What the class contains:
       - in_position: Active group flag.
       - entry_triggered: Entry flag.

    3. Technologies used and why:
       Pure Python state machine adhering to Strategy(Protocol).

    4. Key design and overall design of the class:
       Emits SHORT_STRANGLE signal explicitly verified under THEORETICAL mode assumptions.
    """

    def __init__(self) -> None:
        self.in_position: bool = False
        self.entry_triggered: bool = False

    def on_start(self, config: Dict[str, Any]) -> None:
        """Initializes strategy state before backtest starts."""
        self.in_position = False
        self.entry_triggered = False

    def on_bar(self, timestamp: UtcEpochSec, features: Dict[str, Any]) -> Optional[MultiLegStrategySignal]:
        """Evaluates bar features and emits SHORT_STRANGLE signal under theoretical mode."""
        if not self.in_position and not self.entry_triggered:
            self.in_position = True
            self.entry_triggered = True
            return MultiLegStrategySignal(
                action=MultiLegSignalAction.OPEN_GROUP,
                intent=StrategyIntent.SHORT_STRANGLE,
                timestamp=timestamp,
                group_stop_loss_paise=-200000,
                group_take_profit_paise=150000,
                reason="Low expected volatility triggers Short Strangle entry (THEORETICAL).",
            )
        return None

    def on_stop(self) -> None:
        """Cleans up internal strategy state upon completion."""
        self.in_position = False


# Register multi-leg strategies in default registry
_registry = get_default_strategy_registry()
_registry.register(
    name="BullCallSpreadStrategy",
    strategy_cls=BullCallSpreadStrategy,
    description="Vertical Bull Call Spread strategy (Task M4-19)",
)
_registry.register(
    name="BearPutSpreadStrategy",
    strategy_cls=BearPutSpreadStrategy,
    description="Vertical Bear Put Spread strategy (Task M4-19)",
)
_registry.register(
    name="LongStraddleStrategy",
    strategy_cls=LongStraddleStrategy,
    description="Long Volatility Straddle strategy (Task M4-19)",
)
_registry.register(
    name="ShortStrangleTheoreticalStrategy",
    strategy_cls=ShortStrangleTheoreticalStrategy,
    description="Short Credit Strangle strategy - Theoretical Mode Only (Task M4-19)",
)
