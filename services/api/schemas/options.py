"""
1. What this file does:
   Defines Pydantic data schemas and models for the QuantView Option Chain, Greeks, and Option Candles API
   (Milestones M6-03b, M6-15, M6-18, and Release Gate G4).

2. Overall design:
   Provides strongly-typed schemas conforming to OpenAPI standards:
     - OptionStrikeQuote: Individual strike contract quote with Greeks, depth, open interest, and pricing.
     - OptionChainRow: Strike-level row pairing Call (CE) and Put (PE) strike quotes.
     - OptionChainResponse: Complete option matrix response centered around ATM with spot price metadata.
     - OptionCandleResponse: Per-contract historical candlestick series container.

3. Elements in the file:
   - OptionStrikeQuote: Quote model for single option leg (CE or PE).
   - OptionChainRow: Paired row for a strike price with optional CE and PE legs.
   - OptionChainResponse: Envelope model for the option chain response.
   - OptionCandleResponse: Envelope model for contract historical candle series.

4. Final output of the file:
   - Exported Pydantic models for services.api.routers.options and external client contracts.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from services.api.schemas.market import Candle


class OptionStrikeQuote(BaseModel):
    """
    1. The use of class:
       Data transfer model representing a single option contract quote with pricing, volume,
       open interest, and Black-Scholes Greeks.

    2. What the class contains:
       - trading_symbol: Vendor or human-readable contract symbol.
       - strike: Contract strike price.
       - option_type: Contract flavor ("CE" or "PE").
       - ltp: Last traded price.
       - change: Net price change from previous close.
       - change_pct: Percentage price change from previous close.
       - bid: Best available bid price.
       - ask: Best available ask price.
       - oi: Open interest contract count.
       - oi_change: Net change in open interest.
       - iv: Implied volatility percentage.
       - delta: Option Delta Greek sensitivity.
       - gamma: Option Gamma Greek sensitivity.
       - theta: Option Theta Greek sensitivity (daily decay).
       - vega: Option Vega Greek sensitivity.
       - volume: Accumulated traded volume count.

    3. Technologies used and why:
       Pydantic BaseModel for deterministic serialization, runtime validation, and OpenAPI documentation.

    4. Key design and overall design of the class:
       Compact single-leg schema serving both option chain matrix cells and single-strike quote cards.
    """

    trading_symbol: str = Field(description="Vendor or exchange trading symbol")
    strike: float = Field(description="Strike price")
    option_type: str = Field(description="Option contract type ('CE' or 'PE')")
    ltp: float = Field(description="Last traded price")
    change: float = Field(default=0.0, description="Absolute price change from previous close")
    change_pct: float = Field(default=0.0, description="Percentage price change from previous close")
    bid: float = Field(default=0.0, description="Best available bid price")
    ask: float = Field(default=0.0, description="Best available ask price")
    oi: int = Field(default=0, description="Open interest contract count")
    oi_change: int = Field(default=0, description="Net change in open interest")
    iv: float = Field(default=0.0, description="Implied volatility")
    delta: float = Field(default=0.0, description="Delta Greek sensitivity")
    gamma: float = Field(default=0.0, description="Gamma Greek sensitivity")
    theta: float = Field(default=0.0, description="Theta Greek sensitivity")
    vega: float = Field(default=0.0, description="Vega Greek sensitivity")
    volume: int = Field(default=0, description="Accumulated traded volume count")


class OptionChainRow(BaseModel):
    """
    1. The use of class:
       Data transfer model representing a single strike price row in an option chain matrix,
       pairing the Call (CE) and Put (PE) quotes.

    2. What the class contains:
       - strike: Common strike price for the paired row.
       - ce: Optional quote for the Call contract.
       - pe: Optional quote for the Put contract.

    3. Technologies used and why:
       Pydantic BaseModel for JSON serialization and structural consistency across chain tables.

    4. Key design and overall design of the class:
       Enables standard dual-column tabular rendering (Calls on left, Puts on right) centered at strike.
    """

    strike: float = Field(description="Strike price for this row")
    ce: Optional[OptionStrikeQuote] = Field(default=None, description="Call option quote")
    pe: Optional[OptionStrikeQuote] = Field(default=None, description="Put option quote")


class OptionChainResponse(BaseModel):
    """
    1. The use of class:
       Payload model returned by the reconstructed option chain endpoint.

    2. What the class contains:
       - underlying: Canonical underlying symbol (defaults to 'NIFTY').
       - expiry_date: Target expiry date string in YYYY-MM-DD format.
       - spot_price: Underlying spot price captured at snapshot time.
       - atm_strike: At-The-Money strike price rounded to standard increment.
       - timestamp: Snapshot capture timestamp in UTC epoch seconds.
       - strikes: Ordered list of OptionChainRow models centered around ATM.

    3. Technologies used and why:
       Pydantic BaseModel for schema generation and client deserialization.

    4. Key design and overall design of the class:
       Top-level envelope linking underlying market context with the multi-strike options matrix.
    """

    underlying: str = Field(default="NIFTY", description="Underlying index or asset symbol")
    expiry_date: str = Field(description="Option contract expiry date (YYYY-MM-DD)")
    spot_price: float = Field(description="Underlying spot price at snapshot time")
    atm_strike: float = Field(description="Calculated At-The-Money strike price")
    timestamp: int = Field(description="Snapshot timestamp in UTC epoch seconds")
    strikes: List[OptionChainRow] = Field(default_factory=list, description="Ordered option chain strike rows")
    total_ce_oi: int = Field(default=0, description="Total Call open interest across strikes")
    total_pe_oi: int = Field(default=0, description="Total Put open interest across strikes")
    pcr: float = Field(default=0.0, description="Put-Call Ratio (total_pe_oi / total_ce_oi)")


class OptionCandleResponse(BaseModel):
    """
    1. The use of class:
       Payload model returned by the per-contract option candle retrieval endpoint.

    2. What the class contains:
       - contract_id: Canonical contract identifier string.
       - symbol: Underlying instrument symbol (e.g. 'NIFTY').
       - expiry: Expiry date string (YYYY-MM-DD).
       - strike: Strike price of the queried contract.
       - option_type: Contract option type ('CE' or 'PE').
       - resolution: Timeframe interval resolution (e.g. '1m', '5m', '1d').
       - candles: Chronologically ordered list of Candle bars.

    3. Technologies used and why:
       Pydantic BaseModel with nested Candle schemas from services.api.schemas.market.

    4. Key design and overall design of the class:
       Serves single-strike candlestick charts and trade marker overlays in the dashboard UI.
    """

    contract_id: str = Field(description="Canonical contract identifier")
    symbol: str = Field(description="Underlying instrument symbol")
    expiry: str = Field(description="Option contract expiry date (YYYY-MM-DD)")
    strike: float = Field(description="Strike price of the contract")
    option_type: str = Field(description="Option contract type ('CE' or 'PE')")
    resolution: str = Field(description="Candlestick timeframe interval resolution")
    candles: List[Candle] = Field(default_factory=list, description="Chronologically sorted OHLCV bars")
