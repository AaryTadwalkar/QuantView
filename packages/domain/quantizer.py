"""
1. What this file does:
   Defines the TickQuantizer and exchange tick rounding algorithms for QuantView.
   Enforces exact integer tick quantization against the trader per canonical Engine Spec §4.

2. Overall design:
   NSE derivative contracts trade in discrete tick increments (typically 5 paise = Rs 0.05).
   When an order fills or slippage is applied, the execution price must be rounded to a valid
   contract tick. The canonical rule requires rounding strictly AGAINST the trader:
     - For BUY orders (long entry or short cover): rounds UP to the nearest tick.
     - For SELL orders (long exit or short open): rounds DOWN to the nearest tick.
   This prevents optimistic backtesting fill prices. All arithmetic is performed on integer paise.

3. Elements in the file:
   - OrderSide: Enumeration defining BUY and SELL transaction sides.
   - TickQuantizer: Class providing static and instance methods for integer tick quantization.
   - quantize_tick: Core function quantizing integer paise against the trader.
   - quantize_price: Convenience wrapper converting Decimal/str/float to Paise and quantizing tick.

4. Final output of the file:
   - Exported OrderSide enum, TickQuantizer class, and quantization functions.
"""

from decimal import Decimal
from enum import Enum
from typing import Union

from packages.domain.money import Paise, to_paise


class OrderSide(str, Enum):
    """
    1. The use of class:
       Identifies the execution side of an order or trade (BUY or SELL).

    2. What the class contains:
       - BUY: Purchase transaction (long entry or short covering).
       - SELL: Sale transaction (long exit or short initiation).

    3. Technologies used and why:
       Inherits from str and Enum for serializability and explicit equality comparisons.

    4. Key design and overall design of the class:
       Standard exchange side convention governing the direction of adverse tick quantization.
    """
    BUY = "BUY"
    SELL = "SELL"


class TickQuantizer:
    """
    1. The use of class:
       Encapsulates exchange tick quantization rules, enforcing adverse-side rounding
       using pure integer arithmetic.

    2. What the class contains:
       Static methods:
         - quantize(): Quantizes integer price in paise against tick_paise for a given side.
         - quantize_price(): Parses Decimal/str/float input to Paise and quantizes to tick.

    3. Technologies used and why:
       Integer floor division (//) guaranteeing exact integer paise without floating-point math.

    4. Key design and overall design of the class:
       Directly satisfies ENGINE §4 Step 1:
         "quantize using tick_paise from the effective-dated contract master for that trade date
          (never a hardcoded constant) - buy rounds up to the nearest tick, sell rounds down to the
          nearest tick - using integer arithmetic only."
    """

    @staticmethod
    def quantize(price_paise: int, tick_paise: int, side: OrderSide) -> Paise:
        """
        1. The use of function:
           Quantizes an integer price in paise to the nearest valid exchange tick against the trader.

        2. How does the specific function work:
           - Validates that tick_paise > 0 and price_paise >= 0.
           - If side == OrderSide.BUY:
               Calculates ((price_paise + tick_paise - 1) // tick_paise) * tick_paise (ceiling).
           - If side == OrderSide.SELL:
               Calculates (price_paise // tick_paise) * tick_paise (floor).
           - Returns result wrapped in Paise.

        3. Concepts used in the function:
           Adverse-side rounding, integer modular arithmetic, prevention of optimistic fills.

        4. Places where this function is imported and used:
           Imported by packages/engine/execution.py, packages/engine/orders.py, and test fixtures.

        5. Final output of the function, before and after:
           Before: price_paise = 10023, tick_paise = 5, side = BUY.
           After: Paise(10025).
           Before: price_paise = 10023, tick_paise = 5, side = SELL.
           After: Paise(10020).
        """
        if tick_paise <= 0:
            raise ValueError(f"tick_paise must be strictly positive, got {tick_paise}")

        if price_paise < 0:
            raise ValueError(f"price_paise cannot be negative, got {price_paise}")

        if side == OrderSide.BUY:
            quantized = ((price_paise + tick_paise - 1) // tick_paise) * tick_paise
        elif side == OrderSide.SELL:
            quantized = (price_paise // tick_paise) * tick_paise
        else:
            raise ValueError(f"Invalid OrderSide: {side}. Must be OrderSide.BUY or OrderSide.SELL")

        return Paise(quantized)

    @staticmethod
    def quantize_price(price: Union[Decimal, str, int, float], tick_paise: int, side: OrderSide) -> Paise:
        """
        1. The use of function:
           Validates an arbitrary price representation, converts to integer Paise, and quantizes to tick.

        2. How does the specific function work:
           Calls to_paise(price) to obtain exact integer paise, then delegates to quantize().

        3. Concepts used in the function:
           Uniform conversion pipeline + adverse tick quantization.

        4. Places where this function is imported and used:
           Used when ingesting raw prices from JSON configs, CSV files, or API payloads.

        5. Final output of the function, before and after:
           Before: price = "100.23", tick_paise = 5, side = BUY.
           After: Paise(10025).
        """
        paise_val = to_paise(price)
        return TickQuantizer.quantize(int(paise_val), tick_paise, side)


def quantize_tick(price_paise: int, tick_paise: int, side: OrderSide) -> Paise:
    """
    1. The use of function:
       Standalone functional entrypoint for adverse tick quantization.

    2. How does the specific function work:
       Delegates to TickQuantizer.quantize(price_paise, tick_paise, side).

    3. Concepts used in the function:
       Functional interface for clean import in engine pipelines.

    4. Places where this function is imported and used:
       Imported by simulation loops and unit tests.

    5. Final output of the function, before and after:
       Before: price_paise, tick_paise, side. After: Quantized Paise.
    """
    return TickQuantizer.quantize(price_paise, tick_paise, side)
