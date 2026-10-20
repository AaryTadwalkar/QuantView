"""
1. What this file does:
   Defines the risk management policy evaluator and safety invariants for QuantView.

2. Overall design:
   The risk package implements canonical risk rules (RK-01 to RK-26). It evaluates proposed
   order intents prior to submission and monitors active exposures.
   Key distinction:
     - RK-06: Hard freeze limit (mandatory exchange submission block).
     - RK-26: Advisory order lot ceiling (non-blocking advisory warning in manual paper).

3. Elements in the file:
   - RiskDecision: Outcome of a risk evaluation (APPROVED, REJECTED, ADVISORY).
   - RiskPolicyEvaluator: Interface for pre-trade and real-time risk checks.

4. Final output of the file:
   - Exported risk policy evaluators and safety evaluation contracts.
"""

from enum import Enum
from typing import NamedTuple, Optional
from packages.domain import Paise, ContractIdentifier


class RiskVerdict(str, Enum):
    """
    1. The use of class:
       Enumerates risk check verdicts.

    2. What the class contains:
       - PASS: Order approved without constraint.
       - REJECT: Hard block (e.g. RK-06 freeze limit breach, daily loss limit breached).
       - ADVISORY: Non-blocking warning (e.g. RK-26 manual lot advisory).

    3. Technologies used and why:
       str and Enum for deterministic policy outcomes.

    4. Key design and overall design of the class:
       Strict separation of hard blocks vs advisory warnings.
    """
    PASS = "PASS"
    REJECT = "REJECT"
    ADVISORY = "ADVISORY"


class RiskDecision(NamedTuple):
    """
    1. The use of class:
       Immutable output of a risk evaluation.

    2. What the class contains:
       - verdict: RiskVerdict enum.
       - rule_id: Identifier of the triggering rule (e.g. 'RK-06').
       - reason: Human-readable diagnostic explanation.

    3. Technologies used and why:
       NamedTuple for fast immutable creation and serialization.

    4. Key design and overall design of the class:
       Preserves full audit trail for order approvals and rejections.
    """
    verdict: RiskVerdict
    rule_id: str
    reason: str


class RiskPolicyEvaluator:
    """
    1. The use of class:
       Evaluates orders against configured risk ceilings before they can be routed to simulated
       or live broker adapters.

    2. What the class contains:
       - max_loss_paise: Maximum allowed drawdown in integer paise.
       - freeze_quantity: Hard exchange limit per single order (RK-06).
       - evaluate_order(): Tests an order intent against active constraints.

    3. Technologies used and why:
       Pure Python arithmetic on exact Paise units.

    4. Key design and overall design of the class:
       Fail-closed: any calculation error or missing constraint defaults to REJECT.
    """

    def __init__(self, max_loss_paise: Paise, freeze_quantity: int = 1800):
        """
        1. The use of function:
           Initializes RiskPolicyEvaluator with loss limits and freeze ceilings.

        2. How does the specific function work:
           Stores integer paise limit and freeze lot bounds.

        3. Concepts used in the function:
           Integer money accounting, exchange constraints.

        4. Places where this function is imported and used:
           Initialized by engine and paper/live daemons.

        5. Final output of the function, before and after:
           Before: Parameters. After: Configured evaluator.
        """
        self.max_loss_paise = max_loss_paise
        self.freeze_quantity = freeze_quantity

    def evaluate_order(self, contract: ContractIdentifier, quantity: int) -> RiskDecision:
        """
        1. The use of function:
           Evaluates an order intent against freeze quantity limits (RK-06).

        2. How does the specific function work:
           Checks if quantity > freeze_quantity. Returns REJECT if breached, PASS otherwise.

        3. Concepts used in the function:
           Pre-trade risk enforcement.

        4. Places where this function is imported and used:
           Called before submitting orders to fill models or broker.

        5. Final output of the function, before and after:
           Before: Contract and quantity. After: RiskDecision NamedTuple.
        """
        if quantity > self.freeze_quantity:
            return RiskDecision(
                verdict=RiskVerdict.REJECT,
                rule_id="RK-06",
                reason=f"Order quantity {quantity} exceeds hard exchange freeze limit {self.freeze_quantity}.",
            )
        return RiskDecision(verdict=RiskVerdict.PASS, rule_id="NONE", reason="Order passed risk checks.")
