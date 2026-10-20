"""
1. What this file does:
   Defines the service boundary for collector_ws (live Upstox WebSocket market data streaming).

2. Overall design:
   collector_ws maintains the sole Upstox WebSocket connection. It streams protobuf binary frames
   into .partial raw segment files, fsyncs in batches (<= 1s loss window), and finalizes segments.
   It remains strictly raw-capture-only until M7-01 (when FrameBus real-time decoding begins).

3. Elements in the file:
   - Service metadata and lifecycle contract.

4. Final output of the file:
   - Package interface for services.collector_ws.
"""

SERVICE_NAME = "collector_ws"
