"""
1. What this file does:
   Provides the standalone operational CLI entrypoint to run the live collector_ws service.
   Validates Upstox token readiness, acquires exclusive single-owner process lease, initializes
   the binary segment writer, subscribes to requested instruments, and streams live market data.

2. Overall design:
   Coordinates safe command-line startup:
     - Pre-flight Check: Calls TokenManager to assert active valid JWT token before network work.
     - Graceful Market Hours Handling:
       * Weekend check: Informs operator and exits cleanly.
       * Pre-market check (< 09:15 IST): Waits patiently in responsive countdown sleep without crashing.
       * Post-market check (>= 15:35 IST): Informs operator that session ended and exits cleanly.
     - Single Owner Enforcement: Acquires kernel file lock; terminates if another collector runs.
     - Dynamic ATM Discovery: Resolves ATM ± K strike options for active weekly/monthly expiry at market open.
     - Live Streaming: Runs asyncio loop streaming binary WebSocket frames to disk with batched fsync.
     - Market-Close Auto-Shutdown: Monitors Asia/Kolkata session timing (15:35 IST) to terminate cleanly.
     - Signal Handling: Traps SIGINT/SIGTERM to ensure clean buffer flush, segment rotation, and lock release.

3. Elements in the file:
   - setup_logging(): Configures stdout logging format.
   - wait_for_market_open(): Responsive pre-market sleep until 09:15:00 IST.
   - resolve_atm_option_keys(): Discovers ATM ± K option strikes for the active expiry.
   - market_close_watchdog(): Asyncio monitor stopping client at market close.
   - main(): CLI parser and asyncio entrypoint function.

4. Final output of the file:
   - Live running WebSocket collector process writing raw segments to Data/raw/upstox_ws/.
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
import uuid
import zoneinfo
from datetime import datetime, timezone
from datetime import time as dt_time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

KOLKATA_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")


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
       Called in main() before opening WebSocket connections.

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


def resolve_atm_option_keys(
    token: str,
    underlying_key: str = "NSE_INDEX|Nifty 50",
    atm_count: int = 2,
    expiry_date: Optional[str] = None,
) -> list:
    """
    1. The use of function:
       Discovers ATM ± K strike option instrument keys for the active expiry.

    2. How does the specific function work:
       - Queries spot quote to identify current underlying price.
       - Queries active option contracts from Upstox.
       - Discovers nearest expiry date (or uses explicit expiry).
       - Selects ATM strike and K strikes above and below ATM for both CE and PE.
       - Returns list of (instrument_key, trading_symbol) tuples.

    3. Concepts used in the function:
       Dynamic option chain resolution, ATM discovery.

    4. Places where this function is imported and used:
       Called in main() when --atm-count is specified.

    5. Final output of the function, before and after:
       Before: Underlying only. After: List of tradable option instrument keys.
    """
    import requests
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # 1. Spot price
    spot = 22650.0
    try:
        r_spot = requests.get(f"https://api.upstox.com/v2/market-quote/quotes?instrument_key={underlying_key}", headers=headers, timeout=5.0)
        if r_spot.status_code == 200:
            spot_data = r_spot.json().get("data", {})
            for v in spot_data.values():
                if "last_price" in v:
                    spot = float(v["last_price"])
                    break
    except Exception:
        pass

    # 2. Contracts
    contracts_url = f"https://api.upstox.com/v2/option/contract?instrument_key={underlying_key}"
    if expiry_date:
        contracts_url += f"&expiry_date={expiry_date}"
    r_contracts = requests.get(contracts_url, headers=headers, timeout=8.0)
    if r_contracts.status_code != 200:
        return []

    contracts = r_contracts.json().get("data", [])
    if not contracts:
        return []

    expiries = sorted(list({c.get("expiry") for c in contracts if c.get("expiry")}))
    active_expiry = expiry_date or (expiries[0] if expiries else None)
    if not active_expiry:
        return []

    expiry_contracts = [c for c in contracts if c.get("expiry") == active_expiry]
    distinct_strikes = sorted(list({float(c.get("strike_price")) for c in expiry_contracts if c.get("strike_price") is not None}))
    if not distinct_strikes:
        return []

    atm_strike = min(distinct_strikes, key=lambda s: abs(s - spot))
    atm_idx = distinct_strikes.index(atm_strike)
    selected_strikes = set(distinct_strikes[max(0, atm_idx - atm_count) : min(len(distinct_strikes), atm_idx + atm_count + 1)])

    selected = []
    for c in expiry_contracts:
        st = float(c.get("strike_price", 0))
        if st in selected_strikes:
            k = c.get("instrument_key")
            sym = c.get("trading_symbol", k)
            if k:
                selected.append((k, sym))

    return selected


async def market_close_watchdog(
    client: UpstoxWebSocketClient,
    close_time_str: str,
    enabled: bool,
) -> None:
    """
    1. The use of function:
       Asynchronous watchdog monitoring market session timing and requesting clean stop at close.

    2. How does the specific function work:
       - Parses target close time (e.g. 15:35 IST).
       - Periodically checks current time in Asia/Kolkata timezone every 2 seconds.
       - When IST time reaches or exceeds close time, calls client.stop() to flush buffers,
         rotate segment, and release single-owner lease.

    3. Concepts used in the function:
       Asyncio watchdog, market session boundary enforcement, graceful termination.

    4. Places where this function is imported and used:
       Spawned as an asyncio task in main() during connect_and_run().

    5. Final output of the function, before and after:
       Before: Running collector. After: Triggered clean stop at 15:35 IST.
    """
    if not enabled:
        return

    try:
        parts = [int(p) for p in close_time_str.split(":")]
        target_close_time = dt_time(hour=parts[0], minute=parts[1])
    except Exception:
        target_close_time = dt_time(hour=15, minute=35)

    while not client._stop_event.is_set():
        now_ist = datetime.now(KOLKATA_TZ)
        if now_ist.time() >= target_close_time:
            print(f"\n[MARKET CLOSE] Current time {now_ist.strftime('%H:%M:%S')} IST reached market close ({close_time_str} IST).")
            print("Initiating clean collector shutdown, rotating segment, and releasing exclusive lock...")
            client.stop()
            break
        await asyncio.sleep(2.0)


def main() -> None:
    """
    1. The use of function:
       Main CLI entrypoint executing live Upstox WebSocket data collection.

    2. How does the specific function work:
       - Parses command-line arguments (--token, --mode, --instruments, --raw-root, --market-open-time, --market-close-time).
       - Validates token readiness via TokenManager.
       - Performs market hours check (weekend check, pre-market wait until 09:15, post-market exit).
       - Initializes UpstoxWebSocketClient with SingleOwnerLease, SubscriptionManager, and RawSegmentWriter.
       - Launches market_close_watchdog to trigger clean stop at 15:35 IST.
       - Runs asyncio loop until interrupted by user (Ctrl+C) or market close.

    3. Concepts used in the function:
       Command-line interface, process lifecycle management, signal handling, market close boundaries.

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
    parser.add_argument("--atm-count", type=int, default=0, help="Automatically subscribe to ATM ± K option strikes (CE and PE) for active expiry")
    parser.add_argument("--dry-run", action="store_true", help="Capture exactly one live data frame to verify pipeline and exit")
    parser.add_argument("--quiet", action="store_true", help="Disable real-time tick printing to console")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    parser.add_argument("--market-open-time", type=str, default="09:15", help="Market open time in Asia/Kolkata (HH:MM, default: 09:15)")
    parser.add_argument("--market-close-time", type=str, default="15:35", help="Market close cutoff time in Asia/Kolkata (HH:MM, default: 15:35)")
    parser.add_argument("--no-market-hours-check", action="store_true", help="Bypass market hours check (for manual testing/debug)")
    parser.add_argument("--no-market-close-stop", action="store_true", help="Disable automatic clean shutdown at market close")

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
    resolved_token = token_mgr.token or token

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

    if not args.no_market_hours_check and not args.dry_run:
        # Weekend check
        if now_ist.weekday() >= 5:
            day_name = "Saturday" if now_ist.weekday() == 5 else "Sunday"
            print(f"\n[MARKET CLOSED] Today is {day_name}. Indian equity derivatives market (NSE) is closed on weekends.")
            print("Use --no-market-hours-check to bypass this check for testing. Exiting cleanly.")
            return

        # Post-market check
        if now_ist.time() >= close_time:
            print(f"\n[MARKET CLOSED] Current time {now_ist.strftime('%H:%M:%S')} IST is past market close ({args.market_close_time} IST).")
            print("Today's session is already completed. Exiting cleanly without opening WebSocket connection.")
            print("Use --no-market-hours-check to force execution. Exiting.")
            return

        # Pre-market wait check
        if now_ist.time() < open_time:
            can_proceed = wait_for_market_open(open_time)
            if not can_proceed:
                return

    # Step 3: Initialize components
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

    if args.atm_count > 0:
        print(f"\nResolving ATM ± {args.atm_count} option contracts for active expiry...")
        opt_keys = resolve_atm_option_keys(resolved_token, underlying_key=args.instruments[0], atm_count=args.atm_count)
        if opt_keys:
            print(f"Discovered {len(opt_keys)} tradable option contracts:")
            for k, sym in opt_keys:
                print(f"  + {sym:<30} ({k})")
                sub_mgr.add_subscription("atm_selector", k, FeedMode.FULL)

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
    elif not args.quiet:
        print("\n--- Live Market Ticks Streaming (Press Ctrl+C to stop) ---")

        def _on_live_quote(quotes: list[WsQuote]):
            for q in quotes:
                recv_time_str = q.ts_recv[11:19] if len(q.ts_recv) >= 19 else q.ts_recv
                extra_info = []
                if q.oi > 0:
                    extra_info.append(f"OI: {q.oi:,.0f}")
                if q.volume_traded_today > 0:
                    extra_info.append(f"Vol: {q.volume_traded_today:,}")
                if q.bid_px_1 or q.ask_px_1:
                    extra_info.append(f"Bid/Ask: {q.bid_px_1 or 0:.2f}/{q.ask_px_1 or 0:.2f}")
                extra_str = f" | {' | '.join(extra_info)}" if extra_info else ""
                print(
                    f"[{recv_time_str} UTC] {q.instrument_key:<20} | LTP: INR {q.ltp:>10,.2f} | CP: INR {q.cp:>10,.2f}{extra_str} | #{q.collector_sequence_number}"
                )

        client.add_quote_listener(_on_live_quote)

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

    auto_stop_enabled = not args.no_market_close_stop and not args.dry_run

    async def _run_stream_with_watchdog():
        watchdog_task = asyncio.create_task(
            market_close_watchdog(client, args.market_close_time, auto_stop_enabled)
        )
        try:
            await client.connect_and_run(
                max_frames=max_frames,
                timeout_sec=timeout_sec,
            )
        finally:
            watchdog_task.cancel()

    try:
        print(f"Starting collector_ws with PID {os.getpid()}...")
        print(f"Subscribed instruments: {args.instruments} (mode: {feed_mode.value})")
        print("Raw ticks destination: Data/raw/upstox_ws/ticks/trade_date=YYYY-MM-DD/")
        print("Heartbeat pulse: Data/raw/telemetry/heartbeat_collector_ws.json")
        if auto_stop_enabled:
            print(f"Auto-shutdown at market close active: Clean stop at {args.market_close_time} IST.")
        if not args.dry_run:
            print("Press Ctrl+C to safely terminate.")

        loop.run_until_complete(_run_stream_with_watchdog())

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
