
import os
import time
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from dotenv import load_dotenv

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BASE_URL = "https://api.upstox.com/v2"
UNDERLYING_KEY = "NSE_INDEX|Nifty 50"

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "UPSTOX_ACCESS_TOKEN not found. "
        "Check the project-root .env file."
    )

# Existing expired NIFTY option expiry
EXPIRY_DATE = "2025-04-24"

# Fetch exactly ONE calendar day.
# This should be a trading day within the available history.
DATA_DATE = "2025-04-24"

OUTPUT_DIR = PROJECT_ROOT / "Data" / "historical" / "options"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CSV_PATH = OUTPUT_DIR / (
    f"nifty_options_1m_{EXPIRY_DATE}_{DATA_DATE}.csv"
)

FAILURES_PATH = OUTPUT_DIR / (
    f"failures_{EXPIRY_DATE}_{DATA_DATE}.csv"
)

COLUMNS = [
    "timestamp",
    "instrument_key",
    "trading_symbol",
    "expiry",
    "strike",
    "option_type",
    "lot_size",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "source",
    "interval",
]

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
})


# --------------------------------------------------
# API HELPERS
# --------------------------------------------------

def get_json(url, params=None):
    response = SESSION.get(
        url,
        params=params,
        timeout=45,
    )

    if not response.ok:
        print(f"HTTP status: {response.status_code}")

        try:
            print("Upstox response:", response.json())
        except ValueError:
            print("Upstox response:", response.text[:1000])

        response.raise_for_status()

    payload = response.json()

    if payload.get("status") != "success":
        raise RuntimeError(f"Upstox API error: {payload}")

    return payload


def check_authentication():
    response = SESSION.get(
        f"{BASE_URL}/user/profile",
        timeout=20,
    )

    print("Profile status:", response.status_code)

    if not response.ok:
        try:
            print("Authentication error:", response.json())
        except ValueError:
            print(response.text[:1000])

        response.raise_for_status()

    print("Authentication succeeded.")


# --------------------------------------------------
# GET EXPIRED OPTION CONTRACTS
# --------------------------------------------------

def get_expired_contracts(expiry_date):
    url = f"{BASE_URL}/expired-instruments/option/contract"

    payload = get_json(
        url,
        params={
            "instrument_key": UNDERLYING_KEY,
            "expiry_date": expiry_date,
        },
    )

    contracts = payload.get("data", [])

    print(
        f"Contracts returned for {expiry_date}: "
        f"{len(contracts)}"
    )

    return contracts


# --------------------------------------------------
# GET ONE DAY OF 1-MINUTE CANDLES
# --------------------------------------------------

def get_contract_candles(contract, data_date):
    instrument_key = contract["instrument_key"]
    encoded_key = quote(instrument_key, safe="")

    # Same from_date and to_date = one calendar day.
    url = (
        f"{BASE_URL}/expired-instruments/historical-candle/"
        f"{encoded_key}/1minute/{data_date}/{data_date}"
    )

    payload = get_json(url)

    candles = payload.get("data", {}).get("candles", [])
    rows = []

    for candle in candles:
        if len(candle) != 7:
            raise ValueError(
                f"Unexpected candle format for "
                f"{instrument_key}: {candle}"
            )

        timestamp, open_, high, low, close, volume, oi = candle

        rows.append({
            "timestamp": timestamp,
            "instrument_key": instrument_key,
            "trading_symbol": contract.get("trading_symbol"),
            "expiry": contract.get("expiry"),
            "strike": contract.get("strike_price"),
            "option_type": contract.get("instrument_type"),
            "lot_size": contract.get("lot_size"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "oi": oi,
            "source": "upstox_expired_historical_candle",
            "interval": "1minute",
        })

    return rows


# --------------------------------------------------
# VALIDATE AND SAVE CSV
# --------------------------------------------------

def save_and_validate(all_rows):
    df = pd.DataFrame(all_rows, columns=COLUMNS)

    if not df.empty:
        # Convert timestamps to India Standard Time.
        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            utc=True,
        ).dt.tz_convert("Asia/Kolkata")

        df = df.sort_values(
            ["instrument_key", "timestamp"]
        ).reset_index(drop=True)

    # Write CSV even if no candles were returned.
    # This makes the output path and schema predictable.
    df.to_csv(CSV_PATH, index=False)

    print("\n" + "=" * 55)
    print("DATA VALIDATION SUMMARY")
    print("=" * 55)

    print(f"CSV saved to: {CSV_PATH}")
    print(f"Total rows: {len(df):,}")

    if df.empty:
        print("No candles returned for this date.")
        print("Check API coverage and the requested date.")
        return

    print(
        "Unique contracts:",
        df["instrument_key"].nunique(),
    )

    duplicates = df.duplicated(
        ["instrument_key", "timestamp"]
    ).sum()

    invalid_ohlc = (
        (df["high"] < df["low"])
        | (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["low"] > df["open"])
        | (df["low"] > df["close"])
    ).sum()

    null_timestamps = df["timestamp"].isna().sum()

    print(f"Duplicate contract/timestamps: {duplicates}")
    print(f"Invalid OHLC rows: {invalid_ohlc}")
    print(f"Missing timestamps: {null_timestamps}")
    print(f"First timestamp: {df['timestamp'].min()}")
    print(f"Last timestamp: {df['timestamp'].max()}")

    print("\nCandles per contract — first 20:")

    counts = (
        df.groupby(
            ["trading_symbol", "strike", "option_type"],
            dropna=False,
        )
        .size()
        .rename("candle_count")
        .reset_index()
    )

    print(counts.head(20).to_string(index=False))

    print("\nOHLC preview:")
    print(
        df[
            [
                "timestamp",
                "trading_symbol",
                "strike",
                "option_type",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "oi",
            ]
        ]
        .head(15)
        .to_string(index=False)
    )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    print(f"Expiry date: {EXPIRY_DATE}")
    print(f"Data date:   {DATA_DATE}")
    print("Interval:    1 minute")
    print("Output:      CSV")

    check_authentication()

    contracts = get_expired_contracts(EXPIRY_DATE)

    all_rows = []
    failures = []

    for i, contract in enumerate(contracts, start=1):
        key = contract.get("instrument_key")
        symbol = contract.get("trading_symbol", key)

        try:
            rows = get_contract_candles(
                contract,
                DATA_DATE,
            )

            all_rows.extend(rows)

            print(
                f"[{i}/{len(contracts)}] "
                f"{symbol}: {len(rows)} candles"
            )

        except Exception as exc:
            failures.append({
                "instrument_key": key,
                "trading_symbol": symbol,
                "error": str(exc),
            })

            print(f"FAILED {symbol}: {exc}")

        # Conservative pacing.
        time.sleep(0.15)

    save_and_validate(all_rows)

    if failures:
        pd.DataFrame(failures).to_csv(
            FAILURES_PATH,
            index=False,
        )

        print(f"\nFailed requests saved to: {FAILURES_PATH}")
        print(f"Failed contract requests: {len(failures)}")
    else:
        print("\nAll contract requests completed without errors.")

    print("\nNext step: inspect the CSV before using Parquet.")


if __name__ == "__main__":
    main()
