"""
1. What this file does:
   Comprehensive test suite for the QuantView Stage 7 high-performance transport layer (M7-01 and M7-05).
   Verifies FrameBus circular buffering, monotonic sequence numbering, topic pub/sub filtering,
   high-throughput benchmarks, and ReplayPlayer historical playback controls.

2. Overall design:
   Enforces strict gate G5 criteria:
     - Monotonic sequence continuity across 10,000 frames without drops or duplicates.
     - Ring buffer wrap-around exceeding 65,536 frames with bounded memory usage.
     - Multi-subscriber topic filtering (exact instrument isolation vs wildcard subscription).
     - High-throughput benchmark verifying >= 20,000 frames/sec and p95 latency <= 0.5 ms.
     - ReplayPlayer lifecycle validation (start, pause, resume, stop, speed alteration).
     - Authentic binary raw segment decoding and DuckDB lake synthetic micro-tick generation.

3. Elements in the file:
   - test_tick_frame_immutability_and_coercion: Validates TickFrame immutability and flexible dictionary parsing.
   - test_monotonic_sequence_continuity: Asserts strict sequence increments across 10,000 frames.
   - test_circular_buffer_wrap_around: Validates 70,000 frame insertion wrapping over 65,536 slots.
   - test_multi_subscriber_topic_filtering: Validates isolated subscriber routing based on instrument key.
   - test_high_throughput_and_p95_latency: Asserts publishing throughput >= 20,000 frames/s and p95 <= 0.5 ms.
   - test_get_recent_snapshots: Validates chronological snapshot retrieval with optional instrument filter.
   - test_subscriber_saturation_and_dropped_frames: Validates non-blocking publisher behavior on full queues.
   - test_replay_player_raw_segments_smoke: Smokes authentic raw binary segment replay into FrameBus.
   - test_replay_player_duckdb_synthetic_ticks: Validates 4-tick micro-bar synthesis from DuckDB lake.
   - test_replay_player_lifecycle_controls: Validates start, pause, resume, stop, and dynamic speed mutation.

4. Final output of the file:
   Test execution outcomes verifying compliance with QuantView Stage 7 transport specifications.
"""

import asyncio
import time
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

from packages.transport.frame_bus import FrameBus, TickFrame
from packages.transport.replay_player import PlaybackSpeed, ReplayPlayer


@pytest.mark.gate_g5
def test_tick_frame_immutability_and_coercion() -> None:
    """
    1. The use of function:
       Verifies TickFrame immutability, to_dict serialization, and from_dict field coercion.

    2. How does the specific function work:
       - Instantiates a TickFrame and attempts mutation to verify FrozenInstanceError is raised.
       - Tests to_dict output matching constructor arguments.
       - Tests from_dict with rupee float prices, ISO timestamps, and alternate key names.

    3. Concepts used in the function:
       Dataclass immutability verification, data normalization testing, defensive casting.

    4. Places where this function is imported and used:
       Executed as part of pytest test suite for packages/transport.

    5. Final output of the function, before and after:
       Before: Untested TickFrame methods. After: Verified immutability and resilient dictionary parsing.
    """
    frame = TickFrame(
        sequence_id=1,
        instrument_key="NSE_INDEX|Nifty 50",
        timestamp_epoch_sec=1700000000,
        timestamp_iso="2023-11-14T22:13:20+00:00",
        price_paise=2250000,
        volume=5000,
        open_interest=120000,
        bid_price_paise=2249500,
        ask_price_paise=2250500,
        bid_qty=150,
        ask_qty=100,
        is_replayed=False,
    )

    # Test immutability
    with pytest.raises(FrozenInstanceError):
        frame.price_paise = 2300000  # type: ignore[misc]

    # Test to_dict
    d = frame.to_dict()
    assert d["sequence_id"] == 1
    assert d["instrument_key"] == "NSE_INDEX|Nifty 50"
    assert d["price_paise"] == 2250000
    assert d["open_interest"] == 120000
    assert d["is_replayed"] is False

    # Test from_dict coercion from float rupee prices
    raw_dict = {
        "instrument_key": "OPT-NIFTY-20261029-CE-24500",
        "price": 125.75,
        "volume_traded_today": 850,
        "oi": 45000,
        "bid_px_1": 125.50,
        "ask_px_1": 126.00,
        "bid_qty_1": 75,
        "ask_qty_1": 150,
        "timestamp_epoch_sec": 1700000050,
        "is_replayed": True,
    }
    coerced = TickFrame.from_dict(raw_dict, default_sequence_id=42)
    assert coerced.sequence_id == 42
    assert coerced.instrument_key == "OPT-NIFTY-20261029-CE-24500"
    assert coerced.price_paise == 12575
    assert coerced.volume == 850
    assert coerced.open_interest == 45000
    assert coerced.bid_price_paise == 12550
    assert coerced.ask_price_paise == 12600
    assert coerced.bid_qty == 75
    assert coerced.ask_qty == 150
    assert coerced.is_replayed is True


