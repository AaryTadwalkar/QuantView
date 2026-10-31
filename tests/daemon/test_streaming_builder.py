"""
1. What this file does:
   Comprehensive test suite for the QuantView Stage 7 streaming candle builder (Milestone M7-02).
   Verifies real-time 1m bar assembly, intrabar provisional emissions, boundary clock finalizations,
   causal availability timestamps (ADR-008/ADR-041), Indian market session filtering (09:15-15:30 IST),
   late-tick quarantine handling, multi-timeframe 5m rollups (ADR-005), and FrameBus streaming integration.

2. Overall design:
   Enforces strict Release Gate G5 criteria:
     - Correct OHLCV and tick count assembly across multi-tick sequences.
     - Intrabar provisional event emission (is_closed=False).
     - Minute boundary crossing finalization (is_closed=True).
     - Causal availability enforcement: finalized_at = bar_end + grace_period.
     - Out-of-session tick rejection (before 09:15:00 and after 15:30:00 IST).
     - Late-tick quarantine (> 1.5s delay into already-finalized bars) without mutating history.
     - Exact bit-for-bit OHLC match between 5-minute candle and its five constituent 1-minute bars.
     - Boundary clock auto-finalization on paused/illiquid feeds.
     - Thread-safe multi-instrument isolation.
     - FrameBus end-to-end pub/sub consumption.

3. Elements in the file:
   - make_tick: Factory helper constructing canonical TickFrame instances for given IST coordinates.
   - test_1m_bar_assembly_from_tick_sequence: Asserts correct OHLCV calculation across 1m bars.
   - test_provisional_candle_emission_intrabar: Validates intrabar provisional candle updates.
   - test_finalized_event_emission_on_boundary: Validates bar finalization upon minute boundary crossing.
   - test_causal_availability_rule: Validates finalized_at = bar_end + grace_period.
   - test_rejection_of_ticks_outside_session_boundaries: Asserts rejection of ticks outside 09:15-15:30 IST.
   - test_late_tick_quarantine_handling: Verifies quarantine of ticks arriving into closed bars.
   - test_5_minute_candle_ohlc_match_constituent_1m_bars: Proves 5m candle matches 5 constituent 1m bars.
   - test_boundary_clock_force_finalization: Asserts boundary clocks close expired bars without ticks.
   - test_multi_instrument_state_isolation: Asserts isolated aggregation across multiple instruments.
   - test_callback_registration_and_async_dispatch: Validates async callback notification.
   - test_framebus_streaming_consumer_integration: Tests end-to-end FrameBus consumption.

4. Final output of the file:
   Automated pass/fail verification for Milestone M7-02 under Gate G5.
"""

import asyncio
from datetime import datetime, timezone
from typing import List
from zoneinfo import ZoneInfo

import pytest

from packages.market_data.streaming_builder import (
    StreamingCandle,
    StreamingCandleBuilder,
)
from packages.transport.frame_bus import FrameBus, TickFrame

IST_TZ = ZoneInfo("Asia/Kolkata")
UTC_TZ = timezone.utc
BASE_DATE = "2026-10-30"  # Friday (valid market session day)


def make_tick(
    ist_time_str: str,
    price_paise: int,
    volume: int = 1,
    instrument_key: str = "NSE_INDEX|Nifty 50",
    sequence_id: int = 1,
) -> TickFrame:
    """
    1. The use of function:
       Test factory helper constructing a canonical TickFrame from an IST time string and paise price.

    2. How does the specific function work:
       Combines BASE_DATE with ist_time_str, parses into Asia/Kolkata datetime, extracts UTC epoch seconds,
       and builds an immutable TickFrame instance.

    3. Concepts used in the function:
       Deterministic test data synthesis, timezone projection.

    4. Places where this function is imported and used:
       Used throughout test_streaming_builder.py to synthesize deterministic test ticks.

    5. Final output of the function, before and after:
       Before: String time and price paise. After: Canonical immutable TickFrame instance.
    """
    dt_ist = datetime.fromisoformat(f"{BASE_DATE}T{ist_time_str}+05:30")
    epoch_sec = int(dt_ist.astimezone(UTC_TZ).timestamp())
    iso_str = dt_ist.astimezone(UTC_TZ).isoformat()
    return TickFrame(
        sequence_id=sequence_id,
        instrument_key=instrument_key,
        timestamp_epoch_sec=epoch_sec,
        timestamp_iso=iso_str,
        price_paise=price_paise,
        volume=volume,
    )


