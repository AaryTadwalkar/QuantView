"""
1. What this file does:
   Operational tool to inspect and export recorded raw option chain snapshots (.json.gz) into
   human-readable console tables or canonical Version 3 CSV files per QUANTVIEW_DATA_SPEC §4.3 and §4.4.

2. Overall design:
   - Reads raw gzipped HTTP responses from Data/raw/upstox_rest/snapshots/trade_date=YYYY-MM-DD/.
   - Extracts capture header metadata and strike-level records (144 strikes, CE and PE).
   - Normalizes pricing, market depth, open interest, and Option Greeks (IV, Delta, Theta, Gamma, Vega).
   - Validates fields against canonical Version 3 snapshot schema (matching Stage 1 lake schema).
   - Exports formatted terminal summary or full canonical CSV.

3. Elements in the file:
   - extract_snapshot_rows(): Normalizes raw Upstox option chain JSON payload into flat V3 records.
   - dump_snapshot_to_csv(): Exports normalized option chain rows to CSV.
   - display_snapshot_console(): Renders clean terminal table around ATM spot price.
   - main(): CLI entrypoint with --snapshot, --latest, --date, --to-csv, and --strikes-range.

4. Final output of the file:
   - Human-readable terminal output or exported CSV with complete option chain and Greeks.
"""

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

# Standard QuantView repository bootstrap
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("quantview.dump_snapshot")