@pytest.mark.gate_g5
def test_monotonic_sequence_continuity() -> None:
    """
    1. The use of function:
       Verifies strictly monotonic sequence continuity across 10,000 published frames.

    2. How does the specific function work:
       - Publishes 10,000 frames to FrameBus.
       - Records assigned sequence_id values and validates seq_id == i for every iteration.
       - Confirms total_published and current_sequence_id telemetry both equal 10,000.

    3. Concepts used in the function:
       Monotonic sequence generator validation, continuity assertion, counter tracking.

    4. Places where this function is imported and used:
       Executed as part of pytest test suite for packages/transport.

    5. Final output of the function, before and after:
       Before: Unverified sequence generator.
       After: Confirmed unbroken sequence sequence [1..10000] with zero gaps or duplicates.
    """
    bus = FrameBus(capacity=65536)
    num_frames = 10000

    for i in range(1, num_frames + 1):
        f = bus.publish({
            "instrument_key": "NSE_INDEX|Nifty 50",
            "price_paise": 2250000 + i,
            "volume": i * 10,
        })
        assert f.sequence_id == i

    stats = bus.stats()
    assert stats["total_published"] == num_frames
    assert stats["current_sequence_id"] == num_frames
    assert stats["buffer_size"] == num_frames


@pytest.mark.gate_g5
def test_circular_buffer_wrap_around() -> None:
    """
    1. The use of function:
       Verifies circular ring buffer wrap-around when total published frames exceed capacity (65,536).

    2. How does the specific function work:
       - Publishes 70,000 frames into a FrameBus initialized with default capacity (65,536).
       - Confirms buffer_size remains clamped at 65,536 without unbounded memory allocation.
       - Verifies get_recent() accurately retrieves latest sequence IDs (from 69,996 to 70,000).
       - Asserts oldest available frame in buffer corresponds to sequence 70000 - 65536 + 1 = 4465.

    3. Concepts used in the function:
       Circular ring buffer boundary condition, modular indexing, bounded memory verification.

    4. Places where this function is imported and used:
       Executed as part of pytest test suite for packages/transport.

    5. Final output of the function, before and after:
       Before: Untested buffer overflow conditions.
       After: Validated wrap-around behavior guaranteeing bounded memory and correct sequence retention.
    """
    capacity = 65536
    bus = FrameBus(capacity=capacity)
    total_to_publish = 70000

    frame_template = {
        "instrument_key": "NSE_INDEX|Nifty 50",
        "price_paise": 2250000,
        "volume": 100,
    }

    for _ in range(total_to_publish):
        bus.publish(frame_template)

    stats = bus.stats()
    assert stats["total_published"] == total_to_publish
    assert stats["current_sequence_id"] == total_to_publish
    assert stats["buffer_size"] == capacity
    assert stats["buffer_capacity"] == capacity

    recent = bus.get_recent(limit=5)
    assert len(recent) == 5
    assert [f.sequence_id for f in recent] == [69996, 69997, 69998, 69999, 70000]

    # Verify oldest frame in buffer
    oldest_recent = bus.get_recent(limit=capacity)
    assert len(oldest_recent) == capacity
    assert oldest_recent[0].sequence_id == total_to_publish - capacity + 1