@pytest.mark.gate_g5
def test_1m_bar_assembly_from_tick_sequence() -> None:
    """
    1. The use of function:
       Verifies 1-minute candlestick assembly from a realistic sequence of intrabar ticks.

    2. How does the specific function work:
       - Instantiates StreamingCandleBuilder with '1m' timeframe.
       - Ingests four ticks within 09:15:00 to 09:15:59 IST with varying prices and volumes.
       - Ingests a fifth tick at 09:16:05 IST crossing the minute boundary.
       - Asserts finalized candle OHLCV matches constituent ticks exactly.

    3. Concepts used in the function:
       OHLC aggregation, boundary finalization, volume accumulation.

    4. Places where this function is imported and used:
       Invoked by pytest runner under gate_g5 test suite.

    5. Final output of the function, before and after:
       Before: Raw ticks. After: Verified finalized 1m candle matching expected Open, High, Low, Close, Volume.
    """
    builder = StreamingCandleBuilder(timeframes=["1m"], grace_period_sec=0.5)

    # Sequence of 4 ticks in 09:15 bar
    t1 = make_tick("09:15:05", price_paise=2400000, volume=10, sequence_id=1)
    t2 = make_tick("09:15:20", price_paise=2405000, volume=15, sequence_id=2)
    t3 = make_tick("09:15:40", price_paise=2395000, volume=20, sequence_id=3)
    t4 = make_tick("09:15:55", price_paise=2402000, volume=25, sequence_id=4)

    builder.on_tick(t1)
    builder.on_tick(t2)
    builder.on_tick(t3)
    builder.on_tick(t4)

    # Tick crossing into 09:16 bar
    t5 = make_tick("09:16:05", price_paise=2403000, volume=5, sequence_id=5)
    emitted = builder.on_tick(t5)

    assert len(emitted) == 2, f"Expected 2 candles (1 finalized, 1 provisional), got {len(emitted)}"

    finalized_bar, provisional_bar = emitted[0], emitted[1]

    # Verify finalized 09:15 bar
    assert finalized_bar.is_closed is True
    assert finalized_bar.timeframe == "1m"
    assert finalized_bar.open_paise == 2400000
    assert finalized_bar.high_paise == 2405000
    assert finalized_bar.low_paise == 2395000
    assert finalized_bar.close_paise == 2402000
    assert finalized_bar.volume == 70  # 10 + 15 + 20 + 25
    assert finalized_bar.tick_count == 4
    assert finalized_bar.bar_end_epoch_sec - finalized_bar.bar_start_epoch_sec == 60
    assert finalized_bar.finalized_at_epoch_sec == finalized_bar.bar_end_epoch_sec + 0.5

    # Verify new active provisional 09:16 bar
    assert provisional_bar.is_closed is False
    assert provisional_bar.timeframe == "1m"
    assert provisional_bar.open_paise == 2403000
    assert provisional_bar.high_paise == 2403000
    assert provisional_bar.low_paise == 2403000
    assert provisional_bar.close_paise == 2403000
    assert provisional_bar.volume == 5
    assert provisional_bar.tick_count == 1
    assert provisional_bar.finalized_at_epoch_sec is None


