"""Health check endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.schemas import HealthOut
from app.storage import get_storage

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    minio_status = "ok"
    try:
        get_storage().ensure_bucket(get_settings().minio_bucket_logs)
    except Exception:
        minio_status = "error"

    overall = "ok" if db_status == "ok" and minio_status == "ok" else "degraded"
    return HealthOut(status=overall, database=db_status, minio=minio_status)
