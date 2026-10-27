"""
1. What this file does:
   Defines the explicitly quarantined Session VWAP feature contract and error guards
   for QuantView (Milestone M5-11 / Gate G3).

2. Overall design:
   Enforces strict data honesty per ADR-005, DATA SPEC §4.2, and Stage 5 feasibility matrix.
   Because the NIFTY cash index carries volume = 0, session VWAP is blocked from calculation
   to prevent look-ahead bias or synthetic volume artifacts. Any invocation fails closed.

3. Elements in the file:
   - SessionVWAPQuarantinedError: Exception raised when attempting to calculate cash index VWAP.
   - SessionVWAPGuard: Quarantined feature specification and evaluation guard.
   - register_quarantined_vwap: Function registering the quarantined VWAP in FeatureRegistry.

4. Final output of the file:
   - Fail-closed VWAP quarantine guard and registered BLOCKED_QUARANTINED feature definition.
"""

from typing import Any, Dict, List, Optional
from packages.features.schemas import (
    FeatureDefinition,
    FeatureStatus,
    MemoryClass,
    RepaintClass,
    SourceTier,
)
from packages.features.registry import FeatureRegistry


class SessionVWAPQuarantinedError(RuntimeError):
    """
    1. The use of class:
       Raised when any strategy or engine pipeline attempts to evaluate Session VWAP
       on cash index candles lacking genuine exchange volume.

    2. What the class contains:
       Standard RuntimeError inheritance with informative diagnostic messaging.

    3. Technologies used and why:
       Standard Python RuntimeError for fail-closed operational blocking.

    4. Key design and overall design of the class:
       Guarantees data truthfulness by prohibiting ungrounded volume proxies or fake VWAP calculations.
    """
    pass


class SessionVWAPGuard:
    """
    1. The use of class:
       Enforces the BLOCKED_QUARANTINED lifecycle state for Session VWAP on cash index data.

    2. What the class contains:
       - FEATURE_NAME: Constant string 'SESSION_VWAP'.
       - STATUS: FeatureStatus.BLOCKED_QUARANTINED.
       - REASON: Detailed architectural rationale citing M5-11 and ADR-005.

    3. Technologies used and why:
       Static class pattern encapsulating policy constants and validation methods.

    4. Key design and overall design of the class:
       Serves as the single point of truth rejecting cash index VWAP queries.
    """
    FEATURE_NAME = "SESSION_VWAP"
    STATUS = FeatureStatus.BLOCKED_QUARANTINED
    REASON = (
        "Session VWAP is strictly BLOCKED_QUARANTINED for NIFTY cash index because "
        "cash index candles have volume == 0. Substituting option volume, tick counts, "
        "or synthetic proxies is prohibited. A future futures-based VWAP will be a "
        "distinct feature with independent provenance once Task M3-12 futures data is certified."
    )

    @classmethod
    def evaluate(cls, *args: Any, **kwargs: Any) -> None:
        """
        1. The use of function:
           Fail-closed evaluation gate raising SessionVWAPQuarantinedError.

        2. How does the specific function work:
           Unconditionally raises SessionVWAPQuarantinedError with explanatory message.

        3. Concepts used in the function:
           Fail-closed safety guard, architectural boundary enforcement.

        4. Places where this function is imported and used:
           Used by StrategyContext and feature execution engines when VWAP is requested.

        5. Final output of the function, before and after:
           Before: Query attempt. After: SessionVWAPQuarantinedError raised.
        """
        raise SessionVWAPQuarantinedError(cls.REASON)


def register_quarantined_vwap() -> str:
    """
    1. The use of function:
       Registers the quarantined Session VWAP feature definition in the central FeatureRegistry.

    2. How does the specific function work:
       Constructs a FeatureDefinition with BLOCKED_QUARANTINED metadata and registers it.

    3. Concepts used in the function:
       Declarative registry configuration, self-describing quality flagging.

    4. Places where this function is imported and used:
       Called during package initialization and registry discovery.

    5. Final output of the function, before and after:
       Before: Unregistered VWAP. After: Feature registered with BLOCKED_QUARANTINED description.
    """
    defn = FeatureDefinition(
        name=SessionVWAPGuard.FEATURE_NAME,
        version="v1",
        params={},
        lookback_window=1,
        warm_up_bars=0,
        memory_class=MemoryClass.FINITE,
        source_tier=SourceTier.UNDERLYING_CANDLE,
        repaint_class=RepaintClass.NONE,
        output_schema={"vwap": "null"},
        description=f"BLOCKED_QUARANTINED: {SessionVWAPGuard.REASON}",
    )
    registry = FeatureRegistry()
    return registry.register(
        definition=defn,
        compute_fn=SessionVWAPGuard.evaluate,
        metadata={"status": FeatureStatus.BLOCKED_QUARANTINED.value, "reason": SessionVWAPGuard.REASON},
    )
