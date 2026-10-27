"""
1. What this file does:
   Implements the deterministic Swing Structure, Break of Structure (BOS), and Change of Character (CHoCH)
   feature engine for QuantView (ENGINE §21.2, Task M5-06 / Gate G3).

2. Overall design:
   Evaluates swing highs and swing lows over configurable left and right windows (W_L=5, W_R=5)
   with strict tie-breaking (strict left inequality, non-strict right inequality) and causal
   confirmation gating (confirmed_at = ts_close(i + W_R)). Maintains an explicit three-state market
   bias machine (NEUTRAL, BULLISH, BEARISH) and one-time level consumption to classify structural
   break events (BULLISH_BOS, BEARISH_BOS, BULLISH_CHOCH, BEARISH_CHOCH) without look-ahead bias.

3. Elements in the file:
   - MarketBias: Enum representing bias states (NEUTRAL, BULLISH, BEARISH).
   - StructuralEvent: Enum representing structure break events (NONE, BULLISH_BOS, BEARISH_BOS, BULLISH_CHOCH, BEARISH_CHOCH).
   - BreakCriterion: Enum specifying CLOSE_THROUGH vs TOUCH break evaluation.
   - SwingLevel: Immutable record holding level price, pivot coordinates, and confirmation metadata.
   - MarketStructureBar: Output record holding point-in-time structural state and active levels.
   - MarketStructureEngine: Stateful and batch engine executing causal market structure evaluation.
   - compute_market_structure: High-level calculation function evaluating OHLC series.
   - register_market_structure_feature: Registration helper binding the feature to FeatureRegistry.

4. Final output of the file:
   - Causal, deterministic market structure feature stream with confirmed-lag provenance.
"""

from enum import Enum
from typing import List, NamedTuple, Optional, Sequence

from packages.features.registry import FeatureRegistry
from packages.features.schemas import (
    FeatureDefinition,
    MemoryClass,
    RepaintClass,
    SourceTier,
)


class MarketBias(str, Enum):
    """
    1. The use of class:
       Represents the macro directional trend bias of the market structure.

    2. What the class contains:
       - NEUTRAL: Unestablished trend before initial structural break.
       - BULLISH: Upward trending structural bias.
       - BEARISH: Downward trending structural bias.

    3. Technologies used and why:
       Str-Enum for direct string serialization and type checking.

    4. Key design and overall design of the class:
       Core state variable driving BOS vs CHoCH event classification.
    """
    NEUTRAL = "NEUTRAL"
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class StructuralEvent(str, Enum):
    """
    1. The use of class:
       Classifies structural break events occurring on a closed bar.

    2. What the class contains:
       - NONE: No confirmed structural level was broken on this bar.
       - BULLISH_BOS: Continuation break of active swing high in BULLISH trend.
       - BEARISH_BOS: Continuation break of active swing low in BEARISH trend.
       - BULLISH_CHOCH: Structural trend reversal breaking swing high from BEARISH (or initial from NEUTRAL).
       - BEARISH_CHOCH: Structural trend reversal breaking swing low from BULLISH (or initial from NEUTRAL).

    3. Technologies used and why:
       Str-Enum for standardized logging and signal triggers.

    4. Key design and overall design of the class:
       Discrete signal classification honoring ENGINE §21.2 matrix.
    """
    NONE = "NONE"
    BULLISH_BOS = "BULLISH_BOS"
    BEARISH_BOS = "BEARISH_BOS"
    BULLISH_CHOCH = "BULLISH_CHOCH"
    BEARISH_CHOCH = "BEARISH_CHOCH"


class BreakCriterion(str, Enum):
    """
    1. The use of class:
       Configures the trigger rule for level penetration.

    2. What the class contains:
       - CLOSE_THROUGH: Default variant; bar close must penetrate the level.
       - TOUCH: Optional variant; bar high or low penetrates the level intrabar.

    3. Technologies used and why:
       Str-Enum configuration parameter.

    4. Key design and overall design of the class:
       Enables strict close-through default with support for touch breakout strategies.
    """
    CLOSE_THROUGH = "CLOSE_THROUGH"
    TOUCH = "TOUCH"


