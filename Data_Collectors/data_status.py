"""
data_status.py
==============
Detailed Data Auditor for Nifty 50 Options & Candlesticks.
Analyzes Candlestick data and Options data independently based on
strict intervals and expiry cycles.
"""

import os
import glob
from pathlib import Path
from datetime import datetime, timedelta, time as dtime, date
from collections import defaultdict
import pandas as pd
import sys

# Insert Data_Collectors to sys.path to import settings
ROOT = Path(__file__).resolve().parent
DATA_COLLECTORS_DIR = ROOT / "Data_Collectors"
if str(DATA_COLLECTORS_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_COLLECTORS_DIR))

try:
    from settings import TIMEFRAMES
except ImportError:
    TIMEFRAMES = [
        {"unit": "minutes", "interval": 1, "folder": "1m"},
        {"unit": "minutes", "interval": 3, "folder": "3m"},
        {"unit": "minutes", "interval": 5, "folder": "5m"},
        {"unit": "minutes", "interval": 15, "folder": "15m"},
        {"unit": "hours",   "interval": 1, "folder": "1h"},
        {"unit": "hours",   "interval": 4, "folder": "4h"},
        {"unit": "days",    "interval": 1, "folder": "1d"},
    ]

CANDLE_HIST_BASE = ROOT / "Data" / "historical" / "candles" / "index" / "nifty"
CANDLE_LIVE_BASE = ROOT / "Data" / "live" / "candles" / "index" / "nifty"
OC_BASE          = ROOT / "Data" / "live" / "option_chain" / "nifty"
REPORT_PATH      = ROOT / "DOCS" / "data_status.md"

def get_expected_times(tf_folder: str):
    """Generates expected timestamps for a trading day (09:15 to 15:30) for a given timeframe."""
    if tf_folder == "1m": return pd.date_range("09:15", "15:29", freq="1min").time
    if tf_folder == "3m": return pd.date_range("09:15", "15:27", freq="3min").time
    if tf_folder == "5m": return pd.date_range("09:15", "15:25", freq="5min").time
    if tf_folder == "15m": return pd.date_range("09:15", "15:15", freq="15min").time
    if tf_folder == "1h": return pd.date_range("09:15", "15:15", freq="1h").time
    if tf_folder == "4h": return [dtime(9, 15), dtime(13, 15)]
    return [dtime(0, 0)] # For 1d, usually just date

