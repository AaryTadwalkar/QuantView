"""
1. What this file does:
   Implements the Upstox WebSocket subscription manager (SubscriptionManager).
   Coordinates instrument subscription sets across competing sources (active strategy deployments,
   chart viewers, and background trackers), resolves feed mode hierarchy, enforces connection quotas,
   and generates Upstox V3 JSON wire commands per QUANTVIEW_DATA_SPEC §4.5, §11.5, and Task M2-04.

2. Overall design:
   Coordinates multi-tenant subscription demands into a unified WebSocket stream:
     - Maintains subscriptions by source_id (e.g. deployment UUID, chart window ID).
     - Computes dynamic set union across all sources.
     - Resolves feed mode hierarchy: full_d30 (rank 3) > full (rank 2) > ltpc (rank 1).
     - Enforces hard capacity quota (max_instruments, default 500).
     - Records inspectable rejections when quota is exhausted or keys are invalid.
     - Generates Upstox V3 subscription JSON payloads for live socket dispatch.
     - Provides UI-readable observable telemetry.

3. Elements in the file:
   - FeedMode: Enum defining ltpc, full, and full_d30 modes with precedence rankings.
   - SubscriptionRejection: Dataclass recording rejected subscription attempts and reasons.
   - SubscriptionConfig: Dataclass parameterizing max capacity and default modes.
   - SubscriptionManager: Central class managing subscription lifecycle, union, and wire formatting.

4. Final output of the file:
   - Exported SubscriptionManager, FeedMode, SubscriptionConfig, and SubscriptionRejection classes.
"""

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("quantview.collector_ws.subscription")


class FeedMode(str, Enum):
    """
    1. The use of class:
       Enumeration of Upstox V3 WebSocket feed modes and depth tiers.

    2. What the class contains:
       - LTPC: Last Traded Price and Close ('ltpc', rank 1).
       - FULL: Full market depth 5 levels ('full', rank 2).
       - FULL_D30: 30-level market depth for Upstox Plus ('full_d30', rank 3).

    3. Technologies used and why:
       Python string Enum for type safety and direct JSON serialization.

    4. Key design and overall design of the class:
       Includes rank property to ensure the highest fidelity feed mode is selected in unions.
    """
    LTPC = "ltpc"
    FULL = "full"
    FULL_D30 = "full_d30"

    @property
    def rank(self) -> int:
        """
        1. The use of function:
           Provides integer rank for precedence resolution across competing feed modes.

        2. How does the specific function work:
           Maps LTPC -> 1, FULL -> 2, FULL_D30 -> 3. Higher rank indicates higher market data depth.

        3. Concepts used in the function:
           Hierarchy ranking, feed mode resolution.

        4. Places where this function is imported and used:
           Used by SubscriptionManager.get_effective_subscriptions() to select highest requested tier.

        5. Final output of the function, before and after:
           Before: Unranked enum. After: Integer rank 1, 2, or 3.
        """
        ranks = {FeedMode.LTPC: 1, FeedMode.FULL: 2, FeedMode.FULL_D30: 3}
        return ranks.get(self, 1)


@dataclass
class SubscriptionRejection:
    """
    1. The use of class:
       Encapsulates a rejected subscription attempt for administrative inspection.

    2. What the class contains:
       - source_id: Requesting entity identifier.
       - instrument_key: Target instrument string.
       - requested_mode: FeedMode string requested.
       - reason: Diagnostic failure code (e.g. 'QUOTA_EXCEEDED', 'INVALID_INSTRUMENT_KEY').
       - rejected_at_utc: ISO-8601 UTC timestamp of rejection.

    3. Technologies used and why:
       Python dataclasses for clean serialization.

    4. Key design and overall design of the class:
       Ensures rejection transparency so operators and strategy runners can audit denied feeds.
    """
    source_id: str
    instrument_key: str
    requested_mode: str
    reason: str
    rejected_at_utc: str


@dataclass
class SubscriptionConfig:
    """
    1. The use of class:
       Configuration settings for WebSocket subscription limits.

    2. What the class contains:
       - max_instruments: Maximum unique instruments allowed on single connection (default 500).
       - default_mode: Fallback feed mode if unspecified ('full').

    3. Technologies used and why:
       Python dataclasses for immutable parameter transfer.

    4. Key design and overall design of the class:
       Protects broker connection from exceeding vendor subscription limits.
    """
    max_instruments: int = 500
    default_mode: FeedMode = FeedMode.FULL


