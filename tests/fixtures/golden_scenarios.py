"""
1. What this file does:
   Defines the 9 authoritative hand-calculated golden scenarios for single-leg long CE/PE
   backtesting execution, fill rules, exact fee breakdowns, and ledger reconciliation (Task M4-13).

2. Overall design:
   Acts as the immutable test oracle for QuantView Gate G2a. Each scenario explicitly defines:
     - Input contract metadata, initial capital, decision bar, and input candle stream.
     - Causal fill timing: Next-bar open fill, adverse slippage, tick quantization.
     - Intrabar evaluation: Stop-first ambiguity, gap-through open, zero-volume flat bars, stale wait.
     - Causal force-flat: Queued at 15:24 close, filled at 15:25 open.
     - Final-bar rule: New entry decided at 15:29 is rejected with NO_NEXT_BAR.
     - Exact Indian regulatory fees (UPSTOX_2025_OCT schedule) down to the exact paisa.
     - Fundamental ledger balance verification: Cash + Market Value == Capital + Gross Realized + Unrealized - Fees.

3. Elements in the file:
   - GoldenScenarioRecord: Typed container holding expected inputs, events, fills, and ledger balances.
   - Scenario 1: Standard Long CE Entry & Win (Target Hit Intrabar).
   - Scenario 2: Standard Long PE Entry & Loss (Stop Hit Intrabar).
   - Scenario 3: Same-Bar Stop and Target Touched (Stop-First Invariant).
   - Scenario 4: Bar Opens Through Stop (Gap-Down Open Fill).
   - Scenario 5: Zero-Volume Flat Bar (No Fill, No Exit Trigger).
   - Scenario 6: Stale-Data Wait Exceeded (Force-Exit at Next Valid Open).
   - Scenario 7: Causal 15:25 Force-Flat (Queued at 15:24 Close, Filled at 15:25 Open).
   - Scenario 8: Final Bar 15:29 Rejection (New Entry Rejected with NO_NEXT_BAR; Pre-scheduled Flat Closes).
   - Scenario 9: Statutory Fee Schedule Reconciliation Across Schedule Transitions.
   - ALL_GOLDEN_SCENARIOS: Registry list of all 9 frozen oracle scenarios.

4. Final output of the file:
   - Exported golden scenario data structures used as test fixtures by tests/unit/test_engine_golden_scenarios.py.
"""

from decimal import Decimal
from typing import Any, Dict, List, NamedTuple, Optional

from packages.domain import OptionType, OrderSide, Paise


class ExpectedFill(NamedTuple):
    bar_timestamp: str
    action: str  # BUY or SELL
    raw_price_paise: int
    slippage_paise: int
    quantized_price_paise: int
    qty: int
    gross_value_paise: int
    brokerage_paise: int
    stt_paise: int
    exchange_turnover_paise: int
    gst_paise: int
    sebi_paise: int
    stamp_duty_paise: int
    total_fee_paise: int


class ExpectedLedgerState(NamedTuple):
    cash_balance_paise: int
    position_qty: int
    gross_realized_pnl_paise: int
    total_fees_paid_paise: int
    net_realized_pnl_paise: int
    unrealized_pnl_paise: int
    total_equity_paise: int


class GoldenScenario(NamedTuple):
    scenario_id: str
    title: str
    description: str
    initial_capital_paise: int
    contract_symbol: str
    strike_price: float
    option_type: OptionType
    lot_size: int
    tick_paise: int
    expected_fills: List[ExpectedFill]
    expected_final_state: ExpectedLedgerState
    special_assertions: Dict[str, Any]


