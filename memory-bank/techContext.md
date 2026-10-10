# Tech Context

## Runtime
- Python 3.11 (venv at `C:\Algo\Options\venv\`)
- OS: Windows 11

## Installed packages (requirements.txt)
- pandas 3.0.6
- numpy 2.4.6
- requests 2.34.2
- python-dateutil 2.9.0
- tzdata 2026.5
- certifi, charset-normalizer, idna, urllib3, six

## Missing from requirements (needed for planned work)
- pyarrow — Parquet read/write (needed for G6)
- duckdb — analytical queries
- psycopg2 or asyncpg — PostgreSQL
- pytest — testing (G7)
- import-linter — dependency boundary enforcement
- fastapi or equivalent — API layer

## Upstox integration
- API version: v3 (historical candle), v3 (market data feed WebSocket)
- Auth: Bearer token from `UPSTOX_ACCESS_TOKEN` in `.env`
- Rate limiting: handled with `time.sleep(0.5)` and 3-retry on 429
- Token type: Short-lived OAuth access token (expires daily) — no refresh mechanism
- Instrument key: `NSE_INDEX|Nifty 50`
- Historical candle endpoint: `https://api.upstox.com/v3/historical-candle/{key}/{unit}/{interval}/{to}/{from}`
- Expired contract candle endpoint: documented at Upstox, requires Plus plan — NOT yet verified

## Data storage structure
```
C:\Algo\Options\
  Data/
    historical/candles/index/nifty/{1m,3m,5m,15m,1h,4h,1d}/nifty.csv
    live/candles/index/nifty/1m/nifty_YYYY-MM-DD.csv
    live/option_chain/nifty/{expiry_date}/{trade_date}/snapshots/HH-MM-SS.csv
```

## Environment
- Credentials: `.env` file at project root (gitignored)
- Keys: UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_ACCESS_TOKEN

## Development constraints
- No git commits or pushes (workspace rule)
- Data/ folder is gitignored
- DOCS/ is untracked (never committed — should be committed)
- No CI configured yet

## Key script entry points
- `Data_Collectors/historical/fetch_historical.py` — one-time bulk historical fetch
- `Data_Collectors/historical/fetch_historical_extension.py` — incremental update
- `Data_Collectors/historical/merge_extensions.py` — merge extension into main CSV
- `Data_Collectors/data_status.py` — generate data audit report → DOCS/data_status.md
- `Data_Collectors/data_format/data_quality_checker.py` — option chain quality audit

## Scripts with broken paths (must fix)
- `Data_Collectors/data_format/data_gap_checker.py` — hardcodes C:\Algo\Data\...
- `Data_Collectors/historical/data_gap_filler.py` — hardcodes C:\Algo\storage\...
- `Data_Collectors/data_format/migrate_options.py` — hardcodes storage/live/... and storage/master_db/...
- `Data_Collectors/data_format/parquet_quality_checker.py` — hardcodes C:/Algo/Data/...

## Timezone handling
- Candle timestamps: stored with `+05:30` suffix (pandas-aware IST)
- Option chain timestamps: sub-second precision, NO timezone suffix — ambiguous (presumed IST)
- Exchange timezone: Asia/Kolkata (IST, UTC+05:30, no DST)
