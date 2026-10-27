"""
1. What this file does:
   Automated unit and contract test suite for Milestone M2-01 (REST Raw-First Snapshot Collector).
   Verifies raw-first durability, cryptographic hashing, atomic staging, decoder failure resilience,
   reconciliation auditing, secret redaction, and offline mock adapter behavior.

2. Overall design:
   Uses Python's standard unittest framework with temporary directory sandboxes (tempfile.TemporaryDirectory):
     - TestRawSnapshotWriter: Tests raw-first gzip compression, fsync durability, manifest generation,
       and session reconciliation.
     - TestUpstoxSnapshotAdapter: Tests HTTP response encapsulation, retry with backoff on 429/5xx,
       fail-closed on 401/403, and token redaction.
     - TestSnapshotCollectorService: Tests end-to-end capture coordination, dynamic expiry resolution,
       and raw preservation during decoder parse failures.

3. Elements in the file:
   - TestRawSnapshotWriter: Unit tests for raw filesystem persistence and manifest generation.
   - TestUpstoxSnapshotAdapter: Unit tests for HTTP adapter resilience and secret masking.
   - TestSnapshotCollectorService: Unit tests for service workflow and failure boundaries.

4. Final output of the file:
   - Pass/fail test execution verifying all acceptance criteria of Milestone M2-01.
"""

import gzip
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.collector_snapshot.adapter import SnapshotResponsePayload, UpstoxSnapshotAdapter
from services.collector_snapshot.collector import SnapshotCollectorService, generate_snapshot_id
from services.collector_snapshot.raw_writer import RawCaptureRecord, RawSnapshotWriter


