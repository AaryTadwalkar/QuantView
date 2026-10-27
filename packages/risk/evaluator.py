"""
1. What this file does:
   Implements the RiskPolicyEvaluator pre-trade risk engine for QuantView (Task M4-20).
   Evaluates orders against freeze quantity ceilings (RK-06), daily loss limits, drawdowns, and trading windows.

2. Overall design:
   Enforces QUANTVIEW_DATA_SPEC §2.1 and QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §19.1:
     - Pre-trade gating: orders must pass all active rules before queueing or routing.
     - Fail-closed execution: any rule breach results in an immediate REJECT decision.
     - Invariant separation: RK-06 hard freeze limit (1,800 contracts for NIFTY) vs RK-26 lot ceiling.

3. Elements in the file:
   - RiskPolicyEvaluator: Core risk assessment engine.

4. Final output of the file:
   - Exported RiskPolicyEvaluator class.
"""

from typing import Optional

from packages.domain import ContractIdentifier, Paise
from packages.risk.rules import RiskDecision, RiskRules, RiskVerdict


class RiskPolicyEvaluator:
    """
    1. The use of class:
       Evaluates orders and trading intentions against active risk rules prior to submission.

    2. What the class contains:
       - rules: RiskRules configuration model.
       - max_loss_paise: Daily maximum net loss ceiling in Paise.
       - freeze_quantity: Hard single-order exchange ceiling (RK-06).
       - evaluate_order(): Main evaluation method returning RiskDecision.

    3. Technologies used and why:
       Pure Python with strict type safety and fail-closed branches.

    4. Key design and overall design of the class:
       Guarantees orders exceeding risk parameters cannot enter the execution engine or broker adapters.
    """

    def __init__(
        self,
        rules: Optional[RiskRules] = None,
        max_loss_paise: Optional[Paise] = None,
        freeze_quantity: int = 1800,
    ) -> None:
        """
        Initializes RiskPolicyEvaluator with either a RiskRules model or direct parameters.
        """
        if rules is not None:
            self.rules = rules
        else:
            self.rules = RiskRules(
                max_loss_per_day_paise=int(max_loss_paise) if max_loss_paise is not None else None,
                freeze_quantity=freeze_quantity,
            )
        self.max_loss_paise = max_loss_paise or (
            Paise(self.rules.max_loss_per_day_paise) if self.rules.max_loss_per_day_paise is not None else None
        )
        self.freeze_quantity = self.rules.freeze_quantity

    def evaluate_order(
        self,
        contract: ContractIdentifier,
        quantity: int,
        price_paise: Optional[Paise] = None,
        current_time_str: Optional[str] = None,
        daily_loss_paise: Optional[Paise] = None,
        drawdown_pct: Optional[float] = None,
    ) -> RiskDecision:
        """
        1. The use of function:
           Evaluates an order against all configured pre-trade risk constraints.

        2. How does the specific function work:
           - RK-01: Checks kill switch.
           - RK-02: Checks trading window bounds.
           - RK-06: Checks hard freeze quantity limit.
           - RK-03: Checks daily loss limit.
           - RK-04: Checks maximum drawdown percentage.
           - RK-05: Checks max capital per trade.
           - Returns RiskDecision with verdict PASS or REJECT.
        """
        # 1. Kill Switch Check (RK-01)
        if self.rules.kill_switch_active:
            return RiskDecision(
                verdict=RiskVerdict.REJECT,
                rule_id="RK-01",
                reason="Order rejected: manual kill switch is active.",
            )

        # 2. Hard Freeze Quantity Check (RK-06)
        if quantity > self.freeze_quantity:
            return RiskDecision(
                verdict=RiskVerdict.REJECT,
                rule_id="RK-06",
                reason=f"Order quantity {quantity} exceeds hard exchange freeze limit {self.freeze_quantity}.",
            )

        # 3. Trading Window Check (RK-02)
        if current_time_str is not None:
            if current_time_str < self.rules.trading_window_start or current_time_str > self.rules.trading_window_end:
                return RiskDecision(
                    verdict=RiskVerdict.REJECT,
                    rule_id="RK-02",
                    reason=f"Order time {current_time_str} is outside permitted window {self.rules.trading_window_start}-{self.rules.trading_window_end}.",
                )

        # 4. Daily Loss Limit Check (RK-03)
        if daily_loss_paise is not None and self.rules.max_loss_per_day_paise is not None:
            if daily_loss_paise >= self.rules.max_loss_per_day_paise:
                return RiskDecision(
                    verdict=RiskVerdict.REJECT,
                    rule_id="RK-03",
                    reason=f"Daily net loss ({daily_loss_paise} paise) reached maximum loss limit ({self.rules.max_loss_per_day_paise} paise).",
                )

        # 5. Maximum Drawdown Check (RK-04)
        if drawdown_pct is not None and self.rules.max_drawdown_pct is not None:
            if drawdown_pct >= self.rules.max_drawdown_pct:
                return RiskDecision(
                    verdict=RiskVerdict.REJECT,
                    rule_id="RK-04",
                    reason=f"Account drawdown ({drawdown_pct:.2f}%) reached maximum drawdown ceiling ({self.rules.max_drawdown_pct:.2f}%).",
                )

        # 6. Maximum Capital Per Trade Check (RK-05)
        if price_paise is not None and self.rules.max_capital_per_trade_paise is not None:
            trade_capital = quantity * int(price_paise)
            if trade_capital > self.rules.max_capital_per_trade_paise:
                return RiskDecision(
                    verdict=RiskVerdict.REJECT,
                    rule_id="RK-05",
                    reason=f"Trade capital ({trade_capital} paise) exceeds max capital per trade limit ({self.rules.max_capital_per_trade_paise} paise).",
                )

        return RiskDecision(verdict=RiskVerdict.PASS, rule_id="NONE", reason="Order passed risk checks.")
