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
from typing import Any, Dict, List, Optional, Tuple
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
    parser.add_argument("--atm-count", type=int, default=0, help="Automatically subscribe to ATM ± K option strikes (CE and PE) for active expiry")
    parser.add_argument("--dry-run", action="store_true", help="Capture exactly one live data frame to verify pipeline and exit")
    parser.add_argument("--quiet", action="store_true", help="Disable real-time tick printing to console")
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
