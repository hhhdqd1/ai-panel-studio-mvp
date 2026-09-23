#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_python="$project_root/backend/.venv/bin/python"

if [[ ! -x "$backend_python" || ! -d "$project_root/frontend/node_modules" ]]; then
  echo "请先按 README 安装后端和前端依赖。" >&2
  exit 1
fi

# Safe by default even when a DeepSeek key is present in the parent shell.
export APP_FAKE_MODEL="${APP_FAKE_MODEL:-1}"

cd "$project_root/backend"
"$backend_python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

cd "$project_root/frontend"
npm run dev &
frontend_pid=$!

cleanup() {
  kill "$backend_pid" "$frontend_pid" 2>/dev/null || true
  wait "$backend_pid" "$frontend_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "演播厅：http://127.0.0.1:5173/ （APP_FAKE_MODEL=${APP_FAKE_MODEL}）"
wait "$backend_pid" "$frontend_pid"
