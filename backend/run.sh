#!/usr/bin/env bash
# Avvia il backend LearnAI su http://localhost:8000 (reload disattivato).
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 "$@"
