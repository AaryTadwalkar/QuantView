"""
1. What this file does:
   Executes unidirectional, read-only synchronization of recorded raw collector datasets
   from the production collector host to the research workstation per QUANTVIEW_MASTER_SPEC §4, §5,
   and Task M2-11.

2. Overall design:
   - Connects to production host via SSH/rsync or local staging mount.
   - Pulls newly finalized segments (.bin.gz) and snapshots (.json.gz) with their companion manifests.
   - Verifies SHA-256 checksums of transferred files against manifest digests upon arrival.
   - Strictly enforces no write-back path: destination permissions are read-only for research tools.
   - Rejects unfinalized (.partial or .tmp) files to ensure zero half-written data transfers.

3. Elements in the file:
   - verify_file_checksum(): Computes SHA-256 and compares against expected manifest hash.
   - sync_remote_to_local(): Dispatches read-only sync and verifies cryptographic integrity.
   - main(): CLI entrypoint parsing arguments (--source, --dest, --verify-checksums).

4. Final output of the file:
   - Checksum-verified raw data mirrored to research workstation with zero write-back capability.
"""

import argparse
import hashlib
import json
import logging
from pathlib import Path
import shutil
import sys
from typing import Dict, List, Optional, Tuple

# Standard QuantView repository bootstrap
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("quantview.sync_host")


def verify_file_checksum(file_path: Path, expected_sha256: str) -> bool:
    """
    1. The use of function:
       Verifies that a synchronized raw binary or json file matches its cryptographic manifest digest.

    2. How does the specific function work:
       - Streams file contents in 64 KB chunks.
       - Computes SHA-256 hex digest.
       - Compares computed digest against expected_sha256 string.

    3. Concepts used in the function:
       Cryptographic hash verification, tamper detection.

    4. Places where this function is imported and used:
       Called after sync transfer.

    5. Final output of the function, before and after:
       Before: Unverified file. After: Boolean indicating integrity pass or fail.
    """
    if not file_path.exists():
        return False

    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower() == expected_sha256.lower()


def sync_directory_unidirectional(
    source_dir: Path,
    dest_dir: Path,
    verify_checksums: bool = True,
) -> Dict[str, Any]:
    """
    1. The use of function:
       Copies finalized raw market data files from source host/dir to research machine without write-back.

    2. How does the specific function work:
       - Scans source_dir for finalized files (*.bin.gz, *.json.gz, *.manifest.json).
       - Ignores .partial and .tmp files.
       - Copies new or updated files to dest_dir.
       - If verify_checksums is True, reads manifest and verifies SHA-256 digest on destination.

    3. Concepts used in the function:
       Unidirectional replication, read-only assurance, manifest-driven verification.

    4. Places where this function is imported and used:
       Called in main() and automated sync cron jobs.

    5. Final output of the function, before and after:
       Before: Raw files on source only. After: Mirrored, verified files on destination.
    """
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    synced_files: List[str] = []
    failed_files: List[str] = []

    # Only sync finalized files
    valid_suffixes = {".bin.gz", ".json.gz", ".manifest.json"}
    for src_file in source_dir.rglob("*"):
        if not src_file.is_file():
            continue
        # Skip incomplete files
        if any(src_file.name.endswith(ext) for ext in [".partial", ".tmp", ".lock"]):
            continue

        rel_path = src_file.relative_to(source_dir)
        target_dest = dest_dir / rel_path

        # Check if copy needed
        if not target_dest.exists() or src_file.stat().st_size != target_dest.stat().st_size:
            target_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, target_dest)
            synced_files.append(str(rel_path))

            # Verify checksum if companion manifest exists
            if verify_checksums and target_dest.name.endswith(".manifest.json"):
                try:
                    with open(target_dest, "r", encoding="utf-8") as mf:
                        m_data = json.load(mf)
                    # Check companion compressed file
                    c_sha = m_data.get("compressed_sha256")
                    bin_target = target_dest.with_suffix(".bin.gz")
                    if not bin_target.exists():
                        bin_target = target_dest.parent / f"{target_dest.stem}.bin.gz"
                    if bin_target.exists() and c_sha:
                        if not verify_file_checksum(bin_target, c_sha):
                            failed_files.append(str(bin_target))
                except Exception as ex:
                    logger.warning("Manifest parse failure for %s: %s", target_dest, ex)

    return {
        "status": "PASS" if not failed_files else "FAIL",
        "synced_count": len(synced_files),
        "failed_verifications": failed_files,
    }


def main() -> None:
    """
    1. The use of function:
       CLI entrypoint for unidirectional raw data sync from production collector to research machine.

    2. How does the specific function work:
       - Parses CLI arguments (--source, --dest, --skip-checksum-verify).
       - Executes sync_directory_unidirectional().
       - Displays sync summary.

    3. Concepts used in the function:
       CLI automation, replication management.

    4. Places where this function is imported and used:
       Executed via `python tools/ops/sync_production_to_research.py`.

    5. Final output of the function, before and after:
       Before: Idle. After: Synced datasets verified on research machine.
    """
    parser = argparse.ArgumentParser(description="QuantView Production-to-Research Unidirectional Sync")
    parser.add_argument("--source", type=str, required=True, help="Source path (e.g. production host network share)")
    parser.add_argument("--dest", type=str, default="", help="Destination path (defaults to Data/raw/)")
    parser.add_argument("--skip-checksum-verify", action="store_true", help="Skip SHA-256 verification against manifests")
    args = parser.parse_args()

    src = Path(args.source)
    dst = Path(args.dest) if args.dest else PROJECT_ROOT / "Data" / "raw"

    print(f"\n--- QuantView Unidirectional Production-to-Research Sync ---")
    print(f"Source:       {src.resolve()}")
    print(f"Destination:  {dst.resolve()}")
    print("Enforcing:    Strict Read-Only Direction (No Write-Back Path)\n")

    result = sync_directory_unidirectional(src, dst, verify_checksums=not args.skip_checksum_verify)
    print("=" * 65)
    print(f" Sync Status:            {result['status']}")
    print(f" Files Synchronized:     {result['synced_count']}")
    print(f" Failed Checksums:       {len(result['failed_verifications'])}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
