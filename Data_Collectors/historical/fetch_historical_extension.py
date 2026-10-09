"""
fetch_historical_extension.py
==============================
WHAT THIS FILE DOES:
    Fetches Nifty 50 index candlestick data from the Upstox API v3 for all
    timeframes defined in the project, starting from the day AFTER the last
    timestamp already present in the existing historical CSV, up to today.
    Saves the new data into a SEPARATE CSV file (nifty_extension.csv) inside
    the same timeframe folder — the original nifty.csv is NEVER modified.

OVERALL DESIGN:
    - Reads the last timestamp from the existing historical CSV for each TF.
    - Computes start_date = last_date + 1 business day.
    - Fetches in chunks (30-day for minute TFs, 90-day for hour TFs, full
      range for daily TFs) using the Upstox v3 API.
    - De-duplicates rows (against the existing file's last date and within itself).
    - Saves the extension data as  Data/historical/candles/index/nifty/{tf}/nifty_extension.csv

ELEMENTS IN THIS FILE:
    Classes  → None (procedural style matching the existing codebase)
    Functions → get_last_date(), fetch_extension(), main()
    Constants → BASE_URL, HEADERS, COLUMNS, TIMEFRAMES_CONFIG, HIST_BASE

FINAL OUTPUT:
    For each timeframe:
      Data/historical/candles/index/nifty/{tf}/nifty_extension.csv
    containing all candles from (historical end + 1 day) through today,
    sorted ascending, deduplicated.
"""

import os
import sys
import time
import requests
import pandas as pd

from pathlib import Path
from datetime import datetime, timedelta, date

# ── Path bootstrap: allow `from settings import ...` when run from anywhere ──
DATA_COLLECTORS_DIR = Path(__file__).resolve().parent.parent
if str(DATA_COLLECTORS_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_COLLECTORS_DIR))

try:
    from settings import ACCESS_TOKEN, NIFTY_INSTRUMENT_KEY, TIMEFRAMES
except ImportError:
    raise RuntimeError(
        "Cannot import settings.py — ensure ACCESS_TOKEN and NIFTY_INSTRUMENT_KEY "
        "are defined in Data_Collectors/settings.py"
    )

# ─────────────────────────────── CONSTANTS ────────────────────────────────────
BASE_URL   = "https://api.upstox.com/v3/historical-candle"
HEADERS    = {
    "Accept":        "application/json",
    "Content-Type":  "application/json",
    "Authorization": f"Bearer {ACCESS_TOKEN}",
}
COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "open_interest"]

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
HIST_BASE  = ROOT_DIR / "Data" / "historical" / "candles" / "index" / "nifty"

TIMEFRAMES_CONFIG = TIMEFRAMES


# ──────────────────────────────────────────────────────────────────────────────
def get_last_date(tf_folder: str) -> date | None:
    """
    USE:
        Reads the last (latest) timestamp from the existing nifty.csv for a
        given timeframe, returning its calendar date.

    HOW:
        Reads only the 'timestamp' column of the existing CSV for speed.
        Parses as datetime (timezone-aware), returns .date() of the max value.
        If the file doesn't exist, returns None.

    CONCEPTS:
        pandas read_csv usecols for minimal IO; pd.to_datetime with UTC-aware
        output to handle '+05:30' suffix produced by Upstox API.

    IMPORTS / USED BY:
        Called by fetch_extension() to determine the start of the gap.

    OUTPUT:
        date object (the last calendar date present in existing data) or None.

    Before → existing nifty.csv ends at "2026-01-23 15:29:00+05:30"
    After  → returns date(2026, 1, 23)
    """
    path = HIST_BASE / tf_folder / "nifty.csv"
    if not path.exists():
        print(f"    ⚠️  {path} not found — will fetch full history.")
        return None
    try:
        df = pd.read_csv(path, usecols=["timestamp"], low_memory=False)
        ts = pd.to_datetime(df["timestamp"], utc=False, errors="coerce").dropna()
        if ts.empty:
            return None
        return ts.max().date()
    except Exception as e:
        print(f"    ❌ Error reading {path}: {e}")
        return None


