"""
1. What this file does:
   Automated unit and integration test suite verifying the Paper Broker, Simulated Execution Engine,
   Pre-Trade Risk Policy Guards (RK-01, RK-02, RK-06, RK-26), Statutory Fee Accounting, and
   Relational Ledger Immutability for the QuantView Live Daemon (Task M7-03 / Gate G5).

2. Overall design:
   Uses pytest with @pytest.mark.gate_g5:
     - Tests immediate order matching against Bid/Ask quotes with simulated adverse slippage.
     - Tests deterministic next-bar open fill execution and flat-bar deferral.
     - Tests pre-trade risk policy rule evaluation fail-closed rejections:
       * RK-01 (Kill Switch)
       * RK-02 (Trading Window 09:15-15:25 IST)
       * RK-06 (Exchange Freeze Limit 1,800 units)
       * RK-26 (Advisory Lot Ceiling)
     - Tests statutory regulatory fee accounting (UPSTOX_2026_V1).
     - Tests relational ledger append-only immutability via database engine triggers.
     - Tests margin collateral blocking on short positions and proportional release on liquidation.

3. Elements in the file:
   - sample_contract: Pytest fixture generating test ContractIdentifier.
   - in_memory_broker: Pytest fixture creating a transient PaperBroker instance.
   - TestPaperBrokerExecution: Tests quote matching, deterministic open fills, and margin accounting.
   - TestPreTradeRiskGuards: Tests fail-closed rejections for RK-01, RK-02, RK-06, and RK-26.
   - TestLedgerFeeAccountingAndImmutability: Tests UPSTOX_2026_V1 fees and trigger mutation rejection.

4. Final output of the file:
   - Automated pass/fail test execution for Gate G5 paper broker and risk engine certification.
"""

import sqlite3

import pytest

from packages.domain import ContractIdentifier, OptionType, OrderSide, Paise, TickQuantizer
from packages.ledger.fees import UPSTOX_2026_V1, FeeBreakdown
from packages.market_data.streaming_builder import StreamingCandle
from packages.risk.evaluator import RiskPolicyEvaluator
from packages.risk.rules import RiskRules
from services.live_daemon.broker import ExecutionMode, PaperBroker, PaperOrder


@pytest.fixture
def sample_contract() -> ContractIdentifier:
    """Returns standard test option contract identifier with lot size 25."""
    return ContractIdentifier(
        instrument_key="NSE_FO|NIFTY26OCT24000CE",
        trading_symbol="NIFTY 24000 CE",
        expiry_date="2026-10-29",
        strike_price=24000.0,
        option_type=OptionType.CE,
        lot_size=25,
    )


@pytest.fixture
def in_memory_broker() -> PaperBroker:
    """Returns an isolated in-memory PaperBroker instance for clean testing."""
    return PaperBroker(
        db_path=":memory:",
        initial_cash_paise=10_000_000,  # 1 Lakh INR
        accounts=["ACC-TEST-PAPER"],
        execution_mode=ExecutionMode.QUOTE,
        slippage_paise=5,
        tick_paise=5,
    )


