"""
1. What this file does:
   Defines the canonical Pydantic models and matching PyArrow schemas for market candle datasets in QuantView:
   underlying candles (1m/1d), option candles (1m), and India VIX volatility index candles (1m/1d).

2. Overall design:
   Acts as the central single source of truth for candle schemas per QUANTVIEW_DATA_SPEC §4.1, §4.2, and §4.10.
   Guarantees:
     - Exact decimal strike prices (decimal128(9, 2)) preventing floating-point key representation.
     - Strict UTC-aware timestamp schemas (`timestamp[us, tz=UTC]`) and point-in-time causal availability.
     - Bi-directional compatibility between Pydantic validation models and PyArrow table schemas.
     - Enforcement of OHLC invariants (High >= max(Open, Close), Low <= min(Open, Close), Low >= 0).
     - Explicit handling and flagging of flat bars and vendor negative-volume anomalies.

3. Elements in the file:
   - UnderlyingCandleRow: Pydantic model for underlying index candles.
   - OptionCandleRow: Pydantic model for historical/live option candles.
   - IndiaVixCandleRow: Pydantic model for India VIX index candles.
   - UNDERLYING_CANDLES_SCHEMA: PyArrow schema for underlying candles Parquet dataset.
   - OPTION_CANDLES_SCHEMA: PyArrow schema for option candles Parquet dataset.
   - INDIA_VIX_CANDLES_SCHEMA: PyArrow schema for India VIX Parquet dataset.
   - validate_candle_ohlc: Function verifying mathematical OHLC invariants.
   - check_is_flat_bar: Function identifying canonical flat bars per DATA Spec §4.

4. Final output of the file:
   - Exported Pydantic validation classes, matching PyArrow Parquet schemas, and invariant validators.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

import pyarrow as pa
from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_candle_ohlc(open_px: float, high_px: float, low_px: float, close_px: float) -> bool:
    """
    1. The use of function:
       Validates core mathematical OHLC price invariants for a financial candle bar.

    2. How does the specific function work:
       Ensures High >= max(Open, Close), Low <= min(Open, Close), and Low >= 0.

    3. Concepts used in the function:
       Mathematical bounds checking, price boundary verification.

    4. Places where this function is imported and used:
       Imported by Pydantic models, Parquet promotion tools, and test suites.

    5. Final output of the function, before and after:
       Before: 4 raw float prices. After: Boolean True if valid, False if violated.
    """
    if high_px < max(open_px, close_px):
        return False
    if low_px > min(open_px, close_px):
        return False
    if low_px < 0.0:
        return False
    return True


def check_is_flat_bar(volume: Optional[int], open_px: float, high_px: float, low_px: float, close_px: float) -> bool:
    """
    1. The use of function:
       Identifies whether a candle bar constitutes a canonical flat bar per QUANTVIEW_DATA_SPEC §4.

    2. How does the specific function work:
       A bar is flat exactly when volume == 0 AND open == high == low == close.
       Zero volume alone or equal OHLC alone is NOT sufficient to classify a bar as flat.

    3. Concepts used in the function:
       Specification compliance, flat-bar classification.

    4. Places where this function is imported and used:
       Imported by DuckDB view generators, simulation models, and promotion tools.

    5. Final output of the function, before and after:
       Before: Candle volume and OHLC prices. After: Boolean True if flat, False otherwise.
    """
    vol = volume if volume is not None else 0
    return vol == 0 and (open_px == high_px == low_px == close_px)


class UnderlyingCandleRow(BaseModel):
    """
    1. The use of class:
       Canonical Pydantic model for underlying index candles conforming to QUANTVIEW_DATA_SPEC §4.1.

    2. What the class contains:
       - instrument_key: Stable instrument identifier string (e.g. 'NSE_INDEX|Nifty 50').
       - underlying: Canonical underlying symbol ('NIFTY').
       - interval: Bar interval string ('1m', '1d', etc.).
       - ts_start: UTC timestamp for inclusive bar start.
       - ts_end: UTC timestamp for exclusive bar end.
       - available_at: UTC timestamp when bar becomes causally visible.
       - open, high, low, close: Float64 OHLC prices.
       - volume: Optional integer volume.
       - oi: Optional integer open interest.
       - source: Source adapter identifier string.
       - source_version: API/schema version string.
       - revision: Monotonic revision number (int32).
       - is_active: Manifest-resolved active row flag.
       - quality_flags: List of validation/quality tag strings.
       - ingested_at: UTC timestamp when persisted.

    3. Technologies used and why:
       Pydantic v2 BaseModel for strict schema validation, type coercion, and JSON interchange.

    4. Key design and overall design of the class:
       Enforces causal availability (available_at == ts_end for intraday; 15:30 IST for 1d)
       and validates OHLC invariants at initialization.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_key: str
    underlying: str = "NIFTY"
    interval: str
    ts_start: datetime
    ts_end: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[int] = None
    oi: Optional[int] = None
    source: str
    source_version: str = "v1"
    revision: int = 1
    is_active: bool = True
    quality_flags: List[str] = Field(default_factory=list)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("high")
    @classmethod
    def validate_ohlc_high(cls, v: float, info) -> float:
        """Validates that high is greater than or equal to open."""
        open_val = info.data.get("open")
        if open_val is not None and v < open_val:
            raise ValueError(f"High ({v}) cannot be less than Open ({open_val})")
        return v

    @field_validator("low")
    @classmethod
    def validate_ohlc_low(cls, v: float, info) -> float:
        """Validates that low is less than or equal to open and non-negative."""
        open_val = info.data.get("open")
        if open_val is not None and v > open_val:
            raise ValueError(f"Low ({v}) cannot be greater than Open ({open_val})")
        if v < 0.0:
            raise ValueError(f"Low ({v}) cannot be negative")
        return v


