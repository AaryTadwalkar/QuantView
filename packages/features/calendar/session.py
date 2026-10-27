"""
1. What this file does:
   Implements intraday market session progress, regular trading hours (RTH) tracking,
   and regulatory cutoff countdown features for NSE / Indian equity derivatives markets.

2. Overall design:
   Converts UTC timestamps to Indian Standard Time (IST = UTC+5:30) and evaluates
   point-in-time session metrics: minutes since session open (09:15 IST), countdown
   to entry cutoff (15:00 IST / RK-19), countdown to mandatory force-flat (15:25 IST / RK-20),
   session progress fraction [0.0, 1.0], day of week, and days to expiration (DTE).

3. Elements in the file:
   - SessionProgress: NamedTuple containing point-in-time session timing indicators.
   - parse_utc_to_ist: Helper converting UTC epoch or ISO string to IST datetime.
   - compute_session_progress: Core evaluation function computing session progress metrics.
   - register_session_progress_feature: Registry helper binding the feature to FeatureRegistry.

4. Final output of the file:
   - Causal, deterministic session progress feature stream for intraday risk and timing rules.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import NamedTuple, Optional, Union

from packages.features.registry import FeatureRegistry
from packages.features.schemas import (
    FeatureDefinition,
    MemoryClass,
    RepaintClass,
    SourceTier,
)

# IST Timezone Offset: UTC + 5:30
IST_OFFSET = timedelta(hours=5, minutes=30)
IST_TZ = timezone(IST_OFFSET, name="IST")

# Canonical Market Trading Hours for NSE
MARKET_OPEN_TIME = time(9, 15)      # 09:15:00 IST
ENTRY_CUTOFF_TIME = time(15, 0)     # 15:00:00 IST (RK-19: No new entries)
FORCE_FLAT_TIME = time(15, 25)      # 15:25:00 IST (RK-20: Mandatory force-flat)
MARKET_CLOSE_TIME = time(15, 30)    # 15:30:00 IST

TOTAL_SESSION_MINUTES = 375         # 09:15 to 15:30 = 6 hours 15 mins = 375 minutes
ENTRY_CUTOFF_MINUTES = 345          # 09:15 to 15:00 = 5 hours 45 mins = 345 minutes
FORCE_FLAT_MINUTES = 370            # 09:15 to 15:25 = 6 hours 10 mins = 370 minutes


class SessionProgress(NamedTuple):
    """
    1. The use of class:
       Immutable point-in-time representation of intraday market session progress.

    2. What the class contains:
       - ts_utc: UTC epoch timestamp in seconds.
       - ist_datetime: ISO formatted string of the IST datetime.
       - is_regular_trading_hours: Boolean indicating if time is within 09:15-15:30 IST.
       - minutes_since_open: Integer minutes elapsed since 09:15 IST (0 to 375).
       - minutes_to_entry_cutoff: Countdown minutes to 15:00 IST entry cutoff (0 when >= 15:00).
       - minutes_to_force_flat: Countdown minutes to 15:25 IST force-flat (0 when >= 15:25).
       - session_fraction: Float in [0.0, 1.0] representing session completion.
       - day_of_week: Day of week integer (0=Monday, 6=Sunday).
       - days_to_expiry: Optional integer count of calendar days to target expiry date.

    3. Technologies used and why:
       NamedTuple for lightweight, immutable serialization and low evaluation overhead.

    4. Key design and overall design of the class:
       Provides point-in-time temporal anchors for strategy execution and risk evaluators.
    """
    ts_utc: int
    ist_datetime: str
    is_regular_trading_hours: bool
    minutes_since_open: int
    minutes_to_entry_cutoff: int
    minutes_to_force_flat: int
    session_fraction: float
    day_of_week: int
    days_to_expiry: Optional[int] = None


def parse_utc_to_ist(ts: Union[int, float, datetime]) -> datetime:
    """
    1. The use of function:
       Converts a UTC epoch timestamp or datetime into an IST-aware datetime.

    2. How does the specific function work:
       If input is numeric (epoch seconds), instantiates UTC datetime and applies IST_TZ.
       If input is datetime, converts it to IST timezone.

    3. Concepts used in the function:
       UTC and IST timezone conversions, epoch translation.

    4. Places where this function is imported and used:
       Used by compute_session_progress, calendar feature helpers, and test fixtures.

    5. Final output of the function, before and after:
       Before: UTC epoch seconds or datetime. After: Aware datetime in IST (UTC+5:30).
    """
    if isinstance(ts, (int, float)):
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    elif isinstance(ts, datetime):
        if ts.tzinfo is None:
            dt_utc = ts.replace(tzinfo=timezone.utc)
        else:
            dt_utc = ts.astimezone(timezone.utc)
    else:
        raise ValueError(f"Unsupported timestamp type: {type(ts)}")
    return dt_utc.astimezone(IST_TZ)


def compute_session_progress(
    ts: Union[int, float, datetime],
    expiry_date: Optional[Union[date, str]] = None,
) -> SessionProgress:
    """
    1. The use of function:
       Computes point-in-time session progress metrics for a given timestamp.

    2. How does the specific function work:
       1. Converts timestamp to IST datetime.
       2. Computes minutes elapsed since market open (09:15:00 IST).
       3. Calculates remaining minutes to 15:00 entry cutoff and 15:25 force-flat.
       4. Binds session_fraction within [0.0, 1.0].
       5. If expiry_date is provided, computes calendar days to expiry.
       6. Emits immutable SessionProgress record.

    3. Concepts used in the function:
       NSE intraday calendar logic, risk cutoff countdowns, point-in-time scheduling.

    4. Places where this function is imported and used:
       Used by trading strategies, risk evaluator, and feature pipeline.

    5. Final output of the function, before and after:
       Before: Timestamp and optional expiry. After: Populated SessionProgress NamedTuple.
    """
    dt_ist = parse_utc_to_ist(ts)
    current_time = dt_ist.time()
    current_date = dt_ist.date()

    # Determine epoch seconds
    ts_sec = int(dt_ist.timestamp())

    # Regular trading hours check: 09:15:00 to 15:30:00
    is_rth = (current_time >= MARKET_OPEN_TIME) and (current_time <= MARKET_CLOSE_TIME)

    # Compute minutes since 09:15:00
    open_dt = datetime.combine(current_date, MARKET_OPEN_TIME, tzinfo=IST_TZ)
    delta_sec = (dt_ist - open_dt).total_seconds()
    minutes_since_open = int(delta_sec // 60)

    # Clamp minutes_since_open to [0, TOTAL_SESSION_MINUTES]
    clamped_minutes = max(0, min(TOTAL_SESSION_MINUTES, minutes_since_open))

    # Countdown to 15:00 entry cutoff (345 mins)
    minutes_to_entry_cutoff = max(0, ENTRY_CUTOFF_MINUTES - minutes_since_open) if is_rth else 0

    # Countdown to 15:25 force-flat (370 mins)
    minutes_to_force_flat = max(0, FORCE_FLAT_MINUTES - minutes_since_open) if is_rth else 0

    # Session fraction
    session_fraction = round(clamped_minutes / float(TOTAL_SESSION_MINUTES), 6)

    # Days to expiry calculation
    dte: Optional[int] = None
    if expiry_date is not None:
        target_expiry = (
            date.fromisoformat(expiry_date)
            if isinstance(expiry_date, str)
            else expiry_date
        )
        dte = (target_expiry - current_date).days

    return SessionProgress(
        ts_utc=ts_sec,
        ist_datetime=dt_ist.isoformat(),
        is_regular_trading_hours=is_rth,
        minutes_since_open=clamped_minutes,
        minutes_to_entry_cutoff=minutes_to_entry_cutoff,
        minutes_to_force_flat=minutes_to_force_flat,
        session_fraction=session_fraction,
        day_of_week=dt_ist.weekday(),
        days_to_expiry=dte,
    )


def register_session_progress_feature() -> str:
    """
    1. The use of function:
       Registers SESSION_PROGRESS feature definition into FeatureRegistry.

    2. How does the specific function work:
       Constructs FeatureDefinition with ZERO_REPAINT class and binds compute_session_progress.

    3. Concepts used in the function:
       Registry binding, zero-repaint calendar feature metadata.

    4. Places where this function is imported and used:
       Called during feature package discovery and registry initialization.

    5. Final output of the function, before and after:
       Before: Unregistered feature. After: Registered feature ID string.
    """
    defn = FeatureDefinition(
        name="SESSION_PROGRESS",
        version="v1",
        params={},
        lookback_window=1,
        warm_up_bars=1,
        memory_class=MemoryClass.FINITE,
        source_tier=SourceTier.CALENDAR,
        repaint_class=RepaintClass.NONE,
        output_schema={
            "minutes_since_open": "int32",
            "minutes_to_entry_cutoff": "int32",
            "minutes_to_force_flat": "int32",
            "session_fraction": "float64",
            "is_regular_trading_hours": "bool",
        },
        description="Point-in-time NSE session progress, 15:00 cutoff and 15:25 force-flat countdowns.",
    )
    registry = FeatureRegistry()
    return registry.register(
        definition=defn,
        compute_fn=compute_session_progress,
        metadata={"category": "calendar"},
    )
