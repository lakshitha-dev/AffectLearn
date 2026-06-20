#!/usr/bin/env bash
# Azure App Service startup script (Oryx activates the antenv virtualenv before
# running this, so `python` is the venv interpreter). Using `python -m` avoids
# depending on console-scripts being on PATH.
set -euo pipefail

echo "[startup] running database migrations..."
python -m alembic upgrade head

echo "[startup] starting uvicorn..."
# Single worker: the B1 plan has 1 vCPU and both apps share its 1.75GB RAM, and
# each worker loads the ONNX models separately. One worker halves memory with no
# throughput loss on a single core.
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
