#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"

BACKEND_PORT=8000
FRONTEND_PORT=3000
BACKEND_PID=""
FRONTEND_PID=""

# ── cleanup ───────────────────────────────────────────────────────────────────

cleanup() {
  echo ""
  echo "Stopping services…"
  [[ -n "$BACKEND_PID"  ]] && kill "$BACKEND_PID"  2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  echo "Done."
}
trap cleanup EXIT INT TERM

# ── preflight ─────────────────────────────────────────────────────────────────

if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
  echo "ERROR: $BACKEND_DIR/.venv not found. Run: cd backend && uv venv && uv pip install -r requirements.txt"
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "ERROR: $FRONTEND_DIR/node_modules not found. Run: cd frontend && npm install"
  exit 1
fi

# ── backend ───────────────────────────────────────────────────────────────────

echo "Starting backend (DEMO_MODE=true, port $BACKEND_PORT)…"
(
  cd "$BACKEND_DIR"
  source .venv/bin/activate
  DEMO_MODE=true exec uvicorn api.main:app \
    --host 0.0.0.0 \
    --port "$BACKEND_PORT" \
    --log-level info
) &
BACKEND_PID=$!

# Wait for backend to be ready (up to 15s)
echo -n "Waiting for backend"
for i in $(seq 1 30); do
  if curl -sf "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; then
    echo " ready."
    break
  fi
  echo -n "."
  sleep 0.5
  if [[ $i -eq 30 ]]; then
    echo " timed out. Check backend logs above."
    exit 1
  fi
done

# ── frontend ──────────────────────────────────────────────────────────────────

echo "Starting frontend (port $FRONTEND_PORT)…"
(
  cd "$FRONTEND_DIR"
  exec npm run dev -- --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

# Wait for frontend to be ready (up to 20s)
echo -n "Waiting for frontend"
for i in $(seq 1 40); do
  if curl -sf "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
    echo " ready."
    break
  fi
  echo -n "."
  sleep 0.5
  if [[ $i -eq 40 ]]; then
    echo " timed out. Check frontend logs above."
    exit 1
  fi
done

# ── open browser ──────────────────────────────────────────────────────────────

URL="http://localhost:$FRONTEND_PORT"
echo ""
echo "Demo running at $URL"
echo "Press Ctrl+C to stop."
echo ""

if command -v xdg-open &>/dev/null; then
  xdg-open "$URL" &
elif command -v open &>/dev/null; then
  open "$URL" &
fi

# ── keep alive ────────────────────────────────────────────────────────────────

wait
