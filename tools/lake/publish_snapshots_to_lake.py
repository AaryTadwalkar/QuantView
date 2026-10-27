"""
1. What this file does:
   Executes Phase 3 active data lake publication: atomically promotes validated option snapshot Parquet partitions
   from staging/lake_preparation_phase3/ to Data/lake/, activates production manifest v2 (Data/lake/manifest_active.json),
   registers canonical DuckDB snapshot views, and executes point-in-time analytical query benchmarks per QUANTVIEW_DATA_SPEC §4.3, §4.4, §4.8, §4.9.

2. Overall design:
   Coordinates the transition from validated staging to active production data lake:
     - Validates Phase 3 staging readiness (manifest_phase3.json and 252 Parquet partitions).
     - Confirms existing 183 Phase 2B candle files in Data/lake/ are 100% byte-for-byte unchanged.
     - Atomically publishes snapshot partitions into Data/lake/ using temporary files and SHA-256 verification.
     - Archives previous active manifest to Data/lake/manifest_v1_archive.json.
     - Generates and activates Data/lake/manifest_active.json (version 2) linking all 183 candle partitions + 252 snapshot partitions.
     - Creates and registers canonical DuckDB views:
       * v_snapshots_captures: one record per capture with received_at availability time.
       * v_snapshots_rows: strike-level observations with exact Decimal strikes and observed Greeks.
       * v_snapshots_reconstructed_chain: lazy joined point-in-time chain view.
     - Executes post-publication verification and point-in-time latency benchmarks.

3. Elements in the file:
   - compute_file_sha256: Utility function calculating SHA-256 cryptographic hashes in 64KB blocks.
   - SnapshotLakePublisher: Main workflow class coordinating atomic promotion, manifest v2 activation, and DuckDB registration.
   - main: CLI entry point supporting dry-run and directory overrides.

4. Final output of the file:
   - Active Parquet snapshot partitions: Data/lake/{option_snapshot_captures, option_snapshot_rows}
   - Active publication manifest v2: Data/lake/manifest_active.json (435 files, 38,382,546 rows)
   - Archived manifest v1: Data/lake/manifest_v1_archive.json
   - Updated DuckDB database: Data/lake/quantview.duckdb with registered snapshot analytical views.
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
       Called by SnapshotLakePublisher to verify source and target partition hashes.

    5. Final output of the function, before and after:
       Before: Path to file. After: Hex-encoded 64-character SHA-256 string.
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class SnapshotLakePublisher:
    """
    1. The use of class:
       Orchestrates Phase 3 snapshot data lake publication, manifest v2 activation, and DuckDB view setup.

    2. What the class contains:
       - staging_root: Path to validated Phase 3 staging directory (staging/lake_preparation_phase3).
       - staging_manifest_path: Path to staging manifest (manifest_phase3.json).
       - lake_root: Destination production lake root (Data/lake).
       - active_manifest_path: Target active manifest path (Data/lake/manifest_active.json).
       - duckdb_path: Target DuckDB analytical database file (Data/lake/quantview.duckdb).
       - validate_baseline(): Confirms existing 183 Phase 2B candle files are intact.
       - validate_staging_readiness(): Pre-flight verification of 252 staging files and hashes.
       - publish_partitions(): Atomic transfer and bit-for-bit checksum verification into Data/lake.
       - activate_manifest_v2(): Atomically activates manifest v2 combining candle and snapshot datasets.
       - register_duckdb_views(): Creates canonical DuckDB snapshot views conforming to DATA Spec §4.3, §4.4, §4.8.
       - run(): Main orchestration workflow.

    3. Technologies used and why:
       - pathlib / shutil: Robust filesystem path navigation and atomic copy operations.
       - duckdb: In-process SQL OLAP engine for zero-copy analytical queries over Parquet.
       - pyarrow.parquet: Metadata and schema verification.
       - hashlib / json: Cryptographic provenance tracking and metadata serialization.

    4. Key design and overall design of the class:
       Strictly atomic: files are copied to .tmp, verified by SHA-256 against staging, and renamed.
       Zero data loss: candle partitions and staging inputs remain completely untouched.
    """

    def __init__(
        self,
        staging_root: Optional[Path] = None,
        staging_manifest: Optional[Path] = None,
        lake_root: Optional[Path] = None,
    ):
        """Initializes SnapshotLakePublisher with paths."""
        self.staging_root = staging_root or Path("staging/lake_preparation_phase3")
        self.staging_manifest_path = staging_manifest or (self.staging_root / "manifest_phase3.json")
        self.lake_root = lake_root or Path("Data/lake")
        self.active_manifest_path = self.lake_root / "manifest_active.json"
        self.duckdb_path = self.lake_root / "quantview.duckdb"

    def validate_baseline(self) -> Tuple[bool, Dict]:
        """
        1. The use of function:
           Verifies that all existing Phase 2B candle partitions in Data/lake/ match manifest v1.

        2. How does the specific function work:
           Reads Data/lake/manifest_active.json; checks every candle partition exists and matches SHA-256.

        3. Concepts used in the function:
           Baseline immutability verification, regression prevention.

        4. Places where this function is imported and used:
           Called at start of run() before modifying any lake structures.

        5. Final output of the function, before and after:
           Before: Existing lake. After: Tuple of (is_valid_bool, manifest_v1_dict).
        """
        if not self.active_manifest_path.exists():
            print(f"ERROR: Active lake manifest v1 not found at: {self.active_manifest_path}", flush=True)
            return False, {}

        with open(self.active_manifest_path, "r", encoding="utf-8") as f:
            v1_manifest = json.load(f)

        print("\nVerifying Phase 2B candle baseline immutability in Data/lake/ ...", flush=True)
        mismatches = 0
        total_checked = 0

        for ds_name in ["option_candles", "underlying_candles", "india_vix"]:
            ds_info = v1_manifest.get("datasets", {}).get(ds_name, {})
            partitions = ds_info.get("partitions", [])
            for p in partitions:
                total_checked += 1
                f_path = self.lake_root / p["path"]
                if not f_path.exists():
                    print(f"ERROR: Missing baseline file: {f_path}", flush=True)
                    mismatches += 1
                    continue
                actual_sha = compute_file_sha256(f_path)
                if actual_sha != p["sha256"]:
                    print(f"ERROR: Baseline file corrupted: {p['path']}", flush=True)
                    mismatches += 1

        if mismatches > 0:
            print(f"FATAL: Baseline verification failed with {mismatches} mismatches across {total_checked} files.", flush=True)
            return False, v1_manifest

        print(f"Baseline verified: all {total_checked} Phase 2B candle partitions 100% intact (0 mismatches).", flush=True)
        return True, v1_manifest

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

        print("\nVerifying Phase 3 staging readiness in staging/lake_preparation_phase3/ ...", flush=True)
        missing = 0
        sha_mismatches = 0
        total = 0

        for ds_name in ["option_snapshot_captures", "option_snapshot_rows"]:
            ds_info = manifest.get("datasets", {}).get(ds_name, {})
            partitions = ds_info.get("partitions", [])
            for p in partitions:
                total += 1
                src = self.staging_root / p["path"]
                if not src.exists():
                    missing += 1
                    continue
                actual_sha = compute_file_sha256(src)
                if actual_sha != p["sha256"]:
                    sha_mismatches += 1

        if missing > 0 or sha_mismatches > 0:
            print(f"ERROR: Staging verification failed: missing={missing}, sha_mismatches={sha_mismatches} / total={total}", flush=True)
            return False, manifest

        print(f"Staging verified: all {total} snapshot partitions exist with valid SHA-256 hashes.", flush=True)
        return True, manifest

    def publish_partitions(self, staging_manifest: Dict, dry_run: bool = False) -> Dict:
        """
        1. The use of function:
           Atomically copies all prepared snapshot Parquet partitions from staging to Data/lake/.

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

        for ds_name in ["option_snapshot_captures", "option_snapshot_rows"]:
            ds_info = staging_manifest.get("datasets", {}).get(ds_name, {})
            ds_partitions = ds_info.get("partitions", [])
            ds_rows = ds_info.get("total_rows", 0)
            ds_bytes = ds_info.get("total_bytes", 0)

            print(f"\nPublishing dataset: {ds_name} ({len(ds_partitions)} partitions, {ds_rows:,} rows)...", flush=True)
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

                if idx % 30 == 0 or idx == len(ds_partitions):
                    print(f"  [{idx:>3}/{len(ds_partitions):>3}] Published {rel_path.as_posix()}", flush=True)

            stats["datasets"][ds_name] = {
                "file_count": len(ds_partitions),
                "total_rows": ds_rows,
                "total_bytes": ds_bytes,
            }

        return stats

    def activate_manifest_v2(
        self,
        v1_manifest: Dict,
        staging_manifest: Dict,
        dry_run: bool = False,
    ) -> Path:
        """
        1. The use of function:
           Creates and atomically writes active production manifest version 2.

        2. How does the specific function work:
           Archives existing manifest_active.json to manifest_v1_archive.json;
           merges candle datasets from v1 with snapshot datasets from Phase 3 staging;
           computes new aggregate totals; writes atomically to Data/lake/manifest_active.json.

        3. Concepts used in the function:
           Active manifest pointer activation, immutable dataset lineage, backward compatibility.

        4. Places where this function is imported and used:
           Called by run() after all Parquet partitions are published and verified.

        5. Final output of the function, before and after:
           Before: Lake with manifest v1. After: Manifest v2 activated at Data/lake/manifest_active.json.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        staging_manifest_sha = compute_file_sha256(self.staging_manifest_path)

        # Merge datasets: candle datasets from v1 + snapshot datasets from Phase 3
        merged_datasets = {}
        for k in ["option_candles", "underlying_candles", "india_vix"]:
            if k in v1_manifest.get("datasets", {}):
                merged_datasets[k] = v1_manifest["datasets"][k]

        for k in ["option_snapshot_captures", "option_snapshot_rows"]:
            if k in staging_manifest.get("datasets", {}):
                merged_datasets[k] = staging_manifest["datasets"][k]

        total_files = sum(d["file_count"] for d in merged_datasets.values())
        total_rows = sum(d["total_rows"] for d in merged_datasets.values())
        total_bytes = sum(d["total_bytes"] for d in merged_datasets.values())
        total_mb = round(total_bytes / (1024 * 1024), 2)

        active_manifest_v2 = {
            "manifest_type": "QUANTVIEW_ACTIVE_LAKE_MANIFEST",
            "manifest_version": 2,
            "activated_at_utc": now_utc,
            "is_active": True,
            "lake_root": str(self.lake_root).replace("\\", "/"),
            "source_candle_staging_manifest_sha256": v1_manifest.get("source_staging_manifest_sha256"),
            "source_snapshot_staging_manifest_sha256": staging_manifest_sha,
            "previous_manifest_archive": "manifest_v1_archive.json",
            "datasets": merged_datasets,
            "aggregate_totals": {
                "total_files": total_files,
                "total_rows": total_rows,
                "total_bytes": total_bytes,
                "total_mb": total_mb,
            },
        }

        if dry_run:
            print(f"[DRY-RUN] Would activate manifest v2 at: {self.active_manifest_path}", flush=True)
            return self.active_manifest_path

        # Archive manifest v1 safely
        archive_path = self.lake_root / "manifest_v1_archive.json"
        shutil.copy2(self.active_manifest_path, archive_path)
        print(f"Archived previous manifest v1 to: {archive_path}", flush=True)

        # Write manifest v2 atomically
        tmp_manifest = self.active_manifest_path.with_suffix(".json.tmp")
        with open(tmp_manifest, "w", encoding="utf-8") as f:
            json.dump(active_manifest_v2, f, indent=2)
        tmp_manifest.replace(self.active_manifest_path)

        print(f"Active lake manifest v2 activated at: {self.active_manifest_path}", flush=True)
        return self.active_manifest_path

    def register_duckdb_views(self, dry_run: bool = False) -> Dict:
        """
        1. The use of function:
           Creates and registers canonical DuckDB views for snapshot captures, rows, and reconstructed chains.

        2. How does the specific function work:
           Opens DuckDB connection to Data/lake/quantview.duckdb and registers:
             - v_snapshots_captures: one record per capture.
             - v_snapshots_rows: strike-level observations.
             - v_snapshots_reconstructed_chain: lazy joined point-in-time chain view.
           Runs benchmark queries on each view and records query execution times.

        3. Concepts used in the function:
           DuckDB view registration, Parquet globbing, zero-copy query execution.

        4. Places where this function is imported and used:
           Called by run() after manifest v2 activation.

        5. Final output of the function, before and after:
           Before: Parquet files on disk. After: Canonical DuckDB analytical views queryable by apps and services.
        """
        if dry_run:
            print(f"[DRY-RUN] Would register snapshot DuckDB views at: {self.duckdb_path}", flush=True)
            return {"status": "DRY_RUN"}

        print(f"\nRegistering canonical DuckDB analytical snapshot views at: {self.duckdb_path} ...", flush=True)
        con = duckdb.connect(str(self.duckdb_path))

        # 1. Snapshot Captures View (DATA Spec §4.3)
        captures_glob = (self.lake_root / "option_snapshot_captures" / "**" / "*.parquet").as_posix()
        con.execute(f"""
            CREATE OR REPLACE VIEW v_snapshots_captures AS
            SELECT 
                snapshot_id,
                received_at,
                trade_date,
                underlying,
                expiry,
                spot_price,
                schema_version,
                source_file,
                row_count,
                completeness,
                field_presence_mask,
                quality_flags,
                ingested_at
            FROM read_parquet('{captures_glob}')
        """)

        # 2. Snapshot Rows View (DATA Spec §4.4)
        rows_glob = (self.lake_root / "option_snapshot_rows" / "**" / "*.parquet").as_posix()
        con.execute(f"""
            CREATE OR REPLACE VIEW v_snapshots_rows AS
            SELECT 
                snapshot_id,
                received_at,
                trade_date,
                underlying,
                expiry,
                strike,
                option_type,
                spot_price,
                oi,
                prev_oi,
                volume,
                ltp,
                bid,
                ask,
                bid_qty,
                ask_qty,
                change,
                change_oi,
                iv_observed,
                delta_observed,
                gamma_observed,
                theta_observed,
                vega_observed,
                schema_version,
                field_presence_mask,
                quality_flags,
                source_file
            FROM read_parquet('{rows_glob}')
        """)

        # 3. Lazy Reconstructed Chain View (DATA Spec §4.8)
        con.execute("""
            CREATE OR REPLACE VIEW v_snapshots_reconstructed_chain AS
            SELECT 
                c.snapshot_id,
                c.received_at AS as_of_time,
                c.trade_date,
                c.expiry,
                c.spot_price,
                r.strike,
                r.option_type,
                r.ltp,
                r.bid,
                r.ask,
                r.oi,
                r.volume,
                r.iv_observed,
                r.delta_observed,
                r.gamma_observed,
                r.theta_observed,
                r.vega_observed,
                r.quality_flags
            FROM v_snapshots_captures c
            JOIN v_snapshots_rows r ON c.snapshot_id = r.snapshot_id
        """)

        # Benchmark queries
        t0 = time.perf_counter()
        count_cap = con.execute("SELECT count(*) FROM v_snapshots_captures").fetchone()[0]
        t_cap = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        count_rows = con.execute("SELECT count(*) FROM v_snapshots_rows").fetchone()[0]
        t_rows = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        pit_sample = con.execute("""
            SELECT count(*) 
            FROM v_snapshots_rows 
            WHERE trade_date = '2026-10-14' 
              AND received_at <= '2026-10-14 04:00:00+00:00'
        """).fetchone()[0]
        t_pit = (time.perf_counter() - t0) * 1000

        con.close()

        print(f"  v_snapshots_captures:          {count_cap:>10,} rows in {t_cap:6.2f} ms", flush=True)
        print(f"  v_snapshots_rows:              {count_rows:>10,} rows in {t_rows:6.2f} ms", flush=True)
        print(f"  Point-in-time chain query:     {pit_sample:>10,} rows in {t_pit:6.2f} ms", flush=True)

        return {
            "captures_count": count_cap,
            "captures_ms": round(t_cap, 2),
            "rows_count": count_rows,
            "rows_ms": round(t_rows, 2),
            "pit_sample_count": pit_sample,
            "pit_ms": round(t_pit, 2),
        }

    def run(self, dry_run: bool = False) -> Dict:
        """
        1. The use of function:
           Coordinates the complete publication workflow.

        2. How does the specific function work:
           Validates baseline and staging; publishes partitions atomically; activates manifest v2;
           registers DuckDB views; executes benchmark queries.

        3. Concepts used in the function:
           End-to-end atomic publication lifecycle.

        4. Places where this function is imported and used:
           CLI main() or automation script.

        5. Final output of the function, before and after:
           Before: Lake v1. After: Lake v2 with snapshots queryable via DuckDB.
        """
        print("\n=======================================================", flush=True)
        print("QUANTVIEW -- PHASE 3 SNAPSHOT PUBLICATION (OFFLINE)", flush=True)
        print(f"Staging Root: {self.staging_root}", flush=True)
        print(f"Active Lake:  {self.lake_root} | Dry Run: {dry_run}", flush=True)
        print("=======================================================\n", flush=True)

        # 1. Baseline validation
        base_ok, v1_manifest = self.validate_baseline()
        if not base_ok:
            raise RuntimeError("Phase 2B baseline verification failed. Aborting publication.")

        # 2. Staging readiness validation
        stage_ok, staging_manifest = self.validate_staging_readiness()
        if not stage_ok:
            raise RuntimeError("Phase 3 staging readiness verification failed. Aborting publication.")

        # 3. Publish partitions
        pub_stats = self.publish_partitions(staging_manifest, dry_run=dry_run)

        # 4. Activate manifest v2
        active_manifest_path = self.activate_manifest_v2(v1_manifest, staging_manifest, dry_run=dry_run)

        # 5. Register DuckDB views
        view_benchmarks = self.register_duckdb_views(dry_run=dry_run)

        print("\n=======================================================", flush=True)
        print("PHASE 3 SNAPSHOT LAKE PUBLICATION COMPLETED SUCCESSFULLY", flush=True)
        print(f"Published Files: {pub_stats['published_files']} ({pub_stats['published_rows']:,} rows)", flush=True)
        print(f"Manifest Active: {active_manifest_path} (Version 2)", flush=True)
        print("=======================================================\n", flush=True)

        return {
            "status": "SUCCESS",
            "published_stats": pub_stats,
            "view_benchmarks": view_benchmarks,
        }


def main():
    """CLI entry point for Phase 3 snapshot lake publication."""
    parser = argparse.ArgumentParser(description="Publish validated Phase 3 option snapshots to active lake.")
    parser.add_argument("--staging-root", type=Path, default=None, help="Root path of Phase 3 staged files.")
    parser.add_argument("--lake-root", type=Path, default=None, help="Destination active lake root.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate publication without writing files.")
    args = parser.parse_args()

    publisher = SnapshotLakePublisher(
        staging_root=args.staging_root,
        lake_root=args.lake_root,
    )
    publisher.run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
