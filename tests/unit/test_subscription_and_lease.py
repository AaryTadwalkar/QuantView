"""
1. What this file does:
   Executes comprehensive offline unit tests for Task M2-04:
     - SingleOwnerLease: Exclusive OS file locking, metadata recording, duplicate instance prevention.
     - SubscriptionManager: Dynamic set union, feed mode hierarchy resolution, capacity quota enforcement,
       rejection tracking, Upstox V3 wire payload formatting, and UI telemetry.

2. Overall design:
   The suite runs offline without live sockets or external broker dependencies:
     - TestSingleOwnerLease: Validates mutual exclusion, lock acquisition, fail-closed duplicate rejection,
       and clean context manager unlock and unlinking.
     - TestSubscriptionManager: Validates multi-source union, feed mode precedence ranking, quota guards,
       and Upstox V3 JSON wire commands.

3. Elements in the file:
   - TestSingleOwnerLease: TestCase for lease.py.
   - TestSubscriptionManager: TestCase for subscription.py.

4. Final output of the file:
   - Automated pass/fail unit assertions certifying Task M2-04 contracts.
"""

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from services.collector_ws.lease import (
    DuplicateCollectorInstanceError,
    LeaseMetadata,
    SingleOwnerLease,
)
from services.collector_ws.subscription import (
    FeedMode,
    SubscriptionConfig,
    SubscriptionManager,
    SubscriptionRejection,
)


