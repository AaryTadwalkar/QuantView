"""
Unit tests for QuantView historical data ingestion workflows and offline safety audits:
- Underlying historical candle importer (Chunking, URL parameters, OHLC parsing, Checkpoints)
- Expired option candle importer (Contract mapping, OHLC parsing, Checkpoints)
- Expired expiry discoverer (Budget accounting guard, Raw payload preservation)
- Raw/canonical storage separation (Raw byte fidelity, manifest generation, no Parquet writes)
- Error handling matrix (HTTP 200, empty, 401, 429, 500, malformed)
- Checkpoint interruption and resumption
- Fixture immutability and credential protection
"""

import os
import gzip
import json
import tempfile
import unittest
import hashlib
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.ingest.import_underlying_candles_v3 import (
    UnderlyingCandleImporter,
    parse_candle_rows,
)
from tools.ingest.import_expired_option_candles import (
    ExpiredOptionImporter,
    parse_option_candles,
)
from tools.ingest.discover_expiries import (
    ExpiryContractDiscoverer,
    RequestAccountingSession,
    RequestLimitExceeded,
)


class TestUnderlyingImporter(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.staging = Path(self.tmp_dir.name) / "staging"
        self.checkpoint = Path(self.tmp_dir.name) / "checkpoints"

        self.importer = UnderlyingCandleImporter(
            token="dummy_token_never_printed",
            unit="minutes",
            interval="1",
            staging_root=self.staging,
            checkpoint_dir=self.checkpoint,
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_chunking_bounds_minutes(self):
        # 75 days should yield exactly 3 chunks (30, 30, 15)
        chunks = self.importer.build_chunks(date(2026, 1, 1), date(2026, 3, 16))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].from_date, date(2026, 1, 1))
        self.assertEqual(chunks[0].to_date, date(2026, 1, 30))
        self.assertEqual(chunks[1].from_date, date(2026, 1, 31))
        self.assertEqual(chunks[1].to_date, date(2026, 3, 1))
        self.assertEqual(chunks[2].from_date, date(2026, 3, 2))
        self.assertEqual(chunks[2].to_date, date(2026, 3, 16))

    def test_parse_candle_rows_ohlc_invariants(self):
        raw = [
            # Valid candle
            ["2026-01-20T09:15:00+05:30", 25000.0, 25050.0, 24980.0, 25020.0, 100, 0],
            # Invalid high < open
            ["2026-01-20T09:16:00+05:30", 25000.0, 24900.0, 24800.0, 24850.0, 100, 0],
            # Invalid low > close
            ["2026-01-20T09:17:00+05:30", 25000.0, 25100.0, 25050.0, 25000.0, 100, 0],
            # Negative price
            ["2026-01-20T09:18:00+05:30", -10.0, 25000.0, -20.0, 25000.0, 100, 0],
        ]
        parsed = parse_candle_rows(raw, source_tag="test_src")
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["open"], 25000.0)
        self.assertEqual(parsed[0]["high"], 25050.0)
        self.assertEqual(parsed[0]["low"], 24980.0)
        self.assertEqual(parsed[0]["close"], 25020.0)

    def test_checkpoint_roundtrip_and_resumption(self):
        state = {"completed_chunks": ["2026-01-01_2026-01-30"]}
        self.importer.save_checkpoint(state)
        loaded = self.importer.load_checkpoint()
        self.assertEqual(loaded["completed_chunks"], ["2026-01-01_2026-01-30"])

        # Running dry-run should detect that chunk 1 is already completed
        plan = self.importer.run(date(2026, 1, 1), date(2026, 3, 1), dry_run=True)
        self.assertEqual(plan["plan"][0]["status"], "ALREADY_COMPLETED")
        self.assertEqual(plan["plan"][1]["status"], "PLANNED")


