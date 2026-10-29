"""
1. What this file does:
   Defines the authoritative 39-field EngineRunConfig Pydantic model and config hash generator for QuantView (Task M4-18).
   Enforces exact typing, capital in integer paise, and cryptographic provenance without lookahead.

2. Overall design:
   Enforces QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §19.1 and §19.2:
     - 39 canonical configuration fields covering run metadata, temporal boundaries, capital,
       strategy parameters, execution models, fee schedules, risk constraints, and dataset hashes.
     - Mandates capital_paise as strictly positive integer Paise without default.
     - Computes deterministic SHA-256 config_hash for byte-identical run reproduction.

3. Elements in the file:
   - EngineRunConfig: Authoritative Pydantic v2 schema for backtest runs.

4. Final output of the file:
   - Exported EngineRunConfig class.
"""

import hashlib
import json
import uuid
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.risk.rules import RiskRules


class EngineRunConfig(BaseModel):
    """
    1. The use of class:
       Authoritative 39-field configuration model governing a backtest execution run per ENGINE §19.1.

    2. What the class contains:
       39 canonical fields: schema_version, run_id, seed, instrument_universe, start_date, end_date,
       strategy_id, strategy_version, strategy_params, option_side, decision_timeframe, expiry_policy,
       min_dte, exact_expiry_date, strike_policy, target_delta, exact_strike, mode, capital_paise,
       sizing_mode, lots, risk_inr_paise, risk_policy_id, risk_controls, intrabar_stop_policy,
       entry_delay_policy, entry_delay_bars, max_stale_minutes, order_expiry_bars, stop_loss_pct,
       take_profit_pct, trailing_stop_pct, entry_window_start, last_entry_time, force_flat_time,
       overnight_carry, fee_schedule_version, slippage_model_id, slippage_ticks, slippage_multiplier,
       risk_free_rate_source, vix_filter_enabled, holdout_config_version, final_evaluation,
       and engine helper fields (tick_paise, strategy_code_hash, dataset_manifest_hash).

    3. Technologies used and why:
       Pydantic v2 BaseModel for frozen immutability, runtime boundary validation, and canonical serialization.

    4. Key design and overall design of the class:
       Guarantees invariant 14 (strictly required capital_paise > 0 with no default) and SHA-256 config hash.
    """
    model_config = ConfigDict(frozen=True, extra="allow")

    # 1. Run Metadata
    schema_version: str = "1.0.0"
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    seed: int = 42
    instrument_universe: str = "NIFTY_OPTIONS"

    # 2. Temporal Bounds
    start_date: str
    end_date: str

    # 3. Strategy Specification
    strategy_id: str
    strategy_version: str = "1.0.0"
    strategy_params: Dict[str, Any] = Field(default_factory=dict)
    strategy_name: Optional[str] = None
    strategy_code_hash: str = "unversioned"

    # 4. Instrument & Selection Policies
    option_side: str = "BOTH"
    decision_timeframe: str = "5m"
    expiry_policy: str = "NEAREST_ELIGIBLE"
    min_dte: Optional[int] = None
    exact_expiry_date: Optional[str] = None
    strike_policy: str = "ATM"
    target_delta: Optional[str] = None
    exact_strike: Optional[str] = None

    # 5. Operating Mode & Capital (MANDATORY capital_paise > 0, NO DEFAULT)
    mode: Any = "REALISTIC_ACCOUNT"
    capital_paise: int
    initial_capital_paise: Optional[int] = None
    account_id: str = "default_account"

    # 6. Sizing & Risk Allocation
    sizing_mode: str = "FIXED_LOTS"
    lots: int = 1
    risk_inr_paise: Optional[int] = None
    risk_policy_id: Optional[str] = None
    risk_controls: Optional[RiskRules] = None

    # 7. Execution, Delays & Invariants
    intrabar_stop_policy: str = "STOP_FIRST"
    entry_delay_policy: str = "NEXT_BAR_OPEN"
    entry_delay_bars: Optional[int] = None
    max_stale_minutes: int = 5
    order_expiry_bars: int = 1
    tick_paise: int = 5

    # 8. Order Exit Parameters
    stop_loss_pct: Optional[Union[str, float]] = None
    take_profit_pct: Optional[Union[str, float]] = None
    trailing_stop_pct: Optional[Union[str, float]] = None

    # 9. Session Timing Windows (Asia/Kolkata)
    entry_window_start: str = "09:20"
    last_entry_time: str = "15:00"
    force_flat_time: str = "15:25"
    overnight_carry: bool = False

    # 10. Fee, Slippage & Benchmark Rates
    fee_schedule_version: str = "UPSTOX_2025_OCT"
    fee_schedule_name: Optional[str] = None
    slippage_model_id: str = "FIXED_TICKS"
    slippage_ticks: int = 1
    slippage_paise: int = 5
    slippage_multiplier: str = "1"
    risk_free_rate_source: str = "ZERO_ASSUMPTION"

    # 11. Provenance, Holdout & Integrity
    vix_filter_enabled: bool = False
    holdout_config_version: Optional[str] = None
    final_evaluation: bool = False
    dataset_manifest_hash: str = "local_lake_active"

    @model_validator(mode="before")
    @classmethod
    def reconcile_and_validate_fields(cls, values: Any) -> Any:
        """
        1. The use of function:
           Reconciles field aliases and strictly validates required capital and temporal ordering.

        2. How does the specific function work:
           - Cross-maps initial_capital_paise <-> capital_paise.
           - Cross-maps strategy_name <-> strategy_id.
           - Cross-maps fee_schedule_name <-> fee_schedule_version.
           - Validates that capital_paise is present and strictly > 0.
           - Validates that start_date <= end_date.

        3. Concepts used in the function:
           Pydantic pre-validation and causal temporal bounds check.

        4. Places where this function is imported and used:
           Invoked automatically during EngineRunConfig instantiation.

        5. Final output of the function, before and after:
           Before: Raw dictionary of input parameters.
           After: Cleaned, reconciled parameter dict guaranteed to have valid capital and dates.
        """
        if not isinstance(values, dict):
            return values

        data = dict(values)

        # Cross-map capital aliases
        if "capital_paise" not in data or data["capital_paise"] is None:
            if "initial_capital_paise" in data and data["initial_capital_paise"] is not None:
                data["capital_paise"] = data["initial_capital_paise"]

        if "capital_paise" not in data or data["capital_paise"] is None:
            raise ValueError("capital_paise is strictly required with no default (ENGINE §19.1).")

        if data["capital_paise"] <= 0:
            raise ValueError(f"capital_paise must be strictly positive, got {data['capital_paise']}")

        data["initial_capital_paise"] = data["capital_paise"]

        # Cross-map strategy aliases
        if "strategy_id" not in data or not data["strategy_id"]:
            if "strategy_name" in data and data["strategy_name"]:
                data["strategy_id"] = data["strategy_name"]
            else:
                raise ValueError("strategy_id is strictly required (ENGINE §19.1).")

        if "strategy_name" not in data or not data["strategy_name"]:
            data["strategy_name"] = data["strategy_id"]

        # Cross-map fee schedule aliases
        if "fee_schedule_version" not in data or not data["fee_schedule_version"]:
            if "fee_schedule_name" in data and data["fee_schedule_name"]:
                data["fee_schedule_version"] = data["fee_schedule_name"]

        if "fee_schedule_name" not in data or not data["fee_schedule_name"]:
            data["fee_schedule_name"] = data.get("fee_schedule_version", "UPSTOX_2025_OCT")

        # Temporal ordering check
        start = data.get("start_date")
        end = data.get("end_date")
        if start and end and str(start) > str(end):
            raise ValueError(f"start_date ({start}) cannot be after end_date ({end})")

        return data

    def compute_config_hash(self) -> str:
        """
        1. The use of function:
           Computes deterministic SHA-256 digest of canonical JSON representation.

        2. How does the specific function work:
           Dumps model to sorted JSON key format and hashes UTF-8 bytes.

        3. Concepts used in the function:
           Cryptographic provenance and configuration reproducibility.

        4. Places where this function is imported and used:
           Used by BacktestRunner and run manifests.

        5. Final output of the function, before and after:
           Before: EngineRunConfig instance.
           After: Hexadecimal 64-character SHA-256 string.
        """
        raw_dict = self.model_dump(mode="json")
        canonical_json = json.dumps(raw_dict, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
