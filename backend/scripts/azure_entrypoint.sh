#!/usr/bin/env bash
# Azure App Service container entrypoint for the AffectLearn backend.
#   1. Fetch the large facial model from Blob Storage if not baked into the image.
#   2. Run DB migrations (alembic upgrade head).
#   3. Start gunicorn with uvicorn workers (FastAPI + WebSockets).
# Behavioral ONNX (small) is committed in the image; only the 46MB facial model is pulled.
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-models}"
FACIAL_PATH="${AFFECT_MODEL_PATH:-models/cnn_lstm_best.onnx}"

# Pull facial model from a Blob SAS URL (set FACIAL_MODEL_URL as an App Setting).
if [ ! -f "$FACIAL_PATH" ] && [ -n "${FACIAL_MODEL_URL:-}" ]; then
  echo "[entrypoint] fetching facial model -> $FACIAL_PATH"
  mkdir -p "$(dirname "$FACIAL_PATH")"
  curl -fsSL "$FACIAL_MODEL_URL" -o "$FACIAL_PATH" \
    && echo "[entrypoint] facial model fetched ($(du -h "$FACIAL_PATH" | cut -f1))" \
    || echo "[entrypoint] WARN: facial fetch failed; pipeline runs behavioral-only"
fi

# DB migrations (safe to run every boot; alembic is idempotent).
echo "[entrypoint] alembic upgrade head"
alembic upgrade head || { echo "[entrypoint] migration failed"; exit 1; }

# Serve. PORT is provided by App Service. Keep workers low (ONNX models are per-process
# and hold RAM); 2 workers on a 2 vCPU plan is a sane pilot default.
PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-2}"
echo "[entrypoint] starting gunicorn on :$PORT ($WORKERS workers)"
exec gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "$WORKERS" \
  --bind "0.0.0.0:$PORT" \
  --timeout 120 \
  --access-logfile - --error-logfile -
