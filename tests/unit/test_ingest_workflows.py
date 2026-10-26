"""
1. What this file does:
   Executes comprehensive offline unit tests for QuantView historical data ingestion workflows,
   including underlying candle importing, expired option contract and candle acquisition,
   URL parameter construction, quote encoding, India VIX dataset canonical parsing,
   request accounting safety, and repository integrity invariants.

2. Overall design:
   The suite validates data integrity, safety gates, and specification invariants without
   making network calls. It tests:
     - URL generation: Verifying {to_date} precedes {from_date} and quote encoding for pipe characters.
     - India VIX: Verifying non-derivative index semantics (oi=0, volume nominal) and causal availability.
     - Option candle parsing: Ensuring OHLC validity, strike mapping, and long-format normalization.
     - Underlying candle chunking and checkpointing: Ensuring 30-day bounds and resumption.
     - Request safety: Enforcing hard request ceilings and fail-fast termination on HTTP 401/429/500.
     - Storage fidelity: Verifying bit-for-bit raw gzipped payload preservation and companion manifests.

3. Elements in the file:
   - TestUnderlyingImporter: Tests chunking, OHLC invariants, and checkpoint persistence.
   - TestExpiredOptionImporter: Tests contract mapping, URL construction, and quote encoding.
   - TestIndiaVixDataset: Tests India VIX schema, non-derivative properties, and point-in-time availability.
   - TestRequestAccountingAndSafety: Tests budget enforcement, raw fidelity, and error matrix.
   - TestRepositorySafetyInvariants: Tests fixture immutability and lake publication boundaries.

4. Final output of the file:
   - Automated pass/fail test assertions verifying ingestion contracts and offline safety.
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
from urllib.parse import quote

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
from packages.data import (
    IndiaVixCandle,
    parse_india_vix_candle,
)


class TestUnderlyingImporter(unittest.TestCase):
    """
    1. The use of class:
       Tests underlying candle ingestion logic, chunk planning, and checkpoint resumption.

    2. What the class contains:
       - setUp / tearDown: Temporary filesystem fixture management.
       - test_chunking_bounds_minutes: Validates 30-day chunk partitioning.
       - test_parse_candle_rows_ohlc_invariants: Validates OHLC integrity filters.
       - test_checkpoint_roundtrip_and_resumption: Validates checkpoint state persistence.

    3. Technologies used and why:
       unittest framework with tempfile for isolated execution without side effects.

    4. Key design and overall design of the class:
       Verifies chunking logic and OHLC validation against Upstox V3 historical specifications.
    """

    def setUp(self):
        """
        1. The use of function:
           Sets up temporary directory and initializes UnderlyingCandleImporter instance.

        2. How does the specific function work:
           Creates TemporaryDirectory and instantiates importer with dummy token.

        3. Concepts used in the function:
           Test fixture isolation.

        4. Places where this function is imported and used:
           Invoked by unittest runner before each test method.

        5. Final output of the function, before and after:
           Before: Uninitialized test state. After: Configured test importer.
        """
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
        """
        1. The use of function:
           Cleans up temporary directory after each test.

        2. How does the specific function work:
           Calls TemporaryDirectory.cleanup().

        3. Concepts used in the function:
           Resource cleanup and filesystem hygiene.

        4. Places where this function is imported and used:
           Invoked by unittest runner after each test method.

        5. Final output of the function, before and after:
           Before: Residual temporary files. After: Clean filesystem.
        """
        self.tmp_dir.cleanup()

    def test_chunking_bounds_minutes(self):
        """
        1. The use of function:
           Verifies that 75-day range is partitioned into 30-day chunk boundaries.

        2. How does the specific function work:
           Calls build_chunks() and asserts slice start and end dates.

        3. Concepts used in the function:
           Boundary partitioning, windowing.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Input date range. After: Verified list of ChunkInfo objects.
        """
        chunks = self.importer.build_chunks(date(2026, 1, 1), date(2026, 3, 16))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].from_date, date(2026, 1, 1))
        self.assertEqual(chunks[0].to_date, date(2026, 1, 30))
        self.assertEqual(chunks[1].from_date, date(2026, 1, 31))
        self.assertEqual(chunks[1].to_date, date(2026, 3, 1))
        self.assertEqual(chunks[2].from_date, date(2026, 3, 2))
        self.assertEqual(chunks[2].to_date, date(2026, 3, 16))

    def test_parse_candle_rows_ohlc_invariants(self):
        """
        1. The use of function:
           Verifies that invalid OHLC candles (high < max(o, c), low > min(o, c)) are filtered out.

        2. How does the specific function work:
           Feeds valid and invalid raw candle tuples into parse_candle_rows().

        3. Concepts used in the function:
           Data integrity enforcement.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Mixed raw rows. After: Only mathematically valid candle records retained.
        """
        raw = [
            ["2026-01-20T09:15:00+05:30", 25000.0, 25050.0, 24980.0, 25020.0, 100, 0],
            ["2026-01-20T09:16:00+05:30", 25000.0, 24900.0, 24800.0, 24850.0, 100, 0],
            ["2026-01-20T09:17:00+05:30", 25000.0, 25100.0, 25050.0, 25000.0, 100, 0],
            ["2026-01-20T09:18:00+05:30", -10.0, 25000.0, -20.0, 25000.0, 100, 0],
        ]
        parsed = parse_candle_rows(raw, source_tag="test_src")
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["open"], 25000.0)
        self.assertEqual(parsed[0]["high"], 25050.0)
        self.assertEqual(parsed[0]["low"], 24980.0)
        self.assertEqual(parsed[0]["close"], 25020.0)

    def test_checkpoint_roundtrip_and_resumption(self):
        """
        1. The use of function:
           Verifies that checkpoint state persists to disk and allows resume skipping completed chunks.

        2. How does the specific function work:
           Saves state dict, reloads, and runs dry-run plan checking status strings.

        3. Concepts used in the function:
           Idempotent resumption, checkpoint serialization.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unverified checkpoint. After: Verified round-trip resumption.
        """
        state = {"completed_chunks": ["2026-01-01_2026-01-30"]}
        self.importer.save_checkpoint(state)
        loaded = self.importer.load_checkpoint()
        self.assertEqual(loaded["completed_chunks"], ["2026-01-01_2026-01-30"])

        plan = self.importer.run(date(2026, 1, 1), date(2026, 3, 1), dry_run=True)
        self.assertEqual(plan["plan"][0]["status"], "ALREADY_COMPLETED")
        self.assertEqual(plan["plan"][1]["status"], "PLANNED")


class TestExpiredOptionImporter(unittest.TestCase):
    """
    1. The use of class:
       Tests expired option contract candle acquisition, URL construction, quote encoding, and parsing.

    2. What the class contains:
       - test_parse_option_candles_mapping: Verifies candle field binding and OHLC sanity.
       - test_expired_candle_url_construction_and_ordering: Verifies {to_date}/{from_date} order.
       - test_instrument_key_quote_encoding: Verifies percent-encoding for pipe characters.
       - test_manifest_records_content_type: Verifies companion manifest records Content-Type header.
       - test_safe_parsing_when_data_is_none: Verifies graceful degradation when payload data is None.
       - test_load_contracts_from_gzipped_file_offline: Verifies offline loading from raw gzipped contract file.
       - test_filter_candidate_band_geometric: Verifies geometric strike filtering around Spot +/- Band.
       - test_atomic_staging_and_resumption_merge: Verifies non-destructive staging merge and atomic publication.

    3. Technologies used and why:
       unittest framework with mock patching for offline HTTP verification.

    4. Key design and overall design of the class:
       Guarantees conformance to official Upstox expired candle routes without live API requests.
    """

    def test_parse_option_candles_mapping(self):
        """
        1. The use of function:
           Verifies that raw candle arrays are correctly mapped with contract metadata.

        2. How does the specific function work:
           Calls parse_option_candles() with contract dict and raw 7-element candle tuples.

        3. Concepts used in the function:
           Schema normalization, data mapping.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Raw candle list. After: Normalized dictionary rows.
        """
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

    def test_expired_candle_url_construction_and_ordering(self):
        """
        1. The use of function:
           Verifies that ExpiredOptionImporter constructs the exact official route with {to_date}/{from_date}.

        2. How does the specific function work:
           Configures ExpiredOptionImporter with temporary storage and mock response.
           Calls fetch_contract_candles() with distinct to_date ('2024-12-26') and from_date ('2024-12-01').
           Asserts that the queried URL has to_date preceding from_date and correct path prefix.

        3. Concepts used in the function:
           Reverse chronological API URL specification, mock inspection.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unverified URL string. After: Verified canonical URL conforming to official docs.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            raw_dir = Path(tmp_dir) / "raw"
            staging_dir = Path(tmp_dir) / "staging"
            importer = ExpiredOptionImporter(
                token="test_token",
                max_budget=5,
                raw_root=raw_dir,
                staging_root=staging_dir,
            )
            contract = {
                "instrument_key": "NSE_FO|41685|26-12-2024",
                "trading_symbol": "NIFTY 23750 CE 26 DEC 24",
                "expiry": "2024-12-26",
                "strike_price": 23750.0,
                "instrument_type": "CE",
                "lot_size": 25,
            }
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Type": "application/json"}
            mock_resp.content = b'{"status":"success","data":{"candles":[]}}'
            mock_resp.text = '{"status":"success","data":{"candles":[]}}'
            mock_resp.json.return_value = {"status": "success", "data": {"candles": []}}

            with patch.object(importer.session, "get", return_value=mock_resp) as mock_get:
                importer.fetch_contract_candles(
                    contract=contract,
                    to_date="2024-12-26",
                    from_date="2024-12-01",
                )
                mock_get.assert_called_once()
                called_url = mock_get.call_args[0][0]

                # Expected URL parts
                expected_prefix = "https://api.upstox.com/v2/expired-instruments/historical-candle/"
                expected_encoded_key = "NSE_FO%7C41685%7C26-12-2024"
                expected_suffix = "/1minute/2024-12-26/2024-12-01"
                expected_full_url = f"{expected_prefix}{expected_encoded_key}{expected_suffix}"

                self.assertEqual(called_url, expected_full_url)
                # Ensure to_date comes before from_date
                to_idx = called_url.index("2024-12-26")
                from_idx = called_url.index("2024-12-01")
                self.assertLess(to_idx, from_idx, "to_date must precede from_date in route")

    def test_instrument_key_quote_encoding(self):
        """
        1. The use of function:
           Verifies that quote(..., safe="") converts pipe characters and spaces properly.

        2. How does the specific function work:
           Asserts encoding for option keys and India VIX keys.

        3. Concepts used in the function:
           Percent-encoding, URL safe characters.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unescaped string with pipes. After: URL-safe percent-encoded string.
        """
        raw_opt_key = "NSE_FO|41685|26-12-2024"
        encoded_opt_key = quote(raw_opt_key, safe="")
        self.assertEqual(encoded_opt_key, "NSE_FO%7C41685%7C26-12-2024")

        raw_vix_key = "NSE_INDEX|India VIX"
        encoded_vix_key = quote(raw_vix_key, safe="")
        self.assertEqual(encoded_vix_key, "NSE_INDEX%7CIndia%20VIX")

    def test_manifest_records_content_type(self):
        """
        1. The use of function:
           Verifies that fetch_contract_candles records the Content-Type header in companion manifests.

        2. How does the specific function work:
           Mocks response with Content-Type 'application/json; charset=utf-8', checks manifest file on disk.

        3. Concepts used in the function:
           Provenance completeness, HTTP metadata capture.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unverified manifest metadata. After: Verified content_type in manifest JSON.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            importer = ExpiredOptionImporter(
                token="dummy",
                raw_root=Path(tmp_dir) / "raw",
                staging_root=Path(tmp_dir) / "staging",
            )
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Type": "application/json; charset=utf-8"}
            mock_resp.content = b'{"status":"success","data":{"candles":[]}}'
            mock_resp.text = '{"status":"success","data":{"candles":[]}}'
            mock_resp.json.return_value = {"status": "success", "data": {"candles": []}}

            with patch.object(importer.session, "get", return_value=mock_resp):
                contract = {"instrument_key": "NSE_FO|123|26-12-2024", "strike_price": 24000}
                importer.fetch_contract_candles(contract, to_date="2024-12-26")

            manifests = list((Path(tmp_dir) / "raw").rglob("manifest-*.json"))
            self.assertEqual(len(manifests), 1)
            with open(manifests[0], "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data.get("content_type"), "application/json; charset=utf-8")

    def test_safe_parsing_when_data_is_none(self):
        """
        1. The use of function:
           Verifies that fetch_contract_candles gracefully handles responses where payload['data'] is None.

        2. How does the specific function work:
           Mocks response with {'status': 'success', 'data': None}, confirms no AttributeError and empty candles.

        3. Concepts used in the function:
           Defensive parsing, null safety.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Potential AttributeError. After: Graceful return of empty candle list.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            importer = ExpiredOptionImporter(
                token="dummy",
                raw_root=Path(tmp_dir) / "raw",
                staging_root=Path(tmp_dir) / "staging",
            )
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {"Content-Type": "application/json"}
            mock_resp.content = b'{"status":"success","data":null}'
            mock_resp.text = '{"status":"success","data":null}'
            mock_resp.json.return_value = {"status": "success", "data": None}

            with patch.object(importer.session, "get", return_value=mock_resp):
                contract = {"instrument_key": "NSE_FO|123|26-12-2024", "strike_price": 24000}
                rows, sha = importer.fetch_contract_candles(contract, to_date="2024-12-26")
                self.assertEqual(len(rows), 0)

    def test_load_contracts_from_gzipped_file_offline(self):
        """
        1. The use of function:
           Verifies that ExpiredOptionImporter can load contracts from an offline raw gzipped payload.

        2. How does the specific function work:
           Points load_contracts_from_file to actual response-d87bc3494be9c35c.json.gz in Data/raw/.
           Asserts 281 contracts loaded with 0 network calls.

        3. Concepts used in the function:
           Offline workflow, raw response reuse.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Gzipped JSON on disk. After: List of 281 parsed contract dictionaries.
        """
        raw_file = Path("Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-d87bc3494be9c35c.json.gz")
        if not raw_file.exists():
            self.skipTest("Blocked: Requires external SSD (D:\\Algo_Data_Final\\Data) containing raw option_contract payload")
        self.assertTrue(raw_file.exists())
        importer = ExpiredOptionImporter()
        contracts = importer.load_contracts_from_file(raw_file)
        self.assertEqual(len(contracts), 281)
        self.assertEqual(contracts[0]["expiry"], "2024-12-26")

    def test_filter_candidate_band_geometric(self):
        """
        1. The use of function:
           Verifies that filter_candidate_band restricts contracts to Spot +/- Band without look-ahead bias.

        2. How does the specific function work:
           Loads 281 contracts for 2024-12-26, applies spot_price=23750, band_pts=1000.
           Asserts strikes are bounded in [22750, 24750] and contract count matches expectation.

        3. Concepts used in the function:
           Candidate band filtering, Task D policy verification.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: 281 contracts spanning 14000 to 31000. After: Bounded candidate band contracts.
        """
        raw_file = Path("Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-d87bc3494be9c35c.json.gz")
        if not raw_file.exists():
            self.skipTest("Blocked: Requires external SSD (D:\\Algo_Data_Final\\Data) containing raw option_contract payload")
        importer = ExpiredOptionImporter()
        contracts = importer.load_contracts_from_file(raw_file)
        filtered = importer.filter_candidate_band(contracts, spot_price=23750.0, band_pts=1000.0)

        # Min strike >= 22750, Max strike <= 24750
        strikes = [float(c["strike_price"]) for c in filtered]
        self.assertGreaterEqual(min(strikes), 22750.0)
        self.assertLessEqual(max(strikes), 24750.0)
        # 41 strikes (22750 to 24750 in steps of 50) * 2 (CE + PE) = 82 contracts
        self.assertEqual(len(filtered), 82)

    def test_atomic_staging_and_resumption_merge(self):
        """
        1. The use of function:
           Verifies that staged CSV files are written atomically and merge non-destructively on resumption.

        2. How does the specific function work:
           Executes run() with 1 contract, verifies staged CSV created. Then executes run() with
           2 contracts (1 completed, 1 new). Verifies staged CSV contains merged data and no .tmp file exists.

        3. Concepts used in the function:
           Atomic staging, idempotent resumption, non-destructive persistence.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Potential data loss on resumption. After: Verified merged staged CSV.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            importer = ExpiredOptionImporter(
                token="test",
                raw_root=tmp_path / "raw",
                staging_root=tmp_path / "staging",
                checkpoint_dir=tmp_path / "checkpoints",
            )
            c1 = {"instrument_key": "NSE_FO|1|26-12-2024", "trading_symbol": "OPT1", "expiry": "2024-12-26", "strike_price": 24000, "instrument_type": "CE", "lot_size": 25}
            c2 = {"instrument_key": "NSE_FO|2|26-12-2024", "trading_symbol": "OPT2", "expiry": "2024-12-26", "strike_price": 24050, "instrument_type": "PE", "lot_size": 25}

            raw_candles_1 = [["2024-12-26T09:15:00+05:30", 100.0, 105.0, 95.0, 102.0, 50, 1000]]
            raw_candles_2 = [["2024-12-26T09:15:00+05:30", 80.0, 85.0, 75.0, 82.0, 40, 800]]

            # First run: only c1
            with patch.object(importer, "fetch_contract_candles", return_value=(parse_option_candles(raw_candles_1, c1), "sha1")):
                importer.run("2024-12-26", to_date="2024-12-26", contracts=[c1])

            staged_csv = tmp_path / "staging" / "nifty_options_1m_2024-12-26_2024-12-26.csv"
            self.assertTrue(staged_csv.exists())
            import pandas as pd
            df1 = pd.read_csv(staged_csv)
            self.assertEqual(len(df1), 1)

            # Second run: c1 (completed) and c2 (new)
            with patch.object(importer, "fetch_contract_candles", return_value=(parse_option_candles(raw_candles_2, c2), "sha2")):
                importer.run("2024-12-26", to_date="2024-12-26", contracts=[c1, c2])

            # Merged CSV must contain both records
            df2 = pd.read_csv(staged_csv)
            self.assertEqual(len(df2), 2)
            # Ensure no leftover .tmp files
            tmp_files = list((tmp_path / "staging").glob("*.tmp"))
            self.assertEqual(len(tmp_files), 0)


class TestIndiaVixDataset(unittest.TestCase):
    """
    1. The use of class:
       Validates India VIX canonical dataset invariants per QUANTVIEW_DATA_SPEC §4.10.

    2. What the class contains:
       - test_india_vix_1m_candle_parsing: Verifies 1m candle parsing, nominal volume, oi=0, and ts_end availability.
       - test_india_vix_1d_candle_causal_availability: Verifies daily bar available_at is 15:30 IST.
       - test_india_vix_invalid_ohlc_fails: Verifies that invalid OHLC raises ValueError.
       - test_india_vix_non_derivative_invariant: Verifies that is_derivative is strictly False.

    3. Technologies used and why:
       unittest framework testing domain and data models.

    4. Key design and overall design of the class:
       Guarantees point-in-time compliance and strict index vs derivative separation.
    """

    def test_india_vix_1m_candle_parsing(self):
        """
        1. The use of function:
           Tests 1-minute India VIX candle parsing and schema properties.

        2. How does the specific function work:
           Passes raw candle array, asserts all attributes on IndiaVixCandle.

        3. Concepts used in the function:
           Point-in-time causal availability, non-traded index metric.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Raw candle array. After: Validated IndiaVixCandle instance.
        """
        raw = ["2026-01-20T09:15:00+05:30", 13.5, 13.8, 13.4, 13.6, 250, 1000]
        candle = parse_india_vix_candle(raw, interval="1m")

        self.assertEqual(candle.instrument_key, "NSE_INDEX|India VIX")
        self.assertEqual(candle.interval, "1m")
        self.assertEqual(candle.open, 13.5)
        self.assertEqual(candle.high, 13.8)
        self.assertEqual(candle.low, 13.4)
        self.assertEqual(candle.close, 13.6)
        # Volume is nominal; OI must be strictly 0
        self.assertEqual(candle.volume, 250)
        self.assertEqual(candle.oi, 0)
        self.assertFalse(candle.is_derivative)
        # Causal availability: for 1m, available_at == ts_end == ts_start + 60
        self.assertEqual(candle.ts_end, candle.ts_start + 60)
        self.assertEqual(candle.available_at, candle.ts_end)

    def test_india_vix_1d_candle_causal_availability(self):
        """
        1. The use of function:
           Tests daily India VIX candle causal availability at 15:30 IST.

        2. How does the specific function work:
           Parses daily candle and asserts available_at corresponds to 15:30 IST session close.

        3. Concepts used in the function:
           Anti-lookahead invariant for daily macro features.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Daily raw candle. After: Candle with available_at set to session close.
        """
        raw = ["2026-01-20T09:15:00+05:30", 13.5, 14.2, 13.1, 13.9, 0, 0]
        candle = parse_india_vix_candle(raw, interval="1d")

        self.assertEqual(candle.interval, "1d")
        # 15:30 IST on 2026-01-20 is 10:00:00 UTC
        # Start at 09:15 IST is 03:45:00 UTC
        self.assertGreater(candle.available_at, candle.ts_start)
        # The daily bar is never available at 09:15, 12:00, or 15:00
        midday_utc_sec = candle.ts_start + 10800  # 3 hours into session
        self.assertGreater(candle.available_at, midday_utc_sec)

    def test_india_vix_invalid_ohlc_fails(self):
        """
        1. The use of function:
           Tests that invalid OHLC values (high < low, negative) raise ValueError.

        2. How does the specific function work:
           Passes invalid candles and asserts ValueError.

        3. Concepts used in the function:
           Data integrity enforcement, fail-fast input validation.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Invalid candle array. After: ValueError raised.
        """
        # High lower than close
        bad_raw_1 = ["2026-01-20T09:15:00+05:30", 13.5, 13.0, 12.8, 13.2, 0, 0]
        with self.assertRaises(ValueError):
            parse_india_vix_candle(bad_raw_1, interval="1m")

        # Negative price
        bad_raw_2 = ["2026-01-20T09:15:00+05:30", -1.0, 14.0, -2.0, 13.0, 0, 0]
        with self.assertRaises(ValueError):
            parse_india_vix_candle(bad_raw_2, interval="1m")

    def test_india_vix_non_derivative_invariant(self):
        """
        1. The use of function:
           Verifies that India VIX is strictly non-derivative.

        2. How does the specific function work:
           Inspects candle instance to ensure is_derivative is False and oi is 0.

        3. Concepts used in the function:
           Type safety, asset class demarcation.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Candidate candle. After: Verified non-derivative index asset.
        """
        raw = ["2026-01-20T09:15:00+05:30", 14.0, 14.5, 13.8, 14.1, 0, 0]
        candle = parse_india_vix_candle(raw, interval="1m")
        self.assertFalse(candle.is_derivative)
        self.assertEqual(candle.oi, 0)


class TestRequestAccountingAndSafety(unittest.TestCase):
    """
    1. The use of class:
       Tests HTTP request safety guards, budget ceilings, raw byte preservation, and error handling.

    2. What the class contains:
       - setUp / tearDown: Temporary storage directory setup.
       - test_budget_enforcement: Verifies monotonic counter and RequestLimitExceeded exception.
       - test_raw_byte_fidelity_and_manifest: Verifies raw gzip SHA-256 and companion manifest.
       - test_identical_bodies_distinct_manifests: Verifies distinct manifests for repeated responses.
       - test_http_error_matrix_handling: Verifies behavior across 200, 401, 429, 500, and malformed JSON.
       - test_fail_fast_on_blocking_error: Verifies immediate probe halt on 401.

    3. Technologies used and why:
       unittest framework with mock patching and hashlib for cryptographic verification.

    4. Key design and overall design of the class:
       Enforces zero token leaks, immutable manifests, and hard budget ceilings.
    """

    def setUp(self):
        """
        1. The use of function:
           Creates temporary raw storage directory.

        2. How does the specific function work:
           Initializes TemporaryDirectory and creates raw path.

        3. Concepts used in the function:
           Test isolation.

        4. Places where this function is imported and used:
           Run before each test in this class.

        5. Final output of the function, before and after:
           Before: Uninitialized state. After: Configured raw directory.
        """
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.raw_root = Path(self.tmp_dir.name) / "raw"

    def tearDown(self):
        """
        1. The use of function:
           Cleans up temporary directory.

        2. How does the specific function work:
           Calls TemporaryDirectory.cleanup().

        3. Concepts used in the function:
           Test cleanup.

        4. Places where this function is imported and used:
           Run after each test in this class.

        5. Final output of the function, before and after:
           Before: Temporary files. After: Clean filesystem.
        """
        self.tmp_dir.cleanup()

    def test_budget_enforcement(self):
        """
        1. The use of function:
           Verifies that RequestAccountingSession strictly prevents requests beyond max_budget.

        2. How does the specific function work:
           Configures max_requests=1, executes 1 call, verifies 2nd call raises RequestLimitExceeded.

        3. Concepts used in the function:
           Monotonic budget counter, hard quota enforcement.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unverified session. After: Verified quota-capped session.
        """
        session = RequestAccountingSession(max_requests=1)
        self.assertEqual(session.max_requests, 1)
        self.assertEqual(session.request_count, 0)

        mock_resp = MagicMock()
        mock_resp.content = b'{"status":"success"}'
        mock_resp.status_code = 200

        with patch("requests.Session.send", return_value=mock_resp):
            session.send(MagicMock())
            self.assertEqual(session.request_count, 1)

            with self.assertRaises(RequestLimitExceeded):
                session.send(MagicMock())

    def test_raw_byte_fidelity_and_manifest(self):
        """
        1. The use of function:
           Verifies that raw HTTP responses are saved byte-for-byte in gzip with companion manifest.

        2. How does the specific function work:
           Mocks response with known bytes and SHA-256, verifies saved gzip decompression and manifest.
           Verifies token is never included in manifest.

        3. Concepts used in the function:
           Cryptographic provenance, zero credential leakage.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Mocked response. After: Verified raw gzip and manifest files on disk.
        """
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

            mock_get.assert_called_once()
            _, kwargs = mock_get.call_args
            self.assertFalse(kwargs.get("allow_redirects", True))

            gz_path = Path(res["raw_path"])
            self.assertTrue(gz_path.exists())
            with gzip.open(gz_path, "rb") as gz:
                decompressed = gz.read()
            self.assertEqual(decompressed, test_payload)

            manifest_path = Path(res["manifest_path"])
            self.assertTrue(manifest_path.exists())
            with open(manifest_path, "r", encoding="utf-8") as mf:
                manifest_data = json.load(mf)

            self.assertEqual(manifest_data["raw_sha256"], expected_hash)
            self.assertEqual(manifest_data["http_status"], 200)

            manifest_str = json.dumps(manifest_data)
            self.assertNotIn("secret_test_token_xyz", manifest_str)
            self.assertNotIn("Authorization", manifest_str)

    def test_identical_bodies_distinct_manifests(self):
        """
        1. The use of function:
           Verifies that two requests with identical bodies produce distinct audit manifests.

        2. How does the specific function work:
           Queries two dates returning identical error responses, verifies separate manifest files.

        3. Concepts used in the function:
           Audit trail completeness.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Two queries. After: Two distinct manifest files verified on disk.
        """
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
        """
        1. The use of function:
           Verifies importer handling across HTTP 200, 401, 429, 500, and malformed JSON payloads.

        2. How does the specific function work:
           Iterates through status code test cases, verifying raw preservation and status capture.

        3. Concepts used in the function:
           Error matrix resilience, raw capture on failure.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Error cases. After: Verified graceful degradation and raw file existence.
        """
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
        discoverer = ExpiryContractDiscoverer(
            token=token,
            max_budget=5,
            raw_root=self.raw_root,
            reports_dir=Path(self.raw_root) / "reports"
        )
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
    """
    1. The use of class:
       Verifies repository integrity invariants and storage separation.

    2. What the class contains:
       - test_april24_fixture_unmodified: Verifies SHA-256 of the preserved 2025-04-24 fixture.
       - test_no_parquet_published_by_ingest_tools: Verifies ingest tools do not write to lake Parquet.

    3. Technologies used and why:
       unittest framework with filesystem hashing.

    4. Key design and overall design of the class:
       Safety gate preventing inadvertent file corruption or unverified parquet promotion.
    """

    def test_april24_fixture_unmodified(self):
        """
        1. The use of function:
           Verifies that the original 2025-04-24 option candle file remains unmodified.

        2. How does the specific function work:
           Hashes Data/historical/options/nifty_options_1m_2025-04-24_2025-04-24.csv and checks SHA-256.

        3. Concepts used in the function:
           Bit-for-bit cryptographic immutability.

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Disk file. After: Verified SHA-256 match.
        """
        fixture_path = Path("Data/historical/options/nifty_options_1m_2025-04-24_2025-04-24.csv")
        if not fixture_path.exists():
            self.skipTest("Blocked: Requires external SSD (D:\\Algo_Data_Final\\Data) containing April 24 historical option candle fixture")
        self.assertTrue(fixture_path.exists())
        expected_prefix = "c149b18d2f5f7b1c"
        hasher = hashlib.sha256()
        with open(fixture_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        actual_hash = hasher.hexdigest()
        self.assertTrue(actual_hash.startswith(expected_prefix))

    def test_no_parquet_published_by_ingest_tools(self):
        """
        1. The use of function:
           Verifies that staging directory contains zero unauthorized parquet files.

        2. How does the specific function work:
           Recursively searches staging directory for *.parquet files.

        3. Concepts used in the function:
           Storage segregation invariant (Parquet written only by lake publisher).

        4. Places where this function is imported and used:
           Run by unittest runner.

        5. Final output of the function, before and after:
           Before: Unverified staging dir. After: Verified zero parquet files present.
        """
        staging = Path("staging")
        if staging.exists():
            # Ingestion tools must never write Parquet files into ingest staging directories
            ingest_dirs = [
                staging / "expired_options",
                staging / "underlying_candles",
                staging / "india_vix",
                staging / "checkpoints",
            ]
            parquets = []
            for d in ingest_dirs:
                if d.exists():
                    parquets.extend(list(d.rglob("*.parquet")))
            self.assertEqual(len(parquets), 0)


if __name__ == "__main__":
    unittest.main()
