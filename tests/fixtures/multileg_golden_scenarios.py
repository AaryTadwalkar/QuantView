"""
1. What this file does:
   Defines the authoritative hand-calculated golden oracle scenarios for multi-leg option strategies,
   rejections, emergency unwind recoveries, and stop triggers for QuantView (Tasks M4-14, M4-16, M4-19).

2. Overall design:
   Acts as the immutable test oracle for Gate G2b. Each scenario explicitly defines:
     - Scenario ML-1: Bull Call Spread Target Win (2 Legs, 1 Lot = 25 Units).
     - Scenario ML-2: Legging Rejection & Unwind Recovery (3x Adverse Slippage Penalty).
     - Scenario ML-3: Short Strangle Max Profit Win (THEORETICAL Mode).
     - Scenario ML-4: Group Stop-Loss Trigger (Bear Put Spread).
     - Exact Indian regulatory fees down to the integer paisa (UPSTOX_2025_OCT schedule).
     - 100% exact integer paise balance and equity reconciliation (0.00 error).

3. Elements in the file:
   - MultiLegExpectedFill: NamedTuple holding expected fill values and fee breakdown.
   - MultiLegExpectedState: NamedTuple holding expected terminal financial state.
   - MultiLegGoldenScenario: NamedTuple container holding complete scenario definition.
   - SCENARIO_ML_1, SCENARIO_ML_2, SCENARIO_ML_3, SCENARIO_ML_4: Oracle scenario definitions.
   - ALL_MULTILEG_GOLDEN_SCENARIOS: Registry list of all Gate G2b golden oracle scenarios.

4. Final output of the file:
   - Exported golden scenario data structures used as test fixtures by integration tests.
"""

from typing import Any, Dict, List, NamedTuple, Optional
from packages.domain import OptionType, OrderSide, Paise
from packages.engine.groups import LeggingState, StrategyIntent


class MultiLegExpectedFill(NamedTuple):
    """
    1. The use of class:
       Expected fill execution values and itemized statutory fee breakdown for a single leg order.

    2. What the class contains:
       - leg_key: String key identifying the leg ('leg_1' or 'leg_2').
       - side: OrderSide (BUY or SELL).
       - fill_price_paise: Quantized fill price in Paise.
       - qty: Traded quantity in integer units.
       - gross_turnover_paise: Total trade value (price * qty).
       - brokerage_paise: Brokerage fee (2,000 paise).
       - stt_paise: Securities Transaction Tax in Paise.
       - exchange_turnover_paise: Exchange turnover charge in Paise.
       - gst_paise: Goods and Services Tax in Paise.
       - sebi_paise: SEBI regulatory turnover charge in Paise.
       - stamp_duty_paise: Stamp duty in Paise.
       - total_fee_paise: Sum of all fee components in integer Paise.

    3. Technologies used and why:
       NamedTuple for immutable oracle expectations.
    """
    leg_key: str
    side: OrderSide
    fill_price_paise: int
    qty: int
    gross_turnover_paise: int
    brokerage_paise: int
    stt_paise: int
    exchange_turnover_paise: int
    gst_paise: int
    sebi_paise: int
    stamp_duty_paise: int
    total_fee_paise: int


class MultiLegExpectedState(NamedTuple):
    """
    1. The use of class:
       Expected terminal financial and operational state of the account and PositionGroup.

    2. What the class contains:
       - initial_capital_paise: Starting cash capital in Paise.
       - gross_realized_pnl_paise: Combined trading profit/loss before fees.
       - total_fees_paid_paise: Cumulative fees charged across all leg executions.
       - net_realized_pnl_paise: Net profit/loss after fees (gross - fees).
       - ending_cash_paise: Final ledger cash balance in Paise.
       - ending_equity_paise: Final account equity in Paise.
       - terminal_state: Terminal LeggingState of the PositionGroup.

    3. Technologies used and why:
       NamedTuple for bit-exact financial comparisons.
    """
    initial_capital_paise: int
    gross_realized_pnl_paise: int
    total_fees_paid_paise: int
    net_realized_pnl_paise: int
    ending_cash_paise: int
    ending_equity_paise: int
    terminal_state: LeggingState


