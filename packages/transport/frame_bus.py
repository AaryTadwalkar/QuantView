"""
1. What this file does:
   Implements the high-performance, in-memory transport spine (FrameBus) and canonical market data
   frame representation (TickFrame) for QuantView Stage 7. Provides pre-allocated circular ring buffering,
   strictly monotonic uint64 sequence generation, and non-blocking pub/sub topic dispatching.

2. Overall design:
   Decouples market data producers (live Upstox WebSocket feed and 24/7 historical ReplayPlayer) from
   downstream consumers (streaming candle builder, paper trading execution engine, and WebSocket API bridge):
     - TickFrame: Frozen immutable dataclass encapsulating standard tick attributes in integer paise.
     - FrameBus: Fixed-capacity circular array ring buffer pre-allocated in Python memory (default 65,536).
     - Non-blocking dispatch: Asynchronous subscribers receive tick frames via bounded asyncio.Queue.
     - Resilience: Queue overflows are accounted for in telemetry without stalling producer ingestion.

3. Elements in the file:
   - DEFAULT_RING_BUFFER_CAPACITY: Constant specifying 65,536 default slots.
   - DEFAULT_MAX_QUEUE_SIZE: Constant specifying 10,000 default subscriber queue capacity.
   - TickFrame: Canonical immutable dataclass representing an individual market data tick.
   - FrameBus: Circular ring-buffer message broker with topic subscription and snapshot replay.

4. Final output of the file:
   Exported TickFrame and FrameBus classes ready for production transport across the runtime.
"""

import asyncio
import threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Optional, Union

DEFAULT_RING_BUFFER_CAPACITY = 65536
DEFAULT_MAX_QUEUE_SIZE = 10000


