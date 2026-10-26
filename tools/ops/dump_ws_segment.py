"""
1. What this file does:
   Utility CLI to inspect and export recorded binary Upstox WebSocket segments (.bin.gz or .bin.partial)
   into chronologically ordered, contract-enriched CSV files or formatted console tables.

2. Overall design:
   - Reads raw compressed frames from Data/raw/upstox_ws/ticks/ across one or multiple segment files.
   - Extracts binary frames using unpack_frames_from_bytes and decodes Protobuf payloads via WsQuoteDecoder.
   - Enriches each quote with contract metadata (trading symbol, strike price, option type, expiry)
     from config/live_contracts_cache.json.
   - Tracks underlying Nifty 50 spot price and intraday OHLC across the stream to associate with option ticks.
   - Sorts all records chronologically by receipt timestamp (ts_recv) and collector sequence number.
   - Exports comprehensive tabular CSV (including all Option Greeks, market depth, day/1m OHLC) or prints to stdout.

3. Elements in the file:
   - load_contracts_cache(): Loads local instrument-to-contract dictionary.
   - resolve_contract_metadata(): Maps instrument keys to human-readable symbol, strike, type, and expiry.
   - extract_quotes_from_file(): Decodes frames from an individual .bin.gz or .bin.partial segment.
   - dump_segment_to_csv(): Sorts quotes chronologically, binds underlying spot, and writes full-schema CSV.
   - dump_segment_to_console(): Displays chronologically sorted summary ladder in terminal.
   - main(): CLI entrypoint parsing arguments (--segment, --date, --to-csv, --limit).

4. Final output of the file:
   - Chronologically sorted, contract-enriched CSV or terminal summary table with exact strikes, LTP,
     Greeks, depth, and Nifty 50 underlying levels.
"""

import argparse
import csv
from datetime import datetime, timezone
import gzip
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import zoneinfo

# Standard QuantView repository bootstrap
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.collector_ws.decoder import WsQuote, WsQuoteDecoder
from services.collector_ws.framing import unpack_frames_from_bytes

logger = logging.getLogger("quantview.dump_ws")
KOLKATA_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")


def load_contracts_cache() -> Dict[str, Dict[str, Any]]:
    """
    1. The use of function:
       Loads local offline option contracts dictionary mapping instrument_key to metadata.

    2. How does the specific function work:
       - Looks for config/live_contracts_cache.json in the repository root.
       - Deserializes JSON mapping containing symbol, strike, type, and expiry.
       - Returns empty dictionary if file does not exist or fails to parse.

    3. Concepts used in the function:
       JSON deserialization, cache lookup, offline metadata resolution.

    4. Places where this function is imported and used:
       Called at startup in dump_segment_to_csv() and main().

    5. Final output of the function, before and after:
       Before: Unloaded cache. After: In-memory dictionary of instrument keys to contract metadata.
    """
    cache_path = PROJECT_ROOT / "config" / "live_contracts_cache.json"
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as ex:
        logger.warning("Could not load contracts cache: %s", ex)
        return {}


