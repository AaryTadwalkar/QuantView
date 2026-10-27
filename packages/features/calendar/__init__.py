"""
1. What this file does:
   Package exports for QuantView market calendar, trading session, and high-water features.

2. Overall design:
   Re-exports session progress calculations, cutoff countdowns, and daily rolling session high/low tracking.

3. Elements in the file:
   - SessionProgress, compute_session_progress, register_session_progress_feature.
   - SessionHighWater, compute_session_high_water, register_high_water_feature.
   - parse_utc_to_ist, IST_TZ.

4. Final output of the file:
   - Clean public API for packages.features.calendar.
"""

from packages.features.calendar.session import (
    IST_OFFSET,
    IST_TZ,
    SessionProgress,
    compute_session_progress,
    parse_utc_to_ist,
    register_session_progress_feature,
)
from packages.features.calendar.high_water import (
    SessionHighWater,
    compute_session_high_water,
    register_high_water_feature,
)

__all__ = [
    "IST_OFFSET",
    "IST_TZ",
    "SessionProgress",
    "SessionHighWater",
    "parse_utc_to_ist",
    "compute_session_progress",
    "compute_session_high_water",
    "register_session_progress_feature",
    "register_high_water_feature",
]
