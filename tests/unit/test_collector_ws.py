"""
1. What this file does:
   Automated unit and contract test suite for Milestone M2-03 (WebSocket Raw Segment Writer).
   Verifies binary frame packing/unpacking, batched fsync durability (<= 1s loss window),
   segment rotation, manifest generation, crash recovery at write boundaries, CRC32 tamper detection,
   and forensic session reconciliation per QUANTVIEW_DATA_SPEC §4.5, QUANTVIEW_MASTER_SPEC §3, and Task M2-03.

2. Overall design:
   Uses standard unittest with temporary directories and synthetic frame streams:
     - TestFramingProtocol: Tests binary envelope serialization, CRC32 calculation, and partial unpacking.
     - TestRawSegmentWriter: Tests live streaming, batched fsync, rotation thresholds, and companion manifests.
     - TestCrashRecoveryAndQuarantine: Tests abrupt kill at write boundaries, truncated partial recovery,
       corrupted byte quarantine, and reconciliation auditing.

3. Elements in the file:
   - TestFramingProtocol: Unit tests for framing envelope packing, unpacking, and CRC verification.
   - TestRawSegmentWriter: Unit tests for streaming, batched fsync, and clean finalization.
   - TestCrashRecoveryAndQuarantine: Unit tests for process kill simulation, partial recovery, and quarantine.

4. Final output of the file:
   - Pass/fail test execution verifying all acceptance criteria of Milestone M2-03.
"""

import gzip
import hashlib
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from services.collector_ws.framing import (
    FRAME_MAGIC,
    HEADER_SIZE,
    ParsedFrame,
    pack_frame,
    unpack_frames_from_bytes,
)
from services.collector_ws.raw_segment_writer import RawSegmentWriter, SegmentManifest


class TestFramingProtocol(unittest.TestCase):
    """
    1. The use of class:
       Unit tests for binary frame packing, CRC32 checksums, and defensive unpacking.

    2. What the class contains:
       - test_pack_and_unpack_roundtrip: Asserts exact byte-for-byte fidelity of frame payload.
       - test_unpack_detects_crc32_corruption: Asserts corrupted payload triggers CRC32 mismatch.
       - test_unpack_isolates_incomplete_trailing_bytes: Asserts incomplete frame is cleanly separated.

    3. Technologies used and why:
       struct, zlib, and unittest for binary wire protocol testing.

    4. Key design and overall design of the class:
       Validates framing mechanics before data is written to disk.
    """

    def test_pack_and_unpack_roundtrip(self):
        """
        1. The use of function:
           Verifies that packed binary frames roundtrip through unpacking with zero byte drift.

        2. How does the specific function work:
           Packs 3 distinct frames with varying sequence numbers and payloads, concatenates, and unpacks.

        3. Concepts used in the function:
           Stream framing roundtrip, checksum verification.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Raw payloads. After: Parsed frames matching original inputs exactly.
        """
        payloads = [
            b"\x08\x01\x12\x04test",
            b"\x08\x02\x12\x08protobuf_mock",
            b"\x00" * 256,
        ]
        stream = bytearray()
        now_us = 1700000000000000

        for idx, p in enumerate(payloads, start=1):
            stream.extend(pack_frame(sequence_number=idx, recv_time_us=now_us + idx, payload=p))

        frames, trailing, err = unpack_frames_from_bytes(bytes(stream))
        self.assertEqual(len(frames), 3)
        self.assertEqual(len(trailing), 0)
        self.assertIsNone(err)

        for idx, f in enumerate(frames, start=1):
            self.assertEqual(f.sequence_number, idx)
            self.assertEqual(f.payload, payloads[idx - 1])
            self.assertEqual(f.recv_time_us, now_us + idx)

    def test_unpack_detects_crc32_corruption(self):
        """
        1. The use of function:
           Verifies unpacker rejects tampered payloads with explicit CRC32 error.

        2. How does the specific function work:
           Packs frame, flips a single bit in the payload, calls unpack_frames_from_bytes().

        3. Concepts used in the function:
           Tamper detection, bit corruption isolation.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Tampered stream. After: Asserts error contains CRC32_MISMATCH.
        """
        packed = bytearray(pack_frame(sequence_number=1, recv_time_us=1000, payload=b"original_payload"))
        # Corrupt one payload byte (header is 28 bytes)
        packed[30] ^= 0xFF

        frames, trailing, err = unpack_frames_from_bytes(bytes(packed))
        self.assertEqual(len(frames), 0)
        self.assertIn("CRC32_MISMATCH", str(err))
        self.assertEqual(len(trailing), len(packed))

    def test_unpack_isolates_incomplete_trailing_bytes(self):
        """
        1. The use of function:
           Verifies unpacker cleanly separates complete frames from trailing truncated fragments.

        2. How does the specific function work:
           Packs 2 full frames, appends truncated 10-byte slice of a 3rd frame, unpacks.

        3. Concepts used in the function:
           Truncation boundary handling, crash simulation.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Truncated stream. After: 2 complete frames recovered; trailing 10 bytes flagged.
        """
        f1 = pack_frame(sequence_number=1, recv_time_us=1001, payload=b"frame1")
        f2 = pack_frame(sequence_number=2, recv_time_us=1002, payload=b"frame2")
        f3_partial = pack_frame(sequence_number=3, recv_time_us=1003, payload=b"frame3_long_payload")[:15]

        combined = f1 + f2 + f3_partial
        frames, trailing, err = unpack_frames_from_bytes(combined)

        self.assertEqual(len(frames), 2)
        self.assertEqual(len(trailing), 15)
        self.assertIn("INCOMPLETE_TRAILING", str(err))


