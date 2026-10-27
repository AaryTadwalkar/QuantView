"""
1. What this file does:
   Executes Workflow A: Expired-contract and expiry discovery for NIFTY option contracts
   via the Upstox API (/v2/expired-instruments/option/contract). Supports the Phase A
   bounded historical retention investigation (at most 12 requests) as well as the initial
   single smoke-test and earlier retention probes without downloading candles, leaking credentials,
   or exceeding strict request budgets.

2. Overall design:
   The tool reads UPSTOX_ACCESS_TOKEN from .env without ever logging or exposing it.
   It iterates sequentially over an approved, verified list of expiry dates. For each date, it performs
   exactly one HTTP GET request, captures raw byte responses before parsing, computes SHA-256,
   archives the raw gzipped JSON and manifest in Data/raw/upstox_rest/expired_api/, extracts
   discovered contracts metadata, and generates structured machine-readable index and evidence reports.
   If any blocking status (401, 403, 429, transport failure) occurs, it immediately halts.

3. Elements in the file:
   - RequestLimitExceeded: Custom exception raised when request budget is exceeded.
   - RequestAccountingSession: Custom requests.Session wrapper enforcing hard request ceilings.
   - ExpiryContractDiscoverer: Main workflow class managing requests, raw archival, and reporting.
   - main: CLI entry point executing the Phase A probe or single smoke test.

4. Final output of the file:
   - Raw immutable payloads: Data/raw/upstox_rest/expired_api/endpoint=option_contract/...
   - Retention evidence report: ops/evidence/phase_a_retention_probe.md (or M0-07.md)
   - Machine-readable index: reports/expired_contracts_index.json
"""

import gzip
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv


class RequestLimitExceeded(Exception):
    """Raised when the session attempts to exceed the strict approved request budget."""
    pass


class RequestAccountingSession(requests.Session):
    """
    1. The use of class:
       Wraps requests.Session to maintain a strict monotonic counter of outbound requests
       and enforce a hard budget limit, guaranteeing zero unbudgeted retries or leaks.

    2. What the class contains:
       - max_requests: Integer cap on total allowed outbound network requests.
       - request_count: Monotonic counter of dispatched requests.
       - send(): Overridden method incrementing counter and checking budget.

    3. Technologies used and why:
       Inherits from requests.Session to intercept all HTTP traffic at the transport adapter level.

    4. Key design and overall design of the class:
       Fail-closed budget guard. If request_count reaches max_requests, any further call raises RequestLimitExceeded.
    """

    def __init__(self, max_requests: int):
        """
        1. The use of function:
           Initializes the session wrapper with a maximum request ceiling and zero counter.

        2. How does the specific function work:
           Calls super().__init__() and stores max_requests cap and request_count = 0.

        3. Concepts used in the function:
           Object initialization, encapsulation of safety constraints.

        4. Places where this function is imported and used:
           Called when instantiating RequestAccountingSession inside ExpiryContractDiscoverer.

        5. Final output of the function, before and after:
           Before: Integer limit. After: Initialized session instance with request_count = 0.
        """
        super().__init__()
        self.max_requests = max_requests
        self.request_count = 0

    def send(self, request, **kwargs):
        """
        1. The use of function:
           Intercepts outbound HTTP requests to assert budget compliance and increment count.

        2. How does the specific function work:
           Checks if request_count >= max_requests; raises RequestLimitExceeded if true.
           Otherwise increments request_count by 1 and invokes super().send(request, **kwargs).

        3. Concepts used in the function:
           Transport-layer interception, budget enforcement guard, fail-closed design.

        4. Places where this function is imported and used:
           Invoked internally by requests whenever get(), post(), etc. are dispatched.

        5. Final output of the function, before and after:
           Before: PreparedRequest object. After: requests.Response or raised exception.
        """
        if self.request_count >= self.max_requests:
            raise RequestLimitExceeded(
                f"Budget breached: Cannot dispatch request #{self.request_count + 1}; "
                f"strict budget cap is {self.max_requests}."
            )
        self.request_count += 1
        return super().send(request, **kwargs)


