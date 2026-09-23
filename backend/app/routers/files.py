"""File upload, listing, detail, analysis, and deletion endpoints."""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Incident, LogEvent, LogFile
from app.schemas import FileDetail, FileSummary, IncidentEvidenceLine, IncidentOut
from app.services import analysis_service, upload_service
from app.storage import get_storage

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/upload", response_model=FileSummary, status_code=201)
async def upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> FileSummary:
    data = await file.read()
    log_file = upload_service.upload_file(db, get_storage(), file.filename or "upload", data)
    if log_file.status == "FAILED":
        raise HTTPException(status_code=422, detail=log_file.error_message or "Failed to parse log file.")
    return _to_summary(log_file)


@router.get("", response_model=list[FileSummary])
def list_files(db: Session = Depends(get_db)) -> list[FileSummary]:
    files = (
        db.execute(select(LogFile).order_by(LogFile.created_at.desc(), LogFile.id.desc()))
        .scalars()
        .all()
    )
    return [_to_summary(f) for f in files]


@router.get("/{file_id}", response_model=FileDetail)
def get_file(file_id: uuid.UUID, db: Session = Depends(get_db)) -> FileDetail:
    log_file = db.get(LogFile, file_id)
    if log_file is None:
        raise HTTPException(status_code=404, detail="File not found.")

    level_counts = dict(
        db.execute(
            select(LogEvent.level, func.count(LogEvent.id)).where(LogEvent.file_id == file_id).group_by(LogEvent.level)
        ).all()
    )
    service_counts = dict(
        db.execute(
            select(LogEvent.service, func.count(LogEvent.id))
            .where(LogEvent.file_id == file_id)
            .group_by(LogEvent.service)
            .order_by(func.count(LogEvent.id).desc())
        ).all()
    )

    incidents = (
        db.execute(
            select(Incident)
            .where(Incident.file_id == file_id)
            .order_by(Incident.event_count.desc(), Incident.first_seen)
        )
        .scalars()
        .all()
    )

    return FileDetail(
        id=log_file.id,
        original_filename=log_file.original_filename,
        file_size=log_file.file_size,
        status=log_file.status,
        total_lines=log_file.total_lines,
        parsed_events=log_file.parsed_events,
        unparsed_lines=log_file.unparsed_lines,
        unparsed_samples=log_file.unparsed_samples,
        time_start=log_file.time_start,
        time_end=log_file.time_end,
        error_message=log_file.error_message,
        created_at=log_file.created_at,
        updated_at=log_file.updated_at,
        level_counts=level_counts,
        service_counts=service_counts,
        incidents=[_to_incident(i, db) for i in incidents],
    )


@router.post("/{file_id}/analyze", status_code=202)
def analyze(file_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> dict:
    log_file = db.get(LogFile, file_id)
    if log_file is None:
        raise HTTPException(status_code=404, detail="File not found.")
    if log_file.status not in ("PARSED", "ANALYZED", "ANALYZING"):
        raise HTTPException(
            status_code=409,
            detail=f"File cannot be analyzed while its status is {log_file.status}.",
        )
    if log_file.status == "ANALYZING":
        return {"status": "ANALYZING", "detail": "Analysis already in progress."}
    log_file.status = "ANALYZING"
    log_file.error_message = None
    db.commit()
    background_tasks.add_task(analysis_service.run_analysis, file_id)
    return {"status": "ANALYZING", "detail": "Analysis started."}


@router.delete("/{file_id}", status_code=204)
def delete_file(file_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    upload_service.delete_file(db, get_storage(), file_id)


def _to_summary(f: LogFile) -> FileSummary:
    return FileSummary(
        id=f.id,
        original_filename=f.original_filename,
        file_size=f.file_size,
        status=f.status,
        total_lines=f.total_lines,
        parsed_events=f.parsed_events,
        unparsed_lines=f.unparsed_lines,
        time_start=f.time_start,
        time_end=f.time_end,
        error_message=f.error_message,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


def _to_incident(incident: Incident, db: Session) -> IncidentOut:
    evidence: list[IncidentEvidenceLine] = []
    if incident.evidence_lines:
        rows = (
            db.execute(
                select(LogEvent)
                .where(
                    LogEvent.file_id == incident.file_id,
                    LogEvent.line_number.in_(incident.evidence_lines),
                )
                .order_by(LogEvent.line_number)
            )
            .scalars()
            .all()
        )
        evidence = [
            IncidentEvidenceLine(
                line_number=r.line_number,
                timestamp=r.timestamp,
                level=r.level,
                message=r.message,
            )
            for r in rows
        ]
    return IncidentOut(
        id=incident.id,
        service=incident.service,
        level=incident.level,
        fingerprint=incident.fingerprint,
        sample_message=incident.sample_message,
        event_count=incident.event_count,
        first_seen=incident.first_seen,
        last_seen=incident.last_seen,
        analysis_status=incident.analysis_status,
        title=incident.title,
        category=incident.category,
        severity=incident.severity,
        summary=incident.summary,
        likely_cause=incident.likely_cause,
        evidence_lines=incident.evidence_lines,
        evidence=evidence,
        analysis_error=incident.analysis_error,
        model_name=incident.model_name,
        analyzed_at=incident.analyzed_at,
    )
