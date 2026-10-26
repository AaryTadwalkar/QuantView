"""
1. What this file does:
   Implements the Point-in-Time (PIT) Contract Selector for QuantView single-leg and multi-leg option execution (Task M4-04).
   Dynamically selects option contracts across active strikes, expiries, and data eligibility gates without hardcoded grids.

2. Overall design:
   Replaces fragile hardcoded strike step assumptions (e.g. static 50-pt grids) with dynamic queries against the
   point-in-time contract master:
     - Resolves spot price at decision time t on trade date D.
     - Filters active contracts by underlying symbol, option side (CE/PE), and expiry policy.
     - Resolves strike via ATM, ITM_k, OTM_k, or EXACT policies using the actual available strike spectrum.
     - Validates tradability against the data eligibility registry (v_data_eligibility).
     - Strictly enforces zero silent strike substitution: if a contract does not exist or fails eligibility,
       emits a structured rejection reason (NO_ELIGIBLE_CONTRACT or CONTRACT_DATA_INELIGIBLE).

3. Elements in the file:
   - StrikeSelectionPolicy: Enumeration of strike selection strategies (ATM, ITM, OTM, EXACT).
   - ExpirySelectionPolicy: Enumeration of expiry resolution rules (CURRENT_WEEK, NEXT_WEEK, MONTHLY, EXACT).
   - StrikePolicySpec: Container for parsed strike type and relative depth.
   - ContractSelectionResult: NamedTuple containing the selected ContractIdentifier and eligibility status.
   - ContractMasterProvider: Protocol/abstract interface for retrieving active contract records.
   - InMemoryContractMaster: Test and in-memory implementation of ContractMasterProvider.
   - DuckDbContractMaster: Implementation reading active contracts from DuckDB views.
   - PointInTimeContractSelector: Main contract selection engine.

4. Final output of the file:
   - Exported PointInTimeContractSelector, selection policies, and contract master providers.
"""

from datetime import date, datetime
from enum import Enum
from typing import Dict, List, NamedTuple, Optional, Protocol, Set, Tuple, Union
from packages.domain import ContractIdentifier, OptionType


class StrikeSelectionPolicy(str, Enum):
    """
    1. The use of class:
       Enumerates canonical strike selection strategies relative to underlying spot.

    2. What the class contains:
       - ATM: At-the-money (minimizes |strike - spot|).
       - ITM: In-the-money (depth 1..k).
       - OTM: Out-of-the-money (depth 1..k).
       - EXACT: Explicit strike target.

    3. Technologies used and why:
       str and Enum for deterministic JSON serialization and configuration.

    4. Key design and overall design of the class:
       Standardizes strike intent across strategy definitions.
    """
    ATM = "ATM"
    ITM = "ITM"
    OTM = "OTM"
    EXACT = "EXACT"


class ExpirySelectionPolicy(str, Enum):
    """
    1. The use of class:
       Enumerates canonical expiry resolution policies.

    2. What the class contains:
       - CURRENT_WEEK: Nearest active expiry date >= decision date.
       - NEXT_WEEK: Second nearest active expiry date.
       - MONTHLY: Monthly expiry (last expiry of current month).
       - EXACT: Specific explicit expiry date.

    3. Technologies used and why:
       str and Enum for configuration clarity.

    4. Key design and overall design of the class:
       Enables flexible expiry rollover rules without hardcoded calendar dates.
    """
    CURRENT_WEEK = "CURRENT_WEEK"
    NEXT_WEEK = "NEXT_WEEK"
    MONTHLY = "MONTHLY"
    EXACT = "EXACT"


