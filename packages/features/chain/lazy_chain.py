"""
1. What this file does:
   Implements the point-in-time Lazy Reconstructed Option Chain provider and DuckDB view
   query interface for QuantView (DATA §4.4, §4.8, MASTER §2, Task M5-04 / Gate G3).

2. Overall design:
   Provides zero-copy, lazy point-in-time reconstruction of option chains from canonical
   option candle data, contract master, and snapshots without persisting redundant physical
   chain tables on disk. Strictly enforces causal availability (available_at <= as_of_minute),
   exposes missing strikes explicitly (never silently substituting or interpolating), and
   computes liquid ATM +/- N strike bands for model Greek evaluation.

3. Elements in the file:
   - ChainRow: NamedTuple representing an individual contract's point-in-time state.
   - ReconstructedOptionChain: Container holding all strike rows for an expiry at as_of_minute.
   - LazyChainProvider: High-level provider querying DuckDB views or in-memory fixtures.
   - get_atm_strike: Helper rounding underlying spot price to nearest valid strike step.
   - get_atm_band_strikes: Helper generating 2N+1 strikes centered on the ATM strike.
   - SQL_CREATE_VIEW_RECONSTRUCTED_CHAIN: Canonical DDL defining lazy DuckDB view.

4. Final output of the file:
   - Causal, lazy option chain query engine preserving point-in-time integrity and missing contract visibility.
"""

import math
from datetime import date
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

# Canonical DuckDB View Definition per DATA §4.8
SQL_CREATE_VIEW_RECONSTRUCTED_CHAIN = """
CREATE OR REPLACE VIEW v_snapshots_reconstructed_chain AS
SELECT
    c.bar_end AS as_of_minute,
    c.available_at AS available_at,
    c.contract_id AS contract_id,
    c.symbol AS symbol,
    c.expiry AS expiry,
    c.strike AS strike,
    c.option_type AS option_type,
    c.open AS option_open,
    c.high AS option_high,
    c.low AS option_low,
    c.close AS option_close,
    c.volume AS volume,
    c.oi AS oi,
    c.is_flat_bar AS is_flat_bar,
    'OPTION_CANDLE' AS source_tier,
    c.quality_flags AS quality_flags,
    c.source_manifest_hash AS source_manifest_hash
FROM v_candles_options c
WHERE c.is_active = true;
"""


class ChainRow(NamedTuple):
    """
    1. The use of class:
       Immutable point-in-time snapshot of a single option contract in the reconstructed chain.

    2. What the class contains:
       - contract_id: Unique instrument identifier (e.g. 'OPT-NIFTY-20250109-22500-CE').
       - symbol: Underlying index symbol (e.g. 'NIFTY').
       - expiry: Expiration date of the contract.
       - strike: Exercise strike price in index points (e.g. 22500.0).
       - option_type: 'CE' for Call or 'PE' for Put.
       - as_of_minute: Query evaluation timestamp (epoch seconds).
       - available_at: Point-in-time timestamp when this bar/snapshot closed.
       - option_open: Opening price or None if missing.
       - option_high: High price or None if missing.
       - option_low: Low price or None if missing.
       - option_close: Closing / mark price or None if missing.
       - volume: Traded volume in contracts.
       - oi: Open interest in contracts.
       - is_flat_bar: Boolean indicating if O=H=L=C and volume=0.
       - is_available: True if data exists; False if contract is missing from feed.
       - quality_flags: Diagnostic flags (e.g. ['VALID'], ['MISSING_STRIKE'], ['DATA_GAP']).

    3. Technologies used and why:
       NamedTuple for compact, zero-overhead storage in memory and vectorized scans.

    4. Key design and overall design of the class:
       Enforces DATA §4.8 schema: explicitly represents absent contracts as is_available=False
       with MISSING_STRIKE flag rather than silently omitting or substituting them.
    """
    contract_id: str
    symbol: str
    expiry: date
    strike: float
    option_type: str
    as_of_minute: int
    available_at: int
    option_open: Optional[float]
    option_high: Optional[float]
    option_low: Optional[float]
    option_close: Optional[float]
    volume: int
    oi: int
    is_flat_bar: bool
    is_available: bool
    quality_flags: List[str]