class SubscriptionManager:
    """
    1. The use of class:
       Coordinates multi-client instrument subscriptions into a single unified WebSocket feed.

    2. What the class contains:
       - config: SubscriptionConfig instance.
       - _subscriptions_by_source: Map of source_id -> {instrument_key: FeedMode}.
       - _rejections: List of SubscriptionRejection records.
       - add_subscription(): Registers an instrument interest from a specific source.
       - remove_subscription(): Withdraws an instrument interest from a specific source.
       - remove_source(): Clears all subscriptions associated with a terminated source.
       - get_effective_subscriptions(): Computes set union with resolved highest feed mode.
       - generate_v3_payloads(): Generates JSON wire commands for Upstox V3 socket.
       - get_status(): Returns comprehensive UI-readable subscription telemetry.

    3. Technologies used and why:
       Python dict/set logic for efficient O(1) set operations and precedence evaluation.

    4. Key design and overall design of the class:
       Decouples individual strategy/UI lifecycles from the single physical connection.
       Automatically upgrades feed mode to highest requested tier across active consumers.
    """

    def __init__(self, config: Optional[SubscriptionConfig] = None) -> None:
        """
        1. The use of function:
           Initializes SubscriptionManager with limits and empty tracking structures.

        2. How does the specific function work:
           Configures SubscriptionConfig and initializes subscription dictionaries.

        3. Concepts used in the function:
           State initialization.

        4. Places where this function is imported and used:
           Used by collector_ws daemon, API services, and test fixtures.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: SubscriptionManager instance ready for subscriptions.
        """
        self.config = config or SubscriptionConfig()
        self._subscriptions_by_source: Dict[str, Dict[str, FeedMode]] = {}
        self._rejections: List[SubscriptionRejection] = []

    def add_subscription(
        self,
        source_id: str,
        instrument_key: str,
        feed_mode: FeedMode = FeedMode.FULL,
    ) -> bool:
        """
        1. The use of function:
           Subscribes an instrument on behalf of a specific source (e.g. deployment or chart).

        2. How does the specific function work:
           - Validates non-empty instrument key.
           - Checks if instrument is new to the effective set.
           - If new and current unique instruments count >= max_instruments:
             records SubscriptionRejection (QUOTA_EXCEEDED) and returns False.
           - Adds key and mode to source mapping.
           - Returns True on success.

        3. Concepts used in the function:
           Quota gating, multi-source subscription tracking.

        4. Places where this function is imported and used:
           Called when a deployment starts or user opens an instrument chart.

        5. Final output of the function, before and after:
           Before: Unregistered key. After: Key tracked; True returned (or False on quota limit).
        """
        clean_key = instrument_key.strip()
        if not clean_key:
            self._record_rejection(source_id, instrument_key, feed_mode.value, "INVALID_INSTRUMENT_KEY")
            return False

        effective = self.get_effective_subscriptions()
        if clean_key not in effective and len(effective) >= self.config.max_instruments:
            self._record_rejection(
                source_id,
                clean_key,
                feed_mode.value,
                f"QUOTA_EXCEEDED_MAX_{self.config.max_instruments}",
            )
            return False

        if source_id not in self._subscriptions_by_source:
            self._subscriptions_by_source[source_id] = {}

        self._subscriptions_by_source[source_id][clean_key] = feed_mode
        logger.info(
            "Added subscription for %s from source %s (mode: %s)",
            clean_key,
            source_id,
            feed_mode.value,
        )
        return True

    def remove_subscription(self, source_id: str, instrument_key: str) -> bool:
        """
        1. The use of function:
           Withdraws an instrument interest from a specific source.

        2. How does the specific function work:
           Deletes key from source mapping. If other sources still subscribe, key remains in union.

        3. Concepts used in the function:
           Reference counted set deduction.

        4. Places where this function is imported and used:
           Called when a chart tab closes or strategy unloads a contract.

        5. Final output of the function, before and after:
           Before: Source subscribed. After: Source mapping removed; True if found, False otherwise.
        """
        clean_key = instrument_key.strip()
        if source_id in self._subscriptions_by_source:
            if clean_key in self._subscriptions_by_source[source_id]:
                del self._subscriptions_by_source[source_id][clean_key]
                if not self._subscriptions_by_source[source_id]:
                    del self._subscriptions_by_source[source_id]
                logger.info("Removed subscription for %s from source %s", clean_key, source_id)
                return True
        return False

    def remove_source(self, source_id: str) -> List[str]:
        """
        1. The use of function:
           Clears all subscriptions associated with a terminated source.

        2. How does the specific function work:
           Pops source_id entry from tracking map, returning list of removed keys.

        3. Concepts used in the function:
           Bulk source cleanup.

        4. Places where this function is imported and used:
           Called when deployment halts or user session closes.

        5. Final output of the function, before and after:
           Before: Source had active keys. After: Source cleared; list of removed keys returned.
        """
        if source_id in self._subscriptions_by_source:
            removed_keys = list(self._subscriptions_by_source[source_id].keys())
            del self._subscriptions_by_source[source_id]
            logger.info("Cleared all %d subscriptions for source %s", len(removed_keys), source_id)
            return removed_keys
        return []

    def get_effective_subscriptions(self) -> Dict[str, FeedMode]:
        """
        1. The use of function:
           Computes the unified effective subscription set with resolved highest feed modes.

        2. How does the specific function work:
           Iterates through all sources and keys. For each unique key, selects the FeedMode with highest rank.

        3. Concepts used in the function:
           Set union, feed mode precedence resolution.

        4. Places where this function is imported and used:
           Called before sending WebSocket subscription messages and during health audits.

        5. Final output of the function, before and after:
           Before: Multi-source mappings. After: Consolidated {instrument_key: resolved_mode} dict.
        """
        effective: Dict[str, FeedMode] = {}
        for source_keys in self._subscriptions_by_source.values():
            for key, mode in source_keys.items():
                if key not in effective:
                    effective[key] = mode
                else:
                    # Resolve to highest rank
                    if mode.rank > effective[key].rank:
                        effective[key] = mode
        return effective

    def generate_v3_payloads(
        self,
        method: str = "sub",
        guid: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        1. The use of function:
           Generates Upstox V3 JSON subscription commands grouped by feed mode.

        2. How does the specific function work:
           - Computes effective subscriptions.
           - Groups keys by FeedMode.
           - Constructs Upstox V3 JSON wire payload:
             {"guid": "...", "method": method, "data": {"mode": mode_val, "instrumentKeys": [...]}}.

        3. Concepts used in the function:
           Wire protocol formatting, batching.

        4. Places where this function is imported and used:
           Called by WebSocket connection client to transmit subscription changes.

        5. Final output of the function, before and after:
           Before: Internal model state. After: List of JSON-serializable dictionaries ready for socket.
        """
        effective = self.get_effective_subscriptions()
        by_mode: Dict[FeedMode, List[str]] = {}
        for key, mode in effective.items():
            by_mode.setdefault(mode, []).append(key)

        payloads: List[Dict[str, Any]] = []
        for mode, keys in by_mode.items():
            payload = {
                "guid": guid or str(uuid.uuid4()),
                "method": method,
                "data": {
                    "mode": mode.value,
                    "instrumentKeys": sorted(keys),
                },
            }
            payloads.append(payload)

        return payloads

    def _record_rejection(self, source_id: str, key: str, mode: str, reason: str) -> None:
        """
        1. The use of function:
           Records an unfulfilled subscription attempt into the rejection log.

        2. How does the specific function work:
           Constructs a SubscriptionRejection dataclass with UTC timestamp and appends to self._rejections.

        3. Concepts used in the function:
           Auditability, diagnostic logging, observable rejections.

        4. Places where this function is imported and used:
           Used internally by add_subscription() when quotas or validation guards fail.

        5. Final output of the function, before and after:
           Before: Unlogged rejection. After: Rejection appended to audit trail.
        """
        rej = SubscriptionRejection(
            source_id=source_id,
            instrument_key=key,
            requested_mode=mode,
            reason=reason,
            rejected_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        self._rejections.append(rej)
        logger.warning(
            "Rejected subscription for %s from %s (reason: %s)",
            key,
            source_id,
            reason,
        )

    def get_rejected_subscriptions(self) -> List[Dict[str, Any]]:
        """
        1. The use of function:
           Returns all logged subscription rejections as a list of dictionaries.

        2. How does the specific function work:
           Transforms dataclass records in self._rejections using asdict().

        3. Concepts used in the function:
           Telemetry exposure, serialization.

        4. Places where this function is imported and used:
           Used by UI status handlers and test verifications.

        5. Final output of the function, before and after:
           Before: List of internal dataclasses. After: List of serialized dictionaries.
        """
        return [asdict(r) for r in self._rejections]

    def clear_rejections(self) -> None:
        """
        1. The use of function:
           Clears historical subscription rejections from memory.

        2. How does the specific function work:
           Calls self._rejections.clear().

        3. Concepts used in the function:
           Log pruning, reset.

        4. Places where this function is imported and used:
           Used between test cases or operational reset cycles.

        5. Final output of the function, before and after:
           Before: Rejections list with entries. After: Empty rejections list.
        """
        self._rejections.clear()

    def get_status(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Returns comprehensive, UI-readable subscription telemetry.

        2. How does the specific function work:
           Computes active unique keys, capacity utilization percentage, source counts, and rejections.

        3. Concepts used in the function:
           Observability, status reporting.

        4. Places where this function is imported and used:
           UI telemetry endpoints, health logs, and test suites.

        5. Final output of the function, before and after:
           Before: Unmeasured metrics. After: Structured status dictionary.
        """
        effective = self.get_effective_subscriptions()
        count = len(effective)
        utilization = (count / self.config.max_instruments) * 100.0 if self.config.max_instruments > 0 else 0.0

        return {
            "total_unique_instruments": count,
            "max_instrument_limit": self.config.max_instruments,
            "capacity_utilization_pct": round(utilization, 2),
            "total_active_sources": len(self._subscriptions_by_source),
            "effective_subscriptions": {k: m.value for k, m in effective.items()},
            "total_rejections_logged": len(self._rejections),
            "recent_rejections": [asdict(r) for r in self._rejections[-5:]],
        }
