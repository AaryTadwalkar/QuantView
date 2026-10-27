"""
1. What this file does:
   Unit tests for SimulationClock and the calendar-minute loop (Task M4-03).

2. Overall design:
   Uses pytest to verify:
     - Exactly 375 1-minute bars per regular weekday session (09:15 to 15:30 Asia/Kolkata).
     - Weekends yield zero bars.
     - Multi-timeframe bar close detection (3m, 5m, 15m).
     - Session boundaries: 09:15 is_session_open, 15:25 is_force_flat_minute, 15:29 is_final_session_minute.

3. Elements in the file:
   - TestSimulationClock: Unit tests for calendar minute generation and multi-timeframe synchronization.

4. Final output of the file:
   - Automated pass/fail test execution for Task M4-03.
"""

from datetime import date

import pytest

from packages.engine.clock import SimulationClock, SimulationMinute


class TestSimulationClock:
    """
    1. The use of class:
       Unit test suite validating causal clock mechanics and session geometry.

    2. What the class contains:
       - test_weekday_session_generates_375_minutes: Validates 375 bars per day.
       - test_weekend_session_generates_zero_minutes: Validates weekend exclusion.
       - test_session_boundary_flags: Validates 09:15, 15:25, and 15:29 flags.
       - test_multi_timeframe_close_detection: Validates 5m and 15m bar closes.
    """

    def test_weekday_session_generates_375_minutes(self):
        """Verifies that a standard weekday generates exactly 375 minutes (09:15 to 15:29 inclusive)."""
        d = date(2025, 1, 9)  # Thursday
        minutes = list(SimulationClock.generate_session_minutes(d))
        assert len(minutes) == 375
        assert minutes[0].ist_time_str == "09:15"
        assert minutes[-1].ist_time_str == "15:29"

    def test_weekend_session_generates_zero_minutes(self):
        """Verifies that weekend dates yield zero minutes."""
        d_sat = date(2025, 1, 11)  # Saturday
        d_sun = date(2025, 1, 12)  # Sunday
        assert len(list(SimulationClock.generate_session_minutes(d_sat))) == 0
        assert len(list(SimulationClock.generate_session_minutes(d_sun))) == 0

    def test_session_boundary_flags(self):
        """Verifies boundary flags: session open, force flat (15:25), and final minute (15:29)."""
        d = date(2025, 1, 9)
        minutes = list(SimulationClock.generate_session_minutes(d))

        open_bar = minutes[0]
        assert open_bar.is_session_open is True
        assert open_bar.is_force_flat_minute is False
        assert open_bar.is_final_session_minute is False

        # Find 15:25
        bar_1525 = next(m for m in minutes if m.ist_time_str == "15:25")
        assert bar_1525.is_force_flat_minute is True

        # Final bar 15:29
        final_bar = minutes[-1]
        assert final_bar.is_final_session_minute is True
        assert final_bar.ist_time_str == "15:29"

    def test_multi_timeframe_close_detection(self):
        """Verifies that 5m and 15m timeframe bar closes are correctly identified."""
        d = date(2025, 1, 9)
        minutes = list(SimulationClock.generate_session_minutes(d))

        # 09:15 bar: closes at 09:16 -> not 5m close (5m closes at 09:20, which is index 4 ending at 09:20)
        # 09:19 bar: ends at 09:20 -> elapsed 5 minutes -> is 5m close!
        bar_0919 = next(m for m in minutes if m.ist_time_str == "09:19")
        assert bar_0919.is_timeframe_close(5) is True

        bar_0920 = next(m for m in minutes if m.ist_time_str == "09:20")
        assert bar_0920.is_timeframe_close(5) is False

        # 09:29 bar: ends at 09:30 -> elapsed 15 minutes -> is 15m close!
        bar_0929 = next(m for m in minutes if m.ist_time_str == "09:29")
        assert bar_0929.is_timeframe_close(15) is True
