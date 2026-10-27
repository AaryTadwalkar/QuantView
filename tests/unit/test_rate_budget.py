"""
1. What this file does:
   Automated unit and contract test suite for Milestone M2-02 (Snapshot REST Budget and Priority).
   Verifies rate-budget enforcement, sliding window accounting, live snapshot quota reservation,
   market-hours backfill pausing, 429 cooldown feedback, and adapter integration per QUANTVIEW_DATA_SPEC §4.3, §11.3
   and Task M2-02.

2. Overall design:
   Uses Python standard unittest with deterministically controlled timestamps and mocks:
     - TestMarketHoursDetection: Tests exchange calendar hours logic in Asia/Kolkata timezone.
     - TestRateBudgetManager: Tests sliding window accounting, priority reservation, backfill pausing,
       and 429 cooldown dynamics.
     - TestAdapterBudgetIntegration: Tests that UpstoxSnapshotAdapter interacts correctly with RateBudgetManager.

3. Elements in the file:
   - TestMarketHoursDetection: Evaluates weekday and time boundaries for NSE market sessions.
   - TestRateBudgetManager: Evaluates token bucket, sliding windows, priority levels, and starvation prevention.
   - TestAdapterBudgetIntegration: Evaluates adapter acquisition and 429 notification callbacks.

4. Final output of the file:
   - Pass/fail test execution verifying all acceptance criteria of Milestone M2-02.
"""

import time
import unittest
import zoneinfo
from datetime import datetime, timezone
from datetime import time as dtime
from unittest.mock import MagicMock, patch

from packages.data.budget import (
    BudgetConfig,
    BudgetExhaustedError,
    RateBudgetManager,
    RequestPriority,
)
from services.collector_snapshot.adapter import UpstoxSnapshotAdapter

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


