import os
import glob
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime

# --- CONFIGURATION (Adjust paths as needed) ---
PROJECT_ROOT = Path("C:/Algo")  # Change to your active directory root path
OPTION_CHAIN_DIR = PROJECT_ROOT / "Data/live/option_chain/nifty"
CANDLES_DIR = PROJECT_ROOT / "Data/live/candles/index/nifty/1m"

REPORT_FILE = PROJECT_ROOT / "data_quality_report_comprehensive.txt"

# Expected market parameters (NSE India trading hours)
MARKET_START = "09:15:00"
MARKET_END = "15:30:00"
EXPECTED_CANDLES_PER_DAY = 376  # 1-minute intervals from 09:15 to 15:30 inclusive
SNAPSHOT_GAP_THRESHOLD_MINUTES = 3

def write_to_report(text, file_handle):
    """Prints to console and saves to report file simultaneously."""
    print(text)
    file_handle.write(text + "\n")

def detect_schema(columns):
    """Dynamically categorizes data schema patterns across old and new formats."""
    cols = set(columns)
    if 'open' in cols and 'close' in cols:
        return 'Candle 1m Data'
    if 'ce_oi' in cols or 'pe_oi' in cols:
        return 'Pivoted Old Schema (Wide)'
    if 'type' in cols:
        if 'spot_price' in cols:
            return 'New Schema (Long with Greeks)'
        else:
            return 'Old Schema (Long Standard)'
    return 'Unknown/Corrupted Schema'

def analyze_candles(directory, report):
    write_to_report("\n" + "="*70, report)
    write_to_report("SECTION 1: 1-MINUTE INDEX CANDLES QUALITY AUDIT", report)
    write_to_report("="*70, report)
    
    file_pattern = os.path.join(directory, "nifty_*.csv")
    files = glob.glob(file_pattern)
    
    if not files:
        write_to_report(f"❌ No candle files found in target folder: {directory}", report)
        return []

    present_dates = []
    total_missing_rows_in_files = 0
    
    write_to_report(f"Found {len(files)} total candle CSV files.", report)
    
    for file_path in sorted(files):
        filename = os.path.basename(file_path)
        write_to_report(f"\n[File] {filename}", report)
        
        try:
            df = pd.read_csv(file_path)
            if df.empty:
                write_to_report(f"  - ❌ CRITICAL: File is empty. Missing Rows: {EXPECTED_CANDLES_PER_DAY}/{EXPECTED_CANDLES_PER_DAY}", report)
                total_missing_rows_in_files += EXPECTED_CANDLES_PER_DAY
                continue
                
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            file_date = df['timestamp'].min().date()
            present_dates.append(file_date)
            
            # 1. Date/Time Boundaries
            min_time = df['timestamp'].min()
            max_time = df['timestamp'].max()
            write_to_report(f"  - Range: {min_time} to {max_time} | Total Rows Present: {len(df)}", report)
            
            # 2. Duplicate Entries Check
            duplicates = df.duplicated(subset=['timestamp']).sum()
            if duplicates > 0:
                write_to_report(f"  - ⚠️ Duplicate Rows: {duplicates} duplicate minute entries found.", report)
                
            # 3. Micro Data Gap / Missing Rows Check per File
            expected_range = pd.date_range(
                start=f"{file_date} {MARKET_START}", 
                end=f"{file_date} {MARKET_END}", 
                freq="1min"
            )
            # If the log terminates early (e.g., incomplete active day logging), truncate reference range
            if max_time < expected_range[-1]:
                expected_range = expected_range[expected_range <= max_time]
                
            missing_timestamps = expected_range.difference(df['timestamp'])
            missing_rows_count = len(missing_timestamps)
            total_missing_rows_in_files += missing_rows_count
            
            if missing_rows_count > 0:
                write_to_report(f"  - ❌ Missing Rows in this file: {missing_rows_count} missing minutes.", report)
                # Group consecutive missing blocks cleanly
                missing_series = pd.Series(missing_timestamps)
                gaps = missing_series.diff() != pd.Timedelta(minutes=1)
                gap_groups = gaps.cumsum()
                for _, group in missing_series.groupby(gap_groups):
                    if len(group) == 1:
                        write_to_report(f"      • Drop at: {group.iloc[0]}", report)
                    else:
                        write_to_report(f"      • Drop block: {group.iloc[0]} to {group.iloc[-1]} ({len(group)} mins)", report)
            else:
                write_to_report("  - ✅ Row Consistency: 100% complete (0 missing rows for logged window).", report)
                
        except Exception as e:
            write_to_report(f"  - ❌ Parsing error: {e}", report)

    # 4. Global Missing Full Dates Check
    if present_dates:
        present_dates = sorted(list(set(present_dates)))
        start_date, end_date = present_dates[0], present_dates[-1]
        
        full_business_range = pd.date_range(start=start_date, end=end_date, freq="B").date
        missing_days = [d for d in full_business_range if d not in present_dates]
        
        missing_days_rows = len(missing_days) * EXPECTED_CANDLES_PER_DAY
        grand_total_missing_rows = total_missing_rows_in_files + missing_days_rows
        
        write_to_report("\n" + "-"*50, report)
        write_to_report(f"CANDLE GLOBAL SUMMARY REPORT:", report)
        write_to_report(f"  • Absolute Dataset Range : {start_date} to {end_date}", report)
        write_to_report(f"  • Missing Full Dates ({len(missing_days)} days): {missing_days if missing_days else 'None'}", report)
        write_to_report(f"  • Missing Rows inside existing files   : {total_missing_rows_in_files}", report)
        write_to_report(f"  • Missing Rows from unrecorded full days: {missing_days_rows}", report)
        write_to_report(f"  • GRAND TOTAL MISSING CANDLE ROWS      : {grand_total_missing_rows}", report)
        write_to_report("-"*50, report)

    return present_dates

