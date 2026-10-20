"""
1. What this file does:
   Defines the service boundary for QuantView REST and WebSocket API gateway.

2. Overall design:
   The api service exposes FastAPI routes for submitting RunConfigs, querying run artifacts,
   inspecting account/deployment states, and streaming market updates to web frontends.
   It delegates business logic to packages/* and worker queues without reimplementing it.

3. Elements in the file:
   - Service metadata and lifecycle contract.

4. Final output of the file:
   - Package interface for services.api.
"""

SERVICE_NAME = "api"
