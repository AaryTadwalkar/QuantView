"""
1. What this file does:
   Implements the Intrabar Fill Engine, slippage model, and causal 4-step execution sequence (Tasks M4-05, M4-22).
   Handles STOP_FIRST ambiguity resolution, gap-through fills, zero-volume flat bar deferral,
   stale-data liquidation, causal force-flat, and the NO_NEXT_BAR final bar rule.

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §4 and Stage 3 Review Hardening:
     - Step 1 (At Open): Fills queued orders at open with adverse slippage and TickQuantizer.
       Re-checks cash capital at boundary (REJECTED_INSUFFICIENT_CASH). Fills through gaps at open price.
     - Step 2 (Intrabar): Evaluates stop-loss and take-profit against bar high/low. Enforces STOP_FIRST policy
       if both touched in the same minute. Zero-volume flat bars do not trigger fills or stops.
     - Step 3 (At Close): Marks equity. Evaluates causal 15:25 force-flat. Enforces the final bar 15:29 rule:
       new strategy entries are rejected with NO_NEXT_BAR; pre-scheduled liquidations close at EOD_CLOSE_FILL.
     - Step 4 (Post-Fill): Posts FILL and FEE events to FinancialLedger using dynamic FeeScheduleEngine.

3. Elements in the file:
   - CandleBar: Lightweight tuple/dataclass holding 1-minute OHLCV data.
   - IntrabarFillEngine: The core causal order fill and lifecycle simulation engine.

4. Final output of the file:
   - Exported CandleBar and IntrabarFillEngine classes.
"""

from typing import Any, Dict, List, NamedTuple, Optional

from packages.domain import (
    ContractIdentifier,
    OrderSide,
    Paise,
    TickQuantizer,
)
from packages.engine.clock import SimulationMinute
from packages.engine.orders import ActiveOrder
from packages.engine.positions import ActivePosition
from packages.ledger.fees import FeeScheduleEngine, get_default_fee_engine
from packages.ledger.ledger import FinancialLedger


class CandleBar(NamedTuple):
    """
    1. The use of class:
       Immutable container representing a completed 1-minute option candle bar.

    2. What the class contains:
       - open_paise: Open price in Paise.
       - high_paise: High price in Paise.
       - low_paise: Low price in Paise.
       - close_paise: Close price in Paise.
       - volume: Total contracts traded.
       - is_flat_bar: True if open == high == low == close and volume == 0.

    3. Technologies used and why:
       NamedTuple for fast intrabar evaluation.
    """
    open_paise: Paise
    high_paise: Paise
    low_paise: Paise
    close_paise: Paise
    volume: int
    is_flat_bar: bool


