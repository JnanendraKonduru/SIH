#!/usr/bin/env bash
# scripts/run.sh
# ================
# Starts the Operation Nexus backend API (FastAPI/uvicorn on :8000) and
# serves the static frontend (on :5173) with a single command. Stop both
# with Ctrl+C.
set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting backend API on http://127.0.0.1:8000 ..."
cd "$ROOT_DIR/backend"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

cleanup() {
  echo "Stopping backend (pid $BACKEND_PID)..."
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

sleep 1.5
echo "Starting frontend on http://127.0.0.1:5173 ..."
cd "$ROOT_DIR/frontend"
python3 -m http.server 5173
