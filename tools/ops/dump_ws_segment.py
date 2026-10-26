"""
1. What this file does:
   Utility CLI to inspect and export recorded binary Upstox WebSocket segments (.bin.gz or .bin.partial)
   into human-readable CSV or formatted console tables.

2. Overall design:
   Reads raw compressed frames from Data/raw/upstox_ws/ticks/, extracts binary frames using
   unpack_frames_from_bytes, parses protobuf payloads via WsQuoteDecoder, and outputs tabular data
   (LTP, close price, volume, OI, bid/ask depth, Greeks, quality flags) to stdout or CSV.

3. Elements in the file:
   - dump_segment_to_csv(): Unpacks and writes quotes from raw segment files to a CSV file.
   - dump_segment_to_console(): Prints summary table of quotes to terminal.
   - main(): CLI entrypoint parsing arguments (--segment, --date, --to-csv, --limit).

4. Final output of the file:
   - Terminal summary or CSV file containing decoded tick-by-tick market quotes.
"""

import argparse
import csv
from datetime import datetime, timezone
import gzip
import logging
from pathlib import Path
import sys
from typing import List, Optional

# Standard QuantView repository bootstrap
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.collector_ws.decoder import WsQuote, WsQuoteDecoder
from services.collector_ws.framing import unpack_frames_from_bytes

logger = logging.getLogger("quantview.dump_ws")


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
       Called by dump_segment_to_csv() and dump_segment_to_console().

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


def dump_segment_to_csv(quotes: List[WsQuote], output_csv: Path) -> int:
    """
    1. The use of function:
       Exports a list of WsQuote records to a CSV file on disk.

    2. How does the specific function work:
       - Opens output CSV with UTF-8 encoding.
       - Writes canonical header columns.
       - Iterates over quotes writing row values.

    3. Concepts used in the function:
       CSV serialization, data export.

    4. Places where this function is imported and used:
       Called from main() when --to-csv is supplied.

    5. Final output of the function, before and after:
       Before: Quotes in memory. After: Formatted CSV file saved to output_csv.
    """
    fieldnames = [
        "message_id",
        "collector_sequence_number",
        "instrument_key",
        "feed_mode",
        "feed_type",
        "ts_recv",
        "ts_event",
        "ltp",
        "day_open",
        "day_high",
        "day_low",
        "day_close",
        "candle_1m_open",
        "candle_1m_high",
        "candle_1m_low",
        "candle_1m_close",
        "candle_1m_vol",
        "ltq",
        "cp",
        "atp",
        "volume_traded_today",
        "oi",
        "bid_px_1",
        "bid_qty_1",
        "ask_px_1",
        "ask_qty_1",
        "iv_observed",
        "delta_observed",
        "theta_observed",
        "quality_flags",
    ]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for q in quotes:
            row = q.to_dict()
            row["quality_flags"] = ";".join(q.quality_flags)
            for ohlc_item in q.vendor_ohlc:
                intv = ohlc_item.get("interval")
                if intv == "1d":
                    row["day_open"] = ohlc_item.get("open")
                    row["day_high"] = ohlc_item.get("high")
                    row["day_low"] = ohlc_item.get("low")
                    row["day_close"] = ohlc_item.get("close")
                elif intv in ("I1", "1m"):
                    row["candle_1m_open"] = ohlc_item.get("open")
                    row["candle_1m_high"] = ohlc_item.get("high")
                    row["candle_1m_low"] = ohlc_item.get("low")
                    row["candle_1m_close"] = ohlc_item.get("close")
                    row["candle_1m_vol"] = ohlc_item.get("volume", 0)
            writer.writerow(row)
    return len(quotes)


def main() -> None:
    """
    1. The use of function:
       CLI entrypoint for inspecting raw recorded WebSocket market data segments.

    2. How does the specific function work:
       - Parses command-line arguments.
       - Finds target segment files by exact path or latest trade date.
       - Decodes frames and outputs to console or CSV.

    3. Concepts used in the function:
       CLI tooling, data inspection.

    4. Places where this function is imported and used:
       Executed via `python tools/ops/dump_ws_segment.py`.

    5. Final output of the function, before and after:
       Before: Binary data. After: Human-readable view or exported CSV.
    """
    parser = argparse.ArgumentParser(description="QuantView Raw WebSocket Segment Inspector")
    parser.add_argument("--segment", type=str, default="", help="Path to specific .bin.gz or .bin.partial file")
    parser.add_argument("--date", type=str, default="", help="Trade date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--to-csv", type=str, default="", help="Path to write exported CSV file")
    parser.add_argument("--limit", type=int, default=20, help="Max quotes to display in console (default: 20)")
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

    if args.to_csv:
        out_path = Path(args.to_csv)
        count = dump_segment_to_csv(all_quotes, out_path)
        print(f"Successfully exported {count} quote(s) to: {out_path.resolve()}")
    else:
        display_quotes = all_quotes[:args.limit]
        print("=" * 80)
        print(f"{'TIME (UTC)':<24} {'INSTRUMENT':<22} {'LTP':>10} {'CP':>10} {'FLAGS'}")
        print("=" * 80)
        for q in display_quotes:
            flags = ",".join(q.quality_flags[:2])
            print(f"{q.ts_recv:<24} {q.instrument_key:<22} {q.ltp:>10.2f} {q.cp:>10.2f} {flags}")
        print("=" * 80)
        if len(all_quotes) > args.limit:
            print(f"... and {len(all_quotes) - args.limit} more. Use --to-csv <file.csv> to export all.")


if __name__ == "__main__":
    main()
