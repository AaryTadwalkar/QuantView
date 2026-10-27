"""
1. What this file does:
   Implements the central FeatureRegistry singleton, registration decorators, JSON schema export,
   and causal anti-lookahead test verification interfaces (Prefix Invariance, Future Perturbation,
   and Availability Enforcement) for QuantView Stage 5 (Task M5-01).

2. Overall design:
   Provides a thread-safe registry for point-in-time features with deterministic parameter
   hashing, duplicate registration collision detection, and standardized metadata inspection.
   Bundles three executable causality validation protocols to verify that feature implementations
   are mathematically invariant to future truncations, future perturbations, and temporal access rules.

3. Elements in the file:
   - TemporalLeakageError, DuplicateFeatureRegistrationError, FeatureNotFoundError: Domain exceptions.
   - PrefixInvarianceViolationError, FuturePerturbationViolationError: Causality test exceptions.
   - FeatureRegistration: Named tuple holding definition, compute callable, and metadata.
   - FeatureRegistry: Thread-safe singleton registry class with registration and query methods.
   - register_feature: Parameterized decorator for registering feature compute callables.
   - verify_prefix_invariance: Helper validating truncation invariance across historical cuts.
   - verify_future_perturbation: Helper validating immunity to future series perturbations.
   - verify_availability_enforcement: Helper asserting fail-closed temporal access boundaries.

4. Final output of the file:
   - Thread-safe feature registry singleton, registration decorator, and causal test interfaces.
"""

import math
import threading
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence

from packages.domain import UtcEpochSec
from packages.features.schemas import (
    FeatureDefinition,
    MemoryClass,
    RepaintClass,
    SourceTier,
)


class TemporalLeakageError(Exception):
    """
    1. The use of class:
       Raised when an operation attempts to access feature data prior to its causal available_at timestamp.

    2. What the class contains:
       Standard Exception inheritance for temporal violations.

    3. Technologies used and why:
       Standard Python Exception for explicit, fail-closed temporal boundary enforcement.

    4. Key design and overall design of the class:
       Halts execution immediately upon detecting any forward look-ahead access attempt.
    """
    pass


class DuplicateFeatureRegistrationError(ValueError):
    """
    1. The use of class:
       Raised when attempting to register a feature whose feature_id collides with an existing registration.

    2. What the class contains:
       Standard ValueError inheritance.

    3. Technologies used and why:
       Standard Python ValueError for duplicate configuration detection.

    4. Key design and overall design of the class:
       Guarantees feature registry integrity by rejecting ambiguous or conflicting feature definitions.
    """
    pass


class FeatureNotFoundError(KeyError):
    """
    1. The use of class:
       Raised when querying a feature_id that has not been registered in the FeatureRegistry.

    2. What the class contains:
       Standard KeyError inheritance.

    3. Technologies used and why:
       Standard Python KeyError for dictionary lookup failure.

    4. Key design and overall design of the class:
       Provides fail-closed lookup semantics for strategy execution contexts.
    """
    pass


class PrefixInvarianceViolationError(AssertionError):
    """
    1. The use of class:
       Raised during automated testing when a feature violates the Prefix Invariance protocol.

    2. What the class contains:
       Standard AssertionError inheritance.

    3. Technologies used and why:
       AssertionError for automated pytest failure reporting.

    4. Key design and overall design of the class:
       Pinpoints the exact historical cut point where truncated calculation deviated from full series.
    """
    pass


class FuturePerturbationViolationError(AssertionError):
    """
    1. The use of class:
       Raised during automated testing when perturbing future bars leaks into past feature values.

    2. What the class contains:
       Standard AssertionError inheritance.

    3. Technologies used and why:
       AssertionError for automated pytest failure reporting.

    4. Key design and overall design of the class:
       Catches any accidental centering, smoothing, or forward window leakage.
    """
    pass


class FeatureRegistration(NamedTuple):
    """
    1. The use of class:
       Encapsulates a registered feature definition alongside its computation callable and metadata.

    2. What the class contains:
       - definition: Validated FeatureDefinition model.
       - compute_fn: Optional callable implementing the calculation.
       - metadata: Additional operational or documentation attributes.

    3. Technologies used and why:
       Python typing.NamedTuple for lightweight, immutable record storage.

    4. Key design and overall design of the class:
       Internal storage container inside the FeatureRegistry singleton.
    """
    definition: FeatureDefinition
    compute_fn: Optional[Callable]
    metadata: Dict[str, Any]