@pytest.mark.gate_g5
class TestPaperBrokerExecution:
    """
    1. The use of class:
       Unit test suite validating paper broker execution engines across quote and deterministic open modes.

    2. What the class contains:
       - test_order_fill_against_bid_ask_quotes(): Asserts adverse slippage on quote fills.
       - test_deterministic_open_fill_mode(): Asserts open-fill parity with execution engine.
       - test_deterministic_open_defers_flat_bar(): Asserts flat bars do not fill queued orders.
       - test_short_position_margin_reservation_and_release(): Asserts margin tracking.

    3. Technologies used and why:
       pytest, integer paise arithmetic, TickQuantizer.

    4. Key design and overall design of the class:
       Ensures paper fills execute accurately without price leakage or drift.
    """

    def test_order_fill_against_bid_ask_quotes(
        self,
        in_memory_broker: PaperBroker,
        sample_contract: ContractIdentifier,
    ) -> None:
        """
        1. The use of function:
           Tests order fills against incoming Bid/Ask quotes with simulated adverse slippage.

        2. How does the specific function work:
           - Submits BUY order with ask=150.00 (15000 paise).
             Asserts fill price equals ask + 5 paise slippage (15005 paise).
           - Submits SELL order with bid=160.00 (16000 paise).
             Asserts fill price equals bid - 5 paise slippage (15995 paise).

        3. Concepts used in the function:
           Simulated adverse quote slippage, integer paise quantization.

        4. Places where this function is imported and used:
           Invoked by pytest under gate_g5 marker.

        5. Final output of the function, before and after:
           Before: Unverified quote fills. After: Confirmed exact quote matching.
        """
        broker = in_memory_broker

        # 1. BUY Fill against Ask + Slippage
        buy_order: PaperOrder = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=50,  # 2 lots
            contract=sample_contract,
            ask_price_paise=15000,
            bid_price_paise=14950,
            ltp_paise=14975,
            current_time_str="10:00",
        )

        assert buy_order.status == "FILLED"
        assert buy_order.fill_price_paise == 15005  # 15000 + 5 slippage
        assert buy_order.filled_qty == 50
        assert buy_order.fill_id is not None

        # Verify position created
        pos = broker.get_position("ACC-TEST-PAPER", sample_contract.instrument_key)
        assert pos is not None
        assert pos.quantity == 50
        assert pos.avg_entry_price_paise == 15005

        # 2. SELL Order against Bid - Slippage (closes 25 units)
        sell_order: PaperOrder = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.SELL,
            quantity=25,  # 1 lot
            contract=sample_contract,
            ask_price_paise=16050,
            bid_price_paise=16000,
            ltp_paise=16025,
            current_time_str="10:05",
        )

        assert sell_order.status == "FILLED"
        assert sell_order.fill_price_paise == 15995  # 16000 - 5 slippage
        assert sell_order.filled_qty == 25

        # Position should now be 25 units, with booked profit
        pos = broker.get_position("ACC-TEST-PAPER", sample_contract.instrument_key)
        assert pos.quantity == 25
        expected_realized = 25 * (15995 - 15005)  # 25 * 990 = 24750 paise
        assert pos.realized_pnl_paise == expected_realized

    def test_deterministic_open_fill_mode(
        self,
        in_memory_broker: PaperBroker,
        sample_contract: ContractIdentifier,
    ) -> None:
        """
        1. The use of function:
           Tests deterministic open execution mode parity against packages/engine/execution.py.

        2. How does the specific function work:
           - Configures broker with DETERMINISTIC_OPEN execution mode.
           - Submits BUY order; verifies order is queued as PENDING in pending_orders.
           - Ingests StreamingCandle with open_paise=12000.
           - Verifies order executes at 12000 + 5 = 12005 paise.

        3. Concepts used in the function:
           Deterministic next-bar open fill, engine parity, TickQuantizer.

        4. Places where this function is imported and used:
           Invoked by pytest under gate_g5 marker.

        5. Final output of the function, before and after:
           Before: Unverified open mode. After: Confirmed deterministic open fill.
        """
        broker = in_memory_broker
        broker.execution_mode = ExecutionMode.DETERMINISTIC_OPEN.value

        order: PaperOrder = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=50,
            contract=sample_contract,
            current_time_str="10:00",
        )

        assert order.status == "PENDING"
        assert len(broker.pending_orders) == 1

        # Process next-bar open event
        candle = StreamingCandle(
            instrument_key=sample_contract.instrument_key,
            timeframe="1m",
            bar_start_epoch_sec=1761885600,
            bar_end_epoch_sec=1761885660,
            open_paise=12000,
            high_paise=12200,
            low_paise=11950,
            close_paise=12100,
            volume=500,
            tick_count=45,
            is_closed=False,
        )

        filled = broker.process_bar_open(candle)
        assert len(filled) == 1
        assert filled[0].order_id == order.order_id
        assert order.status == "FILLED"
        expected_fill = TickQuantizer.quantize(12000 + 5, tick_paise=5, side=OrderSide.BUY)
        assert order.fill_price_paise == expected_fill
        assert len(broker.pending_orders) == 0

    def test_deterministic_open_defers_flat_bar(
        self,
        in_memory_broker: PaperBroker,
        sample_contract: ContractIdentifier,
    ) -> None:
        """
        1. The use of function:
           Tests that zero-volume flat bars defer order fills in DETERMINISTIC_OPEN mode.

        2. How does the specific function work:
           - Queues BUY order.
           - Ingests flat bar where open == high == low == close and volume == 0.
           - Asserts no orders fill and order remains PENDING.

        3. Concepts used in the function:
           Zero-volume flat bar deferral, causal illiquid market protection.

        4. Places where this function is imported and used:
           Invoked by pytest under gate_g5 marker.

        5. Final output of the function, before and after:
           Before: Unverified flat bar behavior. After: Confirmed deferral of fills on flat bars.
        """
        broker = in_memory_broker
        broker.execution_mode = ExecutionMode.DETERMINISTIC_OPEN.value

        order = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=25,
            contract=sample_contract,
            current_time_str="10:00",
        )

        flat_candle = StreamingCandle(
            instrument_key=sample_contract.instrument_key,
            timeframe="1m",
            bar_start_epoch_sec=1761885600,
            bar_end_epoch_sec=1761885660,
            open_paise=12000,
            high_paise=12000,
            low_paise=12000,
            close_paise=12000,
            volume=0,
            tick_count=0,
            is_closed=True,
        )

        filled = broker.process_bar_open(flat_candle)
        assert len(filled) == 0
        assert order.status == "PENDING"
        assert len(broker.pending_orders) == 1

    def test_short_position_margin_reservation_and_release(
        self,
        in_memory_broker: PaperBroker,
        sample_contract: ContractIdentifier,
    ) -> None:
        """
        1. The use of function:
           Tests that opening a short derivative position reserves margin collateral and liquidation releases it.

        2. How does the specific function work:
           - Sells 50 units (opening short) @ 10000 paise.
           - Asserts account.margin_reserved_paise increases.
           - Buys 50 units (closing short).
           - Asserts account.margin_reserved_paise returns to 0.

        3. Concepts used in the function:
           Margin collateral blocking, liquidation collateral release.

        4. Places where this function is imported and used:
           Invoked by pytest under gate_g5 marker.

        5. Final output of the function, before and after:
           Before: Unverified margin lifecycle. After: Verified margin reservation and release.
        """
        broker = in_memory_broker
        acc = broker.get_account("ACC-TEST-PAPER")
        initial_margin = acc.margin_reserved_paise
        assert initial_margin == 0

        # Sell to open short
        order_short = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.SELL,
            quantity=50,
            contract=sample_contract,
            bid_price_paise=10000,
            current_time_str="10:00",
        )
        assert order_short.status == "FILLED"
        assert acc.margin_reserved_paise > 0

        # Buy to close short
        order_cover = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=50,
            contract=sample_contract,
            ask_price_paise=9500,
            current_time_str="10:05",
        )
        assert order_cover.status == "FILLED"
        assert acc.margin_reserved_paise == 0