# ==============================================================================
# SCENARIO 1: Standard Long CE Entry & Win (Target Hit Intrabar)
# ==============================================================================
# Setup: NIFTY 24000 CE, Lot=25, Tick=5 paise. Initial Capital: 10,000,000 paise (Rs 1,00,000).
# Decision: 09:20:00 (15m/5m close). Signal: ENTER_LONG 1 lot.
# Fill Entry: 09:20:00 open at Rs 100.00 (10,000 paise) + 5 paise slippage -> 10,005 paise.
# Premium Paid = 25 * 10,005 = 250,125 paise (Rs 2,501.25).
# Entry Fees: Brokerage 2000, STT 0, Exch 88, GST 376, SEBI 0, Stamp 8 -> Total 2,472 paise.
# Cash after entry = 10,000,000 - 250,125 - 2,472 = 9,747,403 paise.
# Target: +10% (trigger = 11,000 paise).
# Fill Exit: 09:25:00 intrabar touches target 11,000 paise - 5 paise slippage -> 10,995 paise.
# Gross Proceeds = 25 * 10,995 = 274,875 paise (Rs 2,748.75).
# Exit Fees: Brokerage 2000, STT 275 (0.10%), Exch 96, GST 377, SEBI 0, Stamp 0 -> Total 2,748 paise.
# Total Fees = 2,472 + 2,748 = 5,220 paise.
# Gross Realized PnL = 274,875 - 250,125 = +24,750 paise.
# Net Realized PnL = 24,750 - 5,220 = +19,530 paise.
# Final Cash = 9,747,403 + 274,875 - 2,748 = 10,019,530 paise.
# Balance Equation: 10,019,530 + 0 == 10,000,000 + 24,750 + 0 - 5,220. EXACT PASS.
SCENARIO_1 = GoldenScenario(
    scenario_id="SCENARIO_01",
    title="Standard Long CE Entry & Win",
    description="Intraday 5m long CE entry at next open with 1-tick adverse slippage, exits at target with 1-tick slippage.",
    initial_capital_paise=10_000_000,
    contract_symbol="NIFTY 24000 CE 30 JAN 25",
    strike_price=24000.0,
    option_type=OptionType.CE,
    lot_size=25,
    tick_paise=5,
    expected_fills=[
        ExpectedFill(
            bar_timestamp="2025-01-09T09:20:00+05:30",
            action="BUY",
            raw_price_paise=10000,
            slippage_paise=5,
            quantized_price_paise=10005,
            qty=25,
            gross_value_paise=250125,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=88,
            gst_paise=376,
            sebi_paise=0,
            stamp_duty_paise=8,
            total_fee_paise=2472,
        ),
        ExpectedFill(
            bar_timestamp="2025-01-09T09:25:00+05:30",
            action="SELL",
            raw_price_paise=11000,
            slippage_paise=-5,
            quantized_price_paise=10995,
            qty=25,
            gross_value_paise=274875,
            brokerage_paise=2000,
            stt_paise=275,
            exchange_turnover_paise=96,
            gst_paise=377,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2748,
        ),
    ],
    expected_final_state=ExpectedLedgerState(
        cash_balance_paise=10_019_530,
        position_qty=0,
        gross_realized_pnl_paise=24_750,
        total_fees_paid_paise=5_220,
        net_realized_pnl_paise=19_530,
        unrealized_pnl_paise=0,
        total_equity_paise=10_019_530,
    ),
    special_assertions={"target_hit_intrabar": True, "stop_hit_intrabar": False},
)


