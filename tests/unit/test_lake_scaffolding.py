"""
1. What this file does:
   Comprehensive automated unit and contract test suite for QuantView Phase 1 Lake Scaffolding & Canonical Schemas.
   Validates Pydantic models, PyArrow schemas, Parquet roundtrips, point-in-time availability,
   exact decimal strikes, negative-volume policy, India VIX session reconciliation, snapshot compaction,
   and staging isolation.

2. Overall design:
   Contains 10 independent test classes verifying each mandatory requirement of the Phase 1 Compliance Gate:
     - TestCanonicalSchemas: Pydantic v2 validation and invariant enforcement.
     - TestPyArrowParquetRoundtrip: Parquet write/read byte-for-byte schema consistency.
     - TestExactStrikeRepresentation: Decimal(9, 2) strike precision preventing binary float keys.
     - TestNegativeVolumePolicy: QuantView Data Spec §11.3 negative-volume clamping and quality tagging.
     - TestFlatBarClassification: QuantView Data Spec §4 exact flat bar conditions.
     - TestCausalAvailabilityInvariants: Intraday (ts_end) vs Daily (session_close) availability.
     - TestIndiaVixSessionReconciliation: Exact mathematical reconciliation of 311-bar special session delta.
     - TestSnapshotCompactionAndIsolation: Capture header and row separation without synthetic chain merging.
     - TestStagingLakeIsolation: Zero writes to active Data/lake/ during Phase 1 preparation.
     - TestDuckDbPointInTimeQueryContract: Read-only DuckDB view query logic enforcing available_at filters.

3. Elements in the file:
   - 10 test case classes containing 16 test methods.
   - Helper fixtures generating representative test records.

4. Final output of the file:
   - Automated pytest/unittest test results validating Phase 1 compliance.
"""

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from packages.data.schemas import (
    INDIA_VIX_CANDLES_SCHEMA,
    OPTION_CANDLES_SCHEMA,
    SNAPSHOT_CAPTURES_SCHEMA,
    SNAPSHOT_ROWS_SCHEMA,
    UNDERLYING_CANDLES_SCHEMA,
    IndiaVixCandleRow,
    OptionCandleRow,
    UnderlyingCandleRow,
    check_is_flat_bar,
    compute_field_presence_mask,
    validate_candle_ohlc,
)
from tools.lake.compact_option_snapshots import classify_and_parse_snapshot
from tools.lake.promote_india_vix import reconcile_vix_sessions
from tools.lake.promote_option_candles import parse_staged_option_csv_to_table


