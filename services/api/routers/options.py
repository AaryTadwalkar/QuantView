"""
1. What this file does:
   Implements the Option Chain, Expiries, and Option Historical Candlesticks REST API endpoints
   for the QuantView FastAPI Gateway (Milestones M6-03b, M6-15, M6-18, and Release Gate G4).

2. Overall design:
   Exposes high-performance analytical endpoints querying DuckDB lake views:
     - GET /api/v1/options/expiries: Retrieves sorted list of available option expiry dates.
     - GET /api/v1/options/chain: Reconstructs Call/Put option chain matrix centered around ATM
       strike with spot price, Greeks, depth, volume, and open interest.
     - GET /api/v1/options/candles: Retrieves chronologically sorted OHLCV bars for specific option
       contracts by contract_id or (strike, option_type, expiry).
   Optimized with indexed snapshot captures (sub-150ms) and graceful fallback chaining.

3. Elements in the file:
   - router: FastAPI APIRouter configured with /api/v1/options prefix and options tags.
   - get_expiries: Endpoint serving available contract expiry dates.
   - get_option_chain: Endpoint reconstructing multi-strike option chain matrix around ATM.
   - get_option_candles: Endpoint serving single-contract candlestick time-series bars.

4. Final output of the file:
   - Exported APIRouter instance for registration in services.api.main.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import duckdb
from fastapi import APIRouter, Depends, Query

from services.api.deps import get_duckdb
from services.api.routers.market import normalize_symbol
from services.api.schemas.market import Candle
from services.api.schemas.options import (
    OptionCandleResponse,
    OptionChainResponse,
    OptionChainRow,
    OptionStrikeQuote,
)

router = APIRouter(prefix="/api/v1/options", tags=["options"])


@router.get(
    "/expiries",
    response_model=List[str],
    summary="Available Option Expiries",
    description="Returns sorted list of available option contract expiry dates in YYYY-MM-DD format.",
)
def get_expiries(
    underlying: str = Query(default="NIFTY", description="Underlying asset symbol (e.g. NIFTY, NSE:NIFTY50)"),
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb),
) -> List[str]:
    """
    1. The use of function:
       FastAPI endpoint returning distinct option contract expiry dates available in the analytical lake.

    2. How does the specific function work:
       - Normalizes the input underlying symbol to canonical representation.
       - Queries distinct expiry dates from v_snapshots_reconstructed_chain and v_candles_options using a UNION query.
       - If tables are missing or query fails, degrades gracefully through individual table checks or returns empty list.
       - Returns a chronologically sorted list of YYYY-MM-DD formatted date strings.

    3. Concepts used in the function:
       Analytical distinct projections, UNION query optimization, graceful degradation, symbol normalization.

    4. Places where this function is imported and used:
       Registered with the options router under GET /api/v1/options/expiries.

    5. Final output of the function, before and after:
       Before: Underlying query parameter. After: Sorted list of expiry date strings.
    """
    canon_symbol, is_vix = normalize_symbol(underlying)
    if is_vix:
        return []

    try:
        query = """
            SELECT DISTINCT CAST(expiry AS VARCHAR) as expiry
            FROM (
                SELECT expiry FROM v_snapshots_captures WHERE expiry IS NOT NULL
                UNION ALL
                SELECT expiry FROM v_candles_options WHERE expiry IS NOT NULL AND symbol = ?
            )
            ORDER BY expiry ASC
        """
        rows = conn.execute(query, [canon_symbol]).fetchall()
        return [str(row[0]) for row in rows]
    except duckdb.Error:
        for fallback_query, params in [
            (
                "SELECT DISTINCT CAST(expiry AS VARCHAR) FROM v_candles_options WHERE expiry IS NOT NULL AND symbol = ? ORDER BY expiry ASC",
                [canon_symbol],
            ),
            (
                "SELECT DISTINCT CAST(expiry AS VARCHAR) FROM v_snapshots_captures WHERE expiry IS NOT NULL ORDER BY expiry ASC",
                [],
            ),
            (
                "SELECT DISTINCT CAST(expiry AS VARCHAR) FROM v_snapshots_reconstructed_chain WHERE expiry IS NOT NULL ORDER BY expiry ASC",
                [],
            ),
        ]:
            try:
                rows = conn.execute(fallback_query, params).fetchall()
                if rows:
                    return [str(row[0]) for row in rows]
            except duckdb.Error:
                continue
        return []


@router.get(
    "/chain",
    response_model=OptionChainResponse,
    summary="Option Chain Matrix",
    description="Queries reconstructed snapshot option chain with CE/PE pairing centered around ATM strike.",
)
def get_option_chain(
    expiry_date: Optional[str] = Query(
        default=None, description="Expiry date in YYYY-MM-DD format (defaults to nearest)"
    ),
    spot_price: Optional[float] = Query(default=None, description="Optional spot price override for ATM centering"),
    strike_count: int = Query(
        default=15, ge=1, le=50, description="Strikes count above and below ATM (default 15 -> 31 rows)"
    ),
    underlying: str = Query(default="NIFTY", description="Underlying asset symbol (e.g. NIFTY)"),
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb),
) -> OptionChainResponse:
    """
    1. The use of function:
       FastAPI endpoint reconstructing the dual-column option chain matrix for a given expiry.

    2. How does the specific function work:
       - Determines target expiry: uses explicit expiry_date if provided, otherwise queries available expiries
         and selects the nearest future expiry (or latest available expiry for historical lake data).
       - Queries latest snapshot in v_snapshots_reconstructed_chain for target expiry, extracting quotes,
         Greeks, depth, and spot price.
       - Falls back to v_candles_options if snapshots are unavailable for that expiry date.
       - Resolves underlying spot price from snapshot, parameter override, or v_candles_underlying close.
       - Computes At-The-Money (ATM) strike using round(spot_price / 50.0) * 50.0.
       - Generates strike sequence centered at ATM: [atm - strike_count*50, ..., atm + strike_count*50].
       - Pairs Call (CE) and Put (PE) quotes into OptionChainRow items.
       - Returns populated OptionChainResponse, or graceful empty response if no data exists.

    3. Concepts used in the function:
       Option chain reconstruction, ATM strike centering, Call/Put pairing, Black-Scholes Greeks mapping,
       graceful fallback chaining.

    4. Places where this function is imported and used:
       Registered with the options router under GET /api/v1/options/chain.

    5. Final output of the function, before and after:
       Before: Query parameters for expiry, spot, and strike range. After: OptionChainResponse model.
    """
    underlying_str = underlying if isinstance(underlying, str) else "NIFTY"
    canon_symbol, _ = normalize_symbol(underlying_str)
    target_expiry = expiry_date.strip() if isinstance(expiry_date, str) and expiry_date.strip() else None
    snapshot_time = 0
    resolved_spot: Optional[float] = spot_price if isinstance(spot_price, (int, float)) else None
    strike_cnt = strike_count if isinstance(strike_count, int) else 15
    quotes_map: Dict[Tuple[float, str], OptionStrikeQuote] = {}
    snapshot_id: Optional[str] = None

    try:
        if target_expiry:
            cap = conn.execute(
                "SELECT snapshot_id, received_at, CAST(expiry AS VARCHAR), spot_price "
                "FROM v_snapshots_captures WHERE expiry = ? AND underlying = ? ORDER BY received_at DESC LIMIT 1",
                [target_expiry, canon_symbol],
            ).fetchone()
        else:
            cap = conn.execute(
                "SELECT snapshot_id, received_at, CAST(expiry AS VARCHAR), spot_price "
                "FROM v_snapshots_captures WHERE underlying = ? ORDER BY received_at DESC LIMIT 1",
                [canon_symbol],
            ).fetchone()

        if cap:
            snapshot_id = str(cap[0])
            if hasattr(cap[1], "timestamp"):
                snapshot_time = int(cap[1].timestamp())
            elif isinstance(cap[1], str):
                try:
                    snapshot_time = int(datetime.fromisoformat(cap[1].replace("Z", "+00:00")).timestamp())
                except Exception:
                    snapshot_time = 0
            if not target_expiry:
                target_expiry = str(cap[2])
            if resolved_spot is None and cap[3] is not None and float(cap[3]) > 0.0:
                resolved_spot = float(cap[3])
    except duckdb.Error:
        pass

    if snapshot_id:
        try:
            query_sql = """
                SELECT
                    CAST(strike AS DOUBLE) as strike,
                    option_type,
                    COALESCE(ltp, 0.0) as ltp,
                    COALESCE(bid, 0.0) as bid,
                    COALESCE(ask, 0.0) as ask,
                    COALESCE(oi, 0) as oi,
                    COALESCE(volume, 0) as volume,
                    COALESCE(iv_observed, 0.0) as iv,
                    COALESCE(delta_observed, 0.0) as delta,
                    COALESCE(gamma_observed, 0.0) as gamma,
                    COALESCE(theta_observed, 0.0) as theta,
                    COALESCE(vega_observed, 0.0) as vega,
                    COALESCE(change_oi, 0) as oi_change
                FROM v_snapshots_rows
                WHERE snapshot_id = ?
            """
            params: list[Any] = [snapshot_id]
            if target_expiry:
                query_sql += " AND expiry = ?"
                params.append(target_expiry)
            query_sql += " ORDER BY strike ASC"
            rows = conn.execute(query_sql, params).fetchall()

            for r in rows:
                strike_val = float(r[0])
                opt_type = str(r[1]).upper()
                ltp_val = float(r[2])
                bid_val = float(r[3])
                ask_val = float(r[4])
                if ltp_val == 0.0 and (bid_val > 0.0 or ask_val > 0.0):
                    ltp_val = (
                        round((bid_val + ask_val) / 2.0, 2) if (bid_val > 0 and ask_val > 0) else max(bid_val, ask_val)
                    )

                display_strike = int(strike_val) if strike_val.is_integer() else strike_val
                trading_sym = f"{canon_symbol} {display_strike} {opt_type}"

                quotes_map[(strike_val, opt_type)] = OptionStrikeQuote(
                    trading_symbol=trading_sym,
                    strike=strike_val,
                    option_type=opt_type,
                    ltp=ltp_val,
                    change=0.0,
                    change_pct=0.0,
                    bid=bid_val,
                    ask=ask_val,
                    oi=int(r[5]),
                    oi_change=int(r[12]),
                    iv=float(r[7]),
                    delta=float(r[8]),
                    gamma=float(r[9]),
                    theta=float(r[10]),
                    vega=float(r[11]),
                    volume=int(r[6]),
                )
        except duckdb.Error:
            pass

    if not quotes_map:
        if not target_expiry:
            all_expiries = get_expiries(underlying=underlying, conn=conn)
            if not all_expiries:
                return OptionChainResponse(
                    underlying=canon_symbol,
                    expiry_date="",
                    spot_price=spot_price or 0.0,
                    atm_strike=0.0,
                    timestamp=0,
                    strikes=[],
                )
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            future_expiries = [e for e in all_expiries if e >= today_str]
            target_expiry = future_expiries[0] if future_expiries else all_expiries[-1]

        try:
            time_res = conn.execute(
                "SELECT MAX(as_of_time), MAX(spot_price) FROM v_snapshots_reconstructed_chain WHERE expiry = ?",
                [target_expiry],
            ).fetchone()
            latest_as_of = time_res[0] if time_res else None

            if latest_as_of is not None:
                if hasattr(latest_as_of, "timestamp"):
                    snapshot_time = int(latest_as_of.timestamp())
                if resolved_spot is None and time_res[1] is not None and float(time_res[1]) > 0.0:
                    resolved_spot = float(time_res[1])

                rows = conn.execute(
                    """
                    SELECT
                        CAST(strike AS DOUBLE) as strike,
                        option_type,
                        COALESCE(ltp, 0.0) as ltp,
                        COALESCE(bid, 0.0) as bid,
                        COALESCE(ask, 0.0) as ask,
                        COALESCE(oi, 0) as oi,
                        COALESCE(volume, 0) as volume,
                        COALESCE(iv_observed, 0.0) as iv,
                        COALESCE(delta_observed, 0.0) as delta,
                        COALESCE(gamma_observed, 0.0) as gamma,
                        COALESCE(theta_observed, 0.0) as theta,
                        COALESCE(vega_observed, 0.0) as vega
                    FROM v_snapshots_reconstructed_chain
                    WHERE expiry = ? AND as_of_time = ?
                    ORDER BY strike ASC
                    """,
                    [target_expiry, latest_as_of],
                ).fetchall()

                for r in rows:
                    strike_val = float(r[0])
                    opt_type = str(r[1]).upper()
                    ltp_val = float(r[2])
                    bid_val = float(r[3])
                    ask_val = float(r[4])
                    if ltp_val == 0.0 and (bid_val > 0.0 or ask_val > 0.0):
                        ltp_val = (
                            round((bid_val + ask_val) / 2.0, 2)
                            if (bid_val > 0 and ask_val > 0)
                            else max(bid_val, ask_val)
                        )

                    display_strike = int(strike_val) if strike_val.is_integer() else strike_val
                    trading_sym = f"{canon_symbol} {display_strike} {opt_type}"

                    quotes_map[(strike_val, opt_type)] = OptionStrikeQuote(
                        trading_symbol=trading_sym,
                        strike=strike_val,
                        option_type=opt_type,
                        ltp=ltp_val,
                        change=0.0,
                        change_pct=0.0,
                        bid=bid_val,
                        ask=ask_val,
                        oi=int(r[5]),
                        oi_change=0,
                        iv=float(r[7]),
                        delta=float(r[8]),
                        gamma=float(r[9]),
                        theta=float(r[10]),
                        vega=float(r[11]),
                        volume=int(r[6]),
                    )
        except duckdb.Error:
            pass

    if not quotes_map and target_expiry:
        try:
            bar_res = conn.execute(
                "SELECT MAX(bar_start) FROM v_candles_options WHERE expiry = ? AND symbol = ?",
                [target_expiry, canon_symbol],
            ).fetchone()
            latest_bar = bar_res[0] if bar_res else None

            if latest_bar is not None:
                if hasattr(latest_bar, "timestamp"):
                    snapshot_time = int(latest_bar.timestamp())

                candle_rows = conn.execute(
                    """
                    SELECT
                        CAST(strike AS DOUBLE) as strike,
                        option_type,
                        COALESCE(close, 0.0) as ltp,
                        COALESCE(oi, 0) as oi,
                        COALESCE(volume, 0) as volume
                    FROM v_candles_options
                    WHERE expiry = ? AND symbol = ? AND bar_start = ?
                    ORDER BY strike ASC
                    """,
                    [target_expiry, canon_symbol, latest_bar],
                ).fetchall()

                for cr in candle_rows:
                    strike_val = float(cr[0])
                    opt_type = str(cr[1]).upper()
                    display_strike = int(strike_val) if strike_val.is_integer() else strike_val
                    trading_sym = f"{canon_symbol} {display_strike} {opt_type}"

                    quotes_map[(strike_val, opt_type)] = OptionStrikeQuote(
                        trading_symbol=trading_sym,
                        strike=strike_val,
                        option_type=opt_type,
                        ltp=float(cr[2]),
                        change=0.0,
                        change_pct=0.0,
                        bid=0.0,
                        ask=0.0,
                        oi=int(cr[3]),
                        oi_change=0,
                        iv=0.0,
                        delta=0.0,
                        gamma=0.0,
                        theta=0.0,
                        vega=0.0,
                        volume=int(cr[4]),
                    )
        except duckdb.Error:
            pass

    if resolved_spot is None or resolved_spot <= 0.0:
        try:
            spot_row = conn.execute(
                "SELECT close, CAST(epoch(bar_start) AS BIGINT) FROM v_candles_underlying WHERE symbol = ? ORDER BY bar_start DESC LIMIT 1",
                [canon_symbol],
            ).fetchone()
            if spot_row:
                resolved_spot = float(spot_row[0])
                if snapshot_time == 0:
                    snapshot_time = int(spot_row[1])
        except duckdb.Error:
            pass

    final_spot = resolved_spot if resolved_spot is not None and resolved_spot > 0.0 else 0.0

    if final_spot > 0.0:
        atm_strike = round(final_spot / 50.0) * 50.0
        target_strikes = [atm_strike + (i * 50.0) for i in range(-strike_cnt, strike_cnt + 1)]
    elif quotes_map:
        strikes_present = sorted({k[0] for k in quotes_map.keys()})
        atm_strike = strikes_present[len(strikes_present) // 2]
        target_strikes = [atm_strike + (i * 50.0) for i in range(-strike_cnt, strike_cnt + 1)]
    else:
        atm_strike = 0.0
        target_strikes = []

    chain_rows: List[OptionChainRow] = []
    for s in target_strikes:
        ce_quote = quotes_map.get((s, "CE"))
        pe_quote = quotes_map.get((s, "PE"))
        chain_rows.append(OptionChainRow(strike=s, ce=ce_quote, pe=pe_quote))

    total_ce_oi = sum((r.ce.oi for r in chain_rows if r.ce and r.ce.oi), 0)
    total_pe_oi = sum((r.pe.oi for r in chain_rows if r.pe and r.pe.oi), 0)
    pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0.0

    return OptionChainResponse(
        underlying=canon_symbol,
        expiry_date=target_expiry or "",
        spot_price=final_spot,
        atm_strike=atm_strike,
        timestamp=snapshot_time,
        strikes=chain_rows,
        total_ce_oi=total_ce_oi,
        total_pe_oi=total_pe_oi,
        pcr=pcr,
    )


@router.get(
    "/candles",
    response_model=OptionCandleResponse,
    summary="Option Contract Candles",
    description="Queries DuckDB lake view v_candles_options for chronologically sorted candlestick bars.",
)
def get_option_candles(
    contract_id: Optional[str] = Query(
        default=None, description="Canonical contract identifier (e.g. NIFTY_2025-01-02_22150.00_PE)"
    ),
    strike: Optional[float] = Query(default=None, description="Contract strike price (e.g. 22150.0)"),
    option_type: Optional[str] = Query(default=None, description="Option contract type ('CE' or 'PE')"),
    expiry_date: Optional[str] = Query(default=None, description="Expiry date in YYYY-MM-DD format"),
    resolution: str = Query(default="1m", description="Candle interval resolution (e.g. 1m, 5m, 1d)"),
    from_ts: Optional[int] = Query(default=None, description="Start timestamp in UTC epoch seconds"),
    to_ts: Optional[int] = Query(default=None, description="End timestamp in UTC epoch seconds"),
    limit: int = Query(default=5000, ge=1, le=10000, description="Maximum number of bars (1 to 10000)"),
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb),
) -> OptionCandleResponse:
    """
    1. The use of function:
       FastAPI endpoint returning historical and real-time OHLCV bars for an individual option contract.

    2. How does the specific function work:
       - Validates and prepares filter parameters for contract_id, strike, option_type, expiry, and resolution.
       - Constructs parameterized SQL query projecting UTC epoch seconds, open, high, low, close, and volume
         from v_candles_options.
       - Orders rows chronologically ascending by bar_start.
       - Catches DuckDB errors gracefully, returning an empty list of candles if tables are missing.
       - Populates and returns OptionCandleResponse schema.

    3. Concepts used in the function:
       Contract specification resolution, time-series candle projection, parameterization, fault tolerance.

    4. Places where this function is imported and used:
       Registered with the options router under GET /api/v1/options/candles.

    5. Final output of the function, before and after:
       Before: Query filters and DB connection. After: Validated OptionCandleResponse instance.
    """
    res_clean = resolution.strip().lower()
    conditions: List[str] = ["interval = ?"]
    params: List[object] = [res_clean]

    if contract_id:
        conditions.append("contract_id = ?")
        params.append(contract_id.strip())

    if strike is not None:
        conditions.append("strike = ?")
        params.append(strike)

    if option_type:
        conditions.append("option_type = ?")
        params.append(option_type.strip().upper())

    if expiry_date:
        conditions.append("expiry = ?")
        params.append(expiry_date.strip())

    if from_ts is not None:
        conditions.append("epoch(bar_start) >= ?")
        params.append(from_ts)

    if to_ts is not None:
        conditions.append("epoch(bar_start) <= ?")
        params.append(to_ts)

    where_clause = " WHERE " + " AND ".join(conditions)
    query = (
        "SELECT contract_id, symbol, CAST(expiry AS VARCHAR) as expiry, "
        "CAST(strike AS DOUBLE) as strike, option_type, "
        "CAST(epoch(bar_start) AS BIGINT) as time, "
        "open, high, low, close, COALESCE(volume, 0) as volume "
        f"FROM v_candles_options{where_clause} ORDER BY bar_start ASC LIMIT ?"
    )
    params.append(limit)

    try:
        rows = conn.execute(query, params).fetchall()
    except duckdb.Error:
        rows = []

    if not rows and contract_id:
        m = re.search(
            r"([A-Z]+)[-_ ]?(\d{4}-?\d{2}-?\d{2}|\d{2}[A-Z]{3})?[-_ ]?(\d+(?:\.\d+)?)[-_ ]?([CP]E)",
            contract_id.upper(),
        )
        if m:
            p_sym = m.group(1)
            p_exp = m.group(2)
            p_strike = float(m.group(3))
            p_type = m.group(4)
            fb_conds = ["interval = ?", "symbol = ?", "strike = ?", "option_type = ?"]
            fb_params: List[object] = [res_clean, p_sym, p_strike, p_type]
            if p_exp:
                fb_conds.append("CAST(expiry AS VARCHAR) LIKE ?")
                fb_params.append(f"%{p_exp}%")
            if from_ts is not None:
                fb_conds.append("epoch(bar_start) >= ?")
                fb_params.append(from_ts)
            if to_ts is not None:
                fb_conds.append("epoch(bar_start) <= ?")
                fb_params.append(to_ts)
            fb_where = " WHERE " + " AND ".join(fb_conds)
            fb_query = (
                "SELECT contract_id, symbol, CAST(expiry AS VARCHAR) as expiry, "
                "CAST(strike AS DOUBLE) as strike, option_type, "
                "CAST(epoch(bar_start) AS BIGINT) as time, "
                "open, high, low, close, COALESCE(volume, 0) as volume "
                f"FROM v_candles_options{fb_where} ORDER BY bar_start ASC LIMIT ?"
            )
            fb_params.append(limit)
            try:
                rows = conn.execute(fb_query, fb_params).fetchall()
            except duckdb.Error:
                pass

    candles = [
        Candle(
            time=int(r[5]),
            open=float(r[6]),
            high=float(r[7]),
            low=float(r[8]),
            close=float(r[9]),
            volume=int(r[10]),
        )
        for r in rows
    ]

    if rows:
        resp_contract_id = str(rows[0][0])
        resp_symbol = str(rows[0][1])
        resp_expiry = str(rows[0][2])
        resp_strike = float(rows[0][3])
        resp_opt_type = str(rows[0][4])
    else:
        opt_upper = option_type.strip().upper() if option_type else ""
        resp_contract_id = contract_id or (
            f"NIFTY_{expiry_date}_{strike:.2f}_{opt_upper}"
            if (expiry_date and strike is not None and opt_upper)
            else ""
        )
        resp_symbol = "NIFTY"
        resp_expiry = expiry_date or ""
        resp_strike = float(strike) if strike is not None else 0.0
        resp_opt_type = opt_upper

    return OptionCandleResponse(
        contract_id=resp_contract_id,
        symbol=resp_symbol,
        expiry=resp_expiry,
        strike=resp_strike,
        option_type=resp_opt_type,
        resolution=res_clean,
        candles=candles,
    )
