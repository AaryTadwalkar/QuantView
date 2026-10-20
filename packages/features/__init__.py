"""
1. What this file does:
   Defines point-in-time technical indicator and feature extraction interfaces for QuantView.

2. Overall design:
   Features transform market data series into quantitative signals without look-ahead bias.
   The core invariant enforced at every step is:
       feature.available_at <= decision_time
   Features never access future bars, unclosed candles, or future option chain snapshots.

3. Elements in the file:
   - FeatureDefinition: Metadata specifying feature name, parameters, and lookback window.
   - BaseFeatureExtractor: Abstract base class for causal feature computation.

4. Final output of the file:
   - Exported feature contracts and causal computation interfaces.
"""

from typing import Dict, Any, List
from packages.domain import UtcEpochSec
from packages.data import DatasetManifest


class FeatureDefinition:
    """
    1. The use of class:
       Encapsulates parameter specification and identification for a computable feature.

    2. What the class contains:
       - name: String identifier of the feature (e.g. 'EMA_20', 'ATM_IV').
       - params: Dictionary of parameter arguments.
       - lookback_window: Number of historical bars required for warm-up.

    3. Technologies used and why:
       Standard Python class for immutable configuration.

    4. Key design and overall design of the class:
       Provides content-addressable parameter hashing for partition caching.
    """

    def __init__(self, name: str, params: Dict[str, Any], lookback_window: int):
        """
        1. The use of function:
           Initializes a FeatureDefinition instance.

        2. How does the specific function work:
           Stores feature name, copies params dictionary, and stores lookback window.

        3. Concepts used in the function:
           Parameter encapsulation, immutability.

        4. Places where this function is imported and used:
           Used by strategy definitions to declare required feature dependencies.

        5. Final output of the function, before and after:
           Before: Name, params, window. After: Configured FeatureDefinition.
        """
        self.name = name
        self.params = dict(params)
        self.lookback_window = lookback_window
