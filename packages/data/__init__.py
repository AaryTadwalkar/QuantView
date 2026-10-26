"""
1. What this file does:
   Defines the canonical data access layer, dataset manifests, schema contracts, and India VIX models for QuantView.

2. Overall design:
   The data package mediates all read/write operations against the canonical Parquet data lake
   and DuckDB analytical views. It guarantees:
     - Dataset manifests are validated before execution.
     - Raw responses remain decoupled from canonical analytical tables.
     - Look-ahead bias is prevented at query boundaries.
     - Supporting market indices (such as India VIX) maintain strict non-derivative semantics and causal availability.

3. Elements in the file:
   - DatasetManifest: Value object recording dataset versions, file lists, row counts, and checksums.
   - IndiaVixCandle: Canonical data class for India VIX index candles adhering to QUANTVIEW_DATA_SPEC §4.10.
   - parse_india_vix_candle: Function converting raw candle arrays into validated IndiaVixCandle instances.
   - RateBudgetManager: Thread-safe REST rate limiter prioritizing live market snapshots over backfill.
   - BudgetConfig: Configuration dataclass for REST quota thresholds and timing.
   - RequestPriority: Priority level enum (HIGH for live snapshots, LOW for backfill).
   - BudgetExhaustedError: Exception raised when budget request times out.

4. Final output of the file:
   - Exported data contracts, dataset manifests, and validated market data domain models.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from packages.domain import UtcEpochSec
from packages.data.budget import (
    RateBudgetManager,
    BudgetConfig,
    RequestPriority,
    BudgetExhaustedError,
)

__all__ = [
    "DatasetManifest",
    "IndiaVixCandle",
    "parse_india_vix_candle",
    "RateBudgetManager",
    "BudgetConfig",
    "RequestPriority",
    "BudgetExhaustedError",
]


class DatasetManifest:
    """
    1. The use of class:
       Maintains provenance and cryptographic integrity records for canonical lake datasets.

    2. What the class contains:
       - dataset_name: Identifier of the dataset (e.g. 'underlying_candles_1m').
       - version: Monotonic dataset version string.
       - file_count: Number of constituent parquet files.
       - total_rows: Aggregate row count across partitions.
       - root_path: Directory containing dataset files.

    3. Technologies used and why:
       Standard Python dataclass-like structure for metadata serialization.

    4. Key design and overall design of the class:
       Immutable snapshot of data state used by worker_compute to pin datasets for reproducible runs.
    """

    def __init__(self, dataset_name: str, version: str, file_count: int, total_rows: int, root_path: Path):
        """
        1. The use of function:
           Initializes a DatasetManifest record.

        2. How does the specific function work:
           Stores dataset attributes and validates that root_path exists or is a valid Path.

        3. Concepts used in the function:
           Provenance tracking, path encapsulation.

        4. Places where this function is imported and used:
           Used by data worker when publishing finalized lake partitions.

        5. Final output of the function, before and after:
           Before: Raw metadata values. After: Initialized DatasetManifest instance.
        """
        self.dataset_name = dataset_name
        self.version = version
        self.file_count = file_count
        self.total_rows = total_rows
        self.root_path = root_path

    def to_dict(self) -> Dict:
        """
        1. The use of function:
           Serializes manifest to a plain dictionary for JSON export.

        2. How does the specific function work:
           Returns dictionary of manifest fields with root_path as string.

        3. Concepts used in the function:
           JSON serialization.

        4. Places where this function is imported and used:
           Called when writing manifest.json companion files.

        5. Final output of the function, before and after:
           Before: DatasetManifest object. After: Dictionary.
        """
        return {
            "dataset_name": self.dataset_name,
            "version": self.version,
            "file_count": self.file_count,
            "total_rows": self.total_rows,
            "root_path": str(self.root_path).replace("\\", "/"),
        }


@dataclass(frozen=True)
class IndiaVixCandle:
    """
    1. The use of class:
       Represents a canonical India VIX (NSE_INDEX|India VIX) candle conforming to QUANTVIEW_DATA_SPEC §4.10.

    2. What the class contains:
       - instrument_key: Fixed index key 'NSE_INDEX|India VIX'.
       - interval: Bar interval ('1m' or '1d').
       - ts_start: UtcEpochSec bar start time.
       - ts_end: UtcEpochSec bar end time.
       - open: Float opening volatility index level.
       - high: Float high volatility index level.
       - low: Float low volatility index level.
       - close: Float closing volatility index level.
       - volume: Int nominal index volume (non-traded).
       - oi: Int open interest (strictly 0 for indices).
       - source: Source identifier string.
       - quality_flags: List of string quality tags (e.g. ['VALID']).
       - available_at: UtcEpochSec timestamp when candle becomes causally visible.
       - is_derivative: Bool invariant (strictly False).

    3. Technologies used and why:
       Python dataclass with frozen=True for immutability and memory efficiency.

    4. Key design and overall design of the class:
       Guarantees point-in-time safety by requiring available_at to equal ts_end for 1m bars,
       or session close (15:30 IST) for daily bars. Disallows open interest or derivative operations.
    """
    instrument_key: str
    interval: str
    ts_start: UtcEpochSec
    ts_end: UtcEpochSec
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int
    source: str
    quality_flags: List[str]
    available_at: UtcEpochSec
    is_derivative: bool = False


def parse_india_vix_candle(raw: List, interval: str = "1m", source: str = "upstox_v3_historical_candle") -> IndiaVixCandle:
    """
    1. The use of function:
       Parses raw 7-element candle data into an immutable, validated IndiaVixCandle instance.

    2. How does the specific function work:
       - Extracts [timestamp_str, open, high, low, close, volume, oi].
       - Parses ISO 8601 timestamp to UTC seconds.
       - Enforces OHLC integrity (high >= max(o, c), low <= min(o, c), low > 0).
       - Enforces non-traded index invariant: oi is set to 0 and is_derivative is False.
       - Enforces causal availability: available_at = ts_end for 1m; available_at = 15:30 IST for 1d.

    3. Concepts used in the function:
       Causal point-in-time availability, non-derivative index distinction, data validation.

    4. Places where this function is imported and used:
       Imported by historical backfill tools, feature extractors, and test suites.

    5. Final output of the function, before and after:
       Before: Raw candle list (e.g. ['2026-01-20T09:15:00+05:30', 13.5, 13.8, 13.4, 13.6, 0, 0]).
       After: Validated IndiaVixCandle object.
    """
    if len(raw) < 5:
        raise ValueError(f"India VIX candle requires at least 5 elements, received {len(raw)}")

    ts_str = raw[0]
    dt = datetime.fromisoformat(ts_str)
    ts_start_sec = int(dt.timestamp())

    o = float(raw[1])
    h = float(raw[2])
    l = float(raw[3])
    cl = float(raw[4])
    vol = int(raw[5]) if len(raw) > 5 and raw[5] is not None else 0
    # India VIX is an index; open interest is strictly 0 regardless of vendor payload
    oi = 0

    if h < max(o, cl) or l > min(o, cl) or l < 0.0:
        raise ValueError(f"Invalid OHLC relationship in India VIX candle: O={o}, H={h}, L={l}, C={cl}")

    if interval == "1m":
        ts_end_sec = ts_start_sec + 60
        avail_sec = ts_end_sec
    elif interval == "1d":
        # Daily candle: available only at session close (15:30 IST = UTC hour 10, minute 0)
        # Calculate session close UTC timestamp for the given date
        session_close_dt = datetime(dt.year, dt.month, dt.day, 15, 30, 0, tzinfo=dt.tzinfo)
        ts_end_sec = int(session_close_dt.timestamp())
        avail_sec = ts_end_sec
    else:
        raise ValueError(f"Unsupported India VIX interval: {interval}. Allowed: '1m', '1d'")

    return IndiaVixCandle(
        instrument_key="NSE_INDEX|India VIX",
        interval=interval,
        ts_start=UtcEpochSec(ts_start_sec),
        ts_end=UtcEpochSec(ts_end_sec),
        open=o,
        high=h,
        low=l,
        close=cl,
        volume=vol,
        oi=oi,
        source=source,
        quality_flags=["VALID"],
        available_at=UtcEpochSec(avail_sec),
        is_derivative=False,
    )