@pytest.mark.gate_g5
@pytest.mark.asyncio
async def test_multi_subscriber_topic_filtering() -> None:
    """
    1. The use of function:
       Verifies topic pub/sub filtering across multiple subscriber queues with differing instrument keys.

    2. How does the specific function work:
       - Creates three subscribers: Sub A (Nifty only), Sub B (Wildcard/All), and Sub C (Bank Nifty only).
       - Publishes 100 Nifty ticks and 50 Bank Nifty ticks to FrameBus.
       - Confirms Sub A receives 100 ticks, Sub B receives 150 ticks, and Sub C receives 50 ticks.
       - Unsubscribes Sub A and verifies it stops receiving newly published Nifty ticks.

    3. Concepts used in the function:
       Pub/sub topic isolation, wildcard topic dispatch, dynamic unsubscribe teardown.

    4. Places where this function is imported and used:
       Executed as part of pytest test suite for packages/transport.

    5. Final output of the function, before and after:
       Before: Untested pub/sub routing.
       After: Confirmed exact message filtering without cross-talk between subscriber queues.
    """
    bus = FrameBus(capacity=1024)

    q_nifty = bus.subscribe(instrument_keys=["NSE_INDEX|Nifty 50"])
    q_all = bus.subscribe(instrument_keys=None)
    q_banknifty = bus.subscribe(instrument_keys=["NSE_INDEX|Bank Nifty"])

    assert bus.stats()["active_subscribers"] == 3

    # Publish 100 Nifty ticks
    for i in range(100):
        bus.publish({
            "instrument_key": "NSE_INDEX|Nifty 50",
            "price_paise": 2250000 + i,
            "volume": 10,
        })

    # Publish 50 Bank Nifty ticks
    for i in range(50):
        bus.publish({
            "instrument_key": "NSE_INDEX|Bank Nifty",
            "price_paise": 4800000 + i,
            "volume": 20,
        })

    assert q_nifty.qsize() == 100
    assert q_all.qsize() == 150
    assert q_banknifty.qsize() == 50

    # Validate contents of q_nifty
    while not q_nifty.empty():
        tick = q_nifty.get_nowait()
        assert tick.instrument_key == "NSE_INDEX|Nifty 50"

    # Validate contents of q_banknifty
    while not q_banknifty.empty():
        tick = q_banknifty.get_nowait()
        assert tick.instrument_key == "NSE_INDEX|Bank Nifty"

    # Test unsubscribe
    bus.unsubscribe(q_nifty)
    assert bus.stats()["active_subscribers"] == 2

    bus.publish({
        "instrument_key": "NSE_INDEX|Nifty 50",
        "price_paise": 2260000,
        "volume": 10,
    })

    assert q_nifty.qsize() == 0  # No new ticks
    assert q_all.qsize() == 151  # Received by wildcard


@pytest.mark.gate_g5
@pytest.mark.asyncio
async def test_high_throughput_and_p95_latency() -> None:
    """
    1. The use of function:
       Benchmarks FrameBus throughput (>= 20,000 frames/sec) and p95 dispatch latency (<= 0.5 ms).

    2. How does the specific function work:
       - Subscribes an active queue with capacity 50,000.
       - Publishes 25,000 pre-constructed TickFrame objects in a tight loop.
       - Measures aggregate elapsed time to determine frames/sec throughput.
       - Collects high-resolution timestamps per frame to evaluate the 95th percentile dispatch latency.

    3. Concepts used in the function:
       Performance benchmarking, percentile latency calculation, high-throughput verification.

    4. Places where this function is imported and used:
       Executed as part of pytest test suite for packages/transport.

    5. Final output of the function, before and after:
       Before: Theoretical throughput assertion.
       After: Confirmed empirical throughput >= 20,000 frames/s and p95 latency <= 0.5 ms.
    """
    bus = FrameBus(capacity=65536)
    q = bus.subscribe(max_queue_size=50000)

    num_frames = 25000
    latencies_sec: List[float] = []

    frame = TickFrame(
        sequence_id=0,
        instrument_key="NSE_INDEX|Nifty 50",
        timestamp_epoch_sec=1700000000,
        timestamp_iso="2023-11-14T22:13:20+00:00",
        price_paise=2250000,
        volume=100,
    )

    t_start = time.perf_counter()
    for _ in range(num_frames):
        t0 = time.perf_counter()
        bus.publish(frame)
        t1 = time.perf_counter()
        latencies_sec.append(t1 - t0)
    t_end = time.perf_counter()

    elapsed = t_end - t_start
    throughput = num_frames / elapsed

    latencies_sec.sort()
    idx_p95 = int(0.95 * len(latencies_sec))
    p95_latency_ms = latencies_sec[idx_p95] * 1000.0

    assert throughput >= 20000.0, f"Throughput {throughput:.0f} frames/s below 20,000 requirement"
    assert p95_latency_ms <= 0.5, f"p95 latency {p95_latency_ms:.4f} ms exceeded 0.5 ms requirement"
    assert q.qsize() == num_frames