class TestExpiredOptionImporter(unittest.TestCase):
    def test_parse_option_candles_mapping(self):
        contract = {
            "instrument_key": "NSE_FO|12345",
            "trading_symbol": "NIFTY25APR24C22500",
            "expiry": "2025-04-24",
            "strike_price": 22500.0,
            "instrument_type": "CE",
            "lot_size": 75,
        }
        raw_candles = [
            ["2025-04-24T09:15:00+05:30", 120.0, 135.0, 115.0, 130.0, 1500, 31200],
            # Invalid candle (high < close)
            ["2025-04-24T09:16:00+05:30", 130.0, 125.0, 110.0, 128.0, 1500, 31200],
        ]
        rows = parse_option_candles(raw_candles, contract)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["instrument_key"], "NSE_FO|12345")
        self.assertEqual(r["trading_symbol"], "NIFTY25APR24C22500")
        self.assertEqual(r["expiry"], "2025-04-24")
        self.assertEqual(r["strike"], 22500.0)
        self.assertEqual(r["option_type"], "CE")
        self.assertEqual(r["lot_size"], 75)
        self.assertEqual(r["open"], 120.0)
        self.assertEqual(r["high"], 135.0)
        self.assertEqual(r["low"], 115.0)
        self.assertEqual(r["close"], 130.0)
        self.assertEqual(r["volume"], 1500)
        self.assertEqual(r["oi"], 31200)