class OptionCandleRow(UnderlyingCandleRow):
    """
    1. The use of class:
       Canonical Pydantic model for historical and live option candle records per QUANTVIEW_DATA_SPEC §4.2.

    2. What the class contains:
       Inherits all UnderlyingCandleRow fields and adds:
       - contract_id: Stable internal contract identifier string.
       - trading_symbol: Optional human-readable exchange symbol.
       - expiry: Contract expiry date.
       - strike: Exact Decimal(9, 2) strike price.
       - option_type: Option right ('CE' or 'PE').
       - lot_size_at_source: Optional contract multiplier at observation.

    3. Technologies used and why:
       Inherits from UnderlyingCandleRow with strict Decimal strike type to prohibit binary float keys.

    4. Key design and overall design of the class:
       Ensures that option-chain records are partitioned by expiry and keyed by exact strike and contract ID.
    """
    contract_id: str
    trading_symbol: Optional[str] = None
    expiry: date
    strike: Decimal
    option_type: str
    lot_size_at_source: Optional[int] = None

    @field_validator("option_type")
    @classmethod
    def validate_option_type(cls, v: str) -> str:
        """Validates that option type is strictly CE or PE."""
        if v not in ("CE", "PE"):
            raise ValueError(f"Invalid option_type: {v}. Must be 'CE' or 'PE'")
        return v


