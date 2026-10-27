"""
1. What this file does:
   Defines the canonical RiskRules Pydantic model and RiskDecision data structures (Task M4-20).

2. Overall design:
   Enforces QUANTVIEW_DATA_SPEC §2.1 and QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §19.1:
     - Defines validated risk parameters with frozen immutability.
     - Supports daily loss ceilings, drawdown boundaries, exchange freeze limits (RK-06),
       trading windows, and manual kill-switch activation.

3. Elements in the file:
   - RiskRules: Pydantic v2 model holding active risk management limits.
   - RiskVerdict: Enumeration of evaluation outcomes (PASS, REJECT, ADVISORY).
   - RiskDecision: Immutable NamedTuple recording decision, rule ID, and diagnostic reason.

4. Final output of the file:
   - Exported RiskRules, RiskVerdict, and RiskDecision classes.
"""

import hashlib
from enum import Enum
from typing import NamedTuple, Optional

from pydantic import BaseModel, ConfigDict


class RiskVerdict(str, Enum):
    """Enumeration of risk evaluation outcomes."""
    PASS = "PASS"
    REJECT = "REJECT"
    ADVISORY = "ADVISORY"


class RiskDecision(NamedTuple):
    """Immutable output record of a risk policy evaluation."""
    verdict: RiskVerdict
    rule_id: str
    reason: str


class RiskRules(BaseModel):
    """
    1. The use of class:
       Pydantic model validating risk configuration parameters per ENGINE §19.1 and DATA §2.1.

    2. What the class contains:
       - max_loss_per_day_paise: Daily maximum net loss ceiling in Paise.
       - max_drawdown_pct: Peak-to-trough equity drawdown limit percentage.
       - freeze_quantity: Exchange hard ceiling per single order (RK-06, default 1,800 for NIFTY).
       - max_capital_per_trade_paise: Maximum premium allowed on a single trade.
       - max_active_orders: Maximum concurrent pending orders allowed.
       - trading_window_start: Opening time for trade entry ('09:15').
       - trading_window_end: Cutoff time for trade entry ('15:25').
       - kill_switch_active: Global circuit breaker halting all new entries.

    3. Technologies used and why:
       Pydantic v2 BaseModel with frozen configuration for strict validation.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_loss_per_day_paise: Optional[int] = None
    max_drawdown_pct: Optional[float] = None
    freeze_quantity: int = 1800
    max_capital_per_trade_paise: Optional[int] = None
    max_active_orders: int = 10
    trading_window_start: str = "09:15"
    trading_window_end: str = "15:25"
    kill_switch_active: bool = False

    def compute_policy_hash(self) -> str:
        """
        1. The use of function:
           Computes deterministic SHA-256 digest of canonical risk policy rules.

        2. How does the specific function work:
           Dumps model to JSON and hashes UTF-8 bytes with SHA-256.

        3. Concepts used in the function:
           Cryptographic risk provenance.

        4. Places where this function is imported and used:
           Used by BacktestRunner and run manifests.

        5. Final output of the function, before and after:
           Before: RiskRules instance. After: Hexadecimal 64-character SHA-256 string.
        """
        raw_json = self.model_dump_json()
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
