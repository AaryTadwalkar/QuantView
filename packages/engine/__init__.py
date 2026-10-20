"""
1. What this file does:
   Defines the simulation engine, causal clock, fill model, and execution orchestration for QuantView.

2. Overall design:
   The engine orchestrates the exchange-calendar minute loop across historical bars or live streams.
   It coordinates:
     - Causal bar progression (STOP_FIRST order of intrabar stops vs targets).
     - Fill models respecting exchange tick sizes and slippage.
     - Separation of the three canonical P&L modes (UNDERLYING_DIRECTIONAL, ACTUAL_OPTIONS, SYNTHETIC_OPTIONS_ESTIMATE).

3. Elements in the file:
   - EngineRunConfig: Configuration specification for backtest execution.
   - SimulationClock: Advances step-by-step through exchange session minutes.

4. Final output of the file:
   - Exported engine configuration contracts and execution clock interfaces.
"""

from typing import Dict, Any, List, Optional
from packages.domain import OperatingMode, UtcEpochSec
from packages.strategies import Strategy
from packages.ledger import FinancialLedger
from packages.risk import RiskPolicyEvaluator


class EngineRunConfig:
    """
    1. The use of class:
       Validates and encapsulates execution parameters for a backtest or paper deployment.

    2. What the class contains:
       - mode: OperatingMode.
       - start_date: ISO date string (YYYY-MM-DD).
       - end_date: ISO date string (YYYY-MM-DD).
       - initial_capital_paise: Starting cash in Paise.
       - strategy_name: Name of strategy to instantiate.
       - strategy_params: Dictionary of strategy parameters.

    3. Technologies used and why:
       Plain class for parameter encapsulation.

    4. Key design and overall design of the class:
       Directly maps to the RunConfig schema in QuantView Master Spec §4.
    """

    def __init__(
        self,
        mode: OperatingMode,
        start_date: str,
        end_date: str,
        initial_capital_paise: int,
        strategy_name: str,
        strategy_params: Optional[Dict[str, Any]] = None,
    ):
        """
        1. The use of function:
           Initializes EngineRunConfig instance.

        2. How does the specific function work:
           Stores and validates operating mode and date boundaries.

        3. Concepts used in the function:
           Configuration validation.

        4. Places where this function is imported and used:
           Constructed by CLI, API, and worker_compute.

        5. Final output of the function, before and after:
           Before: Parameters. After: Validated EngineRunConfig.
        """
        self.mode = mode
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital_paise = initial_capital_paise
        self.strategy_name = strategy_name
        self.strategy_params = strategy_params or {}
