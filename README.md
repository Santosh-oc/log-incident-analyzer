# Log Incident Analyzer

A small MVP that turns uploaded JSON-lines log files into **grouped incidents** with
**plain-language, LLM-generated summaries**. Upload a log file, and the app parses it,
groups repeated errors into incidents, and (on demand) asks an OpenAI-compatible LLM to
explain each incident in plain language.

## What it does

1. **Upload** a `.jsonl` log file (one JSON object per line).
2. **Store** the raw file in **MinIO** (object storage).
3. **Parse** every line into a normalized event (timestamp, level, service, message).
4. **Group** events into **incidents** by `service + fingerprint` (a normalized message
   with variable parts like numbers, UUIDs, IPs and hex IDs replaced by placeholders),
   splitting a group when the gap between consecutive events exceeds a threshold.
5. **Analyze** (on demand, in the background): for each incident, call an
   OpenAI-compatible LLM to produce a title, category, severity, plain-language summary,
   likely cause, and evidence line numbers.
6. **Show** everything in a two-screen web UI (file list → file detail with incidents).
7. **Delete** a file, which cascades to its events, incidents, and the MinIO object.

## Tech stack

| Layer     | Technology |
|-----------|------------|
| Frontend  | React + TypeScript + Vite + Tailwind CSS |
| Backend   | FastAPI + SQLAlchemy + Alembic (Python) |
| Database  | PostgreSQL |
| Storage   | MinIO (S3-compatible) |
| LLM       | Any OpenAI-compatible `/v1/chat/completions` endpoint (e.g. vLLM serving Qwen) |

## Project layout

```text
backend/
  app/
    main.py              FastAPI app, routers, startup (bucket check)
    config.py            pydantic-settings
    db.py                engine, session
    models.py            SQLAlchemy models
    schemas.py           Pydantic API models
    storage/             ObjectStorage, MinIOObjectStorage
    parsing/             jsonl_parser.py, fingerprint.py, grouping.py
    llm/                 provider.py, openai_compatible.py, prompt.py, validate.py
    services/            upload_service.py, analysis_service.py
    routers/             files.py, health.py
  alembic/
  tests/
  requirements.txt
frontend/
  src/ (pages: FilesPage, FileDetailPage; components; api.ts)
README.md
.env.example
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- A running **PostgreSQL** instance
- A running **MinIO** instance
- An **OpenAI-compatible LLM** endpoint (for the analyze step)

If you don't have PostgreSQL/MinIO binaries locally, run them in containers:

```bash
docker run -d --name loganalyzer-pg \
  -e POSTGRES_USER=log_analyzer -e POSTGRES_PASSWORD=log_analyzer \
  -e POSTGRES_DB=log_analyzer -p 5432:5432 postgres:16

docker run -d --name loganalyzer-minio \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  -p 9000:9000 -p 9002:9001 quay.io/minio/minio server /data --console-address ":9001"
```

## Setup

### 1. Configure

Copy the example env file and edit the values:

```bash
cp .env.example backend/.env
```

Key settings (see `.env.example` for the full list):

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@localhost:5432/log_analyzer` |
| `MINIO_ENDPOINT` | e.g. `localhost:9000` |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | MinIO credentials |
| `MINIO_BUCKET_LOGS` | Bucket name (auto-created on startup) |
| `LLM_BASE_URL` | OpenAI-compatible base, e.g. `http://<host>:8000/v1` |
| `LLM_MODEL` | Model name served at that endpoint |
| `LLM_API_KEY` | API key (may be empty if the endpoint needs none) |
| `INCIDENT_GAP_MINUTES` | Gap that splits one incident into two (default 5) |
| `MAX_INCIDENTS_PER_ANALYSIS` | Cap on incidents analyzed per run (default 50) |

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head          # create the schema
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The backend listens on `http://localhost:8000`. On startup it verifies the database
connection and ensures the MinIO bucket exists.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server (default `http://localhost:5173`) proxies `/api` to the backend on
`localhost:8000`, so no CORS setup is needed.

## Using the app

1. Open the frontend. The **Files** screen lists uploaded files with status, line
   counts, and time range.
2. Click **Upload** and choose a `.jsonl` file. The file is stored in MinIO, parsed,
   and grouped into incidents. Status becomes `PARSED`.
3. Open a file to see its **incidents** (grouped, with counts and time ranges).
4. Click **Analyze**. The file status becomes `ANALYZING`; the detail page polls every
   3 seconds. As each incident is analyzed, its LLM summary appears. When done, status
   is `ANALYZED`.
5. **Delete** a file to remove it, its events/incidents, and the stored object.

## API

All endpoints are under `/api`.

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/health` | Health check (status, database, minio) |
| `POST` | `/api/files/upload` | Upload a `.jsonl` file (multipart `file`) |
| `GET`  | `/api/files` | List files |
| `GET`  | `/api/files/{id}` | File detail with incidents |
| `POST` | `/api/files/{id}/analyze` | Start background analysis (returns `202`) |
| `DELETE` | `/api/files/{id}` | Delete file + cascade |

### Example

```bash
# upload
curl -X POST http://localhost:8000/api/files/upload -F "file=@payments.jsonl"

# list
curl http://localhost:8000/api/files

# detail
curl http://localhost:8000/api/files/<file_id>

# analyze (background)
curl -X POST http://localhost:8000/api/files/<file_id>/analyze

# delete
curl -X DELETE http://localhost:8000/api/files/<file_id>
```

## Log file format

One JSON object per line. Recognized fields (all optional except a parseable
timestamp and a message):

```json
{"ts": "2026-09-22T14:00:04Z", "level": "error", "service": "payment-service", "msg": "Timeout calling bank-gateway after 30000ms (order_id=A5506)"}
```

- Timestamp fields tried: `ts`, `timestamp`, `time`, `@timestamp`, `datetime`.
- Level fields tried: `level`, `severity`, `lvl`.
- Service fields tried: `service`, `service_name`, `app`, `component`.
- Message fields tried: `msg`, `message`, `text`.

Lines that can't be parsed are counted as `unparsed_lines` and skipped.

## Testing

Backend unit tests cover the parser, fingerprinting, grouping, LLM response
validation, and the LLM provider (with a mocked HTTP layer):

```bash
cd backend
.venv/bin/pytest -q
```

## Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `GET /api/health` shows `database: error` | `DATABASE_URL` is wrong or PostgreSQL isn't running. |
| `GET /api/health` shows `minio: error` | `MINIO_ENDPOINT`/credentials wrong, or MinIO isn't running. |
| Upload succeeds but analyze fails with `404` | `LLM_BASE_URL` is wrong. It must be the base that ends in `/v1` (the app appends `/chat/completions`). |
| Analyze fails with `401` | `LLM_API_KEY` is missing or wrong. |
| Analyze fails with `429` | The LLM endpoint is rate-limited; retry shortly. |
| Analyze fails with a timeout | Increase `LLM_TIMEOUT_SECONDS`, or check the model server is responsive. |
| Frontend can't reach the API | Make sure the backend is on `localhost:8000` (the Vite proxy target) or adjust `vite.config.ts`. |
| Port 9001 already in use (MinIO console) | Map the console to another host port, e.g. `-p 9002:9001`. |

## Out of scope (by design)

This is an MVP. It intentionally does **not** include: authentication, multi-user
support, a settings page, log tailing/streaming, alerting, or a Docker Compose /
Kubernetes manifest for the app itself.