class StrikePolicySpec(NamedTuple):
    """
    1. The use of class:
       Encapsulates a parsed strike policy and its associated depth or exact target.

    2. What the class contains:
       - policy: StrikeSelectionPolicy.
       - depth: Integer depth (0 for ATM, 1 for ITM_1/OTM_1, etc.).
       - exact_strike: Optional float target when policy is EXACT.

    3. Technologies used and why:
       NamedTuple for immutability and lightweight instantiation.

    4. Key design and overall design of the class:
       Separates strike policy intent from execution mechanics.
    """
    policy: StrikeSelectionPolicy
    depth: int = 0
    exact_strike: Optional[float] = None

    @classmethod
    def from_str(cls, spec_str: str) -> "StrikePolicySpec":
        """
        1. The use of function:
           Parses a string representation (e.g. 'ATM', 'ITM_1', 'OTM_2', 'EXACT:24000') into StrikePolicySpec.

        2. How does the specific function work:
           Splits on '_' or ':', detects policy token, and parses depth or float value.

        3. Concepts used in the function:
           String specification parsing.

        4. Places where this function is imported and used:
           Used by PointInTimeContractSelector to accept either objects or ergonomic strings.

        5. Final output of the function, before and after:
           Before: String specification. After: Structured StrikePolicySpec.
        """
        raw = spec_str.strip().upper()
        if raw == "ATM":
            return cls(policy=StrikeSelectionPolicy.ATM, depth=0)
        if raw.startswith("ITM"):
            parts = raw.split("_")
            depth = int(parts[1]) if len(parts) > 1 else 1
            return cls(policy=StrikeSelectionPolicy.ITM, depth=depth)
        if raw.startswith("OTM"):
            parts = raw.split("_")
            depth = int(parts[1]) if len(parts) > 1 else 1
            return cls(policy=StrikeSelectionPolicy.OTM, depth=depth)
        if raw.startswith("EXACT"):
            parts = raw.split(":") if ":" in raw else raw.split("_")
            strike_val = float(parts[1])
            return cls(policy=StrikeSelectionPolicy.EXACT, depth=0, exact_strike=strike_val)
        raise ValueError(f"Unrecognized strike policy specification: '{spec_str}'")


class ContractSelectionResult(NamedTuple):
    """
    1. The use of class:
       Immutable container recording the outcome of a point-in-time contract selection attempt.

    2. What the class contains:
       - selected_contract: ContractIdentifier if successfully selected, else None.
       - is_eligible: Boolean indicating data eligibility.
       - rejection_reason: Structured rejection code if selection failed.
       - spot_price: Spot price used during selection.
       - candidate_strikes: Available strikes considered.
       - resolved_expiry: Expiry date selected.

    3. Technologies used and why:
       NamedTuple for immutability, pattern matching, and logging.

    4. Key design and overall design of the class:
       Preserves full selection diagnostics to prevent silent lookups and ensure explainability.
    """
    selected_contract: Optional[ContractIdentifier]
    is_eligible: bool
    rejection_reason: Optional[str] = None
    spot_price: float = 0.0
    candidate_strikes: List[float] = []
    resolved_expiry: Optional[date] = None


class ContractMasterProvider(Protocol):
    """
    1. The use of class:
       Protocol interface defining methods required for querying the contract master and eligibility.

    2. What the class contains:
       - get_active_expiries: Returns sorted active expiry dates for an underlying on a given session date.
       - get_contracts_for_expiry: Returns contract records for an underlying, expiry, and option side.
       - is_contract_eligible: Checks whether contract passes point-in-time data eligibility.

    3. Technologies used and why:
       typing.Protocol for structural subtyping and clean separation of storage backends.

    4. Key design and overall design of the class:
       Decouples contract selection logic from DuckDB, SQLite, or in-memory fixtures.
    """

    def get_active_expiries(self, underlying: str, session_date: date) -> List[date]:
        """Returns sorted active expiry dates >= session_date for the given underlying."""
        ...

    def get_contracts_for_expiry(
        self,
        underlying: str,
        expiry: date,
        option_type: OptionType,
    ) -> List[ContractIdentifier]:
        """Returns all available contracts for underlying, expiry date, and option type."""
        ...

    def is_contract_eligible(self, session_date: date, contract_id: str) -> bool:
        """Returns True if the contract is eligible for trading on the session date."""
        ...


