"""FastAPI application entry point.

Serves the API and the built frontend (frontend/dist) under the optional
$DKUBEX_BASE_PATH prefix so the app can run both standalone (at /) and as a
DKubeX workspace tile (under /workspace/<user>/<app>/).
"""
import logging
import os
import sys
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import files, health
from app.storage import get_storage

settings = get_settings()

# The platform injects DKUBEX_BASE_PATH into the pod; the workspace tile
# launcher maps it to BASE_PATH. Honour whichever is set.
if not settings.base_path and os.environ.get("DKUBEX_BASE_PATH"):
    settings.base_path = os.environ["DKUBEX_BASE_PATH"]

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", "-")
        return True


logging.getLogger().addFilter(RequestIdFilter())


def _log(msg: str, **fields) -> None:
    parts = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.info("%s %s", msg, parts)


app = FastAPI(title="Log Incident Analyzer", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    # Platform contract: the gateway authenticates the user and injects
    # X-Auth-Request-*. Never redirect to a login page — 401 when absent.
    # The health endpoint is exempt so Kubernetes probes can reach it.
    if (
        settings.require_auth
        and not request.url.path.endswith("/api/health")
        and not request.headers.get("x-auth-request-user")
    ):
        return JSONResponse(status_code=401, content={"detail": "Not authenticated."})
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        _log("request_failed", request_id=request_id, operation=request.method, path=request.url.path)
        raise
    duration_ms = int((time.monotonic() - start) * 1000)
    _log(
        "request",
        request_id=request_id,
        operation=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
    )
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_error request_id=%s", getattr(request.state, "request_id", "-"))
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


api = FastAPI(title="Log Incident Analyzer API", version="0.1.0")
api.include_router(health.router)
api.include_router(files.router)

DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST.is_dir():

    @api.get("/{path:path}", include_in_schema=False)
    def spa_fallback(path: str):
        # SPA routes (/, /files/<id>) all resolve to index.html.
        return FileResponse(DIST / "index.html")


@app.on_event("startup")
def on_startup() -> None:
    try:
        get_storage().ensure_bucket(settings.minio_bucket_logs)
        _log("startup", operation="ensure_bucket", bucket=settings.minio_bucket_logs, status="ok")
    except Exception as exc:
        _log(
            "startup",
            operation="ensure_bucket",
            bucket=settings.minio_bucket_logs,
            status="error",
            error=f"{exc.__class__.__name__}: {exc}",
        )


# --- Base-path aware mounting (DKubeX tile contract) -------------------------
# nginx forwards the full path, so the app must serve everything under the
# prefix itself. With no prefix (standalone dev) everything mounts at "/".
# The routers already carry the /api prefix, so the API app is mounted at the
# base; static assets are mounted first so they win over the catch-all.
BASE = (settings.base_path or "").strip("/")
if BASE:
    if DIST.is_dir():
        app.mount(f"/{BASE}/assets", StaticFiles(directory=DIST / "assets"), name="assets")
    app.mount(f"/{BASE}", api)
else:
    if DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
    app.mount("/", api)