@pytest.mark.gate_g5
def test_provisional_candle_emission_intrabar() -> None:
    """
    1. The use of function:
       Tests real-time provisional candle emission on every intrabar tick before boundary close.

    2. How does the specific function work:
       - Sends 3 ticks sequentially within the same minute.
       - Asserts that every tick returns an updated provisional candle with is_closed=False.
       - Validates running High, Low, Close, Volume, and Tick Count.

    3. Concepts used in the function:
       Intrabar streaming updates, provisional event emission.

    4. Places where this function is imported and used:
       Invoked by pytest runner under gate_g5 test suite.

    5. Final output of the function, before and after:
       Before: Raw ticks. After: Asserted incremental OHLCV updates on provisional candles.
    """
    builder = StreamingCandleBuilder(timeframes=["1m"])

    # First tick
    t1 = make_tick("09:15:10", price_paise=2400000, volume=10)
    c1 = builder.on_tick(t1)
    assert len(c1) == 1
    assert c1[0].is_closed is False
    assert c1[0].open_paise == 2400000
    assert c1[0].high_paise == 2400000
    assert c1[0].low_paise == 2400000
    assert c1[0].close_paise == 2400000
    assert c1[0].volume == 10
    assert c1[0].tick_count == 1
    assert c1[0].finalized_at_epoch_sec is None

    # Second tick sets new high
    t2 = make_tick("09:15:25", price_paise=2410000, volume=15)
    c2 = builder.on_tick(t2)
    assert len(c2) == 1
    assert c2[0].is_closed is False
    assert c2[0].open_paise == 2400000
    assert c2[0].high_paise == 2410000
    assert c2[0].low_paise == 2400000
    assert c2[0].close_paise == 2410000
    assert c2[0].volume == 25
    assert c2[0].tick_count == 2

    # Third tick sets new low and updates close
    t3 = make_tick("09:15:45", price_paise=2395000, volume=20)
    c3 = builder.on_tick(t3)
    assert len(c3) == 1
    assert c3[0].is_closed is False
    assert c3[0].open_paise == 2400000
    assert c3[0].high_paise == 2410000
    assert c3[0].low_paise == 2395000
    assert c3[0].close_paise == 2395000
    assert c3[0].volume == 45
    assert c3[0].tick_count == 3


@pytest.mark.gate_g5
def test_finalized_event_emission_on_boundary() -> None:
    """
    1. The use of function:
       Validates that crossing a minute boundary triggers immediate bar finalization.

    2. How does the specific function work:
       - Sends tick at 09:15:30 IST.
       - Sends boundary-crossing tick at 09:16:00 IST.
       - Verifies that the previous bar is finalized and closed while the new bar opens.

    3. Concepts used in the function:
       Bar boundary crossing, discrete event scheduling.

    4. Places where this function is imported and used:
       Invoked by pytest runner under gate_g5 test suite.

    5. Final output of the function, before and after:
       Before: Boundary tick. After: Emitted finalized bar followed by active provisional bar.
    """
    builder = StreamingCandleBuilder(timeframes=["1m"], grace_period_sec=0.5)

    builder.on_tick(make_tick("09:15:30", price_paise=2400000, volume=50))
    emitted = builder.on_tick(make_tick("09:16:00", price_paise=2401000, volume=30))

    assert len(emitted) == 2
    finalized = emitted[0]
    provisional = emitted[1]

    assert finalized.is_closed is True
    assert finalized.volume == 50
    assert finalized.finalized_at_epoch_sec == finalized.bar_end_epoch_sec + 0.5

    assert provisional.is_closed is False
    assert provisional.volume == 30
    assert provisional.open_paise == 2401000


@pytest.mark.gate_g5
def test_causal_availability_rule() -> None:
    """
    1. The use of function:
       Enforces causal availability rule: finalized_at = bar_end + grace_period per ADR-008.

    2. How does the specific function work:
       - Tests default grace period (0.5s), custom positive grace period (1.25s), and zero grace period.
       - Asserts that finalized_at_epoch_sec matches bar_end + grace_period exactly in all cases.
       - Asserts that provisional bars have finalized_at_epoch_sec as None.

    3. Concepts used in the function:
       ADR-008 causal availability, no look-ahead prevention.

    4. Places where this function is imported and used:
       Invoked by pytest runner under gate_g5 test suite.

    5. Final output of the function, before and after:
       Before: Raw bar close. After: Strictly verified causal availability timestamp calculations.
    """
    for gp in [0.5, 1.25, 0.0]:
        builder = StreamingCandleBuilder(timeframes=["1m"], grace_period_sec=gp)
        builder.on_tick(make_tick("09:15:10", price_paise=2400000, volume=10))
        emitted = builder.on_tick(make_tick("09:16:05", price_paise=2405000, volume=10))

        finalized = emitted[0]
        assert finalized.is_closed is True
        expected_finalized_at = finalized.bar_end_epoch_sec + gp
        assert finalized.finalized_at_epoch_sec == expected_finalized_at
        assert finalized.finalized_at == expected_finalized_at

        # Verify provisional bar has None
        provisional = emitted[1]
        assert provisional.is_closed is False
        assert provisional.finalized_at_epoch_sec is None
        assert provisional.finalized_at is None