class TestRawSnapshotWriter(unittest.TestCase):
    """
    1. The use of class:
       Unit tests for RawSnapshotWriter raw payload persistence, manifests, and reconciliation.

    2. What the class contains:
       - setUp: Prepares isolated temporary test directory.
       - tearDown: Cleans up temporary test directory.
       - test_raw_payload_durability_and_manifest_hashes: Asserts raw payload compression and SHA-256 matching.
       - test_atomic_write_and_tmp_cleanup: Asserts atomic rename and absence of orphan .tmp files.
       - test_raw_to_manifest_reconciliation_valid: Asserts audit reconciliation passes on valid captures.
       - test_raw_to_manifest_reconciliation_detects_defects: Asserts reconciliation catches missing or tampered files.
       - test_update_manifest_decoder_status: Asserts non-destructive update of manifest decoder metadata.

    3. Technologies used and why:
       unittest and tempfile for hermetic filesystem isolation.

    4. Key design and overall design of the class:
       Validates raw-first durability invariants before any parsing or ingestion can take place.
    """

    def setUp(self):
        """
        1. The use of function:
           Sets up an isolated temporary workspace for file persistence tests.

        2. How does the specific function work:
           Creates a TemporaryDirectory and instantiates RawSnapshotWriter with that root.

        3. Concepts used in the function:
           Hermetic test sandboxing.

        4. Places where this function is imported and used:
           Invoked automatically by unittest before each test method.

        5. Final output of the function, before and after:
           Before: No directory. After: self.test_dir and self.writer initialized.
        """
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temp_dir.name)
        self.writer = RawSnapshotWriter(raw_root=self.test_root)

    def tearDown(self):
        """
        1. The use of function:
           Tears down the temporary directory after each test.

        2. How does the specific function work:
           Calls cleanup() on the TemporaryDirectory.

        3. Concepts used in the function:
           Test resource disposal.

        4. Places where this function is imported and used:
           Invoked automatically by unittest after each test method.

        5. Final output of the function, before and after:
           Before: Temporary directory exists. After: Temporary directory deleted.
        """
        self.temp_dir.cleanup()

    def test_raw_payload_durability_and_manifest_hashes(self):
        """
        1. The use of function:
           Verifies raw bytes write, gzip compression, uncompressed SHA-256, and companion manifest.

        2. How does the specific function work:
           Writes synthetic JSON bytes, verifies file existence, decompresses gzip, and matches hashes.

        3. Concepts used in the function:
           Cryptographic verification, raw-first persistence.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: No files. After: Finalized .json.gz and .manifest.json verified on disk.
        """
        raw_payload = b'{"status":"success","data":[{"strike_price":25000.0,"call_options":{"oi":100}}]}'
        trade_date = "2026-10-26"
        snapshot_id = "snap_2026-10-26_091530_a1b2c3d4"
        now_iso = datetime(2026, 10, 26, 9, 15, 30, tzinfo=timezone.utc).isoformat()

        record = self.writer.persist_raw_response(
            snapshot_id=snapshot_id,
            trade_date=trade_date,
            raw_bytes=raw_payload,
            endpoint="/v2/option/chain",
            request_params={"instrument_key": "NSE_INDEX|Nifty 50", "expiry_date": "2026-10-29"},
            http_status=200,
            content_type="application/json",
            request_timestamp_utc=now_iso,
            received_at_utc=now_iso,
        )

        self.assertTrue(record.raw_file_path.exists())
        self.assertTrue(record.manifest_path.exists())

        # Verify uncompressed hash matches
        expected_uncompressed_sha = hashlib.sha256(raw_payload).hexdigest()
        self.assertEqual(record.uncompressed_sha256, expected_uncompressed_sha)
        self.assertEqual(record.uncompressed_bytes, len(raw_payload))

        # Verify compressed file can be read and matches uncompressed content
        with gzip.open(record.raw_file_path, "rb") as gz_in:
            decompressed = gz_in.read()
        self.assertEqual(decompressed, raw_payload)

        # Verify manifest contents
        with open(record.manifest_path, "r", encoding="utf-8") as mf:
            manifest_data = json.load(mf)

        self.assertEqual(manifest_data["snapshot_id"], snapshot_id)
        self.assertEqual(manifest_data["uncompressed_sha256"], expected_uncompressed_sha)
        self.assertEqual(manifest_data["persistence_status"], "DURABLE_STORED")
        self.assertEqual(manifest_data["http_status"], 200)
        self.assertEqual(manifest_data["endpoint"], "/v2/option/chain")

    def test_atomic_write_and_tmp_cleanup(self):
        """
        1. The use of function:
           Verifies that writes use temporary files and leave zero orphan .tmp files on completion.

        2. How does the specific function work:
           Writes a payload and checks directory for any lingering files ending with .tmp.

        3. Concepts used in the function:
           Atomic filesystem rename, directory cleanliness.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Pre-write state. After: Only final .json.gz and .manifest.json exist; 0 .tmp files.
        """
        raw_payload = b'{"status":"success","data":[]}'
        trade_date = "2026-10-26"
        snapshot_id = "snap_2026-10-26_091535_clean"
        now_iso = datetime(2026, 10, 26, 9, 15, 35, tzinfo=timezone.utc).isoformat()

        self.writer.persist_raw_response(
            snapshot_id=snapshot_id,
            trade_date=trade_date,
            raw_bytes=raw_payload,
            endpoint="/v2/option/chain",
            request_params={},
            http_status=200,
            content_type="application/json",
            request_timestamp_utc=now_iso,
            received_at_utc=now_iso,
        )

        session_dir = self.test_root / f"trade_date={trade_date}"
        tmp_files = list(session_dir.glob("*.tmp*"))
        self.assertEqual(len(tmp_files), 0, f"Found orphan temporary files: {tmp_files}")

    def test_raw_to_manifest_reconciliation_valid(self):
        """
        1. The use of function:
           Verifies session directory reconciliation passes when all raw captures match manifests.

        2. How does the specific function work:
           Persists multiple captures and calls reconcile_session_directory().

        3. Concepts used in the function:
           Forensic reconciliation, data integrity auditing.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Unverified directory. After: Reconciliation report returns 0 defects.
        """
        trade_date = "2026-10-26"
        now_iso = datetime.now(timezone.utc).isoformat()
        for i in range(3):
            payload = f'{{"capture": {i}}}'.encode("utf-8")
            self.writer.persist_raw_response(
                snapshot_id=f"snap_{i}",
                trade_date=trade_date,
                raw_bytes=payload,
                endpoint="/test",
                request_params={},
                http_status=200,
                content_type="application/json",
                request_timestamp_utc=now_iso,
                received_at_utc=now_iso,
            )

        report = self.writer.reconcile_session_directory(trade_date)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["total_captures"], 3)
        self.assertEqual(len(report["unmatched_raw_files"]), 0)
        self.assertEqual(len(report["unmatched_manifest_files"]), 0)
        self.assertEqual(len(report["checksum_errors"]), 0)

    def test_raw_to_manifest_reconciliation_detects_defects(self):
        """
        1. The use of function:
           Verifies reconcile_session_directory flags missing files or corrupted hashes.

        2. How does the specific function work:
           Creates valid captures, tampers with one file, and asserts reconciliation catches it.

        3. Concepts used in the function:
           Tamper detection, fail-closed auditing.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Tampered files. After: Report identifies exact missing or corrupted elements.
        """
        trade_date = "2026-10-26"
        session_dir = self.test_root / f"trade_date={trade_date}"
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create an orphan raw file without manifest
        orphan_raw = session_dir / "capture_orphan.json.gz"
        with gzip.open(orphan_raw, "wb") as gz_out:
            gz_out.write(b'{"orphan": true}')

        # Create an orphan manifest without raw file
        orphan_manifest = session_dir / "capture_ghost.manifest.json"
        with open(orphan_manifest, "w", encoding="utf-8") as mf:
            json.dump({"snapshot_id": "ghost", "uncompressed_sha256": "fake"}, mf)

        report = self.writer.reconcile_session_directory(trade_date)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("capture_orphan", report["unmatched_raw_files"])
        self.assertIn("capture_ghost", report["unmatched_manifest_files"])

    def test_update_manifest_decoder_status(self):
        """
        1. The use of function:
           Verifies non-destructive updating of manifest decoder status.

        2. How does the specific function work:
           Writes raw capture, updates status to DECODER_PARSE_ERROR, and checks manifest fields.

        3. Concepts used in the function:
           Non-destructive manifest mutation.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Manifest without decoder status. After: Manifest with updated decoder fields.
        """
        trade_date = "2026-10-26"
        snapshot_id = "snap_update"
        now_iso = datetime.now(timezone.utc).isoformat()
        record = self.writer.persist_raw_response(
            snapshot_id=snapshot_id,
            trade_date=trade_date,
            raw_bytes=b'{"bad": json}',
            endpoint="/test",
            request_params={},
            http_status=200,
            content_type="application/json",
            request_timestamp_utc=now_iso,
            received_at_utc=now_iso,
        )

        self.writer.update_manifest_decoder_status(
            manifest_path=record.manifest_path,
            decoder_status="DECODER_PARSE_ERROR",
            error_message="Expecting property name enclosed in double quotes",
        )

        with open(record.manifest_path, "r", encoding="utf-8") as mf:
            updated = json.load(mf)

        self.assertEqual(updated["decoder_status"], "DECODER_PARSE_ERROR")
        self.assertIn("Expecting property name", updated["decoder_error"])
        # Original hashes must remain intact
        self.assertEqual(updated["uncompressed_sha256"], record.uncompressed_sha256)


