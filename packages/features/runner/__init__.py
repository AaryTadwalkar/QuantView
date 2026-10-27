"""
1. What this file does:
   Package exports for QuantView subprocess feature runner.

2. Overall design:
   Re-exports IsolatedFeatureRunner and SubprocessFeatureResult for sandboxed feature execution per ADR-012.

3. Elements in the file:
   - SubprocessFeatureResult, IsolatedFeatureRunner.

4. Final output of the file:
   - Clean public API for packages.features.runner.
"""

from packages.features.runner.subprocess_runner import (
    IsolatedFeatureRunner,
    SubprocessFeatureResult,
)

__all__ = [
    "SubprocessFeatureResult",
    "IsolatedFeatureRunner",
]
