"""
1. What this file does:
   Defines the service boundary for worker_data (data normalization and lake publisher).

2. Overall design:
   worker_data reads raw gzipped API responses, validates records against canonical schemas,
   writes intermediate Parquet partitions into staging/, verifies integrity, and atomically
   renames them into the data lake while updating dataset manifests.

3. Elements in the file:
   - Service metadata and lifecycle contract.

4. Final output of the file:
   - Package interface for services.worker_data.
"""

SERVICE_NAME = "worker_data"
