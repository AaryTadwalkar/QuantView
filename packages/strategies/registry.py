"""
1. What this file does:
   Implements the StrategyRegistry and code provenance hasher for QuantView (Task M4-12).
   Provides discovery, parameter validation, and cryptographic code hashing for trading strategies.

2. Overall design:
   Enforces QUANTVIEW_MASTER_SPEC §2.2 and QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §19:
     - Central catalog registering Strategy implementations.
     - Validates incoming parameters against optional Pydantic schemas.
     - Computes SHA-256 code hash of strategy source for immutable backtest provenance manifests.
     - Provides factory instantiation for backtest runners and execution daemons.

3. Elements in the file:
   - StrategyRegistryEntry: Container holding strategy metadata, class reference, and code hash.
   - StrategyRegistry: Singleton catalog managing registered strategies.
   - get_default_strategy_registry(): Shared singleton accessor.

4. Final output of the file:
   - Exported StrategyRegistry and registry helpers.
"""

import hashlib
import inspect
from typing import Any, Dict, List, NamedTuple, Optional, Type

from pydantic import BaseModel

from packages.strategies import Strategy


class StrategyRegistryEntry(NamedTuple):
    """Container holding registered strategy class and provenance metadata."""
    name: str
    strategy_cls: Type[Strategy]
    code_hash: str
    param_schema: Optional[Type[BaseModel]] = None
    description: str = ""


class StrategyRegistry:
    """
    1. The use of class:
       Central catalog registering, discovering, and instantiating Strategy implementations.

    2. What the class contains:
       - _entries: Dictionary mapping strategy name to StrategyRegistryEntry.
       - register(): Registers strategy class and computes source code hash.
       - get(): Instantiates strategy with validated parameters.
       - list_strategies(): Returns list of registered strategy names.

    3. Technologies used and why:
       inspect.getsource and hashlib.sha256 for deterministic reproducibility manifests.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, StrategyRegistryEntry] = {}

    @staticmethod
    def compute_code_hash(strategy_cls: Type[Any]) -> str:
        """Computes deterministic SHA-256 hash of the strategy's source code."""
        try:
            source = inspect.getsource(strategy_cls)
            return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
        except (OSError, TypeError):
            # Fallback if source unavailable (e.g. dynamic or compiled)
            return hashlib.sha256(strategy_cls.__name__.encode("utf-8")).hexdigest()[:16]

    def register(
        self,
        name: str,
        strategy_cls: Type[Strategy],
        param_schema: Optional[Type[BaseModel]] = None,
        description: str = "",
    ) -> None:
        """Registers a strategy class and computes its code hash for reproducibility."""
        code_hash = self.compute_code_hash(strategy_cls)
        entry = StrategyRegistryEntry(
            name=name,
            strategy_cls=strategy_cls,
            code_hash=code_hash,
            param_schema=param_schema,
            description=description,
        )
        self._entries[name] = entry

    def get_entry(self, name: str) -> StrategyRegistryEntry:
        """Retrieves registry entry for a strategy name, raising KeyError if not found."""
        if name not in self._entries:
            raise KeyError(f"Strategy '{name}' is not registered in StrategyRegistry")
        return self._entries[name]

    def create(self, name: str, params: Optional[Dict[str, Any]] = None) -> Strategy:
        """Instantiates a strategy with optional validated parameters."""
        entry = self.get_entry(name)
        cfg = params or {}
        if entry.param_schema is not None:
            # Validate parameters through Pydantic
            validated = entry.param_schema(**cfg)
            cfg = validated.model_dump()
        instance = entry.strategy_cls()
        instance.on_start(cfg)
        return instance

    def list_strategies(self) -> List[str]:
        """Returns sorted list of registered strategy names."""
        return sorted(list(self._entries.keys()))


_GLOBAL_STRATEGY_REGISTRY: Optional[StrategyRegistry] = None


def get_default_strategy_registry() -> StrategyRegistry:
    """Returns singleton instance of StrategyRegistry."""
    global _GLOBAL_STRATEGY_REGISTRY
    if _GLOBAL_STRATEGY_REGISTRY is None:
        _GLOBAL_STRATEGY_REGISTRY = StrategyRegistry()
    return _GLOBAL_STRATEGY_REGISTRY
