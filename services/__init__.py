"""
1. What this file does:
   Defines the root namespace for QuantView operational daemon services (services/*).

2. Overall design:
   Services are independent executable processes (or background daemons) that orchestrate
   data collection, backfilling, compute workers, API serving, and live monitoring.
   Each service is self-contained with its own main entry point.

3. Elements in the file:
   - Root service namespace metadata.

4. Final output of the file:
   - Python package namespace for services.*.
"""

__version__ = "0.1.0"
