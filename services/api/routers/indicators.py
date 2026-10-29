"""
1. What this file does:
   Implements the Technical Indicators catalog and on-demand indicator calculation REST API endpoints
   for the QuantView Gateway (Milestones M6-02, M6-11, Gate G4).

2. Overall design:
   Exposes indicator discovery and compute routes:
     - GET /api/v1/indicators: Returns descriptor catalog of available mathematical indicators (EMA, SMA, RSI,
       MACD, ATR, Supertrend, BOS_CHOCH) with UI categorization and parameter constraints.
     - POST /api/v1/indicators/compute: Fetches underlying candle data and evaluates strictly causal technical
       indicators backed by packages.features algorithms, returning Lightweight Charts compatible timeseries points.

3. Elements in the file:
   - AVAILABLE_INDICATORS: Pre-registered list of IndicatorDescriptor models.
   - router: FastAPI APIRouter configured with /api/v1/indicators prefix.
   - get_indicators: Endpoint handler returning the indicator registry.
   - compute_indicator: Endpoint handler computing indicator values over candle bars.

4. Final output of the file:
   - Exported APIRouter instance for registration in services.api.main.
"""

import math
from typing import List

import duckdb
from fastapi import APIRouter, Depends, HTTPException

from packages.features.statistical.indicators import (
    compute_atr,
    compute_bollinger_bands,
    compute_ema,
    compute_macd,
    compute_rsi,
    compute_sma,
    compute_supertrend,
)
from packages.features.structure.bos_choch import compute_market_structure
from services.api.deps import get_duckdb
from services.api.routers.market import get_candles
from services.api.schemas.indicators import (
    IndicatorComputeRequest,
    IndicatorComputeResponse,
    IndicatorDescriptor,
    IndicatorParameter,
    IndicatorValuePoint,
)

router = APIRouter(tags=["indicators"])

AVAILABLE_INDICATORS: List[IndicatorDescriptor] = [
    IndicatorDescriptor(
        id="EMA",
        name="Exponential Moving Average",
        category="trend",
        description="Exponential moving average with customizable smoothing period.",
        pane="primary",
        parameters=[
            IndicatorParameter(
                name="length",
                type="int",
                default=20,
                min_value=1.0,
                max_value=500.0,
                description="Period length for exponential smoothing",
            ),
        ],
    ),
    IndicatorDescriptor(
        id="SMA",
        name="Simple Moving Average",
        category="trend",
        description="Rolling simple arithmetic moving average.",
        pane="primary",
        parameters=[
            IndicatorParameter(
                name="length",
                type="int",
                default=20,
                min_value=1.0,
                max_value=500.0,
                description="Rolling window period length",
            ),
        ],
    ),
    IndicatorDescriptor(
        id="BB",
        name="Bollinger Bands",
        category="trend",
        description="Bollinger Bands overlay showing volatility envelope and moving average.",
        pane="primary",
        parameters=[
            IndicatorParameter(
                name="length",
                type="int",
                default=20,
                min_value=1.0,
                max_value=200.0,
                description="Moving average lookback period",
            ),
            IndicatorParameter(
                name="mult",
                type="float",
                default=2.0,
                min_value=0.1,
                max_value=10.0,
                description="Standard deviation multiplier",
            ),
        ],
    ),
    IndicatorDescriptor(
        id="RSI",
        name="Relative Strength Index",
        category="momentum",
        description="Wilder Relative Strength Index measuring price velocity and momentum.",
        pane="subpane",
        parameters=[
            IndicatorParameter(
                name="length",
                type="int",
                default=14,
                min_value=1.0,
                max_value=200.0,
                description="RSI lookback period",
            ),
        ],
    ),
    IndicatorDescriptor(
        id="MACD",
        name="Moving Average Convergence Divergence",
        category="momentum",
        description="MACD oscillator showing trend momentum and convergence/divergence.",
        pane="subpane",
        parameters=[
            IndicatorParameter(
                name="fast_length",
                type="int",
                default=12,
                min_value=1.0,
                max_value=200.0,
                description="Fast EMA period",
            ),
            IndicatorParameter(
                name="slow_length",
                type="int",
                default=26,
                min_value=1.0,
                max_value=500.0,
                description="Slow EMA period",
            ),
            IndicatorParameter(
                name="signal_length",
                type="int",
                default=9,
                min_value=1.0,
                max_value=100.0,
                description="Signal smoothing period",
            ),
        ],
    ),
    IndicatorDescriptor(
        id="ATR",
        name="Average True Range",
        category="volatility",
        description="Average True Range volatility indicator using Wilder RMA.",
        pane="subpane",
        parameters=[
            IndicatorParameter(
                name="length",
                type="int",
                default=14,
                min_value=1.0,
                max_value=200.0,
                description="ATR lookback smoothing period",
            ),
        ],
    ),
    IndicatorDescriptor(
        id="Supertrend",
        name="Supertrend",
        category="trend",
        description="Trend following overlay based on ATR and price action.",
        pane="primary",
        parameters=[
            IndicatorParameter(
                name="length",
                type="int",
                default=10,
                min_value=1.0,
                max_value=100.0,
                description="ATR period",
            ),
            IndicatorParameter(
                name="multiplier",
                type="float",
                default=3.0,
                min_value=0.1,
                max_value=20.0,
                description="ATR band multiplier",
            ),
        ],
    ),
    IndicatorDescriptor(
        id="BOS_CHOCH",
        name="Break of Structure & Change of Character",
        category="structural",
        description="Causal market structure swing points, BOS, and CHoCH structural break signals.",
        pane="primary",
        parameters=[
            IndicatorParameter(
                name="pivot_left",
                type="int",
                default=5,
                min_value=1.0,
                max_value=50.0,
                description="Left pivot confirmation window",
            ),
            IndicatorParameter(
                name="pivot_right",
                type="int",
                default=5,
                min_value=1.0,
                max_value=50.0,
                description="Right pivot confirmation window",
            ),
        ],
    ),
]


