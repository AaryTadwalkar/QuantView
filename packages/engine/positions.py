"""
1. What this file does:
   Defines the ActivePosition model and position tracker for single-leg option positions (Task M4-05).

2. Overall design:
   Tracks open options contracts in memory during backtest simulation:
     - Maintains entry price, quantity, stop-loss trigger, and take-profit targets.
     - Tracks flat/stale candle counters to enforce stale-data liquidation rules.
     - Computes unrealized mark-to-market P&L using exact integer paise arithmetic.

3. Elements in the file:
   - ActivePosition: Container tracking a live open contract position.

4. Final output of the file:
   - Exported ActivePosition class.
"""

from typing import Optional
from packages.domain import ContractIdentifier, OrderSide, Paise, UtcEpochSec


class ActivePosition:
    """
    1. The use of class:
       Tracks an open single-leg long option position throughout the simulation.

    2. What the class contains:
       - contract: ContractIdentifier.
       - side: OrderSide (BUY for long).
       - qty: Open quantity in units.
       - entry_price_paise: Quantized entry fill price in Paise.
       - entry_time: UtcEpochSec when filled.
       - stop_loss_paise: Stop loss trigger price.
       - take_profit_paise: Take profit target price.
       - consecutive_stale_bars: Counter tracking consecutive flat/missing bars.

    3. Technologies used and why:
       Plain class for high-performance in-memory state tracking.

    4. Key design and overall design of the class:
       Provides the operational state evaluated during Step 2 of the intrabar sequence.
    """

    def __init__(
        self,
        contract: ContractIdentifier,
        side: OrderSide,
        qty: int,
        entry_price_paise: Paise,
        entry_time: UtcEpochSec,
        stop_loss_paise: Optional[Paise] = None,
        take_profit_paise: Optional[Paise] = None,
    ) -> None:
        self.contract = contract
        self.side = side
        self.qty = qty
        self.entry_price_paise = entry_price_paise
        self.entry_time = entry_time
        self.stop_loss_paise = stop_loss_paise
        self.take_profit_paise = take_profit_paise
        self.consecutive_stale_bars = 0

    def update_stops(self, new_stop: Optional[Paise], new_target: Optional[Paise]) -> None:
        """Updates protective stop loss and take profit targets."""
        if new_stop is not None:
            self.stop_loss_paise = new_stop
        if new_target is not None:
            self.take_profit_paise = new_target

    def mark_unrealized_pnl(self, current_price_paise: Paise) -> Paise:
        """Calculates unrealized mark-to-market gain/loss in Paise."""
        price_diff = int(current_price_paise) - int(self.entry_price_paise)
        return Paise(self.qty * price_diff)