class TestRequestAccountingAndSafety(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.raw_root = Path(self.tmp_dir.name) / "raw"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_budget_enforcement(self):
        session = RequestAccountingSession(max_requests=1)
        self.assertEqual(session.max_requests, 1)
        self.assertEqual(session.request_count, 0)

        mock_resp = MagicMock()
        mock_resp.content = b'{"status":"success"}'
        mock_resp.status_code = 200

        with patch("requests.Session.send", return_value=mock_resp):
            session.send(MagicMock())
            self.assertEqual(session.request_count, 1)

            # Second call must raise RequestLimitExceeded immediately
            with self.assertRaises(RequestLimitExceeded):
                session.send(MagicMock())

    def test_raw_byte_fidelity_and_manifest(self):
        token = "secret_test_token_xyz"
        discoverer = ExpiryContractDiscoverer(token=token, max_budget=2, raw_root=self.raw_root)

        test_payload = b'{"status":"success","data":[{"strike_price":22500,"instrument_type":"CE"}]}'
        expected_hash = hashlib.sha256(test_payload).hexdigest()

        mock_resp = MagicMock()
        mock_resp.content = test_payload
        mock_resp.text = test_payload.decode("utf-8")
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = json.loads(test_payload)

        with patch.object(discoverer.session, "get", return_value=mock_resp) as mock_get:
            res = discoverer.query_and_archive("2025-04-24")

            # Check redirect following was explicitly disabled
            mock_get.assert_called_once()
            _, kwargs = mock_get.call_args
            self.assertFalse(kwargs.get("allow_redirects", True))

            # Verify raw response file exists and matches bit-for-bit when decompressed
            gz_path = Path(res["raw_path"])
            self.assertTrue(gz_path.exists())
            with gzip.open(gz_path, "rb") as gz:
                decompressed = gz.read()
            self.assertEqual(decompressed, test_payload)

            # Verify manifest exists and recorded SHA-256 matches
            manifest_path = Path(res["manifest_path"])
            self.assertTrue(manifest_path.exists())
            with open(manifest_path, "r", encoding="utf-8") as mf:
                manifest_data = json.load(mf)

            self.assertEqual(manifest_data["raw_sha256"], expected_hash)
            self.assertEqual(manifest_data["http_status"], 200)

            # Assert token is NEVER leaked into manifest
            manifest_str = json.dumps(manifest_data)
            self.assertNotIn("secret_test_token_xyz", manifest_str)
            self.assertNotIn("Authorization", manifest_str)

    def test_identical_bodies_distinct_manifests(self):
        # Two requests returning identical 401 bodies must both be auditable
        token = "token_abc"
        discoverer = ExpiryContractDiscoverer(token=token, max_budget=2, raw_root=self.raw_root)

        err_payload = b'{"status":"error","message":"Invalid token"}'
        mock_resp = MagicMock()
        mock_resp.content = err_payload
        mock_resp.text = err_payload.decode("utf-8")
        mock_resp.status_code = 401
        mock_resp.ok = False
        mock_resp.json.return_value = json.loads(err_payload)

        with patch.object(discoverer.session, "get", return_value=mock_resp):
            res1 = discoverer.query_and_archive("2024-04-25")
            res2 = discoverer.query_and_archive("2023-04-27")

            self.assertNotEqual(res1["manifest_path"], res2["manifest_path"])
            self.assertTrue(Path(res1["manifest_path"]).exists())
            self.assertTrue(Path(res2["manifest_path"]).exists())

    def test_http_error_matrix_handling(self):
        token = "token_123"
        discoverer = ExpiryContractDiscoverer(token=token, max_budget=10, raw_root=self.raw_root)

        cases = [
            (200, b'{"status":"success","data":[]}', "SUCCESS", 0),
            (401, b'{"status":"error","message":"Invalid token"}', "HTTP_401", 0),
            (429, b'{"status":"error","message":"Too Many Requests"}', "HTTP_429", 0),
            (500, b'{"status":"error","message":"Internal Server Error"}', "HTTP_500", 0),
            (200, b'NOT_VALID_JSON', "PARSE_ERROR", 0),
        ]

        for code, body, expected_status, expected_count in cases:
            mock_resp = MagicMock()
            mock_resp.content = body
            mock_resp.text = body.decode("utf-8", errors="ignore")
            mock_resp.status_code = code
            mock_resp.ok = (code == 200)
            try:
                mock_resp.json.return_value = json.loads(body)
            except Exception:
                mock_resp.json.side_effect = ValueError("Malformed JSON")

            with patch.object(discoverer.session, "get", return_value=mock_resp):
                res = discoverer.query_and_archive("2025-04-24")
                self.assertEqual(res["http_status"], code)
                self.assertEqual(res["contract_count"], expected_count)
                # Raw bytes must always be preserved
                self.assertTrue(Path(res["raw_path"]).exists())

    def test_fail_fast_on_blocking_error(self):
        """
        1. The use of function:
           Tests that execute_probe immediately stops on blocking HTTP statuses (e.g. 401).

        2. How does the specific function work:
           Configures a discoverer with 5 dates and budget=5. Mocks the HTTP client to return 401.
           Verifies that only 1 request is dispatched before the probe halts.

        3. Concepts used in the function:
           Fail-fast safety verification, monotonic request accounting.

        4. Places where this function is imported and used:
           Run by unittest test runner.

        5. Final output of the function, before and after:
           Before: Unverified probe loop. After: Verified fail-fast halt on blocking error.
        """
        token = "token_fail_fast"
        discoverer = ExpiryContractDiscoverer(token=token, max_budget=5, raw_root=self.raw_root)
        mock_resp = MagicMock()
        mock_resp.content = b'{"status":"error","message":"Invalid token"}'
        mock_resp.text = '{"status":"error","message":"Invalid token"}'
        mock_resp.status_code = 401
        mock_resp.ok = False
        mock_resp.json.return_value = {"status": "error", "message": "Invalid token"}

        with patch("requests.Session.send", return_value=mock_resp):
            dates = ["2024-12-26", "2024-06-27", "2023-12-28", "2023-06-28", "2022-12-29"]
            results, _ = discoverer.execute_probe(dates, evidence_file=str(self.raw_root / "test_ev.md"))
            self.assertEqual(len(results), 1)
            self.assertEqual(discoverer.session.request_count, 1)


class TestRepositorySafetyInvariants(unittest.TestCase):
    def test_april24_fixture_unmodified(self):
        fixture_path = Path("Data/historical/options/nifty_options_1m_2025-04-24_2025-04-24.csv")
        self.assertTrue(fixture_path.exists())
        # The expected SHA-256 hash verified in M0-06
        expected_prefix = "c149b18d2f5f7b1c"
        hasher = hashlib.sha256()
        with open(fixture_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        actual_hash = hasher.hexdigest()
        self.assertTrue(actual_hash.startswith(expected_prefix))

    def test_no_parquet_published_by_ingest_tools(self):
        staging = Path("staging")
        if staging.exists():
            parquets = list(staging.rglob("*.parquet"))
            self.assertEqual(len(parquets), 0)


if __name__ == "__main__":
    unittest.main()
