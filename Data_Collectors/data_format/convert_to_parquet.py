import pandas as pd
from pathlib import Path
# python -m data_collectors.data_format.convert_to_parquet
csv_path = Path(r"C:\Algo\storage\historical\candles\index\nifty\1m\nifty.csv")
parquet_path = Path(r"C:\Algo\storage\master_db\candles\nifty\1m\nifty_master.parquet")

print("⏳ Loading master CSV...")
df = pd.read_csv(csv_path, low_memory=False)


# Optimize data types to save RAM
df['timestamp'] = pd.to_datetime(df['timestamp'])

# 1. Downcast prices to floats
for col in ['open', 'high', 'low', 'close']:
    df[col] = pd.to_numeric(df[col], downcast='float')

# 2. Downcast volume and OI to integers (using the exact column names)
df['volume'] = pd.to_numeric(df['volume'], downcast='integer')
df['open_interest'] = pd.to_numeric(df['open_interest'], downcast='integer')

print("💾 Saving as Parquet...")
df.to_parquet(parquet_path, engine='pyarrow', index=False)
print(f"✅ Done! Master Parquet created successfully.")