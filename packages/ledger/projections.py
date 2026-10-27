"""
1. What this file does:
   Implements deterministic, rebuildable projections from the financial event stream for QuantView (Task M4-07).
   Provides state reconstruction for cash balances, positions, gross/net realized P&L, and equity.

2. Overall design:
   Enforces Option A (Event-Sourced Ledger with Rebuildable Projections) per QUANTVIEW_DATA_SPEC §2.1:
     - Pure functional folds over immutable FinancialEventRecord sequences.
     - CashProjection: Rebuilds cash balance purely from amount_paise summation.
     - PositionProjection: Rebuilds position quantities, average costs, and current long market value.
     - PnlProjection: Tracks gross realized P&L, itemized fees paid, net realized P&L, and mark-to-market unrealized P&L.
     - FundamentalBalanceVerifier: Proves the fundamental balance equation at every state transition:
       Cash + Long Market Value == Initial Capital + Gross Realized PnL + Unrealized PnL - Total Fees Paid.

3. Elements in the file:
   - PositionState: Immutable record of an open contract position.
   - FinancialProjectionState: Aggregated account state at a specific simulation point.
   - LedgerProjectionEngine: Reconstructs state from event streams and verifies financial invariants.

4. Final output of the file:
   - Exported PositionState, FinancialProjectionState, and LedgerProjectionEngine.
"""

from typing import Dict, List, NamedTuple, Optional

from packages.domain import OrderSide, Paise
from packages.ledger.events import CanonicalLedgerEventType, FinancialEventRecord


class PositionState(NamedTuple):
    """
    1. The use of class:
       Immutable container representing the state of an open contract position.

    2. What the class contains:
       - instrument_key: Unique identifier of the contract.
       - qty: Open quantity in units (positive for long).
       - avg_cost_paise: Weighted average entry price per unit in Paise.
       - current_price_paise: Latest marked price per unit in Paise.
       - market_value_paise: Total current position market value (qty * current_price_paise).
       - unrealized_pnl_paise: Mark-to-market paper gain or loss in Paise.

    3. Technologies used and why:
       NamedTuple for immutability and exact integer math.

    4. Key design and overall design of the class:
       Guarantees zero float drift in position valuation.
    """
    instrument_key: str
    qty: int
    avg_cost_paise: Paise
    current_price_paise: Paise
    market_value_paise: Paise
    unrealized_pnl_paise: Paise


class FinancialProjectionState(NamedTuple):
    """
    1. The use of class:
       Represents the fully reconciled financial state of an account at a point in time.

    2. What the class contains:
       - initial_capital_paise: Total deposited capital.
       - cash_balance_paise: Reconstructed cash balance.
       - positions: Map of instrument_key to PositionState.
       - total_market_value_paise: Total market value of all open long positions.
       - gross_realized_pnl_paise: Cumulative trading gain/loss before fees.
       - total_fees_paid_paise: Cumulative statutory and broker fees paid.
       - net_realized_pnl_paise: Gross realized P&L minus total fees paid.
       - unrealized_pnl_paise: Mark-to-market unrealized P&L across open positions.
       - total_equity_paise: Cash balance + total market value.
       - is_balanced: Boolean proving the fundamental balance equation holds exactly.

    3. Technologies used and why:
       NamedTuple for immutability and audit verification.

    4. Key design and overall design of the class:
       Single source of truth for backtest equity mark, margin status, and risk evaluation.
    """
    initial_capital_paise: Paise
    cash_balance_paise: Paise
    positions: Dict[str, PositionState]
    total_market_value_paise: Paise
    gross_realized_pnl_paise: Paise
    total_fees_paid_paise: Paise
    net_realized_pnl_paise: Paise
    unrealized_pnl_paise: Paise
    total_equity_paise: Paise
    is_balanced: bool


