"""
1. What this file does:
   Package exports for QuantView machine learning models and frozen inference contracts.

2. Overall design:
   Re-exports immutable model contracts, baseline enums, and inference interfaces per ENGINE §23.

3. Elements in the file:
   - FrozenModelContract, ModelInferenceInterface, BaselineDecisionModel.
   - R1BaselineType, NoInferenceTrainingAllowedError.

4. Final output of the file:
   - Clean public API for packages.features.models.
"""

from packages.features.models.frozen_contract import (
    BaselineDecisionModel,
    FrozenModelContract,
    ModelInferenceInterface,
    NoInferenceTrainingAllowedError,
    R1BaselineType,
)

__all__ = [
    "FrozenModelContract",
    "ModelInferenceInterface",
    "BaselineDecisionModel",
    "R1BaselineType",
    "NoInferenceTrainingAllowedError",
]
