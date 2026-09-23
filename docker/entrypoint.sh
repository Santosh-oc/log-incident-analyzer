#!/bin/sh
set -e
cd /app
# Apply schema migrations, then serve.
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