@pytest.mark.gate_g5
def test_rejection_of_ticks_outside_session_boundaries() -> None:
    """
    1. The use of function:
       Verifies strict rejection of market ticks arriving outside 09:15:00 to 15:30:00 IST.

    2. How does the specific function work:
       - Ingests pre-market tick (08:30:00 IST) and boundary edge tick (09:14:59 IST).
       - Ingests post-market ticks (15:30:01 IST and 16:00:00 IST).
       - Ingests valid ticks at exact market open (09:15:00 IST) and market close (15:30:00 IST).
       - Asserts all outside ticks are rejected with OUT_OF_SESSION reason and valid ticks accepted.

    3. Concepts used in the function:
       Exchange session boundary enforcement, out-of-session quarantine.

    4. Places where this function is imported and used:
       Invoked by pytest runner under gate_g5 test suite.

    5. Final output of the function, before and after:
       Before: Ticks with varying session times. After: Rejection of off-market ticks, acceptance of in-session ticks.
    """
    builder = StreamingCandleBuilder(timeframes=["1m"])

    # Pre-market ticks: must be rejected
    res1 = builder.on_tick(make_tick("08:30:00", price_paise=2400000))
    assert res1 == []
    res2 = builder.on_tick(make_tick("09:14:59", price_paise=2400000))
    assert res2 == []

    # Post-market ticks: must be rejected
    res3 = builder.on_tick(make_tick("15:30:01", price_paise=2400000))
    assert res3 == []
    res4 = builder.on_tick(make_tick("16:00:00", price_paise=2400000))
    assert res4 == []

    # Assert 4 ticks were quarantined as OUT_OF_SESSION
    assert builder.quarantined_count == 4
    quarantined = builder.get_quarantined_ticks()
    assert all(q.reason == "OUT_OF_SESSION" for q in quarantined)

    # Valid session boundary ticks: must be accepted
    res_open = builder.on_tick(make_tick("09:15:00", price_paise=2400000))
    assert len(res_open) == 1
    assert res_open[0].is_closed is False

    # Force flush open bar and verify exact close boundary tick
    builder.flush()
    res_close = builder.on_tick(make_tick("15:30:00", price_paise=2402000))
    assert len(res_close) == 1
    assert res_close[0].is_closed is False


@pytest.mark.gate_g5
def test_late_tick_quarantine_handling() -> None:
    """
    1. The use of function:
       Tests late-tick quarantine handling (> 1.5s delay) for ticks arriving into already-finalized bars.

    2. How does the specific function work:
       - Builds and finalizes 09:15:00 bar using a tick arriving at 09:16:02.
       - Sends a late tick with timestamp 09:15:58 (delayed by 4 seconds > 1.5s).
       - Asserts that late tick is dropped without mutating the finalized bar.
       - Asserts that quarantine telemetry logs reason 'LATE_QUARANTINED'.

    3. Concepts used in the function:
       Late-tick quarantine, immutable historical bars, temporal causal integrity.

    4. Places where this function is imported and used:
       Invoked by pytest runner under gate_g5 test suite.

    5. Final output of the function, before and after:
       Before: Late tick into closed bar. After: Late tick quarantined, closed bar untouched.
    """
    builder = StreamingCandleBuilder(timeframes=["1m"], grace_period_sec=0.5)

    # Build 09:15 bar
    builder.on_tick(make_tick("09:15:10", price_paise=2400000, volume=10))
    builder.on_tick(make_tick("09:15:50", price_paise=2405000, volume=20))

    # Boundary crossing tick at 09:16:02 finalizes 09:15 bar
    emitted = builder.on_tick(make_tick("09:16:02", price_paise=2402000, volume=15))
    finalized_0915 = emitted[0]
    assert finalized_0915.is_closed is True
    assert finalized_0915.volume == 30
    assert finalized_0915.close_paise == 2405000

    # Now a late tick arrives with timestamp 09:15:58 (delayed by 4 seconds into closed bar)
    late_tick = make_tick("09:15:58", price_paise=2415000, volume=500)
    result = builder.on_tick(late_tick)

    # Must be dropped
    assert result == []
    assert builder.late_quarantined_count == 1

    quarantined = builder.get_quarantined_ticks()
    assert len(quarantined) == 1
    assert quarantined[0].reason == "LATE_QUARANTINED"
    assert quarantined[0].tick.price_paise == 2415000

    # Verify finalized bar was NOT modified
    latest_finalized = builder.get_latest_finalized_candle("NSE_INDEX|Nifty 50", "1m")
    assert latest_finalized is not None
    assert latest_finalized.volume == 30  # Still 30, not 530
    assert latest_finalized.close_paise == 2405000  # Still 2405000, not 2415000