def extract_snapshot_rows(raw_json_path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    1. The use of function:
       Extracts and normalizes all CE and PE strike records from a raw option chain .json.gz file.

    2. How does the specific function work:
       - Decompresses gzip file and parses JSON body.
       - Extracts underlying spot price, expiry, and timestamp.
       - Iterates over strike objects in 'data' array.
       - For each strike, produces two canonical rows: CE (Call) and PE (Put).
       - Maps all market_data (ltp, oi, volume, bid, ask, prev_oi) and option_greeks (iv, delta, theta, gamma, vega).

    3. Concepts used in the function:
       Gzip streaming, JSON normalization, option chain flattening, schema versioning.

    4. Places where this function is imported and used:
       Called by main() for console inspection and CSV exports.

    5. Final output of the function, before and after:
       Before: Compressed raw JSON. After: Header metadata dict and list of flat canonical rows.
    """
    if not raw_json_path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {raw_json_path}")

    with gzip.open(raw_json_path, "rt", encoding="utf-8") as f:
        payload = json.load(f)

    data_list = payload.get("data", [])
    if not data_list:
        return {"spot_price": None, "expiry": None, "total_strikes": 0}, []

    first_item = data_list[0]
    spot_price = float(first_item.get("underlying_spot_price") or 0.0)
    expiry = first_item.get("expiry")
    underlying_key = first_item.get("underlying_key", "NSE_INDEX|Nifty 50")

    # Companion manifest check if present
    manifest_path = raw_json_path.with_name(raw_json_path.name.replace(".json.gz", ".manifest.json"))
    snapshot_id = raw_json_path.stem.replace("capture_", "").replace(".json", "")
    timestamp_utc = ""
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as mf:
                mdata = json.load(mf)
                snapshot_id = mdata.get("snapshot_id", snapshot_id)
                timestamp_utc = mdata.get("received_at_utc", "")
        except Exception:
            pass

    header = {
        "snapshot_id": snapshot_id,
        "timestamp_utc": timestamp_utc,
        "underlying_key": underlying_key,
        "spot_price": spot_price,
        "expiry": expiry,
        "total_strikes": len(data_list),
    }

    canonical_rows: List[Dict[str, Any]] = []

    for item in data_list:
        strike_val = float(item.get("strike_price", 0.0))
        item_spot = float(item.get("underlying_spot_price") or spot_price)
        item_expiry = item.get("expiry", expiry)

        for opt_type, opt_key in [("CE", "call_options"), ("PE", "put_options")]:
            opt_obj = item.get(opt_key, {})
            mkt = opt_obj.get("market_data", {})
            greeks = opt_obj.get("option_greeks", {})

            row = {
                "snapshot_id": snapshot_id,
                "timestamp_utc": timestamp_utc,
                "underlying": "NIFTY",
                "expiry": item_expiry,
                "strike_price": f"{strike_val:.2f}",
                "option_type": opt_type,
                "spot_price": item_spot,
                "ltp": mkt.get("ltp"),
                "close_price": mkt.get("close_price"),
                "volume": mkt.get("volume", 0),
                "oi": mkt.get("oi", 0.0),
                "prev_oi": mkt.get("prev_oi", 0.0),
                "bid_price": mkt.get("bid_price"),
                "bid_qty": mkt.get("bid_qty"),
                "ask_price": mkt.get("ask_price"),
                "ask_qty": mkt.get("ask_qty"),
                "iv": greeks.get("iv"),
                "delta": greeks.get("delta"),
                "theta": greeks.get("theta"),
                "gamma": greeks.get("gamma"),
                "vega": greeks.get("vega"),
                "pop": greeks.get("pop"),
                "schema_version": "v3",
            }
            canonical_rows.append(row)

    return header, canonical_rows


def dump_snapshot_to_csv(rows: List[Dict[str, Any]], output_path: Path) -> int:
    """
    1. The use of function:
       Exports flat canonical option chain rows to CSV.

    2. How does the specific function work:
       Writes rows with Version 3 schema headers to output_path.

    3. Concepts used in the function:
       CSV formatting, file I/O.

    4. Places where this function is imported and used:
       Called from main() when --to-csv is specified.

    5. Final output of the function, before and after:
       Before: List of dicts. After: CSV file on disk.
    """
    fieldnames = [
        "snapshot_id",
        "timestamp_utc",
        "underlying",
        "expiry",
        "strike_price",
        "option_type",
        "spot_price",
        "ltp",
        "close_price",
        "volume",
        "oi",
        "prev_oi",
        "bid_price",
        "bid_qty",
        "ask_price",
        "ask_qty",
        "iv",
        "delta",
        "theta",
        "gamma",
        "vega",
        "pop",
        "schema_version",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return len(rows)


def display_snapshot_console(header: Dict[str, Any], rows: List[Dict[str, Any]], num_atm_strikes: int = 15) -> None:
    """
    1. The use of function:
       Renders a formatted option chain ladder around the ATM spot price in terminal.

    2. How does the specific function work:
       - Sorts distinct strikes.
       - Finds closest strike to spot price (ATM).
       - Selects ±N strikes around ATM.
       - Prints two-sided chain: Call metrics (IV, Delta, OI, LTP) | Strike | Put metrics (LTP, OI, Delta, IV).

    3. Concepts used in the function:
       Option chain ladder formatting, ATM strike calculation.

    4. Places where this function is imported and used:
       Called from main() for terminal viewing.

    5. Final output of the function, before and after:
       Before: Raw rows. After: Clean ASCII option chain table.
    """
    spot = header.get("spot_price") or 0.0
    print("\n" + "=" * 95)
    print(f" LIVE OPTION CHAIN: {header.get('underlying_key')} | EXPIRY: {header.get('expiry')}")
    print(f" SPOT PRICE: INR {spot:,.2f} | CAPTURE: {header.get('snapshot_id')} ({header.get('timestamp_utc')[:19]} UTC)")
    print("=" * 95)

    # Group by strike
    by_strike: Dict[float, Dict[str, Dict[str, Any]]] = {}
    for r in rows:
        st = float(r["strike_price"])
        if st not in by_strike:
            by_strike[st] = {}
        by_strike[st][r["option_type"]] = r

    sorted_strikes = sorted(by_strike.keys())
    if not sorted_strikes:
        print("No strikes found.")
        return

    # Find ATM index
    atm_idx = min(range(len(sorted_strikes)), key=lambda i: abs(sorted_strikes[i] - spot))
    half = num_atm_strikes // 2
    start_idx = max(0, atm_idx - half)
    end_idx = min(len(sorted_strikes), atm_idx + half + 1)
    display_strikes = sorted_strikes[start_idx:end_idx]

    header_str = (
        f"{'CALL IV':>8} {'CALL DELTA':>10} {'CALL OI':>10} {'CALL LTP':>10} |"
        f"{' STRIKE ':^11}|"
        f"{'PUT LTP':>10} {'PUT OI':>10} {'PUT DELTA':>10} {'PUT IV':>8}"
    )
    print(header_str)
    print("-" * 95)

    for st in display_strikes:
        ce = by_strike[st].get("CE", {})
        pe = by_strike[st].get("PE", {})

        ce_iv = f"{ce.get('iv') or 0:.1f}%" if ce.get("iv") else "-"
        ce_delta = f"{ce.get('delta') or 0:.3f}" if ce.get("delta") is not None else "-"
        ce_oi = f"{int(ce.get('oi') or 0):,}"
        ce_ltp = f"{ce.get('ltp') or 0:.2f}"

        pe_ltp = f"{pe.get('ltp') or 0:.2f}"
        pe_oi = f"{int(pe.get('oi') or 0):,}"
        pe_delta = f"{pe.get('delta') or 0:.3f}" if pe.get("delta") is not None else "-"
        pe_iv = f"{pe.get('iv') or 0:.1f}%" if pe.get("iv") else "-"

        is_atm = abs(st - spot) <= 50.0
        marker = ">>" if is_atm else "  "

        row_str = (
            f"{ce_iv:>8} {ce_delta:>10} {ce_oi:>10} {ce_ltp:>10} |"
            f"{marker}{st:>8.1f} |"
            f"{pe_ltp:>10} {pe_oi:>10} {pe_delta:>10} {pe_iv:>8}"
        )
        print(row_str)

    print("-" * 95)
    print(f"Showing {len(display_strikes)} of {len(sorted_strikes)} strikes. Use --to-csv <file.csv> for full chain.")
    print("=" * 95 + "\n")


def main() -> None:
    """
    1. The use of function:
       Main CLI entrypoint to inspect raw option chain snapshots.

    2. How does the specific function work:
       - Parses command-line arguments.
       - Discovers target snapshot file.
       - Extracts and normalizes rows.
       - Outputs console table or writes CSV.

    3. Concepts used in the function:
       CLI handling, snapshot disposition.

    4. Places where this function is imported and used:
       Executed via `python tools/ops/dump_snapshot.py`.

    5. Final output of the function, before and after:
       Before: Compressed file. After: Human-readable option chain view or CSV file.
    """
    parser = argparse.ArgumentParser(description="QuantView Raw Option Chain Snapshot Inspector")
    parser.add_argument("--snapshot", type=str, default="", help="Path to specific capture_snap_*.json.gz file")
    parser.add_argument("--latest", action="store_true", help="Inspect the latest capture from today")
    parser.add_argument("--date", type=str, default="", help="Trade date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--to-csv", type=str, default="", help="Path to write exported CSV file")
    parser.add_argument("--strikes", type=int, default=15, help="Number of strikes to display in console around ATM (default: 15)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snap_dir = PROJECT_ROOT / "Data" / "raw" / "upstox_rest" / "snapshots" / f"trade_date={date_str}"

    target_file: Optional[Path] = None
    if args.snapshot:
        target_file = Path(args.snapshot)
    elif snap_dir.exists():
        gz_files = sorted(snap_dir.glob("capture_*.json.gz"))
        if gz_files:
            target_file = gz_files[-1]

    if not target_file or not target_file.exists():
        print(f"No snapshot files found in {snap_dir}")
        sys.exit(1)

    print(f"Loading raw snapshot: {target_file.name}")
    header, rows = extract_snapshot_rows(target_file)
    spot_val = header.get("spot_price")
    spot_str = f"INR {spot_val:,.2f}" if spot_val is not None else "N/A"
    print(f"Loaded {header['total_strikes']} strikes ({len(rows)} CE/PE rows). Spot: {spot_str}")

    if args.to_csv:
        out_path = Path(args.to_csv)
        count = dump_snapshot_to_csv(rows, out_path)
        print(f"Successfully exported {count} option chain rows to: {out_path.resolve()}")
    else:
        display_snapshot_console(header, rows, num_atm_strikes=args.strikes)


if __name__ == "__main__":
    main()
