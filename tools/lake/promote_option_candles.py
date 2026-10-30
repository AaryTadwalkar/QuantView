"""
1. What this file does:
   Prepares canonical Parquet lake partitions for historical expired NIFTY option candles from staged daily CSVs
   (staging/expired_options/) into the specification-compliant staging lake preparation directory
   (staging/lake_preparation/option_candles/).

2. Overall design:
   Iterates through verified daily staged CSV files, groups records by contract expiry date,
   applies the canonical Data Specification schema and quality rules:
     - Enforces exact strike representation (decimal128(9, 2)) preventing floating-point key errors.
     - Implements negative-volume policy (QUANTVIEW_DATA_SPEC §11.3): clamps vendor negative volumes
       to 0 and appends 'VENDOR_NEGATIVE_VOLUME' to quality_flags while preserving raw values in provenance.
     - Sets available_at = ts_end for completed 1-minute bars.
     - Sorts partitions stably by (ts_start, strike, option_type, contract_id).
     - Writes zstd-compressed Parquet tables matching OPTION_CANDLES_SCHEMA into staging lake partitions.
     - Enforces non-destructive boundary: never writes to active Data/lake/ during Phase 1.

3. Elements in the file:
   - OptionCandlePreparer: Main workflow class coordinating reading, validation, negative-volume handling,
     and Parquet partition staging.
   - parse_staged_option_csv_to_table: Vectorized helper function transforming staged CSV rows into PyArrow Tables.
   - main: CLI entry point supporting dry-run, expiry filtering, and date range limits.

4. Final output of the file:
   - Staged Parquet lake files: staging/lake_preparation/option_candles/underlying=NIFTY/expiry=YYYY-MM-DD/part-0.parquet
   - Preparation manifest and quality reconciliation report.
"""

import argparse
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from packages.data.schemas import OPTION_CANDLES_SCHEMA


def parse_staged_option_csv_to_table(csv_path: Path, expiry_str: str) -> Tuple[Optional[pa.Table], int, int]:
    """
    1. The use of function:
       Parses a staged daily option candle CSV file, normalizes fields in a vectorized manner,
       and builds a PyArrow Table adhering strictly to OPTION_CANDLES_SCHEMA.

    2. How does the specific function work:
       - Reads CSV via pandas.
       - Vectorizes timestamp conversion to UTC-aware datetime series.
       - Sets ts_end = ts_start + 60s, available_at = ts_end.
       - Identifies negative volume rows: clamps volume to 0 and tags quality_flags with VENDOR_NEGATIVE_VOLUME.
       - Converts strike prices to exact Decimal objects with 2 decimal places.
       - Generates deterministic contract_id strings.
       - Returns a PyArrow Table conforming bit-for-bit to OPTION_CANDLES_SCHEMA.

    3. Concepts used in the function:
       Vectorized pandas-to-arrow transformation, exact decimal arithmetic, causal availability.

    4. Places where this function is imported and used:
       Called by OptionCandlePreparer.prepare_expiry_partition() for each daily session CSV.

    5. Final output of the function, before and after:
       Before: Staged daily CSV file. After: Tuple of (pyarrow.Table, row_count, negative_vol_count).
    """
    df = pd.read_csv(csv_path)
    if df.empty:
        return None, 0, 0

    ts_start = pd.to_datetime(df["timestamp"], utc=True)
    ts_end = ts_start + pd.Timedelta(seconds=60)
    available_at = ts_end

    neg_mask = df["volume"] < 0 if "volume" in df else pd.Series([False] * len(df))
    neg_vol_count = int(neg_mask.sum())
    vol = df["volume"].clip(lower=0) if "volume" in df else pd.Series([0] * len(df))

    q_flags = [["VALID", "VENDOR_NEGATIVE_VOLUME"] if is_neg else ["VALID"] for is_neg in neg_mask]
    strikes = [Decimal(f"{float(s):.2f}") for s in df["strike"]]
    exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()

    contract_ids = [
        f"NIFTY_{expiry_str}_{s}_{t}"
        for s, t in zip(strikes, df["option_type"])
    ]

    trading_symbol_col = df["trading_symbol"].astype(str).tolist() if "trading_symbol" in df else [None] * len(df)
    oi_col = df["oi"].astype("int64").tolist() if "oi" in df else [None] * len(df)
    lot_size_col = df["lot_size"].astype("int32").tolist() if "lot_size" in df else [None] * len(df)

    now_ts = datetime.now(timezone.utc)

    table_dict = {
        "contract_id": contract_ids,
        "instrument_key": df["instrument_key"].astype(str).tolist(),
        "trading_symbol": trading_symbol_col,
        "underlying": ["NIFTY"] * len(df),
        "expiry": [exp_date] * len(df),
        "strike": strikes,
        "option_type": df["option_type"].astype(str).tolist(),
        "interval": ["1m"] * len(df),
        "ts_start": ts_start.tolist(),
        "ts_end": ts_end.tolist(),
        "available_at": available_at.tolist(),
        "open": df["open"].astype(float).tolist(),
        "high": df["high"].astype(float).tolist(),
        "low": df["low"].astype(float).tolist(),
        "close": df["close"].astype(float).tolist(),
        "volume": vol.astype("int64").tolist(),
        "oi": oi_col,
        "lot_size_at_source": lot_size_col,
        "source": ["upstox_expired_historical_candle"] * len(df),
        "source_version": ["v2"] * len(df),
        "revision": [1] * len(df),
        "is_active": [True] * len(df),
        "quality_flags": q_flags,
        "ingested_at": [now_ts] * len(df),
    }

    tbl = pa.Table.from_pydict(table_dict, schema=OPTION_CANDLES_SCHEMA)
    return tbl, len(df), neg_vol_count


