"""
1. What this file does:
   Defines the service boundary for collector_ws (live Upstox WebSocket market data streaming).
   Re-exports the raw segment writer, binary framing protocol, single-owner lease, and subscription
   manager per QUANTVIEW_DATA_SPEC §4.5, QUANTVIEW_MASTER_SPEC §3, and Tasks M2-03, M2-04.

2. Overall design:
   collector_ws coordinates live WebSocket market data:
     - Framing vendor binary frames into envelope records with magic and CRC32 (services.collector_ws.framing).
     - Streaming into crash-resilient .partial files with batched fsync (<= 1s loss window).
     - Segment rotation, gzip compression, and companion manifest publication (RawSegmentWriter).
     - Automated crash recovery and partial-file quarantine (recover_session_partials).
     - Single-owner process mutual exclusion before network connection (SingleOwnerLease).
     - Multi-source subscription set union and feed mode resolution (SubscriptionManager).
     - Remains strictly raw-capture-only until M7-01 (when FrameBus real-time decoding begins).

3. Elements in the file:
   - SERVICE_NAME: Constant service identifier ('collector_ws').
   - Re-exported classes: RawSegmentWriter, SegmentManifest, ParsedFrame, pack_frame, unpack_frames_from_bytes,
     SingleOwnerLease, LeaseMetadata, DuplicateCollectorInstanceError,
     SubscriptionManager, FeedMode, SubscriptionConfig, SubscriptionRejection.

4. Final output of the file:
   - Public package interface for services.collector_ws.
"""

from services.collector_ws.client import (
    UpstoxWebSocketClient,
    WebSocketClientConfig,
)
from services.collector_ws.decoder import (
    DECODER_VERSION,
    WsQuote,
    WsQuoteDecoder,
)
from services.collector_ws.framing import (
    FRAME_MAGIC,
    HEADER_SIZE,
    ParsedFrame,
    pack_frame,
    unpack_frames_from_bytes,
)
from services.collector_ws.lease import (
    DuplicateCollectorInstanceError,
    LeaseMetadata,
    SingleOwnerLease,
)
from services.collector_ws.raw_segment_writer import RawSegmentWriter, SegmentManifest
from services.collector_ws.subscription import (
    FeedMode,
    SubscriptionConfig,
    SubscriptionManager,
    SubscriptionRejection,
)

SERVICE_NAME = "collector_ws"

__all__ = [
    "SERVICE_NAME",
    "FRAME_MAGIC",
    "HEADER_SIZE",
    "ParsedFrame",
    "pack_frame",
    "unpack_frames_from_bytes",
    "RawSegmentWriter",
    "SegmentManifest",
    "DuplicateCollectorInstanceError",
    "LeaseMetadata",
    "SingleOwnerLease",
    "FeedMode",
    "SubscriptionConfig",
    "SubscriptionManager",
    "SubscriptionRejection",
    "DECODER_VERSION",
    "WsQuote",
    "WsQuoteDecoder",
    "UpstoxWebSocketClient",
    "WebSocketClientConfig",
]
