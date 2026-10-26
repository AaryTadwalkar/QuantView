"""
1. What this file does:
   Operational CLI entrypoint to capture live full option chain snapshots via Upstox REST API.
   Captures the complete option chain (all strike prices, calls, puts, OI, volume, IV, Greeks, bid/ask depth)
   and persists raw gzip payloads + self-describing manifests per QUANTVIEW_DATA_SPEC §4.3 and Task M2-01.

2. Overall design:
   - Validates Upstox token readiness using TokenManager.
   - Instantiates UpstoxSnapshotAdapter and SnapshotCollectorService.
   - Resolves active expiry dynamically (e.g. nearest weekly/monthly NIFTY expiry).
   - Fetches full option chain response, verifies raw byte durability, writes manifest, and extracts summary.
   - Supports --single (one snapshot) or --loop (periodic capture every N seconds during market hours).

3. Elements in the file:
   - run_single_capture(): Executes a single full option chain snapshot and prints summary.
   - main(): CLI entrypoint parsing arguments (--underlying, --expiry, --loop, --interval-sec).

4. Final output of the file:
   - Live captured option chain raw gzip payloads stored in Data/raw/upstox_rest/snapshots/.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
import time
from typing import Optional

# Standard QuantView repository bootstrap
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from packages.data.budget import RateBudgetManager
from services.collector_snapshot.adapter import UpstoxSnapshotAdapter
from services.collector_snapshot.collector import SnapshotCollectorService
from services.collector_snapshot.raw_writer import RawSnapshotWriter
from services.collector_snapshot.token_manager import TokenManager

logger = logging.getLogger("quantview.collector_snapshot.cli")


def run_single_capture(
    collector: SnapshotCollectorService,
    underlying_key: str,
    expiry_date: Optional[str] = None,
) -> dict:
    """
    1. The use of function:
       Dispatches a single full option chain snapshot capture and prints diagnostic output.

    2. How does the specific function work:
       - Calls collector.capture_once() with underlying and expiry.
       - Formats and displays capture metadata: capture_id, row count, spot price, raw payload size.

    3. Concepts used in the function:
       REST snapshot ingestion, raw-first durability verification.

    4. Places where this function is imported and used:
       Called from main() in CLI runner.

    5. Final output of the function, before and after:
       Before: Idle. After: Snapshot written to disk and summary dictionary returned.
    """
    print(f"\n--- Initiating Option Chain Snapshot for {underlying_key} ---")
    summary = collector.capture_once(
        instrument_key=underlying_key,
        expiry_date=expiry_date,
    )
    print("=" * 65)
    print(" LIVE OPTION CHAIN SNAPSHOT CAPTURE RESULT")
    print("=" * 65)
    print(f" Capture ID:    {summary.get('snapshot_id')}")
    print(f" Status:        {summary.get('status')} (Decoder: {summary.get('decoder_status')})")
    print(f" Trade Date:    {summary.get('trade_date')}")
    print(f" Underlying:    {underlying_key}")
    print(f" Expiry:        {summary.get('expiry')}")
    print(f" Spot Price:    INR {summary.get('spot_price') or 0:,.2f}")
    print(f" Total Strikes: {summary.get('row_count', 0)}")
    print(f" Raw Bytes:     {summary.get('compressed_bytes', 0):,} bytes (gzipped)")
    print(f" Raw File:      {summary.get('raw_file_path')}")
    print(f" Manifest:      {summary.get('manifest_path')}")
    print("=" * 65 + "\n")
    return summary


def main() -> None:
    """
    1. The use of function:
       CLI entrypoint for executing live option chain snapshots.

    2. How does the specific function work:
       - Parses command-line arguments (--underlying, --expiry, --loop, --interval-sec).
       - Validates token readiness.
       - Executes single capture or periodic streaming loop.

    3. Concepts used in the function:
       CLI interface, loop scheduling, graceful termination.

    4. Places where this function is imported and used:
       Executed via `python tools/ops/run_collector_snapshot.py`.

    5. Final output of the function, before and after:
       Before: Idle. After: Raw snapshots persisted to Data/raw/upstox_rest/snapshots/.
    """
    parser = argparse.ArgumentParser(description="QuantView Live Option Chain Snapshot Collector")
    parser.add_argument("--underlying", type=str, default="NSE_INDEX|Nifty 50", help="Underlying key (default: NSE_INDEX|Nifty 50)")
    parser.add_argument("--expiry", type=str, default=None, help="Option expiry date YYYY-MM-DD (optional, auto-detected if omitted)")
    parser.add_argument("--loop", action="store_true", help="Run continuous periodic capture loop")
    parser.add_argument("--interval-sec", type=float, default=60.0, help="Interval in seconds between captures in loop mode (default: 60)")
    args = parser.parse_args()

    # Step 1: Pre-flight token readiness check
    token_mgr = TokenManager()
    readiness = token_mgr.check_token_readiness()
    if not readiness.is_ready:
        print(f"ERROR: Upstox access token check failed: {readiness.message}")
        sys.exit(1)

    print(f"Token Readiness: PASS (Expires: {readiness.expires_at_utc})")
    token = token_mgr.token

    # Step 2: Initialize components
    budget_mgr = RateBudgetManager()
    adapter = UpstoxSnapshotAdapter(
        access_token=token,
        budget_manager=budget_mgr,
    )
    raw_writer = RawSnapshotWriter()
    collector = SnapshotCollectorService(
        adapter=adapter,
        writer=raw_writer,
    )

    if not args.loop:
        run_single_capture(collector, args.underlying, args.expiry)
    else:
        print(f"Starting continuous snapshot loop for {args.underlying} every {args.interval_sec}s. Press Ctrl+C to stop.")
        try:
            while True:
                run_single_capture(collector, args.underlying, args.expiry)
                time.sleep(args.interval_sec)
        except KeyboardInterrupt:
            print("\nSnapshot loop stopped by operator.")


if __name__ == "__main__":
    main()
