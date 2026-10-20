"""
1. What this file does:
   Defines the service boundary for collector_snapshot (periodic 30-second option chain capture).

2. Overall design:
   The collector_snapshot service queries option-chain endpoints, archives raw JSON responses
   into Data/raw/upstox_rest/, and writes capture headers and strike rows into daily staging Parquet.

3. Elements in the file:
   - Service metadata and lifecycle contract.

4. Final output of the file:
   - Package interface for services.collector_snapshot.
"""

SERVICE_NAME = "collector_snapshot"