class Auditor:
    def __init__(self):
        # Candlestick data: TF -> Date -> Set of times
        self.candle_data = defaultdict(lambda: defaultdict(set))
        self.candle_totals = defaultdict(int)
        self.candle_start = {}
        self.candle_end = {}
        
        # Options data
        self.oc_snapshots = defaultdict(lambda: defaultdict(list)) # Expiry -> Date -> List of Time
        self.oc_schema_changes = []
        self.total_oc_snapshots = 0

    def load_candles(self):
        print("Loading Candlestick data for all timeframes...")
        for tf_info in TIMEFRAMES:
            tf = tf_info["folder"]
            # Read Historical
            hist_csv = CANDLE_HIST_BASE / tf / "nifty.csv"
            dfs = []
            if hist_csv.exists():
                dfs.append(pd.read_csv(hist_csv, usecols=["timestamp"], low_memory=False))
            
            # Read Live
            live_dir = CANDLE_LIVE_BASE / tf
            if live_dir.exists():
                for csv in live_dir.glob("*.csv"):
                    dfs.append(pd.read_csv(csv, usecols=["timestamp"], low_memory=False))
                    
            if not dfs:
                continue
                
            df = pd.concat(dfs, ignore_index=True)
            df["timestamp"] = df["timestamp"].astype(str).str.replace(r"\+05:30", "", regex=True)
            ts = pd.to_datetime(df["timestamp"], utc=False, errors="coerce").dropna()
            
            self.candle_totals[tf] = len(ts)
            if not ts.empty:
                self.candle_start[tf] = ts.min()
                self.candle_end[tf] = ts.max()
                
            for t in ts:
                self.candle_data[tf][t.date()].add(t.time())

    def load_option_chains(self):
        print("Loading Option Chain snapshots...")
        pattern = str(OC_BASE / "*" / "*" / "snapshots" / "*.csv")
        files = glob.glob(pattern)
        
        parsed = []
        for f in files:
            p = Path(f)
            parts = p.parts
            try:
                snap_idx = [i for i, x in enumerate(parts) if x == "snapshots"][-1]
                tdate_str = parts[snap_idx - 1]
                exp_str = parts[snap_idx - 2]
                time_str = p.stem
                
                tdate = date.fromisoformat(tdate_str)
                exp = date.fromisoformat(exp_str)
                time_obj = datetime.strptime(time_str, "%H-%M-%S").time()
                parsed.append((exp, tdate, time_obj, p))
            except Exception:
                pass
                
        parsed.sort(key=lambda x: (x[1], x[2])) # Sort chronologically by trade date and time
        self.total_oc_snapshots = len(parsed)
        
        prev_cols = None
        version = 0
        
        for i, (exp, tdate, time_obj, path) in enumerate(parsed):
            self.oc_snapshots[exp][tdate].append(time_obj)
            
            # Schema scan
            if i % 10000 == 0:
                print(f"  ... schema scan {i}/{len(parsed)}")
                
            try:
                df = pd.read_csv(path, nrows=0)
                cols = tuple(df.columns.tolist())
                
                # Ignore empty or corrupted snapshots (e.g., just 'Unnamed: 0')
                if 'strike' not in cols or 'type' not in cols:
                    continue
                    
                if cols != prev_cols:
                    if prev_cols is not None: # Don't increment version for the very first file, call it Version 1
                        version += 1
                    else:
                        version = 1
                        
                    self.oc_schema_changes.append({
                        "version": version,
                        "date": datetime.combine(tdate, time_obj),
                        "columns": cols,
                        "changed_from": prev_cols
                    })
                    prev_cols = cols
            except Exception:
                pass
        
        # Sort the times for each date
        for exp in self.oc_snapshots:
            for tdate in self.oc_snapshots[exp]:
                self.oc_snapshots[exp][tdate].sort()

    def build_report(self):
        lines = []
        lines.append("# Detailed Data Schema & Status Report")
        lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # ======================================================================
        # CANDLESTICK SUMMARY
        # ======================================================================
        lines.append("## 1. Candlestick Data Summary")
        lines.append("| Timeframe | Total Rows | Start Date | End Date |")
        lines.append("|---|---|---|---|")
        for tf_info in TIMEFRAMES:
            tf = tf_info["folder"]
            count = self.candle_totals.get(tf, 0)
            start = self.candle_start.get(tf, "N/A")
            end = self.candle_end.get(tf, "N/A")
            lines.append(f"| {tf} | {count:,} | {start} | {end} |")
        lines.append("")
        
        lines.append("### Candlestick Missing Row Analysis (Per Timeframe)")
        for tf_info in TIMEFRAMES:
            tf = tf_info["folder"]
            if tf not in self.candle_data:
                continue
            
            expected_times = set(get_expected_times(tf))
            days_missing_data = 0
            lines.append(f"#### Timeframe: {tf}")
            
            for d in sorted(self.candle_data[tf].keys()):
                actual_times = self.candle_data[tf][d]
                if tf == "1d":
                    if not actual_times:
                        lines.append(f"- {d}: Missing daily candle")
                        days_missing_data += 1
                else:
                    missing = sorted(expected_times - actual_times)
                    if missing:
                        days_missing_data += 1
                        missing_strs = [t.strftime("%H:%M") for t in missing]
                        # Group consecutive
                        grouped = []
                        if missing_strs:
                            start_m = missing_strs[0]
                            prev_dt = datetime.strptime(start_m, "%H:%M")
                            start_dt = start_m
                            for i in range(1, len(missing_strs)):
                                curr_dt = datetime.strptime(missing_strs[i], "%H:%M")
                                expected_gap = timedelta(minutes=int(tf.replace('m', '').replace('h', '60')) if 'm' in tf or 'h' in tf else 0)
                                if (curr_dt - prev_dt) > expected_gap:
                                    grouped.append(f"{start_dt} to {prev_dt.strftime('%H:%M')}")
                                    start_dt = missing_strs[i]
                                prev_dt = curr_dt
                            grouped.append(f"{start_dt} to {prev_dt.strftime('%H:%M')}")
                        lines.append(f"- **{d}**: Missing {len(missing)} candles ({', '.join(grouped[:5])}{'...' if len(grouped)>5 else ''})")
            
            if days_missing_data == 0:
                lines.append("✅ No missing candles detected within active trading days.")
            lines.append("")
            
        # ======================================================================
        # OPTIONS DATA SUMMARY
        # ======================================================================
        lines.append("## 2. Options Data Summary")
        if not self.oc_snapshots:
            lines.append("No options data found.")
        else:
            all_tdates = set()
            for exp in self.oc_snapshots:
                all_tdates.update(self.oc_snapshots[exp].keys())
                
            min_tdate = min(all_tdates)
            max_tdate = max(all_tdates)
            
            lines.append(f"- **Total Options Snapshots**: {self.total_oc_snapshots:,}")
            lines.append(f"- **Data Collection Start Date**: {min_tdate}")
            lines.append(f"- **Data Collection End Date**: {max_tdate}")
            lines.append(f"- **Total Expiries Tracked**: {len(self.oc_snapshots)}")
            lines.append(f"- **Total Unique Trading Days**: {len(all_tdates)}")
            lines.append("")
            
            lines.append("### Option Chain Schema Changes")
            for sc in self.oc_schema_changes:
                lines.append(f"- **v{sc['version']} ({sc['date']})**: {sc['columns']}")
            lines.append("")
            
            lines.append("### Expiry Date Validation")
            for exp in sorted(self.oc_snapshots.keys()):
                # Nifty expiry currently is Tuesday (weekday == 1)
                if exp.weekday() == 1:
                    status = "✅ Valid (Tuesday)"
                elif exp.weekday() == 0:
                    status = "⚠️ Monday (Holiday shifted?)"
                elif exp.weekday() == 2:
                    status = "⚠️ Wednesday (Holiday shifted?)"
                elif exp.weekday() == 3:
                    status = "⚠️ Thursday (Old Nifty Expiry?)"
                else:
                    status = f"❌ {exp.strftime('%A')} (Unusual)"
                lines.append(f"- {exp}: {status}")
            lines.append("")
            
            # Options Missing Data logic
            lines.append("### Options Data Missing Analysis (30s intervals from 09:15 to 15:30)")
            sorted_expiries = sorted(self.oc_snapshots.keys())
            
            for i, exp in enumerate(sorted_expiries):
                lines.append(f"#### Expiry: {exp}")
                
                # Determine expected business days for this expiry cycle
                if i == 0:
                    cycle_start = min_tdate
                else:
                    cycle_start = sorted_expiries[i-1] + timedelta(days=1)
                    
                cycle_start = max(cycle_start, min_tdate)
                
                if cycle_start > exp:
                    lines.append(f"- No expected days (Cycle start {cycle_start} is after expiry {exp})")
                    continue
                    
                expected_bdays = pd.bdate_range(cycle_start, exp).date
                actual_tdates = set(self.oc_snapshots[exp].keys())
                
                missing_days = sorted(set(expected_bdays) - actual_tdates)
                lines.append(f"- **Total Expected Days**: {len(expected_bdays)}")
                lines.append(f"- **Total Collected Days**: {len(actual_tdates)}")
                lines.append(f"- **Total Missing Days**: {len(missing_days)}")
                
                if missing_days:
                    lines.append(f"- **Missing Dates**: {', '.join(str(d) for d in missing_days)}")
                
                # Now check intra-day snapshots for days we DID collect
                lines.append("- **Snapshot Anomalies for Collected Days (Expected: Every 30s):**")
                anomalies_found = False
                
                for d in sorted(actual_tdates):
                    times = self.oc_snapshots[exp][d]
                    if not times:
                        continue
                        
                    daily_anomalies = []
                    
                    # 1. Check start time
                    if times[0] > dtime(9, 15, 45): # Tolerance of 45s
                        daily_anomalies.append(f"Late start at {times[0].strftime('%H:%M:%S')}")
                        
                    # 2. Check gaps > 45 seconds (expected 30s)
                    for j in range(1, len(times)):
                        dt1 = datetime.combine(d, times[j-1])
                        dt2 = datetime.combine(d, times[j])
                        diff_sec = (dt2 - dt1).total_seconds()
                        if diff_sec > 45: # Threshold for a missed 30s snapshot
                            daily_anomalies.append(f"Gap from {times[j-1].strftime('%H:%M:%S')} to {times[j].strftime('%H:%M:%S')} ({int(diff_sec)}s)")
                            
                    # 3. Check end time
                    if times[-1] < dtime(15, 29, 15):
                        daily_anomalies.append(f"Early end at {times[-1].strftime('%H:%M:%S')}")
                        
                    if daily_anomalies:
                        anomalies_found = True
                        lines.append(f"  - {d}: {len(daily_anomalies)} anomalies")
                        # Print max first 5 to not flood
                        for a in daily_anomalies[:5]:
                            lines.append(f"    - {a}")
                        if len(daily_anomalies) > 5:
                            lines.append(f"    - ... and {len(daily_anomalies)-5} more gaps")
                            
                if not anomalies_found and len(actual_tdates) > 0:
                    lines.append("  - ✅ All collected days have perfect 30-second snapshot intervals!")
                lines.append("")
                
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"Report saved to {REPORT_PATH}")

if __name__ == '__main__':
    auditor = Auditor()
    auditor.load_candles()
    auditor.load_option_chains()
    auditor.build_report()
