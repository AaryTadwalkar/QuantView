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
from packages.features.structure import (
    BreakCriterion,
    MarketBias,
    MarketStructureBar,
    MarketStructureEngine,
    StructuralEvent,
    SwingLevel,
    compute_market_structure,
    register_market_structure_feature,
)
from packages.features.calendar import (
    SessionHighWater,
    SessionProgress,
    compute_session_high_water,
    compute_session_progress,
    parse_utc_to_ist,
    register_high_water_feature,
    register_session_progress_feature,
)
from packages.features.chain import (
    SQL_CREATE_VIEW_RECONSTRUCTED_CHAIN,
    ChainRow,
    LazyChainProvider,
    ReconstructedOptionChain,
    StraddleResult,
    compute_atm_straddle,
    compute_delta_band_oi,
    compute_oi_roc,
    compute_pcr,
    get_atm_band_strikes,
    get_atm_strike,
    register_pcr_feature,
)
from packages.features.volatility import (
    ModelGreeksResult,
    SkewResult,
    black76_delta,
    black76_gamma,
    black76_price,
    black76_theta,
    black76_vega,
    compute_iv_skew_and_fly,
    compute_liquid_atm_band_greeks,
    register_liquid_atm_greeks_feature,
    register_skew_feature,
    solve_implied_volatility,
)
from packages.features.orderflow import (
    CandleDeltaResult,
    DepthImbalanceResult,
    compute_candle_volume_delta,
    compute_depth_imbalance,
    compute_series_candle_delta,
    register_candle_delta_feature,
    register_depth_imbalance_feature,
)
from packages.features.transforms import (
    HeikinAshiBar,
    NonTradableTransformError,
    RenkoBrick,
    compute_heikin_ashi,
    compute_renko_bricks,
    register_heikin_ashi_feature,
    register_renko_feature,
)
from packages.features.models import (
    BaselineDecisionModel,
    FrozenModelContract,
    ModelInferenceInterface,
    NoInferenceTrainingAllowedError,
    R1BaselineType,
)
from packages.features.runner import (
    IsolatedFeatureRunner,
    SubprocessFeatureResult,
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
    "MarketBias",
    "StructuralEvent",
    "BreakCriterion",
    "SwingLevel",
    "MarketStructureBar",
    "MarketStructureEngine",
    "compute_market_structure",
    "register_market_structure_feature",
    "SessionProgress",
    "SessionHighWater",
    "parse_utc_to_ist",
    "compute_session_progress",
    "compute_session_high_water",
    "register_session_progress_feature",
    "register_high_water_feature",
    "SQL_CREATE_VIEW_RECONSTRUCTED_CHAIN",
    "ChainRow",
    "ReconstructedOptionChain",
    "LazyChainProvider",
    "get_atm_strike",
    "get_atm_band_strikes",
    "StraddleResult",
    "compute_pcr",
    "compute_oi_roc",
    "compute_atm_straddle",
    "compute_delta_band_oi",
    "register_pcr_feature",
    "black76_price",
    "black76_delta",
    "black76_gamma",
    "black76_vega",
    "black76_theta",
    "solve_implied_volatility",
    "ModelGreeksResult",
    "compute_liquid_atm_band_greeks",
    "register_liquid_atm_greeks_feature",
    "SkewResult",
    "compute_iv_skew_and_fly",
    "register_skew_feature",
    "DepthImbalanceResult",
    "compute_depth_imbalance",
    "register_depth_imbalance_feature",
    "CandleDeltaResult",
    "compute_candle_volume_delta",
    "compute_series_candle_delta",
    "register_candle_delta_feature",
    "NonTradableTransformError",
    "HeikinAshiBar",
    "compute_heikin_ashi",
    "register_heikin_ashi_feature",
    "RenkoBrick",
    "compute_renko_bricks",
    "register_renko_feature",
    "FrozenModelContract",
    "ModelInferenceInterface",
    "BaselineDecisionModel",
    "R1BaselineType",
    "NoInferenceTrainingAllowedError",
    "SubprocessFeatureResult",
    "IsolatedFeatureRunner",
]
