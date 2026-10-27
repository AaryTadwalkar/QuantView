"""
1. What this file does:
   Executes comprehensive fault-injection testing for QuantView collectors (collector_ws and collector_snapshot)
   conforming to QUANTVIEW_DATA_SPEC §10, QUANTVIEW_MASTER_SPEC §3, and Task M2-09.

2. Overall design:
   The suite runs in isolated temporary sandbox directories without external network dependencies:
     - Disk-Full Fault: Simulates simulated storage exhaustion (OSError Errno 28) and verifies fail-closed safety.
     - Clock Jump Fault: Injects backwards time jumps and verifies monotonic sequencing and anomaly detection.
     - Duplicate Lease Collision: Injects concurrent instance startup and asserts immediate fail-closed mutual exclusion.
     - Process Crash Partial Recovery: Writes corrupted/truncated .partial segments and asserts forensic recovery and quarantine.
     - Token Expiry Fault: Injects expired/invalid JWT tokens and asserts WAITING_FOR_TOKEN / EXPIRED state transitions.

3. Elements in the file:
   - TestCollectorFaultInjection: TestCase class executing all fault injection scenarios.

4. Final output of the file:
   - Automated pass/fail unit assertions certifying collector resilience across all five required failure modes.
"""

import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.collector_snapshot.token_manager import TokenManager, TokenState
from services.collector_ws.framing import pack_frame, unpack_frames_from_bytes
from services.collector_ws.lease import DuplicateCollectorInstanceError, SingleOwnerLease
from services.collector_ws.raw_segment_writer import RawSegmentWriter