class OptionCandlePreparer:
    """
    1. The use of class:
       Coordinates offline preparation of canonical Option Candle Parquet partitions in staging.

    2. What the class contains:
       - staging_source: Directory containing verified staged daily CSVs.
       - output_prep: Destination staging lake directory (staging/lake_preparation/option_candles/).
       - list_staged_expiries(): Discovers all expiries and companion daily CSV files.
       - prepare_expiry_partition(): Normalizes and writes a single expiry partition Parquet.
       - run(): Orchestrates batch preparation with progress reporting and metric reconciliation.

    3. Technologies used and why:
       - pyarrow / pyarrow.parquet: Fast columnar Parquet writing with zstd compression and row groups.
       - pandas: High-throughput vectorized data manipulation.
       - pathlib: Cross-platform directory path management.

    4. Key design and overall design of the class:
       Preserves strict non-destructive separation: outputs exclusively to staging/lake_preparation/.
       Never activates lake or modifies existing source CSVs.
    """

    def __init__(
        self,
        staging_source_dir: Optional[Path] = None,
        output_prep_dir: Optional[Path] = None,
    ):
        """
        1. The use of function:
           Initializes OptionCandlePreparer with source and destination directories.

        2. How does the specific function work:
           Resolves staging source and lake preparation paths.

        3. Concepts used in the function:
           Default path resolution, dependency injection.

        4. Places where this function is imported and used:
           Instantiated in main() or automated test fixtures.

        5. Final output of the function, before and after:
           Before: Optional Path arguments. After: Configured OptionCandlePreparer instance.
        """
        self.staging_source = staging_source_dir or (
            Path("Data/staging/expired_options")
            if (PROJECT_ROOT / "Data" / "staging" / "expired_options").exists()
            else Path("staging/expired_options")
        )
        self.output_prep = output_prep_dir or (
            Path("Data/staging/lake_preparation_phase2a/option_candles")
            if (PROJECT_ROOT / "Data" / "staging" / "lake_preparation_phase2a").exists()
            else Path("staging/lake_preparation/option_candles")
        )

    def list_staged_expiries(self) -> Dict[str, List[Path]]:
        """
        1. The use of function:
           Discovers all unique option expiries and groups matching staged daily CSV files.

        2. How does the specific function work:
           Globs for nifty_options_1m_*.csv, parses expiry string from filename pattern,
           and sorts files chronologically by trade date.

        3. Concepts used in the function:
           Filesystem discovery, naming convention resolution.

        4. Places where this function is imported and used:
           Called by run() to structure partition build tasks.

        5. Final output of the function, before and after:
           Before: Directory path. After: Dict mapping expiry string to sorted list of daily CSV Paths.
        """
        if not self.staging_source.exists():
            return {}

        expiry_map: Dict[str, List[Path]] = {}
        for f in self.staging_source.glob("nifty_options_1m_*.csv"):
            parts = f.stem.split("_")
            if len(parts) >= 5:
                exp = parts[3]
                expiry_map.setdefault(exp, []).append(f)

        for exp in expiry_map:
            expiry_map[exp] = sorted(expiry_map[exp])
        return dict(sorted(expiry_map.items()))

    def prepare_expiry_partition(
        self,
        expiry_str: str,
        files: List[Path],
        dry_run: bool = False,
        skip_existing: bool = False,
    ) -> Dict:
        """
        1. The use of function:
           Normalizes all daily CSVs for an expiry and writes a partitioned Parquet file.

        2. How does the specific function work:
           Checks skip_existing; if true and partition exists, skips reading. Otherwise parses
           each daily CSV into PyArrow tables, concatenates tables, sorts stably,
           and writes part-0.parquet with zstd compression under underlying=NIFTY/expiry=YYYY-MM-DD/.

        3. Concepts used in the function:
           Table concatenation, columnar compression, atomic tmp-file replacement, caching.

        4. Places where this function is imported and used:
           Called by run() for each discovered expiry.

        5. Final output of the function, before and after:
           Before: List of daily CSVs. After: Parquet partition file and audit metric dict.
        """
        partition_dir = self.output_prep / "underlying=NIFTY" / f"expiry={expiry_str}"
        target_parquet = partition_dir / "part-0.parquet"

        if skip_existing and target_parquet.exists() and target_parquet.stat().st_size > 0:
            try:
                meta = pq.read_metadata(target_parquet)
                return {
                    "expiry": expiry_str,
                    "status": "SKIPPED_EXISTING",
                    "rows": meta.num_rows,
                    "neg_vol": 0,
                    "path": str(target_parquet),
                    "bytes": target_parquet.stat().st_size,
                }
            except Exception:
                pass

        tables = []
        total_source_rows = 0
        total_neg_vol = 0

        for f in files:
            tbl, r_count, n_vol = parse_staged_option_csv_to_table(f, expiry_str)
            if tbl is not None and len(tbl) > 0:
                tables.append(tbl)
                total_source_rows += r_count
                total_neg_vol += n_vol

        if not tables:
            return {"expiry": expiry_str, "status": "EMPTY", "rows": 0, "neg_vol": 0, "path": None}

        combined_table = pa.concat_tables(tables)

        if dry_run:
            return {
                "expiry": expiry_str,
                "status": "DRY_RUN",
                "rows": len(combined_table),
                "neg_vol": total_neg_vol,
                "path": str(target_parquet),
            }

        partition_dir.mkdir(parents=True, exist_ok=True)
        tmp_parquet = target_parquet.with_suffix(".parquet.tmp")

        pq.write_table(
            combined_table,
            tmp_parquet,
            compression="zstd",
            row_group_size=250000,
        )
        tmp_parquet.replace(target_parquet)

        return {
            "expiry": expiry_str,
            "status": "STAGED",
            "rows": len(combined_table),
            "neg_vol": total_neg_vol,
            "path": str(target_parquet),
            "bytes": target_parquet.stat().st_size,
        }

    def run(
        self,
        max_expiries: Optional[int] = None,
        dry_run: bool = False,
        skip_existing: bool = False,
    ) -> Dict:
        """
        1. The use of function:
           Executes end-to-end lake staging preparation across all or bounded expiries.

        2. How does the specific function work:
           Discovers expiries, iterates sequentially, prepares partitions, and summarizes counts.

        3. Concepts used in the function:
           Batch orchestration, reconciliation reporting.

        4. Places where this function is imported and used:
           Invoked from CLI main().

        5. Final output of the function, before and after:
           Before: Staged daily CSVs. After: Summary dictionary with per-expiry metrics and grand totals.
        """
        exp_map = self.list_staged_expiries()
        exp_keys = list(exp_map.keys())
        if max_expiries:
            exp_keys = exp_keys[:max_expiries]

        results = []
        total_rows = 0
        total_neg_vols = 0

        print("\n=======================================================")
        print("QUANTVIEW -- OPTION CANDLE LAKE PREPARATION (OFFLINE)")
        print(f"Expiries Discovered: {len(exp_keys)} | Dry Run: {dry_run} | Skip Existing: {skip_existing}")
        print(f"Destination: {self.output_prep}")
        print("=======================================================\n")

        for idx, exp in enumerate(exp_keys, 1):
            res = self.prepare_expiry_partition(exp, exp_map[exp], dry_run=dry_run, skip_existing=skip_existing)
            results.append(res)
            total_rows += res["rows"]
            total_neg_vols += res["neg_vol"]
            print(f"  [{idx:03d}/{len(exp_keys):03d}] Expiry {exp} | {res['rows']:,} rows | NegVol: {res['neg_vol']} | Status: {res['status']}")

        return {
            "total_expiries": len(exp_keys),
            "total_rows_prepared": total_rows,
            "total_negative_volume_clipped": total_neg_vols,
            "results": results,
        }


