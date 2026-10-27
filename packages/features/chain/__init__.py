"""
1. What this file does:
   Package exports for QuantView reconstructed option chain and derived options features.

2. Overall design:
   Re-exports lazy chain query providers, ChainRow models, ATM strike band extractors,
   and derived features (PCR, OI ROC, ATM Straddle, Delta-band OI).

3. Elements in the file:
   - ChainRow, ReconstructedOptionChain, LazyChainProvider.
   - get_atm_strike, get_atm_band_strikes, SQL_CREATE_VIEW_RECONSTRUCTED_CHAIN.
   - StraddleResult, compute_pcr, compute_oi_roc, compute_atm_straddle, compute_delta_band_oi, register_pcr_feature.

4. Final output of the file:
   - Clean public API for packages.features.chain.
"""

from packages.features.chain.derived import (
    StraddleResult,
    compute_atm_straddle,
    compute_delta_band_oi,
    compute_oi_roc,
    compute_pcr,
    register_pcr_feature,
)
from packages.features.chain.lazy_chain import (
    SQL_CREATE_VIEW_RECONSTRUCTED_CHAIN,
    ChainRow,
    LazyChainProvider,
    ReconstructedOptionChain,
    get_atm_band_strikes,
    get_atm_strike,
)

__all__ = [
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
]
