"""
1. What this file does:
   Generates a cryptographic dataset manifest for all prepared option snapshot Parquet datasets in staging
   (staging/lake_preparation_phase3/) before active lake promotion per QUANTVIEW_DATA_SPEC §7.

2. Overall design:
   Inspects staged partitions across:
     - option_snapshot_captures (trade_date=YYYY-MM-DD/part-0.parquet)
     - option_snapshot_rows (trade_date=YYYY-MM-DD/part-0.parquet)
   Calculates SHA-256 cryptographic hashes, byte sizes, and exact row counts from Parquet metadata.
   Outputs a structured staging manifest at staging/lake_preparation_phase3/manifest_phase3.json.
   Enforces non-destructive staging boundaries: does not write to Data/lake/ or alter active pointers.

3. Elements in the file:
   - compute_file_sha256: Utility function calculating SHA-256 hashes in 64KB binary blocks.
   - Phase3ManifestGenerator: Main workflow class coordinating partition scanning and manifest generation.
   - main: CLI entry point supporting directory overrides.

4. Final output of the file:
   - Staging manifest: staging/lake_preparation_phase3/manifest_phase3.json
   - Printed partition count, row count, byte size, and SHA-256 audit summary.
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
    """
    1. The use of function:
       Computes the SHA-256 cryptographic hash of a file on disk.

    2. How does the specific function work:
       Reads file in 64KB binary chunks and updates hashlib.sha256 hash object.

    3. Concepts used in the function:
       Cryptographic hashing, buffered binary stream reading.

    4. Places where this function is imported and used:
       Called for each staged Parquet partition during manifest generation.

    5. Final output of the function, before and after:
       Before: File path. After: Hex-encoded 64-character SHA-256 string.
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class Phase3ManifestGenerator:
    """
    1. The use of class:
       Compiles cryptographic manifests for staged snapshot captures and rows Parquet partitions.

    2. What the class contains:
       - prep_root: Root directory of staged files (staging/lake_preparation_phase3/).
       - inspect_dataset(): Scans partitions within a dataset subfolder and computes hashes and row counts.
       - generate_manifest(): Assembles the full manifest dictionary and writes manifest_phase3.json.

    3. Technologies used and why:
       - pyarrow.parquet: Reads partition metadata without scanning row payloads.
       - hashlib / json: Cryptographic verification and standard metadata serialization.

    4. Key design and overall design of the class:
       Produces an immutable staging manifest that serves as the cryptographic input to active lake promotion.
    """

    def __init__(self, prep_root: Optional[Path] = None):
        """Initializes Phase3ManifestGenerator with staging root directory."""
        self.prep_root = prep_root or Path("staging/lake_preparation_phase3")

    def inspect_dataset(self, dataset_name: str, subfolder: str) -> Dict:
        """
        1. The use of function:
           Inspects all Parquet partitions within a staged dataset subfolder.

        2. How does the specific function work:
           Discovers all part-*.parquet files; reads row count via Parquet metadata; reads file size;
           computes SHA-256 hash; sorts partitions alphabetically by path for determinism.

        3. Concepts used in the function:
           Metadata inspection, deterministic partition sorting.

        4. Places where this function is imported and used:
           Called by generate_manifest() for option_snapshot_captures and option_snapshot_rows.

        5. Final output of the function, before and after:
           Before: Directory on disk. After: Dataset summary dict containing partition list and totals.
        """
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

        parquet_files = sorted(list(ds_dir.glob("**/*.parquet")))
        for p_file in parquet_files:
            if p_file.name.endswith(".tmp"):
                continue

            try:
                meta = pq.read_metadata(p_file)
                r_count = meta.num_rows
            except Exception:
                r_count = 0

            b_size = p_file.stat().st_size
            sha = compute_file_sha256(p_file)
            rel_path = p_file.relative_to(self.prep_root).as_posix()

            partitions.append({
                "path": rel_path,
                "rows": r_count,
                "bytes": b_size,
                "sha256": sha,
            })
            total_rows += r_count
            total_bytes += b_size

        return {
            "dataset_name": dataset_name,
            "status": "PREPARED" if partitions else "NOT_PREPARED",
            "file_count": len(partitions),
            "total_rows": total_rows,
            "total_bytes": total_bytes,
            "partitions": partitions,
        }

    def generate_manifest(self) -> Path:
        """
        1. The use of function:
           Coordinates scanning of snapshot datasets and writes manifest_phase3.json.

        2. How does the specific function work:
           Inspects option_snapshot_captures and option_snapshot_rows; computes aggregate totals;
           assembles manifest metadata with UTC timestamp; writes atomically to manifest_phase3.json.

        3. Concepts used in the function:
           Manifest generation, atomic write via temporary file.

        4. Places where this function is imported and used:
           Called via CLI main() or post-compaction pipeline.

        5. Final output of the function, before and after:
           Before: Staged Parquets. After: Written manifest_phase3.json and returned Path.
        """
        print(f"\nScanning Phase 3 staging partitions in: {self.prep_root} ...", flush=True)

        captures = self.inspect_dataset("option_snapshot_captures", "option_snapshot_captures")
        rows = self.inspect_dataset("option_snapshot_rows", "option_snapshot_rows")

        datasets = {
            "option_snapshot_captures": captures,
            "option_snapshot_rows": rows,
        }

        total_files = sum(d["file_count"] for d in datasets.values())
        total_rows = sum(d["total_rows"] for d in datasets.values())
        total_bytes = sum(d["total_bytes"] for d in datasets.values())
        total_mb = round(total_bytes / (1024 * 1024), 2)

        manifest = {
            "manifest_type": "QUANTVIEW_STAGING_MANIFEST_PHASE3",
            "manifest_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "staging_root": str(self.prep_root).replace("\\", "/"),
            "datasets": datasets,
            "aggregate_totals": {
                "total_files": total_files,
                "total_rows": total_rows,
                "total_bytes": total_bytes,
                "total_mb": total_mb,
            },
        }

        manifest_path = self.prep_root / "manifest_phase3.json"
        tmp_path = manifest_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        tmp_path.replace(manifest_path)

        print("\n=======================================================", flush=True)
        print("QUANTVIEW -- PHASE 3 STAGING MANIFEST GENERATED", flush=True)
        print(f"Manifest Path: {manifest_path}", flush=True)
        print(f"SHA-256: {compute_file_sha256(manifest_path)}", flush=True)
        print(f"Captures Partitions: {captures['file_count']} ({captures['total_rows']:,} rows, {captures['total_bytes'] / (1024*1024):.2f} MB)", flush=True)
        print(f"Rows Partitions:     {rows['file_count']} ({rows['total_rows']:,} rows, {rows['total_bytes'] / (1024*1024):.2f} MB)", flush=True)
        print(f"Aggregate Totals:    {total_files} files, {total_rows:,} rows, {total_mb:.2f} MB", flush=True)
        print("=======================================================\n", flush=True)

        return manifest_path


def main():
    """CLI entry point for Phase 3 staging manifest generation."""
    parser = argparse.ArgumentParser(description="Generate Phase 3 staging manifest for option snapshot datasets.")
    parser.add_argument("--prep-root", type=Path, default=None, help="Root path of Phase 3 staged files.")
    args = parser.parse_args()

    generator = Phase3ManifestGenerator(prep_root=args.prep_root)
    generator.generate_manifest()


if __name__ == "__main__":
    main()
