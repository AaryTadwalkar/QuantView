"""
1. What this file does:
   Defines the risk management policy evaluator, canonical RiskRules model, and safety invariants for QuantView.

2. Overall design:
   The risk package implements canonical risk rules (RK-01 to RK-26). It evaluates proposed
   order intents prior to submission and monitors active exposures:
     - RK-01: Global kill switch.
     - RK-02: Trading window constraints.
     - RK-03: Maximum daily loss limit.
     - RK-04: Maximum portfolio drawdown ceiling.
     - RK-05: Maximum capital per trade.
     - RK-06: Hard freeze limit (mandatory exchange submission block, 1,800 lots).

3. Elements in the file:
   - RiskVerdict: Enumeration of risk verdicts (PASS, REJECT, ADVISORY).
   - RiskDecision: Outcome of a risk evaluation with rule ID and diagnostics.
   - RiskRules: Pydantic configuration model for risk parameters.
   - RiskPolicyEvaluator: Interface for pre-trade and real-time risk checks.

4. Final output of the file:
   - Exported risk policy evaluators, rule models, and safety evaluation contracts.
"""

from packages.risk.rules import RiskVerdict, RiskDecision, RiskRules
from packages.risk.evaluator import RiskPolicyEvaluator

__all__ = [
    "RiskVerdict",
    "RiskDecision",
    "RiskRules",
    "RiskPolicyEvaluator",
]
