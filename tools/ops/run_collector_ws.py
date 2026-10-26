"""
1. What this file does:
   Provides the standalone operational CLI entrypoint to run the live collector_ws service.
   Validates Upstox token readiness, acquires exclusive single-owner process lease, initializes
   the binary segment writer, subscribes to requested instruments, and streams live market data.

2. Overall design:
   Coordinates safe command-line startup:
     - Pre-flight Check: Calls TokenManager to assert active valid JWT token before network work.
     - Single Owner Enforcement: Acquires kernel file lock; terminates if another collector runs.
     - Subscription Setup: Configures SubscriptionManager with instruments and requested feed mode.
     - Live Streaming: Runs asyncio loop streaming binary WebSocket frames to disk with batched fsync.
     - Signal Handling: Traps SIGINT/SIGTERM to ensure clean buffer flush and lock file release.

3. Elements in the file:
   - main(): CLI parser and asyncio entrypoint function.

4. Final output of the file:
   - Live running WebSocket collector process writing raw segments to Data/raw/upstox_ws/.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import signal
import sys
import uuid

# Standard QuantView repository bootstrap
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.collector_snapshot.token_manager import TokenManager
from services.collector_ws.client import UpstoxWebSocketClient, WebSocketClientConfig
from services.collector_ws.decoder import WsQuote, WsQuoteDecoder
from services.collector_ws.lease import DuplicateCollectorInstanceError, SingleOwnerLease
from services.collector_ws.raw_segment_writer import RawSegmentWriter
from services.collector_ws.subscription import FeedMode, SubscriptionConfig, SubscriptionManager


def setup_logging(verbose: bool = False) -> None:
    """
    1. The use of function:
       Configures formatted console logging for the collector_ws runner.

    2. How does the specific function work:
       Configures standard logging with timestamp, level, and module name.

    3. Concepts used in the function:
       Operational observability.

    4. Places where this function is imported and used:
       Called at CLI startup in main().

    5. Final output of the function, before and after:
       Before: Unconfigured logger. After: Formatted logging handlers active.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def main() -> None:
    """
    1. The use of function:
       Main CLI entrypoint executing live Upstox WebSocket data collection.

    2. How does the specific function work:
       - Parses command-line arguments (--token, --mode, --instruments, --raw-root).
       - Validates token readiness via TokenManager.
       - Initializes UpstoxWebSocketClient with SingleOwnerLease, SubscriptionManager, and RawSegmentWriter.
       - Runs asyncio loop until interrupted by user (Ctrl+C).

    3. Concepts used in the function:
       Command-line interface, process lifecycle management, signal handling.

    4. Places where this function is imported and used:
       Executed directly from terminal via `python tools/ops/run_collector_ws.py`.

    5. Final output of the function, before and after:
       Before: Idle terminal. After: Streaming live market frames or exiting with diagnostic code.
    """
    parser = argparse.ArgumentParser(description="QuantView Live Upstox WebSocket Market Data Collector")
    parser.add_argument("--token", type=str, default="", help="Upstox OAuth Bearer token (defaults to UPSTOX_ACCESS_TOKEN from .env)")
    parser.add_argument("--mode", type=str, default="full", choices=["ltpc", "full", "full_d30"], help="Default feed mode (default: full)")
    parser.add_argument("--instruments", type=str, nargs="+", default=["NSE_INDEX|Nifty 50"], help="Instrument keys to subscribe (default: NSE_INDEX|Nifty 50)")
    parser.add_argument("--raw-root", type=str, default="", help="Root directory for raw ticks (default: Data/raw/upstox_ws)")
    parser.add_argument("--max-frames", type=int, default=None, help="Stop after capturing N frames (optional)")
    parser.add_argument("--timeout-sec", type=float, default=None, help="Stop after N seconds (optional)")
    parser.add_argument("--dry-run", action="store_true", help="Capture exactly one live data frame to verify pipeline and exit")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger("quantview.collector_ws.cli")

    # Resolve token: explicit CLI arg → shell env var → .env auto-discovery via TokenManager.
    # Pass None (not "") so TokenManager._discover_token() reads .env when no explicit token set.
    token = args.token or os.environ.get("UPSTOX_ACCESS_TOKEN") or None

    # Step 1: Pre-flight token readiness check
    print("\n--- QuantView Live WebSocket Collector (M2-05) ---")
    token_mgr = TokenManager(token=token)
    readiness = token_mgr.check_token_readiness()

    if not readiness.is_ready:
        print(f"ERROR: Upstox access token check failed: {readiness.message}")
        print("Please generate a valid token from Upstox Developer Console and set UPSTOX_ACCESS_TOKEN in .env.")
        sys.exit(1)

    print(f"Token Readiness: PASS (Expires: {readiness.expires_at_utc})")

    # After readiness check, extract the actual resolved token from TokenManager (which loaded .env).
    # This ensures the WebSocket client receives the real token string even when CLI --token was omitted.
    resolved_token = token_mgr.token or token

    # Step 2: Initialize components
    raw_root = Path(args.raw_root) if args.raw_root else None
    conn_id = str(uuid.uuid4())
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    writer = RawSegmentWriter(
        connection_id=conn_id,
        trade_date=today_str,
        base_raw_dir=raw_root,
    )
    lease = SingleOwnerLease()
    sub_mgr = SubscriptionManager()

    feed_mode = FeedMode(args.mode)
    for key in args.instruments:
        sub_mgr.add_subscription("cli_operator", key, feed_mode)

    client = UpstoxWebSocketClient(
        token=resolved_token,
        lease=lease,
        subscription_manager=sub_mgr,
        segment_writer=writer,
    )

    # If dry-run requested, allow up to 10 frames to capture initial market quote, then stop immediately
    max_frames = 10 if args.dry_run else args.max_frames
    timeout_sec = (args.timeout_sec or 15.0) if args.dry_run else args.timeout_sec

    dry_run_quote_received = False

    if args.dry_run:
        print("\nMode: DRY-RUN (Will capture live market frame, display parsed fields, and exit cleanly)")

        def _on_dry_run_quote(quotes: list[WsQuote]):
            nonlocal dry_run_quote_received
            if not quotes:
                return
            dry_run_quote_received = True
            print("\n" + "=" * 65)
            print(" LIVE WEBSOCKET DRY-RUN: RECEIVED & DECODED LIVE FRAME")
            print("=" * 65)
            for q in quotes:
                print(f" Instrument:    {q.instrument_key}")
                print(f" Feed Type:     {q.feed_type} (Mode: {q.feed_mode})")
                print(f" Last Price:    INR {q.ltp:,.2f} | Quantity: {q.ltq}")
                print(f" Close Price:   INR {q.cp:,.2f} | ATP: INR {q.atp:,.2f}")
                print(f" Day Volume:    {q.volume_traded_today:,} | Open Interest: {q.oi:,}")
                print(f" Event Time:    {q.ts_event or 'N/A'}")
                print(f" Receive Time:  {q.ts_recv}")
                print(f" Message ID:    {q.message_id[:24]}...")
                if q.bid_px_1 or q.ask_px_1:
                    print(f" Top Bid / Ask: INR {q.bid_px_1 or 0:.2f} (qty: {q.bid_qty_1 or 0}) / INR {q.ask_px_1 or 0:.2f} (qty: {q.ask_qty_1 or 0})")
                if q.iv_observed is not None:
                    print(f" Greeks:        IV: {q.iv_observed:.2f}%, Delta: {q.delta_observed:.3f}, Theta: {q.theta_observed:.2f}")
                if q.quality_flags:
                    print(f" Quality Flags: {', '.join(q.quality_flags)}")
            print("=" * 65 + "\n")
            client.stop()

        client.add_quote_listener(_on_dry_run_quote)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Attach signal handler for graceful shutdown
    def _sig_handler():
        logger.info("Received termination signal. Stopping collector...")
        client.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda s, f: _sig_handler())
        except Exception:
            pass

    try:
        print(f"Starting collector_ws with PID {os.getpid()}...")
        print(f"Subscribed instruments: {args.instruments} (mode: {feed_mode.value})")
        print("Raw ticks destination: Data/raw/upstox_ws/ticks/trade_date=YYYY-MM-DD/")
        print("Heartbeat pulse: Data/raw/telemetry/heartbeat_collector_ws.json")
        if not args.dry_run:
            print("Press Ctrl+C to safely terminate.")

        loop.run_until_complete(
            client.connect_and_run(
                max_frames=max_frames,
                timeout_sec=timeout_sec,
            )
        )
        if args.dry_run:
            if dry_run_quote_received or writer.total_frames_written >= 1:
                print("DRY-RUN RESULT: PASS (Live market frame captured, persisted, and decoded).")
            else:
                print("DRY-RUN RESULT: TIMED OUT (No live market frames received within timeout).")
    except DuplicateCollectorInstanceError as dup_err:
        print(f"\nFATAL: {dup_err}")
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
    finally:
        client.stop()
        loop.close()
        print("Collector stopped cleanly. Exclusive lock released.")


if __name__ == "__main__":
    main()
