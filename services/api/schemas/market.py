"""
1. What this file does:
   Defines Pydantic data schemas and models for the QuantView Market and Candle REST API
   (Milestones M6-01, M6-03, M6-16, and Release Gate G4).

2. Overall design:
   Provides strongly-typed schemas for market symbol definitions, single OHLCV candles,
   time-series candle responses, and real-time market quotes.
   Serializes directly into JSON conforming to the OpenAPI specification.

3. Elements in the file:
   - Candle: Single OHLCV bar with epoch timestamp and volume.
   - SymbolInfo: Metadata describing a tradeable or index instrument.
   - MarketQuote: Real-time price quote with daily change and high/low extremes.
   - CandleResponse: Container enclosing resolution, symbol, and ordered candle series.
   - ScreenerItem: Individual row item in the Indian Market Screener table.
   - ScreenerResponse: Container enclosing screener items and snapshot timestamp.

4. Final output of the file:
   - Exported Pydantic models for validation and serialization in services.api.routers.market.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class Candle(BaseModel):
    """
    1. The use of class:
       Data transfer model representing a single OHLCV candlestick bar.

    2. What the class contains:
       - time: UNIX epoch timestamp in seconds marking bar start.
       - open: Opening price of the period.
       - high: Highest traded price during the period.
       - low: Lowest traded price during the period.
       - close: Closing price of the period.
       - volume: Accumulated traded volume (defaults to 0).

    3. Technologies used and why:
       Pydantic BaseModel for runtime validation and automatic serialization to JSON.

    4. Key design and overall design of the class:
       Compact representation tailored for chart viewport renderers and algorithmic consumption.
    """

    time: int = Field(description="Bar start timestamp in UTC epoch seconds")
    open: float = Field(description="Open price")
    high: float = Field(description="High price")
    low: float = Field(description="Low price")
    close: float = Field(description="Close price")
    volume: int = Field(default=0, description="Traded volume count")


class SymbolInfo(BaseModel):
    """
    1. The use of class:
       Data transfer model providing metadata about a market index or trading instrument.

    2. What the class contains:
       - symbol: Standard symbol identifier (e.g. NSE:NIFTY50, INDIAVIX).
       - name: Human-readable display name.
       - type: Instrument category (e.g. INDEX, OPTION, STOCK).
       - tick_size: Minimum price movement increment.
       - lot_size: Market lot quantity.
       - description: Optional human-readable description.

    3. Technologies used and why:
       Pydantic BaseModel for typed symbol dictionary publication.

    4. Key design and overall design of the class:
       Provides frontend chart components and order routers with contract metadata.
    """

    symbol: str = Field(description="Canonical instrument symbol")
    name: str = Field(description="Display name")
    type: str = Field(description="Instrument asset class")
    tick_size: float = Field(description="Minimum tick size increment")
    lot_size: int = Field(description="Trading lot size")
    description: Optional[str] = Field(default=None, description="Optional instrument description")


class MarketQuote(BaseModel):
    """
    1. The use of class:
       Data transfer model representing the latest market price and daily performance metrics.

    2. What the class contains:
       - symbol: Canonical symbol identifier.
       - last_price: Most recent execution or candle close price.
       - change: Absolute price change relative to previous session close.
       - change_pct: Percentage price change relative to previous session close.
       - high: Intraday or latest session highest price.
       - low: Intraday or latest session lowest price.
       - volume: Traded volume count.
       - timestamp: Timestamp of the quote in UTC epoch seconds.

    3. Technologies used and why:
       Pydantic BaseModel for clean JSON API contracts and client telemetry.

    4. Key design and overall design of the class:
       Encapsulates top-level ticker summary metrics for dashboard headers and watchlists.
    """

    symbol: str = Field(description="Canonical instrument symbol")
    last_price: float = Field(description="Latest traded or close price")
    change: float = Field(description="Net price change relative to previous close")
    change_pct: float = Field(description="Percentage price change relative to previous close")
    high: float = Field(description="Period high price")
    low: float = Field(description="Period low price")
    volume: int = Field(description="Period traded volume")
    timestamp: int = Field(description="Quote timestamp in UTC epoch seconds")


class CandleResponse(BaseModel):
    """
    1. The use of class:
       Payload model returned by the historical and real-time candle retrieval endpoint.

    2. What the class contains:
       - symbol: Instrument symbol queried.
       - resolution: Resolution timeframe (e.g. 1m, 5m, 1d).
       - candles: List of Candle objects ordered chronologically ascending.

    3. Technologies used and why:
       Pydantic BaseModel for response validation and schema export.

    4. Key design and overall design of the class:
       Top-level envelope linking instrument context with the time-series array.
    """

    symbol: str = Field(description="Canonical instrument symbol")
    resolution: str = Field(description="Timeframe interval resolution")
    candles: List[Candle] = Field(default_factory=list, description="Chronologically sorted candles")


class ScreenerItem(BaseModel):
    """
    1. The use of class:
       Data model for an individual row item in the Indian Market Screener table.

    2. What the class contains:
       - symbol: Canonical symbol identifier (e.g. NSE:NIFTY50, INDIAVIX, NIFTY ATM CE, NIFTY ATM PE).
       - name: Human-readable display label.
       - type: Instrument category ('INDEX' | 'VOLATILITY' | 'OPTION_CE' | 'OPTION_PE').
       - last_price: Latest close/LTP price.
       - change: Absolute daily price change.
       - change_pct: Percentage daily price change.
       - high: Day high price.
       - low: Day low price.
       - volume: Traded volume count.
       - range_52w: Optional 52-week price range string (for indices).
       - regime: Optional volatility regime categorization ('Low (< 13)' | 'Normal (13–18)' | 'High (> 18)').
       - strike: Optional strike price for derivative contracts.
       - contract_id: Optional underlying option contract identifier.
       - expiry: Optional expiry date string for options.

    3. Technologies used and why:
       Pydantic BaseModel for typed JSON schema and browser table serialization.

    4. Key design and overall design of the class:
       Unified schema accommodating benchmark indices, volatility gauges, and ATM derivative contracts.
    """

    symbol: str = Field(description="Display or query symbol")
    name: str = Field(description="Display name")
    type: str = Field(description="Asset class / instrument type")
    last_price: float = Field(description="Current or latest traded price")
    change: float = Field(description="Absolute daily price change")
    change_pct: float = Field(description="Percentage daily price change")
    high: float = Field(description="Day high price")
    low: float = Field(description="Day low price")
    volume: int = Field(default=0, description="Traded volume count")
    range_52w: Optional[str] = Field(default=None, description="52-week price range")
    regime: Optional[str] = Field(default=None, description="Volatility regime description")
    strike: Optional[float] = Field(default=None, description="Option strike price")
    contract_id: Optional[str] = Field(default=None, description="Canonical contract identifier")
    expiry: Optional[str] = Field(default=None, description="Contract expiry date")


class ScreenerResponse(BaseModel):
    """
    1. The use of class:
       Response container for the Indian Market Screener endpoint.

    2. What the class contains:
       - timestamp: Current UTC epoch seconds.
       - items: List of ScreenerItem rows for NIFTY, VIX, ATM CE, and ATM PE.

    3. Technologies used and why:
       Pydantic BaseModel for JSON envelope generation.

    4. Key design and overall design of the class:
       Provides atomic snapshot of benchmark index, volatility, and ATM derivative premiums.
    """

    timestamp: int = Field(description="Snapshot timestamp in UTC epoch seconds")
    items: List[ScreenerItem] = Field(default_factory=list, description="Screener table rows")
