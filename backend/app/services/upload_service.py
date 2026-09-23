"""Upload workflow: validate → MinIO → DB row → parse → group → PARSED."""
import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Incident, LogEvent, LogFile
from app.parsing.fingerprint import fingerprint
from app.parsing.grouping import group_events
from app.parsing.jsonl_parser import parse_jsonl
from app.storage.base import ObjectStorage

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = (".jsonl", ".log", ".json")
EVENTS_BATCH_SIZE = 1000


def _validate_filename(filename: str, size: int) -> str:
    settings = get_settings()
    max_bytes = settings.max_log_size_mb * 1024 * 1024
    if size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large ({size} bytes). Max size is {settings.max_log_size_mb} MB.",
        )
    name = filename.lower()
    if name.endswith(".gz"):
        base = name[:-3]
    else:
        base = name
    if not base.endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=415,
            detail="Only JSON-lines log files (.jsonl, .log, .json, optionally .gz) are supported.",
        )
    return filename


def _object_key(file_id: uuid.UUID, filename: str) -> str:
    name = filename.lower()
    gz = ""
    base = name
    if name.endswith(".gz"):
        gz = ".gz"
        base = name[:-3]
    for ext in (".jsonl", ".log", ".json"):
        if base.endswith(ext):
            return f"logs/{file_id}/original{ext}{gz}"
    return f"logs/{file_id}/original{gz}"


def upload_file(
    db: Session,
    storage: ObjectStorage,
    filename: str,
    data: bytes,
) -> LogFile:
    settings = get_settings()
    _validate_filename(filename, len(data))

    file_id = uuid.uuid4()
    bucket = settings.minio_bucket_logs
    key = _object_key(file_id, filename)

    # 1. Upload to MinIO first. If this fails, no LogFile row is created.
    try:
        storage.upload(bucket, key, data)
    except Exception as exc:
        logger.exception("minio_upload_failed file_id=%s", file_id)
        raise HTTPException(
            status_code=502,
            detail="Failed to store the uploaded file in object storage. Please try again.",
        ) from exc

    # 2. Create the LogFile row. If the insert fails, delete the MinIO object.
    log_file = LogFile(
        id=file_id,
        original_filename=filename,
        file_size=len(data),
        minio_bucket=bucket,
        minio_object_key=key,
        status="UPLOADED",
    )
    try:
        db.add(log_file)
        db.commit()
        db.refresh(log_file)
    except Exception:
        db.rollback()
        try:
            storage.delete(bucket, key)
        except Exception:
            logger.exception("minio_cleanup_failed file_id=%s", file_id)
        raise

    # 3. Parse into events, group into incidents.
    try:
        _parse_and_store(db, log_file, data)
    except Exception as exc:
        log_file.status = "FAILED"
        log_file.error_message = f"Failed to parse log file: {exc.__class__.__name__}: {exc}"
        db.commit()
        logger.exception("parse_failed file_id=%s", file_id)
        return log_file

    return log_file


def _parse_and_store(db: Session, log_file: LogFile, data: bytes) -> None:
    result = parse_jsonl(data)

    # Insert events in batches of 1,000.
    events: list[LogEvent] = []
    for parsed in result.events:
        events.append(
            LogEvent(
                file_id=log_file.id,
                line_number=parsed.line_number,
                timestamp=parsed.timestamp,
                level=parsed.level,
                service=parsed.service,
                message=parsed.message,
                fingerprint=fingerprint(parsed.message) if parsed.level in ("WARN", "ERROR", "FATAL") else None,
            )
        )
    for i in range(0, len(events), EVENTS_BATCH_SIZE):
        db.add_all(events[i : i + EVENTS_BATCH_SIZE])
        db.flush()

    # Group into incidents (plain code, no LLM).
    groups = group_events(events, gap_minutes=get_settings().incident_gap_minutes)
    event_to_incident: dict[int, uuid.UUID] = {}
    for group in groups:
        incident = Incident(
            id=group.id,
            file_id=log_file.id,
            service=group.service,
            level=group.level,
            fingerprint=group.fingerprint,
            sample_message=group.sample_message,
            event_count=group.event_count,
            first_seen=group.first_seen,
            last_seen=group.last_seen,
        )
        db.add(incident)
        for event_id in group.event_ids:
            event_to_incident[event_id] = group.id
    db.flush()
    for event in events:
        if event.id in event_to_incident:
            event.incident_id = event_to_incident[event.id]

    timestamps = [e.timestamp for e in events]
    log_file.status = "PARSED"
    log_file.total_lines = result.total_lines
    log_file.parsed_events = result.parsed_events
    log_file.unparsed_lines = result.unparsed_lines
    log_file.unparsed_samples = result.unparsed_samples
    log_file.time_start = min(timestamps) if timestamps else None
    log_file.time_end = max(timestamps) if timestamps else None
    db.commit()
    db.refresh(log_file)
    logger.info(
        "file_parsed file_id=%s total_lines=%d parsed_events=%d unparsed_lines=%d incidents=%d",
        log_file.id,
        result.total_lines,
        result.parsed_events,
        result.unparsed_lines,
        len(groups),
    )


def delete_file(db: Session, storage: ObjectStorage, file_id: uuid.UUID) -> None:
    log_file = db.get(LogFile, file_id)
    if log_file is None:
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        storage.delete(log_file.minio_bucket, log_file.minio_object_key)
    except Exception:
        logger.exception("minio_delete_failed file_id=%s", file_id)
        raise HTTPException(
            status_code=502,
            detail="Failed to delete the file from object storage. Please try again.",
        )
    db.delete(log_file)
    db.commit()
    logger.info("file_deleted file_id=%s", file_id)
