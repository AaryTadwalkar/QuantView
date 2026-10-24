"""
1. What this file does:
   Defines the canonical Pydantic model and matching PyArrow schema for the data eligibility dataset
   (`data_eligibility`) per QUANTVIEW_DATA_SPEC §8 and §11.1.

2. Overall design:
   Establishes the authoritative schema for evaluating point-in-time tradability and data quality:
     - Evaluates eligibility per (session_date x contract_id x interval x dataset_manifest_hash).
     - Standardizes status into ELIGIBLE, ELIGIBLE_WITH_WARNINGS, or INELIGIBLE.
     - Enforces stable reason codes: MISSING_BARS, STALE_DATA, INVALID_OHLC, DUPLICATE_ACTIVE_KEY,
       CONTRACT_INVALID, INSUFFICIENT_WARMUP, FLAT_BAR, SOURCE_SEMANTICS_UNVERIFIED, INCOMPLETE_CAPTURE.
     - Preserves immutable input dataset manifest hash and audit version.

3. Elements in the file:
   - DataEligibilityRow: Pydantic model for data eligibility evaluation records.
   - DATA_ELIGIBILITY_SCHEMA: PyArrow schema for data_eligibility Parquet storage.
   - VALID_ELIGIBILITY_STATUSES: Set of allowed status strings.
   - VALID_REASON_CODES: Set of recognized stable reason codes.

4. Final output of the file:
   - Exported validation class DataEligibilityRow and PyArrow schema DATA_ELIGIBILITY_SCHEMA.
"""

from datetime import date, datetime, timezone
from typing import List, Optional
import pyarrow as pa
from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_ELIGIBILITY_STATUSES = {"ELIGIBLE", "ELIGIBLE_WITH_WARNINGS", "INELIGIBLE"}

VALID_REASON_CODES = {
    "MISSING_BARS",
    "STALE_DATA",
    "INVALID_OHLC",
    "DUPLICATE_ACTIVE_KEY",
    "CONTRACT_INVALID",
    "INSUFFICIENT_WARMUP",
    "FLAT_BAR",
    "SOURCE_SEMANTICS_UNVERIFIED",
    "INCOMPLETE_CAPTURE",
}


class DataEligibilityRow(BaseModel):
    """
    1. The use of class:
       Canonical Pydantic model for data eligibility records per QUANTVIEW_DATA_SPEC §11.1.

    2. What the class contains:
       - session_date: Trading session date in Asia/Kolkata.
       - contract_id: Optional contract identifier (null for underlying-only intervals).
       - interval: Evaluated timeframe interval ('1m', '5m', '15m', etc.).
       - manifest_hash: Cryptographic hash of input dataset manifest.
       - status: 'ELIGIBLE', 'ELIGIBLE_WITH_WARNINGS', or 'INELIGIBLE'.
       - reason_codes: List of stable defect tags.
       - checked_at: Audit execution timestamp UTC.
       - audit_version: Audit algorithm version string (e.g. 'v1').
       - details_ref: Optional pointer to detailed diagnostic evidence artifact.

    3. Technologies used and why:
       Pydantic v2 BaseModel for frozen immutable record validation.

    4. Key design and overall design of the class:
       Guarantees point-in-time auditability so backtests can reproduce exact eligibility gates.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_date: date
    contract_id: Optional[str] = None
    interval: str
    manifest_hash: str
    status: str
    reason_codes: List[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    audit_version: str = "v1"
    details_ref: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validates that status is one of the three canonical eligibility states."""
        if v not in VALID_ELIGIBILITY_STATUSES:
            raise ValueError(f"Invalid eligibility status: {v}. Must be one of {VALID_ELIGIBILITY_STATUSES}")
        return v

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, v: List[str]) -> List[str]:
        """Validates that reason codes conform to the canonical vocabulary."""
        for code in v:
            if code not in VALID_REASON_CODES:
                raise ValueError(f"Unrecognized reason code: {code}. Must be in {VALID_REASON_CODES}")
        return v


# Authoritative PyArrow Schema for data_eligibility Parquet Storage
DATA_ELIGIBILITY_SCHEMA = pa.schema([
    pa.field("session_date", pa.date32(), nullable=False),
    pa.field("contract_id", pa.string(), nullable=True),
    pa.field("interval", pa.string(), nullable=False),
    pa.field("manifest_hash", pa.string(), nullable=False),
    pa.field("status", pa.string(), nullable=False),
    pa.field("reason_codes", pa.list_(pa.string()), nullable=False),
    pa.field("checked_at", pa.timestamp("us", tz="UTC"), nullable=False),
    pa.field("audit_version", pa.string(), nullable=False),
    pa.field("details_ref", pa.string(), nullable=True),
])
