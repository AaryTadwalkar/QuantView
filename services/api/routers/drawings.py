"""
1. What this file does:
   Implements the Chart Drawing Persistence, Annotations, and CRUD REST API endpoints for the QuantView Gateway
   (Milestone M6-13, Gate G4).

2. Overall design:
   Provides thread-safe in-memory cache and atomic local JSON filesystem synchronization for user drawings:
     - GET /api/v1/charts/drawings: Retrieves drawing records with optional instrument symbol filtering.
     - POST /api/v1/charts/drawings: Upserts single or batch drawing entities and persists them to Data/drawings/drawings.json.
     - DELETE /api/v1/charts/drawings/{drawing_id}: Deletes a specific drawing annotation by unique ID.
     - DELETE /api/v1/charts/drawings: Purges all drawings associated with a target instrument symbol.

3. Elements in the file:
   - DrawingStore: Thread-safe repository managing in-memory drawing cache with JSON filesystem persistence.
   - get_drawing_store: FastAPI dependency provider and factory returning the active DrawingStore instance.
   - router: FastAPI APIRouter configured with /api/v1/charts/drawings prefix and drawings tag.
   - get_drawings: Endpoint handler retrieving stored chart drawings.
   - save_drawings: Endpoint handler upserting drawings to memory and disk.
   - delete_drawings_by_symbol: Endpoint handler purging drawings for a specific instrument.
   - delete_drawing: Endpoint handler removing a single drawing by unique ID.

4. Final output of the file:
   - Exported APIRouter instance for registration in services.api.main.
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from services.api.schemas.drawings import DrawingDeleteResponse, DrawingRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/charts/drawings", tags=["drawings"])


class DrawingStore:
    """
    1. The use of class:
       Thread-safe in-memory store and JSON persistence manager for chart drawing annotations.

    2. What the class contains:
       - _drawings: Dictionary mapping drawing ID strings to DrawingRecord models.
       - _lock: Reentrant threading lock guarding concurrent mutation and reads.
       - _storage_path: Path to the local JSON persistence file.

    3. Technologies used and why:
       threading.RLock for thread synchronization under ASGI multi-worker execution,
       pathlib.Path and json for atomic file serialization and recovery.

    4. Key design and overall design of the class:
       Provides sub-millisecond in-memory lookups while ensuring persistent durability to disk
       with automatic directory creation and safe in-memory fallback on I/O failures.
    """

    def __init__(self, storage_path: Optional[Union[str, Path]] = None) -> None:
        """
        1. The use of function:
           Initializes the DrawingStore instance and loads existing records from storage if present.

        2. How does the specific function work:
           Resolves storage path against repository root if relative, initializes internal cache
           and reentrant lock, and invokes _load_from_disk to hydrate state.

        3. Concepts used in the function:
           State hydration, path resolution, lock instantiation.

        4. Places where this function is imported and used:
           Invoked when constructing the default singleton and in unit tests.

        5. Final output of the function, before and after:
           Before: Uninitialized store. After: Hydrated DrawingStore instance ready for thread-safe access.
        """
        self._lock = threading.RLock()
        self._drawings: Dict[str, DrawingRecord] = {}

        if storage_path is None:
            repo_root = Path(__file__).resolve().parents[3]
            self._storage_path = repo_root / "Data" / "drawings" / "drawings.json"
        else:
            self._storage_path = Path(storage_path)

        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """
        1. The use of function:
           Reads stored drawings from the local JSON file into the in-memory cache.

        2. How does the specific function work:
           Checks if self._storage_path exists. If present, deserializes JSON records and populates
           _drawings. Gracefully catches file or parsing exceptions to ensure memory-only fallback.

        3. Concepts used in the function:
           JSON deserialization, schema validation, safe error suppression.

        4. Places where this function is imported and used:
           Called internally during __init__.

        5. Final output of the function, before and after:
           Before: Empty cache. After: Cache populated with records from disk.
        """
        if not self._storage_path.is_file():
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    try:
                        record = DrawingRecord.model_validate(item)
                        self._drawings[record.id] = record
                    except Exception as err:
                        logger.warning("Skipping invalid drawing record: %s", err)
        except Exception as exc:
            logger.warning("Failed to load drawings from %s: %s", self._storage_path, exc)

    def _save_to_disk(self) -> None:
        """
        1. The use of function:
           Persists the current in-memory drawing records to the local JSON file.

        2. How does the specific function work:
           Creates parent directories if necessary, dumps all records as serialized dictionaries
           to a temporary file, and atomically replaces the target file to avoid corruption.

        3. Concepts used in the function:
           Atomic file replacement, JSON serialization, resilient error handling.

        4. Places where this function is imported and used:
           Called internally after mutating methods (upsert, delete, delete_by_symbol).

        5. Final output of the function, before and after:
           Before: Unsynchronized disk state. After: Synchronized drawings.json file.
        """
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = [rec.model_dump() for rec in self._drawings.values()]
            temp_path = self._storage_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            temp_path.replace(self._storage_path)
        except Exception as exc:
            logger.warning("Failed to persist drawings to %s: %s", self._storage_path, exc)

    def get_all(self, symbol: Optional[str] = None) -> List[DrawingRecord]:
        """
        1. The use of function:
           Retrieves all drawings from the store, optionally filtered by instrument symbol.

        2. How does the specific function work:
           Acquires lock. If symbol is provided, filters drawings matching the raw or normalized symbol
           token; otherwise, returns all drawings.

        3. Concepts used in the function:
           Thread safety, symbol token normalization, query filtering.

        4. Places where this function is imported and used:
           Invoked by the get_drawings endpoint.

        5. Final output of the function, before and after:
           Before: Query filter parameter. After: List of matching DrawingRecord models.
        """
        with self._lock:
            if symbol is None:
                return list(self._drawings.values())

            target_norm = (
                symbol.strip().upper().replace(" ", "").replace(":", "").replace("_", "").replace("-", "")
            )
            results: List[DrawingRecord] = []
            for rec in self._drawings.values():
                rec_norm = (
                    rec.symbol.strip().upper().replace(" ", "").replace(":", "").replace("_", "").replace("-", "")
                )
                if rec.symbol.strip().upper() == symbol.strip().upper() or rec_norm == target_norm:
                    results.append(rec)
            return results

    def get_by_id(self, drawing_id: str) -> Optional[DrawingRecord]:
        """
        1. The use of function:
           Finds an individual drawing record by its unique identifier.

        2. How does the specific function work:
           Acquires lock and performs O(1) dictionary key lookup.

        3. Concepts used in the function:
           Direct key lookup, thread synchronization.

        4. Places where this function is imported and used:
           Invoked internally and in verification routines.

        5. Final output of the function, before and after:
           Before: drawing_id string. After: Optional DrawingRecord model.
        """
        with self._lock:
            return self._drawings.get(drawing_id)

    def upsert(self, records: List[DrawingRecord]) -> List[DrawingRecord]:
        """
        1. The use of function:
           Inserts or updates one or more drawing records in memory and triggers disk synchronization.

        2. How does the specific function work:
           Acquires lock. Iterates through records, updating their updated_at timestamps,
           stores them in _drawings, invokes _save_to_disk, and returns the updated models.

        3. Concepts used in the function:
           Idempotent upsert, timestamp updating, synchronized persistence.

        4. Places where this function is imported and used:
           Invoked by the save_drawings endpoint.

        5. Final output of the function, before and after:
           Before: Incoming drawing records. After: Persisted drawing records list.
        """
        now = int(time.time())
        with self._lock:
            for rec in records:
                if not rec.created_at:
                    rec.created_at = now
                rec.updated_at = now
                self._drawings[rec.id] = rec
            self._save_to_disk()
            return records

    def delete(self, drawing_id: str) -> bool:
        """
        1. The use of function:
           Removes a single drawing record by unique identifier.

        2. How does the specific function work:
           Acquires lock. If drawing_id exists, removes it from _drawings, invokes _save_to_disk,
           and returns True; otherwise, returns False.

        3. Concepts used in the function:
           Key removal, disk sync, existence check.

        4. Places where this function is imported and used:
           Invoked by the delete_drawing endpoint.

        5. Final output of the function, before and after:
           Before: Target drawing_id. After: True if removed, False if not found.
        """
        with self._lock:
            if drawing_id in self._drawings:
                del self._drawings[drawing_id]
                self._save_to_disk()
                return True
            return False

    def delete_by_symbol(self, symbol: str) -> int:
        """
        1. The use of function:
           Purges all drawings belonging to a given instrument symbol.

        2. How does the specific function work:
           Acquires lock. Finds all drawing IDs matching symbol raw or normalized, deletes them,
           synchronizes to disk if count > 0, and returns the number of deleted records.

        3. Concepts used in the function:
           Bulk deletion, predicate filtering, disk sync.

        4. Places where this function is imported and used:
           Invoked by the delete_drawings_by_symbol endpoint.

        5. Final output of the function, before and after:
           Before: Target symbol string. After: Integer count of removed records.
        """
        target_norm = (
            symbol.strip().upper().replace(" ", "").replace(":", "").replace("_", "").replace("-", "")
        )
        with self._lock:
            to_delete: List[str] = []
            for id_, rec in self._drawings.items():
                rec_norm = (
                    rec.symbol.strip().upper().replace(" ", "").replace(":", "").replace("_", "").replace("-", "")
                )
                if rec.symbol.strip().upper() == symbol.strip().upper() or rec_norm == target_norm:
                    to_delete.append(id_)

            for id_ in to_delete:
                del self._drawings[id_]

            if to_delete:
                self._save_to_disk()
            return len(to_delete)

    def clear(self) -> None:
        """
        1. The use of function:
           Purges all drawings from memory and removes the disk file if present.

        2. How does the specific function work:
           Acquires lock. Clears internal dictionary and calls _save_to_disk with empty state.

        3. Concepts used in the function:
           Cache flush, test teardown.

        4. Places where this function is imported and used:
           Used primarily in test fixtures for isolation.

        5. Final output of the function, before and after:
           Before: Populated cache. After: Empty cache and empty JSON file.
        """
        with self._lock:
            self._drawings.clear()
            self._save_to_disk()


_GLOBAL_DRAWING_STORE: Optional[DrawingStore] = None
_STORE_LOCK = threading.Lock()


def get_drawing_store() -> DrawingStore:
    """
    1. The use of function:
       FastAPI dependency provider returning the global DrawingStore singleton instance.

    2. How does the specific function work:
       Ensures thread-safe lazy instantiation of _GLOBAL_DRAWING_STORE and returns the instance.

    3. Concepts used in the function:
       Singleton pattern, double-checked locking, dependency injection.

    4. Places where this function is imported and used:
       Injected into route handlers across services.api.routers.drawings.

    5. Final output of the function, before and after:
       Before: None. After: Singleton DrawingStore instance.
    """
    global _GLOBAL_DRAWING_STORE
    if _GLOBAL_DRAWING_STORE is None:
        with _STORE_LOCK:
            if _GLOBAL_DRAWING_STORE is None:
                _GLOBAL_DRAWING_STORE = DrawingStore()
    return _GLOBAL_DRAWING_STORE


@router.get(
    "",
    response_model=List[DrawingRecord],
    summary="Get Chart Drawings",
    description="Retrieves saved chart drawing records, optionally filtered by instrument symbol.",
)
@router.get(
    "/",
    response_model=List[DrawingRecord],
    include_in_schema=False,
)
def get_drawings(
    symbol: Optional[str] = Query(default=None, description="Optional instrument symbol filter"),
    store: DrawingStore = Depends(get_drawing_store),
) -> List[DrawingRecord]:
    """
    1. The use of function:
       FastAPI endpoint retrieving drawing annotations from the store.

    2. How does the specific function work:
       Delegates query to store.get_all, filtering by symbol if supplied.

    3. Concepts used in the function:
       REST GET query handler, optional parameter filtering.

    4. Places where this function is imported and used:
       Mounted under GET /api/v1/charts/drawings.

    5. Final output of the function, before and after:
       Before: Optional symbol filter. After: List of DrawingRecord models.
    """
    return store.get_all(symbol=symbol)


@router.post(
    "",
    response_model=List[DrawingRecord],
    summary="Save Chart Drawings",
    description="Upserts one or more chart drawing records and persists them to local storage.",
)
@router.post(
    "/",
    response_model=List[DrawingRecord],
    include_in_schema=False,
)
def save_drawings(
    payload: Union[DrawingRecord, List[DrawingRecord]] = Body(...),
    store: DrawingStore = Depends(get_drawing_store),
) -> List[DrawingRecord]:
    """
    1. The use of function:
       FastAPI endpoint accepting single or bulk drawing entities for persistence.

    2. How does the specific function work:
       Normalizes input payload to a list of DrawingRecord models and executes store.upsert.

    3. Concepts used in the function:
       Polymorphic payload handling, upsert persistence, REST POST handler.

    4. Places where this function is imported and used:
       Mounted under POST /api/v1/charts/drawings.

    5. Final output of the function, before and after:
       Before: DrawingRecord or list of DrawingRecord. After: List of saved DrawingRecord models.
    """
    records = [payload] if isinstance(payload, DrawingRecord) else payload
    return store.upsert(records)


@router.delete(
    "",
    response_model=DrawingDeleteResponse,
    response_model_exclude_none=True,
    summary="Delete Drawings by Symbol",
    description="Deletes all drawings associated with a specific instrument symbol.",
)
@router.delete(
    "/",
    response_model=DrawingDeleteResponse,
    response_model_exclude_none=True,
    include_in_schema=False,
)
def delete_drawings_by_symbol(
    symbol: str = Query(..., description="Target instrument symbol"),
    store: DrawingStore = Depends(get_drawing_store),
) -> DrawingDeleteResponse:
    """
    1. The use of function:
       FastAPI endpoint deleting all drawings associated with a specific instrument symbol.

    2. How does the specific function work:
       Invokes store.delete_by_symbol and returns a deletion confirmation dictionary.

    3. Concepts used in the function:
       Bulk resource deletion, query parameter binding, REST DELETE handler.

    4. Places where this function is imported and used:
       Mounted under DELETE /api/v1/charts/drawings.

    5. Final output of the function, before and after:
       Before: Target symbol query string. After: JSON confirmation with deleted count.
    """
    count = store.delete_by_symbol(symbol)
    return {
        "status": "deleted",
        "symbol": symbol,
        "count": count,
    }


@router.delete(
    "/{drawing_id}",
    response_model=DrawingDeleteResponse,
    response_model_exclude_none=True,
    summary="Delete Drawing by ID",
    description="Deletes an individual chart drawing record by its unique identifier.",
)
def delete_drawing(
    drawing_id: str,
    store: DrawingStore = Depends(get_drawing_store),
) -> DrawingDeleteResponse:
    """
    1. The use of function:
       FastAPI endpoint deleting a single drawing annotation by unique identifier.

    2. How does the specific function work:
       Calls store.delete(drawing_id). If found and removed, returns confirmation;
       otherwise, raises HTTP 404 Not Found.

    3. Concepts used in the function:
       REST resource deletion, 404 error signaling, path parameter extraction.

    4. Places where this function is imported and used:
       Mounted under DELETE /api/v1/charts/drawings/{drawing_id}.

    5. Final output of the function, before and after:
       Before: drawing_id path string. After: JSON confirmation dict or HTTP 404.
    """
    deleted = store.delete(drawing_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Drawing with id '{drawing_id}' not found",
        )
    return {
        "status": "deleted",
        "id": drawing_id,
    }
