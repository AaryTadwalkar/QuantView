"""
1. What this file does:
   Defines the simulation engine, causal clock, fill model, point-in-time contract selector,
   position groups, execution sequencer, and order orchestration for QuantView (Tasks M4-05, M4-14, M4-16).

2. Overall design:
   The engine orchestrates the exchange-calendar minute loop across historical bars or live streams.
   It coordinates:
     - Causal bar progression (STOP_FIRST order of intrabar stops vs targets).
     - Fill models respecting exchange tick sizes and slippage.
     - Separation of the three canonical P&L modes (UNDERLYING_DIRECTIONAL, ACTUAL_OPTIONS, SYNTHETIC_OPTIONS_ESTIMATE).
     - Point-in-time contract selection without look-ahead bias or silent substitution.
     - Multi-leg PositionGroup tracking and 10-state legging lifecycle machine.
     - LeggingSequencer for margin-optimal sequencing, 3x adverse slippage unwind recovery, and session boundaries.

3. Elements in the file:
   - EngineRunConfig: Configuration specification for backtest execution.
   - Re-exports from packages.engine.selector: StrikeSelectionPolicy, ExpirySelectionPolicy,
     StrikePolicySpec, ContractSelectionResult, ContractMasterProvider, InMemoryContractMaster,
     DuckDbContractMaster, PointInTimeContractSelector.
   - Re-exports from packages.engine.groups: LegStatus, LeggingState, StrategyIntent,
     InvalidLeggingTransitionError, LegPosition, PositionGroup.
   - Re-exports from packages.engine.sequencer: SequencerActionType, SequencingDirective, LeggingSequencer.

4. Final output of the file:
   - Exported engine configuration contracts, execution clock interfaces, position groups, sequencer, and PIT contract selector.
"""

from typing import Dict, Any, List, Optional
from packages.domain import OperatingMode, UtcEpochSec
from packages.strategies import Strategy
from packages.ledger import FinancialLedger
from packages.risk import RiskPolicyEvaluator
from packages.engine.config import EngineRunConfig
from packages.engine.clock import SimulationMinute, SimulationClock
from packages.engine.orders import OrderIntentType, OrderStatus, ActiveOrder
from packages.engine.positions import ActivePosition
from packages.engine.execution import CandleBar, IntrabarFillEngine
from packages.engine.selector import (
    StrikeSelectionPolicy,
    ExpirySelectionPolicy,
    StrikePolicySpec,
    ContractSelectionResult,
    ContractMasterProvider,
    InMemoryContractMaster,
    DuckDbContractMaster,
    PointInTimeContractSelector,
)
from packages.engine.groups import (
    LegStatus,
    LeggingState,
    StrategyIntent,
    InvalidLeggingTransitionError,
    LegPosition,
    PositionGroup,
)
from packages.engine.sequencer import (
    SequencerActionType,
    SequencingDirective,
    LeggingSequencer,
)


__all__ = [
    "EngineRunConfig",
    "SimulationMinute",
    "SimulationClock",
    "OrderIntentType",
    "OrderStatus",
    "ActiveOrder",
    "ActivePosition",
    "CandleBar",
    "IntrabarFillEngine",
    "StrikeSelectionPolicy",
    "ExpirySelectionPolicy",
    "StrikePolicySpec",
    "ContractSelectionResult",
    "ContractMasterProvider",
    "InMemoryContractMaster",
    "DuckDbContractMaster",
    "PointInTimeContractSelector",
    "LegStatus",
    "LeggingState",
    "StrategyIntent",
    "InvalidLeggingTransitionError",
    "LegPosition",
    "PositionGroup",
    "SequencerActionType",
    "SequencingDirective",
    "LeggingSequencer",
]