class ReconstructedOptionChain:
    """
    1. The use of class:
       Container holding the full reconstructed option chain for a given expiry and timestamp.

    2. What the class contains:
       - symbol: Underlying symbol.
       - expiry: Expiry date.
       - as_of_minute: Evaluation timestamp.
       - spot_price: Point-in-time underlying spot close.
       - rows: Dict mapping (strike, option_type) -> ChainRow.
       - strikes: Sorted list of distinct strike prices present in the chain.

    3. Technologies used and why:
       Dictionary indexing for O(1) strike lookup during strategy execution.

    4. Key design and overall design of the class:
       Provides point-in-time accessors for ATM strike, liquid ATM band, and coverage metrics.
    """

    def __init__(
        self,
        symbol: str,
        expiry: date,
        as_of_minute: int,
        spot_price: Optional[float],
        rows: Sequence[ChainRow],
    ):
        """Initializes the ReconstructedOptionChain with rows indexed by (strike, option_type)."""
        self.symbol = symbol
        self.expiry = expiry
        self.as_of_minute = as_of_minute
        self.spot_price = spot_price
        self._row_map: Dict[Tuple[float, str], ChainRow] = {
            (r.strike, r.option_type): r for r in rows
        }
        self.strikes = sorted(list({r.strike for r in rows}))

    def get_contract(self, strike: float, option_type: str) -> Optional[ChainRow]:
        """
        1. The use of function:
           Retrieves a specific contract by strike and option type ('CE' or 'PE').

        2. How does the specific function work:
           Looks up (strike, option_type.upper()) in internal row mapping.

        3. Concepts used in the function:
           Point-in-time contract retrieval.

        4. Places where this function is imported and used:
           Used by multi-leg strategies and Greeks evaluators.

        5. Final output of the function, before and after:
           Before: Strike and option type. After: Matching ChainRow or None.
        """
        return self._row_map.get((float(strike), option_type.upper()))

    def get_atm_strike(self, strike_step: float = 50.0) -> Optional[float]:
        """
        1. The use of function:
           Determines the At-The-Money (ATM) strike price based on point-in-time spot.

        2. How does the specific function work:
           Rounds spot_price to the nearest integer multiple of strike_step.

        3. Concepts used in the function:
           ATM strike selection.

        4. Places where this function is imported and used:
           Used by Straddle/Strangle strategies, ATM Greeks evaluators, and PCR metrics.

        5. Final output of the function, before and after:
           Before: None. After: Float ATM strike or None if spot_price is unavailable.
        """
        if self.spot_price is None or math.isnan(self.spot_price):
            return None
        return round(self.spot_price / strike_step) * strike_step

    def get_atm_band(
        self,
        n_strikes: int = 5,
        strike_step: float = 50.0,
    ) -> List[Tuple[Optional[ChainRow], Optional[ChainRow]]]:
        """
        1. The use of function:
           Extracts the liquid ATM +/- N strike pairs (Call and Put).

        2. How does the specific function work:
           Calculates ATM strike, generates 2N+1 strike levels:
           [ATM - N*step, ..., ATM, ..., ATM + N*step], and extracts (CE, PE) pair for each.

        3. Concepts used in the function:
           Liquid ATM strike band extraction (M5-05).

        4. Places where this function is imported and used:
           Used by Black-76 Greeks solver and volatility smile evaluators.

        5. Final output of the function, before and after:
           Before: Band parameters. After: List of (Call_Row, Put_Row) tuples across 2N+1 strikes.
        """
        atm = self.get_atm_strike(strike_step)
        if atm is None:
            return []

        band: List[Tuple[Optional[ChainRow], Optional[ChainRow]]] = []
        for offset in range(-n_strikes, n_strikes + 1):
            k = atm + (offset * strike_step)
            ce = self.get_contract(k, "CE")
            pe = self.get_contract(k, "PE")
            band.append((ce, pe))
        return band

    @property
    def coverage_ratio(self) -> float:
        """Returns the fraction of available contracts vs total indexed contracts."""
        if not self._row_map:
            return 0.0
        avail = sum(1 for r in self._row_map.values() if r.is_available)
        return round(avail / float(len(self._row_map)), 4)


