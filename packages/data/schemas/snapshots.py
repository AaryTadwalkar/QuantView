"""
1. What this file does:
   Defines the canonical Pydantic models and matching PyArrow schemas for option chain snapshot captures
   (`option_snapshot_captures`) and snapshot strike rows (`option_snapshot_rows`) per QUANTVIEW_DATA_SPEC §4.3 and §4.4.

2. Overall design:
   Normalizes heterogeneous snapshot captures (v1: 9 cols, v2: 7 cols, v3: 18 cols) into a unified,
   strictly validated schema. Guarantees:
     - Preservation of capture identity (snapshot_id) and raw source file references.
     - Preserves each individual capture without merging into synthetic continuous chains.
     - Field-presence masks documenting which optional fields existed in the original payload.
     - Exact IEEE-754 64-bit precision for IV and observed Greeks (never downcast to float16/32).
     - Full provenance tracking for path-derived expiries and quality anomalies.

3. Elements in the file:
   - OptionSnapshotCaptureRow: Pydantic model for snapshot capture header.
   - OptionSnapshotRow: Pydantic model for snapshot strike row.
   - SNAPSHOT_CAPTURES_SCHEMA: PyArrow schema for option_snapshot_captures dataset.
   - SNAPSHOT_ROWS_SCHEMA: PyArrow schema for option_snapshot_rows dataset.
   - compute_field_presence_mask: Function generating field presence descriptor.

4. Final output of the file:
   - Exported Pydantic validation classes and PyArrow schemas for snapshot datasets.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

import pyarrow as pa
from pydantic import BaseModel, ConfigDict, Field, field_validator


def compute_field_presence_mask(record: Dict) -> str:
    """
    1. The use of function:
       Computes a stable pipe-delimited string mask recording which optional fields are present in a source row.

    2. How does the specific function work:
       Checks key presence and non-null values for key optional fields (prev_oi, bid_qty, ask_qty, chng, chng_oi, iv, greeks).

    3. Concepts used in the function:
       Schema evolution tracking, field presence auditing.

    4. Places where this function is imported and used:
       Called during snapshot normalization in compact_option_snapshots.py.

    5. Final output of the function, before and after:
       Before: Raw dictionary. After: Mask string (e.g. 'spot|oi|vol|ltp|bid|ask|greeks').
    """
    present = []
    if record.get("spot_price") is not None:
        present.append("spot")
    if record.get("prev_oi") is not None:
        present.append("prev_oi")
    if record.get("bid_qty") is not None:
        present.append("depth_qty")
    if record.get("chng") is not None:
        present.append("chng")
    if record.get("iv") is not None or record.get("iv_observed") is not None:
        present.append("iv")
    if record.get("delta") is not None or record.get("delta_observed") is not None:
        present.append("greeks")
    return "|".join(present) if present else "basic"


class OptionSnapshotCaptureRow(BaseModel):
    """
    1. The use of class:
       Canonical Pydantic model for snapshot capture headers per QUANTVIEW_DATA_SPEC §4.3.

    2. What the class contains:
       - snapshot_id: Unique capture identifier string.
       - received_at: UTC timestamp when capture was received (availability time).
       - trade_date: Session date in Asia/Kolkata.
       - underlying: 'NIFTY'.
       - expiry: Optional expiry date requested or observed.
       - spot_price: Optional spot underlying price.
       - schema_version: Source schema version ('v1', 'v2', 'v3').
       - source_file: Relative path to raw capture CSV.
       - row_count: Number of option strike rows in capture.
       - completeness: Optional coverage ratio against instrument universe.
       - field_presence_mask: Mask of optional fields present.
       - quality_flags: List of validation tags.
       - ingested_at: Persistence timestamp UTC.

    3. Technologies used and why:
       Pydantic v2 BaseModel for immutable validation.

    4. Key design and overall design of the class:
       One row per physical capture file, ensuring capture boundaries and arrival times are never blurred.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str
    received_at: datetime
    trade_date: date
    underlying: str = "NIFTY"
    expiry: Optional[date] = None
    spot_price: Optional[float] = None
    schema_version: str
    source_file: str
    row_count: int
    completeness: Optional[float] = None
    field_presence_mask: str
    quality_flags: List[str] = Field(default_factory=list)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OptionSnapshotRow(BaseModel):
    """
    1. The use of class:
       Canonical Pydantic model for snapshot strike rows per QUANTVIEW_DATA_SPEC §4.4.

    2. What the class contains:
       - snapshot_id: Parent capture ID.
       - received_at: Local receive time UTC.
       - trade_date: Session trade date.
       - underlying: 'NIFTY'.
       - expiry: Contract expiry date.
       - strike: Exact Decimal(9, 2) strike price.
       - option_type: 'CE' or 'PE'.
       - spot_price: Spot price if present in capture.
       - oi: Open interest integer.
       - prev_oi: Previous session open interest (v1).
       - volume: Cumulative/intraday volume.
       - ltp: Last traded price.
       - bid, ask: Best bid and ask prices.
       - bid_qty, ask_qty: Quantities at top of book.
       - change: Price change.
       - change_oi: Open interest change.
       - iv_observed: Vendor-observed implied volatility.
       - delta_observed, gamma_observed, theta_observed, vega_observed: Observed Greeks.
       - schema_version: Decoder version string.
       - field_presence_mask: Present field mask.
       - quality_flags: Validation flags.
       - source_file: Raw source reference path.

    3. Technologies used and why:
       Pydantic v2 with exact strike Decimal and 64-bit float precision.

    4. Key design and overall design of the class:
       Provides a superset schema for all snapshot versions. All absent fields default to None.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str
    received_at: datetime
    trade_date: date
    underlying: str = "NIFTY"
    expiry: date
    strike: Decimal
    option_type: str
    spot_price: Optional[float] = None
    oi: Optional[int] = None
    prev_oi: Optional[int] = None
    volume: Optional[int] = None
    ltp: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_qty: Optional[int] = None
    ask_qty: Optional[int] = None
    change: Optional[float] = None
    change_oi: Optional[int] = None
    iv_observed: Optional[float] = None
    delta_observed: Optional[float] = None
    gamma_observed: Optional[float] = None
    theta_observed: Optional[float] = None
    vega_observed: Optional[float] = None
    schema_version: str
    field_presence_mask: str
    quality_flags: List[str] = Field(default_factory=list)
    source_file: str

    @field_validator("option_type")
    @classmethod
    def validate_option_type(cls, v: str) -> str:
        """Validates option type strictly CE or PE."""
        if v not in ("CE", "PE"):
            raise ValueError(f"Invalid option_type: {v}. Must be 'CE' or 'PE'")
        return v


# Authoritative PyArrow Schemas matching Pydantic Models for Parquet Storage
SNAPSHOT_CAPTURES_SCHEMA = pa.schema([
    pa.field("snapshot_id", pa.string(), nullable=False),
    pa.field("received_at", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("trade_date", pa.date32(), nullable=False),
    pa.field("underlying", pa.string(), nullable=False),
    pa.field("expiry", pa.date32(), nullable=True),
    pa.field("spot_price", pa.float64(), nullable=True),
    pa.field("schema_version", pa.string(), nullable=False),
    pa.field("source_file", pa.string(), nullable=False),
    pa.field("row_count", pa.int32(), nullable=False),
    pa.field("completeness", pa.float64(), nullable=True),
    pa.field("field_presence_mask", pa.string(), nullable=False),
    pa.field("quality_flags", pa.list_(pa.string()), nullable=False),
    pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
])

SNAPSHOT_ROWS_SCHEMA = pa.schema([
    pa.field("snapshot_id", pa.string(), nullable=False),
    pa.field("received_at", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("trade_date", pa.date32(), nullable=False),
    pa.field("underlying", pa.string(), nullable=False),
    pa.field("expiry", pa.date32(), nullable=False),
    pa.field("strike", pa.decimal128(9, 2), nullable=False),
    pa.field("option_type", pa.string(), nullable=False),
    pa.field("spot_price", pa.float64(), nullable=True),
    pa.field("oi", pa.int64(), nullable=True),
    pa.field("prev_oi", pa.int64(), nullable=True),
    pa.field("volume", pa.int64(), nullable=True),
    pa.field("ltp", pa.float64(), nullable=True),
    pa.field("bid", pa.float64(), nullable=True),
    pa.field("ask", pa.float64(), nullable=True),
    pa.field("bid_qty", pa.int32(), nullable=True),
    pa.field("ask_qty", pa.int32(), nullable=True),
    pa.field("change", pa.float64(), nullable=True),
    pa.field("change_oi", pa.int64(), nullable=True),
    pa.field("iv_observed", pa.float64(), nullable=True),
    pa.field("delta_observed", pa.float64(), nullable=True),
    pa.field("gamma_observed", pa.float64(), nullable=True),
    pa.field("theta_observed", pa.float64(), nullable=True),
    pa.field("vega_observed", pa.float64(), nullable=True),
    pa.field("schema_version", pa.string(), nullable=False),
    pa.field("field_presence_mask", pa.string(), nullable=False),
    pa.field("quality_flags", pa.list_(pa.string()), nullable=False),
    pa.field("source_file", pa.string(), nullable=False),
])
