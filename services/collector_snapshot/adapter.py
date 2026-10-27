"""
1. What this file does:
   Implements the Upstox REST option chain snapshot adapter (UpstoxSnapshotAdapter).
   Executes resilient HTTP requests with exponential backoff, jitter, secret redaction,
   and deterministic offline mock support per QUANTVIEW_DATA_SPEC §4.3 and Task M2-01.

2. Overall design:
   Coordinates network interaction with Upstox option chain endpoints:
     - Enforces timeout boundaries preventing socket hangs.
     - Implements exponential backoff with jitter on transient failures (429, 502, 503, 504).
     - Fails closed immediately on fatal auth errors (401, 403) without burning rate budget.
     - Strictly redacts access tokens from all logs, error messages, and string representations.
     - Returns raw unparsed bytes to guarantee raw-first storage before decoding.
     - Supports dependency injection of custom requests.Session for 100% offline mock testing.

3. Elements in the file:
   - UpstoxSnapshotAdapter: Main HTTP client class for fetching raw option chain payloads.
   - SnapshotResponsePayload: Dataclass containing raw response bytes, status, and timing metadata.

4. Final output of the file:
   - Exported UpstoxSnapshotAdapter and SnapshotResponsePayload classes.
"""

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from packages.data.budget import RateBudgetManager, RequestPriority

logger = logging.getLogger("quantview.collector_snapshot.adapter")


@dataclass
class SnapshotResponsePayload:
    """
    1. The use of class:
       Encapsulates raw HTTP response data and timing metadata from an option chain snapshot query.

    2. What the class contains:
       - raw_bytes: Exact bytes of the HTTP response body.
       - http_status: HTTP status code.
       - content_type: Content-Type header string.
       - request_timestamp_utc: ISO-8601 UTC timestamp of request initiation.
       - received_at_utc: ISO-8601 UTC timestamp of response arrival.
       - endpoint: Target URL path.
       - request_params: Request query parameters.

    3. Technologies used and why:
       Python dataclasses for clean, typed data representation.

    4. Key design and overall design of the class:
       Carries original response bytes directly to RawSnapshotWriter before parsing.
    """
    raw_bytes: bytes
    http_status: int
    content_type: str
    request_timestamp_utc: str
    received_at_utc: str
    endpoint: str
    request_params: Dict[str, Any]


