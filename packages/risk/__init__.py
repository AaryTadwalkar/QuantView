"""
1. What this file does:
   Defines the risk management policy evaluator, canonical RiskRules model, margin safety guards,
   and safety invariants for QuantView (Tasks M4-14, M4-17, M4-20).

2. Overall design:
   The risk package implements canonical risk rules (RK-01 to RK-26) and margin safety controls. It evaluates proposed
   order intents prior to submission and monitors active exposures:
     - RK-01: Global kill switch.
     - RK-02: Trading window constraints.
     - RK-03: Maximum daily loss limit.
     - RK-04: Maximum portfolio drawdown ceiling.
     - RK-05: Maximum capital per trade.
     - RK-06: Hard freeze limit (mandatory exchange submission block, 1,800 lots).
     - Margin Guard: Blocks unverified short options under REALISTIC_ACCOUNT mode (Tasks M4-14, M4-17).

3. Elements in the file:
   - RiskVerdict: Enumeration of risk verdicts (PASS, REJECT, ADVISORY).
   - RiskDecision: Outcome of a risk evaluation with rule ID and diagnostics.
   - RiskRules: Pydantic configuration model for risk parameters.
   - RiskPolicyEvaluator: Interface for pre-trade and real-time risk checks.
   - MARGIN_VERIFICATION_RECORD: Authoritative dated verification record for regulatory margin status.
   - RealisticMarginBlockedError: Exception raised when unverified margin execution is attempted.
   - MarginMode: Enumeration of margin accounting modes (THEORETICAL vs REALISTIC_ACCOUNT).
   - MarginEvaluator: Pre-trade margin safety evaluation engine.

4. Final output of the file:
   - Exported risk policy evaluators, rule models, margin safety guards, and evaluation contracts.
"""

from packages.risk.evaluator import RiskPolicyEvaluator
from packages.risk.margin import (
    MARGIN_VERIFICATION_RECORD,
    MarginEvaluator,
    MarginMode,
    RealisticMarginBlockedError,
)
from packages.risk.rules import RiskDecision, RiskRules, RiskVerdict

__all__ = [
    "RiskVerdict",
    "RiskDecision",
    "RiskRules",
    "RiskPolicyEvaluator",
    "MARGIN_VERIFICATION_RECORD",
    "RealisticMarginBlockedError",
    "MarginMode",
    "MarginEvaluator",
]
