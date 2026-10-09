import os
import glob
import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime
# python -m data_collectors.data_format.migrate_options
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "storage/live/option_chain/nifty"
VAULT_DIR = PROJECT_ROOT / "storage/master_db/option_chain/nifty"

# ==========================================
# CONFIGURATION: DATE RANGE FILTER
# ==========================================
# Set to 'None' to process everything, or use "YYYY-MM-DD"
# For daily EOD runs, you can set both to today's date.
START_DATE = "2026-06-7"  
END_DATE = "2026-06-21"    

def migrate_to_parquet(start_date_str=None, end_date_str=None):
    print("🚀 Starting EOD Data Migration to Vault...")
    
    # Parse dates if provided
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else None
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else None

    snapshot_folders = glob.glob(f"{RAW_DIR}/**/snapshots", recursive=True)
    if not RAW_DIR.exists():
        print(u"❌ Error: The directory does not exist ->", RAW_DIR)
        return
    for folder in snapshot_folders:
        folder_path = Path(folder)
        trade_date_str = folder_path.parent.name 
        expiry_date_str = folder_path.parent.parent.name 
        
        # --- 1. DATE FILTERING ---
        try:
            current_trade_date = datetime.strptime(trade_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue # Skip if folder name isn't a valid date format
            
        if start_dt and current_trade_date < start_dt:
            continue
        if end_dt and current_trade_date > end_dt:
            continue

        # Target goes to the VAULT
        target_dir = VAULT_DIR / expiry_date_str
        os.makedirs(target_dir, exist_ok=True)
        target_parquet_file = target_dir / f"{trade_date_str}.parquet"
        
        # --- 2. SKIP IF ALREADY MIGRATED ---
        if target_parquet_file.exists():
            print(f"⏭️ Skipping {trade_date_str}: Parquet already exists in Vault.")
            continue
        
        csv_files = glob.glob(f"{folder}/*.csv")
        if not csv_files: continue
            
        print(f"📦 Compressing {len(csv_files)} files for Trade Date: {trade_date_str}")
        
        df_list = [pd.read_csv(csv) for csv in csv_files]
        if df_list:
            merged_df = pd.concat(df_list, ignore_index=True)
            merged_df['timestamp'] = pd.to_datetime(merged_df['timestamp'])
            merged_df = merged_df.sort_values(by=['timestamp', 'strike', 'type'])
            
            merged_df.to_parquet(target_parquet_file, engine='pyarrow', index=False)
            print(f"  ✅ Saved to Vault: {target_parquet_file.name}")
            
            # CLEANUP: Commented out so you keep your raw CSVs
            # shutil.rmtree(folder_path.parent)
            # print(f"  🧹 Cleaned up raw staging folder.")

if __name__ == "__main__":
    migrate_to_parquet(START_DATE, END_DATE)