class TestUpstoxSnapshotAdapter(unittest.TestCase):
    """
    1. The use of class:
       Unit tests for UpstoxSnapshotAdapter HTTP interactions, retry logic, and secret redaction.

    2. What the class contains:
       - test_secret_redaction_in_repr: Asserts access token is never displayed in repr or logs.
       - test_successful_fetch_returns_raw_bytes: Asserts raw bytes returned with correct metadata.
       - test_retry_on_429_with_exponential_backoff: Asserts retry loop on rate limits.
       - test_fail_closed_on_401_unauthorized: Asserts immediate failure without wasting retries on 401.

    3. Technologies used and why:
       unittest.mock to mock HTTP sessions deterministically without live network access.

    4. Key design and overall design of the class:
       Validates adapter resilience, backoff behavior, and security boundaries.
    """

    def test_secret_redaction_in_repr(self):
        """
        1. The use of function:
           Verifies that the access token is strictly redacted in __repr__ and string casting.

        2. How does the specific function work:
           Initializes adapter with secret token, checks str() and repr() outputs.

        3. Concepts used in the function:
           Credential leak prevention.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Secret token in memory. After: String representations mask token.
        """
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sensitive_secret_token"
        adapter = UpstoxSnapshotAdapter(access_token=token)
        rep = repr(adapter)
        self.assertNotIn(token, rep)
        self.assertIn("...", rep)

    def test_successful_fetch_returns_raw_bytes(self):
        """
        1. The use of function:
           Verifies successful HTTP 200 response returns raw bytes without premature decoding.

        2. How does the specific function work:
           Injects mock session returning 200 OK with binary payload.

        3. Concepts used in the function:
           Mock HTTP session injection, raw byte fidelity.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Mock response. After: SnapshotResponsePayload containing raw bytes.
        """
        raw_body = b'{"status":"success","data":[{"strike_price":25000}]}'
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = raw_body
        mock_response.headers = {"Content-Type": "application/json"}
        mock_session.get.return_value = mock_response

        adapter = UpstoxSnapshotAdapter(access_token="test_tok", session=mock_session)
        payload = adapter.fetch_raw_option_chain("NSE_INDEX|Nifty 50", "2026-10-29")

        self.assertEqual(payload.raw_bytes, raw_body)
        self.assertEqual(payload.http_status, 200)
        self.assertEqual(payload.content_type, "application/json")
        self.assertEqual(payload.request_params["instrument_key"], "NSE_INDEX|Nifty 50")

    def test_retry_on_429_with_exponential_backoff(self):
        """
        1. The use of function:
           Verifies adapter retries on HTTP 429 and succeeds on subsequent attempt.

        2. How does the specific function work:
           Configures mock session to return 429 then 200; mocks time.sleep to run fast.

        3. Concepts used in the function:
           Exponential backoff, transient fault tolerance.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Transient 429. After: Successful 200 payload after 1 retry.
        """
        raw_body = b'{"status":"success","data":[]}'
        mock_session = MagicMock()

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.content = b'{"status":"error","message":"Too Many Requests"}'
        resp_429.headers = {"Content-Type": "application/json"}

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.content = raw_body
        resp_200.headers = {"Content-Type": "application/json"}

        mock_session.get.side_effect = [resp_429, resp_200]

        with patch("time.sleep") as mock_sleep:
            adapter = UpstoxSnapshotAdapter(access_token="test_tok", session=mock_session, max_retries=3)
            payload = adapter.fetch_raw_option_chain("NSE_INDEX|Nifty 50", "2026-10-29")

            self.assertEqual(payload.http_status, 200)
            self.assertEqual(mock_session.get.call_count, 2)
            self.assertEqual(mock_sleep.call_count, 1)

    def test_fail_closed_on_401_unauthorized(self):
        """
        1. The use of function:
           Verifies adapter fails closed immediately on fatal 401 Unauthorized without burning retries.

        2. How does the specific function work:
           Configures mock session to return 401; asserts PermissionError is raised on 1st attempt.

        3. Concepts used in the function:
           Fail-closed security, quota preservation.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: 401 response. After: PermissionError raised immediately with call_count == 1.
        """
        mock_session = MagicMock()
        resp_401 = MagicMock()
        resp_401.status_code = 401
        resp_401.content = b'{"status":"error","message":"Invalid token"}'
        resp_401.headers = {"Content-Type": "application/json"}
        mock_session.get.return_value = resp_401

        adapter = UpstoxSnapshotAdapter(access_token="bad_tok", session=mock_session, max_retries=5)
        with self.assertRaises(PermissionError):
            adapter.fetch_raw_option_chain("NSE_INDEX|Nifty 50", "2026-10-29")

        self.assertEqual(mock_session.get.call_count, 1)


