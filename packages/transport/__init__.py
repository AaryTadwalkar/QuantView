"""
1. What this file does:
   Initializes the transport package for QuantView Stage 7 (Real-Time Paper Trading, Live Daemon & FrameBus Bridge).
   Exports canonical transport primitives: FrameBus, TickFrame, ReplayPlayer, and PlaybackSpeed.

2. Overall design:
   Acts as the unified gateway to the local in-memory pub/sub spinal transport architecture.
   Provides zero-copy, low-latency distribution of market data ticks across collector daemons,
   historical replay engines, streaming candle builders, strategy hosts, and client WebSocket bridges.

3. Elements in the file:
   - FrameBus: Thread-safe, asyncio-enabled circular ring buffer and topic pub/sub broker.
   - TickFrame: Immutable frozen dataclass standardizing live and replayed market ticks.
   - ReplayPlayer: Deterministic historical tick playback player supporting raw segments and DuckDB lake candles.
   - PlaybackSpeed: Playback speed multiplier enumeration (1x, 2x, 5x, asap).

4. Final output of the file:
   Exported public symbols FrameBus, TickFrame, ReplayPlayer, and PlaybackSpeed in __all__.
"""

from packages.transport.frame_bus import FrameBus, TickFrame
from packages.transport.replay_player import PlaybackSpeed, ReplayPlayer

__all__ = [
    "FrameBus",
    "TickFrame",
    "ReplayPlayer",
    "PlaybackSpeed",
]
