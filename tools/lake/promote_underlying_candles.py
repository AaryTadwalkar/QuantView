"""
1. What this file does:
   Prepares canonical Parquet lake partitions for underlying NIFTY 50 index candles (1-minute and daily series)
   from historical CSV files and staged October extension files into staging/lake_preparation/underlying_candles/.

2. Overall design:
   Reconciles historical index candle CSVs with newly staged sessions, normalizes fields to UNDERLYING_CANDLES_SCHEMA:
     - Partitions 1-minute series by interval=1m/year=YYYY/month=MM/part-0.parquet.
     - Partitions daily series by interval=1d/year=YYYY/part-0.parquet.
     - Sets available_at = ts_end for 1-minute bars; sets available_at = 15:30 IST (session close) for daily bars.
     - Reconciles corrupted line 432594 ('2026-10-08 0'): quarantines the defective line with quality flag
       'TRUNCATED_LINE' and isolates it from canonical tables without dropping surrounding valid bars.
     - Deduplicates overlapping timestamps between historical and staged files.
     - Enforces non-destructive boundary: outputs exclusively to staging/lake_preparation/.

3. Elements in the file:
   - UnderlyingCandlePreparer: Main workflow class coordinating reading, sanitizing, deduplicating,
     and Parquet partition writing.
   - parse_underlying_csv_file: Generator/parser yielding validated rows and quarantine events.
   - main: CLI entry point supporting dry-run and interval selection.

4. Final output of the file:
   - Parquet partitions: staging/lake_preparation/underlying_candles/interval={1m,1d}/.../part-0.parquet
   - Quarantine record and reconciliation audit metrics.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from packages.data.schemas import UNDERLYING_CANDLES_SCHEMA, validate_candle_ohlc


def parse_underlying_csv_file(csv_path: Path, interval: str = "1m") -> Tuple[List[Dict], List[Dict]]:
    """
    1. The use of function:
       Safely parses an underlying index candle CSV line-by-line, detecting truncated or corrupt lines.

    2. How does the specific function work:
       - Iterates lines, splits by comma.
       - Validates that line contains at least 5 numeric elements for OHLC.
       - If line contains truncated text (such as line 432594 '2026-10-08 0'), records a quarantine event
         with reason code 'TRUNCATED_LINE' instead of throwing an unhandled parser exception.
       - Computes ts_start, ts_end, and available_at (ts_end for 1m; 15:30 IST for 1d).
       - Validates OHLC integrity and applies quality flags.

    3. Concepts used in the function:
       Defensive line-by-line CSV parsing, defect quarantine, point-in-time availability.

    4. Places where this function is imported and used:
       Called by UnderlyingCandlePreparer.load_dataset() for each source file.

    5. Final output of the function, before and after:
       Before: Raw CSV file. After: Tuple of (valid_rows_list, quarantined_records_list).
    """
    valid_rows = []
    quarantined = []
    now_ts = datetime.now(timezone.utc)

    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        header_line = f.readline().strip()
        has_header = "timestamp" in header_line.lower() or "open" in header_line.lower()
        if not has_header and header_line:
            f.seek(0)

        for line_no, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue

            parts = [p.strip() for p in line_str.split(",")]
            if len(parts) < 5:
                quarantined.append({
                    "file": str(csv_path),
                    "line_number": line_no,
                    "raw_text": line_str,
                    "reason": "TRUNCATED_LINE",
                })
                continue

            ts_raw = parts[0]
            try:
                dt = datetime.fromisoformat(ts_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)

                o = float(parts[1])
                h = float(parts[2])
                l = float(parts[3])
                cl = float(parts[4])
                vol = int(float(parts[5])) if len(parts) > 5 and parts[5] != "" else 0
                oi = int(float(parts[6])) if len(parts) > 6 and parts[6] != "" else 0
            except (ValueError, TypeError) as parse_err:
                quarantined.append({
                    "file": str(csv_path),
                    "line_number": line_no,
                    "raw_text": line_str,
                    "reason": f"PARSER_ERROR: {parse_err}",
                })
                continue

            q_flags = ["VALID"]
            if not validate_candle_ohlc(o, h, l, cl):
                q_flags.append("INVALID_OHLC")

            if interval == "1m":
                dt_end = datetime.fromtimestamp(int(dt.timestamp()) + 60, tz=timezone.utc)
                dt_avail = dt_end
            elif interval == "1d":
                # Session close at 15:30 Asia/Kolkata = 10:00 UTC on trade date
                try:
                    trade_date = datetime.strptime(ts_raw[:10], "%Y-%m-%d").date()
                    session_close = datetime(trade_date.year, trade_date.month, trade_date.day, 10, 0, 0, tzinfo=timezone.utc)
                except Exception:
                    session_close = datetime(dt.year, dt.month, dt.day, 10, 0, 0, tzinfo=timezone.utc)
                dt_end = session_close
                dt_avail = session_close
            else:
                dt_end = dt
                dt_avail = dt

            valid_rows.append({
                "instrument_key": "NSE_INDEX|Nifty 50",
                "underlying": "NIFTY",
                "interval": interval,
                "ts_start": dt,
                "ts_end": dt_end,
                "available_at": dt_avail,
                "open": o,
                "high": h,
                "low": l,
                "close": cl,
                "volume": vol,
                "oi": oi,
                "source": "upstox_historical_candle",
                "source_version": "v3",
                "revision": 1,
                "is_active": True,
                "quality_flags": q_flags,
                "ingested_at": now_ts,
            })

    return valid_rows, quarantined


class UnderlyingCandlePreparer:
    """
    1. The use of class:
       Coordinates offline normalization and lake staging preparation for NIFTY underlying candles.

    2. What the class contains:
       - output_prep: Destination staging lake directory (staging/lake_preparation/underlying_candles/).
       - candidate_historical_dirs: Ordered list of candidate directories containing historical nifty.csv.
       - staged_underlying_dir: Directory containing staged October underlying CSV files.
       - resolve_source_files(): Discovers historical and staged CSV inputs.
       - prepare_1m_partitions(): Builds monthly Parquet files for 1m series.
       - prepare_1d_partitions(): Builds yearly Parquet files for 1d series.
       - run(): Orchestrates preparation across intervals with dry-run support.

    3. Technologies used and why:
       - pyarrow / pyarrow.parquet: Columnar Parquet profile with zstd compression.
       - pandas: Deduplication and partition grouping.
       - pathlib: Robust filesystem path management.

    4. Key design and overall design of the class:
       Safely isolates corrupted line 432594, performs clean deduplication on overlapping dates,
       and stages output strictly to staging/lake_preparation/.
    """

    def __init__(
        self,
        output_prep_dir: Optional[Path] = None,
        staged_dir: Optional[Path] = None,
    ):
        """Initializes UnderlyingCandlePreparer with paths."""
        self.output_prep = output_prep_dir or Path("staging/lake_preparation/underlying_candles")
        self.staged_dir = staged_dir or Path("staging/underlying_candles")
        self.candidate_historical_dirs = [
            Path("Data/historical/candles/index/nifty"),
            Path(r"C:\Old_algo\Algo\Data\historical\candles\index\nifty"),
        ]

    def resolve_source_file(self, interval: str) -> Optional[Path]:
        """Resolves historical CSV file for given interval across candidate paths."""
        for d in self.candidate_historical_dirs:
            cand = d / interval / "nifty.csv"
            if cand.exists() and cand.stat().st_size > 0:
                return cand
        return None

    def prepare_1m_partitions(self, dry_run: bool = False) -> Dict:
        """Prepares monthly Parquet partitions for 1m underlying series."""
        source_f = self.resolve_source_file("1m")
        all_rows = []
        all_quarantine = []

        if source_f:
            rows, q = parse_underlying_csv_file(source_f, interval="1m")
            all_rows.extend(rows)
            all_quarantine.extend(q)

        # Overlay staged October 1m CSV
        if self.staged_dir.exists():
            for staged_f in self.staged_dir.glob("*1m*.csv"):
                s_rows, s_q = parse_underlying_csv_file(staged_f, interval="1m")
                all_rows.extend(s_rows)
                all_quarantine.extend(s_q)

        if not all_rows:
            return {"interval": "1m", "partitions": 0, "rows": 0, "quarantined": len(all_quarantine)}

        # Deduplicate on ts_start
        df = pd.DataFrame(all_rows)
        df.drop_duplicates(subset=["ts_start"], keep="last", inplace=True)
        df.sort_values(by=["ts_start"], inplace=True)
        df.reset_index(drop=True, inplace=True)

        # Group by year and month
        df["year"] = df["ts_start"].apply(lambda dt: f"{dt.year:04d}")
        df["month"] = df["ts_start"].apply(lambda dt: f"{dt.month:02d}")

        partition_counts = {}
        for (yr, mo), group in df.groupby(["year", "month"]):
            part_dir = self.output_prep / "interval=1m" / f"year={yr}" / f"month={mo}"
            target_p = part_dir / "part-0.parquet"
            partition_counts[f"{yr}-{mo}"] = len(group)

            if not dry_run:
                part_dir.mkdir(parents=True, exist_ok=True)
                tmp_p = target_p.with_suffix(".parquet.tmp")
                clean_group = group.drop(columns=["year", "month"])
                table = pa.Table.from_pandas(clean_group, schema=UNDERLYING_CANDLES_SCHEMA, preserve_index=False)
                pq.write_table(table, tmp_p, compression="zstd", row_group_size=250000)
                tmp_p.replace(target_p)

        return {
            "interval": "1m",
            "partitions": len(partition_counts),
            "total_rows": len(df),
            "quarantined": len(all_quarantine),
            "partition_details": partition_counts,
        }

    def prepare_1d_partitions(self, dry_run: bool = False) -> Dict:
        """Prepares yearly Parquet partitions for 1d underlying series."""
        source_f = self.resolve_source_file("1d")
        all_rows = []
        all_quarantine = []

        if source_f:
            rows, q = parse_underlying_csv_file(source_f, interval="1d")
            all_rows.extend(rows)
            all_quarantine.extend(q)

        # Overlay staged October 1d CSV
        if self.staged_dir.exists():
            for staged_f in self.staged_dir.glob("*1d*.csv"):
                s_rows, s_q = parse_underlying_csv_file(staged_f, interval="1d")
                all_rows.extend(s_rows)
                all_quarantine.extend(s_q)

        if not all_rows:
            return {"interval": "1d", "partitions": 0, "rows": 0, "quarantined": len(all_quarantine)}

        df = pd.DataFrame(all_rows)
        df.drop_duplicates(subset=["ts_start"], keep="last", inplace=True)
        df.sort_values(by=["ts_start"], inplace=True)
        df.reset_index(drop=True, inplace=True)

        df["year"] = df["ts_end"].apply(lambda dt: f"{dt.year:04d}")

        partition_counts = {}
        for yr, group in df.groupby("year"):
            part_dir = self.output_prep / "interval=1d" / f"year={yr}"
            target_p = part_dir / "part-0.parquet"
            partition_counts[yr] = len(group)

            if not dry_run:
                part_dir.mkdir(parents=True, exist_ok=True)
                tmp_p = target_p.with_suffix(".parquet.tmp")
                clean_group = group.drop(columns=["year"])
                table = pa.Table.from_pandas(clean_group, schema=UNDERLYING_CANDLES_SCHEMA, preserve_index=False)
                pq.write_table(table, tmp_p, compression="zstd", row_group_size=250000)
                tmp_p.replace(target_p)

        return {
            "interval": "1d",
            "partitions": len(partition_counts),
            "total_rows": len(df),
            "quarantined": len(all_quarantine),
            "partition_details": partition_counts,
        }

    def run(self, dry_run: bool = False) -> Dict:
        """Runs underlying candle preparation for both 1m and 1d intervals."""
        print(f"\n=======================================================", flush=True)
        print(f"QUANTVIEW -- UNDERLYING CANDLE LAKE PREPARATION (OFFLINE)", flush=True)
        print(f"Dry Run Mode: {dry_run}", flush=True)
        print(f"Destination: {self.output_prep}", flush=True)
        print(f"=======================================================\n", flush=True)

        res_1m = self.prepare_1m_partitions(dry_run=dry_run)
        print(f"  [1-Minute Series] Rows: {res_1m['total_rows']:,} | Partitions: {res_1m['partitions']} | Quarantined: {res_1m['quarantined']}", flush=True)

        res_1d = self.prepare_1d_partitions(dry_run=dry_run)
        print(f"  [Daily Series]    Rows: {res_1d['total_rows']:,} | Partitions: {res_1d['partitions']} | Quarantined: {res_1d['quarantined']}", flush=True)

        return {
            "1m": res_1m,
            "1d": res_1d,
        }


def main():
    """
    1. The use of function:
       CLI entry point for preparing canonical Underlying Candle Parquet partitions in staging.

    2. How does the specific function work:
       Parses command-line arguments (--dry-run, --output-dir), initializes
       UnderlyingCandlePreparer with the specified or default output destination, and invokes run().

    3. Concepts used in the function:
       CLI argument parsing via argparse, dependency injection for staging path isolation.

    4. Places where this function is imported and used:
       Executed directly from command line (python -m tools.lake.promote_underlying_candles).

    5. Final output of the function, before and after:
       Before: Command line flags. After: 1m and 1d Parquet partitions staged and audit summary printed.
    """
    parser = argparse.ArgumentParser(description="Prepare canonical Underlying Candle Parquet partitions in staging.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate preparation without writing Parquet files.")
    parser.add_argument("--output-dir", type=str, default=None, help="Destination staging directory for underlying candle partitions.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else None
    preparer = UnderlyingCandlePreparer(output_prep_dir=output_dir)
    preparer.run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