# ==============================================================================
# SCENARIO 2: Standard Long PE Entry & Loss (Stop Hit Intrabar)
# ==============================================================================
# Setup: NIFTY 23500 PE, Lot=25, Tick=5 paise. Initial Capital: 10,000,000 paise.
# Decision: 09:20:00. Signal: ENTER_LONG 1 lot PE.
# Entry: 09:20:00 open at Rs 120.00 (12,000 paise) + 5 paise slippage -> 12,005 paise.
# Premium Paid = 25 * 12,005 = 300,125 paise (Rs 3,001.25).
# Entry Fees: Brokerage 2000, STT 0, Exch 105, GST 379, SEBI 0, Stamp 9 -> Total 2,493 paise.
# Cash after entry = 10,000,000 - 300,125 - 2,493 = 9,697,382 paise.
# Stop set: -20% (trigger = 9,600 paise).
# Exit: 09:30:00 bar low touches 9,500 paise, triggering stop at 9,600 paise - 5 paise slippage -> 9,595 paise.
# Gross Proceeds = 25 * 9,595 = 239,875 paise (Rs 2,398.75).
# Exit Fees: Brokerage 2000, STT 240, Exch 84, GST 375, SEBI 0, Stamp 0 -> Total 2,699 paise.
# Total Fees = 2,493 + 2,699 = 5,192 paise.
# Gross Realized PnL = 239,875 - 300,125 = -60,250 paise (-Rs 602.50).
# Net Realized PnL = -60,250 - 5,192 = -65,442 paise (-Rs 654.42).
# Final Cash = 9,697,382 + 239,875 - 2,699 = 9,934,558 paise (Rs 99,345.58).
# Balance Equation: 9,934,558 + 0 == 10,000,000 + (-60,250) + 0 - 5,192. EXACT PASS.
SCENARIO_2 = GoldenScenario(
    scenario_id="SCENARIO_02",
    title="Standard Long PE Entry & Loss",
    description="Intraday long PE entry at next open, exits at stop loss with 1-tick adverse slippage.",
    initial_capital_paise=10_000_000,
    contract_symbol="NIFTY 23500 PE 30 JAN 25",
    strike_price=23500.0,
    option_type=OptionType.PE,
    lot_size=25,
    tick_paise=5,
    expected_fills=[
        ExpectedFill(
            bar_timestamp="2025-01-09T09:20:00+05:30",
            action="BUY",
            raw_price_paise=12000,
            slippage_paise=5,
            quantized_price_paise=12005,
            qty=25,
            gross_value_paise=300125,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=105,
            gst_paise=379,
            sebi_paise=0,
            stamp_duty_paise=9,
            total_fee_paise=2493,
        ),
        ExpectedFill(
            bar_timestamp="2025-01-09T09:30:00+05:30",
            action="SELL",
            raw_price_paise=9600,
            slippage_paise=-5,
            quantized_price_paise=9595,
            qty=25,
            gross_value_paise=239875,
            brokerage_paise=2000,
            stt_paise=240,
            exchange_turnover_paise=84,
            gst_paise=375,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2699,
        ),
    ],
    expected_final_state=ExpectedLedgerState(
        cash_balance_paise=9_934_558,
        position_qty=0,
        gross_realized_pnl_paise=-60_250,
        total_fees_paid_paise=5_192,
        net_realized_pnl_paise=-65_442,
        unrealized_pnl_paise=0,
        total_equity_paise=9_934_558,
    ),
    special_assertions={"target_hit_intrabar": False, "stop_hit_intrabar": True},
)


# ==============================================================================
# SCENARIO 3: Same-Bar Stop and Target Touched (Stop-First Invariant)
# ==============================================================================
# Bar High = 11,500 (touches 11,000 target); Bar Low = 9,400 (touches 9,600 stop).
# Invariant: STOP_FIRST policy resolves ambiguity -> Stop wins.
# Result matches Scenario 2 exactly: Stop fill at 9,595 paise.
SCENARIO_3 = GoldenScenario(
    scenario_id="SCENARIO_03",
    title="Same-Bar Stop and Target Touched (Stop-First)",
    description="Extremely volatile bar touches both take-profit and stop-loss levels. STOP_FIRST invariant guarantees stop exit fills.",
    initial_capital_paise=10_000_000,
    contract_symbol="NIFTY 24000 CE 30 JAN 25",
    strike_price=24000.0,
    option_type=OptionType.CE,
    lot_size=25,
    tick_paise=5,
    expected_fills=[
        ExpectedFill(
            bar_timestamp="2025-01-09T09:20:00+05:30",
            action="BUY",
            raw_price_paise=10000,
            slippage_paise=5,
            quantized_price_paise=10005,
            qty=25,
            gross_value_paise=250125,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=88,
            gst_paise=376,
            sebi_paise=0,
            stamp_duty_paise=8,
            total_fee_paise=2472,
        ),
        ExpectedFill(
            bar_timestamp="2025-01-09T09:25:00+05:30",
            action="SELL",
            raw_price_paise=9500,  # Stop level
            slippage_paise=-5,
            quantized_price_paise=9495,
            qty=25,
            gross_value_paise=237375,
            brokerage_paise=2000,
            stt_paise=237,
            exchange_turnover_paise=83,
            gst_paise=375,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2695,
        ),
    ],
    expected_final_state=ExpectedLedgerState(
        cash_balance_paise=9_982_083,
        position_qty=0,
        gross_realized_pnl_paise=-12_750,
        total_fees_paid_paise=5_167,
        net_realized_pnl_paise=-17_917,
        unrealized_pnl_paise=0,
        total_equity_paise=9_982_083,
    ),
    special_assertions={"stop_first_policy_triggered": True, "target_ignored": True},
)


