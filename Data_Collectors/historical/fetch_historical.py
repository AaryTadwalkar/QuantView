#fetched candle data of all time frames 1m/3m/5m/15/1hr/4hr/1d for nifty index from 2020-01-01 to 2026-01-23
# using upstox api
#and saved in csv file in Data/historical/candles/index/nifty/ folder

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
DATA_COLLECTORS_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if DATA_COLLECTORS_DIR not in sys.path:
    sys.path.insert(0, DATA_COLLECTORS_DIR)

import requests
import pandas as pd
import os

from Data_Collectors.settings import (
    ACCESS_TOKEN,
    NIFTY_INSTRUMENT_KEY,
    FROM_DATE,
    TO_DATE,
    TIMEFRAMES
)

BASE_URL = "https://api.upstox.com/v3/historical-candle"

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "open_interest"
]


from datetime import datetime, timedelta

def fetch_and_save(unit, interval):
    print(f"Fetching {interval} {unit} data...")

    # Decide chunk size based on unit
    if unit == "minutes":
        chunk_days = 30
    elif unit == "hours":
        chunk_days = 90
    else:  # days, weeks, months
        chunk_days = None

    all_rows = []

    end = datetime.fromisoformat(TO_DATE)
    start = datetime.fromisoformat(FROM_DATE)

    while end > start:
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

        response = requests.get(url, headers=HEADERS)

        if response.status_code == 400:
            print(f"⚠️ Skipping invalid range: {chunk_start.date()} → {end.date()}")
            break

        response.raise_for_status()

        candles = response.json()["data"]["candles"]
        if candles:
            all_rows.extend(candles)

        end = chunk_start - timedelta(days=1)

        if not chunk_days:
            break

    if not all_rows:
        print("❌ No data collected")
        return

    df = pd.DataFrame(
        all_rows,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "open_interest",
        ],
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.drop_duplicates(subset="timestamp", inplace=True)
    df.sort_values("timestamp", inplace=True)

    folder = f"Data/historical/candles/index/nifty/{interval}{unit[0]}"
    os.makedirs(folder, exist_ok=True)

    df.to_csv(f"{folder}/nifty.csv", index=False)
    print(f"✅ Saved {len(df)} rows")



if __name__ == "__main__":
    for tf in TIMEFRAMES:
        fetch_and_save(tf["unit"], tf["interval"])
