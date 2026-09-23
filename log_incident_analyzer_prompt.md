# Build a Log Incident Analyzer Using a Local LLM

Build an MVP web application that **turns uploaded log files into a list of incidents with plain-language summaries and likely causes**, using a locally hosted LLM (Qwen on a DGX box, served through an OpenAI-compatible API). Only JSON-lines log files are supported in this version. Design with clean architecture so more log formats can be added later.

Keep the scope exactly as written. Anything listed under **Out of Scope** must not be built.

---

## 1. Workflow

```text
Upload Log File → Parse Into Events → Group Errors Into Incidents → Analyze With LLM → View Results
```

Simple enough for an engineer to use without reading documentation.

---

## 2. Tech Stack

- **Frontend**: React, TypeScript, Vite, Tailwind CSS
- **Backend**: Python, FastAPI, Pydantic, Uvicorn
- **Object Storage**: MinIO — stores the original uploaded log files
- **Database**: PostgreSQL — stores file metadata, parsed events, and incidents
- **ORM / Migrations**: SQLAlchemy 2.x (synchronous, `psycopg` driver) + Alembic
- **LLM**: any OpenAI-compatible chat completions endpoint (vLLM serving Qwen)

PostgreSQL and MinIO are externally running services. **Do not introduce Docker, Docker Compose, or Kubernetes.**

---

## 3. Out of Scope (do NOT build)

- Log formats other than JSON-lines (no plain text, syslog, nginx, etc.)
- A settings page — LLM configuration comes from `.env` only
- Free-text questions / chat about logs
- A separate "classify" step — category comes back in the same LLM call as the summary
- Redaction of sensitive data
- Custom grouping rules, time-window filters, known-issue notes
- Analysis history — re-running analysis replaces the previous results
- JSON/CSV export or download buttons
- Authentication, users, multi-tenancy
- Vision models, embeddings, vector search

---

## 4. Input Format — JSON-lines

One JSON object per line. Example:

```jsonl
{"ts":"2026-09-22T14:03:11Z","level":"error","service":"payment-service","msg":"Timeout calling bank-gateway after 30000ms (order_id=A1923)"}
{"ts":"2026-09-22T14:03:12Z","level":"info","service":"api","msg":"GET /orders 200 45ms"}
{"timestamp":"2026-09-22T14:03:15.210Z","severity":"ERROR","app":"api","message":"DB connection refused host=db-01"}
```

Accept `.jsonl`, `.log`, and `.json` extensions, plus `.gz` versions of them (decompress while reading).

### Field mapping (first key found wins)

| Event field | Accepted keys |
|---|---|
| timestamp | `ts`, `timestamp`, `time`, `@timestamp` |
| level | `level`, `severity`, `lvl`, `log.level` |
| service | `service`, `app`, `logger`, `component` |
| message | `msg`, `message`, `text` |

Rules:
- Timestamps: ISO-8601 strings or Unix epoch seconds/milliseconds. Timestamps without a time zone are treated as UTC.
- Levels are normalized to one of: `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` (map `warning`→`WARN`, `critical`/`crit`/`panic`→`FATAL`, `err`→`ERROR`, unknown→`INFO`).
- Missing service → `"unknown"`.
- A line is **unparsed** if it is not valid JSON, is not an object, or has no timestamp or no message. Count unparsed lines and keep the first 10 unparsed line numbers. Never crash on a bad line.
- Blank lines are skipped and not counted.

---

## 5. Storage — MinIO

- MinIO is the system of record for the original log file. Do not store file contents in PostgreSQL (parsed events are fine).
- Object key: `logs/{file_id}/original{ext}` (keep the original extension, e.g. `.jsonl.gz`).
- Bucket name configurable; create the bucket at startup if missing.
- Never expose MinIO credentials to the frontend.

Create an `ObjectStorage` abstraction with `upload()`, `download()`, `delete()`, `exists()`, and implement `MinIOObjectStorage`. Services depend on `ObjectStorage`, not the MinIO client.

