"""
1. What this file does:
   Defines the FastAPI gateway router for inspecting and controlling the QuantView Live Daemon
   (Milestone M7-07, Gate G5). Mounted at /api/v1/daemon.

2. Overall design:
   Enforces QUANTVIEW_MASTER_SPEC §2.2 and Milestone M7-07:
     - Asynchronous Gateway Proxy: Proxies operator requests to the internal Live Daemon loopback
       server (http://127.0.0.1:8001/control/*) using httpx.AsyncClient.
     - Fault-Tolerant Status Fallback: If the daemon process is offline or restarting, GET /status
       gracefully returns an OFFLINE status payload rather than unhandled gateway exceptions.
     - Fail-Closed Control Actions: Start, stop, and emergency kill-switch commands require an
       active live daemon process; if unreachable, returns HTTP 503 Service Unavailable.

3. Elements in the file:
   - DaemonStartProxyRequest: Request schema for starting strategy deployments.
   - DaemonStopProxyRequest: Request schema for stopping strategy deployments.
   - DaemonKillSwitchProxyRequest: Request schema for triggering emergency circuit breaker.
   - get_daemon_status: Controller proxying GET /api/v1/daemon/status.
   - start_daemon_deployment: Controller proxying POST /api/v1/daemon/start.
   - stop_daemon_deployment: Controller proxying POST /api/v1/daemon/stop.
   - trigger_daemon_kill_switch: Controller proxying POST /api/v1/daemon/kill-switch.
   - router: Configured APIRouter instance mounted in services.api.main.

4. Final output of the file:
   - Exported APIRouter instance ready for registration with the QuantView API gateway.
"""

import logging
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.api.config import get_api_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/daemon", tags=["daemon"])


class DaemonStartProxyRequest(BaseModel):
    """
    1. The use of class:
       Pydantic validation schema for initiating strategy deployments through the gateway proxy.

    2. What the class contains:
       - strategy_id: Identifier of registered strategy to instantiate.
       - deployment_id: Optional unique deployment instance name.
       - account_id: Optional target paper trading account identifier.
       - instrument_key: Target financial instrument key.
       - params: Optional strategy runtime parameters.
       - mode: Optional ADR-038 account allocation mode (ISOLATED or PORTFOLIO).
       - timeout_sec: Optional execution timeout guard ceiling in seconds.

    3. Technologies used and why:
       Pydantic v2 BaseModel for request validation and OpenAPI schema generation.

    4. Key design and overall design of the class:
       Mirror model matching Live Daemon loopback /control/start schema.
    """

    model_config = ConfigDict(extra="ignore")

    strategy_id: str = Field(..., description="Registered strategy class name or identifier")
    deployment_id: Optional[str] = Field(None, description="Unique deployment identifier")
    account_id: Optional[str] = Field(None, description="Target paper account ID")
    instrument_key: Optional[str] = Field("NSE_INDEX|Nifty 50", description="Financial instrument key")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Strategy parameters")
    mode: Optional[str] = Field(None, description="ADR-038 allocation mode: ISOLATED or PORTFOLIO")
    timeout_sec: Optional[float] = Field(0.5, description="Execution timeout limit in seconds")


class DaemonStopProxyRequest(BaseModel):
    """
    1. The use of class:
       Pydantic validation schema for stopping an active strategy deployment via gateway.

    2. What the class contains:
       - deployment_id: Unique deployment identifier of the strategy host to halt.

    3. Technologies used and why:
       Pydantic v2 BaseModel for deterministic parameter validation.

    4. Key design and overall design of the class:
       Standardizes stop command forwarding payload.
    """

    model_config = ConfigDict(extra="ignore")

    deployment_id: str = Field(..., description="Unique deployment identifier to stop")


class DaemonKillSwitchProxyRequest(BaseModel):
    """
    1. The use of class:
       Pydantic validation schema for triggering emergency kill-switch circuit breaker via gateway.

    2. What the class contains:
       - reason: Diagnostic explanation recorded in audit logs.

    3. Technologies used and why:
       Pydantic v2 BaseModel for emergency commands.

    4. Key design and overall design of the class:
       Standardizes kill-switch command forwarding payload.
    """

    model_config = ConfigDict(extra="ignore")

    reason: Optional[str] = Field(
        "Operator emergency kill-switch via API Gateway",
        description="Audit reason for kill-switch activation",
    )


