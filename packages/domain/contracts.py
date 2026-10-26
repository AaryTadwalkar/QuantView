"""
1. What this file does:
   Defines the contract identifiers, operating modes, and instrument models for QuantView.
   Provides immutable representations of tradable Indian market derivative contracts.

2. Overall design:
   QuantView enforces strict separation of execution modes (UNDERLYING_DIRECTIONAL, ACTUAL_OPTIONS,
   SYNTHETIC_OPTIONS_ESTIMATE). A contract is uniquely identified by its exchange instrument key,
   trading symbol, expiry date, strike price, option type (CE/PE), and lot size. This module guarantees:
     - Immutability of contract specifications.
     - Strict typing of contract attributes avoiding stringly-typed bugs.
     - Zero broker SDK coupling.

3. Elements in the file:
   - OperatingMode: Canonical enumeration of engine operating modes.
   - OptionType: Enumeration of option contract styles (CE, PE).
   - ContractIdentifier: Immutable NamedTuple uniquely identifying an option instrument.

4. Final output of the file:
   - Exported OperatingMode, OptionType, and ContractIdentifier classes.
"""

from enum import Enum
from typing import NamedTuple


class OperatingMode(str, Enum):
    """
    1. The use of class:
       Enumerates all authoritative execution and research modes in QuantView.

    2. What the class contains:
       - RESEARCH: Exploratory analysis and parameter scans.
       - UNDERLYING_DIRECTIONAL: Trades underlying directly without options contracts.
       - ACTUAL_OPTIONS: Backtests using actual historical option candle records.
       - SYNTHETIC_OPTIONS_ESTIMATE: Theoretical research estimate using Black-Scholes.
       - MANUAL_PAPER: Manual user paper order execution.
       - STRATEGY_PAPER: Automated paper trading.
       - LIVE: Gated live broker execution (disabled by default until GATE-05).

    3. Technologies used and why:
       Inherits from str and Enum for serializable string equality and JSON interchange.

    4. Key design and overall design of the class:
       Guarantees that directional underlying results are never conflated with actual options results (ADR-009).
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
       Identifies call or put European option contracts.

    2. What the class contains:
       - CE: European Call Option (NSE convention).
       - PE: European Put Option (NSE convention).

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