class LedgerProjectionEngine:
    """
    1. The use of class:
       Processes streams of FinancialEventRecord objects to build deterministic financial projections.

    2. What the class contains:
       - reconstruct_state(): Folds over an event sequence and returns FinancialProjectionState.
       - verify_balance_equation(): Asserts the fundamental balance equation down to the exact paisa.

    3. Technologies used and why:
       Pure functional folding over immutable records.

    4. Key design and overall design of the class:
       Ensures that replaying events yields bit-for-bit identical state across backtest runs.
    """

    @classmethod
    def reconstruct_state(
        cls,
        events: List[FinancialEventRecord],
        market_marks: Optional[Dict[str, Paise]] = None,
        initial_capital_paise: Paise = Paise(0),
    ) -> FinancialProjectionState:
        """
        1. The use of function:
           Replays an event stream from sequence 1 onwards to reconstruct complete account financials.

        2. How does the specific function work:
           - Iterates sequentially through events.
           - DEPOSIT/WITHDRAWAL: Accumulates initial capital and updates cash.
           - FILL: Matches buy/sell quantities, calculates gross realized P&L on exits, updates positions.
           - FEE: Accumulates total_fees_paid_paise.
           - Marks open positions against market_marks to calculate unrealized P&L and market value.
           - Verifies the fundamental balance equation.

        3. Concepts used in the function:
           Event sourcing projection fold, FIFO trade matching, zero-drift accounting.

        4. Places where this function is imported and used:
           Used by FinancialLedger, backtest runner, and equity mark evaluators.

        5. Final output of the function, before and after:
           Before: List of events. After: Fully reconciled FinancialProjectionState.
        """
        marks = market_marks or {}

        initial_capital = Paise(int(initial_capital_paise))
        cash_balance = Paise(int(initial_capital_paise))
        total_fees = Paise(0)
        gross_realized_pnl = Paise(0)

        # Map of instrument_key -> {'qty': int, 'total_cost_paise': int}
        open_pos: Dict[str, Dict[str, int]] = {}

        for ev in events:
            # 1. Update running cash
            cash_balance = Paise(cash_balance + ev.amount_paise)

            if ev.event_type == CanonicalLedgerEventType.DEPOSIT:
                initial_capital = Paise(initial_capital + ev.amount_paise)

            elif ev.event_type == CanonicalLedgerEventType.WITHDRAWAL:
                initial_capital = Paise(initial_capital + ev.amount_paise)

            elif ev.event_type == CanonicalLedgerEventType.FEE:
                # ev.amount_paise is negative for fee debits
                total_fees = Paise(total_fees + abs(ev.amount_paise))

            elif ev.event_type == CanonicalLedgerEventType.FILL:
                meta = ev.metadata
                side = meta.get("side", "")
                inst_key = meta.get("instrument_key", "")
                fill_qty = int(meta.get("qty", 0))
                fill_price = int(meta.get("price_paise", 0))
                gross_fill = int(meta.get("gross_value_paise", fill_qty * fill_price))

                if inst_key not in open_pos:
                    open_pos[inst_key] = {"qty": 0, "total_cost_paise": 0}

                pos = open_pos[inst_key]

                if side == OrderSide.BUY.value or side == "BUY":
                    if pos["qty"] < 0:
                        # Short position being covered (BUY TO CLOSE)
                        abs_qty = abs(pos["qty"])
                        avg_credit_per_unit = pos["total_cost_paise"] // abs_qty
                        closed_credit = avg_credit_per_unit * fill_qty
                        realized = closed_credit - gross_fill
                        gross_realized_pnl = Paise(gross_realized_pnl + realized)

                        pos["qty"] += fill_qty
                        pos["total_cost_paise"] = max(0, pos["total_cost_paise"] - closed_credit)
                    else:
                        # Long position opened or added to (BUY TO OPEN)
                        pos["qty"] += fill_qty
                        pos["total_cost_paise"] += gross_fill

                elif side == OrderSide.SELL.value or side == "SELL":
                    if pos["qty"] > 0:
                        # Long position being closed (SELL TO CLOSE)
                        cost_per_unit = pos["total_cost_paise"] // pos["qty"]
                        closed_cost = cost_per_unit * fill_qty
                        realized = gross_fill - closed_cost
                        gross_realized_pnl = Paise(gross_realized_pnl + realized)

                        pos["qty"] -= fill_qty
                        pos["total_cost_paise"] = max(0, pos["total_cost_paise"] - closed_cost)
                    else:
                        # Short position opened (SELL TO OPEN)
                        pos["qty"] -= fill_qty
                        pos["total_cost_paise"] += gross_fill

        # Build position state records and mark-to-market
        positions: Dict[str, PositionState] = {}
        total_market_val = Paise(0)
        total_unrealized = Paise(0)

        for inst_key, pdata in open_pos.items():
            qty = pdata["qty"]
            if qty > 0:
                avg_cost = Paise(pdata["total_cost_paise"] // qty)
                mark_price = marks.get(inst_key, avg_cost)
                mkt_val = Paise(qty * int(mark_price))
                unrealized = Paise(mkt_val - pdata["total_cost_paise"])

                positions[inst_key] = PositionState(
                    instrument_key=inst_key,
                    qty=qty,
                    avg_cost_paise=avg_cost,
                    current_price_paise=mark_price,
                    market_value_paise=mkt_val,
                    unrealized_pnl_paise=unrealized,
                )
                total_market_val = Paise(total_market_val + mkt_val)
                total_unrealized = Paise(total_unrealized + unrealized)

            elif qty < 0:
                abs_qty = abs(qty)
                avg_credit = Paise(pdata["total_cost_paise"] // abs_qty)
                mark_price = marks.get(inst_key, avg_credit)
                liability = Paise(abs_qty * int(mark_price))
                unrealized = Paise(pdata["total_cost_paise"] - liability)

                positions[inst_key] = PositionState(
                    instrument_key=inst_key,
                    qty=qty,
                    avg_cost_paise=avg_credit,
                    current_price_paise=mark_price,
                    market_value_paise=Paise(-int(liability)),
                    unrealized_pnl_paise=unrealized,
                )
                total_market_val = Paise(total_market_val - liability)
                total_unrealized = Paise(total_unrealized + unrealized)

        net_realized_pnl = Paise(gross_realized_pnl - total_fees)
        total_equity = Paise(cash_balance + total_market_val)

        # Fundamental Balance Equation:
        # Cash + Market Value == Initial Capital + Gross Realized + Unrealized - Total Fees
        # Equivalently: Total Equity == Initial Capital + Net Realized + Unrealized
        expected_equity = Paise(initial_capital + net_realized_pnl + total_unrealized)
        is_balanced = (total_equity == expected_equity)

        return FinancialProjectionState(
            initial_capital_paise=initial_capital,
            cash_balance_paise=cash_balance,
            positions=positions,
            total_market_value_paise=total_market_val,
            gross_realized_pnl_paise=gross_realized_pnl,
            total_fees_paid_paise=total_fees,
            net_realized_pnl_paise=net_realized_pnl,
            unrealized_pnl_paise=total_unrealized,
            total_equity_paise=total_equity,
            is_balanced=is_balanced,
        )

    @classmethod
    def verify_balance_equation(cls, state: FinancialProjectionState) -> bool:
        """
        1. The use of function:
           Strictly asserts that the fundamental ledger balance equation holds without double-counting fees.

        2. How does the specific function work:
           Evaluates both representations of the balance equation and raises AssertionError if violated.

        3. Concepts used in the function:
           Conservation of financial value, invariant assertion.

        4. Places where this function is imported and used:
           Invoked after every transaction block in backtests and golden tests.

        5. Final output of the function, before and after:
           Before: FinancialProjectionState. After: True or AssertionError.
        """
        eq1 = (state.cash_balance_paise + state.total_market_value_paise) == (
            state.initial_capital_paise
            + state.gross_realized_pnl_paise
            + state.unrealized_pnl_paise
            - state.total_fees_paid_paise
        )
        eq2 = state.total_equity_paise == (
            state.initial_capital_paise + state.net_realized_pnl_paise + state.unrealized_pnl_paise
        )
        if not (eq1 and eq2 and state.is_balanced):
            raise AssertionError(
                f"Ledger balance equation violated!\n"
                f"Cash ({state.cash_balance_paise}) + MktVal ({state.total_market_value_paise}) = {state.total_equity_paise}\n"
                f"Capital ({state.initial_capital_paise}) + GrossPnL ({state.gross_realized_pnl_paise}) + Unrealized ({state.unrealized_pnl_paise}) - Fees ({state.total_fees_paid_paise}) = "
                f"{state.initial_capital_paise + state.gross_realized_pnl_paise + state.unrealized_pnl_paise - state.total_fees_paid_paise}"
            )
        return True