class TestMarketHoursDetection(unittest.TestCase):
    """
    1. The use of class:
       Unit tests for exchange session timing detection in Asia/Kolkata timezone.

    2. What the class contains:
       - test_regular_weekday_market_hours: Asserts True during 09:15-15:30 IST on Monday-Friday.
       - test_pre_market_and_post_market_hours: Asserts False before 09:15 and after 15:30 IST.
       - test_weekend_market_hours: Asserts False on Saturday and Sunday.

    3. Technologies used and why:
       zoneinfo.ZoneInfo and datetime for accurate timezone and calendar calculation.

    4. Key design and overall design of the class:
       Validates market schedule detection driving priority admission controls.
    """

    def setUp(self):
        """
        1. The use of function:
           Initializes RateBudgetManager for market schedule tests.

        2. How does the specific function work:
           Creates default RateBudgetManager.

        3. Concepts used in the function:
           Test setup.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: self.mgr available.
        """
        self.mgr = RateBudgetManager()

    def test_regular_weekday_market_hours(self):
        """
        1. The use of function:
           Verifies True during normal trading hours on a weekday.

        2. How does the specific function work:
           Tests Monday 10:30 IST (UTC 05:00).

        3. Concepts used in the function:
           Timezone conversion and range check.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Timestamp instant. After: Asserts True.
        """
        # Monday 2026-10-26 10:30:00 IST -> 05:00:00 UTC
        dt = datetime(2026, 10, 26, 5, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(self.mgr.is_market_hours(dt))

    def test_pre_market_and_post_market_hours(self):
        """
        1. The use of function:
           Verifies False during pre-market and post-market hours on weekdays.

        2. How does the specific function work:
           Tests 08:45 IST and 16:00 IST on Monday.

        3. Concepts used in the function:
           Boundary time check.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Timestamps outside session. After: Asserts False for both.
        """
        # Monday 2026-10-26 08:45:00 IST -> 03:15:00 UTC
        pre_market = datetime(2026, 10, 26, 3, 15, 0, tzinfo=timezone.utc)
        self.assertFalse(self.mgr.is_market_hours(pre_market))

        # Monday 2026-10-26 15:35:00 IST -> 10:05:00 UTC
        post_market = datetime(2026, 10, 26, 10, 5, 0, tzinfo=timezone.utc)
        self.assertFalse(self.mgr.is_market_hours(post_market))

    def test_weekend_market_hours(self):
        """
        1. The use of function:
           Verifies False on weekends regardless of time of day.

        2. How does the specific function work:
           Tests Saturday and Sunday at 11:00 IST.

        3. Concepts used in the function:
           Day-of-week validation.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Weekend timestamps. After: Asserts False.
        """
        # Saturday 2026-10-24 11:00:00 IST
        sat = datetime(2026, 10, 24, 5, 30, 0, tzinfo=timezone.utc)
        self.assertFalse(self.mgr.is_market_hours(sat))

        # Sunday 2026-10-25 11:00:00 IST
        sun = datetime(2026, 10, 25, 5, 30, 0, tzinfo=timezone.utc)
        self.assertFalse(self.mgr.is_market_hours(sun))


class TestRateBudgetManager(unittest.TestCase):
    """
    1. The use of class:
       Unit tests for RateBudgetManager sliding window quota, priority tiers, and backfill throttle.

    2. What the class contains:
       - setUp: Prepares custom BudgetConfig with testable limits.
       - test_high_priority_snapshot_reservation: Proves backfill yields when capacity drops to reserved quota.
       - test_off_market_backfill_full_capacity: Proves backfill can use full rate limit when market is closed.
       - test_utilization_threshold_throttles_backfill: Proves high minute utilization pauses backfill.
       - test_429_feedback_triggers_backfill_pause: Proves 429 notifications pause low-priority requests.
       - test_acquire_timeout_for_high_priority: Proves BudgetExhaustedError raised on persistent exhaustion.

    3. Technologies used and why:
       unittest and deterministic time offsets to simulate high load without slow sleeps.

    4. Key design and overall design of the class:
       Guarantees snapshot capacity reservation and verifies backfill yielding behavior.
    """

    def setUp(self):
        """
        1. The use of function:
           Sets up RateBudgetManager with deterministic test configuration.

        2. How does the specific function work:
           Creates BudgetConfig with total_rate_limit_per_sec=3.0, snapshot_reserved_per_sec=1.0,
           total_rate_limit_per_min=10.0, backfill_pause_utilization_pct=0.6.

        3. Concepts used in the function:
           Test fixture initialization.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Configured self.mgr and market session dt available.
        """
        self.config = BudgetConfig(
            total_rate_limit_per_sec=3.0,
            total_rate_limit_per_min=10.0,
            snapshot_reserved_per_sec=1.0,
            backfill_pause_utilization_pct=0.60,
            default_cooldown_429_sec=10.0,
        )
        self.mgr = RateBudgetManager(config=self.config)
        # Monday 10:00 IST (in market hours)
        self.market_dt = datetime(2026, 10, 26, 4, 30, 0, tzinfo=timezone.utc)
        # Sunday 10:00 IST (outside market hours)
        self.off_market_dt = datetime(2026, 10, 25, 4, 30, 0, tzinfo=timezone.utc)

    def test_high_priority_snapshot_reservation(self):
        """
        1. The use of function:
           Verifies that during market hours, backfill yields when available capacity <= reserved snapshot quota.

        2. How does the specific function work:
           Total limit = 3 req/sec, reserved = 1 req/sec.
           - At 0 recorded requests: both HIGH and LOW can acquire.
           - At 2 recorded requests: available = 1 req/sec. LOW returns False (yields), HIGH returns True.
           - At 3 recorded requests: available = 0 req/sec. Both HIGH and LOW return False.

        3. Concepts used in the function:
           Priority starvation prevention, reserved quota preservation.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Simulated requests. After: Proven reservation contract.
        """
        now = 1000.0

        # State 1: 0 requests recorded -> Both can acquire
        self.assertTrue(self.mgr.can_acquire(RequestPriority.HIGH, check_dt=self.market_dt, now_ts=now))
        self.assertTrue(self.mgr.can_acquire(RequestPriority.LOW, check_dt=self.market_dt, now_ts=now))

        # Record 1 request: remaining = 2 -> Both can acquire
        self.mgr.record_request(RequestPriority.LOW, now_ts=now)
        self.assertTrue(self.mgr.can_acquire(RequestPriority.HIGH, check_dt=self.market_dt, now_ts=now))
        self.assertTrue(self.mgr.can_acquire(RequestPriority.LOW, check_dt=self.market_dt, now_ts=now))

        # Record 2nd request: remaining = 1 (equal to reserved snapshot quota)
        self.mgr.record_request(RequestPriority.LOW, now_ts=now)
        # Invariant: LOW must yield, HIGH can still proceed!
        self.assertTrue(self.mgr.can_acquire(RequestPriority.HIGH, check_dt=self.market_dt, now_ts=now))
        self.assertFalse(self.mgr.can_acquire(RequestPriority.LOW, check_dt=self.market_dt, now_ts=now))
        self.assertFalse(self.mgr.can_backfill_proceed(check_dt=self.market_dt, now_ts=now))

        # Record 3rd request: remaining = 0 -> Hard cap reached, neither can acquire
        self.mgr.record_request(RequestPriority.HIGH, now_ts=now)
        self.assertFalse(self.mgr.can_acquire(RequestPriority.HIGH, check_dt=self.market_dt, now_ts=now))
        self.assertFalse(self.mgr.can_acquire(RequestPriority.LOW, check_dt=self.market_dt, now_ts=now))

    def test_off_market_backfill_full_capacity(self):
        """
        1. The use of function:
           Verifies that outside market hours, backfill can utilize full rate capacity without snapshot reservation.

        2. How does the specific function work:
           Total limit = 3 req/sec. Record 2 requests off-market. LOW can still acquire the 3rd request.

        3. Concepts used in the function:
           Dynamic quota relaxation outside exchange trading hours.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Off-market datetime. After: LOW can acquire all 3 slots.
        """
        now = 2000.0
        self.mgr.record_request(RequestPriority.LOW, now_ts=now)
        self.mgr.record_request(RequestPriority.LOW, now_ts=now)

        # Off-market: LOW can take the 3rd slot (remaining = 1 is allowed off-market)
        self.assertTrue(self.mgr.can_acquire(RequestPriority.LOW, check_dt=self.off_market_dt, now_ts=now))
        self.assertTrue(self.mgr.can_backfill_proceed(check_dt=self.off_market_dt, now_ts=now))

    def test_utilization_threshold_throttles_backfill(self):
        """
        1. The use of function:
           Verifies that backfill is throttled when rolling 60-second window utilization reaches threshold.

        2. How does the specific function work:
           Total 60s limit = 10, threshold = 60% (6 requests).
           Record 6 requests distributed across the minute (0 in the last second).
           Asserts LOW is throttled, but HIGH can still acquire.

        3. Concepts used in the function:
           Long-term window utilization monitoring.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: High minute load. After: LOW throttled, HIGH unaffected.
        """
        now = 3000.0
        # Spread 6 requests in the past 30 seconds (so 1-second window is 0)
        for i in range(6):
            self.mgr.record_request(RequestPriority.LOW, now_ts=now - 10.0 - i)

        status = self.mgr.get_status(check_dt=self.market_dt, now_ts=now)
        self.assertEqual(status["requests_last_60s"], 6)
        self.assertEqual(status["requests_last_1s"], 0)
        self.assertEqual(status["backfill_state"], "THROTTLED_HIGH_UTILIZATION")

        # Invariant: LOW is throttled due to minute utilization >= 60%
        self.assertFalse(self.mgr.can_acquire(RequestPriority.LOW, check_dt=self.market_dt, now_ts=now))
        # Invariant: HIGH is still permitted because 1s window is clear and total limit not hit
        self.assertTrue(self.mgr.can_acquire(RequestPriority.HIGH, check_dt=self.market_dt, now_ts=now))

    def test_429_feedback_triggers_backfill_pause(self):
        """
        1. The use of function:
           Verifies that HTTP 429 notifications immediately pause low-priority requests for cooldown period.

        2. How does the specific function work:
           Notifies 429 with 10.0s cooldown.
           Asserts LOW is rejected during cooldown and re-enabled once cooldown expires.

        3. Concepts used in the function:
           Adaptive backoff, closed-loop rate-protection.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: 429 event. After: LOW paused until cooldown time passes.
        """
        now = 4000.0
        self.mgr.notify_rate_limit_hit(retry_after_sec=10.0, now_ts=now)

        status = self.mgr.get_status(check_dt=self.market_dt, now_ts=now + 2.0)
        self.assertTrue(status["in_429_cooldown"])
        self.assertEqual(status["backfill_state"], "PAUSED_429_COOLDOWN")
        self.assertFalse(self.mgr.can_acquire(RequestPriority.LOW, check_dt=self.market_dt, now_ts=now + 2.0))

        # After 11 seconds, cooldown expires
        future_now = now + 11.0
        self.assertFalse(self.mgr.get_status(check_dt=self.market_dt, now_ts=future_now)["in_429_cooldown"])
        self.assertTrue(self.mgr.can_acquire(RequestPriority.LOW, check_dt=self.market_dt, now_ts=future_now))

    def test_acquire_timeout_for_high_priority(self):
        """
        1. The use of function:
           Verifies that acquire() raises BudgetExhaustedError when HIGH priority budget cannot be granted.

        2. How does the specific function work:
           Fills quota completely, calls acquire(priority=HIGH, timeout_sec=0.1).

        3. Concepts used in the function:
           Bounded blocking wait and exception signaling.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Saturated budget. After: BudgetExhaustedError raised after timeout.
        """
        # Exhaust 1s quota (3 requests) using real current timestamp
        now = time.time()
        for _ in range(3):
            self.mgr.record_request(RequestPriority.HIGH, now_ts=now)

        with self.assertRaises(BudgetExhaustedError):
            self.mgr.acquire(priority=RequestPriority.HIGH, timeout_sec=0.08)


class TestAdapterBudgetIntegration(unittest.TestCase):
    """
    1. The use of class:
       Unit tests verifying UpstoxSnapshotAdapter interacts with RateBudgetManager.

    2. What the class contains:
       - test_adapter_acquires_high_priority_budget: Verifies adapter calls acquire() with HIGH priority.
       - test_adapter_notifies_429_to_budget_manager: Verifies adapter calls notify_rate_limit_hit on 429.

    3. Technologies used and why:
       unittest.mock to assert integration contract without real network calls.

    4. Key design and overall design of the class:
       Ensures collector adapter coordinates with shared rate budget.
    """

    def test_adapter_acquires_high_priority_budget(self):
        """
        1. The use of function:
           Verifies adapter calls acquire(priority=HIGH) prior to executing HTTP GET.

        2. How does the specific function work:
           Injects mock budget_manager and mock session, executes fetch_raw_option_chain().

        3. Concepts used in the function:
           Mocking and method call assertion.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Unexecuted request. After: Mock budget_manager.acquire called with RequestPriority.HIGH.
        """
        mock_budget = MagicMock()
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status":"success"}'
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_session.get.return_value = mock_resp

        adapter = UpstoxSnapshotAdapter(
            access_token="tok",
            session=mock_session,
            budget_manager=mock_budget,
        )
        adapter.fetch_raw_option_chain("NSE_INDEX|Nifty 50")

        mock_budget.acquire.assert_called_once_with(priority=RequestPriority.HIGH)

    def test_adapter_notifies_429_to_budget_manager(self):
        """
        1. The use of function:
           Verifies adapter calls notify_rate_limit_hit on HTTP 429 response.

        2. How does the specific function work:
           Configures mock session to return 429 with Retry-After: 12 header, then 200 OK.
           Mocks time.sleep to run quickly.

        3. Concepts used in the function:
           Rate limit feedback loop verification.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: 429 HTTP response. After: mock_budget.notify_rate_limit_hit called with retry_after_sec=12.0.
        """
        mock_budget = MagicMock()
        mock_session = MagicMock()

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "12", "Content-Type": "application/json"}
        resp_429.content = b'{"error":"Rate limited"}'

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.headers = {"Content-Type": "application/json"}
        resp_200.content = b'{"status":"success"}'

        mock_session.get.side_effect = [resp_429, resp_200]

        with patch("time.sleep"):
            adapter = UpstoxSnapshotAdapter(
                access_token="tok",
                session=mock_session,
                budget_manager=mock_budget,
                max_retries=2,
            )
            adapter.fetch_raw_option_chain("NSE_INDEX|Nifty 50")

        mock_budget.notify_rate_limit_hit.assert_called_once_with(retry_after_sec=12.0)


if __name__ == "__main__":
    unittest.main()