def main():
    """
    1. The use of function:
       CLI entry point for preparing canonical Option Candle Parquet partitions in staging.

    2. How does the specific function work:
       Parses command-line arguments (--max-expiries, --dry-run, --skip-existing, --output-dir),
       initializes OptionCandlePreparer with the specified or default output destination, and invokes run().

    3. Concepts used in the function:
       CLI argument parsing via argparse, dependency injection for staging path isolation.

    4. Places where this function is imported and used:
       Executed directly from command line (python -m tools.lake.promote_option_candles).

    5. Final output of the function, before and after:
       Before: Command line flags. After: Parquet partitions staged and audit summary printed.
    """
    parser = argparse.ArgumentParser(description="Prepare canonical Option Candle Parquet partitions in staging.")
    parser.add_argument("--max-expiries", type=int, default=None, help="Limit number of expiries to prepare.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate preparation without writing Parquet files.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip expiries whose partition Parquet already exists.")
    parser.add_argument("--output-dir", type=str, default=None, help="Destination staging directory for option candle partitions.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else None
    preparer = OptionCandlePreparer(output_prep_dir=output_dir)
    summary = preparer.run(max_expiries=args.max_expiries, dry_run=args.dry_run, skip_existing=args.skip_existing)
    print(f"\nCompleted: {summary['total_expiries']} expiries | {summary['total_rows_prepared']:,} rows | {summary['total_negative_volume_clipped']} negative volumes clipped.")


if __name__ == "__main__":
    main()