@dataclass(frozen=True)
class TickFrame:
    """
    1. The use of class:
       Immutable, high-performance canonical market data tick frame circulating on the FrameBus.

    2. What the class contains:
       - sequence_id: Monotonic uint64 index assigned by the FrameBus.
       - instrument_key: Unique identifier of the financial instrument (e.g. 'NSE_INDEX|Nifty 50').
       - timestamp_epoch_sec: UTC Unix timestamp in integer seconds.
       - timestamp_iso: ISO 8601 string representation of the tick timestamp.
       - price_paise: Price expressed as integer paise (1 INR = 100 paise).
       - volume: Traded volume or cumulative traded volume today.
       - open_interest: Optional open interest count for derivative contracts.
       - bid_price_paise: Best bid price in paise.
       - ask_price_paise: Best ask price in paise.
       - bid_qty: Best bid quantity.
       - ask_qty: Best ask quantity.
       - is_replayed: Boolean flag indicating if frame originated from historical replay.

    3. Technologies used and why:
       Python dataclasses with frozen=True for immutability, low memory footprint, and thread safety.

    4. Key design and overall design of the class:
       Standardizes live WebSocket quotes, historical replays, and synthetic micro-ticks into an identical,
       unambiguous data structure preventing representation discrepancies across all downstream pipelines.
    """

    sequence_id: int
    instrument_key: str
    timestamp_epoch_sec: int
    timestamp_iso: str
    price_paise: int
    volume: int
    open_interest: Optional[int] = None
    bid_price_paise: Optional[int] = None
    ask_price_paise: Optional[int] = None
    bid_qty: Optional[int] = None
    ask_qty: Optional[int] = None
    is_replayed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Converts the immutable TickFrame instance into a serializable dictionary.

        2. How does the specific function work:
           Invokes dataclasses.asdict to create a deep dictionary copy of all frame fields.

        3. Concepts used in the function:
           Dataclass serialization, shallow dictionary mapping.

        4. Places where this function is imported and used:
           Used by API gateway bridges, JSON serializers, and logging handlers.

        5. Final output of the function, before and after:
           Before: Immutable TickFrame instance. After: Standard Python dictionary containing all frame fields.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], default_sequence_id: int = 0) -> "TickFrame":
        """
        1. The use of function:
           Constructs a canonical TickFrame from raw dictionary payloads with flexible field normalization.

        2. How does the specific function work:
           - Extracts and validates mandatory instrument_key.
           - Converts price to integer paise from price_paise, price, or ltp fields.
           - Derives timestamp_epoch_sec and timestamp_iso bidirectionally, defaulting to UTC now.
           - Extracts volume and derivative metrics (open interest, top bid/ask depth).
           - Instantiates and returns a frozen TickFrame.

        3. Concepts used in the function:
           Data normalization, defensive coercion, ISO 8601 parsing.

        4. Places where this function is imported and used:
           Invoked by FrameBus.publish() when accepting raw dictionary payloads.

        5. Final output of the function, before and after:
           Before: Heterogeneous dictionary with potential missing optional fields.
           After: Strictly validated, immutable TickFrame instance.
        """
        instrument_key = str(data["instrument_key"])
        seq_id = int(data.get("sequence_id", default_sequence_id))

        # Price coercion to paise
        if "price_paise" in data and data["price_paise"] is not None:
            price_paise = int(data["price_paise"])
        elif "price" in data and data["price"] is not None:
            price_paise = int(round(float(data["price"]) * 100))
        elif "ltp" in data and data["ltp"] is not None:
            price_paise = int(round(float(data["ltp"]) * 100))
        else:
            price_paise = 0

        # Timestamp normalization
        if "timestamp_epoch_sec" in data and "timestamp_iso" in data:
            epoch_sec = int(data["timestamp_epoch_sec"])
            iso_str = str(data["timestamp_iso"])
        elif "timestamp_epoch_sec" in data:
            epoch_sec = int(data["timestamp_epoch_sec"])
            iso_str = datetime.fromtimestamp(epoch_sec, tz=timezone.utc).isoformat()
        elif "timestamp_iso" in data:
            iso_str = str(data["timestamp_iso"])
            try:
                dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
                epoch_sec = int(dt.timestamp())
            except Exception:
                now_dt = datetime.now(timezone.utc)
                epoch_sec = int(now_dt.timestamp())
                iso_str = now_dt.isoformat()
        else:
            now_dt = datetime.now(timezone.utc)
            epoch_sec = int(now_dt.timestamp())
            iso_str = now_dt.isoformat()

        # Volume extraction
        vol_raw = data.get("volume", data.get("volume_traded_today", data.get("ltq", 0)))
        volume = int(vol_raw) if vol_raw is not None else 0

        # Open interest
        oi_raw = data.get("open_interest", data.get("oi"))
        oi = int(oi_raw) if oi_raw is not None and oi_raw != "" else None

        # Bid / Ask paise
        bid_px_paise: Optional[int] = None
        if "bid_price_paise" in data and data["bid_price_paise"] is not None:
            bid_px_paise = int(data["bid_price_paise"])
        elif "bid_px_1" in data and data["bid_px_1"] is not None:
            bid_px_paise = int(round(float(data["bid_px_1"]) * 100))

        ask_px_paise: Optional[int] = None
        if "ask_price_paise" in data and data["ask_price_paise"] is not None:
            ask_px_paise = int(data["ask_price_paise"])
        elif "ask_px_1" in data and data["ask_px_1"] is not None:
            ask_px_paise = int(round(float(data["ask_px_1"]) * 100))

        # Bid / Ask quantities
        bid_qty_raw = data.get("bid_qty", data.get("bid_qty_1"))
        bid_qty = int(bid_qty_raw) if bid_qty_raw is not None else None

        ask_qty_raw = data.get("ask_qty", data.get("ask_qty_1"))
        ask_qty = int(ask_qty_raw) if ask_qty_raw is not None else None

        is_replayed = bool(data.get("is_replayed", False))

        return cls(
            sequence_id=seq_id,
            instrument_key=instrument_key,
            timestamp_epoch_sec=epoch_sec,
            timestamp_iso=iso_str,
            price_paise=price_paise,
            volume=volume,
            open_interest=oi,
            bid_price_paise=bid_px_paise,
            ask_price_paise=ask_px_paise,
            bid_qty=bid_qty,
            ask_qty=ask_qty,
            is_replayed=is_replayed,
        )