class SwingLevel(NamedTuple):
    """
    1. The use of class:
       Immutable representation of a confirmed swing pivot level.

    2. What the class contains:
       - price: Price level of the pivot peak or trough.
       - pivot_index: Historical bar index where the extreme price occurred.
       - pivot_time: Economic timestamp of the pivot bar.
       - confirmed_index: Historical bar index where confirmation window completed (pivot_index + W_R).
       - confirmed_at: Timestamp when the pivot became causally visible.
       - is_consumed: Flag indicating whether this level has already been broken.

    3. Technologies used and why:
       NamedTuple for lightweight, immutable structural level provenance.

    4. Key design and overall design of the class:
       Guarantees causal visibility: strategies may observe level only when t >= confirmed_index.
    """
    price: float
    pivot_index: int
    pivot_time: int
    confirmed_index: int
    confirmed_at: int
    is_consumed: bool = False


class MarketStructureBar(NamedTuple):
    """
    1. The use of class:
       Complete structural state emitted for each evaluated bar.

    2. What the class contains:
       - index: Bar sequence index.
       - ts_event: Bar close timestamp.
       - available_at: Causal availability timestamp.
       - last_confirmed_high_price: Price of active confirmed swing high (or None).
       - last_confirmed_high_time: Timestamp of active confirmed swing high.
       - last_confirmed_low_price: Price of active confirmed swing low (or None).
       - last_confirmed_low_time: Timestamp of active confirmed swing low.
       - structural_event: StructuralEvent enum for this bar.
       - market_bias: MarketBias enum as of this bar close.
       - broken_level_price: Price of the level broken on this bar (if any).
       - broken_level_time: Timestamp of the level broken on this bar.
       - quality_flags: Diagnostic flags (e.g. AMBIGUOUS_DOUBLE_BREAK).

    3. Technologies used and why:
       NamedTuple matching ENGINE §21.2 Output Record Schema.

    4. Key design and overall design of the class:
       Immutable feature record consumed by strategy execution contexts.
    """
    index: int
    ts_event: int
    available_at: int
    last_confirmed_high_price: Optional[float]
    last_confirmed_high_time: Optional[int]
    last_confirmed_low_price: Optional[float]
    last_confirmed_low_time: Optional[int]
    structural_event: StructuralEvent
    market_bias: MarketBias
    broken_level_price: Optional[float]
    broken_level_time: Optional[int]
    quality_flags: List[str]