class InMemoryContractMaster:
    """
    1. The use of class:
       In-memory implementation of ContractMasterProvider for ultra-fast unit testing and golden oracle runs.

    2. What the class contains:
       - _contracts: List of registered ContractIdentifier records.
       - _ineligible_keys: Set of (session_date, contract_id) pairs marked ineligible.
       - add_contract(): Adds a tradable contract.
       - mark_ineligible(): Registers an eligibility defect.

    3. Technologies used and why:
       Python lists and sets for zero I/O overhead.

    4. Key design and overall design of the class:
       Enables deterministic testing of contract selection edge cases without external databases.
    """

    def __init__(self, contracts: Optional[List[ContractIdentifier]] = None) -> None:
        """Initializes InMemoryContractMaster with optional initial contract list."""
        self._contracts: List[ContractIdentifier] = list(contracts) if contracts else []
        self._ineligible_keys: Set[Tuple[date, str]] = set()

    def add_contract(self, contract: ContractIdentifier) -> None:
        """Adds a contract record to the in-memory master."""
        self._contracts.append(contract)

    def mark_ineligible(self, session_date: date, contract_id: str) -> None:
        """Marks a contract as ineligible on a specific session date."""
        self._ineligible_keys.add((session_date, contract_id))

    def get_active_expiries(self, underlying: str, session_date: date) -> List[date]:
        """Returns sorted active expiry dates >= session_date for the given underlying."""
        expiries = set()
        for c in self._contracts:
            if c.trading_symbol.startswith(underlying):
                exp_date = date.fromisoformat(c.expiry_date)
                if exp_date >= session_date:
                    expiries.add(exp_date)
        return sorted(list(expiries))

    def get_contracts_for_expiry(
        self,
        underlying: str,
        expiry: date,
        option_type: OptionType,
    ) -> List[ContractIdentifier]:
        """Returns all available contracts for underlying, expiry date, and option type."""
        exp_str = expiry.isoformat()
        matching = []
        for c in self._contracts:
            if (
                c.trading_symbol.startswith(underlying)
                and c.expiry_date == exp_str
                and c.option_type == option_type
            ):
                matching.append(c)
        return matching

    def is_contract_eligible(self, session_date: date, contract_id: str) -> bool:
        """Returns True if the contract is eligible for trading on the session date."""
        return (session_date, contract_id) not in self._ineligible_keys


class DuckDbContractMaster:
    """
    1. The use of class:
       Production ContractMasterProvider querying the active historical DuckDB data lake (quantview.duckdb).

    2. What the class contains:
       - _duckdb_path: Path to quantview.duckdb file.
       - Queries v_candles_options for unique contracts, expiries, strikes, and lot sizes.
       - Queries v_data_eligibility for defect tags and INELIGIBLE status flags.

    3. Technologies used and why:
       duckdb Python API for zero-copy analytical queries against Parquet-backed lake views.

    4. Key design and overall design of the class:
       Connects point-in-time contract selection directly to verified lake views.
    """

    def __init__(self, duckdb_path: str = "Data/lake/quantview.duckdb") -> None:
        """Initializes DuckDbContractMaster pointing to the local lake database."""
        self._duckdb_path = duckdb_path

    def _get_connection(self):
        """Returns read-only DuckDB connection."""
        import duckdb
        return duckdb.connect(self._duckdb_path, read_only=True)

    def get_active_expiries(self, underlying: str, session_date: date) -> List[date]:
        """Queries distinct expiries >= session_date for underlying symbol from v_candles_options."""
        con = self._get_connection()
        try:
            query = """
                SELECT DISTINCT expiry
                FROM v_candles_options
                WHERE symbol = ? AND expiry >= ?
                ORDER BY expiry ASC
            """
            rows = con.execute(query, [underlying, session_date]).fetchall()
            return [r[0] if isinstance(r[0], date) else date.fromisoformat(str(r[0])) for r in rows]
        finally:
            con.close()

    def get_contracts_for_expiry(
        self,
        underlying: str,
        expiry: date,
        option_type: OptionType,
    ) -> List[ContractIdentifier]:
        """Queries contracts for given underlying, expiry date, and option type."""
        con = self._get_connection()
        try:
            query = """
                SELECT DISTINCT contract_id, symbol, expiry, strike, option_type, lot_size_at_source
                FROM v_candles_options
                WHERE symbol = ? AND expiry = ? AND option_type = ?
                ORDER BY strike ASC
            """
            rows = con.execute(query, [underlying, expiry, option_type.value]).fetchall()
            contracts = []
            for r in rows:
                c_id, sym, exp, strike, opt_t, lot = r
                exp_str = exp.isoformat() if isinstance(exp, date) else str(exp)
                trading_sym = f"{sym} {int(strike) if strike == int(strike) else strike} {opt_t} {exp_str}"
                contracts.append(
                    ContractIdentifier(
                        instrument_key=str(c_id),
                        trading_symbol=trading_sym,
                        expiry_date=exp_str,
                        strike_price=float(strike),
                        option_type=OptionType(opt_t),
                        lot_size=int(lot) if lot else 25,
                    )
                )
            return contracts
        finally:
            con.close()

    def is_contract_eligible(self, session_date: date, contract_id: str) -> bool:
        """Queries v_data_eligibility to verify whether contract is flagged INELIGIBLE."""
        con = self._get_connection()
        try:
            query = """
                SELECT status
                FROM v_data_eligibility
                WHERE session_date = ? AND contract_id = ?
            """
            rows = con.execute(query, [session_date, contract_id]).fetchall()
            if not rows:
                return True
            for r in rows:
                if r[0] == "INELIGIBLE":
                    return False
            return True
        finally:
            con.close()


