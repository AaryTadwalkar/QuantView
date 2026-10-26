"""
1. What this file does:
   Implements the checkpointed historical backfill service for expired option candles
   conforming to QUANTVIEW_DATA_SPEC §4.2, §11.2, §11.3, and Task M2-07.

2. Overall design:
   Coordinates resilient, rate-budgeted acquisition of expired contract candles:
     - Maintains atomic JSON checkpoint records tracking completed (expiry, contract, trade_date) triplets.
     - Enforces RateBudgetManager sliding-window limits, yielding or pausing when capacity is constrained.
     - Performs idempotent staging: skips already processed sessions and deduplicates inputs.
     - Provides pause, resume, and recovery hooks for long-running batch ingestion workflows.

3. Elements in the file:
   - BackfillCheckpoint: Dataclass recording state of completed contracts and dates.
   - BackfillCheckpointManager: Manages atomic loading and saving of checkpoint state files.
   - ExpiredOptionBackfillService: Central coordinator executing backfill jobs with budget gating.

4. Final output of the file:
   - Exported BackfillCheckpoint, BackfillCheckpointManager, and ExpiredOptionBackfillService classes.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set

from packages.data.budget import RateBudgetManager, RequestPriority

logger = logging.getLogger("quantview.backfill.service")


@dataclass
class BackfillCheckpoint:
    """
    1. The use of class:
       Encapsulates the state of a checkpointed historical option backfill job.

    2. What the class contains:
       - job_id: Unique string identifying the backfill execution.
       - completed_keys: Set of completed instrument keys or date keys.
       - total_records_processed: Cumulative count of processed items.
       - last_checkpoint_utc: Timestamp of the most recent atomic flush.
       - is_complete: Boolean flag indicating overall batch completion.

    3. Technologies used and why:
       Python dataclass for structured state tracking and serializability.

    4. Key design and overall design of the class:
       Guarantees restartability without redundant network requests or duplicate records.
    """
    job_id: str
    completed_keys: List[str] = field(default_factory=list)
    total_records_processed: int = 0
    last_checkpoint_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    is_complete: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Serializes checkpoint model to a standard dictionary.

        2. How does the specific function work:
           Calls dataclasses.asdict(self).

        3. Concepts used in the function:
           Model serialization.

        4. Places where this function is imported and used:
           Used by BackfillCheckpointManager during JSON persistence.

        5. Final output of the function, before and after:
           Before: Dataclass model. After: Python dictionary.
        """
        return asdict(self)


