"""
1. What this file does:
   Defines the research and streaming feature engineering package boundary for QuantView.

2. Overall design:
   Exposes high-performance online rolling indicators and data-lake feature priming engines
   guaranteeing mathematical parity (< 10^-12) against TradingView / Pine Script batch solvers.

3. Elements in the file:
   - StreamingFeatureEngine: Online streaming indicator engine for real-time daemon execution.

4. Final output of the file:
   - Exported streaming feature classes.
"""

from packages.research.streaming_features import StreamingFeatureEngine

__all__ = ["StreamingFeatureEngine"]