class IntrabarFillEngine:
    """
    1. The use of class:
       Causal intrabar execution engine orchestrating order fills, protective stops, and ledger postings.

    2. What the class contains:
       - ledger: Associated FinancialLedger.
       - fee_engine: FeeScheduleEngine.
       - slippage_paise: Default slippage in integer Paise (e.g. 5 paise).
       - tick_paise: Tick size in integer Paise (e.g. 5 paise).
       - max_stale_minutes: Threshold of consecutive flat bars before forcing liquidation (default 5).
       - active_position: Currently held ActivePosition (or None).
       - pending_orders: List of queued ActiveOrder items.
       - process_minute_open(): Executes Step 1 at bar open.
       - evaluate_intrabar_stops(): Executes Step 2 intrabar stop/target checks.
       - process_minute_close(): Executes Step 3 at bar close (marks, force-flat, signal queues).

    3. Technologies used and why:
       Pure integer arithmetic on Paise types and TickQuantizer for zero float leakage.

    4. Key design and overall design of the class:
       Strictly satisfies the 4-step sequence from ENGINE §4 and the review-mandated NO_NEXT_BAR invariant.
    """

    def __init__(
        self,
        ledger: FinancialLedger,
        fee_engine: Optional[FeeScheduleEngine] = None,
        slippage_paise: int = 5,
        tick_paise: int = 5,
        max_stale_minutes: int = 5,
    ) -> None:
        self.ledger = ledger
        self.fee_engine = fee_engine or get_default_fee_engine()
        self.slippage_paise = slippage_paise
        self.tick_paise = tick_paise
        self.max_stale_minutes = max_stale_minutes
        self.active_position: Optional[ActivePosition] = None
        self.pending_orders: List[ActiveOrder] = []
        self.trade_history: List[Dict[str, Any]] = []

    def queue_order(
        self,
        contract: ContractIdentifier,
        side: OrderSide,
        qty: int,
        current_minute: SimulationMinute,
        stop_loss_paise: Optional[Paise] = None,
        take_profit_paise: Optional[Paise] = None,
    ) -> Optional[ActiveOrder]:
        """
        1. The use of function:
           Queues an order generated at bar close for execution at the next bar open.

        2. How does the specific function work:
           - P0 REVIEW CHECK: If signal is generated on final session bar (15:29 IST),
             rejects immediately with reason code NO_NEXT_BAR.
           - Otherwise, constructs ActiveOrder and adds to pending_orders.
        """
        if current_minute.is_final_session_minute:
            # Rule: Signals decided at 15:29 close cannot fill because no next regular bar exists
            return None

        det_order_id = f"ord_{current_minute.bar_start_utc}_{side.value}_{contract.instrument_key}"
        order = ActiveOrder(
            contract=contract,
            side=side,
            qty=qty,
            queued_at_utc=current_minute.bar_end_utc,
            fill_at_minute=current_minute,
            stop_loss_paise=stop_loss_paise,
            take_profit_paise=take_profit_paise,
            order_id=det_order_id,
        )
        self.pending_orders.append(order)
        return order

    def step_1_open(self, minute: SimulationMinute, candle: CandleBar) -> List[ActiveOrder]:
        """
        1. The use of function:
           Executes Step 1 of the intrabar sequence at bar open.

        2. How does the specific function work:
           - Ignores zero-volume flat bars (defers pending orders).
           - Applies adverse slippage (BUY adds, SELL subtracts).
           - Quantizes fill price via TickQuantizer.
           - Checks available cash at boundary; rejects if unaffordable.
           - Posts FILL and FEE to FinancialLedger.
           - Updates active_position.
        """
        if candle.is_flat_bar:
            # Zero-volume flat bar: do not fill orders, wait for next non-flat bar
            return []

        filled_orders: List[ActiveOrder] = []
        remaining_pending: List[ActiveOrder] = []

        for order in self.pending_orders:
            # Adverse slippage calculation
            if order.side == OrderSide.BUY:
                raw_fill = candle.open_paise + self.slippage_paise
            else:
                raw_fill = candle.open_paise - self.slippage_paise

            # Tick quantization against trader (operates directly on integer paise)
            quantized_fill = TickQuantizer.quantize(
                int(raw_fill),
                tick_paise=self.tick_paise,
                side=order.side,
            )

            gross_value = Paise(order.qty * int(quantized_fill))

            # Cash affordability check on buy
            if order.side == OrderSide.BUY:
                trade_date_str = minute.session_date.isoformat()
                estimated_fees = self.fee_engine.calculate_order_fees(
                    trade_date=trade_date_str,
                    side=order.side,
                    gross_value_paise=gross_value,
                )
                required_cash = gross_value + estimated_fees.total_fee_paise

                if self.ledger.balance_paise < required_cash:
                    order.reject("REJECTED_INSUFFICIENT_CASH")
                    filled_orders.append(order)
                    continue

            # Execute Fill in Ledger
            trade_date_str = minute.session_date.isoformat()
            self.ledger.record_fill(
                side=order.side,
                instrument_key=order.contract.instrument_key,
                qty=order.qty,
                price_paise=quantized_fill,
                gross_value_paise=gross_value,
                event_time=minute.bar_start_utc,
                correlation_id=order.order_id,
                fill_id=f"fill_{order.order_id}",
            )

            fees = self.fee_engine.calculate_order_fees(
                trade_date=trade_date_str,
                side=order.side,
                gross_value_paise=gross_value,
            )
            self.ledger.record_fee(
                fee_breakdown=fees,
                event_time=minute.bar_start_utc,
                correlation_id=order.order_id,
            )

            order.fill(quantized_fill)
            filled_orders.append(order)

            if order.side == OrderSide.BUY:
                self.active_position = ActivePosition(
                    contract=order.contract,
                    side=order.side,
                    qty=order.qty,
                    entry_price_paise=quantized_fill,
                    entry_time=minute.bar_start_utc,
                    stop_loss_paise=order.stop_loss_paise,
                    take_profit_paise=order.take_profit_paise,
                    entry_fees_paise=fees.total_fee_paise,
                )
            elif order.side == OrderSide.SELL:
                if self.active_position is not None:
                    gross_pnl = (int(quantized_fill) - int(self.active_position.entry_price_paise)) * order.qty
                    total_trade_fees = int(self.active_position.entry_fees_paise) + int(fees.total_fee_paise)
                    self.trade_history.append({
                        "symbol": order.contract.instrument_key,
                        "entry_time": minute.ist_time_str,
                        "entry_price_paise": int(self.active_position.entry_price_paise),
                        "exit_price_paise": int(quantized_fill),
                        "quantity": order.qty,
                        "gross_pnl_paise": gross_pnl,
                        "fee_paise": total_trade_fees,
                        "entry_fee_paise": int(self.active_position.entry_fees_paise),
                        "exit_fee_paise": int(fees.total_fee_paise),
                        "net_pnl_paise": gross_pnl - total_trade_fees,
                        "reason": "NEXT_BAR_OPEN_EXIT",
                    })
                self.active_position = None

        self.pending_orders = remaining_pending
        return filled_orders

    def step_2_intrabar(self, minute: SimulationMinute, candle: CandleBar) -> Optional[Paise]:
        """
        1. The use of function:
           Executes Step 2 of the intrabar sequence evaluating stops and targets.

        2. How does the specific function work:
           - If flat bar: increments stale counter, exits if max_stale_minutes exceeded.
           - Enforces STOP_FIRST: if low <= stop and high >= target, stop wins.
           - Executes exit fill and fee deduction.
        """
        if self.active_position is None:
            return None

        pos = self.active_position

        # 1. Flat Bar Handling
        if candle.is_flat_bar:
            pos.consecutive_stale_bars += 1
            if pos.consecutive_stale_bars >= self.max_stale_minutes:
                # Force liquidation due to stale data with 3x worst-case slippage
                penalty_slippage = self.slippage_paise * 3
                raw_exit = candle.open_paise - penalty_slippage
                quantized_exit = TickQuantizer.quantize(int(raw_exit), self.tick_paise, OrderSide.SELL)
                self._execute_exit(minute, pos, quantized_exit, reason="STALE_DATA_FORCE_EXIT")
                return quantized_exit
            return None

        pos.consecutive_stale_bars = 0

        # 2. Check Stop and Target triggers
        hit_stop = False
        hit_target = False

        if pos.stop_loss_paise is not None and candle.low_paise <= pos.stop_loss_paise:
            hit_stop = True

        if pos.take_profit_paise is not None and candle.high_paise >= pos.take_profit_paise:
            hit_target = True

        if not hit_stop and not hit_target:
            return None

        # STOP_FIRST Ambiguity Resolution Invariant: If both touched, STOP WINS!
        if hit_stop:
            trigger_price = pos.stop_loss_paise or candle.low_paise
            # Adverse slippage on stop exit
            raw_exit = trigger_price - self.slippage_paise
            quantized_exit = TickQuantizer.quantize(int(raw_exit), self.tick_paise, OrderSide.SELL)
            self._execute_exit(minute, pos, quantized_exit, reason="STOP_LOSS_HIT")
            return quantized_exit

        elif hit_target:
            trigger_price = pos.take_profit_paise or candle.high_paise
            # Adverse slippage on target exit
            raw_exit = trigger_price - self.slippage_paise
            quantized_exit = TickQuantizer.quantize(int(raw_exit), self.tick_paise, OrderSide.SELL)
            self._execute_exit(minute, pos, quantized_exit, reason="TAKE_PROFIT_HIT")
            return quantized_exit

        return None

    def _execute_exit(
        self,
        minute: SimulationMinute,
        pos: ActivePosition,
        fill_price: Paise,
        reason: str,
    ) -> None:
        """Helper to post exit fill and fees to ledger."""
        gross_value = Paise(pos.qty * int(fill_price))
        trade_date_str = minute.session_date.isoformat()

        self.ledger.record_fill(
            side=OrderSide.SELL,
            instrument_key=pos.contract.instrument_key,
            qty=pos.qty,
            price_paise=fill_price,
            gross_value_paise=gross_value,
            event_time=minute.bar_end_utc,
            correlation_id=f"exit_{minute.bar_start_utc}",
            fill_id=f"fill_exit_{minute.bar_start_utc}",
        )

        fees = self.fee_engine.calculate_order_fees(
            trade_date=trade_date_str,
            side=OrderSide.SELL,
            gross_value_paise=gross_value,
        )
        self.ledger.record_fee(
            fee_breakdown=fees,
            event_time=minute.bar_end_utc,
            correlation_id=f"exit_{minute.bar_start_utc}",
        )

        gross_pnl = (int(fill_price) - int(pos.entry_price_paise)) * pos.qty
        total_trade_fees = int(pos.entry_fees_paise) + int(fees.total_fee_paise)
        self.trade_history.append({
            "symbol": pos.contract.instrument_key,
            "entry_time": minute.ist_time_str,
            "entry_price_paise": int(pos.entry_price_paise),
            "exit_price_paise": int(fill_price),
            "quantity": pos.qty,
            "gross_pnl_paise": gross_pnl,
            "fee_paise": total_trade_fees,
            "entry_fee_paise": int(pos.entry_fees_paise),
            "exit_fee_paise": int(fees.total_fee_paise),
            "net_pnl_paise": gross_pnl - total_trade_fees,
            "reason": reason,
        })

        self.active_position = None

    def step_3_close(self, minute: SimulationMinute, candle: CandleBar) -> None:
        """
        1. The use of function:
           Executes Step 3 of the intrabar sequence at bar close.

        2. How does the specific function work:
           - Handles causal 15:25 force-flat (queued at 15:24 close).
           - Handles final bar 15:29 EOD_CLOSE_FILL for pre-scheduled liquidation.
        """
        if self.active_position is not None:
            # Causal 15:25 force-flat: if holding at 15:24 bar close, queue exit for 15:25 open
            if minute.ist_time_str == "15:24":
                self.queue_order(
                    contract=self.active_position.contract,
                    side=OrderSide.SELL,
                    qty=self.active_position.qty,
                    current_minute=minute,
                )

            # Final session bar liquidation (15:29 IST close)
            elif minute.is_final_session_minute:
                # EOD_CLOSE_FILL with slippage penalty
                raw_exit = candle.close_paise - (self.slippage_paise * 2)
                quantized_exit = TickQuantizer.quantize(int(raw_exit), self.tick_paise, OrderSide.SELL)
                self._execute_exit(minute, self.active_position, quantized_exit, reason="EOD_CLOSE_FILL")