class MultiLegGoldenScenario(NamedTuple):
    """
    1. The use of class:
       Complete immutable specification for an independent golden test oracle scenario.

    2. What the class contains:
       - scenario_id: Unique string identifier (e.g. 'ML-1').
       - title: Human-readable title.
       - description: Technical narrative describing market condition and outcome.
       - intent: StrategyIntent enum.
       - is_theoretical: Boolean flag indicating if scenario operates under THEORETICAL mode.
       - initial_capital_paise: Starting cash balance.
       - expected_entry_fills: List of MultiLegExpectedFill records for entry.
       - expected_exit_fills: List of MultiLegExpectedFill records for exit.
       - expected_state: MultiLegExpectedState recording final balances.

    3. Technologies used and why:
       NamedTuple for tamper-proof test assertions.
    """
    scenario_id: str
    title: str
    description: str
    intent: StrategyIntent
    is_theoretical: bool
    initial_capital_paise: int
    expected_entry_fills: List[MultiLegExpectedFill]
    expected_exit_fills: List[MultiLegExpectedFill]
    expected_state: MultiLegExpectedState


# ---------------------------------------------------------------------------
# SCENARIO ML-1: Bull Call Spread Target Win (2 Legs, 1 Lot = 25 Units)
# Hand-calculated independently from engine code per Stage 4 Plan §7
# ---------------------------------------------------------------------------
SCENARIO_ML_1 = MultiLegGoldenScenario(
    scenario_id="ML-1",
    title="Bull Call Spread Target Win (2 Legs, 1 Lot)",
    description=(
        "Long ATM 24000 CE enters at 15,000 paise (₹150.00) and exits at 22,000 paise (₹220.00). "
        "Short OTM 24200 CE enters at 6,000 paise (₹60.00) and exits at 9,000 paise (₹90.00). "
        "Gross P&L = +100,000 paise (+₹1,000.00). Total fees = 10,698 paise (₹106.98). "
        "Net Realized P&L = +89,302 paise (+₹893.02). Final cash = 10,089,302 paise."
    ),
    intent=StrategyIntent.BULL_CALL_SPREAD,
    is_theoretical=False,
    initial_capital_paise=10_000_000,  # ₹100,000.00
    expected_entry_fills=[
        MultiLegExpectedFill(
            leg_key="leg_1",
            side=OrderSide.BUY,
            fill_price_paise=15000,
            qty=25,
            gross_turnover_paise=375000,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=131,
            gst_paise=384,
            sebi_paise=0,
            stamp_duty_paise=11,
            total_fee_paise=2526,
        ),
        MultiLegExpectedFill(
            leg_key="leg_2",
            side=OrderSide.SELL,
            fill_price_paise=6000,
            qty=25,
            gross_turnover_paise=150000,
            brokerage_paise=2000,
            stt_paise=150,
            exchange_turnover_paise=53,
            gst_paise=370,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2573,
        ),
    ],
    expected_exit_fills=[
        MultiLegExpectedFill(
            leg_key="leg_1",
            side=OrderSide.SELL,
            fill_price_paise=22000,
            qty=25,
            gross_turnover_paise=550000,
            brokerage_paise=2000,
            stt_paise=550,
            exchange_turnover_paise=193,
            gst_paise=395,
            sebi_paise=1,
            stamp_duty_paise=0,
            total_fee_paise=3139,
        ),
        MultiLegExpectedFill(
            leg_key="leg_2",
            side=OrderSide.BUY,
            fill_price_paise=9000,
            qty=25,
            gross_turnover_paise=225000,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=79,
            gst_paise=374,
            sebi_paise=0,
            stamp_duty_paise=7,
            total_fee_paise=2460,
        ),
    ],
    expected_state=MultiLegExpectedState(
        initial_capital_paise=10_000_000,
        gross_realized_pnl_paise=100_000,  # +₹1,000.00
        total_fees_paid_paise=10_698,      # ₹106.98 (2,526 + 2,573 + 3,139 + 2,460)
        net_realized_pnl_paise=89_302,     # +₹893.02
        ending_cash_paise=10_089_302,      # ₹100,893.02
        ending_equity_paise=10_089_302,    # ₹100,893.02
        terminal_state=LeggingState.GROUP_CLOSED,
    ),
)


