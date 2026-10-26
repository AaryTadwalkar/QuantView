"""
1. What this file does:
   Implements canonical baseline smoke strategies for Gate G2a single-leg options verification (Task M4-09).
   Provides LongCETrendFollowing and LongPEMeanReversion implementations.

2. Overall design:
   Adheres to Strategy(Protocol) in packages/strategies/__init__.py:
     - LongCETrendFollowing: Tracks EMA fast and slow periods, emitting ENTER_LONG on bullish cross.
     - LongPEMeanReversion: Tracks price deviation relative to a rolling mean, emitting ENTER_LONG PE on extreme extension.
     - Enforces causal evaluations without look-ahead bias (available_at <= decision_time).
     - Decoupled from broker SDKs and raw database dependencies.

3. Elements in the file:
   - LongCETrendFollowingParams: Pydantic parameter validation model for trend strategy.
   - LongCETrendFollowing: Single-leg Call trend following strategy implementation.
   - LongPEMeanReversionParams: Pydantic parameter validation model for mean-reversion strategy.
   - LongPEMeanReversion: Single-leg Put mean reversion strategy implementation.

4. Final output of the file:
   - Exported strategy classes and automatic registration in default StrategyRegistry.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from packages.domain import UtcEpochSec
from packages.strategies import SignalAction, StrategySignal, get_default_strategy_registry


class LongCETrendFollowingParams(BaseModel):
    """
    1. The use of class:
       Pydantic parameter schema for LongCETrendFollowing strategy.

    2. What the class contains:
       - fast_period: Fast EMA lookback window (default 9).
       - slow_period: Slow EMA lookback window (default 21).

    3. Technologies used and why:
       Pydantic BaseModel for immutable parameter validation and schema verification.

    4. Key design and overall design of the class:
       Ensures strategy parameters cannot be misconfigured at runtime.
    """
    fast_period: int = Field(default=9, ge=2, le=50)
    slow_period: int = Field(default=21, ge=5, le=200)


class LongCETrendFollowing:
    """
    1. The use of class:
       Single-leg Call trend-following strategy for baseline engine benchmarks and Gate G2a verification.

    2. What the class contains:
       - fast_period, slow_period: Moving average parameters.
       - prices: History buffer of close prices.
       - in_position: State tracking active position.
       - on_start, on_bar, on_stop: Canonical lifecycle hooks.

    3. Technologies used and why:
       Pure Python state machine adhering to Strategy(Protocol).

    4. Key design and overall design of the class:
       Calculates exponential moving averages strictly on completed closed bars.
       Emits ENTER_LONG on bullish crossover and EXIT on bearish breakdown.
    """

    def __init__(self) -> None:
        self.fast_period: int = 9
        self.slow_period: int = 21
        self.prices: List[float] = []
        self.in_position: bool = False

    def on_start(self, config: Dict[str, Any]) -> None:
        """
        1. The use of function:
           Initializes strategy state and loads validated parameters.

        2. How does the specific function work:
           Extracts fast_period and slow_period from config dict and resets price buffer.

        3. Concepts used in the function:
           Lifecycle configuration setup.

        4. Places where this function is imported and used:
           Invoked by StrategyRegistry.create() or BacktestRunner prior to simulation.

        5. Final output of the function, before and after:
           Before: Uninitialized strategy. After: Configured strategy ready for bar processing.
        """
        self.fast_period = int(config.get("fast_period", 9))
        self.slow_period = int(config.get("slow_period", 21))
        self.prices = []
        self.in_position = False

    def _calculate_ema(self, series: List[float], period: int) -> float:
        """
        1. The use of function:
           Computes exponential moving average over historical series.

        2. How does the specific function work:
           Applies standard EMA multiplier alpha = 2 / (period + 1) recursively.

        3. Concepts used in the function:
           Digital signal smoothing.

        4. Places where this function is imported and used:
           Used internally inside on_bar().

        5. Final output of the function, before and after:
           Before: Float price array. After: Scalar EMA value.
        """
        if not series:
            return 0.0
        k = 2.0 / (period + 1.0)
        ema = series[0]
        for val in series[1:]:
            ema = (val * k) + (ema * (1.0 - k))
        return ema

    def on_bar(self, timestamp: UtcEpochSec, features: Dict[str, Any]) -> Optional[StrategySignal]:
        """
        1. The use of function:
           Consumes completed bar feature dictionary and emits causal trading signal.

        2. How does the specific function work:
           Extracts close price, appends to price history, checks for fast EMA crossing above slow EMA.
           Emits ENTER_LONG on upward cross if not in position; emits EXIT on downward cross if in position.

        3. Concepts used in the function:
           Causal indicator evaluation without look-ahead bias.

        4. Places where this function is imported and used:
           Called on every completed minute bar by the simulation runner.

        5. Final output of the function, before and after:
           Before: Bar features and current position state.
           After: Optional StrategySignal (ENTER_LONG, EXIT, or None).
        """
        close_price = features.get("close")
        if close_price is None:
            return None

        self.prices.append(float(close_price))
        if len(self.prices) < self.slow_period:
            return None

        recent = self.prices[-self.slow_period * 2:]
        fast_ema = self._calculate_ema(recent, self.fast_period)
        slow_ema = self._calculate_ema(recent, self.slow_period)

        if not self.in_position and fast_ema > slow_ema:
            self.in_position = True
            return StrategySignal(
                action=SignalAction.ENTER_LONG,
                timestamp=timestamp,
                reason=f"Bullish EMA crossover: fast ({fast_ema:.2f}) > slow ({slow_ema:.2f})",
            )
        elif self.in_position and fast_ema < slow_ema:
            self.in_position = False
            return StrategySignal(
                action=SignalAction.EXIT,
                timestamp=timestamp,
                reason=f"Bearish EMA cross-under: fast ({fast_ema:.2f}) < slow ({slow_ema:.2f})",
            )

        return None

    def on_stop(self) -> None:
        """
        1. The use of function:
           Finalizes strategy state when session or run terminates.

        2. How does the specific function work:
           Clears in_position flag.

        3. Concepts used in the function:
           State cleanup.

        4. Places where this function is imported and used:
           Called by simulation runner on session shutdown.

        5. Final output of the function, before and after:
           Before: Active strategy. After: Cleaned up strategy.
        """
        self.in_position = False


class LongPEMeanReversionParams(BaseModel):
    """
    1. The use of class:
       Pydantic parameter schema for LongPEMeanReversion strategy.

    2. What the class contains:
       - window: Rolling mean window (default 20).
       - dev_threshold: Deviation percentage threshold to trigger reversion (default 0.005 = 0.5%).

    3. Technologies used and why:
       Pydantic BaseModel for validation.

    4. Key design and overall design of the class:
       Guarantees positive window and valid threshold.
    """
    window: int = Field(default=20, ge=5, le=100)
    dev_threshold: float = Field(default=0.005, ge=0.0001, le=0.1)


class LongPEMeanReversion:
    """
    1. The use of class:
       Single-leg Put mean-reversion strategy for baseline engine benchmarks and Gate G2a verification.

    2. What the class contains:
       - window: Rolling window for mean.
       - dev_threshold: Threshold deviation.
       - prices: Historical price buffer.
       - in_position: Position state.
       - on_start, on_bar, on_stop: Lifecycle methods.

    3. Technologies used and why:
       Pure Python state machine adhering to Strategy(Protocol).

    4. Key design and overall design of the class:
       Detects overextended spot prices above the rolling mean and buys PEs expecting reversion downward.
    """

    def __init__(self) -> None:
        self.window: int = 20
        self.dev_threshold: float = 0.005
        self.prices: List[float] = []
        self.in_position: bool = False

    def on_start(self, config: Dict[str, Any]) -> None:
        """
        1. The use of function:
           Initializes strategy state and parameters.

        2. How does the specific function work:
           Sets window and dev_threshold from config dict.

        3. Concepts used in the function:
           Lifecycle configuration setup.

        4. Places where this function is imported and used:
           Called by BacktestRunner.

        5. Final output of the function, before and after:
           Before: Uninitialized. After: Configured strategy ready for bar stream.
        """
        self.window = int(config.get("window", 20))
        self.dev_threshold = float(config.get("dev_threshold", 0.005))
        self.prices = []
        self.in_position = False

    def on_bar(self, timestamp: UtcEpochSec, features: Dict[str, Any]) -> Optional[StrategySignal]:
        """
        1. The use of function:
           Consumes bar features and triggers PE entries when spot is overextended above mean.

        2. How does the specific function work:
           Calculates simple moving average. If spot > mean * (1 + dev_threshold), enters PE.
           Exits when spot reverts back to or below mean.

        3. Concepts used in the function:
           Statistical mean-reversion without lookahead.

        4. Places where this function is imported and used:
           Called on every completed minute bar.

        5. Final output of the function, before and after:
           Before: Current bar features. After: Optional StrategySignal.
        """
        close_price = features.get("close")
        if close_price is None:
            return None

        self.prices.append(float(close_price))
        if len(self.prices) < self.window:
            return None

        window_slice = self.prices[-self.window:]
        mean_val = sum(window_slice) / len(window_slice)
        curr = window_slice[-1]

        if not self.in_position and curr > mean_val * (1.0 + self.dev_threshold):
            self.in_position = True
            return StrategySignal(
                action=SignalAction.ENTER_LONG,
                timestamp=timestamp,
                reason=f"Overextended above mean ({curr:.2f} > {mean_val:.2f}): Buy PE for reversion",
            )
        elif self.in_position and curr <= mean_val:
            self.in_position = False
            return StrategySignal(
                action=SignalAction.EXIT,
                timestamp=timestamp,
                reason=f"Reverted to mean ({curr:.2f} <= {mean_val:.2f}): Exit PE",
            )

        return None

    def on_stop(self) -> None:
        """
        1. The use of function:
           Cleans up strategy state on session termination.

        2. How does the specific function work:
           Resets in_position.

        3. Concepts used in the function:
           State cleanup.

        4. Places where this function is imported and used:
           Called by BacktestRunner at end of run.

        5. Final output of the function, before and after:
           Before: Running strategy. After: Reset strategy.
        """
        self.in_position = False


# Register smoke strategies in the default registry upon module import
_reg = get_default_strategy_registry()
_reg.register(
    name="LongCETrendFollowing",
    strategy_cls=LongCETrendFollowing,
    param_schema=LongCETrendFollowingParams,
    description="Baseline single-leg Call trend following strategy using EMA crossover.",
)
_reg.register(
    name="LongPEMeanReversion",
    strategy_cls=LongPEMeanReversion,
    param_schema=LongPEMeanReversionParams,
    description="Baseline single-leg Put mean reversion strategy using rolling price deviation.",
)
