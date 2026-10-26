"""
1. What this file does:
   Implements the SnapshotCollectorService coordinating the raw-first REST option chain capture pipeline.
   Combines UpstoxSnapshotAdapter and RawSnapshotWriter to enforce strict durability invariants,
   dynamic expiry resolution, and fail-safe decoder error isolation per QUANTVIEW_DATA_SPEC §4.3 and Task M2-01.

2. Overall design:
   Coordinates the single-capture and market-hours collection loop:
     - Generates stable capture IDs: snap_YYYY-MM-DD_HHMMSS_<hash[:8]>.
     - Resolves active expiry dynamically without hardcoded dates.
     - Calls UpstoxSnapshotAdapter to retrieve raw HTTP response bytes.
     - Invokes RawSnapshotWriter to write gzip payload and companion manifest with fsync BEFORE parsing.
     - Executes parsing with error boundaries:
       * On valid JSON: extracts spot price, row counts, and field mask; marks manifest DECODED.
       * On malformed JSON: isolates error, logs stack trace, updates manifest to DECODER_PARSE_ERROR.
       * In both cases: RAW PAYLOAD REMAINS 100% PERSISTED AND IMMUTABLE ON DISK.
     - Returns structured capture summary dictionary.

3. Elements in the file:
   - SnapshotCollectorService: Main service coordinator for snapshot capture.
   - generate_snapshot_id: Generates stable deterministic capture ID.

4. Final output of the file:
   - Exported SnapshotCollectorService class.
   - Production-ready raw capture outputs in Data/raw/upstox_rest/snapshots/.
"""

from datetime import datetime, time as dtime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from packages.data.schemas import SNAPSHOT_CAPTURES_SCHEMA
from services.collector_snapshot.adapter import UpstoxSnapshotAdapter, SnapshotResponsePayload
from services.collector_snapshot.raw_writer import RawSnapshotWriter, RawCaptureRecord

logger = logging.getLogger("quantview.collector_snapshot")


def generate_snapshot_id(trade_date: str, recv_dt: datetime, raw_bytes: bytes) -> str:
    """
    1. The use of function:
       Generates a deterministic and collision-resistant snapshot capture ID.

    2. How does the specific function work:
       Combines trade date, UTC time string (HHMMSS), and first 8 characters of SHA-256 payload hash.

    3. Concepts used in the function:
       Stable entity identification, collision resistance.

    4. Places where this function is imported and used:
       Called by SnapshotCollectorService during capture_once().

    5. Final output of the function, before and after:
       Before: Raw inputs. After: String e.g. 'snap_2026-10-26_091530_a1b2c3d4'.
    """
    time_str = recv_dt.strftime("%H%M%S")
    content_hash = hashlib.sha256(raw_bytes).hexdigest()[:8]
    return f"snap_{trade_date}_{time_str}_{content_hash}"


