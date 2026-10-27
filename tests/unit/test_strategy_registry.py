"""
1. What this file does:
   Comprehensive unit tests for the StrategyRegistry and Strategy protocol (Task M4-12).

2. Overall design:
   Uses pytest to verify:
     - Registering Strategy implementations.
     - Computing deterministic SHA-256 code hashes.
     - Parameter schema validation via Pydantic models.
     - Strategy instantiation through create().
     - KeyError fail-closed behavior on unregistered strategy requests.

3. Elements in the file:
   - TestStrategyRegistry: Unit test suite for strategy discovery and registration.

4. Final output of the file:
   - Automated pass/fail test execution for Task M4-12.
"""

from typing import Any, Dict, Optional

import pytest
from pydantic import BaseModel

from packages.domain import UtcEpochSec
from packages.strategies import (
    SignalAction,
    Strategy,
    StrategyRegistry,
    StrategySignal,
)


class DummyParamSchema(BaseModel):
    rsi_period: int = 14
    lot_size: int = 25


class SampleMockStrategy:
    """Mock implementation of Strategy(Protocol)."""
    def __init__(self) -> None:
        self.config: Dict[str, Any] = {}
        self.started = False

    def on_start(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.started = True

    def on_bar(self, timestamp: UtcEpochSec, features: Dict[str, Any]) -> Optional[StrategySignal]:
        return StrategySignal(action=SignalAction.ENTER_LONG, timestamp=timestamp, reason="Mock signal")

    def on_stop(self) -> None:
        self.started = False


class TestStrategyRegistry:
    """
    1. The use of class:
       Unit test suite validating StrategyRegistry operations and code hashing.
    """

    def test_register_and_create_strategy(self):
        """Tests registering a strategy and instantiating it with parameters."""
        reg = StrategyRegistry()
        reg.register(
            name="SampleMockStrategy",
            strategy_cls=SampleMockStrategy,
            param_schema=DummyParamSchema,
            description="Mock strategy for registry verification",
        )

        assert "SampleMockStrategy" in reg.list_strategies()
        entry = reg.get_entry("SampleMockStrategy")
        assert len(entry.code_hash) == 16
        assert entry.description == "Mock strategy for registry verification"

        # Create instance
        strat = reg.create("SampleMockStrategy", {"rsi_period": 21, "lot_size": 50})
        assert isinstance(strat, SampleMockStrategy)
        assert strat.started is True
        assert strat.config["rsi_period"] == 21
        assert strat.config["lot_size"] == 50

    def test_parameter_schema_validation_failure(self):
        """Tests that invalid parameters are rejected by Pydantic validation."""
        reg = StrategyRegistry()
        reg.register("SampleMockStrategy", SampleMockStrategy, param_schema=DummyParamSchema)

        # Invalid string for integer rsi_period
        with pytest.raises(Exception):
            reg.create("SampleMockStrategy", {"rsi_period": "invalid_integer"})

    def test_unregistered_strategy_raises_key_error(self):
        """Tests that requesting an unknown strategy raises KeyError."""
        reg = StrategyRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.create("NonExistentStrategy")

    def test_deterministic_code_hash(self):
        """Tests that code hashing produces identical hashes across runs."""
        hash1 = StrategyRegistry.compute_code_hash(SampleMockStrategy)
        hash2 = StrategyRegistry.compute_code_hash(SampleMockStrategy)
        assert hash1 == hash2
        assert len(hash1) == 16
