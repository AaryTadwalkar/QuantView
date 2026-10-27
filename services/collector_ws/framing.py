"""
1. What this file does:
   Defines the binary framing protocol and serialization envelope for live Upstox WebSocket market ticks.
   Provides deterministic header packing, CRC32 payload verification, and stream unpacking with error
   recovery per QUANTVIEW_DATA_SPEC §4.5, QUANTVIEW_MASTER_SPEC §3, and Task M2-03.

2. Overall design:
   Enforces crash-resilient framing for raw WebSocket stream storage:
     - Magic identifier (4 bytes: b'QVWS') for reliable record synchronization.
     - Collector sequence number (8 bytes uint64, big-endian) for monotonic gap and deduplication tracking.
     - Receive timestamp (8 bytes int64, big-endian) recording arrival time in UTC epoch microseconds.
     - Payload length (4 bytes uint32, big-endian).
     - Payload CRC32 checksum (4 bytes uint32, big-endian) guaranteeing byte-exact integrity.
     - Raw payload bytes (N bytes) preserved unmodified.
     - Resilient unpacker that parses stream bytes, accepts valid frames, and isolates truncated/corrupt trailing fragments.

3. Elements in the file:
   - FRAME_MAGIC: 4-byte constant identifier (b'QVWS').
   - HEADER_SIZE: Fixed 28-byte header size.
   - ParsedFrame: Dataclass encapsulating parsed header fields and raw payload.
   - pack_frame: Function serializing a raw payload into framed binary bytes.
   - unpack_frames_from_bytes: Function parsing binary streams into ParsedFrame instances with corruption recovery.

4. Final output of the file:
   - Exported ParsedFrame dataclass, pack_frame, and unpack_frames_from_bytes functions.
"""

import struct
import zlib
from dataclasses import dataclass
from typing import List, Optional, Tuple

FRAME_MAGIC = b"QVWS"
# Magic(4s) + SeqNum(Q, 8B) + RecvTimeUs(q, 8B) + PayloadLen(I, 4B) + CRC32(I, 4B) = 28 bytes
HEADER_FORMAT = ">4sQqII"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


@dataclass
class ParsedFrame:
    """
    1. The use of class:
       Encapsulates a parsed WebSocket frame record extracted from raw segment streams.

    2. What the class contains:
       - sequence_number: Monotonic local sequence integer.
       - recv_time_us: Microsecond UTC timestamp of frame receipt.
       - payload: Exact binary bytes of the vendor WebSocket frame.
       - payload_crc32: Computed CRC32 checksum of the payload.

    3. Technologies used and why:
       Python dataclasses for strongly-typed, immutable record transfer.

    4. Key design and overall design of the class:
       Maintains full causal provenance and byte-exact fidelity for downstream recovery and decoding.
    """
    sequence_number: int
    recv_time_us: int
    payload: bytes
    payload_crc32: int


def pack_frame(sequence_number: int, recv_time_us: int, payload: bytes) -> bytes:
    """
    1. The use of function:
       Packs a raw vendor WebSocket frame into the canonical binary framing envelope.

    2. How does the specific function work:
       - Calculates CRC32 checksum of payload bytes.
       - Packs magic identifier, sequence number, receive time in microseconds, payload length, and CRC32.
       - Appends raw payload bytes.

    3. Concepts used in the function:
       Binary serialization, struct packing, checksum calculation.

    4. Places where this function is imported and used:
       Called by RawSegmentWriter.write_frame().

    5. Final output of the function, before and after:
       Before: Raw payload bytes and metadata. After: Framed byte sequence ready for stream write.
    """
    payload_len = len(payload)
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    header = struct.pack(
        HEADER_FORMAT,
        FRAME_MAGIC,
        sequence_number,
        recv_time_us,
        payload_len,
        crc,
    )
    return header + payload


def unpack_frames_from_bytes(data: bytes) -> Tuple[List[ParsedFrame], bytes, Optional[str]]:
    """
    1. The use of function:
       Parses a byte stream into valid ParsedFrame instances, isolating incomplete or corrupted trailing bytes.

    2. How does the specific function work:
       - Iterates through data seeking FRAME_MAGIC.
       - Reads 28-byte header and unpacks metadata.
       - Verifies that data has enough bytes for the declared payload length.
       - Validates CRC32 of payload against header CRC32.
       - If payload is complete and valid: appends to frames list and advances offset.
       - If trailing bytes are incomplete (cut off mid-frame by process kill): stops and returns trailing bytes.
       - If magic or CRC32 is corrupted: records error reason and returns corrupt segment.

    3. Concepts used in the function:
       Stream parsing, crash-tolerant recovery, defensive truncation boundary isolation.

    4. Places where this function is imported and used:
       Called by RawSegmentWriter.recover_session_partials() and test fixtures.

    5. Final output of the function, before and after:
       Before: Arbitrary byte stream. After: Tuple of (valid_frames, remaining_bytes, error_reason).
    """
    frames: List[ParsedFrame] = []
    offset = 0
    total_len = len(data)

    while offset < total_len:
        # Check if enough bytes remain for header
        if offset + HEADER_SIZE > total_len:
            # Trailing incomplete header bytes
            return frames, data[offset:], "INCOMPLETE_TRAILING_HEADER"

        magic, seq, recv_us, p_len, expected_crc = struct.unpack_from(HEADER_FORMAT, data, offset)

        if magic != FRAME_MAGIC:
            return frames, data[offset:], f"INVALID_MAGIC_AT_OFFSET_{offset}"

        payload_start = offset + HEADER_SIZE
        payload_end = payload_start + p_len

        if payload_end > total_len:
            # Trailing incomplete payload (process crash/kill during write)
            return frames, data[offset:], "INCOMPLETE_TRAILING_PAYLOAD"

        payload = data[payload_start:payload_end]
        actual_crc = zlib.crc32(payload) & 0xFFFFFFFF

        if actual_crc != expected_crc:
            return frames, data[offset:], f"CRC32_MISMATCH_AT_OFFSET_{offset}"

        frames.append(
            ParsedFrame(
                sequence_number=seq,
                recv_time_us=recv_us,
                payload=payload,
                payload_crc32=actual_crc,
            )
        )
        offset = payload_end

    return frames, b"", None
