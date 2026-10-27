"""
1. What this file does:
   Executes comprehensive unit testing for QuantView Feature Registry, Schemas, Parameter Hashing,
   and Anti-Lookahead Causal Test Protocols (Milestone M5-01 / Gate G3).

2. Overall design:
   Validates Pydantic schema constraints, immutable feature definitions, content-addressed SHA-256
   parameter hashing, duplicate registration collision safety, JSON schema catalog export, and the
   three mandatory causality verification protocols (Prefix Invariance, Future Perturbation,
   and Availability Enforcement).

3. Elements in the file:
   - TestFeatureDefinition: Validates Pydantic constraints, immutability, and deterministic hashing.
   - TestFeatureRegistry: Validates singleton behavior, collision detection, and JSON schema export.
   - TestCausalityProtocols: Validates Prefix Invariance, Future Perturbation, and Temporal Leakage detection.

4. Final output of the file:
   - Automated test suite validating Task M5-01 under `@pytest.mark.gate_g3`.
"""

import pytest
from pydantic import ValidationError

from packages.domain import UtcEpochSec
from packages.features import (
    DuplicateFeatureRegistrationError,
    FeatureDefinition,
    FeatureNotFoundError,
    FeatureRegistry,
    FeatureStatus,
    FuturePerturbationViolationError,
    MemoryClass,
    PrefixInvarianceViolationError,
    RepaintClass,
    SourceTier,
    TemporalLeakageError,
    compute_param_hash,
    register_feature,
    verify_availability_enforcement,
    verify_future_perturbation,
    verify_prefix_invariance,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """
    1. The use of function:
       Pytest fixture ensuring a clean, isolated FeatureRegistry singleton state before and after each test.

    2. How does the specific function work:
       Calls FeatureRegistry().clear() before yield and after test execution.

    3. Concepts used in the function:
       Test isolation, fixture cleanup.

    4. Places where this function is imported and used:
       Executed automatically for all tests in test_feature_registry.py.

    5. Final output of the function, before and after:
       Before: Any previous state. After: Clean empty registry.
    """
    registry = FeatureRegistry()
    registry.clear()
    yield
    registry.clear()


@pytest.mark.gate_g3
class TestFeatureDefinition:
    """
    1. The use of class:
       Unit tests for FeatureDefinition Pydantic model validation and deterministic hashing.

    2. What the class contains:
       - test_valid_definition: Verifies creation and default fields.
       - test_deterministic_param_hashing: Asserts key-order invariance in parameter hashes.
       - test_unique_hash_for_distinct_params: Asserts different parameters yield distinct hashes.
       - test_pydantic_validations: Asserts invalid windows, names, and immutability raise errors.

    3. Technologies used and why:
       pytest, pydantic.ValidationError checks for strict schema enforcement.

    4. Key design and overall design of the class:
       Verifies that every feature definition in QuantView is uniquely and immutably identified.
    """

    def test_valid_definition(self):
        """
        1. The use of function:
           Verifies standard FeatureDefinition construction with explicit metadata.

        2. How does the specific function work:
           Constructs FeatureDefinition and asserts property values.

        3. Concepts used in the function:
           Pydantic field validation, property checking.

        4. Places where this function is imported and used:
           Part of TestFeatureDefinition test suite.

        5. Final output of the function, before and after:
           Before: Uninstantiated model. After: Verified FeatureDefinition instance.
        """
        defn = FeatureDefinition(
            name="EMA",
            version="v1",
            params={"n": 20},
            lookback_window=20,
            warm_up_bars=60,
            memory_class=MemoryClass.INFINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            repaint_class=RepaintClass.NONE,
            output_schema={"ema": "float64", "is_warmed_up": "bool"},
            description="20-period Exponential Moving Average",
        )
        assert defn.name == "EMA"
        assert defn.version == "v1"
        assert defn.lookback_window == 20
        assert defn.warm_up_bars == 60
        assert defn.memory_class == MemoryClass.INFINITE
        assert defn.source_tier == SourceTier.UNDERLYING_CANDLE
        assert defn.repaint_class == RepaintClass.NONE
        assert len(defn.param_hash) == 64
        assert defn.feature_id.startswith("EMA_v1_")
        assert len(defn.feature_id) == len("EMA_v1_") + 8

    def test_deterministic_param_hashing(self):
        """
        1. The use of function:
           Verifies that dictionaries with identical keys and values inserted in different orders
           produce identical SHA-256 hashes and identical feature_id strings.

        2. How does the specific function work:
           Creates two dicts with reverse key ordering, computes hashes, and asserts exact equality.

        3. Concepts used in the function:
           Canonical JSON sorting, cryptographic SHA-256 determinism.

        4. Places where this function is imported and used:
           Part of TestFeatureDefinition test suite.

        5. Final output of the function, before and after:
           Before: Dicts in different order. After: Identical hashes verified.
        """
        params_a = {"fast": 12, "slow": 26, "signal": 9}
        params_b = {"signal": 9, "slow": 26, "fast": 12}

        hash_a = compute_param_hash(params_a)
        hash_b = compute_param_hash(params_b)
        assert hash_a == hash_b

        defn_a = FeatureDefinition(name="MACD", params=params_a, lookback_window=35)
        defn_b = FeatureDefinition(name="MACD", params=params_b, lookback_window=35)
        assert defn_a.feature_id == defn_b.feature_id

    def test_unique_hash_for_distinct_params(self):
        """
        1. The use of function:
           Verifies that different parameters generate distinct SHA-256 hashes and distinct feature_ids.

        2. How does the specific function work:
           Compares FeatureDefinitions for EMA(20) vs EMA(50).

        3. Concepts used in the function:
           Hash collision resistance.

        4. Places where this function is imported and used:
           Part of TestFeatureDefinition test suite.

        5. Final output of the function, before and after:
           Before: Two different parameter sets. After: Unequal feature_ids verified.
        """
        defn_20 = FeatureDefinition(name="EMA", params={"n": 20}, lookback_window=20)
        defn_50 = FeatureDefinition(name="EMA", params={"n": 50}, lookback_window=50)
        assert defn_20.param_hash != defn_50.param_hash
        assert defn_20.feature_id != defn_50.feature_id

    def test_pydantic_validations(self):
        """
        1. The use of function:
           Verifies that invalid names, lookback windows, and mutation attempts fail closed.

        2. How does the specific function work:
           Tests that non-alphanumeric names, lookback_window < 1, and negative warm_up_bars raise
           ValidationError, and that mutating an immutable field raises ValidationError.

        3. Concepts used in the function:
           Fail-closed validation, frozen model protection.

        4. Places where this function is imported and used:
           Part of TestFeatureDefinition test suite.

        5. Final output of the function, before and after:
           Before: Invalid inputs. After: ValidationErrors asserted.
        """
        # Lookback window < 1
        with pytest.raises(ValidationError):
            FeatureDefinition(name="EMA", lookback_window=0)

        # Negative warm_up_bars
        with pytest.raises(ValidationError):
            FeatureDefinition(name="EMA", lookback_window=10, warm_up_bars=-1)

        # Invalid name characters
        with pytest.raises(ValidationError):
            FeatureDefinition(name="EMA-20!", lookback_window=10)

        # Immutability check (frozen=True)
        defn = FeatureDefinition(name="EMA", params={"n": 20}, lookback_window=20)
        with pytest.raises(ValidationError):
            defn.name = "SMA"  # type: ignore[misc]


@pytest.mark.gate_g3
class TestFeatureRegistry:
    """
    1. The use of class:
       Unit tests for FeatureRegistry singleton, registration decorator, collision guards, and schema export.

    2. What the class contains:
       - test_singleton_identity: Asserts that multiple instantiations share one instance.
       - test_registration_and_lookup: Verifies register, has, get, and list_features.
       - test_idempotent_reregistration: Verifies identical re-registration succeeds silently.
       - test_duplicate_collision_raises_error: Asserts conflicting definitions raise DuplicateFeatureRegistrationError.
       - test_missing_feature_raises_not_found: Asserts unregistered queries raise FeatureNotFoundError.
       - test_register_feature_decorator: Verifies the parameterized registration decorator.
       - test_export_json_schema: Verifies export_json_schema structure and fields.

    3. Technologies used and why:
       pytest unit tests verifying registry behavior under thread-safe singleton pattern.

    4. Key design and overall design of the class:
       Guarantees feature catalog integrity and fail-closed resolution.
    """

    def test_singleton_identity(self):
        """
        1. The use of function:
           Assures that FeatureRegistry enforces the singleton pattern across separate calls.

        2. How does the specific function work:
           Instantiates two registry references and asserts identity (reg1 is reg2).

        3. Concepts used in the function:
           Singleton pattern.

        4. Places where this function is imported and used:
           Part of TestFeatureRegistry test suite.

        5. Final output of the function, before and after:
           Before: Two constructor calls. After: Asserted object identity.
        """
        reg1 = FeatureRegistry()
        reg2 = FeatureRegistry()
        assert reg1 is reg2

    def test_registration_and_lookup(self):
        """
        1. The use of function:
           Verifies standard feature registration, membership checking, and record retrieval.

        2. How does the specific function work:
           Registers an RSI definition, checks has(), calls get(), and verifies listed features.

        3. Concepts used in the function:
           Catalog management.

        4. Places where this function is imported and used:
           Part of TestFeatureRegistry test suite.

        5. Final output of the function, before and after:
           Before: Empty registry. After: Verified registration record.
        """
        registry = FeatureRegistry()
        defn = FeatureDefinition(
            name="RSI",
            params={"n": 14},
            lookback_window=14,
            warm_up_bars=70,
            memory_class=MemoryClass.INFINITE,
        )

        def mock_rsi(series):
            return series

        fid = registry.register(defn, compute_fn=mock_rsi)
        assert fid == defn.feature_id
        assert registry.has(fid) is True

        rec = registry.get(fid)
        assert rec.definition == defn
        assert rec.compute_fn is mock_rsi

        listed = registry.list_features()
        assert len(listed) == 1
        assert listed[0] == defn

    def test_idempotent_reregistration(self):
        """
        1. The use of function:
           Verifies that registering the exact same definition and compute_fn twice is idempotent.

        2. How does the specific function work:
           Calls register twice with identical arguments and asserts the returned feature_id matches.

        3. Concepts used in the function:
           Idempotency.

        4. Places where this function is imported and used:
           Part of TestFeatureRegistry test suite.

        5. Final output of the function, before and after:
           Before: One registration. After: Duplicate call returns feature_id without error.
        """
        registry = FeatureRegistry()
        defn = FeatureDefinition(name="ATR", params={"n": 14}, lookback_window=14)

        def mock_atr(h, l, c):
            return c

        fid1 = registry.register(defn, compute_fn=mock_atr)
        fid2 = registry.register(defn, compute_fn=mock_atr)
        assert fid1 == fid2

    def test_duplicate_collision_raises_error(self):
        """
        1. The use of function:
           Verifies that registering a conflicting definition or function with the same feature_id
           raises DuplicateFeatureRegistrationError.

        2. How does the specific function work:
           Registers defn with compute_fn_1, then attempts to register defn with compute_fn_2.

        3. Concepts used in the function:
           Collision detection, fail-closed safety.

        4. Places where this function is imported and used:
           Part of TestFeatureRegistry test suite.

        5. Final output of the function, before and after:
           Before: Initial registration. After: DuplicateFeatureRegistrationError asserted.
        """
        registry = FeatureRegistry()
        defn = FeatureDefinition(name="BB", params={"n": 20, "k": 2.0}, lookback_window=20)

        def fn_one(series):
            return series

        def fn_two(series):
            return [x * 2 for x in series]

        registry.register(defn, compute_fn=fn_one)

        with pytest.raises(DuplicateFeatureRegistrationError):
            registry.register(defn, compute_fn=fn_two)

    def test_missing_feature_raises_not_found(self):
        """
        1. The use of function:
           Verifies that querying a non-existent feature_id raises FeatureNotFoundError.

        2. How does the specific function work:
           Calls registry.get('NON_EXISTENT') and catches FeatureNotFoundError.

        3. Concepts used in the function:
           Fail-closed lookup.

        4. Places where this function is imported and used:
           Part of TestFeatureRegistry test suite.

        5. Final output of the function, before and after:
           Before: Unknown key. After: FeatureNotFoundError asserted.
        """
        registry = FeatureRegistry()
        with pytest.raises(FeatureNotFoundError):
            registry.get("UNKNOWN_FEATURE_ID")

    def test_register_feature_decorator(self):
        """
        1. The use of function:
           Verifies that the @register_feature decorator properly registers a callable into FeatureRegistry.

        2. How does the specific function work:
           Applies @register_feature to a dummy indicator function and verifies its registry entry.

        3. Concepts used in the function:
           Decorator pattern.

        4. Places where this function is imported and used:
           Part of TestFeatureRegistry test suite.

        5. Final output of the function, before and after:
           Before: Undecorated function. After: Decorated function verified in registry.
        """
        @register_feature(
            name="Supertrend",
            version="v1",
            params={"n": 10, "multiplier": 3.0},
            lookback_window=10,
            warm_up_bars=40,
            memory_class=MemoryClass.INFINITE,
            source_tier=SourceTier.UNDERLYING_CANDLE,
            output_schema={"supertrend": "float64", "direction": "int8"},
            description="Supertrend indicator implementation",
        )
        def compute_supertrend(h, l, c):
            return c

        registry = FeatureRegistry()
        defn = compute_supertrend.feature_definition
        assert registry.has(defn.feature_id) is True

        rec = registry.get(defn.feature_id)
        assert rec.definition.name == "Supertrend"
        assert rec.compute_fn is compute_supertrend

    def test_export_json_schema(self):
        """
        1. The use of function:
           Verifies that export_json_schema generates a self-describing JSON Schema catalog.

        2. How does the specific function work:
           Registers two features, exports schema, and asserts catalog contents.

        3. Concepts used in the function:
           JSON Schema specification.

        4. Places where this function is imported and used:
           Part of TestFeatureRegistry test suite.

        5. Final output of the function, before and after:
           Before: Unexported catalog. After: Validated JSON Schema dictionary.
        """
        registry = FeatureRegistry()
        registry.register(FeatureDefinition(name="EMA", params={"n": 20}, lookback_window=20))
        registry.register(FeatureDefinition(name="RSI", params={"n": 14}, lookback_window=14))

        schema = registry.export_json_schema()
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["title"] == "QuantView Feature Registry Catalog"
        assert len(schema["features"]) == 2

        for fid, item in schema["features"].items():
            assert "name" in item
            assert "feature_id" in item
            assert "params" in item
            assert "memory_class" in item
            assert "source_tier" in item


@pytest.mark.gate_g3
class TestCausalityProtocols:
    """
    1. The use of class:
       Unit tests validating the three mandatory causality verification protocols (Task M5-01).

    2. What the class contains:
       - test_prefix_invariance_passes_on_causal: Asserts causal SMA passes Prefix Invariance.
       - test_prefix_invariance_fails_on_lookahead: Asserts lookahead SMA fails Prefix Invariance.
       - test_future_perturbation_passes_on_causal: Asserts causal SMA passes Future Perturbation.
       - test_future_perturbation_fails_on_lookahead: Asserts lookahead SMA fails Future Perturbation.
       - test_availability_enforcement: Verifies temporal leakage check raises TemporalLeakageError.

    3. Technologies used and why:
       pytest, custom causality protocols verifying anti-lookahead invariants.

    4. Key design and overall design of the class:
       Proves that QuantView causality test harnesses reliably detect forward leakage.
    """

    def test_prefix_invariance_passes_on_causal(self):
        """
        1. The use of function:
           Verifies that a strictly causal cumulative average passes the Prefix Invariance protocol.

        2. How does the specific function work:
           Implements causal cumulative sum / count and runs verify_prefix_invariance across cuts.

        3. Concepts used in the function:
           Prefix Invariance: F([0..t])_t == F([0..T])_t.

        4. Places where this function is imported and used:
           Part of TestCausalityProtocols test suite.

        5. Final output of the function, before and after:
           Before: Series and causal function. After: Passes with True.
        """
        series = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0]

        def causal_cum_avg(s):
            out = []
            cum = 0.0
            for i, val in enumerate(s):
                cum += val
                out.append(cum / (i + 1))
            return out

        assert verify_prefix_invariance(causal_cum_avg, series, cut_points=[1, 3, 5, 7]) is True

    def test_prefix_invariance_fails_on_lookahead(self):
        """
        1. The use of function:
           Verifies that a non-causal function (e.g. referencing series[-1]) fails Prefix Invariance.

        2. How does the specific function work:
           Implements non-causal function using total series end, asserts PrefixInvarianceViolationError.

        3. Concepts used in the function:
           Anti-lookahead leak detection.

        4. Places where this function is imported and used:
           Part of TestCausalityProtocols test suite.

        5. Final output of the function, before and after:
           Before: Leaking function. After: PrefixInvarianceViolationError asserted.
        """
        series = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0]

        def leaking_fn(s):
            # Leaks future by using the last element of the entire passed series at every step
            return [x + s[-1] for x in s]

        with pytest.raises(PrefixInvarianceViolationError):
            verify_prefix_invariance(leaking_fn, series, cut_points=[2, 4])

    def test_future_perturbation_passes_on_causal(self):
        """
        1. The use of function:
           Verifies that a causal indicator passes Future Perturbation Invariance.

        2. How does the specific function work:
           Tests causal 2-bar lag difference against verify_future_perturbation.

        3. Concepts used in the function:
           Future Perturbation Invariance.

        4. Places where this function is imported and used:
           Part of TestCausalityProtocols test suite.

        5. Final output of the function, before and after:
           Before: Causal lag difference. After: Passes with True.
        """
        series = [100.0, 102.0, 101.0, 105.0, 107.0, 106.0, 108.0, 110.0]

        def causal_diff(s):
            out = [0.0]
            for i in range(1, len(s)):
                out.append(s[i] - s[i - 1])
            return out

        assert verify_future_perturbation(causal_diff, series, t_decision=4) is True

    def test_future_perturbation_fails_on_lookahead(self):
        """
        1. The use of function:
           Verifies that a forward-looking function (e.g. centered moving average) fails Future Perturbation.

        2. How does the specific function work:
           Implements forward-looking filter and asserts FuturePerturbationViolationError.

        3. Concepts used in the function:
           Future Perturbation leak detection.

        4. Places where this function is imported and used:
           Part of TestCausalityProtocols test suite.

        5. Final output of the function, before and after:
           Before: Centered filter. After: FuturePerturbationViolationError asserted.
        """
        series = [100.0, 102.0, 101.0, 105.0, 107.0, 106.0, 108.0, 110.0]

        def centered_ma(s):
            # Centered 3-bar moving average leaks s[i+1] into output[i]
            out = []
            for i in range(len(s)):
                window = s[max(0, i - 1):min(len(s), i + 2)]
                out.append(sum(window) / len(window))
            return out

        with pytest.raises(FuturePerturbationViolationError):
            verify_future_perturbation(centered_ma, series, t_decision=4)

    def test_availability_enforcement(self):
        """
        1. The use of function:
           Verifies that attempting to access a feature prior to available_at raises TemporalLeakageError.

        2. How does the specific function work:
           Tests access_time < available_at (raises TemporalLeakageError) and access_time >= available_at (returns True).

        3. Concepts used in the function:
           Causal temporal boundary check: available_at <= decision_time.

        4. Places where this function is imported and used:
           Part of TestCausalityProtocols test suite.

        5. Final output of the function, before and after:
           Before: Timestamps. After: Temporal boundary compliance verified.
        """
        bar_available_at = UtcEpochSec(1735703760)  # e.g. 09:16:00 IST

        # Valid access: exactly at available_at
        assert verify_availability_enforcement(UtcEpochSec(1735703760), bar_available_at) is True

        # Valid access: after available_at
        assert verify_availability_enforcement(UtcEpochSec(1735703800), bar_available_at) is True

        # Invalid access: 1 second prior to available_at
        with pytest.raises(TemporalLeakageError):
            verify_availability_enforcement(UtcEpochSec(1735703759), bar_available_at)
