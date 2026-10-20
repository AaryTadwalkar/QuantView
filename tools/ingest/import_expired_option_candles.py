"""
1. What this file does:
   Executes Workflow C: Checkpointed acquisition and staging of expired NIFTY option-contract
   1-minute historical candles from Upstox API (/v2/expired-instruments/historical-candle).
   Enforces canonical route ordering ({to_date}/{from_date}), strict request budgeting,
   content-addressed raw payload preservation, companion manifest generation with Content-Type,
   safe payload parsing, non-destructive atomic staging, and candidate-band strike filtering.

2. Overall design:
   The tool operates in two phases:
     Phase 1: Fetch or load expired contract master for a given expiry date (from API or offline raw cache).
     Phase 2: For candidate strikes and date ranges, fetch 1-minute historical candles using
              the authoritative Upstox route:
              GET /v2/expired-instruments/historical-candle/{encoded_key}/1minute/{to_date}/{from_date}
   Every API response is gzipped and hashed into Data/raw/ before parsing, with an accompanying
   cryptographic manifest recording URL, headers, content-type, status, and SHA-256.
   Checkpoints track per-contract status. Staged CSV records are published atomically to staging/expired_options/
   without mutating canonical lake Parquet storage.

3. Elements in the file:
   - parse_option_candles: Validates raw 7-element candle tuples and maps contract metadata.
   - ExpiredOptionImporter: Main workflow class coordinating contract resolution, candle downloads,
     checkpoint management, candidate-band filtering, and atomic staging.
   - main: CLI entry point supporting dry-run, strike filtering, and offline contract loading.

4. Final output of the file:
   - Raw payloads: Data/raw/upstox_rest/expired_api/endpoint=historical_candle/...
   - Companion manifests: Data/raw/upstox_rest/expired_api/endpoint=historical_candle/.../manifest-*.json
   - Checkpoint state: staging/checkpoints/expired_opt_*.json
   - Staged normalized CSV: staging/expired_options/nifty_options_1m_{expiry}_{date}.csv
   - Coverage report: reports/expired_options_import_report.json
"""

import os
import sys
import gzip
import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote
import requests
from dotenv import load_dotenv

from tools.ingest.discover_expiries import RequestAccountingSession, RequestLimitExceeded


def parse_option_candles(raw_candles: List[List], contract: Dict) -> List[Dict]:
    """
    1. The use of function:
       Transforms raw 7-element expired candle tuples into validated long-format option records.

    2. How does the specific function work:
       Extracts [ts, open, high, low, close, volume, oi]. Binds contract metadata (instrument_key,
       trading_symbol, expiry, strike, option_type, lot_size). Validates OHLC integrity.

    3. Concepts used in the function:
       Long-format option candle representation per QuantView Data Spec, data integrity validation.

    4. Places where this function is imported and used:
       Called internally in ExpiredOptionImporter.fetch_contract_candles().

    5. Final output of the function, before and after:
       Before: Raw candle lists. After: List of canonical long-format option candle dicts.
    """
    rows = []
    inst_key = contract.get("instrument_key", "")
    symbol = contract.get("trading_symbol", "")
    expiry = contract.get("expiry", "")
    strike = float(contract.get("strike_price", 0))
    opt_type = contract.get("instrument_type", "")
    lot_size = int(contract.get("lot_size", 0))

    for c in raw_candles:
        if len(c) != 7:
            continue
        ts_str, o, h, l, cl, vol, oi = c
        o, h, l, cl = float(o), float(h), float(l), float(cl)
        vol, oi = int(vol), int(oi)

        # Basic OHLC sanity: high must be >= open, close, low; low must be <= open, close; low >= 0
        if h < max(o, cl) or l > min(o, cl) or l < 0:
            continue

        rows.append({
            "timestamp": ts_str,
            "instrument_key": inst_key,
            "trading_symbol": symbol,
            "expiry": expiry,
            "strike": strike,
            "option_type": opt_type,
            "lot_size": lot_size,
            "open": o,
            "high": h,
            "low": l,
            "close": cl,
            "volume": vol,
            "oi": oi,
            "source": "upstox_expired_historical_candle",
            "interval": "1minute",
        })
    return rows