### Upload workflow

```text
Receive file → Validate extension and size → Generate file_id (UUID)
→ Upload to MinIO → Create LogFile row (status UPLOADED)
→ Parse into events → Group into incidents → status PARSED
```

- If the MinIO upload fails, do not create a LogFile row.
- If the database insert fails after a successful MinIO upload, delete the MinIO object.
- If parsing fails, set status `FAILED` with a readable `error_message`. Keep the file.
- Parsing runs synchronously inside the upload request (files are capped by `MAX_LOG_SIZE_MB`). Insert events in batches of 1,000.

### Deletion

Deleting a file removes its MinIO object and its database rows (cascade to events and incidents). No orphans.

---

## 6. Database — PostgreSQL

Three tables. Create an initial Alembic migration; `alembic upgrade head` must build the schema.

### LogFile

```text
id                 UUID PRIMARY KEY
original_filename  VARCHAR
file_size          BIGINT
minio_bucket       VARCHAR
minio_object_key   VARCHAR
status             VARCHAR   -- UPLOADED, PARSED, ANALYZING, ANALYZED, FAILED
total_lines        INTEGER
parsed_events      INTEGER
unparsed_lines     INTEGER
unparsed_samples   JSONB     -- first 10 unparsed line numbers
time_start         TIMESTAMPTZ NULL
time_end           TIMESTAMPTZ NULL
error_message      TEXT NULL
created_at         TIMESTAMPTZ
updated_at         TIMESTAMPTZ
```

### LogEvent

```text
id                 BIGINT IDENTITY PRIMARY KEY
file_id            UUID FK → LogFile (ON DELETE CASCADE), indexed
incident_id        UUID FK → Incident NULL (ON DELETE SET NULL), indexed
line_number        INTEGER
timestamp          TIMESTAMPTZ, indexed
level              VARCHAR
service            VARCHAR
message            TEXT
fingerprint        VARCHAR NULL   -- only for WARN/ERROR/FATAL
```

### Incident

```text
id                 UUID PRIMARY KEY
file_id            UUID FK → LogFile (ON DELETE CASCADE), indexed
service            VARCHAR
level              VARCHAR        -- highest level in the incident
fingerprint        VARCHAR
sample_message     TEXT
event_count        INTEGER
first_seen         TIMESTAMPTZ
last_seen          TIMESTAMPTZ

-- filled by analysis
analysis_status    VARCHAR        -- NOT_ANALYZED, COMPLETED, FAILED
title              VARCHAR NULL
category           VARCHAR NULL   -- see categories below
severity           VARCHAR NULL   -- low, medium, high, critical
summary            TEXT NULL
likely_cause       TEXT NULL
evidence_lines     JSONB NULL     -- list of line numbers
analysis_error     TEXT NULL
model_name         VARCHAR NULL
analyzed_at        TIMESTAMPTZ NULL
```

---

## 7. Grouping Errors Into Incidents (plain code, no LLM)

1. Only events with level `WARN`, `ERROR`, or `FATAL` are grouped.
2. **Fingerprint** each message: lowercase it, then replace UUIDs with `<uuid>`, IPs with `<ip>`, hex strings (8+ chars) with `<hex>`, quoted strings with `<str>`, and any remaining numbers with `<n>`. Collapse whitespace.
   - `Timeout calling bank-gateway after 30000ms (order_id=A1923)` → `timeout calling bank-gateway after <n>ms (order_id=a<n>)`
3. Sort events by timestamp. Events with the **same service and same fingerprint** belong to the same incident while the gap between consecutive events is ≤ `INCIDENT_GAP_MINUTES` (default 5). A larger gap starts a new incident.
4. Store each incident and set `incident_id` on its events.

Put fingerprinting and grouping in their own module with no database or LLM imports, so they are easy to unit-test.

---

## 8. LLM Analysis

### Provider abstraction

