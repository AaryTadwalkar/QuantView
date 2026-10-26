"""
1. What this file does:
   Implements the single-owner process lease and exclusive OS file lock (SingleOwnerLease).
   Guarantees that exactly one collector_ws instance owns the physical WebSocket connection,
   failing immediately and closed before any network sockets are opened per QUANTVIEW_DATA_SPEC §2.1,
   §11.5, QUANTVIEW_MASTER_SPEC §3, and Task M2-04.

2. Overall design:
   Coordinates mutual exclusion across local operating system processes:
     - Maintains a lock file at Data/raw/upstox_ws/.collector_ws.lock.
     - Acquires an exclusive, non-blocking kernel lock (msvcrt.locking on Windows, fcntl.flock on POSIX).
     - Writes owner metadata: PID, host, start timestamp, and unique lease token UUID.
     - If another process already holds the lock, raises DuplicateCollectorInstanceError immediately.
     - Supports context manager syntax (`with SingleOwnerLease(): ...`).
     - Releases kernel lock and unlinks lock file cleanly upon normal shutdown or exception.

3. Elements in the file:
   - DuplicateCollectorInstanceError: Exception raised when another instance holds the active lease.
   - LeaseMetadata: Dataclass recording lease owner PID, hostname, token, and timestamp.
   - SingleOwnerLease: Central class managing exclusive OS file lock acquisition, heartbeat, and release.

4. Final output of the file:
   - Exported SingleOwnerLease, LeaseMetadata, and DuplicateCollectorInstanceError classes.
   - Lock file at Data/raw/upstox_ws/.collector_ws.lock during active execution.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import platform
import sys
from typing import Any, Dict, Optional
import uuid

logger = logging.getLogger("quantview.collector_ws.lease")


class DuplicateCollectorInstanceError(RuntimeError):
    """
    1. The use of class:
       Exception raised when an attempt is made to start a duplicate collector_ws instance.

    2. What the class contains:
       Standard Exception constructor with diagnostic details of existing lock holder.

    3. Technologies used and why:
       Standard Python RuntimeError subclass.

    4. Key design and overall design of the class:
       Enforces single-writer boundary by aborting secondary processes before network connection.
    """
    pass


@dataclass
class LeaseMetadata:
    """
    1. The use of class:
       Encapsulates process ownership information written into the active lease lock file.

    2. What the class contains:
       - lease_token: UUID string uniquely identifying this acquisition.
       - pid: Operating system process identifier of the owner.
       - hostname: Machine name running the collector.
       - acquired_at_utc: ISO-8601 UTC timestamp of acquisition.
       - python_version: Executing Python runtime version.

    3. Technologies used and why:
       Python dataclasses for clean JSON serialization.

    4. Key design and overall design of the class:
       Provides forensic visibility into which process currently holds exclusive ownership.
    """
    lease_token: str
    pid: int
    hostname: str
    acquired_at_utc: str
    python_version: str


class SingleOwnerLease:
    """
    1. The use of class:
       Manages an exclusive OS-level file lock ensuring only one collector_ws instance runs at a time.

    2. What the class contains:
       - lock_file_path: Path to the exclusive lock file (.collector_ws.lock).
       - _file_handle: Open file handle backing the kernel lock.
       - _lease_metadata: LeaseMetadata instance of active acquisition.
       - acquire(): Obtains exclusive kernel lock non-blockingly; raises if already locked.
       - release(): Releases kernel lock, closes handle, and cleans up lock file.

    3. Technologies used and why:
       - msvcrt on Windows / fcntl on POSIX for kernel-level non-blocking mutual exclusion.
       - Pathlib for filesystem path management.

    4. Key design and overall design of the class:
       Fail-closed single writer contract: if a secondary process starts, it detects the lock
       and terminates immediately before opening a second WebSocket connection.
    """

    def __init__(self, lock_file_path: Optional[Path] = None) -> None:
        """
        1. The use of function:
           Initializes SingleOwnerLease with the target lock file path.

        2. How does the specific function work:
           Resolves lock file path, defaulting to Data/raw/upstox_ws/.collector_ws.lock.

        3. Concepts used in the function:
           Path configuration, default path resolution.

        4. Places where this function is imported and used:
           Used by collector_ws daemon, CLI runners, and unit test suites.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: SingleOwnerLease instance configured.
        """
        if lock_file_path is None:
            project_root = Path(__file__).resolve().parents[2]
            self.lock_file_path = project_root / "Data" / "raw" / "upstox_ws" / ".collector_ws.lock"
        else:
            self.lock_file_path = Path(lock_file_path)

        self.meta_file_path = self.lock_file_path.with_name(self.lock_file_path.name + ".meta.json")
        self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_handle = None
        self._is_locked = False
        self._metadata: Optional[LeaseMetadata] = None

    @property
    def is_locked(self) -> bool:
        """
        1. The use of function:
           Inspects whether this lease instance currently holds the exclusive kernel lock.

        2. How does the specific function work:
           Returns the internal boolean flag `_is_locked`.

        3. Concepts used in the function:
           Encapsulated state inspection.

        4. Places where this function is imported and used:
           Used by collector runners and test assertions to verify lock status.

        5. Final output of the function, before and after:
           Before: Unchecked state. After: Boolean indicating if lock is held.
        """
        return self._is_locked

    @property
    def metadata(self) -> Optional[LeaseMetadata]:
        """
        1. The use of function:
           Retrieves LeaseMetadata containing PID, host, and token for the active acquisition.

        2. How does the specific function work:
           Returns `_metadata` dataclass instance if held, else None.

        3. Concepts used in the function:
           Lease ownership telemetry.

        4. Places where this function is imported and used:
           Used by logging, diagnostic reporting, and verification suites.

        5. Final output of the function, before and after:
           Before: Unaccessed metadata. After: LeaseMetadata instance or None.
        """
        return self._metadata

    def acquire(self) -> LeaseMetadata:
        """
        1. The use of function:
           Acquires exclusive non-blocking OS kernel lock on the lock file.

        2. How does the specific function work:
           - Opens lock file in read/write/append mode (`a+b`).
           - On Windows: calls msvcrt.locking(fileno, msvcrt.LK_NBLCK, 1).
           - On POSIX: calls fcntl.flock(fileno, fcntl.LOCK_EX | fcntl.LOCK_NB).
           - If locking fails: reads existing metadata and raises DuplicateCollectorInstanceError.
           - If locking succeeds: truncates file, writes fresh LeaseMetadata JSON, flushes and fsyncs.

        3. Concepts used in the function:
           Kernel mutual exclusion, non-blocking lock acquisition, fail-closed isolation.

        4. Places where this function is imported and used:
           Called during collector startup before network connection.

        5. Final output of the function, before and after:
           Before: Unlocked. After: Exclusive lock held; LeaseMetadata returned.
        """
        if self._is_locked:
            assert self._metadata is not None
            return self._metadata

        try:
            self._file_handle = open(self.lock_file_path, "a+b")
            self._file_handle.seek(0)
        except Exception as ex:
            raise RuntimeError(f"Failed to open lock file at {self.lock_file_path}: {ex}")

        # Attempt platform-specific non-blocking exclusive lock
        fileno = self._file_handle.fileno()
        locked_successfully = False

        if sys.platform == "win32":
            import msvcrt
            try:
                msvcrt.locking(fileno, msvcrt.LK_NBLCK, 1)
                locked_successfully = True
            except OSError as ex:
                locked_successfully = False
        else:
            import fcntl
            try:
                fcntl.flock(fileno, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked_successfully = True
            except (BlockingIOError, OSError):
                locked_successfully = False

        if not locked_successfully:
            # Read existing owner metadata for informative error
            existing_info = "Unknown"
            if self.meta_file_path.exists():
                try:
                    with open(self.meta_file_path, "r", encoding="utf-8") as mf:
                        existing_info = mf.read()
                except Exception:
                    pass

            self._file_handle.close()
            self._file_handle = None
            raise DuplicateCollectorInstanceError(
                f"Another collector_ws instance already holds the lock at {self.lock_file_path}. "
                f"Existing lease details: {existing_info.strip()}"
            )

        # Write fresh lease metadata
        now_iso = datetime.now(timezone.utc).isoformat()
        meta = LeaseMetadata(
            lease_token=str(uuid.uuid4()),
            pid=os.getpid(),
            hostname=platform.node(),
            acquired_at_utc=now_iso,
            python_version=platform.python_version(),
        )

        try:
            payload = json.dumps(asdict(meta), indent=2).encode("utf-8")
            tmp_meta = self.meta_file_path.with_suffix(".tmp")
            with open(tmp_meta, "wb") as mf:
                mf.write(payload)
                mf.flush()
                os.fsync(mf.fileno())
            tmp_meta.replace(self.meta_file_path)
        except Exception as ex:
            logger.warning("Could not write lease metadata: %s", ex)

        self._is_locked = True
        self._metadata = meta
        logger.info("Acquired exclusive collector_ws lease (PID %d, Token %s)", meta.pid, meta.lease_token)
        return meta

    def release(self) -> None:
        """
        1. The use of function:
           Releases kernel lock, closes file descriptor, and unlinks lock file.

        2. How does the specific function work:
           - On Windows: calls msvcrt.locking(fileno, msvcrt.LK_UNLCK, 1).
           - On POSIX: calls fcntl.flock(fileno, fcntl.LOCK_UN).
           - Closes file handle.
           - Safely unlinks the lock file.

        3. Concepts used in the function:
           Lock disposal, resource cleanup.

        4. Places where this function is imported and used:
           Collector shutdown, context manager __exit__().

        5. Final output of the function, before and after:
           Before: Lock held. After: Lock released, file removed.
        """
        if not self._is_locked or self._file_handle is None:
            return

        fileno = self._file_handle.fileno()
        try:
            if sys.platform == "win32":
                import msvcrt
                try:
                    self._file_handle.seek(0)
                    msvcrt.locking(fileno, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(fileno, fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            try:
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None
            self._is_locked = False
            self._metadata = None

            # Unlink lock file and companion metadata
            try:
                if self.lock_file_path.exists():
                    self.lock_file_path.unlink()
            except Exception as ex:
                logger.debug("Could not unlink lock file: %s", ex)

            try:
                if self.meta_file_path.exists():
                    self.meta_file_path.unlink()
            except Exception as ex:
                logger.debug("Could not unlink meta file: %s", ex)

        logger.info("Released collector_ws lease.")

    def __enter__(self) -> LeaseMetadata:
        """
        1. The use of function:
           Supports Python context management protocol (`with SingleOwnerLease():`).

        2. How does the specific function work:
           Invokes self.acquire() and returns the acquired LeaseMetadata.

        3. Concepts used in the function:
           Context manager protocol, RAII resource acquisition.

        4. Places where this function is imported and used:
           Used by collector service runners and test fixtures for safe scope management.

        5. Final output of the function, before and after:
           Before: Unlocked context. After: Locked context with LeaseMetadata returned.
        """
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        1. The use of function:
           Ensures clean release of exclusive kernel lock and file cleanup on context exit.

        2. How does the specific function work:
           Invokes self.release() regardless of whether exceptions were raised in the block.

        3. Concepts used in the function:
           Deterministic cleanup, RAII pattern, fail-safe unlock.

        4. Places where this function is imported and used:
           Invoked automatically at end of `with SingleOwnerLease():` blocks.

        5. Final output of the function, before and after:
           Before: Lock held. After: Lock guaranteed released and lock file unlinked.
        """
        self.release()