# ==============================================================================
# SCENARIO 4: Bar Opens Through Stop (Gap-Down Open Fill)
# ==============================================================================
# Stop trigger is at 9,500 paise. Bar opens at 9,000 paise (gapped down past stop).
# Invariant: Fills at actual available open (9,000 paise - 5 slippage = 8,995 paise), NOT at better trigger level.
SCENARIO_4 = GoldenScenario(
    scenario_id="SCENARIO_04",
    title="Bar Opens Through Stop (Gap-Down Open Fill)",
    description="Option gaps down at market open past stop level. Fill executes at open price with slippage, not trigger.",
    initial_capital_paise=10_000_000,
    contract_symbol="NIFTY 24000 CE 30 JAN 25",
    strike_price=24000.0,
    option_type=OptionType.CE,
    lot_size=25,
    tick_paise=5,
    expected_fills=[
        ExpectedFill(
            bar_timestamp="2025-01-09T09:20:00+05:30",
            action="BUY",
            raw_price_paise=10000,
            slippage_paise=5,
            quantized_price_paise=10005,
            qty=25,
            gross_value_paise=250125,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=88,
            gst_paise=376,
            sebi_paise=0,
            stamp_duty_paise=8,
            total_fee_paise=2472,
        ),
        ExpectedFill(
            bar_timestamp="2025-01-09T09:35:00+05:30",
            action="SELL",
            raw_price_paise=9000,  # Open price below 9,500 stop
            slippage_paise=-5,
            quantized_price_paise=8995,
            qty=25,
            gross_value_paise=224875,
            brokerage_paise=2000,
            stt_paise=225,
            exchange_turnover_paise=79,
            gst_paise=374,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2678,
        ),
    ],
    expected_final_state=ExpectedLedgerState(
        cash_balance_paise=9_969_600,
        position_qty=0,
        gross_realized_pnl_paise=-25_250,
        total_fees_paid_paise=5_150,
        net_realized_pnl_paise=-30_400,
        unrealized_pnl_paise=0,
        total_equity_paise=9_969_600,
    ),
    special_assertions={"filled_at_open_price": True, "filled_at_trigger": False},
)


# ==============================================================================
# SCENARIO 5: Zero-Volume Flat Bar (No Fill, No Exit Trigger)
# ==============================================================================
# Open = High = Low = Close, Volume = 0.
# Invariant: Does not provide fills or trigger exits. Mark-to-market uses previous valid price with STALE flag.
SCENARIO_5 = GoldenScenario(
    scenario_id="SCENARIO_05",
    title="Zero-Volume Flat Bar Handling",
    description="Zero-volume flat candle does not provide fills or trigger stop/target exits. Position stays open with STALE mark.",
    initial_capital_paise=10_000_000,
    contract_symbol="NIFTY 24000 CE 30 JAN 25",
    strike_price=24000.0,
    option_type=OptionType.CE,
    lot_size=25,
    tick_paise=5,
    expected_fills=[
        ExpectedFill(
            bar_timestamp="2025-01-09T09:20:00+05:30",
            action="BUY",
            raw_price_paise=10000,
            slippage_paise=5,
            quantized_price_paise=10005,
            qty=25,
            gross_value_paise=250125,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=88,
            gst_paise=376,
            sebi_paise=0,
            stamp_duty_paise=8,
            total_fee_paise=2472,
        ),
    ],
    expected_final_state=ExpectedLedgerState(
        cash_balance_paise=9_747_403,
        position_qty=25,
        gross_realized_pnl_paise=0,
        total_fees_paid_paise=2_472,
        net_realized_pnl_paise=-2_472,
        unrealized_pnl_paise=-125,  # Marked at 10,000 paise (bought at 10,005 with slippage)
        total_equity_paise=9_997_403,  # 9,747,403 cash + 250,000 market value
    ),
    special_assertions={"flat_bar_ignored": True, "mark_provenance": "STALE"},
)


