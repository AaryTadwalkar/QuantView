"""
1. What this file does:
   Compacts raw live option chain snapshot CSV captures (from Data/live/option_chain/nifty/) into
   daily Parquet partitions in staging lake preparation (staging/lake_preparation_phase3/)
   strictly preserving capture boundaries, individual capture identity, decimal strike precision,
   float64 observed Greeks, field-presence metadata, and deterministic sorting per QUANTVIEW_DATA_SPEC §4.3 and §4.4.

2. Overall design:
   Processes snapshot captures across all three schema versions (v1, v2, v3):
     - Produces two separate canonical tables per QUANTVIEW_DATA_SPEC §4.3 and §4.4:
       1. option_snapshot_captures: One row per capture file with snapshot_id, received_at, schema_version, and field_presence_mask.
       2. option_snapshot_rows: One row per strike/type per capture with exact decimal strike and float64 observed Greeks.
     - Strictly forbids merging captures into a fabricated continuous series.
     - Detects and quarantines 0-byte empty files (EMPTY_ZERO_BYTES) and null-byte corrupted files (CORRUPT_NULL_BYTES).
     - Resolves expiry dates from directory paths when absent in raw CSV headers, handling unpadded single-digit days.
     - Localizes naive timestamps to Asia/Kolkata (IST) and converts to UTC per QUANTVIEW_DATA_SPEC §11.
     - Sorts Parquet rows by canonical keys (captures: received_at, expiry; rows: received_at, expiry, strike, option_type)
       before serialization for binary reproducibility and predicate pushdown.
     - Enforces non-destructive execution: outputs strictly to staging/lake_preparation_phase3/ before active lake promotion.

3. Elements in the file:
   - safe_float, safe_int, safe_decimal_strike: Robust numerical conversion helpers.
   - classify_and_parse_snapshot: Helper parsing a single snapshot CSV into capture header and strike rows.
   - SnapshotCompactor: Main workflow class coordinating capture discovery, schema classification,
     and daily Parquet table generation.
   - main: CLI entry point supporting source/output overrides, session limits, and dry-run mode.

4. Final output of the file:
   - Captures table: staging/lake_preparation_phase3/option_snapshot_captures/trade_date=YYYY-MM-DD/part-0.parquet
   - Rows table: staging/lake_preparation_phase3/option_snapshot_rows/trade_date=YYYY-MM-DD/part-0.parquet
   - Quarantine report: staging/lake_preparation_phase3/quarantine/quarantine_report.json
   - Compaction and quarantine reconciliation summary dictionary.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from packages.data.schemas import (
    SNAPSHOT_CAPTURES_SCHEMA,
    SNAPSHOT_ROWS_SCHEMA,
    compute_field_presence_mask,
)

ZONE_IST = ZoneInfo("Asia/Kolkata")


def safe_float(val: Any) -> Optional[float]:
    """
    1. The use of function:
       Safely converts an arbitrary input value to a float or None.

    2. How does the specific function work:
       Checks for None or NaN; parses via float(); catches ValueError and TypeError returning None.

    3. Concepts used in the function:
       Defensive numerical conversion, null preservation.

    4. Places where this function is imported and used:
       Called during strike row dictionary construction in classify_and_parse_snapshot.

    5. Final output of the function, before and after:
       Before: Raw value (float, int, string, NaN). After: Valid float or None.
    """
    if val is None or pd.isna(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val: Any) -> Optional[int]:
    """
    1. The use of function:
       Safely converts an arbitrary input value to an integer or None.

    2. How does the specific function work:
       Checks for None or NaN; parses via int(float(val)); catches ValueError and TypeError returning None.

    3. Concepts used in the function:
       Defensive integer conversion, null preservation.

    4. Places where this function is imported and used:
       Called during strike row dictionary construction in classify_and_parse_snapshot.

    5. Final output of the function, before and after:
       Before: Raw value. After: Valid int or None.
    """
    if val is None or pd.isna(val):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_decimal_strike(val: Any) -> Decimal:
    """
    1. The use of function:
       Converts a raw strike price to an exact Decimal with two decimal places.

    2. How does the specific function work:
       Parses float value, formats with exactly 2 decimal places, and constructs Decimal.

    3. Concepts used in the function:
       Exact decimal currency/strike precision (decimal128(9, 2)).

    4. Places where this function is imported and used:
       Called for option strike normalization in classify_and_parse_snapshot.

    5. Final output of the function, before and after:
       Before: Float or int strike (e.g. 24800.0). After: Decimal('24800.00').
    """
    if val is None or pd.isna(val):
        return Decimal("0.00")
    try:
        return Decimal(f"{float(val):.2f}")
    except (ValueError, TypeError):
        return Decimal("0.00")


def classify_and_parse_snapshot(
    file_path: Path,
    expiry_from_path: date,
    trade_date: date,
) -> Tuple[Optional[Dict], List[Dict], Optional[str]]:
    """
    1. The use of function:
       Classifies and parses an individual option snapshot CSV file into a capture header and strike rows.

    2. How does the specific function work:
       - Checks file size: if 0 bytes, returns EMPTY_ZERO_BYTES.
       - Reads binary bytes: checks for null bytes (\\x00); if found, returns CORRUPT_NULL_BYTES.
       - Parses CSV, inspects column count and names to determine schema version (v1: 9 cols, v2: 7 cols, v3: 18 cols).
       - Extracts capture timestamp: if naive, assumes Asia/Kolkata per DATA SPEC §11 and converts to UTC.
       - Constructs globally unique snapshot_id hashing session, expiry, filename, timestamp, and row count.
       - Converts strikes to exact Decimal(9, 2) and observed Greeks to 64-bit floats.
       - Constructs capture header dict and list of strike row dicts.

    3. Concepts used in the function:
       Binary defect detection, schema evolution classification, timezone normalization, field presence tracking.

    4. Places where this function is imported and used:
       Called by SnapshotCompactor.compact_session() for each discovered capture CSV.

    5. Final output of the function, before and after:
       Before: Raw CSV on disk. After: Tuple of (capture_header_dict, strike_rows_list, quarantine_reason_or_none).
    """
    file_size = file_path.stat().st_size
    if file_size == 0:
        return None, [], "EMPTY_ZERO_BYTES"

    with open(file_path, "rb") as bf:
        raw_bytes = bf.read()
    if b"\x00" in raw_bytes:
        return None, [], "CORRUPT_NULL_BYTES"

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        return None, [], f"CSV_PARSE_FAILED: {e}"

    if df.empty:
        return None, [], "CSV_EMPTY_ROWS"

    cols = list(df.columns)
    col_count = len(cols)

    # Classify schema version
    if col_count == 18 or "iv" in cols or "delta" in cols:
        schema_ver = "v3"
    elif col_count == 9 or "prev_oi" in cols:
        schema_ver = "v1"
    else:
        schema_ver = "v2"

    ts_col = cols[0]
    first_ts_str = str(df[ts_col].iloc[0])
    ts_flag = "AWARE_TIMESTAMP"
    try:
        dt_received = datetime.fromisoformat(first_ts_str)
        if dt_received.tzinfo is None:
            # Naive timestamp from local machine: assume Asia/Kolkata per DATA SPEC §11
            dt_received = dt_received.replace(tzinfo=ZONE_IST).astimezone(timezone.utc)
            ts_flag = "NAIVE_TIMESTAMP_ASSUMED_IST"
        else:
            dt_received = dt_received.astimezone(timezone.utc)
    except Exception:
        mtime = file_path.stat().st_mtime
        dt_received = datetime.fromtimestamp(mtime, tz=timezone.utc)
        ts_flag = "MTIME_TIMESTAMP_FALLBACK"

    # Globally unique stable snapshot_id: SHA-256 of expiry, trade_date, file name, timestamp, and row count
    id_basis = f"{expiry_from_path}_{trade_date}_{file_path.name}_{dt_received.isoformat()}_{len(df)}"
    snapshot_id = hashlib.sha256(id_basis.encode("utf-8")).hexdigest()[:24]

    spot_val = safe_float(df["spot_price"].iloc[0]) if "spot_price" in df else None
    first_dict = df.iloc[0].to_dict()
    mask = compute_field_presence_mask(first_dict)
    now_ts = datetime.now(timezone.utc)

    capture_header = {
        "snapshot_id": snapshot_id,
        "received_at": dt_received,
        "trade_date": trade_date,
        "underlying": "NIFTY",
        "expiry": expiry_from_path,
        "spot_price": spot_val,
        "schema_version": schema_ver,
        "source_file": str(file_path).replace("\\", "/"),
        "row_count": len(df),
        "completeness": None,
        "field_presence_mask": mask,
        "quality_flags": ["VALID", f"SCHEMA_{schema_ver}", ts_flag, "PATH_DERIVED_EXPIRY"],
        "ingested_at": now_ts,
    }

    # Fast row parsing using records
    records = df.to_dict(orient="records")
    strike_rows = []

    for r in records:
        raw_type = r.get("type", r.get("option_type", "CE"))
        opt_type = str(raw_type).strip().upper()
        if opt_type not in ("CE", "PE"):
            continue

        strike_val = safe_decimal_strike(r.get("strike", 0))

        strike_rows.append({
            "snapshot_id": snapshot_id,
            "received_at": dt_received,
            "trade_date": trade_date,
            "underlying": "NIFTY",
            "expiry": expiry_from_path,
            "strike": strike_val,
            "option_type": opt_type,
            "spot_price": spot_val,
            "oi": safe_int(r.get("oi")),
            "prev_oi": safe_int(r.get("prev_oi")),
            "volume": safe_int(r.get("volume")),
            "ltp": safe_float(r.get("ltp")),
            "bid": safe_float(r.get("bid")),
            "ask": safe_float(r.get("ask")),
            "bid_qty": safe_int(r.get("bid_qty")),
            "ask_qty": safe_int(r.get("ask_qty")),
            "change": safe_float(r.get("chng")),
            "change_oi": safe_int(r.get("change_oi", r.get("chng_oi"))),
            "iv_observed": safe_float(r.get("iv")),
            "delta_observed": safe_float(r.get("delta")),
            "gamma_observed": safe_float(r.get("gamma")),
            "theta_observed": safe_float(r.get("theta")),
            "vega_observed": safe_float(r.get("vega")),
            "schema_version": schema_ver,
            "field_presence_mask": mask,
            "quality_flags": ["VALID", "PATH_DERIVED_EXPIRY", ts_flag],
            "source_file": str(file_path).replace("\\", "/"),
        })

    return capture_header, strike_rows, None


class SnapshotCompactor:
    """
    1. The use of class:
       Coordinates offline compaction of raw option chain snapshot CSVs into daily Parquet tables.

    2. What the class contains:
       - source_dir: Root directory of raw snapshot CSVs.
       - output_prep: Destination staging lake directory (staging/lake_preparation_phase3/).
       - quarantine_dir: Destination directory for quarantine audit records.
       - discover_sessions(): Groups raw files by trade_date and extracts expiry from path.
       - compact_session(): Builds daily captures and rows Parquet files sorted by canonical keys.
       - run(): Orchestrates compaction across sessions with complete quarantine accounting.

    3. Technologies used and why:
       - pyarrow / pyarrow.parquet: Fast columnar Parquet serialization with zstd compression.
       - zoneinfo: Canonical Asia/Kolkata timezone localization.
       - pathlib / hashlib: Robust path manipulation and SHA-256 provenance generation.

    4. Key design and overall design of the class:
       Separates captures headers from strike rows and enforces non-destructive staging boundaries.
    """

    def __init__(
        self,
        source_dir: Optional[Path] = None,
        output_prep_dir: Optional[Path] = None,
        quarantine_dir: Optional[Path] = None,
    ):
        """Initializes SnapshotCompactor with source and output directories."""
        self.candidate_source_dirs = [
            Path("Data/live/option_chain/nifty"),
            Path(r"D:\Algo_Data_Final\Data\live\option_chain\nifty"),
        ]
        self.source_dir = source_dir or self._find_existing_source()
        self.output_prep = output_prep_dir or Path("staging/lake_preparation_phase3")
        self.quarantine_dir = quarantine_dir or (self.output_prep / "quarantine")

    def _find_existing_source(self) -> Path:
        """Finds first existing source directory from candidate paths."""
        for d in self.candidate_source_dirs:
            if d.exists():
                return d
        return Path("Data/live/option_chain/nifty")

    def discover_sessions(self) -> Dict[str, List[Tuple[date, date, Path]]]:
        """
        1. The use of function:
           Discovers all snapshot CSV files, parsing trade_date and expiry from path hierarchy.

        2. How does the specific function work:
           Expected layout: {source_dir}/{expiry_folder}/{trade_date_folder}/snapshots/{file}.csv
           Handles unpadded month/day folders defensively.
           Groups files by ISO trade_date string (YYYY-MM-DD).

        3. Concepts used in the function:
           Path-derived metadata, robust date component parsing.

        4. Places where this function is imported and used:
           Called by run() to organize daily compaction batches.

        5. Final output of the function, before and after:
           Before: Directory root. After: Dict mapping trade_date to list of (expiry_date, trade_date, file_path).
        """
        if not self.source_dir.exists():
            return {}

        sessions: Dict[str, List[Tuple[date, date, Path]]] = {}
        for csv_file in self.source_dir.glob("*/*/snapshots/*.csv"):
            parts = csv_file.parts
            try:
                snap_idx = parts.index("snapshots")
                raw_td = parts[snap_idx - 1]
                raw_exp = parts[snap_idx - 2]

                exp_parts = [int(p) for p in raw_exp.split("-")]
                td_parts = [int(p) for p in raw_td.split("-")]
                exp_dt = date(exp_parts[0], exp_parts[1], exp_parts[2])
                td_dt = date(td_parts[0], td_parts[1], td_parts[2])

                td_str = td_dt.isoformat()
                sessions.setdefault(td_str, []).append((exp_dt, td_dt, csv_file))
            except Exception:
                continue

        return sessions

    def compact_session(
        self,
        trade_date_str: str,
        file_tuples: List[Tuple[date, date, Path]],
        dry_run: bool = False,
    ) -> Dict:
        """
        1. The use of function:
           Compacts all captures for one session into daily captures and rows Parquet files.

        2. How does the specific function work:
           Parses each snapshot file; aggregates headers and strike rows; sorts headers by
           (received_at, expiry) and rows by (received_at, expiry, strike, option_type);
           writes to daily Parquet partitions with zstd compression and row groups of 250,000.

        3. Concepts used in the function:
           Columnar Parquet serialization, stable query key sorting (DATA Spec §2.2).

        4. Places where this function is imported and used:
           Called by run() for each session date.

        5. Final output of the function, before and after:
           Before: Raw CSVs. After: Daily Parquet files and session metrics dictionary.
        """
        captures_list = []
        rows_list = []
        quarantined = []

        for exp_dt, td_dt, f_path in file_tuples:
            header, s_rows, q_reason = classify_and_parse_snapshot(f_path, exp_dt, td_dt)
            if q_reason:
                quarantined.append({
                    "file": str(f_path).replace("\\", "/"),
                    "expiry": exp_dt.isoformat(),
                    "trade_date": trade_date_str,
                    "reason": q_reason,
                })
            else:
                if header:
                    captures_list.append(header)
                rows_list.extend(s_rows)

        # Canonical directory layout per DATA SPEC §2
        captures_dir = self.output_prep / "option_snapshot_captures" / f"trade_date={trade_date_str}"
        rows_dir = self.output_prep / "option_snapshot_rows" / f"trade_date={trade_date_str}"

        target_captures = captures_dir / "part-0.parquet"
        target_rows = rows_dir / "part-0.parquet"

        if dry_run or not captures_list:
            return {
                "trade_date": trade_date_str,
                "status": "DRY_RUN" if dry_run else "EMPTY",
                "captures_count": len(captures_list),
                "rows_count": len(rows_list),
                "quarantined_count": len(quarantined),
                "quarantined_items": quarantined,
            }

        captures_dir.mkdir(parents=True, exist_ok=True)
        rows_dir.mkdir(parents=True, exist_ok=True)

        # Sort by canonical query keys per QUANTVIEW_DATA_SPEC §2.2
        captures_list.sort(key=lambda c: (c["received_at"], c["expiry"] or date.min))
        rows_list.sort(key=lambda r: (r["received_at"], r["expiry"], r["strike"], r["option_type"]))

        tbl_captures = pa.Table.from_pylist(captures_list, schema=SNAPSHOT_CAPTURES_SCHEMA)
        pq.write_table(tbl_captures, target_captures, compression="zstd", row_group_size=250000)

        tbl_rows = pa.Table.from_pylist(rows_list, schema=SNAPSHOT_ROWS_SCHEMA)
        pq.write_table(tbl_rows, target_rows, compression="zstd", row_group_size=250000)

        return {
            "trade_date": trade_date_str,
            "status": "STAGED",
            "captures_count": len(captures_list),
            "rows_count": len(rows_list),
            "quarantined_count": len(quarantined),
            "quarantined_items": quarantined,
            "captures_file": str(target_captures).replace("\\", "/"),
            "rows_file": str(target_rows).replace("\\", "/"),
        }

    def run(self, max_sessions: Optional[int] = None, dry_run: bool = False) -> Dict:
        """
        1. The use of function:
           Runs compaction across discovered snapshot sessions.

        2. How does the specific function work:
           Discovers sessions, iterates sequentially through each trade date, compacts session files,
           records metrics and quarantined items, and serializes the quarantine audit JSON.

        3. Concepts used in the function:
           Batch workflow orchestration, comprehensive quarantine audit persistence.

        4. Places where this function is imported and used:
           Invoked via CLI main() or integration pipeline scripts.

        5. Final output of the function, before and after:
           Before: Uncompacted CSVs. After: Staged daily Parquets, quarantine JSON, summary dictionary.
        """
        sessions = self.discover_sessions()
        session_dates = sorted(list(sessions.keys()))
        if max_sessions:
            session_dates = session_dates[:max_sessions]

        print("\n=======================================================", flush=True)
        print("QUANTVIEW -- OPTION SNAPSHOT COMPACTION (OFFLINE)", flush=True)
        print(f"Source Directory: {self.source_dir}", flush=True)
        print(f"Sessions Discovered: {len(session_dates)} | Dry Run: {dry_run}", flush=True)
        print(f"Destination: {self.output_prep}", flush=True)
        print("=======================================================\n", flush=True)

        results = []
        total_captures = 0
        total_rows = 0
        total_quarantined = 0
        all_quarantined = []

        t_start = time.perf_counter()

        for idx, td in enumerate(session_dates, 1):
            t0 = time.perf_counter()
            res = self.compact_session(td, sessions[td], dry_run=dry_run)
            t_session = (time.perf_counter() - t0) * 1000

            results.append(res)
            total_captures += res["captures_count"]
            total_rows += res["rows_count"]
            total_quarantined += res["quarantined_count"]
            all_quarantined.extend(res.get("quarantined_items", []))

            print(
                f"  [{idx:03d}/{len(session_dates):03d}] Date {td} | "
                f"Captures: {res['captures_count']:>4} | "
                f"Rows: {res['rows_count']:>7,} | "
                f"Quarantined: {res['quarantined_count']} | {t_session:>6.1f}ms",
                flush=True,
            )

        total_elapsed = time.perf_counter() - t_start

        # Persist quarantine records if any were detected and not in dry-run
        if not dry_run and all_quarantined:
            self.quarantine_dir.mkdir(parents=True, exist_ok=True)
            quarantine_path = self.quarantine_dir / "quarantine_report.json"
            with open(quarantine_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "total_quarantined": len(all_quarantined),
                        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                        "quarantined_files": all_quarantined,
                    },
                    f,
                    indent=2,
                )
            print(f"\nQuarantine report persisted: {quarantine_path} ({len(all_quarantined)} files)", flush=True)

        print(f"\nCompaction complete in {total_elapsed:.2f}s.", flush=True)
        print(f"Total Captures: {total_captures:,} | Total Rows: {total_rows:,} | Quarantined: {total_quarantined}", flush=True)

        return {
            "source_dir": str(self.source_dir).replace("\\", "/"),
            "destination_dir": str(self.output_prep).replace("\\", "/"),
            "total_sessions": len(session_dates),
            "total_captures_compacted": total_captures,
            "total_rows_compacted": total_rows,
            "total_quarantined": total_quarantined,
            "quarantined_files": all_quarantined,
            "elapsed_seconds": round(total_elapsed, 2),
            "results": results,
        }


def main():
    """
    1. The use of function:
       CLI entry point for snapshot compaction.

    2. How does the specific function work:
       Parses command line arguments, instantiates SnapshotCompactor, and executes run().

    3. Concepts used in the function:
       Command-line interface argument parsing.

    4. Places where this function is imported and used:
       Executed when compact_option_snapshots.py is called from shell or scripts.

    5. Final output of the function, before and after:
       Before: Command-line arguments. After: Executed compaction run.
    """
    parser = argparse.ArgumentParser(description="Compact option snapshot CSVs into daily Parquet tables in staging.")
    parser.add_argument("--source-dir", type=Path, default=None, help="Root path of raw option chain snapshots.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Destination staging root directory.")
    parser.add_argument("--quarantine-dir", type=Path, default=None, help="Directory for quarantine audit json.")
    parser.add_argument("--max-sessions", type=int, default=None, help="Limit number of sessions to compact.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate compaction without writing Parquet files.")
    args = parser.parse_args()

    compactor = SnapshotCompactor(
        source_dir=args.source_dir,
        output_prep_dir=args.output_dir,
        quarantine_dir=args.quarantine_dir,
    )
    compactor.run(max_sessions=args.max_sessions, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
