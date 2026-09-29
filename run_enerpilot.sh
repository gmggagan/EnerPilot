#!/usr/bin/env sh
# One-command local start (macOS/Linux/Git Bash): serves UI + API at http://127.0.0.1:8000
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/backend" && python -m pip install -q -r requirements.txt
if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  cd "$ROOT/frontend" && { [ -d node_modules ] || npm install; } && npm run build
fi
cd "$ROOT/backend"
echo "ENERPILOT -> http://127.0.0.1:8000  (first start trains the model, ~10-30 s)"
python -m uvicorn main:app --host 127.0.0.1 --port 8000