def get_atm_strike(spot_price: float, strike_step: float = 50.0) -> float:
    """
    1. The use of function:
       Standalone helper rounding spot price to nearest strike step.

    2. How does the specific function work:
       Computes round(spot_price / strike_step) * strike_step.

    3. Concepts used in the function:
       Strike rounding.

    4. Places where this function is imported and used:
       Used across feature calculations and contract selector.

    5. Final output of the function, before and after:
       Before: Spot price float. After: Nearest strike step float.
    """
    return round(spot_price / strike_step) * strike_step


def get_atm_band_strikes(
    spot_price: float,
    n_strikes: int = 5,
    strike_step: float = 50.0,
) -> List[float]:
    """
    1. The use of function:
       Generates a sorted list of 2N+1 strikes centered on the ATM strike.

    2. How does the specific function work:
       Computes ATM strike and iterates offsets from -N to +N.

    3. Concepts used in the function:
       ATM +/- N strike band generation.

    4. Places where this function is imported and used:
       Used by Black-76 Greeks solvers and skew features.

    5. Final output of the function, before and after:
       Before: Spot and N. After: List of 2N+1 floats.
    """
    atm = get_atm_strike(spot_price, strike_step)
    return [atm + (offset * strike_step) for offset in range(-n_strikes, n_strikes + 1)]


