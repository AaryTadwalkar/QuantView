"""
1. What this file does:
   Package export for QuantView market structure features (Stage 5 / Phase 5C).

2. Overall design:
   Re-exports core contracts for Swing High/Low Structure, BOS (Break of Structure),
   and CHoCH (Change of Character) deterministic evaluation.

3. Elements in the file:
   - MarketBias, StructuralEvent, BreakCriterion, SwingLevel, MarketStructureBar.
   - MarketStructureEngine, compute_market_structure, register_market_structure_feature.

4. Final output of the file:
   - Clean public API for packages.features.structure.
"""

from packages.features.structure.bos_choch import (
    BreakCriterion,
    MarketBias,
    MarketStructureBar,
    MarketStructureEngine,
    StructuralEvent,
    SwingLevel,
    compute_market_structure,
    register_market_structure_feature,
)

__all__ = [
    "MarketBias",
    "StructuralEvent",
    "BreakCriterion",
    "SwingLevel",
    "MarketStructureBar",
    "MarketStructureEngine",
    "compute_market_structure",
    "register_market_structure_feature",
]
