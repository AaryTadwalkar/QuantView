"""
1. What this file does:
   Defines the branded UtcEpochSec timestamp primitive and timezone conversions for QuantView.
   Enforces canonical UTC epoch integer seconds across all internal backtesting and streaming layers.

2. Overall design:
   QuantView adheres to ADR-041: all timestamps in databases, Parquets, run manifests, and replay cursors
   are represented as 64-bit UTC epoch seconds (UtcEpochSec). The Indian market timezone (Asia/Kolkata,
   UTC+05:30, no DST) is handled deterministically at parsing and presentation boundaries.
   This guarantees:
     - Zero timezone ambiguity in joins and order event logs.
     - Fast integer timestamp comparisons in the calendar-minute master loop.
     - Strict causal point-in-time sequencing: event.available_at <= decision_time.

3. Elements in the file:
   - UtcEpochSec: NewType wrapper around Python int (64-bit UTC epoch seconds).
   - IST_TIMEZONE: ZoneInfo instance for "Asia/Kolkata".
   - UTC_TIMEZONE: ZoneInfo instance for "UTC".
   - from_iso_to_utc_epoch: Parses ISO 8601 string to UtcEpochSec.
   - utc_epoch_to_iso: Formats UtcEpochSec to UTC ISO 8601 string.
   - utc_epoch_to_ist_datetime: Converts UtcEpochSec to an aware datetime in Asia/Kolkata.
   - ist_datetime_to_utc_epoch: Converts an aware or naive IST datetime to UtcEpochSec.
   - is_regular_trading_minute: Evaluates whether a given timestamp falls within 09:15-15:30 IST.

4. Final output of the file:
   - Exported UtcEpochSec type and timezone conversion helpers.
"""

from datetime import datetime, timezone, time
from typing import NewType
from zoneinfo import ZoneInfo

# Branded 64-bit integer timestamp representing seconds since Unix epoch in UTC
UtcEpochSec = NewType("UtcEpochSec", int)

# Canonical timezone definitions
IST_TIMEZONE = ZoneInfo("Asia/Kolkata")
UTC_TIMEZONE = timezone.utc

# Exchange regular session boundaries (Asia/Kolkata)
MARKET_OPEN_TIME = time(9, 15)
MARKET_CLOSE_TIME = time(15, 30)


def from_iso_to_utc_epoch(iso_str: str) -> UtcEpochSec:
    """
    1. The use of function:
       Parses an ISO 8601 timestamp string into an exact UtcEpochSec integer.

    2. How does the specific function work:
       - Uses datetime.fromisoformat() to parse string.
       - If naive, assumes Asia/Kolkata if no offset provided, else standardizes to UTC.
       - Converts to UTC timezone and takes int(dt.timestamp()).

    3. Concepts used in the function:
       Deterministic ISO parsing, implicit IST localization for exchange candles.

    4. Places where this function is imported and used:
       Imported by Parquet readers, config parsers, and data ingestion tools.

    5. Final output of the function, before and after:
       Before: "2026-10-26T09:15:00+05:30" or "2026-10-26 09:15:00".
       After: UtcEpochSec(1792986300).
    """
    cleaned = iso_str.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        # Naive vendor timestamps are exchange local (Asia/Kolkata)
        dt = dt.replace(tzinfo=IST_TIMEZONE)
    dt_utc = dt.astimezone(UTC_TIMEZONE)
    return UtcEpochSec(int(dt_utc.timestamp()))


def utc_epoch_to_iso(epoch: UtcEpochSec) -> str:
    """
    1. The use of function:
       Formats a UtcEpochSec integer into a standardized UTC ISO 8601 string.

    2. How does the specific function work:
       Constructs aware datetime in UTC from timestamp and calls isoformat().

    3. Concepts used in the function:
       ISO 8601 string formatting for serializable manifests and logs.

    4. Places where this function is imported and used:
       Imported by run manifest writers, decision loggers, and API responses.

    5. Final output of the function, before and after:
       Before: UtcEpochSec(1792986300).
       After: "2026-10-26T03:45:00+00:00".
    """
    dt = datetime.fromtimestamp(int(epoch), tz=UTC_TIMEZONE)
    return dt.isoformat()


def utc_epoch_to_ist_datetime(epoch: UtcEpochSec) -> datetime:
    """
    1. The use of function:
       Converts a UtcEpochSec integer into an aware datetime localized to Asia/Kolkata.

    2. How does the specific function work:
       Constructs UTC datetime from timestamp and converts to IST_TIMEZONE.

    3. Concepts used in the function:
       Timezone projection to exchange local time for session rule evaluation.

    4. Places where this function is imported and used:
       Imported by calendar-minute loop, force-flat checkers, and contract selectors.

    5. Final output of the function, before and after:
       Before: UtcEpochSec(1792986300).
       After: datetime(2026, 10, 26, 9, 15, tzinfo=ZoneInfo(key='Asia/Kolkata')).
    """
    return datetime.fromtimestamp(int(epoch), tz=UTC_TIMEZONE).astimezone(IST_TIMEZONE)


def ist_datetime_to_utc_epoch(dt: datetime) -> UtcEpochSec:
    """
    1. The use of function:
       Converts an IST datetime (aware or naive) into a UtcEpochSec integer.

    2. How does the specific function work:
       If naive, attaches IST_TIMEZONE. Converts to UTC and takes int(timestamp()).

    3. Concepts used in the function:
       Exchange local datetime to universal epoch conversion.

    4. Places where this function is imported and used:
       Imported by backtest run configuration builders and calendar generators.

    5. Final output of the function, before and after:
       Before: datetime(2026, 10, 26, 9, 15).
       After: UtcEpochSec(1792986300).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST_TIMEZONE)
    return UtcEpochSec(int(dt.astimezone(UTC_TIMEZONE).timestamp()))


def is_regular_trading_minute(epoch: UtcEpochSec) -> bool:
    """
    1. The use of function:
       Evaluates whether a UtcEpochSec timestamp falls within regular NSE equity derivative session hours.

    2. How does the specific function work:
       - Converts epoch to IST datetime.
       - Checks weekday (Monday=0 through Friday=4).
       - Checks time between 09:15:00 and 15:30:00 inclusive.

    3. Concepts used in the function:
       Trading session boundary validation.

    4. Places where this function is imported and used:
       Imported by master loop and data quality checkers.

    5. Final output of the function, before and after:
       Before: UtcEpochSec. After: True if regular weekday market minute, else False.
    """
    dt_ist = utc_epoch_to_ist_datetime(epoch)
    if dt_ist.weekday() >= 5:
        return False
    t = dt_ist.time()
    return MARKET_OPEN_TIME <= t <= MARKET_CLOSE_TIME
