"""
merge_extensions.py
===================
WHAT THIS FILE DOES:
    Merges the newly fetched 'nifty_extension.csv' into the original 'nifty.csv'
    for all timeframes. It appends the data, drops duplicates, and sorts.

OVERALL DESIGN:
    Loops over TIMEFRAMES, finds 'nifty.csv' and 'nifty_extension.csv'.
    If both exist, concatenates them and overwrites 'nifty.csv'.
    It does not delete 'nifty_extension.csv' but it can be manually deleted.
"""

import sys
import pandas as pd
from pathlib import Path

DATA_COLLECTORS_DIR = Path(__file__).resolve().parent.parent
if str(DATA_COLLECTORS_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_COLLECTORS_DIR))

try:
    from settings import TIMEFRAMES
except ImportError:
    raise RuntimeError("Cannot import settings.py from Data_Collectors/settings.py")

ROOT_DIR = DATA_COLLECTORS_DIR.parent
HIST_BASE = ROOT_DIR / "Data" / "historical" / "candles" / "index" / "nifty"

def merge_extensions():
    print("=" * 55)
    print("🚀 Merging Historical Extensions")
    print("=" * 55)
    
    for tf_info in TIMEFRAMES:
        folder = tf_info["folder"]
        main_csv = HIST_BASE / folder / "nifty.csv"
        ext_csv = HIST_BASE / folder / "nifty_extension.csv"
        
        if not main_csv.exists() or not ext_csv.exists():
            print(f"  {folder:5s} → SKIPPED (missing main or extension CSV)")
            continue
            
        print(f"  {folder:5s} → Merging...", end=" ")
        try:
            df_main = pd.read_csv(main_csv, low_memory=False)
            df_ext = pd.read_csv(ext_csv, low_memory=False)
            
            df_combined = pd.concat([df_main, df_ext], ignore_index=True)
            
            # Convert to datetime to properly sort and drop duplicates
            df_combined["timestamp"] = pd.to_datetime(df_combined["timestamp"], utc=False, errors="coerce")
            df_combined.dropna(subset=["timestamp"], inplace=True)
            df_combined.drop_duplicates(subset="timestamp", keep="last", inplace=True)
            df_combined.sort_values("timestamp", inplace=True)
            
            # Save back to main_csv
            df_combined.to_csv(main_csv, index=False)
            print(f"DONE. Total rows: {len(df_combined):,}")
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    merge_extensions()