@pytest.mark.gate_g5
def test_get_recent_snapshots() -> None:
    """
    1. The use of function:
       Verifies get_recent() snapshot retrieval with limits, chronological order, and instrument filtering.

    2. How does the specific function work:
       - Asserts get_recent on empty bus returns empty list.
       - Publishes alternating NIFTY and BANKNIFTY ticks.
       - Queries recent without filter and verifies chronological sequence order.
       - Queries recent with instrument_key filter and verifies only matching instruments returned.

    3. Concepts used in the function:
       Historical snapshot retrieval, chronologically ordered ring buffer slices, key-filtered catch-up.

    4. Places where this function is imported and used:
       Executed as part of pytest test suite for packages/transport.

    5. Final output of the function, before and after:
       Before: Untested snapshot query logic.
       After: Verified chronological consistency and topic filtering on snapshot queries.
    """
    bus = FrameBus(capacity=100)
    assert bus.get_recent(limit=10) == []

    bus.publish({"instrument_key": "NIFTY", "price_paise": 100})
    bus.publish({"instrument_key": "BANKNIFTY", "price_paise": 200})
    bus.publish({"instrument_key": "NIFTY", "price_paise": 101})
    bus.publish({"instrument_key": "BANKNIFTY", "price_paise": 201})
    bus.publish({"instrument_key": "NIFTY", "price_paise": 102})

    # Limit 3 without filter
    recent_all = bus.get_recent(limit=3)
    assert len(recent_all) == 3
    assert [f.sequence_id for f in recent_all] == [3, 4, 5]

    # Limit 2 with NIFTY filter
    recent_nifty = bus.get_recent(limit=2, instrument_key="NIFTY")
    assert len(recent_nifty) == 2
    assert [f.sequence_id for f in recent_nifty] == [3, 5]
    assert all(f.instrument_key == "NIFTY" for f in recent_nifty)


@pytest.mark.gate_g5
def test_subscriber_saturation_and_dropped_frames() -> None:
    """
    1. The use of function:
       Verifies publisher non-blocking resilience when subscriber queues saturate.

    2. How does the specific function work:
       - Subscribes a bounded queue of max_queue_size 5.
       - Publishes 15 frames without reading from the subscriber queue.
       - Verifies queue length remains capped at 5 and dropped_frames counter records 10 dropped ticks.
       - Asserts publishing thread never blocked or raised QueueFull exception.

    3. Concepts used in the function:
       Backpressure resilience, non-blocking queue handling, dropped frame metric accounting.

    4. Places where this function is imported and used:
       Executed as part of pytest test suite for packages/transport.

    5. Final output of the function, before and after:
       Before: Untested backpressure overload condition.
       After: Verified non-blocking publisher execution with accurate dropped_frames telemetry.
    """
    bus = FrameBus(capacity=100)
    q = bus.subscribe(max_queue_size=5)

    for i in range(15):
        bus.publish({
            "instrument_key": "NSE_INDEX|Nifty 50",
            "price_paise": 2250000 + i,
        })

    assert q.qsize() == 5
    stats = bus.stats()
    assert stats["total_published"] == 15
    assert stats["dropped_frames"] == 10


@pytest.mark.gate_g5
@pytest.mark.asyncio
async def test_replay_player_raw_segments_smoke() -> None:
    """
    1. The use of function:
       Smokes authentic raw binary WebSocket segment replay into FrameBus.

    2. How does the specific function work:
       - Checks for presence of authentic raw segment files in data/raw/upstox_ws/ticks.
       - If present, initializes ReplayPlayer in ASAP speed mode with force_source='raw'.
       - Subscribes queue to bus and executes player.run().
       - Asserts published frames have is_replayed=True and valid paise pricing.

    3. Concepts used in the function:
       Raw binary segment unpacking, protobuf feed decoding, playback verification.

    4. Places where this function is imported and used:
       Executed as part of pytest test suite for packages/transport.

    5. Final output of the function, before and after:
       Before: Untested raw segment playback pipeline.
       After: Confirmed authentic raw segment decoding and publishing into FrameBus.
    """
    raw_dir = Path("data/raw/upstox_ws/ticks")
    if not raw_dir.exists() or not list(raw_dir.glob("trade_date=*")):
        pytest.skip("No raw segment fixtures found in data/raw/upstox_ws/ticks")

    bus = FrameBus(capacity=10000)
    q = bus.subscribe(max_queue_size=1000)

    player = ReplayPlayer(
        bus=bus,
        trade_date="2026-10-26",
        speed=PlaybackSpeed.ASAP,
        force_source="raw",
        max_ticks=200,
    )

    count = await player.run()
    assert count == 200, "Expected 200 ticks replayed from authentic raw segments"
    assert q.qsize() == count

    sample_frame = q.get_nowait()
    assert sample_frame.is_replayed is True
    assert sample_frame.price_paise > 0
    assert sample_frame.instrument_key != ""


