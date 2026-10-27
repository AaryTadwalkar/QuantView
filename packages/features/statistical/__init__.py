"""
1. What this file does:
   Package export for QuantView statistical indicators and quarantined features (Stage 5 / Phase 5B).

2. Overall design:
   Re-exports core calculation routines for moving averages, oscillators, volatility bands,
   and the fail-closed Session VWAP guard.

3. Elements in the file:
   - compute_sma, compute_ema, compute_wilder_rma, compute_rsi, compute_macd,
     compute_atr, compute_natr, compute_bollinger_bands, compute_supertrend,
     compute_adx, compute_realized_volatility, compute_iv_rv_spread.
   - SessionVWAPQuarantinedError, SessionVWAPGuard, register_quarantined_vwap.
   - register_all_statistical_features.

4. Final output of the file:
   - Exported statistical calculation interfaces.
"""

from packages.features.statistical.indicators import (
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
)
from packages.features.statistical.vwap_guard import (
    SessionVWAPGuard,
    SessionVWAPQuarantinedError,
    register_quarantined_vwap,
)

# Alias for backwards compatibility if needed
SessionVWAPBlockedError = SessionVWAPQuarantinedError

__all__ = [
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
    "SessionVWAPBlockedError",
    "SessionVWAPGuard",
    "register_quarantined_vwap",
]