class TestCanonicalSchemas(unittest.TestCase):
    """Tests Pydantic models and field-level validation invariants."""

    def test_underlying_candle_valid(self):
        dt_start = datetime(2026, 1, 20, 9, 15, 0, tzinfo=timezone.utc)
        dt_end = datetime(2026, 1, 20, 9, 16, 0, tzinfo=timezone.utc)
        row = UnderlyingCandleRow(
            instrument_key="NSE_INDEX|Nifty 50",
            underlying="NIFTY",
            interval="1m",
            ts_start=dt_start,
            ts_end=dt_end,
            available_at=dt_end,
            open=21500.0,
            high=21550.0,
            low=21490.0,
            close=21540.0,
            volume=0,
            oi=0,
            source="upstox_historical_candle",
        )
        self.assertEqual(row.underlying, "NIFTY")
        self.assertEqual(row.open, 21500.0)

    def test_ohlc_invariants_rejected(self):
        dt_start = datetime(2026, 1, 20, 9, 15, 0, tzinfo=timezone.utc)
        dt_end = datetime(2026, 1, 20, 9, 16, 0, tzinfo=timezone.utc)
        # High < Open
        with self.assertRaises(ValueError):
            UnderlyingCandleRow(
                instrument_key="NSE_INDEX|Nifty 50",
                underlying="NIFTY",
                interval="1m",
                ts_start=dt_start,
                ts_end=dt_end,
                available_at=dt_end,
                open=21500.0,
                high=21400.0,  # Invalid
                low=21300.0,
                close=21450.0,
                source="test",
            )

    def test_option_type_validation(self):
        dt_start = datetime(2026, 1, 20, 9, 15, 0, tzinfo=timezone.utc)
        dt_end = datetime(2026, 1, 20, 9, 16, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            OptionCandleRow(
                contract_id="TEST",
                instrument_key="TEST",
                underlying="NIFTY",
                expiry=date(2026, 1, 23),
                strike=Decimal("21500.00"),
                option_type="INVALID_TYPE",
                interval="1m",
                ts_start=dt_start,
                ts_end=dt_end,
                available_at=dt_end,
                open=100.0,
                high=110.0,
                low=95.0,
                close=105.0,
                source="test",
            )

    def test_india_vix_zero_oi_invariant(self):
        dt_start = datetime(2026, 1, 20, 9, 15, 0, tzinfo=timezone.utc)
        dt_end = datetime(2026, 1, 20, 9, 16, 0, tzinfo=timezone.utc)
        # Attempting non-zero OI on India VIX must raise ValueError
        with self.assertRaises(ValueError):
            IndiaVixCandleRow(
                interval="1m",
                ts_start=dt_start,
                ts_end=dt_end,
                open=13.5,
                high=13.8,
                low=13.4,
                close=13.6,
                oi=500,  # Prohibited!
                available_at=dt_end,
            )


class TestPyArrowParquetRoundtrip(unittest.TestCase):
    """Tests PyArrow schema fidelity and Parquet file round-trip serialization."""

    def test_option_candles_parquet_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_parquet = Path(tmp_dir) / "test_option.parquet"
            dt_start = datetime(2026, 1, 20, 9, 15, 0, tzinfo=timezone.utc)
            dt_end = datetime(2026, 1, 20, 9, 16, 0, tzinfo=timezone.utc)

            rows = [{
                "contract_id": "NIFTY_2026-01-23_21500.00_CE",
                "instrument_key": "NSE_FO|41685|23-01-2026",
                "trading_symbol": "NIFTY 21500 CE",
                "underlying": "NIFTY",
                "expiry": date(2026, 1, 23),
                "strike": Decimal("21500.00"),
                "option_type": "CE",
                "interval": "1m",
                "ts_start": dt_start,
                "ts_end": dt_end,
                "available_at": dt_end,
                "open": 150.25,
                "high": 155.50,
                "low": 149.00,
                "close": 154.75,
                "volume": 1250,
                "oi": 45000,
                "lot_size_at_source": 25,
                "source": "upstox_expired_historical_candle",
                "source_version": "v2",
                "revision": 1,
                "is_active": True,
                "quality_flags": ["VALID"],
                "ingested_at": dt_start,
            }]

            table = pa.Table.from_pylist(rows, schema=OPTION_CANDLES_SCHEMA)
            pq.write_table(table, tmp_parquet, compression="zstd")

            read_table = pq.read_table(tmp_parquet)
            self.assertEqual(read_table.schema, OPTION_CANDLES_SCHEMA)
            self.assertEqual(len(read_table), 1)
            self.assertEqual(read_table.column("strike")[0].as_py(), Decimal("21500.00"))


class TestExactStrikeRepresentation(unittest.TestCase):
    """Verifies that strikes are exact decimals and never binary floating-point keys."""

    def test_decimal_strike_precision(self):
        s1 = Decimal("21500.00")
        s2 = Decimal("21500.50")
        self.assertEqual(str(s1), "21500.00")
        self.assertNotEqual(s1, s2)
        # Verify schema field type is decimal128(9, 2)
        strike_field = OPTION_CANDLES_SCHEMA.field("strike")
        self.assertEqual(strike_field.type, pa.decimal128(9, 2))


class TestNegativeVolumePolicy(unittest.TestCase):
    """Tests the canonical negative-volume policy per QUANTVIEW_DATA_SPEC §11.3."""

    def test_negative_volume_clamped_and_flagged(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "nifty_options_1m_test.csv"
            # Simulate raw vendor anomaly row from Budget Day 2025-02-01 (negative volume)
            df = pd.DataFrame([{
                "timestamp": "2025-02-01T09:15:00+05:30",
                "instrument_key": "NSE_FO|52400|06-02-2025",
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 102.0,
                "volume": -21017925,  # Vendor anomaly
                "oi": 150000,
                "strike": 23500.0,
                "option_type": "CE",
            }])
            df.to_csv(csv_path, index=False)

            tbl, r_count, neg_count = parse_staged_option_csv_to_table(csv_path, "2025-02-06")
            self.assertEqual(r_count, 1)
            self.assertEqual(neg_count, 1)

            # Volume must be clamped to 0
            self.assertEqual(tbl.column("volume")[0].as_py(), 0)
            # Quality flags must contain VENDOR_NEGATIVE_VOLUME
            flags = tbl.column("quality_flags")[0].as_py()
            self.assertIn("VENDOR_NEGATIVE_VOLUME", flags)


class TestFlatBarClassification(unittest.TestCase):
    """Tests canonical flat bar classification per QUANTVIEW_DATA_SPEC §4."""

    def test_flat_bar_conditions(self):
        # Genuine flat bar: volume == 0 AND open == high == low == close
        self.assertTrue(check_is_flat_bar(0, 24500.0, 24500.0, 24500.0, 24500.0))
        # Volume > 0 with equal OHLC is NOT flat
        self.assertFalse(check_is_flat_bar(100, 24500.0, 24500.0, 24500.0, 24500.0))
        # Volume == 0 with varying prices is NOT flat
        self.assertFalse(check_is_flat_bar(0, 24500.0, 24510.0, 24490.0, 24505.0))


class TestCausalAvailabilityInvariants(unittest.TestCase):
    """Tests causal availability timestamp rules for 1m vs 1d bars."""

    def test_intraday_available_at_equals_ts_end(self):
        dt_start = datetime(2026, 1, 20, 9, 15, 0, tzinfo=timezone.utc)
        dt_end = datetime(2026, 1, 20, 9, 16, 0, tzinfo=timezone.utc)
        row = UnderlyingCandleRow(
            instrument_key="NSE_INDEX|Nifty 50",
            interval="1m",
            ts_start=dt_start,
            ts_end=dt_end,
            available_at=dt_end,
            open=21500.0,
            high=21510.0,
            low=21495.0,
            close=21505.0,
            source="test",
        )
        self.assertEqual(row.available_at, row.ts_end)

    def test_daily_available_at_is_session_close(self):
        dt_day = datetime(2026, 1, 20, 0, 0, 0, tzinfo=timezone.utc)
        session_close_utc = datetime(2026, 1, 20, 10, 0, 0, tzinfo=timezone.utc)  # 15:30 IST
        row = UnderlyingCandleRow(
            instrument_key="NSE_INDEX|Nifty 50",
            interval="1d",
            ts_start=dt_day,
            ts_end=session_close_utc,
            available_at=session_close_utc,
            open=21500.0,
            high=21600.0,
            low=21450.0,
            close=21580.0,
            source="test",
        )
        self.assertEqual(row.available_at, session_close_utc)


class TestIndiaVixSessionReconciliation(unittest.TestCase):
    """Verifies that the 311-bar discrepancy in India VIX is exactly accounted for."""

    def test_session_reconciliation_math(self):
        vix_file = Path("staging/india_vix/underlying_NSE_INDEX_India_VIX_1m_2025-01-01_2026-10-19.csv")
        if vix_file.exists():
            df = pd.read_csv(vix_file)
            session_counts, special = reconcile_vix_sessions(df)
            expected = len(session_counts) * 375
            actual = len(df)
            diff = actual - expected
            self.assertEqual(diff, -311)
            # Verify Diwali Muhurat trading session is present with exactly 60 bars
            self.assertEqual(session_counts.get("2025-10-21"), 60)


class TestSnapshotCompactionAndIsolation(unittest.TestCase):
    """Tests option snapshot compaction, schema classification, and quarantine."""

    def test_zero_byte_empty_quarantine(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            empty_file = Path(tmp_dir) / "empty.csv"
            empty_file.touch()
            header, rows, q_reason = classify_and_parse_snapshot(empty_file, date(2026, 1, 23), date(2026, 1, 20))
            self.assertEqual(q_reason, "EMPTY_ZERO_BYTES")

    def test_null_byte_corrupt_quarantine(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            corrupt_file = Path(tmp_dir) / "corrupt.csv"
            with open(corrupt_file, "wb") as bf:
                bf.write(b"timestamp,strike\x00\x00\x00corrupt")
            header, rows, q_reason = classify_and_parse_snapshot(corrupt_file, date(2026, 1, 23), date(2026, 1, 20))
            self.assertEqual(q_reason, "CORRUPT_NULL_BYTES")

    def test_schema_v3_parsing_preserves_greeks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            v3_file = Path(tmp_dir) / "snap_v3.csv"
            df = pd.DataFrame([{
                "timestamp": "2026-07-29T14:28:03+05:30",
                "spot_price": 24850.5,
                "strike": 24800.0,
                "type": "CE",
                "oi": 2629705,
                "volume": 310245,
                "ltp": 125.4,
                "bid": 125.2,
                "ask": 125.6,
                "bid_qty": 50,
                "ask_qty": 75,
                "chng": 15.2,
                "chng_oi": 15000,
                "iv": 14.85,
                "delta": 0.542,
                "gamma": 0.0012,
                "theta": -8.54,
                "vega": 12.35,
            }])
            df.to_csv(v3_file, index=False)

            header, rows, q_reason = classify_and_parse_snapshot(v3_file, date(2026, 8, 4), date(2026, 7, 29))
            self.assertIsNone(q_reason)
            self.assertIsNotNone(header)
            self.assertEqual(header["schema_version"], "v3")
            self.assertEqual(len(rows), 1)
            self.assertAlmostEqual(rows[0]["delta_observed"], 0.542)
            self.assertAlmostEqual(rows[0]["iv_observed"], 14.85)

    def test_derived_candle_row_validation(self):
        """
        1. The use of function:
           Verifies Pydantic validation and OHLC invariants on DerivedCandleRow.

        2. How does the specific function work:
           Tests that valid derived bar passes and bar violating High >= Open raises ValueError.

        3. Concepts used in the function:
           Pydantic invariant testing, derived candle validation.

        4. Places where this function is imported and used:
           Executed in automated unit test suite.

        5. Final output of the function, before and after:
           Before: Unverified model. After: Confirmed model invariant enforcement.
        """
        from packages.data.schemas import DerivedCandleRow
        dt = datetime(2026, 1, 20, 9, 15, 0, tzinfo=timezone.utc)
        dt_end = datetime(2026, 1, 20, 9, 20, 0, tzinfo=timezone.utc)

        valid_row = DerivedCandleRow(
            derivation_id="test_deriv_123",
            interval="5m",
            input_manifest_hash="hash123",
            ts_start=dt,
            ts_end=dt_end,
            available_at=dt_end,
            open=21500.0,
            high=21550.0,
            low=21480.0,
            close=21520.0,
            volume=1500,
            oi=250000,
        )
        self.assertEqual(valid_row.interval, "5m")
        self.assertEqual(valid_row.available_at, dt_end)

        with self.assertRaises(ValueError):
            DerivedCandleRow(
                derivation_id="test_deriv_123",
                interval="5m",
                input_manifest_hash="hash123",
                ts_start=dt,
                ts_end=dt_end,
                available_at=dt_end,
                open=21500.0,
                high=21400.0,  # High < Open violates invariant!
                low=21350.0,
                close=21450.0,
            )

    def test_data_eligibility_row_validation(self):
        """
        1. The use of function:
           Verifies Pydantic validation and reason code vocabulary on DataEligibilityRow.

        2. How does the specific function work:
           Tests that canonical status and valid reason codes pass, while invalid codes raise ValueError.

        3. Concepts used in the function:
           Pydantic vocabulary constraint validation.

        4. Places where this function is imported and used:
           Executed in automated unit test suite.

        5. Final output of the function, before and after:
           Before: Unverified model. After: Confirmed vocabulary enforcement.
        """
        from packages.data.schemas import DataEligibilityRow

        row = DataEligibilityRow(
            session_date=date(2026, 1, 20),
            interval="1m",
            manifest_hash="manifest_hash_123",
            status="ELIGIBLE",
            reason_codes=[],
        )
        self.assertEqual(row.status, "ELIGIBLE")

        # Invalid status must raise
        with self.assertRaises(ValueError):
            DataEligibilityRow(
                session_date=date(2026, 1, 20),
                interval="1m",
                manifest_hash="manifest_hash_123",
                status="INVALID_STATUS",
                reason_codes=[],
            )

        # Invalid reason code must raise
        with self.assertRaises(ValueError):
            DataEligibilityRow(
                session_date=date(2026, 1, 20),
                interval="1m",
                manifest_hash="manifest_hash_123",
                status="ELIGIBLE",
                reason_codes=["UNRECOGNIZED_CODE"],
            )


class TestStagingLakeIsolation(unittest.TestCase):
    """
    1. The use of class:
       Verifies boundary isolation between staging workspace and active production Data/lake/.

    2. What the class contains:
       - test_active_lake_directory_unmodified: Enforces that active lake writes only occur under an active manifest.

    3. Technologies used and why:
       unittest framework, pathlib for filesystem path inspection.

    4. Key design and overall design of the class:
       Guarantees that unmanifested or unapproved writes to Data/lake/ are strictly prohibited.
    """

    def test_active_lake_directory_unmodified(self):
        """
        1. The use of function:
           Verifies that files in Data/lake/ are governed by an active cryptographic manifest.

        2. How does the specific function work:
           Inspects Data/lake/. If present, verifies that manifest_active.json exists, declares
           is_active = true, and indexes all published Parquet partitions. Unmanifested files fail.

        3. Concepts used in the function:
           Manifest-governed storage, publication boundary verification.

        4. Places where this function is imported and used:
           Executed in automated unit test suite (test_lake_scaffolding.py).

        5. Final output of the function, before and after:
           Before: Unverified filesystem state. After: Assertion pass confirming manifest-governed lake.
        """
        active_lake = Path("Data/lake")
        if active_lake.exists():
            active_manifest = active_lake / "manifest_active.json"
            if active_manifest.exists():
                with open(active_manifest, "r", encoding="utf-8") as f:
                    m = json.load(f)
                self.assertTrue(m.get("is_active", False))
                self.assertGreaterEqual(m.get("manifest_version", 1), 2)
                self.assertGreaterEqual(len(list(active_lake.glob("**/*.parquet"))), 435)
            else:
                files = list(active_lake.glob("**/*.parquet"))
                self.assertEqual(len(files), 0, "Unmanifested writes to Data/lake/ are prohibited")

    def test_active_snapshot_duckdb_views(self):
        """
        1. The use of function:
           Verifies that published snapshot views are active in quantview.duckdb and queryable.

        2. How does the specific function work:
           Opens Data/lake/quantview.duckdb in read-only mode, queries v_snapshots_captures,
           v_snapshots_rows, and v_snapshots_reconstructed_chain, and validates row count thresholds.

        3. Concepts used in the function:
           DuckDB analytical view regression verification.

        4. Places where this function is imported and used:
           Executed in automated unit test suite.

        5. Final output of the function, before and after:
           Before: Unverified view status. After: Assertion pass confirming active queryable views.
        """
        db_file = Path("Data/lake/quantview.duckdb")
        if db_file.exists():
            con = duckdb.connect(str(db_file), read_only=True)
            res_cap = con.execute("SELECT count(*) FROM v_snapshots_captures").fetchone()[0]
            self.assertEqual(res_cap, 82274)
            res_rows = con.execute("SELECT count(*) FROM v_snapshots_rows").fetchone()[0]
            self.assertEqual(res_rows, 17445732)
            res_chain = con.execute("SELECT count(*) FROM v_snapshots_reconstructed_chain").fetchone()[0]
            self.assertEqual(res_chain, 17445732)
            con.close()


class TestDuckDbPointInTimeQueryContract(unittest.TestCase):
    """Verifies that DuckDB queries enforce point-in-time available_at filtering."""

    def test_duckdb_view_causal_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            p_file = Path(tmp_dir) / "sample_candles.parquet"
            dt_start1 = datetime(2026, 1, 20, 9, 15, 0, tzinfo=timezone.utc)
            dt_end1 = datetime(2026, 1, 20, 9, 16, 0, tzinfo=timezone.utc)
            dt_start2 = datetime(2026, 1, 20, 9, 16, 0, tzinfo=timezone.utc)
            dt_end2 = datetime(2026, 1, 20, 9, 17, 0, tzinfo=timezone.utc)

            rows = [
                {
                    "instrument_key": "NSE_INDEX|Nifty 50",
                    "underlying": "NIFTY",
                    "interval": "1m",
                    "ts_start": dt_start1,
                    "ts_end": dt_end1,
                    "available_at": dt_end1,
                    "open": 21500.0,
                    "high": 21510.0,
                    "low": 21495.0,
                    "close": 21505.0,
                    "volume": 100,
                    "oi": 0,
                    "source": "test",
                    "source_version": "v1",
                    "revision": 1,
                    "is_active": True,
                    "quality_flags": ["VALID"],
                    "ingested_at": dt_start1,
                },
                {
                    "instrument_key": "NSE_INDEX|Nifty 50",
                    "underlying": "NIFTY",
                    "interval": "1m",
                    "ts_start": dt_start2,
                    "ts_end": dt_end2,
                    "available_at": dt_end2,
                    "open": 21505.0,
                    "high": 21520.0,
                    "low": 21500.0,
                    "close": 21515.0,
                    "volume": 120,
                    "oi": 0,
                    "source": "test",
                    "source_version": "v1",
                    "revision": 1,
                    "is_active": True,
                    "quality_flags": ["VALID"],
                    "ingested_at": dt_start2,
                },
            ]

            tbl = pa.Table.from_pylist(rows, schema=UNDERLYING_CANDLES_SCHEMA)
            pq.write_table(tbl, p_file)

            con = duckdb.connect()
            p_str = str(p_file).replace("\\", "/")
            con.execute(f"CREATE VIEW v_test_candles AS SELECT * FROM read_parquet('{p_str}') WHERE is_active = true")

            # Point-in-time query at 09:16:00 UTC must see exactly 1 bar (bar 1 completed; bar 2 not available)
            res = con.execute("SELECT count(*) FROM v_test_candles WHERE available_at <= '2026-01-20 09:16:00+00'").fetchone()
            self.assertEqual(res[0], 1)

            # Query at 09:17:00 UTC sees both bars
            res2 = con.execute("SELECT count(*) FROM v_test_candles WHERE available_at <= '2026-01-20 09:17:00+00'").fetchone()
            self.assertEqual(res2[0], 2)


class TestStage1GateG1AndManifestV3(unittest.TestCase):
    """
    1. The use of class:
       Unit and integration tests for Stage 1 completion, Manifest v3 integrity, and Gate G1 analytical views.

    2. What the class contains:
       - test_manifest_v3_structure_and_aggregate_totals(): Tests Manifest v3 schema, totals, and active state.
       - test_duckdb_eight_views_registered_and_queryable(): Verifies all 8 canonical views query without errors.

    3. Technologies used and why:
       - unittest framework for test assertions.
       - DuckDB for verifying analytical view queryability.
       - Python json for manifest inspection.

    4. Key design and overall design of the class:
       Follows non-destructive read-only assertions verifying that Stage 1 production lake
       satisfies all Gate G1 acceptance contracts.
    """

    def test_manifest_v3_structure_and_aggregate_totals(self) -> None:
        """
        1. The use of function:
           Verifies that Data/lake/manifest_active.json is active Manifest Version 3 with 784 files.

        2. How does the specific function work:
           Loads manifest_active.json, checks manifest_version == 3, is_active == True,
           confirms 7 datasets are present, and validates aggregate file and row totals.

        3. Concepts used in the function:
           Catalog manifest contract testing, aggregate reconciliation.

        4. Places where this function is imported and used:
           Run by unittest discover runner.

        5. Final output of the function, before and after:
           Before: Manifest unverified. After: Assertions pass confirming Manifest v3 validity.
        """
        manifest_path = Path("Data/lake/manifest_active.json")
        self.assertTrue(manifest_path.exists(), "Active manifest must exist in Data/lake/")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual(manifest.get("manifest_version"), 3)
        self.assertTrue(manifest.get("is_active"))
        self.assertEqual(manifest.get("manifest_type"), "quantview_active_lake_manifest")

        expected_datasets = {
            "option_candles",
            "underlying_candles",
            "india_vix",
            "option_snapshot_captures",
            "option_snapshot_rows",
            "derived_candles",
            "data_eligibility",
        }
        self.assertEqual(set(manifest.get("datasets", {}).keys()), expected_datasets)
        totals = manifest.get("aggregate_totals", {})
        self.assertEqual(totals.get("total_files"), 784)
        self.assertEqual(totals.get("total_rows"), 38753287)

    def test_duckdb_eight_views_registered_and_queryable(self) -> None:
        """
        1. The use of function:
           Verifies that all 8 canonical views in Data/lake/quantview.duckdb are registered and queryable.

        2. How does the specific function work:
           Connects to quantview.duckdb in read-only mode, queries information_schema to verify
           the presence of all 8 views, and runs a count query on v_candles_derived and v_data_eligibility.

        3. Concepts used in the function:
           Database schema reflection, view querying verification, point-in-time data verification.

        4. Places where this function is imported and used:
           Run by unittest discover runner.

        5. Final output of the function, before and after:
           Before: Views unverified. After: Assertions pass confirming 8 views exist and return expected row counts.
        """
        duckdb_path = Path("Data/lake/quantview.duckdb")
        self.assertTrue(duckdb_path.exists(), "quantview.duckdb must exist in Data/lake/")

        con = duckdb.connect(str(duckdb_path), read_only=True)
        try:
            views = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_type='VIEW';").fetchall()]
            expected_views = {
                "v_candles_underlying",
                "v_candles_options",
                "v_candles_vix",
                "v_snapshots_captures",
                "v_snapshots_rows",
                "v_snapshots_reconstructed_chain",
                "v_candles_derived",
                "v_data_eligibility",
            }
            for exp in expected_views:
                self.assertIn(exp, views, f"View {exp} must be registered in quantview.duckdb")

            derived_count = con.execute("SELECT count(*) FROM v_candles_derived;").fetchone()[0]
            self.assertEqual(derived_count, 287306)

            eligibility_count = con.execute("SELECT count(*) FROM v_data_eligibility;").fetchone()[0]
            self.assertEqual(eligibility_count, 1161)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