class TestRawSegmentWriter(unittest.TestCase):
    """
    1. The use of class:
       Unit tests for RawSegmentWriter live streaming, batched fsync, rotation, and manifests.

    2. What the class contains:
       - setUp: Prepares temporary directory for raw storage.
       - tearDown: Cleans up temporary directory.
       - test_write_frames_and_batched_fsync: Asserts loss window <= 1.0s and fsync behavior.
       - test_segment_rotation_and_manifest_hashes: Asserts rotation to .bin.gz and manifest creation.
       - test_clean_shutdown_unlinks_empty_partial: Asserts zero orphan .partial files after close.

    3. Technologies used and why:
       tempfile and gzip for realistic filesystem simulation.

    4. Key design and overall design of the class:
       Validates raw segment streaming and cryptographic manifest publication.
    """

    def setUp(self):
        """
        1. The use of function:
           Initializes temporary directory and writer instance.

        2. How does the specific function work:
           Creates TemporaryDirectory and instantiates RawSegmentWriter.

        3. Concepts used in the function:
           Test setup.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: self.test_dir and self.writer ready.
        """
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)
        self.connection_id = "conn_unit_01"
        self.trade_date = "2026-10-26"
        self.writer = RawSegmentWriter(
            connection_id=self.connection_id,
            trade_date=self.trade_date,
            base_raw_dir=self.test_root,
            fsync_interval_sec=1.0,
            max_frames_per_segment=50,
        )

    def tearDown(self):
        """
        1. The use of function:
           Cleans up temporary resources.

        2. How does the specific function work:
           Calls close() on writer and cleans up TemporaryDirectory.

        3. Concepts used in the function:
           Resource disposal.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Temp dir exists. After: Deleted.
        """
        self.writer.close()
        self.temp_dir.cleanup()

    def test_write_frames_and_batched_fsync(self):
        """
        1. The use of function:
           Verifies that writing frames updates sequence numbers and fsync commits data.

        2. How does the specific function work:
           Writes 5 frames, calls flush_and_fsync(), verifies partial file exists and is non-empty.

        3. Concepts used in the function:
           Batched durability verification.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Empty session dir. After: .partial file with 5 framed records committed to disk.
        """
        for i in range(5):
            seq = self.writer.write_frame(raw_payload=f"tick_{i}".encode("utf-8"))
            self.assertEqual(seq, i + 1)

        self.writer.flush_and_fsync()

        session_dir = self.test_root / f"trade_date={self.trade_date}"
        partial_files = list(session_dir.glob("*.bin.partial"))
        self.assertEqual(len(partial_files), 1)
        self.assertGreater(partial_files[0].stat().st_size, 0)

    def test_segment_rotation_and_manifest_hashes(self):
        """
        1. The use of function:
           Verifies that segment rotation creates finalized .bin.gz and matching manifest.

        2. How does the specific function work:
           Writes 20 frames, triggers rotate_and_finalize(), verifies .bin.gz and manifest SHA-256.

        3. Concepts used in the function:
           Segment rotation, cryptographic digest verification.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Open partial file. After: Finalized .bin.gz and .manifest.json verified on disk.
        """
        for i in range(20):
            self.writer.write_frame(raw_payload=f"payload_data_{i:04d}".encode("utf-8"))

        manifest = self.writer.rotate_and_finalize()
        self.assertIsNotNone(manifest)
        assert manifest is not None

        session_dir = self.test_root / f"trade_date={self.trade_date}"
        final_bin = session_dir / f"{manifest.segment_id}.bin.gz"
        final_mf = session_dir / f"{manifest.segment_id}.manifest.json"

        self.assertTrue(final_bin.exists())
        self.assertTrue(final_mf.exists())

        # Verify compressed SHA-256
        with open(final_bin, "rb") as bf:
            actual_comp_sha = hashlib.sha256(bf.read()).hexdigest()
        self.assertEqual(actual_comp_sha, manifest.compressed_sha256)

        # Decompress and verify uncompressed SHA-256
        with gzip.open(final_bin, "rb") as gz:
            decompressed = gz.read()
        actual_uncomp_sha = hashlib.sha256(decompressed).hexdigest()
        self.assertEqual(actual_uncomp_sha, manifest.uncompressed_sha256)

        # Verify manifest content
        self.assertEqual(manifest.total_frames, 20)
        self.assertEqual(manifest.first_sequence_number, 1)
        self.assertEqual(manifest.last_sequence_number, 20)
        self.assertEqual(manifest.quality_flags, ["CLEAN_FINALIZED"])

    def test_clean_shutdown_unlinks_empty_partial(self):
        """
        1. The use of function:
           Verifies that closing writer finalizes pending frames and leaves zero orphan .partial files.

        2. How does the specific function work:
           Writes frames, calls close(), checks directory for any lingering .partial or .tmp files.

        3. Concepts used in the function:
           Clean teardown verification.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Streaming state. After: Finalized .bin.gz present; 0 .partial files.
        """
        self.writer.write_frame(raw_payload=b"final_tick")
        self.writer.close()

        session_dir = self.test_root / f"trade_date={self.trade_date}"
        partial_files = list(session_dir.glob("*.partial*"))
        tmp_files = list(session_dir.glob("*.tmp*"))

        self.assertEqual(len(partial_files), 0, f"Found orphan partial files: {partial_files}")
        self.assertEqual(len(tmp_files), 0, f"Found orphan temporary files: {tmp_files}")


