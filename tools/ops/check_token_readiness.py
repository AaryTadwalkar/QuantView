"""
1. What this file does:
   Standalone CLI pre-flight token readiness verification tool (check_token_readiness.py).
   Executes the authoritative 08:45 Asia/Kolkata pre-market authentication gate, validates JWT expiry,
   transitions to WAITING_FOR_TOKEN on failure, and exits with non-zero code on unauthenticated state
   per QUANTVIEW_MASTER_SPEC §4, QUANTVIEW_ENGINE_UI_RESEARCH_SPEC §10, and Task M2-06.

2. Overall design:
   Coordinates pre-market command-line validation:
     - Discovers active Upstox access token from environment, arguments, or .env file.
     - Inspects expiration timestamp against local and UTC clocks.
     - Enforces secret masking: raw token values are never printed to terminal or written to disk.
     - Emits structured exit codes:
       * Exit 0: Token VALID and ready for market session.
       * Exit 1: Token WAITING_FOR_TOKEN, EXPIRED, or MISSING.
     - Supports optional JSON output for integration into systemd timers and health dashboards.

3. Elements in the file:
   - main(): Command-line interface parser and execution entrypoint.

4. Final output of the file:
   - Terminal status display and programmatic exit code (0 for valid, 1 for waiting/expired).
"""

import argparse
import json
import sys
from pathlib import Path

# Standard QuantView repository bootstrap
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.collector_snapshot.token_manager import TokenManager, TokenState


def main() -> int:
    """
    1. The use of function:
       Main execution function for the pre-market token readiness CLI tool.

    2. How does the specific function work:
       Parses command-line arguments, instantiates TokenManager, runs run_pre_market_check(),
       prints masked results, and returns exit code 0 on VALID or 1 on failure.

    3. Concepts used in the function:
       CLI argument parsing, exit code conventions, credential protection.

    4. Places where this function is imported and used:
       Executed directly from command line or called by morning systemd timers / cron tasks.

    5. Final output of the function, before and after:
       Before: Unchecked token state. After: Process exits with status code 0 (success) or 1 (failure).
    """
    parser = argparse.ArgumentParser(description="QuantView 08:45 Pre-Market Token Readiness Check")
    parser.add_argument("--token", type=str, default=None, help="Explicit token to validate (optional)")
    parser.add_argument("--env-file", type=str, default=None, help="Path to custom .env file")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    env_path = Path(args.env_file) if args.env_file else None
    manager = TokenManager(token=args.token, env_file_path=env_path)
    result = manager.run_pre_market_check()

    if args.json_output:
        print(
            json.dumps(
                {
                    "state": result.state.value,
                    "is_ready": result.is_ready,
                    "expires_at_utc": result.expires_at_utc,
                    "checked_at_utc": result.checked_at_utc,
                    "message": result.message,
                },
                indent=2,
            )
        )
    else:
        print("=" * 65)
        print(" QUANTVIEW 08:45 ASIA/KOLKATA PRE-MARKET AUTHENTICATION CHECK")
        print("=" * 65)
        print(f" Status:        {result.state.value}")
        print(f" Ready:         {result.is_ready}")
        print(f" Checked At:    {result.checked_at_utc}")
        print(f" Expires At:    {result.expires_at_utc or 'N/A'}")
        print(f" Details:       {result.message}")
        print("=" * 65)

        if not result.is_ready:
            print("[ACTION REQUIRED] Daily Upstox human login required.")
            print("Please authenticate, copy token to UPSTOX_ACCESS_TOKEN in .env, and re-run.")
            print("=" * 65)

    return 0 if result.is_ready else 1


if __name__ == "__main__":
    sys.exit(main())
