"""
1. What this file does:
   Implements the shared REST rate-limit budget and priority manager (RateBudgetManager).
   Enforces configurable REST quotas, prioritizes live market snapshots during market hours,
   and pauses/throttles historical backfills to prevent rate exhaustion per QUANTVIEW_DATA_SPEC §4.3, §11.3,
   QUANTVIEW_MASTER_SPEC §1, §10, and Task M2-02.

2. Overall design:
   Coordinates API request quotas across competing consumers (live collectors vs historical backfill):
     - Configurable request limits per second and per minute.
     - Guaranteed capacity reservation for high-priority live snapshot captures.
     - Market-hours detection (09:15 to 15:30 Asia/Kolkata, Monday through Friday).
     - Strict backfill yielding: historical backfill pauses or throttles during market hours
       whenever the measured remaining capacity is below the reserved snapshot threshold.
     - 429 feedback loop: enforces backoff cooldown and pauses low-priority tasks immediately.
     - Thread-safe sliding window tracking with microseconds precision.

3. Elements in the file:
   - RequestPriority: Enum defining HIGH (live snapshots) and LOW (historical backfill) priority tiers.
   - BudgetConfig: Dataclass parameterizing rate limits, reservations, and market timings.
   - RateBudgetManager: Thread-safe budget coordinator managing token reservation and pause states.
   - BudgetExhaustedError: Exception raised when budget acquisition fails within timeout.

4. Final output of the file:
   - Exported RequestPriority, BudgetConfig, RateBudgetManager, and BudgetExhaustedError classes.
"""

import threading
import time
import zoneinfo
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from datetime import time as dtime
from enum import Enum
from typing import Any, Dict, Optional

IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")


class RequestPriority(str, Enum):
    """
    1. The use of class:
       Enumeration of REST request priority levels.

    2. What the class contains:
       - HIGH: Live snapshot collectors (absolute priority during market hours).
       - LOW: Historical backfill processes (preemptible, throttled during market hours).

    3. Technologies used and why:
       Python string Enum for type safety and serialization.

    4. Key design and overall design of the class:
       Decouples request purpose from caller identity to enforce fair priority scheduling.
    """
    HIGH = "HIGH"
    LOW = "LOW"


class BudgetExhaustedError(RuntimeError):
    """
    1. The use of class:
       Exception raised when request budget is exhausted and cannot be granted within timeout.

    2. What the class contains:
       Standard Exception constructor with message and status details.

    3. Technologies used and why:
       Standard Python RuntimeError subclass.

    4. Key design and overall design of the class:
       Enables callers to catch budget exhaustion deterministically and yield.
    """
    pass


@dataclass
class BudgetConfig:
    """
    1. The use of class:
       Configuration parameters for REST rate budgets and priority scheduling.

    2. What the class contains:
       - total_rate_limit_per_sec: Maximum permitted requests in a rolling 1-second window.
       - total_rate_limit_per_min: Maximum permitted requests in a rolling 60-second window.
       - snapshot_reserved_per_sec: Minimum requests per second reserved strictly for HIGH priority.
       - market_open_ist: Opening time for regular NSE session (09:15:00).
       - market_close_ist: Closing time for regular NSE session (15:30:00).
       - backfill_pause_utilization_pct: Threshold of window utilization (e.g. 0.70) at which backfill pauses.
       - default_cooldown_429_sec: Duration in seconds to halt backfill upon receiving HTTP 429.

    3. Technologies used and why:
       Python dataclasses for strongly-typed, immutable configuration objects.

    4. Key design and overall design of the class:
       Centralizes rate limits and timing thresholds without hardcoding constants across services.
    """
    total_rate_limit_per_sec: float = 3.0
    total_rate_limit_per_min: float = 150.0
    snapshot_reserved_per_sec: float = 1.0
    market_open_ist: dtime = field(default_factory=lambda: dtime(9, 15, 0))
    market_close_ist: dtime = field(default_factory=lambda: dtime(15, 30, 0))
    backfill_pause_utilization_pct: float = 0.65
    default_cooldown_429_sec: float = 15.0