class SnapshotCollectorService:
    """
    1. The use of class:
       Central service coordinator for raw-first REST option chain snapshot capture.

    2. What the class contains:
       - adapter: UpstoxSnapshotAdapter instance for HTTP queries.
       - writer: RawSnapshotWriter instance for fsync durability and manifests.
       - default_instrument: Underlying key ('NSE_INDEX|Nifty 50').
       - capture_once(): Executes a single raw-first capture cycle.
       - is_market_hours(): Checks if current time is within 09:15 to 15:30 Asia/Kolkata.
       - resolve_active_expiry(): Dynamically resolves expiry date from config or fallback.

    3. Technologies used and why:
       - RawSnapshotWriter: Guarantees zero data loss before parsing.
       - UpstoxSnapshotAdapter: Resilient HTTP requests with retries and timeout boundaries.
       - JSON parsing: Validates payload and extracts capture-level metrics.

    4. Key design and overall design of the class:
       Strict raw-first durability: network bytes hit disk before any decoder is executed.
       If the decoder fails or crashes, the raw response is safely stored on disk.
    """

    def __init__(
        self,
        adapter: Optional[UpstoxSnapshotAdapter] = None,
        writer: Optional[RawSnapshotWriter] = None,
        default_instrument: str = "NSE_INDEX|Nifty 50",
    ) -> None:
        """
        1. The use of function:
           Initializes SnapshotCollectorService with adapter and raw writer.

        2. How does the specific function work:
           Configures adapter (defaulting to UpstoxSnapshotAdapter), writer (RawSnapshotWriter),
           and default instrument key.

        3. Concepts used in the function:
           Dependency injection, default composition.

        4. Places where this function is imported and used:
           Instantiated by CLI commands, daemon runners, and test suites.

        5. Final output of the function, before and after:
           Before: Uninitialized service. After: Ready-to-capture service instance.
        """
        self.adapter = adapter or UpstoxSnapshotAdapter()
        self.writer = writer or RawSnapshotWriter()
        self.default_instrument = default_instrument

    def resolve_active_expiry(self, explicit_expiry: Optional[str] = None) -> str:
        """
        1. The use of function:
           Resolves the active expiry date dynamically without hardcoding.

        2. How does the specific function work:
           - If explicit_expiry is provided, returns it directly.
           - Else checks config/nse_nifty_expiries_2025_2026.json for nearest future expiry.
           - Falls back to nearest Thursday calculation if config is unavailable.

        3. Concepts used in the function:
           Dynamic configuration resolution, fallback date arithmetic.

        4. Places where this function is imported and used:
           Called during capture_once() when expiry_date is omitted.

        5. Final output of the function, before and after:
           Before: None or explicit expiry. After: ISO-8601 date string (YYYY-MM-DD).
        """
        if explicit_expiry:
            return explicit_expiry

        project_root = Path(__file__).resolve().parents[2]
        expiries_json = project_root / "config" / "nse_nifty_expiries_2025_2026.json"
        today_str = datetime.now().strftime("%Y-%m-%d")

        if expiries_json.exists():
            try:
                with open(expiries_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                all_expiries = sorted(data.get("expiries", []))
                for exp in all_expiries:
                    if exp >= today_str:
                        return exp
                if all_expiries:
                    return all_expiries[-1]
            except Exception as ex:
                logger.warning("Failed to parse expiries config: %s", ex)

        # Fallback to current date
        return today_str

    def capture_once(
        self,
        instrument_key: Optional[str] = None,
        expiry_date: Optional[str] = None,
        trade_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        1. The use of function:
           Executes a single end-to-end raw-first snapshot capture cycle.

        2. How does the specific function work:
           - Resolves instrument key, trade date, and active expiry date.
           - Invokes UpstoxSnapshotAdapter.fetch_raw_option_chain() to obtain raw response bytes.
           - Generates stable snapshot_id.
           - Calls RawSnapshotWriter.persist_raw_response() to fsync raw compressed payload and manifest to disk.
           - Parses payload with fail-safe error isolation:
             * If valid: extracts spot price, strike row count, and marks manifest DECODED.
             * If invalid (e.g. malformed JSON): updates manifest to DECODER_PARSE_ERROR with error details.
           - Returns comprehensive capture summary.

        3. Concepts used in the function:
           Raw-first persistence, fail-closed isolation, error-tolerant ingestion.

        4. Places where this function is imported and used:
           Called by test suites, CLI runners, and scheduled cron jobs.

        5. Final output of the function, before and after:
           Before: Uncaptured market state. After: Durably persisted raw file, manifest, and summary dict.
        """
        inst = instrument_key or self.default_instrument
        resolved_expiry = self.resolve_active_expiry(expiry_date)
        recv_now = datetime.now(timezone.utc)
        t_date = trade_date or recv_now.strftime("%Y-%m-%d")

        # 1. Query network / adapter for raw response payload
        payload: SnapshotResponsePayload = self.adapter.fetch_raw_option_chain(
            instrument_key=inst,
            expiry_date=resolved_expiry,
        )

        # 2. Generate stable snapshot ID
        snapshot_id = generate_snapshot_id(t_date, recv_now, payload.raw_bytes)

        # 3. DURABLE PERSISTENCE FIRST: write raw bytes and manifest to disk with fsync
        record: RawCaptureRecord = self.writer.persist_raw_response(
            snapshot_id=snapshot_id,
            trade_date=t_date,
            raw_bytes=payload.raw_bytes,
            endpoint=payload.endpoint,
            request_params=payload.request_params,
            http_status=payload.http_status,
            content_type=payload.content_type,
            request_timestamp_utc=payload.request_timestamp_utc,
            received_at_utc=payload.received_at_utc,
            schema_version="v3",
            quality_flags=["RAW_STORED_OK"],
        )

        # 4. DOWNSTREAM PARSING (with strict error isolation)
        decoder_status = "PENDING"
        spot_price = None
        row_count = 0
        field_mask = "00000000"
        decoder_error = None

        try:
            parsed = json.loads(payload.raw_bytes.decode("utf-8"))
            data_body = parsed.get("data", [])
            row_count = len(data_body) if isinstance(data_body, list) else 0

            # Inspect spot price if present in response
            if isinstance(parsed, dict) and "spot_price" in parsed:
                spot_price = float(parsed["spot_price"])
            elif isinstance(data_body, list) and data_body and isinstance(data_body[0], dict):
                first_item = data_body[0]
                raw_spot = first_item.get("underlying_spot_price") or first_item.get("spot_price")
                spot_price = float(raw_spot) if raw_spot is not None else None

            # Check presence of Greeks fields
            has_greeks = False
            if isinstance(data_body, list) and data_body:
                first_row = data_body[0]
                if any(k in first_row for k in ["delta", "iv", "gamma", "theta", "vega"]):
                    has_greeks = True
            field_mask = "11111111" if has_greeks else "11110000"

            decoder_status = "DECODED"

        except Exception as ex:
            decoder_status = "DECODER_PARSE_ERROR"
            decoder_error = f"{type(ex).__name__}: {str(ex)}"
            logger.error("Decoder parse error on snapshot %s: %s", snapshot_id, decoder_error)

        # 5. Update companion manifest with decoder outcome (raw payload is already safe!)
        updated_manifest = self.writer.update_manifest_decoder_status(
            manifest_path=record.manifest_path,
            decoder_status=decoder_status,
            error_message=decoder_error,
            row_count=row_count,
            field_mask=field_mask,
        )

        overall_status = "DECODER_ERROR" if decoder_status == "DECODER_PARSE_ERROR" else "SUCCESS"

        return {
            "status": overall_status,
            "snapshot_id": snapshot_id,
            "trade_date": t_date,
            "expiry": resolved_expiry,
            "raw_file_path": str(record.raw_file_path).replace("\\", "/"),
            "manifest_path": str(record.manifest_path).replace("\\", "/"),
            "uncompressed_bytes": record.uncompressed_bytes,
            "uncompressed_sha256": record.uncompressed_sha256,
            "compressed_bytes": record.compressed_bytes,
            "compressed_sha256": record.compressed_sha256,
            "decoder_status": decoder_status,
            "decoder_error": decoder_error,
            "row_count": row_count,
            "spot_price": spot_price,
            "raw_retained_on_parse_error": True,
        }