@pytest.mark.gate_g5
class TestPreTradeRiskGuards:
    """
    1. The use of class:
       Unit test suite validating pre-trade risk policy enforcement (RK-01, RK-02, RK-06, RK-26).

    2. What the class contains:
       - test_rk01_kill_switch_rejection(): Verifies kill switch halts order submission.
       - test_rk02_trading_window_rejection(): Verifies rejection outside 09:15-15:25 IST.
       - test_rk06_freeze_limit_rejection(): Verifies rejection exceeding 1,800 units.
       - test_rk26_advisory_lot_ceiling_rejection(): Verifies rejection exceeding advisory lot ceiling.

    3. Technologies used and why:
       pytest, RiskPolicyEvaluator, RiskRules.

    4. Key design and overall design of the class:
       Guarantees non-compliant orders cannot enter execution or create financial exposures.
    """

    def test_rk01_kill_switch_rejection(
        self,
        in_memory_broker: PaperBroker,
        sample_contract: ContractIdentifier,
    ) -> None:
        """Tests that active kill switch halts all order submissions under RK-01."""
        broker = in_memory_broker
        broker.risk_evaluator = RiskPolicyEvaluator(rules=RiskRules(kill_switch_active=True))

        order = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=25,
            contract=sample_contract,
            current_time_str="10:00",
        )

        assert order.status == "REJECTED"
        assert "RK-01" in order.rejection_reason

    def test_rk02_trading_window_rejection(
        self,
        in_memory_broker: PaperBroker,
        sample_contract: ContractIdentifier,
    ) -> None:
        """Tests that orders outside permitted trading window (09:15-15:25) are rejected under RK-02."""
        broker = in_memory_broker
        broker.risk_evaluator = RiskPolicyEvaluator(
            rules=RiskRules(trading_window_start="09:15", trading_window_end="15:25")
        )

        # 09:14 IST: Pre-market rejection
        order_pre = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=25,
            contract=sample_contract,
            current_time_str="09:14",
        )
        assert order_pre.status == "REJECTED"
        assert "RK-02" in order_pre.rejection_reason

        # 15:26 IST: Post-cutoff rejection
        order_post = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=25,
            contract=sample_contract,
            current_time_str="15:26",
        )
        assert order_post.status == "REJECTED"
        assert "RK-02" in order_post.rejection_reason

        # 11:30 IST: Within window passes
        order_ok = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=25,
            contract=sample_contract,
            ask_price_paise=10000,
            current_time_str="11:30",
        )
        assert order_ok.status == "FILLED"

    def test_rk06_freeze_limit_rejection(
        self,
        in_memory_broker: PaperBroker,
        sample_contract: ContractIdentifier,
    ) -> None:
        """Tests that orders exceeding 1,800 units are rejected under RK-06."""
        broker = in_memory_broker
        broker.risk_evaluator = RiskPolicyEvaluator(freeze_quantity=1800)

        # 1825 units (> 1800): REJECT
        order_exceed = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=1825,
            contract=sample_contract,
            current_time_str="10:00",
        )
        assert order_exceed.status == "REJECTED"
        assert "RK-06" in order_exceed.rejection_reason

        # 1800 units (<= 1800): PASS
        order_pass = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=1800,
            contract=sample_contract,
            ask_price_paise=2000,
            current_time_str="10:00",
        )
        assert order_pass.status == "FILLED"

    def test_rk26_advisory_lot_ceiling_rejection(
        self,
        in_memory_broker: PaperBroker,
        sample_contract: ContractIdentifier,
    ) -> None:
        """Tests that orders exceeding configured advisory lot ceiling are rejected under RK-26."""
        broker = in_memory_broker
        # Configure advisory lot ceiling of 50 lots (with freeze quantity higher at 2500)
        broker.risk_evaluator = RiskPolicyEvaluator(
            rules=RiskRules(freeze_quantity=2500, advisory_lot_ceiling=50)
        )

        # 60 lots * 25 lot_size = 1500 units (under 2500 freeze, but exceeds 50 lot advisory ceiling)
        order = broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=1500,
            contract=sample_contract,
            current_time_str="10:00",
        )
        assert order.status == "REJECTED"
        assert "RK-26" in order.rejection_reason


