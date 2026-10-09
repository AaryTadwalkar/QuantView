import os
import pandas as pd
from pathlib import Path
from datetime import datetime

# --- CONFIG ---
BASE_DIR = Path("C:/Algo/Data/live/option_chain/nifty")
REPORT_FILE = Path("C:/Algo/parquet_quality_report.txt")
GAP_THRESHOLD_SECONDS = 180  # 3 minutes

def check_parquet_quality():
    print("🚀 Starting Parquet Quality Audit...")
    parquet_files = list(BASE_DIR.rglob("*.parquet"))
    
    if not parquet_files:
        print("❌ No parquet files found.")
        return

    with open(REPORT_FILE, "w", encoding="utf-8") as report:
        report.write("==================================================\n")
        report.write("      PARQUET OPTION CHAIN QUALITY REPORT         \n")
        report.write(f"      Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        report.write("==================================================\n\n")

        total_rows = 0
        
        for file in sorted(parquet_files):
            try:
                df = pd.read_parquet(file)
                if df.empty:
                    report.write(f"\n[File] {file.name} - ⚠️ EMPTY FILE\n")
                    continue
                
                # 1. Detect Schema
                columns = set(df.columns)
                if 'iv' in columns and 'spot_price' in columns:
                    schema_type = "🟢 NEW SCHEMA (With Greeks)"
                else:
                    schema_type = "🟡 OLD SCHEMA (Standard)"

                # 2. Basic Stats
                row_count = len(df)
                total_rows += row_count
                duplicates = df.duplicated(subset=['timestamp', 'strike', 'type']).sum()
                
                timestamps = pd.Series(df['timestamp'].unique()).sort_values()
                start_time = timestamps.iloc[0].strftime("%H:%M:%S")
                end_time = timestamps.iloc[-1].strftime("%H:%M:%S")
                
                report.write(f"\n[File] {file.name} | Expiry: {file.parent.name}\n")
                report.write(f"  - Schema     : {schema_type}\n")
                report.write(f"  - Window     : {start_time} to {end_time} ({len(timestamps)} snapshots)\n")
                report.write(f"  - Total Rows : {row_count} rows\n")
                
                if duplicates > 0:
                    report.write(f"  - ⚠️ WARNING  : {duplicates} duplicate rows detected.\n")
                
                # 3. Gap Analysis
                if len(timestamps) > 1:
                    gaps = timestamps.diff().dt.total_seconds()
                    large_gaps = gaps[gaps > GAP_THRESHOLD_SECONDS]
                    
                    if not large_gaps.empty:
                        report.write(f"  - ❌ GAPS FOUND: {len(large_gaps)} stream disconnect(s) > 3 mins.\n")
                        for idx, gap_sec in large_gaps.items():
                            down_start = timestamps.iloc[idx-1].strftime("%H:%M:%S")
                            down_end = timestamps.iloc[idx].strftime("%H:%M:%S")
                            report.write(f"      • Offline: {down_start} -> {down_end} ({int(gap_sec//60)} mins)\n")
                    else:
                        report.write("  - ✅ Continuous Stream (No gaps > 3 mins)\n")

            except Exception as e:
                report.write(f"\n[File] {file.name} - ❌ CORRUPTED: {e}\n")

        report.write("\n==================================================\n")
        report.write(f"✅ Audit Complete. Grand Total Rows: {total_rows}\n")
        
    print(f"🎉 Done! Processed {total_rows} rows. Report saved to {REPORT_FILE.name}")

if __name__ == "__main__":
    check_parquet_quality()