class ExpiredOptionImporter:
    """
    1. The use of class:
       Manages bounded, checkpointed downloads of expired option contracts and 1m candles.

    2. What the class contains:
       - token: Upstox API access token.
       - session: RequestAccountingSession enforcing request ceiling.
       - base_url: API v2 endpoint.
       - raw_root: Destination for gzipped JSON responses and manifests.
       - staging_root: Destination for staged normalized CSVs.
       - checkpoint_dir: Path to restartable JSON checkpoint files.
       - get_contracts(): Retrieves expired contract list via API.
       - load_contracts_from_file(): Loads cached contract list from disk offline.
       - filter_candidate_band(): Filters contracts to Spot +/- Band without look-ahead bias.
       - fetch_contract_candles(): Retrieves 1m candles for one contract and archives raw bytes.
       - run(): Executes bounded batch download with checkpointing and atomic staging.

    3. Technologies used and why:
       - requests / RequestAccountingSession: HTTP communication with strict budget accounting.
       - gzip/hashlib: Raw payload preservation and content-addressed storage.
       - urllib.parse.quote: Exact URL-encoding for instrument keys.
       - pandas: In-memory table manipulation for atomic staging.

    4. Key design and overall design of the class:
       Authoritative endpoint order: {to_date}/{from_date}. Never overwrites raw files.
       Checkpoints track per-contract status. Dry-run mode provides exact request estimates.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        max_budget: int = 100,
        raw_root: Optional[Path] = None,
        staging_root: Optional[Path] = None,
        checkpoint_dir: Optional[Path] = None,
    ):
        """
        1. The use of function:
           Initializes ExpiredOptionImporter with credentials, budget, and storage paths.

        2. How does the specific function work:
           Configures RequestAccountingSession, sets headers, and resolves filesystem paths.

        3. Concepts used in the function:
           Session encapsulation, dependency injection.

        4. Places where this function is imported and used:
           Instantiated in main() and unit test fixtures.

        5. Final output of the function, before and after:
           Before: Raw arguments. After: Configured ExpiredOptionImporter.
        """
        self.token = token
        self.base_url = "https://api.upstox.com/v2"
        self.underlying_key = "NSE_INDEX|Nifty 50"
        self.session = RequestAccountingSession(max_requests=max_budget)
        if token:
            self.session.headers.update({
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            })
        self.raw_root = raw_root or Path("Data/raw/upstox_rest/expired_api")
        self.staging_root = staging_root or Path("staging/expired_options")
        self.checkpoint_dir = checkpoint_dir or Path("staging/checkpoints")

    def get_contracts(self, expiry_date: str) -> List[Dict]:
        """
        1. The use of function:
           Fetches expired contracts for an expiry date and archives raw JSON response with manifest.

        2. How does the specific function work:
           Dispatches GET to /v2/expired-instruments/option/contract, archives raw gzip, parses contracts.

        3. Concepts used in the function:
           Raw-first capture, content hashing.

        4. Places where this function is imported and used:
           Called in run() when contracts list is not pre-supplied.

        5. Final output of the function, before and after:
           Before: Expiry date string. After: List of contract dicts.
        """
        url = f"{self.base_url}/expired-instruments/option/contract"
        params = {"instrument_key": self.underlying_key, "expiry_date": expiry_date}

        resp = self.session.get(url, params=params, timeout=30, allow_redirects=False)
        raw_bytes = resp.content
        content_type = resp.headers.get("Content-Type", "application/json")

        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
        retrieval_ts = datetime.now(timezone.utc).isoformat()
        capture_date = retrieval_ts[:10]

        dest_dir = self.raw_root / f"endpoint=option_contract/capture_date={capture_date}"
        dest_dir.mkdir(parents=True, exist_ok=True)

        raw_gz = dest_dir / f"response-{sha256_hash[:16]}.json.gz"
        with gzip.open(raw_gz, "wb") as gz:
            gz.write(raw_bytes)

        manifest_path = dest_dir / f"manifest-{expiry_date}-{sha256_hash[:16]}.json"
        manifest = {
            "endpoint": "/v2/expired-instruments/option/contract",
            "url": url,
            "instrument_key": self.underlying_key,
            "expiry_date": expiry_date,
            "retrieval_timestamp_utc": retrieval_ts,
            "http_status": resp.status_code,
            "content_type": content_type,
            "raw_sha256": sha256_hash,
            "raw_bytes": len(raw_bytes),
            "compressed_path": str(raw_gz).replace("\\", "/"),
        }
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

        if not resp.ok:
            raise RuntimeError(f"HTTP {resp.status_code} fetching contracts for {expiry_date}: {resp.text[:200]}")

        payload = resp.json()
        return payload.get("data", [])

    def load_contracts_from_file(self, contracts_path: Path) -> List[Dict]:
        """
        1. The use of function:
           Loads expired contract master from a local JSON or gzipped JSON file offline.

        2. How does the specific function work:
           Opens file, decompresses if gzipped, parses JSON, and extracts contract array.

        3. Concepts used in the function:
           Offline execution, zero-network reproducibility.

        4. Places where this function is imported and used:
           Called in run() when contracts_file is supplied.

        5. Final output of the function, before and after:
           Before: Path to local JSON/GZ. After: List of contract dicts.
        """
        path = Path(contracts_path)
        if not path.exists():
            raise FileNotFoundError(f"Contracts file not found: {path}")

        if path.suffix == ".gz":
            with gzip.open(path, "rb") as gz:
                payload = json.loads(gz.read().decode("utf-8"))
        else:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)

        if isinstance(payload, list):
            return payload
        elif isinstance(payload, dict):
            return payload.get("data", [])
        return []

    def filter_candidate_band(
        self,
        contracts: List[Dict],
        spot_price: float,
        band_pts: float = 1000.0,
    ) -> List[Dict]:
        """
        1. The use of function:
           Filters contracts to a geometric candidate strike band (Spot +/- band_pts) per Task D.

        2. How does the specific function work:
           Computes min and max strike bounds. Retains contracts within bounds.
           Strictly forbids look-ahead volume or liquidity filtering.

        3. Concepts used in the function:
           Geometric strike band, anti-lookahead invariant.

        4. Places where this function is imported and used:
           Called in run() when candidate_band_pts and spot_price are specified.

        5. Final output of the function, before and after:
           Before: Complete contract list (e.g. 281). After: Candidate band contract list (e.g. 82).
        """
        min_strike = spot_price - band_pts
        max_strike = spot_price + band_pts
        filtered = [
            c for c in contracts
            if min_strike <= float(c.get("strike_price", 0)) <= max_strike
        ]
        # Sort deterministically: strike ascending, CE before PE
        filtered.sort(key=lambda x: (float(x.get("strike_price", 0)), x.get("instrument_type", "")))
        return filtered

    def fetch_contract_candles(
        self,
        contract: Dict,
        to_date: str,
        from_date: Optional[str] = None,
    ) -> Tuple[List[Dict], str]:
        """
        1. The use of function:
           Fetches 1m historical candles for an expired contract using authoritative Upstox route.

        2. How does the specific function work:
           Encodes instrument_key via quote(key, safe=''). Constructs URL with {to_date}/{from_date}
           parameter ordering. Dispatches GET, archives raw gzipped JSON, creates companion manifest,
           and parses raw 7-element candle tuples defensively.

        3. Concepts used in the function:
           Authoritative endpoint resolution, URL-encoding, companion manifest creation, raw byte preservation.

        4. Places where this function is imported and used:
           Called in run() loop for each eligible contract.

        5. Final output of the function, before and after:
           Before: Contract dict and date range. After: Tuple of (parsed candle rows list, SHA-256 hash).
        """
        inst_key = contract["instrument_key"]
        encoded_key = quote(inst_key, safe="")
        if from_date is None:
            from_date = to_date

        # Authoritative endpoint ordering: {to_date} precedes {from_date}
        url = f"{self.base_url}/expired-instruments/historical-candle/{encoded_key}/1minute/{to_date}/{from_date}"

        retrieval_ts = datetime.now(timezone.utc).isoformat()
        capture_date = retrieval_ts[:10]

        try:
            resp = self.session.get(url, timeout=30, allow_redirects=False)
            raw_bytes = resp.content
            status_code = resp.status_code
            if resp is not None and hasattr(resp, "headers") and hasattr(resp.headers, "get"):
                ct = resp.headers.get("Content-Type", "application/json")
                content_type = ct if isinstance(ct, str) else "application/json"
            else:
                content_type = "unknown"
        except requests.exceptions.RequestException as e:
            raw_bytes = json.dumps({"transport_error": str(e)[:300]}).encode("utf-8")
            status_code = 0
            content_type = "unknown"
            resp = None

        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()

        dest_dir = self.raw_root / f"endpoint=historical_candle/capture_date={capture_date}"
        dest_dir.mkdir(parents=True, exist_ok=True)

        raw_gz = dest_dir / f"response-{sha256_hash[:16]}.json.gz"
        with gzip.open(raw_gz, "wb") as gz:
            gz.write(raw_bytes)

        # Build contract-safe tag for manifest
        safe_key = inst_key.replace("|", "_").replace("/", "_")
        manifest_path = dest_dir / f"manifest-{safe_key}-{to_date}-{sha256_hash[:16]}.json"

        candles = []
        error_msg = None
        api_status = "UNKNOWN"

        if resp is not None and resp.ok:
            try:
                payload = resp.json()
                api_status = payload.get("status", "SUCCESS")
                data_field = payload.get("data")
                candles = data_field.get("candles", []) if isinstance(data_field, dict) else []
            except Exception as e:
                api_status = "PARSE_ERROR"
                error_msg = str(e)
        elif resp is not None:
            api_status = f"HTTP_{status_code}"
            error_msg = resp.text[:200]
        else:
            api_status = "TRANSPORT_ERROR"
            error_msg = "Network transport error"

        # Companion manifest recording all metadata including Content-Type
        manifest = {
            "endpoint": "/v2/expired-instruments/historical-candle",
            "url": url,
            "instrument_key": inst_key,
            "to_date": to_date,
            "from_date": from_date,
            "retrieval_timestamp_utc": retrieval_ts,
            "http_status": status_code,
            "content_type": content_type,
            "api_status": api_status,
            "raw_sha256": sha256_hash,
            "raw_bytes": len(raw_bytes),
            "compressed_path": str(raw_gz).replace("\\", "/"),
            "candle_count": len(candles),
            "error_message": error_msg,
        }
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

        if resp is None or not resp.ok:
            raise RuntimeError(f"HTTP {status_code} for {inst_key}: {error_msg}")

        rows = parse_option_candles(candles, contract)
        return rows, sha256_hash

    def run(
        self,
        expiry_date: str,
        to_date: str,
        from_date: Optional[str] = None,
        contracts: Optional[List[Dict]] = None,
        contracts_file: Optional[Path] = None,
        spot_price: Optional[float] = None,
        candidate_band_pts: Optional[float] = None,
        max_contracts: Optional[int] = None,
        dry_run: bool = False,
    ) -> Dict:
        """
        1. The use of function:
           Executes bounded expired option candle import or prints dry-run plan.

        2. How does the specific function work:
           Resolves contracts (offline file, pre-supplied, or API), applies candidate band filter,
           verifies checkpoints, loops over pending contracts, fetches candles, updates checkpoint,
           and stages output CSV atomically with resumption protection.

        3. Concepts used in the function:
           Checkpointing, bounded execution, atomic staging, resumption preservation.

        4. Places where this function is imported and used:
           Called from main() CLI and unit tests.

        5. Final output of the function, before and after:
           Before: Parameters. After: Summary dictionary with completion stats.
        """
        if from_date is None:
            from_date = to_date

        print(f"\n--- Expired Option Candle Importer ---")
        print(f"Expiry: {expiry_date} | Range: {from_date} to {to_date} | Dry Run: {dry_run}")

        # Resolve contracts source
        if contracts is None:
            if contracts_file is not None:
                print(f"Loading contracts offline from: {contracts_file}")
                contracts = self.load_contracts_from_file(contracts_file)
            elif dry_run:
                print("Dry Run: Simulating contract discovery...")
                return {
                    "status": "DRY_RUN_COMPLETED",
                    "expiry_date": expiry_date,
                    "to_date": to_date,
                    "from_date": from_date,
                    "message": "Specify contracts_file or active token to plan exact requests.",
                }
            else:
                contracts = self.get_contracts(expiry_date)

        # Apply candidate band filter if specified
        initial_count = len(contracts)
        if spot_price is not None and candidate_band_pts is not None:
            contracts = self.filter_candidate_band(contracts, spot_price=spot_price, band_pts=candidate_band_pts)
            print(f"Candidate band filter applied (Spot: {spot_price} +/- {candidate_band_pts} pts): "
                  f"{initial_count} -> {len(contracts)} contracts")

        if max_contracts and len(contracts) > max_contracts:
            contracts = contracts[:max_contracts]

        checkpoint_file = self.checkpoint_dir / f"expired_opt_{expiry_date}_{to_date}.json"
        completed_keys = set()
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    completed_keys = set(json.load(f).get("completed_contracts", []))
            except Exception:
                pass

        print(f"Total contracts in scope: {len(contracts)} (Already completed: {len(completed_keys)})")

        if dry_run:
            planned = [c["instrument_key"] for c in contracts if c["instrument_key"] not in completed_keys]
            print(f"Dry Run Plan: {len(planned)} requests required.")
            return {
                "status": "DRY_RUN_COMPLETED",
                "total_contracts": len(contracts),
                "planned_requests": len(planned),
                "sample_contracts": [c.get("trading_symbol") for c in contracts[:5]],
            }

        all_records = []
        for idx, c in enumerate(contracts, 1):
            key = c["instrument_key"]
            sym = c.get("trading_symbol", key)
            if key in completed_keys:
                print(f"  [{idx}/{len(contracts)}] {sym} (Skipping - completed)")
                continue

            print(f"  [{idx}/{len(contracts)}] Fetching {sym} ...")
            try:
                rows, sha = self.fetch_contract_candles(c, to_date=to_date, from_date=from_date)
                all_records.extend(rows)
                completed_keys.add(key)

                self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
                with open(checkpoint_file, "w", encoding="utf-8") as f:
                    json.dump({"completed_contracts": sorted(list(completed_keys))}, f, indent=2)

                print(f"       -> Retrieved {len(rows)} candles | SHA: {sha[:12]}...")
                time.sleep(0.5)
            except Exception as e:
                print(f"       -> ERROR: {e}")
                break

        # Atomic staging publication with non-destructive resumption protection
        staged_file = None
        if all_records:
            self.staging_root.mkdir(parents=True, exist_ok=True)
            staged_file = self.staging_root / f"nifty_options_1m_{expiry_date}_{to_date}.csv"
            tmp_staged = staged_file.with_suffix(".csv.tmp")
            import pandas as pd
            new_df = pd.DataFrame(all_records)

            if staged_file.exists():
                # Merge existing staged rows with newly fetched records, deduplicating on timestamp + instrument_key
                try:
                    existing_df = pd.read_csv(staged_file)
                    merged_df = pd.concat([existing_df, new_df], ignore_index=True)
                    merged_df.drop_duplicates(subset=["timestamp", "instrument_key"], keep="last", inplace=True)
                except Exception:
                    merged_df = new_df
            else:
                merged_df = new_df

            # Sort deterministically: strike ascending, CE before PE, timestamp ascending (09:15 to 15:29)
            if not merged_df.empty and {"strike", "option_type", "timestamp"}.issubset(merged_df.columns):
                merged_df.sort_values(by=["strike", "option_type", "timestamp"], ascending=[True, True, True], inplace=True)
                merged_df.reset_index(drop=True, inplace=True)

            # Write to temp file then atomic replace
            merged_df.to_csv(tmp_staged, index=False)
            tmp_staged.replace(staged_file)
            print(f"Atomically staged {len(merged_df)} total option candles to: {staged_file}")

        return {
            "status": "COMPLETED",
            "contracts_completed": len(completed_keys),
            "candles_staged": len(all_records),
            "staged_file": str(staged_file) if staged_file else None,
        }


def main():
    """
    1. The use of function:
       CLI entry point for running expired option candle downloads with argument parsing.

    2. How does the specific function work:
       Parses CLI options, initializes ExpiredOptionImporter, runs workflow, prints JSON result.

    3. Concepts used in the function:
       CLI interface, parameter delegation.

    4. Places where this function is imported and used:
       Executed when running python tools/ingest/import_expired_option_candles.py.

    5. Final output of the function, before and after:
       Before: Raw arguments. After: Executed workflow summary JSON.
    """
    import argparse
    parser = argparse.ArgumentParser(description="QuantView Expired Option Candle Importer")
    parser.add_argument("--expiry-date", required=True, help="Expiry date YYYY-MM-DD")
    parser.add_argument("--to-date", required=True, help="Ending date YYYY-MM-DD")
    parser.add_argument("--from-date", default=None, help="Starting date YYYY-MM-DD (defaults to to-date)")
    parser.add_argument("--contracts-file", default=None, help="Path to offline contracts JSON or JSON.GZ")
    parser.add_argument("--spot-price", type=float, default=None, help="Underlying spot price for candidate band")
    parser.add_argument("--candidate-band-pts", type=float, default=None, help="Candidate band half-width in points")
    parser.add_argument("--max-contracts", type=int, default=None, help="Max contracts to fetch")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without making network calls")

    args = parser.parse_args()
    load_dotenv(".env")
    token = os.getenv("UPSTOX_ACCESS_TOKEN")

    importer = ExpiredOptionImporter(token=token)
    result = importer.run(
        args.expiry_date,
        to_date=args.to_date,
        from_date=args.from_date,
        contracts_file=Path(args.contracts_file) if args.contracts_file else None,
        spot_price=args.spot_price,
        candidate_band_pts=args.candidate_band_pts,
        max_contracts=args.max_contracts,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