class RateBudgetManager:
    """
    1. The use of class:
       Thread-safe shared rate-limit budget and priority manager for REST endpoints.

    2. What the class contains:
       - config: BudgetConfig instance.
       - _lock: threading.Lock protecting sliding window deques and state flags.
       - _requests_1s: deque of UTC epoch timestamps for requests within last 1.0 second.
       - _requests_60s: deque of UTC epoch timestamps for requests within last 60.0 seconds.
       - _last_429_ts: UTC epoch timestamp of most recent 429 rate limit notification.
       - _cooldown_until_ts: UTC epoch timestamp until which low-priority requests are paused.

    3. Technologies used and why:
       threading.Lock for cross-thread synchronization, deque for efficient O(1) sliding window eviction.

    4. Key design and overall design of the class:
       Guarantees that high-priority market snapshots are never starved by backfill activity.
       During market hours, if available capacity drops to or below the reserved snapshot quota,
       backfill requests are forced to yield or block.
    """

    def __init__(self, config: Optional[BudgetConfig] = None) -> None:
        """
        1. The use of function:
           Initializes RateBudgetManager with configuration and thread locks.

        2. How does the specific function work:
           Sets up sliding window deques and thread safety primitives.

        3. Concepts used in the function:
           Sliding window rate limiting, synchronization.

        4. Places where this function is imported and used:
           Shared across services/collector_snapshot, services/backfill, and test harnesses.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Configured, empty budget manager ready for request dispatching.
        """
        self.config = config or BudgetConfig()
        self._lock = threading.Lock()
        self._requests_1s: deque = deque()
        self._requests_60s: deque = deque()
        self._last_429_ts: float = 0.0
        self._cooldown_until_ts: float = 0.0

    def is_market_hours(self, check_dt: Optional[datetime] = None) -> bool:
        """
        1. The use of function:
           Determines whether the given or current timestamp falls within active NSE trading hours.

        2. How does the specific function work:
           Converts input datetime (or UTC now) to Asia/Kolkata timezone, checks weekday (Monday-Friday),
           and asserts market_open_ist <= time < market_close_ist.

        3. Concepts used in the function:
           Timezone conversion (Asia/Kolkata), exchange schedule validation.

        4. Places where this function is imported and used:
           Used by can_acquire(), acquire(), and operational health checks.

        5. Final output of the function, before and after:
           Before: Timestamp instant. After: Boolean True if in market hours, False otherwise.
        """
        dt = check_dt or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ist_dt = dt.astimezone(IST_TZ)

        # NSE regular trading is Monday (0) to Friday (4)
        if ist_dt.weekday() >= 5:
            return False

        t = ist_dt.time()
        return self.config.market_open_ist <= t < self.config.market_close_ist

    def _purge_expired_entries(self, now: float) -> None:
        """
        1. The use of function:
           Evicts expired request timestamps from the 1-second and 60-second sliding windows.

        2. How does the specific function work:
           Pops elements from left of deques while entry < (now - window_size).

        3. Concepts used in the function:
           Sliding window eviction.

        4. Places where this function is imported and used:
           Called internally under _lock.

        5. Final output of the function, before and after:
           Before: Deques may contain stale timestamps. After: Deques contain strictly recent timestamps.
        """
        cutoff_1s = now - 1.0
        while self._requests_1s and self._requests_1s[0] <= cutoff_1s:
            self._requests_1s.popleft()

        cutoff_60s = now - 60.0
        while self._requests_60s and self._requests_60s[0] <= cutoff_60s:
            self._requests_60s.popleft()

    def can_acquire(
        self,
        priority: RequestPriority,
        check_dt: Optional[datetime] = None,
        now_ts: Optional[float] = None,
    ) -> bool:
        """
        1. The use of function:
           Checks non-blockingly whether a request of the specified priority can be executed immediately.

        2. How does the specific function work:
           - Purges expired entries from sliding windows.
           - Checks if current time is within 429 cooldown period (blocks LOW priority).
           - High priority: permitted if total 1s and 60s counts are within total limits.
           - Low priority: if market is open, asserts remaining capacity exceeds snapshot_reserved_per_sec
             and window utilization is below backfill_pause_utilization_pct.

        3. Concepts used in the function:
           Priority admission control, capacity reservation.

        4. Places where this function is imported and used:
           Called before dispatching HTTP calls or during backfill throttle loops.

        5. Final output of the function, before and after:
           Before: Unverified budget state. After: True if request can proceed, False if it must yield.
        """
        now = now_ts if now_ts is not None else time.time()
        with self._lock:
            self._purge_expired_entries(now)

            # If in 429 cooldown, LOW priority is strictly paused
            if priority == RequestPriority.LOW and now < self._cooldown_until_ts:
                return False

            count_1s = len(self._requests_1s)
            count_60s = len(self._requests_60s)

            # Hard cap check for any priority
            if count_1s >= self.config.total_rate_limit_per_sec:
                return False
            if count_60s >= self.config.total_rate_limit_per_min:
                return False

            # If HIGH priority, capacity exists
            if priority == RequestPriority.HIGH:
                return True

            # LOW Priority (Backfill) Admission Rules:
            market_active = self.is_market_hours(check_dt)
            if market_active:
                # 1. During market hours, preserve reserved snapshot quota
                available_1s = self.config.total_rate_limit_per_sec - count_1s
                if available_1s <= self.config.snapshot_reserved_per_sec:
                    return False

                # 2. Pause if 60-second window utilization exceeds pause threshold
                utilization_60s = count_60s / self.config.total_rate_limit_per_min
                if utilization_60s >= self.config.backfill_pause_utilization_pct:
                    return False

            return True

    def acquire(
        self,
        priority: RequestPriority = RequestPriority.HIGH,
        timeout_sec: float = 5.0,
        check_dt: Optional[datetime] = None,
    ) -> bool:
        """
        1. The use of function:
           Acquires budget capacity for a request, blocking if necessary until capacity is available.

        2. How does the specific function work:
           Polls can_acquire() in a tight sleep loop up to timeout_sec. On grant, records request and returns True.
           If timeout expires, raises BudgetExhaustedError for HIGH or returns False for LOW.

        3. Concepts used in the function:
           Bounded spin-wait with exponential backoff, priority reservation.

        4. Places where this function is imported and used:
           Invoked by UpstoxSnapshotAdapter and backfill workers prior to executing HTTP queries.

        5. Final output of the function, before and after:
           Before: Unreserved request. After: Capacity booked in sliding window, ready for HTTP send.
        """
        start_t = time.time()
        sleep_interval = 0.05

        while True:
            now_t = time.time()
            if self.can_acquire(priority=priority, check_dt=check_dt, now_ts=now_t):
                with self._lock:
                    self._requests_1s.append(now_t)
                    self._requests_60s.append(now_t)
                return True

            if (time.time() - start_t) >= timeout_sec:
                if priority == RequestPriority.HIGH:
                    raise BudgetExhaustedError(
                        f"Failed to acquire HIGH priority budget within {timeout_sec:.2f}s."
                    )
                return False

            time.sleep(sleep_interval)
            sleep_interval = min(sleep_interval * 1.5, 0.5)

    def record_request(self, priority: RequestPriority = RequestPriority.HIGH, now_ts: Optional[float] = None) -> None:
        """
        1. The use of function:
           Explicitly records an externally executed request into the rate budget counters.

        2. How does the specific function work:
           Appends timestamp to both 1-second and 60-second deques under thread lock.

        3. Concepts used in the function:
           Manual accounting, external telemetry integration.

        4. Places where this function is imported and used:
           Used when requests are executed by external HTTP clients that report completions.

        5. Final output of the function, before and after:
           Before: Counter unchanged. After: Request timestamp tracked in sliding windows.
        """
        now = now_ts if now_ts is not None else time.time()
        with self._lock:
            self._purge_expired_entries(now)
            self._requests_1s.append(now)
            self._requests_60s.append(now)

    def notify_rate_limit_hit(
        self,
        retry_after_sec: Optional[float] = None,
        now_ts: Optional[float] = None,
    ) -> None:
        """
        1. The use of function:
           Notifies the budget manager of an HTTP 429 response, pausing low-priority workloads.

        2. How does the specific function work:
           Records 429 occurrence timestamp and sets cooldown timestamp until which LOW priority is halted.

        3. Concepts used in the function:
           Feedback control, adaptive backoff, upstream rate-protection.

        4. Places where this function is imported and used:
           Invoked by UpstoxSnapshotAdapter when HTTP 429 response is encountered.

        5. Final output of the function, before and after:
           Before: Standard operation. After: Low-priority backfills paused for cooldown period.
        """
        now = now_ts if now_ts is not None else time.time()
        cooldown = retry_after_sec if retry_after_sec is not None else self.config.default_cooldown_429_sec
        with self._lock:
            self._last_429_ts = now
            self._cooldown_until_ts = max(self._cooldown_until_ts, now + cooldown)

    def can_backfill_proceed(
        self,
        check_dt: Optional[datetime] = None,
        now_ts: Optional[float] = None,
    ) -> bool:
        """
        1. The use of function:
           Convenience predicate for backfill workers to check if execution is safe.

        2. How does the specific function work:
           Calls can_acquire(RequestPriority.LOW, check_dt=check_dt, now_ts=now_ts).

        3. Concepts used in the function:
           Interface simplification, polling check.

        4. Places where this function is imported and used:
           services/backfill workers and batch ingest tools.

        5. Final output of the function, before and after:
           Before: Unknown state. After: Boolean True if backfill can query, False if it must pause.
        """
        return self.can_acquire(priority=RequestPriority.LOW, check_dt=check_dt, now_ts=now_ts)

    def get_status(self, check_dt: Optional[datetime] = None, now_ts: Optional[float] = None) -> Dict[str, Any]:
        """
        1. The use of function:
           Returns an observable status snapshot of rate limits, consumption, and priority state.

        2. How does the specific function work:
           Inspects deques, calculates remaining capacity, checks market hours and 429 cooldown status.

        3. Concepts used in the function:
           Observability, real-time health telemetry.

        4. Places where this function is imported and used:
           Called by health checks, telemetry endpoints, and test suites.

        5. Final output of the function, before and after:
           Before: Unmeasured metrics. After: Structured dictionary detailing budget consumption.
        """
        now = now_ts if now_ts is not None else time.time()
        with self._lock:
            self._purge_expired_entries(now)
            count_1s = len(self._requests_1s)
            count_60s = len(self._requests_60s)
            in_cooldown = now < self._cooldown_until_ts
            cooldown_remaining = max(0.0, self._cooldown_until_ts - now)

        market_active = self.is_market_hours(check_dt)
        available_1s = max(0.0, self.config.total_rate_limit_per_sec - count_1s)
        available_60s = max(0.0, self.config.total_rate_limit_per_min - count_60s)

        if in_cooldown:
            backfill_state = "PAUSED_429_COOLDOWN"
        elif market_active:
            if available_1s <= self.config.snapshot_reserved_per_sec:
                backfill_state = "YIELDING_SNAPSHOT_RESERVATION"
            elif (count_60s / self.config.total_rate_limit_per_min) >= self.config.backfill_pause_utilization_pct:
                backfill_state = "THROTTLED_HIGH_UTILIZATION"
            else:
                backfill_state = "ACTIVE_WITH_RESERVATION"
        else:
            backfill_state = "ACTIVE_OFF_MARKET"

        return {
            "market_hours_active": market_active,
            "requests_last_1s": count_1s,
            "requests_last_60s": count_60s,
            "available_capacity_1s": available_1s,
            "available_capacity_60s": available_60s,
            "snapshot_reserved_quota_1s": self.config.snapshot_reserved_per_sec,
            "backfill_state": backfill_state,
            "in_429_cooldown": in_cooldown,
            "cooldown_remaining_sec": round(cooldown_remaining, 2),
        }
