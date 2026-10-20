# QuantView — Owner Decisions Log

**Document Version:** 1.0  
**Effective Date:** 2026-10-20  
**Authority Hierarchy:** Subordinate to `DOCS/AGENTS.md` and `DOCS/QUANTVIEW_MASTER_SPEC.md`  
**Purpose:** Formal, auditable record of owner approvals, release gates, and bounded-acquisition authorizations.

---

## 1. Active Decisions Register

### `OWNER-DEC-01` — Acceptance of Refreshed M0-01 Inventory
- **Decision Date:** 2026-10-20
- **Status:** **APPROVED**
- **Scope:** Formal acceptance of the refreshed read-only repository and market data inventory deliverable recorded in `ops/inventory.md`.
- **Governing Facts Accepted:**
  - Total `Data/` estate: 82,355 files (2,131.18 MB).
  - Snapshot captures: 82,283 files across 127 unique trading days and 36 expiry directories (including newly ingested PC B captures from 2026-10-12 to 2026-10-19).
  - Snapshot schema distribution: v1 (1,036), v2 (8,770), v3 (72,468), 5 null-byte corrupted files, 4 zero-byte empty files.
  - Underlying index candles: 432,967 rows in historical `1m/nifty.csv` + 18,985 rows across 57 live daily files. Known defect: line 432594 truncated string `'2026-10-08 0'`.
- **Limitations & Safety Invariant:** Acceptance acknowledges current disk evidence. It does not certify that unobserved data exists or that legacy semantics are fully resolved. Source data remains strictly immutable.

---

### `OWNER-DEC-02` — Authorize D:\ as Official Secondary Physical Backup Medium
- **Decision Date:** 2026-10-20
- **Status:** **APPROVED**
- **Scope:** Confirmation that external physical USB SSD `Cablet USB 3.0` (DeviceId 1, 256 GB, mounted as `D:\`, free space: 59.43 GB) containing directory `D:\Algo_Data_Final\Data` is the official secondary physical backup destination satisfying Non-negotiable Constraint `P1`.
- **Authorized Actions:**
  1. Generate SHA-256 checksum manifest of `Data/` and verify the existing copy on `D:\Algo_Data_Final\Data` (`M0-06`).
  2. Perform isolated restore verification to a temporary sandbox directory, verifying end-to-end byte checksum parity (`M0-08`).
  3. Record full command, checksum, and restore evidence in `ops/evidence/M0-06.md` and `ops/evidence/M0-08.md`.

---

### `OWNER-DEC-03` — Approve Seven-Request Bounded Expired-Contract Retention Probe
- **Decision Date:** 2026-10-20
- **Status:** **APPROVED**
- **Scope:** Authorization of exactly seven (7) outbound read-only REST requests to Upstox API endpoints to establish the empirical retention horizon for expired NIFTY option contracts.
- **Mandatory Operating Restrictions:**
  - Exactly 7 requests allocated; zero expansion, zero unbudgeted retries, zero redirects unaccounted for.
  - Read-only queries to `/v2/expired-instruments/option/contract` only.
  - **No candle downloads** during this probe.
  - Zero token or credential exposure in logs, reports, or stdout.
  - Original raw response payloads archived under `Data/raw/upstox_rest/expired_api/`.

---

### `OWNER-DEC-04` — Authorize M0-11 Contract Refinement
- **Decision Date:** 2026-10-20
- **Status:** **APPROVED**
- **Scope:** Authorization to execute task `M0-11` (*Post-inventory contract refinement and owner approval*), updating acceptance contracts for tasks `M0-02` through `M0-09` based on verified inventory facts, path corrections, and schema variants.
- **Deliverable Target:** `ops/evidence/M0-11.md`.

---

### `OWNER-DEC-05` — Single Authenticated Ingestion Smoke Test
- **Decision Date:** 2026-10-20
- **Status:** **APPROVED & EXECUTED**
- **Scope:** Narrow authorization of exactly one (1) outbound read-only request to validate updated credentials and API access against `/v2/expired-instruments/option/contract` for sample date `2025-04-24`.
- **Execution Accounting & Evidence:**
  - Budget Allocated: 1 request. Dispatched: 1 request. Remaining: 0 requests.
  - HTTP Status: **200 OK**. Total Contracts Returned: **232**.
  - Raw Response SHA-256: `ed718675f485a8635f50417c9dafed9b69bd1e033f64029c2156090a37a64897`.
  - Storage Location: `Data/raw/upstox_rest/expired_api/endpoint=option_contract/capture_date=2026-10-20/response-ed718675f485a863.json.gz`.
  - Manifest Location: `manifest-2025-04-24-ed718675f485a863.json`.
  - Credential Protection: Zero token or credential exposure in logs or artifacts. Redirects and retries strictly disabled (`allow_redirects=False`).

---

### `OWNER-DEC-06` — Phase A Bounded Historical Expiry-Retention Investigation
- **Decision Date:** 2026-10-20
- **Status:** **APPROVED & EXECUTED**
- **Scope:** Narrow authorization of at most twelve (12) outbound read-only requests to `/v2/expired-instruments/option/contract` across pre-verified historical expiry dates spanning 2019 to 2024 to empirically establish the historical retention boundary.
- **Execution Accounting & Evidence:**
  - Budget Allocated: 12 requests. Dispatched: 12 requests. Remaining: 0 requests.
  - Endpoints Consumed: `GET /v2/expired-instruments/option/contract` only (0 candle endpoints, 0 retries, `allow_redirects=False`).
  - Dates Probed: 12 exchange-verified dates: `2024-12-26`, `2024-06-27`, `2023-12-28`, `2023-06-28` (Bakri Eid shift), `2022-12-29`, `2022-06-30`, `2021-12-30`, `2021-06-24`, `2020-12-31`, `2020-06-25`, `2019-12-26`, `2019-06-27`.
  - Key Empirical Findings:
    - `2024-12-26`: HTTP 200 OK, 281 contracts returned (SHA: `d87bc3494be9c35c...`).
    - `2024-06-27` through `2019-06-27` (11 dates): HTTP 200 OK, 0 contracts returned (empty `data: []`, SHA: `20bc1392a17b383b...`).
  - Retention Horizon Established: The contract retention cliff lies between `2024-06-27` and `2024-12-26` (~1.8 to 2.3 years retention). Data prior to mid-2024 is not retained on Upstox expired-instruments contract endpoint.
  - Deliverable Evidence: `ops/evidence/phase_a_retention_probe.md`, `reports/expired_contracts_index.json`.
  - Invariant Conformance: All raw responses gzipped and manifested; zero credential exposure; live collector on PC B untouched.

