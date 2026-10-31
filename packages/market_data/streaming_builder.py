"""
1. What this file does:
   Implements the high-performance streaming candle builder (StreamingCandleBuilder) and canonical
   streaming candle data structure (StreamingCandle) for QuantView Stage 7 (Milestone M7-02).
   Aggregates discrete TickFrame events from the FrameBus transport into provisional (is_closed=False)
   and finalized (is_closed=True) 1-minute and multi-timeframe candlestick bars.

2. Overall design:
   Enforces causal temporal boundaries and Indian market trading hours per ADR-005, ADR-008, and ADR-041:
     - Exchange Session Boundaries: Validates timestamps against 09:15:00 to 15:30:00 IST. Ticks outside
       are discarded and recorded in quarantine telemetry.
     - 1-Minute State Machine: Maintains active mutable bar state per instrument key. Updates OHLCV on
       intrabar ticks and finalizes bar upon minute boundary crossing.
     - Causal Availability: Finalized bars carry finalized_at_epoch_sec = bar_end_epoch_sec + grace_period
       (default 0.5s per ADR-008/ADR-041).
     - Late-Tick Quarantine: Ticks with timestamps belonging to already-finalized bars are tagged as
       LATE_QUARANTINED and dropped without mutating historical candles.
     - Hierarchical Multi-Timeframe Rollup: Multi-timeframe aggregators (3m, 5m, 15m) roll up strictly from
       finalized 1m constituent bars per ADR-005, reflecting intrabar updates from the active 1m bar.
     - Dual Synchronous & Asynchronous Stream Interface: Supports synchronous on_tick() with background
       callback dispatching and async on_tick_async() / FrameBus consumer tasks.

3. Elements in the file:
   - DEFAULT_GRACE_PERIOD_SEC: Default grace period (0.5 seconds) before causal bar publication.
   - DEFAULT_TIMEFRAMES: Default timeframe set (('1m',)).
   - SESSION_OPEN_TIME: Regular trading session open boundary (09:15:00 IST).
   - SESSION_CLOSE_TIME: Regular trading session close boundary (15:30:00 IST).
   - IST_TIMEZONE: ZoneInfo instance for Asia/Kolkata (+05:30).
   - parse_timeframe_to_seconds: Helper converting string timeframes (e.g. '1m', '5m') to integer seconds.
   - compute_bar_start_epoch: Computes aligned bar start epoch seconds for any timeframe.
   - StreamingCandle: Canonical immutable dataclass representing streaming OHLCV candle events.
   - QuarantinedTick: Immutable audit container for rejected out-of-session or late ticks.
   - _Active1mBar: Mutable accumulator for active 1-minute bar building.
   - _InstrumentCandleState: Container tracking active 1m bar, finalized history, and multi-TF constituents.
   - StreamingCandleBuilder: Main aggregator class managing real-time candle assembly and callback dispatch.

4. Final output of the file:
   Exported StreamingCandle, StreamingCandleBuilder, and QuarantinedTick classes ready for deployment
   in the Live Broker Daemon and API gateway bridge.
"""

import asyncio
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from datetime import time as dt_time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Union
from zoneinfo import ZoneInfo

from packages.transport.frame_bus import FrameBus, TickFrame

DEFAULT_GRACE_PERIOD_SEC: float = 0.5
DEFAULT_TIMEFRAMES: Sequence[str] = ("1m",)
SESSION_OPEN_TIME: dt_time = dt_time(9, 15, 0)
SESSION_CLOSE_TIME: dt_time = dt_time(15, 30, 0)
IST_TIMEZONE: ZoneInfo = ZoneInfo("Asia/Kolkata")
UTC_TIMEZONE: timezone = timezone.utc


def parse_timeframe_to_seconds(timeframe: str) -> int:
    """
    1. The use of function:
       Converts standard timeframe string representations into duration in integer seconds.

    2. How does the specific function work:
       Strips whitespace, extracts numeric duration and unit suffix ('s', 'm', 'h', 'd'),
       and multiplies by appropriate unit scalar (1, 60, 3600, 86400).

    3. Concepts used in the function:
       String parsing, temporal unit normalization.

    4. Places where this function is imported and used:
       Imported by StreamingCandleBuilder, multi-timeframe aggregators, and unit tests.

    5. Final output of the function, before and after:
       Before: '1m', '5m', '1h'. After: 60, 300, 3600.
    """
    tf = timeframe.strip().lower()
    if tf.endswith("s"):
        return int(tf[:-1])
    elif tf.endswith("m"):
        return int(tf[:-1]) * 60
    elif tf.endswith("h"):
        return int(tf[:-1]) * 3600
    elif tf.endswith("d"):
        return int(tf[:-1]) * 86400
    raise ValueError(f"Unsupported timeframe format: '{timeframe}'")