def resolve_contract_metadata(instrument_key: str, cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    1. The use of function:
       Resolves human-readable symbol, strike price, option type, and expiry for any instrument key.

    2. How does the specific function work:
       - Checks if instrument_key represents the cash index (NSE_INDEX|Nifty 50).
       - Checks cache dictionary for pre-cached instrument key metadata.
       - Falls back to parsing heuristics for synthetic or missing keys.

    3. Concepts used in the function:
       Metadata resolution, contract identification.

    4. Places where this function is imported and used:
       Called inside dump_segment_to_csv() and dump_segment_to_console().

    5. Final output of the function, before and after:
       Before: Raw instrument key (e.g. NSE_FO|51338). After: Dict with symbol, strike, type, expiry.
    """
    if "NSE_INDEX" in instrument_key or "Nifty 50" in instrument_key:
        return {
            "symbol": "NIFTY 50",
            "strike_price": "",
            "option_type": "INDEX",
            "expiry": "",
        }

    cached = cache.get(instrument_key)
    if cached:
        return {
            "symbol": cached.get("symbol", instrument_key),
            "strike_price": cached.get("strike", ""),
            "option_type": cached.get("type", "OPT"),
            "expiry": cached.get("expiry", ""),
        }

    # Fallback heuristic
    return {
        "symbol": instrument_key,
        "strike_price": "",
        "option_type": "OPT" if "NSE_FO" in instrument_key else "EQ",
        "expiry": "",
    }


def to_ist_string(utc_iso_str: Optional[str]) -> str:
    """
    1. The use of function:
       Converts an ISO UTC timestamp string into a readable Asia/Kolkata (IST) timestamp string.

    2. How does the specific function work:
       - Parses ISO UTC timestamp into datetime object.
       - Converts timezone to Asia/Kolkata.
       - Formats as 'YYYY-MM-DD HH:MM:SS.fff IST'.

    3. Concepts used in the function:
       Timezone conversion, Indian market time representation.

    4. Places where this function is imported and used:
       Called during CSV and console row formatting.

    5. Final output of the function, before and after:
       Before: UTC ISO string (e.g. '2026-10-26T08:30:00+00:00'). After: IST string.
    """
    if not utc_iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(utc_iso_str)
        ist_dt = dt.astimezone(KOLKATA_TZ)
        return ist_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " IST"
    except Exception:
        return utc_iso_str


def extract_quotes_from_file(file_path: Path, decoder: WsQuoteDecoder) -> List[WsQuote]:
    """
    1. The use of function:
       Extracts and decodes all canonical WsQuote records from a single raw segment file.

    2. How does the specific function work:
       - Opens file (.bin.gz via gzip.open or .bin.partial via open binary).
       - Reads bytes and calls unpack_frames_from_bytes().
       - Iterates through frames and calls decoder.decode_frame() on each.
       - Returns aggregated list of decoded WsQuote records.

    3. Concepts used in the function:
       Binary deserialization, protobuf unpacking, crash resilience.

    4. Places where this function is imported and used:
       Called by dump_segment_to_csv() and main().

    5. Final output of the function, before and after:
       Before: Raw file on disk. After: List of parsed WsQuote dataclass instances.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Segment file not found: {file_path}")

    if file_path.suffix == ".gz":
        with gzip.open(file_path, "rb") as f:
            raw_data = f.read()
    else:
        with open(file_path, "rb") as f:
            raw_data = f.read()

    frames, _, _ = unpack_frames_from_bytes(raw_data)
    quotes: List[WsQuote] = []
    for fr in frames:
        decoded = decoder.decode_frame(
            raw_payload=fr.payload,
            collector_sequence=fr.sequence_number,
            arrival_ts_us=fr.recv_time_us,
            payload_checksum=fr.payload_crc32,
            raw_segment_ref=file_path.name,
        )
        quotes.extend(decoded)
    return quotes


def dump_segment_to_csv(
    quotes: List[WsQuote],
    output_csv: Path,
    contracts_cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> int:
    """
    1. The use of function:
       Exports quotes to CSV sorted chronologically by timestamp, enriched with strike prices,
       Option Greeks, depth, and live underlying Nifty 50 spot levels.

    2. How does the specific function work:
       - Sorts quotes chronologically by (ts_recv, collector_sequence_number).
       - Scans and tracks running Nifty 50 spot price so option rows include current spot.
       - Enriches each row with symbol, strike, option type, and expiry from contracts cache.
       - Unpacks day OHLC and 1-minute intraday candle bars.
       - Writes formatted CSV to destination path.

    3. Concepts used in the function:
       Chronological sort, underlying spot tracking, contract enrichment, CSV serialization.

    4. Places where this function is imported and used:
       Called from main() when --to-csv is supplied.

    5. Final output of the function, before and after:
       Before: Unordered quotes in memory. After: Formatted, sorted CSV file saved to output_csv.
    """
    if contracts_cache is None:
        contracts_cache = load_contracts_cache()

    # Step 1: Sort chronologically
    quotes.sort(key=lambda q: (q.ts_recv or "", q.collector_sequence_number or 0))

    # Step 2: Pre-scan to find baseline Nifty spot price if available
    running_spot = ""
    for q in quotes:
        if ("NSE_INDEX" in q.instrument_key or "Nifty 50" in q.instrument_key) and q.ltp > 0:
            running_spot = q.ltp
            break

    fieldnames = [
        "ts_recv_utc",
        "ts_recv_ist",
        "instrument_key",
        "trading_symbol",
        "strike_price",
        "option_type",
        "expiry",
        "ltp",
        "underlying_spot_ltp",
        "ltq",
        "cp",
        "atp",
        "volume_traded_today",
        "oi",
        "iv_observed",
        "delta_observed",
        "theta_observed",
        "gamma_observed",
        "vega_observed",
        "rho_observed",
        "bid_px_1",
        "bid_qty_1",
        "ask_px_1",
        "ask_qty_1",
        "day_open",
        "day_high",
        "day_low",
        "day_close",
        "candle_1m_open",
        "candle_1m_high",
        "candle_1m_low",
        "candle_1m_close",
        "candle_1m_vol",
        "quality_flags",
        "collector_sequence_number",
        "feed_mode",
        "feed_type",
        "message_id",
    ]

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for q in quotes:
            # Update running Nifty spot
            if ("NSE_INDEX" in q.instrument_key or "Nifty 50" in q.instrument_key) and q.ltp > 0:
                running_spot = q.ltp

            meta = resolve_contract_metadata(q.instrument_key, contracts_cache)
            row: Dict[str, Any] = {
                "ts_recv_utc": q.ts_recv,
                "ts_recv_ist": to_ist_string(q.ts_recv),
                "instrument_key": q.instrument_key,
                "trading_symbol": meta["symbol"],
                "strike_price": meta["strike_price"],
                "option_type": meta["option_type"],
                "expiry": meta["expiry"],
                "ltp": f"{q.ltp:.2f}" if q.ltp else "",
                "underlying_spot_ltp": f"{running_spot:.2f}" if isinstance(running_spot, (int, float)) else str(running_spot),
                "ltq": q.ltq,
                "cp": f"{q.cp:.2f}" if q.cp else "",
                "atp": f"{q.atp:.2f}" if q.atp else "",
                "volume_traded_today": q.volume_traded_today,
                "oi": f"{q.oi:.0f}" if q.oi else "",
                "iv_observed": f"{q.iv_observed:.2f}" if q.iv_observed is not None else "",
                "delta_observed": f"{q.delta_observed:.4f}" if q.delta_observed is not None else "",
                "theta_observed": f"{q.theta_observed:.4f}" if q.theta_observed is not None else "",
                "gamma_observed": f"{q.gamma_observed:.4f}" if q.gamma_observed is not None else "",
                "vega_observed": f"{q.vega_observed:.4f}" if q.vega_observed is not None else "",
                "rho_observed": f"{q.rho_observed:.4f}" if q.rho_observed is not None else "",
                "bid_px_1": f"{q.bid_px_1:.2f}" if q.bid_px_1 is not None else "",
                "bid_qty_1": q.bid_qty_1 if q.bid_qty_1 is not None else "",
                "ask_px_1": f"{q.ask_px_1:.2f}" if q.ask_px_1 is not None else "",
                "ask_qty_1": q.ask_qty_1 if q.ask_qty_1 is not None else "",
                "day_open": "",
                "day_high": "",
                "day_low": "",
                "day_close": "",
                "candle_1m_open": "",
                "candle_1m_high": "",
                "candle_1m_low": "",
                "candle_1m_close": "",
                "candle_1m_vol": "",
                "quality_flags": ";".join(q.quality_flags),
                "collector_sequence_number": q.collector_sequence_number,
                "feed_mode": q.feed_mode,
                "feed_type": q.feed_type,
                "message_id": q.message_id,
            }

            for ohlc_item in q.vendor_ohlc:
                intv = ohlc_item.get("interval")
                if intv == "1d":
                    row["day_open"] = f"{ohlc_item.get('open', 0):.2f}"
                    row["day_high"] = f"{ohlc_item.get('high', 0):.2f}"
                    row["day_low"] = f"{ohlc_item.get('low', 0):.2f}"
                    row["day_close"] = f"{ohlc_item.get('close', 0):.2f}"
                elif intv in ("I1", "1m"):
                    row["candle_1m_open"] = f"{ohlc_item.get('open', 0):.2f}"
                    row["candle_1m_high"] = f"{ohlc_item.get('high', 0):.2f}"
                    row["candle_1m_low"] = f"{ohlc_item.get('low', 0):.2f}"
                    row["candle_1m_close"] = f"{ohlc_item.get('close', 0):.2f}"
                    row["candle_1m_vol"] = ohlc_item.get("volume", 0)

            writer.writerow(row)

    return len(quotes)


def dump_segment_to_console(
    quotes: List[WsQuote],
    limit: int = 20,
    contracts_cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    """
    1. The use of function:
       Prints a clean, formatted terminal table of chronologically sorted quotes with strikes and Greeks.

    2. How does the specific function work:
       - Sorts quotes chronologically.
       - Enriches each quote with symbol, strike, and option type.
       - Formats columns: TIME (IST), SYMBOL, STRIKE, TYPE, LTP, SPOT, OI, VOL, DELTA, IV.
       - Displays top N rows.

    3. Concepts used in the function:
       Console formatting, tabular presentation.

    4. Places where this function is imported and used:
       Called from main() when --to-csv is not specified.

    5. Final output of the function, before and after:
       Before: Quotes in memory. After: Formatted ASCII ladder printed to terminal.
    """
    if contracts_cache is None:
        contracts_cache = load_contracts_cache()

    quotes.sort(key=lambda q: (q.ts_recv or "", q.collector_sequence_number or 0))

    # Pre-scan running spot
    running_spot = ""
    for q in quotes:
        if ("NSE_INDEX" in q.instrument_key or "Nifty 50" in q.instrument_key) and q.ltp > 0:
            running_spot = f"{q.ltp:.2f}"
            break

    display_quotes = quotes[:limit]
    print("=" * 115)
    print(
        f"{'TIME (IST)':<20} {'SYMBOL':<28} {'STRIKE':>8} {'TYPE':<5} {'LTP':>10} {'SPOT':>10} {'OI':>10} {'DELTA':>8} {'IV':>8}"
    )
    print("=" * 115)
    for q in display_quotes:
        if ("NSE_INDEX" in q.instrument_key or "Nifty 50" in q.instrument_key) and q.ltp > 0:
            running_spot = f"{q.ltp:.2f}"

        meta = resolve_contract_metadata(q.instrument_key, contracts_cache)
        ist_time = to_ist_string(q.ts_recv)[11:19]  # HH:MM:SS
        sym = meta["symbol"][:27]
        stk = str(meta["strike_price"]) if meta["strike_price"] else "-"
        opt_type = meta["option_type"]
        delta_str = f"{q.delta_observed:.3f}" if q.delta_observed is not None else "-"
        iv_str = f"{q.iv_observed:.1f}%" if q.iv_observed is not None else "-"
        oi_str = f"{int(q.oi):,}" if q.oi else "-"

        print(
            f"{ist_time:<20} {sym:<28} {stk:>8} {opt_type:<5} {q.ltp:>10.2f} {running_spot:>10} {oi_str:>10} {delta_str:>8} {iv_str:>8}"
        )
    print("=" * 115)
    if len(quotes) > limit:
        print(f"... and {len(quotes) - limit} more quote(s). Use --to-csv <file.csv> to export all.\n")


def main() -> None:
    """
    1. The use of function:
       CLI entrypoint for inspecting raw recorded WebSocket market data segments.

    2. How does the specific function work:
       - Parses command-line arguments (--segment, --date, --to-csv, --limit).
       - Finds target segment files by exact path or latest trade date.
       - Decodes frames, sorts chronologically, and outputs enriched results to console or CSV.

    3. Concepts used in the function:
       CLI tooling, data inspection, batch processing.

    4. Places where this function is imported and used:
       Executed via `python tools/ops/dump_ws_segment.py`.

    5. Final output of the function, before and after:
       Before: Raw binary files. After: Sorted, enriched CSV file or formatted terminal table.
    """
    parser = argparse.ArgumentParser(description="QuantView Raw WebSocket Segment Inspector")
    parser.add_argument("--segment", type=str, default="", help="Path to specific .bin.gz or .bin.partial file")
    parser.add_argument("--date", type=str, default="", help="Trade date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--to-csv", type=str, default="", help="Path to write exported CSV file")
    parser.add_argument("--limit", type=int, default=25, help="Max quotes to display in console (default: 25)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw_dir = PROJECT_ROOT / "Data" / "raw" / "upstox_ws" / "ticks" / f"trade_date={date_str}"

    target_files: List[Path] = []
    if args.segment:
        target_files.append(Path(args.segment))
    elif raw_dir.exists():
        target_files.extend(sorted(raw_dir.glob("*.bin.gz")))
        target_files.extend(sorted(raw_dir.glob("*.bin.partial")))

    if not target_files:
        print(f"No segment files found in {raw_dir}")
        sys.exit(1)

    decoder = WsQuoteDecoder("inspector_tool")
    all_quotes: List[WsQuote] = []
    for fp in target_files:
        try:
            q_list = extract_quotes_from_file(fp, decoder)
            all_quotes.extend(q_list)
        except Exception as ex:
            print(f"Warning: Failed reading {fp.name}: {ex}")

    print(f"\nScanned {len(target_files)} segment file(s). Found {len(all_quotes)} decoded quote(s).")
    cache = load_contracts_cache()

    if args.to_csv:
        out_path = Path(args.to_csv)
        count = dump_segment_to_csv(all_quotes, out_path, contracts_cache=cache)
        print(f"Successfully exported {count} chronologically sorted quote(s) to: {out_path.resolve()}\n")
    else:
        dump_segment_to_console(all_quotes, limit=args.limit, contracts_cache=cache)


if __name__ == "__main__":
    main()