class MarketStructureEngine:
    """
    1. The use of class:
       Stateful evaluation engine for BOS and CHoCH structural market tracking.

    2. What the class contains:
       - pivot_left: Left lookback window W_L (default 5).
       - pivot_right: Right confirmation window W_R (default 5).
       - break_criterion: BreakCriterion (CLOSE_THROUGH or TOUCH).
       - current_bias: Active MarketBias state.
       - active_swing_high: Active confirmed SwingLevel or None.
       - active_swing_low: Active confirmed SwingLevel or None.

    3. Technologies used and why:
       Pure Python state machine with strict asymmetric tie-breaking and one-time consumption.

    4. Key design and overall design of the class:
       Enforces ENGINE §21.2 contracts ensuring zero look-ahead and deterministic replay determinism.
    """

    def __init__(
        self,
        pivot_left: int = 5,
        pivot_right: int = 5,
        break_criterion: BreakCriterion = BreakCriterion.CLOSE_THROUGH,
    ):
        """
        1. The use of function:
           Initializes the MarketStructureEngine with configuration parameters.

        2. How does the specific function work:
           Validates window parameters >= 1 and initializes bias to NEUTRAL.

        3. Concepts used in the function:
           Parameter validation, initial bias state.

        4. Places where this function is imported and used:
           Used by compute_market_structure and StrategyContext.

        5. Final output of the function, before and after:
           Before: Uninitialized engine. After: Configured MarketStructureEngine instance.
        """
        if pivot_left < 1 or pivot_right < 1:
            raise ValueError(f"Pivot windows must be >= 1, got W_L={pivot_left}, W_R={pivot_right}.")
        self.pivot_left = pivot_left
        self.pivot_right = pivot_right
        self.break_criterion = break_criterion

        self.current_bias = MarketBias.NEUTRAL
        self.active_swing_high: Optional[SwingLevel] = None
        self.active_swing_low: Optional[SwingLevel] = None

    def evaluate_series(
        self,
        highs: Sequence[float],
        lows: Sequence[float],
        closes: Sequence[float],
        timestamps: Optional[Sequence[int]] = None,
    ) -> List[MarketStructureBar]:
        """
        1. The use of function:
           Evaluates an entire OHLC series chronologically and emits MarketStructureBar records.

        2. How does the specific function work:
           Iterates through each bar t from 0 to N-1:
           1. Confirms candidate swing pivots at bar i = t - W_R.
           2. Checks for level penetrations at bar t under configured BreakCriterion.
           3. Transitions market bias and marks broken levels as consumed.
           4. Emits MarketStructureBar record.

        3. Concepts used in the function:
           Causal pivot confirmation, close-through breakout evaluation, one-time level consumption.

        4. Places where this function is imported and used:
           Used by compute_market_structure, feature registry runners, and unit tests.

        5. Final output of the function, before and after:
           Before: OHLC price sequences. After: List of MarketStructureBar records.
        """
        n = len(closes)
        if len(highs) != n or len(lows) != n:
            raise ValueError(f"Length mismatch: highs({len(highs)}), lows({len(lows)}), closes({n}).")
        if n == 0:
            return []

        ts = list(timestamps) if timestamps is not None else list(range(n))
        if len(ts) != n:
            raise ValueError(f"Length mismatch: timestamps({len(ts)}) vs closes({n}).")

        results: List[MarketStructureBar] = []

        for t in range(n):
            # Step 1: Check if bar i = t - W_R confirms as a new swing pivot
            candidate_i = t - self.pivot_right
            if candidate_i >= self.pivot_left:
                self._check_and_confirm_pivot(candidate_i, t, highs, lows, ts)

            # Step 2: Evaluate structural breaks at bar t
            bar_record = self._evaluate_breaks_at_bar(t, highs, lows, closes, ts)
            results.append(bar_record)

        return results

    def _check_and_confirm_pivot(
        self,
        i: int,
        t: int,
        highs: Sequence[float],
        lows: Sequence[float],
        ts: Sequence[int],
    ) -> None:
        """
        1. The use of function:
           Tests if candidate bar i satisfies swing high or low criteria and confirms it at bar t.

        2. How does the specific function work:
           Applies asymmetric tie-breaking rule:
           - Swing High: high[i] > high[i - l] for all l in [1, W_L] and high[i] >= high[i + r] for all r in [1, W_R].
           - Swing Low: low[i] < low[i - l] for all l in [1, W_L] and low[i] <= low[i + r] for all r in [1, W_R].
           If satisfied, sets confirmed level at bar t (available_at = ts[t]).

        3. Concepts used in the function:
           Asymmetric plateau tie-breaking, delayed causal confirmation.

        4. Places where this function is imported and used:
           Internal helper inside evaluate_series.

        5. Final output of the function, before and after:
           Before: Candidate at i. After: Updated active_swing_high / active_swing_low if confirmed.
        """
        # Test Swing High
        cand_h = highs[i]
        is_swing_high = True
        for l in range(1, self.pivot_left + 1):
            if not (cand_h > highs[i - l]):
                is_swing_high = False
                break
        if is_swing_high:
            for r in range(1, self.pivot_right + 1):
                if not (cand_h >= highs[i + r]):
                    is_swing_high = False
                    break

        if is_swing_high:
            self.active_swing_high = SwingLevel(
                price=cand_h,
                pivot_index=i,
                pivot_time=ts[i],
                confirmed_index=t,
                confirmed_at=ts[t],
                is_consumed=False,
            )

        # Test Swing Low
        cand_l = lows[i]
        is_swing_low = True
        for l in range(1, self.pivot_left + 1):
            if not (cand_l < lows[i - l]):
                is_swing_low = False
                break
        if is_swing_low:
            for r in range(1, self.pivot_right + 1):
                if not (cand_l <= lows[i + r]):
                    is_swing_low = False
                    break

        if is_swing_low:
            self.active_swing_low = SwingLevel(
                price=cand_l,
                pivot_index=i,
                pivot_time=ts[i],
                confirmed_index=t,
                confirmed_at=ts[t],
                is_consumed=False,
            )

    def _evaluate_breaks_at_bar(
        self,
        t: int,
        highs: Sequence[float],
        lows: Sequence[float],
        closes: Sequence[float],
        ts: Sequence[int],
    ) -> MarketStructureBar:
        """
        1. The use of function:
           Evaluates whether bar t breaks the active confirmed high or low.

        2. How does the specific function work:
           Under CLOSE_THROUGH:
             Tests close[t] > active_swing_high.price and close[t] < active_swing_low.price.
           Under TOUCH:
             Tests high[t] > active_swing_high.price and low[t] < active_swing_low.price.
           Applies the canonical classification matrix:
             - NEUTRAL + Break High -> BULLISH_CHOCH (New Bias: BULLISH)
             - NEUTRAL + Break Low  -> BEARISH_CHOCH (New Bias: BEARISH)
             - BULLISH + Break High -> BULLISH_BOS   (New Bias: BULLISH)
             - BULLISH + Break Low  -> BEARISH_CHOCH (New Bias: BEARISH)
             - BEARISH + Break Low  -> BEARISH_BOS   (New Bias: BEARISH)
             - BEARISH + Break High -> BULLISH_CHOCH (New Bias: BULLISH)
           Marks broken level as consumed. Emits MarketStructureBar.

        3. Concepts used in the function:
           BOS vs CHoCH state machine, one-time level consumption.

        4. Places where this function is imported and used:
           Internal helper inside evaluate_series.

        5. Final output of the function, before and after:
           Before: State as of bar t. After: Emitted MarketStructureBar and updated engine state.
        """
        bar_close = closes[t]
        bar_high = highs[t]
        bar_low = lows[t]
        bar_time = ts[t]

        event = StructuralEvent.NONE
        broken_price: Optional[float] = None
        broken_time: Optional[int] = None
        quality_flags: List[str] = []

        # Check eligibility: level must exist, not be consumed, and confirmed_index <= t
        high_eligible = (
            self.active_swing_high is not None
            and not self.active_swing_high.is_consumed
            and self.active_swing_high.confirmed_index <= t
        )
        low_eligible = (
            self.active_swing_low is not None
            and not self.active_swing_low.is_consumed
            and self.active_swing_low.confirmed_index <= t
        )

        break_high = False
        break_low = False

        if self.break_criterion == BreakCriterion.CLOSE_THROUGH:
            if high_eligible and bar_close > self.active_swing_high.price:  # type: ignore[union-attr]
                break_high = True
            if low_eligible and bar_close < self.active_swing_low.price:    # type: ignore[union-attr]
                break_low = True
        else:  # TOUCH
            if high_eligible and bar_high > self.active_swing_high.price:  # type: ignore[union-attr]
                break_high = True
            if low_eligible and bar_low < self.active_swing_low.price:    # type: ignore[union-attr]
                break_low = True

        # Handle double break under TOUCH
        if break_high and break_low:
            quality_flags.append("AMBIGUOUS_DOUBLE_BREAK")
            # Conservative trend-reversal policy: current bias flips first into CHoCH
            if self.current_bias == MarketBias.BULLISH:
                break_high = False  # Bearish break takes precedence
            elif self.current_bias == MarketBias.BEARISH:
                break_low = False   # Bullish break takes precedence
            else:
                # NEUTRAL: resolve using bar body direction
                if bar_close >= highs[t]:
                    break_low = False
                else:
                    break_high = False

        if break_high and self.active_swing_high is not None:
            broken_price = self.active_swing_high.price
            broken_time = self.active_swing_high.pivot_time
            # Consume level
            self.active_swing_high = self.active_swing_high._replace(is_consumed=True)

            if self.current_bias == MarketBias.NEUTRAL:
                event = StructuralEvent.BULLISH_CHOCH
                self.current_bias = MarketBias.BULLISH
            elif self.current_bias == MarketBias.BULLISH:
                event = StructuralEvent.BULLISH_BOS
                self.current_bias = MarketBias.BULLISH
            elif self.current_bias == MarketBias.BEARISH:
                # Structural trend reversal from Bearish to Bullish
                event = StructuralEvent.BULLISH_CHOCH
                self.current_bias = MarketBias.BULLISH

        elif break_low and self.active_swing_low is not None:
            broken_price = self.active_swing_low.price
            broken_time = self.active_swing_low.pivot_time
            # Consume level
            self.active_swing_low = self.active_swing_low._replace(is_consumed=True)

            if self.current_bias == MarketBias.NEUTRAL:
                event = StructuralEvent.BEARISH_CHOCH
                self.current_bias = MarketBias.BEARISH
            elif self.current_bias == MarketBias.BULLISH:
                # Structural trend reversal from Bullish to Bearish
                event = StructuralEvent.BEARISH_CHOCH
                self.current_bias = MarketBias.BEARISH
            elif self.current_bias == MarketBias.BEARISH:
                event = StructuralEvent.BEARISH_BOS
                self.current_bias = MarketBias.BEARISH

        # Record active levels (if unconsumed, expose them; else None)
        active_h_price = self.active_swing_high.price if (self.active_swing_high and not self.active_swing_high.is_consumed) else None
        active_h_time = self.active_swing_high.pivot_time if (self.active_swing_high and not self.active_swing_high.is_consumed) else None
        active_l_price = self.active_swing_low.price if (self.active_swing_low and not self.active_swing_low.is_consumed) else None
        active_l_time = self.active_swing_low.pivot_time if (self.active_swing_low and not self.active_swing_low.is_consumed) else None

        return MarketStructureBar(
            index=t,
            ts_event=bar_time,
            available_at=bar_time,
            last_confirmed_high_price=active_h_price,
            last_confirmed_high_time=active_h_time,
            last_confirmed_low_price=active_l_price,
            last_confirmed_low_time=active_l_time,
            structural_event=event,
            market_bias=self.current_bias,
            broken_level_price=broken_price,
            broken_level_time=broken_time,
            quality_flags=quality_flags,
        )