Create an `LLMProvider` interface with one method, `complete(system_prompt, user_prompt) -> str`, and implement `OpenAICompatibleProvider` (POST `{base_url}/chat/completions`, Bearer auth if an API key is set). No model-specific logic in the analysis service.

Handle: connection errors, timeouts, 401, 429, 5xx, empty responses. Error messages must be readable and include a truncated (≤ 300 chars) raw response snippet where relevant. Never log the API key.

### Running analysis

- `POST /api/files/{id}/analyze` sets the file status to `ANALYZING`, returns `202` immediately, and runs the analysis with FastAPI `BackgroundTasks`.
- Analyze up to `MAX_INCIDENTS_PER_ANALYSIS` incidents (default 50), largest `event_count` first. Others stay `NOT_ANALYZED`.
- One LLM call per incident, sequentially. One failed incident does not stop the rest; mark it `FAILED` with `analysis_error`.
- Re-running analysis overwrites previous analysis fields.
- When done, file status becomes `ANALYZED` (even if some incidents failed). If the run crashes, status becomes `FAILED` with `error_message`.

### What is sent per incident (keep it small)

- Service, highest level, event count, first/last seen
- Up to 20 sample events: the first 15 and the last 5, each as `line_number | timestamp | level | message`
- Truncate each message to 500 characters and the whole sample block to 8,000 characters

### Prompt contract

The system prompt tells the model it is a site-reliability engineer, must only use the provided log lines, must not guess beyond them, and must reply with **only** a JSON object:

```json
{
  "title": "Bank gateway timeouts in payment-service",
  "category": "timeout",
  "severity": "high",
  "summary": "Between 14:03 and 14:11, 214 payment requests timed out waiting 30s for bank-gateway.",
  "likely_cause": "bank-gateway is unresponsive or overloaded; the errors start abruptly and affect all orders.",
  "evidence_lines": [1042, 1043, 1188]
}
```

Allowed categories: `timeout`, `database`, `auth`, `network`, `config`, `resource` (memory/disk/CPU), `dependency` (external service), `application` (code error/exception), `other`.

### Response validation

1. Remove any `<think>...</think>` block (Qwen reasoning output).
2. Strip markdown code fences.
3. Parse JSON and validate with a Pydantic model. `category` and `severity` must be allowed values; `evidence_lines` must only contain line numbers that were sent — drop any others.
4. If it fails, retry the call once. If it still fails, mark the incident `FAILED` with a readable error and a truncated raw snippet. Never store unvalidated data.

Use `temperature=0`.

---

## 9. API Endpoints

```text
GET    /api/health
POST   /api/files/upload           multipart file → LogFile with stats
GET    /api/files                  list, newest first
GET    /api/files/{file_id}        file stats + level counts + service counts + incidents
                                   (each incident includes its evidence lines' text)
POST   /api/files/{file_id}/analyze   → 202
DELETE /api/files/{file_id}
```

Use Pydantic request/response models. Errors return `{ "detail": "<friendly message>" }` with an appropriate status code, never a stack trace.

---

## 10. Frontend — Two Screens

### Files (default page)

```text
┌─────────────────────────────────────────────┐
│ Upload log file                             │
│  Drag & drop a .jsonl file here  [Browse]   │
│  Max size: 50 MB                            │
├─────────────────────────────────────────────┤
│ File              Uploaded   Status   Events│
│ payments.jsonl    14:20      Analyzed 48,210│
│ api-0922.jsonl.gz 13:02      Parsed   12,044│
└─────────────────────────────────────────────┘
```

- Reject unsupported files with: "Only JSON-lines log files (.jsonl, .log, .json, optionally .gz) are supported."
- Show upload progress and errors inline. Clicking a row opens the file.

### File Detail