class FrameBus:
    """
    1. The use of class:
       Central real-time transport spine providing pre-allocated circular buffering and non-blocking pub/sub.

    2. What the class contains:
       - _capacity: Pre-allocated circular ring buffer capacity (default 65,536).
       - _buffer: Pre-allocated Python list holding TickFrame references.
       - _sequence_counter: Monotonic uint64 sequence generator.
       - _sequence_lock: Threading lock protecting sequence increments and buffer updates.
       - _subscribers: Dictionary mapping asyncio.Queue instances to optional instrument topic filter sets.
       - _subscribers_lock: Threading lock protecting subscriber registration and teardown.
       - _total_published: Counter tracking aggregate published frames.
       - _dropped_frames: Counter tracking dropped frames caused by saturated subscriber queues.

    3. Technologies used and why:
       - Fixed-capacity circular array for zero-allocation, O(1) buffer indexing without unbounded memory leaks.
       - Python asyncio.Queue for non-blocking asynchronous downstream consumption.
       - Threading locks for thread-safe cross-thread frame ingestion from background threads and WebSocket collectors.

    4. Key design and overall design of the class:
       Acts as the decoupled spinal bus between data producers (live Upstox collector, replay player) and consumers
       (candle builder, strategy engine, API WebSocket bridge). It guarantees monotonic sequence continuity,
       deterministic circular retention, and sub-millisecond dispatch latency.
    """

    def __init__(self, capacity: int = DEFAULT_RING_BUFFER_CAPACITY) -> None:
        """
        1. The use of function:
           Initializes the FrameBus ring buffer, sequence counters, locks, and subscriber registry.

        2. How does the specific function work:
           - Pre-allocates a fixed-size Python list of length capacity filled with None.
           - Sets sequence counter and publication metrics to zero.
           - Creates re-entrant / mutual exclusion locks for thread safety.
           - Initializes empty subscriber mapping.

        3. Concepts used in the function:
           Circular ring buffer pre-allocation, synchronization primitives, state initialization.

        4. Places where this function is imported and used:
           Instantiated at runtime startup by LiveDaemon, PaperTradingDaemon, ReplayPlayer, and test fixtures.

        5. Final output of the function, before and after:
           Before: Uninitialized memory. After: Ready-to-operate FrameBus instance with pre-allocated buffer slots.
        """
        if capacity <= 0:
            raise ValueError(f"Ring buffer capacity must be positive, got {capacity}")
        self._capacity = capacity
        self._buffer: List[Optional[TickFrame]] = [None] * capacity
        self._sequence_counter: int = 0
        self._sequence_lock = threading.Lock()
        self._subscribers: Dict[asyncio.Queue[TickFrame], Optional[FrozenSet[str]]] = {}
        self._subscribers_lock = threading.Lock()
        self._total_published: int = 0
        self._dropped_frames: int = 0

    def _next_sequence_id(self) -> int:
        """
        1. The use of function:
           Generates the next monotonic uint64 sequence identifier in a thread-safe manner.

        2. How does the specific function work:
           Acquires sequence lock, increments counter, masks to 64-bit unsigned integer range, and returns value.

        3. Concepts used in the function:
           Monotonic counter, uint64 integer masking, critical section synchronization.

        4. Places where this function is imported and used:
           Called internally by FrameBus.publish().

        5. Final output of the function, before and after:
           Before: Current sequence value N. After: Strictly incremented sequence value N + 1.
        """
        with self._sequence_lock:
            self._sequence_counter = (self._sequence_counter + 1) & 0xFFFFFFFFFFFFFFFF
            return self._sequence_counter

    def publish(self, frame_data: Union[Dict[str, Any], TickFrame]) -> TickFrame:
        """
        1. The use of function:
           Publishes a tick frame to the circular ring buffer and dispatches it non-blocking to active subscribers.

        2. How does the specific function work:
           - Increments the monotonic sequence counter under lock.
           - Assigns the sequence ID to the TickFrame (or constructs TickFrame from dictionary).
           - Writes frame into circular ring buffer at index (sequence_id - 1) % capacity.
           - Takes a thread-safe snapshot of active subscribers.
           - Dispatches frame via put_nowait() to matched subscribers, handling saturated queues by logging dropped counts.

        3. Concepts used in the function:
           Circular buffer indexing, non-blocking queue dispatch, thread-safe iteration, backpressure handling.

        4. Places where this function is imported and used:
           Called by live WebSocket collector threads, historical ReplayPlayer tasks, and mock publishers.

        5. Final output of the function, before and after:
           Before: Unsequenced frame data or dictionary.
           After: Sequenced, stored TickFrame circulated to all matched active subscriber queues.
        """
        # Assign monotonic sequence and store in pre-allocated circular ring buffer
        with self._sequence_lock:
            self._sequence_counter = (self._sequence_counter + 1) & 0xFFFFFFFFFFFFFFFF
            seq_id = self._sequence_counter

            if isinstance(frame_data, TickFrame):
                frame = replace(frame_data, sequence_id=seq_id)
            elif isinstance(frame_data, dict):
                frame = TickFrame.from_dict(frame_data, default_sequence_id=seq_id)
            else:
                raise TypeError(f"frame_data must be dict or TickFrame, got {type(frame_data)}")

            idx = (seq_id - 1) % self._capacity
            self._buffer[idx] = frame
            self._total_published += 1

        # Non-blocking dispatch to active subscribers
        with self._subscribers_lock:
            subs = list(self._subscribers.items())

        if subs:
            frame_inst = frame.instrument_key
            for queue, filter_keys in subs:
                if filter_keys is not None and frame_inst not in filter_keys:
                    continue

                # Deliver without blocking
                try:
                    queue.put_nowait(frame)
                except asyncio.QueueFull:
                    self._dropped_frames += 1
                except Exception:
                    # In case of cross-thread event loop execution
                    try:
                        loop = queue._loop  # type: ignore[attr-defined]
                        if loop.is_running():
                            loop.call_soon_threadsafe(self._safe_put_nowait, queue, frame)
                    except Exception:
                        self._dropped_frames += 1

        return frame

    def _safe_put_nowait(self, queue: asyncio.Queue[TickFrame], frame: TickFrame) -> None:
        """
        1. The use of function:
           Helper callback for safe cross-thread non-blocking queue insertion.

        2. How does the specific function work:
           Attempts queue.put_nowait(frame) and increments _dropped_frames on QueueFull.

        3. Concepts used in the function:
           Thread-safe dispatch callback, non-blocking queue insertion.

        4. Places where this function is imported and used:
           Invoked via loop.call_soon_threadsafe from publish().

        5. Final output of the function, before and after:
           Before: Frame pending cross-thread enqueue. After: Frame enqueued or dropped counter incremented.
        """
        try:
            queue.put_nowait(frame)
        except asyncio.QueueFull:
            self._dropped_frames += 1

    def subscribe(
        self,
        instrument_keys: Optional[List[str]] = None,
        max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE,
    ) -> asyncio.Queue[TickFrame]:
        """
        1. The use of function:
           Creates and registers an asynchronous subscriber queue with optional instrument topic filtering.

        2. How does the specific function work:
           - Instantiates an asyncio.Queue bounded by max_queue_size.
           - Converts instrument_keys list to an immutable frozenset for O(1) membership testing.
           - Registers queue in the internal subscriber dictionary under lock.
           - Returns the newly created queue.

        3. Concepts used in the function:
           Pub/Sub topic subscription, bounded queue allocation, frozenset topic index.

        4. Places where this function is imported and used:
           Called by streaming candle builders, strategy execution hosts, and WebSocket API client sessions.

        5. Final output of the function, before and after:
           Before: Unregistered subscriber. After: Active registered asyncio.Queue receiving published frames.
        """
        queue: asyncio.Queue[TickFrame] = asyncio.Queue(maxsize=max_queue_size)
        filter_keys = frozenset(instrument_keys) if (instrument_keys is not None and len(instrument_keys) > 0) else None

        with self._subscribers_lock:
            self._subscribers[queue] = filter_keys

        return queue

    def unsubscribe(self, queue: asyncio.Queue[TickFrame]) -> None:
        """
        1. The use of function:
           Unregisters and removes an active subscriber queue from the FrameBus.

        2. How does the specific function work:
           Acquires subscribers lock and pops queue from dictionary if present.

        3. Concepts used in the function:
           Safe teardown, lock-protected dictionary removal.

        4. Places where this function is imported and used:
           Called when consumer tasks complete, strategies stop, or client WebSockets disconnect.

        5. Final output of the function, before and after:
           Before: Active subscriber in registry. After: Subscriber removed, no further frames dispatched to it.
        """
        with self._subscribers_lock:
            self._subscribers.pop(queue, None)

    def get_recent(self, limit: int = 1000, instrument_key: Optional[str] = None) -> List[TickFrame]:
        """
        1. The use of function:
           Retrieves recent snapshot frames from the circular ring buffer in chronological order.

        2. How does the specific function work:
           - Determines range of valid sequence IDs stored in the circular buffer under lock.
           - If instrument_key is None, slices the most recent limit frames in ascending sequence order.
           - If instrument_key is provided, traverses backwards from newest to oldest up to limit matches,
             then reverses results to restore chronological order.

        3. Concepts used in the function:
           Circular buffer backward indexing, chronological sorting, snapshot catch-up query.

        4. Places where this function is imported and used:
           Called during new client WebSocket connection handshakes to provide initial chart backfill.

        5. Final output of the function, before and after:
           Before: Empty snapshot list. After: Chronologically ordered list of recent TickFrame instances.
        """
        with self._sequence_lock:
            current_seq = self._sequence_counter
            if current_seq == 0 or limit <= 0:
                return []

            min_available_seq = max(1, current_seq - self._capacity + 1)

            if instrument_key is None:
                start_seq = max(min_available_seq, current_seq - limit + 1)
                frames: List[TickFrame] = []
                for seq in range(start_seq, current_seq + 1):
                    idx = (seq - 1) % self._capacity
                    f = self._buffer[idx]
                    if f is not None and f.sequence_id == seq:
                        frames.append(f)
                return frames

            # Filtered by instrument_key: scan backwards from newest to oldest
            matched: List[TickFrame] = []
            for seq in range(current_seq, min_available_seq - 1, -1):
                idx = (seq - 1) % self._capacity
                f = self._buffer[idx]
                if f is not None and f.sequence_id == seq and f.instrument_key == instrument_key:
                    matched.append(f)
                    if len(matched) >= limit:
                        break

            matched.reverse()
            return matched

    def stats(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Returns real-time telemetry metrics regarding FrameBus throughput, capacity, and backpressure.

        2. How does the specific function work:
           Reads internal counters under sequence and subscriber locks and packages them into a telemetry dictionary.

        3. Concepts used in the function:
           System observability, telemetry reporting, lock-protected metric snapshots.

        4. Places where this function is imported and used:
           Called by health-check endpoints, daemon status monitors, and test verifications.

        5. Final output of the function, before and after:
           Before: Unaggregated internal counters.
           After: Dictionary containing total_published, current_sequence_id, active_subscribers,
                  buffer_capacity, buffer_size, and dropped_frames.
        """
        with self._sequence_lock:
            total_pub = self._total_published
            curr_seq = self._sequence_counter

        with self._subscribers_lock:
            active_subs = len(self._subscribers)

        return {
            "total_published": total_pub,
            "current_sequence_id": curr_seq,
            "active_subscribers": active_subs,
            "buffer_capacity": self._capacity,
            "buffer_size": min(total_pub, self._capacity),
            "dropped_frames": self._dropped_frames,
        }

    def clear(self) -> None:
        """
        1. The use of function:
           Resets the circular ring buffer, sequence counters, and dropped frames metrics.

        2. How does the specific function work:
           Acquires sequence lock, clears list contents back to None, and resets numeric counters to 0.

        3. Concepts used in the function:
           State reset, testing hygiene, memory clearing.

        4. Places where this function is imported and used:
           Called between isolated unit test cases and simulated session resets.

        5. Final output of the function, before and after:
           Before: Populated ring buffer. After: Cleared ring buffer with zeroed counters.
        """
        with self._sequence_lock:
            self._buffer = [None] * self._capacity
            self._sequence_counter = 0
            self._total_published = 0
            self._dropped_frames = 0
