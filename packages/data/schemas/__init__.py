"""
1. What this file does:
   Acts as the central package export point for all QuantView canonical schemas, Pydantic validation models,
   and PyArrow table schemas per QUANTVIEW_DATA_SPEC §4.

2. Overall design:
   Centralizes schema authority into a single package (packages/data/schemas/) preventing schema drift
   and prohibiting duplicate schema definitions across tools. Exposes models for:
     - Underlying index candles (1m/1d)
     - Expired and live option candles (1m)
     - India VIX volatility index candles (1m/1d)
     - Option chain snapshot headers and strike rows (v1, v2, v3 superset)

3. Elements in the file:
   - Re-exports UnderlyingCandleRow, OptionCandleRow, IndiaVixCandleRow
   - Re-exports OptionSnapshotCaptureRow, OptionSnapshotRow
   - Re-exports UNDERLYING_CANDLES_SCHEMA, OPTION_CANDLES_SCHEMA, INDIA_VIX_CANDLES_SCHEMA
   - Re-exports SNAPSHOT_CAPTURES_SCHEMA, SNAPSHOT_ROWS_SCHEMA
   - Re-exports validate_candle_ohlc, check_is_flat_bar, compute_field_presence_mask

4. Final output of the file:
   - Unified machine-readable canonical schema authority for QuantView.
"""

from packages.data.schemas.candles import (
    DERIVED_CANDLES_SCHEMA,
    INDIA_VIX_CANDLES_SCHEMA,
    OPTION_CANDLES_SCHEMA,
    UNDERLYING_CANDLES_SCHEMA,
    DerivedCandleRow,
    IndiaVixCandleRow,
    OptionCandleRow,
    UnderlyingCandleRow,
    check_is_flat_bar,
    validate_candle_ohlc,
)
from packages.data.schemas.eligibility import (
    DATA_ELIGIBILITY_SCHEMA,
    VALID_ELIGIBILITY_STATUSES,
    VALID_REASON_CODES,
    DataEligibilityRow,
)
from packages.data.schemas.snapshots import (
    SNAPSHOT_CAPTURES_SCHEMA,
    SNAPSHOT_ROWS_SCHEMA,
    OptionSnapshotCaptureRow,
    OptionSnapshotRow,
    compute_field_presence_mask,
)

__all__ = [
    "UnderlyingCandleRow",
    "OptionCandleRow",
    "IndiaVixCandleRow",
    "DerivedCandleRow",
    "UNDERLYING_CANDLES_SCHEMA",
    "OPTION_CANDLES_SCHEMA",
    "INDIA_VIX_CANDLES_SCHEMA",
    "DERIVED_CANDLES_SCHEMA",
    "validate_candle_ohlc",
    "check_is_flat_bar",
    "OptionSnapshotCaptureRow",
    "OptionSnapshotRow",
    "SNAPSHOT_CAPTURES_SCHEMA",
    "SNAPSHOT_ROWS_SCHEMA",
    "compute_field_presence_mask",
    "DataEligibilityRow",
    "DATA_ELIGIBILITY_SCHEMA",
    "VALID_ELIGIBILITY_STATUSES",
    "VALID_REASON_CODES",
]
