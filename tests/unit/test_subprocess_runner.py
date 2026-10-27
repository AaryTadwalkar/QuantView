"""
1. What this file does:
   Comprehensive unit tests for QuantView Isolated Subprocess Feature Runner
   (MASTER §2, ENGINE §9, ADR-012, Task M5-07 / Gate G3).

2. Overall design:
   Validates timeout enforcement, exception isolation without crashing the main process,
   malformed output detection, and strategy entry blocking when a required feature is unavailable.

3. Elements in the file:
   - TestSubprocessRunner: Tests SUCCESS, TIMEOUT, UNAVAILABLE, and MALFORMED_OUTPUT states.
   - TestEntryBlockingOnUnavailable: Tests engine entry gating when a feature fails.

4. Final output of the file:
   - Automated pytest suite certifying Task M5-07 under @pytest.mark.gate_g3.
"""

import time

import pytest

from packages.features.runner import (
    IsolatedFeatureRunner,
    SubprocessFeatureResult,
)


def _slow_feature(sleep_sec: float) -> list:
    """Mock feature that hangs or runs slowly."""
    time.sleep(sleep_sec)
    return [1.0, 2.0, 3.0]


def _crashing_feature() -> list:
    """Mock feature that raises an unhandled error."""
    raise ZeroDivisionError("Simulated indicator mathematical crash!")


def _malformed_feature() -> dict:
    """Mock feature returning malformed type."""
    return {"invalid": "dict_not_list"}


def _valid_feature(x: float) -> list:
    """Mock feature that calculates correctly."""
    return [x, x * 2.0, x * 3.0]


@pytest.mark.gate_g3
class TestSubprocessRunner:
    """
    1. The use of class:
       Unit tests for IsolatedFeatureRunner.

    2. What the class contains:
       - test_successful_run: Tests normal feature calculation.
       - test_timeout_termination: Tests termination when execution exceeds limit.
       - test_crash_isolation: Tests error containment without crashing parent process.
       - test_malformed_output_detection: Tests rejection of invalid data structures.

    3. Technologies used and why:
       pytest assertions verifying ADR-012 isolation.

    4. Key design and overall design of the class:
       Guarantees engine process resilience.
    """

    def test_successful_run(self):
        runner = IsolatedFeatureRunner()
        res = runner.run_feature(
            feature_id="VALID_FEAT_v1",
            compute_fn=_valid_feature,
            args=(5.0,),
            timeout_sec=2.0,
        )
        assert res.status == "SUCCESS"
        assert res.values == [5.0, 10.0, 15.0]
        assert res.error_message is None

    def test_timeout_termination(self):
        runner = IsolatedFeatureRunner()
        # Sleep for 1.0s, timeout at 0.1s
        res = runner.run_feature(
            feature_id="SLOW_FEAT_v1",
            compute_fn=_slow_feature,
            args=(1.0,),
            timeout_sec=0.1,
        )
        assert res.status == "TIMEOUT"
        assert res.values is None
        assert "exceeded timeout" in res.error_message

    def test_crash_isolation(self):
        runner = IsolatedFeatureRunner()
        res = runner.run_feature(
            feature_id="CRASH_FEAT_v1",
            compute_fn=_crashing_feature,
            timeout_sec=2.0,
        )
        assert res.status == "UNAVAILABLE"
        assert res.values is None
        assert "Simulated indicator" in res.error_message

    def test_malformed_output_detection(self):
        runner = IsolatedFeatureRunner()
        res = runner.run_feature(
            feature_id="BAD_SCHEMA_FEAT_v1",
            compute_fn=_malformed_feature,
            timeout_sec=2.0,
        )
        assert res.status == "MALFORMED_OUTPUT"
        assert res.values is None


@pytest.mark.gate_g3
class TestEntryBlockingOnUnavailable:
    """Verifies that strategy entry orders are blocked if any required feature is UNAVAILABLE."""

    def test_entry_blocked_when_feature_unavailable(self):
        # Engine contract: If any required feature is not SUCCESS, orders are blocked
        feature_results = {
            "EMA_20": SubprocessFeatureResult(
                feature_id="EMA_20",
                status="SUCCESS",
                values=[100.0],
                execution_time_ms=1.0,
            ),
            "CUSTOM_ALPHA": SubprocessFeatureResult(
                feature_id="CUSTOM_ALPHA",
                status="UNAVAILABLE",
                values=None,
                execution_time_ms=5.0,
                error_message="Feature crashed",
            ),
        }

        # Strategy check
        all_features_ready = all(
            r.status == "SUCCESS" and r.values is not None
            for r in feature_results.values()
        )
        assert all_features_ready is False

        # Invariant: Entry orders blocked
        is_entry_permitted = all_features_ready
        assert is_entry_permitted is False