class FeatureRegistry:
    """
    1. The use of class:
       Central thread-safe catalog storing all registered quantitative feature definitions and solvers.

    2. What the class contains:
       - _lock: Reentrant lock for thread safety.
       - _features: Internal mapping from feature_id (str) to FeatureRegistration.

    3. Technologies used and why:
       Singleton pattern with threading.RLock to support concurrent multi-worker backtest environments.

    4. Key design and overall design of the class:
       Enforces content-addressable parameter uniqueness, duplicate collision detection, and
       JSON schema export for UI and documentation introspection.
    """
    _instance: Optional["FeatureRegistry"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "FeatureRegistry":
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._lock = threading.RLock()
                cls._instance._features = {}
            return cls._instance

    def register(
        self,
        definition: FeatureDefinition,
        compute_fn: Optional[Callable] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        1. The use of function:
           Registers a FeatureDefinition and optional compute callable into the registry.

        2. How does the specific function work:
           Acquires thread lock, checks for collisions under the deterministic feature_id.
           If the identical definition and compute_fn are already present, returns idempotently.
           If definitions or compute_fns conflict, raises DuplicateFeatureRegistrationError.

        3. Concepts used in the function:
           Thread safety, idempotency, duplicate collision detection.

        4. Places where this function is imported and used:
           Used by register_feature decorator, feature modules, and strategy initialization.

        5. Final output of the function, before and after:
           Before: Unregistered feature. After: Stored registration record; returns feature_id.
        """
        feature_id = definition.feature_id
        meta = dict(metadata) if metadata is not None else {}

        with self._lock:
            if feature_id in self._features:
                existing = self._features[feature_id]
                if existing.definition == definition and existing.compute_fn == compute_fn:
                    return feature_id
                raise DuplicateFeatureRegistrationError(
                    f"Duplicate feature_id collision detected for '{feature_id}'. "
                    f"Existing definition: {existing.definition}, New definition: {definition}."
                )

            self._features[feature_id] = FeatureRegistration(
                definition=definition,
                compute_fn=compute_fn,
                metadata=meta,
            )
            return feature_id

    def get(self, feature_id: str) -> FeatureRegistration:
        """
        1. The use of function:
           Retrieves a registered feature record by its unique feature_id.

        2. How does the specific function work:
           Acquires lock and looks up feature_id; raises FeatureNotFoundError if absent.

        3. Concepts used in the function:
           Fail-closed dictionary lookup.

        4. Places where this function is imported and used:
           Used by StrategyContext and feature computation runners.

        5. Final output of the function, before and after:
           Before: feature_id string. After: FeatureRegistration or FeatureNotFoundError.
        """
        with self._lock:
            if feature_id not in self._features:
                raise FeatureNotFoundError(
                    f"Feature '{feature_id}' is not registered in FeatureRegistry."
                )
            return self._features[feature_id]

    def has(self, feature_id: str) -> bool:
        """
        1. The use of function:
           Checks whether a feature_id is currently registered.

        2. How does the specific function work:
           Acquires lock and tests membership in internal features dictionary.

        3. Concepts used in the function:
           Membership testing.

        4. Places where this function is imported and used:
           Used during conditional registration checks and pre-flight validation.

        5. Final output of the function, before and after:
           Before: feature_id string. After: Boolean True/False.
        """
        with self._lock:
            return feature_id in self._features

    def list_features(self) -> List[FeatureDefinition]:
        """
        1. The use of function:
           Lists all currently registered FeatureDefinitions.

        2. How does the specific function work:
           Acquires lock and extracts definitions sorted alphabetically by feature_id.

        3. Concepts used in the function:
           Deterministic list extraction.

        4. Places where this function is imported and used:
           Used by UI APIs, CLI tools, and documentation generators.

        5. Final output of the function, before and after:
           Before: None. After: Sorted list of FeatureDefinition instances.
        """
        with self._lock:
            return [reg.definition for reg in sorted(self._features.values(), key=lambda r: r.definition.feature_id)]

    def export_json_schema(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Exports the complete catalog of registered features as a self-describing JSON Schema dictionary.

        2. How does the specific function work:
           Builds an OpenAPI / JSON-schema compatible dictionary of all registered features,
           their parameter models, schemas, memory classes, and source tiers.

        3. Concepts used in the function:
           Self-describing schema generation, API documentation parity.

        4. Places where this function is imported and used:
           Used by REST endpoints (`/api/v1/features/catalog`) and UI feature pickers.

        5. Final output of the function, before and after:
           Before: None. After: JSON Schema catalog dictionary.
        """
        with self._lock:
            catalog: Dict[str, Any] = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": "QuantView Feature Registry Catalog",
                "version": "1.0.0",
                "features": {},
            }
            for fid, reg in sorted(self._features.items()):
                defn = reg.definition
                catalog["features"][fid] = {
                    "name": defn.name,
                    "version": defn.version,
                    "feature_id": defn.feature_id,
                    "params": defn.params,
                    "lookback_window": defn.lookback_window,
                    "warm_up_bars": defn.warm_up_bars,
                    "memory_class": defn.memory_class.value,
                    "source_tier": defn.source_tier.value,
                    "repaint_class": defn.repaint_class.value,
                    "output_schema": defn.output_schema,
                    "description": defn.description,
                    "has_compute_fn": reg.compute_fn is not None,
                }
            return catalog

    def clear(self) -> None:
        """
        1. The use of function:
           Clears all registered features from the registry.

        2. How does the specific function work:
           Acquires lock and calls dict.clear().

        3. Concepts used in the function:
           State reset for isolated test execution.

        4. Places where this function is imported and used:
           Used by pytest test fixtures to ensure fresh registry state between tests.

        5. Final output of the function, before and after:
           Before: Active registry entries. After: Empty registry dictionary.
        """
        with self._lock:
            self._features.clear()


def register_feature(
    name: str,
    version: str = "v1",
    params: Optional[Dict[str, Any]] = None,
    lookback_window: int = 1,
    warm_up_bars: int = 0,
    memory_class: MemoryClass = MemoryClass.FINITE,
    source_tier: SourceTier = SourceTier.UNDERLYING_CANDLE,
    repaint_class: RepaintClass = RepaintClass.NONE,
    output_schema: Optional[Dict[str, str]] = None,
    description: str = "",
) -> Callable[[Callable], Callable]:
    """
    1. The use of function:
       Parameterized decorator that registers a feature computation callable into FeatureRegistry.

    2. How does the specific function work:
       Constructs a FeatureDefinition from the provided arguments, registers it with the decorated
       callable upon function definition, and returns the original callable intact.

    3. Concepts used in the function:
       Python decorator pattern, declarative feature registration.

    4. Places where this function is imported and used:
       Used across feature modules (`packages/features/statistical/`, etc.) to register indicator solvers.

    5. Final output of the function, before and after:
       Before: Raw computation function. After: Decorated function registered in FeatureRegistry.
    """
    def decorator(fn: Callable) -> Callable:
        defn = FeatureDefinition(
            name=name,
            version=version,
            params=params or {},
            lookback_window=lookback_window,
            warm_up_bars=warm_up_bars,
            memory_class=memory_class,
            source_tier=source_tier,
            repaint_class=repaint_class,
            output_schema=output_schema or {},
            description=description or (fn.__doc__ or "").strip(),
        )
        registry = FeatureRegistry()
        registry.register(definition=defn, compute_fn=fn)
        fn.feature_definition = defn  # type: ignore[attr-defined]
        return fn

    return decorator


def verify_prefix_invariance(
    compute_fn: Callable[[Sequence[float]], Sequence[float]],
    series: Sequence[float],
    cut_points: Sequence[int],
    tol: float = 1e-8,
) -> bool:
    """
    1. The use of function:
       Verifies Protocol 1: Prefix Invariance (ENGINE §3.3, Task M5-01).

    2. How does the specific function work:
       For each cut point t in cut_points:
         1. Evaluates compute_fn over the truncated series slice series[:t + 1], taking the final output value.
         2. Evaluates compute_fn over the full series, taking the output value at index t.
         3. Compares the two values; if difference > tol, raises PrefixInvarianceViolationError.
       Returns True if all cut points match.

    3. Concepts used in the function:
       Causality verification, prefix invariance: F([0..t])_t == F([0..T])_t.

    4. Places where this function is imported and used:
       Used by unit tests to verify that indicators do not leak future information.

    5. Final output of the function, before and after:
       Before: Compute function and series. After: True or PrefixInvarianceViolationError.
    """
    full_output = compute_fn(series)
    n_full = len(series)

    for t in cut_points:
        if t < 0 or t >= n_full:
            raise ValueError(f"Cut point {t} is outside valid series range [0, {n_full - 1}].")

        truncated_slice = series[:t + 1]
        truncated_output = compute_fn(truncated_slice)

        v_trunc = truncated_output[-1]
        v_full = full_output[t]

        # Handle NaN matching
        if math.isnan(v_trunc) and math.isnan(v_full):
            continue

        if math.isnan(v_trunc) != math.isnan(v_full):
            raise PrefixInvarianceViolationError(
                f"Prefix invariance violated at cut point {t}: "
                f"truncated is {v_trunc} but full is {v_full}."
            )

        diff = abs(v_trunc - v_full)
        if diff > tol:
            raise PrefixInvarianceViolationError(
                f"Prefix invariance violated at cut point {t}: "
                f"truncated {v_trunc} != full {v_full} (diff: {diff:.6e} > tol {tol:.6e})."
            )

    return True


def verify_future_perturbation(
    compute_fn: Callable[[Sequence[float]], Sequence[float]],
    series: Sequence[float],
    t_decision: int,
    perturbation_val: float = 999999.0,
    tol: float = 1e-8,
) -> bool:
    """
    1. The use of function:
       Verifies Protocol 2: Future Perturbation Invariance (ENGINE §3.3, Task M5-01).

    2. How does the specific function work:
       1. Computes feature output on the original series.
       2. Creates a perturbed series where all values strictly after t_decision are perturbed.
       3. Computes feature output on the perturbed series.
       4. Asserts that for all indices i <= t_decision, outputs remain identical within tol.
       If any value up to t_decision changed, raises FuturePerturbationViolationError.

    3. Concepts used in the function:
       Anti-lookahead testing, future data perturbation.

    4. Places where this function is imported and used:
       Used in test suites to catch centered moving averages or forward-looking smoothing filters.

    5. Final output of the function, before and after:
       Before: Compute function and series. After: True or FuturePerturbationViolationError.
    """
    n = len(series)
    if t_decision < 0 or t_decision >= n:
        raise ValueError(f"t_decision {t_decision} is outside valid series range [0, {n - 1}].")

    original_output = compute_fn(series)

    perturbed_series = list(series)
    for s in range(t_decision + 1, n):
        perturbed_series[s] += perturbation_val

    perturbed_output = compute_fn(perturbed_series)

    for i in range(t_decision + 1):
        v_orig = original_output[i]
        v_pert = perturbed_output[i]

        if math.isnan(v_orig) and math.isnan(v_pert):
            continue

        if math.isnan(v_orig) != math.isnan(v_pert):
            raise FuturePerturbationViolationError(
                f"Future perturbation leakage detected at index {i} <= decision_time {t_decision}: "
                f"original is {v_orig} but perturbed is {v_pert}."
            )

        diff = abs(v_orig - v_pert)
        if diff > tol:
            raise FuturePerturbationViolationError(
                f"Future perturbation leakage detected at index {i} <= decision_time {t_decision}: "
                f"original {v_orig} != perturbed {v_pert} (diff: {diff:.6e} > tol {tol:.6e})."
            )

    return True


def verify_availability_enforcement(
    access_time: UtcEpochSec,
    available_at: UtcEpochSec,
) -> bool:
    """
    1. The use of function:
       Verifies Protocol 3: Availability Enforcement (ENGINE §3.3, ADR-008, Task M5-01).

    2. How does the specific function work:
       Compares access_time against available_at. If access_time < available_at, raises TemporalLeakageError.
       Returns True if access_time >= available_at.

    3. Concepts used in the function:
       Causal temporal boundary check: available_at <= decision_time.

    4. Places where this function is imported and used:
       Used in StrategyContext and feature query dispatchers.

    5. Final output of the function, before and after:
       Before: access_time and available_at. After: True or TemporalLeakageError.
    """
    if access_time < available_at:
        raise TemporalLeakageError(
            f"Temporal leakage detected: query at access_time {access_time} "
            f"prior to causal available_at {available_at}."
        )
    return True
