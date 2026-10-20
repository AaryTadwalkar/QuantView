"""
1. What this file does:
   Defines the root namespace for QuantView central configuration (config/*).

2. Overall design:
   Provides access to central application settings and configuration loaders.

3. Elements in the file:
   - QuantViewSettings and get_settings re-exports.

4. Final output of the file:
   - Exported settings access.
"""

from config.settings import QuantViewSettings, get_settings

__all__ = ["QuantViewSettings", "get_settings"]