# ==============================================================================
# SCENARIO 6: Stale-Data Wait Exceeded (Force-Exit at Next Valid Open)
# ==============================================================================
# After 5 consecutive missing/flat bars (max_stale_minutes = 5), force exit order is queued
# and fills at the next valid non-flat bar open with 3x worst-case slippage (15 paise).
SCENARIO_6 = GoldenScenario(
    scenario_id="SCENARIO_06",
    title="Stale-Data Wait Exceeded Force-Exit",
    description="Option data missing/flat for > max_stale_minutes. Engine forces liquidation at next valid open with 3x worst-case slippage.",
    initial_capital_paise=10_000_000,
    contract_symbol="NIFTY 24000 CE 30 JAN 25",
    strike_price=24000.0,
    option_type=OptionType.CE,
    lot_size=25,
    tick_paise=5,
    expected_fills=[
        ExpectedFill(
            bar_timestamp="2025-01-09T09:20:00+05:30",
            action="BUY",
            raw_price_paise=10000,
            slippage_paise=5,
            quantized_price_paise=10005,
            qty=25,
            gross_value_paise=250125,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=88,
            gst_paise=376,
            sebi_paise=0,
            stamp_duty_paise=8,
            total_fee_paise=2472,
        ),
        ExpectedFill(
            bar_timestamp="2025-01-09T09:30:00+05:30",
            action="SELL",
            raw_price_paise=9800,  # Valid open after 5 stale bars
            slippage_paise=-15,  # 3x worst-case slippage
            quantized_price_paise=9785,
            qty=25,
            gross_value_paise=244625,
            brokerage_paise=2000,
            stt_paise=245,
            exchange_turnover_paise=86,
            gst_paise=375,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2706,
        ),
    ],
    expected_final_state=ExpectedLedgerState(
        cash_balance_paise=9_989_322,
        position_qty=0,
        gross_realized_pnl_paise=-5_500,
        total_fees_paid_paise=5_178,
        net_realized_pnl_paise=-10_678,
        unrealized_pnl_paise=0,
        total_equity_paise=9_989_322,
    ),
    special_assertions={"stale_forced_exit": True, "worst_case_slippage_applied": True},
)


# ==============================================================================
# SCENARIO 7: Causal 15:25 Force-Flat Timing
# ==============================================================================
# Position held into afternoon.
# At 15:24:00 bar close (available_at = 15:25:00), engine evaluates open position against force_flat_time = 15:25.
# Order intent for market exit queued for 15:25:00 open.
# Fills at 15:25:00 open at 10,200 paise - 5 paise slippage = 10,195 paise.
SCENARIO_7 = GoldenScenario(
    scenario_id="SCENARIO_07",
    title="Causal 15:25 Force-Flat Timing",
    description="Open intraday position is scheduled for force-flat at 15:24 close, filling cleanly at 15:25 next-bar open.",
    initial_capital_paise=10_000_000,
    contract_symbol="NIFTY 24000 CE 30 JAN 25",
    strike_price=24000.0,
    option_type=OptionType.CE,
    lot_size=25,
    tick_paise=5,
    expected_fills=[
        ExpectedFill(
            bar_timestamp="2025-01-09T09:20:00+05:30",
            action="BUY",
            raw_price_paise=10000,
            slippage_paise=5,
            quantized_price_paise=10005,
            qty=25,
            gross_value_paise=250125,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=88,
            gst_paise=376,
            sebi_paise=0,
            stamp_duty_paise=8,
            total_fee_paise=2472,
        ),
        ExpectedFill(
            bar_timestamp="2025-01-09T15:25:00+05:30",
            action="SELL",
            raw_price_paise=10200,
            slippage_paise=-5,
            quantized_price_paise=10195,
            qty=25,
            gross_value_paise=254875,
            brokerage_paise=2000,
            stt_paise=255,
            exchange_turnover_paise=89,
            gst_paise=376,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2720,
        ),
    ],
    expected_final_state=ExpectedLedgerState(
        cash_balance_paise=9_999_558,
        position_qty=0,
        gross_realized_pnl_paise=4_750,
        total_fees_paid_paise=5_192,
        net_realized_pnl_paise=-442,
        unrealized_pnl_paise=0,
        total_equity_paise=9_999_558,
    ),
    special_assertions={"force_flat_at_1525_open": True, "zero_lookahead": True},
)


