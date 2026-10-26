"""
1. What this file does:
   Implements the versioned, effective-dated regulatory and broker fee schedule engine for QuantView (Task M4-06).
   Calculates itemized statutory exchange charges, STT, GST, SEBI turnover fees, stamp duty, and brokerage
   down to the exact integer paisa without floating-point drift.

2. Overall design:
   Rejects static rate constants in favor of date-aware schedules matching Indian regulatory changes:
     - UPSTOX_2025_OCT: 2024-10-01 through 2026-02-28 (STT 0.10% sell, NSE Turnover 0.03503%).
     - UPSTOX_2026_MAR: 2026-03-01 through 2026-03-31 (STT 0.10% sell, NSE Turnover 0.03553% per NSE Circular FA73061).
     - UPSTOX_2026_APR: 2026-04-01 onwards (STT 0.15% sell per Union Budget 2026, NSE Turnover 0.03553%).
   Uses Python Decimal with ROUND_HALF_UP on itemized bases to quantize exact paise, then returns an immutable
   FeeBreakdown tuple whose total equals the sum of its integer components.

3. Elements in the file:
   - FeeBreakdown: NamedTuple holding itemized integer-paise charges.
   - FeeSchedule: Class encapsulating rates for a specific regulatory validity window.
   - FeeScheduleEngine: Registry resolving effective schedules by trade date and computing order charges.
   - UPSTOX_2025_OCT, UPSTOX_2026_MAR, UPSTOX_2026_APR: Authoritative statutory schedule definitions.
   - get_default_fee_engine(): Factory returning configured singleton fee engine.

4. Final output of the file:
   - Exported FeeBreakdown, FeeSchedule, FeeScheduleEngine, and default Indian fee schedules.
"""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple, Optional, List, Union
from packages.domain import Paise, OrderSide