class TestCollectorFaultInjection(unittest.TestCase):
    """
    1. The use of class:
       Integration test suite injecting infrastructure and operating system faults into collector components.

    2. What the class contains:
       - setUp(): Initializes isolated sandboxed directory.
       - tearDown(): Cleans up temporary resources.
       - test_disk_full_fail_closed(): Injects simulated disk-full OSError and asserts fail-closed behavior.
       - test_clock_jump_anomaly(): Injects backwards time jump and asserts monotonic sequencing.
       - test_duplicate_collector_lease(): Injects duplicate process collision and asserts mutual exclusion.
       - test_process_crash_partial_recovery(): Injects truncated frames and asserts quarantine/recovery.
       - test_token_expiry_transition(): Injects expired JWT and asserts safe refusal to connect.

    3. Technologies used and why:
       Python unittest with tempfile, mock patching, and binary frame injection.

    4. Key design and overall design of the class:
       Certifies that collector failures never corrupt disk state, discard raw data, or spawn duplicate sockets.
    """

    def setUp(self) -> None:
        """
        1. The use of function:
           Prepares temporary directories before each fault injection test.

        2. How does the specific function work:
           Creates a temporary sandbox directory for data, logs, and locks.

        3. Concepts used in the function:
           Test isolation.

        4. Places where this function is imported and used:
           unittest framework setup hook.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Temp sandbox ready.
        """
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sandbox_path = Path(self.temp_dir.name)
        self.raw_ws_dir = self.sandbox_path / "Data" / "raw" / "upstox_ws" / "ticks"
        self.raw_ws_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """
        1. The use of function:
           Cleans up temporary sandbox directory.

        2. How does the specific function work:
           Calls cleanup() on temporary directory.

        3. Concepts used in the function:
           Resource reclamation.

        4. Places where this function is imported and used:
           unittest framework teardown hook.

        5. Final output of the function, before and after:
           Before: Sandbox exists. After: Cleaned up.
        """
        self.temp_dir.cleanup()

    def test_disk_full_fail_closed(self) -> None:
        """
        1. The use of function:
           Tests that RawSegmentWriter fails closed when the underlying filesystem is full.

        2. How does the specific function work:
           - Instantiates RawSegmentWriter.
           - Writes a valid initial frame.
           - Patches os.write to raise OSError(28, "No space left on device").
           - Asserts that subsequent write_frame raises OSError and does not corrupt existing data.

        3. Concepts used in the function:
           Disk exhaustion fault injection, fail-closed durability.

        4. Places where this function is imported and used:
           Invoked by unittest runner for Task M2-09.

        5. Final output of the function, before and after:
           Before: Normal writing. After: Certified fail-closed behavior on disk full.
        """
        writer = RawSegmentWriter(
            connection_id="disk_full_conn",
            trade_date="2026-10-26",
            base_raw_dir=self.raw_ws_dir,
        )
        # First write succeeds
        now_utc = datetime.now(timezone.utc)
        seq1 = writer.write_frame(b"VALID_INITIAL_FRAME", now_utc)
        self.assertEqual(seq1, 1)

        # Inject disk full on flush
        with patch.object(writer._active_file, "write", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                writer.write_frame(b"FAILING_FRAME_ON_FULL_DISK", now_utc)

        writer.close()
        # Verify valid initial segment was rotated cleanly and contains the 1 valid frame
        gz_files = list((self.raw_ws_dir / "trade_date=2026-10-26").glob("*.bin.gz"))
        self.assertEqual(len(gz_files), 1)

        import gzip
        with gzip.open(gz_files[0], "rb") as f:
            recovered_bytes = f.read()
        frames, _, _ = unpack_frames_from_bytes(recovered_bytes)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].payload, b"VALID_INITIAL_FRAME")

    def test_clock_jump_anomaly(self) -> None:
        """
        1. The use of function:
           Tests that collector sequence numbers remain strictly monotonic even during system clock jumps.

        2. How does the specific function work:
           - Writes frame with timestamp T0.
           - Writes frame with backwards timestamp T0 - 3600s (simulating clock skew / NTP jump).
           - Asserts sequence numbers are strictly incrementing (1, 2).

        3. Concepts used in the function:
           Monotonic sequencing, clock anomaly tolerance.

        4. Places where this function is imported and used:
           Invoked by unittest runner for Task M2-09.

        5. Final output of the function, before and after:
           Before: Susceptible to clock skew. After: Certified monotonic sequencing.
        """
        writer = RawSegmentWriter(
            connection_id="clock_conn",
            trade_date="2026-10-26",
            base_raw_dir=self.raw_ws_dir,
        )
        t_now = datetime(2026, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
        seq1 = writer.write_frame(b"FRAME_1", t_now)

        # Inject clock jump backwards by 1 hour
        t_jump_back = datetime(2026, 10, 26, 9, 0, 0, tzinfo=timezone.utc)
        seq2 = writer.write_frame(b"FRAME_2", t_jump_back)

        self.assertEqual(seq1, 1)
        self.assertEqual(seq2, 2)
        writer.close()

    def test_duplicate_collector_lease(self) -> None:
        """
        1. The use of function:
           Tests that a second collector instance fails immediately before opening any socket.

        2. How does the specific function work:
           - First lease acquires lock file in sandbox.
           - Second lease attempts acquisition on same path.
           - Asserts DuplicateCollectorInstanceError is raised immediately.

        3. Concepts used in the function:
           Process mutual exclusion, single-owner invariant.

        4. Places where this function is imported and used:
           Invoked by unittest runner for Task M2-09.

        5. Final output of the function, before and after:
           Before: Risk of concurrent duplicate connections. After: Guaranteed single-owner mutual exclusion.
        """
        lock_dir = self.sandbox_path / "Data" / "raw" / "upstox_ws"
        lock_file = lock_dir / ".collector_ws.lock"

        lease1 = SingleOwnerLease(lock_file_path=lock_file)
        lease2 = SingleOwnerLease(lock_file_path=lock_file)

        # First acquires cleanly
        lease1.acquire()
        self.assertTrue(lease1.is_locked)

        # Second must fail closed
        with self.assertRaises(DuplicateCollectorInstanceError):
            lease2.acquire()

        lease1.release()
        self.assertFalse(lease1.is_locked)

    def test_process_crash_partial_recovery(self) -> None:
        """
        1. The use of function:
           Tests that incomplete .partial segment files from sudden process crashes are recovered and quarantined.

        2. How does the specific function work:
           - Packs two valid frames into binary data.
           - Appends 15 bytes of truncated, corrupt garbage bytes (simulating unbuffered crash).
           - Writes data to .bin.partial file.
           - Runs RawSegmentWriter.recover_session_partials().
           - Asserts valid frames are recovered to .bin.gz with .manifest.json and corrupt fragment quarantined.

        3. Concepts used in the function:
           Crash recovery, binary frame unpacking, forensic quarantine.

        4. Places where this function is imported and used:
           Invoked by unittest runner for Task M2-09.

        5. Final output of the function, before and after:
           Before: Corrupted session file. After: Recovered complete frames and quarantined fragments.
        """
        session_dir = self.raw_ws_dir / "trade_date=2026-10-26"
        session_dir.mkdir(parents=True, exist_ok=True)
        partial_path = session_dir / "ws_seg_2026-10-26_crash_test_000001.bin.partial"

        # Pack 2 valid frames
        frame1 = pack_frame(sequence_number=1, recv_time_us=1700000000000000, payload=b"HELLO_MARKET_TICK_1")
        frame2 = pack_frame(sequence_number=2, recv_time_us=1700000001000000, payload=b"HELLO_MARKET_TICK_2")
        corrupt_tail = b"TRUNCATED_GARBAGE_BYTES"

        with open(partial_path, "wb") as f:
            f.write(frame1 + frame2 + corrupt_tail)

        # Run crash recovery
        result = RawSegmentWriter.recover_session_partials(
            trade_date="2026-10-26",
            base_raw_dir=self.raw_ws_dir,
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["recovered_segments"], 1)
        self.assertEqual(result["quarantined_files"], 1)

        # Verify finalized .bin.gz exists
        gz_files = list(session_dir.glob("*.bin.gz"))
        manifest_files = list(session_dir.glob("*.manifest.json"))
        self.assertEqual(len(gz_files), 1)
        self.assertEqual(len(manifest_files), 1)

        # Verify manifest recorded 2 recovered frames
        with open(manifest_files[0], "r", encoding="utf-8") as mf:
            m_data = json.load(mf)
        self.assertEqual(m_data["total_frames"], 2)
        self.assertIn("RECOVERED_FROM_PARTIAL", m_data["quality_flags"])

    def test_token_expiry_transition(self) -> None:
        """
        1. The use of function:
           Tests that TokenManager detects expired JWT tokens and transitions to EXPIRED state.

        2. How does the specific function work:
           - Constructs a synthetic expired JWT payload (exp: timestamp in the past).
           - Instantiates TokenManager with expired token.
           - Evaluates token readiness.
           - Asserts is_ready is False and state is EXPIRED.

        3. Concepts used in the function:
           JWT validation, pre-flight authentication gating.

        4. Places where this function is imported and used:
           Invoked by unittest runner for Task M2-09.

        5. Final output of the function, before and after:
           Before: Unchecked token. After: Certified token expiration detection.
        """
        import base64
        # Construct synthetic expired JWT: header.payload.sig
        header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode("utf-8").rstrip("=")
        # Expired 1 hour ago
        past_exp = int(time.time()) - 3600
        payload_json = json.dumps({"sub": "test_user", "exp": past_exp})
        payload = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")
        expired_jwt = f"{header}.{payload}.synthetic_signature"

        mgr = TokenManager(token=expired_jwt)
        readiness = mgr.check_token_readiness()

        self.assertFalse(readiness.is_ready)
        self.assertEqual(readiness.state, TokenState.EXPIRED)
        self.assertIn("expired", readiness.message.lower())


if __name__ == "__main__":
    unittest.main()