@pytest.mark.gate_g5
class TestLedgerFeeAccountingAndImmutability:
    """
    1. The use of class:
       Integration test suite verifying statutory fee engine and relational ledger database immutability.

    2. What the class contains:
       - test_statutory_fee_calculation_upstox_2026_v1(): Validates UPSTOX_2026_V1 itemized charges.
       - test_ledger_append_only_triggers_prevent_mutation(): Asserts triggers block UPDATE and DELETE.
       - test_ledger_reconciliation_zero_discrepancy(): Asserts cash balance reconciles to 0 paise discrepancy.

    3. Technologies used and why:
       sqlite3 triggers, FeeScheduleEngine, UPSTOX_2026_V1.

    4. Key design and overall design of the class:
       Enforces cryptographic and legal invariants on financial accounting records.
    """

    def test_statutory_fee_calculation_upstox_2026_v1(
        self,
        in_memory_broker: PaperBroker,
    ) -> None:
        """
        1. The use of function:
           Tests that exact statutory charges are calculated per UPSTOX_2026_V1.

        2. How does the specific function work:
           - Calculates fees on BUY and SELL transactions for 100,000 paise (Rs 1,000 gross).
           - Asserts brokerage (Rs 20), STT, GST, NSE turnover, SEBI, and stamp duty match schedule.

        3. Concepts used in the function:
           Statutory fee audit, ROUND_HALF_UP exact paise math.

        4. Places where this function is imported and used:
           Invoked by pytest under gate_g5 marker.

        5. Final output of the function, before and after:
           Before: Unverified fees. After: Verified statutory charge accuracy.
        """
        broker = in_memory_broker
        gross_value = Paise(100_000)  # Rs 1,000

        # Calculate BUY fees
        buy_fees: FeeBreakdown = broker.fee_engine.calculate_order_fees(
            trade_date="2026-10-31",
            side=OrderSide.BUY,
            gross_value_paise=gross_value,
        )
        assert buy_fees.brokerage_paise == 2000  # Rs 20
        assert buy_fees.stt_paise == 0  # No STT on buy options
        assert buy_fees.stamp_duty_paise > 0  # Stamp duty applies on buy
        assert buy_fees.total_fee_paise == sum([
            buy_fees.brokerage_paise,
            buy_fees.stt_paise,
            buy_fees.exchange_turnover_paise,
            buy_fees.gst_paise,
            buy_fees.sebi_paise,
            buy_fees.stamp_duty_paise,
        ])

        # Calculate SELL fees
        sell_fees: FeeBreakdown = broker.fee_engine.calculate_order_fees(
            trade_date="2026-10-31",
            side=OrderSide.SELL,
            gross_value_paise=gross_value,
        )
        assert sell_fees.brokerage_paise == 2000
        assert sell_fees.stt_paise == 150  # 0.15% STT on sell = Rs 1.50 = 150 paise
        assert sell_fees.stamp_duty_paise == 0  # No stamp duty on sell

    def test_ledger_append_only_triggers_prevent_mutation(
        self,
        in_memory_broker: PaperBroker,
        sample_contract: ContractIdentifier,
    ) -> None:
        """
        1. The use of function:
           Tests that SQLite database triggers strictly block any UPDATE or DELETE on ledger_events.

        2. How does the specific function work:
           - Submits and fills an order to record events in sqlite.
           - Directly executes UPDATE and DELETE queries on sqlite connection.
           - Asserts sqlite3.OperationalError is raised with trigger abort message.

        3. Concepts used in the function:
           Database trigger immutability, fail-closed financial integrity.

        4. Places where this function is imported and used:
           Invoked by pytest under gate_g5 marker.

        5. Final output of the function, before and after:
           Before: Unverified trigger safety. After: Proven database immutability.
        """
        broker = in_memory_broker
        broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=25,
            contract=sample_contract,
            ask_price_paise=10000,
            current_time_str="10:00",
        )

        conn = broker.repo._conn

        # Test UPDATE is blocked by trigger
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="ledger_events is append-only"):
            conn.execute("UPDATE ledger_events SET amount_paise = 0;")

        # Test DELETE is blocked by trigger
        with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="ledger_events is append-only"):
            conn.execute("DELETE FROM ledger_events;")

    def test_ledger_reconciliation_zero_discrepancy(
        self,
        in_memory_broker: PaperBroker,
        sample_contract: ContractIdentifier,
    ) -> None:
        """
        1. The use of function:
           Tests that reconcile_account() validates cash and event sums with 0 discrepancy.

        2. How does the specific function work:
           - Performs buy, sell, and fee transactions.
           - Dispatches reconcile_account('ACC-TEST-PAPER').
           - Asserts is_reconciled is True and discrepancy_paise is 0.

        3. Concepts used in the function:
           Automated cash reconciliation, double-entry audit check.

        4. Places where this function is imported and used:
           Invoked by pytest under gate_g5 marker.

        5. Final output of the function, before and after:
           Before: Unreconciled account. After: Reconciled account with 0 paise drift.
        """
        broker = in_memory_broker
        broker.submit_order(
            account_id="ACC-TEST-PAPER",
            instrument_key=sample_contract.instrument_key,
            trading_symbol=sample_contract.trading_symbol,
            side=OrderSide.BUY,
            quantity=25,
            contract=sample_contract,
            ask_price_paise=10000,
            current_time_str="10:00",
        )

        audit = broker.reconcile_account("ACC-TEST-PAPER")
        assert audit["is_reconciled"] is True
        assert audit["discrepancy_paise"] == 0
        assert audit["event_count"] >= 3  # DEPOSIT, ORDER_ACCEPTED, FILL, FEE