def _round_half_up_paise(val_decimal: Decimal) -> Paise:
    """
    1. The use of function:
       Rounds a Decimal value representing paise to the nearest integer paisa using ROUND_HALF_UP.

    2. How does the specific function work:
       Applies Decimal.quantize with Decimal('1') and ROUND_HALF_UP, then wraps in integer Paise.

    3. Concepts used in the function:
       Indian statutory rounding rules, exact decimal quantization.

    4. Places where this function is imported and used:
       Internal helper used across fee component calculations in FeeSchedule.

    5. Final output of the function, before and after:
       Before: Arbitrary precision Decimal paise. After: Exact integer Paise.
    """
    return Paise(int(val_decimal.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


class FeeBreakdown(NamedTuple):
    """
    1. The use of class:
       Immutable container for itemized statutory fees and broker charges for an executed order.

    2. What the class contains:
       - schedule_name: Regulatory schedule identifier.
       - side: OrderSide (BUY or SELL).
       - gross_value_paise: Gross premium traded in integer paise.
       - brokerage_paise: Flat brokerage charge.
       - stt_paise: Securities Transaction Tax (STT).
       - exchange_turnover_paise: NSE transaction charge.
       - gst_paise: Goods and Services Tax (18% on brokerage + exchange charge).
       - sebi_paise: SEBI regulatory turnover fee (Rs 10/crore).
       - stamp_duty_paise: State stamp duty (buy turnover only).
       - total_fee_paise: Sum of all itemized charges.

    3. Technologies used and why:
       NamedTuple for immutability, compact memory layout, and deterministic hashing.

    4. Key design and overall design of the class:
       Guarantees that total_fee_paise strictly equals the arithmetic sum of its constituent paise.
    """
    schedule_name: str
    side: OrderSide
    gross_value_paise: Paise
    brokerage_paise: Paise
    stt_paise: Paise
    exchange_turnover_paise: Paise
    gst_paise: Paise
    sebi_paise: Paise
    stamp_duty_paise: Paise
    total_fee_paise: Paise


class FeeSchedule:
    """
    1. The use of class:
       Represents an Indian derivatives broker and regulatory fee schedule effective over a date range.

    2. What the class contains:
       - name: Identifier of the schedule.
       - effective_from: Start date (inclusive).
       - effective_to: Optional end date (inclusive); None indicates currently active.
       - brokerage_per_order_paise: Flat brokerage fee per order.
       - stt_rate_sell: STT rate on option sell premium.
       - stt_rate_buy: STT rate on option buy premium (statutorily 0).
       - exchange_turnover_rate: NSE option turnover charge rate.
       - gst_rate: GST rate on brokerage and exchange charges (statutorily 18%).
       - sebi_turnover_rate: SEBI turnover fee rate (Rs 10 per crore).
       - stamp_duty_rate_buy: Stamp duty rate on buy premium (statutorily 0.003%).
       - stamp_duty_rate_sell: Stamp duty rate on sell premium (statutorily 0).
       - calculate_fees(): Core calculation logic for a single fill.

    3. Technologies used and why:
       Python Decimal for exact financial rate specification and rounding.

    4. Key design and overall design of the class:
       Encapsulates statutory rules and ensures zero float conversion in all fee paths.
    """

    def __init__(
        self,
        name: str,
        effective_from: date,
        effective_to: Optional[date],
        brokerage_per_order_paise: Paise = Paise(2000),
        stt_rate_sell: Decimal = Decimal("0.0010"),
        stt_rate_buy: Decimal = Decimal("0"),
        exchange_turnover_rate: Decimal = Decimal("0.0003503"),
        gst_rate: Decimal = Decimal("0.18"),
        sebi_turnover_rate: Decimal = Decimal("0.000001"),
        stamp_duty_rate_buy: Decimal = Decimal("0.00003"),
        stamp_duty_rate_sell: Decimal = Decimal("0"),
    ) -> None:
        """
        1. The use of function:
           Initializes a FeeSchedule instance with specific regulatory parameters.

        2. How does the specific function work:
           Stores effective date bounds and Decimal rate schedules.

        3. Concepts used in the function:
           Effective-dating and statutory parameter encapsulation.

        4. Places where this function is imported and used:
           Used when constructing regulatory schedules (UPSTOX_2025_OCT, etc.).

        5. Final output of the function, before and after:
           Before: Raw rates. After: Initialized FeeSchedule instance.
        """
        self.name = name
        self.effective_from = effective_from
        self.effective_to = effective_to
        self.brokerage_per_order_paise = brokerage_per_order_paise
        self.stt_rate_sell = stt_rate_sell
        self.stt_rate_buy = stt_rate_buy
        self.exchange_turnover_rate = exchange_turnover_rate
        self.gst_rate = gst_rate
        self.sebi_turnover_rate = sebi_turnover_rate
        self.stamp_duty_rate_buy = stamp_duty_rate_buy
        self.stamp_duty_rate_sell = stamp_duty_rate_sell

    def is_effective(self, trade_date: date) -> bool:
        """
        1. The use of function:
           Checks if this fee schedule is legally active on the given trade date.

        2. How does the specific function work:
           Returns True if effective_from <= trade_date <= effective_to (or effective_to is None).

        3. Concepts used in the function:
           Interval containment for versioned temporal data.

        4. Places where this function is imported and used:
           Called by FeeScheduleEngine.resolve_schedule.

        5. Final output of the function, before and after:
           Before: Target trade_date. After: Boolean indicating validity.
        """
        if trade_date < self.effective_from:
            return False
        if self.effective_to is not None and trade_date > self.effective_to:
            return False
        return True

    def calculate_fees(self, side: OrderSide, gross_value_paise: Paise) -> FeeBreakdown:
        """
        1. The use of function:
           Calculates itemized statutory fees for an executed option order of given side and value.

        2. How does the specific function work:
           - Computes turnover in INR: Decimal(gross_value_paise) / 100.
           - Brokerage: Flat 2000 paise (Rs 20.00).
           - STT: Applied to sell only, quantized to paise using ROUND_HALF_UP.
           - Exchange turnover charges: Turnover * exchange_turnover_rate, quantized to paise.
           - GST: 18% on (Brokerage + Exchange turnover), quantized to paise.
           - SEBI turnover fee: Turnover * Rs 10 / 1 Cr, quantized to paise.
           - Stamp duty: Applied to buy only (0.003%), quantized to paise.
           - Total fee: Direct integer summation of all above paise values.

        3. Concepts used in the function:
           NSE Derivatives clearing rules, contract note reconciliation, ROUND_HALF_UP.

        4. Places where this function is imported and used:
           Used by backtest fill engine, risk evaluator, and paper trading accounts.

        5. Final output of the function, before and after:
           Before: OrderSide and gross_value_paise. After: Fully itemized FeeBreakdown.
        """
        if gross_value_paise < 0:
            raise ValueError(f"gross_value_paise must be non-negative, got {gross_value_paise}")

        turnover_inr = Decimal(int(gross_value_paise)) / Decimal("100")
        brokerage = self.brokerage_per_order_paise

        # 1. STT (Securities Transaction Tax)
        stt_rate = self.stt_rate_sell if side == OrderSide.SELL else self.stt_rate_buy
        stt_inr = turnover_inr * stt_rate
        stt_paise = _round_half_up_paise(stt_inr * Decimal("100"))

        # 2. Exchange Turnover Charge
        exch_inr = turnover_inr * self.exchange_turnover_rate
        exch_paise = _round_half_up_paise(exch_inr * Decimal("100"))

        # 3. GST (18% on Brokerage + Exchange Charges)
        gst_base_paise = Decimal(int(brokerage) + int(exch_paise))
        gst_paise = _round_half_up_paise(gst_base_paise * self.gst_rate)

        # 4. SEBI Regulatory Turnover Fee (Rs 10 / Crore)
        sebi_inr = turnover_inr * self.sebi_turnover_rate
        sebi_paise = _round_half_up_paise(sebi_inr * Decimal("100"))

        # 5. Stamp Duty (Buy orders only, 0.003%)
        stamp_rate = self.stamp_duty_rate_buy if side == OrderSide.BUY else self.stamp_duty_rate_sell
        stamp_inr = turnover_inr * stamp_rate
        stamp_duty_paise = _round_half_up_paise(stamp_inr * Decimal("100"))

        total_fee = Paise(
            int(brokerage)
            + int(stt_paise)
            + int(exch_paise)
            + int(gst_paise)
            + int(sebi_paise)
            + int(stamp_duty_paise)
        )

        return FeeBreakdown(
            schedule_name=self.name,
            side=side,
            gross_value_paise=gross_value_paise,
            brokerage_paise=brokerage,
            stt_paise=stt_paise,
            exchange_turnover_paise=exch_paise,
            gst_paise=gst_paise,
            sebi_paise=sebi_paise,
            stamp_duty_paise=stamp_duty_paise,
            total_fee_paise=total_fee,
        )


# Authoritative Historical and Current Statutory Schedules
UPSTOX_2025_OCT = FeeSchedule(
    name="UPSTOX_2025_OCT",
    effective_from=date(2024, 10, 1),
    effective_to=date(2026, 2, 28),
    brokerage_per_order_paise=Paise(2000),
    stt_rate_sell=Decimal("0.0010"),  # 0.10% (10 bps)
    stt_rate_buy=Decimal("0"),
    exchange_turnover_rate=Decimal("0.0003503"),  # 0.03503%
    gst_rate=Decimal("0.18"),
    sebi_turnover_rate=Decimal("0.000001"),  # Rs 10 per crore
    stamp_duty_rate_buy=Decimal("0.00003"),  # 0.003% (3 bps)
    stamp_duty_rate_sell=Decimal("0"),
)

UPSTOX_2026_MAR = FeeSchedule(
    name="UPSTOX_2026_MAR",
    effective_from=date(2026, 3, 1),
    effective_to=date(2026, 3, 31),
    brokerage_per_order_paise=Paise(2000),
    stt_rate_sell=Decimal("0.0010"),  # 0.10%
    stt_rate_buy=Decimal("0"),
    exchange_turnover_rate=Decimal("0.0003553"),  # 0.03553% (NSE Circular FA73061)
    gst_rate=Decimal("0.18"),
    sebi_turnover_rate=Decimal("0.000001"),
    stamp_duty_rate_buy=Decimal("0.00003"),
    stamp_duty_rate_sell=Decimal("0"),
)

UPSTOX_2026_APR = FeeSchedule(
    name="UPSTOX_2026_APR",
    effective_from=date(2026, 4, 1),
    effective_to=None,  # Open-ended active schedule
    brokerage_per_order_paise=Paise(2000),
    stt_rate_sell=Decimal("0.0015"),  # 0.15% (15 bps, Union Budget 2026)
    stt_rate_buy=Decimal("0"),
    exchange_turnover_rate=Decimal("0.0003553"),  # 0.03553%
    gst_rate=Decimal("0.18"),
    sebi_turnover_rate=Decimal("0.000001"),
    stamp_duty_rate_buy=Decimal("0.00003"),
    stamp_duty_rate_sell=Decimal("0"),
)


class FeeScheduleEngine:
    """
    1. The use of class:
       Manages a collection of versioned fee schedules and dynamically resolves the effective
       schedule for any trading date.

    2. What the class contains:
       - schedules: List of registered FeeSchedule objects.
       - register_schedule(): Adds a custom or updated schedule.
       - resolve_schedule(): Finds the active schedule for a given date.
       - calculate_order_fees(): One-step resolution and fee calculation.

    3. Technologies used and why:
       Date parsing and chronological lookup ensuring fail-closed safety.

    4. Key design and overall design of the class:
       Ensures backtests spanning multiple fiscal years or regulatory changes automatically apply
       exact statutory rates without manual schedule switching.
    """

    def __init__(self, schedules: Optional[List[FeeSchedule]] = None) -> None:
        """
        1. The use of function:
           Initializes the fee schedule engine with default or custom schedules.

        2. How does the specific function work:
           Stores schedules, defaulting to the three canonical Upstox schedules if none provided.

        3. Concepts used in the function:
           Default configuration and dependency injection.

        4. Places where this function is imported and used:
           Used by get_default_fee_engine and backtest orchestrator.

        5. Final output of the function, before and after:
           Before: Optional list of schedules. After: Initialized FeeScheduleEngine.
        """
        if schedules is not None:
            self._schedules = list(schedules)
        else:
            self._schedules = [UPSTOX_2025_OCT, UPSTOX_2026_MAR, UPSTOX_2026_APR]

    def register_schedule(self, schedule: FeeSchedule) -> None:
        """
        1. The use of function:
           Registers an additional or updated fee schedule into the engine.

        2. How does the specific function work:
           Appends schedule to internal registry list.

        3. Concepts used in the function:
           Extensible fee catalog.

        4. Places where this function is imported and used:
           Called when defining broker-specific or updated exchange fee schedules.

        5. Final output of the function, before and after:
           Before: Unregistered schedule. After: Schedule registered in lookup list.
        """
        self._schedules.append(schedule)

    def _normalize_date(self, trade_date: Union[date, datetime, str]) -> date:
        """
        1. The use of function:
           Normalizes various date/datetime/string formats into a standard datetime.date object.

        2. How does the specific function work:
           Extracts date component if datetime, parses YYYY-MM-DD if string, passes through date.

        3. Concepts used in the function:
           Defensive input normalization.

        4. Places where this function is imported and used:
           Internal helper for resolve_schedule.

        5. Final output of the function, before and after:
           Before: date, datetime, or str. After: datetime.date.
        """
        if isinstance(trade_date, datetime):
            return trade_date.date()
        if isinstance(trade_date, str):
            # Supports 'YYYY-MM-DD' or ISO timestamp prefixes
            return date.fromisoformat(trade_date.split("T")[0])
        if isinstance(trade_date, date):
            return trade_date
        raise TypeError(f"trade_date must be date, datetime, or str, got {type(trade_date)}")

    def resolve_schedule(self, trade_date: Union[date, datetime, str]) -> FeeSchedule:
        """
        1. The use of function:
           Resolves the effective statutory fee schedule for a given trade date.

        2. How does the specific function work:
           Normalizes trade_date and iterates through registered schedules in order.
           Returns the first matching schedule where schedule.is_effective(d) is True.
           If no schedule matches, raises ValueError (fail-closed).

        3. Concepts used in the function:
           Point-in-time regulatory resolution, fail-closed security.

        4. Places where this function is imported and used:
           Called during fill evaluation and order fee accounting.

        5. Final output of the function, before and after:
           Before: Target trade date. After: Active FeeSchedule instance.
        """
        d = self._normalize_date(trade_date)
        for sched in self._schedules:
            if sched.is_effective(d):
                return sched
        raise ValueError(f"No effective fee schedule found for trade date {d}")

    def calculate_order_fees(
        self,
        trade_date: Union[date, datetime, str],
        side: OrderSide,
        gross_value_paise: Paise,
    ) -> FeeBreakdown:
        """
        1. The use of function:
           Dynamically resolves the fee schedule for trade_date and calculates exact itemized fees.

        2. How does the specific function work:
           Calls resolve_schedule(trade_date) then schedule.calculate_fees(side, gross_value_paise).

        3. Concepts used in the function:
           Single-point-of-entry facade for trade accounting.

        4. Places where this function is imported and used:
           Primary method invoked by execution engine and ledger writer.

        5. Final output of the function, before and after:
           Before: Trade date, side, gross value. After: Exact integer-paise FeeBreakdown.
        """
        schedule = self.resolve_schedule(trade_date)
        return schedule.calculate_fees(side, gross_value_paise)


_GLOBAL_FEE_ENGINE: Optional[FeeScheduleEngine] = None


def get_default_fee_engine() -> FeeScheduleEngine:
    """
    1. The use of function:
       Returns the shared singleton instance of FeeScheduleEngine configured with Indian schedules.

    2. How does the specific function work:
       Constructs FeeScheduleEngine if not already created, then returns it.

    3. Concepts used in the function:
       Singleton accessor pattern.

    4. Places where this function is imported and used:
       Imported by backtest runners, ledger writers, and financial projection services.

    5. Final output of the function, before and after:
       Before: None or cached engine. After: Initialized FeeScheduleEngine singleton.
    """
    global _GLOBAL_FEE_ENGINE
    if _GLOBAL_FEE_ENGINE is None:
        _GLOBAL_FEE_ENGINE = FeeScheduleEngine()
    return _GLOBAL_FEE_ENGINE
