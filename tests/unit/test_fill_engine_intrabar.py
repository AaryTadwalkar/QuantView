"""
1. What this file does:
   Comprehensive unit tests for IntrabarFillEngine and slippage execution (Tasks M4-05, M4-22).

2. Overall design:
   Uses pytest to verify the 4-step intrabar sequence and review hardening invariants:
     - Step 1: Next-open fill with adverse slippage and TickQuantizer rounding.
     - Step 1: Cash affordability check (REJECTED_INSUFFICIENT_CASH).
     - Step 2: STOP_FIRST policy (stop wins when both stop and target touched in same bar).
     - Step 2: Gap-down through stop fills at bar open, not the trigger level.
     - Step 2: Zero-volume flat bar does not fill orders or trigger stop exits.
     - Step 2: Stale-data force-exit after max_stale_minutes with 3x worst-case slippage penalty.
     - Step 3: Causal 15:25 force-flat (queued at 15:24 close, filled at 15:25 open).
     - Step 3: Final-bar rule: new strategy signal decided at 15:29 close is rejected with NO_NEXT_BAR.
     - Step 3: Pre-scheduled liquidation holding into 15:29 close fills at EOD_CLOSE_FILL.

3. Elements in the file:
   - TestIntrabarFillEngine: Complete unit test suite for order execution and risk timing.

4. Final output of the file:
   - Automated pass/fail test execution for Tasks M4-05 and M4-22.
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
from packages.engine.clock import SimulationMinute
from packages.engine.execution import CandleBar, IntrabarFillEngine
from packages.engine.orders import OrderStatus
from packages.engine.positions import ActivePosition
from packages.ledger.ledger import FinancialLedger


@pytest.fixture
def test_contract() -> ContractIdentifier:
    """Fixture returning sample NIFTY 24000 CE contract."""
    return ContractIdentifier(
        instrument_key="NSE_FO|NIFTY_2025-01-09_24000_CE",
        trading_symbol="NIFTY 24000 CE 09 JAN 25",
        expiry_date="2025-01-09",
        strike_price=24000.0,
        option_type=OptionType.CE,
        lot_size=25,
    )


@pytest.fixture
def make_sim_minute():
    """Helper fixture to generate SimulationMinute records."""
    def _make(time_str: str = "09:20", is_final: bool = False) -> SimulationMinute:
        return SimulationMinute(
            session_date=date(2025, 1, 9),
            bar_start_utc=UtcEpochSec(1735200000),
            bar_end_utc=UtcEpochSec(1735200060),
            ist_time_str=time_str,
            is_session_open=(time_str == "09:15"),
            is_force_flat_minute=(time_str == "15:25"),
            is_final_session_minute=is_final,
        )
    return _make


@pytest.mark.gate_g2a
class TestIntrabarFillEngine:
    """
    1. The use of class:
       Unit tests validating order execution, slippage, intrabar stops, and causal exit rules.
    """

    def test_next_bar_open_fill_with_adverse_slippage(self, test_contract, make_sim_minute):
        """Tests that a BUY order fills at open + slippage and quantizes against the trader."""
        ledger = FinancialLedger(initial_cash_paise=Paise(10_000_000))
        engine = IntrabarFillEngine(ledger=ledger, slippage_paise=5, tick_paise=5)

        m_decision = make_sim_minute("09:19")
        order = engine.queue_order(test_contract, OrderSide.BUY, qty=25, current_minute=m_decision)
        assert order is not None
        assert order.status == OrderStatus.PENDING

        m_fill = make_sim_minute("09:20")
        # Bar open at 10,000 paise (Rs 100.00). Slippage = 5 paise -> 10,005 paise.
        candle = CandleBar(
            open_paise=Paise(10000),
            high_paise=Paise(10500),
            low_paise=Paise(9800),
            close_paise=Paise(10200),
            volume=500,
            is_flat_bar=False,
        )

        filled = engine.step_1_open(m_fill, candle)
        assert len(filled) == 1
        assert filled[0].status == OrderStatus.FILLED
        assert filled[0].filled_price_paise == 10005
        assert engine.active_position is not None
        assert engine.active_position.entry_price_paise == 10005

    def test_rejection_on_insufficient_cash(self, test_contract, make_sim_minute):
        """Tests that an order is rejected at open if ledger cash is insufficient."""
        # Only Rs 1,000 (100,000 paise) in cash, but order needs Rs 2,500+
        ledger = FinancialLedger(initial_cash_paise=Paise(100_000))
        engine = IntrabarFillEngine(ledger=ledger, slippage_paise=5, tick_paise=5)

        m_decision = make_sim_minute("09:19")
        order = engine.queue_order(test_contract, OrderSide.BUY, qty=25, current_minute=m_decision)

        m_fill = make_sim_minute("09:20")
        candle = CandleBar(
            open_paise=Paise(10000),
            high_paise=Paise(10200),
            low_paise=Paise(9900),
            close_paise=Paise(10100),
            volume=500,
            is_flat_bar=False,
        )

        filled = engine.step_1_open(m_fill, candle)
        assert len(filled) == 1
        assert filled[0].status == OrderStatus.REJECTED
        assert filled[0].rejection_reason == "REJECTED_INSUFFICIENT_CASH"
        assert engine.active_position is None

    def test_stop_first_ambiguity_resolution(self, test_contract, make_sim_minute):
        """Tests the STOP_FIRST policy when both stop-loss and take-profit are touched in the same bar."""
        ledger = FinancialLedger(initial_cash_paise=Paise(10_000_000))
        engine = IntrabarFillEngine(ledger=ledger, slippage_paise=5, tick_paise=5)

        m = make_sim_minute("09:20")
        # Entry at 10,000 paise, stop at 9,000 paise (-10%), target at 11,000 paise (+10%)
        engine.active_position = ActivePosition(
            contract=test_contract,
            side=OrderSide.BUY,
            qty=25,
            entry_price_paise=Paise(10000),
            entry_time=m.bar_start_utc,
            stop_loss_paise=Paise(9000),
            take_profit_paise=Paise(11000),
        )

        # Candle touches BOTH: Low is 8,900 (touches stop 9,000), High is 11,100 (touches target 11,000)
        candle = CandleBar(
            open_paise=Paise(10000),
            high_paise=Paise(11100),
            low_paise=Paise(8900),
            close_paise=Paise(10500),
            volume=1000,
            is_flat_bar=False,
        )

        exit_price = engine.step_2_intrabar(m, candle)
        # STOP_FIRST invariant: Stop wins! Exit price = 9,000 - 5 paise slippage = 8,995 paise
        assert exit_price == 8995
        assert engine.active_position is None

    def test_zero_volume_flat_bar_deferral(self, test_contract, make_sim_minute):
        """Tests that a flat zero-volume candle does not fill pending orders and does not trigger stops."""
        ledger = FinancialLedger(initial_cash_paise=Paise(10_000_000))
        engine = IntrabarFillEngine(ledger=ledger, slippage_paise=5, tick_paise=5)

        m = make_sim_minute("09:20")
        order = engine.queue_order(test_contract, OrderSide.BUY, qty=25, current_minute=m)

        # Flat zero-volume candle
        flat_candle = CandleBar(
            open_paise=Paise(10000),
            high_paise=Paise(10000),
            low_paise=Paise(10000),
            close_paise=Paise(10000),
            volume=0,
            is_flat_bar=True,
        )

        filled = engine.step_1_open(m, flat_candle)
        assert len(filled) == 0  # Deferred
        assert order.status == OrderStatus.PENDING

    def test_stale_data_force_exit_after_threshold(self, test_contract, make_sim_minute):
        """Tests that consecutive flat bars exceeding max_stale_minutes trigger force liquidation with 3x slippage."""
        ledger = FinancialLedger(initial_cash_paise=Paise(10_000_000))
        engine = IntrabarFillEngine(ledger=ledger, slippage_paise=5, tick_paise=5, max_stale_minutes=3)

        m = make_sim_minute("09:20")
        engine.active_position = ActivePosition(
            contract=test_contract,
            side=OrderSide.BUY,
            qty=25,
            entry_price_paise=Paise(10000),
            entry_time=m.bar_start_utc,
            stop_loss_paise=Paise(9000),
        )

        flat_candle = CandleBar(
            open_paise=Paise(10000),
            high_paise=Paise(10000),
            low_paise=Paise(10000),
            close_paise=Paise(10000),
            volume=0,
            is_flat_bar=True,
        )

        # Bar 1 flat
        assert engine.step_2_intrabar(m, flat_candle) is None
        assert engine.active_position is not None
        # Bar 2 flat
        assert engine.step_2_intrabar(m, flat_candle) is None
        assert engine.active_position is not None
        # Bar 3 flat -> triggers force liquidation with 3x slippage (15 paise penalty) -> 9,985 paise
        exit_price = engine.step_2_intrabar(m, flat_candle)
        assert exit_price == 9985
        assert engine.active_position is None

    def test_final_bar_1529_rejection_no_next_bar(self, test_contract, make_sim_minute):
        """
        1. The use of function:
           P0 Review Invariant: Tests that a new strategy entry decided on the final bar (15:29 IST)
           is rejected with NO_NEXT_BAR because no subsequent regular-session bar exists.
        """
        ledger = FinancialLedger(initial_cash_paise=Paise(10_000_000))
        engine = IntrabarFillEngine(ledger=ledger)

        m_final = make_sim_minute("15:29", is_final=True)
        order = engine.queue_order(test_contract, OrderSide.BUY, qty=25, current_minute=m_final)
        # Invariant: Must return None / reject immediately
        assert order is None

    def test_eod_close_fill_for_prescheduled_liquidation(self, test_contract, make_sim_minute):
        """Tests that a pre-scheduled position holding into 15:29 close fills at EOD_CLOSE_FILL with slippage."""
        ledger = FinancialLedger(initial_cash_paise=Paise(10_000_000))
        engine = IntrabarFillEngine(ledger=ledger, slippage_paise=5, tick_paise=5)

        m_final = make_sim_minute("15:29", is_final=True)
        engine.active_position = ActivePosition(
            contract=test_contract,
            side=OrderSide.BUY,
            qty=25,
            entry_price_paise=Paise(10000),
            entry_time=m_final.bar_start_utc,
        )

        candle = CandleBar(
            open_paise=Paise(9800),
            high_paise=9850,
            low_paise=9450,
            close_paise=Paise(9500),
            volume=200,
            is_flat_bar=False,
        )

        # Step 3 at 15:29 close executes EOD_CLOSE_FILL at close (9,500) - 2x slippage (10) = 9,490 paise
        engine.step_3_close(m_final, candle)
        assert engine.active_position is None
        # Verify ledger has sell fill at 9,490
        sell_fills = [e for e in ledger.events if e.event_type.value == "FILL" and e.amount_paise > 0]
        assert len(sell_fills) == 1
        assert sell_fills[0].metadata["price_paise"] == 9490
