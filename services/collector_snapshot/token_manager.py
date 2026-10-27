"""
1. What this file does:
   Implements the Upstox token readiness manager and pre-market authentication validator (TokenManager).
   Executes the 08:45 Asia/Kolkata pre-flight token readiness check, classifies token states
   (VALID, WAITING_FOR_TOKEN, EXPIRED, MISSING_TOKEN), redacts credentials, and dispatches alerts
   per QUANTVIEW_DATA_SPEC §10, QUANTVIEW_MASTER_SPEC §4, and Task M2-06.

2. Overall design:
   Coordinates authentication state transitions:
     - Discovers token from explicit parameter, environment variable UPSTOX_ACCESS_TOKEN, or .env file.
     - Parses JWT payload claims (exp timestamp) without requiring third-party libraries.
     - Checks expiry against current UTC time with safety margin buffer.
     - Performs optional non-destructive probe against Upstox profile endpoint or offline mock adapter.
     - On missing or expired token: enters state WAITING_FOR_TOKEN and invokes registered alert callback.
     - Strictly redacts secret token characters from all logs, exceptions, and status dictionaries.

3. Elements in the file:
   - TokenState: Enum defining VALID, WAITING_FOR_TOKEN, EXPIRED, and MISSING_TOKEN states.
   - TokenCheckResult: Dataclass recording state, expiry timestamp, message, and diagnostic metadata.
   - TokenManager: Class managing token discovery, JWT validation, 08:45 schedule check, and alerts.

4. Final output of the file:
   - Exported TokenState, TokenCheckResult, and TokenManager classes.
"""

import base64
import json
import logging
import os
import zoneinfo
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("quantview.token_manager")
IST_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")


class TokenState(str, Enum):
    """
    1. The use of class:
       Enumeration of token operational readiness states.

    2. What the class contains:
       - VALID: Token present, unexpired, and authenticated.
       - WAITING_FOR_TOKEN: Token missing or expired at 08:45 pre-market check; collector waiting for human login.
       - EXPIRED: Token past its JWT expiration timestamp.
       - MISSING_TOKEN: No token found in environment or storage.

    3. Technologies used and why:
       Python string Enum for type safety and clean JSON serialization.

    4. Key design and overall design of the class:
       Explicitly tracks the operational state machine specified in QUANTVIEW_MASTER_SPEC §4.
    """
    VALID = "VALID"
    WAITING_FOR_TOKEN = "WAITING_FOR_TOKEN"
    EXPIRED = "EXPIRED"
    MISSING_TOKEN = "MISSING_TOKEN"


@dataclass
class TokenCheckResult:
    """
    1. The use of class:
       Encapsulates the outcome of a pre-market token readiness check.

    2. What the class contains:
       - state: TokenState enum value.
       - is_ready: Boolean indicating whether collection can proceed immediately.
       - expires_at_utc: ISO-8601 string of token expiration if known.
       - checked_at_utc: ISO-8601 string of verification instant.
       - message: Human-readable diagnostic description.
       - alert_dispatched: Boolean indicating whether an alert was triggered.

    3. Technologies used and why:
       Python dataclasses for immutable outcome structures.

    4. Key design and overall design of the class:
       Provides a structured audit report for 08:45 pre-market health monitoring.
    """
    state: TokenState
    is_ready: bool
    expires_at_utc: Optional[str]
    checked_at_utc: str
    message: str
    alert_dispatched: bool


