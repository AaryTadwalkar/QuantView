import pandas as pd
import requests
import time
import sys
from datetime import timedelta, datetime
from pathlib import Path
from settings import ACCESS_TOKEN
#  python -m data_collectors.historical.data_gap_filler
FILE_PATH = Path(r"C:\Algo\storage\historical\candles\index\nifty\1m\nifty.csv")
BASE_URL = "https://api.upstox.com/v2/historical-candle"
INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"
HEADERS = {"Accept": "application/json", "Authorization": f"Bearer {ACCESS_TOKEN}"}

def fill_gaps():
    print("="*50)
    print("🚀 NIFTY MASTER GAP FILLER ENGINE (Strict Filter)")
    print("="*50)
    
    try:
        with open(FILE_PATH, 'a'):
            pass
    except PermissionError:
        print(f"\n❌ FATAL ERROR: Cannot access '{FILE_PATH.name}'. It is open in another program.")
        sys.exit(1)

    print(f"⏳ Loading '{FILE_PATH.name}'...")
    df = pd.read_csv(FILE_PATH, low_memory=False)
    original_row_count = len(df)
    
    df = df[df['timestamp'] != 'timestamp'].copy()
    df['timestamp'] = df['timestamp'].astype(str).str.replace("+05:30", "", regex=False)
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp'])

    # start_date = df['timestamp'].min().date()
    # end_date = df['timestamp'].max().date()
    start_date = datetime(2026, 6, 1).date()  # You can adjust this as needed
    end_date = datetime.now().date() - timedelta(days=1)  # Up to
    expected_days = pd.date_range(start=start_date, end=end_date, freq="B").date
    present_dates = df['timestamp'].dt.date.unique()
    missing_days = sorted(list(set(expected_days) - set(present_dates)))

    if not missing_days:
        print("✅ No missing days found. Your data is 100% complete!")
        return

    print(f"📊 Found {len(missing_days)} missing days to verify.\n")

    all_new_rows = []

    for target_date in missing_days:
        print(f"🔄 Checking {target_date}...")
        to_date = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")
        from_date = target_date.strftime("%Y-%m-%d")
        
        url = f"{BASE_URL}/{INSTRUMENT_KEY}/1minute/{to_date}/{from_date}"
        response = requests.get(url, headers=HEADERS)
        
        if response.status_code == 200:
            candles = response.json().get("data", {}).get("candles", [])
            valid_candles_for_target = 0
            
            if candles:
                for c in candles:
                    dt_obj = datetime.strptime(c[0], "%Y-%m-%dT%H:%M:%S%z")
                    
                    # --- STRICT DATE FILTER ---
                    # Only accept the candle if it exactly matches the missing target day
                    if dt_obj.date() == target_date:
                        all_new_rows.append({
                            "timestamp": dt_obj.strftime("%Y-%m-%d %H:%M:%S"),
                            "open": float(c[1]), "high": float(c[2]), "low": float(c[3]),
                            "close": float(c[4]), "volume": int(c[5]), "open_interest": int(c[6])
                        })
                        valid_candles_for_target += 1
                
                if valid_candles_for_target > 0:
                    print(f"  ✅ Added {valid_candles_for_target} valid candles.")
                else:
                    print(f"  - No valid candles for this specific date (Confirmed Market Holiday).")
            else:
                print(f"  - No data returned.")
                
        elif response.status_code == 429:
            print("  ⚠️ Rate limit hit. Sleeping 3s...")
            time.sleep(3)
        else:
            print(f"  ❌ Error: {response.status_code}")
        
        time.sleep(1)

    if all_new_rows:
        new_df = pd.DataFrame(all_new_rows)
        new_df['timestamp'] = pd.to_datetime(new_df['timestamp'])
        
        print(f"\n🧩 Injecting {len(new_df)} verified rows into existing data...")
        
        final_df = pd.concat([df, new_df], ignore_index=True)
        final_df = final_df.drop_duplicates(subset=['timestamp'], keep='last')
        final_df = final_df.sort_values(by='timestamp')
        
        final_df.to_csv(FILE_PATH, index=False)
        
        new_row_count = len(final_df)
        added_rows = new_row_count - original_row_count
        
        print("\n" + "="*50)
        print(f"🎉 BACKFILL COMPLETE! {FILE_PATH.name} updated.")
        print("="*50)
        print(f"📈 Old Row Count: {original_row_count:,}")
        print(f"📈 New Row Count: {new_row_count:,}")
        print(f"✅ Net Added Rows: {added_rows:,} new candles injected.")
    else:
        print("\n✅ Verification complete. All missing days were confirmed market holidays. CSV is pristine.")

if __name__ == "__main__":
    fill_gaps()