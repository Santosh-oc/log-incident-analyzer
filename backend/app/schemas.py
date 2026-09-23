"""Pydantic request/response models for the API."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class FileSummary(BaseModel):
    id: uuid.UUID
    original_filename: str
    file_size: int
    status: str
    total_lines: int
    parsed_events: int
    unparsed_lines: int
    time_start: datetime | None
    time_end: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class IncidentEvidenceLine(BaseModel):
    line_number: int
    timestamp: datetime
    level: str
    message: str


class IncidentOut(BaseModel):
    id: uuid.UUID
    service: str
    level: str
    fingerprint: str
    sample_message: str
    event_count: int
    first_seen: datetime
    last_seen: datetime
    analysis_status: str
    title: str | None
    category: str | None
    severity: str | None
    summary: str | None
    likely_cause: str | None
    evidence_lines: list[int] | None
    evidence: list[IncidentEvidenceLine]
    analysis_error: str | None
    model_name: str | None
    analyzed_at: datetime | None


class FileDetail(BaseModel):
    id: uuid.UUID
    original_filename: str
    file_size: int
    status: str
    total_lines: int
    parsed_events: int
    unparsed_lines: int
    unparsed_samples: list[int] | None
    time_start: datetime | None
    time_end: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    level_counts: dict[str, int]
    service_counts: dict[str, int]
    incidents: list[IncidentOut]


class HealthOut(BaseModel):
    status: str
    database: str
    minio: str
