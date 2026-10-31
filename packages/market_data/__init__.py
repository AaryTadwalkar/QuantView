"""
1. What this file does:
   Initializes the market_data package for QuantView Stage 7 (Streaming Candle Aggregator & Boundary Clocks).
   Exports canonical streaming market data primitives: StreamingCandle, StreamingCandleBuilder, and QuarantinedTick.

2. Overall design:
   Decouples raw, high-throughput FrameBus tick streams from downstream analytical and trading layers.
   Aggregates discrete tick events into provisional (is_closed=False) and finalized (is_closed=True)
   1-minute and multi-timeframe candles (3m, 5m, 15m) adhering strictly to Indian market session hours
   (09:15 to 15:30 IST) and causal availability rules (ADR-008, ADR-041).

3. Elements in the file:
   - StreamingCandle: Canonical data structure representing provisional and finalized candles in integer paise.
   - QuarantinedTick: Immutable audit container recording ticks dropped due to session or late arrival violations.
   - StreamingCandleBuilder: State-machine aggregator assembling multi-timeframe bars from sequential TickFrames.

4. Final output of the file:
   Exported public symbols StreamingCandle, StreamingCandleBuilder, and QuarantinedTick in __all__.
"""

from packages.market_data.streaming_builder import (
    QuarantinedTick,
    StreamingCandle,
    StreamingCandleBuilder,
)

__all__ = [
    "StreamingCandle",
    "StreamingCandleBuilder",
    "QuarantinedTick",
]
