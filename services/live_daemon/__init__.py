"""
1. What this file does:
   Defines the service boundary for live_daemon (paper trading and live execution orchestrator).

2. Overall design:
   live_daemon consumes real-time frames from FrameBus / snapshots, checks data freshness
   (available_at <= decision_time), steps strategy instances on completed bars, evaluates risk
   rules, simulates order fills, and writes immutable events to PostgreSQL ledger_events in integer paise.

3. Elements in the file:
   - Service metadata and lifecycle contract.

4. Final output of the file:
   - Package interface for services.live_daemon.
"""

SERVICE_NAME = "live_daemon"