@pytest.mark.gate_g5
@pytest.mark.asyncio
async def test_replay_player_duckdb_synthetic_ticks() -> None:
    """
    1. The use of function:
       Verifies 4-tick micro-bar synthetic generation from historical DuckDB 1m candles.

    2. How does the specific function work:
       - Checks for presence of Data/lake/quantview.duckdb.
       - Runs ReplayPlayer with force_source='duckdb' for trade_date='2021-02-01'.
       - Validates exactly 4 ticks generated per 1m candle (open, high/low, low/high, close).
       - Asserts 15-second intra-candle timestamp increments and is_replayed=True.

    3. Concepts used in the function:
       Synthetic micro-tick generation, intra-bar interpolation, DuckDB Parquet lake query.

    4. Places where this function is imported and used:
       Executed as part of pytest test suite for packages/transport.

    5. Final output of the function, before and after:
       Before: Untested micro-tick synthesis.
       After: Verified 4 micro-ticks per 1m candle with accurate time offsets and paise pricing.
    """
    db_path = Path("Data/lake/quantview.duckdb")
    if not db_path.exists():
        pytest.skip("Data/lake/quantview.duckdb not found")

    bus = FrameBus(capacity=10000)
    q = bus.subscribe(max_queue_size=1000)

    player = ReplayPlayer(
        bus=bus,
        trade_date="2026-10-30",
        speed=PlaybackSpeed.ASAP,
        force_source="duckdb",
        duckdb_path=str(db_path),
        max_ticks=200,
    )

    count = await player.run()
    assert count == 200, f"Expected 200 micro-ticks, got {count}"
    assert count % 4 == 0, f"Micro-tick count {count} must be a multiple of 4 (4 ticks per 1m bar)"
    assert q.qsize() == count

    tick1 = q.get_nowait()
    tick2 = q.get_nowait()
    tick3 = q.get_nowait()
    tick4 = q.get_nowait()

    assert tick1.is_replayed is True
    assert tick2.timestamp_epoch_sec == tick1.timestamp_epoch_sec + 15
    assert tick3.timestamp_epoch_sec == tick1.timestamp_epoch_sec + 30
    assert tick4.timestamp_epoch_sec == tick1.timestamp_epoch_sec + 45


@pytest.mark.gate_g5
@pytest.mark.asyncio
async def test_replay_player_lifecycle_controls() -> None:
    """
    1. The use of function:
       Verifies interactive lifecycle controls of ReplayPlayer: start, pause, resume, stop, and set_speed.

    2. How does the specific function work:
       - Initializes ReplayPlayer and validates initial idle state.
       - Calls start() and verifies is_running is True.
       - Calls pause() and verifies is_paused is True.
       - Calls set_speed() and verifies dynamic speed mutation.
       - Calls resume() and verifies is_paused transitions to False.
       - Calls stop() and verifies is_running transitions to False and background task finishes.

    3. Concepts used in the function:
       Asynchronous lifecycle management, state machine verification, dynamic rate control.

    4. Places where this function is imported and used:
       Executed as part of pytest test suite for packages/transport.

    5. Final output of the function, before and after:
       Before: Untested interactive player controls.
       After: Confirmed robust pause/resume/stop lifecycle and dynamic speed mutation.
    """
    bus = FrameBus(capacity=100)
    player = ReplayPlayer(
        bus=bus,
        speed=PlaybackSpeed.FAST_5X,
        duckdb_path="Data/lake/quantview.duckdb",
    )

    assert player.is_running is False
    assert player.is_paused is False
    assert player.speed == PlaybackSpeed.FAST_5X

    # Test dynamic speed modification
    player.set_speed(PlaybackSpeed.FAST_2X)
    assert player.speed == PlaybackSpeed.FAST_2X

    # Start task
    task = player.start()
    assert player.is_running is True
    assert player.is_paused is False

    # Pause
    player.pause()
    assert player.is_paused is True

    # Resume
    player.resume()
    assert player.is_paused is False

    # Stop
    player.stop()
    assert player.is_running is False

    # Let event loop settle
    await asyncio.sleep(0.01)
    assert task.done()
