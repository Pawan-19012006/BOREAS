#!/usr/bin/env bash
# Starts the whole BOREAS system: boreas-core (FastAPI backend, port 8000)
# and frontend (Vite dev server, port 5174). Ctrl+C stops both.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup() {
  echo ""
  echo "Stopping BOREAS..."
  kill "$BACKEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting boreas-core backend on http://localhost:8000 ..."
(cd "$ROOT_DIR/boreas-core" && uv run uvicorn boreas_core.api.server:app --port 8000) &
BACKEND_PID=$!

# Give the backend a moment to bind before the frontend's health checks fire.
sleep 2

echo "Starting frontend on http://localhost:5174 ..."
cd "$ROOT_DIR/frontend"
npm run dev -- --port 5174
