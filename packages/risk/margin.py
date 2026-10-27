"""
1. What this file does:
   Implements the margin evaluation interface, dated verification record, and fail-closed safety guard
   for QuantView (Tasks M4-14, M4-17).
   Prevents unverified short options from executing in realistic-account mode pending authoritative exchange SPAN parameter files.

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §14, §17 and QUANTVIEW_DATA_SPEC §2.1:
     - Maintains MARGIN_VERIFICATION_RECORD linking empirical research from Task M4-21 to gate enforcement.
     - Defines MarginMode enumeration (THEORETICAL vs REALISTIC_ACCOUNT).
     - Provides RealisticMarginBlockedError with the canonical 'MARGIN_NOT_VERIFIED' rejection code.
     - Implements MarginEvaluator to gate single-leg and multi-leg short options at order-queue time.
     - Fail-closed default: short options are strictly prohibited unless explicitly operating under THEORETICAL mode.

3. Elements in the file:
   - MARGIN_VERIFICATION_RECORD: Authoritative dated verification record for regulatory margin status.
   - RealisticMarginBlockedError: Exception raised when unverified margin execution is attempted.
   - MarginMode: Enumeration of margin accounting modes.
   - MarginEvaluator: Pre-trade margin safety evaluation engine.

4. Final output of the file:
   - Exported MARGIN_VERIFICATION_RECORD, RealisticMarginBlockedError, MarginMode, and MarginEvaluator classes.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from packages.domain import OrderSide, Paise

# Dated verification record per Task M4-17 acceptance contract
MARGIN_VERIFICATION_RECORD: Dict[str, Any] = {
    "verification_task": "M4-17",
    "research_task_ref": "M4-21",
    "research_report": "reports/margin-settlement-evidence.md",
    "date": "2026-10-27",
    "status": "VERIFY_SPAN_FILES_ABSENT",
    "clearing_files_available": False,
    "span_risk_parameter_file_type": ".spn",
    "hedge_benefit_framework": "SEBI/HO/MRD/DRMNP/CIR/P/2020/06",
    "peak_margin_intraday_snapshots": 4,
    "settlement_type": "CASH_SETTLED_VWAP_30MIN",
    "enforcement_action": "REJECT_REALISTIC_SHORT_OPTIONS",
    "theoretical_label_mandatory": True,
}


class RealisticMarginBlockedError(Exception):
    """
    1. The use of class:
       Raised when short option execution is attempted in REALISTIC_ACCOUNT mode without verified clearing SPAN files.

    2. What the class contains:
       - error_code: String code 'MARGIN_NOT_VERIFIED'.
       - message: Diagnostic explanation of the clearing file requirement.

    3. Technologies used and why:
       Standard Python Exception subclass for fail-closed control flow.

    4. Key design and overall design of the class:
       Halts order routing immediately when realistic short options margin cannot be verified against exchange SPAN data.
    """

    def __init__(self, message: str = "MARGIN_NOT_VERIFIED: Real-time clearing member SPAN risk parameter files (.spn) required for REALISTIC_ACCOUNT short options. Execution strictly blocked.") -> None:
        self.error_code = "MARGIN_NOT_VERIFIED"
        super().__init__(f"[{self.error_code}] {message}")


class MarginMode(str, Enum):
    """
    1. The use of class:
       Enumeration of margin accounting modes supported by the execution engine.

    2. What the class contains:
       - THEORETICAL: Assumes theoretical margin parameters with prominent labelling.
       - REALISTIC_ACCOUNT: Requires verified exchange SPAN parameter files and actual clearing rules.

    3. Technologies used and why:
       String Enum for clean serialization and configuration validation.

    4. Key design and overall design of the class:
       Separates exploratory theoretical simulations from production-grade clearing margin runs.
    """
    THEORETICAL = "THEORETICAL"
    REALISTIC_ACCOUNT = "REALISTIC_ACCOUNT"


class MarginEvaluator:
    """
    1. The use of class:
       Evaluates margin safety constraints and enforces fail-closed gates for short option orders and multi-leg groups.

    2. What the class contains:
       - mode: Current MarginMode setting (default THEORETICAL).
       - is_verified: Boolean flag indicating whether clearing SPAN risk files are loaded and active.
       - validate_order_safety(): Validates a proposed single order before submission.
       - validate_group_safety(): Validates a multi-leg group structure before legging begins.
       - check_buying_power(): Verifies free cash sufficiency against required margin.
       - get_margin_status(): Returns diagnostic metadata for run manifests.

    3. Technologies used and why:
       Pure Python class ensuring zero-dependency, high-speed pre-trade verification.

    4. Key design and overall design of the class:
       Operates as a pre-flight security barrier in the execution pipeline to ensure QuantView never emits false realistic-account claims.
    """

    def __init__(
        self,
        mode: Union[MarginMode, str] = MarginMode.THEORETICAL,
        is_verified: bool = False,
    ) -> None:
        if isinstance(mode, str):
            self.mode = MarginMode(mode)
        else:
            self.mode = mode
        self.is_verified = is_verified

    def validate_order_safety(
        self,
        side: OrderSide,
        is_option: bool = True,
        override_mode: Optional[Union[MarginMode, str]] = None,
    ) -> None:
        """
        1. The use of function:
           Validates that a single order meets margin safety requirements before queueing or submission.

        2. How does the specific function work:
           - Resolves active margin mode (override or instance default).
           - Checks if the order is a short option (side == SELL and is_option == True).
           - If short option and mode is REALISTIC_ACCOUNT while unverified, raises RealisticMarginBlockedError.
           - Allows long options and all theoretical mode orders to pass.

        3. Concepts used in the function:
           Fail-closed security check, SEBI margin verification gating.

        4. Places where this function is imported and used:
           Used by BacktestRunner, IntrabarFillEngine, and RiskPolicyEvaluator.

        5. Final output of the function, before and after:
           Before: Unvalidated order parameters. After: None on success, or raises RealisticMarginBlockedError.
        """
        effective_mode = self.mode
        if override_mode is not None:
            effective_mode = MarginMode(override_mode) if isinstance(override_mode, str) else override_mode

        if is_option and side == OrderSide.SELL:
            if effective_mode == MarginMode.REALISTIC_ACCOUNT and not self.is_verified:
                raise RealisticMarginBlockedError(
                    "Real-time clearing member SPAN risk parameter files (.spn) required for REALISTIC_ACCOUNT short options. Execution strictly blocked."
                )

    def validate_group_safety(
        self,
        legs: List[Tuple[OrderSide, bool]],
        override_mode: Optional[Union[MarginMode, str]] = None,
    ) -> None:
        """
        1. The use of function:
           Validates that all legs within a proposed multi-leg position group comply with margin verification rules.

        2. How does the specific function work:
           - Iterates across each (side, is_option) leg tuple in the group.
           - Invokes validate_order_safety on each leg.
           - Fails closed immediately upon encountering the first unverified short option leg in realistic mode.

        3. Concepts used in the function:
           Composite structure pre-validation, atomic group gating.

        4. Places where this function is imported and used:
           Used by PositionGroup and execution sequencer prior to queueing Leg 1.

        5. Final output of the function, before and after:
           Before: List of proposed leg side/type specifications. After: None on success, or raises RealisticMarginBlockedError.
        """
        for side, is_option in legs:
            self.validate_order_safety(side=side, is_option=is_option, override_mode=override_mode)

    def check_buying_power(
        self,
        free_cash_paise: Paise,
        required_margin_paise: Paise,
    ) -> bool:
        """
        1. The use of function:
           Verifies that unencumbered cash balance is sufficient to cover required initial margin reservation.

        2. How does the specific function work:
           Returns True if free_cash_paise >= required_margin_paise, else False.

        3. Concepts used in the function:
           Free cash buying power check (ENGINE §8).

        4. Places where this function is imported and used:
           Used by pre-trade risk policy evaluators and backtest engines.

        5. Final output of the function, before and after:
           Before: Free cash and margin requirement. After: Boolean indicating buying power sufficiency.
        """
        return int(free_cash_paise) >= int(required_margin_paise)

    def get_margin_status(self) -> Dict[str, Any]:
        """
        1. The use of function:
           Returns the current margin evaluation configuration and verification state for provenance tracking.

        2. How does the specific function work:
           Constructs a dictionary containing margin mode, verification status, and reason code.

        3. Concepts used in the function:
           Run provenance and audit trail generation.

        4. Places where this function is imported and used:
           Used by BacktestManifestBuilder to embed margin verification details into manifest.json.

        5. Final output of the function, before and after:
           Before: MarginEvaluator instance. After: Dictionary with 'margin_mode', 'is_verified', and 'audit_label'.
        """
        return {
            "margin_mode": self.mode.value,
            "is_verified": self.is_verified,
            "audit_label": "VERIFIED" if self.is_verified else "MARGIN_NOT_VERIFIED",
            "verification_record": MARGIN_VERIFICATION_RECORD,
        }
