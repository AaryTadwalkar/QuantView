"""
1. What this file does:
   Comprehensive unit tests for QuantView Market Calendar, Intraday Session Progress,
   Regulatory Cutoff Countdowns, and Rolling High-Water Mark features.

2. Overall design:
   Validates point-in-time calculation of regular trading hours, 15:00 entry cutoff,
   15:25 force-flat cutoff, days to expiry (DTE), and clean multi-day session resets.

3. Elements in the file:
   - TestSessionProgress: Verifies exact minute counts, countdowns, and RTH status.
   - TestSessionHighWater: Verifies rolling high/low tracking and multi-day reset logic.
   - TestCalendarRegistry: Verifies feature registry integration.

4. Final output of the file:
   - Automated pytest suite certifying Phase 5D under @pytest.mark.gate_g3.
"""

from datetime import date, datetime, timezone
import pytest

from packages.features import FeatureRegistry
from packages.features.calendar import (
    SessionProgress,
    SessionHighWater,
    compute_session_progress,
    compute_session_high_water,
    parse_utc_to_ist,
    register_session_progress_feature,
    register_high_water_feature,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensures FeatureRegistry singleton is reset cleanly before and after each test."""
    FeatureRegistry._instance = None
    yield
    FeatureRegistry._instance = None


@pytest.mark.gate_g3
class TestSessionProgress:
    """
    1. The use of class:
       Unit tests for compute_session_progress.

    2. What the class contains:
       - test_session_progress_open_and_close: Checks 09:15, 15:00, 15:25, 15:30 IST.
       - test_session_progress_out_of_hours: Checks pre-market and post-market hours.
       - test_days_to_expiry_calculation: Checks DTE countdown to expiry date.

    3. Technologies used and why:
       pytest assertions on exact minute boundaries.

    4. Key design and overall design of the class:
       Guarantees timing rules align with RK-19, RK-20, and ENGINE §7.1.
    """

    def test_session_progress_open_and_close(self):
        # 2025-01-09 09:15:00 IST is 2025-01-09 03:45:00 UTC
        ts_open = int(datetime(2025, 1, 9, 3, 45, 0, tzinfo=timezone.utc).timestamp())
        res_open = compute_session_progress(ts_open)

        assert res_open.is_regular_trading_hours is True
        assert res_open.minutes_since_open == 0
        assert res_open.minutes_to_entry_cutoff == 345
        assert res_open.minutes_to_force_flat == 370
        assert res_open.session_fraction == 0.0
        assert res_open.day_of_week == 3  # Thursday

        # 2025-01-09 15:00:00 IST is 2025-01-09 09:30:00 UTC (15:00 Entry Cutoff)
        ts_cutoff = int(datetime(2025, 1, 9, 9, 30, 0, tzinfo=timezone.utc).timestamp())
        res_cutoff = compute_session_progress(ts_cutoff)

        assert res_cutoff.is_regular_trading_hours is True
        assert res_cutoff.minutes_since_open == 345
        assert res_cutoff.minutes_to_entry_cutoff == 0
        assert res_cutoff.minutes_to_force_flat == 25
        assert abs(res_cutoff.session_fraction - (345 / 375)) < 1e-5

        # 2025-01-09 15:25:00 IST is 2025-01-09 09:55:00 UTC (15:25 Force-Flat)
        ts_flat = int(datetime(2025, 1, 9, 9, 55, 0, tzinfo=timezone.utc).timestamp())
        res_flat = compute_session_progress(ts_flat)

        assert res_flat.is_regular_trading_hours is True
        assert res_flat.minutes_since_open == 370
        assert res_flat.minutes_to_entry_cutoff == 0
        assert res_flat.minutes_to_force_flat == 0

        # 2025-01-09 15:30:00 IST is 2025-01-09 10:00:00 UTC (Session Close)
        ts_close = int(datetime(2025, 1, 9, 10, 0, 0, tzinfo=timezone.utc).timestamp())
        res_close = compute_session_progress(ts_close)

        assert res_close.is_regular_trading_hours is True
        assert res_close.minutes_since_open == 375
        assert res_close.session_fraction == 1.0

    def test_session_progress_out_of_hours(self):
        # 2025-01-09 08:30:00 IST is 2025-01-09 03:00:00 UTC (Pre-market)
        ts_pre = int(datetime(2025, 1, 9, 3, 0, 0, tzinfo=timezone.utc).timestamp())
        res_pre = compute_session_progress(ts_pre)
        assert res_pre.is_regular_trading_hours is False

        # 2025-01-09 16:00:00 IST is 2025-01-09 10:30:00 UTC (Post-market)
        ts_post = int(datetime(2025, 1, 9, 10, 30, 0, tzinfo=timezone.utc).timestamp())
        res_post = compute_session_progress(ts_post)
        assert res_post.is_regular_trading_hours is False

    def test_days_to_expiry_calculation(self):
        # 2025-01-09 with expiry 2025-01-09 -> DTE = 0
        ts = int(datetime(2025, 1, 9, 4, 0, 0, tzinfo=timezone.utc).timestamp())
        res_0 = compute_session_progress(ts, expiry_date="2025-01-09")
        assert res_0.days_to_expiry == 0

        # 2025-01-09 with expiry 2025-01-16 -> DTE = 7
        res_7 = compute_session_progress(ts, expiry_date=date(2025, 1, 16))
        assert res_7.days_to_expiry == 7


@pytest.mark.gate_g3
class TestSessionHighWater:
    """
    1. The use of class:
       Unit tests for compute_session_high_water.

    2. What the class contains:
       - test_high_water_intraday_accumulation: Running max and min within a single session.
       - test_high_water_multi_session_reset: Daily reset of extremes across day boundaries.

    3. Technologies used and why:
       pytest assertions on running high/low tracking.

    4. Key design and overall design of the class:
       Guarantees daily boundary isolation without lookahead or backward contamination.
    """

    def test_high_water_intraday_accumulation(self):
        # Single day: 3 bars on 2025-01-09
        t0 = int(datetime(2025, 1, 9, 3, 45, 0, tzinfo=timezone.utc).timestamp())
        t1 = t0 + 60
        t2 = t1 + 60

        highs = [105.0, 108.0, 106.0]
        lows = [100.0, 102.0, 101.0]
        closes = [102.0, 107.0, 104.0]
        timestamps = [t0, t1, t2]

        results = compute_session_high_water(highs, lows, closes, timestamps)
        assert len(results) == 3

        # Bar 0
        assert results[0].is_session_start is True
        assert results[0].session_high == 105.0
        assert results[0].session_low == 100.0
        assert results[0].dist_to_high == 105.0 - 102.0  # 3.0
        assert results[0].dist_to_low == 102.0 - 100.0   # 2.0

        # Bar 1 (new high 108.0)
        assert results[1].is_session_start is False
        assert results[1].session_high == 108.0
        assert results[1].session_low == 100.0
        assert results[1].dist_to_high == 108.0 - 107.0  # 1.0
        assert results[1].dist_to_low == 107.0 - 100.0   # 7.0

        # Bar 2 (retains high 108.0)
        assert results[2].session_high == 108.0
        assert results[2].session_low == 100.0
        assert results[2].dist_to_high == 108.0 - 104.0  # 4.0
        assert results[2].dist_to_low == 104.0 - 100.0   # 4.0

    def test_high_water_multi_session_reset(self):
        # Day 1: 2025-01-09
        t_d1 = int(datetime(2025, 1, 9, 3, 45, 0, tzinfo=timezone.utc).timestamp())
        # Day 2: 2025-01-10
        t_d2 = int(datetime(2025, 1, 10, 3, 45, 0, tzinfo=timezone.utc).timestamp())

        highs = [150.0, 110.0]
        lows = [140.0, 90.0]
        closes = [145.0, 95.0]
        timestamps = [t_d1, t_d2]

        results = compute_session_high_water(highs, lows, closes, timestamps)
        assert len(results) == 2

        # Day 1
        assert results[0].session_date == "2025-01-09"
        assert results[0].session_high == 150.0
        assert results[0].session_low == 140.0

        # Day 2: Must reset cleanly to Day 2's bar, NOT carrying 150.0 high!
        assert results[1].is_session_start is True
        assert results[1].session_date == "2025-01-10"
        assert results[1].session_high == 110.0
        assert results[1].session_low == 90.0
        assert results[1].dist_to_high == 110.0 - 95.0  # 15.0


@pytest.mark.gate_g3
class TestCalendarRegistry:
    """Verifies that calendar features correctly register in FeatureRegistry."""

    def test_registry_integration(self):
        id_progress = register_session_progress_feature()
        assert id_progress.startswith("SESSION_PROGRESS_v1_")

        id_high_water = register_high_water_feature()
        assert id_high_water.startswith("SESSION_HIGH_WATER_v1_")

        registry = FeatureRegistry()
        assert registry.get(id_progress) is not None
        assert registry.get(id_high_water) is not None
