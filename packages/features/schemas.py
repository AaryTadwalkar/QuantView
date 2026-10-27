"""
1. What this file does:
   Defines canonical data schemas, enums, metadata models, and deterministic parameter
   hashing contracts for QuantView point-in-time features (Stage 5 / Task M5-01).

2. Overall design:
   Enforces strict temporal metadata (memory classes, source tiers, repaint classes, and
   quality status) and cryptographic SHA-256 parameter hashing for every feature definition.
   Ensures feature identifiers are unique, reproducible, content-addressed, and immune to
   parameter order or representation variance.

3. Elements in the file:
   - SourceTier: Enum classifying feature dependency sources across the data hierarchy.
   - MemoryClass: Enum declaring whether a feature has finite sliding-window or infinite state memory.
   - RepaintClass: Enum declaring repaint safety (strictly NONE or CONFIRMED_LAG).
   - FeatureStatus: Enum specifying runtime operational quality states.
   - canonical_json_dumps: Helper function producing deterministic JSON strings.
   - compute_param_hash: Helper function calculating SHA-256 digests of parameter dictionaries.
   - FeatureDefinition: Immutable Pydantic model encapsulating feature identity, parameters, and metadata.

4. Final output of the file:
   - Type-checked, validated, immutable feature schemas and parameter hashing contracts.
"""

import hashlib
import json
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceTier(str, Enum):
    """
    1. The use of class:
       Categorizes the underlying source dependency tier for a given feature.

    2. What the class contains:
       - UNDERLYING_CANDLE: 1m or derived candles of the underlying index.
       - OPTION_CANDLE: 1m bars of discrete option strike contracts.
       - SNAPSHOT_CHAIN: Full option chain market depth and Greek snapshots.
       - MODEL_DERIVED: Features derived from analytical models (e.g., Black-76).
       - CALENDAR: Features derived from exchange schedule, time-of-day, and clock.

    3. Technologies used and why:
       Standard Python Enum inheriting from str for serialization compatibility.

    4. Key design and overall design of the class:
       Provides strict lineage classification to prevent unverified source claims.
    """
    UNDERLYING_CANDLE = "UNDERLYING_CANDLE"
    OPTION_CANDLE = "OPTION_CANDLE"
    SNAPSHOT_CHAIN = "SNAPSHOT_CHAIN"
    MODEL_DERIVED = "MODEL_DERIVED"
    CALENDAR = "CALENDAR"


class MemoryClass(str, Enum):
    """
    1. The use of class:
       Specifies the memory retention model of a feature's calculation recurrence.

    2. What the class contains:
       - FINITE: Feature depends strictly on a bounded sliding window of W bars.
       - INFINITE: Feature carries infinite autoregressive state (e.g. EMA, RMA).

    3. Technologies used and why:
       Str-Enum for partition caching and state checkpointing classification.

    4. Key design and overall design of the class:
       Allows caching and warming engines to know whether W bars suffice or state must be saved.
    """
    FINITE = "FINITE"
    INFINITE = "INFINITE"


class RepaintClass(str, Enum):
    """
    1. The use of class:
       Classifies the temporal repaint safety of a feature stream.

    2. What the class contains:
       - NONE: Strictly causal value; once computed for closed bar t, it never changes.
       - CONFIRMED_LAG: Structural pivot requiring W_R subsequent bars before becoming available.

    3. Technologies used and why:
       Str-Enum to guard against look-ahead bias and unconfirmed signal consumption.

    4. Key design and overall design of the class:
       Integrates with strategy context to ensure pivots are accessed only after confirmed_at.
    """
    NONE = "NONE"
    CONFIRMED_LAG = "CONFIRMED_LAG"


class FeatureStatus(str, Enum):
    """
    1. The use of class:
       Represents the runtime operational and quality status of a feature computation.

    2. What the class contains:
       - AVAILABLE: Valid, warmed-up, and causally available for trading decisions.
       - WARMING_UP: Computable but within historical warm-up window; signals suppressed.
       - STALE: Underlying source mark is older than allowed staleness threshold.
       - UNAVAILABLE: Source data missing, null, or strike not found; fails closed.
       - BLOCKED_QUARANTINED: Feature calculation explicitly blocked due to unverified data (e.g. VWAP).

    3. Technologies used and why:
       Str-Enum for machine-readable quality flagging.

    4. Key design and overall design of the class:
       Enforces data honesty by explicitly surfacing why a feature cannot be traded.
    """
    AVAILABLE = "AVAILABLE"
    WARMING_UP = "WARMING_UP"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED_QUARANTINED = "BLOCKED_QUARANTINED"


def canonical_json_dumps(data: Dict[str, Any]) -> str:
    """
    1. The use of function:
       Produces a strictly canonical, deterministic JSON string representation of a dictionary.

    2. How does the specific function work:
       Sorts all dictionary keys recursively and uses compact delimiters (',', ':') without whitespace.

    3. Concepts used in the function:
       Deterministic serialization, canonical hashing.

    4. Places where this function is imported and used:
       Used in compute_param_hash and FeatureDefinition model initialization.

    5. Final output of the function, before and after:
       Before: Arbitrary dictionary. After: Deterministic JSON string.
    """
    return json.dumps(data, sort_keys=True, separators=(',', ':'), default=str)


