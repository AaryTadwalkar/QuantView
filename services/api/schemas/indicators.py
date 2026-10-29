"""
1. What this file does:
   Defines Pydantic data schemas for technical indicators, descriptor metadata, calculation parameters,
   and timeseries calculation results in the QuantView Gateway (Milestone M6-02, M6-11, Gate G4).

2. Overall design:
   Exposes strongly typed DTOs conforming to TradingView Lightweight Charts v5 specifications:
     - IndicatorParameter: Configurable variable definition with validation bounds and defaults.
     - IndicatorDescriptor: Indicator specification containing identity, category, chart pane assignment, and parameter list.
     - IndicatorComputeRequest: Request model specifying symbol, resolution, indicator identifier, and parameter overrides.
     - IndicatorValuePoint: Single timestamped point mapping line identifiers to numerical values.
     - IndicatorComputeResponse: Container model wrapping calculated indicator series.

3. Elements in the file:
   - IndicatorParameter: Parameter metadata and constraint schema.
   - IndicatorDescriptor: Schema-driven indicator definition and UI registration model.
   - IndicatorComputeRequest: Request payload for on-demand indicator calculation.
   - IndicatorValuePoint: UTC epoch timestamped line coordinate dictionary.
   - IndicatorComputeResponse: Standardized response envelope for computed indicator series.

4. Final output of the file:
   - Exported Pydantic schema models for indicator metadata and computation endpoints.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IndicatorParameter(BaseModel):
    """
    1. The use of class:
       Defines metadata, data type, and validation bounds for a single configurable indicator parameter.

    2. What the class contains:
       - name: Internal parameter variable identifier.
       - type: Data type descriptor string ('int', 'float', 'str').
       - default: Default argument value.
       - min_value: Optional lower numeric bound.
       - max_value: Optional upper numeric bound.
       - description: Human-readable explanation of parameter behavior.

    3. Technologies used and why:
       Pydantic BaseModel for automatic OpenAPI documentation and client-side form generation.

    4. Key design and overall design of the class:
       Enables UI-1 schema-driven indicator settings dialogs and property inspection.
    """

    name: str = Field(description="Parameter variable name")
    type: str = Field(description="Parameter data type ('int', 'float', 'str')")
    default: Any = Field(description="Default parameter value")
    min_value: Optional[float] = Field(default=None, description="Optional minimum numeric value")
    max_value: Optional[float] = Field(default=None, description="Optional maximum numeric value")
    description: str = Field(default="", description="Parameter description for UI tooltips")


class IndicatorDescriptor(BaseModel):
    """
    1. The use of class:
       Provides comprehensive metadata describing a technical indicator, its UI category, and parameter spec.

    2. What the class contains:
       - id: Canonical uppercase indicator identifier string (e.g. 'EMA', 'RSI').
       - name: Full human-readable display name.
       - category: Technical domain category ('trend', 'momentum', 'volatility', 'structural').
       - description: Technical calculation and operational summary.
       - pane: Visual placement designation ('primary' for price overlay, 'subpane' for oscillators).
       - parameters: List of IndicatorParameter schemas defining configurable settings.

    3. Technologies used and why:
       Pydantic BaseModel for serialization into the indicator registry discovery catalog.

    4. Key design and overall design of the class:
       Decouples frontend chart visualization controls from backend mathematical engines.
    """

    id: str = Field(description="Canonical unique indicator identifier")
    name: str = Field(description="Display name for chart interface")
    category: str = Field(description="Category ('trend', 'momentum', 'volatility', 'structural')")
    description: str = Field(description="Description of indicator formula and purpose")
    pane: str = Field(description="Placement target ('primary' or 'subpane')")
    parameters: List[IndicatorParameter] = Field(
        default_factory=list,
        description="List of configurable parameter definitions",
    )


class IndicatorComputeRequest(BaseModel):
    """
    1. The use of class:
       Request payload specifying instrument, resolution, indicator ID, and custom parameters.

    2. What the class contains:
       - symbol: Target underlying instrument or index ticker.
       - indicator_id: Identifier of indicator to calculate.
       - resolution: Candle timeframe (e.g. '1m', '5m', '15m', '1d').
       - params: Dictionary of parameter overrides matching IndicatorParameter names.
       - from_ts: Optional start timestamp filter in UTC epoch seconds.
       - to_ts: Optional end timestamp filter in UTC epoch seconds.
       - limit: Maximum number of bars to fetch and compute.

    3. Technologies used and why:
       Pydantic BaseModel with Field validation bounds ensuring safe memory and execution boundaries.

    4. Key design and overall design of the class:
       Enforces standard API request parameters aligned with GET /api/v1/market/candles.
    """

    symbol: str = Field(description="Instrument symbol (e.g. NSE:NIFTY50, NIFTY, INDIAVIX)")
    indicator_id: str = Field(description="Canonical indicator identifier (e.g. EMA, RSI, Supertrend)")
    resolution: str = Field(default="1m", description="Bar aggregation timeframe")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary of parameter overrides",
    )
    from_ts: Optional[int] = Field(default=None, description="Start timestamp in UTC epoch seconds")
    to_ts: Optional[int] = Field(default=None, description="End timestamp in UTC epoch seconds")
    limit: int = Field(default=5000, ge=1, le=10000, description="Maximum number of bars (1 to 10000)")


class IndicatorValuePoint(BaseModel):
    """
    1. The use of class:
       Represents a single timestamped indicator calculation output point.

    2. What the class contains:
       - time: Bar timestamp in UTC epoch seconds matching Lightweight Charts format.
       - values: Dictionary mapping indicator series keys to numeric floats, strings, or None (for warm-up NaNs).

    3. Technologies used and why:
       Pydantic BaseModel ensuring JSON compatibility with Lightweight Charts line/histogram series.

    4. Key design and overall design of the class:
       Accommodates single-line (EMA, RSI), multi-line (MACD, Supertrend), and structural levels with event labels.
    """

    time: int = Field(description="Timestamp in UTC epoch seconds")
    values: Dict[str, Any] = Field(
        description="Calculated line values (e.g. {'ema': 24500.5} or {'macd': 12.3, 'signal': 10.1})",
    )


class IndicatorComputeResponse(BaseModel):
    """
    1. The use of class:
       Response envelope containing calculated indicator timeseries data for charting.

    2. What the class contains:
       - indicator_id: Echoed indicator identifier.
       - symbol: Echoed instrument symbol.
       - resolution: Echoed candle resolution timeframe.
       - data: Chronological list of IndicatorValuePoint records.

    3. Technologies used and why:
       Pydantic BaseModel for typed JSON response serialization and documentation.

    4. Key design and overall design of the class:
       Provides a unified envelope format for all indicators regardless of output line complexity.
    """

    indicator_id: str = Field(description="Identifier of calculated indicator")
    symbol: str = Field(description="Evaluated instrument symbol")
    resolution: str = Field(description="Evaluated candle timeframe")
    data: List[IndicatorValuePoint] = Field(
        default_factory=list,
        description="Chronological series of indicator points",
    )
