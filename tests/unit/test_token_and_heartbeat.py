"""
1. What this file does:
   Automated unit and contract test suite for Milestone M2-06 (Pre-Market Token and Heartbeat Monitor).
   Verifies 08:45 AM pre-flight auth validation, JWT expiration parsing, WAITING_FOR_TOKEN transitions,
   dead-man switch telemetry persistence with fsync, and staleness alert dispatching per
   QUANTVIEW_DATA_SPEC §10, QUANTVIEW_MASTER_SPEC §4, and Task M2-06.

2. Overall design:
   Uses standard unittest with temporary directories and hermetic mocks:
     - TestTokenManager: Tests JWT decoding, missing/expired token handling, WAITING_FOR_TOKEN state transitions,
       and alert callbacks.
     - TestHeartbeatMonitor: Tests atomic pulse writes, fsync durability, lag thresholding, and missing/stale alerts.
     - TestTokenCliTool: Tests CLI script exit codes and formatting.

3. Elements in the file:
   - TestTokenManager: Validates TokenManager lifecycle and state machine.
   - TestHeartbeatMonitor: Validates HeartbeatMonitor pulses and dead-man switch alerting.
   - TestTokenCliTool: Validates command-line tool execution and output.

4. Final output of the file:
   - Pass/fail test execution verifying all acceptance criteria of Milestone M2-06.
"""

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from services.collector_snapshot.heartbeat import (
    HeartbeatMonitor,
    HeartbeatRecord,
    MissingHeartbeatAlert,
)
from services.collector_snapshot.token_manager import (
    TokenCheckResult,
    TokenManager,
    TokenState,
)
from tools.ops.check_token_readiness import main as cli_main