class ExpiryContractDiscoverer:
    """
    1. The use of class:
       Coordinates the execution of expired contract queries, raw payload preservation,
       manifesting, and coverage reporting for approved expiry dates.

    2. What the class contains:
       - session: RequestAccountingSession with strict budget.
       - base_url: Upstox API v2 base endpoint.
       - underlying_key: Instrument key ('NSE_INDEX|Nifty 50').
       - raw_root: Base path for immutable raw storage.
       - query_and_archive(): Dispatches single query, archives raw payload, parses contracts.
       - execute_probe(): Runs probe across approved date list and records evidence.
       - generate_evidence(): Renders markdown evidence report.

    3. Technologies used and why:
       - requests: HTTP protocol client.
       - gzip: Standard compression matching Data Spec raw layer requirements.
       - hashlib: SHA-256 content-addressing for raw payloads.
       - json: Structured manifest serialization.

    4. Key design and overall design of the class:
       Strict separation of raw layer from canonical layer. Raw bytes are gzipped and hashed
       BEFORE any JSON parsing. Headers containing tokens are completely stripped from manifests.
    """

    def __init__(self, token: str, max_budget: int = 7, raw_root: Optional[Path] = None, reports_dir: Optional[Path] = None):
        """
        1. The use of function:
           Initializes the discoverer with credentials, budget, and raw storage destination.

        2. How does the specific function work:
           Sets base_url, instrument key, initializes RequestAccountingSession, sets headers
           without logging token, and sets raw root and reports directories.

        3. Concepts used in the function:
           Dependency injection, secret handling isolation, path resolution.

        4. Places where this function is imported and used:
           Called from main() or test fixtures.

        5. Final output of the function, before and after:
           Before: Secret token and budget parameter. After: Configured discoverer instance.
        """
        self.base_url = "https://api.upstox.com/v2"
        self.underlying_key = "NSE_INDEX|Nifty 50"
        self.session = RequestAccountingSession(max_requests=max_budget)
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })
        self.raw_root = raw_root or Path("Data/raw/upstox_rest/expired_api/endpoint=option_contract")
        self.reports_dir = reports_dir or Path("reports")

    def query_and_archive(self, expiry_date: str) -> Dict:
        """
        1. The use of function:
           Queries expired contracts for one expiry date, archives raw bytes, and returns summary.

        2. How does the specific function work:
           Sends GET request to /v2/expired-instruments/option/contract, computes raw response SHA-256,
           compresses raw bytes to .json.gz, writes companion manifest.json, and parses contract list.

        3. Concepts used in the function:
           Atomic immutable raw archival, payload hashing, metadata provenance separation.

        4. Places where this function is imported and used:
           Called sequentially within execute_probe() for each approved date in the budget.

        5. Final output of the function, before and after:
           Before: Date string. After: Result dictionary with status, contract count, and raw manifest path.
        """
        endpoint_url = f"{self.base_url}/expired-instruments/option/contract"
        params = {
            "instrument_key": self.underlying_key,
            "expiry_date": expiry_date,
        }

        retrieval_ts_utc = datetime.now(timezone.utc).isoformat()
        capture_date = retrieval_ts_utc[:10]

        # Dispatch single request with redirect following strictly disabled
        try:
            resp = self.session.get(endpoint_url, params=params, timeout=30, allow_redirects=False)
            raw_bytes = resp.content
            status_code = resp.status_code
        except requests.exceptions.RequestException as e:
            raw_bytes = json.dumps({"transport_error": str(e)[:300]}).encode("utf-8")
            status_code = 0
            resp = None

        # Cryptographic digest of raw response bytes
        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()

        # Archive path: Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=YYYY-MM-DD/
        dest_dir = self.raw_root / f"capture_date={capture_date}"
        dest_dir.mkdir(parents=True, exist_ok=True)

        raw_gz_path = dest_dir / f"response-{sha256_hash[:16]}.json.gz"
        # Include expiry date in manifest filename so distinct requests with identical bodies remain auditable
        manifest_path = dest_dir / f"manifest-{expiry_date}-{sha256_hash[:16]}.json"

        # Compress and save raw bytes
        with gzip.open(raw_gz_path, "wb") as gz:
            gz.write(raw_bytes)

        # Parse JSON payload
        contracts = []
        api_status = "UNKNOWN"
        error_msg = None

        if resp is not None and resp.ok:
            try:
                data = resp.json()
                api_status = data.get("status", "SUCCESS")
                contracts = data.get("data", [])
            except Exception as e:
                api_status = "PARSE_ERROR"
                error_msg = str(e)
        elif resp is not None:
            api_status = f"HTTP_{status_code}"
            try:
                error_msg = resp.json().get("errors", [{}])[0].get("message", resp.text[:200])
            except Exception:
                error_msg = resp.text[:200]
        else:
            api_status = "TRANSPORT_CONNECTION_ERROR"
            error_msg = "Network connection failed (DNS or connect error)"

        # Write metadata manifest (never logging Authorization tokens!)
        manifest = {
            "endpoint": "/v2/expired-instruments/option/contract",
            "url": endpoint_url,
            "params": params,
            "retrieval_timestamp_utc": retrieval_ts_utc,
            "http_status": status_code,
            "api_status": api_status,
            "raw_sha256": sha256_hash,
            "raw_bytes": len(raw_bytes),
            "compressed_path": str(raw_gz_path).replace("\\", "/"),
            "contract_count": len(contracts),
            "error_message": error_msg,
        }

        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)

        return {
            "expiry_date": expiry_date,
            "http_status": status_code,
            "api_status": api_status,
            "contract_count": len(contracts),
            "contracts": contracts,
            "raw_sha256": sha256_hash,
            "raw_path": str(raw_gz_path).replace("\\", "/"),
            "manifest_path": str(manifest_path).replace("\\", "/"),
            "error_message": error_msg,
        }

    def execute_probe(
        self,
        expiry_dates: List[str],
        evidence_file: str = "ops/evidence/phase_a_retention_probe.md",
        title: str = "QuantView — Phase A Historical Expiry-Retention Investigation Report",
    ) -> Tuple[List[Dict], str]:
        """
        1. The use of function:
           Orchestrates sequential querying and raw archival of expired options across a list
           of pre-verified expiry dates under strict budget caps and fail-fast safety stops.

        2. How does the specific function work:
           Iterates sequentially over expiry_dates. For each date, calls query_and_archive(),
           appends results, paces requests with 1.0s delays, checks for blocking HTTP errors (401, 403, 429, 0),
           immediately halts further queries if blocked, dumps an index to reports/expired_contracts_index.json,
           and renders a markdown evidence report.

        3. Concepts used in the function:
           Sequential request pacing, monotonic budget tracking, fail-closed safety gating,
           machine-readable index generation, and provenance tracking.

        4. Places where this function is imported and used:
           Called from main() when running retention probes or unit tests.

        5. Final output of the function, before and after:
           Before: List of date strings. After: Tuple containing list of query result dictionaries
           and the string path to the generated markdown evidence report.
        """
        results = []
        print(f"Beginning bounded probe for {len(expiry_dates)} dates (Budget cap: {self.session.max_requests})...")

        for idx, exp in enumerate(expiry_dates, 1):
            print(f"  [{idx}/{len(expiry_dates)}] Querying expiry: {exp} ...")
            res = self.query_and_archive(exp)
            results.append(res)
            print(f"       -> Status: {res['http_status']} | Contracts: {res['contract_count']} | Raw SHA: {res['raw_sha256'][:12]}...")

            # Safety check: fail-fast on auth failure, rate-limit, or transport disconnect
            if res["http_status"] in (401, 403, 429) or res["http_status"] == 0:
                print(f"CRITICAL: Blocking HTTP status encountered ({res['http_status']}). Halting probe immediately per safety rules.")
                break

            time.sleep(1.0)  # Conservative 1.0s inter-request pace

        # Write machine-readable index of tested expiries
        reports_dir = self.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        index_file = reports_dir / "expired_contracts_index.json"

        index_data = {
            "probe_executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "total_requests_budgeted": self.session.max_requests,
            "total_requests_dispatched": self.session.request_count,
            "results": [
                {
                    "expiry_date": r["expiry_date"],
                    "http_status": r["http_status"],
                    "contract_count": r["contract_count"],
                    "raw_sha256": r["raw_sha256"],
                    "raw_path": r["raw_path"],
                    "error_message": r["error_message"],
                }
                for r in results
            ]
        }

        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2)

        # Generate Evidence Document
        evidence_content = self.generate_evidence(results, title=title)
        evidence_path = Path(evidence_file)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(evidence_content, encoding="utf-8")

        return results, str(evidence_path)

    def generate_evidence(
        self,
        results: List[Dict],
        title: str = "QuantView — Phase A Historical Expiry-Retention Investigation Report",
    ) -> str:
        """
        1. The use of function:
           Formats probe execution results into a comprehensive, auditable Markdown report
           satisfying QuantView evidence standards.

        2. How does the specific function work:
           Iterates over the results list, extracts HTTP status, contract count, raw SHA-256 digest,
           raw storage path, and error diagnostics, and formats them into an aligned Markdown table
           with executive summary and budget accounting.

        3. Concepts used in the function:
           Markdown document generation, auditable artifact recording, cryptographic proof indexing.

        4. Places where this function is imported and used:
           Called internally by execute_probe() to create the final evidence file.

        5. Final output of the function, before and after:
           Before: List of result dictionaries. After: Formatted Markdown string ready to write to disk.
        """
        rows = []
        for r in results:
            rows.append(
                f"| `{r['expiry_date']}` | {r['http_status']} | {r['contract_count']} | `{r['raw_sha256'][:16]}...` | `{r['raw_path']}` | {r['error_message'] or 'None'} |"
            )
        table = "\n".join(rows)

        return f"""# {title}

**Phase:** Phase A — Bounded Historical Expiry-Retention Investigation  
**Execution Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}  
**Authority Reference:** `DOCS/AGENTS.md` §6, `DOCS/QUANTVIEW_DATA_SPEC.md` §11.6  
**Target Endpoint:** `GET /v2/expired-instruments/option/contract`  
**Underlying Key:** `NSE_INDEX|Nifty 50`  

---

## 1. Executive Summary & Budget Accounting
- **Approved Request Budget:** At most {self.session.max_requests} read-only requests.
- **Outbound Requests Dispatched:** Exactly {self.session.request_count} requests.
- **Remaining Budget:** {self.session.max_requests - self.session.request_count} requests.
- **Budget Compliance:** 100% compliant (0 unbudgeted retries, 0 candle requests, 0 credential leaks).

---

## 2. Retention Horizon Probe Results

| Tested Expiry Date | HTTP Status | Contracts Found | Raw SHA-256 (Prefix) | Raw Storage Path | Notes / Errors |
|---|---|---|---|---|---|
{table}

---

## 3. Raw Layer Provenance & Storage Separation
All {len(results)} responses were captured byte-for-byte in original JSON format, compressed with gzip, and stored under:
`Data/raw/upstox_rest/expired_api/endpoint=option_contract/`
Each response has an accompanying cryptographic manifest documenting retrieval timestamp, URL, query parameters, byte size, and SHA-256 checksum. Zero tokens or secrets were logged.
"""