def analyze_option_chains(base_directory, report):
    write_to_report("\n" + "="*70, report)
    write_to_report("SECTION 2: OPTION CHAIN SNAPSHOTS QUALITY AUDIT", report)
    write_to_report("="*70, report)
    
    file_pattern = os.path.join(base_directory, "**", "snapshots", "*.csv")
    files = glob.glob(file_pattern, recursive=True)
    
    if not files:
        write_to_report(f"❌ No option chain snapshot files found under {base_directory}", report)
        return

    # Group snapshots by Expiry and Trade Date to inspect cross-contamination
    snapshots_by_day = {}
    trade_date_to_expiries = {}
    
    for file_path in files:
        path_obj = Path(file_path)
        trade_date_str = path_obj.parent.parent.name 
        expiry_date_str = path_obj.parent.parent.parent.name
        
        day_key = (expiry_date_str, trade_date_str)
        if day_key not in snapshots_by_day:
            snapshots_by_day[day_key] = []
        snapshots_by_day[day_key].append(path_obj)
        
        if trade_date_str not in trade_date_to_expiries:
            trade_date_to_expiries[trade_date_str] = set()
        trade_date_to_expiries[trade_date_str].add(expiry_date_str)

    # 1. Structural Routing Overlap Check
    write_to_report("Auditing Cross-Expiry Routing Integrity...", report)
    overlap_found = False
    for t_date, expiries in sorted(trade_date_to_expiries.items()):
        if len(expiries) > 1:
            overlap_found = True
            write_to_report(f"  - ⚠️ CONFIGURATION OVERLAP for Trade Date [{t_date}]: Data spread across multiple folders: {list(expiries)}", report)
    if not overlap_found:
        write_to_report("  - ✅ Expiry isolation clean. No structural folder leakage found.", report)

    all_trade_dates = []
    
    # 2. Process Day Groups
    for (expiry, trade_date), path_list in sorted(snapshots_by_day.items()):
        write_to_report(f"\nGroup: Expiry [{expiry}] | Trade Date [{trade_date}]", report)
        write_to_report(f"  - Total snapshot files found: {len(path_list)}", report)
        
        day_timestamps = []
        schema_distribution = {}
        total_corrupt_files = 0
        file_row_counts = {}
        file_duplicate_counts = {}
        
        try:
            all_trade_dates.append(datetime.strptime(trade_date, "%Y-%m-%d").date())
        except:
            pass

        # Phase A: Map individual files and identify row structures
        for file_path in sorted(path_list):
            try:
                df = pd.read_csv(file_path)
                if df.empty:
                    total_corrupt_files += 1
                    file_row_counts[file_path.name] = 0
                    continue
                
                current_schema = detect_schema(df.columns)
                schema_distribution[current_schema] = schema_distribution.get(current_schema, 0) + 1
                
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                day_timestamps.extend(list(df['timestamp'].unique()))
                
                # Check duplicates based on layout type
                dup_subset = ['timestamp', 'strike'] if current_schema == 'Pivoted Old Schema (Wide)' else ['timestamp', 'strike', 'type']
                file_duplicate_counts[file_path.name] = df.duplicated(subset=dup_subset).sum()
                file_row_counts[file_path.name] = len(df)
                
            except Exception:
                total_corrupt_files += 1
                file_row_counts[file_path.name] = 0

        # Phase B: Calculate Missing Rows per Snapshot File
        # A file has missing rows if its row count is lower than the healthy max matrix size for that day's asset chain
        max_rows_in_snapshot = max(file_row_counts.values()) if file_row_counts else 0
        write_to_report(f"  - Auto-Detected Schema Layout: {schema_distribution}", report)
        write_to_report(f"  - Target Complete Matrix Size: {max_rows_in_snapshot} rows per snapshot", report)
        
        missing_rows_in_group_files = 0
        for fname, count in sorted(file_row_counts.items()):
            missing_in_file = max_rows_in_snapshot - count
            missing_rows_in_group_files += missing_in_file
            dup_msg = f" [⚠️ {file_duplicate_counts[fname]} duplicates]" if file_duplicate_counts.get(fname, 0) > 0 else ""
            if missing_in_file > 0 or file_duplicate_counts.get(fname, 0) > 0:
                write_to_report(f"    • Snapshot File [{fname}]: Present Rows: {count} | Missing Rows: {missing_in_file}{dup_msg}", report)

        write_to_report(f"  - Cumulative Missing Contract Rows across files: {missing_rows_in_group_files}", report)
        if total_corrupt_files > 0:
            write_to_report(f"  - ❌ Unreadable/Corrupted Snapshot Files: {total_corrupt_files} files broken", report)

        # Phase C: Timeline Stream Analysis
        if day_timestamps:
            day_timestamps = pd.to_datetime(list(set(day_timestamps))).sort_values()
            write_to_report(f"  - Time Coverage Window: {day_timestamps[0]} to {day_timestamps[-1]}", report)
            
            if len(day_timestamps) > 1:
                time_series = pd.Series(day_timestamps)
                time_diffs = time_series.diff().dropna()
                large_gaps = time_diffs[time_diffs > pd.Timedelta(minutes=SNAPSHOT_GAP_THRESHOLD_MINUTES)]
                if not large_gaps.empty:
                    write_to_report(f"  - ❌ STREAM DISCONNECTS DETECTED: {len(large_gaps)} instance(s) (> {SNAPSHOT_GAP_THRESHOLD_MINUTES} mins).", report)
                    for idx, gap in large_gaps.items():
                        write_to_report(f"      • Offline Block: {time_series.iloc[idx - 1]} to {time_series.iloc[idx]} (Downtime: {gap})", report)
                else:
                    write_to_report("  - ✅ Recording Stream: Continuous. No gaps exceeding threshold found.", report)

    # 3. Global Missing Full Dates Check for Option Chains
    if all_trade_dates:
        all_trade_dates = sorted(list(set(all_trade_dates)))
        start_date, end_date = all_trade_dates[0], all_trade_dates[-1]
        
        full_business_range = pd.date_range(start=start_date, end=end_date, freq="B").date
        missing_days = [d for d in full_business_range if d not in all_trade_dates]
        
        write_to_report("\n" + "-"*50, report)
        write_to_report(f"OPTION CHAIN GLOBAL SUMMARY REPORT:", report)
        write_to_report(f"  • Absolute Trading Activity Range: {start_date} to {end_date}", report)
        write_to_report(f"  • Missing Full Trading Dates     : {missing_days if missing_days else 'None'}", report)
        write_to_report("-"*50, report)


if __name__ == "__main__":
    print("🚀 Running Data Quality Audit Engine...")
    with open(REPORT_FILE, "w", encoding="utf-8") as report:
        report.write("================================================================================\n")
        report.write(f"           COMPREHENSIVE MARKET DATA INTEGRITY AUDIT REPORT                     \n")
        report.write(f"           Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}        \n")
        report.write("================================================================================\n")
        
        analyze_candles(CANDLES_DIR, report)
        analyze_option_chains(OPTION_CHAIN_DIR, report)
        
    print(f"\n[SUCCESS] Quality Audit Complete! Detailed metrics outputted to:\n➡️ {REPORT_FILE}")