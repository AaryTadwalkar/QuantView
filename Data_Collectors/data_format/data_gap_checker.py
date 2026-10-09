import pandas as pd
from datetime import datetime

# --- CONFIG ---
FILE_PATH = r"C:\Algo\Data\historical\candles\index\nifty\1m\nifty.csv"
REPORT_PATH = r"C:\Algo\nifty_master_gaps.txt"

MARKET_START = "09:15:00"
MARKET_END = "15:30:00"

print("⏳ Loading master nifty.csv (this may take a moment for 4 years of data)...")
df = pd.read_csv(FILE_PATH)

# Clean up the timezone offset (+05:30) so pandas can parse it uniformly
df['timestamp'] = df['timestamp'].str.replace("+05:30", "", regex=False)
df['timestamp'] = pd.to_datetime(df['timestamp'])

start_date = df['timestamp'].min().date()
end_date = df['timestamp'].max().date()

print(f"📅 Data bounds detected: {start_date} to {end_date}")

# Create an index of ALL valid trading days (Monday - Friday)
expected_days = pd.date_range(start=start_date, end=end_date, freq="B")
present_dates = pd.to_datetime(df['timestamp'].dt.date.unique())

missing_full_days = expected_days.difference(present_dates)

with open(REPORT_PATH, "w", encoding="utf-8") as report:
    report.write(f"MASTER NIFTY.CSV GAP REPORT\n")
    report.write(f"Range: {start_date} to {end_date}\n")
    report.write("="*50 + "\n\n")
    
    report.write(f"❌ MISSING FULL TRADING DAYS: {len(missing_full_days)}\n")
    for d in missing_full_days:
        report.write(f"   - {d.date()}\n")
        
    report.write("\n" + "="*50 + "\n")
    report.write("❌ INTRA-DAY MISSING MINUTES (Incomplete Days)\n")
    
    # Check intra-day gaps for days that DO exist
    total_missing_minutes = 0
    for day in present_dates:
        day_df = df[df['timestamp'].dt.date == day.date()]
        
        expected_minutes = pd.date_range(
            start=f"{day.date()} {MARKET_START}", 
            end=f"{day.date()} {MARKET_END}", 
            freq="1min"
        )
        
        missing_mins = expected_minutes.difference(day_df['timestamp'])
        
        if len(missing_mins) > 0:
            total_missing_minutes += len(missing_mins)
            report.write(f"\n[{day.date()}] Missing {len(missing_mins)} minutes:\n")
            # Print first few gaps so file isn't millions of lines long
            report.write(f"   - {list(missing_mins.time[:5])} ...\n")

    report.write("\n" + "="*50 + "\n")
    report.write(f"GRAND TOTAL MISSING MINUTES: {total_missing_minutes}\n")

print(f"✅ Scan complete. Report saved to: {REPORT_PATH}")