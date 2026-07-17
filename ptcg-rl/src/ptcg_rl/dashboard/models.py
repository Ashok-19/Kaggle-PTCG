from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OperationalStatus(StrEnum):
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"
    ABANDONED = "ABANDONED"
    SUPERSEDED = "SUPERSEDED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class GateDecision(StrEnum):
    NOT_REVIEWED = "NOT_REVIEWED"
    PASS = "PASS"
    CONDITIONAL_PASS = "CONDITIONAL_PASS"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"
    WAIVED = "WAIVED"


class ExperimentVerdict(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    NOT_EVALUATED = "NOT_EVALUATED"


class RecordEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int = 1
    record_id: str
    created_at_utc: str
    updated_at_utc: str | None = None
    source_path: str
    source_sha256: str | None = None
    producer: str
    producer_version: str | None = None
    run_id: str | None = None
    experiment_id: str | None = None
    gate_id: str | None = None


class Page(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)