@pytest.mark.gate_g5
def test_5_minute_candle_ohlc_match_constituent_1m_bars() -> None:
    """
    1. The use of function:
       Validates ADR-005 hierarchical multi-timeframe rollup: 5m candle matches 5 constituent 1m bars.

    2. How does the specific function work:
       - Configures builder with timeframes=['1m', '5m'].
       - Feeds ticks across all five 1m bars of the 09:15:00 to 09:20:00 window.
       - Closes window with a tick at 09:20:01.
       - Collects the 5 finalized 1m bars and the finalized 5m bar.
       - Compares Open, High, Low, Close, Volume, and Tick Count bit-for-bit.

    3. Concepts used in the function:
       ADR-005 multi-timeframe hierarchy, constituent aggregation.

    4. Places where this function is imported and used:
       Invoked by pytest runner under gate_g5 test suite.

    5. Final output of the function, before and after:
       Before: Five 1m bars. After: Asserted exact equivalence between 5m bar and five 1m bars.
    """
    builder = StreamingCandleBuilder(timeframes=["1m", "5m"], grace_period_sec=0.5)

    finalized_1m_bars: List[StreamingCandle] = []
    finalized_5m_bars: List[StreamingCandle] = []

    def on_candle(c: StreamingCandle) -> None:
        """
        1. The use of function:
           Test callback capturing emitted candles partitioned by timeframe.

        2. How does the specific function work:
           Appends finalized candles into finalized_1m_bars or finalized_5m_bars lists.

        3. Concepts used in the function:
           Callback test probe, partitioned accumulator.

        4. Places where this function is imported and used:
           Used locally within test_5_minute_candle_ohlc_match_constituent_1m_bars.

        5. Final output of the function, before and after:
           Before: Unrecorded candle. After: Candle appended to corresponding test list.
        """
        if c.is_closed:
            if c.timeframe == "1m":
                finalized_1m_bars.append(c)
            elif c.timeframe == "5m":
                finalized_5m_bars.append(c)

    builder.register_candle_callback(on_candle)

    # Minute 1 (09:15)
    builder.on_tick(make_tick("09:15:05", price_paise=2400000, volume=20))
    builder.on_tick(make_tick("09:15:40", price_paise=2405000, volume=30))

    # Minute 2 (09:16)
    builder.on_tick(make_tick("09:16:10", price_paise=2408000, volume=25))
    builder.on_tick(make_tick("09:16:50", price_paise=2412000, volume=35))

    # Minute 3 (09:17)
    builder.on_tick(make_tick("09:17:15", price_paise=2395000, volume=40))
    builder.on_tick(make_tick("09:17:45", price_paise=2398000, volume=10))

    # Minute 4 (09:18)
    builder.on_tick(make_tick("09:18:20", price_paise=2399000, volume=15))
    builder.on_tick(make_tick("09:18:55", price_paise=2402000, volume=25))

    # Minute 5 (09:19)
    builder.on_tick(make_tick("09:19:10", price_paise=2401000, volume=50))
    builder.on_tick(make_tick("09:19:50", price_paise=2404000, volume=30))

    # Boundary crossing tick at 09:20:05: finalizes Minute 5 and the 5m bar!
    builder.on_tick(make_tick("09:20:05", price_paise=2406000, volume=10))

    assert len(finalized_1m_bars) == 5, f"Expected 5 finalized 1m bars, got {len(finalized_1m_bars)}"
    assert len(finalized_5m_bars) == 1, f"Expected 1 finalized 5m bar, got {len(finalized_5m_bars)}"

    bar_5m = finalized_5m_bars[0]

    # Verify OHLCV match against constituent 1m bars
    expected_open = finalized_1m_bars[0].open_paise
    expected_high = max(b.high_paise for b in finalized_1m_bars)
    expected_low = min(b.low_paise for b in finalized_1m_bars)
    expected_close = finalized_1m_bars[-1].close_paise
    expected_vol = sum(b.volume for b in finalized_1m_bars)
    expected_count = sum(b.tick_count for b in finalized_1m_bars)

    assert bar_5m.open_paise == expected_open == 2400000
    assert bar_5m.high_paise == expected_high == 2412000
    assert bar_5m.low_paise == expected_low == 2395000
    assert bar_5m.close_paise == expected_close == 2404000
    assert bar_5m.volume == expected_vol == 280
    assert bar_5m.tick_count == expected_count == 10
    assert bar_5m.bar_end_epoch_sec - bar_5m.bar_start_epoch_sec == 300
    assert bar_5m.finalized_at_epoch_sec == bar_5m.bar_end_epoch_sec + 0.5


