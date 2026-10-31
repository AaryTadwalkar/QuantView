"""
1. What this file does:
   Implements the 24/7 historical market tick ReplayPlayer for QuantView Stage 7.
   Replays authentic binary WebSocket segment files or generates realistic synthetic micro-ticks
   from the DuckDB Parquet lake, streaming them into the FrameBus with speed regulation and interactive controls.

2. Overall design:
   Enables round-the-clock deterministic testing, model validation, and paper simulation:
     - Multi-source ingestion: Prioritizes byte-exact raw Upstox binary segments (.bin / .bin.gz)
       via framing and WsQuoteDecoder; falls back to DuckDB lake candles (v_candles_underlying_1m).
     - Micro-tick generation: Synthesizes 4 realistic intra-minute ticks (open -> low -> high -> close
       for bullish bars, open -> high -> low -> close for bearish bars) with 15-second spacing.
     - Speed regulation: Controls inter-tick delay using PlaybackSpeed (1x, 2x, 5x, asap) with
       inter-session sleep bounding to prevent indefinite idling during trading halts.
     - Interactive controls: start(), pause(), resume(), stop(), and dynamic set_speed().

3. Elements in the file:
   - PlaybackSpeed: Enum representing playback acceleration modes (1x, 2x, 5x, asap).
   - ReplayPlayer: Asynchronous historical tick replay orchestrator.

4. Final output of the file:
   Exported PlaybackSpeed and ReplayPlayer classes ready for paper trading and live daemon simulations.
"""

import asyncio
import gzip
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

from packages.transport.frame_bus import FrameBus, TickFrame

logger = logging.getLogger("quantview.transport.replay_player")


class PlaybackSpeed(str, Enum):
    """
    1. The use of class:
       Enumeration of supported playback speed multipliers for historical tick replay.

    2. What the class contains:
       - REALTIME: 1x real-time pace reflecting authentic clock intervals.
       - FAST_2X: 2x accelerated pace (half sleep intervals).
       - FAST_5X: 5x accelerated pace (one-fifth sleep intervals).
       - ASAP: As-fast-as-possible replay without inter-tick delays for batch testing.

    3. Technologies used and why:
       Python str and Enum for seamless serialization, configuration parsing, and type safety.

    4. Key design and overall design of the class:
       Provides clean human-readable speed indicators matching standard market replay consoles.
    """

    REALTIME = "1x"
    FAST_2X = "2x"
    FAST_5X = "5x"
    ASAP = "asap"

    def get_multiplier(self) -> float:
        """
        1. The use of function:
           Translates the playback speed enum into a numerical speed multiplier.

        2. How does the specific function work:
           Returns 1.0 for REALTIME, 2.0 for FAST_2X, 5.0 for FAST_5X, and infinity for ASAP.

        3. Concepts used in the function:
           Enum value mapping, numerical rate multiplier derivation.

        4. Places where this function is imported and used:
           Invoked internally by ReplayPlayer._sleep_inter_tick().

        5. Final output of the function, before and after:
           Before: PlaybackSpeed enum member. After: Floating point multiplier value.
        """
        if self == PlaybackSpeed.REALTIME:
            return 1.0
        if self == PlaybackSpeed.FAST_2X:
            return 2.0
        if self == PlaybackSpeed.FAST_5X:
            return 5.0
        return float("inf")


