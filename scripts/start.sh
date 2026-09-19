#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
PYTHON_BIN="${ATMOTRUST_PYTHON:-python3}"
"$PYTHON_BIN" -m pip install -r backend/requirements.txt
if [ ! -d frontend/node_modules ]; then (cd frontend && npm ci); fi
if [ ! -f frontend/dist/index.html ]; then (cd frontend && npm run build); fi
"$PYTHON_BIN" scripts/seed_accounts.py
exec "$PYTHON_BIN" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