```text
┌──────────────────────────────────────────────────────┐
│ payments.jsonl                        [Analyze] [Delete]
│ 48,210 events · 12 unparsed · 14:00 – 15:00 UTC      │
│ ERROR 812   WARN 230   INFO 47,168                   │
├──────────────────────────────────────────────────────┤
│ Incidents (6)                                        │
│ ▸ HIGH  timeout   Bank gateway timeouts   214  14:03 │
│ ▸ MED   database  DB connection refused    41  14:05 │
│ ▸ —     —         (not analyzed)            3  14:40 │
└──────────────────────────────────────────────────────┘
```

- Before analysis, incidents show service, sample message, count, and time range.
- Expanding an incident shows title, summary, likely cause, and the evidence log lines.
- `Analyze` shows a spinner and "Analyzing incidents…" while status is `ANALYZING`; poll `GET /api/files/{id}` every 3 seconds until it changes. Button text becomes `Re-analyze` after the first run.
- Failed incidents show their error message and are not hidden.
- Deleting asks for confirmation.
- Dark/light theme via `prefers-color-scheme`. Responsive down to mobile width.

The frontend calls the backend with relative `/api/...` URLs; Vite proxies `/api` to the backend.

---

## 11. Environment

Provide `.env.example`; never commit real values.

```env
APP_ENV=development
LOG_LEVEL=INFO
MAX_LOG_SIZE_MB=50

DATABASE_URL=postgresql+psycopg://log_analyzer:log_analyzer@localhost:5432/log_analyzer

MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
MINIO_BUCKET_LOGS=logs

LLM_BASE_URL=http://<dgx-host>:8000/v1
LLM_MODEL=<served-model-name>
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=120
LLM_MAX_TOKENS=1024

INCIDENT_GAP_MINUTES=5
MAX_INCIDENTS_PER_ANALYSIS=50
```

Load settings with `pydantic-settings`. Example values are for development only.

Run locally:
- Backend: `alembic upgrade head` then `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Frontend: `npm install && npm run dev`

---

## 12. Suggested Project Layout

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

---

## 13. Logging & Security

- Structured logs with: request_id, operation, file_id, event counts, model, duration_ms, status.
- Never log API keys, MinIO secrets, or log-line contents / LLM responses.
- Never return credentials in any API response.

---

## 14. Testing

No real LLM, API key, or DGX access required for tests. Generate synthetic JSONL files in tests and mock the LLM provider.

Test:
- **Parser**: valid lines, each field-mapping variant, epoch timestamps, invalid JSON, missing fields, blank lines, `.gz` files
- **Fingerprint**: numbers, UUIDs, IPs, hex, quoted strings normalize as expected
- **Grouping**: same fingerprint within gap → one incident; gap exceeded → two; different services → separate
- **Validation**: clean JSON, fenced JSON, `<think>` block, bad category, invalid evidence lines dropped, non-JSON → retry → FAILED
- **Provider** (mocked HTTP): success, 401, 429, timeout, empty response
- **API**: upload (valid, too large, wrong type), list, detail, analyze with mocked LLM, delete removes MinIO object and rows

Persistence check (against real PostgreSQL and MinIO): upload → analyze (mocked LLM) → restart backend → file, events, and incidents still returned → delete leaves nothing behind.

---

## 15. Build Order

Build and verify each step before starting the next.

1. Config, database models, Alembic migration — verify `alembic upgrade head` creates the tables.
2. `ObjectStorage` + MinIO implementation — verify upload/download/delete against MinIO.
3. JSONL parser, fingerprint, grouping + their unit tests — all passing.
4. Upload service and `POST /api/files/upload`, `GET /api/files`, `GET /api/files/{id}`, `DELETE` — verify with a sample file via curl.
5. LLM provider, prompt builder, response validator + tests with mocks.
6. Analysis service and `POST /api/files/{id}/analyze` — verify one real call against the DGX Qwen endpoint.
7. Frontend Files page.
8. Frontend File Detail page with polling.
9. README (what it does, setup, running, configuration, API, testing, troubleshooting) and a final end-to-end run:

```text
Upload JSONL → Stored in MinIO → Events + incidents in PostgreSQL → Analyze → Summaries shown → Delete
```
