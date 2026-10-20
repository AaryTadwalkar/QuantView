"""
1. What this file does:
   Defines the service boundary for worker_compute (backtest execution worker).

2. Overall design:
   worker_compute polls the PostgreSQL jobs queue, claims backtest leases, freezes lake dataset
   manifests, executes the causal calendar-minute loop, verifies financial ledger math, and
   atomically publishes run artifacts into data/runs/{run_id}/.

3. Elements in the file:
   - Service metadata and lifecycle contract.

4. Final output of the file:
   - Package interface for services.worker_compute.
"""

SERVICE_NAME = "worker_compute"