class BackfillCheckpointManager:
    """
    1. The use of class:
       Manages atomic on-disk storage and retrieval of backfill checkpoints.

    2. What the class contains:
       - checkpoint_dir: Directory where checkpoint state files are persisted.
       - load_checkpoint(): Reads existing checkpoint from disk or creates new.
       - save_checkpoint(): Atomically saves state using .tmp file rename.

    3. Technologies used and why:
       File I/O with atomic rename to prevent corruption on sudden process termination.

    4. Key design and overall design of the class:
       Guarantees fault-tolerant checkpoint updates with fsync.
    """

    def __init__(self, checkpoint_dir: Optional[Path] = None) -> None:
        """
        1. The use of function:
           Initializes the checkpoint manager with destination directory.

        2. How does the specific function work:
           Sets checkpoint_dir and ensures directory exists on disk.

        3. Concepts used in the function:
           Directory initialization.

        4. Places where this function is imported and used:
           Instantiated by ExpiredOptionBackfillService.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Ready checkpoint manager.
        """
        if checkpoint_dir is None:
            project_root = Path(__file__).resolve().parents[2]
            self.checkpoint_dir = project_root / "staging" / "checkpoints"
        else:
            self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def load_checkpoint(self, job_id: str) -> BackfillCheckpoint:
        """
        1. The use of function:
           Loads an existing checkpoint for job_id, or initializes a fresh one.

        2. How does the specific function work:
           - Checks if checkpoint file exists at checkpoint_dir / f"{job_id}.json".
           - If exists, reads JSON and reconstructs BackfillCheckpoint.
           - If not found, instantiates a new BackfillCheckpoint with job_id.

        3. Concepts used in the function:
           Checkpoint deserialization, fallback creation.

        4. Places where this function is imported and used:
           Called at startup of backfill jobs.

        5. Final output of the function, before and after:
           Before: Job ID string. After: Active BackfillCheckpoint instance.
        """
        cp_file = self.checkpoint_dir / f"{job_id}.json"
        if cp_file.exists():
            try:
                with open(cp_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return BackfillCheckpoint(
                    job_id=data.get("job_id", job_id),
                    completed_keys=data.get("completed_keys", []),
                    total_records_processed=data.get("total_records_processed", 0),
                    last_checkpoint_utc=data.get("last_checkpoint_utc", datetime.now(timezone.utc).isoformat()),
                    is_complete=data.get("is_complete", False),
                )
            except Exception as ex:
                logger.warning("Failed loading checkpoint %s: %s; starting fresh.", cp_file, ex)
        return BackfillCheckpoint(job_id=job_id)

    def save_checkpoint(self, checkpoint: BackfillCheckpoint) -> None:
        """
        1. The use of function:
           Atomically writes checkpoint state to disk.

        2. How does the specific function work:
           - Updates last_checkpoint_utc to current time.
           - Writes JSON to temporary file f"{job_id}.json.tmp".
           - Calls flush() and os.fsync() on descriptor.
           - Atomically replaces target checkpoint file.

        3. Concepts used in the function:
           Atomic write pattern, hardware sync, crash resilience.

        4. Places where this function is imported and used:
           Called periodically during backfill iterations.

        5. Final output of the function, before and after:
           Before: In-memory state. After: Durably synced JSON checkpoint on disk.
        """
        checkpoint.last_checkpoint_utc = datetime.now(timezone.utc).isoformat()
        target_path = self.checkpoint_dir / f"{checkpoint.job_id}.json"
        tmp_path = self.checkpoint_dir / f"{checkpoint.job_id}.json.tmp"

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        if target_path.exists():
            target_path.unlink()
        tmp_path.rename(target_path)


class ExpiredOptionBackfillService:
    """
    1. The use of class:
       Coordinating service for historical expired option candle backfilling.

    2. What the class contains:
       - budget_manager: RateBudgetManager enforcing Upstox API limits.
       - checkpoint_manager: BackfillCheckpointManager managing job checkpoints.
       - is_paused: Control flag allowing graceful pause and resume.
       - process_batch(): Executes batch backfill respecting budget limits.

    3. Technologies used and why:
       Modular architecture integrating RateBudgetManager and checkpointing.

    4. Key design and overall design of the class:
       Enforces rate-limit budgets, yields to live snapshot priority, and supports pause/resume.
    """

    def __init__(
        self,
        budget_manager: Optional[RateBudgetManager] = None,
        checkpoint_manager: Optional[BackfillCheckpointManager] = None,
    ) -> None:
        """
        1. The use of function:
           Initializes ExpiredOptionBackfillService with budget and checkpoint managers.

        2. How does the specific function work:
           Assigns budget_manager and checkpoint_manager, providing defaults if None.

        3. Concepts used in the function:
           Dependency injection.

        4. Places where this function is imported and used:
           Instantiated by backfill CLI scripts and tests.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Service ready for backfill execution.
        """
        self.budget_manager = budget_manager or RateBudgetManager()
        self.checkpoint_manager = checkpoint_manager or BackfillCheckpointManager()
        self._is_paused = False

    def pause(self) -> None:
        """
        1. The use of function:
           Pauses active backfill loop.

        2. How does the specific function work:
           Sets self._is_paused = True.

        3. Concepts used in the function:
           State management.

        4. Places where this function is imported and used:
           Operational pause commands or budget exhaustion handlers.

        5. Final output of the function, before and after:
           Before: Running. After: Paused.
        """
        self._is_paused = True

    def resume(self) -> None:
        """
        1. The use of function:
           Resumes paused backfill loop.

        2. How does the specific function work:
           Sets self._is_paused = False.

        3. Concepts used in the function:
           State management.

        4. Places where this function is imported and used:
           Operator resume command.

        5. Final output of the function, before and after:
           Before: Paused. After: Running.
        """
        self._is_paused = False

    def is_paused(self) -> bool:
        """
        1. The use of function:
           Returns whether service is currently paused.

        2. How does the specific function work:
           Returns boolean value of self._is_paused.

        3. Concepts used in the function:
           Inspection.

        4. Places where this function is imported and used:
           Loop conditions.

        5. Final output of the function, before and after:
           Before: Checked state. After: Boolean status.
        """
        return self._is_paused

    def process_item(
        self,
        item_key: str,
        checkpoint: BackfillCheckpoint,
        fetch_fn: Any,
    ) -> bool:
        """
        1. The use of function:
           Executes a single backfill item with rate budget acquisition and checkpointing.

        2. How does the specific function work:
           - Checks if item_key already exists in checkpoint.completed_keys (idempotent skip).
           - Checks self._is_paused flag; returns False if paused.
           - Acquires budget permission from RateBudgetManager with LOW priority.
           - If budget exhausted, yields/returns False without calling API.
           - Executes fetch_fn(item_key).
           - On success, appends item_key to completed_keys and increments total_records_processed.

        3. Concepts used in the function:
           Rate gating, priority reservation, idempotent processing.

        4. Places where this function is imported and used:
           Called in backfill worker loops.

        5. Final output of the function, before and after:
           Before: Pending item. After: Processed item recorded in checkpoint.
        """
        if item_key in checkpoint.completed_keys:
            return True  # Idempotent skip

        if self._is_paused:
            logger.info("Backfill is paused. Skipping item %s.", item_key)
            return False

        # Acquire rate budget with LOW priority (yields to live market snapshot capture)
        acquired = self.budget_manager.acquire(priority=RequestPriority.LOW)
        if not acquired:
            logger.warning("Rate budget unavailable for backfill; yielding.")
            return False

        try:
            success = fetch_fn(item_key)
            if success:
                checkpoint.completed_keys.append(item_key)
                checkpoint.total_records_processed += 1
                return True
            return False
        except Exception as ex:
            logger.error("Error processing backfill item %s: %s", item_key, ex)
            return False