def compute_bar_start_epoch(timestamp_epoch_sec: int, timeframe_sec: int) -> int:
    """
    1. The use of function:
       Calculates the canonical epoch start timestamp for a candlestick bar containing a given epoch.

    2. How does the specific function work:
       For timeframes <= 900s (1m, 3m, 5m, 15m), computes timestamp_epoch_sec - (timestamp_epoch_sec % timeframe_sec)
       which aligns with both UTC epoch seconds and 09:15:00 IST market open. For higher timeframes (> 900s),
       aligns relative to the trading day's 09:15:00 IST market open.

    3. Concepts used in the function:
       Bar boundary synchronization, modular temporal arithmetic.

    4. Places where this function is imported and used:
       Used by StreamingCandleBuilder to align 1-minute and multi-timeframe bar start boundaries.

    5. Final output of the function, before and after:
       Before: timestamp_epoch_sec=1793331915, timeframe_sec=60. After: 1793331900.
    """
    if timeframe_sec <= 900:
        return timestamp_epoch_sec - (timestamp_epoch_sec % timeframe_sec)

    # For timeframes > 15m (e.g. 30m, 1h), align relative to 09:15:00 IST open
    dt_ist = datetime.fromtimestamp(timestamp_epoch_sec, tz=UTC_TIMEZONE).astimezone(IST_TIMEZONE)
    session_open_dt = dt_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    session_open_epoch = int(session_open_dt.astimezone(UTC_TIMEZONE).timestamp())

    elapsed = timestamp_epoch_sec - session_open_epoch
    if elapsed >= 0:
        return session_open_epoch + (elapsed // timeframe_sec) * timeframe_sec
    else:
        return timestamp_epoch_sec - (timestamp_epoch_sec % timeframe_sec)


@dataclass(frozen=True)
class StreamingCandle:
    """
    1. The use of class:
       Immutable canonical data structure representing a streaming candlestick bar (provisional or finalized).

    2. What the class contains:
       - instrument_key: Unique identifier of the financial instrument (e.g. 'NSE_INDEX|Nifty 50').
       - timeframe: Timeframe interval string (e.g. '1m', '3m', '5m', '15m').
       - bar_start_epoch_sec: Bar start timestamp in UTC integer seconds.
       - bar_end_epoch_sec: Bar end timestamp in UTC integer seconds (e.g. bar_start + 60s).
       - open_paise: Opening traded price in integer paise.
       - high_paise: Highest traded price in integer paise.
       - low_paise: Lowest traded price in integer paise.
       - close_paise: Latest/closing traded price in integer paise.
       - volume: Accumulated traded volume over the bar.
       - tick_count: Total count of ticks aggregated within the bar.
       - is_closed: Boolean flag indicating if bar is finalized (True) or provisional (False).
       - finalized_at_epoch_sec: Timestamp when bar became causally available (bar_end + grace_period).

    3. Technologies used and why:
       Python dataclasses with frozen=True for immutability, thread safety, and low memory overhead.

    4. Key design and overall design of the class:
       Provides a unified, unambiguous contract for streaming charts, indicator engines, and paper broker
       execution without floating-point currency representation errors.
    """

    instrument_key: str
    timeframe: str
    bar_start_epoch_sec: int
    bar_end_epoch_sec: int
    open_paise: int
    high_paise: int
    low_paise: int
    close_paise: int
    volume: int
    tick_count: int
    is_closed: bool
    finalized_at_epoch_sec: Optional[Union[int, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Serializes the StreamingCandle instance into a JSON-compatible dictionary.

        2. How does the specific function work:
           Calls dataclasses.asdict to create a deep copy dictionary of all candle attributes.

        3. Concepts used in the function:
           Dataclass serialization, network transport mapping.

        4. Places where this function is imported and used:
           Used by WebSocket API bridges, REST responses, and message serializers.

        5. Final output of the function, before and after:
           Before: StreamingCandle instance. After: Dictionary containing all candle fields.
        """
        return asdict(self)

    @property
    def finalized_at(self) -> Optional[Union[int, float]]:
        """
        1. The use of function:
           Provides an alias property accessing the finalized_at causal availability timestamp.

        2. How does the specific function work:
           Returns the underlying finalized_at_epoch_sec attribute.

        3. Concepts used in the function:
           Property accessor, causal timestamp alias per ADR-008.

        4. Places where this function is imported and used:
           Accessed by strategy hosts, indicator engines, and test assertions.

        5. Final output of the function, before and after:
           Before: N/A. After: Float or integer epoch timestamp, or None if bar is provisional.
        """
        return self.finalized_at_epoch_sec

    @property
    def open_inr(self) -> float:
        """
        1. The use of function:
           Returns the opening price formatted as standard Rupee float.

        2. How does the specific function work:
           Divides open_paise by 100.0.

        3. Concepts used in the function:
           Currency decimal conversion.

        4. Places where this function is imported and used:
           Used by user interface bridges and human-readable loggers.

        5. Final output of the function, before and after:
           Before: N/A. After: Float representing price in INR.
        """
        return self.open_paise / 100.0

    @property
    def high_inr(self) -> float:
        """
        1. The use of function:
           Returns the high price formatted as standard Rupee float.

        2. How does the specific function work:
           Divides high_paise by 100.0.

        3. Concepts used in the function:
           Currency decimal conversion.

        4. Places where this function is imported and used:
           Used by user interface bridges and human-readable loggers.

        5. Final output of the function, before and after:
           Before: N/A. After: Float representing price in INR.
        """
        return self.high_paise / 100.0

    @property
    def low_inr(self) -> float:
        """
        1. The use of function:
           Returns the low price formatted as standard Rupee float.

        2. How does the specific function work:
           Divides low_paise by 100.0.

        3. Concepts used in the function:
           Currency decimal conversion.

        4. Places where this function is imported and used:
           Used by user interface bridges and human-readable loggers.

        5. Final output of the function, before and after:
           Before: N/A. After: Float representing price in INR.
        """
        return self.low_paise / 100.0

    @property
    def close_inr(self) -> float:
        """
        1. The use of function:
           Returns the closing price formatted as standard Rupee float.

        2. How does the specific function work:
           Divides close_paise by 100.0.

        3. Concepts used in the function:
           Currency decimal conversion.

        4. Places where this function is imported and used:
           Used by user interface bridges and human-readable loggers.

        5. Final output of the function, before and after:
           Before: N/A. After: Float representing price in INR.
        """
        return self.close_paise / 100.0


@dataclass(frozen=True)
class QuarantinedTick:
    """
    1. The use of class:
       Immutable audit container capturing details of a tick rejected due to boundary or latency violations.

    2. What the class contains:
       - tick: The rejected TickFrame instance.
       - reason: String explanation code (e.g. 'LATE_QUARANTINED', 'OUT_OF_SESSION').
       - quarantined_at_epoch_sec: Epoch seconds when quarantine was recorded.

    3. Technologies used and why:
       Python dataclasses with frozen=True for non-mutating forensic telemetry.

    4. Key design and overall design of the class:
       Maintains audit traceability of dropped ticks without distorting finalized historical candles.
    """

    tick: TickFrame
    reason: str
    quarantined_at_epoch_sec: float

    def to_dict(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Converts the QuarantinedTick into a serializable dictionary.

        2. How does the specific function work:
           Serializes tick via tick.to_dict() and nests within telemetry payload.

        3. Concepts used in the function:
           Dataclass serialization, audit telemetry.

        4. Places where this function is imported and used:
           Used by daemon diagnostic endpoints and telemetry monitors.

        5. Final output of the function, before and after:
           Before: QuarantinedTick instance. After: Dictionary containing rejected tick telemetry.
        """
        return {
            "tick": self.tick.to_dict(),
            "reason": self.reason,
            "quarantined_at_epoch_sec": self.quarantined_at_epoch_sec,
        }


class _Active1mBar:
    """
    1. The use of class:
       Internal mutable accumulator tracking the state of an active, incomplete 1-minute candlestick bar.

    2. What the class contains:
       - instrument_key: Unique identifier of the instrument.
       - bar_start_epoch_sec: Start epoch seconds of the 1-minute interval.
       - bar_end_epoch_sec: End epoch seconds of the 1-minute interval (start + 60s).
       - open_paise: Opening traded price in paise.
       - high_paise: Running high price in paise.
       - low_paise: Running low price in paise.
       - close_paise: Running latest price in paise.
       - volume: Accumulated bar volume.
       - tick_count: Running count of ticks.

    3. Technologies used and why:
       Standard Python mutable class for zero-allocation in-place arithmetic updates during tick bursts.

    4. Key design and overall design of the class:
       Separates high-frequency in-place mutation from immutable StreamingCandle output generation.
    """

    def __init__(
        self,
        instrument_key: str,
        bar_start_epoch_sec: int,
        bar_end_epoch_sec: int,
        open_paise: int,
        high_paise: int,
        low_paise: int,
        close_paise: int,
        volume: int,
        tick_count: int = 1,
    ) -> None:
        """
        1. The use of function:
           Initializes a new mutable _Active1mBar accumulator.

        2. How does the specific function work:
           Assigns initial OHLCV attributes from the first tick of the minute interval.

        3. Concepts used in the function:
           Accumulator initialization.

        4. Places where this function is imported and used:
           Instantiated by _InstrumentCandleState upon receiving the first tick of a new minute.

        5. Final output of the function, before and after:
           Before: N/A. After: Initialized _Active1mBar instance.
        """
        self.instrument_key = instrument_key
        self.bar_start_epoch_sec = bar_start_epoch_sec
        self.bar_end_epoch_sec = bar_end_epoch_sec
        self.open_paise = open_paise
        self.high_paise = high_paise
        self.low_paise = low_paise
        self.close_paise = close_paise
        self.volume = volume
        self.tick_count = tick_count

    def update(self, price_paise: int, vol: int) -> None:
        """
        1. The use of function:
           Updates running OHLCV metrics in-place with a new intrabar tick.

        2. How does the specific function work:
           Updates high_paise, low_paise, close_paise, increments volume, and increments tick_count.

        3. Concepts used in the function:
           Streaming aggregation, in-place arithmetic.

        4. Places where this function is imported and used:
           Called by StreamingCandleBuilder on each tick falling within the active bar interval.

        5. Final output of the function, before and after:
           Before: Previous OHLCV. After: Updated OHLCV reflecting new tick.
        """
        if price_paise > self.high_paise:
            self.high_paise = price_paise
        if price_paise < self.low_paise:
            self.low_paise = price_paise
        self.close_paise = price_paise
        self.volume += vol
        self.tick_count += 1

    def to_candle(
        self,
        is_closed: bool,
        finalized_at_epoch_sec: Optional[Union[int, float]] = None,
    ) -> StreamingCandle:
        """
        1. The use of function:
           Materializes an immutable StreamingCandle snapshot from the current accumulator state.

        2. How does the specific function work:
           Constructs and returns a StreamingCandle instance with current fields.

        3. Concepts used in the function:
           State snapshotting, immutability conversion.

        4. Places where this function is imported and used:
           Called to emit provisional candles and during bar finalization.

        5. Final output of the function, before and after:
           Before: Mutable _Active1mBar. After: Immutable StreamingCandle instance.
        """
        return StreamingCandle(
            instrument_key=self.instrument_key,
            timeframe="1m",
            bar_start_epoch_sec=self.bar_start_epoch_sec,
            bar_end_epoch_sec=self.bar_end_epoch_sec,
            open_paise=self.open_paise,
            high_paise=self.high_paise,
            low_paise=self.low_paise,
            close_paise=self.close_paise,
            volume=self.volume,
            tick_count=self.tick_count,
            is_closed=is_closed,
            finalized_at_epoch_sec=finalized_at_epoch_sec,
        )


class _InstrumentCandleState:
    """
    1. The use of class:
       Maintains full candlestick aggregation state for a single instrument key.

    2. What the class contains:
       - instrument_key: Unique identifier of the instrument.
       - active_1m: Optional _Active1mBar accumulator for currently building 1m bar.
       - last_finalized_1m_end: Epoch seconds of the latest finalized 1m bar end.
       - higher_tf_constituents: Dict mapping higher timeframe strings to lists of finalized 1m bars.
       - higher_tf_window_start: Dict mapping higher timeframe strings to current window start epoch.
       - higher_tf_window_end: Dict mapping higher timeframe strings to current window end epoch.
       - latest_finalized: Dict mapping timeframe strings to most recent finalized StreamingCandle.
       - quarantined_ticks: List of QuarantinedTick instances rejected for this instrument.

    3. Technologies used and why:
       Standard Python object mapping for encapsulated per-instrument lifecycle isolation.

    4. Key design and overall design of the class:
       Guarantees complete state isolation between multiple instruments (e.g. Nifty 50 vs Bank Nifty).
    """

    def __init__(self, instrument_key: str, higher_tfs: Sequence[str]) -> None:
        """
        1. The use of function:
           Initializes per-instrument candle aggregation state.

        2. How does the specific function work:
           Initializes dictionaries for higher timeframe constituents, window boundaries, and telemetry.

        3. Concepts used in the function:
           State initialization, multi-timeframe partition setup.

        4. Places where this function is imported and used:
           Instantiated by StreamingCandleBuilder upon first tick seen for an instrument key.

        5. Final output of the function, before and after:
           Before: N/A. After: Initialized _InstrumentCandleState instance.
        """
        self.instrument_key = instrument_key
        self.active_1m: Optional[_Active1mBar] = None
        self.last_finalized_1m_end: Optional[int] = None
        self.higher_tf_constituents: Dict[str, List[StreamingCandle]] = {tf: [] for tf in higher_tfs}
        self.higher_tf_window_start: Dict[str, Optional[int]] = {tf: None for tf in higher_tfs}
        self.higher_tf_window_end: Dict[str, Optional[int]] = {tf: None for tf in higher_tfs}
        self.latest_finalized: Dict[str, StreamingCandle] = {}
        self.quarantined_ticks: List[QuarantinedTick] = []

    def reset_higher_tf_window(self, tf: str) -> None:
        """
        1. The use of function:
           Resets constituent list and window boundary pointers for a specified higher timeframe.

        2. How does the specific function work:
           Clears constituent list and sets window start and end to None.

        3. Concepts used in the function:
           Window boundary lifecycle reset.

        4. Places where this function is imported and used:
           Called when a higher timeframe bar is finalized.

        5. Final output of the function, before and after:
           Before: Accumulated constituents and active window. After: Cleared constituents and None window.
        """
        self.higher_tf_constituents[tf] = []
        self.higher_tf_window_start[tf] = None
        self.higher_tf_window_end[tf] = None


class StreamingCandleBuilder:
    """
    1. The use of class:
       Real-time streaming candlestick aggregator assembling multi-timeframe bars from TickFrame streams.

    2. What the class contains:
       - _timeframes: List of configured timeframe interval strings to emit.
       - _higher_tfs: List of configured higher timeframes (excluding '1m').
       - _tf_seconds: Dict mapping timeframe strings to duration in integer seconds.
       - _grace_period_sec: Grace period duration in seconds before causal availability publication.
       - _enforce_session_boundaries: Boolean flag enabling/disabling 09:15-15:30 IST session validation.
       - market_open_time: Exchange session start time boundary (default 09:15:00 IST).
       - market_close_time: Exchange session close time boundary (default 15:30:00 IST).
       - _callbacks: Registered async and synchronous candle event listener callables.
       - _instruments: Dict mapping instrument keys to _InstrumentCandleState instances.
       - _global_quarantined: Audit log of all quarantined ticks across all instruments.
       - _consumer_task: Optional running asyncio.Task consuming from FrameBus.
       - _stop_requested: Flag coordinating graceful consumer task shutdown.

    3. Technologies used and why:
       Asyncio for high-performance non-blocking event dispatching and zoneinfo for IST session boundaries.

    4. Key design and overall design of the class:
       Acts as the authoritative bridge between transport ticks and downstream strategy hosts/charts.
       Enforces causal availability, Indian market boundaries, and late-tick quarantine with zero lookahead.
    """

    def __init__(
        self,
        timeframes: Optional[Sequence[str]] = None,
        grace_period_sec: float = DEFAULT_GRACE_PERIOD_SEC,
        enforce_session_boundaries: bool = True,
        market_open_time: dt_time = SESSION_OPEN_TIME,
        market_close_time: dt_time = SESSION_CLOSE_TIME,
    ) -> None:
        """
        1. The use of function:
           Constructs and initializes the StreamingCandleBuilder instance.

        2. How does the specific function work:
           Normalizes timeframes, calculates timeframe durations, stores session configuration,
           and initializes internal state tables and callback collections.

        3. Concepts used in the function:
           Builder initialization, timeframe normalization, session rule configuration.

        4. Places where this function is imported and used:
           Instantiated by live daemon supervisors, paper test harnesses, and gateway bridges.

        5. Final output of the function, before and after:
           Before: Uninitialized builder. After: Ready StreamingCandleBuilder instance.
        """
        raw_tfs = list(timeframes) if timeframes is not None else list(DEFAULT_TIMEFRAMES)
        # Ensure timeframes are unique and preserve order
        seen = set()
        deduped_tfs = []
        for tf in raw_tfs:
            normalized = tf.strip().lower()
            if normalized not in seen:
                seen.add(normalized)
                deduped_tfs.append(normalized)

        self._timeframes: List[str] = deduped_tfs
        self._tf_seconds: Dict[str, int] = {tf: parse_timeframe_to_seconds(tf) for tf in self._timeframes}
        # Ensure 1m duration is registered even if not explicitly in output timeframes
        if "1m" not in self._tf_seconds:
            self._tf_seconds["1m"] = 60

        # Higher timeframes sorted ascending by duration
        self._higher_tfs: List[str] = sorted(
            [tf for tf in self._timeframes if tf != "1m"],
            key=lambda tf: self._tf_seconds[tf],
        )

        self._grace_period_sec: float = grace_period_sec
        self._enforce_session_boundaries: bool = enforce_session_boundaries
        self.market_open_time: dt_time = market_open_time
        self.market_close_time: dt_time = market_close_time

        self._callbacks: List[Callable[[StreamingCandle], Union[Awaitable[None], None]]] = []
        self._instruments: Dict[str, _InstrumentCandleState] = {}
        self._global_quarantined: List[QuarantinedTick] = []

        self._consumer_task: Optional[asyncio.Task] = None
        self._stop_requested: bool = False

    @property
    def timeframes(self) -> List[str]:
        """
        1. The use of function:
           Returns the list of configured candlestick timeframes.

        2. How does the specific function work:
           Returns a copy of the _timeframes list.

        3. Concepts used in the function:
           Property accessor.

        4. Places where this function is imported and used:
           Inspected by test suites and configuration reporters.

        5. Final output of the function, before and after:
           Before: N/A. After: List of timeframe strings (e.g. ['1m', '5m']).
        """
        return list(self._timeframes)

    @property
    def grace_period_sec(self) -> float:
        """
        1. The use of function:
           Returns the configured causal grace period in seconds.

        2. How does the specific function work:
           Returns _grace_period_sec.

        3. Concepts used in the function:
           Property accessor.

        4. Places where this function is imported and used:
           Inspected by test assertions and daemon telemetry.

        5. Final output of the function, before and after:
           Before: N/A. After: Float representing grace period in seconds (e.g. 0.5).
        """
        return self._grace_period_sec

    @property
    def quarantined_count(self) -> int:
        """
        1. The use of function:
           Returns total number of rejected ticks across all instruments and reasons.

        2. How does the specific function work:
           Returns length of _global_quarantined list.

        3. Concepts used in the function:
           Telemetry metric property.

        4. Places where this function is imported and used:
           Queried by health checkers, diagnostic APIs, and test assertions.

        5. Final output of the function, before and after:
           Before: N/A. After: Integer total count of quarantined ticks.
        """
        return len(self._global_quarantined)

    @property
    def late_quarantined_count(self) -> int:
        """
        1. The use of function:
           Returns count of ticks specifically rejected due to late arrival into finalized bars.

        2. How does the specific function work:
           Counts entries in _global_quarantined with reason 'LATE_QUARANTINED'.

        3. Concepts used in the function:
           Filtered telemetry metric calculation.

        4. Places where this function is imported and used:
           Queried by test suites verifying ADR-008 late tick quarantine invariants.

        5. Final output of the function, before and after:
           Before: N/A. After: Integer count of late-quarantined ticks.
        """
        return sum(1 for q in self._global_quarantined if q.reason == "LATE_QUARANTINED")

    def register_candle_callback(
        self,
        cb: Callable[[StreamingCandle], Union[Awaitable[None], None]],
    ) -> None:
        """
        1. The use of function:
           Registers an asynchronous or synchronous callback function invoked whenever a candle is emitted.

        2. How does the specific function work:
           Appends the callback callable to the internal _callbacks list if not already present.

        3. Concepts used in the function:
           Observer pattern, pub/sub callback hook.

        4. Places where this function is imported and used:
           Called by live daemon subscribers, WebSocket push adapters, and strategy hosts.

        5. Final output of the function, before and after:
           Before: Previous callback list. After: Callback list containing new listener.
        """
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def unregister_candle_callback(
        self,
        cb: Callable[[StreamingCandle], Union[Awaitable[None], None]],
    ) -> None:
        """
        1. The use of function:
           Unregisters a previously attached candle event callback listener.

        2. How does the specific function work:
           Removes the callback from the internal _callbacks list if present.

        3. Concepts used in the function:
           Listener unsubscription, resource cleanup.

        4. Places where this function is imported and used:
           Called during subscriber teardown and test isolation teardowns.

        5. Final output of the function, before and after:
           Before: Callback attached. After: Callback removed.
        """
        if cb in self._callbacks:
            self._callbacks.remove(cb)

    def is_within_session(self, timestamp_epoch_sec: int) -> bool:
        """
        1. The use of function:
           Validates whether an epoch timestamp falls within Indian exchange trading hours (09:15 to 15:30 IST).

        2. How does the specific function work:
           Converts epoch to Asia/Kolkata datetime and verifies market_open_time <= time <= market_close_time.

        3. Concepts used in the function:
           Exchange calendar boundary validation, timezone projection.

        4. Places where this function is imported and used:
           Called on every ingested tick in on_tick() and test suites.

        5. Final output of the function, before and after:
           Before: Utc integer timestamp. After: True if within 09:15-15:30 IST, False otherwise.
        """
        dt_ist = datetime.fromtimestamp(timestamp_epoch_sec, tz=UTC_TIMEZONE).astimezone(IST_TIMEZONE)
        t = dt_ist.time()
        return self.market_open_time <= t <= self.market_close_time

    def on_tick(self, tick: TickFrame) -> List[StreamingCandle]:
        """
        1. The use of function:
           Primary synchronous entrypoint aggregating a single incoming TickFrame into streaming candles.

        2. How does the specific function work:
           - Validates exchange session boundaries; drops out-of-session ticks.
           - Checks for late arrival into already-finalized bars; quarantines late ticks.
           - If tick falls in active 1m bar: updates OHLCV and emits provisional candle(s).
           - If tick crosses minute boundary: finalizes active 1m bar, cascades rollup to higher TFs,
             initializes new active bar with tick as Open, and emits finalized then provisional candles.
           - Dispatches emitted candles to registered callbacks.

        3. Concepts used in the function:
           Real-time bar aggregation, causal finalization, multi-timeframe rollup, late-tick quarantine.

        4. Places where this function is imported and used:
           Called by consumer loops, replay players, and unit test suites.

        5. Final output of the function, before and after:
           Before: Ingested TickFrame. After: List of emitted StreamingCandle instances (finalized & provisional).
        """
        # 1. Exchange session boundary validation
        if self._enforce_session_boundaries and not self.is_within_session(tick.timestamp_epoch_sec):
            quarantined = QuarantinedTick(
                tick=tick,
                reason="OUT_OF_SESSION",
                quarantined_at_epoch_sec=time.time(),
            )
            state = self._get_or_create_state(tick.instrument_key)
            state.quarantined_ticks.append(quarantined)
            self._global_quarantined.append(quarantined)
            return []

        state = self._get_or_create_state(tick.instrument_key)

        # 2. Late-tick quarantine validation
        # Tick is late if its timestamp belongs to a 1m bar that has already been finalized
        if (state.last_finalized_1m_end is not None and tick.timestamp_epoch_sec < state.last_finalized_1m_end) or (
            state.active_1m is not None and tick.timestamp_epoch_sec < state.active_1m.bar_start_epoch_sec
        ):
            quarantined = QuarantinedTick(
                tick=tick,
                reason="LATE_QUARANTINED",
                quarantined_at_epoch_sec=time.time(),
            )
            state.quarantined_ticks.append(quarantined)
            self._global_quarantined.append(quarantined)
            return []

        finalized_candles: List[StreamingCandle] = []

        # 3. Minute boundary crossing check
        if state.active_1m is not None:
            if tick.timestamp_epoch_sec >= state.active_1m.bar_end_epoch_sec:
                # Crossed minute boundary: finalize current active bar and roll up
                finalized_candles.extend(self._finalize_1m_bar(state))

        # 4. Update active 1m bar or initialize new bar
        if state.active_1m is None:
            bar_start = compute_bar_start_epoch(tick.timestamp_epoch_sec, 60)
            bar_end = bar_start + 60
            state.active_1m = _Active1mBar(
                instrument_key=tick.instrument_key,
                bar_start_epoch_sec=bar_start,
                bar_end_epoch_sec=bar_end,
                open_paise=tick.price_paise,
                high_paise=tick.price_paise,
                low_paise=tick.price_paise,
                close_paise=tick.price_paise,
                volume=tick.volume,
                tick_count=1,
            )
        else:
            state.active_1m.update(tick.price_paise, tick.volume)

        # 5. Assemble provisional candles across configured timeframes
        provisional_candles: List[StreamingCandle] = []
        for tf in self._timeframes:
            prov = self._build_provisional_candle(state, tf)
            if prov is not None:
                provisional_candles.append(prov)

        # Filter finalized candles to configured timeframes
        emitted_finalized = [c for c in finalized_candles if c.timeframe in self._timeframes]
        emitted: List[StreamingCandle] = emitted_finalized + provisional_candles

        # 6. Dispatch to registered callbacks
        if emitted:
            self._dispatch_callbacks(emitted)

        return emitted

    async def on_tick_async(self, tick: TickFrame) -> List[StreamingCandle]:
        """
        1. The use of function:
           Asynchronous wrapper around on_tick guaranteeing awaitable callback execution.

        2. How does the specific function work:
           Executes synchronous on_tick state machine, then directly awaits any async callbacks.

        3. Concepts used in the function:
           Asynchronous dispatching, coroutine execution.

        4. Places where this function is imported and used:
           Used by asynchronous event consumers and async test suites.

        5. Final output of the function, before and after:
           Before: Incoming tick frame. After: Awaited callback delivery and emitted candle list.
        """
        emitted = self.on_tick(tick)
        if emitted:
            await self._dispatch_callbacks_async(emitted)
        return emitted

    def check_boundary_clock(self, current_epoch_sec: Optional[int] = None) -> List[StreamingCandle]:
        """
        1. The use of function:
           Evaluates boundary clocks to finalize expired bars during periods of low or paused tick liquidity.

        2. How does the specific function work:
           For each instrument with an active 1m bar, checks if current_epoch_sec >= bar_end + grace_period.
           If expired, finalizes the active bar, cascades rollup to higher TFs, and resets active state.

        3. Concepts used in the function:
           Boundary clock synchronization, causal expiration without tick dependency.

        4. Places where this function is imported and used:
           Called periodically by background daemon supervisor timer loops and test suites.

        5. Final output of the function, before and after:
           Before: Stale open active bars. After: Finalized candle events emitted and active bar cleared.
        """
        now_epoch = current_epoch_sec if current_epoch_sec is not None else int(time.time())
        finalized_candles: List[StreamingCandle] = []

        for state in self._instruments.values():
            if state.active_1m is not None:
                expiration_threshold = state.active_1m.bar_end_epoch_sec + self._grace_period_sec
                if now_epoch >= expiration_threshold:
                    bars = self._finalize_1m_bar(state)
                    finalized_candles.extend([b for b in bars if b.timeframe in self._timeframes])

        if finalized_candles:
            self._dispatch_callbacks(finalized_candles)

        return finalized_candles

    def flush(self) -> List[StreamingCandle]:
        """
        1. The use of function:
           Force-finalizes all currently active bars across all instruments (e.g. at session close).

        2. How does the specific function work:
           Iterates through all active instrument states, invokes finalization, force-closes any open
           higher-TF constituents, and returns all produced finalized candles.

        3. Concepts used in the function:
           Session teardown, graceful buffer flushing.

        4. Places where this function is imported and used:
           Called at 15:30:00 IST market close and during daemon shutdown sequences.

        5. Final output of the function, before and after:
           Before: Active bars uncommitted. After: All active bars finalized and emitted.
        """
        finalized_candles: List[StreamingCandle] = []
        for state in self._instruments.values():
            if state.active_1m is not None:
                bars = self._finalize_1m_bar(state)
                finalized_candles.extend([b for b in bars if b.timeframe in self._timeframes])

            # Force-close any remaining partial higher-TF constituents
            for htf in self._higher_tfs:
                constituents = state.higher_tf_constituents[htf]
                if constituents and (htf in self._timeframes):
                    w_start = state.higher_tf_window_start[htf] or constituents[0].bar_start_epoch_sec
                    w_end = state.higher_tf_window_end[htf] or (w_start + self._tf_seconds[htf])
                    htf_candle = StreamingCandle(
                        instrument_key=state.instrument_key,
                        timeframe=htf,
                        bar_start_epoch_sec=w_start,
                        bar_end_epoch_sec=w_end,
                        open_paise=constituents[0].open_paise,
                        high_paise=max(c.high_paise for c in constituents),
                        low_paise=min(c.low_paise for c in constituents),
                        close_paise=constituents[-1].close_paise,
                        volume=sum(c.volume for c in constituents),
                        tick_count=sum(c.tick_count for c in constituents),
                        is_closed=True,
                        finalized_at_epoch_sec=w_end + self._grace_period_sec,
                    )
                    state.latest_finalized[htf] = htf_candle
                    finalized_candles.append(htf_candle)
                    state.reset_higher_tf_window(htf)

        if finalized_candles:
            self._dispatch_callbacks(finalized_candles)

        return finalized_candles

    def get_active_candle(self, instrument_key: str, timeframe: str = "1m") -> Optional[StreamingCandle]:
        """
        1. The use of function:
           Returns the current provisional candle for a given instrument and timeframe.

        2. How does the specific function work:
           Looks up instrument state and calls _build_provisional_candle().

        3. Concepts used in the function:
           Provisional state query.

        4. Places where this function is imported and used:
           Used by charting query handlers, REST snapshot endpoints, and tests.

        5. Final output of the function, before and after:
           Before: Instrument key. After: Latest provisional StreamingCandle or None.
        """
        state = self._instruments.get(instrument_key)
        if state is None:
            return None
        return self._build_provisional_candle(state, timeframe)

    def get_latest_finalized_candle(self, instrument_key: str, timeframe: str = "1m") -> Optional[StreamingCandle]:
        """
        1. The use of function:
           Returns the most recently finalized candle for a given instrument and timeframe.

        2. How does the specific function work:
           Queries latest_finalized dictionary on the instrument state.

        3. Concepts used in the function:
           Finalized state retrieval.

        4. Places where this function is imported and used:
           Queried by strategy runners to read historical closed bars.

        5. Final output of the function, before and after:
           Before: Instrument key. After: Latest closed StreamingCandle or None.
        """
        state = self._instruments.get(instrument_key)
        if state is None:
            return None
        return state.latest_finalized.get(timeframe)

    def get_quarantined_ticks(self, instrument_key: Optional[str] = None) -> List[QuarantinedTick]:
        """
        1. The use of function:
           Returns audit trail list of quarantined ticks, optionally filtered by instrument.

        2. How does the specific function work:
           Returns instrument-specific list if instrument_key provided, else returns _global_quarantined copy.

        3. Concepts used in the function:
           Telemetry inspection, forensic audit trail.

        4. Places where this function is imported and used:
           Queried by diagnostic handlers, risk monitoring dashboards, and unit tests.

        5. Final output of the function, before and after:
           Before: Optional instrument key. After: List of QuarantinedTick instances.
        """
        if instrument_key is not None:
            state = self._instruments.get(instrument_key)
            return list(state.quarantined_ticks) if state is not None else []
        return list(self._global_quarantined)

    async def start_consumer(
        self,
        frame_bus: FrameBus,
        instrument_keys: Optional[List[str]] = None,
    ) -> asyncio.Task:
        """
        1. The use of function:
           Spawns a continuous background asyncio consumer task reading TickFrames from FrameBus.

        2. How does the specific function work:
           Subscribes to FrameBus, starts async loop draining queue and routing to on_tick().

        3. Concepts used in the function:
           Async background workers, message subscription.

        4. Places where this function is imported and used:
           Invoked by live daemon lifecycle supervisor to attach candle builder to the message spine.

        5. Final output of the function, before and after:
           Before: Disconnected builder. After: Active running asyncio.Task consuming from FrameBus.
        """
        self._stop_requested = False
        queue = frame_bus.subscribe(instrument_keys=instrument_keys)

        async def _consumer_loop() -> None:
            """
            1. The use of function:
               Background loop continuously dequeuing ticks from FrameBus and aggregating candles.

            2. How does the specific function work:
               Awaits queue.get() with short timeouts, calls on_tick(), and marks task as done.

            3. Concepts used in the function:
               Asyncio worker loop, queue draining.

            4. Places where this function is imported and used:
               Spawned as background Task by start_consumer().

            5. Final output of the function, before and after:
               Before: Pending queued ticks. After: Processed ticks and aggregated candles.
            """
            try:
                while not self._stop_requested:
                    try:
                        tick = await asyncio.wait_for(queue.get(), timeout=0.1)
                        self.on_tick(tick)
                        queue.task_done()
                    except asyncio.TimeoutError:
                        continue
            finally:
                frame_bus.unsubscribe(queue)

        self._consumer_task = asyncio.create_task(_consumer_loop())
        return self._consumer_task

    async def stop_consumer(self) -> None:
        """
        1. The use of function:
           Gracefully stops the active FrameBus consumer background task.

        2. How does the specific function work:
           Sets _stop_requested flag to True, awaits task completion or cancels if pending.

        3. Concepts used in the function:
           Graceful task cancellation, clean teardown.

        4. Places where this function is imported and used:
           Invoked during daemon shutdown and test cleanup routines.

        5. Final output of the function, before and after:
           Before: Running consumer task. After: Stopped task and unsubscribed FrameBus queue.
        """
        self._stop_requested = True
        if self._consumer_task is not None and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        self._consumer_task = None

    def _get_or_create_state(self, instrument_key: str) -> _InstrumentCandleState:
        """
        1. The use of function:
           Retrieves or allocates the _InstrumentCandleState for an instrument key.

        2. How does the specific function work:
           Checks _instruments map; if absent, instantiates a new _InstrumentCandleState.

        3. Concepts used in the function:
           Lazy dictionary allocation, partitioned state management.

        4. Places where this function is imported and used:
           Internal helper called by on_tick() and query methods.

        5. Final output of the function, before and after:
           Before: Instrument key. After: Corresponding _InstrumentCandleState instance.
        """
        state = self._instruments.get(instrument_key)
        if state is None:
            state = _InstrumentCandleState(instrument_key, self._higher_tfs)
            self._instruments[instrument_key] = state
        return state

    def _finalize_1m_bar(self, state: _InstrumentCandleState) -> List[StreamingCandle]:
        """
        1. The use of function:
           Finalizes the active 1-minute bar and rolls up completed higher timeframe bars.

        2. How does the specific function work:
           - Materializes finalized 1m StreamingCandle with is_closed=True and causal finalized_at.
           - Records last_finalized_1m_end and updates state.latest_finalized['1m'].
           - Appends 1m candle to constituents of each configured higher timeframe.
           - Checks if higher timeframe window boundary is completed; if so, finalizes higher-TF bar.
           - Resets active_1m to None and returns all finalized candles.

        3. Concepts used in the function:
           Hierarchical bar aggregation, ADR-005 rollup, causal availability stamping.

        4. Places where this function is imported and used:
           Internal helper called by on_tick() on boundary crossings, boundary clocks, and flush().

        5. Final output of the function, before and after:
           Before: Open active 1m bar. After: Closed 1m candle and any closed higher-TF candles.
        """
        if state.active_1m is None:
            return []

        active = state.active_1m
        candle_1m = active.to_candle(
            is_closed=True,
            finalized_at_epoch_sec=active.bar_end_epoch_sec + self._grace_period_sec,
        )
        state.last_finalized_1m_end = active.bar_end_epoch_sec
        state.latest_finalized["1m"] = candle_1m
        state.active_1m = None

        finalized_list: List[StreamingCandle] = [candle_1m]

        # Cascading multi-timeframe rollup per ADR-005
        for htf in self._higher_tfs:
            tf_sec = self._tf_seconds[htf]
            w_start = compute_bar_start_epoch(candle_1m.bar_start_epoch_sec, tf_sec)
            w_end = w_start + tf_sec

            # If existing window was open and we jumped across it (e.g. data gap), close old window first
            if (
                state.higher_tf_window_end[htf] is not None
                and w_start >= state.higher_tf_window_end[htf]
                and len(state.higher_tf_constituents[htf]) > 0
            ):
                old_constituents = state.higher_tf_constituents[htf]
                old_start = state.higher_tf_window_start[htf] or old_constituents[0].bar_start_epoch_sec
                old_end = state.higher_tf_window_end[htf]
                old_htf = StreamingCandle(
                    instrument_key=state.instrument_key,
                    timeframe=htf,
                    bar_start_epoch_sec=old_start,
                    bar_end_epoch_sec=old_end,
                    open_paise=old_constituents[0].open_paise,
                    high_paise=max(c.high_paise for c in old_constituents),
                    low_paise=min(c.low_paise for c in old_constituents),
                    close_paise=old_constituents[-1].close_paise,
                    volume=sum(c.volume for c in old_constituents),
                    tick_count=sum(c.tick_count for c in old_constituents),
                    is_closed=True,
                    finalized_at_epoch_sec=old_end + self._grace_period_sec,
                )
                state.latest_finalized[htf] = old_htf
                finalized_list.append(old_htf)
                state.reset_higher_tf_window(htf)

            if state.higher_tf_window_start[htf] is None:
                state.higher_tf_window_start[htf] = w_start
                state.higher_tf_window_end[htf] = w_end

            state.higher_tf_constituents[htf].append(candle_1m)

            # Check if this 1m bar completed the higher-TF bar boundary
            if candle_1m.bar_end_epoch_sec >= state.higher_tf_window_end[htf]:
                constituents = state.higher_tf_constituents[htf]
                htf_candle = StreamingCandle(
                    instrument_key=state.instrument_key,
                    timeframe=htf,
                    bar_start_epoch_sec=state.higher_tf_window_start[htf],
                    bar_end_epoch_sec=state.higher_tf_window_end[htf],
                    open_paise=constituents[0].open_paise,
                    high_paise=max(c.high_paise for c in constituents),
                    low_paise=min(c.low_paise for c in constituents),
                    close_paise=constituents[-1].close_paise,
                    volume=sum(c.volume for c in constituents),
                    tick_count=sum(c.tick_count for c in constituents),
                    is_closed=True,
                    finalized_at_epoch_sec=state.higher_tf_window_end[htf] + self._grace_period_sec,
                )
                state.latest_finalized[htf] = htf_candle
                finalized_list.append(htf_candle)
                state.reset_higher_tf_window(htf)

        return finalized_list

    def _build_provisional_candle(
        self,
        state: _InstrumentCandleState,
        tf: str,
    ) -> Optional[StreamingCandle]:
        """
        1. The use of function:
           Constructs a provisional (is_closed=False) StreamingCandle for a specified timeframe.

        2. How does the specific function work:
           - For '1m': Returns active 1m bar state.
           - For higher TFs: Combines already-finalized constituent 1m bars in current window with active 1m bar.

        3. Concepts used in the function:
           Intrabar provisional aggregation, multi-timeframe rollup.

        4. Places where this function is imported and used:
           Internal helper called by on_tick() and get_active_candle().

        5. Final output of the function, before and after:
           Before: Instrument state and timeframe. After: Provisional StreamingCandle or None.
        """
        if state.active_1m is None:
            return None

        if tf == "1m":
            return state.active_1m.to_candle(is_closed=False, finalized_at_epoch_sec=None)

        if tf not in self._higher_tfs:
            return None

        tf_sec = self._tf_seconds[tf]
        w_start = compute_bar_start_epoch(state.active_1m.bar_start_epoch_sec, tf_sec)
        w_end = w_start + tf_sec

        constituents = state.higher_tf_constituents.get(tf, [])

        if constituents:
            open_paise = constituents[0].open_paise
            high_paise = max(max(c.high_paise for c in constituents), state.active_1m.high_paise)
            low_paise = min(min(c.low_paise for c in constituents), state.active_1m.low_paise)
            close_paise = state.active_1m.close_paise
            volume = sum(c.volume for c in constituents) + state.active_1m.volume
            tick_count = sum(c.tick_count for c in constituents) + state.active_1m.tick_count
        else:
            open_paise = state.active_1m.open_paise
            high_paise = state.active_1m.high_paise
            low_paise = state.active_1m.low_paise
            close_paise = state.active_1m.close_paise
            volume = state.active_1m.volume
            tick_count = state.active_1m.tick_count

        return StreamingCandle(
            instrument_key=state.instrument_key,
            timeframe=tf,
            bar_start_epoch_sec=w_start,
            bar_end_epoch_sec=w_end,
            open_paise=open_paise,
            high_paise=high_paise,
            low_paise=low_paise,
            close_paise=close_paise,
            volume=volume,
            tick_count=tick_count,
            is_closed=False,
            finalized_at_epoch_sec=None,
        )

    def _dispatch_callbacks(self, candles: Sequence[StreamingCandle]) -> None:
        """
        1. The use of function:
           Dispatches emitted candles to all registered callbacks, scheduling tasks for coroutines.

        2. How does the specific function work:
           Iterates over candles and callbacks. If callback is coroutine function, schedules task
           on running loop if available; otherwise invokes synchronous callable.

        3. Concepts used in the function:
           Callback distribution, asynchronous scheduling.

        4. Places where this function is imported and used:
           Internal helper called by on_tick(), check_boundary_clock(), and flush().

        5. Final output of the function, before and after:
           Before: Emitted candle batch. After: Callbacks notified.
        """
        if not self._callbacks:
            return

        loop: Optional[asyncio.AbstractEventLoop] = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        for candle in candles:
            for cb in self._callbacks:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        if loop is not None and loop.is_running():
                            loop.create_task(cb(candle))  # type: ignore[arg-type]
                    else:
                        cb(candle)
                except Exception:
                    pass

    async def _dispatch_callbacks_async(self, candles: Sequence[StreamingCandle]) -> None:
        """
        1. The use of function:
           Awaits execution of all registered callbacks sequentially for a batch of candles.

        2. How does the specific function work:
           Iterates over candles and callbacks, awaiting any coroutines and calling synchronous listeners.

        3. Concepts used in the function:
           Deterministic sequential coroutine dispatch.

        4. Places where this function is imported and used:
           Internal helper called by on_tick_async().

        5. Final output of the function, before and after:
           Before: Emitted candle batch. After: All callbacks completed and awaited.
        """
        for candle in candles:
            for cb in self._callbacks:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(candle)  # type: ignore[misc]
                    else:
                        cb(candle)
                except Exception:
                    pass