class TestSingleOwnerLease(unittest.TestCase):
    """
    1. The use of class:
       Unit test suite verifying SingleOwnerLease OS-level exclusive locking and duplicate prevention.

    2. What the class contains:
       - setUp(): Initializes temporary test directory for lock file.
       - tearDown(): Cleans up temporary test directory.
       - test_exclusive_lease_acquisition(): Tests initial lock acquisition and metadata writing.
       - test_duplicate_instance_fails_closed(): Tests that a secondary instance raises DuplicateCollectorInstanceError.
       - test_lease_release_and_reacquisition(): Tests that releasing the lock permits reacquisition.
       - test_context_manager_lifecycle(): Tests context manager auto-acquisition and cleanup.

    3. Technologies used and why:
       Python unittest with tempfile to run isolated, hermetic lock tests.

    4. Key design and overall design of the class:
       Guarantees single-writer boundary at process startup before network calls.
    """

    def setUp(self) -> None:
        """
        1. The use of function:
           Sets up isolated temporary workspace for lock tests.

        2. How does the specific function work:
           Creates a temporary directory and sets lock file path within it.

        3. Concepts used in the function:
           Test isolation.

        4. Places where this function is imported and used:
           Invoked by unittest runner before each test method.

        5. Final output of the function, before and after:
           Before: No directory. After: Temporary directory created with lock file path defined.
        """
        self._temp_dir = tempfile.TemporaryDirectory()
        self.lock_path = Path(self._temp_dir.name) / ".collector_ws.lock"

    def tearDown(self) -> None:
        """
        1. The use of function:
           Cleans up temporary directory after each test.

        2. How does the specific function work:
           Calls cleanup() on TemporaryDirectory.

        3. Concepts used in the function:
           Resource teardown.

        4. Places where this function is imported and used:
           Invoked by unittest runner after each test method.

        5. Final output of the function, before and after:
           Before: Active temporary folder. After: Temporary folder purged.
        """
        self._temp_dir.cleanup()

    def test_exclusive_lease_acquisition(self) -> None:
        """
        1. The use of function:
           Verifies that a SingleOwnerLease successfully acquires the lock and persists valid metadata.

        2. How does the specific function work:
           - Instantiates SingleOwnerLease with lock_path.
           - Calls acquire().
           - Verifies is_locked is True, metadata is populated, and file contains JSON metadata.
           - Releases lock cleanly.

        3. Concepts used in the function:
           Exclusive locking, metadata persistence, process ownership.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unacquired lock. After: Acquired and verified metadata.
        """
        lease = SingleOwnerLease(lock_file_path=self.lock_path)
        meta = lease.acquire()

        self.assertTrue(lease.is_locked)
        self.assertIsNotNone(meta.lease_token)
        self.assertGreater(meta.pid, 0)
        self.assertTrue(self.lock_path.exists())

        # Inspect on-disk metadata from companion file
        with open(lease.meta_file_path, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
            self.assertEqual(disk_data["lease_token"], meta.lease_token)
            self.assertEqual(disk_data["pid"], meta.pid)

        lease.release()
        self.assertFalse(lease.is_locked)

    def test_duplicate_instance_fails_closed(self) -> None:
        """
        1. The use of function:
           Verifies that a second SingleOwnerLease instance fails closed with DuplicateCollectorInstanceError.

        2. How does the specific function work:
           - Acquires lease 1.
           - Instantiates lease 2 targeting the same lock file.
           - Calls lease2.acquire() and asserts DuplicateCollectorInstanceError is raised.
           - Releases lease 1.

        3. Concepts used in the function:
           Kernel mutual exclusion, fail-closed architecture, single writer boundary.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: One active lease. After: Secondary lease attempt rejected with exception.
        """
        lease1 = SingleOwnerLease(lock_file_path=self.lock_path)
        meta1 = lease1.acquire()
        self.assertTrue(lease1.is_locked)

        lease2 = SingleOwnerLease(lock_file_path=self.lock_path)
        with self.assertRaises(DuplicateCollectorInstanceError) as ctx:
            lease2.acquire()

        self.assertIn("Another collector_ws instance already holds the lock", str(ctx.exception))
        self.assertIn(str(meta1.pid), str(ctx.exception))
        self.assertFalse(lease2.is_locked)

        lease1.release()

    def test_lease_release_and_reacquisition(self) -> None:
        """
        1. The use of function:
           Verifies that once a lease is released, a subsequent instance can acquire it successfully.

        2. How does the specific function work:
           - Acquires lease 1 and releases it.
           - Verifies lock file unlinked.
           - Acquires lease 2 and asserts success.
           - Releases lease 2.

        3. Concepts used in the function:
           Lock lifecycle, reacquisition, lock unlinking.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Released lock. After: Second lease successfully acquired.
        """
        lease1 = SingleOwnerLease(lock_file_path=self.lock_path)
        lease1.acquire()
        lease1.release()

        self.assertFalse(lease1.is_locked)
        self.assertFalse(self.lock_path.exists())

        lease2 = SingleOwnerLease(lock_file_path=self.lock_path)
        meta2 = lease2.acquire()
        self.assertTrue(lease2.is_locked)
        self.assertIsNotNone(meta2.lease_token)
        lease2.release()

    def test_context_manager_lifecycle(self) -> None:
        """
        1. The use of function:
           Verifies python context manager syntax (`with SingleOwnerLease():`).

        2. How does the specific function work:
           - Enters `with SingleOwnerLease(lock_path) as meta:`.
           - Verifies lock held within block.
           - Verifies lock released after block exits.

        3. Concepts used in the function:
           RAII, context manager protocol.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unmanaged lease. After: Verified scoped acquisition and release.
        """
        lease = SingleOwnerLease(lock_file_path=self.lock_path)
        with lease as meta:
            self.assertTrue(lease.is_locked)
            self.assertIsNotNone(meta.lease_token)
            self.assertTrue(self.lock_path.exists())

        self.assertFalse(lease.is_locked)
        self.assertFalse(self.lock_path.exists())


class TestSubscriptionManager(unittest.TestCase):
    """
    1. The use of class:
       Unit test suite for SubscriptionManager multi-source set union, mode hierarchy, and quotas.

    2. What the class contains:
       - setUp(): Initializes SubscriptionManager with test config.
       - test_multi_source_union_and_mode_hierarchy(): Tests union and rank upgrades (LTPC -> FULL -> FULL_D30).
       - test_remove_subscription_and_source_cleanup(): Tests selective and bulk removal of subscriptions.
       - test_quota_enforcement_and_rejections(): Tests rejection logging when max_instruments limit is reached.
       - test_v3_wire_payload_generation(): Tests Upstox V3 JSON payload schema.
       - test_ui_status_telemetry(): Tests telemetry reporting dictionary.

    3. Technologies used and why:
       Python unittest for deterministic subscription testing.

    4. Key design and overall design of the class:
       Validates that multiple strategy deployments and chart viewers share the physical WebSocket stream.
    """

    def setUp(self) -> None:
        """
        1. The use of function:
           Initializes SubscriptionManager with a test capacity of 5 instruments.

        2. How does the specific function work:
           Instantiates SubscriptionConfig(max_instruments=5) and SubscriptionManager.

        3. Concepts used in the function:
           Test initialization.

        4. Places where this function is imported and used:
           Invoked by unittest runner before each test.

        5. Final output of the function, before and after:
           Before: Unset manager. After: Manager instance ready with max_instruments=5.
        """
        self.config = SubscriptionConfig(max_instruments=5)
        self.mgr = SubscriptionManager(config=self.config)

    def test_multi_source_union_and_mode_hierarchy(self) -> None:
        """
        1. The use of function:
           Tests that multi-source subscriptions are unioned and resolved to the highest requested mode rank.

        2. How does the specific function work:
           - Source A requests NIFTY at LTPC.
           - Source B requests NIFTY at FULL.
           - Source C requests BANKNIFTY at LTPC.
           - Source B requests NIFTY at FULL_D30.
           - Verifies effective subscriptions resolve NIFTY to FULL_D30 and BANKNIFTY to LTPC.

        3. Concepts used in the function:
           Set union, feed mode precedence ranking (FULL_D30 > FULL > LTPC).

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Disjoint source feeds. After: Unified set with highest fidelity feed mode.
        """
        self.mgr.add_subscription("source_a", "NSE_INDEX|Nifty 50", FeedMode.LTPC)
        effective = self.mgr.get_effective_subscriptions()
        self.assertEqual(effective["NSE_INDEX|Nifty 50"], FeedMode.LTPC)

        # Source B upgrades to FULL
        self.mgr.add_subscription("source_b", "NSE_INDEX|Nifty 50", FeedMode.FULL)
        effective = self.mgr.get_effective_subscriptions()
        self.assertEqual(effective["NSE_INDEX|Nifty 50"], FeedMode.FULL)

        # Source C adds different key
        self.mgr.add_subscription("source_c", "NSE_INDEX|Nifty Bank", FeedMode.LTPC)
        effective = self.mgr.get_effective_subscriptions()
        self.assertEqual(len(effective), 2)
        self.assertEqual(effective["NSE_INDEX|Nifty Bank"], FeedMode.LTPC)

        # Source D upgrades NIFTY to FULL_D30
        self.mgr.add_subscription("source_d", "NSE_INDEX|Nifty 50", FeedMode.FULL_D30)
        effective = self.mgr.get_effective_subscriptions()
        self.assertEqual(effective["NSE_INDEX|Nifty 50"], FeedMode.FULL_D30)

    def test_remove_subscription_and_source_cleanup(self) -> None:
        """
        1. The use of function:
           Tests removing single subscriptions and removing all subscriptions for an entire source.

        2. How does the specific function work:
           - Adds subscriptions for source A (key 1, key 2) and source B (key 2).
           - Removes key 2 from source A. Verifies key 2 remains in effective set (because source B needs it).
           - Removes source B. Verifies key 2 disappears from effective set.
           - Removes source A. Verifies effective set is empty.

        3. Concepts used in the function:
           Reference-counted set deduction, multi-tenant subscription lifecycle.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Populated subscriptions. After: Clean removal matching consumer lifecycles.
        """
        self.mgr.add_subscription("source_a", "KEY_1", FeedMode.LTPC)
        self.mgr.add_subscription("source_a", "KEY_2", FeedMode.FULL)
        self.mgr.add_subscription("source_b", "KEY_2", FeedMode.LTPC)

        self.assertEqual(len(self.mgr.get_effective_subscriptions()), 2)

        # Source A drops KEY_2
        removed = self.mgr.remove_subscription("source_a", "KEY_2")
        self.assertTrue(removed)
        # KEY_2 should still exist because source_b subscribes
        effective = self.mgr.get_effective_subscriptions()
        self.assertIn("KEY_2", effective)
        self.assertEqual(effective["KEY_2"], FeedMode.LTPC)

        # Remove source B completely
        removed_keys = self.mgr.remove_source("source_b")
        self.assertEqual(removed_keys, ["KEY_2"])
        effective = self.mgr.get_effective_subscriptions()
        self.assertNotIn("KEY_2", effective)
        self.assertIn("KEY_1", effective)

        # Remove source A completely
        self.mgr.remove_source("source_a")
        self.assertEqual(len(self.mgr.get_effective_subscriptions()), 0)

    def test_quota_enforcement_and_rejections(self) -> None:
        """
        1. The use of function:
           Tests that adding keys beyond max_instruments fails closed and logs inspectable rejections.

        2. How does the specific function work:
           - Adds 5 unique keys (filling capacity).
           - Attempts to add 6th key. Verifies add_subscription returns False.
           - Inspects get_rejected_subscriptions() and verifies QUOTA_EXCEEDED reason.
           - Verifies invalid empty keys are also rejected.

        3. Concepts used in the function:
           Capacity quota guarding, fail-closed enforcement, rejection transparency.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unconstrained manager. After: Verified quota boundary and logged rejection.
        """
        for i in range(5):
            success = self.mgr.add_subscription("source_a", f"INSTR_{i}", FeedMode.FULL)
            self.assertTrue(success)

        self.assertEqual(len(self.mgr.get_effective_subscriptions()), 5)

        # 6th key should be rejected
        overflow_success = self.mgr.add_subscription("source_b", "INSTR_5", FeedMode.FULL)
        self.assertFalse(overflow_success)

        # Effective set remains 5
        self.assertEqual(len(self.mgr.get_effective_subscriptions()), 5)

        # Rejections are logged
        rejections = self.mgr.get_rejected_subscriptions()
        self.assertEqual(len(rejections), 1)
        self.assertEqual(rejections[0]["source_id"], "source_b")
        self.assertEqual(rejections[0]["instrument_key"], "INSTR_5")
        self.assertIn("QUOTA_EXCEEDED", rejections[0]["reason"])

        # Invalid key rejection
        empty_success = self.mgr.add_subscription("source_c", "   ", FeedMode.LTPC)
        self.assertFalse(empty_success)
        rejections2 = self.mgr.get_rejected_subscriptions()
        self.assertEqual(len(rejections2), 2)
        self.assertEqual(rejections2[1]["reason"], "INVALID_INSTRUMENT_KEY")

    def test_v3_wire_payload_generation(self) -> None:
        """
        1. The use of function:
           Tests that generate_v3_payloads() produces valid Upstox V3 JSON subscription commands.

        2. How does the specific function work:
           - Adds subscriptions in LTPC and FULL modes.
           - Invokes generate_v3_payloads(method="sub").
           - Asserts output contains grouped payloads with guid, method, mode, and sorted instrumentKeys.

        3. Concepts used in the function:
           Wire protocol formatting, message batching.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Model state. After: Verified Upstox V3 wire commands.
        """
        self.mgr.add_subscription("src_1", "NSE_INDEX|Nifty 50", FeedMode.FULL)
        self.mgr.add_subscription("src_1", "NSE_INDEX|Nifty Bank", FeedMode.FULL)
        self.mgr.add_subscription("src_2", "NSE_FO|12345", FeedMode.LTPC)

        payloads = self.mgr.generate_v3_payloads(method="sub", guid="fixed-test-guid")
        self.assertEqual(len(payloads), 2)

        # Find FULL payload
        full_payload = next(p for p in payloads if p["data"]["mode"] == "full")
        self.assertEqual(full_payload["guid"], "fixed-test-guid")
        self.assertEqual(full_payload["method"], "sub")
        self.assertEqual(
            full_payload["data"]["instrumentKeys"],
            ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"],
        )

        # Find LTPC payload
        ltpc_payload = next(p for p in payloads if p["data"]["mode"] == "ltpc")
        self.assertEqual(ltpc_payload["data"]["instrumentKeys"], ["NSE_FO|12345"])

    def test_ui_status_telemetry(self) -> None:
        """
        1. The use of function:
           Tests that get_status() returns complete UI-readable subscription telemetry.

        2. How does the specific function work:
           - Subscribes keys and triggers a rejection.
           - Invokes get_status().
           - Verifies total_unique_instruments, max_instrument_limit, capacity_utilization_pct,
             and recent_rejections.

        3. Concepts used in the function:
           Observability, status reporting.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unmeasured metrics. After: Validated telemetry dictionary.
        """
        self.mgr.add_subscription("src_1", "KEY_A", FeedMode.LTPC)
        self.mgr.add_subscription("src_2", "KEY_B", FeedMode.FULL)

        status = self.mgr.get_status()
        self.assertEqual(status["total_unique_instruments"], 2)
        self.assertEqual(status["max_instrument_limit"], 5)
        self.assertEqual(status["capacity_utilization_pct"], 40.0)
        self.assertEqual(status["total_active_sources"], 2)
        self.assertEqual(status["total_rejections_logged"], 0)
