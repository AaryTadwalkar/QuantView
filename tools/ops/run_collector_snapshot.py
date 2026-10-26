"""
1. What this file does:
   Operational CLI entrypoint to capture live full option chain snapshots via Upstox REST API.
   Captures the complete option chain (all strike prices, calls, puts, OI, volume, IV, Greeks, bid/ask depth)
   and persists raw gzip payloads + self-describing manifests per QUANTVIEW_DATA_SPEC §4.3 and Task M2-01.

2. Overall design:
   - Validates Upstox token readiness using TokenManager before network interactions.
   - Instantiates UpstoxSnapshotAdapter and SnapshotCollectorService with RateBudgetManager.
   - Graceful Market Hours Handling:
     * Weekend check: Informs operator and exits cleanly.
     * Pre-market check (< 09:15 IST): Waits patiently in responsive countdown sleep without crashing or spamming.
     * Post-market check (>= 15:35 IST): Informs operator that session ended and exits cleanly.
   - Supports --single (one snapshot) or --loop (periodic capture every N seconds).
   - Features automatic clean shutdown at market close (15:35 Asia/Kolkata).

3. Elements in the file:
   - wait_for_market_open(): Responsive pre-market sleep until 09:15:00 IST.
   - run_single_capture(): Executes a single full option chain snapshot and prints summary.
   - main(): CLI entrypoint parsing arguments (--underlying, --expiry, --loop, --interval-sec, --market-open-time, --market-close-time).

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


def wait_for_market_open(market_open_time: dt_time) -> bool:
    """
    1. The use of function:
       Checks if NSE market is open; if pre-market (< 09:15 IST), waits patiently in loop.

    2. How does the specific function work:
       - Evaluates current time in Asia/Kolkata timezone.
       - If current time is earlier than market_open_time, prints countdown message and sleeps in 5s increments.
       - Returns True once market open boundary is reached, or False if interrupted by user.

    3. Concepts used in the function:
       Pre-market scheduling, responsive polling, graceful non-crash operator UX.

    4. Places where this function is imported and used:
       Called in main() before entering active capture loop.

    5. Final output of the function, before and after:
       Before: Early start. After: Execution synchronized with exchange open time.
    """
    now_ist = datetime.now(KOLKATA_TZ)
    if now_ist.time() >= market_open_time:
        return True

    target_today = now_ist.replace(hour=market_open_time.hour, minute=market_open_time.minute, second=market_open_time.second, microsecond=0)
    delta_secs = max(0, int((target_today - now_ist).total_seconds()))
    hours = delta_secs // 3600
    mins = (delta_secs % 3600) // 60
    print(f"\n[PRE-MARKET WAIT] Current time is {now_ist.strftime('%H:%M:%S')} IST.")
    print(f"NSE market opens at {market_open_time.strftime('%H:%M')} IST (in {hours}h {mins}m).")
    print("Waiting patiently for market open... (Press Ctrl+C to cancel)\n")

    try:
        last_logged = -1
        while True:
            now = datetime.now(KOLKATA_TZ)
            if now.time() >= market_open_time:
                print(f"\n[MARKET OPEN] Current time is {now.strftime('%H:%M:%S')} IST. Market session is now LIVE!")
                return True

            secs_left = max(0, int((target_today - now).total_seconds()))
            if secs_left <= 0:
                print(f"\n[MARKET OPEN] Current time is {now.strftime('%H:%M:%S')} IST. Market session is now LIVE!")
                return True

            if secs_left != last_logged and (secs_left % 60 == 0 or secs_left <= 10):
                print(f"[PRE-MARKET] Time until market open: {secs_left // 60}m {secs_left % 60}s ({now.strftime('%H:%M:%S')} IST)")
                last_logged = secs_left
            time.sleep(min(5.0, max(1.0, float(secs_left))))
    except KeyboardInterrupt:
        print("\nPre-market wait cancelled by operator.")
        return False


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
       CLI entrypoint for executing live option chain snapshots with pre-market and market-close protections.

    2. How does the specific function work:
       - Parses command-line arguments (--underlying, --expiry, --loop, --interval-sec, --market-open-time, --market-close-time).
       - Validates token readiness via TokenManager.
       - Performs market hours check (weekend check, pre-market wait until 09:15, post-market exit).
       - Executes single capture or periodic streaming loop.
       - Cleanly halts at market close (default 15:35 IST).

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
    parser.add_argument("--market-open-time", type=str, default="09:15", help="Market open time in Asia/Kolkata (HH:MM, default: 09:15)")
    parser.add_argument("--market-close-time", type=str, default="15:35", help="Market close cutoff time in Asia/Kolkata (HH:MM, default: 15:35)")
    parser.add_argument("--no-market-hours-check", action="store_true", help="Bypass market hours check (for manual testing/debug)")
    parser.add_argument("--no-market-close-stop", action="store_true", help="Disable automatic clean shutdown at market close")
    args = parser.parse_args()

    # Step 1: Pre-flight token readiness check
    print("\n--- QuantView Live Option Chain Snapshot Collector ---")
    token_mgr = TokenManager()
    readiness = token_mgr.check_token_readiness()
    if not readiness.is_ready:
        print(f"ERROR: Upstox access token check failed: {readiness.message}")
        sys.exit(1)

    print(f"Token Readiness: PASS (Expires: {readiness.expires_at_utc})")
    token = token_mgr.token

    # Step 2: Market hours evaluation
    try:
        parts_open = [int(p) for p in args.market_open_time.split(":")]
        open_time = dt_time(hour=parts_open[0], minute=parts_open[1])
    except Exception:
        open_time = dt_time(hour=9, minute=15)

    try:
        parts_close = [int(p) for p in args.market_close_time.split(":")]
        close_time = dt_time(hour=parts_close[0], minute=parts_close[1])
    except Exception:
        close_time = dt_time(hour=15, minute=35)

    now_ist = datetime.now(KOLKATA_TZ)

    if not args.no_market_hours_check:
        # Weekend check
        if now_ist.weekday() >= 5:
            day_name = "Saturday" if now_ist.weekday() == 5 else "Sunday"
            print(f"\n[MARKET CLOSED] Today is {day_name}. Indian equity derivatives market (NSE) is closed on weekends.")
            print("Use --no-market-hours-check to bypass this check for testing. Exiting cleanly.")
            return

        # Post-market check
        if now_ist.time() >= close_time:
            print(f"\n[MARKET CLOSED] Current time {now_ist.strftime('%H:%M:%S')} IST is past market close ({args.market_close_time} IST).")
            print("Today's session is already completed. Exiting cleanly without making network calls.")
            print("Use --no-market-hours-check to force execution. Exiting.")
            return

        # Pre-market wait check
        if now_ist.time() < open_time:
            can_proceed = wait_for_market_open(open_time)
            if not can_proceed:
                return

    # Step 3: Initialize components
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
        print(f"Starting continuous snapshot loop for {args.underlying} every {args.interval_sec}s.")
        if not args.no_market_close_stop:
            print(f"Auto-shutdown at market close active: Clean stop at {args.market_close_time} IST.")
        print("Press Ctrl+C to stop.")

        try:
            while True:
                curr_ist = datetime.now(KOLKATA_TZ)
                if not args.no_market_close_stop and curr_ist.time() >= close_time:
                    print(f"\n[MARKET CLOSE] Current time {curr_ist.strftime('%H:%M:%S')} IST reached market close ({args.market_close_time} IST).")
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