@router.get(
    "/api/v1/indicators",
    response_model=List[IndicatorDescriptor],
    summary="Available Indicator Descriptors",
    description="Returns registry of technical indicator descriptors with UI categories and parameter schemas.",
)
@router.get(
    "/api/v1/indicators/",
    response_model=List[IndicatorDescriptor],
    include_in_schema=False,
)
@router.get(
    "/api/v1/charts/indicators",
    response_model=List[IndicatorDescriptor],
    include_in_schema=False,
)
@router.get(
    "/api/v1/charts/indicators/",
    response_model=List[IndicatorDescriptor],
    include_in_schema=False,
)
def get_indicators() -> List[IndicatorDescriptor]:
    """
    1. The use of function:
       FastAPI endpoint serving the technical indicator discovery catalog.

    2. How does the specific function work:
       Returns the pre-configured AVAILABLE_INDICATORS list conforming to the UI-1 schema-driven contract.

    3. Concepts used in the function:
       Catalog discovery pattern, schema reflection, REST GET endpoint.

    4. Places where this function is imported and used:
       Registered with the indicator router under GET /api/v1/indicators and GET /api/v1/charts/indicators.

    5. Final output of the function, before and after:
       Before: HTTP GET request. After: JSON array of IndicatorDescriptor objects.
    """
    return AVAILABLE_INDICATORS