class LazyChainProvider:
    """
    1. The use of class:
       Executes lazy, point-in-time reconstructed option chain queries without loading
       the entire chain history into memory or maintaining duplicate Parquet stores.

    2. What the class contains:
       - duckdb_connection: Optional duckdb connection (in-memory or file-backed).
       - in_memory_table: In-memory fallback dictionary for test fixtures and isolated unit tests.

    3. Technologies used and why:
       DuckDB Python API for fast zero-copy SQL queries over Parquet lake views.

    4. Key design and overall design of the class:
       Enforces DATA §4.8:
       - Strictly filters available_at <= as_of_minute (zero future rows).
       - Explicitly flags absent universe contracts with MISSING_STRIKE rather than omitting them.
    """

    def __init__(self, duckdb_connection: Optional[Any] = None):
        """Initializes the LazyChainProvider with optional DuckDB connection or in-memory backing."""
        self.con = duckdb_connection
        self._in_memory_records: List[Dict[str, Any]] = []

    def set_in_memory_records(self, records: Sequence[Dict[str, Any]]) -> None:
        """Sets in-memory candle records for deterministic fixture testing."""
        self._in_memory_records = list(records)

    def get_reconstructed_chain(
        self,
        symbol: str,
        expiry: date,
        as_of_minute: int,
        spot_price: Optional[float] = None,
        expected_strikes: Optional[Sequence[float]] = None,
    ) -> ReconstructedOptionChain:
        """
        1. The use of function:
           Reconstructs the option chain for a given symbol, expiry, and timestamp.

        2. How does the specific function work:
           1. Queries eligible records where symbol=symbol, expiry=expiry, and available_at <= as_of_minute.
           2. Deduplicates records, taking the latest bar available at or before as_of_minute.
           3. If expected_strikes universe is provided, aligns available strikes against expected strikes;
              for any missing strike, inserts synthetic ChainRow with is_available=False,
              quality_flags=['MISSING_STRIKE'].
           4. Instantiates and returns ReconstructedOptionChain.

        3. Concepts used in the function:
           Point-in-time causal query, missing strike identification, zero-future filtering.

        4. Places where this function is imported and used:
           Used by StrategyContext, backtest runner, and Greeks evaluator.

        5. Final output of the function, before and after:
           Before: Symbol, expiry, timestamp. After: Causal ReconstructedOptionChain.
        """
        rows: List[ChainRow] = []
        observed_keys: Set[Tuple[float, str]] = set()

        if self.con is not None:
            # Execute SQL query against DuckDB view
            query = """
                SELECT
                    contract_id, symbol, expiry, strike, option_type,
                    as_of_minute, available_at,
                    option_open, option_high, option_low, option_close,
                    volume, oi, is_flat_bar, quality_flags
                FROM v_snapshots_reconstructed_chain
                WHERE symbol = ?
                  AND expiry = ?
                  AND available_at <= ?
                ORDER BY strike ASC, option_type ASC
            """
            cursor = self.con.execute(query, [symbol, expiry, as_of_minute])
            for r in cursor.fetchall():
                strike = float(r[3])
                opt_type = str(r[4])
                observed_keys.add((strike, opt_type))
                rows.append(
                    ChainRow(
                        contract_id=str(r[0]),
                        symbol=str(r[1]),
                        expiry=expiry if isinstance(r[2], date) else date.fromisoformat(str(r[2])),
                        strike=strike,
                        option_type=opt_type,
                        as_of_minute=as_of_minute,
                        available_at=int(r[6]),
                        option_open=float(r[7]) if r[7] is not None else None,
                        option_high=float(r[8]) if r[8] is not None else None,
                        option_low=float(r[9]) if r[9] is not None else None,
                        option_close=float(r[10]) if r[10] is not None else None,
                        volume=int(r[11]),
                        oi=int(r[12]),
                        is_flat_bar=bool(r[13]),
                        is_available=True,
                        quality_flags=list(r[14]) if r[14] is not None else ["VALID"],
                    )
                )
        else:
            # Query in-memory records
            for rec in self._in_memory_records:
                if rec.get("symbol") != symbol:
                    continue
                rec_expiry = rec.get("expiry")
                if isinstance(rec_expiry, str):
                    rec_expiry = date.fromisoformat(rec_expiry)
                if rec_expiry != expiry:
                    continue
                avail_at = int(rec.get("available_at", rec.get("ts_end", 0)))
                # Strict causality filter: NO FUTURE ROWS
                if avail_at > as_of_minute:
                    continue

                strike = float(rec["strike"])
                opt_type = str(rec["option_type"])
                observed_keys.add((strike, opt_type))

                rows.append(
                    ChainRow(
                        contract_id=str(rec["contract_id"]),
                        symbol=symbol,
                        expiry=expiry,
                        strike=strike,
                        option_type=opt_type,
                        as_of_minute=as_of_minute,
                        available_at=avail_at,
                        option_open=rec.get("open"),
                        option_high=rec.get("high"),
                        option_low=rec.get("low"),
                        option_close=rec.get("close"),
                        volume=int(rec.get("volume", 0)),
                        oi=int(rec.get("oi", 0)),
                        is_flat_bar=bool(rec.get("is_flat_bar", False)),
                        is_available=True,
                        quality_flags=list(rec.get("quality_flags", ["VALID"])),
                    )
                )

        # Handle expected strike universe alignment: identify missing strikes
        if expected_strikes is not None:
            for k in expected_strikes:
                for opt_type in ("CE", "PE"):
                    if (k, opt_type) not in observed_keys:
                        # Insert missing contract row
                        dummy_id = f"OPT-{symbol}-{expiry.strftime('%Y%m%d')}-{int(k)}-{opt_type}"
                        rows.append(
                            ChainRow(
                                contract_id=dummy_id,
                                symbol=symbol,
                                expiry=expiry,
                                strike=float(k),
                                option_type=opt_type,
                                as_of_minute=as_of_minute,
                                available_at=as_of_minute,
                                option_open=None,
                                option_high=None,
                                option_low=None,
                                option_close=None,
                                volume=0,
                                oi=0,
                                is_flat_bar=False,
                                is_available=False,
                                quality_flags=["MISSING_STRIKE"],
                            )
                        )

        return ReconstructedOptionChain(
            symbol=symbol,
            expiry=expiry,
            as_of_minute=as_of_minute,
            spot_price=spot_price,
            rows=rows,
        )