@pytest.mark.gate_g5
def test_boundary_clock_force_finalization() -> None:
    """
    1. The use of function:
       Tests boundary clock auto-finalization when feed pauses and no boundary tick arrives.

    2. How does the specific function work:
       - Sends tick in 09:15 bar.
       - Advances boundary clock past bar_end + grace_period without any new ticks.
       - Verifies that check_boundary_clock() finalizes the open bar cleanly.

    3. Concepts used in the function:
       Boundary clock timeout, zero-latency bar closure without tick dependency.

    4. Places where this function is imported and used:
       Invoked by pytest runner under gate_g5 test suite.

    5. Final output of the function, before and after:
       Before: Stale open bar. After: Closed finalized bar emitted by clock trigger.
    """
    builder = StreamingCandleBuilder(timeframes=["1m"], grace_period_sec=0.5)

    builder.on_tick(make_tick("09:15:10", price_paise=2400000, volume=10))

    active = builder.get_active_candle("NSE_INDEX|Nifty 50", "1m")
    assert active is not None
    assert active.is_closed is False

    # Simulate boundary clock firing at 09:16:01 (past 09:16:00.5 threshold)
    dt_clock = datetime.fromisoformat(f"{BASE_DATE}T09:16:01+05:30")
    clock_epoch = int(dt_clock.astimezone(UTC_TZ).timestamp())

    finalized = builder.check_boundary_clock(current_epoch_sec=clock_epoch)
    assert len(finalized) == 1
    assert finalized[0].is_closed is True
    assert finalized[0].open_paise == 2400000

    # Active bar is now None
    assert builder.get_active_candle("NSE_INDEX|Nifty 50", "1m") is None


@pytest.mark.gate_g5
def test_multi_instrument_state_isolation() -> None:
    """
    1. The use of function:
       Validates complete state isolation across multiple instruments building concurrently.

    2. How does the specific function work:
       - Interleaves ticks for 'NSE_INDEX|Nifty 50' and 'NSE_INDEX|Nifty Bank'.
       - Finalizes Nifty 50 bar while Bank Nifty remains in its minute.
       - Verifies both instruments assemble candles independently without cross-talk.

    3. Concepts used in the function:
       Multi-instrument partitioning, concurrent state isolation.

    4. Places where this function is imported and used:
       Invoked by pytest runner under gate_g5 test suite.

    5. Final output of the function, before and after:
       Before: Interleaved ticks. After: Independent candles assembled per instrument.
    """
    builder = StreamingCandleBuilder(timeframes=["1m"])

    # Tick 1 for NIFTY
    builder.on_tick(make_tick("09:15:10", price_paise=2400000, volume=10, instrument_key="NSE_INDEX|Nifty 50"))
    # Tick 1 for BANKNIFTY
    builder.on_tick(make_tick("09:15:15", price_paise=5200000, volume=20, instrument_key="NSE_INDEX|Nifty Bank"))

    # Tick 2 for NIFTY crossing boundary
    emitted_nifty = builder.on_tick(
        make_tick("09:16:05", price_paise=2405000, volume=5, instrument_key="NSE_INDEX|Nifty 50")
    )

    # NIFTY should have 1 finalized bar and 1 provisional bar
    assert len(emitted_nifty) == 2
    assert emitted_nifty[0].instrument_key == "NSE_INDEX|Nifty 50"
    assert emitted_nifty[0].is_closed is True

    # BANKNIFTY should still be in active bar
    bn_active = builder.get_active_candle("NSE_INDEX|Nifty Bank", "1m")
    assert bn_active is not None
    assert bn_active.is_closed is False
    assert bn_active.open_paise == 5200000
    assert bn_active.volume == 20