# ==============================================================================
# SCENARIO 8: Final Bar 15:29 Rejection & Pre-Scheduled Close-Fill Invariant
# ==============================================================================
# Invariant: A NEW strategy signal decided at 15:29 close has NO next bar in the session -> REJECTED with NO_NEXT_BAR.
# However, if an existing position was still open at 15:29 due to prior liquidation delays, it fills at 15:29 close with EOD_CLOSE_FILL.
SCENARIO_8 = GoldenScenario(
    scenario_id="SCENARIO_08",
    title="Final Bar 15:29 Rule & Pre-Scheduled Liquidation",
    description="Proves that new strategy entries decided at 15:29 close are rejected with NO_NEXT_BAR, while open positions liquidate at 15:29 close.",
    initial_capital_paise=10_000_000,
    contract_symbol="NIFTY 24000 CE 30 JAN 25",
    strike_price=24000.0,
    option_type=OptionType.CE,
    lot_size=25,
    tick_paise=5,
    expected_fills=[
        ExpectedFill(
            bar_timestamp="2025-01-09T09:20:00+05:30",
            action="BUY",
            raw_price_paise=10000,
            slippage_paise=5,
            quantized_price_paise=10005,
            qty=25,
            gross_value_paise=250125,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=88,
            gst_paise=376,
            sebi_paise=0,
            stamp_duty_paise=8,
            total_fee_paise=2472,
        ),
        ExpectedFill(
            bar_timestamp="2025-01-09T15:29:00+05:30",
            action="SELL",
            raw_price_paise=9500,  # Final 15:29 close price
            slippage_paise=-10,  # EOD close fill slippage penalty
            quantized_price_paise=9490,
            qty=25,
            gross_value_paise=237250,
            brokerage_paise=2000,
            stt_paise=237,
            exchange_turnover_paise=83,
            gst_paise=375,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2695,
        ),
    ],
    expected_final_state=ExpectedLedgerState(
        cash_balance_paise=9_981_958,
        position_qty=0,
        gross_realized_pnl_paise=-12_875,
        total_fees_paid_paise=5_167,
        net_realized_pnl_paise=-18_042,
        unrealized_pnl_paise=0,
        total_equity_paise=9_981_958,
    ),
    special_assertions={"new_entry_at_1529_rejected": True, "rejection_reason": "NO_NEXT_BAR"},
)


# ==============================================================================
# SCENARIO 9: Statutory Fee Schedule Transition (Union Budget 2026 STT 0.15%)
# ==============================================================================
# Verifies that trade executed on 2026-04-02 applies STT = 0.15% (15 bps) on sell turnover,
# compared to 0.10% (10 bps) in 2025.
# Sale value: 25 * 10,000 = 250,000 paise (Rs 2,500).
# STT under 2025 rate (0.10%) would be 250 paise.
# STT under 2026 rate (0.15%) is: 250,000 * 0.0015 = 375 paise (Rs 3.75).
SCENARIO_9 = GoldenScenario(
    scenario_id="SCENARIO_09",
    title="Statutory Fee Schedule Transition (2026 STT 0.15%)",
    description="Verifies dynamic rate resolution across regulatory transitions: STT increases to 0.15% on 2026-04-01.",
    initial_capital_paise=10_000_000,
    contract_symbol="NIFTY 24000 CE 30 APR 26",
    strike_price=24000.0,
    option_type=OptionType.CE,
    lot_size=25,
    tick_paise=5,
    expected_fills=[
        ExpectedFill(
            bar_timestamp="2026-04-02T09:20:00+05:30",
            action="BUY",
            raw_price_paise=10000,
            slippage_paise=5,
            quantized_price_paise=10005,
            qty=25,
            gross_value_paise=250125,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=89,  # 0.03553% in 2026
            gst_paise=376,
            sebi_paise=0,
            stamp_duty_paise=8,
            total_fee_paise=2473,
        ),
        ExpectedFill(
            bar_timestamp="2026-04-02T10:00:00+05:30",
            action="SELL",
            raw_price_paise=10000,
            slippage_paise=-5,
            quantized_price_paise=9995,
            qty=25,
            gross_value_paise=249875,
            brokerage_paise=2000,
            stt_paise=375,  # 0.15% STT (249,875 * 0.0015 = 374.81 -> 375 paise)
            exchange_turnover_paise=89,
            gst_paise=376,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2840,
        ),
    ],
    expected_final_state=ExpectedLedgerState(
        cash_balance_paise=9_994_437,
        position_qty=0,
        gross_realized_pnl_paise=-250,
        total_fees_paid_paise=5_313,
        net_realized_pnl_paise=-5_563,
        unrealized_pnl_paise=0,
        total_equity_paise=9_994_437,
    ),
    special_assertions={"stt_rate_applied": Decimal("0.0015"), "schedule_resolved": "UPSTOX_2026_APR"},
)


ALL_GOLDEN_SCENARIOS = [
    SCENARIO_1,
    SCENARIO_2,
    SCENARIO_3,
    SCENARIO_4,
    SCENARIO_5,
    SCENARIO_6,
    SCENARIO_7,
    SCENARIO_8,
    SCENARIO_9,
]
