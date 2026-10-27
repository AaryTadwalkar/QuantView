"""
1. What this file does:
   Generates a dry-run dataset manifest for all prepared Parquet datasets in staging lake preparation
   (staging/lake_preparation/) without publishing to the active data lake or activating manifest pointers.

2. Overall design:
   Inspects prepared partitions across:
     - option_candles (underlying=NIFTY/expiry=YYYY-MM-DD/)
     - underlying_candles (interval={1m,1d}/)
     - india_vix (interval={1m,1d}/)
     - option_snapshots (captures/ and rows/)
   Calculates SHA-256 cryptographic hashes and byte sizes of all prepared Parquet files.
   Records exact dataset version, row count totals, and partition lists.
   Outputs a structured JSON manifest at staging/lake_preparation/manifest_dry_run.json.
   Enforces non-destructive boundary: does not publish to active Data/lake/ or alter database active pointers.

3. Elements in the file:
   - DryRunManifestGenerator: Workflow class calculating partition hashes and compiling dataset manifests.
   - compute_file_sha256: Utility calculating SHA-256 hash of a file on disk.
   - main: CLI entry point.

4. Final output of the file:
   - Dry-run manifest: staging/lake_preparation/manifest_dry_run.json
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pyarrow.parquet as pq


def compute_file_sha256(file_path: Path) -> str:
    """Calculates SHA-256 hash of a file in 64KB chunks."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class DryRunManifestGenerator:
    """Coordinates compilation of dry-run publication manifests across staging lake partitions."""

    def __init__(self, prep_root: Optional[Path] = None):
        self.prep_root = prep_root or Path("staging/lake_preparation")

    def inspect_dataset(self, dataset_name: str, subfolder: str) -> Dict:
        """Inspects all Parquet partitions within a prepared dataset subfolder."""
        ds_dir = self.prep_root / subfolder
        if not ds_dir.exists():
            return {
                "dataset_name": dataset_name,
                "status": "NOT_PREPARED",
                "file_count": 0,
                "total_rows": 0,
                "total_bytes": 0,
                "partitions": [],
            }

        partitions = []
        total_rows = 0
        total_bytes = 0

        for p_file in ds_dir.glob("**/*.parquet"):
            if p_file.name.endswith(".tmp"):
                continue

            try:
                meta = pq.read_metadata(p_file)
                r_count = meta.num_rows
            except Exception:
                r_count = 0

            f_bytes = p_file.stat().st_size
            f_hash = compute_file_sha256(p_file)

            total_rows += r_count
            total_bytes += f_bytes

            rel_path = str(p_file.relative_to(self.prep_root)).replace("\\", "/")
            partitions.append({
                "path": rel_path,
                "rows": r_count,
                "bytes": f_bytes,
                "sha256": f_hash,
            })

        return {
            "dataset_name": dataset_name,
            "status": "PREPARED" if partitions else "EMPTY",
            "file_count": len(partitions),
            "total_rows": total_rows,
            "total_bytes": total_bytes,
            "partitions": partitions,
        }

    def run(self, manifest_filename: str = "manifest_dry_run.json") -> Dict:
        """
        1. The use of function:
           Compiles an offline staging dry-run publication manifest across all prepared lake datasets.

        2. How does the specific function work:
           Iterates through dataset subdirectories (option_candles, underlying_candles, india_vix,
           option_snapshots), inspects Parquet files, computes SHA-256 hashes and row counts,
           and writes the resulting manifest JSON to disk.

        3. Concepts used in the function:
           Cryptographic dataset integrity, metadata serialization, partition indexing.

        4. Places where this function is imported and used:
           Called by main() or invoked directly during staging validation.

        5. Final output of the function, before and after:
           Before: Staged Parquet files. After: Manifest JSON file written to prep_root / manifest_filename and returned dict.
        """
        now_ts = datetime.now(timezone.utc).isoformat()
        print("\n=======================================================", flush=True)
        print("QUANTVIEW -- STAGING LAKE DRY-RUN MANIFEST GENERATOR", flush=True)
        print(f"Inspection Root: {self.prep_root}", flush=True)
        print(f"Timestamp: {now_ts}", flush=True)
        print("=======================================================\n", flush=True)

        datasets = {
            "option_candles": "option_candles",
            "underlying_candles": "underlying_candles",
            "india_vix": "india_vix",
            "option_snapshot_captures": "option_snapshots/captures",
            "option_snapshot_rows": "option_snapshots/rows",
        }

        manifest = {
            "manifest_type": "QUANTVIEW_LAKE_DRY_RUN_PUBLICATION_MANIFEST",
            "generated_at_utc": now_ts,
            "prep_root": str(self.prep_root).replace("\\", "/"),
            "is_published_to_active_lake": False,
            "active_pointer_updated": False,
            "datasets": {},
        }

        total_files = 0
        total_rows = 0
        total_bytes = 0

        for ds_name, sub_path in datasets.items():
            ds_info = self.inspect_dataset(ds_name, sub_path)
            manifest["datasets"][ds_name] = ds_info
            total_files += ds_info["file_count"]
            total_rows += ds_info["total_rows"]
            total_bytes += ds_info["total_bytes"]
            print(f"  * {ds_name:<26}: {ds_info['file_count']:>3} files | {ds_info['total_rows']:>10,} rows | {ds_info['total_bytes'] / (1024*1024):>8.2f} MB", flush=True)

        manifest["aggregate_totals"] = {
            "total_files": total_files,
            "total_rows": total_rows,
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
        }

        self.prep_root.mkdir(parents=True, exist_ok=True)
        out_manifest_path = self.prep_root / manifest_filename
        with open(out_manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        print(f"\nDry-run manifest generated at: {out_manifest_path}", flush=True)
        print(f"Total Prepared: {total_files} files | {total_rows:,} rows | {manifest['aggregate_totals']['total_mb']} MB", flush=True)
        print("Active Lake Publication Status: UNPUBLISHED (Phase 1 boundary preserved)", flush=True)

        return manifest


def main():
    """
    1. The use of function:
       CLI entry point for staging lake manifest compilation.

    2. How does the specific function work:
       Parses command-line arguments (--prep-root, --manifest-filename), instantiates
       DryRunManifestGenerator, and executes run().

    3. Concepts used in the function:
       CLI argument parsing via argparse, dynamic path resolution.

    4. Places where this function is imported and used:
       Executed directly from command line (python -m tools.lake.prepare_dry_run_manifest).

    5. Final output of the function, before and after:
       Before: Command line flags. After: Manifest JSON generated and printed.
    """
    parser = argparse.ArgumentParser(description="Generate dry-run publication manifest for lake staging.")
    parser.add_argument("--prep-root", type=str, default=None, help="Root directory of prepared staging lake.")
    parser.add_argument("--manifest-filename", type=str, default="manifest_dry_run.json", help="Filename of output manifest JSON.")
    args = parser.parse_args()

    prep_root = Path(args.prep_root) if args.prep_root else None
    gen = DryRunManifestGenerator(prep_root=prep_root)
    gen.run(manifest_filename=args.manifest_filename)


if __name__ == "__main__":
    main()