def compute_market_structure(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    timestamps: Optional[Sequence[int]] = None,
    pivot_left: int = 5,
    pivot_right: int = 5,
    break_criterion: str = "CLOSE_THROUGH",
) -> List[MarketStructureBar]:
    """
    1. The use of function:
       Functional entry point calculating causal BOS / CHoCH market structure series.

    2. How does the specific function work:
       Instantiates MarketStructureEngine with configured parameters and executes evaluate_series.

    3. Concepts used in the function:
       Deterministic market structure extraction, parameter encapsulation.

    4. Places where this function is imported and used:
       Used by trading strategies, backtest feature extractors, and unit tests.

    5. Final output of the function, before and after:
       Before: Raw OHLC lists. After: List of MarketStructureBar records.
    """
    criterion = BreakCriterion(break_criterion.upper())
    engine = MarketStructureEngine(
        pivot_left=pivot_left,
        pivot_right=pivot_right,
        break_criterion=criterion,
    )
    return engine.evaluate_series(highs, lows, closes, timestamps)


def register_market_structure_feature() -> str:
    """
    1. The use of function:
       Registers the BOS_CHOCH market structure feature definition into FeatureRegistry.

    2. How does the specific function work:
       Constructs FeatureDefinition with CONFIRMED_LAG repaint class and binds compute_market_structure.

    3. Concepts used in the function:
       Declarative registry registration, confirmed-lag documentation.

    4. Places where this function is imported and used:
       Called during package initialization and feature discovery.

    5. Final output of the function, before and after:
       Before: Unregistered feature. After: Feature registered in FeatureRegistry; returns feature_id.
    """
    defn = FeatureDefinition(
        name="BOS_CHOCH",
        version="v1",
        params={"pivot_left": 5, "pivot_right": 5, "break_criterion": "CLOSE_THROUGH"},
        lookback_window=11,
        warm_up_bars=11,
        memory_class=MemoryClass.INFINITE,
        source_tier=SourceTier.UNDERLYING_CANDLE,
        repaint_class=RepaintClass.CONFIRMED_LAG,
        output_schema={
            "structural_event": "string",
            "market_bias": "string",
            "last_confirmed_high": "float64",
            "last_confirmed_low": "float64",
            "broken_level_price": "float64",
        },
        description="Deterministic Swing Structure, BOS and CHoCH engine with causal confirmation lag.",
    )
    registry = FeatureRegistry()
    return registry.register(
        definition=defn,
        compute_fn=compute_market_structure,
        metadata={"engine_class": "MarketStructureEngine"},
    )
