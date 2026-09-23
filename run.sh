#!/usr/bin/env bash
# Start the Log Incident Analyzer (API + built frontend) on the DKubeX-allocated port.
set -euo pipefail
cd "$(dirname "$0")"

set -a
. ./.dkubex-app.env
set +a
export BASE_PATH="$DKUBEX_BASE_PATH"

cd backend
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
