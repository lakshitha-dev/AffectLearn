#!/usr/bin/env bash
# Azure App Service startup script (Oryx activates the antenv virtualenv before
# running this, so `python` is the venv interpreter). Using `python -m` avoids
# depending on console-scripts being on PATH.
set -euo pipefail

echo "[startup] running database migrations..."
python -m alembic upgrade head

echo "[startup] starting uvicorn..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