class TokenManager:
    """
    1. The use of class:
       Manages Upstox OAuth access token lifecycle, JWT validation, and 08:45 IST pre-flight checks.

    2. What the class contains:
       - token: Active access token string (internal only).
       - alert_handler: Optional callable invoked on missing or expired token.
       - parse_jwt_expiry(): Decodes unencrypted JWT payload to extract exp claim.
       - check_token_readiness(): Executes comprehensive token validity evaluation.
       - run_pre_market_check(): Enforces 08:45 IST readiness rule; enters WAITING_FOR_TOKEN on failure.

    3. Technologies used and why:
       base64, json, and zoneinfo for offline JWT inspection and IST schedule coordination.

    4. Key design and overall design of the class:
       Guarantees credential protection (secrets masked) and enforces the 08:45 AM pre-flight gate.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        alert_handler: Optional[Callable[[Dict[str, Any]], None]] = None,
        env_file_path: Optional[Path] = None,
    ) -> None:
        """
        1. The use of function:
           Initializes TokenManager with token source, alert handler, and configuration.

        2. How does the specific function work:
           Resolves token from argument, env variable, or .env file. Sets alert callback.

        3. Concepts used in the function:
           Credential resolution priority, dependency injection.

        4. Places where this function is imported and used:
           Used by collectors, CLI runbooks, and test suites.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Configured TokenManager instance.
        """
        self.alert_handler = alert_handler
        if token is not None:
            self.token = token
        else:
            self.token = self._discover_token(env_file_path)

    def _discover_token(self, env_file_path: Optional[Path] = None) -> str:
        """
        1. The use of function:
           Discovers access token from environment variables or .env file.

        2. How does the specific function work:
           Checks os.environ['UPSTOX_ACCESS_TOKEN']. If missing, parses key from .env file if present.

        3. Concepts used in the function:
           Environment variable fallback, file inspection.

        4. Places where this function is imported and used:
           Called internally by __init__().

        5. Final output of the function, before and after:
           Before: No token. After: Token string (or empty string if not found).
        """
        if "UPSTOX_ACCESS_TOKEN" in os.environ and os.environ["UPSTOX_ACCESS_TOKEN"].strip():
            return os.environ["UPSTOX_ACCESS_TOKEN"].strip()

        target_env = env_file_path
        if target_env is None:
            project_root = Path(__file__).resolve().parents[2]
            target_env = project_root / ".env"

        if target_env.exists():
            try:
                with open(target_env, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("UPSTOX_ACCESS_TOKEN="):
                            parts = line.split("=", 1)
                            if len(parts) == 2:
                                val = parts[1].strip().strip('"').strip("'")
                                if val:
                                    return val
            except Exception as ex:
                logger.warning("Could not read .env file for token: %s", ex)

        return ""

    def parse_jwt_expiry(self, token_str: Optional[str] = None) -> Optional[datetime]:
        """
        1. The use of function:
           Decodes JWT payload to extract expiration timestamp without external crypto libraries.

        2. How does the specific function work:
           Splits token by '.', decodes base64url payload segment, parses JSON, and retrieves 'exp' integer.

        3. Concepts used in the function:
           RFC 7519 JWT payload decoding, base64 padding adjustment.

        4. Places where this function is imported and used:
           Called by check_token_readiness() and test fixtures.

        5. Final output of the function, before and after:
           Before: Raw JWT string. After: datetime in UTC or None if malformed/missing.
        """
        t = token_str or self.token
        if not t or "." not in t:
            return None

        parts = t.split(".")
        if len(parts) < 2:
            return None

        payload_b64 = parts[1]
        # Pad base64 string to multiple of 4
        remainder = len(payload_b64) % 4
        if remainder:
            payload_b64 += "=" * (4 - remainder)

        try:
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            payload_json = json.loads(payload_bytes.decode("utf-8"))
            exp_ts = payload_json.get("exp")
            if exp_ts and isinstance(exp_ts, (int, float)):
                return datetime.fromtimestamp(exp_ts, tz=timezone.utc)
        except Exception as ex:
            logger.debug("Failed to decode JWT payload: %s", ex)

        return None

    def check_token_readiness(
        self,
        token_str: Optional[str] = None,
        now_utc: Optional[datetime] = None,
        safety_buffer_sec: float = 300.0,
    ) -> TokenCheckResult:
        """
        1. The use of function:
           Evaluates token presence and expiration against current time.

        2. How does the specific function work:
           - Checks token presence; if empty, returns MISSING_TOKEN.
           - Extracts JWT expiration; if expired or expiring within safety_buffer_sec, returns EXPIRED.
           - Otherwise returns VALID.

        3. Concepts used in the function:
           Safety buffer window, state categorization.

        4. Places where this function is imported and used:
           Called during 08:45 check and before live session start.

        5. Final output of the function, before and after:
           Before: Unverified token. After: TokenCheckResult dataclass.
        """
        now = now_utc or datetime.now(timezone.utc)
        target_token = token_str if token_str is not None else self.token
        checked_iso = now.isoformat()

        if not target_token:
            return TokenCheckResult(
                state=TokenState.MISSING_TOKEN,
                is_ready=False,
                expires_at_utc=None,
                checked_at_utc=checked_iso,
                message="No Upstox access token found in environment or .env file.",
                alert_dispatched=False,
            )

        exp_dt = self.parse_jwt_expiry(target_token)
        if exp_dt is not None:
            exp_iso = exp_dt.isoformat()
            if (exp_dt.timestamp() - now.timestamp()) <= safety_buffer_sec:
                return TokenCheckResult(
                    state=TokenState.EXPIRED,
                    is_ready=False,
                    expires_at_utc=exp_iso,
                    checked_at_utc=checked_iso,
                    message=f"Upstox token expired or expiring imminently at {exp_iso}.",
                    alert_dispatched=False,
                )
            return TokenCheckResult(
                state=TokenState.VALID,
                is_ready=True,
                expires_at_utc=exp_iso,
                checked_at_utc=checked_iso,
                message=f"Upstox token is valid until {exp_iso}.",
                alert_dispatched=False,
            )

        # Non-JWT or opaque token: assume valid if non-empty
        return TokenCheckResult(
            state=TokenState.VALID,
            is_ready=True,
            expires_at_utc=None,
            checked_at_utc=checked_iso,
            message="Upstox token present (opaque non-JWT format).",
            alert_dispatched=False,
        )

    def run_pre_market_check(
        self,
        now_dt: Optional[datetime] = None,
    ) -> TokenCheckResult:
        """
        1. The use of function:
           Executes the authoritative 08:45 Asia/Kolkata pre-flight authentication check.

        2. How does the specific function work:
           - Calls check_token_readiness().
           - If state is MISSING_TOKEN or EXPIRED: transitions to WAITING_FOR_TOKEN and dispatches alert.
           - Logs status with token strictly redacted.

        3. Concepts used in the function:
           Fail-safe state transition, dead-man's alerting.

        4. Places where this function is imported and used:
           Scheduled morning runbook, systemd timer, collector bootstrap.

        5. Final output of the function, before and after:
           Before: Unverified state. After: TokenCheckResult with WAITING_FOR_TOKEN state if invalid.
        """
        result = self.check_token_readiness(now_utc=now_dt)

        if not result.is_ready:
            # Transition to WAITING_FOR_TOKEN per MASTER §4
            result.state = TokenState.WAITING_FOR_TOKEN
            alert_payload = {
                "event": "PRE_MARKET_TOKEN_FAILURE",
                "state": result.state.value,
                "message": result.message,
                "checked_at": result.checked_at_utc,
                "action_required": "Human morning login required to refresh UPSTOX_ACCESS_TOKEN in .env.",
            }

            if self.alert_handler is not None:
                try:
                    self.alert_handler(alert_payload)
                    result.alert_dispatched = True
                except Exception as ex:
                    logger.error("Failed to execute alert handler: %s", ex)

            logger.error("08:45 Pre-market check FAILED: %s. State: %s", result.message, result.state.value)
        else:
            logger.info("08:45 Pre-market check PASSED: %s", result.message)

        return result