@router.post(
    "/api/v1/indicators/compute",
    response_model=IndicatorComputeResponse,
    summary="Compute Technical Indicator Series",
    description="Calculates strictly causal technical indicator values on symbol candles.",
)
@router.post(
    "/api/v1/charts/indicators/compute",
    response_model=IndicatorComputeResponse,
    include_in_schema=False,
)
def compute_indicator(
    req: IndicatorComputeRequest,
    conn: duckdb.DuckDBPyConnection = Depends(get_duckdb),
) -> IndicatorComputeResponse:
    """
    1. The use of function:
       FastAPI endpoint executing on-demand technical indicator mathematical computation over candle bars.

    2. How does the specific function work:
       - Fetches underlying candlestick data via get_candles using requested symbol and resolution.
       - Dispatches mathematical evaluation to packages.features solvers based on indicator_id.
       - Maps outputs to chronologically ordered IndicatorValuePoint models with UTC epoch timestamps.
       - Handles missing data, NaN warm-up periods, and unknown indicator exceptions cleanly.

    3. Concepts used in the function:
       On-demand timeseries signal processing, mathematical indicators, causal filtering, REST POST endpoint.

    4. Places where this function is imported and used:
       Registered with the indicator router under POST /api/v1/indicators/compute.

    5. Final output of the function, before and after:
       Before: IndicatorComputeRequest payload. After: Validated IndicatorComputeResponse instance.
    """
    candle_res = get_candles(
        symbol=req.symbol,
        resolution=req.resolution,
        from_ts=req.from_ts,
        to_ts=req.to_ts,
        limit=req.limit,
        conn=conn,
    )

    if not candle_res.candles:
        return IndicatorComputeResponse(
            indicator_id=req.indicator_id,
            symbol=req.symbol,
            resolution=req.resolution,
            data=[],
        )

    times = [c.time for c in candle_res.candles]
    closes = [c.close for c in candle_res.candles]
    highs = [c.high for c in candle_res.candles]
    lows = [c.low for c in candle_res.candles]

    ind_id = req.indicator_id.strip().upper()
    points: List[IndicatorValuePoint] = []

    try:
        if ind_id == "EMA":
            length = int(req.params.get("length", 20))
            vals = compute_ema(closes, length=length)
            points = [
                IndicatorValuePoint(
                    time=t,
                    values={"ema": None if math.isnan(v) else round(v, 4)},
                )
                for t, v in zip(times, vals)
            ]
        elif ind_id == "SMA":
            length = int(req.params.get("length", 20))
            vals = compute_sma(closes, length=length)
            points = [
                IndicatorValuePoint(
                    time=t,
                    values={"sma": None if math.isnan(v) else round(v, 4)},
                )
                for t, v in zip(times, vals)
            ]
        elif ind_id == "RSI":
            length = int(req.params.get("length", 14))
            vals = compute_rsi(closes, length=length)
            points = [
                IndicatorValuePoint(
                    time=t,
                    values={"rsi": None if math.isnan(v) else round(v, 4)},
                )
                for t, v in zip(times, vals)
            ]
        elif ind_id == "MACD":
            fast_length = int(req.params.get("fast_length", 12))
            slow_length = int(req.params.get("slow_length", 26))
            signal_length = int(req.params.get("signal_length", 9))
            m_vals, s_vals, h_vals = compute_macd(
                closes,
                fast_length=fast_length,
                slow_length=slow_length,
                signal_length=signal_length,
            )
            points = [
                IndicatorValuePoint(
                    time=t,
                    values={
                        "macd": None if math.isnan(m) else round(m, 4),
                        "signal": None if math.isnan(s) else round(s, 4),
                        "histogram": None if math.isnan(h) else round(h, 4),
                    },
                )
                for t, m, s, h in zip(times, m_vals, s_vals, h_vals)
            ]
        elif ind_id in {"BB", "BOLLINGER", "BOLLINGER_BANDS"}:
            length = int(req.params.get("length", 20))
            mult = float(req.params.get("mult", req.params.get("multiplier", 2.0)))
            middle, upper, lower, _, _ = compute_bollinger_bands(
                closes,
                length=length,
                mult=mult,
            )
            points = [
                IndicatorValuePoint(
                    time=t,
                    values={
                        "middle": None if math.isnan(m) else round(m, 4),
                        "upper": None if math.isnan(u) else round(u, 4),
                        "lower": None if math.isnan(l) else round(l, 4),
                    },
                )
                for t, m, u, l in zip(times, middle, upper, lower)
            ]
        elif ind_id == "ATR":
            length = int(req.params.get("length", 14))
            vals = compute_atr(highs, lows, closes, length=length)
            points = [
                IndicatorValuePoint(
                    time=t,
                    values={"atr": None if math.isnan(v) else round(v, 4)},
                )
                for t, v in zip(times, vals)
            ]
        elif ind_id == "SUPERTREND":
            length = int(req.params.get("length", 10))
            multiplier = float(req.params.get("multiplier", 3.0))
            st_vals, directions = compute_supertrend(
                highs,
                lows,
                closes,
                length=length,
                multiplier=multiplier,
            )
            points = [
                IndicatorValuePoint(
                    time=t,
                    values={
                        "supertrend": None if math.isnan(st) else round(st, 4),
                        "direction": float(d),
                    },
                )
                for t, st, d in zip(times, st_vals, directions)
            ]
        elif ind_id in {"BOS_CHOCH", "BOS", "CHOCH", "STRUCTURE", "SMC"}:
            pivot_left = int(req.params.get("pivot_left", 5))
            pivot_right = int(req.params.get("pivot_right", 5))
            bars = compute_market_structure(
                highs,
                lows,
                closes,
                timestamps=times,
                pivot_left=pivot_left,
                pivot_right=pivot_right,
            )
            points = [
                IndicatorValuePoint(
                    time=t,
                    values={
                        "high_level": (
                            None
                            if b.last_confirmed_high_price is None
                            or math.isnan(b.last_confirmed_high_price)
                            else round(float(b.last_confirmed_high_price), 4)
                        ),
                        "low_level": (
                            None
                            if b.last_confirmed_low_price is None
                            or math.isnan(b.last_confirmed_low_price)
                            else round(float(b.last_confirmed_low_price), 4)
                        ),
                        "event": (
                            b.structural_event.value
                            if b.structural_event.value != "NONE"
                            else None
                        ),
                        "bias": b.market_bias.value,
                    },
                )
                for t, b in zip(times, bars)
            ]
        else:
            supported = ["EMA", "SMA", "BB", "RSI", "MACD", "ATR", "Supertrend", "BOS_CHOCH"]
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported indicator_id '{req.indicator_id}'. Supported indicators: {', '.join(supported)}",
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid indicator parameters for '{req.indicator_id}': {str(exc)}",
        ) from exc

    return IndicatorComputeResponse(
        indicator_id=req.indicator_id,
        symbol=req.symbol,
        resolution=req.resolution,
        data=points,
    )
