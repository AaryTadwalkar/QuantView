<#
.SYNOPSIS
    QuantView Unified Workstation Launcher (Stage 7 / Gate G5 Certification).

.DESCRIPTION
    Launches the full QuantView live trading and research workstation:
      - Live Daemon Service on http://127.0.0.1:8001 (Loopback admin, FrameBus, PaperBroker)
      - API Gateway Service on http://127.0.0.1:8000 (FastAPI REST, WebSocket bridge, Web UI)
    Supports continuous 24/7 Historical Replay (-Replay), variable playback speed (-Speed),
    and automatic browser launch with graceful Ctrl+C shutdown.

.PARAMETER Replay
    Enables automatic 24/7 continuous historical tick playback from Data/lake into FrameBus.

.PARAMETER Speed
    Playback speed multiplier for the Replay Player: '1x', '2x', '5x', or 'asap'. Default: '2x'.

.PARAMETER NoBrowser
    Suppresses automatic launching of the default web browser to http://localhost:8000.

.EXAMPLE
    .\run_workstation.ps1
    Launches Gateway and Live Daemon in standard live standby mode with browser.

.EXAMPLE
    .\run_workstation.ps1 -Replay -Speed 5x
    Launches workstation with 24/7 historical replay at 5x speed.
#>

[CmdletBinding()]
param(
    [switch]$Replay,
    [ValidateSet("1x", "2x", "5x", "asap")][string]$Speed = "2x",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

# 1. Resolve Python executable
$VenvPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $PythonExe) {
        Write-Error "CRITICAL: Python executable could not be resolved in virtualenv or PATH."
        exit 1
    }
}

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "                QUANTVIEW WORKSTATION - STAGE 7                     " -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host " Python Runtime : $PythonExe" -ForegroundColor Gray
Write-Host " Workspace Root : $PSScriptRoot" -ForegroundColor Gray
Write-Host " Replay Mode    : $(if ($Replay) { "ENABLED ($Speed speed)" } else { "DISABLED (Live Standby)" })" -ForegroundColor Yellow
Write-Host " Web Gateway    : http://localhost:8000" -ForegroundColor Green
Write-Host " Live Daemon    : http://127.0.0.1:8001" -ForegroundColor Green
Write-Host "====================================================================" -ForegroundColor Cyan

# 2. Check for port conflicts (8000 and 8001)
function Test-PortAvailable([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return ($null -eq $conn)
}

if (-not (Test-PortAvailable 8000)) {
    Write-Warning "Port 8000 is currently occupied. Attempting to locate conflicting process..."
    $proc = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1
    if ($proc) {
        Write-Warning "Port 8000 is used by PID: $proc. Terminate this process or change configuration."
    }
}

if (-not (Test-PortAvailable 8001)) {
    Write-Warning "Port 8001 is currently occupied. Attempting to locate conflicting process..."
    $proc = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1
    if ($proc) {
        Write-Warning "Port 8001 is used by PID: $proc. Terminate this process or change configuration."
    }
}

# 3. Configure environment variables for child processes
if ($Replay) {
    $env:QUANTVIEW_REPLAY = "1"
    $env:QUANTVIEW_REPLAY_SPEED = $Speed
} else {
    $env:QUANTVIEW_REPLAY = "0"
    $env:QUANTVIEW_REPLAY_SPEED = $Speed
}

# 4. Process tracking state
$DaemonProcess = $null
$GatewayProcess = $null

function Stop-WorkstationProcesses {
    Write-Host "`n[QuantView] Initiating graceful shutdown of workstation processes..." -ForegroundColor Yellow
    if ($DaemonProcess -and -not $DaemonProcess.HasExited) {
        Write-Host "  Stopping Live Daemon (PID: $($DaemonProcess.Id))..." -ForegroundColor Gray
        try {
            Stop-Process -Id $DaemonProcess.Id -Force -ErrorAction SilentlyContinue
        } catch {}
    }
    if ($GatewayProcess -and -not $GatewayProcess.HasExited) {
        Write-Host "  Stopping Gateway (PID: $($GatewayProcess.Id))..." -ForegroundColor Gray
        try {
            Stop-Process -Id $GatewayProcess.Id -Force -ErrorAction SilentlyContinue
        } catch {}
    }
    Write-Host "[QuantView] All workstation processes terminated cleanly. Goodbye." -ForegroundColor Green
}

try {
    # 5. Start Live Daemon on Port 8001
    Write-Host "[1/3] Spawning Live Daemon Service on port 8001..." -ForegroundColor White
    $daemonArgs = "-m uvicorn services.live_daemon.main:app --host 127.0.0.1 --port 8001 --log-level info"
    $DaemonProcess = Start-Process -FilePath $PythonExe `
                                   -ArgumentList $daemonArgs `
                                   -WorkingDirectory $PSScriptRoot `
                                   -PassThru

    # 6. Start API Gateway on Port 8000
    Write-Host "[2/3] Spawning API Gateway Service on port 8000..." -ForegroundColor White
    $gatewayArgs = "-m uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --log-level info"
    $GatewayProcess = Start-Process -FilePath $PythonExe `
                                    -ArgumentList $gatewayArgs `
                                    -WorkingDirectory $PSScriptRoot `
                                    -PassThru

    # 7. Health Probe Poll Loop
    Write-Host "[3/3] Probing services for readiness..." -ForegroundColor White
    $daemonReady = $false
    $gatewayReady = $false
    $attempts = 0
    $maxAttempts = 30  # 15 seconds max

    while ($attempts -lt $maxAttempts -and (-not $daemonReady -or -not $gatewayReady)) {
        Start-Sleep -Milliseconds 500
        $attempts++

        if (-not $daemonReady) {
            try {
                $daemonRes = Invoke-RestMethod -Uri "http://127.0.0.1:8001/control/status" -TimeoutSec 1 -ErrorAction SilentlyContinue
                if ($daemonRes -and $daemonRes.status -eq "RUNNING") {
                    $daemonReady = $true
                    Write-Host "  -> Live Daemon operational at http://127.0.0.1:8001 (Supervisor: RUNNING)" -ForegroundColor Green
                }
            } catch {}
        }

        if (-not $gatewayReady) {
            try {
                $gatewayRes = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 1 -ErrorAction SilentlyContinue
                if ($gatewayRes -and $gatewayRes.status -eq "ok") {
                    $gatewayReady = $true
                    Write-Host "  -> API Gateway operational at http://127.0.0.1:8000 (Health: OK)" -ForegroundColor Green
                }
            } catch {}
        }
    }

    if ($daemonReady -and $gatewayReady) {
        Write-Host "`n>>> WORKSTATION READY <<<" -ForegroundColor Green
        Write-Host "  * Web App UI  : http://localhost:8000" -ForegroundColor Cyan
        Write-Host "  * REST API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
        Write-Host "  * Daemon Admin : http://127.0.0.1:8001/control/status" -ForegroundColor Cyan
        Write-Host "  * Press Ctrl+C in this console to stop all services cleanly.`n" -ForegroundColor Yellow

        if (-not $NoBrowser) {
            Start-Process "http://localhost:8000"
        }

        # Keep alive until user interrupts or process exits
        while (-not $DaemonProcess.HasExited -and -not $GatewayProcess.HasExited) {
            Start-Sleep -Seconds 1
        }
    } else {
        Write-Error "Workstation startup timed out. Check process output for error diagnostics."
    }

} finally {
    Stop-WorkstationProcesses
}