class ReplayPlayer:
    """
    1. The use of class:
       Asynchronous historical tick replay engine feeding the FrameBus for 24/7 paper trading.

    2. What the class contains:
       - _bus: Target FrameBus instance receiving published ticks.
       - _trade_date: Optional target trade date string ('YYYY-MM-DD').
       - _speed: Configured PlaybackSpeed enum mode.
       - _raw_data_dir: Base directory path containing raw WebSocket segment files.
       - _duckdb_path: Path to DuckDB lake file containing historical 1m candle views.
       - _instrument_key: Optional filter key to restrict replay to a single instrument.
       - _max_sleep_sec: Ceiling cap on inter-tick sleep to avoid long stalls over gaps.
       - _force_source: Optional override ('raw' or 'duckdb') to select ingestion source.
       - Controls: start(), pause(), resume(), stop(), and dynamic set_speed().

    3. Technologies used and why:
       - asyncio.Task and asyncio.Event for non-blocking concurrent playback and pause coordination.
       - gzip and struct unpackers for authentic Upstox binary segment stream decoding.
       - DuckDB SQL engine for high-performance reading from Parquet-backed candle views.

    4. Key design and overall design of the class:
       Acts as a plug-and-play drop-in replacement for the live WebSocket feed collector. Downstream
       consumers receive standard TickFrame objects with is_replayed=True and cannot distinguish
       between live and replayed market conditions.
    """

    def __init__(
        self,
        bus: FrameBus,
        trade_date: Optional[str] = None,
        speed: PlaybackSpeed = PlaybackSpeed.REALTIME,
        raw_data_dir: str = "data/raw/upstox_ws/ticks",
        duckdb_path: str = "Data/lake/quantview.duckdb",
        instrument_key: Optional[str] = None,
        max_sleep_sec: float = 1.0,
        force_source: Optional[str] = None,
        max_ticks: Optional[int] = None,
    ) -> None:
        """
        1. The use of function:
           Initializes the ReplayPlayer with target bus, data sources, speed, and filter configuration.

        2. How does the specific function work:
           - Records configuration attributes and initializes playback lifecycle state.
           - Sets up asyncio.Event for pause/resume signaling (initialized to set/unpaused).
           - Resets publication count and inter-tick clock tracking.

        3. Concepts used in the function:
           Dependency injection, asynchronous synchronization primitive setup, state initialization.

        4. Places where this function is imported and used:
           Instantiated by PaperTradingDaemon, integration test harnesses, and backtest runners.

        5. Final output of the function, before and after:
           Before: Uninitialized player state. After: Configured ReplayPlayer ready to start playback.
        """
        self._bus = bus
        self._trade_date = trade_date
        self._speed = speed
        self._raw_data_dir = raw_data_dir
        self._duckdb_path = duckdb_path
        self._instrument_key = instrument_key
        self._max_sleep_sec = max_sleep_sec
        self._force_source = force_source
        self._max_ticks = max_ticks

        # Lifecycle state
        self._is_running: bool = False
        self._is_paused: bool = False
        self._stop_requested: bool = False
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._task: Optional[asyncio.Task] = None
        self._published_count: int = 0
        self._last_tick_epoch: Optional[int] = None
        self._asap_yield_counter: int = 0

    @property
    def is_running(self) -> bool:
        """
        1. The use of function:
           Reports whether the replay loop is actively running.

        2. How does the specific function work:
           Evaluates internal running flag and verifies the underlying asyncio task is active.

        3. Concepts used in the function:
           Property accessor, task state evaluation.

        4. Places where this function is imported and used:
           Queried by daemon monitoring routines and test assertions.

        5. Final output of the function, before and after:
           Before: None. After: Boolean indicating active execution.
        """
        return self._is_running and (self._task is not None and not self._task.done())

    @property
    def is_paused(self) -> bool:
        """
        1. The use of function:
           Reports whether playback is currently paused.

        2. How does the specific function work:
           Returns the boolean value of _is_paused.

        3. Concepts used in the function:
           Property accessor.

        4. Places where this function is imported and used:
           Queried by user interface controls and lifecycle tests.

        5. Final output of the function, before and after:
           Before: None. After: Boolean indicating pause status.
        """
        return self._is_paused

    @property
    def speed(self) -> PlaybackSpeed:
        """
        1. The use of function:
           Returns the currently configured playback speed.

        2. How does the specific function work:
           Returns the PlaybackSpeed enum member stored in _speed.

        3. Concepts used in the function:
           Property accessor.

        4. Places where this function is imported and used:
           Read by telemetry loggers and UI controls.

        5. Final output of the function, before and after:
           Before: None. After: Active PlaybackSpeed enum member.
        """
        return self._speed

    @property
    def published_count(self) -> int:
        """
        1. The use of function:
           Returns aggregate count of frames successfully published to FrameBus during this session.

        2. How does the specific function work:
           Returns the integer count stored in _published_count.

        3. Concepts used in the function:
           Property accessor, telemetry inspection.

        4. Places where this function is imported and used:
           Checked in test validations and status endpoints.

        5. Final output of the function, before and after:
           Before: None. After: Integer total of published frames.
        """
        return self._published_count

    def set_speed(self, speed: PlaybackSpeed) -> None:
        """
        1. The use of function:
           Dynamically modifies playback speed while replay is in progress.

        2. How does the specific function work:
           Updates internal _speed attribute; subsequent inter-tick sleep intervals adapt immediately.

        3. Concepts used in the function:
           Dynamic rate modulation, state mutation.

        4. Places where this function is imported and used:
           Called by operator speed slider controls and load tests.

        5. Final output of the function, before and after:
           Before: Previous speed setting. After: Updated PlaybackSpeed applied to ongoing replay.
        """
        logger.info("Replay speed changed from %s to %s", self._speed.value, speed.value)
        self._speed = speed

    def start(self) -> asyncio.Task:
        """
        1. The use of function:
           Starts historical tick replay asynchronously as a background asyncio.Task.

        2. How does the specific function work:
           - Verifies if task is already running; returns active task if so.
           - Resets lifecycle flags, unpauses resume event, and launches run() via asyncio.create_task.
           - Stores task handle and returns it to caller.

        3. Concepts used in the function:
           Asynchronous task creation, lifecycle management, non-blocking startup.

        4. Places where this function is imported and used:
           Called by LiveDaemon / PaperDaemon during engine boot or test suites.

        5. Final output of the function, before and after:
           Before: Idle player. After: Active background asyncio.Task executing the replay loop.
        """
        if self.is_running and self._task is not None:
            return self._task

        self._is_running = True
        self._stop_requested = False
        self._is_paused = False
        self._resume_event.set()
        self._task = asyncio.create_task(self.run())
        return self._task

    def pause(self) -> None:
        """
        1. The use of function:
           Pauses tick replay without terminating the playback task or losing buffer position.

        2. How does the specific function work:
           Clears _resume_event and sets _is_paused flag, causing playback loop to await resumption.

        3. Concepts used in the function:
           Asynchronous cooperative suspension, event synchronization.

        4. Places where this function is imported and used:
           Called by operator pause buttons or stepping controllers.

        5. Final output of the function, before and after:
           Before: Continuously publishing ticks. After: Suspended at current tick until resume() is called.
        """
        if not self._is_running or self._is_paused:
            return
        self._is_paused = True
        self._resume_event.clear()
        logger.info("ReplayPlayer paused at published tick count %d", self._published_count)

    def resume(self) -> None:
        """
        1. The use of function:
           Resumes paused tick replay from the exact point of suspension.

        2. How does the specific function work:
           Clears _is_paused flag and sets _resume_event, releasing the awaiting playback loop.

        3. Concepts used in the function:
           Asynchronous event signaling, state resumption.

        4. Places where this function is imported and used:
           Called by operator play/resume buttons or step controls.

        5. Final output of the function, before and after:
           Before: Suspended replay loop. After: Active replay loop continuing tick publishing.
        """
        if not self._is_running or not self._is_paused:
            return
        self._is_paused = False
        self._resume_event.set()
        logger.info("ReplayPlayer resumed at published tick count %d", self._published_count)

    def stop(self) -> None:
        """
        1. The use of function:
           Terminates tick replay and releases background task resources.

        2. How does the specific function work:
           - Sets _stop_requested flag and unpauses resume event to allow clean loop exit.
           - Cancels asyncio task if still running.
           - Clears running flag.

        3. Concepts used in the function:
           Graceful task cancellation, lifecycle teardown.

        4. Places where this function is imported and used:
           Called on session shutdown, fixture cleanup, or operator stop request.

        5. Final output of the function, before and after:
           Before: Active or paused replay task. After: Stopped replay task and reset lifecycle status.
        """
        self._stop_requested = True
        self._is_paused = False
        self._resume_event.set()

        if self._task is not None and not self._task.done():
            self._task.cancel()

        self._is_running = False
        logger.info("ReplayPlayer stopped after publishing %d ticks", self._published_count)

    async def run(self) -> int:
        """
        1. The use of function:
           Main replay execution coroutine reading ticks and streaming them to the FrameBus.

        2. How does the specific function work:
           - Evaluates whether to source ticks from authentic binary raw segments or DuckDB lake candles.
           - Executes selected ingestion pipeline while respecting pause events and stop requests.
           - Updates total published frame count and guarantees clean state reset in finally block.

        3. Concepts used in the function:
           Coroutine orchestration, error isolation, source routing.

        4. Places where this function is imported and used:
           Launched by start() or awaited directly in integration test runners.

        5. Final output of the function, before and after:
           Before: 0 published ticks. After: Replay completed with total published count returned.
        """
        self._is_running = True
        self._stop_requested = False
        self._last_tick_epoch = None
        self._asap_yield_counter = 0

        try:
            # Determine source
            use_raw = False
            raw_files: List[Path] = []

            if self._force_source == "raw":
                use_raw = True
                raw_files = self._discover_raw_segment_files()
                if not raw_files:
                    raise FileNotFoundError(
                        f"Forced raw source selected but no segment files found in {self._raw_data_dir}"
                    )
            elif self._force_source == "duckdb":
                use_raw = False
            else:
                raw_files = self._discover_raw_segment_files()
                use_raw = len(raw_files) > 0

            if use_raw:
                logger.info("Replaying from %d raw segment files", len(raw_files))
                await self._replay_raw_segments(raw_files)
            else:
                logger.info("Replaying from DuckDB Parquet lake: %s", self._duckdb_path)
                await self._replay_duckdb()

        except asyncio.CancelledError:
            logger.info("Replay task received cancellation")
        except Exception as ex:
            logger.error("ReplayPlayer encountered unexpected exception: %s", ex, exc_info=True)
            raise
        finally:
            self._is_running = False

        return self._published_count

    async def _sleep_inter_tick(self, current_ts_epoch: int) -> None:
        """
        1. The use of function:
           Regulates inter-tick sleep interval based on configured PlaybackSpeed multiplier.

        2. How does the specific function work:
           - Computes elapsed time delta between consecutive ticks.
           - In ASAP mode, skips sleep and periodically yields CPU via asyncio.sleep(0).
           - In 1x, 2x, 5x modes, divides delta by multiplier and caps at max_sleep_sec.
           - Sleeps asynchronously if calculated duration exceeds 0.

        3. Concepts used in the function:
           Speed regulation, event loop cooperative multitasking, clock delta scaling.

        4. Places where this function is imported and used:
           Invoked prior to publishing each tick in _replay_raw_segments() and _replay_duckdb().

        5. Final output of the function, before and after:
           Before: Unpaced tick dispatch. After: Paced tick dispatch aligned with chosen playback speed.
        """
        if self._last_tick_epoch is None:
            self._last_tick_epoch = current_ts_epoch
            return

        delta = max(0.0, float(current_ts_epoch - self._last_tick_epoch))
        self._last_tick_epoch = current_ts_epoch

        if self._speed == PlaybackSpeed.ASAP:
            self._asap_yield_counter += 1
            if self._asap_yield_counter >= 100:
                self._asap_yield_counter = 0
                await asyncio.sleep(0)
            return

        multiplier = self._speed.get_multiplier()
        sleep_sec = min(delta / multiplier, self._max_sleep_sec)
        if sleep_sec > 0:
            await asyncio.sleep(sleep_sec)

    def _discover_raw_segment_files(self) -> List[Path]:
        """
        1. The use of function:
           Discovers and sorts authentic binary WebSocket segment files for replay.

        2. How does the specific function work:
           - Inspects raw data directory.
           - If trade_date is specified, looks in trade_date=YYYY-MM-DD folder.
           - If not specified, finds available trade_date subdirectories and picks the latest.
           - Collects all ws_seg_*.bin.gz and ws_seg_*.bin files sorted alphabetically.

        3. Concepts used in the function:
           Filesystem traversal, partition path pattern matching, chronological sorting.

        4. Places where this function is imported and used:
           Called internally by run() during source evaluation.

        5. Final output of the function, before and after:
           Before: Raw path string. After: List of sorted Path objects referencing binary segment files.
        """
        base_dir = Path(self._raw_data_dir)
        if not base_dir.exists():
            return []

        target_dir: Optional[Path] = None
        if self._trade_date:
            target_dir = base_dir / f"trade_date={self._trade_date}"
            if not target_dir.exists():
                return []
        else:
            date_dirs = sorted([d for d in base_dir.glob("trade_date=*") if d.is_dir()])
            if not date_dirs:
                return []
            target_dir = date_dirs[-1]

        files = sorted(list(target_dir.glob("ws_seg_*.bin.gz")) + list(target_dir.glob("ws_seg_*.bin")))
        return files

    async def _replay_raw_segments(self, files: List[Path]) -> None:
        """
        1. The use of function:
           Replays ticks from authentic binary raw WebSocket segment files.

        2. How does the specific function work:
           - Unpacks binary frames using services.collector_ws.framing.unpack_frames_from_bytes.
           - Decodes raw protobuf payloads using services.collector_ws.decoder.WsQuoteDecoder.
           - Maps decoded WsQuote records into canonical TickFrame instances.
           - Yields to pause/stop signals and streams frames to FrameBus with speed regulation.

        3. Concepts used in the function:
           Binary unpacking, protobuf feed decoding, stream throttling, pause/resume coordination.

        4. Places where this function is imported and used:
           Called by run() when authentic raw segments are present.

        5. Final output of the function, before and after:
           Before: Binary segment disk files. After: Decoded canonical TickFrames published to FrameBus.
        """
        from services.collector_ws.decoder import WsQuoteDecoder
        from services.collector_ws.framing import unpack_frames_from_bytes

        decoder = WsQuoteDecoder(connection_id="replay_player")

        for file_path in files:
            if self._stop_requested:
                break

            try:
                if file_path.suffix == ".gz":
                    with gzip.open(file_path, "rb") as gz_f:
                        raw_data = gz_f.read()
                else:
                    with open(file_path, "rb") as b_f:
                        raw_data = b_f.read()
            except Exception as read_ex:
                logger.warning("Failed reading raw segment file %s: %s", file_path, read_ex)
                continue

            parsed_frames, _, _ = unpack_frames_from_bytes(raw_data)

            for p_frame in parsed_frames:
                if self._stop_requested:
                    break

                await self._resume_event.wait()
                if self._stop_requested:
                    break

                quotes = decoder.decode_frame(
                    raw_payload=p_frame.payload,
                    collector_sequence=p_frame.sequence_number,
                    arrival_ts_us=p_frame.recv_time_us,
                    payload_checksum=p_frame.payload_crc32,
                    raw_segment_ref=file_path.name,
                )

                for quote in quotes:
                    if self._stop_requested:
                        break

                    await self._resume_event.wait()
                    if self._stop_requested:
                        break

                    # Instrument filter
                    if self._instrument_key and quote.instrument_key != self._instrument_key:
                        continue

                    # Construct TickFrame
                    ts_iso = quote.ts_event or quote.ts_recv
                    try:
                        ts_epoch = int(datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).timestamp())
                    except Exception:
                        ts_epoch = int(p_frame.recv_time_us / 1_000_000.0)

                    price_paise = int(round(quote.ltp * 100))
                    vol = quote.volume_traded_today or quote.ltq
                    oi = int(quote.oi) if (quote.oi is not None and quote.oi > 0) else None
                    bid_px = int(round(quote.bid_px_1 * 100)) if quote.bid_px_1 is not None else None
                    ask_px = int(round(quote.ask_px_1 * 100)) if quote.ask_px_1 is not None else None

                    tick_frame = TickFrame(
                        sequence_id=0,
                        instrument_key=quote.instrument_key,
                        timestamp_epoch_sec=ts_epoch,
                        timestamp_iso=ts_iso,
                        price_paise=price_paise,
                        volume=vol,
                        open_interest=oi,
                        bid_price_paise=bid_px,
                        ask_price_paise=ask_px,
                        bid_qty=quote.bid_qty_1,
                        ask_qty=quote.ask_qty_1,
                        is_replayed=True,
                    )

                    await self._sleep_inter_tick(ts_epoch)
                    self._bus.publish(tick_frame)
                    self._published_count += 1
                    if self._max_ticks is not None and self._published_count >= self._max_ticks:
                        self._stop_requested = True
                        break

    async def _replay_duckdb(self) -> None:
        """
        1. The use of function:
           Generates synthetic micro-ticks from historical 1-minute DuckDB lake candles.

        2. How does the specific function work:
           - Queries v_candles_underlying_1m from DuckDB.
           - Slices candles into 4 synthetic ticks (open -> low -> high -> close or open -> high -> low -> close).
           - Assigns intra-minute timestamps (0s, 15s, 30s, 45s) and distributes volume incrementally.
           - Publishes generated TickFrames with is_replayed=True to FrameBus under speed regulation.

        3. Concepts used in the function:
           Micro-tick generation, intra-bar synthetic modeling, DuckDB SQL execution.

        4. Places where this function is imported and used:
           Called by run() as fallback when raw segments are unavailable or DuckDB is forced.

        5. Final output of the function, before and after:
           Before: 1-minute OHLCV candles in DuckDB.
           After: 4 micro-ticks per candle published to FrameBus.
        """
        import duckdb

        if not Path(self._duckdb_path).exists():
            logger.warning("DuckDB database %s not found; skipping DuckDB replay", self._duckdb_path)
            return

        con = duckdb.connect(self._duckdb_path, read_only=True)
        try:
            con.execute(
                "CREATE TEMPORARY VIEW IF NOT EXISTS v_candles_underlying_1m AS "
                "SELECT * FROM v_candles_underlying WHERE interval = '1m'"
            )

            query = "SELECT symbol, bar_start, open, high, low, close, volume, oi FROM v_candles_underlying_1m"
            params = []
            if self._trade_date:
                query += " WHERE CAST(bar_start AS DATE) = CAST(? AS DATE)"
                params.append(self._trade_date)

            query += " ORDER BY bar_start ASC"
            rows = con.execute(query, params).fetchall()
        finally:
            con.close()

        if not rows:
            logger.warning("No 1m candles found in DuckDB for trade_date=%s", self._trade_date)
            return

        for row in rows:
            if self._stop_requested:
                break

            await self._resume_event.wait()
            if self._stop_requested:
                break

            symbol, bar_start, open_px, high_px, low_px, close_px, vol, oi = row
            inst_key = self._instrument_key or (
                "NSE_INDEX|Nifty 50" if symbol == "NIFTY" else f"NSE_INDEX|{symbol}"
            )

            # Determine 4 micro-tick price progression
            if close_px >= open_px:
                points = [(open_px, 0), (low_px, 15), (high_px, 30), (close_px, 45)]
            else:
                points = [(open_px, 0), (high_px, 15), (low_px, 30), (close_px, 45)]

            # Convert bar_start to UTC timestamp
            if isinstance(bar_start, datetime):
                bar_epoch = int(bar_start.timestamp())
            else:
                bar_epoch = int(datetime.fromisoformat(str(bar_start).replace("Z", "+00:00")).timestamp())

            total_vol = vol if vol is not None else 0
            open_int = int(oi) if (oi is not None and oi > 0) else None

            for idx, (px, sec_offset) in enumerate(points):
                if self._stop_requested:
                    break

                await self._resume_event.wait()
                if self._stop_requested:
                    break

                tick_epoch = bar_epoch + sec_offset
                tick_iso = datetime.fromtimestamp(tick_epoch, tz=timezone.utc).isoformat()
                px_paise = int(round(px * 100))
                tick_vol = int(total_vol * (idx + 1) / 4)

                tick_frame = TickFrame(
                    sequence_id=0,
                    instrument_key=inst_key,
                    timestamp_epoch_sec=tick_epoch,
                    timestamp_iso=tick_iso,
                    price_paise=px_paise,
                    volume=tick_vol,
                    open_interest=open_int,
                    bid_price_paise=px_paise - 5,
                    ask_price_paise=px_paise + 5,
                    bid_qty=50,
                    ask_qty=50,
                    is_replayed=True,
                )

                await self._sleep_inter_tick(tick_epoch)
                self._bus.publish(tick_frame)
                self._published_count += 1
                if self._max_ticks is not None and self._published_count >= self._max_ticks:
                    self._stop_requested = True
                    break