class UpstoxSnapshotAdapter:
    """
    1. The use of class:
       Resilient HTTP client for Upstox REST option chain snapshot endpoints.

    2. What the class contains:
       - base_url: Target API endpoint URL.
       - access_token: Bearer access token (redacted in representations).
       - session: requests.Session instance (supports mock injection).
       - timeout_sec: Network socket timeout in seconds.
       - max_retries: Maximum retry attempts for transient errors.
       - fetch_raw_option_chain(): Executes HTTP GET, handles retries, and returns SnapshotResponsePayload.

    3. Technologies used and why:
       - requests: Standard synchronous HTTP client library.
       - time/random: Exponential backoff calculation with randomized jitter.

    4. Key design and overall design of the class:
       Safe, credential-protective adapter. Never exposes access token in __repr__ or error logs.
       Yields raw bytes directly for raw-first archiving.
    """

    DEFAULT_OPTION_CHAIN_URL = "https://api.upstox.com/v2/option/chain"

    def __init__(
        self,
        access_token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_sec: float = 10.0,
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
        budget_manager: Optional[RateBudgetManager] = None,
    ) -> None:
        """
        1. The use of function:
           Initializes UpstoxSnapshotAdapter with authentication credentials, timeout settings, and rate budget.

        2. How does the specific function work:
           Configures endpoints, timeout, retries, requests.Session, and RateBudgetManager. Redacts token.

        3. Concepts used in the function:
           Client initialization, dependency injection, rate budget coordination.

        4. Places where this function is imported and used:
           Instantiated by SnapshotCollectorService and test suites.

        5. Final output of the function, before and after:
           Before: Unconfigured client. After: Ready-to-query adapter instance.
        """
        self.access_token = access_token or ""
        self.base_url = base_url or self.DEFAULT_OPTION_CHAIN_URL
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.budget_manager = budget_manager

    def __repr__(self) -> str:
        """Redacts sensitive tokens in string representation."""
        masked_token = f"{self.access_token[:4]}...{self.access_token[-4:]}" if len(self.access_token) > 8 else "***"
        return f"UpstoxSnapshotAdapter(base_url='{self.base_url}', access_token='{masked_token}', timeout={self.timeout_sec}s)"

    def fetch_active_expiries(
        self,
        instrument_key: str = "NSE_INDEX|Nifty 50",
    ) -> List[str]:
        """
        1. The use of function:
           Fetches available live option contract expiries dynamically from Upstox REST API.

        2. How does the specific function work:
           - Queries /v2/option/contract endpoint with instrument_key.
           - Extracts and returns a sorted list of unique expiry dates.
           - Returns empty list if query fails or network unavailable.

        3. Concepts used in the function:
           Dynamic instrument contract discovery, defensive fallback.

        4. Places where this function is imported and used:
           Called by SnapshotCollectorService.resolve_active_expiry() to discover current live expiries.

        5. Final output of the function, before and after:
           Before: Unknown expiries. After: Sorted list of ISO-8601 expiry strings (e.g. ['2026-10-27', ...]).
        """
        contracts_url = "https://api.upstox.com/v2/option/contract"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        try:
            resp = self.session.get(
                contracts_url,
                headers=headers,
                params={"instrument_key": instrument_key},
                timeout=self.timeout_sec,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                expiries = sorted(list({c.get("expiry") for c in data if c.get("expiry")}))
                return expiries
        except Exception as ex:
            logger.warning("Failed to fetch active expiries dynamically: %s", ex)
        return []

    def fetch_raw_option_chain(
        self,
        instrument_key: str = "NSE_INDEX|Nifty 50",
        expiry_date: Optional[str] = None,
    ) -> SnapshotResponsePayload:
        """
        1. The use of function:
           Queries Upstox option chain endpoint and returns raw response bytes with timing metadata.

        2. How does the specific function work:
           - Constructs headers and request parameters.
           - Records request start timestamp in UTC.
           - Enters retry loop (up to max_retries) handling 429 and 5xx errors with exponential backoff and jitter.
           - If 401 or 403 encountered, immediately raises PermissionError without retrying.
           - Records receive timestamp in UTC upon response arrival.
           - Returns SnapshotResponsePayload containing raw response.content bytes.

        3. Concepts used in the function:
           HTTP networking, exponential backoff, jitter, fail-closed auth handling.

        4. Places where this function is imported and used:
           Called by SnapshotCollectorService during capture cycles.

        5. Final output of the function, before and after:
           Before: Request unexecuted. After: Raw bytes returned in SnapshotResponsePayload.
        """
        params: Dict[str, Any] = {"instrument_key": instrument_key}
        if expiry_date:
            params["expiry_date"] = expiry_date

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

        last_exception = None
        for attempt in range(self.max_retries + 1):
            if self.budget_manager is not None:
                self.budget_manager.acquire(priority=RequestPriority.HIGH)

            req_ts = datetime.now(timezone.utc).isoformat()
            try:
                resp = self.session.get(
                    self.base_url,
                    headers=headers,
                    params=params,
                    timeout=self.timeout_sec,
                )
                recv_ts = datetime.now(timezone.utc).isoformat()

                # Fail-closed on authentication rejection
                if resp.status_code in (401, 403):
                    raise PermissionError(f"HTTP {resp.status_code} Unauthorized: Check API credentials. Token redacted.")

                # Transient rate limit or server error: retry if attempts remain
                if resp.status_code == 429:
                    if self.budget_manager is not None:
                        retry_after = None
                        if "Retry-After" in resp.headers:
                            try:
                                retry_after = float(resp.headers["Retry-After"])
                            except ValueError:
                                retry_after = None
                        self.budget_manager.notify_rate_limit_hit(retry_after_sec=retry_after)

                    if attempt < self.max_retries:
                        sleep_time = (2 ** attempt) + random.uniform(0.1, 0.5)
                        time.sleep(sleep_time)
                        continue

                elif resp.status_code in (500, 502, 503, 504) and attempt < self.max_retries:
                    sleep_time = (2 ** attempt) + random.uniform(0.1, 0.5)
                    time.sleep(sleep_time)
                    continue

                return SnapshotResponsePayload(
                    raw_bytes=resp.content,
                    http_status=resp.status_code,
                    content_type=resp.headers.get("Content-Type", "application/json"),
                    request_timestamp_utc=req_ts,
                    received_at_utc=recv_ts,
                    endpoint=self.base_url,
                    request_params=params,
                )

            except (requests.ConnectionError, requests.Timeout) as ex:
                last_exception = ex
                if attempt < self.max_retries:
                    sleep_time = (2 ** attempt) + random.uniform(0.1, 0.5)
                    time.sleep(sleep_time)
                else:
                    raise ConnectionError(f"Upstox snapshot request failed after {self.max_retries} retries: {str(ex)}")

        raise RuntimeError(f"Unexpected completion of fetch_raw_option_chain: {last_exception}")