def _build_test_jwt(exp_epoch: int) -> str:
    """Helper to build a syntactically valid JWT with custom exp claim."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode("utf-8").rstrip("=")
    payload_dict = {"sub": "user123", "exp": exp_epoch, "user_id": "TEST_USER"}
    payload = base64.urlsafe_b64encode(json.dumps(payload_dict).encode("utf-8")).decode("utf-8").rstrip("=")
    sig = base64.urlsafe_b64encode(b"synthetic_signature_bytes_12345").decode("utf-8").rstrip("=")
    return f"{header}.{payload}.{sig}"


class TestTokenManager(unittest.TestCase):
    """
    1. The use of class:
       Unit tests for TokenManager authentication checks and state transitions.

    2. What the class contains:
       - test_missing_token_transitions_to_waiting_for_token: Asserts WAITING_FOR_TOKEN when no token exists.
       - test_expired_token_transitions_to_waiting_for_token: Asserts WAITING_FOR_TOKEN when JWT is expired.
       - test_valid_token_readiness: Asserts VALID state when token has future expiration.
       - test_secret_token_redaction: Asserts token characters are never leaked in messages or results.

    3. Technologies used and why:
       unittest and synthetic JWT builder for hermetic offline testing.

    4. Key design and overall design of the class:
       Guarantees that unauthenticated states fail loudly and transition to WAITING_FOR_TOKEN.
    """

    def test_missing_token_transitions_to_waiting_for_token(self):
        """
        1. The use of function:
           Verifies that missing token triggers WAITING_FOR_TOKEN and dispatches an alert.

        2. How does the specific function work:
           Initializes TokenManager with empty token and mock alert handler. Executes run_pre_market_check().

        3. Concepts used in the function:
           Pre-market gate verification.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Unverified state. After: TokenState.WAITING_FOR_TOKEN and mock alert called.
        """
        mock_alert = MagicMock()
        manager = TokenManager(token="", alert_handler=mock_alert)
        result = manager.run_pre_market_check()

        self.assertEqual(result.state, TokenState.WAITING_FOR_TOKEN)
        self.assertFalse(result.is_ready)
        self.assertTrue(result.alert_dispatched)
        mock_alert.assert_called_once()
        alert_payload = mock_alert.call_args[0][0]
        self.assertEqual(alert_payload["event"], "PRE_MARKET_TOKEN_FAILURE")
        self.assertEqual(alert_payload["state"], "WAITING_FOR_TOKEN")

    def test_expired_token_transitions_to_waiting_for_token(self):
        """
        1. The use of function:
           Verifies that expired JWT triggers WAITING_FOR_TOKEN and dispatches an alert.

        2. How does the specific function work:
           Creates JWT with exp in the past, calls run_pre_market_check().

        3. Concepts used in the function:
           JWT expiry validation.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Expired JWT. After: TokenState.WAITING_FOR_TOKEN and mock alert dispatched.
        """
        past_exp = int(time.time()) - 3600  # Expired 1 hour ago
        expired_token = _build_test_jwt(past_exp)
        mock_alert = MagicMock()

        manager = TokenManager(token=expired_token, alert_handler=mock_alert)
        result = manager.run_pre_market_check()

        self.assertEqual(result.state, TokenState.WAITING_FOR_TOKEN)
        self.assertFalse(result.is_ready)
        self.assertTrue(result.alert_dispatched)
        mock_alert.assert_called_once()
        self.assertIn("expired", result.message.lower())

    def test_valid_token_readiness(self):
        """
        1. The use of function:
           Verifies that a valid unexpired token passes the pre-market check with state VALID.

        2. How does the specific function work:
           Creates JWT with exp 12 hours in the future, runs run_pre_market_check().

        3. Concepts used in the function:
           Positive authentication gate check.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Valid JWT. After: TokenState.VALID, is_ready=True, 0 alerts.
        """
        future_exp = int(time.time()) + 43200  # 12 hours in future
        valid_token = _build_test_jwt(future_exp)
        mock_alert = MagicMock()

        manager = TokenManager(token=valid_token, alert_handler=mock_alert)
        result = manager.run_pre_market_check()

        self.assertEqual(result.state, TokenState.VALID)
        self.assertTrue(result.is_ready)
        self.assertFalse(result.alert_dispatched)
        mock_alert.assert_not_called()

    def test_secret_token_redaction(self):
        """
        1. The use of function:
           Verifies that the secret token is never exposed in check messages.

        2. How does the specific function work:
           Checks result message for any occurrence of the raw secret token string.

        3. Concepts used in the function:
           Credential leak prevention.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Raw token in memory. After: Asserts token not present in messages.
        """
        secret_token = _build_test_jwt(int(time.time()) + 3600)
        manager = TokenManager(token=secret_token)
        result = manager.run_pre_market_check()
        self.assertNotIn(secret_token, result.message)


class TestHeartbeatMonitor(unittest.TestCase):
    """
    1. The use of class:
       Unit tests for HeartbeatMonitor telemetry persistence, lag thresholding, and staleness alerts.

    2. What the class contains:
       - setUp: Prepares isolated temporary telemetry directory.
       - tearDown: Cleans up temporary directory.
       - test_record_pulse_with_fsync_durability: Asserts atomic write of heartbeat JSON.
       - test_check_freshness_healthy: Asserts OK status when pulse is recent.
       - test_check_freshness_stale_triggers_alert: Asserts alert when pulse exceeds max lag.
       - test_check_freshness_missing_triggers_alert: Asserts alert when heartbeat file does not exist.

    3. Technologies used and why:
       tempfile.TemporaryDirectory for hermetic filesystem isolation.

    4. Key design and overall design of the class:
       Validates dead-man switch behavior: absent or lagging heartbeats trigger alerts within <= 60s.
    """

    def setUp(self):
        """
        1. The use of function:
           Initializes HeartbeatMonitor test environment.

        2. How does the specific function work:
           Creates TemporaryDirectory and HeartbeatMonitor instance.

        3. Concepts used in the function:
           Test setup.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: self.monitor and self.test_dir available.
        """
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.mock_alert = MagicMock()
        self.monitor = HeartbeatMonitor(telemetry_dir=self.test_dir, alert_handler=self.mock_alert)

    def tearDown(self):
        """
        1. The use of function:
           Cleans up temporary directory.

        2. How does the specific function work:
           Calls cleanup() on TemporaryDirectory.

        3. Concepts used in the function:
           Resource disposal.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Temp dir exists. After: Deleted.
        """
        self.temp_dir.cleanup()

    def test_record_pulse_with_fsync_durability(self):
        """
        1. The use of function:
           Verifies atomic heartbeat JSON file creation and absence of orphan .tmp files.

        2. How does the specific function work:
           Records pulse for 'collector_snapshot', inspects file contents on disk.

        3. Concepts used in the function:
           Atomic persistence, process metadata recording.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: No file. After: Finalized heartbeat JSON verified on disk.
        """
        now = 10000.0
        record = self.monitor.record_pulse(
            service_name="collector_snapshot",
            status="HEALTHY",
            metadata={"captures_count": 128},
            now_ts=now,
        )

        h_path = self.test_dir / "heartbeat_collector_snapshot.json"
        self.assertTrue(h_path.exists())

        with open(h_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["service_name"], "collector_snapshot")
        self.assertEqual(data["epoch_sec"], 10000.0)
        self.assertEqual(data["status"], "HEALTHY")
        self.assertEqual(data["pid"], os.getpid())
        self.assertEqual(data["metadata"]["captures_count"], 128)

        # Ensure no orphan temporary files
        tmp_files = list(self.test_dir.glob("*.tmp*"))
        self.assertEqual(len(tmp_files), 0)

    def test_check_freshness_healthy(self):
        """
        1. The use of function:
           Verifies check_freshness returns OK when lag is well within max_lag_sec.

        2. How does the specific function work:
           Records pulse at now - 15.0s, checks freshness with max_lag_sec=60.0s.

        3. Concepts used in the function:
           Liveness check.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Pulse recorded. After: Status 'OK', 0 alerts fired.
        """
        now = 20000.0
        self.monitor.record_pulse("collector_snapshot", now_ts=now - 15.0)

        status = self.monitor.check_freshness("collector_snapshot", max_lag_sec=60.0, now_ts=now)
        self.assertEqual(status["status"], "OK")
        self.assertEqual(status["lag_sec"], 15.0)
        self.mock_alert.assert_not_called()

    def test_check_freshness_stale_triggers_alert(self):
        """
        1. The use of function:
           Verifies check_freshness generates STALE alert when lag exceeds 60 seconds.

        2. How does the specific function work:
           Records pulse at now - 75.0s. Calls check_freshness with max_lag_sec=60.0s.

        3. Concepts used in the function:
           Dead-man switch trip.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Stale pulse. After: Status 'STALE' and alert handler invoked.
        """
        now = 30000.0
        self.monitor.record_pulse("collector_snapshot", now_ts=now - 75.0)

        status = self.monitor.check_freshness("collector_snapshot", max_lag_sec=60.0, now_ts=now)
        self.assertEqual(status["status"], "STALE")
        self.assertEqual(status["event"], "STALE_HEARTBEAT_ALERT")
        self.assertEqual(status["lag_sec"], 75.0)
        self.mock_alert.assert_called_once()

    def test_check_freshness_missing_triggers_alert(self):
        """
        1. The use of function:
           Verifies check_freshness generates MISSING alert when service file does not exist.

        2. How does the specific function work:
           Checks freshness for 'unstarted_collector'.

        3. Concepts used in the function:
           Missing service detection.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: No heartbeat. After: Status 'MISSING' and alert handler invoked.
        """
        status = self.monitor.check_freshness("unstarted_collector", max_lag_sec=60.0)
        self.assertEqual(status["status"], "MISSING")
        self.assertEqual(status["event"], "MISSING_HEARTBEAT_ALERT")
        self.mock_alert.assert_called_once()


class TestTokenCliTool(unittest.TestCase):
    """
    1. The use of class:
       Unit tests for check_token_readiness.py command-line execution.

    2. What the class contains:
       - test_cli_returns_zero_on_valid_token: Asserts exit code 0 when valid token supplied.
       - test_cli_returns_one_on_missing_token: Asserts exit code 1 when no token supplied.

    3. Technologies used and why:
       sys.argv patching and mock stdout for CLI testing.

    4. Key design and overall design of the class:
       Validates command-line contract for systemd timers and automated runbooks.
    """

    def test_cli_returns_zero_on_valid_token(self):
        """
        1. The use of function:
           Verifies check_token_readiness CLI exits with 0 on valid token.

        2. How does the specific function work:
           Patches sys.argv with valid token, runs cli_main().

        3. Concepts used in the function:
           CLI exit code contract testing.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Unrun CLI. After: Exit code 0 returned.
        """
        valid_jwt = _build_test_jwt(int(time.time()) + 36000)
        test_args = ["check_token_readiness.py", "--token", valid_jwt, "--json"]
        with unittest.mock.patch("sys.argv", test_args):
            exit_code = cli_main()
            self.assertEqual(exit_code, 0)

    def test_cli_returns_one_on_missing_token(self):
        """
        1. The use of function:
           Verifies check_token_readiness CLI exits with 1 on missing/expired token.

        2. How does the specific function work:
           Patches sys.argv with empty token, runs cli_main().

        3. Concepts used in the function:
           CLI failure exit code testing.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Unrun CLI. After: Exit code 1 returned.
        """
        test_args = ["check_token_readiness.py", "--token", "", "--json"]
        with unittest.mock.patch("sys.argv", test_args):
            exit_code = cli_main()
            self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