def compute_param_hash(params: Dict[str, Any]) -> str:
    """
    1. The use of function:
       Computes a deterministic cryptographic SHA-256 hash of a feature's parameter set.

    2. How does the specific function work:
       Serializes parameters via canonical_json_dumps and computes the SHA-256 hexadecimal digest.

    3. Concepts used in the function:
       Content-addressable hashing, SHA-256.

    4. Places where this function is imported and used:
       Used by FeatureDefinition to generate unique, reproducible feature identifiers.

    5. Final output of the function, before and after:
       Before: Parameter dictionary. After: 64-character SHA-256 hexadecimal string.
    """
    canonical_repr = canonical_json_dumps(params)
    return hashlib.sha256(canonical_repr.encode('utf-8')).hexdigest()


class FeatureDefinition(BaseModel):
    """
    1. The use of class:
       Immutable specification of a point-in-time quantitative feature.

    2. What the class contains:
       - name: Base name of the feature (e.g., 'EMA', 'RSI', 'BOS_CHOCH').
       - version: Semantic version string of the algorithm (default 'v1').
       - params: Hyperparameters dictionary.
       - lookback_window: Number of historical bars required for minimum computation.
       - warm_up_bars: Number of historical bars required for numerical float convergence.
       - memory_class: MemoryClass (FINITE or INFINITE).
       - source_tier: SourceTier identifying lake dependency.
       - repaint_class: RepaintClass (NONE or CONFIRMED_LAG).
       - output_schema: Dictionary mapping output variable names to expected data types.
       - description: Human-readable explanation.
       - param_hash: Deterministic SHA-256 hash of the parameters.
       - feature_id: Deterministic unique identifier: f"{name}_{version}_{param_hash[:8]}".

    3. Technologies used and why:
       Pydantic v2 BaseModel with frozen=True to enforce immutability and valid typing.

    4. Key design and overall design of the class:
       Central contract ensuring every feature request in QuantView is uniquely identified,
       content-addressed, and fully documented before execution.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., min_length=1, description="Base identifier of the feature (e.g. 'EMA').")
    version: str = Field(default="v1", min_length=1, description="Algorithm implementation version.")
    params: Dict[str, Any] = Field(default_factory=dict, description="Hyperparameters dictionary.")
    lookback_window: int = Field(default=1, ge=1, description="Minimum historical bars required.")
    warm_up_bars: int = Field(default=0, ge=0, description="Bars required for convergence.")
    memory_class: MemoryClass = Field(default=MemoryClass.FINITE, description="Finite or infinite memory.")
    source_tier: SourceTier = Field(default=SourceTier.UNDERLYING_CANDLE, description="Data dependency tier.")
    repaint_class: RepaintClass = Field(default=RepaintClass.NONE, description="Repaint safety class.")
    output_schema: Dict[str, str] = Field(default_factory=dict, description="Output names to data types.")
    description: str = Field(default="", description="Detailed human-readable summary.")

    @field_validator("name")
    @classmethod
    def validate_name_alphanumeric(cls, v: str) -> str:
        """
        1. The use of function:
           Validates that feature names contain only alphanumeric characters and underscores.

        2. How does the specific function work:
           Replaces underscores and tests if the remaining string is alphanumeric.

        3. Concepts used in the function:
           Input validation, safe identifier formatting.

        4. Places where this function is imported and used:
           Invoked automatically during FeatureDefinition validation.

        5. Final output of the function, before and after:
           Before: Raw name string. After: Validated name string or ValueError.
        """
        sanitized = v.replace("_", "")
        if not sanitized.isalnum():
            raise ValueError(f"Feature name '{v}' must be alphanumeric and underscore only.")
        return v

    @property
    def param_hash(self) -> str:
        """
        1. The use of function:
           Returns the full 64-character SHA-256 hexadecimal hash of the parameters.

        2. How does the specific function work:
           Calls compute_param_hash on the immutable params dictionary.

        3. Concepts used in the function:
           Property accessor, deterministic hashing.

        4. Places where this function is imported and used:
           Used by feature_id and caching layers.

        5. Final output of the function, before and after:
           Before: None. After: 64-character SHA-256 string.
        """
        return compute_param_hash(self.params)

    @property
    def feature_id(self) -> str:
        """
        1. The use of function:
           Constructs the deterministic unique identifier string for this feature configuration.

        2. How does the specific function work:
           Formats the name, version, and the first 8 characters of the param_hash.

        3. Concepts used in the function:
           Content-addressable identification (e.g., 'EMA_v1_3a8b1c4d').

        4. Places where this function is imported and used:
           Used as primary key in FeatureRegistry and StrategyContext feature queries.

        5. Final output of the function, before and after:
           Before: None. After: Formatted feature_id string.
        """
        return f"{self.name}_{self.version}_{self.param_hash[:8]}"
