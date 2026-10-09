import os
from dotenv import load_dotenv

# Load .env from the root folder (C:\Algo\Options\.env)
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
load_dotenv(os.path.join(ROOT_DIR, '.env'))

ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
if not ACCESS_TOKEN:
    print("WARNING: UPSTOX_ACCESS_TOKEN missing in .env")

NIFTY_INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"

FROM_DATE = "2026-01-23"
TO_DATE   = "2026-09-10"

# Historical Candle Data configurations
TIMEFRAMES = [
    {"unit": "minutes", "interval": 1, "folder": "1m"},
    {"unit": "minutes", "interval": 3, "folder": "3m"},
    {"unit": "minutes", "interval": 5, "folder": "5m"},
    {"unit": "minutes", "interval": 15, "folder": "15m"},
    {"unit": "hours",   "interval": 1, "folder": "1h"},
    {"unit": "hours",   "interval": 4, "folder": "4h"},
    {"unit": "days",    "interval": 1, "folder": "1d"},
]
