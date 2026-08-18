#!/usr/bin/env bash
# Deploy NagarAI to the server on port 9999.
#
# Placeholder values — replace with your own before use:
#   SERVER  = "root@<YOUR_SERVER_IP>"
#   DASHSCOPE_API_KEY, OPENROUTER_API_KEY  (or export them in your shell / CI)
set -e

# --- config (edit these) -------------------------------------------------
SERVER="${NAGARAI_SERVER:-root@<YOUR_SERVER_IP>}"
DASHSCOPE_BASE_URL="${DASHSCOPE_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}"
DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY:-<YOUR_DASHSCOPE_KEY>}"
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-<YOUR_OPENROUTER_KEY>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# --------------------------------------------------------------------------

echo "== 1. sync code to server =="
rsync -az --exclude node_modules --exclude dist --exclude '*.pyc' --exclude __pycache__ \
  -e "ssh -o StrictHostKeyChecking=no" "$ROOT/backend/" "$SERVER:/opt/nagarai/backend/"
rsync -az --exclude node_modules -e "ssh -o StrictHostKeyChecking=no" \
  "$ROOT/frontend/site/" "$SERVER:/opt/nagarai/frontend/site/"
rsync -az -e "ssh -o StrictHostKeyChecking=no" \
  "$ROOT/scripts/" "$SERVER:/opt/nagarai/scripts/"

echo "== 2. install deps on server =="
ssh -o StrictHostKeyChecking=no "$SERVER" 'bash -s' <<'REMOTE'
set -e
cd /opt/nagarai/backend
if [ ! -d venv ]; then
  python3 -m venv venv
fi
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt || \
  ./venv/bin/pip install -q fastapi uvicorn httpx pydantic python-multipart
echo "deps installed"
REMOTE

echo "== 3. start server on :9999 =="
ssh -o StrictHostKeyChecking=no "$SERVER" "SERVER_BASE_URL='$DASHSCOPE_BASE_URL' SERVER_DASHSCOPE_KEY='$DASHSCOPE_API_KEY' SERVER_OPENROUTER_KEY='$OPENROUTER_API_KEY' bash -s" <<'REMOTE'
set -e
cd /opt/nagarai/backend
pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1
export DASHSCOPE_API_KEY="$SERVER_DASHSCOPE_KEY"
export DASHSCOPE_BASE_URL="$SERVER_BASE_URL"
export OPENROUTER_API_KEY="$SERVER_OPENROUTER_KEY"
setsid nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 9999 \
  > /opt/nagarai/nagarai.log 2>&1 < /dev/null &
echo "started, waiting..."
sleep 4
curl -s --max-time 10 http://127.0.0.1:9999/api/health
echo
REMOTE

echo "== done =="
