# Live option chain data collector for Nifty 50 using Upstox API
# Saves snapshots every 30 seconds during market hours if there's a meaningful change
# Data is saved in Data/live/option_chain/nifty/{expiry_date}/{trade_date}/snapshots/
# Each snapshot is a CSV file with 2 rows per strike: one for CE, one for PE
# Includes comprehensive Greeks data (IV, Delta, Gamma, Theta, Vega)
# To run: python -m market_intelligence.data_collectors.live.live_option_chain

import requests
import pandas as pd
import time
from datetime import datetime, time as dtime
from pathlib import Path
from settings import ACCESS_TOKEN

print(f"ACCESS_TOKEN USED: {ACCESS_TOKEN}")

# ===============================
# PROJECT ROOT
# ===============================
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# ===============================
# UPSTOX CONFIG
# ===============================
OPTION_CHAIN_URL = "https://api.upstox.com/v2/option/chain"
OPTION_GREEKS_URL = "https://api.upstox.com/v3/market-quote/option-greek"
UNDERLYING_KEY = "NSE_INDEX|Nifty 50"
EXPIRY_DATE = "2026-10-13"  # Update this weekly

HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

# ===============================
# MARKET HOURS
# ===============================
def is_market_open(now=None):
    if now is None:
        now = datetime.now()
    return dtime(9, 15) <= now.time() <= dtime(15, 30)

# ===============================
# SAVE PATH
# ===============================
TRADE_DATE = datetime.now().strftime("%Y-%m-%d")

SAVE_DIR = (
    PROJECT_ROOT /
    "Data/live/option_chain/nifty" /
    EXPIRY_DATE /
    TRADE_DATE /
    "snapshots"
)

SAVE_DIR.mkdir(parents=True, exist_ok=True)
print("📂 Saving to:", SAVE_DIR)

# ===============================
# SANITY FILTER
# ===============================
class OptionChainSanityFilter:
    def __init__(self):
        self.prev_state = None
        self.prev_minute = None

    def should_store(self, df, spot):
        if df.empty:
            return False

        now = datetime.now()
        minute = now.replace(second=0, microsecond=0)

        ce_oi = df[df["type"] == "CE"]["oi"].sum()
        pe_oi = df[df["type"] == "PE"]["oi"].sum()
        volume = df["volume"].sum()

        state = (round(spot, 2), ce_oi, pe_oi, volume)

        if self.prev_state is None or minute != self.prev_minute:
            self.prev_state = state
            self.prev_minute = minute
            return True

        if state != self.prev_state:
            self.prev_state = state
            return True

        return False

# ===============================
# FETCH OPTION CHAIN
# ===============================
def fetch_option_chain():
    """Fetch basic option chain data"""
    try:
        r = requests.get(
            OPTION_CHAIN_URL,
            headers=HEADERS,
            params={"instrument_key": UNDERLYING_KEY, "expiry_date": EXPIRY_DATE},
            timeout=10
        )
        
        print(f"📡 Option Chain API Status: {r.status_code}")
        
        if r.status_code != 200:
            print(f"❌ API Error Response: {r.text}")
            return []
            
        response = r.json()
        
        if response.get("status") != "success":
            print(f"❌ API returned non-success status: {response.get('status')}")
            print(f"   Message: {response.get('message', 'No message')}")
            return []
            
        data = response.get("data", [])
        
        if not data:
            print(f"⚠️  API returned empty data array")
            print(f"   Full response: {response}")
            print(f"   Try changing EXPIRY_DATE to next Thursday")
            return []
            
        print(f"✅ Fetched {len(data)} strikes")
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected error in fetch_option_chain: {e}")
        import traceback
        traceback.print_exc()
        return []

# ===============================
# ===============================
# FETCH GREEKS FOR INSTRUMENTS
# ===============================
def fetch_greeks(instrument_keys):
    """Fetch Greeks data for multiple instruments (max 50 at a time)"""
    if not instrument_keys:
        return {}
    
    # Split into batches of 50
    batches = [instrument_keys[i:i+50] for i in range(0, len(instrument_keys), 50)]
    all_greeks = {}
    
    for batch_idx, batch in enumerate(batches):
        keys_param = ",".join(batch)
        try:
            r = requests.get(
                OPTION_GREEKS_URL,
                headers=HEADERS,
                params={"instrument_key": keys_param},
                timeout=10
            )
            
            if r.status_code != 200:
                print(f"⚠️  Greeks API batch {batch_idx+1} error: {r.status_code}")
                continue
                
            response = r.json()
            
            if response.get("status") == "success":
                data = response.get("data", {})
                
                # --- THE FIX ---
                # Re-key the dictionary using 'instrument_token' so it matches 
                # the Option Chain instrument_key
                for symbol_key, metrics in data.items():
                    inst_token = metrics.get("instrument_token", symbol_key)
                    all_greeks[inst_token] = metrics
                    
            else:
                print(f"⚠️  Greeks API batch {batch_idx+1} non-success: {response.get('status')}")
                
        except Exception as e:
            print(f"⚠️  Error fetching Greeks for batch {batch_idx+1}: {e}")
            continue
    
    return all_greeks

