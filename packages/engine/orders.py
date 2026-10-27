"""
1. What this file does:
   Defines order contracts, order intents, statuses, and life-cycle models for QuantView (Task M4-05).

2. Overall design:
   Enforces causal order progression per QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §4:
     - Orders are created at bar close e (decision time) and queued for execution at next bar open s.
     - Strict typing of side, contract, quantity, and protective stop/target levels.
     - Tracks life-cycle states (PENDING, FILLED, REJECTED, EXPIRED, CANCELLED) with structured rejection reasons.

3. Elements in the file:
   - OrderIntentType: Enumeration of strategy order intentions.
   - OrderStatus: Enumeration of order execution states.
   - ActiveOrder: Mutable or immutable order state container tracking execution lifecycle.

4. Final output of the file:
   - Exported OrderIntentType, OrderStatus, and ActiveOrder classes.
"""

import uuid
from enum import Enum
from typing import Optional

from packages.domain import (
    ContractIdentifier,
    OrderSide,
    Paise,
    UtcEpochSec,
)
from packages.engine.clock import SimulationMinute


class OrderIntentType(str, Enum):
    """Enumeration of strategy trading intentions."""
    ENTER_LONG_CE = "ENTER_LONG_CE"
    ENTER_LONG_PE = "ENTER_LONG_PE"
    EXIT_LONG_CE = "EXIT_LONG_CE"
    EXIT_LONG_PE = "EXIT_LONG_PE"
    FORCE_FLAT = "FORCE_FLAT"


class OrderStatus(str, Enum):
    """Enumeration of order execution states."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ActiveOrder:
    """
    1. The use of class:
       Tracks an active order throughout its lifecycle from queue to fill or rejection.

    2. What the class contains:
       - order_id: Unique UUID string.
       - contract: ContractIdentifier of the instrument.
       - side: OrderSide (BUY or SELL).
       - qty: Number of units to trade.
       - queued_at_utc: UtcEpochSec when order was queued.
       - fill_at_minute: SimulationMinute when order is eligible to fill (next open).
       - stop_loss_paise: Optional stop-loss trigger price in Paise.
       - take_profit_paise: Optional take-profit trigger price in Paise.
       - status: OrderStatus.
       - filled_price_paise: Final quantized fill price if filled.
       - rejection_reason: Structured code if rejected.

    3. Technologies used and why:
       Plain class for mutable lifecycle transitions within the fill engine.

    4. Key design and overall design of the class:
       Enforces next-bar open fill delay to eliminate look-ahead bias.
    """

    def __init__(
        self,
        contract: ContractIdentifier,
        side: OrderSide,
        qty: int,
        queued_at_utc: UtcEpochSec,
        fill_at_minute: SimulationMinute,
        stop_loss_paise: Optional[Paise] = None,
        take_profit_paise: Optional[Paise] = None,
        order_id: Optional[str] = None,
    ) -> None:
        self.order_id = order_id or str(uuid.uuid4())
        self.contract = contract
        self.side = side
        self.qty = qty
        self.queued_at_utc = queued_at_utc
        self.fill_at_minute = fill_at_minute
        self.stop_loss_paise = stop_loss_paise
        self.take_profit_paise = take_profit_paise
        self.status = OrderStatus.PENDING
        self.filled_price_paise: Optional[Paise] = None
        self.rejection_reason: Optional[str] = None

    def fill(self, fill_price_paise: Paise) -> None:
        """Marks the order as FILLED at the given quantized fill price."""
        self.status = OrderStatus.FILLED
        self.filled_price_paise = fill_price_paise

    def reject(self, reason: str) -> None:
        """Marks the order as REJECTED with a structured reason code."""
        self.status = OrderStatus.REJECTED
        self.rejection_reason = reason
