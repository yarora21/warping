#!/bin/sh
set -eu

alembic upgrade head
if [ "${SEED_DEMO_ON_EMPTY_DB:-false}" = "true" ]; then
    python -m app.bootstrap
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
