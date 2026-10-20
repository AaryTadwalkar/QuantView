# QuantView — Phase A Historical Expiry-Retention Investigation Report

**Phase:** Phase A — Bounded Historical Expiry-Retention Investigation  
**Execution Date:** 2026-10-20  
**Authority Reference:** `DOCS/AGENTS.md` §6, `DOCS/QUANTVIEW_DATA_SPEC.md` §11.6  
**Target Endpoint:** `GET /v2/expired-instruments/option/contract`  
**Underlying Key:** `NSE_INDEX|Nifty 50`  

---

## 1. Executive Summary & Budget Accounting
- **Approved Request Budget:** At most 12 read-only requests.
- **Outbound Requests Dispatched:** Exactly 12 requests.
- **Remaining Budget:** 0 requests.
- **Budget Compliance:** 100% compliant (0 unbudgeted retries, 0 candle requests, 0 credential leaks).

---

## 2. Retention Horizon Probe Results

| Tested Expiry Date | HTTP Status | Contracts Found | Raw SHA-256 (Prefix) | Raw Storage Path | Notes / Errors |
|---|---|---|---|---|---|
| `2024-12-26` | 200 | 281 | `d87bc3494be9c35c...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-d87bc3494be9c35c.json.gz` | None |
| `2024-06-27` | 200 | 0 | `20bc1392a17b383b...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-20bc1392a17b383b.json.gz` | None |
| `2023-12-28` | 200 | 0 | `20bc1392a17b383b...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-20bc1392a17b383b.json.gz` | None |
| `2023-06-28` | 200 | 0 | `20bc1392a17b383b...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-20bc1392a17b383b.json.gz` | None |
| `2022-12-29` | 200 | 0 | `20bc1392a17b383b...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-20bc1392a17b383b.json.gz` | None |
| `2022-06-30` | 200 | 0 | `20bc1392a17b383b...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-20bc1392a17b383b.json.gz` | None |
| `2021-12-30` | 200 | 0 | `20bc1392a17b383b...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-20bc1392a17b383b.json.gz` | None |
| `2021-06-24` | 200 | 0 | `20bc1392a17b383b...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-20bc1392a17b383b.json.gz` | None |
| `2020-12-31` | 200 | 0 | `20bc1392a17b383b...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-20bc1392a17b383b.json.gz` | None |
| `2020-06-25` | 200 | 0 | `20bc1392a17b383b...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-20bc1392a17b383b.json.gz` | None |
| `2019-12-26` | 200 | 0 | `20bc1392a17b383b...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-20bc1392a17b383b.json.gz` | None |
| `2019-06-27` | 200 | 0 | `20bc1392a17b383b...` | `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-20bc1392a17b383b.json.gz` | None |

---

## 3. Raw Layer Provenance & Storage Separation
All 12 responses were captured byte-for-byte in original JSON format, compressed with gzip, and stored under:
`Data/raw/upstox_rest/expired_api/endpoint=option_contract/`
Each response has an accompanying cryptographic manifest documenting retrieval timestamp, URL, query parameters, byte size, and SHA-256 checksum. Zero tokens or secrets were logged.
