"""
1. What this file does:
   Implements the online StreamingFeatureEngine for the QuantView Live Daemon (Milestone M7-09).
   Maintains incremental rolling indicators (SMA, Pine Script EMA, Wilder RSI, MACD, Supertrend)
   guaranteeing mathematical parity (< 10^-12) with packages/features/statistical/indicators.py,
   and primes indicator states directly from the historical DuckDB lake prior to live streaming.

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §5 and Milestone M7-09:
     - Real-Time Incremental Updates: O(1) state transitions per arriving candle without full series recalculation.
     - Pine Script Parity (< 10^-12): Seeds EMA on bar 0 matching TradingView ta.ema; Wilder RMA alpha for RSI/ATR.
     - Warm-Up Priming (seed_from_lake): Queries historical DuckDB lake partitions (Data/lake/quantview.duckdb)
       to eliminate live start-up latency and cold-start indicator distortion.
     - Multi-Indicator State: Manages arbitrary SMA/EMA horizons, Wilder RSI(14), MACD(12,26,9), and Supertrend(10,3.0).

3. Elements in the file:
   - StreamingFeatureEngine: Core stateful online indicator calculator and historical lake seeder.

4. Final output of the file:
   - Exported StreamingFeatureEngine class.
"""

from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import duckdb


class StreamingFeatureEngine:
    """
    1. The use of class:
       Maintains stateful, online rolling technical indicators updated on incoming candlestick bars.

    2. What the class contains:
       - sma_lengths: Set of configured SMA lookback lengths.
       - ema_lengths: Set of configured EMA lookback lengths.
       - rsi_length: Wilder RSI lookback length.
       - macd_params: Fast, slow, and signal lengths for MACD.
       - supertrend_params: Length and multiplier for Supertrend.
       - update(): Updates internal indicator buffers with a new bar.
       - update_candle(): Convenience method accepting a StreamingCandle or dict.
       - seed_from_lake(): Primes internal buffers from historical DuckDB lake.
       - sma(), ema(), rsi(), macd(), supertrend(): Getter functions returning latest indicator values.
       - get_all_features(): Snapshot dictionary of all current indicators.

    3. Technologies used and why:
       collections.deque for bounded O(1) rolling windows, pure math operations for speed and precision.

    4. Key design and overall design of the class:
       Replicates recursive filter equations bit-for-bit with Pine Script without lookahead or float divergence.
    """

    def __init__(
        self,
        sma_lengths: Optional[List[int]] = None,
        ema_lengths: Optional[List[int]] = None,
        rsi_length: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        supertrend_length: int = 10,
        supertrend_multiplier: float = 3.0,
    ) -> None:
        """
        1. The use of function:
           Initializes StreamingFeatureEngine with indicator parameters and prepares rolling buffers.

        2. How does the specific function work:
           - Configures indicator horizons (defaulting to standard periods: SMA 20/50, EMA 9/21/50, RSI 14).
           - Allocates deques and state scalar variables for recursive filter formulas.

        3. Concepts used in the function:
           Online streaming state initialization, memory bounding.

        4. Places where this function is imported and used:
           Used by live daemon bot runners, feature processors, and streaming tests.

        5. Final output of the function, before and after:
           Before: Unconfigured engine. After: Initialized StreamingFeatureEngine ready for streaming updates.
        """
        self.sma_lengths = sorted(list(set(sma_lengths or [20, 50])))
        self.ema_lengths = sorted(list(set(ema_lengths or [9, 21, 50])))
        self.rsi_length = rsi_length
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.supertrend_length = supertrend_length
        self.supertrend_multiplier = supertrend_multiplier

        # Internal state tracking
        self.bar_count: int = 0
        self.prev_close: Optional[float] = None

        # SMA state: sliding window deques of close prices
        self._sma_windows: Dict[int, Deque[float]] = {
            length: deque(maxlen=length) for length in self.sma_lengths
        }
        self._current_sma: Dict[int, float] = {length: float("nan") for length in self.sma_lengths}

        # EMA state: latest exponential moving average scalar values
        self._current_ema: Dict[int, float] = {}

        # RSI state
        self._rsi_gains: List[float] = []
        self._rsi_losses: List[float] = []
        self._rsi_avg_gain: Optional[float] = None
        self._rsi_avg_loss: Optional[float] = None
        self._current_rsi: float = float("nan")

        # MACD state
        self._macd_fast_ema: Optional[float] = None
        self._macd_slow_ema: Optional[float] = None
        self._macd_signal_ema: Optional[float] = None
        self._current_macd: float = float("nan")
        self._current_macd_signal: float = float("nan")
        self._current_macd_hist: float = float("nan")

        # Supertrend state
        self._tr_history: List[float] = []
        self._atr: Optional[float] = None
        self._final_upper: Optional[float] = None
        self._final_lower: Optional[float] = None
        self._supertrend_val: float = float("nan")
        self._supertrend_direction: int = 0

    def reset(self) -> None:
        """
        1. The use of function:
           Clears all rolling buffers and resets indicator values back to initial cold state.

        2. How does the specific function work:
           Empties deques, resets counters, and restores NaNs.

        3. Concepts used in the function:
           State clearing, warm-up cycle re-initialization.

        4. Places where this function is imported and used:
           Used between test fixtures and strategy re-initializations.

        5. Final output of the function, before and after:
           Before: Populated buffers. After: Blank cold-start engine state.
        """
        self.bar_count = 0
        self.prev_close = None
        for length in self.sma_lengths:
            self._sma_windows[length].clear()
            self._current_sma[length] = float("nan")
        self._current_ema.clear()
        self._rsi_gains.clear()
        self._rsi_losses.clear()
        self._rsi_avg_gain = None
        self._rsi_avg_loss = None
        self._current_rsi = float("nan")
        self._macd_fast_ema = None
        self._macd_slow_ema = None
        self._macd_signal_ema = None
        self._current_macd = float("nan")
        self._current_macd_signal = float("nan")
        self._current_macd_hist = float("nan")
        self._tr_history.clear()
        self._atr = None
        self._final_upper = None
        self._final_lower = None
        self._supertrend_val = float("nan")
        self._supertrend_direction = 0

    def update(
        self,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float = 0.0,
    ) -> Dict[str, Any]:
        """
        1. The use of function:
           Ingests a new OHLCV bar, updating all online rolling indicators deterministically.

        2. How does the specific function work:
           - Increments bar counter and appends close to SMA deques.
           - Updates Pine Script EMAs: bar 0 seeds with close, bar t updates via alpha.
           - Updates Wilder RSI: accumulates initial length diffs, then updates RMA avg_gain/avg_loss.
           - Updates MACD line and signal EMA.
           - Updates Supertrend ATR, upper/lower trailing bands, and directional switch state.
           - Returns snapshot of all current feature values.

        3. Concepts used in the function:
           Online causal recurrence, Pine Script mathematical parity, Wilder smoothing.

        4. Places where this function is imported and used:
           Invoked on every bar completion by LiveDaemon and ReplayPlayer.

        5. Final output of the function, before and after:
           Before: Previous bar state. After: New state reflecting latest bar and returned features dictionary.
        """
        self.bar_count += 1

        # 1. Update SMA
        for length in self.sma_lengths:
            window = self._sma_windows[length]
            window.append(close)
            if len(window) == length:
                self._current_sma[length] = sum(window) / length
            else:
                self._current_sma[length] = float("nan")

        # 2. Update EMA (Pine Script Parity: seed on bar 0 with close)
        for length in self.ema_lengths:
            alpha = 2.0 / (length + 1.0)
            if length not in self._current_ema:
                self._current_ema[length] = close
            else:
                prev_val = self._current_ema[length]
                self._current_ema[length] = alpha * close + (1.0 - alpha) * prev_val

        # 3. Update Wilder RSI
        if self.prev_close is not None:
            diff = close - self.prev_close
            gain = max(diff, 0.0)
            loss = max(-diff, 0.0)
            self._rsi_gains.append(gain)
            self._rsi_losses.append(loss)

            if len(self._rsi_gains) < self.rsi_length:
                self._current_rsi = float("nan")
            elif len(self._rsi_gains) == self.rsi_length:
                # Initial SMA seed of gains and losses
                self._rsi_avg_gain = sum(self._rsi_gains) / self.rsi_length
                self._rsi_avg_loss = sum(self._rsi_losses) / self.rsi_length
                self._current_rsi = self._compute_rsi_from_averages(self._rsi_avg_gain, self._rsi_avg_loss)
            else:
                # Wilder RMA smoothing
                alpha_rsi = 1.0 / self.rsi_length
                self._rsi_avg_gain = alpha_rsi * gain + (1.0 - alpha_rsi) * self._rsi_avg_gain
                self._rsi_avg_loss = alpha_rsi * loss + (1.0 - alpha_rsi) * self._rsi_avg_loss
                self._current_rsi = self._compute_rsi_from_averages(self._rsi_avg_gain, self._rsi_avg_loss)
        else:
            self._current_rsi = float("nan")

        # 4. Update MACD
        fast_alpha = 2.0 / (self.macd_fast + 1.0)
        slow_alpha = 2.0 / (self.macd_slow + 1.0)
        sig_alpha = 2.0 / (self.macd_signal + 1.0)

        if self._macd_fast_ema is None:
            self._macd_fast_ema = close
            self._macd_slow_ema = close
        else:
            self._macd_fast_ema = fast_alpha * close + (1.0 - fast_alpha) * self._macd_fast_ema
            self._macd_slow_ema = slow_alpha * close + (1.0 - slow_alpha) * self._macd_slow_ema

        self._current_macd = self._macd_fast_ema - self._macd_slow_ema

        if self._macd_signal_ema is None:
            self._macd_signal_ema = self._current_macd
        else:
            self._macd_signal_ema = sig_alpha * self._current_macd + (1.0 - sig_alpha) * self._macd_signal_ema

        self._current_macd_signal = self._macd_signal_ema
        self._current_macd_hist = self._current_macd - self._current_macd_signal

        # 5. Update Supertrend
        if self.prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))

        self._tr_history.append(tr)
        if len(self._tr_history) < self.supertrend_length:
            self._supertrend_val = float("nan")
            self._supertrend_direction = 0
        elif len(self._tr_history) == self.supertrend_length:
            # First valid ATR: arithmetic SMA of initial TRs
            self._atr = sum(self._tr_history) / self.supertrend_length
            hl2 = (high + low) / 2.0
            basic_up = hl2 + self.supertrend_multiplier * self._atr
            basic_lo = hl2 - self.supertrend_multiplier * self._atr
            self._final_upper = basic_up
            self._final_lower = basic_lo
            if close > basic_up:
                self._supertrend_direction = 1
                self._supertrend_val = self._final_lower
            else:
                self._supertrend_direction = -1
                self._supertrend_val = self._final_upper
        else:
            # Subsequent ATR: Wilder RMA smoothing
            alpha_st = 1.0 / self.supertrend_length
            self._atr = alpha_st * tr + (1.0 - alpha_st) * self._atr
            hl2 = (high + low) / 2.0
            cur_basic_up = hl2 + self.supertrend_multiplier * self._atr
            cur_basic_lo = hl2 - self.supertrend_multiplier * self._atr

            # Final upper band
            if cur_basic_up < self._final_upper or (self.prev_close and self.prev_close > self._final_upper):
                self._final_upper = cur_basic_up

            # Final lower band
            if cur_basic_lo > self._final_lower or (self.prev_close and self.prev_close < self._final_lower):
                self._final_lower = cur_basic_lo

            # Direction transition
            prev_st = self._supertrend_val
            curr_dir = self._supertrend_direction
            if prev_st == self._final_upper or curr_dir == -1:
                if close > self._final_upper:
                    curr_dir = 1
                else:
                    curr_dir = -1
            else:
                if close < self._final_lower:
                    curr_dir = -1
                else:
                    curr_dir = 1

            self._supertrend_direction = curr_dir
            self._supertrend_val = self._final_lower if curr_dir == 1 else self._final_upper

        self.prev_close = close
        return self.get_all_features()

    def update_candle(self, candle: Any) -> Dict[str, Any]:
        """
        1. The use of function:
           Convenience method parsing candle attributes and delegating to update().

        2. How does the specific function work:
           Extracts open, high, low, close, volume supporting integer paise and float rupees.

        3. Concepts used in the function:
           Polymorphic candle ingestion.

        4. Places where this function is imported and used:
           Used by daemon frame consumers and event subscribers.

        5. Final output of the function, before and after:
           Before: Raw candle object. After: Updated indicator state.
        """
        # Check integer paise properties first
        if hasattr(candle, "open_paise"):
            o = candle.open_paise / 100.0
            h = candle.high_paise / 100.0
            l = candle.low_paise / 100.0
            c = candle.close_paise / 100.0
            v = getattr(candle, "volume", 0)
        elif isinstance(candle, dict):
            o = float(candle.get("open", candle.get("open_paise", 0) / 100.0))
            h = float(candle.get("high", candle.get("high_paise", 0) / 100.0))
            l = float(candle.get("low", candle.get("low_paise", 0) / 100.0))
            c = float(candle.get("close", candle.get("close_paise", 0) / 100.0))
            v = float(candle.get("volume", 0))
        else:
            o = float(getattr(candle, "open", 0.0))
            h = float(getattr(candle, "high", 0.0))
            l = float(getattr(candle, "low", 0.0))
            c = float(getattr(candle, "close", 0.0))
            v = float(getattr(candle, "volume", 0.0))

        return self.update(open=o, high=h, low=l, close=c, volume=v)

    def _compute_rsi_from_averages(self, avg_gain: float, avg_loss: float) -> float:
        """
        1. The use of function:
           Calculates Wilder's RSI value from smoothed average gain and average loss.

        2. How does the specific function work:
           Applies fail-safe division guards: 50.0 for flat series, 100.0 if loss is 0, 0.0 if gain is 0,
           and otherwise computes 100.0 - (100.0 / (1.0 + RS)).

        3. Concepts used in the function:
           Wilder Relative Strength Index, division-by-zero boundary preservation.

        4. Places where this function is imported and used:
           Internal helper called by update().

        5. Final output of the function, before and after:
           Before: Raw averages. After: Bounded float in [0.0, 100.0].
        """
        if avg_loss == 0.0 and avg_gain == 0.0:
            return 50.0
        if avg_loss == 0.0:
            return 100.0
        if avg_gain == 0.0:
            return 0.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def sma(self, length: int) -> float:
        """
        1. The use of function:
           Returns the current Simple Moving Average (SMA) value for the specified lookback length.

        2. How does the specific function work:
           Looks up length in self._current_sma; raises KeyError if not configured.

        3. Concepts used in the function:
           Indicator value inspection.

        4. Places where this function is imported and used:
           Used by trading strategies, feature extractors, and unit tests.

        5. Final output of the function, before and after:
           Before: Target lookback length. After: Current rolling SMA float (or NaN if warming up).
        """
        if length not in self._current_sma:
            raise KeyError(f"SMA length {length} was not registered at engine initialization.")
        return self._current_sma[length]

    def ema(self, length: int) -> float:
        """
        1. The use of function:
           Returns the current Exponential Moving Average (EMA) value for the specified length.

        2. How does the specific function work:
           Looks up length in self._current_ema; raises KeyError if not configured.

        3. Concepts used in the function:
           Pine Script parity exponential moving average accessor.

        4. Places where this function is imported and used:
           Used by strategies and indicator divergence tests.

        5. Final output of the function, before and after:
           Before: Target EMA length. After: Current smoothed EMA float value.
        """
        if length not in self._current_ema:
            raise KeyError(f"EMA length {length} was not registered at engine initialization.")
        return self._current_ema[length]

    def rsi(self, length: int = 14) -> float:
        """
        1. The use of function:
           Returns the current Wilder Relative Strength Index (RSI) value.

        2. How does the specific function work:
           Returns cached self._current_rsi.

        3. Concepts used in the function:
           Wilder momentum oscillator retrieval.

        4. Places where this function is imported and used:
           Used by mean-reversion bots and indicator checks.

        5. Final output of the function, before and after:
           Before: None or length. After: Bounded RSI value in [0.0, 100.0] or NaN.
        """
        return self._current_rsi

    def macd(self) -> Dict[str, float]:
        """
        1. The use of function:
           Returns the current MACD line, signal line, and histogram values.

        2. How does the specific function work:
           Packages cached MACD line, signal line, and histogram into a dictionary.

        3. Concepts used in the function:
           MACD trend and momentum coordinates.

        4. Places where this function is imported and used:
           Used by momentum and breakout strategies.

        5. Final output of the function, before and after:
           Before: None. After: Dictionary with 'macd', 'signal', and 'hist' float values.
        """
        return {
            "macd": self._current_macd,
            "signal": self._current_macd_signal,
            "hist": self._current_macd_hist,
        }

    def supertrend(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Returns the current Supertrend band price and directional trend bias.

        2. How does the specific function work:
           Packages current band value and direction (+1 Bullish, -1 Bearish) into a dictionary.

        3. Concepts used in the function:
           Directional regime state machine.

        4. Places where this function is imported and used:
           Used by trailing stop engines and trend-following strategies.

        5. Final output of the function, before and after:
           Before: None. After: Dictionary containing 'supertrend' (float) and 'direction' (+1/-1 int).
        """
        return {
            "supertrend": self._supertrend_val,
            "direction": self._supertrend_direction,
        }

    def get_all_features(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Returns a consolidated dictionary snapshot of all active technical indicators.

        2. How does the specific function work:
           Gathers current SMAs, EMAs, RSI, MACD, and Supertrend values into a key-value dictionary.

        3. Concepts used in the function:
           Feature vector construction.

        4. Places where this function is imported and used:
           Used by strategy bot signal generators.

        5. Final output of the function, before and after:
           Before: Scattered state. After: Dictionary of current feature values.
        """
        features: Dict[str, Any] = {
            "bar_count": self.bar_count,
            "rsi_14": self._current_rsi,
            "macd": self._current_macd,
            "macd_signal": self._current_macd_signal,
            "macd_hist": self._current_macd_hist,
            "supertrend": self._supertrend_val,
            "supertrend_direction": self._supertrend_direction,
        }
        for length, val in self._current_sma.items():
            features[f"sma_{length}"] = val
        for length, val in self._current_ema.items():
            features[f"ema_{length}"] = val
        return features

    def seed_from_lake(
        self,
        instrument_key: str,
        lookback_bars: int = 100,
        lake_path: str = "Data/lake/quantview.duckdb",
    ) -> int:
        """
        1. The use of function:
           Primes rolling indicator buffers using historical bars queried from the DuckDB lake.

        2. How does the specific function work:
           - Connects to DuckDB at lake_path in read-only mode.
           - Queries completed 1m bars for instrument_key (supporting index or option views).
           - Sorts bars chronologically ascending.
           - Streams bars through self.update() to warm up buffers.
           - Returns total count of seeded bars.

        3. Concepts used in the function:
           Zero-latency warm-up, historical state priming, DuckDB columnar query execution.

        4. Places where this function is imported and used:
           Invoked prior to live WebSocket or FrameBus event consumption.

        5. Final output of the function, before and after:
           Before: Unprimed (NaN) indicators. After: Warmed up indicator buffers ready for live trading.
        """
        if not Path(lake_path).exists():
            return 0

        conn = duckdb.connect(lake_path, read_only=True)
        try:
            # Check available views
            tables = [r[0] for r in conn.execute("SHOW TABLES;").fetchall()]
            rows: List[Tuple[float, float, float, float, float]] = []

            # Determine appropriate query target
            if "v_candles_underlying" in tables and ("NIFTY" in instrument_key or "INDEX" in instrument_key):
                query = """
                    SELECT open, high, low, close, volume
                    FROM v_candles_underlying
                    WHERE interval = '1m' AND (symbol = ? OR symbol = 'NIFTY')
                    ORDER BY bar_end DESC
                    LIMIT ?
                """
                raw_rows = conn.execute(query, [instrument_key, lookback_bars]).fetchall()
                rows = list(reversed(raw_rows))
            elif "v_candles_options" in tables and ("CE" in instrument_key or "PE" in instrument_key):
                query = """
                    SELECT open, high, low, close, volume
                    FROM v_candles_options
                    WHERE contract_id = ?
                    ORDER BY bar_end DESC
                    LIMIT ?
                """
                raw_rows = conn.execute(query, [instrument_key, lookback_bars]).fetchall()
                rows = list(reversed(raw_rows))
            elif "v_candles_underlying_1m" in tables:
                query = """
                    SELECT open, high, low, close, volume
                    FROM v_candles_underlying_1m
                    WHERE instrument_key = ?
                    ORDER BY epoch_sec DESC
                    LIMIT ?
                """
                raw_rows = conn.execute(query, [instrument_key, lookback_bars]).fetchall()
                rows = list(reversed(raw_rows))

            count = 0
            for r in rows:
                o, h, l, c, v = float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])
                self.update(open=o, high=h, low=l, close=c, volume=v)
                count += 1

            return count
        finally:
            conn.close()
