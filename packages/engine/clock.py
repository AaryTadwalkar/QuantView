"""
1. What this file does:
   Defines the SimulationClock and calendar-minute generator for QuantView deterministic execution (Task M4-03).
   Advances step-by-step through exchange session minutes respecting the Asia/Kolkata market calendar.

2. Overall design:
   Enforces causal temporal progression per QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §4:
     - Operates strictly on exchange trading minutes (09:15 to 15:30 Asia/Kolkata, weekdays).
     - Each minute m is defined by its bar start s and bar end e (e = s + 60s).
     - Identifies timeframe decision boundaries (1m, 3m, 5m, 15m).
     - Invariant: Information from bar ending at e is only available to strategy at or after e (available_at <= e).

3. Elements in the file:
   - SimulationMinute: Value object representing a single discrete exchange calendar minute.
   - SimulationClock: Advances simulation time and yields sequential trading minutes.

4. Final output of the file:
   - Exported SimulationMinute and SimulationClock classes.
"""

from datetime import date, datetime, timedelta
from typing import Generator, NamedTuple

from packages.domain import (
    IST_TIMEZONE,
    UtcEpochSec,
    ist_datetime_to_utc_epoch,
)


class SimulationMinute(NamedTuple):
    """
    1. The use of class:
       Immutable container representing a single discrete exchange calendar minute bar.

    2. What the class contains:
       - session_date: datetime.date of the trading day in Asia/Kolkata.
       - bar_start_utc: UtcEpochSec representing minute start (e.g. 09:15:00 IST).
       - bar_end_utc: UtcEpochSec representing minute close (e.g. 09:16:00 IST).
       - ist_time_str: Human-readable HH:MM string in Asia/Kolkata.
       - is_session_open: True if this is the first minute (09:15).
       - is_force_flat_minute: True if this is 15:25 IST (standard auto-square-off).
       - is_final_session_minute: True if this is 15:29 IST (last bar of regular session).

    3. Technologies used and why:
       NamedTuple for lightweight, immutable minute representations.

    4. Key design and overall design of the class:
       Standardizes simulation step time coordinates across engine loops.
    """
    session_date: date
    bar_start_utc: UtcEpochSec
    bar_end_utc: UtcEpochSec
    ist_time_str: str
    is_session_open: bool
    is_force_flat_minute: bool
    is_final_session_minute: bool

    def is_timeframe_close(self, timeframe_minutes: int) -> bool:
        """
        1. The use of function:
           Determines if this minute represents the close of a higher timeframe bar (e.g. 5m, 15m).

        2. How does the specific function work:
           Parses ist_time_str, computes elapsed minutes since 09:15:00, and checks modulo timeframe_minutes.

        3. Concepts used in the function:
           Multi-timeframe bar synchronization.
        """
        h, m = map(int, self.ist_time_str.split(":"))
        elapsed = (h - 9) * 60 + (m - 15) + 1  # 1-indexed completed minutes
        return (elapsed % timeframe_minutes) == 0


class SimulationClock:
    """
    1. The use of class:
       Drives the causal simulation loop through exchange trading calendar minutes.

    2. What the class contains:
       - generate_session_minutes(): Yields 375 discrete SimulationMinute items for a given trade date.
       - generate_multi_session_minutes(): Yields SimulationMinute sequence across multiple trading dates.

    3. Technologies used and why:
       Python generators and zoneinfo/datetime for zero-leakage temporal navigation.

    4. Key design and overall design of the class:
       Guarantees strictly 375 standard 1-minute bars per regular session (09:15 to 15:30).
    """

    @classmethod
    def generate_session_minutes(cls, session_date: date) -> Generator[SimulationMinute, None, None]:
        """
        1. The use of function:
           Generates the 375 calendar minutes for a regular NSE trading session.

        2. How does the specific function work:
           Loops minute-by-minute from 09:15 to 15:29 IST, producing SimulationMinute with exact UTC timestamps.

        3. Concepts used in the function:
           Discrete time simulation grid.
        """
        # Weekends are excluded
        if session_date.weekday() >= 5:
            return

        start_dt = datetime(session_date.year, session_date.month, session_date.day, 9, 15, 0, tzinfo=IST_TIMEZONE)

        for minute_offset in range(375):
            current_bar_start = start_dt + timedelta(minutes=minute_offset)
            current_bar_end = current_bar_start + timedelta(minutes=1)

            start_utc = ist_datetime_to_utc_epoch(current_bar_start)
            end_utc = ist_datetime_to_utc_epoch(current_bar_end)
            time_str = current_bar_start.strftime("%H:%M")

            yield SimulationMinute(
                session_date=session_date,
                bar_start_utc=start_utc,
                bar_end_utc=end_utc,
                ist_time_str=time_str,
                is_session_open=(minute_offset == 0),
                is_force_flat_minute=(time_str == "15:25"),
                is_final_session_minute=(minute_offset == 374),  # 15:29:00
            )