@router.get("/status", summary="Query Live Daemon Operational Health & Status")
async def get_daemon_status() -> Dict[str, Any]:
    """
    1. The use of function:
       Proxies operational status query to the internal Live Daemon loopback control plane.

    2. How does the specific function work:
       - Resolves daemon loopback base URL from ApiConfig (default http://127.0.0.1:8001).
       - Issues asynchronous GET request to /control/status with a 3.0s timeout.
       - If daemon is offline, catches network errors and returns structured OFFLINE payload.
       - Returns JSON status response from daemon.

    3. Concepts used in the function:
       Reverse proxying, circuit breaker fallback, asynchronous HTTP client.

    4. Places where this function is imported and used:
       Mounted under GET /api/v1/daemon/status.

    5. Final output of the function, before and after:
       Before: Gateway status request. After: Daemon telemetry or graceful OFFLINE response.
    """
    cfg = get_api_config()
    daemon_url = f"{cfg.daemon_url.rstrip('/')}/control/status"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(daemon_url)
            if resp.status_code == 200:
                return resp.json()
            return {
                "status": "ERROR",
                "daemon_url": cfg.daemon_url,
                "status_code": resp.status_code,
                "detail": resp.text,
            }
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.debug(f"Live Daemon unreachable at {daemon_url}: {exc}")
        return {
            "status": "OFFLINE",
            "daemon_url": cfg.daemon_url,
            "detail": "Live Daemon loopback service unreachable or offline",
            "uptime_sec": 0.0,
            "deployments_total": 0,
            "deployments_running": 0,
            "deployments_halted": 0,
            "deployments": [],
            "kill_switch_active": False,
        }


@router.post("/start", summary="Start Strategy Deployment on Live Daemon")
async def start_daemon_deployment(req: DaemonStartProxyRequest) -> Dict[str, Any]:
    """
    1. The use of function:
       Proxies strategy deployment launch command to the internal Live Daemon loopback control plane.

    2. How does the specific function work:
       - Resolves daemon loopback base URL from ApiConfig.
       - Issues asynchronous POST request to /control/start with validated payload.
       - If daemon is offline or returns error status, raises appropriate HTTPException.
       - Returns JSON response confirming deployment launch.

    3. Concepts used in the function:
       Asynchronous proxy dispatch, error translation, service availability gating.

    4. Places where this function is imported and used:
       Mounted under POST /api/v1/daemon/start.

    5. Final output of the function, before and after:
       Before: Start command payload. After: Started deployment telemetry.
    """
    cfg = get_api_config()
    daemon_url = f"{cfg.daemon_url.rstrip('/')}/control/start"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(daemon_url, json=req.model_dump())
            if resp.status_code == 200:
                return resp.json()
            raise HTTPException(
                status_code=resp.status_code,
                detail=resp.json() if resp.headers.get("content-type") == "application/json" else resp.text,
            )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Live Daemon is offline or unreachable at {cfg.daemon_url}: {exc}",
        )


@router.post("/stop", summary="Stop Strategy Deployment on Live Daemon")
async def stop_daemon_deployment(req: DaemonStopProxyRequest) -> Dict[str, Any]:
    """
    1. The use of function:
       Proxies strategy deployment stop command to the internal Live Daemon loopback control plane.

    2. How does the specific function work:
       - Resolves daemon loopback base URL from ApiConfig.
       - Issues asynchronous POST request to /control/stop with validated payload.
       - If daemon returns error, raises HTTPException with daemon's diagnostic response.
       - Returns JSON response confirming deployment stop.

    3. Concepts used in the function:
       Deployment termination proxy, error propagation.

    4. Places where this function is imported and used:
       Mounted under POST /api/v1/daemon/stop.

    5. Final output of the function, before and after:
       Before: Stop command payload. After: Stopped deployment telemetry.
    """
    cfg = get_api_config()
    daemon_url = f"{cfg.daemon_url.rstrip('/')}/control/stop"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(daemon_url, json=req.model_dump())
            if resp.status_code == 200:
                return resp.json()
            raise HTTPException(
                status_code=resp.status_code,
                detail=resp.json() if resp.headers.get("content-type") == "application/json" else resp.text,
            )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Live Daemon is offline or unreachable at {cfg.daemon_url}: {exc}",
        )


@router.post("/kill-switch", summary="Trigger Emergency RK-01 Kill Switch on Live Daemon")
async def trigger_daemon_kill_switch(req: DaemonKillSwitchProxyRequest) -> Dict[str, Any]:
    """
    1. The use of function:
       Proxies emergency kill-switch command to the internal Live Daemon loopback control plane.

    2. How does the specific function work:
       - Resolves daemon loopback base URL from ApiConfig.
       - Issues asynchronous POST request to /control/kill-switch with audit reason.
       - If daemon returns error or is unreachable, raises HTTPException.
       - Returns audit confirmation with canceled order summary.

    3. Concepts used in the function:
       Emergency circuit breaker dispatch, fail-closed command proxying.

    4. Places where this function is imported and used:
       Mounted under POST /api/v1/daemon/kill-switch.

    5. Final output of the function, before and after:
       Before: Emergency kill-switch intent. After: Confirmed kill-switch activation and audit log.
    """
    cfg = get_api_config()
    daemon_url = f"{cfg.daemon_url.rstrip('/')}/control/kill-switch"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(daemon_url, json=req.model_dump())
            if resp.status_code == 200:
                return resp.json()
            raise HTTPException(
                status_code=resp.status_code,
                detail=resp.json() if resp.headers.get("content-type") == "application/json" else resp.text,
            )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Live Daemon is offline or unreachable at {cfg.daemon_url}: {exc}",
        )
