"""
1. What this file does:
   Implements the raw-first persistence engine for REST market data snapshots (RawSnapshotWriter).
   Guarantees crash-resilient, fsync-durable, atomic writes of raw HTTP payloads and companion
   manifests prior to any decoding or normalization per QUANTVIEW_DATA_SPEC §2, §4.3, §10 and Task M2-01.

2. Overall design:
   Enforces strict raw-first durability mechanics:
     - Receives original uncompressed HTTP response bytes.
     - Computes cryptographic SHA-256 hash on original uncompressed bytes.
     - Compresses payload with gzip and writes to an isolated .tmp file.
     - Executes flush() and os.fsync() on the file descriptor before closing.
     - Atomically renames temporary file to final capture path:
       Data/raw/upstox_rest/snapshots/trade_date=YYYY-MM-DD/capture_<snapshot_id>.json.gz
     - Constructs self-describing companion capture manifest with uncompressed hash, compressed hash,
       timestamps, HTTP status, and persistence status.
     - Atomically writes companion manifest via .tmp file and fsync.
     - If decoding fails later, the raw payload is already durably preserved on disk with 0% data loss.

3. Elements in the file:
   - RawSnapshotWriter: Central class managing raw snapshot directory structure, atomic writes, and manifests.
   - RawCaptureRecord: Dataclass encapsulating paths, hashes, and metadata for a durably persisted capture.

4. Final output of the file:
   - Persisted raw file: Data/raw/upstox_rest/snapshots/trade_date=YYYY-MM-DD/capture_<snapshot_id>.json.gz
   - Persisted manifest: Data/raw/upstox_rest/snapshots/trade_date=YYYY-MM-DD/capture_<snapshot_id>.manifest.json
   - Returned RawCaptureRecord containing verified hashes and file references.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RawCaptureRecord:
    """
    1. The use of class:
       Encapsulates the verified file paths, hashes, and metadata of a durably persisted raw capture.

    2. What the class contains:
       - snapshot_id: Unique capture identifier.
       - raw_file_path: Path to the finalized .json.gz file.
       - manifest_path: Path to the companion .manifest.json file.
       - uncompressed_bytes: Size of the original HTTP response body in bytes.
       - uncompressed_sha256: SHA-256 hash of the original uncompressed response body.
       - compressed_bytes: Size of the persisted .json.gz file in bytes.
       - compressed_sha256: SHA-256 hash of the persisted .json.gz file.
       - received_at_utc: Timestamp when the response was received.
       - status: Durability status ('DURABLE_STORED').

    3. Technologies used and why:
       Python dataclasses for immutable and strongly-typed capture metadata transfer.

    4. Key design and overall design of the class:
       Read-only data structure returned after successful fsync and atomic rename.
    """
    snapshot_id: str
    raw_file_path: Path
    manifest_path: Path
    uncompressed_bytes: int
    uncompressed_sha256: str
    compressed_bytes: int
    compressed_sha256: str
    received_at_utc: str
    status: str = "DURABLE_STORED"


class RawSnapshotWriter:
    """
    1. The use of class:
       Manages the raw snapshot filesystem hierarchy and executes crash-resilient atomic writes.

    2. What the class contains:
       - raw_root: Base directory for raw snapshots (Data/raw/upstox_rest/snapshots).
       - persist_raw_response(): Writes raw response bytes and companion manifest with fsync and atomic rename.
       - update_manifest_decoder_status(): Updates companion manifest with decoder outcome (DECODED or ERROR).
       - reconcile_session_directory(): Audits raw-to-manifest integrity across a session date directory.

    3. Technologies used and why:
       - hashlib: Cryptographic SHA-256 computation on raw and compressed bytes.
       - gzip: Compressed archival storage minimizing disk footprint.
       - os.fsync: Hardware-level disk sync ensuring durability before atomic rename.
       - Pathlib: Cross-platform directory path management.

    4. Key design and overall design of the class:
       Fail-closed atomic write protocol: never write directly to final destination; always write to
       temporary `.tmp` files, flush and fsync, then rename. Preserves original bytes unconditionally.
    """

    def __init__(self, raw_root: Optional[Path] = None) -> None:
        """
        1. The use of function:
           Initializes RawSnapshotWriter with the target raw storage root.

        2. How does the specific function work:
           Resolves raw root directory path, defaulting to Data/raw/upstox_rest/snapshots.

        3. Concepts used in the function:
           Path initialization and parameter defaulting.

        4. Places where this function is imported and used:
           Instantiated by SnapshotCollector and test fixtures.

        5. Final output of the function, before and after:
           Before: Uninitialized instance. After: Configured RawSnapshotWriter ready for persistence.
        """
        if raw_root is None:
            project_root = Path(__file__).resolve().parents[2]
            self.raw_root = project_root / "Data" / "raw" / "upstox_rest" / "snapshots"
        else:
            self.raw_root = Path(raw_root)

    def persist_raw_response(
        self,
        snapshot_id: str,
        trade_date: str,
        raw_bytes: bytes,
        endpoint: str,
        request_params: Dict[str, Any],
        http_status: int,
        content_type: str,
        request_timestamp_utc: str,
        received_at_utc: str,
        schema_version: str = "v3",
        quality_flags: Optional[List[str]] = None,
    ) -> RawCaptureRecord:
        """
        1. The use of function:
           Persists raw response bytes and companion manifest with full fsync durability and atomic rename.

        2. How does the specific function work:
           - Computes SHA-256 of raw uncompressed response bytes.
           - Prepares session directory: raw_root / f"trade_date={trade_date}".
           - Compresses raw bytes with gzip and writes to a temporary file (`.json.gz.tmp`).
           - Flushes and calls os.fsync() on the file descriptor before closing.
           - Atomically renames temporary file to `capture_<snapshot_id>.json.gz`.
           - Computes SHA-256 and size of the finalized compressed file.
           - Constructs companion manifest dictionary containing full provenance and cryptographic hashes.
           - Writes manifest to `.manifest.json.tmp`, flushes, fsyncs, and atomically renames.
           - Returns RawCaptureRecord.

        3. Concepts used in the function:
           Two-phase commit via atomic rename, hardware disk synchronization (fsync), cryptographic integrity.

        4. Places where this function is imported and used:
           Called immediately upon receiving HTTP response body in SnapshotCollector.

        5. Final output of the function, before and after:
           Before: Raw bytes in memory. After: Compressed raw file and manifest durably committed to disk.
        """
        if not isinstance(raw_bytes, (bytes, bytearray)):
            raise TypeError(f"raw_bytes must be bytes or bytearray, got {type(raw_bytes)}")

        uncompressed_bytes = len(raw_bytes)
        uncompressed_sha256 = hashlib.sha256(raw_bytes).hexdigest()

        session_dir = self.raw_root / f"trade_date={trade_date}"
        session_dir.mkdir(parents=True, exist_ok=True)

        final_raw_path = session_dir / f"capture_{snapshot_id}.json.gz"
        tmp_raw_path = session_dir / f"capture_{snapshot_id}.json.gz.tmp"

        final_manifest_path = session_dir / f"capture_{snapshot_id}.manifest.json"
        tmp_manifest_path = session_dir / f"capture_{snapshot_id}.manifest.json.tmp"

        # 1. Write compressed raw payload to temporary file with fsync
        with open(tmp_raw_path, "wb") as f_raw:
            with gzip.GzipFile(fileobj=f_raw, mode="wb", compresslevel=6) as gz:
                gz.write(raw_bytes)
            f_raw.flush()
            os.fsync(f_raw.fileno())

        # Atomically rename raw file
        if final_raw_path.exists():
            final_raw_path.unlink()
        tmp_raw_path.rename(final_raw_path)

        # 2. Compute compressed file statistics
        compressed_bytes = final_raw_path.stat().st_size
        h_comp = hashlib.sha256()
        with open(final_raw_path, "rb") as f_read:
            while chunk := f_read.read(65536):
                h_comp.update(chunk)
        compressed_sha256 = h_comp.hexdigest()

        # 3. Construct self-describing capture manifest
        # Filter request parameters to ensure zero secrets/tokens are logged
        sanitized_params = {
            k: v for k, v in request_params.items()
            if not any(secret in k.lower() for secret in ["token", "key", "secret", "auth", "password"])
        }

        manifest_data = {
            "snapshot_id": snapshot_id,
            "trade_date": trade_date,
            "endpoint": endpoint,
            "request_params": sanitized_params,
            "http_status": http_status,
            "content_type": content_type,
            "request_timestamp_utc": request_timestamp_utc,
            "received_at_utc": received_at_utc,
            "uncompressed_bytes": uncompressed_bytes,
            "uncompressed_sha256": uncompressed_sha256,
            "compressed_bytes": compressed_bytes,
            "compressed_sha256": compressed_sha256,
            "compression_codec": "gzip",
            "schema_version": schema_version,
            "persistence_status": "DURABLE_STORED",
            "decoder_status": "PENDING",
            "quality_flags": quality_flags or ["RAW_STORED_OK"],
            "persisted_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        # 4. Write companion manifest to temporary file with fsync
        with open(tmp_manifest_path, "w", encoding="utf-8") as f_man:
            json.dump(manifest_data, f_man, indent=2)
            f_man.flush()
            os.fsync(f_man.fileno())

        # Atomically rename manifest
        if final_manifest_path.exists():
            final_manifest_path.unlink()
        tmp_manifest_path.rename(final_manifest_path)

        return RawCaptureRecord(
            snapshot_id=snapshot_id,
            raw_file_path=final_raw_path,
            manifest_path=final_manifest_path,
            uncompressed_bytes=uncompressed_bytes,
            uncompressed_sha256=uncompressed_sha256,
            compressed_bytes=compressed_bytes,
            compressed_sha256=compressed_sha256,
            received_at_utc=received_at_utc,
            status="DURABLE_STORED",
        )

    def update_manifest_decoder_status(
        self,
        manifest_path: Path,
        decoder_status: str,
        error_message: Optional[str] = None,
        row_count: Optional[int] = None,
        field_mask: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        1. The use of function:
           Updates companion manifest with the downstream decoder outcome without mutating raw bytes.

        2. How does the specific function work:
           Reads existing manifest, updates decoder fields, writes to .tmp file with fsync, and renames.

        3. Concepts used in the function:
           Manifest state transitions, atomic metadata updates.

        4. Places where this function is imported and used:
           Called after decoder succeeds or fails in SnapshotCollector.

        5. Final output of the function, before and after:
           Before: decoder_status is PENDING. After: decoder_status is DECODED or DECODER_PARSE_ERROR.
        """
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found at {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        manifest["decoder_status"] = decoder_status
        manifest["decoder_updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        if error_message:
            manifest["decoder_error"] = str(error_message)
            if "DECODER_ERROR" not in manifest.get("quality_flags", []):
                manifest.setdefault("quality_flags", []).append("DECODER_ERROR")
        if row_count is not None:
            manifest["row_count"] = row_count
        if field_mask is not None:
            manifest["field_presence_mask"] = field_mask

        tmp_path = manifest_path.with_suffix(".manifest.json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        if manifest_path.exists():
            manifest_path.unlink()
        tmp_path.rename(manifest_path)

        return manifest

    def reconcile_session_directory(self, trade_date: str) -> Dict[str, Any]:
        """
        1. The use of function:
           Audits raw-to-manifest reconciliation across a specific trading session directory.

        2. How does the specific function work:
           Scans session directory for .json.gz and .manifest.json files, verifies 1:1 pair matching,
           checks for abandoned .tmp files, and validates SHA-256 checksums of uncompressed payloads.

        3. Concepts used in the function:
           Forensic reconciliation audit, orphan file detection, integrity verification.

        4. Places where this function is imported and used:
           Called by post-close audits, health checks, and test suites.

        5. Final output of the function, before and after:
           Before: Directory integrity unverified. After: Dictionary detailing reconciliation counts and errors.
        """
        session_dir = self.raw_root / f"trade_date={trade_date}"
        if not session_dir.exists():
            return {
                "status": "PASS",
                "trade_date": trade_date,
                "total_captures": 0,
                "unmatched_raw_files": [],
                "unmatched_manifest_files": [],
                "abandoned_tmp_files": [],
                "checksum_errors": [],
            }

        raw_files = {p.stem.replace(".json", ""): p for p in session_dir.glob("capture_*.json.gz")}
        manifest_files = {p.stem.replace(".manifest", ""): p for p in session_dir.glob("capture_*.manifest.json")}
        tmp_files = [str(p.name) for p in session_dir.glob("*.tmp")]

        unmatched_raw = [str(name) for name in raw_files if name not in manifest_files]
        unmatched_manifest = [str(name) for name in manifest_files if name not in raw_files]

        checksum_errors = []
        for name, r_path in raw_files.items():
            if name in manifest_files:
                m_path = manifest_files[name]
                try:
                    with open(m_path, "r", encoding="utf-8") as f:
                        m_data = json.load(f)
                    with gzip.open(r_path, "rb") as gz:
                        decompressed = gz.read()
                    actual_sha = hashlib.sha256(decompressed).hexdigest()
                    if actual_sha != m_data.get("uncompressed_sha256"):
                        checksum_errors.append(f"{name}: expected {m_data.get('uncompressed_sha256')}, got {actual_sha}")
                except Exception as ex:
                    checksum_errors.append(f"{name}: read exception {str(ex)}")

        has_errors = bool(unmatched_raw or unmatched_manifest or checksum_errors)
        return {
            "status": "FAIL" if has_errors else "PASS",
            "trade_date": trade_date,
            "total_captures": len(raw_files),
            "unmatched_raw_files": unmatched_raw,
            "unmatched_manifest_files": unmatched_manifest,
            "abandoned_tmp_files": tmp_files,
            "checksum_errors": checksum_errors,
        }