# ===============================
# PARSE OPTION CHAIN WITH GREEKS
# ===============================
def fetch_chain_df():
    """
    Fetch and parse complete option chain with Greeks
    Returns: DataFrame with 2 rows per strike (CE and PE)
    """
    # Get basic option chain
    payload = fetch_option_chain()
    
    if not payload:
        return pd.DataFrame(), None
    
    spot_price = payload[0].get("underlying_spot_price")
    print(f"💹 Spot Price: {spot_price}")
    
    # Collect all instrument keys for Greeks
    instrument_keys = []
    strike_data = {}
    
    for strike_info in payload:
        strike = strike_info.get("strike_price")
        
        call_options = strike_info.get("call_options", {})
        put_options = strike_info.get("put_options", {})
        
        strike_data[strike] = {
            "strike": strike,
            "call_data": call_options,
            "put_data": put_options
        }
        
        # Collect instrument keys
        ce_key = call_options.get("instrument_key")
        pe_key = put_options.get("instrument_key")
        
        if ce_key:
            instrument_keys.append(ce_key)
        if pe_key:
            instrument_keys.append(pe_key)
    
    # Fetch Greeks for all instruments
    print(f"📊 Fetching Greeks for {len(instrument_keys)} instruments...")
    greeks_data = fetch_greeks(instrument_keys)
    print(f"✅ Received Greeks data for {len(greeks_data)} instruments")
    
    # Build dataframe with 2 rows per strike
    rows = []
    
    for strike, data in sorted(strike_data.items()):
        # === CALL OPTION ROW ===
        ce_market = data["call_data"].get("market_data", {})
        ce_key = data["call_data"].get("instrument_key", "")
        ce_greeks = greeks_data.get(ce_key, {})
        
        if ce_market or ce_greeks:  # Only add if we have data
            ce_row = {
                "strike": strike,
                "type": "CE",
                "oi": ce_market.get("oi") or 0,
                "volume": ce_market.get("volume") or 0,
                "ltp": ce_market.get("ltp") or ce_greeks.get("last_price") or 0,
                "bid": ce_market.get("bid_price") or 0,
                "ask": ce_market.get("ask_price") or 0,
                "bid_qty": ce_market.get("bid_qty") or 0,
                "ask_qty": ce_market.get("ask_qty") or 0,
                "chng": ce_market.get("net_change") or 0,
                "chng_oi": (ce_market.get("oi_day_high") or 0) - (ce_market.get("oi_day_low") or 0),
                
                # Greeks
                "iv": ce_greeks.get("iv") or 0,
                "delta": ce_greeks.get("delta") or 0,
                "gamma": ce_greeks.get("gamma") or 0,
                "theta": ce_greeks.get("theta") or 0,
                "vega": ce_greeks.get("vega") or 0,
            }
            rows.append(ce_row)
        
        # === PUT OPTION ROW ===
        pe_market = data["put_data"].get("market_data", {})
        pe_key = data["put_data"].get("instrument_key", "")
        pe_greeks = greeks_data.get(pe_key, {})
        
        if pe_market or pe_greeks:  # Only add if we have data
            pe_row = {
                "strike": strike,
                "type": "PE",
                "oi": pe_market.get("oi") or 0,
                "volume": pe_market.get("volume") or 0,
                "ltp": pe_market.get("ltp") or pe_greeks.get("last_price") or 0,
                "bid": pe_market.get("bid_price") or 0,
                "ask": pe_market.get("ask_price") or 0,
                "bid_qty": pe_market.get("bid_qty") or 0,
                "ask_qty": pe_market.get("ask_qty") or 0,
                "chng": pe_market.get("net_change") or 0,
                "chng_oi": (pe_market.get("oi_day_high") or 0) - (pe_market.get("oi_day_low") or 0),
                
                # Greeks
                "iv": pe_greeks.get("iv") or 0,
                "delta": pe_greeks.get("delta") or 0,
                "gamma": pe_greeks.get("gamma") or 0,
                "theta": pe_greeks.get("theta") or 0,
                "vega": pe_greeks.get("vega") or 0,
            }
            rows.append(pe_row)
    
    if not rows:
        return pd.DataFrame(), spot_price
    
    df = pd.DataFrame(rows)
    
    return df, spot_price


# ===============================
# SAVE SNAPSHOT
# ===============================
def save_snapshot(df, spot_price):
    """Save snapshot with timestamp and spot price"""
    now = datetime.now()
    df = df.copy()
    
    # Insert metadata columns
    df.insert(0, "timestamp", now)
    df.insert(1, "spot_price", spot_price)
    
    path = SAVE_DIR / f"{now.strftime('%H-%M-%S')}.csv"
    df.to_csv(path, index=False)
    
    ce_count = len(df[df["type"] == "CE"])
    pe_count = len(df[df["type"] == "PE"])
    print(f"✅ Saved snapshot → {path.name}")
    print(f"   Spot: {spot_price} | Strikes: {ce_count} CE, {pe_count} PE")

# ===============================
# MAIN LOOP
# ===============================
if __name__ == "__main__":
    print("🟢 Live option chain logger started")
    print("📊 Features: Full option chain + Greeks (IV, Delta, Gamma, Theta, Vega)")
    print("💾 Format: 2 rows per strike (CE + PE separate)")
    print(f"📅 Expiry: {EXPIRY_DATE}")
    print(f"🔑 Token: {ACCESS_TOKEN[:20]}...{ACCESS_TOKEN[-10:]}")
    
    filter = OptionChainSanityFilter()

    while True:
        try:
            if not is_market_open():
                print("⏸  Market closed - waiting...")
                time.sleep(30)
                continue

            print(f"\n🔄 Fetching data at {datetime.now().strftime('%H:%M:%S')}")
            df, spot = fetch_chain_df()

            if df.empty:
                print("⚠️  Empty dataframe - check API responses above")
            elif filter.should_store(df, spot):
                save_snapshot(df, spot)
            else:
                print("⭐ No meaningful change - skipping save")

        except Exception as e:
            print(f"❌ Error in main loop: {e}")
            import traceback
            traceback.print_exc()

        time.sleep(30)
