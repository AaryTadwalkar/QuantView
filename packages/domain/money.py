"""
1. What this file does:
   Defines the exact-money currency primitives and conversion functions for QuantView.
   Enforces integer paise representation (1 INR = 100 paise) across all financial calculation paths.

2. Overall design:
   Floating-point arithmetic introduces non-deterministic representation drift in financial software
   (e.g., 0.1 + 0.2 != 0.3). In Indian equity derivatives backtesting and live contract-note reconciliation,
   all calculations must match exchange and broker figures within <= 1 paisa (and 0-paisa drift against
   authoritative hand-calculated or broker calculator fixtures). This module provides:
     - The `Paise` branded integer type.
     - Strict Decimal / string / int parsing to Paise.
     - Rejection of binary floats with fractional paise beyond micro-tolerances.
     - Reversible formatting functions back to exact Decimal and string representations.

3. Elements in the file:
   - Paise: NewType wrapper around standard Python int representing monetary value in paise.
   - PriceUnquantizableError: Exception raised when a float price has unquantizable fractional paise.
   - to_paise: Master conversion function translating Decimal, str, int, or float to Paise.
   - from_rupees: Explicit semantic conversion from rupee units (Decimal, str, int) to Paise.
   - paise_to_decimal: Converts integer paise to an exact Decimal representation in rupees.
   - paise_to_str: Formats integer paise into a standard two-decimal currency string (e.g., "150.25").
   - rupees_to_paise: Backward-compatible alias for from_rupees.
   - paise_to_rupees: Backward-compatible conversion from Paise to float rupees.

4. Final output of the file:
   - Exported currency primitives and arithmetic conversion functions.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import NewType, Union

# Strict integer type for currency representation in paise (100 paise = 1 INR)
Paise = NewType("Paise", int)


class PriceUnquantizableError(ValueError):
    """
    1. The use of class:
       Exception raised when an incoming price input contains unquantizable fractional paise
       or invalid floating-point representation that cannot be unambiguously mapped to integer paise.

    2. What the class contains:
       Standard ValueError subclass with diagnostic price and reason context.

    3. Technologies used and why:
       Inherits from ValueError for idiomatic Python error hierarchy and test catchability.

    4. Key design and overall design of the class:
       Provides a stable, structured error code ('PRICE_NOT_QUANTIZABLE') matching the canonical
       Engine Specification (ENGINE §4 Step 1).
    """

    def __init__(self, message: str, original_value: object = None):
        super().__init__(message)
        self.error_code = "PRICE_NOT_QUANTIZABLE"
        self.original_value = original_value


def to_paise(val: Union[Decimal, str, int, float]) -> Paise:
    """
    1. The use of function:
       Converts a monetary rupee value (as Decimal, str, int, or validated float) into exact integer Paise.

    2. How does the specific function work:
       - If val is Decimal: multiplies by 100, quantizes to integer using ROUND_HALF_UP, returns Paise(int).
       - If val is str: parses into Decimal, multiplies by 100 with ROUND_HALF_UP, returns Paise(int).
       - If val is int: interprets as whole rupees (e.g., 100 -> 10,000 paise).
       - If val is float: validates that abs(val * 100 - round(val * 100)) < 1e-6. If breached, raises
         PriceUnquantizableError with code PRICE_NOT_QUANTIZABLE. Otherwise converts via round().

    3. Concepts used in the function:
       Exact monetary quantization, boundary validation, elimination of binary floating-point drift.

    4. Places where this function is imported and used:
       Imported by order matchers, fee calculators, contract selectors, and ledger writers.

    5. Final output of the function, before and after:
       Before: Decimal('150.25') or str '150.25' or float 150.25.
       After: Paise(15025).
    """
    if isinstance(val, Decimal):
        cents = (val * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return Paise(int(cents))

    if isinstance(val, str):
        try:
            d = Decimal(val.strip())
            cents = (d * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return Paise(int(cents))
        except (InvalidOperation, ValueError) as err:
            raise PriceUnquantizableError(f"Invalid monetary string '{val}'", original_value=val) from err

    if isinstance(val, int) and not isinstance(val, bool):
        return Paise(val * 100)

    if isinstance(val, float):
        # Strict IEEE-754 boundary check: must represent a valid 2-decimal rupee price
        scaled = val * 100.0
        nearest = round(scaled)
        if abs(scaled - nearest) >= 1e-6:
            raise PriceUnquantizableError(
                f"Float price {val} contains unquantizable fractional paise (drift >= 1e-6)",
                original_value=val,
            )
        return Paise(int(nearest))

    raise TypeError(f"Unsupported type for conversion to Paise: {type(val).__name__} (value: {val})")


def from_rupees(val: Union[Decimal, str, int, float]) -> Paise:
    """
    1. The use of function:
       Explicit semantic alias for converting rupee amounts to integer paise.

    2. How does the specific function work:
       Delegates directly to to_paise(val).

    3. Concepts used in the function:
       Single conversion pipeline ensuring uniform validation.

    4. Places where this function is imported and used:
       Imported across domain, ledger, and engine packages.

    5. Final output of the function, before and after:
       Before: Rupee input (e.g. Decimal('20.50')). After: Paise(2050).
    """
    return to_paise(val)


def paise_to_decimal(paise: Paise) -> Decimal:
    """
    1. The use of function:
       Converts an integer Paise amount to an exact Decimal in rupees with two decimal places.

    2. How does the specific function work:
       Constructs Decimal(int(paise)) / Decimal(100) and quantizes to '0.01'.

    3. Concepts used in the function:
       Reversible exact decimal representation for financial reporting.

    4. Places where this function is imported and used:
       Imported by metrics generators, reporting tools, and ledger projections.

    5. Final output of the function, before and after:
       Before: Paise(15025). After: Decimal('150.25').
    """
    return (Decimal(int(paise)) / Decimal(100)).quantize(Decimal("0.01"))


def paise_to_str(paise: Paise) -> str:
    """
    1. The use of function:
       Formats an integer Paise amount into a standard two-decimal currency string.

    2. How does the specific function work:
       Converts paise to Decimal via paise_to_decimal() and returns string format '{:.2f}'.

    3. Concepts used in the function:
       Deterministic string serialization for logs, JSON payloads, and UI tables.

    4. Places where this function is imported and used:
       Imported by REST API serializers, manifest writers, and CLI backtest summaries.

    5. Final output of the function, before and after:
       Before: Paise(15025). After: "150.25".
    """
    return f"{paise_to_decimal(paise):.2f}"


def rupees_to_paise(rupees: float) -> Paise:
    """
    1. The use of function:
       Backward-compatible helper converting float INR rupees to integer paise.

    2. How does the specific function work:
       Delegates to to_paise(rupees).

    3. Concepts used in the function:
       Backward compatibility with Phase 0/1 existing package code.

    4. Places where this function is imported and used:
       Imported by existing legacy test fixtures and tests/unit/test_package_boundaries.py.

    5. Final output of the function, before and after:
       Before: float 150.25. After: Paise(15025).
    """
    return to_paise(rupees)


def paise_to_rupees(paise: Paise) -> float:
    """
    1. The use of function:
       Backward-compatible helper converting integer paise to float rupees for legacy consumers.

    2. How does the specific function work:
       Divides integer paise by 100.0.

    3. Concepts used in the function:
       Float projection for third-party visualization libraries (e.g. lightweight-charts).

    4. Places where this function is imported and used:
       Imported by chart formatters and legacy tests.

    5. Final output of the function, before and after:
       Before: Paise(15025). After: float 150.25.
    """
    return float(int(paise)) / 100.0
