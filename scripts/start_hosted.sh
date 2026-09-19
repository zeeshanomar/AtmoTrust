#!/bin/sh
set -eu
python scripts/seed_accounts.py
exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "${PORT:-10000}" --workers 1
