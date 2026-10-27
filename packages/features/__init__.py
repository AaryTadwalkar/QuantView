"""
1. What this file does:
   Canonical top-level package export for QuantView point-in-time features, registry,
   schemas, and causal verification contracts (Stage 5 / Task M5-01).

2. Overall design:
   Re-exports the core metadata models, deterministic parameter hashing utilities,
   FeatureRegistry singleton, and anti-lookahead verification protocols.
   The fundamental invariant enforced throughout this package is:
       feature.available_at <= decision_time
   Features never access future bars, unclosed candles, or future option chain snapshots.

3. Elements in the file:
   - SourceTier, MemoryClass, RepaintClass, FeatureStatus: Core temporal and data tier enums.
   - FeatureDefinition: Immutable Pydantic model with deterministic SHA-256 parameter hashing.
   - compute_param_hash: Utility producing content-addressable parameter hashes.
   - FeatureRegistry, FeatureRegistration, register_feature: Thread-safe registry and decorator.
   - TemporalLeakageError, DuplicateFeatureRegistrationError, FeatureNotFoundError: Registry exceptions.
   - PrefixInvarianceViolationError, FuturePerturbationViolationError: Causality test exceptions.
   - verify_prefix_invariance, verify_future_perturbation, verify_availability_enforcement: Causality test helpers.

4. Final output of the file:
   - Clean public API for packages.features.
"""

from packages.features.schemas import (
    FeatureDefinition,
    FeatureStatus,
    MemoryClass,
    RepaintClass,
    SourceTier,
    canonical_json_dumps,
    compute_param_hash,
)
from packages.features.registry import (
    DuplicateFeatureRegistrationError,
    FeatureNotFoundError,
    FeatureRegistration,
    FeatureRegistry,
    FuturePerturbationViolationError,
    PrefixInvarianceViolationError,
    TemporalLeakageError,
    register_feature,
    verify_availability_enforcement,
    verify_future_perturbation,
    verify_prefix_invariance,
)
from packages.features.statistical import (
    SessionVWAPGuard,
    SessionVWAPQuarantinedError,
    compute_adx,
    compute_atr,
    compute_bollinger_bands,
    compute_ema,
    compute_iv_rv_spread,
    compute_macd,
    compute_natr,
    compute_realized_volatility,
    compute_rsi,
    compute_sma,
    compute_supertrend,
    compute_wilder_rma,
    register_all_statistical_features,
    register_quarantined_vwap,
)

__all__ = [
    "SourceTier",
    "MemoryClass",
    "RepaintClass",
    "FeatureStatus",
    "canonical_json_dumps",
    "compute_param_hash",
    "FeatureDefinition",
    "FeatureRegistration",
    "FeatureRegistry",
    "register_feature",
    "TemporalLeakageError",
    "DuplicateFeatureRegistrationError",
    "FeatureNotFoundError",
    "PrefixInvarianceViolationError",
    "FuturePerturbationViolationError",
    "verify_prefix_invariance",
    "verify_future_perturbation",
    "verify_availability_enforcement",
    "compute_sma",
    "compute_ema",
    "compute_wilder_rma",
    "compute_rsi",
    "compute_macd",
    "compute_atr",
    "compute_natr",
    "compute_bollinger_bands",
    "compute_supertrend",
    "compute_adx",
    "compute_realized_volatility",
    "compute_iv_rv_spread",
    "register_all_statistical_features",
    "SessionVWAPQuarantinedError",
    "SessionVWAPGuard",
    "register_quarantined_vwap",
]