def fetch_extension(unit: str, interval: int, folder: str) -> None:
    """
    USE:
        Fetches all missing Nifty index candles for a given timeframe from
        the day after the last existing timestamp up to today, and saves them
        as nifty_extension.csv (never modifying the original nifty.csv).

    HOW:
        1. get_last_date() to find where historical data ends.
        2. start_date = last_date + 1 day (business day next).
        3. end_date = today.
        4. Chunk the range (30-day chunks for minutes, 90-day for hours,
           single request for days) and call the Upstox v3 API.
        5. Collect all candle rows, build DataFrame, deduplicate on timestamp,
           sort ascending, save as nifty_extension.csv.

    CONCEPTS:
        Chunked reverse iteration (end → start) to match Upstox API convention.
        Rate-limit handling: sleeps 1s between requests; retries on 429.
        Deduplication: removes any rows already present in the last 2 days of
        historical data (overlapping chunk boundary handling).

    IMPORTS / USED BY:
        Called from main() for each entry in TIMEFRAMES_CONFIG.

    OUTPUT:
        Data/historical/candles/index/nifty/{folder}/nifty_extension.csv
        Before → file may not exist; After → CSV with new candles from gap period.
    """
    print(f"\n{'─' * 55}")
    print(f"  📥  Fetching extension: {interval}{unit[0]}  (folder: {folder})")

    last_date  = get_last_date(folder)
    today      = datetime.now().date()

    if last_date is None:
        start_date = date(2020, 1, 1)        # fallback: fetch from 2020
    else:
        start_date = last_date + timedelta(days=1)

    if start_date > today:
        print(f"    ✅ Already up-to-date (last: {last_date}). Nothing to fetch.")
        return

    print(f"    Existing data ends : {last_date}")
    print(f"    Fetching from      : {start_date}  →  {today}")

    # Determine chunk size
    if unit == "minutes":
        chunk_days = 30
    elif unit == "hours":
        chunk_days = 90
    else:
        chunk_days = None       # single API call for daily

    all_rows: list = []
    end   = datetime.combine(today, datetime.min.time())
    start = datetime.combine(start_date, datetime.min.time())

    while end >= start:
        if chunk_days:
            chunk_start = max(start, end - timedelta(days=chunk_days))
        else:
            chunk_start = start

        url = (
            f"{BASE_URL}/"
            f"{NIFTY_INSTRUMENT_KEY}/"
            f"{unit}/"
            f"{interval}/"
            f"{end.date()}/"
            f"{chunk_start.date()}"
        )

        retries = 0
        while retries < 3:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=30)
                if resp.status_code == 429:
                    print("    ⚠️  Rate limit — sleeping 5s...")
                    time.sleep(5)
                    retries += 1
                    continue
                if resp.status_code == 400:
                    print(f"    ⚠️  Bad range {chunk_start.date()} → {end.date()}, skipping.")
                    break
                resp.raise_for_status()
                candles = resp.json().get("data", {}).get("candles", [])
                if candles:
                    all_rows.extend(candles)
                    print(f"    + {len(candles):>5} candles  [{chunk_start.date()} → {end.date()}]")
                break
            except requests.exceptions.RequestException as e:
                print(f"    ❌ Request error: {e}. Retry {retries+1}/3...")
                retries += 1
                time.sleep(2)

        time.sleep(0.5)          # polite pause between chunks

        if not chunk_days:
            break
        end = chunk_start - timedelta(days=1)
        if end < start:
            break

    if not all_rows:
        print(f"    ❌  No data returned for {folder}. Extension file not created.")
        return

    # Build DataFrame
    df = pd.DataFrame(all_rows, columns=COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df.dropna(subset=["timestamp"], inplace=True)
    df.drop_duplicates(subset="timestamp", inplace=True)

    # Strip any rows that duplicate the last 2 days of historical data
    if last_date:
        overlap_cutoff = pd.Timestamp(last_date - timedelta(days=2), tz="Asia/Kolkata")
        df = df[df["timestamp"] > overlap_cutoff]

    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    if df.empty:
        print(f"    ✅  All fetched rows are already in historical data. Nothing new.")
        return

    # Save
    out_dir  = HIST_BASE / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "nifty_extension.csv"
    df.to_csv(out_path, index=False)
    print(f"    ✅  Saved {len(df):,} new rows → {out_path}")


def main() -> None:
    """
    USE:
        Entry-point. Iterates all TIMEFRAMES_CONFIG entries and calls
        fetch_extension() for each one.

    HOW:
        Sequentially processes each TF to avoid hammering the API.
        Prints a final summary after all TFs are processed.

    CONCEPTS:
        Token from settings.py (not hardcoded). Respects Upstox v3 API structure.

    OUTPUT:
        Console progress; one nifty_extension.csv per timeframe in their
        respective folders under Data/historical/candles/index/nifty/.
    """
    print("=" * 55)
    print("🚀 Nifty Historical Extension Fetcher")
    print(f"   Instrument : {NIFTY_INSTRUMENT_KEY}")
    print(f"   Base URL   : {BASE_URL}")
    print(f"   Run time   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    results = []
    for cfg in TIMEFRAMES_CONFIG:
        try:
            fetch_extension(cfg["unit"], cfg["interval"], cfg["folder"])
            out = HIST_BASE / cfg["folder"] / "nifty_extension.csv"
            if out.exists():
                rows = len(pd.read_csv(out, usecols=["timestamp"]))
                results.append((cfg["folder"], rows, str(out)))
            else:
                results.append((cfg["folder"], 0, "NOT CREATED"))
        except Exception as e:
            print(f"    ❌ Unhandled error for {cfg['folder']}: {e}")
            results.append((cfg["folder"], -1, str(e)))

    print("\n" + "=" * 55)
    print("📋 FINAL SUMMARY")
    print("=" * 55)
    for folder, rows, path in results:
        status = f"{rows:,} rows" if rows > 0 else ("SKIPPED / UP-TO-DATE" if rows == 0 else "ERROR")
        print(f"  {folder:5s} → {status}")
    print("\nDone! Original nifty.csv files were NOT modified.")


if __name__ == "__main__":
    main()
