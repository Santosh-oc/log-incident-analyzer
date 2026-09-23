"""LLM analysis of incidents, run in a background task."""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.llm.prompt import SYSTEM_PROMPT, build_user_prompt
from app.llm.provider import LLMError
from app.llm.validate import ValidationError_, validate_response
from app.models import Incident, LogEvent, LogFile

logger = logging.getLogger(__name__)

SAMPLE_FIRST = 15
SAMPLE_LAST = 5
MESSAGE_TRUNCATE = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sample_events(db: Session, incident: Incident) -> list[tuple[int, datetime, str, str]]:
    """First 15 + last 5 events of the incident, messages truncated to 500 chars."""
    rows = (
        db.execute(
            select(LogEvent)
            .where(LogEvent.incident_id == incident.id)
            .order_by(LogEvent.timestamp, LogEvent.id)
        )
        .scalars()
        .all()
    )
    if len(rows) <= SAMPLE_FIRST + SAMPLE_LAST:
        picked = rows
    else:
        picked = rows[:SAMPLE_FIRST] + rows[-SAMPLE_LAST:]
    return [
        (e.line_number, e.timestamp, e.level, e.message[:MESSAGE_TRUNCATE])
        for e in picked
    ]


def _analyze_one(db: Session, provider: OpenAICompatibleProvider, incident: Incident) -> None:
    sample = _sample_events(db, incident)
    allowed_lines = {line_number for line_number, _, _, _ in sample}
    user_prompt = build_user_prompt(
        service=incident.service,
        level=incident.level,
        event_count=incident.event_count,
        first_seen=incident.first_seen,
        last_seen=incident.last_seen,
        sample_events=sample,
    )

    last_error = ""
    for attempt in (1, 2):
        try:
            raw = provider.complete(SYSTEM_PROMPT, user_prompt)
            result = validate_response(raw, allowed_lines)
        except (LLMError, ValidationError_) as exc:
            last_error = str(exc)
            if attempt == 1:
                logger.warning(
                    "incident_analysis_retry incident_id=%s attempt=1 error=%s",
                    incident.id,
                    last_error,
                )
                continue
            break
        else:
            incident.analysis_status = "COMPLETED"
            incident.title = result.title
            incident.category = result.category
            incident.severity = result.severity
            incident.summary = result.summary
            incident.likely_cause = result.likely_cause
            incident.evidence_lines = result.evidence_lines
            incident.analysis_error = None
            incident.model_name = provider.model_name
            incident.analyzed_at = _utcnow()
            db.commit()
            logger.info(
                "incident_analyzed incident_id=%s category=%s severity=%s",
                incident.id,
                result.category,
                result.severity,
            )
            return

    incident.analysis_status = "FAILED"
    incident.analysis_error = last_error
    incident.model_name = provider.model_name
    incident.analyzed_at = _utcnow()
    db.commit()
    logger.warning("incident_analysis_failed incident_id=%s error=%s", incident.id, last_error)


def run_analysis(file_id: uuid.UUID) -> None:
    """Analyze up to MAX_INCIDENTS_PER_ANALYSIS incidents for a file.

    Runs in its own DB session (invoked from FastAPI BackgroundTasks).
    """
    settings = get_settings()
    provider = OpenAICompatibleProvider()
    db = SessionLocal()
    try:
        log_file = db.get(LogFile, file_id)
        if log_file is None:
            logger.error("analysis_file_missing file_id=%s", file_id)
            return
        log_file.status = "ANALYZING"
        db.commit()

        incidents = (
            db.execute(
                select(Incident)
                .where(Incident.file_id == file_id)
                .order_by(Incident.event_count.desc(), Incident.first_seen)
                .limit(settings.max_incidents_per_analysis)
            )
            .scalars()
            .all()
        )
        logger.info(
            "analysis_started file_id=%s incidents=%d model=%s",
            file_id,
            len(incidents),
            provider.model_name,
        )
        for incident in incidents:
            _analyze_one(db, provider, incident)

        log_file.status = "ANALYZED"
        db.commit()
        logger.info("analysis_completed file_id=%s", file_id)
    except Exception as exc:
        db.rollback()
        try:
            log_file = db.get(LogFile, file_id)
            if log_file is not None:
                log_file.status = "FAILED"
                log_file.error_message = f"Analysis run failed: {exc.__class__.__name__}: {exc}"
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("analysis_crash file_id=%s", file_id)
        logger.exception("analysis_crashed file_id=%s", file_id)
    finally:
        db.close()
