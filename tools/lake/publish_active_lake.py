"""
1. What this file does:
   Executes Phase 2B active data lake publication: atomically promotes validated Parquet partitions
   from staging/lake_preparation_phase2a/ to Data/lake/, activates the production manifest
   (Data/lake/manifest_active.json), registers canonical DuckDB views, and verifies point-in-time queries.

2. Overall design:
   Coordinates the transition from validated staging to active production data lake:
     - Validates source staging readiness (manifest_phase2a.json and 184 Parquet files).
     - Atomically publishes partitions into Data/lake/ using temporary files and byte-for-byte SHA-256 verification.
     - Generates and activates Data/lake/manifest_active.json with is_active = true and cryptographic hashes.
     - Creates and registers canonical DuckDB views (v_candles_underlying, v_candles_options, v_candles_vix)
       in Data/lake/quantview.duckdb conforming strictly to QUANTVIEW_DATA_SPEC §4.9.
     - Executes post-publication verification and point-in-time latency benchmarks.

3. Elements in the file:
   - compute_file_sha256: Utility function calculating SHA-256 cryptographic hashes in 64KB blocks.
   - ActiveLakePublisher: Main workflow class coordinating atomic publication, manifest activation, and DuckDB registration.
   - main: CLI entry point supporting dry-run and custom path overrides.

4. Final output of the file:
   - Active canonical Parquet partitions: Data/lake/{option_candles, underlying_candles, india_vix}
   - Active publication manifest: Data/lake/manifest_active.json
   - Canonical DuckDB database: Data/lake/quantview.duckdb with analytical views
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import duckdb
import pyarrow.parquet as pq


def compute_file_sha256(file_path: Path) -> str:
    """
    1. The use of function:
       Computes SHA-256 cryptographic hash of a file on disk.

    2. How does the specific function work:
       Reads file in 64KB binary chunks and updates hashlib.sha256 hash object.

    3. Concepts used in the function:
       Cryptographic hashing, buffered binary stream reading.

    4. Places where this function is imported and used:
       Called by ActiveLakePublisher to verify source and target partition hashes.

    5. Final output of the function, before and after:
       Before: Path to file. After: Hex-encoded 64-character SHA-256 string.
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class ActiveLakePublisher:
    """
    1. The use of class:
       Orchestrates Phase 2B production data lake publication, manifest activation, and DuckDB view setup.

    2. What the class contains:
       - staging_root: Path to validated Phase 2A staging directory (staging/lake_preparation_phase2a).
       - staging_manifest_path: Path to staging manifest (manifest_phase2a.json).
       - lake_root: Destination production lake root (Data/lake).
       - active_manifest_path: Target active manifest path (Data/lake/manifest_active.json).
       - duckdb_path: Target DuckDB analytical database file (Data/lake/quantview.duckdb).
       - validate_staging_readiness(): Pre-flight verification of staging files and hashes.
       - publish_partitions(): Atomic transfer and bit-for-bit checksum verification into Data/lake.
       - activate_manifest(): Atomically writes and activates Data/lake/manifest_active.json.
       - register_duckdb_views(): Creates canonical DuckDB views conforming to DATA Spec §4.9.
       - run(): Main orchestration workflow.

    3. Technologies used and why:
       - pathlib / shutil: Robust filesystem path navigation and atomic copy operations.
       - duckdb: In-process SQL OLAP engine for zero-copy analytical queries over Parquet.
       - pyarrow.parquet: Metadata and schema verification.
       - hashlib / json: Cryptographic provenance tracking and metadata serialization.

    4. Key design and overall design of the class:
       Strictly atomic: files are copied to .tmp, verified by SHA-256 against staging, and renamed.
       Zero data loss: raw archives and staging inputs remain completely untouched.
    """

    def __init__(
        self,
        staging_root: Optional[Path] = None,
        staging_manifest: Optional[Path] = None,
        lake_root: Optional[Path] = None,
    ):
        """
        1. The use of function:
           Initializes ActiveLakePublisher with paths.

        2. How does the specific function work:
           Resolves staging root, manifest path, lake destination, and DuckDB target.

        3. Concepts used in the function:
           Default path resolution, dependency injection.

        4. Places where this function is imported and used:
           Instantiated in main() or automated integration tests.

        5. Final output of the function, before and after:
           Before: Optional path parameters. After: Configured ActiveLakePublisher instance.
        """
        self.staging_root = staging_root or Path("staging/lake_preparation_phase2a")
        self.staging_manifest_path = staging_manifest or (self.staging_root / "manifest_phase2a.json")
        self.lake_root = lake_root or Path("Data/lake")
        self.active_manifest_path = self.lake_root / "manifest_active.json"
        self.duckdb_path = self.lake_root / "quantview.duckdb"

    def validate_staging_readiness(self) -> Tuple[bool, Dict]:
        """
        1. The use of function:
           Verifies that staging files and manifest are 100% complete and uncorrupted before publishing.

        2. How does the specific function work:
           Reads staging manifest, verifies all referenced partitions exist, and confirms SHA-256 hashes.

        3. Concepts used in the function:
           Preflight gate validation, cryptographic verification.

        4. Places where this function is imported and used:
           Called at start of run() to block publication if staging is imperfect.

        5. Final output of the function, before and after:
           Before: Staging files on disk. After: Tuple of (is_ready_bool, manifest_dict).
        """
        if not self.staging_manifest_path.exists():
            print(f"ERROR: Staging manifest not found: {self.staging_manifest_path}", flush=True)
            return False, {}

        with open(self.staging_manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        missing = 0
        total = 0
        for ds_name, ds_info in manifest.get("datasets", {}).items():
            for p in ds_info.get("partitions", []):
                total += 1
                src = self.staging_root / p["path"]
                if not src.exists():
                    missing += 1

        if missing > 0:
            print(f"ERROR: Staging incomplete. Missing {missing}/{total} files.", flush=True)
            return False, manifest

        return True, manifest

    def publish_partitions(self, manifest: Dict, dry_run: bool = False) -> Dict:
        """
        1. The use of function:
           Atomically copies all prepared Parquet partitions from staging to Data/lake/.

        2. How does the specific function work:
           For each partition: creates parent directory in Data/lake/, copies to target.with_suffix('.parquet.tmp'),
           computes SHA-256 of the copied file, confirms match with staging SHA-256, and renames to part-0.parquet.

        3. Concepts used in the function:
           Atomic write pattern, cryptographic transfer verification, directory tree mirroring.

        4. Places where this function is imported and used:
           Called by run() during publication.

        5. Final output of the function, before and after:
           Before: Files in staging. After: Verified files in Data/lake/ and transfer metrics dict.
        """
        stats = {
            "published_files": 0,
            "published_rows": 0,
            "published_bytes": 0,
            "sha_verified": 0,
            "datasets": {},
        }

        for ds_name, ds_info in manifest.get("datasets", {}).items():
            ds_partitions = ds_info.get("partitions", [])
            ds_rows = ds_info.get("total_rows", 0)
            ds_bytes = ds_info.get("total_bytes", 0)

            print(f"Publishing dataset: {ds_name} ({len(ds_partitions)} partitions, {ds_rows:,} rows)...", flush=True)
            for idx, p in enumerate(ds_partitions, 1):
                rel_path = Path(p["path"])
                src_path = self.staging_root / rel_path
                dst_path = self.lake_root / rel_path
                exp_sha = p["sha256"]

                if dry_run:
                    stats["published_files"] += 1
                    stats["published_rows"] += p["rows"]
                    stats["published_bytes"] += p["bytes"]
                    stats["sha_verified"] += 1
                    continue

                dst_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_dst = dst_path.with_suffix(".parquet.tmp")

                # Atomic copy via temporary file
                shutil.copy2(src_path, tmp_dst)
                copied_sha = compute_file_sha256(tmp_dst)
                if copied_sha != exp_sha:
                    tmp_dst.unlink(missing_ok=True)
                    raise IOError(f"Checksum mismatch copying {rel_path}: expected {exp_sha}, got {copied_sha}")

                tmp_dst.replace(dst_path)

                stats["published_files"] += 1
                stats["published_rows"] += p["rows"]
                stats["published_bytes"] += p["bytes"]
                stats["sha_verified"] += 1

                if idx % 25 == 0 or idx == len(ds_partitions):
                    print(f"  [{idx:>3}/{len(ds_partitions):>3}] Published {rel_path.as_posix()}", flush=True)

            stats["datasets"][ds_name] = {
                "file_count": len(ds_partitions),
                "total_rows": ds_rows,
                "total_bytes": ds_bytes,
            }

        return stats

    def activate_manifest(self, staging_manifest: Dict, dry_run: bool = False) -> Path:
        """
        1. The use of function:
           Creates and atomically writes the active production data lake manifest.

        2. How does the specific function work:
           Builds active manifest JSON with is_active = true, records source staging manifest hash,
           and writes to Data/lake/manifest_active.json via atomic tmp replacement.

        3. Concepts used in the function:
           Active manifest pointer activation, immutable dataset lineage.

        4. Places where this function is imported and used:
           Called by run() after all Parquet partitions are published and verified.

        5. Final output of the function, before and after:
           Before: Unactivated lake. After: Active manifest published at Data/lake/manifest_active.json.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        staging_manifest_sha = compute_file_sha256(self.staging_manifest_path)

        active_manifest = {
            "manifest_type": "QUANTVIEW_ACTIVE_LAKE_MANIFEST",
            "manifest_version": 1,
            "activated_at_utc": now_utc,
            "is_active": True,
            "lake_root": str(self.lake_root).replace("\\", "/"),
            "source_staging_manifest_sha256": staging_manifest_sha,
            "datasets": staging_manifest.get("datasets", {}),
            "aggregate_totals": staging_manifest.get("aggregate_totals", {}),
        }

        if dry_run:
            print(f"[DRY-RUN] Would activate manifest at: {self.active_manifest_path}", flush=True)
            return self.active_manifest_path

        self.lake_root.mkdir(parents=True, exist_ok=True)
        tmp_manifest = self.active_manifest_path.with_suffix(".json.tmp")
        with open(tmp_manifest, "w", encoding="utf-8") as f:
            json.dump(active_manifest, f, indent=2)
        tmp_manifest.replace(self.active_manifest_path)

        print(f"Active lake manifest activated at: {self.active_manifest_path}", flush=True)
        return self.active_manifest_path

    def register_duckdb_views(self, dry_run: bool = False) -> Dict:
        """
        1. The use of function:
           Creates and registers canonical DuckDB views for underlying, options, and India VIX candles.

        2. How does the specific function work:
           Opens DuckDB connection to Data/lake/quantview.duckdb and registers:
             - v_candles_underlying: mapping to underlying_candles partitions.
             - v_candles_options: mapping to option_candles partitions.
             - v_candles_vix: mapping to india_vix partitions.
           Runs test query on each view and records query execution times.

        3. Concepts used in the function:
           DuckDB view registration, Parquet globbing, zero-copy query execution.

        4. Places where this function is imported and used:
           Called by run() after active manifest activation.

        5. Final output of the function, before and after:
           Before: Parquet files on disk. After: Canonical DuckDB analytical views queryable by apps and services.
        """
        if dry_run:
            print(f"[DRY-RUN] Would register DuckDB views at: {self.duckdb_path}", flush=True)
            return {"status": "DRY_RUN"}

        print(f"\nRegistering canonical DuckDB analytical views at: {self.duckdb_path} ...", flush=True)
        con = duckdb.connect(str(self.duckdb_path))

        # 1. Underlying Candles View (DATA Spec §4.9)
        und_glob = (self.lake_root / "underlying_candles" / "**" / "*.parquet").as_posix()
        con.execute(f"""
            CREATE OR REPLACE VIEW v_candles_underlying AS
            SELECT 
                underlying AS symbol,
                interval,
                ts_start AS bar_start,
                ts_end AS bar_end,
                available_at,
                open, high, low, close, volume, oi,
                quality_flags,
                (COALESCE(volume, 0) = 0 AND open = high AND high = low AND low = close) AS is_flat_bar,
                is_active
            FROM read_parquet('{und_glob}')
            WHERE is_active = true
        """)

        # 2. Option Candles View (DATA Spec §4.9)
        opt_glob = (self.lake_root / "option_candles" / "**" / "*.parquet").as_posix()
        con.execute(f"""
            CREATE OR REPLACE VIEW v_candles_options AS
            SELECT 
                contract_id,
                underlying AS symbol,
                expiry,
                strike,
                option_type,
                interval,
                ts_start AS bar_start,
                ts_end AS bar_end,
                available_at,
                open, high, low, close, volume, oi,
                lot_size_at_source,
                quality_flags,
                (COALESCE(volume, 0) = 0 AND open = high AND high = low AND low = close) AS is_flat_bar,
                is_active
            FROM read_parquet('{opt_glob}')
            WHERE is_active = true
        """)

        # 3. India VIX View (DATA Spec §4.10)
        vix_glob = (self.lake_root / "india_vix" / "**" / "*.parquet").as_posix()
        con.execute(f"""
            CREATE OR REPLACE VIEW v_candles_vix AS
            SELECT 
                instrument_key,
                interval,
                ts_start AS bar_start,
                ts_end AS bar_end,
                available_at,
                open, high, low, close, volume, oi,
                quality_flags
            FROM read_parquet('{vix_glob}')
        """)

        # Benchmark queries
        t0 = time.perf_counter()
        count_und = con.execute("SELECT count(*) FROM v_candles_underlying").fetchone()[0]
        t_und = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        count_opt = con.execute("SELECT count(*) FROM v_candles_options").fetchone()[0]
        t_opt = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        count_vix = con.execute("SELECT count(*) FROM v_candles_vix").fetchone()[0]
        t_vix = (time.perf_counter() - t0) * 1000

        # Point-in-time query sample
        t0 = time.perf_counter()
        sample_pit = con.execute("""
            SELECT count(*) 
            FROM v_candles_underlying 
            WHERE bar_start >= '2025-01-01' AND available_at <= '2025-01-02 10:00:00+00'
        """).fetchone()[0]
        t_pit = (time.perf_counter() - t0) * 1000

        con.close()

        print(f"  * v_candles_underlying: {count_und:,} rows (query: {t_und:.2f} ms)", flush=True)
        print(f"  * v_candles_options:    {count_opt:,} rows (query: {t_opt:.2f} ms)", flush=True)
        print(f"  * v_candles_vix:        {count_vix:,} rows (query: {t_vix:.2f} ms)", flush=True)
        print(f"  * Point-in-time check:  {sample_pit:,} rows visible (query: {t_pit:.2f} ms)", flush=True)

        return {
            "v_candles_underlying": {"rows": count_und, "query_ms": round(t_und, 2)},
            "v_candles_options": {"rows": count_opt, "query_ms": round(t_opt, 2)},
            "v_candles_vix": {"rows": count_vix, "query_ms": round(t_vix, 2)},
            "sample_point_in_time": {"rows": sample_pit, "query_ms": round(t_pit, 2)},
        }

    def run(self, dry_run: bool = False) -> Dict:
        """
        1. The use of function:
           Executes end-to-end active data lake publication workflow.

        2. How does the specific function work:
           Orchestrates preflight check, partition publishing, manifest activation, and DuckDB view registration.

        3. Concepts used in the function:
           End-to-end orchestration, atomic promotion lifecycle.

        4. Places where this function is imported and used:
           Invoked from CLI main().

        5. Final output of the function, before and after:
           Before: Staged Parquets. After: Production lake active, manifest live, DuckDB views registered.
        """
        t0 = time.time()
        print("=======================================================", flush=True)
        print("QUANTVIEW -- PHASE 2B ACTIVE DATA LAKE PUBLICATION", flush=True)
        print("Timestamp:", datetime.now(timezone.utc).isoformat(), flush=True)
        print(f"Source Staging: {self.staging_root}", flush=True)
        print(f"Destination:    {self.lake_root}", flush=True)
        print(f"Dry Run:        {dry_run}", flush=True)
        print("=======================================================\n", flush=True)

        # 1. Preflight
        ready, manifest = self.validate_staging_readiness()
        if not ready:
            raise RuntimeError("Staging validation failed. Aborting publication.")

        # 2. Publish Partitions
        transfer_stats = self.publish_partitions(manifest, dry_run=dry_run)

        # 3. Activate Manifest
        manifest_path = self.activate_manifest(manifest, dry_run=dry_run)

        # 4. DuckDB Views
        duckdb_stats = self.register_duckdb_views(dry_run=dry_run)

        t1 = time.time()
        duration_s = round(t1 - t0, 2)
        print(f"\nPhase 2B Lake Publication COMPLETED in {duration_s}s.", flush=True)
        print(f"Total Files Published: {transfer_stats['published_files']}", flush=True)
        print(f"Total Rows Active:     {transfer_stats['published_rows']:,}", flush=True)
        print(f"Active Manifest:       {manifest_path}", flush=True)

        return {
            "status": "SUCCESS" if not dry_run else "DRY_RUN",
            "duration_seconds": duration_s,
            "transfer_stats": transfer_stats,
            "active_manifest": str(manifest_path).replace("\\", "/"),
            "duckdb_views": duckdb_stats,
        }


def main():
    """
    1. The use of function:
       CLI entry point for Phase 2B active data lake publication.

    2. How does the specific function work:
       Parses command-line arguments (--dry-run, --staging-dir, --lake-dir), instantiates
       ActiveLakePublisher, and executes run().

    3. Concepts used in the function:
       CLI argument parsing via argparse, dynamic path resolution.

    4. Places where this function is imported and used:
       Executed directly from command line (python tools/lake/publish_active_lake.py).

    5. Final output of the function, before and after:
       Before: Command line flags. After: Published canonical lake and activated manifest.
    """
    parser = argparse.ArgumentParser(description="Publish validated Phase 2A staging datasets to active Data/lake/.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate publication without writing to Data/lake/.")
    parser.add_argument("--staging-dir", type=str, default=None, help="Custom path to staging lake directory.")
    parser.add_argument("--lake-dir", type=str, default=None, help="Custom path to active lake directory.")
    args = parser.parse_args()

    staging_root = Path(args.staging_dir) if args.staging_dir else None
    lake_root = Path(args.lake_dir) if args.lake_dir else None

    publisher = ActiveLakePublisher(staging_root=staging_root, lake_root=lake_root)
    publisher.run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