@pytest.mark.asyncio
@pytest.mark.gate_g5
async def test_callback_registration_and_async_dispatch() -> None:
    """
    1. The use of function:
       Validates asynchronous callback registration and invocation via on_tick_async().

    2. How does the specific function work:
       - Registers an async callback recording received candles.
       - Feeds ticks via on_tick_async().
       - Asserts callback received both provisional and finalized events in exact order.

    3. Concepts used in the function:
       Async callback hooks, awaitable event dispatch.

    4. Places where this function is imported and used:
       Invoked by pytest runner under gate_g5 test suite.

    5. Final output of the function, before and after:
       Before: Async tick feed. After: Asserted delivery to async callback listener.
    """
    builder = StreamingCandleBuilder(timeframes=["1m"], grace_period_sec=0.5)
    received_candles: List[StreamingCandle] = []

    async def async_cb(c: StreamingCandle) -> None:
        """
        1. The use of function:
           Async callback recording received candles for async dispatch verification.

        2. How does the specific function work:
           Appends incoming StreamingCandle instance into received_candles list.

        3. Concepts used in the function:
           Async callback hook test probe.

        4. Places where this function is imported and used:
           Used locally within test_callback_registration_and_async_dispatch.

        5. Final output of the function, before and after:
           Before: Unrecorded candle. After: Candle appended to received_candles list.
        """
        received_candles.append(c)

    builder.register_candle_callback(async_cb)

    t1 = make_tick("09:15:10", price_paise=2400000, volume=10)
    await builder.on_tick_async(t1)

    assert len(received_candles) == 1
    assert received_candles[0].is_closed is False

    t2 = make_tick("09:16:02", price_paise=2405000, volume=15)
    await builder.on_tick_async(t2)

    assert len(received_candles) == 3  # prov1, finalized1, prov2
    assert received_candles[1].is_closed is True
    assert received_candles[2].is_closed is False


@pytest.mark.asyncio
@pytest.mark.gate_g5
async def test_framebus_streaming_consumer_integration() -> None:
    """
    1. The use of function:
       Tests end-to-end integration between FrameBus ring buffer publisher and StreamingCandleBuilder consumer.

    2. How does the specific function work:
       - Instantiates FrameBus and StreamingCandleBuilder.
       - Starts consumer background task via builder.start_consumer(frame_bus).
       - Publishes 3 ticks to FrameBus.
       - Verifies builder builds and finalizes candles asynchronously.
       - Gracefully stops consumer.

    3. Concepts used in the function:
       Message spine integration, producer-consumer queueing.

    4. Places where this function is imported and used:
       Invoked by pytest runner under gate_g5 test suite.

    5. Final output of the function, before and after:
       Before: Unconnected modules. After: Verified live stream consumption across FrameBus.
    """
    bus = FrameBus(capacity=1024)
    builder = StreamingCandleBuilder(timeframes=["1m"], grace_period_sec=0.5)

    received: List[StreamingCandle] = []
    def on_received(c: StreamingCandle) -> None:
        """
        1. The use of function:
           Test callback capturing emitted candles from consumer task.

        2. How does the specific function work:
           Appends incoming StreamingCandle instance into received list.

        3. Concepts used in the function:
           Consumer test probe.

        4. Places where this function is imported and used:
           Used locally within test_framebus_streaming_consumer_integration.

        5. Final output of the function, before and after:
           Before: Unrecorded candle. After: Candle appended to received list.
        """
        received.append(c)

    builder.register_candle_callback(on_received)

    consumer_task = await builder.start_consumer(bus, instrument_keys=["NSE_INDEX|Nifty 50"])

    try:
        t1 = make_tick("09:15:10", price_paise=2400000, volume=10)
        t2 = make_tick("09:15:30", price_paise=2405000, volume=20)
        t3 = make_tick("09:16:05", price_paise=2402000, volume=30)

        bus.publish(t1)
        bus.publish(t2)
        bus.publish(t3)

        # Allow consumer loop to drain queue
        for _ in range(50):
            if any(c.is_closed for c in received):
                break
            await asyncio.sleep(0.02)

        closed_bars = [c for c in received if c.is_closed]
        assert len(closed_bars) == 1
        assert closed_bars[0].volume == 30
        assert closed_bars[0].open_paise == 2400000
        assert closed_bars[0].close_paise == 2405000

    finally:
        await builder.stop_consumer()
        assert consumer_task.done()
