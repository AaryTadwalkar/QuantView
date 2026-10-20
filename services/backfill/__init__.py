"""
1. What this file does:
   Defines the service boundary for historical data backfill orchestration.

2. Overall design:
   The backfill service coordinates bounded, checkpointed downloads of underlying index candles
   and expired option contracts/candles under explicit rate-limit budgets, writing raw gzipped
   payloads to Data/raw/ before handoff to worker_data for staging.

3. Elements in the file:
   - Service metadata and lifecycle contract.

4. Final output of the file:
   - Package interface for services.backfill.
"""

SERVICE_NAME = "backfill"
