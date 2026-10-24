"""
1. What this file does:
   Generates a cryptographic dataset manifest for all Phase 4 prepared datasets in staging
   (staging/lake_preparation_phase4/) including multi-timeframe derived candles and data eligibility matrix.

2. Overall design:
   Inspects staged partitions across:
     - derived_candles (interval={3m,5m,15m,30m,1h,4h}/year=YYYY/month=MM/part-0.parquet)
     - data_eligibility (part-0.parquet)
   Calculates SHA-256 cryptographic hashes, byte sizes, and exact row counts from Parquet metadata.
   Outputs a structured staging manifest at staging/lake_preparation_phase4/manifest_phase4.json.

3. Elements in the file:
   - compute_file_sha256: Utility function calculating SHA-256 hashes in 64KB binary blocks.
   - Phase4ManifestGenerator: Workflow class calculating partition hashes and compiling dataset manifests.
   - main: CLI entry point.

4. Final output of the file:
   - Staging manifest: staging/lake_preparation_phase4/manifest_phase4.json
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


class Phase4ManifestGenerator:
    """
    1. The use of class:
       Compiles cryptographic manifests for staged Phase 4 derived candles and data eligibility partitions.

    2. What the class contains:
       - prep_root: Root directory of staged files (staging/lake_preparation_phase4/).
       - inspect_dataset(): Scans partitions within a dataset subfolder and computes hashes and row counts.
       - generate_manifest(): Assembles the full manifest dictionary and writes manifest_phase4.json.

    3. Technologies used and why:
       - pyarrow.parquet: Reads partition metadata without scanning row payloads.
       - hashlib / json: Cryptographic verification and standard metadata serialization.

    4. Key design and overall design of the class:
       Produces an immutable staging manifest that records all Phase 4 outputs.
    """

    def __init__(self, prep_root: Optional[Path] = None):
        """Initializes Phase4ManifestGenerator with staging root directory."""
        self.prep_root = prep_root or Path("staging/lake_preparation_phase4")

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
           Called by generate_manifest() for derived_candles and data_eligibility.

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
           Coordinates scanning of Phase 4 datasets and writes manifest_phase4.json.

        2. How does the specific function work:
           Inspects derived_candles and data_eligibility; computes aggregate totals;
           assembles manifest metadata with UTC timestamp; writes atomically to manifest_phase4.json.

        3. Concepts used in the function:
           Manifest generation, atomic write via temporary file.

        4. Places where this function is imported and used:
           Called via CLI main() or post-compaction pipeline.

        5. Final output of the function, before and after:
           Before: Staged Parquets. After: Written manifest_phase4.json and returned Path.
        """
        print(f"\nScanning Phase 4 staging partitions in: {self.prep_root} ...", flush=True)

        derived = self.inspect_dataset("derived_candles", "derived_candles")
        eligibility = self.inspect_dataset("data_eligibility", "data_eligibility")

        datasets = {
            "derived_candles": derived,
            "data_eligibility": eligibility,
        }

        total_files = sum(d["file_count"] for d in datasets.values())
        total_rows = sum(d["total_rows"] for d in datasets.values())
        total_bytes = sum(d["total_bytes"] for d in datasets.values())
        total_mb = round(total_bytes / (1024 * 1024), 2)

        manifest = {
            "manifest_type": "QUANTVIEW_STAGING_MANIFEST_PHASE4",
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

        manifest_path = self.prep_root / "manifest_phase4.json"
        tmp_path = manifest_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        tmp_path.replace(manifest_path)

        print(f"\n=======================================================", flush=True)
        print(f"QUANTVIEW -- PHASE 4 STAGING MANIFEST GENERATED", flush=True)
        print(f"Manifest Path: {manifest_path}", flush=True)
        print(f"SHA-256: {compute_file_sha256(manifest_path)}", flush=True)
        print(f"Derived Candles Partitions:   {derived['file_count']} ({derived['total_rows']:,} rows, {derived['total_bytes'] / (1024*1024):.2f} MB)", flush=True)
        print(f"Data Eligibility Partitions:  {eligibility['file_count']} ({eligibility['total_rows']:,} rows, {eligibility['total_bytes'] / (1024*1024):.4f} MB)", flush=True)
        print(f"Aggregate Totals:             {total_files} files, {total_rows:,} rows, {total_mb:.2f} MB", flush=True)
        print(f"=======================================================\n", flush=True)

        return manifest_path


def main():
    """CLI entry point for Phase 4 staging manifest generation."""
    parser = argparse.ArgumentParser(description="Generate Phase 4 staging manifest for derived candles and eligibility datasets.")
    parser.add_argument("--prep-root", type=Path, default=None, help="Root path of Phase 4 staged files.")
    args = parser.parse_args()

    generator = Phase4ManifestGenerator(prep_root=args.prep_root)
    generator.generate_manifest()


if __name__ == "__main__":
    main()
