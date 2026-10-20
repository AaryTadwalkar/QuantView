"""
1. What this file does:
   Defines foundational domain models, types, currency representation, and timestamps for QuantView.

2. Overall design:
   The domain package is the leaf dependency of all QuantView packages. It imports zero internal
   modules. It enforces:
     - Exact integer paise representation (1 INR = 100 paise) preventing floating point drift.
     - Branded UtcEpochSec timestamps for point-in-time invariants.
     - Core enumeration types for trading modes, contract sides, and order intents.

3. Elements in the file:
   - Paise: Integer-based currency unit (paise).
   - UtcEpochSec: 64-bit integer timestamp in UTC seconds.
   - OperatingMode: Canonical enum for engine operation modes.
   - OptionType: Enum for CE/PE option sides.
   - ContractIdentifier: Value object representing an option contract.

4. Final output of the file:
   - Exported domain primitives and value objects.
"""

from enum import Enum
from typing import NewType, NamedTuple

# Strict integer types for monetary amounts and timestamps
Paise = NewType("Paise", int)
UtcEpochSec = NewType("UtcEpochSec", int)


class OperatingMode(str, Enum):
    """
    1. The use of class:
       Enumerates all authoritative execution and research modes in QuantView.

    2. What the class contains:
       - RESEARCH: Exploratory analysis.
       - UNDERLYING_DIRECTIONAL: Trades underlying directly without options contracts.
       - ACTUAL_OPTIONS: Backtests using actual historical option candle records.
       - SYNTHETIC_OPTIONS_ESTIMATE: Theoretical research estimate using Black-Scholes.
       - MANUAL_PAPER: Manual user paper order execution.
       - STRATEGY_PAPER: Automated paper trading.
       - LIVE: Gated live broker execution (disabled by default until GATE-05).

    3. Technologies used and why:
       Inherits from str and Enum for serializable string equality and JSON interchange.

    4. Key design and overall design of the class:
       Guarantees that directional underlying results are never conflated with actual options results.
    """
    RESEARCH = "RESEARCH"
    UNDERLYING_DIRECTIONAL = "UNDERLYING_DIRECTIONAL"
    ACTUAL_OPTIONS = "ACTUAL_OPTIONS"
    SYNTHETIC_OPTIONS_ESTIMATE = "SYNTHETIC_OPTIONS_ESTIMATE"
    MANUAL_PAPER = "MANUAL_PAPER"
    STRATEGY_PAPER = "STRATEGY_PAPER"
    LIVE = "LIVE"


class OptionType(str, Enum):
    """
    1. The use of class:
       Identifies call or put option contracts.

    2. What the class contains:
       - CE: European Call Option.
       - PE: European Put Option.

    3. Technologies used and why:
       str and Enum for explicit NSE derivatives conventions.

    4. Key design and overall design of the class:
       Restricted to CE and PE; invalid types fail fast.
    """
    CE = "CE"
    PE = "PE"


class ContractIdentifier(NamedTuple):
    """
    1. The use of class:
       Immutable composite key uniquely identifying a tradable option contract.

    2. What the class contains:
       - instrument_key: Upstox/exchange instrument identifier (e.g. 'NSE_FO|41685|26-12-2024').
       - trading_symbol: Human-readable exchange symbol (e.g. 'NIFTY 23750 CE 26 DEC 24').
       - expiry_date: ISO 8601 expiry string (YYYY-MM-DD).
       - strike_price: Float or int strike price.
       - option_type: CE or PE.
       - lot_size: Contract multiplier (e.g. 25).

    3. Technologies used and why:
       NamedTuple for zero-overhead immutability, hashing, and tuple unpacking.

    4. Key design and overall design of the class:
       Encapsulates all static contract metadata required for contract selection and ledger tracking.
    """
    instrument_key: str
    trading_symbol: str
    expiry_date: str
    strike_price: float
    option_type: OptionType
    lot_size: int


def rupees_to_paise(rupees: float) -> Paise:
    """
    1. The use of function:
       Converts decimal INR rupees to integer paise using standard banker's / half-up rounding.

    2. How does the specific function work:
       Multiplies float rupees by 100 and rounds to nearest integer.

    3. Concepts used in the function:
       Integer financial accounting preventing float representation leakage.

    4. Places where this function is imported and used:
       Imported by ledger, risk, and order fill models.

    5. Final output of the function, before and after:
       Before: float (e.g. 150.25). After: Paise(15025).
    """
    return Paise(int(round(rupees * 100)))


def paise_to_rupees(paise: Paise) -> float:
    """
    1. The use of function:
       Converts integer paise to decimal INR rupees for external display or reporting.

    2. How does the specific function work:
       Divides integer paise by 100.0.

    3. Concepts used in the function:
       Boundary conversion from internal exact paise to display decimal currency.

    4. Places where this function is imported and used:
       Imported by API view models and charting formatters.

    5. Final output of the function, before and after:
       Before: Paise(15025). After: float (150.25).
    """
    return float(paise) / 100.0
