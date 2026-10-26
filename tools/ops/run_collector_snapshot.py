"""
1. What this file does:
   Operational CLI entrypoint to capture live full option chain snapshots via Upstox REST API.
   Captures the complete option chain (all strike prices, calls, puts, OI, volume, IV, Greeks, bid/ask depth)
   and persists raw gzip payloads + self-describing manifests per QUANTVIEW_DATA_SPEC §4.3 and Task M2-01.

2. Overall design:
   - Validates Upstox token readiness using TokenManager before network interactions.
   - Instantiates UpstoxSnapshotAdapter and SnapshotCollectorService with RateBudgetManager.
   - Resolves active expiry dynamically (e.g. nearest weekly/monthly NIFTY expiry).
   - Fetches full option chain response, verifies raw byte durability, writes manifest, and extracts summary.
   - Supports --single (one snapshot) or --loop (periodic capture every N seconds).
   - Features automatic clean shutdown at market close (15:35 Asia/Kolkata) to prevent idle polling after hours.

3. Elements in the file:
   - run_single_capture(): Executes a single full option chain snapshot and prints summary.
   - main(): CLI entrypoint parsing arguments (--underlying, --expiry, --loop, --interval-sec, --market-close-time).

4. Final output of the file:
   - Live captured option chain raw gzip payloads stored in Data/raw/upstox_rest/snapshots/.
"""

import argparse
from datetime import datetime, time as dt_time, timezone
import json
import logging
from pathlib import Path
import sys
import time
from typing import Optional
import zoneinfo

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
KOLKATA_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")


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
       CLI entrypoint for executing live option chain snapshots with market-close boundary protection.

    2. How does the specific function work:
       - Parses command-line arguments (--underlying, --expiry, --loop, --interval-sec, --market-close-time).
       - Validates token readiness via TokenManager.
       - Executes single capture or periodic streaming loop.
       - Monitors Asia/Kolkata time and cleanly breaks the capture loop at market close (default 15:35 IST).

    3. Concepts used in the function:
       CLI interface, loop scheduling, market session boundary enforcement, graceful termination.

    4. Places where this function is imported and used:
       Executed via `python tools/ops/run_collector_snapshot.py`.

    5. Final output of the function, before and after:
       Before: Idle. After: Raw snapshots persisted to Data/raw/upstox_rest/snapshots/ and clean shutdown at close.
    """
    parser = argparse.ArgumentParser(description="QuantView Live Option Chain Snapshot Collector")
    parser.add_argument("--underlying", type=str, default="NSE_INDEX|Nifty 50", help="Underlying key (default: NSE_INDEX|Nifty 50)")
    parser.add_argument("--expiry", type=str, default=None, help="Option expiry date YYYY-MM-DD (optional, auto-detected if omitted)")
    parser.add_argument("--loop", action="store_true", help="Run continuous periodic capture loop")
    parser.add_argument("--interval-sec", type=float, default=60.0, help="Interval in seconds between captures in loop mode (default: 60)")
    parser.add_argument("--market-close-time", type=str, default="15:35", help="Market close cutoff time in Asia/Kolkata (HH:MM, default: 15:35)")
    parser.add_argument("--no-market-close-stop", action="store_true", help="Disable automatic clean shutdown at market close")
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
        try:
            parts = [int(p) for p in args.market_close_time.split(":")]
            close_time = dt_time(hour=parts[0], minute=parts[1])
        except Exception:
            close_time = dt_time(hour=15, minute=35)

        print(f"Starting continuous snapshot loop for {args.underlying} every {args.interval_sec}s.")
        if not args.no_market_close_stop:
            print(f"Auto-shutdown at market close active: Clean stop at {args.market_close_time} IST.")
        print("Press Ctrl+C to stop.")

        try:
            while True:
                now_ist = datetime.now(KOLKATA_TZ)
                if not args.no_market_close_stop and now_ist.time() >= close_time:
                    print(f"\n[MARKET CLOSE] Current time {now_ist.strftime('%H:%M:%S')} IST reached market close ({args.market_close_time} IST).")
                    print("Option chain capture complete. Cleanly stopping snapshot collector.")
                    break

                run_single_capture(collector, args.underlying, args.expiry)

                # Responsive sleep: wake up every 1s to promptly detect market close or user interrupt
                sleep_remaining = args.interval_sec
                while sleep_remaining > 0:
                    step = min(1.0, sleep_remaining)
                    time.sleep(step)
                    sleep_remaining -= step
                    if not args.no_market_close_stop and datetime.now(KOLKATA_TZ).time() >= close_time:
                        break

                if not args.no_market_close_stop and datetime.now(KOLKATA_TZ).time() >= close_time:
                    now_closed = datetime.now(KOLKATA_TZ)
                    print(f"\n[MARKET CLOSE] Current time {now_closed.strftime('%H:%M:%S')} IST reached market close ({args.market_close_time} IST).")
                    print("Option chain capture complete. Cleanly stopping snapshot collector.")
                    break
        except KeyboardInterrupt:
            print("\nSnapshot loop stopped by operator.")


if __name__ == "__main__":
    main()