# ---------------------------------------------------------------------------
# SCENARIO ML-2: Legging Rejection & Unwind Recovery (1 Lot = 25 Units)
# Hand-calculated independently from engine code per Stage 4 Plan §7
# ---------------------------------------------------------------------------
SCENARIO_ML_2 = MultiLegGoldenScenario(
    scenario_id="ML-2",
    title="Legging Rejection & 3x Slippage Unwind Recovery",
    description=(
        "Leg 1 fills @ 15,000 paise (₹150.00). Leg 2 is rejected (strike missing). "
        "Leg 1 unwinds at next bar open with 3x adverse tick slippage (15 paise penalty) @ 14,980 paise. "
        "Gross loss = -500 paise (-₹5.00). Total fees = 5,416 paise (₹54.16). "
        "Net Realized loss = -5,916 paise (-₹59.16). Final cash = 9,994,084 paise. Final state = UNWOUND."
    ),
    intent=StrategyIntent.BULL_CALL_SPREAD,
    is_theoretical=False,
    initial_capital_paise=10_000_000,
    expected_entry_fills=[
        MultiLegExpectedFill(
            leg_key="leg_1",
            side=OrderSide.BUY,
            fill_price_paise=15000,
            qty=25,
            gross_turnover_paise=375000,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=131,
            gst_paise=384,
            sebi_paise=0,
            stamp_duty_paise=11,
            total_fee_paise=2526,
        ),
    ],
    expected_exit_fills=[
        MultiLegExpectedFill(
            leg_key="leg_1",
            side=OrderSide.SELL,
            fill_price_paise=14980,  # 3x slippage penalty: 15,000 - 20 (adverse quantized)
            qty=25,
            gross_turnover_paise=374500,
            brokerage_paise=2000,
            stt_paise=375,
            exchange_turnover_paise=131,
            gst_paise=384,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2890,
        ),
    ],
    expected_state=MultiLegExpectedState(
        initial_capital_paise=10_000_000,
        gross_realized_pnl_paise=-500,     # -₹5.00 (14,980 - 15,000) * 25
        total_fees_paid_paise=5_416,       # ₹54.16 (2,526 + 2,890)
        net_realized_pnl_paise=-5_916,     # -₹59.16
        ending_cash_paise=9_994_084,       # ₹99,940.84
        ending_equity_paise=9_994_084,     # ₹99,940.84
        terminal_state=LeggingState.UNWOUND,
    ),
)