def main():
    """
    1. The use of function:
       CLI entry point for running either the single smoke test, Phase A retention investigation,
       or single-date queries.

    2. How does the specific function work:
       Parses command-line arguments (--smoke-test, --phase-a, --expiry-date, --max-budget).
       Loads UPSTOX_ACCESS_TOKEN via dotenv without echoing it. Initializes ExpiryContractDiscoverer
       with strict budget cap. Dispatches request(s), archives raw response bytes, and outputs summary.

    3. Concepts used in the function:
       Strict budget bounding, defense against unbudgeted requests, credential isolation.

    4. Places where this function is imported and used:
       Executed when running `python tools/ingest/discover_expiries.py` from CLI.

    5. Final output of the function, before and after:
       Before: Raw API endpoint untouched. After: Gzipped raw response and manifest archived, exit code 0.
    """
    import argparse
    parser = argparse.ArgumentParser(description="QuantView Expired Option Contract Discovery / Retention Investigation")
    parser.add_argument("--smoke-test", action="store_true", help="Run exactly one smoke test request for 2025-04-24 (budget=1)")
    parser.add_argument("--phase-a", action="store_true", help="Run Phase A bounded 12-request historical retention investigation (budget=12)")
    parser.add_argument("--expiry-date", default=None, help="Single expiry date to query (YYYY-MM-DD)")
    parser.add_argument("--max-budget", type=int, default=None, help="Strict maximum request ceiling")

    args = parser.parse_args()

    load_dotenv(".env")
    token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token or not token.strip():
        print("ERROR: UPSTOX_ACCESS_TOKEN is missing or empty in .env")
        sys.exit(1)

    if args.smoke_test:
        expiries = ["2025-04-24"]
        budget = 1
        evidence_file = "ops/evidence/smoke_test_evidence.md"
        title = "QuantView — Single Authenticated Ingestion Smoke Test Report"
    elif args.phase_a:
        # Pre-verified 12 historical expiry dates spanning 2019 to 2024
        expiries = [
            "2024-12-26",  # Verified last Thursday of Dec 2024, regular trading day
            "2024-06-27",  # Verified last Thursday of Jun 2024, regular trading day
            "2023-12-28",  # Verified last Thursday of Dec 2023, regular trading day
            "2023-06-28",  # Shifted from 2023-06-29 due to Bakri Eid holiday (NSE Circular 095/2023)
            "2022-12-29",  # Verified last Thursday of Dec 2022, regular trading day
            "2022-06-30",  # Verified last Thursday of Jun 2022, regular trading day
            "2021-12-30",  # Verified last Thursday of Dec 2021, regular trading day
            "2021-06-24",  # Verified last Thursday of Jun 2021, regular trading day
            "2020-12-31",  # Verified last Thursday of Dec 2020, regular trading day
            "2020-06-25",  # Verified last Thursday of Jun 2020, regular trading day
            "2019-12-26",  # Verified last Thursday of Dec 2019, regular trading day
            "2019-06-27",  # Verified last Thursday of Jun 2019, regular trading day
        ]
        budget = 12
        evidence_file = "ops/evidence/phase_a_retention_probe.md"
        title = "QuantView — Phase A Historical Expiry-Retention Investigation Report"
    elif args.expiry_date:
        expiries = [args.expiry_date]
        budget = args.max_budget or 1
        evidence_file = "ops/evidence/single_query_evidence.md"
        title = "QuantView — Single Expiry Query Report"
    else:
        # Default 7-request probe list (OWNER-DEC-03)
        expiries = [
            "2025-04-24",
            "2024-10-31",
            "2024-04-25",
            "2023-10-26",
            "2023-04-27",
            "2022-04-28",
            "2021-04-29",
        ]
        budget = args.max_budget or 7
        evidence_file = "ops/evidence/M0-07.md"
        title = "QuantView — M0-07 Upstox Expired Options Retention Probe Report"

    discoverer = ExpiryContractDiscoverer(token=token, max_budget=budget)
    results, evidence_path = discoverer.execute_probe(expiries, evidence_file=evidence_file, title=title)

    print(f"\nProbe execution complete. Total requests: {discoverer.session.request_count}/{budget}.")
    print(f"Evidence report generated at: {evidence_path}")


if __name__ == "__main__":
    main()