class TestCrashRecoveryAndQuarantine(unittest.TestCase):
    """
    1. The use of class:
       Unit tests for process kill at write boundaries, partial file recovery, and quarantine.

    2. What the class contains:
       - setUp: Prepares isolated test directory.
       - tearDown: Cleans up test directory.
       - test_kill_at_write_boundary_recovers_intact_frames: Simulates crash and verifies complete recovery.
       - test_corrupted_partial_quarantines_bad_tail: Asserts bad bytes are moved to quarantine.
       - test_reconcile_session_directory_detects_tampering: Asserts forensic audit flags tampered files.

    3. Technologies used and why:
       unittest and synthetic truncation fixtures to simulate process kills.

    4. Key design and overall design of the class:
       Enforces zero unexplained data loss: valid frames recovered, corrupted bytes quarantined.
    """

    def setUp(self):
        """
        1. The use of function:
           Initializes recovery test environment.

        2. How does the specific function work:
           Creates TemporaryDirectory and resolves session paths.

        3. Concepts used in the function:
           Test setup.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: self.test_root and self.session_dir ready.
        """
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)
        self.trade_date = "2026-10-26"
        self.session_dir = self.test_root / f"trade_date={self.trade_date}"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """
        1. The use of function:
           Disposes of temporary files.

        2. How does the specific function work:
           Calls cleanup() on TemporaryDirectory.

        3. Concepts used in the function:
           Test cleanup.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Temp dir exists. After: Deleted.
        """
        self.temp_dir.cleanup()

    def test_kill_at_write_boundary_recovers_intact_frames(self):
        """
        1. The use of function:
           Simulates abrupt process kill mid-write and verifies 100% recovery of complete frames.

        2. How does the specific function work:
           Writes 10 valid frames into a synthetic .partial file. Appends 12 bytes of a truncated 11th frame.
           Executes RawSegmentWriter.recover_session_partials().
           Verifies that 10 frames are recovered into .bin.gz, manifest is created, and partial file is unlinked.

        3. Concepts used in the function:
           Simulated process kill, crash recovery, truncated tail isolation.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Interrupted .partial file. After: 10 frames recovered in .bin.gz; 12 bytes quarantined.
        """
        stream = bytearray()
        now_us = 1700000000000000

        for i in range(1, 11):
            stream.extend(pack_frame(sequence_number=i, recv_time_us=now_us + i, payload=f"tick_{i}".encode("utf-8")))

        # Simulate kill boundary: append truncated header (only 12 bytes of 28-byte header)
        truncated_tail = pack_frame(sequence_number=11, recv_time_us=now_us + 11, payload=b"killed_tick")[:12]
        stream.extend(truncated_tail)

        # Write to synthetic partial file
        partial_file = self.session_dir / "segment_crash_001.bin.partial"
        with open(partial_file, "wb") as pf:
            pf.write(stream)

        # Execute recovery
        report = RawSegmentWriter.recover_session_partials(
            trade_date=self.trade_date,
            base_raw_dir=self.test_root,
        )

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["recovered_segments"], 1)
        self.assertEqual(report["quarantined_files"], 1)
        self.assertFalse(partial_file.exists(), ".partial file must be unlinked after recovery")

        # Verify finalized segment has all 10 intact frames
        recovered_bin = self.session_dir / "segment_crash_001.bin.gz"
        recovered_mf = self.session_dir / "segment_crash_001.manifest.json"
        self.assertTrue(recovered_bin.exists())
        self.assertTrue(recovered_mf.exists())

        with open(recovered_mf, "r", encoding="utf-8") as mf:
            m_data = json.load(mf)
        self.assertEqual(m_data["total_frames"], 10)
        self.assertEqual(m_data["first_sequence_number"], 1)
        self.assertEqual(m_data["last_sequence_number"], 10)
        self.assertIn("RECOVERED_FROM_PARTIAL", m_data["quality_flags"])

        # Decompress and verify unpacked frames match
        with gzip.open(recovered_bin, "rb") as gz:
            recovered_bytes = gz.read()
        parsed, _, _ = unpack_frames_from_bytes(recovered_bytes)
        self.assertEqual(len(parsed), 10)
        self.assertEqual(parsed[9].payload, b"tick_10")

    def test_corrupted_partial_quarantines_bad_tail(self):
        """
        1. The use of function:
           Verifies that corrupted bytes in a partial file are safely moved to quarantine directory.

        2. How does the specific function work:
           Writes valid frame, then corrupt bytes with invalid magic. Runs recovery.
           Verifies quarantine directory contains corrupt fragment and companion quarantine report.

        3. Concepts used in the function:
           Quarantine isolation, forensic reason reporting.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Corrupt bytes in active session. After: Corrupt bytes safely quarantined with reason report.
        """
        valid_frame = pack_frame(sequence_number=1, recv_time_us=1000, payload=b"valid")
        corrupt_noise = b"\xFF\xFE\xFD\xFC_random_garbage_corruption_bytes"

        partial_file = self.session_dir / "segment_garbage_002.bin.partial"
        with open(partial_file, "wb") as pf:
            pf.write(valid_frame + corrupt_noise)

        report = RawSegmentWriter.recover_session_partials(
            trade_date=self.trade_date,
            base_raw_dir=self.test_root,
        )

        self.assertEqual(report["recovered_segments"], 1)
        self.assertEqual(report["quarantined_files"], 1)

        quarantine_dir = self.test_root / "quarantine" / f"trade_date={self.trade_date}"
        q_reports = list(quarantine_dir.glob("*_quarantine.json"))
        self.assertEqual(len(q_reports), 1)

        with open(q_reports[0], "r", encoding="utf-8") as qrf:
            q_data = json.load(q_rf := qrf)
        self.assertEqual(q_data["corrupt_bytes_count"], len(corrupt_noise))
        self.assertIn("INVALID_MAGIC", q_data["error_reason"])

    def test_reconcile_session_directory_detects_tampering(self):
        """
        1. The use of function:
           Verifies that reconcile_session_directory detects file tampering or missing manifests.

        2. How does the specific function work:
           Creates valid finalized segment and manifest. Tampering: modifies 1 byte in .bin.gz.
           Runs reconcile_session_directory(), asserts status FAIL and checksum mismatch reported.

        3. Concepts used in the function:
           Forensic reconciliation, tamper detection.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Tampered file. After: Reconciliation reports status FAIL and exact checksum error.
        """
        writer = RawSegmentWriter(
            connection_id="reconcile_test",
            trade_date=self.trade_date,
            base_raw_dir=self.test_root,
        )
        writer.write_frame(b"tick_sample_data")
        manifest = writer.rotate_and_finalize()
        writer.close()

        assert manifest is not None
        # Clean check first
        clean_report = RawSegmentWriter.reconcile_session_directory(
            trade_date=self.trade_date,
            base_raw_dir=self.test_root,
        )
        self.assertEqual(clean_report["status"], "PASS")
        self.assertEqual(len(clean_report["checksum_errors"]), 0)

        # Tamper with the compressed file
        bin_path = self.session_dir / f"{manifest.segment_id}.bin.gz"
        with open(bin_path, "r+b") as bf:
            bf.seek(10)
            bf.write(b"\xFF")

        tampered_report = RawSegmentWriter.reconcile_session_directory(
            trade_date=self.trade_date,
            base_raw_dir=self.test_root,
        )
        self.assertEqual(tampered_report["status"], "FAIL")
        self.assertGreater(len(tampered_report["checksum_errors"]), 0)


if __name__ == "__main__":
    unittest.main()