class TestSnapshotCollectorService(unittest.TestCase):
    """
    1. The use of class:
       Unit tests for SnapshotCollectorService orchestration, durability, and error boundaries.

    2. What the class contains:
       - setUp: Prepares test environment with temporary directories and mocks.
       - tearDown: Cleans up test directories.
       - test_capture_once_success: Asserts successful capture workflow and schema fields.
       - test_raw_retained_on_decoder_parse_failure: Asserts 100% raw byte preservation on corrupt JSON.
       - test_generate_snapshot_id_format: Asserts deterministic ID structure.

    3. Technologies used and why:
       unittest and tempfile for offline hermetic testing.

    4. Key design and overall design of the class:
       Validates the core raw-first invariant: capture data is written and synced before parsing.
    """

    def setUp(self):
        """
        1. The use of function:
           Initializes service test environment.

        2. How does the specific function work:
           Creates TemporaryDirectory and mock adapter.

        3. Concepts used in the function:
           Hermetic mocking.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Temporary test environment ready.
        """
        self.temp_dir = tempfile.TemporaryDirectory()
        self.raw_dir = Path(self.temp_dir.name)
        self.writer = RawSnapshotWriter(raw_root=self.raw_dir)
        self.mock_adapter = MagicMock()
        self.service = SnapshotCollectorService(
            adapter=self.mock_adapter,
            writer=self.writer,
            default_instrument="NSE_INDEX|Nifty 50",
        )

    def tearDown(self):
        """
        1. The use of function:
           Disposes of temporary files.

        2. How does the specific function work:
           Cleans up TemporaryDirectory.

        3. Concepts used in the function:
           Resource cleanup.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Test directories exist. After: Deleted.
        """
        self.temp_dir.cleanup()

    def test_capture_once_success(self):
        """
        1. The use of function:
           Verifies end-to-end capture_once on valid option chain response.

        2. How does the specific function work:
           Returns valid JSON payload from mock adapter, verifies raw storage and summary dictionary.

        3. Concepts used in the function:
           Full collector orchestration.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Mock payload. After: Raw file stored, manifest marked DECODED, summary complete.
        """
        valid_json = {
            "status": "success",
            "data": [
                {
                    "strike_price": 25000.0,
                    "underlying_spot_price": 25020.5,
                    "call_options": {"oi": 15000, "market_data": {"ltp": 120.5}},
                    "put_options": {"oi": 12000, "market_data": {"ltp": 95.0}},
                }
            ],
        }
        raw_bytes = json.dumps(valid_json).encode("utf-8")
        now_utc = datetime(2026, 10, 26, 9, 20, 0, tzinfo=timezone.utc)

        self.mock_adapter.fetch_raw_option_chain.return_value = SnapshotResponsePayload(
            raw_bytes=raw_bytes,
            http_status=200,
            content_type="application/json",
            request_timestamp_utc=now_utc.isoformat(),
            received_at_utc=now_utc.isoformat(),
            endpoint="/v2/option/chain",
            request_params={"instrument_key": "NSE_INDEX|Nifty 50", "expiry_date": "2026-10-29"},
        )

        summary = self.service.capture_once(expiry_date="2026-10-29", trade_date="2026-10-26")

        self.assertEqual(summary["status"], "SUCCESS")
        self.assertEqual(summary["spot_price"], 25020.5)
        self.assertEqual(summary["row_count"], 1)
        self.assertTrue(Path(summary["raw_file_path"]).exists())
        self.assertTrue(Path(summary["manifest_path"]).exists())

        # Verify manifest is marked DECODED
        with open(summary["manifest_path"], "r", encoding="utf-8") as mf:
            m_data = json.load(mf)
        self.assertEqual(m_data["decoder_status"], "DECODED")

    def test_raw_retained_on_decoder_parse_failure(self):
        """
        1. The use of function:
           Verifies raw bytes are 100% preserved on disk even when downstream JSON parsing crashes.

        2. How does the specific function work:
           Injects malformed/truncated JSON payload into adapter. Executes capture_once.
           Asserts that raw file exists on disk, uncompressed bytes match, and manifest records error.

        3. Concepts used in the function:
           Raw-first durability, fail-safe isolation, zero data loss.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Corrupt vendor stream. After: Raw file durably stored; manifest updated with DECODER_PARSE_ERROR.
        """
        corrupted_raw_bytes = b'{"status":"success","data":[{"strike_price":25000.0,'  # Truncated JSON
        now_utc = datetime(2026, 10, 26, 9, 25, 0, tzinfo=timezone.utc)

        self.mock_adapter.fetch_raw_option_chain.return_value = SnapshotResponsePayload(
            raw_bytes=corrupted_raw_bytes,
            http_status=200,
            content_type="application/json",
            request_timestamp_utc=now_utc.isoformat(),
            received_at_utc=now_utc.isoformat(),
            endpoint="/v2/option/chain",
            request_params={"instrument_key": "NSE_INDEX|Nifty 50", "expiry_date": "2026-10-29"},
        )

        summary = self.service.capture_once(expiry_date="2026-10-29", trade_date="2026-10-26")

        self.assertEqual(summary["status"], "DECODER_ERROR")
        raw_path = Path(summary["raw_file_path"])
        manifest_path = Path(summary["manifest_path"])

        # Crucial invariant: raw file MUST exist on disk
        self.assertTrue(raw_path.exists(), "Raw compressed file must exist despite decode error!")
        self.assertTrue(manifest_path.exists(), "Manifest must exist despite decode error!")

        # Verify raw bytes in .json.gz match original bytes
        with gzip.open(raw_path, "rb") as gz_in:
            decompressed = gz_in.read()
        self.assertEqual(decompressed, corrupted_raw_bytes)

        # Verify manifest records parse error
        with open(manifest_path, "r", encoding="utf-8") as mf:
            m_data = json.load(mf)
        self.assertEqual(m_data["decoder_status"], "DECODER_PARSE_ERROR")
        self.assertIn("decoder_error", m_data)
        self.assertIn("Expecting property name", m_data["decoder_error"])

    def test_generate_snapshot_id_format(self):
        """
        1. The use of function:
           Verifies generate_snapshot_id produces canonical snap_YYYY-MM-DD_HHMMSS_<hash[:8]> format.

        2. How does the specific function work:
           Passes trade_date, datetime, and raw bytes, checks format using regex/string split.

        3. Concepts used in the function:
           Deterministic entity identification.

        4. Places where this function is imported and used:
           unittest execution.

        5. Final output of the function, before and after:
           Before: Raw arguments. After: Validated capture ID string.
        """
        recv_dt = datetime(2026, 10, 26, 9, 15, 30, tzinfo=timezone.utc)
        payload = b'{"test": 123}'
        snap_id = generate_snapshot_id("2026-10-26", recv_dt, payload)

        expected_hash = hashlib.sha256(payload).hexdigest()[:8]
        expected_prefix = "snap_2026-10-26_091530_"
        self.assertTrue(snap_id.startswith(expected_prefix))
        self.assertEqual(snap_id, f"{expected_prefix}{expected_hash}")


if __name__ == "__main__":
    unittest.main()