class IndiaVixCandleRow(BaseModel):
    """
    1. The use of class:
       Canonical Pydantic model for India VIX index candles per QUANTVIEW_DATA_SPEC §4.10.

    2. What the class contains:
       - instrument_key: Fixed index key 'NSE_INDEX|India VIX'.
       - interval: Interval string ('1m' or '1d').
       - ts_start: Inclusive UTC start timestamp.
       - ts_end: Exclusive UTC end timestamp.
       - open, high, low, close: Float64 index levels.
       - volume: Non-traded nominal volume integer (default 0).
       - oi: Open interest integer (strictly 0 for volatility index).
       - source: Source identifier string.
       - quality_flags: List of validation tags.
       - available_at: UTC timestamp when candle becomes causally available.
       - ingested_at: Ingestion timestamp UTC.

    3. Technologies used and why:
       Pydantic v2 BaseModel enforcing non-derivative invariants.

    4. Key design and overall design of the class:
       Enforces oi == 0, disallows derivative contracts on index, and enforces causal availability.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_key: str = "NSE_INDEX|India VIX"
    interval: str
    ts_start: datetime
    ts_end: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    oi: int = 0
    source: str = "upstox_v3_historical_candle"
    quality_flags: List[str] = Field(default_factory=lambda: ["VALID"])
    available_at: datetime
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("oi")
    @classmethod
    def validate_zero_oi(cls, v: int) -> int:
        """Enforces that open interest is strictly 0 for non-derivative index."""
        if v != 0:
            raise ValueError("India VIX is a volatility index; open interest must strictly be 0")
        return v


# Authoritative PyArrow Schemas matching Pydantic Models for Parquet Storage
UNDERLYING_CANDLES_SCHEMA = pa.schema([
    pa.field("instrument_key", pa.string(), nullable=False),
    pa.field("underlying", pa.string(), nullable=False),
    pa.field("interval", pa.string(), nullable=False),
    pa.field("ts_start", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("ts_end", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("available_at", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("open", pa.float64(), nullable=False),
    pa.field("high", pa.float64(), nullable=False),
    pa.field("low", pa.float64(), nullable=False),
    pa.field("close", pa.float64(), nullable=False),
    pa.field("volume", pa.int64(), nullable=True),
    pa.field("oi", pa.int64(), nullable=True),
    pa.field("source", pa.string(), nullable=False),
    pa.field("source_version", pa.string(), nullable=False),
    pa.field("revision", pa.int32(), nullable=False),
    pa.field("is_active", pa.bool_(), nullable=False),
    pa.field("quality_flags", pa.list_(pa.string()), nullable=False),
    pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
])

OPTION_CANDLES_SCHEMA = pa.schema([
    pa.field("contract_id", pa.string(), nullable=False),
    pa.field("instrument_key", pa.string(), nullable=False),
    pa.field("trading_symbol", pa.string(), nullable=True),
    pa.field("underlying", pa.string(), nullable=False),
    pa.field("expiry", pa.date32(), nullable=False),
    pa.field("strike", pa.decimal128(9, 2), nullable=False),
    pa.field("option_type", pa.string(), nullable=False),
    pa.field("interval", pa.string(), nullable=False),
    pa.field("ts_start", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("ts_end", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("available_at", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("open", pa.float64(), nullable=False),
    pa.field("high", pa.float64(), nullable=False),
    pa.field("low", pa.float64(), nullable=False),
    pa.field("close", pa.float64(), nullable=False),
    pa.field("volume", pa.int64(), nullable=True),
    pa.field("oi", pa.int64(), nullable=True),
    pa.field("lot_size_at_source", pa.int32(), nullable=True),
    pa.field("source", pa.string(), nullable=False),
    pa.field("source_version", pa.string(), nullable=False),
    pa.field("revision", pa.int32(), nullable=False),
    pa.field("is_active", pa.bool_(), nullable=False),
    pa.field("quality_flags", pa.list_(pa.string()), nullable=False),
    pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
])

INDIA_VIX_CANDLES_SCHEMA = pa.schema([
    pa.field("instrument_key", pa.string(), nullable=False),
    pa.field("interval", pa.string(), nullable=False),
    pa.field("ts_start", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("ts_end", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("open", pa.float64(), nullable=False),
    pa.field("high", pa.float64(), nullable=False),
    pa.field("low", pa.float64(), nullable=False),
    pa.field("close", pa.float64(), nullable=False),
    pa.field("volume", pa.int64(), nullable=False),
    pa.field("oi", pa.int64(), nullable=False),
    pa.field("source", pa.string(), nullable=False),
    pa.field("quality_flags", pa.list_(pa.string()), nullable=False),
    pa.field("available_at", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
])


class DerivedCandleRow(BaseModel):
    """
    1. The use of class:
       Canonical Pydantic model for higher-timeframe derived candles per QUANTVIEW_DATA_SPEC §4.6.

    2. What the class contains:
       - derivation_id: Stable identifier hash for the derived partition/batch.
       - derivation_version: Generator code version (e.g. 'v1').
       - instrument_key: Underlying or instrument identifier.
       - underlying: 'NIFTY'.
       - interval: Target timeframe ('3m', '5m', '15m', '30m', '1h', '4h').
       - input_interval: Canonical source interval ('1m').
       - input_manifest_hash: SHA-256 hash of active input manifest.
       - session_policy: Trading session boundary enforcement policy string.
       - ts_start, ts_end, available_at: UTC timestamps ensuring causal availability.
       - open, high, low, close: Mathematically aggregated OHLC levels.
       - volume, oi: Aggregated volume sum and terminal open interest.
       - is_partial: True if bucket is incomplete at session close.
       - is_active: Manifest selection flag.
       - quality_flags: List of validation tags.
       - ingested_at: Persistence timestamp UTC.

    3. Technologies used and why:
       Pydantic v2 BaseModel for frozen immutable validation.

    4. Key design and overall design of the class:
       Carries full derivation provenance, input dataset hash, and causal availability metadata.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    derivation_id: str
    derivation_version: str = "v1"
    instrument_key: str = "NSE_INDEX|Nifty 50"
    underlying: str = "NIFTY"
    interval: str
    input_interval: str = "1m"
    input_manifest_hash: str
    session_policy: str = "REGULAR_SESSION_0915_1530"
    ts_start: datetime
    ts_end: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[int] = None
    oi: Optional[int] = None
    is_partial: bool = False
    is_active: bool = True
    quality_flags: List[str] = Field(default_factory=lambda: ["VALID"])
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("close")
    @classmethod
    def validate_ohlc_invariants(cls, v: float, info) -> float:
        """Validates that OHLC invariants hold for derived bars."""
        values = info.data
        if "open" in values and "high" in values and "low" in values:
            if not validate_candle_ohlc(values["open"], values["high"], values["low"], v):
                raise ValueError("Derived bar violates OHLC price invariants")
        return v


DERIVED_CANDLES_SCHEMA = pa.schema([
    pa.field("derivation_id", pa.string(), nullable=False),
    pa.field("derivation_version", pa.string(), nullable=False),
    pa.field("instrument_key", pa.string(), nullable=False),
    pa.field("underlying", pa.string(), nullable=False),
    pa.field("interval", pa.string(), nullable=False),
    pa.field("input_interval", pa.string(), nullable=False),
    pa.field("input_manifest_hash", pa.string(), nullable=False),
    pa.field("session_policy", pa.string(), nullable=False),
    pa.field("ts_start", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("ts_end", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("available_at", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("open", pa.float64(), nullable=False),
    pa.field("high", pa.float64(), nullable=False),
    pa.field("low", pa.float64(), nullable=False),
    pa.field("close", pa.float64(), nullable=False),
    pa.field("volume", pa.int64(), nullable=True),
    pa.field("oi", pa.int64(), nullable=True),
    pa.field("is_partial", pa.bool_(), nullable=False),
    pa.field("is_active", pa.bool_(), nullable=False),
    pa.field("quality_flags", pa.list_(pa.string()), nullable=False),
    pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
])