class PointInTimeContractSelector:
    """
    1. The use of class:
       Selects exact option contracts at decision time without look-ahead bias or silent substitution.

    2. What the class contains:
       - _provider: ContractMasterProvider instance.
       - resolve_expiry(): Selects target expiry date based on ExpirySelectionPolicy.
       - resolve_strike(): Selects strike from real available strikes based on StrikePolicySpec.
       - select_contract(): Main execution method returning ContractSelectionResult.

    3. Technologies used and why:
       Pure Python algorithmic resolution against discrete available strikes.

    4. Key design and overall design of the class:
       Enforces zero silent substitution: missing strikes or expiries immediately return structured rejections.
    """

    def __init__(self, provider: ContractMasterProvider) -> None:
        """Initializes PointInTimeContractSelector with a given contract provider."""
        self._provider = provider

    def _normalize_date(self, d: Union[date, datetime, str]) -> date:
        """Normalizes various date formats to a standard datetime.date."""
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, str):
            return date.fromisoformat(d.split("T")[0])
        if isinstance(d, date):
            return d
        raise TypeError(f"Date must be date, datetime, or str, got {type(d)}")

    def resolve_expiry(
        self,
        underlying: str,
        session_date: date,
        expiry_policy: Union[ExpirySelectionPolicy, str],
        target_expiry_date: Optional[date] = None,
    ) -> Optional[date]:
        """
        1. The use of function:
           Resolves the target expiry date according to the specified policy.

        2. How does the specific function work:
           - Retrieves active expiries >= session_date sorted chronologically.
           - CURRENT_WEEK: expiries[0].
           - NEXT_WEEK: expiries[1] if available.
           - MONTHLY: Latest expiry in the same month as expiries[0].
           - EXACT: Explicit target date match.

        3. Concepts used in the function:
           Point-in-time expiry resolution.

        4. Places where this function is imported and used:
           Called by select_contract.

        5. Final output of the function, before and after:
           Before: Expiry policy. After: Resolved date or None if unavailable.
        """
        active_expiries = self._provider.get_active_expiries(underlying, session_date)
        if not active_expiries:
            return None

        pol = (
            expiry_policy
            if isinstance(expiry_policy, ExpirySelectionPolicy)
            else ExpirySelectionPolicy(expiry_policy.upper())
        )

        if pol == ExpirySelectionPolicy.CURRENT_WEEK:
            return active_expiries[0]

        if pol == ExpirySelectionPolicy.NEXT_WEEK:
            return active_expiries[1] if len(active_expiries) > 1 else None

        if pol == ExpirySelectionPolicy.MONTHLY:
            # Last expiry in the same month as the nearest active expiry
            base_month = active_expiries[0].month
            base_year = active_expiries[0].year
            same_month = [e for e in active_expiries if e.month == base_month and e.year == base_year]
            return same_month[-1] if same_month else active_expiries[0]

        if pol == ExpirySelectionPolicy.EXACT:
            if target_expiry_date is None:
                raise ValueError("target_expiry_date must be provided for EXACT expiry policy")
            return target_expiry_date if target_expiry_date in active_expiries else None

        return None

    def resolve_strike(
        self,
        spot_price: float,
        available_strikes: List[float],
        option_type: OptionType,
        policy_spec: StrikePolicySpec,
    ) -> Optional[float]:
        """
        1. The use of function:
           Resolves a single strike price from available strikes according to policy without substitution.

        2. How does the specific function work:
           - Finds ATM strike s* minimizing |s - spot| with lower-strike tie-breaking.
           - For CE:
             * ITM_k: k-th strike below s* in descending order (s < s*).
             * OTM_k: k-th strike above s* in ascending order (s > s*).
           - For PE:
             * ITM_k: k-th strike above s* in ascending order (s > s*).
             * OTM_k: k-th strike below s* in descending order (s < s*).
           - For EXACT: Direct membership test in available_strikes.
           - If requested strike index is out of bounds, returns None (no substitution).

        3. Concepts used in the function:
           Option moneyness conventions and exact strike selection.

        4. Places where this function is imported and used:
           Called by select_contract.

        5. Final output of the function, before and after:
           Before: Spot, available strikes, policy. After: Exact float strike or None.
        """
        if not available_strikes:
            return None

        strikes = sorted(list(set(available_strikes)))

        # Find ATM strike: minimizes absolute distance to spot. If tie, prefer lower strike.
        atm_strike = min(strikes, key=lambda s: (abs(s - spot_price), s))

        if policy_spec.policy == StrikeSelectionPolicy.ATM:
            return atm_strike

        if policy_spec.policy == StrikeSelectionPolicy.EXACT:
            if policy_spec.exact_strike is None:
                return None
            return policy_spec.exact_strike if policy_spec.exact_strike in strikes else None

        depth = max(1, policy_spec.depth)

        if option_type == OptionType.CE:
            if policy_spec.policy == StrikeSelectionPolicy.ITM:
                # Strikes strictly below ATM, sorted descending (closest to ATM first)
                itm_strikes = sorted([s for s in strikes if s < atm_strike], reverse=True)
                return itm_strikes[depth - 1] if len(itm_strikes) >= depth else None
            elif policy_spec.policy == StrikeSelectionPolicy.OTM:
                # Strikes strictly above ATM, sorted ascending (closest to ATM first)
                otm_strikes = sorted([s for s in strikes if s > atm_strike])
                return otm_strikes[depth - 1] if len(otm_strikes) >= depth else None

        elif option_type == OptionType.PE:
            if policy_spec.policy == StrikeSelectionPolicy.ITM:
                # For Put, ITM strikes are strictly above spot/ATM
                itm_strikes = sorted([s for s in strikes if s > atm_strike])
                return itm_strikes[depth - 1] if len(itm_strikes) >= depth else None
            elif policy_spec.policy == StrikeSelectionPolicy.OTM:
                # For Put, OTM strikes are strictly below spot/ATM
                otm_strikes = sorted([s for s in strikes if s < atm_strike], reverse=True)
                return otm_strikes[depth - 1] if len(otm_strikes) >= depth else None

        return None

    def select_contract(
        self,
        trade_date: Union[date, datetime, str],
        spot_price: float,
        option_type: OptionType,
        strike_policy: Union[StrikePolicySpec, str] = "ATM",
        expiry_policy: Union[ExpirySelectionPolicy, str] = ExpirySelectionPolicy.CURRENT_WEEK,
        underlying_symbol: str = "NIFTY",
        target_expiry_date: Optional[date] = None,
    ) -> ContractSelectionResult:
        """
        1. The use of function:
           Authoritative point-in-time selection method for an option contract.

        2. How does the specific function work:
           - Normalizes trade_date and strike policy.
           - Resolves active expiry date via resolve_expiry. Returns NO_ELIGIBLE_CONTRACT if none.
           - Fetches active contracts for the resolved expiry and option type.
           - Extracts available strikes and resolves target strike via resolve_strike.
           - Matches the specific ContractIdentifier.
           - Checks data eligibility in v_data_eligibility. If ineligible, returns CONTRACT_DATA_INELIGIBLE.
           - Returns ContractSelectionResult with full diagnostic trace.

        3. Concepts used in the function:
           Point-in-time contract resolution, zero look-ahead, zero silent substitution.

        4. Places where this function is imported and used:
           Used by Strategy orchestrators, Signal evaluators, and Backtest Fill Engine.

        5. Final output of the function, before and after:
           Before: Market parameters and selection intent. After: ContractSelectionResult.
        """
        session_date = self._normalize_date(trade_date)
        spec = (
            strike_policy
            if isinstance(strike_policy, StrikePolicySpec)
            else StrikePolicySpec.from_str(strike_policy)
        )

        resolved_exp = self.resolve_expiry(
            underlying=underlying_symbol,
            session_date=session_date,
            expiry_policy=expiry_policy,
            target_expiry_date=target_expiry_date,
        )

        if resolved_exp is None:
            return ContractSelectionResult(
                selected_contract=None,
                is_eligible=False,
                rejection_reason="NO_ELIGIBLE_CONTRACT",
                spot_price=spot_price,
                candidate_strikes=[],
                resolved_expiry=None,
            )

        contracts = self._provider.get_contracts_for_expiry(
            underlying=underlying_symbol,
            expiry=resolved_exp,
            option_type=option_type,
        )

        if not contracts:
            return ContractSelectionResult(
                selected_contract=None,
                is_eligible=False,
                rejection_reason="NO_ELIGIBLE_CONTRACT",
                spot_price=spot_price,
                candidate_strikes=[],
                resolved_expiry=resolved_exp,
            )

        available_strikes = sorted(list(set(c.strike_price for c in contracts)))
        resolved_strike = self.resolve_strike(
            spot_price=spot_price,
            available_strikes=available_strikes,
            option_type=option_type,
            policy_spec=spec,
        )

        if resolved_strike is None:
            return ContractSelectionResult(
                selected_contract=None,
                is_eligible=False,
                rejection_reason="NO_ELIGIBLE_CONTRACT",
                spot_price=spot_price,
                candidate_strikes=available_strikes,
                resolved_expiry=resolved_exp,
            )

        # Match contract by strike
        chosen_contract: Optional[ContractIdentifier] = None
        for c in contracts:
            if c.strike_price == resolved_strike:
                chosen_contract = c
                break

        if chosen_contract is None:
            return ContractSelectionResult(
                selected_contract=None,
                is_eligible=False,
                rejection_reason="NO_ELIGIBLE_CONTRACT",
                spot_price=spot_price,
                candidate_strikes=available_strikes,
                resolved_expiry=resolved_exp,
            )

        # Check data eligibility
        is_eligible = self._provider.is_contract_eligible(session_date, chosen_contract.instrument_key)
        if not is_eligible:
            return ContractSelectionResult(
                selected_contract=chosen_contract,
                is_eligible=False,
                rejection_reason="CONTRACT_DATA_INELIGIBLE",
                spot_price=spot_price,
                candidate_strikes=available_strikes,
                resolved_expiry=resolved_exp,
            )

        return ContractSelectionResult(
            selected_contract=chosen_contract,
            is_eligible=True,
            rejection_reason=None,
            spot_price=spot_price,
            candidate_strikes=available_strikes,
            resolved_expiry=resolved_exp,
        )
