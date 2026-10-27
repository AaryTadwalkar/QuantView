"""
1. What this file does:
   Implements the Frozen Model Artifact and Strategy Inference Contract for QuantView
   (ENGINE §23, DATA §2.1, Task M5-10 / Gate G3).

2. Overall design:
   Enforces strict separation between offline research/training and online execution:
   - Frozen Model Contract: Immutable specification binding model hash, version, training data
     manifest hash, required features, label horizon, and inference resource budget.
   - Non-negotiable Invariant: Absolutely NO model training or weight updating inside backtest
     or live decision loops (raises NoInferenceTrainingAllowedError).
   - R1 Baselines: Standardized baseline schemas for Directional prediction, Regime classification,
     and Meta-Labeling trade gating.

3. Elements in the file:
   - NoInferenceTrainingAllowedError: Exception raised if training is attempted during inference.
   - R1BaselineType: Enum declaring baseline model categorization.
   - FrozenModelContract: Immutable Pydantic model defining the frozen model manifest.
   - ModelInferenceInterface: Abstract base contract for deterministic inference execution.
   - BaselineDecisionModel: Deterministic reference model adhering to the inference contract.

4. Final output of the file:
   - Type-safe, auditable frozen model contract and runtime inference interface.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class NoInferenceTrainingAllowedError(RuntimeError):
    """Raised when an engine component attempts to fit or modify model parameters during inference."""
    pass


class R1BaselineType(str, Enum):
    """
    1. The use of class:
       Categorizes Machine Learning R1 research baselines per ENGINE §23.

    2. What the class contains:
       - DIRECTION: Binary/multiclass price direction prediction.
       - REGIME: Market volatility / structural regime classification.
       - META_LABELING: Secondary bet-sizing and trade execution filter.

    3. Technologies used and why:
       Str-Enum for clean JSON serialization and manifest binding.

    4. Key design and overall design of the class:
       Differentiates baseline modeling archetypes across research and strategy layers.
    """
    DIRECTION = "DIRECTION"
    REGIME = "REGIME"
    META_LABELING = "META_LABELING"


class FrozenModelContract(BaseModel):
    """
    1. The use of class:
       Immutable manifest contract certifying a trained model artifact for strategy inference.

    2. What the class contains:
       - model_id: Unique string identifier for the model.
       - model_version: Semantic version string.
       - model_sha256: Cryptographic SHA-256 hash of the frozen model weights / binary.
       - training_manifest_hash: Hash of the training dataset manifest and split embargo.
       - features_required: List of feature IDs required by the model at decision time.
       - label_horizon_bars: Prediction horizon in bars (e.g. 5 bars).
       - r1_baseline_type: R1BaselineType enum.
       - resource_budget_ms: Maximum allowable execution latency per inference call.
       - as_of_rule: Strict causal availability policy ('CLOSED_BAR_ONLY').
       - created_at_utc: Timestamp string of model certification.
       - metadata: Additional audit or hyperparameter attributes.

    3. Technologies used and why:
       Pydantic v2 with frozen=True for strict immutable schema enforcement.

    4. Key design and overall design of the class:
       Enforces DATA §2.1 and ENGINE §23: model artifacts are completely decoupled from runtime training.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    model_version: str
    model_sha256: str
    training_manifest_hash: str
    features_required: List[str]
    label_horizon_bars: int = Field(gt=0)
    r1_baseline_type: R1BaselineType
    resource_budget_ms: float = Field(default=5.0, gt=0.0)
    as_of_rule: str = "CLOSED_BAR_ONLY"
    created_at_utc: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModelInferenceInterface(ABC):
    """
    1. The use of class:
       Abstract base class defining the mandatory inference protocol for strategies.

    2. What the class contains:
       - contract: Bound FrozenModelContract.
       - predict: Abstract method evaluating point-in-time features.
       - fit: Forbidden method raising NoInferenceTrainingAllowedError.

    3. Technologies used and why:
       Python ABC for compile-time contract enforcement.

    4. Key design and overall design of the class:
       Guarantees point-in-time inference without lookahead or data contamination.
    """

    def __init__(self, contract: FrozenModelContract):
        self.contract = contract

    @abstractmethod
    def predict(
        self,
        features: Dict[str, float],
        decision_time: int,
    ) -> Dict[str, Any]:
        """
        1. The use of function:
           Evaluates the frozen model using point-in-time feature values.

        2. How does the specific function work:
           Must validate feature inputs and return deterministic predictions within resource budget.

        3. Concepts used in the function:
           Point-in-time inference.

        4. Places where this function is imported and used:
           Used by strategy on_bar handlers.

        5. Final output of the function, before and after:
           Before: Features dictionary. After: Prediction result dictionary.
        """
        raise NotImplementedError

    def fit(self, *args, **kwargs) -> None:
        """
        1. The use of function:
           Strictly forbidden runtime training hook.

        2. How does the specific function work:
           Always raises NoInferenceTrainingAllowedError to prevent loop data leakage.

        3. Concepts used in the function:
           Anti-leakage guard per ENGINE §23.

        4. Places where this function is imported and used:
           Defensive runtime barrier.

        5. Final output of the function, before and after:
           Before: Any call. After: Raises NoInferenceTrainingAllowedError.
        """
        raise NoInferenceTrainingAllowedError(
            f"Model '{self.contract.model_id}' is a frozen artifact. "
            "No training or parameter fitting is permitted inside the execution decision loop."
        )


class BaselineDecisionModel(ModelInferenceInterface):
    """
    1. The use of class:
       Deterministic reference model implementing ModelInferenceInterface for R1 testing.

    2. What the class contains:
       - Linear scoring rule on normalized input features.
       - Prediction output dictionary with score, predicted_class, and confidence.

    3. Technologies used and why:
       Pure Python arithmetic for fast, reproducible testing.

    4. Key design and overall design of the class:
       Serves as test fixture and reference baseline for R1 directional and regime modeling.
    """

    def predict(
        self,
        features: Dict[str, float],
        decision_time: int,
    ) -> Dict[str, Any]:
        """Evaluates features and emits deterministic prediction."""
        for feat in self.contract.features_required:
            if feat not in features:
                raise ValueError(
                    f"Required feature '{feat}' missing for model '{self.contract.model_id}'."
                )

        # Reference scoring rule: sum of features
        score = sum(features[f] for f in self.contract.features_required)
        predicted_class = 1 if score > 0 else 0
        confidence = min(1.0, max(0.0, 0.5 + 0.1 * score))

        return {
            "model_id": self.contract.model_id,
            "decision_time": decision_time,
            "score": round(score, 4),
            "predicted_class": predicted_class,
            "confidence": round(confidence, 4),
        }