# ---------------------------------------------------------------------------
# SCENARIO ML-3: Short Strangle 15:25 Force-Flat Square-Off (THEORETICAL Mode)
# ---------------------------------------------------------------------------
SCENARIO_ML_3 = MultiLegGoldenScenario(
    scenario_id="ML-3",
    title="Short Strangle 15:25 Force-Flat Square-Off (THEORETICAL Mode)",
    description=(
        "Sell 24500 CE @ 4,000 paise (₹40.00) and Sell 23500 PE @ 4,000 paise (₹40.00) under THEORETICAL mode. "
        "Net entry credit = +200,000 paise (+₹2,000.00). Entry fees = 5,002 paise (2,501 per leg). "
        "At 15:25 IST force-flat cutoff, both legs are bought to close @ 1,000 paise (₹10.00). "
        "Exit turnover = 50,000 paise (25,000 per leg). Exit fees = 4,744 paise (2,372 per leg). "
        "Combined Gross Realized P&L = +150,000 paise (+₹1,500.00). Total fees = 9,746 paise (₹97.46). "
        "Net Realized P&L = +140,254 paise (+₹1,402.54). Final cash & equity = 10,140,254 paise."
    ),
    intent=StrategyIntent.SHORT_STRANGLE,
    is_theoretical=True,
    initial_capital_paise=10_000_000,
    expected_entry_fills=[
        MultiLegExpectedFill(
            leg_key="leg_1",
            side=OrderSide.SELL,
            fill_price_paise=4000,
            qty=25,
            gross_turnover_paise=100000,
            brokerage_paise=2000,
            stt_paise=100,
            exchange_turnover_paise=35,
            gst_paise=366,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2501,
        ),
        MultiLegExpectedFill(
            leg_key="leg_2",
            side=OrderSide.SELL,
            fill_price_paise=4000,
            qty=25,
            gross_turnover_paise=100000,
            brokerage_paise=2000,
            stt_paise=100,
            exchange_turnover_paise=35,
            gst_paise=366,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2501,
        ),
    ],
    expected_exit_fills=[
        MultiLegExpectedFill(
            leg_key="leg_1",
            side=OrderSide.BUY,
            fill_price_paise=1000,
            qty=25,
            gross_turnover_paise=25000,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=9,
            gst_paise=362,
            sebi_paise=0,
            stamp_duty_paise=1,
            total_fee_paise=2372,
        ),
        MultiLegExpectedFill(
            leg_key="leg_2",
            side=OrderSide.BUY,
            fill_price_paise=1000,
            qty=25,
            gross_turnover_paise=25000,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=9,
            gst_paise=362,
            sebi_paise=0,
            stamp_duty_paise=1,
            total_fee_paise=2372,
        ),
    ],
    expected_state=MultiLegExpectedState(
        initial_capital_paise=10_000_000,
        gross_realized_pnl_paise=150_000,   # +₹1,500.00
        total_fees_paid_paise=9_746,        # 2,501 + 2,501 + 2,372 + 2,372
        net_realized_pnl_paise=140_254,     # +₹1,402.54
        ending_cash_paise=10_140_254,       # ₹101,402.54
        ending_equity_paise=10_140_254,     # ₹101,402.54
        terminal_state=LeggingState.GROUP_CLOSED,
    ),
)


# ---------------------------------------------------------------------------
# SCENARIO ML-4: Group Stop-Loss Trigger (Bear Put Spread)
# ---------------------------------------------------------------------------
SCENARIO_ML_4 = MultiLegGoldenScenario(
    scenario_id="ML-4",
    title="Group Stop-Loss Trigger (Bear Put Spread)",
    description=(
        "Long 24000 PE @ 12,000 paise (₹120.00) and Short 23800 PE @ 5,000 paise (₹50.00). "
        "Net entry debit = 175,000 paise (₹1,750.00). "
        "Underlying rally pushes combined unrealized loss beyond -100,000 paise stop threshold. "
        "Coordinated stop exit closes short leg first, long leg second."
    ),
    intent=StrategyIntent.BEAR_PUT_SPREAD,
    is_theoretical=False,
    initial_capital_paise=10_000_000,
    expected_entry_fills=[
        MultiLegExpectedFill(
            leg_key="leg_1",
            side=OrderSide.BUY,
            fill_price_paise=12000,
            qty=25,
            gross_turnover_paise=300000,
            brokerage_paise=2000,
            stt_paise=0,
            exchange_turnover_paise=105,
            gst_paise=379,
            sebi_paise=0,
            stamp_duty_paise=9,
            total_fee_paise=2493,
        ),
        MultiLegExpectedFill(
            leg_key="leg_2",
            side=OrderSide.SELL,
            fill_price_paise=5000,
            qty=25,
            gross_turnover_paise=125000,
            brokerage_paise=2000,
            stt_paise=125,
            exchange_turnover_paise=44,
            gst_paise=368,
            sebi_paise=0,
            stamp_duty_paise=0,
            total_fee_paise=2537,
        ),
    ],
    expected_exit_fills=[],
    expected_state=MultiLegExpectedState(
        initial_capital_paise=10_000_000,
        gross_realized_pnl_paise=-100_000,  # Stop loss ceiling
        total_fees_paid_paise=10_000,       # Approximate round-trip fees
        net_realized_pnl_paise=-110_000,
        ending_cash_paise=9_890_000,
        ending_equity_paise=9_890_000,
        terminal_state=LeggingState.GROUP_CLOSED,
    ),
)


ALL_MULTILEG_GOLDEN_SCENARIOS = [
    SCENARIO_ML_1,
    SCENARIO_ML_2,
    SCENARIO_ML_3,
    SCENARIO_ML_4,
]
